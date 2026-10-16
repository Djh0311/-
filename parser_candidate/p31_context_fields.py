"""Allowlisted observation and category text, kept separate from SKU rows."""

from . import p31_public_fields as base

FOOD_SPECS = (
    ('operation_content_text', ('data', 'container_operation_source', 'operation_source_list', None, 'content'), '运营说明文字'),
    ('operation_tag_name_text', ('data', 'container_operation_source', 'tag_name'), '运营标签名称'),
    ('moderate_ordering_reminder_text', ('data', 'moderate_ordering_reminder'), '适量点餐提示'),
    ('delivery_tab_text', ('data', 'pick_goods_tab_info', 'delivery', 'text'), '配送页签文字（非已选配送方式）'),
    ('self_pick_tab_text', ('data', 'pick_goods_tab_info', 'self_pick', 'text'), '自取页签文字（非已选自取状态）'),
)
CATEGORY_PREFIX = ('data', 'food_spu_tags', None)
CATEGORY_SPECS = (
    ('category_activity_text', CATEGORY_PREFIX + ('activity_info', 'activity_text'), '分类活动说明'),
    ('category_activity_tag_text', CATEGORY_PREFIX + ('activity_tag',), '分类活动标签'),
    ('category_description_text', CATEGORY_PREFIX + ('description',), '分类说明'),
    ('category_fold_text', CATEGORY_PREFIX + ('fold_dynamic_spus_text',), '分类展开提示'),
    ('category_tag_description_text', CATEGORY_PREFIX + ('tag_description',), '分类标签说明'),
)
LIST_SPECS = (
    ('required_tag_tips_text', ('data', 'required_tag_info', 'tips'), '必选分类提示'),
    ('required_tag_toast_text', ('data', 'required_tag_info', 'toast'), '必选分类短提示'),
)
SPECS = FOOD_SPECS + CATEGORY_SPECS + LIST_SPECS


def _check_leaf_types(analysis, paths):
    metadata = analysis.get('fields')
    if type(metadata) is not list or len(metadata) > 8000:
        base._fail()
    for item in metadata:
        if type(item) is not dict or type(item.get('path')) is not str:
            base._fail()
        path = item['path']
        if any(path == root or path.startswith(root + '.') or path.startswith(root + '[') for root in paths):
            if path not in paths or item.get('type') not in ('string', 'null'):
                base._fail()


def _row(spec, coords, selected, scope, category_ref=None, category_index=None, entry_index=None):
    field, pattern, label = spec
    value, state = base._fact(selected.get(coords, base._MISSING), 'text')
    return {'scope': scope, 'category_ref': category_ref, 'category_index': category_index,
            'entry_index': entry_index, 'field': field, 'field_label_zh': label,
            'source_path': base._canonical(pattern), 'value': value, 'state': state}


def parse_context_fields(analysis, endpoint_id):
    if endpoint_id not in ('FOOD', 'PRODUCTLIST'):
        base._fail()
    specs = FOOD_SPECS if endpoint_id == 'FOOD' else CATEGORY_SPECS + LIST_SPECS
    patterns = {base._canonical(path): path for _, path, _ in specs}
    _check_leaf_types(analysis, patterns)
    selected = base._select(analysis, patterns)
    rows = []
    if endpoint_id == 'FOOD':
        for spec in specs:
            path = spec[1]
            if None in path:
                matches = sorted(c for c in selected if len(c) == len(path)
                                 and all(p is None or p == v for p, v in zip(path, c)))
                for coords in matches:
                    rows.append(_row(spec, coords, selected, 'FOOD_ROOT', entry_index=coords[3]))
                if not matches:
                    rows.append(_row(spec, path, selected, 'FOOD_ROOT'))
            else:
                rows.append(_row(spec, path, selected, 'FOOD_ROOT'))
    else:
        tag = CATEGORY_PREFIX + ('tag',)
        ids = base._select(analysis, {base._canonical(tag): tag})
        categories = {}
        for coords, value in sorted(ids.items()):
            value, state = base._fact(value, 'text')
            if state != 'PRESENT_UNCONFIRMED' or value in categories.values():
                base._fail()
            categories[coords[2]] = value
        for coords in selected:
            if coords[:2] == ('data', 'food_spu_tags') and coords[2] not in categories:
                base._fail()
        for index, ref in categories.items():
            for spec in CATEGORY_SPECS:
                path = spec[1][:2] + (index,) + spec[1][3:]
                rows.append(_row(spec, path, selected, 'CATEGORY', ref, index))
        rows.extend(_row(spec, spec[1], selected, 'PRODUCTLIST_ROOT') for spec in LIST_SPECS)
    return rows
