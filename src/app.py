# coding:utf-8
"""
MiniPet 应用组装入口。

MiniPetApp 是整个桌宠程序的协调层，负责把桌宠窗口、设置窗口、聊天记录、
回复卡片、外部智能体事件、语音识别和 TTS 串在一起。具体 UI 和协议实现
分散在各自模块中，这里只保留跨模块流程编排。
"""

import base64
import json
import mimetypes
import random
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentTranslator, setThemeColor

import config
from clients.asr_client import AsrWorker
from storage.chat_store import ChatStore
from pet.desktop_pet import DesktopPet
from clients.event_client import EventClient
from clients.llm_client import ChatWorker
from clients.openclaw_client import OpenClawWorker
from widgets.notifications.reply_card_center import ReplyCardCenter
from protocols.protocol_v1 import SESSION_PING, SESSION_PONG, SESSION_READY, SURFACE_CLOSE, SURFACE_SHOW, SURFACE_UPDATE, USER_INPUT, V1_CAPABILITIES, normalize_inbound_event
from protocols.surface_utils import is_silent_surface_text, is_terminal_surface_status, normalize_display_event, surface_text, surface_timeout
from settings_window import SettingsWindow
from clients.stream_tts import StreamTtsQueue
from clients.tts_client import TtsPreviewWorker, stop_tts
from clients.wake_word_client import WakeWordWorker
from clients.doubao_call_client import DoubaoCallWorker


WAKE_ACK_KEYS = ('wake_ack_1', 'wake_ack_2', 'wake_ack_3', 'wake_ack_4')
EVENT_CARD_AFTER_TTS_START_DELAY_MS = 450
GOODBYE_CARD_QUIT_DELAY_MS = 1800


class MiniPetApp(QApplication):
    """MiniPet 主应用对象。

    这个类是跨模块的“胶水层”：它不直接绘制桌宠或聊天窗口，而是负责创建
    DesktopPet、SettingsWindow、ReplyCardCenter 等对象，并通过 Qt 信号把
    用户操作、LLM 回复、TTS 播放和外部事件连接起来。

    运行时聊天上下文只保存在 self.chat_history 中。
    """

    def __init__(self, argv, start_event_client=True):
        super().__init__(argv)
        self.setQuitOnLastWindowClosed(False)
        config.load()
        self.setFont(QFont('Microsoft YaHei UI'))
        translator = FluentTranslator(QLocale(config.app_config.get('language_code', 'zh_CN')))
        self.installTranslator(translator)
        if config.app_config.get('theme_color'):
            setThemeColor(config.app_config['theme_color'])

        # 多屏环境下把主屏放到第一位，桌宠初始定位和找回逻辑都会优先参考它。
        screens = self.screens()
        primary = self.primaryScreen()
        if primary in screens:
            screens.insert(0, screens.pop(screens.index(primary)))

        self.pet = DesktopPet(screens)
        self.chat_store = ChatStore(config.DATA_DIR / 'chat')
        self.settings = SettingsWindow(self.chat_store)
        self.note = ReplyCardCenter()
        self.events = EventClient() if start_event_client else None
        if self.events and self._agent_backend() == 'custom':
            self.events.set_url(self._agent_ws_url())
        # 当前运行中的短期上下文；可选从磁盘恢复最近消息。
        self.chat_history = []
        self._restore_chat_history()
        # quick_chat_* 管理桌宠头顶快速输入：LLM 请求、回复卡片和可选 TTS 播报。
        self.quick_chat_worker = None
        self.openclaw_worker = None
        self._abandoned_reply_workers = []
        self.event_tts_worker = None
        self.quick_chat_source = 'quick_chat'
        self.quick_reply_card_id = None
        self._quick_stream_text = ''
        self._surface_cards = {}
        # 内置模型和外置 surface 都是“完整文本不断增长”的流式形态，
        # 统一交给 StreamTtsQueue 按小句切分并串行播放。
        self.quick_stream_tts = StreamTtsQueue(self, label='TTS', on_started=self._on_quick_stream_tts_started, on_idle=self._finish_quick_voice_if_tts_idle)
        self.external_stream_tts = StreamTtsQueue(self, label='External TTS', on_started=self._on_external_stream_tts_started, on_idle=self._finish_external_voice_if_tts_idle)

        # pet_voice_* 是桌宠旁边的轻量语音聊天状态，不等同于独立 豆包通话窗口。
        self.pet_voice_active = False
        self.pet.set_voice_chat_active(False)
        self.pet_voice_listening = False
        self.pet_voice_asr_worker = None
        self.pet_voice_waiting_reply = False
        self.pet_voice_paused = False
        self.pet_voice_paused_stage = 'idle'
        self.pet_voice_shared_screen = None  # 语音球屏幕共享
        self.wake_word_worker = None
        self.wake_ack_worker = None
        self.wake_ack_pending_start = False
        self.is_quitting = False
        self.startup_greeting_shown = False
        self.exit_card_shown = False

        self.pet.show_settings.connect(self.settings.show_window)
        self.pet.reply_card_text_requested.connect(lambda text, x, y, timeout: self.note.setup_reply_card_text(text, x, y, timeout, title=config.pet_display_name()))
        self.pet.chat_prompt_submitted.connect(self._on_quick_chat_prompt)
        self.pet.drop_intent_submitted.connect(self._on_drop_intent)
        self.pet.chat_requested.connect(self._show_chat_window)
        self.pet.voice_chat_requested.connect(self._toggle_voice_orb)
        self.pet.voice_pause_requested.connect(self._pause_pet_voice_chat)
        self.pet.voice_stop_requested.connect(self._stop_pet_voice_chat)
        self.pet.share_screen_requested.connect(self._on_voice_share_screen_toggled)
        self.pet.doubao_call_requested.connect(self._show_doubao_call_window)
        self.pet.quit_requested.connect(self._on_quit_requested)
        self.settings.settings_changed.connect(self.pet.apply_settings)
        self.settings.settings_changed.connect(self._apply_agent_settings)
        self.settings.settings_changed.connect(self._apply_wake_word_settings)
        self.settings.pet_changed.connect(self.pet.load_pet)
        self.note.reply_card_action_clicked.connect(self._on_reply_card_action)
        self.note.reply_card_interrupted.connect(self._on_reply_card_interrupted)
        if self.events:
            self.events.event_received.connect(self._on_event)
            self.events.connection_changed.connect(self._on_event_connection_changed)
            if self._agent_backend() == 'custom':
                self.events.start()
        self._apply_wake_word_settings()
        QTimer.singleShot(0, self._show_startup_greeting)

    def _memory_message_limit(self):
        turns = max(0, int(config.llm_config.get('memory_turns') or 0))
        return turns * 2

    def _restore_chat_history(self):
        """启动时默认恢复最近 N 轮历史消息，作为统一对话上下文。"""
        max_messages = self._memory_message_limit()
        if max_messages <= 0:
            return
        self.chat_history = self.chat_store.load_recent(max_messages)

    def _agent_backend(self):
        return config.app_config.get('agent_backend', 'builtin') or 'builtin'

    def _agent_ws_url(self):
        return config.app_config.get('custom_agent_ws_url') or config.CUSTOM_AGENT_WS_DEFAULT

    def _apply_agent_settings(self):
        if not self.events:
            return
        if self._agent_backend() != 'custom':
            self.events.stop()
            return
        self.events.set_url(self._agent_ws_url())
        if self.events.isRunning():
            self.events.reconnect()
        else:
            self.events.running = True
            self.events.start()

    def _continuous_voice_chat_enabled(self):
        return bool(config.voice_chat_config.get('continuous', False))

    def _wake_word_enabled(self):
        return self.pet_voice_active and bool(config.wake_word_config.get('enabled', False))

    def _apply_wake_word_settings(self):
        if not self._wake_word_enabled():
            self._stop_wake_word_listener()
            return
        if self.wake_word_worker is not None and self.wake_word_worker.isRunning():
            self.wake_word_worker.wake_config = dict(config.wake_word_config)
            self.wake_word_worker.resume()
            return
        self.wake_word_worker = WakeWordWorker(config.wake_word_config, parent=self)
        self.wake_word_worker.detected.connect(self._on_wake_word_detected)
        self.wake_word_worker.status_changed.connect(self._on_wake_word_status)
        self.wake_word_worker.error_received.connect(self._on_wake_word_error)
        self.wake_word_worker.finished.connect(self._on_wake_word_finished)
        self.wake_word_worker.start()

    def _stop_wake_word_listener(self):
        if self.wake_word_worker is None:
            return
        self.wake_word_worker.stop()
        self.wake_word_worker.wait(1200)
        self.wake_word_worker = None

    def _pause_wake_word_listener(self):
        if self.wake_word_worker is not None:
            self.wake_word_worker.pause()

    def _resume_wake_word_listener(self):
        if self._wake_word_enabled() and not self.pet_voice_listening and not self.pet_voice_waiting_reply:
            if self.wake_word_worker is not None and self.wake_word_worker.isRunning():
                self.wake_word_worker.resume()
            else:
                self._apply_wake_word_settings()

    def _on_wake_word_detected(self, text):
        if self.is_quitting or not self.pet_voice_active or self.pet_voice_listening or self.pet_voice_waiting_reply:
            return
        self._pause_wake_word_listener()
        self._play_wake_ack_then_start()

    def _wake_ack_sound_path(self):
        voice_name = config.tts_config.get('voice_name') or config.DEFAULT_TTS_CONFIG['voice_name']
        safe_voice = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in voice_name)
        key = random.choice(WAKE_ACK_KEYS)
        path = config.DATA_DIR / 'tts_wake_ack' / safe_voice / (key + '.pcm')
        return path if path.is_file() else None

    def _play_wake_ack_then_start(self):
        if not self.pet_voice_active or self.wake_ack_worker is not None:
            return
        self.wake_ack_pending_start = True
        self.pet.update_voice_popup('thinking', '')
        path = self._wake_ack_sound_path()
        if path is None:
            self._finish_wake_ack_start()
            return
        stop_tts()
        self.quick_stream_tts.reset()
        self.external_stream_tts.reset()
        self.wake_ack_worker = TtsPreviewWorker(path, parent=self)
        self.wake_ack_worker.result_ready.connect(self._on_wake_ack_done)
        self.wake_ack_worker.start()

    def _finish_wake_ack_start(self):
        if self.wake_ack_pending_start and self.pet_voice_active and not self.pet_voice_paused:
            self.wake_ack_pending_start = False
            self._start_pet_voice_chat_once('wake_word')

    def _on_wake_ack_done(self, success, text):
        if not success:
            print('Wake ack audio failed:', text)
        self.wake_ack_worker = None
        self._finish_wake_ack_start()

    def _on_wake_word_status(self, text):
        if text and text not in ('等待唤醒词',):
            print('WakeWord:', text)

    def _on_wake_word_error(self, text):
        print('WakeWord error:', text)
        self.wake_word_worker = None

    def _on_wake_word_finished(self):
        self.wake_word_worker = None

    def _event_tts_path(self, event_name):
        voice_name = config.tts_config.get('voice_name') or config.DEFAULT_TTS_CONFIG['voice_name']
        safe_name = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in voice_name)
        return config.DATA_DIR / 'tts_events' / f'{safe_name}_{event_name}.pcm'

    def _play_event_tts(self, event_name):
        path = self._event_tts_path(event_name)
        if not path.is_file():
            return False
        stop_tts()
        self.quick_stream_tts.reset()
        self.external_stream_tts.reset()
        self.event_tts_worker = TtsPreviewWorker(path, parent=self)
        self.event_tts_worker.result_ready.connect(lambda success, text: self._on_event_tts_done(event_name, success, text))
        self.event_tts_worker.start()
        return True

    def _on_event_tts_done(self, event_name, success, text):
        if not success:
            print('Event TTS failed:', text)
        self.event_tts_worker = None
        if event_name == 'exit' and self.is_quitting:
            self._show_exit_card()
            QTimer.singleShot(300 if success else GOODBYE_CARD_QUIT_DELAY_MS, self.pet.quit_now)

    def _show_startup_greeting(self):
        if self._play_event_tts('startup'):
            QTimer.singleShot(EVENT_CARD_AFTER_TTS_START_DELAY_MS, self._show_startup_greeting_card)
            return
        self._show_startup_greeting_card()

    def _show_startup_greeting_card(self):
        if self.startup_greeting_shown:
            return
        self.startup_greeting_shown = True
        x, y = self.pet.reply_card_anchor()
        name = config.pet_display_name()
        self.note.setup_reply_card_text('好久不见，想我了吗？', x, y, 6000, title=name)

    def _show_exit_card(self):
        if self.exit_card_shown:
            return
        self.exit_card_shown = True
        x, y = self.pet.reply_card_anchor()
        self.note.setup_reply_card_text('我会想你的，再见~', x, y, 3000, title=config.pet_display_name())

    def _show_chat_window(self):
        self.pet.show_chat(self.chat_history, self._append_chat_message, self.chat_store.content_for_llm, self._build_system_prompt, self._clear_chat_history)

    def _toggle_pet_voice_chat(self):
        """兼容旧调用：切换语音球显示状态。"""
        self._toggle_voice_orb()

    def _toggle_voice_orb(self):
        if self.pet_voice_active:
            self._stop_pet_voice_chat()
            return
        self._open_voice_orb()

    def _open_voice_orb(self):
        self.pet.show_voice_popup()
        if not config.tts_config.get('api_key'):
            self.pet.update_voice_popup('error', '缺少语音配置')
            x, y = self.pet.reply_card_anchor()
            self.note.setup_reply_card_text('请先在设置 > 语音中填写 TTS API Key', x, y, 4000, title=config.pet_display_name())
            QTimer.singleShot(1800, self.pet.close_voice_popup)
            return
        self.pet_voice_active = True
        self.pet.set_voice_chat_active(True)
        self.pet_voice_waiting_reply = False
        self.pet_voice_paused = False
        self.pet.update_voice_popup('wakeup' if self._wake_word_enabled() else 'idle', '')
        if self._wake_word_enabled():
            self._apply_wake_word_settings()

    def _start_pet_voice_chat_once(self, trigger='menu'):
        """启动一次本地 AI 语音接听，后续是否继续由连续对话开关控制。"""
        if self.pet_voice_active:
            self.pet.show_voice_popup()
            if trigger == 'wake_word' and not self.pet_voice_listening and not self.pet_voice_waiting_reply:
                self._pause_wake_word_listener()
                self._start_pet_voice_recording()
            return
        self.pet.show_voice_popup()
        if not config.tts_config.get('api_key'):
            self.pet.update_voice_popup('error', '缺少语音配置')
            x, y = self.pet.reply_card_anchor()
            self.note.setup_reply_card_text('请先在设置 > 语音中填写 TTS API Key', x, y, 4000, title=config.pet_display_name())
            QTimer.singleShot(1800, self.pet.close_voice_popup)
            return
        self.pet_voice_active = True
        self.pet.set_voice_chat_active(True)
        self.pet_voice_waiting_reply = False
        self.pet_voice_paused = False
        if self._wake_word_enabled() and trigger != 'wake_word':
            self.pet.update_voice_popup('wakeup', '')
            self._apply_wake_word_settings()
            return
        self._pause_wake_word_listener()
        self._start_pet_voice_recording()

    def _start_pet_voice_recording(self):
        if not self.pet_voice_active or self.pet_voice_paused or self.quick_chat_worker is not None or self.pet_voice_waiting_reply:
            return
        self.pet_voice_listening = True
        self.pet.update_voice_popup('listening', '')
        if self.pet_voice_asr_worker is not None and not self.pet_voice_asr_worker.isRunning():
            self.pet_voice_asr_worker = None
        if self.pet_voice_asr_worker is None:
            self.pet_voice_asr_worker = AsrWorker(parent=self)
            self.pet_voice_asr_worker.status_changed.connect(self._on_pet_voice_status)
            self.pet_voice_asr_worker.text_received.connect(self._on_pet_voice_text)
            self.pet_voice_asr_worker.final_received.connect(self._on_pet_voice_final)
            self.pet_voice_asr_worker.error_received.connect(self._on_pet_voice_error)
            self.pet_voice_asr_worker.finished_signal.connect(self._on_pet_voice_finished)
            self.pet_voice_asr_worker.start()
        QTimer.singleShot(250, self.pet_voice_asr_worker.start_recording)

    def _stop_pet_voice_recording(self):
        self.pet_voice_listening = False
        if self.pet_voice_asr_worker is not None:
            self.pet_voice_asr_worker.stop_recording()

    def _pause_pet_voice_chat(self):
        if not self.pet_voice_active:
            return
        if self.pet_voice_paused:
            self.pet_voice_paused = False
            if self.pet_voice_paused_stage == 'wakeup':
                self.pet.update_voice_popup('wakeup', '')
                self._resume_wake_word_listener()
            else:
                self._start_pet_voice_recording()
            self.pet_voice_paused_stage = 'idle'
            return
        self.pet_voice_paused = True
        if self.pet_voice_listening or self.pet_voice_waiting_reply or self.quick_stream_tts.is_active() or self.external_stream_tts.is_active() or self.wake_ack_worker is not None:
            self.pet_voice_paused_stage = 'recording'
        elif self._wake_word_enabled():
            self.pet_voice_paused_stage = 'wakeup'
        else:
            self.pet_voice_paused_stage = 'recording'
        self._pause_wake_word_listener()
        self._stop_pet_voice_recording()
        stop_tts()
        self._cancel_current_reply_workers()
        self.quick_stream_tts.reset()
        self.external_stream_tts.reset()
        self.pet_voice_waiting_reply = False
        self.pet.update_voice_popup('idle', '已暂停，单击继续')
        QTimer.singleShot(1600, self._shrink_paused_voice_popup)

    def _shrink_paused_voice_popup(self):
        if self.pet_voice_active and self.pet_voice_paused:
            self.pet.update_voice_popup('idle', '')

    def _stop_pet_voice_chat(self):
        self.pet_voice_active = False
        self.pet.set_voice_chat_active(False)
        self.pet_voice_listening = False
        self.pet_voice_waiting_reply = False
        self.pet_voice_paused = False
        self.pet_voice_paused_stage = 'idle'
        self.pet_voice_shared_screen = None
        self._stop_wake_word_listener()
        if self.pet_voice_asr_worker is not None:
            self.pet_voice_asr_worker.finish()
            self.pet_voice_asr_worker.wait(1200)
            self.pet_voice_asr_worker = None
        if self.wake_ack_worker is not None:
            self.wake_ack_pending_start = False
            stop_tts()
            self.wake_ack_worker.wait(1200)
            self.wake_ack_worker = None
        stop_tts()
        self._cancel_current_reply_workers()
        self.quick_stream_tts.reset()
        self.external_stream_tts.reset()
        self.pet.close_voice_popup()
        if not self.is_quitting:
            QTimer.singleShot(int(config.wake_word_config.get('restart_delay_ms') or 1200), self._resume_wake_word_listener)

    def _on_voice_share_screen_toggled(self, enabled):
        if not config.SCREEN_SHARE_ENABLED:
            self.pet_voice_shared_screen = None
            return
        if enabled:
            screen = QApplication.primaryScreen()
            self.pet_voice_shared_screen = screen
        else:
            self.pet_voice_shared_screen = None

    def _capture_voice_screenshot(self):
        if not config.SCREEN_SHARE_ENABLED:
            return ''
        import base64
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice
        from PySide6.QtCore import Qt as _Qt
        screen = self.pet_voice_shared_screen
        if screen is None:
            return ''
        pixmap = screen.grabWindow(0)
        if pixmap.isNull():
            return ''
        image = pixmap.toImage()
        if image.width() > 1280:
            image = image.scaledToWidth(1280, _Qt.SmoothTransformation)
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        image.save(buf, 'JPEG', 85)
        return 'data:image/jpeg;base64,' + base64.b64encode(bytes(data)).decode('ascii')

    def _on_pet_voice_status(self, text):
        if self.pet_voice_active and not self.pet_voice_paused and text in ('ASR已连接', '正在识别') and self.quick_chat_worker is None and not self.quick_stream_tts.is_active():
            self.pet.update_voice_popup('listening', '')

    def _on_pet_voice_text(self, text):
        if self.pet_voice_active and not self.pet_voice_paused and text and self.quick_chat_worker is None and not self.quick_stream_tts.is_active():
            self.pet.update_voice_popup('listening', text)

    def _on_pet_voice_final(self, text):
        text = (text or '').strip()
        if not text or not self.pet_voice_active or self.pet_voice_paused or self.pet_voice_waiting_reply:
            return
        self._stop_pet_voice_recording()
        self.pet_voice_waiting_reply = True
        self.pet.update_voice_popup('thinking', text)
        screenshot = self._capture_voice_screenshot()
        if self._agent_backend() == 'builtin':
            submitted = self._submit_quick_chat(text, 'voice_chat', screenshot=screenshot)
        else:
            submitted = self._send_external_command(text, 'voice', 'voice_orb', screenshot=screenshot)
            if submitted:
                self.quick_chat_source = 'voice_chat'
                self.pet.update_voice_popup('thinking', '等待回复')
        if not submitted:
            self.pet_voice_waiting_reply = False
            if self.pet_voice_active:
                QTimer.singleShot(800, self._start_pet_voice_recording)

    def _on_pet_voice_error(self, text):
        if self.pet_voice_active:
            self.pet.update_voice_popup('error', str(text)[:60])
            x, y = self.pet.reply_card_anchor()
            self.note.setup_reply_card_text('语音识别出错：' + str(text), x, y, 5000, title=config.pet_display_name())
        self._stop_pet_voice_chat()

    def _on_pet_voice_finished(self):
        self.pet_voice_asr_worker = None

    def _show_doubao_call_window(self):
        self.pet.show_doubao_call(None)

    def _on_quit_requested(self):
        if self.is_quitting:
            return
        self.is_quitting = True
        if self.pet.quick_menu is not None:
            self.pet.quick_menu.close()
        if self.pet_voice_active or self.pet_voice_asr_worker is not None:
            self._stop_pet_voice_chat()
        self._stop_wake_word_listener()
        if self._play_event_tts('exit'):
            QTimer.singleShot(EVENT_CARD_AFTER_TTS_START_DELAY_MS, self._show_exit_card)
        else:
            self._show_exit_card()
            QTimer.singleShot(GOODBYE_CARD_QUIT_DELAY_MS, self.pet.quit_now)

    def _append_chat_message(self, role, content, source):
        """保存一条聊天消息，并同步到当前运行中的短期上下文。"""
        stored_message = self.chat_store.append(role, content, source, pet_name=config.pet_display_name())
        self.chat_history.append(stored_message)
        return stored_message

    def _clear_chat_history(self):
        self.chat_history.clear()
        self.chat_store.clear_all()

    def _build_system_prompt(self):
        """组合角色设定，作为 LLM system prompt。"""
        name = config.pet_display_name()
        prompt = (config.llm_config.get('system_prompt', '') or '').strip()
        if name:
            return '你的名字是：%s。\n%s' % (name, prompt)
        return prompt

    def _content_text_for_preview(self, content):
        if isinstance(content, str):
            return content
        parts = []
        for block in content or []:
            if block.get('type') == 'text':
                parts.append(block.get('text', ''))
            elif block.get('type') == 'code':
                parts.append(block.get('text', ''))
        return '\n'.join(part for part in parts if part).strip()

    def _content_preview(self, content):
        if isinstance(content, str):
            return content
        text = self._content_text_for_preview(content)
        image_count = sum(1 for block in content or [] if block.get('type') == 'image')
        return (text + '\n' if text else '') + ('[图片] × %d' % image_count if image_count else '')

    def _attachment_from_data_url(self, data_url, name='image.png', source='input'):
        data_url = str(data_url or '').strip()
        if not data_url.startswith('data:') or ';base64,' not in data_url:
            return None
        header, data = data_url.split(',', 1)
        mime_type = header[5:].split(';', 1)[0] or 'application/octet-stream'
        if not data:
            return None
        return {
            'type': 'image',
            'name': name,
            'mime_type': mime_type,
            'encoding': 'base64',
            'data': data,
            'source': source,
        }

    def _attachment_from_image_file(self, file_path, source='drop'):
        path = Path(str(file_path or ''))
        if not path.is_file():
            return None
        mime_type = mimetypes.guess_type(str(path))[0] or ''
        if not mime_type.startswith('image/'):
            return None
        return {
            'type': 'image',
            'name': path.name,
            'mime_type': mime_type,
            'encoding': 'base64',
            'data': base64.b64encode(path.read_bytes()).decode('ascii'),
            'source': source,
        }

    def _content_attachments(self, content, screenshot=''):
        attachments = []
        if screenshot:
            item = self._attachment_from_data_url(screenshot, name='screenshot.jpg', source='screenshot')
            if item:
                attachments.append(item)
        if isinstance(content, list):
            for index, block in enumerate(content):
                if block.get('type') != 'image':
                    continue
                src = block.get('src') or block.get('path') or block.get('data_url') or ''
                item = self._attachment_from_data_url(src, name=block.get('name') or 'image_%d.png' % (index + 1), source='message')
                if item is None:
                    item = self._attachment_from_image_file(src, source='message')
                if item:
                    attachments.append(item)
        return attachments

    def _drop_attachments(self, payload):
        attachments = []
        for index, item in enumerate(payload.get('items') or []):
            if item.get('kind') not in ('image', 'file'):
                continue
            attachment = self._attachment_from_data_url(item.get('data_url'), name=item.get('name') or 'drop_%d.png' % (index + 1), source='drop')
            if attachment is None:
                attachment = self._attachment_from_image_file(item.get('path'), source='drop')
            if attachment:
                attachments.append(attachment)
        return attachments

    def _drop_payload_without_inline_image_data(self, payload):
        data = dict(payload or {})
        items = []
        for item in data.get('items') or []:
            clean = dict(item)
            clean.pop('data_url', None)
            items.append(clean)
        data['items'] = items
        return data

    def _user_input_payload(self, content, mode='text', surface='pet_popup', screenshot='', attachments=None):
        text = self._content_text_for_preview(content)
        preview = self._content_preview(content)
        payload = {
            'text': text or preview,
            'preview': preview,
            'mode': mode,
            'surface': surface,
        }
        merged = list(attachments or [])
        merged.extend(self._content_attachments(content, screenshot=screenshot))
        if merged:
            payload['attachments'] = merged
        return payload

    def _openclaw_input_payload(self, content, screenshot='', attachments=None):
        text = self._content_text_for_preview(content) or self._content_preview(content)
        merged = list(attachments or [])
        merged.extend(self._content_attachments(content, screenshot=screenshot))
        if not merged:
            return text
        parts = [{'type': 'input_text', 'text': text or '请处理图片内容'}]
        for item in merged:
            if item.get('type') != 'image' or item.get('encoding') != 'base64' or not item.get('data'):
                continue
            mime_type = item.get('mime_type') or 'image/png'
            parts.append({
                'type': 'input_image',
                'image_url': 'data:%s;base64,%s' % (mime_type, item.get('data')),
            })
        return [{'role': 'user', 'content': parts}]

    def _send_external_command(self, content, mode='text', surface='pet_popup', screenshot=''):
        if self._agent_backend() == 'openclaw':
            return self._send_openclaw_prompt(content, mode, screenshot=screenshot)
        x, y = self.pet.reply_card_anchor()
        self.note.setup_reply_card_text(self._content_preview(content), x, y, 2000, title='你')
        if mode in ('text', 'voice'):
            self._begin_reply_card_turn()
            self._reset_external_stream_tts()
            self._show_reply_card('正在思考...', status='streaming', timeout_ms=60000)
        payload = self._user_input_payload(content, mode=mode, surface=surface, screenshot=screenshot)
        sent = self.events.send_event(USER_INPUT, payload) if self.events else False
        if not sent:
            self._close_reply_card()
            self.note.setup_reply_card_text('外置智能体还没连接，先检查“智能体”设置。', x, y, 4500, title=config.pet_display_name())
        return sent

    def _send_openclaw_prompt(self, content, mode='text', screenshot='', attachments=None):
        if self.openclaw_worker is not None:
            x, y = self.pet.reply_card_anchor()
            self.note.setup_reply_card_text('OpenClaw 还在处理上一句话，稍等一下。', x, y, 3000, title=config.pet_display_name())
            return False
        prompt = self._content_preview(content).strip()
        openclaw_input = self._openclaw_input_payload(content, screenshot=screenshot, attachments=attachments)
        has_input = bool(prompt) or (isinstance(openclaw_input, list) and bool(openclaw_input[0].get('content')))
        if not has_input:
            return False
        x, y = self.pet.reply_card_anchor()
        self.quick_chat_source = 'voice_chat' if mode == 'voice' else 'quick_chat'
        self.note.setup_reply_card_text(prompt, x, y, 2000, title='你')
        self._begin_reply_card_turn()
        self._reset_external_stream_tts()
        self._show_reply_card('正在问 OpenClaw...', status='streaming', timeout_ms=60000)
        self.openclaw_worker = OpenClawWorker(openclaw_input, parent=self)
        self.openclaw_worker.delta_ready.connect(self._on_openclaw_delta)
        self.openclaw_worker.result_ready.connect(self._on_openclaw_reply)
        self.openclaw_worker.start()
        return True

    def _on_openclaw_delta(self, text):
        if not text:
            return
        self._quick_stream_text += text
        shown = self._quick_stream_text.strip()
        if not shown:
            return
        self._show_reply_card(shown, status='streaming', timeout_ms=60000)
        self.external_stream_tts.queue_text('openclaw-reply', shown, terminal=False)

    def _on_openclaw_reply(self, success, text):
        self.openclaw_worker = None
        reply = (text or self._quick_stream_text or '').strip()
        if success:
            reply = reply or 'OpenClaw 没有返回文本。'
            self._show_reply_card(reply, status='done', timeout_ms=max(5000, min(25000, len(reply) * 180)))
            self._quick_stream_text = reply
            self.external_stream_tts.queue_text('openclaw-reply', reply, terminal=True)
            self._finish_external_voice_if_tts_idle()
            return
        self._reset_external_stream_tts()
        self._show_reply_card(reply or '调用 OpenClaw 失败。', status='failed', timeout_ms=8000)
        if self.quick_chat_source == 'voice_chat' and self.pet_voice_active:
            self._finish_voice_turn(delay_ms=800)

    def _show_reply_card(self, content, status='streaming', timeout_ms=60000):
        event = {
            'surface_id': 'local-quick-reply',
            'content': content,
            'status': status,
            'timeout_ms': timeout_ms,
        }
        x, y = self.pet.reply_card_anchor()
        if self.quick_reply_card_id and self.note.update_reply_card(self.quick_reply_card_id, event, timeout=timeout_ms):
            return
        self.quick_reply_card_id = self.note.setup_reply_card(event, x, y, play_sound=False)

    def _begin_reply_card_turn(self):
        self.quick_reply_card_id = None
        self._quick_stream_text = ''

    def _close_reply_card(self):
        if self.quick_reply_card_id:
            self.note.close_reply_card(self.quick_reply_card_id)
            self.quick_reply_card_id = None

    def _on_quick_chat_prompt(self, text):
        if self._agent_backend() == 'builtin':
            self._submit_quick_chat(text, 'quick_chat')
            return
        self._send_external_command(text, 'text', 'pet_popup')
        # 外置后端会用 surface 卡片回复，不使用快速输入弹窗自己的思考浮层。
        # submitted 信号返回后 PetInputPopup 才会 start_thinking，所以延后一拍关闭。
        QTimer.singleShot(0, self._close_input_popup)

    def _close_input_popup(self):
        if self.pet.input_popup is not None:
            self.pet.input_popup.close()
            self.pet.input_popup = None

    def _on_drop_intent(self, drop_payload, intent):
        payload = dict(drop_payload)
        payload['intent'] = intent
        payload['surface'] = 'desktop_pet'
        payload['context'] = {'surface': 'desktop_pet'}
        x, y = self.pet.reply_card_anchor()
        intent_labels = {
            'summarize': '总结',
            'create_task': '生成待办',
            'draft_reply': '起草回复',
            'send_to_lark': '发到飞书',
            'ask': '询问处理方式',
        }
        if self._agent_backend() == 'builtin':
            prompt = self._drop_prompt_for_builtin(payload, intent_labels.get(intent, intent))
            self._submit_quick_chat(prompt, 'drop')
            return
        if self._agent_backend() == 'openclaw':
            self._send_openclaw_prompt(
                self._drop_prompt_for_builtin(payload, intent_labels.get(intent, intent)),
                'text',
                attachments=self._drop_attachments(payload),
            )
            return
        prompt = self._drop_prompt_for_builtin(payload, intent_labels.get(intent, intent))
        event_payload = self._user_input_payload(
            prompt,
            mode='drop',
            surface='desktop_pet',
            attachments=self._drop_attachments(payload),
        )
        event_payload.update({
            'intent': intent,
            'drop': self._drop_payload_without_inline_image_data(payload),
        })
        sent = self.events.send_event(USER_INPUT, event_payload) if self.events else False
        if sent:
            self.note.setup_reply_card_text('收到，我交给外置智能体处理：' + intent_labels.get(intent, intent), x, y, 3500, title=config.pet_display_name())
        else:
            self.note.setup_reply_card_text('外置智能体还没连接，先检查“智能体”设置。', x, y, 4500, title=config.pet_display_name())

    def _drop_prompt_for_builtin(self, payload, intent_label):
        lines = ['用户投喂了内容，希望你处理：%s。' % intent_label]
        preview = payload.get('preview') or ''
        if preview:
            lines.append('预览：' + str(preview))
        items = payload.get('items') or []
        if items:
            lines.append('投喂项：')
            for item in items:
                lines.append('- ' + json.dumps(item, ensure_ascii=False))
        return '\n'.join(lines)

    def _submit_quick_chat(self, text, source='quick_chat', screenshot=''):
        """提交桌宠快速输入或语音识别文本到内置 LLM。"""
        if self.quick_chat_worker is not None:
            if source == 'quick_chat' and self.pet.input_popup is not None:
                self.pet.input_popup.close()
                self.pet.input_popup = None
            x, y = self.pet.reply_card_anchor()
            self.note.setup_reply_card_text('我还在想上一句话，稍等一下。', x, y, 3000, title=config.pet_display_name())
            return False
        self.quick_chat_source = source
        self._append_chat_message('user', text, source)
        if self.pet.chat_window is not None and self.pet.chat_window.isVisible():
            self.pet.chat_window.reload_history()
        self._begin_reply_card_turn()
        self._reset_quick_stream_tts()
        self._show_reply_card('正在思考...', status='streaming', timeout_ms=60000)
        self.quick_chat_worker = ChatWorker(self._build_quick_chat_messages(screenshot=screenshot), parent=self)
        self.quick_chat_worker.delta_ready.connect(self._on_quick_chat_delta)
        self.quick_chat_worker.result_ready.connect(self._on_quick_chat_reply)
        self.quick_chat_worker.start()
        return True

    def _build_quick_chat_messages(self, screenshot=''):
        """构造快速聊天的 LLM 消息，只保留最近 10 条上下文。"""
        messages = []
        system = self._build_system_prompt()
        if system:
            messages.append({'role': 'system', 'content': system})
        memory_limit = self._memory_message_limit()
        history = list(self.chat_history[-memory_limit:] if memory_limit > 0 else [])
        # 历史消息除最后一条外都用纯文本
        for message in history[:-1]:
            messages.append({'role': message.get('role'), 'content': self.chat_store.content_for_llm(message.get('content', ''))})
        # 最后一条（刚刚说的那句话）附加截图
        if history:
            last = history[-1]
            text = self.chat_store.content_for_llm(last.get('content', ''))
            if screenshot and last.get('role') == 'user':
                content = [
                    {'type': 'image_url', 'image_url': {'url': screenshot}},
                    {'type': 'text', 'text': text},
                ]
            else:
                content = text
            messages.append({'role': last.get('role'), 'content': content})
        return messages

    def _on_quick_chat_delta(self, text):
        if not text or self.quick_chat_worker is None:
            return
        self._quick_stream_text += text
        shown = self._quick_stream_text.strip()
        if shown:
            self._show_reply_card(shown, status='streaming', timeout_ms=60000)
            self.quick_stream_tts.queue_text('quick-reply', shown, terminal=False)

    def _on_quick_chat_reply(self, success, text):
        """处理快速聊天回复：保存历史、展示回复卡片，并按配置触发 TTS。"""
        self.quick_chat_worker = None
        if self.quick_chat_source == 'quick_chat' and self.pet.input_popup is not None:
            self.pet.input_popup.close()
            self.pet.input_popup = None
        if success:
            reply = (text or self._quick_stream_text).strip() or '嗯。'
            self._append_chat_message('assistant', reply, self.quick_chat_source or 'quick_chat')
            if self.pet.chat_window is not None and self.pet.chat_window.isVisible():
                self.pet.chat_window.reload_history()
            self._show_reply_card(reply, status='done', timeout_ms=max(5000, min(25000, len(reply) * 180)))
            self._quick_stream_text = reply
            self.quick_stream_tts.queue_text('quick-reply', reply, terminal=True)
            self._finish_quick_voice_if_tts_idle()
        else:
            self._reset_quick_stream_tts()
            self._show_reply_card('我现在说不出来：' + text, status='failed', timeout_ms=6000)
            if self.quick_chat_source == 'voice_chat' and self.pet_voice_active:
                self._finish_voice_turn(delay_ms=800)

    def _on_quick_stream_tts_started(self, stream_id, text):
        if self.quick_chat_source == 'voice_chat' and self.pet_voice_active:
            self.pet.update_voice_popup('speaking', '')

    def _finish_quick_voice_if_tts_idle(self):
        if self.quick_stream_tts.is_active():
            return
        if self.quick_chat_source == 'voice_chat' and self.pet_voice_active:
            self._finish_voice_turn(delay_ms=500)

    def _on_external_stream_tts_started(self, stream_id, text):
        if self.quick_chat_source == 'voice_chat' and self.pet_voice_active:
            self.pet.update_voice_popup('speaking', '')

    def _finish_external_voice_if_tts_idle(self):
        if self.external_stream_tts.is_active():
            return
        if self.quick_chat_source == 'voice_chat' and self.pet_voice_active:
            self._finish_voice_turn(delay_ms=500)

    def _reset_quick_stream_tts(self):
        self._quick_stream_text = ''
        self.quick_stream_tts.reset()

    def _finish_voice_turn(self, delay_ms=500):
        self.pet_voice_waiting_reply = False
        if not self.pet_voice_active or self.pet_voice_paused:
            return
        if self._continuous_voice_chat_enabled():
            self.pet.update_voice_popup('listening', '')
            QTimer.singleShot(delay_ms, self._start_pet_voice_recording)
            return
        self.pet_voice_paused = False
        if self._wake_word_enabled():
            self.pet.update_voice_popup('wakeup', '')
            QTimer.singleShot(int(config.wake_word_config.get('restart_delay_ms') or 1200), self._resume_wake_word_listener)
        else:
            self.pet.update_voice_popup('idle', '')

    def _on_event_connection_changed(self, connected):
        pass

    def _on_event(self, event):
        event = normalize_inbound_event(event)
        event_type = event.get('type', '')
        payload = event.get('payload') if isinstance(event.get('payload'), dict) else event
        x, y = self.pet.reply_card_anchor()
        if event_type == SESSION_READY:
            server = payload.get('server') if isinstance(payload.get('server'), dict) else {}
            self.note.setup_reply_card_text('后端已就绪：' + str(server.get('name') or payload.get('name') or '智能体'), x, y, 3000, title=config.pet_display_name())
        elif event_type == SURFACE_SHOW:
            self._handle_surface_show(payload)
        elif event_type == SURFACE_UPDATE:
            self._handle_surface_update(payload)
        elif event_type == SURFACE_CLOSE:
            self._handle_surface_close(payload)
        elif event_type == SESSION_PING:
            if self.events:
                self.events.send_event(SESSION_PONG, {'ts': payload.get('ts')})
        else:
            self.note.setup_toast(payload.get('title', '外部事件'), payload.get('summary') or payload.get('content') or '')

    def _handle_surface_show(self, payload):
        card_event = normalize_display_event(SURFACE_SHOW, payload)
        self._close_reply_card()
        text = surface_text(card_event)
        self._queue_external_reply_tts(card_event, text)
        if is_silent_surface_text(text) and not card_event.get('elements') and not card_event.get('actions') and not card_event.get('controls'):
            return
        x, y = self.pet.reply_card_anchor()
        card_id = self.note.setup_reply_card(card_event, x, y, play_sound=False)
        surface_id = card_event.get('surface_id')
        if surface_id:
            self._surface_cards[surface_id] = card_id
        self._handle_external_voice_surface(card_event)
        if surface_id and is_terminal_surface_status(card_event):
            self._surface_cards.pop(surface_id, None)

    def _handle_surface_update(self, payload):
        surface_id = payload.get('surface_id')
        if not surface_id:
            return
        card_event = normalize_display_event(SURFACE_UPDATE, payload)
        self._close_reply_card()
        text = surface_text(card_event)
        self._queue_external_reply_tts(card_event, text)
        if is_silent_surface_text(text) and not card_event.get('elements') and not card_event.get('actions') and not card_event.get('controls'):
            return
        timeout = surface_timeout(card_event)
        card_id = self._surface_cards.get(surface_id)
        if card_id and self.note.update_reply_card(card_id, card_event, timeout=timeout):
            self._handle_external_voice_surface(card_event)
            if is_terminal_surface_status(card_event):
                self._surface_cards.pop(surface_id, None)
            return
        x, y = self.pet.reply_card_anchor()
        card_id = self.note.setup_reply_card(card_event, x, y, play_sound=False)
        self._surface_cards[surface_id] = card_id
        self._handle_external_voice_surface(card_event)
        if is_terminal_surface_status(card_event):
            self._surface_cards.pop(surface_id, None)

    def _queue_external_reply_tts(self, card_event, text):
        if self._agent_backend() == 'builtin' or not text:
            return
        if is_silent_surface_text(text):
            return
        # 空正文终态帧只表示 surface 生命周期结束，不再回读旧正文补触发 TTS。
        surface_id = card_event.get('surface_id') or '__external_reply__'
        terminal = is_terminal_surface_status(card_event)
        self.external_stream_tts.queue_text(surface_id, text, terminal=terminal)

    def _reset_external_stream_tts(self):
        self.external_stream_tts.reset()

    def _handle_external_voice_surface(self, card_event):
        if not self.pet_voice_active or not self.pet_voice_waiting_reply or self.quick_chat_source != 'voice_chat':
            return
        text = surface_text(card_event)
        if text:
            # 外置后端已经用卡片在回复了，语音等待浮层不应该继续盖在卡片上。
            # V1 surface 协议不允许后端控制宠物动作；有正文后就清掉本地等待动作。
            self.pet.close_voice_popup()
            self.pet.play_action('idle')
        if is_terminal_surface_status(card_event):
            self._finish_external_voice_if_tts_idle()

    def _handle_surface_close(self, payload):
        surface_id = payload.get('surface_id')
        if not surface_id:
            return
        card_id = self._surface_cards.pop(surface_id, None)
        if card_id:
            self.note.close_reply_card(card_id)
        self.external_stream_tts.reset(surface_id)

    def _on_reply_card_action(self, event, action):
        action_id = action.get('id') or action.get('type')
        text = action.get('text') or event.get('suggestion') or event.get('summary') or event.get('content') or ''
        x, y = self.pet.reply_card_anchor()
        if action_id == 'ignore':
            return
        if action_id == 'copy':
            QGuiApplication.clipboard().setText(text)
            self.note.setup_reply_card_text('已复制到剪贴板', x, y, 3000)
            return
        if action_id == 'open_chat':
            self._show_chat_window()
            return
        if action_id == 'later':
            self.note.setup_reply_card_text(f'稍后提醒功能会在 {config.APP_DISPLAY_NAME} 本地提醒模块中接入', x, y, 4000)
            return
        if self.events:
            self.events.execute_action(event, action)

    def _on_reply_card_interrupted(self, _card_id):
        self._cancel_current_reply_workers()
        self.quick_stream_tts.reset()
        self.external_stream_tts.reset()
        if self.pet_voice_active and self.pet_voice_waiting_reply:
            self._finish_voice_turn(delay_ms=300)

    def _cancel_current_reply_workers(self):
        for attr, delta_slot, result_slot in (
            ('quick_chat_worker', self._on_quick_chat_delta, self._on_quick_chat_reply),
            ('openclaw_worker', self._on_openclaw_delta, self._on_openclaw_reply),
        ):
            worker = getattr(self, attr, None)
            if worker is None:
                continue
            try:
                worker.delta_ready.disconnect(delta_slot)
            except (TypeError, RuntimeError):
                pass
            try:
                worker.result_ready.disconnect(result_slot)
            except (TypeError, RuntimeError):
                pass
            if worker.isRunning():
                worker.requestInterruption()
                self._abandoned_reply_workers.append(worker)
                worker.finished.connect(lambda w=worker: self._forget_abandoned_reply_worker(w))
            setattr(self, attr, None)

    def _forget_abandoned_reply_worker(self, worker):
        if worker in self._abandoned_reply_workers:
            self._abandoned_reply_workers.remove(worker)

    def shutdown(self):
        stop_tts()
        self.settings.shutdown()
        if self.pet.chat_window is not None:
            self.pet.chat_window.shutdown()
        if self.pet.doubao_call_window is not None:
            self.pet.doubao_call_window.shutdown()
        self.pet.close_voice_popup()
        self.quick_stream_tts.reset()
        self.external_stream_tts.reset()
        if self.pet_voice_asr_worker is not None:
            self.pet_voice_asr_worker.finish()
            self.pet_voice_asr_worker.wait(1500)
            self.pet_voice_asr_worker = None
        for worker_name in ('quick_chat_worker', 'openclaw_worker', 'event_tts_worker', 'wake_ack_worker'):
            worker = getattr(self, worker_name, None)
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.quit()
                worker.wait(1000)
            setattr(self, worker_name, None)
        self.pet._stop_animation()
        if self.events:
            self.events.stop()
            self.events = None


def main():
    app = MiniPetApp(sys.argv)
    signal.signal(signal.SIGINT, lambda signum, frame: app.pet.quit_now())
    signal.signal(signal.SIGTERM, lambda signum, frame: app.pet.quit_now())
    timer = QTimer()
    timer.start(250)
    timer.timeout.connect(lambda: None)
    code = app.exec()
    app.shutdown()
    sys.exit(code)
