# coding:utf-8

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon

import config
from widgets.menus.pet_menus import build_pet_context_menu


def setup_tray(owner):
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return
    if not owner.tray:
        owner.tray = QSystemTrayIcon(QIcon(str(config.avatar_path('pet'))), owner)
    owner.tray.setContextMenu(build_menu(owner, include_actions=True))
    owner.tray.show()


def build_menu(owner, include_actions=False):
    owner.context_menu = build_pet_context_menu(owner, include_actions=include_actions)
    return owner.context_menu


def hide_tray(owner):
    if owner.tray:
        owner.tray.hide()
