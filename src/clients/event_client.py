# coding:utf-8
"""
外部智能体事件客户端。

MiniPet 可选连接通用协议后端 WebSocket。这个模块负责维持连接、发送
session hello、接收事件并规范化为协议 V1 的内部事件字典。
"""

import asyncio
import json
import os
import socket
import urllib.request
import uuid
from urllib.parse import urlparse

import websockets
from PySide6.QtCore import QThread, Signal

from protocols.protocol_v1 import SESSION_HELLO, SESSION_PROBE, SESSION_PROBE_RESULT, USER_INPUT, hello_payload, normalize_inbound_event, probe_payload


async def _probe_minipet_backend_async(url, timeout=3):
    request_id = 'probe_' + uuid.uuid4().hex
    async with websockets.connect(url, ping_interval=None, open_timeout=timeout, close_timeout=1) as ws:
        await ws.send(json.dumps({
            'version': '1.0',
            'type': SESSION_PROBE,
            'request_id': request_id,
            'payload': probe_payload(),
        }, ensure_ascii=False))
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        event = normalize_inbound_event(json.loads(raw))
        if event.get('type') != SESSION_PROBE_RESULT:
            return False, '后端已连接，但未返回 session.probe.result。'
        if event.get('request_id') and event.get('request_id') != request_id:
            return False, '后端返回了检测结果，但 request_id 不匹配。'
        payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
        protocol = payload.get('protocol') or ''
        if protocol and protocol != 'minipet.v1':
            return False, '后端协议不匹配：' + str(protocol)
        server = payload.get('server') if isinstance(payload.get('server'), dict) else {}
        name = server.get('name') or payload.get('name') or 'MiniPet 协议后端'
        return True, '协议检测通过：' + str(name)


def probe_minipet_backend(url, timeout=3):
    """通过 session.probe 检测 MiniPet 协议后端。"""
    target = (url or '').strip()
    if not target:
        return False, '请先填写 MiniPet 协议后端地址。'
    if not (target.startswith('ws://') or target.startswith('wss://')):
        return False, '后端地址需要以 ws:// 或 wss:// 开头。'
    parsed = urlparse(target)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == 'wss' else 80)
    if not host:
        return False, '后端地址缺少主机名。'
    try:
        return asyncio.run(_probe_minipet_backend_async(target, timeout=timeout))
    except TimeoutError:
        return False, f'连接或等待检测结果超时：{host}:{port}'
    except asyncio.TimeoutError:
        return False, f'等待检测结果超时：{host}:{port}'
    except OSError as exc:
        message = str(exc) or exc.__class__.__name__
        if isinstance(exc, ConnectionRefusedError):
            return False, f'连接被拒绝：{host}:{port} 没有服务监听。'
        if isinstance(exc, socket.gaierror):
            return False, '无法解析后端地址：' + message
        return False, f'连接 MiniPet 协议后端失败：{message}'
    except Exception as exc:
        return False, 'MiniPet 协议检测失败：' + (str(exc) or exc.__class__.__name__)


class EventClient(QThread):
    """后台 WebSocket 客户端，向 UI 线程发出规范化事件。"""

    event_received = Signal(dict)
    connection_changed = Signal(bool)

    def __init__(self, url='ws://127.0.0.1:18889/ws/minipet', action_url='http://127.0.0.1:18889/actions/execute', parent=None):
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
                        'payload': hello_payload(),
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
        action_text = action.get('label') or action.get('text') or action.get('id') or action.get('type') or '确认'
        values = event.get('values')
        if values:
            action_text += '\n' + json.dumps(values, ensure_ascii=False)
        return self.send_event(USER_INPUT, {'text': action_text})

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
