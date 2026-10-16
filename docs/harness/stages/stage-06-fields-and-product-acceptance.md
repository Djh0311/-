# Stage 06 字段充分性与产品验收

2026-10-12 后续实施：用户在排除图片后明确“继续做后续工作”。已实现 P32 的独立本地结果入口：`python3 -B -m collection_adapter.p32_result_entry` 无参数定位当前已交付表格、字段说明和缺失清单，核对 manifest 合同及文件状态，失败给固定原因和恢复方法。7 项合成测试通过，当前 11 个结果文件的目录检查通过；未读取业务表正文或重做来源核对。此切片只依赖已交付文件，不要求先证明全店收齐；P29/P31 资格、P32 真实采集入口和整体验收均未提升。使用说明：`docs/harness/p32-local-results.md`；证据：`docs/harness/reports/P32-local-entry-validation.json`。

2026-10-12 最新范围：用户明确“图片跳过”。图片下载、保存、图片标识及引用导出均移出当前交付范围，不再计入未完成项或验收缺口；不启动图片合同或解析实现。已有公开标签文字和业务结果保留。当前价格和费用均已确认为人民币元；其余语义、来源资格及全店覆盖结论不因本次范围调整而改变。

目标：尽量收齐六类已确认可得的公开业务字段，交付易用结果和运行入口，并以真实数据验收产品。
状态：ACTIVE_P31_P32_PARTIAL；2026-10-12 已按六类共 27 组需求复核，已发现的公开文本/来源码/初始元数据漏项已补；当前价格/费用已由用户确认为人民币元；图片已移出范围，其它语义/范围仍缺证，整体未验收，P32 本地入口已交付，P33 未启动。当前结论见 ../reports/P31-six-group-acceptance-review.md；不新增真实运行或发布授权。
产品：清晰业务表、完整结构化结果、字段与商品覆盖报告、操作说明及真实验收记录。
证据：真实字段与页面核对、明确的缺失原因、多个获准目标/场景的结果及已解决问题。

相关权威设计：

- docs/harness/plan.md 的 R03–R10
- docs/harness/field-coverage-plan.md
- docs/harness/stages/stage-05-real-sku-and-store-coverage.md
- docs/price-margin-data-asset-v1.md（价格→毛利数据资产、规模化监控的前瞻设计）

相关现有实现：

- collection_core/p1_contract.py
- collection_core/p1.py
- collection_core/p1_result_views.py
- collection_adapter/runner.py
- contracts/schemas/

必须保持的架构边界：

- 真实扩展字段需单独版本化接入，不能改名或去掉 synthetic 检查就声称合格。
- 新字段只取实际范围内的公开业务信息，语义不明标待确认，不能通过自由对象或原始响应落盘扩充。
- 可选未提供字段与已知可得但未实现字段分开，业务字段数与关联元数据列数分开。
- 产品验收不自动改变来源资格、正式 Parser/Provider、系统权限、Git 或发布权限；这些事实分别核验。

## 叶子与依赖

| 任务 | 交付 | 前置 |
| --- | --- | --- |
| [P31](../unfinished/P31-public-business-fields.md) | 六类可得字段的版本化解析、关联、导出适配 | P28 accepted，不等待 P30 |
| [P32](../unfinished/P32-usable-export-and-entry.md) | 易读业务表、完整 JSON、覆盖说明及简化使用入口 | 完整交付须 P29 与 P31 accepted；本地只读入口独立交付 |
| [P33](../unfinished/P33-real-product-acceptance.md) | 真实结果、完整性、字段充分性和操作恢复的产品验收 | P30、P31、P32 accepted |

完成标准：

- 六类字段逐项说明已导出、未提供、待确认、未适配或不适用；需求范围内已确认可得字段没有未说明的遗漏。
- 商品、SKU、各类价格、活动适用对象与配送语义经真实核对，无伪造补值。
- 用户无需编写私有配置；就绪、采集、停止和结果位置明确，必须手动的步骤易于执行。
- 业务表可直接查看，完整 JSON 保留结构与必要关联；缺失原因和覆盖范围实际导出，结果不覆盖。
- 获准的不同目标与场景有真实证据；未出现/无法验证的场景如实列出，不把合成通过写成真实通过。
- P30、P31、P32、P33 的产品证据均通过；仍有真实结果或需求缺口时 productResult=incomplete。
