import copy
import json
import unittest

from collection_adapter.p28_business_batch import analyze_public_body
from collection_adapter.tests.test_p28_business_batch import bodies
from parser_candidate import p31_public_fields as fields
from parser_candidate.p29_category_profile import CategoryCandidateError


def analysis(body):
    return analyze_public_body(json.dumps(body).encode())


def product_body():
    _, body = bodies()
    product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
    product.update(description='Synthetic 商品, "说明"', month_saled=0, stock=-1,
                   has_food=False, status_description='', forbid_single_buy=None)
    product['skus'][0].update(min_order_count=2, real_stock=-1)
    product['attrs'] = [{'name': 'Synthetic 口味', 'choose_n': 1,
                        'values': [{'id': 901, 'value': 'Synthetic 辣味', 'hidden': False},
                                   {'id': 902, 'value': 'Synthetic 原味'}]},
                       {'name': 'Synthetic 分量', 'values': [{'value': ''}]}]
    return body


class PublicFieldTests(unittest.TestCase):
    def test_own_description_and_sku_fields(self):
        rows = fields.parse_product_fields(analysis(product_body()))
        own = rows.get(('category_a', '101', '201'), {})
        self.assertEqual(own.get('product_description_text'), 'Synthetic 商品, "说明"')
        self.assertEqual(own['sku_min_order_count_number'], '2')
        self.assertIsNone(rows[('category_a', '101', '202')]['sku_min_order_count_number'])

    def test_missing_null_empty_zero_negative_boolean_are_distinct(self):
        own = fields.parse_product_fields(analysis(product_body()))['category_a', '101', '201']
        self.assertEqual((own['product_month_saled_number'], own['product_month_saled_number_state']), ('0', 'PRESENT_UNCONFIRMED'))
        self.assertEqual((own['product_stock_number'], own['product_stock_number_state']), ('-1', 'NEGATIVE_SEMANTICS_UNCONFIRMED'))
        self.assertEqual(own['product_forbid_single_buy_text_state'], 'SOURCE_NULL')
        self.assertEqual(own['product_status_description_text_state'], 'SOURCE_EMPTY')
        self.assertEqual(own['product_sku_label_text_state'], 'NOT_OBSERVED')
        self.assertIs(own['product_has_food_flag'], False)

    def test_attribute_indices_and_json_are_stable_when_projection_is_reordered(self):
        source = analysis(product_body())
        expected = fields.parse_product_fields(source)
        source['public_values'].reverse()
        self.assertEqual(fields.parse_product_fields(source), expected)
        attrs = expected['category_a', '101', '201']['product_attributes']
        self.assertEqual([a['attribute_index'] for a in attrs], [0, 1])
        self.assertEqual([v['value_index'] for v in attrs[0]['values']], [0, 1])
        self.assertEqual(attrs[0]['values'][0]['id'], '901')
        self.assertIs(attrs[0]['values'][0]['hidden'], False)
        self.assertEqual(attrs[1]['values'][0]['value_state'], 'SOURCE_EMPTY')
        self.assertEqual(json.loads(expected['category_a', '101', '201']['product_attributes_json']), attrs)

    def test_duplicates_malformed_coordinates_and_orphans_reject(self):
        source = analysis(product_body())
        target = next(x for x in source['public_values'] if x['path'].endswith('dynamic_spus[].description'))
        for change in ('duplicate', 'wrong_path', 'bool_index', 'orphan'):
            bad = copy.deepcopy(source)
            extra = copy.deepcopy(target)
            if change == 'wrong_path': extra['coordinates'][-1] = 'unrelated'
            if change == 'bool_index': extra['coordinates'][4] = True
            if change == 'orphan': extra['coordinates'][4] = 7999
            bad['public_values'].append(extra)
            with self.subTest(change=change), self.assertRaises(CategoryCandidateError):
                fields.parse_product_fields(bad)

    def test_invalid_selected_type_and_url_reject(self):
        for path, value in [('month_saled', True), ('description', 'https://synthetic.invalid'), ('stock', float('inf'))]:
            source = analysis(product_body())
            next(x for x in source['public_values'] if x['path'].endswith('dynamic_spus[].' + path))['value'] = value
            with self.subTest(path=path), self.assertRaises(CategoryCandidateError):
                fields.parse_product_fields(source)

    def test_store_is_separate_and_ignores_unrelated_fields(self):
        food, _ = bodies()
        food['data']['poi_info'].update(address='Synthetic 商店地址', shipping_fee=0,
                                        is_meituan_delivery=False, distance='PRIVATE_CONTEXT',
                                        favorite_desc='PRIVATE_CONTEXT')
        parsed = fields.parse_store_fields(analysis(food))
        self.assertEqual(parsed['store_address_text'], 'Synthetic 商店地址')
        self.assertEqual(parsed['store_shipping_fee_number'], '0')
        self.assertIs(parsed['store_is_meituan_delivery_flag'], False)
        self.assertNotIn('PRIVATE', json.dumps(parsed))
        self.assertNotIn('product_id', parsed)

    def test_oversized_numbers_and_malformed_paths_use_fixed_error(self):
        food, _ = bodies()
        food['data']['poi_info']['shipping_fee'] = 1
        source = analysis(food)
        number = copy.deepcopy(source)
        next(x for x in number['public_values'] if x['path'].endswith('.shipping_fee'))['value'] = 10 ** 400
        malformed = copy.deepcopy(source)
        malformed['public_values'][0]['path'] = []
        for bad in (number, malformed):
            with self.assertRaises(CategoryCandidateError) as raised:
                fields.parse_store_fields(bad)
            self.assertEqual(raised.exception.code, 'P31_FIELD_INPUT_INVALID')
