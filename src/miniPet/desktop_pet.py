# coding:utf-8
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QEasingCurve, QEvent, QParallelAnimationGroup, QPropertyAnimation, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QIcon, QKeyEvent, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF

from miniPet import config
from miniPet.animation import AnimationThread
from miniPet.chat_window import ChatWindow
from miniPet.pet_assets import load_pet_profile
from miniPet.realtime_window import RealtimeWindow
from miniPet.voice_chat_window import VoiceChatWindow


class PetInputPopup(QFrame):
    submitted = Signal(object)

    def __init__(self, x, y, parent=None):
        super().__init__(parent)
        self.anim_group = None
        self.pending_images = []
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(0.0)
        self.setStyleSheet('''
            QFrame#InputCard {
                border: 1px solid rgba(210, 216, 226, 220);
                border-radius: 16px;
                background: rgba(255, 255, 255, 248);
            }
            QLineEdit {
                border: 1px solid #dfe3e8;
                border-radius: 12px;
                padding: 10px 12px;
                background: #ffffff;
                color: #1f2328;
                font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #8ab4f8; }
        ''')
        card = QFrame(self)
        card.setObjectName('InputCard')
        root = QVBoxLayout(card)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(0)
        self.preview_row = QHBoxLayout()
        self.preview_row.setContentsMargins(0, 0, 0, 8)
        self.preview_row.setSpacing(6)
        root.addLayout(self.preview_row)
        self.input = QLineEdit(card)
        self.input.setAcceptDrops(True)
        self.input.installEventFilter(self)
        self.input.setPlaceholderText('想对宠物说什么？')
        self.input.returnPressed.connect(self._submit)
        root.addWidget(self.input)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        self.setFixedWidth(300)
        self.adjustSize()
        end_pos = QPoint(int(x - self.width() / 2), int(y - self.height() - 18))
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
        self.pending_images.append(self._image_to_data_url(image))
        preview = QLabel(self)
        preview.setFixedSize(42, 42)
        preview.setStyleSheet('QLabel{border:1px solid #dfe3e8;border-radius:8px;background:#f7f8fa;}')
        preview.setPixmap(QPixmap.fromImage(image).scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.preview_row.addWidget(preview)
        self.input.setPlaceholderText('已添加 %d 张图片，输入文字后回车发送' % len(self.pending_images))
        self.adjustSize()

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
        text = self.input.text().strip()
        if text or self.pending_images:
            self.submitted.emit(self._build_content(text))
        self.close()

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

    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            self.close()
        super().changeEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)


class PetQuickMenu(QFrame):
    def __init__(self, x, top_y, bottom_y, on_settings, on_chat, on_voice_chat, on_realtime, on_quit, parent=None):
        super().__init__(parent)
        self.anim_group = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowOpacity(0.0)
        self.setStyleSheet('''
            QFrame#QuickMenuCard {
                border: 1px solid rgba(210, 216, 226, 220);
                border-radius: 18px;
                background: rgba(255, 255, 255, 245);
            }
            QPushButton {
                border: none;
                border-radius: 14px;
                background: transparent;
                padding: 8px;
            }
            QPushButton:hover { background: #edf3ff; }
        ''')
        card = QFrame(self)
        card.setObjectName('QuickMenuCard')
        row = QHBoxLayout(card)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(6)
        settings_btn = QPushButton(card)
        chat_btn = QPushButton(card)
        voice_chat_btn = QPushButton(card)
        realtime_btn = QPushButton(card)
        quit_btn = QPushButton(card)
        settings_btn.setIcon(QIcon(str(config.RES_DIR / 'icons' / 'SystemPanel.png')))
        chat_btn.setIcon(QIcon(str(config.RES_DIR / 'icons' / 'Dialogue_icon.png')))
        voice_chat_btn.setIcon(FIF.CHAT.icon())
        realtime_btn.setIcon(FIF.PHONE.icon())
        quit_btn.setIcon(FIF.POWER_BUTTON.icon())
        for btn in (settings_btn, chat_btn, voice_chat_btn, realtime_btn, quit_btn):
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(34, 34)
        settings_btn.setToolTip('设置')
        chat_btn.setToolTip('聊天')
        voice_chat_btn.setToolTip('语音聊天')
        realtime_btn.setToolTip('实时通话')
        quit_btn.setToolTip('退出')
        settings_btn.clicked.connect(lambda: self._trigger(on_settings))
        chat_btn.clicked.connect(lambda: self._trigger(on_chat))
        voice_chat_btn.clicked.connect(lambda: self._trigger(on_voice_chat))
        realtime_btn.clicked.connect(lambda: self._trigger(on_realtime))
        quit_btn.clicked.connect(lambda: self._trigger(on_quit))
        row.addWidget(settings_btn)
        row.addWidget(chat_btn)
        row.addWidget(voice_chat_btn)
        row.addWidget(realtime_btn)
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
        QTimer.singleShot(180, self.close)
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
    chat_requested = Signal()
    voice_chat_requested = Signal()
    realtime_requested = Signal()
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
        self.voice_chat_window = None
        self.realtime_window = None
        self.tray = None
        self.context_menu = None
        self.input_popup = None
        self.quick_menu = None
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
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.show_quick_menu)
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

    def _init_ui(self):
        self.label = QLabel(self)
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
        self.floor_y = self.current_screen.bottom() - self.height() + 1
        if keep_position:
            self.move(self._limit_position(old_pos.x(), old_pos.y()))
        else:
            self.move(self.current_screen.center().x() - self.width() // 2, self.floor_y)
        if set_image and config.current_image:
            self._set_image(config.current_image, config.current_anchor)

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if not self.tray:
            self.tray = QSystemTrayIcon(QIcon(str(config.avatar_path('pet'))), self)
            self.tray.activated.connect(lambda reason: self.fetch_back() if reason == QSystemTrayIcon.Trigger else None)
        self.tray.setContextMenu(self._build_menu(include_actions=True, include_fetch=True))
        self.tray.show()

    def _build_menu(self, include_actions=False, include_fetch=False):
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
        realtime_action = QAction(FIF.PHONE.icon(), '实时通话', menu)
        realtime_action.triggered.connect(self.realtime_requested.emit)
        menu.addAction(system_action)
        menu.addAction(chat_action)
        menu.addAction(voice_chat_action)
        menu.addAction(realtime_action)
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

        if include_fetch:
            fetch_action = QAction(QIcon(str(icon_dir / 'backpack.svg')), '找回宠物', menu)
            fetch_action.triggered.connect(self.fetch_back)
            menu.addAction(fetch_action)
            menu.addSeparator()
        quit_action = QAction(FIF.POWER_BUTTON.icon(), '退出', menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        return menu

    def enterEvent(self, event):
        self.hover_timer.start(500)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_timer.stop()
        QTimer.singleShot(220, self._close_quick_menu_if_mouse_away)
        super().leaveEvent(event)

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
        self.show_quick_menu()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.hover_timer.stop()
            self.left_pressed = True
            self.was_dragging = False
            self.mouse_drag_pos = event.globalPos() - self.pos()
            self.press_global_pos = event.globalPos()
            self.last_mouse = [QCursor.pos()]
            event.accept()
        elif event.button() == Qt.RightButton:
            self.show_quick_menu()
            event.accept()

    def mouseMoveEvent(self, event):
        if not self.left_pressed:
            return
        if not self.is_dragging and (event.globalPos() - self.press_global_pos).manhattanLength() >= 6:
            self.is_dragging = True
            self.was_dragging = True
            self.hover_timer.stop()
            if self.quick_menu is not None:
                self.quick_menu.close()
            if self.input_popup is not None:
                self.input_popup.close()
            self.fall_timer.stop()
            if self.anim_thread:
                self.anim_thread.worker.play([self.profile.drag])
        if self.is_dragging:
            self.move(event.globalPos() - self.mouse_drag_pos)
            self.last_mouse.append(QCursor.pos())
            self.last_mouse = self.last_mouse[-4:]
            event.accept()

    def mouseReleaseEvent(self, event):
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
        if config.app_config.get('allow_drop', True):
            config.on_floor = False
            if self.anim_thread:
                self.anim_thread.worker.play([self.profile.fall])
            self.fall_timer.start(16)
        else:
            self.move(self._limit_position(self.x(), self.y()))
            self._resume_random_animation()
        event.accept()

    def show_quick_menu(self):
        if self.quick_menu is not None and self.quick_menu.isVisible():
            self.quick_menu.close()
            return
        x, top_y, bottom_y = self.quick_menu_anchor()
        self.quick_menu = PetQuickMenu(x, top_y, bottom_y, self.show_settings.emit, self.chat_requested.emit, self.voice_chat_requested.emit, self.realtime_requested.emit, self.quit, self)
        self.quick_menu.destroyed.connect(lambda: setattr(self, 'quick_menu', None))

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.hover_timer.stop()
            if self.quick_menu is not None:
                self.quick_menu.close()
            self.ask_pet()
            event.accept()

    def ask_pet(self):
        if self.input_popup is not None and self.input_popup.isVisible():
            self.input_popup.raise_()
            self.input_popup.activateWindow()
            return
        x, y = self.bubble_anchor()
        self.input_popup = PetInputPopup(x, y, self)
        self.input_popup.submitted.connect(self.chat_prompt_submitted.emit)
        self.input_popup.destroyed.connect(lambda: setattr(self, 'input_popup', None))

    def _fall_step(self):
        gravity = 0.7
        config.drag_speed_y += gravity
        nx = self.x() + config.drag_speed_x
        ny = self.y() + config.drag_speed_y
        limited = self._limit_position(nx, ny)
        hit_side = limited.x() != int(nx)
        hit_floor = limited.y() >= self.floor_y
        if hit_side:
            config.drag_speed_x = -config.drag_speed_x * 0.5
        self.move(limited)
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

    def _move_by(self, dx, dy):
        self.move(self._limit_position(self.x() + dx, self.y() + dy))

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

    def show_chat(self, history=None, append_message=None, content_for_llm=None):
        if self.chat_window is None:
            self.chat_window = ChatWindow(config.current_pet, self, history=history, append_message=append_message, content_for_llm=content_for_llm)
        else:
            self.chat_window.append_message = append_message
            self.chat_window.content_for_llm = content_for_llm
            if history is not None and self.chat_window.history is not history:
                self.chat_window.history = history
                self.chat_window.reload_history()
            elif history is not None:
                self.chat_window.reload_history()
        self.chat_window.show_window()

    def show_voice_chat(self, history=None, append_message=None, content_for_llm=None):
        if self.voice_chat_window is None:
            self.voice_chat_window = VoiceChatWindow(config.current_pet, self, history=history, append_message=append_message, content_for_llm=content_for_llm)
            self.voice_chat_window.closed_signal.connect(self._on_voice_chat_closed)
        else:
            self.voice_chat_window.pet_name = config.current_pet
            self.voice_chat_window.history = history if history is not None else self.voice_chat_window.history
            self.voice_chat_window.append_message = append_message
            self.voice_chat_window.content_for_llm = content_for_llm
        self.voice_chat_window.show_window()

    def _on_voice_chat_closed(self):
        self.voice_chat_window = None

    def show_realtime(self, append_message=None):
        if self.realtime_window is None:
            self.realtime_window = RealtimeWindow(config.current_pet, self, append_message=append_message)
            self.realtime_window.closed_signal.connect(self._on_realtime_closed)
        else:
            self.realtime_window.pet_name = config.current_pet
            self.realtime_window.append_message = append_message
        self.realtime_window.show_window()

    def _on_realtime_closed(self):
        self.realtime_window = None

    def fetch_back(self):
        screen = self.screen().availableGeometry() if self.screen() else self.current_screen
        self.current_screen = screen
        self.floor_y = screen.bottom() - self.height() + 1
        self.move(screen.center().x() - self.width() // 2, self.floor_y)
        self.show()
        self.raise_()
        self.activateWindow()

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
