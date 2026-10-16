# 架构

## Autocapture 离线安全基础

```text
精确策略与 endpoint selector
→ 请求/响应元数据门
→ 有界、一次性内存 lease
→ 严格 JSON 与 value-free shape
→ 敏感/未知/预算异常停止
→ 原子、无覆盖 Publisher
```

`autocapture/` 不负责取得真实来源。它只定义输入已经由外部显式提供时，怎样在最小能力面内失败关闭地分类、投影和发布无值结构。

## Parser 候选

```text
合成脱值 event
→ capture contract 与 read-scope 绑定
→ family/version profile registry
→ candidate parser
→ 同 observation 的结构化候选结果
```

`parser_candidate/` 是候选解析验证面，已由下述离线 Adapter/Core 通路调用，但未成为正式 Parser 或合格 Provider，也没有与 `autocapture/` 建立合格的真实来源链。测试 fixture 只证明离线候选行为，不证明真实来源语义。

## Stage 01 离线入口

```text
显式 target + run config
→ 注册的纯内存 fake Adapter
→ 严格同 read/observation scope 事件批次
→ parser_candidate
→ collection_core P0
→ 标准输出的可读 JSON
```

`collection_adapter/` 只接收显式传入的 opaque target 和运行配置。内置 fake 的所有
fixture 都在 Python 内存中构造；它没有网络、文件、进程、浏览器或 UI 能力。Stage 01 的
`--scenario` 分支没有输出路径或 Publisher 调用，只有在 Adapter、Parser 和 P0 均成功后才向
标准输出写入完整 JSON。该 JSON 的来源类型固定为 `SYNTHETIC_OFFLINE_FIXTURE`，因此这条
通路只验证合成输入编排，不把 `parser_candidate/` 接入正式 Provider 或真实业务发布链。

## Stage 02 P0 离线结果集

```text
显式 offline target + run/options + output intent
→ 已注册的纯内存 fake Adapter
→ parser_candidate
→ 同 observation P0 记录
→ 稳定 JSON/CSV 视图
→ 已存在的 0700 本地输出根中的独占结果目录
→ records.json、records.csv、manifest.json（完成标记）
```

这条入口只在调用者显式提供全部请求字段时启用。目标注册表不提供默认回退；未知目标、
Adapter/Parser/P0 拒绝、无效结果视图和发布异常都以稳定闭合错误结束。Publisher 只接受
非符号链接的既存绝对 `0700` 根目录，并用独占创建的结果名防止改写；它先写 JSON 与 CSV，
最后写 manifest，失败仅清理本次新建目录内的固定文件名。

结果中的店铺、商品、`price_yuan`、币种和关联引用都来自同一合成 observation。它是本地
`SYNTHETIC_OFFLINE_FIXTURE` 结果集，不连接任何真实 Provider 或 Parser，不改变来源资格、
latch 或真实发布结论。

## Stage 03 P1 合成业务字段结果集

```text
显式 offline target + --p1 + run/options + output intent
→ 已注册的纯内存 fake Adapter
→ 隔离 parser_candidate 的 synthetic P1 profile
→ 冻结的 P0 核心结果 + 同 observation P1 SKU 记录
→ 稳定 JSON/CSV P1 视图
→ 已存在的 0700 本地输出根中的独占结果目录
→ records.json、records.csv、P1 manifest.json（完成标记）
```

P1 记录始终链接既有 P0 业务记录并复用同一 run、batch、observation、时间与来源完整性引用。
分类、SKU、原价/活动价、优惠、配送和每个缺失状态都有闭合字段合同、实体/owner 绑定、稳定
来源标签及精确编码。金额内部保持分单位，只在结果视图转为元；百分比优惠使用明确的整数基点，
不从价格反推。缺失字段没有默认值、空字符串或跨实体/时间/分页补值。

`--p1` 仅选择 `synthetic_p1_productlist/v1` 的内存 fixture，仍要求调用者显式给出全部请求
字段。P1 JSON、CSV 和 manifest 共享同一行模型和无覆盖发布策略；未知目标、解析/组装/视图
拒绝或发布异常均以闭合错误结束。该链路没有真实网络、微信、浏览器、正式 Parser/Provider 或
来源资格含义，也不会改变 live/execution latch。

## Stage 04R 被动 source entry bridge

```text
用户自行加载的 mitmproxy addon future callback
→ loader 注入的严格内存 endpoint/预算/敏感/P0 projection policy
→ 进程内 bridge 汇集同观察的 FOOD 与 PRODUCTLIST 各一个事件
→ P16 read_once()（仅在当次新鲜 lease 等待时）
→ LiveP0Observation
```

P20 的 bridge 不 import/start `mitmproxy`、不接端口、不使用 socket/文件/后台轮询，也不触碰请求
正文、headers、Cookie 或 session。它在 callback 中只读取 `method`、`host`、`path` 供严格策略匹配，
将临时响应交给注入的预算、敏感和目标漂移检查及 P0 投影；完成、拒绝、重复或超时均释放引用并以
闭合码结束。P20 绑定 `TGT-HZ-XCJ-GFTJ-001` 到新的显式 `target:<token>`，并只在 P21 调用时生成
一次新的 P15 request/authority/reader，不复用旧入口、锁、H31/H34 或 candidate profile。

P20 交付时尚未加载 addon、创建 runtime lock、消费来源或发布 P0/JSON/CSV；其 receipt 记录 source
attempts 为 `0`、两个 latch 为 `CLOSED`。后来的 P21 另行消耗了一次真实尝试并超时。历史实现或
network capability 声明不代表当前已获准启动网络；当前 latch 仍为关闭，UI、代理、CA、keychain、
凭据/会话和交易边界不因计划修订改变。

P21 的 `collection_adapter/live_mitmproxy_addon.py` 是独立的 mitmproxy-compatible lifecycle
wrapper，不 import/start mitmproxy。本 addon 默认 `UNCONFIGURED`，`response(flow)` 在此状态只拒绝；
caller 必须对当前一次运行注入完整严格 policy、runtime mapping、P15 refs/时间窗、Parser registry、
P0 context factory 与 `0700` 输出根，然后人工调用 `start_once()`。此时才即时创建 request/authority，
worker 等待加载后的两个目标事件组成同一次完整观察；当前 bridge 固定要求 FOOD 与 PRODUCTLIST
各一次，不具备全店分页汇总能力。成功仅通过既有 no-clobber publisher 写完整 JSON/CSV/manifest；
失败仅产生闭合无值收据并关闭 latch。

P21 已实际消费一次新鲜运行额度并以 `MITMPROXY_BRIDGE_TIMEOUT` 停止，业务输出为零。该实例的
request、reader、authority、attempt、input lock、receipt 和输出边界都已关闭，不能重新 arm。该停止
只证明未形成可接受的完整结果，不能据此断言完全没有网络回调。旧 Stage 04S/P23/P24 已由
[新计划](harness/plan.md)取代并原文保留于 superseded/，不能自动恢复旧监听任务。

## 待实现的产品路线

后续分为真实接入与首份正确商品表、真实 SKU/价格与全店覆盖、业务字段补齐与可用交付三个阶段。
开发者准备接口规则和运行参数，用户只完成业务目标确认及必要的手动操作。先明确获准真实输入的
字段含义，再实现版本化解析；离线测试用于验证这些具体规则，真实核对才决定产品进度。

分类分页的多观察入口已在 P29 实现（`collection_adapter/p29_store_pages.py` 接收多组新鲜 FOOD/PRODUCTLIST 并各自独立发布）；多次观察只能汇总各自完整的
记录，保留各自时间和来源，不能跨观察拼凑字段，覆盖仍为 PARTIAL。真实 P1 profile、六类业务字段完整性、字段缺失原因、
全店完整性说明和易读导出仍未完成，不是已验收能力。详见 [字段范围表](harness/field-coverage-plan.md)。

P25–P28及Stage 04T已accepted。窗口19本轮声明范围已全部覆盖并交付最终233行清单/155商品/200SKU/19分类。初始响应155有序成员+22折叠成员共177个分类商品关系，与实际正文集合完全相等：有序缺0、折叠缺0、额外未声明成员0；5类展开入口均已操作并有自身响应证明。本轮19份v4分类响应、scope拒绝0，147组请求/响应成员匹配，输入253行按SKU/分类保留最新整行去重20行；55初始完整记录+178分类候选，不跨观察补价、不提升候选资格。四组实际输出合同/JSON/CSV/manifest/计数/来源/权限核对通过。有限已声明引用集合耗尽作为本轮停止依据，平台分页终止、未声明或未来商品不作断言。2026-10-11T17:03:14.350370+00:00stop关闭，宿主2974退出、锁消失、stream0、拦截清理、cleanup=COMPLETE、两latch=CLOSED、固定CA保留；HTTP35完整/0失败/0未完成，TLS失败0。当前无页面任务或采集窗口；剩余为分类候选完整业务资格、币种单位及平台终止未确认，P29 active/incomplete，不accepted、不启动P30–P33。证据：docs/harness/reports/P29-window19-final-coverage-direct-check.json、docs/harness/reports/P29-window19-final-inventory-export-receipt.json。 入口见[P29说明](harness/p29-store-pages-operations.md)，正式Parser/Provider资格不提升。

## P28 商品和 SKU 关联

`parser_candidate/p28_profile.py`注册已观察公开标量的新候选版本；`collection_core/p28.py`按同观察绑定商品、SKU、分类和各自价格。跨分类副本保留归属，名称或规格内容冲突拒绝；同名不同ID保持不同商品。SKU清单用于拒绝漏掉非最低价规格，空规格不从商品单位补齐。

P28在自己的P0内存结果中为公开来源ID生成明确类型的opaque引用，并使用新记录引用，使新嵌套合同可闭合校验；旧P0/P26文件和格式不改。`p28_result_views.py`生成SKU行和商品最低展示价，发布器从原绑定模型重新生成并比对JSON/CSV后才创建目录。未知原价、活动价、包装、可用状态和优惠含义保留未知，观察到的原数字不被命名为原价或自动套用元单位。

`collection_adapter/p28_projection_review.py`是明确命名的既有获准公开标量导出的只读入口：有界/no-follow读取、目标核对、两个事件和原时点保留、内存JSON/CSV/manifest校验，只输出有限无值诊断。它不创建运行窗口、尝试、输入锁或业务文件，也不把识别投影提升为新来源路由证明。

`p28_business_batch.py`通过`p26_identification_host`显式批量模式，接收准确PID中已确认的两条目标POST业务响应。PREPARED不读输入或计尝试，明确start后进入RESULT；先核对当前店名、两FORM公开编号及≤10秒同观察关系，再由两遍词法检查选择有界公开标量、保留数组坐标并发布P28视图。私人分支值保持不解码，URL/超长值拒绝；只保存受控公开投影，不保存原包。成功/失败/取消均关闭转发、释放原文/FORM租约与latch，准备/原始回调/合格事件/解析/发布分别计数。操作与预算见[批量说明](harness/p28-batch-operations.md)。

本次56条分类SKU记录对应32个商品、44个SKU；商品attrs选项文本实际可得但当前没有直接到SKU的链接，不能按数组顺序猜配。原价/优惠/费用/库存/配送含义留未知，响应覆盖PARTIAL，全店分页仍待后续实现。直接结果及无值盘点见[P28报告](harness/reports/P28-delivery-report.md)。

## P29 多观察与本机证书复用

`collection_adapter/p29_store_pages.py`显式接收多组新鲜完整FOOD/PRODUCTLIST，不自动UI或重放。每组先保留P28目标、FORM、同观察和完整SKU保护，再从获准数组坐标登记分类、原页标记、折叠及已加载商品引用；每组发布独立完整结果和公开投影，清理使用过的原文/FORM租约，继续等待下一组。已消费请求引用不可重用，累计字节不归零。只有PRODUCTLIST时明确等待新鲜FOOD，空页只写覆盖元数据，不造业务行或推定终止。

`collection_core/p29.py`重新验证每份完整绑定，再按店铺/SKU/分类选最后完整行去重。商品多分类关系、不同商品ID和每条自身时点/来源保留，后续未出现的SKU保留原观察、不推断当前在售；不跨观察补字段。SKU归属或来源变化拒绝，32组/40000输入行/256源分类与16MiB等预算封闭。关闭先拒绝输入并清租约，再由发布器重新生成、比对和无覆盖发布汇总JSON/CSV/manifest；先前完整观察不会被发布异常删除，范围始终PARTIAL。

按当前用户长期证书决定，`development_transport.py`将本机CA和0600注册文件保存在独立0700/Git忽略根。每窗口通过精确registry绑定复用自有CA，仍重新确认目标、当前PID、输入锁和输出边界。元数据/公开期限校验不读取或导出私钥，不代表来源就绪；关闭采集保留CA，显式用户移除才清理。正式产品在本机可复用，其它设备应各自生成及信任CA，开发私钥不随产品分发。本任务没有实施产品安装分发或提升资格。

`upstream_tls_diagnostic.py`在选定上游TLS失败时，仅把OpenSSL数值校验结果和名称比较缩减为固定状态码、种类和布尔值，关闭前写入forwarding诊断。缺失API记UNKNOWN，不读取错误文本、证书链、URL或正文，不放宽TLS验证。旧收据没有子因字段则保持原事实；无校验错误报告不能当作握手成功。

## 合同

`contracts/` 使用 closed object、固定 `schema_version` 和语义校验边界，描述资格、Provider 控制面、观察、字段、业务记录、证据和 value-free stop。JSON Schema 通过只是结构证据，不会自动提升来源资格或执行 latch。

## 历史继承，不是运行依赖

当前设计不是从零开始：CP1 提供了 FD/no-follow、预算、稳定性和原子证据经验；R2B 提供了视觉绑定、内存帧 lease 和失败关闭经验；owned-development-v1 提供了当前 15 个合同文件；H31/H34 提供了 Parser 候选的无值 shape 与合成 fixture 来源链。

这些历史源码和报告保存在 `historical_assets/` 与 `docs/history/`，但没有接入当前产品。`autocapture/` 只发布 value-free shape；`parser_candidate/` 仍是隔离候选；两者之间没有合格 Provider 合同。详细路线和终态见 `docs/history/route-ledger.md`。

P29当前增加`collection_adapter/p29_category_export.py`：从明确公开投影及对应v2匹配收据生成独立候选JSON/CSV/manifest。每行保留自身字段/时点/来源，不接入完整记录发布器，不补门店/分类名或金额含义，不开真实接收器或消耗尝试。两份新闭合Schema固定PARTIAL与UNKNOWN；已有完整业务合同不变。


`collection_adapter/p29_store_inventory.py`提供按分类排列的部分输入视图。参考分类标签单列来源，价格/商品/规格由各行自身响应提供；复用严格候选审核，以分类/SKU选择最新整条行，保留候选和UNKNOWN单位。该视图不接入完整Publisher，不把参考标签提升为同观察字段，不新增采集/UI/重放能力。两份`p29-store-input-inventory`闭合合同固定PARTIAL与不可提升完整结果。
