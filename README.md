# Meituan Collection Agent

这是一个离线优先、默认拒绝的采集基础项目。当前仓库只保留三类可继续维护的内容：

- `autocapture/`：默认 `DISARMED` 的离线安全基础；
- `parser_candidate/`：只消费合成、脱值事件的隔离候选，尚未接入正式 Provider；
- `contracts/`：来源资格、观察、字段、证据和停止行为的通用闭合合同。

## 当前状态

```text
SOURCE_QUALIFICATION=NO_QUALIFIED_SOURCE
PROVIDER_QUALIFIED_FOR_BUILD=false
LIVE_CAPTURE_LATCH=CLOSED
EXECUTION_LATCH=CLOSED
PARSER_CANDIDATE=NOT_INTEGRATED
P02_FORMAL_PARSER=NOT_ENTERED
```

这些状态表示：仓库具备离线安全基础和候选解析能力，但尚未证明真实来源、真实 Provider、真实 loader、网络、微信或浏览器 UI 采集。历史观察任务没有取得项目内可读的脱敏事件输入，因此没有产生真实观察，也不会在新仓自动恢复。

## 离线验证

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s autocapture/tests -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -B autocapture/tools/verify_autocapture_build.py --repo-root . --strict
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s parser_candidate/tests -p 'test_*.py' -v
git diff --check
```

当前产品边界见 `docs/boundaries.md`，架构见 `docs/architecture.md`，资格状态见 `docs/qualification-status.md`。历史 raw capture、旧 Harness、旧任务图和旧 worktree 现场只存在于仓外受控归档，不是本仓依赖或当前权威。
