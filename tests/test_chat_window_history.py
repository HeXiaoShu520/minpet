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
        app._session_backend.return_value = backend
        app._append_chat_message = Mock()
        app._build_quick_chat_messages.return_value = []
        app._send_external_command.return_value = sent
        app.stream_display_delay.enqueue.side_effect = lambda lane, callback: callback()
        app._chat_window_turn = None
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

    def test_selected_session_routes_to_its_backend(self):
        app = self.make_app('builtin')
        app._session_backend.return_value = 'claude_code'
        on_sent = Mock()

        result = MiniPetApp._send_chat_window_message(
            app, '你好', on_sent, Mock(), Mock(), 'claude-session'
        )

        self.assertTrue(result)
        app._send_external_command.assert_called_once_with(
            '你好', 'text', 'chat_window',
            turn_id=app._chat_window_turn['turn_id'],
            surface_id=app._chat_window_turn['surface_id'],
            backend='claude_code', session_id='claude-session',
        )
        app._append_chat_message.assert_called_once_with(
            'user', '你好', 'chat_window', 'claude_code', 'claude-session'
        )
        on_sent.assert_called_once_with('claude_code')

    def test_external_callback_only_shows_user_message(self):
        window = Mock()
        window.backend = 'builtin'
        window._push_message = Mock()

        ChatWindow._show_sent_user(window, '你好', 'claude_code')

        self.assertEqual('claude_code', window.backend)
        self.assertEqual('claude_code', window._stream_backend)
        window._push_message.assert_called_once_with('user', '你好')

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

    def test_clear_history_switches_to_new_session(self):
        window = Mock()
        window.session_id = 'old-session'
        window.clear_history_callback.return_value = 'new-session'
        window.select_session_callback = Mock()
        window._reset_stream_tts = Mock()
        window._select_session_id = Mock()

        ChatWindow.clear_history(window, show_hint=True)

        window.clear_history_callback.assert_called_once_with('old-session')
        window._select_session_id.assert_called_once_with('new-session')
        window._js.assert_not_called()
        window._push_message.assert_not_called()

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
