# Stage 05 真实规格关联与全店覆盖

目标：在首份真实基础结果成立后，正确区分商品、SKU 和价格，并通过分类、分页与去重收齐目标店铺范围。
状态：P29_ACTIVE_DECLARED_COVERAGE_VERIFIED_QUALIFICATION_PENDING；窗口19本轮声明范围已全部覆盖并交付最终233行清单/155商品/200SKU/19分类。初始响应155有序成员+22折叠成员共177个分类商品关系，与实际正文集合完全相等：有序缺0、折叠缺0、额外未声明成员0；5类展开入口均已操作并有自身响应证明。本轮19份v4分类响应、scope拒绝0，147组请求/响应成员匹配，输入253行按SKU/分类保留最新整行去重20行；55初始完整记录+178分类候选，不跨观察补价、不提升候选资格。四组实际输出合同/JSON/CSV/manifest/计数/来源/权限核对通过。有限已声明引用集合耗尽作为本轮停止依据，平台分页终止、未声明或未来商品不作断言。2026-10-11T17:03:14.350370+00:00stop关闭，宿主2974退出、锁消失、stream0、拦截清理、cleanup=COMPLETE、两latch=CLOSED、固定CA保留；HTTP35完整/0失败/0未完成，TLS失败0。当前无页面任务或采集窗口；剩余为分类候选完整业务资格、币种单位及平台终止未确认，P29 active/incomplete，不accepted、不启动P30–P33。证据：docs/harness/reports/P29-window19-final-coverage-direct-check.json、docs/harness/reports/P29-window19-final-inventory-export-receipt.json。 Stage 05仍incomplete。
产品：可追溯到各次观察的店铺商品/SKU 结果集及分类分页覆盖说明。
证据：真实规格和价格对照、分类页面完成依据、商品/SKU 去重、部分或完整范围的准确声明。

相关权威设计：

- docs/harness/plan.md 的 R02–R04、R06–R10
- docs/harness/field-coverage-plan.md
- docs/harness/done/2026-10/stage-04t-live-entry-and-first-result.md
- docs/price-margin-data-asset-v1.md（价格→毛利数据资产、规模化监控的前瞻设计）

相关现有实现：

- parser_candidate/capture_contract.py
- collection_core/p0.py
- collection_core/p1.py
- collection_core/result_publisher.py
- collection_adapter/mitmproxy_bridge.py

必须保持的架构边界：

- P27 的真实成功是进入依据，旧 P21 超时、合成 fixture 或页面可见不替代。
- P26/P28仍以一对新鲜事件为单位；P29显式增加有界完整观察组织及Publisher类型分支，不靠重复旧窗口或删除同观察校验实现分页。
- 结果集可汇总各自完整的记录，单条记录不跨页、跨时间或跨运行补字段。
- 分类/翻页由用户按明确提示触发的首版边界保留；自动 UI、请求重放或多目标扩大另行裁决。
- 每次采集的时间、次数、页面和输出预算明确，失败不覆盖既有完整结果。

## 叶子与依赖

| 任务 | 交付 | 前置 |
| --- | --- | --- |
| [P28](../done/2026-10/P28-real-sku-price-binding.md) | 稳定核心已accepted并退场；覆盖PARTIAL，可选字段留清单 | P27 accepted |
| [P29](../leaves/P29-store-category-pagination.md) | 分类分页编排、多观察汇总与去重 | P28 accepted |
| [P30](../unfinished/P30-store-coverage-acceptance.md) | 全店范围核对和缺口结论 | P29 accepted |

完成标准：

- 多规格、同名不同商品、同商品跨分类等情况有确定行为和实际范围内的证据。
- 分类/页清单、结束依据和未完成项明确；源提供总数时核对，无足够依据时不得声明全店完整。
- 每条记录保留自身来源与时点，JSON/CSV 与计数一致，发布失败不能覆盖已有结果。
- P28–P30 accepted；无法证明全店完整时维持该目标 incomplete，而不是改名为完整交付。

并行关系：P28 accepted 后 P31 可处理其余公开字段，不必等待 P30；这只表示任务依赖，不授权并行 Agent、真实额外读取或共享写面的同时修改。
