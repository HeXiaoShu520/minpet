# coding:utf-8
"""miniPet <-> OpenClaw 简化中转。

运行后监听 ws://127.0.0.1:18888/ws/pet，miniPet 连接这里。
收到 miniPet 的 user.command / user.drop 后，照抄 OpenClaw GUI 的方式调用：
    POST http://127.0.0.1:18789/v1/responses
再把 OpenClaw 回复发回 miniPet。
"""
import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib import error, request

import websockets

MINIPET_HOST = os.environ.get('MINIPET_ADAPTER_HOST', '127.0.0.1')
MINIPET_PORT = int(os.environ.get('MINIPET_ADAPTER_PORT', '18888'))
OPENCLAW_API_URL = os.environ.get('OPENCLAW_API_URL', 'http://127.0.0.1:18789/v1/responses')
OPENCLAW_MODEL = os.environ.get('OPENCLAW_MODEL', 'openclaw:main')
OPENCLAW_USER = os.environ.get('OPENCLAW_USER', 'minipet_adapter_user')
OPENCLAW_TIMEOUT = int(os.environ.get('OPENCLAW_TIMEOUT', '120'))

CLIENTS = set()


def load_openclaw_token():
    token = os.environ.get('OPENCLAW_GATEWAY_TOKEN') or os.environ.get('OPENCLAW_TOKEN')
    if token:
        return token.strip()
    config_path = Path.home() / '.openclaw' / 'openclaw.json'
    try:
        data = json.loads(config_path.read_text(encoding='utf-8'))
        return str(data.get('gateway', {}).get('auth', {}).get('token', '') or '').strip()
    except Exception:
        return ''


def start_openclaw_gateway():
    if os.environ.get('MINIPET_ADAPTER_AUTO_START_GATEWAY', '0').lower() not in ('1', 'true', 'yes', 'on'):
        return
    try:
        if sys.platform.startswith('win'):
            subprocess.Popen(['powershell', '-Command', 'openclaw gateway run'], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen(['openclaw', 'gateway', 'run'])
    except Exception as exc:
        print('启动 OpenClaw Gateway 失败:', exc)


def extract_openclaw_text(data):
    """复用 OpenClaw GUI 的解析逻辑，兼容 Responses API 常见返回。"""
    if isinstance(data, dict):
        output = data.get('output')
        if isinstance(output, list):
            for item in output:
                if isinstance(item, dict) and item.get('type') == 'message':
                    for content in item.get('content') or []:
                        if isinstance(content, dict) and content.get('type') == 'output_text':
                            return content.get('text') or ''
        if isinstance(data.get('text'), str):
            return data['text']
        if isinstance(data.get('message'), str):
            return data['message']
        return json.dumps(data, ensure_ascii=False)
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get('type') == 'message':
                for content in item.get('content') or []:
                    if isinstance(content, dict) and content.get('type') == 'output_text':
                        return content.get('text') or ''
        return json.dumps(data, ensure_ascii=False)
    return str(data)


def content_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                if item.get('type') in ('text', 'code'):
                    parts.append(str(item.get('text') or ''))
                elif item.get('type') == 'image':
                    parts.append('[图片]')
            else:
                parts.append(str(item))
        return '\n'.join(p for p in parts if p).strip()
    return str(value or '')


def prompt_from_minipet_message(msg):
    payload = msg.get('payload') if isinstance(msg.get('payload'), dict) else {}
    msg_type = msg.get('type')
    if msg_type == 'user.drop':
        intent = msg.get('intent') or payload.get('intent') or 'ask'
        items = msg.get('items') or payload.get('items') or []
        preview = msg.get('preview') or payload.get('preview') or ''
        lines = [f'用户通过 miniPet 投喂了内容，期望操作：{intent}。']
        if preview:
            lines.append(f'预览：{preview}')
        if items:
            lines.append('投喂项：')
            for item in items:
                if isinstance(item, dict):
                    lines.append('- ' + json.dumps(item, ensure_ascii=False))
                else:
                    lines.append('- ' + str(item))
        return '\n'.join(lines)
    text = msg.get('text') or payload.get('text') or payload.get('content') or msg.get('content') or ''
    return content_text(text).strip()


def call_openclaw(message):
    token = load_openclaw_token()
    if not token:
        raise RuntimeError('未找到 OpenClaw Token。请设置 OPENCLAW_GATEWAY_TOKEN，或确认 ~/.openclaw/openclaw.json 存在。')
    body = json.dumps({
        'model': OPENCLAW_MODEL,
        'input': message,
        'user': OPENCLAW_USER,
    }, ensure_ascii=False).encode('utf-8')
    req = request.Request(
        OPENCLAW_API_URL,
        data=body,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json; charset=utf-8',
        },
        method='POST',
    )
    with request.urlopen(req, timeout=OPENCLAW_TIMEOUT) as resp:
        raw = resp.read().decode('utf-8', errors='replace')
        return extract_openclaw_text(json.loads(raw))


async def send_minipet(ws, msg_type, **payload):
    await ws.send(json.dumps({'type': msg_type, **payload}, ensure_ascii=False))


async def handle_minipet(ws):
    CLIENTS.add(ws)
    print('miniPet 已连接')
    try:
        await send_minipet(ws, 'pet.say', text='miniPet Adapter 已连接 OpenClaw 中转')
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                await send_minipet(ws, 'pet.say', text='收到了一条不是 JSON 的消息')
                continue
            msg_type = msg.get('type')
            print('from miniPet:', msg_type, str(msg)[:300])
            if msg_type in ('hello', 'client.hello'):
                await send_minipet(ws, 'pet.say', text='我在，OpenClaw 中转已准备好')
                continue
            if msg_type not in ('user.command', 'user.drop', 'interaction.action', 'ui.button.clicked'):
                continue
            prompt = prompt_from_minipet_message(msg)
            if not prompt:
                await send_minipet(ws, 'pet.say', text='我没读到要发送给 OpenClaw 的内容')
                continue
            await send_minipet(ws, 'pet.say', text='收到，我去问 OpenClaw。')
            try:
                reply = await asyncio.to_thread(call_openclaw, prompt)
            except error.HTTPError as exc:
                detail = exc.read().decode('utf-8', errors='replace')[:500]
                if exc.code == 404:
                    detail = '请先启用 OpenClaw Responses API：openclaw config set gateway.http.endpoints.responses.enabled true'
                await send_minipet(ws, 'pet.say', text=f'OpenClaw HTTP {exc.code}: {detail}')
                continue
            except Exception as exc:
                await send_minipet(ws, 'pet.say', text='调用 OpenClaw 失败：' + str(exc))
                continue
            await send_minipet(ws, 'card', title='OpenClaw', content=reply)
    finally:
        CLIENTS.discard(ws)
        print('miniPet 已断开')


async def main():
    start_openclaw_gateway()
    print(f'miniPet Adapter 监听 ws://{MINIPET_HOST}:{MINIPET_PORT}/ws/pet')
    print(f'OpenClaw API: {OPENCLAW_API_URL}')
    async with websockets.serve(handle_minipet, MINIPET_HOST, MINIPET_PORT):
        await asyncio.Future()


if __name__ == '__main__':
    asyncio.run(main())
