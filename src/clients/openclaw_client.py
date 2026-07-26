# coding:utf-8
"""OpenClaw Gateway HTTP client."""

import json
import os
import socket
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse

from PySide6.QtCore import QThread, Signal

import config


def load_openclaw_token():
    env_data = {}
    try:
        env_data = config._parse_env_file()
    except Exception:
        env_data = {}
    token = (
        os.environ.get('OPENCLAW_GATEWAY_TOKEN')
        or os.environ.get('OPENCLAW_TOKEN')
        or env_data.get('OPENCLAW_GATEWAY_TOKEN')
        or env_data.get('OPENCLAW_TOKEN')
    )
    if token:
        return token.strip()
    config_path = Path.home() / '.openclaw' / 'openclaw.json'
    try:
        data = json.loads(config_path.read_text(encoding='utf-8'))
        return str(data.get('gateway', {}).get('auth', {}).get('token', '') or '').strip()
    except Exception:
        return ''


def extract_openclaw_text(data):
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


def probe_openclaw_gateway(api_url=None, timeout=3):
    """检测 OpenClaw 网关端口，并判断 Responses HTTP API 是否可用。"""
    target = (api_url or config.OPENCLAW_API_URL_DEFAULT).strip()
    if not target:
        return False, '请先填写 OpenClaw Gateway 地址。'
    parsed = urlparse(target)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    if not host:
        return False, 'OpenClaw Gateway 地址缺少主机名。'
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except TimeoutError:
        return False, f'连接超时：{host}:{port}'
    except OSError as exc:
        message = str(exc) or exc.__class__.__name__
        if isinstance(exc, ConnectionRefusedError):
            return False, f'连接被拒绝：{host}:{port} 没有服务监听。'
        if isinstance(exc, socket.gaierror):
            return False, '无法解析 OpenClaw Gateway 地址：' + message
        return False, f'端口检测失败：{message}'
    except Exception as exc:
        return False, '端口检测失败：' + (str(exc) or exc.__class__.__name__)

    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'Accept': 'application/json',
    }
    token = load_openclaw_token()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    body = json.dumps({'model': config.OPENCLAW_MODEL_DEFAULT}, ensure_ascii=False).encode('utf-8')
    req = request.Request(target, data=body, headers=headers, method='POST')
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return True, f'OpenClaw HTTP API 可访问：HTTP {resp.status}'
    except error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:200]
        if exc.code == 400:
            return True, 'OpenClaw 网关已启动，Responses HTTP API 已开启。'
        if exc.code == 401:
            return False, 'OpenClaw 网关已启动，Responses HTTP API 存在；但 Token 未通过鉴权。'
        if exc.code == 404:
            return False, 'OpenClaw 网关已启动，但 Responses HTTP API 未开启；可点击“一键开启”后重启网关。'
        return False, f'OpenClaw HTTP API 检测失败：HTTP {exc.code}: {detail}'
    except Exception as exc:
        return False, 'OpenClaw 网关端口可连接，但 HTTP API 检测失败：' + (str(exc) or exc.__class__.__name__)


def _iter_sse_events(resp):
    event_type = None
    data_lines = []
    for raw_line in resp:
        line = raw_line.decode('utf-8', errors='replace').rstrip('\r\n')
        if not line:
            if data_lines:
                yield event_type, '\n'.join(data_lines)
            event_type = None
            data_lines = []
            continue
        if line.startswith(':'):
            continue
        field, _, value = line.partition(':')
        if value.startswith(' '):
            value = value[1:]
        if field == 'event':
            event_type = value
        elif field == 'data':
            data_lines.append(value)
    if data_lines:
        yield event_type, '\n'.join(data_lines)


def _read_openclaw_stream(resp, on_delta=None):
    chunks = []
    final_text = ''
    for _, payload in _iter_sse_events(resp):
        if payload == '[DONE]':
            break
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        event_type = data.get('type') if isinstance(data, dict) else ''
        if event_type == 'response.output_text.delta':
            delta = data.get('delta') or ''
            if delta:
                chunks.append(delta)
                if on_delta:
                    on_delta(delta)
        elif event_type in ('response.output_text.done', 'response.content_part.done'):
            text = data.get('text') if event_type == 'response.output_text.done' else (data.get('part') or {}).get('text')
            if isinstance(text, str):
                final_text = text
        elif event_type == 'response.completed':
            text = extract_openclaw_text(data.get('response') or {})
            if text:
                final_text = text
        elif event_type == 'response.failed':
            response_data = data.get('response') or {}
            err = response_data.get('error') if isinstance(response_data, dict) else None
            message = err.get('message') if isinstance(err, dict) else ''
            return False, message or 'OpenClaw 流式响应失败。'
    return True, (final_text or ''.join(chunks)).strip()


def call_openclaw(message, cfg=None, on_delta=None):
    cfg = cfg or config.app_config
    token = load_openclaw_token()
    if not token:
        return False, '未找到 OpenClaw Token。请设置 OPENCLAW_GATEWAY_TOKEN，或确认 ~/.openclaw/openclaw.json 存在。'
    api_url = cfg.get('openclaw_api_url') or config.OPENCLAW_API_URL_DEFAULT
    model = cfg.get('openclaw_model') or config.OPENCLAW_MODEL_DEFAULT
    user = cfg.get('openclaw_user') or config.OPENCLAW_USER_DEFAULT
    timeout = int(cfg.get('openclaw_timeout') or config.OPENCLAW_TIMEOUT_DEFAULT)
    payload = {
        'model': model,
        'input': message,
        'user': user,
    }
    if on_delta:
        payload['stream'] = True
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = request.Request(
        api_url,
        data=body,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'text/event-stream' if on_delta else 'application/json',
        },
        method='POST',
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            if on_delta:
                return _read_openclaw_stream(resp, on_delta)
            raw = resp.read().decode('utf-8', errors='replace')
            return True, extract_openclaw_text(json.loads(raw)).strip()
    except error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:500]
        if exc.code == 404:
            detail = '请先启用 OpenClaw Responses API：openclaw config set gateway.http.endpoints.responses.enabled true'
        return False, f'OpenClaw HTTP {exc.code}: {detail}'
    except Exception as exc:
        return False, '调用 OpenClaw 失败：' + str(exc)


class OpenClawWorker(QThread):
    delta_ready = Signal(str)
    result_ready = Signal(bool, str)

    def __init__(self, message, cfg=None, parent=None):
        super().__init__(parent)
        self.message = message
        self.cfg = dict(cfg) if cfg is not None else dict(config.app_config)

    def run(self):
        self.result_ready.emit(*call_openclaw(self.message, self.cfg, on_delta=self.delta_ready.emit))
