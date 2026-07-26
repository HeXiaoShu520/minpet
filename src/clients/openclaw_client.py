# coding:utf-8
"""OpenClaw Gateway HTTP client."""

import json
import os
from pathlib import Path
from urllib import error, request

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


def call_openclaw(message, cfg=None):
    cfg = cfg or config.app_config
    token = load_openclaw_token()
    if not token:
        return False, '未找到 OpenClaw Token。请设置 OPENCLAW_GATEWAY_TOKEN，或确认 ~/.openclaw/openclaw.json 存在。'
    api_url = cfg.get('openclaw_api_url') or config.OPENCLAW_API_URL_DEFAULT
    model = cfg.get('openclaw_model') or config.OPENCLAW_MODEL_DEFAULT
    user = cfg.get('openclaw_user') or config.OPENCLAW_USER_DEFAULT
    timeout = int(cfg.get('openclaw_timeout') or config.OPENCLAW_TIMEOUT_DEFAULT)
    body = json.dumps({
        'model': model,
        'input': message,
        'user': user,
    }, ensure_ascii=False).encode('utf-8')
    req = request.Request(
        api_url,
        data=body,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json; charset=utf-8',
        },
        method='POST',
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
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
    result_ready = Signal(bool, str)

    def __init__(self, message, cfg=None, parent=None):
        super().__init__(parent)
        self.message = message
        self.cfg = dict(cfg) if cfg is not None else dict(config.app_config)

    def run(self):
        self.result_ready.emit(*call_openclaw(self.message, self.cfg))
