# coding:utf-8
import signal
import sys

from PySide6.QtCore import QLocale, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentTranslator, setThemeColor

from miniPet import config
from miniPet.chat_store import ChatStore
from miniPet.desktop_pet import DesktopPet
from miniPet.event_client import EventClient
from miniPet.llm_client import ChatWorker
from miniPet.notification import NotificationCenter
from miniPet.settings_window import SettingsWindow
from miniPet.tts_client import TtsPreviewWorker, TtsWorker, stop_tts


class MiniPetApp(QApplication):
    def __init__(self, argv, start_event_client=True):
        super().__init__(argv)
        self.setQuitOnLastWindowClosed(False)
        config.load()
        translator = FluentTranslator(QLocale(config.app_config.get('language_code', 'zh_CN')))
        self.installTranslator(translator)
        if config.app_config.get('theme_color'):
            setThemeColor(config.app_config['theme_color'])

        screens = self.screens()
        primary = self.primaryScreen()
        if primary in screens:
            screens.insert(0, screens.pop(screens.index(primary)))

        self.pet = DesktopPet(screens)
        self.settings = SettingsWindow()
        self.note = NotificationCenter()
        self.events = EventClient() if start_event_client else None
        self.chat_store = ChatStore(config.DATA_DIR / 'chat')
        self.chat_history = self.chat_store.load_today()
        self.quick_chat_worker = None
        self.quick_tts_worker = None
        self.event_tts_worker = None
        self.quick_thinking_bubble_id = None
        self.is_quitting = False

        self.pet.show_settings.connect(self.settings.show_window)
        self.pet.chat_prompt_submitted.connect(self._on_quick_chat_prompt)
        self.pet.chat_requested.connect(self._show_chat_window)
        self.pet.voice_chat_requested.connect(self._show_voice_chat_window)
        self.pet.realtime_requested.connect(self._show_realtime_window)
        self.pet.quit_requested.connect(self._on_quit_requested)
        self.settings.settings_changed.connect(self.pet.apply_settings)
        self.settings.pet_changed.connect(self.pet.load_pet)
        self.settings.clear_history_requested.connect(self._clear_chat_history)
        self.note.smart_action_clicked.connect(self._on_smart_action)
        if self.events:
            self.events.event_received.connect(self._on_event)
            self.events.start()
        QTimer.singleShot(0, self._show_startup_greeting)

    def _event_tts_path(self, event_name):
        voice_name = config.tts_config.get('voice_name') or config.DEFAULT_TTS_CONFIG['voice_name']
        safe_name = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in voice_name)
        return config.DATA_DIR / 'tts_events' / f'{safe_name}_{event_name}.pcm'

    def _play_event_tts(self, event_name):
        cfg = config.tts_config
        if not cfg.get('enabled') or not cfg.get('api_key'):
            return False
        path = self._event_tts_path(event_name)
        if not path.is_file():
            return False
        stop_tts()
        self.event_tts_worker = TtsPreviewWorker(path, parent=self)
        self.event_tts_worker.result_ready.connect(lambda success, text: self._on_event_tts_done(event_name, success, text))
        self.event_tts_worker.start()
        return True

    def _on_event_tts_done(self, event_name, success, text):
        if not success:
            print('Event TTS failed:', text)
        self.event_tts_worker = None
        if event_name == 'exit' and self.is_quitting:
            self.pet.quit_now()

    def _show_startup_greeting(self):
        x, y = self.pet.bubble_anchor()
        name = config.current_pet or '宠物'
        self.note.setup_bubble('好久不见~', x, y, 6000, title=name)
        self._play_event_tts('startup')

    def _show_chat_window(self):
        self.pet.show_chat(self.chat_history, self._append_chat_message, self.chat_store.content_for_llm)

    def _show_voice_chat_window(self):
        self.pet.show_voice_chat(self.chat_history, self._append_chat_message, self.chat_store.content_for_llm)

    def _show_realtime_window(self):
        self.pet.show_realtime(None)

    def _on_quit_requested(self):
        if self.is_quitting:
            return
        self.is_quitting = True
        if self.pet.quick_menu is not None:
            self.pet.quick_menu.close()
        x, y = self.pet.bubble_anchor()
        self.note.setup_bubble('我会想你的，再见~', x, y, 3000, title=config.current_pet or '宠物')
        if not self._play_event_tts('exit'):
            self.pet.quit_now()

    def _append_chat_message(self, role, content, source):
        message = self.chat_store.append(role, content, source=source, pet_name=config.current_pet or '宠物')
        self.chat_history.append(message)
        return message

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

    def _on_quick_chat_prompt(self, text):
        if self.quick_chat_worker is not None:
            x, y = self.pet.bubble_anchor()
            self.note.setup_bubble('我还在想上一句话，稍等一下。', x, y, 3000, title=config.current_pet or '宠物')
            return
        x, y = self.pet.bubble_anchor()
        self.note.setup_bubble(self._content_preview(text), x, y, 2000, title='你')
        self._append_chat_message('user', text, 'quick_chat')
        if self.pet.chat_window is not None and self.pet.chat_window.isVisible():
            self.pet.chat_window.reload_history()
        self.quick_thinking_bubble_id = self.note.setup_bubble('让我想想...', x, y, 60000, title=config.current_pet or '宠物')
        self.quick_chat_worker = ChatWorker(self._build_quick_chat_messages(), parent=self)
        self.quick_chat_worker.result_ready.connect(self._on_quick_chat_reply)
        self.quick_chat_worker.start()

    def _clear_chat_history(self):
        self.chat_store.clear_today()
        if self.pet.chat_window is not None:
            self.pet.chat_window.clear_history()
        else:
            self.chat_history.clear()

    def _build_quick_chat_messages(self):
        messages = []
        system_parts = [config.llm_config.get('system_prompt', ''), config.llm_config.get('memory_prompt', '')]
        system = '\n\n'.join(part.strip() for part in system_parts if part and part.strip())
        if system:
            messages.append({'role': 'system', 'content': system})
        for message in self.chat_history[-10:]:
            messages.append({'role': message.get('role'), 'content': self.chat_store.content_for_llm(message.get('content', ''))})
        return messages

    def _on_quick_chat_reply(self, success, text):
        self.quick_chat_worker = None
        if self.quick_thinking_bubble_id:
            self.note.close_bubble(self.quick_thinking_bubble_id)
            self.quick_thinking_bubble_id = None
        x, y = self.pet.bubble_anchor()
        if success:
            reply = text.strip() or '嗯。'
            self._append_chat_message('assistant', reply, 'quick_chat')
            if self.pet.chat_window is not None and self.pet.chat_window.isVisible():
                self.pet.chat_window.reload_history()
            self.note.setup_bubble(reply, x, y, max(5000, min(25000, len(reply) * 180)), title=config.current_pet or '宠物')
            self._speak_quick_reply(reply)
        else:
            self.note.setup_bubble('我现在说不出来：' + text, x, y, 6000, title=config.current_pet or '宠物')

    def _speak_quick_reply(self, text):
        cfg = config.tts_config
        if not cfg.get('enabled') or not cfg.get('api_key'):
            return
        stop_tts()
        self.quick_tts_worker = TtsWorker(text, cfg, parent=self)
        self.quick_tts_worker.result_ready.connect(self._on_quick_tts_done)
        self.quick_tts_worker.start()

    def _on_quick_tts_done(self, success, text):
        if not success:
            print('TTS failed:', text)
        self.quick_tts_worker = None

    def _on_event(self, event):
        event_type = event.get('type', 'message')
        x, y = self.pet.bubble_anchor()
        if event_type == 'message':
            self.note.setup_smart_bubble(event, x, y)
            self._trigger_pet_reaction(event)
        elif event_type == 'bubble':
            self.note.setup_bubble(event.get('message') or event.get('summary') or '', x, y, int(event.get('timeout', 6)) * 1000)
        elif event_type == 'action':
            self._trigger_pet_reaction(event)
        else:
            self.note.setup_notification(event.get('title', '外部事件'), event.get('summary', ''))

    def _trigger_pet_reaction(self, event):
        action = event.get('pet_action')
        if not action:
            priority = event.get('priority', 'normal')
            if priority in ('high', 'urgent'):
                action = 'fall'
            elif event.get('is_at_me'):
                action = 'default'
        if action:
            self.pet.play_action(action)

    def _on_smart_action(self, event, action):
        action_id = action.get('id') or action.get('type')
        text = action.get('text') or event.get('suggestion') or event.get('summary') or event.get('content') or ''
        x, y = self.pet.bubble_anchor()
        if action_id == 'ignore':
            return
        if action_id == 'copy':
            QGuiApplication.clipboard().setText(text)
            self.note.setup_bubble('已复制到剪贴板', x, y, 3000)
            return
        if action_id == 'open_chat':
            self._show_chat_window()
            return
        if action_id == 'later':
            self.note.setup_bubble('稍后提醒功能会在 miniPet 本地提醒模块中接入', x, y, 4000)
            return
        if self.events:
            self.events.execute_action(event, action)

    def shutdown(self):
        stop_tts()
        self.settings.shutdown()
        if self.pet.chat_window is not None:
            self.pet.chat_window.shutdown()
        if self.pet.voice_chat_window is not None:
            self.pet.voice_chat_window.shutdown()
        if self.pet.realtime_window is not None:
            self.pet.realtime_window.shutdown()
        for worker_name in ('quick_chat_worker', 'quick_tts_worker', 'event_tts_worker'):
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
