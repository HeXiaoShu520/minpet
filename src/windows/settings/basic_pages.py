# coding:utf-8
"""基础和智能体设置页面。"""

import shutil
import subprocess
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import InfoBar, InfoBarPosition, PrimaryPushButton, PushSettingCard, SettingCard, SettingCardGroup, SwitchSettingCard
from qfluentwidgets import FluentIcon as FIF

import config
from base_page import MiniPetScrollPage
from clients.event_client import probe_minipet_backend
from clients.llm_client import ChatWorker
from clients.openclaw_client import probe_openclaw_gateway
from widgets.setting_cards import ComboSettingCard, LineEditSettingCard, RangeSettingCard


REPLY_CARD_STYLE_OPTIONS = [
    ('aurora', '极光渐变'),
    ('glass', '玻璃拟态'),
    ('cream', '奶油暖色'),
    ('mint', '清新薄荷'),
    ('dark', '深色半透'),
]

VOICE_ORB_STYLE_OPTIONS = [
    ('jade', '温润玉石'),
    ('mint', '薄荷蓝绿'),
    ('violet', '紫罗兰'),
    ('sakura', '樱花粉'),
    ('sunset', '日落橙'),
    ('mono', '极简灰'),
]

VOICE_FOLLOW_EFFECT_OPTIONS = [
    ('spring', '弹力绳'),
    ('magnet', '丝滑吸附'),
]

STYLE_PREVIEW_QSS = {
    'reply': {
        'aurora': 'background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #fffdfa,stop:0.55 #f7fbff,stop:1 #f6f1ff);border:1px solid #e4d7ff;border-radius:12px;',
        'glass': 'background:rgba(255,255,255,0.72);border:1px solid rgba(255,255,255,0.85);border-radius:12px;',
        'cream': 'background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #fffaf0,stop:1 #fff2dc);border:1px solid #f5d2a0;border-radius:12px;',
        'mint': 'background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #f4fffb,stop:1 #e9fff7);border:1px solid #96e1d2;border-radius:12px;',
        'dark': 'background:#242a3a;border:1px solid #5a6991;border-radius:12px;',
    },
    'voice': {
        'jade': 'background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #f6fff9,stop:0.55 #dff7ec,stop:1 #c8eadc);border:1px solid #8bcdb4;border-radius:14px;',
        'mint': 'background:#f5f3ff;border:1px solid #a89eff;border-radius:14px;',
        'violet': 'background:#f8f4ff;border:1px solid #b796ff;border-radius:14px;',
        'sakura': 'background:#fff6fa;border:1px solid #ffaacd;border-radius:14px;',
        'sunset': 'background:#fff9f0;border:1px solid #ffb969;border-radius:14px;',
        'mono': 'background:#f6f7f9;border:1px solid #b9c0cd;border-radius:14px;',
    },
}


def _attach_style_preview(card, kind):
    preview = QLabel(card)
    preview.setFixedSize(92, 32)
    preview.setAlignment(Qt.AlignCenter)
    preview.setToolTip('当前样式预览')

    def update_preview(value=None):
        value = value or card.currentValue()
        qss = STYLE_PREVIEW_QSS.get(kind, {}).get(value, '')
        color = '#f4f6fb' if value == 'dark' else '#263238'
        text = '回复' if kind == 'reply' else '● 语音'
        preview.setText(text)
        preview.setStyleSheet('QLabel{%s color:%s; font:12px "Microsoft YaHei UI"; font-weight:600;}' % (qss, color))

    update_preview()
    card.comboBox.currentIndexChanged.connect(lambda _index: update_preview())
    card.hBoxLayout.insertWidget(card.hBoxLayout.count() - 2, preview, 0, Qt.AlignRight)
    return preview


class BasicPage(MiniPetScrollPage):
    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__('基础设置', parent, save_callback=lambda: self._save())
        typewriter_cfg = config.typewriter_config
        typewriter_defaults = config.DEFAULT_TYPEWRITER_CONFIG

        self.visualGroup = SettingCardGroup('视觉样式', self.scrollWidget)
        self.replyCardStyleCard = ComboSettingCard(REPLY_CARD_STYLE_OPTIONS, FIF.MESSAGE, '回复卡片样式', '选择 AI 回复、本地提示和协议卡片的视觉风格', self.visualGroup)
        self.replyCardStyleCard.setCurrentValue(config.app_config.get('reply_card_style', 'aurora'))
        _attach_style_preview(self.replyCardStyleCard, 'reply')
        self.voiceOrbStyleCard = ComboSettingCard(VOICE_ORB_STYLE_OPTIONS, FIF.VOLUME, '语音球样式', '选择语音悬浮球的颜色风格', self.visualGroup)
        self.voiceOrbStyleCard.setCurrentValue(config.app_config.get('voice_orb_style', 'jade'))
        _attach_style_preview(self.voiceOrbStyleCard, 'voice')
        self.voiceFollowEffectCard = ComboSettingCard(VOICE_FOLLOW_EFFECT_OPTIONS, FIF.SPEED_HIGH, '语音球跟随效果', '弹力绳有惯性过冲；丝滑吸附更稳、更少跳变', self.visualGroup)
        self.voiceFollowEffectCard.setCurrentValue(config.app_config.get('voice_follow_effect', 'spring'))

        self.replyDisplayGroup = SettingCardGroup('回复设置', self.scrollWidget)
        self.typewriterEnabledCard = SwitchSettingCard(FIF.MESSAGE, '打印字效果', '开启后，回复文字会一字一字显示；关闭后直接显示完整回复', parent=self.replyDisplayGroup)
        self.typewriterEnabledCard.setChecked(bool(typewriter_cfg.get('enabled', typewriter_defaults['enabled'])))
        self.typewriterSpeedCard = RangeSettingCard(8, 120, 1, FIF.MESSAGE, '打印字速度', '每个字的最大显示间隔，单位毫秒，数值越小越快', self.replyDisplayGroup)
        self.typewriterSpeedCard.setValue(int(typewriter_cfg.get('speed_ms', typewriter_defaults['speed_ms'])))
        self.typewriterMaxDurationCard = RangeSettingCard(500, 15000, 1, FIF.FONT_SIZE, '最长显示时长', '单条回复打印字效果的最长时间，单位毫秒', self.replyDisplayGroup)
        self.typewriterMaxDurationCard.setValue(int(typewriter_cfg.get('max_duration_ms', typewriter_defaults['max_duration_ms'])))
        self.typewriterTtsDelayCard = RangeSettingCard(0, 3000, 1, FIF.VOLUME, '语音播报文字延迟', '开启语音播报时，回复文字延迟显示的时间，单位毫秒', self.replyDisplayGroup)
        self.typewriterTtsDelayCard.setValue(int(typewriter_cfg.get('tts_delay_ms', typewriter_defaults['tts_delay_ms'])))

        self.visualGroup.addSettingCard(self.replyCardStyleCard)
        self.visualGroup.addSettingCard(self.voiceOrbStyleCard)
        self.visualGroup.addSettingCard(self.voiceFollowEffectCard)
        for card in [self.typewriterEnabledCard, self.typewriterSpeedCard, self.typewriterMaxDurationCard, self.typewriterTtsDelayCard]:
            self.replyDisplayGroup.addSettingCard(card)
        self.expandLayout.addWidget(self.visualGroup)
        self.expandLayout.addWidget(self.replyDisplayGroup)

    def _save(self):
        config.app_config.update({
            'reply_card_style': self.replyCardStyleCard.currentValue() or 'aurora',
            'voice_orb_style': self.voiceOrbStyleCard.currentValue() or 'jade',
            'voice_follow_effect': self.voiceFollowEffectCard.currentValue() or 'spring',
        })
        config.app_config.pop('voice_follow_level', None)
        config.save_app_config()
        config.save_typewriter_config({
            'enabled': self.typewriterEnabledCard.isChecked(),
            'speed_ms': int(self.typewriterSpeedCard.value()),
            'max_duration_ms': int(self.typewriterMaxDurationCard.value()),
            'tts_delay_ms': int(self.typewriterTtsDelayCard.value()),
        })
        InfoBar.success('保存成功', '基础已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())
        self.settings_changed.emit()


class OpenClawHttpApiWorker(QThread):
    result_ready = Signal(bool, str)

    def run(self):
        exe = shutil.which('openclaw.cmd') or shutil.which('openclaw')
        if not exe:
            self.result_ready.emit(False, '找不到 openclaw 命令，请确认 OpenClaw CLI 已安装并加入 PATH。')
            return
        try:
            if exe.lower().endswith('.cmd'):
                command = ['cmd.exe', '/c', exe, 'config', 'set', 'gateway.http.endpoints.responses.enabled', 'true']
            else:
                command = [exe, 'config', 'set', 'gateway.http.endpoints.responses.enabled', 'true']
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        except Exception as exc:
            self.result_ready.emit(False, str(exc))
            return
        output = (result.stdout or result.stderr or '').strip()
        if result.returncode == 0:
            self.result_ready.emit(True, output or 'OpenClaw Responses HTTP API 已启用。')
        else:
            self.result_ready.emit(False, output or 'openclaw config set 执行失败。')


class OpenClawProbeWorker(QThread):
    result_ready = Signal(bool, str)

    def __init__(self, api_url, parent=None):
        super().__init__(parent)
        self.api_url = api_url

    def run(self):
        self.result_ready.emit(*probe_openclaw_gateway(self.api_url))


class MiniPetBackendProbeWorker(QThread):
    result_ready = Signal(bool, str)

    def __init__(self, ws_url, parent=None):
        super().__init__(parent)
        self.ws_url = ws_url

    def run(self):
        self.result_ready.emit(*probe_minipet_backend(self.ws_url))


class AgentPage(MiniPetScrollPage):
    settings_changed = Signal()

    BACKENDS = [
        ('builtin', '使用内置大模型'),
        ('openclaw', '连接 OpenClaw 网关'),
        ('custom', '连接 MiniPet 协议后端'),
        ('claude_code', '连接 Claude Code'),
        ('codex', '连接 Codex'),
    ]

    def __init__(self, parent=None):
        super().__init__('智能体设置', parent, save_callback=lambda: self._save())
        self.worker = None
        cfg = config.app_config
        llm_cfg = config.llm_config

        self.modeBox = QWidget(self.scrollWidget)
        self.modeLayout = QVBoxLayout(self.modeBox)
        self.modeLayout.setContentsMargins(0, 0, 0, 0)
        self.modeLayout.setSpacing(0)
        self.backendCard = ComboSettingCard(self.BACKENDS, FIF.ROBOT, '智能体模式', '各后端分别保存聊天记录；切换模式后只显示当前后端的历史', self.modeBox)
        self.backendCard.setCurrentValue(cfg.get('agent_backend', 'builtin'))
        self.modeBox.setFixedHeight(self.backendCard.height())

        self.openclawGroup = SettingCardGroup('OpenClaw 设置', self.scrollWidget)
        self.openclawApiCard = LineEditSettingCard(FIF.LINK, 'OpenClaw Gateway 地址', '需先在 OpenClaw 开启 Responses HTTP API；MiniPet 会直接请求这里', placeholder=config.OPENCLAW_API_URL_DEFAULT, parent=self.openclawGroup)
        self.openclawApiCard.setText(cfg.get('openclaw_api_url', config.OPENCLAW_API_URL_DEFAULT))
        self.openclawProbeCard = SettingCard(FIF.SYNC, '测试连接', '检测网关是否启动，并判断 Responses HTTP API 是否可用', self.openclawGroup)
        self.openclawProbeBtn = PrimaryPushButton('测试', self.openclawProbeCard)
        self.openclawProbeCard.hBoxLayout.addStretch(1)
        self.openclawProbeCard.hBoxLayout.addWidget(self.openclawProbeBtn, 0, Qt.AlignRight)
        self.openclawProbeCard.hBoxLayout.addSpacing(16)
        self.openclawProbeBtn.clicked.connect(self._probe_openclaw_gateway)
        self.openclawEnableCard = SettingCard(FIF.SETTING, '启用 OpenClaw HTTP API', '本功能要求 OpenClaw 打开 Responses HTTP 接口；如果未打开，可以使用本方式一键配置，启用后可能要重启 OpenClaw 网关', self.openclawGroup)
        self.openclawEnableBtn = PrimaryPushButton('一键开启', self.openclawEnableCard)
        self.openclawEnableCard.hBoxLayout.addStretch(1)
        self.openclawEnableCard.hBoxLayout.addWidget(self.openclawEnableBtn, 0, Qt.AlignRight)
        self.openclawEnableCard.hBoxLayout.addSpacing(16)
        self.openclawEnableBtn.clicked.connect(self._enable_openclaw_http_api)
        self.openclawSessionCard = PushSettingCard('打开', FIF.LINK, 'OpenClaw 会话管理', f'打开 OpenClaw 会话列表；当前会话 {self._openclaw_session_key()}', self.openclawGroup)
        self.openclawSessionCard.clicked.connect(self._open_openclaw_sessions)

        self.customGroup = SettingCardGroup('MiniPet 协议后端设置', self.scrollWidget)
        self.customWsCard = LineEditSettingCard(FIF.LINK, 'MiniPet 协议后端地址', '连接 miniClaw 或其他按 MiniPet 通用协议实现的智能体服务', placeholder=config.CUSTOM_AGENT_WS_DEFAULT, parent=self.customGroup)
        self.customWsCard.setText(cfg.get('custom_agent_ws_url', config.CUSTOM_AGENT_WS_DEFAULT))
        self.customProbeCard = SettingCard(FIF.SYNC, '测试连接', '发送 session.probe，判断后端是否支持 MiniPet 协议检测', self.customGroup)
        self.customProbeBtn = PrimaryPushButton('测试', self.customProbeCard)
        self.customProbeCard.hBoxLayout.addStretch(1)
        self.customProbeCard.hBoxLayout.addWidget(self.customProbeBtn, 0, Qt.AlignRight)
        self.customProbeCard.hBoxLayout.addSpacing(16)
        self.customProbeBtn.clicked.connect(self._probe_minipet_backend)
        self.protocolDocCard = PushSettingCard('打开', FIF.MESSAGE, 'MiniPet 协议文档', '通用后端接入见 minipet交互协议设计.md', self.customGroup)
        self.protocolDocCard.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(config.ROOT_DIR / 'minipet交互协议设计.md'))))

        self.claudeCodeGroup = SettingCardGroup('Claude Code 设置', self.scrollWidget)
        self.claudeCodeDirCard = LineEditSettingCard(FIF.LINK, '项目目录', '第一次输入时会在这个目录下启动 Claude Code 会话', placeholder=str(config.ROOT_DIR), parent=self.claudeCodeGroup)
        self.claudeCodeDirCard.setText(cfg.get('claude_code_project_dir', str(config.ROOT_DIR)))
        self.claudeCodeBrowseCard = SettingCard(FIF.LINK, '选择目录', '选择 Claude Code 执行开发任务的工作目录', self.claudeCodeGroup)
        self.claudeCodeBrowseBtn = PrimaryPushButton('选择', self.claudeCodeBrowseCard)
        self.claudeCodeBrowseCard.hBoxLayout.addStretch(1)
        self.claudeCodeBrowseCard.hBoxLayout.addWidget(self.claudeCodeBrowseBtn, 0, Qt.AlignRight)
        self.claudeCodeBrowseCard.hBoxLayout.addSpacing(16)
        self.claudeCodeBrowseBtn.clicked.connect(self._choose_claude_code_dir)
        self.claudeCodeResetCard = SettingCard(FIF.DELETE, '重置会话', '结束当前 Claude Code 会话，下次会使用新的会话 ID', self.claudeCodeGroup)
        self.claudeCodeResetBtn = PrimaryPushButton('重置', self.claudeCodeResetCard)
        self.claudeCodeResetCard.hBoxLayout.addStretch(1)
        self.claudeCodeResetCard.hBoxLayout.addWidget(self.claudeCodeResetBtn, 0, Qt.AlignRight)
        self.claudeCodeResetCard.hBoxLayout.addSpacing(16)
        self.claudeCodeResetBtn.clicked.connect(self._reset_claude_code_session)

        self.codexGroup = SettingCardGroup('Codex 设置', self.scrollWidget)
        self.codexDirCard = LineEditSettingCard(FIF.LINK, '项目目录', '第一次输入时会在这个目录下启动 Codex 会话', placeholder=str(config.ROOT_DIR), parent=self.codexGroup)
        self.codexDirCard.setText(cfg.get('codex_project_dir', str(config.ROOT_DIR)))
        self.codexBrowseCard = SettingCard(FIF.LINK, '选择目录', '选择 Codex 执行开发任务的工作目录', self.codexGroup)
        self.codexBrowseBtn = PrimaryPushButton('选择', self.codexBrowseCard)
        self.codexBrowseCard.hBoxLayout.addStretch(1)
        self.codexBrowseCard.hBoxLayout.addWidget(self.codexBrowseBtn, 0, Qt.AlignRight)
        self.codexBrowseCard.hBoxLayout.addSpacing(16)
        self.codexBrowseBtn.clicked.connect(self._choose_codex_dir)
        self.codexResetCard = SettingCard(FIF.DELETE, '重置会话', '结束当前 Codex 会话，下次会创建新的会话', self.codexGroup)
        self.codexResetBtn = PrimaryPushButton('重置', self.codexResetCard)
        self.codexResetCard.hBoxLayout.addStretch(1)
        self.codexResetCard.hBoxLayout.addWidget(self.codexResetBtn, 0, Qt.AlignRight)
        self.codexResetCard.hBoxLayout.addSpacing(16)
        self.codexResetBtn.clicked.connect(self._reset_codex_session)

        self.builtinGroup = SettingCardGroup('内置大模型设置', self.scrollWidget)
        self.apiBaseCard = LineEditSettingCard(FIF.GLOBE, 'API 地址', 'OpenAI 兼容接口地址，例如 https://api.openai.com/v1', placeholder='https://api.openai.com/v1', parent=self.builtinGroup)
        self.apiBaseCard.setText(llm_cfg.get('api_base', ''))
        self.apiKeyCard = LineEditSettingCard(FIF.VPN, 'API Key', '密钥会保存在本地 .env', password=True, placeholder='sk-...', parent=self.builtinGroup)
        self.apiKeyCard.setText(llm_cfg.get('api_key', ''))
        self.modelCard = LineEditSettingCard(FIF.ROBOT, '模型名称', 'OpenAI 兼容模型名，如 gpt-4o-mini / deepseek-chat', placeholder='gpt-4o-mini', parent=self.builtinGroup)
        self.modelCard.setText(llm_cfg.get('model', ''))
        self.memoryTurnsCard = LineEditSettingCard(FIF.HISTORY, '记忆对话轮数', 'AI 对话时带入最近多少轮历史对话', placeholder='10', parent=self.builtinGroup)
        self.memoryTurnsCard.setText(llm_cfg.get('memory_turns', 10))
        self.actionCard = SettingCard(FIF.LINK, '测试连接', '测试内置大模型连接是否正常', self.builtinGroup)
        self.testBtn = PrimaryPushButton('测试连接', self.actionCard)
        self.actionCard.hBoxLayout.addStretch(1)
        self.actionCard.hBoxLayout.addWidget(self.testBtn, 0, Qt.AlignRight)
        self.actionCard.hBoxLayout.addSpacing(16)
        self.testBtn.clicked.connect(self._test_builtin_llm)

        self.modeLayout.addWidget(self.backendCard)
        for card in [self.openclawApiCard, self.openclawEnableCard, self.openclawSessionCard, self.openclawProbeCard]:
            self.openclawGroup.addSettingCard(card)
        for card in [self.customWsCard, self.protocolDocCard, self.customProbeCard]:
            self.customGroup.addSettingCard(card)
        for card in [self.claudeCodeDirCard, self.claudeCodeBrowseCard, self.claudeCodeResetCard]:
            self.claudeCodeGroup.addSettingCard(card)
        for card in [self.codexDirCard, self.codexBrowseCard, self.codexResetCard]:
            self.codexGroup.addSettingCard(card)
        for card in [self.apiBaseCard, self.apiKeyCard, self.modelCard, self.memoryTurnsCard, self.actionCard]:
            self.builtinGroup.addSettingCard(card)
        self.expandLayout.addWidget(self.modeBox)
        self.expandLayout.addWidget(self.openclawGroup)
        self.expandLayout.addWidget(self.customGroup)
        self.expandLayout.addWidget(self.claudeCodeGroup)
        self.expandLayout.addWidget(self.codexGroup)
        self.expandLayout.addWidget(self.builtinGroup)
        self.backendCard.comboBox.currentIndexChanged.connect(lambda _index: self._sync_backend_groups())
        self._sync_backend_groups()

    def _sync_backend_groups(self):
        backend = self.backendCard.currentValue() or 'builtin'
        self.openclawGroup.setVisible(backend == 'openclaw')
        self.customGroup.setVisible(backend == 'custom')
        self.claudeCodeGroup.setVisible(backend == 'claude_code')
        self.codexGroup.setVisible(backend == 'codex')
        self.builtinGroup.setVisible(backend == 'builtin')
        for widget in (self.modeBox, self.openclawGroup, self.customGroup, self.claudeCodeGroup, self.codexGroup, self.builtinGroup, self.scrollWidget):
            widget.adjustSize()
            widget.updateGeometry()

    def _choose_claude_code_dir(self):
        path = QFileDialog.getExistingDirectory(self, '选择 Claude Code 项目目录', self.claudeCodeDirCard.text() or str(config.ROOT_DIR))
        if path:
            self.claudeCodeDirCard.setText(path)

    def _choose_codex_dir(self):
        path = QFileDialog.getExistingDirectory(self, '选择 Codex 项目目录', self.codexDirCard.text() or str(config.ROOT_DIR))
        if path:
            self.codexDirCard.setText(path)

    def _reset_claude_code_session(self):
        config.app_config['claude_code_reset_token'] = int(config.app_config.get('claude_code_reset_token') or 0) + 1
        config.save_app_config()
        InfoBar.success('已重置', '下次发送消息会启动新的 Claude Code 会话', duration=2500, position=InfoBarPosition.BOTTOM, parent=self.window())
        self.settings_changed.emit()

    def _reset_codex_session(self):
        config.app_config['codex_reset_token'] = int(config.app_config.get('codex_reset_token') or 0) + 1
        config.save_app_config()
        InfoBar.success('已重置', '下次发送消息会创建新的 Codex 会话', duration=2500, position=InfoBarPosition.BOTTOM, parent=self.window())
        self.settings_changed.emit()

    def _openclaw_session_key(self):
        model = config.app_config.get('openclaw_model') or config.OPENCLAW_MODEL_DEFAULT
        lane = str(model).split(':', 1)[1] if str(model).startswith('openclaw:') else 'main'
        user = config.app_config.get('openclaw_user') or config.OPENCLAW_USER_DEFAULT
        return f'agent:{lane}:openresponses-user:{user}'

    def _openclaw_base_url(self):
        api_url = self.openclawApiCard.text() or config.OPENCLAW_API_URL_DEFAULT
        parsed = urlparse(api_url)
        return f'{parsed.scheme or "http"}://{parsed.netloc or "127.0.0.1:18789"}'

    def _openclaw_sessions_url(self):
        return self._openclaw_base_url().rstrip('/') + '/sessions'

    def _open_openclaw_sessions(self):
        QDesktopServices.openUrl(QUrl(self._openclaw_sessions_url()))

    def _enable_openclaw_http_api(self):
        if getattr(self, 'openclaw_enable_worker', None) is not None:
            return
        self.openclawEnableBtn.setEnabled(False)
        self.openclawEnableBtn.setText('开启中...')
        self.openclaw_enable_worker = OpenClawHttpApiWorker(self)
        self.openclaw_enable_worker.result_ready.connect(self._on_openclaw_http_api_enabled)
        self.openclaw_enable_worker.finished.connect(lambda: setattr(self, 'openclaw_enable_worker', None))
        self.openclaw_enable_worker.start()

    def _on_openclaw_http_api_enabled(self, success, text):
        self.openclawEnableBtn.setEnabled(True)
        self.openclawEnableBtn.setText('一键开启')
        if success:
            InfoBar.success('已开启 OpenClaw HTTP API', text[:120], duration=3500, position=InfoBarPosition.BOTTOM, parent=self.window())
        else:
            InfoBar.error('开启失败', text[:160], duration=6000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _probe_openclaw_gateway(self):
        if getattr(self, 'openclaw_probe_worker', None) is not None:
            return
        self.openclawProbeBtn.setEnabled(False)
        self.openclawProbeBtn.setText('测试中...')
        api_url = self.openclawApiCard.text() or config.OPENCLAW_API_URL_DEFAULT
        self.openclaw_probe_worker = OpenClawProbeWorker(api_url, self)
        self.openclaw_probe_worker.result_ready.connect(self._on_openclaw_gateway_probed)
        self.openclaw_probe_worker.finished.connect(lambda: setattr(self, 'openclaw_probe_worker', None))
        self.openclaw_probe_worker.start()

    def _on_openclaw_gateway_probed(self, success, text):
        self.openclawProbeBtn.setEnabled(True)
        self.openclawProbeBtn.setText('测试')
        if success:
            InfoBar.success('检测完成', text[:180], duration=5000, position=InfoBarPosition.BOTTOM, parent=self.window())
        else:
            InfoBar.error('检测未通过', text[:180], duration=6000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _probe_minipet_backend(self):
        if getattr(self, 'custom_probe_worker', None) is not None:
            return
        self.customProbeBtn.setEnabled(False)
        self.customProbeBtn.setText('测试中...')
        ws_url = self.customWsCard.text() or config.CUSTOM_AGENT_WS_DEFAULT
        self.custom_probe_worker = MiniPetBackendProbeWorker(ws_url, self)
        self.custom_probe_worker.result_ready.connect(self._on_minipet_backend_probed)
        self.custom_probe_worker.finished.connect(lambda: setattr(self, 'custom_probe_worker', None))
        self.custom_probe_worker.start()

    def _on_minipet_backend_probed(self, success, text):
        self.customProbeBtn.setEnabled(True)
        self.customProbeBtn.setText('测试')
        if success:
            InfoBar.success('测试完成', text[:180], duration=5000, position=InfoBarPosition.BOTTOM, parent=self.window())
        else:
            InfoBar.error('连接失败', text[:180], duration=6000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _parse_int_card(self, card, default, minimum=1):
        try:
            return max(minimum, int(card.text() or default))
        except ValueError:
            return default

    def _collect_llm(self):
        memory_turns = self._parse_int_card(self.memoryTurnsCard, 10, minimum=0)
        return {
            'api_base': self.apiBaseCard.text(),
            'api_key': self.apiKeyCard.text(),
            'model': self.modelCard.text(),
            'memory_turns': memory_turns,
            'system_prompt': config.llm_config.get('system_prompt', ''),
        }

    def _save(self):
        config.app_config.update({
            'agent_backend': self.backendCard.currentValue() or 'builtin',
            'openclaw_api_url': self.openclawApiCard.text() or config.OPENCLAW_API_URL_DEFAULT,
            'custom_agent_ws_url': self.customWsCard.text() or config.CUSTOM_AGENT_WS_DEFAULT,
            'claude_code_project_dir': self.claudeCodeDirCard.text().strip() or str(config.ROOT_DIR),
            'codex_project_dir': self.codexDirCard.text().strip() or str(config.ROOT_DIR),
        })
        config.save_app_config()
        config.save_llm_config(self._collect_llm())
        InfoBar.success('保存成功', '智能体设置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())
        self.settings_changed.emit()

    def _test_builtin_llm(self):
        self.testBtn.setEnabled(False)
        self.testBtn.setText('测试中...')
        self.worker = ChatWorker([{'role': 'user', 'content': '你好'}], self._collect_llm(), parent=self)
        self.worker.result_ready.connect(self._on_test_result)
        self.worker.start()

    def _on_test_result(self, success, text):
        self.testBtn.setEnabled(True)
        self.testBtn.setText('测试连接')
        if success:
            InfoBar.success('测试成功', '连接正常：' + text[:40], duration=3000, position=InfoBarPosition.BOTTOM, parent=self.window())
        else:
            InfoBar.error('测试失败', text[:120], duration=5000, position=InfoBarPosition.BOTTOM, parent=self.window())


