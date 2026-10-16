import contextlib
import csv
import io
import json
from pathlib import Path
import stat
import unittest
from dataclasses import replace
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from collection_adapter.p29_store_inventory import (
    CSV_FIELDS, CSV_PRICE_FIELDS, CSV_PRICE_RULE_FIELDS, initial_price_rules_inventory_view,
    main, publish_store_initial_price_rules, publish_store_inventory, publish_store_price_inventory,
    publish_store_price_rules,
)
from collection_adapter.tests.test_p28_business_batch import bodies
from collection_adapter.tests.test_p29_price_rules_inventory import PriceRuleInventoryTests
from collection_core.result_publisher import ResultPublishError
from parser_candidate.p29_category_price import CategoryPriceParse, parse_category_price
from parser_candidate.p29_category_profile import CategoryCandidateError
from parser_candidate.p29_price_rules import (
    NEGATIVE_NOT_ADAPTED, PRESENT_TEXT_UNCONFIRMED, PRESENT_UNCONFIRMED, SOURCE_NULL,
)


def _initial_bodies():
    food, product = bodies()
    item = product['data']['food_spu_tags'][0]['dynamic_spus'][0]
    item['full_discount_price'] = 8.8
    item['max_discount'] = 0
    item['preferential_feeling_price'] = None
    item['activity_policy'] = {'discount_by_count': {'count': 0, 'discount': 5}}
    item['render_info']['price_info'].update(
        origin_price=9, min_price_tail='', price_desc='元',
        coupon_count=0, multi_activity_price=-3, show_origin_price=1)
    item['render_info']['sup_info'] = {'discountTag': ''}
    item['skus'][0].update(member_price=-4, full_discount_price=0, box_price=0, price_desc='')
    item['skus'][0]['activity_policy'] = {'discount_by_count': {'count': None, 'discount': -1}}
    item['skus'][0]['sku_ladder_box_info'] = {'ladder_package_food_num': 3, 'ladder_package_price': 0}
    item['skus'][0]['full_discount_tag'] = [{'sub_tags': [{'text': ''}, {'text': '元'}]}]
    item['skus'][1]['box_price'] = None
    item['skus'][1]['activity_policy'] = {'discount_by_count': {'discount': 4}}
    item['skus'][1]['sku_ladder_box_info'] = {'ladder_package_price': 1}
    product['data']['currency'] = 'USD'
    product['data']['amount_unit'] = 'FEN'
    return food, product


class InitialPriceInventoryTests(PriceRuleInventoryTests):
    def setUp(self):
        with patch('collection_adapter.tests.test_p29_store_inventory.bodies', side_effect=_initial_bodies):
            super().setUp()
        self.initial_name = 'store_initial_price_rules_' + 'f' * 32

    def schema(self, name):
        root = Path(__file__).resolve().parents[2] / 'contracts/schemas'
        resources = {path.name: Resource.from_contents(json.loads(path.read_text()))
                     for path in root.glob('*.schema.json')}
        return Draft202012Validator(json.loads((root / name).read_text()),
            registry=Registry().with_resources(resources.items()), format_checker=FormatChecker())

    def publish_v4(self, names=None, result_name=None):
        return publish_store_initial_price_rules(
            self.root, self.observation, names or [self.name], result_name or self.initial_name)

    def test_initial_and_category_keep_own_sources_and_page_confirmed_currency(self):
        result = self.publish_v4()
        view = self.read(self.initial_name + '/records.json')
        initial = [row for row in view['records'] if row['source_kind'] == 'CHECKED_INITIAL_PAIR']
        category = [row for row in view['records'] if row['source_kind'] == 'PARTIAL_CATEGORY_CANDIDATE']
        self.assertEqual(result['code'], 'P29_STORE_INITIAL_PRICE_RULES_EXPORTED')
        self.assertEqual(result['live_attempts_consumed'], 0)
        self.assertFalse(result['currency_inferred'])
        self.assertTrue(result['initial_pair_additional_price_reparsed'])
        self.assertTrue(result['initial_pair_price_rules_reparsed'])
        self.assertEqual(view['schema_version'], 'p29-store-input-inventory/v4')
        self.assertEqual((len(initial), len(category)), (2, 2))
        self.assertTrue(view['initial_pair_additional_price_reparsed'])
        self.assertTrue(view['initial_pair_price_rules_reparsed'])
        self.assertFalse(view['currency_inferred'])
        self.assertFalse(view['category_currency_borrowed_from_initial_pair'])
        self.assertFalse(view['complete_result_promotion'])
        self.assertFalse(view['cross_observation_prices_or_specs_copied'])
        self.assertFalse(view['cross_observation_rule_fields_copied'])
        self.assertEqual(view['coverage_status'], 'PARTIAL')
        self.assertEqual(view['rule_profile_kind'], 'LOCAL_OBSERVED_PRICE_RULE_EVIDENCE')
        self.assertTrue(all(
            row['currency'] == 'CNY' and row['amount_unit'] == 'YUAN'
            and row['currency_status'] == 'PAGE_CONFIRMED_FOR_INITIAL_PAIR_ONLY'
            and row['amount_unit_status'] == 'PAGE_CONFIRMED_FOR_INITIAL_PAIR_ONLY'
            and row['currency_basis'] == 'INITIAL_PAIR_PAGE_CONFIRMATION'
            and row['amount_unit_basis'] == 'INITIAL_PAIR_PAGE_CONFIRMATION'
            and row['sku_price_source'] == 'INITIAL_PAIR_PAGE_CONFIRMED_SKU_PRICE'
            and row['numeric_min_relation'] == 'NOT_REPARSED_ON_INITIAL_PAIR'
            and row['product_unit_role'] == 'NOT_REPARSED_ON_INITIAL_PAIR'
            and row['source_file'] == self.observation + '-public-fields.json'
            and row['product_full_discount_price_number'] == '8.8'
            and row['product_discount_by_count_discount_number'] == '5'
            for row in initial))
        own = next(row for row in category if row['sku_id'] == '201')
        self.assertIsNone(own['currency'])
        self.assertIsNone(own['amount_unit'])
        self.assertEqual(own['currency_basis'], 'NOT_BORROWED_FROM_INITIAL_PAIR')
        self.assertEqual(own['amount_unit_basis'], 'NOT_BORROWED_FROM_INITIAL_PAIR')
        self.assertEqual(own['currency_status'], 'NOT_PROVIDED_IN_OBSERVED_PUBLIC_STRUCTURE')
        self.assertEqual(own['product_full_discount_price_number'], '1.1')
        self.assertEqual(own['product_discount_by_count_discount_number'], '2')
        self.assertNotEqual(own['source_file'], initial[0]['source_file'])
        self.assertNotIn('USD', json.dumps(view))
        self.assertNotIn('FEN', json.dumps(view))
        self.assertTrue(self.schema('p29-store-input-inventory-v4.schema.json').is_valid(view))
        manifest = self.read(self.initial_name + '/manifest.json')
        self.assertEqual(manifest['schema_version'], 'p29-store-input-inventory-manifest/v4')
        self.assertTrue(manifest['initial_pair_additional_price_reparsed'])
        self.assertTrue(self.schema('p29-store-input-inventory-manifest-v4.schema.json').is_valid(manifest))
        destination = self.root / self.initial_name
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in destination.iterdir()))
        with (destination / 'records.csv').open(newline='') as stream:
            reader = csv.DictReader(stream)
            csv_rows = list(reader)
            self.assertEqual(tuple(reader.fieldnames), CSV_PRICE_RULE_FIELDS)
        self.assertEqual(len(csv_rows), len(view['records']))
        for record, csv_row in zip(view['records'], csv_rows):
            for key in CSV_PRICE_RULE_FIELDS:
                expected = '' if record[key] is None else record[key]
                self.assertEqual(csv_row[key], expected)
            if record['sku_full_discount_tag_texts'] is None:
                self.assertEqual(csv_row['sku_full_discount_tag_texts_json'], '')
            else:
                self.assertEqual(csv_row['sku_full_discount_tag_texts_json'], record['sku_full_discount_tag_texts_json'])
                self.assertEqual(json.loads(csv_row['sku_full_discount_tag_texts_json']),
                                 record['sku_full_discount_tag_texts'])
        changed = json.loads(json.dumps(view))
        changed['records'][0]['sku_member_price_state'] = 'NOT_REPARSED_ON_INITIAL_PAIR'
        self.assertFalse(self.schema('p29-store-input-inventory-v4.schema.json').is_valid(changed))
        changed = json.loads(json.dumps(view))
        changed['promoted_to_parser'] = True
        self.assertFalse(self.schema('p29-store-input-inventory-v4.schema.json').is_valid(changed))

    def test_unknown_empty_negative_and_zero_keep_separate_price_and_rule_states(self):
        self.publish_v4()
        rows = {row['sku_id']: row for row in self.read(self.initial_name + '/records.json')['records']
                if row['source_kind'] == 'CHECKED_INITIAL_PAIR'}
        first, second = rows['201'], rows['202']
        self.assertEqual(first['sku_member_price_state'], 'PRESENT_NEGATIVE_NUMBER_NOT_ADAPTED_AS_AMOUNT')
        self.assertIsNone(first['sku_member_price_number'])
        self.assertEqual(first['sku_full_discount_price_number'], '0')
        self.assertEqual(first['sku_full_discount_price_state'], PRESENT_UNCONFIRMED)
        self.assertEqual(first['sku_box_price_number'], '0')
        self.assertEqual(first['sku_price_desc'], '')
        self.assertEqual(first['sku_price_desc_state'], 'SOURCE_EMPTY')
        self.assertEqual(first['render_origin_number'], '9')
        self.assertEqual(first['render_origin_state'], PRESENT_UNCONFIRMED)
        self.assertEqual(first['min_price_tail'], '')
        self.assertEqual(first['min_price_tail_state'], 'SOURCE_EMPTY')
        self.assertEqual(first['render_price_desc'], '元')
        self.assertEqual(first['render_price_desc_state'], 'CLOSED_MARK_NOT_PROMOTED_TO_CURRENCY_OR_AMOUNT_UNIT')
        self.assertEqual(second['sku_member_price_state'], 'NOT_OBSERVED')
        self.assertIsNone(second['sku_member_price_number'])
        self.assertEqual(second['sku_box_price_state'], 'NOT_OBSERVED')
        self.assertIsNone(second['sku_full_discount_price_number'])
        self.assertEqual(first['product_discount_by_count_count_number'], '0')
        self.assertEqual(first['product_discount_by_count_count_state'], PRESENT_UNCONFIRMED)
        self.assertEqual(first['product_discount_by_count_pair_state'], 'BOTH_KEYS_PRESENT')
        self.assertEqual(first['product_max_discount_number'], '0')
        self.assertEqual(first['product_max_discount_state'], PRESENT_UNCONFIRMED)
        self.assertIsNone(first['product_preferential_feeling_price_number'])
        self.assertEqual(first['product_preferential_feeling_price_state'], SOURCE_NULL)
        self.assertEqual(first['product_coupon_count_number'], '0')
        self.assertEqual(first['product_coupons_per_price_state'], 'NOT_OBSERVED')
        self.assertIsNone(first['product_multi_activity_price_number'])
        self.assertEqual(first['product_multi_activity_price_state'], NEGATIVE_NOT_ADAPTED)
        self.assertEqual(first['product_show_origin_price_number'], '1')
        self.assertEqual(first['product_show_origin_price_state'], PRESENT_UNCONFIRMED)
        self.assertEqual(first['product_discount_tag_text'], '')
        self.assertEqual(first['product_discount_tag_text_state'], 'SOURCE_EMPTY')
        self.assertEqual(first['sku_discount_by_count_count_state'], SOURCE_NULL)
        self.assertIsNone(first['sku_discount_by_count_count_number'])
        self.assertEqual(first['sku_discount_by_count_discount_state'], NEGATIVE_NOT_ADAPTED)
        self.assertIsNone(first['sku_discount_by_count_discount_number'])
        self.assertEqual(first['sku_discount_by_count_pair_state'], 'BOTH_KEYS_PRESENT')
        self.assertEqual(first['sku_discount_by_count_scope'], 'SKU')
        self.assertEqual(first['product_discount_by_count_scope'], 'PRODUCT')
        self.assertEqual(second['sku_discount_by_count_pair_state'], 'COUNT_KEY_NOT_OBSERVED')
        self.assertEqual(second['sku_discount_by_count_count_state'], 'NOT_OBSERVED')
        self.assertEqual(second['sku_discount_by_count_discount_number'], '4')
        self.assertEqual(second['sku_discount_by_count_discount_state'], PRESENT_UNCONFIRMED)
        self.assertEqual(first['sku_ladder_package_food_num_number'], '3')
        self.assertEqual(first['sku_ladder_package_price_number'], '0')
        self.assertEqual(first['sku_ladder_package_price_state'], PRESENT_UNCONFIRMED)
        self.assertEqual(first['sku_ladder_package_pair_state'], 'BOTH_KEYS_PRESENT')
        self.assertEqual(second['sku_ladder_package_pair_state'], 'FOOD_NUM_KEY_NOT_OBSERVED')
        self.assertEqual(second['sku_ladder_package_food_num_state'], 'NOT_OBSERVED')
        self.assertEqual(first['sku_full_discount_tag_texts_state'], 'PRESENT_INDEXED_GROUP')
        self.assertEqual([(item['tag_index'], item['sub_tag_index'], item['text'], item['text_state'])
                          for item in first['sku_full_discount_tag_texts']],
                         [(0, 0, '', 'SOURCE_EMPTY'),
                          (0, 1, '元', 'CLOSED_MARK_NOT_PROMOTED_TO_CURRENCY_OR_AMOUNT_UNIT')])
        self.assertEqual(second['sku_full_discount_tag_texts_state'], 'NOT_OBSERVED')
        self.assertIsNone(second['sku_full_discount_tag_texts'])
        self.assertEqual(first['product_discount_tag_text_state'], 'SOURCE_EMPTY')
        self.assertEqual(first['sku_member_price_state'], first['sku_discount_by_count_discount_state'])
        self.assertNotEqual(PRESENT_UNCONFIRMED, PRESENT_TEXT_UNCONFIRMED)
        view = self.read(self.initial_name + '/records.json')
        self.assertFalse(view['count_zero_means_no_threshold'])
        self.assertFalse(view['discount_number_proves_algorithm'])
        self.assertFalse(view['zero_amount_means_free'])
        self.assertFalse(view['negative_adapted_as_amount'])
        self.assertFalse(view['display_only_fields_passed_through'])
        self.assertFalse(view['nested_rules_concatenated'])

    def test_later_category_row_replaces_the_whole_initial_row(self):
        from collection_adapter.tests.test_p29_category_review import synthetic_body
        body = synthetic_body()
        body['data']['food_spu_tags'][0]['tag'] = 'category_a'
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['skus'] = [product['skus'][0]]
        product['min_price'] = product['render_info']['price_info']['min_price'] = 9
        product['skus'][0]['price'] = 9
        product['skus'][0]['member_price'] = 7
        product['activity_policy'] = {'discount_by_count': {'count': 1, 'discount': 6}}
        product['skus'][0]['activity_policy'] = {'discount_by_count': {'count': 1, 'discount': 6}}
        name = self.input('f', '9', '2026-01-01T00:03:00+00:00', body)
        result_name = 'store_initial_price_rules_' + 'a' * 32
        self.publish_v4([self.name, name], result_name)
        rows = {row['sku_id']: row for row in self.read(result_name + '/records.json')['records']
                if row['category_ref'] == 'category_a'}
        self.assertEqual(rows['201']['source_kind'], 'PARTIAL_CATEGORY_CANDIDATE')
        self.assertIsNone(rows['201']['currency'])
        self.assertIsNone(rows['201']['amount_unit'])
        self.assertEqual(rows['201']['sku_price_number'], '9')
        self.assertEqual(rows['201']['sku_member_price_number'], '7')
        self.assertEqual(rows['201']['sku_discount_by_count_discount_number'], '6')
        self.assertNotEqual(rows['201']['product_full_discount_price_number'], '8.8')
        self.assertEqual(rows['201']['source_file'], name)
        self.assertEqual(rows['202']['source_kind'], 'CHECKED_INITIAL_PAIR')
        self.assertEqual(rows['202']['currency'], 'CNY')
        self.assertEqual(rows['202']['amount_unit'], 'YUAN')
        self.assertEqual(rows['202']['product_discount_by_count_discount_number'], '5')
        self.assertNotEqual(rows['202']['sku_member_price_state'], 'PRESENT_NEGATIVE_NUMBER_NOT_ADAPTED_AS_AMOUNT')

    def test_older_category_values_do_not_fill_a_newer_initial_row(self):
        from collection_adapter.tests.test_p29_category_review import synthetic_body
        body = synthetic_body()
        body['data']['food_spu_tags'][0]['tag'] = 'category_a'
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['skus'] = [product['skus'][0]]
        product['full_discount_price'] = 4.4
        product['activity_policy'] = {'discount_by_count': {'count': 4, 'discount': 9}}
        product['skus'][0]['activity_policy'] = {'discount_by_count': {'count': 4, 'discount': 9}}
        product['skus'][0]['member_price'] = 6
        name = self.input('f', '9', '2025-12-31T00:00:00+00:00', body)
        result_name = 'store_initial_price_rules_' + 'c' * 32
        self.publish_v4([name], result_name)
        row = next(item for item in self.read(result_name + '/records.json')['records']
                   if item['category_ref'] == 'category_a' and item['sku_id'] == '201')
        self.assertEqual(row['source_kind'], 'CHECKED_INITIAL_PAIR')
        self.assertEqual(row['currency'], 'CNY')
        self.assertEqual(row['sku_member_price_state'], 'PRESENT_NEGATIVE_NUMBER_NOT_ADAPTED_AS_AMOUNT')
        self.assertIsNone(row['sku_member_price_number'])
        self.assertEqual(row['product_full_discount_price_number'], '8.8')
        self.assertEqual(row['sku_discount_by_count_discount_state'], NEGATIVE_NOT_ADAPTED)
        self.assertNotEqual(row['source_file'], name)

    def test_v1_v2_and_v3_stay_unchanged_and_republish_does_not_overwrite(self):
        v1_name = 'store_inventory_' + '1' * 32
        v2_name = 'store_price_inventory_' + '2' * 32
        v3_name = 'store_price_rules_' + '3' * 32
        publish_store_inventory(self.root, self.observation, [self.name], v1_name)
        publish_store_price_inventory(self.root, self.observation, [self.name], v2_name)
        publish_store_price_rules(self.root, self.observation, [self.name], v3_name)
        self.publish_v4()
        v1_view = self.read(v1_name + '/records.json')
        v2_view = self.read(v2_name + '/records.json')
        v3_view = self.read(v3_name + '/records.json')
        v4_view = self.read(self.initial_name + '/records.json')
        self.assertEqual(v1_view['schema_version'], 'p29-store-input-inventory/v1')
        self.assertEqual(v2_view['schema_version'], 'p29-store-input-inventory/v2')
        self.assertEqual(v3_view['schema_version'], 'p29-store-input-inventory/v3')
        self.assertNotIn('sku_full_discount_tag_texts', v1_view['records'][0])
        self.assertNotIn('sku_full_discount_tag_texts', v2_view['records'][0])
        self.assertNotIn('initial_pair_price_rules_reparsed', v3_view)
        self.assertTrue(all(
            row['sku_member_price_state'] == 'NOT_REPARSED_ON_INITIAL_PAIR'
            and row['product_discount_by_count_scope'] == 'NOT_REPARSED_ON_INITIAL_PAIR'
            and row['sku_full_discount_tag_texts'] is None
            for row in v3_view['records'] if row['source_kind'] == 'CHECKED_INITIAL_PAIR'))
        self.assertTrue(self.schema('p29-store-input-inventory-v1.schema.json').is_valid(v1_view))
        self.assertTrue(self.schema('p29-store-input-inventory-v2.schema.json').is_valid(v2_view))
        self.assertTrue(self.schema('p29-store-input-inventory-v3.schema.json').is_valid(v3_view))
        with (self.root / v1_name / 'records.csv').open(newline='') as stream:
            self.assertEqual(tuple(csv.DictReader(stream).fieldnames), CSV_FIELDS)
        with (self.root / v2_name / 'records.csv').open(newline='') as stream:
            self.assertEqual(tuple(csv.DictReader(stream).fieldnames), CSV_PRICE_FIELDS)
        v3_category = [row for row in v3_view['records'] if row['source_kind'] == 'PARTIAL_CATEGORY_CANDIDATE']
        v4_category = [row for row in v4_view['records'] if row['source_kind'] == 'PARTIAL_CATEGORY_CANDIDATE']
        self.assertEqual(v3_category, v4_category)
        kept = ('currency', 'amount_unit', 'currency_status', 'amount_unit_status', 'currency_basis',
                'amount_unit_basis', 'sku_price_source', 'numeric_min_relation', 'product_unit_role',
                'sku_price_number', 'product_min_price_number', 'sku_origin_number', 'product_id', 'sku_id',
                'category_ref', 'source_kind', 'source_file')
        for old, new in zip(
                (row for row in v3_view['records'] if row['source_kind'] == 'CHECKED_INITIAL_PAIR'),
                (row for row in v4_view['records'] if row['source_kind'] == 'CHECKED_INITIAL_PAIR')):
            self.assertEqual({key: old[key] for key in kept}, {key: new[key] for key in kept})
            self.assertNotEqual(new['sku_member_price_state'], 'NOT_REPARSED_ON_INITIAL_PAIR')
            self.assertNotEqual(new['product_discount_by_count_scope'], 'NOT_REPARSED_ON_INITIAL_PAIR')
        before = (self.root / self.initial_name / 'records.json').read_bytes()
        v3_before = (self.root / v3_name / 'records.json').read_bytes()
        with self.assertRaises(ResultPublishError) as raised:
            self.publish_v4()
        self.assertEqual(raised.exception.code, 'RESULT_TARGET_EXISTS')
        self.assertEqual((self.root / self.initial_name / 'records.json').read_bytes(), before)
        self.assertEqual((self.root / v3_name / 'records.json').read_bytes(), v3_before)

    def test_initial_rows_reject_duplicate_missing_and_extra_parses(self):
        def parsed(analysis):
            return parse_category_price(analysis)

        def copied(result, rows):
            return CategoryPriceParse(
                rows, result.currency_path_status, result.amount_unit_path_status,
                result.activity_price_path_status, result.price_desc_tag_path_status)

        def duplicate(analysis):
            result = parsed(analysis)
            return copied(result, (result.rows[0], result.rows[0]))

        def shortened(analysis):
            result = parsed(analysis)
            return copied(result, result.rows[:1])

        def replaced(analysis):
            result = parsed(analysis)
            return copied(result, (replace(result.rows[0], sku_id='999'), result.rows[1]))

        for wrapper in (duplicate, shortened, replaced):
            with self.subTest(wrapper=wrapper.__name__):
                with patch('collection_adapter.p29_store_inventory.parse_category_price', side_effect=wrapper):
                    with self.assertRaises(CategoryCandidateError) as raised:
                        initial_price_rules_inventory_view(self.root, self.observation, [self.name])
                self.assertEqual(raised.exception.code, 'P29_INVENTORY_INITIAL_ROW_MISMATCH')

    def test_cli_selects_initial_rules_without_changing_older_entries(self):
        stream = io.StringIO()
        with patch('sys.argv', ['inventory', '--output-root', str(self.root),
                                '--observation-name', self.observation, '--input-name', self.name,
                                '--result-name', self.initial_name, '--initial-price-rules']), \
                contextlib.redirect_stdout(stream):
            self.assertEqual(main(), 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload['code'], 'P29_STORE_INITIAL_PRICE_RULES_EXPORTED')
        self.assertNotIn('synthetic_rule_text', stream.getvalue())
        self.assertEqual(self.read(self.initial_name + '/records.json')['schema_version'],
                         'p29-store-input-inventory/v4')
        price_name = 'store_price_inventory_' + 'd' * 32
        stream = io.StringIO()
        with patch('sys.argv', ['inventory', '--output-root', str(self.root),
                                '--observation-name', self.observation, '--input-name', self.name,
                                '--result-name', price_name, '--price-evidence']), \
                contextlib.redirect_stdout(stream):
            self.assertEqual(main(), 0)
        self.assertEqual(self.read(price_name + '/records.json')['schema_version'], 'p29-store-input-inventory/v2')
        rules_name = 'store_price_rules_' + 'e' * 32
        stream = io.StringIO()
        with patch('sys.argv', ['inventory', '--output-root', str(self.root),
                                '--observation-name', self.observation, '--input-name', self.name,
                                '--result-name', rules_name, '--price-rules']), \
                contextlib.redirect_stdout(stream):
            self.assertEqual(main(), 0)
        self.assertEqual(self.read(rules_name + '/records.json')['schema_version'], 'p29-store-input-inventory/v3')
        for flags in (['--price-evidence', '--price-rules'],
                      ['--price-rules', '--initial-price-rules'],
                      ['--price-evidence', '--initial-price-rules']):
            stream = io.StringIO()
            with patch('sys.argv', ['inventory', '--output-root', str(self.root),
                                    '--observation-name', self.observation, '--input-name', self.name,
                                    *flags]), contextlib.redirect_stdout(stream):
                self.assertEqual(main(), 1)
            self.assertEqual(json.loads(stream.getvalue())['code'], 'P29_INVENTORY_ARGUMENTS_INVALID')


if __name__ == '__main__':
    unittest.main()
