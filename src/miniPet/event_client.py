# coding:utf-8
import asyncio
import json
import os
import urllib.request

import websockets
from PySide6.QtCore import QThread, Signal


class EventClient(QThread):
    event_received = Signal(dict)

    def __init__(self, url='ws://localhost:18888/ws/pet', action_url='http://localhost:18888/actions/execute', parent=None):
        super().__init__(parent)
        self.url = os.environ.get('MINIPET_EVENT_WS', os.environ.get('DYBERPET_EVENT_WS', url))
        self.action_url = os.environ.get('MINIPET_ACTION_URL', os.environ.get('DYBERPET_ACTION_URL', action_url))
        self.running = True
        self.loop = None
        self.ws = None

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._listen())
        except RuntimeError as e:
            if 'interpreter shutdown' not in str(e):
                raise
        finally:
            try:
                self.loop.close()
            except Exception:
                pass
            self.loop = None

    async def _listen(self):
        while self.running:
            try:
                async with websockets.connect(self.url) as ws:
                    self.ws = ws
                    async for raw in ws:
                        if not self.running:
                            break
                        try:
                            self.event_received.emit(self._normalize(json.loads(raw)))
                        except Exception:
                            pass
            except Exception:
                if self.running:
                    await asyncio.sleep(3)
            finally:
                self.ws = None

    def _normalize(self, data):
        if not isinstance(data, dict):
            return {'type': 'message', 'summary': str(data)}
        event = dict(data)
        event.setdefault('type', 'message')
        if event['type'] == 'message':
            sender = event.get('sender', '')
            chat_name = event.get('chat_name', '')
            event.setdefault('title', chat_name or sender or '外部消息')
            parsed = self._parse_message_content(event)
            if parsed:
                event.update(parsed)
            if not event.get('summary') and event.get('content'):
                event['summary'] = event.get('content')
            if not event.get('actions') and event.get('suggestion'):
                event['actions'] = [
                    {'id': 'copy', 'label': '复制建议'},
                    {'id': 'open_chat', 'label': '打开聊天'},
                    {'id': 'ignore', 'label': '忽略'},
                ]
        event.setdefault('priority', 'normal')
        return event

    def _parse_message_content(self, event):
        if event.get('msg_type') != 'post':
            return None
        try:
            post = json.loads(event.get('content') or '{}')
        except Exception:
            return None
        lines = []
        for row in post.get('content') or []:
            parts = []
            for item in row:
                tag = item.get('tag')
                if tag == 'text':
                    text = item.get('text') or ''
                    if 'bold' in (item.get('style') or []):
                        text = '**%s**' % text
                    parts.append(text)
                elif tag == 'img':
                    image_key = item.get('image_key') or ''
                    width = item.get('width') or ''
                    height = item.get('height') or ''
                    parts.append('![图片 %sx%s](lark-image:%s)' % (width, height, image_key))
                elif tag == 'code_block':
                    language = item.get('language') or ''
                    parts.append('```%s\n%s\n```' % (language.lower(), item.get('text') or ''))
            if parts:
                lines.append(''.join(parts))
        text = '\n\n'.join(lines).strip()
        return {'summary': text, 'message': text} if text else None

    def execute_action(self, event, action):
        payload = {
            'event': event,
            'action': action,
            'type': action.get('type') or action.get('id'),
            'text': action.get('text') or event.get('suggestion') or '',
        }
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                self.action_url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            urllib.request.urlopen(req, timeout=5).read()
            return True
        except Exception:
            return False

    def stop(self):
        self.running = False
        loop = self.loop
        ws = self.ws
        if loop is not None and ws is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(ws.close(), loop)
        self.quit()
        self.wait(1500)
