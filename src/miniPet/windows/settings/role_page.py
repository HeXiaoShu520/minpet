# coding:utf-8
"""角色设定、自动总结和记忆管理页面。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout
from qfluentwidgets import ComboBox, InfoBar, InfoBarPosition, LineEdit, PrimaryPushButton, PushSettingCard, SettingCard, SettingCardGroup, SwitchSettingCard
from qfluentwidgets import FluentIcon as FIF

from miniPet import config
from miniPet.base_page import MiniPetScrollPage
from miniPet.storage.memory_store import CATEGORY_LABELS, MEMORY_CATEGORIES, MemoryStore
from miniPet.widgets.setting_cards import LineEditSettingCard


def _icon(name):
    return QIcon(str(config.RES_DIR / 'icons' / 'system' / name))


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
        super().__init__('角色设定', parent, save_callback=lambda: self._save())
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
        self.clearCard = PushSettingCard('清空', FIF.DELETE, '当前对话', '清空本次运行中的短期上下文，不删除已总结的重点', self.manageGroup)
        self.clearCard.clicked.connect(self._clear_history)

        self.roleGroup.addSettingCard(self.roleCard)
        self.roleGroup.addSettingCard(self.memoryCard)
        for card in [self.autoMemoryCard, self.memoryEveryCard, self.memoryRecentCard, self.memoryMaxItemsCard]:
            self.autoMemoryGroup.addSettingCard(card)
        self.reload_memories()
        for card in [self.restoreEnabledCard, self.restoreMaxMsgCard, self.restoreMaxDaysCard]:
            self.chatRestoreGroup.addSettingCard(card)
        self.manageGroup.addSettingCard(self.clearCard)
        self.expandLayout.addWidget(self.roleGroup)
        self.expandLayout.addWidget(self.autoMemoryGroup)
        self.expandLayout.addWidget(self.memoryListGroup)
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
        rc = dict(config.chat_restore_config)
        rc['enabled'] = self.restoreEnabledCard.isChecked()
        rc['max_messages'] = self._parse_int_card(self.restoreMaxMsgCard, 20)
        rc['max_days'] = self._parse_int_card(self.restoreMaxDaysCard, 1)
        config.save_chat_restore_config(rc)
        InfoBar.success('保存成功', '角色、自动总结和对话恢复设置已保存', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())

    def _clear_history(self):
        self.clear_history_requested.emit()
        InfoBar.success('已清空', '当前对话上下文已清空', duration=2000, position=InfoBarPosition.BOTTOM, parent=self.window())


