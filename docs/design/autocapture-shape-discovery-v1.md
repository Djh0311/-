# Autocapture shape discovery v1

## 1. 结论和证据上限

本设计只定义并实现 `LOCAL_MEITUAN_MINIPROGRAM_AUTOCAPTURE_V1` 的离线
基础：一个 mitmproxy-compatible `response(flow)` addon、失败关闭的内存
shape probe、value-free stop receipt 和只接收 sanitized shape 的 Publisher。

本包只使用新生成的 synthetic flow。通过本包最多只能得出：

```text
AUTOCAPTURE_OFFLINE_FOUNDATION_ACCEPTED_FOR_LIVE_PROBE
REAL_ENDPOINT=UNKNOWN / UNAUTHORIZED
REAL_MITMPROXY_LOADER_HOOK=UNKNOWN / UNAUTHORIZED
LIVE_CAPTURE=UNKNOWN / UNAUTHORIZED
```

本机未安装 mitmproxy，因此本包不能证明真实 loader、微信代理、TLS 拦截、目标
响应、业务字段、Provider 资格、OSE-M1、部署或发布已经通过。

## 2. 当前关闭的能力

本包的能力闭集如下：

| 能力 | 当前状态 | 本包行为 |
| --- | --- | --- |
| network | `CLOSED` | 不导入或调用网络客户端 |
| browser | `CLOSED` | 不启动浏览器 |
| ui | `CLOSED` | 不打开或操作微信/小程序 |
| local_source_read | `CONTROL_CODE_ONLY` | 只加载本包代码；不读微信、本地业务源或历史抓包 |
| filesystem_write | `OFFLINE_TEST_ONLY` | 仅 Publisher 隔离目标和构建工件 |
| process_spawn | `VERIFIER_TEST_ONLY` | addon 不启动子进程；故障注入测试只启动本地 Python verifier |
| certificate | `CLOSED` | 不安装、信任或读取 CA |
| system_proxy | `CLOSED` | 不查看或修改系统代理 |
| administrator | `CLOSED` | 不请求管理员权限 |
| credential_or_session | `PROHIBITED` | 项目代码不得读取或派生 |
| private_service | `CLOSED` | 不连接任何服务 |
| transaction | `PROHIBITED` | 不触发交易动作 |
| external_cost | `NOT_REQUIRED` | 不调用付费能力 |

导入 `autocapture.addon` 只创建默认 `DISARMED` 的 addon。模块加载、环境变量、
mitmproxy loader 回调或 flow 到达都不能自动 arm。唯一导出必须精确为
`addons = [ResponseCaptureAddon()]`：一个 list、一个零参数实例。只有未来受控调用者
显式传入完整且有效的 `CapturePolicy` 和 Publisher，才可在一个新实例上执行一次
`DISARMED -> ARMED`；本包不导入 mitmproxy，也不注册 `load`、`configure` 或
`running` 自动 hook。

## 3. mitmproxy-compatible 边界

`autocapture.addon` 导出：

```python
addons = [ResponseCaptureAddon()]
```

`ResponseCaptureAddon.response(flow)` 使用 duck typing，不在离线包中导入
mitmproxy。包导入和直接脚本导入都只解析 `addon.py` 自身的 realpath，临时加入
精确 package root，导入 canonical `autocapture.*` 后核验 policy、lease、shape
三个模块的真实来源，并立即撤回临时 import path。普通和 isolated Python 的
direct-script smoke 只能证明本地 load shape 和类身份一致；真实 mitmproxy
import/load/hook 调度仍为 `UNKNOWN`，必须在独立授权下验证。

addon 在正文前对 flow 的允许读取是闭合的：

- `flow.request.method`、`flow.request.host`、`flow.request.path`，各一次，且只作为
  一次原子 endpoint selector 的输入；
- `flow.response.status_code`；
- response headers 中的 `Content-Type`、`Content-Length` 和
  `Content-Encoding`；
- 所有前置门通过后，精确读取一次 `flow.response.raw_content`。

禁止读取 request query、完整 URL、headers、body、Cookie、Authorization、path
components、其他 response header、decoded text、对象表示或通用 header 映射。无论
match 与否，这些 request surface 的读取计数都必须为 0。addon 不写 `flow`、metadata、
header 或 body，不调用 kill/replay。

门控顺序固定为：

```text
state/window/event budget
  -> request.method + request.host + request.path
  -> one atomic endpoint selector
  -> metadata-invalid: value-free STOP
  -> tuple mismatch: ignore, all response reads/copies = 0
  -> response.status
  -> fixed response headers
  -> declared byte/encoding gates
  -> second window gate
  -> one raw_content read
  -> actual byte gate
  -> addon-owned RawLease
  -> UTF-8/JSON/sensitive/unknown/shape budgets
  -> event-local shape commit
```

method、host、path、status 和完整 Content-Type header value 均作精确匹配，不做
大小写、尾点或参数归一化。request metadata 的类型、空值、控制字符或非规范语法
失败时，以固定 `REQUEST_METADATA_INVALID` 锁存停止；合法但不匹配完整 tuple 时仅
忽略，response status/header/body accessor/copy 均为 0。匹配 tuple 下缺失或未知
Content-Type、非 identity encoding、非法声明长度、正文类型未知或任一预算超限会
停止整个尝试。`Content-Length` 只接受最多 20 位 ASCII 十进制；Unicode digit、超长
数字或其他表示在正文读取前停止。

## 4. 显式策略与硬上限

每次 arm 必须同时冻结：

- `EndpointRule(method, exact lowercase DNS host, query-free canonical static path)`
  的不可变集合；
- exact response status allowlist；
- exact JSON media-type allowlist；
- 运行前冻结的 exact JSON object-key allowlist；
- 单 body byte 上限与累计 byte 上限；
- JSON depth、node 和 unique shape path 上限；
- event count；
- observation window；
- 单 RawLease 存活时间。

endpoint rule 不把 method、host、path 拆成独立 allowlist；三者只作为同一条 rule
匹配，绝不形成笛卡尔组合。method 只接受有界 ASCII uppercase HTTP token；host 只
接受精确 lowercase DNS host，拒绝 wildcard、IP literal、scheme、path、port、query
和 fragment；path 只接受有界 ASCII、absolute、non-root、无 query/fragment/percent
encoding/反斜线/双斜线/`.` 或 `..` segment/尾斜线/wildcard/动态模板的静态路径。

缺字段、空 allowlist、上述非规范 endpoint metadata、带参数 media type、非有限时间、
布尔伪装整数、非正数或超过实现硬上限全部拒绝，addon 保持 `DISARMED`。策略不能
关闭敏感 key 规则、unknown 规则、zero-retry 或 value-free Publisher 校验。
Publisher 声明的 key allowlist 必须与 CapturePolicy 精确相同，否则不能 arm。

observation window 从显式 arm 时刻开始。窗口或 event budget 闭合后，入口先停止
读取 flow；已聚合至少一个安全事件时只发布一次，零事件时不制造 shape。
clock 每次读取只接受 exact `int|float`、finite 且不回退的值，arm 时还要求 deadline
可表示且严格晚于起点；非法 clock 在 flow 入口或第二个正文前 gate 失败关闭，正文
读取为 0。

## 5. RawLease 的准确保证

`RawLease` 只拥有从 `raw_content` 复制出的一个有界 `bytearray`。工厂在复制前
检查 proxy-owned buffer 的实际 byte 数，复制后再次检查 addon-owned buffer；
`consume_once()` 只能成功一次。所有成功、拒收、解码失败、敏感、unknown、
超限、超时、取消和异常路径都在 `finally`/context manager 中幂等关闭 lease，
原地覆盖并释放 addon 自己的引用。

该保证只覆盖 addon-owned buffer。它不声称能清除 mitmproxy、操作系统、Python
解码字符串或硬件中的副本，也不把托管运行时的引用释放夸大成硬件级内存擦除。
准确结论是：本包控制的 raw buffer 在退出后不可由 lease 再访问且未被本包
持久化。

## 6. shape、敏感和 unknown 处理

probe 使用严格 UTF-8 和严格 JSON：

- duplicate object key、非有限 number、root scalar、未知类型失败关闭；
- integer/float token 最长 128 个字符，避免解释器版本和启动配置造成大整数漂移；
- JSON decoder 的 CPU/分配只由单 body bytes、累计 bytes 和 numeric token 长度
  间接封顶；depth、node、path 和 observation deadline 是完整解码后的投影/接受
  budget，不是 streaming decoder 的前置工作量上限；
- 投影期间每访问一个节点检查 deadline、depth、node 和 path budget；
- event-local shape 完整通过前不得提交到 accumulator；
- JSON array 使用 wildcard JSON Pointer，不输出元素索引或 scalar 值；
- scalar 只在最短内存生命周期内接受固定敏感分类，不哈希，也不复制到输出、异常或
  持久化对象；JSON 解码器和分类器的瞬态字符串不属于 RawLease 可物理清零保证。

唯一公开 schema-key 分类器定义在 `autocapture.shape`，并由 policy、shape staging、
`SanitizedShape` validation、Publisher 构造和 pointer/reopen validation 重新调用。
它只返回四种结论：`SENSITIVE`、`REGISTERED_SAFE`、`SAFE_UNREGISTERED`、
`TRUE_UNKNOWN`。敏感语义始终优先于结构或 registered membership；控制字符、非
ASCII、超长、动态/高熵或非保守结构一定是 `TRUE_UNKNOWN`，不会因注册集合成员身份
而变安全。`REGISTERED_SAFE` 只在同一保守结构检查通过且 key 位于 frozen registered
set 时成立。

`SAFE_UNREGISTERED` 只可作为当前 event 的 sanitized JSON Pointer 结构 token，进入
`path`、`parent`、`relation` 和 type/cardinality 的无值 shape；它绝不产生分类字段、
candidate 表、observed-key list、key hash/长度/片段，不写回或缓存进 registered set，
也不接触 scalar/value。`SENSITIVE` 与 `TRUE_UNKNOWN` 都在生成/提交 event-local stage
前丢弃并触发 value-free stop。safe-unregistered 因而不等于稳态 `SafeProjection` 或
业务字段放行。

固定敏感规则覆盖 credential、session、设备/账号身份、验证码、个人收货语义、以及
这些类别词之间插入普通限定词、版本号、大小写/缩写/复数变体的字段名；另覆盖
synthetic sensitive canary、Bearer/Basic/JWT 和若干高置信 secret prefix。该保守分类器
不是通用 DLP，也不声称能理解任意未见字符串的业务语义；alphabetic 动态业务 key
仍是模型边界。它能证明的是：冻结的高置信敏感测试向量触发停工，任何 scalar 均不
进入 shape、digest、receipt 或 Publisher。未来 live 任务仍须在读取正文前冻结并人工
独立审查字段规则版本，再对 value-free 输出做独立接受。

正常 `SanitizedShape` 的顶层闭集是：

```text
schema_version
event_count
nodes[
  path
  types
  parent
  relation
  presence{observed_events,total_events}
  cardinality{minimum,maximum} | null
]
sanitized_shape_digest
```

digest 的输入是移除 digest 字段后的 canonical sanitized model。它不是 raw、
scalar 或敏感值的 hash。shape 不含 `payload_family/version`；synthetic 数据
不得编造真实 family/version。

任何 sensitive、unknown、decode、timeout、budget 或 internal failure 会原子地：

1. 把 addon 置为不可恢复的 `STOPPED`；
2. 清空本次尝试已经聚合的全部 shape；
3. 关闭当前 RawLease；
4. 禁止 Publisher 接收任何对象；
5. 让后续 flow 在入口返回，正文读取为 0；
6. 仅保留固定枚举组成的 `ValueFreeStopReceipt`。

stop receipt 只含 schema、outcome 和 reason code。它不含字段路径/键名、值、
片段、长度、hash、host、URL/query/header、本地路径、异常消息、traceback、
dump 或邻近内容。异常对象不得跨越 addon。

## 7. Publisher

`AtomicShapePublisher.publish()` 的入参类型必须精确为 `SanitizedShape`，不能是
flow、RawLease、bytes、dict 或通用对象。构造 Publisher 时必须再次提供与
CapturePolicy 相同的 frozen key allowlist。Publisher 顺序执行：

1. exact schema 和 canonical type 校验；
2. path 再次调用同一四态 classifier：允许保守 `REGISTERED_SAFE` 与
   `SAFE_UNREGISTERED` pointer token，拒绝 `SENSITIVE` 或 `TRUE_UNKNOWN` tamper；
3. 重算 `sanitized_shape_digest`；
4. 生成只含 shape 和 sanitized digest manifest 的单文件 bundle；
5. 在目标同目录创建 mode `0600` staging 并 fsync；
6. 用 no-replace 原子 promotion 使完整文件一次可见；
7. 复开、重算并验证 bundle/manifest；
8. 清理 staging。

target 必须位于已存在、当前 uid 所有、无 group/world 权限的专用 root 下，且 root
必须以 canonical absolute path 传入，路径本身及任一 ancestor 都不能是 symlink；
构造时冻结 root device/inode，发布时再次核对。target 只接受 basename。调用者还
必须保证该目录没有同 uid 并发写者；本实现不把 `0700` 夸大为跨同 uid 进程的强
隔离，也未证明继承 ACL。target 已存在、symlink、路径逃逸、root 路径/identity
漂移、manifest 不符或 promotion 前故障都失败关闭且不覆盖旧 target。

promotion 使用 no-replace hard link，返回后立即核对 target 的 inode/mode/size，
再清理 staging、同步目录并独立复开。若内核已经提交而 Python 同时收到取消，
只有 target inode 与预期精确一致时才继续复开并按成功处理。promotion 后复开失败
时，为避免 check-then-unlink 误删并发替换 inode，Publisher 返回闭合失败码但不再
按名字删除 target；保留物只能是 promotion 前已经通过 schema/privacy/digest 的
完整 sanitized bundle。后续运行必须使用新的 target-absent root。若违反“无同 uid
并发写者”前提，source/target inode 不符会失败而不会报告发布成功，但外部写者造成
的 foreign 文件或 staging residue 不属于本包可安全清理的对象。当前只证明原子
可见和 no-clobber，不声称断电持久性。

## 8. 生产 verifier 与离线故障注入

`autocapture/tools/verify_autocapture_build.py --strict` 对生产闭集执行：

- required/extra file 和 regular-file 检查；
- symlink、realpath/scope escape 检查；
- build manifest exact entry 和 SHA-256；
- Python syntax/AST、forbidden import/capability；
- 原子 method/host/static-path endpoint selector、request/response 读取闭集和 flow
  零写入；
- selector 必须位于任何 response read 前，拒 host-only/拆分 selector/删除或反转门；
- 所有 policy、shape、model、Publisher consumer 必须引用唯一四态 classifier，拒复制
  或旁路；
- exact `addons = [ResponseCaptureAddon()]`、one/zero-arg/`DISARMED` loader contract，
  拒 mitmproxy import、auto-arm 和外部 hook；
- exact raw-content 单次读取、flow/closure/container alias 传播；
- shape/output 静态闭集、动态 output key 拒绝；
- 固定敏感规则和 synthetic leak canary；
- dead branch、动态 import/getattr/callable alias、publisher clobber primitive；
- semantic snapshot 与最终 tree 二次逐字节核对；
- raw/HAR/PCAP/dump/cache 残留。

单元测试在隔离临时副本中重新绑定 manifest 后注入 missing、extra、forbidden
import、symlink/scope escape、raw/value-hash schema key、动态 key、flow alias、
正文逃逸、endpoint selector/门失活、唯一 classifier 复制或旁路、loader auto-arm/hook、
敏感门失活、publisher clobber 和验证期间 tree swap，要求生产 verifier 全部非零退出
并给出固定 reason code。测试输出不打印注入内容。

## 9. 下一次一次性 live shape discovery

离线验收通过后只能提出一个新的、一次性 live 任务。来源选择已经确定，不再讨论
export-versus-autocapture。新任务必须先冻结：

- 精确 target page scope、method/exact host/static-path endpoint rule 和必要 network
  service；
- proxy 的 pre-state、期望 during-state、post-state 与失败恢复命令；
- CA 的精确 identity、安装/信任范围、验证方式和 removal plan；
- 一个 observation window、单 body/累计 bytes、depth/nodes/paths/events/lease；
- `max_attempts=1`、`automatic_retry=0`；
- target-absent 输出根和 value-free output 闭集；
- crash dump、日志、临时目录和缓存的运行时控制；
- 紧急停止、代理恢复、CA 移除、进程退出和残留扫描命令；
- 每项能力的单独授权与实际调用计数。

未来代理 transport core 为传输既有流量，可能在自身瞬态内存中携带请求 header。
这是 transport-secret transient boundary，不是项目代码读取授权。addon 仍不得
读取、记录、持久化、重放、比较、hash 或派生 Cookie、Authorization、token、
账号、设备或 session；不得把 transport core 的瞬态持有冒充项目已取得凭据。

未来能力表必须逐项裁定：

```text
network
browser
ui
local_source_read
filesystem_write
process_spawn
certificate
system_proxy
administrator
credential_or_session
private_service
transaction
external_cost
```

每项只可为 `NOT_REQUIRED`、`REQUIRED_PENDING_SEPARATE_AUTHORIZATION`、
`PROHIBITED` 或 `UNKNOWN`。任何 `UNKNOWN`、缺恢复步骤、缺 no-clobber 输出根、
缺运行时隐私控制或缺独立用户授权，都保持 live latch `CLOSED`。
