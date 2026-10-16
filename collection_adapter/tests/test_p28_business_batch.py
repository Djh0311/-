import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from collection_adapter.p26_identification import IdentificationError, key_only_layout
from collection_adapter.p26_public_projection import FOOD_ROUTE, PRODUCT_ROUTE, PUBLIC_PATHS
from collection_adapter.p28_business_batch import P28BusinessBatchWindow, analyze_public_body


def bodies():
    food = {'code': 0, 'data': {'poi_info': {'id': -42, 'poi_id_str': 'public_synthetic_42',
                'name': 'Synthetic batch shop'}, 'notice': 'Synthetic public notice',
                'user_info': {'name': 'PRIVATE_VALUE'}}}
    product = {'code': 0, 'data': {'food_spu_tags': [{'tag': 'category_a', 'name': 'Synthetic category',
        'current_page': 0, 'has_next_page': False, 'dynamic_spus': [{'id': 101,
        'name': 'Synthetic item', 'unit': 'Synthetic unit', 'min_price': 1.2,
        'skus': [{'id': 201, 'spec': 'Synthetic A', 'spec_desc': '', 'price': 1.2, 'origin_price': 2.0},
                 {'id': 202, 'spec': 'Synthetic B', 'spec_desc': '', 'price': 2.3, 'origin_price': 3.0}],
        'render_info': {'price_info': {'min_price': 1.2}}, 'new_public_flag': True}]}]}}
    return food, product


class BatchAnalysisTests(unittest.TestCase):
    def test_complete_arrays_and_new_fields_preserve_coordinates(self):
        _, product = bodies()
        result = analyze_public_body(json.dumps(product).encode())
        skus = [v for v in result['public_values'] if v['path'].endswith('.skus[].price')]
        self.assertEqual([v['value'] for v in skus], [1.2, 2.3])
        self.assertEqual(skus[1]['coordinates'][-2:], [1, 'price'])
        self.assertTrue(any(v['path'].endswith('.new_public_flag') for v in result['public_values']))
        self.assertEqual(result['field_meanings'], 'DEVELOPER_REVIEW_REQUIRED')

    def test_private_branches_are_never_decoded_and_urls_are_not_exported(self):
        food, _ = bodies()
        food['data']['image_url'] = 'https://synthetic.invalid/public-image'
        loader = json.loads
        def guarded(value, *args, **kwargs):
            if value == b'"PRIVATE_VALUE"':
                self.fail('private scalar decoded')
            return loader(value, *args, **kwargs)
        with patch('collection_adapter.p26_identification.json.loads', side_effect=guarded):
            result = analyze_public_body(json.dumps(food).encode())
        self.assertNotIn('PRIVATE_VALUE', json.dumps(result))
        self.assertTrue(result['restricted_fields'])
        self.assertEqual(result['unavailable_fields'][0]['reason'], 'URL_VALUE')

    def test_default_path_budget_is_unchanged_and_batch_budget_is_finite(self):
        payload = json.dumps({'data': {f'field_{i}': i for i in range(129)}}).encode()
        selected = frozenset(f'$.data.field_{i}' for i in range(129))
        with self.assertRaises(IdentificationError):
            key_only_layout(payload, public_paths=selected)
        self.assertEqual(len(analyze_public_body(payload)['public_values']), 129)
        oversized = json.dumps({'data': {f'field_{i}': i for i in range(1025)}}).encode()
        with self.assertRaises(IdentificationError):
            analyze_public_body(oversized)


class BatchWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve(); self.root.chmod(0o700)
        self.now = [100.0]
        self.window = P28BusinessBatchWindow('Synthetic batch shop', self.root,
            'authorization:synthetic_batch', clock=lambda: self.now[0], duration_seconds=None)
        self.window.routes = [('POST', 'wx.waimai.meituan.com', r) for r in (FOOD_ROUTE, PRODUCT_ROUTE)]
        self.window.route_origins = {0: 'wx.waimai.meituan.com', 1: 'wx.waimai.meituan.com'}
        self.window.key_layout_only = self.window.sensitive_key_layout_authorized = True
        self.window.public_projection_enabled = True
        self.window.public_projection_paths = dict(PUBLIC_PATHS)
        self.window.start_once()

    def tearDown(self):
        self.temp.cleanup()

    def response(self, slot, payload, *, wrong_request=False):
        ref = 'request:' + ('a' if slot == 0 else 'b') * 32
        form = b'poi_id_str=public_synthetic_42&wm_poi_id=-42'
        if wrong_request: form = b'poi_id_str=other_synthetic&wm_poi_id=-42'
        self.window.request_leases[ref] = {'body': form, 'keys': ['poi_id_str', 'wm_poi_id'],
            'route_slot': slot, 'expires_at': self.now[0] + 60}
        self.window._consume(slot, json.dumps(payload).encode(), source_request_ref=ref)

    def test_fresh_full_pair_publishes_sku_files_and_public_inventory_then_cleans(self):
        food, product = bodies(); self.response(0, food); self.response(1, product)
        self.assertEqual(self.window.code, 'P26_RESULT_PUBLISHED')
        self.assertFalse(self.window._bodies or self.window.request_leases)
        output = json.loads((self.root/'first_result'/'records.json').read_text())
        self.assertEqual(output['sku_count'], 2)
        scalar = json.loads((self.root/'public-business-fields.json').read_text())
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
        schema_root = Path(__file__).resolve().parents[2]/'contracts'/'schemas'
        schema = json.loads((schema_root/'p28-public-business-batch-v1.schema.json').read_text())
        registry = Registry()
        for path in schema_root.glob('*.schema.json'):
            registry = registry.with_resource(path.name, Resource.from_contents(json.loads(path.read_text())))
        Draft202012Validator(schema, registry=registry, format_checker=FormatChecker()).validate(scalar)
        diagnostic_schema = json.loads((schema_root/'p26-result-diagnostic-v1.schema.json').read_text())
        host_receipt = json.loads(json.dumps({**self.window.diagnostic(), 'p28_batch_receipt': self.window.batch_receipt}))
        validator = Draft202012Validator(diagnostic_schema, registry=registry, format_checker=FormatChecker())
        self.assertEqual([(list(e.path), e.validator) for e in validator.iter_errors(host_receipt)], [])
        host_receipt['p28_batch_receipt']['unexpected'] = 'synthetic'
        self.assertFalse(validator.is_valid(host_receipt))
        self.assertNotIn('PRIVATE_VALUE', json.dumps(scalar))
        self.assertTrue(scalar['source_association']['store_name_match'])
        self.assertEqual(self.window.diagnostic()['published_records'], 2)
        self.assertEqual(self.window.diagnostic()['qualified_business_events'], 2)
        self.assertEqual(self.window.diagnostic()['execution_latch'], 'CLOSED')

    def test_wrong_form_never_exports_unknown_values(self):
        food, product = bodies(); self.response(0, food); self.response(1, product, wrong_request=True)
        self.assertEqual(self.window.code, 'P26_RESULT_SOURCE_ASSOCIATION_INVALID')
        self.assertEqual(self.window.diagnostic()['qualified_business_events'], 0)
        self.assertFalse((self.root/'public-business-fields.json').exists())
        self.assertFalse(self.window._bodies)
        check = self.window.diagnostic()['association_check']
        self.assertTrue(check['store_name_match'])
        self.assertFalse(check['product_poi_id_str_matches_public_string_id'])
        self.assertFalse(check['poi_id_str_equal_between_requests'])
        self.assertFalse(self.window.request_leases or self.window.projected_observations)

    def test_failed_code_condition_survives_cleanup_without_response_values(self):
        from jsonschema import Draft202012Validator
        food, product = bodies(); product['code'] = 7
        with patch('collection_adapter.p28_business_batch.analyze_public_body') as analyze:
            self.response(0, food); self.response(1, product)
        analyze.assert_not_called()
        diagnostic = self.window.diagnostic()
        check = diagnostic['association_check']
        self.assertTrue(check['food_success_code'])
        self.assertFalse(check['product_success_code'])
        self.assertTrue(check['store_name_match'])
        self.assertTrue(check['product_wm_poi_id_matches_numeric_id'])
        self.assertEqual(diagnostic['result_attempts'], 1)
        self.assertEqual(diagnostic['execution_latch'], 'CLOSED')
        self.assertFalse(self.window._bodies or self.window.request_leases)
        self.assertFalse(list(self.root.iterdir()))
        encoded = json.dumps(diagnostic)
        for value in ('Synthetic batch shop', 'public_synthetic_42', 'PRIVATE_VALUE'):
            self.assertNotIn(value, encoded)
        schemas = Path(__file__).resolve().parents[2]/'contracts'/'schemas'
        schema = json.loads((schemas/'p26-result-diagnostic-v1.schema.json').read_text())
        validator = Draft202012Validator(schema)
        validator.validate(diagnostic)
        check['unexpected_value'] = 'synthetic'
        self.assertFalse(validator.is_valid(diagnostic))

    def test_other_store_is_rejected_before_full_public_analysis(self):
        food, product = bodies()
        food['data']['poi_info']['name'] = 'Other synthetic shop'
        with patch('collection_adapter.p28_business_batch.analyze_public_body') as analyze:
            self.response(0, food); self.response(1, product)
        analyze.assert_not_called()
        self.assertEqual(self.window.code, 'P26_RESULT_SOURCE_ASSOCIATION_INVALID')
        self.assertFalse((self.root/'public-business-fields.json').exists())
        self.assertFalse(self.window._bodies or self.window.request_leases)
        self.assertFalse(self.window.diagnostic()['association_check']['store_name_match'])

    def test_prepared_does_not_consume_input_or_attempts(self):
        window = P28BusinessBatchWindow('Synthetic batch shop', self.root,
            'authorization:synthetic_prepared', clock=lambda: self.now[0], duration_seconds=None)
        window._consume(0, b'not JSON and must remain unread')
        self.assertEqual(window.attempts, 0)
        self.assertEqual(window.raw_callbacks, 0)
        self.assertEqual(window.state, 'PREPARED')
        self.assertFalse(window._bodies or window.projected_observations)
        self.assertEqual(window.diagnostic()['execution_latch'], 'CLOSED')
        self.assertIsNone(window.diagnostic()['association_check'])

    def test_host_counts_batch_as_result_and_matches_latches_without_double_count(self):
        from collection_adapter.p26_identification_host import _update_state
        from jsonschema import Draft202012Validator, FormatChecker
        schema_root = Path(__file__).resolve().parents[2]/'contracts'/'schemas'
        schema = json.loads((schema_root/'p26-result-diagnostic-v1.schema.json').read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        baseline = {'identification_attempts': 3, 'result_attempts': 5}
        _update_state(self.root, baseline, self.window)
        active = json.loads((self.root/'transport-state.json').read_text())
        self.assertEqual(active['execution_latch'], self.window.diagnostic()['execution_latch'])
        self.assertEqual((active['identification_attempts'], active['result_attempts']), (3, 6))
        validator.validate(self.window.diagnostic())
        self.window.close('P26_CANCELLED')
        _update_state(self.root, baseline, self.window)
        closed = json.loads((self.root/'transport-state.json').read_text())
        self.assertEqual((closed['identification_attempts'], closed['result_attempts']), (3, 6))
        self.assertEqual(closed['execution_latch'], 'CLOSED')
        self.assertEqual(self.window.diagnostic()['result_attempts'], 1)
        validator.validate(self.window.diagnostic())

    def test_expired_raw_pair_is_not_combined_or_persisted(self):
        food, product = bodies(); self.response(0, food); self.now[0] += 11
        self.response(1, product)
        self.assertEqual(set(self.window._bodies), {PRODUCT_ROUTE})
        self.assertFalse((self.root/'first_result').exists())
        self.window.close('P26_CANCELLED')
        self.assertFalse(self.window._bodies)

    def test_partial_core_record_does_not_publish_complete_result(self):
        food, product = bodies(); del product['data']['food_spu_tags'][0]['dynamic_spus'][0]['min_price']
        self.response(0, food); self.response(1, product)
        self.assertEqual(self.window.code, 'P26_RESULT_PARSE_FAILED')
        self.assertEqual(self.window.diagnostic()['qualified_business_events'], 2)
        self.assertEqual(self.window.diagnostic()['parsed_records'], 0)
        self.assertEqual(self.window.diagnostic()['published_records'], 0)
        self.assertFalse((self.root/'first_result').exists())
        self.assertFalse(self.window._bodies)

    def test_observed_business_hosts_publish_the_same_public_pair(self):
        self.window.routes = [
            ('POST', 'hcapi-wx.waimai.meituan.com', FOOD_ROUTE),
            ('POST', 'apimobile.meituan.com', PRODUCT_ROUTE)]
        self.window.route_origins = {0: 'hcapi-wx.waimai.meituan.com', 1: 'apimobile.meituan.com'}
        food, product = bodies(); self.response(0, food); self.response(1, product)
        self.assertEqual(self.window.code, 'P26_RESULT_PUBLISHED')
        self.assertTrue((self.root/'public-business-fields.json').exists())

    def test_image_host_is_not_parsed_on_the_same_path(self):
        self.window.routes[0] = ('POST', 'img.meituan.net', FOOD_ROUTE)
        self.window.route_origins[0] = 'img.meituan.net'
        food, _ = bodies(); self.response(0, food)
        self.assertEqual(self.window._bodies, {})
        self.assertNotEqual(self.window.code, 'P26_RESULT_PUBLISHED')
        self.assertFalse((self.root/'public-business-fields.json').exists())

    def test_wrong_method_stops_without_scalar_export(self):
        food, _ = bodies()
        self.window.routes[0] = ('GET', 'wx.waimai.meituan.com', FOOD_ROUTE)
        self.response(0, food)
        self.assertEqual(self.window.code, 'P26_RESULT_EVENT_SET_INVALID')
        self.assertFalse((self.root/'public-business-fields.json').exists())


if __name__ == '__main__':
    unittest.main()
