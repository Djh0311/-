import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from collection_adapter.p29_store_pages import P29StorePagesWindow
from collection_adapter.p29_category_render import RENDER_ROUTE, response_code_status
from collection_adapter.p26_public_projection import FOOD_ROUTE, PRODUCT_ROUTE, PUBLIC_PATHS
from collection_adapter.p26_request_metadata import form_keys
from collection_adapter.p26_identification_host import IdentificationAddon
from collection_adapter.tests import test_p29_store_pages as store_tests


class CategoryRenderTests(unittest.TestCase):
    pair = store_tests.StorePagesTests.pair
    response = store_tests.StorePagesTests.response

    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.root.chmod(0o700)
        self.now = [100.0]
        self.window = P29StorePagesWindow('Synthetic batch shop', self.root,
            'authorization:synthetic_p29', clock=lambda: self.now[0],
            duration_seconds=None, identify_category_render=True)
        self.window.routes = [('POST', 'wx.waimai.meituan.com', r)
                              for r in (FOOD_ROUTE, PRODUCT_ROUTE, RENDER_ROUTE)]
        self.window.route_origins = dict.fromkeys(range(3), 'wx.waimai.meituan.com')
        self.window.selected_routes = set(range(3))
        self.window.allowed_domains = {'wx.waimai.meituan.com'}
        self.window.key_layout_only = self.window.sensitive_key_layout_authorized = True
        self.window.public_projection_enabled = True
        self.window.public_projection_paths = {**PUBLIC_PATHS, RENDER_ROUTE: frozenset()}
        self.window.start_once()

    def lease(self, body=b'poi_id_str=public_synthetic_42&wm_poi_id=-42'):
        ref = 'request:' + uuid4().hex
        self.window.request_leases[ref] = {'body': body, 'keys': form_keys(body),
            'route_slot': 2, 'expires_at': self.now[0]+60}
        return ref

    def render(self, ref=None, body=None):
        ref = ref or self.lease()
        if self.window.authorize_category_request(2, ref):
            collector = self.window.begin_response(2, 'identity', source_request_ref=ref)
            collector.feed(body or b'{"data":{"synthetic_products":[{"id":101,"price":15.2}]}}')
            collector.feed(b'')
        return ref

    def test_current_pair_then_render_is_inventory_and_never_a_complete_record(self):
        self.pair(); self.now[0] += 30
        count = self.window.published_count; parsed = self.window._parsed_total
        ref = self.render()
        result = json.loads(next(self.root.glob('category_render_*-public-fields.json')).read_text())
        self.assertTrue(result['shop_scope_verified'])
        self.assertFalse(result['source_context_age_within_10_seconds'])
        self.assertFalse(result['same_observation_record_ready'])
        self.assertEqual(result['payload_version'], 'UNKNOWN')
        self.assertEqual(result['business_record_count'], 0)
        self.assertEqual((self.window.published_count, self.window._parsed_total), (count, parsed))
        self.assertEqual(len(self.window.snapshots), 1)
        self.assertNotIn(ref, self.window.request_leases)

    def test_no_current_shop_context_denies_before_response_decoding(self):
        ref = self.lease()
        with patch('collection_adapter.p29_category_render.analyze_public_body') as decode:
            self.assertFalse(self.window.authorize_category_request(2, ref))
            self.window._consume(2, b'must not decode', source_request_ref=ref)
        decode.assert_not_called()
        self.assertFalse(list(self.root.iterdir()))

    def test_wrong_either_shop_id_missing_or_expired_request_denies_before_body(self):
        self.pair()
        for body in (b'poi_id_str=other_synthetic&wm_poi_id=-42',
                     b'poi_id_str=public_synthetic_42&wm_poi_id=-43',
                     b'wm_poi_id=-42'):
            ref = self.lease(body)
            with patch('collection_adapter.p29_category_render.analyze_public_body') as decode:
                self.assertFalse(self.window.authorize_category_request(2, ref))
                self.window._consume(2, b'must not decode', source_request_ref=ref)
            decode.assert_not_called()
        ref = self.lease(); self.now[0] += 61
        self.assertFalse(self.window.authorize_category_request(2, ref))
        self.assertFalse(list(self.root.glob('category_render_*')))

    def test_private_form_and_response_branches_remain_opaque(self):
        self.pair()
        ref = self.lease(b'poi_id_str=public_synthetic_42&wm_poi_id=-42&session=%FF&cookie=%FF')
        self.render(ref, b'{"data":{"synthetic_products":[{"name":"Synthetic render"}],'
                    b'"session":{"nested":"synthetic private sentinel"}}}')
        text = next(self.root.glob('category_render_*-public-fields.json')).read_text()
        self.assertNotIn('synthetic private sentinel', text)
        self.assertNotIn('%FF', text)
        self.assertTrue(self.window.active())
        self.assertFalse(json.loads(text)['sensitive_values_processed'])

    def test_request_reference_cannot_be_reused(self):
        self.pair(); ref = self.render()
        self.window.request_leases[ref] = {'body': b'poi_id_str=public_synthetic_42&wm_poi_id=-42',
            'keys': ['poi_id_str', 'wm_poi_id'], 'route_slot': 2, 'expires_at': self.now[0]+60}
        with patch('collection_adapter.p29_category_render.analyze_public_body') as decode:
            self.assertFalse(self.window.authorize_category_request(2, ref))
            self.window._consume(2, b'must not decode', source_request_ref=ref)
        decode.assert_not_called()
        self.assertEqual(len(list(self.root.glob('category_render_*-public-fields.json'))), 1)

    def test_completed_rejected_form_requests_do_not_exhaust_concurrent_collectors(self):
        self.pair()
        addon = IdentificationAddon(self.window, batch_public_json=True, detached_analysis=False)
        addon.reported_routes.update(range(3))
        with patch('collection_adapter.p29_category_render.analyze_public_body') as decode:
            for _ in range(12):
                flow = SimpleNamespace(id=uuid4().hex,
                    client_conn=SimpleNamespace(sni='wx.waimai.meituan.com'),
                    request=SimpleNamespace(method='POST', host='wx.waimai.meituan.com',
                        path=RENDER_ROUTE, stream=None,
                        headers={'content-type': 'application/x-www-form-urlencoded'}),
                    response=SimpleNamespace(stream=None, status_code=200,
                        headers={'content-type': 'application/json'}))
                addon.requestheaders(flow)
                self.assertTrue(callable(flow.request.stream), self.window.code)
                flow.request.stream(b'poi_id_str=other_synthetic&wm_poi_id=-42')
                flow.request.stream(b'')
                addon.request(flow)
                addon.responseheaders(flow)
                self.assertIs(flow.response.stream, True)
                addon.response(flow)
                self.assertTrue(self.window.active(), self.window.code)
                self.assertLessEqual(len(self.window.collectors), 8)
        decode.assert_not_called()
        self.assertEqual(self.window.render_inspector.rejected, 12)
        self.assertFalse(self.window.request_leases)
        self.window.close('P26_CANCELLED')
        self.assertEqual(self.window.collection_receipt['complete_observations'], 1)

    def test_eight_unfinished_form_collectors_still_close_on_next_request(self):
        from collection_adapter.p26_request_metadata import RequestBudget, begin_form_metadata
        budget = RequestBudget(self.window)
        for _ in range(8):
            collector = begin_form_metadata(self.window, budget,
                'request:' + uuid4().hex, 2, [])
            self.assertIsNotNone(collector)
            collector.feed(b'poi_id_str=synthetic_pending')
        self.assertIsNone(begin_form_metadata(self.window, budget,
            'request:' + uuid4().hex, 2, []))
        self.assertEqual(self.window.code, 'P26_RESPONSE_COUNT_LIMIT')
        self.assertTrue(all(c.finished and not c.buffer for c in self.window.collectors))

    def test_other_store_and_non_json_headers_never_enable_body_copy(self):
        self.pair(); addon = IdentificationAddon(self.window, batch_public_json=True, detached_analysis=False)
        for body, content_type in ((b'poi_id_str=other_synthetic&wm_poi_id=-42', 'application/json'),
                                    (b'poi_id_str=public_synthetic_42&wm_poi_id=-42', 'text/html')):
            ref = self.lease(body); flow_id = uuid4().hex
            addon.route_slots[flow_id] = 2; addon.request_refs[flow_id] = ref
            flow = SimpleNamespace(id=flow_id, response=SimpleNamespace(stream=None,
                status_code=200, headers={'content-type': content_type}))
            addon.responseheaders(flow)
            self.assertIs(flow.response.stream, True)
        self.assertFalse(list(self.root.glob('category_render_*')))

    def test_exact_route_is_explicit_and_other_methods_or_hosts_are_ignored(self):
        addon = IdentificationAddon(self.window, batch_public_json=True, detached_analysis=False)
        self.assertTrue(addon._business_candidate(2))
        self.window.routes[2] = ('GET', 'wx.waimai.meituan.com', RENDER_ROUTE)
        self.assertFalse(addon._business_candidate(2))
        self.window.routes[2] = ('POST', 'other.invalid', RENDER_ROUTE)
        self.window.route_origins[2] = 'other.invalid'
        self.assertFalse(addon._business_candidate(2))
        self.window.routes[2] = ('POST', 'hcapi-wx.waimai.meituan.com', RENDER_ROUTE)
        self.window.route_origins[2] = 'hcapi-wx.waimai.meituan.com'
        self.assertTrue(addon._business_candidate(2))
        self.window.routes[2] = ('POST', 'img.meituan.net', RENDER_ROUTE)
        self.window.route_origins[2] = 'img.meituan.net'
        self.assertFalse(addon._business_candidate(2))

    def test_shared_budget_closes_and_clears_proof_preserving_completed_results(self):
        self.pair(); self.render()
        with patch('collection_adapter.p29_store_pages.MAX_OBSERVATIONS', 2):
            self.render()
        self.assertEqual(self.window.code, 'P26_TOTAL_SIZE_LIMIT')
        self.assertEqual(len(list(self.root.glob('category_render_*-public-fields.json'))), 1)
        self.assertEqual(len(self.window.snapshots), 1)
        self.assertIsNotNone(self.window.collection_receipt)
        inspector = self.window.render_inspector
        self.assertIsNone(inspector.target)
        self.assertFalse(inspector.authorized or inspector.consumed or self.window.request_leases)

    def test_cancel_cleans_proof_and_never_adds_identification_records_to_collection(self):
        self.pair(); self.render(); self.window.close('P26_CANCELLED')
        self.assertEqual(self.window.collection_receipt['complete_observations'], 1)
        self.assertEqual(self.window.render_inspector.diagnostic()['business_records_from_render'], 0)
        self.assertIsNone(self.window.render_inspector.target)
        self.assertFalse(self.window.render_inspector.authorized)

    def test_closed_contracts_are_local_and_refuse_extra_values(self):
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
        schemas = Path(__file__).parents[2]/'contracts/schemas'
        registry = Registry().with_resources((p.name, Resource.from_contents(json.loads(p.read_text())))
                                            for p in schemas.glob('*.schema.json'))
        self.pair(); self.render()
        v = json.loads(next(self.root.glob('category_render_*-public-fields.json')).read_text())
        validator = Draft202012Validator(json.loads((schemas/'p29-category-render-inspection-v2.schema.json').read_text()),
                                          registry=registry, format_checker=FormatChecker())
        self.assertTrue(validator.is_valid(v))
        self.assertFalse(validator.is_valid({**v, 'raw': 'synthetic raw sentinel'}))
        self.assertFalse(validator.is_valid({**v, 'same_observation_record_ready': True}))
        diag = Draft202012Validator(json.loads((schemas/'p29-store-pages-diagnostic-v1.schema.json').read_text()),
                                     registry=registry, format_checker=FormatChecker())
        self.assertTrue(diag.is_valid(self.window.diagnostic()))
        self.window.close('P26_CANCELLED')
        self.assertTrue(diag.is_valid(self.window.diagnostic()))

    def test_root_code_is_fixed_metadata_with_no_private_text(self):
        for body, expected in ((b'{"code":0,"data":{"session":{"token":"synthetic private sentinel"}}}', 'ZERO'),
                               (b'{"code":7,"data":{}}', 'NONZERO'),
                               (b'{"data":{}}', 'ABSENT'),
                               (b'{"code":true,"data":{}}', 'INVALID_TYPE'),
                               (b'{"code":{"nested":"synthetic private sentinel"},"data":{}}', 'INVALID_TYPE')):
            self.assertEqual(response_code_status(body), expected)
        self.pair()
        self.render(body=b'{"code":0,"data":{"synthetic_products":[{"id":101,"price":15.2}],'
                    b'"session":{"token":"synthetic private sentinel"}}}')
        text = next(self.root.glob('category_render_*-public-fields.json')).read_text()
        v = json.loads(text)
        self.assertEqual((v['schema_version'], v['response_code_status']), ('p29-category-render-inspection/v2', 'ZERO'))
        self.assertNotIn('synthetic private sentinel', text)
        self.assertFalse(v['same_observation_record_ready'])
        self.window.close('P26_CANCELLED')


if __name__ == '__main__':
    unittest.main()
