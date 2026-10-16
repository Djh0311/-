# 仓外归档边界

以下内容已经从当前产品运行边界中移出，只能存在于访问受控、带校验清单的仓外归档：

- 历史 raw capture 和 live evidence；
- 旧 Harness runtime、控制面、生命周期、报告、audit 和 usage；
- 旧 authority、迁移现场、完整 dispatch/task graph；
- 被退役 worktree 的完整工作副本、Git refs 和共享 Git 元数据；
- 未被当前产品路线采用的 H5/Wechat 实验源码。

“仓外”指不在 Git 跟踪范围内的本地归档。自 2026-10-08 起 `_archive/` 位于仓库根目录下，但被 `.gitignore`（以及本地 `.git/info/exclude`）排除：它不进入 Git，不属于产品代码，也不是运行、测试或授权依赖。

当前有三个独立仓外载体：

- `/Users/yoyi/爬虫/_archive/meituan-collection-agent-owned-v2-2026-08-11`：旧 Git/worktree、raw/live evidence、Harness 和迁移现场；
- `/Users/yoyi/爬虫/_archive/meituan-stage2-history-2026-08-11`：51 个 Stage 2 成果目录、38 个 dispatch、10 份 handoff 和精选无值报告的原件级归档；
- `/Users/yoyi/爬虫/_archive/root-legacy-20261008`：2026-10-08 仓库结构重构时，从旧工作根移入的 100 个顶层条目（90 个目录、10 个文件），包括旧 `meituan-collection-agent-owned-v2` 仓库、历史 stage/dispatch 目录和 handoff。内容原字节保留（4278 个文件逐一校验），不删除、不改写，也不恢复成授权。迁移清单、校验和与恢复脚本在 `_archive/root-legacy-20261008.receipt/`。

为了让项目知识可检索，本仓还在 `historical_assets/` 保存关键安全源码与测试的原字节副本，在 `docs/history/original-reports/` 保存 19 份无值原始报告。它们没有 raw、control 或 live evidence，不是运行依赖、当前 Harness 状态或授权。

需要查证历史时先读 `docs/history/` 和归档 manifest；任何语义读取、恢复执行或重新导入都需要新的任务和边界裁决。

## 2026-10-08 起的旧路径映射

| 重构前路径 | 现路径 |
| --- | --- |
| `/Users/yoyi/爬虫/meituan-collection-agent-owned-v3/<x>` | `/Users/yoyi/爬虫/<x>` |
| `/Users/yoyi/爬虫/<并列旧条目>`（stage2/dispatch 目录、handoff、旧 v2 仓库等） | `/Users/yoyi/爬虫/_archive/root-legacy-20261008/<并列旧条目>` |

`historical_assets/`、`docs/history/` 和归档报告中写着的旧绝对路径是历史原文，保持不改；需要定位文件时按上表换算。
