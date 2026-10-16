"""Own-observation source codes, separate from product and public text tables."""

from collections import Counter
import os
import re
import sys
from uuid import uuid4

from . import p31_initial_relation_export as previous
from .p31_additional_export import main as export_main
from .p29_store_inventory import _initial, _validate
from .p29_receiver_control import ReceiverControlError
from collection_core.p29 import MAX_COLLECTION_BYTES
from collection_core.result_publisher import ResultPublishError, _DIRECTORY_FLAGS, _write_file, precheck_result_destination
from parser_candidate import p31_context_codes as fields
from parser_candidate.p29_category_profile import CategoryCandidateError

base=previous.base
context=previous.previous
CODE_SCHEMA='p31-public-codes-v1.schema.json'
DICTIONARY_SCHEMA='p31-field-dictionary-v4.schema.json'
COVERAGE_SCHEMA='p31-field-coverage-v3.schema.json'
MANIFEST_SCHEMA='p31-business-manifest-v6.schema.json'
MANIFEST_VERSION='p31-business-manifest/v6'
RESULT_CODE='P31_CONTEXT_CODES_EXPORTED'
RESULT_PREFIX='p31_context_codes_'
_NAME=re.compile(r'p31_context_codes_[a-f0-9]{32}')
FILES=('records.json','records.csv','stores.json','stores.csv','public_texts.json','public_texts.csv',
       'public_codes.json','public_codes.csv','field_dictionary.json','coverage.json','manifest.json')
CODE_COLUMNS=('scope','category_ref','category_index','entry_index','field','field_label_zh',
              'source_path','value_type','value','state','endpoint_id','source_file','source_request_ref',
              'observed_at','window_ref')


def business_view(root, observation_name, input_names):
    try:
        products,stores,texts=previous.business_view(root,observation_name,input_names)
        public,_,_,_=_initial(base._root(root),observation_name)
        rows=[]
        for endpoint in ('FOOD','PRODUCTLIST'):
            source=next(o for o in public['observations'] if o['endpoint_id']==endpoint)
            rows.extend({**row,'endpoint_id':endpoint,'source_file':observation_name+'-public-fields.json',
                'source_request_ref':source['source_request_ref'],'observed_at':source['observed_at'],
                'window_ref':products['window_ref']} for row in fields.parse_context_codes(source,endpoint))
        codes={'schema_version':'p31-public-codes/v1','window_ref':products['window_ref'],
               'record_count':len(rows),'records':rows,
               'source_scope':'INITIAL_PAIR_ALLOWLISTED_ROOT_AND_CATEGORY_CODES',
               'copied_into_product_rows':False,'business_semantics_confirmed':False,
               'flags_prove_customer_eligibility':False,'codes_decoded_to_business_meaning':False}
        _validate(codes,CODE_SCHEMA)
        return products,stores,texts,codes
    except (CategoryCandidateError,ReceiverControlError):
        raise
    except (OSError,ValueError,KeyError,TypeError,StopIteration):
        base._fail()


def code_definitions():
    return [{'field':field,'source_path':fields.base._canonical(path),'value_type':kind,'label_zh':label,
             'scope':'FOOD_ROOT' if spec in fields.FOOD_SPECS else 'CATEGORY' if spec in fields.CATEGORY_SPECS else 'PRODUCTLIST_ROOT',
             'endpoint_id':'FOOD' if spec in fields.FOOD_SPECS else 'PRODUCTLIST'}
            for spec in fields.SPECS for field,path,kind,label in (spec,)]


def field_dictionary():
    doc=previous.field_dictionary();doc['schema_version']='p31-field-dictionary/v4'
    old={f['field']:f for f in doc['fields'] if f['table']=='public_texts'}
    for column in CODE_COLUMNS:
        if column=='value_type':
            entry={**old['field'],'field':'value_type','label_zh':'来源标量类型：integer以十进制字符串导出','type':'enum-string'}
        else:
            entry={**old[column]}
            if column=='value':entry.update(label_zh='来源值：结合value_type和state解释',type='source-scalar')
            elif column=='entry_index':entry['label_zh']='原运营项数组索引'
        doc['fields'].append({**entry,'table':'public_codes'})
    doc['public_code_definitions']=code_definitions()
    return doc


def coverage_view(products,stores,texts,codes):
    doc=previous.coverage_view(products,stores,texts);doc['schema_version']='p31-field-coverage/v3'
    for field,_,_,_ in fields.SPECS:
        rows=[r for r in codes['records'] if r['field']==field];counts=Counter(r['state'] for r in rows)
        doc['fields'].append({'table':'public_codes','field':field,'row_count':len(rows),
                              'states':{state:counts[state] for state in base.STATES}})
    return doc


def _cleanup(root_fd,result_fd,name):
    if result_fd is not None:
        for filename in FILES:
            try:os.unlink(filename,dir_fd=result_fd)
            except OSError:pass
    if root_fd is not None:
        try:os.rmdir(name,dir_fd=root_fd)
        except OSError:pass


def csv_fields():
    return context.previous.csv_fields()


def publish_business_fields(root,observation_name,input_names,result_name=None,*,_profile=None):
    profile=_profile if _profile is not None else sys.modules[__name__]
    root=base._root(root)
    name=result_name if result_name is not None else profile.RESULT_PREFIX+uuid4().hex
    if type(name) is not str or profile._NAME.fullmatch(name) is None:base._fail('P31_EXPORT_NAME_INVALID')
    precheck_result_destination(str(root),name)
    products,stores,texts,codes=profile.business_view(root,observation_name,input_names)
    dictionary,coverage=profile.field_dictionary(),profile.coverage_view(products,stores,texts,codes)
    _validate(dictionary,profile.DICTIONARY_SCHEMA);_validate(coverage,profile.COVERAGE_SCHEMA)
    manifest={'schema_version':profile.MANIFEST_VERSION,'result_name':name,
        'window_ref':products['window_ref'],'record_count':products['record_count'],
        'product_count':products['product_count'],'sku_count':products['sku_count'],
        'category_count':products['category_count'],'store_record_count':1,
        'public_text_record_count':texts['record_count'],'public_code_record_count':codes['record_count'],
        'files':list(FILES),'coverage_status':'PARTIAL','complete_result_promotion':False,
        'target_system_import_verified':False,'live_attempts_consumed':0}
    _validate(manifest,profile.MANIFEST_SCHEMA)
    product_columns,store_columns=profile.csv_fields()
    contents=(base._bytes(products),base._csv_bytes(products['records'],product_columns),
              base._bytes(stores),base._csv_bytes(stores['records'],store_columns),
              base._bytes(texts),base._csv_bytes(texts['records'],context.TEXT_COLUMNS),
              base._bytes(codes),base._csv_bytes(codes['records'],CODE_COLUMNS),
              base._bytes(dictionary),base._bytes(coverage),base._bytes(manifest))
    if sum(map(len,contents))>profile.MAX_COLLECTION_BYTES:base._fail('P31_EXPORT_BUDGET')
    root_fd=result_fd=None;created=success=False
    try:
        root_fd=os.open(root,_DIRECTORY_FLAGS);os.mkdir(name,0o700,dir_fd=root_fd);created=True
        result_fd=os.open(name,_DIRECTORY_FLAGS,dir_fd=root_fd)
        for filename,content in zip(FILES,contents):profile._write_file(result_fd,filename,content)
        os.fsync(result_fd);os.fsync(root_fd);success=True
    except FileExistsError:raise ResultPublishError('RESULT_TARGET_EXISTS') from None
    except OSError:raise ResultPublishError('RESULT_PUBLISH_FAILED') from None
    finally:
        if created and not success:_cleanup(root_fd,result_fd,name)
        for fd in (result_fd,root_fd):
            if fd is not None:
                try:os.close(fd)
                except OSError:pass
    return {key:manifest[key] for key in ('result_name','record_count','product_count','sku_count',
        'category_count','store_record_count','public_text_record_count','public_code_record_count','live_attempts_consumed')} | {
        'code':profile.RESULT_CODE,'complete_result_promotion':False}


def main():
    return export_main(_profile=sys.modules[__name__])


if __name__=='__main__':
    raise SystemExit(main())
