# coding:utf-8
"""大模型设置页面。"""

from PySide6.QtCore import Qt
from qfluentwidgets import InfoBar, InfoBarPosition, PrimaryPushButton, SettingCard, SettingCardGroup
from qfluentwidgets import FluentIcon as FIF

from miniPet import config
from miniPet.base_page import MiniPetScrollPage
from miniPet.clients.llm_client import ChatWorker
from miniPet.widgets.setting_cards import ComboSettingCard, LineEditSettingCard


class LLMPage(MiniPetScrollPage):
    def __init__(self, parent=None):
        super().__init__('大模型设置', parent, save_callback=lambda: self._save())
        self.worker = None
        cfg = config.llm_config

        self.apiGroup = SettingCardGroup('API 配置', self.scrollWidget)
        self.providerCard = ComboSettingCard([('openai', 'OpenAI 兼容')], FIF.CLOUD, '接口类型', '当前仅支持 OpenAI 兼容 Chat Completions 接口', self.apiGroup)
        self.providerCard.setCurrentValue('openai')
        self.apiBaseCard = LineEditSettingCard(FIF.GLOBE, 'API 地址', 'OpenAI 兼容接口地址，例如 https://api.openai.com/v1', placeholder='https://api.openai.com/v1', parent=self.apiGroup)
        self.apiBaseCard.setText(cfg.get('api_base', ''))
        self.apiKeyCard = LineEditSettingCard(FIF.VPN, 'API Key', '密钥会保存在本地 .env', password=True, placeholder='sk-...', parent=self.apiGroup)
        self.apiKeyCard.setText(cfg.get('api_key', ''))
        self.modelCard = LineEditSettingCard(FIF.ROBOT, '模型名称', 'OpenAI 兼容模型名，如 gpt-4o-mini / deepseek-chat', placeholder='gpt-4o-mini', parent=self.apiGroup)
        self.modelCard.setText(cfg.get('model', ''))
        self.maxTokenCard = LineEditSettingCard(FIF.FONT_SIZE, '最大 Token', '单次回复的最大 token 数', placeholder='1024', parent=self.apiGroup)
        self.maxTokenCard.setText(cfg.get('max_tokens', 1024))

        self.actionCard = SettingCard(FIF.LINK, '测试连接', '测试大模型连接是否正常', self.apiGroup)
        self.testBtn = PrimaryPushButton('测试连接', self.actionCard)
        self.actionCard.hBoxLayout.addStretch(1)
        self.actionCard.hBoxLayout.addWidget(self.testBtn, 0, Qt.AlignRight)
        self.actionCard.hBoxLayout.addSpacing(16)
        self.testBtn.clicked.connect(self._test)

        for card in [self.providerCard, self.apiBaseCard, self.apiKeyCard, self.modelCard, self.maxTokenCard, self.actionCard]:
            self.apiGroup.addSettingCard(card)
        self.expandLayout.addWidget(self.apiGroup)

    def _collect(self):
        try:
            max_tokens = int(self.maxTokenCard.text() or 1024)
        except ValueError:
            max_tokens = 1024
        return {
            'provider': 'openai',
            'api_base': self.apiBaseCard.text(),
            'api_key': self.apiKeyCard.text(),
            'model': self.modelCard.text(),
            'max_tokens': max_tokens,
            'system_prompt': config.llm_config.get('system_prompt', ''),
        }

    def _save(self):
        config.save_llm_config(self._collect())
        InfoBar.success('保存成功', '大模型配置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _test(self):
        self.testBtn.setEnabled(False)
        self.testBtn.setText('测试中...')
        self.worker = ChatWorker([{'role': 'user', 'content': '你好'}], self._collect(), parent=self)
        self.worker.result_ready.connect(self._on_test_result)
        self.worker.start()

    def _on_test_result(self, success, text):
        self.testBtn.setEnabled(True)
        self.testBtn.setText('测试连接')
        if success:
            InfoBar.success('测试成功', '连接正常：' + text[:40], duration=3000, position=InfoBarPosition.BOTTOM, parent=self.window())
        else:
            InfoBar.error('测试失败', text[:120], duration=5000, position=InfoBarPosition.BOTTOM, parent=self.window())


