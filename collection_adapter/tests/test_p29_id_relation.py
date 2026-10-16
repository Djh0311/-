import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote, unquote_to_bytes
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker

from collection_adapter.p26_public_projection import FOOD_ROUTE, PRODUCT_ROUTE, PUBLIC_PATHS
from collection_adapter.p29_id_relation import inspect_current_id_relation
from collection_adapter.p29_store_pages import P29StorePagesWindow
from collection_adapter.tests.test_p28_business_batch import bodies


class RoutingIdRelationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.root.chmod(0o700)
        self.now = [100.0]
        self.window = self.make_window()
        schemas = Path(__file__).resolve().parents[2]/'contracts'/'schemas'
        self.validator = Draft202012Validator(json.loads(
            (schemas/'p29-routing-id-relation-v1.schema.json').read_text()),
            format_checker=FormatChecker())

    def make_window(self, *, start=True):
        w = P29StorePagesWindow('Synthetic batch shop', self.root,
            'authorization:synthetic_id_relation', clock=lambda: self.now[0], duration_seconds=None)
        w.routes = [('POST', 'wx.waimai.meituan.com', r) for r in (FOOD_ROUTE, PRODUCT_ROUTE)]
        w.route_origins = {0: 'wx.waimai.meituan.com', 1: 'wx.waimai.meituan.com'}
        w.selected_routes = {0, 1}
        w.key_layout_only = w.sensitive_key_layout_authorized = w.public_projection_enabled = True
        w.public_projection_paths = dict(PUBLIC_PATHS)
        if start: w.start_once()
        return w

    def response(self, slot, body, request_id, *, numeric='-42', prefix=b''):
        ref = 'request:' + uuid4().hex
        form = prefix + ('wm_poi_id=' + numeric + '&poi_id_str=' + quote(request_id, safe='')).encode()
        self.window.request_leases[ref] = {'body': form, 'keys': ['wm_poi_id', 'poi_id_str'],
            'route_slot': slot, 'expires_at': self.now[0] + 60}
        collector = self.window.begin_response(slot, 'identity', source_request_ref=ref)
        self.assertIsNotNone(collector)
        collector.feed(json.dumps(body).encode()); collector.feed(b'')

    def mismatch(self, request_id='synthetic_other_public', *, prefix=b''):
        food, product = bodies()
        self.response(0, food, request_id, prefix=prefix)
        self.response(1, product, request_id, prefix=prefix)

    def probe(self):
        paths = list(self.root.glob('routing_id_relation_*.json'))
        self.assertEqual(len(paths), 1)
        self.assertEqual(stat.S_IMODE(paths[0].stat().st_mode), 0o600)
        doc = json.loads(paths[0].read_text()); self.validator.validate(doc)
        return doc

    def assert_closed_without_result(self):
        diagnostic = self.window.diagnostic()
        self.assertEqual(diagnostic['code'], 'P26_RESULT_SOURCE_ASSOCIATION_INVALID')
        self.assertEqual((diagnostic['qualified_business_events'], diagnostic['published_records']), (0, 0))
        self.assertEqual((diagnostic['live_capture_latch'], diagnostic['execution_latch']), ('CLOSED', 'CLOSED'))
        self.assertEqual(diagnostic['result_attempts'], 1)
        self.assertFalse(self.window._bodies or self.window.request_leases or self.window.projected_observations)
        self.assertFalse(list(self.root.glob('observation_*')))

    def test_different_strings_record_metadata_and_keep_qualification_failed(self):
        self.mismatch(); doc = self.probe(); self.assert_closed_without_result()
        self.assertFalse(doc['request_equals_response'])
        self.assertFalse(doc['one_more_request_url_decode_equals_response'])
        self.assertFalse(doc['one_response_url_decode_equals_request'])
        self.assertFalse(doc['nfkc_space_free_strings_equal'])
        self.assertFalse(doc['mapping_rule_qualified'])
        self.assertEqual(doc['field_role_relation'], 'UNCONFIRMED')
        encoded = json.dumps(doc)
        for value in ('public_synthetic_42', 'synthetic_other_public', 'Synthetic batch shop', 'PRIVATE_VALUE'):
            self.assertNotIn(value, encoded)
        doc['identifier'] = 'synthetic'
        self.assertFalse(self.validator.is_valid(doc))

    def test_extra_url_encoding_is_observed_without_applying_a_mapping_rule(self):
        self.mismatch('%70ublic_synthetic_42')
        doc = self.probe(); self.assert_closed_without_result()
        self.assertTrue(doc['request_contains_url_escape'])
        self.assertTrue(doc['one_more_request_url_decode_equals_response'])
        self.assertFalse(doc['request_equals_response'])
        self.assertFalse(doc['mapping_rule_qualified'])
        self.assertFalse(self.window.association_check['food_poi_id_str_matches_public_string_id'])

    def test_scope_failures_never_read_more_request_values_or_write_probe(self):
        for cause in ('name', 'numeric_id', 'different_request_ids', 'success_code'):
            with self.subTest(cause=cause):
                self.window = self.make_window()
                food, product = bodies()
                if cause == 'name': food['data']['poi_info']['name'] = 'Other synthetic shop'
                if cause == 'success_code': product['code'] = 9
                numeric = '-99' if cause == 'numeric_id' else '-42'
                other = 'synthetic_another_public' if cause == 'different_request_ids' else 'synthetic_other_public'
                with patch('collection_adapter.p29_id_relation.current_routing_id') as read:
                    self.response(0, food, 'synthetic_other_public', numeric=numeric)
                    self.response(1, product, other, numeric=numeric)
                read.assert_not_called()
                self.assert_closed_without_result()
                self.assertFalse(list(self.root.iterdir()))

    def test_private_form_value_remains_encoded_and_absent_from_probe(self):
        def guarded(value):
            if b'PRIVATE_FORM_VALUE' in value:
                self.fail('private form value decoded')
            return unquote_to_bytes(value)
        with patch('collection_adapter.p26_result_mapping.unquote_to_bytes', side_effect=guarded):
            self.mismatch(prefix=b'Cookie=%FF_PRIVATE_FORM_VALUE&')
        self.assertNotIn('PRIVATE_FORM_VALUE', json.dumps(self.probe()))
        self.assert_closed_without_result()

    def test_invalid_url_utf8_is_null_metadata_and_keeps_original_stop_code(self):
        self.mismatch('%FF')
        doc = self.probe(); self.assert_closed_without_result()
        self.assertTrue(doc['request_contains_url_escape'])
        self.assertIsNone(doc['one_more_request_url_decode_equals_response'])

    def test_probe_obeys_existing_output_budget_and_cleanup(self):
        with patch('collection_adapter.p29_store_pages.MAX_COLLECTION_BYTES', 100):
            self.mismatch()
        self.assertEqual(self.window.code, 'P26_TOTAL_SIZE_LIMIT')
        self.assertFalse(list(self.root.iterdir()))
        self.assertFalse(self.window._bodies or self.window.request_leases)
        self.assertEqual(self.window.diagnostic()['result_attempts'], 1)

    def test_prepared_and_successful_paths_do_not_create_mismatch_probe(self):
        prepared = self.make_window(start=False)
        with patch('collection_adapter.p29_id_relation.current_routing_id') as read:
            self.assertIsNone(inspect_current_id_relation(prepared, {}))
        read.assert_not_called()
        self.assertEqual(prepared.attempts, 0)
        food, product = bodies()
        self.response(0, food, 'public_synthetic_42'); self.response(1, product, 'public_synthetic_42')
        self.assertEqual(len(self.window.snapshots), 1)
        self.assertFalse(list(self.root.glob('routing_id_relation_*.json')))
