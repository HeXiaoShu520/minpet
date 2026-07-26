# coding:utf-8

from widgets.easter import CoinPopup, DicePopup, FortuneStickPopup, GachaPopup, MagicConchPopup, WoodenFishPopup
from widgets.menus.pet_menus import PetEasterMenu


def show_easter_menu(owner):
    if owner.quick_menu is not None:
        owner.quick_menu.close()
    if owner.easter_menu is not None and owner.easter_menu.isVisible():
        owner.easter_menu.raise_()
        return
    x, y = owner.easter_popup_anchor()
    actions = [
        ('🐚', '魔法海螺', '问一个是/否问题', owner.show_magic_conch),
        ('🎋', '今日求签', '摇一支今日运势', owner.show_fortune),
        ('🎲', '摇骰子', '交给随机数决定', owner.show_dice),
        ('res/icons/easter/coin.png', '抛硬币', '正反之间做选择', owner.show_coin),
        ('📞', '豆包通话', '与豆包实时语音对话', owner.show_doubao_call),
        ('🐟', '电子木鱼', '功德 +1，Bug -1', owner.toggle_wooden_fish),
        ('🎁', '桌宠扭蛋', '胶囊里有今日惊喜', owner.show_gacha),
    ]
    owner.easter_menu = PetEasterMenu(x, y, actions, owner)
    owner.easter_menu.destroyed.connect(lambda: setattr(owner, 'easter_menu', None))


def show_game_popup(owner, attr_name, popup_class):
    current = getattr(owner, attr_name)
    if current is not None and current.isVisible():
        current.raise_()
        return
    x, y = owner.easter_popup_anchor()
    popup = popup_class(x, y, owner)
    popup.destroyed.connect(lambda: setattr(owner, attr_name, None))
    setattr(owner, attr_name, popup)
    owner.pat()


def show_magic_conch(owner):
    show_game_popup(owner, 'magic_conch_popup', MagicConchPopup)


def show_gacha(owner):
    show_game_popup(owner, 'gacha_popup', GachaPopup)


def show_dice(owner):
    show_game_popup(owner, 'dice_popup', DicePopup)


def show_coin(owner):
    show_game_popup(owner, 'coin_popup', CoinPopup)


def show_fortune(owner):
    if owner.fortune_stick_popup is not None and owner.fortune_stick_popup.isVisible():
        owner.fortune_stick_popup.raise_()
        return
    x, y = owner.easter_popup_anchor()
    owner.fortune_stick_popup = FortuneStickPopup(x, y, owner)
    owner.fortune_stick_popup.destroyed.connect(lambda: setattr(owner, 'fortune_stick_popup', None))
    owner.pat()


def toggle_wooden_fish(owner):
    if owner.wooden_fish_popup is not None and owner.wooden_fish_popup.isVisible():
        owner.wooden_fish_popup.close()
        owner.wooden_fish_popup = None
        return
    x, y = owner.easter_popup_anchor()
    owner.wooden_fish_popup = WoodenFishPopup(x, y, owner)
    owner.wooden_fish_popup.destroyed.connect(lambda: setattr(owner, 'wooden_fish_popup', None))
