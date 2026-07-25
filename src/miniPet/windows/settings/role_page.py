# coding:utf-8
"""角色设定和历史对话设置页面。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPlainTextEdit
from qfluentwidgets import InfoBar, InfoBarPosition, PushSettingCard, SettingCard, SettingCardGroup, SwitchSettingCard
from qfluentwidgets import FluentIcon as FIF

from miniPet import config
from miniPet.base_page import MiniPetScrollPage
from miniPet.widgets.setting_cards import LineEditSettingCard


def _icon(name):
    return QIcon(str(config.RES_DIR / 'icons' / 'system' / name))


class RolePage(MiniPetScrollPage):
    clear_history_requested = Signal()

    def __init__(self, parent=None):
        super().__init__('角色设定', parent, save_callback=lambda: self._save())
        cfg = config.llm_config

        self.roleGroup = SettingCardGroup('角色', self.scrollWidget)
        self.roleCard = SettingCard(_icon('character.svg'), '宠物性格', '定义宠物的性格与说话风格', self.roleGroup)
        self.roleEdit = QPlainTextEdit(self.roleCard)
        self.roleEdit.setPlainText(cfg.get('system_prompt', ''))
        self._style_editor(self.roleEdit)
        self.roleCard.hBoxLayout.addStretch(1)
        self.roleCard.hBoxLayout.addWidget(self.roleEdit, 0, Qt.AlignRight)
        self.roleCard.hBoxLayout.addSpacing(16)

        self.chatRestoreGroup = SettingCardGroup('历史对话', self.scrollWidget)
        rc = config.chat_restore_config
        self.restoreEnabledCard = SwitchSettingCard(FIF.HISTORY, '启动时恢复对话', '上电后自动加载之前的聊天记录作为上下文', parent=self.chatRestoreGroup)
        self.restoreEnabledCard.setChecked(bool(rc.get('enabled', True)))
        self.restoreMaxMsgCard = LineEditSettingCard(FIF.FONT_SIZE, '最多加载条数', '最多恢复多少条历史消息（最新的优先）', placeholder='20', parent=self.chatRestoreGroup)
        self.restoreMaxMsgCard.lineEdit.setFixedWidth(120)
        self.restoreMaxMsgCard.setText(rc.get('max_messages', 20))
        self.restoreMaxDaysCard = LineEditSettingCard(FIF.CALENDAR, '往前追溯天数', '最多往前查找几天的记录（1=仅今天）', placeholder='1', parent=self.chatRestoreGroup)
        self.restoreMaxDaysCard.lineEdit.setFixedWidth(120)
        self.restoreMaxDaysCard.setText(rc.get('max_days', 1))

        self.manageGroup = SettingCardGroup('保存', self.scrollWidget)
        self.clearCard = PushSettingCard('清空', FIF.DELETE, '当前对话', '清空本次运行中的短期上下文', self.manageGroup)
        self.clearCard.clicked.connect(self._clear_history)

        self.roleGroup.addSettingCard(self.roleCard)
        for card in [self.restoreEnabledCard, self.restoreMaxMsgCard, self.restoreMaxDaysCard]:
            self.chatRestoreGroup.addSettingCard(card)
        self.manageGroup.addSettingCard(self.clearCard)
        self.expandLayout.addWidget(self.roleGroup)
        self.expandLayout.addWidget(self.chatRestoreGroup)
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

    def _save(self):
        cfg = dict(config.llm_config)
        cfg['system_prompt'] = self.roleEdit.toPlainText().strip()
        config.save_llm_config(cfg)
        rc = dict(config.chat_restore_config)
        rc['enabled'] = self.restoreEnabledCard.isChecked()
        rc['max_messages'] = self._parse_int_card(self.restoreMaxMsgCard, 20)
        rc['max_days'] = self._parse_int_card(self.restoreMaxDaysCard, 1)
        config.save_chat_restore_config(rc)
        InfoBar.success('保存成功', '角色和对话恢复设置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _clear_history(self):
        self.clear_history_requested.emit()
        InfoBar.success('已清空', '当前对话上下文已清空', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())
