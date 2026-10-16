# Meituan Collection Agent

2026-10-16 当前：用户确认数据足够、采集已停。控制根已 stop、intercept_cleared=true、宿主退出、cleanup=INCOMPLETE 且不可再 start；两 latch=CLOSED。有效商品数据在 `runtime-output/p29_pages_313d083fff964939b7d1edc1ccb1bdd7`：去重后 1220 个商品、1318 个规格（1156 个规格有 12–14 位编号、161 个空），412 个商品有带编号分享链接，44 个分类声明 1039 个商品、14 个分类还有下一页。“把店铺链接交给程序后自动打开并抓取”仍未实现。P25–P28 已 accepted 并退场，P29 为当前 leaf，P29/P31 与产品整体仍 incomplete。计划权威以 [docs/harness/plan.md](docs/harness/plan.md) 顶部为准；以下为历史时点。

2026-10-14（历史）：用户确认地址页已打开，窗口33的门店详情请求返回HTTP 200且响应完成，0传输失败；此前失败根因仍未知。查明详情路由原先只转发、未复制正文，现已补公开详情副本独立保存：只选已观察的POST /weapp/shop/v1/poi/detail，不复制详情请求正文，不读取私人分支值，不推断店铺关联或混入商品表。569项适配层经两套解释器互补通过，核心58项通过。窗口33已完整清理，窗口34于17:49:19 UTC接替，PID60732、网络PID46630，ACTIVE、接受副本且详情副本功能enabled，两latch=OPEN，无截止时间，保持开启。窗口34已于17:53:08 UTC保存并核对1份详情公开副本（69个标量条目），当前所选店名一致，地址、公开电话、配送时段、服务说明、门店标签和公告均非空；HTTP 200且根code为ZERO，传输失败/跳过/丢弃均0，接收继续开启。见 docs/harness/reports/P29-window34-detail-copy-direct-check.json；旧231行及55行结果保留，分类无需重刷。无自动重试或系统配置修改，P29/P31及产品仍incomplete。见[当前结果及控制](docs/harness/reports/P29-window30-export-and-window31-recovery-2026-10-14.md)。以下为历史时点。

2026-10-14 当前：用户明确要求保持接收器开启，已取消本轮两分钟时限。窗口30于14:24:02 UTC启动，接收器71734持续ACTIVE、两latch=OPEN，无会话截止时间；不因等待回复或聊天结束主动停止，不自动重试。启动时新增商品0，真实入流仍待核对。39项相关用例互补通过，见[持续接收及控制根](docs/harness/reports/P29-continuous-receiver-window30-2026-10-14.md)。以下两分钟试采均为历史状态。

2026-10-14 当前：用户再次“继续采集”后完成窗口29两分钟试采，新增商品0；6个上游连接建立成功，目标TLS hello和HTTP输入均0，副本解析无失败。已完整关闭、两latch=CLOSED，当前等待这一次页面重进的事实反馈，不自动重试。见[本轮结果](docs/harness/reports/P29-window29-trial-result-2026-10-14.md)。以下为此前状态。

2026-10-14 最新：已修复转发引擎启动问题，完成窗口28两分钟试采。用户反馈页面正常，但目标商品响应与新增数据均为0；接收器退出、锁清理、拦截解除，两latch=CLOSED。已补回连接/TLS计数，最终38项相关用例经两套解释器互补通过，尚待下一轮真实入流验证。窗口26准备中底层库意外更新Redirector应用，已披露并补上只复用已有组件的保护；未修改系统代理、CA或keychain。见[本轮结果与修复](docs/harness/reports/P29-forwarding-startup-and-window28-2026-10-14.md)。P29/P31和产品整体仍incomplete，旧窗口不重开；以下为历史记录。

2026-10-13 当前采集入口已退役：为落实用户“只拿副本”的要求，已删除旧PID代理启动路径。旧准备/serve命令及控制器start现在拒绝，返回`P29_COPY_SOURCE_UNAVAILABLE`；尚未接通真实旁路副本来源，不能继续真实采集。已有结果的离线解析/导出和旧实例status/stop仍保留。下文涉及代理启动的步骤仅为历史说明，不再可执行；不应重装组件或换参数绕回旧方案。见[改动与未完成项](docs/harness/reports/P29-copy-only-entry-retirement.md)。

2026-10-12 后续实施：用户在排除图片后明确“继续做后续工作”。已实现 P32 的独立本地结果入口：`python3 -B -m collection_adapter.p32_result_entry` 无参数定位当前已交付表格、字段说明和缺失清单，核对 manifest 合同及文件状态，失败给固定原因和恢复方法。7 项合成测试通过，当前 11 个结果文件的目录检查通过；未读取业务表正文或重做来源核对。此切片只依赖已交付文件，不要求先证明全店收齐；P29/P31 资格、P32 真实采集入口和整体验收均未提升。使用说明：`docs/harness/p32-local-results.md`；证据：`docs/harness/reports/P32-local-entry-validation.json`。

这是沿微信小程序真实网络响应抓包路线开发的商品采集项目，目标是尽量收齐目标店铺的商品与公开业务字段。P26 已交付首份受控真实基础表，P27 已核对实际文件和用户页面的有限样本：39 条分类记录对应31个不同商品，覆盖为 PARTIAL。采集已关闭，全店和完整字段扩充仍未完成，产品整体 incomplete。已有实现包括：

- `autocapture/`：默认 `DISARMED` 的离线安全基础；
- `parser_candidate/`：隔离候选，保留合成路径及依据 P26 当次事实建立的显式 v2，尚未接入正式 Provider；
- `collection_adapter/`：严格 Adapter 合同、合成离线入口、准备与被动 bridge，以及 P26 受控准确 PID 宿主；
- `collection_core/`：同观察 P0 核心记录、P1 业务字段组装与无覆盖 Publisher；
- `contracts/`：来源资格、观察、字段、证据和停止行为的通用闭合合同。

`historical_assets/` 和 `docs/history/` 是非活跃历史区：前者按原字节保留关键工程资产，后者记录完整路线谱系、终态和禁止重复项。它们不加入当前 import、测试或运行入口。

## 仓库结构

自 2026-10-08 起，`/Users/yoyi/爬虫` 本身就是产品仓库根：原 `meituan-collection-agent-owned-v3` 的 Git 历史、产品目录、合同、文档和 Harness 控制面已提升为仓库根，Harness Lite 0.13.0 安装在这里，不再位于子目录。

`_archive/` 保存旧 v2 仓库、历史 stage/dispatch 目录和 Stage 2 成果的原字节归档。它在工作目录内但被 `.gitignore` 排除，不是产品代码，也不是运行或授权依赖。目录映射、迁移收据和回退方法见 [docs/archive-boundary.md](docs/archive-boundary.md) 与 [MIGRATION_MANIFEST.md](MIGRATION_MANIFEST.md)。

## 迁移与协作权威

本项目的日常协作控制面当前为 **Harness Lite 0.13.0（working-copy candidate），project profile**。运行时为未提交的工作区副本（`.claude/harness-lite/ownership.json` 记为 `0.13.0-candidate`），从官方 0.7.0 升级为 20 文件 runtime；受管 instruction、Codex Hook 配置和 installation anchor 已更新。注：此前文稿曾引用标签 `v0.13.0` 与提交 `aac6bd5…`，但二者在本仓库并不存在、运行时文件尚未提交——以 `ownership.json` 的 candidate 记录为准。业务源码、项目资格、升级时的 P23 leaf / Stage 04S 和采集 latch 未因升级而改变。当前产品计划以 docs/harness/plan.md 为准。

历史项目、旧 Harness、旧任务包和 `docs/history/` 都只作为证据，不会覆盖 Lite 0.13.0，也不会自动恢复成授权、current leaf 或执行能力。完整权威链、备份、摘要和证据上限见 [MIGRATION_MANIFEST.md](MIGRATION_MANIFEST.md)。

Devin 的项目级适配位于 `.devin/hooks.v1.json`：只读注入新版上下文，保留本项目的 push 停点；它不生成 Codex 宿主观测、执行授权或 Stop 自动续跑。配置和隔离测试通过不等于真实宿主已触发。Devin 需要以仓库根为工作根启动新会话，使用 `/hooks` 检查加载来源。

## 当前状态

```text
SOURCE_QUALIFICATION=NO_QUALIFIED_SOURCE
PROVIDER_QUALIFIED_FOR_BUILD=false
LIVE_CAPTURE_LATCH=CLOSED
EXECUTION_LATCH=CLOSED
PARSER_CANDIDATE=ISOLATED_CANDIDATE
P02_FORMAL_PARSER=NOT_ENTERED
```

这些状态保留正式来源和 Parser/Provider 的资格边界。P26 在具体授权下取得过正确的同观察基础记录，P27 完成有限核对；该事实没有提升正式资格，当前两 latch 仍为 CLOSED。历史 H36–H38 和旧停止结论各自保留，不恢复为当前来源或运行能力。

## 后续开发计划（2026-10-08）

2026-10-11 解析更新：已补同响应附加价格数字、说明文本及缺失状态解析，通过 `--price-evidence` 发布候选/清单 v2；窗口 19 的新版清单仍为 233 行、155 商品、200 SKU、19 分类。旧导出保留，178 行分类数据的币种/金额单位及业务含义仍保留未确认。见[解析实现](docs/harness/reports/P29-category-price-parser-implementation.md)与[直接验证](docs/harness/reports/P29-category-price-parser-direct-check.json)。

2026-10-12 优惠规则解析更新：已补商品/SKU 数量与折扣配对、阶梯包装数量/费用和带索引优惠文本，`--price-rules` 发布 v3；新版清单仍为 233 行、155 商品、200 SKU、19 分类。178 行分类数据完成自身来源核对，初始 55 行规则明确未重解析；币种、单位和业务算法仍未确认。见[规则解析实现](docs/harness/reports/P29-price-rules-implementation.md)与[独立验证](docs/harness/reports/P29-price-rules-direct-check.json)。

2026-10-12 初始行补齐：已将初始 55 行自身附加价格和优惠接入 `--initial-price-rules` 库存 v4，CSV 列结构沿用 v3；清单仍为 233 行，分类 178 行不变。102 次相关测试及独立来源核对通过，旧 v1–v3 重算字节一致。用途为通用 CSV 导入，目标系统适配尚未验证。见[初始行实现](docs/harness/reports/P29-initial-price-implementation.md)与[独立检查](docs/harness/reports/P29-initial-price-direct-check.json)。

2026-10-12 非价格字段交付：已新增 49 项商品/SKU/门店标量及带索引的属性选项解析，交付 233 行商品表、1 行门店表、逐列字段说明和状态覆盖清单。原 v4 字段全部保留；79 次相关测试执行和自身来源逐项核对通过。当前仍有业务语义和未全面适配的可见字段，P31 整体 incomplete；无新采集或目标系统实际导入验收。 见[字段实现报告](docs/harness/reports/P31-public-fields-implementation.md)与[导入字段说明](docs/harness/p31-field-import-guide.md)。

2026-10-12 后续字段补漏：新增 37 条标量路径和 15 条带索引的标签路径，商品 233 行/门店 1 行及旧字段全部保留；49 次相关测试和独立来源核对通过。修复七文件导出的晚期失败清理。用户明确无需目标系统导入验证，该项不再作为当前任务缺口或停点；P31 其它语义/范围缺口保留。证据：`docs/harness/reports/P31-additional-fields-direct-check.json`。 新入口：`python3 -B -m collection_adapter.p31_additional_export`；[补漏报告](docs/harness/reports/P31-additional-fields-implementation.md)。

2026-10-12 剩余公开字段处置：新增 6 条标量、1 条分享渠道索引路径，并明确记录 6 条来源 null，商品 233 行和门店 1 行的旧字段保留；37 次相关测试与独立来源核对通过。用户已确认只要公开信息，个人优惠排除；两条券引用的账号关联用途仍未知，暂不导出。已有公开投影的 PRODUCT/SKU/poi_info 路径均有明确处置，P31 业务语义和完整资格仍 incomplete。证据：`docs/harness/reports/P31-remaining-fields-direct-check.json`。 此前 v3 入口：`python3 -B -m collection_adapter.p31_remaining_export`；[本轮说明](docs/harness/reports/P31-remaining-fields-implementation.md)。

2026-10-12 最新范围：用户明确“图片跳过”。图片下载、保存、图片标识及引用导出均移出当前交付范围，不再计入未完成项或验收缺口；不启动图片合同或解析实现。已有公开标签文字和业务结果保留。当前价格和费用均已确认为人民币元；其余语义、来源资格及全店覆盖结论不因本次范围调整而改变。

2026-10-12 用户已确认当前价格和费用均为人民币元：新版商品 233 行均标注 CNY/YUAN，初始 55 行原依据保留，178 行补明确用户确认依据；门店费用一并标注。金额及其它旧业务值不变，确认前状态另存；确认仅绑定当前既有结果，不能自动套用未来输入。65 次相关测试和逐行核对通过，旧 v6 十个数据文件重算一致。当前币种/元单位不再作为待用户确认项；券/位置用途、枚举和平台终止仍缺证，P29/P31 不整体 accepted，P32 未启动。证据：`docs/harness/reports/P31-confirmed-units-direct-check.json`；说明：`docs/harness/reports/P31-confirmed-units-implementation.md`。 当前入口：`python3 -B -m collection_adapter.p31_confirmed_units_export`。

用户已确认以真实抓包结果推进，并尽量收齐目标店铺的商品和公开业务字段。后续按以下顺序实施：

1. Stage 04T：开发者完成接入准备和诊断，取得第一份可核对的真实商品表，并盘点可得字段。
2. Stage 05：正确关联商品、SKU 和价格，处理分类、分页、去重与全店覆盖。
3. Stage 06：补齐六类可得业务字段，提供易读导出、覆盖说明和简化入口，并进行真实产品验收。

[总计划](docs/harness/plan.md)、[字段范围与覆盖口径](docs/harness/field-coverage-plan.md)和 P25–P33 已写入任务安排。接口识别、字段映射和运行参数由开发者负责，用户不需编写私有配置。

P25–P28及Stage 04T已accepted并退场。窗口19本轮声明范围已全部覆盖并交付最终233行清单/155商品/200SKU/19分类。初始响应155有序成员+22折叠成员共177个分类商品关系，与实际正文集合完全相等：有序缺0、折叠缺0、额外未声明成员0；5类展开入口均已操作并有自身响应证明。本轮19份v4分类响应、scope拒绝0，147组请求/响应成员匹配，输入253行按SKU/分类保留最新整行去重20行；55初始完整记录+178分类候选，不跨观察补价、不提升候选资格。四组实际输出合同/JSON/CSV/manifest/计数/来源/权限核对通过。有限已声明引用集合耗尽作为本轮停止依据，平台分页终止、未声明或未来商品不作断言。2026-10-11T17:03:14.350370+00:00stop关闭，宿主2974退出、锁消失、stream0、拦截清理、cleanup=COMPLETE、两latch=CLOSED、固定CA保留；HTTP35完整/0失败/0未完成，TLS失败0。当前无页面任务或采集窗口；剩余为分类候选完整业务资格、币种单位及平台终止未确认，P29 active/incomplete，不accepted、不启动P30–P33。证据：docs/harness/reports/P29-window19-final-coverage-direct-check.json、docs/harness/reports/P29-window19-final-inventory-export-receipt.json。 入口与直接事实见[P29说明](docs/harness/p29-store-pages-operations.md)和[P29报告](docs/harness/reports/P29-delivery-report.md)。下列Stage 01–03示例仍为离线演示。

P25 准备命令为 `python3 -B -m collection_adapter.live_prepare --output-root <已有规范绝对0700目录> --result-name p26_first`。它只检查准备并输出闭合诊断，零尝试；当前真实规则缺失时明确报告 INCOMPLETE/UNKNOWN。可原样运行的临时目录命令、验收证据和 P26 缺口见 [P25 交付报告](docs/harness/reports/P25-delivery-report.md)，开发者参数与操作步骤见 [准备说明](docs/harness/p25-entry-operations.md)。

[当前状态](docs/current-state.md)与[总计划](docs/harness/plan.md)已同步至 P29（采集已停、两 latch=CLOSED，P25–P28 accepted、P29/P31 与产品 incomplete）。`docs/boundaries.md`、`docs/qualification-status.md` 的任务状态已按 2026-10-16 对齐；正式资格及默认能力边界仍沿用。P26 现场操作说明见 [接入步骤](docs/harness/p26-live-run-operations.md)，后续真实窗口须按新任务明确范围和新鲜输入。

## 历史成果

开始新的来源、Provider、Parser 或采集路线前，先读：

- `docs/history/README.md`：历史入口和证据等级；
- `docs/history/route-ledger.md`：各路线最强成果和实际终态；
- `docs/history/do-not-repeat.md`：已经验证过、不得无事实重做的工作；
- `docs/history/original-carriers.md`：原件、哈希和仓外全集归档。

## 离线验证

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s autocapture/tests -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -B autocapture/tools/verify_autocapture_build.py --repo-root . --strict
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s parser_candidate/tests -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s collection_adapter/tests -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s collection_core/tests -p 'test_*.py' -v
git diff --check
```

同一组检查已登记在 `docs/harness/checks.json`，也可以由 Harness 运行：`node .claude/harness-lite/bin/hl.js verify --profile full --run`；按改动文件选测用 `hl.js verify <文件路径> --run`。它们都只使用合成、脱值 fixture，不启动网络、微信或浏览器。

当前产品边界见 `docs/boundaries.md`，架构见 `docs/architecture.md`，资格状态见 `docs/qualification-status.md`。raw capture、live evidence、旧 Harness 和旧 worktree 现场只存在于仓外受控归档；关键无值报告和工程源码另有只读原字节副本，但都不是当前运行依赖或授权权威。

## Stage 01 离线演示

下面的命令只在内存中运行内置的合成 fixture，并把完整结果写到标准输出。它没有
输出路径、不会读取 fixture 文件，也不连接网络、微信或浏览器：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m collection_adapter.runner --scenario success
```

成功结果的 `source_kind` 固定为 `SYNTHETIC_OFFLINE_FIXTURE`，`readable_records` 仅展示
合成的 `store`、`product`、`price_yuan` 与 `currency`。`empty`、`format-error` 和
`cross-observation` 场景只输出闭合错误码，绝不发布部分结果。这不是真实采集、来源资格、
正式 Parser/Provider 集成或发布收据。

## Stage 02 离线结果集

下面的显式请求会使用同一个内置合成 fixture，生成一个新的本地 JSON/CSV 结果集。先准备
一个已经存在的、真实绝对路径且权限为 `0700` 的受控目录作为输出根；不要把结果名指向已有
目录，也不要把输出根设为符号链接：

```sh
mkdir -m 700 /absolute/path/to/stage02-results
PYTHONDONTWRITEBYTECODE=1 python3 -B -m collection_adapter.runner \
  --target target:offline_demo_01 \
  --adapter-id offline_fake \
  --run-ref run:stage02_cli_01 \
  --read-scope READ_STAGE02_01 \
  --observation-scope OBS_STAGE02_01 \
  --observed-at 2026-08-11T10:00:00Z \
  --output-root /absolute/path/to/stage02-results \
  --result-name stage02_cli_01 \
  --formats JSON_CSV
```

成功时会在输出根中新建 `stage02_cli_01/`，其中仅有 `records.json`、`records.csv` 和作为
完成标记的 `manifest.json`。每条记录带有店铺、商品、按元显示的价格、币种，以及 run、batch、
observation 和业务记录引用；所有字段来自同一次合成 observation。已有同名结果、无效输出根
或任一步写入失败都会以闭合错误退出，且不会覆盖或报告半成品成功。

这条命令不读取 fixture 文件，不访问网络、微信或浏览器，也不会提升真实采集、来源资格、
正式 Provider/Parser 集成、latch、发布或运行授权。它只验证本地
`SYNTHETIC_OFFLINE_FIXTURE` 的离线结果集流程。

## Stage 03 P1 业务字段离线结果集

在同样的受控 `0700` 本地输出根中，加上显式 `--p1` 可验证 Stage 03 的合成字段链路：

```sh
mkdir -m 700 /absolute/path/to/stage03-results
PYTHONDONTWRITEBYTECODE=1 python3 -B -m collection_adapter.runner \
  --p1 \
  --target target:offline_demo_01 \
  --adapter-id offline_fake \
  --run-ref run:stage03_cli_01 \
  --read-scope READ_STAGE03_01 \
  --observation-scope OBS_STAGE03_01 \
  --observed-at 2026-08-11T10:00:00Z \
  --output-root /absolute/path/to/stage03-results \
  --result-name stage03_cli_01 \
  --formats JSON_CSV
```

它在保留 P0 店铺、商品、当前元价格、币种和关联引用的同时，表达分类、SKU、原价/活动价、
优惠和配送字段。每个 P1 字段在 JSON/CSV 中都带有值或明确 presence/absence、实体和 owner
绑定、稳定来源标签及值编码；金额只对用户以元显示。缺失不补零、不推导价格或优惠，也不会跨
店铺、SKU、时间、分页或 observation 补值。manifest、CSV 和 JSON 均来自同一完整结果集，
同名目标仍会被拒绝而不会覆盖。

该 `--p1` 命令严格使用 Python 内存构造的 `SYNTHETIC_OFFLINE_FIXTURE` 与隔离的
`parser_candidate/` profile。它不读取 fixture 文件，不访问网络、微信或浏览器，不构成真实字段、
正式 Parser/Provider、来源资格、真实发布或任何 latch 的提升。

## 真实接入的现状与历史结论

现有 collection_adapter/ 包含准备入口、被动 mitmproxy callback bridge、一次性运行边界、addon 和 P26 受控宿主。准备与实际开始分开，准备不消费输入或尝试；当前真实 consumer 仅接基础 P0，扩展 P1 仍为合成路径。仓库尚未交付无需开发者准备即可完成真实全店采集的用户入口。

Stage 04 保留零尝试的 LIVE_SOURCE_ENTRY_UNAVAILABLE 结论。Stage 04R/P21 实际消耗过一次新鲜尝试，以 MITMPROXY_BRIDGE_TIMEOUT 结束；没有 P0 业务表、JSON/CSV 或 manifest。超时只说明没有形成可接受的完整输入，不能推出当时完全没有网络响应。

旧 P23/P24 后续监听安排已被 2026-10-08 新计划替代；P21 的 reader、request、lock 和输出边界仍不可复用。P26 已依据当次事实固定真实映射，累计识别22次、结果2次；资源关闭、输入锁移除、两 latch 为 CLOSED。临时 CA 文件已删除，用户手动移除曾导入的信任仍待确认；安装组件未声称已卸载。

后续由开发者按新任务完善真实商品/SKU/价格关系、分类分页及扩展字段。接口、参数、映射和诊断继续由开发者负责，用户完成必要本人页面或系统动作；范围和能力在相应任务中明确。P27 到验收退场为止，不自动启动 P28、全店或新真实窗口。
