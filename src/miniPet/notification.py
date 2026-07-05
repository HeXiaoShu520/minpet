# coding:utf-8
import re
import uuid

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QPoint, QRect, QSize, Qt, QTimer, QUrl, Signal

BUBBLE_STACK_GAP = 10
BUBBLE_BASE_GAP = 18
BUBBLE_ENTER_OFFSET = QPoint(0, -14)
BUBBLE_EXIT_OFFSET = QPoint(0, -10)
BUBBLE_ANIM_IN_MS = 220
BUBBLE_ANIM_MOVE_MS = 180
BUBBLE_ANIM_OUT_MS = 180
MAX_STACKED_BUBBLES = 4
SMART_BUBBLE_TIMEOUT_MS = 12000
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)
from qfluentwidgets import BodyLabel, CaptionLabel, StrongBodyLabel, TextWrap, TransparentToolButton
from qfluentwidgets import FluentIcon as FIF

from miniPet.typewriter import Typewriter
from miniPet.tts_client import stop_tts

from miniPet import config


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


def _smart_bubble_style_qss(style):
    card = {
        'glass': 'background: rgba(255,255,255,218); border: 1px solid rgba(255,255,255,210);',
        'cream': 'background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #fffaf0,stop:1 #fff2dc); border: 1px solid rgba(245,210,160,220);',
        'mint': 'background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #f4fffb,stop:1 #e9fff7); border: 1px solid rgba(150,225,210,220);',
        'dark': 'background: rgba(36,42,58,238); border: 1px solid rgba(90,105,145,220);',
        'aurora': 'background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #fffdfa,stop:0.54 #f7fbff,stop:1 #f6f1ff); border: 1px solid rgba(228,215,255,210);',
    }.get(style, '')
    dark = style == 'dark'
    title = '#f3f6ff' if dark else '#202436'
    body = '#d9e0f2' if dark else '#3a4054'
    meta = '#9faad0' if dark else '#8b93a7'
    box_bg = 'rgba(255,255,255,35)' if dark else '#ffffff'
    return f'''
            QFrame#SmartCard {{ border-radius: 22px; {card} }}
            QFrame#SmartAccent {{ border: none; border-radius: 3px; background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #8fd3ff, stop:1 #c7a8ff); }}
            QFrame#SmartSuggestionBox {{ border: 1px solid rgba(222,231,255,180); border-radius: 14px; background: {box_bg}; }}
            QLabel {{ border: none; background: transparent; font-family: "Microsoft YaHei UI", "Microsoft YaHei"; }}
            QLabel#SmartTitle {{ color: {title}; font-size: 16px; font-weight: 700; }}
            QLabel#SmartMeta, QLabel#SmartSuggestionLabel {{ color: {meta}; font-size: 12px; }}
            QLabel#SmartSummary, QLabel#SmartElement, QLabel#SmartSuggestion {{ color: {body}; font-size: 13px; line-height: 1.45; }}
            QFrame#SmartHr {{ border: none; border-top: 1px solid rgba(180,190,215,130); background: transparent; max-height: 1px; }}
            QPushButton {{ border: 1px solid rgba(218,226,238,220); border-radius: 13px; background: rgba(255,255,255,190); color: #3a4054; font: 13px "Microsoft YaHei UI"; padding: 7px 12px; }}
            QPushButton:hover {{ background: #eef6ff; color: #1677ff; border-color: #b9dcff; }}
            QPushButton#PrimaryAction {{ border: 1px solid #7ebcff; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5aa8ff,stop:1 #8b7cff); color: white; font-weight: 700; }}
            QPushButton#DangerAction {{ background: #fff1f0; color: #d93026; border-color: #ffd1cc; }}
            QPushButton#QuietAction {{ background: transparent; color: {meta}; border-color: transparent; }}
        '''


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
        # 根据内容长度自适应宽度：短内容窄一些，长内容宽一些
        content_length = len(message or '')
        if content_length < 30:
            max_width = 260
        elif content_length < 100:
            max_width = 340
        elif content_length < 200:
            max_width = 420
        else:
            max_width = 500
        msg_label.setMaximumWidth(max_width)
        text_box.addWidget(title_label)
        text_box.addWidget(msg_label, 0, Qt.AlignTop)
        text_box.setAlignment(Qt.AlignTop)
        layout.addLayout(text_box, 1)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        wrapped = message or ''
        html_text = _markdown_to_html(wrapped)
        msg_label.setText(html_text)
        self.adjustSize()
        msg_label.clear()
        self._tw = Typewriter(msg_label)
        tts_on = config.tts_config.get('enabled') and config.tts_config.get('api_key')
        delay = int(config.typewriter_config.get('tts_delay_ms', 500)) if tts_on else 0
        if delay > 0:
            QTimer.singleShot(delay, lambda: self._tw.typewrite(wrapped))
        else:
            self._tw.typewrite(wrapped)
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


class SmartBubble(QFrame):
    action_clicked = Signal(dict, dict)
    closed = Signal(str)

    def __init__(self, bubble_id, event, timeout=SMART_BUBBLE_TIMEOUT_MS, parent=None):
        super().__init__(parent)
        self.bubble_id = bubble_id
        self.event_data = dict(event)
        self.anim_group = None
        self.closing = False
        self.closed_emitted = False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(0.0)
        style = config.app_config.get('smart_bubble_style', 'aurora')
        self.setStyleSheet(_smart_bubble_style_qss(style))
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(94, 84, 135, 44))
        self.setGraphicsEffect(shadow)

        card = QFrame(self)
        card.setObjectName('SmartCard')
        shell = QHBoxLayout(card)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        accent = QFrame(card)
        accent.setObjectName('SmartAccent')
        accent.setFixedWidth(6)
        shell.addWidget(accent)
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 13, 15, 13)
        layout.setSpacing(9)
        shell.addLayout(layout, 1)

        header = QHBoxLayout()
        header.setSpacing(10)
        badge = QLabel(self._badge_text(event), card)
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet('QLabel{border-radius:17px;background:%s;color:white;font-size:15px;font-weight:700;}' % self._badge_color(event))
        header.addWidget(badge, 0, Qt.AlignTop)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(3)
        title = QLabel(event.get('title') or event.get('sender') or '外部事件', card)
        title.setObjectName('SmartTitle')
        title.setWordWrap(True)
        title.setMaximumWidth(330)
        meta_text = event.get('subtitle') or event.get('sender') or event.get('source') or self._kind_text(event)
        meta = QLabel(meta_text, card)
        meta.setObjectName('SmartMeta')
        title_box.addWidget(title)
        if meta_text:
            title_box.addWidget(meta)
        header.addLayout(title_box, 1)
        close_btn = TransparentToolButton(FIF.CLOSE, card)
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self.request_close)
        header.addWidget(close_btn, 0, Qt.AlignTop)
        layout.addLayout(header)

        elements = event.get('elements') or []
        if elements:
            self._add_elements(layout, card, elements)
        else:
            summary_text = event.get('summary') or event.get('content') or event.get('message') or ''
            if summary_text:
                summary = QLabel(TextWrap.wrap(str(summary_text), 36, False)[0], card)
                summary.setObjectName('SmartSummary')
                summary.setWordWrap(True)
                summary.setMaximumWidth(360)
                layout.addWidget(summary)
        suggestion = event.get('suggestion') or event.get('assistant_message')
        if suggestion:
            suggestion_box = QFrame(card)
            suggestion_box.setObjectName('SmartSuggestionBox')
            suggestion_layout = QVBoxLayout(suggestion_box)
            suggestion_layout.setContentsMargins(10, 8, 10, 8)
            suggestion_layout.setSpacing(3)
            suggestion_label = QLabel(self._suggestion_label(event), suggestion_box)
            suggestion_label.setObjectName('SmartSuggestionLabel')
            tip = QLabel(TextWrap.wrap(suggestion, 36, False)[0], suggestion_box)
            tip.setObjectName('SmartSuggestion')
            tip.setWordWrap(True)
            tip.setMaximumWidth(340)
            suggestion_layout.addWidget(suggestion_label)
            suggestion_layout.addWidget(tip)
            layout.addWidget(suggestion_box)
        actions = event.get('actions') or [{'id': 'ignore', 'label': '忽略', 'style': 'quiet'}]
        action_row = QHBoxLayout()
        action_row.setSpacing(7)
        action_row.addStretch(1)
        for action in actions[:4]:
            btn = QPushButton(action.get('label') or action.get('id') or '操作', card)
            btn.setCursor(Qt.PointingHandCursor)
            style = action.get('style') or action.get('intent') or ''
            intent = action.get('intent') or ''
            action_id = action.get('id') or ''
            if style in ('primary', 'confirm') or intent == 'confirm' or action_id in ('confirm', 'send', 'ok'):
                btn.setObjectName('PrimaryAction')
            elif style in ('danger', 'reject') or intent == 'reject':
                btn.setObjectName('DangerAction')
            elif style in ('quiet', 'cancel') or intent == 'cancel' or action_id in ('cancel', 'ignore'):
                btn.setObjectName('QuietAction')
            btn.clicked.connect(lambda checked=False, a=action: self._click_action(a))
            action_row.addWidget(btn)
        layout.addLayout(action_row)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self.adjustSize()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.request_close)
        if timeout > 0:
            self.timer.start(timeout)

    def animate_in(self, end_pos):
        if self.anim_group is not None:
            self.anim_group.stop()
        self.move(end_pos + BUBBLE_ENTER_OFFSET)
        self.show()
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(BUBBLE_ANIM_IN_MS)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        opacity_anim = QPropertyAnimation(self, b'windowOpacity', self)
        opacity_anim.setDuration(BUBBLE_ANIM_IN_MS)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.addAnimation(opacity_anim)
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

    def _add_elements(self, layout, card, elements):
        for element in elements[:8]:
            if not isinstance(element, dict):
                continue
            tag = element.get('tag') or element.get('type')
            if tag == 'hr':
                line = QFrame(card)
                line.setObjectName('SmartHr')
                line.setFixedHeight(1)
                layout.addWidget(line)
                continue
            if tag not in ('markdown', 'text', 'plain_text'):
                continue
            content = element.get('content') or element.get('text') or ''
            if not content:
                continue
            label = QLabel(TextWrap.wrap(self._plain_card_text(str(content)), 36, False)[0], card)
            label.setObjectName('SmartElement')
            label.setWordWrap(True)
            label.setMaximumWidth(360)
            layout.addWidget(label)

    def _plain_card_text(self, text):
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1', text)
        return text

    def _badge_text(self, event):
        kind = (event.get('kind') or event.get('type') or '').lower()
        priority = (event.get('priority') or '').lower()
        if 'confirm' in kind or kind == 'display.confirm.show':
            return '✓'
        if priority in ('urgent', 'high'):
            return '!'
        if priority == 'important':
            return '★'
        if 'progress' in kind or 'agent' in kind:
            return '…'
        return 'AI'

    def _badge_color(self, event):
        kind = (event.get('kind') or event.get('type') or '').lower()
        priority = (event.get('priority') or '').lower()
        if priority in ('urgent', 'high'):
            return 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ff8a80,stop:1 #ff5f7e)'
        if 'confirm' in kind or kind == 'display.confirm.show':
            return 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #74d680,stop:1 #22c55e)'
        if priority == 'important':
            return 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ffd66b,stop:1 #ff9f43)'
        return 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #73c8ff,stop:1 #9d8cff)'

    def _kind_text(self, event):
        kind = event.get('kind') or event.get('type') or ''
        labels = {
            'draft_confirmation': '草稿确认',
            'message': 'AI 后端',
            'confirm': '需要确认',
        }
        return labels.get(kind, kind.replace('_', ' ') if kind else '')

    def _suggestion_label(self, event):
        kind = (event.get('kind') or event.get('type') or '').lower()
        if 'confirm' in kind or kind == 'display.confirm.show':
            return '建议操作'
        return 'AI 建议'

    def _click_action(self, action):
        self.action_clicked.emit(self.event_data, action)
        self.request_close()

    def closeEvent(self, event):
        if not self.closed_emitted:
            self.closed_emitted = True
            self.closed.emit(self.bubble_id)
        super().closeEvent(event)


class NotificationCenter(QWidget):
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

    def setup_smart_bubble(self, event, x, y):
        bubble_id = str(uuid.uuid4())
        timeout = int(event.get('timeout_ms', SMART_BUBBLE_TIMEOUT_MS) or 0)
        bubble = SmartBubble(bubble_id, event, timeout)
        bubble.action_clicked.connect(self.smart_action_clicked)
        bubble.closed.connect(self._remove_bubble)
        self._register_bubble(bubble_id, bubble, x, y)
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
