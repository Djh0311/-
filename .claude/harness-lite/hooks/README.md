# Harness Lite 0.7 Hooks

四个 Codex 事件共用 `hooks/dispatcher.js`：`SessionStart` 恢复短链，`UserPromptSubmit` 记录真实 user-turn receipt 和 Git baseline，`Stop` 写报告/usage 并在有新进展时返回顶层 `decision: "block"`；普通 leaf 范围外继续并在报告中标出，明确禁区仍停止。`PreToolUse` 只匹配 `^Bash$` 并硬拦未确认的精确 push。

安装器把 definition 语义合并到权威 root checkout 的 `.codex/hooks.json`，保留外来组。非法 JSON、未知 Harness 冲突或不可写路径进入 HOLD。definition 改变后必须重新查询 Codex `hooks/list`；只有宿主实际报告 modified/untrusted 时才需要用户在 UI review/trust，安装器不伪写 trust 记录。

官方 wire 字段使用 `hook_event_name`、`session_id`、turn 事件的 `turn_id`，Bash 命令使用 `tool_input.command`。`transcript_path` 不是稳定接口。PreToolUse 拒绝使用 `hookSpecificOutput.permissionDecision: "deny"`；非 push 输出为空，绝不返回尚未支持的 `ask`。

健康状态必须分别证明 installed、configured、trusted、四事件 observed，以及 native pre-push configured/probed。真实宿主验收通过 Codex `hooks/list` 的 currentHash/trustStatus 和事件 receipt 完成，离线直接执行 dispatcher 只算 synthetic fixture。

原生 Git pre-push 是单独、repo-wide 的维护动作；需要精确授权后才链式保留外来 hook，并用 disposable local bare remote probe。它与 Codex PreToolUse 共用同一 pending + 真实 user event + 模型 push-assert 的一次性绑定和密钥扫描逻辑。wrapper 在已管理 worktree 发现 runtime identity 或 marker 损坏时 fail closed；未安装 0.7 runtime 的其它 worktree 不介入，只链外来 hook。
