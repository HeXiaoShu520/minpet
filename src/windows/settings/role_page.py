# coding:utf-8
"""角色设定和历史对话设置页面。"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit
from qfluentwidgets import InfoBar, InfoBarPosition, SettingCard, SettingCardGroup
from qfluentwidgets import FluentIcon as FIF

import config
from base_page import MiniPetScrollPage
from widgets.setting_cards import AvatarPathSettingCard, ComboSettingCard, LineEditSettingCard


def _icon(name):
    return QIcon(str(config.RES_DIR / 'icons' / 'system' / name))


class RolePage(MiniPetScrollPage):
    settings_changed = Signal()
    pet_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__('角色设定', parent, save_callback=lambda: self._save())
        cfg = config.llm_config

        self.userGroup = SettingCardGroup('我的设置', self.scrollWidget)
        self.userAvatarCard = AvatarPathSettingCard(FIF.PEOPLE, '我的头像', '聊天窗口中用户消息显示的头像', self.userGroup)
        self.userAvatarCard.setText(config.app_config.get('user_avatar', ''))

        self.petGroup = SettingCardGroup('宠物设置', self.scrollWidget)
        self.petCard = ComboSettingCard(self._pet_model_items(), _icon('homestar.svg'), '宠物模型', '应用启动时加载的角色资源', self.petGroup)
        self.petCard.comboBox.setMinimumWidth(260)
        self.petCard.comboBox.setIconSize(QSize(28, 28))
        self.petCard.setCurrentText(config.app_config.get('default_pet', ''))
        self.petPreview = QLabel(self.petCard)
        self.petPreview.setFixedSize(42, 42)
        self.petPreview.setAlignment(Qt.AlignCenter)
        self.petPreview.setStyleSheet('QLabel{border:1px solid #dcdfe6;border-radius:8px;background:#fff;}')
        self.petCard.hBoxLayout.insertWidget(self.petCard.hBoxLayout.count() - 1, self.petPreview, 0, Qt.AlignRight)
        self.petCard.comboBox.currentTextChanged.connect(self._update_pet_preview)
        self._update_pet_preview()
        self.petNameCard = LineEditSettingCard(_icon('character.svg'), '宠物名字', '回复卡片、聊天窗口和语音通话中显示的名字', placeholder='例如：小呆', parent=self.petGroup)
        self.petNameCard.setText(config.app_config.get('pet_name') or config.current_pet or '')
        self.petAvatarCard = AvatarPathSettingCard(_icon('character.svg'), '宠物头像', '聊天、语音聊天和豆包通话中显示的宠物头像', self.petGroup)
        self.petAvatarCard.setText(config.app_config.get('pet_avatar', ''))
        self.roleCard = SettingCard(_icon('character.svg'), '宠物性格', '定义宠物的性格与说话风格', self.petGroup)
        self.roleEdit = QPlainTextEdit(self.roleCard)
        self.roleEdit.setPlainText(cfg.get('system_prompt', ''))
        self._style_editor(self.roleEdit)
        self.roleCard.hBoxLayout.addStretch(1)
        self.roleCard.hBoxLayout.addWidget(self.roleEdit, 0, Qt.AlignRight)
        self.roleCard.hBoxLayout.addSpacing(16)

        self.userGroup.addSettingCard(self.userAvatarCard)
        self.petGroup.addSettingCard(self.petNameCard)
        self.petGroup.addSettingCard(self.petAvatarCard)
        self.petGroup.addSettingCard(self.petCard)
        self.petGroup.addSettingCard(self.roleCard)
        self.expandLayout.addWidget(self.userGroup)
        self.expandLayout.addWidget(self.petGroup)

    def _pet_model_items(self):
        return [(pet, pet, QIcon(str(config.pet_model_image_path(pet)))) for pet in config.get_pet_list()]

    def _update_pet_preview(self):
        path = config.pet_model_image_path(self.petCard.currentText())
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.petPreview.setPixmap(QPixmap())
            self.petPreview.setText('?')
            return
        self.petPreview.setText('')
        screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        pm = pixmap.scaled(int(38 * dpr), int(38 * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        self.petPreview.setPixmap(pm)

    def _style_editor(self, editor):
        editor.setFixedSize(520, 92)
        editor.setStyleSheet(
            'QPlainTextEdit{background:#ffffff;border:1px solid #dfe3e8;border-radius:8px;'
            'padding:8px 10px;font-size:14px;color:#1f2328;}'
            'QPlainTextEdit:focus{border:1px solid #8ab4f8;}'
        )

    def _save(self):
        old_pet = config.app_config.get('default_pet')
        new_pet = self.petCard.currentText()
        config.app_config.update({
            'default_pet': new_pet,
            'pet_name': self.petNameCard.text(),
            'pet_avatar': self.petAvatarCard.text(),
            'user_avatar': self.userAvatarCard.text(),
        })
        config.save_app_config()
        cfg = dict(config.llm_config)
        cfg['system_prompt'] = self.roleEdit.toPlainText().strip()
        config.save_llm_config(cfg)
        InfoBar.success('保存成功', '角色设置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())
        self.settings_changed.emit()
        if old_pet != new_pet:
            self.pet_changed.emit(new_pet)
