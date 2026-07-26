# coding:utf-8
"""Streaming reply TTS queue with audio prefetch and ordered playback."""

import queue
import re
import threading

from PySide6.QtCore import QObject, QThread, Signal

import config
from clients.tts_client import (
    PcmStreamPlayer,
    SAMPLE_RATE,
    clear_active_player,
    request_audio_chunks,
    set_active_player,
    stop_tts,
)


STREAM_TTS_FIRST_MIN_CHARS = 15
STREAM_TTS_FIRST_TARGET_CHARS = 30
STREAM_TTS_FIRST_MAX_CHARS = 38
STREAM_TTS_NEXT_MIN_CHARS = 50
STREAM_TTS_NEXT_TARGET_CHARS = 80
STREAM_TTS_NEXT_MAX_CHARS = 100
STREAM_TTS_DEBUG = False


def _debug(message):
    if STREAM_TTS_DEBUG:
        print(message, flush=True)


def _tts_countable_text(text):
    return re.sub(r"""[\s\n\r\t。！？!?；;，,、：:.…~`*_#\[\](){}<>"'\-]+""", '', text or '')


def _last_mark_index(text, marks, end):
    positions = [text.rfind(mark, 0, end) for mark in marks]
    return max(positions) + 1


def stream_tts_cut_index(text, terminal=False, first_chunk=True):
    """Return a stable cut point for text that can be sent to TTS."""
    text = text or ''
    if not text:
        return 0
    min_chars = STREAM_TTS_FIRST_MIN_CHARS if first_chunk else STREAM_TTS_NEXT_MIN_CHARS
    target_chars = STREAM_TTS_FIRST_TARGET_CHARS if first_chunk else STREAM_TTS_NEXT_TARGET_CHARS
    max_chars = STREAM_TTS_FIRST_MAX_CHARS if first_chunk else STREAM_TTS_NEXT_MAX_CHARS
    if terminal and len(text) <= max_chars:
        return len(text)
    if len(_tts_countable_text(text)) < min_chars:
        return len(text) if terminal else 0

    hard_cut = _last_mark_index(text, '\n。！？!?；;', min(len(text), max_chars) + 1)
    if hard_cut > 0 and len(_tts_countable_text(text[:hard_cut])) >= min_chars:
        return hard_cut

    if not terminal and len(text) < target_chars:
        return 0

    soft_cut = _last_mark_index(text, '，,、：: ', min(len(text), max_chars) + 1)
    if soft_cut > 0 and len(_tts_countable_text(text[:soft_cut])) >= min_chars:
        return soft_cut

    return min(len(text), max_chars)


class _PipelineTtsWorker(QThread):
    """Prefetch TTS audio in one thread while another ordered loop plays it."""

    chunk_started = Signal(str, str)
    result_ready = Signal(bool, str)
    _STOP = object()

    def __init__(self, label='TTS', parent=None):
        super().__init__(parent)
        self.label = label
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.player = None

    def enqueue(self, stream_id, text, terminal=False):
        _debug('[StreamTTS] queued chars=%d terminal=%s stream=%s' % (len(text or ''), terminal, stream_id))
        self.text_queue.put((stream_id, text, bool(terminal)))

    def finish_stream(self, stream_id):
        self.text_queue.put((stream_id, '', True))

    def stop(self):
        self.stop_event.set()
        self.text_queue.put(self._STOP)
        self.audio_queue.put(self._STOP)
        stop_tts()
        player = self.player
        if player is not None:
            try:
                player.close()
            except Exception:
                pass

    def run(self):
        cfg = dict(config.tts_config)
        synth = threading.Thread(target=self._synth_loop, args=(cfg,), daemon=True)
        synth.start()
        try:
            has_audio = False
            while not self.stop_event.is_set():
                item = self.audio_queue.get()
                if item is self._STOP:
                    break
                kind = item[0]
                if kind == 'error':
                    raise RuntimeError(item[1])
                if kind == 'done':
                    break
                _kind, stream_id, text, chunks = item
                if not chunks:
                    continue
                if self.player is None:
                    self.player = PcmStreamPlayer(SAMPLE_RATE)
                    set_active_player(self.player)
                    _debug('[StreamTTS] playback started stream=%s' % stream_id)
                self.chunk_started.emit(stream_id, text)
                for payload in chunks:
                    if self.stop_event.is_set():
                        break
                    if payload:
                        has_audio = True
                        self.player.write(payload)
            if not self.stop_event.is_set() and has_audio:
                self.player.wait_done()
            if not self.stop_event.is_set():
                self.result_ready.emit(True, '')
        except Exception as exc:
            if not self.stop_event.is_set():
                self.result_ready.emit(False, str(exc))
        finally:
            self.stop_event.set()
            self.text_queue.put(self._STOP)
            synth.join(timeout=0.2)
            player = self.player
            self.player = None
            if player is not None:
                clear_active_player(player)
                try:
                    player.close()
                except Exception:
                    pass

    def _synth_loop(self, cfg):
        while not self.stop_event.is_set():
            item = self.text_queue.get()
            if item is self._STOP:
                self.audio_queue.put(self._STOP)
                return
            stream_id, text, terminal = item
            try:
                if text:
                    _debug('[StreamTTS] synth start chars=%d stream=%s' % (len(text or ''), stream_id))
                    chunks = request_audio_chunks(text, cfg, cancel_event=self.stop_event)
                    _debug('[StreamTTS] synth done chunks=%d stream=%s' % (len(chunks or []), stream_id))
                    if not self.stop_event.is_set():
                        self.audio_queue.put(('audio', stream_id, text, chunks))
                if terminal and not self.stop_event.is_set():
                    self.audio_queue.put(('done', stream_id))
                    return
            except Exception as exc:
                if not self.stop_event.is_set():
                    self.audio_queue.put(('error', str(exc)))
                return


class StreamTtsQueue(QObject):
    """Cut streaming text, prefetch TTS audio, then play chunks in order."""

    def __init__(self, parent=None, label='TTS', on_started=None, on_idle=None):
        super().__init__(parent)
        self.label = label
        self.on_started = on_started
        self.on_idle = on_idle
        self.worker = None
        self.current_stream_id = None
        self.consumed = {}
        self.chunk_counts = {}
        self.final_streams = set()
        self.stopping_workers = []

    def is_active(self):
        return self.worker is not None

    def queue_text(self, stream_id, text, terminal=False):
        stream_id = stream_id or '__default__'
        text = (text or '').strip()
        if terminal:
            self.final_streams.add(stream_id)
        if not text:
            self._finish_if_needed(stream_id, terminal)
            return False
        if not self._enabled():
            self._maybe_emit_idle()
            return False

        consumed = int(self.consumed.get(stream_id, 0) or 0)
        if consumed > len(text):
            consumed = 0
        delta = text[consumed:]
        if not delta.strip():
            self._finish_if_needed(stream_id, terminal)
            return False

        queued = False
        while delta.strip():
            chunk_count = int(self.chunk_counts.get(stream_id, 0) or 0)
            cut = stream_tts_cut_index(delta, terminal=terminal, first_chunk=(chunk_count == 0))
            if cut <= 0:
                break

            chunk = delta[:cut].strip()
            consumed += cut
            self.consumed[stream_id] = consumed
            if not chunk:
                break

            self._ensure_worker(stream_id)
            is_terminal_chunk = terminal and consumed >= len(text)
            self.worker.enqueue(stream_id, chunk, terminal=is_terminal_chunk)
            self.chunk_counts[stream_id] = chunk_count + 1
            queued = True
            if not terminal:
                break
            delta = text[consumed:]

        if terminal and not delta.strip() and not queued:
            self._finish_if_needed(stream_id, terminal)
        return queued

    def reset(self, stream_id=None, stop_current=True):
        if stream_id is None:
            self.consumed.clear()
            self.chunk_counts.clear()
            self.final_streams.clear()
            if stop_current:
                self._stop_current()
            return
        self.consumed.pop(stream_id, None)
        self.chunk_counts.pop(stream_id, None)
        self.final_streams.discard(stream_id)
        if stop_current and self.current_stream_id == stream_id:
            self._stop_current()

    def _enabled(self):
        cfg = config.tts_config
        return bool(cfg.get('enabled') and cfg.get('api_key'))

    def _ensure_worker(self, stream_id):
        if self.worker is not None and self.current_stream_id != stream_id:
            self._stop_current()
        if self.worker is not None:
            return
        self.current_stream_id = stream_id
        self.worker = _PipelineTtsWorker(self.label, parent=self)
        self.worker.chunk_started.connect(self._on_chunk_started)
        self.worker.result_ready.connect(self._on_done)
        self.worker.start()

    def _finish_if_needed(self, stream_id, terminal):
        if terminal and self.worker is not None and self.current_stream_id == stream_id:
            self.worker.finish_stream(stream_id)
            return
        self._maybe_emit_idle()

    def _on_chunk_started(self, stream_id, text):
        if self.on_started:
            self.on_started(stream_id, text)

    def _on_done(self, success, text):
        if not success:
            print('%s failed: %s' % (self.label, text))
        self.worker = None
        self.current_stream_id = None
        self.final_streams.clear()
        if self.on_idle:
            self.on_idle()

    def _stop_current(self):
        worker = self.worker
        self.worker = None
        self.current_stream_id = None
        if worker is None:
            return
        try:
            worker.chunk_started.disconnect(self._on_chunk_started)
            worker.result_ready.disconnect(self._on_done)
        except (TypeError, RuntimeError):
            pass
        worker.stop()
        worker.wait(300)
        if worker.isRunning():
            self.stopping_workers.append(worker)
            worker.finished.connect(lambda w=worker: self._forget_stopping_worker(w))

    def _forget_stopping_worker(self, worker):
        if worker in self.stopping_workers:
            self.stopping_workers.remove(worker)

    def _maybe_emit_idle(self):
        if self.worker is not None or not self.final_streams:
            return
        self.final_streams.clear()
        if self.on_idle:
            self.on_idle()
