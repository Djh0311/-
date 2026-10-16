"""Remaining public display fields; no personal coupon qualification."""

from . import p31_additional_fields as previous
from .p29_category_profile import CategoryCandidateError

base = previous.base
PRODUCT_PREFIX = previous.PRODUCT_PREFIX
SKU_PREFIX = previous.SKU_PREFIX
STORE_PREFIX = previous.STORE_PREFIX
PRODUCT_SPECS = (
    ('product_render_price_status_code', ('render_info', 'price_info', 'status'), 'integer',
     '商品价格渲染状态来源码（不代表SKU库存状态）'),
)
SKU_SPECS = ()
STORE_SPECS = (
    ('store_share_activity_id_number', ('share_tip', 'activity_id'), 'integer', '门店分享活动来源编号'),
    ('store_share_channel_codes', ('share_tip', 'channels', None), 'integer', '门店分享渠道来源码，保留数组索引'),
    ('store_share_description_text', ('share_tip', 'description'), 'text', '门店分享说明文字'),
    ('store_share_title_text', ('share_tip', 'share_info', 'title'), 'text', '门店分享标题'),
    ('store_share_content_text', ('share_tip', 'share_info', 'content'), 'text', '门店分享内容文字'),
    ('store_share_recommendation_text', ('share_tip', 'share_info', 'share_recommend', 'label_text'), 'text', '门店分享推荐标签文字'),
    ('store_dine_in_restaurant_label_null', ('dine_in_restaurant_label',), 'null-only', '堂食标签来源空值（非空结构尚未适配）'),
    ('store_no_dine_in_restaurant_label_null', ('no_dine_in_restaurant_label',), 'null-only', '非堂食标签来源空值（非空结构尚未适配）'),
    ('store_label_info_null', ('label_info',), 'null-only', '门店label_info来源空值（非空结构尚未适配）'),
    ('store_platform_promotion_info_null', ('platform_promotion_info',), 'null-only', '门店平台活动来源空值（非空结构尚未适配）'),
    ('store_regular_promotion_info_null', ('regular_promotion_info',), 'null-only', '门店常规活动来源空值（非空结构尚未适配）'),
    ('store_worry_free_info_null', ('worry_free_info',), 'null-only', '门店worry_free_info来源空值（非空结构尚未适配）'),
)


def parse_product_fields(analysis):
    return previous._parse_product_fields(analysis, PRODUCT_SPECS, SKU_SPECS)


def parse_store_fields(analysis):
    selected = base._select(analysis, previous._patterns(((STORE_PREFIX, STORE_SPECS),)))
    null_paths = {base._canonical(STORE_PREFIX + path) for _, path, kind, _ in STORE_SPECS if kind == 'null-only'}
    # A new non-null structure must not silently become NOT_OBSERVED.
    metadata = analysis.get('fields')
    if type(metadata) is not list or len(metadata) > 8000:
        base._fail()
    for item in metadata:
        if type(item) is not dict or type(item.get('path')) is not str:
            base._fail()
        path = item['path']
        if any(path == root or path.startswith(root + '.') or path.startswith(root + '[') for root in null_paths):
            if path not in null_paths or item.get('type') != 'null':
                raise CategoryCandidateError('P31_SOURCE_STRUCTURE_NOT_ADAPTED')
    for item in analysis['public_values']:
        path = item['path']
        if any(path == root or path.startswith(root + '.') or path.startswith(root + '[') for root in null_paths):
            if path not in null_paths or item['value'] is not None:
                raise CategoryCandidateError('P31_SOURCE_STRUCTURE_NOT_ADAPTED')
    return previous._fields(selected, STORE_PREFIX, STORE_SPECS)
