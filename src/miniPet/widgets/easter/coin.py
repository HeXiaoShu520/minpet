# coding:utf-8
import math
import random
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QPushButton

from miniPet.widgets.easter.base import EasterGamePopup


class CoinPopup(EasterGamePopup):
    title = '抛硬币'

    def __init__(self, x, y, parent=None):
        self.result = random.choice(['正面', '反面'])
        self.coin_y = -50  # 硬币初始位置（屏幕上方）
        self.coin_vy = 0   # 硬币垂直速度
        self.rotation = 0  # 硬币旋转角度（0-360度）
        self.rotation_speed = 28  # 旋转速度
        self.settled = False  # 是否已落定
        super().__init__(x, y, parent)
        self.setFixedSize(280, 408)
        self.move_to_anchor(x, y)

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._animate_coin)
        self.anim_timer.start(16)  # 约60fps

        self.button = QPushButton('重新抛掷', self)
        self.button.setGeometry(86, 334, 108, 32)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setStyleSheet('QPushButton{border:none;border-radius:15px;background:#bd5f86;color:white;font-weight:700;} QPushButton:hover{background:#a84f75;}')
        self.button.clicked.connect(self.toss)
        self.button.show()
        self._play_once('coin_start', 'coin')

    def toss(self):
        self.result = random.choice(['正面', '反面'])
        self.coin_y = -50
        self.coin_vy = 0
        self.rotation = 0
        self.settled = False
        self.started_at = time.monotonic()
        self.played_sounds.discard('coin_land')
        self.played_sounds.discard('coin_start')
        self._play_once('coin_start', 'coin')
        self.update()


    def _animate_coin(self):
        """更新硬币动画"""
        if self.settled:
            return

        # 重力和弹跳物理
        self.coin_vy += 0.8  # 重力加速度
        self.coin_y += self.coin_vy

        # 旋转
        self.rotation += self.rotation_speed
        if self.rotation >= 360:
            self.rotation -= 360

        # 落地检测和弹跳
        target_y = 150  # 落地位置
        if self.coin_y >= target_y:
            self.coin_y = target_y
            if abs(self.coin_vy) > 2:
                self.coin_vy = -self.coin_vy * 0.5  # 弹起，能量损失
                self.rotation_speed *= 0.7  # 旋转减速
            else:
                self.coin_vy = 0
                self.rotation_speed = 0
                # 落定到最终面
                if self.result == '正面':
                    self.rotation = 0
                else:
                    self.rotation = 180
                self.settled = True

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._draw_card(painter, QColor(255, 247, 250, 248), QColor(238, 180, 202, 230))

        # 绘制硬币
        self._draw_coin(painter)

        # 显示结果文字
        if self.settled and self._elapsed() > 0.3:
            self._play_once('coin_land', 'drop')
            painter.setFont(QFont('Microsoft YaHei UI', 12, QFont.Bold))
            painter.setPen(QColor(116, 56, 82))
            painter.drawText(0, 304, self.width(), 24, Qt.AlignCenter, f'结果：{self.result}')

    def _draw_coin(self, painter):
        """绘制二次元风格的硬币"""
        cx = self.width() / 2
        cy = 52 + 126 + self.coin_y

        # 根据旋转角度计算椭圆宽度（模拟3D翻转）
        rotation_rad = math.radians(self.rotation)
        width_scale = abs(math.cos(rotation_rad))
        coin_width = int(80 * width_scale)
        coin_height = 80

        # 判断当前显示正面还是反面
        is_front = (self.rotation % 360) < 180

        # 绘制阴影
        shadow_offset = 8
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(139, 85, 108, 60))
        painter.drawEllipse(int(cx - 45), int(cy + coin_height/2 + shadow_offset), 90, 16)

        if coin_width > 8:  # 只在不是完全侧面时绘制
            # 硬币外圈（金色边框）
            painter.setPen(QPen(QColor(180, 130, 60), 3))
            grad = QLinearGradient(cx - coin_width/2, cy - coin_height/2,
                                  cx + coin_width/2, cy + coin_height/2)
            grad.setColorAt(0, QColor(255, 220, 120))
            grad.setColorAt(0.5, QColor(255, 200, 80))
            grad.setColorAt(1, QColor(220, 170, 90))
            painter.setBrush(grad)
            painter.drawEllipse(int(cx - coin_width/2), int(cy - coin_height/2),
                              coin_width, coin_height)

            # 内圈图案
            inner_width = int(coin_width * 0.7)
            inner_height = int(coin_height * 0.7)
            painter.setPen(QPen(QColor(200, 140, 50), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(int(cx - inner_width/2), int(cy - inner_height/2),
                              inner_width, inner_height)

            # 绘制图案
            painter.setPen(QPen(QColor(180, 110, 40), 2.5))
            if is_front:
                # 正面：星星
                self._draw_star(painter, cx, cy, inner_width * 0.4)
            else:
                # 反面：月亮
                self._draw_moon(painter, cx, cy, inner_width * 0.35)

    def _draw_star(self, painter, cx, cy, size):
        """绘制五角星"""
        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF
        points = []
        for i in range(5):
            angle = math.radians(i * 72 - 90)
            points.append(QPointF(cx + size * math.cos(angle),
                                cy + size * math.sin(angle)))
            angle2 = math.radians(i * 72 - 90 + 36)
            points.append(QPointF(cx + size * 0.4 * math.cos(angle2),
                                cy + size * 0.4 * math.sin(angle2)))
        painter.setBrush(QColor(200, 130, 50))
        painter.drawPolygon(QPolygonF(points))

    def _draw_moon(self, painter, cx, cy, size):
        """绘制月牙"""
        painter.setBrush(QColor(200, 130, 50))
        painter.drawEllipse(int(cx - size), int(cy - size), int(size * 2), int(size * 2))
        painter.setBrush(QColor(255, 200, 80))
        painter.drawEllipse(int(cx - size * 0.5), int(cy - size),
                          int(size * 2), int(size * 2))
