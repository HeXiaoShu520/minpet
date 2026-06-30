# coding:utf-8
import uuid

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QPoint, QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)
from qfluentwidgets import BodyLabel, CaptionLabel, StrongBodyLabel, TextWrap, TransparentToolButton
from qfluentwidgets import FluentIcon as FIF

from miniPet.typewriter import Typewriter

from miniPet import config


class Toast(QWidget):
    closed = Signal(str)

    def __init__(self, note_id, title, message, icon=None, timeout=5000, parent=None):
        super().__init__(parent)
        self.note_id = note_id
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        frame = QFrame()
        frame.setStyleSheet('''
            QFrame { border: 1px solid #202020; border-radius: 6px; background: white; }
            QLabel { border: 0; background: transparent; color: black; }
        ''')
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        if icon and not icon.isNull():
            icon_label = QLabel()
            screen = QApplication.primaryScreen()
            dpr = screen.devicePixelRatio() if screen else 1.0
            pm = icon.scaled(int(28 * dpr), int(28 * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            icon_label.setPixmap(pm)
            layout.addWidget(icon_label)
        text_box = QVBoxLayout()
        title_label = StrongBodyLabel(title or 'miniPet')
        msg_label = CaptionLabel(message or '')
        msg_label.setWordWrap(True)
        msg_label.setMaximumWidth(260)
        text_box.addWidget(title_label)
        text_box.addWidget(msg_label)
        layout.addLayout(text_box, 1)
        close_btn = TransparentToolButton(FIF.CLOSE)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close)
        self.timer.start(timeout)
        self.adjustSize()

    def show_at(self, offset):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 24, screen.bottom() - self.height() - 24 - offset)
        self.show()

    def closeEvent(self, event):
        self.closed.emit(self.note_id)
        super().closeEvent(event)


class BubbleText(QFrame):
    closed = Signal(str)

    def __init__(self, bubble_id, message, x, y, timeout=6000, parent=None, title='miniPet'):
        super().__init__(parent)
        self.bubble_id = bubble_id
        self.anim_group = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(0.0)
        self.setStyleSheet('''
            QFrame#BubbleCard {
                border: 1px solid rgba(210, 216, 226, 210);
                border-radius: 14px;
                background: rgba(255, 255, 255, 245);
            }
            QLabel { border: 0; background: transparent; color: #1f2328; font-family: "Microsoft YaHei"; }
            QLabel#BubbleTitle { color: #68707d; font-size: 12px; font-weight: 600; }
            QLabel#BubbleMessage { color: #1f2328; font-size: 14px; }
            QLabel#BubbleAvatar { border-radius: 16px; background: #e8f2ff; }
        ''')
        card = QFrame(self)
        card.setObjectName('BubbleCard')
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        avatar = QLabel(card)
        avatar.setObjectName('BubbleAvatar')
        avatar.setFixedSize(32, 32)
        avatar.setAlignment(Qt.AlignCenter)
        icon = QPixmap(str(config.avatar_path('pet')))
        if not icon.isNull():
            screen = QApplication.primaryScreen()
            dpr = screen.devicePixelRatio() if screen else 1.0
            pm = icon.scaled(int(24 * dpr), int(24 * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            avatar.setPixmap(pm)
        else:
            avatar.setText('宠')
        layout.addWidget(avatar, 0, Qt.AlignTop)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(3)
        title_label = QLabel(title or 'miniPet', card)
        title_label.setObjectName('BubbleTitle')
        msg_label = QLabel('', card)
        msg_label.setObjectName('BubbleMessage')
        msg_label.setWordWrap(True)
        msg_label.setMaximumWidth(320)
        text_box.addWidget(title_label)
        text_box.addWidget(msg_label)
        layout.addLayout(text_box, 1)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        wrapped = TextWrap.wrap(message or '', 30, False)[0]
        msg_label.setText(wrapped)
        self.adjustSize()
        msg_label.clear()
        end_pos = QPoint(int(x - self.width() / 2), int(y - self.height() - 18))
        self.move(end_pos + QPoint(0, 14))
        self._animate_in(end_pos)
        self._tw = Typewriter(msg_label)
        tts_on = config.tts_config.get('enabled') and config.tts_config.get('api_key')
        delay = int(config.typewriter_config.get('tts_delay_ms', 500)) if tts_on else 0
        if delay > 0:
            QTimer.singleShot(delay, lambda: self._tw.typewrite(wrapped))
        else:
            self._tw.typewrite(wrapped)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._animate_out)
        self.timer.start(timeout)

    def _animate_in(self, end_pos):
        self.show()
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(220)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        opacity_anim = QPropertyAnimation(self, b'windowOpacity', self)
        opacity_anim.setDuration(180)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.addAnimation(opacity_anim)
        self.anim_group.start()

    def _animate_out(self):
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(180)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(self.pos() + QPoint(0, -10))
        pos_anim.setEasingCurve(QEasingCurve.InCubic)
        opacity_anim = QPropertyAnimation(self, b'windowOpacity', self)
        opacity_anim.setDuration(180)
        opacity_anim.setStartValue(self.windowOpacity())
        opacity_anim.setEndValue(0.0)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.addAnimation(opacity_anim)
        self.anim_group.finished.connect(self.close)
        self.anim_group.start()

    def closeEvent(self, event):
        self.closed.emit(self.bubble_id)
        super().closeEvent(event)


class SmartBubble(QFrame):
    action_clicked = Signal(dict, dict)
    closed = Signal(str)

    def __init__(self, bubble_id, event, x, y, parent=None):
        super().__init__(parent)
        self.bubble_id = bubble_id
        self.event = dict(event)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet('''
            QFrame { border: 1px solid #202020; border-radius: 8px; background: white; }
            QLabel, QPushButton { border: 0; background: transparent; color: black; font: 13px "Microsoft YaHei"; }
            QPushButton { border: 1px solid #c8c8c8; border-radius: 4px; padding: 4px 8px; }
            QPushButton:hover { background: #f0f0f0; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        title = StrongBodyLabel(event.get('title') or event.get('sender') or '外部事件')
        summary = BodyLabel(event.get('summary') or event.get('content') or event.get('message') or '')
        summary.setWordWrap(True)
        summary.setMaximumWidth(300)
        layout.addWidget(title)
        layout.addWidget(summary)
        suggestion = event.get('suggestion')
        if suggestion:
            tip = CaptionLabel(suggestion)
            tip.setWordWrap(True)
            tip.setMaximumWidth(300)
            layout.addWidget(tip)
        actions = event.get('actions') or [{'id': 'ignore', 'label': '忽略'}]
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        for action in actions[:4]:
            btn = QPushButton(action.get('label') or action.get('id') or '操作')
            btn.clicked.connect(lambda checked=False, a=action: self._click_action(a))
            action_row.addWidget(btn)
        layout.addLayout(action_row)
        self.adjustSize()
        self.move(int(x - self.width() / 2), int(y - self.height() - 16))

    def _click_action(self, action):
        self.action_clicked.emit(self.event, action)
        self.close()

    def closeEvent(self, event):
        self.closed.emit(self.bubble_id)
        super().closeEvent(event)


class NotificationCenter(QWidget):
    smart_action_clicked = Signal(dict, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.toasts = {}
        self.bubbles = {}
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
        bubble = BubbleText(bubble_id, message, x, y, timeout, title=title)
        bubble.closed.connect(self._remove_bubble)
        self.bubbles[bubble_id] = bubble
        return bubble_id

    def close_bubble(self, bubble_id):
        bubble = self.bubbles.pop(bubble_id, None)
        if bubble is not None:
            bubble.close()

    def setup_smart_bubble(self, event, x, y):
        bubble_id = str(uuid.uuid4())
        bubble = SmartBubble(bubble_id, event, x, y)
        bubble.action_clicked.connect(self.smart_action_clicked)
        bubble.closed.connect(self._remove_bubble)
        self.bubbles[bubble_id] = bubble
        bubble.show()
        self._play_sound()

    def _remove_toast(self, note_id):
        self.toasts.pop(note_id, None)

    def _remove_bubble(self, bubble_id):
        self.bubbles.pop(bubble_id, None)

    def _play_sound(self):
        sound = config.RES_DIR / 'sounds' / 'Notification.wav'
        if not sound.exists():
            return
        self.audio_output.setVolume(float(config.app_config.get('volume', 0.4)))
        self.audio.setSource(QUrl.fromLocalFile(str(sound)))
        self.audio.play()
