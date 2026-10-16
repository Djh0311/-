import copy
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from collection_adapter.p26_public_projection import FOOD_ROUTE, PRODUCT_ROUTE, PUBLIC_PATHS
from collection_adapter.p29_category_render import RENDER_ROUTE
from collection_adapter.p29_store_pages import P29StorePagesWindow
from collection_adapter.tests.test_p28_business_batch import bodies


class NumericStoreBindingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.root.chmod(0o700)
        self.now = [100.0]
        self.window = self.make_window()

    def make_window(self, *, start=True, enabled=True):
        w = P29StorePagesWindow('Synthetic batch shop', self.root,
            'authorization:synthetic_numeric_binding', clock=lambda: self.now[0],
            duration_seconds=None, identify_category_render=True,
            numeric_store_binding=enabled)
        w.routes = [('POST', 'wx.waimai.meituan.com', r)
                    for r in (FOOD_ROUTE, PRODUCT_ROUTE, RENDER_ROUTE)]
        w.route_origins = dict.fromkeys(range(3), 'wx.waimai.meituan.com')
        w.selected_routes = set(range(3)); w.allowed_domains = {'wx.waimai.meituan.com'}
        w.key_layout_only = w.sensitive_key_layout_authorized = w.public_projection_enabled = True
        w.public_projection_paths = {**PUBLIC_PATHS, RENDER_ROUTE: frozenset()}
        if start: w.start_once()
        return w

    def response(self, slot, body, selector='synthetic_request_selector', numeric='-42', prefix=b''):
        ref = 'request:' + uuid4().hex
        self.window.request_leases[ref] = {
            'body': prefix + ('poi_id_str=' + selector + '&wm_poi_id=' + numeric).encode(),
            'keys': ['poi_id_str', 'wm_poi_id'], 'route_slot': slot,
            'expires_at': self.now[0] + 60}
        collector = self.window.begin_response(slot, 'identity', source_request_ref=ref)
        self.assertIsNotNone(collector)
        collector.feed(json.dumps(body).encode()); collector.feed(b'')
        return ref

    def pair(self):
        food, product = bodies()
        self.response(0, food); self.response(1, product)

    def exported(self):
        return json.loads(next(self.root.glob('observation_*-public-fields.json')).read_text())

    def validate(self, document, name):
        from collection_adapter.p29_store_inventory import _validate
        _validate(document, name)

    def test_distinct_strings_use_explicit_numeric_proof_and_preserve_raw_comparisons(self):
        self.pair()
        self.assertEqual(len(self.window.snapshots), 1)
        export = self.exported(); proof = export['source_association']
        self.assertEqual(export['schema_version'], 'p29-public-business-batch/v1')
        self.assertEqual(proof['schema_version'], 'p29-numeric-store-association/v1')
        self.assertFalse(proof['food_poi_id_str_matches_public_string_id'])
        self.assertFalse(proof['product_poi_id_str_matches_public_string_id'])
        self.assertEqual(proof['string_id_role'], 'UNCONFIRMED')
        self.assertEqual(self.window.diagnostic()['association_check']['schema_version'],
                         'p26-result-association-check/v1')
        self.validate(proof, 'p29-numeric-store-association-v1.schema.json')
        self.validate(export, 'p29-public-business-batch-v1.schema.json')
        self.assertNotIn('synthetic_request_selector', json.dumps(proof))
        self.assertFalse(self.window._bodies or self.window.request_leases or self.window.projected_observations)

    def test_disabled_rule_still_stops_with_original_code(self):
        self.window = self.make_window(enabled=False); self.pair()
        self.assertEqual(self.window.code, 'P26_RESULT_SOURCE_ASSOCIATION_INVALID')
        self.assertFalse(self.window.snapshots)

    def test_wrong_store_numeric_id_string_pair_or_success_denies_before_public_analysis(self):
        for reason in ('name', 'numeric', 'request_string_pair', 'success', 'float_numeric'):
            with self.subTest(reason=reason):
                self.window = self.make_window(); food, product = bodies()
                if reason == 'name': food['data']['poi_info']['name'] = 'Other synthetic shop'
                if reason == 'success': product['code'] = 9
                if reason == 'float_numeric': food['data']['poi_info']['id'] = -42.0
                numeric = '-99' if reason == 'numeric' else '-42.0' if reason == 'float_numeric' else '-42'
                other = 'synthetic_other_selector' if reason == 'request_string_pair' else 'synthetic_request_selector'
                with patch('collection_adapter.p28_business_batch.analyze_public_body') as analyze:
                    self.response(0, food, numeric=numeric)
                    self.response(1, product, other, numeric)
                analyze.assert_not_called()
                self.assertEqual(self.window.code, 'P26_RESULT_SOURCE_ASSOCIATION_INVALID')
                self.assertFalse(self.window.snapshots or self.window.request_leases or self.window._bodies)

    def test_prepare_and_expired_pair_never_consume_quota_or_publish(self):
        self.window = self.make_window(start=False)
        self.window._consume(0, b'must not decode')
        self.assertEqual((self.window.attempts, self.window.raw_callbacks), (0, 0))
        self.window = self.make_window(); food, product = bodies()
        self.response(0, food); self.now[0] += 11; self.response(1, product)
        self.assertFalse(self.window.snapshots)
        self.window.close('P26_CANCELLED')
        self.assertFalse(self.window.request_leases or self.window._bodies)

    def test_render_uses_response_public_string_and_rejects_initial_request_selector(self):
        self.pair()
        def lease(selector):
            ref = 'request:' + uuid4().hex
            self.window.request_leases[ref] = {
                'body': ('poi_id_str=' + selector + '&wm_poi_id=-42').encode(),
                'keys': ['poi_id_str', 'wm_poi_id'], 'route_slot': 2,
                'expires_at': self.now[0]+60}
            return ref
        good = lease('public_synthetic_42')
        self.assertTrue(self.window.authorize_category_request(2, good))
        self.assertEqual(self.window.render_inspector.last_scope_check, {
            'request_string_matches_context_selector': False,
            'request_numeric_matches_context_numeric': True,
            'request_string_matches_response_public_string': True})
        collector = self.window.begin_response(2, 'identity', source_request_ref=good)
        collector.feed(b'{"code":0,"data":{"synthetic_products":[{"id":101,"price":15.2}]}}')
        collector.feed(b'')
        document = json.loads(next(self.root.glob('category_render_*-public-fields.json')).read_text())
        self.assertEqual(document['schema_version'], 'p29-category-render-inspection/v4')
        self.assertEqual(document['string_context_basis'], 'CURRENT_RESPONSE_PUBLIC_STRING')
        self.assertEqual(document['business_record_count'], 0)
        self.assertFalse(document['same_observation_record_ready'])
        self.validate(document, 'p29-category-render-inspection-v4.schema.json')
        self.assertNotIn('synthetic_request_selector', json.dumps(document))
        self.assertEqual(len(self.window.snapshots), 1)
        bad = lease('synthetic_request_selector')
        with patch('collection_adapter.p29_category_render.analyze_public_body') as analyze:
            self.assertFalse(self.window.authorize_category_request(2, bad))
            self.window._consume(2, b'must not decode', source_request_ref=bad)
        analyze.assert_not_called()

    def test_collection_json_csv_and_manifest_have_explicit_version_and_cleanup(self):
        self.pair(); self.window.close('P26_CANCELLED')
        result = self.root / self.window.collection_receipt['result_summary']['result_name']
        view = json.loads((result/'records.json').read_text())
        manifest = json.loads((result/'manifest.json').read_text())
        self.assertEqual(view['schema_version'], 'collection-p29-result-view/v2')
        self.assertEqual(manifest['schema_version'], 'collection-p29-result-manifest/v2')
        self.validate(view, 'p29-result-view-v2.schema.json')
        self.validate(manifest, 'p29-result-manifest-v2.schema.json')
        import csv,io
        self.assertEqual(list(csv.DictReader(io.StringIO((result/'records.csv').read_text()))), view['records'])
        self.assertEqual(stat.S_IMODE(result.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE((result/n).stat().st_mode)==0o600
                            for n in ('records.json','records.csv','manifest.json')))
        self.assertIsNone(self.window.render_inspector.target)
        self.assertFalse(self.window._bodies or self.window.request_leases)

    def test_numeric_category_request_through_addon_probe_and_inventory_export(self):
        from types import SimpleNamespace
        from urllib.parse import quote_from_bytes
        from collection_adapter.p26_identification_host import IdentificationAddon, _write_new
        from collection_adapter.p29_store_inventory import publish_store_inventory
        from collection_adapter.tests.test_p29_category_review import synthetic_body
        self.pair()
        body = synthetic_body()
        body['data']['food_spu_tags'][0]['tag'] = 'category_a'
        parameter = [{'spuId': 101, 'tagId': 'category_a', 'childTagId': '', 'tagType': 1}]
        form = (b'poi_id_str=public_synthetic_42&wm_poi_id=-42&tag_spu_ids='
                + quote_from_bytes(json.dumps(parameter).encode()).encode() + b'&cookie=%FF')
        addon = IdentificationAddon(self.window, batch_public_json=True, detached_analysis=False)
        addon.reported_routes.update(range(3))
        flow = SimpleNamespace(id=uuid4().hex,
            client_conn=SimpleNamespace(sni='wx.waimai.meituan.com'),
            request=SimpleNamespace(method='POST', host='wx.waimai.meituan.com',
                path=RENDER_ROUTE, stream=None,
                headers={'content-type': 'application/x-www-form-urlencoded'}),
            response=SimpleNamespace(stream=None, status_code=200,
                headers={'content-type': 'application/json'}))
        addon.requestheaders(flow)
        flow.request.stream(form); flow.request.stream(b''); addon.request(flow)
        addon.responseheaders(flow)
        self.assertTrue(callable(flow.response.stream))
        flow.response.stream(json.dumps(body).encode()); flow.response.stream(b'')
        addon.response(flow)
        probe_file = next(self.root.glob('category_render_*-batch-parameter.json'))
        probe = json.loads(probe_file.read_text())
        self.assertEqual(probe['probe']['status'], 'STRUCTURE_OBSERVED')
        self.assertEqual(probe['probe']['array_item_relation']['status'], 'MATCHED_CURRENT_RESPONSE')
        self.assertNotIn('category_a', json.dumps(probe))
        self.assertNotIn('%FF', json.dumps(probe))
        category = next(self.root.glob('category_render_*-public-fields.json'))
        self.assertEqual(json.loads(category.read_text())['schema_version'],
                         'p29-category-render-inspection/v4')
        self.window.close('P26_CANCELLED')
        self.assertFalse(self.window.request_leases or self.window.render_inspector.authorized)
        _write_new(self.root, 'transport-state.json', {'output_root': str(self.root)})
        _write_new(self.root, 'result-attempt-' + self.window.window_ref.split(':')[1] + '.lock',
            {'schema_version': 'p26-attempt-reservation/v1', 'window_ref': self.window.window_ref})
        observation = next(p.name for p in self.root.iterdir()
                           if p.is_dir() and p.name.startswith('observation_'))
        with patch('collection_adapter.p29_store_inventory._root', return_value=self.root), \
                patch('collection_adapter.p29_category_review._root', return_value=self.root):
            result = publish_store_inventory(self.root, observation, [category.name])
        view = json.loads((self.root/result['result_name']/'records.json').read_text())
        self.assertEqual((view['record_count'], view['partial_category_rows']), (2, 2))
        self.assertFalse(view['complete_result_promotion'])
        self.assertFalse(view['cross_observation_prices_or_specs_copied'])
        self.assertEqual(self.window.collection_receipt['result_summary']['record_count'], 2)

    def test_numeric_batch_probe_rechecks_both_ids_before_parameter_decoding(self):
        from collection_adapter.p29_batch_parameter import inspect_current_batch_parameter
        self.pair()
        for body in (b'poi_id_str=synthetic_request_selector&wm_poi_id=-42',
                     b'poi_id_str=public_synthetic_42&wm_poi_id=-99'):
            ref = 'request:' + uuid4().hex
            self.window.request_leases[ref] = {
                'body': b'poi_id_str=public_synthetic_42&wm_poi_id=-42&tag_spu_ids=%FF',
                'keys': ['poi_id_str', 'wm_poi_id', 'tag_spu_ids'],
                'route_slot': 2, 'expires_at': self.now[0] + 60}
            self.assertTrue(self.window.authorize_category_request(2, ref))
            self.window.request_leases[ref]['body'] = body + b'&tag_spu_ids=%FF'
            with patch('collection_adapter.p29_batch_parameter.unquote_to_bytes',
                       side_effect=AssertionError('parameter must stay unread')):
                result = inspect_current_batch_parameter(self.window, 2, ref, {})
            self.assertEqual(result['status'], 'SCOPE_UNAVAILABLE')

    def test_render_rejection_explains_current_id_relations_without_relaxing_scope(self):
        self.pair()
        inspector = self.window.render_inspector
        for selector, numeric, expected in (
                ('public_synthetic_42', '-99', (False, False, True)),
                ('synthetic_request_selector', '-42', (True, True, False)),
                ('synthetic_other', '-42', (False, True, False)),
                ('synthetic_request_selector', '-99', (True, False, False))):
            ref = 'request:' + uuid4().hex
            self.window.request_leases[ref] = {
                'body': ('poi_id_str=' + selector + '&wm_poi_id=' + numeric).encode(),
                'keys': ['poi_id_str', 'wm_poi_id'], 'route_slot': 2,
                'expires_at': self.now[0] + 60}
            with patch('collection_adapter.p29_category_render.analyze_public_body') as analyze:
                self.assertFalse(self.window.authorize_category_request(2, ref))
                self.window._consume(2, b'must not decode', source_request_ref=ref)
            analyze.assert_not_called()
            check = inspector.diagnostic()['last_scope_check']
            self.assertEqual(check, dict(zip((
                'request_string_matches_context_selector',
                'request_numeric_matches_context_numeric',
                'request_string_matches_response_public_string'), expected)))
            self.validate(self.window.diagnostic(), 'p29-store-pages-diagnostic-v1.schema.json')
            from parser_candidate.p29_category_profile import CategoryCandidateError
            forged = copy.deepcopy(self.window.diagnostic())
            forged['category_render']['last_scope_check']['identifier'] = 'PRIVATE_VALUE'
            with self.assertRaises(CategoryCandidateError):
                self.validate(forged, 'p29-store-pages-diagnostic-v1.schema.json')
        self.window.close('P26_CANCELLED')
        self.assertEqual(inspector.diagnostic()['last_scope_check'], check)
        self.assertIsNone(inspector.target)
        self.assertNotIn('synthetic_', json.dumps(inspector.diagnostic()))

    def test_missing_request_clears_previous_scope_check(self):
        self.pair()
        inspector = self.window.render_inspector
        ref = 'request:' + uuid4().hex
        self.window.request_leases[ref] = {
            'body': b'poi_id_str=synthetic_other&wm_poi_id=-42',
            'keys': ['poi_id_str', 'wm_poi_id'], 'route_slot': 2,
            'expires_at': self.now[0] + 60}
        self.assertFalse(self.window.authorize_category_request(2, ref))
        self.assertIsNotNone(inspector.diagnostic()['last_scope_check'])
        self.assertFalse(self.window.authorize_category_request(2, 'request:' + uuid4().hex))
        self.assertIsNone(inspector.diagnostic()['last_scope_check'])

    def test_public_string_requires_current_context_and_unexpired_own_request(self):
        def lease():
            ref = 'request:' + uuid4().hex
            self.window.request_leases[ref] = {
                'body': b'poi_id_str=public_synthetic_42&wm_poi_id=-42',
                'keys': ['poi_id_str', 'wm_poi_id'], 'route_slot': 2,
                'expires_at': self.now[0] + 60}
            return ref
        with patch('collection_adapter.p29_category_render.analyze_public_body') as analyze:
            ref = lease()
            self.assertFalse(self.window.authorize_category_request(2, ref))
            self.window._consume(2, b'must not decode', source_request_ref=ref)
        analyze.assert_not_called()
        self.pair()
        expired = lease(); self.now[0] += 61
        with patch('collection_adapter.p29_category_render.analyze_public_body') as analyze:
            self.assertFalse(self.window.authorize_category_request(2, expired))
            self.window._consume(2, b'must not decode', source_request_ref=expired)
        analyze.assert_not_called()
        pending = lease()
        self.window.close('P26_CANCELLED')
        self.assertIsNone(self.window.render_inspector.target)
        self.assertFalse(self.window.request_leases)
        self.assertFalse(self.window.authorize_category_request(2, pending))
        self.assertFalse(list(self.root.glob('category_render_*')))

    def test_forged_numeric_proof_or_value_field_cannot_enter_collection(self):
        from collection_core.p29 import P29Error,render_collection
        self.pair()
        for field,value in (('food_wm_poi_id_matches_numeric_id',False),
                            ('poi_id_str_equal_between_requests',False),
                            ('same_observation_gap_valid',False),
                            ('string_id_role','ALIAS_CONFIRMED'),('identifier','PRIVATE_VALUE')):
            forged = copy.deepcopy(self.window.snapshots)
            forged[0]['source_association'][field] = value
            with self.assertRaises(P29Error): render_collection(forged)

    def test_existing_output_budget_and_private_form_opacity_remain(self):
        from urllib.parse import unquote_to_bytes
        def guarded(value):
            self.assertNotIn(b'PRIVATE_FORM_VALUE',value)
            return unquote_to_bytes(value)
        food, product = bodies()
        with patch('collection_adapter.p26_result_mapping.unquote_to_bytes', side_effect=guarded):
            self.response(0,food,prefix=b'Cookie=%FF_PRIVATE_FORM_VALUE&')
            self.response(1,product,prefix=b'Cookie=%FF_PRIVATE_FORM_VALUE&')
        self.assertEqual(len(self.window.snapshots),1)
        self.assertNotIn('PRIVATE_FORM_VALUE',json.dumps(self.exported()))
        self.window.close('P26_CANCELLED')
        with tempfile.TemporaryDirectory() as temp:
            self.root=Path(temp).resolve();self.root.chmod(0o700)
            self.window=self.make_window()
            with patch('collection_adapter.p29_store_pages.MAX_COLLECTION_BYTES',100): self.pair()
            self.assertEqual(self.window.code,'P26_TOTAL_SIZE_LIMIT')
            self.assertFalse(list(self.root.iterdir()))
            self.assertFalse(self.window.request_leases or self.window._bodies)


if __name__ == '__main__':
    unittest.main()
