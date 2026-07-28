# coding:utf-8

import json
import unittest
from unittest.mock import Mock

from src.clients.claude_code_client import ClaudeCodeSession


class ClaudeCodeSessionTest(unittest.TestCase):
    def make_session(self, resume=False):
        session = ClaudeCodeSession('.', resume=resume)
        calls = {'process': [], 'session': [], 'mismatch': []}
        session.process_ready.connect(lambda: calls['process'].append(()))
        session.session_ready.connect(lambda value: calls['session'].append(value))
        session.session_mode_mismatch.connect(lambda value: calls['mismatch'].append(value))
        session._terminate_process = Mock()
        return session, calls

    def test_only_top_level_init_marks_session_ready(self):
        session, calls = self.make_session(resume=True)

        session._handle_json_line(json.dumps({'type': 'system', 'subtype': 'status'}))
        session._handle_json_line(json.dumps({'type': 'result', 'result': 'done'}))
        session._handle_json_line(json.dumps({
            'type': 'stream_event',
            'event': {'type': 'system', 'subtype': 'init'},
        }))

        self.assertEqual([], calls['process'])
        self.assertEqual([], calls['session'])

        session._handle_json_line(json.dumps({'type': 'system', 'subtype': 'init'}))
        session._handle_json_line(json.dumps({'type': 'system', 'subtype': 'init'}))

        self.assertEqual([()], calls['process'])
        self.assertEqual([session.session_id], calls['session'])

    def test_resume_not_found_falls_back_to_new_once(self):
        session, calls = self.make_session(resume=True)

        self.assertTrue(session._handle_mode_mismatch('No conversation found'))
        self.assertTrue(session._handle_mode_mismatch('Session not found'))

        self.assertEqual(['new'], calls['mismatch'])
        session._terminate_process.assert_called_once_with()

    def test_new_conflict_falls_back_to_resume_once(self):
        session, calls = self.make_session(resume=False)

        self.assertTrue(session._handle_mode_mismatch('Session ID already in use'))

        self.assertEqual(['resume'], calls['mismatch'])

    def test_timeout_falls_back_and_is_deduplicated(self):
        session, calls = self.make_session(resume=True)

        session._on_startup_timeout()
        session._on_startup_timeout()
        session._fail_startup('EOF')

        self.assertEqual(['new'], calls['mismatch'])
        self.assertIn('15', session._startup_error)

    def test_init_disables_mode_fallback(self):
        session, calls = self.make_session(resume=True)
        session._handle_json_line(json.dumps({'type': 'system', 'subtype': 'init'}))

        self.assertFalse(session._handle_mode_mismatch('Session not found'))
        self.assertFalse(session._fail_startup('EOF'))
        self.assertEqual([], calls['mismatch'])


if __name__ == '__main__':
    unittest.main()
