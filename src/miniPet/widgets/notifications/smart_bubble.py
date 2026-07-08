# coding:utf-8
"""外部事件智能通知气泡。"""

import re

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from qfluentwidgets import TextWrap, TransparentToolButton
from qfluentwidgets import FluentIcon as FIF

from miniPet import config
from miniPet.widgets.notifications.constants import BUBBLE_ANIM_IN_MS, BUBBLE_ANIM_MOVE_MS, BUBBLE_ANIM_OUT_MS, BUBBLE_ENTER_OFFSET, BUBBLE_EXIT_OFFSET, SMART_BUBBLE_TIMEOUT_MS


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


class SmartBubble(QFrame):
    """外部事件使用的智能通知卡片，支持建议、元信息和操作按钮。"""

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


