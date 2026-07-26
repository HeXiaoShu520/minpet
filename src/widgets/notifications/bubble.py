# coding:utf-8
"""宠物头顶普通对话气泡。"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout

import config
from typewriter import Typewriter
from widgets.notifications.text_format import markdown_to_html
from widgets.notifications.window_base import NotificationBubbleWindow


def _bubble_style_qss(style):
    styles = {
        'glass': ('rgba(255,255,255,225)', 'rgba(255,255,255,210)', '#5f6675', '#1f2328', '#eef6ff'),
        'pink': ('rgba(255,246,249,250)', 'rgba(255,190,210,235)', '#9b5870', '#2b2026', '#fff0f5'),
        'mint': ('rgba(242,255,251,250)', 'rgba(160,225,210,235)', '#52756e', '#1f2b29', '#e8fbf5'),
        'night': ('rgba(38,43,58,245)', 'rgba(95,108,145,235)', '#b8c2dd', '#f2f5ff', '#323a52'),
        'soft': ('rgba(255,255,255,255)', 'rgba(210,216,226,255)', '#68707d', '#1f2328', '#fff1f0'),
    }
    bg, border, title, text, hover = styles.get(style, styles['soft'])
    return f'''
            QFrame#BubbleCard {{ border: 1px solid {border}; border-radius: 16px; background: {bg}; }}
            QLabel {{ border: 0; background: transparent; color: {text}; font-family: "Microsoft YaHei"; }}
            QLabel#BubbleTitle {{ color: {title}; font-size: 12px; font-weight: 600; }}
            QLabel#BubbleMessage {{ color: {text}; font-size: 14px; }}
            QLabel#BubbleAvatar {{ border-radius: 16px; background: #e8f2ff; }}
            QPushButton#BubbleClose {{ border: none; border-radius: 12px; background: transparent; color: #8b8f99; padding: 3px; }}
            QPushButton#BubbleClose:hover {{ background: {hover}; color: #ff3b30; }}
        '''


class BubbleText(NotificationBubbleWindow):
    """宠物头顶普通对话气泡，支持 Markdown 文本和头像。"""

    def __init__(self, bubble_id, message, timeout=6000, parent=None, title='miniPet'):
        super().__init__(bubble_id, parent, fade_in=False, initial_opacity=1.0)
        self.setStyleSheet(_bubble_style_qss(config.app_config.get('bubble_style', 'soft')))
        card = QFrame(self)
        card.setObjectName('BubbleCard')
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 18, 10)
        layout.setSpacing(10)

        avatar = QLabel(card)
        avatar.setObjectName('BubbleAvatar')
        avatar.setFixedSize(32, 32)
        avatar.setAlignment(Qt.AlignCenter)
        avatar_kind = 'user' if (title or '') == '你' else 'pet'
        icon = QPixmap(str(config.avatar_path(avatar_kind)))
        if not icon.isNull():
            screen = QApplication.primaryScreen()
            dpr = screen.devicePixelRatio() if screen else 1.0
            pm = icon.scaled(int(24 * dpr), int(24 * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            avatar.setPixmap(pm)
        else:
            avatar.setText('你' if avatar_kind == 'user' else '宠')
        layout.addWidget(avatar, 0, Qt.AlignTop)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(3)
        title_label = QLabel(title or 'miniPet', card)
        title_label.setObjectName('BubbleTitle')
        msg_label = QLabel('', card)
        msg_label.setObjectName('BubbleMessage')
        msg_label.setTextFormat(Qt.RichText)  # 启用富文本模式
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        msg_label.setMinimumWidth(180)
        # 根据内容长度适度调整宽度，避免过宽
        content_length = len(message or '')
        if content_length < 30:
            max_width = 260
        elif content_length < 80:
            max_width = 320
        else:
            max_width = 360  # 长内容也不要太宽，保持合理宽度让文字换行
        msg_label.setMaximumWidth(max_width)
        text_box.addWidget(title_label)
        text_box.addWidget(msg_label, 0, Qt.AlignTop)
        text_box.setAlignment(Qt.AlignTop)
        layout.addLayout(text_box, 1)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        wrapped = message or ''
        # 先转换为HTML并计算窗口大小
        html_text = markdown_to_html(wrapped)
        msg_label.setText(html_text)
        self.adjustSize()
        msg_label.clear()
        # 然后使用打字机效果显示
        self._tw = Typewriter(msg_label)
        tts_on = config.tts_config.get('enabled') and config.tts_config.get('api_key')
        delay = int(config.typewriter_config.get('tts_delay_ms', 500)) if tts_on else 0
        if delay > 0:
            QTimer.singleShot(delay, lambda: self._tw.typewrite(html_text))
        else:
            self._tw.typewrite(html_text)
        self.message_label = msg_label
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.request_close)
        self.timer.start(timeout)

    def update_message(self, message, timeout=None):
        """更新气泡文本，用于流式输出。"""
        if self.closing:
            return
        if hasattr(self, '_tw'):
            self._tw.set_text(markdown_to_html(message or ''))
        else:
            self.message_label.setText(markdown_to_html(message or ''))
        self.adjustSize()
        if timeout is not None:
            self.timer.start(int(timeout))


