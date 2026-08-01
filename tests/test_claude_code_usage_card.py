# coding:utf-8

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from app import MiniPetApp
from widgets.notifications.reply_card import ReplyCard


class ClaudeCodeUsageCardTest(unittest.TestCase):
    def test_result_progress_passes_structured_usage_to_card(self):
        app = Mock()
        app._quick_stream_text = '你好呀，哥哥。'
        app._claude_code_result_usage = MiniPetApp._claude_code_result_usage.__get__(app)
        app._claude_code_metric_number = MiniPetApp._claude_code_metric_number
        app._show_reply_card = Mock()

        MiniPetApp._on_claude_code_progress(app, {
            'kind': 'result',
            'num_turns': 1,
            'duration_ms': 3326,
            'total_cost_usd': 0.034236,
            'usage': {
                'input_tokens': 4703,
                'output_tokens': 9,
                'cache_read_input_tokens': 20992,
                'cache_creation_input_tokens': 128,
            },
        })

        app._show_reply_card.assert_called_once_with(
            '你好呀，哥哥。',
            status='done',
            timeout_ms=60000,
            progress='',
            result_usage={
                'turns': 1,
                'duration_ms': 3326.0,
                'input_tokens': 4703,
                'output_tokens': 9,
                'cache_tokens': 21120,
                'cost_usd': 0.034236,
            },
        )

    def test_result_progress_ignores_invalid_metrics(self):
        app = Mock()
        app._quick_stream_text = ''
        app._claude_code_result_usage = MiniPetApp._claude_code_result_usage.__get__(app)
        app._claude_code_metric_number = MiniPetApp._claude_code_metric_number
        app._show_reply_card = Mock()

        MiniPetApp._on_claude_code_progress(app, {
            'kind': 'result',
            'duration_ms': 'NaN',
            'cost_usd': -1,
            'usage': {'input_tokens': 'invalid'},
        })

        app._show_reply_card.assert_not_called()

    def test_tool_progress_remains_plain_text(self):
        app = Mock()
        app._quick_stream_text = '处理中'
        app._show_reply_card = Mock()

        MiniPetApp._on_claude_code_progress(app, {'kind': 'tool', 'state': 'running', 'name': 'Read'})

        app._show_reply_card.assert_called_once_with(
            '处理中', status='streaming', timeout_ms=60000, progress='正在调用工具：Read'
        )

    def test_reply_card_keeps_usage_outside_body_elements(self):
        card = ReplyCard.__new__(ReplyCard)
        card.event_data = {
            'content': '完成',
            'progress': '工具执行完成',
            'result_usage': {'input_tokens': 4703, 'output_tokens': 9},
        }

        elements = ReplyCard._normalized_elements(card)

        self.assertEqual(['text', 'text'], [element['type'] for element in elements])
        self.assertNotEqual(ReplyCard._structure_signature(card), (
            repr(card.event_data.get('elements') or []),
            repr(card.event_data.get('progress') or ''),
            repr(card.event_data.get('controls') or []),
            repr(card.event_data.get('actions') or []),
        ))

    def test_reply_card_formats_usage_as_single_line_metrics(self):
        card = ReplyCard.__new__(ReplyCard)

        metrics = ReplyCard._usage_metrics(card, {
            'duration_ms': 3326,
            'cost_usd': 0.034236,
            'input_tokens': 4703,
            'output_tokens': 9,
            'cache_tokens': 21120,
        })

        self.assertEqual([
            ('输入', '4.7k'),
            ('输出', '9'),
            ('缓存', '21.1k'),
            ('费用', '$0.0342'),
        ], metrics)

    def test_reply_card_uses_placeholders_before_usage_arrives(self):
        card = ReplyCard.__new__(ReplyCard)

        self.assertEqual([
            ('输入', '--'),
            ('输出', '--'),
            ('缓存', '--'),
            ('费用', '--'),
        ], ReplyCard._usage_metrics(card, {}))

    def test_only_usage_dict_uses_usage_card_width(self):
        card = ReplyCard.__new__(ReplyCard)
        card._weighted_text_length = ReplyCard._weighted_text_length.__get__(card)
        card._event_text_for_width = ReplyCard._event_text_for_width.__get__(card)

        ordinary_event = {'content': '普通回复', 'result_usage': None}
        usage_event = {'content': 'Claude 回复', 'result_usage': {}}

        self.assertEqual(248, ReplyCard._card_width_for_event(card, ordinary_event))
        self.assertEqual(368, ReplyCard._card_width_for_event(card, usage_event))

    def test_non_claude_reply_clears_previous_usage(self):
        app = Mock()
        app.quick_chat_backend = 'builtin'
        app.pet.reply_card_anchor.return_value = (1, 2)
        app.note.update_reply_card.return_value = True
        app.quick_reply_card_id = 'existing-card'

        MiniPetApp._show_reply_card(app, '普通回复')

        app.note.update_reply_card.assert_called_once()
        event = app.note.update_reply_card.call_args.args[1]
        self.assertIsNone(event['result_usage'])


if __name__ == '__main__':
    unittest.main()
