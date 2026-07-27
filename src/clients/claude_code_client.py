# coding:utf-8
"""Claude Code stream-json 本地会话桥接。"""

import hashlib
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import uuid

from PySide6.QtCore import QThread, Signal


ANSI_RE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
MAX_OUTPUT_CHARS = 3000


class ClaudeCodeSession(QThread):
    output_ready = Signal(str)
    result_ready = Signal(str)
    error_ready = Signal(str)
    stopped = Signal()
    process_ready = Signal()
    session_ready = Signal(str)
    session_mode_mismatch = Signal(str)

    def __init__(self, project_dir, reset_token=0, resume=False, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.session_id = self._session_id_for_project(project_dir, reset_token)
        self.resume = bool(resume)
        self._proc = None
        self._stopping = False
        self._buffer = ''
        self._write_queue = queue.Queue()
        self._write_thread_started = False
        self._process_ready_emitted = False
        self._session_ready_emitted = False
        self._mode_mismatch_emitted = False

    @staticmethod
    def _session_id_for_project(project_dir, reset_token=0):
        project_key = str(project_dir or '').strip() or '.'
        project_key = project_key.replace('\\', '/').lower()
        reset_token = int(reset_token or 0)
        if reset_token:
            project_key += '#reset:%s' % reset_token
        digest = hashlib.sha256(project_key.encode('utf-8')).digest()
        return str(uuid.UUID(bytes=digest[:16], version=4))

    def send(self, text):
        text = (text or '').strip()
        if not text:
            return False
        self._buffer = ''
        self._write_queue.put(text)
        return True

    def interrupt(self):
        self._send_interrupt()

    def stop(self):
        self._stopping = True
        self._terminate_process()

    def _send_interrupt(self):
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
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

    def _terminate_process(self):
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
            if proc.poll() is None:
                self._send_interrupt()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
        except Exception:
            pass

    def run(self):
        if not shutil.which('claude'):
            self.error_ready.emit('找不到 claude 命令，请先安装 Claude Code 并加入 PATH。')
            self.stopped.emit()
            return

        self._cleanup_own_claude_processes()
        try:
            self._proc = subprocess.Popen(
                self._command(),
                cwd=self.project_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
            )
            self._start_stderr_thread()
            if not self._write_thread_started:
                self._start_write_thread()
                self._write_thread_started = True
            self._read_stdout_loop()
        except Exception as exc:
            if not self._stopping:
                self.error_ready.emit('Claude Code 会话异常：%s' % exc)
        finally:
            self._terminate_process()
            self._proc = None
            self.stopped.emit()

    def _cleanup_own_claude_processes(self):
        if os.name != 'nt':
            return
        try:
            tasklist = subprocess.run(
                ['wmic', 'process', 'where', "name='claude.exe'", 'get', 'ProcessId,ParentProcessId,CommandLine', '/format:csv'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=3,
            )
        except Exception:
            return
        current_pid = os.getpid()
        for line in (tasklist.stdout or '').splitlines():
            if self.session_id not in line:
                continue
            parts = [part.strip() for part in line.split(',')]
            if len(parts) < 4:
                continue
            try:
                parent_pid = int(parts[-2])
                process_id = int(parts[-1])
            except ValueError:
                continue
            if parent_pid != current_pid:
                continue
            try:
                subprocess.run(['taskkill', '/PID', str(process_id), '/T', '/F'], capture_output=True, timeout=3)
            except Exception:
                pass

    def _command(self):
        command = [
            'claude',
            '--print',
            '--verbose',
            '--input-format', 'stream-json',
            '--output-format', 'stream-json',
            '--include-partial-messages',
            '--replay-user-messages',
            '--permission-mode', 'auto',
        ]
        if self.resume:
            command.extend(['--resume', self.session_id])
        else:
            command.extend(['--session-id', self.session_id])
        return command

    def _start_write_thread(self):
        threading.Thread(target=self._write_loop, daemon=True).start()

    def _start_stderr_thread(self):
        threading.Thread(target=self._read_stderr_loop, daemon=True).start()

    def _write_loop(self):
        while not self._stopping:
            try:
                text = self._write_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if not self._wait_writable_process():
                if not self._stopping:
                    self.error_ready.emit('Claude Code 进程未运行，发送失败。')
                continue
            try:
                event = {
                    'type': 'user',
                    'message': {
                        'role': 'user',
                        'content': [{'type': 'text', 'text': text}],
                    },
                }
                payload = json.dumps(event, ensure_ascii=False)
                print('[Claude Code stdin]', payload, flush=True)
                self._proc.stdin.write(payload + '\n')
                self._proc.stdin.flush()
            except Exception as exc:
                if not self._stopping:
                    self.error_ready.emit('发送给 Claude Code 失败：%s' % exc)

    def _wait_writable_process(self):
        return self._proc is not None and self._proc.poll() is None and self._proc.stdin is not None

    def _read_stdout_loop(self):
        while not self._stopping and self._proc is not None and self._proc.stdout is not None:
            line = self._proc.stdout.readline()
            if not line:
                break
            print('[Claude Code stdout]', line.rstrip(), flush=True)
            self._handle_json_line(line)

    def _read_stderr_loop(self):
        proc = self._proc
        while not self._stopping and proc is not None and proc.stderr is not None:
            line = proc.stderr.readline()
            if not line:
                break
            text = ANSI_RE.sub('', line or '').strip()
            if not text:
                continue
            print('[Claude Code stderr]', text, flush=True)
            if self._handle_mode_mismatch(text):
                continue
            self.error_ready.emit(text)

    def _handle_json_line(self, line):
        line = (line or '').strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self._append_output(line)
            return

        event_type = event.get('type', '')
        if event_type == 'system' and event.get('subtype') == 'init' and not self._process_ready_emitted:
            self._process_ready_emitted = True
            self.process_ready.emit()
        if event_type == 'stream_event' and isinstance(event.get('event'), dict):
            event = event.get('event')
            event_type = event.get('type', '')
        if event_type == 'error':
            text = self._event_error_text(event) or 'Claude Code 调用失败。'
            if not self._handle_mode_mismatch(text):
                self.error_ready.emit(text)
            return

        if event_type in ('system', 'result', 'stream_event') and not self._session_ready_emitted:
            self._session_ready_emitted = True
            self.session_ready.emit(self.session_id)

        text = self._event_text(event)
        if text:
            self._append_output(text)

    def _handle_mode_mismatch(self, text):
        if self._mode_mismatch_emitted:
            return True
        normalized = str(text or '').lower()
        if not self.resume and 'session id' in normalized and 'already in use' in normalized:
            mode = 'resume'
        elif self.resume and ('no conversation found' in normalized or 'session not found' in normalized or 'could not find session' in normalized):
            mode = 'new'
        else:
            return False
        self._mode_mismatch_emitted = True
        self.session_mode_mismatch.emit(mode)
        return True

    def _event_error_text(self, event):
        error = event.get('error')
        if isinstance(error, dict):
            return error.get('message') or error.get('type') or json.dumps(error, ensure_ascii=False)
        if isinstance(error, str):
            return error
        return event.get('message') if isinstance(event.get('message'), str) else ''

    def _event_text(self, event):
        event_type = event.get('type', '')

        if event_type in ('user', 'system'):
            return ''

        if event_type == 'assistant':
            return ''

        if event_type == 'result':
            text = event.get('result') or self._message_text(event.get('message'))
            if text:
                self.result_ready.emit(text)
            return ''

        if event_type == 'content_block_delta':
            delta = event.get('delta') or {}
            if isinstance(delta, dict):
                return delta.get('text') or delta.get('thinking') or ''

        if event_type == 'content_block_start':
            block = event.get('content_block') or {}
            if isinstance(block, dict) and block.get('type') == 'text':
                return block.get('text') or ''

        if event_type == 'message_delta':
            delta = event.get('delta') or {}
            if isinstance(delta, dict):
                return delta.get('text') or ''

        return ''

    def _message_text(self, message):
        if isinstance(message, str):
            return message
        if not isinstance(message, dict):
            return ''
        content = message.get('content')
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ''
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get('type') in ('text', 'output_text'):
                parts.append(block.get('text') or '')
        return ''.join(parts)

    def _append_output(self, text):
        text = ANSI_RE.sub('', text or '')
        if not text:
            return
        self._buffer = (self._buffer + text)[-MAX_OUTPUT_CHARS:]
        self.output_ready.emit(self._buffer.strip())
