"""Public sharing text and explicit null evidence, excluding personal coupons."""

from collections import Counter
from datetime import datetime
import re
import sys

from . import p31_additional_export as previous
from .p29_store_inventory import _initial, _read_owned, _validate
from .p29_receiver_control import ReceiverControlError
from collection_core.p29 import MAX_COLLECTION_BYTES
from collection_core.result_publisher import _write_file
from parser_candidate import p31_remaining_fields as fields
from parser_candidate.p29_category_profile import CategoryCandidateError

base = previous.base
PRODUCT_SCHEMA = 'p31-business-products-v3.schema.json'
STORE_SCHEMA = 'p31-business-stores-v3.schema.json'
MANIFEST_SCHEMA = 'p31-business-manifest-v3.schema.json'
MANIFEST_VERSION = 'p31-business-manifest/v3'
DICTIONARY_SCHEMA = 'p31-field-dictionary-v2.schema.json'
RESULT_PREFIX = 'p31_remaining_fields_'
RESULT_CODE = 'P31_REMAINING_PUBLIC_FIELDS_EXPORTED'
_NAME = re.compile(r'p31_remaining_fields_[a-f0-9]{32}')
FILES = previous.FILES


def _groups():
    return (('products',fields.PRODUCT_SPECS,fields.PRODUCT_PREFIX),
            ('stores',fields.STORE_SPECS,fields.STORE_PREFIX))


def csv_fields():
    products, stores = map(list, previous.csv_fields())
    for table, specs, _ in _groups():
        destination = products if table == 'products' else stores
        for field, path, _, _ in specs:
            destination.extend((field + '_json' if None in path else field, field + '_state'))
    return tuple(products), tuple(stores)


def _business_view(root, observation_name, input_names):
    products, stores = previous.business_view(root, observation_name, input_names)
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
        additional = by_file[row['source_file']].get((row['category_ref'],row['product_id'],row['sku_id']))
        if additional is None or set(row) & set(additional):
            base._fail('P31_EXPORT_ROW_SOURCE_MISMATCH')
        row.update(additional)
    food = next(o for o in public['observations'] if o['endpoint_id'] == 'FOOD')
    additional = fields.parse_store_fields(food)
    if set(stores['records'][0]) & set(additional):
        base._fail('P31_EXPORT_ROW_SOURCE_MISMATCH')
    stores['records'][0].update(additional)
    products['schema_version'] = 'p31-business-products/v3'
    stores['schema_version'] = 'p31-business-stores/v3'
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
    document = previous.field_dictionary()
    document['schema_version'] = 'p31-field-dictionary/v2'
    definitions = {(r['table'],r['field']):r for r in document['fields']}
    for table, specs, prefix in _groups():
        for field,path,kind,label in specs:
            column = field + '_json' if None in path else field
            for key,title,dtype,path_value,meaning in (
                (column,label,'json-string' if None in path else 'decimal-string' if kind=='integer' else kind,
                 fields.base._canonical(prefix+path),'SOURCE_FIELD_MEANING_NOT_PROMOTED'),
                (field+'_state',label+'：缺失或解析状态','enum-string',None,'PARSER_STATE')):
                definitions[table,key]={'table':table,'field':key,'label_zh':title,'type':dtype,
                    'source_path':path_value,'meaning_status':meaning,
                    'empty_cell':'CONSULT_STATE_COLUMN_OR_SOURCE_BASIS','unit':'NOT_INFERRED'}
    document['fields']=[definitions[table,key] for table,columns in zip(('products','stores'),csv_fields()) for key in columns]
    return document


def coverage_view(products, stores):
    document = previous.coverage_view(products,stores)
    for table,specs,_ in _groups():
        rows=(products if table=='products' else stores)['records']
        for field,_,_,_ in specs:
            counts=Counter(row[field+'_state'] for row in rows)
            document['fields'].append({'table':table,'field':field,'row_count':len(rows),
                                      'states':{state:counts[state] for state in base.STATES}})
    return document


def publish_business_fields(root, observation_name, input_names, result_name=None):
    return previous.publish_business_fields(root,observation_name,input_names,result_name,_profile=sys.modules[__name__])


def main():
    return previous.main(_profile=sys.modules[__name__])


if __name__ == '__main__':
    raise SystemExit(main())
