# coding:utf-8

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from app import MiniPetApp


class PetVoiceRecordingTimeoutTest(unittest.TestCase):
    def make_app(self):
        app = Mock()
        app.pet_voice_active = True
        app.pet_voice_paused = False
        app.pet_voice_listening = True
        app.pet_voice_waiting_reply = False
        app.pet_voice_last_text = ''
        app._stop_pet_voice_recording = Mock()
        app._submit_pet_voice_text = Mock()
        app._finish_voice_turn = Mock()
        app.pet.reply_card_anchor.return_value = (100, 200)
        return app

    def test_timeout_submits_latest_interim_text_once(self):
        app = self.make_app()
        app.pet_voice_last_text = '已经识别的内容'

        MiniPetApp._on_pet_voice_recording_timeout(app)

        app._stop_pet_voice_recording.assert_called_once_with()
        app._submit_pet_voice_text.assert_called_once_with('已经识别的内容')
        app._finish_voice_turn.assert_not_called()
        app.note.setup_reply_card_text.assert_called_once()
        self.assertIn('继续处理已识别内容', app.note.setup_reply_card_text.call_args.args[0])

    def test_timeout_without_text_returns_to_existing_voice_state(self):
        app = self.make_app()

        MiniPetApp._on_pet_voice_recording_timeout(app)

        app._stop_pet_voice_recording.assert_called_once_with()
        app._submit_pet_voice_text.assert_not_called()
        app._finish_voice_turn.assert_called_once_with(delay_ms=0)
        app.note.setup_reply_card_text.assert_called_once()
        self.assertIn('未识别到可发送的内容', app.note.setup_reply_card_text.call_args.args[0])

    def test_stale_timeout_has_no_effect(self):
        app = self.make_app()
        app.pet_voice_listening = False

        MiniPetApp._on_pet_voice_recording_timeout(app)

        app._stop_pet_voice_recording.assert_not_called()
        app._submit_pet_voice_text.assert_not_called()
        app.note.setup_reply_card_text.assert_not_called()


if __name__ == '__main__':
    unittest.main()
