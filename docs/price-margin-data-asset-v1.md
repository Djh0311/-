# 价格→毛利 数据资产 v1:架构方案、P0 冻结规范与 AI 派工手册

## 1. 结论与证据上限

本文件是**总设计蓝图与 P0 契约冻结规范**,定义“把美团小程序店铺链接交给程序 → 自动抓取 → 价格/毛利数据资产 → 降价告警 → 通知机器人”这一后续产品形态的架构、五个接缝契约、数据库表结构、美团响应映射规则与分阶段实现 AI 派工单。

本文件**不构成**实现、真实采集、latch 变更、来源资格或 Provider/Parser 资格的授权,也不改变当前状态:

```text
SOURCE_QUALIFICATION=NO_QUALIFIED_SOURCE
LIVE_CAPTURE_LATCH=CLOSED
EXECUTION_LATCH=CLOSED
```

- 真实采集仍沿用本项目既有的**按窗口显式授权 + 两 latch 默认 CLOSED + 新根/引用/锁 + 准确 PID 预检**模型(见 `docs/harness/plan.md` R09/R13/R16)。本设计不自动开启任何窗口,也不新增任何自动 arm 路径。
- 本文件 **value-free**:只引用结构性计数与合成示例,不含任何敏感值、凭据、原始正文或值哈希。
- 注意目录边界:`docs/design/` 受 `autocapture/build-manifest.json` 与 `autocapture/tools/verify_autocapture_build.py --strict` 封闭清单保护(仅允许 `docs/design/autocapture-shape-discovery-v1.md`),因此本设计文件与后续 P0–P6 规范统一存放在 `docs/price-margin-data-asset-v1.md`,避免触发 `EXTRA_FILE` 校验失败。
- “店铺链接 → 自动打开并抓取”目前**尚未实现**(plan.md 2026-10-16),是本设计针对的**目标形态**,属于用户负责的抓取层。

**事实基线**(取自 plan.md 2026-10-16 已保存数据的结构计数,仅作设计依据):
- 1220 个商品、1318 个规格;其中 **1156 个规格有 12–14 位编号**(可作唯一码)、161 个为空、1 个非标准长度;
- **412 个商品有带商品编号的分享链接**(`share_tip.share_info.url` / `weixin_url`);只出现在滑动接口(`smooth/render`)里的约 800 个商品分享链接为空;
- 44 个分类声明共 1039 个商品,其中 **14 个分类还有下一页**(`has_next_page=true`)。

这三条直接回答了之前两个“待实测项”:唯一码主要落在**规格(SKU)级**且覆盖大多数但非全部(需降级兜底);商品链接**部分可得**(决定“重点单品探”只能部分启用)。

---

## 2. 北极星与范围

**北极星**:一套**按区域划分的“价格→毛利”数据资产**,持续掌握 ~200 家自有店(每区域约 70 家)每个商品规格的到手价与历史,任何降价第一时间按区通知负责人,并支撑盈利与运营决策。

| 维度 | 内容 |
|---|---|
| **现在做** | 价格抓取接入 · 价格/毛利数据资产(售价+成本)· 降价告警(按区路由)· 可靠性/健康 · 区域隔离 |
| **留接缝、后面做** | 总利润(对接订单系统)· 跨店最低三家 · 上新/下架/售罄/门店级告警 · 负责人报表加厚 |
| **不做** | 抓取内部实现(用户的)· 订单/销量数据(用户另一套系统)· 图片 |

边界:本系统只算**单位毛利 = 到手价 − 单位成本**;**总利润 = 单位毛利 × 销量**由外部订单系统按 `(product_key, store_id, time)` join 本资产完成(见 P5)。

---

## 3. 能力边界与 latch 姿态

抓取层是**用户的黑盒**,受既有 `autocapture/` 的默认拒绝基础 + 按窗口授权 + 两 latch 管控。本设计中**我方各层(编排/存储/比对/通知)全部是离线软件**,不直接触碰网络、微信/浏览器 UI、CA、系统代理或系统设置。

| 能力 | 本设计的姿态 |
|---|---|
| network / browser / ui | 不直接调用;抓取由用户黑盒在既有 per-window 授权下进行 |
| certificate / system_proxy / administrator | 本设计不新增任何操作路径 |
| credential / session | 禁止读取或派生;凭据不入库、不入 Git |
| filesystem_write | 仅限数据资产库与导出工件(受控目录) |

调度器只向抓取层投递 `CaptureJobRequest`(worklist),**是否真的开窗抓取由用户在既有授权模型下显式决定**;调度软件本身不 arm 采集。

---

## 4. 系统全景与五个接缝

```text
[调度器/区] ─(CaptureJobRequest)→ [Redis 队列/区] ─→ [抓取黑盒 · 用户] ─(CaptureResult)→ [接入]
                                                                                           │
                                                                      (CostFeed · 用户维护成本)
                                                                                           ▼
                                                        [价格/毛利数据资产 · SQLite(试点)/PostgreSQL(生产)]
                                  [变化检测] ─(NotificationEvent · 按区路由)→ [outbox] → [机器人 → 区域负责人]
                                  [数据资产] ─(AssetQuery/Export · 按 UPC/店/时间)→ [订单系统→总利润 / 区域报表]
                                  [健康监控] ─(覆盖/新鲜度/失败告警,独立于价格告警)
```

**五个接缝 = 分活给不同实现 AI 的边界(契约):**

1. `CaptureJobRequest`(调度 → 抓取)
2. `CaptureResult`(抓取 → 接入)
3. `CostFeed`(用户成本 → 资产)
4. `NotificationEvent`(告警 → 机器人,带区域路由)
5. `AssetQuery/Export`(资产 → 订单系统 / 报表)

只要这五个契约冻结,四层可由不同 AI 并行实现,互不依赖对方内部。

---

## 5. 数据资产模型概览

原则:**UPC(唯一码)为脊梁** —— 一头连抓来的到手价、一头连成本、还连跨店比价;**所有行带 `region_id`**;**历史 append-only**;**钱用整数分 + 币种**;**当前投影与历史分离**。

| 表 / 视图 | 作用 | 关键列 / 说明 |
|---|---|---|
| `regions` | 区域 | 隔离与权限的根(`region_id`, `name`, `manager_bot_channel`) |
| `stores` | 门店 | `store_id`、`region_id`、`store_link`、`store_name`、`platform_poi_id`、`monitor_config_json`、`status` |
| `products` | **当前投影** | 唯一键 `(store_id, product_key)`;`final_price_minor`、`list_price_minor`、`sale_status`、`content_hash`、`key_source`、`region_id` |
| `product_observations` | **历史(append-only)** | 唯一键 `(run_id, store_id, product_key)`;`final_price_minor`、`sale_status`、`observed_at`、`is_run_complete`、`region_id` |
| `change_events` | **事件(append-only)** | `PRICE_DROP` 等;`old/new_final_price_minor`、`delta_minor`、`drop_pct_bp`、`confidence`、`region_id` |
| `costs` | **用户维护成本** | `product_key`、`scope_type(GLOBAL/REGION/STORE)`、`scope_id`、`unit_cost_minor`、`currency`、`effective_from` |
| `runs` | 运行台账 | `run_id`、`store_id`、`region_id`、`granularity`、`is_complete`、计数、缺口原因、`trigger_source` |
| `notifications_outbox` | 投递队列 | `outbox_id`、`event_id`、`region_id`、`target_channel`、`payload_json`、`delivery_status`、`retry_count` |
| `v_product_margins`(视图) | 毛利视图 | `products / product_observations ⋈ costs` 按 `(product_key, store_id/region_id/GLOBAL)` 优先级计算单位毛利 |

**粒度(据事实基线)**:以**规格(SKU)**为基本行;`product_key` 优先取 12–14 位标准条码(`upc:<upccode>`)。约 161 个规格无条码 → `key_source` 按确定性规则降级(`UPC` → `PLATFORM_SKU_ID` → `PRODUCT_LINK` → `NAME_SPEC_FALLBACK`),并在 `confidence` 中标出。

---

## 6. 五个契约概览

1. **`CaptureJobRequest`** —— 调度向抓取端下发的采集任务单,必带 `region_id`、`store_id`、`granularity(STORE_SWEEP | PRODUCT_PROBE)` 与过期时间。
2. **`CaptureResult`(最关键)** —— 抓取端向接入层交付的标准化店铺/规格价格快照。价格字段统一为整数分(`final_price_minor` 优惠后到手价、`list_price_minor` 原价上下文);每个规格必带 `product_key` + `key_source`;全店扫必带 `completeness` 对象。
3. **`CostFeed`** —— 用户导入/维护的成本流水,支持 `GLOBAL` / `REGION` / `STORE` 三级作用域(`STORE > REGION > GLOBAL` 覆盖优先级)。
4. **`NotificationEvent`** —— 变化检测产出的告警事件,必带 `region_id`、路由目标、降价前后价格、降幅基点(`drop_pct_bp`)、`confidence` 以及可选的毛利变化(`margin_before_minor` → `margin_after_minor`)。
5. **`AssetQuery / AssetExport`** —— 面向区域负责人报表与外部订单系统(P5 总利润计算)的统一只读查询与批量导出契约,以 `(product_key, store_id, observed_at)` 为关联主轴。

---

## 7. 核心流程

1. **监控循环**:调度器按区错峰到点 → 生成 `CaptureJobRequest` 入该区队列 → 抓取端按自己速度取、抓完回 `CaptureResult` → 接入(Schema 校验 / 幂等检查 `run_id` / 落 `product_observations` / 更新 `products` 当前投影 / 记 `runs`)→ 变化检测(**首轮静默建基线**;**仅 `is_complete=true` 的全店扫判 `REMOVED_PRODUCT`**;`final_price_minor` 下降跃迁 → `PRICE_DROP`;dedup + 冷却窗)→ 按 `product_key` join `costs` 算单位毛利 → 生成 `NotificationEvent`(按 `region_id` 路由)→ 写入 `notifications_outbox` → 机器人投递给对应区域负责人。
2. **成本维护**:用户通过 CSV/JSON 导入 `CostFeed` → 写入 `costs` → `v_product_margins` 与后续 `NotificationEvent` 自动带出毛利。
3. **负责人查看**:区域范围查询(`region_id` 强制过滤)→ 只出本区价格、单位毛利与告警历史。
4. **后期贯穿(P5)**:外部订单系统按 `(product_key, store_id, time)` join `AssetExport` → `unit_margin_minor × 销量 = 总利润`。

---

## 8. 可靠性与正确性规则(信任层)

- **首轮静默**:一家店首次成功摄入只建立 `products` 基线与 `product_observations` 历史,不触发任何价格或新增告警,避免首轮全店刷屏。
- **`removed` 只在 `is_complete=true` 的全店扫判**:不完整轮(`is_complete=false`,例如存在 `has_next_page=true` 未翻完的分类)只落观察、更新已见商品的价格投影,绝不判未见商品下架,也不因缺页误报。
- **幂等接入**:同一 `run_id` 重复摄入直接返回既有收据,不重复写入 `product_observations`、不重复触发 `change_events` 或 `notifications_outbox`。
- **降价只在下降跃迁报**:仅当本轮 `new_final_price_minor < old_final_price_minor` 时产生 `PRICE_DROP`;维持同一低价的后续轮次不重复推送;同一 `(store_id, product_key, new_final_price_minor)` 在冷却窗(默认 24 小时)内防抖。
- **健康告警独立于价格告警**:“某店连续 N 小时无完整运行”“队列积压超时”“单轮抓取不完整率过高”“单轮异常大面积变动(>30% 商品同时降价或下架)”——触发熔断并转入独立的 `HEALTH_ALERT` 通道,不污染业务负责人的降价通知。
- **`confidence` 显式挂事件**:由 `key_source` 与本轮 `completeness.is_complete` 共同决定(`HIGH` / `MEDIUM` / `LOW`),让区域负责人一眼区分“标准条码+完整轮”与“无码兜底/部分轮”。

---

## 9. 技术栈与部署形态

- **语言**:Python 3(全仓统一,零外部重依赖即可跑通 P0–P2,便于分活与离线单测)。
- **存储**:统一封装 `AssetRepository` 接口;**P0–P2 试点阶段使用 SQLite**(单文件、零运维、事务严密),**P3–P4 规模化阶段切换 PostgreSQL**(按 `region_id` + 时间分区),上层业务与比对逻辑零改动。
- **调度 + 队列**:每区域一条 **Redis 队列**(P3 引入),作为“每小时想抓”与“抓取端实际吞吐”之间的缓冲垫;积压可观测,过期任务按 `expires_at` 丢弃或合并。
- **比对/通知**:无状态 Python worker,消费 `notifications_outbox`,按 `region_id` 路由到对应区域机器人的 webhook/stub。
- **区域 = 分片 + 权限边界**:所有表、查询、队列、推送均以 `region_id` 为第一顺位隔离键。

---

## 10. 开发计划(P0–P6)

每个阶段是一个可整包交给实现 AI 的独立工程单元:

- **P0 契约与资产骨架冻结** —— 冻结五接缝 JSON Schema 与校验函数 + SQLite/Repository 资产表 DDL + 金额(`amount_minor`)、时间(UTC ISO-8601)、`product_key` 降级、`confidence` 与 `completeness` 纯函数及单测。*完成判据*:实现 AI 照契约能独立开工、无需追问;全套离线单测通过。
- **P1 一家店端到端(垂直切片)** —— 离线响应目录或 `CaptureResult` → 摄入 SQLite → 首轮静默建基线 → 第二轮 `final_price_minor` 下降跃迁 → 产出 `PRICE_DROP` 事件与 `NotificationEvent` → 写入 `notifications_outbox` 并由 stub 机器人输出。*完成判据*:单店一次降价产出一条字段完整的告警,首轮静默、同价不重报、同 `run_id` 幂等。
- **P2 把一家店做稳(信任层 + 毛利打通)** —— 接入 `CostFeed` 导入与三级作用域查询,告警自动附带 `unit_cost_minor`、`margin_before_minor`、`margin_after_minor`;实现 `is_complete` 守卫、冷却窗防抖、单轮大面积异常熔断与独立 `HEALTH_ALERT`;提供 `p29_pages_*` 真实离线目录到 `CaptureResult` 的转换适配器。*完成判据*:单店“价格→毛利→降价告警”完整闭环跑通,1220 商品/1318 规格离线转换与比对回归通过。
- **P3 自动化 + 队列 + PostgreSQL(单区 ~70 店可扩)** —— 调度器 + 每区 Redis 队列、每小时派单、过期合并策略;`product_link` 可用商品(约 412/1220)支持 `PRODUCT_PROBE` 重点单品探;`AssetRepository` 增加 PostgreSQL 实现。
- **P4 多区域 + 权限隔离(~200 店)** —— 多区域路由配置、按 `region_id` 强制隔离的 `AssetQuery/Export` 视图与区域负责人日报/周报、每区健康看板。
- **P5 资产增值应用(长期,各自独立)** —— (a) **总利润**:`AssetExport` 对接外部订单系统 → 单位毛利 × 销量;(b) 跨店**最低三家**比价(按 `upc:` 主键跨店聚合);(c) 加厚告警(上新/下架/售罄/门店级)。
- **P6 运营长青** —— 监控“监控本身”、历史分区归档清理、Schema 版本演进。

---

## 11. 边界声明

本文件为离线设计与契约冻结规范,**不**提升任何资格,**不**开启网络/UI/CA/系统能力,**不**改变两 latch,**不**自动执行真实采集。真实采集、latch 变更或正式资格均属新的产品决定,须新的事实输入与用户明确授权,并在本项目既有的 per-window 授权 + 两 latch + 新根/引用/锁模型下进行。

---

## 12. P0 五个接缝契约冻结规范(实现 AI 权威依据)

> **全局数据类型约定(所有契约通用)**:
> 1. **金额**:一律使用**整数分(`*_minor`, int)**,禁止使用浮点数传金额。人民币 1 元 = `100` 分(例如 `19.90` 元写作 `1990`)。原始字符串/数字转整数分必须使用 `Decimal(str(val)) * Decimal("100")` 四舍五入到整数(`ROUND_HALF_UP`)。
> 2. **比例/百分比**:一律使用**整数基点(`*_bp`, int, 1 bp = 0.01% = 万分之一)**。例如降价 `15.25%` 写作 `1525`。计算公式:`round((abs(delta_minor) * 10000) / old_final_price_minor)`。
> 3. **币种**:固定大写 ISO 4217 字符串,当前固定为 `"CNY"`。
> 4. **时间**:一律使用 UTC ISO-8601 字符串,格式 `YYYY-MM-DDTHH:MM:SSZ`(或带微秒 `+00:00`)。
> 5. **封闭对象**:所有契约顶层与嵌套对象均遵循 `additionalProperties: false`,禁止塞入未声明字段、原始响应体或敏感值。

### 12.1 契约 1:`CaptureJobRequest` (`price-asset.capture-job-request.v1`)

调度器投递给抓取队列的任务单。

| 字段名 | 类型 | 必填 | 约束与语义 |
|---|---|---|---|
| `schema_version` | `string` | 是 | 固定值 `"price-asset.capture-job-request.v1"` |
| `job_id` | `string` | 是 | 非空唯一任务 ID(如 `"job_20261016_east01_store001_0800"`) |
| `region_id` | `string` | 是 | 区域唯一标识(如 `"region_east_01"`),决定队列分片与后续权限边界 |
| `store_id` | `string` | 是 | 系统内部门店唯一标识(如 `"store_0001"`) |
| `granularity` | `string` | 是 | 枚举:`"STORE_SWEEP"`(全店扫描) \| `"PRODUCT_PROBE"`(重点单品探查) |
| `target_link` | `string` | 是 | 店铺入口链接或单品分享链接(非空字符串) |
| `target_product_keys` | `array<string>` | 是 | `STORE_SWEEP` 时为空数组 `[]`;`PRODUCT_PROBE` 时为非空 `product_key` 列表 |
| `trigger` | `string` | 是 | 枚举:`"SCHEDULED_HOURLY"` \| `"MANUAL"` \| `"RETRY"` \| `"VERIFY"` |
| `requested_at` | `string` | 是 | 任务生成 UTC 时间戳 |
| `expires_at` | `string` | 是 | 任务队列过期 UTC 时间戳(超过此时间抓取端可直接丢弃并记 `EXPIRED`) |

**合成示例(Value-Free)**:

```json
{
  "schema_version": "price-asset.capture-job-request.v1",
  "job_id": "job_20261016_r01_s001_0001",
  "region_id": "region_01",
  "store_id": "store_001",
  "granularity": "STORE_SWEEP",
  "target_link": "meituan://waimai.example/store/store_001",
  "target_product_keys": [],
  "trigger": "SCHEDULED_HOURLY",
  "requested_at": "2026-10-16T08:00:00Z",
  "expires_at": "2026-10-16T09:00:00Z"
}
```

---

### 12.2 契约 2:`CaptureResult` (`price-asset.capture-result.v1`)

抓取层(或离线响应转换器)交付给数据资产接入层的标准化结果。**以规格(SKU)为 `items[]` 的基本行**。

| 字段名 | 类型 | 必填 | 约束与语义 |
|---|---|---|---|
| `schema_version` | `string` | 是 | 固定值 `"price-asset.capture-result.v1"` |
| `run_id` | `string` | 是 | 本次抓取运行唯一 ID(接入层幂等键) |
| `job_id` | `string \| null` | 是 | 对应 `CaptureJobRequest.job_id`;手动或离线导入可为 `null` |
| `region_id` | `string` | 是 | 门店所属区域 ID |
| `store_id` | `string` | 是 | 系统内部门店 ID |
| `store_name` | `string` | 是 | 门店公开名称 |
| `platform_poi_id` | `string \| null` | 是 | 平台门店编号(如 `poi_id_str` 或数字 `wm_poi_id` 字符串) |
| `granularity` | `string` | 是 | 枚举:`"STORE_SWEEP"` \| `"PRODUCT_PROBE"` |
| `observed_at` | `string` | 是 | 本次观察完成 UTC 时间戳 |
| `currency` | `string` | 是 | 固定值 `"CNY"` |
| `completeness` | `object` | 是 | 完整性声明对象,结构见下表 |
| `items` | `array<object>` | 是 | 去重后的规格(SKU)级观察列表,同一 `run_id` 内 `(store_id, product_key)` 唯一 |

#### `completeness` 子对象字段规范

| 字段名 | 类型 | 必填 | 约束与语义 |
|---|---|---|---|
| `is_complete` | `boolean` | 是 | **核心信任布尔值**。仅当 `granularity == "STORE_SWEEP"` 且 `pagination_terminated == true` 且 `categories_with_unfetched_next_page == 0` 且 `incomplete_reasons` 为空数组时才允许为 `true` |
| `categories_expected` | `integer \| null` | 是 | 门店声明的分类总数(如 `44`);`PRODUCT_PROBE` 时可为 `null` |
| `categories_seen` | `integer` | 是 | 实际观察到的分类数(`>= 0`) |
| `categories_with_unfetched_next_page` | `integer` | 是 | 响应中仍带 `has_next_page == true` 且未抓完后续页的分类数(事实基线中为 `14`) |
| `items_expected` | `integer \| null` | 是 | 门店声明或引用集合并集的商品(SPU)总数(如 `1220` 或分类累计 `1039`) |
| `items_seen` | `integer` | 是 | 实际解析出的去重商品(SPU)数 |
| `skus_seen` | `integer` | 是 | 实际解析出的去重规格(SKU)数(等于 `len(items)`) |
| `pagination_terminated` | `boolean` | 是 | 所有已见分类是否均已到达末页(`has_next_page == false`) |
| `incomplete_reasons` | `array<string>` | 是 | 枚举数组:`"UNFETCHED_CATEGORY_NEXT_PAGE"` \| `"PARTIAL_CATEGORY_COVERAGE"` \| `"PRODUCT_PROBE_ONLY"` \| `"TRANSPORT_OR_PARSE_DROP"` \| `"USER_STOPPED_EARLY"` |

#### `items[]` 单条规格(SKU)对象字段规范

| 字段名 | 类型 | 必填 | 约束与语义 |
|---|---|---|---|
| `product_key` | `string` | 是 | **资产脊梁键**,按 12.2.1 优先级生成(如 `"upc:6900000000001"` 或 `"mt_sku:10000000001"`) |
| `key_source` | `string` | 是 | 枚举:`"UPC"` \| `"PLATFORM_SKU_ID"` \| `"PRODUCT_LINK"` \| `"NAME_SPEC_FALLBACK"` |
| `upccode` | `string \| null` | 是 | 12–14 位标准数字条码;无码或非标时为 `null` |
| `platform_spu_id` | `string` | 是 | 平台商品编号(来自商品 `id` 转字符串) |
| `platform_sku_id` | `string` | 是 | 平台规格编号(来自 `skus[].id` 转字符串) |
| `product_name` | `string` | 是 | 商品名称(来自商品 `name`) |
| `sku_spec` | `string` | 是 | 规格名称(来自 `skus[].spec`,单规格无文案时为空字符串 `""`) |
| `category_names` | `array<string>` | 是 | 该规格所属的分类名列表(跨分类出现时合并去重并按字典序排列) |
| `final_price_minor` | `integer` | 是 | **核心比对字段**:当前优惠后到手价(整数分,`>= 0`,来自 `skus[].price`) |
| `list_price_minor` | `integer \| null` | 是 | 原价/划线价(整数分,`>= 0`,来自 `skus[].origin_price`,仅作上下文) |
| `stock` | `integer \| null` | 是 | 库存数(来自 `skus[].stock`) |
| `sale_status` | `string` | 是 | 枚举:`"ON_SALE"` \| `"SOLD_OUT"` \| `"OFF_SHELF"` |
| `product_link` | `string \| null` | 是 | 商品分享链接或小程序路径(来自 `share_tip`,仅在约 412/1220 商品上非空,其余为 `null`) |
| `promotion_summary` | `string \| null` | 是 | 公开促销/折扣标签摘要(如 `"7.5折 限1份"`,无则为 `null`) |

#### 12.2.1 `product_key` 与 `key_source` 确定性生成规则

针对事实基线中“1318 个规格里 1156 个有 12–14 位 `upccode`、161 个为空、1 个非标准”的真实分布,所有解析器必须严格执行以下四级降级规则:

1. **第一优先级 `UPC`**:若 `skus[].upccode` 去除首尾空白后匹配正则 `^\d{12,14}$`,则:
   - `product_key = f"upc:{upccode}"`
   - `key_source = "UPC"`
   - *优势*:天然支持同店历史比对、与用户 `CostFeed` 条码表直接 join、以及跨店同品比价。
2. **第二优先级 `PLATFORM_SKU_ID`**:若无合格 `upccode`,但 `skus[].id` 为有效非空平台规格编号,则:
   - `product_key = f"mt_sku:{platform_sku_id}"`
   - `key_source = "PLATFORM_SKU_ID"`
   - *优势*:在同店多轮抓取之间完全稳定,不会把 161 个无码规格丢弃。
3. **第三优先级 `PRODUCT_LINK`**:若 `skus[].id` 缺失但 `product_link` 中带有明确 `spu_id` 参数,则:
   - `product_key = f"mt_link:{spu_id}:{normalized_spec}"`
   - `key_source = "PRODUCT_LINK"`
4. **第四优先级 `NAME_SPEC_FALLBACK`**:极端兜底:
   - `product_key = f"fallback:{normalized_product_name}:{normalized_spec}"`
   - `key_source = "NAME_SPEC_FALLBACK"`

**合成示例(Value-Free)**:

```json
{
  "schema_version": "price-asset.capture-result.v1",
  "run_id": "run_20261016_080500_001",
  "job_id": "job_20261016_r01_s001_0001",
  "region_id": "region_01",
  "store_id": "store_001",
  "store_name": "示例自有门店01",
  "platform_poi_id": "10000001",
  "granularity": "STORE_SWEEP",
  "observed_at": "2026-10-16T08:05:00Z",
  "currency": "CNY",
  "completeness": {
    "is_complete": false,
    "categories_expected": 44,
    "categories_seen": 44,
    "categories_with_unfetched_next_page": 14,
    "items_expected": 1220,
    "items_seen": 1220,
    "skus_seen": 1318,
    "pagination_terminated": false,
    "incomplete_reasons": ["UNFETCHED_CATEGORY_NEXT_PAGE"]
  },
  "items": [
    {
      "product_key": "upc:6900000000001",
      "key_source": "UPC",
      "upccode": "6900000000001",
      "platform_spu_id": "20000000001",
      "platform_sku_id": "30000000001",
      "product_name": "合成示例商品A",
      "sku_spec": "500ml/瓶",
      "category_names": ["推荐", "饮品"],
      "final_price_minor": 1590,
      "list_price_minor": 1990,
      "stock": 50,
      "sale_status": "ON_SALE",
      "product_link": "https://i.waimai.meituan.com/external/food?spu_id=20000000001",
      "promotion_summary": "限时特惠"
    }
  ]
}
```

---

### 12.3 契约 3:`CostFeed` (`price-asset.cost-feed.v1`)

用户导入或维护的商品单位成本契约。支持按全局(`GLOBAL`)、区域(`REGION`)或单店(`STORE`)配置成本,查询时按 **`STORE > REGION > GLOBAL`** 优先级匹配且取 `effective_from <= observed_at` 的最新一条。

| 字段名 | 类型 | 必填 | 约束与语义 |
|---|---|---|---|
| `schema_version` | `string` | 是 | 固定值 `"price-asset.cost-feed.v1"` |
| `batch_id` | `string` | 是 | 导入批次唯一 ID |
| `imported_at` | `string` | 是 | 导入 UTC 时间戳 |
| `source` | `string` | 是 | 枚举:`"MERCHANT_CSV_IMPORT"` \| `"ERP_SYNC"` \| `"MANUAL_EDIT"` |
| `entries` | `array<object>` | 是 | 成本条目列表(非空) |
| `entries[].product_key` | `string` | 是 | 优先使用 `"upc:<12-14位条码>"`,也可对无码商品使用 `"mt_sku:<sku_id>"` |
| `entries[].scope_type` | `string` | 是 | 枚举:`"GLOBAL"` \| `"REGION"` \| `"STORE"` |
| `entries[].scope_id` | `string` | 是 | `GLOBAL` 时固定为 `"GLOBAL"`;`REGION` 时为 `region_id`;`STORE` 时为 `store_id` |
| `entries[].unit_cost_minor` | `integer` | 是 | 单位成本(整数分,`>= 0`) |
| `entries[].currency` | `string` | 是 | 固定值 `"CNY"` |
| `entries[].effective_from` | `string` | 是 | 生效起始 UTC 时间戳 |
| `entries[].effective_to` | `string \| null` | 是 | 生效截止 UTC 时间戳(长期有效为 `null`) |

**合成示例(Value-Free)**:

```json
{
  "schema_version": "price-asset.cost-feed.v1",
  "batch_id": "cost_batch_20261016_01",
  "imported_at": "2026-10-16T00:00:00Z",
  "source": "MERCHANT_CSV_IMPORT",
  "entries": [
    {
      "product_key": "upc:6900000000001",
      "scope_type": "GLOBAL",
      "scope_id": "GLOBAL",
      "unit_cost_minor": 1100,
      "currency": "CNY",
      "effective_from": "2026-10-01T00:00:00Z",
      "effective_to": null
    }
  ]
}
```

---

### 12.4 契约 4:`NotificationEvent` (`price-asset.notification-event.v1`)

变化检测层写入 `notifications_outbox` 并推送给区域负责人机器人的标准事件。

#### `confidence` 置信度计算矩阵(冻结规则)

| `key_source` | `completeness.is_complete == true` | `completeness.is_complete == false` |
|---|---|---|
| `"UPC"` | `"HIGH"` | `"MEDIUM"` |
| `"PLATFORM_SKU_ID"` 或 `"PRODUCT_LINK"` | `"MEDIUM"` | `"LOW"` |
| `"NAME_SPEC_FALLBACK"` | `"LOW"` | `"LOW"` |

#### `NotificationEvent` 字段规范

| 字段名 | 类型 | 必填 | 约束与语义 |
|---|---|---|---|
| `schema_version` | `string` | 是 | 固定值 `"price-asset.notification-event.v1"` |
| `event_id` | `string` | 是 | 事件唯一 ID(如 `f"evt_{run_id}_{store_id}_{product_key}"`) |
| `event_type` | `string` | 是 | 当前启用:`"PRICE_DROP"` \| `"HEALTH_ALERT"`;预留:`"NEW_PRODUCT"` \| `"REMOVED_PRODUCT"` \| `"SOLD_OUT"` |
| `region_id` | `string` | 是 | 区域唯一标识(决定推送路由与权限隔离) |
| `routing_target` | `object` | 是 | `{ "target_type": "REGION_MANAGER_BOT", "region_id": "...", "channel_key": "..." }` |
| `store_id` | `string` | 是 | 门店 ID |
| `store_name` | `string` | 是 | 门店名称 |
| `run_id` | `string` | 是 | 触发该事件的运行 ID |
| `observed_at` | `string` | 是 | 观察到的 UTC 时间戳 |
| `product_key` | `string` | 是 | 商品规格唯一键 |
| `key_source` | `string` | 是 | 枚举:`"UPC"` \| `"PLATFORM_SKU_ID"` \| `"PRODUCT_LINK"` \| `"NAME_SPEC_FALLBACK"` |
| `confidence` | `string` | 是 | 枚举:`"HIGH"` \| `"MEDIUM"` \| `"LOW"` |
| `product_name` | `string` | 是 | 商品名称 |
| `sku_spec` | `string` | 是 | 规格名称 |
| `product_link` | `string \| null` | 是 | 商品分享链接(可为空) |
| `currency` | `string` | 是 | 固定值 `"CNY"` |
| `old_final_price_minor` | `integer` | 是 | 降价前到手价(整数分) |
| `new_final_price_minor` | `integer` | 是 | 降价后到手价(整数分,必满足 `new < old`) |
| `delta_minor` | `integer` | 是 | `new_final_price_minor - old_final_price_minor`(降价时为负数,如 `-400`) |
| `drop_pct_bp` | `integer` | 是 | 降幅基点(`round((abs(delta_minor) * 10000) / old_final_price_minor)`) |
| `unit_cost_minor` | `integer \| null` | 是 | 匹配到的单位成本(整数分;P1 或未导入成本时为 `null`) |
| `margin_before_minor` | `integer \| null` | 是 | 降价前单位毛利(`old_final_price_minor - unit_cost_minor`,无成本时为 `null`) |
| `margin_after_minor` | `integer \| null` | 是 | 降价后单位毛利(`new_final_price_minor - unit_cost_minor`,无成本时为 `null`) |
| `margin_rate_after_bp` | `integer \| null` | 是 | 降价后毛利率基点(`round((margin_after_minor * 10000) / new_final_price_minor)`,无成本或新价为 0 时为 `null`) |

**合成示例(Value-Free)**:

```json
{
  "schema_version": "price-asset.notification-event.v1",
  "event_id": "evt_run002_store001_upc6900000000001",
  "event_type": "PRICE_DROP",
  "region_id": "region_01",
  "routing_target": {
    "target_type": "REGION_MANAGER_BOT",
    "region_id": "region_01",
    "channel_key": "bot_channel_region_01"
  },
  "store_id": "store_001",
  "store_name": "示例自有门店01",
  "run_id": "run_20261016_090500_002",
  "observed_at": "2026-10-16T09:05:00Z",
  "product_key": "upc:6900000000001",
  "key_source": "UPC",
  "confidence": "MEDIUM",
  "product_name": "合成示例商品A",
  "sku_spec": "500ml/瓶",
  "product_link": "https://i.waimai.meituan.com/external/food?spu_id=20000000001",
  "currency": "CNY",
  "old_final_price_minor": 1990,
  "new_final_price_minor": 1590,
  "delta_minor": -400,
  "drop_pct_bp": 2010,
  "unit_cost_minor": 1100,
  "margin_before_minor": 890,
  "margin_after_minor": 490,
  "margin_rate_after_bp": 3082
}
```

---

### 12.5 契约 5:`AssetQuery` 与 `AssetExport` (`price-asset.asset-export.v1`)

供区域报表查看及 P5 外部订单系统按 `(product_key, store_id, observed_at)` 计算总利润的读取契约。

- **`AssetQuery` 过滤参数**:
  - `region_id` (`string`, **必填** —— 禁止跨区裸查)
  - `store_ids` (`array<string> | null`, 可选门店列表)
  - `product_keys` (`array<string> | null`, 可选条码/唯一键列表)
  - `observed_from` (`string | null`, 起始 UTC 时间)
  - `observed_to` (`string | null`, 截止 UTC 时间)
  - `mode` (`"CURRENT_PROJECTION" | "OBSERVATION_HISTORY"`, 默认 `"CURRENT_PROJECTION"`)
- **`AssetExport` 输出对象 (`price-asset.asset-export.v1`)**:
  - `schema_version`: `"price-asset.asset-export.v1"`
  - `exported_at`: UTC 时间戳
  - `region_id`: 区域 ID
  - `mode`: `"CURRENT_PROJECTION" | "OBSERVATION_HISTORY"`
  - `records[]`: 每行包含 `{region_id, store_id, store_name, product_key, key_source, upccode, platform_spu_id, platform_sku_id, product_name, sku_spec, final_price_minor, list_price_minor, unit_cost_minor, unit_margin_minor, margin_rate_bp, currency, sale_status, observed_at, run_id, is_run_complete, confidence}`。

---

## 13. P0 数据库表结构冻结规范(SQLite / PostgreSQL 兼容 DDL)

以下 DDL 在 SQLite 3 与 PostgreSQL 中均可直接执行(时间统一存 ISO-8601 UTC 文本,金额统一存整数分 `INTEGER`,布尔统一存 `0/1` `INTEGER`)。

```sql
-- 1. 区域表 (隔离与权限边界的根)
CREATE TABLE IF NOT EXISTS regions (
    region_id TEXT PRIMARY KEY,
    region_name TEXT NOT NULL,
    manager_bot_channel TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 2. 门店表
CREATE TABLE IF NOT EXISTS stores (
    store_id TEXT PRIMARY KEY,
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    store_name TEXT NOT NULL,
    store_link TEXT NOT NULL,
    platform_poi_id TEXT,
    monitor_config_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stores_region ON stores(region_id);

-- 3. 采集运行台账表 (幂等与完整性审计)
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    job_id TEXT,
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    granularity TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    is_complete INTEGER NOT NULL CHECK (is_complete IN (0, 1)),
    categories_expected INTEGER,
    categories_seen INTEGER NOT NULL,
    categories_with_unfetched_next_page INTEGER NOT NULL,
    items_expected INTEGER,
    items_seen INTEGER NOT NULL,
    skus_seen INTEGER NOT NULL,
    pagination_terminated INTEGER NOT NULL CHECK (pagination_terminated IN (0, 1)),
    incomplete_reasons_json TEXT NOT NULL DEFAULT '[]',
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_store_observed ON runs(region_id, store_id, observed_at DESC);

-- 4. 商品规格当前投影表 (每店每 product_key 一行最新状态)
CREATE TABLE IF NOT EXISTS products (
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    product_key TEXT NOT NULL,
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    key_source TEXT NOT NULL,
    upccode TEXT,
    platform_spu_id TEXT NOT NULL,
    platform_sku_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    sku_spec TEXT NOT NULL,
    category_names_json TEXT NOT NULL DEFAULT '[]',
    final_price_minor INTEGER NOT NULL CHECK (final_price_minor >= 0),
    list_price_minor INTEGER,
    stock INTEGER,
    sale_status TEXT NOT NULL,
    product_link TEXT,
    promotion_summary TEXT,
    currency TEXT NOT NULL DEFAULT 'CNY',
    content_hash TEXT NOT NULL,
    last_run_id TEXT NOT NULL REFERENCES runs(run_id),
    last_observed_at TEXT NOT NULL,
    last_is_run_complete INTEGER NOT NULL CHECK (last_is_run_complete IN (0, 1)),
    PRIMARY KEY (store_id, product_key)
);
CREATE INDEX IF NOT EXISTS idx_products_region_upc ON products(region_id, product_key);

-- 5. 商品规格历史观察表 (Append-Only, 严禁 UPDATE/DELETE)
CREATE TABLE IF NOT EXISTS product_observations (
    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    product_key TEXT NOT NULL,
    key_source TEXT NOT NULL,
    upccode TEXT,
    platform_spu_id TEXT NOT NULL,
    platform_sku_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    sku_spec TEXT NOT NULL,
    category_names_json TEXT NOT NULL DEFAULT '[]',
    final_price_minor INTEGER NOT NULL CHECK (final_price_minor >= 0),
    list_price_minor INTEGER,
    stock INTEGER,
    sale_status TEXT NOT NULL,
    product_link TEXT,
    promotion_summary TEXT,
    currency TEXT NOT NULL DEFAULT 'CNY',
    observed_at TEXT NOT NULL,
    is_run_complete INTEGER NOT NULL CHECK (is_run_complete IN (0, 1)),
    UNIQUE (run_id, store_id, product_key)
);
CREATE INDEX IF NOT EXISTS idx_obs_region_store_key_time
    ON product_observations(region_id, store_id, product_key, observed_at DESC);

-- 6. 成本维护表 (支持 GLOBAL / REGION / STORE 三级作用域)
CREATE TABLE IF NOT EXISTS costs (
    cost_id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    product_key TEXT NOT NULL,
    scope_type TEXT NOT NULL CHECK (scope_type IN ('GLOBAL', 'REGION', 'STORE')),
    scope_id TEXT NOT NULL,
    unit_cost_minor INTEGER NOT NULL CHECK (unit_cost_minor >= 0),
    currency TEXT NOT NULL DEFAULT 'CNY',
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    source TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    UNIQUE (product_key, scope_type, scope_id, effective_from)
);
CREATE INDEX IF NOT EXISTS idx_costs_lookup
    ON costs(product_key, scope_type, scope_id, effective_from DESC);

-- 7. 价格变化与健康事件表 (Append-Only)
CREATE TABLE IF NOT EXISTS change_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    store_id TEXT NOT NULL REFERENCES stores(store_id),
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    product_key TEXT NOT NULL,
    key_source TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    old_final_price_minor INTEGER,
    new_final_price_minor INTEGER,
    delta_minor INTEGER,
    drop_pct_bp INTEGER,
    unit_cost_minor INTEGER,
    margin_before_minor INTEGER,
    margin_after_minor INTEGER,
    margin_rate_after_bp INTEGER,
    currency TEXT NOT NULL DEFAULT 'CNY',
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_region_store_time
    ON change_events(region_id, store_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_dedup_cooldown
    ON change_events(store_id, product_key, event_type, new_final_price_minor, observed_at DESC);

-- 8. 通知投递 Outbox 表 (事务内与 change_events 同写, 保证至少一次投递)
CREATE TABLE IF NOT EXISTS notifications_outbox (
    outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE REFERENCES change_events(event_id),
    region_id TEXT NOT NULL REFERENCES regions(region_id),
    target_channel TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (delivery_status IN ('PENDING', 'SENT', 'FAILED', 'SUPPRESSED_COOLDOWN')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    delivered_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON notifications_outbox(region_id, delivery_status, created_at);
```

---

## 14. 真实美团响应 → `CaptureResult` 映射规则(基于 2026-10-16 事实基线)

当离线转换器将 `runtime-output/p29_pages_*` 下保存的公开业务响应转换为 `CaptureResult` 时,遵循以下精确路径映射(不读取任何私人分支或凭据):

1. **输入端点集合**:
   - 门店详情:`POST /weapp/shop/v1/poi/detail` → 提取公开 `store_name`、`platform_poi_id`
   - 分类与首屏列表:`POST /mtweapp/v1/poi/sputag/products` → 提取分类定义(`current_page_spu_list` / `product_count` / `has_next_page` / `allSpuIds`)与商品对象(`product_spu_list[]`)
   - 滑动分页渲染:`POST /mtweapp/v1/poi/product/smooth/render` → 提取分页商品对象(`product_spu_list[]` 或 `spu_list[]`)
2. **商品与规格展开**:
   - 每个商品对象 `spu` 的 `spu["id"]` → `platform_spu_id` (`str(spu["id"])`),`spu["name"]` → `product_name`。
   - 遍历 `spu["skus"]` 数组,每个元素 `sku` 生成一条规格候选:
     - `sku["id"]` → `platform_sku_id` (`str(sku["id"])`)
     - `sku.get("upccode")` → 去除空白后若为 12–14 位纯数字则作为 `upccode`,否则 `upccode = None`
     - `sku.get("spec")` → `sku_spec` (空或 `None` 归一为 `""`)
     - `sku["price"]` → 经 `Decimal(str(price)) * 100` 转为整数分 `final_price_minor`
     - `sku.get("origin_price")` → 经 `Decimal(str(origin_price)) * 100` 转为整数分 `list_price_minor`
     - `sku.get("stock")` → `stock` (`int` 或 `None`)
     - `spu.get("share_tip", {}).get("share_info", {}).get("url")` 或 `weixin_url` → 非空字符串则填入 `product_link`,否则 `None`(在事实基线中,仅 `sputag/products` 里的 412 个商品有此链接,只出现在 `smooth/render` 里的约 800 个商品为 `None`)。
3. **跨分类同规格合并去重(关键差异点)**:
   - 第三方工具(小云采集)按 `(分类, SKU)` 重复导出行;但**本数据资产以 `(store_id, product_key)` 为唯一主键**。
   - 同一 `run_id` 内,若同一 `platform_sku_id` 出现在多个分类或同时出现在 `sputag/products` 与 `smooth/render` 中:
     - 合并为**唯一一条** `items[]` 记录;
     - `category_names` 取所有出现分类名的去重有序并集;
     - `product_link` 取非空值优先(即保留 `sputag/products` 提供的分享链接,不被 `smooth/render` 的空链接覆盖);
     - 价格与库存取同运行内最新观察值。
4. **`completeness` 判定规则**:
   - 统计本次运行中所有分类的最终 `has_next_page` 状态;
   - 若存在任意一个分类最终 `has_next_page == True`(例如事实基线中的 14/44 个分类),则 `categories_with_unfetched_next_page > 0`,`pagination_terminated = False`,`is_complete = False`,且 `"UNFETCHED_CATEGORY_NEXT_PAGE"` 加入 `incomplete_reasons`。

### 14.5 第三方工具(小云采集)函数体逆向终局结论与本系统架构对照

经 REA 对参考工具(`main.py` + Cython 模块 `zhuabaojiemian`、`clientParseData`、`mydataV1`、`my_excel`、`my_global_interface`)完成函数体级拆解,确认其真实内部实现如下,并直接验证了本系统架构设计的必要性:

| 维度 | 第三方工具(小云采集)函数体实测事实 | 本系统(“价格→毛利”数据资产)架构设计 |
|---|---|---|
| **采集入口与分支** | `on_caiji_clicked`(`0x18003bb60`)与 `on_caiji_2_clicked`(`0x18003dab0`)对应**店铺区**与**搜索区**两条管道;由 `clientParseData.解析_店铺区_数据`(`0x180021a50`)入字典,再由 `提取树形字典列表_美团`(`0x18000f0d0`)按 `所有商品列表/子类目列表/总数/当前个数` 建树。 | 直接消费美团小程序公开业务响应(`poi/detail`、`sputag/products`、`smooth/render`),无需 GUI 控件中转。 |
| **价格与优惠字段** | `获取表格列标题列表`(`0x18000d970`)固定 16 列:`一级分类、二级分类、商品名称、商品ID、upc码、现价、原价、商品预估价、商品折扣、商品月售、库存、包装费、起订、商品规格、描述、图片链接`。模块字符串表中**根本不存在 `优惠券`、`活动价`、`到手价`**。 | 以 `final_price_minor`(整数分到手价)为比对核心,保留 `list_price_minor`(原价)与 `promotion_summary`,并接 `CostFeed` 直接计算单位毛利(`final_price - unit_cost`)。 |
| **商品链接** | **无任何商品页/规格页/分享链接拼接逻辑**;仅提取 CDN `图片链接` 供 `my_excel` 插图与 `qushuiyin` 打马赛克。 | 从 `sputag/products` 的 `share_tip` 提取真实 `product_link`(412/1220 商品可得),供告警直达与 P3 `PRODUCT_PROBE` 单品探查使用。 |
| **自动翻页与完整性** | `judgmentAutoPage`(`0x180002620`)仅调用 `小程序鼠标在窗口某个范围内滚动鼠标`,函数体中**无任何滚到底、分类变绿、数量停止增长或固定 50 次的终止比较**。 | 严格依据协议字段 `has_next_page` 与分类声明集合计算 `completeness.is_complete`,不完整轮绝不误判下架(`removed`)。 |
| **多店与历史存储** | `on_clearList_clicked`(`0x180043550`)提示“切换店铺会自动覆盖旧的数据”,仅导出单次 `./img/数据导出-*.xlsx`(`商品详情` 单表),无历史、无比对、无汇总表(`想买清单/数据汇总/月销售额` 等字符串均不存在)。 | `region_id` 区域分片隔离 + `(store_id, product_key)` 当前投影 + `product_observations` Append-Only 历史 + 下降跃迁检测 + Outbox 按区路由通知。 |

---

## 15. 给实现 AI 的分阶段派工单(可直接复制发送)

> **总设计师/监理使用说明**:
> 你可以将下方任意一个派工单代码块直接复制给负责写代码的实现 AI(如 Claude / Codex / Grok / Devin)。每个派工单均已内嵌完整边界、输入输出契约与验收命令,实现 AI 无需猜测即可独立交付。交付后由我(总设计师/监理)按验收清单核对代码与单测。

### 15.1 派工单 P0:冻结五接缝契约校验器与 SQLite 数据资产骨架

```markdown
### 任务名称：P0 — 价格→毛利数据资产：五接缝契约校验器与存储骨架实现

#### 1. 背景与权威规范
请先完整阅读仓库内的 `AGENTS.md` 与 `docs/price-margin-data-asset-v1.md`（特别是第 12、13 节）。
你要实现的是“价格→毛利数据资产系统”的 **P0 基础包**。本阶段全部为纯离线 Python 标准库实现，不触碰任何网络、UI、代理、CA 或既有 `autocapture/` 目录。

#### 2. 允许修改的写面（Write Scope）
仅允许新建或修改以下路径（严禁修改 `autocapture/`、`docs/design/`、`_archive/` 或任何既有测试）：
- `price_asset/__init__.py`
- `price_asset/contracts.py`（五个接缝契约的校验器、金额/基点换算、`product_key` 四级生成规则、`confidence` 计算矩阵）
- `price_asset/repository.py`（基于 `sqlite3` 的 8 张核心表 DDL 初始化与 Repository 接口封装）
- `price_asset/tests/__init__.py`
- `price_asset/tests/test_p0_contracts_and_repo.py`

#### 3. 必须实现的精确功能
1. **金额与比例纯函数（`price_asset/contracts.py`）**：
   - `yuan_to_minor(value) -> int`：使用 `Decimal(str(value)) * Decimal("100")`（`ROUND_HALF_UP`）转为非负整数分，拒绝 `float` NaN/负数/非数字。
   - `compute_drop_pct_bp(old_minor: int, new_minor: int) -> int`：当 `old_minor > 0` 且 `new_minor < old_minor` 时返回 `round(((old_minor - new_minor) * 10000) / old_minor)`。
   - `build_product_key(upccode, platform_sku_id, product_link, product_name, sku_spec) -> tuple[str, str]`：严格按 `docs/price-margin-data-asset-v1.md` 12.2.1 的四级优先级返回 `(product_key, key_source)`。
   - `compute_confidence(key_source: str, is_run_complete: bool) -> str`：严格按 12.4 矩阵返回 `"HIGH" | "MEDIUM" | "LOW"`。
2. **五接缝契约严格校验函数（`price_asset/contracts.py`）**：
   - `validate_capture_job_request(payload: dict) -> dict`
   - `validate_capture_result(payload: dict) -> dict`（含 `completeness.is_complete` 一致性校验：若 `categories_with_unfetched_next_page > 0` 或 `pagination_terminated is False` 或 `incomplete_reasons` 非空，但 `is_complete is True`，必须抛出 `ContractValidationError`）
   - `validate_cost_feed(payload: dict) -> dict`
   - `validate_notification_event(payload: dict) -> dict`
   - `validate_asset_export(payload: dict) -> dict`
   - 所有校验器对未知额外字段（`additionalProperties`）、缺失必填字段、类型错误、负数金额均须 fail-closed 抛出 `ContractValidationError`。
3. **SQLite 资产表骨架（`price_asset/repository.py`）**：
   - 实现 `SQLiteAssetRepository(db_path)`，初始化 `docs/price-margin-data-asset-v1.md` 第 13 节定义的全部 8 张表（`regions`, `stores`, `runs`, `products`, `product_observations`, `costs`, `change_events`, `notifications_outbox`）及索引，开启 `PRAGMA foreign_keys = ON`。
   - 提供 `upsert_region`、`upsert_store` 基础方法。

#### 4. 完成判据与自检命令
- 编写不少于 20 个合成单元测试（覆盖五契约正反例、`is_complete` 伪造拦截、12–14 位条码与 161 无码规格降级、`confidence` 矩阵、表初始化与外键约束）。
- 运行以下命令必须全部 0 错误通过：
  `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s price_asset/tests -p 'test_*.py'`
  `PYTHONDONTWRITEBYTECODE=1 python3 -B autocapture/tools/verify_autocapture_build.py --repo-root . --strict`
  `git diff --check`
- 不要执行 `git commit` 或 `git push`。
```

---

### 15.2 派工单 P1:单店端到端垂直切片(摄入 → 首轮静默 → 降价检测 → Outbox 告警)

```markdown
### 任务名称：P1 — 单店端到端垂直切片（CaptureResult 摄入 + 首轮静默 + 降价跃迁告警 + Outbox）

#### 1. 背景与权威规范
请先阅读 `AGENTS.md` 与 `docs/price-margin-data-asset-v1.md`（第 7、8、12、13 节）。
在 P0 完成后，本阶段实现一家店从摄入 `CaptureResult` 到产出 `NotificationEvent` 并投递到 stub 机器人的完整垂直切片。

#### 2. 允许修改的写面（Write Scope）
- `price_asset/ingest.py`（`CaptureResult` 幂等摄入、首轮基线建立、`final_price_minor` 下降跃迁比对、`change_events` 与 `notifications_outbox` 同事务写入）
- `price_asset/notifier.py`（消费 `notifications_outbox`，按 `region_id` 路由到 `StubBotNotifier` 并更新投递状态为 `SENT`）
- `price_asset/repository.py`（补充摄入、比对与 outbox 查询所需事务方法）
- `price_asset/tests/test_p1_vertical_slice.py`

#### 3. 必须实现的精确行为规则
1. **幂等摄入**：若 `run_id` 已存在于 `runs` 表，直接返回既有摄入收据 `{ "status": "DUPLICATE_RUN_IGNORED", "run_id": ... }`，不重复写 `product_observations`，不产生重复事件。
2. **首轮静默（First-Run Silence）**：当某 `store_id` 之前在 `runs` 表中没有任何记录时，本轮所有商品只写入 `product_observations` 与 `products` 当前投影，产出 `0` 条 `change_events` 和 `0` 条 `notifications_outbox`。
3. **降价跃迁检测（Price Drop Transition Only）**：
   - 后续轮次中，对每个 `(store_id, product_key)` 对比 `products.final_price_minor`（旧价 `old`）与本轮 `item.final_price_minor`（新价 `new`）：
   - 仅当 `new < old` 时：生成一条 `event_type = "PRICE_DROP"` 的 `change_events` 记录及对应的 `NotificationEvent`，写入 `notifications_outbox`，并将 `products.final_price_minor` 更新为 `new`。
   - 若第三轮价格仍保持 `new`（未继续下降）：绝不重复报警。
   - 若价格回升（`new > old`）：更新 `products.final_price_minor` 为 `new`（使后续若再次降价能再次触发跃迁），但本轮不发降价告警。
4. **区域隔离路由**：`NotificationEvent` 必须携带门店所属 `region_id` 与该区域的 `manager_bot_channel`，严禁跨区混发。

#### 4. 完成判据与自检命令
- 编写完整的端到端测试 `test_p1_vertical_slice.py`，验证：
  (1) 第一轮摄入 3 个 SKU 全部静默；
  (2) 第二轮其中 1 个 SKU 降价，精确产出 1 条 `PRICE_DROP` 与 1 条 Outbox 消息；
  (3) 重复摄入第二轮 `run_id` 完全幂等；
  (4) 第三轮维持同低价不重复报警；
  (5) 第四轮涨回原价、第五轮再次降价能再次触发告警；
  (6) 两个不同 `region_id` 的门店各自只路由给各自区域的机器人通道。
- 运行：
  `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s price_asset/tests -p 'test_*.py'`
  `PYTHONDONTWRITEBYTECODE=1 python3 -B autocapture/tools/verify_autocapture_build.py --repo-root . --strict`
  `git diff --check`
- 不要执行 `git commit` 或 `git push`。
```

---

### 15.3 派工单 P2:信任层硬化 + `CostFeed` 毛利打通 + 真实离线响应转换器

```markdown
### 任务名称：P2 — 信任层硬化（完整性守卫/冷却防抖/异常熔断）+ CostFeed 毛利计算 + 离线数据转换器

#### 1. 背景与权威规范
请先阅读 `AGENTS.md` 与 `docs/price-margin-data-asset-v1.md`（第 8、12、13、14 节）。
在 P1 基础上，本阶段把单店打磨到生产可信标准：接入 `CostFeed` 算出单位毛利（`到手价 - 成本`），加上冷却窗、大面积变动熔断守卫，并提供将美团公开响应结构转换为 `CaptureResult` 的离线转换器。

#### 2. 允许修改的写面（Write Scope）
- `price_asset/costs.py`（`CostFeed` 导入与按 `STORE > REGION > GLOBAL` + `effective_from <= observed_at` 的成本匹配器、毛利计算器）
- `price_asset/trust_guards.py`（同价冷却窗防抖、不完整轮 `is_complete=False` 守卫、单轮异常大面积变动熔断转 `HEALTH_ALERT`）
- `price_asset/meituan_adapter.py`（按第 14 节规则，将 `sputag/products` + `smooth/render` + `poi/detail` 公开结构合并去重为标准 `CaptureResult`）
- `price_asset/query.py`（实现 `AssetQuery` / `AssetExport` 按 `region_id` 导出当前价格与毛利表）
- `price_asset/ingest.py` 与 `price_asset/repository.py`
- `price_asset/tests/test_p2_trust_and_margin.py`

#### 3. 必须实现的精确行为规则
1. **成本匹配与单位毛利计算**：
   - 导入 `CostFeed` 落 `costs` 表；
   - 计算价格变化或导出资产时，按 `(product_key, store_id/region_id/GLOBAL)` 优先级查找生效成本 `unit_cost_minor`；
   - 自动填充 `NotificationEvent` 中的 `unit_cost_minor`、`margin_before_minor`、`margin_after_minor`、`margin_rate_after_bp`。
2. **信任层三大守卫**：
   - **不完整轮守卫**：当 `completeness.is_complete == False`（如 `categories_with_unfetched_next_page > 0`）时，只更新已见规格的价格与观察历史，严禁将未出现的规格判定为下架（`OFF_SHELF` / `REMOVED_PRODUCT`）。
   - **冷却窗防抖**：同一 `(store_id, product_key, new_final_price_minor)` 在 `cooldown_hours`（默认 24 小时）内若因短暂抖动已发过相同低价的 `PRICE_DROP`，后续重复降到同一价格时标记 `SUPPRESSED_COOLDOWN`，不重复推送机器人。
   - **单轮异常大面积变动熔断**：当门店基线商品数 `>= 20` 且单轮同时触发降价的规格比例 `> 30%`（可配置阈值）时，判定为疑似抓取或平台活动解析异常，扣住本轮逐商品的 `PRICE_DROP` 刷屏，改为生成 1 条门店级 `event_type = "HEALTH_ALERT"` 通知负责人核查。
3. **美团公开结构转换器（`price_asset/meituan_adapter.py`）**：
   - 输入合成或离线的 `poi/detail`、`sputag/products`、`smooth/render` 载荷列表；
   - 按 `platform_sku_id` 跨分类合并去重，保留 `sputag/products` 中的非空 `product_link`，合并 `category_names`；
   - 准确统计 `categories_with_unfetched_next_page` 并设置 `completeness.is_complete`。

#### 4. 完成判据与自检命令
- 编写合成单测 `test_p2_trust_and_margin.py` 覆盖：`STORE > REGION > GLOBAL` 成本优先级、降价前后毛利与毛利率基点计算、冷却窗抑制、>30% 异常批量降价熔断转 `HEALTH_ALERT`、跨分类同 SKU 合并去重与 `has_next_page` 完整性判定。
- 严禁把任何真实业务数据或 `runtime-output/` 内容写入测试 fixture 或 Git。
- 运行：
  `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s price_asset/tests -p 'test_*.py'`
  `PYTHONDONTWRITEBYTECODE=1 python3 -B autocapture/tools/verify_autocapture_build.py --repo-root . --strict`
  `git diff --check`
- 不要执行 `git commit` 或 `git push`。
```
