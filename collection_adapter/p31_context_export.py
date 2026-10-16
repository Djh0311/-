"""Public root/category text bundle; keeps existing product/store views intact."""

from collections import Counter
import os
import re
import sys
from uuid import uuid4

from . import p31_remaining_export as previous
from .p29_store_inventory import _initial, _validate
from .p29_receiver_control import ReceiverControlError
from collection_core.p29 import MAX_COLLECTION_BYTES
from collection_core.result_publisher import (
    ResultPublishError, _DIRECTORY_FLAGS, _write_file, precheck_result_destination,
)
from parser_candidate import p31_context_fields as fields
from parser_candidate.p29_category_profile import CategoryCandidateError

base = previous.base
TEXT_SCHEMA = 'p31-public-texts-v1.schema.json'
MANIFEST_SCHEMA = 'p31-business-manifest-v4.schema.json'
MANIFEST_VERSION = 'p31-business-manifest/v4'
RESULT_CODE = 'P31_CONTEXT_FIELDS_EXPORTED'
DICTIONARY_SCHEMA = 'p31-field-dictionary-v3.schema.json'
COVERAGE_SCHEMA = 'p31-field-coverage-v2.schema.json'
FILES = ('records.json', 'records.csv', 'stores.json', 'stores.csv',
         'public_texts.json', 'public_texts.csv', 'field_dictionary.json', 'coverage.json', 'manifest.json')
RESULT_PREFIX = 'p31_context_fields_'
_NAME = re.compile(r'p31_context_fields_[a-f0-9]{32}')
TEXT_COLUMNS = ('scope', 'category_ref', 'category_index', 'entry_index', 'field', 'field_label_zh',
                'source_path', 'value', 'state', 'endpoint_id', 'source_file', 'source_request_ref',
                'observed_at', 'window_ref')
_LABELS = ('说明所属对象', '分类编号（根级说明为空）', '原分类数组索引', '原运营说明数组索引',
           '字段代号', '字段中文说明', '原始字段路径', '来源文字', '缺失或解析状态',
           '自身来源端点', '自身公开投影文件', '自身请求引用', '自身观察时间', '窗口引用')


def business_view(root, observation_name, input_names):
    try:
        products, stores = previous.business_view(root, observation_name, input_names)
        root = base._root(root)
        public, _, _, _ = _initial(root, observation_name)
        records = []
        for endpoint in ('FOOD', 'PRODUCTLIST'):
            source = next(o for o in public['observations'] if o['endpoint_id'] == endpoint)
            for row in fields.parse_context_fields(source, endpoint):
                records.append({**row, 'endpoint_id': endpoint,
                    'source_file': observation_name + '-public-fields.json',
                    'source_request_ref': source['source_request_ref'], 'observed_at': source['observed_at'],
                    'window_ref': products['window_ref']})
        texts = {'schema_version': 'p31-public-texts/v1', 'window_ref': products['window_ref'],
                 'record_count': len(records), 'records': records,
                 'source_scope': 'INITIAL_PAIR_ALLOWLISTED_ROOT_AND_CATEGORY_TEXT',
                 'copied_into_product_rows': False, 'business_semantics_confirmed': False}
        _validate(texts, TEXT_SCHEMA)
        return products, stores, texts
    except (CategoryCandidateError, ReceiverControlError):
        raise
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        base._fail()


def field_dictionary():
    doc = previous.field_dictionary()
    doc['schema_version'] = 'p31-field-dictionary/v3'
    for column, label in zip(TEXT_COLUMNS, _LABELS):
        doc['fields'].append({'table': 'public_texts', 'field': column, 'label_zh': label,
            'type': 'integer' if column in ('category_index', 'entry_index') else 'text',
            'source_path': None, 'meaning_status': 'PARSER_STATE' if column == 'state' else
            'SOURCE_FIELD_MEANING_NOT_PROMOTED' if column == 'value' else 'SOURCE_REFERENCE',
            'empty_cell': 'CONSULT_STATE_COLUMN_OR_SOURCE_BASIS', 'unit': 'NOT_INFERRED'})
    doc['public_text_definitions'] = [
        {'field': field, 'source_path': fields.base._canonical(path), 'label_zh': label,
         'scope': 'FOOD_ROOT' if spec in fields.FOOD_SPECS else 'CATEGORY' if spec in fields.CATEGORY_SPECS else 'PRODUCTLIST_ROOT'}
        for spec in fields.SPECS for field, path, label in (spec,)]
    return doc


def coverage_view(products, stores, texts):
    doc = previous.coverage_view(products, stores)
    doc['schema_version'] = 'p31-field-coverage/v2'
    for field, _, _ in fields.SPECS:
        rows = [r for r in texts['records'] if r['field'] == field]
        counts = Counter(r['state'] for r in rows)
        doc['fields'].append({'table': 'public_texts', 'field': field, 'row_count': len(rows),
                              'states': {state: counts[state] for state in base.STATES}})
    return doc


def _cleanup(root_fd, result_fd, name):
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


def publish_business_fields(root, observation_name, input_names, result_name=None, *, _profile=None):
    profile = _profile if _profile is not None else sys.modules[__name__]
    root = base._root(root)
    name = result_name if result_name is not None else profile.RESULT_PREFIX + uuid4().hex
    if type(name) is not str or profile._NAME.fullmatch(name) is None:
        base._fail('P31_EXPORT_NAME_INVALID')
    precheck_result_destination(str(root), name)
    products, stores, texts = profile.business_view(root, observation_name, input_names)
    dictionary, coverage = profile.field_dictionary(), profile.coverage_view(products, stores, texts)
    _validate(dictionary, profile.DICTIONARY_SCHEMA)
    _validate(coverage, profile.COVERAGE_SCHEMA)
    manifest = {'schema_version': profile.MANIFEST_VERSION, 'result_name': name,
        'window_ref': products['window_ref'], 'record_count': products['record_count'],
        'product_count': products['product_count'], 'sku_count': products['sku_count'],
        'category_count': products['category_count'], 'store_record_count': 1,
        'public_text_record_count': texts['record_count'], 'files': list(FILES),
        'coverage_status': 'PARTIAL', 'complete_result_promotion': False,
        'target_system_import_verified': False, 'live_attempts_consumed': 0}
    _validate(manifest, profile.MANIFEST_SCHEMA)
    product_columns, store_columns = previous.csv_fields()
    contents = (base._bytes(products), base._csv_bytes(products['records'], product_columns),
                base._bytes(stores), base._csv_bytes(stores['records'], store_columns),
                base._bytes(texts), base._csv_bytes(texts['records'], TEXT_COLUMNS),
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
            _cleanup(root_fd, result_fd, name)
        for fd in (result_fd, root_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
    return {key: manifest[key] for key in ('result_name', 'record_count', 'product_count',
        'sku_count', 'category_count', 'store_record_count', 'public_text_record_count', 'live_attempts_consumed')} | {
        'code': profile.RESULT_CODE, 'complete_result_promotion': False}


def main():
    return previous.previous.main(_profile=sys.modules[__name__])


if __name__ == '__main__':
    raise SystemExit(main())
