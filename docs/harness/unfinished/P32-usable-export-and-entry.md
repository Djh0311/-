# P32 易读导出、覆盖报告与使用入口

2026-10-12 后续实施：用户在排除图片后明确“继续做后续工作”。已实现 P32 的独立本地结果入口：`python3 -B -m collection_adapter.p32_result_entry` 无参数定位当前已交付表格、字段说明和缺失清单，核对 manifest 合同及文件状态，失败给固定原因和恢复方法。7 项合成测试通过，当前 11 个结果文件的目录检查通过；未读取业务表正文或重做来源核对。此切片只依赖已交付文件，不要求先证明全店收齐；P29/P31 资格、P32 真实采集入口和整体验收均未提升。使用说明：`docs/harness/p32-local-results.md`；证据：`docs/harness/reports/P32-local-entry-validation.json`。

阶段：stage-06-fields-and-product-acceptance 字段充分性与产品验收
目标：把已取得的数据交付成用户能直接查看的结果，并提供无需自行编写配置的使用流程。
状态：ACTIVE_LOCAL_ENTRY_PARTIAL；本地只读结果入口已实现并核对，统一真实采集流程与整体验收尚未完成。
依赖：完整交付仍依赖 P29、P31；本次独立本地结果入口仅依赖已交付 P31 v7 包，不以它们整体 accepted 为前提，也不解锁真实采集。
来源收据：本会话需求基线及列明依赖的直接验收证据；尚未完成的依赖不算输入。
产品：易读业务表、完整 JSON、字段/商品覆盖说明和明确的启动与恢复步骤。
证据：P32 完成标准中的直接结果及对应验证；不能以文档存在或作者自报代替。
载体：working-copy-only；不 commit、不 push、不发布。

相关权威设计：

- docs/harness/plan.md
- docs/harness/field-coverage-plan.md
- docs/harness/stages/stage-06-fields-and-product-acceptance.md

相关事实：

- 历史 P1 CLI 固定 offline_fake；当前 P31 v7 已交付四张 CSV 和状态清单，本次 P32 增加只读定位入口。

入口：

- collection_adapter/p32_result_entry.py（当前本地入口）

- collection_adapter/runner.py
- collection_core/p1_result_views.py
- collection_core/result_publisher.py

未知：最终业务表拆分依实际商品、规格与优惠关系在实现时冻结。

允许动：

- collection_adapter/
- collection_core/
- contracts/schemas/
- docs/harness/
- README.md
- docs/architecture.md

不许动：

- 本次仅新增本地只读结果入口及说明；不得启动真实采集或将当前继续指令扩成真实运行。
- 复用旧运行锁或额度、自动重试、未明确的网络/UI/系统代理/CA/keychain/凭据/会话/交易操作。
- 原始来源正文、URL、headers、Cookie、值哈希或自由错误进入代码、fixture、报告或 Git。
- 其它 worktree、_archive/、historical_assets/、历史 done/ 原件和 Harness runtime；不 commit、push 或发布。

完成标准：

- 提供统一操作入口与就绪/采集/完成/失败状态，用户不需准备接口、字段或私有脚本；必须手动的页面与系统步骤明确。
- 商品、规格、各类价格和优惠条件清楚表达，业务表与关联说明合理组织；JSON 保留完整可核对结构。
- 真正导出字段缺失原因、商品覆盖、采集时点和未完成项；空值不代替原因，元数据列数不当业务字段数。
- 多表或新格式采用版本化 manifest，无覆盖发布、JSON/CSV 一致与部分失败行为有直接验证。
- 操作说明与实际实现一致，失败给出可操作的下一步；不新增界面自动化、网络权限或发布授权。

后续边界：本地结果入口切片已完成；P32 全任务仍须完整依赖和各项完成证据，涉及真实输入须当次来源事实与明确运行范围。当前命令不提供 start、重采集或自动恢复能力。
恢复：执行 Agent 核对当前指令、依赖和边界后，将本任务移入 leaves/ 作为唯一 current leaf；仅移动任务文件不扩大权限。
