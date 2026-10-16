# 重建与迁移收据

- 日期：2026-08-11
- 旧项目：`meituan-collection-agent-owned-v2`
- 新项目：`meituan-collection-agent-owned-v3`

## 载体与 Git

- 旧仓 branch：`codex/harness-lite-cutover-20260807`
- 旧仓 HEAD：`45b32b70fca11f618065db1b93acca51266c8158`
- 旧仓 all-files status SHA-256：`245598b98bb711dc10f2eef5f002c909fc193971a9f281d03ab445bbeca18189`
- 旧仓 14-worktree expanded fingerprint：`c20d4d3c6f876788690597994bb6947e311a91ef459d75cc2ac7e35be1403abb`
- 仓外归档 receipt ID：`meituan-collection-agent-owned-v2-2026-08-11`
- 归档 artifact receipt SHA-256：`cd509f4dfc78e5181885039cb128fb367d5febd882e8f57dcc4bc30a4e472f5e`
- 产品转移 preimage tar SHA-256：`a2c028f8df33bcce79d9c2f993d9d802863cf5f1848df991cf34e010554dfb47`
- 新仓初始产品 commit：`868a1b033224691641bed7d0ce61799f0da3895b`
- 新仓初始产品 tree：`1f54f8e9aafdbaaa9a1c8a8cbaee7e676e4eda64`
- 新仓 branch：`codex/project-rebuild-20260811`
- remote / upstream：无

本收据所在提交只补充 provenance，不改变初始产品 tree 中的代码、合同、runtime 或资格结论。

## 选择结果

直接带入 52 个普通文件：当前 `autocapture/`、隔离 `parser_candidate/`（排除历史 raw projection 工具）、14 个通用合同及其 README、严格 verifier 依赖的 design 文档。

摘要后新写：README、项目协作边界、当前状态、架构、资格、证据、仓外归档边界和无值资格检查清单。

明确未带入：历史 raw/live evidence、旧 Harness runtime 与控制面、旧 leaf/stage/done/report/audit/usage、旧 authority/dispatch/task graph、H5/Wechat 实验源码、其它 worktree 内容、历史 raw projection 工具。它们只存在于仓外受控归档，且不是新仓运行依赖。

## 初始 Harness Lite 0.7（历史迁移收据）

`2026-08-11` 重建时的协作与生命周期权威是 Harness Lite 0.7。以下 0.7 载体、摘要和宿主状态保留为历史事实；当前版本以本文的 0.13.0 升级收据为准。爬虫产品内容仍以用户当前目标和项目计划为范围来源，历史任务包和报告不恢复为执行授权。

### Lite authority carrier

- 唯一方案权威：`/Users/yoyi/Documents/Codex/2026-07-26/users-yoyi-documents-codex-2026-07/outputs/harness-lite-0.7-upgrade-plan-2026-08-10.md`
- 干净源码：`/Users/yoyi/harness engineering/harness-lite-0.7-authority`
- branch / commit / tree：`codex/harness-lite-0.7-authority-clean` / `90b5f8c14a71a415d87374821fff4af35ad6372e` / `1ba67855a5c3b25138e3ad8dafdd7ce243c2a40f`
- 精确安装载体：`/Users/yoyi/Documents/Codex/2026-07-26/users-yoyi-documents-codex-2026-07/outputs/harness-lite-0.7.0-runtime-source-90b5f8c.tar.gz`
- 载体 manifest：`/Users/yoyi/Documents/Codex/2026-07-26/users-yoyi-documents-codex-2026-07/outputs/harness-lite-0.7.0-runtime-source-90b5f8c.manifest.json`
- manifest SHA-256：`3f43ad3c55a467f6055dfcb9d543312ff79ed914711c05bb878d872ef6abfae0`
- managed files：12；载体为 local / unreleased / unpushed；`licenseDeclared=false`

`ownership.json` 中的 `sourceCommit=working-copy:640ad4d…` 是恢复的 0.7 working-copy 历史字段，不是源码权威 HEAD。精确权威由上面的 `90b5f8c…`、tree、bundle SHA 和 package digest 共同锁定；不得改写 ownership 来伪装该字段。

- 源码权威 commit：`90b5f8c14a71a415d87374821fff4af35ad6372e`
- runtime source bundle SHA-256：`d0b445e3362f76d93c248d639f1368ca0a3a84a3e88a828f43ea00a0e87e310b`
- 安装前 identity：`fresh`
- 安装后 identity：`current`
- package digest：`sha256:99323df550792f5dc34a33ae7e09df17fae727f5c8d20195f736e746057bafb3`
- instruction digest：`sha256:4a87ff5ab56331b588057614ab5f1c824589017088b38404ea4923bbc3fe9320`
- Hook definition digest：`sha256:9dcc3c8b3f4c028956aa42ff34ca21e807903dff9d407d947837ac39186e5054`
- installed：true
- configured：true
- trusted：false（未做真实宿主 trust 验收）
- observed：四事件均 false（未做真实宿主事件观测）
- native pre-push：未安装

因此当前只证明 installed 和 configured；尚未证明 trusted、observed 或 effective，也不把本地载体冒充已发布版本。

机制预算保持：新增用户命令 0、持久状态 0、非 push 门禁 0、Hook 事件 0、内部命令 0、技能 0、风险模块 0、项目专属 Core 兼容 0。

## 2026-10-07 Harness Lite 0.13.0 升级收据

本次用户明确批准备份和项目级 Harness 升级。使用固定 `v0.13.0` 源码提交 `aac6bd5fe721aa126cf6d9203e5d96d2db540913`，未带入远端工作区未提交的 Cursor 适配、私有配置或源仓计划。

### 当前载体与保留边界

- 升级前 identity / version：`official-07` / `0.7.0`；升级后：`current` / `0.13.0`。
- profile：`project`；managed files：20；没有安装全局 managed runtime 或原生 pre-push。
- package digest：`sha256:0ab9bee59a2f151f129841d03b8e40e915a4804e573310f806fefbadb8709f32`。
- instruction digest：`sha256:3039aeda829abc6b0577e6a5c68e0d8ac978d5c02eb3e81738a8f1b592e53575`。
- Codex Hook definition digest：`sha256:b17ccf006df0b3c983b121614e3f5ea6ee732d3f050c92ea26a3d62514245188`。
- 上游 `sourceCommit=working-copy:0.13.0-candidate` 原字段保持不变；精确 Git 来源由上述固定提交单独证明，不改写 ownership 冒充不同来源。
- 原字节备份：`meituan-harness-backup-20261007-A46QNa`，位于本机用户缓存目录；57 个 Harness/协作文件已复制校验，132 个受保护源码/计划文件和既有 Git HEAD 保持不变。备份未读取认证文件、历史 raw、归档或实际采集数据。
- 安装器回退载体：`.claude/.harness-lite.rollback-mqCLqQ/harness-lite`；其中旧 runtime 与升级前备份字节和权限完全一致。2026-10-08 重构时它随官方 uninstall 移除（见下一节），内容仍在备份中。
- current leaf / stage 仍为 `P23-fresh-listener-window-single-p0-attempt` / `stage-04s-continuation-single-live-p0`；唯一 current leaf 和原计划未移动或改写。
- `docs/harness/authorization.json` 初始化为 `authorized=false`，并加入本地 Git 排除项；本次升级不是 P23 执行授权，两个采集 latch 继续关闭。

### Devin 适配与证据上限

`.devin/hooks.v1.json` 和 `.devin/hooks/harness-lite.cjs` 是项目自有的边界适配，不属于上游 20 文件 runtime。它只在 SessionStart/UserPromptSubmit 中只读投影新版上下文，并在 shell PreToolUse 保留 push 停点；不签发执行或 push 授权，不生成 Codex 观测账，不配置 Stop 自动续跑，不保存 prompt、transcript 或凭据。

适配配置及隔离 fixture 只证明配置、wire 和行为分支。Codex installed/configured 已校验；真实 Codex trust/observed、真实 Devin Hook loaded/observed 和宿主 effective 均未验收。当时会话工作根是爬虫父目录；2026-10-08 重构后仓库根就是工作根（见下一节），仍需在仓库根新开 Devin 会话并检查 `/hooks`，不能把对子进程的直接调用写成真实宿主触发。

### 本次直接验证

- 真实目标只读预检：`READY / official-07 / written=0 / differences=[]`；随后按明确授权完成 `INSTALLED`，runtime self-verify 与 installation anchor 校验通过。
- 隔离 0.7 专用试升级与注入故障回退：通过；计划、leaf/stage、用户指令前缀和模拟业务文件保持不变。
- Devin 适配：6/6 单测通过，覆盖只读上下文、Devin turn 字段映射（合成输入）、普通命令不拦截、push 默认拒绝、缺失 runtime 和不同 workspace 边界；配置中的实际命令另做合成 wire 校验，未把这些调用记录为真实宿主事件。
- `autocapture`：154/154；`parser_candidate`：41/41；`collection_adapter`：58/58；`collection_core`：27/27，合计 280 项离线单测通过。
- strict verifier：`AUTOCAPTURE_STRICT_VERIFY_PASS`，16 files / 15 manifest entries。
- 保留上游限制：本机安装/历史指令选测为 10/13；历史 0.9/0.10 载体固定 Hook 摘要与本机生成值不一致，CLI 大段 JSON 输出会因提前退出被截断。本次真实升级不依赖该大段 JSON，并另行验证安装元数据；不把这些选测写成全量通过。
- 没有启动真实采集、网络/UI、系统代理或 CA/keychain 动作，没有 commit、push 或发布。业务来源资格和真实运行结论不因本次升级而提升。

## 2026-10-08 仓库根重构收据

用户在项目线程明确要求：重构仓库结构，把 v3 作为实际产品 main；Harness 安装在仓库根而不是子目录；要把项目形状适配成 Harness 0.13，而不只是 Devin。下面是实际执行的结果。

### 结构变化

- 重构前：`/Users/yoyi/爬虫` 不是 Git 仓库。产品在子目录 `meituan-collection-agent-owned-v3/`（branch `codex/project-rebuild-20260811`，HEAD `19634a15a212d10be45bf0c2c79afe88c0d0f925`，无 remote），旁边并列 100 个旧条目和 3 个其它条目。
- 重构后：`/Users/yoyi/爬虫` 就是仓库根，branch 和 HEAD 不变，Git 历史没有改写，没有 commit；未提交的工作保持未提交。v3 的 16 个顶层条目（`.codex .devin .git .gitignore AGENTS.md CLAUDE.md MIGRATION_MANIFEST.md README.md autocapture collection_adapter collection_core contracts docs historical_assets parser_candidate tmp`）原样提升到根，`.claude/` 由官方安装器重新创建。
- 100 个旧并列条目用同卷重命名原样移入 `_archive/root-legacy-20261008/`：38 个 dispatch 目录、51 个 Stage 2 成果目录、旧 `meituan-collection-agent-owned-v2` 仓库和 10 份 handoff。4278 个文件移动前后的 SHA-256、大小和权限一致（清单 SHA-256 `0479b25e184d67076e2b2f8ce510b78d764a28b779dd0328e767ed98b5041988`）。
- 不属于本产品的两项没有移动：`adaptive-harness-python-test-inventory-001/`（外部仓库的 Git worktree，搬动会破坏它的 worktree 登记）和 `ai-browser-crawling-platform-requirements.md`。它们只被本地 `.git/info/exclude` 忽略。
- `.gitignore` 新增 `/_archive/`，本地 `.git/info/exclude` 有同样的兜底。移动记录、校验和与恢复脚本在 `_archive/root-legacy-20261008.receipt/`：`move-journal.json` SHA-256 `3300f479950bc86da8804f9ac8a48d34b59a2aa35cd19726388e7734444b685b`，`files.sha256` SHA-256 `ad8dcbe64f36f4f4b125fd3cb50dddd3fed4ef4adb162a45f7ab42c773e78250`。
- 旧路径到新路径的映射见 `docs/archive-boundary.md`。

### Harness Lite 0.13.0 在仓库根重新安装

installation anchor 绑定安装路径，目录不能直接 `mv`，所以走官方路径：

1. 在旧路径运行官方 uninstall：`UNINSTALLED`。只移除 36 个 Harness 自有文件（21 个 runtime 文件含 `ownership.json`、14 个 0.7 回退载体文件、1 个 installation anchor），以及 `AGENTS.md`、`CLAUDE.md` 中的受管块和 `.codex/hooks.json` 中的 Hook 组；其它文件零变化。
2. 移动目录（见上）。
3. 在仓库根用同一固定源码（`v0.13.0`，`aac6bd5fe721aa126cf6d9203e5d96d2db540913`）和同一 project profile 重新安装：`INSTALLED`，20 个受管文件，anchor `targetCanonical=/Users/yoyi/爬虫`，anchor digest `sha256:ebb63498bc5d83e1a664b55723fc11f50696f07719513f08592f32428173242a`。

- package digest、instruction digest 和 Hook definition digest 与 2026-10-07 升级收据完全一致。
- 2026-10-07 升级留下的回退载体随官方 uninstall 移除，新安装没有 rollback carrier；旧 runtime 仍在两份备份里。
- 官方 uninstall/install 的文本级 Hook 合并在 `.codex/hooks.json` 里留下 4 个只含空格的行，使 `git diff --check` 失败。已整理成标准缩进：JSON 解析结果与重构前逐项相同，与 HEAD 的差异只剩 4 行 `command`。
- `AGENTS.md` 的 Harness 受管块字节不变，但官方重新安装把它放到了文件末尾（原来在中间）。
- Hook 命令里的 node 路径是安装时的真实路径 `/opt/homebrew/Cellar/node/23.11.0/bin/node`，`.devin/hooks.v1.json` 同。用 Homebrew 升级 node 后该路径会失效，需要用官方安装器刷新 Hook 命令，并同步改 Devin 适配。

### 项目形状适配到 Harness 0.13

- `docs/harness/plan.md` 新增 REQUIREMENT-BASELINE 块：确认来源是用户 2026-10-08 的明确要求，`hl status` 显示 `需求基线：current`。块内沿用的产品目标是 2026-08 既有计划的原文，本次没有重新确认其语义。
- 当前 leaf `P23-fresh-listener-window-single-p0-attempt` 和排队中的 `P24-stage-acceptance`，验收字段由编号的“完成条件”改成 0.13 读取的“完成标准：”单行列表（P23 为 6 条，P24 为 5 条，措辞与原文一致）。0.13 只读取这种写法，原来的写法会被判为没有完成标准。
- 两个 leaf 里折行的“目标”“来源收据”“证据”“产品”和 P24 折行的“不许动”条目合并成单行，否则 `hl status` 只显示第一行（P23 的证据曾在“不能把未接通的”处截断）。两处改动都只动换行和列表标记，去掉空白后的全文与原文一致；P23、P24 和 Stage 04S 的范围、语义和 latch 都未变。
- 新增 `docs/harness/checks.json`：6 个按路径选测的 task 检查、1 个 quick 检查和 7 个 full 检查，对应 README 的离线验证命令。`hl verify` 不再显示“无登记检查”。
- README、`AGENTS.md`（只改项目部分）、`docs/archive-boundary.md`、`docs/history/original-carriers.md` 更新为新布局；Harness 受管块没有手工改动。
- Devin 适配不变：`$DEVIN_PROJECT_DIR` 现在就是仓库根。

### 备份与回退

- 重构前 v3 的 APFS 克隆：`/Users/yoyi/Library/Caches/meituan-restructure-backup-20261008/v3-before`（670 个文件，清单 SHA-256 `1fe78c732f0f62f39229f66eccc5a5887c72237b590c4d97e3f8cc5b1d626e82`）。2026-10-07 的升级前备份 `meituan-harness-backup-20261007-A46QNa` 在同一缓存目录。两者都可能被系统清理，需要长期保留请复制走。
- 只把旧条目移回仓库根：`_archive/root-legacy-20261008.receipt/restore-neighbors.py`（默认只预检；已在沙箱上测试，并在真实布局上预检通过）。整体回退到重构前的步骤见同目录 `README.md`，该路径没有演练过。

### 直接验证

- 官方 uninstall 前后相比，只少了上述 36 个 Harness 自有文件，另有 `.codex/hooks.json`、`AGENTS.md`、`CLAUDE.md` 三个文件中的受管内容被移除；目录提升后，树与 uninstall 后的 v3 逐文件一致（`.git/index` 和 `.git/info/exclude` 除外）。
- 现状与重构前备份逐文件比较：业务源码、合同、`historical_assets/` 和 `docs/history/` 字节不变，权限不变。变化只有 Harness 安装文件（`ownership.json`、anchor、已移除的回退载体）、本节列出的文档和 `.gitignore`、`docs/harness/` 下新增的 `checks.json` 与 `verify.jsonl`、`.codex/hooks.json` 的空白整理，以及 Git 索引和本地排除。`docs/history/` 中只有 `original-carriers.md` 增加了位置说明。`historical-assets-tree.sha256` 的 269 个文件仍全部匹配。
- `hl status`：`healthy`；官方 uninstall 预检（只读）：`READY`。
- `hl verify --profile full --run`：7 项登记检查全部通过。包括 280 项离线单测（autocapture 154、parser_candidate 41、collection_adapter 58、collection_core 27）、strict verifier `AUTOCAPTURE_STRICT_VERIFY_PASS`（16 files / 15 manifest entries）、Devin 适配 6/6 和 `git diff --check`。运行记录在 `docs/harness/verify.jsonl`。另在系统 Python 3.9.6 上跑过四组单测和 strict verifier，也通过。
- `authorization.json` 仍为 `authorized=false`（权限 0600，被本地 Git 排除），两个采集 latch 仍关闭。没有真实采集、网络/UI、系统代理或 CA/keychain 动作，没有 commit、push 或发布。
- 未验证：真实宿主的 Hook trust/observed/effective（需要在仓库根新开会话后用 `/hooks` 检查）；plan-review 仍为 missing；代码图谱不可用（140 个未提交代码文件未进入图谱）。

## 2026-08-11 初始迁移直接验证（历史）

- `autocapture`：154/154 通过；
- strict verifier：`AUTOCAPTURE_STRICT_VERIFY_PASS`，16 files / 15 manifest entries；
- `parser_candidate`：41/41 通过；
- Harness Lite Core：83/83 通过，selfcheck 通过；
- raw/archive/legacy-control 负向路径检查：通过；
- symlink 检查：0；
- 初始 commit 后 working tree：clean；
- 没有真实网络、微信/浏览器 UI、系统代理、CA、keychain、管理员配置或 raw 正文读取。

## 直接带入文件

| path | mode | bytes | sha256 |
| --- | ---: | ---: | --- |
| `autocapture/__init__.py` | `0644` | 68 | `95c974a1b5b0171a6029bdb30c4d4e65c3d28846bfabaeb6a1f8c8325cbcdd24` |
| `autocapture/addon.py` | `0644` | 12906 | `bdf2e5a77b84f277dae0d0c28894463d6f151672506805698b2f74a8f7c0a74e` |
| `autocapture/build-manifest.json` | `0644` | 2584 | `191e41a534f354fc7b9e1229512251b3ab47f965b57d042eae1dd8051c7d7315` |
| `autocapture/lease.py` | `0644` | 5849 | `a13d4e92e963e190e46f567fc29d9fd3f3be18d072f40dd762d0fa89cf86f63d` |
| `autocapture/policy.py` | `0644` | 10760 | `7e2f2206a0d1e23780eb5ede20dc55bb1081f37c1253b69030a28e8545604e44` |
| `autocapture/publisher.py` | `0644` | 26593 | `dd3d318053882df14e961508d7d05f54eee1fe841a9c5d3ad4a12543cf5bf32c` |
| `autocapture/shape.py` | `0644` | 32664 | `1b987f0349608ea08ed92ff22914c9810cfd233b0f79fb8456ef61507b689e75` |
| `autocapture/tests/__init__.py` | `0644` | 67 | `0a18cd520a066693c3786c2744334489e00370b05f4c40ef14f09be30436a5a8` |
| `autocapture/tests/fakes.py` | `0644` | 9152 | `444be0f5d6a930898428c0e518be1683550038c8756ecf8273e1b5a33ed96658` |
| `autocapture/tests/test_addon.py` | `0644` | 29320 | `8f07d5e517ead1ec4dfe25447cdd140ec875d9ead6514806fe598fdef7b75f06` |
| `autocapture/tests/test_policy_and_lease.py` | `0644` | 17988 | `187178bf797bdcab2d99db59ffa18b8e83189b9bea929454fbdd111f019a79f3` |
| `autocapture/tests/test_publisher.py` | `0644` | 25252 | `c8d9e966d1b68f664c502fa81905d8b1d06075c69d93bf246a4a5ffad26d6151` |
| `autocapture/tests/test_shape.py` | `0644` | 19886 | `43db307d32d8b569b87f4cf39514877cdac4821831c9b88d6f0b04c53f8854e4` |
| `autocapture/tests/test_verifier.py` | `0644` | 52661 | `1e8e23ef3715f4e09cd5cfe4542d37be2803a163b02347274e0c443591ee8af6` |
| `autocapture/tools/verify_autocapture_build.py` | `0644` | 134676 | `901a55b3b74247abd9a4ee4917d687e258cac0a69e7ad2d354070e38e0d9de3a` |
| `contracts/README.md` | `0644` | 5410 | `848251880a0f1e16393321bbe8e890bbadc6f042deeef37912627f3aea415422` |
| `contracts/schemas/adapter-checkpoint.schema.json` | `0644` | 8524 | `57c0ca033699fcce094c78d3e54a5eb29e625479464d56ef6e9b0cf14c67f1ea` |
| `contracts/schemas/business-record-v2.schema.json` | `0644` | 3908 | `60fab61beb5afde53b26110de72f21ab4afd47361244643a6fafbff3caa81190` |
| `contracts/schemas/capability-ledger.schema.json` | `0644` | 26352 | `526ed8a5a8ab910859433e2db974bad38699f5f832b8550297e68741fcc42e8a` |
| `contracts/schemas/coverage-receipt.schema.json` | `0644` | 3376 | `5c7c8d3e81356da475312ba139ba8543cea056a40ac14e2389df2781397740c1` |
| `contracts/schemas/error-status-code.schema.json` | `0644` | 2819 | `8c2898e7f9e3054c46ab40dba097c26c48618da88d9e736f1dc33c4224d4d0af` |
| `contracts/schemas/evidence-manifest.schema.json` | `0644` | 8237 | `1de4af93a0d8d658dc632a19baf2962fa7497ba27a69f4a4c3e2af6410cb8142` |
| `contracts/schemas/field-observation-v2.schema.json` | `0644` | 13657 | `124b3bc974202c5d188f8088f82db3b3bcbfb3191effc55dc4b62d9cdea264f6` |
| `contracts/schemas/observation-batch.schema.json` | `0644` | 5395 | `8c7fe1bcf9dd1033bf38bda40dffccea39d7ee03c2855b9694995e912eec8661` |
| `contracts/schemas/observation-envelope.schema.json` | `0644` | 4088 | `e4c328b1a743433aa8e5417119ac54e47ce9730cbe5bac02333bc519e68f95e9` |
| `contracts/schemas/provider-contract.schema.json` | `0644` | 6516 | `cc2694b093bda9a3275d52b7577ce2d2650113a8145ac28e5b5f6edcc774d9e8` |
| `contracts/schemas/provider-qualification-summary.schema.json` | `0644` | 8469 | `65f921c550cfde4601112429c786ab6d058cbdfb79bbc3bb8cb058b041e6a880` |
| `contracts/schemas/provider-qualification.schema.json` | `0644` | 16223 | `fd83d4b166166550e27c79c7afd5a096e02ac1a36352587dd0eabe514a300474` |
| `contracts/schemas/source-integrity-receipt.schema.json` | `0644` | 8525 | `e37f270ccfdba9b6cd505b2e5a0a0b6ced6238b9542e0e996d639174af87cdb1` |
| `contracts/schemas/value-free-sensitive-stop.schema.json` | `0644` | 2644 | `9b3c704565353d681aa18d591c6896bf347326779b2b8a9a0e869546407e702d` |
| `docs/design/autocapture-shape-discovery-v1.md` | `0644` | 16927 | `6747f44a62113461b727d29687c4644177f1a511cf191ba791b00602308147d6` |
| `parser_candidate/__init__.py` | `0644` | 1259 | `6c0a1bc118d975b42e2429ca1f89bb4cf2f41c3c47816243f31b7bb00e607383` |
| `parser_candidate/capture_contract.py` | `0644` | 9690 | `dfe27ab16cd47b87e743267f174f8578732c01975c1045a61b8bb771813368a1` |
| `parser_candidate/envelope.py` | `0644` | 4716 | `68f976d170be70bac501d03d24645bba1bcbd3b40b001c076ededc9b4b62ce17` |
| `parser_candidate/fixtures/h34/manifest.json` | `0644` | 6947 | `2cc424cb853d2c6463b4867744b78b69d9df92841bcb7b28ef414e10e4559103` |
| `parser_candidate/fixtures/h34/read_01/events/event_01.json` | `0644` | 106959 | `79a2f484769f6f29b230ae0b301545f02b2d4261754fae6b0a4acfb91d70869e` |
| `parser_candidate/fixtures/h34/read_01/events/event_02.json` | `0644` | 767668 | `2a5bf58e05d5d517a5749ca29b9c8ace3f75c749006248ffcd91b671e6433705` |
| `parser_candidate/fixtures/h34/read_02/events/event_01.json` | `0644` | 79427 | `379dd69213baa5981f5c6b85fe9e84caffc4af42da1214cbdfb3ae356ccb05a2` |
| `parser_candidate/fixtures/h34/read_02/events/event_02.json` | `0644` | 677449 | `c80118fb6e959bade17ba733e02a6b4eda2b779af8c93a13c3ab2aeffee5153e` |
| `parser_candidate/fixtures/h34/read_03/events/event_01.json` | `0644` | 79427 | `c662b12388b6c0c1a4c072402002613ee5aef15662359b916ac0bb20a34608f4` |
| `parser_candidate/fixtures/h34/read_03/events/event_02.json` | `0644` | 679917 | `638b645453d17b3f6caeeea0d14ef0d72094aab5a3e09e84d77d6206c9183b90` |
| `parser_candidate/fixtures/h34/read_03/events/event_03.json` | `0644` | 79427 | `3619b5aa132cb0e3f5991c2f0bbe928766c46d704f44b2ad57413a366349b9ee` |
| `parser_candidate/fixtures/h34/read_03/events/event_04.json` | `0644` | 679917 | `4f1d0deb1517c09e13cdc4116d33d318ecb1bf7d570a0b1387d172bc4420ff0f` |
| `parser_candidate/parser.py` | `0644` | 16959 | `fe720b2f07af3825833b708c1dd1a8656ce1490677f93969d2fe95d193d27a5b` |
| `parser_candidate/profiles.py` | `0644` | 8027 | `66a95f1bbd90fde73a69e11df3d58985b93294aaae0b553a89700c8756cb9c00` |
| `parser_candidate/registry.py` | `0644` | 3421 | `34d272a51ab871745e20aa8349e61b85c1b9442cd85fda9254f3774196f54175` |
| `parser_candidate/tests/__init__.py` | `0644` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `parser_candidate/tests/test_capture_contract.py` | `0644` | 13847 | `9703cb4b7ed45ff93fce014a1503d890c094e496e39a331a08851102b523f0c0` |
| `parser_candidate/tests/test_food_profile.py` | `0644` | 2460 | `0bab83889f9239cea89acc2bfbb8878fd7719cc3095ff8051a4c11ab49304cf8` |
| `parser_candidate/tests/test_h34_sanitized_fixtures.py` | `0644` | 17793 | `63f6aab71e8cbdee301c46f3d2e93b4557a1f526e51db00ffd4fb335fa9237e4` |
| `parser_candidate/tests/test_parser.py` | `0644` | 16298 | `21433bcb33b3ca313b25c4f21f98bcea1143ac190256ab8a76422d344534f91c` |
| `parser_candidate/tests/test_profiles.py` | `0644` | 5631 | `09f3bd383acbe452dcf12bb13e47274e4b84f1d61dd6ea1bbdf44dc1a9aae34d` |
