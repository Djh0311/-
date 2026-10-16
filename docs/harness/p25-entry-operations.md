# P25 接入准备操作说明

范围：本地准备与诊断；P26 未启动，真实采集未授权。LIVE_CAPTURE_LATCH=CLOSED、EXECUTION_LATCH=CLOSED。

## 当前可调用的命令

开发者选定一个已存在、可写且可进入、权限 0700 的规范绝对输出根，以及未使用的结果名：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m collection_adapter.live_prepare \
  --output-root /absolute/controlled/output-root \
  --result-name p26_first
```

这条命令只检查目录元数据和权限、输出诊断；不加载私有配置，不导入旧 companion，不创建结果目录，不开始监听或读取回调。普通调用成功输出诊断时退出码为 0；目录或参数拒绝时为 2。非法参数不回显输入，`--help` 只显示静态帮助。

当前没有已确认的真实规则，正常诊断是 `program_preparation=INCOMPLETE`、`real_source_ready=UNKNOWN`、`closure_code=DEVELOPER_PARAMETERS_MISSING`、`not_started=true`、尝试数 0。退出码 0 表示诊断成功，不能解释为真实准备完成或可采集。

## 开发者准备参数的进程内入口

入口位于 `collection_adapter.live_prepare`：

```python
session = prepare_live_entry(LivePreparationSpec(...))
diagnostic = session.diagnostic()
# start 是另外一次显式调用；本次只在合成回归中验证。
```

开发者负责构造 `LivePreparationSpec`：输出根与结果名、当前目标绑定及无值引用、新鲜 request 引用与 issued/expires、可刷新时钟、端点匹配/大小/敏感/目标/投影 policy、候选 Parser registry、P0 context factory。真实参数只能来自 P26 当次获准事实，不使用本仓测试中的路径或 family 标签作为真实规则。用户不找接口、不写配置、不提供 Cookie。

`prepare_live_entry` 不创建一次性 attempt，不调用时钟取得来源，不读取 flow，也不消费输入锁。参数与本地预检均通过才形成程序内 PREPARED：程序准备 COMPLETE，真实来源仍 UNKNOWN，`receiver_ready=NO`、`local_receiver_armed=false`、`start_requested=false`、`not_started=true`、尝试数 0。完整参数只是结构已给出，不能证明真实语义。

后续明确获准的 P26 需要先确认真实来源、映射、就绪和窗口范围，再单独执行 start；本次不提供实际监听启动命令。当前 start/cancel 生命周期的直接证据只有合成验证。

## 分层诊断

| 字段 | 口径 |
| --- | --- |
| program_preparation / developer_match_parameters | 本地准备及参数结构是否完整 |
| real_source_ready / real_interface_rules / real_field_rules / network_readiness | 本轮均 UNKNOWN；没有网络或真实来源检测 |
| not_started / start_requested | 是否尚未成功进入一次尝试 / 是否请求过开始；请求被拒且未 acquire 时仍未启动、零尝试 |
| receiver_ready / local_receiver_armed | 实际程序内 reader 为 WAITING 才就绪；PREPARED 不算 armed，也不代表真实网络就绪 |
| callback_entered / raw_callback_count | 活跃 reader 中进入的原始回调，不等于合格事件；关闭后的回调不计入窗口 |
| target_matched / target_match_count | 已通过大小、敏感和目标判断的回调 |
| events_complete | 当前内存合同的两个必需事件齐全；是否适合真实来源须 P26 确认 |
| parse_status | NOT_RUN、RUNNING、ACCEPTED、REJECTED、STOPPED |
| publish_status | NOT_RUN、RUNNING、PUBLISHED、REJECTED |
| qualified_event_count | 当前兼容字段名称，实际计数为通过 P0 的业务记录数；不是原始回调数、商品覆盖率或真实来源资格 |
| closure_status / closure_code | 当前开放/关闭及固定枚举码 |
| cancel_status | 取消尚未请求、已请求、已关闭，或请求落在发布提交阶段 |

原始与目标计数最大 8，合格记录计数最大 10000，按上限饱和；最大值不表示恰好只有该数量。程序未 armed 或关闭后返回 NOT_WAITING，不检查来源对象；这不能推断系统完全没有网络流量。

诊断中的两个 `product_*_latch=CLOSED` 是 P25 当前策略声明，`local_lease_scope=NOT_PRODUCT_LATCH`；合成实例的 lease 开闭只由本地测试检查。这些声明不能代替 P26 对真实运行状态的裁决。字段盘点保持 NOT_STARTED，不提升来源资格或正式 Parser/Provider 定位。

## 等待、取消与输出边界

- 输入有效跨度、接收等待和辅助等待均不超过 120 秒；NaN、无穷、过大整数或超限拒绝。等待按剩余有效时间醒来刷新时钟，回调和发布前也检查过期。
- 普通路由不匹配返回 `MITMPROXY_BRIDGE_IGNORED`：只读允许的路由元数据，不读 response，不消耗业务事件预算，不延长原 deadline。异常 matcher、非布尔返回、目标漂移、敏感输入和无效投影仍停止。
- 端点与大小之后，敏感检查先于目标识别和投影。异常文本不外传，诊断仅固定码与有限计数。
- 取消可撤销等待或解析中的 lease；受托纯函数正在执行时，等待其返回后清理，不能越过取消继续发布。取消不自动重试。
- 发布开始是提交边界。此时取消返回诊断 `cancel_status=PUBLICATION_IN_PROGRESS`，表示这次取消未撤销提交；已完成结果不删除。发布仍使用原有独占目录、无覆盖和失败清理机制。
- 输出根在 prepare 与 start 前预检：规范绝对目录、0700、写/进入权限、无同名目标。预检不保留描述符、不写文件；不能保证之后文件系统永不变化，publisher 仍作最终无覆盖校验。

## P26 的开发者识别步骤

1. 先明确目标、用途及识别/结果试跑各自的最小输入范围、预算、停止条件和新鲜引用。不能以 P25 accepted 自动开启任何真实能力。
2. 在获准识别窗口中，仅检查明示范围内的公开业务响应。原始内容只在允许的瞬时内存边界处理；敏感内容先拒绝，不保存整包、URL、headers、Cookie、值哈希或自由错误。目标以当前事实确认，不从历史 raw 或合成标签推断。
3. 开发者固定无值 shape、family/version、字段路径与归属、金额单位/币种、同观察绑定及敏感拒绝规则。含义不明标待确认，不能猜值。映射先做对应合成回归。
4. 单独确认当前转发、加载、回调与目标页面就绪，准备新的输出根、锁和参数；用户仅完成必须本人决定/操作的事项。
5. 新鲜结果试跑与识别窗口分别记录，每个获准窗口一次、最多 120 秒，不自动重开。成功基础表才能进入 P27 的真实核对。
6. P26 开始无值字段盘点：稳定名、含义、归属、单位/枚举、核心性、适用条件、无值结构标签、可得/导出状态和对应任务。六类扩充与全店范围仍属于后续任务。
