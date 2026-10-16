import csv
import io
import json
import stat
import unittest
from unittest.mock import patch

from collection_adapter.tests.test_p28_business_batch import bodies
from collection_adapter.tests import test_p29_store_inventory as fixtures
from collection_adapter import p31_business_export as export
from collection_adapter.p31_business_export import business_view
from collection_adapter.tests.test_p29_category_review import synthetic_body
from collection_adapter.p29_store_inventory import initial_price_rules_inventory_view, _validate
from collection_core.result_publisher import ResultPublishError
from parser_candidate.p29_category_profile import CategoryCandidateError


def extended_bodies():
    food, product = bodies()
    food['data']['poi_info'].update(address='Synthetic 地址, "入口"', shipping_fee=3.5)
    item = product['data']['food_spu_tags'][0]['dynamic_spus'][0]
    item.update(description='Synthetic 商品, "说明"', month_saled=0, stock=-1)
    item['skus'][0].update(min_order_count=2, real_stock=-1)
    item['attrs'] = [{'name': 'Synthetic 口味', 'choose_n': 1,
                      'values': [{'id': 901, 'value': 'Synthetic 辣味', 'hidden': False}]}]
    return food, product


class BusinessExportTests(fixtures.StoreInventoryTests):
    def setUp(self):
        with patch('collection_adapter.tests.test_p29_store_inventory.bodies', extended_bodies):
            super().setUp()
        root = patch('collection_adapter.p31_business_export._root', return_value=self.root)
        root.start()
        self.addCleanup(root.stop)
        self.bundle_name = 'p31_public_fields_' + 'f' * 32

    def test_initial_description_is_exported_from_own_projection(self):
        products, _ = business_view(self.root, self.observation, [self.name])
        row = next(r for r in products['records'] if r['source_kind'] == 'CHECKED_INITIAL_PAIR')
        self.assertEqual(row.get('product_description_text'), 'Synthetic 商品, "说明"')

    def test_bundle_preserves_base_rows_and_separates_store_with_import_dictionary(self):
        base, _, _ = initial_price_rules_inventory_view(self.root, self.observation, [self.name])
        result = export.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        destination = self.root / self.bundle_name
        products = self.read(self.bundle_name + '/records.json')
        stores = self.read(self.bundle_name + '/stores.json')
        self.assertEqual(result['live_attempts_consumed'], 0)
        self.assertEqual(set(p.name for p in destination.iterdir()), set(export.FILES))
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in destination.iterdir()))
        for old, new in zip(base['records'], products['records']):
            self.assertEqual({k: new[k] for k in old}, old)
            self.assertNotIn('store_address_text', new)
        self.assertEqual(stores['records'][0]['store_address_text'], 'Synthetic 地址, "入口"')
        self.assertEqual(stores['records'][0]['store_shipping_fee_number'], '3.5')
        self.assertNotEqual(stores['records'][0]['source_request_ref'], products['records'][0]['source_request_ref'])
        self.assertFalse(stores['delivery_terms_apply_to_all_customers'])
        for file, document in [('records.csv', products), ('stores.csv', stores)]:
            with (destination / file).open(newline='') as stream:
                reader = csv.DictReader(stream)
                actual = list(reader)
                expected = [{k: export._cell(row[k]) for k in reader.fieldnames} for row in document['records']]
                self.assertEqual(actual, expected)
        dictionary = self.read(self.bundle_name + '/field_dictionary.json')
        columns, store_columns = export.csv_fields()
        self.assertEqual([x['field'] for x in dictionary['fields'] if x['table'] == 'products'], list(columns))
        self.assertEqual([x['field'] for x in dictionary['fields'] if x['table'] == 'stores'], list(store_columns))
        coverage = self.read(self.bundle_name + '/coverage.json')
        self.assertTrue(all(sum(row['states'].values()) == row['row_count'] for row in coverage['fields']))
        malformed = json.loads(json.dumps(products))
        malformed['records'][0]['unbounded'] = {}
        with self.assertRaises(CategoryCandidateError):
            _validate(malformed, export.PRODUCT_SCHEMA)
        before = {p.name: p.read_bytes() for p in destination.iterdir()}
        with self.assertRaises(ResultPublishError):
            export.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, before)

    def test_equal_time_new_field_difference_cannot_hide_behind_equal_prices(self):
        body = synthetic_body()
        body['data']['food_spu_tags'][0]['dynamic_spus'][0]['description'] = 'Synthetic first'
        first = self.input('a', 'c', '2026-01-01T00:01:00+00:00', body)
        body['data']['food_spu_tags'][0]['dynamic_spus'][0]['description'] = 'Synthetic second'
        second = self.input('b', 'd', '2026-01-01T00:01:00+00:00', body)
        with self.assertRaises(CategoryCandidateError) as raised:
            business_view(self.root, self.observation, [first, second])
        self.assertEqual(raised.exception.code, 'P31_EXPORT_EQUAL_TIME_FIELDS_CONFLICT')

    def test_newer_category_does_not_borrow_initial_description_or_attributes(self):
        body = synthetic_body()
        body['data']['food_spu_tags'][0]['tag'] = 'category_a'
        name = self.input('b', 'd', '2026-01-01T00:02:00+00:00', body)
        products, _ = business_view(self.root, self.observation, [name])
        rows = [r for r in products['records'] if r['category_ref'] == 'category_a']
        self.assertTrue(all(r['product_description_text_state'] == 'NOT_OBSERVED' for r in rows))
        self.assertTrue(all(r['product_attributes'] is None and r['currency'] is None for r in rows))

    def test_failure_before_or_during_publish_preserves_no_partial_directory(self):
        with patch.object(export, 'MAX_COLLECTION_BYTES', 1), self.assertRaises(CategoryCandidateError):
            export.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        self.assertFalse((self.root / self.bundle_name).exists())
        original = export._write_file
        def fail_on_csv(fd, name, content):
            if name == 'manifest.json':
                raise OSError()
            original(fd, name, content)
        with patch.object(export, '_write_file', side_effect=fail_on_csv), self.assertRaises(ResultPublishError):
            export.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        self.assertFalse((self.root / self.bundle_name).exists())
