# coding:utf-8
"""增量回复文本的 TTS 排队播放辅助。"""

import re

from PySide6.QtCore import QObject

import config
from clients.tts_client import TtsWorker, stop_tts


STREAM_TTS_MIN_CHARS = 12


def _tts_countable_text(text):
    return re.sub(r"[\s\n\r\t。！？!?；;，,、：:,.…~`*_#\\-\\[\\](){}<>\"']+", '', text or '')


def stream_tts_cut_index(text, terminal=False, min_chars=STREAM_TTS_MIN_CHARS):
    """返回当前增量文本中适合送去 TTS 的切分位置。"""
    if terminal:
        return len(text)
    if len(_tts_countable_text(text)) < min_chars:
        return 0
    hard_marks = '\n。！？!?；;'
    hard_cut = max(text.rfind(mark) for mark in hard_marks) + 1
    if hard_cut > 0:
        return hard_cut
    if len(text) < 42:
        return 0
    soft_marks = '，,、：: '
    soft_cut = max(text.rfind(mark, 0, 56) for mark in soft_marks) + 1
    if soft_cut >= 18:
        return soft_cut
    return min(len(text), 56)


class StreamTtsQueue(QObject):
    """把不断增长的回复文本切成片段，并串行交给 TtsWorker 播放。"""

    def __init__(self, parent=None, label='TTS', on_started=None, on_idle=None):
        super().__init__(parent)
        self.label = label
        self.on_started = on_started
        self.on_idle = on_idle
        self.worker = None
        self.current_stream_id = None
        self.queue = []
        self.consumed = {}
        self.final_streams = set()

    def is_active(self):
        return self.worker is not None or bool(self.queue)

    def queue_text(self, stream_id, text, terminal=False):
        stream_id = stream_id or '__default__'
        text = (text or '').strip()
        if terminal:
            self.final_streams.add(stream_id)
        if not text:
            self._maybe_emit_idle()
            return False
        if not self._enabled():
            self._maybe_emit_idle()
            return False
        consumed = int(self.consumed.get(stream_id, 0) or 0)
        if consumed > len(text):
            consumed = 0
        delta = text[consumed:]
        if not delta.strip():
            self._maybe_emit_idle()
            return False
        cut = stream_tts_cut_index(delta, terminal=terminal)
        if cut <= 0:
            return False
        chunk = delta[:cut].strip()
        self.consumed[stream_id] = consumed + cut
        if not chunk:
            self._maybe_emit_idle()
            return False
        self.queue.append((stream_id, chunk))
        self._start_next()
        return True

    def reset(self, stream_id=None, stop_current=True):
        if stream_id is None:
            self.queue.clear()
            self.consumed.clear()
            self.final_streams.clear()
            if stop_current:
                self._stop_current()
            return
        self.queue = [item for item in self.queue if item[0] != stream_id]
        self.consumed.pop(stream_id, None)
        self.final_streams.discard(stream_id)
        if stop_current and self.current_stream_id == stream_id:
            self._stop_current()
            self._start_next()

    def _enabled(self):
        cfg = config.tts_config
        return bool(cfg.get('enabled') and cfg.get('api_key'))

    def _start_next(self):
        if self.worker is not None or not self.queue:
            return
        if not self._enabled():
            self.queue.clear()
            self._maybe_emit_idle()
            return
        stream_id, text = self.queue.pop(0)
        self.current_stream_id = stream_id
        if self.on_started:
            self.on_started(stream_id, text)
        self.worker = TtsWorker(text, config.tts_config, parent=self)
        self.worker.result_ready.connect(self._on_done)
        self.worker.start()

    def _on_done(self, success, text):
        if not success:
            print('%s failed: %s' % (self.label, text))
        self.worker = None
        self.current_stream_id = None
        self._start_next()
        self._maybe_emit_idle()

    def _stop_current(self):
        if self.worker is None:
            self.current_stream_id = None
            return
        try:
            self.worker.result_ready.disconnect(self._on_done)
        except (TypeError, RuntimeError):
            pass
        stop_tts()
        self.worker = None
        self.current_stream_id = None

    def _maybe_emit_idle(self):
        if self.worker is not None or self.queue or not self.final_streams:
            return
        self.final_streams.clear()
        if self.on_idle:
            self.on_idle()
