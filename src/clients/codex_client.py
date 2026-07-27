# coding:utf-8
"""Codex JSONL 本地连续会话桥接。"""

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import threading

from PySide6.QtCore import QThread, Signal


ANSI_RE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
MAX_OUTPUT_CHARS = 3000


class CodexSession(QThread):
    output_ready = Signal(str)
    result_ready = Signal(str)
    error_ready = Signal(str)
    thread_ready = Signal(str)
    thread_invalidated = Signal(str)
    stopped = Signal()

    def __init__(self, project_dir, reset_token=0, thread_id='', parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.reset_token = int(reset_token or 0)
        self.thread_id = str(thread_id or '').strip()
        self._proc = None
        self._proc_lock = threading.Lock()
        self._stopping = False
        self._buffer = ''
        self._write_queue = queue.Queue()
        self._turn_final_text = ''
        self._turn_completed = False
        self._turn_error = ''

    def send(self, text):
        text = (text or '').strip()
        if not text or self._stopping:
            return False
        self._write_queue.put(text)
        return True

    def interrupt(self):
        self._terminate_active_process()

    def stop(self):
        self._stopping = True
        self._write_queue.put(None)
        self._terminate_active_process()

    def run(self):
        if not shutil.which('codex'):
            self.error_ready.emit('找不到 codex 命令，请先安装 Codex CLI 并加入 PATH。')
            self.stopped.emit()
            return

        try:
            while not self._stopping:
                try:
                    prompt = self._write_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                if prompt is None:
                    break
                self._run_prompt(prompt, allow_new_retry=True)
        except Exception as exc:
            if not self._stopping:
                self.error_ready.emit('Codex 会话异常：%s' % exc)
        finally:
            self._terminate_active_process()
            self.stopped.emit()

    def _command(self, resume):
        if resume:
            return ['codex', 'exec', 'resume', self.thread_id, '--json', '-']
        return ['codex', 'exec', '--json', '--cd', self.project_dir, '-']

    def _run_prompt(self, prompt, allow_new_retry):
        resume = bool(self.thread_id)
        self._buffer = ''
        self._turn_final_text = ''
        self._turn_completed = False
        self._turn_error = ''
        proc = None
        stderr_text = ''
        try:
            proc = subprocess.Popen(
                self._command(resume),
                cwd=self.project_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),
            )
            with self._proc_lock:
                self._proc = proc
            try:
                proc.stdin.write(prompt + '\n')
                proc.stdin.flush()
                proc.stdin.close()
            except Exception:
                pass

            while not self._stopping and proc.stdout is not None:
                line = proc.stdout.readline()
                if not line:
                    break
                self._handle_json_line(line)

            if proc.poll() is None:
                proc.wait(timeout=3)
            if proc.stderr is not None:
                stderr_text = proc.stderr.read() or ''
        except subprocess.TimeoutExpired:
            self._terminate_process(proc)
        except Exception as exc:
            if not self._stopping:
                self.error_ready.emit('Codex 执行失败：%s' % exc)
            return
        finally:
            with self._proc_lock:
                if self._proc is proc:
                    self._proc = None

        if self._stopping:
            return
        error_text = self._turn_error or ANSI_RE.sub('', stderr_text).strip()
        if resume and allow_new_retry and self._resume_target_missing(error_text):
            old_thread_id = self.thread_id
            self.thread_id = ''
            self.thread_invalidated.emit(old_thread_id)
            self._run_prompt(prompt, allow_new_retry=False)
            return
        if error_text and proc is not None and proc.returncode not in (0, None):
            self.error_ready.emit(error_text)
            return
        if not self._turn_completed:
            if self._turn_final_text:
                self.result_ready.emit(self._turn_final_text)
            elif proc is not None and proc.returncode not in (0, None):
                self.error_ready.emit(error_text or 'Codex 调用失败。')

    def _handle_json_line(self, line):
        line = (line or '').strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self._append_output(line)
            return
        if not isinstance(event, dict):
            return

        event_type = str(event.get('type') or event.get('event_type') or '')
        if event_type == 'thread.started':
            thread_id = str(event.get('thread_id') or '').strip()
            if thread_id:
                self.thread_id = thread_id
                self.thread_ready.emit(thread_id)
            return

        if event_type == 'item.completed':
            item = event.get('item') or {}
            if isinstance(item, dict) and item.get('type') == 'agent_message':
                text = str(item.get('text') or '').strip()
                if text:
                    self._turn_final_text = text
                    self._set_output(text)
            return

        if event_type == 'turn.completed':
            self._turn_completed = True
            if self._turn_final_text:
                self.result_ready.emit(self._turn_final_text)
            else:
                self.error_ready.emit('Codex 没有返回文本。')
            return

        if event_type in ('error', 'fatal', 'turn.failed'):
            self._turn_error = self._error_text(event) or 'Codex 调用失败。'

    def _error_text(self, event):
        error = event.get('error')
        if isinstance(error, dict):
            return str(error.get('message') or error.get('type') or '').strip()
        if isinstance(error, str):
            return error.strip()
        message = event.get('message')
        if isinstance(message, str):
            return message.strip()
        return ''

    def _resume_target_missing(self, text):
        text = str(text or '').lower()
        if not text:
            return False
        target = 'thread' in text or 'session' in text or 'conversation' in text
        missing = any(marker in text for marker in (
            'not found',
            'no thread',
            'no session',
            'no conversation',
            'unknown thread',
            'unknown session',
            'failed to find',
            'failed to load',
            'failed to resume',
        ))
        return target and missing

    def _set_output(self, text):
        self._buffer = ANSI_RE.sub('', text or '')[-MAX_OUTPUT_CHARS:]
        if self._buffer:
            self.output_ready.emit(self._buffer.strip())

    def _append_output(self, text):
        text = ANSI_RE.sub('', text or '')
        if not text:
            return
        self._buffer = (self._buffer + text)[-MAX_OUTPUT_CHARS:]
        self.output_ready.emit(self._buffer.strip())

    def _terminate_active_process(self):
        with self._proc_lock:
            proc = self._proc
        self._terminate_process(proc)

    def _terminate_process(self, proc):
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
            if proc.poll() is None:
                try:
                    if os.name == 'nt':
                        proc.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        proc.send_signal(signal.SIGINT)
                except Exception:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2)
        except Exception:
            pass
