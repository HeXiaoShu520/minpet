# coding:utf-8
"""桌宠相关弹出菜单。"""

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QParallelAnimationGroup, QPropertyAnimation, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout
from qfluentwidgets import FluentIcon as FIF

from miniPet import config
from miniPet.widgets.ui_utils import clamp_popup_pos


def build_pet_context_menu(owner, include_actions=False):
    menu = QMenu(owner)
    icon_dir = config.RES_DIR / 'icons'
    system_icon_dir = icon_dir / 'system'
    if config.current_pet:
        title = QAction(QIcon(str(system_icon_dir / 'minipet.svg')), config.current_pet, menu)
        title.setEnabled(False)
        menu.addAction(title)
        menu.addSeparator()

    system_action = QAction(QIcon(str(icon_dir / 'SystemPanel.png')), '设置', menu)
    system_action.triggered.connect(owner.show_settings.emit)
    chat_action = QAction(QIcon(str(icon_dir / 'Dialogue_icon.png')), '聊天', menu)
    chat_action.triggered.connect(owner.chat_requested.emit)
    voice_chat_action = QAction(FIF.CHAT.icon(), '语音聊天', menu)
    voice_chat_action.triggered.connect(owner.voice_chat_requested.emit)
    menu.addAction(system_action)
    menu.addAction(chat_action)
    menu.addAction(voice_chat_action)
    menu.addSeparator()

    if include_actions:
        act_menu = menu.addMenu(QIcon(str(icon_dir / 'jump.svg')), '动作')
        if owner.profile:
            for name in owner.profile.acts.keys():
                action = QAction(QIcon(str(icon_dir / 'jump.svg')), name, act_menu)
                action.triggered.connect(lambda checked=False, n=name: owner.play_action(n))
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
        action.triggered.connect(lambda checked=False, p=pet: owner.load_pet(p))
        role_menu.addAction(action)
    quit_action = QAction(FIF.POWER_BUTTON.icon(), '退出', menu)
    quit_action.triggered.connect(owner.quit)
    menu.addAction(quit_action)
    return menu


class PetDropIntentPopup(QFrame):
    """用户向桌宠拖放内容后，用来选择总结、起草回复等处理意图的弹窗。"""

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
        end_pos = clamp_popup_pos(QPoint(int(x - self.width() / 2), int(y - self.height() - 18)), self.size(), QPoint(int(x), int(y)))
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
    """彩蛋菜单中的自绘动作按钮。"""

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
    """桌宠彩蛋功能入口菜单。"""

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
        pos = clamp_popup_pos(QPoint(int(x - self.width() / 2), int(y - self.height() - 24)), self.size(), QPoint(int(x), int(y)))
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
    """鼠标靠近桌宠时显示的极简快捷菜单。"""

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
        voice_chat_btn.setToolTip('启动一次接听')
        share_screen_btn.setToolTip('共享屏幕（语音时附带截图）')
        share_screen_btn.setChecked(share_screen_active)
        quit_btn.setToolTip('退出')

        settings_btn.clicked.connect(lambda: self._trigger(on_settings))
        chat_btn.clicked.connect(lambda: self._trigger(on_chat))
        voice_chat_btn.clicked.connect(lambda: self._trigger(on_voice_chat))
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


