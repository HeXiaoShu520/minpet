# coding:utf-8
"""
文本聊天窗口。

聊天内容由 res/chat/chat.html 渲染，Python 侧负责：
- 收集输入文本和粘贴/拖入图片。
- 通过 ChatWorker 调用 LLM，并把流式增量推给 WebEngine。
- 按配置触发 TTS 播放。
- 与 ChatStore/MiniPetApp 共享历史消息。
"""

import json
import uuid

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QFont, QIcon, QKeyEvent, QPixmap
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget)
from qfluentwidgets import TitleLabel, TransparentToolButton
from qframelesswindow import FramelessWindow, StandardTitleBar
from qfluentwidgets import FluentIcon as FIF

import config
from clients.llm_client import ChatWorker
from clients.stream_tts import StreamTtsQueue
from clients.tts_client import stop_tts
from widgets.notifications.reply_card import SourceChipWidget

try:
    from PySide6.QtTextEdit import QTextEdit
except ImportError:
    from PySide6.QtWidgets import QTextEdit


class ChatInput(QTextEdit):
    """支持回车发送、Shift+Enter 换行、粘贴/拖入图片的输入框。"""

    image_pasted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAcceptRichText(False)
        self.setPlaceholderText('发送给宠物')
        self.setCursor(Qt.IBeamCursor)
        self.viewport().setCursor(Qt.IBeamCursor)
        self.setMinimumHeight(38)
        self.setMaximumHeight(120)
        self.document().setDocumentMargin(0)
        self.textChanged.connect(self._resize_to_content)
        self._resize_to_content()

    def _image_to_data_url(self, image):
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, 'PNG')
        return 'data:image/png;base64,' + bytes(data.toBase64()).decode('ascii')

    def insertFromMimeData(self, source):
        if source.hasImage():
            self.image_pasted.emit(self._image_to_data_url(source.imageData()))
            return
        super().insertFromMimeData(source)

    def dragEnterEvent(self, event):
        if event.mimeData().hasImage() or event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasImage():
            self.image_pasted.emit(self._image_to_data_url(mime.imageData()))
            event.acceptProposedAction()
            return
        for url in mime.urls():
            path = url.toLocalFile()
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.image_pasted.emit(self._image_to_data_url(pixmap.toImage()))
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            self.window()._send()
            event.accept()
            return
        super().keyPressEvent(event)

    def _resize_to_content(self):
        if not self.toPlainText().strip():
            self.setFixedHeight(38)
            return
        doc_height = int(self.document().size().height()) + 20
        self.setFixedHeight(max(38, min(120, doc_height)))


def _scaled_pixmap(pixmap, w, h, mode=Qt.KeepAspectRatio):
    """按屏幕 DPI 缩放，保证高清显示。"""
    screen = QApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0
    pw, ph = int(w * dpr), int(h * dpr)
    pm = pixmap.scaled(pw, ph, mode, Qt.SmoothTransformation)
    pm.setDevicePixelRatio(dpr)
    return pm


class Avatar(QLabel):
    """聊天消息头像，图片加载失败时回退为单字文本。"""

    def __init__(self, pixmap_path, fallback_text, is_user=False, parent=None, size=38, icon_size=30):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(pixmap_path)) if pixmap_path else QPixmap()
        if not pixmap.isNull():
            self.setPixmap(_scaled_pixmap(pixmap, icon_size, icon_size))
        else:
            self.setText(fallback_text[:1])
        bg = '#dbeafe' if is_user else '#fff1e8'
        fg = '#1d4ed8' if is_user else '#c2410c'
        self.setStyleSheet(
            'QLabel{background:%s;color:%s;border-radius:%dpx;font-weight:600;}' % (bg, fg, size // 2)
        )


class ChatBridge(QWebChannel):
    """QWebChannel 桥：把消息推给 JS，接收 JS 的卡片按钮回调。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._card_callback = None
        self._quote_callback = None
        self.registerObject('bridge', self)

    def set_card_callback(self, cb):
        self._card_callback = cb

    def set_quote_callback(self, cb):
        self._quote_callback = cb

    # JS 可调用的槽
    from PySide6.QtCore import Slot
    @Slot(str)
    def cardAction(self, value):
        if self._card_callback:
            self._card_callback(value)

    @Slot(str)
    def imagePasted(self, data_url):
        pass  # 留给扩展用

    @Slot(str)
    def quoteActivated(self, quoted_text):
        if self._quote_callback:
            self._quote_callback(quoted_text)


class ChatWindow(FramelessWindow):
    """完整文本聊天窗口。

    这个窗口把 Qt 输入区和 WebEngine 消息区组合在一起。history 由外层
    MiniPetApp 传入时，窗口只负责展示和提交消息；没有外部 append_message 时
    则在本地列表里维护临时历史，便于独立测试。
    """

    def __init__(self, pet_name='', parent=None, history=None, append_message=None, content_for_llm=None, system_prompt_builder=None, clear_history_callback=None, send_callback=None, backend='builtin'):
        super().__init__(parent)
        self.pet_name = pet_name
        self.history = history if history is not None else []
        self.append_message = append_message
        self.content_for_llm = content_for_llm
        self.system_prompt_builder = system_prompt_builder
        self.clear_history_callback = clear_history_callback
        self.send_callback = send_callback
        self.backend = backend or 'builtin'
        self.worker = None
        self._stream_id = None
        self._stream_text = ''
        self.stream_tts = StreamTtsQueue(self, label='Chat TTS')
        self.pending_images = []
        self._web_ready = False
        self._pending_js = []
        self.setWindowTitle('与宠物聊天')
        self.setWindowIcon(QIcon(str(config.avatar_path('pet'))))
        self.setTitleBar(StandardTitleBar(self))
        self.titleBar.setStyleSheet('StandardTitleBar{background:#ffffff;border-bottom:1px solid #e5e7eb;}')
        self.resize(720, 620)
        self.setMinimumSize(QSize(520, 460))
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, self.titleBar.height(), 0, 0)
        root.setSpacing(0)
        self.setStyleSheet('QWidget{font-family:Microsoft YaHei, Segoe UI, sans-serif;}')

        header = QWidget()
        header.setFixedHeight(54)
        header.setStyleSheet('QWidget{background:#ffffff;border-bottom:1px solid #e5e7eb;}')
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 0, 12, 0)
        self.avatar_widget = Avatar(config.avatar_path('pet'), self.pet_name or '宠', False, header, size=34, icon_size=27)
        title_box = QHBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(8)
        self.title_label = TitleLabel(self.pet_name or '宠物')
        self.title_label.setFont(QFont(self.title_label.font().family(), 13, QFont.DemiBold))
        self.backend_badge = None
        self._title_box = title_box
        title_box.addWidget(self.title_label)
        self.set_backend(self.backend)
        h_layout.addWidget(self.avatar_widget)
        h_layout.addLayout(title_box)
        h_layout.addStretch(1)
        clear_btn = TransparentToolButton(FIF.DELETE, header)
        clear_btn.setToolTip('清空对话')
        clear_btn.clicked.connect(self._clear)
        h_layout.addWidget(clear_btn)
        root.addWidget(header)

        # WebEngine 消息区
        self.web = QWebEngineView()
        from PySide6.QtWebEngineCore import QWebEngineSettings
        settings = self.web.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.bridge = ChatBridge(self)
        self.web.page().setWebChannel(self.bridge)
        self.web.loadFinished.connect(self._on_load_finished)
        html_path = config.RES_DIR / 'chat' / 'chat.html'
        html_text = html_path.read_text(encoding='utf-8')
        base_url = QUrl.fromLocalFile(str(html_path))
        self.web.setHtml(html_text, base_url)
        root.addWidget(self.web, 1)

        # 输入区
        input_bar = QWidget()
        input_bar.setStyleSheet('QWidget{background:#f7f8fa;}')
        input_layout = QVBoxLayout(input_bar)
        input_layout.setContentsMargins(18, 8, 18, 12)
        input_layout.setSpacing(4)
        self.preview_row = QHBoxLayout()
        self.preview_row.setContentsMargins(0, 0, 0, 0)
        self.preview_row.setSpacing(6)
        input_layout.addLayout(self.preview_row)

        # 引用预览栏（默认隐藏）
        self.quote_bar = QWidget(input_bar)
        self.quote_bar.setVisible(False)
        self.quote_bar.setStyleSheet(
            'QWidget{background:#eef4ff;border-left:3px solid #4080ff;border-radius:6px;padding:0px;}'
        )
        quote_bar_layout = QHBoxLayout(self.quote_bar)
        quote_bar_layout.setContentsMargins(10, 4, 6, 4)
        quote_bar_layout.setSpacing(6)
        self.quote_label = QLabel('', self.quote_bar)
        self.quote_label.setStyleSheet(
            'QLabel{color:#4060cc;font-size:12px;background:transparent;border:none;border-left:none;}'
        )
        self.quote_label.setWordWrap(False)
        from PySide6.QtWidgets import QPushButton as _QPushButton
        quote_close_btn = _QPushButton('×', self.quote_bar)
        quote_close_btn.setFixedSize(20, 20)
        quote_close_btn.setStyleSheet(
            'QPushButton{background:transparent;border:none;color:#8090bb;font-size:14px;}'
            'QPushButton:hover{color:#1677ff;}'
        )
        quote_close_btn.clicked.connect(self._clear_quote)
        quote_bar_layout.addWidget(self.quote_label, 1)
        quote_bar_layout.addWidget(quote_close_btn, 0)
        input_layout.addWidget(self.quote_bar)
        self._quoted_text = ''
        self.bridge.set_quote_callback(self._on_quote_activated)

        self.input = ChatInput(input_bar)
        self.input.image_pasted.connect(self._add_pending_image)
        self.input.setStyleSheet(
            'QTextEdit{background:#ffffff;border:1px solid #dfe3e8;border-radius:10px;padding:8px 12px;font-size:14px;}'
            'QTextEdit:focus{border:1px solid #8ab4f8;}'
        )
        input_layout.addWidget(self.input)
        root.addWidget(input_bar)

    # ─── WebEngine 就绪后批量执行待办 JS ───

    def _on_load_finished(self, ok):
        if not ok:
            return
        self._web_ready = True
        self.reload_history()
        for js in self._pending_js:
            self.web.page().runJavaScript(js)
        self._pending_js.clear()

    def set_pet_name(self, pet_name):
        self.pet_name = pet_name or '宠物'
        if hasattr(self, 'title_label'):
            self.title_label.setText(self.pet_name)

    def set_backend(self, backend):
        self.backend = backend or 'builtin'
        _BACKEND_LABEL = {
            'builtin':    '内置AI',
            'claude_code':'Claude',
            'openclaw':   'OpenClaw',
            'custom':     'MiniPet',
        }
        if not hasattr(self, '_title_box'):
            return
        if self.backend_badge is not None:
            self.backend_badge.setParent(None)
            self.backend_badge.deleteLater()
            self.backend_badge = None
        text = _BACKEND_LABEL.get(self.backend, self.backend)
        chip = SourceChipWidget(text)
        f = chip.font()
        f.setPointSize(9)
        f.setBold(True)
        chip.setFont(f)
        self.backend_badge = chip
        self._title_box.addWidget(chip, 0, Qt.AlignVCenter)

    def _on_quote_activated(self, quoted_text):
        self._quoted_text = quoted_text.strip()
        if self._quoted_text:
            summary = self._quoted_text[:80] + ('...' if len(self._quoted_text) > 80 else '')
            self.quote_label.setText('引用：' + summary)
            self.quote_bar.setVisible(True)
            self.input.setFocus()

    def _clear_quote(self):
        self._quoted_text = ''
        self.quote_bar.setVisible(False)
        self.quote_label.setText('')
        self._js('Chat.clearQuote()')

    def _js(self, code):
        if self._web_ready:
            self.web.page().runJavaScript(code)
        else:
            self._pending_js.append(code)

    # ─── 消息构建工具 ───

    def _backend_label(self, backend):
        labels = {
            'builtin': '内置模型', 'custom': '自定义智能体', 'openclaw': 'OpenClaw',
            'claude_code': 'Claude Code',
        }
        return labels.get(backend or 'builtin', backend or 'builtin')

    def _msg_dict(self, role, content, msg_id=None, backend=None):
        """把 str 或 blocks list 转成 chat.js 需要的 msg dict。"""
        avatar_url = QUrl.fromLocalFile(str(config.avatar_path('user' if role == 'user' else 'pet'))).toString()
        name = '我' if role == 'user' else (self.pet_name or '宠物')
        blocks = self._normalize_blocks(content)
        return {
            'id': msg_id or str(uuid.uuid4()),
            'role': role,
            'name': name,
            'backend': '' if role == 'user' else self._backend_label(backend or self.backend),
            'avatar': avatar_url,
            'content': blocks,
        }

    def _normalize_blocks(self, content):
        if isinstance(content, str):
            return [{'type': 'text', 'text': content}]
        if isinstance(content, list):
            blocks = []
            for b in content:
                t = b.get('type') or b.get('tag')
                if t == 'text':
                    blk = {'type': 'text', 'text': b.get('text', '')}
                    if b.get('quote'):
                        blk['quote'] = b['quote']
                    blocks.append(blk)
                elif t == 'image':
                    src = b.get('src') or b.get('path') or b.get('image_key') or ''
                    blocks.append({'type': 'image', 'src': src, 'alt': b.get('alt', '图片')})
                elif t == 'code':
                    blocks.append({'type': 'code', 'language': b.get('language', ''), 'text': b.get('text', '')})
                elif t == 'card':
                    blocks.append(b)
            return blocks or [{'type': 'text', 'text': ''}]
        return [{'type': 'text', 'text': str(content)}]

    # ─── 消息区操作 ───

    def _push_message(self, role, content, msg_id=None):
        msg = self._msg_dict(role, content, msg_id)
        self._js('Chat.appendMessage(%s)' % json.dumps(msg, ensure_ascii=False))

    def _start_stream(self, msg_id):
        self._stream_id = msg_id
        self._stream_text = ''
        avatar_url = QUrl.fromLocalFile(str(config.avatar_path('pet'))).toString()
        self._js('Chat.startStream(%s)' % json.dumps({
            'id': msg_id,
            'role': 'assistant',
            'name': self.pet_name or '宠物',
            'backend': self.backend_badge.text() if self.backend_badge is not None else '',
            'avatar': avatar_url,
        }, ensure_ascii=False))

    def reload_history(self):
        self._js('Chat.clear()')
        if not self.history:
            self._push_message('assistant', '主人好呀，想聊点什么？')
            return
        for msg in self.history:
            role = msg.get('role')
            if role in ('user', 'assistant'):
                self._js('Chat.appendMessage(%s)' % json.dumps(
                    self._msg_dict(role, msg.get('content', ''), backend=msg.get('backend')),
                    ensure_ascii=False,
                ))

    # ─── 输入区 ───

    def _add_pending_image(self, data_url):
        self.pending_images.append(data_url)
        import base64
        from PySide6.QtGui import QImage
        img = QImage()
        img.loadFromData(base64.b64decode(data_url.split(',', 1)[1]))
        thumb = QLabel(self.input.parent())  # 必须有 parent，否则浮成顶层窗口
        thumb.setFixedSize(48, 48)
        thumb.setStyleSheet('QLabel{border:1px solid #dfe3e8;border-radius:6px;background:#f0f0f0;}')
        thumb.setPixmap(QPixmap.fromImage(img).scaled(46, 46, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.preview_row.addWidget(thumb)

    def _build_user_content(self, text, quote=''):
        if not self.pending_images and not quote:
            return text
        blocks = []
        if text:
            block = {'type': 'text', 'text': text}
            if quote:
                block['quote'] = quote[:80] + ('...' if len(quote) > 80 else '')
            blocks.append(block)
        for img in self.pending_images:
            blocks.append({'type': 'image', 'src': img, 'alt': '图片'})
        return blocks or text

    def _send(self):
        """发送用户输入，启动一条流式 assistant 消息。"""
        text = self.input.toPlainText().strip()
        if (not text and not self.pending_images) or self.worker is not None:
            return
        quoted = self._quoted_text
        # 发给 LLM 的文本（拼接格式，保持 AI 理解上下文）
        if quoted and text:
            summary = quoted[:60] + ('...' if len(quoted) > 60 else '')
            send_text = '对方引用了"%s"，他的输入是：%s' % (summary, text)
        else:
            send_text = text
        content = self._build_user_content(send_text, quote=quoted if quoted and text else '')
        self._clear_quote()
        self.input.clear()
        self.pending_images = []
        while self.preview_row.count():
            w = self.preview_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.input.setPlaceholderText('发送给宠物')
        # 开始流式回复卡片
        stream_id = str(uuid.uuid4())
        self._reset_stream_tts()
        self.input.setEnabled(False)
        if self.send_callback:
            self.worker = self.send_callback(
                content,
                lambda backend: self._show_sent_user_then_stream(content, backend, stream_id),
                lambda d: self._on_delta(stream_id, d),
                lambda ok, t: self._on_reply(stream_id, ok, t),
            )
            if not self.worker:
                self._on_reply(stream_id, False, '当前后端发送失败。')
            return
        self._save_sent_user(content, self.backend)
        self._start_stream(stream_id)
        self.worker = ChatWorker(self._build_messages(), parent=self)
        self.worker.delta_ready.connect(lambda d: self._on_delta(stream_id, d))
        self.worker.result_ready.connect(lambda ok, t: self._on_reply(stream_id, ok, t))
        self.worker.start()

    def _show_sent_user_then_stream(self, content, backend, stream_id):
        self.backend = backend or self.backend
        self._stream_backend = self.backend
        self._push_message('user', content)
        self._start_stream(stream_id)

    def _show_sent_user(self, content, backend):
        self.backend = backend or self.backend
        self._stream_backend = self.backend
        self._push_message('user', content)

    def _save_sent_user(self, content, backend):
        self.backend = backend or self.backend
        self._stream_backend = self.backend
        message = self.append_message('user', content, 'chat_window', self.backend) if self.append_message else {'role': 'user', 'content': content, 'backend': self.backend}
        if self.append_message is None:
            self.history.append(message)
        self._push_message('user', message.get('content', content))

    def _memory_message_limit(self):
        return max(0, int(config.llm_config.get('memory_turns') or 0)) * 2

    def _build_messages(self):
        """构造发给 LLM 的上下文，保留配置的最近 N 轮聊天记录。"""
        messages = []
        system = self.system_prompt_builder() if self.system_prompt_builder else ''
        if not system:
            system = (config.llm_config.get('system_prompt', '') or '').strip()
        if system:
            messages.append({'role': 'system', 'content': system})
        memory_limit = self._memory_message_limit()
        for msg in (self.history[-memory_limit:] if memory_limit > 0 else []):
            content = msg.get('content', '')
            if self.content_for_llm:
                content = self.content_for_llm(content)
            messages.append({'role': msg.get('role'), 'content': content})
        return messages

    def _on_delta(self, stream_id, text):
        if text:
            self._stream_text += text
            escaped = json.dumps(text, ensure_ascii=False)
            self._js('Chat.appendDelta(%s, %s)' % (json.dumps(stream_id), escaped))
            self.stream_tts.queue_text(stream_id, self._stream_text.strip(), terminal=False)

    def _on_reply(self, stream_id, success, text):
        self.input.setEnabled(True)
        self.worker = None
        if success:
            final = text.strip() or '嗯。'
            self._js('Chat.endStream(%s, %s)' % (json.dumps(stream_id), json.dumps(final, ensure_ascii=False)))
            if self.append_message:
                self.append_message('assistant', final, 'chat_window', getattr(self, '_stream_backend', self.backend))
            else:
                self.history.append({'role': 'assistant', 'content': final})
            self._stream_text = final
            self.stream_tts.queue_text(stream_id, final, terminal=True)
        else:
            self._reset_stream_tts()
            self._js('Chat.endStream(%s, %s)' % (json.dumps(stream_id), json.dumps('⚠️ ' + text[:200], ensure_ascii=False)))
        self.input.setFocus()

    def _reset_stream_tts(self):
        self.stream_tts.reset()

    def clear_history(self, show_hint=False):
        stop_tts()
        self._reset_stream_tts()
        if self.clear_history_callback:
            self.clear_history_callback()
        else:
            self.history.clear()
        self._js('Chat.clear()')
        if show_hint:
            self._push_message('assistant', '对话已清空，重新开始吧。')

    def _clear(self):
        self.clear_history(show_hint=True)

    def _fit_to_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = min(max(self.x(), area.left()), area.right() - self.width() + 1)
        y = min(max(self.y(), area.top()), area.bottom() - self.height() + 1)
        self.move(x, y)

    def shutdown(self):
        stop_tts()
        self._reset_stream_tts()
        for attr in ('worker',):
            w = getattr(self, attr, None)
            if w is not None and w.isRunning():
                w.requestInterruption()
                w.quit()
                w.wait(2000)
            setattr(self, attr, None)

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def show_window(self):
        if not self.isVisible():
            self.show()
        self._fit_to_screen()
        self.activateWindow()
        self.raise_()
        self.input.setFocus()
