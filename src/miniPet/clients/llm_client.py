# coding:utf-8
"""
大模型客户端封装。

对外提供 chat_completion() 和 ChatWorker：
- chat_completion() 是同步函数，内部按配置调用 OpenAI 兼容接口。
- ChatWorker 在 Qt 线程中调用 chat_completion()，用于 UI 不阻塞地接收回复。
"""

import asyncio

from PySide6.QtCore import QThread, Signal

try:
    from openai import AsyncOpenAI, APIConnectionError as OpenAIConnectionError, APITimeoutError as OpenAITimeoutError
except Exception:
    AsyncOpenAI = None
    OpenAIConnectionError = Exception
    OpenAITimeoutError = TimeoutError

from miniPet import config


def _normalize_openai_messages(messages):
    """规范化 OpenAI 兼容接口需要的 text/image_url 消息块。"""
    normalized = []
    for msg in messages:
        content = msg.get('content', '')
        if isinstance(content, list):
            blocks = []
            for block in content:
                block_type = block.get('type')
                if block_type == 'text':
                    blocks.append({'type': 'text', 'text': block.get('text', '')})
                elif block_type == 'image_url':
                    image_url = block.get('image_url')
                    if isinstance(image_url, str):
                        image_url = {'url': image_url}
                    blocks.append({'type': 'image_url', 'image_url': image_url or {}})
            normalized.append({'role': msg.get('role'), 'content': blocks})
        else:
            normalized.append({'role': msg.get('role'), 'content': content})
    return normalized


async def _call_openai(messages, cfg, timeout, on_delta=None):
    """调用 OpenAI 兼容 Chat Completions 接口，支持流式 delta 回调。"""
    if AsyncOpenAI is None:
        return False, '缺少 openai SDK，请执行：pip install openai'
    api_base = (cfg.get('api_base') or '').rstrip('/') or None
    api_key = cfg.get('api_key') or ''
    model = cfg.get('model') or ''
    if not model:
        return False, '未配置模型名称。'
    if not api_key:
        return False, '未配置 API Key。'
    kwargs = {'api_key': api_key, 'timeout': timeout, 'max_retries': 1}
    if api_base:
        kwargs['base_url'] = api_base
    client = AsyncOpenAI(**kwargs)
    messages = _normalize_openai_messages(messages)
    try:
        if on_delta:
            chunks = []
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=int(cfg.get('max_tokens') or 1024),
                stream=True,
            )
            async for event in stream:
                delta = event.choices[0].delta.content if event.choices else None
                if delta:
                    chunks.append(delta)
                    on_delta(delta)
            return True, ''.join(chunks).strip()
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=int(cfg.get('max_tokens') or 1024),
        )
        return True, (response.choices[0].message.content or '').strip()
    except OpenAITimeoutError as e:
        return False, '网络超时：%s' % e
    except OpenAIConnectionError as e:
        return False, '网络错误：%s' % e
    except Exception as e:
        return False, '请求失败：%s' % e


async def _chat_async(messages, cfg, timeout, on_delta=None):
    return await _call_openai(messages, cfg, timeout, on_delta)


def chat_completion(messages, cfg=None, timeout=60, on_delta=None):
    """同步聊天补全入口，供普通逻辑和 Qt Worker 复用。"""
    cfg = cfg or config.llm_config
    try:
        return asyncio.run(_chat_async(messages, cfg, timeout, on_delta))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_chat_async(messages, cfg, timeout, on_delta))
        finally:
            loop.close()


class ChatWorker(QThread):
    """在后台线程中执行 LLM 请求，避免阻塞 Qt UI。"""

    delta_ready = Signal(str)
    result_ready = Signal(bool, str)

    def __init__(self, messages, cfg=None, parent=None):
        super().__init__(parent)
        self.messages = list(messages)
        self.cfg = dict(cfg) if cfg is not None else dict(config.llm_config)

    def run(self):
        self.result_ready.emit(*chat_completion(self.messages, self.cfg, on_delta=self.delta_ready.emit))
