# coding:utf-8
"""
外部智能体事件客户端。

miniPet 可选连接 OpenClaw 或通用后端 WebSocket。这个模块负责维持连接、发送
session hello、接收事件并规范化为协议 V1 的内部事件字典。
"""

import asyncio
import json
import os
import urllib.request

import websockets
from PySide6.QtCore import QThread, Signal

from miniPet.protocols.protocol_v1 import SESSION_HELLO, USER_ACTION, hello_payload, normalize_inbound_event


class EventClient(QThread):
    """后台 WebSocket 客户端，向 UI 线程发出规范化事件。"""

    event_received = Signal(dict)
    connection_changed = Signal(bool)

    def __init__(self, url='ws://localhost:18888/ws/pet', action_url='http://localhost:18888/actions/execute', parent=None):
        super().__init__(parent)
        self.default_url = url
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
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as ws:
                    self.ws = ws
                    self.connection_changed.emit(True)
                    await self._send({
                        'version': '1.0',
                        'type': SESSION_HELLO,
                        'source': 'minipet',
                        'payload': hello_payload('miniPet'),
                    })
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
                if self.ws is not None:
                    self.connection_changed.emit(False)
                self.ws = None

    def _normalize(self, data):
        if not isinstance(data, dict):
            return normalize_inbound_event(data)
        event = dict(data)
        event.setdefault('type', 'message')
        event.setdefault('priority', 'normal')
        return normalize_inbound_event(event)

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

    async def _send(self, payload):
        if self.ws is None:
            return False
        await self.ws.send(json.dumps(payload, ensure_ascii=False))
        return True

    def send_event(self, event_type, payload=None, request_id=None):
        return self._send_event_message(event_type, payload, request_id)

    def send_v1_event(self, v1_type, payload=None, request_id=None):
        return self._send_event_message(v1_type, payload, request_id)

    def _send_event_message(self, event_type, payload=None, request_id=None):
        message = {
            'version': '1.0',
            'type': event_type,
            'source': 'minipet',
            'payload': payload or {},
        }
        if request_id:
            message['request_id'] = request_id
        loop = self.loop
        ws = self.ws
        if loop is not None and ws is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._send(message), loop)
                return True
            except Exception:
                pass
        return self._post_action(message)

    def _post_action(self, payload):
        try:
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
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

    def execute_action(self, event, action):
        surface_id = event.get('surface_id') or event.get('card_id') or event.get('confirm_id') or event.get('interaction_id')
        action_id = action.get('id') or action.get('type')
        payload = {
            'surface_id': surface_id,
            'action_id': action_id,
            'intent': action.get('intent'),
            'action': action,
            'metadata': event.get('metadata') or {},
        }
        if event.get('values') is not None:
            payload['values'] = event.get('values')
        return self.send_event(USER_ACTION, payload)

    def set_url(self, url):
        self.url = url or self.default_url

    def reconnect(self, url=None):
        if url:
            self.set_url(url)
        loop = self.loop
        ws = self.ws
        if loop is not None and ws is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(ws.close(), loop)
            except Exception:
                pass

    def stop(self):
        self.running = False
        loop = self.loop
        ws = self.ws
        if loop is not None and ws is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(ws.close(), loop)
        self.quit()
        self.wait(1500)
