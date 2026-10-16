"""Record fresh complete response pairs and their explicit category gaps.

This bounded processor consumes supplied response copies; it is not itself a
passive network source. It neither drives a UI nor replays requests. Unknown
page markers cannot establish whole-store completion.
"""

import json
from uuid import uuid4

from collection_core.p29 import (MAX_COLLECTION_BYTES, MAX_OBSERVATIONS, MAX_ROWS, P29Error,
    _category_check, render_collection, snapshot_from_views)
from collection_core.result_publisher import publish_result_set, ResultPublishError
from .p26_identification import IdentificationError
from .p26_public_projection import FOOD_ROUTE, PRODUCT_ROUTE, is_business_origin
from .p28_business_batch import P28BusinessBatchWindow


def categories_from_public_values(values):
    """Exact approved array coordinates only; never interpret count as a total."""
    categories = {}
    prefix = ['data', 'food_spu_tags']
    for row in values:
        c = row['coordinates']
        if c[:2] != prefix or len(c) < 4 or type(c[2]) is not int:
            continue
        out = categories.setdefault(c[2], {'category_ref': None, 'category_name': None,
            'source_page_number': None, 'source_has_next_page': None,
            'source_reported_product_count': None, 'loaded_product_ids': [],
            'folded_product_ids': [], 'page_semantics': 'UNCONFIRMED',
            'termination_semantics': 'UNCONFIRMED'})
        key = {'tag': 'category_ref', 'name': 'category_name', 'current_page': 'source_page_number',
               'has_next_page': 'source_has_next_page', 'product_count': 'source_reported_product_count'}
        if len(c) == 4 and c[3] in key:
            out[key[c[3]]] = row['value']
        elif len(c) == 5 and c[3] == 'fold_spu_ids' and type(c[4]) is int:
            if type(row['value']) is not int:
                raise P29Error('P29_COVERAGE_INVALID')
            out['folded_product_ids'].append(str(row['value']))
        elif len(c) == 6 and c[3] == 'dynamic_spus' and type(c[4]) is int and c[5] == 'id':
            if type(row['value']) is not int:
                raise P29Error('P29_COVERAGE_INVALID')
            out['loaded_product_ids'].append(str(row['value']))
    return [categories[i] for i in sorted(categories)]


class P29StorePagesWindow(P28BusinessBatchWindow):
    """Keep each complete pair; on close publish a canonical partial collection."""

    def __init__(self, *args, identify_category_render=False, numeric_store_binding=False,
                 copy_store_detail=False, **kwargs):
        if type(numeric_store_binding) is not bool or type(copy_store_detail) is not bool:
            raise IdentificationError('P26_MONITORING_SCOPE_INVALID')
        super().__init__(*args, **kwargs)
        self.numeric_store_binding = numeric_store_binding
        self.snapshots = []
        self.empty_count = self._qualified_total = self._parsed_total = 0
        self._public_bytes = 0
        self.collection_receipt = None
        self.last_result_name = None
        self._finalizing = False
        self._consumed_requests = set()
        self.render_inspector = None
        self.detail_copies = None
        if copy_store_detail:
            from .p29_store_detail import StoreDetailCopies
            self.detail_copies = StoreDetailCopies(self)
        if identify_category_render:
            from .p29_category_render import CategoryRenderInspector, RENDER_ROUTE
            self.render_inspector = CategoryRenderInspector(self)
            self.public_projection_paths[RENDER_ROUTE] = frozenset()

    def is_category_route(self, route):
        from .p29_category_render import RENDER_ROUTE
        return (self.render_inspector is not None and route is not None
                and self.routes[route][0] == 'POST'
                and is_business_origin(self.route_origins[route])
                and self.routes[route][2] == RENDER_ROUTE)

    def authorize_category_request(self, route, request_ref):
        return self.render_inspector.authorize(route, request_ref)

    def is_store_detail_route(self, route):
        from .p29_store_detail import DETAIL_ROUTE
        return (self.detail_copies is not None and route is not None
                and self.routes[route][0] == 'POST'
                and is_business_origin(self.route_origins[route])
                and self.routes[route][2] == DETAIL_ROUTE)

    def _consume(self, route, body, *, source_request_ref=None):
        if not self.active():
            return
        if self.is_store_detail_route(route):
            self.detail_copies.consume(route, body)
            return
        if self.is_category_route(route):
            self.render_inspector.consume(route, body, source_request_ref)
            return
        if source_request_ref in self._consumed_requests:
            self.close('P26_RESULT_EVENT_SET_INVALID')
            return
        super()._consume(route, body, source_request_ref=source_request_ref)

    def _release_pair(self):
        used = {value[2] for value in self._bodies.values()}
        self._consumed_requests.update(used)
        self._bodies.clear()
        self.projected_observations = [r for r in self.projected_observations
                                       if r['source_request_ref'] not in used]
        for ref in used:
            self.request_leases.pop(ref, None)
        self.qualified_count = self._qualified_total
        self.parsed_count = self._parsed_total
        self.target_matches_at_least = self._qualified_total > 8
        self.target_matches = min(8, self._qualified_total)
        self.code = 'P29_OBSERVATION_RECORDED'

    def _record_qualified_pair(self):
        self._qualified_total += 2
        self.target_matches_at_least = self._qualified_total > 8
        self.target_matches = min(8, self._qualified_total)

    def _record_parsed_pair(self, count):
        self._parsed_total += count

    def _check_budget(self, document):
        size = len(json.dumps(document, ensure_ascii=True).encode())
        inspected = self.render_inspector.inspected if self.render_inspector else 0
        inspected += self.detail_copies.saved if self.detail_copies else 0
        if (len(self.snapshots) + self.empty_count + inspected >= MAX_OBSERVATIONS
                or self._public_bytes + size > MAX_COLLECTION_BYTES):
            raise IdentificationError('P26_TOTAL_SIZE_LIMIT')
        return size

    def _association_failed(self, check):
        from .p29_id_relation import inspect_current_id_relation
        document = inspect_current_id_relation(self, check)
        if document is None:
            return
        size = self._check_budget(document)
        from .p26_identification_host import _write_new
        _write_new(self.root, 'routing_id_relation_' + uuid4().hex + '.json', document)
        self._public_bytes += size

    def _qualify_association(self, check):
        strict = super()._qualify_association(check)
        if strict is not None or not self.numeric_store_binding:
            return strict
        from .p29_store_identity import numeric_store_association
        return numeric_store_association(self, check)

    def _publish_pair(self, views, export):
        from .p26_identification_host import _write_new
        try:
            if export['source_association']['schema_version'] == 'p29-numeric-store-association/v1':
                export = {**export, 'schema_version': 'p29-public-business-batch/v1'}
                from .p28_business_batch import MAX_BATCH_BYTES
                if len(json.dumps(export, ensure_ascii=True).encode()) > MAX_BATCH_BYTES:
                    raise IdentificationError('P26_TOTAL_SIZE_LIMIT')
            product = next(o for o in export['observations'] if o['endpoint_id'] == 'PRODUCTLIST')
            categories = categories_from_public_values(product['public_values'])
            name = 'observation_' + uuid4().hex
            render_target = (self.render_inspector.prepare_binding(export, name)
                             if self.render_inspector else None)
            snapshot = snapshot_from_views(views, categories, export['source_association'], self.window_ref, name)
            size = self._check_budget(export)
            # Validate all previous source snapshots before opening a new destination.
            combined = render_collection([*self.snapshots, snapshot])
            summary = publish_result_set(str(self.root), name, views)
            _write_new(self.root, name + '-public-fields.json', export)
            self.snapshots.append(snapshot)
            self._public_bytes += size
            self.published_count = json.loads(combined.json_bytes)['record_count']
            self.last_result_name = name
            if self.render_inspector:
                self.render_inspector.target = render_target
            self._release_pair()
        except P29Error:
            raise IdentificationError('P26_RESULT_EVENT_SET_INVALID') from None

    def _accept_empty_pair(self, analyzed, rows, check):
        definitions = {(r['path'], r['type']) for r in analyzed[PRODUCT_ROUTE]['fields']}
        if ('$.data.food_spu_tags[].dynamic_spus', 'array') not in definitions:
            return False
        if ('$.data.food_spu_tags[].dynamic_spus[]', 'object') in definitions:
            return False
        try:
            categories = categories_from_public_values(analyzed[PRODUCT_ROUTE]['public_values'])
            _category_check(categories, [])
            document = {'schema_version': 'p29-empty-observation/v1', 'window_ref': self.window_ref,
                'source_association': check, 'observed_at': rows[PRODUCT_ROUTE]['observed_at'],
                'coverage_status': 'PARTIAL', 'business_record_count': 0,
                'empty_page_is_termination': False, 'categories': categories,
                'raw_payload_persisted': False, 'sensitive_values_processed': False}
            if check['schema_version'] == 'p29-numeric-store-association/v1':
                document['schema_version'] = 'p29-empty-observation/v2'
            size = self._check_budget(document)
            from .p26_identification_host import _write_new
            _write_new(self.root, 'empty_observation_' + uuid4().hex + '.json', document)
            self.empty_count += 1
            self._public_bytes += size
            self._release_pair()
            self.code = 'P29_EMPTY_OBSERVATION_RECORDED'
            return True
        except P29Error:
            raise IdentificationError('P26_RESULT_EVENT_SET_INVALID') from None

    def close(self, code='P26_IDENTIFICATION_CLOSED'):
        if self.state == 'CLOSED' or self._finalizing:
            return
        self._finalizing = True
        # Shut input and discard every raw/FORM lease before publishing the collection.
        super().close(code)
        if self.render_inspector:
            self.render_inspector.clear()
        if self.snapshots:
            try:
                views = render_collection(self.snapshots)
                summary = publish_result_set(str(self.root), 'collection_' + uuid4().hex, views)
                v = json.loads(views.json_bytes)
                self.collection_receipt = {'result_summary': summary,
                    'complete_observations': len(self.snapshots), 'empty_observations': self.empty_count,
                    'source_category_count': v['source_category_count'],
                    'folded_product_references_not_loaded': v['folded_product_references_not_loaded'],
                    'category_product_references_not_loaded': v['category_product_references_not_loaded'],
                    'coverage_status': 'PARTIAL', 'raw_payload_persisted': False,
                    'sensitive_values_processed': False}
                self.published_count = summary['record_count']
            except Exception:
                # Individual completed observations remain; never claim aggregate success.
                self.code = 'P26_RESULT_PUBLISH_FAILED'
        self._finalizing = False

    def diagnostic(self):
        result = super().diagnostic()
        pending = set(self._bodies)
        result.update(schema_version='p29-store-pages-diagnostic/v1',
            qualified_business_events=min(self._qualified_total, MAX_OBSERVATIONS * 2),
            qualified_business_events_at_least=self._qualified_total > MAX_OBSERVATIONS * 2,
            parsed_records=min(self._parsed_total, MAX_ROWS),
            parsed_records_at_least=self._parsed_total > MAX_ROWS,
            complete_observations=len(self.snapshots), empty_observations=self.empty_count,
            pending_pair=('FRESH_PAIR_PENDING' if len(pending) == 2 else
                          'FRESH_MERCHANT_PENDING' if PRODUCT_ROUTE in pending else
                          'FRESH_PRODUCTLIST_PENDING' if FOOD_ROUTE in pending else 'NO_PENDING_PAIR'),
            coverage_status='PARTIAL', aggregate_published=self.collection_receipt is not None)
        if self.render_inspector:
            result['category_render'] = self.render_inspector.diagnostic()
        if self.detail_copies:
            result['store_detail'] = self.detail_copies.diagnostic()
        return result
