# Claude Code / Codex 调用桥接说明

本文记录 MiniPet 当前对 Claude Code 和 Codex 的本地调用方式、消息流、会话管理、退出清理和已知限制。它是 [README.md](../README.md) 中“连接 Claude Code / 连接 Codex”的详细补充。

## 总体目标

MiniPet 的桌宠输入不是一次性任务，而是连续聊天式输入。因此 Claude Code 和 Codex 都被封装成“本地子进程会话桥接”：

- 每次用户发送消息时，MiniPet 把输入转成 CLI 可理解的机器输入
- CLI 在子进程里生成回复
- MiniPet 把增量文本显示到回复卡片
- 收到最终结果后，把卡片状态切为 `done`
- 如果开启 TTS，再在最终结果阶段完成播报收尾

这两类后端的共同目标都是：

1. 避免 UI 直接依赖复杂的终端交互
2. 避免长期占用交互式 TUI
3. 让桌宠侧的状态机可以明确知道“开始 / 流式输出 / 结束 / 失败”
4. 在退出程序、切换后端或中断回复时能释放子进程

---

## Claude Code 调用方式

### 启动命令

MiniPet 只保留 Claude Code 的 `stream-json` 子进程方式。首次创建会话时使用：

```bash
claude --print \
  --verbose \
  --input-format stream-json \
  --output-format stream-json \
  --include-partial-messages \
  --replay-user-messages \
  --permission-mode auto \
  --session-id <由项目路径生成的固定 UUID>
```

同一个会话在 MiniPet 重启后使用：

```bash
claude --print \
  --verbose \
  --input-format stream-json \
  --output-format stream-json \
  --include-partial-messages \
  --replay-user-messages \
  --permission-mode auto \
  --resume <固定 UUID>
```

`--resume` 只恢复原会话，不使用 `--fork-session`，不会生成分叉会话。

### 关键参数含义

- `--print`
  - 让 Claude Code 以非交互方式向 stdout 输出结果
- `--verbose`
  - 当前版本使用 `--output-format stream-json` 时必须加
- `--input-format stream-json`
  - MiniPet 通过 JSONL 事件把用户消息写入 stdin
- `--output-format stream-json`
  - 让 Claude Code 以机器可解析事件流输出
- `--include-partial-messages`
  - 允许流式增量输出
- `--replay-user-messages`
  - 让会话保持对历史消息的回放能力
- `--permission-mode auto`
  - 让 CLI 以自动权限模式运行
- `--session-id ...`
  - 首次创建固定 ID 的 Claude Code 会话
- `--resume ...`
  - 后续启动时恢复该固定 ID 的已有会话

### 会话 ID 生成

MiniPet 不单独保存 Claude Code 的 session id，而是由项目目录和重置 token 稳定生成：

```text
session_id = UUID(sha256(project_dir + reset_token).前 16 字节)
```

规则：

- 项目目录相同、reset token 相同 → session id 相同
- 用户点击“重置会话” → reset token 加 1 → session id 改变
- 同一项目目录重启 MiniPet → 仍会复用相同会话上下文

MiniPet 会把已经成功创建的 ID 记录在 `claude_code_known_sessions`：

- ID 不在列表中 → 使用 `--session-id` 创建
- ID 已在列表中 → 使用 `--resume` 恢复
- 创建成功后 → 把 ID 写入列表
- `--session-id` 报 ID 已存在 → 自动记为已知并改用 `--resume`
- `--resume` 报找不到会话 → 自动移除标记并改用 `--session-id`

这个标记只负责判断“创建还是恢复”，真正的聊天上下文仍由 Claude Code 自己保存。

### 输入格式

MiniPet 发给 Claude Code 的最小用户事件为一行 JSON：

```json
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"你好"}]}}
```

### 输出解析

MiniPet 读取 stdout 的每一行，并处理以下情况：

- 顶层 `stream_event` 包裹：
  - 实际事件在 `event` 字段里
- `content_block_delta`
  - 取 `delta.text` / `delta.thinking` 作为增量文本
- `content_block_start`
  - 取文本块的初始内容
- `message_delta`
  - 取 `delta.text`
- `result`
  - 视为最终结果，切换回复卡片为 `done`

### 卡片与 TTS 行为

- 流式阶段：
  - 回复卡片状态为 `streaming`
  - 语音播报以 `terminal=False` 持续入队
- 最终结果阶段：
  - 回复卡片状态为 `done`
  - 语音播报以 `terminal=True` 收尾
- 失败阶段：
  - 回复卡片状态为 `failed`

### 清理策略

为了避免 `Session ID ... is already in use`：

- MiniPet 退出时会停止当前 Claude Code 子进程
- 切换后端时会停止当前 Claude Code 子进程
- Claude Code 启动前，会先清理当前 MiniPet 自己拉起的同 session 残留进程
- 只清理当前 MiniPet 父进程下的 `claude.exe`
- 不会去杀用户手动启动的别的 Claude Code 进程

### 现状限制

Claude Code 这条桥接仍是“单会话单进程”模型：

- 如果外部还有别的 Claude Code 进程占着同一个 session id，MiniPet 仍可能启动失败
- 这时需要先结束那个外部进程，或点击“重置会话”换一个新 session id

---

## Codex 调用方式

### 启动命令

Codex 不走交互式 TUI / winpty，而是每轮使用一个短生命周期的非交互 `exec` 子进程。首次消息创建持久化 thread：

```bash
codex exec \
  --json \
  --cd <项目目录> \
  -
```

MiniPet 从输出的 `thread.started.thread_id` 保存 Codex 实际生成的 thread ID。后续消息和 MiniPet 重启后的消息恢复该 thread：

```bash
codex exec resume <thread_id> \
  --json \
  -
```

不使用 `--ephemeral`，否则 Codex 不会保存可恢复会话；也不使用 fork。

### Thread 持久化与重置

thread ID 按“规范化项目路径 + `codex_reset_token`”保存在 MiniPet 设置中：

- 没有 thread ID → 普通 `codex exec` 创建
- 有 thread ID → `codex exec resume <thread_id>` 恢复
- 收到 `thread.started` → 写入或更新 ID
- resume 明确返回 thread/session 不存在 → 删除旧 ID，对同一个 prompt 普通创建重试一次
- 认证、权限、参数或网络错误 → 不错误地回退创建
- 点击设置页“重置会话” → token 加 1，下一条消息创建新 thread

### 输入方式

MiniPet 把每轮用户输入写入该轮 Codex 子进程 stdin，随后关闭 stdin 并读取 JSONL stdout。多条消息在本地队列中串行处理，不会并发恢复同一个 thread。

### 输出解析

主要事件：

- `thread.started`：提取并持久化 `thread_id`
- `item.completed` 且 `item.type == agent_message`：提取最终回答候选并更新回复卡片
- `turn.completed`：确认本轮结束，发出最终结果
- `error / fatal / turn.failed`：提取真实错误
- 非 JSON stdout：只作为卡片诊断输出，不作为最终回复

命令、工具和 reasoning item 不会被误当成最终回答。

### 卡片与 TTS 行为

- 每次输入先创建新的等待卡片
- agent message 到达时更新 `streaming` 卡片
- `turn.completed` 后把卡片切为 `done`
- 流式和诊断内容不送 TTS
- 仅最终 agent message 以 `terminal=True` 播报一次

### 进程清理

Codex 每轮进程正常完成后会被 `wait()` 回收。中断回复、切换后端、重置会话或退出 MiniPet 时，会按 CTRL_BREAK/SIGINT、terminate、kill 的顺序停止当前进程，并等待线程结束。

---

## 两者的共同 UI 约定

MiniPet 对 Claude Code 和 Codex 都遵循同一套桌宠侧状态机：

1. 发送前先开启新轮次
2. 显示“正在启动”或“等待输出”卡片
3. 流式输出时不断更新同一张卡片
4. 最终结果到达后切为 `done`
5. 出错时切为 `failed`
6. 如果开启语音播报，最终结果阶段负责收尾

这套约定的目的，是让它们和内置大模型、OpenClaw、MiniPet 协议后端的体验尽量统一。

---

## 当前代码位置

- Claude Code 桥接：`src/clients/claude_code_client.py`
- Codex 桥接：`src/clients/codex_client.py`
- 桌宠流程编排：`src/app.py`
- 设置页入口：`src/windows/settings/basic_pages.py`

---

## 推荐使用方式

- Claude Code 和 Codex 都支持当前项目内连续聊天以及 MiniPet 重启后恢复上下文
- Claude Code 运行中复用一个常驻 stream-json 进程；Codex 每轮启动一个短进程并 resume 同一 thread
- 建议始终从 MiniPet 的设置页选择项目和重置会话，不要在外部同时操作 MiniPet 正在使用的同一会话
