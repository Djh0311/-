"""Additional bounded public observations, never interpreted stock or timestamps.

Each indexed field preserves its own array coordinates. Related label fields can
be joined only within the same row, label family and index tuple.
"""

import json

from . import p31_public_fields as base

# (output field, relative source path, scalar type, Chinese description).
PRODUCT_SPECS = (
    ('product_activity_tag_id_text', ('activity_tag_id',), 'text', '活动标签来源编号'),
    ('product_ctime_number', ('ctime',), 'integer', 'ctime来源数字（不转换时间或猜单位）'),
    ('product_group_id_number', ('group_id',), 'integer', '分组来源编号'),
    ('product_spu_category_code', ('spu_category',), 'integer', 'spu_category来源分类码'),
    ('product_spu_type_code', ('spu_type',), 'integer', 'spu_type来源类型码'),
    ('product_tag_text', ('tag',), 'text', '商品自身tag文字（不替代外层分类）'),
    ('product_is_premium_spu_flag', ('isPremiumSpu',), 'boolean', 'isPremiumSpu来源标记'),
    ('product_need_attr_accessory_flag', ('need_attr_accessory_product',), 'boolean', '属性附属商品来源标记'),
    ('product_topping_flag', ('topping_product',), 'boolean', 'topping_product来源标记'),
    ('product_button_text', ('render_info', 'btn_info', 'text'), 'text', '商品按钮文案'),
    ('product_image_label_text', ('render_info', 'img_area', 'label_text'), 'text', '商品图片区域标签文字'),
    ('product_rule_tag_text', ('render_info', 'sup_info', 'ruleTag'), 'text', '商品规则标签文字'),
)
SKU_SPECS = (
    ('sku_activity_stock_number', ('activity_stock',), 'integer', '活动库存来源数字（哨兵含义未确认）'),
    ('sku_activity_tag_text', ('activity_tag',), 'text', 'SKU活动标签文字'),
    ('sku_activity_tag_id_text', ('activity_tag_id',), 'text', 'SKU活动标签来源编号'),
    ('sku_activity_type_code', ('activity_type',), 'integer', 'SKU活动来源类型码'),
    ('sku_promotion_activity_text', ('promotion', 'activity_text'), 'text', 'SKU促销活动文案'),
    ('sku_promotion_activity_type_code', ('promotion', 'activity_type'), 'integer', 'SKU促销活动来源类型码'),
    ('sku_promotion_entry_item_id_number', ('promotion', 'entry_item_id'), 'integer', 'SKU促销入口来源编号'),
    ('sku_promotion_tag_texts', ('promotion_tag', None, 'sub_tags', None, 'text'), 'text', 'SKU促销标签文字，保留两层索引'),
    ('sku_promotion_tag_rule_ids', ('promotion_tag', None, 'rule_id'), 'integer', 'SKU促销标签规则编号，保留标签索引'),
    ('sku_full_discount_tag_rule_ids', ('full_discount_tag', None, 'rule_id'), 'integer', 'SKU优惠标签规则编号，按已有优惠文字标签索引关联'),
)
STORE_SPECS = (
    ('store_numeric_id_number', ('id',), 'integer', '门店数值编号（不替代字符串门店编号）'),
    ('store_buy_sku_count_threshold_number', ('buy_sku_count_threshold',), 'integer', '门店购买SKU数量阈值来源数字（条件未确认）'),
    ('store_has_poi_env_flag', ('has_poi_env',), 'boolean', '门店has_poi_env来源标记'),
    ('store_has_xbk_flag', ('has_xbk',), 'boolean', '门店has_xbk来源标记'),
    ('store_restrict_toast_text', ('restrict_toast',), 'text', '门店限制提示来源文字'),
    ('store_speed_refund_status_code', ('speed_refund_status',), 'integer', '门店快速退款来源状态码（不推断服务承诺）'),
    ('store_support_pay_code', ('support_pay',), 'integer', '门店支付支持来源码（不推断支付方式）'),
    ('store_brand_id_number', ('brand_id',), 'integer', '门店品牌来源编号'),
    ('store_origin_brand_id_number', ('origin_brand_id',), 'integer', '门店原品牌来源编号'),
    ('store_buz_code_number', ('buz_code',), 'integer', '门店buz_code来源数字'),
    ('store_buz_type_code', ('buz_type',), 'integer', '门店buz_type来源类型码'),
    ('store_shop_business_type_text', ('shop_business_type',), 'text', '门店业务类型来源文字'),
    ('store_poi_sp_type_code', ('poi_sp_type',), 'integer', '门店poi_sp_type来源类型码'),
    ('store_buz_menu_tip_text', ('buz_menu_tip',), 'text', '门店业务菜单说明'),
    ('store_attention_count_text', ('attention_count_text',), 'text', '门店关注数量展示文字（不解析成精确数量）'),
    ('store_per_cust_trans_text', ('per_cust_trans',), 'text', '门店per_cust_trans来源文字（单位含义未确认）'),
    ('store_impress_title_text', ('poi_impress', 'title'), 'text', '门店印象标题'),
    ('store_service_title_text', ('poi_service_label', 'title'), 'text', '门店服务标题'),
    ('store_impress_texts', ('poi_impress', 'impress_label', None, 'label_text'), 'text', '门店印象标签文字'),
    ('store_impress_descriptions', ('poi_impress', 'impress_label', None, 'label_desc_text'), 'text', '门店印象标签说明'),
    ('store_label_texts', ('poi_label', 'labels', None, 'label_text'), 'text', '门店标签文字'),
    ('store_label_descriptions', ('poi_label', 'labels', None, 'label_desc_text'), 'text', '门店标签说明'),
    ('store_new_label_texts', ('poi_label_new', 'labels', None, 'label_text'), 'text', '门店新版标签文字'),
    ('store_new_label_descriptions', ('poi_label_new', 'labels', None, 'label_desc_text'), 'text', '门店新版标签说明'),
    ('store_service_texts', ('poi_service_label', 'service_label', None, 'label_text'), 'text', '门店服务标签文字'),
    ('store_service_descriptions', ('poi_service_label', 'service_label', None, 'label_desc_text'), 'text', '门店服务标签说明'),
    ('store_normal_tag_texts', ('poi_normal_tags', None, 'sub_tags', None, 'text'), 'text', '门店普通标签文字'),
    ('store_normal_tag_rule_ids', ('poi_normal_tags', None, 'rule_id'), 'integer', '门店普通标签规则来源编号'),
    ('store_tag_texts', ('poi_tags', None, 'sub_tags', None, 'text'), 'text', '门店标签分组文字'),
    ('store_tag_rule_ids', ('poi_tags', None, 'rule_id'), 'integer', '门店标签分组规则来源编号'),
)
PRODUCT_PREFIX = ('data', 'food_spu_tags', None, 'dynamic_spus', None)
SKU_PREFIX = PRODUCT_PREFIX + ('skus', None)
STORE_PREFIX = ('data', 'poi_info')


def _patterns(groups):
    return {base._canonical(prefix + path): prefix + path
            for prefix, specs in groups for _, path, _, _ in specs}


def _fields(selected, prefix, specs):
    result = {}
    for field, path, kind, _ in specs:
        if None not in path:
            value, state = base._fact(selected.get(prefix + path, base._MISSING), kind)
        else:
            pattern = prefix + path
            items = []
            for coord, raw in selected.items():
                if len(coord) != len(pattern) or any(p is not None and p != c for p, c in zip(pattern, coord)):
                    continue
                value, state = base._fact(raw, kind)
                items.append({'indices': [c for p, c in zip(path, coord[len(prefix):]) if p is None],
                              'value': value, 'state': state})
            if len(items) > 256:
                base._fail()
            items.sort(key=lambda item: item['indices'])
            value, state = (items, 'PRESENT_UNCONFIRMED') if items else (None, 'NOT_OBSERVED')
            encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')) if items else None
            if encoded is not None and len(encoded.encode('ascii')) > 65536:
                base._fail()
            result[field + '_json'] = encoded
        result[field], result[field + '_state'] = value, state
    return result


def parse_product_fields(analysis):
    return _parse_product_fields(analysis, PRODUCT_SPECS, SKU_SPECS)


def _parse_product_fields(analysis, product_specs, sku_specs):
    # Validate the original identity and coordinates before adding fields.
    expected = base.parse_product_fields(analysis)
    selected = base._select(analysis, _patterns(((PRODUCT_PREFIX, product_specs), (SKU_PREFIX, sku_specs))))
    identity_patterns = (('data', 'food_spu_tags', None, 'tag'), PRODUCT_PREFIX + ('id',), SKU_PREFIX + ('id',))
    ids = base._select(analysis, {base._canonical(p): p for p in identity_patterns})
    owners = {}
    for coord, value in ids.items():
        if len(coord) == 8:
            identity = (ids[coord[:3] + ('tag',)], str(ids[coord[:5] + ('id',)]), str(value))
            owners[identity] = coord[:5], coord[:7]
    if set(owners) != set(expected):
        base._fail()
    products = {p for p, _ in owners.values()}
    skus = {s for _, s in owners.values()}
    for coord in selected:
        if coord[:5] not in products or coord[5] == 'skus' and coord[:7] not in skus:
            base._fail()
    cached = {p: _fields(selected, p, product_specs) for p in products}
    return {identity: {**cached[p], **_fields(selected, s, sku_specs)} for identity, (p, s) in owners.items()}


def parse_store_fields(analysis):
    return _fields(base._select(analysis, _patterns(((STORE_PREFIX, STORE_SPECS),))), STORE_PREFIX, STORE_SPECS)
