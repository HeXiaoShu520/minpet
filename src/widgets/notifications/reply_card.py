# coding:utf-8
"""回复卡片窗口。"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QVBoxLayout
from qfluentwidgets import TransparentToolButton
from qfluentwidgets import FluentIcon as FIF

import config
from typewriter import Typewriter
from widgets.notifications.constants import REPLY_CARD_TIMEOUT_MS
from widgets.notifications.text_format import markdown_to_html
from widgets.notifications.card_window import ReplyCardWindow

REPLY_CARD_DEFAULT_WIDTH = 320
REPLY_CARD_MIN_WIDTH = 280
REPLY_CARD_MAX_WIDTH = 420
REPLY_CARD_AVATAR_SIZE = 40

def _reply_card_style_qss(style):
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
            QFrame#ReplyCard {{ border-radius: 22px; {card} }}
            QFrame#ReplyCardSectionBox {{ border: 1px solid rgba(222,231,255,180); border-radius: 14px; background: {box_bg}; }}
            QFrame#ReplyCardHr {{ border: none; border-top: 1px solid rgba(180,190,215,130); background: transparent; max-height: 1px; }}
            QLabel {{ border: none; background: transparent; font-family: "Microsoft YaHei UI", "Microsoft YaHei"; }}
            QLabel#ReplyCardTitle {{ color: {title}; font-size: 16px; font-weight: 700; }}
            QLabel#ReplyCardAvatar {{ border-radius: 20px; background: #e8f2ff; }}
            QLabel#ReplyCardStatus {{ color: {meta}; font-size: 12px; font-weight: 700; }}
            QLabel#ReplyCardMeta, QLabel#ReplyCardControlLabel, QLabel#ReplyCardOptionDescription {{ color: {meta}; font-size: 12px; }}
            QLabel#ReplyCardSummary, QLabel#ReplyCardElement {{ color: {body}; font-size: 13px; line-height: 1.45; }}
            QRadioButton, QCheckBox {{ color: {body}; font: 13px "Microsoft YaHei UI"; background: transparent; border: none; }}
            QLineEdit {{ border: 1px solid rgba(218,226,238,220); border-radius: 9px; background: rgba(255,255,255,210); color: {body}; padding: 6px 8px; font: 13px "Microsoft YaHei UI"; }}
            QPushButton {{ border: 1px solid rgba(218,226,238,220); border-radius: 13px; background: rgba(255,255,255,190); color: #3a4054; font: 13px "Microsoft YaHei UI"; padding: 7px 12px; }}
            QPushButton:hover {{ background: #eef6ff; color: #1677ff; border-color: #b9dcff; }}
            QPushButton#PrimaryAction {{ border: 1px solid #7ebcff; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5aa8ff,stop:1 #8b7cff); color: white; font-weight: 700; }}
            QPushButton#DangerAction {{ background: #fff1f0; color: #d93026; border-color: #ffd1cc; }}
            QPushButton#QuietAction {{ background: transparent; color: {meta}; border-color: transparent; }}
        '''


class ReplyCard(ReplyCardWindow):
    """回复卡片，按需渲染展示内容、输入控件和操作按钮。"""

    action_clicked = Signal(dict, dict)

    def __init__(self, card_id, event, timeout=REPLY_CARD_TIMEOUT_MS, parent=None):
        super().__init__(card_id, parent, fade_in=True, initial_opacity=0.0)
        self.event_data = dict(event)
        self.control_widgets = {}
        self._typewriters = []
        self._status_frames = ['', '.', '..', '...']
        self._status_frame = 0
        self._status_animating = False
        self._primary_text = ''
        self._primary_text_html = ''
        self._primary_typewriter = None
        self._body_structure_signature = None
        self.setStyleSheet(_reply_card_style_qss(config.app_config.get('reply_card_style', 'aurora')))
        # 顶层透明窗口叠加 QGraphicsDropShadowEffect 在 Windows 多屏/缩放环境下
        # 容易产生负 dirty rect，触发 UpdateLayeredWindowIndirect 参数错误。
        # 卡片本身已有边框和半透明背景，这里不再给顶层窗口加 Qt 阴影。

        self._card_width = self._normalized_card_width(self.event_data.get('width'))
        self._content_width = max(220, self._card_width - 86)
        self.setFixedWidth(self._card_width)
        card = QFrame(self)
        card.setObjectName('ReplyCard')
        shell = QHBoxLayout(card)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
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

    def _normalized_card_width(self, width):
        try:
            value = int(width or REPLY_CARD_DEFAULT_WIDTH)
        except (TypeError, ValueError):
            value = REPLY_CARD_DEFAULT_WIDTH
        return max(REPLY_CARD_MIN_WIDTH, min(REPLY_CARD_MAX_WIDTH, value))

    def _build_header(self, card):
        header = QHBoxLayout()
        header.setSpacing(10)
        self.avatar_label = QLabel(card)
        self.avatar_label.setObjectName('ReplyCardAvatar')
        self.avatar_label.setFixedSize(REPLY_CARD_AVATAR_SIZE, REPLY_CARD_AVATAR_SIZE)
        self.avatar_label.setAlignment(Qt.AlignCenter)
        avatar_kind = self.event_data.get('avatar_kind') or 'pet'
        icon = QPixmap(str(config.avatar_path(avatar_kind)))
        if not icon.isNull():
            self.avatar_label.setPixmap(self._rounded_avatar(icon, REPLY_CARD_AVATAR_SIZE))
        else:
            self.avatar_label.setText('你' if avatar_kind == 'user' else '宠')
        header.addWidget(self.avatar_label, 0, Qt.AlignTop)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        self.title_label = QLabel(config.current_pet or '宠物', card)
        self.title_label.setObjectName('ReplyCardTitle')
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumWidth(280)
        self.status_label = QLabel('', card)
        self.status_label.setObjectName('ReplyCardStatus')
        title_row.addWidget(self.title_label, 0, Qt.AlignVCenter)
        title_row.addWidget(self.status_label, 0, Qt.AlignVCenter)
        title_row.addStretch(1)
        header.addLayout(title_row, 1)
        close_btn = TransparentToolButton(FIF.CLOSE, card)
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self.request_close)
        header.addWidget(close_btn, 0, Qt.AlignTop)
        self.layout_box.addLayout(header)
        self._refresh_title_meta()

    def _rounded_avatar(self, pixmap, size):
        screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        target = max(1, int(size * dpr))
        scaled = pixmap.scaled(target, target, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        if scaled.width() != target or scaled.height() != target:
            x = max(0, (scaled.width() - target) // 2)
            y = max(0, (scaled.height() - target) // 2)
            scaled = scaled.copy(x, y, target, target)
        result = QPixmap(target, target)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addEllipse(0, 0, target, target)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        result.setDevicePixelRatio(dpr)
        return result

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
        for tw in self._typewriters:
            tw.set_text('')
        if hasattr(self, 'body_layout'):
            self._clear_layout(self.body_layout)
        else:
            self.body_layout = QVBoxLayout()
            self.body_layout.setContentsMargins(0, 0, 0, 0)
            self.body_layout.setSpacing(9)
            self.layout_box.addLayout(self.body_layout)
        self.control_widgets = {}
        self._typewriters = []
        self._primary_typewriter = None
        self._add_elements(self.body_layout, card, self._normalized_elements())
        self._add_controls(self.body_layout, card, self.event_data.get('controls') or [])
        self._add_actions(self.body_layout, card, self.event_data.get('actions') or [])
        self._body_structure_signature = self._structure_signature()

    def _primary_text_value(self):
        return self.event_data.get('summary') or self.event_data.get('content') or self.event_data.get('message') or ''

    def _normalized_elements(self):
        elements = self.event_data.get('elements') or []
        normalized = elements if isinstance(elements, list) else []
        text = self._primary_text_value()
        if text:
            normalized = [{'type': 'text', 'content': text, '_primary': True}] + normalized
        return normalized

    def _structure_signature(self):
        return (repr(self.event_data.get('elements') or []), repr(self.event_data.get('controls') or []), repr(self.event_data.get('actions') or []))

    def update_card(self, event, timeout=None):
        if self.closing:
            return
        previous_html = self._primary_text_html
        self.event_data.update(event or {})
        self._refresh_title_meta()
        new_html = markdown_to_html(str(self._primary_text_value()))
        if self._structure_signature() == self._body_structure_signature and self._primary_typewriter is not None:
            if new_html.startswith(previous_html):
                self._primary_typewriter.append_chunk(new_html[len(previous_html):])
            else:
                self._primary_typewriter.set_text(new_html)
            self._primary_text_html = new_html
        else:
            self._render_body()
        self._refresh_status()
        if timeout is not None:
            self.timer.stop()
            if int(timeout) > 0:
                self.timer.start(int(timeout))
        self.adjustSize()

    def update_message(self, message, timeout=None):
        """兼容纯文本回复的更新入口。"""
        self.update_card({'content': message, 'elements': []}, timeout=timeout)

    def _refresh_title_meta(self):
        self.title_label.setText(str(self.event_data.get('title') or config.current_pet or '宠物'))

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
            self.status_label.setText(self._status_frames[self._status_frame])
            self.status_label.setVisible(True)
            if not self.status_timer.isActive():
                self.status_timer.start(420)
            return
        self._status_animating = False
        self.status_timer.stop()
        if status in ('failed', 'failure', 'error'):
            self.status_label.setText('发送失败')
            self.status_label.setVisible(True)
        else:
            self.status_label.clear()
            self.status_label.setVisible(False)

    def _tick_status(self):
        if not self._status_animating:
            return
        self._status_frame = (self._status_frame + 1) % len(self._status_frames)
        self.status_label.setText(self._status_frames[self._status_frame])

    def _before_request_close(self):
        super()._before_request_close()
        self.status_timer.stop()

    def _add_elements(self, layout, card, elements):
        for element in elements[:8]:
            if not isinstance(element, dict):
                continue
            tag = element.get('tag') or element.get('type')
            if tag in ('hr', 'divider'):
                line = QFrame(card)
                line.setObjectName('ReplyCardHr')
                line.setFixedHeight(1)
                layout.addWidget(line)
                continue
            if tag not in ('markdown', 'text', 'plain_text', 'code'):
                continue
            content = element.get('content') or element.get('text') or ''
            if not content:
                continue
            is_primary = bool(element.get('_primary'))
            label = QLabel('', card)
            label.setObjectName('ReplyCardElement')
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(True)
            label.setFixedWidth(self._content_width)
            html_text = markdown_to_html(str(content))
            label.setText(html_text)
            layout.addWidget(label)
            tw = Typewriter(label)
            self._typewriters.append(tw)
            if is_primary:
                self._primary_text = str(content)
                self._primary_text_html = html_text
                self._primary_typewriter = tw
            tw.typewrite(html_text)

    def _add_controls(self, layout, card, controls):
        for control in controls[:5]:
            if not isinstance(control, dict):
                continue
            ctype = (control.get('type') or 'text').lower()
            cid = control.get('id') or control.get('name')
            if not cid:
                continue
            box = QFrame(card)
            box.setObjectName('ReplyCardSectionBox')
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(10, 8, 10, 8)
            box_layout.setSpacing(6)
            label_text = control.get('label') or control.get('title') or ''
            if label_text:
                label = QLabel(label_text, box)
                label.setObjectName('ReplyCardControlLabel')
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

    def _click_action(self, action):
        event = dict(self.event_data)
        values = self._collect_values()
        if values:
            event['values'] = values
        self.action_clicked.emit(event, action)
        self.request_close()

    def _before_close_event(self):
        self.status_timer.stop()
        for tw in self._typewriters:
            tw.set_text('')
