# coding:utf-8

from PySide6.QtCore import QRect, QSize, Qt

from miniPet import config
from miniPet.pet.animation import AnimationThread


def start_animation(owner):
    owner.anim_thread = AnimationThread(owner.profile, owner)
    owner.anim_thread.worker.image_changed.connect(owner._set_image)
    owner.anim_thread.worker.move_requested.connect(owner._move_by)
    owner.anim_thread.worker.finished.connect(owner._resume_random_animation)
    owner.anim_thread.start()


def stop_animation(owner):
    if owner.anim_thread:
        owner.anim_thread.stop()
        owner.anim_thread = None


def set_image(owner, pixmap, anchor, act=None):
    config.current_image = pixmap
    config.previous_anchor = config.current_anchor
    config.current_anchor = list(anchor or [0, 0])
    scale = float(config.app_config.get('scale', 1.0))
    width = max(1, int(pixmap.width() * scale))
    height = max(1, int(pixmap.height() * scale))
    owner.current_frame_size = QSize(pixmap.width(), pixmap.height())
    if act is not None:
        owner.visible_bounds = act.get_bounds(pixmap, scale)
    else:
        owner.visible_bounds = QRect(0, 0, width, height)
    owner.label.setFixedSize(width, height)
    owner.label.setPixmap(pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    reset_size(owner, keep_position=True, apply_image=False)


def reset_size(owner, keep_position=True, apply_image=True):
    if not owner.profile:
        return
    old_pos = owner.pos()
    scale = float(config.app_config.get('scale', 1.0))
    owner.setFixedSize(max(1, int(owner.profile.width * scale)), max(1, int(owner.profile.height * scale)))
    if keep_position:
        owner._set_current_screen_from_point(owner._pet_reference_point(old_pos.x(), old_pos.y()))
        owner.move(owner._limit_position(old_pos.x(), old_pos.y()))
    else:
        owner.floor_y = owner.current_screen.bottom() - owner.height() + 1
        owner.move(owner.current_screen.center().x() - owner.width() // 2, owner.floor_y)
    if apply_image and config.current_image:
        set_image(owner, config.current_image, config.current_anchor)
    owner._sync_voice_popup_position()


def move_by(owner, dx, dy):
    owner.move(owner._limit_position(owner.x() + dx, owner.y() + dy))
    owner._sync_voice_popup_position()


def resume_random_animation(owner):
    if owner.anim_thread:
        owner.anim_thread.worker.resume()


def play_action(owner, name):
    if not owner.profile or name not in owner.profile.acts:
        return
    if owner.anim_thread:
        owner.anim_thread.worker.play([owner.profile.acts[name]])


def pat(owner):
    act = owner.profile.patpat.get(2) or owner.profile.default
    if owner.anim_thread:
        owner.anim_thread.worker.play([act])
