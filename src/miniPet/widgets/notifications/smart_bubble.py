# coding:utf-8
"""外部事件智能通知气泡。"""

import re

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QVBoxLayout
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
            QFrame#SmartSectionBox {{ border: 1px solid rgba(222,231,255,180); border-radius: 14px; background: {box_bg}; }}
            QFrame#SmartHr {{ border: none; border-top: 1px solid rgba(180,190,215,130); background: transparent; max-height: 1px; }}
            QLabel {{ border: none; background: transparent; font-family: "Microsoft YaHei UI", "Microsoft YaHei"; }}
            QLabel#SmartTitle {{ color: {title}; font-size: 16px; font-weight: 700; }}
            QLabel#SmartMeta, QLabel#SmartControlLabel, QLabel#SmartOptionDescription {{ color: {meta}; font-size: 12px; }}
            QLabel#SmartSummary, QLabel#SmartElement {{ color: {body}; font-size: 13px; line-height: 1.45; }}
            QRadioButton, QCheckBox {{ color: {body}; font: 13px "Microsoft YaHei UI"; background: transparent; border: none; }}
            QLineEdit {{ border: 1px solid rgba(218,226,238,220); border-radius: 9px; background: rgba(255,255,255,210); color: {body}; padding: 6px 8px; font: 13px "Microsoft YaHei UI"; }}
            QPushButton {{ border: 1px solid rgba(218,226,238,220); border-radius: 13px; background: rgba(255,255,255,190); color: #3a4054; font: 13px "Microsoft YaHei UI"; padding: 7px 12px; }}
            QPushButton:hover {{ background: #eef6ff; color: #1677ff; border-color: #b9dcff; }}
            QPushButton#PrimaryAction {{ border: 1px solid #7ebcff; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5aa8ff,stop:1 #8b7cff); color: white; font-weight: 700; }}
            QPushButton#DangerAction {{ background: #fff1f0; color: #d93026; border-color: #ffd1cc; }}
            QPushButton#QuietAction {{ background: transparent; color: {meta}; border-color: transparent; }}
        '''


class SmartBubble(QFrame):
    """外部事件使用的通用卡片，按需渲染展示内容、输入控件和操作按钮。"""

    action_clicked = Signal(dict, dict)
    closed = Signal(str)

    def __init__(self, bubble_id, event, timeout=SMART_BUBBLE_TIMEOUT_MS, parent=None):
        super().__init__(parent)
        self.bubble_id = bubble_id
        self.event_data = dict(event)
        self.anim_group = None
        self.closing = False
        self.closed_emitted = False
        self.control_widgets = {}
        self._status_frames = ['·', '··', '···']
        self._status_frame = 0
        self._status_animating = False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(0.0)
        self.setStyleSheet(_smart_bubble_style_qss(config.app_config.get('smart_bubble_style', 'aurora')))
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
        self.layout_box = QVBoxLayout()
        self.layout_box.setContentsMargins(15, 13, 15, 13)
        self.layout_box.setSpacing(9)
        shell.addLayout(self.layout_box, 1)

        self._build_header(card)
        self._render_body(card)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self.adjustSize()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.request_close)
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._tick_status)
        self._refresh_status()
        if timeout > 0:
            self.timer.start(timeout)

    def _build_header(self, card):
        header = QHBoxLayout()
        header.setSpacing(10)
        self.badge = QLabel(self._badge_text(self.event_data), card)
        self.badge.setFixedSize(34, 34)
        self.badge.setAlignment(Qt.AlignCenter)
        self._set_badge_color(self._badge_color(self.event_data))
        header.addWidget(self.badge, 0, Qt.AlignTop)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(3)
        self.title_label = QLabel(self.event_data.get('title') or self.event_data.get('sender') or 'AI 回复', card)
        self.title_label.setObjectName('SmartTitle')
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumWidth(330)
        self.meta_label = QLabel('', card)
        self.meta_label.setObjectName('SmartMeta')
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.meta_label)
        header.addLayout(title_box, 1)
        close_btn = TransparentToolButton(FIF.CLOSE, card)
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self.request_close)
        header.addWidget(close_btn, 0, Qt.AlignTop)
        self.layout_box.addLayout(header)
        self._refresh_title_meta()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            widget = item.widget()
            if child_layout is not None:
                self._clear_layout(child_layout)
            if widget is not None:
                widget.deleteLater()

    def _render_body(self, card=None):
        card = card or self
        if hasattr(self, 'body_layout'):
            self._clear_layout(self.body_layout)
        else:
            self.body_layout = QVBoxLayout()
            self.body_layout.setContentsMargins(0, 0, 0, 0)
            self.body_layout.setSpacing(9)
            self.layout_box.addLayout(self.body_layout)
        self.control_widgets = {}
        self._add_elements(self.body_layout, card, self._normalized_elements())
        self._add_controls(self.body_layout, card, self.event_data.get('controls') or [])
        self._add_actions(self.body_layout, card, self.event_data.get('actions') or [])

    def _normalized_elements(self):
        elements = self.event_data.get('elements') or []
        if elements:
            return elements
        text = self.event_data.get('summary') or self.event_data.get('content') or self.event_data.get('message') or ''
        return [{'type': 'text', 'content': text}] if text else []

    def update_card(self, event, timeout=None):
        if self.closing:
            return
        self.event_data.update(event or {})
        self._refresh_title_meta()
        self._render_body()
        self._refresh_status()
        if timeout is not None:
            self.timer.stop()
            if int(timeout) > 0:
                self.timer.start(int(timeout))
        self.adjustSize()

    def _refresh_title_meta(self):
        self.title_label.setText(self.event_data.get('title') or self.event_data.get('sender') or 'AI 回复')
        meta_text = self.event_data.get('subtitle') or self.event_data.get('sender') or self.event_data.get('source') or self._kind_text(self.event_data)
        self.meta_label.setText(meta_text)
        self.meta_label.setVisible(bool(meta_text))

    def _status_value(self):
        if self.event_data.get('done'):
            return 'done'
        if self.event_data.get('error'):
            return 'failed'
        return str(self.event_data.get('status') or self.event_data.get('state') or '').strip().lower().replace('_', '-')

    def _refresh_status(self):
        status = self._status_value()
        if status in ('running', 'streaming', 'thinking', 'working'):
            self._status_animating = True
            self._status_frame = 0
            self.badge.setText(self._status_frames[self._status_frame])
            self._set_badge_color(self._badge_color({'status': 'streaming'}))
            if not self.status_timer.isActive():
                self.status_timer.start(420)
            return
        self._status_animating = False
        self.status_timer.stop()
        if status in ('done', 'completed', 'complete', 'success'):
            self.badge.setText('✓')
            self._set_badge_color('qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #74d680,stop:1 #22c55e)')
        elif status in ('failed', 'failure', 'error'):
            self.badge.setText('!')
            self._set_badge_color('qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ff8a80,stop:1 #ff5f7e)')
        else:
            self.badge.setText(self._badge_text(self.event_data))
            self._set_badge_color(self._badge_color(self.event_data))

    def _tick_status(self):
        if not self._status_animating:
            return
        self._status_frame = (self._status_frame + 1) % len(self._status_frames)
        self.badge.setText(self._status_frames[self._status_frame])

    def _set_badge_color(self, color):
        self.badge.setStyleSheet('QLabel{border-radius:17px;background:%s;color:white;font-size:15px;font-weight:700;}' % color)

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
        self.status_timer.stop()
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
            if tag in ('hr', 'divider'):
                line = QFrame(card)
                line.setObjectName('SmartHr')
                line.setFixedHeight(1)
                layout.addWidget(line)
                continue
            if tag not in ('markdown', 'text', 'plain_text', 'code'):
                continue
            content = element.get('content') or element.get('text') or ''
            if not content:
                continue
            label = QLabel(TextWrap.wrap(self._plain_card_text(str(content)), 36, False)[0], card)
            label.setObjectName('SmartElement')
            label.setWordWrap(True)
            label.setMaximumWidth(360)
            layout.addWidget(label)

    def _add_controls(self, layout, card, controls):
        for control in controls[:5]:
            if not isinstance(control, dict):
                continue
            ctype = (control.get('type') or 'text').lower()
            cid = control.get('id') or control.get('name')
            if not cid:
                continue
            box = QFrame(card)
            box.setObjectName('SmartSectionBox')
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(10, 8, 10, 8)
            box_layout.setSpacing(6)
            label_text = control.get('label') or control.get('title') or ''
            if label_text:
                label = QLabel(label_text, box)
                label.setObjectName('SmartControlLabel')
                box_layout.addWidget(label)
            if ctype in ('text', 'input'):
                edit = QLineEdit(box)
                edit.setPlaceholderText(control.get('placeholder') or '')
                edit.setText(str(control.get('default_value') or control.get('value') or ''))
                self.control_widgets[cid] = {'type': 'text', 'widget': edit}
                box_layout.addWidget(edit)
            elif ctype in ('radio', 'radio_group', 'select'):
                group = QButtonGroup(box)
                buttons = []
                for option in (control.get('options') or [])[:8]:
                    if not isinstance(option, dict):
                        continue
                    btn = QRadioButton(option.get('label') or option.get('id') or '', box)
                    btn._minipet_value = option.get('id') or option.get('value') or option.get('label')
                    if option.get('description'):
                        btn.setToolTip(str(option.get('description')))
                    group.addButton(btn)
                    box_layout.addWidget(btn)
                    buttons.append(btn)
                custom_edit = None
                if control.get('allow_custom'):
                    custom = QRadioButton(control.get('custom_label') or '其他', box)
                    custom._minipet_value = control.get('custom_id') or 'custom'
                    group.addButton(custom)
                    box_layout.addWidget(custom)
                    custom_edit = QLineEdit(box)
                    custom_edit.setPlaceholderText(control.get('custom_placeholder') or '请输入')
                    box_layout.addWidget(custom_edit)
                    buttons.append(custom)
                if buttons:
                    buttons[0].setChecked(True)
                self.control_widgets[cid] = {'type': 'radio_group', 'buttons': buttons, 'custom_edit': custom_edit}
            elif ctype in ('checkbox', 'checkbox_group', 'multi_select'):
                checks = []
                for option in (control.get('options') or [])[:8]:
                    if not isinstance(option, dict):
                        continue
                    chk = QCheckBox(option.get('label') or option.get('id') or '', box)
                    chk._minipet_value = option.get('id') or option.get('value') or option.get('label')
                    box_layout.addWidget(chk)
                    checks.append(chk)
                custom_edit = None
                if control.get('allow_custom'):
                    chk = QCheckBox(control.get('custom_label') or '其他', box)
                    chk._minipet_value = control.get('custom_id') or 'custom'
                    box_layout.addWidget(chk)
                    custom_edit = QLineEdit(box)
                    custom_edit.setPlaceholderText(control.get('custom_placeholder') or '请输入')
                    box_layout.addWidget(custom_edit)
                    checks.append(chk)
                self.control_widgets[cid] = {'type': 'checkbox_group', 'checks': checks, 'custom_edit': custom_edit}
            else:
                continue
            layout.addWidget(box)

    def _add_actions(self, layout, card, actions):
        if not actions:
            return
        action_row = QHBoxLayout()
        action_row.setSpacing(7)
        action_row.addStretch(1)
        for action in actions[:4]:
            if not isinstance(action, dict):
                continue
            btn = QPushButton(action.get('label') or action.get('id') or '操作', card)
            btn.setCursor(Qt.PointingHandCursor)
            style = action.get('style') or action.get('intent') or ''
            intent = action.get('intent') or ''
            action_id = action.get('id') or ''
            if style in ('primary', 'confirm') or intent == 'confirm' or action_id in ('confirm', 'send', 'ok', 'submit'):
                btn.setObjectName('PrimaryAction')
            elif style in ('danger', 'reject') or intent == 'reject':
                btn.setObjectName('DangerAction')
            elif style in ('quiet', 'cancel') or intent == 'cancel' or action_id in ('cancel', 'ignore'):
                btn.setObjectName('QuietAction')
            btn.clicked.connect(lambda checked=False, a=action: self._click_action(a))
            action_row.addWidget(btn)
        layout.addLayout(action_row)

    def _collect_values(self):
        values = {}
        for cid, spec in self.control_widgets.items():
            if spec['type'] == 'text':
                values[cid] = spec['widget'].text()
            elif spec['type'] == 'radio_group':
                selected = None
                for btn in spec['buttons']:
                    if btn.isChecked():
                        selected = getattr(btn, '_minipet_value', btn.text())
                        break
                values[cid] = selected
                if selected == 'custom' and spec.get('custom_edit') is not None:
                    values[cid + '_text'] = spec['custom_edit'].text()
            elif spec['type'] == 'checkbox_group':
                selected = [getattr(chk, '_minipet_value', chk.text()) for chk in spec['checks'] if chk.isChecked()]
                values[cid] = selected
                if 'custom' in selected and spec.get('custom_edit') is not None:
                    values[cid + '_text'] = spec['custom_edit'].text()
        return values

    def _plain_card_text(self, text):
        text = re.sub(r'```[^\n]*\n(.*?)```', r'\1', text, flags=re.DOTALL)
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1', text)
        return text

    def _badge_text(self, event):
        kind = (event.get('kind') or event.get('type') or '').lower()
        priority = (event.get('priority') or '').lower()
        if priority in ('urgent', 'high'):
            return '!'
        if priority == 'important':
            return '★'
        if 'progress' in kind:
            return '…'
        return 'AI'

    def _badge_color(self, event):
        status = (event.get('status') or event.get('state') or '').lower()
        priority = (event.get('priority') or '').lower()
        if status in ('failed', 'failure', 'error') or priority in ('urgent', 'high'):
            return 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ff8a80,stop:1 #ff5f7e)'
        if status in ('done', 'completed', 'complete', 'success'):
            return 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #74d680,stop:1 #22c55e)'
        if priority == 'important':
            return 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ffd66b,stop:1 #ff9f43)'
        return 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #73c8ff,stop:1 #9d8cff)'

    def _kind_text(self, event):
        kind = event.get('kind') or event.get('type') or ''
        labels = {
            'message': 'AI 后端',
            'card': 'AI 后端',
            'surface.show': 'AI 后端',
            'surface.update': 'AI 后端',
        }
        return labels.get(kind, kind.replace('_', ' ') if kind else '')

    def _click_action(self, action):
        event = dict(self.event_data)
        values = self._collect_values()
        if values:
            event['values'] = values
        self.action_clicked.emit(event, action)
        self.request_close()

    def closeEvent(self, event):
        self.status_timer.stop()
        if not self.closed_emitted:
            self.closed_emitted = True
            self.closed.emit(self.bubble_id)
        super().closeEvent(event)
