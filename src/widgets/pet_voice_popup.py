# coding:utf-8
"""桌宠轻量语音聊天悬浮球。"""

import math

from PySide6.QtCore import QEasingCurve, QEvent, QParallelAnimationGroup, QPropertyAnimation, QPoint, QPointF, QRectF, Qt, QTimer, Signal, Property
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QWidget

import config
from widgets.ui_utils import clamp_popup_pos


VOICE_ORB_PALETTES = {
    'jade': {'bg': (244, 255, 249, 246), 'border': (125, 195, 165, 238), 'wave': (72, 172, 145, 225), 'dot': (98, 175, 150), 'ring': (84, 190, 160), 'core': (116, 210, 178, 230), 'core2': (225, 255, 240, 230), 'text': (30, 70, 58, 235)},
    'mint': {'bg': (245, 243, 255, 245), 'border': (168, 158, 255, 235), 'wave': (116, 111, 255, 220), 'dot': (132, 105, 255), 'ring': (50, 210, 190), 'core': (70, 160, 255, 230), 'core2': (92, 238, 202, 210), 'text': (40, 44, 52, 230)},
    'violet': {'bg': (248, 244, 255, 245), 'border': (183, 150, 255, 235), 'wave': (143, 111, 255, 225), 'dot': (155, 105, 255), 'ring': (132, 115, 255), 'core': (130, 105, 255, 230), 'core2': (210, 150, 255, 210), 'text': (45, 38, 62, 230)},
    'sakura': {'bg': (255, 246, 250, 245), 'border': (255, 170, 205, 235), 'wave': (255, 125, 175, 225), 'dot': (235, 120, 180), 'ring': (255, 145, 160), 'core': (255, 125, 175, 230), 'core2': (255, 200, 220, 220), 'text': (58, 35, 45, 230)},
    'sunset': {'bg': (255, 249, 240, 245), 'border': (255, 185, 105, 235), 'wave': (255, 165, 80, 225), 'dot': (240, 150, 75), 'ring': (255, 130, 90), 'core': (255, 145, 70, 230), 'core2': (255, 215, 120, 220), 'text': (58, 40, 28, 230)},
    'mono': {'bg': (246, 247, 249, 245), 'border': (185, 192, 205, 235), 'wave': (110, 120, 140, 225), 'dot': (120, 130, 150), 'ring': (105, 155, 160), 'core': (120, 135, 155, 230), 'core2': (180, 190, 200, 220), 'text': (38, 42, 50, 230)},
}


class VoiceOrbWidget(QWidget):
    """语音聊天状态球的绘制组件，负责动画、文字宽度和不同状态图标。"""

    width_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = 'idle'
        self.phase = 0
        self.text = ''
        self.min_orb_width = 40
        self.max_orb_width = 260
        self.orb_height = 40
        self.icon_area_width = 40
        self.text_right_padding = 12
        self._orb_width = self.min_orb_width
        self._target_width = self.min_orb_width
        self.width_anim = None
        # 涟漪状态（供父级 PetVoicePopup 绘制）
        self._ripples = []        # 每项为 progress float 0.0→1.0
        self._ripple_tick = 0
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.min_orb_width, self.orb_height)

    def get_orb_width(self):
        return self._orb_width

    def set_orb_width(self, width):
        width = int(max(self.min_orb_width, min(self.max_orb_width, width)))
        if self._orb_width == width:
            return
        self._orb_width = width
        self.setFixedWidth(width)
        self.width_changed.emit()
        self.update()

    orbWidth = Property(int, get_orb_width, set_orb_width)

    def set_state(self, state):
        if self.state != state:
            self.state = state
            self.phase = 0
        self.update()

    def set_text(self, text):
        self.text = str(text or '').strip()
        self._animate_to_text_width()
        self.update()

    def set_phase(self, phase):
        self.phase = phase
        self.update()

    def _tick_ripples(self):
        # 推进所有涟漪，progress 0.0→1.0
        self._ripples = [p + 0.022 for p in self._ripples if p + 0.022 < 1.0]
        # listening/speaking/wakeup 状态每隔一定 tick 生成新涟漪，最多同时 3 个
        if self.state in ('listening', 'speaking', 'wakeup'):
            self._ripple_tick += 1
            interval = 28 if self.state == 'wakeup' else (22 if self.state == 'listening' else 18)
            if self._ripple_tick >= interval and len(self._ripples) < 3:
                self._ripples.append(0.0)
                self._ripple_tick = 0
        else:
            self._ripple_tick = 0

    def _animate_to_text_width(self):
        target = self.min_orb_width
        if self.text:
            fm = QFontMetrics(self.font())
            target = self.icon_area_width + 8 + fm.horizontalAdvance(self.text) + self.text_right_padding
            target = max(self.min_orb_width, min(self.max_orb_width, target))
        if abs(target - self._target_width) < 2:
            return
        self._target_width = target
        if self.width_anim is not None:
            self.width_anim.stop()
        self.width_anim = QPropertyAnimation(self, b'orbWidth', self)
        self.width_anim.setDuration(220 if target <= self.min_orb_width else 180)
        self.width_anim.setStartValue(self._orb_width)
        self.width_anim.setEndValue(target)
        self.width_anim.setEasingCurve(QEasingCurve.InOutCubic if target <= self.min_orb_width else QEasingCurve.OutCubic)
        self.width_anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pill = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg, border = self._background_colors()
        painter.setPen(QPen(border, 1))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        self._paint_material_glow(painter, pill)

        icon_rect = QRectF(0, 0, self.icon_area_width, self.height()).adjusted(4, 4, -4, -4)
        if self.state == 'listening':
            self._paint_listening(painter, icon_rect)
        elif self.state == 'wakeup':
            self._paint_wakeup(painter, icon_rect)
        elif self.state == 'thinking':
            self._paint_thinking(painter, icon_rect)
        elif self.state == 'speaking':
            self._paint_speaking(painter, icon_rect)
        elif self.state == 'error':
            self._paint_status_dot(painter, icon_rect, QColor(255, 90, 80, 220))
        else:
            self._paint_status_dot(painter, icon_rect, self._color('dot', 185))
        self._paint_text(painter)

    def _paint_material_glow(self, painter, pill):
        style = config.app_config.get('voice_orb_style', 'jade')
        settings = {
            'jade': (QColor(255, 255, 246, 135), QColor(210, 246, 226, 62), QColor(120, 205, 170, 18), QColor(94, 175, 145, 42)),
            'glass': (QColor(255, 255, 255, 120), QColor(210, 235, 255, 54), QColor(120, 170, 220, 18), QColor(120, 170, 220, 48)),
            'sakura': (QColor(255, 255, 255, 112), QColor(255, 215, 230, 58), QColor(255, 145, 185, 18), QColor(255, 150, 190, 38)),
            'sunset': (QColor(255, 250, 220, 118), QColor(255, 210, 125, 58), QColor(255, 120, 80, 20), QColor(230, 135, 70, 40)),
            'mono': (QColor(255, 255, 255, 85), QColor(210, 216, 226, 36), QColor(120, 130, 145, 12), QColor(130, 140, 155, 28)),
            'violet': (QColor(255, 255, 255, 98), QColor(225, 205, 255, 52), QColor(150, 115, 255, 18), QColor(155, 130, 230, 34)),
            'mint': (QColor(255, 255, 255, 98), QColor(215, 245, 235, 52), QColor(90, 205, 170, 18), QColor(90, 180, 155, 34)),
        }
        c0, c1, c2, inner = settings.get(style, settings['mint'])
        glow = QRadialGradient(QPointF(pill.left() + pill.width() * 0.28, pill.top() + pill.height() * 0.26), max(pill.width(), pill.height()) * 0.78)
        glow.setColorAt(0.0, c0)
        glow.setColorAt(0.45, c1)
        glow.setColorAt(1.0, c2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawRoundedRect(pill.adjusted(2, 2, -2, -2), pill.height() / 2, pill.height() / 2)

        painter.setPen(QPen(QColor(255, 255, 255, 86 if style != 'mono' else 58), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(pill.adjusted(7, 6, -7, -7), 42 * 16, 92 * 16)
        painter.setPen(QPen(inner, 1))
        painter.drawRoundedRect(pill.adjusted(3, 3, -3, -3), pill.height() / 2 - 3, pill.height() / 2 - 3)

    def _palette(self):
        return VOICE_ORB_PALETTES.get(config.app_config.get('voice_orb_style', 'jade'), VOICE_ORB_PALETTES['jade'])

    def _color(self, key, alpha=None):
        values = self._palette()[key]
        if len(values) == 3:
            values = (*values, 255 if alpha is None else alpha)
        elif alpha is not None:
            values = (*values[:3], alpha)
        return QColor(*values)

    def _background_colors(self):
        if self.state == 'error':
            return QColor(255, 244, 244, 245), QColor(255, 150, 140, 235)
        if self.state == 'idle':
            return self._color('bg'), self._color('border')
        if self.state == 'wakeup':
            return self._color('bg'), self._color('ring', 245)
        return self._color('bg'), self._color('border')

    def _paint_text(self, painter):
        if not self.text or self.width() <= self.icon_area_width + 10:
            return
        text_rect = QRectF(self.icon_area_width, 0, self.width() - self.icon_area_width - self.text_right_padding, self.height())
        if text_rect.width() <= 8:
            return
        painter.setPen(self._color('text'))
        font = painter.font()
        font.setPointSize(10)
        font.setFamily('Microsoft YaHei UI')
        painter.setFont(font)
        text = QFontMetrics(font).elidedText(self.text, Qt.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)

    def _paint_listening(self, painter, rect):
        center_y = rect.center().y()
        bar_count = 5
        bar_w = 3.6
        gap = 2.8
        total_w = bar_count * bar_w + (bar_count - 1) * gap
        start_x = rect.center().x() - total_w / 2
        color = self._color('wave')
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        for i in range(bar_count):
            wave = (math.sin((self.phase + i * 2) * 0.65) + 1) / 2
            height = 7 + wave * 13
            x = start_x + i * (bar_w + gap)
            y = center_y - height / 2
            painter.drawRoundedRect(QRectF(x, y, bar_w, height), 2, 2)

    def _paint_wakeup(self, painter, rect):
        center = rect.center()
        pulse = (math.sin(self.phase * 0.42) + 1) / 2
        outer_radius = 12 + pulse * 3
        painter.setPen(QPen(self._color('ring', 120 - int(pulse * 45)), 2.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(center.x() - outer_radius, center.y() - outer_radius, outer_radius * 2, outer_radius * 2))
        painter.setPen(QPen(self._color('wave', 210), 2.3))
        arc_rect = QRectF(center.x() - 8.5, center.y() - 8.5, 17, 17)
        start = int((self.phase * 18) % 360) * 16
        painter.drawArc(arc_rect, start, 250 * 16)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._color('core')))
        painter.drawEllipse(QRectF(center.x() - 4.2, center.y() - 4.2, 8.4, 8.4))
        painter.setBrush(QBrush(self._color('core2')))
        painter.drawEllipse(QRectF(center.x() - 1.8, center.y() - 1.8, 3.6, 3.6))

    def _paint_thinking(self, painter, rect):
        painter.setPen(Qt.NoPen)
        base_x = rect.center().x() - 10
        y = rect.center().y()
        for i in range(3):
            pulse = (math.sin((self.phase + i * 4) * 0.55) + 1) / 2
            radius = 2.8 + pulse * 1.6
            alpha = 95 + int(pulse * 125)
            painter.setBrush(QBrush(self._color('dot', alpha)))
            cx = base_x + i * 10
            painter.drawEllipse(QRectF(cx - radius, y - radius, radius * 2, radius * 2))

    def _paint_speaking(self, painter, rect):
        center = rect.center()
        pulse = (math.sin(self.phase * 0.45) + 1) / 2
        ring_radius = 8 + pulse * 6
        ring_alpha = 95 - int(pulse * 55)
        painter.setPen(QPen(self._color('ring', ring_alpha), 2.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(center.x() - ring_radius, center.y() - ring_radius, ring_radius * 2, ring_radius * 2))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._color('core')))
        painter.drawEllipse(QRectF(center.x() - 5.5, center.y() - 5.5, 11, 11))
        painter.setBrush(QBrush(self._color('core2')))
        painter.drawEllipse(QRectF(center.x() - 2.8, center.y() - 2.8, 5.6, 5.6))
        painter.setBrush(QBrush(QColor(255, 255, 246, 170)))
        painter.drawEllipse(QRectF(center.x() - 3.5, center.y() - 5.0, 3.2, 3.2))

    def _paint_status_dot(self, painter, rect, color):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        radius = 5
        center = rect.center()
        painter.drawEllipse(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2))


class PetVoicePopup(QFrame):
    """跟随桌宠移动的轻量语音聊天悬浮球。"""

    pause_requested = Signal()
    stop_requested = Signal()

    def __init__(self, x, y, parent=None):
        super().__init__(parent)
        self.anim_group = None
        self.follow_anim = None
        self.follow_target = None
        self.follow_pos = QPointF()
        self.follow_velocity = QPointF()
        self.follow_timer = QTimer(self)
        self.follow_timer.timeout.connect(self._spring_follow_step)
        self.state = 'idle'
        self.anchor_x = x
        self.anchor_y = y
        self.anim_index = 0
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(1.0)
        self.setStyleSheet('''
            QFrame#VoiceCard {
                border: none;
                background: transparent;
            }
            QLabel { border: none; background: transparent; color: #202124; font-family: "Microsoft YaHei UI", "Microsoft YaHei"; }
        ''')
        card = QFrame(self)
        card.setObjectName('VoiceCard')
        root = QHBoxLayout(card)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.anim_widget = VoiceOrbWidget(card)
        self.anim_widget.installEventFilter(self)
        self.anim_widget.width_changed.connect(self._sync_to_current_anchor)
        self.anim_widget.setToolTip('单击暂停/继续语音，双击结束语音聊天')
        root.addWidget(self.anim_widget)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self.adjustSize()
        end_pos = self._pos_from_anchor(x, y)
        self.follow_pos = QPointF(end_pos)
        self.follow_target = end_pos
        self.move(end_pos + QPoint(0, 8))
        self._animate_in(end_pos)
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.pause_requested.emit)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick_animation)
        self.anim_timer.start(120)

    def eventFilter(self, watched, event):
        if watched is self.anim_widget:
            if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                self.click_timer.stop()
                self.stop_requested.emit()
                event.accept()
                return True
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self.click_timer.start(QApplication.doubleClickInterval())
                event.accept()
                return True
            if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _pos_from_anchor(self, x, y):
        side_overlap = 8
        parent = self.parent()
        bounds = parent._current_visible_bounds() if hasattr(parent, '_current_visible_bounds') else None
        if bounds is not None:
            pet_left = parent.x() + parent.label.x() + bounds.left()
            pet_right = parent.x() + parent.label.x() + bounds.right()
            pet_top = parent.y() + parent.label.y() + bounds.top()
            pet_height = bounds.height()
            screen = QApplication.screenAt(QPoint(int(x), int(y))) or QApplication.primaryScreen()
            area = screen.availableGeometry() if screen else None
            prefer_right = area is None or pet_right - side_overlap + self.width() <= area.right()
            px = int(pet_right - side_overlap) if prefer_right else int(pet_left - self.width() + side_overlap)
            py = int(pet_top + pet_height * 0.06)
            return clamp_popup_pos(QPoint(px, py), self.size(), QPoint(int(x), int(y)))
        px = int(x - side_overlap)
        return clamp_popup_pos(QPoint(px, int(y - self.height() / 2)), self.size(), QPoint(int(x), int(y)))

    def move_to_anchor(self, x, y, smooth=True, floaty=False):
        self.anchor_x = x
        self.anchor_y = y
        self.follow_floaty = floaty
        target = self._pos_from_anchor(x, y)
        self.follow_target = target
        if not smooth:
            self.follow_timer.stop()
            if self.follow_anim is not None:
                self.follow_anim.stop()
            self.follow_pos = QPointF(target)
            self.follow_velocity = QPointF()
            self.move(target)
            return
        effect = config.app_config.get('voice_follow_effect', 'spring')
        if effect == 'magnet':
            self.follow_timer.stop()
            self.follow_velocity = QPointF()
            if self.follow_anim is not None:
                self.follow_anim.stop()
            distance = abs(target.x() - self.x()) + abs(target.y() - self.y())
            level = config.app_config.get('voice_follow_level', 'normal')
            magnet_params = {
                'soft': (110, 240, 0.75),
                'normal': (80, 180, 0.55),
                'fast': (55, 130, 0.38),
            }
            min_ms, max_ms, factor = magnet_params.get(level, magnet_params['normal'])
            duration = max(min_ms, min(max_ms, int(distance * factor)))
            self.follow_anim = QPropertyAnimation(self, b'pos', self)
            self.follow_anim.setDuration(duration)
            self.follow_anim.setStartValue(self.pos())
            self.follow_anim.setEndValue(target)
            self.follow_anim.setEasingCurve(QEasingCurve.OutExpo)
            self.follow_anim.finished.connect(lambda: setattr(self, 'follow_pos', QPointF(self.pos())))
            self.follow_anim.start()
            return
        if self.follow_anim is not None:
            self.follow_anim.stop()
        if self.follow_pos.isNull():
            self.follow_pos = QPointF(self.pos())
        if not self.follow_timer.isActive():
            self.follow_timer.start(16)

    def _spring_follow_step(self):
        if self.follow_target is None:
            self.follow_timer.stop()
            return
        target = QPointF(self.follow_target)
        dx = target.x() - self.follow_pos.x()
        dy = target.y() - self.follow_pos.y()
        if abs(dx) < 0.5 and abs(dy) < 0.5 and abs(self.follow_velocity.x()) < 0.5 and abs(self.follow_velocity.y()) < 0.5:
            self.follow_pos = target
            self.follow_velocity = QPointF()
            self.move(self.follow_target)
            self.follow_timer.stop()
            return
        level = config.app_config.get('voice_follow_level', 'normal')
        spring_params = {
            'soft': (0.10, 0.88),
            'normal': (0.16, 0.82),
            'fast': (0.24, 0.76),
        }
        stiffness, damping = spring_params.get(level, spring_params['normal'])
        self.follow_velocity.setX((self.follow_velocity.x() + dx * stiffness) * damping)
        self.follow_velocity.setY((self.follow_velocity.y() + dy * stiffness) * damping)
        self.follow_pos.setX(self.follow_pos.x() + self.follow_velocity.x())
        self.follow_pos.setY(self.follow_pos.y() + self.follow_velocity.y())
        self.move(QPoint(round(self.follow_pos.x()), round(self.follow_pos.y())))

    def _sync_to_current_anchor(self):
        self.adjustSize()
        self.move_to_anchor(self.anchor_x, self.anchor_y, smooth=False)

    def _animate_in(self, end_pos):
        self.show()
        self.raise_()
        self.setWindowOpacity(1.0)
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(160)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.start()

    def update_state(self, state, text=''):
        self.state = state
        self.anim_widget.set_state(state)
        self.anim_widget.set_text(text)
        self._sync_to_current_anchor()
        tips = {
            'listening': '正在听你说话',
            'thinking': '正在思考',
            'speaking': '正在播放回复',
            'wakeup': '等待唤醒词',
            'idle': '语音聊天已结束',
            'error': '语音聊天出错',
        }
        tip = tips.get(state, '语音聊天')
        if text:
            tip = f'{tip}：{str(text)[:30]}'
        self.setToolTip(tip)

    def _tick_animation(self):
        self.anim_index = (self.anim_index + 1) % 24
        self.anim_widget.set_phase(self.anim_index)
        self.anim_widget._tick_ripples()
        self.update()  # 触发 PetVoicePopup.paintEvent 绘制涟漪

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.click_timer.start(QApplication.doubleClickInterval())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.click_timer.stop()
            self.stop_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        ripples = self.anim_widget._ripples
        if not ripples:
            return
        orb = self.anim_widget
        # orb 相对于 popup 的位置
        orb_pos = orb.mapTo(self, QPoint(0, 0))
        cx = orb_pos.x() + orb.width() / 2
        cy = orb_pos.y() + orb.height() / 2
        orb_r = orb.orb_height / 2 - 1
        max_extra = orb_r * 1.6
        ring_color = orb._color('ring')
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(Qt.NoBrush)
        for t in ripples:
            radius = orb_r + t * max_extra
            alpha = int((1.0 - t) ** 2 * 80)
            if alpha <= 0:
                continue
            color = QColor(ring_color.red(), ring_color.green(), ring_color.blue(), alpha)
            pen_w = 2.0 * (1.0 - t * 0.5)
            painter.setPen(QPen(color, pen_w))
            painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
        painter.end()

    def closeEvent(self, event):
        self.click_timer.stop()
        self.anim_timer.stop()
        super().closeEvent(event)


