# miniPet 外部交互接口设计

本文定义 miniPet 对外提供的桌宠能力接口。目标是让外部程序可以用统一协议控制 miniPet 显示气泡、播放动作、展示文字、播放语音、读取/设置位置、切换动画和订阅状态，而不需要直接调用 miniPet 内部 Python 对象。

## 设计目标

- miniPet 是能力提供方，不绑定任何具体业务系统。
- 外部程序只通过协议表达意图，不关心 PySide6、动画线程、资源目录等内部实现。
- 协议可扩展，旧客户端发送旧字段仍能工作。
- 所有请求都可带 `request_id`，miniPet 返回对应结果，方便外部系统做确认和重试。
- 所有能力都可以通过 WebSocket 双向通道完成；HTTP 只作为按钮回调或兼容入口。

## 通信模型

### 默认 WebSocket 地址

```text
ws://127.0.0.1:18888/ws/pet
```

当前 miniPet 作为客户端连接外部事件源。后续建议支持两种模式：

- `client`：miniPet 主动连接外部事件源，兼容当前实现。
- `server`：miniPet 本地启动 WebSocket server，外部程序主动连接 miniPet。

推荐最终默认模式是 `server`，因为“对外提供能力”更符合外部控制 miniPet 的语义。

### 消息包格式

所有消息使用 JSON。

```json
{
  "version": "1.0",
  "request_id": "optional-client-generated-id",
  "type": "bubble.show",
  "source": "my-app",
  "timestamp": 1730000000000,
  "payload": {}
}
```

字段说明：

- `version`：协议版本，当前为 `1.0`。
- `request_id`：可选。外部生成，用于匹配响应。
- `type`：能力类型，格式为 `domain.action`。
- `source`：可选。调用来源，例如 `lark`、`scheduler`、`local-script`。
- `timestamp`：可选。毫秒时间戳。
- `payload`：具体能力参数。

### 响应格式

```json
{
  "version": "1.0",
  "request_id": "same-id",
  "type": "response",
  "ok": true,
  "result": {},
  "error": null
}
```

失败：

```json
{
  "version": "1.0",
  "request_id": "same-id",
  "type": "response",
  "ok": false,
  "result": null,
  "error": {
    "code": "unknown_action",
    "message": "Action not found: dance"
  }
}
```

## 能力总览

| 类型 | 能力 | 当前映射 |
| --- | --- | --- |
| `bubble.show` | 显示普通气泡 | `NotificationCenter.setup_bubble` |
| `bubble.smart` | 显示带按钮的智能气泡 | `NotificationCenter.setup_smart_bubble` |
| `bubble.close` | 关闭指定气泡 | 待实现 |
| `toast.show` | 显示系统通知 | `NotificationCenter.setup_notification` |
| `pet.action` | 播放宠物动作 | `DesktopPet.play_action` |
| `pet.say` | 显示文字并可选语音 | 气泡 + TTS |
| `pet.speak` | 只播放语音 | `TtsWorker` |
| `pet.move` | 移动宠物到指定位置 | `QWidget.move` |
| `pet.position.get` | 获取宠物位置 | `DesktopPet.pos/size` |
| `pet.fetch` | 找回宠物 | `DesktopPet.fetch_back` |
| `pet.switch` | 切换宠物角色 | `DesktopPet.load_pet` |
| `pet.status.get` | 获取状态和可用能力 | 待实现 |
| `ui.buttons.set` | 在宠物旁显示外部定义按钮 | 待实现 |
| `ui.buttons.clear` | 清除外部定义按钮 | 待实现 |
| `animation.play` | 播放动画/动作 | `DesktopPet.play_action` |
| `animation.list` | 列出当前宠物动作 | `profile.acts` |
| `chat.open` | 打开聊天窗口 | `DesktopPet.show_chat` |
| `settings.open` | 打开设置窗口 | `show_settings` |

## 气泡能力

### bubble.show

显示普通文本气泡，适合轻提示、提醒、状态反馈。

```json
{
  "version": "1.0",
  "request_id": "bubble-001",
  "type": "bubble.show",
  "payload": {
    "text": "主人，该休息一下了。",
    "timeout_ms": 6000,
    "anchor": "pet_top",
    "offset": { "x": 0, "y": -12 },
    "style": "default"
  }
}
```

字段：

- `text`：必填，显示内容。
- `timeout_ms`：显示时长，默认 `6000`。
- `anchor`：气泡锚点。
  - `pet_top`：宠物顶部居中。
  - `pet_center`：宠物中心。
  - `screen`：使用屏幕坐标。
  - `cursor`：鼠标位置。
- `position`：当 `anchor=screen` 时使用。
- `offset`：相对锚点偏移。
- `style`：预留，`default`、`notice`、`warning`、`success`。

响应：

```json
{
  "type": "response",
  "request_id": "bubble-001",
  "ok": true,
  "result": { "bubble_id": "uuid" }
}
```

### bubble.smart

显示带标题、摘要、建议和按钮的智能气泡，适合外部消息、审批、日程提醒等。

```json
{
  "version": "1.0",
  "request_id": "smart-001",
  "type": "bubble.smart",
  "source": "lark",
  "payload": {
    "title": "产品群",
    "sender": "张三",
    "content": "下午四点能给个方案吗？",
    "summary": "产品群在催方案",
    "suggestion": "可以，我四点前发初版。",
    "priority": "high",
    "timeout_ms": 12000,
    "actions": [
      { "id": "send", "label": "发送建议", "type": "send_message", "text": "可以，我四点前发初版。" },
      { "id": "later", "label": "稍后", "type": "remind_later" },
      { "id": "ignore", "label": "忽略", "type": "ignore" }
    ],
    "metadata": {
      "chat_id": "optional",
      "message_id": "optional"
    }
  }
}
```

按钮点击事件由 miniPet 发回外部系统：

```json
{
  "version": "1.0",
  "type": "bubble.action",
  "source": "minipet",
  "payload": {
    "bubble_id": "uuid",
    "action": { "id": "send", "type": "send_message", "label": "发送建议" },
    "event": { "...": "原始 payload" },
    "text": "可以，我四点前发初版。",
    "metadata": {
      "chat_id": "optional",
      "message_id": "optional"
    }
  }
}
```

### bubble.close

关闭一个气泡。

```json
{
  "version": "1.0",
  "request_id": "close-001",
  "type": "bubble.close",
  "payload": {
    "bubble_id": "uuid"
  }
}
```

## 外部按钮能力

外部系统可以在宠物附近挂载临时按钮。典型场景是 AI 判断需要用户确认，例如“发送邮件”“批准审批”“创建日程”。miniPet 只负责展示按钮和把点击事件回传；真正执行动作的系统仍是外部 AI/Agent/自动化服务。

### ui.buttons.set

设置一组显示在宠物旁边的按钮。

```json
{
  "version": "1.0",
  "request_id": "buttons-001",
  "type": "ui.buttons.set",
  "source": "ai-agent",
  "payload": {
    "placement": "pet_right",
    "ttl_ms": 120000,
    "title": "邮件草稿已准备好",
    "buttons": [
      {
        "id": "send_email",
        "label": "发送邮件",
        "style": "primary",
        "icon": "send",
        "callback": {
          "type": "agent_action",
          "name": "send_email",
          "arguments": {
            "draft_id": "mail-draft-001"
          }
        }
      },
      {
        "id": "edit_email",
        "label": "修改",
        "style": "normal",
        "callback": {
          "type": "agent_action",
          "name": "edit_email",
          "arguments": {
            "draft_id": "mail-draft-001"
          }
        }
      },
      {
        "id": "cancel",
        "label": "取消",
        "style": "quiet",
        "callback": {
          "type": "dismiss"
        }
      }
    ],
    "metadata": {
      "conversation_id": "ai-session-001",
      "task_id": "mail-task-001"
    }
  }
}
```

字段：

- `placement`：按钮显示位置。
  - `pet_top`
  - `pet_right`
  - `pet_bottom`
  - `pet_left`
  - `cursor`
  - `screen`
- `ttl_ms`：按钮自动消失时间。默认 `120000`。
- `title`：可选，按钮组标题。
- `buttons`：按钮数组，建议最多 4 个。
- `button.id`：按钮 ID，点击时原样返回。
- `button.label`：按钮文案。
- `button.style`：`primary`、`normal`、`danger`、`quiet`。
- `button.icon`：预留图标名。第一版可以只支持内置图标映射。
- `button.callback`：外部系统需要的回调描述，miniPet 不解释业务含义，只原样返回。
- `metadata`：会在点击事件中原样返回。

响应：

```json
{
  "version": "1.0",
  "request_id": "buttons-001",
  "type": "response",
  "ok": true,
  "result": {
    "button_group_id": "uuid"
  }
}
```

### ui.button.clicked

用户点击按钮后，miniPet 向外部系统发送事件。

```json
{
  "version": "1.0",
  "type": "ui.button.clicked",
  "source": "minipet",
  "payload": {
    "button_group_id": "uuid",
    "button": {
      "id": "send_email",
      "label": "发送邮件",
      "style": "primary",
      "callback": {
        "type": "agent_action",
        "name": "send_email",
        "arguments": {
          "draft_id": "mail-draft-001"
        }
      }
    },
    "metadata": {
      "conversation_id": "ai-session-001",
      "task_id": "mail-task-001"
    }
  }
}
```

外部 AI/Agent 收到后可以继续执行：

1. 读取 `button.callback`。
2. 根据 `name=send_email` 调用真实邮件发送工具。
3. 执行完成后再调用 `pet.say` 或 `bubble.show` 告诉用户结果。

miniPet 不直接发送邮件，也不直接执行高风险操作；它只提供用户确认入口和点击回传。

### ui.buttons.clear

清除按钮组。

```json
{
  "version": "1.0",
  "request_id": "buttons-clear-001",
  "type": "ui.buttons.clear",
  "payload": {
    "button_group_id": "uuid"
  }
}
```

如果不传 `button_group_id`，表示清除所有外部按钮。

```json
{
  "version": "1.0",
  "request_id": "buttons-clear-all",
  "type": "ui.buttons.clear",
  "payload": {}
}
```

### 与 bubble.smart 的区别

- `bubble.smart` 适合“消息通知 + 顺手操作”，按钮跟随气泡生命周期。
- `ui.buttons.set` 适合“AI 等用户确认”，按钮可以独立存在更久，也能表达任务上下文。

示例：AI 写好邮件后，不应该只弹一个普通气泡；应该调用：

1. `pet.say`：提示“邮件草稿好了，要发送吗？”
2. `ui.buttons.set`：显示“发送邮件 / 修改 / 取消”。
3. 用户点击“发送邮件”。
4. miniPet 发出 `ui.button.clicked`。
5. 外部 AI 收到点击事件后调用邮件工具。
6. 外部 AI 调用 `pet.say` 返回“已发送”。

## 通知能力

### toast.show

显示屏幕右下角通知。

```json
{
  "version": "1.0",
  "request_id": "toast-001",
  "type": "toast.show",
  "payload": {
    "title": "构建完成",
    "message": "miniPet 打包任务已完成。",
    "timeout_ms": 5000,
    "icon": "default",
    "sound": true
  }
}
```

字段：

- `title`：标题。
- `message`：正文。
- `timeout_ms`：显示时长。
- `icon`：`default` 或资源路径/URL，第一版只建议支持本地资源名。
- `sound`：是否播放通知音。

## 宠物动作能力

### pet.action

播放当前宠物的动作。

```json
{
  "version": "1.0",
  "request_id": "action-001",
  "type": "pet.action",
  "payload": {
    "name": "happy",
    "mode": "interrupt",
    "repeat": 1,
    "fallback": "default"
  }
}
```

字段：

- `name`：动作名，对应当前宠物 `act_conf.json` 中的 key。
- `mode`：播放策略。
  - `interrupt`：立即打断当前动作。
  - `queue`：排队播放。
  - `if_idle`：仅空闲时播放。
- `repeat`：额外重复次数。第一版可忽略，使用资源配置中的 `act_num`。
- `fallback`：动作不存在时使用的动作。

错误码：

- `unknown_action`：动作不存在且无 fallback。
- `pet_not_loaded`：当前没有宠物资源。

### animation.list

列出当前宠物可用动作。

```json
{
  "version": "1.0",
  "request_id": "acts-001",
  "type": "animation.list",
  "payload": {}
}
```

响应：

```json
{
  "ok": true,
  "result": {
    "pet": "Kitty",
    "actions": ["default", "left_walk", "right_walk", "drag", "fall"]
  }
}
```

### animation.play

`animation.play` 是 `pet.action` 的别名。保留这个名称是为了让外部系统更直观地调用“播放动画”。

## 文字和语音能力

### pet.say

让宠物“说一句话”：显示气泡，可选同步播放 TTS。

```json
{
  "version": "1.0",
  "request_id": "say-001",
  "type": "pet.say",
  "payload": {
    "text": "我在这里。",
    "bubble": true,
    "speak": true,
    "voice": "default",
    "timeout_ms": 6000,
    "action": "default"
  }
}
```

执行顺序建议：

1. 如果 `action` 存在，先触发宠物动作。
2. 如果 `bubble=true`，显示普通气泡。
3. 如果 `speak=true`，调用 TTS 播放。

### pet.speak

只播放语音，不显示气泡。

```json
{
  "version": "1.0",
  "request_id": "speak-001",
  "type": "pet.speak",
  "payload": {
    "text": "会议还有五分钟开始。",
    "voice": "default",
    "interrupt": true
  }
}
```

字段：

- `text`：语音文本。
- `voice`：预留。第一版可以直接使用设置页里的默认音色。
- `interrupt`：是否打断当前 TTS。

错误码：

- `tts_not_configured`：TTS 未启用或缺少密钥。
- `tts_failed`：TTS 请求失败。

## 位置能力

### pet.position.get

获取宠物窗口位置。

```json
{
  "version": "1.0",
  "request_id": "pos-001",
  "type": "pet.position.get",
  "payload": {}
}
```

响应：

```json
{
  "ok": true,
  "result": {
    "x": 1520,
    "y": 820,
    "width": 180,
    "height": 220,
    "screen": {
      "x": 0,
      "y": 0,
      "width": 1920,
      "height": 1040
    },
    "anchor": {
      "top": { "x": 1610, "y": 820 },
      "center": { "x": 1610, "y": 930 },
      "bottom": { "x": 1610, "y": 1040 }
    }
  }
}
```

### pet.move

移动宠物。

```json
{
  "version": "1.0",
  "request_id": "move-001",
  "type": "pet.move",
  "payload": {
    "x": 1200,
    "y": 700,
    "coordinate": "screen",
    "duration_ms": 0,
    "clamp_to_screen": true
  }
}
```

字段：

- `x` / `y`：目标坐标。
- `coordinate`：`screen` 或 `relative`。
- `duration_ms`：移动动画时长。第一版可以只支持 `0`，直接移动。
- `clamp_to_screen`：是否限制在屏幕内。

### pet.fetch

召回宠物到当前屏幕右下角。

```json
{
  "version": "1.0",
  "request_id": "fetch-001",
  "type": "pet.fetch",
  "payload": {}
}
```

## 角色能力

### pet.switch

切换宠物角色。

```json
{
  "version": "1.0",
  "request_id": "switch-001",
  "type": "pet.switch",
  "payload": {
    "name": "Kitty"
  }
}
```

响应：

```json
{
  "ok": true,
  "result": {
    "pet": "Kitty"
  }
}
```

### pet.status.get

获取 miniPet 当前状态和能力。

```json
{
  "version": "1.0",
  "request_id": "status-001",
  "type": "pet.status.get",
  "payload": {}
}
```

响应：

```json
{
  "ok": true,
  "result": {
    "pet": "Kitty",
    "available_pets": ["ChrisKitty", "Kitty"],
    "actions": ["default", "drag", "fall"],
    "position": { "x": 1520, "y": 820, "width": 180, "height": 220 },
    "settings": {
      "on_top": true,
      "allow_drop": true,
      "scale": 1.0,
      "volume": 0.4
    },
    "capabilities": [
      "bubble.show",
      "bubble.smart",
      "toast.show",
      "pet.action",
      "pet.say",
      "pet.speak",
      "pet.move",
      "pet.position.get",
      "pet.fetch",
      "pet.switch",
      "animation.list",
      "chat.open",
      "settings.open"
    ]
  }
}
```

## 窗口能力

### chat.open

打开聊天窗口。

```json
{
  "version": "1.0",
  "request_id": "chat-001",
  "type": "chat.open",
  "payload": {
    "prefill": "帮我总结刚刚的消息"
  }
}
```

第一版可以忽略 `prefill`，只打开窗口。

### settings.open

打开设置窗口。

```json
{
  "version": "1.0",
  "request_id": "settings-001",
  "type": "settings.open",
  "payload": {
    "page": "basic"
  }
}
```

第一版可以忽略 `page`，只打开设置窗口。

## 兼容旧协议

旧协议事件应继续支持：

```json
{ "type": "message", "summary": "..." }
{ "type": "bubble", "message": "..." }
{ "type": "action", "pet_action": "happy" }
```

兼容映射：

| 旧类型 | 新类型 |
| --- | --- |
| `message` | `bubble.smart` |
| `bubble` | `bubble.show` |
| `action` | `pet.action` |

## 错误码

| code | 含义 |
| --- | --- |
| `invalid_json` | JSON 解析失败 |
| `invalid_request` | 请求结构不合法 |
| `unknown_type` | 未知 `type` |
| `missing_field` | 缺少必填字段 |
| `unknown_action` | 动作不存在 |
| `unknown_pet` | 宠物不存在 |
| `pet_not_loaded` | 当前没有加载宠物 |
| `tts_not_configured` | TTS 未配置 |
| `tts_failed` | TTS 播放失败 |
| `internal_error` | miniPet 内部错误 |

## 安全边界

第一版建议只监听本机地址：

```text
127.0.0.1
```

不要默认开放到局域网。后续如果需要远程控制，应增加：

- 访问 token
- 来源白名单
- 请求频率限制
- 用户确认敏感操作

## 第一阶段实现建议

先实现最小闭环：

1. 新增 `src/miniPet/interface_server.py`，在 miniPet 内启动本地 WebSocket server。
2. 将 `MiniPetApp._on_event` 改成调用统一 dispatcher。
3. 新增 `src/miniPet/command_dispatcher.py`，用 `PetCommandDispatcher` 把协议 `type` 映射到现有能力。
4. 保留 `EventClient` 作为兼容模式，收到旧事件后转成新协议。
5. 实现这些能力：
   - `bubble.show`
   - `bubble.smart`
   - `toast.show`
   - `pet.action`
   - `pet.say`
   - `pet.position.get`
   - `pet.move`
   - `pet.fetch`
   - `pet.switch`
   - `animation.list`
   - `pet.status.get`
   - `chat.open`
   - `settings.open`

第二阶段再实现：

- `bubble.close`
- `pet.speak` 的完整异步回执
- 移动补间动画
- 多客户端订阅状态事件
- 权限 token 和访问控制

## Python 调用示例

```python
import asyncio
import json
import websockets

async def main():
    async with websockets.connect('ws://127.0.0.1:18888/ws/pet') as ws:
        await ws.send(json.dumps({
            'version': '1.0',
            'request_id': 'demo-001',
            'type': 'pet.say',
            'payload': {
                'text': '我在这里。',
                'bubble': True,
                'speak': False,
                'action': 'default'
            }
        }, ensure_ascii=False))
        print(await ws.recv())

asyncio.run(main())
```
