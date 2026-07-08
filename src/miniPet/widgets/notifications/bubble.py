# coding:utf-8
"""宠物头顶普通对话气泡。"""

import re

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from miniPet import config
from miniPet.clients.tts_client import stop_tts
from miniPet.typewriter import Typewriter
from miniPet.widgets.notifications.constants import BUBBLE_ANIM_IN_MS, BUBBLE_ANIM_MOVE_MS, BUBBLE_ANIM_OUT_MS, BUBBLE_ENTER_OFFSET, BUBBLE_EXIT_OFFSET


def _markdown_to_html(text):
    """简单的Markdown到HTML转换，支持基本格式"""
    if not text:
        return ''
    # 转义HTML特殊字符（除了即将处理的标记）
    html = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    # 代码块 ```code```
    html = re.sub(r'```([^`]+)```', r'<pre style="background:#f5f5f5;padding:8px;border-radius:4px;margin:4px 0;">\1</pre>', html, flags=re.DOTALL)
    # 行内代码 `code`
    html = re.sub(r'`([^`]+)`', r'<code style="background:#f0f0f0;padding:2px 4px;border-radius:3px;">\1</code>', html)
    # 粗体 **text**
    html = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', html)
    # 斜体 *text*
    html = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', html)
    # 段落间的空行（连续换行）压缩为单个换行
    html = re.sub(r'\n\n+', '\n', html)
    # 换行保留
    html = html.replace('\n', '<br>')
    return html


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


class BubbleText(QFrame):
    """宠物头顶普通对话气泡，支持 Markdown 文本和头像。"""

    closed = Signal(str)

    def __init__(self, bubble_id, message, timeout=6000, parent=None, title='miniPet'):
        super().__init__(parent)
        self.bubble_id = bubble_id
        self.anim_group = None
        self.closing = False
        self.closed_emitted = False
        self.dragging = False
        self.drag_start_pos = QPoint()
        self.drag_window_pos = QPoint()
        self.manual_position = False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(1.0)
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
        html_text = _markdown_to_html(wrapped)
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
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.request_close)
        self.timer.start(timeout)

    def animate_in(self, end_pos):
        if self.anim_group is not None:
            self.anim_group.stop()
        self.move(end_pos + BUBBLE_ENTER_OFFSET)
        self.show()
        self.setWindowOpacity(1.0)
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(BUBBLE_ANIM_IN_MS)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.start()

    def animate_to(self, end_pos):
        if self.closing:
            return
        if self.anim_group is not None:
            self.anim_group.stop()
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(BUBBLE_ANIM_MOVE_MS)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.start()

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
            self.timer.stop()
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

    def request_close(self):
        if self.closing:
            return
        self.closing = True
        self.timer.stop()
        self._animate_out()

    def _animate_out(self):
        if self.anim_group is not None:
            self.anim_group.stop()
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(BUBBLE_ANIM_OUT_MS)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(self.pos() + BUBBLE_EXIT_OFFSET)
        pos_anim.setEasingCurve(QEasingCurve.InCubic)
        opacity_anim = QPropertyAnimation(self, b'windowOpacity', self)
        opacity_anim.setDuration(BUBBLE_ANIM_OUT_MS)
        opacity_anim.setStartValue(self.windowOpacity())
        opacity_anim.setEndValue(0.0)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.addAnimation(opacity_anim)
        self.anim_group.finished.connect(self.close)
        self.anim_group.start()

    def closeEvent(self, event):
        if not self.closed_emitted:
            self.closed_emitted = True
            self.closed.emit(self.bubble_id)
        super().closeEvent(event)


