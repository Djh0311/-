import contextlib
import csv
import io
import json
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from collection_adapter.p29_category_export import (
    CSV_PRICE_FIELDS, CSV_PRICE_RULE_FIELDS, main, price_view, publish_category_candidates,
    publish_category_price, publish_category_price_rules,
)
from collection_adapter.tests.test_p29_category_export import CategoryExportTests
from collection_core.result_publisher import ResultPublishError, _manifest_from_views
from parser_candidate.p29_category_price import NEGATIVE_NOT_ADAPTED, PRESENT_UNCONFIRMED
from parser_candidate.p29_category_profile import CategoryCandidateError
from parser_candidate.p29_price_rules import CLOSED_MARK_NOT_PROMOTED
from parser_candidate.tests.test_p29_price_rules import rules_body


class PriceRuleExportTests(CategoryExportTests):
    def setUp(self):
        super().setUp()
        self.rules_name = 'category_price_rules_' + 'e' * 32
        self.input('a', 'c', '2026-01-01T00:01:00+00:00', rules_body())

    def schema(self, name):
        root = Path(__file__).resolve().parents[2] / 'contracts/schemas'
        resources = {path.name: Resource.from_contents(json.loads(path.read_text()))
                     for path in root.glob('*.schema.json')}
        return Draft202012Validator(json.loads((root / name).read_text()),
            registry=Registry().with_resources(resources.items()), format_checker=FormatChecker())

    def test_equal_time_rule_difference_is_ambiguous_and_v2_stays_on_price_rows(self):
        body = rules_body()
        body['data']['food_spu_tags'][0]['dynamic_spus'][0]['skus'][0]['activity_policy']['discount_by_count']['discount'] = 8
        other = self.input('f', '9', '2026-01-01T00:01:00+00:00', body)
        kept, _, _ = price_view(self.root, [self.name, other])
        self.assertEqual(kept['schema_version'], 'p29-category-candidate-result/v2')
        self.assertEqual(kept['record_count'], 2)
        self.assertNotIn('product_discount_by_count_count_number', kept['records'][0])
        for names in ([self.name, other], [other, self.name]):
            with self.subTest(order=names):
                with self.assertRaises(CategoryCandidateError) as raised:
                    price_view(self.root, names, include_rules=True)
                self.assertEqual(raised.exception.code, 'P29_CATEGORY_BATCH_ORDER_AMBIGUOUS')

    def test_equal_time_identical_rules_can_deduplicate(self):
        other = self.input('f', '9', '2026-01-01T00:01:00+00:00', rules_body())
        view, _, _ = price_view(self.root, [self.name, other], include_rules=True)
        self.assertEqual(view['record_count'], 2)
        self.assertEqual(view['deduplicated_candidate_rows'], 2)
        self.assertFalse(view['cross_observation_rule_fields_copied'])

    def test_rules_export_keeps_product_sku_nulls_and_indexed_text(self):
        result = publish_category_price_rules(self.root, [self.name], self.rules_name)
        view = self.read(self.rules_name + '/records.json')
        rows = {row['sku_id']: row for row in view['records']}
        first, second = rows['201'], rows['202']
        self.assertEqual(result['code'], 'P29_CATEGORY_PRICE_RULES_EXPORTED')
        self.assertEqual(view['schema_version'], 'p29-category-candidate-result/v3')
        self.assertEqual(first['sku_price_number'], '1.25')
        self.assertEqual(first['product_discount_by_count_scope'], 'PRODUCT')
        self.assertEqual(first['sku_discount_by_count_scope'], 'SKU')
        self.assertEqual((first['product_discount_by_count_count_number'],
                          first['product_discount_by_count_discount_number']), ('0', '2'))
        self.assertEqual(first['product_discount_by_count_count_state'], PRESENT_UNCONFIRMED)
        self.assertEqual((first['sku_discount_by_count_count_number'],
                          first['sku_discount_by_count_discount_number']), ('0', '3'))
        self.assertEqual(second['product_discount_by_count_discount_number'], '2')
        self.assertEqual(second['sku_discount_by_count_pair_state'], 'COUNT_KEY_NOT_OBSERVED')
        self.assertIsNone(second['sku_discount_by_count_count_number'])
        self.assertEqual(second['sku_discount_by_count_discount_number'], '4')
        self.assertEqual(first['sku_ladder_package_pair_state'], 'BOTH_KEYS_PRESENT')
        self.assertEqual((first['sku_ladder_package_food_num_number'],
                          first['sku_ladder_package_price_number']), ('2', '0'))
        self.assertEqual(first['sku_ladder_package_price_state'], PRESENT_UNCONFIRMED)
        self.assertEqual(second['sku_ladder_package_pair_state'], 'BOTH_KEYS_NOT_OBSERVED')
        self.assertIsNone(first['product_multi_activity_price_number'])
        self.assertEqual(first['product_multi_activity_price_state'], NEGATIVE_NOT_ADAPTED)
        self.assertEqual(first['product_show_origin_price_state'], NEGATIVE_NOT_ADAPTED)
        self.assertEqual(first['product_discount_tag_text'], 'synthetic_rule_text')
        texts = first['sku_full_discount_tag_texts']
        self.assertEqual([(item['tag_index'], item['sub_tag_index'], item['text']) for item in texts],
                         [(0, 0, 'synthetic_rule_a'), (0, 1, 'synthetic_rule_b'), (1, 0, 'synthetic_rule_c')])
        self.assertNotIn('synthetic_rule_text', [item['text'] for item in texts])
        self.assertIsNone(second['sku_full_discount_tag_texts'])
        self.assertIsNone(second['sku_full_discount_tag_texts_json'])
        self.assertEqual(second['sku_full_discount_tag_texts_state'], 'NOT_OBSERVED')
        canonical = json.dumps(texts, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
        self.assertEqual(first['sku_full_discount_tag_texts_json'], canonical)
        rendered = json.dumps(view)
        for display in ('synthetic_border', 'synthetic_color', 'synthetic_icon', 'synthetic_ladder_color', 'font_size', 'fontSize'):
            self.assertNotIn(display, rendered)
        self.assertNotIn('synthetic_rule_a synthetic_rule_b', rendered)
        for flag in ('count_zero_means_no_threshold', 'discount_number_proves_algorithm',
                     'zero_amount_means_free', 'negative_adapted_as_amount',
                     'display_only_fields_passed_through', 'nested_rules_concatenated',
                     'currency_inferred', 'can_publish_complete_result',
                     'cross_observation_rule_fields_copied'):
            self.assertIs(view[flag], False)
        self.assertTrue(self.schema('p29-category-candidate-result-v3.schema.json').is_valid(view))
        destination = self.root / self.rules_name
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in destination.iterdir()))
        with (destination / 'records.csv').open(newline='') as stream:
            reader = csv.DictReader(stream)
            csv_rows = list(reader)
            self.assertEqual(tuple(reader.fieldnames), CSV_PRICE_RULE_FIELDS)
        by_sku = {row['sku_id']: row for row in csv_rows}
        self.assertEqual(json.loads(by_sku['201']['sku_full_discount_tag_texts_json']), texts)
        self.assertEqual(by_sku['202']['sku_full_discount_tag_texts_json'], '')
        manifest = self.read(self.rules_name + '/manifest.json')
        self.assertTrue(self.schema('p29-category-candidate-manifest-v3.schema.json').is_valid(manifest))
        self.assertNotIn('records', manifest)
        with self.assertRaises(ResultPublishError):
            _manifest_from_views(view, 'complete_result')
        changed = json.loads(json.dumps(view))
        changed['records'][0]['product_multi_activity_price_number'] = '1'
        self.assertFalse(self.schema('p29-category-candidate-result-v3.schema.json').is_valid(changed))
        styled = json.loads(json.dumps(view))
        styled['records'][0]['sku_full_discount_tag_texts'][0]['color'] = 'synthetic_color'
        self.assertFalse(self.schema('p29-category-candidate-result-v3.schema.json').is_valid(styled))

    def test_null_negative_and_missing_pair_keys_stay_distinct(self):
        body = rules_body()
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['activity_policy']['discount_by_count']['count'] = None
        product['activity_policy']['discount_by_count']['discount'] = -5
        product['render_info']['sup_info']['discountTag'] = '元'
        product['skus'][0]['sku_ladder_box_info'].pop('ladder_package_price')
        name = self.input('b', 'd', '2026-01-01T00:04:00+00:00', body)
        publish_category_price_rules(self.root, [name], 'category_price_rules_' + 'b' * 32)
        row = next(item for item in self.read('category_price_rules_' + 'b' * 32 + '/records.json')['records']
                   if item['sku_id'] == '201')
        self.assertEqual(row['product_discount_by_count_pair_state'], 'BOTH_KEYS_PRESENT')
        self.assertEqual(row['product_discount_by_count_count_state'], 'SOURCE_NULL')
        self.assertIsNone(row['product_discount_by_count_count_number'])
        self.assertEqual(row['product_discount_by_count_discount_state'], NEGATIVE_NOT_ADAPTED)
        self.assertIsNone(row['product_discount_by_count_discount_number'])
        self.assertEqual(row['product_discount_tag_text_state'], CLOSED_MARK_NOT_PROMOTED)
        self.assertEqual(row['sku_ladder_package_pair_state'], 'PRICE_KEY_NOT_OBSERVED')
        self.assertEqual(row['sku_ladder_package_food_num_number'], '2')
        self.assertIsNone(row['sku_ladder_package_price_number'])

    def test_later_response_replaces_the_whole_rule_row(self):
        body = rules_body()
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['activity_policy']['discount_by_count']['discount'] = 9
        product.pop('max_discount')
        sku = product['skus'][0]
        sku.pop('sku_ladder_box_info')
        sku.pop('full_discount_tag')
        sku['activity_policy']['discount_by_count']['discount'] = 8
        product['skus'] = [sku]
        later = self.input('f', '9', '2026-01-01T00:02:00+00:00', body)
        publish_category_price_rules(self.root, [self.name, later], self.rules_name)
        rows = {row['sku_id']: row for row in self.read(self.rules_name + '/records.json')['records']}
        self.assertEqual(rows['201']['source_file'], later)
        self.assertEqual(rows['201']['product_discount_by_count_discount_number'], '9')
        self.assertEqual(rows['201']['sku_discount_by_count_discount_number'], '8')
        self.assertEqual(rows['201']['product_max_discount_state'], 'NOT_OBSERVED')
        self.assertIsNone(rows['201']['product_max_discount_number'])
        self.assertEqual(rows['201']['sku_ladder_package_pair_state'], 'BOTH_KEYS_NOT_OBSERVED')
        self.assertEqual(rows['201']['sku_full_discount_tag_texts_state'], 'NOT_OBSERVED')
        self.assertEqual(rows['202']['source_file'], self.name)
        self.assertEqual(rows['202']['product_discount_by_count_discount_number'], '2')
        self.assertEqual(rows['202']['product_max_discount_number'], '0')

    def test_short_rule_coordinate_stays_fixed_candidate_error(self):
        document = self.read(self.name)
        selected = next(value for value in document['public_analysis']['public_values']
                        if value['path'] == '$.data.food_spu_tags[].dynamic_spus[].max_discount')
        selected['coordinates'] = ['data', 'food_spu_tags', 0, 'dynamic_spus']
        self.write(self.name, document)
        with self.assertRaises(CategoryCandidateError) as raised:
            price_view(self.root, [self.name], include_rules=True)
        self.assertEqual(raised.exception.code, 'P29_CATEGORY_CANDIDATE_INVALID')

    def test_v1_and_v2_contracts_do_not_gain_rule_columns(self):
        v1 = publish_category_candidates(self.root, [self.name], self.result_name)
        v2_name = 'category_price_' + 'a' * 32
        publish_category_price(self.root, [self.name], v2_name)
        v1_view = self.read(v1['result_name'] + '/records.json')
        v2_view = self.read(v2_name + '/records.json')
        self.assertEqual(v1_view['schema_version'], 'p29-category-candidate-result/v1')
        self.assertEqual(v2_view['schema_version'], 'p29-category-candidate-result/v2')
        self.assertNotIn('sku_full_discount_tag_texts', v1_view['records'][0])
        self.assertNotIn('sku_full_discount_tag_texts', v2_view['records'][0])
        self.assertTrue(self.schema('p29-category-candidate-result-v2.schema.json').is_valid(v2_view))
        changed = json.loads(json.dumps(v2_view))
        changed['records'][0]['product_discount_by_count_count_number'] = '0'
        self.assertFalse(self.schema('p29-category-candidate-result-v2.schema.json').is_valid(changed))
        with (self.root / v2_name / 'records.csv').open(newline='') as stream:
            self.assertEqual(tuple(csv.DictReader(stream).fieldnames), CSV_PRICE_FIELDS)

    def test_republish_does_not_overwrite_rule_output(self):
        publish_category_price_rules(self.root, [self.name], self.rules_name)
        before = (self.root / self.rules_name / 'records.json').read_bytes()
        with self.assertRaises(ResultPublishError):
            publish_category_price_rules(self.root, [self.name], self.rules_name)
        self.assertEqual((self.root / self.rules_name / 'records.json').read_bytes(), before)

    def test_cli_selects_rules_without_changing_price_evidence(self):
        stream = io.StringIO()
        with patch('sys.argv', ['export', '--output-root', str(self.root), '--input-name', self.name,
                                '--result-name', self.rules_name, '--price-rules']), contextlib.redirect_stdout(stream):
            self.assertEqual(main(), 0)
        self.assertEqual(json.loads(stream.getvalue())['code'], 'P29_CATEGORY_PRICE_RULES_EXPORTED')
        self.assertNotIn('synthetic_rule_text', stream.getvalue())
        price_name = 'category_price_' + 'c' * 32
        stream = io.StringIO()
        with patch('sys.argv', ['export', '--output-root', str(self.root), '--input-name', self.name,
                                '--result-name', price_name, '--price-evidence']), contextlib.redirect_stdout(stream):
            self.assertEqual(main(), 0)
        self.assertEqual(self.read(price_name + '/records.json')['schema_version'], 'p29-category-candidate-result/v2')
        stream = io.StringIO()
        with patch('sys.argv', ['export', '--output-root', str(self.root), '--input-name', self.name,
                                '--price-evidence', '--price-rules']), contextlib.redirect_stdout(stream):
            self.assertEqual(main(), 1)
        self.assertEqual(json.loads(stream.getvalue())['code'], 'P29_CATEGORY_ARGUMENTS_INVALID')


if __name__ == '__main__':
    unittest.main()
