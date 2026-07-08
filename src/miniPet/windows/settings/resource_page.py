# coding:utf-8
"""角色资源设置页。"""

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from qfluentwidgets import PushSettingCard, SettingCardGroup

from miniPet import config
from miniPet.base_page import MiniPetScrollPage


def _icon(name):
    return QIcon(str(config.RES_DIR / 'icons' / 'system' / name))


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


