# coding:utf-8
"""通知管理器。"""

import uuid

from PySide6.QtCore import QPoint, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QApplication, QWidget

import config
from widgets.notifications.constants import CARD_BASE_GAP, CARD_STACK_GAP, MAX_STACKED_REPLY_CARDS, REPLY_CARD_TIMEOUT_MS
from widgets.notifications.reply_card import ReplyCard
from widgets.notifications.toast import Toast


class ReplyCardCenter(QWidget):
    """回复卡片管理器，负责创建、堆叠、移动和关闭短生命周期卡片。"""

    reply_card_action_clicked = Signal(dict, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.toasts = {}
        self.reply_cards = {}
        self.reply_card_order = []
        self.reply_card_anchor = None
        self.audio = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio.setAudioOutput(self.audio_output)

    def setup_toast(self, title, message='', icon_path=None):
        note_id = str(uuid.uuid4())
        icon = QPixmap(icon_path) if icon_path else QPixmap(str(config.avatar_path('pet')))
        toast = Toast(note_id, title, message, icon)
        toast.closed.connect(self._remove_toast)
        offset = sum(t.height() + 10 for t in self.toasts.values())
        self.toasts[note_id] = toast
        toast.show_at(offset)
        self._play_sound()

    def setup_reply_card_text(self, message, x, y, timeout=6000, title=None):
        title = title or config.APP_DISPLAY_NAME
        card_id = str(uuid.uuid4())
        card = ReplyCard(card_id, {
            'type': 'surface.show',
            'content': message,
            'title': title,
            'avatar_kind': 'user' if title == '你' else 'pet',
            'status': 'done',
        }, timeout)
        card.closed.connect(self._remove_reply_card)
        self._register_reply_card(card_id, card, x, y)
        return card_id

    def close_reply_card(self, card_id):
        card = self.reply_cards.get(card_id)
        if card is not None:
            card.request_close()

    def update_reply_card(self, card_id, message, timeout=None):
        card = self.reply_cards.get(card_id)
        if card is None:
            return False
        old_size = card.size()
        if isinstance(message, dict) and hasattr(card, 'update_card'):
            card.update_card(message, timeout=timeout)
        elif hasattr(card, 'update_message'):
            card.update_message(message, timeout=timeout)
        else:
            return False
        if card.size() != old_size:
            self._reflow_reply_cards(animate=True)
        return True

    def setup_reply_card(self, event, x, y, play_sound=True):
        card_id = str(uuid.uuid4())
        timeout = int(event.get('timeout_ms', REPLY_CARD_TIMEOUT_MS) or 0)
        card = ReplyCard(card_id, event, timeout)
        card.action_clicked.connect(self.reply_card_action_clicked)
        card.closed.connect(self._remove_reply_card)
        self._register_reply_card(card_id, card, x, y)
        if play_sound:
            self._play_sound()
        return card_id

    def _register_reply_card(self, card_id, card, x, y):
        self.reply_card_anchor = QPoint(int(x), int(y))
        self.reply_cards[card_id] = card
        self.reply_card_order.append(card_id)
        target = self._reply_card_target_pos(card, 0, self.reply_card_anchor)
        self._trim_reply_cards()
        self._reflow_reply_cards(animate=True, skip_id=card_id)
        card.animate_in(target)

    def _reply_card_target_pos(self, card, stack_index, anchor):
        x = int(anchor.x() - card.width() / 2)
        y = int(anchor.y() - card.height() - CARD_BASE_GAP)
        return self._clamp_to_anchor_screen(QPoint(x, y - stack_index * (card.height() + CARD_STACK_GAP)), card, anchor)

    def _clamp_to_anchor_screen(self, pos, widget, anchor, margin=4):
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        if screen is None:
            return pos
        area = screen.availableGeometry()
        x = max(area.left() + margin, min(pos.x(), area.right() - widget.width() - margin))
        y = max(area.top() + margin, min(pos.y(), area.bottom() - widget.height() - margin))
        return QPoint(x, y)

    def _active_reply_card_ids(self):
        self.reply_card_order = [cid for cid in self.reply_card_order if cid in self.reply_cards]
        return [cid for cid in self.reply_card_order if not getattr(self.reply_cards[cid], 'closing', False)]

    def _trim_reply_cards(self):
        active_ids = self._active_reply_card_ids()
        overflow = len(active_ids) - MAX_STACKED_REPLY_CARDS
        if overflow <= 0:
            return
        for card_id in active_ids[:overflow]:
            card = self.reply_cards.get(card_id)
            if card is not None:
                card.request_close()

    def _reflow_reply_cards(self, animate=True, skip_id=None):
        if self.reply_card_anchor is None:
            return
        active_ids = self._active_reply_card_ids()
        for stack_index, card_id in enumerate(reversed(active_ids)):
            if card_id == skip_id:
                continue
            card = self.reply_cards[card_id]
            if getattr(card, 'manual_position', False):
                continue
            target = self._reply_card_target_pos(card, stack_index, self.reply_card_anchor)
            if animate:
                card.animate_to(target)
            else:
                card.move(target)

    def _remove_toast(self, note_id):
        self.toasts.pop(note_id, None)

    def _remove_reply_card(self, card_id):
        self.reply_cards.pop(card_id, None)
        self.reply_card_order = [cid for cid in self.reply_card_order if cid != card_id]
        self._reflow_reply_cards(animate=True)

    def _play_sound(self):
        sound = config.RES_DIR / 'sounds' / 'Notification.wav'
        if not sound.exists():
            return
        self.audio_output.setVolume(float(config.app_config.get('volume', 0.4)))
        self.audio.setSource(QUrl.fromLocalFile(str(sound)))
        self.audio.play()
