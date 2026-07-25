# coding:utf-8
"""角色设定和历史对话设置页面。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPlainTextEdit
from qfluentwidgets import InfoBar, InfoBarPosition, SettingCard, SettingCardGroup

from miniPet import config
from miniPet.base_page import MiniPetScrollPage


def _icon(name):
    return QIcon(str(config.RES_DIR / 'icons' / 'system' / name))


class RolePage(MiniPetScrollPage):
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

        self.roleGroup.addSettingCard(self.roleCard)
        self.expandLayout.addWidget(self.roleGroup)

    def _style_editor(self, editor):
        editor.setFixedSize(520, 92)
        editor.setStyleSheet(
            'QPlainTextEdit{background:#ffffff;border:1px solid #dfe3e8;border-radius:8px;'
            'padding:8px 10px;font-size:14px;color:#1f2328;}'
            'QPlainTextEdit:focus{border:1px solid #8ab4f8;}'
        )

    def _save(self):
        cfg = dict(config.llm_config)
        cfg['system_prompt'] = self.roleEdit.toPlainText().strip()
        config.save_llm_config(cfg)
        InfoBar.success('保存成功', '角色设置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())
