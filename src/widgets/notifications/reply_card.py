# coding:utf-8
"""回复卡片窗口。"""

from PySide6.QtCore import QEasingCurve, Property, QElapsedTimer, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QTextDocument
from PySide6.QtWidgets import QApplication, QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QVBoxLayout

import config
from typewriter import Typewriter
from widgets.notifications.constants import REPLY_CARD_TIMEOUT_MS
from widgets.notifications.text_format import has_structured_markdown, markdown_to_html
from widgets.notifications.card_window import ReplyCardWindow

REPLY_CARD_WIDTH_LEVELS = (248, 288, 328, 368, 408, 456)
REPLY_CARD_DEFAULT_WIDTH = 288
REPLY_CARD_MIN_WIDTH = REPLY_CARD_WIDTH_LEVELS[0]
REPLY_CARD_MAX_WIDTH = REPLY_CARD_WIDTH_LEVELS[-1]
REPLY_CARD_AVATAR_SIZE = 36
REPLY_CARD_RESIZE_ANIM_MS = 180
REPLY_CARD_COUNTDOWN_TICK_MS = 80


class CountdownAvatarLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 1.0
        self._permanent = False

    def set_progress(self, value):
        self._permanent = False
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    def set_permanent(self):
        self._permanent = True
        self._progress = 1.0
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        progress = 1.0 if self._permanent else self._progress
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        width = 2.0
        rect = QRectF(width / 2, width / 2, self.width() - width, self.height() - width)
        painter.setPen(QPen(QColor(135, 224, 224, 120), width, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, 0, 360 * 16)
        if progress > 0:
            painter.setPen(QPen(QColor(0, 194, 203, 235), width, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(rect, 90 * 16, -int(360 * 16 * progress))
        painter.end()


class CopyableLabel(QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self._copy_button = None
        self._copy_text_cache = ''
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.setCursor(Qt.IBeamCursor)

    def setText(self, text):
        self._copy_text_cache = ''
        self._hide_copy_button()
        super().setText(text)

    def mousePressEvent(self, event):
        self._hide_copy_button()
        if event.button() == Qt.RightButton:
            event.accept()
            return
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            self._show_copy_button_if_selected(event.globalPos())
            event.accept()

    def contextMenuEvent(self, event):
        event.accept()

    def _selected_plain_text(self):
        return self.selectedText().replace('\u2029', '\n').strip()

    def _visible_plain_text(self):
        text = self.text()
        if not text:
            return ''
        if self.textFormat() == Qt.RichText or text.lstrip().startswith('<'):
            doc = QTextDocument()
            doc.setHtml(text)
            return doc.toPlainText()
        return text

    def _copy_text(self):
        text = self._copy_text_cache or self._selected_plain_text()
        if text:
            QApplication.clipboard().setText(text)
        self._copy_text_cache = ''
        self._hide_copy_button()

    def _hide_copy_button(self):
        if self._copy_button is not None:
            self._copy_button.hide()

    def _show_copy_button_if_selected(self, global_pos):
        selected_text = self._selected_plain_text()
        if not selected_text:
            self._copy_text_cache = ''
            self._hide_copy_button()
            return
        self._copy_text_cache = selected_text
        root = self.window()
        if root is None:
            return
        if self._copy_button is None:
            self._copy_button = QPushButton('复制', root)
            self._copy_button.setCursor(Qt.PointingHandCursor)
            self._copy_button.setObjectName('FloatingCopyButton')
            self._copy_button.setFixedSize(58, 30)
            self._copy_button.setStyleSheet(
                'QPushButton#FloatingCopyButton{background:#00a8b4;color:white;'
                'border:1px solid rgba(255,255,255,180);border-radius:15px;'
                'font:13px "Microsoft YaHei UI";font-weight:700;padding:0;}'
                'QPushButton#FloatingCopyButton:hover{background:#14bbc6;}'
            )
            self._copy_button.clicked.connect(self._copy_text)
        pos = root.mapFromGlobal(global_pos)
        x = max(6, min(pos.x() + 8, root.width() - self._copy_button.width() - 6))
        y = max(6, min(pos.y() + 8, root.height() - self._copy_button.height() - 6))
        self._copy_button.move(x, y)
        self._copy_button.raise_()
        self._copy_button.show()


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
            QLabel#ReplyCardAvatar {{ border-radius: 18px; background: #e8f2ff; }}
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
    layout_changed = Signal()

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
        self._primary_structured = False
        self._primary_typewriter = None
        self._body_structure_signature = None
        self._animated_width = 0
        self._resize_anim = None
        self._resize_anchor_center_x = None
        self._resize_anchor_bottom_y = None
        self._content_resize_pending = False
        self._timeout_ms = 0
        self._countdown_elapsed = QElapsedTimer()
        self.setStyleSheet(_reply_card_style_qss(config.app_config.get('reply_card_style', 'aurora')))
        # 顶层透明窗口叠加 QGraphicsDropShadowEffect 在 Windows 多屏/缩放环境下
        # 容易产生负 dirty rect，触发 UpdateLayeredWindowIndirect 参数错误。
        # 卡片本身已有边框和半透明背景，这里不再给顶层窗口加 Qt 阴影。

        self._card_width = self._card_width_for_event(self.event_data)
        self._animated_width = self._card_width
        self._content_width = self._content_width_for_card(self._card_width)
        self.setFixedWidth(self._card_width)
        card = QFrame(self)
        card.setObjectName('ReplyCard')
        shell = QHBoxLayout(card)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.layout_box = QVBoxLayout()
        self.layout_box.setContentsMargins(15, 10, 15, 11)
        self.layout_box.setSpacing(5)
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
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._tick_countdown)
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._tick_status)
        self._refresh_status()
        self._start_auto_close(timeout)

    def _nearest_width_level(self, width):
        return min(REPLY_CARD_WIDTH_LEVELS, key=lambda level: abs(level - width))

    def _normalized_card_width(self, width):
        try:
            value = int(width or REPLY_CARD_DEFAULT_WIDTH)
        except (TypeError, ValueError):
            value = REPLY_CARD_DEFAULT_WIDTH
        return self._nearest_width_level(self._clamped_card_width(value))

    def _clamped_card_width(self, width):
        try:
            value = int(width or REPLY_CARD_DEFAULT_WIDTH)
        except (TypeError, ValueError):
            value = REPLY_CARD_DEFAULT_WIDTH
        return max(REPLY_CARD_MIN_WIDTH, min(REPLY_CARD_MAX_WIDTH, value))

    def _content_width_for_card(self, card_width):
        return max(168, card_width - 30)

    def _sync_content_widths(self):
        for label in self.findChildren(QLabel, 'ReplyCardElement'):
            label.setFixedWidth(self._content_width)

    def _schedule_content_resize(self):
        if self.closing or self._content_resize_pending:
            return
        self._content_resize_pending = True
        QTimer.singleShot(0, self._resize_to_current_content)

    def _resize_to_current_content(self):
        self._content_resize_pending = False
        if self.closing:
            return
        anchor_center_x, anchor_bottom_y = self._resize_anchor()
        old_size = self.size()
        for label in self.findChildren(QLabel, 'ReplyCardElement'):
            label.updateGeometry()
        layout = self.layout()
        if layout is not None:
            layout.activate()
        self.adjustSize()
        if self.size() != old_size:
            self._move_to_resize_anchor(anchor_center_x, anchor_bottom_y)
            self.layout_changed.emit()
            self._refresh_topmost_soon()

    def _start_auto_close(self, timeout):
        self.timer.stop()
        self.countdown_timer.stop()
        self._timeout_ms = max(0, int(timeout or 0))
        if self.manual_position or self._timeout_ms <= 0:
            self.avatar_label.set_permanent()
            return
        self.avatar_label.set_progress(1.0)
        self._countdown_elapsed.restart()
        self.timer.start(self._timeout_ms)
        self.countdown_timer.start(REPLY_CARD_COUNTDOWN_TICK_MS)

    def _tick_countdown(self):
        if self.manual_position:
            self._make_permanent()
            return
        if self._timeout_ms <= 0 or not self._countdown_elapsed.isValid():
            self.countdown_timer.stop()
            self.avatar_label.set_permanent()
            return
        progress = 1.0 - (self._countdown_elapsed.elapsed() / self._timeout_ms)
        self.avatar_label.set_progress(progress)
        if progress <= 0:
            self.countdown_timer.stop()

    def _get_adaptive_width(self):
        return int(self._animated_width or self.width() or self._card_width)

    def _set_adaptive_width(self, width):
        self._apply_card_width(
            int(width),
            anchor_center_x=self._resize_anchor_center_x,
            anchor_bottom_y=self._resize_anchor_bottom_y,
        )

    adaptiveWidth = Property(int, _get_adaptive_width, _set_adaptive_width)

    def _resize_anchor(self):
        return self.x() + self.width() / 2, self.y() + self.height()

    def _move_to_resize_anchor(self, anchor_center_x=None, anchor_bottom_y=None):
        if self.manual_position or not self.isVisible():
            return
        center_x = self.x() + self.width() / 2 if anchor_center_x is None else anchor_center_x
        bottom_y = self.y() + self.height() if anchor_bottom_y is None else anchor_bottom_y
        self.move(int(center_x - self.width() / 2), int(bottom_y - self.height()))

    def _apply_card_width(self, width, anchor_center_x=None, anchor_bottom_y=None):
        width = self._clamped_card_width(width)
        self._animated_width = width
        self._content_width = self._content_width_for_card(width)
        self.setFixedWidth(width)
        self._sync_content_widths()
        self.adjustSize()
        self._move_to_resize_anchor(anchor_center_x, anchor_bottom_y)
        self._refresh_topmost_soon()

    def _animate_card_width_to(self, width, anchor_center_x=None, anchor_bottom_y=None):
        width = self._normalized_card_width(width)
        start_width = self._get_adaptive_width()
        if self._resize_anim is not None:
            self._resize_anim.stop()
            self._resize_anim = None
        self._resize_anchor_center_x = anchor_center_x
        self._resize_anchor_bottom_y = anchor_bottom_y
        if abs(start_width - width) <= 1 or not self.isVisible():
            self._apply_card_width(width, anchor_center_x, anchor_bottom_y)
            self._resize_anchor_center_x = None
            self._resize_anchor_bottom_y = None
            self.layout_changed.emit()
            return
        anim = QPropertyAnimation(self, b'adaptiveWidth', self)
        anim.setDuration(REPLY_CARD_RESIZE_ANIM_MS)
        anim.setStartValue(start_width)
        anim.setEndValue(width)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: self._finish_resize_animation(width))
        self._resize_anim = anim
        anim.start()

    def _finish_resize_animation(self, width):
        self._apply_card_width(width, self._resize_anchor_center_x, self._resize_anchor_bottom_y)
        self._resize_anim = None
        self._resize_anchor_center_x = None
        self._resize_anchor_bottom_y = None
        self.layout_changed.emit()

    def _card_width_for_event(self, event):
        if event.get('width') is not None:
            return self._normalized_card_width(event.get('width'))
        controls = event.get('controls') or []
        actions = event.get('actions') or []
        elements = event.get('elements') or []
        text = self._event_text_for_width(event)
        length = self._weighted_text_length(text)
        if has_structured_markdown(text) and length > 90:
            return 456
        if controls:
            return 408 if len(controls) > 2 or length > 90 else 368
        if actions:
            return 408 if len(actions) > 2 or length > 70 else 368
        if isinstance(elements, list) and len(elements) > 1:
            return 408 if length > 90 else 368
        if length <= 24:
            return 248
        if length <= 52:
            return 288
        if length <= 78:
            return 328
        if length <= 130:
            return 368
        return 408

    def _event_text_for_width(self, event):
        parts = [event.get('summary'), event.get('content'), event.get('message')]
        for element in event.get('elements') or []:
            if isinstance(element, dict):
                parts.append(element.get('content') or element.get('text'))
        return '\n'.join(str(part) for part in parts if part)

    def _weighted_text_length(self, text):
        total = 0
        for ch in str(text or ''):
            if ch in '\r\n\t':
                total += 8
            elif ord(ch) > 127:
                total += 2
            else:
                total += 1
        return total

    def _build_header(self, card):
        header = QHBoxLayout()
        header.setSpacing(9)
        self.avatar_label = CountdownAvatarLabel(card)
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
        self.title_label = CopyableLabel(config.pet_display_name(), card)
        self.title_label.setObjectName('ReplyCardTitle')
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumWidth(280)
        self.status_label = QLabel('', card)
        self.status_label.setObjectName('ReplyCardStatus')
        title_row.addWidget(self.title_label, 0, Qt.AlignVCenter)
        title_row.addWidget(self.status_label, 0, Qt.AlignVCenter)
        title_row.addStretch(1)
        header.addLayout(title_row, 1)
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
        self._primary_structured = False
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
        anchor_center_x, anchor_bottom_y = self._resize_anchor()
        self.event_data.update(event or {})
        new_width = self._card_width_for_event(self.event_data)
        width_changed = new_width != self._card_width
        if width_changed:
            self._card_width = new_width
        self._refresh_title_meta()
        new_text = str(self._primary_text_value())
        new_html = markdown_to_html(new_text)
        new_structured = has_structured_markdown(new_text)
        if self._structure_signature() == self._body_structure_signature and self._primary_typewriter is not None:
            if new_structured or self._primary_structured:
                self._primary_typewriter.set_text(new_html)
            elif new_html.startswith(previous_html):
                self._primary_typewriter.append_chunk(new_html[len(previous_html):])
            else:
                self._primary_typewriter.set_text(new_html)
            self._primary_text = new_text
            self._primary_text_html = new_html
            self._primary_structured = new_structured
        else:
            self._render_body()
            self._schedule_content_resize()
        self._refresh_status()
        if timeout is not None:
            self._start_auto_close(timeout)
        if width_changed:
            self._animate_card_width_to(new_width, anchor_center_x, anchor_bottom_y)
        else:
            self.adjustSize()
            self._move_to_resize_anchor(anchor_center_x, anchor_bottom_y)
            self._refresh_topmost_soon()

    def update_message(self, message, timeout=None):
        """兼容纯文本回复的更新入口。"""
        self.update_card({'content': message, 'elements': []}, timeout=timeout)

    def _refresh_title_meta(self):
        self.title_label.setText(str(self.event_data.get('title') or config.pet_display_name()))

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

    def _make_permanent(self):
        self.timer.stop()
        self.countdown_timer.stop()
        self.avatar_label.set_permanent()

    def _on_manual_positioned(self):
        self._make_permanent()

    def _before_request_close(self):
        super()._before_request_close()
        self.countdown_timer.stop()
        if hasattr(self, 'avatar_label'):
            self.avatar_label.set_progress(0.0)
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
            label = CopyableLabel('', card)
            label.setObjectName('ReplyCardElement')
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(True)
            label.setFixedWidth(self._content_width)
            content_text = str(content)
            structured = has_structured_markdown(content_text)
            html_text = markdown_to_html(content_text)
            label.setText(html_text)
            layout.addWidget(label)
            tw = Typewriter(label, on_update=self._schedule_content_resize)
            self._typewriters.append(tw)
            if is_primary:
                self._primary_text = content_text
                self._primary_text_html = html_text
                self._primary_structured = structured
                self._primary_typewriter = tw
            if structured:
                tw.set_text(html_text)
            else:
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
        self.countdown_timer.stop()
        self.status_timer.stop()
        if self._resize_anim is not None:
            self._resize_anim.stop()
            self._resize_anim = None
        for tw in self._typewriters:
            tw.set_text('')
