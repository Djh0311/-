# 公开业务字段导入说明

2026-10-12 最新范围：用户明确“图片跳过”。图片下载、保存、图片标识及引用导出均移出当前交付范围，不再计入未完成项或验收缺口；不启动图片合同或解析实现。已有公开标签文字和业务结果保留。当前价格和费用均已确认为人民币元；其余语义、来源资格及全店覆盖结论不因本次范围调整而改变。

当前最新包：`p31_confirmed_units_f73fc5498c734905b23afa6c9442453d`，位于窗口 19 输出根，另新增 96 行独立公开来源码。已补上次审计的分类和根级 12 条公开文本路径；新增 104 行独立公开说明，商品表另外补齐初始 55 行的最低价关系与计量文字角色，门店和公开说明表保持不变。本份结果的价格/费用单位已由用户确认为人民币元；状态码和部分来源用途仍未知，不声明全部业务字段完成。见[本轮说明](reports/P31-context-fields-implementation.md)。


2026-10-12 用户范围确认：只要店铺和商品的公开信息，不需要个人领券状态、个人会员资格或账号专属优惠。公开展示的价格、优惠文案及条件仍在范围内；公开会员价来源数字不等于个人会员资格。两条券引用的账号关联用途仍是事实未知，继续不导出，不把它们断言为私人字段，也不再向用户重复询问是否需要个人优惠。该范围确认不改变未知单位/枚举、来源资格或全店覆盖结论。


当前 v7 包入口：`python3 -B -m collection_adapter.p31_confirmed_units_export`（原 v1–v6 包入口保留），显式传入 `--output-root`、`--observation-name` 和每个 `--input-name`。只整理已有获准公开投影，不启动网络或接收器。

## 文件与关联

- `records.csv`：商品/SKU 主表，当前 233 行；保留分类与 SKU 的多对多展示关系，不按商品名合并。原 v4 列全部保留。
- `stores.csv`：门店与配送观察表，当前 1 行；按 `window_ref` 关联本次店铺上下文，不能将其数值当成每条商品自身响应的字段，也不代表配送费用适用于所有客户。
- `public_texts.csv`、`public_texts.json`：104 行独立公开说明，分类通过 `category_ref` 关联，根级说明只关联 `window_ref`。自身端点、请求引用和时间均保留，不借到 SKU 行。
- `public_codes.csv`、`public_codes.json`：公开来源码/标记表，当前 96 行；保留原类型、状态和来源，不解释为个人资格。
- `records.json`、`stores.json`：保留 null、布尔类型及属性/优惠数组的完整对应结构。
- `field_dictionary.json`：逐列中文说明、类型、来源路径或原 v4 字段标记。
- `coverage.json`：每个新增标量字段在输出行中的状态计数，以及未推定和明确排除的范围。
- `manifest.json`：文件列表、版本及行数；不声明完整业务资格或目标系统导入通过。

## 导入规则

UTF-8 编码、逗号分隔、标准双引号转义；包含逗号或引号的文字应交给 CSV 解析器读取，不能手动按逗号拆行。编号、状态码和数字字符串按文本读入；金额运算需使用精确十进制并先确认该行单位。不要让表格软件自动把长编号转换为浮点数。布尔列使用 `true` / `false`。

空单元格不等于数字 0。新增字段的 `_state` 表示：`NOT_OBSERVED` 为所选公开投影中未观察到该标量，`SOURCE_NULL` 为明确 null，`SOURCE_EMPTY` 为空文字，`PRESENT_UNCONFIRMED` 为字段已保留但业务语义未升级，`NEGATIVE_SEMANTICS_UNCONFIRMED` 为负数仍保留、哨兵含义未知。旧 v4 状态列沿用既有定义，不将其不同状态强制合并。

`product_attributes_json` 保存属性组和选项的索引、编号、文字、限制来源数字及状态；解析 JSON 后可按 `attribute_index` / `value_index` 展开。属性选项不等于具体 SKU 组合。`sku_full_discount_tag_texts_json` 保留优惠文本标签与子标签索引。JSON 文件另有相应真实数组。没有可用属性标量时保留未观察到状态，不能据此断言平台不存在该属性。

来源字段名可提示用途，但不能证明状态码含义、库存负数代表不限量、销量统计的精确周期、配送时间单位或统一金额单位。`shipping_time` 保留来源文字，不直接重命名为营业时间。原初始行已有 CNY/YUAN 依据保持，分类行不借单位。

用户明确不需要目标系统导入验证；当前只核对 CSV/JSON 及来源一致性，不以系统导入作为待办。未知金额单位或状态码保持原值及未确认状态。

## 主表列

| 字段 | 中文说明 | 数据类型 |
| --- | --- | --- |
| `category_reference_label` | 分类参考名称 | string |
| `product_name` | 商品名称 | string |
| `sku_spec` | SKU规格名称 | string |
| `sku_price_number` | 来源SKU价格数字 | decimal-string |
| `product_min_price_number` | 来源商品最低价数字 | decimal-string |
| `sku_origin_number` | 来源SKU原价数字 | decimal-string |
| `product_unit` | 商品计量文字 | string |
| `sku_description` | SKU规格说明（spec_desc） | string |
| `currency` | 币种，仅采用该行已有确认依据 | string |
| `amount_unit` | 金额单位，仅采用该行已有确认依据 | string |
| `currency_status` | 币种确认状态 | string |
| `amount_unit_status` | 金额单位确认状态 | string |
| `currency_basis` | 币种确认依据 | string |
| `amount_unit_basis` | 金额单位确认依据 | string |
| `sku_price_source` | SKU价格来源依据 | string |
| `numeric_min_relation` | 最低价数字关系核对状态 | string |
| `product_unit_role` | 商品计量文字角色 | string |
| `render_origin_number` | 来源渲染原价数字 | decimal-string |
| `render_origin_state` | 来源渲染原价数字：缺失或解析状态 | string |
| `product_full_discount_price_number` | 商品full_discount_price数字 | decimal-string |
| `product_full_discount_price_state` | 商品full_discount_price数字：缺失或解析状态 | string |
| `sku_member_price_number` | SKU会员价来源数字 | decimal-string |
| `sku_member_price_state` | SKU会员价来源数字：缺失或解析状态 | string |
| `sku_full_discount_price_number` | SKU full_discount_price数字 | decimal-string |
| `sku_full_discount_price_state` | SKU full_discount_price数字：缺失或解析状态 | string |
| `sku_box_price_number` | SKU包装费来源数字 | decimal-string |
| `sku_box_price_state` | SKU包装费来源数字：缺失或解析状态 | string |
| `min_price_tail` | 最低价尾部说明 | string |
| `min_price_tail_state` | 最低价尾部说明：缺失或解析状态 | string |
| `render_price_desc` | 商品价格说明 | string |
| `render_price_desc_state` | 商品价格说明：缺失或解析状态 | string |
| `sku_price_desc` | SKU价格说明 | string |
| `sku_price_desc_state` | SKU价格说明：缺失或解析状态 | string |
| `product_discount_by_count_scope` | 商品数量折扣适用对象 | string |
| `product_discount_by_count_count_number` | 商品数量折扣的数量条件数字 | decimal-string |
| `product_discount_by_count_count_state` | 商品数量折扣的数量条件数字：缺失或解析状态 | string |
| `product_discount_by_count_discount_number` | 商品数量折扣数字，算法未确认 | decimal-string |
| `product_discount_by_count_discount_state` | 商品数量折扣数字，算法未确认：缺失或解析状态 | string |
| `product_discount_by_count_pair_state` | 商品数量条件配对状态，仅说明键是否同时出现 | string |
| `sku_discount_by_count_scope` | SKU数量折扣适用对象 | string |
| `sku_discount_by_count_count_number` | SKU数量折扣的数量条件数字 | decimal-string |
| `sku_discount_by_count_count_state` | SKU数量折扣的数量条件数字：缺失或解析状态 | string |
| `sku_discount_by_count_discount_number` | SKU数量折扣数字，算法未确认 | decimal-string |
| `sku_discount_by_count_discount_state` | SKU数量折扣数字，算法未确认：缺失或解析状态 | string |
| `sku_discount_by_count_pair_state` | SKU数量条件配对状态，仅说明键是否同时出现 | string |
| `product_max_discount_number` | 商品max_discount来源数字 | decimal-string |
| `product_max_discount_state` | 商品max_discount来源数字：缺失或解析状态 | string |
| `product_preferential_feeling_price_number` | 商品优惠体感价来源数字 | decimal-string |
| `product_preferential_feeling_price_state` | 商品优惠体感价来源数字：缺失或解析状态 | string |
| `product_coupon_count_number` | 商品coupon_count来源数字 | decimal-string |
| `product_coupon_count_state` | 商品coupon_count来源数字：缺失或解析状态 | string |
| `product_coupons_per_price_number` | 商品coupons_per_price来源数字 | decimal-string |
| `product_coupons_per_price_state` | 商品coupons_per_price来源数字：缺失或解析状态 | string |
| `product_multi_activity_price_number` | 商品multi_activity_price来源数字 | decimal-string |
| `product_multi_activity_price_state` | 商品multi_activity_price来源数字：缺失或解析状态 | string |
| `product_show_origin_price_number` | 商品show_origin_price来源数字 | decimal-string |
| `product_show_origin_price_state` | 商品show_origin_price来源数字：缺失或解析状态 | string |
| `product_discount_tag_text` | 商品优惠标签文字 | string |
| `product_discount_tag_text_state` | 商品优惠标签文字：缺失或解析状态 | string |
| `sku_ladder_package_food_num_number` | SKU阶梯包装数量条件数字 | decimal-string |
| `sku_ladder_package_food_num_state` | SKU阶梯包装数量条件数字：缺失或解析状态 | string |
| `sku_ladder_package_price_number` | SKU阶梯包装费用来源数字 | decimal-string |
| `sku_ladder_package_price_state` | SKU阶梯包装费用来源数字：缺失或解析状态 | string |
| `sku_ladder_package_pair_state` | SKU数量条件配对状态，仅说明键是否同时出现 | string |
| `sku_full_discount_tag_texts_json` | SKU优惠文本分组JSON，保留标签与子标签索引 | json-string |
| `sku_full_discount_tag_texts_state` | SKU优惠文本分组JSON，保留标签与子标签索引：缺失或解析状态 | string |
| `source_kind` | 初始已核对行或分类候选行 | string |
| `category_ref` | 分类编号 | string |
| `product_id` | 商品编号 | string |
| `sku_id` | SKU编号 | string |
| `sku_spec_state` | SKU规格名称：缺失或解析状态 | string |
| `sku_description_state` | SKU规格说明（spec_desc）：缺失或解析状态 | string |
| `product_unit_state` | 商品计量文字：缺失或解析状态 | string |
| `source_file` | 该行自身公开投影文件 | string |
| `source_request_ref` | 该行自身来源请求引用 | string |
| `observed_at` | 该行自身观察时间 | string |
| `category_label_source_file` | 分类参考名称的来源文件 | string |
| `category_label_source_request_ref` | 分类参考名称的请求引用 | string |
| `category_label_observed_at` | 分类参考名称的观察时间 | string |
| `window_ref` | 窗口引用，用于关联本包来源 | string |
| `product_description_text` | 商品说明文字 | text |
| `product_description_text_state` | 商品说明文字：缺失或解析状态 | enum-string |
| `product_month_saled_number` | 商品月销量来源数字（精确口径未确认） | decimal-string |
| `product_month_saled_number_state` | 商品月销量来源数字（精确口径未确认）：缺失或解析状态 | enum-string |
| `product_status_code` | 商品状态码（枚举含义未确认） | decimal-string |
| `product_status_code_state` | 商品状态码（枚举含义未确认）：缺失或解析状态 | enum-string |
| `product_status_description_text` | 商品状态说明文字 | text |
| `product_status_description_text_state` | 商品状态说明文字：缺失或解析状态 | enum-string |
| `product_stock_number` | 商品stock库存来源数字（哨兵含义未确认） | decimal-string |
| `product_stock_number_state` | 商品stock库存来源数字（哨兵含义未确认）：缺失或解析状态 | enum-string |
| `product_has_food_flag` | 商品has_food来源标记 | boolean |
| `product_has_food_flag_state` | 商品has_food来源标记：缺失或解析状态 | enum-string |
| `product_forbid_single_buy_text` | 商品禁止单购来源说明 | text |
| `product_forbid_single_buy_text_state` | 商品禁止单购来源说明：缺失或解析状态 | enum-string |
| `product_sku_label_text` | 商品规格标签 | text |
| `product_sku_label_text_state` | 商品规格标签：缺失或解析状态 | enum-string |
| `product_activity_tag_text` | 商品活动标签 | text |
| `product_activity_tag_text_state` | 商品活动标签：缺失或解析状态 | enum-string |
| `product_activity_type_code` | 商品活动类型码 | decimal-string |
| `product_activity_type_code_state` | 商品活动类型码：缺失或解析状态 | enum-string |
| `product_has_multi_sale_attr_flag` | 商品多销售属性标记 | boolean |
| `product_has_multi_sale_attr_flag_state` | 商品多销售属性标记：缺失或解析状态 | enum-string |
| `sku_public_description_text` | SKU说明文字 | text |
| `sku_public_description_text_state` | SKU说明文字：缺失或解析状态 | enum-string |
| `sku_spec_info_text` | SKU规格补充说明 | text |
| `sku_spec_info_text_state` | SKU规格补充说明：缺失或解析状态 | enum-string |
| `sku_min_order_count_number` | SKU起购数量来源数字 | decimal-string |
| `sku_min_order_count_number_state` | SKU起购数量来源数字：缺失或解析状态 | enum-string |
| `sku_stock_number` | SKUstock库存来源数字（哨兵含义未确认） | decimal-string |
| `sku_stock_number_state` | SKUstock库存来源数字（哨兵含义未确认）：缺失或解析状态 | enum-string |
| `sku_real_stock_number` | SKUreal_stock库存来源数字（哨兵含义未确认） | decimal-string |
| `sku_real_stock_number_state` | SKUreal_stock库存来源数字（哨兵含义未确认）：缺失或解析状态 | enum-string |
| `sku_status_code` | SKU状态码（枚举含义未确认） | decimal-string |
| `sku_status_code_state` | SKU状态码（枚举含义未确认）：缺失或解析状态 | enum-string |
| `sku_restrict_number` | SKU限制数量来源数字 | decimal-string |
| `sku_restrict_number_state` | SKU限制数量来源数字：缺失或解析状态 | enum-string |
| `sku_count_number` | SKUcount来源数字 | decimal-string |
| `sku_count_number_state` | SKUcount来源数字：缺失或解析状态 | enum-string |
| `sku_box_num_number` | SKU包装数量来源数字 | decimal-string |
| `sku_box_num_number_state` | SKU包装数量来源数字：缺失或解析状态 | enum-string |
| `sku_promotion_info_text` | SKU促销补充说明 | text |
| `sku_promotion_info_text_state` | SKU促销补充说明：缺失或解析状态 | enum-string |
| `sku_promotion_text` | SKU促销文字 | text |
| `sku_promotion_text_state` | SKU促销文字：缺失或解析状态 | enum-string |
| `sku_promotion_restrict_text` | SKU促销限制文字 | text |
| `sku_promotion_restrict_text_state` | SKU促销限制文字：缺失或解析状态 | enum-string |
| `sku_promotion_addition_text` | SKU促销附加文字 | text |
| `sku_promotion_addition_text_state` | SKU促销附加文字：缺失或解析状态 | enum-string |
| `product_attributes_json` | 商品属性分组JSON，不代表已选SKU组合 | json-string |
| `product_attributes_state` | 商品属性分组JSON，不代表已选SKU组合：缺失或解析状态 | string |

## 门店表列

| 字段 | 中文说明 | 数据类型 |
| --- | --- | --- |
| `store_id` | 门店公开编号 | string |
| `store_name` | 门店名称 | string |
| `source_file` | 该行自身公开投影文件 | string |
| `source_request_ref` | 该行自身来源请求引用 | string |
| `observed_at` | 该行自身观察时间 | string |
| `window_ref` | 窗口引用，用于关联本包来源 | string |
| `store_address_text` | 门店公开营业地址 | text |
| `store_address_text_state` | 门店公开营业地址：缺失或解析状态 | enum-string |
| `store_bulletin_text` | 门店门店公告 | text |
| `store_bulletin_text_state` | 门店门店公告：缺失或解析状态 | enum-string |
| `store_shipping_time_text` | 门店shipping_time来源文字（不推定营业时段） | text |
| `store_shipping_time_text_state` | 门店shipping_time来源文字（不推定营业时段）：缺失或解析状态 | enum-string |
| `store_min_price_tip_text` | 门店最低金额说明 | text |
| `store_min_price_tip_text_state` | 门店最低金额说明：缺失或解析状态 | enum-string |
| `store_shipping_fee_tip_text` | 门店配送费说明 | text |
| `store_shipping_fee_tip_text_state` | 门店配送费说明：缺失或解析状态 | enum-string |
| `store_origin_shipping_fee_tip_text` | 门店原配送费说明 | text |
| `store_origin_shipping_fee_tip_text_state` | 门店原配送费说明：缺失或解析状态 | enum-string |
| `store_delivery_time_tip_text` | 门店配送时间说明 | text |
| `store_delivery_time_tip_text_state` | 门店配送时间说明：缺失或解析状态 | enum-string |
| `store_delivery_tips_text` | 门店配送提示 | text |
| `store_delivery_tips_text_state` | 门店配送提示：缺失或解析状态 | enum-string |
| `store_app_delivery_tip_text` | 门店配送服务说明 | text |
| `store_app_delivery_tip_text_state` | 门店配送服务说明：缺失或解析状态 | enum-string |
| `store_poi_prepare_time_text` | 门店备餐时间来源文字 | text |
| `store_poi_prepare_time_text_state` | 门店备餐时间来源文字：缺失或解析状态 | enum-string |
| `store_status_code` | 门店状态码（枚举含义未确认） | decimal-string |
| `store_status_code_state` | 门店状态码（枚举含义未确认）：缺失或解析状态 | enum-string |
| `store_poi_sell_status_code` | 门店门店销售状态码 | decimal-string |
| `store_poi_sell_status_code_state` | 门店门店销售状态码：缺失或解析状态 | enum-string |
| `store_score_number` | 门店score评分来源数字 | decimal-string |
| `store_score_number_state` | 门店score评分来源数字：缺失或解析状态 | enum-string |
| `store_wm_poi_score_number` | 门店外卖评分来源数字 | decimal-string |
| `store_wm_poi_score_number_state` | 门店外卖评分来源数字：缺失或解析状态 | enum-string |
| `store_dp_score_number` | 门店点评评分来源数字 | decimal-string |
| `store_dp_score_number_state` | 门店点评评分来源数字：缺失或解析状态 | enum-string |
| `store_comment_number` | 门店评论数量来源数字 | decimal-string |
| `store_comment_number_state` | 门店评论数量来源数字：缺失或解析状态 | enum-string |
| `store_dp_comment_number` | 门店点评数量来源数字 | decimal-string |
| `store_dp_comment_number_state` | 门店点评数量来源数字：缺失或解析状态 | enum-string |
| `store_avg_delivery_time_number` | 门店平均配送时间来源数字（单位未确认） | decimal-string |
| `store_avg_delivery_time_number_state` | 门店平均配送时间来源数字（单位未确认）：缺失或解析状态 | enum-string |
| `store_min_price_number` | 门店门店最低金额来源数字（单位及条件未确认） | decimal-string |
| `store_min_price_number_state` | 门店门店最低金额来源数字（单位及条件未确认）：缺失或解析状态 | enum-string |
| `store_shipping_fee_number` | 门店配送费来源数字（单位及条件未确认） | decimal-string |
| `store_shipping_fee_number_state` | 门店配送费来源数字（单位及条件未确认）：缺失或解析状态 | enum-string |
| `store_shipping_reduce_fee_number` | 门店配送减免来源数字（单位及条件未确认） | decimal-string |
| `store_shipping_reduce_fee_number_state` | 门店配送减免来源数字（单位及条件未确认）：缺失或解析状态 | enum-string |
| `store_delivery_type_code` | 门店配送类型码 | decimal-string |
| `store_delivery_type_code_state` | 门店配送类型码：缺失或解析状态 | enum-string |
| `store_shipping_fee_type_code` | 门店配送费类型码 | decimal-string |
| `store_shipping_fee_type_code_state` | 门店配送费类型码：缺失或解析状态 | enum-string |
| `store_invoice_support_code` | 门店发票支持来源码 | decimal-string |
| `store_invoice_support_code_state` | 门店发票支持来源码：缺失或解析状态 | enum-string |
| `store_is_meituan_delivery_flag` | 门店美团配送来源标记 | boolean |
| `store_is_meituan_delivery_flag_state` | 门店美团配送来源标记：缺失或解析状态 | enum-string |

## 当前缺口

所有新标量字段都有逐行状态，具体数量见输出的 `coverage.json`。本轮覆盖商品描述、销量/库存/状态来源数字、起购/限购与包装数量、促销文字、属性选项，以及门店公开地址/公告/评分/配送字段；不是将所有技术键计作业务字段。

- 语义待确认：库存与状态枚举、销量精确口径、属性选择约束、配送数字单位与适用条件、分类金额单位。
- 仍未全面适配：额外的商品内部分类/分组码、创建时间与展示标签体系等可见字段；它们不影响本轮已交付字段，但也不记为已完成。
- 明确排除：私人资料、客户位置/距离/个人范围和资格、任意 URL/图片、样式与追踪字段。本轮没有读取新响应或下载图片。


## v2 补漏字段与索引

当时 v2 结果：`p31_additional_fields_d332b8a0e269496c807954278e2d0e03`，位于同一窗口 19 输出根。原列和正常导出值不变，新增下列字段；每项另有 `_state` 列。

标量 ctime 不转换日期。多值 JSON 是 `{indices: [...], value: ..., state: ...}` 对象数组；单层标签一个索引、两层标签两个索引，排序仅为稳定输出，不推定对应 SKU。缺少选定标量时为 NOT_OBSERVED，不等于源数组不存在；条目中的 null/空字符串分别保留 SOURCE_NULL/SOURCE_EMPTY。规则编号与文字只在同一标签家族、同一记录、同一索引下关联。旧优惠文字中的 `tag_index` 对应新增优惠规则编号的 `indices[0]`。

| 表 | CSV 字段 | 说明 | 来源路径 |
| --- | --- | --- | --- |
| 商品/SKU | `product_activity_tag_id_text` | 活动标签来源编号 | `$.data.food_spu_tags[].dynamic_spus[].activity_tag_id` |
| 商品/SKU | `product_ctime_number` | ctime来源数字（不转换时间或猜单位） | `$.data.food_spu_tags[].dynamic_spus[].ctime` |
| 商品/SKU | `product_group_id_number` | 分组来源编号 | `$.data.food_spu_tags[].dynamic_spus[].group_id` |
| 商品/SKU | `product_spu_category_code` | spu_category来源分类码 | `$.data.food_spu_tags[].dynamic_spus[].spu_category` |
| 商品/SKU | `product_spu_type_code` | spu_type来源类型码 | `$.data.food_spu_tags[].dynamic_spus[].spu_type` |
| 商品/SKU | `product_tag_text` | 商品自身tag文字（不替代外层分类） | `$.data.food_spu_tags[].dynamic_spus[].tag` |
| 商品/SKU | `product_is_premium_spu_flag` | isPremiumSpu来源标记 | `$.data.food_spu_tags[].dynamic_spus[].isPremiumSpu` |
| 商品/SKU | `product_need_attr_accessory_flag` | 属性附属商品来源标记 | `$.data.food_spu_tags[].dynamic_spus[].need_attr_accessory_product` |
| 商品/SKU | `product_topping_flag` | topping_product来源标记 | `$.data.food_spu_tags[].dynamic_spus[].topping_product` |
| 商品/SKU | `product_button_text` | 商品按钮文案 | `$.data.food_spu_tags[].dynamic_spus[].render_info.btn_info.text` |
| 商品/SKU | `product_image_label_text` | 商品图片区域标签文字 | `$.data.food_spu_tags[].dynamic_spus[].render_info.img_area.label_text` |
| 商品/SKU | `product_rule_tag_text` | 商品规则标签文字 | `$.data.food_spu_tags[].dynamic_spus[].render_info.sup_info.ruleTag` |
| 商品/SKU | `sku_activity_stock_number` | 活动库存来源数字（哨兵含义未确认） | `$.data.food_spu_tags[].dynamic_spus[].skus[].activity_stock` |
| 商品/SKU | `sku_activity_tag_text` | SKU活动标签文字 | `$.data.food_spu_tags[].dynamic_spus[].skus[].activity_tag` |
| 商品/SKU | `sku_activity_tag_id_text` | SKU活动标签来源编号 | `$.data.food_spu_tags[].dynamic_spus[].skus[].activity_tag_id` |
| 商品/SKU | `sku_activity_type_code` | SKU活动来源类型码 | `$.data.food_spu_tags[].dynamic_spus[].skus[].activity_type` |
| 商品/SKU | `sku_promotion_activity_text` | SKU促销活动文案 | `$.data.food_spu_tags[].dynamic_spus[].skus[].promotion.activity_text` |
| 商品/SKU | `sku_promotion_activity_type_code` | SKU促销活动来源类型码 | `$.data.food_spu_tags[].dynamic_spus[].skus[].promotion.activity_type` |
| 商品/SKU | `sku_promotion_entry_item_id_number` | SKU促销入口来源编号 | `$.data.food_spu_tags[].dynamic_spus[].skus[].promotion.entry_item_id` |
| 商品/SKU | `sku_promotion_tag_texts_json` | SKU促销标签文字，保留两层索引 | `$.data.food_spu_tags[].dynamic_spus[].skus[].promotion_tag[].sub_tags[].text` |
| 商品/SKU | `sku_promotion_tag_rule_ids_json` | SKU促销标签规则编号，保留标签索引 | `$.data.food_spu_tags[].dynamic_spus[].skus[].promotion_tag[].rule_id` |
| 商品/SKU | `sku_full_discount_tag_rule_ids_json` | SKU优惠标签规则编号，按已有优惠文字标签索引关联 | `$.data.food_spu_tags[].dynamic_spus[].skus[].full_discount_tag[].rule_id` |
| 门店 | `store_numeric_id_number` | 门店数值编号（不替代字符串门店编号） | `$.data.poi_info.id` |
| 门店 | `store_buy_sku_count_threshold_number` | 门店购买SKU数量阈值来源数字（条件未确认） | `$.data.poi_info.buy_sku_count_threshold` |
| 门店 | `store_has_poi_env_flag` | 门店has_poi_env来源标记 | `$.data.poi_info.has_poi_env` |
| 门店 | `store_has_xbk_flag` | 门店has_xbk来源标记 | `$.data.poi_info.has_xbk` |
| 门店 | `store_restrict_toast_text` | 门店限制提示来源文字 | `$.data.poi_info.restrict_toast` |
| 门店 | `store_speed_refund_status_code` | 门店快速退款来源状态码（不推断服务承诺） | `$.data.poi_info.speed_refund_status` |
| 门店 | `store_support_pay_code` | 门店支付支持来源码（不推断支付方式） | `$.data.poi_info.support_pay` |
| 门店 | `store_brand_id_number` | 门店品牌来源编号 | `$.data.poi_info.brand_id` |
| 门店 | `store_origin_brand_id_number` | 门店原品牌来源编号 | `$.data.poi_info.origin_brand_id` |
| 门店 | `store_buz_code_number` | 门店buz_code来源数字 | `$.data.poi_info.buz_code` |
| 门店 | `store_buz_type_code` | 门店buz_type来源类型码 | `$.data.poi_info.buz_type` |
| 门店 | `store_shop_business_type_text` | 门店业务类型来源文字 | `$.data.poi_info.shop_business_type` |
| 门店 | `store_poi_sp_type_code` | 门店poi_sp_type来源类型码 | `$.data.poi_info.poi_sp_type` |
| 门店 | `store_buz_menu_tip_text` | 门店业务菜单说明 | `$.data.poi_info.buz_menu_tip` |
| 门店 | `store_attention_count_text` | 门店关注数量展示文字（不解析成精确数量） | `$.data.poi_info.attention_count_text` |
| 门店 | `store_per_cust_trans_text` | 门店per_cust_trans来源文字（单位含义未确认） | `$.data.poi_info.per_cust_trans` |
| 门店 | `store_impress_title_text` | 门店印象标题 | `$.data.poi_info.poi_impress.title` |
| 门店 | `store_service_title_text` | 门店服务标题 | `$.data.poi_info.poi_service_label.title` |
| 门店 | `store_impress_texts_json` | 门店印象标签文字 | `$.data.poi_info.poi_impress.impress_label[].label_text` |
| 门店 | `store_impress_descriptions_json` | 门店印象标签说明 | `$.data.poi_info.poi_impress.impress_label[].label_desc_text` |
| 门店 | `store_label_texts_json` | 门店标签文字 | `$.data.poi_info.poi_label.labels[].label_text` |
| 门店 | `store_label_descriptions_json` | 门店标签说明 | `$.data.poi_info.poi_label.labels[].label_desc_text` |
| 门店 | `store_new_label_texts_json` | 门店新版标签文字 | `$.data.poi_info.poi_label_new.labels[].label_text` |
| 门店 | `store_new_label_descriptions_json` | 门店新版标签说明 | `$.data.poi_info.poi_label_new.labels[].label_desc_text` |
| 门店 | `store_service_texts_json` | 门店服务标签文字 | `$.data.poi_info.poi_service_label.service_label[].label_text` |
| 门店 | `store_service_descriptions_json` | 门店服务标签说明 | `$.data.poi_info.poi_service_label.service_label[].label_desc_text` |
| 门店 | `store_normal_tag_texts_json` | 门店普通标签文字 | `$.data.poi_info.poi_normal_tags[].sub_tags[].text` |
| 门店 | `store_normal_tag_rule_ids_json` | 门店普通标签规则来源编号 | `$.data.poi_info.poi_normal_tags[].rule_id` |
| 门店 | `store_tag_texts_json` | 门店标签分组文字 | `$.data.poi_info.poi_tags[].sub_tags[].text` |
| 门店 | `store_tag_rule_ids_json` | 门店标签分组规则来源编号 | `$.data.poi_info.poi_tags[].rule_id` |

数字字符串和各状态的规则沿用前文。具体排除项及待审查路径见[逐路径处置表](reports/P31-additional-fields-disposition.json)，其路径数不等于业务字段数。


## v3 分享文案与来源空值

当时 v3 结果：`p31_remaining_fields_6a1836dbe7f44ec3bbf861b7d16bd273`，同一窗口 19 输出根。上一版所有行及字段保留。新增字段如下，每项另带 `_state`。分享渠道码仅按原索引记录，不猜渠道名称；价格渲染状态不代表库存或售罄。

| 表 | CSV 字段 | 说明 | 来源路径 |
| --- | --- | --- | --- |
| 商品/SKU | `product_render_price_status_code` | 商品价格渲染状态来源码（不代表SKU库存状态） | `$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.status` |
| 门店 | `store_share_activity_id_number` | 门店分享活动来源编号 | `$.data.poi_info.share_tip.activity_id` |
| 门店 | `store_share_channel_codes_json` | 门店分享渠道来源码，保留数组索引 | `$.data.poi_info.share_tip.channels[]` |
| 门店 | `store_share_description_text` | 门店分享说明文字 | `$.data.poi_info.share_tip.description` |
| 门店 | `store_share_title_text` | 门店分享标题 | `$.data.poi_info.share_tip.share_info.title` |
| 门店 | `store_share_content_text` | 门店分享内容文字 | `$.data.poi_info.share_tip.share_info.content` |
| 门店 | `store_share_recommendation_text` | 门店分享推荐标签文字 | `$.data.poi_info.share_tip.share_info.share_recommend.label_text` |
| 门店 | `store_dine_in_restaurant_label_null` | 堂食标签来源空值（非空结构尚未适配） | `$.data.poi_info.dine_in_restaurant_label` |
| 门店 | `store_no_dine_in_restaurant_label_null` | 非堂食标签来源空值（非空结构尚未适配） | `$.data.poi_info.no_dine_in_restaurant_label` |
| 门店 | `store_label_info_null` | 门店label_info来源空值（非空结构尚未适配） | `$.data.poi_info.label_info` |
| 门店 | `store_platform_promotion_info_null` | 门店平台活动来源空值（非空结构尚未适配） | `$.data.poi_info.platform_promotion_info` |
| 门店 | `store_regular_promotion_info_null` | 门店常规活动来源空值（非空结构尚未适配） | `$.data.poi_info.regular_promotion_info` |
| 门店 | `store_worry_free_info_null` | 门店worry_free_info来源空值（非空结构尚未适配） | `$.data.poi_info.worry_free_info` |

六个 `null-only` 字段的值固定为空，必须结合状态阅读：SOURCE_NULL 是来源明确 null，NOT_OBSERVED 是未观察到；不解释成“没有该活动”或“店铺不支持”。将来出现非空结构会固定报错，需单独适配，不任意透传。

券引用的账号关联用途尚未确认，个人领券/会员资格、分享链接及图片不在本轮导出。历史[局部分支处置表](reports/P31-remaining-fields-disposition.json)区分这些原因；该表只覆盖商品/SKU/poi_info 分支，不能据此宣称平台所有业务字段齐全。

## 分类和根级公开说明

`public_texts` 采用一行一项文字，`field_label_zh` 可直接展示中文用途；`field` 是稳定代号。`value` 配合 `state` 区分未观测、来源 null 和空字符串。`category_index` / `entry_index` 保留原数组索引，根级说明的分类编号/索引为空。`source_path` 与 `endpoint_id`、`source_request_ref`、`observed_at` 表明文字自己的来源。每种代号的路径、用途和对象也列在字典的 `public_text_definitions` 中。

| 对象 | 说明项 | 当前行数 |
| --- | --- | --- |
| FOOD 根级 | 运营说明、运营标签、适量点餐、配送和自取页签 | 7 |
| 初始 PRODUCTLIST 分类 | 活动说明、活动标签、分类说明、展开提示、标签说明 | 95 |
| 初始 PRODUCTLIST 根级 | 必选分类 tips、toast | 2 |

配送/自取文字是页签标签，不能作为用户选择、配送费或个人资格。分类说明不重复拼进商品行；即使后来分类响应更新商品价格，这些说明仍明确来自初始观察。全部 672 个来源组/路径的当前处置见[全路径表](reports/P31-context-codes-path-review.json)，业务含义待审项继续保留。

## 初始行最低价关系和计量文字角色

最新包将 55 行 `CHECKED_INITIAL_PAIR` 的两个旧 `NOT_REPARSED_ON_INITIAL_PAIR` 占位状态替换为实际结果，列名不变：

- `numeric_min_relation=EQUAL_PRODUCT_RENDER_AND_MIN_SKU`：该商品最低价、展示最低价和同一来源/分类/商品中的最小 SKU 价格数字相等。不是每个 SKU 价格都相同，也不证明金额单位。
- `product_unit_role=PRODUCT_MEASURE_TEXT_NOT_AMOUNT_UNIT`：按既有规则保留商品 unit 路径中的非空、非闭合货币标记文字；不是金额单位证明，不猜“份/件”等文字对应的具体数量。

源文字、价格、币种和单位依据均保留，分类行没有借用初始行结果。商品 JSON 为 v4，包 manifest 为 v5；其它表版本不变。若按列名导入，CSV 列结构与上包完全相同。[独立核对](reports/P31-initial-relation-direct-check.json)。

## 公开来源码与能力标记

新增 `public_codes` 为一行一项来源值，共 96 行。18 个来源组/路径条目的中文用途及完整路径列在 `field_dictionary.json` 的 `public_code_definitions` 中；其中 FOOD 和 PRODUCTLIST 的热销标记分开记录。用 `field`、`scope`、`category_ref`、`category_index`、`entry_index` 识别对象，用端点/请求引用/观察时间识别来源。

`value_type` 必须与 `value` 一起使用：`integer` 为十进制字符串，`boolean` 为布尔值（CSV 写 `true/false`），`text` 为文字/引用。不要按通用数字列读整列 value。空单元格结合 `state` 判断；保留负数不代表知道其含义。

`support_preorder_flag`、`support_cake_upgrade_flag` 等只是该观察中的来源标记，不是对所有用户、所有时间或当前订单的服务保证。`category_health_tag_flag` 不代表健康认证；类型码不解码，顺序数字不当作销量排名，引用不默认建立外键。

类型字典式 TYPE_*、计价配置和 selected 选择状态共 6 项未进入业务表，原因与未知见[完整处置](reports/P31-context-codes-path-review.json)。原三张表六个文件与上一包字节一致；[本轮核对](reports/P31-context-codes-direct-check.json)。

## 六类需求复核边界

最新包可交付已有公开字段，但不代表全部业务需求齐备。门店、商品、规格、价格、优惠、配送共 27 组的已交付内容和缺口见[六类复核](reports/P31-six-group-acceptance-review.md)。图片已按用户要求排除，不是交付缺口；当前价格/费用的人民币元单位已确认，券信息公共/个人用途、状态码和地址相关配送条件仍有缺证。字段列数包含元数据和状态列，不是业务字段数量。本轮复核没有改动业务文件，不要求用户做目标系统导入验证。

## 人民币／元的用户确认（当前口径）

用户已明确确认当前展示的价格和费用数字均为人民币元。商品表 233 行的 `currency=CNY`、`amount_unit=YUAN`；原初始 55 行的页面依据保留，分类 178 行使用 `USER_CONFIRMED_FOR_CURRENT_RESULT` 状态及 `EXPLICIT_USER_CONFIRMATION_CNY_YUAN` 依据。门店费用同样采用用户确认。金额数字保持原样，无元/分换算。

商品新增 `prior_currency_status`、`prior_amount_unit_status` 保留确认前状态；商品和门店的 `amount_confirmation_ref` 指向本次确认。JSON、字典和覆盖清单中的 `user_amount_confirmation` 绑定旧结果及窗口，`confirmed_amount_fields` 列明适用的 14 项金额字段。这些列的字典单位为 `USER_CONFIRMED_CNY_YUAN`；折扣、数量、时间及含义不明代码不套用元单位。

商品 CSV 为 179 列、门店 CSV 为 147 列，原列顺序保留，新证据列追加。公开说明和来源码 CSV 不变。旧版“178 行单位未确认”描述仍是当时事实，当前已由用户证据补齐，不再作为本份结果的待确认项；接口没有返回单位这一事实仍保留，不混淆来源证据与用户确认。优惠适用条件、配送范围等不因此自动确认。详见[本次确认与核对](reports/P31-confirmed-units-implementation.md)。


2026-10-12 恢复原计划工作：用户报告重启微信后恢复，故障根因仍 UNKNOWN。窗口20保持关闭，未开启新采集。中断前15份分类投影及初始观察已核对并独占导出220行、144商品、189 SKU、19分类；四表CSV/JSON、字段字典、状态清单及manifest核对通过。当前缺12个声明关系：第12类折叠3、第13类折叠4、第19类有序5；旧窗口有这些历史记录，但不跨窗补成当前记录。新旧无新增商品/SKU，215个共有键价格数值一致；第2类声明关系新增/移出各3个，形成5个新分类商品SKU键。旧233行人民币元交付保留。当前等待用户补充验证前是否到第19类末尾及终止提示，不要求重做页面操作。证据：docs/harness/reports/P31-window20-fields-direct-check.json、docs/harness/reports/P29-window20-membership-change-review.json。
