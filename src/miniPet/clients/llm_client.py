# coding:utf-8
"""
大模型客户端封装。

对外提供 chat_completion() 和 ChatWorker：
- chat_completion() 是同步函数，内部按配置调用 OpenAI 兼容接口或 Anthropic 接口。
- ChatWorker 在 Qt 线程中调用 chat_completion()，用于 UI 不阻塞地接收回复。

内部消息格式尽量保持 OpenAI 风格；调用 Anthropic 时再转换 system、text、image_url。
"""

import asyncio

import httpx
from PySide6.QtCore import QThread, Signal

try:
    from openai import AsyncOpenAI, APIConnectionError as OpenAIConnectionError, APITimeoutError as OpenAITimeoutError
except Exception:
    AsyncOpenAI = None
    OpenAIConnectionError = Exception
    OpenAITimeoutError = TimeoutError

try:
    from anthropic import AsyncAnthropic, APIConnectionError as AnthropicConnectionError, APITimeoutError as AnthropicTimeoutError, APIStatusError as AnthropicStatusError
except Exception:
    AsyncAnthropic = None
    AnthropicConnectionError = Exception
    AnthropicTimeoutError = TimeoutError
    AnthropicStatusError = Exception

from miniPet import config

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


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



def _data_url_to_anthropic_source(url):
    """把 data:image/...;base64,... 转成 Anthropic 原生图片 source。"""
    if not isinstance(url, str) or not url.startswith('data:image/') or ',' not in url:
        return None
    header, data = url.split(',', 1)
    media_type = header.replace('data:', '').split(';', 1)[0]
    if ';base64' not in header or not media_type:
        return None
    return {'type': 'base64', 'media_type': media_type, 'data': data}


def _content_to_anthropic(content):
    """把 OpenAI 风格 content 转成 Anthropic messages.content。"""
    if isinstance(content, str):
        return content
    blocks = []
    for block in content or []:
        block_type = block.get('type')
        if block_type == 'text':
            text = block.get('text', '')
            if text:
                blocks.append({'type': 'text', 'text': text})
        elif block_type == 'image_url':
            image_url = block.get('image_url')
            if isinstance(image_url, str):
                url = image_url
            else:
                url = (image_url or {}).get('url', '')
            source = _data_url_to_anthropic_source(url)
            if source:
                blocks.append({'type': 'image', 'source': source})
            else:
                blocks.append({'type': 'text', 'text': '[用户发送了一张无法读取的图片]'})
    return blocks or ''


def _split_system(messages):
    """Anthropic API 单独接收 system 字段，所以这里把 system 消息拆出来。"""
    system_parts = []
    chat_messages = []
    for msg in messages:
        role = msg.get('role')
        content = msg.get('content', '')
        if role == 'system':
            if content:
                system_parts.append(str(content))
        else:
            chat_messages.append({'role': role, 'content': _content_to_anthropic(content)})
    return '\n\n'.join(system_parts), chat_messages


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


async def _call_anthropic(messages, cfg, timeout, on_delta=None):
    """调用 Anthropic Messages API，自动处理 system 和图片消息格式。"""
    if AsyncAnthropic is None:
        return False, '缺少 anthropic SDK，请执行：pip install anthropic httpx'
    api_base = (cfg.get('api_base') or '').rstrip('/') or None
    api_key = cfg.get('api_key') or ''
    model = cfg.get('model') or ''
    if not model:
        return False, '未配置模型名称。'
    if not api_key:
        return False, '未配置 API Key。'
    system, chat_messages = _split_system(messages)
    http_client = httpx.AsyncClient(headers={'User-Agent': USER_AGENT}, timeout=timeout)
    client = AsyncAnthropic(api_key=api_key, base_url=api_base, http_client=http_client, max_retries=1)
    try:
        kwargs = {'model': model, 'max_tokens': int(cfg.get('max_tokens') or 1024), 'messages': chat_messages}
        if system:
            kwargs['system'] = system
        if on_delta:
            chunks = []
            async with client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    if text:
                        chunks.append(text)
                        on_delta(text)
            return True, ''.join(chunks).strip()
        response = await client.messages.create(**kwargs)
        text = next((block.text for block in response.content if getattr(block, 'type', None) == 'text'), '')
        return True, text.strip()
    except AnthropicTimeoutError as e:
        return False, '网络超时：%s' % e
    except AnthropicConnectionError as e:
        return False, '网络错误：%s' % e
    except AnthropicStatusError as e:
        return False, '请求失败 (HTTP %s): %s' % (getattr(e, 'status_code', '?'), getattr(e, 'message', str(e)))
    except Exception as e:
        return False, '请求失败：%s' % e
    finally:
        await http_client.aclose()


async def _chat_async(messages, cfg, timeout, on_delta=None):
    provider = (cfg.get('provider') or 'openai').lower()
    if provider in ('anthropic', 'claude'):
        return await _call_anthropic(messages, cfg, timeout, on_delta)
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
