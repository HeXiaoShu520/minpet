# coding:utf-8
"""
MiniPet 全局配置模块。

职责：
- 维护项目路径常量，例如资源目录、数据目录和 .env 文件位置。
- 定义各功能模块的默认配置。
- 从系统环境变量、.env 和 JSON 设置文件加载配置。
- 保存设置页产生的配置变更。

配置读取优先级：系统环境变量 > .env > data/minipet_settings.json > DEFAULT_* 默认值。
"""

import json
import os
from pathlib import Path

from PySide6.QtCore import QLocale

ROOT_DIR = Path(__file__).resolve().parents[1]
RES_DIR = ROOT_DIR / 'res'
DATA_DIR = ROOT_DIR / 'data'
AVATARS_DIR = DATA_DIR / 'avatars'
SETTINGS_FILE = DATA_DIR / 'minipet_settings.json'
ENV_FILE = ROOT_DIR / '.env'
DEFAULT_THEME_COLOR = '#009faa'
SCREEN_SHARE_ENABLED = False
APP_DISPLAY_NAME = 'MiniPet'
APP_ID = 'minipet'
OPENCLAW_API_URL_DEFAULT = 'http://127.0.0.1:18789/v1/responses'
OPENCLAW_MODEL_DEFAULT = 'openclaw:main'
OPENCLAW_USER_DEFAULT = 'minipet_user'
OPENCLAW_TIMEOUT_DEFAULT = 120
CUSTOM_AGENT_WS_DEFAULT = 'ws://127.0.0.1:18889/ws/minipet'

TRUE_VALUES = {'1', 'true', 'yes', 'on'}
FALSE_VALUES = {'0', 'false', 'no', 'off'}

DEFAULT_APP_CONFIG = {
    # 这两个行为固定开启，不再通过设置页或 .env 暴露，避免桌宠行为被配置成不一致。
    'on_top': True,      # 宠物窗口置顶：始终显示在其他窗口上方
    'allow_drop': True,  # 允许宠物掉落：释放鼠标后掉落到屏幕底部
    'volume': 0.4,       # 高级参数：通过 APP_VOLUME 配置，不在设置页展示
    'language_code': QLocale().name(),
    'theme_color': None,
    'default_pet': '',
    'pet_name': '',
    'scale': 1.0,        # 高级参数：通过 APP_SCALE 配置，不在设置页展示
    'pet_avatar': '',
    'user_avatar': 'user_avatar_5.png',  # 默认使用 3x3 头像切片的中心图
    'agent_backend': 'builtin',
    'openclaw_api_url': OPENCLAW_API_URL_DEFAULT,
    'openclaw_model': OPENCLAW_MODEL_DEFAULT,
    'openclaw_user': OPENCLAW_USER_DEFAULT,
    'openclaw_timeout': OPENCLAW_TIMEOUT_DEFAULT,
    'custom_agent_ws_url': CUSTOM_AGENT_WS_DEFAULT,
    'claude_code_project_dir': str(ROOT_DIR),
    'claude_code_reset_token': 0,
    'claude_code_known_sessions': [],
    'codex_project_dir': str(ROOT_DIR),
    'codex_reset_token': 0,
    'codex_thread_ids': {},
    'reply_card_style': 'aurora',
    'voice_orb_style': 'jade',
    'voice_follow_effect': 'spring',
}

DEFAULT_LLM_CONFIG = {
    'api_base': 'https://api.openai.com/v1',
    'api_key': '',
    'model': 'gpt-4o-mini',
    'memory_turns': 10,
    'system_prompt': '你是一只可爱的桌面宠物，性格活泼亲切，会用简短、口语化、带点撒娇的语气陪伴主人聊天。',
}

DEFAULT_TTS_CONFIG = {
    'enabled': False,
    'api_key': '',
    'voice_name': 'zh_female_vv_uranus_bigtts',
    'max_chars': 200,
    'test_text': '',
    'disable_emoji_filter': True,
    'max_length_to_filter_parenthesis': 100,
}

DEFAULT_VOICE_CHAT_CONFIG = {
    'continuous': False,
}

VOICE_CHAT_ENV_KEYS = {
    'continuous': 'VOICE_CHAT_CONTINUOUS',
}

DEFAULT_WAKE_WORD_CONFIG = {
    'enabled': False,
    'words': '小月小月',
    'model_dir': 'data/vosk/vosk-model-small-cn-0.22',
    'sample_rate': 16000,
    'chunk_ms': 160,
    'restart_delay_ms': 1200,
}

WAKE_WORD_ENV_KEYS = {
    'enabled': 'WAKE_WORD_ENABLED',
    'words': 'WAKE_WORDS',
    'model_dir': 'WAKE_WORD_MODEL_DIR',
    'sample_rate': 'WAKE_WORD_SAMPLE_RATE',
    'chunk_ms': 'WAKE_WORD_CHUNK_MS',
    'restart_delay_ms': 'WAKE_WORD_RESTART_DELAY_MS',
}

APP_BASIC_ENV_KEYS = {
    'volume': 'APP_VOLUME',
    'scale': 'APP_SCALE',
}

OPENCLAW_ENV_KEYS = {
    'openclaw_api_url': 'OPENCLAW_API_URL',
    'openclaw_model': 'OPENCLAW_MODEL',
    'openclaw_user': 'OPENCLAW_USER',
    'openclaw_timeout': 'OPENCLAW_TIMEOUT',
}

DEFAULT_TYPEWRITER_CONFIG = {
    'enabled': True,         # 打字机效果总开关
    'speed_ms': 28,          # 每字间隔上限（毫秒）
    'max_duration_ms': 5000, # 打字总时长上限（毫秒）
    'tts_delay_ms': 500,     # 开启语音播放时，回复延迟显示的毫秒数
}

TYPEWRITER_ENV_KEYS = {
    'enabled': 'TYPEWRITER_ENABLED',
    'speed_ms': 'TYPEWRITER_SPEED_MS',
    'max_duration_ms': 'TYPEWRITER_MAX_DURATION_MS',
    'tts_delay_ms': 'TYPEWRITER_TTS_DELAY_MS',
}

DEFAULT_DOUBAO_CALL_CONFIG = {
    'speaker': 'zh_female_vv_jupiter_bigtts',
}

LLM_ENV_KEYS = {
    'api_base': 'LLM_API_BASE',
    'api_key': 'LLM_API_KEY',
    'model': 'LLM_MODEL',
    'memory_turns': 'LLM_MEMORY_TURNS',
    'system_prompt': 'LLM_SYSTEM_PROMPT',
}

LLM_LEGACY_ENV_KEYS = {
    'LLM_MAX_TOKENS',
    'CHAT_RESTORE_ENABLED',
    'CHAT_RESTORE_MAX_MESSAGES',
    'CHAT_RESTORE_MAX_DAYS',
}

TTS_ENV_KEYS = {
    'enabled': 'TTS_ENABLED',
    'api_key': 'TTS_API_KEY',
    'voice_name': 'TTS_VOICE_NAME',
    'max_chars': 'TTS_MAX_CHARS',
    'test_text': 'TTS_TEST_TEXT',
}

DOUBAO_CALL_ENV_KEYS = {
    'speaker': 'DOUBAO_CALL_SPEAKER',
}

DOUBAO_CALL_LEGACY_ENV_KEYS = {
    'DOUBAO_CALL_ENABLED',
    'DOUBAO_CALL_MODEL',
    'DOUBAO_CALL_BOT_NAME',
    'DOUBAO_CALL_SYSTEM_ROLE',
    'DOUBAO_CALL_SPEAKING_STYLE',
    'CHAT_RESTORE_ENABLED',
    'CHAT_RESTORE_MAX_MESSAGES',
    'CHAT_RESTORE_MAX_DAYS',
    'REALTIME_ENABLED',
    'REALTIME_MODEL',
    'REALTIME_SPEAKER',
    'REALTIME_BOT_NAME',
    'REALTIME_SYSTEM_ROLE',
    'REALTIME_SPEAKING_STYLE',
}

app_config = dict(DEFAULT_APP_CONFIG)
llm_config = dict(DEFAULT_LLM_CONFIG)
tts_config = dict(DEFAULT_TTS_CONFIG)
doubao_call_config = dict(DEFAULT_DOUBAO_CALL_CONFIG)
voice_chat_config = dict(DEFAULT_VOICE_CHAT_CONFIG)
typewriter_config = dict(DEFAULT_TYPEWRITER_CONFIG)
wake_word_config = dict(DEFAULT_WAKE_WORD_CONFIG)

# 桌宠窗口运行态。历史代码直接从 config 模块读写这些状态，先保留集中入口。
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
    """确保 data 目录存在。"""
    DATA_DIR.mkdir(exist_ok=True)


def avatar_path(kind):
    """
    返回用户或宠物头像路径。

    优先使用 data/avatars 中的自定义头像；宠物头像未配置时回退到当前角色
    的 res/role/<pet>/info/pfp.png；再失败则使用内置默认图标。
    """
    key = 'user_avatar' if kind == 'user' else 'pet_avatar'
    filename = str(app_config.get(key, '') or '').strip()
    if filename:
        path = AVATARS_DIR / filename
        if path.is_file():
            return path
    if kind == 'pet' and current_pet:
        profile_path = pet_model_image_path(current_pet)
        if profile_path.is_file():
            return profile_path
    return RES_DIR / 'icons' / 'character.svg'


def _image_suffixes():
    return ('.png', '.jpg', '.jpeg', '.webp', '.bmp')


def _same_stem_image(path):
    for suffix in _image_suffixes():
        candidate = path.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def _first_image_by_key(role_dir, image_key):
    image_key = str(image_key or '').strip()
    if not image_key:
        return None
    action_dir = role_dir / 'action'
    for suffix in _image_suffixes():
        for name in (f'{image_key}_0{suffix}', f'{image_key}{suffix}'):
            candidate = action_dir / name
            if candidate.is_file():
                return candidate
    matches = []
    for suffix in _image_suffixes():
        matches.extend(action_dir.glob(f'{image_key}_*{suffix}'))
    return sorted(matches)[0] if matches else None


def _pet_default_action_image_path(role_dir):
    pet_conf_file = role_dir / 'pet_conf.json'
    act_conf_file = role_dir / 'act_conf.json'
    if not pet_conf_file.is_file() or not act_conf_file.is_file():
        return None
    try:
        pet_conf = json.loads(pet_conf_file.read_text(encoding='utf-8'))
        act_conf = json.loads(act_conf_file.read_text(encoding='utf-8'))
    except Exception:
        return None
    default_act = str(pet_conf.get('default') or 'default')
    act_data = act_conf.get(default_act) or {}
    image_key = act_data.get('images') or default_act
    return _first_image_by_key(role_dir, image_key)


def pet_model_image_path(pet_name):
    """返回角色模型自己的默认展示图。"""
    role_dir = RES_DIR / 'role' / str(pet_name or '')
    fallback = RES_DIR / 'icons' / 'character.svg'
    info_dir = role_dir / 'info'
    if info_dir.is_dir():
        info_file = info_dir / 'info.json'
        info = {}
        if info_file.is_file():
            try:
                info = json.loads(info_file.read_text(encoding='utf-8'))
            except Exception:
                info = {}
        pfp = str(info.get('pfp') or '').strip()
        if pfp:
            path = info_dir / pfp
            if path.is_file():
                return path
            same_stem = _same_stem_image(path)
            if same_stem is not None:
                return same_stem

        for cover in info.get('coverImages') or []:
            path = info_dir / str(cover)
            if path.is_file():
                return path
            same_stem = _same_stem_image(path)
            if same_stem is not None:
                return same_stem

        pfp_path = info_dir / 'pfp.png'
        if pfp_path.is_file():
            return pfp_path
        for suffix in ('*.png', '*.jpg', '*.jpeg', '*.webp', '*.bmp'):
            matches = sorted(info_dir.glob(suffix))
            if matches:
                return matches[0]

    action_image = _pet_default_action_image_path(role_dir)
    if action_image is not None:
        return action_image

    for suffix in _image_suffixes():
        try:
            match = next((role_dir / 'action').glob(f'*{suffix}'))
            return match
        except Exception:
            pass
    return fallback


def pet_display_name():
    """返回界面和聊天中展示的宠物名字，未设置时回退到当前角色目录名。"""
    return str(app_config.get('pet_name') or current_pet or '宠物').strip() or '宠物'


def get_pet_list():
    """扫描 res/role，返回包含 pet_conf.json 的可用角色名。"""
    role_dir = RES_DIR / 'role'
    if not role_dir.exists():
        return []
    pets = []
    for child in role_dir.iterdir():
        if child.is_dir() and child.name != 'sys' and (child / 'pet_conf.json').exists():
            pets.append(child.name)
    return sorted(pets)


def _strip_inline_comment(value):
    """
    移除 .env 值后面的行内注释。

    只把空白后的 # 当作注释起点，避免误删 URL、颜色值等合法内容。
    例如：APP_VOLUME=0.7    # 音量设置 -> 0.7
    """
    quote = ''
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == '\\':
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ''
            continue
        if char in ('"', "'"):
            quote = char
            continue
        if char == '#' and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.strip()


def _parse_env_file():
    """读取项目根目录 .env，返回键值字典。"""
    data = {}
    if not ENV_FILE.is_file():
        return data
    with ENV_FILE.open('r', encoding='utf-8') as file:
        for line in file:
            raw = line.strip()
            if not raw or raw.startswith('#') or '=' not in raw:
                continue
            key, value = raw.split('=', 1)
            value = _strip_inline_comment(value).strip().strip('"').strip("'").replace('\\n', '\n')
            data[key.strip()] = value
    return data


def _coerce_env_value(value, default):
    """按默认值类型把 .env 字符串转换成 bool/int/float/str。"""
    if isinstance(default, bool):
        normalized = str(value).strip().lower()
        if normalized in TRUE_VALUES:
            return True
        if normalized in FALSE_VALUES:
            return False
        return default
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return value


def _load_env_config(defaults, env_keys):
    """按 env_keys 映射从系统环境变量和 .env 加载一组配置。"""
    env_data = _parse_env_file()
    cfg = dict(defaults)
    for field, env_key in env_keys.items():
        value = os.environ.get(env_key, env_data.get(env_key))
        if value is None:
            continue
        cfg[field] = _coerce_env_value(value, defaults[field])
    return cfg


def _save_env_config(config_data, env_keys, defaults, section_title, extra_managed_keys=None):
    """
    将一组配置写回 .env，同时保留其他未知配置项。

    设置页保存时只替换当前 section 管理的键，避免覆盖用户手写的其他配置、
    注释和暂未被 MiniPet 管理的服务密钥。
    """
    existing = []
    if ENV_FILE.is_file():
        existing = ENV_FILE.read_text(encoding='utf-8').splitlines()

    managed_keys = set(env_keys.values())
    if extra_managed_keys:
        managed_keys.update(extra_managed_keys)
    kept = []
    for line in existing:
        stripped = line.strip()
        if stripped == section_title:
            continue
        if '=' in stripped and not stripped.startswith('#'):
            key = stripped.split('=', 1)[0].strip()
            if key in managed_keys:
                continue
        kept.append(line)

    if kept and kept[-1].strip():
        kept.append('')
    kept.append(section_title)
    for field, env_key in env_keys.items():
        value = str(config_data.get(field, defaults[field])).replace('\n', '\\n')
        kept.append(f'{env_key}={value}')
    ENV_FILE.write_text('\n'.join(kept).rstrip() + '\n', encoding='utf-8')


def load():
    """加载所有配置，并初始化当前宠物等运行时状态。"""
    global app_config, llm_config, tts_config, doubao_call_config, voice_chat_config, typewriter_config, wake_word_config, current_pet
    ensure_data_dir()
    pets = get_pet_list()

    app_config = dict(DEFAULT_APP_CONFIG)
    if SETTINGS_FILE.is_file():
        try:
            app_config.update(json.loads(SETTINGS_FILE.read_text(encoding='utf-8')))
        except Exception:
            pass

    # 固定置顶和掉落配置，不允许旧 JSON、环境变量或设置页覆盖。
    app_config['on_top'] = True
    app_config['allow_drop'] = True
    app_config.pop('voice_follow_level', None)

    # 音量和缩放属于高级参数，只从环境变量/.env 读取，优先级高于 JSON。
    env_data = _parse_env_file()
    for field, env_key in APP_BASIC_ENV_KEYS.items():
        value = os.environ.get(env_key, env_data.get(env_key))
        if value is not None:
            app_config[field] = _coerce_env_value(value, DEFAULT_APP_CONFIG[field])
    for field, env_key in OPENCLAW_ENV_KEYS.items():
        value = os.environ.get(env_key, env_data.get(env_key))
        if value is not None:
            app_config[field] = _coerce_env_value(value, DEFAULT_APP_CONFIG[field])

    if not app_config.get('default_pet') and pets:
        app_config['default_pet'] = pets[0]
    if app_config.get('default_pet') not in pets and pets:
        app_config['default_pet'] = pets[0]
    current_pet = app_config.get('default_pet') or ''

    llm_config = _load_env_config(DEFAULT_LLM_CONFIG, LLM_ENV_KEYS)
    tts_config = _load_env_config(DEFAULT_TTS_CONFIG, TTS_ENV_KEYS)
    doubao_call_config = _load_env_config(DEFAULT_DOUBAO_CALL_CONFIG, DOUBAO_CALL_ENV_KEYS)
    voice_chat_config = _load_env_config(DEFAULT_VOICE_CHAT_CONFIG, VOICE_CHAT_ENV_KEYS)
    typewriter_config = _load_env_config(DEFAULT_TYPEWRITER_CONFIG, TYPEWRITER_ENV_KEYS)
    wake_word_config = _load_env_config(DEFAULT_WAKE_WORD_CONFIG, WAKE_WORD_ENV_KEYS)
    save_app_config()


def save_app_config():
    """保存基础设置到 data/minipet_settings.json。"""
    ensure_data_dir()
    SETTINGS_FILE.write_text(json.dumps(app_config, ensure_ascii=False, indent=2), encoding='utf-8')


def codex_thread_key(project_dir, reset_token=0):
    project_key = os.path.normcase(os.path.abspath(str(project_dir or ROOT_DIR))).replace('\\', '/')
    return '%s#reset:%s' % (project_key, int(reset_token or 0))


def get_codex_thread_id(project_dir, reset_token=0):
    thread_ids = app_config.get('codex_thread_ids') or {}
    return str(thread_ids.get(codex_thread_key(project_dir, reset_token)) or '').strip()


def set_codex_thread_id(project_dir, reset_token, thread_id):
    thread_ids = dict(app_config.get('codex_thread_ids') or {})
    key = codex_thread_key(project_dir, reset_token)
    thread_id = str(thread_id or '').strip()
    if thread_id:
        thread_ids[key] = thread_id
    else:
        thread_ids.pop(key, None)
    app_config['codex_thread_ids'] = thread_ids
    save_app_config()


def save_llm_config(config):
    """保存大模型配置到 .env。"""
    global llm_config
    llm_config = dict(config)
    _save_env_config(llm_config, LLM_ENV_KEYS, DEFAULT_LLM_CONFIG, '# MiniPet LLM settings', LLM_LEGACY_ENV_KEYS)


def save_tts_config(config):
    """保存 TTS 配置到 .env。"""
    global tts_config
    tts_config = dict(config)
    _save_env_config(tts_config, TTS_ENV_KEYS, DEFAULT_TTS_CONFIG, '# MiniPet TTS settings')


def save_typewriter_config(config):
    """保存回复逐字显示配置到 .env。"""
    global typewriter_config
    typewriter_config = dict(config)
    _save_env_config(typewriter_config, TYPEWRITER_ENV_KEYS, DEFAULT_TYPEWRITER_CONFIG, '# MiniPet Typewriter settings')


def save_doubao_call_config(config):
    """保存豆包通话音色配置到 .env。"""
    global doubao_call_config
    doubao_call_config = dict(config)
    _save_env_config(doubao_call_config, DOUBAO_CALL_ENV_KEYS, DEFAULT_DOUBAO_CALL_CONFIG, '# MiniPet DoubaoCall settings', DOUBAO_CALL_LEGACY_ENV_KEYS)


def save_voice_chat_config(config):
    """保存本地 AI 语音聊天配置到 .env。"""
    global voice_chat_config
    voice_chat_config = dict(config)
    _save_env_config(voice_chat_config, VOICE_CHAT_ENV_KEYS, DEFAULT_VOICE_CHAT_CONFIG, '# MiniPet VoiceChat settings')


def save_wake_word_config(config):
    """保存离线唤醒词配置到 .env。"""
    global wake_word_config
    wake_word_config = dict(config)
    _save_env_config(wake_word_config, WAKE_WORD_ENV_KEYS, DEFAULT_WAKE_WORD_CONFIG, '# MiniPet WakeWord settings')
