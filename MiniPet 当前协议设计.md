# MiniPet 当前协议设计

本文是 MiniPet 当前实现的权威接入说明，面向 miniClaw、自定义智能体网关和其他外置后端。内容以以下代码为准：

- `src/protocols/protocol_v1.py`
- `src/protocols/surface_utils.py`
- `src/clients/event_client.py`
- `src/app.py`
- `src/widgets/notifications/reply_card.py`

本文明确区分“当前规范”和“客户端兼容行为”。新后端应只依赖规范部分；兼容行为用于承接旧脚本或历史字段，不代表稳定承诺。

## 1. 定位与边界

MiniPet 是外置智能体的桌面输入与展示端，不是业务执行后端。当前协议的最小闭环是：

```text
MiniPet 发送 user.input
后端发送 surface.show / surface.update / surface.close
卡片交互再次整理为 user.input
```

MiniPet 当前负责：

- 建立 WebSocket 会话并声明能力；
- 发送文字、语音识别结果、拖拽意图和图片附件；
- 展示文本、轻量 Markdown、输入控件、选择控件和操作按钮；
- 用 `surface_id` 更新或关闭同一张卡片；
- 将非本地按钮操作及控件值转成文本交还后端；
- 对外置回复做可选 TTS 播报，并与聊天记录关联。

MiniPet 当前不负责：

- 直接调用飞书、邮件、审批、日历等业务 API；
- 允许后端通过 V1 协议控制宠物动作；
- 自动采集窗口标题、选中文本或屏幕内容；
- 提供通用文件上传协议。当前附件只实际构造图片；普通文件主要保留在拖拽描述中。

## 2. 传输与连接

MiniPet 是 WebSocket 客户端，默认连接：

```text
ws://127.0.0.1:18889/ws/minipet
```

可通过设置页修改，也可由环境变量覆盖：

```text
MINIPET_EVENT_WS=ws://127.0.0.1:18889/ws/minipet
MINIPET_ACTION_URL=http://127.0.0.1:18889/actions/execute
```

历史环境变量 `DYBERPET_EVENT_WS`、`DYBERPET_ACTION_URL` 仍可被读取，但新部署应使用 `MINIPET_*`。

正式连接使用 WebSocket 自带的 ping（20 秒间隔、20 秒超时），断线后约 3 秒重连。连接建立后 MiniPet 立即发送 `session.hello`。

发送 `user.input` 等事件时，MiniPet 优先使用当前 WebSocket；如果连接尚未可用，则向 `MINIPET_ACTION_URL` 发送相同 JSON 信封的 HTTP `POST`，超时 5 秒。HTTP 返回正文不参与协议处理，失败会返回发送失败状态。

设置页的“测试连接”会建立一条独立、短暂的 WebSocket，发送 `session.probe`，收到一次响应后结束。它不等同于正式会话。

## 3. 消息信封

当前规范中的消息均为 JSON 对象：

```json
{
  "version": "1.0",
  "type": "surface.show",
  "payload": {},
  "request_id": "optional-id"
}
```

| 字段 | 规范要求 | 说明 |
| --- | --- | --- |
| `version` | 应发送 | 当前值为字符串 `1.0` |
| `type` | 必须 | 事件类型 |
| `payload` | 必须为对象 | 事件数据 |
| `request_id` | 按需 | 当前用于 probe 请求与响应关联，也可随普通发送事件携带 |

兼容行为：

- 入站对象缺少 `version` 时补为 `1.0`；缺少 `payload` 时补为空对象。
- 入站 JSON 若不是对象，会被转换成 `surface.show`，正文为其字符串形式。
- `EventClient` 对缺少 `type` 的对象补 `message`，并补 `priority: normal`。这类事件最终走未知事件 Toast，不属于 V1 规范。
- `payload` 若不是对象，`app.py` 会在部分分发路径退回使用整个事件对象；新后端不可依赖这一行为。

## 4. 协议标识与能力

协议标识为：

```text
minipet.v1
```

客户端当前声明的能力列表严格为：

```json
[
  "session.hello",
  "session.ready",
  "session.probe",
  "session.probe.result",
  "session.ping",
  "session.pong",
  "user.input",
  "surface.show",
  "surface.update",
  "surface.close"
]
```

代码中还定义了 `agent.state` 常量，但它不在 `V1_CAPABILITIES` 中，`app.py` 也没有专门处理逻辑；因此 **`agent.state` 不是当前可依赖的已实现能力**。收到后只会按未知事件显示 Toast。

## 5. Session 事件

### 5.1 `session.probe`

方向：MiniPet → 后端。

```json
{
  "version": "1.0",
  "type": "session.probe",
  "request_id": "probe_随机十六进制串",
  "payload": {
    "protocol": "minipet.v1",
    "capabilities": [
      "session.hello",
      "session.ready",
      "session.probe",
      "session.probe.result",
      "session.ping",
      "session.pong",
      "user.input",
      "surface.show",
      "surface.update",
      "surface.close"
    ]
  }
}
```

后端必须把检测结果作为该连接上的第一条响应返回。

### 5.2 `session.probe.result`

方向：后端 → MiniPet。

```json
{
  "version": "1.0",
  "type": "session.probe.result",
  "request_id": "probe_与请求一致",
  "payload": {
    "ok": true,
    "protocol": "minipet.v1",
    "server": {"name": "demo-agent"}
  }
}
```

实际检测规则：

1. 响应类型必须是 `session.probe.result`；
2. 响应包含 `request_id` 时必须与请求一致；响应省略它仍会通过，因此“原样返回”是规范要求但客户端兼容缺省；
3. `payload.protocol` 存在时必须等于 `minipet.v1`；省略时客户端兼容接受；
4. 当前客户端不检查 `payload.ok`，但规范要求后端正确填写；
5. 服务名读取顺序为 `payload.server.name`、`payload.name`、默认名称。

### 5.3 `session.hello`

方向：MiniPet → 后端。正式 WebSocket 建立后立即发送，payload 与 probe 的能力声明相同：

```json
{
  "version": "1.0",
  "type": "session.hello",
  "payload": {
    "protocol": "minipet.v1",
    "capabilities": ["session.hello", "session.ready", "session.probe", "session.probe.result", "session.ping", "session.pong", "user.input", "surface.show", "surface.update", "surface.close"]
  }
}
```

### 5.4 `session.ready`

方向：后端 → MiniPet。

```json
{
  "version": "1.0",
  "type": "session.ready",
  "payload": {
    "protocol": "minipet.v1",
    "server": {"name": "demo-agent"}
  }
}
```

客户端当前仅显示“后端已就绪”卡片，不验证这里的 `protocol`。服务名兼容读取 `payload.name`。

### 5.5 `session.ping` / `session.pong`

方向：后端 → MiniPet → 后端。

```json
{
  "version": "1.0",
  "type": "session.ping",
  "payload": {"ts": 1730000000000}
}
```

MiniPet 原样回传 `payload.ts`：

```json
{
  "version": "1.0",
  "type": "session.pong",
  "payload": {"ts": 1730000000000}
}
```

这与 WebSocket 库自身的 ping/pong 并存。

## 6. `user.input`

方向：MiniPet → 后端。它是当前协议中唯一规范化的用户输入事件。

### 6.1 常规输入

```json
{
  "version": "1.0",
  "type": "user.input",
  "payload": {
    "text": "帮我总结今天的事项",
    "preview": "帮我总结今天的事项",
    "mode": "text",
    "surface": "pet_popup",
    "turn_id": "可选轮次 ID",
    "surface_id": "可选期望回复卡片 ID"
  }
}
```

当前可能出现的字段：

| 字段 | 含义 |
| --- | --- |
| `text` | 给后端理解的主文本 |
| `preview` | 用于展示的文本预览，图片会显示为 `[图片] × N` |
| `mode` | 当前常见值：`text`、`voice`、`drop` |
| `surface` | 输入来源，如 `pet_popup`、`voice_orb`、`chat_window`、`desktop_pet` |
| `turn_id` | custom 后端请求关联 ID；MiniPet 普通输入会生成 UUID |
| `surface_id` | custom 后端期望关联的回复 surface；普通输入默认为 `turn-<turn_id>` |
| `attachments` | 图片附件数组 |
| `intent`、`drop` | 拖拽投喂时的结构化补充 |

后端回复 custom 请求时应回传相同的 `turn_id` 或 `surface_id`，以便 MiniPet 将结果写入正确聊天窗口和历史。兼容旧后端时，如果事件完全没有关联字段且全局只有一个待处理请求，客户端才会降级匹配。

### 6.2 图片附件

```json
{
  "type": "image",
  "name": "image_1.png",
  "mime_type": "image/png",
  "encoding": "base64",
  "data": "iVBORw0KGgo...",
  "source": "message"
}
```

`source` 当前可能为 `message`、`screenshot`、`drop`。图片可能来自用户消息、用户主动开启语音看屏后截取的屏幕，或拖拽图片。当前代码只为可识别为图片的文件构造附件；不要假设任意文件都会作为 base64 上传。

### 6.3 拖拽投喂

拖拽会生成面向模型的文本，并附加：

```json
{
  "version": "1.0",
  "type": "user.input",
  "payload": {
    "text": "用户投喂了内容，希望你处理：总结。\n预览：……",
    "preview": "……",
    "mode": "drop",
    "surface": "desktop_pet",
    "intent": "summarize",
    "drop": {
      "items": [],
      "preview": "……",
      "intent": "summarize",
      "surface": "desktop_pet",
      "context": {"surface": "desktop_pet"}
    },
    "attachments": []
  }
}
```

`drop.items` 中的内联 `data_url` 会被移除，图片二进制统一进入 `attachments`。

### 6.4 卡片交互回传

点击非本地 action 后，MiniPet 取 `label`、`text`、`id`、`type` 中第一个可用值作为首行。如果卡片有控件值，再附加一行 JSON：

```json
{
  "version": "1.0",
  "type": "user.input",
  "payload": {
    "text": "提交\n{\"plan\": \"simple\", \"note\": \"先做最小版本\"}"
  }
}
```

当前不会把原 action ID、原 surface ID 或 values 作为独立 payload 字段回传。后端必须从文本和自身会话上下文理解操作。

以下 action ID 由 MiniPet 本地处理，不发后端：

| ID | 本地行为 |
| --- | --- |
| `ignore` | 关闭卡片，不做其他操作 |
| `copy` | 复制 `action.text` 或卡片建议/摘要/正文 |
| `open_chat` | 打开聊天窗口 |
| `later` | 显示“稍后提醒尚待接入”的本地提示 |

## 7. Surface 生命周期

### 7.1 `surface.show`

方向：后端 → MiniPet。创建一张卡片：

```json
{
  "version": "1.0",
  "type": "surface.show",
  "payload": {
    "surface_id": "reply-1",
    "content": "正在生成……",
    "status": "streaming",
    "timeout_ms": 0
  }
}
```

`surface_id` 强烈建议必填。缺省时卡片仍能显示，但无法通过后续事件可靠更新或关闭。

### 7.2 `surface.update`

方向：后端 → MiniPet。`surface_id` 必须存在，否则事件被忽略：

```json
{
  "version": "1.0",
  "type": "surface.update",
  "payload": {
    "surface_id": "reply-1",
    "content": "这是不断增长的完整文本，而不是 delta。",
    "status": "streaming",
    "timeout_ms": 0
  }
}
```

若客户端仍持有该 `surface_id` 对应卡片，会原位更新；否则会新建卡片。文本更新按“新文本以旧文本开头”识别追加，否则整体替换。后端应发送截至当前的完整正文，而不是只发增量。

终态更新后，MiniPet 会从内部 `surface_id` 映射移除卡片，但不会立即强制关闭；卡片按 timeout 自动关闭。此后再次 update 同一 ID 会创建新卡片。

### 7.3 `surface.close`

方向：后端 → MiniPet。`surface_id` 必须存在：

```json
{
  "version": "1.0",
  "type": "surface.close",
  "payload": {
    "surface_id": "reply-1",
    "reason": "completed"
  }
}
```

客户端关闭已追踪卡片，并清理该 surface 的 TTS 流。`reason` 当前不参与逻辑。

## 8. Surface payload

### 8.1 主文本与标题

主文本提取优先级严格为：

```text
text → message → summary → content → elements 中的文本
```

但回复卡片自身的默认正文优先级是：

```text
summary → content → message
```

因此新后端应统一使用 `content`，或只使用 `elements`，避免同时发送互相矛盾的 `text`、`summary`、`content`。

卡片标题读取 `payload.title`，缺省使用当前宠物名。旧设计曾建议忽略 title，但当前渲染器确实支持它；它属于已实现字段。`avatar_kind: "user"` 会使用用户头像，否则使用宠物头像。

`normalize_display_event` 会复制 payload、写入当前 `type`，并在 `summary` 缺省时用 `content` 或 `description` 补齐。由于卡片更新是字典合并，update 未提供的旧字段会保留。

### 8.2 状态

推荐规范值：

| 状态 | 行为 |
| --- | --- |
| `streaming` | 进行中动画；默认 60 秒 |
| `done` | 终态；默认 6 秒 |
| `failed` | 终态并显示“发送失败”；默认 6 秒 |

客户端兼容：

- 进行中：`running`、`streaming`、`thinking`、`working`；
- 终态：`done`、`completed`、`complete`、`success`、`failed`、`failure`、`error`；
- 状态也可来自 `state`，下划线会转成连字符；
- 卡片渲染还兼容顶层 `done: true` 与 `error: true`，但 surface 生命周期终态判断不读取这两个布尔值。新后端必须使用 `status`。

以下占位文本会被视为静默文本，不显示纯文本卡片，也不播报：`我在处理.../…`、`正在处理.../…`、`处理中.../…`。若同一 payload 含 `elements`、`actions` 或 `controls`，卡片仍会显示。

### 8.3 超时

解析顺序：

1. `timeout_ms`，毫秒；
2. `lifetime.ttl_ms`，毫秒；
3. `timeout`，秒并乘 1000；
4. 终态默认 6000 毫秒，非终态默认 60000 毫秒。

`0` 表示不自动关闭。用户手动移动卡片后，卡片永久保留，倒计时停止。

### 8.4 宽度

可发送 `width`，但客户端只会吸附到 `248、288、328、368、408、456` 像素之一，并限制在该范围内。不发送时根据正文长度、结构和控件数量自动选择。宽度是展示提示，不应承载业务语义。

### 8.5 `elements`

最多渲染前 8 项。支持：

| `type`/`tag` | 行为 |
| --- | --- |
| `text`、`plain_text`、`markdown`、`code` | 读取 `content`，兼容读取 `text`，按当前轻量 Markdown 渲染 |
| `divider`、`hr` | 分隔线 |

其他类型静默忽略。若同时存在 `summary/content/message`，主文本会作为第一个文本 element，再追加协议中的 `elements`。

```json
{
  "elements": [
    {"type": "markdown", "content": "**结论**：建议先按 A 版推进。"},
    {"type": "divider"},
    {"type": "text", "content": "是否继续？"}
  ]
}
```

### 8.6 `controls`

最多处理前 5 项，每项必须有 `id` 或 `name`。

#### 文本输入

类型：`text`、`input`。

```json
{
  "id": "note",
  "type": "text",
  "label": "补充说明",
  "placeholder": "可选",
  "default_value": ""
}
```

初值兼容读取 `value`。

#### 单选

类型：`radio`、`radio_group`、`select`。最多 8 个 option，默认选中第一个有效项。

```json
{
  "id": "plan",
  "type": "radio_group",
  "label": "方案",
  "options": [
    {"id": "simple", "label": "简单方案", "description": "改动少"},
    {"id": "full", "label": "完整方案"}
  ],
  "allow_custom": true,
  "custom_id": "custom",
  "custom_label": "其他",
  "custom_placeholder": "请输入"
}
```

option 值优先级为 `id → value → label`。`description` 当前仅作为 tooltip。选择 custom 时额外产生 `<control_id>_text`。

#### 多选

类型：`checkbox`、`checkbox_group`、`multi_select`。最多 8 个 option，值为数组；自定义输入规则与单选相同。

不支持的 control 类型会被忽略。

### 8.7 `actions`

最多渲染前 4 个对象：

```json
{
  "actions": [
    {"id": "cancel", "label": "取消", "style": "quiet"},
    {"id": "submit", "label": "提交", "style": "primary"}
  ]
}
```

按钮文字读取 `label`，缺省读 `id`。样式映射：

- 主按钮：`style` 为 `primary/confirm`，或 `intent=confirm`，或 ID 为 `confirm/send/ok/submit`；
- 危险按钮：`style` 为 `danger/reject`，或 `intent=reject`；
- 弱按钮：`style` 为 `quiet/cancel`，或 `intent=cancel`，或 ID 为 `cancel/ignore`；
- 其余为默认按钮。

`metadata` 当前不会被 MiniPet 特殊处理，但 action 原对象会保留到点击阶段。

## 9. TTS、语音与聊天关联

外置后端 surface 的可播报文本使用第 8.1 节的 `surface_text` 优先级。静默占位不播报。MiniPet 把同一 `surface_id` 的文本视为不断增长的完整流；终态状态用于结束该 TTS 流。空正文终态只结束生命周期，不会回读旧正文重新播报。

语音输入等待外置回复时，只要 surface 出现正文，客户端会关闭本地语音等待浮层并让宠物回到 idle；V1 不允许后端指定宠物动作。

custom 后端输入通常带 `turn_id` 与 `surface_id`。回复 surface 应至少回传一个关联字段；终态正文会进入对应聊天历史。对于聊天窗口，流式正文也会更新窗口内容。

## 10. 未知事件与历史兼容

任何未被 `_on_event` 专门处理的类型，包括历史 `message`、`bubble`、`action`、当前未实现的 `agent.state`，都会降级为右下角 Toast：标题取 `payload.title` 或“外部事件”，正文取 `payload.summary` 或 `payload.content`。

这不等于旧事件协议仍被完整支持：

- 不会按旧 `priority` 或 `pet_action` 控制宠物；
- 不会按旧 message schema 渲染完整交互卡片；
- 不会使用旧 `interaction.action` 回传格式；
- 旧 `timeout` 只有进入 surface 卡片路径时才按秒兼容。

新后端必须使用 `session.*`、`user.input`、`surface.*`。

## 11. 最小后端示例

```python
import asyncio
import json
import uuid

import websockets


async def send(ws, event_type, payload, request_id=None):
    event = {"version": "1.0", "type": event_type, "payload": payload}
    if request_id:
        event["request_id"] = request_id
    await ws.send(json.dumps(event, ensure_ascii=False))


async def handler(ws):
    async for raw in ws:
        event = json.loads(raw)
        event_type = event.get("type")

        if event_type == "session.probe":
            await send(ws, "session.probe.result", {
                "ok": True,
                "protocol": "minipet.v1",
                "server": {"name": "demo-agent"},
            }, event.get("request_id"))
            continue

        if event_type == "session.hello":
            await send(ws, "session.ready", {
                "protocol": "minipet.v1",
                "server": {"name": "demo-agent"},
            })
            continue

        if event_type == "session.pong":
            continue

        if event_type != "user.input":
            continue

        payload = event.get("payload") or {}
        surface_id = payload.get("surface_id") or "reply-" + uuid.uuid4().hex
        correlation = {
            "surface_id": surface_id,
            "turn_id": payload.get("turn_id"),
        }
        await send(ws, "surface.show", {
            **correlation,
            "content": "正在处理……",
            "status": "streaming",
            "timeout_ms": 0,
        })
        await send(ws, "surface.update", {
            **correlation,
            "content": "收到：" + payload.get("text", ""),
            "status": "done",
            "timeout_ms": 8000,
        })


async def main():
    async with websockets.serve(handler, "127.0.0.1", 18889):
        await asyncio.Future()


asyncio.run(main())
```

## 12. 接入检查清单

- probe 返回正确类型、协议标识和原 `request_id`；
- 正式连接收到 hello 后返回 ready；
- 只把 `user.input` 当作用户输入；
- 每轮回复使用稳定且唯一的 `surface_id`；
- custom 聊天回传请求中的 `turn_id` 或 `surface_id`；
- 流式 update 发送完整累计文本；
- 使用 `status: streaming/done/failed`，不要只发 `done: true`；
- 长任务使用 `timeout_ms: 0`，终态提供合理 timeout；
- 不超过 8 个 elements、5 个 controls、每控件 8 个 options、4 个 actions；
- 高风险动作先展示清楚，再等待用户按钮确认；
- 不依赖旧事件、宠物动作控制或尚未声明的 `agent.state`。
