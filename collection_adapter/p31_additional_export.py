"""Versioned extension of existing public fields; no acquisition."""

from collections import Counter
from datetime import datetime
import os
from pathlib import Path
import re
import json
import sys
from uuid import uuid4

from . import p31_business_export as base
from .p29_store_inventory import _initial, _read_owned, _validate
from .p29_receiver_control import ReceiverControlError
from collection_core.p29 import MAX_COLLECTION_BYTES
from collection_core.result_publisher import (
    ResultPublishError, _DIRECTORY_FLAGS, _write_file,
    precheck_result_destination,
)
from parser_candidate import p31_additional_fields as fields
from parser_candidate.p29_category_profile import CategoryCandidateError

PRODUCT_SCHEMA = 'p31-business-products-v2.schema.json'
STORE_SCHEMA = 'p31-business-stores-v2.schema.json'
FILES = base.FILES
_NAME = re.compile(r'p31_additional_fields_[a-f0-9]{32}')
RESULT_PREFIX = 'p31_additional_fields_'
RESULT_CODE = 'P31_ADDITIONAL_FIELDS_EXPORTED'
MANIFEST_SCHEMA = 'p31-business-manifest-v2.schema.json'
MANIFEST_VERSION = 'p31-business-manifest/v2'
DICTIONARY_SCHEMA = 'p31-field-dictionary-v1.schema.json'


def _groups():
    return (('products', fields.PRODUCT_SPECS, fields.PRODUCT_PREFIX),
            ('products', fields.SKU_SPECS, fields.SKU_PREFIX),
            ('stores', fields.STORE_SPECS, fields.STORE_PREFIX))


def csv_fields():
    products, stores = map(list, base.csv_fields())
    for table, specs, _ in _groups():
        destination = products if table == 'products' else stores
        for field, path, _, _ in specs:
            destination.extend((field + '_json' if None in path else field, field + '_state'))
    return tuple(products), tuple(stores)


def _business_view(root, observation_name, input_names):
    products, stores = base.business_view(root, observation_name, input_names)
    root = base._root(root)
    public, initial, _, _ = _initial(root, observation_name)
    by_file = {observation_name + '-public-fields.json': fields.parse_product_fields(initial)}
    equal_time = {}
    for name in input_names:
        source = _read_owned(root / name, 4 * 1024 * 1024)
        parsed = fields.parse_product_fields(source['public_analysis'])
        by_file[name] = parsed
        at = datetime.fromisoformat(source['observed_at'].replace('Z', '+00:00'))
        for identity, values in parsed.items():
            key, signature = (at, identity[0], identity[2]), (identity[1], values)
            if key in equal_time and equal_time[key] != signature:
                base._fail('P31_EXPORT_EQUAL_TIME_FIELDS_CONFLICT')
            equal_time[key] = signature
    for row in products['records']:
        identity = row['category_ref'], row['product_id'], row['sku_id']
        additional = by_file[row['source_file']].get(identity)
        if additional is None or set(row) & set(additional):
            base._fail('P31_EXPORT_ROW_SOURCE_MISMATCH')
        row.update(additional)
    food = next(o for o in public['observations'] if o['endpoint_id'] == 'FOOD')
    additional = fields.parse_store_fields(food)
    if set(stores['records'][0]) & set(additional):
        base._fail('P31_EXPORT_ROW_SOURCE_MISMATCH')
    stores['records'][0].update(additional)
    products['schema_version'] = 'p31-business-products/v2'
    stores['schema_version'] = 'p31-business-stores/v2'
    _validate(products, PRODUCT_SCHEMA)
    _validate(stores, STORE_SCHEMA)
    return products, stores


def business_view(root, observation_name, input_names):
    try:
        return _business_view(root, observation_name, input_names)
    except (CategoryCandidateError, ReceiverControlError):
        raise
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        base._fail()


def field_dictionary():
    document = base.field_dictionary()
    definitions = {(r['table'], r['field']): r for r in document['fields']}
    for table, specs, prefix in _groups():
        for field, path, kind, label in specs:
            array = None in path
            column = field + '_json' if array else field
            for key, title, dtype, source, semantics in (
                (column, label, 'json-string' if array else 'decimal-string' if kind == 'integer' else kind,
                 fields.base._canonical(prefix + path), 'SOURCE_FIELD_MEANING_NOT_PROMOTED'),
                (field + '_state', label + '：缺失或解析状态', 'enum-string', None, 'PARSER_STATE')):
                definitions[table, key] = {'table': table, 'field': key, 'label_zh': title, 'type': dtype,
                    'source_path': source, 'meaning_status': semantics,
                    'empty_cell': 'CONSULT_STATE_COLUMN_OR_SOURCE_BASIS', 'unit': 'NOT_INFERRED'}
    document['fields'] = [definitions[table, field] for table, columns in zip(('products', 'stores'), csv_fields()) for field in columns]
    # Dictionary/coverage contracts already permit bounded additional fields;
    # the product/store record and bundle versions distinguish this extension.
    return document


def coverage_view(products, stores):
    document = base.coverage_view(products, stores)
    for table, specs, _ in _groups():
        rows = (products if table == 'products' else stores)['records']
        for field, _, _, _ in specs:
            counts = Counter(row[field + '_state'] for row in rows)
            document['fields'].append({'table': table, 'field': field, 'row_count': len(rows),
                                      'states': {state: counts[state] for state in base.STATES}})
    return document


def publish_business_fields(root, observation_name, input_names, result_name=None, *, _profile=None):
    profile = _profile if _profile is not None else sys.modules[__name__]
    root = base._root(root)
    name = result_name if result_name is not None else profile.RESULT_PREFIX + uuid4().hex
    if type(name) is not str or profile._NAME.fullmatch(name) is None:
        base._fail('P31_EXPORT_NAME_INVALID')
    precheck_result_destination(str(root), name)
    products, stores = profile.business_view(root, observation_name, input_names)
    dictionary, coverage = profile.field_dictionary(), profile.coverage_view(products, stores)
    _validate(dictionary, profile.DICTIONARY_SCHEMA)
    _validate(coverage, 'p31-field-coverage-v1.schema.json')
    manifest = {'schema_version': profile.MANIFEST_VERSION, 'result_name': name,
        'window_ref': products['window_ref'], 'record_count': products['record_count'],
        'product_count': products['product_count'], 'sku_count': products['sku_count'],
        'category_count': products['category_count'], 'store_record_count': 1, 'files': list(FILES),
        'coverage_status': 'PARTIAL', 'complete_result_promotion': False,
        'target_system_import_verified': False, 'live_attempts_consumed': 0}
    _validate(manifest, profile.MANIFEST_SCHEMA)
    product_columns, store_columns = profile.csv_fields()
    contents = (base._bytes(products), base._csv_bytes(products['records'], product_columns),
                base._bytes(stores), base._csv_bytes(stores['records'], store_columns),
                base._bytes(dictionary), base._bytes(coverage), base._bytes(manifest))
    if sum(map(len, contents)) > profile.MAX_COLLECTION_BYTES:
        base._fail('P31_EXPORT_BUDGET')
    root_fd = result_fd = None
    created = success = False
    try:
        root_fd = os.open(root, _DIRECTORY_FLAGS)
        os.mkdir(name, 0o700, dir_fd=root_fd)
        created = True
        result_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        for filename, content in zip(FILES, contents):
            profile._write_file(result_fd, filename, content)
        os.fsync(result_fd)
        os.fsync(root_fd)
        success = True
    except FileExistsError:
        raise ResultPublishError('RESULT_TARGET_EXISTS') from None
    except OSError:
        raise ResultPublishError('RESULT_PUBLISH_FAILED') from None
    finally:
        if created and not success:
            base._cleanup_created_result(root_fd, result_fd, name)
        for fd in (result_fd, root_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
    return {key: manifest[key] for key in ('result_name', 'record_count', 'product_count',
        'sku_count', 'category_count', 'store_record_count', 'live_attempts_consumed')} | {
        'code': profile.RESULT_CODE, 'complete_result_promotion': False}


def main(*, _profile=None):
    profile = _profile if _profile is not None else sys.modules[__name__]
    parser = base._Arguments()
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--observation-name', required=True)
    parser.add_argument('--input-name', action='append', required=True)
    parser.add_argument('--result-name')
    try:
        args = parser.parse_args()
        result = profile.publish_business_fields(Path(args.output_root), args.observation_name, args.input_name, args.result_name)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (CategoryCandidateError, ReceiverControlError, ResultPublishError) as error:
        print(json.dumps({'code': error.code, 'live_attempts_consumed': 0}, sort_keys=True))
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({'code': 'P31_EXPORT_INPUT_INVALID', 'live_attempts_consumed': 0}, sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
