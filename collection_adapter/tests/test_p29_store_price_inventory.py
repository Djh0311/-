import json
import unittest

from collection_adapter.p29_store_inventory import publish_store_price_inventory
from collection_adapter.tests.test_p29_category_review import synthetic_body
from collection_adapter.tests.test_p29_store_inventory import StoreInventoryTests
from parser_candidate.p29_category_price import CURRENCY_NOT_PROVIDED


class StorePriceInventoryTests(StoreInventoryTests):
    def test_category_rows_keep_own_price_evidence_and_initial_currency_stays_scoped(self):
        body = synthetic_body()
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['skus'][0]['member_price'] = 1.05
        product['skus'][0]['box_price'] = 0
        self.input('a', 'c', '2026-01-01T00:01:00+00:00', body)
        result_name = 'store_price_inventory_' + 'e' * 32
        result = publish_store_price_inventory(self.root, self.observation, [self.name], result_name)
        view = self.read(result_name + '/records.json')
        self.assertEqual(result['live_attempts_consumed'], 0)
        self.assertFalse(view['currency_inferred'])
        self.assertFalse(view['category_currency_borrowed_from_initial_pair'])
        self.assertEqual(view['schema_version'], 'p29-store-input-inventory/v2')
        initial = [row for row in view['records'] if row['source_kind'] == 'CHECKED_INITIAL_PAIR']
        category = [row for row in view['records'] if row['source_kind'] == 'PARTIAL_CATEGORY_CANDIDATE']
        self.assertEqual((len(initial), len(category)), (2, 2))
        self.assertTrue(all(row['currency'] == 'CNY' and row['amount_unit'] == 'YUAN'
                            and row['currency_basis'] == 'INITIAL_PAIR_PAGE_CONFIRMATION'
                            and row['sku_member_price_state'] == 'NOT_REPARSED_ON_INITIAL_PAIR'
                            for row in initial))
        own = next(row for row in category if row['sku_id'] == '201')
        other = next(row for row in category if row['sku_id'] == '202')
        self.assertEqual(own['sku_member_price_number'], '1.05')
        self.assertEqual(own['sku_box_price_number'], '0')
        self.assertIsNone(other['sku_member_price_number'])
        self.assertEqual(other['sku_member_price_state'], 'NOT_OBSERVED')
        self.assertTrue(all(row['currency'] is None and row['amount_unit'] is None
                            and row['currency_status'] == CURRENCY_NOT_PROVIDED
                            and row['currency_basis'] == 'NOT_BORROWED_FROM_INITIAL_PAIR'
                            for row in category))
        self.assertNotIn('"currency": "CNY"', json.dumps(
            [row for row in view['records'] if row['source_kind'] != 'CHECKED_INITIAL_PAIR']))

    def test_newer_category_row_replaces_initial_without_keeping_cny(self):
        body = synthetic_body()
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        body['data']['food_spu_tags'][0]['tag'] = 'category_a'
        product['skus'] = [product['skus'][0]]
        product['min_price'] = product['render_info']['price_info']['min_price'] = 9
        product['skus'][0]['price'] = 9
        product['skus'][0]['member_price'] = 7
        name = self.input('f', '9', '2026-01-01T00:03:00+00:00', body)
        result_name = 'store_price_inventory_' + 'a' * 32
        publish_store_price_inventory(self.root, self.observation, [name], result_name)
        view = self.read(result_name + '/records.json')
        rows = {row['sku_id']: row for row in view['records'] if row['category_ref'] == 'category_a'}
        self.assertEqual(rows['201']['source_kind'], 'PARTIAL_CATEGORY_CANDIDATE')
        self.assertIsNone(rows['201']['currency'])
        self.assertEqual(rows['201']['sku_price_number'], '9')
        self.assertEqual(rows['201']['sku_member_price_number'], '7')
        self.assertEqual(rows['202']['source_kind'], 'CHECKED_INITIAL_PAIR')
        self.assertEqual(rows['202']['currency'], 'CNY')
        self.assertEqual(rows['202']['sku_member_price_state'], 'NOT_REPARSED_ON_INITIAL_PAIR')


if __name__ == '__main__':
    unittest.main()
