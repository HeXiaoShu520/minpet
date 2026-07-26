# MiniPet 桌面 AI 交互协议

MiniPet 通用协议是外置 AI 后端与桌面宠物之间的轻量交互协议。

MiniPet 不执行业务 API，不替代后端；它只负责：

- 接收用户在桌宠上的文字输入、拖拽投喂和卡片操作；
- 在桌面上展示后端返回的回复卡片；
- 把用户点击、选择、输入结果整理成文本回传给后端。

一句话：

> MiniPet 发送 `user.input`，后端发送 `surface.*`，用户输入统一交给后端大模型理解。

## 1. 设计目标

- 协议小：只保留 `session`、`user`、`surface` 三类顶层概念。
- 输入简单：外置后端只接收 `user.input`，其中 `text` 是用户意图，`attachments` 可携带图片等附件；不承载语音协议。
- 输出统一：普通文字、按钮、富文本、选择、输入、流式状态都用回复卡片表达。
- 交互闭环：用户点击按钮或提交控件值后，MiniPet 整理成文本继续发送 `user.input`。
- 可扩展：后续增加更多控件时，扩展 `controls`，不增加新的 surface 类型。

MiniPet 的边界：

- 不直接发送飞书消息、审批、创建日程或任务。
- 不自动采集屏幕、窗口标题、选中文本等敏感上下文。
- 外置后端只应把业务意图放进卡片，真正执行业务由后端完成。

## 2. 传输模型

MiniPet 作为 WebSocket client 主动连接本地或自定义后端：

| 模式 | 默认地址 | 说明 |
| --- | --- | --- |
| MiniPet 协议后端 | `ws://127.0.0.1:18889/ws/minipet` | MiniPet 连接遵循本协议的后端 |

也支持环境变量覆盖：

```text
MINIPET_EVENT_WS=ws://127.0.0.1:18889/ws/minipet
MINIPET_ACTION_URL=http://127.0.0.1:18889/actions/execute
```

WebSocket 不可用时，MiniPet 发送事件会 fallback 到 HTTP POST，POST body 是同样的事件 JSON。

### 快速接入

后端只需要实现一个 WebSocket 服务。启动后，在 MiniPet 的“设置 → 智能体设置”中选择“连接 MiniPet 协议后端”，地址填写：

```text
ws://127.0.0.1:18889/ws/minipet
```

MiniPet 连接后会先发送：

```json
{
  "version": "1.0",
  "type": "session.hello",
  "payload": {
    "protocol": "minipet.v1"
  }
}
```

后端可回复就绪：

```json
{
  "version": "1.0",
  "type": "session.ready",
  "payload": {
    "server": {
      "name": "my-agent"
    }
  }
}
```

用户输入会发送为：

```json
{
  "version": "1.0",
  "type": "user.input",
  "payload": {
    "text": "你好"
  }
}
```

后端返回普通文本卡片：

```json
{
  "version": "1.0",
  "type": "surface.show",
  "payload": {
    "surface_id": "reply-1",
    "content": "你好，我是后端返回的回复。",
    "status": "done",
    "timeout_ms": 8000
  }
}
```

最小 Python 后端：

```python
import asyncio
import json
import websockets


async def handler(ws):
    async for raw in ws:
        event = json.loads(raw)
        if event.get("type") == "session.probe":
            await ws.send(json.dumps({
                "version": "1.0",
                "type": "session.probe.result",
                "request_id": event.get("request_id"),
                "payload": {
                    "ok": True,
                    "protocol": "minipet.v1",
                    "server": {"name": "demo-agent"},
                },
            }, ensure_ascii=False))
            continue

        if event.get("type") == "session.hello":
            await ws.send(json.dumps({
                "version": "1.0",
                "type": "session.ready",
                "payload": {"server": {"name": "demo-agent"}},
            }, ensure_ascii=False))
            continue

        if event.get("type") == "user.input":
            text = event.get("payload", {}).get("text", "")
            await ws.send(json.dumps({
                "version": "1.0",
                "type": "surface.show",
                "payload": {
                    "surface_id": "reply-1",
                    "content": "收到：" + text,
                    "status": "done",
                    "timeout_ms": 8000,
                },
            }, ensure_ascii=False))


async def main():
    async with websockets.serve(handler, "127.0.0.1", 18889):
        await asyncio.Future()


asyncio.run(main())
```

## 3. 消息信封

所有消息都是 JSON 对象。

```json
{
  "version": "1.0",
  "type": "surface.show",
  "payload": {},
  "request_id": "optional-request-id"
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `version` | 推荐 | 协议版本，当前为 `1.0` |
| `type` | 是 | 消息类型 |
| `payload` | 是 | 具体内容 |
| `request_id` | 否 | 请求 ID，用于关联请求和响应 |

## 4. 核心消息类型

| 类型 | 方向 | 用途 |
| --- | --- | --- |
| `session.probe` | MiniPet → 后端 | 设置页检测协议可用性，不进入正式会话 |
| `session.probe.result` | 后端 → MiniPet | 返回检测结果 |
| `session.hello` | MiniPet → 后端 | MiniPet 连接后声明协议和能力 |
| `session.ready` | 后端 → MiniPet | 后端就绪 |
| `session.ping` | 后端 → MiniPet | 心跳请求 |
| `session.pong` | MiniPet → 后端 | 心跳响应 |
| `user.input` | MiniPet → 后端 | 用户输入；文字命令、拖拽投喂、卡片操作都整理成 `text`，图片放入 `attachments` |
| `surface.show` | 后端 → MiniPet | 创建回复卡片 |
| `surface.update` | 后端 → MiniPet | 更新已有卡片 |
| `surface.close` | 后端 → MiniPet | 关闭已有卡片 |

## 5. Session

### session.probe

设置页点击“检测 MiniPet 协议”时发送。后端收到后应立即回复 `session.probe.result`，不要把它当作正式会话连接。

```json
{
  "version": "1.0",
  "type": "session.probe",
  "request_id": "probe_xxx",
  "payload": {
    "protocol": "minipet.v1",
    "capabilities": [
      "session.probe",
      "session.probe.result",
      "session.hello",
      "session.ready",
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

后端回复：

```json
{
  "version": "1.0",
  "type": "session.probe.result",
  "request_id": "probe_xxx",
  "payload": {
    "ok": true,
    "protocol": "minipet.v1",
    "server": {
      "name": "miniClaw"
    }
  }
}
```

### session.hello

MiniPet 连接后发送：

```json
{
  "version": "1.0",
  "type": "session.hello",
  "payload": {
    "protocol": "minipet.v1",
    "capabilities": [
      "session.probe",
      "session.probe.result",
      "session.hello",
      "session.ready",
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

### session.ready

后端就绪：

```json
{
  "version": "1.0",
  "type": "session.ready",
  "payload": {
    "server": {
      "name": "miniClaw"
    },
    "protocol": "minipet.v1"
  }
}
```

### session.ping / session.pong

```json
{
  "version": "1.0",
  "type": "session.ping",
  "payload": {
    "ts": 1730000000000
  }
}
```

MiniPet 回：

```json
{
  "version": "1.0",
  "type": "session.pong",
  "payload": {
    "ts": 1730000000000
  }
}
```

## 6. User

### user.input

MiniPet 发给后端的唯一用户输入事件。文字命令、拖拽投喂、卡片按钮和控件提交都整理成 `text`，图片等二进制内容放在 `attachments` 中，让后端大模型自行理解意图。

```json
{
  "version": "1.0",
  "type": "user.input",
  "payload": {
    "text": "帮我总结今天需要处理的事"
  }
}
```

带图片输入时，`attachments` 使用 base64。后端直接解码 `data` 字段即可：

```json
{
  "version": "1.0",
  "type": "user.input",
  "payload": {
    "text": "帮我看看这张图",
    "preview": "帮我看看这张图\n[图片] × 1",
    "mode": "text",
    "surface": "pet_popup",
    "attachments": [
      {
        "type": "image",
        "name": "image_1.png",
        "mime_type": "image/png",
        "encoding": "base64",
        "data": "iVBORw0KGgo...",
        "source": "message"
      }
    ]
  }
}
```

Python 解码示例：

```python
import base64

payload = event.get("payload", {})
for attachment in payload.get("attachments", []):
    if attachment.get("type") == "image" and attachment.get("encoding") == "base64":
        image_bytes = base64.b64decode(attachment["data"])
        mime_type = attachment.get("mime_type", "image/png")
```

拖拽投喂也按 `text` 描述意图；如果投喂的是图片，会同时携带 `attachments`：

```json
{
  "version": "1.0",
  "type": "user.input",
  "payload": {
    "text": "用户投喂了内容，希望你处理：总结。\n预览：一张图片，可以识别文字、总结或发到飞书。",
    "mode": "drop",
    "surface": "desktop_pet",
    "intent": "summarize",
    "attachments": [
      {
        "type": "image",
        "name": "拖入的图片",
        "mime_type": "image/png",
        "encoding": "base64",
        "data": "iVBORw0KGgo...",
        "source": "drop"
      }
    ]
  }
}
```

用户点击卡片按钮或提交控件后，也按文本发送：

```json
{
  "version": "1.0",
  "type": "user.input",
  "payload": {
    "text": "提交\n{\"plan\": \"simple\", \"note\": \"先做最小版本\"}"
  }
}
```

MiniPet 内置 action：

| action id | 本地行为 |
| --- | --- |
| `ignore` | 关闭/忽略，不发送给后端 |
| `copy` | 复制卡片文本 |
| `open_chat` | 打开聊天窗口 |
| `later` | 本地稍后提醒占位提示 |

其他 action 会整理成 `user.input.text` 发送给后端。

## 7. Surface：回复卡片

后端所有展示和交互都通过回复卡片表达。

```json
{
  "surface_id": "surface-001",
  "content": "正文文本",
  "status": "streaming",
  "elements": [],
  "controls": [],
  "actions": [],
  "timeout_ms": 12000,
  "metadata": {}
}
```

卡片由三块组成：

```text
Card
├─ elements：展示内容，用户不能编辑
├─ controls：输入/选择控件，用户可以填写或选择
└─ actions：按钮，点击后触发本地动作或整理成 user.input
```

渲染规则：

- Header 固定存在，由 MiniPet 显示宠物头像、宠物名、状态和关闭按钮。
- `elements` / `content` 存在才显示正文区域。
- `controls` 存在才显示输入/选择区域。
- `actions` 存在才显示按钮区域。
- 不存在的部分不预留空间。

### 7.1 Header 和状态

状态字段：

| status | 表现 |
| --- | --- |
| 空 | 不显示额外状态 |
| `running` / `streaming` / `thinking` / `working` | 进行中动画标记 |
| `done` / `completed` / `success` | 完成标记 |
| `failed` / `error` | 失败标记 |

### 7.2 elements

`elements` 用于展示内容。当前推荐类型：

| type/tag | 说明 |
| --- | --- |
| `text` / `plain_text` | 普通文本 |
| `markdown` | Markdown 文本，客户端可轻量降级展示 |
| `code` | 代码文本 |
| `divider` / `hr` | 分隔线 |

如果没有 `elements`，MiniPet 会使用 `content` / `summary` / `message` 生成默认文本内容。

```json
{
  "elements": [
    {"type": "markdown", "content": "**总结：** 这个任务需要改 3 个文件。"},
    {"type": "divider"},
    {"type": "text", "content": "是否继续？"}
  ]
}
```

### 7.3 controls

`controls` 用于收集用户输入和选择。当前推荐类型：

| type | 说明 | 回传值 |
| --- | --- | --- |
| `text` / `input` | 文本输入框 | 字符串 |
| `radio_group` / `select` | 单选 | 选中 option id |
| `checkbox_group` / `multi_select` | 多选 | option id 数组 |

文本输入：

```json
{
  "id": "note",
  "type": "text",
  "label": "补充说明",
  "placeholder": "可选",
  "default_value": ""
}
```

单选并允许自定义输入：

```json
{
  "id": "plan",
  "type": "radio_group",
  "label": "方案",
  "options": [
    {"id": "simple", "label": "简单方案", "description": "改动少"},
    {"id": "full", "label": "完整方案", "description": "功能完整"}
  ],
  "allow_custom": true,
  "custom_id": "custom",
  "custom_label": "其他",
  "custom_placeholder": "请输入其他方案"
}
```

用户选择“其他”并填写后，回传：

```json
{
  "values": {
    "plan": "custom",
    "plan_text": "只更新文档，不改代码"
  }
}
```

多选：

```json
{
  "id": "features",
  "type": "checkbox_group",
  "label": "启用能力",
  "options": [
    {"id": "card", "label": "卡片显示"},
    {"id": "stream", "label": "流式状态"},
    {"id": "markdown", "label": "Markdown"}
  ],
  "allow_custom": true
}
```

### 7.4 actions

`actions` 是卡片底部按钮。推荐字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 后端识别动作的稳定 ID |
| `label` | 是 | 按钮文字 |
| `style` | 否 | `primary` / `default` / `quiet` / `danger` |
| `intent` | 否 | 语义标签 |
| `metadata` | 否 | action 级附加信息 |

示例：

```json
{
  "actions": [
    {"id": "cancel", "label": "取消", "style": "quiet"},
    {"id": "submit", "label": "提交", "style": "primary"}
  ]
}
```

建议按钮不超过 4 个。

## 8. surface.show / surface.update / surface.close

字段规则：

- 所有 `surface.*` 都按回复卡片处理，不再需要 `kind` 字段。
- 卡片头部由 MiniPet 统一显示宠物头像和宠物名；协议不再使用 `title` / `subtitle` 作为卡片标题或副标题。
- 需要展示的信息都放进 `content` 或 `elements`。
- 流式状态统一使用 `status` 表达，推荐值为 `streaming` / `done` / `failed`。不建议再使用 `done: true/false`，旧客户端如已支持可继续兼容，但新适配器不要依赖它。

### 创建流式卡片

```json
{
  "version": "1.0",
  "type": "surface.show",
  "payload": {
    "surface_id": "reply-1",
    "content": "正在生成回复...",
    "status": "streaming",
    "timeout_ms": 0
  }
}
```

### 更新同一张卡片

```json
{
  "version": "1.0",
  "type": "surface.update",
  "payload": {
    "surface_id": "reply-1",
    "content": "这是当前已生成的内容。",
    "status": "streaming",
    "timeout_ms": 0
  }
}
```

### 完成

```json
{
  "version": "1.0",
  "type": "surface.update",
  "payload": {
    "surface_id": "reply-1",
    "content": "这是最终回复。",
    "status": "done",
    "timeout_ms": 8000
  }
}
```

### 关闭

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

## 9. 完整交互示例

### 用户发命令

```json
{
  "type": "user.input",
  "payload": {
    "text": "帮我总结今天需要处理的事"
  }
}
```

### 后端创建流式卡片

```json
{
  "type": "surface.show",
  "payload": {
    "surface_id": "briefing-001",
    "content": "正在整理...",
    "status": "streaming",
    "timeout_ms": 0
  }
}
```

### 后端展示结果和按钮

```json
{
  "type": "surface.update",
  "payload": {
    "surface_id": "briefing-001",
    "elements": [
      {"type": "markdown", "content": "**今天需要处理的 4 件事**\n\n1. 产品群有 1 条消息需要回复\n2. 接口文档需要补充\n3. 昨天会议有 2 个待办"}
    ],
    "status": "done",
    "timeout_ms": 10000,
    "actions": [
      {"id": "copy", "label": "复制", "style": "default"},
      {"id": "create_tasks", "label": "生成任务", "style": "primary"}
    ]
  }
}
```

### 用户点击按钮

```json
{
  "type": "user.input",
  "payload": {
    "text": "生成任务"
  }
}
```

## 10. 安全边界

- 默认只连接本机地址。
- 自定义后端应被视为受信任后端。
- MiniPet 不直接执行业务 API。
- 普通文件拖拽只传路径和元信息；图片拖拽会作为 base64 附件发送给后端。
- 高风险业务动作必须通过卡片清楚展示，并由用户点击确认按钮。
- 屏幕截图、选中文本、窗口标题等敏感上下文不属于外置后端默认协议；只有用户主动发起的图片或开启语音看屏时的截图会进入 `attachments`。

## 11. Python 调用示例

```python
import asyncio
import json
import websockets

async def main():
    async with websockets.connect('ws://127.0.0.1:18889/ws/minipet') as ws:
        hello = await ws.recv()
        print('recv:', hello)

        await ws.send(json.dumps({
            'version': '1.0',
            'type': 'surface.show',
            'payload': {
                'surface_id': 'demo-card-001',
                'elements': [
                    {'type': 'markdown', 'content': '**MiniPet 回复卡片示例**\n\n这是回复卡片。'}
                ],
                'controls': [
                    {
                        'id': 'plan',
                        'type': 'radio_group',
                        'label': '选择方案',
                        'options': [
                            {'id': 'simple', 'label': '简单方案'},
                            {'id': 'full', 'label': '完整方案'},
                        ],
                        'allow_custom': True,
                    }
                ],
                'actions': [
                    {'id': 'cancel', 'label': '取消', 'style': 'quiet'},
                    {'id': 'submit', 'label': '提交', 'style': 'primary'},
                ]
            }
        }, ensure_ascii=False))

        while True:
            print(await ws.recv())

asyncio.run(main())
```
