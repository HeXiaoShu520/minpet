# coding:utf-8
"""通知气泡使用的轻量文本格式化。"""

import re


def markdown_to_html(text):
    """支持通知气泡里常用的少量 Markdown，并先做 HTML 转义。"""
    if not text:
        return ''
    html = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    html = re.sub(r'```([^`]+)```', r'<pre style="background:#f5f5f5;padding:8px;border-radius:4px;margin:4px 0;">\1</pre>', html, flags=re.DOTALL)
    html = re.sub(r'`([^`]+)`', r'<code style="background:#f0f0f0;padding:2px 4px;border-radius:3px;">\1</code>', html)
    html = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', html)
    html = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', html)
    html = re.sub(r'\n\n+', '\n', html)
    return html.replace('\n', '<br>')
