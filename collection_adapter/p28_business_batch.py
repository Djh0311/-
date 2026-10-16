"""Analyze fresh target-verified response pairs without persisting raw bodies.

The lexical reader keeps private branches opaque. Newly observed public scalar
paths are inventory candidates; their meanings are never inferred from names.
"""

from dataclasses import fields
import json
import re
from uuid import uuid4

from collection_core.p0 import P0Context
from collection_core.p28 import P28Error, build_p28_batch
from collection_core.p28_result_views import render_p28_result
from collection_core.result_publisher import ResultPublishError, publish_result_set
from parser_candidate import CaptureParserEvent
from parser_candidate.p28_profile import FAMILY, VERSION, p28_registry
from .p26_identification import IdentificationError, IdentificationWindow, key_only_layout, structure_budget_error
from .p26_structure_budget import record_failure
from .p26_public_projection import FOOD_ROUTE, PRODUCT_ROUTE, is_business_origin
from .p26_result_mapping import check_current_association, restore_projection
from .p28_projection_review import PATHS
from .observation_time import observation_clock

MAX_BATCH_BYTES = 4 * 1024 * 1024
MAX_BATCH_VALUES = 8000
_PATH = re.compile(r"^\$\.data(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\])*)+$")


def analyze_public_body(body):
    """Two passes: opaque privacy/shape scan, then bounded public scalars."""
    restricted = []
    definitions, categories = key_only_layout(body, restricted_fields=restricted)
    paths = frozenset(row['path'] for row in definitions
                      if row['type'] in {'string', 'number', 'boolean', 'null'}
                      and _PATH.fullmatch(row['path']))
    values, unavailable = [], []
    key_only_layout(body, restricted_fields=[], public_paths=paths,
                    public_values=values, public_failures=unavailable,
                    max_public_paths=1024)
    if len(values) > MAX_BATCH_VALUES:
        raise structure_budget_error('PUBLIC_VALUES', len(values), 'PUBLIC_PROJECTION')
    document = {'fields': definitions, 'public_values': values,
                'unavailable_fields': unavailable, 'restricted_fields': restricted,
                'sensitive_rejections': categories,
                'field_meanings': 'DEVELOPER_REVIEW_REQUIRED',
                'sensitive_values_processed': False, 'raw_payload_persisted': False}
    if len(json.dumps(document, ensure_ascii=True).encode()) > MAX_BATCH_BYTES:
        raise IdentificationError('P26_TOTAL_SIZE_LIMIT')
    return document


def association_ready(check):
    required = ('store_name_match', 'food_success_code', 'product_success_code',
                'same_observation_gap_valid', 'public_string_id_ready',
                'food_poi_id_str_matches_public_string_id',
                'product_poi_id_str_matches_public_string_id',
                'poi_id_str_equal_between_requests', 'food_wm_poi_id_matches_numeric_id',
                'product_wm_poi_id_matches_numeric_id', 'wm_poi_id_equal_between_requests')
    return (type(check) is dict and check.get('merchant_container') == '$.data.poi_info'
            and all(check.get(k) is True for k in required))


class P28BusinessBatchWindow(IdentificationWindow):
    """One fresh, full response pair; scope remains CURRENT_RESPONSES_ONLY."""

    phase = 'RESULT'

    def __init__(self, expected_store, root, authorization_ref, **kwargs):
        super().__init__(expected_store, **kwargs)
        self.window_ref = 'result:' + uuid4().hex
        self.code = 'P26_RESULT_NOT_STARTED'
        self.root, self.authorization_ref = root, authorization_ref
        self._bodies = {}
        self.batch_receipt = None
        self.association_check = None
        self.qualified_count = self.parsed_count = 0
        self.published_count = 0

    def start_once(self):
        super().start_once()
        self.code = 'P26_RESULT_RECEIVING'

    def _consume(self, route, body, *, source_request_ref=None):
        super()._consume(route, body, source_request_ref=source_request_ref)
        if not self.active():
            return
        route_path = self.routes[route][2]
        if route_path not in PATHS or not is_business_origin(self.route_origins[route]):
            return
        if self.routes[route][0] != 'POST':
            self.close('P26_RESULT_EVENT_SET_INVALID')
            return
        self._bodies = {k: v for k, v in self._bodies.items()
                        if self.last_clock - v[0] <= 10}
        self._bodies[route_path] = (observation_clock(self.last_clock), body, source_request_ref)
        if set(self._bodies) != set(PATHS):
            return
        try:
            self.association_check = None
            check = check_current_association(self)
            self.association_check = check
            qualified_check = self._qualify_association(check)
            if qualified_check is None:
                self._association_failed(check)
                raise IdentificationError('P26_RESULT_SOURCE_ASSOCIATION_INVALID')
            check = qualified_check
            rows = {self.routes[r['route_slot']][2]: r for r in self.projected_observations}
            if (set(rows) != set(PATHS)
                    or any(rows[r]['source_request_ref'] != self._bodies[r][2] for r in PATHS)):
                raise IdentificationError('P26_RESULT_EVENT_SET_INVALID')
            self._record_qualified_pair()
            analyzed = {r: analyze_public_body(self._bodies[r][1]) for r in PATHS}
            if self._accept_empty_pair(analyzed, rows, check):
                return
            token = uuid4().hex
            refs = {f.name: f.name.removesuffix('_ref').replace('binding_context', 'context')
                    .replace('coverage_scope', 'scope').replace('_', '-') + ':' + token
                    for f in fields(P0Context) if f.name.endswith('_ref')}
            refs.update(authorization_ref=self.authorization_ref,
                        attempt_ref='attempt:' + self.window_ref.split(':')[1])
            evidence = {'schema_version': 'p28-price-evidence/v1',
                        'basis': 'USER_CONFIRMED_MULTI_SKU_PAGE',
                        'evidence_ref': refs['evidence_ref'], 'currency': 'CNY', 'amount_unit': 'YUAN'}
            context = P0Context(**refs, source_kind='SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE',
                                observed_at=rows[PRODUCT_ROUTE]['observed_at'])
            events = []
            for i, (r, endpoint) in enumerate(((FOOD_ROUTE, 'FOOD'), (PRODUCT_ROUTE, 'PRODUCTLIST')), 1):
                payload = restore_projection({**rows[r],
                    'values': [v for v in analyzed[r]['public_values'] if v['path'] in PATHS[r]]
                              + [v for v in rows[r]['values'] if v['path'] == '$.code'],
                    'unavailable_fields': [v for v in analyzed[r]['unavailable_fields'] if v['path'] in PATHS[r]]},
                    r, allowed_paths=PATHS[r])
                events.append(CaptureParserEvent(read_scope='READ_' + token, observation_scope='OBS_' + token,
                    event_index=i, endpoint_id=endpoint, payload_family=FAMILY, payload_version=VERSION, payload=payload))
            binding = build_p28_batch(events, p28_registry(), context, evidence)
            self._record_parsed_pair(len(binding['sku_records']))
            views = render_p28_result(binding)
            # A curated scalar/field inventory, never an original response dump.
            export = {'schema_version': 'p28-public-business-batch/v1', 'window_ref': self.window_ref,
                      'source_association': check, 'coverage': 'CURRENT_RESPONSES_ONLY',
                      'field_meanings': 'DEVELOPER_REVIEW_REQUIRED', 'observations': [
                          {'endpoint_id': endpoint, 'source_request_ref': rows[r]['source_request_ref'],
                           'observed_at': rows[r]['observed_at'], **analyzed[r]}
                          for r, endpoint in ((FOOD_ROUTE, 'FOOD'), (PRODUCT_ROUTE, 'PRODUCTLIST'))],
                      'sensitive_values_processed': False, 'raw_payload_persisted': False}
            if len(json.dumps(export, ensure_ascii=True).encode()) > MAX_BATCH_BYTES:
                raise IdentificationError('P26_TOTAL_SIZE_LIMIT')
            self._publish_pair(views, export)
        except IdentificationError as error:
            record_failure(self, error)
            self.close(error.code)
        except P28Error:
            self.close('P26_RESULT_PARSE_FAILED')
        except ResultPublishError:
            self.close('P26_RESULT_PUBLISH_FAILED')
        except Exception:
            self.close('P26_RESULT_ASSEMBLY_FAILED')

    def _association_failed(self, check):
        pass

    def _qualify_association(self, check):
        return check if association_ready(check) else None

    def _accept_empty_pair(self, analyzed, rows, check):
        return False

    def _record_qualified_pair(self):
        self.target_matches = self.qualified_count = 2

    def _record_parsed_pair(self, count):
        self.parsed_count = count

    def _publish_pair(self, views, export):
        from .p26_identification_host import _write_new
        _write_new(self.root, 'public-business-fields.json', export)
        summary = publish_result_set(str(self.root), 'first_result', views)
        self.published_count = summary['record_count']
        self.batch_receipt = {'source_association': export['source_association'], 'result_summary': summary,
            'public_field_path_count': sum(len(a['fields']) for a in export['observations']),
            'public_scalar_count': sum(len(a['public_values']) for a in export['observations']),
            'raw_payload_persisted': False, 'sensitive_values_processed': False}
        self.close('P26_RESULT_PUBLISHED')

    def active(self):
        active = super().active()
        if hasattr(self, '_bodies') and self.last_clock is not None:
            self._bodies = {k: v for k, v in self._bodies.items() if self.last_clock - v[0] <= 10}
        return active

    def close(self, code='P26_IDENTIFICATION_CLOSED'):
        self._bodies.clear()
        super().close(code)

    def diagnostic(self):
        result = super().diagnostic()
        result.update(schema_version='p26-result-diagnostic/v1',
                      identification_attempts=0, result_attempts=self.attempts,
                      execution_latch='OPEN' if self.state == 'ACTIVE' else 'CLOSED',
                      qualified_business_events=self.qualified_count,
                      parsed_records=self.parsed_count, published_records=self.published_count,
                      association_check=self.association_check)
        return result
