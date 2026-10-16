# P29 分类分页、多观察汇总与去重

2026-10-16 工作投影：用户“继续”对应已有详情副本的缺口核对。87 条路径已归类，营业时间和完整优惠规则在这份副本中没有独立路径，配送补了 6 个来源标量。证据见[报告](../reports/P31-detail-gap-review-2026-10-16.md)。complete=false、productResult=incomplete。未操作接收器、网络/UI、latch 或系统配置。以下为历史记录。

2026-10-16 此前工作投影：用户“开始吧”对应副本持续处理。单份可隔离错误不再停掉整个分析器，诊断用 `recovery` 区分仍在接收和已经停止。证据见[报告](../reports/P29-copy-continuation-2026-10-16.md)。适配层 580 项与核心 58 项为合成证据。complete=false、productResult=incomplete。未操作接收器、网络/UI、latch 或系统配置。真实复现验收本轮不启动。以下为历史记录。

2026-10-15 工作投影：本轮用户“开始做”对应先整理既有数据的 P31_FIELDS 切片，已导出窗口34详情并按两种公开门店编号关联窗口30商品交付；直接验收见[报告](../reports/P31-store-detail-export-2026-10-15.md)及[核对记录](../reports/P31-store-detail-export-direct-check-2026-10-15.json)。该局部结果已核对，不推进P29/P31整体accepted，complete=false、productResult=incomplete。未操作接收器、网络/UI、latch或系统配置；实时运行状态未查。后续缺口是采集器持续处理与真实复现验收，本轮不启动。以下为历史记录。

2026-10-14 当前：用户确认地址页已打开，窗口33的门店详情请求返回HTTP 200且响应完成，0传输失败；此前失败根因仍未知。查明详情路由原先只转发、未复制正文，现已补公开详情副本独立保存：只选已观察的POST /weapp/shop/v1/poi/detail，不复制详情请求正文，不读取私人分支值，不推断店铺关联或混入商品表。569项适配层经两套解释器互补通过，核心58项通过。窗口33已完整清理，窗口34于17:49:19 UTC接替，PID60732、网络PID46630，ACTIVE、接受副本且详情副本功能enabled，两latch=OPEN，无截止时间，保持开启。窗口34已于17:53:08 UTC保存并核对1份详情公开副本（69个标量条目），当前所选店名一致，地址、公开电话、配送时段、服务说明、门店标签和公告均非空；HTTP 200且根code为ZERO，传输失败/跳过/丢弃均0，接收继续开启。见 docs/harness/reports/P29-window34-detail-copy-direct-check.json；旧231行及55行结果保留，分类无需重刷。无自动重试或系统配置修改，P29/P31及产品仍incomplete。见 docs/harness/reports/P29-window30-export-and-window31-recovery-2026-10-14.md。以下为历史时点。

2026-10-14 当前：用户明确要求保持开启，窗口30已按一次持续接收启动，无会话截止时间，接收器71734、准确网络PID46630、两latch=OPEN。不以两分钟、等待反馈或聊天结束主动停机，不自动重试。39项相关用例互补通过，启动业务输入0，P29/产品仍incomplete。当前根与控制方法见 docs/harness/reports/P29-continuous-receiver-window30-2026-10-14.md；以下关闭状态属于旧窗口。

2026-10-14 当前：窗口29按用户“继续采集”完成120秒/1次试采，新增商品0；6个上游连接成功，目标TLS hello和HTTP输入0。宿主退出、锁清理、拦截解除，两latch=CLOSED；无程序修改。当前等待本轮重进页面事实，不自动重试，不借窗口28页面反馈提升本轮结论。P29及产品仍incomplete。见 docs/harness/reports/P29-window29-trial-result-2026-10-14.md。

2026-10-14 最新：启动故障已修复，窗口28完成120秒/1次试采并正常清理。用户反馈页面正常，目标商品响应、完整观察与新增数据均0；两latch=CLOSED。已有连接/TLS计数已接回状态输出，最终38项相关用例互补通过，未据此提升真实采集结论。窗口26意外应用更新已披露并加上复用已有组件保护。下一轮入流核对已询问用户，尚未启动；当前P29/P31与产品仍incomplete。证据：docs/harness/reports/P29-forwarding-startup-and-window28-2026-10-14.md。以下为历史状态。

2026-10-13 本轮用户选择“接管之后原样转发回去”，当前聚焦代理转发可靠性。已复现并修复分离解析模式下单连接故障关闭整个转发窗口的问题：拒绝不完整副本，保留其他连接转发；原正文块返回行为保留。适配层541项互补覆盖、核心58项通过，仅为离线证据。旧CLI/serve/launch/start仍停用，没有新采集或latch变化，不宣称窗口25加载故障或风控已解决，P29/P31保持incomplete。证据：docs/harness/reports/P29-forwarding-fault-isolation-2026-10-13.md。以下无接管副本源方向为历史事实，不覆盖本轮选择。

2026-10-13 最新约束与改动：用户确认停采后页面恢复，并明确要求只拿副本、把程序改好。已删除P26/P29旧代理宿主的网络启动执行体与控制器创建接收器路径；旧CLI和start均在触碰运行环境前拒绝，返回P29_COPY_SOURCE_UNAVAILABLE，保留status/stop清理与离线解析导出。真实旁路副本来源尚未接通，因此目前不能恢复采集，不能宣称程序整体修复完成；不退回PID中间代理、不自动启动真实能力。539项适配层用例经两套现有解释器互补通过，仅为离线证据。详见 docs/harness/reports/P29-copy-only-entry-retirement.md。

2026-10-13 窗口25因用户报告加载失败立即停止：11:03:04 UTC关闭，宿主95123退出、锁消失、cleanup=COMPLETE、拦截清除、活动流0、两latch=CLOSED、诊断输出完整。实际尝试1，目标TLS hello0、HTTP请求/响应0、原文回调0、完整观察0；副本分析无失败，未触发结构预算，故此次未取得结构预算子因证据。39个非目标TLS hello和97个上游连接建立不能证明页面成功或转发无影响。停止后准确网络PID46630重新只读核对通过；加载失败根因UNKNOWN，不归因于正文解析，也不据零错误计数排除代理链路问题。当前已请用户在采集关闭状态正常重进一次确认是否恢复，不开启新采集或自动重试；旧231行和6条优惠导出保留。证据：docs/harness/reports/P29-window25-load-failure-stop-check.json、P29-window25-close-receipt.json、P29-window25-final-copy-analysis.json、P29-window25-final-http-progress.json。

2026-10-13 窗口25已实际启动：用户确认单目标首页后重新预检通过，网络PID46630、宿主95123，独立根runtime-output/p29_pages_e1862047da8d4883932e21cc73902d24；先PREPARED零尝试，再于2026-10-13T10:56:34.191420+00:00单独start，引用result:8116bdc030bb4d9a9596d5d91585ea14，本窗实际尝试1、两latch=OPEN。启动时完整观察0，接收开启不代表真实页面或来源已验证。当前先等待用户重进原店加载新鲜初始列表，核对后再打开店铺详情；不遍历分类，触限或页面异常停止，不自动重试。证据：docs/harness/reports/P29-window25-preflight.json、P29-window25-receiver-ready.json、P29-window25-started.json、P29-window25-current-status.json。

2026-10-13 用户已明确授权一次小范围结构预算验证，仅重进同店并打开店铺详情，不遍历分类。窗口25独立新根runtime-output/p29_pages_e1862047da8d4883932e21cc73902d24已建立；当前网络PID46630、父进程46626及固定CA只读复核通过，窗口24宿主已退出。当前等待用户只保留目标小程序并停在首页；接收器未启动、实际尝试0、两latch=CLOSED。使用新增闭合无值细分诊断，原预算不变；触限或页面异常停止，不自动重试，未知路由仍只做安全元数据核对，不放行正文。证据：docs/harness/reports/P29-window25-preparation.json。

2026-10-13 按用户继续指令完成结构预算诊断补丁，未放宽任何采集限制。判断：旧P26_STRUCTURE_BUDGET合并多种触发项导致无法定位（怎么确认的：代码中的节点、深度、字段定义、受限字段定义、公开标量及跨响应目录均共用该码；两项合成先行测试证明异常不含细分原因）。新增闭合无值structure_budget细节，记录dimension/stage/observed/limit，经BodyCollector、初始配对、分类解析传到副本分析快照，沿现有P29_COPY_ANALYSIS_STATUS状态及停机事件输出；旧状态合同不变，副本诊断增加可选闭合对象。7项针对性测试通过，适配层535项在基础解释器530通过/5缺引擎跳过，现有引擎解释器补齐5项通过。原始块转发不变、触限仍停副本、原产物保留；无真实网络/UI/采集、无新尝试、窗口24仍关闭。旧窗口具体触发项仍UNKNOWN，不能据此宣称实际停采原因已定位或修复。下一步须新的获准有限观察才能取得具体触发项；不自动重试、不重滑已覆盖分类。证据：docs/harness/reports/P29-structure-budget-diagnostic-validation.json；说明：docs/harness/reports/P29-structure-budget-diagnostic-implementation.md。

2026-10-13 用户优惠弹层截图促成真实漏项核对：三条页面优惠文案均已存在窗口24 FOOD公开投影的poi_info.poi_normal_tags[].sub_tags[].text，但既有四表均未导出，不能继续把它们仅标为来源未知。按test-first先证明旧路径丢失4条合成嵌套标签，再新增隔离p31_store_promotions解析/独立导出及两份闭合合同。保留group_index/tag_index、空/null/未观察差异、门店归属及自身请求/时点，不处理购物车分支，不推断领券资格、有效期或叠加性。新增独立目录p31_store_promotions_58e544c8116b4eec8836cd500eb32e03导出6条标签，JSON/CSV/manifest三文件0700/0600；自身公开坐标逐条、CSV逐格与manifest核对通过。16项新旧相关测试通过，旧231行四表和全部旧版本未改。无新网络/采集、未改结构预算或系统配置、未提交Git。当前仍缺店铺详情地址等网络输出及结构预算具体子因；截图确认的是配送时段，不是营业时间。证据：docs/harness/reports/P31-window24-store-promotions-direct-check.json；说明：docs/harness/reports/P31-store-promotions-implementation.md。

2026-10-13 用户提供店铺详情截图，页面可见公开地址、服务设施及明确标为配送时间的时段；截图仅作页面证据，不将配送时间改称营业时间，不把截图值填入网络来源行。打开详情前后新增安全路由模板为comment/poi及shoppingcart/refreshdata，未建立专用详情响应来源，不放行未知或私人正文。状态检查发现副本分析已以P26_STRUCTURE_BUDGET关闭，具体节点/深度/字段子因UNKNOWN，跳过头部12；转发仍ACTIVE且HTTP46完成/0失败。立即发送stop，10:28:20 UTC正常关闭，宿主87827退出、锁消失、拦截清理、stream0、cleanup=COMPLETE、两latch=CLOSED。已收到的22份分类和初始公开投影保留，独立导出p31_context_codes_54d18c555807482e80945991d34e4b0b：商品231行/153商品/198SKU/19类，门店1、文本104、代码96。四组JSON自身来源重算、CSV逐格、字典/覆盖/manifest及0700/0600核对通过；旧结果不覆盖，截图未混入，门店详情/公开优惠/配送范围仍未完成。接下来可先核对用户提供的公开活动页面证据，不要求重新滑分类；未启动新采集或修改预算/代码/系统设置。证据：docs/harness/reports/P29-window24-close-receipt.json、P29-window24-final-copy-analysis.json、P29-window24-final-http-progress.json、P31-window24-fields-export-receipt.json、P31-window24-fields-direct-check.json。

2026-10-13 窗口24分类阶段声明范围已覆盖：用户完成浏览后核对22份自身分类投影与新鲜初始列表，合并231行/153商品/198SKU/19分类，初始143有序+33折叠共176分类商品关系均有正文，缺失0、额外0；不宣称未声明或未来商品完整，不将旧窗口值补入本次。当前HTTP33响应完成/0HTTP失败，副本分析无失败/积压/跳过/丢弃；另有1次非目标上游连接失败，目标连接失败0，页面影响未知。窗口继续ACTIVE、本窗尝试仍1；无需继续重复分类，下一步按实际可见的商家/门店信息入口观察公开门店信息及新增安全路由元数据，再处理公开优惠与配送。未知路由正文仍不放行，图片和私人值排除。证据：docs/harness/reports/P29-window24-received-coverage-check.json。

2026-10-13 窗口24已收到并核对一组新鲜店铺/列表输入：47行、19分类，初始同店自身关联通过。当前分类编号、名称和顺序与窗口23一致，未沿用窗口21旧序号；第1和第5类声明关系已齐，其余分类仍有普通或折叠正文缺口。初始声明143有序+33折叠，缺109有序+33折叠，折叠引用不证明页面有展开控件。当前HTTP10响应完成/0失败，副本分析无失败/积压/跳过/丢弃；窗口继续ACTIVE，本窗实际尝试仍1。下一步用户按当前页面顺序浏览第2至4及第6至19类，等各类加载并看至本类末尾，仅在实际看到展开入口时操作；列表后继续核对公开门店/优惠/配送页面，不把列表完成当全部任务完成。证据：docs/harness/reports/P29-window24-initial-coverage-check.json。

2026-10-13 窗口24已启动：用户确认单目标首页后重新预检通过，网络PID46630、宿主87827，新根runtime-output/p29_pages_a20c00a2b8c34da09b76212f9e3764f8。先PREPARED零尝试，再于2026-10-13T09:49:01.007968+00:00单独start，引用result:25fd7a7b580c49f587ff74f43e5167e3，本窗实际尝试1、两latch=OPEN，开始时完整观察0。授权覆盖同店全部分类缺口及公开门店/优惠/配送信息；当前先等待用户进入原店加载新鲜列表，据当次分类编号/名称确认缺口后再给页面指示，不沿用旧序号或猜可见展开。未知路由先无值元数据，不直接放行正文；无图片、私人值、自动UI、重试或系统配置变更。证据：docs/harness/reports/P29-window24-preflight.json、P29-window24-receiver-ready.json、P29-window24-started.json、P29-window24-current-status.json。

2026-10-13 用户明确授权下一轮扩大为同店全部分类缺口及公开门店、优惠、配送信息。窗口24独立新根runtime-output/p29_pages_a20c00a2b8c34da09b76212f9e3764f8已准备；当前网络PID46630、父进程46626和固定CA只读核对通过，窗口23宿主已退出。当前等待用户单目标小程序停在首页，接收器未启动、实际尝试0、两latch=CLOSED。新鲜初始列表到达后按分类编号/名称重核当前排序与缺项；不根据folded引用猜测可见展开入口。新增门店/优惠/配送路由先核对无值元数据与公开范围，再决定必要适配；不直接放行未知正文。图片、私人值、自动UI、重试、系统设置变更仍排除，加载异常或验证立即停止。证据：docs/harness/reports/P29-window24-preparation.json。

2026-10-13 按用户继续指令完成当前缺口定位：窗口21与23的19个分类编号和名称全部匹配，但排序改变，旧12→当前2、旧13→当前3、旧10→当前12。窗口23当前声明仍缺58有序+33折叠分类商品关系，不等于91个不同商品，也不证明页面有展开按钮。当前公开投影经现有六类字段管道验证得到131行/79商品/119SKU、门店1行、公开文本104行、代码96行；本轮仅内存核对，未发布新业务表。地址字段仍为空，费用/时效/状态等已有自身来源值但含义或适用条件未确认；专用营业时间、公开券规则、活动有效期/叠加及公开配送范围仍缺来源事实。后续应按当前分类身份补列表缺口，并界定公开门店/活动/配送输入；未知路由先看无值元数据，不直接读取正文。窗口23关闭且不复用；本轮无新网络/UI/系统配置/代码/Git操作。证据：docs/harness/reports/P29-P31-window23-current-gap-mapping.json。

2026-10-13 窗口23已关闭并纠正页面指示。用户指出当前第12类没有展开入口；代理此前未观察页面，却沿用历史序号/折叠缺口指示展开，不能作为当前事实。09:31:27 UTC受控stop，宿主83918退出、锁消失、cleanup=COMPLETE、intercept_cleared=true、active_streams=0、两latch=CLOSED。当前一组初始输入和4份分类公开投影自身验证通过，合并视图131行；当前第12类声明15有序关系、0折叠，15个商品均有正文，缺失0。未核对当前第12类与旧目标的身份对应，不把本次序号当历史同类。HTTP18完整/0失败，副本解析失败空、积压/跳过/丢弃0；这些传输事实不等于用户确认页面正常。本窗实际尝试1，已发布结果保留，不要求用户继续寻找展开入口，不自动重启。证据：docs/harness/reports/P29-window23-close-receipt.json、P29-window23-correction-and-close-check.json。

2026-10-13 窗口23已按本次单独授权启动。用户确认单目标小程序停在首页，重新预检通过；新根runtime-output/p29_pages_b1e58c01304b4682a900c0e14ba2d071、网络PID46630、宿主83918。先就绪零尝试，再于2026-10-13T08:40:12.670738+00:00单独start，引用result:3275890babe04f55b715f29ecacefe77，本窗实际尝试1、两latch=OPEN。首次状态为ACTIVE，副本分析接收开启、失败空、积压/跳过/丢弃均0，但网络流和业务响应也为0，不能据此证明实际页面加载正常。当前等待用户进入原店，列表加载后展开第12类；按新鲜初始身份与目标响应核对，不跨窗补值。目标完成、加载异常或验证即关闭，不自动重试。证据：docs/harness/reports/P29-window23-preflight.json、P29-window23-receiver-ready.json、P29-window23-started.json、P29-window23-current-status.json。

2026-10-13 用户已明确授权一次同店转发验证和第12类折叠补采。窗口23新根已建立，当前网络PID46630、父进程46626及固定CA只读核对通过；仅沿用既有运行配置，不扩大本次一次尝试授权。当前等待用户仅保留目标小程序并停在首页；接收器未启动、实际尝试0、两latch=CLOSED。取得当前页面事实后重新预检，先就绪再单独start；只接收同店新鲜初始列表及第12类目标输入，加载失败、验证或目标核对完成即关闭，不自动重试。图片、私人值、自动UI和系统设置变更均排除。证据：docs/harness/reports/P29-window23-preparation.json。

2026-10-13 当前用户明确要求先完成转发/解析分离改动。已在P29真实入口接入有界内存副本队列和单独串行解析线程：请求/响应流回调返回原始bytes，不等待解压、解析、校验或结果写入；解析状态与转发状态分开。解析拒绝/失败、忙或积压不会自动关闭转发；跳过或丢弃副本单独记不完整。stop先清除拦截与连接，再离线收尾正在执行的有界解析，丢弃排队副本后给关闭收据。保留来源接收时点、门店请求关联、原有大小/时效/隐私限制。16项新测试含2项旧行为语义红；适配层525项用例由现有两套解释器互补覆盖通过，语法及git diff --check通过。未启动真实采集/网络/UI，未改系统配置或Git提交；窗口22仍关闭。当前改动完成且仅获离线验证，不证明实际微信加载恢复，不改变P29/P31整体验收或来源资格。仍使用现有PID中间代理，没有实现重定向前网络分流。证据：docs/harness/reports/P29-detached-analysis-validation.json；实现说明：docs/harness/reports/P29-detached-analysis-implementation.md。

2026-10-12 窗口22因用户报告加载失败并要求停机而关闭：16:40:11 UTC stop，宿主29076退出、锁消失、cleanup=COMPLETE、intercept_cleared=true、active_streams=0、两latch=CLOSED；本窗1次实际尝试，完整观察0、分类响应0，无新商品交付。15个HTTP响应完成及失败计数0不能证明页面正常，也不能排除采集器影响。当前任务转为只读分析转发/分流架构，不重新采集或改代码。判断：当前local PID重定向先让指定小程序网络进程连接进入代理，再按TLS域名选择解密；非目标TLS及UDP走不解密转发，仍依赖代理（怎么确认的：p26_identification_host.py:891、1009、572、586及本窗关闭诊断）。真正非目标绕过需在重定向前筛选，不能用解析接口白名单或ignore选项冒充。加载失败根因UNKNOWN。证据：docs/harness/reports/P29-window22-load-failure-stop-check.json、P29-window22-flow-routing-readonly-review.json。

2026-10-12 窗口22已获新授权并启动：用户明确同意仅补同店第12类展开商品。当前父进程46626、网络PID46630及固定CA复核通过；新根runtime-output/p29_pages_383add39cdf84889a075d57287fbb8b2，独立控制引用，宿主29076。先PREPARED零尝试/两latch=CLOSED，再于2026-10-12T16:38:03.031135+00:00单独start，窗口result:4f1d37e32aaf49f0be9d4c0cdfb8ac75，本窗实际尝试1、两latch=OPEN、初始业务输入0。已请用户回小程序首页重新进入原店，列表加载后展开刚才第12类；收到新鲜初始列表后核对分类身份，只验收对应缺项。不提前按用户完成口述关闭，先核对目标正文；异常则立即关闭。无自动UI/重试/系统变更/图片/私值，旧窗口和交付保留。证据：docs/harness/reports/P29-window22-preflight.json、P29-window22-receiver-ready.json、P29-window22-started.json。

2026-10-12 用户补充：第12类在窗口21结束前未点展开，现已点击。已只读复核窗口21仍CLOSED、宿主退出、锁不存在、分类输入仍9份；当前点击不在采集期间，不能记为已收到。既有第12类仍缺3个折叠关系。下一步若补当前正文，仅需一次同店新鲜初始列表及第12类展开的定向窗口；窗口21限定一次且已关闭，不重开旧根、不自动启动，等待新窗口授权及随后必要页面操作。其余已交付文件保持不变。证据：docs/harness/reports/P29-window21-category12-user-action-fact.json。

2026-10-12 窗口21已关闭并核对：用户报告页面有“已经到底了”一类提示，记为本次访问可见末尾的用户证据，不等于协议终止或全店收齐。16:19:33 UTC stop后宿主90436退出、锁消失、cleanup=COMPLETE、拦截清理、两latch=CLOSED、active_streams=0；HTTP20完成/0失败/0未完成。本窗9份分类投影自身证明通过，独立导出139行、105商品、119 SKU、16个有记录分类（初始声明19类）；四表CSV/JSON、字段字典、覆盖及manifest重算核对通过。第13类26有序+4折叠及第19类13有序关系均齐；第12类7有序已齐，仍缺3折叠。本轮定向范围以外不重采，不跨窗补记录，旧233行确认单位交付保留。已询问用户刚才第12类是否展开，仅待动作事实，不要求重复操作；不自动新建窗口。P29/P31仍未整体accepted。证据：docs/harness/reports/P29-window21-user-terminal-fact.json、P29-window21-close-direct-check.json、P29-window21-received-coverage-check.json、P31-window21-fields-direct-check.json。

2026-10-12 窗口21初始列表核对通过：55行、30商品、41 SKU、19分类；当前初始声明155有序及22折叠关系。原第12/13/19类在新鲜列表中的身份、标签、序号及各自声明集合均与窗口20相同，未将旧业务值补入新记录。已请用户展开第12/13类并等待加载，再查看第19类末尾及可见终止提示。窗口21保持ACTIVE、实际尝试1，无再次start；该定向窗口不作为全店当前快照，平台终止仍UNCONFIRMED。证据：docs/harness/reports/P29-window21-initial-coverage-check.json。

2026-10-12 窗口21已启动：用户确认目标小程序首页后，重新prepare通过，接收器90436先核对PREPARED/零尝试/两latch=CLOSED，再于2026-10-12T16:03:28.783696+00:00单独start。窗口引用result:4c55c792ee1a42caa0a07f75f92ff63e，本窗结果尝试1，启动收据两latch=OPEN、业务输入0、完整观察0。现等待用户进入原店加载初始列表，随后按新鲜分类身份核对原第12/13类折叠项及第19类末尾。一次定向窗口，不跨窗补字段、不宣称全店当前完整，不自动重试；再次验证或网络异常立即停止。代码和系统配置未修改。证据：docs/harness/reports/P29-window21-receiver-ready.json、docs/harness/reports/P29-window21-started.json。

2026-10-12 用户补充：上次跳验证前未滑到最底部，因此窗口20没有末页终止证据。按用户重启微信恢复后明确继续原工作的指令，准备窗口21的一次同店定向观察；目标仅新鲜初始列表、第12/13类折叠项和第19类末尾，实际分类序号须按新鲜身份核对。新根及控制引用已建立，重查当前父进程46626、网络进程46630与固定CA通过；当前等待用户停在目标小程序首页，接收器未启动、两latch=CLOSED、尝试0。不复用旧根、不跨窗补记录，不把定向窗口当作全店当前完整快照。若再次报告验证则关闭，不自动重试。证据：docs/harness/reports/P29-window20-user-terminal-fact.json、docs/harness/reports/P29-window21-targeted-preparation.json。

2026-10-12 恢复原计划工作：用户报告重启微信后恢复，故障根因仍 UNKNOWN。窗口20保持关闭，未开启新采集。中断前15份分类投影及初始观察已核对并独占导出220行、144商品、189 SKU、19分类；四表CSV/JSON、字段字典、状态清单及manifest核对通过。当前缺12个声明关系：第12类折叠3、第13类折叠4、第19类有序5；旧窗口有这些历史记录，但不跨窗补成当前记录。新旧无新增商品/SKU，215个共有键价格数值一致；第2类声明关系新增/移出各3个，形成5个新分类商品SKU键。旧233行人民币元交付保留。当前等待用户补充验证前是否到第19类末尾及终止提示，不要求重做页面操作。证据：docs/harness/reports/P31-window20-fields-direct-check.json、docs/harness/reports/P29-window20-membership-change-review.json。

2026-10-12 窗口 20 已停止：用户报告滑动过程中跳转验证中心，开发者立即通过本窗口自有 FIFO 发送 stop。已核对宿主 49678 退出、host-active.lock 消失、cleanup=COMPLETE、intercept_cleared=true、两 latch=CLOSED；实际结果尝试仍为 1，没有重试或开启新窗口。验证出现以用户报告为依据，具体触发原因 UNKNOWN；未操作验证页面或读取验证正文。已发布的 54 行初始结果和此前窗口 19 交付保留，全店分页终止仍未确认。当前无页面采集任务，不继续要求滑动，不扩展 P32。关闭证据：`docs/harness/reports/P29-window20-verification-stop-check.json`、`docs/harness/reports/P29-window20-close-receipt.json`、`docs/harness/reports/P29-window20-output-receipt.json`。

2026-10-12 窗口 20 已实际启动：用户单独授权本次同店公开列表/分类分页采集，并确认只保留目标小程序停在首页。新根 `/Users/yoyi/爬虫/runtime-output/p29_pages_5d1758a4492b46adaa43c7d28d51ebac`，引用 `result:95603d43ee81435d9923a0033e8b1d56`，准确网络 PID 42372、宿主 49678；重新核对进程/固定 CA 后先准备零尝试，再于 `2026-10-12T13:04:26.249917+00:00` 单独 start。本根结果尝试 1，P29 历史累计结果 20；两 latch=OPEN，启动时业务输入/发布均 0，source_ready=UNKNOWN。现等待用户进入同店加载初始列表，再按本窗口声明集合核对分页；不重开旧根、不复用旧输入，不采图片/私人值，不改系统配置、不自动 UI 或重试。当前焦点为 P29，不扩展 P32。证据：`docs/harness/reports/P29-window20-preflight.json`、`docs/harness/reports/P29-window20-receiver-ready.json`、`docs/harness/reports/P29-window20-started.json`。

2026-10-12 当前计划工作：回到 P29/P31，不继续扩展 P32 入口。按最新指令重核 27 组需求，人民币元已确认、图片已排除，不再列为缺口；已有来源值的语义未知不等于解析漏项。窗口 19 声明的 177 个分类商品关系缺失为 0，平台终止仍未确认，分类候选资格不自动提升。用户已单独授权一次同店公开列表/分类分页补采；窗口 20 新根已准备，当前等待用户确认仅保留目标小程序并停在首页，尚未启动接收器或采集，两 latch=CLOSED、实际尝试 0。证据：`docs/harness/reports/P29-P31-remaining-work-review.json`、`docs/harness/reports/P29-window20-authorization.json`。

2026-10-12 后续实施：用户在排除图片后明确“继续做后续工作”。已实现 P32 的独立本地结果入口：`python3 -B -m collection_adapter.p32_result_entry` 无参数定位当前已交付表格、字段说明和缺失清单，核对 manifest 合同及文件状态，失败给固定原因和恢复方法。7 项合成测试通过，当前 11 个结果文件的目录检查通过；未读取业务表正文或重做来源核对。此切片只依赖已交付文件，不要求先证明全店收齐；P29/P31 资格、P32 真实采集入口和整体验收均未提升。使用说明：`docs/harness/p32-local-results.md`；证据：`docs/harness/reports/P32-local-entry-validation.json`。

2026-10-12 最新范围：用户明确“图片跳过”。图片下载、保存、图片标识及引用导出均移出当前交付范围，不再计入未完成项或验收缺口；不启动图片合同或解析实现。已有公开标签文字和业务结果保留。当前价格和费用均已确认为人民币元；其余语义、来源资格及全店覆盖结论不因本次范围调整而改变。

2026-10-12 用户已确认当前价格和费用均为人民币元：新版商品 233 行均标注 CNY/YUAN，初始 55 行原依据保留，178 行补明确用户确认依据；门店费用一并标注。金额及其它旧业务值不变，确认前状态另存；确认仅绑定当前既有结果，不能自动套用未来输入。65 次相关测试和逐行核对通过，旧 v6 十个数据文件重算一致。当前币种/元单位不再作为待用户确认项；券/位置用途、枚举和平台终止仍缺证，P29/P31 不整体 accepted，P32 未启动。证据：`docs/harness/reports/P31-confirmed-units-direct-check.json`；说明：`docs/harness/reports/P31-confirmed-units-implementation.md`。


2026-10-12 用户范围确认：只要店铺和商品的公开信息，不需要个人领券状态、个人会员资格或账号专属优惠。公开展示的价格、优惠文案及条件仍在范围内；公开会员价来源数字不等于个人会员资格。两条券引用的账号关联用途仍是事实未知，继续不导出，不把它们断言为私人字段，也不再向用户重复询问是否需要个人优惠。该范围确认不改变未知单位/枚举、来源资格或全店覆盖结论。


阶段：stage-05-real-sku-and-store-coverage 真实规格关联与全店覆盖
目标：按目标店铺实际分类和分页行为组织采集，汇总完整记录并保留范围和来源。
状态：ACTIVE_DECLARED_COVERAGE_VERIFIED_QUALIFICATION_PENDING；窗口19本轮声明范围已全部覆盖并交付最终233行清单/155商品/200SKU/19分类。初始响应155有序成员+22折叠成员共177个分类商品关系，与实际正文集合完全相等：有序缺0、折叠缺0、额外未声明成员0；5类展开入口均已操作并有自身响应证明。本轮19份v4分类响应、scope拒绝0，147组请求/响应成员匹配，输入253行按SKU/分类保留最新整行去重20行；55初始完整记录+178分类候选，不跨观察补价、不提升候选资格。四组实际输出合同/JSON/CSV/manifest/计数/来源/权限核对通过。有限已声明引用集合耗尽作为本轮停止依据，平台分页终止、未声明或未来商品不作断言。2026-10-11T17:03:14.350370+00:00stop关闭，宿主2974退出、锁消失、stream0、拦截清理、cleanup=COMPLETE、两latch=CLOSED、固定CA保留；HTTP35完整/0失败/0未完成，TLS失败0。当前无页面任务或采集窗口；剩余为分类候选完整业务资格、币种单位及平台终止未确认，P29 active/incomplete，不accepted、不启动P30–P33。证据：docs/harness/reports/P29-window19-final-coverage-direct-check.json、docs/harness/reports/P29-window19-final-inventory-export-receipt.json。
依赖：P28
来源收据：当前用户“现在继续”；docs/harness/reports/P28-direct-acceptance.json、P28-delegation-ledger.json及P29-predecessor-coverage-review.json。旧公开投影只作前置事实，不冒充新来源。
产品：有界分类分页编排、商品/SKU 去重和多观察结果集，附完成与缺口清单。
证据：P29 完成标准中的直接结果及对应验证；不能以文档存在或作者自报代替。
载体：working-copy-only；不 commit、不 push、不发布。

相关权威设计：

- docs/harness/plan.md
- docs/harness/field-coverage-plan.md
- docs/harness/stages/stage-05-real-sku-and-store-coverage.md

相关事实：

- P26/P28原入口仍以一对新鲜FOOD/PRODUCTLIST为单位；P29已增加完整观察的有界连续记录和独立汇总分支。
- 不同观察可以各自保留完整记录，不能互相补价格或缺失字段。

入口：

- collection_adapter/mitmproxy_bridge.py
- collection_core/result_publisher.py
- collection_core/p1.py

未知：分页触发、结束条件及来源总数是否存在需依据当前真实路线确认。

允许动：

- collection_adapter/
- parser_candidate/
- collection_core/
- contracts/schemas/
- docs/harness/
- docs/architecture.md
- README.md
- runtime-output/（仅本次新建0700/Git忽略根中的控制与公开业务结果，0600且不覆盖）

不许动：

- 超出当前P29分类分页/多观察范围的实现或真实运行；同一已确认店铺的公开列表/分类输入仍须新鲜引用、当前PID与实际预检，不扩大为全微信/全系统。
- 复用旧运行锁或额度、自动重试、未明确的网络/UI/系统代理/CA/keychain/凭据/会话/交易操作。
- 原始来源正文、URL、headers、Cookie、值哈希或自由错误进入代码、fixture、报告或 Git。
- 其它 worktree、_archive/、historical_assets/、历史 done/ 原件和 Harness runtime；不 commit、push 或发布。

完成标准：

- 冻结当前目标的分类/页触发方式、有限预算和结束条件；首版给用户必要页面操作提示，未获明确范围不自动 UI 或重放请求。
- 版本化实现多观察结果组织及 manifest，保留单条记录自身时点与来源，不删除现有同观察保护。
- 稳定去重且保留商品多分类关系和全部已观察 SKU；同名不同商品不合并。
- 缺页、重复、空页、来源变化、取消/超时、发布异常有确定行为；保留已发布完整结果，不将部分范围标全店。
- 实际范围内验证分页与合并结果，JSON/CSV 和商品/SKU/分类/页计数一致。

当前焦点：窗口30声明商品集合已覆盖并导出；修复后的窗口31持续接收，等待用户正常重进同店的新初始配对。保持接收器开启，无自动重试，产品仍incomplete。
窗口7已识别：该窗口自身门店两组FORM编号匹配，14份真实render全部ZERO，125组请求数组中tagId/spuId逐项与各自响应匹配。19分类均已见公开商品正文，该窗口155个有序引用已见正文；22个折叠引用缺正文。候选规则p29-observed-category-render-v1，真实平台version仍UNKNOWN，不以键名、候选数量或停止收据证明全店。
边界：沿用已获准用户手动信任与准确PID扩展能力，按本次用户决定固定本机开发CA、窗口关闭不再删除CA；不自动UI/重放/交易。准备及未start记零尝试，实际窗口独立记账；单条记录不跨观察补值。P30–P33未启动。入口与当前状态见docs/harness/p29-store-pages-operations.md。
恢复：执行 Agent 核对当前指令、依赖和边界后，将本任务移入 leaves/ 作为唯一 current leaf；仅移动任务文件不扩大权限。

## Work Unit P29_PAGES

2026-10-11 解析实现补充：按用户明确要求由 Grok 实现，新增 `p29_category_price.py`、候选与清单 v2、`--price-evidence` 离线入口。主代理修复短坐标固定错误码和同一时刻附加价格冲突遗漏，相关回归与真实公开投影逐项核对通过。当前交付为 178 行价格证据候选及 233 行清单；币种/金额单位和业务语义的缺口不因数字已解析而消失。证据：`docs/harness/reports/P29-category-price-parser-direct-check.json`。无新采集、无资格提升，P29 仍 active。

2026-10-12 优惠规则解析补充：Grok 完成 `p29_price_rules.py`、候选/清单 v3、`--price-rules` 及合成测试。主代理核对 2136 个数字字段、178 个商品文本字段及 51 条 SKU 文本，与自身来源一致；178 行分类结果合入 233 行清单，v2 共有字段保留。187 次相关测试执行通过（含父套件重复）。初始 55 行规则明确未重解析，规则算法/币种/单位未知。证据：`docs/harness/reports/P29-price-rules-direct-check.json`。无新真实尝试，P29 active、complete=false、productResult=incomplete。

2026-10-12 初始行补齐：按用户继续指令复用既有公开投影，初始 55 行自身附加价格和优惠通过 v4 导出；分类 178 行保持 v3 原样，旧 v1–v3 重算字节一致。102 次相关测试执行通过，935 个数字字段、220 个文本字段及 24 条 SKU 文本独立来源核对通过。证据：`docs/harness/reports/P29-initial-price-direct-check.json`。保留未知语义、分类单位和部分资格；无新采集，complete=false、productResult=incomplete。

目标：建立有界观察组织、商品/SKU去重与覆盖缺口清单，取得允许范围内的真实分类验证。
依赖：无（跨leaf的P28稳定核心accepted已核对）
允许动：

- collection_adapter/
- collection_core/
- parser_candidate/
- contracts/schemas/
- docs/harness/
- docs/architecture.md
- README.md
- runtime-output/（本次独立0700忽略根）

不许动：

- 跨观察补字段、读取原包/私人值/旧raw、复用旧锁、自动UI/重放/交易、扩大目标或系统能力。
- 其它worktree、归档、历史done原件、Harness runtime及Git写入。

完成标准：

- 多观察模型和结果可调用，完整保留每条记录自身时点/来源及商品SKU分类关系，稳定去重且不跨观察补值。
- 缺页/空页/重复/来源变化/预算/取消/发布失败确定处理，保留已发布完整结果，不把未确认终止标全店。
- 分类触发和终止事实来自获准真实输入；实际汇总JSON/CSV/manifest计数一致，必要回归与无值直接证据齐全。

结果合同：docs/harness/reports/P29-delivery-report.md。


## Work Unit P31_FIELDS

目标：按用户 2026-10-12 明确继续指令，补齐窗口 19 已获准公开投影中价格以外的商品/SKU/属性及门店配送字段，交付 CSV、JSON、字段说明与缺失清单。
依赖：无（P28 accepted 的真实依赖已核对；无需等待 P29 完整资格）
相关权威设计：docs/harness/plan.md、docs/harness/unfinished/P31-public-business-fields.md
相关事实：窗口 19 初始 55 行与分类 178 行的 v4 清单已独立核对；当前无真实采集窗口；新字段的来源路径/类型见 docs/harness/reports/P31-existing-field-source-inventory.json。
允许动：

- parser_candidate/p31_public_fields.py、parser_candidate/p31_additional_fields.py、parser_candidate/p31_remaining_fields.py、parser_candidate/p31_context_fields.py、parser_candidate/p31_context_codes.py 及其对应合成测试
- collection_adapter/p31_business_export.py、collection_adapter/p31_additional_export.py、collection_adapter/p31_remaining_export.py、collection_adapter/p31_context_export.py、collection_adapter/p31_initial_relation_export.py、collection_adapter/p31_context_codes_export.py、collection_adapter/p31_confirmed_units_export.py 及其对应合成测试
- contracts/schemas/p31-*.schema.json、docs/harness/、README.md
- runtime-output/ 下明确窗口根中的新独占 0700/0600/Git 忽略结果

不许动：

- 原 v1–v4 代码和输出、跨观察补值、状态枚举或金额单位猜测、任意原包透传
- 私人数据、URL/图片/样式/追踪值、原始响应、新网络/UI/系统设置/latch 或资格提升
- Git 写入、其它 worktree、归档

完成标准：

- 逐字段按自身来源和坐标解析，商品与 SKU、属性索引及门店观察分离；缺失/null/空/零/负数区别明确。
- 有闭合合同与对应合成回归，原 v4 字段和选择顺序保留，同一时刻新增字段冲突拒绝。
- CSV/JSON/manifest/字段说明/缺失清单一致，实际公开投影逐项核对，旧文件保留，无新真实尝试。

未知：状态码、库存哨兵、销量精确口径和配送单位/适用条件；用户明确无需目标系统导入验证，该项不作为待办或阻塞。
结果合同：docs/harness/reports/P31-public-fields-implementation.md

P31_FIELDS 当前交付：2026-10-12 非价格字段交付：已新增 49 项商品/SKU/门店标量及带索引的属性选项解析，交付 233 行商品表、1 行门店表、逐列字段说明和状态覆盖清单。原 v4 字段全部保留；79 次相关测试执行和自身来源逐项核对通过。当前仍有业务语义和未全面适配的可见字段，P31 整体 incomplete；无新采集或目标系统实际导入验收。 证据：`docs/harness/reports/P31-public-fields-direct-check.json`。本有界切片通过验证，不将 P31 全任务或 P29 资格标为 accepted。


2026-10-12 后续字段补漏：新增 37 条标量路径和 15 条带索引的标签路径，商品 233 行/门店 1 行及旧字段全部保留；49 次相关测试和独立来源核对通过。修复七文件导出的晚期失败清理。用户明确无需目标系统导入验证，该项不再作为当前任务缺口或停点；P31 其它语义/范围缺口保留。证据：`docs/harness/reports/P31-additional-fields-direct-check.json`。


2026-10-12 剩余公开字段处置：新增 6 条标量、1 条分享渠道索引路径，并明确记录 6 条来源 null，商品 233 行和门店 1 行的旧字段保留；37 次相关测试与独立来源核对通过。两条券引用的账号关联范围尚未确认，暂不导出；已向用户询问是否另需个人优惠。已有公开投影的 PRODUCT/SKU/poi_info 路径均有明确处置，P31 业务语义和完整资格仍 incomplete。证据：`docs/harness/reports/P31-remaining-fields-direct-check.json`。


## Work Unit P32_LOCAL_ENTRY

目标：按用户后续工作指令，以无参数本地命令定位既有交付结果，提供文件状态、范围和恢复说明。
依赖：无（只依赖已核对交付的 P31 v7 文件；不消费 P29/P31 整体资格）
相关权威设计：docs/harness/unfinished/P32-usable-export-and-entry.md
允许动：collection_adapter/p32_result_entry.py、对应合成测试、docs/harness/、README.md。
不许动：业务结果正文或文件、新采集、网络/UI、系统设置、latch、Git 写入、归档。
完成标准：无参数入口正确定位当前包；缺文件、异常权限及清单错误按固定原因失败；说明包含范围、缺失、恢复路径；不将文件存在当作业务或全店验收。
当前交付：7 项合成测试通过，实际目录命令退出 0，11 文件存在，运行前后结果大小/修改时间/权限不变。此独立本地切片已完成，P32 全任务未 accepted。
结果合同：docs/harness/reports/P32-local-entry-validation.json


窗口 20 初始列表已核对：本次 FOOD/PRODUCTLIST 同观察与自身结果验证通过，54 行、30 个不同商品、40 个 SKU、19 个分类。初始声明 155 个有序和 22 个折叠分类商品关系；仍缺 115 个有序及 22 个折叠正文。第 1/2/4/5/6 类声明关系已齐，已请用户只浏览第 3 类和第 7–19 类并展开列表入口，最后继续翻一屏反馈终止提示或加载变化。部分缺正文分类同时标 has_next_page=false，已取得该标记不足以单独证明终止的当前反例；不将其改判全店完成。原窗口继续 ACTIVE，无再次 start。证据：`docs/harness/reports/P29-window20-initial-coverage-check.json`。
