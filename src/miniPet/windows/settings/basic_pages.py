# coding:utf-8
"""基础设置和智能体设置页面。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel
from qfluentwidgets import InfoBar, InfoBarPosition, SettingCard, SettingCardGroup
from qfluentwidgets import FluentIcon as FIF

from miniPet import config
from miniPet.base_page import MiniPetScrollPage
from miniPet.widgets.setting_cards import AvatarPathSettingCard, ComboSettingCard, LineEditSettingCard


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


class BasicPage(MiniPetScrollPage):
    settings_changed = Signal()
    pet_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__('基本设置', parent, save_callback=lambda: self._save())
        self.personalGroup = SettingCardGroup('个性化', self.scrollWidget)
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

        self.personalGroup.addSettingCard(self.petCard)
        self.personalGroup.addSettingCard(self.petAvatarCard)
        self.personalGroup.addSettingCard(self.userAvatarCard)
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
        super().__init__('智能体设置', parent, save_callback=lambda: self._save())
        cfg = config.app_config
        self.agentGroup = SettingCardGroup('桌宠大脑', self.scrollWidget)
        self.backendCard = ComboSettingCard(self.BACKENDS, FIF.ROBOT, '智能体选项', '选择桌宠输入、语音和投喂交给哪个大脑处理', self.agentGroup)
        self.backendCard.setCurrentValue(cfg.get('agent_backend', 'builtin'))
        self.openclawWsCard = LineEditSettingCard(FIF.LINK, 'OpenClaw Adapter 地址', 'OpenClaw 中转脚本监听的 WebSocket 地址', placeholder='ws://127.0.0.1:18888/ws/pet', parent=self.agentGroup)
        self.openclawWsCard.setText(cfg.get('openclaw_ws_url', 'ws://127.0.0.1:18888/ws/pet'))
        self.customWsCard = LineEditSettingCard(FIF.LINK, '通用 AI 后端地址', '完全体后端的 WebSocket 地址，遵循 miniPet 通用智能体协议', placeholder='ws://127.0.0.1:18889/ws/minipet', parent=self.agentGroup)
        self.customWsCard.setText(cfg.get('custom_agent_ws_url', 'ws://127.0.0.1:18889/ws/minipet'))
        self.noteCard = SettingCard(FIF.MESSAGE, '说明', '内置模式使用”大模型”页配置；OpenClaw 和通用后端模式会通过 WebSocket 双向通信', self.agentGroup)

        for card in [self.backendCard, self.openclawWsCard, self.customWsCard, self.noteCard]:
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


