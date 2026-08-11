# 自研采集机器合同基线

状态：

```text
CONTRACT_BASELINE=OWNED_COLLECTION_V1
JSON_SCHEMA_DIALECT=DRAFT_2020_12
SOURCE_SPECIFIC_SHAPE_SCHEMA=PENDING
NO_PROVIDER_OR_PARSER_BUILD_AUTHORITY
```

本目录给下一阶段开发提供通用、值安全的机器合同。它只定义来源资格、Provider 控制面、观察元数据、标准化字段、业务记录、证据与恢复边界，不定义任何真实 Provider 的专属载荷。

## 使用边界

- 所有对象均为 closed object；未声明字段一律拒绝。
- 每个顶层对象都有固定 `schema_version`。
- `observation-envelope` 只承载可发布元数据和不透明引用，不承载来源正文。
- 真实来源正文只能短暂存在于有界内存中，分类、解析或停止后销毁。
- `field-observation-v2` 是 Parser 的标准化输出，不是 Provider 原始字段镜像。
- `business-record-v2` 只允许由同一观察、同一 context 的字段观测组成。
- 所有 present 字段必须带 context、anchor、evidence 和 source-integrity 引用。
- `value-free-sensitive-stop` 只保留稳定分类码和计数，不保留敏感内容或其派生摘要。
- 正式落盘前还必须执行语义校验；JSON Schema 通过本身不等于来源合格、业务正确或真实运行获批。

以下字段或等价内容在本合同族中禁止：`raw_payload`、`URL`、`query`、`header`、`path`、`credential`、`value_hash`、`raw_error`。也不得通过自由对象、自由键名或日志文本变相携带这些内容。

## Schema 清单

| 文件 | 作用 |
| --- | --- |
| `provider-qualification.schema.json` | 一个候选的来源所有权、用途、shape、能力风险和 QH01–QH12 裁定 |
| `provider-qualification-summary.schema.json` | 多候选计数、引用集合和任务总体裁定 |
| `provider-contract.schema.json` | 已获资格 Provider 的冻结控制面合同 |
| `observation-envelope.schema.json` | 不含来源正文的单观察元数据 |
| `observation-batch.schema.json` | 可封存、可恢复的隐私安全观察批 |
| `field-observation-v2.schema.json` | 带完整同观察 provenance 的字段观测 |
| `business-record-v2.schema.json` | schema-v2 业务观测记录 |
| `coverage-receipt.schema.json` | 覆盖范围和零结果主张边界 |
| `source-integrity-receipt.schema.json` | family/version/shape/预算/隐私完整性结果 |
| `value-free-sensitive-stop.schema.json` | 不含敏感值的硬停止收据 |
| `capability-ledger.schema.json` | Provider、Parser、Publisher、Core 能力账本 |
| `adapter-checkpoint.schema.json` | 不重开真实来源的 Adapter 检查点 |
| `evidence-manifest.schema.json` | 值安全证据与正式导出清单 |
| `error-status-code.schema.json` | 稳定、无原始诊断文本的错误状态 |

资格任务为保持固定文件面，可以使用一个任务级物理封装文件承载
`candidate_results[]` 和 `summary`。这不改变上表的逻辑对象边界：
生产验证器仍须分别用单候选 Schema 和汇总 Schema 验证每个嵌套对象，并验证候选
ID 集合、分类集合与计数精确一致；不得把两类字段合并为一个自由对象。

## 尚未定义

真实 `payload_family`、`payload_version`、字段树和专属 Parser 输入 Schema 仍由
`S2-02-OWNED-SOURCE-QUALIFICATION-001` 阻塞。只有主管接受
`PROVIDER_QUALIFIED_FOR_BUILD` 和冻结的 value-free shape 后，才能在新的版本化文件中增加对应 Schema。

不得为了提前实现 Parser 而在这些通用合同中加入猜测字段、示例业务值或宽松透传对象。

## 语义校验最低要求

实现阶段除 JSON Schema 外，至少还要失败关闭地检查：

1. 候选资格实例和任务总体实例分开；总体计数与候选结果集合精确相等；
2. `route_id` 与 `source_kind` 分开，并在资格、合同、观察、字段、记录和证据链中精确一致；
3. Provider 合同引用的资格结果确实为已接受且版本一致；
4. Envelope 的 family/version 与冻结 shape 精确匹配；
5. Batch 中所有对象属于同一 Provider 合同、同一授权尝试和同一运行；
6. BusinessRecord 的 core binding 引用实际存在的 store、product、price、currency 字段；
7. 所有 present 字段的 observation/context/evidence/integrity 引用一致；
8. coverage 为 `PARTIAL` 或 `UNKNOWN` 时不能发布穷举零结果；
9. source-integrity 非 `VERIFIED` 时不得发布业务记录；
10. Parser I/O、未声明能力、跨来源补值、跨时间补值均为 fatal；
11. 真实来源消费后，checkpoint 只能恢复同一份已封存、隐私安全的批次，不能重新打开来源；
12. manifest 只列值安全工件，并在原子发布后重新计算校验。

`route_id` 是产品/实现路线；`source_kind` 是真实来源 provenance。任何可落盘合同都不得用原载荷精确长度、原值哈希或其他 data-derived 元数据替代值安全状态。

## 版本规则

- 当前合同主线：`s2-02.*.v1`；业务字段合同名称含 `v2`，表示其对应 schema-v2 数据面。
- 增加可选字段也要升版本，禁止靠 `additionalProperties` 扩张。
- 旧版本一旦被任务输入冻结，不原地改写；新版本以新文件发布并提供迁移说明。
- 来源专属 shape 与通用合同分开版本化，Provider 更换不得扩大 Parser 或 Core 权限。
