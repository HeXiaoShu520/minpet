# coding:utf-8
"""
豆包端到端 Realtime 客户端。

负责 Realtime WebSocket 会话、麦克风采集、服务端音频播放和事件分发。
窗口层只接收状态、ASR 文本、AI 文本和输入音量，不直接处理协议细节。
"""

import asyncio
import audioop
import inspect
import queue
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

from miniPet import config
from miniPet.protocols.realtime_protocol import (
    EVENT_ASR_INFO,
    EVENT_ASR_RESPONSE,
    EVENT_CHAT_ENDED,
    EVENT_CHAT_RESPONSE,
    EVENT_CLIENT_INTERRUPT,
    EVENT_CONNECTION_FAILED,
    EVENT_CONNECTION_STARTED,
    EVENT_DIALOG_COMMON_ERROR,
    EVENT_FINISH_CONNECTION,
    EVENT_FINISH_SESSION,
    EVENT_SESSION_CANCELED,
    EVENT_SESSION_FAILED,
    EVENT_SESSION_FINISHED,
    EVENT_SESSION_STARTED,
    EVENT_SAY_HELLO,
    EVENT_START_CONNECTION,
    EVENT_START_SESSION,
    EVENT_TTS_ENDED,
    EVENT_TTS_RESPONSE,
    build_audio_event,
    build_json_event,
    parse_packet,
)
from miniPet.clients.tts_client import PcmStreamPlayer, stop_tts

REALTIME_URL = 'wss://openspeech.bytedance.com/api/v3/realtime/dialogue'
REALTIME_RESOURCE_ID = 'volc.speech.dialog'
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2
INPUT_CHUNK_MS = 20
INPUT_CHUNK_BYTES = int(INPUT_SAMPLE_RATE * INPUT_CHUNK_MS / 1000) * SAMPLE_WIDTH


class RealtimeError(Exception):
    """Realtime 通话链路异常。"""


class MicrophoneStreamer:
    """把麦克风 PCM 块推给上层回调的轻量封装。"""

    def __init__(self, on_audio):
        if sd is None:
            raise RealtimeError('缺少 sounddevice，请执行：pip install sounddevice')
        self.on_audio = on_audio
        self.stream = None

    def start(self):
        if self.stream is not None:
            return
        self.stream = sd.RawInputStream(
            samplerate=INPUT_SAMPLE_RATE,
            channels=CHANNELS,
            dtype='int16',
            blocksize=INPUT_CHUNK_BYTES // SAMPLE_WIDTH,
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


class RealtimeSession:
    def __init__(self, cfg, status_cb=None, asr_cb=None, chat_cb=None, error_cb=None, event_cb=None, level_cb=None):
        self.cfg = dict(cfg)
        self.status_cb = status_cb or (lambda text: None)
        self.asr_cb = asr_cb or (lambda text, interim: None)
        self.chat_cb = chat_cb or (lambda text: None)
        self.error_cb = error_cb or (lambda text: None)
        self.event_cb = event_cb or (lambda name, payload: None)
        self.level_cb = level_cb or (lambda level: None)
        self.connect_id = str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())
        self.dialog_id = ''
        self.ws = None
        self.commands = queue.Queue()
        self.audio_queue = queue.Queue(maxsize=120)
        self.mic = None
        self.player = None
        self.session_started = False
        self.say_hello_finished = False
        self.playing_tts = False
        self.resuming_recording = False
        self.recording = False
        self.recording_requested = False
        self.closed = False
        self.sent_audio_bytes = 0
        self.received_audio_bytes = 0
        self.last_send_audio_log_time = 0
        self.last_recv_audio_log_time = 0
        self.text_query = (self.cfg.get('text_query') or '').strip()
        self.single_turn = bool(self.cfg.get('single_turn', False))
        self.skip_welcome = bool(self.cfg.get('skip_welcome', False) or self.text_query)

    def command(self, name):
        self.commands.put(name)

    def _emit_status(self, text):
        self.status_cb(text)

    def _emit_error(self, text):
        self.error_cb(text)

    def _log(self, message):
        print('[Realtime] %s' % message, flush=True)

    def _payload_summary(self, packet):
        payload = packet.payload or {}
        if packet.event == EVENT_ASR_RESPONSE:
            results = payload.get('results') or []
            if results:
                result = results[0]
                return {'text': result.get('text', ''), 'is_interim': bool(result.get('is_interim')), 'stream_asr_finish': bool(result.get('stream_asr_finish'))}
        if packet.event == EVENT_CHAT_RESPONSE:
            return {'content': payload.get('content', '')}
        if packet.event in (EVENT_TTS_RESPONSE,):
            return {'audio_bytes': len(packet.payload_bytes or b'')}
        return payload

    def _build_start_session_payload(self):
        model = self.cfg.get('model') or config.DEFAULT_REALTIME_CONFIG['model']
        dialog_extra = {
            'input_mod': 'keep_alive',
            'strict_audit': True,
            'enable_conversation_truncate': True,
            'enable_user_query_exit': True,
            'model': model,
        }
        if model == '1.2.1.1':
            dialog_extra['enable_music'] = True
        return {
            'asr': {
                'audio_info': {
                    'format': 'pcm',
                    'sample_rate': INPUT_SAMPLE_RATE,
                    'channel': CHANNELS,
                },
                'extra': {
                    'end_smooth_window_ms': 800,
                    'enable_asr_twopass': True,
                },
            },
            'dialog': {
                'bot_name': self.cfg.get('bot_name') or config.DEFAULT_REALTIME_CONFIG['bot_name'],
                'system_role': self.cfg.get('system_role') or config.DEFAULT_REALTIME_CONFIG['system_role'],
                'speaking_style': self.cfg.get('speaking_style') or config.DEFAULT_REALTIME_CONFIG['speaking_style'],
                'dialog_id': self.dialog_id,
                'extra': dialog_extra,
            },
            'tts': {
                'speaker': self.cfg.get('speaker') or config.DEFAULT_REALTIME_CONFIG['speaker'],
                'audio_config': {
                    'channel': CHANNELS,
                    'format': 'pcm_s16le',
                    'sample_rate': OUTPUT_SAMPLE_RATE,
                },
                'extra': {},
            },
        }

    def _headers(self):
        api_key = config.tts_config.get('api_key') or ''
        if not api_key:
            raise RealtimeError('请先在语音设置中填写 TTS API Key')
        return {
            'X-Api-Key': api_key,
            'X-Api-Resource-Id': REALTIME_RESOURCE_ID,
            'X-Api-Connect-Id': self.connect_id,
        }

    async def run(self):
        if websockets is None:
            raise RealtimeError('缺少 websockets，请执行：pip install websockets')
        self._emit_status('连接中')
        self._log('connecting url=%s connect_id=%s session_id=%s' % (REALTIME_URL, self.connect_id, self.session_id))
        header_arg = 'additional_headers' if 'additional_headers' in inspect.signature(websockets.connect).parameters else 'extra_headers'
        kwargs = {header_arg: self._headers(), 'ping_interval': 20, 'ping_timeout': 20}
        async with websockets.connect(REALTIME_URL, **kwargs) as ws:
            self.ws = ws
            self._log('websocket connected')
            await self._send_json(EVENT_START_CONNECTION, {})
            await self._send_json(EVENT_START_SESSION, self._build_start_session_payload())
            receiver = asyncio.create_task(self._receive_loop())
            commander = asyncio.create_task(self._command_loop())
            try:
                await asyncio.wait([receiver, commander], return_when=asyncio.FIRST_COMPLETED)
            finally:
                self.closed = True
                self._log('closing session')
                self._stop_recording()
                self._close_player()
                for task in (receiver, commander):
                    task.cancel()

    async def _send_json(self, event, payload=None, connect_id=''):
        packet = build_json_event(event, payload or {}, session_id=self.session_id, connect_id=connect_id)
        self._log('send event=%s bytes=%d payload=%s' % (event, len(packet), payload or {}))
        await self.ws.send(packet)

    async def _send_say_hello(self):
        await self._send_json(EVENT_SAY_HELLO, {
            'content': '你好呀，有什么需要帮忙的吗？',
        })

    async def _send_text_query(self, text):
        await self._send_json(EVENT_CHAT_TEXT_QUERY, {
            'content': text,
        })

    async def _send_audio(self, audio):
        packet = build_audio_event(audio, self.session_id)
        self.sent_audio_bytes += len(audio or b'')
        await self.ws.send(packet)

    async def _receive_loop(self):
        async for message in self.ws:
            packet = parse_packet(message)
            if packet.is_audio:
                self.received_audio_bytes += len(packet.payload_bytes or b'')
            elif packet.event != EVENT_ASR_RESPONSE:
                self._log('recv event=%s(%s) payload=%s' % (packet.event_name, packet.event, self._payload_summary(packet)))
            self.event_cb(packet.event_name, packet.payload if not packet.is_audio else {})
            if packet.event == EVENT_CONNECTION_STARTED:
                self._emit_status('连接已建立')
            elif packet.event == EVENT_SESSION_STARTED:
                payload = packet.payload or {}
                self.dialog_id = payload.get('dialog_id') or self.dialog_id
                self.session_started = True
                self.say_hello_finished = self.skip_welcome
                if self.text_query:
                    await self._send_text_query(self.text_query)
                    self._emit_status('唱歌中')
                else:
                    await self._send_say_hello()
                    self._emit_status('会话中')
                if self.recording_requested and not self.say_hello_finished:
                    self._log('recording pending until welcome finished')
            elif packet.event == EVENT_ASR_INFO:
                self._interrupt_playback()
            elif packet.event == EVENT_ASR_RESPONSE:
                for result in (packet.payload or {}).get('results', []):
                    text = result.get('text', '')
                    interim = bool(result.get('is_interim'))
                    stream_finish = bool(result.get('stream_asr_finish'))
                    if text and (not interim or stream_finish):
                        self._log('asr final text=%s' % text)
                    self.asr_cb(text, interim)
            elif packet.event == EVENT_CHAT_RESPONSE:
                self.chat_cb((packet.payload or {}).get('content', ''))
            elif packet.event == EVENT_TTS_RESPONSE:
                self._write_playback(packet.payload_bytes)
            elif packet.event == EVENT_TTS_ENDED:
                asyncio.create_task(self._finish_tts_playback())
            elif packet.event == EVENT_CHAT_ENDED:
                self._emit_status('回复结束')
                if self.single_turn:
                    await self._wait_playback_done()
                    await self._send_json(EVENT_FINISH_SESSION, {})
                    await asyncio.sleep(0.1)
                    await self._send_json(EVENT_FINISH_CONNECTION, {})
                    self.closed = True
                    return
            elif packet.event == EVENT_SESSION_CANCELED:
                self._emit_status('会话已取消')
                self.closed = True
                return
            elif packet.event in (EVENT_SESSION_FINISHED,):
                self._emit_status('会话已结束')
                self.closed = True
                return
            elif packet.event in (EVENT_CONNECTION_FAILED, EVENT_SESSION_FAILED, EVENT_DIALOG_COMMON_ERROR) or packet.is_error:
                error_text = self._error_text(packet)
                self._log('error event=%s text=%s' % (packet.event_name, error_text))
                if 'session has ended' in error_text:
                    self._emit_status('会话已结束')
                    self.closed = True
                    return
                self._emit_error(error_text)

    async def _command_loop(self):
        while not self.closed:
            try:
                command = await asyncio.to_thread(self.commands.get, True, 0.1)
            except queue.Empty:
                await self._drain_audio()
                continue
            if command == 'start_recording':
                self._log('command start_recording')
                self.recording_requested = True
                if not self.session_started:
                    self._log('recording pending until session started')
                    continue
                if not self.say_hello_finished:
                    self._log('recording pending until welcome finished')
                    continue
                self._interrupt_playback()
                self._start_recording()
                self._emit_status('正在听')
            elif command == 'stop_recording':
                self._log('command stop_recording')
                self.recording_requested = False
                self._stop_recording()
                await self._drain_audio()
                self._emit_status('麦克风已关闭')
            elif command == 'interrupt':
                self._log('command interrupt')
                self._interrupt_playback()
                await self._send_json(EVENT_CLIENT_INTERRUPT, {})
            elif command == 'finish':
                self._log('command finish')
                self._stop_recording()
                await self._drain_audio()
                await self._send_json(EVENT_FINISH_SESSION, {})
                await asyncio.sleep(0.1)
                await self._send_json(EVENT_FINISH_CONNECTION, {})
                self.closed = True
                return
            await self._drain_audio()

    async def _drain_audio(self):
        if self.playing_tts:
            self._clear_audio_queue()
            return
        while True:
            try:
                audio = self.audio_queue.get_nowait()
            except queue.Empty:
                return
            await self._send_audio(audio)
            await asyncio.sleep(0)

    def _clear_audio_queue(self):
        dropped = 0
        while True:
            try:
                self.audio_queue.get_nowait()
                dropped += 1
            except queue.Empty:
                break
        if dropped:
            self._log('dropped audio frames=%d' % dropped)

    async def _wait_playback_done(self):
        player = self.player
        if player is not None:
            self._log('waiting local playback to finish')
            await asyncio.to_thread(player.wait_done)
        self._close_player()
        self.playing_tts = False

    async def _finish_tts_playback(self):
        if self.resuming_recording:
            return
        self.resuming_recording = True
        try:
            await self._wait_playback_done()
            if not self.say_hello_finished:
                self.say_hello_finished = True
            if self.recording_requested and not self.closed:
                self._log('resume microphone after local playback finished')
                self._start_recording()
                self._emit_status('正在听')
        finally:
            self.resuming_recording = False

    def _on_mic_audio(self, audio):
        if not self.recording:
            return
        try:
            rms = audioop.rms(audio, SAMPLE_WIDTH)
            self.level_cb(min(100, int(rms / 120)))
        except Exception:
            pass
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
            self._log('microphone already recording')
            return
        self.recording = True
        self.mic = MicrophoneStreamer(self._on_mic_audio)
        self.mic.start()
        self._log('microphone started sample_rate=%d chunk_bytes=%d' % (INPUT_SAMPLE_RATE, INPUT_CHUNK_BYTES))

    def _stop_recording(self):
        self.recording = False
        mic = self.mic
        self.mic = None
        if mic is not None:
            mic.stop()
            self._log('microphone stopped sent_audio=%dB' % self.sent_audio_bytes)

    def _write_playback(self, chunk):
        if not chunk:
            return
        if not self.playing_tts:
            self.playing_tts = True
            self._stop_recording()
            self._clear_audio_queue()
            self._log('pause microphone during playback')
        if self.player is None:
            stop_tts()
            self.player = PcmStreamPlayer(OUTPUT_SAMPLE_RATE)
            self._log('playback started sample_rate=%d' % OUTPUT_SAMPLE_RATE)
        self.player.write(chunk)

    def _close_player(self):
        player = self.player
        self.player = None
        if player is not None:
            player.close()
            self._log('playback closed received_audio=%dB' % self.received_audio_bytes)

    def _interrupt_playback(self):
        self._close_player()

    def _error_text(self, packet):
        payload = packet.payload or {}
        if isinstance(payload, dict):
            return payload.get('message') or payload.get('error') or str(payload)
        return str(payload or packet.event_name or 'Realtime error')


class RealtimeWorker(QThread):
    status_changed = Signal(str)
    asr_received = Signal(str, bool)
    chat_received = Signal(str)
    error_received = Signal(str)
    event_received = Signal(str, dict)
    level_changed = Signal(int)
    finished_signal = Signal()

    def __init__(self, cfg=None, parent=None):
        super().__init__(parent)
        self.cfg = dict(cfg) if cfg is not None else dict(config.realtime_config)
        self.session = None
        self._ready = threading.Event()

    def run(self):
        self.session = RealtimeSession(
            self.cfg,
            status_cb=self.status_changed.emit,
            asr_cb=self.asr_received.emit,
            chat_cb=self.chat_received.emit,
            error_cb=self.error_received.emit,
            event_cb=self.event_received.emit,
            level_cb=self.level_changed.emit,
        )
        self._ready.set()
        try:
            asyncio.run(self.session.run())
        except Exception as e:
            self.error_received.emit(str(e))
        finally:
            self.finished_signal.emit()

    def _command(self, name):
        if self.session is None and not self._ready.wait(2):
            print('[Realtime] drop command=%s reason=session_not_ready' % name, flush=True)
            return
        if self.session is not None:
            print('[Realtime] enqueue command=%s' % name, flush=True)
            self.session.command(name)

    def start_recording(self):
        self._command('start_recording')

    def stop_recording(self):
        self._command('stop_recording')

    def interrupt(self):
        self._command('interrupt')

    def finish(self):
        self._command('finish')
