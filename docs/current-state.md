# 当前状态

## 产品结果

2026-10-16 当前：产品结果仍为 incomplete。用户确认数据足够、采集已停（控制根 cleanup=INCOMPLETE、不可再 start），两 latch=CLOSED。P25–P28 均已 accepted 并退场；当前 current leaf 为 P29（分类分页与多观察汇总），P29/P31 与产品整体 incomplete。有效商品数据位于 `runtime-output/p29_pages_313d083fff964939b7d1edc1ccb1bdd7`：去重后 1220 个商品、1318 个规格，其中 1156 个规格有 12–14 位编号、161 个为空；412 个商品有带编号分享链接；44 个分类声明 1039 个商品、其中 14 个分类还有下一页。全店覆盖、完整字段与真实产品验收仍未完成。计划权威见 [plan.md](harness/plan.md) 顶部。

以下为此前 P26/P27 时点快照：P26已取得第一份真实基础商品JSON/CSV/manifest，P27已重新核对三份文件、获准公开标量及用户页面前三张商品卡片。39条分类记录对应31个不同商品；当前列表响应为PARTIAL，全店覆盖、完整SKU、扩展字段与产品验收未完成。

SOURCE_QUALIFICATION=NO_QUALIFIED_SOURCE；PROVIDER_QUALIFIED_FOR_BUILD=false；P02_FORMAL_PARSER=NOT_ENTERED。P26本次具体授权下的监控已结束、accepted并退场，两latch=CLOSED。只处理已观察公开标量，私人分支值保持不解码；实际窗口、次数和latch见[P26当前快照](harness/reports/P26-monitoring-current-status.json)，不提升正式来源或Parser/Provider资格。

## 已有实现与证据上限

- autocapture/ 默认 DISARMED，提供严格策略、有界一次性内存 lease、无值 shape、敏感停止和原子无覆盖发布。
- parser_candidate/ 是隔离候选；保留合成配置及P26 v1。第22次真实观察支持显式v2的poi_info容器、两组FORM编号对应与数值SKU状态类型，旧v1不自动回退。未知枚举不补猜，read/observation绑定继续严格校验，不提升正式Parser。
- collection_adapter/ 提供严格输入合同、纯内存fake、离线CLI、被动bridge及P26准确PID宿主；P25回归已accepted。P26依据新鲜事实建立v2，准备不消费输入/尝试；实际start、两阶段计数、转发分层诊断和关闭独立记录，拒绝旧目标/输入/锁。
- collection_core/ 可将同观察事件组装为P0；P26已真实发布20列基础视图，明确最低SKU展示价、元/CNY、来源proof及PARTIAL，独占目录、manifest最后发布。JSON/CSV逐条一致、manifest关联一致，不表示全店或所有SKU价格已导出。
- Stage 03 已验收合成 P1 的分类、SKU、原价/活动价、优惠、配送和缺失模型。当前 P1 仍限定合成 profile，真实 consumer 只调用 P0。
- 2026-10-08 静态复核确认 P1 当前为 14 个扩展业务字段、120 列 CSV，导出未包含 absence_reason；这不代表六类真实字段已接入。
- contracts/ 提供通用闭合 Schema 及离线扩展、单次运行合同。结构或离线验证通过不提升来源资格或正式 Parser/Provider 定位。

## 历史真实尝试

Stage 04/P17 曾以 LIVE_SOURCE_ENTRY_UNAVAILABLE 零尝试停止。Stage 04R/P21 后来实际消耗一次新鲜尝试，并以 MITMPROXY_BRIDGE_TIMEOUT 关闭；没有 P0 业务表、JSON/CSV 或结果发布。

P21 不能重开。旧 Stage 04S/P23/P24 的计划已原字节保留在 [被替代计划](harness/superseded/2026-10-08/README.md)，它们未被验收完成，也没有新增真实尝试证据。旧文档记载的 mitmdump 版本、代理和页面状态是当时事实，不是本轮直接核验。

更早 CP1/R2B 等实验的工程成果和业务零结果继续按 [历史账本](history/route-ledger.md)引用，不恢复旧来源、票据、执行能力或已耗尽路线。

## 2026-10-08 后续安排

用户已确认沿真实抓包路线，开发者负责技术配置，商品尽量收全、业务字段尽量多。P25已accepted并退场；P26已派发。首次119秒识别关闭后，用户明确改为现场实时监控、配合必要操作，并取消采集时间与尝试次数上限；同一目标公开业务、敏感停止、有界短暂处理及新鲜输入边界继续适用。

- Stage 04T / P25–P27：接入准备与诊断、首份真实基础表和验收。
- Stage 05 / P28–P30：真实商品/SKU/价格关联、分类分页汇总与全店覆盖验收。
- Stage 06 / P31–P33：六类可得业务字段、易用导出/入口和真实产品验收；P31 可在 P28 accepted 后开始，不必等待 P30。

P25、P26、P27、P28均先reported再依直接证据accepted并退场，Stage 04T完成；当前 current leaf 为 P29（分类分页与多观察），P29/P31 active/incomplete，P30、P32 真实采集入口、P33 未启动（P32 本地结果入口已实现）。第22次识别确认当前店名、poi_info容器：两份FORM的poi_id_str分别等于响应公开字符串编号，wm_poi_id分别等于响应整数id的文本形式。结果第2次于2026-10-09T05:11:14.482068至05:11:27.279861 UTC以新鲜输入发布39条记录，原始HTTP回调3、业务响应2、合格事件2、解析/发布各39。两latch=CLOSED、清理及输出完整、退出0，累计识别22/结果2；P27增加零真实尝试。首个结果失败、第20次转发干扰及其UNKNOWN根因保留原收据；状态见快照。

新增v2与分类重复关系反例后，25项结果/候选配置专项通过；2026-10-09T05:04:59.639 UTC Harness按改动选测Parser、Adapter、Core均PASS，含P25。默认解释器两项引擎测试跳过，已在实际引擎解释器另行通过。相关AST、闭合Schema元模式、实际结果六份对象Schema及23项直接核对通过；未保存raw/私人值。局部与真实首表通过都不表示产品整体完成。

P27对实际文件重新计算34项检查、公开标量交叉核对8项、字段及回归复查12项，并按用户提供截图核对前三款。初始核对清单第三项选错商品，已用实际文件与卡片位置纠正，没有改写业务结果；原未出现在截图中的商品仍未做页面核对。实际已有输出预检返回RESULT_TARGET_EXISTS，文件元数据未变。交付及范围见[P27报告](harness/reports/P27-delivery-report.md)，直接验收见[P27证据](harness/reports/P27-direct-acceptance.json)。本次只修改验收和状态文档，没有更改业务代码或重跑整项目测试。

总计划见 [harness/plan.md](harness/plan.md)，字段口径见 [field-coverage-plan.md](harness/field-coverage-plan.md)。旧结果不改写，新任务只由实际验收解锁。

## 未知与待验证

- 当前基础最低展示价逐条满足商品min_price=渲染min_price=最低SKU.price；元/CNY依据用户当次页面确认，没有伪造响应币种字段。P27有用户当前页面附件的三个可见样本，不声称与抓包同一时点或核对全部商品；正式来源资格证据仍未取得。
- 第22次已确认目标的684项路径/类型定义包含容器、技术键与未知字段；9项基础来源字段已导出，5项已确认可得但未导出，669项待确认、1项URL投影拒绝，另2项受限键只留元数据。六类候选不能当684项已确认公开业务字段。
- 时钟刷新、取消清理、尝试计数等直接问题有P25回归；P26转发异常、固定诊断、同店/同观察与发布均有直接证据。第20次具体加载干扰根因UNKNOWN。
- 本次准确PID、内核stream门禁、公开店名和两组FORM关系均已查证。后续新鲜运行仍须本次目标/观察门禁，不要求用户提供接口、字段路径或Cookie。
- 全店覆盖、真实扩展字段、多目标、简化用户入口和产品最终验收：未完成。
- 临时CA文件已删除；用户手动移除曾导入信任仍待确认，安装组件未声称已卸载。采集关闭与组件卸载分别记账。

失败收据只结束一次尝试；缺真实结果或覆盖依据时产品仍incomplete。本次代码、实际监控与直接收据见[P26报告](harness/reports/P26-delivery-report.md)。开发者只读进入了本次扩展的系统设置详情诊断，没有自动操作微信/浏览器、修改keychain/系统代理或进行Git写入/发布。本次CA与新增组件安装有独立具体授权；现场监控没有提升正式Parser/Provider资格。
