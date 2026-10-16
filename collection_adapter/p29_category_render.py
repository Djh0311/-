"""Identify the observed category route without claiming mapped SKU records.

The current window's completed merchant observation is used only to isolate
the shop. It never supplies missing fields to a rendered business record.
"""

from .observation_time import observation_time, observation_clock
from uuid import uuid4

from .p26_identification import IdentificationError, key_only_layout
from .p26_structure_budget import record_failure
from .p26_result_mapping import current_routing_id
from .p28_business_batch import analyze_public_body
from collection_core.p29_source_association import p29_association_ready, NUMERIC_VERSION

RENDER_ROUTE = '/weapp/poi/food/render'


def response_code_status(body):
    """Keep only a fixed root-code marker; private branches remain opaque."""
    values = []
    definitions, _ = key_only_layout(body, public_paths=frozenset({'$.code'}),
        public_values=values, public_failures=[], max_public_paths=1)
    codes = [v['value'] for v in values if v['coordinates'] == ['code']]
    if not codes:
        return 'INVALID_TYPE' if any(f['path'] == '$.code' for f in definitions) else 'ABSENT'
    if len(codes) != 1 or type(codes[0]) is not int:
        return 'INVALID_TYPE'
    return 'ZERO' if codes[0] == 0 else 'NONZERO'


class CategoryRenderInspector:
    def __init__(self, window):
        self.window = window
        self.target = None
        self.authorized = {}
        self.consumed = set()
        self.inspected = self.rejected = 0
        self.rejected_at_least = False
        self.last_scope_status = 'UNOBSERVED'
        self.last_scope_check = None

    def prepare_binding(self, export, result_name):
        if not p29_association_ready(export.get('source_association'), self.window.window_ref):
            raise IdentificationError('P26_RESULT_SOURCE_ASSOCIATION_INVALID')
        food = next(o for o in export['observations'] if o['endpoint_id'] == 'FOOD')
        values = {tuple(v['coordinates']): v['value'] for v in food['public_values']}
        numeric = values.get(('data', 'poi_info', 'id'))
        public = values.get(('data', 'poi_info', 'poi_id_str'))
        if type(numeric) is not int or type(public) is not str or not 1 <= len(public) <= 256:
            raise IdentificationError('P26_RESULT_SOURCE_ASSOCIATION_INVALID')
        selector = public
        version = export['source_association']['schema_version']
        if version == NUMERIC_VERSION:
            from .p29_store_identity import numeric_store_association
            if numeric_store_association(self.window, self.window.association_check) != export['source_association']:
                raise IdentificationError('P26_RESULT_SOURCE_ASSOCIATION_INVALID')
            row = next(r for r in self.window.projected_observations
                       if r['source_request_ref'] == food['source_request_ref'])
            selector = current_routing_id(self.window, row, 'poi_id_str')
        return {'wm_poi_id': str(numeric), 'poi_id_str': selector,
                'response_public_string': public, 'identity_version': version,
                'result_name': result_name, 'observed_at': food['observed_at'],
                'clock': observation_clock(self.window.last_clock)}

    def _reject(self, status, request_ref):
        self.last_scope_status = status
        if status != 'OTHER_STORE_REQUEST':
            self.last_scope_check = None
        self.rejected_at_least |= self.rejected >= 128
        self.rejected = min(128, self.rejected + 1)
        self.authorized.pop(request_ref, None)
        self.window.request_leases.pop(request_ref, None)
        return False

    def authorize(self, route, request_ref):
        self.last_scope_check = None
        if not self.window.active():
            return False
        if request_ref in self.consumed or request_ref in self.authorized:
            return self._reject('REQUEST_REUSED', request_ref)
        if self.target is None:
            return self._reject('CURRENT_STORE_CONTEXT_REQUIRED', request_ref)
        lease = self.window.request_leases.get(request_ref)
        if (not lease or lease.get('route_slot') != route
                or lease.get('expires_at', 0) <= self.window.last_clock
                or not {'poi_id_str', 'wm_poi_id'} <= set(lease.get('keys', []))):
            return self._reject('CURRENT_REQUEST_IDS_REQUIRED', request_ref)
        try:
            row = {'route_slot': route, 'source_request_ref': request_ref}
            current = {key: current_routing_id(self.window, row, key)
                       for key in ('poi_id_str', 'wm_poi_id')}
            self.last_scope_check = {
                'request_string_matches_context_selector': current['poi_id_str'] == self.target['poi_id_str'],
                'request_numeric_matches_context_numeric': current['wm_poi_id'] == self.target['wm_poi_id'],
                'request_string_matches_response_public_string': current['poi_id_str'] == self.target['response_public_string']}
            # Category routing uses the current response's public string ID,
            # not the distinct selector shared by the initial request pair.
            # Both current IDs must match; the selector remains diagnostic only.
            matches = (self.last_scope_check['request_string_matches_response_public_string']
                       and self.last_scope_check['request_numeric_matches_context_numeric'])
        except IdentificationError:
            return self._reject('CURRENT_REQUEST_IDS_REQUIRED', request_ref)
        if not matches:
            return self._reject('OTHER_STORE_REQUEST', request_ref)
        self.authorized[request_ref] = {
            'result_name': self.target['result_name'], 'observed_at': self.target['observed_at'],
            'identity_version': self.target['identity_version'],
            'keys': list(lease['keys']),
            'age_within_10_seconds': 0 <= self.window.last_clock - self.target['clock'] <= 10}
        self.last_scope_status = 'MATCHED_CURRENT_STORE_REQUEST'
        return True

    def consume(self, route, body, request_ref):
        proof = self.authorized.get(request_ref)
        if not self.window.active() or proof is None or request_ref in self.consumed:
            return  # No raw decoding without the request's own authorization.
        try:
            analyzed = analyze_public_body(body)
            now = observation_time()
            from .p29_batch_parameter import inspect_current_batch_parameter
            parameter = {'schema_version': 'p29-category-batch-parameter-probe/v2',
                'window_ref': self.window.window_ref, 'source_request_ref': request_ref,
                'observed_at': now, 'route': RENDER_ROUTE,
                'source_context_result_name': proof['result_name'],
                'probe': inspect_current_batch_parameter(self.window, route, request_ref, analyzed)}
            if not self.window.active():
                return
            document = {
                'schema_version': 'p29-category-render-inspection/v2',
                'window_ref': self.window.window_ref, 'source_request_ref': request_ref,
                'route': RENDER_ROUTE, 'observed_at': now,
                'source_context_result_name': proof['result_name'],
                'source_context_observed_at': proof['observed_at'],
                'request_field_keys': proof['keys'], 'shop_scope_verified': True,
                'poi_id_str_matches_context': True, 'wm_poi_id_matches_context': True,
                'source_context_age_within_10_seconds': proof['age_within_10_seconds'],
                'response_code_status': response_code_status(body),
                'same_observation_record_ready': False,
                'payload_family': 'UNKNOWN', 'payload_version': 'UNKNOWN',
                'business_record_count': 0, 'coverage_status': 'PARTIAL',
                'public_analysis': analyzed,
                'raw_payload_persisted': False, 'sensitive_values_processed': False}
            if proof['identity_version'] == NUMERIC_VERSION:
                document.update(schema_version='p29-category-render-inspection/v4',
                    store_context_identity_basis='CURRENT_RESPONSE_NUMERIC_ID_MATCHES_BOTH_REQUESTS',
                    string_context_basis='CURRENT_RESPONSE_PUBLIC_STRING')
            size = self.window._check_budget({'inspection': document, 'batch_parameter': parameter})
            from .p26_identification_host import _write_new
            name = 'category_render_' + uuid4().hex + '-public-fields.json'
            _write_new(self.window.root, name, document)
            _write_new(self.window.root, name.removesuffix('-public-fields.json')
                       + '-batch-parameter.json', parameter)
            self.inspected += 1
            self.window._public_bytes += size
            for category, count in analyzed['sensitive_rejections'].items():
                self.window.sensitive_rejections[category] = min(
                    128, self.window.sensitive_rejections[category] + count)
            self.window.last_body_route = route
            self.window.code = 'P29_CATEGORY_RENDER_INSPECTED'
        except IdentificationError as error:
            record_failure(self.window, error)
            self.window.close(error.code)
        except Exception:
            self.window.close('P26_RESULT_ASSEMBLY_FAILED')
        finally:
            self.authorized.pop(request_ref, None)
            if self.window.state != 'CLOSED':
                self.consumed.add(request_ref)
            self.window.request_leases.pop(request_ref, None)

    def clear(self):
        self.target = None
        self.authorized.clear()
        self.consumed.clear()

    def diagnostic(self):
        return {'enabled': True, 'inspected_responses': self.inspected,
                'scope_rejected': self.rejected,
                'scope_rejections_at_least': self.rejected_at_least,
                'last_scope_status': self.last_scope_status,
                'last_scope_check': self.last_scope_check,
                'business_records_from_render': 0}
