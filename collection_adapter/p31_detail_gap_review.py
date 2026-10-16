"""Classify one existing store-detail projection and export its delivery scalars.

Opening hours are not inferred from the delivery period. Promotion rules and
store coordinates stay out of this table. Image and URL paths are not exported.
"""

import argparse
import json
import os
from collections import Counter
from pathlib import Path
import re
from uuid import uuid4

from parser_candidate import p31_public_fields as fields
from collection_core.result_publisher import (
    ResultPublishError, _DIRECTORY_FLAGS, _write_file, precheck_result_destination,
)
from . import p31_business_export as base
from . import p31_store_detail_export as detail
from .p29_receiver_control import _root
from .p29_store_inventory import _read_owned, _validate

SCHEMA = 'p31-detail-gap-review-v1.schema.json'
RESULT_NAME = re.compile(r'p31_detail_gap_[a-f0-9]{32}')
FILES = ('delivery.json', 'delivery.csv', 'field_dictionary.json',
         'path_disposition.json', 'coverage.json', 'manifest.json')
DISPOSITIONS = (
    'ENVELOPE', 'ALREADY_EXPORTED', 'CONTAINER', 'DELIVERY_SCALAR_EXPORTED',
    'IMAGE_OR_URL_EXCLUDED', 'IMAGE_GALLERY_EXCLUDED', 'PRESENTATION_NOT_EXPORTED',
    'STORE_COORDINATE_NOT_EXPORTED', 'PUBLIC_SCALAR_UNCONFIRMED_NOT_EXPORTED',
    'OBJECT_WITHOUT_PUBLIC_SCALARS', 'UNCLASSIFIED',
)
SPECS = (
    ('delivery_service_text', ('data', 'deliveryInfoRpc', 'deliveryType'), 'text',
     '详情配送服务来源文字'),
    ('delivery_info_type_text', ('data', 'delivery_info_v2', 'type'), 'text',
     '详情配送信息类型来源文字'),
    ('delivery_type_code', ('data', 'delivery_type'), 'integer',
     '详情配送类型来源数字，枚举未确认'),
    ('distance_text', ('data', 'distance'), 'text', '详情距离来源文字，不拆单位'),
    ('map_display_range_number', ('data', 'map_display_range'), 'integer',
     '地图显示范围来源数字，不是配送边界'),
    ('map_type_code', ('data', 'poi_map_type'), 'integer', '地图类型来源数字，枚举未确认'),
)
EXACT = {
    **{path: 'ENVELOPE' for path in ('$', '$.code', '$.data', '$.from_shepherd', '$.msg')},
    **{path: 'ALREADY_EXPORTED' for path in (
        '$.data.address', '$.data.bulletin', '$.data.delivery_info_v2.text',
        '$.data.delivery_tip', '$.data.name', '$.data.phone_list', '$.data.phone_list[]',
        '$.data.poi_attribute_tags', '$.data.poi_attribute_tags[]',
        '$.data.poi_attribute_tags[].content', '$.data.poi_id_str',
        '$.data.poi_service_info', '$.data.poi_service_info[]',
        '$.data.poi_service_info[].content', '$.data.shipping_time', '$.data.wm_poi_id')},
    **{path: 'CONTAINER' for path in (
        '$.data.deliveryInfoRpc', '$.data.delivery_info_v2', '$.data.env_protect_url',
        '$.data.poi_qualify_info', '$.data.poi_real_video', '$.data.poi_story_info')},
    **{fields._canonical(pattern): 'DELIVERY_SCALAR_EXPORTED' for _, pattern, _, _ in SPECS},
    **{path: 'IMAGE_OR_URL_EXCLUDED' for path in (
        '$.data.delivery_info_v2.icon', '$.data.env_protect_url.url', '$.data.pic_url',
        '$.data.poi_attribute_tags[].icon', '$.data.poi_attribute_tags[].url',
        '$.data.poi_qualify_info.url', '$.data.poi_real_video.top_pic',
        '$.data.poi_service_info[].icon', '$.data.poi_service_info[].scheme_url',
        '$.data.poi_story_info.entrance_url', '$.data.poi_story_info.top_pic')},
    '$.data.latitude': 'STORE_COORDINATE_NOT_EXPORTED',
    '$.data.longitude': 'STORE_COORDINATE_NOT_EXPORTED',
    '$.data.shop_template_type': 'PRESENTATION_NOT_EXPORTED',
    '$.data.dp_address': 'OBJECT_WITHOUT_PUBLIC_SCALARS',
    **{path: 'PUBLIC_SCALAR_UNCONFIRMED_NOT_EXPORTED' for path in (
        '$.data.env_protect_url.display', '$.data.env_protect_url.displayName',
        '$.data.phone_call_text', '$.data.poi_qualify_info.content',
        '$.data.poi_real_video.title', '$.data.poi_story_info.title',
        '$.data.poi_attribute_tags[].type', '$.data.poi_service_info[].label_color',
        '$.data.poi_service_info[].label_desc_text', '$.data.poi_service_info[].label_type',
        '$.data.poi_service_info[].scheme_sec_url', '$.data.sp_status',
        '$.data.has_inspection_video_material')},
}
PREFIXES = (
    ('$.data.poi_env_info', 'IMAGE_GALLERY_EXCLUDED'),
    ('$.data.function_control', 'PRESENTATION_NOT_EXPORTED'),
)
OPENING_MARKERS = ('opening_hours', 'opening_hour', 'open_time', 'business_hours',
                   'business_time', 'sale_time')
PROMO_MARKERS = ('promotion', 'coupon', 'activity', 'discount')
AREA_MARKERS = ('shipping_fee', 'min_price', 'delivery_area', 'shipping_area',
                'delivery_range', 'origin_shipping_fee')
ID_COLUMNS = detail.ID_COLUMNS
COLUMNS = ID_COLUMNS + tuple(name + suffix for name, _, _, _ in SPECS
                             for suffix in ('', '_state'))


def _fail(code='P31_DETAIL_INPUT_INVALID'):
    base._fail(code)


def _leaf(path):
    return path.rsplit('.', 1)[-1].replace('[]', '').lower()


def _marked(paths, markers):
    return sorted(path for path in paths if any(marker in _leaf(path) for marker in markers))


def _classify(path, reasons):
    if path in EXACT:
        return EXACT[path]
    for prefix, label in PREFIXES:
        if path == prefix or path.startswith(prefix + '.') or path.startswith(prefix + '['):
            return label
    if 'URL_VALUE' in reasons:
        return 'IMAGE_OR_URL_EXCLUDED'
    return 'UNCLASSIFIED'


def _scalar(analysis, pattern, kind):
    path = fields._canonical(pattern)
    allowed = {'string', 'null'} if kind == 'text' else {'number', 'null'}
    observed = {item['type'] for item in analysis['fields'] if item['path'] == path}
    if observed - allowed or len(observed) > 1:
        _fail()
    selected = fields._select(analysis, {path: pattern})
    rejected = any(item['path'] == path for item in analysis['unavailable_fields'])
    if rejected and selected:
        _fail()
    if rejected:
        return {'value': None, 'state': 'SOURCE_REJECTED'}
    value, state = fields._fact(selected.get(pattern, fields._MISSING), kind)
    if kind == 'text' and state == 'PRESENT_UNCONFIRMED':
        state = 'PRESENT_AS_OBSERVED'
    return {'value': value, 'state': state}


def _disposition(analysis):
    if (type(analysis) is not dict or type(analysis.get('fields')) is not list
            or type(analysis.get('unavailable_fields')) is not list
            or type(analysis.get('restricted_fields')) is not list
            or type(analysis.get('public_values')) is not list):
        _fail()
    types, reasons = {}, {}
    for item in analysis['fields']:
        if type(item) is not dict or type(item.get('path')) is not str or type(item.get('type')) is not str:
            _fail()
        types.setdefault(item['path'], set()).add(item['type'])
    for item in analysis['unavailable_fields']:
        if type(item) is not dict or type(item.get('path')) is not str or type(item.get('reason')) is not str:
            _fail()
        reasons.setdefault(item['path'], set()).add(item['reason'])
        types.setdefault(item['path'], set())
    for item in analysis['restricted_fields']:
        if type(item) is not dict or type(item.get('path')) is not str:
            _fail()
        types.setdefault(item['path'], set())
    stats = {path: Counter() for path in types}
    for item in analysis['public_values']:
        if type(item) is not dict or type(item.get('path')) is not str or 'value' not in item:
            _fail()
        path, value = item['path'], item['value']
        stats.setdefault(path, Counter())
        types.setdefault(path, set())
        if value is None:
            stats[path]['null'] += 1
        elif value == '':
            stats[path]['empty'] += 1
            stats[path]['text'] += 1
        elif type(value) is str:
            stats[path]['text'] += 1
        elif type(value) is bool:
            stats[path]['boolean'] += 1
        elif type(value) in (int, float):
            stats[path]['number'] += 1
        else:
            _fail()
    rows = []
    for path in sorted(types):
        count = stats.get(path, Counter())
        rows.append({
            'path': path, 'types': sorted(types[path]),
            'value_count': count['null'] + count['text'] + count['number'] + count['boolean'],
            'null_count': count['null'],
            'empty_count': count['empty'], 'text_count': count['text'],
            'number_count': count['number'], 'boolean_count': count['boolean'],
            'unavailable_reasons': sorted(reasons.get(path, ())),
            'disposition': _classify(path, reasons.get(path, ())),
        })
    counts = Counter(row['disposition'] for row in rows)
    return rows, {name: counts[name] for name in DISPOSITIONS}


def _gap(paths, markers, absent, present):
    return {'status': present if _marked(paths, markers) else absent,
            'matched_path_count': len(_marked(paths, markers))}


def bundle_view(document, source_file, result_name):
    if type(result_name) is not str or not RESULT_NAME.fullmatch(result_name):
        _fail('P31_EXPORT_NAME_INVALID')
    record = detail.detail_record(document, source_file)
    analysis = document['public_analysis']
    paths, counts = _disposition(analysis)
    delivery = {name: _scalar(analysis, pattern, kind) for name, pattern, kind, _ in SPECS}
    path_names = [row['path'] for row in paths]
    opening = _gap(path_names, OPENING_MARKERS, 'PATH_ABSENT', 'OBSERVED_NOT_EXPORTED')
    promotion = _gap(path_names, PROMO_MARKERS, 'PATH_ABSENT', 'OBSERVED_NOT_EXPORTED')
    area_paths = _marked(path_names, AREA_MARKERS)
    bundle = {
        'delivery': {'schema_version': 'p31-detail-delivery-scalars/v1', 'record_count': 1,
                     'opening_hours_filled_from_delivery_period': False,
                     'records': [{**{key: record[key] for key in ID_COLUMNS}, **delivery}]},
        'field_dictionary': {'schema_version': 'p31-detail-delivery-dictionary/v1',
            'fields': [{'field': name, 'label_zh': label, 'source_path': fields._canonical(pattern),
                        'kind': 'INTEGER' if kind == 'integer' else 'TEXT'}
                       for name, pattern, kind, label in SPECS]},
        'path_disposition': {'schema_version': 'p31-detail-path-disposition/v1',
            'business_values_included': False, 'paths': paths, 'counts': counts},
        'coverage': {'schema_version': 'p31-detail-gap-coverage/v1',
            'fields': [{'field': name, 'state': delivery[name]['state']} for name, _, _, _ in SPECS],
            'gaps': [
                {'field': 'opening_hours', **opening,
                 'explanation_zh': '独立营业时间路径按固定名称核对；配送时段保持原字段，不改作营业时间。'},
                {'field': 'complete_promotion_rules', **promotion,
                 'explanation_zh': '优惠、券和活动路径按固定名称核对；其他观察的标签不并入这张表。'},
                {'field': 'complete_delivery_rules', 'status': 'PARTIAL_SOURCE_SCALARS',
                 'matched_path_count': len(area_paths),
                 'explanation_zh': '本表只增加这份详情里的六个来源标量，不补费用、起送或范围边界。'},
                {'field': 'remaining_public_fields', 'status': 'CLASSIFIED_NOT_FULLY_EXPORTED',
                 'matched_path_count': counts['PUBLIC_SCALAR_UNCONFIRMED_NOT_EXPORTED']
                 + counts['UNCLASSIFIED'],
                 'explanation_zh': '其余公开路径已归类。含义未确认或未归类的路径不导出。'},
            ],
            'images': 'EXCLUDED_BY_USER', 'personal_offers': 'EXCLUDED_BY_USER',
            'store_coordinates_exported': False, 'unclassified_count': counts['UNCLASSIFIED'],
            'product_result': 'incomplete'},
        'manifest': {'schema_version': 'p31-detail-gap-manifest/v1', 'result_name': result_name,
            'record_count': 1, 'files': list(FILES), 'detail_file': source_file,
            'path_count': len(paths), 'unclassified_count': counts['UNCLASSIFIED'],
            'live_attempts_consumed': 0, 'raw_payload_read': False,
            'original_files_modified': False, 'product_result': 'incomplete'},
    }
    _validate(bundle, SCHEMA)
    return bundle


def csv_row(record):
    row = {key: record[key] for key in ID_COLUMNS}
    for name, _, _, _ in SPECS:
        row[name] = record[name]['value']
        row[name + '_state'] = record[name]['state']
    return row


def publish_detail_gap(detail_root, detail_file, result_name=None):
    detail_root = _root(detail_root)
    name = result_name if result_name is not None else 'p31_detail_gap_' + uuid4().hex
    if type(name) is not str or not RESULT_NAME.fullmatch(name):
        _fail('P31_EXPORT_NAME_INVALID')
    if not isinstance(detail_file, str) or not detail.DETAIL_NAME.fullmatch(detail_file):
        _fail()
    precheck_result_destination(str(detail_root), name)
    document = _read_owned(detail_root / detail_file, 4 * 1024 * 1024)
    bundle = bundle_view(document, detail_file, name)
    content = {key + '.json': base._bytes(value) for key, value in bundle.items()}
    content['delivery.csv'] = base._csv_bytes([csv_row(bundle['delivery']['records'][0])], COLUMNS)
    if sum(map(len, content.values())) > 4 * 1024 * 1024:
        _fail('P31_EXPORT_BUDGET')
    root_fd = result_fd = None
    created = success = False
    try:
        root_fd = os.open(detail_root, _DIRECTORY_FLAGS)
        os.mkdir(name, 0o700, dir_fd=root_fd)
        created = True
        result_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        for filename in FILES:
            _write_file(result_fd, filename, content[filename])
        os.fsync(result_fd)
        os.fsync(root_fd)
        success = True
    except FileExistsError:
        raise ResultPublishError('RESULT_TARGET_EXISTS') from None
    except OSError:
        raise ResultPublishError('RESULT_PUBLISH_FAILED') from None
    finally:
        if created and not success:
            if result_fd is not None:
                for filename in FILES:
                    try:
                        os.unlink(filename, dir_fd=result_fd)
                    except OSError:
                        pass
            if root_fd is not None:
                try:
                    os.rmdir(name, dir_fd=root_fd)
                except OSError:
                    pass
        for fd in (result_fd, root_fd):
            if fd is not None:
                os.close(fd)
    return {'result_name': name, 'record_count': 1, 'path_count': bundle['manifest']['path_count'],
            'unclassified_count': bundle['manifest']['unclassified_count'],
            'live_attempts_consumed': 0, 'product_result': 'incomplete'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--detail-root', required=True)
    parser.add_argument('--detail-file', required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(publish_detail_gap(Path(args.detail_root), args.detail_file)))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({'code': getattr(error, 'code', 'P31_DETAIL_INPUT_INVALID')}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
