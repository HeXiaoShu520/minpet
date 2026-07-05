# coding:utf-8
import math
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QEasingCurve, QEvent, QParallelAnimationGroup, QPropertyAnimation, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, QUrl, Signal, Property
from PySide6.QtGui import QAction, QBrush, QColor, QCursor, QDesktopServices, QDragEnterEvent, QDropEvent, QFont, QFontMetrics, QIcon, QKeyEvent, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF

from miniPet import config
from miniPet.animation import AnimationThread
from miniPet.chat_window import ChatWindow
from miniPet.pet_assets import load_pet_profile
from miniPet.realtime_window import RealtimeWindow as DoubaoCallWindow
from miniPet.easter_games import CoinPopup, DicePopup, GachaPopup, MagicConchPopup
from miniPet.fortune_stick import FortuneStickPopup
from miniPet.wooden_fish import WoodenFishPopup


def _clamp_popup_pos(pos, size, anchor, margin=4):
    screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
    if screen is None:
        return pos
    area = screen.availableGeometry()
    x = max(area.left() + margin, min(pos.x(), area.right() - size.width() - margin))
    y = max(area.top() + margin, min(pos.y(), area.bottom() - size.height() - margin))
    return QPoint(x, y)


class ImageAttachmentChip(QFrame):
    remove_requested = Signal(str)

    def __init__(self, key, image, parent=None):
        super().__init__(parent)
        self.key = key
        self.image = image
        self.temp_path = None
        self.setObjectName('ImageAttachmentChip')
        self.setFixedHeight(28)
        self.setStyleSheet('''
            QFrame#ImageAttachmentChip { border: 1px solid rgba(210,216,226,245); border-radius: 8px; background: rgba(255,255,255,245); }
            QLabel { border: none; background: transparent; color: #3a4054; font-family: "Microsoft YaHei UI", "Microsoft YaHei"; font-size: 12px; }
            QPushButton { border: none; border-radius: 7px; background: transparent; color: #7b8496; font-weight: 700; }
            QPushButton:hover { background: #eef6ff; color: #d93026; }
        ''')
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 3, 6, 3)
        row.setSpacing(5)
        thumb = QLabel(self)
        thumb.setFixedSize(18, 18)
        thumb.setStyleSheet('QLabel{border:1px solid rgba(210,216,226,230);border-radius:4px;background:white;}')
        thumb.setPixmap(QPixmap.fromImage(image).scaled(18, 18, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        name = QLabel('image.png', self)
        close_btn = QPushButton('×', self)
        close_btn.setFixedSize(16, 16)
        close_btn.clicked.connect(lambda: self.remove_requested.emit(self.key))
        row.addWidget(thumb)
        row.addWidget(name)
        row.addWidget(close_btn)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.temp_path is None:
                tmp = NamedTemporaryFile(delete=False, suffix='.png')
                tmp.close()
                self.image.save(tmp.name, 'PNG')
                self.temp_path = tmp.name
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.temp_path))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class PetInputPopup(QFrame):
    submitted = Signal(object)

    def __init__(self, x, y, parent=None):
        super().__init__(parent)
        self.anim_group = None
        self.thinking_timer = None
        self.thinking_phase = 0
        self.is_thinking = False
        self.anchor_x = x
        self.anchor_y = y
        self.pending_images = []
        self.pending_image_keys = set()
        self.attachment_chips = {}
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(0.0)
        self.setStyleSheet('''
            QFrame#InputCard {
                border: 1px solid rgba(210,216,226,235);
                border-radius: 17px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(255,255,255,248),stop:1 rgba(246,250,255,242));
            }
            QLabel#InputDot {
                border: none;
                border-radius: 5px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #8fd3ff,stop:1 #c7a8ff);
            }
            QFrame#ImageBadge {
                border: 1px solid rgba(115,170,255,235);
                border-radius: 11px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #eaf4ff,stop:1 #f4efff);
            }
            QLabel#ImageThumb {
                border: 1px solid rgba(255,255,255,230);
                border-radius: 5px;
                background: rgba(255,255,255,220);
            }
            QLabel#ImageCount {
                border: none;
                background: transparent;
                color: #2f66b3;
                font-family: "Microsoft YaHei UI", "Microsoft YaHei";
                font-size: 11px;
                font-weight: 700;
            }
            QLineEdit {
                border: none;
                border-radius: 0;
                padding: 0;
                background: transparent;
                color: #1f2328;
                font-family: "Microsoft YaHei UI", "Microsoft YaHei";
                font-size: 13px;
                selection-background-color: #dbeeff;
            }
            QLineEdit:focus { background: transparent; }
            QLineEdit::placeholder { color: #8b93a7; }
        ''')
        self.card = QFrame(self)
        self.card.setObjectName('InputCard')
        self.card.setMinimumHeight(38)
        root = QVBoxLayout(self.card)
        root.setContentsMargins(14, 7, 14, 7)
        root.setSpacing(6)
        self.attachment_holder = QWidget(self.card)
        self.attachment_row = QHBoxLayout(self.attachment_holder)
        self.attachment_row.setContentsMargins(0, 0, 0, 0)
        self.attachment_row.setSpacing(6)
        self.attachment_holder.hide()
        root.addWidget(self.attachment_holder)
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(7)
        dot = QLabel(self.card)
        dot.setObjectName('InputDot')
        dot.setFixedSize(10, 10)
        input_row.addWidget(dot, 0, Qt.AlignVCenter)
        self.input = QLineEdit(self.card)
        self.input.setAcceptDrops(True)
        self.input.installEventFilter(self)
        self.input.setPlaceholderText('想对宠物说什么？')
        self.input.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.input.setFixedHeight(24)
        self.input.returnPressed.connect(self._submit)
        input_row.addWidget(self.input, 1, Qt.AlignVCenter)
        root.addLayout(input_row)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.card)
        self.setFixedWidth(260)
        self.adjustSize()
        end_pos = _clamp_popup_pos(QPoint(int(x - self.width() / 2), int(y - self.height() - 18)), self.size(), QPoint(int(x), int(y)))
        self.move(end_pos + QPoint(0, 12))
        self._animate_in(end_pos)

    def _animate_in(self, end_pos):
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(180)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        opacity_anim = QPropertyAnimation(self, b'windowOpacity', self)
        opacity_anim.setDuration(160)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.addAnimation(opacity_anim)
        self.anim_group.start()

    def _image_to_data_url(self, image):
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, 'JPEG', 85)
        return 'data:image/jpeg;base64,' + bytes(data.toBase64()).decode('ascii')

    def _add_image(self, image):
        data_url = self._image_to_data_url(image)
        if data_url in self.pending_image_keys:
            return
        self.pending_image_keys.add(data_url)
        self.pending_images.append(data_url)
        chip = ImageAttachmentChip(data_url, image, self.card)
        chip.remove_requested.connect(self._remove_image)
        self.attachment_chips[data_url] = chip
        self.attachment_row.addWidget(chip)
        self.input.setPlaceholderText('可继续输入，回车发送')
        self._refresh_attachment_layout()

    def _remove_image(self, key):
        chip = self.attachment_chips.pop(key, None)
        if chip is not None:
            self.attachment_row.removeWidget(chip)
            chip.deleteLater()
        self.pending_image_keys.discard(key)
        self.pending_images = [image for image in self.pending_images if image != key]
        if not self.pending_images:
            self.input.setPlaceholderText('想对宠物说什么？')
        self._refresh_attachment_layout()

    def _refresh_attachment_layout(self):
        has_images = bool(self.pending_images)
        self.attachment_holder.setVisible(has_images)
        self.card.setFixedHeight(72 if has_images else 38)
        self.adjustSize()
        pos = _clamp_popup_pos(QPoint(int(self.anchor_x - self.width() / 2), int(self.anchor_y - self.height() - 18)), self.size(), QPoint(int(self.anchor_x), int(self.anchor_y)))
        self.move(pos)
        self.card.update()
        self.update()

    def _build_content(self, text):
        if not self.pending_images:
            return text
        blocks = []
        if text:
            blocks.append({'type': 'text', 'text': text})
        for image in self.pending_images:
            blocks.append({'type': 'image', 'src': image, 'alt': '图片'})
        return blocks

    def _submit(self):
        if self.is_thinking:
            return
        text = self.input.text().strip()
        if text or self.pending_images:
            self.submitted.emit(self._build_content(text))
            self.start_thinking()

    def start_thinking(self):
        if self.is_thinking:
            return
        self.is_thinking = True
        self.card.hide()
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet('background: transparent; border: none;')
        self.setFixedSize(96, 96)
        pos = _clamp_popup_pos(QPoint(int(self.anchor_x - self.width() / 2), int(self.anchor_y - self.height() - 20)), self.size(), QPoint(int(self.anchor_x), int(self.anchor_y)))
        size_anim = QPropertyAnimation(self, b'pos', self)
        size_anim.setDuration(220)
        size_anim.setStartValue(self.pos())
        size_anim.setEndValue(pos)
        size_anim.setEasingCurve(QEasingCurve.OutCubic)
        size_anim.start()
        self.shrink_anim = size_anim
        self.thinking_timer = QTimer(self)
        self.thinking_timer.timeout.connect(self._tick_thinking)
        self.thinking_timer.start(33)
        self.update()

    def finish_thinking(self):
        if self.thinking_timer is not None:
            self.thinking_timer.stop()
            self.thinking_timer = None
        self.close()

    def _tick_thinking(self):
        self.thinking_phase = (self.thinking_phase + 1) % 360
        self.update()

    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.KeyPress and event.key() == Qt.Key_V and event.modifiers() & Qt.ControlModifier:
            image = QApplication.clipboard().image()
            if not image.isNull():
                self._add_image(image)
                return True
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasImage() or event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasImage():
            self._add_image(mime.imageData())
            event.acceptProposedAction()
            return
        for url in mime.urls():
            pixmap = QPixmap(url.toLocalFile())
            if not pixmap.isNull():
                self._add_image(pixmap.toImage())
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def paintEvent(self, event):
        if not self.is_thinking:
            return super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        phase = self.thinking_phase
        center = QPointF(self.width() / 2, self.height() / 2)
        pulse = (math.sin(math.radians(phase * 3)) + 1) / 2
        painter.setPen(Qt.NoPen)
        for i, alpha in enumerate((52, 34, 18)):
            painter.setBrush(QColor(70, 145, 255, int(alpha + pulse * 18)))
            painter.drawEllipse(center, int(24 + i * 7 + pulse * 5), int(24 + i * 7 + pulse * 5))
        grad = QRadialGradient(center, 27)
        grad.setColorAt(0, QColor(255, 255, 255, 252))
        grad.setColorAt(0.38, QColor(142, 220, 255, 245))
        grad.setColorAt(0.76, QColor(104, 136, 255, 240))
        grad.setColorAt(1, QColor(132, 92, 255, 230))
        painter.setBrush(grad)
        painter.drawEllipse(center, 25, 25)
        painter.setBrush(QColor(255, 255, 255, 150))
        painter.drawEllipse(QPointF(center.x() - 8, center.y() - 10), 6, 6)
        for i, color in enumerate((QColor(255, 255, 255, 235), QColor(205, 245, 255, 225), QColor(255, 215, 245, 225))):
            angle = math.radians(phase * 4 + i * 120)
            radius = 16 + 3 * math.sin(math.radians(phase * 5 + i * 70))
            dot = QPointF(center.x() + math.cos(angle) * radius, center.y() + math.sin(angle) * radius)
            painter.setBrush(color)
            painter.drawEllipse(dot, 3.5, 3.5)

    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow() and not self.is_thinking:
            self.close()
        super().changeEvent(event)

    def closeEvent(self, event):
        if self.thinking_timer is not None:
            self.thinking_timer.stop()
            self.thinking_timer = None
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)


VOICE_ORB_PALETTES = {
    'jade': {'bg': (244, 255, 249, 246), 'border': (125, 195, 165, 238), 'wave': (72, 172, 145, 225), 'dot': (98, 175, 150), 'ring': (84, 190, 160), 'core': (116, 210, 178, 230), 'core2': (225, 255, 240, 230), 'text': (30, 70, 58, 235)},
    'mint': {'bg': (245, 243, 255, 245), 'border': (168, 158, 255, 235), 'wave': (116, 111, 255, 220), 'dot': (132, 105, 255), 'ring': (50, 210, 190), 'core': (70, 160, 255, 230), 'core2': (92, 238, 202, 210), 'text': (40, 44, 52, 230)},
    'violet': {'bg': (248, 244, 255, 245), 'border': (183, 150, 255, 235), 'wave': (143, 111, 255, 225), 'dot': (155, 105, 255), 'ring': (132, 115, 255), 'core': (130, 105, 255, 230), 'core2': (210, 150, 255, 210), 'text': (45, 38, 62, 230)},
    'sakura': {'bg': (255, 246, 250, 245), 'border': (255, 170, 205, 235), 'wave': (255, 125, 175, 225), 'dot': (235, 120, 180), 'ring': (255, 145, 160), 'core': (255, 125, 175, 230), 'core2': (255, 200, 220, 220), 'text': (58, 35, 45, 230)},
    'sunset': {'bg': (255, 249, 240, 245), 'border': (255, 185, 105, 235), 'wave': (255, 165, 80, 225), 'dot': (240, 150, 75), 'ring': (255, 130, 90), 'core': (255, 145, 70, 230), 'core2': (255, 215, 120, 220), 'text': (58, 40, 28, 230)},
    'mono': {'bg': (246, 247, 249, 245), 'border': (185, 192, 205, 235), 'wave': (110, 120, 140, 225), 'dot': (120, 130, 150), 'ring': (105, 155, 160), 'core': (120, 135, 155, 230), 'core2': (180, 190, 200, 220), 'text': (38, 42, 50, 230)},
}


class VoiceOrbWidget(QWidget):
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
        # listening/speaking 状态每隔一定 tick 生成新涟漪，最多同时 3 个
        if self.state in ('listening', 'speaking'):
            self._ripple_tick += 1
            interval = 22 if self.state == 'listening' else 18
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

    def _pos_from_anchor(self, x, y):
        side_gap = 8
        if x < self.parent().x() + self.parent().width() / 2:
            px = int(x - self.width() - side_gap)
        else:
            px = int(x + side_gap)
        return _clamp_popup_pos(QPoint(px, int(y - self.height() / 2)), self.size(), QPoint(int(x), int(y)))

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


class PetDropIntentPopup(QFrame):
    intent_selected = Signal(dict, str)

    def __init__(self, drop_payload, x, y, parent=None):
        super().__init__(parent)
        self.drop_payload = drop_payload
        self.anim_group = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(0.0)
        self.setStyleSheet('''
            QFrame#DropCard {
                border: 1px solid rgba(210, 216, 226, 220);
                border-radius: 16px;
                background: rgba(255, 255, 255, 248);
            }
            QLabel { border: none; background: transparent; color: #1f2328; font-family: "Microsoft YaHei UI", "Microsoft YaHei"; }
            QLabel#DropTitle { font-size: 14px; font-weight: 700; }
            QLabel#DropDesc { color: #68707d; font-size: 12px; }
            QPushButton { border: none; border-radius: 12px; background: #f4f7fb; color: #1f2328; padding: 7px 10px; }
            QPushButton:hover { background: #e8f1ff; }
            QPushButton#PrimaryButton { background: #1677ff; color: white; }
            QPushButton#PrimaryButton:hover { background: #4096ff; }
            QPushButton#QuietButton { background: transparent; color: #8b8f99; }
            QPushButton#QuietButton:hover { background: #f4f4f5; color: #4b5563; }
        ''')
        card = QFrame(self)
        card.setObjectName('DropCard')
        root = QVBoxLayout(card)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        title = QLabel(self._title_text(), card)
        title.setObjectName('DropTitle')
        root.addWidget(title)

        desc = QLabel(self._description_text(), card)
        desc.setObjectName('DropDesc')
        desc.setWordWrap(True)
        desc.setMaximumWidth(320)
        root.addWidget(desc)

        first_row = QHBoxLayout()
        first_row.setSpacing(6)
        for intent, label, primary in (
            ('summarize', '总结', True),
            ('create_task', '生成待办', False),
            ('draft_reply', '起草回复', False),
        ):
            btn = QPushButton(label, card)
            if primary:
                btn.setObjectName('PrimaryButton')
            btn.clicked.connect(lambda checked=False, i=intent: self._select(i))
            first_row.addWidget(btn)
        root.addLayout(first_row)

        second_row = QHBoxLayout()
        second_row.setSpacing(6)
        for intent, label in (
            ('send_to_lark', '发到飞书'),
            ('ask', '问它怎么处理'),
            ('cancel', '取消'),
        ):
            btn = QPushButton(label, card)
            if intent == 'cancel':
                btn.setObjectName('QuietButton')
            btn.clicked.connect(lambda checked=False, i=intent: self._select(i))
            second_row.addWidget(btn)
        root.addLayout(second_row)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self.adjustSize()
        end_pos = _clamp_popup_pos(QPoint(int(x - self.width() / 2), int(y - self.height() - 18)), self.size(), QPoint(int(x), int(y)))
        self.move(end_pos + QPoint(0, 10))
        self._animate_in(end_pos)
        QTimer.singleShot(18000, self.close)

    def _title_text(self):
        kind = self.drop_payload.get('kind')
        count = len(self.drop_payload.get('items') or [])
        if kind == 'file':
            return '收到 %d 个文件' % count
        if kind == 'url':
            return '收到 %d 个链接' % count
        if kind == 'image':
            return '收到图片'
        return '收到一段文字'

    def _description_text(self):
        preview = self.drop_payload.get('preview') or ''
        if len(preview) > 90:
            preview = preview[:90] + '…'
        return preview or '要我怎么处理这个内容？'

    def _animate_in(self, end_pos):
        self.show()
        self.raise_()
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(160)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        opacity_anim = QPropertyAnimation(self, b'windowOpacity', self)
        opacity_anim.setDuration(140)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.addAnimation(opacity_anim)
        self.anim_group.start()

    def _select(self, intent):
        if intent != 'cancel':
            self.intent_selected.emit(self.drop_payload, intent)
        self.close()

    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            self.close()
        super().changeEvent(event)


class EasterActionButton(QPushButton):
    def __init__(self, icon_text, label, subtitle, parent=None):
        super().__init__(parent)
        self.icon_text = icon_text
        self.label = label
        self.subtitle = subtitle
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(140, 70)
        self.setText('')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        if self.isDown():
            bg = QColor(246, 217, 158, 245)
            border = QColor(204, 150, 72, 180)
        elif self.underMouse():
            bg = QColor(255, 236, 194, 250)
            border = QColor(218, 157, 65, 185)
        else:
            bg = QColor(255, 247, 226, 240)
            border = QColor(235, 204, 144, 125)
        painter.setPen(QPen(border, 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 18, 18)

        icon_rect = QRectF(rect.left() + 10, rect.top() + 14, 40, 40)
        painter.setBrush(QColor(255, 255, 255, 205))
        painter.setPen(QPen(QColor(232, 191, 112, 120), 1))
        painter.drawEllipse(icon_rect)

        if '/' in self.icon_text or '\\' in self.icon_text or '.png' in self.icon_text.lower():
            from pathlib import Path
            icon_path = Path(self.icon_text) if not self.icon_text.startswith('res/') else config.RES_DIR / self.icon_text.replace('res/', '')
            if icon_path.exists():
                pixmap = QPixmap(str(icon_path))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(int(icon_rect.width()), int(icon_rect.height()), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    x_offset = (icon_rect.width() - scaled.width()) / 2
                    y_offset = (icon_rect.height() - scaled.height()) / 2
                    painter.drawPixmap(int(icon_rect.x() + x_offset), int(icon_rect.y() + y_offset), scaled)
        else:
            font = QFont('Microsoft YaHei UI', 19)
            painter.setFont(font)
            painter.setPen(QColor(92, 59, 24))
            painter.drawText(icon_rect, Qt.AlignCenter, self.icon_text)

        font = QFont('Microsoft YaHei UI', 10, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(82, 52, 22))
        painter.drawText(QRectF(rect.left() + 58, rect.top() + 13, rect.width() - 64, 22), Qt.AlignLeft | Qt.AlignVCenter, self.label)
        font = QFont('Microsoft YaHei UI', 8)
        painter.setFont(font)
        painter.setPen(QColor(122, 82, 38, 185))
        painter.drawText(QRectF(rect.left() + 58, rect.top() + 36, rect.width() - 64, 20), Qt.AlignLeft | Qt.AlignVCenter, self.subtitle)


class PetEasterMenu(QFrame):
    def __init__(self, x, y, actions, parent=None):
        super().__init__(parent)
        self.anim_group = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(0.0)
        self.setFixedWidth(346)
        self.setStyleSheet('''
            QFrame#EasterCard {
                border: 1px solid rgba(218, 190, 132, 230);
                border-radius: 24px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 251, 239, 252), stop:1 rgba(255, 240, 210, 250));
            }
            QLabel { border: none; background: transparent; color: #5c3b18; font-family: "Microsoft YaHei UI", "Microsoft YaHei"; }
            QLabel#EasterTitle { font-size: 17px; font-weight: 800; }
            QLabel#EasterSubTitle { font-size: 10px; color: rgba(116, 78, 36, 190); }
        ''')
        card = QFrame(self)
        card.setObjectName('EasterCard')
        root = QVBoxLayout(card)
        root.setContentsMargins(18, 15, 18, 18)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        mark = QLabel('✦', card)
        mark.setFixedWidth(18)
        mark.setStyleSheet('font-size: 16px; color: #c98a2e; font-weight: 900;')
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title = QLabel('彩蛋小铺', card)
        title.setObjectName('EasterTitle')
        subtitle = QLabel('摸鱼、占卜和一点点玄学', card)
        subtitle.setObjectName('EasterSubTitle')
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_row.addWidget(mark)
        title_row.addLayout(title_col)
        title_row.addStretch(1)
        root.addLayout(title_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        for index, action in enumerate(actions):
            icon_text, label, subtitle, callback = action
            btn = EasterActionButton(icon_text, label, subtitle, card)
            btn.clicked.connect(lambda checked=False, cb=callback: self._trigger(cb))
            grid.addWidget(btn, index // 2, index % 2)
        root.addLayout(grid)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self.adjustSize()
        pos = _clamp_popup_pos(QPoint(int(x - self.width() / 2), int(y - self.height() - 24)), self.size(), QPoint(int(x), int(y)))
        self.move(pos + QPoint(0, 8))
        self._animate_in(pos)
        QTimer.singleShot(8000, self.close)

    def _trigger(self, callback):
        self.close()
        callback()

    def _animate_in(self, end_pos):
        self.show()
        self.raise_()
        self.activateWindow()
        QApplication.instance().installEventFilter(self)
        opacity_anim = QPropertyAnimation(self, b'windowOpacity', self)
        opacity_anim.setDuration(140)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(160)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(opacity_anim)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.start()

    def leaveEvent(self, event):
        super().leaveEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            pos = QCursor.pos()
            if not self.geometry().contains(pos):
                self.close()
        return super().eventFilter(obj, event)

    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            self.close()
        super().changeEvent(event)

    def closeEvent(self, event):
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)


class PetQuickMenu(QFrame):
    def __init__(self, x, top_y, bottom_y, on_settings, on_chat, on_voice_chat, on_quit, on_share_screen, share_screen_active=False, voice_chat_active=False, parent=None):
        super().__init__(parent)
        self.anim_group = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(0.0)
        self.setStyleSheet('''
            QFrame#QuickMenuCard {
                border: 1px solid rgba(210,216,226,235);
                border-radius: 17px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(255,255,255,248),stop:1 rgba(246,250,255,242));
            }
            QPushButton {
                border: none;
                border-radius: 10px;
                background: transparent;
                padding: 5px;
            }
            QPushButton:hover { background: #eef6ff; }
            QPushButton:pressed { background: #dbeeff; }
            QPushButton#ShareScreenBtn:checked { background: #dbeeff; }
            QPushButton#VoiceChatBtn { background: #fee; border: 1px solid #fcc; }
            QPushButton#VoiceChatBtn:hover { background: #fdd; }
            QPushButton#VoiceChatBtn:checked { background: #dbeeff; border: none; }
            QPushButton#VoiceChatBtn:checked:hover { background: #c8e5ff; }
        ''')
        card = QFrame(self)
        card.setObjectName('QuickMenuCard')
        row = QHBoxLayout(card)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(4)
        settings_btn = QPushButton(card)
        chat_btn = QPushButton(card)
        voice_chat_btn = QPushButton(card)
        voice_chat_btn.setObjectName('VoiceChatBtn')
        voice_chat_btn.setCheckable(True)
        share_screen_btn = QPushButton(card)
        share_screen_btn.setObjectName('ShareScreenBtn')
        share_screen_btn.setCheckable(True)
        quit_btn = QPushButton(card)
        settings_btn.setIcon(FIF.SETTING.icon())
        chat_btn.setIcon(QIcon(str(config.RES_DIR / 'icons' / 'Dialogue_icon.png')))
        voice_chat_btn.setIcon(FIF.MICROPHONE.icon())
        share_screen_btn.setIcon(QIcon(str(config.RES_DIR / 'icons' / 'system' / 'screen_share.svg')))
        quit_btn.setIcon(FIF.POWER_BUTTON.icon())
        for btn in (settings_btn, chat_btn, share_screen_btn, voice_chat_btn, quit_btn):
            btn.setIconSize(QSize(18, 18))
            btn.setFixedSize(30, 30)
        settings_btn.setToolTip('设置')
        chat_btn.setToolTip('聊天')
        voice_chat_btn.setToolTip('语音聊天')
        share_screen_btn.setToolTip('共享屏幕（语音时附带截图）')
        share_screen_btn.setChecked(share_screen_active)
        voice_chat_btn.setChecked(voice_chat_active)
        quit_btn.setToolTip('退出')

        def update_voice_chat_icon(checked):
            if checked:
                voice_chat_btn.setIcon(FIF.MICROPHONE.icon())
            else:
                voice_chat_btn.setIcon(QIcon(str(config.RES_DIR / 'icons' / 'system' / 'microphone_off.png')))

        voice_chat_btn.toggled.connect(update_voice_chat_icon)
        update_voice_chat_icon(voice_chat_active)

        settings_btn.clicked.connect(lambda: self._trigger(on_settings))
        chat_btn.clicked.connect(lambda: self._trigger(on_chat))
        voice_chat_btn.clicked.connect(lambda checked: on_voice_chat(checked))
        share_screen_btn.clicked.connect(lambda checked: on_share_screen(checked))
        quit_btn.clicked.connect(lambda: self._trigger(on_quit))
        row.addWidget(settings_btn)
        row.addWidget(chat_btn)
        row.addWidget(share_screen_btn)
        row.addWidget(voice_chat_btn)
        row.addWidget(quit_btn)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self.adjustSize()
        screen = QApplication.screenAt(QPoint(int(x), int(bottom_y))) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        gap = 6
        target_y = int(top_y - self.height() - gap)
        start_offset = QPoint(0, 6)
        target_x = int(x - self.width() / 2)
        if area:
            target_x = max(area.left() + 4, min(target_x, area.right() - self.width() - 4))
            target_y = max(area.top() + 4, min(target_y, area.bottom() - self.height() - 4))
        end_pos = QPoint(target_x, target_y)
        self.move(end_pos + start_offset)
        self._animate_in(end_pos)
        QTimer.singleShot(4500, self.close)

    def _trigger(self, callback):
        self.close()
        callback()

    def leaveEvent(self, event):
        super().leaveEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            self.close()
        super().changeEvent(event)

    def _animate_in(self, end_pos):
        self.show()
        self.raise_()
        self.activateWindow()
        pos_anim = QPropertyAnimation(self, b'pos', self)
        pos_anim.setDuration(140)
        pos_anim.setStartValue(self.pos())
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        opacity_anim = QPropertyAnimation(self, b'windowOpacity', self)
        opacity_anim.setDuration(120)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(pos_anim)
        self.anim_group.addAnimation(opacity_anim)
        self.anim_group.start()


class DesktopPet(QWidget):
    show_settings = Signal()
    bubble_requested = Signal(str, int, int, int)
    notification_requested = Signal(str, str)
    smart_bubble_requested = Signal(dict, int, int)
    chat_prompt_submitted = Signal(object)
    drop_intent_submitted = Signal(dict, str)
    chat_requested = Signal()
    voice_chat_requested = Signal()
    voice_pause_requested = Signal()
    share_screen_requested = Signal(bool)
    doubao_call_requested = Signal()
    pet_changed = Signal(str)
    quit_requested = Signal()

    def __init__(self, screens, parent=None):
        super().__init__(parent)
        self.screens = screens
        self.current_screen = screens[0].availableGeometry()
        config.screens = screens
        config.current_screen = screens[0]
        self.profile = None
        self.anim_thread = None
        self.chat_window = None
        self.doubao_call_window = None
        self.tray = None
        self.context_menu = None
        self.input_popup = None
        self.voice_popup = None
        self.quick_menu = None
        self._share_screen_active = False
        self._voice_chat_active = False
        self.drop_popup = None
        self.wooden_fish_popup = None
        self.fortune_stick_popup = None
        self.easter_menu = None
        self.magic_conch_popup = None
        self.gacha_popup = None
        self.dice_popup = None
        self.coin_popup = None
        self.right_click_menu_timer = QTimer(self)
        self.right_click_menu_timer.setSingleShot(True)
        self.right_click_menu_timer.timeout.connect(self.show_quick_menu)
        self.suppress_next_right_release_menu = False
        self.current_frame_size = QSize(0, 0)
        self.visible_bounds = QRect()
        self.is_dragging = False
        self.left_pressed = False
        self.was_dragging = False
        self.mouse_drag_pos = QPoint(0, 0)
        self.press_global_pos = QPoint(0, 0)
        self.last_mouse = []
        self.fall_timer = QTimer(self)
        self.fall_timer.timeout.connect(self._fall_step)
        self.hover_menu_armed = False
        self.hover_inside_visible = False
        self.hover_mouse_trace = []
        self.hover_trace_timer = QTimer(self)
        self.hover_trace_timer.timeout.connect(self._sample_hover_mouse_trace)
        self.hover_trace_timer.start(50)
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self._show_quick_menu_from_hover)
        self._init_window()
        self._init_ui()
        self.load_pet(config.app_config.get('default_pet') or (config.get_pet_list()[0] if config.get_pet_list() else ''))
        self.show()
        self._setup_tray()

    def _init_window(self):
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
        if config.app_config.get('on_top', True):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

    def _init_ui(self):
        self.label = QLabel(self)
        self.label.setMouseTracking(True)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label.setScaledContents(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label, 0, Qt.AlignBottom | Qt.AlignHCenter)

    def load_pet(self, pet_name):
        if not pet_name:
            return
        self._stop_animation()
        self.profile = load_pet_profile(pet_name)
        config.current_pet = pet_name
        config.app_config['default_pet'] = pet_name
        config.save_app_config()
        self.setWindowTitle('miniPet - ' + pet_name)
        self._set_image(self.profile.default.images[0], self.profile.default.anchor)
        self._reset_size(keep_position=False)
        self._start_animation()
        self._setup_tray()
        self.pet_changed.emit(pet_name)

    def _start_animation(self):
        self.anim_thread = AnimationThread(self.profile, self)
        self.anim_thread.worker.image_changed.connect(self._set_image)
        self.anim_thread.worker.move_requested.connect(self._move_by)
        self.anim_thread.worker.finished.connect(self._resume_random_animation)
        self.anim_thread.start()

    def _stop_animation(self):
        if self.anim_thread:
            self.anim_thread.stop()
            self.anim_thread = None

    def _set_image(self, pixmap, anchor, act=None):
        config.current_image = pixmap
        config.previous_anchor = config.current_anchor
        config.current_anchor = list(anchor or [0, 0])
        scale = float(config.app_config.get('scale', 1.0))
        width = max(1, int(pixmap.width() * scale))
        height = max(1, int(pixmap.height() * scale))
        self.current_frame_size = QSize(pixmap.width(), pixmap.height())
        if act is not None:
            self.visible_bounds = act.get_bounds(pixmap, scale)
        else:
            self.visible_bounds = QRect(0, 0, width, height)
        self.label.setFixedSize(width, height)
        self.label.setPixmap(pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._reset_size(keep_position=True, set_image=False)

    def _reset_size(self, keep_position=True, set_image=True):
        if not self.profile:
            return
        old_pos = self.pos()
        scale = float(config.app_config.get('scale', 1.0))
        self.setFixedSize(max(1, int(self.profile.width * scale)), max(1, int(self.profile.height * scale)))
        if keep_position:
            self._set_current_screen_from_point(self._pet_reference_point(old_pos.x(), old_pos.y()))
            self.move(self._limit_position(old_pos.x(), old_pos.y()))
        else:
            self.floor_y = self.current_screen.bottom() - self.height() + 1
            self.move(self.current_screen.center().x() - self.width() // 2, self.floor_y)
        if set_image and config.current_image:
            self._set_image(config.current_image, config.current_anchor)
        self._sync_voice_popup_position()

    def _screen_at_point(self, point):
        screen = QApplication.screenAt(point)
        if screen is not None:
            return screen
        screen = self.screen()
        if screen is not None:
            return screen
        screen = QApplication.primaryScreen()
        if screen is not None:
            return screen
        return self.screens[0] if self.screens else None

    def _pet_reference_point(self, x=None, y=None):
        px = self.x() if x is None else int(x)
        py = self.y() if y is None else int(y)
        return QPoint(px + self.width() // 2, py + self.height())

    def _set_current_screen_from_point(self, point):
        screen = self._screen_at_point(point)
        if screen is not None:
            config.current_screen = screen
            self.current_screen = screen.availableGeometry()
        self.floor_y = self.current_screen.bottom() - self.height() + 1
        return self.current_screen

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if not self.tray:
            self.tray = QSystemTrayIcon(QIcon(str(config.avatar_path('pet'))), self)
        self.tray.setContextMenu(self._build_menu(include_actions=True))
        self.tray.show()

    def _build_menu(self, include_actions=False):
        self.context_menu = QMenu(self)
        menu = self.context_menu
        icon_dir = config.RES_DIR / 'icons'
        system_icon_dir = icon_dir / 'system'
        if config.current_pet:
            title = QAction(QIcon(str(system_icon_dir / 'minipet.svg')), config.current_pet, menu)
            title.setEnabled(False)
            menu.addAction(title)
            menu.addSeparator()

        system_action = QAction(QIcon(str(icon_dir / 'SystemPanel.png')), '设置', menu)
        system_action.triggered.connect(self.show_settings.emit)
        chat_action = QAction(QIcon(str(icon_dir / 'Dialogue_icon.png')), '聊天', menu)
        chat_action.triggered.connect(self.chat_requested.emit)
        voice_chat_action = QAction(FIF.CHAT.icon(), '语音聊天', menu)
        voice_chat_action.triggered.connect(self.voice_chat_requested.emit)
        menu.addAction(system_action)
        menu.addAction(chat_action)
        menu.addAction(voice_chat_action)
        menu.addSeparator()

        if include_actions:
            act_menu = menu.addMenu(QIcon(str(icon_dir / 'jump.svg')), '动作')
            if self.profile:
                for name in self.profile.acts.keys():
                    action = QAction(QIcon(str(icon_dir / 'jump.svg')), name, act_menu)
                    action.triggered.connect(lambda checked=False, n=name: self.play_action(n))
                    act_menu.addAction(action)
            if not act_menu.actions():
                empty_action = QAction('无可用动作', act_menu)
                empty_action.setEnabled(False)
                act_menu.addAction(empty_action)

        role_menu = menu.addMenu(QIcon(str(system_icon_dir / 'character.svg')), '角色切换')
        for pet in config.get_pet_list():
            action = QAction(QIcon(str(system_icon_dir / 'character.svg')), pet, role_menu)
            action.setCheckable(True)
            action.setChecked(pet == config.current_pet)
            action.triggered.connect(lambda checked=False, p=pet: self.load_pet(p))
            role_menu.addAction(action)
        quit_action = QAction(FIF.POWER_BUTTON.icon(), '退出', menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        return menu

    def enterEvent(self, event):
        self._arm_hover_menu_from_cursor()
        super().enterEvent(event)

    def _sample_hover_mouse_trace(self):
        pos = QCursor.pos()
        now = time.monotonic()
        self.hover_mouse_trace.append((now, pos))
        self.hover_mouse_trace = [(t, p) for t, p in self.hover_mouse_trace if now - t <= 0.45]

    def _is_horizontal_hover_entry(self):
        if len(self.hover_mouse_trace) < 2:
            return False
        now = time.monotonic()
        points = [(t, p) for t, p in self.hover_mouse_trace if now - t <= 0.35]
        if len(points) < 2:
            return False
        start = points[0][1]
        end = points[-1][1]
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        adx = abs(dx)
        ady = abs(dy)
        return adx >= 18 and adx >= ady * 1.6

    def _arm_hover_menu_from_cursor(self):
        local = self.mapFromGlobal(QCursor.pos()) - self.label.pos()
        bounds = self._current_visible_bounds()
        inside = bounds.contains(local)
        if not inside:
            self.hover_inside_visible = False
            self.hover_menu_armed = False
            self.hover_timer.stop()
            return
        if self.hover_inside_visible:
            return
        self.hover_inside_visible = True
        if not self._is_horizontal_hover_entry():
            self.hover_menu_armed = False
            self.hover_timer.stop()
            return
        self.hover_menu_armed = True
        self.hover_timer.start(600)

    def leaveEvent(self, event):
        self.hover_inside_visible = False
        self.hover_menu_armed = False
        self.hover_timer.stop()
        QTimer.singleShot(220, self._close_quick_menu_if_mouse_away)
        super().leaveEvent(event)

    def _show_quick_menu_from_hover(self):
        if not self.hover_menu_armed:
            return
        self.hover_menu_armed = False
        self.show_quick_menu()

    def _close_quick_menu_if_mouse_away(self):
        if self.quick_menu is None:
            return
        cursor = QCursor.pos()
        if self.geometry().contains(cursor):
            return
        if self.quick_menu.geometry().contains(cursor):
            return
        self.quick_menu.close()

    def contextMenuEvent(self, event):
        event.accept()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._drop_payload_from_mime(event.mimeData()) is not None:
            event.acceptProposedAction()
            self.hover_menu_armed = False
            self.hover_timer.stop()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        payload = self._drop_payload_from_mime(event.mimeData())
        if payload is None:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        self._show_drop_popup(payload)

    def _drop_payload_from_mime(self, mime):
        if mime is None:
            return None
        if mime.hasUrls():
            items = []
            has_file = False
            for url in mime.urls():
                item = self._drop_item_from_url(url)
                if item:
                    has_file = has_file or item.get('kind') == 'file'
                    items.append(item)
            if items:
                kind = 'file' if has_file else 'url'
                return {
                    'kind': kind,
                    'items': items,
                    'preview': self._drop_preview(items),
                }
        if mime.hasImage():
            return {
                'kind': 'image',
                'items': [{'kind': 'image', 'name': '拖入的图片'}],
                'preview': '一张图片，可以识别文字、总结或发到飞书。',
            }
        if mime.hasText():
            text = (mime.text() or '').strip()
            if text:
                kind = 'url' if self._looks_like_url(text) else 'text'
                return {
                    'kind': kind,
                    'items': [{'kind': kind, 'text': text}],
                    'preview': text,
                }
        return None

    def _drop_item_from_url(self, url: QUrl):
        if url.isLocalFile():
            path = url.toLocalFile()
            name = Path(path).name or path
            return {'kind': 'file', 'path': path, 'name': name}
        text = url.toString()
        if text:
            return {'kind': 'url', 'url': text, 'name': text}
        return None

    def _looks_like_url(self, text):
        lower = text.lower()
        return lower.startswith(('http://', 'https://', 'file://')) or '://' in lower

    def _drop_preview(self, items):
        names = []
        for item in items[:3]:
            names.append(item.get('name') or item.get('url') or item.get('text') or item.get('kind'))
        text = '、'.join(names)
        if len(items) > 3:
            text += ' 等 %d 项' % len(items)
        return text

    def _show_drop_popup(self, payload):
        if self.drop_popup is not None:
            self.drop_popup.close()
        x, y = self.bubble_anchor()
        self.drop_popup = PetDropIntentPopup(payload, x, y, self)
        self.drop_popup.intent_selected.connect(self.drop_intent_submitted.emit)
        self.drop_popup.destroyed.connect(lambda: setattr(self, 'drop_popup', None))
        self.pat()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.hover_inside_visible = True
            self.hover_menu_armed = False
            self.hover_timer.stop()
            self.left_pressed = True
            self.was_dragging = False
            self.mouse_drag_pos = event.globalPos() - self.pos()
            self.press_global_pos = event.globalPos()
            self.last_mouse = [QCursor.pos()]
            event.accept()
        elif event.button() == Qt.RightButton:
            self.hover_inside_visible = True
            self.hover_menu_armed = False
            self.hover_timer.stop()
            self.right_click_menu_timer.stop()
            event.accept()

    def mouseMoveEvent(self, event):
        if not self.left_pressed:
            if self.quick_menu is None:
                self._arm_hover_menu_from_cursor()
            return
        if not self.is_dragging and (event.globalPos() - self.press_global_pos).manhattanLength() >= 6:
            self.is_dragging = True
            self.was_dragging = True
            self.hover_inside_visible = True
            self.hover_menu_armed = False
            self.hover_timer.stop()
            if self.quick_menu is not None:
                self.quick_menu.close()
            if self.easter_menu is not None:
                self.easter_menu.close()
            if self.input_popup is not None:
                self.input_popup.close()
            self.right_click_menu_timer.stop()
            self.fall_timer.stop()
            if self.anim_thread:
                self.anim_thread.worker.play([self.profile.drag])
        if self.is_dragging:
            self.move(event.globalPos() - self.mouse_drag_pos)
            self._sync_voice_popup_position()
            self.last_mouse.append(QCursor.pos())
            self.last_mouse = self.last_mouse[-4:]
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            if self.suppress_next_right_release_menu:
                self.suppress_next_right_release_menu = False
            self.right_click_menu_timer.stop()
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            return
        self.left_pressed = False
        if not self.was_dragging:
            event.accept()
            return
        self.is_dragging = False
        if len(self.last_mouse) >= 2:
            p1 = self.last_mouse[-1]
            p0 = self.last_mouse[0]
            config.drag_speed_x = (p1.x() - p0.x()) / max(1, len(self.last_mouse))
            config.drag_speed_y = (p1.y() - p0.y()) / max(1, len(self.last_mouse))
        self._set_current_screen_from_point(self._pet_reference_point())
        if config.app_config.get('allow_drop', True):
            config.on_floor = False
            if self.anim_thread:
                self.anim_thread.worker.play([self.profile.fall])
            self.fall_timer.start(16)
        else:
            self.move(self._limit_position(self.x(), self.y()))
            self._resume_random_animation()
        event.accept()

    def show_easter_menu(self):
        if self.quick_menu is not None:
            self.quick_menu.close()
        if self.easter_menu is not None and self.easter_menu.isVisible():
            self.easter_menu.raise_()
            return
        x, y = self.bubble_anchor()
        actions = [
            ('🐚', '魔法海螺', '问一个是/否问题', self.show_magic_conch),
            ('🎋', '今日求签', '摇一支今日运势', self.show_fortune),
            ('🎲', '摇骰子', '交给随机数决定', self.show_dice),
            ('res/icons/easter/coin.png', '抛硬币', '正反之间做选择', self.show_coin),
            ('📞', '豆包通话', '与豆包实时语音对话', self.show_doubao_call),
            ('🐟', '电子木鱼', '功德 +1，Bug -1', self.toggle_wooden_fish),
            ('🎁', '桌宠扭蛋', '胶囊里有今日惊喜', self.show_gacha),
        ]
        self.easter_menu = PetEasterMenu(x, y, actions, self)
        self.easter_menu.destroyed.connect(lambda: setattr(self, 'easter_menu', None))

    def _show_game_popup(self, attr_name, popup_class):
        current = getattr(self, attr_name)
        if current is not None and current.isVisible():
            current.raise_()
            return
        x, y = self.bubble_anchor()
        popup = popup_class(x, y, self)
        popup.destroyed.connect(lambda: setattr(self, attr_name, None))
        setattr(self, attr_name, popup)
        self.pat()

    def show_magic_conch(self):
        self._show_game_popup('magic_conch_popup', MagicConchPopup)

    def show_gacha(self):
        self._show_game_popup('gacha_popup', GachaPopup)

    def show_dice(self):
        self._show_game_popup('dice_popup', DicePopup)

    def show_coin(self):
        self._show_game_popup('coin_popup', CoinPopup)

    def show_fortune(self):
        if self.fortune_stick_popup is not None and self.fortune_stick_popup.isVisible():
            self.fortune_stick_popup.raise_()
            return
        x, y = self.bubble_anchor()
        self.fortune_stick_popup = FortuneStickPopup(x, y, self)
        self.fortune_stick_popup.finished.connect(self._show_fortune_result)
        self.fortune_stick_popup.destroyed.connect(lambda: setattr(self, 'fortune_stick_popup', None))
        self.pat()

    def _show_fortune_result(self, level, text):
        x, y = self.bubble_anchor()
        self.bubble_requested.emit(f'【{level}】{text}', x, y, 7000)

    def toggle_wooden_fish(self):
        if self.wooden_fish_popup is not None and self.wooden_fish_popup.isVisible():
            self.wooden_fish_popup.close()
            self.wooden_fish_popup = None
            return
        x, y = self.bubble_anchor()
        self.wooden_fish_popup = WoodenFishPopup(x, y, self)
        self.wooden_fish_popup.destroyed.connect(lambda: setattr(self, 'wooden_fish_popup', None))

    def show_quick_menu(self):
        if self.easter_menu is not None:
            self.easter_menu.close()
        if self.quick_menu is not None and self.quick_menu.isVisible():
            self.quick_menu.close()
            return
        x, top_y, bottom_y = self.quick_menu_anchor()
        self.quick_menu = PetQuickMenu(x, top_y, bottom_y, self.show_settings.emit, self.chat_requested.emit, self._on_voice_chat_toggle, self.quit, self._on_share_screen_toggle, share_screen_active=self._share_screen_active, voice_chat_active=self._voice_chat_active, parent=self)
        self.quick_menu.destroyed.connect(lambda: setattr(self, 'quick_menu', None))

    def _on_share_screen_toggle(self, checked):
        self._share_screen_active = checked
        self.share_screen_requested.emit(checked)

    def _on_voice_chat_toggle(self, checked):
        self._voice_chat_active = checked
        if checked:
            self.voice_chat_requested.emit()
        else:
            self.close_voice_popup()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.hover_menu_armed = False
            self.hover_timer.stop()
            self.right_click_menu_timer.stop()
            if self.quick_menu is not None:
                self.quick_menu.close()
            self.ask_pet()
            event.accept()
            return
        if event.button() == Qt.RightButton:
            self.hover_menu_armed = False
            self.suppress_next_right_release_menu = True
            self.right_click_menu_timer.stop()
            if self.quick_menu is not None:
                self.quick_menu.close()
            self.show_easter_menu()
            event.accept()
            return

    def ask_pet(self):
        if self.input_popup is not None and self.input_popup.isVisible():
            self.input_popup.raise_()
            self.input_popup.activateWindow()
            return
        x, y = self.bubble_anchor()
        self.input_popup = PetInputPopup(x, y, self)
        self.input_popup.submitted.connect(self.chat_prompt_submitted.emit)
        self.input_popup.destroyed.connect(lambda: setattr(self, 'input_popup', None))

    def show_voice_popup(self):
        if self.voice_popup is not None and self.voice_popup.isVisible():
            self.voice_popup.raise_()
            return self.voice_popup
        x, y = self.bubble_anchor()
        self.voice_popup = PetVoicePopup(x, y, self)
        self.voice_popup.pause_requested.connect(self.voice_pause_requested.emit)
        self.voice_popup.destroyed.connect(lambda: setattr(self, 'voice_popup', None))
        return self.voice_popup

    def update_voice_popup(self, state, text=''):
        popup = self.show_voice_popup()
        x, y = self.bubble_anchor()
        popup.move_to_anchor(x, y, smooth=False)
        popup.update_state(state, text)

    def close_voice_popup(self):
        if self.voice_popup is not None:
            self.voice_popup.close()
            self.voice_popup = None

    def _fall_step(self):
        gravity = 0.7
        config.drag_speed_y += gravity
        nx = self.x() + config.drag_speed_x
        ny = self.y() + config.drag_speed_y
        screen = QApplication.screenAt(self._pet_reference_point(nx, ny))
        if screen is not None and screen.availableGeometry() != self.current_screen:
            self._set_current_screen_from_point(self._pet_reference_point(nx, ny))
        limited = self._limit_position(nx, ny)
        hit_side = limited.x() != int(nx)
        hit_floor = limited.y() >= self.floor_y
        if hit_side:
            config.drag_speed_x = -config.drag_speed_x * 0.5
        self.move(limited)
        self._sync_voice_popup_position()
        if hit_floor:
            self.fall_timer.stop()
            config.on_floor = True
            config.drag_speed_x = 0
            config.drag_speed_y = 0
            self._resume_random_animation()

    def _limit_position(self, x, y):
        left = self.current_screen.left() - self.width() // 2
        right = self.current_screen.right() - self.width() // 2
        top = self.current_screen.top() - self.height() // 2
        bottom = self.floor_y
        return QPoint(max(left, min(int(x), right)), max(top, min(int(y), bottom)))

    def _sync_voice_popup_position(self):
        if self.voice_popup is not None and self.voice_popup.isVisible():
            x, y = self.bubble_anchor()
            self.voice_popup.move_to_anchor(x, y, floaty=self.fall_timer.isActive())

    def _move_by(self, dx, dy):
        self.move(self._limit_position(self.x() + dx, self.y() + dy))
        self._sync_voice_popup_position()

    def _resume_random_animation(self):
        if self.anim_thread:
            self.anim_thread.worker.resume()

    def play_action(self, name):
        if not self.profile or name not in self.profile.acts:
            return
        if self.anim_thread:
            self.anim_thread.worker.play([self.profile.acts[name]])

    def pat(self):
        act = self.profile.patpat.get(2) or self.profile.default
        if self.anim_thread:
            self.anim_thread.worker.play([act])

    def show_chat(self, history=None, append_message=None, content_for_llm=None, system_prompt_builder=None):
        if self.chat_window is None:
            self.chat_window = ChatWindow(config.current_pet, self, history=history, append_message=append_message, content_for_llm=content_for_llm, system_prompt_builder=system_prompt_builder)
        else:
            self.chat_window.append_message = append_message
            self.chat_window.content_for_llm = content_for_llm
            self.chat_window.system_prompt_builder = system_prompt_builder
            if history is not None and self.chat_window.history is not history:
                self.chat_window.history = history
                self.chat_window.reload_history()
            elif history is not None:
                self.chat_window.reload_history()
        self.chat_window.show_window()

    def show_doubao_call(self, append_message=None):
        if self.doubao_call_window is None:
            self.doubao_call_window = DoubaoCallWindow(config.current_pet, self, append_message=append_message)
            self.doubao_call_window.closed_signal.connect(self._on_doubao_call_closed)
        else:
            self.doubao_call_window.pet_name = config.current_pet
            self.doubao_call_window.append_message = append_message
        self.doubao_call_window.show_window()

    def _on_doubao_call_closed(self):
        self.doubao_call_window = None

    def _current_visible_bounds(self):
        return self.visible_bounds if not self.visible_bounds.isNull() else QRect(0, 0, self.width(), self.height())

    def bubble_anchor(self):
        bounds = self._current_visible_bounds()
        center_x = self.x() + self.label.x() + bounds.left() + bounds.width() // 2
        top_y = self.y() + self.label.y() + bounds.top()
        return center_x, top_y + 12

    def quick_menu_anchor(self):
        bounds = self._current_visible_bounds()
        center_x = self.x() + self.label.x() + bounds.left() + bounds.width() // 2
        top_y = self.y() + self.label.y() + bounds.top()
        bottom_y = self.y() + self.label.y() + bounds.bottom()
        return center_x, top_y, bottom_y

    def apply_settings(self):
        self._init_window()
        self.show()
        self._reset_size(keep_position=True)
        self._setup_tray()

    def quit(self):
        self.quit_requested.emit()

    def quit_now(self):
        self._stop_animation()
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        self._stop_animation()
        super().closeEvent(event)
