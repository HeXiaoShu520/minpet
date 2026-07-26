# coding:utf-8
"""通知管理器。"""

import uuid

from PySide6.QtCore import QPoint, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QApplication, QWidget

import config
from widgets.notifications.bubble import BubbleText
from widgets.notifications.constants import BUBBLE_BASE_GAP, BUBBLE_STACK_GAP, MAX_STACKED_BUBBLES, SMART_BUBBLE_TIMEOUT_MS
from widgets.notifications.smart_bubble import SmartBubble
from widgets.notifications.toast import Toast


class NotificationCenter(QWidget):
    """通知管理器，负责创建、堆叠、移动和关闭所有短生命周期提示窗口。"""

    smart_action_clicked = Signal(dict, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.toasts = {}
        self.bubbles = {}
        self.bubble_order = []
        self.bubble_anchor = None
        self.audio = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio.setAudioOutput(self.audio_output)

    def setup_notification(self, title, message='', icon_path=None):
        note_id = str(uuid.uuid4())
        icon = QPixmap(icon_path) if icon_path else QPixmap(str(config.avatar_path('pet')))
        toast = Toast(note_id, title, message, icon)
        toast.closed.connect(self._remove_toast)
        offset = sum(t.height() + 10 for t in self.toasts.values())
        self.toasts[note_id] = toast
        toast.show_at(offset)
        self._play_sound()

    def setup_bubble(self, message, x, y, timeout=6000, title='miniPet'):
        bubble_id = str(uuid.uuid4())
        bubble = BubbleText(bubble_id, message, timeout, title=title)
        bubble.closed.connect(self._remove_bubble)
        self._register_bubble(bubble_id, bubble, x, y)
        return bubble_id

    def close_bubble(self, bubble_id):
        bubble = self.bubbles.get(bubble_id)
        if bubble is not None:
            bubble.request_close()

    def update_bubble(self, bubble_id, message, timeout=None):
        bubble = self.bubbles.get(bubble_id)
        if bubble is None:
            return False
        old_size = bubble.size()
        if isinstance(message, dict) and hasattr(bubble, 'update_card'):
            bubble.update_card(message, timeout=timeout)
        elif hasattr(bubble, 'update_message'):
            bubble.update_message(message, timeout=timeout)
        else:
            return False
        if bubble.size() != old_size:
            self._reflow_bubbles(animate=True)
        return True

    def setup_smart_bubble(self, event, x, y, play_sound=True):
        bubble_id = str(uuid.uuid4())
        timeout = int(event.get('timeout_ms', SMART_BUBBLE_TIMEOUT_MS) or 0)
        bubble = SmartBubble(bubble_id, event, timeout)
        bubble.action_clicked.connect(self.smart_action_clicked)
        bubble.closed.connect(self._remove_bubble)
        self._register_bubble(bubble_id, bubble, x, y)
        if play_sound:
            self._play_sound()
        return bubble_id

    def _register_bubble(self, bubble_id, bubble, x, y):
        self.bubble_anchor = QPoint(int(x), int(y))
        self.bubbles[bubble_id] = bubble
        self.bubble_order.append(bubble_id)
        target = self._bubble_target_pos(bubble, 0, self.bubble_anchor)
        self._trim_bubbles()
        self._reflow_bubbles(animate=True, skip_id=bubble_id)
        bubble.animate_in(target)

    def _bubble_target_pos(self, bubble, stack_index, anchor):
        x = int(anchor.x() - bubble.width() / 2)
        y = int(anchor.y() - bubble.height() - BUBBLE_BASE_GAP)
        return self._clamp_to_anchor_screen(QPoint(x, y - stack_index * (bubble.height() + BUBBLE_STACK_GAP)), bubble, anchor)

    def _clamp_to_anchor_screen(self, pos, widget, anchor, margin=4):
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        if screen is None:
            return pos
        area = screen.availableGeometry()
        x = max(area.left() + margin, min(pos.x(), area.right() - widget.width() - margin))
        y = max(area.top() + margin, min(pos.y(), area.bottom() - widget.height() - margin))
        return QPoint(x, y)

    def _active_bubble_ids(self):
        self.bubble_order = [bid for bid in self.bubble_order if bid in self.bubbles]
        return [bid for bid in self.bubble_order if not getattr(self.bubbles[bid], 'closing', False)]

    def _trim_bubbles(self):
        active_ids = self._active_bubble_ids()
        overflow = len(active_ids) - MAX_STACKED_BUBBLES
        if overflow <= 0:
            return
        for bubble_id in active_ids[:overflow]:
            bubble = self.bubbles.get(bubble_id)
            if bubble is not None:
                bubble.request_close()

    def _reflow_bubbles(self, animate=True, skip_id=None):
        if self.bubble_anchor is None:
            return
        active_ids = self._active_bubble_ids()
        for stack_index, bubble_id in enumerate(reversed(active_ids)):
            if bubble_id == skip_id:
                continue
            bubble = self.bubbles[bubble_id]
            if getattr(bubble, 'manual_position', False):
                continue
            target = self._bubble_target_pos(bubble, stack_index, self.bubble_anchor)
            if animate:
                bubble.animate_to(target)
            else:
                bubble.move(target)

    def _remove_toast(self, note_id):
        self.toasts.pop(note_id, None)

    def _remove_bubble(self, bubble_id):
        self.bubbles.pop(bubble_id, None)
        self.bubble_order = [bid for bid in self.bubble_order if bid != bubble_id]
        self._reflow_bubbles(animate=True)

    def _play_sound(self):
        sound = config.RES_DIR / 'sounds' / 'Notification.wav'
        if not sound.exists():
            return
        self.audio_output.setVolume(float(config.app_config.get('volume', 0.4)))
        self.audio.setSource(QUrl.fromLocalFile(str(sound)))
        self.audio.play()
