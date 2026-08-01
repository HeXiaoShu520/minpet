# coding:utf-8

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from app import MiniPetApp
from clients.claude_code_client import ClaudeCodeSession
from clients.openclaw_client import call_openclaw
from windows.chat_window import ChatWindow


class _Signal:
    def connect(self, callback):
        self.callback = callback


class _Worker:
    def __init__(self):
        self.delta_ready = _Signal()
        self.result_ready = _Signal()
        self.finished = _Signal()
        self.start = Mock()
        self.deleteLater = Mock()


class ChatWindowHistoryTest(unittest.TestCase):
    def make_app(self, backend, sent=True):
        app = Mock()
        app._agent_backend.return_value = backend
        app._backend_session_id.return_value = backend + ':global'
        app._append_chat_message = Mock()
        app._build_quick_chat_messages.return_value = []
        app._send_external_command.return_value = sent
        app.stream_display_delay.enqueue.side_effect = lambda lane, callback: callback()
        app._active_turns = {}
        app._turn_by_surface_id = {}
        for name in ('_begin_turn', '_resolve_turn', '_turn_lane', '_publish_turn_delta', '_refresh_chat_window_for_turn', '_finish_turn'):
            setattr(app, name, getattr(MiniPetApp, name).__get__(app))
        return app

    def test_claude_code_saves_user_before_showing_it(self):
        app = self.make_app('claude_code')
        calls = []
        app._append_chat_message.side_effect = lambda *args: calls.append(('save', args))
        on_sent = Mock(side_effect=lambda *args: calls.append(('show', args)))

        result = MiniPetApp._send_chat_window_message(app, '你好', on_sent, Mock(), Mock())

        self.assertTrue(result)
        self.assertEqual('save', calls[0][0])
        self.assertEqual(('user', '你好', 'chat_window', 'claude_code'), calls[0][1][:4])
        self.assertEqual(('show', ('claude_code',)), calls[1])

    def test_external_send_failure_does_not_save_or_show_user(self):
        app = self.make_app('claude_code', sent=False)
        on_sent = Mock()

        result = MiniPetApp._send_chat_window_message(app, '你好', on_sent, Mock(), Mock())

        self.assertFalse(result)
        app._append_chat_message.assert_not_called()
        on_sent.assert_not_called()

    @patch('app.ChatWorker')
    def test_builtin_saves_user_before_creating_worker(self, chat_worker):
        app = self.make_app('builtin')
        worker = _Worker()
        chat_worker.return_value = worker
        on_sent = Mock()

        result = MiniPetApp._send_chat_window_message(app, '你好', on_sent, Mock(), Mock())

        self.assertIs(result, worker)
        app._append_chat_message.assert_called_once()
        self.assertEqual(
            ('user', '你好', 'chat_window', 'builtin'),
            app._append_chat_message.call_args.args[:4],
        )
        on_sent.assert_called_once_with('builtin')
        chat_worker.assert_called_once_with([], parent=app)
        worker.start.assert_called_once_with()

    def test_current_backend_uses_its_global_session(self):
        app = self.make_app('claude_code')
        on_sent = Mock()

        result = MiniPetApp._send_chat_window_message(
            app, '你好', on_sent, Mock(), Mock()
        )

        self.assertTrue(result)
        args = app._send_external_command.call_args
        self.assertEqual(('你好', 'text', 'chat_window'), args.args[:3])
        self.assertEqual('claude_code', args.kwargs['backend'])
        self.assertEqual('claude_code:global', args.kwargs['session_id'])
        self.assertTrue(args.kwargs['turn_id'])
        self.assertEqual('turn-' + args.kwargs['turn_id'], args.kwargs['surface_id'])
        on_sent.assert_called_once_with('claude_code')

    def test_backend_selector_reloads_global_history_once(self):
        window = Mock()
        window.backend = 'builtin'
        window.backend_select_callback.return_value = [{'content': 'Claude 历史'}]
        window.set_backend = Mock()
        window._clear_quote = Mock()
        window.reload_history = Mock()

        ChatWindow._select_backend(window, 'claude_code')

        window.backend_select_callback.assert_called_once_with('claude_code')
        self.assertEqual([{'content': 'Claude 历史'}], window.history)
        window.set_backend.assert_called_once_with('claude_code')
        window._clear_quote.assert_called_once_with()
        window.reload_history.assert_called_once_with()

    @patch.dict('app.config.app_config', {'agent_backend': 'builtin'}, clear=False)
    @patch('app.config.save_app_config')
    def test_backend_selection_does_not_reopen_chat_window(self, save_config):
        app = Mock()
        app._agent_backend.return_value = 'builtin'
        app._history_for_backend.return_value = [{'content': 'Claude 历史'}]
        app._apply_agent_settings = Mock()
        app._show_chat_window = Mock()

        history = MiniPetApp._select_chat_backend(app, 'claude_code')

        self.assertEqual([{'content': 'Claude 历史'}], history)
        save_config.assert_called_once_with()
        app._apply_agent_settings.assert_called_once_with(refresh_chat_window=False)
        app._show_chat_window.assert_not_called()

    def test_apply_agent_settings_refreshes_only_visible_chat_window(self):
        app = Mock()
        app._agent_backend.return_value = 'builtin'
        app._history_for_backend.return_value = []
        app.pet.chat_window.isVisible.return_value = True
        app.claude_code_reset_token = 0
        app.events = None
        app._show_chat_window = Mock()
        app._stop_claude_code_session = Mock()

        MiniPetApp._apply_agent_settings(app)

        app._show_chat_window.assert_called_once_with()

        app.pet.chat_window.isVisible.return_value = False
        app._show_chat_window.reset_mock()
        MiniPetApp._apply_agent_settings(app)
        app._show_chat_window.assert_not_called()

    def test_external_callback_only_shows_user_message(self):
        window = Mock()
        window.backend = 'builtin'
        window._push_message = Mock()

        ChatWindow._show_sent_user(window, '你好', 'claude_code')

        self.assertEqual('claude_code', window.backend)
        self.assertEqual('claude_code', window._stream_backend)
        window._push_message.assert_called_once_with('user', '你好')

    def test_chat_window_claude_output_does_not_show_reply_card(self):
        app = self.make_app('claude_code')
        app._show_reply_card = Mock()
        app._quick_reply_usage = None
        on_delta = Mock()
        turn = MiniPetApp._begin_turn(app, 'claude_code', 'chat_window', on_delta=on_delta)

        MiniPetApp._show_claude_code_streaming(app, turn, '流式回答')

        on_delta.assert_called_once_with('流式回答')
        app._show_reply_card.assert_not_called()

    def test_chat_window_claude_result_does_not_use_quick_tts(self):
        app = self.make_app('claude_code')
        on_result = Mock()
        app._show_reply_card = Mock()
        app.quick_stream_tts.queue_text = Mock()
        turn = MiniPetApp._begin_turn(app, 'claude_code', 'chat_window', on_result=on_result)

        MiniPetApp._show_claude_code_result(app, turn, '最终回答')

        on_result.assert_called_once_with(True, '最终回答')
        app._show_reply_card.assert_not_called()
        app.quick_stream_tts.queue_text.assert_not_called()

    def test_chat_window_turn_delta_never_updates_reply_card(self):
        app = self.make_app('claude_code')
        app._active_turns = {}
        app._turn_by_surface_id = {}
        app._show_reply_card = Mock()
        on_delta = Mock()
        turn = MiniPetApp._begin_turn(
            app, 'claude_code', 'chat_window', 'claude_code:global',
            on_delta=on_delta,
        )

        MiniPetApp._publish_turn_delta(app, turn, '流式回答')

        on_delta.assert_called_once_with('流式回答')
        app._show_reply_card.assert_not_called()

    def test_external_turn_refreshes_matching_open_chat_window_on_final(self):
        app = self.make_app('claude_code')
        app._active_turns = {}
        app._turn_by_surface_id = {}
        app.pet.chat_window.isVisible.return_value = True
        app.pet.chat_window.backend = 'claude_code'
        turn = MiniPetApp._begin_turn(
            app, 'claude_code', 'external', 'claude_code:global', 'quick_chat',
        )

        MiniPetApp._finish_turn(app, turn, True, '最终回答')

        app._append_chat_message.assert_called_once_with(
            'assistant', '最终回答', 'quick_chat', 'claude_code',
        )
        app.pet.chat_window.reload_history.assert_called_once_with()

    def test_claude_cli_session_id_depends_on_chat_session(self):
        first = ClaudeCodeSession._session_id_for_project('E:/project', 0, 'first')
        second = ClaudeCodeSession._session_id_for_project('E:/project', 0, 'second')

        self.assertNotEqual(first, second)

    @patch('clients.openclaw_client.request.urlopen')
    @patch('clients.openclaw_client.load_openclaw_token', return_value='token')
    def test_openclaw_uses_session_scoped_user(self, _token, urlopen):
        response = Mock()
        response.read.return_value = b'{"output":[{"type":"message","content":[{"type":"output_text","text":"ok"}]}]}'
        urlopen.return_value.__enter__.return_value = response

        success, text = call_openclaw('你好', {'openclaw_user': 'mini'}, session_id='session-a')

        self.assertTrue(success)
        self.assertEqual('ok', text)
        payload = urlopen.call_args.args[0].data.decode('utf-8')
        self.assertIn('"user": "mini:chat:session-a"', payload)

    def test_clear_history_resets_current_backend(self):
        window = Mock()
        window.clear_history_callback = Mock()
        window._reset_stream_tts = Mock()

        ChatWindow.clear_history(window, show_hint=True)

        window.clear_history_callback.assert_called_once_with()
        self.assertEqual([], window.history)
        window._js.assert_called_once_with('Chat.clear()')
        window._push_message.assert_called_once_with('assistant', '对话已清空，重新开始吧。')

    def test_clear_history_without_callback_keeps_local_behavior(self):
        window = Mock()
        window.clear_history_callback = None
        window.history = Mock()
        window._reset_stream_tts = Mock()

        ChatWindow.clear_history(window, show_hint=True)

        window.history.clear.assert_called_once_with()
        window._js.assert_called_once_with('Chat.clear()')
        window._push_message.assert_called_once_with('assistant', '对话已清空，重新开始吧。')


if __name__ == '__main__':
    unittest.main()
