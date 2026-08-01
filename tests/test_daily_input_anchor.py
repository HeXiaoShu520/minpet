# coding:utf-8

import sys
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from clients.middle_btn_listener import MiddleButtonListener
from daily_input_controller import DailyInputController
from widgets.pet_voice_popup import VoiceOrbWidget


class DailyInputAnchorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def make_controller(self):
        app = Mock()
        app.pet_voice_active = False
        app.pet = Mock()
        controller = DailyInputController(app=app)
        return controller, app

    def test_initial_voice_orb_content_has_final_width_without_animation(self):
        orb = VoiceOrbWidget()

        orb.set_initial_content('typing', '语音输入中')

        self.assertEqual('typing', orb.state)
        self.assertEqual('语音输入中', orb.text)
        self.assertGreater(orb.width(), orb.min_orb_width)
        self.assertIsNone(orb.width_anim)

        orb.set_text('这是更长的识别文本')

        self.assertIsNotNone(orb.width_anim)

    def test_middle_listener_emits_toggle(self):
        listener = MiddleButtonListener()
        received = []
        listener.toggled.connect(lambda: received.append(True))

        listener.emit_toggled()

        self.assertEqual([True], received)

    @patch('daily_input_controller.QCursor.pos', return_value=QPoint(480, 240))
    @patch('daily_input_controller.QTimer.singleShot')
    @patch('daily_input_controller.AsrWorker')
    @patch('daily_input_controller.config.tts_config', {'api_key': 'test'})
    def test_recognition_updates_reuse_qt_cursor_anchor(self, asr_worker, single_shot, cursor_pos):
        controller, app = self.make_controller()
        worker = Mock()
        asr_worker.return_value = worker

        controller._on_middle_btn_toggled()
        controller._on_text_received('正在识别')
        controller._on_final_received('完成')

        calls = app.pet.update_voice_popup.call_args_list
        self.assertEqual(3, len(calls))
        for call in calls:
            self.assertEqual((480, 240), call.kwargs['anchor'])
            self.assertEqual('cursor', call.kwargs['anchor_mode'])
        cursor_pos.assert_called_once_with()

    @patch('daily_input_controller.config.tts_config', {'api_key': 'test'})
    def test_late_recognition_does_not_restore_typing_popup(self):
        controller, app = self.make_controller()
        controller._recording = False
        controller._popup_anchor = None

        controller._on_text_received('迟到文本')
        controller._on_final_received('迟到结果')

        app.pet.update_voice_popup.assert_not_called()

    @patch('daily_input_controller.QTimer.singleShot')
    def test_timeout_stops_and_injects_recognized_text(self, single_shot):
        controller, app = self.make_controller()
        worker = Mock()
        controller._recording = True
        controller._asr_worker = worker
        controller._accumulated_text = '已识别内容'
        controller._popup_anchor = (480, 240)

        controller._on_recording_timeout()

        worker.finish.assert_called_once_with()
        self.assertFalse(controller._recording)
        app.note.setup_reply_card_text.assert_called_once_with(
            '语音输入已达到 5 分钟，已自动结束，并已输入识别内容。',
            480, 240, 5000, title=ANY,
        )
        self.assertEqual(80, single_shot.call_args.args[0])

    def test_timeout_without_text_only_stops_recording(self):
        controller, app = self.make_controller()
        worker = Mock()
        controller._recording = True
        controller._asr_worker = worker
        controller._popup_anchor = (480, 240)

        controller._on_recording_timeout()

        worker.finish.assert_called_once_with()
        app.note.setup_reply_card_text.assert_called_once_with(
            '语音输入已达到 5 分钟，已自动结束；未识别到可输入的内容。',
            480, 240, 5000, title=ANY,
        )

    def test_stale_delayed_start_does_not_restart_worker(self):
        controller, _app = self.make_controller()
        worker = Mock()
        worker.isRunning.return_value = True
        controller._recording = False
        controller._asr_worker = worker

        controller._start_asr_if_current(worker)

        worker.start_recording.assert_not_called()


if __name__ == '__main__':
    unittest.main()
