"""Bounded own-source field enrichment; no acquisition or qualification change."""

import argparse
from collections import Counter
from datetime import datetime
import csv
import io
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from collection_core.p29 import MAX_COLLECTION_BYTES
from collection_core.result_publisher import (
    ResultPublishError, _DIRECTORY_FLAGS, _write_file,
    precheck_result_destination,
)
from parser_candidate.p29_category_profile import CategoryCandidateError
from .p29_store_inventory import (
    CSV_PRICE_RULE_FIELDS, _initial, _read_owned, _root, _validate,
    initial_price_rules_inventory_view,
)
from .p29_category_export import _bytes
from .p29_receiver_control import ReceiverControlError

_NAME = re.compile(r'p31_public_fields_[a-f0-9]{32}')
PRODUCT_SCHEMA = 'p31-business-products-v1.schema.json'
STORE_SCHEMA = 'p31-business-stores-v1.schema.json'
FILES = ('records.json', 'records.csv', 'stores.json', 'stores.csv',
         'field_dictionary.json', 'coverage.json', 'manifest.json')
STATES = ('NOT_OBSERVED', 'SOURCE_NULL', 'SOURCE_EMPTY', 'PRESENT_UNCONFIRMED',
          'NEGATIVE_SEMANTICS_UNCONFIRMED')
STORE_ID_FIELDS = ('store_id', 'store_name', 'source_file', 'source_request_ref', 'observed_at', 'window_ref')
ATTRIBUTE_CSV_FIELDS = ('product_attributes_json', 'product_attributes_state')


def _cleanup_created_result(root_fd, result_fd, result_name):
    # The generic publisher owns three filenames; this bundle owns seven.
    # Only clean this invocation's exclusively created destination.
    if result_fd is not None:
        for name in FILES:
            try:
                os.unlink(name, dir_fd=result_fd)
            except OSError:
                pass
    if root_fd is not None:
        try:
            os.rmdir(result_name, dir_fd=root_fd)
        except OSError:
            pass


def _parser():
    from parser_candidate import p31_public_fields
    return p31_public_fields


def _fail(code='P31_EXPORT_INPUT_INVALID'):
    raise CategoryCandidateError(code)


def _extra_columns(specs):
    return tuple(key for field, _, _ in specs for key in (field, field + '_state'))


def csv_fields():
    p = _parser()
    return (CSV_PRICE_RULE_FIELDS + _extra_columns(p.PRODUCT_SPECS + p.SKU_SPECS) + ATTRIBUTE_CSV_FIELDS,
            STORE_ID_FIELDS + _extra_columns(p.STORE_SPECS))


def _cell(value):
    if value is None:
        return ''
    if type(value) is bool:
        return 'true' if value else 'false'
    return str(value)


def _csv_bytes(rows, fields):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n', extrasaction='raise')
    writer.writeheader()
    writer.writerows({key: _cell(row[key]) for key in fields} for row in rows)
    return stream.getvalue().encode('utf-8')


def _business_view(root, observation_name, input_names):
    p = _parser()
    base, _, _ = initial_price_rules_inventory_view(root, observation_name, input_names)
    root = _root(root)
    public, product, _, _ = _initial(root, observation_name)
    initial_name = observation_name + '-public-fields.json'
    by_file = {initial_name: p.parse_product_fields(product)}
    same_time = {}
    # Recheck every supplied observation, including equal-time rows the v4
    # price-only comparison could deduplicate before seeing these new fields.
    for name in input_names:
        source = _read_owned(root / name, 4 * 1024 * 1024)
        parsed = p.parse_product_fields(source['public_analysis'])
        by_file[name] = parsed
        at = datetime.fromisoformat(source['observed_at'].replace('Z', '+00:00'))
        for identity, extras in parsed.items():
            key = (at, identity[0], identity[2])
            signature = (identity[1], extras)
            if key in same_time and same_time[key] != signature:
                _fail('P31_EXPORT_EQUAL_TIME_FIELDS_CONFLICT')
            same_time[key] = signature
    records = []
    for old in base['records']:
        identity = (old['category_ref'], old['product_id'], old['sku_id'])
        extras = by_file[old['source_file']].get(identity)
        if extras is None or set(extras) & set(old):
            _fail('P31_EXPORT_ROW_SOURCE_MISMATCH')
        records.append({**old, **extras})
    products = {**base, 'schema_version': 'p31-business-products/v1', 'records': records,
                'extended_fields_are_source_observations': True,
                'extended_business_semantics_confirmed': False}
    food = next(item for item in public['observations'] if item['endpoint_id'] == 'FOOD')
    identity_values = {tuple(v['coordinates']): v['value'] for v in food['public_values']
                       if v['path'] in ('$.data.poi_info.poi_id_str', '$.data.poi_info.name')}
    store = {'store_id': identity_values[('data', 'poi_info', 'poi_id_str')],
             'store_name': identity_values[('data', 'poi_info', 'name')],
             'source_file': initial_name, 'source_request_ref': food['source_request_ref'],
             'observed_at': food['observed_at'], 'window_ref': base['window_ref'],
             **p.parse_store_fields(food)}
    stores = {'schema_version': 'p31-business-stores/v1', 'window_ref': base['window_ref'],
              'record_count': 1, 'records': [store], 'values_are_observed_at_source_time': True,
              'store_values_copied_into_product_rows': False,
              'delivery_terms_apply_to_all_customers': False, 'amount_unit_inferred': False,
              'business_semantics_confirmed': False}
    _validate(products, PRODUCT_SCHEMA)
    _validate(stores, STORE_SCHEMA)
    return products, stores


def business_view(root, observation_name, input_names):
    try:
        return _business_view(root, observation_name, input_names)
    except (CategoryCandidateError, ReceiverControlError):
        raise
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        _fail()


_BASE_LABELS = {
    'category_reference_label': '分类参考名称', 'product_name': '商品名称',
    'sku_spec': 'SKU规格名称', 'sku_description': 'SKU规格说明（spec_desc）',
    'product_unit': '商品计量文字', 'category_ref': '分类编号', 'product_id': '商品编号',
    'sku_id': 'SKU编号', 'sku_price_number': '来源SKU价格数字',
    'product_min_price_number': '来源商品最低价数字', 'sku_origin_number': '来源SKU原价数字',
    'render_origin_number': '来源渲染原价数字',
    'product_full_discount_price_number': '商品full_discount_price数字',
    'sku_member_price_number': 'SKU会员价来源数字',
    'sku_full_discount_price_number': 'SKU full_discount_price数字', 'sku_box_price_number': 'SKU包装费来源数字',
    'min_price_tail': '最低价尾部说明', 'render_price_desc': '商品价格说明', 'sku_price_desc': 'SKU价格说明',
    'currency': '币种，仅采用该行已有确认依据', 'amount_unit': '金额单位，仅采用该行已有确认依据',
    'currency_status': '币种确认状态', 'amount_unit_status': '金额单位确认状态',
    'currency_basis': '币种确认依据', 'amount_unit_basis': '金额单位确认依据',
    'source_kind': '初始已核对行或分类候选行', 'source_file': '该行自身公开投影文件',
    'source_request_ref': '该行自身来源请求引用', 'observed_at': '该行自身观察时间',
    'window_ref': '窗口引用，用于关联本包来源', 'sku_price_source': 'SKU价格来源依据',
    'numeric_min_relation': '最低价数字关系核对状态', 'product_unit_role': '商品计量文字角色',
    'category_label_source_file': '分类参考名称的来源文件',
    'category_label_source_request_ref': '分类参考名称的请求引用',
    'category_label_observed_at': '分类参考名称的观察时间',
    'product_discount_by_count_scope': '商品数量折扣适用对象',
    'sku_discount_by_count_scope': 'SKU数量折扣适用对象',
    'product_discount_by_count_count_number': '商品数量折扣的数量条件数字',
    'product_discount_by_count_discount_number': '商品数量折扣数字，算法未确认',
    'sku_discount_by_count_count_number': 'SKU数量折扣的数量条件数字',
    'sku_discount_by_count_discount_number': 'SKU数量折扣数字，算法未确认',
    'product_max_discount_number': '商品max_discount来源数字',
    'product_preferential_feeling_price_number': '商品优惠体感价来源数字',
    'product_coupon_count_number': '商品coupon_count来源数字',
    'product_coupons_per_price_number': '商品coupons_per_price来源数字',
    'product_multi_activity_price_number': '商品multi_activity_price来源数字',
    'product_show_origin_price_number': '商品show_origin_price来源数字',
    'product_discount_tag_text': '商品优惠标签文字',
    'sku_ladder_package_food_num_number': 'SKU阶梯包装数量条件数字',
    'sku_ladder_package_price_number': 'SKU阶梯包装费用来源数字',
    'sku_full_discount_tag_texts_json': 'SKU优惠文本分组JSON，保留标签与子标签索引',
    'product_attributes_json': '商品属性分组JSON，不代表已选SKU组合',
    'store_id': '门店公开编号', 'store_name': '门店名称',
}
_PATH_LABELS = {
    'description': '说明文字', 'month_saled': '月销量来源数字（精确口径未确认）',
    'status': '状态码（枚举含义未确认）', 'status_description': '状态说明文字',
    'stock': 'stock库存来源数字（哨兵含义未确认）', 'real_stock': 'real_stock库存来源数字（哨兵含义未确认）',
    'has_food': 'has_food来源标记', 'forbid_single_buy': '禁止单购来源说明',
    'sku_label': '规格标签', 'activity_tag': '活动标签', 'activity_type': '活动类型码',
    'has_multi_sale_attr': '多销售属性标记', 'spec_info': '规格补充说明',
    'min_order_count': '起购数量来源数字', 'restrict': '限制数量来源数字',
    'count': 'count来源数字', 'box_num': '包装数量来源数字', 'promotion_info': '促销补充说明',
    'promotion_text': '促销文字', 'restrict_text': '促销限制文字', 'addition_text': '促销附加文字',
    'address': '公开营业地址', 'bulletin': '门店公告', 'shipping_time': 'shipping_time来源文字（不推定营业时段）',
    'min_price_tip': '最低金额说明', 'shipping_fee_tip': '配送费说明',
    'origin_shipping_fee_tip': '原配送费说明', 'delivery_time_tip': '配送时间说明',
    'delivery_tips': '配送提示', 'app_delivery_tip': '配送服务说明', 'poi_prepare_time': '备餐时间来源文字',
    'poi_sell_status': '门店销售状态码', 'score': 'score评分来源数字',
    'wm_poi_score': '外卖评分来源数字', 'dp_score': '点评评分来源数字',
    'comment_number': '评论数量来源数字', 'dp_comment_number': '点评数量来源数字',
    'avg_delivery_time': '平均配送时间来源数字（单位未确认）',
    'min_price': '门店最低金额来源数字（单位及条件未确认）',
    'shipping_fee': '配送费来源数字（单位及条件未确认）',
    'shippingReduceFee': '配送减免来源数字（单位及条件未确认）',
    'delivery_type': '配送类型码', 'shipping_fee_type': '配送费类型码',
    'invoice_support': '发票支持来源码', 'is_meituan_delivery': '美团配送来源标记',
}


def _base_label(field):
    if field in _BASE_LABELS:
        return _BASE_LABELS[field]
    if field.endswith('_pair_state'):
        return ('商品' if field.startswith('product') else 'SKU') + '数量条件配对状态，仅说明键是否同时出现'
    if field.endswith('_state'):
        stem = field[:-6]
        label = _BASE_LABELS.get(stem) or _BASE_LABELS.get(stem + '_number') or _BASE_LABELS.get(stem + '_json')
        if label:
            return label + '：缺失或解析状态'
    _fail('P31_FIELD_DICTIONARY_LABEL_MISSING')


def field_dictionary():
    parser = _parser()
    product_fields, store_fields = csv_fields()
    definitions = {}
    for scope, specs, prefix in (
            ('products', parser.PRODUCT_SPECS, '$.data.food_spu_tags[].dynamic_spus[]'),
            ('products', parser.SKU_SPECS, '$.data.food_spu_tags[].dynamic_spus[].skus[]'),
            ('stores', parser.STORE_SPECS, '$.data.poi_info')):
        for field, path, kind in specs:
            label = ('门店' if scope == 'stores' else 'SKU' if specs is parser.SKU_SPECS else '商品') + _PATH_LABELS[path[-1]]
            definitions[scope, field] = (label, 'decimal-string' if kind in ('number', 'integer') else kind,
                                         prefix + '.' + '.'.join(path), 'SOURCE_FIELD_MEANING_NOT_PROMOTED')
            definitions[scope, field + '_state'] = (label + '：缺失或解析状态', 'enum-string', None, 'PARSER_STATE')
    rows = []
    for table, fields in (('products', product_fields), ('stores', store_fields)):
        for field in fields:
            if (table, field) in definitions:
                label, kind, path, semantics = definitions[table, field]
            else:
                label = _base_label(field)
                kind = ('json-string' if field.endswith('_json') else 'decimal-string'
                        if field.endswith('_number') else 'string')
                path = None
                semantics = 'EXISTING_V4_FIELD' if field in CSV_PRICE_RULE_FIELDS else 'SOURCE_REFERENCE'
            rows.append({'table': table, 'field': field, 'label_zh': label, 'type': kind,
                         'source_path': path, 'meaning_status': semantics,
                         'empty_cell': 'CONSULT_STATE_COLUMN_OR_SOURCE_BASIS', 'unit': 'NOT_INFERRED'})
    return {'schema_version': 'p31-field-dictionary/v1', 'encoding': 'UTF-8', 'delimiter': ',',
            'boolean_cells': ['true', 'false'], 'identifier_import_type': 'TEXT',
            'json_columns_require_json_decode': True, 'target_system_import_verified': False,
            'fields': rows}


def coverage_view(products, stores):
    p = _parser()
    coverage = []
    for table, rows, specs in (('products', products['records'], p.PRODUCT_SPECS + p.SKU_SPECS),
                               ('stores', stores['records'], p.STORE_SPECS)):
        for field, _, _ in specs:
            counts = Counter(row[field + '_state'] for row in rows)
            coverage.append({'table': table, 'field': field, 'row_count': len(rows),
                             'states': {state: counts[state] for state in STATES}})
    return {'schema_version': 'p31-field-coverage/v1', 'counts_are_output_rows_not_unique_objects': True,
            'fields': coverage,
            'not_inferred': ['SOLD_OUT_FROM_STATUS_CODE', 'UNLIMITED_STOCK_FROM_NEGATIVE',
                             'PRECISE_SALES_WINDOW', 'ATTRIBUTE_OPTIONS_ARE_SKU_COMBINATIONS',
                             'BUSINESS_HOURS_FROM_SHIPPING_TIME', 'DELIVERY_TIME_OR_AMOUNT_UNIT'],
            'excluded': ['PRIVATE_OR_CUSTOMER_LOCATION', 'PERSONAL_ELIGIBILITY', 'URL_OR_IMAGES',
                         'STYLE_OR_TRACKING_FIELDS'],
            'source_scope': 'EXISTING_APPROVED_WINDOW_PUBLIC_PROJECTIONS',
            'all_business_fields_complete': False, 'target_system_import_verified': False}


def publish_business_fields(root, observation_name, input_names, result_name=None):
    root = _root(root)
    name = result_name if result_name is not None else 'p31_public_fields_' + uuid4().hex
    if type(name) is not str or _NAME.fullmatch(name) is None:
        _fail('P31_EXPORT_NAME_INVALID')
    precheck_result_destination(str(root), name)
    products, stores = business_view(root, observation_name, input_names)
    product_fields, store_fields = csv_fields()
    dictionary, coverage = field_dictionary(), coverage_view(products, stores)
    _validate(dictionary, 'p31-field-dictionary-v1.schema.json')
    _validate(coverage, 'p31-field-coverage-v1.schema.json')
    manifest = {'schema_version': 'p31-business-manifest/v1', 'result_name': name,
                'window_ref': products['window_ref'], 'record_count': products['record_count'],
                'product_count': products['product_count'], 'sku_count': products['sku_count'],
                'category_count': products['category_count'], 'store_record_count': 1, 'files': list(FILES),
                'coverage_status': 'PARTIAL', 'complete_result_promotion': False,
                'target_system_import_verified': False, 'live_attempts_consumed': 0}
    _validate(manifest, 'p31-business-manifest-v1.schema.json')
    contents = (_bytes(products), _csv_bytes(products['records'], product_fields),
                _bytes(stores), _csv_bytes(stores['records'], store_fields),
                _bytes(dictionary), _bytes(coverage), _bytes(manifest))
    if sum(map(len, contents)) > MAX_COLLECTION_BYTES:
        _fail('P31_EXPORT_BUDGET')
    root_fd = result_fd = None
    created = success = False
    try:
        root_fd = os.open(root, _DIRECTORY_FLAGS)
        os.mkdir(name, 0o700, dir_fd=root_fd)
        created = True
        result_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        for filename, content in zip(FILES, contents):
            _write_file(result_fd, filename, content)
        os.fsync(result_fd)
        os.fsync(root_fd)
        success = True
    except FileExistsError:
        raise ResultPublishError('RESULT_TARGET_EXISTS') from None
    except OSError:
        raise ResultPublishError('RESULT_PUBLISH_FAILED') from None
    finally:
        if created and not success:
            _cleanup_created_result(root_fd, result_fd, name)
        for fd in (result_fd, root_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
    return {key: manifest[key] for key in ('result_name', 'record_count', 'product_count',
            'sku_count', 'category_count', 'store_record_count', 'live_attempts_consumed')} | {
                'code': 'P31_PUBLIC_FIELDS_EXPORTED', 'complete_result_promotion': False}


class _Arguments(argparse.ArgumentParser):
    def error(self, message):
        _fail('P31_EXPORT_ARGUMENTS_INVALID')


def main():
    parser = _Arguments()
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--observation-name', required=True)
    parser.add_argument('--input-name', action='append', required=True)
    parser.add_argument('--result-name')
    try:
        args = parser.parse_args()
        result = publish_business_fields(Path(args.output_root), args.observation_name, args.input_name, args.result_name)
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
