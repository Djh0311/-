"""Review named current public inventories without opening a live receiver.

Only counts and missing facts are returned. Candidate rows never enter the
complete-observation publisher, and this command consumes no live attempt.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource

from parser_candidate.p29_category_profile import (FAMILY, VERSION, PATHS,
    CategoryCandidateError, CategoryCandidateRow, parse_category_public_values)
from collection_core.p29 import MAX_COLLECTION_BYTES, MAX_OBSERVATIONS, MAX_ROWS
from .p26_identification_host import _read_owned
from .p29_receiver_control import _root, read_events, ReceiverControlError

_INPUT = re.compile(r'category_render_[a-f0-9]{32}-public-fields\.json')


@dataclass(frozen=True)
class CategoryCandidateObservation:
    source_file: str
    source_request_ref: str
    observed_at: str
    candidate: CategoryCandidateRow


def _window_started(root, state, window_ref):
    if state.get('output_root') != str(root):
        return False
    try:
        reservation = _read_owned(root / ('result-attempt-' + window_ref.split(':')[1] + '.lock'))
    except FileNotFoundError:
        # The forwarded-copy entry records the actual start in its owned event
        # file, rather than creating the legacy result reservation. That event
        # remains available after the receiver and its transient lock close.
        receipt = _read_owned(root / 'receiver-process.json')
        if (receipt.get('schema_version') != 'p29-owned-receiver-process/v1'
                or receipt.get('output_root') != str(root)
                or receipt.get('input_mode') != 'FORWARDED_COPY'
                or state.get('result_attempts') != 1):
            return False
        starts = [e for e in read_events(root) if e.get('event') == 'P29_FORWARDING_STARTED']
        if len(starts) != 1:
            return False
        started = starts[0]
        diagnostic = started.get('diagnostic')
        return (started.get('input_mode') == 'FORWARDED_COPY'
                and started.get('transport_started') is True
                and started.get('new_attempts') == 1
                and type(diagnostic) is dict
                and diagnostic.get('window_ref') == window_ref
                and diagnostic.get('state') == 'ACTIVE'
                and diagnostic.get('result_attempts') == 1
                and diagnostic.get('live_capture_latch') == 'OPEN'
                and diagnostic.get('execution_latch') == 'OPEN')
    return (reservation.get('schema_version') == 'p26-attempt-reservation/v1'
            and reservation.get('window_ref') == window_ref)


def review_category_inventory(root, input_name):
    root = _root(root)
    if type(input_name) is not str or _INPUT.fullmatch(input_name) is None:
        raise CategoryCandidateError('P29_CATEGORY_INPUT_INVALID')
    document = _read_owned(root / input_name, 4 * 1024 * 1024)
    schema_root = Path(__file__).resolve().parents[1] / 'contracts/schemas'
    resources = {p.name: Resource.from_contents(json.loads(p.read_text()))
                 for p in schema_root.glob('*.schema.json')}
    def local(uri):
        if uri in resources:
            return resources[uri]
        raise NoSuchResource(ref=uri)
    registry = Registry(retrieve=local).with_resources(resources.items())
    version = document.get('schema_version')
    versions = {'p29-category-render-inspection/v1': 'v1',
                'p29-category-render-inspection/v2': 'v2',
                'p29-category-render-inspection/v3': 'v3',
                'p29-category-render-inspection/v4': 'v4'}
    if type(version) is not str or version not in versions:
        raise CategoryCandidateError('P29_CATEGORY_INPUT_INVALID')
    validator = Draft202012Validator(json.loads(
        (schema_root/('p29-category-render-inspection-' + versions[version] + '.schema.json')).read_text()),
        registry=registry, format_checker=FormatChecker())
    if not validator.is_valid(document):
        raise CategoryCandidateError('P29_CATEGORY_INPUT_INVALID')
    state = _read_owned(root / 'transport-state.json')
    if not _window_started(root, state, document['window_ref']):
        raise CategoryCandidateError('P29_CATEGORY_WINDOW_MISMATCH')
    code_status = document.get('response_code_status', 'UNOBSERVED')
    if code_status not in ('ZERO', 'UNOBSERVED'):
        raise CategoryCandidateError('P29_CATEGORY_RESPONSE_NOT_SUCCESS')
    rows = parse_category_public_values(document['public_analysis'])
    unconfirmed = ['FRESH_MERCHANT_IDENTITY', 'CATEGORY_NAME',
                   'PRICE_CURRENCY_AND_UNIT', 'CATEGORY_TERMINATION']
    if code_status == 'UNOBSERVED':
        unconfirmed.insert(0, 'RESPONSE_SUCCESS_CODE')
    report = {'schema_version': 'p29-category-candidate-review/v1',
        'source_file': input_name, 'window_ref': document['window_ref'],
        'source_request_ref': document['source_request_ref'], 'observed_at': document['observed_at'],
        'profile_family': FAMILY, 'profile_version': VERSION,
        'profile_kind': 'LOCAL_OBSERVED_CANDIDATE_RULES',
        'shop_scope_verified': True,
        'source_context_age_within_10_seconds': document['source_context_age_within_10_seconds'],
        'response_code_status': code_status,
        'candidate_row_count': len(rows), 'product_count': len({r.product_id for r in rows}),
        'sku_count': len({r.sku_id for r in rows}), 'category_count': len({r.category_ref for r in rows}),
        'mapping_paths': sorted(PATHS), 'business_result_rows_added': 0,
        'can_publish_complete_result': False, 'coverage_status': 'PARTIAL',
        'unconfirmed_facts': unconfirmed,
        'raw_payload_read': False, 'business_values_in_report': False,
        'sensitive_values_processed': False, 'product_result': 'incomplete'}
    return report, rows


def review_category_batch(root, input_names):
    """Review explicitly named inventories; retain each selected row's source.

    Selection copies the whole candidate from its latest own observation. No
    merchant/category label, currency or optional field is filled from another
    response. The result remains unsuitable for the complete-record publisher.
    """
    if (type(input_names) not in (list, tuple) or not input_names
            or len(input_names) > MAX_OBSERVATIONS
            or any(type(name) is not str or _INPUT.fullmatch(name) is None
                   for name in input_names)
            or len(set(input_names)) != len(input_names)):
        raise CategoryCandidateError('P29_CATEGORY_BATCH_INPUT_INVALID')
    root = _root(root)
    sources, input_rows, input_bytes = [], 0, 0
    windows, requests = set(), set()
    for name in input_names:
        try:
            input_bytes += (root / name).lstat().st_size
        except OSError:
            raise CategoryCandidateError('P29_CATEGORY_INPUT_INVALID') from None
        if input_bytes > MAX_COLLECTION_BYTES:
            raise CategoryCandidateError('P29_CATEGORY_BATCH_BUDGET')
        report, rows = review_category_inventory(root, name)
        input_rows += len(rows)
        if input_rows > MAX_ROWS:
            raise CategoryCandidateError('P29_CATEGORY_BATCH_BUDGET')
        windows.add(report['window_ref'])
        if len(windows) != 1 or report['source_request_ref'] in requests:
            raise CategoryCandidateError('P29_CATEGORY_BATCH_SOURCE_INVALID')
        requests.add(report['source_request_ref'])
        observed = datetime.fromisoformat(report['observed_at'].replace('Z', '+00:00'))
        sources.append((observed, report, rows))
    sources.sort(key=lambda item: (item[0], item[1]['source_request_ref']))
    selected, owners = {}, {}
    code_counts = {'ZERO': 0, 'UNOBSERVED': 0}
    for observed, report, rows in sources:
        code_counts[report['response_code_status']] += 1
        for row in rows:
            if row.sku_id in owners and owners[row.sku_id] != row.product_id:
                raise CategoryCandidateError('P29_CATEGORY_SKU_OWNER_CHANGED')
            owners[row.sku_id] = row.product_id
            key = (row.category_ref, row.sku_id)
            previous = selected.get(key)
            if (previous is not None and previous[0] == observed
                    and previous[1].candidate != row):
                raise CategoryCandidateError('P29_CATEGORY_BATCH_ORDER_AMBIGUOUS')
            selected[key] = (observed, CategoryCandidateObservation(
                report['source_file'], report['source_request_ref'], report['observed_at'], row))
    result_rows = tuple(selected[key][1] for key in sorted(selected))
    category_count = len({r.candidate.category_ref for r in result_rows})
    if category_count > 256:
        raise CategoryCandidateError('P29_CATEGORY_BATCH_BUDGET')
    report = {'schema_version': 'p29-category-candidate-batch-review/v1',
        'window_ref': sources[0][1]['window_ref'], 'profile_family': FAMILY,
        'profile_version': VERSION, 'profile_kind': 'LOCAL_OBSERVED_CANDIDATE_RULES',
        'response_count': len(sources), 'input_candidate_rows': input_rows,
        'candidate_row_count': len(result_rows),
        'deduplicated_candidate_rows': input_rows - len(result_rows),
        'product_count': len({r.candidate.product_id for r in result_rows}),
        'sku_count': len({r.candidate.sku_id for r in result_rows}),
        'category_count': category_count,
        'fresh_source_context_response_count': sum(
            r['source_context_age_within_10_seconds'] for _, r, _ in sources),
        'response_code_status_counts': code_counts,
        'deduplication': 'LATEST_OWN_CANDIDATE_PER_SKU_CATEGORY',
        'sources': [r for _, r, _ in sources],
        'source_observation_time_preserved': True, 'cross_observation_fields_copied': False,
        'business_result_rows_added': 0, 'can_publish_complete_result': False,
        'coverage_status': 'PARTIAL', 'raw_payload_read': False,
        'business_values_in_report': False, 'sensitive_values_processed': False,
        'product_result': 'incomplete'}
    return report, result_rows


class _Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise CategoryCandidateError('P29_CATEGORY_ARGUMENTS_INVALID')


def main():
    parser = _Arguments(description=__doc__)
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--input-name', required=True, action='append')
    try:
        args = parser.parse_args()
        report, _ = (review_category_inventory(Path(args.output_root), args.input_name[0])
                     if len(args.input_name) == 1 else
                     review_category_batch(Path(args.output_root), args.input_name))
    except (CategoryCandidateError, ReceiverControlError) as error:
        print(json.dumps({'code': error.code})); return 1
    except Exception:
        print(json.dumps({'code': 'P29_CATEGORY_REVIEW_FAILED'})); return 1
    print(json.dumps(report, ensure_ascii=True, sort_keys=True)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
