# coding:utf-8
import base64

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget
from qfluentwidgets import InfoBar, InfoBarPosition
from qfluentwidgets import FluentIcon as FIF

from miniPet import config
from miniPet.asr_client import AsrWorker
from miniPet.llm_client import ChatWorker
from miniPet.tts_client import TtsCacheWorker, TtsPreviewWorker, TtsWorker, stop_tts
from miniPet.typewriter import Typewriter


class InterruptButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__('打断', parent)
        self.setFixedSize(88, 36)
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


class VoiceMicButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.muted = False
        self.setFixedSize(44, 44)
        self.setToolTip('打开或关闭麦克风')
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)

    def setMuted(self, muted):
        self.muted = bool(muted)
        self.setToolTip('麦克风已关闭' if self.muted else '打开或关闭麦克风')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = self.rect().center()
        rect = self.rect().adjusted(4, 4, -4, -4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#fff1f0' if self.muted else '#eefaf3'))
        painter.drawEllipse(rect)
        self._draw_mic(painter, QColor('#ff3b30' if self.muted else '#202124'))
        if self.muted:
            pen = QPen(QColor('#ff3b30'), 3)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(center.x() + 11, center.y() - 14, center.x() - 11, center.y() + 14)

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


class VoiceChatWindow(QWidget):
    closed_signal = Signal()

    def __init__(self, pet_name='', parent=None, history=None, append_message=None, content_for_llm=None):
        super().__init__(parent)
        self.pet_name = pet_name
        self.history = history if history is not None else []
        self.append_message = append_message
        self.content_for_llm = content_for_llm
        self.asr_worker = None
        self.chat_worker = None
        self.tts_worker = None
        self.welcome_worker = None
        self.welcome_played = False
        self.pending_recording_after_welcome = False
        self.current_text = ''
        self.current_reply = ''
        self.resume_recording_after_tts = False
        self.shared_screen = None
        self.call_state = 'idle'
        self.anim_index = 0
        self._drag_pos = None
        self._closing = False
        self.setWindowTitle('语音聊天')
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
            VoiceChatWindow{background:transparent;}
            QWidget{font-family:"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;background:transparent;color:#202124;}
            QLabel#AvatarLabel{background:transparent;border-radius:54px;}
            QLabel#AnimLabel{color:#3d3d3d;font-size:22px;font-weight:700;letter-spacing:3px;}
            QLabel#StatusLabel{color:#8b8f99;font-size:16px;font-weight:400;}
            QTextBrowser#CaptionView{background:transparent;border:none;font-family:"Microsoft YaHei UI", "Microsoft YaHei", sans-serif;font-size:16px;font-weight:400;line-height:1.65;color:#24292f;text-align:left;}
            QPushButton#ToolButton{border:none;border-radius:22px;background:transparent;color:#8a8a8a;}
            QPushButton#ToolButton:hover{background:#f4f5f7;color:#303133;}
            QPushButton#ToolButton:checked{color:#1f6fff;background:#eef5ff;}
            QPushButton#MicButton{border:none;border-radius:22px;background:transparent;color:#303133;}
            QPushButton#MicButton:hover{background:#f4f5f7;}
            QPushButton#MicButton:checked{color:#22a957;background:#eefaf3;}
            QPushButton#InterruptButton{border:none;border-radius:18px;background:#f6f7f8;color:#60646f;font-size:13px;}
            QPushButton#InterruptButton:hover{background:#eef1f4;color:#303133;}
            QPushButton#EndButton{border:none;border-radius:22px;background:transparent;color:#ff3b30;}
            QPushButton#EndButton:hover{background:#fff1f0;}
        ''')
        root.addSpacing(8)
        self.avatar = QLabel(self)
        self.avatar.setObjectName('AvatarLabel')
        self.avatar.setFixedSize(108, 108)
        self.avatar.setAlignment(Qt.AlignCenter)
        self._set_avatar()
        root.addWidget(self.avatar, 0, Qt.AlignHCenter)

        root.addSpacing(18)
        self.anim_label = QLabel('● ● ●', self)
        self.anim_label.setObjectName('AnimLabel')
        self.anim_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.anim_label)

        root.addSpacing(14)
        self.status_label = QLabel('请开始说话', self)
        self.status_label.setObjectName('StatusLabel')
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(False)
        self.status_label.setFixedSize(280, 36)
        root.addWidget(self.status_label, 0, Qt.AlignHCenter)

        self.caption_view = QTextBrowser(self)
        self.caption_view.setObjectName('CaptionView')
        self.caption_view.setOpenExternalLinks(False)
        self.caption_view.setVisible(True)
        self.caption_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.caption_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.caption_view.document().setDocumentMargin(0)
        self.caption_view.setFixedHeight(220)
        root.addWidget(self.caption_view)
        self._tw = Typewriter(self.caption_view, speed_ms=22)

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
        self.mic_btn = VoiceMicButton(self)
        self.mic_btn.setChecked(True)
        self.mic_btn.setMuted(False)
        self.end_btn = EndCallButton(self)
        controls.addWidget(self.share_btn)
        controls.addWidget(self.mic_btn)
        controls.addWidget(self.end_btn)
        controls.addStretch(1)
        root.addLayout(controls)

        self.share_btn.clicked.connect(self._share_screen)
        self.mic_btn.clicked.connect(self._toggle_recording)
        self.interrupt_btn.clicked.connect(self._interrupt_speech)
        self.end_btn.clicked.connect(self.close)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick_animation)
        self.anim_timer.start(420)
        self._set_state('idle', '请开始说话')

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
            self.status_label.setText(text.rstrip('，。！？、…,.!?；;'))
        self.anim_label.setText('▁ ▃ ▆' if state == 'listening' else '● ● ●')

    def _set_interrupt_visible(self, visible):
        self.interrupt_btn.setVisible(bool(visible))

    def _interrupt_speech(self):
        stop_tts()
        self._set_interrupt_visible(False)
        self.welcome_worker = None
        self.tts_worker = None
        if self.pending_recording_after_welcome:
            self.pending_recording_after_welcome = False
            self.welcome_played = True
            self._set_state('idle', '请开始说话')
            return
        if self.resume_recording_after_tts and self.mic_btn.isChecked() and not self._closing:
            self._start_recording()
        else:
            self._set_state('idle', '请开始说话')
        self.resume_recording_after_tts = False

    def _tick_animation(self):
        self.anim_index = (self.anim_index + 1) % 4
        dots = ['● ○ ○', '○ ● ○', '○ ○ ●', '○ ● ○']
        wave = ['▁ ▃ ▆', '▃ ▆ ▃', '▆ ▃ ▁', '▃ ▁ ▃']
        if self.call_state == 'listening':
            self.anim_label.setText(wave[self.anim_index])
        elif self.call_state in ('connecting', 'thinking', 'speaking'):
            self.anim_label.setText(dots[self.anim_index])

    def _escape(self, text):
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')

    def _show_reply_caption(self, text):
        if not self.caption_view.isVisible():
            return
        tts_on = config.tts_config.get('enabled') and config.tts_config.get('api_key')
        # 如果 delta 流式已经打过了，直接 set_text 锁定，不从头重打
        if self._tw._target == text:
            self._tw.set_text(text)
            return
        delay = int(config.typewriter_config.get('tts_delay_ms', 500)) if tts_on else 0
        if delay > 0:
            QTimer.singleShot(delay, lambda: self._tw.typewrite(text))
        else:
            self._tw.typewrite(text)

    def _share_screen(self):
        if self.shared_screen is not None:
            self.shared_screen = None
            self.share_btn.setChecked(False)
            self._set_state(self.call_state, '已停止共享屏幕')
            return
        screens = QApplication.screens()
        if not screens:
            self.share_btn.setChecked(False)
            InfoBar.error('共享屏幕', '没有检测到可共享的屏幕', duration=3000, position=InfoBarPosition.BOTTOM, parent=self)
            return
        if len(screens) == 1:
            self.shared_screen = screens[0]
            self.share_btn.setChecked(True)
            self._set_state(self.call_state, '已共享屏幕')
            return
        # 多屏幕：显示选择菜单
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        for index, screen in enumerate(screens, 1):
            geometry = screen.geometry()
            name = screen.name() or f'屏幕 {index}'
            text = f'{name}  {geometry.width()}x{geometry.height()}'
            action = menu.addAction(text)
            action.triggered.connect(lambda checked=False, s=screen: self._select_screen(s))
        menu.exec(self.share_btn.mapToGlobal(self.share_btn.rect().bottomLeft()))

    def _select_screen(self, screen):
        self.shared_screen = screen
        self.share_btn.setChecked(True)
        geometry = screen.geometry()
        name = screen.name() or '屏幕'
        self._set_state(self.call_state, f'已共享 {name}（{geometry.width()}x{geometry.height()}）')

    def _capture_shared_screen(self):
        if self.shared_screen is None:
            return ''
        pixmap = self.shared_screen.grabWindow(0)
        if pixmap.isNull():
            return ''
        image = pixmap.toImage()
        max_width = 1280
        if image.width() > max_width:
            image = image.scaledToWidth(max_width, Qt.SmoothTransformation)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, 'JPEG', 85)
        return 'data:image/jpeg;base64,' + base64.b64encode(bytes(data)).decode('ascii')

    def _toggle_recording(self):
        self.mic_btn.setMuted(not self.mic_btn.isChecked())
        if self.mic_btn.isChecked():
            self._start_recording()
        else:
            self._stop_recording()

    def _welcome_path(self):
        voice_name = config.tts_config.get('voice_name') or config.DEFAULT_TTS_CONFIG['voice_name']
        safe_name = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in voice_name)
        return config.DATA_DIR / 'tts_welcome' / (safe_name + '_welcome.pcm')

    def _play_welcome_then_record(self):
        if self.welcome_worker is not None:
            return
        if not config.tts_config.get('api_key'):
            self.welcome_played = True
            self._start_recording()
            return
        self.pending_recording_after_welcome = True
        self._set_state('speaking', '你好呀，有什么需要帮忙的吗')
        self._set_interrupt_visible(True)
        welcome_path = self._welcome_path()
        if welcome_path.is_file():
            self.welcome_worker = TtsPreviewWorker(welcome_path, parent=self)
        else:
            self.welcome_worker = TtsCacheWorker('你好呀，有什么需要帮忙的吗', config.tts_config, welcome_path, parent=self)
        self.welcome_worker.result_ready.connect(self._on_welcome_done)
        self.welcome_worker.start()

    def _on_welcome_done(self, success, text):
        self.welcome_worker = None
        self.welcome_played = True
        self._set_interrupt_visible(False)
        should_record = self.pending_recording_after_welcome and self.mic_btn.isChecked() and not self._closing
        self.pending_recording_after_welcome = False
        if not success:
            self._on_error(text)
            return
        if should_record:
            self._start_recording()
        else:
            self._set_state('idle', '请开始说话')

    def _start_recording(self):
        if not self.welcome_played:
            self._play_welcome_then_record()
            return
        if not config.tts_config.get('api_key'):
            self.mic_btn.setChecked(False)
            self.mic_btn.setMuted(True)
            InfoBar.error('缺少配置', '请先在设置 > 语音中填写 TTS API Key', duration=4000, position=InfoBarPosition.BOTTOM, parent=self)
            return
        self.mic_btn.setMuted(False)
        if self.asr_worker is not None and not self.asr_worker.isRunning():
            self.asr_worker = None
        if self.asr_worker is None:
            self.asr_worker = AsrWorker(parent=self)
            self.asr_worker.status_changed.connect(self._on_asr_status)
            self.asr_worker.text_received.connect(self._on_asr_text)
            self.asr_worker.final_received.connect(self._on_asr_final)
            self.asr_worker.error_received.connect(self._on_error)
            self.asr_worker.finished_signal.connect(self._on_asr_finished)
            self.asr_worker.start()
        self._set_state('listening', '正在听...')
        QTimer.singleShot(250, self.asr_worker.start_recording)

    def _stop_recording(self):
        if self.asr_worker is not None:
            self.asr_worker.stop_recording()
        self.mic_btn.setMuted(True)
        self._set_state('idle', '麦克风已关闭')

    def _on_asr_status(self, text):
        if self.mic_btn.isChecked() and text in ('ASR已连接', '正在识别'):
            self._set_state('listening', '正在听...')

    def _on_asr_text(self, text):
        if text:
            self.current_text = text
            self._set_state('listening', text[-24:])

    def _on_asr_final(self, text):
        text = (text or '').strip()
        if not text or self.chat_worker is not None:
            return
        self.current_text = text
        self.current_reply = ''
        self._tw.set_text('')
        self._set_state('thinking', text[-24:])
        if self.append_message:
            self.append_message('user', text, 'voice_chat')
        stop_tts()
        screenshot = self._capture_shared_screen()
        self.chat_worker = ChatWorker(self._build_messages(text, screenshot), parent=self)
        self.chat_worker.delta_ready.connect(self._on_llm_delta)
        self.chat_worker.result_ready.connect(self._on_llm_reply)
        self.chat_worker.start()

    def _build_messages(self, text, screenshot=''):
        messages = []
        system_parts = [config.llm_config.get('system_prompt', ''), config.llm_config.get('memory_prompt', '')]
        system = '\n\n'.join(part.strip() for part in system_parts if part and part.strip())
        if system:
            messages.append({'role': 'system', 'content': system})
        for message in self.history[-10:]:
            content = message.get('content', '')
            if self.content_for_llm:
                content = self.content_for_llm(content)
            messages.append({'role': message.get('role'), 'content': content})
        if screenshot:
            user_content = [
                {'type': 'image_url', 'image_url': {'url': screenshot}},
                {'type': 'text', 'text': text},
            ]
        else:
            user_content = text
        messages.append({'role': 'user', 'content': user_content})
        return messages

    def _on_llm_delta(self, text):
        if text:
            self._set_state('speaking', '正在回复')
            self._tw.append_chunk(text)

    def _on_llm_reply(self, success, text):
        self.chat_worker = None
        if not success:
            self._on_error(text)
            return
        reply = text.strip() or '嗯。'
        self.current_reply = reply
        self._show_reply_caption(reply)
        if self.append_message:
            self.append_message('assistant', reply, 'voice_chat')
        if not self._speak_reply(reply):
            if self.mic_btn.isChecked() and not self._closing:
                self._start_recording()
            else:
                self._set_state('idle', '请开始说话')

    def _speak_reply(self, text):
        cfg = config.tts_config
        if not cfg.get('enabled') or not cfg.get('api_key'):
            return False
        self.resume_recording_after_tts = self.mic_btn.isChecked()
        if self.asr_worker is not None:
            self.asr_worker.stop_recording()
        self._set_state('speaking', '正在播报')
        self._set_interrupt_visible(True)
        self.tts_worker = TtsWorker(text, cfg, parent=self)
        self.tts_worker.result_ready.connect(self._on_tts_done)
        self.tts_worker.start()
        return True

    def _on_tts_done(self, success, text):
        self.tts_worker = None
        self._set_interrupt_visible(False)
        if self.resume_recording_after_tts and self.mic_btn.isChecked() and not self._closing:
            self._start_recording()
        else:
            self._set_state('idle', '请开始说话')
        self.resume_recording_after_tts = False

    def _on_error(self, text):
        self._set_state('idle', '出错了')
        InfoBar.error('语音聊天错误', str(text)[:120], duration=5000, position=InfoBarPosition.BOTTOM, parent=self)

    def _on_asr_finished(self):
        self.asr_worker = None

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

    def _detach_audio_worker(self, worker):
        if worker is None:
            return
        try:
            worker.result_ready.disconnect()
        except Exception:
            pass
        if worker.isRunning():
            worker.requestInterruption()
            worker.quit()
            if worker.wait(800):
                worker.deleteLater()
                return
            worker.setParent(None)
            worker.finished.connect(worker.deleteLater)
        else:
            worker.deleteLater()

    def shutdown(self):
        if self._closing:
            return
        self._closing = True
        self.anim_timer.stop()
        stop_tts()
        if self.asr_worker is not None:
            self.asr_worker.finish()
            if not self.asr_worker.wait(2000):
                self.asr_worker.terminate()
                self.asr_worker.wait(1000)
            self.asr_worker = None
        if self.chat_worker is not None and self.chat_worker.isRunning():
            self.chat_worker.requestInterruption()
            self.chat_worker.quit()
            self.chat_worker.wait(1500)
            self.chat_worker = None
        self._detach_audio_worker(self.tts_worker)
        self.tts_worker = None
        self._detach_audio_worker(self.welcome_worker)
        self.welcome_worker = None

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
        self.mic_btn.setChecked(True)
        self._start_recording()
