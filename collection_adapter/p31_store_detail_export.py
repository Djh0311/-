"""Offline export of selected public store details, with explicit provenance.

Only existing public projections and delivered tables are read. Identity links
observations; it does not make their business values contemporaneous.
"""

import argparse
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from parser_candidate import p31_public_fields as fields
from parser_candidate.p31_context_fields import _check_leaf_types
from . import p31_business_export as base
from .p29_store_inventory import _read_owned, _validate
from .p29_receiver_control import _root
from collection_core.result_publisher import (
    ResultPublishError, _DIRECTORY_FLAGS, _write_file, precheck_result_destination,
)

SCHEMA = 'p31-store-detail-bundle-v1.schema.json'
DETAIL_NAME = re.compile(r'store_detail_[a-f0-9]{32}-public-fields\.json')
PRODUCT_NAME = re.compile(r'p31_context_codes_[a-f0-9]{32}')
RESULT_NAME = re.compile(r'p31_store_detail_[a-f0-9]{32}')
FILES = ('stores.json', 'stores.csv', 'field_dictionary.json', 'coverage.json',
         'association.json', 'manifest.json')
SPECS = (
    ('store_name', ('data', 'name'), '门店名称'),
    ('address', ('data', 'address'), '公开门店地址'),
    ('phones', ('data', 'phone_list', None), '公开电话（保留索引）'),
    ('delivery_period', ('data', 'shipping_time'), '配送时段，不是营业时间'),
    ('delivery_description', ('data', 'delivery_info_v2', 'text'), '配送说明'),
    ('delivery_tip', ('data', 'delivery_tip'), '配送提示'),
    ('services', ('data', 'poi_service_info', None, 'content'), '服务内容（保留索引）'),
    ('tags', ('data', 'poi_attribute_tags', None, 'content'), '门店标签（保留索引）'),
    ('bulletin', ('data', 'bulletin'), '门店公告'),
)
ID_COLUMNS = ('store_id', 'store_numeric_id', 'source_file', 'observed_at', 'window_ref')
COLUMNS = ID_COLUMNS + tuple(c for name, path, _ in SPECS
    for c in (name + ('_json' if None in path else ''), name + '_state'))
GAPS = (
    ('opening_hours', 'NOT_CONFIRMED', '已确认配送时段；未确认独立营业时间来源。'),
    ('complete_promotion_rules', 'NOT_CONFIRMED', '历史展示标签不证明有效期、适用对象及叠加规则完整。'),
    ('complete_delivery_rules', 'NOT_CONFIRMED', '配送说明已整理，完整范围、条件与费用规则仍未确认。'),
    ('unmapped_detail_fields', 'NOT_ADAPTED', '本次只转换列明的九组字段，其他公开字段尚未逐项解释。'),
    ('all_store_products', 'NOT_CONFIRMED', '已有分类覆盖证据仅限当批声明集合。'),
)


def _fail(code='P31_DETAIL_INPUT_INVALID'):
    base._fail(code)


def _fact(value):
    value, state = fields._fact(value, 'text')
    return {'value': value, 'state': 'PRESENT_AS_OBSERVED'
            if state == 'PRESENT_UNCONFIRMED' else state}


def _extract(analysis, pattern):
    path = fields._canonical(pattern)
    _check_leaf_types(analysis, {path})
    selected = fields._select(analysis, {path: pattern})
    rejected = any(f['path'] == path for f in analysis['unavailable_fields'])
    if None not in pattern:
        if rejected and selected:
            _fail()
        return ({'value': None, 'state': 'SOURCE_REJECTED'} if rejected
                else _fact(selected.get(pattern, fields._MISSING)))
    index_at = pattern.index(None)
    parent = fields._canonical(pattern[:index_at])
    parent_types = {f['type'] for f in analysis['fields'] if f['path'] == parent}
    if parent_types - {'array', 'null'} or len(parent_types) > 1:
        _fail()
    items = [{'index': coords[index_at], **_fact(value)}
             for coords, value in sorted(selected.items())]
    if items and parent_types != {'array'}:
        _fail()
    if rejected:
        state = 'PARTIAL_REJECTED' if items else 'SOURCE_REJECTED'
    elif items:
        state = 'PRESENT_AS_OBSERVED'
    elif parent_types == {'null'}:
        state = 'SOURCE_NULL'
    elif parent_types == {'array'} and not any(
            f['path'].startswith(parent + '[]') for f in analysis['fields']):
        state = 'SOURCE_EMPTY'
    else:
        state = 'NOT_OBSERVED'
    return {'items': items, 'state': state}


def detail_record(document, source_file):
    if type(source_file) is not str or not DETAIL_NAME.fullmatch(source_file):
        _fail()
    _validate(document, 'p29-store-detail-public-copy-v1.schema.json')
    if document['response_code_status'] != 'ZERO':
        _fail('P31_DETAIL_RESPONSE_NOT_SUCCESSFUL')
    analysis = document['public_analysis']
    patterns = {'$.data.poi_id_str': ('data', 'poi_id_str'),
                '$.data.wm_poi_id': ('data', 'wm_poi_id')}
    ids = fields._select(analysis, patterns)
    store_id = ids.get(('data', 'poi_id_str'))
    numeric_id = ids.get(('data', 'wm_poi_id'))
    if (type(store_id) is not str or not store_id or type(numeric_id) is not int):
        _fail('P31_DETAIL_IDENTITY_MISSING')
    fields._fact(store_id, 'text')
    numeric_text, _ = fields._fact(numeric_id, 'integer')
    record = {'store_id': store_id, 'store_numeric_id': numeric_text,
              'source_file': source_file, 'observed_at': document['observed_at'],
              'window_ref': document['window_ref']}
    record.update({name: _extract(analysis, pattern) for name, pattern, _ in SPECS})
    return record


def _product_bundle(root, name):
    if type(name) is not str or not PRODUCT_NAME.fullmatch(name):
        _fail('P31_DETAIL_PRODUCT_RESULT_INVALID')
    bundle = _root(root / name)
    manifest = _read_owned(bundle / 'manifest.json', 65536)
    stores = _read_owned(bundle / 'stores.json', 4 * 1024 * 1024)
    products = _read_owned(bundle / 'records.json', 16 * 1024 * 1024)
    for doc, schema in ((manifest, 'p31-business-manifest-v6.schema.json'),
                        (stores, 'p31-business-stores-v3.schema.json'),
                        (products, 'p31-business-products-v4.schema.json')):
        _validate(doc, schema)
    if (manifest['result_name'] != name or stores['record_count'] != 1
            or len(stores['records']) != 1 or manifest['store_record_count'] != 1
            or stores['window_ref'] != manifest['window_ref']
            or products['window_ref'] != manifest['window_ref']
            or stores['records'][0]['window_ref'] != manifest['window_ref']
            or not products['records']
            or any(r['window_ref'] != manifest['window_ref'] for r in products['records'])):
        _fail('P31_DETAIL_PRODUCT_RESULT_INVALID')
    counts = {'record_count': len(products['records']),
              'product_count': len({r['product_id'] for r in products['records']}),
              'sku_count': len({r['sku_id'] for r in products['records']}),
              'category_count': len({r['category_ref'] for r in products['records']})}
    if any(manifest[k] != n or products[k] != n for k, n in counts.items()):
        _fail('P31_DETAIL_PRODUCT_RESULT_INVALID')
    return stores['records'][0], manifest


def associate(record, store, manifest):
    if (record['store_id'] != store['store_id']
            or record['store_numeric_id'] != store['store_numeric_id_number']
            or store['store_numeric_id_number_state'] not in
            ('PRESENT_UNCONFIRMED', 'NEGATIVE_SEMANTICS_UNCONFIRMED')):
        _fail('P31_DETAIL_STORE_ID_MISMATCH')
    return {'basis': 'EXACT_PUBLIC_STRING_AND_NUMERIC_STORE_IDS',
            'string_id_match': True, 'numeric_id_match': True,
            'name_match': record['store_name']['value'] == store['store_name'],
            'product_result_name': manifest['result_name'],
            'product_window_ref': manifest['window_ref'],
            'detail_window_ref': record['window_ref'],
            'product_record_count': manifest['record_count'],
            'product_store_observed_at': store['observed_at'],
            'detail_observed_at': record['observed_at'],
            'values_are_same_observation': False, 'product_values_modified': False}


def bundle_view(detail_root, detail_file, product_root, product_result, result_name):
    detail_root, product_root = _root(detail_root), _root(product_root)
    if not isinstance(detail_file, str) or not DETAIL_NAME.fullmatch(detail_file):
        _fail()
    if not isinstance(result_name, str) or not RESULT_NAME.fullmatch(result_name):
        _fail('P31_EXPORT_NAME_INVALID')
    doc = _read_owned(detail_root / detail_file, 4 * 1024 * 1024)
    record = detail_record(doc, detail_file)
    store, product_manifest = _product_bundle(product_root, product_result)
    association = associate(record, store, product_manifest)
    bundle = {
        'stores': {'schema_version': 'p31-store-details/v1', 'record_count': 1,
                   'records': [record], 'all_detail_fields_adapted': False},
        'field_dictionary': {'schema_version': 'p31-store-detail-dictionary/v1',
            'fields': [{'field': name, 'label_zh': label,
                        'source_path': fields._canonical(pattern),
                        'kind': 'INDEXED_TEXT' if None in pattern else 'TEXT'}
                       for name, pattern, label in SPECS]},
        'coverage': {'schema_version': 'p31-store-detail-coverage/v1',
            'fields': [{'field': name, 'state': record[name]['state']} for name, _, _ in SPECS],
            'gaps': [{'field': name, 'status': state, 'explanation_zh': why}
                     for name, state, why in GAPS],
            'images': 'EXCLUDED_BY_USER', 'personal_offers': 'EXCLUDED_BY_USER',
            'product_result': 'incomplete'},
        'association': association,
        'manifest': {'schema_version': 'p31-store-detail-manifest/v1',
            'result_name': result_name, 'record_count': 1, 'files': list(FILES),
            'detail_root': str(detail_root), 'detail_file': detail_file,
            'product_root': str(product_root), 'product_result_name': product_result,
            'live_attempts_consumed': 0, 'raw_payload_read': False,
            'original_files_modified': False, 'product_result': 'incomplete'},
    }
    _validate(bundle, SCHEMA)
    return bundle


def csv_row(record):
    row = {key: record[key] for key in ID_COLUMNS}
    for name, pattern, _ in SPECS:
        value = record[name]
        row[name + ('_json' if None in pattern else '')] = (
            json.dumps(value['items'], ensure_ascii=False, separators=(',', ':'))
            if None in pattern else value['value'])
        row[name + '_state'] = value['state']
    return row


def publish_store_detail(detail_root, detail_file, product_root, product_result, result_name=None):
    detail_root = _root(detail_root)
    name = result_name if result_name is not None else 'p31_store_detail_' + uuid4().hex
    if type(name) is not str or not RESULT_NAME.fullmatch(name):
        _fail('P31_EXPORT_NAME_INVALID')
    precheck_result_destination(str(detail_root), name)
    bundle = bundle_view(detail_root, detail_file, product_root, product_result, name)
    content = {key + '.json': base._bytes(value) for key, value in bundle.items()}
    content['stores.csv'] = base._csv_bytes([csv_row(bundle['stores']['records'][0])], COLUMNS)
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
    return {'result_name': name, 'record_count': 1, 'live_attempts_consumed': 0,
            'store_identity_match': True, 'product_result': 'incomplete'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--detail-root', required=True)
    parser.add_argument('--detail-file', required=True)
    parser.add_argument('--product-root', required=True)
    parser.add_argument('--product-result', required=True)
    args = parser.parse_args(argv)
    try:
        receipt = publish_store_detail(Path(args.detail_root), args.detail_file,
                                       Path(args.product_root), args.product_result)
        print(json.dumps(receipt))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({'code': getattr(error, 'code', 'P31_DETAIL_INPUT_INVALID')}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
