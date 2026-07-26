# coding:utf-8
"""离线唤醒词监听。

常驻只使用本地 Vosk 模型识别短文本；命中唤醒词后由应用层启动现有火山 ASR
语音聊天。这里不调用任何云端语音服务。
"""

import json
import re
import shutil
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

try:
    import sounddevice as sd
except Exception:
    sd = None

try:
    import vosk
except Exception:
    vosk = None

import config


class WakeWordError(Exception):
    pass


def normalize_text(text):
    text = str(text or '').lower()
    return re.sub(r'\s+', '', text)


def split_wake_words(words):
    if isinstance(words, (list, tuple)):
        values = words
    else:
        values = re.split(r'[,，;；\n]+', str(words or ''))
    return [normalize_text(item) for item in values if normalize_text(item)]


def resolve_model_dir(path_text):
    path = Path(str(path_text or '').strip())
    if not path.is_absolute():
        path = config.ROOT_DIR / path
    return path


def ensure_runtime_model_dir(model_dir):
    """把模型复制到用户目录，避开 Vosk 在中文工程路径下的模型读取问题。"""
    cache_root = Path.home() / '.minipet' / 'vosk'
    cache_dir = cache_root / model_dir.name
    required = ('am', 'conf', 'graph', 'ivector')
    if cache_dir.is_dir() and all((cache_dir / name).exists() for name in required):
        return cache_dir
    if not all((model_dir / name).exists() for name in required):
        return model_dir
    cache_root.mkdir(parents=True, exist_ok=True)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    shutil.copytree(model_dir, cache_dir)
    return cache_dir


class WakeWordWorker(QThread):
    detected = Signal(str)
    status_changed = Signal(str)
    error_received = Signal(str)

    def __init__(self, wake_config=None, parent=None):
        super().__init__(parent)
        self.wake_config = dict(wake_config or config.wake_word_config)
        self.running = True
        self.paused = False
        self.model = None
        self.stream = None

    def run(self):
        try:
            self._run_loop()
        except Exception as e:
            self.error_received.emit(str(e))
        finally:
            self._close_stream()

    def _run_loop(self):
        if sd is None:
            raise WakeWordError('缺少 sounddevice，请执行：pip install sounddevice')
        if vosk is None:
            raise WakeWordError('缺少 vosk，请执行：pip install vosk')
        model_dir = resolve_model_dir(self.wake_config.get('model_dir'))
        if not model_dir.is_dir():
            raise WakeWordError('未找到离线唤醒模型：%s' % model_dir)
        model_dir = ensure_runtime_model_dir(model_dir)
        wake_words = split_wake_words(self.wake_config.get('words'))
        if not wake_words:
            raise WakeWordError('请至少配置一个唤醒词')

        sample_rate = max(8000, int(self.wake_config.get('sample_rate') or 16000))
        chunk_ms = max(40, int(self.wake_config.get('chunk_ms') or 160))
        blocksize = max(1, int(sample_rate * chunk_ms / 1000))
        self.status_changed.emit('加载离线唤醒模型')
        self.model = vosk.Model(str(model_dir))
        recognizer = vosk.KaldiRecognizer(self.model, sample_rate)
        recognizer.SetWords(False)
        self.status_changed.emit('等待唤醒词')

        with sd.RawInputStream(samplerate=sample_rate, channels=1, dtype='int16', blocksize=blocksize) as stream:
            self.stream = stream
            while self.running:
                if self.paused:
                    time.sleep(0.08)
                    continue
                audio, overflowed = stream.read(blocksize)
                if overflowed:
                    self.status_changed.emit('唤醒监听音频溢出')
                if recognizer.AcceptWaveform(bytes(audio)):
                    text = self._extract_text(recognizer.Result())
                else:
                    text = self._extract_text(recognizer.PartialResult())
                if self._matches(text, wake_words):
                    self.detected.emit(text)
                    self.status_changed.emit('已唤醒')
                    recognizer.Reset()
                    self.pause()

    def _extract_text(self, payload):
        try:
            data = json.loads(payload or '{}')
        except Exception:
            return ''
        return data.get('text') or data.get('partial') or ''

    def _matches(self, text, wake_words):
        normalized = normalize_text(text)
        if not normalized:
            return False
        return any(word and word in normalized for word in wake_words)

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False
        self.status_changed.emit('等待唤醒词')

    def stop(self):
        self.running = False
        self.paused = False

    def _close_stream(self):
        self.stream = None
