"""A category-ordered view of one window's already approved public input.

Category labels are explicit references to that window's initial list. Prices,
names and specifications always come from the selected row's own response.
This partial inventory does not replace or qualify complete business records.
"""

import argparse
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
import csv
import io
import json
import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource

from collection_core.p29 import MAX_COLLECTION_BYTES, MAX_ROWS
from collection_core.result_publisher import (
    ResultPublishError, _DIRECTORY_FLAGS, _cleanup_created_result, _write_file,
    precheck_result_destination,
)
from parser_candidate.p29_category_profile import CategoryCandidateError, parse_category_public_values
from parser_candidate.p29_category_price import parse_category_price
from parser_candidate.p29_price_rules import (
    PROFILE_KIND as RULE_PROFILE_KIND, RULE_EXPORT_FIELDS, VERSION as RULE_VERSION,
    columns_from_row, indexed_text_records, parse_price_rules,
)
from .p26_identification_host import _read_owned
from collection_core.p29_source_association import p29_association_ready
from .p29_category_export import _view as candidate_view, _bytes, price_view
from .p29_receiver_control import _root, ReceiverControlError

CSV_FIELDS = (
    'category_reference_label', 'product_name', 'sku_spec', 'sku_price_number',
    'product_min_price_number', 'product_unit', 'sku_description', 'sku_origin_number',
    'currency', 'amount_unit', 'source_kind', 'category_ref', 'product_id', 'sku_id',
    'sku_spec_state', 'sku_description_state', 'product_unit_state',
    'source_file', 'source_request_ref', 'observed_at',
    'category_label_source_file', 'category_label_source_request_ref',
    'category_label_observed_at', 'window_ref',
)
_OBSERVATION = re.compile(r'observation_[a-f0-9]{32}')
_NAME = re.compile(r'store_inventory_[a-f0-9]{32}')
_PRICE_NAME = re.compile(r'store_price_inventory_[a-f0-9]{32}')
_RULES_NAME = re.compile(r'store_price_rules_[a-f0-9]{32}')
_INITIAL_RULES_NAME = re.compile(r'store_initial_price_rules_[a-f0-9]{32}')
_PRICE_GAPS = (
    ('render_origin_number', 'render_origin_state'),
    ('product_full_discount_price_number', 'product_full_discount_price_state'),
    ('sku_member_price_number', 'sku_member_price_state'),
    ('sku_full_discount_price_number', 'sku_full_discount_price_state'),
    ('sku_box_price_number', 'sku_box_price_state'),
    ('min_price_tail', 'min_price_tail_state'),
    ('render_price_desc', 'render_price_desc_state'),
    ('sku_price_desc', 'sku_price_desc_state'),
)
CSV_PRICE_FIELDS = (
    'category_reference_label', 'product_name', 'sku_spec', 'sku_price_number',
    'product_min_price_number', 'sku_origin_number', 'product_unit', 'sku_description',
    'currency', 'amount_unit', 'currency_status', 'amount_unit_status',
    'currency_basis', 'amount_unit_basis', 'sku_price_source', 'numeric_min_relation',
    'product_unit_role', 'render_origin_number', 'render_origin_state',
    'product_full_discount_price_number', 'product_full_discount_price_state',
    'sku_member_price_number', 'sku_member_price_state',
    'sku_full_discount_price_number', 'sku_full_discount_price_state',
    'sku_box_price_number', 'sku_box_price_state',
    'min_price_tail', 'min_price_tail_state',
    'render_price_desc', 'render_price_desc_state',
    'sku_price_desc', 'sku_price_desc_state',
    'source_kind', 'category_ref', 'product_id', 'sku_id',
    'sku_spec_state', 'sku_description_state', 'product_unit_state',
    'source_file', 'source_request_ref', 'observed_at',
    'category_label_source_file', 'category_label_source_request_ref',
    'category_label_observed_at', 'window_ref',
)
_KIND_AT = CSV_PRICE_FIELDS.index('source_kind')
CSV_PRICE_RULE_FIELDS = CSV_PRICE_FIELDS[:_KIND_AT] + RULE_EXPORT_FIELDS + CSV_PRICE_FIELDS[_KIND_AT:]


def _fail(code='P29_INVENTORY_INPUT_INVALID'):
    raise CategoryCandidateError(code)


def _validate(document, name):
    schemas = Path(__file__).resolve().parents[1] / 'contracts/schemas'
    resources = {p.name: Resource.from_contents(json.loads(p.read_text()))
                 for p in schemas.glob('*.schema.json')}
    def local(uri):
        if uri in resources:
            return resources[uri]
        raise NoSuchResource(ref=uri)
    registry = Registry(retrieve=local).with_resources(resources.items())
    validator = Draft202012Validator(json.loads((schemas / name).read_text()),
        registry=registry, format_checker=FormatChecker())
    if not validator.is_valid(document):
        _fail()


def _initial(root, observation_name):
    if type(observation_name) is not str or _OBSERVATION.fullmatch(observation_name) is None:
        _fail()
    metadata = (root / observation_name).lstat()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700):
        _fail()
    source_name = observation_name + '-public-fields.json'
    public = _read_owned(root / source_name, 4 * 1024 * 1024)
    complete = _read_owned(root / observation_name / 'records.json', 4 * 1024 * 1024)
    schemas = {'p28-public-business-batch/v1': 'p28-public-business-batch-v1.schema.json',
               'p29-public-business-batch/v1': 'p29-public-business-batch-v1.schema.json'}
    if public.get('schema_version') not in schemas:
        _fail()
    _validate(public, schemas[public['schema_version']])
    _validate(complete, 'p28-result-view-v1.schema.json')
    if (not p29_association_ready(public['source_association'])
            or public['source_association']['window_ref'] != public['window_ref']):
        _fail('P29_INVENTORY_SOURCE_MISMATCH')
    observations = {o['endpoint_id']: o for o in public['observations']}
    if set(observations) != {'FOOD', 'PRODUCTLIST'}:
        _fail()
    food, product = observations['FOOD'], observations['PRODUCTLIST']
    times = [datetime.fromisoformat(o['observed_at']) for o in (food, product)]
    if (any(t.utcoffset() is None for t in times)
            or abs((times[0] - times[1]).total_seconds()) > 10
            or food['source_request_ref'] == product['source_request_ref']):
        _fail('P29_INVENTORY_SOURCE_MISMATCH')
    merchant = {}
    for v in food['public_values']:
        if v['path'] not in {'$.data.poi_info.poi_id_str', '$.data.poi_info.name'}:
            continue
        c = v['coordinates']
        if (c not in (['data', 'poi_info', 'poi_id_str'], ['data', 'poi_info', 'name'])
                or v['path'] != '$.' + '.'.join(c) or c[-1] in merchant
                or type(v['value']) is not str or not v['value']):
            _fail()
        merchant[c[-1]] = v['value']
    if set(merchant) != {'poi_id_str', 'name'}:
        _fail()
    values = {}
    for v in product['public_values']:
        if v['path'] not in {'$.data.food_spu_tags[].tag', '$.data.food_spu_tags[].name'}:
            continue
        c = v['coordinates']
        if (len(c) != 4 or c[:2] != ['data', 'food_spu_tags']
                or type(c[2]) is not int or not 0 <= c[2] < 256
                or c[3] not in {'tag', 'name'} or tuple(c) in values
                or v['path'] != '$.data.food_spu_tags[].' + c[3]
                or type(v['value']) is not str or not v['value']
                or any(x in v['value'] for x in ('\r', '\n', '\0', '://'))):
            _fail()
        values[tuple(c)] = v['value']
    categories = []
    for i in sorted({c[2] for c in values}):
        prefix = ('data', 'food_spu_tags', i)
        if prefix + ('tag',) not in values or prefix + ('name',) not in values:
            _fail()
        categories.append({'category_ref': values[prefix + ('tag',)],
            'category_reference_label': values[prefix + ('name',)], 'source_index': i,
            'source_file': source_name, 'source_request_ref': product['source_request_ref'],
            'observed_at': product['observed_at'], 'label_kind': 'REFERENCED_INITIAL_LIST_LABEL'})
    if not categories or len({c['category_ref'] for c in categories}) != len(categories):
        _fail()
    raw_rows = parse_category_public_values(product)
    own = {(r.category_ref, r.sku_id): r for r in raw_rows}
    if len(own) != len(raw_rows) or len(complete['records']) != len(raw_rows):
        _fail('P29_INVENTORY_SOURCE_MISMATCH')
    seen = set()
    category_names = {c['category_ref']: c['category_reference_label'] for c in categories}
    for row in complete['records']:
        key = (row['category_ref'], row['sku_id'])
        if key not in own or key in seen:
            _fail('P29_INVENTORY_SOURCE_MISMATCH')
        seen.add(key); source = own[key]
        if (row['product_id'] != source.product_id or row['product'] != source.product_name
                or row['store_id'] != merchant['poi_id_str'] or row['store'] != merchant['name']
                or row['category_name'] != category_names.get(source.category_ref)
                or row['observed_at'] != product['observed_at']
                or Decimal(row['sku_price_yuan']) != Decimal(source.sku_price_number)
                or Decimal(row['product_display_price_yuan']) != Decimal(source.product_min_price_number)
                or Decimal(source.product_min_price_number) != Decimal(source.render_min_price_number)
                or row['sku_spec'] != (source.sku_spec or '')
                or row['sku_description'] != (source.sku_description or '')
                or row['product_unit_text'] != (source.product_unit or '')
                or row['source_origin_price_number'] != (source.sku_origin_number or '')):
            _fail('P29_INVENTORY_SOURCE_MISMATCH')
    return public, product, categories, raw_rows


def _inventory_view(root, observation_name, input_names):
    root = _root(root)
    candidates, _, _ = candidate_view(root, input_names)
    public, product, categories, initial_rows = _initial(root, observation_name)
    window = public['window_ref']
    if (candidates['window_ref'] != window or any(
            s['source_context_result_name'] != observation_name
            or s['source_context_observed_at'] != next(
                o['observed_at'] for o in public['observations'] if o['endpoint_id'] == 'FOOD')
            for s in candidates['sources'])):
        _fail('P29_INVENTORY_SOURCE_MISMATCH')
    category_map = {c['category_ref']: c for c in categories}
    rows = []
    initial_file = observation_name + '-public-fields.json'
    for source in initial_rows:
        row = asdict(source)
        row.pop('render_min_price_number')
        row.update(currency='CNY', amount_unit='YUAN', source_kind='CHECKED_INITIAL_PAIR',
            source_file=initial_file, source_request_ref=product['source_request_ref'],
            observed_at=product['observed_at'], window_ref=window)
        rows.append(row)
    for source in candidates['records']:
        rows.append({k: source[k] for k in (
            'category_ref', 'product_id', 'product_name', 'sku_id',
            'product_min_price_number', 'sku_price_number', 'product_unit',
            'sku_spec', 'sku_description', 'sku_origin_number', 'currency', 'amount_unit',
            'source_file', 'source_request_ref', 'observed_at', 'window_ref')}
            | {'source_kind': 'PARTIAL_CATEGORY_CANDIDATE'})
    input_count = len(initial_rows) + candidates['input_candidate_rows']
    if input_count > MAX_ROWS:
        _fail('P29_INVENTORY_BUDGET')
    selected, owners = {}, {}
    for row in sorted(rows, key=lambda r: (datetime.fromisoformat(r['observed_at']), r['source_request_ref'])):
        if row['category_ref'] not in category_map:
            _fail('P29_INVENTORY_CATEGORY_UNREFERENCED')
        if row['sku_id'] in owners and owners[row['sku_id']] != row['product_id']:
            _fail('P29_INVENTORY_SKU_OWNER_CHANGED')
        owners[row['sku_id']] = row['product_id']
        key = (row['category_ref'], row['sku_id'])
        previous = selected.get(key)
        if (previous is not None
                and datetime.fromisoformat(previous['observed_at']) == datetime.fromisoformat(row['observed_at'])
                and previous != row):
            _fail('P29_INVENTORY_ORDER_AMBIGUOUS')
        # Select the whole own row; a partial newer row never borrows old fields.
        selected[key] = row
    output = []
    for row in sorted(selected.values(), key=lambda r: (
            category_map[r['category_ref']]['source_index'], r['product_id'], r['sku_id'])):
        category = category_map[row['category_ref']]
        row.update(category_reference_label=category['category_reference_label'],
            category_label_source_file=category['source_file'],
            category_label_source_request_ref=category['source_request_ref'],
            category_label_observed_at=category['observed_at'])
        for key in ('sku_spec', 'sku_description', 'product_unit'):
            row[key + '_state'] = ('NOT_OBSERVED' if row[key] is None else
                'SOURCE_EMPTY' if row[key] == '' else 'PRESENT')
        output.append(row)
    view = {'schema_version': 'p29-store-input-inventory/v1', 'window_ref': window,
        'record_count': len(output), 'input_record_count': input_count,
        'deduplicated_record_count': input_count - len(output),
        'product_count': len({r['product_id'] for r in output}),
        'sku_count': len({r['sku_id'] for r in output}),
        'category_count': len({r['category_ref'] for r in output}),
        'checked_initial_rows': sum(r['source_kind'] == 'CHECKED_INITIAL_PAIR' for r in output),
        'partial_category_rows': sum(r['source_kind'] == 'PARTIAL_CATEGORY_CANDIDATE' for r in output),
        'coverage_status': 'PARTIAL', 'coverage_scope': 'CURRENT_WINDOW_OBSERVED_PUBLIC_INPUT',
        'deduplication': 'LATEST_WHOLE_OWN_ROW_PER_CATEGORY_SKU',
        'price_meaning': 'CATEGORY_SCOPED_RESPONSE_SKU_PRICE_NUMBER',
        'category_labels': 'REFERENCES_WITH_EXPLICIT_SOURCE_NOT_RESPONSE_OWNED_FIELDS',
        'cross_observation_prices_or_specs_copied': False, 'complete_result_promotion': False,
        'raw_payload_persisted': False, 'sensitive_values_processed': False,
        'categories': categories, 'records': output}
    _validate(view, 'p29-store-input-inventory-v1.schema.json')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator='\n', extrasaction='raise')
    writer.writeheader(); writer.writerows(output)
    return view, _bytes(view), stream.getvalue().encode('utf-8')


def inventory_view(root, observation_name, input_names):
    """Fixed errors only, including missing or malformed owned input files."""
    try:
        return _inventory_view(root, observation_name, input_names)
    except (CategoryCandidateError, ReceiverControlError):
        raise
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        _fail()


def publish_store_inventory(root, observation_name, input_names, result_name=None):
    root = _root(root)
    result_name = result_name if result_name is not None else 'store_inventory_' + uuid4().hex
    if type(result_name) is not str or _NAME.fullmatch(result_name) is None:
        _fail('P29_INVENTORY_NAME_INVALID')
    precheck_result_destination(str(root), result_name)
    view, json_bytes, csv_bytes = inventory_view(root, observation_name, input_names)
    manifest = {k: v for k, v in view.items() if k not in ('schema_version', 'records')}
    manifest.update(schema_version='p29-store-input-inventory-manifest/v1',
        result_name=result_name, files=['records.json', 'records.csv', 'manifest.json'])
    _validate(manifest, 'p29-store-input-inventory-manifest-v1.schema.json')
    manifest_bytes = _bytes(manifest)
    if sum(map(len, (json_bytes, csv_bytes, manifest_bytes))) > MAX_COLLECTION_BYTES:
        _fail('P29_INVENTORY_BUDGET')
    root_fd = result_fd = None
    created = success = False
    try:
        root_fd = os.open(root, _DIRECTORY_FLAGS)
        os.mkdir(result_name, 0o700, dir_fd=root_fd); created = True
        result_fd = os.open(result_name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        for name, content in (('records.json', json_bytes), ('records.csv', csv_bytes), ('manifest.json', manifest_bytes)):
            _write_file(result_fd, name, content)
        os.fsync(result_fd); os.fsync(root_fd); success = True
    except FileExistsError:
        raise ResultPublishError('RESULT_TARGET_EXISTS') from None
    except OSError:
        raise ResultPublishError('RESULT_PUBLISH_FAILED') from None
    finally:
        if created and not success:
            _cleanup_created_result(root_fd, result_fd, result_name)
        for fd in (result_fd, root_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
    return {'code': 'P29_STORE_INVENTORY_EXPORTED', 'result_name': result_name,
        **{k: view[k] for k in ('record_count', 'product_count', 'sku_count', 'category_count',
            'checked_initial_rows', 'partial_category_rows')}, 'live_attempts_consumed': 0}


def _initial_price_gaps():
    gaps = {number: None for number, _ in _PRICE_GAPS}
    gaps.update({state: 'NOT_REPARSED_ON_INITIAL_PAIR' for _, state in _PRICE_GAPS})
    gaps.update(product_unit_role='NOT_REPARSED_ON_INITIAL_PAIR',
        sku_price_source='INITIAL_PAIR_PAGE_CONFIRMED_SKU_PRICE',
        numeric_min_relation='NOT_REPARSED_ON_INITIAL_PAIR',
        currency='CNY', amount_unit='YUAN',
        currency_status='PAGE_CONFIRMED_FOR_INITIAL_PAIR_ONLY',
        amount_unit_status='PAGE_CONFIRMED_FOR_INITIAL_PAIR_ONLY',
        currency_basis='INITIAL_PAIR_PAGE_CONFIRMATION',
        amount_unit_basis='INITIAL_PAIR_PAGE_CONFIRMATION')
    return gaps


def _initial_rule_gaps():
    gaps = {
        field: 'NOT_REPARSED_ON_INITIAL_PAIR'
        if field.endswith('_state') or field.endswith('_scope') else None
        for field in RULE_EXPORT_FIELDS
    }
    gaps['sku_full_discount_tag_texts'] = None
    return gaps


_INITIAL_BASE_FIELDS = (
    'category_ref', 'product_id', 'product_name', 'sku_id', 'product_min_price_number',
    'sku_price_number', 'product_unit', 'sku_spec', 'sku_description', 'sku_origin_number',
)


def _align_initial_rows(source_rows, parsed_rows):
    """One parsed row per source identity. A dict write would hide a duplicate."""
    if len(parsed_rows) != len(source_rows):
        _fail('P29_INVENTORY_INITIAL_ROW_MISMATCH')
    located = {}
    for parsed in parsed_rows:
        key = (parsed.category_ref, parsed.product_id, parsed.sku_id)
        if key in located:
            _fail('P29_INVENTORY_INITIAL_ROW_MISMATCH')
        located[key] = parsed
    aligned = []
    seen = set()
    for source in source_rows:
        key = (source.category_ref, source.product_id, source.sku_id)
        if key in seen or key not in located:
            _fail('P29_INVENTORY_INITIAL_ROW_MISMATCH')
        seen.add(key)
        aligned.append(located[key])
    if len(seen) != len(located):
        _fail('P29_INVENTORY_INITIAL_ROW_MISMATCH')
    return aligned


def _additional_price(price_row):
    overlaid = {}
    for number, state in _PRICE_GAPS:
        overlaid[number] = getattr(price_row, number)
        overlaid[state] = getattr(price_row, state)
    return overlaid


def _initial_price_and_rules(product, source_rows):
    parsed_price = parse_category_price(product)
    parsed_rules = parse_price_rules(product)
    if any((parsed_rules.count_zero_means_no_threshold,
            parsed_rules.discount_number_proves_algorithm, parsed_rules.zero_amount_means_free,
            parsed_rules.negative_adapted_as_amount, parsed_rules.display_only_fields_passed_through,
            parsed_rules.nested_rules_concatenated)):
        _fail('P29_INVENTORY_INITIAL_ROW_MISMATCH')
    price_rows = _align_initial_rows(source_rows, parsed_price.rows)
    rule_rows = _align_initial_rows(source_rows, parsed_rules.rows)
    for source, price_row in zip(source_rows, price_rows):
        if any(getattr(source, field) != getattr(price_row, field) for field in _INITIAL_BASE_FIELDS):
            _fail('P29_INVENTORY_INITIAL_ROW_MISMATCH')
    return price_rows, rule_rows


def _price_inventory_view(root, observation_name, input_names, *, include_rules=False,
                          parse_initial_price_rules=False):
    if parse_initial_price_rules:
        include_rules = True
    root = _root(root)
    candidates, _, _ = price_view(root, input_names, include_rules=include_rules)
    public, product, categories, initial_rows = _initial(root, observation_name)
    window = public['window_ref']
    if (candidates['window_ref'] != window or any(
            source['source_context_result_name'] != observation_name
            or source['source_context_observed_at'] != next(
                item['observed_at'] for item in public['observations'] if item['endpoint_id'] == 'FOOD')
            for source in candidates['sources'])):
        _fail('P29_INVENTORY_SOURCE_MISMATCH')
    category_map = {item['category_ref']: item for item in categories}
    rows = []
    initial_file = observation_name + '-public-fields.json'
    parsed_initial = (_initial_price_and_rules(product, initial_rows)
                      if parse_initial_price_rules else None)
    for index, source in enumerate(initial_rows):
        rows.append({'category_ref': source.category_ref, 'product_id': source.product_id,
            'product_name': source.product_name, 'sku_id': source.sku_id,
            'product_min_price_number': source.product_min_price_number,
            'sku_price_number': source.sku_price_number, 'product_unit': source.product_unit,
            'sku_spec': source.sku_spec, 'sku_description': source.sku_description,
            'sku_origin_number': source.sku_origin_number, 'source_kind': 'CHECKED_INITIAL_PAIR',
            'source_file': initial_file, 'source_request_ref': product['source_request_ref'],
            'observed_at': product['observed_at'], 'window_ref': window, **_initial_price_gaps()})
        if include_rules and not parse_initial_price_rules:
            rows[-1].update(_initial_rule_gaps())
        elif parse_initial_price_rules:
            # Page-confirmed CNY/YUAN and basis stay on this row. Category rows are built separately.
            rows[-1].update(_additional_price(parsed_initial[0][index]))
            rows[-1].update(columns_from_row(parsed_initial[1][index]))
            rows[-1]['sku_full_discount_tag_texts'] = indexed_text_records(parsed_initial[1][index])
    for source in candidates['records']:
        row = {key: source[key] for key in (
            'category_ref', 'product_id', 'product_name', 'sku_id',
            'product_min_price_number', 'sku_price_number', 'product_unit',
            'sku_spec', 'sku_description', 'sku_origin_number',
            'sku_price_source', 'numeric_min_relation', 'product_unit_role',
            'currency_status', 'amount_unit_status', 'source_file',
            'source_request_ref', 'observed_at', 'window_ref')}
        row.update({number: source[number] for number, state in _PRICE_GAPS})
        row.update({state: source[state] for number, state in _PRICE_GAPS})
        row.update(currency=None, amount_unit=None,
            currency_basis='NOT_BORROWED_FROM_INITIAL_PAIR',
            amount_unit_basis='NOT_BORROWED_FROM_INITIAL_PAIR',
            source_kind='PARTIAL_CATEGORY_CANDIDATE')
        if include_rules:
            row.update({key: source[key] for key in RULE_EXPORT_FIELDS})
            row['sku_full_discount_tag_texts'] = source['sku_full_discount_tag_texts']
        rows.append(row)
    input_count = len(initial_rows) + candidates['input_candidate_rows']
    if input_count > MAX_ROWS:
        _fail('P29_INVENTORY_BUDGET')
    selected, owners = {}, {}
    for row in sorted(rows, key=lambda item: (datetime.fromisoformat(item['observed_at']), item['source_request_ref'])):
        if row['category_ref'] not in category_map:
            _fail('P29_INVENTORY_CATEGORY_UNREFERENCED')
        if row['sku_id'] in owners and owners[row['sku_id']] != row['product_id']:
            _fail('P29_INVENTORY_SKU_OWNER_CHANGED')
        owners[row['sku_id']] = row['product_id']
        key = (row['category_ref'], row['sku_id'])
        previous = selected.get(key)
        if (previous is not None
                and datetime.fromisoformat(previous['observed_at']) == datetime.fromisoformat(row['observed_at'])
                and previous != row):
            _fail('P29_INVENTORY_ORDER_AMBIGUOUS')
        selected[key] = row
    output = []
    for row in sorted(selected.values(), key=lambda item: (
            category_map[item['category_ref']]['source_index'], item['product_id'], item['sku_id'])):
        category = category_map[row['category_ref']]
        row.update(category_reference_label=category['category_reference_label'],
            category_label_source_file=category['source_file'],
            category_label_source_request_ref=category['source_request_ref'],
            category_label_observed_at=category['observed_at'])
        for key in ('sku_spec', 'sku_description', 'product_unit'):
            row[key + '_state'] = ('NOT_OBSERVED' if row[key] is None else
                'SOURCE_EMPTY' if row[key] == '' else 'PRESENT')
        fieldnames = CSV_PRICE_RULE_FIELDS if include_rules else CSV_PRICE_FIELDS
        record = {key: row[key] for key in fieldnames}
        if include_rules:
            record['sku_full_discount_tag_texts'] = row['sku_full_discount_tag_texts']
        output.append(record)
    view = {'schema_version': 'p29-store-input-inventory/v2', 'window_ref': window,
        'record_count': len(output), 'input_record_count': input_count,
        'deduplicated_record_count': input_count - len(output),
        'product_count': len({row['product_id'] for row in output}),
        'sku_count': len({row['sku_id'] for row in output}),
        'category_count': len({row['category_ref'] for row in output}),
        'checked_initial_rows': sum(row['source_kind'] == 'CHECKED_INITIAL_PAIR' for row in output),
        'partial_category_rows': sum(row['source_kind'] == 'PARTIAL_CATEGORY_CANDIDATE' for row in output),
        'coverage_status': 'PARTIAL', 'coverage_scope': 'CURRENT_WINDOW_OBSERVED_PUBLIC_INPUT',
        'deduplication': 'LATEST_WHOLE_OWN_ROW_PER_CATEGORY_SKU',
        'price_meaning': 'OWN_RESPONSE_PRICE_NUMBERS_CURRENCY_NOT_INFERRED',
        'category_labels': 'REFERENCES_WITH_EXPLICIT_SOURCE_NOT_RESPONSE_OWNED_FIELDS',
        'cross_observation_prices_or_specs_copied': False, 'complete_result_promotion': False,
        'currency_inferred': False, 'category_currency_borrowed_from_initial_pair': False,
        'raw_payload_persisted': False, 'sensitive_values_processed': False,
        'categories': categories, 'records': output}
    schema_name = 'p29-store-input-inventory-v2.schema.json'
    fieldnames = CSV_PRICE_FIELDS
    if include_rules:
        view['schema_version'] = 'p29-store-input-inventory/v3'
        view.update(rule_profile_version=RULE_VERSION, rule_profile_kind=RULE_PROFILE_KIND,
            count_zero_means_no_threshold=False, discount_number_proves_algorithm=False,
            zero_amount_means_free=False, negative_adapted_as_amount=False,
            display_only_fields_passed_through=False, nested_rules_concatenated=False,
            cross_observation_rule_fields_copied=False)
        schema_name = 'p29-store-input-inventory-v3.schema.json'
        fieldnames = CSV_PRICE_RULE_FIELDS
    if parse_initial_price_rules:
        view['schema_version'] = 'p29-store-input-inventory/v4'
        view.update(initial_pair_additional_price_reparsed=True, initial_pair_price_rules_reparsed=True)
        schema_name = 'p29-store-input-inventory-v4.schema.json'
    _validate(view, schema_name)
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator='\n', extrasaction='raise')
    writer.writeheader()
    writer.writerows([{key: row[key] for key in fieldnames} for row in output])
    return view, _bytes(view), stream.getvalue().encode('utf-8')


def price_inventory_view(root, observation_name, input_names):
    try:
        return _price_inventory_view(root, observation_name, input_names)
    except (CategoryCandidateError, ReceiverControlError):
        raise
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        _fail()


def publish_store_price_inventory(root, observation_name, input_names, result_name=None):
    root = _root(root)
    result_name = result_name if result_name is not None else 'store_price_inventory_' + uuid4().hex
    if type(result_name) is not str or _PRICE_NAME.fullmatch(result_name) is None:
        _fail('P29_INVENTORY_NAME_INVALID')
    precheck_result_destination(str(root), result_name)
    view, json_bytes, csv_bytes = price_inventory_view(root, observation_name, input_names)
    manifest = {key: value for key, value in view.items() if key not in ('schema_version', 'records')}
    manifest.update(schema_version='p29-store-input-inventory-manifest/v2',
        result_name=result_name, files=['records.json', 'records.csv', 'manifest.json'])
    _validate(manifest, 'p29-store-input-inventory-manifest-v2.schema.json')
    manifest_bytes = _bytes(manifest)
    if sum(map(len, (json_bytes, csv_bytes, manifest_bytes))) > MAX_COLLECTION_BYTES:
        _fail('P29_INVENTORY_BUDGET')
    root_fd = result_fd = None
    created = success = False
    try:
        root_fd = os.open(root, _DIRECTORY_FLAGS)
        os.mkdir(result_name, 0o700, dir_fd=root_fd); created = True
        result_fd = os.open(result_name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        for name, content in (('records.json', json_bytes), ('records.csv', csv_bytes), ('manifest.json', manifest_bytes)):
            _write_file(result_fd, name, content)
        os.fsync(result_fd); os.fsync(root_fd); success = True
    except FileExistsError:
        raise ResultPublishError('RESULT_TARGET_EXISTS') from None
    except OSError:
        raise ResultPublishError('RESULT_PUBLISH_FAILED') from None
    finally:
        if created and not success:
            _cleanup_created_result(root_fd, result_fd, result_name)
        for fd in (result_fd, root_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
    return {'code': 'P29_STORE_PRICE_INVENTORY_EXPORTED', 'result_name': result_name,
        **{key: view[key] for key in ('record_count', 'product_count', 'sku_count', 'category_count',
            'checked_initial_rows', 'partial_category_rows')},
        'currency_inferred': False, 'live_attempts_consumed': 0}


def rules_inventory_view(root, observation_name, input_names):
    try:
        return _price_inventory_view(root, observation_name, input_names, include_rules=True)
    except (CategoryCandidateError, ReceiverControlError):
        raise
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        _fail()


def publish_store_price_rules(root, observation_name, input_names, result_name=None):
    root = _root(root)
    result_name = result_name if result_name is not None else 'store_price_rules_' + uuid4().hex
    if type(result_name) is not str or _RULES_NAME.fullmatch(result_name) is None:
        _fail('P29_INVENTORY_NAME_INVALID')
    precheck_result_destination(str(root), result_name)
    view, json_bytes, csv_bytes = rules_inventory_view(root, observation_name, input_names)
    manifest = {key: value for key, value in view.items() if key not in ('schema_version', 'records')}
    manifest.update(schema_version='p29-store-input-inventory-manifest/v3',
        result_name=result_name, files=['records.json', 'records.csv', 'manifest.json'])
    _validate(manifest, 'p29-store-input-inventory-manifest-v3.schema.json')
    manifest_bytes = _bytes(manifest)
    if sum(map(len, (json_bytes, csv_bytes, manifest_bytes))) > MAX_COLLECTION_BYTES:
        _fail('P29_INVENTORY_BUDGET')
    root_fd = result_fd = None
    created = success = False
    try:
        root_fd = os.open(root, _DIRECTORY_FLAGS)
        os.mkdir(result_name, 0o700, dir_fd=root_fd); created = True
        result_fd = os.open(result_name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        for name, content in (('records.json', json_bytes), ('records.csv', csv_bytes), ('manifest.json', manifest_bytes)):
            _write_file(result_fd, name, content)
        os.fsync(result_fd); os.fsync(root_fd); success = True
    except FileExistsError:
        raise ResultPublishError('RESULT_TARGET_EXISTS') from None
    except OSError:
        raise ResultPublishError('RESULT_PUBLISH_FAILED') from None
    finally:
        if created and not success:
            _cleanup_created_result(root_fd, result_fd, result_name)
        for fd in (result_fd, root_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
    return {'code': 'P29_STORE_PRICE_RULES_EXPORTED', 'result_name': result_name,
        **{key: view[key] for key in ('record_count', 'product_count', 'sku_count', 'category_count',
            'checked_initial_rows', 'partial_category_rows')},
        'currency_inferred': False, 'count_zero_means_no_threshold': False,
        'zero_amount_means_free': False, 'negative_adapted_as_amount': False,
        'live_attempts_consumed': 0}


def initial_price_rules_inventory_view(root, observation_name, input_names):
    try:
        return _price_inventory_view(
            root, observation_name, input_names, parse_initial_price_rules=True)
    except (CategoryCandidateError, ReceiverControlError):
        raise
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        _fail()


def publish_store_initial_price_rules(root, observation_name, input_names, result_name=None):
    root = _root(root)
    result_name = result_name if result_name is not None else 'store_initial_price_rules_' + uuid4().hex
    if type(result_name) is not str or _INITIAL_RULES_NAME.fullmatch(result_name) is None:
        _fail('P29_INVENTORY_NAME_INVALID')
    precheck_result_destination(str(root), result_name)
    view, json_bytes, csv_bytes = initial_price_rules_inventory_view(root, observation_name, input_names)
    manifest = {key: value for key, value in view.items() if key not in ('schema_version', 'records')}
    manifest.update(schema_version='p29-store-input-inventory-manifest/v4',
        result_name=result_name, files=['records.json', 'records.csv', 'manifest.json'])
    _validate(manifest, 'p29-store-input-inventory-manifest-v4.schema.json')
    manifest_bytes = _bytes(manifest)
    if sum(map(len, (json_bytes, csv_bytes, manifest_bytes))) > MAX_COLLECTION_BYTES:
        _fail('P29_INVENTORY_BUDGET')
    root_fd = result_fd = None
    created = success = False
    try:
        root_fd = os.open(root, _DIRECTORY_FLAGS)
        os.mkdir(result_name, 0o700, dir_fd=root_fd); created = True
        result_fd = os.open(result_name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        for name, content in (('records.json', json_bytes), ('records.csv', csv_bytes), ('manifest.json', manifest_bytes)):
            _write_file(result_fd, name, content)
        os.fsync(result_fd); os.fsync(root_fd); success = True
    except FileExistsError:
        raise ResultPublishError('RESULT_TARGET_EXISTS') from None
    except OSError:
        raise ResultPublishError('RESULT_PUBLISH_FAILED') from None
    finally:
        if created and not success:
            _cleanup_created_result(root_fd, result_fd, result_name)
        for fd in (result_fd, root_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
    return {'code': 'P29_STORE_INITIAL_PRICE_RULES_EXPORTED', 'result_name': result_name,
        **{key: view[key] for key in ('record_count', 'product_count', 'sku_count', 'category_count',
            'checked_initial_rows', 'partial_category_rows')},
        'currency_inferred': False, 'initial_pair_additional_price_reparsed': True,
        'initial_pair_price_rules_reparsed': True, 'count_zero_means_no_threshold': False,
        'zero_amount_means_free': False, 'negative_adapted_as_amount': False,
        'complete_result_promotion': False, 'live_attempts_consumed': 0}


class _Arguments(argparse.ArgumentParser):
    def error(self, message):
        _fail('P29_INVENTORY_ARGUMENTS_INVALID')


def main():
    parser = _Arguments(description=__doc__)
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--observation-name', required=True)
    parser.add_argument('--input-name', required=True, action='append')
    parser.add_argument('--result-name')
    parser.add_argument('--price-evidence', action='store_true')
    parser.add_argument('--price-rules', action='store_true')
    parser.add_argument('--initial-price-rules', action='store_true')
    try:
        args = parser.parse_args()
        if sum((args.price_evidence, args.price_rules, args.initial_price_rules)) > 1:
            _fail('P29_INVENTORY_ARGUMENTS_INVALID')
        publish = (publish_store_initial_price_rules if args.initial_price_rules else
                   publish_store_price_rules if args.price_rules else
                   publish_store_price_inventory if args.price_evidence else publish_store_inventory)
        result = publish(Path(args.output_root), args.observation_name,
            args.input_name, args.result_name)
    except (CategoryCandidateError, ReceiverControlError, ResultPublishError) as error:
        print(json.dumps({'code': error.code})); return 1
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        print(json.dumps({'code': 'P29_INVENTORY_INPUT_INVALID'})); return 1
    print(json.dumps(result, sort_keys=True)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
