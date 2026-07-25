# coding:utf-8
"""
桌面宠物主窗口和桌面交互组件。

这个文件目前集中放了桌宠窗口相关的 UI：
- PetInputPopup：双击桌宠弹出的快速输入框，支持粘贴/拖入图片。
- PetVoicePopup / VoiceOrbWidget：桌宠旁边的轻量语音聊天状态球。
- DesktopPet：透明桌宠窗口、动画播放、拖拽/掉落、托盘菜单和快捷菜单。

后续如果继续拆文件，优先把输入弹窗和语音球组件拆到独立模块。
"""

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from miniPet import config
from miniPet.pet.desktop_actions import move_by as move_pet_by
from miniPet.pet.desktop_actions import pat as pat_pet
from miniPet.pet.desktop_actions import play_action as play_pet_action
from miniPet.pet.desktop_actions import reset_size as reset_pet_size
from miniPet.pet.desktop_actions import resume_random_animation, set_image as set_pet_image
from miniPet.pet.desktop_actions import start_animation, stop_animation
from miniPet.pet.desktop_easter import show_coin as show_coin_popup
from miniPet.pet.desktop_easter import show_dice as show_dice_popup
from miniPet.pet.desktop_easter import show_easter_menu as show_easter_popup_menu
from miniPet.pet.desktop_easter import show_fortune as show_fortune_popup
from miniPet.pet.desktop_easter import show_fortune_result, show_gacha as show_gacha_popup
from miniPet.pet.desktop_easter import show_magic_conch as show_magic_conch_popup
from miniPet.pet.desktop_easter import toggle_wooden_fish as toggle_wooden_fish_popup
from miniPet.pet.desktop_hover import arm_hover_menu_from_cursor, close_quick_menu_if_mouse_away, disarm_hover_menu, start_hover_tracking
from miniPet.pet.desktop_interactions import drop_payload_from_mime, fall_step, handle_mouse_move, handle_mouse_press, handle_mouse_release, limit_position
from miniPet.pet.desktop_tray import build_menu, hide_tray, setup_tray
from miniPet.pet.desktop_windows import show_chat_window, show_doubao_call_window
from miniPet.pet.pet_assets import load_pet_profile
from miniPet.widgets.pet_input_popup import PetInputPopup
from miniPet.widgets.pet_voice_popup import PetVoicePopup
from miniPet.widgets.menus.pet_menus import PetDropIntentPopup, PetQuickMenu


class DesktopPet(QWidget):
    """桌面宠物主窗口。

    负责透明窗口显示、角色动画、拖拽/掉落、多屏找回、托盘菜单、快捷菜单、
    聊天窗口和豆包通话窗口的打开/关闭。业务请求通过 Qt 信号交给 MiniPetApp，
    避免主窗口直接调用 LLM 或 TTS。
    """

    show_settings = Signal()
    bubble_requested = Signal(str, int, int, int)
    notification_requested = Signal(str, str)
    smart_bubble_requested = Signal(dict, int, int)
    chat_prompt_submitted = Signal(object)
    drop_intent_submitted = Signal(dict, str)
    chat_requested = Signal()
    voice_chat_requested = Signal()
    voice_pause_requested = Signal()
    share_screen_requested = Signal(bool)
    doubao_call_requested = Signal()
    pet_changed = Signal(str)
    quit_requested = Signal()

    def __init__(self, screens, parent=None):
        super().__init__(parent)
        self.screens = screens
        self.current_screen = screens[0].availableGeometry()
        config.screens = screens
        config.current_screen = screens[0]
        self.profile = None
        self.anim_thread = None
        self.chat_window = None
        self.doubao_call_window = None
        self.tray = None
        self.context_menu = None
        self.input_popup = None
        self.voice_popup = None
        self.quick_menu = None
        self._share_screen_active = False
        self._voice_chat_active = False
        self.drop_popup = None
        self.wooden_fish_popup = None
        self.fortune_stick_popup = None
        self.easter_menu = None
        self.magic_conch_popup = None
        self.gacha_popup = None
        self.dice_popup = None
        self.coin_popup = None
        self.right_click_menu_timer = QTimer(self)
        self.right_click_menu_timer.setSingleShot(True)
        self.right_click_menu_timer.timeout.connect(self.show_quick_menu)
        self.suppress_next_right_release_menu = False
        self.current_frame_size = QSize(0, 0)
        self.visible_bounds = QRect()
        self.is_dragging = False
        self.left_pressed = False
        self.was_dragging = False
        self.mouse_drag_pos = QPoint(0, 0)
        self.press_global_pos = QPoint(0, 0)
        self.last_mouse = []
        self.fall_timer = QTimer(self)
        self.fall_timer.timeout.connect(self._fall_step)
        start_hover_tracking(self)
        self._init_window()
        self._init_ui()
        self.load_pet(config.app_config.get('default_pet') or (config.get_pet_list()[0] if config.get_pet_list() else ''))
        self.show()
        self._setup_tray()

    def _init_window(self):
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
        if config.app_config.get('on_top', True):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

    def _init_ui(self):
        self.label = QLabel(self)
        self.label.setMouseTracking(True)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.label.setScaledContents(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label, 0, Qt.AlignBottom | Qt.AlignHCenter)

    def load_pet(self, pet_name):
        if not pet_name:
            return
        self._stop_animation()
        self.profile = load_pet_profile(pet_name)
        config.current_pet = pet_name
        config.app_config['default_pet'] = pet_name
        config.save_app_config()
        self.setWindowTitle('miniPet - ' + pet_name)
        self._set_image(self.profile.default.images[0], self.profile.default.anchor)
        self._reset_size(keep_position=False)
        self._start_animation()
        self._setup_tray()
        self.pet_changed.emit(pet_name)

    def _start_animation(self):
        start_animation(self)

    def _stop_animation(self):
        stop_animation(self)

    def _set_image(self, pixmap, anchor, act=None):
        set_pet_image(self, pixmap, anchor, act=act)

    def _reset_size(self, keep_position=True, set_image=True):
        reset_pet_size(self, keep_position=keep_position, apply_image=set_image)

    def _screen_at_point(self, point):
        screen = QApplication.screenAt(point)
        if screen is not None:
            return screen
        screen = self.screen()
        if screen is not None:
            return screen
        screen = QApplication.primaryScreen()
        if screen is not None:
            return screen
        return self.screens[0] if self.screens else None

    def _pet_reference_point(self, x=None, y=None):
        px = self.x() if x is None else int(x)
        py = self.y() if y is None else int(y)
        return QPoint(px + self.width() // 2, py + self.height())

    def _set_current_screen_from_point(self, point):
        screen = self._screen_at_point(point)
        if screen is not None:
            config.current_screen = screen
            self.current_screen = screen.availableGeometry()
        self.floor_y = self.current_screen.bottom() - self.height() + 1
        return self.current_screen

    def _setup_tray(self):
        setup_tray(self)

    def _build_menu(self, include_actions=False):
        return build_menu(self, include_actions=include_actions)

    def enterEvent(self, event):
        arm_hover_menu_from_cursor(self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        disarm_hover_menu(self)
        QTimer.singleShot(220, lambda: close_quick_menu_if_mouse_away(self))
        super().leaveEvent(event)

    def contextMenuEvent(self, event):
        event.accept()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if drop_payload_from_mime(self, event.mimeData()) is not None:
            event.acceptProposedAction()
            disarm_hover_menu(self)
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        payload = drop_payload_from_mime(self, event.mimeData())
        if payload is None:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        self._show_drop_popup(payload)

    def _show_drop_popup(self, payload):
        if self.drop_popup is not None:
            self.drop_popup.close()
        x, y = self.bubble_anchor()
        self.drop_popup = PetDropIntentPopup(payload, x, y, self)
        self.drop_popup.intent_selected.connect(self.drop_intent_submitted.emit)
        self.drop_popup.destroyed.connect(lambda: setattr(self, 'drop_popup', None))
        self.pat()

    def mousePressEvent(self, event):
        if not handle_mouse_press(self, event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not handle_mouse_move(self, event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not handle_mouse_release(self, event):
            super().mouseReleaseEvent(event)

    def show_easter_menu(self):
        show_easter_popup_menu(self)

    def show_magic_conch(self):
        show_magic_conch_popup(self)

    def show_gacha(self):
        show_gacha_popup(self)

    def show_dice(self):
        show_dice_popup(self)

    def show_coin(self):
        show_coin_popup(self)

    def show_fortune(self):
        show_fortune_popup(self)

    def _show_fortune_result(self, level, text):
        show_fortune_result(self, level, text)

    def toggle_wooden_fish(self):
        toggle_wooden_fish_popup(self)

    def show_quick_menu(self):
        if self.easter_menu is not None:
            self.easter_menu.close()
        if self.quick_menu is not None and self.quick_menu.isVisible():
            self.quick_menu.close()
            return
        x, top_y, bottom_y = self.quick_menu_anchor()
        self.quick_menu = PetQuickMenu(x, top_y, bottom_y, self.show_settings.emit, self.chat_requested.emit, self._on_voice_chat_requested, self.quit, self._on_share_screen_toggle, share_screen_active=self._share_screen_active, voice_chat_active=self._voice_chat_active, parent=self)
        self.quick_menu.destroyed.connect(lambda: setattr(self, 'quick_menu', None))

    def _on_share_screen_toggle(self, checked):
        self._share_screen_active = checked
        self.share_screen_requested.emit(checked)

    def _on_voice_chat_requested(self):
        self.voice_chat_requested.emit()

    def set_voice_chat_active(self, active):
        self._voice_chat_active = bool(active)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            disarm_hover_menu(self)
            self.right_click_menu_timer.stop()
            if self.quick_menu is not None:
                self.quick_menu.close()
            self.ask_pet()
            event.accept()
            return
        if event.button() == Qt.RightButton:
            disarm_hover_menu(self)
            self.suppress_next_right_release_menu = True
            self.right_click_menu_timer.stop()
            if self.quick_menu is not None:
                self.quick_menu.close()
            self.show_easter_menu()
            event.accept()
            return

    def ask_pet(self):
        if self.input_popup is not None and self.input_popup.isVisible():
            self.input_popup.raise_()
            self.input_popup.activateWindow()
            return
        x, y = self.bubble_anchor()
        self.input_popup = PetInputPopup(x, y, self)
        self.input_popup.submitted.connect(self.chat_prompt_submitted.emit)
        self.input_popup.destroyed.connect(lambda: setattr(self, 'input_popup', None))

    def show_voice_popup(self):
        if self.voice_popup is not None and self.voice_popup.isVisible():
            self.voice_popup.raise_()
            return self.voice_popup
        x, y = self.bubble_anchor()
        self.voice_popup = PetVoicePopup(x, y, self)
        self.voice_popup.pause_requested.connect(self.voice_pause_requested.emit)
        self.voice_popup.destroyed.connect(lambda: setattr(self, 'voice_popup', None))
        return self.voice_popup

    def update_voice_popup(self, state, text=''):
        popup = self.show_voice_popup()
        x, y = self.bubble_anchor()
        popup.move_to_anchor(x, y, smooth=False)
        popup.update_state(state, text)

    def close_voice_popup(self):
        if self.voice_popup is not None:
            self.voice_popup.close()
            self.voice_popup = None

    def _fall_step(self):
        fall_step(self)

    def _limit_position(self, x, y):
        return limit_position(self, x, y)

    def _sync_voice_popup_position(self):
        if self.voice_popup is not None and self.voice_popup.isVisible():
            x, y = self.bubble_anchor()
            self.voice_popup.move_to_anchor(x, y, floaty=self.fall_timer.isActive())

    def _move_by(self, dx, dy):
        move_pet_by(self, dx, dy)

    def _resume_random_animation(self):
        resume_random_animation(self)

    def play_action(self, name):
        play_pet_action(self, name)

    def pat(self):
        pat_pet(self)

    def show_chat(self, history=None, append_message=None, content_for_llm=None, system_prompt_builder=None, clear_history_callback=None):
        show_chat_window(self, history=history, append_message=append_message, content_for_llm=content_for_llm, system_prompt_builder=system_prompt_builder, clear_history_callback=clear_history_callback)

    def show_doubao_call(self, append_message=None):
        show_doubao_call_window(self, append_message=append_message)

    def _on_doubao_call_closed(self):
        self.doubao_call_window = None

    def _current_visible_bounds(self):
        return self.visible_bounds if not self.visible_bounds.isNull() else QRect(0, 0, self.width(), self.height())

    def bubble_anchor(self):
        bounds = self._current_visible_bounds()
        center_x = self.x() + self.label.x() + bounds.left() + bounds.width() // 2
        top_y = self.y() + self.label.y() + bounds.top()
        return center_x, top_y + 12

    def quick_menu_anchor(self):
        bounds = self._current_visible_bounds()
        center_x = self.x() + self.label.x() + bounds.left() + bounds.width() // 2
        top_y = self.y() + self.label.y() + bounds.top()
        bottom_y = self.y() + self.label.y() + bounds.bottom()
        return center_x, top_y, bottom_y

    def apply_settings(self):
        self._init_window()
        self.show()
        self._reset_size(keep_position=True)
        self._setup_tray()

    def quit(self):
        self.quit_requested.emit()

    def quit_now(self):
        self._stop_animation()
        hide_tray(self)
        QApplication.quit()

    def closeEvent(self, event):
        self._stop_animation()
        super().closeEvent(event)
