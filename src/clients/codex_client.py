# coding:utf-8
"""Codex 本地会话桥接。"""

import json
import os
import queue
import re
import shutil
import signal
import subprocess

from PySide6.QtCore import QThread, Signal


ANSI_RE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
MAX_OUTPUT_CHARS = 3000


class CodexSession(QThread):
    output_ready = Signal(str)
    result_ready = Signal(str)
    error_ready = Signal(str)
    stopped = Signal()

    def __init__(self, project_dir, parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self._stopping = False
        self._buffer = ''
        self._write_queue = queue.Queue()

    def send(self, text):
        text = (text or '').strip()
        if not text:
            return False
        self._write_queue.put(text)
        return True

    def interrupt(self):
        self.stop()

    def stop(self):
        self._stopping = True
        self._write_queue.put(None)

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
                self._buffer = ''
                self._run_exec_prompt(prompt)
        except Exception as exc:
            if not self._stopping:
                self.error_ready.emit('Codex 会话异常：%s' % exc)
        finally:
            self.stopped.emit()

    def _run_exec_prompt(self, prompt):
        command = [
            'codex',
            'exec',
            '--json',
            '--ephemeral',
            '--cd', self.project_dir,
            '-',
        ]
        proc = None
        try:
            proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),
            )
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

            stderr_text = ''
            if proc.stderr is not None:
                try:
                    stderr_text = proc.stderr.read() or ''
                except Exception:
                    stderr_text = ''
            if proc.poll() not in (0, None):
                text = ANSI_RE.sub('', stderr_text).strip()
                if text:
                    self.error_ready.emit(text)
        except Exception as exc:
            if not self._stopping:
                self.error_ready.emit('Codex 执行失败：%s' % exc)
        finally:
            if proc is not None:
                try:
                    if proc.poll() is None:
                        self._terminate_process(proc)
                except Exception:
                    pass

    def _terminate_process(self, proc):
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
        except Exception:
            pass

    def _handle_json_line(self, line):
        line = (line or '').strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self._append_output(line)
            return

        if isinstance(event, dict) and 'event' in event and isinstance(event['event'], dict):
            event = event['event']

        event_type = str(event.get('type') or event.get('event_type') or '')
        if event_type in ('error', 'fatal'):
            self.error_ready.emit(self._event_text(event) or 'Codex 调用失败。')
            return

        if event_type in ('result', 'final', 'done', 'completed'):
            text = self._event_text(event)
            if text:
                self.result_ready.emit(text)
            return

        text = self._event_text(event)
        if text:
            self._append_output(text)

    def _event_text(self, event):
        if not isinstance(event, dict):
            return ''

        for key in ('text', 'content', 'message', 'output_text', 'result'):
            value = event.get(key)
            if isinstance(value, str) and value.strip():
                return value

        delta = event.get('delta')
        if isinstance(delta, dict):
            for key in ('text', 'content', 'message', 'output_text'):
                value = delta.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        content = event.get('content')
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    for key in ('text', 'content', 'result'):
                        value = block.get(key)
                        if isinstance(value, str):
                            parts.append(value)
                            break
            return ''.join(parts).strip()

        message = event.get('message')
        if isinstance(message, dict):
            content = message.get('content')
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict):
                        for key in ('text', 'content', 'result'):
                            value = block.get(key)
                            if isinstance(value, str):
                                parts.append(value)
                                break
                return ''.join(parts).strip()

        return ''

    def _append_output(self, text):
        text = ANSI_RE.sub('', text or '')
        if not text:
            return
        self._buffer = (self._buffer + text)[-MAX_OUTPUT_CHARS:]
        self.output_ready.emit(self._buffer.strip())
