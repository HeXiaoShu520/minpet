# coding:utf-8

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCursor


def start_hover_tracking(owner):
    owner.hover_menu_armed = False
    owner.hover_inside_visible = False
    owner.hover_timer = QTimer(owner)
    owner.hover_timer.setSingleShot(True)
    owner.hover_timer.timeout.connect(lambda: show_quick_menu_from_hover(owner))


def cursor_inside_visible_pet(owner):
    local = owner.mapFromGlobal(QCursor.pos()) - owner.label.pos()
    return owner._current_visible_bounds().contains(local)


def arm_hover_menu_from_cursor(owner):
    if owner.quick_menu is not None:
        return
    if not cursor_inside_visible_pet(owner):
        disarm_hover_menu(owner)
        return
    owner.hover_inside_visible = True
    if owner.hover_menu_armed:
        return
    owner.hover_menu_armed = True
    owner.hover_timer.start(320)


def disarm_hover_menu(owner):
    owner.hover_inside_visible = False
    owner.hover_menu_armed = False
    owner.hover_timer.stop()


def show_quick_menu_from_hover(owner):
    if not owner.hover_menu_armed:
        return
    owner.hover_menu_armed = False
    if cursor_inside_visible_pet(owner):
        owner.show_quick_menu()


def close_quick_menu_if_mouse_away(owner):
    if owner.quick_menu is None:
        return
    cursor = QCursor.pos()
    if owner.geometry().contains(cursor):
        return
    if owner.quick_menu.geometry().contains(cursor):
        return
    owner.quick_menu.close()
