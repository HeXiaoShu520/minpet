# miniPet 桌面 AI 交互协议设计 V1

miniPet V1 是一个桌面 AI 交互 Runtime。

它不直接执行业务，不替代飞书、OpenClaw 或其他后端；它只负责在桌面上承载 AI 的状态、表达、展示和追问，并把用户的命令、点击、输入和投喂回传给后端。

一句话：

> 后端控制 `surface` 和 `agent.state`；miniPet 回传 `user.*`；双方通过 `session.*` 建立连接与能力边界。

## 1. 设计目标

V1 追求“抽象最小”，不是“功能最少”。

- 概念少：只保留 `session`、`user`、`surface`、`agent` 四类概念。
- 消息少：核心消息类型固定为 12 个。
- 表达强：通过 `surface.kind` 承载气泡、卡片、确认、输入、选择。
- 可生长：未来新增 timeline、feed、dashboard 等界面形态，不增加新的顶层协议族。

miniPet 的边界：

- 不直接发送飞书消息。
- 不直接审批。
- 不直接创建日程、任务、文档。
- 不做完整 IM 客户端。
- 不自动采集屏幕、窗口标题、选中文本等敏感上下文。
- 高风险动作只做本地确认，真正执行由后端完成。

## 2. 四个核心概念

| 概念 | 方向 | 含义 |
| --- | --- | --- |
| `session` | 双向 | 连接生命周期、握手、心跳、能力协商 |
| `user` | miniPet → 后端 | 用户命令、点击、输入、拖拽投喂 |
| `surface` | 后端 → miniPet | 桌面上的可见界面：气泡、卡片、确认、输入、选择 |
| `agent` | 后端 → miniPet | AI 当前状态、情绪、进度、任务结果 |

## 3. 传输模型

当前实现中，miniPet 作为 WebSocket client 主动连接本地或自定义后端：

| 模式 | 默认地址 | 说明 |
| --- | --- | --- |
| OpenClaw adapter | `ws://127.0.0.1:18888/ws/pet` | miniPet 连接本地 adapter |
| 自定义后端 | `ws://127.0.0.1:18889/ws/minipet` | miniPet 连接遵循 V1 的后端 |

配置字段保存在 `data/minipet_settings.json`：

```json
{
  "agent_backend": "builtin",
  "openclaw_ws_url": "ws://127.0.0.1:18888/ws/pet",
  "custom_agent_ws_url": "ws://127.0.0.1:18889/ws/minipet"
}
```

`builtin` 模式不走外部协议；`openclaw` 和 `custom` 模式使用本文协议。

## 4. 消息信封

所有消息都是 JSON 对象。

```json
{
  "version": "1.0",
  "id": "msg-001",
  "request_id": "optional-request-id",
  "type": "surface.show",
  "source": "agent",
  "timestamp": 1730000000000,
  "payload": {}
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `version` | 推荐 | 协议版本，当前为 `1.0` |
| `id` | 否 | 消息 ID |
| `request_id` | 否 | 请求 ID，用于匹配响应 |
| `type` | 是 | 消息类型 |
| `source` | 否 | 来源，例如 `minipet`、`agent`、`openclaw` |
| `timestamp` | 否 | 毫秒时间戳 |
| `payload` | 是 | 具体内容 |

响应消息可使用：

```json
{
  "version": "1.0",
  "type": "response",
  "reply_to": "msg-001",
  "request_id": "optional-request-id",
  "ok": true,
  "result": {},
  "error": null
}
```

失败：

```json
{
  "version": "1.0",
  "type": "response",
  "reply_to": "msg-001",
  "ok": false,
  "result": null,
  "error": {
    "code": "unknown_type",
    "message": "Unknown message type"
  }
}
```

## 5. V1 核心消息类型

| 类型 | 方向 | 用途 |
| --- | --- | --- |
| `session.hello` | miniPet → 后端 | miniPet 发起握手并声明能力 |
| `session.ready` | 后端 → miniPet | 后端就绪并声明能力 |
| `session.ping` | 后端 → miniPet | 心跳请求 |
| `session.pong` | miniPet → 后端 | 心跳响应 |
| `user.command` | miniPet → 后端 | 用户自然语言命令 |
| `user.action` | miniPet → 后端 | 用户点击按钮、确认、取消、打开等动作 |
| `user.input` | miniPet → 后端 | 用户提交输入或选择 |
| `user.drop` | miniPet → 后端 | 用户拖拽文本、文件、链接等给宠物 |
| `surface.show` | 后端 → miniPet | 展示一个桌面交互界面 |
| `surface.update` | 后端 → miniPet | 更新已有界面 |
| `surface.close` | 后端 → miniPet | 关闭已有界面 |
| `agent.state` | 后端 → miniPet | 更新 AI 状态、情绪、进度 |

第一版代码重点实现：`session.hello`、`session.ready`、`session.ping`、`session.pong`、`user.command`、`user.action`、`user.input`、`user.drop`、`surface.show`、`agent.state`。

`surface.update`、`surface.close` 是 V1 稳定接口，第一版可先作为保留能力。

## 6. Session

### session.hello

miniPet 连接后发送，用于声明 V1 能力。

```json
{
  "version": "1.0",
  "type": "session.hello",
  "source": "minipet",
  "payload": {
    "client": {
      "name": "miniPet",
      "version": "1.0.0"
    },
    "protocol": "minipet.v1",
    "concepts": ["session", "user", "surface", "agent"],
    "surface_kinds": ["bubble", "card", "confirm", "input", "choice"],
    "capabilities": [
      "user.command",
      "user.action",
      "user.input",
      "user.drop",
      "surface.show",
      "surface.update",
      "surface.close",
      "agent.state"
    ]
  }
}
```

### session.ready

后端就绪。

```json
{
  "version": "1.0",
  "type": "session.ready",
  "source": "agent",
  "payload": {
    "server": {
      "name": "My Agent Backend",
      "version": "1.0.0"
    },
    "accepted_surface_kinds": ["bubble", "card", "confirm", "input", "choice"]
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

```json
{
  "version": "1.0",
  "type": "session.pong",
  "source": "minipet",
  "payload": {
    "ts": 1730000000000
  }
}
```

## 7. User

### user.command

用户主动向桌宠输入自然语言命令。

```json
{
  "version": "1.0",
  "type": "user.command",
  "source": "minipet",
  "payload": {
    "text": "帮我总结今天需要处理的事",
    "mode": "text",
    "surface": "pet_popup",
    "context": {}
  }
}
```

### user.action

所有按钮点击、确认、取消、打开、稍后等动作都统一为 `user.action`。

```json
{
  "version": "1.0",
  "type": "user.action",
  "source": "minipet",
  "payload": {
    "surface_id": "briefing-001",
    "action_id": "detail",
    "intent": "open",
    "action": {
      "id": "detail",
      "label": "查看详情",
      "style": "primary"
    },
    "metadata": {}
  }
}
```

### user.input

用户对输入或选择界面提交结果。

```json
{
  "version": "1.0",
  "type": "user.input",
  "source": "minipet",
  "payload": {
    "surface_id": "edit-reply-001",
    "action_id": "submit",
    "kind": "text",
    "value": "可以，我四点半前发你。",
    "metadata": {}
  }
}
```

选择结果：

```json
{
  "version": "1.0",
  "type": "user.input",
  "source": "minipet",
  "payload": {
    "surface_id": "meeting-time-001",
    "action_id": "submit",
    "kind": "choice",
    "value": ["t2"]
  }
}
```

### user.drop

用户把文本、链接或文件拖给宠物。

```json
{
  "version": "1.0",
  "type": "user.drop",
  "source": "minipet",
  "payload": {
    "drop_id": "drop-001",
    "kind": "text",
    "content": "这段内容帮我整理成任务",
    "intent": "create_task",
    "surface": "desktop_pet"
  }
}
```

文件只传路径和元信息，是否读取由后端权限决定：

```json
{
  "type": "user.drop",
  "source": "minipet",
  "payload": {
    "kind": "file",
    "files": [
      {
        "path": "C:/Users/me/Desktop/report.pdf",
        "name": "report.pdf",
        "mime": "application/pdf",
        "size": 123456
      }
    ],
    "intent": "summarize"
  }
}
```

## 8. Surface

`surface` 是后端要求 miniPet 展示的桌面交互界面。

统一对象：

```json
{
  "surface_id": "surface-001",
  "kind": "card",
  "title": "标题",
  "subtitle": "副标题",
  "content": "正文",
  "elements": [],
  "input": null,
  "actions": [],
  "placement": {
    "anchor": "pet_right",
    "follow_pet": true
  },
  "lifetime": {
    "ttl_ms": 180000,
    "after_timeout": "keep"
  },
  "priority": "normal",
  "metadata": {}
}
```

第一版 `kind`：

| kind | 用途 |
| --- | --- |
| `bubble` | 短提示 |
| `card` | 正式内容展示 |
| `confirm` | 高风险确认 |
| `input` | 请求用户输入文本 |
| `choice` | 请求用户选择 |

### surface.show kind=bubble

```json
{
  "version": "1.0",
  "type": "surface.show",
  "source": "agent",
  "payload": {
    "surface_id": "hello-001",
    "kind": "bubble",
    "content": "我在这里。",
    "lifetime": {
      "ttl_ms": 5000
    }
  }
}
```

### surface.show kind=card

```json
{
  "version": "1.0",
  "type": "surface.show",
  "source": "agent",
  "payload": {
    "surface_id": "briefing-001",
    "kind": "card",
    "title": "今天需要处理的事",
    "content": "你有 3 项待处理。",
    "actions": [
      { "id": "detail", "label": "查看详情", "style": "primary", "intent": "open" },
      { "id": "later", "label": "稍后", "style": "quiet", "intent": "snooze" }
    ]
  }
}
```

### surface.show kind=confirm

```json
{
  "version": "1.0",
  "type": "surface.show",
  "source": "agent",
  "payload": {
    "surface_id": "send-reply-001",
    "kind": "confirm",
    "title": "确认发送？",
    "content": "可以，我四点前发初版。",
    "risk": "medium",
    "actions": [
      { "id": "confirm", "label": "发送", "style": "primary", "intent": "confirm" },
      { "id": "edit", "label": "修改", "intent": "edit" },
      { "id": "cancel", "label": "取消", "style": "quiet", "intent": "cancel" }
    ],
    "metadata": {
      "draft_id": "draft-001"
    }
  }
}
```

### surface.show kind=input

```json
{
  "version": "1.0",
  "type": "surface.show",
  "source": "agent",
  "payload": {
    "surface_id": "edit-reply-001",
    "kind": "input",
    "title": "修改回复内容",
    "input": {
      "type": "text",
      "placeholder": "请输入回复内容",
      "default_value": "可以，我四点前发初版。"
    },
    "actions": [
      { "id": "submit", "label": "继续", "style": "primary" },
      { "id": "cancel", "label": "取消", "style": "quiet" }
    ],
    "metadata": {
      "draft_id": "draft-001"
    }
  }
}
```

### surface.show kind=choice

```json
{
  "version": "1.0",
  "type": "surface.show",
  "source": "agent",
  "payload": {
    "surface_id": "meeting-time-001",
    "kind": "choice",
    "title": "选择会议时间",
    "content": "我找到 3 个大家都有空的时间。",
    "input": {
      "type": "choice",
      "multi": false,
      "options": [
        { "id": "t1", "label": "明天 14:00 - 14:30" },
        { "id": "t2", "label": "明天 15:30 - 16:00" },
        { "id": "t3", "label": "后天 10:00 - 10:30" }
      ]
    },
    "actions": [
      { "id": "submit", "label": "确定", "style": "primary" },
      { "id": "cancel", "label": "取消", "style": "quiet" }
    ]
  }
}
```

### surface.update / surface.close

V1 保留更新和关闭接口。

```json
{
  "version": "1.0",
  "type": "surface.update",
  "source": "agent",
  "payload": {
    "surface_id": "briefing-001",
    "title": "已更新",
    "content": "新的内容"
  }
}
```

```json
{
  "version": "1.0",
  "type": "surface.close",
  "source": "agent",
  "payload": {
    "surface_id": "briefing-001",
    "reason": "completed"
  }
}
```

## 9. Agent

### agent.state

统一表达 AI 当前状态、宠物情绪、提示文本和进度。

```json
{
  "version": "1.0",
  "type": "agent.state",
  "source": "agent",
  "payload": {
    "state": "working",
    "text": "我在整理今天需要你处理的事项。",
    "emotion": "thinking",
    "progress": 0.35,
    "task": {
      "id": "briefing-001",
      "title": "整理今日待处理"
    }
  }
}
```

`state` 推荐值：

```text
idle | listening | thinking | working | waiting_user | done | failed | muted
```

miniPet 自行决定如何表现：气泡、宠物动作、情绪、进度提示或声音。

## 10. 最小闭环

### 用户发命令

```json
{
  "type": "user.command",
  "source": "minipet",
  "payload": {
    "text": "帮我总结今天需要处理的事",
    "mode": "text"
  }
}
```

### 后端更新状态

```json
{
  "type": "agent.state",
  "source": "agent",
  "payload": {
    "state": "working",
    "text": "我在查看消息、任务和会议纪要。",
    "emotion": "thinking",
    "progress": 0.3
  }
}
```

### 后端展示结果

```json
{
  "type": "surface.show",
  "source": "agent",
  "payload": {
    "surface_id": "briefing-001",
    "kind": "card",
    "title": "今天需要处理的 4 件事",
    "content": "产品群 1 条消息需要回复；接口文档需要补充；昨天会议有 2 个待办。",
    "actions": [
      { "id": "detail", "label": "查看详情", "style": "primary", "intent": "open" },
      { "id": "create_tasks", "label": "生成任务", "intent": "custom" }
    ]
  }
}
```

### 用户点击按钮

```json
{
  "type": "user.action",
  "source": "minipet",
  "payload": {
    "surface_id": "briefing-001",
    "action_id": "detail",
    "intent": "open"
  }
}
```

## 11. 错误码

| code | 含义 |
| --- | --- |
| `invalid_json` | JSON 解析失败 |
| `invalid_request` | 请求结构不合法 |
| `unknown_type` | 未知消息类型 |
| `missing_field` | 缺少必填字段 |
| `unknown_action` | 动作不存在 |
| `surface_not_found` | 界面不存在 |
| `input_cancelled` | 用户取消输入 |
| `permission_denied` | 当前权限不允许 |
| `rate_limited` | 请求过于频繁 |
| `internal_error` | miniPet 内部错误 |

## 12. 安全边界

- 默认只连接本机地址。
- 自定义后端应被视为受信任后端。
- miniPet 不直接执行业务 API。
- 文件拖拽只传路径和元信息。
- 高风险业务动作必须通过 `surface.show kind=confirm` 明确展示。
- 屏幕截图、选中文本、窗口标题等敏感上下文必须由用户主动触发。

## 13. Python 调用示例

```python
import asyncio
import json
import websockets

async def main():
    async with websockets.connect('ws://127.0.0.1:18888/ws/pet') as ws:
        await ws.send(json.dumps({
            'version': '1.0',
            'type': 'surface.show',
            'source': 'demo-agent',
            'payload': {
                'surface_id': 'demo-card-001',
                'kind': 'card',
                'title': 'V1 卡片示例',
                'content': '这是通过 surface.show 展示的桌面卡片。',
                'actions': [
                    {'id': 'ok', 'label': '知道了', 'style': 'primary', 'intent': 'confirm'}
                ]
            }
        }, ensure_ascii=False))

        while True:
            print(await ws.recv())

asyncio.run(main())
```
