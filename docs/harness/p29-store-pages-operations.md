# P29 分类观察、多观察汇总与固定开发证书

2026-10-16 当前：用户确认数据足够，采集已停。runtime-output/p29_pages_b50e2d2a61a242f2a0dfedc8fc7e0a50 已 stop，intercept_cleared=true，cleanup=INCOMPLETE，不可再 start。有效商品正文在 runtime-output/p29_pages_313d083fff964939b7d1edc1ccb1bdd7 的 captured-http，尚未解析成商品表。不要重开旧窗口。P29/P31 及产品仍 incomplete。

2026-10-14 当前：用户确认地址页已打开，窗口33的门店详情请求返回HTTP 200且响应完成，0传输失败；此前失败根因仍未知。查明详情路由原先只转发、未复制正文，现已补公开详情副本独立保存：只选已观察的POST /weapp/shop/v1/poi/detail，不复制详情请求正文，不读取私人分支值，不推断店铺关联或混入商品表。569项适配层经两套解释器互补通过，核心58项通过。窗口33已完整清理，窗口34于17:49:19 UTC接替，PID60732、网络PID46630，ACTIVE、接受副本且详情副本功能enabled，两latch=OPEN，无截止时间，保持开启。窗口34已于17:53:08 UTC保存并核对1份详情公开副本（69个标量条目），当前所选店名一致，地址、公开电话、配送时段、服务说明、门店标签和公告均非空；HTTP 200且根code为ZERO，传输失败/跳过/丢弃均0，接收继续开启。见 docs/harness/reports/P29-window34-detail-copy-direct-check.json；旧231行及55行结果保留，分类无需重刷。无自动重试或系统配置修改，P29/P31及产品仍incomplete。当前控制根为runtime-output/p29_pages_134d3b6061b64235b1bfbfde88928d7d，send_command(status/stop)只用此根。不要重开旧窗口。见[控制](reports/P29-window30-export-and-window31-recovery-2026-10-14.md)。以下为历史时点。

2026-10-14 当前运行：用户明确“保持接收器打开”，窗口30已以 `CURRENT_USER_REQUESTED_CONTINUOUS_RECEIVING` 启动，time_limit_seconds=null、attempt_limit=1，无两分钟截止。接收器71734、两latch=OPEN；不因等待反馈或聊天结束主动停止。新根、当前进程和控制方法见[持续接收](reports/P29-continuous-receiver-window30-2026-10-14.md)。`status`只查状态，明确stop或实际故障才关闭；不重复start或自动重试。下文两分钟试采不再限制本轮。

2026-10-14 当前：窗口29按用户再次继续指令完成两分钟试采并完整关闭，新增商品0；转发诊断实际输出6个连接成功、目标TLS hello0、HTTP输入0、引擎错误0，副本解析无失败。当前等待本轮页面重进时点和结果，不自动新开或重复操作。两latch=CLOSED，见[窗口29结果](reports/P29-window29-trial-result-2026-10-14.md)。

2026-10-14 最新状态：窗口28已完成120秒/1次试采并关闭，用户反馈页面正常，新增商品数据0。当前宿主退出、锁清理、拦截解除，两latch=CLOSED；不重开旧窗口。启动准备改为90秒，真实试采仍为120秒；初始化只通知实际配置变更，Redirector只复用已有组件，status/close输出已有连接与TLS计数。窗口26意外更新应用已单独披露。下一轮真实入流核对尚未启动，见[修复、验证与实际结果](reports/P29-forwarding-startup-and-window28-2026-10-14.md)。以下为历史状态。

当前控制方法：使用已完成当次目标、固定CA和准确网络PID准备的新0700/Git忽略根，在安装现有mitmproxy的解释器中调用 `launch_prepared(root, forward_public_copy=True)`。等待 `P29_RECEIVER_PREPARED` 事件，此时零尝试、无网络引擎；然后用 `send_command(root, 'start')` 单独启动。`status` 查看分开的转发/解析状态，`stop` 先清除接管与连接再关闭分析，最终检查 `P29_FORWARDING_CLOSED` 的 `cleanup`、`intercept_cleared`、活动流数和latch。新收据含 `input_mode=FORWARDED_COPY`；无此标记的旧实例仍只允许status/layout/stop，不可start。

小范围试采支持 `CURRENT_USER_REQUESTED_ONE_SMALL_TRIAL`：120秒、1次，保留原有目标引用和公开范围校验；窗口超时或用户stop即关闭，不自动重试。准备和启动都重新核对当前进程，启动过程中也能stop。新入口不安装/更换CA或改系统代理/keychain；固定证书仍由原有准备检查验证。不能将本次程序接通或离线测试当成真实加载/风控已解决。见[实现与测试](reports/P29-forwarding-entry-restored-2026-10-13.md)。

2026-10-13 当前采集入口已退役：为落实用户“只拿副本”的要求，已删除旧PID代理启动路径。旧准备/serve命令及控制器start现在拒绝，返回`P29_COPY_SOURCE_UNAVAILABLE`；尚未接通真实旁路副本来源，不能继续真实采集。已有结果的离线解析/导出和旧实例status/stop仍保留。下文涉及代理启动的步骤仅为历史说明，不再可执行；不应重装组件或换参数绕回旧方案。见[改动与未完成项](reports/P29-copy-only-entry-retirement.md)。

R17最新状态：窗口19本轮声明范围已全部覆盖并交付最终233行清单/155商品/200SKU/19分类。初始响应155有序成员+22折叠成员共177个分类商品关系，与实际正文集合完全相等：有序缺0、折叠缺0、额外未声明成员0；5类展开入口均已操作并有自身响应证明。本轮19份v4分类响应、scope拒绝0，147组请求/响应成员匹配，输入253行按SKU/分类保留最新整行去重20行；55初始完整记录+178分类候选，不跨观察补价、不提升候选资格。四组实际输出合同/JSON/CSV/manifest/计数/来源/权限核对通过。有限已声明引用集合耗尽作为本轮停止依据，平台分页终止、未声明或未来商品不作断言。2026-10-11T17:03:14.350370+00:00stop关闭，宿主2974退出、锁消失、stream0、拦截清理、cleanup=COMPLETE、两latch=CLOSED、固定CA保留；HTTP35完整/0失败/0未完成，TLS失败0。当前无页面任务或采集窗口；剩余为分类候选完整业务资格、币种单位及平台终止未确认，P29 active/incomplete，不accepted、不启动P30–P33。证据：docs/harness/reports/P29-window19-final-coverage-direct-check.json、docs/harness/reports/P29-window19-final-inventory-export-receipt.json。

## 已有输入的离线价格解析

当前离线价格解析入口（2026-10-11）：`python3 -B -m collection_adapter.p29_category_export` 和 `python3 -B -m collection_adapter.p29_store_inventory` 增加 `--price-evidence`，其余命名输入参数不变；不传该参数仍发布 v1。新入口只读取明确指定的现有公开投影，按自身响应保留价格分量、文本和缺失状态，发布新的独占目录，不启动接收器或消耗真实尝试。

窗口 19 根内已交付 `category_price_7809d5cadf6a4c66ac185f6f30d9584c`（178 行）与 `store_price_inventory_6274f2ce1fae4b39bb3f0db70f2dcea4`（233 行），各含 `records.json`、`records.csv`、`manifest.json`。目录 0700、文件 0600 且 Git 忽略；原 v1 输出保留。附加价格数字的负值不作金额，未确认币种/单位不借初始行补齐。实现与复核见 [解析报告](reports/P29-category-price-parser-implementation.md)及[直接检查](reports/P29-category-price-parser-direct-check.json)。

2026-10-12 规则入口：上述两个 CLI 增加 `--price-rules`，与 `--price-evidence` 互斥；默认仍为 v1，`--price-evidence` 仍为 v2。规则 v3 在同一来源行保留商品/SKU 数量与折扣配对、阶梯包装数量/费用和文本索引，不推定算法或金额单位。窗口 19 根内新目录为 `category_price_rules_35f33711fb3f4d769d31f5a4ac042512`（178 行）及 `store_price_rules_eb05eb319a1945b196ba31b781017bfe`（233 行），各含三件套并沿用 0700/0600、Git 忽略和独占发布。初始 55 行规则标记 `NOT_REPARSED_ON_INITIAL_PAIR`，不借分类值填补。旧目录保留，核对见[规则独立检查](reports/P29-price-rules-direct-check.json)。

2026-10-12 初始行补齐入口：库存 CLI 另加 `--initial-price-rules`，与原两个价格选项互斥。库存 v4 复用已获准初始公开投影，补 55 行自身附加价格和优惠，分类 178 行及 CSV 列结构沿用 v3。新目录 `store_initial_price_rules_e1fa474f71c84fcb98d916c9bc0f2e15` 共 233 行三件套，权限/Git 忽略/独占输出不变；旧版本保留。来源与重算核对见[初始行独立检查](reports/P29-initial-price-direct-check.json)。

## 固定证书

用户本轮明确要求长期证书，取代本轮临时证书策略。固定证书名称：`Local Collection Development CA 94988f9dbcf24726a245d903c3a57a76`，公开证书到期时间：`2036-10-04T20:31:27+00:00`。

```text
/Users/yoyi/爬虫/runtime-output/development-transport/p26_transport_21b02c9a5735459190a437f9e2a6ef8c/mitmproxy-ca-cert.cer
```

用户本人将这张公开证书导入登录钥匙串，把SSL设为“始终信任”；开发者不读取或代改keychain。前一张未使用临时CA文件已按创建身份清理；若已导入其信任，用户可手动移除那一张临时证书。

`collection_adapter/development_transport.py`提供`create_development_ca_once`和`validate_development_ca`。前者只在已有具体CA创建/使用授权及本次长期保留决定后使用；生成一次，已有registry拒绝重新生成。后者只检查自有0700/Git忽略根、0600注册文件、精确目录身份、六文件元数据及公开到期时间，不读取或导出私钥。

固定存储根：`/Users/yoyi/爬虫/runtime-output/development-transport`，0600注册文件为`development-ca.json`。各采集窗口使用新的目标引用、控制和尝试锁，通过`development-ca-binding/v1`引用这一准确注册目录；证书复用不复用旧窗口，也不证明目标来源已就绪。窗口结束关闭接收器、连接、短暂输入和latch，保留固定证书/私钥，只有用户明确移除才清理。私钥仅供本机TLS引擎使用，不放入代码、报告、fixture、Git或产品分发包。

正式产品若运行在本机可继续使用这份本机证书；其它设备应生成各自的本机CA并由本人信任，不共用分发开发私钥。本任务只完成本机证书复用，没有实施正式产品安装、分发或提升Parser/Provider资格。

## 本轮范围与预算

| 项目 | 明确范围 |
| --- | --- |
| 目标 | 用户已确认的美团外卖微信小程序、绝味鸭脖（通盛路店）；当前PID和来源归属仍须现场重新核对 |
| 来源 | 已直接确认的wx.waimai.meituan.com FOOD与PRODUCTLIST POST业务响应；其它路由先只检查去查询参数的安全路由元数据，不能自动读取未知正文 |
| 当前归属保护 | 每组合格观察都需要两份新鲜FORM的poi_id_str与wm_poi_id分别匹配当组FOOD公开编号，店名匹配，两响应间隔≤10秒；不得借用旧FOOD |
| 页面 | 用户本人进入同一店铺、切换左侧分类和滑动列表；不逐商品点开，不自动UI，不重放或交易。先观察实际响应再固定分页规则 |
| 短暂输入 | 单响应编码/解码各≤1MiB，窗口编码/解码累计各≤4MiB，并发读取≤8；待配对原文最多两份、各≤10秒，FORM/投影租约≤60秒，关闭即清空。累计字节不因完成一组而归零 |
| 结构 | 节点≤40000、深度≤32、路径≤4096、选取公开路径≤1024、单份公开标量≤8000、单个字符串≤256字；私人分支值保持不解码，URL等值拒绝 |
| 汇总 | 本窗口最多32组合格观察（含空观察及分类识别），输入完整SKU行累计≤40000，源分类并集≤256，折叠分类商品引用≤40000；保留的公开字段产物累计≤16MiB，绑定快照及JSON/CSV汇总各受16MiB预算。没有会话时间或尝试总次数上限，不自动重试 |
| 输出 | 本次新0700/Git忽略根下独立observation目录、0600公开标量投影；关闭后独立collection目录中JSON、CSV、manifest。禁止覆盖。空观察只写覆盖元数据，不造业务行 |
| 停止 | 用户stop/Ctrl-C、来源或同观察失败、结构/隐私/大小/计数预算、解析/发布异常、接收器丢失即关闭；已发布完整观察保留。部分范围始终PARTIAL，空页和has_next_page=false不能证明全店终止 |

新窗口根：`/Users/yoyi/爬虫/runtime-output/p29_pages_c0e95647243d41d7bddbbcaca61b31c6`。P26历史识别22/结果2和P28新根识别0/结果2保留，本根从实际零尝试开始。

## 准备、启动和关闭

本次SSL信任及单目标页面完成事实未到时，`prepare`准确返回P26_APPROVED_PRECONDITIONS_REQUIRED、零尝试且两latch=CLOSED，没有虚报来源就绪。用户随后明确“好了”，开发者记录当前完成事实并重新核对helper父子进程、UID与唯一socket owner；实际预检见[收据](reports/P29-live-preflight.json)。用户无需寻找接口、参数或Cookie。

以下为本轮实际执行的命令，保留用于复现检查；此根窗口已使用，不能重新start。新窗口须由开发者新建独立0700/Git忽略根、当前引用/输入锁/参数，重查PID及预检后替换output-root，继续复用固定CA。不会自动重开。

只读准备入口不启动网络、不读回调、不计尝试；已使用根准确拒绝复用：

```sh
cd /Users/yoyi/爬虫
PYTHONDONTWRITEBYTECODE=1 /Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B \
  -m collection_adapter.p26_identification_host \
  --output-root /Users/yoyi/爬虫/runtime-output/p29_pages_c0e95647243d41d7bddbbcaca61b31c6
```

预检通过只表示program_preparation=COMPLETE，source_ready仍UNKNOWN。下列为本轮历史接收器命令；当前接收器已经退出，新窗口满足上述条件后才可由开发者执行：

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B \
  -m collection_adapter.p26_identification_host \
  --output-root /Users/yoyi/爬虫/runtime-output/p29_pages_c0e95647243d41d7bddbbcaca61b31c6 \
  --serve-identification --inspect-current-domain wx.waimai.meituan.com \
  --batch-public-json --identify-field-layout-only \
  --inspect-sensitive-field-keys --inspect-public-fields --analyze-store-pages
```

P26_RECEIVER_READY_NOT_STARTED仍零尝试；开发者发送`start`再次预检后才激活准确PID，两latch=OPEN，P29窗口计一次新的RESULT尝试。入口宿主名字沿用P26，不算额外识别成功。用户按开发者实时提示重进店铺、切分类或滑动，开发者发送`status`查看固定码、有限计数与pending_pair，不自动切换页面。

第一组合格完整输入发布后保持ACTIVE，可继续接收其它新鲜完整观察。若只有PRODUCTLIST，pending_pair=FRESH_MERCHANT_PENDING；10秒过期后丢弃原文，不借用历史店铺响应。所有新观察保留自身时点/来源；按store_id、sku_id、category_ref选最后完整行去重，不跨观察补字段。后续未重复出现的SKU保留原完整观察时点，不推断当前在售；每个观察目录和公开投影可独立核对。

`stop`、Ctrl-C或错误先关闭输入和清理租约，再从已完成绑定快照重新生成并验证汇总，独立发布`collection_<新引用>`三件套。发布失败保留先前观察，不声称汇总成功。空观察只记录来源、时点、分类和折叠缺口，empty_page_is_termination=false，不冒充完整商品结果。关闭收据核对cleanup=COMPLETE、活动stream0、intercept_cleared=true及diagnostic_output_complete=true；固定CA按本次用户决定保留。

本轮实际关闭证据分为[关闭收据](reports/P29-window1-close-receipt.json)和[输出收据](reports/P29-window1-output-receipt.json)；diagnostic_output_complete来自后者。固定CA客户端握手已成功，不能据上游失败要求再换本机CA。旧窗口没有记录校验子因，保持UNKNOWN。新增upstream_tls_failure只读取OpenSSL数值校验结果及名称种类/比较结果，输出固定状态码，不读错误文本、证书链或正文；TLS_VERIFY_NO_ERROR_REPORTED只表示没有报告证书校验错误，不代表握手成功。不关闭上游验证，也不猜测修补SNI。

## 当前缺口

上一轮获准公开投影直接显示19个分类容器、7个非空分类、23个折叠商品引用无正文；product_count与正文数量不一致，current_page=0和has_next_page=false含义未确认。详见[前置覆盖检查](reports/P29-predecessor-coverage-review.json)。这些旧事实不能当作本轮新鲜输入。

尚需本次真实观察确定：切分类/滑动是否返回同期FOOD/PRODUCTLIST，折叠商品由哪个当前路由加载，category/page参数与返回分类对应，空页/重复/页标记的真实含义，是否有可信来源总数及全店终止条件。未知路由须先隔离到当前目标再检查获准公开结构，不扩为全微信/全系统扫描。不改同观察、隐私或预算校验来迎合响应。

## R17 最新继续窗口

P29窗口2已于2026-10-10T04:27:37.220002+00:00关闭：1组完整观察及独立汇总已发布，48条分类SKU记录、32个商品、44个SKU、5个有商品分类；19个源分类容器，25个折叠商品缺正文。JSON/CSV/manifest一致，cleanup=COMPLETE、活动stream0、两latch=CLOSED，固定本机CA保留。新根识别0/结果1，P29跨两根累计实际结果尝试2；未start的两次准备退出仍零尝试。分类切换触发了新的POST分类render路由，上一窗口未读其正文，字段与终止语义仍UNKNOWN。187项对应本地回归通过；P29唯一current leaf、complete=false、productResult=incomplete，P30–P33未启动。

窗口2根为 `/Users/yoyi/爬虫/runtime-output/p29_pages_81df91969dc74a29be9d6ffa4e21a4c5`，已经关闭，不复用锁或引用。见[关闭](reports/P29-window2-close-receipt.json)、[输出](reports/P29-window2-output-receipt.json)、[汇总核对](reports/P29-window2-collection-check.json)。

## 分类render识别准备

新发现POST `/weapp/poi/food/render`。显式`--identify-category-render`仅与`--analyze-store-pages`共同使用。下一窗口重新核对当前父子PID、UID、唯一socket owner，使用新0700忽略根、新引用和锁，复用固定CA；prepare和接收器就绪仍零尝试，手动start后记一次结果窗口。

先取得本窗口新鲜完整FOOD/PRODUCTLIST观察，店名、两组FORM编号和同观察校验全部通过，再建立店铺隔离上下文。分类请求自己的poi_id_str和wm_poi_id须同时匹配；缺任一编号、过期、其他店铺、复用引用、非200或非JSON均在正文复制前拒绝。私人FORM值和响应分支值保持不解码，只识别获准公开标量和结构。

上下文超过10秒明确标注，始终same_observation_record_ready=false、business_record_count=0、family/version=UNKNOWN；店铺隔离上下文不填商品字段。新识别与原完整/空观察共享32份及16MiB公开产物预算，原编码、解码和内存预算保留。关闭清理编号、proof、租约、连接和latch，保留完整结果及固定CA。

用户本人重进同一家店铺，再切分类、滑动到列表底部；实际字段和分页事实取得后再做版本映射。旧PTY控制已在窗口3中断；当前使用下文独立FIFO控制。新参数追加为`--analyze-store-pages --identify-category-render`。准备见[收据](reports/P29-category-route-preparation.json)，验证见[收据](reports/P29-category-route-local-validation.json)。


## 窗口3启动历史（现已中断，无正常关闭收据）

窗口3已于2026-10-10T04:38:33.617622+00:00实际start，当前ACTIVE、两latch=OPEN，新根识别0/结果1，P29跨根累计实际结果尝试3。固定CA复用、当前准确网络PID42372；先等待本窗口新鲜完整店铺观察，再按本次分类请求两个店铺编号核对归属，识别公开结构。新窗口尚无业务响应；窗口2的48条完整汇总和关闭证据保持原样。187项相关回归通过，完整分类及终止语义仍UNKNOWN，P29 complete=false、产品incomplete、下游未启动。

新根为 `/Users/yoyi/爬虫/runtime-output/p29_pages_186302818a2a4c0eab869e0951e9d50b`，只用此根的新引用和锁。[预检](reports/P29-window3-preflight.json)仍零尝试、source_ready=UNKNOWN；[实际start](reports/P29-window3-started.json)及[当前分层状态](reports/P29-window3-current-status.json)分别保存真实开始和进展。使用上文新识别参数，stop/Ctrl-C关闭，不自动重开。

## 独立接收器控制

上一窗口宿主退出后，工具句柄不可用，原控制latch滞留OPEN；[中断检查](reports/P29-window3-interrupted-receiver.json)核对准确宿主及转发进程均不存在，结果产物0、关闭收据缺失。原因和最终清理仍UNKNOWN，实际结果尝试1保留。原控制文件在新建备份后据无活动宿主改为CLOSED，不复用该根或锁，不伪造正常关闭收据。

`collection_adapter/p29_receiver_control.py`提供`launch_prepared(root)`、`send_command(root, command)`及`read_events(root)`。开发者先建立新根、新引用和当前PID/固定CA预检，再用已核对mitmproxy Python调用launch_prepared。它只准备接收器，零尝试；独立进程以本根自有FIFO作为输入，子进程同时持有读写端，短命令写端退出不会触发EOF。stdout仅写本根0600受控事件文件，stderr不保留；未安装服务或改变系统代理/扩展配置。

控制仅接受start、status、layout、stop；每次核对UID、准确进程参数和本根FIFO inode，拒绝另一进程、替换FIFO、符号链接及宽权限文件。最多64条普通控制命令，到预算仍允许stop；事件文件累计最多1MiB，触限按诊断失败关闭。启动与关闭行为及原隐私/输入/来源预算不变，进程退出不自动重启。

窗口4旧根（已关闭，仅作历史事实及候选审核）：`/Users/yoyi/爬虫/runtime-output/p29_pages_f5b9641968cb4c448a6c0cbf941297a1`。启动CLI退出后第二条独立CLI仍成功status，PREPARED零回调/零尝试、两latch=CLOSED；见[直接控制核对](reports/P29-window4-independent-control-check.json)。随后开发者单独发送start，[实际开始](reports/P29-window4-started.json)及[当前分层状态](reports/P29-window4-current-status.json)记录新结果尝试。随后聊天轮次的独立控制核对准确PID51327仍运行、窗口引用和实际次数不变，且已收到一对当前真实响应；见[跨轮次生存检查](reports/P29-window4-conversation-survival-check.json)和[56条逐行来源核对](reports/P29-window4-observation1-direct-check.json)。[折叠缺口](reports/P29-window4-fold-gap-check.json)保留当时尚无分类响应的检查事实；后续已取得2份render，见[当前分类输入](reports/P29-window4-category-input-direct-check.json)。用户未找到不可售入口，不重复要求查找。

以下为窗口5运行期间使用的控制命令；该宿主现已正常退出，不能对已用根重新start。关闭后只读read_events或下列实际关闭收据：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B - <<'PY'
from pathlib import Path
from collection_adapter.p29_receiver_control import send_command
root = Path('/Users/yoyi/爬虫/runtime-output/p29_pages_df1c58789ae84ca0b69d340a031fb18d')
send_command(root, 'status')
# 结束时改为 send_command(root, 'stop')
PY
```

关闭后核对当前根的result-host关闭收据、result-output输出收据、活动stream0和latch=CLOSED；若没有直接关闭收据，保持UNKNOWN，不用存储状态替代实际清理证据。固定CA保留，产品仍incomplete。

## 窗口4历史分类输入的候选核对

用户未找到不可售入口；此后接收器已实际收到两份render，来自初始源分类索引15–18。无需继续寻找该入口或逐商品操作。当前19条候选包含15个新增商品；25个原折叠引用仍无正文。数据完整性、当前门店/分类名称和页终止均未补猜。

入口只读当前明确文件的获准公开标量，不开监听、不增加尝试，不写业务值或提升来源资格。它核对0700忽略根、0600自有文件、关闭Schema及本根当前attempt引用，再按版本化候选规则读各SKU；stdout只有无值审核元数据。当前两个v1输入的code标记为UNOBSERVED，不回读原包。

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m collection_adapter.p29_category_review --output-root /Users/yoyi/爬虫/runtime-output/p29_pages_f5b9641968cb4c448a6c0cbf941297a1 --input-name category_render_88faa9d5e09c44c3a4a3d1438ac35d3d-public-fields.json
```

第二份明确输入为`category_render_34af72f17f694891a8b2296706baf5e9-public-fields.json`。见[直接核对](reports/P29-window4-category-input-direct-check.json)及[本地验证](reports/P29-category-candidate-local-validation.json)。

代码已增加`p29-category-render-inspection/v2`，只保留根code的ZERO/NONZERO/ABSENT/INVALID_TYPE固定标记，私人分支仍不读值，不保留原数值或错误文本。窗口4原v1宿主已受控关闭；窗口5已直接接收28份v2输入，全部ZERO，随后正常关闭。旧v1文件及原事实不改写。任何完整发布仍须新鲜、完整、同观察关联与单位事实；候选审核不能替代它们。

## 窗口5启动历史与当前已关闭结果

窗口4已正常关闭并保存独立56条汇总，19条候选没有加入完整结果。见[关闭](reports/P29-window4-close-receipt.json)、[输出完成](reports/P29-window4-output-receipt.json)和[汇总核对](reports/P29-window4-collection-check.json)：cleanup=COMPLETE、活动stream0、intercept_cleared=true、两latch=CLOSED，固定CA保留。

窗口5根为`/Users/yoyi/爬虫/runtime-output/p29_pages_df1c58789ae84ca0b69d340a031fb18d`，准确网络PID42372、独立宿主98407已退出。准备与第二条独立CLI直接核对零尝试、零输入、两latch=CLOSED，之后单独start于2026-10-10T08:24:59.535500+00:00；2026-10-10T09:07:42.564011+00:00受控关闭。见[预检](reports/P29-window5-preflight.json)、[开始](reports/P29-window5-started.json)、[关闭](reports/P29-window5-close-receipt.json)、[输出完成](reports/P29-window5-output-receipt.json)及[51条汇总核对](reports/P29-window5-collection-check.json)。本根识别0/结果1，P29累计结果尝试5；固定CA继续保留，不自动重开。

用户重新进入后滑动列表，已取得两组完整列表与28份分类响应。129商品/168SKU/19非空分类是本窗口输入公开编号并集，完整已发布结果仍51条、33商品/47SKU/4分类。25个折叠编号缺正文，完整性不以列表滑到底或来源product_count=0证明。

## 批量候选审核入口

`review_category_batch(root, input_names)`只读明确列出的当前授权公开投影：最多32个文件、合计16MiB、40000候选行；不启动接收、网络或新尝试。核对本根、各文件、版本、当前attempt、唯一请求引用及单一窗口；按原观察时点选择每SKU/分类最新的整条候选，保留自身source_file/request_ref/observed_at，拒绝SKU归属变化和同刻冲突，空/缺失字段不借旧值。stdout仍只返回固定审核元数据，不能送入完整publisher。

重复`--input-name`即可批量调用；单文件兼容原入口。下面两份明确输入可复现两个观察间的去重，无新尝试：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m collection_adapter.p29_category_review \
  --output-root /Users/yoyi/爬虫/runtime-output/p29_pages_df1c58789ae84ca0b69d340a031fb18d \
  --input-name category_render_9e823f021a8843ca8f11163123711bcd-public-fields.json \
  --input-name category_render_46043f0b243141f39f2d5d8149ff1308-public-fields.json
```

28个明确文件及原时点清单见[批量审核](reports/P29-window5-category-batch-review.json)，各自字段/价格/可选文本逐坐标检查见[直接核对](reports/P29-window5-category-input-direct-check.json)。可直接调用该API的input_names列表来自这份当前清单，禁止扫描历史raw。全部ZERO排除了旧code采样缺口；8份请求时上下文在10秒内，其余20份不是新鲜同观察，所有候选仍不能借门店/分类名称、单位或原价含义。

下一步由开发者核对获准请求中tag_spu_ids的有界公开编号结构及与当前响应的关系，确认页/折叠终止，再做完整分类适配。该键值本轮未读取，不能凭键名推定语法或批次总数；未知字段语义、金额单位和适用条件仍待真实事实。当前不要求用户继续找不可售按钮或逐个打开商品，不自动启动新窗口或下游。


## 窗口6批量请求关联识别（已关闭）

窗口6历史根：`/Users/yoyi/爬虫/runtime-output/p29_pages_d7e7ec57e9e249c2817adaa84817eb7f`。目标仍是用户已确认的美团外卖微信小程序、绝味鸭脖（通盛路店）。先由开发者核对实际接收器，再单独start；准备、接收器就绪不记真实尝试。复用本机固定CA，无须新证书或重复信任。

| 预检项 | 具体边界 |
| --- | --- |
| 输入与来源 | 当前准确网络PID的已确认域名FOOD、PRODUCTLIST及render；render自身两个FORM编号均匹配本窗口完整门店观察后，才检查获准正文和已观察tag_spu_ids键 |
| 所需能力 | 已获准准确PID网络扩展与本机固定CA；不改变代理、keychain或管理员设置 |
| 参数检查 | 编码值≤48KiB、解码值≤16KiB，定义≤128、公开标量≤4096；结构状态与本响应公开编号匹配计数无值输出，私人分支及其它FORM值不解码 |
| 原响应预算 | 单响应编码/解码各≤1MiB，窗口各≤4MiB、同时读取≤8；共享32观察、40000行、256分类、16MiB公开产物及原时效边界，预算不因配对清零 |
| 输出 | 本根0700/Git忽略、0600新文件；每份render保持原v2公开投影，另写同前缀batch-parameter.json闭合无值收据；两份共同计入字节预算，不覆盖旧结果 |
| 启动/关闭 | 开发者用自有FIFO的start/stop；先就绪再实际激活，关闭即清理流、租约、转发和latch，保留固定CA与已发布完整观察 |
| 停止 | 用户stop、来源/隐私/结构/字节/计数预算、时钟、解析/发布或接收器异常即关闭，不自动重开/重试；未知语法只记录固定标记，不把它认作结束或采集成功 |

开发者准备命令（零尝试，不启动监听）：

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B -m collection_adapter.p26_identification_host --output-root /Users/yoyi/爬虫/runtime-output/p29_pages_d7e7ec57e9e249c2817adaa84817eb7f
```

获准start且实际接收器就绪后，用户只需退出回首页再进入这家店铺，滑动右侧商品列表到末尾，不逐商品点开。参数角色/真实平台版本、币种/单位、完整同观察及页终止仍需当前事实，结构或编号命中不自动提升候选资格。窗口5原参数未留存，不能回读或补填；[预检](reports/P29-window6-preflight.json)与[验证](reports/P29-batch-parameter-local-validation.json)保留此时的零尝试事实。


窗口6启动时实际[接收器就绪](reports/P29-window6-receiver-ready.json)、[独立零尝试核对](reports/P29-window6-independent-prestart-status.json)后，[单独start](reports/P29-window6-started.json)于2026-10-10T16:01:39.267474+00:00；[控制转换检查](reports/P29-window6-control-transition-check.json)和[当前状态](reports/P29-window6-current-status.json)当时核对准确宿主75410存活、本根识别0/结果1、累计实际结果尝试6，两latch=OPEN、业务响应0。该启动事实不回填后续输入；用户仅重进同店并批量滑动，开发者实时核对。没有系统设置、证书或范围变化；异常/stop仍受控关闭，不自动重开。

当前重进的[逐条来源核对](reports/P29-window6-observation1-direct-check.json)和[首次输入状态](reports/P29-window6-first-input-status.json)证明56条完整记录来自本窗口自身公开投影；分类参数、单位及完整关联仍待实际render输入。本窗口继续由本人批量滑动右侧列表，不逐商品打开。

## 窗口7逐项数组关联验证（已关闭）

已关闭根：/Users/yoyi/爬虫/runtime-output/p29_pages_6b40659a625f432cb88672f2307adee8；原接收器30826已退出，准确网络PID42372，复用固定CA及已获授权能力。窗口6已关闭，旧根/锁不重开。本人重进同店、连续滑动右侧列表，开发者负责实时检查；先取得本窗口自身完整FOOD/PRODUCTLIST，再按分类请求两个FORM编号隔离。

v2无值收据增加array_item_relation：逐项比较tagId/spuId，另记childTagId比较，不替代tagId；记录重复、未返回及多返回成员。空对象不能从计数中消失，数组项数≤4096；原参数16KiB、定义128、标量4096及窗口预算不变。匹配不提升控制键语义、币种、同观察完整性或正式来源资格，完整业务行仍0。

下列为历史启动前准备命令；该根已start并关闭，不重开宿主或重复start：

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B -m collection_adapter.p26_identification_host --output-root /Users/yoyi/爬虫/runtime-output/p29_pages_6b40659a625f432cb88672f2307adee8
```

[预检](reports/P29-window7-preflight.json)、[零尝试接收器](reports/P29-window7-receiver-ready.json)、[独立CLI](reports/P29-window7-independent-prestart-status.json)、[实际start](reports/P29-window7-started.json)及[当前状态](reports/P29-window7-current-status.json)分别记录。关闭使用自有FIFO的stop；结束即清理转发、租约和latch，保留固定CA及完整结果，不自动重开。

## 当前公开投影的候选表导出

本窗口已关闭。下列入口只读窗口7明确列名的公开标量投影和v2无值匹配收据，不读raw、不开网络/宿主/任意latch，不消耗真实尝试。每次生成新的0700子目录，三件套0600，不覆盖已有结果。非ZERO、旧v1、参数关系缺项/错配、私人值标记、不安全根或预算超限均在创建目标前拒绝。

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B - <<'PY'
import json
from pathlib import Path
from collection_adapter.p29_category_export import publish_category_candidates
root = Path("/Users/yoyi/爬虫/runtime-output/p29_pages_6b40659a625f432cb88672f2307adee8")
review = json.loads(Path("docs/harness/reports/P29-window7-category-batch-review.json").read_text())
names = [source["source_file"] for source in review["sources"]]
print(json.dumps(publish_category_candidates(root, names), ensure_ascii=True))
PY
```

等价CLI为`python3 -B -m collection_adapter.p29_category_export --output-root <root> --input-name <name>`；对明确文件重复--input-name，不传原包或把配置项交给用户。当前已生成`category_candidates_6b9effd9ba9847b1a1e995660659f20b`，152条/115商品/152SKU/14分类，JSON/CSV/manifest逐行一致。表保留原数值，币种、金额单位、价格含义明记UNKNOWN；空字符串与未观察由状态列区分。门店名、分类名不从初始观察补入，不推定原价、活动价或在售。它是真实输入候选表，不是完整业务结果；完整汇总仍`collection_96bd6321c4d04288996bc2e3db9a47e0`的56条。

当前[125组逐项关系](reports/P29-window7-batch-parameter-direct-review.json)、[155个有序引用](reports/P29-window7-reference-set-direct-check.json)、[导出核对](reports/P29-window7-category-export-direct-check.json)和[关闭核对](reports/P29-window7-close-direct-check.json)保留自身窗口、时点和缺口。无需用户逐商品点开。


## 当前按分类的统一商品表

`collection_adapter.p29_store_inventory`只整理本窗口明确的公开投影。按初始列表的分类顺序排列，以分类/SKU选择最后整条自身记录；不同分类分别保留价格，缺失规格不借旧值。分类名称为初始列表的参考标签，标签来源单列，不冒充候选响应自身字段。

实际新目录为`store_inventory_6b933eeef1574f298139bef1e3e767b1`，208行、133商品、174SKU、19分类。`category_reference_label`是参考分类名，`sku_price_number`是该行自身的SKU价格数值。56行来自已验证初始对，152行仍是分类候选；候选币种/单位保留UNKNOWN，源origin数值不作为已确认原价。旧完整结果和保护不变。

以下开发者命令在受控根下新建唯一0700目录与0600三件套，不覆盖，不启动网络或增加尝试；清单来自已有明确manifest，不扫描raw。用户无需运行Harness命令或写参数。

```sh
cd /Users/yoyi/爬虫
PYTHONDONTWRITEBYTECODE=1 python3 -B - <<'PY'
import json
from pathlib import Path
from collection_adapter.p29_receiver_control import _root, _read_owned
from collection_adapter.p29_store_inventory import publish_store_inventory
root = _root(Path('/Users/yoyi/爬虫/runtime-output/p29_pages_6b40659a625f432cb88672f2307adee8'))
manifest = _read_owned(root / 'category_candidates_6b9effd9ba9847b1a1e995660659f20b' / 'manifest.json', 128 * 1024)
result = publish_store_inventory(root, 'observation_0ac27a064fb5440887d339152b2411ed',
    [source['source_file'] for source in manifest['sources']])
print(json.dumps(result, sort_keys=True))
PY
```

见[逐行核对](reports/P29-window7-store-inventory-direct-check.json)、[分类价格核对](reports/P29-window7-category-price-context-review.json)和[250项验证](reports/P29-store-inventory-local-validation.json)。窗口7保持关闭，22个折叠引用无正文，此表不表示全店完成或P29已accepted。


## 窗口8：折叠引用的定向观察

[已有公开字段核对](reports/P29-folded-reference-source-review.json)确认22个折叠引用全部位于5个含不可售提示的分类组；组提示不替代逐商品状态，未见no_sale_dynamic_spus子结构，也未识别独立折叠加载路由。155个有序引用正文已取得，不需要为普通分类价差重复采集。

新根：/Users/yoyi/爬虫/runtime-output/p29_pages_01da14edd27e46d3ae2ebc9239c76055。窗口引用：result:7f8b869cb6f9492fb3b427afa6255410。固定CA复用，准确PID重新核对，新目标引用/独立输入锁。先[零尝试预检](reports/P29-window8-preflight.json)，再[接收器就绪](reports/P29-window8-receiver-ready.json)，最后[独立实际start](reports/P29-window8-started.json)；[当前快照](reports/P29-window8-current-status.json)为ACTIVE，两latch=OPEN且尚无业务输入。本窗口不是窗口7结果的补写或原锁重用。

用户保持小程序开启，从店铺返回小程序首页，再进入同一店铺。开发者先核对本窗口FOOD/PRODUCTLIST，按本次分类列表给出一个分类到底部的具体动作；不用逐商品打开，也不重复寻找旧轮已找不到的按钮。若实际加载产生已批准render响应，先核对当前请求归属及自身结构；新路由仅元数据，不能猜正文适配。用户stop、现有预算/隐私/解析/转发异常、接收器丢失或定向操作完成即按预检停止条件关闭，不自动重开。

复现控制入口：collection_adapter.p29_receiver_control.send_command(Path(上述新根), "status"或"stop")。只有本窗口自有FIFO/准确进程有效，已使用根不得重发start。准备失败不增加次数；当前实际开始1次，P29累计8次。关闭仍待真实收据，不将ACTIVE写成已清理。


## 窗口8实际失败及窗口9诊断验证

窗口8实际收到两份业务响应，在关联检查处停止。实际收据与清理分别见[关闭](reports/P29-window8-close-receipt.json)、[输出](reports/P29-window8-output-receipt.json)和[直接核对](reports/P29-window8-close-direct-check.json)。旧宿主未保留具体条件，因此不能推定店名、状态码或编号哪一项失败；两响应投影间隔约5毫秒，敏感拒绝只留键类别计数，不读私人值。窗口8当前文件已同步CLOSED，原预检/start与当时ACTIVE快照保持各自时点。

[诊断修复](reports/P29-association-diagnostic-local-validation.json)仅让P28/P29保留check_current_association已生成的布尔/null检查并通过既有association_check字段输出；旧合同已有该字段，无Schema改动。准备时null，完整配对时更新，生成检查失败先清前次值，关闭保留检查但清原文、请求租约和投影；不会把前次成功补给新失败。未改变目标、同观察或发布条件，77项相关测试及3个AST通过。旧窗口实际失败子项仍UNKNOWN，不按合成场景反推真实原因。

窗口9新根：/Users/yoyi/爬虫/runtime-output/p29_pages_0efec0f7c5744750a787652d075cffb3。引用：result:8ec833ed2d5446e6b228ab9e93378e65。重新检查准确PID，复用固定CA，用新引用/锁/0700根，先[零尝试预检](reports/P29-window9-preflight.json)、[接收器就绪](reports/P29-window9-receiver-ready.json)，再[单独实际start](reports/P29-window9-started.json)。[当前状态](reports/P29-window9-current-status.json)为ACTIVE、两个latch=OPEN、启动输入0，实际结果1次、P29累计9次；不是原窗口自动重试或原锁复用。

用户从店铺返回小程序首页，再进入同一店铺以产生新鲜FOOD/PRODUCTLIST；开发者先查本窗口无值关联检查，再安排必要分类动作，不逐商品打开或重复寻找旧按钮。当前诊断字段不包含名称、编号、状态码原值、原包或敏感错误。控制仍用collection_adapter.p29_receiver_control.send_command(Path(上述新根), "status"或"stop")；错误/预算/stop即关闭，无自动重开。


## 窗口9定位字符串编号差异，窗口10只查实际关系

[窗口9直接关联证据](reports/P29-window9-identity-association-direct-check.json)确认名称、成功码、时间和数字门店编号均通过；两个请求的字符串编号彼此相等，却均不等于当前响应公开字符串编号。[关闭](reports/P29-window9-close-receipt.json)与[输出](reports/P29-window9-output-receipt.json)确认旧窗口已完整清理且没有新结果。不能从这些布尔推定编码方案或别名角色，也不能回读已清理原文。

[本地验证](reports/P29-routing-id-relation-local-validation.json)支持新增collection_adapter/p29_id_relation.py及封闭p29-routing-id-relation-v1合同。只在本次店名、两组数字编号、成功码、时间和请求间一致性通过后比较既有public routing字符串；其长度/格式、额外一次URL解码比较及NFKC去空格比较均为诊断布尔/null，不返回规范化值或提升规则资格。私人成员始终不解码，错误目标、数字编号、请求间不等或失败状态码均阻止参数再读；既有输出预算和关闭清理保留。84项相关测试、4个AST和1个Schema通过。

窗口10新根：/Users/yoyi/爬虫/runtime-output/p29_pages_6d7719c5ee034789b432fe22c1499d06。引用：result:d3d79b8cb3c0496c9ba820726c00ba26。复用固定CA，准确PID重新核对，新引用/锁/0700根；先[零尝试预检](reports/P29-window10-preflight.json)、[接收器就绪](reports/P29-window10-receiver-ready.json)，再[独立start](reports/P29-window10-started.json)。[当前快照](reports/P29-window10-current-status.json)为ACTIVE、两latch=OPEN、启动业务输入0；本根结果1次，P29累计10次。未读取本轮编号值，真实格式/编码/角色仍UNKNOWN。

用户只从店铺返回小程序首页、再进入同一店铺；本轮不切分类或逐商品点开。如果现有关联仍失败且前置scope通过，关闭前只写0600 routing_id_relation_<新引用>.json，其业务记录0、mapping_rule_qualified=false，原关联失败及清理行为保持；若前置scope不通过，则不再读或写此编号探针。若原完整关联自然通过，沿用原完整发布，开发者核对本次输入后stop。控制继续用自有FIFO status/stop，不自动重试或重开。


## 窗口10实际编号关系与窗口11数字门店绑定

[窗口10直接核对](reports/P29-window10-id-relation-direct-check.json)与[关闭](reports/P29-window10-close-receipt.json)、[输出](reports/P29-window10-output-receipt.json)分别记录实际输入和完整清理。早先[无业务输入快照](reports/P29-window10-no-business-input-direct-check.json)是本次输入到来前的事实，不能当成最终状态；原预检、ready和start保持各自时点。编号值已随旧窗口清理，未回读raw。

[新规则本地验证](reports/P29-numeric-store-binding-local-validation.json)对应collection_adapter/p29_store_identity.py与collection_core/p29_source_association.py。只在当前店名、两请求数字编号、请求字符串彼此一致、成功码与10秒同观察均通过后建立显式数字门店关联。新proof保持两个请求字符串与响应字符串不等的真实布尔，string_id_role=UNCONFIRMED；它不提供别名或编码算法。旧默认P26/P28规则不变，P29需显式--bind-through-current-numeric-store-ids。新公开投影/汇总/空观察/分类检查分别使用版本化合同，旧合同原件不变。分类隔离使用本次FOOD/PRODUCTLIST请求的字符串编号，不能把响应编号补回请求；分类价格单位/币种与完整性仍不提升。

窗口11新根：/Users/yoyi/爬虫/runtime-output/p29_pages_3da2bc6244554274a40c6db57359cd42；引用result:000306665c1143e38d0be9f073b64e15；固定CA复用，准确PID42372重新核对，接收器17801。先[零尝试预检](reports/P29-window11-preflight.json)与[接收器就绪](reports/P29-window11-receiver-ready.json)，再[独立start](reports/P29-window11-started.json)。[当前状态](reports/P29-window11-current-status.json)在start时为ACTIVE/输入0、两latch=OPEN、本根结果1次/P29累计11次，不能把准备或本地验证当成真实新规则通过。

用户关闭美团小程序窗口，再从微信重新打开同一小程序和店铺，回复好了；先不切分类或点商品。开发者先核对本窗口完整对与新proof，再据本次实际分类给出必要的一个动作。控制继续使用collection_adapter.p29_receiver_control.send_command(Path(上述根), "status"或"stop")；本根已start，不重复start。错误、预算、用户stop或本次定向核对完成即关闭，未拿到结果保持incomplete，不自动重开、资格提升或退场。


## 窗口11转发层结束与窗口12继续核对

[窗口11直接核对](reports/P29-window11-forwarding-close-direct-check.json)、[关闭](reports/P29-window11-close-receipt.json)与[输出](reports/P29-window11-output-receipt.json)确认1个原始回调/业务响应0，新绑定没有执行；FOOD/PRODUCTLIST请求元数据已观察，具体失败路由和原因未记录，不能从请求顺序反推失败对象。目标TLS握手通过，接收器17801退出、cleanup=COMPLETE、活动stream0、两latch=CLOSED、输出完整。原启动和上一轮交回检查保留各自时点，当前快照已CLOSED。本轮未改代码、读取敏感错误或宽松跳过失败。

窗口12新根：/Users/yoyi/爬虫/runtime-output/p29_pages_74f4b9d1127f406a8f74e1d9aea86066；引用result:10c3291852d342298c9ea9620af58ab3；接收器34372，准确网络PID42372重新查证、固定CA复用，新目标引用和锁。先[零尝试预检](reports/P29-window12-preflight.json)、[接收器就绪](reports/P29-window12-receiver-ready.json)，再[独立start](reports/P29-window12-started.json)；[当前状态](reports/P29-window12-current-status.json)启动时ACTIVE/业务输入0，本根结果1次、P29累计12次、两latch=OPEN，真实新规则仍待输入验证。

用户保持小程序开启，从店铺返回小程序首页，再进同一店铺。开发者先核对本次完整对，再安排必要分类动作。控制仍为collection_adapter.p29_receiver_control.send_command(Path(上述根), "status"或"stop")，已start的根不重复start；错误/预算/stop或本次定向核对完成即关闭，不自动重放、重试或重开，也不提升资格。

## 窗口12完整对已通过，继续当前分类输入

[本次真实直接核对](reports/P29-window12-numeric-binding-real-pair-direct-check.json)确认显式数字门店关联实际执行并通过；49条分类SKU记录、32个商品、45个SKU及4个有正文分类的JSON/CSV/manifest一致，商品名、规格、价格、时点和当前FOOD门店字段逐条一致。元/CNY仍依据已有P28页面确认规则，本窗口没有新的页面逐价核对；两个请求字符串对响应字符串的不等布尔保留，含义UNCONFIRMED。独立三件套位于当前根下observation_448d4e25788a415f9ddb81587faae859，目录0700、文件0600且被Git忽略。

本窗口初始响应自己定义19分类和154个有序分类商品引用，已有正文34个、尚缺120个；另24个折叠引用缺正文。分类顺序及引用以本次输入为准，不使用窗口7的序号或业务值。接收器34372仍ACTIVE，原窗口/输入锁/固定CA继续有效，识别0/结果1、P29累计12次；无需退出重进或重复start。用户把左侧分类从上到下浏览一遍，每类把商品列表滑到底，不点开商品；开发者核对本次新绑定render和参数/响应关系后再给必要动作。

此时新绑定render尚未观察、金额单位/币种仍UNKNOWN，折叠商品逐项状态及全店终止仍UNCONFIRMED，不能凭19分类或初始49行声称全店完成。当前status是可更新快照；原preflight/ready/start/handoff是原时点收据，保持原件。本窗口仍使用自有FIFO status/stop，错误、预算、用户stop或本次定向分类核对完成即关闭，不自动重开。

## 窗口12加载故障后已关闭，用户确认恢复

[关闭](reports/P29-window12-close-receipt.json)、[输出](reports/P29-window12-output-receipt.json)和[恢复直接核对](reports/P29-window12-loading-recovery-direct-check.json)确认2026-10-11T09:35:55.896651+00:00开发者stop后接收器退出、活动stream0、两latch=CLOSED、cleanup=COMPLETE、intercept_cleared=true及诊断输出完整。用户随后明确恢复正常；原有固定CA保留，系统代理启用值0，没有系统设置写入或新证书。前一节ACTIVE和分类操作说明是此前状态，当前窗口已经结束，原控制根不得再次start。

关闭发布collection_30d8c00af0ed4df1a473477001e2a9f4，49条记录/32商品/45SKU/4个有正文分类，JSON/CSV/manifest及本次初始完整记录逐条一致；仍PARTIAL，来源proof为p29-numeric-store-association/v1。原字段category_product_references_not_loaded=24按实现只算折叠成员；本次有序引用缺120个，另折叠缺24个，应以直接审计一并阅读，不能把24当全部缺口。初始定义19分类没有证明终止；分类render输入0。

当前没有记录到TLS、HTTP、连接、引擎、dispatch或async失败，准确网络PID仍为当前socket owner。已安装引擎中合成UDP双向透传和既有NextLayer优先规则6项检查通过，无socket/真实输入/内核扩展验证；不能从合成通过反推现场没有故障，也不能据125个不透明UDP计数认定UDP导致卡顿。本轮保持采集关闭，只本地诊断，加载机制UNKNOWN；未改代码、放宽隐私或自动重开。用户目前无需继续分类操作。

## D1原样透传对照与D2准备

用户随后要求查明原因。D1使用现有入口，不传任何解密域名或正文、解析参数；实际窗口于2026-10-11T10:16:42.997378+00:00开始、10:21:41.429581+00:00显式stop结束。新根识别1/结果0，P29诊断累计1、结果累计12。[直接核对](reports/P29-forwarding-D1-direct-check.json)、[关闭](reports/P29-forwarding-D1-close-receipt.json)、[输出](reports/P29-forwarding-D1-output-receipt.json)记录54次TLS透传、50个UDP层、104次上游连接、HTTP/正文/解析0、失败计数0；宿主退出、活动stream0、两latch=CLOSED、cleanup=COMPLETE。用户“好了”仅确认操作完成，切分类后的实际加载结果仍待明确，不把计数当作页面成功。

[软件直接核对](reports/P29-forwarding-software-direct-check.json)比较的是软件文件字节，没有生成值哈希或读取业务输入。应用与唯一已安装扩展副本和mitmproxy_macos0.12.11安装包相同，未发现旧副本残留；这不能排除当前版本自身问题。

D2只在D1页面结果明确后选用：解密此前已识别的目标域名，检查安全路由元数据，正文处理和商品解析保持关闭，以区分TLS/HTTP转发与正文处理。已建立新引用和0700/Git忽略根，[预检](reports/P29-forwarding-D2-preflight.json)通过，来源仍UNKNOWN、尝试0、两latch=CLOSED；尚未启动接收器或窗口。固定CA继续复用，不改系统设置。

以下只读命令可复现D2准备，不读取回调或消耗尝试：

```sh
/Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B -m collection_adapter.p26_identification_host \
  --output-root /Users/yoyi/爬虫/runtime-output/p29_tls_forwarding_diagnostic_1b667dccd50c473a80aa218d0744bd4d
```

若D1原样透传也加载失败，先查原生捕获/转发连接层；若D1正常，则由开发者准备D2接收器，加`--serve-identification --inspect-current-domain wx.waimai.meituan.com`，核对就绪零尝试后单独`start`。用户仅按提示完成同店分类动作；结果明确即`stop`，核对实际关闭收据、输出收据、宿主退出和两latch关闭。无自动重试；有界计数、并发64、诊断输出1MiB预算保留，正文检查预算为0。对照不产生商品结果，也不完成P29。

## D2未经过目标链路，D3识别当前路由

用户已明确“好了”表示页面正常。[D1页面结果](reports/P29-forwarding-D1-page-outcome.json)记录本次原样透传动作正常；旧待答检查保留当时时点。D2一度在接收器准备阶段因进程身份预检拒绝，尚未start、零尝试；[直接核对](reports/P29-forwarding-D2-precheck-refusal.json)保留拒绝子因UNKNOWN及随后准确PID/socket归属通过的事实，不虚构修复。

D2实际识别1/结果0，2026-10-11T12:17:49.419970+00:00用户动作完成后开发者stop。[直接核对](reports/P29-forwarding-D2-direct-check.json)、[关闭](reports/P29-forwarding-D2-close-receipt.json)、[输出](reports/P29-forwarding-D2-output-receipt.json)确认页面NORMAL、119次上游连接、错误计数0，但所选域名握手和HTTP计数均0，目标测试为UNEXERCISED。不能用页面正常声称解密层正常。宿主93033已退出、活动stream0、两latch=CLOSED、cleanup=COMPLETE，固定CA保留。[扩展资源可见性](reports/P29-forwarding-D2-extension-resource-visibility.json)只确认扩展进程；未提权的FD查询不可见，实际FD数量UNKNOWN，不能把可见0当成没有占用。

D2的TLS元数据实际出现apimobile.meituan.com，仅确认域名，接口用途和店铺归属仍UNKNOWN。D3保留原wx域名，并只加入这一已观察域名做安全路由元数据识别；不自动读正文或扩大业务目标。新根为`/Users/yoyi/爬虫/runtime-output/p29_current_routing_diagnostic_91f6ffc103f841fdb47677a21f6e9899`，准备、就绪均零尝试，[实际start](reports/P29-forwarding-D3-started.json)为2026-10-11T12:24:53.262512+00:00。新根识别1/结果0，P29诊断累计3、结果累计12，宿主8216，LIVE_CAPTURE_LATCH=OPEN、EXECUTION_LATCH=CLOSED。此前P26一次helper重启收据是历史已执行动作，不构成本次再终止进程的许可。

以下是D3实际宿主命令，此根已start，不能复用或再次start：

```sh
/Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B -m collection_adapter.p26_identification_host \
  --output-root /Users/yoyi/爬虫/runtime-output/p29_current_routing_diagnostic_91f6ffc103f841fdb47677a21f6e9899 \
  --serve-identification --inspect-current-domain wx.waimai.meituan.com \
  --inspect-current-domain apimobile.meituan.com
```

用户从美团小程序首页重进已确认同店一次；开发者核对目标握手、实际路由及HTTP层是否进入。只有真实经过的层才标为已测试；没有握手/路由保留UNEXERCISED。结果明确或错误/预算/stop即关闭，核对本根关闭和输出收据；正文检查预算0，其余并发、诊断、结构预算及隐私保护保留，不重放或自动UI。

## D3关闭与窗口13完整处理对照（历史启动，现已关闭）

D3已完整关闭；用户正常，目标TLS和HTTP实际进入，8次请求/8份响应头、固定错误0。正文和商品解析没有打开，因此不证明业务关联或完整响应结束。[直接核对](reports/P29-forwarding-D3-direct-check.json)保留当次真实证据，加载机制仍UNKNOWN。

新增p26-forwarding-http-progress/v1是单独的无值协议，旧诊断合同保留。status先输出P26_FORWARDING_HTTP_PROGRESS，再输出原P26_MONITOR_STATUS。pending_by_phase分别指REQUEST_BODY、RESPONSE_HEADERS和RESPONSE_BODY；http_responses_completed记录引擎响应结束钩子，已用流式上游EOF验证，不能当作客户端送达、业务成功或解析通过。等待区间只作诊断，不增加时间上限；跟踪超出64项时标tracking_incomplete，不改变转发。关闭时先冻结未完成阶段并清跟踪，再关闭自有连接；0600文件名为forwarding-http-progress-<窗口引用的随机部分>.json，完整名称由P26_FORWARDING_HTTP_PROGRESS_CLOSED事件给出，禁止覆盖或复用。文件写失败输出P26_FORWARDING_HTTP_PROGRESS_OUTPUT_INCOMPLETE，不阻止核心清理。

窗口13根：`/Users/yoyi/爬虫/runtime-output/p29_pages_fef1c09a12e445229627b08c376b0eb8`；引用`result:5c0691de4db54618ae90455608333510`；宿主44880、准确网络PID42372。[预检](reports/P29-window13-preflight.json)列明来源范围、1MiB单响应、4MiB总输入、32观察、64并发及输出预算。固定CA、手动页面和敏感键/路径/类型能力沿用当前持续授权，不新增证书、系统设置、UI或重放。本根先准备零尝试，再实际开始1次；识别累计3与结果累计13分开，不把准备或诊断算成功采集。

这是实际宿主参数；本根已start，不再次运行或start：

```sh
/Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B -m collection_adapter.p26_identification_host \
  --output-root /Users/yoyi/爬虫/runtime-output/p29_pages_fef1c09a12e445229627b08c376b0eb8 \
  --serve-identification --inspect-current-domain wx.waimai.meituan.com \
  --batch-public-json --identify-field-layout-only \
  --inspect-sensitive-field-keys --inspect-public-fields \
  --analyze-store-pages --identify-category-render --bind-through-current-numeric-store-ids
```

当时要求从小程序首页重进同店一次，用户已回复好了，表示正常完成；该动作不再待办。开发者实时核对新HTTP阶段、业务匹配、解析及发布；本次定向核对完成或错误/预算/stop即关闭，不自动重新启动。新root的FOOD/PRODUCTLIST仍须当前响应/请求数字关联及10秒同观察，render正文须先验证本次请求归属，不复用旧编号或猜字段。

控制当前自有FIFO：

```sh
python3 -B - <<'PY'
from pathlib import Path
from collection_adapter.p29_receiver_control import send_command
root = Path.cwd() / 'runtime-output/p29_pages_fef1c09a12e445229627b08c376b0eb8'
send_command(root, 'status')  # 关闭时改为stop；没有自动重开。
PY
```

窗口13现已CLOSED，两latch=CLOSED、接收器退出，关闭证据见[本轮直接核对](reports/P29-window13-recovered-close-direct-check.json)；D3的关闭收据只用于D3。上述控制命令是历史操作，不应对已关闭根再次start。阶段协议与合成验证见[诊断验证](reports/P29-http-progress-local-validation.json)，P29仍incomplete。


窗口13关闭汇总位于原根下`collection_cf171b3a52ba4705b2fb8afea1f27b0d/`，三件套已核对56条/31商品/43SKU/7个有正文分类。原初始观察保持不变。当前没有待执行的页面动作；下一现场步骤须针对分类正文缺口，不能以重复重进代替分类分页验证。本次缺115个有序分类成员和22个折叠成员正文，计数属于本窗口；窗口7的208行视图独立保留，不跨窗口混价补值。


## 窗口14：分类列表连续滑动（已关闭）

用户再次明确继续后，新根 /Users/yoyi/爬虫/runtime-output/p29_pages_e5823d6f18134a7a8c01a70e787334a3 已在2026-10-11T15:09:59.996169+00:00实际start，宿主19916、准确网络PID42372，两latch=OPEN，固定CA复用。预检/就绪零尝试与实际start分别保存；见[当前状态](reports/P29-window14-current-status.json)。不再次运行start，不复用任何旧窗口。

当时页面动作已由用户正常完成：重进同店并连续向下滑动右侧商品列表至末尾；该动作不再待办。用户“好了”表示正常完成。开发者从本根无值status及各自公开投影核对新输入、HTTP阶段和分类关系，必要时仅给有依据的具体补充动作；完成定向核对或错误/预算/stop即通过自有FIFO关闭并核对清理，不自动重试。窗口13的关闭事实和结果保持不变。


窗口14于2026-10-11T15:13:08.345591+00:00自动关闭，宿主退出、清理完成、两个latch=CLOSED；见[直接核对](reports/P29-window14-category-rejection-direct-check.json)。上段OPEN属于历史启动状态，旧根不得重开。分类scope拒绝7次，但原诊断不能区分具体编号条件；本地已修复FORM完成缓冲误计并发，并增加category_render.last_scope_check三个布尔，详见[验证](reports/P29-request-collector-scope-diagnostic-local-validation.json)。新增字段只诊断，不授予读取被拒绝响应正文的资格。当前没有页面操作或运行中的采集窗口；下一次明确现场继续须新根、新锁与当前PID预检，先读具体匹配结果再决定适配，不重复原步骤假装新证据。


## 窗口15：分类编号关系定向验证（已关闭）

新根 /Users/yoyi/爬虫/runtime-output/p29_pages_0757d897d1674ece92d316ba58d9b1a7，宿主33875、当前网络PID42372，2026-10-11T15:25:09.644409+00:00实际start，两个latch=OPEN，固定CA复用。见[预检](reports/P29-window15-preflight.json)、[就绪](reports/P29-window15-receiver-ready.json)、[实际开始](reports/P29-window15-started.json)和[当前快照](reports/P29-window15-current-status.json)。

本窗历史页面步骤：从美团首页重进已确认同店，向下滑动右侧列表触发分类加载即可，不要求反复滑到底。用户“好了”表示正常完成。开发者通过本根FIFO status读取category_render.last_scope_check，再据实际关系判断，不读取被拒绝响应正文或旧raw；获得定向事实后及时stop并核对进程、活动流、latch和输出。不要重复start，不自动重试。窗口14及更早窗口的状态、锁和结果不能作为本窗新鲜证据。

窗口15已自动关闭，用户页面步骤完成；上段OPEN只表示历史启动事实。55条自身结果核对通过，分类关系未触发，TLS具体原因UNKNOWN。当前两个latch=CLOSED，没有待做页面操作，不重开旧根或自动重试。见[关闭核对](reports/P29-window15-tls-close-direct-check.json)及[HTTP阶段](reports/P29-window15-http-progress-close-receipt.json)。

离线TLS状态诊断已补充并验证：upstream_transport_state与client_transport_state均为固定枚举，不读自由错误文本。失败收据可用它们区分连接状态，不能据此直接认定根因。窗口15没有这些历史字段，不补写；当前没有运行窗口。见[验证收据](reports/P29-tls-transport-state-local-validation.json)。


## 窗口16：TLS与分类定向验证（已关闭）

用户在单次验证说明后明确“继续”。新根 /Users/yoyi/爬虫/runtime-output/p29_pages_61fdcb8852d44035a207356edc67db51，窗口引用result:aac626af8d5841078a7bcb3110a6e60a，宿主61851。重新查证小程序父进程91545、准确网络进程42372的UID、直接父子关系及唯一socket归属；沿用固定CA，不改系统设置。先预检和接收器就绪，零尝试且两latch=CLOSED；2026-10-11T15:55:12.502514+00:00另行发送start后ACTIVE、两latch=OPEN。本根识别0/结果1、P29诊断累计3/结果累计16，启动输入和发布0，source_ready=UNKNOWN。

用户从小程序首页重进同店，向下滑动右侧列表触发一次分类加载；“好了”表示正常完成，卡住或错误需直接反馈，不反复重进。若TLS失败，读取本窗固定状态枚举；若正常，检查分类三项编号关系。定向结果或错误/预算/stop立即关闭，无自动重试。本窗口不能凭已启动声称分类匹配、TLS修复或全店完成。

证据：[零尝试预检](reports/P29-window16-preflight.json)、[接收器就绪](reports/P29-window16-receiver-ready.json)、[独立实际开始](reports/P29-window16-started.json)、[当前快照](reports/P29-window16-current-status.json)。控制使用本根collection_adapter.p29_receiver_control.send_command，已start，不重复start；status/stop须先准确核对自有进程。

窗口16定向关系已取得并关闭，用户页面步骤完成。分类三项关系false/true/true，未读被拒绝正文；HTTP9次完整、TLS失败0。两个latch=CLOSED、宿主退出、清理完成，固定CA保留。以上OPEN和页面步骤属于历史启动状态。见[本窗核对](reports/P29-window16-category-id-relation-direct-check.json)。下一步是合成数据上的分类路由关联修复，不重复页面操作；本轮未改匹配规则。

分类路由关联修复已本地完成：同时核对当前响应数字编号和公开字符串，不回退初始请求selector。新输出v4记录CURRENT_RESPONSE_PUBLIC_STRING，旧v3不改义；95项相关用例通过。当前仍无运行窗口或页面步骤，不能据本地通过认定全店采集完成。见[验证](reports/P29-category-public-string-binding-local-validation.json)。


## 窗口17：修复后的分类路由验证（已关闭）

用户要求不要停在本地验证，继续推进同店工作；本次新建根 /Users/yoyi/爬虫/runtime-output/p29_pages_f5412e6344c24323bbe056390e1e6066，窗口引用result:3f734c0507004ed293f91d023d4fcf6b。重新核对当前父91545及网络PID42372的UID、直接父子关系与唯一socket归属；固定CA复用，新引用/锁/0700忽略根，未改系统设置。

预检与接收器80520就绪时零尝试、两latch=CLOSED；2026-10-11T16:18:13.920328+00:00独立start后ACTIVE、两个latch=OPEN，本根识别0/结果1，P29诊断累计3/结果累计17。启动业务输入0、发布0，source_ready=UNKNOWN；准备和启动不证明修复已实际通过。

需要用户从小程序首页重进同店并向下滑动右侧列表，触发一次分类加载，完成回复“好了”；卡住直接说明，不反复重进。开发者接着核对新关联、v4自身分类输出和候选资格，处理已授权范围内本地问题，不停下等待重复“继续”。定向结果或错误/预算/stop即关闭，不自动重试或扩展范围。

[预检](reports/P29-window17-preflight.json)、[就绪](reports/P29-window17-receiver-ready.json)、[独立开始](reports/P29-window17-started.json)、[当前状态](reports/P29-window17-current-status.json)。本根已经start，不重复start；控制仍为自有FIFO和准确进程核对。


窗口17中途检查：用户正常重进与滑动后，本窗发布56条初始完整记录，公开投影逐行核对通过；19个源分类中前7项有正文，当前顺序第8项loaded_rows=0。TLS与HTTP失败0，分类inspected=0、rejected=0，属于分类请求尚未触发，不能声称修复通过。原宿主80520继续ACTIVE，两latch=OPEN，没有再次start或新窗口。已请用户保持页面，点击左侧第8分类；不用退出重进。证据：docs/harness/reports/P29-window17-initial-only-check.json。


## 窗口17关闭与下游参数校验补齐

用户完成第8分类操作，两个分类请求均通过新双编号匹配，v4响应码均ZERO，scope拒绝0。分类公开投影解析为19条候选、11商品、19SKU、2分类；初始完整结果56条、31商品、43SKU、7分类，独立合同/公开来源/JSON/CSV/manifest/权限核对通过。2026-10-11T16:26:13.516067+00:00stop后宿主80520退出、活动锁消失、stream0、清理COMPLETE、两latch=CLOSED、固定CA保留。[直接核对](reports/P29-window17-category-match-direct-check.json)、[分类审阅](reports/P29-window17-category-review.json)、[关闭](reports/P29-window17-close-receipt.json)、[输出](reports/P29-window17-output-receipt.json)、[HTTP](reports/P29-window17-http-progress-close-receipt.json)。

判断：分类关联修复确实通过，但参数证明因同一旧selector复核漏改而缺失（怎么确认的：两份参数probe均SCOPE_UNAVAILABLE；p29_batch_parameter仍比较target.poi_id_str；合成实际addon回调完整路径复现该结果，并且旧selector被替入后错误进入参数解码）。候选导出准确报P29_CATEGORY_EXPORT_PROOF_MISMATCH，未绕过保护、未将19条候选冒充完整业务记录。上轮95项测试只分别覆盖关联和手工构造的导出proof，漏掉了新数字关联下的参数guard链路。

已将参数guard同步为当前响应公开字符串与数字编号双项复核，初始对规则不动；增加请求/响应流回调→参数证明→v4审阅→清单导出的完整合成测试，以及任一编号被替换时在参数解码前拒绝的测试。两项先红后绿，7模块97项全部通过，2个AST及git diff检查通过。[本地验证](reports/P29-category-batch-public-string-local-validation.json)。窗口17请求数据已清理，缺失证明不可能事后合法补录，因此没有重新导出或篡改旧收据。

## 窗口18：参数证明与清单导出定向验证（已关闭）

按照用户“不反复等继续、必要时通知页面动作”的同店持续推进指令，实质修复后新建根 /Users/yoyi/爬虫/runtime-output/p29_pages_327da07d3797411893f8c2e1a98664b8，窗口result:b85034fd2d5f4c48ac52ab781835e815，宿主93567。重新核对父91545/网络42372的UID、直接子进程及唯一socket归属；固定CA复用，新引用/锁。零尝试预检及就绪后，2026-10-11T16:29:23.300849+00:00独立start，当前ACTIVE、两latch=OPEN，本根识别0/结果1，累计诊断3/结果18，启动业务输入0、发布0，source_ready=UNKNOWN。

必要页面动作：从小程序首页重进同店，初始列表出现后点击左侧第8分类，加载完成回复“好了”。开发者随后直接检查参数成员关系与导出结果；错误、预算、stop或定向结果即关闭，不自动盲目重试。[预检](reports/P29-window18-preflight.json)、[就绪](reports/P29-window18-receiver-ready.json)、[实际开始](reports/P29-window18-started.json)、[当前状态](reports/P29-window18-current-status.json)。新鲜证明未到前不宣称导出已修复现场通过；P29仍active/incomplete。

窗口18完整链路验证通过并关闭。74行同窗清单已保存（55初始完整+19分类候选），实际文件与来源核对通过；两latch=CLOSED、宿主退出、清理完成。当前无页面步骤。剩余全店覆盖和终止未确认，不重复此缺陷的定向验证。见[直接核对](reports/P29-window18-export-chain-direct-check.json)与[清单收据](reports/P29-window18-inventory-export-receipt.json)。


## 窗口19：继续全店分类与折叠覆盖（已关闭）

用户明确“继续做啊”，在窗口18定向修复通过后继续P29全店覆盖。新根 /Users/yoyi/爬虫/runtime-output/p29_pages_003b896bb92941eb9115e3c9202e26e5，窗口result:57219e7bdc8c43e884eb405a59cb3512，宿主2974。当前父91545/网络PID42372的UID、直接子进程和唯一socket归属重新核对，固定CA复用，新引用/锁/0700忽略根。预检及就绪零尝试、两latch=CLOSED；2026-10-11T16:37:52.631721+00:00独立start后ACTIVE、两latch=OPEN，本根识别0/结果1，P29累计诊断3/结果19。启动业务输入0/发布0，source_ready=UNKNOWN。

用户必要页面步骤：从小程序首页重进同店，按左侧顺序浏览全部分类，每类等商品出现后把右侧列表滑到底；存在“展开/更多商品”列表入口时展示更多商品，不加购、不下单。全部完成回复“好了”，卡住立即反馈。开发者随后直接核对本窗覆盖与自身proof并导出，发现局部本地问题直接修复；不能把页面完成或新19分类计数替代缺失正文和全店终止证据。

[预检](reports/P29-window19-preflight.json)、[就绪](reports/P29-window19-receiver-ready.json)、[开始](reports/P29-window19-started.json)、[当前状态](reports/P29-window19-current-status.json)。原窗口18已关闭、74行清单独立保留，本窗不使用旧编号/输入锁/额度或跨窗补价。错误、预算、用户stop即关闭，不自动重试；P29仍active/incomplete。


## 窗口19中途：全部有序分类引用已覆盖，折叠入口待核对

用户正常完成全部分类浏览。本窗14份v4响应均ZERO、分类拒绝0，125组请求分类/商品成员与各自响应完全匹配。候选输入172行、按自身SKU/分类保留最新整行后152行；加55条初始完整记录，共227输入行去重20行，形成207行清单、133商品、174SKU、19分类。合同、JSON/CSV/manifest、集合计数、各行自身公开来源、标签引用、权限与Git忽略核对通过；候选币种/单位UNKNOWN，未提升为完整记录或正式Parser/Provider。

19分类的155个有序引用全部有正文，缺失0。22个折叠引用分布在本窗第9/11/12/13/16分类，各4/10/3/4/1项；它们是22个不同商品，在其他类别也没有商品正文。因此不能将“19分类都有行”或“有序引用全覆盖”写成全店所有商品完成。

已保存实际清单runtime-output/p29_pages_003b896bb92941eb9115e3c9202e26e5/store_inventory_0e525899e41e402db083d152aab676a0/，候选目录同根category_candidates_c7f9d32a9417467d83a165e393d9c5e4/。这是当前时点快照，不覆盖旧结果。[覆盖与文件核对](reports/P29-window19-visible-coverage-check.json)、[清单导出](reports/P29-window19-visible-inventory-export-receipt.json)、[候选导出](reports/P29-window19-visible-candidate-export-receipt.json)、[审阅](reports/P29-window19-visible-category-review.json)。

原窗口继续ACTIVE、宿主2974、两latch=OPEN，没有重启或另开窗口。已请用户检查第11分类有无“展开/更多商品/查看全部”列表入口；有则展开并等待加载，无则明确反馈。仅这一缺失页面事实待输入，不重复遍历全店。终止语义仍UNCONFIRMED，P29 active/incomplete。


窗口19折叠进展：用户明确第11/12/13类均有入口且已展开，本窗新增3份匹配响应，17个对应折叠引用全部有正文。当前计算结果224行/150商品/191SKU，候选169行；155有序引用仍全部覆盖。仅第9类4个及第16类1个折叠引用待核对，已通知用户只检查这两类；原窗口ACTIVE，无再次start。旧207行导出保持历史快照，当前224行尚未发布新文件。见docs/harness/reports/P29-window19-folded-progress.json。

窗口19最终关闭：本轮初始声明的155个有序+22个折叠引用全部有正文，实际分类商品集合与声明集合完全相等，缺0、额外0。最终233行清单已发布并核对，仍含178分类候选；不提升资格或声称平台终止。宿主退出、清理完成、两latch=CLOSED、固定CA保留。以上页面动作已完成，当前无待做操作，不重开旧根。见[最终核对](reports/P29-window19-final-coverage-direct-check.json)和[清单收据](reports/P29-window19-final-inventory-export-receipt.json)。


## 窗口 20：公开分类分页终止证据

2026-10-12 窗口 20 已实际启动：用户单独授权本次同店公开列表/分类分页采集，并确认只保留目标小程序停在首页。新根 `/Users/yoyi/爬虫/runtime-output/p29_pages_5d1758a4492b46adaa43c7d28d51ebac`，引用 `result:95603d43ee81435d9923a0033e8b1d56`，准确网络 PID 42372、宿主 49678；重新核对进程/固定 CA 后先准备零尝试，再于 `2026-10-12T13:04:26.249917+00:00` 单独 start。本根结果尝试 1，P29 历史累计结果 20；两 latch=OPEN，启动时业务输入/发布均 0，source_ready=UNKNOWN。现等待用户进入同店加载初始列表，再按本窗口声明集合核对分页；不重开旧根、不复用旧输入，不采图片/私人值，不改系统配置、不自动 UI 或重试。当前焦点为 P29，不扩展 P32。证据：`docs/harness/reports/P29-window20-preflight.json`、`docs/harness/reports/P29-window20-receiver-ready.json`、`docs/harness/reports/P29-window20-started.json`。

操作：用户从当前小程序首页进入原店铺，先等待初始列表加载；开发者核对新鲜目标及本窗口声明集合后给出后续必要列表动作。结束条件为本轮定向列表动作及证据核对完成，或用户 stop、转发/隐私/范围/预算异常。无充分终止证据时如实保留 UNKNOWN，不自动增加窗口或修改校验来完成验收。控制沿用自有 FIFO 的 status/stop，不能重复 start。


窗口 20 初始列表已核对：本次 FOOD/PRODUCTLIST 同观察与自身结果验证通过，54 行、30 个不同商品、40 个 SKU、19 个分类。初始声明 155 个有序和 22 个折叠分类商品关系；仍缺 115 个有序及 22 个折叠正文。第 1/2/4/5/6 类声明关系已齐，已请用户只浏览第 3 类和第 7–19 类并展开列表入口，最后继续翻一屏反馈终止提示或加载变化。部分缺正文分类同时标 has_next_page=false，已取得该标记不足以单独证明终止的当前反例；不将其改判全店完成。原窗口继续 ACTIVE，无再次 start。证据：`docs/harness/reports/P29-window20-initial-coverage-check.json`。


2026-10-12 窗口 20 已停止：用户报告滑动过程中跳转验证中心，开发者立即通过本窗口自有 FIFO 发送 stop。已核对宿主 49678 退出、host-active.lock 消失、cleanup=COMPLETE、intercept_cleared=true、两 latch=CLOSED；实际结果尝试仍为 1，没有重试或开启新窗口。验证出现以用户报告为依据，具体触发原因 UNKNOWN；未操作验证页面或读取验证正文。已发布的 54 行初始结果和此前窗口 19 交付保留，全店分页终止仍未确认。当前无页面采集任务，不继续要求滑动，不扩展 P32。关闭证据：`docs/harness/reports/P29-window20-verification-stop-check.json`、`docs/harness/reports/P29-window20-close-receipt.json`、`docs/harness/reports/P29-window20-output-receipt.json`。


2026-10-12 恢复原计划工作：用户报告重启微信后恢复，故障根因仍 UNKNOWN。窗口20保持关闭，未开启新采集。中断前15份分类投影及初始观察已核对并独占导出220行、144商品、189 SKU、19分类；四表CSV/JSON、字段字典、状态清单及manifest核对通过。当前缺12个声明关系：第12类折叠3、第13类折叠4、第19类有序5；旧窗口有这些历史记录，但不跨窗补成当前记录。新旧无新增商品/SKU，215个共有键价格数值一致；第2类声明关系新增/移出各3个，形成5个新分类商品SKU键。旧233行人民币元交付保留。当前等待用户补充验证前是否到第19类末尾及终止提示，不要求重做页面操作。证据：docs/harness/reports/P31-window20-fields-direct-check.json、docs/harness/reports/P29-window20-membership-change-review.json。


2026-10-12 用户补充：上次跳验证前未滑到最底部，因此窗口20没有末页终止证据。按用户重启微信恢复后明确继续原工作的指令，准备窗口21的一次同店定向观察；目标仅新鲜初始列表、第12/13类折叠项和第19类末尾，实际分类序号须按新鲜身份核对。新根及控制引用已建立，重查当前父进程46626、网络进程46630与固定CA通过；当前等待用户停在目标小程序首页，接收器未启动、两latch=CLOSED、尝试0。不复用旧根、不跨窗补记录，不把定向窗口当作全店当前完整快照。若再次报告验证则关闭，不自动重试。证据：docs/harness/reports/P29-window20-user-terminal-fact.json、docs/harness/reports/P29-window21-targeted-preparation.json。


2026-10-12 窗口21已启动：用户确认目标小程序首页后，重新prepare通过，接收器90436先核对PREPARED/零尝试/两latch=CLOSED，再于2026-10-12T16:03:28.783696+00:00单独start。窗口引用result:4c55c792ee1a42caa0a07f75f92ff63e，本窗结果尝试1，启动收据两latch=OPEN、业务输入0、完整观察0。现等待用户进入原店加载初始列表，随后按新鲜分类身份核对原第12/13类折叠项及第19类末尾。一次定向窗口，不跨窗补字段、不宣称全店当前完整，不自动重试；再次验证或网络异常立即停止。代码和系统配置未修改。证据：docs/harness/reports/P29-window21-receiver-ready.json、docs/harness/reports/P29-window21-started.json。


2026-10-12 窗口21初始列表核对通过：55行、30商品、41 SKU、19分类；当前初始声明155有序及22折叠关系。原第12/13/19类在新鲜列表中的身份、标签、序号及各自声明集合均与窗口20相同，未将旧业务值补入新记录。已请用户展开第12/13类并等待加载，再查看第19类末尾及可见终止提示。窗口21保持ACTIVE、实际尝试1，无再次start；该定向窗口不作为全店当前快照，平台终止仍UNCONFIRMED。证据：docs/harness/reports/P29-window21-initial-coverage-check.json。


2026-10-12 窗口21已关闭并核对：用户报告页面有“已经到底了”一类提示，记为本次访问可见末尾的用户证据，不等于协议终止或全店收齐。16:19:33 UTC stop后宿主90436退出、锁消失、cleanup=COMPLETE、拦截清理、两latch=CLOSED、active_streams=0；HTTP20完成/0失败/0未完成。本窗9份分类投影自身证明通过，独立导出139行、105商品、119 SKU、16个有记录分类（初始声明19类）；四表CSV/JSON、字段字典、覆盖及manifest重算核对通过。第13类26有序+4折叠及第19类13有序关系均齐；第12类7有序已齐，仍缺3折叠。本轮定向范围以外不重采，不跨窗补记录，旧233行确认单位交付保留。已询问用户刚才第12类是否展开，仅待动作事实，不要求重复操作；不自动新建窗口。P29/P31仍未整体accepted。证据：docs/harness/reports/P29-window21-user-terminal-fact.json、P29-window21-close-direct-check.json、P29-window21-received-coverage-check.json、P31-window21-fields-direct-check.json。


2026-10-12 用户补充：第12类在窗口21结束前未点展开，现已点击。已只读复核窗口21仍CLOSED、宿主退出、锁不存在、分类输入仍9份；当前点击不在采集期间，不能记为已收到。既有第12类仍缺3个折叠关系。下一步若补当前正文，仅需一次同店新鲜初始列表及第12类展开的定向窗口；窗口21限定一次且已关闭，不重开旧根、不自动启动，等待新窗口授权及随后必要页面操作。其余已交付文件保持不变。证据：docs/harness/reports/P29-window21-category12-user-action-fact.json。


2026-10-12 窗口22已获新授权并启动：用户明确同意仅补同店第12类展开商品。当前父进程46626、网络PID46630及固定CA复核通过；新根runtime-output/p29_pages_383add39cdf84889a075d57287fbb8b2，独立控制引用，宿主29076。先PREPARED零尝试/两latch=CLOSED，再于2026-10-12T16:38:03.031135+00:00单独start，窗口result:4f1d37e32aaf49f0be9d4c0cdfb8ac75，本窗实际尝试1、两latch=OPEN、初始业务输入0。已请用户回小程序首页重新进入原店，列表加载后展开刚才第12类；收到新鲜初始列表后核对分类身份，只验收对应缺项。不提前按用户完成口述关闭，先核对目标正文；异常则立即关闭。无自动UI/重试/系统变更/图片/私值，旧窗口和交付保留。证据：docs/harness/reports/P29-window22-preflight.json、P29-window22-receiver-ready.json、P29-window22-started.json。


2026-10-12 窗口22因用户报告加载失败并要求停机而关闭：16:40:11 UTC stop，宿主29076退出、锁消失、cleanup=COMPLETE、intercept_cleared=true、active_streams=0、两latch=CLOSED；本窗1次实际尝试，完整观察0、分类响应0，无新商品交付。15个HTTP响应完成及失败计数0不能证明页面正常，也不能排除采集器影响。当前任务转为只读分析转发/分流架构，不重新采集或改代码。判断：当前local PID重定向先让指定小程序网络进程连接进入代理，再按TLS域名选择解密；非目标TLS及UDP走不解密转发，仍依赖代理（怎么确认的：p26_identification_host.py:891、1009、572、586及本窗关闭诊断）。真正非目标绕过需在重定向前筛选，不能用解析接口白名单或ignore选项冒充。加载失败根因UNKNOWN。证据：docs/harness/reports/P29-window22-load-failure-stop-check.json、P29-window22-flow-routing-readonly-review.json。


2026-10-13 当前用户明确要求先完成转发/解析分离改动。已在P29真实入口接入有界内存副本队列和单独串行解析线程：请求/响应流回调返回原始bytes，不等待解压、解析、校验或结果写入；解析状态与转发状态分开。解析拒绝/失败、忙或积压不会自动关闭转发；跳过或丢弃副本单独记不完整。stop先清除拦截与连接，再离线收尾正在执行的有界解析，丢弃排队副本后给关闭收据。保留来源接收时点、门店请求关联、原有大小/时效/隐私限制。16项新测试含2项旧行为语义红；适配层525项用例由现有两套解释器互补覆盖通过，语法及git diff --check通过。未启动真实采集/网络/UI，未改系统配置或Git提交；窗口22仍关闭。当前改动完成且仅获离线验证，不证明实际微信加载恢复，不改变P29/P31整体验收或来源资格。仍使用现有PID中间代理，没有实现重定向前网络分流。证据：docs/harness/reports/P29-detached-analysis-validation.json；实现说明：docs/harness/reports/P29-detached-analysis-implementation.md。
