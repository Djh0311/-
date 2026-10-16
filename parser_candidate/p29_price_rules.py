"""Whitelist price-rule evidence from one category-render public analysis.

Numbers, quantity conditions, ladder fees and discount texts stay on the
response object that carried them. Field names, zero and negative values do
not establish a threshold, an algorithm, a free amount, a currency or a unit.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math

from parser_candidate.p29_category_price import (
    CLOSED_MARK_NOT_PROMOTED, NEGATIVE_NOT_ADAPTED, PRESENT_UNCONFIRMED, _text_state,
)
from parser_candidate.p29_category_profile import (
    CategoryCandidateError, _identifier, _number, _text, parse_category_public_values,
)

FAMILY = 'meituan_wechat_miniprogram'
VERSION = 'p29-observed-price-rules-v1'
PROFILE_KIND = 'LOCAL_OBSERVED_PRICE_RULE_EVIDENCE'
SOURCE_NULL = 'SOURCE_NULL'
PRESENT_TEXT_UNCONFIRMED = 'PRESENT_TEXT_SEMANTICS_UNCONFIRMED'
PRESENT_INDEXED_GROUP = 'PRESENT_INDEXED_GROUP'
BOTH_KEYS_PRESENT = 'BOTH_KEYS_PRESENT'
COUNT_KEY_NOT_OBSERVED = 'COUNT_KEY_NOT_OBSERVED'
DISCOUNT_KEY_NOT_OBSERVED = 'DISCOUNT_KEY_NOT_OBSERVED'
BOTH_KEYS_NOT_OBSERVED = 'BOTH_KEYS_NOT_OBSERVED'
FOOD_NUM_KEY_NOT_OBSERVED = 'FOOD_NUM_KEY_NOT_OBSERVED'
PRICE_KEY_NOT_OBSERVED = 'PRICE_KEY_NOT_OBSERVED'
PARSED_RULE_PATHS = (
    '$.data.food_spu_tags[].dynamic_spus[].activity_policy.discount_by_count.count',
    '$.data.food_spu_tags[].dynamic_spus[].activity_policy.discount_by_count.discount',
    '$.data.food_spu_tags[].dynamic_spus[].max_discount',
    '$.data.food_spu_tags[].dynamic_spus[].preferential_feeling_price',
    '$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.coupon_count',
    '$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.coupons_per_price',
    '$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.multi_activity_price',
    '$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.show_origin_price',
    '$.data.food_spu_tags[].dynamic_spus[].render_info.sup_info.discountTag',
    '$.data.food_spu_tags[].dynamic_spus[].skus[].activity_policy.discount_by_count.count',
    '$.data.food_spu_tags[].dynamic_spus[].skus[].activity_policy.discount_by_count.discount',
    '$.data.food_spu_tags[].dynamic_spus[].skus[].full_discount_tag[].sub_tags[].text',
    '$.data.food_spu_tags[].dynamic_spus[].skus[].sku_ladder_box_info.ladder_package_food_num',
    '$.data.food_spu_tags[].dynamic_spus[].skus[].sku_ladder_box_info.ladder_package_price',
)
UNKNOWN_FACTS = (
    'MERCHANT_NAME_IN_RESPONSE', 'CATEGORY_NAME_IN_RESPONSE', 'CURRENCY_CODE', 'AMOUNT_UNIT',
    'BUSINESS_SEMANTICS_OF_UNCONFIRMED_PRICE_COMPONENTS',
    'BUSINESS_SEMANTICS_OF_DISCOUNT_BY_COUNT', 'BUSINESS_SEMANTICS_OF_MAX_DISCOUNT',
    'BUSINESS_SEMANTICS_OF_PREFERENTIAL_FEELING_PRICE', 'BUSINESS_SEMANTICS_OF_COUPON_COUNT',
    'BUSINESS_SEMANTICS_OF_COUPONS_PER_PRICE', 'BUSINESS_SEMANTICS_OF_MULTI_ACTIVITY_PRICE',
    'BUSINESS_SEMANTICS_OF_SHOW_ORIGIN_PRICE', 'BUSINESS_SEMANTICS_OF_DISCOUNT_TAG_TEXT',
    'BUSINESS_SEMANTICS_OF_SKU_FULL_DISCOUNT_TAG_TEXT', 'BUSINESS_SEMANTICS_OF_LADDER_PACKAGE_FEE',
    'CATEGORY_TERMINATION', 'TAG_TYPE_SEMANTICS', 'CHILD_TAG_SEMANTICS',
)
_ABSENT_NUMBER = (None, 'NOT_OBSERVED')
_COUNT = ('activity_policy', 'discount_by_count', 'count')
_DISCOUNT = ('activity_policy', 'discount_by_count', 'discount')
_SPECS = {
    PARSED_RULE_PATHS[0]: ('product_pair', 'count', _COUNT),
    PARSED_RULE_PATHS[1]: ('product_pair', 'discount', _DISCOUNT),
    PARSED_RULE_PATHS[2]: ('product_number', 'max_discount', ('max_discount',)),
    PARSED_RULE_PATHS[3]: ('product_number', 'preferential_feeling_price', ('preferential_feeling_price',)),
    PARSED_RULE_PATHS[4]: ('product_number', 'coupon_count', ('render_info', 'price_info', 'coupon_count')),
    PARSED_RULE_PATHS[5]: ('product_number', 'coupons_per_price', ('render_info', 'price_info', 'coupons_per_price')),
    PARSED_RULE_PATHS[6]: ('product_number', 'multi_activity_price', ('render_info', 'price_info', 'multi_activity_price')),
    PARSED_RULE_PATHS[7]: ('product_number', 'show_origin_price', ('render_info', 'price_info', 'show_origin_price')),
    PARSED_RULE_PATHS[8]: ('product_text', 'discount_tag', ('render_info', 'sup_info', 'discountTag')),
    PARSED_RULE_PATHS[9]: ('sku_pair', 'count', ('skus', None, *_COUNT)),
    PARSED_RULE_PATHS[10]: ('sku_pair', 'discount', ('skus', None, *_DISCOUNT)),
    PARSED_RULE_PATHS[11]: ('sku_text', 'text', ('skus', None, 'full_discount_tag', None, 'sub_tags', None, 'text')),
    PARSED_RULE_PATHS[12]: ('sku_ladder', 'food_num', ('skus', None, 'sku_ladder_box_info', 'ladder_package_food_num')),
    PARSED_RULE_PATHS[13]: ('sku_ladder', 'price', ('skus', None, 'sku_ladder_box_info', 'ladder_package_price')),
}
RULE_EXPORT_FIELDS = (
    'product_discount_by_count_scope',
    'product_discount_by_count_count_number', 'product_discount_by_count_count_state',
    'product_discount_by_count_discount_number', 'product_discount_by_count_discount_state',
    'product_discount_by_count_pair_state',
    'sku_discount_by_count_scope',
    'sku_discount_by_count_count_number', 'sku_discount_by_count_count_state',
    'sku_discount_by_count_discount_number', 'sku_discount_by_count_discount_state',
    'sku_discount_by_count_pair_state',
    'product_max_discount_number', 'product_max_discount_state',
    'product_preferential_feeling_price_number', 'product_preferential_feeling_price_state',
    'product_coupon_count_number', 'product_coupon_count_state',
    'product_coupons_per_price_number', 'product_coupons_per_price_state',
    'product_multi_activity_price_number', 'product_multi_activity_price_state',
    'product_show_origin_price_number', 'product_show_origin_price_state',
    'product_discount_tag_text', 'product_discount_tag_text_state',
    'sku_ladder_package_food_num_number', 'sku_ladder_package_food_num_state',
    'sku_ladder_package_price_number', 'sku_ladder_package_price_state',
    'sku_ladder_package_pair_state',
    'sku_full_discount_tag_texts_json', 'sku_full_discount_tag_texts_state',
)


@dataclass(frozen=True)
class DiscountByCount:
    scope: str
    count_number: str | None
    count_state: str
    discount_number: str | None
    discount_state: str
    pair_state: str


@dataclass(frozen=True)
class LadderPackage:
    food_num_number: str | None
    food_num_state: str
    price_number: str | None
    price_state: str
    pair_state: str


@dataclass(frozen=True)
class IndexedRuleText:
    tag_index: int
    sub_tag_index: int
    text: str | None
    text_state: str


@dataclass(frozen=True)
class PriceRuleRow:
    category_ref: str
    product_id: str
    sku_id: str
    product_discount_by_count: DiscountByCount
    sku_discount_by_count: DiscountByCount
    product_max_discount_number: str | None
    product_max_discount_state: str
    product_preferential_feeling_price_number: str | None
    product_preferential_feeling_price_state: str
    product_coupon_count_number: str | None
    product_coupon_count_state: str
    product_coupons_per_price_number: str | None
    product_coupons_per_price_state: str
    product_multi_activity_price_number: str | None
    product_multi_activity_price_state: str
    product_show_origin_price_number: str | None
    product_show_origin_price_state: str
    product_discount_tag_text: str | None
    product_discount_tag_text_state: str
    sku_ladder_package: LadderPackage
    sku_full_discount_tag_texts: tuple
    sku_full_discount_tag_texts_state: str


@dataclass(frozen=True)
class PriceRuleParse:
    rows: tuple
    count_zero_means_no_threshold: bool
    discount_number_proves_algorithm: bool
    zero_amount_means_free: bool
    negative_adapted_as_amount: bool
    display_only_fields_passed_through: bool
    nested_rules_concatenated: bool


def _canonical(coordinates):
    if type(coordinates) is not list:
        raise CategoryCandidateError()
    rendered = '$'
    for item in coordinates:
        if type(item) is int:
            rendered += '[]'
        elif type(item) is str and item.isidentifier():
            rendered += '.' + item
        else:
            raise CategoryCandidateError()
    return rendered


def _locate(coordinates, pattern):
    if (type(coordinates) is not list or len(coordinates) != 5 + len(pattern)
            or tuple(coordinates[:2]) != ('data', 'food_spu_tags')
            or type(coordinates[2]) is not int or not 0 <= coordinates[2] < 256
            or coordinates[3] != 'dynamic_spus' or type(coordinates[4]) is not int
            or not 0 <= coordinates[4] < 8000):
        raise CategoryCandidateError()
    indexes = []
    for got, expected in zip(coordinates[5:], pattern):
        if expected is None:
            if type(got) is not int or not 0 <= got < 8000:
                raise CategoryCandidateError()
            indexes.append(got)
        elif got != expected:
            raise CategoryCandidateError()
    return coordinates[2], coordinates[4], tuple(indexes)


def _number_fact(value):
    if value is None:
        return None, SOURCE_NULL
    if type(value) in (int, float) and math.isfinite(value) and value < 0:
        return None, NEGATIVE_NOT_ADAPTED
    return _number(value), PRESENT_UNCONFIRMED


def _text_fact(value):
    if value is None:
        return None, SOURCE_NULL
    text, state = _text_state(value)
    if state == 'PRESENT_TEXT_NOT_CURRENCY_OR_AMOUNT_UNIT':
        state = PRESENT_TEXT_UNCONFIRMED
    return text, state


def _stored_number(container, name):
    if name not in container:
        return _ABSENT_NUMBER
    return _number_fact(container[name])


def _pair(scope, raw, absent_name, other_name, absent_state, other_absent_state):
    count_number, count_state = _stored_number(raw, 'count')
    discount_number, discount_state = _stored_number(raw, 'discount')
    has_count, has_discount = 'count' in raw, 'discount' in raw
    if has_count and has_discount:
        pair_state = BOTH_KEYS_PRESENT
    elif has_discount:
        pair_state = absent_state
    elif has_count:
        pair_state = other_absent_state
    else:
        pair_state = BOTH_KEYS_NOT_OBSERVED
    return DiscountByCount(scope, count_number, count_state, discount_number, discount_state, pair_state)


def _ladder(raw):
    food_number, food_state = _stored_number(raw, 'food_num')
    price_number, price_state = _stored_number(raw, 'price')
    has_food, has_price = 'food_num' in raw, 'price' in raw
    if has_food and has_price:
        pair_state = BOTH_KEYS_PRESENT
    elif has_food:
        pair_state = PRICE_KEY_NOT_OBSERVED
    elif has_price:
        pair_state = FOOD_NUM_KEY_NOT_OBSERVED
    else:
        pair_state = BOTH_KEYS_NOT_OBSERVED
    return LadderPackage(food_number, food_state, price_number, price_state, pair_state)


def _blank_product():
    return {'pair': {}, 'numbers': {}, 'text': None, 'text_seen': False}


def _blank_sku():
    return {'pair': {}, 'ladder': {}, 'texts': []}


def indexed_text_records(row):
    """Explicit tag/sub_tag ownership. None means the group was not observed."""
    if row.sku_full_discount_tag_texts_state != PRESENT_INDEXED_GROUP:
        return None
    return [
        {'tag_index': item.tag_index, 'sub_tag_index': item.sub_tag_index,
         'text': item.text, 'text_state': item.text_state}
        for item in row.sku_full_discount_tag_texts
    ]


def columns_from_row(row):
    product, sku, ladder = row.product_discount_by_count, row.sku_discount_by_count, row.sku_ladder_package
    records = indexed_text_records(row)
    texts_json = None if records is None else json.dumps(
        records, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    return {
        'product_discount_by_count_scope': product.scope,
        'product_discount_by_count_count_number': product.count_number,
        'product_discount_by_count_count_state': product.count_state,
        'product_discount_by_count_discount_number': product.discount_number,
        'product_discount_by_count_discount_state': product.discount_state,
        'product_discount_by_count_pair_state': product.pair_state,
        'sku_discount_by_count_scope': sku.scope,
        'sku_discount_by_count_count_number': sku.count_number,
        'sku_discount_by_count_count_state': sku.count_state,
        'sku_discount_by_count_discount_number': sku.discount_number,
        'sku_discount_by_count_discount_state': sku.discount_state,
        'sku_discount_by_count_pair_state': sku.pair_state,
        'product_max_discount_number': row.product_max_discount_number,
        'product_max_discount_state': row.product_max_discount_state,
        'product_preferential_feeling_price_number': row.product_preferential_feeling_price_number,
        'product_preferential_feeling_price_state': row.product_preferential_feeling_price_state,
        'product_coupon_count_number': row.product_coupon_count_number,
        'product_coupon_count_state': row.product_coupon_count_state,
        'product_coupons_per_price_number': row.product_coupons_per_price_number,
        'product_coupons_per_price_state': row.product_coupons_per_price_state,
        'product_multi_activity_price_number': row.product_multi_activity_price_number,
        'product_multi_activity_price_state': row.product_multi_activity_price_state,
        'product_show_origin_price_number': row.product_show_origin_price_number,
        'product_show_origin_price_state': row.product_show_origin_price_state,
        'product_discount_tag_text': row.product_discount_tag_text,
        'product_discount_tag_text_state': row.product_discount_tag_text_state,
        'sku_ladder_package_food_num_number': ladder.food_num_number,
        'sku_ladder_package_food_num_state': ladder.food_num_state,
        'sku_ladder_package_price_number': ladder.price_number,
        'sku_ladder_package_price_state': ladder.price_state,
        'sku_ladder_package_pair_state': ladder.pair_state,
        'sku_full_discount_tag_texts_json': texts_json,
        'sku_full_discount_tag_texts_state': row.sku_full_discount_tag_texts_state,
    }


def parse_price_rules(analysis):
    """Parse one inventory. Callers must not pass another response's values."""
    core = parse_category_public_values(analysis)
    values = analysis.get('public_values') if type(analysis) is dict else None
    if type(values) is not list:
        raise CategoryCandidateError()
    tags, product_ids, sku_ids = {}, {}, {}
    products, skus, seen = {}, {}, set()
    try:
        for value in values:
            if type(value) is not dict:
                raise CategoryCandidateError()
            path, coordinates = value.get('path'), value.get('coordinates')
            if path == '$.data.food_spu_tags[].tag' and type(coordinates) is list and len(coordinates) == 4:
                tags[coordinates[2]] = value.get('value')
            elif path == '$.data.food_spu_tags[].dynamic_spus[].id' and type(coordinates) is list and len(coordinates) == 6:
                product_ids[(coordinates[2], coordinates[4])] = value.get('value')
            elif path == '$.data.food_spu_tags[].dynamic_spus[].skus[].id' and type(coordinates) is list and len(coordinates) == 8:
                sku_ids[(coordinates[2], coordinates[4], coordinates[6])] = value.get('value')
            spec = _SPECS.get(path)
            if spec is None:
                continue
            if _canonical(coordinates) != path or tuple(coordinates) in seen:
                raise CategoryCandidateError()
            seen.add(tuple(coordinates))
            kind, name, pattern = spec
            tag_index, product_index, indexes = _locate(coordinates, pattern)
            if kind.startswith('product'):
                bucket = products.setdefault((tag_index, product_index), _blank_product())
                if kind == 'product_pair':
                    bucket['pair'][name] = value.get('value')
                elif kind == 'product_number':
                    bucket['numbers'][name] = value.get('value')
                else:
                    bucket['text'] = value.get('value')
                    bucket['text_seen'] = True
            else:
                if not indexes:
                    raise CategoryCandidateError()
                sku_index = indexes[0]
                bucket = skus.setdefault((tag_index, product_index, sku_index), _blank_sku())
                if kind == 'sku_pair':
                    bucket['pair'][name] = value.get('value')
                elif kind == 'sku_ladder':
                    bucket['ladder'][name] = value.get('value')
                else:
                    if len(indexes) != 3:
                        raise CategoryCandidateError()
                    text, text_state = _text_fact(value.get('value'))
                    bucket['texts'].append(IndexedRuleText(indexes[1], indexes[2], text, text_state))
        located = {}
        for key, sku_id in sku_ids.items():
            identity = (_text(tags[key[0]]), _identifier(product_ids[key[:2]]), _identifier(sku_id))
            if identity in located:
                raise CategoryCandidateError()
            located[identity] = key
        for key in products:
            if key not in product_ids:
                raise CategoryCandidateError()
        for key in skus:
            if key not in sku_ids:
                raise CategoryCandidateError()
        rows = []
        for row in core:
            key = located[(row.category_ref, row.product_id, row.sku_id)]
            product = products.get(key[:2], _blank_product())
            sku = skus.get(key, _blank_sku())
            numbers = product['numbers']
            if product['text_seen']:
                tag_text, tag_state = _text_fact(product['text'])
            else:
                tag_text, tag_state = None, 'NOT_OBSERVED'
            texts = tuple(sorted(sku['texts'], key=lambda item: (item.tag_index, item.sub_tag_index)))
            max_number, max_state = _stored_number(numbers, 'max_discount')
            feeling_number, feeling_state = _stored_number(numbers, 'preferential_feeling_price')
            coupon_number, coupon_state = _stored_number(numbers, 'coupon_count')
            per_number, per_state = _stored_number(numbers, 'coupons_per_price')
            multi_number, multi_state = _stored_number(numbers, 'multi_activity_price')
            origin_number, origin_state = _stored_number(numbers, 'show_origin_price')
            rows.append(PriceRuleRow(
                row.category_ref, row.product_id, row.sku_id,
                _pair('PRODUCT', product['pair'], COUNT_KEY_NOT_OBSERVED, DISCOUNT_KEY_NOT_OBSERVED,
                      COUNT_KEY_NOT_OBSERVED, DISCOUNT_KEY_NOT_OBSERVED),
                _pair('SKU', sku['pair'], COUNT_KEY_NOT_OBSERVED, DISCOUNT_KEY_NOT_OBSERVED,
                      COUNT_KEY_NOT_OBSERVED, DISCOUNT_KEY_NOT_OBSERVED),
                max_number, max_state, feeling_number, feeling_state, coupon_number, coupon_state,
                per_number, per_state, multi_number, multi_state, origin_number, origin_state,
                tag_text, tag_state, _ladder(sku['ladder']), texts,
                PRESENT_INDEXED_GROUP if texts else 'NOT_OBSERVED'))
    except CategoryCandidateError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError):
        raise CategoryCandidateError() from None
    return PriceRuleParse(tuple(rows), False, False, False, False, False, False)
