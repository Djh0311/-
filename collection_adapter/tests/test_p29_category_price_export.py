import csv
import json
from pathlib import Path
import stat
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from collection_adapter.p29_category_export import (
    CSV_PRICE_FIELDS, main, price_view, publish_category_candidates, publish_category_price,
)
from collection_adapter.tests.test_p29_category_export import CategoryExportTests
from collection_core.result_publisher import ResultPublishError, _manifest_from_views
from parser_candidate.p29_category_price import CURRENCY_NOT_PROVIDED
from parser_candidate.p29_category_profile import CategoryCandidateError
from parser_candidate.tests.test_p29_category_price import price_body


class CategoryPriceExportTests(CategoryExportTests):
    def test_equal_time_optional_price_conflict_is_rejected(self):
        body = price_body()
        body['data']['food_spu_tags'][0]['dynamic_spus'][0]['skus'][0]['member_price'] = 2.05
        other = self.input('f', '9', '2026-01-01T00:01:00+00:00', body)
        for names in ([self.name, other], [other, self.name]):
            with self.subTest(order=names):
                with self.assertRaises(CategoryCandidateError) as raised:
                    price_view(self.root, names)
                self.assertEqual(raised.exception.code, 'P29_CATEGORY_BATCH_ORDER_AMBIGUOUS')

    def test_equal_time_identical_price_evidence_can_deduplicate(self):
        other = self.input('f', '9', '2026-01-01T00:01:00+00:00', price_body())
        view, _, _ = price_view(self.root, [self.name, other])
        self.assertEqual(view['record_count'], 2)
        self.assertEqual(view['deduplicated_candidate_rows'], 2)

    def setUp(self):
        super().setUp()
        self.price_name = 'category_price_' + 'e' * 32
        self.input('a', 'c', '2026-01-01T00:01:00+00:00', price_body())

    def schema(self, name):
        root = Path(__file__).resolve().parents[2] / 'contracts/schemas'
        resources = {path.name: Resource.from_contents(json.loads(path.read_text()))
                     for path in root.glob('*.schema.json')}
        registry = Registry().with_resources(resources.items())
        return Draft202012Validator(json.loads((root / name).read_text()),
            registry=registry, format_checker=FormatChecker())

    def test_price_export_keeps_own_numbers_and_refuses_currency_promotion(self):
        result = publish_category_price(self.root, [self.name], self.price_name)
        view = self.read(self.price_name + '/records.json')
        rows = {row['sku_id']: row for row in view['records']}
        self.assertEqual(result['record_count'], 2)
        self.assertEqual(rows['201']['sku_member_price_number'], '1.05')
        self.assertEqual(rows['202']['sku_member_price_state'], 'NOT_OBSERVED')
        self.assertEqual(rows['201']['sku_box_price_number'], '0')
        self.assertEqual(rows['202']['sku_box_price_number'], '0.5')
        self.assertTrue(all(row['currency_status'] == row['amount_unit_status'] == CURRENCY_NOT_PROVIDED
                            for row in rows.values()))
        self.assertNotIn('CNY', json.dumps(view))
        self.assertNotIn('YUAN', json.dumps(view))
        self.assertFalse(view['can_publish_complete_result'])
        self.assertFalse(view['currency_inferred'])
        self.assertFalse(view['initial_pair_currency_borrowed'])
        self.assertEqual(view['schema_version'], 'p29-category-candidate-result/v2')
        validator = self.schema('p29-category-candidate-result-v2.schema.json')
        self.assertTrue(validator.is_valid(view))
        changed = json.loads(json.dumps(view))
        changed['records'][0]['currency_status'] = 'CNY'
        self.assertFalse(validator.is_valid(changed))
        destination = self.root / self.price_name
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in destination.iterdir()))
        with (destination / 'records.csv').open(newline='') as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(tuple(reader.fieldnames), CSV_PRICE_FIELDS)
        manifest = self.read(self.price_name + '/manifest.json')
        self.assertTrue(self.schema('p29-category-candidate-manifest-v2.schema.json').is_valid(manifest))
        with self.assertRaises(ResultPublishError):
            _manifest_from_views(view, 'complete_result')

    def test_later_response_does_not_keep_an_unrepeated_price_component(self):
        body = price_body()
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['skus'] = [product['skus'][0]]
        product['skus'][0].pop('member_price')
        product['min_price'] = product['render_info']['price_info']['min_price'] = 4
        product['skus'][0]['price'] = 4
        later = self.input('f', '9', '2026-01-01T00:02:00+00:00', body)
        publish_category_price(self.root, [self.name, later], self.price_name)
        view = self.read(self.price_name + '/records.json')
        current = next(row for row in view['records'] if row['sku_id'] == '201')
        previous = next(row for row in view['records'] if row['sku_id'] == '202')
        self.assertEqual(current['source_file'], later)
        self.assertEqual(current['sku_member_price_state'], 'NOT_OBSERVED')
        self.assertEqual(current['sku_price_number'], '4')
        self.assertEqual(previous['sku_price_number'], '2.75')
        self.assertEqual(previous['source_file'], self.name)

    def test_v1_candidate_export_still_rejects_promoted_currency(self):
        result = publish_category_candidates(self.root, [self.name], self.result_name)
        view = self.read(result['result_name'] + '/records.json')
        self.assertEqual(view['schema_version'], 'p29-category-candidate-result/v1')
        self.assertTrue(all(row['currency'] == 'UNKNOWN' and row['amount_unit'] == 'UNKNOWN' for row in view['records']))
        self.assertFalse(view['can_publish_complete_result'])


if __name__ == '__main__':
    unittest.main()
