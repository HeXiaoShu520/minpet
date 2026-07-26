# miniPet 软件架构

本文档说明 miniPet 当前源码目录、模块职责和后续拆分原则。目标是避免所有代码堆在一个目录里，让功能边界清晰、依赖方向稳定、后续维护更容易。

## 总体分层

```text
miniPet QApplication
├─ app.py                      # 应用组装和跨模块流程编排
├─ settings_window.py          # 设置窗口入口，页面正在拆入 windows/settings/
├─ config.py                   # 路径、默认配置、.env/JSON 配置加载
├─ clients/                    # 网络/API/音频客户端
├─ storage/                    # 本地数据持久化
├─ windows/                    # 独立窗口
├─ widgets/                    # 可复用 UI 组件和弹窗
├─ pet/                        # 桌宠资源、动画、角色加载
└─ protocols/                  # 外部协议和二进制协议封装
```

## 目录职责

### `clients/`

只放“与外部服务或底层设备通信”的客户端，不直接写 UI。

```text
clients/
  llm_client.py        # OpenAI 兼容聊天客户端，支持流式 delta
  tts_client.py        # 火山豆包 TTS WebSocket 与 PCM 播放
  asr_client.py        # 火山豆包 ASR WebSocket 与麦克风采集
  doubao_call_client.py   # 豆包端到端 豆包通话 WebSocket、麦克风和远端音频
  event_client.py      # OpenClaw/通用智能体事件 WebSocket 客户端
```

依赖原则：
- 可以依赖 `config.py`、`protocols/`。
- 不应依赖具体窗口类。
- 通过 Qt Signal 或函数返回结果交给 UI 层。

### `storage/`

只放本地持久化，不直接调用网络和 UI。

```text
storage/
  chat_store.py        # 聊天 JSONL、图片附件、历史内容转换
```

依赖原则：
- 可以依赖标准库和 `config.py` 中的路径。
- 不应依赖窗口、客户端、桌宠主窗口。

### `windows/`

放独立顶层窗口。

```text
windows/
  chat_window.py              # 文本聊天窗口
  doubao_call_window.py       # 豆包端到端通话窗口
  settings/
    basic_pages.py            # 基础设置、智能体设置页面
```

依赖原则：
- 窗口可以依赖 `clients/`、`storage/`、`widgets/`。
- 窗口之间尽量不直接互相依赖，统一通过 `app.py` 或 `desktop_pet.py` 组装。

### `widgets/`

放可复用控件、浮层和菜单，不直接持有全局应用流程。

```text
widgets/
  pet_input_popup.py          # 桌宠快速输入浮层
  pet_voice_popup.py          # 桌宠轻量语音聊天悬浮球
  setting_cards.py            # 设置页通用 SettingCard 控件
  ui_utils.py                 # UI 公共工具函数
  menus/
    pet_menus.py              # 右键菜单、托盘菜单、拖放意图菜单、快捷菜单、彩蛋菜单
  easter/
    base.py                   # 彩蛋弹窗基类、拖动和音效生成
    magic_conch.py            # 魔法海螺
    gacha.py                  # 桌宠扭蛋机
    dice.py                   # 3D 骰子
    coin.py                   # 抛硬币
    fortune_stick.py          # 今日求签
    wooden_fish.py            # 电子木鱼
    daily_tip.py              # 每日小技巧
    notice.py                 # 通用小游戏提示
  notifications/
    center.py                 # 通知管理器
    toast.py                  # 右下角 Toast
    bubble.py                 # 普通对话气泡
    smart_bubble.py           # 智能通知气泡
    constants.py              # 通知动画和堆叠常量
```

依赖原则：
- 可以依赖 `config.py` 和资源路径。
- 业务动作通过 Signal 或回调交给上层。
- 不应直接调用 LLM/TTS/ASR 客户端。

### `pet/`

放桌宠角色、动画和资源加载逻辑。

```text
pet/
  desktop_pet.py              # 桌宠主窗口和事件转发入口
  desktop_actions.py          # 动画线程、帧应用、尺寸重算和动作播放
  desktop_tray.py             # 系统托盘创建、菜单刷新和退出隐藏
  desktop_easter.py           # 彩蛋菜单和各彩蛋弹窗打开逻辑
  desktop_hover.py            # 鼠标横向进入检测和 hover 快捷菜单状态机
  desktop_interactions.py      # 拖放 payload、拖拽状态机、位置限制和掉落物理
  desktop_windows.py           # 聊天窗口和豆包通话窗口打开逻辑
  animation.py                # 动画线程和动作播放
  pet_assets.py               # 角色资源、动作配置和帧图加载
```

后续计划：
- 如果 `desktop_pet.py` 继续变大，再拆屏幕定位辅助或快速输入/语音入口。

### `protocols/`

放协议常量、事件规范和二进制编码/解码。

```text
protocols/
  protocol_v1.py              # miniPet 通用智能体协议 V1
  doubao_call_protocol.py        # 豆包 豆包通话二进制协议封装
```

依赖原则：
- 尽量保持纯函数/常量，不依赖 UI。
- 被 `clients/` 和 `app.py` 使用。

## 核心数据流

### 文本聊天

```text
ChatWindow / PetInputPopup
→ MiniPetApp._submit_quick_chat / ChatWindow._send
→ clients.llm_client.ChatWorker
→ storage.chat_store.ChatStore
→ NotificationCenter / ChatWindow
→ 可选 clients.tts_client.TtsWorker
```

### 本地 AI 语音聊天

```text
PetVoicePopup
→ clients.asr_client.AsrWorker
→ MiniPetApp._submit_quick_chat
→ clients.llm_client.ChatWorker
→ clients.tts_client.TtsWorker
→ PetVoicePopup 状态更新
```

### 豆包端到端通话

```text
windows.doubao_call_window.DoubaoCallWindow
→ clients.doubao_call_client.DoubaoCallWorker
→ protocols.doubao_call_protocol
→ 远端 ASR/LLM/TTS
→ DoubaoCallWindow 字幕、音频和状态更新
```

### 外部智能体事件

```text
clients.event_client.EventClient
→ protocols.protocol_v1.normalize_inbound_event
→ MiniPetApp._on_event
→ NotificationCenter / DesktopPet 动作 / 输入回调
```

## 配置策略

- `data/minipet_settings.json`：基础 UI 设置、宠物、头像、样式。
- `.env`：API Key、模型、TTS、ASR、豆包通话、打字机、高级参数。
- `APP_VOLUME` 和 `APP_SCALE` 只通过 `.env` 配置，不在设置页展示。
- `on_top` 和 `allow_drop` 固定为 `True`，不再从 `.env` 或设置页读取。

## 重构原则

1. **按功能目录归类**：新增模块必须进入合适目录，不能继续堆到 `src/` 根目录。
2. **入口保留薄层**：`app.py`、`desktop_pet.py`、`settings_window.py` 只负责组装，具体控件/客户端/存储逻辑下沉到子目录。
3. **UI 与服务解耦**：窗口和控件通过 Signal/回调使用客户端，不直接嵌入协议细节。
4. **存储与网络解耦**：`storage/` 不调用网络，`clients/` 不直接写 UI。
5. **先稳定后大拆**：每次移动模块后必须运行编译检查和主要 import 检查。

## 后续拆分计划

- `desktop_pet.py` 已移动到 `pet/desktop_pet.py`，根目录不再保留兼容入口。
- `settings_window.py` 的主要页面已拆入 `windows/settings/`：
  - `basic_pages.py`
  - `llm_page.py`
  - `role_page.py`
  - `voice_pages.py`
  - `resource_page.py`
- `notification.py` 已拆入 `widgets/notifications/`，根目录不再保留兼容入口。
- `easter_games.py`、`wooden_fish.py` 和 `fortune_stick.py` 已按具体小游戏拆入 `widgets/easter/`，根目录不再保留兼容入口。
- `pet/desktop_pet.py` 的动画线程、帧应用、尺寸重算和动作播放已下沉到 `pet/desktop_actions.py`。
- `pet/desktop_pet.py` 的托盘创建、菜单刷新和退出隐藏已下沉到 `pet/desktop_tray.py`。
- `pet/desktop_pet.py` 的彩蛋菜单和各彩蛋弹窗打开逻辑已下沉到 `pet/desktop_easter.py`。
- `pet/desktop_pet.py` 的 hover 快捷菜单状态机已下沉到 `pet/desktop_hover.py`。
- `pet/desktop_pet.py` 的拖放 payload、拖拽状态机、位置限制和掉落物理已下沉到 `pet/desktop_interactions.py`。
- `pet/desktop_pet.py` 的聊天窗口和豆包通话窗口打开逻辑已下沉到 `pet/desktop_windows.py`。
