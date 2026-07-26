# coding:utf-8
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

import config
from pet.desktop_hover import arm_hover_menu_from_cursor, disarm_hover_menu


def _image_to_data_url(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, 'PNG')
    return 'data:image/png;base64,' + bytes(data.toBase64()).decode('ascii')


def drop_payload_from_mime(owner, mime):
    if mime is None:
        return None
    if mime.hasUrls():
        items = []
        has_file = False
        for url in mime.urls():
            item = drop_item_from_url(url)
            if item:
                has_file = has_file or item.get('kind') == 'file'
                items.append(item)
        if items:
            kind = 'file' if has_file else 'url'
            return {'kind': kind, 'items': items, 'preview': drop_preview(items)}
    if mime.hasImage():
        image = mime.imageData()
        return {
            'kind': 'image',
            'items': [{'kind': 'image', 'name': '拖入的图片', 'data_url': _image_to_data_url(image)}],
            'preview': '一张图片，可以识别文字、总结或发到飞书。',
        }
    if mime.hasText():
        text = (mime.text() or '').strip()
        if text:
            kind = 'url' if looks_like_url(text) else 'text'
            return {'kind': kind, 'items': [{'kind': kind, 'text': text}], 'preview': text}
    return None


def drop_item_from_url(url):
    if url.isLocalFile():
        path = url.toLocalFile()
        name = Path(path).name or path
        return {'kind': 'file', 'path': path, 'name': name}
    text = url.toString()
    if text:
        return {'kind': 'url', 'url': text, 'name': text}
    return None


def looks_like_url(text):
    lower = text.lower()
    return lower.startswith(('http://', 'https://', 'file://')) or '://' in lower


def drop_preview(items):
    names = [item.get('name') or item.get('url') or item.get('text') or item.get('kind') for item in items[:3]]
    text = '、'.join(names)
    if len(items) > 3:
        text += ' 等 %d 项' % len(items)
    return text


def handle_mouse_press(owner, event):
    if event.button() == Qt.LeftButton:
        owner.hover_inside_visible = True
        disarm_hover_menu(owner)
        owner.left_pressed = True
        owner.was_dragging = False
        owner.mouse_drag_pos = event.globalPos() - owner.pos()
        owner.press_global_pos = event.globalPos()
        owner.last_mouse = [QCursor.pos()]
        event.accept()
        return True
    if event.button() == Qt.RightButton:
        owner.hover_inside_visible = True
        disarm_hover_menu(owner)
        owner.right_click_menu_timer.stop()
        event.accept()
        return True
    return False


def handle_mouse_move(owner, event):
    if not owner.left_pressed:
        if owner.quick_menu is None:
            arm_hover_menu_from_cursor(owner)
        return True
    if not owner.is_dragging and (event.globalPos() - owner.press_global_pos).manhattanLength() >= 6:
        owner.is_dragging = True
        owner.was_dragging = True
        owner.hover_inside_visible = True
        disarm_hover_menu(owner)
        close_interaction_popups(owner)
        owner.right_click_menu_timer.stop()
        owner.fall_timer.stop()
        if owner.anim_thread:
            owner.anim_thread.worker.play([owner.profile.drag])
    if owner.is_dragging:
        owner.move(event.globalPos() - owner.mouse_drag_pos)
        owner._sync_voice_popup_position()
        owner.last_mouse.append(QCursor.pos())
        owner.last_mouse = owner.last_mouse[-4:]
        event.accept()
    return True


def handle_mouse_release(owner, event):
    if event.button() == Qt.RightButton:
        if owner.suppress_next_right_release_menu:
            owner.suppress_next_right_release_menu = False
        owner.right_click_menu_timer.stop()
        event.accept()
        return True
    if event.button() != Qt.LeftButton:
        return False
    owner.left_pressed = False
    if not owner.was_dragging:
        event.accept()
        return True
    owner.is_dragging = False
    update_drag_speed(owner)
    owner._set_current_screen_from_point(owner._pet_reference_point())
    if config.app_config.get('allow_drop', True):
        config.on_floor = False
        if owner.anim_thread:
            owner.anim_thread.worker.play([owner.profile.fall])
        owner.fall_timer.start(16)
    else:
        owner.move(limit_position(owner, owner.x(), owner.y()))
        owner._resume_random_animation()
    event.accept()
    return True


def close_interaction_popups(owner):
    if owner.quick_menu is not None:
        owner.quick_menu.close()
    if owner.easter_menu is not None:
        owner.easter_menu.close()
    if owner.input_popup is not None:
        owner.input_popup.close()


def update_drag_speed(owner):
    if len(owner.last_mouse) < 2:
        return
    p1 = owner.last_mouse[-1]
    p0 = owner.last_mouse[0]
    config.drag_speed_x = (p1.x() - p0.x()) / max(1, len(owner.last_mouse))
    config.drag_speed_y = (p1.y() - p0.y()) / max(1, len(owner.last_mouse))


def limit_position(owner, x, y):
    left = owner.current_screen.left() - owner.width() // 2
    right = owner.current_screen.right() - owner.width() // 2
    top = owner.current_screen.top() - owner.height() // 2
    bottom = owner.floor_y
    return QPoint(max(left, min(int(x), right)), max(top, min(int(y), bottom)))


def fall_step(owner):
    gravity = 0.7
    config.drag_speed_y += gravity
    nx = owner.x() + config.drag_speed_x
    ny = owner.y() + config.drag_speed_y
    screen = QApplication.screenAt(owner._pet_reference_point(nx, ny))
    if screen is not None and screen.availableGeometry() != owner.current_screen:
        owner._set_current_screen_from_point(owner._pet_reference_point(nx, ny))
    limited = limit_position(owner, nx, ny)
    hit_side = limited.x() != int(nx)
    hit_floor = limited.y() >= owner.floor_y
    if hit_side:
        config.drag_speed_x = -config.drag_speed_x * 0.5
    owner.move(limited)
    owner._sync_voice_popup_position()
    if hit_floor:
        owner.fall_timer.stop()
        config.on_floor = True
        config.drag_speed_x = 0
        config.drag_speed_y = 0
        owner._resume_random_animation()
