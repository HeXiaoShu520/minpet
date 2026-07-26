# coding:utf-8
"""
火山豆包流式 ASR 客户端。

这个模块把麦克风 PCM 音频按火山 SAUC 协议打包，经 WebSocket 发送到 ASR
服务，并把中间识别结果、最终识别结果和错误通过 Qt 信号返回给 UI。
"""

import asyncio
import gzip
import inspect
import json
import queue
import struct
import threading
import uuid

from PySide6.QtCore import QThread, Signal

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    import websockets
except Exception:
    websockets = None

import config

ASR_URL = 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async'
ASR_RESOURCE_ID = 'volc.seedasr.sauc.duration'
INPUT_SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
CHUNK_MS = 200
CHUNK_BYTES = int(INPUT_SAMPLE_RATE * CHUNK_MS / 1000) * SAMPLE_WIDTH

MSG_FULL_CLIENT_REQUEST = 0x1
MSG_AUDIO_ONLY_REQUEST = 0x2
MSG_FULL_SERVER_RESPONSE = 0x9
MSG_ERROR = 0xF
SER_RAW = 0x0
SER_JSON = 0x1
COMP_GZIP = 0x1
COMP_NONE = 0x0
FLAG_NONE = 0x0
FLAG_POS_SEQUENCE = 0x1
FLAG_LAST_NO_SEQUENCE = 0x2
FLAG_LAST_NEG_SEQUENCE = 0x3


class AsrError(Exception):
    """ASR 采集或协议调用异常。"""


def _header(message_type, flags, serialization, compression):
    return bytes([0x11, (message_type << 4) | flags, (serialization << 4) | compression, 0x00])


def _pack_u32(value):
    return struct.pack('>I', int(value))


def _pack_i32(value):
    return struct.pack('>i', int(value))


def _build_packet(message_type, flags, serialization, compression, payload=b'', sequence=None):
    if serialization == SER_JSON and not isinstance(payload, bytes):
        payload = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if compression == COMP_GZIP:
        payload = gzip.compress(payload)
    parts = [_header(message_type, flags, serialization, compression)]
    if sequence is not None:
        parts.append(_pack_i32(sequence))
    parts.append(_pack_u32(len(payload)))
    parts.append(payload)
    return b''.join(parts)


def build_start_request():
    payload = {
        'user': {'uid': 'miniPet'},
        'audio': {
            'format': 'pcm',
            'codec': 'raw',
            'rate': INPUT_SAMPLE_RATE,
            'bits': 16,
            'channel': CHANNELS,
            'language': 'zh-CN',
        },
        'request': {
            'model_name': 'bigmodel',
            'enable_itn': True,
            'enable_punc': True,
            'enable_ddc': False,
            'enable_nonstream': True,
            'show_utterances': True,
            'result_type': 'full',
            'end_window_size': 800,
            'force_to_speech_time': 800,
        },
    }
    return _build_packet(MSG_FULL_CLIENT_REQUEST, FLAG_NONE, SER_JSON, COMP_GZIP, payload)


def build_audio_packet(audio, final=False, sequence=None):
    flags = FLAG_LAST_NO_SEQUENCE if final and sequence is None else FLAG_LAST_NEG_SEQUENCE if final else FLAG_NONE
    return _build_packet(MSG_AUDIO_ONLY_REQUEST, flags, SER_RAW, COMP_GZIP, audio or b'', sequence=sequence)


def parse_response(data):
    if len(data) < 8:
        raise AsrError('ASR response too short')
    message_type = data[1] >> 4
    flags = data[1] & 0x0F
    serialization = data[2] >> 4
    compression = data[2] & 0x0F
    offset = (data[0] & 0x0F) * 4
    sequence = None
    if message_type == MSG_ERROR:
        code = struct.unpack('>I', data[offset:offset + 4])[0]
        offset += 4
        size = struct.unpack('>I', data[offset:offset + 4])[0]
        offset += 4
        return {'error': data[offset:offset + size].decode('utf-8', errors='replace'), 'code': code}
    if flags in (FLAG_POS_SEQUENCE, FLAG_LAST_NEG_SEQUENCE):
        sequence = struct.unpack('>i', data[offset:offset + 4])[0]
        offset += 4
    size = struct.unpack('>I', data[offset:offset + 4])[0]
    offset += 4
    payload = data[offset:offset + size]
    if compression == COMP_GZIP and payload:
        payload = gzip.decompress(payload)
    if serialization == SER_JSON and payload:
        result = json.loads(payload.decode('utf-8'))
    else:
        result = {'payload': payload}
    result['_sequence'] = sequence
    result['_last'] = flags in (FLAG_LAST_NO_SEQUENCE, FLAG_LAST_NEG_SEQUENCE)
    return result


class MicrophoneStreamer:
    def __init__(self, on_audio):
        if sd is None:
            raise AsrError('缺少 sounddevice，请执行：pip install sounddevice')
        self.on_audio = on_audio
        self.stream = None

    def start(self):
        if self.stream is not None:
            return
        self.stream = sd.RawInputStream(
            samplerate=INPUT_SAMPLE_RATE,
            channels=CHANNELS,
            dtype='int16',
            blocksize=CHUNK_BYTES // SAMPLE_WIDTH,
            callback=self._callback,
        )
        self.stream.start()

    def _callback(self, indata, frames, time_info, status):
        self.on_audio(bytes(indata))

    def stop(self):
        stream = self.stream
        self.stream = None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()


class AsrSession:
    def __init__(self, text_cb=None, final_cb=None, status_cb=None, error_cb=None):
        self.text_cb = text_cb or (lambda text: None)
        self.final_cb = final_cb or (lambda text: None)
        self.status_cb = status_cb or (lambda text: None)
        self.error_cb = error_cb or (lambda text: None)
        self.audio_queue = queue.Queue(maxsize=80)
        self.commands = queue.Queue()
        self.mic = None
        self.recording = False
        self.closed = False
        self.sent_finals = set()

    def command(self, name):
        self.commands.put(name)

    def _headers(self):
        api_key = config.tts_config.get('api_key') or ''
        if not api_key:
            raise AsrError('请先在语音设置中填写 TTS API Key')
        request_id = str(uuid.uuid4())
        return {
            'X-Api-Key': api_key,
            'X-Api-Resource-Id': ASR_RESOURCE_ID,
            'X-Api-Request-Id': request_id,
            'X-Api-Connect-Id': request_id,
            'X-Api-Sequence': '-1',
        }

    async def run(self):
        if websockets is None:
            raise AsrError('缺少 websockets，请执行：pip install websockets')
        header_arg = 'additional_headers' if 'additional_headers' in inspect.signature(websockets.connect).parameters else 'extra_headers'
        async with websockets.connect(ASR_URL, **{header_arg: self._headers()}, ping_interval=20, ping_timeout=20) as ws:
            self.status_cb('ASR已连接')
            await ws.send(build_start_request())
            receiver = asyncio.create_task(self._receive_loop(ws))
            commander = asyncio.create_task(self._command_loop(ws))
            try:
                await asyncio.wait([receiver, commander], return_when=asyncio.FIRST_COMPLETED)
            finally:
                self.closed = True
                self._stop_recording()
                for task in (receiver, commander):
                    task.cancel()

    async def _receive_loop(self, ws):
        async for message in ws:
            data = parse_response(message)
            if data.get('error'):
                error = str(data.get('error'))
                if 'session has ended' in error:
                    self.closed = True
                    return
                self.error_cb(error)
                continue
            text = self._extract_text(data)
            if text:
                self.text_cb(text)
            for item_id, final_text in self._extract_final_utterances(data):
                if item_id not in self.sent_finals and final_text:
                    self.sent_finals.add(item_id)
                    self.final_cb(final_text)

    def _extract_text(self, data):
        result = data.get('result') or {}
        if isinstance(result, dict):
            return result.get('text') or ''
        return ''

    def _extract_final_utterances(self, data):
        result = data.get('result') or {}
        utterances = result.get('utterances') if isinstance(result, dict) else []
        finals = []
        for index, utterance in enumerate(utterances or []):
            if utterance.get('definite'):
                item_id = '%s:%s:%s' % (utterance.get('start_time'), utterance.get('end_time'), index)
                finals.append((item_id, utterance.get('text') or ''))
        return finals

    async def _command_loop(self, ws):
        while not self.closed:
            try:
                command = await asyncio.to_thread(self.commands.get, True, 0.05)
            except queue.Empty:
                await self._drain_audio(ws)
                continue
            if command == 'start':
                self._start_recording()
                self.status_cb('正在识别')
            elif command == 'stop':
                self._stop_recording()
                await self._drain_audio(ws)
                self.status_cb('ASR已暂停')
            elif command == 'finish':
                self._stop_recording()
                await self._drain_audio(ws)
                await ws.send(build_audio_packet(b'', final=True))
                self.closed = True
                return
            await self._drain_audio(ws)

    async def _drain_audio(self, ws):
        while True:
            try:
                audio = self.audio_queue.get_nowait()
            except queue.Empty:
                return
            await ws.send(build_audio_packet(audio))
            await asyncio.sleep(0)

    def _on_audio(self, audio):
        if not self.recording:
            return
        try:
            self.audio_queue.put_nowait(audio)
        except queue.Full:
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass
            self.audio_queue.put_nowait(audio)

    def _start_recording(self):
        if self.recording:
            return
        self.recording = True
        self.mic = MicrophoneStreamer(self._on_audio)
        self.mic.start()

    def _stop_recording(self):
        self.recording = False
        mic = self.mic
        self.mic = None
        if mic is not None:
            mic.stop()


class AsrWorker(QThread):
    status_changed = Signal(str)
    text_received = Signal(str)
    final_received = Signal(str)
    error_received = Signal(str)
    finished_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = None
        self._ready = threading.Event()

    def run(self):
        self.session = AsrSession(
            text_cb=self.text_received.emit,
            final_cb=self.final_received.emit,
            status_cb=self.status_changed.emit,
            error_cb=self.error_received.emit,
        )
        self._ready.set()
        try:
            asyncio.run(self.session.run())
        except Exception as e:
            self.error_received.emit(str(e))
        finally:
            self.finished_signal.emit()

    def _command(self, name):
        if self.session is not None:
            self.session.command(name)

    def start_recording(self):
        self._command('start')

    def stop_recording(self):
        self._command('stop')

    def finish(self):
        self._command('finish')
