# coding:utf-8
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget
from qfluentwidgets import InfoBar, InfoBarPosition
from qfluentwidgets import FluentIcon as FIF

from miniPet import config
from miniPet.realtime_client import RealtimeWorker
from miniPet.typewriter import Typewriter


class InterruptButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__('打断', parent)
        self.setFixedSize(68, 34)
        self.setToolTip('停止当前语音输出')
        self.setCursor(Qt.PointingHandCursor)


class EndCallButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 44)
        self.setToolTip('挂断')
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#ff3b30'))
        painter.drawRoundedRect(13, 18, 18, 8, 4, 4)
        painter.drawEllipse(10, 20, 9, 9)
        painter.drawEllipse(25, 20, 9, 9)
        painter.setBrush(QColor('#ffffff'))
        painter.drawRoundedRect(17, 22, 10, 6, 3, 3)


class MicLevelButton(QPushButton):
    def __init__(self, icon, parent=None):
        super().__init__(parent)
        self.level = 0
        self.muted = False
        self.setIcon(icon)
        self.setIconSize(QSize(24, 24))
        self.setFixedSize(44, 44)
        self.setToolTip('当前输入音量')
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)

    def setLevel(self, level):
        self.level = max(0, min(100, int(level)))
        self.update()

    def setMuted(self, muted):
        self.muted = bool(muted)
        self.setToolTip('麦克风已静音' if self.muted else '当前输入音量')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = self.rect().center()
        rect = self.rect().adjusted(4, 4, -4, -4)
        if self.muted:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#fff1f0'))
            painter.drawEllipse(rect)
            self._draw_mic(painter, QColor('#ff3b30'))
            pen = QPen(QColor('#ff3b30'), 3)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(center.x() + 11, center.y() - 14, center.x() - 11, center.y() + 14)
            return
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#f6f7f8'))
        painter.drawEllipse(rect)
        if self.level > 0:
            fill_rect = rect.adjusted(3, 3, -3, -3)
            fill_height = max(4, int(fill_rect.height() * self.level / 100))
            level_rect = fill_rect.adjusted(0, fill_rect.height() - fill_height, 0, 0)
            painter.setBrush(QColor('#22c55e'))
            painter.drawRoundedRect(level_rect, 12, 12)
            pen = QPen(QColor('#16a34a'), 2)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(rect.adjusted(2, 2, -2, -2))
        self._draw_mic(painter, QColor('#202124'))

    def _draw_mic(self, painter, color):
        center = self.rect().center()
        pen = QPen(color, 2.4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(center.x() - 5, center.y() - 14, 10, 18, 5, 5)
        painter.drawArc(center.x() - 11, center.y() - 8, 22, 20, 200 * 16, 140 * 16)
        painter.drawLine(center.x(), center.y() + 12, center.x(), center.y() + 17)
        painter.drawLine(center.x() - 7, center.y() + 17, center.x() + 7, center.y() + 17)


class RealtimeWindow(QWidget):
    closed_signal = Signal()

    def __init__(self, pet_name='', parent=None, append_message=None):
        super().__init__(parent)
        self.pet_name = pet_name
        self.append_message = append_message
        self.worker = None
        self.current_asr = ''
        self.current_reply = ''
        self._asr_debounce = QTimer()
        self._asr_debounce.setSingleShot(True)
        self._asr_debounce.timeout.connect(self._flush_asr)
        self.captions_enabled = True
        self.call_state = 'idle'
        self.input_level = 0
        self.mic_muted = False
        self.anim_index = 0
        self.shared_screen = None
        self._drag_pos = None
        self._closing = False
        self.setWindowTitle('豆包通话')
        self.setWindowIcon(QIcon(str(config.avatar_path('pet'))))
        self.setFixedSize(322, 520)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 24, 18, 24)
        root.setSpacing(0)
        self.setStyleSheet('''
            RealtimeWindow{background:transparent;}
            QWidget{font-family:"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;background:transparent;color:#202124;}
            QLabel#AvatarLabel{background:transparent;border-radius:54px;}
            QLabel#AnimLabel{color:#3d3d3d;font-size:22px;font-weight:700;letter-spacing:3px;}
            QLabel#StatusLabel{color:#8b8f99;font-size:16px;font-weight:400;}
            QLabel#CaptionView{background:transparent;border:none;font-family:"Microsoft YaHei UI", "Microsoft YaHei", sans-serif;font-size:16px;font-weight:400;line-height:1.65;color:#24292f;padding:0 10px;}
            QPushButton#ToolButton{border:none;border-radius:22px;background:transparent;color:#8a8a8a;}
            QPushButton#ToolButton:hover{background:#f4f5f7;color:#303133;}
            QPushButton#ToolButton:checked{color:#1f6fff;background:#eef5ff;}
            QPushButton#MicButton{border:none;background:transparent;color:#303133;}
            QPushButton#InterruptButton{border:none;border-radius:18px;background:#f6f7f8;color:#60646f;font-size:13px;}
            QPushButton#InterruptButton:hover{background:#eef1f4;color:#303133;}
            QPushButton#EndButton{border:none;border-radius:22px;background:#fff1f0;color:#ff3b30;}
            QPushButton#EndButton:hover{background:#ffe3e0;color:#d92d20;}
        ''')

        root.addSpacing(8)
        self.avatar = QLabel(self)
        self.avatar.setObjectName('AvatarLabel')
        self.avatar.setFixedSize(108, 108)
        self.avatar.setAlignment(Qt.AlignCenter)
        self._set_avatar()
        root.addWidget(self.avatar, 0, Qt.AlignHCenter)

        root.addSpacing(24)
        self.anim_label = QLabel('● ● ●', self)
        self.anim_label.setObjectName('AnimLabel')
        self.anim_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.anim_label)

        root.addSpacing(18)
        self.status_label = QLabel('正在连接...', self)
        self.status_label.setObjectName('StatusLabel')
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(False)
        self.status_label.setFixedSize(280, 48)
        root.addWidget(self.status_label, 0, Qt.AlignHCenter)

        self.caption_view = QLabel('', self)
        self.caption_view.setObjectName('CaptionView')
        self.caption_view.setVisible(True)
        self.caption_view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.caption_view.setWordWrap(True)
        self.caption_view.setFixedHeight(180)
        root.addWidget(self.caption_view)
        self._tw = Typewriter(self.caption_view, speed_ms=22)
        root.addStretch(1)

        self.interrupt_btn = InterruptButton(self)
        self.interrupt_btn.setObjectName('InterruptButton')
        self.interrupt_btn.setVisible(False)
        root.addWidget(self.interrupt_btn, 0, Qt.AlignHCenter)
        root.addSpacing(8)

        controls = QHBoxLayout()
        controls.setContentsMargins(18, 0, 18, 0)
        controls.setSpacing(34)
        controls.addStretch(1)
        self.share_btn = self._tool_button(QIcon(str(config.RES_DIR / 'icons' / 'system' / 'screen_share.svg')), '共享屏幕', checkable=True)
        self.mic_btn = MicLevelButton(FIF.MICROPHONE.icon(), self)
        self.end_btn = EndCallButton(self)
        controls.addWidget(self.share_btn)
        controls.addWidget(self.mic_btn)
        controls.addWidget(self.end_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        self.share_btn.clicked.connect(self._share_screen)
        self.mic_btn.clicked.connect(self._toggle_mute)
        self.interrupt_btn.clicked.connect(self._interrupt_speech)
        self.end_btn.clicked.connect(self._finish_session)

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick_animation)
        self.anim_timer.start(420)
        self._set_state('idle', '准备连接')

    def _tool_button(self, icon, tooltip, checkable=False, mic=False, end=False):
        button = QPushButton(self)
        button.setObjectName('EndButton' if end else 'MicButton' if mic else 'ToolButton')
        button.setIcon(icon)
        button.setIconSize(QSize(25, 25))
        button.setFixedSize(44, 44)
        button.setToolTip(tooltip)
        button.setCheckable(checkable)
        return button

    def _set_avatar(self):
        pixmap = QPixmap(str(config.avatar_path('pet')))
        if pixmap.isNull():
            pixmap = QPixmap(str(config.RES_DIR / 'icons' / 'character.svg'))
        if pixmap.isNull():
            self.avatar.setText((self.pet_name or '宠')[:1])
            return
        screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        pm = pixmap.scaled(int(108 * dpr), int(108 * dpr), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        self.avatar.setPixmap(pm)

    def _set_state(self, state, text=None):
        self.call_state = state
        if text is not None:
            text = text.rstrip('，。！？、…,.!?；;')
            # 超宽时只保留末尾，避免跳变
            fm = self.status_label.fontMetrics()
            max_w = self.status_label.width() - 8
            if fm.horizontalAdvance(text) > max_w:
                while text and fm.horizontalAdvance('…' + text) > max_w:
                    text = text[1:]
                text = '…' + text
            self.status_label.setText(text)
        if state in ('idle', 'listening', 'thinking', 'connecting'):
            self.interrupt_btn.setVisible(False)
        if state == 'idle':
            self.anim_label.setText('● ● ●')
        elif state == 'listening':
            self.anim_label.setText('▁ ▃ ▆')
        else:
            self.anim_label.setText('● ● ●')

    def _tick_animation(self):
        self.anim_index = (self.anim_index + 1) % 4
        dot_frames = ['● ○ ○', '○ ● ○', '○ ○ ●', '○ ● ○']
        listen_frames = ['▁ ▃ ▆', '▃ ▆ ▃', '▆ ▃ ▁', '▃ ▁ ▃']
        if self.call_state == 'listening':
            self.anim_label.setText(listen_frames[self.anim_index])
        elif self.call_state in ('connecting', 'thinking', 'speaking'):
            self.anim_label.setText(dot_frames[self.anim_index])

    def _escape(self, text):
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')

    def _refresh_caption(self):
        pass  # 由 _on_chat 直接调 _tw.append_chunk 驱动

    def _flush_asr(self):
        pass  # 保留 timer 引用，不再使用

    def _set_caption(self, text):
        self.current_asr = str(text or '').strip()
        if self.current_asr:
            self._set_state('listening', self.current_asr[-32:])

    def _append_assistant(self, text):
        self.current_reply = str(text or '').strip()

    def _collect_config(self):
        cfg = dict(config.realtime_config)
        if not cfg.get('bot_name'):
            cfg['bot_name'] = self.pet_name or config.DEFAULT_REALTIME_CONFIG['bot_name']
        return cfg

    def _ensure_session(self):
        if self.worker is not None:
            return True
        if not config.tts_config.get('api_key'):
            InfoBar.error('缺少配置', '请先在设置 > 语音中填写 TTS API Key', duration=4000, position=InfoBarPosition.BOTTOM, parent=self)
            return False
        self.current_asr = ''
        self.current_reply = ''
        self.worker = RealtimeWorker(self._collect_config(), parent=self)
        self.worker.status_changed.connect(self._on_status)
        self.worker.asr_received.connect(self._on_asr)
        self.worker.chat_received.connect(self._on_chat)
        self.worker.error_received.connect(self._on_error)
        self.worker.level_changed.connect(self._on_input_level)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()
        self._set_state('connecting', '正在连接...')
        return True

    def _start_recording(self):
        if self.mic_muted:
            self._set_state('idle', '已静音')
            return
        if not self._ensure_session():
            return
        self.current_asr = ''
        self.current_reply = ''
        self._set_state('listening', '正在听...')
        self.worker.start_recording()

    def _stop_recording(self):
        if self.worker is not None:
            self.worker.stop_recording()
        self._set_state('idle', '已静音')

    def _interrupt_speech(self):
        if self.worker is not None:
            self.worker.interrupt()
        self.interrupt_btn.setVisible(False)
        self._set_state('listening' if not self.mic_muted else 'idle', '正在听...' if not self.mic_muted else '已静音')

    def _toggle_mute(self):
        self.mic_muted = not self.mic_muted
        self.mic_btn.setMuted(self.mic_muted)
        if self.mic_muted:
            if self.worker is not None:
                self.worker.stop_recording()
            self._set_state('idle', '已静音')
            return
        self._set_state('listening', '正在听...')
        if self.worker is not None:
            self.worker.start_recording()
        else:
            self._start_recording()

    def _share_screen(self):
        screens = QApplication.screens()
        if self.shared_screen is not None:
            self.shared_screen = None
            self.share_btn.setChecked(False)
            self._set_state('listening' if self.worker is not None else 'idle', '已停止共享屏幕')
            return
        if not screens:
            self.share_btn.setChecked(False)
            InfoBar.error('共享屏幕', '没有检测到可共享的屏幕', duration=3000, position=InfoBarPosition.BOTTOM, parent=self)
            return
        if len(screens) == 1:
            self._select_screen(screens[0], 1)
            return
        self.share_btn.setChecked(False)
        menu = QMenu(self)
        for index, screen in enumerate(screens, 1):
            geometry = screen.geometry()
            name = screen.name() or ('屏幕 %d' % index)
            text = '%s  %dx%d' % (name, geometry.width(), geometry.height())
            action = menu.addAction(text)
            action.triggered.connect(lambda checked=False, s=screen, i=index: self._select_screen(s, i))
        menu.exec(self.share_btn.mapToGlobal(self.share_btn.rect().bottomLeft()))

    def _select_screen(self, screen, index):
        self.shared_screen = screen
        self.share_btn.setChecked(True)
        geometry = screen.geometry()
        name = screen.name() or ('屏幕 %d' % index)
        text = '已共享 %s（%dx%d）' % (name, geometry.width(), geometry.height())
        self._set_state('listening' if self.worker is not None else 'idle', text)
        InfoBar.success('共享屏幕', text, duration=2600, position=InfoBarPosition.BOTTOM, parent=self)

    def _finish_session(self):
        self._set_state('connecting', '正在挂断...')
        self.close()

    def _on_status(self, text):
        if self.mic_muted and text in ('会话中', '正在听', '麦克风已关闭'):
            self._set_state('idle', '已静音')
            return
        status_map = {
            '连接中': ('connecting', '正在连接...'),
            '连接已建立': ('connecting', '正在准备通话...'),
            '会话中': ('speaking', '正在准备通话...'),
            '正在听': ('listening', '正在听...'),
            '识别中': ('thinking', '正在思考...'),
            '麦克风已关闭': ('idle', '麦克风已关闭'),
            '会话已结束': ('idle', '通话已结束'),
            '会话已取消': ('idle', '通话已取消'),
            '回复结束': None,
        }
        if text == '回复结束':
            # 保存本轮回复到历史，清空 current_reply 让下一轮 ASR final 能正常清字幕
            if self.current_reply and self.append_message:
                self.append_message('assistant', self.current_reply, 'realtime')
            self.current_reply = ''
            return
        state, label = status_map.get(text, (self.call_state, text))
        self._set_state(state, label)

    def _on_asr(self, text, interim):
        if not text:
            return
        self.current_asr = text
        self._set_caption(text)
        if interim:
            return
        # AI 正在回复时忽略 final ASR，避免字幕被清空重来
        if self.current_reply:
            return
        self.current_reply = ''
        self._tw.set_text('')
        self._refresh_caption()
        self.call_state = 'thinking'
        if self.append_message:
            self.append_message('user', text, 'realtime')

    def _on_chat(self, text):
        if not text:
            return
        if not self.current_reply:
            self.interrupt_btn.setVisible(True)
        self.current_reply += text
        self._tw.append_chunk(text)

    def _on_input_level(self, level):
        self.input_level = 0 if self.mic_muted else max(0, min(100, int(level)))
        self.mic_btn.setLevel(self.input_level)

    def _on_error(self, text):
        self._set_state('idle', '通话出错')
        InfoBar.error('豆包通话错误', text[:120], duration=5000, position=InfoBarPosition.BOTTOM, parent=self)

    def _on_finished(self):
        if self.current_reply and self.append_message:
            self.append_message('assistant', self.current_reply, 'realtime')
        self.worker = None
        self._set_state('idle', '通话已结束')

    def _apply_window_mask(self):
        self.clearMask()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#ffffff'))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 36, 36)
        super().paintEvent(event)

    def _move_to_start_position(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = area.center().x() - self.width() // 2
        y = area.top() + max(42, int(area.height() * 0.10))
        self.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_window_mask()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_window_mask()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and event.position().y() < self.height() - 92:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def shutdown(self):
        if self._closing:
            return
        self._closing = True
        self.anim_timer.stop()
        worker = self.worker
        self.worker = None
        if worker is not None:
            try:
                worker.finish()
                if not worker.wait(2500):
                    worker.terminate()
                    worker.wait(1000)
            except Exception:
                pass
        self.mic_btn.setLevel(0)
        self.mic_btn.setMuted(False)
        self.shared_screen = None
        self.current_asr = ''
        self.current_reply = ''

    def closeEvent(self, event):
        self.shutdown()
        self.closed_signal.emit()
        self.deleteLater()
        super().closeEvent(event)

    def show_window(self):
        if not self.isVisible():
            self._move_to_start_position()
            self.show()
        self.activateWindow()
        self.raise_()
        self._start_recording()
