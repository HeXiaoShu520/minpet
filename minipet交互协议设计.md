# miniPet 桌面 AI 交互协议 V1

miniPet V1 是外置 AI 后端与桌面宠物之间的轻量交互协议。

miniPet 不执行业务 API，不替代后端；它只负责：

- 接收用户在桌宠上的文字输入、拖拽投喂和卡片操作；
- 在桌面上展示后端返回的通用卡片；
- 把用户点击、选择、输入结果整理成文本回传给后端。

一句话：

> miniPet 发送 `user.input`，后端发送 `surface.*`，用户输入统一交给后端大模型理解。

## 1. 设计目标

- 协议小：只保留 `session`、`user`、`surface` 三类顶层概念。
- 输入简单：外置后端只接收 `user.input` 文本输入，不承载语音协议。
- 输出统一：普通文字、按钮、富文本、选择、输入、流式状态都用通用卡片表达。
- 交互闭环：用户点击按钮或提交控件值后，miniPet 整理成文本继续发送 `user.input`。
- 可扩展：后续增加更多控件时，扩展 `controls`，不增加新的 surface 类型。

miniPet 的边界：

- 不直接发送飞书消息、审批、创建日程或任务。
- 不自动采集屏幕、窗口标题、选中文本等敏感上下文。
- 外置后端只应把业务意图放进卡片，真正执行业务由后端完成。

## 2. 传输模型

miniPet 作为 WebSocket client 主动连接本地或自定义后端：

| 模式 | 默认地址 | 说明 |
| --- | --- | --- |
| OpenClaw adapter | `ws://127.0.0.1:18888/ws/pet` | miniPet 连接本地 adapter |
| miniClaw / 通用后端 | `ws://127.0.0.1:18889/ws/minipet` | miniPet 连接遵循 V1 的后端 |

也支持环境变量覆盖：

```text
MINIPET_EVENT_WS=ws://127.0.0.1:18889/ws/minipet
MINIPET_ACTION_URL=http://localhost:18888/actions/execute
```

WebSocket 不可用时，miniPet 发送事件会 fallback 到 HTTP POST，POST body 是同样的事件 JSON。

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
| `session.hello` | miniPet → 后端 | miniPet 连接后声明协议和能力 |
| `session.ready` | 后端 → miniPet | 后端就绪 |
| `session.ping` | 后端 → miniPet | 心跳请求 |
| `session.pong` | miniPet → 后端 | 心跳响应 |
| `user.input` | miniPet → 后端 | 用户输入文本；文字命令、拖拽投喂、卡片操作都整理成文本发送 |
| `surface.show` | 后端 → miniPet | 创建通用卡片 |
| `surface.update` | 后端 → miniPet | 更新已有卡片 |
| `surface.close` | 后端 → miniPet | 关闭已有卡片 |

## 5. Session

### session.hello

miniPet 连接后发送：

```json
{
  "version": "1.0",
  "type": "session.hello",
  "payload": {
    "protocol": "minipet.v1",
    "capabilities": [
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

miniPet 回：

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

miniPet 发给后端的唯一用户输入事件。文字命令、拖拽投喂、卡片按钮和控件提交都整理成文本，让后端大模型自行理解意图。

```json
{
  "version": "1.0",
  "type": "user.input",
  "payload": {
    "text": "帮我总结今天需要处理的事"
  }
}
```

拖拽投喂也按文本发送：

```json
{
  "version": "1.0",
  "type": "user.input",
  "payload": {
    "text": "用户投喂了内容，希望你处理：生成待办。\n预览：这段内容帮我整理成任务"
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

miniPet 内置 action：

| action id | 本地行为 |
| --- | --- |
| `ignore` | 关闭/忽略，不发送给后端 |
| `copy` | 复制卡片文本 |
| `open_chat` | 打开聊天窗口 |
| `later` | 本地稍后提醒占位提示 |

其他 action 会整理成 `user.input.text` 发送给后端。

## 7. Surface：通用卡片

后端所有展示和交互都通过通用卡片表达。

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

- Header 固定存在，由 miniPet 显示宠物头像、宠物名、状态和关闭按钮。
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

如果没有 `elements`，miniPet 会使用 `content` / `summary` / `message` 生成默认文本内容。

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

- 所有 `surface.*` 都按通用卡片处理，不再需要 `kind` 字段。
- 卡片头部由 miniPet 统一显示宠物头像和宠物名；协议不再使用 `title` / `subtitle` 作为卡片标题或副标题。
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
- miniPet 不直接执行业务 API。
- 文件拖拽只传路径和元信息。
- 高风险业务动作必须通过卡片清楚展示，并由用户点击确认按钮。
- 屏幕截图、选中文本、窗口标题等敏感上下文不属于外置后端默认协议。

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
                    {'type': 'markdown', 'content': '**V1 通用卡片示例**\n\n这是通用卡片。'}
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
