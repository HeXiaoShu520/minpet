# coding:utf-8
"""
角色资源加载模块。

负责读取 res/role/<pet>/pet_conf.json、动作帧图片和锚点配置，组装成
PetProfile/Act。DesktopPet 和 AnimationWorker 只消费这里返回的结构化对象。
"""

import glob
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPixmap

from miniPet import config


CODEX_V2_ROW_ALIASES = {
    'default': 'idle',
    'stand': 'idle',
    'idle': 'idle',
    'running-right': 'running-right',
    'right_walk': 'running-right',
    'rightwalk': 'running-right',
    'running-left': 'running-left',
    'left_walk': 'running-left',
    'leftwalk': 'running-left',
    'waving': 'waving',
    'jumping': 'jumping',
    'failed': 'failed',
    'waiting': 'waiting',
    'running': 'running',
    'review': 'review',
}

CODEX_V2_DEFAULT_ROWS = [
    'idle',
    'running-right',
    'running-left',
    'waving',
    'jumping',
    'failed',
    'waiting',
    'running',
    'review',
]


def _pixmap_bounds(pixmap):
    """计算 pixmap 中非透明区域的 bounding box（原始像素坐标）。"""
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    try:
        import numpy as np
        ptr = image.bits()
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape(image.height(), image.width(), 4)
        alpha = arr[:, :, 3]
        rows = np.any(alpha > 0, axis=1)
        cols = np.any(alpha > 0, axis=0)
        if not rows.any():
            return (0, 0, image.width(), image.height())
        top = int(np.argmax(rows))
        bottom = int(len(rows) - 1 - np.argmax(rows[::-1]))
        left = int(np.argmax(cols))
        right = int(len(cols) - 1 - np.argmax(cols[::-1]))
        return (left, top, right - left + 1, bottom - top + 1)
    except ImportError:
        return (0, 0, image.width(), image.height())


@dataclass
class Act:
    name: str
    images: list
    act_num: int = 1
    direction: str = None
    frame_move: float = 0.0
    frame_refresh: float = 0.5
    anchor: list = field(default_factory=lambda: [0, 0])
    bounds: list = field(default_factory=list)  # per-frame (left,top,w,h) in original pixels

    def get_bounds(self, pixmap, scale):
        idx = id(pixmap)
        for pid, rect in self.bounds:
            if pid == idx:
                l, t, w, h = rect
                return QRect(int(l * scale), int(t * scale), max(1, int(w * scale)), max(1, int(h * scale)))
        return QRect(0, 0, max(1, int(pixmap.width() * scale)), max(1, int(pixmap.height() * scale)))


@dataclass
class PetProfile:
    name: str
    width: int
    height: int
    scale: float
    refresh: float
    interact_speed: int
    acts: dict
    default: Act
    drag: Act
    fall: Act
    prefall: Act
    on_floor: Act
    patpat: dict
    random_acts: list
    accessory_acts: dict


def _load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _frame_files(role_dir: Path, image_key: str):
    pattern = str(role_dir / 'action' / f'{image_key}_*.png')
    files = glob.glob(pattern)
    def frame_index(path):
        match = re.search(r'_(\d+)\.png$', os.path.basename(path))
        return int(match.group(1)) if match else 0
    return sorted(files, key=frame_index)


def _load_pixmaps(role_dir: Path, image_key: str):
    files = _frame_files(role_dir, image_key)
    if not files:
        direct = role_dir / 'action' / f'{image_key}.png'
        if direct.exists():
            files = [str(direct)]
    pixmaps = []
    for file_path in files:
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            pixmaps.append(pixmap)
    return pixmaps


def _find_codex_v2_spritesheet(role_dir: Path, pet_conf: dict):
    configured = pet_conf.get('spritesheet') or pet_conf.get('atlas') or pet_conf.get('image')
    candidates = []
    if configured:
        path = Path(str(configured))
        candidates.append(path if path.is_absolute() else role_dir / path)
    for name in ('spritesheet.webp', 'spritesheet.png', 'atlas.webp', 'atlas.png'):
        candidates.append(role_dir / name)
        candidates.append(role_dir / 'action' / name)
    for path in candidates:
        if path.is_file():
            return path
    return None


def _load_codex_v2_pixmaps(role_dir: Path, pet_conf: dict):
    sheet_path = _find_codex_v2_spritesheet(role_dir, pet_conf)
    if sheet_path is None:
        raise FileNotFoundError(f'Codex v2 spritesheet not found: {role_dir.name}')
    sheet = QPixmap(str(sheet_path))
    if sheet.isNull():
        raise FileNotFoundError(f'Codex v2 spritesheet cannot be loaded: {sheet_path}')
    cell_width = int(pet_conf.get('cell_width') or pet_conf.get('cellWidth') or 192)
    cell_height = int(pet_conf.get('cell_height') or pet_conf.get('cellHeight') or 208)
    columns = int(pet_conf.get('columns') or pet_conf.get('cols') or 8)
    rows = int(pet_conf.get('rows') or 11)
    if sheet.width() < columns * cell_width or sheet.height() < rows * cell_height:
        raise ValueError(f'Codex v2 spritesheet size mismatch: {sheet_path}')
    row_frames = {}
    for row_index in range(rows):
        frames = []
        for column in range(columns):
            frames.append(sheet.copy(column * cell_width, row_index * cell_height, cell_width, cell_height))
        row_frames[row_index] = frames
    return row_frames, cell_width, cell_height


def _make_codex_v2_act(name: str, row_frames: dict, row_index: int, data: dict, scale: float):
    images = list(row_frames.get(row_index, []))
    if not images:
        raise FileNotFoundError(f'Codex v2 row not found: {name}')
    bounds = [(id(p), _pixmap_bounds(p)) for p in images]
    return Act(
        name=name,
        images=images,
        act_num=int(data.get('act_num', 1)),
        direction=data.get('direction'),
        frame_move=float(data.get('frame_move', 0)) * scale,
        frame_refresh=float(data.get('frame_refresh', 0.12)),
        anchor=[int(v * scale) for v in data.get('anchor', [0, 0])],
        bounds=bounds,
    )


def _make_act(role_dir: Path, name: str, data: dict, scale: float):
    images = _load_pixmaps(role_dir, data.get('images', name))
    if not images:
        raise FileNotFoundError(f'Action images not found: {role_dir.name}/{name}')
    bounds = [(id(p), _pixmap_bounds(p)) for p in images]
    return Act(
        name=name,
        images=images,
        act_num=int(data.get('act_num', 1)),
        direction=data.get('direction'),
        frame_move=float(data.get('frame_move', 0)) * scale,
        frame_refresh=float(data.get('frame_refresh', 0.5)),
        anchor=[int(v * scale) for v in data.get('anchor', [0, 0])],
        bounds=bounds,
    )


def _fill_patpat(raw, acts):
    if isinstance(raw, str):
        return {i: acts.get(raw) or next(iter(acts.values())) for i in range(4)}
    if isinstance(raw, dict):
        filled = {}
        last = None
        for i in range(4):
            key = str(i)
            if key in raw:
                last = raw[key]
            filled[i] = acts.get(last) if last else next(iter(acts.values()))
        return filled
    return {i: next(iter(acts.values())) for i in range(4)}


def _load_standard_pet_acts(role_dir: Path, pet_conf: dict, act_conf: dict, scale: float):
    acts = {}
    for name, data in act_conf.items():
        try:
            acts[name] = _make_act(role_dir, name, data, scale)
        except FileNotFoundError:
            pass
    return acts


def _load_codex_v2_acts(role_dir: Path, pet_conf: dict, act_conf: dict, scale: float):
    row_frames, _cell_width, _cell_height = _load_codex_v2_pixmaps(role_dir, pet_conf)
    acts = {}
    for name, row_name in zip(CODEX_V2_DEFAULT_ROWS, CODEX_V2_DEFAULT_ROWS):
        row_index = CODEX_V2_DEFAULT_ROWS.index(row_name)
        data = dict(act_conf.get(name, {}))
        data.setdefault('images', name)
        acts[name] = _make_codex_v2_act(name, row_frames, row_index, data, scale)
    for name, data in act_conf.items():
        row_name = data.get('codex_row') or data.get('row_name') or CODEX_V2_ROW_ALIASES.get(data.get('images', name), data.get('images', name))
        if row_name in CODEX_V2_DEFAULT_ROWS:
            row_index = CODEX_V2_DEFAULT_ROWS.index(row_name)
        elif isinstance(data.get('row'), int):
            row_index = int(data.get('row'))
        else:
            continue
        acts[name] = _make_codex_v2_act(name, row_frames, row_index, data, scale)
    aliases = {
        'default': 'idle',
        'stand': 'idle',
        'drag': 'idle',
        'fall': 'failed',
        'prefall': 'failed',
        'onfloor': 'idle',
        'patpat': 'waving',
        'happy': 'waving',
        'work': 'running',
        'left_walk': 'running-left',
        'right_walk': 'running-right',
    }
    for alias, target in aliases.items():
        if alias not in acts and target in acts:
            acts[alias] = acts[target]
    return acts


def load_pet_profile(pet_name: str):
    role_dir = config.RES_DIR / 'role' / pet_name
    pet_conf = _load_json(role_dir / 'pet_conf.json')
    act_conf_path = role_dir / 'act_conf.json'
    act_conf = _load_json(act_conf_path) if act_conf_path.is_file() else {}
    scale = float(pet_conf.get('scale', 1.0))
    is_codex_v2 = int(pet_conf.get('spriteVersionNumber', pet_conf.get('sprite_version_number', 0)) or 0) == 2
    if is_codex_v2:
        acts = _load_codex_v2_acts(role_dir, pet_conf, act_conf, scale)
        default_width = int(pet_conf.get('cell_width') or pet_conf.get('cellWidth') or 192)
        default_height = int(pet_conf.get('cell_height') or pet_conf.get('cellHeight') or 208)
    else:
        acts = _load_standard_pet_acts(role_dir, pet_conf, act_conf, scale)
        default_width = 128
        default_height = 128

    def act(name, fallback='default'):
        return acts.get(pet_conf.get(name, fallback)) or acts[fallback]

    random_acts = []
    for item in pet_conf.get('random_act', []):
        act_list = [acts[a] for a in item.get('act_list', []) if a in acts]
        if act_list:
            random_acts.append({
                'name': item.get('name') or act_list[0].name,
                'acts': act_list,
                'prob': float(item.get('act_prob', 0.2)),
            })

    accessory_acts = {}
    for item in pet_conf.get('accessory_act', []):
        act_list = [acts[a] for a in item.get('act_list', []) if a in acts]
        acc_list = [acts[a] for a in item.get('acc_list', []) if a in acts]
        if act_list:
            accessory_acts[item.get('name') or act_list[0].name] = {
                'acts': act_list,
                'accessory_acts': acc_list,
                'anchor': [int(v * scale) for v in item.get('anchor', [0, 0])],
            }

    return PetProfile(
        name=pet_name,
        width=int(float(pet_conf.get('width', default_width)) * scale),
        height=int(float(pet_conf.get('height', default_height)) * scale),
        scale=scale,
        refresh=float(pet_conf.get('refresh', 5)),
        interact_speed=int(float(pet_conf.get('interact_speed', 0.02)) * 1000),
        acts=acts,
        default=act('default'),
        drag=act('drag'),
        fall=act('fall'),
        prefall=act('prefall', 'fall'),
        on_floor=act('on_floor', 'default'),
        patpat=_fill_patpat(pet_conf.get('patpat', 'default'), acts),
        random_acts=random_acts,
        accessory_acts=accessory_acts,
    )
