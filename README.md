# miniPet

miniPet 是一个独立桌面 AI 宠物应用。它由 MINIPET 简化整合而来，把桌宠窗口、动画、右键菜单、系统设置、AI 对话、语音播报、语音聊天、实时通话、通知气泡和外部事件接入统一收敛到 `miniPet/` 内，形成可以单独维护和发布的整体。

## 参考
基于呆啵宠物 DyberPet开发 https://github.com/ChaozhongLiu/DyberPet

> 当前目标：`miniPet/` 是独立应用目录。源码、资源、文档、依赖样例和启动入口都已收敛到这里；后续功能不要再依赖外层 MINIPET 结构。

## 当前功能

### 桌面宠物

- 桌面透明宠物窗口
- 宠物动画播放
- 鼠标拖拽、掉落、找回宠物
- 双击宠物弹出沉浸式快速输入浮层，Enter 发送，Esc 关闭
- 输入文字后，宠物回复会以通知卡片式头顶气泡显示，并带淡入/上移动画
- 如果已配置并启用 TTS，回复会同时语音播报
- 鼠标移到桌面宠物上自动弹出极简图标菜单，右键也可立即弹出
  - 设置
  - 文本聊天
  - 语音聊天
  - 实时通话
  - 退出
- 右下角托盘菜单保留完整功能
  - 设置、聊天、语音聊天、实时通话、动作播放、角色切换、找回宠物、退出

### AI 文本聊天

- 独立聊天窗口
- 双方头像与消息块
- Markdown 内容渲染
- 流式输出
- `Enter` 发送，`Shift+Enter` 换行
- 支持 OpenAI 兼容接口
- 支持 Anthropic Claude 原生接口（含多模态图片）
- 可通过 System Prompt 定义宠物性格
- 可选 TTS 自动播报回复
- 支持粘贴或拖入图片，发送时一并传给大模型（Anthropic 走 base64 原生图片块，OpenAI 走 image_url）
- 快速输入浮层支持粘贴图片，弹窗内显示缩略图预览
- 支持在基础设置中自定义用户头像和宠物头像，选择后会立即显示图片预览

### 语音聊天（本地 AI 模式）

这是 miniPet 的“自己的脑子”模式。

链路：

```text
麦克风
→ 豆包流式 ASR WebSocket 识别
→ miniPet 本地/自定义 LLM 思考
→ 火山豆包 TTS 播放
```

特点：

- 使用火山豆包纯 ASR 服务，只做语音转文字
- 复用 `TTS_API_KEY` 鉴权
- 使用当前 `LLM_PROVIDER / LLM_API_BASE / LLM_MODEL` 配置生成回复
- 能吃到 miniPet 的角色设定、记忆和本地聊天上下文
- 进入语音聊天会先播放欢迎语“你好呀，有什么需要帮忙的吗”，播放完成后再开始语音识别
- 欢迎语按音色缓存到 `data/tts_welcome/`，已有缓存会直接播放，没有时才合成一次
- 回复后复用现有 TTS 播放
- UI 是纯净通话卡片风格，麦克风是开关，不需要按住说话
- 用户语音识别内容显示在状态行，AI 回复显示在下方字幕区
- 播放语音时会显示“打断”按钮，可立即停止当前语音输出

当前 ASR 接口：

```text
wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
```

当前 ASR 资源：

```text
volc.seedasr.sauc.duration
```

### 实时通话（豆包端到端模式）

这是“豆包自己听、自己想、自己说”的低延迟模式。

链路：

```text
麦克风
→ 豆包端到端 Realtime WebSocket
→ 豆包 ASR + 豆包模型思考 + 豆包 TTS
→ 本地播放
```

特点：

- 低延迟，更接近豆包原生通话体验
- 不走本地 LLM，因此不会使用 miniPet 配置的 OpenAI/Claude/DeepSeek 等模型
- 适合快速闲聊或备用通话
- 复用 `TTS_API_KEY` 鉴权
- 默认固定使用 O2.0 通用对话模型 `1.2.1.1`
- O2.0 模式下开启 `enable_music`，支持服务端唱歌能力触发
- 支持音色、角色背景和说话风格配置
- UI 是纯净通话卡片风格
- 用户语音识别内容显示在状态行，AI 回复在下方字幕区流式显示
- 播放语音时会显示“打断”按钮，可中断当前输出
- 支持多屏共享选择的本地交互状态

当前 Realtime 接口：

```text
wss://openspeech.bytedance.com/api/v3/realtime/dialogue
```

当前 Realtime 资源：

```text
volc.speech.dialog
```

注意：当前豆包端到端 Realtime 文档只定义了语音输入输出事件，miniPet 的“共享屏幕”按钮目前实现了本地多屏选择和状态显示；如果要让 AI 理解屏幕内容，需要后续再接入视觉模型或支持视觉上下文的 ASR/LLM 通道。

### 语音播报 TTS

- 使用火山豆包 TTS 单向流式 WebSocket 接口
- 每段待播报文本建立一次单向流连接，边接收 PCM 音频边播放
- 支持开关自动播报
- 支持音色选择
- 支持本地缓存预览音频
- 支持语音聊天欢迎语缓存，缓存路径为 `data/tts_welcome/`
- 普通文本聊天和语音聊天都会复用它播报回复
- 普通 TTS 不使用双向长连接；双向链路只保留在“实时通话”端到端模式中

当前 TTS 接口：

```text
wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream
```

### 通知与外部事件

miniPet 可以作为独立桌宠运行，也可以可选连接外部事件源。

默认事件 WebSocket 地址：

```text
ws://localhost:18888/ws/pet
```

支持事件类型：

- `message`：显示智能气泡，支持标题、发送人、摘要、建议和按钮
- `bubble`：显示普通宠物气泡
- `action`：触发宠物动作

用户点击智能气泡按钮时，可以回调外部服务：

```text
POST http://localhost:18888/actions/execute
```

如果外部服务不在线，miniPet 仍可独立运行。

## 系统架构

```text
miniPet QApplication
├─ DesktopPet
│  ├─ 桌宠透明窗口
│  ├─ 快捷图标菜单
│  ├─ 右键/托盘菜单
│  ├─ ChatWindow          文本聊天
│  ├─ VoiceChatWindow     语音聊天：ASR → 本地 LLM → TTS
│  └─ RealtimeWindow      实时通话：豆包端到端
├─ SettingsWindow
│  ├─ BasicPage           基础设置
│  ├─ LLMPage             大模型配置
│  ├─ RolePage            角色与记忆
│  ├─ TTSPage             火山豆包 TTS
│  ├─ RealtimePage        豆包端到端实时通话配置
│  └─ RoleToolsPage       角色资源
├─ ChatStore              本地聊天历史和图片持久化
├─ NotificationCenter     气泡与智能通知
└─ EventClient            外部事件 WebSocket 客户端
```

核心数据流：

```text
文本聊天：
用户输入 → ChatWorker → LLM API → ChatWindow/气泡 → 可选 TTS

语音聊天：
麦克风 → AsrWorker → ASR WebSocket → ChatWorker → LLM API → TtsWorker → 播放

实时通话：
麦克风 → RealtimeWorker → 豆包端到端 WebSocket → 远端音频流 → 播放

外部事件：
EventClient → NotificationCenter → 气泡/动作/聊天入口
```

## 运行

建议 Python 3.9 到 3.12。

在项目根目录安装依赖：

```bash
pip install -r requirements.txt
```

启动：

```bash
python run_miniPet.py
```

如果你在外层仓库目录运行，也可以直接指定内部入口：

```bash
python miniPet/run_miniPet.py
```

## 配置

### 应用设置

基础设置保存到 miniPet 内部数据目录：

```text
miniPet/data/minipet_settings.json
```

### 大模型配置

大模型配置从环境变量或 `.env` 读取，并可在设置页保存。

```text
LLM_PROVIDER=openai
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini
LLM_MAX_TOKENS=1024
LLM_SYSTEM_PROMPT=你是一只可爱的桌面宠物，性格活泼亲切，会用简短、口语化、带点撒娇的语气陪伴主人聊天。
LLM_MEMORY_PROMPT=
```

`LLM_PROVIDER` 可选：

- `openai`：OpenAI 兼容 Chat Completions API
- `anthropic`：Claude 原生 Messages API

### 语音配置

TTS、ASR 和 Realtime 当前复用同一个火山语音 API Key：

```text
TTS_ENABLED=false
TTS_API_KEY=
TTS_VOICE_NAME=zh_female_vv_uranus_bigtts
TTS_MAX_CHARS=500
```

用途：

- `TTS_API_KEY` 用于豆包 TTS 单向流式 WebSocket
- `TTS_API_KEY` 同时用于豆包 ASR WebSocket
- `TTS_API_KEY` 同时用于豆包 Realtime WebSocket

### 实时通话配置

实时通话配置也从 `.env` 读取，并可在设置页保存。设置页只暴露音色、角色背景和说话风格；实时通话入口不再依赖单独的启用开关，模型固定为 O2.0 通用对话 `1.2.1.1`。

```text
REALTIME_ENABLED=true
REALTIME_MODEL=1.2.1.1
REALTIME_SPEAKER=zh_female_vv_jupiter_bigtts
REALTIME_BOT_NAME=miniPet
REALTIME_SYSTEM_ROLE=你是一只可爱的桌面宠物，陪伴用户聊天，回答要简短自然。
REALTIME_SPEAKING_STYLE=语气活泼、亲切、口语化。
```

当前欢迎词固定为：

```text
你好呀，有什么需要帮忙的吗？
```

## 这轮我们做了什么

- 修复多模态图片消息链路：Anthropic 现在收到真实 base64 图片块，不再是占位文字
- 快速输入浮层粘贴图片后显示缩略图预览
- 图片编码统一改为 JPEG 85 质量压缩，避免超出 5MB 限制
- 接入豆包端到端 Realtime WebSocket
- 新增 `实时通话` 功能
- 将 Realtime 鉴权改为复用 `TTS_API_KEY`
- 修正 Realtime 连接事件帧，不再在二进制 optional 里重复写 `connect_id`
- 新增纯净通话 UI
- 支持麦克风自动收音模式，由服务端 VAD 自动识别有没有输入
- 支持多屏共享选择的本地交互
- 接入豆包纯 ASR WebSocket
- 新增 `语音聊天` 功能：ASR → 本地 LLM → TTS
- 保留两种语音模式：豆包端到端模式与本地 AI 模式
- 语音聊天新增欢迎语缓存播放，先播欢迎词再开始语音识别
- 语音聊天和实时通话都支持播放时打断当前语音输出
- 调整通话窗口字幕：用户识别文本显示在状态行，AI 回复显示在下方区域
- 调整实时通话设置页，固定 O2.0 模型并精简启用、模型和 Bot 名称配置项
- 基础设置头像选择增加图片预览
- 更新桌宠快捷菜单、右键菜单、退出清理逻辑

## 目录职责

```text
miniPet/
  run_miniPet.py       # 启动入口
  requirements.txt     # Python 依赖
  README.md            # 项目说明
  MINIPET_INTERFACE_PROTOCOL.md
  PET_EVENT_PROTOCOL.md
  src/
    miniPet/
      app.py                 # QApplication 组装入口
      desktop_pet.py         # 桌面宠物窗口、菜单、拖拽和掉落
      animation.py           # 动画线程和动作播放
      pet_assets.py          # 角色资源、动作配置加载
      settings_window.py     # 系统设置窗口
      chat_window.py         # 文本 AI 对话窗口
      voice_chat_window.py   # 语音聊天窗口，本地 AI 模式
      realtime_window.py     # 实时通话窗口，豆包端到端模式
      llm_client.py          # OpenAI/Anthropic 聊天客户端，支持流式输出
      asr_client.py          # 豆包流式 ASR WebSocket 客户端
      tts_client.py          # 火山豆包 TTS 单向流式 WebSocket 客户端和 PCM 播放
      realtime_client.py     # 豆包端到端 Realtime WebSocket 客户端
      realtime_protocol.py   # Realtime 二进制协议封装
      notification.py        # 通知、气泡、智能气泡
      event_client.py        # 外部事件 WebSocket 客户端
      config.py              # 配置、路径和环境变量
  res/                  # 图标、角色、宠物、道具资源
  docs/                 # 资源制作文档
  data/                 # 本地运行配置、聊天历史、音频预览缓存
```

## 资源目录

运行资源已内置到 `miniPet/`：

```text
miniPet/
  res/
    icons/
    role/
    pet/
    items/
  docs/
  data/
```

`config.py` 位于 `src/miniPet/`，但应用根目录仍是外层 `miniPet/`：

```python
ROOT_DIR = Path(__file__).resolve().parents[2]
RES_DIR = ROOT_DIR / 'res'
DATA_DIR = ROOT_DIR / 'data'
ENV_FILE = ROOT_DIR / '.env'
```

因此删除外层 `res/` 后，miniPet 仍会读取内部资源。

## 外部事件示例

```json
{
  "type": "message",
  "title": "模拟事件",
  "sender": "mock",
  "summary": "这是一条高优先级提醒",
  "suggestion": "点击按钮可以执行动作",
  "priority": "high",
  "actions": [
    { "id": "ignore", "label": "忽略" },
    { "id": "later", "label": "稍后" }
  ]
}
```

miniPet 收到后会显示智能气泡，并根据 `priority` 或 `pet_action` 触发动作。

## 开发原则

- 新功能代码进入 `miniPet/src/miniPet/`，资源进入 `miniPet/res/`，文档进入 `miniPet/docs/`。
- 不再依赖外层 `MINIPET/` 的 Python 模块。
- 复用原 MINIPET 的资源格式，但资源最终要迁移到 `miniPet/res/`。
- 设置页、菜单、聊天窗口和语音窗口要保持完整视觉体验，不使用裸表单堆控件。
- 外部事件源是可选插件，不是 miniPet 的运行依赖。

## License

MIT
