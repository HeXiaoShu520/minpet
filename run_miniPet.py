# coding:utf-8
import os
import sys

from tendo import singleton
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(APP_DIR, 'src')
os.chdir(APP_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from app import main


if __name__ == '__main__':
    try:
        me = singleton.SingleInstance()
    except Exception:
        sys.exit()

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    main()
