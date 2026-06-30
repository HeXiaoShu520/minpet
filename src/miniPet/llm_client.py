# coding:utf-8
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
    if not isinstance(url, str) or not url.startswith('data:image/') or ',' not in url:
        return None
    header, data = url.split(',', 1)
    media_type = header.replace('data:', '').split(';', 1)[0]
    if ';base64' not in header or not media_type:
        return None
    return {'type': 'base64', 'media_type': media_type, 'data': data}


def _content_to_anthropic(content):
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
    delta_ready = Signal(str)
    result_ready = Signal(bool, str)

    def __init__(self, messages, cfg=None, parent=None):
        super().__init__(parent)
        self.messages = list(messages)
        self.cfg = dict(cfg) if cfg is not None else dict(config.llm_config)

    def run(self):
        self.result_ready.emit(*chat_completion(self.messages, self.cfg, on_delta=self.delta_ready.emit))
