# coding:utf-8
"""通知窗口动画和堆叠常量。"""

from PySide6.QtCore import QPoint

BUBBLE_STACK_GAP = 10
BUBBLE_BASE_GAP = 18
BUBBLE_ENTER_OFFSET = QPoint(0, -14)
BUBBLE_EXIT_OFFSET = QPoint(0, -10)
BUBBLE_ANIM_IN_MS = 220
BUBBLE_ANIM_MOVE_MS = 180
BUBBLE_ANIM_OUT_MS = 180
MAX_STACKED_BUBBLES = 4
SMART_BUBBLE_TIMEOUT_MS = 12000
from qfluentwidgets import CaptionLabel, StrongBodyLabel, TextWrap, TransparentToolButton
from qfluentwidgets import FluentIcon as FIF

from typewriter import Typewriter
from clients.tts_client import stop_tts

import config


