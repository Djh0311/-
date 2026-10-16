"""Public store promotion text, separate from customer coupon eligibility."""

from . import p31_public_fields as base
from .p31_context_fields import _check_leaf_types

PATTERN = ('data', 'poi_info', 'poi_normal_tags', None, 'sub_tags', None, 'text')
SOURCE_PATH = base._canonical(PATTERN)


def parse_store_promotions(analysis):
    _check_leaf_types(analysis, {SOURCE_PATH})
    selected = base._select(analysis, {SOURCE_PATH: PATTERN})
    rows = []
    for coords, raw in sorted(selected.items()):
        value, state = base._fact(raw, 'text')
        rows.append({'group_index': coords[3], 'tag_index': coords[5],
                     'display_text': value, 'state': state})
    return rows or [{'group_index': None, 'tag_index': None,
                     'display_text': None, 'state': 'NOT_OBSERVED'}]
