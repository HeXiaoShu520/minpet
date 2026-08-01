# coding:utf-8

import tempfile
import unittest
from pathlib import Path

from storage.chat_store import GLOBAL_SESSION_IDS, ChatStore


class ChatStoreSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ChatStore(Path(self.tmp.name) / 'chat')

    def tearDown(self):
        self.tmp.cleanup()

    def test_backends_have_stable_global_session_ids(self):
        self.assertEqual('builtin:global', self.store.global_session_id('builtin'))
        self.assertEqual('claude_code:global', self.store.global_session_id('claude_code'))
        self.assertEqual('openclaw:global', self.store.global_session_id('openclaw'))
        self.assertEqual('custom:global', self.store.global_session_id('custom'))
        self.assertEqual(set(GLOBAL_SESSION_IDS.values()), {
            self.store.global_session_id(backend)
            for backend in GLOBAL_SESSION_IDS
        })

    def test_backend_history_is_isolated(self):
        self.store.append('user', '内置消息', backend='builtin')
        self.store.append('user', 'Claude 消息', backend='claude_code')

        self.assertEqual(['内置消息'], [
            message['content']
            for message in self.store.load_backend_history('builtin')
        ])
        self.assertEqual(['Claude 消息'], [
            message['content']
            for message in self.store.load_backend_history('claude_code')
        ])

    def test_clear_backend_history_keeps_other_backends(self):
        self.store.append('user', '保留', backend='openclaw')
        self.store.append('user', '清除', backend='builtin')

        self.store.clear_backend_history('builtin')

        self.assertEqual([], self.store.load_backend_history('builtin'))
        self.assertEqual(['保留'], [
            message['content']
            for message in self.store.load_backend_history('openclaw')
        ])

    def test_clear_all_removes_chat_data(self):
        self.store.append('user', '消息', backend='custom')

        self.store.clear_all()

        self.assertEqual([], self.store.load_backend_history('custom'))
        self.assertFalse(self.store.index_file.exists())
        self.assertFalse(self.store.search_db.exists())


if __name__ == '__main__':
    unittest.main()
