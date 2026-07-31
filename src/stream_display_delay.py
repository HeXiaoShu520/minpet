# coding:utf-8
"""Delay streamed UI updates by a fixed offset while preserving order."""

import math
import time

from PySide6.QtCore import QObject, QTimer

try:
    import config
except ModuleNotFoundError:
    from src import config


class StreamDisplayDelay(QObject):
    """Schedule UI callbacks independently for each streamed reply lane."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lanes = {}
        self._timers = {}
        self._generations = {}

    def enqueue(self, lane_id, callback):
        lane_id = str(lane_id or '__default__')
        delay_ms = self._delay_ms()
        if delay_ms <= 0:
            callback()
            return
        due_at = time.monotonic() + delay_ms / 1000.0
        self._lanes.setdefault(lane_id, []).append((due_at, callback))
        self._schedule(lane_id)

    def reset(self, lane_id=None):
        if lane_id is None:
            lane_ids = set(self._lanes) | set(self._timers) | set(self._generations)
        else:
            lane_ids = {str(lane_id or '__default__')}
        for current_lane in lane_ids:
            self._generations[current_lane] = self._generations.get(current_lane, 0) + 1
            self._lanes.pop(current_lane, None)
            timer = self._timers.pop(current_lane, None)
            if timer is not None:
                timer.stop()
                timer.deleteLater()

    @staticmethod
    def _delay_ms():
        if not (config.tts_config.get('enabled') and config.tts_config.get('api_key')):
            return 0
        return max(0, int(config.typewriter_config.get('tts_delay_ms') or 0))

    def _schedule(self, lane_id):
        if lane_id in self._timers:
            return
        items = self._lanes.get(lane_id)
        if not items:
            return
        generation = self._generations.get(lane_id, 0)
        wait_ms = max(0, math.ceil((items[0][0] - time.monotonic()) * 1000))
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda lane=lane_id, token=generation: self._run_next(lane, token))
        self._timers[lane_id] = timer
        timer.start(wait_ms)

    def _run_next(self, lane_id, generation):
        timer = self._timers.pop(lane_id, None)
        if timer is not None:
            timer.deleteLater()
        if generation != self._generations.get(lane_id, 0):
            return
        items = self._lanes.get(lane_id)
        if not items:
            return
        _due_at, callback = items.pop(0)
        if not items:
            self._lanes.pop(lane_id, None)
        callback()
        if generation == self._generations.get(lane_id, 0):
            self._schedule(lane_id)
