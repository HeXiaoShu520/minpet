# coding:utf-8
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCursor


def start_hover_tracking(owner):
    owner.hover_menu_armed = False
    owner.hover_inside_visible = False
    owner.hover_mouse_trace = []
    owner.hover_trace_timer = QTimer(owner)
    owner.hover_trace_timer.timeout.connect(lambda: sample_hover_mouse_trace(owner))
    owner.hover_trace_timer.start(50)
    owner.hover_timer = QTimer(owner)
    owner.hover_timer.setSingleShot(True)
    owner.hover_timer.timeout.connect(lambda: show_quick_menu_from_hover(owner))


def sample_hover_mouse_trace(owner):
    pos = QCursor.pos()
    now = time.monotonic()
    owner.hover_mouse_trace.append((now, pos))
    owner.hover_mouse_trace = [(t, p) for t, p in owner.hover_mouse_trace if now - t <= 0.45]


def is_horizontal_hover_entry(owner):
    if len(owner.hover_mouse_trace) < 2:
        return False
    now = time.monotonic()
    points = [(t, p) for t, p in owner.hover_mouse_trace if now - t <= 0.35]
    if len(points) < 2:
        return False
    start = points[0][1]
    end = points[-1][1]
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    adx = abs(dx)
    ady = abs(dy)
    return adx >= 18 and adx >= ady * 1.6


def arm_hover_menu_from_cursor(owner):
    local = owner.mapFromGlobal(QCursor.pos()) - owner.label.pos()
    inside = owner._current_visible_bounds().contains(local)
    if not inside:
        disarm_hover_menu(owner)
        return
    if owner.hover_inside_visible:
        return
    owner.hover_inside_visible = True
    if not is_horizontal_hover_entry(owner):
        owner.hover_menu_armed = False
        owner.hover_timer.stop()
        return
    owner.hover_menu_armed = True
    owner.hover_timer.start(600)


def disarm_hover_menu(owner):
    owner.hover_inside_visible = False
    owner.hover_menu_armed = False
    owner.hover_timer.stop()


def show_quick_menu_from_hover(owner):
    if not owner.hover_menu_armed:
        return
    owner.hover_menu_armed = False
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
