# coding:utf-8

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QWidget, QVBoxLayout
from qfluentwidgets import (ComboBox, ExpandLayout, FluentWindow, InfoBar, InfoBarPosition,
                            LineEdit, PrimaryPushButton, PushSettingCard, ScrollArea,
                            SettingCard, SettingCardGroup, Slider, SwitchSettingCard)
from qfluentwidgets import FluentIcon as FIF

from miniPet import config
from miniPet.llm_client import ChatWorker
from miniPet.memory_store import CATEGORY_LABELS, MEMORY_CATEGORIES, MemoryStore
from miniPet.tts_client import TtsCacheWorker, TtsPreviewWorker, stop_tts


VOICE_OPTIONS = [
    ('zh_female_vv_uranus_bigtts', 'vivi 2.0'),
    ('zh_female_xiaohe_uranus_bigtts', '小何 2.0'),
    ('zh_male_m191_uranus_bigtts', '云舟 2.0'),
    ('zh_male_taocheng_uranus_bigtts', '小天 2.0'),
    ('saturn_zh_female_cancan_tob', '知性灿灿'),
    ('saturn_zh_female_qingyingduoduo_cs_tob', '轻盈朵朵 2.0'),
    ('saturn_zh_female_tiaopigongzhu_tob', '调皮公主'),
    ('saturn_zh_female_keainvsheng_tob', '可爱女生'),
    ('zh_female_zhixingnv_uranus_bigtts', '知性女声 2.0'),
    ('zh_female_qinqienv_uranus_bigtts', '亲切女声 2.0'),
    ('zh_female_lingling_uranus_bigtts', '玲玲姐姐 2.0'),
    ('zh_female_jiaochuannv_uranus_bigtts', '娇喘女声 2.0'),
    ('zh_female_kailangjiejie_uranus_bigtts', '开朗姐姐 2.0'),
    ('zh_female_roumeinvyou_uranus_bigtts', '柔美女友2.0'),
    ('zh_female_sophie_uranus_bigtts', '魅力苏菲2.0'),
    ('zh_female_mengyatou_uranus_bigtts', '萌丫头'),
    ('zh_female_yingtaowanzi_uranus_bigtts', '樱桃丸子2.0'),
    ('zh_female_sajiaoxuemei_uranus_bigtts', '撒娇学妹2.0'),
]
VOICE_VALUE_TO_LABEL = dict(VOICE_OPTIONS)
VOICE_LABEL_TO_VALUE = {label: value for value, label in VOICE_OPTIONS}

REALTIME_VOICE_OPTIONS = [
    ('zh_female_vv_jupiter_bigtts', 'vv 女声'),
    ('zh_female_xiaohe_jupiter_bigtts', '小何女声'),
    ('zh_male_yunzhou_jupiter_bigtts', '云舟男声'),
    ('zh_male_xiaotian_jupiter_bigtts', '小天男声'),
]

BUBBLE_STYLE_OPTIONS = [
    ('soft', '柔和白'),
    ('glass', '半透明玻璃'),
    ('pink', '樱花粉'),
    ('mint', '薄荷绿'),
    ('night', '夜间蓝'),
]

SMART_BUBBLE_STYLE_OPTIONS = [
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

VOICE_FOLLOW_LEVEL_OPTIONS = [
    ('soft', '柔和'),
    ('normal', '标准'),
    ('fast', '灵敏'),
]

STYLE_PREVIEW_QSS = {
    'bubble': {
        'soft': 'background:#ffffff;border:1px solid #d2d8e2;border-radius:12px;',
        'glass': 'background:rgba(255,255,255,0.72);border:1px solid rgba(255,255,255,0.85);border-radius:12px;',
        'pink': 'background:#fff6f9;border:1px solid #ffbed2;border-radius:12px;',
        'mint': 'background:#f2fffb;border:1px solid #a0e1d2;border-radius:12px;',
        'night': 'background:#262b3a;border:1px solid #5f6c91;border-radius:12px;',
    },
    'smart': {
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
        color = '#f4f6fb' if value in ('night', 'dark') else '#263238'
        text = 'Aa 气泡' if kind == 'bubble' else ('通知' if kind == 'smart' else '● 语音')
        preview.setText(text)
        preview.setStyleSheet('QLabel{%s color:%s; font:12px "Microsoft YaHei UI"; font-weight:600;}' % (qss, color))

    update_preview()
    card.comboBox.currentIndexChanged.connect(lambda _index: update_preview())
    card.hBoxLayout.insertWidget(card.hBoxLayout.count() - 2, preview, 0, Qt.AlignRight)
    return preview


def _icon(name):
    return QIcon(str(config.RES_DIR / 'icons' / 'system' / name))


class RangeSettingCard(SettingCard):
    def __init__(self, minimum, maximum, factor, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.factor = factor
        self.valueLabel = QLabel(self)
        self.slider = Slider(Qt.Horizontal, self)
        self.slider.setRange(minimum, maximum)
        self.slider.setMinimumWidth(260)
        self.hBoxLayout.addStretch(1)
        self.hBoxLayout.addWidget(self.valueLabel, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(12)
        self.hBoxLayout.addWidget(self.slider, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.slider.valueChanged.connect(self._on_value_changed)

    def _on_value_changed(self, value):
        self.valueLabel.setText('%g' % (value * self.factor))
        self.valueLabel.adjustSize()

    def setValue(self, value):
        self.slider.setValue(value)
        self._on_value_changed(value)

    def value(self):
        return self.slider.value() * self.factor


class ComboSettingCard(SettingCard):
    def __init__(self, items, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.comboBox = ComboBox(self)
        self.comboBox.setMinimumWidth(180)
        self.valueToText = {}
        self.textToValue = {}
        for item in items:
            if isinstance(item, tuple):
                value, text = item
            else:
                value, text = item, item
            self.valueToText[value] = text
            self.textToValue[text] = value
            self.comboBox.addItem(text, userData=value)
        self.hBoxLayout.addStretch(1)
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def setCurrentText(self, text):
        index = self.comboBox.findText(text)
        if index >= 0:
            self.comboBox.setCurrentIndex(index)

    def setCurrentValue(self, value):
        text = self.valueToText.get(value, value)
        self.setCurrentText(text)

    def currentText(self):
        return self.comboBox.currentText()

    def currentValue(self):
        return self.comboBox.currentData() or self.textToValue.get(self.comboBox.currentText(), self.comboBox.currentText())


class LineEditSettingCard(SettingCard):
    def __init__(self, icon, title, content=None, password=False, placeholder='', parent=None):
        super().__init__(icon, title, content, parent)
        self.lineEdit = LineEdit(self)
        self.lineEdit.setMinimumWidth(300)
        self.lineEdit.setClearButtonEnabled(True)
        if placeholder:
            self.lineEdit.setPlaceholderText(placeholder)
        if password:
            self.lineEdit.setEchoMode(LineEdit.Password)
        self.hBoxLayout.addStretch(1)
        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def text(self):
        return self.lineEdit.text().strip()

    def setText(self, value):
        self.lineEdit.setText(str(value))


class AvatarPathSettingCard(LineEditSettingCard):
    def __init__(self, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, placeholder='选择 png / jpg / svg 图片', parent=parent)
        self._filename = ''
        self.lineEdit.hide()  # 不显示路径输入框
        self.preview = QLabel(self)
        self.preview.setFixedSize(42, 42)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet('QLabel{border:1px solid #dcdfe6;border-radius:8px;background:#fff;}')
        self.name_label = QLabel('未选择', self)
        self.name_label.setStyleSheet('QLabel{color:#909399;font-size:13px;}')
        self.button = PrimaryPushButton('选择', self)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 1, self.name_label, 0, Qt.AlignRight)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 1, self.preview, 0, Qt.AlignRight)
        self.hBoxLayout.insertWidget(self.hBoxLayout.count() - 1, self.button, 0, Qt.AlignRight)
        self.button.clicked.connect(self._choose_file)
        self._update_preview()

    def text(self):
        return self._filename

    def setText(self, value):
        self._filename = str(value or '').strip()
        self._update_preview()

    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window(),
            '选择头像',
            str(config.DATA_DIR),
            '图片文件 (*.png *.jpg *.jpeg *.bmp *.svg);;所有文件 (*)',
        )
        if path:
            import shutil
            config.AVATARS_DIR.mkdir(parents=True, exist_ok=True)
            dest = config.AVATARS_DIR / Path(path).name
            if Path(path).resolve() != dest.resolve():
                shutil.copy2(path, dest)
            self.setText(dest.name)

    def _update_preview(self):
        filename = self._filename
        if filename:
            p = config.AVATARS_DIR / filename
            if not p.is_file():
                # 兼容旧绝对路径：尝试复制到 avatars 目录
                old = Path(filename)
                if old.is_file():
                    import shutil
                    config.AVATARS_DIR.mkdir(parents=True, exist_ok=True)
                    dest = config.AVATARS_DIR / old.name
                    shutil.copy2(str(old), dest)
                    self._filename = old.name
                    p = dest
            pixmap = QPixmap(str(p)) if p.is_file() else QPixmap()
        else:
            pixmap = QPixmap()
        if pixmap.isNull():
            self.preview.setPixmap(QPixmap())
            self.preview.setText('?')
            self.name_label.setText('未选择')
            return
        self.preview.setText('')
        screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        pm = pixmap.scaled(int(38 * dpr), int(38 * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        self.preview.setPixmap(pm)
        self.name_label.setText(self._filename)


class MiniPetScrollPage(ScrollArea):
    def __init__(self, title, parent=None):
        super().__init__(parent=parent)
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)
        self.settingLabel = QLabel(title, self)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 74, 0, 20)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.scrollWidget.setObjectName('scrollWidget')
        self.settingLabel.setObjectName('settingLabel')
        self.expandLayout.setSpacing(26)
        self.expandLayout.setContentsMargins(60, 10, 60, 0)
        self._set_qss()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.settingLabel.move(50, 20)

    def _set_qss(self):
        qss = config.RES_DIR / 'icons' / 'system' / 'qss' / 'light' / 'setting_interface.qss'
        if qss.is_file():
            self.setStyleSheet(qss.read_text(encoding='utf-8'))


class BasicPage(MiniPetScrollPage):
    settings_changed = Signal()
    pet_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__('基本设置', parent)
        self.personalGroup = SettingCardGroup('个性化', self.scrollWidget)
        self.onTopCard = SwitchSettingCard(FIF.PIN, '置顶宠物', '宠物将始终显示在其他应用程序的上方', parent=self.personalGroup)
        self.onTopCard.setChecked(bool(config.app_config.get('on_top', True)))
        self.allowDropCard = SwitchSettingCard(_icon('falldown.svg'), '允许掉落', '鼠标释放时，宠物会掉落到地面；关闭后停留在原地', parent=self.personalGroup)
        self.allowDropCard.setChecked(bool(config.app_config.get('allow_drop', True)))
        self.volumeCard = RangeSettingCard(0, 100, 0.01, _icon('speaker.svg'), '音量', '通知和语音的音量', self.personalGroup)
        self.volumeCard.setValue(int(float(config.app_config.get('volume', 0.4)) * 100))
        self.scaleCard = RangeSettingCard(20, 500, 0.01, _icon('resize.svg'), '宠物大小', '调整宠物的显示比例', self.personalGroup)
        self.scaleCard.setValue(int(float(config.app_config.get('scale', 1.0)) * 100))
        self.petCard = ComboSettingCard(config.get_pet_list(), _icon('homestar.svg'), '默认宠物', '应用启动时显示的宠物', self.personalGroup)
        self.petCard.setCurrentText(config.app_config.get('default_pet', ''))
        self.petAvatarCard = AvatarPathSettingCard(_icon('character.svg'), '宠物头像', '聊天、语音聊天和豆包通话中显示的宠物头像', self.personalGroup)
        self.petAvatarCard.setText(config.app_config.get('pet_avatar', ''))
        self.userAvatarCard = AvatarPathSettingCard(FIF.PEOPLE, '我的头像', '聊天窗口中用户消息显示的头像', self.personalGroup)
        self.userAvatarCard.setText(config.app_config.get('user_avatar', ''))
        self.visualGroup = SettingCardGroup('视觉样式', self.scrollWidget)
        self.bubbleStyleCard = ComboSettingCard(BUBBLE_STYLE_OPTIONS, FIF.MESSAGE, '通知气泡样式', '选择普通对话气泡的颜色和质感', self.visualGroup)
        self.bubbleStyleCard.setCurrentValue(config.app_config.get('bubble_style', 'soft'))
        _attach_style_preview(self.bubbleStyleCard, 'bubble')
        self.smartBubbleStyleCard = ComboSettingCard(SMART_BUBBLE_STYLE_OPTIONS, FIF.MESSAGE, '智能通知样式', '选择事件卡片的视觉风格', self.visualGroup)
        self.smartBubbleStyleCard.setCurrentValue(config.app_config.get('smart_bubble_style', 'aurora'))
        _attach_style_preview(self.smartBubbleStyleCard, 'smart')
        self.voiceOrbStyleCard = ComboSettingCard(VOICE_ORB_STYLE_OPTIONS, FIF.VOLUME, '语音球样式', '选择语音悬浮球的颜色风格', self.visualGroup)
        self.voiceOrbStyleCard.setCurrentValue(config.app_config.get('voice_orb_style', 'jade'))
        _attach_style_preview(self.voiceOrbStyleCard, 'voice')
        self.voiceFollowEffectCard = ComboSettingCard(VOICE_FOLLOW_EFFECT_OPTIONS, FIF.SPEED_HIGH, '语音球跟随效果', '弹力绳有惯性过冲；丝滑吸附更稳、更少跳变', self.visualGroup)
        self.voiceFollowEffectCard.setCurrentValue(config.app_config.get('voice_follow_effect', 'spring'))
        self.voiceFollowLevelCard = ComboSettingCard(VOICE_FOLLOW_LEVEL_OPTIONS, FIF.SPEED_HIGH, '语音球跟随档位', '柔和更飘，标准均衡，灵敏更跟手', self.visualGroup)
        self.voiceFollowLevelCard.setCurrentValue(config.app_config.get('voice_follow_level', 'normal'))

        self.saveCard = PushSettingCard('保存', FIF.SAVE, '保存设置', '应用基础设置并刷新宠物', self.personalGroup)
        self.saveCard.clicked.connect(self._save)

        self.personalGroup.addSettingCard(self.onTopCard)
        self.personalGroup.addSettingCard(self.allowDropCard)
        self.personalGroup.addSettingCard(self.volumeCard)
        self.personalGroup.addSettingCard(self.scaleCard)
        self.personalGroup.addSettingCard(self.petCard)
        self.personalGroup.addSettingCard(self.petAvatarCard)
        self.personalGroup.addSettingCard(self.userAvatarCard)
        self.personalGroup.addSettingCard(self.saveCard)
        self.visualGroup.addSettingCard(self.bubbleStyleCard)
        self.visualGroup.addSettingCard(self.smartBubbleStyleCard)
        self.visualGroup.addSettingCard(self.voiceOrbStyleCard)
        self.visualGroup.addSettingCard(self.voiceFollowEffectCard)
        self.visualGroup.addSettingCard(self.voiceFollowLevelCard)
        self.expandLayout.addWidget(self.personalGroup)
        self.expandLayout.addWidget(self.visualGroup)

    def _save(self):
        old_pet = config.app_config.get('default_pet')
        config.app_config.update({
            'on_top': self.onTopCard.isChecked(),
            'allow_drop': self.allowDropCard.isChecked(),
            'volume': self.volumeCard.value(),
            'scale': self.scaleCard.value(),
            'default_pet': self.petCard.currentText(),
            'pet_avatar': self.petAvatarCard.text(),
            'user_avatar': self.userAvatarCard.text(),
            'bubble_style': self.bubbleStyleCard.currentValue() or 'soft',
            'smart_bubble_style': self.smartBubbleStyleCard.currentValue() or 'aurora',
            'voice_orb_style': self.voiceOrbStyleCard.currentValue() or 'jade',
            'voice_follow_effect': self.voiceFollowEffectCard.currentValue() or 'spring',
            'voice_follow_level': self.voiceFollowLevelCard.currentValue() or 'normal',
        })
        config.save_app_config()
        InfoBar.success('保存成功', '基础设置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())
        self.settings_changed.emit()
        if old_pet != self.petCard.currentText():
            self.pet_changed.emit(self.petCard.currentText())


class AgentPage(MiniPetScrollPage):
    settings_changed = Signal()

    BACKENDS = [
        ('builtin', '内置 miniPet 大模型'),
        ('openclaw', 'OpenClaw AI'),
        ('custom', '通用 AI 后端'),
    ]

    def __init__(self, parent=None):
        super().__init__('智能体设置', parent)
        cfg = config.app_config
        self.agentGroup = SettingCardGroup('桌宠大脑', self.scrollWidget)
        self.backendCard = ComboSettingCard(self.BACKENDS, FIF.ROBOT, '智能体选项', '选择桌宠输入、语音和投喂交给哪个大脑处理', self.agentGroup)
        self.backendCard.setCurrentValue(cfg.get('agent_backend', 'builtin'))
        self.openclawWsCard = LineEditSettingCard(FIF.LINK, 'OpenClaw Adapter 地址', 'OpenClaw 中转脚本监听的 WebSocket 地址', placeholder='ws://127.0.0.1:18888/ws/pet', parent=self.agentGroup)
        self.openclawWsCard.setText(cfg.get('openclaw_ws_url', 'ws://127.0.0.1:18888/ws/pet'))
        self.customWsCard = LineEditSettingCard(FIF.LINK, '通用 AI 后端地址', '完全体后端的 WebSocket 地址，遵循 miniPet 通用智能体协议', placeholder='ws://127.0.0.1:18889/ws/minipet', parent=self.agentGroup)
        self.customWsCard.setText(cfg.get('custom_agent_ws_url', 'ws://127.0.0.1:18889/ws/minipet'))
        self.noteCard = SettingCard(FIF.MESSAGE, '说明', '内置模式使用“大模型”页配置；OpenClaw 和通用后端模式会通过 WebSocket 双向通信', self.agentGroup)
        self.saveCard = PushSettingCard('保存', FIF.SAVE, '保存智能体设置', '切换后会重新连接外置智能体', self.agentGroup)
        self.saveCard.clicked.connect(self._save)

        for card in [self.backendCard, self.openclawWsCard, self.customWsCard, self.noteCard, self.saveCard]:
            self.agentGroup.addSettingCard(card)
        self.expandLayout.addWidget(self.agentGroup)

    def _save(self):
        config.app_config.update({
            'agent_backend': self.backendCard.currentValue() or 'builtin',
            'openclaw_ws_url': self.openclawWsCard.text() or 'ws://127.0.0.1:18888/ws/pet',
            'custom_agent_ws_url': self.customWsCard.text() or 'ws://127.0.0.1:18889/ws/minipet',
        })
        config.save_app_config()
        InfoBar.success('保存成功', '智能体设置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())
        self.settings_changed.emit()


class LLMPage(MiniPetScrollPage):
    def __init__(self, parent=None):
        super().__init__('大模型设置', parent)
        self.worker = None
        cfg = config.llm_config

        self.apiGroup = SettingCardGroup('API 配置', self.scrollWidget)
        self.providerCard = ComboSettingCard([('openai', 'OpenAI 兼容'), ('anthropic', 'Anthropic / Claude')], FIF.CLOUD, '服务商', '选择大模型 API 格式', self.apiGroup)
        self.providerCard.setCurrentValue(cfg.get('provider', 'openai'))
        self.apiBaseCard = LineEditSettingCard(FIF.GLOBE, 'API 地址', 'OpenAI 兼容接口地址，或 Anthropic 自定义 base_url', placeholder='https://api.openai.com/v1', parent=self.apiGroup)
        self.apiBaseCard.setText(cfg.get('api_base', ''))
        self.apiKeyCard = LineEditSettingCard(FIF.VPN, 'API Key', '密钥会保存在本地 .env', password=True, placeholder='sk-...', parent=self.apiGroup)
        self.apiKeyCard.setText(cfg.get('api_key', ''))
        self.modelCard = LineEditSettingCard(FIF.ROBOT, '模型名称', '如 gpt-4o-mini / deepseek-chat / claude-sonnet-4-6', placeholder='gpt-4o-mini', parent=self.apiGroup)
        self.modelCard.setText(cfg.get('model', ''))
        self.maxTokenCard = LineEditSettingCard(FIF.FONT_SIZE, '最大 Token', '单次回复的最大 token 数', placeholder='1024', parent=self.apiGroup)
        self.maxTokenCard.setText(cfg.get('max_tokens', 1024))

        self.actionCard = SettingCard(FIF.SAVE, '保存 / 测试', '保存配置或测试连接是否正常', self.apiGroup)
        self.testBtn = PrimaryPushButton('测试连接', self.actionCard)
        self.saveBtn = PrimaryPushButton('保存', self.actionCard)
        self.actionCard.hBoxLayout.addStretch(1)
        self.actionCard.hBoxLayout.addWidget(self.testBtn, 0, Qt.AlignRight)
        self.actionCard.hBoxLayout.addSpacing(8)
        self.actionCard.hBoxLayout.addWidget(self.saveBtn, 0, Qt.AlignRight)
        self.actionCard.hBoxLayout.addSpacing(16)
        self.saveBtn.clicked.connect(self._save)
        self.testBtn.clicked.connect(self._test)

        for card in [self.providerCard, self.apiBaseCard, self.apiKeyCard, self.modelCard, self.maxTokenCard, self.actionCard]:
            self.apiGroup.addSettingCard(card)
        self.expandLayout.addWidget(self.apiGroup)

    def _collect(self):
        try:
            max_tokens = int(self.maxTokenCard.text() or 1024)
        except ValueError:
            max_tokens = 1024
        provider = (self.providerCard.currentValue() or 'openai').lower()
        return {
            'provider': provider,
            'api_base': self.apiBaseCard.text(),
            'api_key': self.apiKeyCard.text(),
            'model': self.modelCard.text(),
            'max_tokens': max_tokens,
            'system_prompt': config.llm_config.get('system_prompt', ''),
            'memory_prompt': config.llm_config.get('memory_prompt', ''),
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


class MemoryEditDialog(QDialog):
    def __init__(self, memory=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('编辑记忆' if memory else '新增记忆')
        self.setMinimumWidth(560)
        self.memory = dict(memory or {})
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        self.categoryBox = ComboBox(self)
        for category in MEMORY_CATEGORIES:
            self.categoryBox.addItem(CATEGORY_LABELS.get(category, category), userData=category)
        current_category = self.memory.get('category', 'user_preference')
        index = self.categoryBox.findData(current_category)
        if index >= 0:
            self.categoryBox.setCurrentIndex(index)
        root.addWidget(QLabel('类别'))
        root.addWidget(self.categoryBox)

        self.textEdit = QPlainTextEdit(self)
        self.textEdit.setFixedHeight(90)
        self.textEdit.setPlainText(self.memory.get('text', ''))
        root.addWidget(QLabel('内容'))
        root.addWidget(self.textEdit)

        row = QHBoxLayout()
        self.importanceEdit = LineEdit(self)
        self.importanceEdit.setText(str(self.memory.get('importance', 3)))
        self.confidenceEdit = LineEdit(self)
        self.confidenceEdit.setText(str(self.memory.get('confidence', 0.8)))
        row.addWidget(QLabel('重要性 1-5'))
        row.addWidget(self.importanceEdit)
        row.addWidget(QLabel('置信度 0-1'))
        row.addWidget(self.confidenceEdit)
        root.addLayout(row)

        self.sourceDateEdit = LineEdit(self)
        self.sourceDateEdit.setPlaceholderText('YYYY-MM-DD，可空')
        self.sourceDateEdit.setText(self.memory.get('source_date', ''))
        root.addWidget(QLabel('来源日期'))
        root.addWidget(self.sourceDateEdit)

        self.sourceIdsEdit = LineEdit(self)
        self.sourceIdsEdit.setPlaceholderText('来源消息 ID，多个用逗号分隔')
        self.sourceIdsEdit.setText(','.join(self.memory.get('source_message_ids') or []))
        root.addWidget(QLabel('来源消息 ID'))
        root.addWidget(self.sourceIdsEdit)

        self.evidenceEdit = QPlainTextEdit(self)
        self.evidenceEdit.setFixedHeight(70)
        self.evidenceEdit.setPlainText(self.memory.get('evidence', ''))
        root.addWidget(QLabel('证据 / 来源说明'))
        root.addWidget(self.evidenceEdit)

        self.expiresEdit = LineEdit(self)
        self.expiresEdit.setPlaceholderText('YYYY-MM-DDTHH:MM:SS，留空表示不过期')
        self.expiresEdit.setText(self.memory.get('expires_at', ''))
        root.addWidget(QLabel('过期时间'))
        root.addWidget(self.expiresEdit)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancelBtn = PrimaryPushButton('取消', self)
        self.saveBtn = PrimaryPushButton('保存', self)
        self.cancelBtn.clicked.connect(self.reject)
        self.saveBtn.clicked.connect(self.accept)
        buttons.addWidget(self.cancelBtn)
        buttons.addWidget(self.saveBtn)
        root.addLayout(buttons)

    def values(self):
        try:
            importance = max(1, min(5, int(self.importanceEdit.text() or 3)))
        except ValueError:
            importance = 3
        try:
            confidence = max(0.0, min(1.0, float(self.confidenceEdit.text() or 0.8)))
        except ValueError:
            confidence = 0.8
        source_ids = [item.strip() for item in self.sourceIdsEdit.text().split(',') if item.strip()]
        return {
            'category': self.categoryBox.currentData() or 'user_preference',
            'text': self.textEdit.toPlainText().strip(),
            'importance': importance,
            'confidence': confidence,
            'source_date': self.sourceDateEdit.text().strip(),
            'source_message_ids': source_ids,
            'evidence': self.evidenceEdit.toPlainText().strip(),
            'expires_at': self.expiresEdit.text().strip(),
        }


class RolePage(MiniPetScrollPage):
    clear_history_requested = Signal()

    def __init__(self, memory_store=None, parent=None):
        super().__init__('角色设定', parent)
        cfg = config.llm_config
        self.memory_store = memory_store or MemoryStore(config.DATA_DIR / 'memory')

        self.roleGroup = SettingCardGroup('角色', self.scrollWidget)
        self.roleCard = SettingCard(_icon('character.svg'), '宠物性格', '定义宠物的性格与说话风格', self.roleGroup)
        self.roleEdit = QPlainTextEdit(self.roleCard)
        self.roleEdit.setPlainText(cfg.get('system_prompt', ''))
        self._style_editor(self.roleEdit)
        self.roleCard.hBoxLayout.addStretch(1)
        self.roleCard.hBoxLayout.addWidget(self.roleEdit, 0, Qt.AlignRight)
        self.roleCard.hBoxLayout.addSpacing(16)

        self.memoryCard = SettingCard(FIF.MESSAGE, '记忆', '会随角色设定一起发送给大模型', self.roleGroup)
        self.memoryEdit = QPlainTextEdit(self.memoryCard)
        self.memoryEdit.setPlainText(cfg.get('memory_prompt', ''))
        self._style_editor(self.memoryEdit)
        self.memoryCard.hBoxLayout.addStretch(1)
        self.memoryCard.hBoxLayout.addWidget(self.memoryEdit, 0, Qt.AlignRight)
        self.memoryCard.hBoxLayout.addSpacing(16)

        self.autoMemoryGroup = SettingCardGroup('自动总结', self.scrollWidget)
        self.autoMemoryCard = SwitchSettingCard(FIF.MESSAGE, '自动总结并记住重点', '不保存完整聊天，只从最近对话里总结少量长期有用信息', parent=self.autoMemoryGroup)
        self.autoMemoryCard.setChecked(bool(cfg.get('auto_memory_enabled', True)))
        self.memoryEveryCard = LineEditSettingCard(FIF.FONT_SIZE, '总结频率', '每多少次用户对话自动总结一次', placeholder='3', parent=self.autoMemoryGroup)
        self.memoryEveryCard.lineEdit.setFixedWidth(120)
        self.memoryEveryCard.setText(cfg.get('auto_memory_every_n_user_turns', 3))
        self.memoryRecentCard = LineEditSettingCard(FIF.MESSAGE, '参考最近消息', '每次总结时参考最近多少条当前对话', placeholder='12', parent=self.autoMemoryGroup)
        self.memoryRecentCard.lineEdit.setFixedWidth(120)
        self.memoryRecentCard.setText(cfg.get('auto_memory_recent_messages', 12))
        self.memoryMaxItemsCard = LineEditSettingCard(FIF.FONT_SIZE, '每次最多重点', '单次最多保存几条总结重点', placeholder='3', parent=self.autoMemoryGroup)
        self.memoryMaxItemsCard.lineEdit.setFixedWidth(120)
        self.memoryMaxItemsCard.setText(cfg.get('auto_memory_max_items_per_pass', 3))

        self.memoryListGroup = SettingCardGroup('总结重点管理', self.scrollWidget)

        self.manageGroup = SettingCardGroup('保存', self.scrollWidget)
        self.clearCard = PushSettingCard('清空', FIF.DELETE, '当前对话', '清空本次运行中的短期上下文，不删除已总结的重点', self.manageGroup)
        self.clearCard.clicked.connect(self._clear_history)
        self.saveCard = PushSettingCard('保存', FIF.SAVE, '保存角色设定', '保存宠物性格和自动总结设置', self.manageGroup)
        self.saveCard.clicked.connect(self._save)

        self.roleGroup.addSettingCard(self.roleCard)
        self.roleGroup.addSettingCard(self.memoryCard)
        for card in [self.autoMemoryCard, self.memoryEveryCard, self.memoryRecentCard, self.memoryMaxItemsCard]:
            self.autoMemoryGroup.addSettingCard(card)
        self.reload_memories()
        self.manageGroup.addSettingCard(self.clearCard)
        self.manageGroup.addSettingCard(self.saveCard)
        self.expandLayout.addWidget(self.roleGroup)
        self.expandLayout.addWidget(self.autoMemoryGroup)
        self.expandLayout.addWidget(self.memoryListGroup)
        self.expandLayout.addWidget(self.manageGroup)

    def _style_editor(self, editor):
        editor.setFixedSize(520, 92)
        editor.setStyleSheet(
            'QPlainTextEdit{background:#ffffff;border:1px solid #dfe3e8;border-radius:8px;'
            'padding:8px 10px;font-size:14px;color:#1f2328;}'
            'QPlainTextEdit:focus{border:1px solid #8ab4f8;}'
        )

    def _parse_int_card(self, card, default, minimum=1):
        try:
            return max(minimum, int(card.text() or default))
        except ValueError:
            return default

    def reload_memories(self):
        while self.memoryListGroup.cardLayout.count():
            item = self.memoryListGroup.cardLayout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        add_card = PushSettingCard('新增', FIF.MESSAGE, '手动新增记忆', '添加一条用户画像、项目事实或任务上下文', self.memoryListGroup)
        add_card.clicked.connect(self._add_memory)
        self.memoryListGroup.addSettingCard(add_card)
        grouped = self.memory_store.list_by_category(include_expired=True)
        empty = True
        for category in MEMORY_CATEGORIES:
            items = grouped.get(category) or []
            if not items:
                continue
            empty = False
            header = SettingCard(FIF.MESSAGE, CATEGORY_LABELS.get(category, category), '自动记忆分类', self.memoryListGroup)
            self.memoryListGroup.addSettingCard(header)
            for memory in items:
                created_at = memory.get('created_at', '')
                source_count = len(memory.get('source_message_ids') or [])
                meta = '记录：%s｜更新：%s｜重要性：%s｜置信度：%s｜来源：%s/%d条' % (
                    created_at,
                    memory.get('updated_at', ''),
                    memory.get('importance', 3),
                    memory.get('confidence', 0.8),
                    memory.get('source_date', '') or '手动/未知',
                    source_count,
                )
                if memory.get('evidence'):
                    meta += '｜证据：' + str(memory.get('evidence'))[:30]
                expires_at = memory.get('expires_at') or ''
                if expires_at:
                    meta += '｜过期：%s' % expires_at
                    if self.memory_store.is_expired(memory):
                        meta += '（已过期）'
                card = SettingCard(FIF.MESSAGE, memory.get('text', ''), meta, self.memoryListGroup)
                edit_btn = PrimaryPushButton('编辑', card)
                delete_btn = PrimaryPushButton('删除', card)
                edit_btn.clicked.connect(lambda checked=False, mid=memory.get('id'): self._edit_memory(mid))
                delete_btn.clicked.connect(lambda checked=False, mid=memory.get('id'): self._delete_memory(mid))
                card.hBoxLayout.addStretch(1)
                card.hBoxLayout.addWidget(edit_btn, 0, Qt.AlignRight)
                card.hBoxLayout.addSpacing(8)
                card.hBoxLayout.addWidget(delete_btn, 0, Qt.AlignRight)
                card.hBoxLayout.addSpacing(16)
                self.memoryListGroup.addSettingCard(card)
        if empty:
            self.memoryListGroup.addSettingCard(SettingCard(FIF.MESSAGE, '暂无总结重点', '对话后会自动总结少量值得长期记住的信息', self.memoryListGroup))

    def _validate_memory_values(self, values):
        if not values.get('text'):
            InfoBar.error('保存失败', '记忆内容不能为空', duration=3000, position=InfoBarPosition.BOTTOM, parent=self.window())
            return False
        expires_at = values.get('expires_at') or ''
        if expires_at:
            from datetime import datetime
            try:
                datetime.fromisoformat(expires_at)
            except ValueError:
                InfoBar.error('保存失败', '过期时间格式不正确', duration=3000, position=InfoBarPosition.BOTTOM, parent=self.window())
                return False
        return True

    def _add_memory(self):
        dialog = MemoryEditDialog(parent=self.window())
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not self._validate_memory_values(values):
            return
        self.memory_store.create_memory(**values)
        self.reload_memories()
        InfoBar.success('已新增', '记忆已新增', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _edit_memory(self, memory_id):
        memory = self.memory_store.get_memory(memory_id)
        if not memory:
            InfoBar.error('编辑失败', '记忆不存在', duration=3000, position=InfoBarPosition.BOTTOM, parent=self.window())
            return
        dialog = MemoryEditDialog(memory, self.window())
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        if not self._validate_memory_values(values):
            return
        self.memory_store.update_memory(memory_id, values)
        self.reload_memories()
        InfoBar.success('已保存', '记忆已更新', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _delete_memory(self, memory_id):
        if self.memory_store.delete_memory(memory_id):
            self.reload_memories()
            InfoBar.success('已删除', '记忆已删除', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _save(self):
        cfg = dict(config.llm_config)
        cfg['system_prompt'] = self.roleEdit.toPlainText().strip()
        cfg['memory_prompt'] = self.memoryEdit.toPlainText().strip()
        cfg['auto_memory_enabled'] = self.autoMemoryCard.isChecked()
        cfg['auto_memory_every_n_user_turns'] = self._parse_int_card(self.memoryEveryCard, 3)
        cfg['auto_memory_recent_messages'] = self._parse_int_card(self.memoryRecentCard, 12)
        cfg['auto_memory_max_items_per_pass'] = self._parse_int_card(self.memoryMaxItemsCard, 3)
        config.save_llm_config(cfg)
        InfoBar.success('保存成功', '角色和自动总结设置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _clear_history(self):
        self.clear_history_requested.emit()
        InfoBar.success('已清空', '当前对话上下文已清空', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())


class TTSPage(MiniPetScrollPage):
    def __init__(self, parent=None):
        super().__init__('语音设置', parent)
        self.worker = None
        self.preview_worker = None
        self._initializing = True
        cfg = config.tts_config
        self.apiGroup = SettingCardGroup('火山豆包 TTS', self.scrollWidget)
        self.enabledCard = SwitchSettingCard(FIF.VOLUME, '聊天回复语音播报', '开启后，宠物的 AI 回复会自动转成语音播放', parent=self.apiGroup)
        self.enabledCard.setChecked(bool(cfg.get('enabled', False)))
        self.apiKeyCard = LineEditSettingCard(FIF.VPN, 'API Key', '控制台 > API Key 管理中获取的 X-Api-Key', password=True, placeholder='火山引擎 API Key', parent=self.apiGroup)
        self.apiKeyCard.setText(cfg.get('api_key', ''))
        self.voiceCard = ComboSettingCard(VOICE_OPTIONS, FIF.PEOPLE, '音色', '选择后会生成并播放一句音色预览', self.apiGroup)
        self.voiceCard.setCurrentValue(cfg.get('voice_name', config.DEFAULT_TTS_CONFIG['voice_name']))
        self.voiceCard.comboBox.currentTextChanged.connect(self._preview_voice)
        self.maxCharsCard = LineEditSettingCard(FIF.FONT_SIZE, '最大字数', '过长回复会截断后播放，避免请求过大', placeholder='500', parent=self.apiGroup)
        self.maxCharsCard.lineEdit.setFixedWidth(120)
        self.maxCharsCard.setText(cfg.get('max_chars', 500))
        self.disableEmojiFilterCard = SwitchSettingCard(FIF.MESSAGE, '禁用 Emoji 过滤', '对应火山参数 disable_emoji_filter，开启后合成请求传 true', parent=self.apiGroup)
        self.disableEmojiFilterCard.setChecked(bool(cfg.get('disable_emoji_filter', False)))
        self.parenthesisFilterCard = LineEditSettingCard(FIF.FONT_SIZE, '括号过滤长度', '对应火山参数 max_length_to_filter_parenthesis，0 为不过滤，100 为过滤', placeholder='0', parent=self.apiGroup)
        self.parenthesisFilterCard.lineEdit.setFixedWidth(120)
        self.parenthesisFilterCard.setText(cfg.get('max_length_to_filter_parenthesis', 0))

        self.linkGroup = SettingCardGroup('相关链接', self.scrollWidget)
        self.linkCard = SettingCard(FIF.LINK, '火山语音资源', '服务开通、在线体验和 API 教程', self.linkGroup)
        self.serviceBtn = PrimaryPushButton('服务开通', self.linkCard)
        self.experienceBtn = PrimaryPushButton('在线体验', self.linkCard)
        self.apiDocBtn = PrimaryPushButton('API 教程', self.linkCard)
        self.linkCard.hBoxLayout.addStretch(1)
        self.linkCard.hBoxLayout.addWidget(self.serviceBtn, 0, Qt.AlignRight)
        self.linkCard.hBoxLayout.addSpacing(8)
        self.linkCard.hBoxLayout.addWidget(self.experienceBtn, 0, Qt.AlignRight)
        self.linkCard.hBoxLayout.addSpacing(8)
        self.linkCard.hBoxLayout.addWidget(self.apiDocBtn, 0, Qt.AlignRight)
        self.linkCard.hBoxLayout.addSpacing(16)
        self.serviceBtn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://console.volcengine.com/speech/new/setting/activate?_vtm_=a106466.b106468.0_0.0_0.0.44_7656326907147814435&projectName=default.')))
        self.experienceBtn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://console.volcengine.com/speech/new/experience/tts?projectName=default')))
        self.apiDocBtn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://www.volcengine.com/docs/6561/2528925?lang=zh')))

        self.actionCard = SettingCard(FIF.SAVE, '保存 / 测试', '保存配置或播放一段测试语音', self.apiGroup)
        self.testBtn = PrimaryPushButton('测试连接', self.actionCard)
        self.saveBtn = PrimaryPushButton('保存', self.actionCard)
        self.actionCard.hBoxLayout.addStretch(1)
        self.actionCard.hBoxLayout.addWidget(self.testBtn, 0, Qt.AlignRight)
        self.actionCard.hBoxLayout.addSpacing(8)
        self.actionCard.hBoxLayout.addWidget(self.saveBtn, 0, Qt.AlignRight)
        self.actionCard.hBoxLayout.addSpacing(16)
        self.saveBtn.clicked.connect(self._save)
        self.testBtn.clicked.connect(self._test)

        for card in [self.enabledCard, self.apiKeyCard, self.voiceCard, self.maxCharsCard, self.disableEmojiFilterCard, self.parenthesisFilterCard, self.actionCard]:
            self.apiGroup.addSettingCard(card)
        self.linkGroup.addSettingCard(self.linkCard)
        self.expandLayout.addWidget(self.apiGroup)
        self.expandLayout.addWidget(self.linkGroup)
        self._initializing = False

    def _voice_preview_path(self, voice_value):
        safe_name = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in voice_value)
        return config.DATA_DIR / 'tts_preview' / (safe_name + '.pcm')

    def _preview_text(self, voice_value):
        voice_label = VOICE_VALUE_TO_LABEL.get(voice_value, voice_value)
        preview_name = voice_label.replace(' 2.0', '').replace('2.0', '').strip()
        return '你好呀，我是%s，有什么需要帮助的吗' % preview_name

    def _preview_voice(self):
        if self._initializing or self.preview_worker is not None:
            return
        voice_value = self.voiceCard.currentValue() or config.DEFAULT_TTS_CONFIG['voice_name']
        self.preview_worker = TtsPreviewWorker(self._voice_preview_path(voice_value), parent=self)
        self.preview_worker.result_ready.connect(self._on_preview_result)
        self.preview_worker.start()

    def _on_preview_result(self, success, text):
        self.preview_worker = None
        if not success:
            InfoBar.error('试听失败', text[:120], duration=5000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _collect(self):
        try:
            max_chars = max(1, int(self.maxCharsCard.text() or 500))
        except ValueError:
            max_chars = 500
        try:
            max_length_to_filter_parenthesis = max(0, int(self.parenthesisFilterCard.text() or 0))
        except ValueError:
            max_length_to_filter_parenthesis = 0
        return {
            'enabled': self.enabledCard.isChecked(),
            'api_key': self.apiKeyCard.text(),
            'voice_name': self.voiceCard.currentValue() or config.DEFAULT_TTS_CONFIG['voice_name'],
            'max_chars': max_chars,
            'disable_emoji_filter': self.disableEmojiFilterCard.isChecked(),
            'max_length_to_filter_parenthesis': max_length_to_filter_parenthesis,
        }

    def _save(self):
        config.save_tts_config(self._collect())
        InfoBar.success('保存成功', '语音配置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _test(self):
        cfg = self._collect()
        if not cfg.get('api_key'):
            InfoBar.error('缺少 API Key', '请先填写 API Key', duration=3000, position=InfoBarPosition.BOTTOM, parent=self.window())
            return
        stop_tts()
        self.testBtn.setEnabled(False)
        self.testBtn.setText('播放中...')
        voice_value = cfg['voice_name']
        self.worker = TtsCacheWorker(self._preview_text(voice_value), cfg, self._voice_preview_path(voice_value), parent=self)
        self.worker.result_ready.connect(self._on_test_result)
        self.worker.start()

    def _on_test_result(self, success, text):
        self.testBtn.setEnabled(True)
        self.testBtn.setText('测试连接')
        if success:
            InfoBar.success('测试成功', '语音已播放完成', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())
        else:
            InfoBar.error('测试失败', text[:120], duration=5000, position=InfoBarPosition.BOTTOM, parent=self.window())


class ReplyDisplayPage(MiniPetScrollPage):
    def __init__(self, parent=None):
        super().__init__('回复显示设置', parent)
        cfg = config.typewriter_config
        defaults = config.DEFAULT_TYPEWRITER_CONFIG

        self.displayGroup = SettingCardGroup('AI 回复显示', self.scrollWidget)
        self.enabledCard = SwitchSettingCard(FIF.MESSAGE, 'AI 回复逐字显示', '开启后，AI 回复文字会一字一字显示；关闭后直接显示完整回复', parent=self.displayGroup)
        self.enabledCard.setChecked(bool(cfg.get('enabled', defaults['enabled'])))
        self.speedCard = RangeSettingCard(8, 120, 1, FIF.MESSAGE, '逐字显示速度', '每个字的最大显示间隔，单位毫秒，数值越小越快', self.displayGroup)
        self.speedCard.setValue(int(cfg.get('speed_ms', defaults['speed_ms'])))
        self.maxDurationCard = RangeSettingCard(500, 15000, 1, FIF.FONT_SIZE, '最长显示时长', '单条回复逐字显示的最长时间，单位毫秒', self.displayGroup)
        self.maxDurationCard.setValue(int(cfg.get('max_duration_ms', defaults['max_duration_ms'])))
        self.ttsDelayCard = RangeSettingCard(0, 3000, 1, FIF.VOLUME, '语音播报文字延迟', '开启语音播报时，回复文字延迟显示的时间，单位毫秒', self.displayGroup)
        self.ttsDelayCard.setValue(int(cfg.get('tts_delay_ms', defaults['tts_delay_ms'])))
        self.saveCard = PushSettingCard('保存', FIF.SAVE, '保存回复显示设置', '保存 AI 回复逐字显示相关配置', self.displayGroup)
        self.saveCard.clicked.connect(self._save)

        for card in [self.enabledCard, self.speedCard, self.maxDurationCard, self.ttsDelayCard, self.saveCard]:
            self.displayGroup.addSettingCard(card)
        self.expandLayout.addWidget(self.displayGroup)

    def _collect(self):
        return {
            'enabled': self.enabledCard.isChecked(),
            'speed_ms': int(self.speedCard.value()),
            'max_duration_ms': int(self.maxDurationCard.value()),
            'tts_delay_ms': int(self.ttsDelayCard.value()),
        }

    def _save(self):
        config.save_typewriter_config(self._collect())
        InfoBar.success('保存成功', '回复显示设置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())


class RealtimePage(MiniPetScrollPage):
    def __init__(self, parent=None):
        super().__init__('豆包通话设置', parent)
        cfg = config.realtime_config
        self.apiGroup = SettingCardGroup('豆包 Realtime API', self.scrollWidget)
        self.keyHintCard = SettingCard(FIF.VPN, '认证方式', '豆包通话复用语音设置里的 TTS API Key', self.apiGroup)
        self.speakerCard = ComboSettingCard(REALTIME_VOICE_OPTIONS, FIF.PEOPLE, '音色', 'Realtime 语音回复使用的发音人', self.apiGroup)
        self.speakerCard.setCurrentValue(cfg.get('speaker', config.DEFAULT_REALTIME_CONFIG['speaker']))
        self.systemRoleCard = SettingCard(FIF.MESSAGE, '角色背景', 'O2.0 的 system_role', self.apiGroup)
        self.systemRoleEdit = QPlainTextEdit(self.systemRoleCard)
        self.systemRoleEdit.setPlainText(cfg.get('system_role', ''))
        self._style_editor(self.systemRoleEdit)
        self.systemRoleCard.hBoxLayout.addStretch(1)
        self.systemRoleCard.hBoxLayout.addWidget(self.systemRoleEdit, 0, Qt.AlignRight)
        self.systemRoleCard.hBoxLayout.addSpacing(16)
        self.speakingStyleCard = SettingCard(FIF.CHAT, '说话风格', 'O2.0 的 speaking_style', self.apiGroup)
        self.speakingStyleEdit = QPlainTextEdit(self.speakingStyleCard)
        self.speakingStyleEdit.setPlainText(cfg.get('speaking_style', ''))
        self._style_editor(self.speakingStyleEdit)
        self.speakingStyleCard.hBoxLayout.addStretch(1)
        self.speakingStyleCard.hBoxLayout.addWidget(self.speakingStyleEdit, 0, Qt.AlignRight)
        self.speakingStyleCard.hBoxLayout.addSpacing(16)

        self.actionCard = SettingCard(FIF.SAVE, '保存', '保存豆包通话配置到本地 .env', self.apiGroup)
        self.saveBtn = PrimaryPushButton('保存', self.actionCard)
        self.actionCard.hBoxLayout.addStretch(1)
        self.actionCard.hBoxLayout.addWidget(self.saveBtn, 0, Qt.AlignRight)
        self.actionCard.hBoxLayout.addSpacing(16)
        self.saveBtn.clicked.connect(self._save)

        for card in [self.keyHintCard, self.speakerCard, self.systemRoleCard, self.speakingStyleCard, self.actionCard]:
            self.apiGroup.addSettingCard(card)
        self.expandLayout.addWidget(self.apiGroup)

    def _style_editor(self, editor):
        editor.setFixedSize(520, 80)
        editor.setStyleSheet(
            'QPlainTextEdit{background:#ffffff;border:1px solid #dfe3e8;border-radius:8px;'
            'padding:8px 10px;font-size:14px;color:#1f2328;}'
            'QPlainTextEdit:focus{border:1px solid #8ab4f8;}'
        )

    def _collect(self):
        return {
            'enabled': True,
            'model': config.DEFAULT_REALTIME_CONFIG['model'],
            'speaker': self.speakerCard.currentValue() or config.DEFAULT_REALTIME_CONFIG['speaker'],
            'bot_name': config.DEFAULT_REALTIME_CONFIG['bot_name'],
            'system_role': self.systemRoleEdit.toPlainText().strip(),
            'speaking_style': self.speakingStyleEdit.toPlainText().strip(),
        }

    def _save(self):
        config.save_realtime_config(self._collect())
        InfoBar.success('保存成功', '豆包通话配置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())


class RoleToolsPage(MiniPetScrollPage):
    def __init__(self, parent=None):
        super().__init__('角色资源', parent)
        self.resourceGroup = SettingCardGroup('资源管理', self.scrollWidget)
        self.roleCard = PushSettingCard('打开', _icon('minipet.svg'), '角色资源目录', '角色卡和动画资源放于 res/role 下', self.resourceGroup)
        self.docsCard = PushSettingCard('打开', _icon('document.svg'), '资源编辑文档', '查看原版角色、动作和资源编辑说明', self.resourceGroup)
        self.roleCard.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(config.RES_DIR / 'role'))))
        self.docsCard.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(config.ROOT_DIR / 'docs' / 'art_dev.md'))))
        self.resourceGroup.addSettingCard(self.roleCard)
        self.resourceGroup.addSettingCard(self.docsCard)
        self.expandLayout.addWidget(self.resourceGroup)


class SettingsWindow(FluentWindow):
    settings_changed = Signal()
    pet_changed = Signal(str)
    clear_history_requested = Signal()

    def __init__(self, chat_store=None, memory_store=None):
        super().__init__()
        self.memory_store = memory_store or MemoryStore(config.DATA_DIR / 'memory')
        self.setWindowTitle('miniPet System')
        self.setWindowIcon(QIcon(str(config.avatar_path('pet'))))
        self.resize(1020, 760)
        self._drag_pos = None
        self.installEventFilter(self)
        self.basic = BasicPage(self)
        self.basic.setObjectName('BasicPage')
        self.agent = AgentPage(self)
        self.agent.setObjectName('AgentPage')
        self.llm = LLMPage(self)
        self.llm.setObjectName('LLMPage')
        self.role = RolePage(self.memory_store, self)
        self.role.setObjectName('RolePage')
        self.tts = TTSPage(self)
        self.tts.setObjectName('TTSPage')
        self.reply_display = ReplyDisplayPage(self)
        self.reply_display.setObjectName('ReplyDisplayPage')
        self.realtime = RealtimePage(self)
        self.realtime.setObjectName('RealtimePage')
        self.role_tools = RoleToolsPage(self)
        self.role_tools.setObjectName('RoleToolsPage')
        self.basic.settings_changed.connect(self.settings_changed)
        self.agent.settings_changed.connect(self.settings_changed)
        self.basic.pet_changed.connect(self.pet_changed)
        self.role.clear_history_requested.connect(self.clear_history_requested)
        self.addSubInterface(self.basic, FIF.SETTING, '基础')
        self.addSubInterface(self.agent, FIF.ROBOT, '智能体')
        self.addSubInterface(self.llm, FIF.CLOUD, '大模型')
        self.addSubInterface(self.role, _icon('character.svg'), '角色')
        self.addSubInterface(self.tts, FIF.VOLUME, '语音')
        self.addSubInterface(self.reply_display, FIF.MESSAGE, '回复显示')
        self.addSubInterface(self.realtime, FIF.PHONE, '豆包通话')
        self.addSubInterface(self.role_tools, _icon('minipet.svg'), '角色资源')
        self.navigationInterface.setExpandWidth(180)
        self.navigationInterface.setMinimumExpandWidth(180)
        self.navigationInterface.setCollapsible(False)
        self.navigationInterface.setMenuButtonVisible(False)
        self.navigationInterface.expand(useAni=False)

    def _is_title_drag_area(self, pos):
        return pos.y() <= 56

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            pos = event.position() if obj is self else obj.mapTo(self, event.position().toPoint())
            if self._is_title_drag_area(pos):
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return False
        if event.type() == QEvent.MouseMove and self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            return True
        if event.type() == QEvent.MouseButtonRelease:
            self._drag_pos = None
        return super().eventFilter(obj, event)

    def _install_title_drag_filters(self):
        for child in self.findChildren(QWidget):
            if child.mapTo(self, child.rect().topLeft()).y() <= 56:
                child.installEventFilter(self)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and event.position().y() <= 56:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _keep_navigation_expanded(self):
        self.navigationInterface.setExpandWidth(180)
        self.navigationInterface.setMinimumExpandWidth(180)
        self.navigationInterface.setCollapsible(False)
        self.navigationInterface.setMenuButtonVisible(False)
        self.navigationInterface.expand(useAni=False)

    def showEvent(self, event):
        super().showEvent(event)
        self._keep_navigation_expanded()
        self._install_title_drag_filters()

    def reload_memories(self):
        self.role.reload_memories()

    def reload_history(self):
        pass

    def shutdown(self):
        for page in (self.llm, self.tts):
            for worker_name in ('worker', 'preview_worker'):
                worker = getattr(page, worker_name, None)
                if worker is not None and worker.isRunning():
                    worker.requestInterruption()
                    worker.quit()
                    worker.wait(2000)
                if hasattr(page, worker_name):
                    setattr(page, worker_name, None)

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    def show_window(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self._keep_navigation_expanded()
            self.activateWindow()
