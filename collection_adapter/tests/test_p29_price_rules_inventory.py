import csv
import json
from pathlib import Path
import stat
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from collection_adapter.p29_store_inventory import (
    CSV_PRICE_FIELDS, publish_store_price_inventory, publish_store_price_rules, rules_inventory_view,
)
from collection_adapter.tests.test_p29_store_inventory import StoreInventoryTests
from collection_core.result_publisher import ResultPublishError
from parser_candidate.p29_category_profile import CategoryCandidateError
from collection_adapter.tests.test_p29_category_review import synthetic_body
from parser_candidate.tests.test_p29_price_rules import rules_body


class PriceRuleInventoryTests(StoreInventoryTests):
    def setUp(self):
        super().setUp()
        self.rules_name = 'store_price_rules_' + 'e' * 32
        self.input('a', 'c', '2026-01-01T00:01:00+00:00', rules_body())

    def schema(self, name):
        root = Path(__file__).resolve().parents[2] / 'contracts/schemas'
        resources = {path.name: Resource.from_contents(json.loads(path.read_text()))
                     for path in root.glob('*.schema.json')}
        return Draft202012Validator(json.loads((root / name).read_text()),
            registry=Registry().with_resources(resources.items()), format_checker=FormatChecker())

    def test_initial_rows_do_not_borrow_category_rules(self):
        result = publish_store_price_rules(self.root, self.observation, [self.name], self.rules_name)
        view = self.read(self.rules_name + '/records.json')
        initial = [row for row in view['records'] if row['source_kind'] == 'CHECKED_INITIAL_PAIR']
        category = [row for row in view['records'] if row['source_kind'] == 'PARTIAL_CATEGORY_CANDIDATE']
        self.assertEqual(result['live_attempts_consumed'], 0)
        self.assertEqual(view['schema_version'], 'p29-store-input-inventory/v3')
        self.assertEqual((len(initial), len(category)), (2, 2))
        self.assertTrue(all(
            row['currency'] == 'CNY' and row['product_discount_by_count_scope'] == 'NOT_REPARSED_ON_INITIAL_PAIR'
            and row['sku_discount_by_count_count_state'] == 'NOT_REPARSED_ON_INITIAL_PAIR'
            and row['sku_discount_by_count_count_number'] is None
            and row['sku_full_discount_tag_texts'] is None
            and row['sku_full_discount_tag_texts_json'] is None
            and row['sku_ladder_package_pair_state'] == 'NOT_REPARSED_ON_INITIAL_PAIR'
            for row in initial))
        own = next(row for row in category if row['sku_id'] == '201')
        other = next(row for row in category if row['sku_id'] == '202')
        self.assertEqual(own['product_discount_by_count_scope'], 'PRODUCT')
        self.assertEqual(own['sku_discount_by_count_scope'], 'SKU')
        self.assertEqual(own['product_discount_by_count_discount_number'], '2')
        self.assertEqual(own['sku_discount_by_count_discount_number'], '3')
        self.assertEqual(own['sku_ladder_package_food_num_number'], '2')
        self.assertEqual(own['sku_ladder_package_price_number'], '0')
        self.assertIsNone(own['currency'])
        self.assertEqual([(item['tag_index'], item['sub_tag_index']) for item in own['sku_full_discount_tag_texts']],
                         [(0, 0), (0, 1), (1, 0)])
        self.assertEqual(other['sku_discount_by_count_pair_state'], 'COUNT_KEY_NOT_OBSERVED')
        self.assertIsNone(other['sku_full_discount_tag_texts'])
        self.assertFalse(view['count_zero_means_no_threshold'])
        self.assertFalse(view['zero_amount_means_free'])
        self.assertFalse(view['negative_adapted_as_amount'])
        self.assertFalse(view['nested_rules_concatenated'])
        self.assertFalse(view['cross_observation_rule_fields_copied'])
        self.assertFalse(view['category_currency_borrowed_from_initial_pair'])
        self.assertTrue(self.schema('p29-store-input-inventory-v3.schema.json').is_valid(view))
        manifest = self.read(self.rules_name + '/manifest.json')
        self.assertTrue(self.schema('p29-store-input-inventory-manifest-v3.schema.json').is_valid(manifest))
        destination = self.root / self.rules_name
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
        with (destination / 'records.csv').open(newline='') as stream:
            reader = csv.DictReader(stream)
            csv_rows = list(reader)
        own_csv = next(row for row in csv_rows if row['sku_id'] == '201' and row['source_kind'] == 'PARTIAL_CATEGORY_CANDIDATE')
        self.assertEqual(json.loads(own_csv['sku_full_discount_tag_texts_json']), own['sku_full_discount_tag_texts'])
        self.assertNotIn('synthetic_color', json.dumps(view))

    def test_newer_category_row_replaces_initial_without_keeping_its_rule_gap(self):
        body = synthetic_body()
        body['data']['food_spu_tags'][0]['tag'] = 'category_a'
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['skus'] = [product['skus'][0]]
        product['min_price'] = product['render_info']['price_info']['min_price'] = 9
        product['skus'][0]['price'] = 9
        product['activity_policy'] = {'discount_by_count': {'count': 1, 'discount': 6}}
        product['skus'][0]['activity_policy'] = {'discount_by_count': {'count': 1, 'discount': 6}}
        name = self.input('f', '9', '2026-01-01T00:03:00+00:00', body)
        result_name = 'store_price_rules_' + 'a' * 32
        publish_store_price_rules(self.root, self.observation, [name], result_name)
        rows = {row['sku_id']: row for row in self.read(result_name + '/records.json')['records']
                if row['category_ref'] == 'category_a'}
        self.assertEqual(rows['201']['source_kind'], 'PARTIAL_CATEGORY_CANDIDATE')
        self.assertIsNone(rows['201']['currency'])
        self.assertEqual(rows['201']['sku_price_number'], '9')
        self.assertEqual(rows['201']['sku_discount_by_count_discount_number'], '6')
        self.assertNotEqual(rows['201']['sku_discount_by_count_discount_state'], 'NOT_REPARSED_ON_INITIAL_PAIR')
        self.assertEqual(rows['202']['source_kind'], 'CHECKED_INITIAL_PAIR')
        self.assertEqual(rows['202']['currency'], 'CNY')
        self.assertIsNone(rows['202']['sku_discount_by_count_discount_number'])
        self.assertEqual(rows['202']['sku_discount_by_count_discount_state'], 'NOT_REPARSED_ON_INITIAL_PAIR')

    def test_older_category_rules_do_not_fill_a_newer_initial_row(self):
        body = synthetic_body()
        body['data']['food_spu_tags'][0]['tag'] = 'category_a'
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['skus'] = [product['skus'][0]]
        product['activity_policy'] = {'discount_by_count': {'count': 4, 'discount': 9}}
        product['skus'][0]['activity_policy'] = {'discount_by_count': {'count': 4, 'discount': 9}}
        name = self.input('f', '9', '2025-12-31T00:00:00+00:00', body)
        result_name = 'store_price_rules_' + 'c' * 32
        publish_store_price_rules(self.root, self.observation, [name], result_name)
        row = next(item for item in self.read(result_name + '/records.json')['records']
                   if item['category_ref'] == 'category_a' and item['sku_id'] == '201')
        self.assertEqual(row['source_kind'], 'CHECKED_INITIAL_PAIR')
        self.assertEqual(row['currency'], 'CNY')
        self.assertIsNone(row['sku_discount_by_count_discount_number'])
        self.assertEqual(row['sku_discount_by_count_discount_state'], 'NOT_REPARSED_ON_INITIAL_PAIR')
        self.assertNotEqual(row['source_file'], name)

    def test_same_time_rule_conflict_rejects_inventory(self):
        body = rules_body()
        body['data']['food_spu_tags'][0]['dynamic_spus'][0]['skus'][0]['activity_policy']['discount_by_count']['count'] = 2
        other = self.input('f', '9', '2026-01-01T00:01:00+00:00', body)
        for names in ([self.name, other], [other, self.name]):
            with self.subTest(order=names):
                with self.assertRaises(CategoryCandidateError) as raised:
                    rules_inventory_view(self.root, self.observation, names)
                self.assertEqual(raised.exception.code, 'P29_CATEGORY_BATCH_ORDER_AMBIGUOUS')

    def test_v2_inventory_and_republish_stay_unchanged(self):
        v2_name = 'store_price_inventory_' + 'd' * 32
        publish_store_price_inventory(self.root, self.observation, [self.name], v2_name)
        v2_view = self.read(v2_name + '/records.json')
        self.assertEqual(v2_view['schema_version'], 'p29-store-input-inventory/v2')
        self.assertNotIn('sku_full_discount_tag_texts', v2_view['records'][0])
        self.assertTrue(self.schema('p29-store-input-inventory-v2.schema.json').is_valid(v2_view))
        with (self.root / v2_name / 'records.csv').open(newline='') as stream:
            self.assertEqual(tuple(csv.DictReader(stream).fieldnames), CSV_PRICE_FIELDS)
        publish_store_price_rules(self.root, self.observation, [self.name], self.rules_name)
        before = (self.root / self.rules_name / 'records.json').read_bytes()
        with self.assertRaises(ResultPublishError):
            publish_store_price_rules(self.root, self.observation, [self.name], self.rules_name)
        self.assertEqual((self.root / self.rules_name / 'records.json').read_bytes(), before)
        self.assertTrue((self.root / v2_name / 'records.json').is_file())


if __name__ == '__main__':
    unittest.main()
