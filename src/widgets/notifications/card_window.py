# coding:utf-8
"""回复卡片顶层窗口的公共交互和动画。"""

import ctypes
import sys

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame

from clients.tts_client import stop_tts
from widgets.notifications.constants import CARD_ANIM_IN_MS, CARD_ANIM_MOVE_MS, CARD_ANIM_OUT_MS, CARD_ENTER_OFFSET, CARD_EXIT_OFFSET


class ReplyCardWindow(QFrame):
    """带拖拽、右键打断和进出动画的透明置顶回复卡片窗口。"""

    closed = Signal(str)
    interrupted = Signal(str)

    def __init__(self, card_id, parent=None, fade_in=False, initial_opacity=0.0):
        super().__init__(parent)
        self.card_id = card_id
        self.fade_in = fade_in
        self.anim_group = None
        self.closing = False
        self.closed_emitted = False
        self.dragging = False
        self.drag_moved = False
        self.drag_start_pos = QPoint()
        self.drag_window_pos = QPoint()
        self.manual_position = False
        self._last_left_click_time = 0.0
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(initial_opacity)

    def _ensure_topmost(self):
        try:
            self.raise_()
        except RuntimeError:
            return
        if sys.platform != 'win32':
            return
        try:
            hwnd = int(self.winId())
            flags = 0x0001 | 0x0002 | 0x0010 | 0x0040  # NOMOVE | NOSIZE | NOACTIVATE | SHOWWINDOW
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)
        except Exception:
            pass

    def _refresh_topmost_soon(self):
        self._ensure_topmost()
        for delay in (0, 60, 180, 360):
            QTimer.singleShot(delay, self._ensure_topmost)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_topmost_soon()

    def animate_in(self, end_pos):
        if self.anim_group is not None:
            self.anim_group.stop()
        self.move(end_pos + CARD_ENTER_OFFSET)
        self.show()
        self._refresh_topmost_soon()
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(CARD_ANIM_IN_MS)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        if self.fade_in:
            opacity_anim = QPropertyAnimation(self, b'windowOpacity', self)
            opacity_anim.setDuration(CARD_ANIM_IN_MS)
            opacity_anim.setStartValue(0.0)
            opacity_anim.setEndValue(1.0)
            self.anim_group.addAnimation(opacity_anim)
        else:
            self.setWindowOpacity(1.0)
        self.anim_group.finished.connect(self._refresh_topmost_soon)
        self.anim_group.start()

    def animate_to(self, end_pos):
        if self.closing:
            return
        if self.anim_group is not None:
            self.anim_group.stop()
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(CARD_ANIM_MOVE_MS)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.finished.connect(self._refresh_topmost_soon)
        self.anim_group.start()

    def request_close(self):
        if self.closing:
            return
        self.closing = True
        self._before_request_close()
        self._animate_out()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            now = __import__('time').time()
            if now - getattr(self, '_last_right_click_time', 0) < 0.4:
                self._interrupt()
                self._last_right_click_time = 0
            else:
                self._last_right_click_time = now
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            now = __import__('time').time()
            if not self.dragging and (now - self._last_left_click_time) < 0.35:
                self._last_left_click_time = 0.0
                self._on_double_click()
                event.accept()
                return
            self._last_left_click_time = now
            self.dragging = True
            self.drag_moved = False
            self.drag_start_pos = event.globalPos()
            self.drag_window_pos = self.pos()
            if self.anim_group is not None:
                self.anim_group.stop()
            self._ensure_topmost()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            if (event.globalPos() - self.drag_start_pos).manhattanLength() >= 4:
                self.drag_moved = True
            self.move(self.drag_window_pos + event.globalPos() - self.drag_start_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            if self.drag_moved:
                self.manual_position = True
                self._on_manual_positioned()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _interrupt(self):
        stop_tts()
        self.interrupted.emit(self.card_id)
        self.request_close()

    def _before_request_close(self):
        timer = getattr(self, 'timer', None)
        if timer is not None:
            timer.stop()

    def _before_close_event(self):
        pass

    def _on_manual_positioned(self):
        pass

    def _on_double_click(self):
        pass

    def _animate_out(self):
        if self.anim_group is not None:
            self.anim_group.stop()
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(CARD_ANIM_OUT_MS)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(self.pos() + CARD_EXIT_OFFSET)
        pos_anim.setEasingCurve(QEasingCurve.InCubic)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.finished.connect(self.close)
        self.anim_group.start()

    def closeEvent(self, event):
        self._before_close_event()
        if not self.closed_emitted:
            self.closed_emitted = True
            self.closed.emit(self.card_id)
        super().closeEvent(event)
