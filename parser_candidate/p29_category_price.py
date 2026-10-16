"""Price evidence for one category-render public scalar inventory.

Numbers stay on the response object that carried them. Currency and amount
unit are reported only from a closed path-segment check; a missing path is
not provided, and a present path is not promoted to CNY or YUAN.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import math
import re

from parser_candidate.p29_category_profile import (
    CategoryCandidateError, _number, _text, parse_category_public_values,
)

FAMILY = 'meituan_wechat_miniprogram'
VERSION = 'p29-observed-category-price-v1'
PROFILE_KIND = 'LOCAL_OBSERVED_PRICE_EVIDENCE'
CURRENCY_NOT_PROVIDED = 'NOT_PROVIDED_IN_OBSERVED_PUBLIC_STRUCTURE'
PATH_PRESENT_NOT_ADAPTED = 'PRESENT_PATH_NOT_ADAPTED'
PRESENT_UNCONFIRMED = 'PRESENT_SEMANTICS_UNCONFIRMED'
NEGATIVE_NOT_ADAPTED = 'PRESENT_NEGATIVE_NUMBER_NOT_ADAPTED_AS_AMOUNT'
PRESENT_TEXT_NOT_CURRENCY = 'PRESENT_TEXT_NOT_CURRENCY_OR_AMOUNT_UNIT'
CLOSED_MARK_NOT_PROMOTED = 'CLOSED_MARK_NOT_PROMOTED_TO_CURRENCY_OR_AMOUNT_UNIT'
PRODUCT_MEASURE_NOT_AMOUNT_UNIT = 'PRODUCT_MEASURE_TEXT_NOT_AMOUNT_UNIT'
SKU_PRICE_SOURCE = 'SAME_RESPONSE_SKU_PRICE_SCALAR'
PRODUCT_MIN_SOURCE = 'SAME_RESPONSE_PRODUCT_MIN_PRICE_SCALAR'
RENDER_MIN_SOURCE = 'SAME_RESPONSE_RENDER_MIN_PRICE_SCALAR'
ACTIVITY_PRICE_PATH = '$.data.food_spu_tags[].dynamic_spus[].skus[].activity_price'
PRICE_DESC_TAG_PATH = '$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.price_desc_tag'
_CURRENCY_SEGMENTS = frozenset({'currency', 'cny', 'rmb', 'yuan'})
_AMOUNT_UNIT_SEGMENTS = frozenset({'amount_unit', 'price_unit', 'money_unit', 'fen'})
_CLOSED_MARKS = frozenset({
    'CNY', 'RMB', 'USD', 'JPY', 'EUR', 'YUAN', 'FEN', 'yuan', 'fen', '元', '分', '¥', '￥',
})
_SEGMENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_OPTIONAL = {
    '$.data.food_spu_tags[].dynamic_spus[].full_discount_price': ('product', 'full_discount'),
    '$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.origin_price': ('product', 'render_origin'),
    '$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.min_price_tail': ('product', 'tail'),
    '$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.price_desc': ('product', 'render_desc'),
    '$.data.food_spu_tags[].dynamic_spus[].skus[].member_price': ('sku', 'member'),
    '$.data.food_spu_tags[].dynamic_spus[].skus[].full_discount_price': ('sku', 'full_discount'),
    '$.data.food_spu_tags[].dynamic_spus[].skus[].box_price': ('sku', 'box'),
    '$.data.food_spu_tags[].dynamic_spus[].skus[].price_desc': ('sku', 'price_desc'),
}
_PRODUCT_LEAVES = {
    'full_discount_price': 'full_discount',
    'origin_price': 'render_origin',
    'min_price_tail': 'tail',
    'price_desc': 'render_desc',
}
_SKU_LEAVES = {
    'member_price': 'member', 'full_discount_price': 'full_discount',
    'box_price': 'box', 'price_desc': 'price_desc',
}
_TEXT_LEAVES = {'tail', 'render_desc', 'price_desc'}


@dataclass(frozen=True)
class CategoryPriceRow:
    category_ref: str
    product_id: str
    product_name: str
    sku_id: str
    product_min_price_number: str
    render_min_price_number: str
    sku_price_number: str
    product_unit: str | None
    sku_spec: str | None
    sku_description: str | None
    sku_origin_number: str | None
    currency_status: str
    amount_unit_status: str
    product_unit_role: str
    sku_price_source: str
    product_min_price_source: str
    render_min_price_source: str
    sku_origin_state: str
    numeric_min_relation: str
    numeric_relation_proves_currency: bool
    numeric_relation_proves_amount_unit: bool
    render_origin_number: str | None
    render_origin_state: str
    product_full_discount_price_number: str | None
    product_full_discount_price_state: str
    sku_member_price_number: str | None
    sku_member_price_state: str
    sku_full_discount_price_number: str | None
    sku_full_discount_price_state: str
    sku_box_price_number: str | None
    sku_box_price_state: str
    min_price_tail: str | None
    min_price_tail_state: str
    render_price_desc: str | None
    render_price_desc_state: str
    sku_price_desc: str | None
    sku_price_desc_state: str


@dataclass(frozen=True)
class CategoryPriceParse:
    rows: tuple
    currency_path_status: str
    amount_unit_path_status: str
    activity_price_path_status: str
    price_desc_tag_path_status: str


def _segments(path):
    return {segment.lower() for segment in _SEGMENT.findall(path)}


def _status(fields, present):
    return PATH_PRESENT_NOT_ADAPTED if any(present(row) for row in fields) else CURRENCY_NOT_PROVIDED


def _canonical(coordinates):
    if (type(coordinates) is not list or len(coordinates) not in (6, 8)
            or tuple(coordinates[:2]) != ('data', 'food_spu_tags')
            or type(coordinates[2]) is not int or not 0 <= coordinates[2] < 256
            or coordinates[3] != 'dynamic_spus' or type(coordinates[4]) is not int
            or not 0 <= coordinates[4] < 8000):
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


def _number_state(value):
    if value is None:
        return None, 'NOT_OBSERVED'
    if type(value) in (int, float) and math.isfinite(value) and value < 0:
        return None, NEGATIVE_NOT_ADAPTED
    return _number(value), PRESENT_UNCONFIRMED


def _text_state(value):
    if value is None:
        return None, 'NOT_OBSERVED'
    text = _text(value, empty=True)
    if text == '':
        return '', 'SOURCE_EMPTY'
    if text in _CLOSED_MARKS:
        return text, CLOSED_MARK_NOT_PROMOTED
    return text, PRESENT_TEXT_NOT_CURRENCY


def _unit_role(value):
    text, state = _text_state(value)
    if state == PRESENT_TEXT_NOT_CURRENCY:
        state = PRODUCT_MEASURE_NOT_AMOUNT_UNIT
    return text, state


def _take(container, name, numeric):
    if name not in container:
        return (None, 'NOT_OBSERVED')
    return (_number_state if numeric else _text_state)(container[name])


def parse_category_price(analysis):
    """Parse one inventory. Callers must not pass another response's values."""
    core = parse_category_public_values(analysis)
    fields = analysis.get('fields')
    values = analysis.get('public_values')
    if type(fields) is not list or type(values) is not list:
        raise CategoryCandidateError()
    currency_status = _status(fields, lambda row: type(row) is dict and type(row.get('path')) is str
                              and _segments(row['path']) & _CURRENCY_SEGMENTS)
    amount_status = _status(fields, lambda row: type(row) is dict and type(row.get('path')) is str
                            and _segments(row['path']) & _AMOUNT_UNIT_SEGMENTS)
    activity_status = _status(fields, lambda row: type(row) is dict and row.get('path') == ACTIVITY_PRICE_PATH)
    tag_status = _status(fields, lambda row: type(row) is dict and row.get('path') == PRICE_DESC_TAG_PATH)
    tags, product_ids, sku_ids = {}, {}, {}
    product_extra, sku_extra, seen = {}, {}, set()
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
            spec = _OPTIONAL.get(path)
            if spec is None:
                continue
            if _canonical(coordinates) != path or tuple(coordinates) in seen:
                raise CategoryCandidateError()
            seen.add(tuple(coordinates))
            kind, name = spec
            if kind == 'product':
                leaf = coordinates[5] if len(coordinates) == 6 else coordinates[7]
                if ((len(coordinates) == 6 and coordinates[5] != 'full_discount_price')
                        or (len(coordinates) == 8 and (coordinates[5:7] != ['render_info', 'price_info']
                            or _PRODUCT_LEAVES.get(leaf) != name))):
                    raise CategoryCandidateError()
                product_extra.setdefault((coordinates[2], coordinates[4]), {})[name] = value.get('value')
            else:
                if (len(coordinates) != 8 or coordinates[5] != 'skus' or type(coordinates[6]) is not int
                        or not 0 <= coordinates[6] < 8000 or _SKU_LEAVES.get(coordinates[7]) != name):
                    raise CategoryCandidateError()
                sku_extra.setdefault((coordinates[2], coordinates[4], coordinates[6]), {})[name] = value.get('value')
        located = {}
        for key, sku_id in sku_ids.items():
            category, product_id = tags.get(key[0]), product_ids.get(key[:2])
            identity = (str(category), str(product_id), str(sku_id))
            if identity in located:
                raise CategoryCandidateError()
            located[identity] = key
        relation = {}
        grouped = {}
        for row in core:
            grouped.setdefault((row.category_ref, row.product_id), []).append(row)
        for key, group in grouped.items():
            minimum = min(Decimal(row.sku_price_number) for row in group)
            equal = all(Decimal(row.product_min_price_number) == Decimal(row.render_min_price_number) == minimum
                        for row in group)
            relation[key] = 'EQUAL_PRODUCT_RENDER_AND_MIN_SKU' if equal else 'NOT_EQUAL'
        rows = []
        for row in core:
            key = located[(row.category_ref, row.product_id, row.sku_id)]
            product, sku = product_extra.get(key[:2], {}), sku_extra.get(key, {})
            render_origin, render_origin_state = _take(product, 'render_origin', True)
            product_discount, product_discount_state = _take(product, 'full_discount', True)
            tail, tail_state = _take(product, 'tail', False)
            render_desc, render_desc_state = _take(product, 'render_desc', False)
            member, member_state = _take(sku, 'member', True)
            sku_discount, sku_discount_state = _take(sku, 'full_discount', True)
            box, box_state = _take(sku, 'box', True)
            price_desc, price_desc_state = _take(sku, 'price_desc', False)
            _, unit_role = _unit_role(row.product_unit)
            origin_state = 'NOT_OBSERVED' if row.sku_origin_number is None else PRESENT_UNCONFIRMED
            rows.append(CategoryPriceRow(
                row.category_ref, row.product_id, row.product_name, row.sku_id,
                row.product_min_price_number, row.render_min_price_number, row.sku_price_number,
                row.product_unit, row.sku_spec, row.sku_description, row.sku_origin_number,
                currency_status, amount_status, unit_role, SKU_PRICE_SOURCE, PRODUCT_MIN_SOURCE,
                RENDER_MIN_SOURCE, origin_state, relation[(row.category_ref, row.product_id)],
                False, False, render_origin, render_origin_state, product_discount,
                product_discount_state, member, member_state, sku_discount, sku_discount_state,
                box, box_state, tail, tail_state, render_desc, render_desc_state,
                price_desc, price_desc_state))
    except CategoryCandidateError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError):
        raise CategoryCandidateError() from None
    return CategoryPriceParse(tuple(rows), currency_status, amount_status, activity_status, tag_status)
