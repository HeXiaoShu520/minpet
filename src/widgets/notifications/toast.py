# coding:utf-8
"""右下角系统 Toast。"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, StrongBodyLabel, TransparentToolButton
from qfluentwidgets import FluentIcon as FIF

import config

class Toast(QWidget):
    """右下角普通系统提示窗口。"""

    closed = Signal(str)

    def __init__(self, note_id, title, message, icon=None, timeout=5000, parent=None):
        super().__init__(parent)
        self.note_id = note_id
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        frame = QFrame()
        frame.setStyleSheet('''
            QFrame { border: 1px solid #202020; border-radius: 6px; background: white; }
            QLabel { border: 0; background: transparent; color: black; }
        ''')
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        if icon and not icon.isNull():
            icon_label = QLabel()
            screen = QApplication.primaryScreen()
            dpr = screen.devicePixelRatio() if screen else 1.0
            pm = icon.scaled(int(28 * dpr), int(28 * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            icon_label.setPixmap(pm)
            layout.addWidget(icon_label)
        text_box = QVBoxLayout()
        title_label = StrongBodyLabel(title or config.APP_DISPLAY_NAME)
        msg_label = CaptionLabel(message or '')
        msg_label.setWordWrap(True)
        msg_label.setMaximumWidth(260)
        text_box.addWidget(title_label)
        text_box.addWidget(msg_label)
        layout.addLayout(text_box, 1)
        close_btn = TransparentToolButton(FIF.CLOSE)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close)
        self.timer.start(timeout)
        self.adjustSize()

    def show_at(self, offset):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 24, screen.bottom() - self.height() - 24 - offset)
        self.show()

    def closeEvent(self, event):
        self.closed.emit(self.note_id)
        super().closeEvent(event)


