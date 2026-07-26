# coding:utf-8
import math
import random
import struct
import time
import wave

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import QApplication, QFrame

import config


EASTER_POPUP_GAP = 16


def easter_popup_pos(x, y, size, gap=EASTER_POPUP_GAP):
    screen = QApplication.screenAt(QPoint(int(x), int(y))) or QApplication.primaryScreen()
    pos = QPoint(int(x - size.width() / 2), int(y - size.height() - gap))
    if screen is not None:
        area = screen.availableGeometry()
        pos.setX(max(area.left() + 4, min(pos.x(), area.right() - size.width() - 4)))
        pos.setY(max(area.top() + 4, min(pos.y(), area.bottom() - size.height() - 4)))
    return pos


class EasterGamePopup(QFrame):
    title = '小游戏'
    life_ms = 9000
    _sound_cache = {}

    def __init__(self, x, y, parent=None):
        super().__init__(parent)
        self.started_at = time.monotonic()
        self.dragging = False
        self.drag_start_pos = QPoint()
        self.drag_window_pos = QPoint()
        self.anchor_x = int(x)
        self.anchor_y = int(y)
        self.fade_anim = None
        self.played_sounds = set()
        self.sound_effects = {}
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(280, 260)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(16)
        self.life_timer = QTimer(self)
        self.life_timer.setSingleShot(True)
        self.life_timer.timeout.connect(self.close)
        # 彩蛋小铺的小游戏由用户右键关闭，不自动消失。
        self.move_to_anchor(x, y)
        self.show()
        self.raise_()
        self._fade_in()

    def move_to_anchor(self, x, y):
        self.anchor_x = int(x)
        self.anchor_y = int(y)
        self.move(easter_popup_pos(x, y, self.size()))

    def _fade_in(self):
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b'windowOpacity', self)
        anim.setDuration(160)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self.fade_anim = anim

    def _tick(self):
        self.update()

    def _play_once(self, key, kind):
        if key in self.played_sounds:
            return
        self.played_sounds.add(key)
        self._play_sound(kind)

    def _play_sound(self, kind):
        path = self._ensure_sound(kind)
        if path is None:
            return
        effect = QSoundEffect(self)
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.setVolume(float(config.app_config.get('volume', 0.4)))
        effect.play()
        self.sound_effects[kind + str(time.monotonic())] = effect

    def _ensure_sound(self, kind):
        if kind in self._sound_cache:
            return self._sound_cache[kind]
        sound_dir = config.RES_DIR / 'sounds' / 'easter'
        sound_dir.mkdir(parents=True, exist_ok=True)
        path = sound_dir / f'{kind}.wav'
        if not path.is_file():
            self._write_sound(path, kind)
        self._sound_cache[kind] = path
        return path

    def _write_sound(self, path, kind):
        sample_rate = 44100
        duration = {
            'click': 0.08, 'tick': 0.05, 'drop': 0.16, 'open': 0.32,
            'coin': 0.55, 'dice': 0.42, 'mystic': 0.8,
        }.get(kind, 0.18)
        total = int(sample_rate * duration)
        frames = bytearray()
        for i in range(total):
            t = i / sample_rate
            if kind == 'coin':
                env = math.exp(-4.0 * t)
                freq = 1050 + 800 * math.sin(t * 48)
                sample = math.sin(2 * math.pi * freq * t) * env * 0.33
            elif kind == 'dice':
                env = math.exp(-7.0 * t)
                noise = random.uniform(-1, 1) * env * 0.22
                sample = noise + math.sin(2 * math.pi * 140 * t) * env * 0.18
            elif kind == 'drop':
                env = math.exp(-16 * t)
                sample = (math.sin(2 * math.pi * 150 * t) + random.uniform(-0.5, 0.5)) * env * 0.32
            elif kind == 'open':
                env = math.exp(-5 * t)
                sample = (math.sin(2 * math.pi * 660 * t) + 0.5 * math.sin(2 * math.pi * 990 * t)) * env * 0.24
            elif kind == 'mystic':
                env = min(1.0, t * 5) * math.exp(-1.4 * t)
                sample = (math.sin(2 * math.pi * 330 * t) + 0.45 * math.sin(2 * math.pi * 495 * t)) * env * 0.20
            elif kind == 'tick':
                env = math.exp(-80 * t)
                sample = math.sin(2 * math.pi * 1800 * t) * env * 0.36
            else:
                env = math.exp(-55 * t)
                sample = math.sin(2 * math.pi * 900 * t) * env * 0.34
            frames.extend(struct.pack('<h', int(max(-1, min(1, sample)) * 32767)))
        with wave.open(str(path), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(bytes(frames))

    def _elapsed(self):
        return time.monotonic() - self.started_at

    def _ease_out(self, t):
        t = max(0.0, min(1.0, t))
        return 1 - pow(1 - t, 3)

    def _ease_in_out(self, t):
        t = max(0.0, min(1.0, t))
        return t * t * (3 - 2 * t)

    def _spring(self, t, damping=5.5, frequency=13.0):
        t = max(0.0, t)
        return math.exp(-damping * t) * math.cos(frequency * t)

    def _impact(self, t, duration=0.32):
        if t < 0 or t > duration:
            return 0.0
        p = t / duration
        return math.sin(p * math.pi) * math.exp(-3.0 * p)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.close()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self.childAt(event.pos()) is None:
            self.dragging = True
            self.drag_start_pos = event.globalPos()
            self.drag_window_pos = self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            self.move(self.drag_window_pos + event.globalPos() - self.drag_start_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.dragging:
            self.move(easter_popup_pos(self.anchor_x, self.anchor_y, self.size()))

    def _draw_card(self, painter, bg=QColor(255, 250, 238, 246), border=QColor(225, 205, 165, 230)):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(80, 54, 24, 35))
        painter.drawRoundedRect(18, 20, self.width() - 36, self.height() - 30, 22, 22)
        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.5))
        painter.drawRoundedRect(14, 14, self.width() - 28, self.height() - 32, 22, 22)
        painter.setFont(QFont('Microsoft YaHei UI', 13, QFont.Bold))
        painter.setPen(QColor(92, 59, 24, 230))
        painter.drawText(0, 26, self.width(), 26, Qt.AlignCenter, self.title)

    def closeEvent(self, event):
        self.anim_timer.stop()
        self.life_timer.stop()
        super().closeEvent(event)
