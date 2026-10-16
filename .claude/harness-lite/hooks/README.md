# Harness Lite Hooks

四个 Codex 事件共用 `hooks/dispatcher.js`。`SessionStart` 和 `UserPromptSubmit` 恢复短链与 current leaf 最小投影，并只根据当前 leaf/委派/恢复状态加载已触发的 guidance；无 active 不展示 heartbeat，无失败不展示恢复链，无派发事件不展示 capability。`UserPromptSubmit` 另记录 user-role 来源 receipt 和 Git baseline；`Stop` 只在短期授权文件与当前 project/session/turn/leaf/stage 精确绑定且委派账出现带 evidenceRef 的 semantic progress 时返回顶层 `decision: "block"`；固定 continuation 先判为 internal，不能自签授权或扩大范围。`PreToolUse` 只匹配 `^Bash$` 并硬拦未确认的精确 push。

Hook 自身只投影和记账，不 spawn、poll、interrupt、takeover，也不维护后台 timer。leaf 内 work unit 可并行的依据是依赖和写面：无依赖且写面不重叠可同时 active；写面前缀重叠或共享状态冲突必须 integration owner、重拆或串行；`reported_complete` 与 `accepted` 分离，只有 `accepted` 解锁依赖。

指导模型在真实 spawn/wait/status/message/interrupt/takeover 工具调用之后，从已安装项目根目录加载稳定 runtime 模块：`const delegation = require("./.claude/harness-lite/lib/delegation.js")`，再直接调用 `delegation.recordAgentStatus()`、`recordAgentObservation()`、`recordAgentFailure()` 或 `recordAgentRecovery()` 记账；用户不需要、也不应运行 Harness 命令来同步 agent 状态。这个路径来自安装到项目内的 Harness runtime，不假设 npm package 解析。这些接口只写 delegation ledger，不连接 provider，不等待 agent，不中断 agent，不保存 prompt/transcript/code/credential。active unit 的 channel、model、modelFamily、reasoning、dependencies、writeScope、status 和 heartbeat/activity/progress 从同一 carrier 读回。

300000ms heartbeat 是只读 reminder。heartbeat 只更新 `heartbeatAt`，activity 只更新 `activityAt/activityKind`，semantic progress 只允许 verified-fact、route-eliminated、acceptance-advanced、root-cause-isolated、actionable-blocker 且必须绑定 evidenceRef。旧的文件/head/verify activity 不再冒充 semantic progress；当前 Stop 不再使用“同处失败三次”续跑/停点逻辑。

wait/status 观察以 300000ms 为单次上限：指导模型等待真实 agent 时，最多一次 wait/status 到这个窗口；到期只记录 heartbeat 或 activity，不能把沉默、long-tool、provider delay 当 semantic progress。只有真实完成标准直接验证后才记录 `reported_complete` 或 `accepted`；`reported_complete` 只触发主管验收，`accepted` 必须携带 `evidenceRef` 才解锁依赖。

无法从状态可靠观测的语义动作，由指导模型用只读 `hl status --intent <intent> --json` 取当次 guidance。九类事件（`leaf-definition`、`route-clarification`、`pre-dispatch`、`agent-active`、`agent-reported`、`problem-recovery`、`leaf-closeout`、`legacy-fact`、`push-attempt`）统一综合成一个 `focus`、一个 `decisionQuestion` 和一个 `nextAction`；intent 不授权、不伪造状态、不持久化，未知值拒绝。完整目标和完成标准通过带完整性标记与 sentinel 的 completion carrier 传递。只有真实命中的既有硬风险才出现拦截说明，普通路径不增加确认。

`project` profile 把 definition 精确合并到权威 root checkout 的 `.codex/hooks.json` 并保留外来组。`managed` profile 不写项目 Harness Hook，由管理员配置的 `managed_dir` 统一加载 global gateway；gateway 校验受保护 registry、allowlist 和 global runtime 后才转发。非法 JSON、未知 Harness 冲突、未知 digest 或不安全路径进入 HOLD。

官方 wire 字段使用 `hook_event_name`、`session_id`、turn 事件的 `turn_id`，Bash 命令使用 `tool_input.command`。`transcript_path` 不是稳定接口。PreToolUse 拒绝使用 `hookSpecificOutput.permissionDecision: "deny"`；非 push 输出为空，绝不返回尚未支持的 `ask`。

健康状态必须分别证明 installed、configured、trusted/policyTrusted、四事件 observed，以及 native pre-push configured/probed。证据 bundle 保存精简 hooks/list 前后快照、started/completed run id 和无秘密 receipt，再做 exact/ambiguous/missing join。Desktop、CLI、unknown-live 和 synthetic 分开计算，离线直接执行 dispatcher 不能补真实宿主或 Desktop。

原生 Git pre-push 是单独、repo-wide 的维护动作；需要精确授权后才链式保留外来 hook，并用 disposable local bare remote probe。它与 Codex PreToolUse 共用同一 pending + user-role event + 模型 push-assert 的一次性绑定和密钥扫描逻辑。wrapper 在已管理 worktree 发现 runtime identity 或 marker 损坏时 fail closed；未安装当前 Harness Lite runtime 的其它 worktree不介入，只链外来 hook。
