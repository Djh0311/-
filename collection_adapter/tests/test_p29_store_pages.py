import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from collection_adapter.p26_public_projection import FOOD_ROUTE, PRODUCT_ROUTE, PUBLIC_PATHS
from collection_adapter.p29_store_pages import P29StorePagesWindow
from collection_adapter.tests.test_p28_business_batch import bodies
from collection_core.result_publisher import ResultPublishError


class StorePagesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.root.chmod(0o700)
        self.now = [100.0]
        self.window = self.make_window(); self.window.start_once()

    def make_window(self):
        w = P29StorePagesWindow('Synthetic batch shop', self.root, 'authorization:synthetic_p29',
            clock=lambda: self.now[0], duration_seconds=None)
        w.routes = [('POST', 'wx.waimai.meituan.com', r) for r in (FOOD_ROUTE, PRODUCT_ROUTE)]
        w.route_origins = {0: 'wx.waimai.meituan.com', 1: 'wx.waimai.meituan.com'}
        w.selected_routes = {0, 1}
        w.key_layout_only = w.sensitive_key_layout_authorized = w.public_projection_enabled = True
        w.public_projection_paths = dict(PUBLIC_PATHS)
        return w

    def response(self, slot, body, *, wrong=False):
        ref = 'request:' + uuid4().hex
        self.window.request_leases[ref] = {'body': b'poi_id_str=public_synthetic_42&wm_poi_id=-42'
            if not wrong else b'poi_id_str=other_synthetic&wm_poi_id=-42',
            'keys': ['poi_id_str', 'wm_poi_id'], 'route_slot': slot, 'expires_at': self.now[0]+60}
        collector = self.window.begin_response(slot, 'identity', source_request_ref=ref)
        self.assertIsNotNone(collector)
        collector.feed(json.dumps(body).encode()); collector.feed(b'')

    def pair(self, food=None, product=None):
        default_food, default_product = bodies()
        self.response(0, food if food is not None else default_food)
        self.response(1, product if product is not None else default_product)

    def collection(self):
        return self.root/self.window.collection_receipt['result_summary']['result_name']

    def test_prepare_is_zero_attempt_and_consumes_nothing(self):
        w = self.make_window(); w._consume(0, b'must not be decoded')
        self.assertEqual((w.attempts, w.raw_callbacks, w.state), (0, 0, 'PREPARED'))
        self.assertFalse(list(self.root.iterdir()))
        w.close('P26_CANCELLED')
        self.assertIsNone(w.collection_receipt)

    def test_repeated_pairs_continue_then_close_with_complete_consistent_collection(self):
        self.pair()
        self.assertEqual((self.window.state, len(self.window.snapshots)), ('ACTIVE', 1))
        self.assertFalse(self.window._bodies or self.window.request_leases or self.window.projected_observations)
        self.pair(); self.window.close('P26_CANCELLED')
        p = self.collection(); view = json.loads((p/'records.json').read_text())
        self.assertEqual((view['observation_count'], view['record_count'], view['input_record_count']), (2, 2, 4))
        self.assertEqual(list(csv.DictReader(io.StringIO((p/'records.csv').read_text()))), view['records'])
        self.assertEqual(json.loads((p/'manifest.json').read_text())['record_count'], 2)
        d = self.window.diagnostic()
        self.assertEqual((d['raw_callbacks'], d['qualified_business_events'], d['parsed_records'], d['published_records']), (4, 4, 4, 2))
        self.assertEqual((d['result_attempts'], d['live_capture_latch'], d['execution_latch']), (1, 'CLOSED', 'CLOSED'))
        self.assertEqual(len(list(self.root.glob('observation_*-public-fields.json'))), 2)

    def test_missing_fresh_merchant_never_reuses_previous_pair(self):
        self.pair(); _, product = bodies(); self.response(1, product)
        self.assertEqual(self.window.diagnostic()['pending_pair'], 'FRESH_MERCHANT_PENDING')
        self.assertEqual(len(self.window.snapshots), 1)
        self.now[0] += 11; self.window.diagnostic()
        self.assertFalse(self.window._bodies)
        self.window.close('P26_CANCELLED')
        self.assertEqual(json.loads((self.collection()/'manifest.json').read_text())['observation_count'], 1)

    def test_reused_request_reference_stops_before_decoding_body(self):
        self.pair(); ref = next(iter(self.window._consumed_requests))
        with patch('collection_adapter.p28_business_batch.analyze_public_body') as analyze:
            self.window._consume(0, b'must remain unread', source_request_ref=ref)
        analyze.assert_not_called()
        self.assertEqual(self.window.code, 'P26_RESULT_EVENT_SET_INVALID')
        self.assertEqual(len(self.window.snapshots), 1)

    def test_empty_page_is_coverage_only_and_does_not_claim_termination(self):
        self.pair(); _, empty = bodies()
        empty['data']['food_spu_tags'][0].update(dynamic_spus=[], fold_spu_ids=[909], product_count=0)
        self.pair(product=empty)
        self.assertEqual((self.window.state, len(self.window.snapshots), self.window.empty_count), ('ACTIVE', 1, 1))
        metadata = json.loads(next(self.root.glob('empty_observation_*.json')).read_text())
        self.assertFalse(metadata['empty_page_is_termination'])
        self.assertEqual(metadata['business_record_count'], 0)
        self.window.close('P26_CANCELLED')
        self.assertEqual(self.window.collection_receipt['empty_observations'], 1)
        self.assertEqual(self.window.diagnostic()['qualified_business_events'], 4)

    def test_only_empty_observations_never_publish_a_business_result(self):
        _, empty = bodies(); empty['data']['food_spu_tags'][0]['dynamic_spus'] = []
        self.pair(product=empty); self.window.close('P26_CANCELLED')
        self.assertEqual(self.window.empty_count, 1)
        self.assertIsNone(self.window.collection_receipt)
        self.assertFalse(list(self.root.glob('collection_*')))
        self.assertEqual(self.window.diagnostic()['published_records'], 0)

    def test_other_store_and_wrong_form_never_export_public_batches(self):
        for wrong in (True, False):
            with self.subTest(wrong_form=wrong):
                self.window = self.make_window(); self.window.start_once()
                food, product = bodies()
                if not wrong: food['data']['poi_info']['name'] = 'Other synthetic'
                self.response(0, food); self.response(1, product, wrong=wrong)
                self.assertEqual(self.window.code, 'P26_RESULT_SOURCE_ASSOCIATION_INVALID')
                self.assertFalse(self.window._bodies or self.window.request_leases)
                self.assertFalse(list(self.root.iterdir()))

    def test_latest_failed_association_keeps_prior_result_and_value_free_check(self):
        from jsonschema import Draft202012Validator
        self.pair()
        original = next(self.root.glob('observation_*-public-fields.json')).read_bytes()
        food, product = bodies()
        self.response(0, food); self.response(1, product, wrong=True)
        diagnostic = self.window.diagnostic()
        self.assertEqual(diagnostic['code'], 'P26_RESULT_SOURCE_ASSOCIATION_INVALID')
        self.assertFalse(diagnostic['association_check']['product_poi_id_str_matches_public_string_id'])
        self.assertTrue(diagnostic['association_check']['store_name_match'])
        self.assertEqual((diagnostic['complete_observations'], diagnostic['qualified_business_events']), (1, 2))
        self.assertEqual((diagnostic['result_attempts'], diagnostic['live_capture_latch'],
                          diagnostic['execution_latch']), (1, 'CLOSED', 'CLOSED'))
        self.assertFalse(self.window._bodies or self.window.request_leases or self.window.projected_observations)
        self.assertEqual(next(self.root.glob('observation_*-public-fields.json')).read_bytes(), original)
        self.assertEqual(json.loads((self.collection()/'records.json').read_text())['record_count'], 2)
        for value in ('Synthetic batch shop', 'public_synthetic_42', 'other_synthetic', 'PRIVATE_VALUE'):
            self.assertNotIn(value, json.dumps(diagnostic))
        schema_path = Path(__file__).resolve().parents[2]/'contracts/schemas/p29-store-pages-diagnostic-v1.schema.json'
        Draft202012Validator(json.loads(schema_path.read_text())).validate(diagnostic)

    def test_unprojectable_identity_never_reuses_previous_successful_check(self):
        self.pair()
        self.assertTrue(self.window.diagnostic()['association_check']['store_name_match'])
        food, product = bodies()
        food['data']['poi_info']['name'] = 'https://synthetic.invalid/blocked-identity'
        self.pair(food=food, product=product)
        diagnostic = self.window.diagnostic()
        self.assertEqual(diagnostic['code'], 'P26_RESULT_MAPPING_INVALID')
        self.assertIsNone(diagnostic['association_check'])
        self.assertEqual((diagnostic['complete_observations'], diagnostic['qualified_business_events']), (1, 2))
        self.assertFalse(self.window._bodies or self.window.request_leases)
        self.assertEqual(json.loads((self.collection()/'records.json').read_text())['record_count'], 2)
        self.assertNotIn('blocked-identity', json.dumps(diagnostic))

    def test_partial_core_cannot_borrow_fields_and_keeps_previous_completed_result(self):
        self.pair(); _, product = bodies()
        del product['data']['food_spu_tags'][0]['dynamic_spus'][0]['min_price']
        self.pair(product=product)
        self.assertEqual(self.window.code, 'P26_RESULT_PARSE_FAILED')
        d = self.window.diagnostic()
        self.assertEqual((d['qualified_business_events'], d['parsed_records'], d['published_records']), (4, 2, 2))
        self.assertEqual(len(self.window.snapshots), 1)
        self.assertEqual(json.loads((self.collection()/'manifest.json').read_text())['record_count'], 2)

    def test_budget_stops_and_retains_previous_complete_observation(self):
        self.pair(); original = next(self.root.glob('observation_*-public-fields.json')).read_bytes()
        with patch('collection_adapter.p29_store_pages.MAX_OBSERVATIONS', 1): self.pair()
        self.assertEqual(self.window.code, 'P26_TOTAL_SIZE_LIMIT')
        self.assertEqual(len(self.window.snapshots), 1)
        self.assertEqual(next(self.root.glob('observation_*-public-fields.json')).read_bytes(), original)
        self.assertIsNotNone(self.window.collection_receipt)

    def test_cumulative_response_bytes_do_not_reset_after_each_pair(self):
        self.pair(); before = self.window.decoded_bytes
        self.pair(); self.assertGreater(self.window.decoded_bytes, before)
        self.window.close('P26_CANCELLED')

    def test_aggregate_publish_failure_preserves_individual_files(self):
        self.pair(); name = self.window.last_result_name
        before = {p.name: p.read_bytes() for p in (self.root/name).iterdir()}
        with patch('collection_adapter.p29_store_pages.publish_result_set',
                   side_effect=ResultPublishError('RESULT_PUBLISH_FAILED')):
            self.window.close('P26_CANCELLED')
        self.assertEqual(self.window.code, 'P26_RESULT_PUBLISH_FAILED')
        self.assertIsNone(self.window.collection_receipt)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root/name).iterdir()})
        self.assertFalse(self.window._bodies or self.window.request_leases or self.window.collectors)

    def test_timeout_closes_and_keeps_already_published_observation(self):
        self.window = self.make_window()
        self.window.duration_seconds = 5
        self.window.start_once()
        self.pair(); self.now[0] += 6
        d = self.window.diagnostic()
        self.assertEqual((d['code'], d['state'], d['execution_latch']), ('P26_WINDOW_TIMEOUT', 'CLOSED', 'CLOSED'))
        self.assertIsNotNone(self.window.collection_receipt)

    def test_closed_diagnostic_and_empty_observation_schemas(self):
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
        schemas = Path(__file__).parents[2]/'contracts'/'schemas'
        registry = Registry()
        for file in schemas.glob('*.schema.json'):
            registry = registry.with_resource(file.name, Resource.from_contents(json.loads(file.read_text())))
        validator = Draft202012Validator(json.loads((schemas/'p29-store-pages-diagnostic-v1.schema.json').read_text()),
                                        registry=registry, format_checker=FormatChecker())
        validator.validate(self.window.diagnostic())
        self.pair(); validator.validate(self.window.diagnostic())
        _, empty = bodies(); empty['data']['food_spu_tags'][0]['dynamic_spus'] = []
        self.pair(product=empty)
        value = json.loads(next(self.root.glob('empty_observation_*.json')).read_text())
        ev = Draft202012Validator(json.loads((schemas/'p29-empty-observation-v1.schema.json').read_text()),
                                 registry=registry, format_checker=FormatChecker())
        self.assertTrue(ev.is_valid(value)); self.assertFalse(ev.is_valid({**value, 'extra': 'synthetic'}))
        self.window.close('P26_CANCELLED')
        value = json.loads(json.dumps({**self.window.diagnostic(), 'p29_collection_receipt': self.window.collection_receipt}))
        self.assertEqual([(list(e.path), e.validator) for e in validator.iter_errors(value)], [])
        value['p29_collection_receipt']['unexpected'] = 'synthetic'
        self.assertFalse(validator.is_valid(value))


if __name__ == '__main__': unittest.main()
