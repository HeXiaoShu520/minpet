# miniPet

miniPet 是一个独立桌面 AI 宠物应用。它由 MINIPET 简化整合而来，把桌宠窗口、动画、右键菜单、系统设置、AI 对话、语音播报、语音聊天、豆包通话、通知气泡和外部事件接入统一收敛到 `miniPet/` 内，形成可以单独维护和发布的整体。

## 参考
基于呆啵宠物 DyberPet开发 https://github.com/ChaozhongLiu/DyberPet

木鱼小组件参考 CyberZen（赛博木鱼）工程的桌面悬浮木鱼交互、功德飘字和木鱼资源组织思路：https://github.com/Litt1eQ/cyber-zen

木鱼音效参考 Electronic Wooden Fish 工程：https://github.com/xiwang-online/Electronic-Wooden-Fish

第三方资源和许可证说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

> 当前目标：`miniPet/` 是独立应用目录。源码、资源、文档、依赖样例和启动入口都已收敛到这里；后续功能不要再依赖外层 MINIPET 结构。

## OpenClaw 中转

miniPet 可以通过简化中转脚本接入 OpenClaw HTTP Responses API。这个脚本复用了 `OpenClaw Gui_new` 的调用方式：`POST http://127.0.0.1:18789/v1/responses`。

1. 启动 OpenClaw Gateway，并启用 Responses API：

```bash
openclaw config set gateway.http.endpoints.responses.enabled true
openclaw gateway run
```

2. 启动 miniPet adapter：

```bash
python tools/minipet_adapter.py
```

3. 启动 miniPet。miniPet 默认连接 `ws://localhost:18888/ws/pet`，会连到 adapter。用户对宠物输入或拖拽投喂后，adapter 会转发给 OpenClaw，并把回复发回宠物显示。

可选环境变量：

```text
OPENCLAW_API_URL=http://127.0.0.1:18789/v1/responses
OPENCLAW_GATEWAY_TOKEN=<token>
OPENCLAW_USER=minipet_adapter_user
MINIPET_ADAPTER_HOST=127.0.0.1
MINIPET_ADAPTER_PORT=18888
```

如果未设置 `OPENCLAW_GATEWAY_TOKEN`，adapter 会自动读取 `~/.openclaw/openclaw.json` 中的 `gateway.auth.token`。

## miniClaw 接入

miniPet 可以把桌宠输入交给相邻项目 miniClaw 处理。此模式下 miniPet 作为 WebSocket 客户端，miniClaw 作为本地 FastAPI/WebSocket 服务端。

1. 启动 miniClaw：

```bash
cd E:/源丶工程/miniClaw
python main.py
```

miniClaw 默认会同时启动 miniPet 网关：

```text
ws://127.0.0.1:18889/ws/minipet
```

可用健康检查确认网关已启动：

```bash
curl http://127.0.0.1:18889/health
```

预期返回：

```json
{"ok": true}
```

2. 启动 miniPet，打开“设置 → 智能体设置”：

- 智能体选项：`miniClaw / 通用 AI 后端`
- miniClaw / 通用后端地址：`ws://127.0.0.1:18889/ws/minipet`

保存后，miniPet 会连接 miniClaw。连接成功时会显示“后端已就绪：miniClaw”。

3. 在桌宠输入框中发送内容。

链路如下：

```text
miniPet user.command
→ miniClaw /ws/minipet
→ miniClaw LLM/Agent
→ surface.show 创建气泡
→ surface.update 流式更新气泡
→ surface.update done=true 完成
```

miniPet 使用 `surface_id` 追踪同一个气泡，因此 miniClaw 的流式回复会在同一个气泡里持续刷新，不会生成多条气泡。

miniClaw 侧可选环境变量：

```text
DESKTOP_API_ENABLED=true
DESKTOP_API_HOST=127.0.0.1
DESKTOP_API_PORT=18889
```

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
  - 豆包通话
  - 退出
- 右下角托盘菜单保留完整功能
  - 设置、聊天、语音聊天、豆包通话、动作播放、角色切换、找回宠物、退出

### AI 文本聊天

- 独立聊天窗口
- 双方头像与消息块
- Markdown 内容渲染
- 流式输出
- `Enter` 发送，`Shift+Enter` 换行
- 支持 OpenAI 兼容接口
- 支持 Anthropic Claude 原生接口（含多模态图片）
- 可通过 System Prompt 定义宠物性格
- 支持自动总结：不保存完整聊天历史，只从最近对话中提取少量长期有用信息
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
- 菜单语音入口会打开语音球；语音球存在时才启用语音功能
- 可选离线唤醒词监听：打开语音球后，本地 Vosk 小模型识别“小月小月”，命中后再打开火山流式 ASR，避免云端 ASR 常驻计费
- 如果未开启唤醒词，打开语音球后会直接启动一次火山流式接听
- 可选连续对话：回复完成后自动进入下一轮接听；关闭时回到语音球待机
- 识别到“唱歌、唱一首、来首歌、唱两句、哼一段”等关键词时，会临时切到 豆包通话 O2.0 单次唱歌模式，播放完成后自动回到语音球待机，不受连续对话影响
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

### 豆包通话（豆包端到端模式）

这是“豆包自己听、自己想、自己说”的低延迟模式。

链路：

```text
麦克风
→ 豆包端到端 豆包通话 WebSocket
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

当前 豆包通话接口：

```text
wss://openspeech.bytedance.com/api/v3/realtime/dialogue
```

当前 豆包通话资源：

```text
volc.speech.dialog
```

注意：当前豆包端到端 豆包通话文档只定义了语音输入输出事件，miniPet 的“共享屏幕”按钮目前实现了本地多屏选择和状态显示；如果要让 AI 理解屏幕内容，需要后续再接入视觉模型或支持视觉上下文的 ASR/LLM 通道。

### 语音播报 TTS

- 使用火山豆包 TTS 单向流式 WebSocket 接口
- 每段待播报文本建立一次单向流连接，边接收 PCM 音频边播放
- 支持开关自动播报
- 支持音色选择
- 支持本地缓存预览音频
- 支持语音聊天欢迎语缓存，缓存路径为 `data/tts_welcome/`
- 普通文本聊天和语音聊天都会复用它播报回复
- 普通 TTS 不使用双向长连接；双向链路只保留在“豆包通话”端到端模式中

当前 TTS 接口：

```text
wss://openspeech.bytedance.com/api/v3/tts/unidirectional/stream
```

### 自动总结

- 不保存完整聊天历史，只在当前运行中保留最近对话作为短期上下文
- 自动总结是可选功能，可在“设置 → 角色 → 自动总结”里开关
- 开启后，每隔几次用户发言，会从最近对话中总结少量长期有用信息
- 总结重点保存到 `data/memory/memories.json`，后续会拼入大模型系统提示
- 设置页“角色”可查看、编辑和删除总结重点
- 清空当前对话只清掉短期上下文，不会删除已保存的总结重点
- 详细设计见 [自动总结设计](记忆与历史设计.md)

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

当前源码已经按功能目录解耦，不再把所有模块堆在 `src/miniPet/` 根目录。详细说明见 [软件架构文档](ARCHITECTURE.md)。

```text
miniPet QApplication
├─ app.py                         应用组装和跨模块流程编排
├─ pet/desktop_pet.py             桌宠主窗口和事件转发入口
├─ pet/desktop_actions.py         动画线程、帧应用、尺寸重算和动作播放
├─ pet/desktop_tray.py            系统托盘创建、菜单刷新和退出隐藏
├─ pet/desktop_easter.py          彩蛋菜单和各彩蛋弹窗打开逻辑
├─ pet/desktop_hover.py           鼠标横向进入检测和 hover 快捷菜单状态机
├─ pet/desktop_interactions.py     拖放 payload、拖拽状态机、位置限制和掉落物理
├─ pet/desktop_windows.py          聊天窗口和豆包通话窗口打开逻辑
├─ settings_window.py             设置窗口入口
├─ clients/                       LLM / TTS / ASR / 豆包通话 / 外部事件客户端
├─ storage/                       聊天记录和自动总结记忆存储
├─ windows/                       文本聊天、豆包通话、设置页等顶层窗口
├─ widgets/                       快速输入、语音球、菜单、通知、彩蛋等 UI 组件
├─ pet/                           动画线程和角色资源加载
└─ protocols/                     miniPet V1 协议和豆包 豆包通话二进制协议
```

核心数据流：

```text
文本聊天：
windows.chat_window.ChatWindow / widgets.pet_input_popup.PetInputPopup
→ clients.llm_client.ChatWorker → LLM API → storage.chat_store.ChatStore
→ ChatWindow/气泡 → 可选 clients.tts_client.TtsWorker

语音聊天：
widgets.pet_voice_popup.PetVoicePopup
→ clients.asr_client.AsrWorker → ASR WebSocket
→ clients.llm_client.ChatWorker → clients.tts_client.TtsWorker → 播放

唱歌关键词：
widgets.pet_voice_popup.PetVoicePopup
→ clients.asr_client.AsrWorker → 命中唱歌意图
→ clients.doubao_call_client.DoubaoCallWorker 单次文本任务 → O2.0 enable_music 音频流 → 播放

豆包通话：
windows.doubao_call_window.DoubaoCallWindow
→ clients.doubao_call_client.DoubaoCallWorker → 豆包端到端 WebSocket → 远端音频流 → 播放

外部事件：
clients.event_client.EventClient → protocols.protocol_v1
→ NotificationCenter → 气泡/动作/聊天入口
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

大模型配置从环境变量或 `.env` 读取，并可在设置页保存。自动总结是可选功能，可在“设置 → 角色 → 自动总结”里开关；开关和频率也随大模型配置保存。

```text
LLM_PROVIDER=openai
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini
LLM_MAX_TOKENS=1024
LLM_SYSTEM_PROMPT=你是一只可爱的桌面宠物，性格活泼亲切，会用简短、口语化、带点撒娇的语气陪伴主人聊天。
LLM_MEMORY_PROMPT=
LLM_AUTO_MEMORY_ENABLED=true
LLM_AUTO_MEMORY_EVERY_N_USER_TURNS=3
LLM_AUTO_MEMORY_RECENT_MESSAGES=12
LLM_AUTO_MEMORY_MAX_ITEMS_PER_PASS=3
```

`LLM_PROVIDER` 可选：

- `openai`：OpenAI 兼容 Chat Completions API
- `anthropic`：Claude 原生 Messages API

### 语音配置

TTS、ASR 和 豆包通话当前复用同一个火山语音 API Key：

```text
TTS_ENABLED=false
TTS_API_KEY=
TTS_VOICE_NAME=zh_female_vv_uranus_bigtts
TTS_MAX_CHARS=500
TTS_TEST_TEXT=
VOICE_CHAT_CONTINUOUS=false
WAKE_WORD_ENABLED=false
WAKE_WORDS=小月小月
```

用途：

- `TTS_API_KEY` 用于豆包 TTS 单向流式 WebSocket
- `TTS_TEST_TEXT` 控制设置页“测试语音”的自定义试听文本；留空时使用当前音色的默认预览文案
- `TTS_API_KEY` 同时用于豆包 ASR WebSocket
- `TTS_API_KEY` 同时用于豆包 豆包通话 WebSocket
- `VOICE_CHAT_CONTINUOUS` 控制回复完成后是否继续接听下一轮；关闭时回到语音球待机
- `WAKE_WORD_ENABLED` 开启后，语音球打开时使用本地 Vosk 模型监听唤醒词，不调用火山 ASR
- Vosk 中文小模型固定读取 `data/vosk/vosk-model-small-cn-0.22`

### 豆包通话配置

豆包通话配置也从 `.env` 读取，并可在设置页保存。设置页只暴露音色、角色背景和说话风格；豆包通话入口不再依赖单独的启用开关，模型固定为 O2.0 通用对话 `1.2.1.1`。

```text
DOUBAO_CALL_ENABLED=true
DOUBAO_CALL_MODEL=1.2.1.1
DOUBAO_CALL_SPEAKER=zh_female_vv_jupiter_bigtts
DOUBAO_CALL_BOT_NAME=miniPet
DOUBAO_CALL_SYSTEM_ROLE=你是一只可爱的桌面宠物，陪伴用户聊天，回答要简短自然。
DOUBAO_CALL_SPEAKING_STYLE=语气活泼、亲切、口语化。
```

当前欢迎词固定为：

```text
你好呀，有什么需要帮忙的吗？
```

## 这轮我们做了什么

- 修复多模态图片消息链路：Anthropic 现在收到真实 base64 图片块，不再是占位文字
- 快速输入浮层粘贴图片后显示缩略图预览
- 图片编码统一改为 JPEG 85 质量压缩，避免超出 5MB 限制
- 接入豆包端到端 豆包通话 WebSocket
- 新增 `豆包通话` 功能
- 将 豆包通话鉴权改为复用 `TTS_API_KEY`
- 修正 豆包通话连接事件帧，不再在二进制 optional 里重复写 `connect_id`
- 新增纯净通话 UI
- 支持麦克风自动收音模式，由服务端 VAD 自动识别有没有输入
- 支持多屏共享选择的本地交互
- 接入豆包纯 ASR WebSocket
- 新增 `语音聊天` 功能：ASR → 本地 LLM → TTS
- 保留两种语音模式：豆包端到端模式与本地 AI 模式
- 语音聊天新增欢迎语缓存播放，先播欢迎词再开始语音识别
- 语音聊天和豆包通话都支持播放时打断当前语音输出
- 调整通话窗口字幕：用户识别文本显示在状态行，AI 回复显示在下方区域
- 调整豆包通话设置页，固定 O2.0 模型并精简启用、模型和 Bot 名称配置项
- 基础设置头像选择增加图片预览
- 新增自动总结重点管理
- 去掉默认历史记录逻辑，只保留当前运行短期上下文和自动总结重点
- 更新桌宠快捷菜单、右键菜单、退出清理逻辑

## 目录职责

```text
miniPet/
  run_miniPet.py          # 启动入口
  requirements.txt        # Python 依赖
  README.md               # 项目说明
  ARCHITECTURE.md        # 软件架构、模块边界和重构原则
  docs/
    art_dev.md            # 角色资源制作文档
  src/
    miniPet/
      app.py              # QApplication 组装入口
      config.py           # 配置、路径和环境变量
      settings_window.py  # 设置窗口入口，页面逐步拆入 windows/settings/
      base_page.py        # 设置页滚动基类
      typewriter.py       # 打字机文字显示效果
      clients/            # 外部 API、WebSocket、音频设备客户端
        llm_client.py
        tts_client.py
        asr_client.py
        doubao_call_client.py
        event_client.py
      storage/            # 本地持久化
        chat_store.py
        memory_store.py
      windows/            # 独立顶层窗口
        chat_window.py
        doubao_call_window.py
        settings/
          basic_pages.py
          llm_page.py
          role_page.py
          voice_pages.py
          resource_page.py
      widgets/            # 可复用 UI 组件和弹窗
        pet_input_popup.py
        pet_voice_popup.py
        setting_cards.py
        ui_utils.py
        menus/
          pet_menus.py
        easter/
          base.py
          magic_conch.py
          gacha.py
          dice.py
          coin.py
          fortune_stick.py
          wooden_fish.py
          daily_tip.py
          notice.py
        notifications/
          center.py
          toast.py
          bubble.py
          smart_bubble.py
          constants.py
      pet/                # 桌宠主窗口、动画与资源
        desktop_pet.py
        desktop_actions.py
        desktop_tray.py
        desktop_easter.py
        desktop_hover.py
        desktop_interactions.py
        desktop_windows.py
        animation.py
        pet_assets.py
      protocols/          # 协议常量和编解码
        protocol_v1.py
        doubao_call_protocol.py
  res/                    # 图标、角色、宠物、道具资源
  data/                   # 本地运行配置、总结重点、音频预览缓存
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

- 新功能代码必须按职责进入功能目录，不能继续把所有 `.py` 堆在 `src/miniPet/` 根目录。
- 入口层保持薄：`app.py`、`desktop_pet.py`、`settings_window.py` 负责组装，具体窗口、控件、客户端、存储逻辑下沉到子目录。
- UI 与服务解耦：窗口/控件通过 Signal、回调或 Worker 使用 `clients/`，不要把协议细节写进 UI。
- 存储与网络解耦：`storage/` 不调用网络，`clients/` 不直接操作 UI。
- 新功能代码进入 `src/miniPet/` 下合适目录，资源进入 `res/`，文档进入 `docs/`。
- 不再依赖外层 `MINIPET/` 的 Python 模块。
- 复用原 MINIPET 的资源格式，但资源最终要迁移到 `res/`。
- 设置页、菜单、聊天窗口和语音窗口要保持完整视觉体验，不使用裸表单堆控件。
- 外部事件源是可选插件，不是 miniPet 的运行依赖。

## License

MIT
