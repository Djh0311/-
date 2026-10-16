# P33 真实产品验收

阶段：stage-06-fields-and-product-acceptance 字段充分性与产品验收
目标：按真实结果检查商品覆盖、字段充分性、数据正确性和可操作性是否满足用户需求。
状态：PLANNED_NOT_STARTED；本轮只修改计划，下列写面和行为仅描述后续明确授权的实施范围。
依赖：P30, P31, P32
来源收据：本会话需求基线及列明依赖的直接验收证据；尚未完成的依赖不算输入。
产品：逐需求真实验收记录与准确的产品完成或未完成结论。
证据：P33 完成标准中的直接结果及对应验证；不能以文档存在或作者自报代替。
载体：working-copy-only；不 commit、不 push、不发布。

相关权威设计：

- docs/harness/plan.md
- docs/harness/field-coverage-plan.md
- docs/harness/stages/stage-06-fields-and-product-acceptance.md

相关事实：

- 离线通过、一次运行退出或计划文件齐全不等于产品完成。

入口：

- docs/harness/plan.md
- docs/harness/field-coverage-plan.md

未知：未出现或未允许验证的目标/场景须明确保留为未验证。

允许动：

- docs/harness/
- docs/current-state.md
- docs/qualification-status.md
- README.md

不许动：

- 本轮启动实现或真实采集；未来实现指令也不自动授权超出当次范围的真实运行。
- 复用旧运行锁或额度、自动重试、未明确的网络/UI/系统代理/CA/keychain/凭据/会话/交易操作。
- 原始来源正文、URL、headers、Cookie、值哈希或自由错误进入代码、fixture、报告或 Git。
- 其它 worktree、_archive/、historical_assets/、历史 done/ 原件和 Harness runtime；不 commit、push 或发布。

完成标准：

- P30、P31、P32 均已 accepted；对真实商品/SKU/价格/优惠/配送、覆盖与缺失说明逐项核对。
- 在分别明确范围的目标和场景下验证多规格、促销、售罄、缺字段、分页与操作恢复；没有证据的项目不写通过。
- 确认已知可得字段没有被静默漏掉、部分店铺范围没有被标完整、用户无需自行配接口和字段。
- 将产品结果与来源资格、正式 Parser/Provider、宿主状态和发布权限分别陈述；残留需求缺口时维持 productResult=incomplete。
- 交付准确使用说明和遗留问题；不因阶段收尾 commit、push、发布、删除历史或再开真实来源。

等待：后续实施指令及列明依赖 accepted；涉及真实输入时还须当次来源事实和明确运行范围，计划不代替它们。
恢复：执行 Agent 核对当前指令、依赖和边界后，将本任务移入 leaves/ 作为唯一 current leaf；仅移动任务文件不扩大权限。
