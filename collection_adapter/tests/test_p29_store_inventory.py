import copy
import csv
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from collection_adapter.p26_public_projection import FOOD_ROUTE, PRODUCT_ROUTE, PUBLIC_PATHS
from collection_adapter.p29_store_pages import P29StorePagesWindow
from collection_adapter.p29_store_inventory import CSV_FIELDS, _validate, inventory_view, publish_store_inventory
from collection_adapter.tests.test_p28_business_batch import bodies
from collection_adapter.tests import test_p29_category_export as export_tests
from collection_adapter.tests.test_p29_category_review import synthetic_body
from collection_adapter.tests import test_p29_store_pages as store_tests
from collection_core.result_publisher import ResultPublishError, _manifest_from_views
from parser_candidate.p29_category_profile import CategoryCandidateError


class StoreInventoryTests(unittest.TestCase):
    write = export_tests.CategoryExportTests.write
    read = export_tests.CategoryExportTests.read

    def setUp(self):
        export_tests.CategoryExportTests.setUp(self)
        patched = patch('collection_adapter.p29_store_inventory._root', return_value=self.root)
        patched.start(); self.addCleanup(patched.stop)
        w = P29StorePagesWindow('Synthetic batch shop', self.root,
            'authorization:synthetic_inventory', clock=lambda: 100., duration_seconds=None)
        w.routes = [('POST', 'wx.waimai.meituan.com', r) for r in (FOOD_ROUTE, PRODUCT_ROUTE)]
        w.route_origins = {0: 'wx.waimai.meituan.com', 1: 'wx.waimai.meituan.com'}
        w.selected_routes = {0, 1}
        w.key_layout_only = w.sensitive_key_layout_authorized = w.public_projection_enabled = True
        w.public_projection_paths = dict(PUBLIC_PATHS)
        w.window_ref = self.window; w.start_once()
        food, product = bodies()
        product['data']['food_spu_tags'][0]['name'] = 'Synthetic offer category'
        product['data']['food_spu_tags'].append({'tag': 'synthetic_category',
            'name': 'Synthetic category 中文', 'dynamic_spus': [],
            'current_page': 0, 'has_next_page': False})
        holder = SimpleNamespace(window=w, now=[100.], assertIsNotNone=self.assertIsNotNone)
        store_tests.StorePagesTests.response(holder, 0, food)
        store_tests.StorePagesTests.response(holder, 1, product)
        self.observation = w.last_result_name
        self.assertIsNotNone(self.observation)
        public = self.read(self.observation + '-public-fields.json')
        self.context_time = next(o['observed_at'] for o in public['observations'] if o['endpoint_id'] == 'FOOD')
        self.name = self.input('a', 'c', '2026-01-01T00:01:00+00:00')
        w.close('P26_CANCELLED')
        self.result_name = 'store_inventory_' + 'e' * 32

    def input(self, file_letter, request_letter, observed_at, body=None):
        name = export_tests.CategoryExportTests.input(self, file_letter, request_letter, observed_at, body)
        if not hasattr(self, 'observation'):
            return name
        observed = (datetime.fromisoformat(self.context_time)
            + (datetime.fromisoformat(observed_at) - datetime.fromisoformat('2026-01-01T00:00:00+00:00'))).isoformat()
        document = self.read(name)
        document.update(source_context_result_name=self.observation,
            source_context_observed_at=self.context_time, observed_at=observed)
        self.write(name, document)
        probe_name = name.replace('-public-fields.json', '-batch-parameter.json')
        probe = self.read(probe_name)
        probe.update(source_context_result_name=self.observation, observed_at=observed)
        self.write(probe_name, probe)
        return name

    def publish(self, names=None):
        return publish_store_inventory(self.root, self.observation, names or [self.name], self.result_name)

    def test_category_prices_are_separate_and_json_csv_manifest_are_consistent(self):
        before = (self.root / ('result-attempt-' + 'b' * 32 + '.lock')).read_bytes()
        result = self.publish(); destination = self.root / result['result_name']
        view = self.read(result['result_name'] + '/records.json')
        self.assertEqual((view['record_count'], view['product_count'], view['sku_count'], view['category_count']), (4, 1, 2, 2))
        self.assertEqual((view['checked_initial_rows'], view['partial_category_rows']), (2, 2))
        self.assertEqual([(r['category_reference_label'], r['sku_price_number']) for r in view['records']],
            [('Synthetic offer category', '1.2'), ('Synthetic offer category', '2.3'),
             ('Synthetic category 中文', '1.25'), ('Synthetic category 中文', '2.75')])
        self.assertEqual([r['currency'] for r in view['records']], ['CNY', 'CNY', 'UNKNOWN', 'UNKNOWN'])
        self.assertTrue(all(r['category_label_source_file'] == self.observation + '-public-fields.json' for r in view['records']))
        with (destination / 'records.csv').open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream); rows = list(reader)
            self.assertEqual(tuple(reader.fieldnames), CSV_FIELDS)
        self.assertEqual(rows, [{k: '' if v is None else v for k, v in r.items()} for r in view['records']])
        manifest = self.read(result['result_name'] + '/manifest.json')
        self.assertEqual({k:v for k,v in manifest.items() if k not in ('schema_version','result_name','files')},
            {k:v for k,v in view.items() if k not in ('schema_version','records')})
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in destination.iterdir()))
        self.assertEqual((self.root / ('result-attempt-' + 'b' * 32 + '.lock')).read_bytes(), before)
        self.assertEqual(result['live_attempts_consumed'], 0)
        with self.assertRaises(ResultPublishError): _manifest_from_views(view, 'complete_result')

    def test_latest_whole_row_keeps_missing_optional_values_and_older_unrepeated_sku(self):
        body = synthetic_body(); product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['min_price'] = product['render_info']['price_info']['min_price'] = 1.75
        product['skus'] = [{'id': 201, 'price': 1.75}]; product.pop('unit')
        later = self.input('f', '9', '2026-01-01T00:02:00+00:00', body)
        self.publish([later, self.name]); view = self.read(self.result_name + '/records.json')
        rows = [r for r in view['records'] if r['category_ref'] == 'synthetic_category']
        self.assertEqual((rows[0]['sku_price_number'], rows[0]['source_file']), ('1.75', later))
        self.assertIsNone(rows[0]['sku_spec']); self.assertIsNone(rows[0]['product_unit'])
        self.assertEqual(rows[0]['sku_spec_state'], 'NOT_OBSERVED')
        self.assertEqual((rows[1]['sku_price_number'], rows[1]['source_file']), ('2.75', self.name))
        self.assertEqual(view['deduplicated_record_count'], 1)

    def test_new_partial_row_in_same_category_cannot_borrow_initial_currency_or_spec(self):
        body = synthetic_body(); body['data']['food_spu_tags'][0]['tag'] = 'category_a'
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['skus'][0].pop('spec'); product.pop('unit')
        self.input('a', 'c', '2026-01-01T00:01:00+00:00', body)
        self.publish(); view = self.read(self.result_name + '/records.json')
        self.assertEqual((view['record_count'], view['checked_initial_rows'], view['partial_category_rows']), (2, 0, 2))
        self.assertTrue(all(r['currency'] == r['amount_unit'] == 'UNKNOWN' for r in view['records']))
        self.assertIsNone(view['records'][0]['sku_spec']); self.assertIsNone(view['records'][0]['product_unit'])
        self.assertEqual(view['records'][0]['category_reference_label'], 'Synthetic offer category')

    def test_foreign_context_unknown_category_and_owner_change_refuse_output(self):
        original = self.read(self.name)
        for key, value in [('source_context_result_name', 'observation_' + '1' * 32),
                           ('source_context_observed_at', '2026-01-01T00:00:00+00:00')]:
            changed = copy.deepcopy(original); changed[key] = value; self.write(self.name, changed)
            with self.subTest(key=key), self.assertRaises(CategoryCandidateError): self.publish()
            self.assertFalse((self.root / self.result_name).exists())
        for change, code in [('category', 'P29_INVENTORY_CATEGORY_UNREFERENCED'),
                              ('owner', 'P29_INVENTORY_SKU_OWNER_CHANGED')]:
            body = synthetic_body()
            if change == 'category': body['data']['food_spu_tags'][0]['tag'] = 'unobserved_category'
            else: body['data']['food_spu_tags'][0]['dynamic_spus'][0]['id'] = 102
            self.input('a', 'c', '2026-01-01T00:01:00+00:00', body)
            with self.subTest(change=change), self.assertRaises(CategoryCandidateError) as error: self.publish()
            self.assertEqual(error.exception.code, code)
            self.assertFalse((self.root / self.result_name).exists())

    def test_changed_complete_values_or_pair_proof_cannot_be_used_as_initial_identity(self):
        path = self.observation + '/records.json'; original = self.read(path)
        for key, value in [('product', 'Synthetic wrong product'), ('sku_price_yuan', '9.99'),
                           ('store', 'Synthetic wrong shop'), ('category_name', 'Synthetic wrong category')]:
            changed = copy.deepcopy(original); changed['records'][0][key] = value; self.write(path, changed)
            with self.subTest(key=key), self.assertRaises(CategoryCandidateError): self.publish()
            self.assertFalse((self.root / self.result_name).exists())
        self.write(path, original)
        public_name = self.observation + '-public-fields.json'; public = self.read(public_name)
        public['source_association']['same_observation_gap_valid'] = False; self.write(public_name, public)
        with self.assertRaises(CategoryCandidateError): self.publish()

    def test_closed_contracts_refuse_promotion_private_values_and_currency_filling(self):
        body = synthetic_body(); body['data']['session'] = {'cookie': 'synthetic private sentinel'}
        self.input('a', 'c', '2026-01-01T00:01:00+00:00', body)
        view, _, csv_bytes = inventory_view(self.root, self.observation, [self.name])
        self.assertNotIn('synthetic private sentinel', json.dumps(view))
        self.assertNotIn('synthetic private sentinel', csv_bytes.decode())
        for key, value in [('complete_result_promotion', True), ('coverage_status', 'COMPLETE'), ('raw', 'synthetic private sentinel')]:
            with self.subTest(key=key), self.assertRaises(CategoryCandidateError):
                _validate({**view, key:value}, 'p29-store-input-inventory-v1.schema.json')
        changed = copy.deepcopy(view); changed['records'][-1]['currency'] = 'CNY'
        with self.assertRaises(CategoryCandidateError): _validate(changed, 'p29-store-input-inventory-v1.schema.json')

    def test_no_overwrite_budget_and_publication_failure_preserve_prior_outputs(self):
        previous = self.root / self.result_name; previous.mkdir(mode=0o700)
        sentinel = previous / 'keep'; sentinel.write_bytes(b'synthetic existing result')
        with self.assertRaises(ResultPublishError): self.publish()
        self.assertEqual(sentinel.read_bytes(), b'synthetic existing result')
        previous.rename(self.root / 'previous')
        with patch('collection_adapter.p29_store_inventory.MAX_COLLECTION_BYTES', 1), self.assertRaises(CategoryCandidateError): self.publish()
        self.assertFalse((self.root / self.result_name).exists())
        from collection_adapter.p29_store_inventory import _write_file
        def fail_manifest(fd, name, content):
            if name == 'manifest.json': raise OSError('synthetic private error')
            return _write_file(fd, name, content)
        with patch('collection_adapter.p29_store_inventory._write_file', side_effect=fail_manifest), self.assertRaises(ResultPublishError) as error:
            self.publish()
        self.assertEqual(error.exception.code, 'RESULT_PUBLISH_FAILED')
        self.assertFalse((self.root / self.result_name).exists())
        self.assertEqual((self.root / 'previous' / 'keep').read_bytes(), b'synthetic existing result')

    def test_missing_owned_input_and_invalid_name_return_fixed_codes(self):
        with self.assertRaises(CategoryCandidateError) as caught:
            publish_store_inventory(self.root, self.observation, [self.name], '')
        self.assertEqual(str(caught.exception), 'P29_INVENTORY_NAME_INVALID')
        (self.root / (self.observation + '-public-fields.json')).unlink()
        with self.assertRaises(CategoryCandidateError) as caught: self.publish()
        self.assertEqual(str(caught.exception), 'P29_INVENTORY_INPUT_INVALID')
        self.assertFalse((self.root / self.result_name).exists())


if __name__ == '__main__':
    unittest.main()
