# P30 全店商品覆盖验收

阶段：stage-05-real-sku-and-store-coverage 真实规格关联与全店覆盖
目标：用分类、页面、商品和 SKU 的直接证据判断目标店铺是否收齐。
状态：PLANNED_NOT_STARTED；本轮只修改计划，下列写面和行为仅描述后续明确授权的实施范围。
依赖：P29
来源收据：本会话需求基线及列明依赖的直接验收证据；尚未完成的依赖不算输入。
产品：全店覆盖核对结论，包含总量依据、结束依据和未完成项。
证据：P30 完成标准中的直接结果及对应验证；不能以文档存在或作者自报代替。
载体：working-copy-only；不 commit、不 push、不发布。

相关权威设计：

- docs/harness/plan.md
- docs/harness/field-coverage-plan.md
- docs/harness/stages/stage-05-real-sku-and-store-coverage.md

相关事实：

- 单页非空、采集时长或一次无新商品都不能单独证明全店完整。

入口：

- collection_core/result_publisher.py
- docs/harness/field-coverage-plan.md

未知：来源可能没有可核对总数；需要其它充分的分类与页终止依据，否则为 UNKNOWN。

允许动：

- docs/harness/
- docs/current-state.md
- README.md

不许动：

- 本轮启动实现或真实采集；未来实现指令也不自动授权超出当次范围的真实运行。
- 复用旧运行锁或额度、自动重试、未明确的网络/UI/系统代理/CA/keychain/凭据/会话/交易操作。
- 原始来源正文、URL、headers、Cookie、值哈希或自由错误进入代码、fixture、报告或 Git。
- 其它 worktree、_archive/、historical_assets/、历史 done/ 原件和 Harness runtime；不 commit、push 或发布。

完成标准：

- 逐项核对分类/页清单、终止依据、商品/SKU 去重和遗漏；来源提供总数时对齐其统计口径。
- 完整声明有充分事实依据；缺页或依据不足标 PARTIAL/UNKNOWN，保持对应产品目标 incomplete。
- 多页记录保留各自观察身份，分类关系不丢失，字段不跨观察拼接。
- 记录真实覆盖范围、检查方法和残留问题；有未完成范围时不解锁全店完成的最终验收。

等待：后续实施指令及列明依赖 accepted；涉及真实输入时还须当次来源事实和明确运行范围，计划不代替它们。
恢复：执行 Agent 核对当前指令、依赖和边界后，将本任务移入 leaves/ 作为唯一 current leaf；仅移动任务文件不扩大权限。
