# coding:utf-8
import json
import signal
import sys
from datetime import datetime, timedelta

from PySide6.QtCore import QLocale, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QInputDialog
from qfluentwidgets import FluentTranslator, setThemeColor

from miniPet import config
from miniPet.asr_client import AsrWorker
from miniPet.chat_store import ChatStore
from miniPet.desktop_pet import DesktopPet
from miniPet.event_client import EventClient
from miniPet.llm_client import ChatWorker
from miniPet.memory_store import MEMORY_CATEGORIES, MemoryStore
from miniPet.notification import NotificationCenter
from miniPet.protocol_v1 import AGENT_STATE, SESSION_PING, SESSION_PONG, SESSION_READY, SURFACE_KINDS, SURFACE_SHOW, USER_COMMAND, USER_DROP, USER_INPUT, V1_CAPABILITIES, normalize_inbound_event
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
        self.chat_store = ChatStore(config.DATA_DIR / 'chat')
        self.memory_store = MemoryStore(config.DATA_DIR / 'memory')
        self.settings = SettingsWindow(self.chat_store, self.memory_store)
        self.note = NotificationCenter()
        self.events = EventClient() if start_event_client else None
        if self.events:
            self.events.set_url(self._agent_ws_url())
        self.chat_history = []
        self.memory_worker = None
        self.user_turns_since_memory_check = 0
        self.quick_chat_worker = None
        self.quick_tts_worker = None
        self.event_tts_worker = None
        self.quick_chat_source = 'quick_chat'
        self.quick_thinking_bubble_id = None
        self.pet_voice_active = False
        self.pet_voice_asr_worker = None
        self.pet_voice_waiting_reply = False
        self.pet_voice_paused = False
        self.is_quitting = False

        self.pet.show_settings.connect(self.settings.show_window)
        self.pet.chat_prompt_submitted.connect(self._on_quick_chat_prompt)
        self.pet.drop_intent_submitted.connect(self._on_drop_intent)
        self.pet.chat_requested.connect(self._show_chat_window)
        self.pet.voice_chat_requested.connect(self._show_voice_chat_window)
        self.pet.voice_pause_requested.connect(self._pause_pet_voice_chat)
        self.pet.realtime_requested.connect(self._show_realtime_window)
        self.pet.quit_requested.connect(self._on_quit_requested)
        self.settings.settings_changed.connect(self.pet.apply_settings)
        self.settings.settings_changed.connect(self._apply_agent_settings)
        self.settings.pet_changed.connect(self.pet.load_pet)
        self.settings.clear_history_requested.connect(self._clear_chat_history)
        self.note.smart_action_clicked.connect(self._on_smart_action)
        if self.events:
            self.events.event_received.connect(self._on_event)
            self.events.connection_changed.connect(self._on_event_connection_changed)
            if self._agent_backend() != 'builtin':
                self.events.start()
        QTimer.singleShot(0, self._show_startup_greeting)

    def _agent_backend(self):
        return config.app_config.get('agent_backend', 'builtin') or 'builtin'

    def _agent_ws_url(self):
        backend = self._agent_backend()
        if backend == 'custom':
            return config.app_config.get('custom_agent_ws_url') or 'ws://127.0.0.1:18889/ws/minipet'
        return config.app_config.get('openclaw_ws_url') or 'ws://127.0.0.1:18888/ws/pet'

    def _apply_agent_settings(self):
        if not self.events:
            return
        self.events.set_url(self._agent_ws_url())
        if self._agent_backend() == 'builtin':
            self.events.stop()
            return
        if self.events.isRunning():
            self.events.reconnect()
        else:
            self.events.running = True
            self.events.start()

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
        self.note.setup_bubble('好久不见，想我了吗？', x, y, 6000, title=name)
        self._play_event_tts('startup')

    def _show_chat_window(self):
        self.pet.show_chat(self.chat_history, self._append_chat_message, self.chat_store.content_for_llm, self._build_system_prompt)

    def _show_voice_chat_window(self):
        self._toggle_pet_voice_chat()

    def _toggle_pet_voice_chat(self):
        if self.pet_voice_active:
            self._stop_pet_voice_chat()
            return
        popup = self.pet.show_voice_popup()
        popup.stop_requested.connect(self._stop_pet_voice_chat)
        if not config.tts_config.get('api_key'):
            self.pet.update_voice_popup('error', '缺少语音配置')
            x, y = self.pet.bubble_anchor()
            self.note.setup_bubble('请先在设置 > 语音中填写 TTS API Key', x, y, 4000, title=config.current_pet or '宠物')
            QTimer.singleShot(1800, self.pet.close_voice_popup)
            return
        self.pet_voice_active = True
        self.pet_voice_paused = False
        self._start_pet_voice_recording()

    def _start_pet_voice_recording(self):
        if not self.pet_voice_active or self.pet_voice_paused or self.quick_chat_worker is not None:
            return
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
        if self.pet_voice_asr_worker is not None:
            self.pet_voice_asr_worker.stop_recording()

    def _pause_pet_voice_chat(self):
        if not self.pet_voice_active:
            return
        if self.pet_voice_paused:
            self.pet_voice_paused = False
            self._start_pet_voice_recording()
            return
        self.pet_voice_paused = True
        self._stop_pet_voice_recording()
        stop_tts()
        self.pet.update_voice_popup('idle', '已暂停，单击继续')
        QTimer.singleShot(1600, self._shrink_paused_voice_popup)

    def _shrink_paused_voice_popup(self):
        if self.pet_voice_active and self.pet_voice_paused:
            self.pet.update_voice_popup('idle', '')

    def _stop_pet_voice_chat(self):
        self.pet_voice_active = False
        self.pet_voice_waiting_reply = False
        self.pet_voice_paused = False
        if self.pet_voice_asr_worker is not None:
            self.pet_voice_asr_worker.finish()
            self.pet_voice_asr_worker.wait(1200)
            self.pet_voice_asr_worker = None
        stop_tts()
        self.pet.close_voice_popup()

    def _on_pet_voice_status(self, text):
        if self.pet_voice_active and not self.pet_voice_paused and text in ('ASR已连接', '正在识别') and self.quick_chat_worker is None and self.quick_tts_worker is None:
            self.pet.update_voice_popup('listening', '')

    def _on_pet_voice_text(self, text):
        if self.pet_voice_active and not self.pet_voice_paused and text and self.quick_chat_worker is None and self.quick_tts_worker is None:
            self.pet.update_voice_popup('listening', text)

    def _on_pet_voice_final(self, text):
        text = (text or '').strip()
        if not text or not self.pet_voice_active:
            return
        self._stop_pet_voice_recording()
        self.pet_voice_waiting_reply = True
        self.pet.update_voice_popup('thinking', text)
        if not self._submit_quick_chat(text, 'voice_chat'):
            self.pet_voice_waiting_reply = False
            if self.pet_voice_active:
                QTimer.singleShot(800, self._start_pet_voice_recording)

    def _on_pet_voice_error(self, text):
        if self.pet_voice_active:
            self.pet.update_voice_popup('error', str(text)[:60])
            x, y = self.pet.bubble_anchor()
            self.note.setup_bubble('语音识别出错：' + str(text), x, y, 5000, title=config.current_pet or '宠物')
        self._stop_pet_voice_chat()

    def _on_pet_voice_finished(self):
        self.pet_voice_asr_worker = None

    def _show_realtime_window(self):
        self.pet.show_realtime(None)

    def _on_quit_requested(self):
        if self.is_quitting:
            return
        self.is_quitting = True
        if self.pet.quick_menu is not None:
            self.pet.quick_menu.close()
        if self.pet_voice_active or self.pet_voice_asr_worker is not None:
            self._stop_pet_voice_chat()
        x, y = self.pet.bubble_anchor()
        self.note.setup_bubble('我会想你的，再见~', x, y, 3000, title=config.current_pet or '宠物')
        if not self._play_event_tts('exit'):
            self.pet.quit_now()

    def _append_chat_message(self, role, content, source):
        message = {'role': role, 'content': content, 'source': source}
        self.chat_history.append(message)
        if role == 'user':
            self._maybe_schedule_memory_extraction()
        return message

    def _build_system_prompt(self):
        parts = [
            config.llm_config.get('system_prompt', ''),
            config.llm_config.get('memory_prompt', ''),
            self.memory_store.build_memory_prompt(),
        ]
        return '\n\n'.join(part.strip() for part in parts if part and part.strip())

    def _maybe_schedule_memory_extraction(self):
        if not config.llm_config.get('auto_memory_enabled', True):
            return
        self.user_turns_since_memory_check += 1
        every_n = max(1, int(config.llm_config.get('auto_memory_every_n_user_turns') or 3))
        if self.user_turns_since_memory_check < every_n or self.memory_worker is not None:
            return
        self.user_turns_since_memory_check = 0
        messages = self._build_memory_extraction_messages()
        if not messages:
            return
        self.memory_worker = ChatWorker(messages, parent=self)
        self.memory_worker.result_ready.connect(self._on_memory_extraction_result)
        self.memory_worker.start()

    def _build_memory_extraction_messages(self):
        recent_count = max(4, int(config.llm_config.get('auto_memory_recent_messages') or 12))
        stored = self.chat_history[-recent_count:]
        recent = []
        for message in stored:
            text = self.chat_store.content_text_for_memory(message.get('content', ''))
            if not text:
                continue
            recent.append({
                'id': message.get('id', ''),
                'created_at': message.get('created_at', ''),
                'role': message.get('role', ''),
                'source': message.get('source', ''),
                'text': text[:1200],
            })
        if not recent:
            return []
        existing = [
            {'id': m.get('id'), 'category': m.get('category'), 'text': m.get('text')}
            for m in self.memory_store.list_memories()
        ]
        max_items = max(1, int(config.llm_config.get('auto_memory_max_items_per_pass') or 3))
        payload = {
            'existing_memories': existing,
            'recent_messages': recent,
            'max_items': max_items,
            'allowed_categories': list(MEMORY_CATEGORIES),
            'required_output_schema': {
                'memories': [{
                    'action': 'add|update|noop',
                    'memory_id': '',
                    'category': 'user_preference|project_fact|relationship|task_context',
                    'text': '',
                    'importance': 1,
                    'confidence': 0.8,
                    'evidence': '',
                    'expires_days': 14,
                    'source_message_ids': [],
                }],
            },
        }
        system = (
            '你是一个严格保守的长期记忆抽取器。只从对未来多轮对话明显有帮助的信息中提炼记忆。\n'
            '允许的记忆类别只有：user_preference、project_fact、relationship、task_context。\n'
            '严格要求：1. 若没有高价值信息，返回空数组。2. 不记录一次性寒暄、临时情绪、短期安排、显而易见的本轮内容。\n'
            '3. 不重复已有记忆。4. 若只是对已有记忆的小改写，不要新增重复项；只有明确更正时才 update。\n'
            '5. 输出必须是合法 JSON，不能包含 Markdown 或解释。6. 每条 text 必须是简洁、稳定、可直接展示的一句话中文。\n'
            '7. importance 为 1-5，confidence 为 0-1。task_context 必须给 expires_days，默认 14；长期类别 expires_days 用 0。'
        )
        return [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
        ]

    def _on_memory_extraction_result(self, success, text):
        self.memory_worker = None
        if not success:
            print('Memory extraction failed:', text)
            return
        try:
            data = json.loads((text or '').strip())
        except Exception as e:
            print('Memory extraction invalid JSON:', e, text)
            return
        changed = False
        max_items = max(1, int(config.llm_config.get('auto_memory_max_items_per_pass') or 3))
        for item in (data.get('memories') or [])[:max_items]:
            action = item.get('action')
            category = item.get('category')
            memory_text = (item.get('text') or '').strip()
            if action not in ('add', 'update') or category not in MEMORY_CATEGORIES or not memory_text or len(memory_text) > 180:
                continue
            expires_at = ''
            try:
                expires_days = int(item.get('expires_days') or 0)
            except (TypeError, ValueError):
                expires_days = 14 if category == 'task_context' else 0
            if category == 'task_context' and expires_days > 0:
                expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat(timespec='seconds')
            memory = self.memory_store.upsert_memory(
                category,
                memory_text,
                source_message_ids=item.get('source_message_ids') or [],
                source_date=self.chat_store.today(),
                memory_id=item.get('memory_id') if action == 'update' else '',
                importance=item.get('importance', 3),
                confidence=item.get('confidence', 0.8),
                evidence=item.get('evidence', ''),
                expires_at=expires_at,
            )
            changed = changed or memory is not None
        if changed and hasattr(self.settings, 'reload_memories'):
            self.settings.reload_memories()

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
        if self._agent_backend() == 'builtin':
            self._submit_quick_chat(text, 'quick_chat')
            return
        x, y = self.pet.bubble_anchor()
        self.note.setup_bubble(self._content_preview(text), x, y, 2000, title='你')
        sent = self.events.send_event(USER_COMMAND, {
            'text': self._content_preview(text),
            'content': text,
            'mode': 'text',
            'backend': self._agent_backend(),
            'surface': 'pet_popup',
            'context': {'surface': 'pet_popup'},
        }) if self.events else False
        if sent:
            self.note.setup_bubble('收到，我交给外置智能体处理。', x, y, 3000, title=config.current_pet or '宠物')
        else:
            self.note.setup_bubble('外置智能体还没连接，先检查“智能体”设置。', x, y, 4500, title=config.current_pet or '宠物')

    def _on_drop_intent(self, drop_payload, intent):
        payload = dict(drop_payload)
        payload['intent'] = intent
        payload['surface'] = 'desktop_pet'
        payload['context'] = {'surface': 'desktop_pet'}
        x, y = self.pet.bubble_anchor()
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
        sent = self.events.send_event('user.drop', payload) if self.events else False
        if sent:
            self.note.setup_bubble('收到，我交给外置智能体处理：' + intent_labels.get(intent, intent), x, y, 3500, title=config.current_pet or '宠物')
        else:
            self.note.setup_bubble('外置智能体还没连接，先检查“智能体”设置。', x, y, 4500, title=config.current_pet or '宠物')

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

    def _submit_quick_chat(self, text, source='quick_chat'):
        if self.quick_chat_worker is not None:
            if source == 'quick_chat' and self.pet.input_popup is not None:
                self.pet.input_popup.finish_thinking()
                self.pet.input_popup = None
            x, y = self.pet.bubble_anchor()
            self.note.setup_bubble('我还在想上一句话，稍等一下。', x, y, 3000, title=config.current_pet or '宠物')
            return False
        self.quick_chat_source = source
        self._append_chat_message('user', text, source)
        if self.pet.chat_window is not None and self.pet.chat_window.isVisible():
            self.pet.chat_window.reload_history()
        self.quick_chat_worker = ChatWorker(self._build_quick_chat_messages(), parent=self)
        self.quick_chat_worker.result_ready.connect(self._on_quick_chat_reply)
        self.quick_chat_worker.start()
        return True

    def _show_quick_thinking_bubble(self, source):
        if self.quick_chat_worker is None or self.quick_chat_source != source or self.quick_thinking_bubble_id:
            return
        x, y = self.pet.bubble_anchor()
        self.quick_thinking_bubble_id = self.note.setup_bubble('让我想想...', x, y, 60000, title=config.current_pet or '宠物')

    def _clear_chat_history(self):
        if self.pet.chat_window is not None:
            self.pet.chat_window.clear_history()
        else:
            self.chat_history.clear()

    def _build_quick_chat_messages(self):
        messages = []
        system = self._build_system_prompt()
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
        if self.quick_chat_source == 'quick_chat' and self.pet.input_popup is not None:
            self.pet.input_popup.finish_thinking()
            self.pet.input_popup = None
        x, y = self.pet.bubble_anchor()
        if success:
            reply = text.strip() or '嗯。'
            self._append_chat_message('assistant', reply, self.quick_chat_source or 'quick_chat')
            if self.pet.chat_window is not None and self.pet.chat_window.isVisible():
                self.pet.chat_window.reload_history()
            self.note.setup_bubble(reply, x, y, max(5000, min(25000, len(reply) * 180)), title=config.current_pet or '宠物')
            if self.quick_chat_source == 'voice_chat' and self.pet_voice_active:
                self.pet.update_voice_popup('speaking', '')
            self._speak_quick_reply(reply)
        else:
            self.note.setup_bubble('我现在说不出来：' + text, x, y, 6000, title=config.current_pet or '宠物')
            if self.quick_chat_source == 'voice_chat' and self.pet_voice_active:
                self.pet_voice_waiting_reply = False
                if not self.pet_voice_paused:
                    self.pet.update_voice_popup('listening', '')
                    QTimer.singleShot(800, self._start_pet_voice_recording)

    def _speak_quick_reply(self, text):
        cfg = config.tts_config
        if not cfg.get('enabled') or not cfg.get('api_key'):
            self._on_quick_tts_done(True, '')
            return
        stop_tts()
        self.quick_tts_worker = TtsWorker(text, cfg, parent=self)
        self.quick_tts_worker.result_ready.connect(self._on_quick_tts_done)
        self.quick_tts_worker.start()

    def _on_quick_tts_done(self, success, text):
        if not success:
            print('TTS failed:', text)
        self.quick_tts_worker = None
        if self.quick_chat_source == 'voice_chat' and self.pet_voice_active:
            self.pet_voice_waiting_reply = False
            if not self.pet_voice_paused:
                self.pet.update_voice_popup('listening', '')
                QTimer.singleShot(500, self._start_pet_voice_recording)

    def _on_event_connection_changed(self, connected):
        if connected:
            x, y = self.pet.bubble_anchor()
            name = '通用 AI 后端' if self._agent_backend() == 'custom' else 'OpenClaw AI'
            self.note.setup_bubble('已连接 ' + name + '。', x, y, 3000, title=config.current_pet or '宠物')

    def _on_event(self, event):
        event = normalize_inbound_event(event)
        event_type = event.get('type', '')
        payload = event.get('payload') if isinstance(event.get('payload'), dict) else event
        x, y = self.pet.bubble_anchor()
        if event_type == SESSION_READY:
            server = payload.get('server') if isinstance(payload.get('server'), dict) else {}
            self.note.setup_bubble('后端已就绪：' + str(server.get('name') or payload.get('name') or '智能体'), x, y, 3000, title=config.current_pet or '宠物')
        elif event_type == SURFACE_SHOW:
            self._handle_surface_show(payload)
        elif event_type == AGENT_STATE:
            self._handle_agent_status(event_type, payload)
        elif event_type == SESSION_PING:
            if self.events:
                self.events.send_event(SESSION_PONG, {'ts': payload.get('ts')})
        else:
            self.note.setup_notification(payload.get('title', '外部事件'), payload.get('summary') or payload.get('content') or '')

    def _handle_surface_show(self, payload):
        kind = payload.get('kind') or ''
        x, y = self.pet.bubble_anchor()
        if kind in ('input', 'choice'):
            self._handle_input_request(payload)
            return
        if kind == 'bubble' and not payload.get('actions'):
            timeout = payload.get('timeout_ms') or (payload.get('lifetime') or {}).get('ttl_ms') or int(payload.get('timeout', 6)) * 1000
            self.note.setup_bubble(payload.get('text') or payload.get('message') or payload.get('summary') or payload.get('content') or '', x, y, int(timeout), title=payload.get('title') or config.current_pet or '宠物')
            return
        card_event = self._normalize_display_event(SURFACE_SHOW, payload)
        self.note.setup_smart_bubble(card_event, x, y)
        self._trigger_pet_reaction(card_event)

    def _handle_input_request(self, payload):
        title = payload.get('title') or '需要你的输入'
        metadata = payload.get('metadata') or {}
        input_spec = payload.get('input') if isinstance(payload.get('input'), dict) else {}
        kind = payload.get('kind') or input_spec.get('type')
        surface_id = payload.get('surface_id')
        if kind in ('input', 'text'):
            default = payload.get('default_text') or input_spec.get('default_value') or ''
            prompt = payload.get('description') or input_spec.get('placeholder') or payload.get('placeholder') or '请输入'
            text, ok = QInputDialog.getText(None, title, prompt, text=default)
            if self.events:
                self.events.send_event(USER_INPUT, {
                    'surface_id': surface_id,
                    'action_id': 'submit' if ok else 'cancel',
                    'kind': 'text',
                    'value': text if ok else '',
                    'metadata': metadata,
                })
            return
        if kind == 'choice':
            options = payload.get('options') or input_spec.get('options') or []
            labels = [str(opt.get('label') or opt.get('id')) for opt in options if isinstance(opt, dict)]
            if not labels:
                return
            label, ok = QInputDialog.getItem(None, title, payload.get('description') or payload.get('content') or '请选择', labels, 0, False)
            selected = []
            if ok:
                for opt in options:
                    if str(opt.get('label') or opt.get('id')) == label:
                        selected = [opt.get('id')]
                        break
            if self.events:
                self.events.send_event(USER_INPUT, {
                    'surface_id': surface_id,
                    'action_id': 'submit' if ok else 'cancel',
                    'kind': 'choice',
                    'value': selected,
                    'metadata': metadata,
                })
            return
        actions = [
            {'id': 'confirm', 'label': payload.get('confirm_label') or '确认', 'style': 'primary'},
            {'id': 'cancel', 'label': payload.get('cancel_label') or '取消', 'style': 'quiet'},
        ]
        event = dict(payload)
        event['actions'] = actions
        event['summary'] = payload.get('content') or payload.get('description') or ''
        x, y = self.pet.bubble_anchor()
        self.note.setup_smart_bubble(event, x, y)

    def _handle_pet_control(self, event_type, payload):
        if event_type in ('pet.emotion.set', 'pet.nudge'):
            emotion = payload.get('emotion') or payload.get('intensity') or payload.get('reason') or ''
            text = payload.get('text') or payload.get('message') or ''
            action = payload.get('action') or payload.get('fallback_action')
            if not action:
                if emotion in ('happy', 'celebrate'):
                    action = 'happy'
                elif emotion in ('urgent', 'error'):
                    action = 'fall'
                elif emotion in ('thinking', 'working', 'waiting'):
                    action = 'default'
            if action:
                self.pet.play_action(action)
            if text:
                x, y = self.pet.bubble_anchor()
                self.note.setup_bubble(text, x, y, int(payload.get('timeout_ms') or 4000), title=config.current_pet or '宠物')
            return
        self._trigger_pet_reaction(payload)

    def _handle_agent_status(self, event_type, payload):
        x, y = self.pet.bubble_anchor()
        if event_type == 'agent.step.update':
            steps = payload.get('steps') or []
            lines = []
            for step in steps[:6]:
                status = step.get('status') if isinstance(step, dict) else ''
                mark = '✓' if status == 'done' else '●' if status == 'running' else '○'
                lines.append('%s %s' % (mark, step.get('title') or step.get('id') if isinstance(step, dict) else step))
            text = '\n'.join(lines) or '正在处理...'
            self.note.setup_bubble(text, x, y, 8000, title=payload.get('title') or '任务步骤')
            return
        if event_type == 'agent.task.done':
            self.pet.play_action('happy')
            self.note.setup_bubble(payload.get('summary') or payload.get('title') or '任务完成', x, y, 6000, title='完成')
            return
        if event_type == 'agent.task.failed':
            self.note.setup_bubble(payload.get('error') or '任务失败', x, y, 6000, title='失败')
            return
        title = payload.get('title') or payload.get('state') or (payload.get('task') or {}).get('title') or '智能体状态'
        text = payload.get('text') or payload.get('status') or payload.get('state') or '正在处理...'
        emotion = payload.get('emotion') or payload.get('state')
        if emotion in ('happy', 'celebrate', 'done'):
            self.pet.play_action('happy')
        elif emotion in ('urgent', 'error', 'failed'):
            self.pet.play_action('fall')
        self.note.setup_bubble(text, x, y, 5000, title=title)

    def _send_context_status(self, request_id=None):
        if not self.events:
            return
        pos = self.pet.pos()
        self.events.send_event('session.context', {
            'pet': config.current_pet,
            'visible': self.pet.isVisible(),
            'agent_backend': self._agent_backend(),
            'position': {'x': pos.x(), 'y': pos.y(), 'width': self.pet.width(), 'height': self.pet.height()},
            'protocol': 'minipet.v1',
            'surface_kinds': list(SURFACE_KINDS),
            'capabilities': list(V1_CAPABILITIES),
        }, request_id=request_id)

    def _handle_memory_hint(self, event_type, payload):
        text = payload.get('text') or payload.get('alias') or ''
        x, y = self.pet.bubble_anchor()
        if text:
            self.note.setup_bubble('已收到记忆提示：' + str(text)[:50], x, y, 3500, title='记忆')

    def _normalize_display_event(self, event_type, payload):
        event = dict(payload)
        event['type'] = event_type
        if event_type == 'display.message.show':
            self._normalize_display_message(event)
        elif event_type == 'interaction.present':
            event['summary'] = event.get('assistant_message') or event.get('content') or event.get('subtitle') or ''
        else:
            event.setdefault('summary', event.get('content') or event.get('description') or '')
        if event.get('preview') and isinstance(event.get('preview'), dict) and not event.get('assistant_message'):
            event['assistant_message'] = event['preview'].get('content') or ''
        if 'priority' not in event:
            event['priority'] = 'normal'
        return event

    def _normalize_display_message(self, event):
        chat = event.get('chat') if isinstance(event.get('chat'), dict) else {}
        sender = event.get('sender') if isinstance(event.get('sender'), dict) else {}
        message = event.get('message') if isinstance(event.get('message'), dict) else {}
        content = message.get('content') if isinstance(message.get('content'), dict) else {}
        event['title'] = event.get('title') or chat.get('name') or '外部消息'
        event['subtitle'] = event.get('subtitle') or sender.get('name') or chat.get('type') or event.get('source') or ''
        text = content.get('plain_text') or content.get('text') or message.get('text') or event.get('summary') or ''
        event['summary'] = text
        event['kind'] = 'external_message'
        metadata = dict(event.get('metadata') or {})
        for key in ('chat_id', 'message_id', 'thread_id', 'root_id', 'parent_id'):
            if event.get(key) and key not in metadata:
                metadata[key] = event.get(key)
            if message.get(key) and key not in metadata:
                metadata[key] = message.get(key)
            if chat.get('id') and key == 'chat_id' and key not in metadata:
                metadata[key] = chat.get('id')
        event['metadata'] = metadata

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
        self.pet.close_voice_popup()
        if self.pet_voice_asr_worker is not None:
            self.pet_voice_asr_worker.finish()
            self.pet_voice_asr_worker.wait(1500)
            self.pet_voice_asr_worker = None
        for worker_name in ('quick_chat_worker', 'quick_tts_worker', 'event_tts_worker', 'memory_worker'):
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
