# coding:utf-8
import json
import os
from pathlib import Path

from PySide6.QtCore import QLocale

ROOT_DIR = Path(__file__).resolve().parents[2]
RES_DIR = ROOT_DIR / 'res'
DATA_DIR = ROOT_DIR / 'data'
AVATARS_DIR = DATA_DIR / 'avatars'
SETTINGS_FILE = DATA_DIR / 'minipet_settings.json'
ENV_FILE = ROOT_DIR / '.env'
DEFAULT_THEME_COLOR = '#009faa'

DEFAULT_APP_CONFIG = {
    'on_top': True,      # 宠物窗口置顶：固定为True，始终显示在其他窗口上方
    'allow_drop': True,  # 允许宠物掉落：固定为True，释放鼠标时宠物会掉落到地面
    'volume': 0.4,
    'language_code': QLocale().name(),
    'theme_color': None,
    'default_pet': '',
    'scale': 1.0,
    'pet_avatar': '',
    'user_avatar': 'user_avatar_5.png',  # 默认使用中心位置的头像
    'agent_backend': 'builtin',
    'openclaw_ws_url': 'ws://127.0.0.1:18888/ws/pet',
    'custom_agent_ws_url': 'ws://127.0.0.1:18889/ws/minipet',
    'bubble_style': 'soft',
    'smart_bubble_style': 'aurora',
    'voice_orb_style': 'jade',
    'voice_follow_effect': 'spring',
    'voice_follow_level': 'normal',
}

DEFAULT_LLM_CONFIG = {
    'provider': 'openai',
    'api_base': 'https://api.openai.com/v1',
    'api_key': '',
    'model': 'gpt-4o-mini',
    'max_tokens': 1024,
    'system_prompt': '你是一只可爱的桌面宠物，性格活泼亲切，会用简短、口语化、带点撒娇的语气陪伴主人聊天。',
    'memory_prompt': '',
    'auto_memory_enabled': True,
    'auto_memory_every_n_user_turns': 3,
    'auto_memory_max_items_per_pass': 3,
    'auto_memory_recent_messages': 12,
}

DEFAULT_TTS_CONFIG = {
    'enabled': False,
    'api_key': '',
    'voice_name': 'zh_female_vv_uranus_bigtts',
    'max_chars': 500,
    'disable_emoji_filter': False,
    'max_length_to_filter_parenthesis': 0,
}

DEFAULT_CHAT_RESTORE_CONFIG = {
    'enabled': True,             # 启动时是否恢复上次对话
    'max_messages': 20,          # 最多加载最近多少条消息
    'max_days': 1,               # 最多往前追溯多少天
}

CHAT_RESTORE_ENV_KEYS = {
    'enabled': 'CHAT_RESTORE_ENABLED',
    'max_messages': 'CHAT_RESTORE_MAX_MESSAGES',
    'max_days': 'CHAT_RESTORE_MAX_DAYS',
}

APP_BASIC_ENV_KEYS = {
    'volume': 'APP_VOLUME',
    'scale': 'APP_SCALE',
}

DEFAULT_TYPEWRITER_CONFIG = {
    'enabled': True,        # 打字机效果总开关
    'speed_ms': 28,         # 每字间隔上限（毫秒）
    'max_duration_ms': 5000,# 打字总时长上限（毫秒）
    'tts_delay_ms': 500,    # 开启语音播放时，回复延迟显示的毫秒数
}

TYPEWRITER_ENV_KEYS = {
    'enabled': 'TYPEWRITER_ENABLED',
    'speed_ms': 'TYPEWRITER_SPEED_MS',
    'max_duration_ms': 'TYPEWRITER_MAX_DURATION_MS',
    'tts_delay_ms': 'TYPEWRITER_TTS_DELAY_MS',
}

DEFAULT_REALTIME_CONFIG = {
    'enabled': False,
    'model': '1.2.1.1',
    'speaker': 'zh_female_vv_jupiter_bigtts',
    'bot_name': 'miniPet',
    'system_role': '你是一只可爱的桌面宠物，陪伴用户聊天，回答要简短自然。',
    'speaking_style': '语气活泼、亲切、口语化。',
}

LLM_ENV_KEYS = {
    'provider': 'LLM_PROVIDER',
    'api_base': 'LLM_API_BASE',
    'api_key': 'LLM_API_KEY',
    'model': 'LLM_MODEL',
    'max_tokens': 'LLM_MAX_TOKENS',
    'system_prompt': 'LLM_SYSTEM_PROMPT',
    'memory_prompt': 'LLM_MEMORY_PROMPT',
    'auto_memory_enabled': 'LLM_AUTO_MEMORY_ENABLED',
    'auto_memory_every_n_user_turns': 'LLM_AUTO_MEMORY_EVERY_N_USER_TURNS',
    'auto_memory_max_items_per_pass': 'LLM_AUTO_MEMORY_MAX_ITEMS_PER_PASS',
    'auto_memory_recent_messages': 'LLM_AUTO_MEMORY_RECENT_MESSAGES',
}

TTS_ENV_KEYS = {
    'enabled': 'TTS_ENABLED',
    'api_key': 'TTS_API_KEY',
    'voice_name': 'TTS_VOICE_NAME',
    'max_chars': 'TTS_MAX_CHARS',
    'disable_emoji_filter': 'TTS_DISABLE_EMOJI_FILTER',
    'max_length_to_filter_parenthesis': 'TTS_MAX_LENGTH_TO_FILTER_PARENTHESIS',
}

REALTIME_ENV_KEYS = {
    'enabled': 'REALTIME_ENABLED',
    'model': 'REALTIME_MODEL',
    'speaker': 'REALTIME_SPEAKER',
    'bot_name': 'REALTIME_BOT_NAME',
    'system_role': 'REALTIME_SYSTEM_ROLE',
    'speaking_style': 'REALTIME_SPEAKING_STYLE',
}

app_config = dict(DEFAULT_APP_CONFIG)
llm_config = dict(DEFAULT_LLM_CONFIG)
tts_config = dict(DEFAULT_TTS_CONFIG)
realtime_config = dict(DEFAULT_REALTIME_CONFIG)
typewriter_config = dict(DEFAULT_TYPEWRITER_CONFIG)
chat_restore_config = dict(DEFAULT_CHAT_RESTORE_CONFIG)
current_image = None
previous_anchor = [0, 0]
current_anchor = [0, 0]
screens = []
current_screen = None
on_floor = True
dragging = False
drag_speed_x = 0.0
drag_speed_y = 0.0
fall_right = False
play_id = 0
act_id = 0
current_pet = ''


def ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)


def avatar_path(kind):
    key = 'user_avatar' if kind == 'user' else 'pet_avatar'
    filename = str(app_config.get(key, '') or '').strip()
    if filename:
        p = AVATARS_DIR / filename
        if p.is_file():
            return p
    if kind == 'pet' and current_pet:
        pfp = RES_DIR / 'role' / current_pet / 'info' / 'pfp.png'
        if pfp.is_file():
            return pfp
    return RES_DIR / 'icons' / ('character.svg' if kind == 'user' else 'icon.png')



def get_pet_list():
    role_dir = RES_DIR / 'role'
    if not role_dir.exists():
        return []
    pets = []
    for child in role_dir.iterdir():
        if child.is_dir() and child.name != 'sys' and (child / 'pet_conf.json').exists():
            pets.append(child.name)
    return sorted(pets)


def _parse_env_file():
    data = {}
    if not ENV_FILE.is_file():
        return data
    with ENV_FILE.open('r', encoding='utf-8') as f:
        for line in f:
            raw = line.strip()
            if not raw or raw.startswith('#') or '=' not in raw:
                continue
            key, value = raw.split('=', 1)
            value = value.strip().strip('"').strip("'").replace('\\n', '\n')
            data[key.strip()] = value
    return data


def _load_env_config(defaults, env_keys):
    env_data = _parse_env_file()
    cfg = dict(defaults)
    for field, env_key in env_keys.items():
        value = os.environ.get(env_key, env_data.get(env_key))
        if value is None:
            continue
        if isinstance(defaults[field], bool):
            value = str(value).lower() in ('1', 'true', 'yes', 'on')
        elif isinstance(defaults[field], int):
            try:
                value = int(value)
            except ValueError:
                value = defaults[field]
        cfg[field] = value
    return cfg


def _save_env_config(config, env_keys, defaults, section_title):
    existing = []
    if ENV_FILE.is_file():
        existing = ENV_FILE.read_text(encoding='utf-8').splitlines()
    managed = set(env_keys.values())
    kept = []
    for line in existing:
        stripped = line.strip()
        if stripped == section_title:
            continue
        if '=' in stripped and not stripped.startswith('#'):
            key = stripped.split('=', 1)[0].strip()
            if key in managed:
                continue
        kept.append(line)
    if kept and kept[-1].strip():
        kept.append('')
    kept.append(section_title)
    for field, env_key in env_keys.items():
        value = str(config.get(field, defaults[field])).replace('\n', '\\n')
        kept.append(f'{env_key}={value}')
    ENV_FILE.write_text('\n'.join(kept).rstrip() + '\n', encoding='utf-8')


def load():
    global app_config, llm_config, tts_config, realtime_config, typewriter_config, chat_restore_config, current_pet
    ensure_data_dir()
    pets = get_pet_list()
    app_config = dict(DEFAULT_APP_CONFIG)
    if SETTINGS_FILE.is_file():
        try:
            app_config.update(json.loads(SETTINGS_FILE.read_text(encoding='utf-8')))
        except Exception:
            pass
    # 强制固定置顶和掉落配置（不可通过设置界面或.env修改）
    # on_top=True: 保证宠物窗口始终在最上层，不会被其他窗口遮挡
    # allow_drop=True: 保证拖拽释放后宠物会自然掉落到屏幕底部，符合物理效果
    app_config['on_top'] = True
    app_config['allow_drop'] = True
    # 从.env加载音量和宠物大小配置（优先级高于JSON）
    env_data = _parse_env_file()
    for field, env_key in APP_BASIC_ENV_KEYS.items():
        value = os.environ.get(env_key, env_data.get(env_key))
        if value is not None:
            try:
                app_config[field] = float(value)
            except ValueError:
                pass  # 保持默认值
    if not app_config.get('default_pet') and pets:
        app_config['default_pet'] = pets[0]
    if app_config.get('default_pet') not in pets and pets:
        app_config['default_pet'] = pets[0]
    current_pet = app_config.get('default_pet') or ''
    llm_config = _load_env_config(DEFAULT_LLM_CONFIG, LLM_ENV_KEYS)
    tts_config = _load_env_config(DEFAULT_TTS_CONFIG, TTS_ENV_KEYS)
    realtime_config = _load_env_config(DEFAULT_REALTIME_CONFIG, REALTIME_ENV_KEYS)
    typewriter_config = _load_env_config(DEFAULT_TYPEWRITER_CONFIG, TYPEWRITER_ENV_KEYS)
    chat_restore_config = _load_env_config(DEFAULT_CHAT_RESTORE_CONFIG, CHAT_RESTORE_ENV_KEYS)
    save_app_config()


def save_app_config():
    ensure_data_dir()
    SETTINGS_FILE.write_text(json.dumps(app_config, ensure_ascii=False, indent=2), encoding='utf-8')


def save_llm_config(config):
    global llm_config
    llm_config = dict(config)
    _save_env_config(llm_config, LLM_ENV_KEYS, DEFAULT_LLM_CONFIG, '# MINIPET LLM settings')


def save_tts_config(config):
    global tts_config
    tts_config = dict(config)
    _save_env_config(tts_config, TTS_ENV_KEYS, DEFAULT_TTS_CONFIG, '# MINIPET TTS settings')


def save_typewriter_config(config):
    global typewriter_config
    typewriter_config = dict(config)
    _save_env_config(typewriter_config, TYPEWRITER_ENV_KEYS, DEFAULT_TYPEWRITER_CONFIG, '# MINIPET Typewriter settings')


def save_realtime_config(config):
    global realtime_config
    realtime_config = dict(config)
    _save_env_config(realtime_config, REALTIME_ENV_KEYS, DEFAULT_REALTIME_CONFIG, '# MINIPET Realtime settings')


def save_chat_restore_config(config):
    global chat_restore_config
    chat_restore_config = dict(config)
    _save_env_config(chat_restore_config, CHAT_RESTORE_ENV_KEYS, DEFAULT_CHAT_RESTORE_CONFIG, '# MINIPET ChatRestore settings')
