# 商品与门店详情交付索引

2026-10-15：已将窗口34既有公开详情副本转换为门店详情 JSON/CSV，并与窗口30的商品交付建立双编号关联。没有重新采集，也没有覆盖旧表。它们是不同时间的观察，关联仅确认门店身份。

## 文件怎么用

| 用途 | 文件 | 范围 |
| --- | --- | --- |
| 主商品表 | [商品 CSV](../../runtime-output/p29_pages_6544736b307c4a96b9868fa113870995/p31_context_codes_2a4d1133164b47759b068ddc8410c5a3/records.csv) | 231行、153商品、198 SKU、19分类；同商品跨分类不算新增商品 |
| 原列表门店表 | [原门店 CSV](../../runtime-output/p29_pages_6544736b307c4a96b9868fa113870995/p31_context_codes_2a4d1133164b47759b068ddc8410c5a3/stores.csv) | 保留原观察的价格、配送等字段 |
| 新门店详情表 | [详情 CSV](../../runtime-output/p29_pages_134d3b6061b64235b1bfbfde88928d7d/p31_store_detail_7f78b57ab84a4dc6ac7dfdaff4f0e609/stores.csv)、[详情 JSON](../../runtime-output/p29_pages_134d3b6061b64235b1bfbfde88928d7d/p31_store_detail_7f78b57ab84a4dc6ac7dfdaff4f0e609/stores.json) | 1行；地址、公开电话、配送时段、说明、服务、标签、公告 |
| 关联依据 | [关联说明 JSON](../../runtime-output/p29_pages_134d3b6061b64235b1bfbfde88928d7d/p31_store_detail_7f78b57ab84a4dc6ac7dfdaff4f0e609/association.json) | 两种公开门店编号一致，店名也一致；记录商品结果目录、双方窗口及各自时间 |
| 新表字段与缺项 | [字段字典](../../runtime-output/p29_pages_134d3b6061b64235b1bfbfde88928d7d/p31_store_detail_7f78b57ab84a4dc6ac7dfdaff4f0e609/field_dictionary.json)、[缺项清单](../../runtime-output/p29_pages_134d3b6061b64235b1bfbfde88928d7d/p31_store_detail_7f78b57ab84a4dc6ac7dfdaff4f0e609/coverage.json) | 9组字段；更早的缺项说明保留 |
| 详情配送补充 | [配送 CSV](../../runtime-output/p29_pages_134d3b6061b64235b1bfbfde88928d7d/p31_detail_gap_68965c2eae1749198b63021b4de7133d/delivery.csv)、[路径归类](../../runtime-output/p29_pages_134d3b6061b64235b1bfbfde88928d7d/p31_detail_gap_68965c2eae1749198b63021b4de7133d/path_disposition.json) | 同一详情观察的6个来源标量；87条路径归类不含业务值 |

商品字段字典、原覆盖清单、公开文本和来源代码表仍在同一商品结果目录。

主商品表没有逐行门店编号。关联文件明确绑定整个商品结果目录及其唯一门店表，并校验商品行所属窗口和计数。不能仅按店名或把其他目录的商品拿来套用此关联。

窗口31的[55行首页样本](../../runtime-output/p29_pages_40fa56739ccf4f77b5d6e1d8960a7a96/observation_4bf34efd5cf74c1db76fc77c533c1d5b/records.csv)和窗口24的[6行历史优惠标签](../../runtime-output/p29_pages_a20c00a2b8c34da09b76212f9e3764f8/p31_store_promotions_58e544c8116b4eec8836cd500eb32e03/records.csv)作为独立补充保留，不累加到231行，不当作当前完整优惠规则。这两份文件的数量沿用10月14日报告，本次没有重新核对其业务内容。

## 详情表的含义

- `store_id` 是详情自身的公开字符串编号，`store_numeric_id` 是详情自身的数字编号（以十进制文本保存，避免精度损失）。两个编号分别与主交付门店表比对；只同名而编号不一致会拒绝导出。
- `source_file`、`observed_at`、`window_ref` 始终属于详情自身。原商品、原门店表保留自己的时间，不能把后来的地址或配送说明说成采商品时已观察到。
- `delivery_period` 是配送时段，不是营业时间，也不是预计送达时间。
- `phones_json`、`services_json`、`tags_json` 是带 `index`、`value`、`state` 的JSON数组；不拼接或丢掉原索引。实际分别有1、3、2项。
- 每组字段都有状态列：`PRESENT_AS_OBSERVED` 表示保留来源文字；`SOURCE_NULL` 表示来源为null；`SOURCE_EMPTY` 表示空字符串或空数组；`NOT_OBSERVED` 表示未观察到；`SOURCE_REJECTED`、`PARTIAL_REJECTED` 表示公开投影筛除了全部或部分内容，不等于来源未提供。
- CSV按通用导入格式保留文字；电话、编号、时间和JSON列导入表格软件时按文本读取。原商品的金额单位与语义状态照旧保留，本次不对任何新金额作确认。

## 还缺什么

1. 独立营业时间在这份详情副本中没有对应路径。配送时段保持 `delivery_period`。列表门店表里的 `store_shipping_time_text` 也留在自己的观察，不填到营业时间。
2. 完整优惠规则在这份详情副本中没有优惠、券或活动路径。窗口24的6条展示标签和商品促销文字仍各自保留。
3. 2026-10-16 已从同一详情副本另存6个配送来源标量：服务文字、信息类型文字、类型数字、距离文字、地图显示范围数字、地图类型数字。枚举和单位未确认。地图显示范围保持原名，不作为配送边界。费用、起送和范围边界路径在这份详情里缺失；窗口30门店表已有的费用字段留在原观察时间。
4. 详情副本的 87 条路径已逐项归类，未归类为 0。其中 13 条公开标量含义未确认，未导出；图片、URL 和门店经纬度不导出。这仍不等于全部字段语义已经完成。
5. 单份副本出错后的持续处理已有本地合成修复，见[报告](reports/P29-copy-continuation-2026-10-16.md)。重复真实采集仍未验收。

路径归类和配送补充的核对见[报告](reports/P31-detail-gap-review-2026-10-16.md)。

## 本地再次导出

已有输入可用时执行下列命令。每次只生成新的独占结果目录，旧文件不覆盖；输入编号不匹配、权限不符或合同校验失败时拒绝。该入口仅支持当前 `p31_context_codes` 商品结果版本，不会搜索其他输入或启动接收器。

```sh
python3 -B -m collection_adapter.p31_store_detail_export \
  --detail-root /Users/yoyi/爬虫/runtime-output/p29_pages_134d3b6061b64235b1bfbfde88928d7d \
  --detail-file store_detail_6c1d69a1d3824d58bba3ce2fd5cdf8f8-public-fields.json \
  --product-root /Users/yoyi/爬虫/runtime-output/p29_pages_6544736b307c4a96b9868fa113870995 \
  --product-result p31_context_codes_2a4d1133164b47759b068ddc8410c5a3
```

同一详情副本的路径归类和6个配送标量用下面的入口。它不读取商品包，不改上面的9组字段表。

```sh
python3 -B -m collection_adapter.p31_detail_gap_review \
  --detail-root /Users/yoyi/爬虫/runtime-output/p29_pages_134d3b6061b64235b1bfbfde88928d7d \
  --detail-file store_detail_6c1d69a1d3824d58bba3ce2fd5cdf8f8-public-fields.json
```

验证依据：[实际文件核对](reports/P31-store-detail-export-direct-check-2026-10-15.json)、[实现与验证记录](reports/P31-store-detail-export-2026-10-15.md)、[详情缺口核对](reports/P31-detail-gap-review-direct-check-2026-10-16.json)。旧P32入口仍定位其原有历史交付，本次使用上面的明确文件链接。
