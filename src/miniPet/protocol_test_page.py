# coding:utf-8
"""
协议测试页面 — miniPet V1 交互协议模拟触发工具

内嵌一个轻量 WebSocket 服务器（ws://127.0.0.1:18889/ws/minipet），
miniPet 连接到"通用 AI 后端"后，此页面可以直接向已连接的客户端
推送各类 V1 协议消息，方便观察宠物端的渲染效果。
"""

import asyncio
import json
import time
import uuid

import websockets
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    InfoBar, InfoBarPosition, LineEdit,
    PrimaryPushButton, PushButton, SettingCard, SettingCardGroup,
)
from qfluentwidgets import FluentIcon as FIF

from miniPet.base_page import MiniPetScrollPage


# ──────────────────────────────────────────────
#  内嵌 WS 服务器线程
# ──────────────────────────────────────────────

TEST_HOST = '127.0.0.1'
TEST_PORT = 18889


class _TestServer(QThread):
    """后台 asyncio WebSocket 服务器，最多保留一条活跃连接。"""
    client_connected = Signal(bool)
    message_received = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop = None
        self._ws = None
        self._running = False

    def send(self, payload: dict) -> bool:
        loop = self._loop
        ws = self._ws
        if loop is None or ws is None or not loop.is_running():
            return False
        try:
            asyncio.run_coroutine_threadsafe(self._async_send(ws, payload), loop)
            return True
        except Exception:
            return False

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def run(self):
        self._running = True
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception:
            pass
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None

    def stop(self):
        self._running = False
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        self.quit()
        self.wait(2000)

    async def _serve(self):
        async def handler(ws):
            self._ws = ws
            self.client_connected.emit(True)
            try:
                async for raw in ws:
                    if not self._running:
                        break
                    try:
                        self.message_received.emit(json.loads(raw))
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                if self._ws is ws:
                    self._ws = None
                self.client_connected.emit(False)

        async with websockets.serve(handler, TEST_HOST, TEST_PORT):
            while self._running:
                await asyncio.sleep(0.5)

    @staticmethod
    async def _async_send(ws, payload: dict):
        await ws.send(json.dumps(payload, ensure_ascii=False))


# ──────────────────────────────────────────────
#  消息构造
# ──────────────────────────────────────────────

def _msg(msg_type: str, payload: dict) -> dict:
    return {
        'version': '1.0',
        'id': 'test-' + uuid.uuid4().hex[:8],
        'type': msg_type,
        'source': 'protocol-tester',
        'timestamp': int(time.time() * 1000),
        'payload': payload,
    }


# 预设消息列表：(label, msg_type, payload)
PRESET_MESSAGES = [
    ('agent.state — working', 'agent.state', {
        'state': 'working',
        'text': '我正在整理今天需要你处理的事项。',
        'emotion': 'thinking',
        'progress': 0.35,
        'task': {'id': 'briefing-001', 'title': '整理今日待处理'},
    }),
    ('agent.state — idle', 'agent.state', {
        'state': 'idle',
        'text': '',
        'emotion': 'idle',
        'progress': None,
    }),
    ('agent.state — done', 'agent.state', {
        'state': 'done',
        'text': '已完成！',
        'emotion': 'happy',
        'progress': 1.0,
    }),
    ('agent.state — failed', 'agent.state', {
        'state': 'failed',
        'text': '出错了，请稍后再试。',
        'emotion': 'sad',
    }),
    ('surface.show — bubble', 'surface.show', {
        'surface_id': 'test-bubble-001',
        'kind': 'bubble',
        'content': '你好，我在这里！这是一条气泡测试消息。',
        'lifetime': {'ttl_ms': 5000},
    }),
    ('surface.show — card', 'surface.show', {
        'surface_id': 'test-card-001',
        'kind': 'card',
        'title': '今天需要处理的 4 件事',
        'content': '产品群 1 条消息需要回复；接口文档需要补充；昨天会议有 2 个待办。',
        'actions': [
            {'id': 'detail', 'label': '查看详情', 'style': 'primary', 'intent': 'open'},
            {'id': 'later',  'label': '稍后',     'style': 'quiet',   'intent': 'snooze'},
        ],
    }),
    ('surface.show — confirm', 'surface.show', {
        'surface_id': 'test-confirm-001',
        'kind': 'confirm',
        'title': '确认发送？',
        'content': '可以，我四点前发初版。',
        'risk': 'medium',
        'actions': [
            {'id': 'confirm', 'label': '发送',  'style': 'primary', 'intent': 'confirm'},
            {'id': 'edit',    'label': '修改',                       'intent': 'edit'},
            {'id': 'cancel',  'label': '取消',  'style': 'quiet',   'intent': 'cancel'},
        ],
        'metadata': {'draft_id': 'draft-test-001'},
    }),
    ('surface.show — input', 'surface.show', {
        'surface_id': 'test-input-001',
        'kind': 'input',
        'title': '修改回复内容',
        'input': {
            'type': 'text',
            'placeholder': '请输入回复内容',
            'default_value': '可以，我四点前发初版。',
        },
        'actions': [
            {'id': 'submit', 'label': '继续', 'style': 'primary'},
            {'id': 'cancel', 'label': '取消', 'style': 'quiet'},
        ],
        'metadata': {'draft_id': 'draft-test-001'},
    }),
    ('surface.show — choice', 'surface.show', {
        'surface_id': 'test-choice-001',
        'kind': 'choice',
        'title': '选择会议时间',
        'content': '我找到 3 个大家都有空的时间。',
        'input': {
            'type': 'choice',
            'multi': False,
            'options': [
                {'id': 't1', 'label': '明天 14:00 - 14:30'},
                {'id': 't2', 'label': '明天 15:30 - 16:00'},
                {'id': 't3', 'label': '后天 10:00 - 10:30'},
            ],
        },
        'actions': [
            {'id': 'submit', 'label': '确定', 'style': 'primary'},
            {'id': 'cancel', 'label': '取消', 'style': 'quiet'},
        ],
    }),
    ('surface.update — card', 'surface.update', {
        'surface_id': 'test-card-001',
        'title': '已更新内容',
        'content': '这是 surface.update 更新后的新内容。',
    }),
    ('surface.close — card', 'surface.close', {
        'surface_id': 'test-card-001',
        'reason': 'completed',
    }),
    ('session.ping', 'session.ping', {
        'ts': 0,
    }),
]


# ──────────────────────────────────────────────
#  编辑弹窗
# ──────────────────────────────────────────────

class _EditDialog(QDialog):
    """编辑单条测试消息的标签名和 payload JSON。"""

    def __init__(self, label: str, msg_type: str, payload: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle('编辑测试消息')
        self.setMinimumWidth(520)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        # 标签名
        root.addWidget(QLabel('按钮标签名'))
        self.label_edit = LineEdit(self)
        self.label_edit.setText(label)
        self.label_edit.setClearButtonEnabled(True)
        root.addWidget(self.label_edit)

        # 消息类型（只读，不允许改，避免混乱）
        root.addWidget(QLabel('消息类型（只读）'))
        type_edit = LineEdit(self)
        type_edit.setText(msg_type)
        type_edit.setReadOnly(True)
        type_edit.setStyleSheet('QLineEdit{color:#888;}')
        root.addWidget(type_edit)

        # payload JSON
        root.addWidget(QLabel('Payload JSON'))
        self.payload_edit = QPlainTextEdit(self)
        self.payload_edit.setFixedHeight(260)
        self.payload_edit.setPlainText(
            json.dumps(payload, ensure_ascii=False, indent=2)
        )
        self.payload_edit.setStyleSheet(
            'QPlainTextEdit{font-family:"Consolas","Courier New",monospace;font-size:13px;}'
        )
        root.addWidget(self.payload_edit)

        # 错误提示
        self._err_label = QLabel('', self)
        self._err_label.setStyleSheet('QLabel{color:#e05252;}')
        self._err_label.hide()
        root.addWidget(self._err_label)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.cancel_btn = PushButton('取消', self)
        self.save_btn = PrimaryPushButton('保存', self)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)

        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self._on_save)

    def _on_save(self):
        text = self.payload_edit.toPlainText().strip()
        try:
            json.loads(text)
        except json.JSONDecodeError as e:
            self._err_label.setText('JSON 格式错误：' + str(e))
            self._err_label.show()
            return
        self._err_label.hide()
        self.accept()

    def result_label(self) -> str:
        return self.label_edit.text().strip()

    def result_payload(self) -> dict:
        return json.loads(self.payload_edit.toPlainText().strip())


# ──────────────────────────────────────────────
#  卡片（含发送 + 编辑按钮）
# ──────────────────────────────────────────────

class _SendCard(SettingCard):
    """带"发送"和"编辑"按钮的测试卡片，标签名和 payload 均可在运行时修改。"""

    send_clicked = Signal()
    edit_clicked = Signal()

    def __init__(self, label: str, msg_type: str, parent=None):
        super().__init__(FIF.SEND, label, msg_type, parent)
        self.hBoxLayout.addStretch(1)

        self._edit_btn = PushButton('编辑', self)
        self._send_btn = PrimaryPushButton('发送', self)

        self.hBoxLayout.addWidget(self._edit_btn, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self._send_btn, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self._send_btn.clicked.connect(self.send_clicked)
        self._edit_btn.clicked.connect(self.edit_clicked)

    def set_label(self, text: str):
        self.titleLabel.setText(text)


# ──────────────────────────────────────────────
#  页面主体
# ──────────────────────────────────────────────

class ProtocolTestPage(MiniPetScrollPage):
    """
    协议测试页面

    使用前先在"智能体"页将后端切换为"通用 AI 后端"，
    地址填 ws://127.0.0.1:18889/ws/minipet，保存后 miniPet 会自动连上。
    """

    def __init__(self, parent=None):
        super().__init__('协议测试', parent)

        self._server = _TestServer(self)
        self._server.client_connected.connect(self._on_client_connected)
        self._server.start()

        # 运行时数据：[(card, msg_type, payload_dict)]
        self._entries: list[tuple[_SendCard, str, dict]] = []

        # ── 状态栏 ───────────────────────────────
        self.statusGroup = SettingCardGroup('服务器状态', self.scrollWidget)
        self.statusCard = SettingCard(
            FIF.WIFI,
            '测试服务器',
            'ws://127.0.0.1:18889/ws/minipet — 等待客户端连接…',
            self.statusGroup,
        )
        self._restart_btn = PushButton('重启服务器', self.statusCard)
        self.statusCard.hBoxLayout.addStretch(1)
        self.statusCard.hBoxLayout.addWidget(self._restart_btn, 0, Qt.AlignRight)
        self.statusCard.hBoxLayout.addSpacing(16)
        self._restart_btn.clicked.connect(self._restart_server)
        self.statusGroup.addSettingCard(self.statusCard)
        self.expandLayout.addWidget(self.statusGroup)

        # ── 消息测试组 ───────────────────────────
        self.testGroup = SettingCardGroup('发送测试消息', self.scrollWidget)

        for label, msg_type, payload in PRESET_MESSAGES:
            self._add_entry(label, msg_type, dict(payload))

        self.expandLayout.addWidget(self.testGroup)

        # ── 使用说明 ─────────────────────────────
        self.hintGroup = SettingCardGroup('使用说明', self.scrollWidget)
        self.hintCard = SettingCard(
            FIF.INFO,
            '使用步骤',
            (
                '① 在"智能体"页将后端切换为"通用 AI 后端"，'
                '地址填 ws://127.0.0.1:18889/ws/minipet，保存。'
                '  ② 等待上方状态变为"已连接"。'
                '  ③ 点"发送"触发消息；点"编辑"可修改按钮标签和 payload。'
            ),
            self.hintGroup,
        )
        self.hintGroup.addSettingCard(self.hintCard)
        self.expandLayout.addWidget(self.hintGroup)

    # ── 内部方法 ─────────────────────────────────

    def _add_entry(self, label: str, msg_type: str, payload: dict):
        card = _SendCard(label, msg_type, self.testGroup)
        self.testGroup.addSettingCard(card)
        idx = len(self._entries)
        self._entries.append((card, msg_type, payload))

        card.send_clicked.connect(lambda _i=idx: self._on_send(_i))
        card.edit_clicked.connect(lambda _i=idx: self._on_edit(_i))

    def _on_send(self, idx: int):
        card, msg_type, payload = self._entries[idx]
        if not self._server.connected:
            InfoBar.warning(
                '未连接',
                '还没有客户端连接到测试服务器',
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
            return
        p = dict(payload)
        if msg_type == 'session.ping':
            p['ts'] = int(time.time() * 1000)
        ok = self._server.send(_msg(msg_type, p))
        if ok:
            InfoBar.success(
                '已发送',
                msg_type,
                duration=1500,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
        else:
            InfoBar.error(
                '发送失败',
                '消息未能送达，请检查连接',
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )

    def _on_edit(self, idx: int):
        card, msg_type, payload = self._entries[idx]
        dlg = _EditDialog(card.titleLabel.text(), msg_type, payload, self.window())
        if dlg.exec() != QDialog.Accepted:
            return
        new_label = dlg.result_label() or card.titleLabel.text()
        new_payload = dlg.result_payload()
        card.set_label(new_label)
        self._entries[idx] = (card, msg_type, new_payload)

    def _on_client_connected(self, connected: bool):
        if connected:
            self.statusCard.setContent(
                'ws://127.0.0.1:18889/ws/minipet — ✅ 客户端已连接'
            )
            InfoBar.success(
                '客户端已连接',
                'miniPet 已连上测试服务器，可以开始发送消息了',
                duration=3000,
                position=InfoBarPosition.BOTTOM,
                parent=self.window(),
            )
        else:
            self.statusCard.setContent(
                'ws://127.0.0.1:18889/ws/minipet — 等待客户端连接…'
            )

    def _restart_server(self):
        self._server.stop()
        self._server = _TestServer(self)
        self._server.client_connected.connect(self._on_client_connected)
        self._server.start()
        self.statusCard.setContent(
            'ws://127.0.0.1:18889/ws/minipet — 等待客户端连接…'
        )
        InfoBar.info(
            '已重启',
            '测试服务器已重启',
            duration=2000,
            position=InfoBarPosition.BOTTOM,
            parent=self.window(),
        )

    def closeEvent(self, event):
        self._server.stop()
        super().closeEvent(event)
