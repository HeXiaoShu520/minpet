# MINIPET 通用事件协议（Legacy）

本文是旧版简化事件协议，继续用于兼容 miniClaw、脚本和早期 OpenClaw adapter。新后端优先阅读 `minipet交互协议设计.md`，使用 V1 的 `session` / `user` / `surface` / `agent` 核心协议。

MINIPET 不强绑定飞书。miniClaw、飞书、脚本或其他软件都可以作为外部事件源，通过 WebSocket 向 MINIPET 推送事件。

默认连接地址：

```text
ws://localhost:18888/ws/pet
```

MINIPET 收到事件后只做三件事：

1. 展示宠物气泡
2. 按优先级触发宠物动作
3. 用户点击气泡按钮时，把动作回传给外部服务

动作回传优先走当前 WebSocket 连接，miniPet 会发送兼容事件 `interaction.action`，payload 中同时带有 V1 元信息 `v1_type: user.action`。当 WebSocket 不可用时，才回退到 HTTP：

```text
POST http://localhost:18888/actions/execute
```

## message 事件

用于外部消息、提醒、AI 建议。

```json
{
  "type": "message",
  "title": "产品群",
  "sender": "张三",
  "content": "下午四点能给个方案吗？",
  "summary": "产品群在催方案",
  "suggestion": "可以，我四点前发初版。",
  "priority": "high",
  "is_at_me": true,
  "pet_action": "alert",
  "timeout": 12,
  "actions": [
    { "id": "send", "type": "send_message", "label": "发送建议" },
    { "id": "later", "type": "later", "label": "稍后处理" },
    { "id": "ignore", "type": "ignore", "label": "忽略" }
  ],
  "source": "miniclaw",
  "chat_id": "optional",
  "message_id": "optional"
}
```

字段说明：

- `title`：气泡标题，通常是群名、软件名或提醒来源
- `sender`：发送人，可选
- `content`：原始内容
- `summary`：优先显示的摘要；为空时显示 `content`
- `suggestion`：AI 建议回复或建议动作
- `priority`：`normal` / `high` / `urgent`
- `is_at_me`：是否需要用户关注
- `pet_action`：显式指定宠物动作；为空时 MINIPET 按优先级自动选择
- `timeout`：气泡显示秒数，默认 12 秒
- `actions`：最多显示前三个按钮

## bubble 事件

只显示普通文本气泡，不带按钮。

```json
{
  "type": "bubble",
  "message": "主人，该休息一下了。",
  "bubble_type": "break_reminder",
  "timeout": 8
}
```

## action 事件

只触发宠物动作，不显示智能消息气泡。

```json
{
  "type": "action",
  "pet_action": "happy",
  "priority": "normal"
}
```

## 按钮回传

用户点击智能气泡按钮时，MINIPET 会尝试 POST 到 `/actions/execute`：

```json
{
  "event": { "...": "原始事件" },
  "action": { "id": "send", "type": "send_message", "label": "发送建议" },
  "type": "send_message",
  "chat_id": "optional",
  "message_id": "optional",
  "text": "可以，我四点前发初版。"
}
```

如果外部服务不在线，MINIPET 会静默失败，不影响独立运行。
