# coding:utf-8
"""日常工作语音输入控制器。"""

from PySide6.QtCore import QObject, QTimer

import config
from clients.asr_client import AsrWorker
from clients.middle_btn_listener import MiddleButtonListener


class DailyInputController(QObject):

    def __init__(self, app=None, parent=None):
        super().__init__(parent)
        self._app = app
        self._listener = None
        self._asr_worker = None
        self._recording = False
        self._last_text = ''
        self._accumulated_text = ''

    # ── 唤醒词互斥 ──────────────────────────────────────────────────────

    def _pause_wake_word(self):
        if self._app is not None and hasattr(self._app, '_pause_wake_word_listener'):
            self._app._pause_wake_word_listener()

    def _resume_wake_word(self):
        if self._app is not None and hasattr(self._app, '_resume_wake_word_listener'):
            self._app._resume_wake_word_listener()

    # ── 设置 ────────────────────────────────────────────────────────────

    def apply_settings(self):
        enabled = bool(config.daily_input_config.get('enabled', False))
        print('[语音输入小助手] 设置更新 enabled=%s' % enabled)
        if enabled:
            self._ensure_listener()
        else:
            self._stop_listener()

    def _ensure_listener(self):
        if self._listener is not None:
            return
        self._listener = MiddleButtonListener(parent=self)
        self._listener.toggled.connect(self._on_middle_btn_toggled)
        self._listener.start()
        print('[语音输入小助手] 中键监听器已启动')

    def _stop_listener(self):
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
            print('[语音输入小助手] 中键监听器已停止')

    # ── 中键触发 ────────────────────────────────────────────────────────

    def _on_middle_btn_toggled(self):
        # 语音聊天正在录音/思考/播放时，忽略中键
        if self._app is not None:
            popup = getattr(self._app.pet, 'voice_popup', None)
            voice_active = getattr(self._app, 'pet_voice_active', False)
            if voice_active and popup is not None:
                busy_states = ('listening', 'thinking', 'speaking')
                if popup.state in busy_states:
                    print('[语音输入小助手] 中键忽略：语音球正在语音聊天 state=%s' % popup.state)
                    return
        print('[语音输入小助手] 中键触发 recording=%s asr_worker=%s' % (self._recording, self._asr_worker))
        # 若上一次 worker 已结束但没被清理，补清
        if self._asr_worker is not None and not self._asr_worker.isRunning():
            print('[语音输入小助手] 清理旧录音任务')
            self._asr_worker = None
            self._recording = False
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    # ── 录音生命周期 ─────────────────────────────────────────────────────

    def _start_recording(self):
        if not config.tts_config.get('api_key'):
            print('[语音输入小助手] 缺少 API Key，无法录音')
            return
        if self._asr_worker is not None:
            print('[语音输入小助手] 录音任务仍在运行，跳过')
            return
        print('[语音输入小助手] 开始录音')
        self._pause_wake_word()
        self._recording = True
        self._last_text = ''
        self._accumulated_text = ''
        if self._app is not None:
            self._app.pet.update_voice_popup('typing', '语音输入中')
        self._asr_worker = AsrWorker(parent=self)
        self._asr_worker.text_received.connect(self._on_text_received)
        self._asr_worker.final_received.connect(self._on_final_received)
        self._asr_worker.error_received.connect(self._on_error)
        self._asr_worker.finished_signal.connect(self._on_asr_finished)
        self._asr_worker.start()
        QTimer.singleShot(250, self._asr_worker.start_recording)

    def _stop_recording(self):
        print('[语音输入小助手] 停止录音')
        self._recording = False
        text = self._accumulated_text or self._last_text
        self._accumulated_text = ''
        worker = self._asr_worker
        self._asr_worker = None
        if worker is not None:
            worker.finish()
        self._restore_voice_popup_state()
        if text:
            QTimer.singleShot(80, lambda: self._inject_text(text))

    def _restore_voice_popup_state(self):
        self._resume_wake_word()
        if self._app is None:
            return
        if not getattr(self._app, 'pet_voice_active', False):
            self._app.pet.close_voice_popup()
        else:
            if self._app._wake_word_enabled():
                self._app.pet.update_voice_popup('wakeup', '')
            else:
                self._app.pet.update_voice_popup('idle', '')

    def _finish_recording(self, reason=''):
        print('[语音输入小助手] 录音结束 reason=%s' % (reason or 'callback'))
        self._recording = False
        self._accumulated_text = ''
        self._asr_worker = None
        self._restore_voice_popup_state()

    # ── ASR 回调 ─────────────────────────────────────────────────────────

    def _on_text_received(self, text):
        if text:
            self._last_text = text
            if self._app is not None:
                self._app.pet.update_voice_popup('typing', text)

    def _on_final_received(self, text):
        text = (text or '').strip()
        if text:
            self._accumulated_text = (self._accumulated_text + text).strip()
        if self._accumulated_text and self._app is not None:
            self._app.pet.update_voice_popup('typing', self._accumulated_text)
        print('[语音输入小助手] 识别结果: %r  累积: %r' % (text, self._accumulated_text))

    def _on_error(self, text):
        print('[语音输入小助手] 识别错误: %s' % text)
        self._finish_recording('error')

    def _on_asr_finished(self):
        print('[语音输入小助手] 识别任务结束, recording=%s' % self._recording)
        self._asr_worker = None
        self._recording = False

    # ── 文字注入 ──────────────────────────────────────────────────────────

    def _inject_text(self, text):
        print('[语音输入小助手] 输入文字: %r' % text)
        try:
            from pynput.keyboard import Controller
            Controller().type(text)
        except Exception as e:
            print('[语音输入小助手] 输入失败:', e)

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def shutdown(self):
        print('[语音输入小助手] 关闭')
        self._stop_listener()
        self._recording = False
        if self._asr_worker is not None:
            try:
                self._asr_worker.finish()
                self._asr_worker.wait(1200)
            except Exception:
                pass
            self._asr_worker = None
        self._restore_voice_popup_state()
