# coding:utf-8
import math
import random
import struct
import time
import wave

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QPoint, QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QKeyEvent, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QLineEdit, QPushButton
from PySide6.QtWebEngineWidgets import QWebEngineView

from miniPet import config
from miniPet.llm_client import ChatWorker


class EasterGamePopup(QFrame):
    title = '小游戏'
    life_ms = 9000
    _sound_cache = {}

    def __init__(self, x, y, parent=None):
        super().__init__(parent)
        self.started_at = time.monotonic()
        self.dragging = False
        self.drag_start_pos = QPoint()
        self.drag_window_pos = QPoint()
        self.fade_anim = None
        self.played_sounds = set()
        self.sound_effects = {}
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(280, 260)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(16)
        self.life_timer = QTimer(self)
        self.life_timer.setSingleShot(True)
        self.life_timer.timeout.connect(self.close)
        # 彩蛋小铺的小游戏由用户右键关闭，不自动消失。
        self.move_to_anchor(x, y)
        self.show()
        self.raise_()
        self._fade_in()

    def move_to_anchor(self, x, y):
        screen = QApplication.screenAt(QPoint(int(x), int(y))) or QApplication.primaryScreen()
        pos = QPoint(int(x - self.width() / 2), int(y - self.height() - 18))
        if screen is not None:
            area = screen.availableGeometry()
            pos.setX(max(area.left() + 4, min(pos.x(), area.right() - self.width() - 4)))
            pos.setY(max(area.top() + 4, min(pos.y(), area.bottom() - self.height() - 4)))
        self.move(pos)

    def _fade_in(self):
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b'windowOpacity', self)
        anim.setDuration(160)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self.fade_anim = anim

    def _tick(self):
        self.update()

    def _play_once(self, key, kind):
        if key in self.played_sounds:
            return
        self.played_sounds.add(key)
        self._play_sound(kind)

    def _play_sound(self, kind):
        path = self._ensure_sound(kind)
        if path is None:
            return
        effect = QSoundEffect(self)
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.setVolume(float(config.app_config.get('volume', 0.4)))
        effect.play()
        self.sound_effects[kind + str(time.monotonic())] = effect

    def _ensure_sound(self, kind):
        if kind in self._sound_cache:
            return self._sound_cache[kind]
        sound_dir = config.RES_DIR / 'sounds' / 'easter'
        sound_dir.mkdir(parents=True, exist_ok=True)
        path = sound_dir / f'{kind}.wav'
        if not path.is_file():
            self._write_sound(path, kind)
        self._sound_cache[kind] = path
        return path

    def _write_sound(self, path, kind):
        sample_rate = 44100
        duration = {
            'click': 0.08, 'tick': 0.05, 'drop': 0.16, 'open': 0.32,
            'coin': 0.55, 'dice': 0.42, 'mystic': 0.8,
        }.get(kind, 0.18)
        total = int(sample_rate * duration)
        frames = bytearray()
        for i in range(total):
            t = i / sample_rate
            if kind == 'coin':
                env = math.exp(-4.0 * t)
                freq = 1050 + 800 * math.sin(t * 48)
                sample = math.sin(2 * math.pi * freq * t) * env * 0.33
            elif kind == 'dice':
                env = math.exp(-7.0 * t)
                noise = random.uniform(-1, 1) * env * 0.22
                sample = noise + math.sin(2 * math.pi * 140 * t) * env * 0.18
            elif kind == 'drop':
                env = math.exp(-16 * t)
                sample = (math.sin(2 * math.pi * 150 * t) + random.uniform(-0.5, 0.5)) * env * 0.32
            elif kind == 'open':
                env = math.exp(-5 * t)
                sample = (math.sin(2 * math.pi * 660 * t) + 0.5 * math.sin(2 * math.pi * 990 * t)) * env * 0.24
            elif kind == 'mystic':
                env = min(1.0, t * 5) * math.exp(-1.4 * t)
                sample = (math.sin(2 * math.pi * 330 * t) + 0.45 * math.sin(2 * math.pi * 495 * t)) * env * 0.20
            elif kind == 'tick':
                env = math.exp(-80 * t)
                sample = math.sin(2 * math.pi * 1800 * t) * env * 0.36
            else:
                env = math.exp(-55 * t)
                sample = math.sin(2 * math.pi * 900 * t) * env * 0.34
            frames.extend(struct.pack('<h', int(max(-1, min(1, sample)) * 32767)))
        with wave.open(str(path), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(bytes(frames))

    def _elapsed(self):
        return time.monotonic() - self.started_at

    def _ease_out(self, t):
        t = max(0.0, min(1.0, t))
        return 1 - pow(1 - t, 3)

    def _ease_in_out(self, t):
        t = max(0.0, min(1.0, t))
        return t * t * (3 - 2 * t)

    def _spring(self, t, damping=5.5, frequency=13.0):
        t = max(0.0, t)
        return math.exp(-damping * t) * math.cos(frequency * t)

    def _impact(self, t, duration=0.32):
        if t < 0 or t > duration:
            return 0.0
        p = t / duration
        return math.sin(p * math.pi) * math.exp(-3.0 * p)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.close()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self.childAt(event.pos()) is None:
            self.dragging = True
            self.drag_start_pos = event.globalPos()
            self.drag_window_pos = self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            self.move(self.drag_window_pos + event.globalPos() - self.drag_start_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _draw_card(self, painter, bg=QColor(255, 250, 238, 246), border=QColor(225, 205, 165, 230)):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(80, 54, 24, 35))
        painter.drawRoundedRect(18, 20, self.width() - 36, self.height() - 30, 22, 22)
        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.5))
        painter.drawRoundedRect(14, 14, self.width() - 28, self.height() - 32, 22, 22)
        painter.setFont(QFont('Microsoft YaHei UI', 13, QFont.Bold))
        painter.setPen(QColor(92, 59, 24, 230))
        painter.drawText(0, 26, self.width(), 26, Qt.AlignCenter, self.title)

    def closeEvent(self, event):
        self.anim_timer.stop()
        self.life_timer.stop()
        super().closeEvent(event)


class MagicConchPopup(EasterGamePopup):
    title = '魔法海螺'
    life_ms = 0
    ANSWERS = [
        '可以。', '不可以。', '也许吧。', '再问一次。', '现在还不是时候。', '海螺不知道。',
        '当然。', '别想了，去做。', '先保存再说。', '答案已经很明显了。'
    ]

    def __init__(self, x, y, parent=None):
        self.answer = ''
        self.question = ''
        self.ask_started_at = 0.0
        self.worker = None
        self.waiting_llm = False
        super().__init__(x, y, parent)
        self.setFixedSize(360, 360)
        self.input = QLineEdit(self)
        self.input.setAttribute(Qt.WA_MacShowFocusRect, False)
        self.input.setPlaceholderText('问海螺一个问题...')
        self.input.setGeometry(42, 274, 206, 34)
        self.input.setStyleSheet('QLineEdit{border:1px solid rgba(112,153,210,180);border-radius:14px;padding:6px 10px;background:rgba(255,255,255,230);color:#28486c;font-size:12px;} QLineEdit:focus{border:1px solid #5b91dc;}')
        self.input.returnPressed.connect(self.ask)
        self.button = QPushButton('问', self)
        self.button.setGeometry(256, 274, 58, 34)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setStyleSheet('QPushButton{border:none;border-radius:14px;background:#5f92dc;color:white;font-weight:700;} QPushButton:hover{background:#4d82ce;}')
        self.button.clicked.connect(self.ask)
        self.input.show()
        self.button.show()
        self.input.setFocus(Qt.OtherFocusReason)
        self.activateWindow()

    def ask(self):
        question = self.input.text().strip()
        if not question:
            return
        self._play_sound('mystic')
        self.question = question
        self.answer = ''
        self.ask_started_at = time.monotonic()
        self.waiting_llm = True
        self.input.hide()
        self.button.hide()
        messages = [
            {'role': 'system', 'content': '你是桌宠里的神奇海螺。用户会问一个问题。你必须用中文回答，只给一句短答案，像神奇海螺一样神秘、笃定、可爱。不要解释，不要超过18个字。'},
            {'role': 'user', 'content': question},
        ]
        self.worker = ChatWorker(messages, parent=self)
        self.worker.result_ready.connect(self._answer_ready)
        self.worker.start()
        self.update()

    def _answer_ready(self, ok, text):
        if ok and text.strip():
            self.answer = text.strip().replace('\n', ' ')[:36]
        else:
            self.answer = random.choice(self.ANSWERS)
        self.waiting_llm = False
        self.update()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        self._draw_card(painter, QColor(238, 247, 255, 250), QColor(128, 178, 238, 230))
        elapsed = self._elapsed()
        asked = self.ask_started_at > 0.0
        ask_elapsed = time.monotonic() - self.ask_started_at if asked else 0.0
        listening = asked and (self.waiting_llm or ask_elapsed < 1.45)
        reveal = self._ease_out((ask_elapsed - 1.45) / 0.55) if asked and self.answer else 0.0
        pulse = (math.sin(elapsed * 7) + 1) / 2
        wobble_amp = 7 if listening else 2.2
        wobble = math.sin(elapsed * 10) * wobble_amp
        cx, cy = self.width() / 2, 136 + wobble

        painter.setPen(Qt.NoPen)
        for i in range(4):
            alpha = int((70 - i * 12) * (0.35 + pulse * 0.65))
            painter.setBrush(QColor(128, 166, 255, alpha))
            r = 62 + i * 16 + pulse * 10
            painter.drawEllipse(QPoint(int(cx), int(cy)), int(r), int(r * 0.56))
        self._draw_magic_sparkles(painter, cx, cy, elapsed, listening)
        self._draw_shell(painter, cx, cy, elapsed, listening)

        if not asked:
            painter.setFont(QFont('Microsoft YaHei UI', 9, QFont.Bold))
            painter.setPen(QColor(67, 95, 142, 205))
            painter.drawText(0, 232, self.width(), 22, Qt.AlignCenter, '像神奇海螺一样，先问一个问题')
            return

        if listening:
            dots = '.' * (1 + int(ask_elapsed * 4) % 3)
            painter.setFont(QFont('Microsoft YaHei UI', 10, QFont.Bold))
            painter.setPen(QColor(67, 95, 142, 205))
            painter.drawText(0, 258, self.width(), 26, Qt.AlignCenter, f'海螺正在聆听宇宙的回响{dots}')
            return

        painter.setOpacity(reveal)
        painter.setPen(QPen(QColor(102, 146, 205, 150), 1))
        painter.setBrush(QColor(255, 255, 255, 226))
        box = QRectF(30, 232, self.width() - 60, 92)
        painter.drawRoundedRect(box, 15, 15)
        painter.setFont(QFont('Microsoft YaHei UI', 8))
        painter.setPen(QColor(77, 105, 145, 190))
        painter.drawText(46, 240, self.width() - 92, 18, Qt.AlignCenter, '你问：' + self.question[:24])
        font = QFont('Microsoft YaHei UI', 11, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(42, 69, 108))
        metrics = painter.fontMetrics()
        answer = '海螺说：' + self.answer
        answer_rect = QRectF(42, 262, self.width() - 84, 48)
        if metrics.boundingRect(answer_rect.toRect(), Qt.AlignCenter | Qt.TextWordWrap, answer).height() > answer_rect.height():
            font.setPointSize(10)
            painter.setFont(font)
        painter.drawText(answer_rect, Qt.AlignCenter | Qt.TextWordWrap, answer)
        painter.setOpacity(1)

    def _draw_magic_sparkles(self, painter, cx, cy, elapsed, listening):
        painter.save()
        painter.setPen(Qt.NoPen)
        points = [(-92, -34, 2.0), (-66, 42, 1.4), (-18, -58, 1.8), (46, -48, 1.5), (96, -10, 2.1), (72, 50, 1.3)]
        for i, (dx, dy, size) in enumerate(points):
            twinkle = (math.sin(elapsed * (3.2 + i * 0.37) + i) + 1) / 2
            alpha = int((70 + 120 * twinkle) * (1.25 if listening else 0.75))
            painter.setBrush(QColor(130, 170, 255, max(0, min(220, alpha))))
            x = cx + dx + math.sin(elapsed * 1.5 + i) * 3
            y = cy + dy + math.cos(elapsed * 1.3 + i) * 2
            r = size + twinkle * 1.5
            painter.drawEllipse(QPoint(int(x), int(y)), int(r), int(r))
            painter.setPen(QPen(QColor(255, 255, 255, alpha), 1.2))
            painter.drawLine(int(x - r * 2.0), int(y), int(x + r * 2.0), int(y))
            painter.drawLine(int(x), int(y - r * 2.0), int(x), int(y + r * 2.0))
            painter.setPen(Qt.NoPen)
        painter.restore()

    def _draw_shell(self, painter, cx, cy, elapsed, listening):
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(math.sin(elapsed * 4) * (3 if listening else 0.8))
        painter.scale(0.82, 0.82)

        painter.setPen(Qt.NoPen)
        shadow = QRadialGradient(10, 58, 132)
        shadow.setColorAt(0, QColor(35, 45, 75, 62))
        shadow.setColorAt(1, QColor(35, 45, 75, 0))
        painter.setBrush(shadow)
        painter.drawEllipse(QRectF(-144, 30, 288, 58))

        tail_grad = QLinearGradient(-150, -42, 22, 60)
        tail_grad.setColorAt(0, QColor(224, 221, 252))
        tail_grad.setColorAt(0.45, QColor(216, 187, 232))
        tail_grad.setColorAt(1, QColor(166, 143, 203))
        painter.setBrush(tail_grad)
        painter.setPen(QPen(QColor(55, 48, 73), 2.8))
        tail = QPainterPath()
        tail.moveTo(-150, 0)
        tail.cubicTo(-124, -42, -64, -62, -8, -38)
        tail.cubicTo(24, -24, 28, 4, 6, 28)
        tail.cubicTo(-22, 58, -90, 62, -130, 34)
        tail.cubicTo(-142, 26, -150, 12, -150, 0)
        painter.drawPath(tail)

        painter.setPen(QPen(QColor(102, 82, 137, 165), 2.2))
        for x, y, w, h in [(-132, -14, 48, 42), (-108, -31, 62, 66), (-76, -42, 74, 84), (-38, -40, 78, 90)]:
            painter.drawArc(x, y, w, h, 72 * 16, 210 * 16)

        painter.setBrush(QColor(247, 226, 250))
        painter.setPen(QPen(QColor(105, 78, 126), 1.8))
        for x, y, r in [(-120, 9, 8), (-98, -13, 10), (-76, 17, 11), (-52, -19, 12), (-28, 16, 12)]:
            bump = QPainterPath()
            bump.moveTo(x - r, y + r * 0.25)
            bump.cubicTo(x - r * 0.7, y - r * 1.2, x + r * 0.7, y - r * 1.2, x + r, y + r * 0.25)
            bump.cubicTo(x + r * 0.42, y + r, x - r * 0.42, y + r, x - r, y + r * 0.25)
            painter.drawPath(bump)

        body_grad = QLinearGradient(-36, -68, 148, 82)
        body_grad.setColorAt(0, QColor(255, 241, 253))
        body_grad.setColorAt(0.36, QColor(241, 190, 230))
        body_grad.setColorAt(0.72, QColor(218, 148, 207))
        body_grad.setColorAt(1, QColor(175, 105, 174))
        painter.setBrush(body_grad)
        painter.setPen(QPen(QColor(48, 42, 61), 3.0))
        body = QPainterPath()
        body.moveTo(-34, -12)
        body.cubicTo(-8, -54, 42, -70, 78, -48)
        body.cubicTo(114, -26, 142, 6, 158, 40)
        body.cubicTo(170, 72, 132, 92, 76, 84)
        body.cubicTo(26, 77, -18, 58, -48, 36)
        body.cubicTo(-64, 23, -56, 2, -34, -12)
        painter.drawPath(body)

        lip_grad = QLinearGradient(18, -52, 130, 72)
        lip_grad.setColorAt(0, QColor(255, 232, 250, 225))
        lip_grad.setColorAt(0.55, QColor(217, 150, 209, 210))
        lip_grad.setColorAt(1, QColor(143, 94, 158, 205))
        painter.setBrush(lip_grad)
        painter.setPen(QPen(QColor(86, 61, 100), 2.5))
        lip = QPainterPath()
        lip.moveTo(36, -42)
        lip.cubicTo(76, -48, 124, -16, 144, 28)
        lip.cubicTo(158, 60, 130, 76, 90, 70)
        lip.cubicTo(54, 64, 26, 42, 16, 18)
        lip.cubicTo(8, -4, 14, -34, 36, -42)
        painter.drawPath(lip)

        inner_grad = QRadialGradient(88, 24, 56)
        inner_grad.setColorAt(0, QColor(42, 38, 58))
        inner_grad.setColorAt(0.62, QColor(92, 66, 116))
        inner_grad.setColorAt(1, QColor(182, 126, 188))
        painter.setBrush(inner_grad)
        painter.setPen(QPen(QColor(57, 44, 72), 2.2))
        inner = QPainterPath()
        inner.moveTo(64, -18)
        inner.cubicTo(91, -23, 120, 6, 124, 36)
        inner.cubicTo(108, 56, 72, 54, 54, 28)
        inner.cubicTo(46, 10, 48, -10, 64, -18)
        painter.drawPath(inner)

        painter.setPen(QPen(QColor(255, 247, 255, 190), 4.2))
        painter.drawArc(-26, -48, 112, 86, 75 * 16, 82 * 16)
        painter.drawArc(-8, 10, 132, 70, 210 * 16, 72 * 16)
        painter.setPen(QPen(QColor(143, 96, 160, 135), 2.1))
        for x in [-18, 10, 38, 66, 94]:
            line = QPainterPath()
            line.moveTo(x, -36)
            line.cubicTo(x + 12, -8, x + 9, 28, x - 8, 64)
            painter.drawPath(line)

        painter.restore()


class DailyTipPopup(EasterGamePopup):
    title = '每日小技巧'
    TIPS = [
        ('Git', 'git commit --fixup 可以配合 rebase --autosquash 自动整理提交。'),
        ('Python', 'pathlib.Path 比 os.path 更适合写现代路径处理代码。'),
        ('PySide', '频繁动画用 QTimer 控制 repaint，比反复创建动画对象更稳。'),
        ('Debug', '先写一个最小复现，再猜原因，速度通常更快。'),
        ('VS Code', 'Ctrl+Shift+L 可以同时选中所有匹配项批量编辑。'),
        ('正则', '非贪婪匹配用 *? 或 +?，适合截取最近的闭合片段。'),
        ('架构', '先让数据流清楚，再考虑抽象；抽象太早容易变成负担。'),
    ]

    def __init__(self, x, y, parent=None):
        self.kind, self.tip = random.choice(self.TIPS)
        super().__init__(x, y, parent)

    def paintEvent(self, event):
        painter = QPainter(self)
        self._draw_card(painter, QColor(248, 255, 246, 248), QColor(178, 222, 169, 230))
        elapsed = self._elapsed()
        p = self._ease_out(min(1, elapsed / 0.7))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(96, 181, 122, 220))
        painter.drawRoundedRect(68, int(76 - 12 * (1 - p)), 144, 34, 17, 17)
        painter.setFont(QFont('Microsoft YaHei UI', 12, QFont.Bold))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(68, int(82 - 12 * (1 - p)), 144, 24, Qt.AlignCenter, self.kind)
        painter.setFont(QFont('Microsoft YaHei UI', 10))
        painter.setPen(QColor(48, 82, 56))
        painter.drawText(34, 130, self.width() - 68, 82, Qt.AlignCenter | Qt.TextWordWrap, self.tip)


class DicePopup(EasterGamePopup):
    title = '摇骰子'

    def __init__(self, x, y, parent=None):
        self.value = random.randint(1, 6)
        self.final_transform = self._final_transform()
        super().__init__(x, y, parent)
        self.setFixedSize(280, 300)
        self.move_to_anchor(x, y)
        self.web = QWebEngineView(self)
        self.web.setGeometry(34, 58, 212, 158)
        self.web.setContextMenuPolicy(Qt.NoContextMenu)
        self.web.setStyleSheet('background: #fff7fa; border: none;')
        self.web.page().setBackgroundColor(QColor(255, 247, 250))
        self.web.setHtml(self._html(self.value))
        self.web.show()
        self.web.raise_()
        self.button = QPushButton('重新投掷', self)
        self.button.setGeometry(86, 252, 108, 32)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setStyleSheet('QPushButton{border:none;border-radius:15px;background:#bd5f86;color:white;font-weight:700;} QPushButton:hover{background:#a84f75;}')
        self.button.clicked.connect(self.roll)
        self.button.show()
        self._play_once('dice_start', 'dice3d')

    def roll(self):
        self.value = random.randint(1, 6)
        self.final_transform = self._final_transform()
        self.started_at = time.monotonic()
        self.played_sounds.discard('dice_land')
        self.played_sounds.discard('dice_start')
        self.web.setHtml(self._html(self.value))
        self._play_once('dice_start', 'dice3d')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        self._draw_card(painter, QColor(255, 247, 250, 248), QColor(238, 180, 202, 230))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(105, 55, 82, 34))
        painter.drawEllipse(QRectF(88, 198, 104, 14))
        elapsed = self._elapsed()
        if elapsed > 1.18:
            self._play_once('dice_land', 'drop')
            painter.setFont(QFont('Microsoft YaHei UI', 12, QFont.Bold))
            painter.setPen(QColor(116, 56, 82))
            painter.drawText(0, 220, self.width(), 24, Qt.AlignCenter, f'结果：{self.value} 点')

    def _final_transform(self):
        # 落地后保持稳定俯视侧角，能看到顶部结果面。
        return 'rotateX(-18deg) rotateY(-26deg) rotateZ(0deg)'

    def _pips(self, value):
        return {
            1: '<span class="p c"></span>',
            2: '<span class="p tl"></span><span class="p br"></span>',
            3: '<span class="p tl"></span><span class="p c"></span><span class="p br"></span>',
            4: '<span class="p tl"></span><span class="p tr"></span><span class="p bl"></span><span class="p br"></span>',
            5: '<span class="p tl"></span><span class="p tr"></span><span class="p c"></span><span class="p bl"></span><span class="p br"></span>',
            6: '<span class="p tl"></span><span class="p tr"></span><span class="p ml"></span><span class="p mr"></span><span class="p bl"></span><span class="p br"></span>',
        }[value]

    def _html(self, value):
        final = self.final_transform
        top_pips = self._pips(value)
        return f'''
<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:100%;height:100%;background:#fff7fa;overflow:hidden;}}
.scene{{width:212px;height:158px;display:flex;align-items:flex-end;justify-content:center;perspective:660px;padding-bottom:18px;box-sizing:border-box;}}
.dice{{width:78px;height:78px;position:relative;transform-style:preserve-3d;animation:drop 1.18s linear forwards;}}
.face{{position:absolute;width:78px;height:78px;border-radius:14px;background:linear-gradient(135deg,#fff 0%,#ffe7f0 60%,#d58aac 100%);border:2px solid #7d3759;box-sizing:border-box;box-shadow:inset 0 2px 7px rgba(255,255,255,.85),0 8px 18px rgba(92,43,69,.18);backface-visibility:visible;}}
.front{{transform:translateZ(39px)}} .back{{transform:rotateY(180deg) translateZ(39px)}} .right{{transform:rotateY(90deg) translateZ(39px)}} .left{{transform:rotateY(-90deg) translateZ(39px)}} .top{{transform:rotateX(90deg) translateZ(39px)}} .bottom{{transform:rotateX(-90deg) translateZ(39px)}}
.p{{position:absolute;width:11px;height:11px;border-radius:50%;background:#bc4870;box-shadow:inset 0 1px 2px rgba(255,255,255,.35)}}
.c{{left:33px;top:33px}} .tl{{left:17px;top:17px}} .tr{{right:17px;top:17px}} .ml{{left:17px;top:33px}} .mr{{right:17px;top:33px}} .bl{{left:17px;bottom:17px}} .br{{right:17px;bottom:17px}}
@keyframes drop{{
0%{{transform:translateY(-120px) rotateX(-260deg) rotateY(130deg) rotateZ(42deg);animation-timing-function:cubic-bezier(.24,.02,.78,.46)}}
45%{{transform:translateY(0) rotateX(210deg) rotateY(255deg) rotateZ(112deg) scaleY(.86);animation-timing-function:cubic-bezier(.18,.78,.25,1)}}
63%{{transform:translateY(-34px) rotateX(285deg) rotateY(310deg) rotateZ(145deg) scaleY(1.02);animation-timing-function:cubic-bezier(.35,.02,.82,.42)}}
78%{{transform:translateY(0) rotateX(345deg) rotateY(365deg) rotateZ(170deg) scaleY(.92);animation-timing-function:cubic-bezier(.18,.75,.28,1)}}
90%{{transform:translateY(-10px) rotateX(342deg) rotateY(334deg) rotateZ(180deg)}}
100%{{transform:translateY(0) {final}}}
}}
</style></head><body><div class="scene"><div class="dice">
<div class="face front"><span class="p tl"></span><span class="p tr"></span><span class="p bl"></span><span class="p br"></span></div>
<div class="face right"><span class="p tl"></span><span class="p br"></span></div>
<div class="face top">{top_pips}</div>
<div class="face bottom"><span class="p tl"></span><span class="p tr"></span><span class="p bl"></span><span class="p br"></span></div>
<div class="face left"><span class="p tl"></span><span class="p tr"></span><span class="p c"></span><span class="p bl"></span><span class="p br"></span></div>
<div class="face back"><span class="p tl"></span><span class="p tr"></span><span class="p ml"></span><span class="p mr"></span><span class="p bl"></span><span class="p br"></span></div>
</div></div></body></html>'''


class CoinPopup(EasterGamePopup):
    title = '抛硬币'

    def __init__(self, x, y, parent=None):
        self.result = random.choice(['正面', '反面'])
        self.rest_angle = random.choice([-16, -11, -7, 6, 12, 17])
        super().__init__(x, y, parent)

    def paintEvent(self, event):
        painter = QPainter(self)
        self._draw_card(painter, QColor(255, 252, 240, 248), QColor(234, 203, 121, 230))
        elapsed = self._elapsed()
        self._play_once('coin_start', 'coin')
        if elapsed > 1.05:
            self._play_once('coin_land', 'drop')
        if elapsed < 1.05:
            stage = 'air'
            p = elapsed / 1.05
            x = self.width() / 2 + math.sin(p * math.pi) * 12
            y = 182 - math.sin(p * math.pi) * 96
            edge = abs(math.cos(elapsed * 22))
            angle = elapsed * 420
            face = '正' if int(elapsed * 7) % 2 == 0 else '反'
        elif elapsed < 2.25:
            stage = 'edge'
            t = elapsed - 1.05
            p = min(1.0, t / 1.2)
            x = self.width() / 2 + math.sin(t * 12) * (1 - p) * 10
            y = 184 - abs(math.sin(t * 10)) * (1 - p) * 22
            edge = 0.10 + 0.22 * (1 - p) + 0.08 * abs(math.sin(t * 18))
            angle = self.rest_angle * p + t * 900 * (1 - p) + self._spring(t, 4.0, 16.0) * 12
            face = self.result[0]
        elif elapsed < 3.05:
            stage = 'settle'
            t = elapsed - 2.25
            p = self._ease_out(t / 0.8)
            x = self.width() / 2 + math.sin(t * 10) * (1 - p) * 3
            y = 184 - abs(math.sin(t * 9)) * (1 - p) * 6
            edge = 0.32 + 0.68 * p
            angle = self.rest_angle + self._spring(t, 4.2, 14.0) * 10 * (1 - p)
            face = self.result[0]
        else:
            stage = 'flat'
            t = elapsed - 3.05
            x = self.width() / 2
            y = 184
            edge = 1.0
            angle = self.rest_angle + self._spring(t, 5.0, 18.0) * 3
            face = self.result[0]

        shadow_w = 60 + edge * 62
        shadow_alpha = 26 + int(edge * 24)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(110, 80, 26, shadow_alpha))
        painter.drawEllipse(QRectF(self.width() / 2 - shadow_w / 2, 204, shadow_w, 15))

        painter.save()
        painter.translate(x, y)
        painter.rotate(angle)
        if stage == 'edge':
            painter.rotate(90)
        self._draw_coin(painter, edge, face)
        painter.restore()

        if stage != 'flat':
            painter.setFont(QFont('Microsoft YaHei UI', 10, QFont.Bold))
            painter.setPen(QColor(137, 95, 26, 190))
            painter.drawText(0, 218, self.width(), 24, Qt.AlignCenter, '硬币翻滚中...')
        else:
            painter.setFont(QFont('Microsoft YaHei UI', 12, QFont.Bold))
            painter.setPen(QColor(120, 82, 24))
            painter.drawText(0, 218, self.width(), 28, Qt.AlignCenter, f'结果：{self.result}')

    def _draw_coin(self, painter, face_scale, face):
        sx = max(0.08, min(1.0, face_scale))
        for offset in range(10, 0, -1):
            painter.save()
            painter.translate(offset * (1 - sx) * 0.9, 0)
            painter.scale(sx, 1.0)
            painter.setBrush(QColor(129, 83, 28, 210))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPoint(0, 0), 56, 56)
            painter.restore()

        painter.save()
        painter.scale(sx, 1.0)
        outer = QRadialGradient(-18, -22, 82)
        outer.setColorAt(0, QColor(255, 248, 190))
        outer.setColorAt(0.36, QColor(242, 190, 72))
        outer.setColorAt(0.72, QColor(177, 111, 34))
        outer.setColorAt(1, QColor(93, 58, 22))
        painter.setPen(QPen(QColor(116, 76, 28), 3))
        painter.setBrush(outer)
        painter.drawEllipse(QPoint(0, 0), 56, 56)

        inner = QRadialGradient(-14, -18, 58)
        inner.setColorAt(0, QColor(255, 249, 205))
        inner.setColorAt(0.52, QColor(233, 174, 57))
        inner.setColorAt(1, QColor(148, 88, 27))
        painter.setPen(QPen(QColor(255, 235, 148, 170), 2))
        painter.setBrush(inner)
        painter.drawEllipse(QPoint(0, 0), 45, 45)

        painter.setPen(QPen(QColor(103, 68, 26, 150), 1))
        for i in range(36):
            a = math.radians(i * 10)
            painter.drawLine(int(math.cos(a) * 47), int(math.sin(a) * 47), int(math.cos(a) * 54), int(math.sin(a) * 54))

        painter.setPen(QPen(QColor(255, 242, 174, 155), 1.5))
        painter.drawArc(-34, -38, 58, 48, 35 * 16, 105 * 16)
        painter.setPen(QPen(QColor(96, 61, 24, 130), 1.5))
        painter.drawArc(-30, -26, 66, 58, 210 * 16, 105 * 16)

        if face == '正':
            painter.setPen(QPen(QColor(119, 73, 24), 2))
            painter.setBrush(QColor(215, 159, 54, 120))
            painter.drawEllipse(QPoint(0, -5), 16, 20)
            painter.setPen(QPen(QColor(255, 230, 150, 170), 2))
            painter.drawLine(-8, -13, 6, 4)
            painter.setPen(QColor(105, 66, 25))
            painter.setFont(QFont('Georgia', 15, QFont.Bold))
            painter.drawText(-28, 18, 56, 20, Qt.AlignCenter, 'HEAD')
        else:
            painter.setPen(QPen(QColor(113, 70, 25), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(-22, 5, 22, 5)
            painter.drawLine(-16, 5, -16, -18)
            painter.drawLine(0, 5, 0, -24)
            painter.drawLine(16, 5, 16, -18)
            painter.drawArc(-25, -32, 50, 24, 0, 180 * 16)
            painter.setPen(QColor(105, 66, 25))
            painter.setFont(QFont('Georgia', 15, QFont.Bold))
            painter.drawText(-28, 18, 56, 20, Qt.AlignCenter, 'TAIL')
        painter.restore()


class GachaPopup(EasterGamePopup):
    title = '桌宠扭蛋机'
    PRIZES = [
        ('🌸 今日一句', '今天会遇见一件小好事。'),
        ('🍀 今日好运', '幸运值 87%，适合提交代码。'),
        ('🚀 今日 BUFF', '写代码效率 +20%，但只持续到下班。'),
        ('😴 今日 Debuff', '容易犯困，记得补水和休息。'),
        ('✨ 随机表情', '( •̀ ω •́ )✧'),
        ('🎯 小任务', '把那个一直拖着的小功能做完。'),
    ]

    def __init__(self, x, y, parent=None):
        self.prize = random.choice(self.PRIZES)
        self.opened = False
        self.started = False
        super().__init__(x, y, parent)
        self.setFixedSize(300, 360)
        self.start_button = QPushButton('开始扭蛋', self)
        self.start_button.setGeometry(104, 306, 92, 34)
        self.start_button.setCursor(Qt.PointingHandCursor)
        self.start_button.setStyleSheet('QPushButton{border:none;border-radius:15px;background:#ef5c91;color:white;font-weight:800;} QPushButton:hover{background:#dc477f;}')
        self.start_button.clicked.connect(self.start_gacha)
        self.start_button.show()

    def start_gacha(self):
        self.started = True
        self.opened = False
        self.prize = random.choice(self.PRIZES)
        self.started_at = time.monotonic()
        self.played_sounds.clear()
        self.start_button.hide()
        self.update()

    def mouseReleaseEvent(self, event):
        if self.started and event.button() == Qt.LeftButton and self._elapsed() >= 2.0:
            self.opened = True
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        self._draw_card(painter, QColor(255, 247, 252, 250), QColor(238, 177, 210, 230))
        elapsed = self._elapsed() if self.started else 0.0
        if self.started:
            self._play_once('gacha_turn', 'tick')
            if elapsed > 1.05:
                self._play_once('gacha_drop', 'drop')
            if self.opened:
                self._play_once('gacha_open', 'open')
        turn_p = min(1.0, elapsed / 1.1) if self.started else 0.0
        drop_p = self._ease_out((elapsed - 1.05) / 0.85) if self.started else 0.0
        shake = math.sin(elapsed * 38) * 3 * (1 - turn_p) if self.started and elapsed < 1.1 else 0

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(95, 55, 88, 35))
        painter.drawEllipse(74, 284, 152, 18)

        # machine body
        body_grad = QLinearGradient(74, 76, 226, 266)
        body_grad.setColorAt(0, QColor(255, 184, 215))
        body_grad.setColorAt(0.55, QColor(255, 126, 181))
        body_grad.setColorAt(1, QColor(201, 77, 132))
        painter.setBrush(body_grad)
        painter.setPen(QPen(QColor(166, 82, 124), 2))
        painter.drawRoundedRect(74 + shake, 76, 152, 190, 22, 22)
        glass_grad = QLinearGradient(92, 92, 208, 184)
        glass_grad.setColorAt(0, QColor(255, 255, 255, 230))
        glass_grad.setColorAt(1, QColor(255, 224, 243, 180))
        painter.setBrush(glass_grad)
        painter.drawRoundedRect(92 + shake, 92, 116, 92, 18, 18)
        painter.setPen(QPen(QColor(255, 255, 255, 150), 2))
        painter.drawArc(104 + int(shake), 101, 84, 50, 35 * 16, 95 * 16)
        painter.setPen(QPen(QColor(166, 82, 124), 2))
        painter.setBrush(QColor(238, 92, 145))
        painter.drawRoundedRect(96 + shake, 196, 108, 42, 16, 16)
        painter.setBrush(QColor(255, 249, 253))
        painter.drawRoundedRect(112 + shake, 210, 76, 16, 8, 8)

        # balls inside
        colors = [QColor(255, 211, 91), QColor(117, 205, 255), QColor(155, 229, 131), QColor(195, 143, 255), QColor(255, 142, 142)]
        for i, color in enumerate(colors):
            bx = 112 + (i % 3) * 32 + math.sin(elapsed * 5 + i) * 3 + shake
            by = 126 + (i // 3) * 27 + math.cos(elapsed * 4 + i) * 2
            painter.setBrush(color)
            painter.setPen(QPen(QColor(255, 255, 255, 150), 1))
            painter.drawEllipse(QPoint(int(bx), int(by)), 15, 15)

        # knob
        painter.save()
        painter.translate(150 + shake, 197)
        painter.rotate(360 * self._ease_out(turn_p))
        painter.setBrush(QColor(255, 230, 118))
        painter.setPen(QPen(QColor(154, 105, 28), 2))
        painter.drawEllipse(QPoint(0, 0), 25, 25)
        painter.setPen(QPen(QColor(154, 105, 28), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(-13, 0, 13, 0)
        painter.restore()

        # capsule
        cap_x = 150
        cap_y = 182 + 88 * drop_p
        if drop_p > 0:
            painter.setPen(QPen(QColor(137, 76, 105), 1.5))
            painter.setBrush(QColor(119, 205, 255))
            painter.drawPie(int(cap_x - 24), int(cap_y - 24), 48, 48, 0, 180 * 16)
            painter.setBrush(QColor(255, 232, 116))
            painter.drawPie(int(cap_x - 24), int(cap_y - 24), 48, 48, 180 * 16, 180 * 16)
            painter.drawLine(int(cap_x - 24), int(cap_y), int(cap_x + 24), int(cap_y))

        if not self.started:
            painter.setFont(QFont('Microsoft YaHei UI', 10, QFont.Bold))
            painter.setPen(QColor(126, 62, 98, 205))
            painter.drawText(0, 270, self.width(), 24, Qt.AlignCenter, '点击按钮开始')
            return

        if elapsed < 2.0:
            painter.setFont(QFont('Microsoft YaHei UI', 10, QFont.Bold))
            painter.setPen(QColor(126, 62, 98, 205))
            text = '咔哒咔哒，扭蛋掉落中...' if elapsed < 1.9 else '点击胶囊打开'
            painter.drawText(0, 306, self.width(), 24, Qt.AlignCenter, text)
            return

        if not self.opened:
            painter.setFont(QFont('Microsoft YaHei UI', 10, QFont.Bold))
            painter.setPen(QColor(126, 62, 98, 220))
            painter.drawText(0, 306, self.width(), 24, Qt.AlignCenter, '点击胶囊打开')
            return

        title, text = self.prize
        painter.setBrush(QColor(255, 255, 255, 232))
        painter.setPen(QPen(QColor(220, 144, 188, 160), 1))
        painter.drawRoundedRect(38, 205, 224, 72, 16, 16)
        painter.setFont(QFont('Microsoft YaHei UI', 11, QFont.Bold))
        painter.setPen(QColor(136, 58, 102))
        painter.drawText(48, 212, 204, 24, Qt.AlignCenter, title)
        painter.setFont(QFont('Microsoft YaHei UI', 9))
        painter.setPen(QColor(91, 57, 78))
        painter.drawText(52, 238, 196, 30, Qt.AlignCenter | Qt.TextWordWrap, text)


class GameNoticePopup(EasterGamePopup):
    def __init__(self, x, y, title, text, parent=None):
        self.title = title
        self.text = text
        super().__init__(x, y, parent)

    def paintEvent(self, event):
        painter = QPainter(self)
        self._draw_card(painter)
        painter.setFont(QFont('Microsoft YaHei UI', 11, QFont.Bold))
        painter.setPen(QColor(92, 59, 24))
        painter.drawText(34, 96, self.width() - 68, 100, Qt.AlignCenter | Qt.TextWordWrap, self.text)
