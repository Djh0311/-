"""Candidate rows from one observed category-render scalar inventory.

This local rule version is not a platform version or a qualified Parser.
No merchant/category label, currency, amount unit or success code is invented.
The returned rows are inspection candidates, never complete result records.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import math

FAMILY = 'meituan_wechat_miniprogram'
VERSION = 'p29-observed-category-render-v1'
PREFIX = ('data', 'food_spu_tags')
PRODUCT = '$.data.food_spu_tags[].dynamic_spus[]'
PATHS = frozenset({'$.data.food_spu_tags[].tag'}
    | {PRODUCT + '.' + key for key in ('id', 'name', 'unit', 'min_price')}
    | {PRODUCT + '.skus[].' + key for key in ('id', 'price', 'spec', 'spec_desc', 'origin_price')}
    | {PRODUCT + '.render_info.price_info.min_price'})


class CategoryCandidateError(ValueError):
    def __init__(self, code='P29_CATEGORY_CANDIDATE_INVALID'):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CategoryCandidateRow:
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


def _text(value, *, empty=False):
    if (type(value) is not str or len(value) > 256 or not empty and not value
            or any(c in value for c in ('\r', '\n', '\0')) or '://' in value):
        raise CategoryCandidateError()
    return value


def _number(value):
    if (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
        raise CategoryCandidateError()
    result = format(Decimal(str(value)), 'f')
    if len(result) > 64:
        raise CategoryCandidateError()
    return result


def _identifier(value):
    if type(value) is not int or len(str(value)) > 64:
        raise CategoryCandidateError()
    return str(value)


def _optional_text(body, key):
    value = body.get(key)
    return None if value is None else _text(value, empty=True)


def parse_category_public_values(analysis):
    """One inventory only: no context argument or cross-observation fallback."""
    if (type(analysis) is not dict or analysis.get('raw_payload_persisted') is not False
            or analysis.get('sensitive_values_processed') is not False):
        raise CategoryCandidateError()
    values = analysis.get('public_values')
    if type(values) is not list or len(values) > 8000:
        raise CategoryCandidateError('P29_CATEGORY_CANDIDATE_BUDGET')
    selected, products = {}, {}
    try:
        for value in values:
            if type(value) is not dict or set(value) != {'path', 'coordinates', 'value'}:
                raise CategoryCandidateError()
            if value['path'] not in PATHS:
                continue
            coordinates = value['coordinates']
            if (type(coordinates) is not list or not 4 <= len(coordinates) <= 8
                    or tuple(coordinates[:2]) != PREFIX
                    or type(coordinates[2]) is not int or not 0 <= coordinates[2] < 256
                    or any(type(c) not in (str, int) for c in coordinates)):
                raise CategoryCandidateError()
            canonical = '$'
            for c in coordinates:
                canonical += '[]' if type(c) is int else '.' + c
            key = tuple(coordinates)
            if canonical != value['path'] or key in selected:
                raise CategoryCandidateError()
            selected[key] = value['value']
            if len(coordinates) >= 6:
                if (coordinates[3] != 'dynamic_spus' or type(coordinates[4]) is not int
                        or not 0 <= coordinates[4] < 8000):
                    raise CategoryCandidateError()
                if len(coordinates) == 8 and coordinates[5] == 'skus':
                    if type(coordinates[6]) is not int or not 0 <= coordinates[6] < 8000:
                        raise CategoryCandidateError()
                products.setdefault((coordinates[2], coordinates[4]), {})[tuple(coordinates[5:])] = value['value']
        rows, seen, owners = [], set(), {}
        for (category_index, _), product in sorted(products.items()):
            category = _text(selected[PREFIX + (category_index, 'tag')])
            product_id = _identifier(product[('id',)])
            name = _text(product[('name',)])
            price = _number(product[('min_price',)])
            render_price = _number(product[('render_info', 'price_info', 'min_price')])
            skus = sorted({c[1] for c in product if len(c) == 3 and c[0] == 'skus'})
            if not skus:
                raise CategoryCandidateError()
            for index in skus:
                sku_id = _identifier(product[('skus', index, 'id')])
                if ((category, sku_id) in seen or sku_id in owners and owners[sku_id] != product_id):
                    raise CategoryCandidateError()
                seen.add((category, sku_id)); owners[sku_id] = product_id
                origin = product.get(('skus', index, 'origin_price'))
                rows.append(CategoryCandidateRow(category, product_id, name, sku_id, price,
                    render_price, _number(product[('skus', index, 'price')]),
                    _optional_text(product, ('unit',)), _optional_text(product, ('skus', index, 'spec')),
                    _optional_text(product, ('skus', index, 'spec_desc')),
                    None if origin is None else _number(origin)))
        if not rows:
            raise CategoryCandidateError('P29_CATEGORY_CANDIDATE_EMPTY')
        return tuple(rows)
    except CategoryCandidateError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError):
        raise CategoryCandidateError() from None
