"""Apply explicit user currency/unit evidence to an exact existing result."""

import json
import os
from pathlib import Path
import re
import stat
import sys

from . import p31_context_codes_export as previous
from .p31_additional_export import main as export_main
from .p29_store_inventory import _read_owned, _validate
from .p29_receiver_control import ReceiverControlError
from parser_candidate.p29_category_profile import CategoryCandidateError

base=previous.base
PRODUCT_SCHEMA='p31-business-products-v5.schema.json'
STORE_SCHEMA='p31-business-stores-v4.schema.json'
DICTIONARY_SCHEMA='p31-field-dictionary-v5.schema.json'
COVERAGE_SCHEMA='p31-field-coverage-v4.schema.json'
MANIFEST_SCHEMA='p31-business-manifest-v7.schema.json'
MANIFEST_VERSION='p31-business-manifest/v7'
CONFIRMATION_SCHEMA='p31-user-amount-confirmation-v1.schema.json'
RESULT_PREFIX='p31_confirmed_units_'
RESULT_CODE='P31_USER_CONFIRMED_UNITS_EXPORTED'
_NAME=re.compile(r'p31_confirmed_units_[a-f0-9]{32}')
FILES=previous.FILES
MAX_COLLECTION_BYTES=previous.MAX_COLLECTION_BYTES
_write_file=previous._write_file
CONFIRMATION_FILE=Path(__file__).resolve().parents[1]/'docs/harness/reports/P31-user-amount-confirmation.json'
CONFIRMATION_REF='user-confirmation:p31-cny-yuan'
UNIT_STATUS='USER_CONFIRMED_FOR_CURRENT_RESULT'
UNIT_BASIS='EXPLICIT_USER_CONFIRMATION_CNY_YUAN'
PRODUCT_AMOUNT_FIELDS=('sku_price_number','product_min_price_number','sku_origin_number','render_origin_number',
    'product_full_discount_price_number','sku_member_price_number','sku_full_discount_price_number',
    'sku_box_price_number','sku_ladder_package_price_number','product_preferential_feeling_price_number',
    'product_multi_activity_price_number')
STORE_AMOUNT_FIELDS=('store_min_price_number','store_shipping_fee_number','store_shipping_reduce_fee_number')
PRODUCT_NEW_COLUMNS=('prior_currency_status','prior_amount_unit_status','amount_confirmation_ref')
STORE_NEW_COLUMNS=('currency','amount_unit','currency_status','amount_unit_status','currency_basis','amount_unit_basis','amount_confirmation_ref')


def _confirmation():
    try:
        doc=json.loads(CONFIRMATION_FILE.read_text())
        _validate(doc,CONFIRMATION_SCHEMA)
        return doc
    except (OSError,ValueError,TypeError):
        base._fail('P31_AMOUNT_CONFIRMATION_INVALID')


def amount_fields():
    return {'products':list(PRODUCT_AMOUNT_FIELDS),'stores':list(STORE_AMOUNT_FIELDS)}


def csv_fields():
    products,stores=previous.csv_fields()
    return products+PRODUCT_NEW_COLUMNS,stores+STORE_NEW_COLUMNS


def business_view(root, observation_name, input_names):
    try:
        confirmation=_confirmation();_validate(confirmation,CONFIRMATION_SCHEMA)
        products,stores,texts,codes=previous.business_view(root,observation_name,input_names)
        if products['window_ref']!=confirmation['window_ref']:
            base._fail('P31_AMOUNT_CONFIRMATION_SCOPE_MISMATCH')
        source=base._root(root)/confirmation['input_result_name']
        info=source.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
            base._fail('P31_AMOUNT_CONFIRMATION_SCOPE_MISMATCH')
        manifest=_read_owned(source/'manifest.json',8*1024*1024)
        _validate(manifest,previous.MANIFEST_SCHEMA)
        if (manifest['result_name']!=confirmation['input_result_name'] or manifest['window_ref']!=confirmation['window_ref']
            or _read_owned(source/'records.json',8*1024*1024)!=products
            or _read_owned(source/'stores.json',8*1024*1024)!=stores):
            base._fail('P31_AMOUNT_CONFIRMATION_SCOPE_MISMATCH')
        for row in products['records']:
            row.update(prior_currency_status=row['currency_status'],prior_amount_unit_status=row['amount_unit_status'],
                       amount_confirmation_ref=CONFIRMATION_REF)
            if row['source_kind']=='PARTIAL_CATEGORY_CANDIDATE':
                row.update(currency='CNY',amount_unit='YUAN',currency_status=UNIT_STATUS,amount_unit_status=UNIT_STATUS,
                           currency_basis=UNIT_BASIS,amount_unit_basis=UNIT_BASIS)
        for row in stores['records']:
            row.update(currency='CNY',amount_unit='YUAN',currency_status=UNIT_STATUS,amount_unit_status=UNIT_STATUS,
                       currency_basis=UNIT_BASIS,amount_unit_basis=UNIT_BASIS,amount_confirmation_ref=CONFIRMATION_REF)
        products['schema_version']='p31-business-products/v5';stores['schema_version']='p31-business-stores/v4'
        for doc in (products,stores):
            doc['user_amount_confirmation']=confirmation
            doc['confirmed_amount_fields']=amount_fields()
        _validate(products,PRODUCT_SCHEMA);_validate(stores,STORE_SCHEMA)
        return products,stores,texts,codes
    except (CategoryCandidateError,ReceiverControlError):raise
    except (OSError,ValueError,KeyError,TypeError):base._fail('P31_AMOUNT_CONFIRMATION_SCOPE_MISMATCH')


def field_dictionary():
    doc=previous.field_dictionary();doc['schema_version']='p31-field-dictionary/v5'
    for entry in doc['fields']:
        if entry['field'] in amount_fields().get(entry['table'],[]):
            entry['unit']='USER_CONFIRMED_CNY_YUAN'
            entry['label_zh']=entry['label_zh'].replace('单位及条件未确认','单位确认为元，条件未确认')
    labels={'prior_currency_status':'用户确认前的币种状态','prior_amount_unit_status':'用户确认前的金额单位状态',
            'amount_confirmation_ref':'当前结果的用户金额单位确认引用','currency':'币种','amount_unit':'金额单位',
            'currency_status':'币种确认状态','amount_unit_status':'金额单位确认状态',
            'currency_basis':'币种确认依据','amount_unit_basis':'金额单位确认依据'}
    for table,columns in [('products',PRODUCT_NEW_COLUMNS),('stores',STORE_NEW_COLUMNS)]:
        for field in columns:
            doc['fields'].append({'table':table,'field':field,'label_zh':labels[field],'type':'enum-string','source_path':None,
                'meaning_status':'USER_CONFIRMATION_EVIDENCE','empty_cell':'CONSULT_STATE_COLUMN_OR_SOURCE_BASIS','unit':'NOT_INFERRED'})
    # Keep each table's dictionary order identical to its CSV header.
    lookup={(f['table'],f['field']):f for f in doc['fields']}
    p,s=csv_fields()
    doc['fields']=[lookup[table,col] for table,cols in [('products',p),('stores',s),('public_texts',previous.context.TEXT_COLUMNS),('public_codes',previous.CODE_COLUMNS)] for col in cols]
    doc['user_amount_confirmation']=_confirmation();doc['confirmed_amount_fields']=amount_fields()
    return doc


def coverage_view(products,stores,texts,codes):
    doc=previous.coverage_view(products,stores,texts,codes);doc['schema_version']='p31-field-coverage/v4'
    doc['user_amount_confirmation']=products['user_amount_confirmation'];doc['confirmed_amount_fields']=amount_fields()
    return doc


def publish_business_fields(root,observation_name,input_names,result_name=None):
    return previous.publish_business_fields(root,observation_name,input_names,result_name,_profile=sys.modules[__name__])


def main():
    return export_main(_profile=sys.modules[__name__])


if __name__=='__main__':raise SystemExit(main())
