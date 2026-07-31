# coding:utf-8
"""日常工作语音输入悬浮胶囊。"""

import math

from PySide6.QtCore import Property, QPropertyAnimation, QEasingCurve, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget


class DailyInputBar(QWidget):
    """屏幕底部居中的黑色圆角胶囊，显示语音输入状态和实时识别文字。"""

    _BAR_HEIGHT = 44
    _MIN_WIDTH = 160
    _MAX_WIDTH = 500
    _PADDING_H = 20
    _ICON_W = 28
    _SEP_W = 1
    _SEP_MARGIN = 10
    _WAVE_BARS = 3
    _WAVE_BAR_W = 3
    _WAVE_BAR_GAP = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText('')
        self._phase = 0
        self._blink = True
        self._listening = False

        flags = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                 Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedHeight(self._BAR_HEIGHT)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(50)
        self._anim_timer.timeout.connect(self._tick)

        self._width_anim = None
        self._current_width = self._MIN_WIDTH
        self._set_width(self._MIN_WIDTH, animated=False)

    def _set_width(self, w, animated=True):
        w = max(self._MIN_WIDTH, min(self._MAX_WIDTH, w))
        if abs(w - self._current_width) < 2:
            return
        self._current_width = w
        if animated and self._width_anim is None:
            self._width_anim = QPropertyAnimation(self, b'_bar_width', self)
            self._width_anim.setDuration(150)
            self._width_anim.setEasingCurve(QEasingCurve.OutCubic)
        if self._width_anim:
            self._width_anim.stop()
            self._width_anim.setStartValue(self.width())
            self._width_anim.setEndValue(w)
            self._width_anim.start()
        else:
            self.setFixedWidth(w)
            self._reposition()

    def _get_bar_width(self):
        return self.width()

    def _set_bar_width(self, w):
        self.setFixedWidth(int(w))
        self._reposition()

    _bar_width = Property(int, _get_bar_width, _set_bar_width)

    def setText(self, text):
        self._text = str(text or '').strip()
        if hasattr(self, '_anim_timer'):
            self._recalc_width()
            self.update()

    def reset(self):
        """每次开始录音前重置状态，宽度回到最小值。"""
        self._text = ''
        self._current_width = self._MIN_WIDTH
        if self._width_anim is not None:
            self._width_anim.stop()
        self.setFixedWidth(self._MIN_WIDTH)
        self.update()

    def _recalc_width(self):
        text_w = 0
        if self._text:
            fm = QFontMetrics(self.font())
            text_w = fm.horizontalAdvance(self._text)
        wave_w = self._WAVE_BARS * self._WAVE_BAR_W + (self._WAVE_BARS - 1) * self._WAVE_BAR_GAP
        total = (self._PADDING_H + self._ICON_W + self._SEP_MARGIN * 2 + self._SEP_W +
                 wave_w + (8 + text_w if self._text else 0) + self._PADDING_H)
        self._set_width(int(total))

    def show_listening(self):
        self._listening = True
        self._phase = 0
        self._reposition()
        self.show()
        self.raise_()
        self._anim_timer.start()

    def hide_bar(self):
        self._listening = False
        self._anim_timer.stop()
        self.hide()

    def update_text(self, text):
        # 只保留最后一段（最新的识别内容），截断过长文字
        text = str(text or '').strip()
        if len(text) > 40:
            text = '…' + text[-38:]
        self.setText(text)

    def _reposition(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + geo.height() - self.height() - 48
        self.move(x, y)

    def _tick(self):
        self._phase = (self._phase + 1) % 24
        self._blink = (self._phase % 12) < 8
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        r = h / 2

        # 胶囊背景
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), r, r)
        painter.fillPath(path, QColor(20, 20, 20, 225))

        # 麦克风图标（简单圆形 + 矩形）
        mic_cx = self._PADDING_H + self._ICON_W // 2
        cy = h / 2
        mic_color = QColor(255, 80, 80) if self._blink else QColor(220, 60, 60)
        painter.setPen(Qt.NoPen)
        painter.setBrush(mic_color)
        # 麦克风头
        painter.drawRoundedRect(QRectF(mic_cx - 5, cy - 10, 10, 14), 5, 5)
        # 麦克风支架弧线
        pen = QPen(mic_color, 2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        from PySide6.QtCore import QRectF as _QRectF
        painter.drawArc(_QRectF(mic_cx - 8, cy - 8, 16, 14), 0, -180 * 16)
        # 底座竖线
        painter.drawLine(int(mic_cx), int(cy + 6), int(mic_cx), int(cy + 10))
        # 底座横线
        painter.drawLine(int(mic_cx - 4), int(cy + 10), int(mic_cx + 4), int(cy + 10))

        # 分隔线
        sep_x = self._PADDING_H + self._ICON_W + self._SEP_MARGIN
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.drawLine(sep_x, 10, sep_x, h - 10)

        # 波形条
        wave_x = sep_x + self._SEP_MARGIN
        wave_heights = [8, 14, 8]
        for i in range(self._WAVE_BARS):
            if self._listening:
                t = (self._phase / 24.0 * 2 * math.pi) + i * 1.2
                bar_h = max(4, int(wave_heights[i] * (0.5 + 0.5 * math.sin(t))))
            else:
                bar_h = 4
            bx = wave_x + i * (self._WAVE_BAR_W + self._WAVE_BAR_GAP)
            by = cy - bar_h / 2
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 210))
            painter.drawRoundedRect(QRectF(bx, by, self._WAVE_BAR_W, bar_h), 1.5, 1.5)

        # 文字
        if self._text:
            text_x = (wave_x + self._WAVE_BARS * self._WAVE_BAR_W +
                      (self._WAVE_BARS - 1) * self._WAVE_BAR_GAP + 8)
            painter.setPen(QColor(255, 255, 255, 220))
            fm = QFontMetrics(self.font())
            text_y = int(cy + fm.ascent() / 2 - 1)
            painter.drawText(text_x, text_y, self._text)

        painter.end()
