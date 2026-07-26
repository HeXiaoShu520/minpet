# coding:utf-8
"""miniPet surface 卡片事件的纯数据辅助函数。"""


SILENT_SURFACE_TEXTS = {'我在处理...', '我在处理…', '正在处理...', '正在处理…', '处理中...', '处理中…'}
TERMINAL_SURFACE_STATUSES = {'done', 'completed', 'complete', 'success', 'failed', 'failure', 'error'}
TEXT_ELEMENT_TYPES = {'markdown', 'text', 'plain_text', 'code'}


def surface_text(payload):
    """从 surface payload 中提取适合展示和语音播报的主文本。"""
    text = payload.get('text') or payload.get('message') or payload.get('summary') or payload.get('content') or ''
    if text:
        return str(text).strip()
    parts = []
    for element in payload.get('elements') or []:
        if not isinstance(element, dict):
            continue
        tag = element.get('tag') or element.get('type')
        if tag in TEXT_ELEMENT_TYPES:
            content = element.get('content') or element.get('text') or ''
            if content:
                parts.append(str(content))
    return '\n'.join(parts).strip()


def is_silent_surface_text(text):
    return not text or text in SILENT_SURFACE_TEXTS


def is_terminal_surface_status(payload):
    status = str(payload.get('status') or payload.get('state') or '').strip().lower().replace('_', '-')
    return status in TERMINAL_SURFACE_STATUSES


def surface_timeout(payload):
    if payload.get('timeout_ms') is not None:
        return int(payload.get('timeout_ms') or 0)
    lifetime = payload.get('lifetime') if isinstance(payload.get('lifetime'), dict) else {}
    if lifetime.get('ttl_ms') is not None:
        return int(lifetime.get('ttl_ms') or 0)
    if payload.get('timeout') is not None:
        return int(float(payload.get('timeout') or 0) * 1000)
    return 6000 if is_terminal_surface_status(payload) else 60000


def normalize_display_event(event_type, payload):
    event = dict(payload)
    event['type'] = event_type
    event.setdefault('summary', event.get('content') or event.get('description') or '')
    return event
