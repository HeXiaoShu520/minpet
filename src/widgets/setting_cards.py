# coding:utf-8
"""设置页通用 SettingCard 组件。"""

from pathlib import Path
import shutil

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel
from qfluentwidgets import ComboBox, LineEdit, PrimaryPushButton, SettingCard, Slider

import config


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
    """头像选择卡片。

    设置页只保存头像文件名；用户从任意路径选择图片时，先复制到
    data/avatars，再把文件名写入配置。这样聊天窗口和通知气泡都能通过
    config.avatar_path() 稳定加载头像。
    """

    def __init__(self, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, placeholder='选择 png / jpg / svg 图片', parent=parent)
        self._filename = ''
        self.lineEdit.hide()  # 路径输入框保留底层能力，但 UI 只展示文件名和预览。
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

    def _copy_to_avatar_dir(self, path):
        """复制外部头像到 data/avatars，并返回应保存到配置里的文件名。"""
        source = Path(path)
        if not source.is_file():
            return str(path or '').strip()
        config.AVATARS_DIR.mkdir(parents=True, exist_ok=True)
        dest = config.AVATARS_DIR / source.name
        if source.resolve() != dest.resolve():
            shutil.copy2(source, dest)
        return dest.name

    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window(),
            '选择头像',
            str(config.DATA_DIR),
            '图片文件 (*.png *.jpg *.jpeg *.bmp *.svg);;所有文件 (*)',
        )
        if path:
            self.setText(self._copy_to_avatar_dir(path))

    def _update_preview(self):
        filename = self._filename
        if filename:
            path = config.AVATARS_DIR / filename
            if not path.is_file():
                # 兼容旧配置里保存绝对路径的情况：发现文件存在就迁移到 avatars 目录。
                migrated_name = self._copy_to_avatar_dir(filename)
                if migrated_name != filename:
                    self._filename = migrated_name
                    path = config.AVATARS_DIR / migrated_name
            pixmap = QPixmap(str(path)) if path.is_file() else QPixmap()
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



