# coding:utf-8
import math
import random
import struct
import time
import wave

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QPoint, QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QKeyEvent, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
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
            {'role': 'system', 'content': '你就是神奇海螺本身。用户问你问题，你必须用"海螺说："开头，接一句神秘、笃定、可爱的中文短答案，总长度不超过20个字。不要解释，不要换行，不要出现"海螺低语"等其他前缀，只用"海螺说："。'},
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
        cx, cy = self.width() / 2, 176 + wobble

        # 外层光晕圆圈
        painter.setPen(Qt.NoPen)
        for i in range(4):
            alpha = int((70 - i * 12) * (0.35 + pulse * 0.65))
            painter.setBrush(QColor(170, 140, 220, alpha))
            r = 62 + i * 16 + pulse * 10
            painter.drawEllipse(QPoint(int(cx), int(cy)), int(r), int(r * 0.56))
        self._draw_magic_sparkles(painter, cx, cy, elapsed, listening)
        self._draw_shell(painter, cx, cy, elapsed, listening)

        if not asked:
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
        answer = self.answer
        answer_rect = QRectF(42, 262, self.width() - 84, 48)
        if metrics.boundingRect(answer_rect.toRect(), Qt.AlignCenter | Qt.TextWordWrap, answer).height() > answer_rect.height():
            font.setPointSize(10)
            painter.setFont(font)
        painter.drawText(answer_rect, Qt.AlignCenter | Qt.TextWordWrap, answer)
        painter.setOpacity(1)

    def _draw_magic_sparkles(self, painter, cx, cy, elapsed, listening):
        """简约星光粒子：只画细十字星，克制分布"""
        painter.save()
        # 6个星光点，偏移更分散
        pts = [(-78, -44), (68, -52), (104, 8), (82, 58), (-48, 62), (-96, 18)]
        for i, (dx, dy) in enumerate(pts):
            twinkle = (math.sin(elapsed * (2.8 + i * 0.45) + i * 1.3) + 1) / 2
            base_alpha = 160 if listening else 90
            alpha = int(base_alpha * (0.3 + 0.7 * twinkle))
            alpha = max(0, min(240, alpha))
            x = cx + dx + math.sin(elapsed * 1.2 + i) * 4
            y = cy + dy + math.cos(elapsed * 1.1 + i) * 3
            r = 1.4 + twinkle * 2.0
            # 十字星：两条线
            color = QColor(170, 210, 255, alpha)
            pen = QPen(color, max(1.0, r * 0.7))
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            arm = r * 2.8
            painter.drawLine(QPointF(x - arm, y), QPointF(x + arm, y))
            painter.drawLine(QPointF(x, y - arm), QPointF(x, y + arm))
            # 斜45°短臂
            arm2 = arm * 0.55
            painter.drawLine(QPointF(x - arm2, y - arm2), QPointF(x + arm2, y + arm2))
            painter.drawLine(QPointF(x + arm2, y - arm2), QPointF(x - arm2, y + arm2))
            # 中心亮点
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(240, 248, 255, alpha))
            painter.drawEllipse(QPointF(x, y), r * 0.6, r * 0.6)
        painter.restore()

    def _draw_shell(self, painter, cx, cy, elapsed, listening):
        """直接渲染神奇海螺图片，带摇摆和辉光动画"""
        painter.save()

        # ── 底部投影 ──
        painter.setPen(Qt.NoPen)
        sh = QRadialGradient(cx, cy + 68, 85)
        sh.setColorAt(0, QColor(160, 120, 200, 40))
        sh.setColorAt(1, QColor(160, 120, 200, 0))
        painter.setBrush(sh)
        painter.drawEllipse(QRectF(cx - 85, cy + 48, 170, 40))

        # ── 图片大小和摆动 ──
        img_size = 172  # 渲染尺寸
        sway = math.sin(elapsed * (3.2 if listening else 1.8)) * (3.0 if listening else 1.0)

        # 加载（缓存到类属性）
        if not hasattr(MagicConchPopup, '_shell_pixmap'):
            _p = config.RES_DIR / 'items' / 'easter' / 'magic_conch.png'
            MagicConchPopup._shell_pixmap = QPixmap(str(_p))

        px = MagicConchPopup._shell_pixmap
        if not px.isNull():
            scaled = px.scaled(img_size, img_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            sw, sh2 = scaled.width(), scaled.height()
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(-10 + sway)  # 固定逆时针10度 + 摇摆
            painter.drawPixmap(-sw // 2, -sh2 // 2, scaled)
            painter.restore()

        # ── 聆听时外层辉光环 ──
        if listening:
            pulse = (math.sin(elapsed * 8) + 1) / 2
            for i in range(3):
                r = img_size // 2 + 8 + i * 10 + pulse * 6
                alpha = int((80 - i * 22) * (0.5 + pulse * 0.5))
                glow = QRadialGradient(cx, cy, r)
                glow.setColorAt(0.7, QColor(200, 160, 240, alpha))
                glow.setColorAt(1.0, QColor(200, 160, 240, 0))
                painter.setPen(Qt.NoPen)
                painter.setBrush(glow)
                painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

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
        super().__init__(x, y, parent)
        self.setFixedSize(280, 408)
        self.move_to_anchor(x, y)
        self.web = QWebEngineView(self)
        self.web.setGeometry(20, 52, 240, 252)
        self.web.setContextMenuPolicy(Qt.NoContextMenu)
        self.web.setStyleSheet('background: #fff7fa; border: none;')
        self.web.page().setBackgroundColor(QColor(255, 247, 250))
        self.web.setHtml(self._html(self.value), QUrl.fromLocalFile(str(config.RES_DIR / 'items' / 'easter' / '3d' / 'dice.html')))
        self.web.show()
        self.web.raise_()
        self.button = QPushButton('重新投掷', self)
        self.button.setGeometry(86, 334, 108, 32)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setStyleSheet('QPushButton{border:none;border-radius:15px;background:#bd5f86;color:white;font-weight:700;} QPushButton:hover{background:#a84f75;}')
        self.button.clicked.connect(self.roll)
        self.button.show()
        self._play_once('dice_start', 'dice3d')

    def roll(self):
        self.value = random.randint(1, 6)
        self.started_at = time.monotonic()
        self.played_sounds.discard('dice_land')
        self.played_sounds.discard('dice_start')
        self.web.setHtml(self._html(self.value), QUrl.fromLocalFile(str(config.RES_DIR / 'items' / 'easter' / '3d' / 'dice.html')))
        self._play_once('dice_start', 'dice3d')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        self._draw_card(painter, QColor(255, 247, 250, 248), QColor(238, 180, 202, 230))
        if self._elapsed() > 1.8:
            self._play_once('dice_land', 'drop')
            painter.setFont(QFont('Microsoft YaHei UI', 12, QFont.Bold))
            painter.setPen(QColor(116, 56, 82))
            painter.drawText(0, 304, self.width(), 24, Qt.AlignCenter, f'结果：{self.value} 点')

    def _html(self, value):
        import base64
        three_path = (config.RES_DIR / 'items' / 'easter' / '3d' / 'three.min.js').as_posix()
        dice_dir = config.RES_DIR / 'items' / 'easter' / 'dice'

        # 读取6张PNG贴图并转Base64
        face_data = {}
        for i in range(1, 7):
            png_path = dice_dir / f'face_{i}.png'
            with open(png_path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('ascii')
                face_data[i] = f'data:image/png;base64,{b64}'

        side_values = [v for v in (1, 2, 3, 4, 5, 6) if v != value]
        random.shuffle(side_values)
        right, left, bottom, front, back = side_values[:5]
        ry = random.randint(0, 359)
        return f"""<!doctype html><html><head><meta charset='utf-8'><style>
html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:#fff7fa;}}
#stage{{width:240px;height:252px;}}
</style></head><body><div id='stage'></div><script src='file:///{three_path}'></script><script>
const W=240,H=252,OA=W/H,OH=5.2;
const scene=new THREE.Scene();
const camera=new THREE.OrthographicCamera(-OH*OA/2,OH*OA/2,OH/2,-OH/2,0.1,100);
camera.position.set(2.6,3.2,5.2); camera.lookAt(0,0.15,0);
const renderer=new THREE.WebGLRenderer({{alpha:true,antialias:true}});
renderer.setSize(W,H); renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
document.getElementById('stage').appendChild(renderer.domElement);
scene.add(new THREE.AmbientLight(0xfff5f8,1.5));
const dL=new THREE.DirectionalLight(0xffffff,1.8); dL.position.set(-1.5,5,4); scene.add(dL);
const fL=new THREE.DirectionalLight(0xffe0f0,0.6); fL.position.set(4,0.5,-1); scene.add(fL);
const shadowMesh=new THREE.Mesh(
  new THREE.CircleGeometry(0.9,48),
  new THREE.MeshBasicMaterial({{color:0x6b3a55,transparent:true,opacity:0.0,depthWrite:false}})
);
shadowMesh.rotation.x=-Math.PI/2; shadowMesh.position.set(0,-1.35,0);
shadowMesh.scale.set(1.2,0.8,1); scene.add(shadowMesh);
const faceDataURLs={{{','.join(f'{i}:"{face_data[i]}"' for i in range(1,7))}}};
const loader=new THREE.TextureLoader();
function faceTex(n){{
  const t=loader.load(faceDataURLs[n],()=>renderer.render(scene,camera));
  t.colorSpace=THREE.SRGBColorSpace;
  t.anisotropy=renderer.capabilities.getMaxAnisotropy();
  return t;
}}
const mats=[{right},{left},{value},{bottom},{front},{back}].map(n=>
  new THREE.MeshStandardMaterial({{map:faceTex(n),roughness:0.12,metalness:0.0}})
);
const cube=new THREE.Mesh(new THREE.BoxGeometry(1.8,1.8,1.8),mats);
scene.add(cube);
const finalRad={{x:0,y:{ry}*Math.PI/180,z:0}};
const GROUND=-1.15,DICE_R=0.9,THROW_H=3.8;
const DUR_FLY=900,DUR_B1=320,DUR_B2=220,DUR_SETTLE=200;
const TOTAL=DUR_FLY+DUR_B1+DUR_B2+DUR_SETTLE;
const spinX0=(Math.random()*3+2)*Math.PI*2;
const spinY0=(Math.random()*2+1.5)*Math.PI*2;
const spinZ0=(Math.random()*1.5+0.5)*Math.PI*2;
const T0=performance.now();
function tick(now){{
  const el=now-T0;
  let cy,rx,ry2,rz,sOp,sS;
  if(el<DUR_FLY){{
    const p=el/DUR_FLY,fp=p*p,sd=1-p*0.3;
    cy=GROUND+DICE_R+THROW_H*(1-fp);
    rx=finalRad.x+spinX0*sd*(1-p); ry2=finalRad.y+spinY0*sd*(1-p); rz=spinZ0*(1-p);
    const hr=(1-fp); sOp=0.04+(1-hr)*0.20; sS=0.4+(1-hr)*0.7;
  }} else if(el<DUR_FLY+DUR_B1){{
    const p=(el-DUR_FLY)/DUR_B1,sf=Math.pow(1-p,2);
    cy=GROUND+DICE_R+Math.sin(p*Math.PI)*0.55;
    rx=finalRad.x+spinX0*sf*0.12; ry2=finalRad.y+spinY0*sf*0.10; rz=spinZ0*sf*0.08;
    sOp=0.18-Math.sin(p*Math.PI)*0.06; sS=1.0-Math.sin(p*Math.PI)*0.18;
  }} else if(el<DUR_FLY+DUR_B1+DUR_B2){{
    const p=(el-DUR_FLY-DUR_B1)/DUR_B2;
    cy=GROUND+DICE_R+Math.sin(p*Math.PI)*0.18;
    rx=finalRad.x; ry2=finalRad.y; rz=0;
    sOp=0.20-Math.sin(p*Math.PI)*0.03; sS=1.0-Math.sin(p*Math.PI)*0.06;
  }} else {{
    const p=Math.min(1,(el-DUR_FLY-DUR_B1-DUR_B2)/DUR_SETTLE);
    const j=Math.sin(p*Math.PI*3)*(1-p)*0.018;
    cy=GROUND+DICE_R; rx=finalRad.x+j; ry2=finalRad.y; rz=j*0.5;
    sOp=0.22; sS=1.0;
  }}
  cube.position.y=cy; cube.rotation.x=rx; cube.rotation.y=ry2; cube.rotation.z=rz;
  shadowMesh.material.opacity=Math.min(sOp,0.28);
  const s=Math.max(0.3,sS); shadowMesh.scale.set(s,s,s);
  renderer.render(scene,camera); if(el<TOTAL) requestAnimationFrame(tick);
}}
requestAnimationFrame(tick);
</script></body></html>"""


class CoinPopup(EasterGamePopup):
    title = '抛硬币'

    def __init__(self, x, y, parent=None):
        self.result = random.choice(['正面', '反面'])
        super().__init__(x, y, parent)
        self.setFixedSize(280, 408)
        self.move_to_anchor(x, y)
        self.web = QWebEngineView(self)
        self.web.setGeometry(20, 52, 240, 252)
        self.web.setContextMenuPolicy(Qt.NoContextMenu)
        self.web.setStyleSheet('background: #fff7fa; border: none;')
        self.web.page().setBackgroundColor(QColor(255, 247, 250))
        self.web.setHtml(self._html(self.result), QUrl.fromLocalFile(str(config.RES_DIR / 'items' / 'easter' / '3d' / 'dice.html')))
        self.web.show()
        self.web.raise_()
        self.button = QPushButton('重新抛掷', self)
        self.button.setGeometry(86, 334, 108, 32)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setStyleSheet('QPushButton{border:none;border-radius:15px;background:#bd5f86;color:white;font-weight:700;} QPushButton:hover{background:#a84f75;}')
        self.button.clicked.connect(self.toss)
        self.button.show()
        self._play_once('coin_start', 'coin')

    def toss(self):
        self.result = random.choice(['正面', '反面'])
        self.started_at = time.monotonic()
        self.played_sounds.discard('coin_land')
        self.played_sounds.discard('coin_start')
        self.web.setHtml(self._html(self.result), QUrl.fromLocalFile(str(config.RES_DIR / 'items' / 'easter' / '3d' / 'dice.html')))
        self._play_once('coin_start', 'coin')
        self.update()

    def _html(self, result):
        three_path = (config.RES_DIR / 'items' / 'easter' / '3d' / 'three.min.js').as_posix()
        front_path = (config.RES_DIR / 'items' / 'easter' / 'coin_front.png').as_posix()
        back_path  = (config.RES_DIR / 'items' / 'easter' / 'coin_back.png').as_posix()
        final_x = 0 if result == '正面' else 180
        final_y = random.randint(0, 359)
        return f"""<!doctype html><html><head><meta charset='utf-8'><style>
html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:#fff7fa;}}
#stage{{width:240px;height:252px;}}
</style></head><body><div id='stage'></div>
<script src='file:///{three_path}'></script><script>
const W=240,H=252,OA=W/H,OH=5.8;
const scene=new THREE.Scene();
const camera=new THREE.OrthographicCamera(-OH*OA/2,OH*OA/2,OH/2,-OH/2,0.1,100);
camera.position.set(1.5,3.8,5.5); camera.lookAt(0,0.25,0);
const renderer=new THREE.WebGLRenderer({{alpha:true,antialias:true}});
renderer.setSize(W,H); renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
document.getElementById('stage').appendChild(renderer.domElement);
scene.add(new THREE.AmbientLight(0xffffff,2.6));
const dL=new THREE.DirectionalLight(0xffffff,2.2); dL.position.set(-1.5,5,4); scene.add(dL);
const fL=new THREE.DirectionalLight(0xfff0f8,0.8); fL.position.set(4,1,-2); scene.add(fL);
// 柔和点光源做辉光（不遮挡贴图）
const pL=new THREE.PointLight(0xffb8e0,0.0,8); pL.position.set(0,1,2); scene.add(pL);
const shadowMesh=new THREE.Mesh(
  new THREE.CircleGeometry(1.5,64),
  new THREE.MeshBasicMaterial({{color:0x6b3a55,transparent:true,opacity:0.0,depthWrite:false}})
);
shadowMesh.rotation.x=-Math.PI/2; shadowMesh.position.set(0,-0.36,0); scene.add(shadowMesh);
function makeFaceTex(isFront){{
  const loader=new THREE.TextureLoader();
  const url=isFront?'file:///{front_path}':'file:///{back_path}';
  const t=loader.load(url,()=>{{renderer.render(scene,camera);}});
  t.colorSpace=THREE.SRGBColorSpace;
  t.anisotropy=renderer.capabilities.getMaxAnisotropy();
  return t;
}}
function makeEdgeTex(){{
  const c=document.createElement('canvas'); c.width=256; c.height=32;
  const g=c.getContext('2d');
  const eg=g.createLinearGradient(0,0,0,32);
  eg.addColorStop(0,'#f0c8b0'); eg.addColorStop(0.25,'#d4907a'); eg.addColorStop(0.5,'#c07860'); eg.addColorStop(0.75,'#d4907a'); eg.addColorStop(1,'#f0c8b0');
  g.fillStyle=eg; g.fillRect(0,0,256,32);
  g.strokeStyle='rgba(255,220,200,0.40)'; g.lineWidth=1;
  for(let x=0;x<256;x+=4){{ g.beginPath(); g.moveTo(x,0); g.lineTo(x,32); g.stroke(); }}
  const t=new THREE.CanvasTexture(c); t.colorSpace=THREE.SRGBColorSpace; return t;
}}
const coinGeo=new THREE.CylinderGeometry(1.32,1.32,0.26,96);
const coinMats=[
  new THREE.MeshStandardMaterial({{map:makeEdgeTex(),roughness:0.15,metalness:0.75}}),
  new THREE.MeshStandardMaterial({{map:makeFaceTex(true),roughness:0.10,metalness:0.0}}),
  new THREE.MeshStandardMaterial({{map:makeFaceTex(false),roughness:0.10,metalness:0.0}}),
];
const coin=new THREE.Mesh(coinGeo,coinMats);
scene.add(coin);
const finalRad={{x:{final_x}*Math.PI/180,y:{final_y}*Math.PI/180,z:0}};
const GROUND=-0.35,THROW_H=3.8;
const DUR_FLY=900,DUR_B1=300,DUR_B2=200,DUR_SETTLE=180;
const TOTAL=DUR_FLY+DUR_B1+DUR_B2+DUR_SETTLE;
const spinX0=(Math.random()*3+2.5)*Math.PI*2;
const spinY0=(Math.random()*0.8+0.5)*Math.PI*2;
const T0=performance.now();
function tick(now){{
  const el=now-T0;
  let worldY,rx,ry2,rz=0,sOp,sS,glowI;
  if(el<DUR_FLY){{
    const p=el/DUR_FLY,fp=p*p,h=THROW_H*(1-fp);
    worldY=GROUND+h;
    rx=finalRad.x+spinX0*(1-p); ry2=finalRad.y+spinY0*(1-p);
    sOp=0.04+(1-h/THROW_H)*0.22; sS=0.3+(1-h/THROW_H)*0.75;
    glowI=0.0;
  }} else if(el<DUR_FLY+DUR_B1){{
    const p=(el-DUR_FLY)/DUR_B1,f=Math.pow(1-p,2);
    worldY=GROUND+Math.sin(p*Math.PI)*0.45;
    rx=finalRad.x+spinX0*f*0.08; ry2=finalRad.y+spinY0*f*0.06;
    sOp=0.22-Math.sin(p*Math.PI)*0.06; sS=1.0-Math.sin(p*Math.PI)*0.16;
    glowI=p*1.2;
  }} else if(el<DUR_FLY+DUR_B1+DUR_B2){{
    const p=(el-DUR_FLY-DUR_B1)/DUR_B2;
    worldY=GROUND+Math.sin(p*Math.PI)*0.14;
    rx=finalRad.x; ry2=finalRad.y;
    sOp=0.22; sS=1.0-Math.sin(p*Math.PI)*0.05;
    glowI=1.2+p*0.6;
  }} else {{
    const p=Math.min(1,(el-DUR_FLY-DUR_B1-DUR_B2)/DUR_SETTLE);
    const j=Math.sin(p*Math.PI*4)*(1-p)*0.012;
    worldY=GROUND; rx=finalRad.x+j; ry2=finalRad.y; rz=j*0.3;
    sOp=0.24; sS=1.0;
    glowI=1.4+Math.sin((el-TOTAL)*0.004)*0.4;
  }}
  coin.position.y=worldY; coin.rotation.x=rx; coin.rotation.y=ry2; coin.rotation.z=rz;
  pL.intensity=glowI; pL.position.set(0,worldY+0.5,1.8);
  shadowMesh.material.opacity=Math.min(sOp,0.30);
  const s=Math.max(0.3,sS); shadowMesh.scale.set(s,s,s);
  renderer.render(scene,camera);
  requestAnimationFrame(tick);
}}
requestAnimationFrame(tick);
</script></body></html>"""

    def paintEvent(self, event):
        painter = QPainter(self)
        self._draw_card(painter, QColor(255, 247, 250, 248), QColor(238, 180, 202, 230))
        if self._elapsed() > 1.6:
            self._play_once('coin_land', 'drop')
            painter.setFont(QFont('Microsoft YaHei UI', 12, QFont.Bold))
            painter.setPen(QColor(116, 56, 82))
            painter.drawText(0, 304, self.width(), 24, Qt.AlignCenter, f'结果：{self.result}')


class GachaPopup(EasterGamePopup):
    title = '桌宠扭蛋机'
    PRIZES = [
        ('🌸 今日一句', '今天会遇见一件小好事。'),
        ('🌸 今日一句', '代码一次跑通的概率今天翻倍。'),
        ('🌸 今日一句', '今天写的注释会被未来的你感谢。'),
        ('🍀 今日好运', '幸运值 87%，适合提交代码。'),
        ('🍀 今日好运', '今天的 Bug 都是表面问题，好修。'),
        ('🍀 今日好运', '遇到的报错都能在前三条搜索结果里找到答案。'),
        ('🚀 今日 BUFF', '写代码效率 +20%，但只持续到下班。'),
        ('🚀 今日 BUFF', '思路清晰 +50%，逻辑顺畅加成。'),
        ('🚀 今日 BUFF', '专注力 MAX，摸鱼欲望 -80%。'),
        ('🚀 今日 BUFF', '代码补全准确率 +30%，少打好多字。'),
        ('😴 今日 Debuff', '容易犯困，记得补水和休息。'),
        ('😴 今日 Debuff', '容易手滑打错变量名，小心拼写。'),
        ('😴 今日 Debuff', '今天可能遇到玄学问题，保持耐心。'),
        ('✨ 随机表情', '( •̀ ω •́ )✧'),
        ('✨ 随机表情', '(｡•̀ᴗ-)✧'),
        ('✨ 随机表情', '(๑•̀ㅂ•́)و✧'),
        ('✨ 随机表情', 'ヾ(≧▽≦*)o'),
        ('✨ 随机表情', '(๑˃ᴗ˂)ﻭ'),
        ('🎯 小任务', '把那个一直拖着的小功能做完。'),
        ('🎯 小任务', '整理一下待办列表，删掉过期的。'),
        ('🎯 小任务', '给最近的提交写个像样的 commit message。'),
        ('🎯 小任务', '把上周说要优化的地方优化一下。'),
        ('💡 灵感降临', '突然想到一个优雅的实现方案。'),
        ('💡 灵感降临', '今天适合重构，思路会很清晰。'),
        ('🎁 随机奖励', '获得一次免费摸鱼机会（限今日）。'),
        ('🎁 随机奖励', '今天写的代码可以少测一轮（不推荐）。'),
        ('🔧 开发者贴士', '记得定期提交，别攒到最后。'),
        ('🔧 开发者贴士', '先写测试再写代码，会更快。'),
        ('🔧 开发者贴士', '卡住超过 15 分钟就该求助了。'),
        ('📦 神秘物品', '获得了一个万能的 console.log。'),
        ('📦 神秘物品', '获得了传说中的「一次跑通」护身符。'),
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
            self._play_once("gacha_turn", "tick")
            if elapsed > 1.05:
                self._play_once("gacha_drop", "drop")
            if self.opened:
                self._play_once("gacha_open", "open")
        turn_p = min(1.0, elapsed / 1.1) if self.started else 0.0
        drop_p = self._ease_out((elapsed - 1.05) / 0.85) if self.started else 0.0
        shake = math.sin(elapsed * 38) * 3 * (1 - turn_p) if self.started and elapsed < 1.1 else 0

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(95, 55, 88, 35))
        painter.drawEllipse(74, 284, 152, 18)

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

        colors = [QColor(255, 211, 91), QColor(117, 205, 255), QColor(155, 229, 131), QColor(195, 143, 255), QColor(255, 142, 142)]
        for i, color in enumerate(colors):
            bx = 112 + (i % 3) * 32 + math.sin(elapsed * 5 + i) * 3 + shake
            by = 126 + (i // 3) * 27 + math.cos(elapsed * 4 + i) * 2
            painter.setBrush(color)
            painter.setPen(QPen(QColor(255, 255, 255, 150), 1))
            painter.drawEllipse(QPoint(int(bx), int(by)), 15, 15)

        painter.save()
        painter.translate(150 + shake, 197)
        painter.rotate(360 * self._ease_out(turn_p))
        painter.setBrush(QColor(255, 230, 118))
        painter.setPen(QPen(QColor(154, 105, 28), 2))
        painter.drawEllipse(QPoint(0, 0), 25, 25)
        painter.setPen(QPen(QColor(154, 105, 28), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(-13, 0, 13, 0)
        painter.restore()

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
