# coding:utf-8
"""回复卡片顶层窗口的公共交互和动画。"""

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame

from clients.tts_client import stop_tts
from widgets.notifications.constants import CARD_ANIM_IN_MS, CARD_ANIM_MOVE_MS, CARD_ANIM_OUT_MS, CARD_ENTER_OFFSET, CARD_EXIT_OFFSET


class ReplyCardWindow(QFrame):
    """带拖拽、右键打断和进出动画的透明置顶回复卡片窗口。"""

    closed = Signal(str)

    def __init__(self, card_id, parent=None, fade_in=False, initial_opacity=0.0):
        super().__init__(parent)
        self.card_id = card_id
        self.fade_in = fade_in
        self.anim_group = None
        self.closing = False
        self.closed_emitted = False
        self.dragging = False
        self.drag_start_pos = QPoint()
        self.drag_window_pos = QPoint()
        self.manual_position = False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(initial_opacity)

    def animate_in(self, end_pos):
        if self.anim_group is not None:
            self.anim_group.stop()
        self.move(end_pos + CARD_ENTER_OFFSET)
        self.show()
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
        self.anim_group.start()

    def request_close(self):
        if self.closing:
            return
        self.closing = True
        self._before_request_close()
        self._animate_out()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._interrupt()
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_start_pos = event.globalPos()
            self.drag_window_pos = self.pos()
            if self.anim_group is not None:
                self.anim_group.stop()
            timer = getattr(self, 'timer', None)
            if timer is not None:
                timer.stop()
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
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self.manual_position = True
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _interrupt(self):
        stop_tts()
        self.request_close()

    def _before_request_close(self):
        timer = getattr(self, 'timer', None)
        if timer is not None:
            timer.stop()

    def _before_close_event(self):
        pass

    def _animate_out(self):
        if self.anim_group is not None:
            self.anim_group.stop()
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(CARD_ANIM_OUT_MS)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(self.pos() + CARD_EXIT_OFFSET)
        pos_anim.setEasingCurve(QEasingCurve.InCubic)
        opacity_anim = QPropertyAnimation(self, b'windowOpacity', self)
        opacity_anim.setDuration(CARD_ANIM_OUT_MS)
        opacity_anim.setStartValue(self.windowOpacity())
        opacity_anim.setEndValue(0.0)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.addAnimation(opacity_anim)
        self.anim_group.finished.connect(self.close)
        self.anim_group.start()

    def closeEvent(self, event):
        self._before_close_event()
        if not self.closed_emitted:
            self.closed_emitted = True
            self.closed.emit(self.card_id)
        super().closeEvent(event)
