# coding:utf-8

import tempfile
import unittest
from pathlib import Path

from storage.chat_store import ChatStore


class ChatStoreSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ChatStore(Path(self.tmp.name) / 'chat')

    def tearDown(self):
        self.tmp.cleanup()

    def test_sessions_are_isolated_within_same_backend(self):
        first = self.store.create_session('builtin')
        second = self.store.create_session('builtin')
        self.store.append('user', '第一段对话', backend='builtin', session_id=first)
        self.store.append('assistant', '第一段回复', backend='builtin', session_id=first)
        self.store.append('user', '第二段对话', backend='builtin', session_id=second)

        self.assertEqual(['第一段对话', '第一段回复'], [m['content'] for m in self.store.load_session(first)])
        self.assertEqual(['第二段对话'], [m['content'] for m in self.store.load_session(second)])
        self.assertEqual({first, second}, {item['session_id'] for item in self.store.list_sessions('builtin')})

    def test_delete_session_keeps_other_sessions(self):
        first = self.store.create_session('builtin')
        second = self.store.create_session('builtin')
        self.store.append('user', '保留', backend='builtin', session_id=first)
        self.store.append('user', '删除', backend='builtin', session_id=second)

        self.assertTrue(self.store.delete_session(second))
        self.assertEqual(['保留'], [m['content'] for m in self.store.load_session(first)])
        self.assertEqual([], self.store.load_session(second))

    def test_mixed_backend_sessions_keep_metadata(self):
        builtin = self.store.create_session('builtin')
        claude = self.store.create_session('claude_code')
        self.store.append('user', '内置对话', backend='builtin', session_id=builtin)
        self.store.append('user', 'Claude 对话', backend='claude_code', session_id=claude)

        sessions = {item['session_id']: item for item in self.store.list_sessions()}
        self.assertEqual('builtin', sessions[builtin]['backend'])
        self.assertEqual('claude_code', sessions[claude]['backend'])
        self.assertEqual(claude, self.store.get_session(claude)['session_id'])
        self.assertIsNone(self.store.get_session('missing'))

    def test_old_records_map_to_date_and_backend_session(self):
        path = self.store.sessions_dir / '2026-08-01.jsonl'
        path.write_text('{"role":"user","backend":"builtin","content":[{"type":"text","text":"旧记录"}]}\n', encoding='utf-8')

        sessions = self.store.list_sessions('builtin')
        self.assertEqual('legacy:2026-08-01:builtin', sessions[0]['session_id'])
        self.assertEqual(['旧记录'], [m['content'] for m in self.store.load_session(sessions[0]['session_id'])])


if __name__ == '__main__':
    unittest.main()
