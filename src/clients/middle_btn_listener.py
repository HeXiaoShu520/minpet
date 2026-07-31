# coding:utf-8
"""全局鼠标中键监听器。"""

from PySide6.QtCore import QMetaObject, QObject, Qt, Signal, Slot

try:
    from pynput import mouse as _pynput_mouse
    _PYNPUT_OK = True
except Exception:
    _PYNPUT_OK = False


class MiddleButtonListener(QObject):
    """在后台线程监听全局鼠标中键按下，每次按下发射 toggled 信号（主线程安全）。"""

    toggled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener = None

    def start(self):
        if not _PYNPUT_OK:
            return
        if self._listener is not None:
            return
        try:
            self._listener = _pynput_mouse.Listener(on_click=self._on_click)
            self._listener.start()
        except Exception as e:
            print('MiddleButtonListener start error:', e)
            self._listener = None

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _on_click(self, x, y, button, pressed):
        if pressed and button == _pynput_mouse.Button.middle:
            QMetaObject.invokeMethod(self, 'emit_toggled', Qt.QueuedConnection)

    @Slot()
    def emit_toggled(self):
        self.toggled.emit()
