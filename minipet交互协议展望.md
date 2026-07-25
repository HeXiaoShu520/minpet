# miniPet 交互协议展望

本文承接 `minipet交互协议设计.md` 中未进入 V1 核心协议的能力。

V1 的原则是：核心协议只保留 `session`、`user`、`surface`、`agent` 四个概念。本文中的能力都应该作为 `surface.kind`、`agent.state` 子结构或后续扩展协议出现，而不是让第一版协议膨胀成一堆命令。

## 1. 更丰富的 Surface

V1 第一版只定义：

```text
bubble | card | confirm | input | choice
```

后续可扩展：

| kind | 用途 |
| --- | --- |
| `message` | 展示外部来源消息上下文，例如飞书消息 |
| `timeline` | 展示多步骤任务流程 |
| `feed` | 展示摘要信息流 |
| `dashboard` | 展示宠物展开面板 / 工作台 |
| `inbox` | 展示待办托盘 / 背包 |
| `badge` | 展示低打扰角标 |
| `form` | 轻量表单 |
| `media` | 图片、音频、文件预览 |

原则：

- 优先扩展 `surface.kind`，不要轻易新增顶层消息族。
- `surface.show`、`surface.update`、`surface.close` 仍然是生命周期入口。
- 复杂 UI schema 应该保持轻量，避免 miniPet 变成完整 IM 或浏览器容器。

## 2. Timeline

适合展示长任务步骤。

```json
{
  "type": "surface.show",
  "payload": {
    "surface_id": "schedule-meeting-001",
    "kind": "timeline",
    "title": "正在帮你约会议",
    "steps": [
      { "id": "parse", "title": "理解需求", "status": "done" },
      { "id": "freebusy", "title": "查询空闲时间", "status": "running" },
      { "id": "confirm", "title": "等待你选择时间", "status": "pending" }
    ],
    "actions": [
      { "id": "cancel", "label": "取消", "style": "quiet", "intent": "cancel" }
    ]
  }
}
```

## 3. Feed

适合“今天发生了什么”“上午飞书摘要”这类信息流。

```json
{
  "type": "surface.show",
  "payload": {
    "surface_id": "morning-feed-001",
    "kind": "feed",
    "title": "今天上午摘要",
    "items": [
      {
        "id": "item-1",
        "title": "产品群讨论了接口排期",
        "summary": "核心结论：今天需要给出初版方案。"
      }
    ]
  }
}
```

## 4. Dashboard

宠物展开面板，可作为桌面 AI 办公入口。

```json
{
  "type": "surface.show",
  "payload": {
    "surface_id": "main-dashboard",
    "kind": "dashboard",
    "title": "办公助手",
    "sections": [
      {
        "id": "todo",
        "title": "待处理",
        "items": [
          { "id": "m1", "text": "产品群消息待回复", "level": "important" }
        ]
      }
    ],
    "actions": [
      { "id": "ask", "label": "问飞书", "style": "primary", "intent": "custom" }
    ]
  }
}
```

## 5. Inbox / Badge

`inbox` 和 `badge` 用于低打扰保留事项。

可能形态：

```json
{
  "type": "surface.show",
  "payload": {
    "surface_id": "todo-inbox",
    "kind": "inbox",
    "items": [
      {
        "id": "todo-001",
        "category": "lark_message",
        "title": "产品群有一条消息可能需要回复",
        "priority": "important",
        "status": "pending"
      }
    ]
  }
}
```

角标可以作为 `surface.update` 的轻量属性，也可以作为未来专门的本地状态：

```json
{
  "type": "surface.update",
  "payload": {
    "surface_id": "pet-badge",
    "kind": "badge",
    "value": 3,
    "level": "important",
    "tooltip": "有 3 个 AI 判断需要你处理的事项"
  }
}
```

## 6. 飞书 / OpenClaw 场景

miniPet 不做完整飞书客户端，不转发普通飞书通知。

适合接入的场景：

- AI 总结今天需要处理的事项。
- AI 判断某条消息需要用户处理，并展示上下文。
- AI 生成飞书回复草稿，请用户确认或修改。
- AI 整理会议纪要，生成待办。
- 用户拖拽飞书链接、文档或本地文件给宠物处理。
- 长任务执行中，展示状态和进度。

边界：

- 普通消息通知由飞书原生负责。
- 业务执行由后端负责。
- 高风险动作必须回到 `surface.show kind=confirm`。

## 7. Agent Task Graph

V1 的 `agent.state` 只表达当前状态。未来可以扩展任务图：

```json
{
  "type": "agent.state",
  "payload": {
    "state": "working",
    "task": {
      "id": "briefing-001",
      "title": "整理今日待处理",
      "steps": [
        { "id": "messages", "title": "检索消息", "status": "done" },
        { "id": "tasks", "title": "整理任务", "status": "running" }
      ]
    }
  }
}
```

如果步骤需要变成可见 UI，再投射为 `surface.show kind=timeline`。

## 8. 上下文授权

未来如果需要外部后端读取上下文，应统一成清晰、显式授权的上下文协议。

方向：

- `context.request`：后端请求 miniPet 提供用户主动授权的上下文。
- `context.response`：miniPet 返回授权后的上下文。

原则：

- 不自动采集敏感上下文。
- 用户必须知道 miniPet 传了什么。
- 可撤销、可审计。

## 9. 能力协商增强

V1 的能力协商是轻量的。未来可以支持：

```json
{
  "protocol": "minipet.v1",
  "surface_kinds": ["bubble", "card", "confirm", "input", "choice", "timeline"],
  "features": {
    "surface_update": true,
    "surface_close": true,
    "markdown": "plain_text_fallback",
    "voice": false,
    "file_drop": true
  },
  "limits": {
    "max_actions": 4,
    "max_content_chars": 4000
  }
}
```

## 10. 权限与审计

未来需要：

- 受信任后端白名单。
- 本地 token / 设备绑定。
- 高风险动作二次确认。
- 用户可见的权限设置页。
- 本地审计日志。
- 文件路径投喂提示。
- 非 localhost 后端连接警告。

## 11. 多端与多宠物

未来如果支持多设备或多宠物，需要补充：

- `session_id`
- `device_id`
- `pet_id`
- `user_id`
- surface 归属关系
- 同步策略

V1 暂不强制这些字段，只在消息信封中预留空间。

## 12. 旧协议长期策略

旧事件名仍可保留兼容，但不再作为新能力入口。

建议演进：

1. 当前阶段：旧 type + V1 metadata。
2. 中间阶段：支持 `MINIPET_PROTOCOL_MODE=legacy|v1|dual`。
3. 稳定阶段：新后端默认使用 V1 type，旧事件名作为 compatibility layer。

