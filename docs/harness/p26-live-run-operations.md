# P26 准备与受控真实窗口操作

当前：P26已reported后直接accepted并退场，current leaf为空。真实JSON/CSV/manifest已发布、关闭：39条分类记录、31个不同商品、7个有商品的分类，当前列表PARTIAL。第22次确认poi_info及两组FORM对应，显式v2在独立结果第2次通过。累计识别22/结果2，两latch=CLOSED、清理/输出完整、退出0。9项基础来源字段已导出，扩展未知项逐条登记；不启动P27或全店，准确状态见[快照](reports/P26-monitoring-current-status.json)。

最新范围见 [监控范围变更收据](reports/P26-monitoring-scope-update.json)。下文120秒、单次及90/180秒准备等待记载原派发和原始行为；实时监控模式无采集时间上限、无尝试总次数上限、无等待start期限。仍保留每份输入的大小/内存预算、敏感停止和单目标边界。每次启动有新鲜引用和独立锁，历史尝试计数与锁不删除。准备命令只读本次控制和进程/socket元数据；已经用过的次数仍显示，不归零。

当前现场顺序：开发者核对当次父子进程、用户/路径与socket归属；prepare通过后启动拒绝全部接收器，再start，确认就绪后请用户回到小程序首页再进同一家店铺并停在商品列表。没有刷新按钮时不要求找按钮。自动候选筛选由开发者完成，不让用户找路由或逐商品收集数据。已观察的当次SNI可用--inspect-current-domain预选；参数不证明接口/来源资格。原文最多60秒内存，不修改代理，不扩大到其它微信进程。

## 已查证与授权

- 使用本次用户选择的独立绑定，不继承旧编号、配置、锁或额度。业务名称只保留在对话及受控根的 current-business-choice.json，不复制到报告。
- 复用 mitmproxy 12.2.3 引擎，新识别宿主只注册四个必要 addon，不加载默认保存、日志、回放或浏览器能力；不执行旧 companion。结果映射由真实事实决定，不受旧两回调假定限制。
- 临时 CA 实际创建成功，文件 0600、目录 0700；用户已报告完成登录钥匙串 HTTPS 信任。这是用户就绪确认，没有读取 keychain。
- 发现 /Applications/Mitmproxy Redirector.app 缺失后，展开现有软件包自带应用并验证签名；用户另行授权安装，已无覆盖复制到原不存在的该路径，安装后签名复核 PASS。
- 最小宿主模块组合已实际构造并释放，server 数 0、两 latch=CLOSED、零尝试；实际准备 CLI 通过。组件存在不证明网络扩展、转发路径或业务响应已就绪。

## 可复现准备入口

受控根：`/Users/yoyi/爬虫/runtime-output/p26_aeb8ef41471c42a78f5c1b5bd172ba94`，既存 0700、Git 忽略；保留本次控制记录及first_result真实结果；本次CA六个固定文件和创建目录已按身份核对删除。不得读历史 raw、默认 confdir、旧 companion 配置或旧票据。

```sh
PYTHONDONTWRITEBYTECODE=1 \
  /Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B \
  -m collection_adapter.p26_identification_host \
  --output-root '/Users/yoyi/爬虫/runtime-output/p26_aeb8ef41471c42a78f5c1b5bd172ba94'
```

首次识别准备返回P26_IDENTIFICATION_HOST_PREPARED、program_preparation=COMPLETE、source_ready=UNKNOWN、两阶段零尝试和CLOSED。随后程序按真实观察完成结果映射；结果准备命令见下文。准备如实显示此前累计次数，不消费输入、不新增尝试。ACTIVE时不能再prepare并发宿主，应由现有宿主status核对；关闭后才能重新prepare。程序COMPLETE不能代替新鲜接收器、转发路径和目标页面就绪，source_ready仍按UNKNOWN报告。准备只读本次控制、目录及准确进程/socket元数据，不导入网络宿主或读取回调。

## 识别窗口表

| 项目 | 明确范围 |
| --- | --- |
| 目标 | 当次确认的一个小程序、一家店铺；本次 CurrentTargetBinding，用户确认仅保留该目标页 |
| 输入隔离 | 仅当前socket归属查证的同应用包/用户直接网络子进程PID，绑定对应唯一小程序父进程；每条stream再核对内核给出的PID，缺失/不一致在读取字节前拒绝并停止 |
| 初始识别 | 只检查必要 TLS 域名元数据；未选域名加密透传；UDP/QUIC和明文不检查、不存消息 |
| 业务范围 | 仅当次已观察的两个POST店铺路由；必要query/FORM参数名和Content-Type枚举可检查，选定公开店铺路由编号只作相等比较，其他请求值不解码。未选响应流式透传，完整URL/headers不输出；普通值处理敏感即停，当前获准键级诊断只记录受限键名/类型并跳过私人分支值 |
| 来源依据 | 用户当前选择、单目标页面确认、准确 PID、内核 stream PID、当前店名匹配和实际结构分层核对；单域名/进程不代替店铺归属或价格语义 |
| 所需能力 | 已批准的专用 CA 使用、用户手动信任、PID local capture 和 Redirector 安装；系统扩展批准提示由用户本人操作；保持系统代理启用标记不变 |
| 启动 | serve只准备非空等价拒绝全部intercept接收器；P26_RECEIVER_READY_NOT_STARTED后开发者另发start，立即复核绑定、目的地、CA、PID和新鲜锁；成功激活才记一次，同一宿主不再次start |
| 时间 | 当前获准连续监控无采集时间/尝试总次数上限，无等待start期限；接收器资源准备90秒有界且零尝试。单份未完成正文最多60秒、匹配原文最多60秒内存 |
| 数量/大小 | 连续模式最多8个同时正文处理、8份最近短暂原文，顺序响应可超过8；经典模式8份总量。单个编码/解码各≤1MiB，总编码/解码各≤4MiB；连续模式64并发stream、64同时连接、64域名、128query-free路由，经典模式32连接/8域名/16路由。有限计数饱和后用*_at_least标下界，不据历史总数结束；正文预算超限停止，无自动重开 |
| 内存/核对 | JSON节点≤40000、深度≤32、无值shape≤4096项/响应；公开投影白名单最多128路径，当前7条门店允许路径覆盖两个实际观察容器的三个身份字段及code，22条商品发现路径来自本次实际结构；一个响应仅处理真实存在的字段。只处理精确选中标量，字符串≤256字，不输出容器、URL、私人值或值哈希；公开投影及FORM租约最多8份/60秒，关闭清空。旧probe命令另有32次、首三个列表项限制，不能当成批量投影上限 |
| 输出 | 上述0700根内新的固定诊断收据、无值shape、明确选取的公开业务核对标量；后者仅为 incomplete 识别依据，不是完整商品表。原始包、routing catalog、URL、headers、错误正文不落盘 |
| 停止 | 正文处理期限、大小/并发/结构预算、PID缺证、敏感、取消、异常或收齐后切为拒绝全部intercept，关闭连接、接收器和控制通道，清空原文，两latch=CLOSED；单轮未开始0、开始1，累计不归零，无自动重试 |

```sh
PYTHONDONTWRITEBYTECODE=1 \
  /Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B \
  -m collection_adapter.p26_identification_host \
  --output-root '/Users/yoyi/爬虫/runtime-output/p26_aeb8ef41471c42a78f5c1b5bd172ba94' \
  --serve-identification \
  --inspect-current-domain wx.waimai.meituan.com \
  --batch-public-json \
  --identify-field-layout-only \
  --inspect-sensitive-field-keys \
  --inspect-public-fields
```

这是开发者入口；用户只完成系统提示和页面操作，不填写域名、路由或 JSON path。接收器未就绪不发 start；就绪后开发者 start 并告知用户手动刷新当前商品页，必要时手动返回并再进入同一家店铺；用户不要进入订单、地址或个人账户页。

只用--identify-field-layout-only时，全部标量不解码，敏感键命中即关闭。用户之后明确允许看敏感字段，--inspect-sensitive-field-keys须匹配本次目标的权限收据，才记录受限键名/类型并持续检查结构，受限值及分支子字段仍不解码。当前附加--inspect-public-fields只解码第16/19/21/22次本次事实支持的白名单公开标量；普通整包值路径仍敏感停止，没有删除隐私校验。array坐标保留，URL/超长字符串/容器/非有限数不作公开标量，60秒清除。layout是无值结构；public_values_processed会如实标识同时发生的公开投影，sensitive_values_processed=false。

开发者发送merchant可在租约期间查看选定的公开门店名称/编号；projection可将新鲜公开投影写入0700根，仅当本轮公开店名匹配当前选择才允许写出。产品店铺关联仍标NOT_CONFIRMED、product_result=incomplete，不是结果表。association只比较已观察的wm_poi_id/poi_id_str与命名响应编号字段及两请求是否相等，写固定布尔/null事实，不输出编号。窗口内最多8份layout/projection/association快照；原文不保存。非法公开字段只登记固定路径/类型及NONSCALAR、URL_VALUE、STRING_LENGTH、LINE_BREAK或NONFINITE_NUMBER，不输出失败值；unavailable_fields不允许成为完整记录。

两个当次实际POST路由均观察到FORM请求，query参数名中没有店铺编号。当前只在这两个路由流式处理FORM字段名，不解码其它参数值；单请求编码/解码各1MiB，FORM总编码/解码各4MiB，与响应预算分别计数，共用最多8个并发处理器。最近最多8份FORM租约保留内存不超过60秒，关闭即清空，原始请求不落盘。

layout中request_field_layouts只提供当次request_ref、route_slot及参数名。开发者从实际出现的公开店铺路由编号字段中选择一个，发送parameter {"request_ref":"request:<本次随机引用>","field":"<实际观察键名>"}，只解码该参数标量并比较当前匹配门店响应编号。输出只有字段名、引用、固定角色及matches_current_public_store_id布尔值，不输出参数值。未匹配门店、其他店铺、过期租约、私人键或未观察键不能通过。商品公开投影中的source_request_ref用于核对其对应的当次请求，不能只凭时点拼接不同店铺。

开发者协议：status为固定码/有限计数，route_rejections区分HOST_NOT_SELECTED、METHOD_NOT_ALLOWED、PATH_NOT_SUPPORTED、PRIVATE_ROUTE，不回显拒绝值。domain <当次slot>选择必要域名并关闭其旧透传连接；route <当次slot>选择公开正文；probe含slot/path，只核对已匹配目标的允许公开标量；stop或Ctrl-C关闭。选择依据当前元数据，不套用fixture/历史raw，不重放请求或自动UI。--inspect-current-domain最多8个、必须来自当前现场已观察的SNI；它只准备路由检查，不消费输入、不预选正文。

## 结果窗口、字段与恢复

识别结束后，以当次事实固定版本合同、目标匹配、同观察关系、公开字段路径、单位/币种和价格含义；未知登记，不猜测。必要映射用合成数据验证并保留 P25 回归。一个响应同时提供门店与商品时保持同观察，不为旧两回调合同拆出虚假输入。

当前显式候选family=meituan_wechat_miniprogram、version=p26-observed-shop-v2，依据第22次精确命名事实生成。version是本地观察规则版本，非平台官方版本或正式Parser资格。旧v1保留原poi_base_info条件，不自动选择新容器；v2只接受唯一poi_info，双容器拒绝。配置由开发者准备，不要求用户提供参数或Cookie。

| 项目 | 结果试跑范围与依据 |
| --- | --- |
| 目标与输入 | 当前绑定的一家店铺；只接TLS来源wx.waimai.meituan.com的POST /weapp/v1/poi/food与POST /weapp/shop/v1/poi/productlist及其对应新鲜FORM |
| 归属 | v2要求FOOD店名匹配当前选择、两FORM的poi_id_str分别等于poi_info.poi_id_str字符串、wm_poi_id分别等于poi_info.id整数文本，两请求对应字段分别相等。第22次与结果第2次均直接通过；负数路由编号不视为占位。旧集合探针不作为具体字段证明 |
| 同观察 | 本次独立result窗口的首个FOOD和PRODUCTLIST，间隔≤10秒，独立新read/observation引用与一次性锁；不重用识别投影或历史输入 |
| 价格 | 当前页面确认元单位/CNY；每个商品min_price必须同时等于render_info.price_info.min_price与最低SKU.price。导出含义为PRODUCT_LIST_MINIMUM_SKU_PRICE；不生成所有SKU价格，不将最低价说成结算价 |
| 投影 | FOOD七条允许路径（code及两个实际观察容器的三字段，v2仍严格拒绝旧/双容器）、PRODUCTLIST十五条路径；整数id用于第二组FORM关联，公开字符串编号用于结果身份。敏感与未选值不解码。URL型price_desc_tag不进入基础结果；基础所需字段缺失或不合格即拒绝，不能填默认值 |
| 数量与大小 | 成功需要恰好两种端点各一份、对应两份FORM；重复端点拒绝。单份编码/解码各≤1MiB，响应与FORM分别总计各≤4MiB；并发≤8、节点≤40000、深度≤32，字符串≤256字 |
| 等待与停止 | 不设会话等待/尝试总次数上限；第一份输入开始后，事件组和原文/投影/FORM租约最多60秒，不能跨过期输入凑记录。收齐发布、不同目标、关系改变、敏感/预算/解析/发布失败、取消或异常即关闭，不自动重开 |
| 输出 | 既存Git忽略0700根下独占first_result目录，records.json、records.csv、manifest.json；记录完整，但覆盖仅CURRENT_LIST_RESPONSE_ONLY/PARTIAL，不声称全店 |

以下记录本次实际调用顺序，供开发者复现入口行为。本次已完成、first_result已存在且CA已清理，不能直接重跑旧控制或旧锁；现有输出不得覆盖。下一真实任务需开发者按当次范围建立新根、目标/能力引用和参数，重新查证接收器与页面，不能凭这些命令自动重开。

本次先在关闭状态调用准备：

```sh
PYTHONDONTWRITEBYTECODE=1 \
  /Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B \
  -m collection_adapter.p26_identification_host \
  --output-root '/Users/yoyi/爬虫/runtime-output/p26_aeb8ef41471c42a78f5c1b5bd172ba94' \
  --result-profile-control p26-result-profile-bf8e8426c156484996b90d213eb38879.json
```

结果第2次开始前实际返回P26_RESULT_HOST_PREPARED、program_preparation=COMPLETE、source_ready=UNKNOWN、累计识别22/结果1、两latch=CLOSED；实际PREPARED status也证明本窗口0尝试、0回调/业务响应。准备不消费输入或新增尝试，start才将累计结果加到2。见[准备证据](reports/P26-result2-preparation-evidence.json)。

然后由开发者在可保持stdin的终端启动接收器：

```sh
PYTHONDONTWRITEBYTECODE=1 \
  /Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B \
  -m collection_adapter.p26_identification_host \
  --output-root '/Users/yoyi/爬虫/runtime-output/p26_aeb8ef41471c42a78f5c1b5bd172ba94' \
  --serve-result \
  --result-profile-control p26-result-profile-bf8e8426c156484996b90d213eb38879.json
```

P26_RECEIVER_READY_NOT_STARTED时仍拒绝全部输入、零本窗口尝试；开发者再发送start，复核目的地/控制/准确PID后激活，只有此时结果累计增加一次。用户随后回到首页、进入同一家店铺并停在列表，不逐个点商品。status返回固定码和有限计数；stop或Ctrl-C关闭。成功自动关闭并写独立result-host/result-output收据；任何失败保持incomplete。已存在first_result时准备拒绝覆盖；完成后不再执行上述本次命令。

六类字段沿 [字段范围计划](field-coverage-plan.md)登记，新发现公开字段也登记。未观察不能标来源未提供，含义不明待确认，已可得未适配保留缺口。全店分页和六类完整扩充留后续任务。

关闭分别记录 receiver_ready、pid_verified_streams、raw_callbacks、business_responses、target_matches、cleanup；business_responses 是选定路由的读取次数，拒绝也计入；qualified_business_events、parsed_records、published_records 在识别阶段均0，不将店名/shape匹配算合格完整记录或成功采集。扩展可能仍安装/启用，关闭不等于卸载；用户可在系统设置关闭本次 mitmproxy 网络扩展，再删除本次新增的 /Applications/Mitmproxy Redirector.app。开发者不自动系统 UI。

本次已按创建目录身份、精确六文件集合和权限核对，删除自己创建的CA六文件及目录，保留结果和其它文件；[清理收据](reports/P26-ca-cleanup-receipt.json)。用户需在“钥匙串访问”→“登录”→“证书”搜索P26 Temporary CA adf3cdf7022c4b6aa135fb65e3f70471，仅删除本次导入证书；开发者未修改keychain。删除文件不等于删除信任。其它系统能力或扩大目标须明确授权；同目标监控时间及尝试总次数上限已取消，不重复请示已批准能力。实际次数与收据见[P26报告](reports/P26-delivery-report.md)。

统一发现模式参数为三个当次美团来源后缀；仅匹配准确PID中实际出现的SNI及完整域名边界。--batch-public-json还要求当前用户批量公开业务范围与目标绑定一致；自动选HTTP200 JSON候选，已观察的不必要路由和账户等私人路由在正文前拒绝。任何候选都先作键级隐私检查，再确认真实目标/字段，不靠后缀赋予来源资格。当前更窄的字段诊断命令见上，不使用三个后缀展开正文。

第11/12次退出2问题已复现为异步stdin使共享TTY stdout非阻塞，关闭行写出时WOULD_BLOCK。宿主现在以有界队列按顺序完成短写，并在关闭后写diagnostic_output_complete收据；零尝试prepare/stop和第14次实际敏感停止均退出0、输出完整。历史故障收据不改写。旧authority_kind/authority_equals_tls实际表示Request.host转发目标；HTTP Host/:authority未检查，新输出已改为destination_host_kind/destination_equals_tls。
