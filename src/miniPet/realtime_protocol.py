# coding:utf-8
import gzip
import json
import struct
from dataclasses import dataclass

PROTOCOL_VERSION = 0x1
HEADER_SIZE_WORDS = 0x1
HEADER_BYTE = (PROTOCOL_VERSION << 4) | HEADER_SIZE_WORDS

MSG_FULL_CLIENT_REQUEST = 0x1
MSG_AUDIO_ONLY_REQUEST = 0x2
MSG_FULL_SERVER_RESPONSE = 0x9
MSG_AUDIO_ONLY_RESPONSE = 0xB
MSG_ERROR = 0xF

FLAG_NO_SEQUENCE = 0x0
FLAG_POS_SEQUENCE = 0x1
FLAG_LAST_NO_SEQUENCE = 0x2
FLAG_LAST_NEG_SEQUENCE = 0x3
FLAG_EVENT = 0x4

SER_RAW = 0x0
SER_JSON = 0x1

COMP_NONE = 0x0
COMP_GZIP = 0x1

EVENT_START_CONNECTION = 1
EVENT_FINISH_CONNECTION = 2
EVENT_START_SESSION = 100
EVENT_FINISH_SESSION = 102
EVENT_TASK_REQUEST = 200
EVENT_UPDATE_CONFIG = 201
EVENT_SAY_HELLO = 300
EVENT_END_ASR = 400
EVENT_CHAT_TTS_TEXT = 500
EVENT_CHAT_TEXT_QUERY = 501
EVENT_CHAT_RAG_TEXT = 502
EVENT_CLIENT_INTERRUPT = 515

EVENT_CONNECTION_STARTED = 50
EVENT_CONNECTION_FAILED = 51
EVENT_CONNECTION_FINISHED = 52
EVENT_SESSION_STARTED = 150
EVENT_SESSION_CANCELED = 151
EVENT_SESSION_FINISHED = 152
EVENT_SESSION_FAILED = 153
EVENT_USAGE_RESPONSE = 154
EVENT_CONFIG_UPDATED = 251
EVENT_TTS_SENTENCE_START = 350
EVENT_TTS_SENTENCE_END = 351
EVENT_TTS_RESPONSE = 352
EVENT_TTS_ENDED = 359
EVENT_ASR_INFO = 450
EVENT_ASR_RESPONSE = 451
EVENT_ASR_ENDED = 459
EVENT_CHAT_RESPONSE = 550
EVENT_CHAT_TEXT_QUERY_CONFIRMED = 553
EVENT_CHAT_ENDED = 559
EVENT_DIALOG_COMMON_ERROR = 599

CONNECT_EVENTS = {EVENT_START_CONNECTION, EVENT_FINISH_CONNECTION, EVENT_CONNECTION_STARTED, EVENT_CONNECTION_FAILED, EVENT_CONNECTION_FINISHED}
SESSION_EVENTS = {
    EVENT_START_SESSION, EVENT_FINISH_SESSION, EVENT_TASK_REQUEST, EVENT_UPDATE_CONFIG,
    EVENT_SAY_HELLO, EVENT_END_ASR, EVENT_CHAT_TTS_TEXT, EVENT_CHAT_TEXT_QUERY,
    EVENT_CHAT_RAG_TEXT, EVENT_CLIENT_INTERRUPT, EVENT_SESSION_STARTED,
    EVENT_SESSION_CANCELED, EVENT_SESSION_FINISHED, EVENT_SESSION_FAILED, EVENT_USAGE_RESPONSE,
    EVENT_CONFIG_UPDATED, EVENT_TTS_SENTENCE_START, EVENT_TTS_SENTENCE_END,
    EVENT_TTS_RESPONSE, EVENT_TTS_ENDED, EVENT_ASR_INFO, EVENT_ASR_RESPONSE,
    EVENT_ASR_ENDED, EVENT_CHAT_RESPONSE, EVENT_CHAT_TEXT_QUERY_CONFIRMED,
    EVENT_CHAT_ENDED, EVENT_DIALOG_COMMON_ERROR,
}

EVENT_NAMES = {
    EVENT_START_CONNECTION: 'StartConnection',
    EVENT_FINISH_CONNECTION: 'FinishConnection',
    EVENT_START_SESSION: 'StartSession',
    EVENT_FINISH_SESSION: 'FinishSession',
    EVENT_TASK_REQUEST: 'TaskRequest',
    EVENT_UPDATE_CONFIG: 'UpdateConfig',
    EVENT_SAY_HELLO: 'SayHello',
    EVENT_END_ASR: 'EndASR',
    EVENT_CHAT_TTS_TEXT: 'ChatTTSText',
    EVENT_CHAT_TEXT_QUERY: 'ChatTextQuery',
    EVENT_CHAT_RAG_TEXT: 'ChatRAGText',
    EVENT_CLIENT_INTERRUPT: 'ClientInterrupt',
    EVENT_CONNECTION_STARTED: 'ConnectionStarted',
    EVENT_CONNECTION_FAILED: 'ConnectionFailed',
    EVENT_CONNECTION_FINISHED: 'ConnectionFinished',
    EVENT_SESSION_STARTED: 'SessionStarted',
    EVENT_SESSION_CANCELED: 'SessionCanceled',
    EVENT_SESSION_FINISHED: 'SessionFinished',
    EVENT_SESSION_FAILED: 'SessionFailed',
    EVENT_USAGE_RESPONSE: 'UsageResponse',
    EVENT_CONFIG_UPDATED: 'ConfigUpdated',
    EVENT_TTS_SENTENCE_START: 'TTSSentenceStart',
    EVENT_TTS_SENTENCE_END: 'TTSSentenceEnd',
    EVENT_TTS_RESPONSE: 'TTSResponse',
    EVENT_TTS_ENDED: 'TTSEnded',
    EVENT_ASR_INFO: 'ASRInfo',
    EVENT_ASR_RESPONSE: 'ASRResponse',
    EVENT_ASR_ENDED: 'ASREnded',
    EVENT_CHAT_RESPONSE: 'ChatResponse',
    EVENT_CHAT_TEXT_QUERY_CONFIRMED: 'ChatTextQueryConfirmed',
    EVENT_CHAT_ENDED: 'ChatEnded',
    EVENT_DIALOG_COMMON_ERROR: 'DialogCommonError',
}


@dataclass
class RealtimePacket:
    message_type: int
    flags: int
    serialization: int
    compression: int
    event: int = None
    sequence: int = None
    session_id: str = ''
    connect_id: str = ''
    error_code: int = None
    payload: object = None
    payload_bytes: bytes = b''

    @property
    def event_name(self):
        return EVENT_NAMES.get(self.event, str(self.event or ''))

    @property
    def is_audio(self):
        return self.message_type == MSG_AUDIO_ONLY_RESPONSE or self.event == EVENT_TTS_RESPONSE

    @property
    def is_error(self):
        return self.message_type == MSG_ERROR or self.event in (EVENT_CONNECTION_FAILED, EVENT_SESSION_FAILED, EVENT_DIALOG_COMMON_ERROR)


def _pack_u32(value):
    return struct.pack('>I', int(value))


def _pack_i32(value):
    return struct.pack('>i', int(value))


def _read_u32(data, offset):
    if offset + 4 > len(data):
        raise ValueError('Realtime packet truncated')
    return struct.unpack('>I', data[offset:offset + 4])[0], offset + 4


def _read_i32(data, offset):
    if offset + 4 > len(data):
        raise ValueError('Realtime packet truncated')
    return struct.unpack('>i', data[offset:offset + 4])[0], offset + 4


def _read_text(data, offset):
    size, offset = _read_u32(data, offset)
    if offset + size > len(data):
        raise ValueError('Realtime packet text field truncated')
    return data[offset:offset + size].decode('utf-8'), offset + size


def _payload_bytes(payload, serialization, compression):
    if payload is None:
        raw = b''
    elif serialization == SER_JSON:
        raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    elif isinstance(payload, bytes):
        raw = payload
    else:
        raw = bytes(payload)
    if compression == COMP_GZIP:
        raw = gzip.compress(raw)
    return raw


def build_client_packet(event, payload=None, session_id='', connect_id='', audio=False, sequence=None, compression=COMP_NONE):
    message_type = MSG_AUDIO_ONLY_REQUEST if audio else MSG_FULL_CLIENT_REQUEST
    serialization = SER_RAW if audio else SER_JSON
    flags = FLAG_EVENT
    header = bytes([
        HEADER_BYTE,
        (message_type << 4) | flags,
        (serialization << 4) | compression,
        0x00,
    ])
    optional = bytearray()
    if sequence is not None:
        flags = FLAG_POS_SEQUENCE if sequence > 0 else FLAG_LAST_NEG_SEQUENCE
        header = bytes([
            HEADER_BYTE,
            (message_type << 4) | flags,
            (serialization << 4) | compression,
            0x00,
        ])
        optional.extend(_pack_i32(sequence))
    optional.extend(_pack_u32(event))
    if event in CONNECT_EVENTS and connect_id:
        connect_bytes = connect_id.encode('utf-8')
        optional.extend(_pack_u32(len(connect_bytes)))
        optional.extend(connect_bytes)
    if event in SESSION_EVENTS:
        session_bytes = session_id.encode('utf-8')
        optional.extend(_pack_u32(len(session_bytes)))
        optional.extend(session_bytes)
    body = _payload_bytes(payload, serialization, compression)
    return header + bytes(optional) + _pack_u32(len(body)) + body


def build_json_event(event, payload=None, session_id='', connect_id=''):
    return build_client_packet(event, payload if payload is not None else {}, session_id=session_id, connect_id=connect_id)


def build_audio_event(audio, session_id):
    return build_client_packet(EVENT_TASK_REQUEST, audio or b'', session_id=session_id, audio=True)


def parse_packet(data):
    if len(data) < 8:
        raise ValueError('Realtime packet too short')
    first, second, third, _reserved = data[:4]
    header_words = first & 0x0F
    header_size = header_words * 4
    message_type = second >> 4
    flags = second & 0x0F
    serialization = third >> 4
    compression = third & 0x0F
    offset = header_size
    packet = RealtimePacket(message_type, flags, serialization, compression)

    if message_type == MSG_ERROR:
        packet.error_code, offset = _read_u32(data, offset)
    if flags in (FLAG_POS_SEQUENCE, FLAG_LAST_NEG_SEQUENCE):
        packet.sequence, offset = _read_i32(data, offset)
    if flags == FLAG_EVENT or flags in (FLAG_POS_SEQUENCE, FLAG_LAST_NEG_SEQUENCE):
        packet.event, offset = _read_u32(data, offset)
    if packet.event in CONNECT_EVENTS and offset + 4 <= len(data):
        possible_size = struct.unpack('>I', data[offset:offset + 4])[0]
        possible_payload_offset = offset + 4 + possible_size
        if possible_payload_offset + 4 <= len(data):
            payload_size_at_next = struct.unpack('>I', data[possible_payload_offset:possible_payload_offset + 4])[0]
            if possible_payload_offset + 4 + payload_size_at_next == len(data):
                packet.connect_id, offset = _read_text(data, offset)
    if packet.event in SESSION_EVENTS:
        packet.session_id, offset = _read_text(data, offset)

    payload_size, offset = _read_u32(data, offset)
    if offset + payload_size > len(data):
        raise ValueError('Realtime packet payload truncated')
    payload = data[offset:offset + payload_size]
    if compression == COMP_GZIP and payload:
        payload = gzip.decompress(payload)
    packet.payload_bytes = payload
    if serialization == SER_JSON and payload:
        packet.payload = json.loads(payload.decode('utf-8'))
    elif serialization == SER_JSON:
        packet.payload = {}
    else:
        packet.payload = payload
    return packet
