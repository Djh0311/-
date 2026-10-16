"""Explicit public observations, not inferred stock, status, or delivery rules."""

from decimal import Decimal
import json
import math

from .p29_category_profile import CategoryCandidateError, parse_category_public_values

PRODUCT_SPECS = (
    ('product_description_text', ('description',), 'text'),
    ('product_month_saled_number', ('month_saled',), 'integer'),
    ('product_status_code', ('status',), 'integer'),
    ('product_status_description_text', ('status_description',), 'text'),
    ('product_stock_number', ('stock',), 'integer'),
    ('product_has_food_flag', ('has_food',), 'boolean'),
    ('product_forbid_single_buy_text', ('forbid_single_buy',), 'text'),
    ('product_sku_label_text', ('sku_label',), 'text'),
    ('product_activity_tag_text', ('activity_tag',), 'text'),
    ('product_activity_type_code', ('activity_type',), 'integer'),
    ('product_has_multi_sale_attr_flag', ('has_multi_sale_attr',), 'boolean'),
)
SKU_SPECS = (
    ('sku_public_description_text', ('description',), 'text'),
    ('sku_spec_info_text', ('spec_info',), 'text'),
    ('sku_min_order_count_number', ('min_order_count',), 'integer'),
    ('sku_stock_number', ('stock',), 'integer'),
    ('sku_real_stock_number', ('real_stock',), 'integer'),
    ('sku_status_code', ('status',), 'integer'),
    ('sku_restrict_number', ('restrict',), 'integer'),
    ('sku_count_number', ('count',), 'integer'),
    ('sku_box_num_number', ('box_num',), 'number'),
    ('sku_promotion_info_text', ('promotion_info',), 'text'),
    ('sku_promotion_text', ('promotion', 'promotion_text'), 'text'),
    ('sku_promotion_restrict_text', ('promotion', 'restrict_text'), 'text'),
    ('sku_promotion_addition_text', ('promotion', 'addition_text'), 'text'),
)
STORE_SPECS = (
    ('store_address_text', ('address',), 'text'),
    ('store_bulletin_text', ('bulletin',), 'text'),
    ('store_shipping_time_text', ('shipping_time',), 'text'),
    ('store_min_price_tip_text', ('min_price_tip',), 'text'),
    ('store_shipping_fee_tip_text', ('shipping_fee_tip',), 'text'),
    ('store_origin_shipping_fee_tip_text', ('origin_shipping_fee_tip',), 'text'),
    ('store_delivery_time_tip_text', ('delivery_time_tip',), 'text'),
    ('store_delivery_tips_text', ('delivery_tips',), 'text'),
    ('store_app_delivery_tip_text', ('app_delivery_tip',), 'text'),
    ('store_poi_prepare_time_text', ('poi_prepare_time',), 'text'),
    ('store_status_code', ('status',), 'integer'),
    ('store_poi_sell_status_code', ('poi_sell_status',), 'integer'),
    ('store_score_number', ('score',), 'number'),
    ('store_wm_poi_score_number', ('wm_poi_score',), 'number'),
    ('store_dp_score_number', ('dp_score',), 'number'),
    ('store_comment_number', ('comment_number',), 'integer'),
    ('store_dp_comment_number', ('dp_comment_number',), 'integer'),
    ('store_avg_delivery_time_number', ('avg_delivery_time',), 'integer'),
    ('store_min_price_number', ('min_price',), 'number'),
    ('store_shipping_fee_number', ('shipping_fee',), 'number'),
    ('store_shipping_reduce_fee_number', ('shippingReduceFee',), 'number'),
    ('store_delivery_type_code', ('delivery_type',), 'integer'),
    ('store_shipping_fee_type_code', ('shipping_fee_type',), 'integer'),
    ('store_invoice_support_code', ('invoice_support',), 'integer'),
    ('store_is_meituan_delivery_flag', ('is_meituan_delivery',), 'boolean'),
)
ATTR_SPECS = (('name', ('name',), 'text'), ('choose_n', ('choose_n',), 'integer'))
VALUE_SPECS = (
    ('id', ('id',), 'integer'), ('attr_id', ('attrId',), 'integer'),
    ('value', ('value',), 'text'), ('count', ('count',), 'integer'),
    ('hidden', ('hidden',), 'boolean'), ('mode', ('mode',), 'integer'),
    ('repeatable_choice', ('repeatable_choice',), 'boolean'),
    ('sequence', ('sequence',), 'integer'),
)
_PREFIX = ('data', 'food_spu_tags', None, 'dynamic_spus', None)
_SKU = _PREFIX + ('skus', None)
_MISSING = object()


def _fail():
    raise CategoryCandidateError('P31_FIELD_INPUT_INVALID')


def _canonical(pattern):
    return '$' + ''.join('[]' if x is None else '.' + x for x in pattern)


def _select(analysis, patterns):
    if (type(analysis) is not dict or analysis.get('raw_payload_persisted') is not False
            or analysis.get('sensitive_values_processed') is not False):
        _fail()
    values = analysis.get('public_values')
    if type(values) is not list or len(values) > 8000:
        _fail()
    selected = {}
    for item in values:
        if type(item) is not dict or set(item) != {'path', 'coordinates', 'value'}:
            _fail()
        if type(item['path']) is not str:
            _fail()
        pattern = patterns.get(item['path'])
        if pattern is None:
            continue
        coords = item['coordinates']
        if type(coords) is not list or len(coords) != len(pattern):
            _fail()
        for i, (part, expected) in enumerate(zip(coords, pattern)):
            if expected is None:
                limit = 256 if i == 2 else 8000
                if type(part) is not int or not 0 <= part < limit:
                    _fail()
            elif type(part) is not str or part != expected:
                _fail()
        key = tuple(coords)
        if key in selected:
            _fail()
        selected[key] = item['value']
    return selected


def _fact(value, kind):
    if value is _MISSING:
        return None, 'NOT_OBSERVED'
    if value is None:
        return None, 'SOURCE_NULL'
    if kind == 'text':
        if (type(value) is not str or len(value) > 256
                or any(c in value for c in ('\r', '\n', '\0')) or '://' in value):
            _fail()
        return value, 'SOURCE_EMPTY' if value == '' else 'PRESENT_UNCONFIRMED'
    if kind == 'boolean':
        if type(value) is not bool:
            _fail()
        return value, 'PRESENT_UNCONFIRMED'
    if (type(value) not in ((int,) if kind == 'integer' else (int, float))
            or type(value) is float and not math.isfinite(value)):
        _fail()
    number = format(Decimal(str(value)), 'f')
    if len(number) > 64:
        _fail()
    return number, 'NEGATIVE_SEMANTICS_UNCONFIRMED' if value < 0 else 'PRESENT_UNCONFIRMED'


def _columns(selected, prefix, specs):
    result = {}
    for field, relative, kind in specs:
        result[field], result[field + '_state'] = _fact(selected.get(prefix + relative, _MISSING), kind)
    return result


def _attributes(selected, product):
    prefix = product + ('attrs',)
    indices = sorted({coord[6] for coord in selected if coord[:6] == prefix})
    if len(indices) > 128:
        _fail()
    groups = []
    for index in indices:
        group_prefix = prefix + (index,)
        value_prefix = group_prefix + ('values',)
        value_indices = sorted({coord[8] for coord in selected if coord[:8] == value_prefix})
        if len(value_indices) > 256:
            _fail()
        group = {'attribute_index': index, **_columns(selected, group_prefix, ATTR_SPECS),
                 'values': [{'value_index': vi, **_columns(selected, value_prefix + (vi,), VALUE_SPECS)}
                            for vi in value_indices]}
        groups.append(group)
    encoded = json.dumps(groups, ensure_ascii=True, sort_keys=True, separators=(',', ':')) if groups else None
    if encoded is not None and len(encoded.encode('ascii')) > 65536:
        _fail()
    return {'product_attributes': groups or None, 'product_attributes_json': encoded,
            'product_attributes_state': 'PRESENT_UNCONFIRMED' if groups else 'NOT_OBSERVED'}


def parse_product_fields(analysis):
    core = parse_category_public_values(analysis)
    patterns = {_canonical(prefix + relative): prefix + relative
                for prefix, specs in ((_PREFIX, PRODUCT_SPECS), (_SKU, SKU_SPECS),
                    (_PREFIX + ('attrs', None), ATTR_SPECS),
                    (_PREFIX + ('attrs', None, 'values', None), VALUE_SPECS))
                for _, relative, _ in specs}
    selected = _select(analysis, patterns)
    identity_patterns = { _canonical(pattern): pattern for pattern in (
        ('data', 'food_spu_tags', None, 'tag'), _PREFIX + ('id',), _SKU + ('id',))}
    ids = _select(analysis, identity_patterns)
    identities, products, skus = {}, set(), set()
    for coord, value in ids.items():
        if len(coord) != 8:
            continue
        product, sku = coord[:5], coord[:7]
        identity = (ids[coord[:3] + ('tag',)], str(ids[product + ('id',)]), str(value))
        if identity in identities:
            _fail()
        identities[identity] = (product, sku)
        products.add(product)
        skus.add(sku)
    expected = {(r.category_ref, r.product_id, r.sku_id) for r in core}
    if set(identities) != expected:
        _fail()
    for coord in selected:
        if coord[:5] not in products or coord[5] == 'skus' and coord[:7] not in skus:
            _fail()
    result = {}
    product_fields = {prefix: {**_columns(selected, prefix, PRODUCT_SPECS), **_attributes(selected, prefix)}
                      for prefix in products}
    for identity, (product, sku) in identities.items():
        result[identity] = {**product_fields[product], **_columns(selected, sku, SKU_SPECS)}
    return result


def parse_store_fields(analysis):
    prefix = ('data', 'poi_info')
    patterns = {_canonical(prefix + relative): prefix + relative for _, relative, _ in STORE_SPECS}
    return _columns(_select(analysis, patterns), prefix, STORE_SPECS)
