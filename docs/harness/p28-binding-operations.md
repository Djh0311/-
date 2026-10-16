# P28 规格关联本地入口

状态：本地合同/组装/视图及既有获准公开投影的内存复核可调用；新鲜批量入口已实际发布并核对56条分类SKU记录、32个商品、44个SKU，见[交付报告](reports/P28-delivery-report.md)。当前接收器和两latch已关闭，用户要求本轮结束后停止；图像UI保持停用，正式来源资格不提升。

## 开发者调用

`parser_candidate.p28_profile.p28_registry()`注册新观察规则；`collection_core.p28.build_p28_batch(events, registry, context, price_evidence)`要求同观察的FOOD/PRODUCTLIST及明确CNY元依据，输出带预期SKU清单的版本化模型。`render_p28_result(binding)`生成SKU行、商品最低展示价和各自缺失状态。发布器仅接受从该绑定模型重新生成且JSON/CSV一致的视图，使用既有0700/no-clobber策略。

本轮真实业务文件由[批量入口](p28-batch-operations.md)在新0700忽略根独占发布。以下旧投影命令仅作指定既有观察的内存复核，保留原时点和关联局限，不生成新结果或消耗尝试。未来输出仍须新的当次边界，不能复用旧结果名称或输入锁。

以下只读命令由开发者填入已获准的具体公开投影及当前业务对象，用户不负责寻找字段或技术参数：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m collection_adapter.p28_projection_review \
  --root '<既有获准公开投影的0700根>' \
  --projection-file '<明确获准的identification-public-projection文件名>' \
  --expected-store '<当前已确认店铺名>' \
  --price-evidence-ref 'evidence:<已核对页面价格单位的引用>'
```

入口拒绝其它文件名、symlink、非0600文件、超4MiB输入及恢复数组总容量超8000的情况；不搜索raw、不读请求/headers/Cookie，不打开网络或UI。受控投影的选定字段不可用时拒绝，不把非目标URL标记纳入P28字段。诊断只包含固定状态、有限计数和边界布尔值，不包含店铺/商品/价格业务值，也不生成业务文件或消耗尝试。

现有获准导出只证明旧观察中的选定公开标量。其来源路由关联标志尚未确认，复核明确保留`CORROBORATION_ONLY_NOT_NEW_ROUTING_PROOF`，不把它改成一次新鲜实时采集。SKU规格为空不从页面或商品单位补成网络字段。

## 必要验证

生产入口使用Python标准库；合同检查测试另使用当前本地已有的`jsonschema`和`referencing`，不临时联网安装。对应合成检查：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
  collection_core.tests.test_p28 \
  collection_core.tests.test_p28_result_views \
  collection_adapter.tests.test_p28_projection_review
```

已运行的相关旧Parser、P0/P1发布、P26结果窗口和P25边界回归、实际获准导出结构检查及局限见 [本地检查](reports/P28-local-binding-checks.json)、[导出复核](reports/P28-public-projection-review.json)和[合同检查](reports/P28-authorized-export-schema-checks.json)。合成或导出复核通过不能代替实时UI证据、全店覆盖或P28验收。
