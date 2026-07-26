# coding:utf-8
"""Codex v2 宠物包导出。

把 MiniPet 现有角色按 Codex v2 的 8x11 spritesheet 运行时格式导出到
~/.codex/pets/<pet>/，用于让 Codex/ChatGPT 的宠物前端加载 MiniPet 角色。
"""

import json
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter

import config
from pet.pet_assets import load_pet_profile


CODEX_PET_DIR = Path.home() / '.codex' / 'pets'
CELL_WIDTH = 192
CELL_HEIGHT = 208
COLUMNS = 8
ROWS = 11

ROW_ACTIONS = [
    ('idle', ['idle', 'default', 'stand']),
    # Codex 的 running-right / running-left 在按住拖拽时使用；MiniPet 语义下按住统一用 drag。
    ('running-right', ['drag', 'running-right', 'right_walk', 'rightwalk', 'right', 'default']),
    ('running-left', ['drag', 'running-left', 'left_walk', 'leftwalk', 'left', 'default']),
    ('waving', ['waving', 'wavehand', 'wavehand2', 'happy', 'patpat', 'pat', 'default']),
    ('jumping', ['jumping', 'playball', 'play', 'dance', 'happy', 'default']),
    # MiniPet 的 fall 是桌面物理下落，不等于任务失败；这里只用真正失败/情绪类动作。
    ('failed', ['failed', 'faint', 'giveup', 'cry', 'aggrieved', 'disturbed', 'angry', 'dislike', 'redangry', 'default']),
    ('waiting', ['waiting', 'sleep', 'sleepy', 'fall_asleep', 'sit', 'default']),
    ('running', ['running', 'work', 'focus', 'loop', 'default']),
    ('review', ['review', 'focus', 'look', 'seebook', 'ly-guancha', 'work', 'default']),
]

LOOK_DIRECTIONS = [
    '000', '022.5', '045', '067.5', '090', '112.5', '135', '157.5',
    '180', '202.5', '225', '247.5', '270', '292.5', '315', '337.5',
]


def _pet_id(name):
    return str(name or '').strip() or config.APP_ID


def _first_existing_act(profile, candidates):
    for name in candidates:
        if name in profile.acts:
            return profile.acts[name]
    return profile.default


def _frame_at(act, index):
    if not act.images:
        return None
    return act.images[index % len(act.images)]


def _draw_frame(painter, pixmap, column, row):
    if pixmap is None or pixmap.isNull():
        return
    available = QRect(column * CELL_WIDTH, row * CELL_HEIGHT, CELL_WIDTH, CELL_HEIGHT)
    scaled = pixmap.scaled(CELL_WIDTH, CELL_HEIGHT, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    x = available.x() + (CELL_WIDTH - scaled.width()) // 2
    y = available.y() + CELL_HEIGHT - scaled.height()
    painter.drawPixmap(x, y, scaled)


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def export_pet_to_codex(pet_name, output_root=None):
    """导出当前 MiniPet 角色为 Codex v2 资源目录，返回导出目录 Path。"""
    profile = load_pet_profile(pet_name)
    output_root = Path(output_root) if output_root else CODEX_PET_DIR
    output_dir = output_root / _pet_id(pet_name)
    output_dir.mkdir(parents=True, exist_ok=True)

    atlas = QImage(COLUMNS * CELL_WIDTH, ROWS * CELL_HEIGHT, QImage.Format.Format_ARGB32)
    atlas.fill(Qt.transparent)
    painter = QPainter(atlas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    used_actions = {}
    for row_index, (row_name, candidates) in enumerate(ROW_ACTIONS):
        act = _first_existing_act(profile, candidates)
        used_actions[row_name] = act.name
        for column in range(COLUMNS):
            _draw_frame(painter, _frame_at(act, column), column, row_index)

    # Codex 在鼠标附近但未按住时使用 look-direction 行。
    # MiniPet 没有 16 向视线资源；为了避免 hover 触发走路/跳舞感，这里统一用默认动作。
    look_act = _first_existing_act(profile, ['idle', 'default', 'stand'])
    for direction_index in range(16):
        act = look_act
        row = 9 if direction_index < 8 else 10
        column = direction_index % 8
        _draw_frame(painter, _frame_at(act, column), column, row)
    painter.end()

    spritesheet = output_dir / 'spritesheet.webp'
    if not atlas.save(str(spritesheet), 'WEBP'):
        spritesheet = output_dir / 'spritesheet.png'
        if not atlas.save(str(spritesheet), 'PNG'):
            raise RuntimeError('无法写入 Codex spritesheet: ' + str(spritesheet))
    spritesheet_name = spritesheet.name

    pet_conf = {
        'name': pet_name,
        'spriteVersionNumber': 2,
        'spritesheet': spritesheet_name,
        'width': CELL_WIDTH,
        'height': CELL_HEIGHT,
        'cell_width': CELL_WIDTH,
        'cell_height': CELL_HEIGHT,
        'columns': COLUMNS,
        'rows': ROWS,
        'scale': 1.0,
        'default': 'idle',
        'drag': 'idle',
        'fall': 'failed',
        'on_floor': 'idle',
        'patpat': 'waving',
        'codex_row_actions': used_actions,
        'lookDirections': LOOK_DIRECTIONS,
        'exportedBy': config.APP_DISPLAY_NAME,
        'exportNote': 'MiniPet 原生角色导出的 Codex v2 显示包；标准动作按现有动作映射，look directions 暂用 idle/default 填充。',
    }
    codex_manifest = {
        'id': _pet_id(pet_name),
        'displayName': pet_name,
        'description': 'A MiniPet character exported for Codex.',
        'spriteVersionNumber': 2,
        'spritesheetPath': spritesheet_name,
    }
    debug_manifest = {
        'name': pet_name,
        'spriteVersionNumber': 2,
        'spritesheet': spritesheet_name,
        'cell': {'width': CELL_WIDTH, 'height': CELL_HEIGHT},
        'atlas': {'columns': COLUMNS, 'rows': ROWS},
        'animations': {row_name: {'row': index, 'frames': COLUMNS} for index, (row_name, _candidates) in enumerate(ROW_ACTIONS)},
        'lookDirections': LOOK_DIRECTIONS,
    }
    _write_json(output_dir / 'pet.json', codex_manifest)
    _write_json(output_dir / 'pet_conf.json', pet_conf)
    _write_json(output_dir / 'manifest.json', debug_manifest)
    return output_dir


def export_all_pets_to_codex(output_root=None, progress_callback=None):
    """批量导出所有 MiniPet 角色，返回成功目录和失败信息。"""
    exported = []
    failed = []
    pets = config.get_pet_list()
    total = len(pets)
    for index, pet_name in enumerate(pets, start=1):
        if progress_callback:
            progress_callback(pet_name, index, total)
        try:
            exported.append(export_pet_to_codex(pet_name, output_root=output_root))
        except Exception as exc:
            failed.append({'pet': pet_name, 'error': str(exc)})
    return exported, failed
