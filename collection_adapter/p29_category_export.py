"""Export owned category candidates with explicit missing facts and sources.

This reads named public scalar inventories, consumes no live attempt and does
not enter the complete-record publisher. Unknown units and identities remain
unknown; a later observation always supplies the whole selected candidate.
"""

import argparse
import csv
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource

from collection_core.p29 import MAX_COLLECTION_BYTES
from collection_core.result_publisher import (
    ResultPublishError, _DIRECTORY_FLAGS, _cleanup_created_result, _write_file,
    precheck_result_destination,
)
from .p26_identification_host import _read_owned
from .p29_batch_parameter import _ARRAY_FIELDS, _response_memberships
from .p29_category_review import review_category_batch
from .p29_receiver_control import ReceiverControlError, _root
from parser_candidate.p29_category_profile import CategoryCandidateError, parse_category_public_values
from parser_candidate.p29_category_price import (
    FAMILY as PRICE_FAMILY, PROFILE_KIND, VERSION as PRICE_VERSION,
    CURRENCY_NOT_PROVIDED, PATH_PRESENT_NOT_ADAPTED, parse_category_price,
)
from parser_candidate.p29_price_rules import (
    PROFILE_KIND as RULE_PROFILE_KIND, RULE_EXPORT_FIELDS, UNKNOWN_FACTS as RULE_UNKNOWN_FACTS,
    VERSION as RULE_VERSION, columns_from_row, indexed_text_records, parse_price_rules,
)

CSV_FIELDS = (
    'category_ref', 'product_id', 'product_name', 'sku_id',
    'product_min_price_number', 'render_min_price_number', 'sku_price_number',
    'product_unit', 'product_unit_state', 'sku_spec', 'sku_spec_state',
    'sku_description', 'sku_description_state', 'sku_origin_number',
    'sku_origin_number_state', 'currency', 'amount_unit', 'price_meaning',
    'store_scope', 'store_name_state', 'category_name_state',
    'source_file', 'source_request_ref', 'observed_at', 'window_ref',
)
_NAME = re.compile(r'category_candidates_[a-f0-9]{32}')
_PRICE_NAME = re.compile(r'category_price_[a-f0-9]{32}')
_RULE_NAME = re.compile(r'category_price_rules_[a-f0-9]{32}')
CSV_PRICE_FIELDS = (
    'category_ref', 'product_id', 'product_name', 'sku_id',
    'product_min_price_number', 'render_min_price_number', 'sku_price_number',
    'sku_price_source', 'product_min_price_source', 'render_min_price_source',
    'numeric_min_relation', 'sku_origin_number', 'sku_origin_state',
    'render_origin_number', 'render_origin_state',
    'product_full_discount_price_number', 'product_full_discount_price_state',
    'sku_member_price_number', 'sku_member_price_state',
    'sku_full_discount_price_number', 'sku_full_discount_price_state',
    'sku_box_price_number', 'sku_box_price_state',
    'min_price_tail', 'min_price_tail_state',
    'render_price_desc', 'render_price_desc_state',
    'sku_price_desc', 'sku_price_desc_state',
    'product_unit', 'product_unit_state', 'product_unit_role',
    'sku_spec', 'sku_spec_state', 'sku_description', 'sku_description_state',
    'currency_status', 'amount_unit_status',
    'store_scope', 'store_name_state', 'category_name_state',
    'source_file', 'source_request_ref', 'observed_at', 'window_ref',
)
_SOURCE_AT = CSV_PRICE_FIELDS.index('source_file')
CSV_PRICE_RULE_FIELDS = CSV_PRICE_FIELDS[:_SOURCE_AT] + RULE_EXPORT_FIELDS + CSV_PRICE_FIELDS[_SOURCE_AT:]
_PRICE_UNKNOWN_FACTS = [
    'MERCHANT_NAME_IN_RESPONSE', 'CATEGORY_NAME_IN_RESPONSE', 'CURRENCY_CODE',
    'AMOUNT_UNIT', 'BUSINESS_SEMANTICS_OF_UNCONFIRMED_PRICE_COMPONENTS',
    'CATEGORY_TERMINATION', 'TAG_TYPE_SEMANTICS', 'CHILD_TAG_SEMANTICS',
]


def _validate(document, name):
    path = Path(__file__).resolve().parents[1] / 'contracts/schemas' / name
    validator = Draft202012Validator(json.loads(path.read_text()), format_checker=FormatChecker())
    if not validator.is_valid(document):
        raise CategoryCandidateError('P29_CATEGORY_EXPORT_INVALID')


def _validate_closed(document, name):
    schemas = Path(__file__).resolve().parents[1] / 'contracts/schemas'
    resources = {item.name: Resource.from_contents(json.loads(item.read_text()))
                 for item in schemas.glob('*.schema.json')}

    def local(uri):
        if uri in resources:
            return resources[uri]
        raise NoSuchResource(ref=uri)

    validator = Draft202012Validator(json.loads((schemas / name).read_text()),
        registry=Registry(retrieve=local).with_resources(resources.items()),
        format_checker=FormatChecker())
    if not validator.is_valid(document):
        raise CategoryCandidateError('P29_CATEGORY_EXPORT_INVALID')


def _rollup(values):
    if all(value == CURRENCY_NOT_PROVIDED for value in values):
        return CURRENCY_NOT_PROVIDED
    if all(value == PATH_PRESENT_NOT_ADAPTED for value in values):
        return PATH_PRESENT_NOT_ADAPTED
    return 'MIXED_PATH_PRESENCE'


def _bytes(document):
    return (json.dumps(document, ensure_ascii=True, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode('utf-8')


def _view(root, input_names):
    report, selected = review_category_batch(root, input_names)
    sources = []
    for source in report['sources']:
        name = source['source_file']
        probe_name = name.removesuffix('-public-fields.json') + '-batch-parameter.json'
        try:
            public = _read_owned(root / name, 4 * 1024 * 1024)
            probe = _read_owned(root / probe_name, 128 * 1024)
        except (OSError, ValueError):
            raise CategoryCandidateError('P29_CATEGORY_EXPORT_PROOF_UNAVAILABLE') from None
        _validate(probe, 'p29-category-batch-parameter-probe-v2.schema.json')
        if (public['schema_version'] not in ('p29-category-render-inspection/v2',
                'p29-category-render-inspection/v3', 'p29-category-render-inspection/v4')
                or public['response_code_status'] != 'ZERO'
                or any(public[k] != probe[k] for k in (
                    'window_ref', 'source_request_ref', 'observed_at', 'source_context_result_name'))):
            raise CategoryCandidateError('P29_CATEGORY_EXPORT_PROOF_MISMATCH')
        body = probe['probe']
        relation = body['array_item_relation']
        count = len(_response_memberships(public['public_analysis']))
        if (body['status'] != 'STRUCTURE_OBSERVED' or body['root_kind'] != 'ARRAY'
                or {(f['path'], f['type']) for f in body['fields']} != _ARRAY_FIELDS
                or body['public_scalar_count'] != 4 * count
                or body['response_category_product_membership_count'] != count
                or relation['status'] != 'MATCHED_CURRENT_RESPONSE'
                or relation['item_count'] != count
                or relation['request_membership_count'] != count
                or relation['matching_tag_membership_count'] != count
                or any(relation[k] != 0 for k in ('duplicate_request_memberships',
                    'request_memberships_not_in_response', 'response_memberships_not_in_request'))):
            raise CategoryCandidateError('P29_CATEGORY_EXPORT_PROOF_MISMATCH')
        groups = {}
        for row in parse_category_public_values(public['public_analysis']):
            groups.setdefault((row.category_ref, row.product_id), []).append(row)
        for group in groups.values():
            minimum = min(Decimal(r.sku_price_number) for r in group)
            if any(Decimal(r.product_min_price_number) != minimum
                   or Decimal(r.render_min_price_number) != minimum for r in group):
                raise CategoryCandidateError('P29_CATEGORY_EXPORT_PRICE_RELATION_INVALID')
        sources.append({k: public[k] for k in ('source_request_ref', 'observed_at',
            'source_context_result_name', 'source_context_observed_at',
            'source_context_age_within_10_seconds')}
            | {'source_file': name, 'batch_parameter_file': probe_name,
               'array_item_relation': 'MATCHED_CURRENT_RESPONSE'})
    rows = []
    for observation in selected:
        row = asdict(observation.candidate)
        for key in ('product_unit', 'sku_spec', 'sku_description'):
            row[key + '_state'] = ('NOT_OBSERVED' if row[key] is None else
                                  'SOURCE_EMPTY' if row[key] == '' else 'PRESENT')
        row['sku_origin_number_state'] = ('NOT_OBSERVED' if row['sku_origin_number'] is None
                                          else 'SEMANTICS_UNCONFIRMED')
        row.update(currency='UNKNOWN', amount_unit='UNKNOWN',
            price_meaning='UNCONFIRMED_CATEGORY_SOURCE_NUMBERS',
            store_scope='MATCHED_CURRENT_STORE_REQUEST',
            store_name_state='NOT_OBSERVED_IN_RESPONSE',
            category_name_state='NOT_OBSERVED_IN_RESPONSE',
            source_file=observation.source_file,
            source_request_ref=observation.source_request_ref,
            observed_at=observation.observed_at, window_ref=report['window_ref'])
        rows.append(row)
    view = {k: report[k] for k in ('window_ref', 'profile_family', 'profile_version',
        'profile_kind', 'response_count', 'input_candidate_rows', 'deduplicated_candidate_rows',
        'product_count', 'sku_count', 'category_count', 'deduplication')}
    view.update(schema_version='p29-category-candidate-result/v1',
        record_kind='PARTIAL_CATEGORY_CANDIDATE', record_count=len(rows),
        coverage_status='PARTIAL', coverage_scope='OBSERVED_MATCHED_CATEGORY_RESPONSES_ONLY',
        can_publish_complete_result=False, cross_observation_fields_copied=False,
        raw_payload_persisted=False, sensitive_values_processed=False,
        unknown_facts=['MERCHANT_NAME_IN_RESPONSE', 'CATEGORY_NAME_IN_RESPONSE',
            'PRICE_CURRENCY_AND_UNIT', 'PRICE_SEMANTICS', 'CATEGORY_TERMINATION',
            'TAG_TYPE_SEMANTICS', 'CHILD_TAG_SEMANTICS'], sources=sources, records=rows)
    _validate(view, 'p29-category-candidate-result-v1.schema.json')
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator='\n', extrasaction='raise')
    writer.writeheader()
    writer.writerows(rows)
    return view, _bytes(view), stream.getvalue().encode('utf-8')


def publish_category_candidates(root, input_names, result_name=None):
    """Publish an exclusive, bounded candidate directory, manifest last."""
    root = _root(root)
    result_name = result_name if result_name is not None else 'category_candidates_' + uuid4().hex
    if type(result_name) is not str or _NAME.fullmatch(result_name) is None:
        raise CategoryCandidateError('P29_CATEGORY_EXPORT_NAME_INVALID')
    precheck_result_destination(str(root), result_name)
    view, json_bytes, csv_bytes = _view(root, input_names)
    manifest = {k: v for k, v in view.items() if k not in ('schema_version', 'records')}
    manifest.update(schema_version='p29-category-candidate-manifest/v1',
                    result_name=result_name, files=['records.json', 'records.csv', 'manifest.json'])
    _validate(manifest, 'p29-category-candidate-manifest-v1.schema.json')
    manifest_bytes = _bytes(manifest)
    if len(json_bytes) + len(csv_bytes) + len(manifest_bytes) > MAX_COLLECTION_BYTES:
        raise CategoryCandidateError('P29_CATEGORY_EXPORT_BUDGET')
    root_fd = result_fd = None
    created = success = False
    try:
        root_fd = os.open(root, _DIRECTORY_FLAGS)
        try:
            os.mkdir(result_name, 0o700, dir_fd=root_fd)
        except FileExistsError:
            raise ResultPublishError('RESULT_TARGET_EXISTS') from None
        created = True
        result_fd = os.open(result_name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        for name, payload in (('records.json', json_bytes), ('records.csv', csv_bytes),
                              ('manifest.json', manifest_bytes)):
            _write_file(result_fd, name, payload)
        os.fsync(result_fd)
        os.fsync(root_fd)
        success = True
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
    return {'code': 'P29_CATEGORY_CANDIDATES_EXPORTED', 'result_name': result_name,
        'file_names': manifest['files'], **{k: view[k] for k in ('record_count',
            'product_count', 'sku_count', 'category_count', 'response_count')},
        'can_publish_complete_result': False, 'live_attempts_consumed': 0}


def _price_record(price, observation, window_ref):
    candidate = observation.candidate
    if (price.category_ref != candidate.category_ref or price.product_id != candidate.product_id
            or price.product_name != candidate.product_name or price.sku_id != candidate.sku_id
            or price.product_min_price_number != candidate.product_min_price_number
            or price.render_min_price_number != candidate.render_min_price_number
            or price.sku_price_number != candidate.sku_price_number
            or price.product_unit != candidate.product_unit or price.sku_spec != candidate.sku_spec
            or price.sku_description != candidate.sku_description
            or price.sku_origin_number != candidate.sku_origin_number
            or price.numeric_min_relation != 'EQUAL_PRODUCT_RENDER_AND_MIN_SKU'):
        raise CategoryCandidateError('P29_CATEGORY_EXPORT_PRICE_EVIDENCE_MISMATCH')
    row = {key: getattr(price, key) for key in (
        'category_ref', 'product_id', 'product_name', 'sku_id',
        'product_min_price_number', 'render_min_price_number', 'sku_price_number',
        'sku_price_source', 'product_min_price_source', 'render_min_price_source',
        'numeric_min_relation', 'sku_origin_number', 'sku_origin_state',
        'render_origin_number', 'render_origin_state',
        'product_full_discount_price_number', 'product_full_discount_price_state',
        'sku_member_price_number', 'sku_member_price_state',
        'sku_full_discount_price_number', 'sku_full_discount_price_state',
        'sku_box_price_number', 'sku_box_price_state',
        'min_price_tail', 'min_price_tail_state',
        'render_price_desc', 'render_price_desc_state',
        'sku_price_desc', 'sku_price_desc_state',
        'product_unit', 'product_unit_role')}
    for key in ('product_unit', 'sku_spec', 'sku_description'):
        value = getattr(price, key)
        row[key] = value
        row[key + '_state'] = ('NOT_OBSERVED' if value is None else
                               'SOURCE_EMPTY' if value == '' else 'PRESENT')
    row.update(currency_status=price.currency_status, amount_unit_status=price.amount_unit_status,
        store_scope='MATCHED_CURRENT_STORE_REQUEST',
        store_name_state='NOT_OBSERVED_IN_RESPONSE',
        category_name_state='NOT_OBSERVED_IN_RESPONSE',
        source_file=observation.source_file, source_request_ref=observation.source_request_ref,
        observed_at=observation.observed_at, window_ref=window_ref)
    return row


def price_view(root, input_names, *, include_rules=False):
    """Candidate export with per-component price evidence. v1 export stays unchanged.

    include_rules adds same-response rule columns and compares those columns in
    the same-time conflict check. v2 callers leave it false.
    """
    report, selected = review_category_batch(root, input_names)
    sources, parsed_by_file, rules_by_file, same_time_rows = [], {}, {}, {}
    for source in report['sources']:
        name = source['source_file']
        probe_name = name.removesuffix('-public-fields.json') + '-batch-parameter.json'
        try:
            public = _read_owned(root / name, 4 * 1024 * 1024)
            probe = _read_owned(root / probe_name, 128 * 1024)
        except (OSError, ValueError):
            raise CategoryCandidateError('P29_CATEGORY_EXPORT_PROOF_UNAVAILABLE') from None
        _validate(probe, 'p29-category-batch-parameter-probe-v2.schema.json')
        if (public['schema_version'] not in ('p29-category-render-inspection/v2',
                'p29-category-render-inspection/v3', 'p29-category-render-inspection/v4')
                or public['response_code_status'] != 'ZERO'
                or any(public[k] != probe[k] for k in (
                    'window_ref', 'source_request_ref', 'observed_at', 'source_context_result_name'))):
            raise CategoryCandidateError('P29_CATEGORY_EXPORT_PROOF_MISMATCH')
        body = probe['probe']
        relation = body['array_item_relation']
        count = len(_response_memberships(public['public_analysis']))
        if (body['status'] != 'STRUCTURE_OBSERVED' or body['root_kind'] != 'ARRAY'
                or {(f['path'], f['type']) for f in body['fields']} != _ARRAY_FIELDS
                or body['public_scalar_count'] != 4 * count
                or body['response_category_product_membership_count'] != count
                or relation['status'] != 'MATCHED_CURRENT_RESPONSE'
                or relation['item_count'] != count
                or relation['request_membership_count'] != count
                or relation['matching_tag_membership_count'] != count
                or any(relation[k] != 0 for k in ('duplicate_request_memberships',
                    'request_memberships_not_in_response', 'response_memberships_not_in_request'))):
            raise CategoryCandidateError('P29_CATEGORY_EXPORT_PROOF_MISMATCH')
        parsed = parse_category_price(public['public_analysis'])
        rule_by_identity = {}
        if include_rules:
            parsed_rules = parse_price_rules(public['public_analysis'])
            price_identity = [(row.category_ref, row.product_id, row.sku_id) for row in parsed.rows]
            rule_identity = [(row.category_ref, row.product_id, row.sku_id) for row in parsed_rules.rows]
            if price_identity != rule_identity or any((
                    parsed_rules.count_zero_means_no_threshold,
                    parsed_rules.discount_number_proves_algorithm,
                    parsed_rules.zero_amount_means_free, parsed_rules.negative_adapted_as_amount,
                    parsed_rules.display_only_fields_passed_through,
                    parsed_rules.nested_rules_concatenated)):
                raise CategoryCandidateError('P29_CATEGORY_EXPORT_PRICE_EVIDENCE_MISMATCH')
            for rule_row in parsed_rules.rows:
                rule_by_identity[(rule_row.category_ref, rule_row.product_id, rule_row.sku_id)] = rule_row
            rules_by_file[name] = rule_by_identity
        observed_at = datetime.fromisoformat(public['observed_at'].replace('Z', '+00:00'))
        for row in parsed.rows:
            key = (observed_at, row.category_ref, row.sku_id)
            signature = (row, rule_by_identity[(row.category_ref, row.product_id, row.sku_id)]) if include_rules else row
            previous = same_time_rows.get(key)
            if previous is not None and previous != signature:
                raise CategoryCandidateError('P29_CATEGORY_BATCH_ORDER_AMBIGUOUS')
            same_time_rows[key] = signature
        parsed_by_file[name] = { (row.category_ref, row.sku_id): row for row in parsed.rows }
        groups = {}
        for row in parsed.rows:
            groups.setdefault((row.category_ref, row.product_id), []).append(row)
        for group in groups.values():
            minimum = min(Decimal(row.sku_price_number) for row in group)
            if any(Decimal(row.product_min_price_number) != minimum
                   or Decimal(row.render_min_price_number) != minimum
                   or row.numeric_min_relation != 'EQUAL_PRODUCT_RENDER_AND_MIN_SKU'
                   for row in group):
                raise CategoryCandidateError('P29_CATEGORY_EXPORT_PRICE_RELATION_INVALID')
        sources.append({k: public[k] for k in ('source_request_ref', 'observed_at',
            'source_context_result_name', 'source_context_observed_at',
            'source_context_age_within_10_seconds')}
            | {'source_file': name, 'batch_parameter_file': probe_name,
               'array_item_relation': 'MATCHED_CURRENT_RESPONSE',
               'currency_path_status': parsed.currency_path_status,
               'amount_unit_path_status': parsed.amount_unit_path_status,
               'activity_price_path_status': parsed.activity_price_path_status,
               'price_desc_tag_path_status': parsed.price_desc_tag_path_status})
    rows = []
    for observation in selected:
        try:
            price = parsed_by_file[observation.source_file][
                (observation.candidate.category_ref, observation.candidate.sku_id)]
            record = _price_record(price, observation, report['window_ref'])
            if include_rules:
                rule_row = rules_by_file[observation.source_file][(
                    observation.candidate.category_ref, observation.candidate.product_id,
                    observation.candidate.sku_id)]
                record.update(columns_from_row(rule_row))
                record['sku_full_discount_tag_texts'] = indexed_text_records(rule_row)
        except KeyError:
            raise CategoryCandidateError('P29_CATEGORY_EXPORT_PRICE_EVIDENCE_MISMATCH') from None
        rows.append(record)
    view = {k: report[k] for k in ('window_ref', 'response_count', 'input_candidate_rows',
        'deduplicated_candidate_rows', 'product_count', 'sku_count', 'category_count', 'deduplication')}
    view.update(schema_version='p29-category-candidate-result/v2',
        profile_family=PRICE_FAMILY, profile_version=PRICE_VERSION, profile_kind=PROFILE_KIND,
        record_kind='PARTIAL_CATEGORY_CANDIDATE', record_count=len(rows),
        coverage_status='PARTIAL', coverage_scope='OBSERVED_MATCHED_CATEGORY_RESPONSES_ONLY',
        can_publish_complete_result=False, cross_observation_fields_copied=False,
        raw_payload_persisted=False, sensitive_values_processed=False,
        currency_inferred=False, amount_unit_inferred=False, initial_pair_currency_borrowed=False,
        currency_path_status=_rollup(source['currency_path_status'] for source in sources),
        amount_unit_path_status=_rollup(source['amount_unit_path_status'] for source in sources),
        activity_price_path_status=_rollup(source['activity_price_path_status'] for source in sources),
        price_desc_tag_path_status=_rollup(source['price_desc_tag_path_status'] for source in sources),
        unknown_facts=list(_PRICE_UNKNOWN_FACTS), sources=sources, records=rows)
    schema_name = 'p29-category-candidate-result-v2.schema.json'
    csv_fields = CSV_PRICE_FIELDS
    csv_rows = rows
    if include_rules:
        view['schema_version'] = 'p29-category-candidate-result/v3'
        view['unknown_facts'] = list(RULE_UNKNOWN_FACTS)
        view.update(rule_profile_version=RULE_VERSION, rule_profile_kind=RULE_PROFILE_KIND,
            count_zero_means_no_threshold=False, discount_number_proves_algorithm=False,
            zero_amount_means_free=False, negative_adapted_as_amount=False,
            display_only_fields_passed_through=False, nested_rules_concatenated=False,
            cross_observation_rule_fields_copied=False)
        schema_name = 'p29-category-candidate-result-v3.schema.json'
        csv_fields = CSV_PRICE_RULE_FIELDS
        csv_rows = [{key: row[key] for key in csv_fields} for row in rows]
    _validate_closed(view, schema_name)
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=csv_fields, lineterminator='\n', extrasaction='raise')
    writer.writeheader()
    writer.writerows(csv_rows)
    return view, _bytes(view), stream.getvalue().encode('utf-8')


def publish_category_price(root, input_names, result_name=None):
    """Publish v2 price evidence without replacing a v1 candidate directory."""
    root = _root(root)
    result_name = result_name if result_name is not None else 'category_price_' + uuid4().hex
    if type(result_name) is not str or _PRICE_NAME.fullmatch(result_name) is None:
        raise CategoryCandidateError('P29_CATEGORY_EXPORT_NAME_INVALID')
    precheck_result_destination(str(root), result_name)
    view, json_bytes, csv_bytes = price_view(root, input_names)
    manifest = {k: v for k, v in view.items() if k not in ('schema_version', 'records')}
    manifest.update(schema_version='p29-category-candidate-manifest/v2',
                    result_name=result_name, files=['records.json', 'records.csv', 'manifest.json'])
    _validate_closed(manifest, 'p29-category-candidate-manifest-v2.schema.json')
    manifest_bytes = _bytes(manifest)
    if len(json_bytes) + len(csv_bytes) + len(manifest_bytes) > MAX_COLLECTION_BYTES:
        raise CategoryCandidateError('P29_CATEGORY_EXPORT_BUDGET')
    root_fd = result_fd = None
    created = success = False
    try:
        root_fd = os.open(root, _DIRECTORY_FLAGS)
        try:
            os.mkdir(result_name, 0o700, dir_fd=root_fd)
        except FileExistsError:
            raise ResultPublishError('RESULT_TARGET_EXISTS') from None
        created = True
        result_fd = os.open(result_name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        for name, payload in (('records.json', json_bytes), ('records.csv', csv_bytes),
                              ('manifest.json', manifest_bytes)):
            _write_file(result_fd, name, payload)
        os.fsync(result_fd)
        os.fsync(root_fd)
        success = True
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
    return {'code': 'P29_CATEGORY_PRICE_EXPORTED', 'result_name': result_name,
        'file_names': manifest['files'], **{k: view[k] for k in ('record_count',
            'product_count', 'sku_count', 'category_count', 'response_count')},
        'can_publish_complete_result': False, 'currency_inferred': False,
        'live_attempts_consumed': 0}


def publish_category_price_rules(root, input_names, result_name=None):
    """Publish v3 price-plus-rule evidence without replacing a v1 or v2 directory."""
    root = _root(root)
    result_name = result_name if result_name is not None else 'category_price_rules_' + uuid4().hex
    if type(result_name) is not str or _RULE_NAME.fullmatch(result_name) is None:
        raise CategoryCandidateError('P29_CATEGORY_EXPORT_NAME_INVALID')
    precheck_result_destination(str(root), result_name)
    view, json_bytes, csv_bytes = price_view(root, input_names, include_rules=True)
    manifest = {key: value for key, value in view.items() if key not in ('schema_version', 'records')}
    manifest.update(schema_version='p29-category-candidate-manifest/v3',
                    result_name=result_name, files=['records.json', 'records.csv', 'manifest.json'])
    _validate_closed(manifest, 'p29-category-candidate-manifest-v3.schema.json')
    manifest_bytes = _bytes(manifest)
    if len(json_bytes) + len(csv_bytes) + len(manifest_bytes) > MAX_COLLECTION_BYTES:
        raise CategoryCandidateError('P29_CATEGORY_EXPORT_BUDGET')
    root_fd = result_fd = None
    created = success = False
    try:
        root_fd = os.open(root, _DIRECTORY_FLAGS)
        try:
            os.mkdir(result_name, 0o700, dir_fd=root_fd)
        except FileExistsError:
            raise ResultPublishError('RESULT_TARGET_EXISTS') from None
        created = True
        result_fd = os.open(result_name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        for name, payload in (('records.json', json_bytes), ('records.csv', csv_bytes),
                              ('manifest.json', manifest_bytes)):
            _write_file(result_fd, name, payload)
        os.fsync(result_fd)
        os.fsync(root_fd)
        success = True
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
    return {'code': 'P29_CATEGORY_PRICE_RULES_EXPORTED', 'result_name': result_name,
        'file_names': manifest['files'], **{key: view[key] for key in ('record_count',
            'product_count', 'sku_count', 'category_count', 'response_count')},
        'can_publish_complete_result': False, 'currency_inferred': False,
        'count_zero_means_no_threshold': False, 'zero_amount_means_free': False,
        'negative_adapted_as_amount': False, 'live_attempts_consumed': 0}


class _Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise CategoryCandidateError('P29_CATEGORY_ARGUMENTS_INVALID')


def main():
    parser = _Arguments(description=__doc__)
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--input-name', required=True, action='append')
    parser.add_argument('--result-name')
    parser.add_argument('--price-evidence', action='store_true')
    parser.add_argument('--price-rules', action='store_true')
    try:
        args = parser.parse_args()
        if args.price_evidence and args.price_rules:
            raise CategoryCandidateError('P29_CATEGORY_ARGUMENTS_INVALID')
        publish = (publish_category_price_rules if args.price_rules else
                   publish_category_price if args.price_evidence else publish_category_candidates)
        result = publish(Path(args.output_root), args.input_name, args.result_name)
    except (CategoryCandidateError, ReceiverControlError, ResultPublishError) as error:
        print(json.dumps({'code': error.code})); return 1
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({'code': 'P29_CATEGORY_EXPORT_INVALID'})); return 1
    print(json.dumps(result, ensure_ascii=True)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
