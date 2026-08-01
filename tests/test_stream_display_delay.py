# coding:utf-8

import time
import unittest

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from src import config
from src.stream_display_delay import StreamDisplayDelay


class StreamDisplayDelayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.old_tts = dict(config.tts_config)
        self.old_typewriter = dict(config.typewriter_config)

    def tearDown(self):
        config.tts_config.clear()
        config.tts_config.update(self.old_tts)
        config.typewriter_config.clear()
        config.typewriter_config.update(self.old_typewriter)

    def enable_delay(self, delay_ms=40):
        config.tts_config.update({'enabled': True, 'api_key': 'test'})
        config.typewriter_config['tts_delay_ms'] = delay_ms

    def wait(self, milliseconds):
        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def test_without_tts_runs_immediately(self):
        config.tts_config.update({'enabled': False, 'api_key': ''})
        calls = []

        StreamDisplayDelay().enqueue('reply', lambda: calls.append('shown'))

        self.assertEqual(['shown'], calls)

    def test_keeps_stream_interval_and_terminal_order(self):
        self.enable_delay()
        delay = StreamDisplayDelay()
        calls = []
        started = time.monotonic()
        delay.enqueue('reply', lambda: calls.append(('first', time.monotonic())))
        self.wait(20)
        delay.enqueue('reply', lambda: calls.append(('terminal', time.monotonic())))

        self.wait(100)

        self.assertEqual(['first', 'terminal'], [name for name, _at in calls])
        self.assertGreaterEqual(calls[0][1] - started, 0.03)
        self.assertLess(calls[1][1] - calls[0][1], 0.06)

    def test_reset_cancels_pending_lane(self):
        self.enable_delay()
        delay = StreamDisplayDelay()
        calls = []
        delay.enqueue('reply', lambda: calls.append('shown'))
        delay.reset('reply')

        self.wait(80)

        self.assertEqual([], calls)

    def test_lanes_do_not_block_each_other(self):
        self.enable_delay()
        delay = StreamDisplayDelay()
        calls = []
        delay.enqueue('one', lambda: calls.append('one'))
        self.wait(20)
        delay.enqueue('two', lambda: calls.append('two'))

        self.wait(100)

        self.assertEqual(['one', 'two'], calls)


if __name__ == '__main__':
    unittest.main()
