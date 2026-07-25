# coding:utf-8

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QIcon, QMouseEvent
from PySide6.QtWidgets import QWidget
from qfluentwidgets import FluentWindow
from qfluentwidgets import FluentIcon as FIF

from miniPet import config
from miniPet.protocol_test_page import ProtocolTestPage
from miniPet.storage.memory_store import MemoryStore
from miniPet.windows.settings.basic_pages import AgentPage, BasicPage
from miniPet.windows.settings.llm_page import LLMPage
from miniPet.windows.settings.resource_page import RoleToolsPage
from miniPet.windows.settings.role_page import RolePage
from miniPet.windows.settings.voice_pages import DoubaoCallPage, ReplyDisplayPage, TTSPage


def _icon(name):
    return QIcon(str(config.RES_DIR / 'icons' / 'system' / name))


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
        self.doubao_call = DoubaoCallPage(self)
        self.doubao_call.setObjectName('DoubaoCallPage')
        self.role_tools = RoleToolsPage(self)
        self.role_tools.setObjectName('RoleToolsPage')
        self.protocol_test = ProtocolTestPage(self)
        self.protocol_test.setObjectName('ProtocolTestPage')
        self.basic.settings_changed.connect(self.settings_changed)
        self.agent.settings_changed.connect(self.settings_changed)
        self.tts.settings_changed.connect(self.settings_changed)
        self.basic.pet_changed.connect(self.pet_changed)
        self.role.clear_history_requested.connect(self.clear_history_requested)
        self.addSubInterface(self.basic, FIF.SETTING, '基础')
        self.addSubInterface(self.agent, FIF.ROBOT, '智能体')
        self.addSubInterface(self.llm, FIF.CLOUD, '大模型')
        self.addSubInterface(self.role, _icon('character.svg'), '角色')
        self.addSubInterface(self.tts, FIF.VOLUME, '语音')
        self.addSubInterface(self.reply_display, FIF.MESSAGE, '回复显示')
        self.addSubInterface(self.doubao_call, FIF.PHONE, '豆包通话')
        self.addSubInterface(self.role_tools, _icon('minipet.svg'), '角色资源')
        self.addSubInterface(self.protocol_test, FIF.DEVELOPER_TOOLS, '协议测试')
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
