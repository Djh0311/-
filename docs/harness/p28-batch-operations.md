# P28 当前店铺批量公开输入与集中分析

当前：125项相关本地回归通过。第2个新窗口实际发布56条分类SKU记录、32个商品、44个SKU及完整有界公开字段批次；当前来源逐条核对、JSON/CSV/manifest一致性及闭合合同通过，见[交付报告](reports/P28-delivery-report.md)。新根累计识别0/结果2；两个窗口都已关闭、两latch=CLOSED，本次专用CA已按创建身份移除。用户要求本轮结束后停止，不再执行下面历史启动命令或启动后续任务，产品仍incomplete。第1次TLS失败原事实见[原收据](reports/P28-batch-window1-close-receipt.json)，当前状态见[窗口状态](reports/P28-batch-window-current-status.json)。

用户已明确要求统一抓取数据后分析，沿用同一已确认小程序/店铺及之前获准的临时CA、手动信任和准确PID网络扩展能力；不重开图像UI，不重复询问已批准网络扩展。业务目标来自本次`current-business-choice.json`，旧目标编号、配置、输入锁和结果不复用。

## 范围、预算与输出

| 项目 | 本次准备 |
| --- | --- |
| 来源 | 当前准确网络helper PID，TLS来源wx.waimai.meituan.com，两条此前实际确认的FOOD和PRODUCTLIST POST路由；实际PID在prepare和start前重新核对，组件存在不等于转发就绪 |
| 归属 | 当前店名匹配poi_info；两份新鲜FORM的poi_id_str分别匹配公开字符串编号、wm_poi_id分别匹配公开数字编号，两请求对应编号相等；响应间隔≤10秒 |
| 输入 | 完整遍历这两份响应的公开数组、字段结构及合格标量，不截取前三个商品或只取最低价SKU。私有分支只登记字段路径/类型，值不解码；未知含义保留DEVELOPER_REVIEW_REQUIRED |
| 预算 | 单响应编码/解码各≤1MiB，响应累计内存预算≤4MiB；新窗口最多短暂保留两份待关联原文，每份≤10秒，关闭即清空。节点≤40000、深度≤32、结构路径≤4096、选取公开路径≤1024、公开标量每份≤8000、字符串≤256字，合并字段产物≤4MiB；并发读取≤8。会话无时间或尝试总次数上限，仍不自动重试 |
| 发布 | 新根下public-business-fields.json记录公开标量/坐标、无值结构和来源校验；first_result/下records.json、records.csv、manifest.json按新P28模型发布。0700目录、0600文件、Git忽略、禁止覆盖；不保存整包、URL、headers、凭据、值哈希或自由错误 |
| 完整程度 | CURRENT_RESPONSES_ONLY；当前入口收齐第一组合格输入后关闭，再分析覆盖和未知字段。尚未实现全店分页，不承诺本次两响应含全店或所有路由；分析出的缺口继续按实际事实处理 |
| 停止 | 收齐发布、目标或FORM关联失败、同观察过期、预算/结构/解析/发布失败、取消、异常或接收器丢失即关闭，不自动重开或延长原文租约；无结果仍incomplete |

本次新根：`/Users/yoyi/爬虫/runtime-output/p28_batch_94e07ee25b324ca7a9082efac2c5f3de`。旧P26识别22/结果2作为历史事实单独保留，新根从实际零尝试开始；新批量窗口归入RESULT，实际start增加新结果尝试一次，关闭不重复累计。

## 本轮用户系统动作与结束状态

上一轮[清理收据](reports/P26-ca-cleanup-receipt.json)确认专用CA六文件及目录已删除，其中配套私钥不能再签发HTTPS证书。旧钥匙串信任不能代替私钥。本次新CA目录与私钥已经由既有获准准备程序创建，不读取或导出私钥。

本次公开证书原位置：`/Users/yoyi/爬虫/runtime-output/p28_batch_94e07ee25b324ca7a9082efac2c5f3de/p26_transport_82c127bac3b549259d2071d7eae57b17/mitmproxy-ca-cert.cer`，结束后已删除。用户本人完成导入与准确SSL信任确认；第2窗口实际TLS/业务输入通过。证书名称为`P26 Temporary CA e7fad42c47fa43139df75bb714804e70`，P26是生成器名称，不是旧证书重用。用户手动删除登录钥匙串中的这一张证书仍待确认，开发者不代改keychain；见[清理收据](reports/P28-ca-cleanup-receipt.json)。

没有用户明确完成事实时ca_trust仍NOT_CONFIRMED，不读取或代改keychain。手动信任完成后开发者更新本次控制并重新预检；网络扩展不重装，不再要求批准已授予的能力。

## 本轮准备与启动命令记录（已结束）

以下记录本轮实际入口与步骤；当前CA已移除、用户要求停止，不能用这些旧控制引用重开。PREPARED只证明程序准备，与实际TLS/回调就绪分别判断。

只读准备，不启动网络或消费输入：

```sh
cd /Users/yoyi/爬虫
PYTHONDONTWRITEBYTECODE=1 /Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B \
  -m collection_adapter.p26_identification_host \
  --output-root /Users/yoyi/爬虫/runtime-output/p28_batch_94e07ee25b324ca7a9082efac2c5f3de
```

只有手动信任、输出边界和当前进程预检通过才返回P26_IDENTIFICATION_HOST_PREPARED，program_preparation=COMPLETE、source_ready=UNKNOWN、零尝试、两latch=CLOSED；不能凭PREPARED宣称真实转发成功。

由开发者在保持stdin的终端启动新接收器：

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/yoyi/.local/share/uv/tools/mitmproxy/bin/python -B \
  -m collection_adapter.p26_identification_host \
  --output-root /Users/yoyi/爬虫/runtime-output/p28_batch_94e07ee25b324ca7a9082efac2c5f3de \
  --serve-identification \
  --inspect-current-domain wx.waimai.meituan.com \
  --batch-public-json --identify-field-layout-only \
  --inspect-sensitive-field-keys --inspect-public-fields \
  --analyze-current-store-batch
```

P26_RECEIVER_READY_NOT_STARTED仍拒绝输入、零尝试；开发者发送`start`，重复校验当前输出/CA/PID后才激活，两latch=OPEN，并输出P26_RESULT_STARTED。该参数复用宿主入口名字，实际批量窗口是RESULT，独立result-attempt锁及result-host关闭收据，不算额外识别成功。

确认实际启动后，用户回到小程序首页，再进入同一家店铺并停在商品列表即可；没有官方刷新按钮时无需找刷新按钮，不逐个打开商品、不操作购物车。开发者用`status`看固定状态码和有限计数。新公开字段由开发者集中分析，不要求用户找接口、字段、Cookie或技术参数。

## 关闭与验证

`stop`或Ctrl-C关闭本轮，成功/失败均清空原文及FORM租约、清除转发并关闭自有连接，写独立无值收据、准确次数及两latch=CLOSED。收据必须核对cleanup和diagnostic_output_complete；关闭不等于卸载已经批准的网络扩展。

结束本次真实工作后，仅按创建身份删除本次自有CA六文件及目录，保留结果。用户本人删除本次登录钥匙串证书；开发者不代改keychain。仅本次证书，不操作其它系统设置或调用者。

本次准备历史事实见[批量准备收据](reports/P28-batch-preparation-checks.json)，实际新鲜结果见[直接核对](reports/P28-direct-batch-result-check.json)及[交付报告](reports/P28-delivery-report.md)。字段含义与缺口见[无值盘点](reports/P28-field-inventory-current.json)；属性选项到SKU对应、可选优惠费用和全店覆盖仍待确认。
