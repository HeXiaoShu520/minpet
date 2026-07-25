# coding:utf-8
from PySide6.QtCore import QTimer
import shiboken6


def _cfg():
    from miniPet import config
    return config.typewriter_config


class Typewriter:
    """逐字打印到任意 QLabel 或 QTextBrowser。
    set_text(full_text) — 立即替换（跳过打字）
    typewrite(text) — 打字机效果（受 config 控制）
    append_chunk(chunk) — 流式追加新 token
    """

    def __init__(self, widget, speed_ms=None):
        self._w = widget
        self._speed_override = speed_ms  # 若传入则覆盖 config
        self._target = ''
        self._shown = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)

    def _speed(self):
        if self._speed_override is not None:
            return self._speed_override
        return int(_cfg().get('speed_ms', 28))

    def _max_duration(self):
        return int(_cfg().get('max_duration_ms', 5000))

    def _enabled(self):
        return bool(_cfg().get('enabled', True))

    def _is_label(self):
        from PySide6.QtWidgets import QTextEdit
        return not isinstance(self._w, QTextEdit)

    def _set(self, text):
        if self._w is None or not shiboken6.isValid(self._w):
            self._timer.stop()
            return
        if self._is_label():
            self._w.setText(text)
        else:
            self._w.setHtml('<p style="margin:0">%s</p>' % text.replace('\n', '<br>'))

    def _calc_interval(self):
        remaining = len(self._target) - self._shown
        if remaining <= 0:
            return self._speed()
        ideal = self._max_duration() // max(remaining, 1)
        return max(8, min(self._speed(), ideal))

    def _tick(self):
        if self._shown >= len(self._target):
            self._timer.stop()
            return
        self._shown += 1
        self._set(self._target[:self._shown])
        self._timer.setInterval(self._calc_interval())

    def typewrite(self, text):
        self._timer.stop()
        self._target = text
        self._shown = 0
        if not self._enabled():
            self._set(text)
            self._shown = len(text)
            return
        self._timer.start(self._calc_interval())

    def append_chunk(self, chunk):
        self._target += chunk
        if not self._enabled():
            self._set(self._target)
            self._shown = len(self._target)
            return
        if not self._timer.isActive():
            self._timer.start(self._calc_interval())

    def set_text(self, text):
        self._timer.stop()
        self._target = text
        self._shown = len(text)
        self._set(text)
