import json
import unittest

from collection_adapter.p28_business_batch import analyze_public_body
from collection_adapter.tests.test_p29_category_review import synthetic_body
from parser_candidate.p29_category_profile import CategoryCandidateError
from parser_candidate.p29_category_price import (
    CLOSED_MARK_NOT_PROMOTED, CURRENCY_NOT_PROVIDED, NEGATIVE_NOT_ADAPTED,
    PATH_PRESENT_NOT_ADAPTED, PRESENT_TEXT_NOT_CURRENCY, PRESENT_UNCONFIRMED,
    PRODUCT_MEASURE_NOT_AMOUNT_UNIT, parse_category_price,
)


def price_body():
    body = synthetic_body()
    product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
    product['full_discount_price'] = 1.1
    product['render_info']['price_info'].update(origin_price=3, min_price_tail='synthetic_tail', price_desc='')
    product['skus'][0].update(member_price=1.05, full_discount_price=1.1, box_price=0, price_desc='')
    product['skus'][1]['box_price'] = 0.5
    product['preferential_feeling_price'] = 8
    return body


def parsed(body=None):
    return parse_category_price(analyze_public_body(json.dumps(body or price_body()).encode()))


class CategoryPriceTests(unittest.TestCase):
    def test_short_optional_coordinates_return_fixed_error(self):
        analysis = analyze_public_body(json.dumps(price_body()).encode())
        for value in analysis['public_values']:
            if value['path'] == '$.data.food_spu_tags[].dynamic_spus[].full_discount_price':
                value['coordinates'] = ['data', 'food_spu_tags', 0, 'dynamic_spus']
        with self.assertRaises(CategoryCandidateError) as raised:
            parse_category_price(analysis)
        self.assertEqual(raised.exception.code, 'P29_CATEGORY_CANDIDATE_INVALID')

    def test_same_object_numbers_keep_source_and_do_not_invent_currency(self):
        result = parsed()
        rows = {row.sku_id: row for row in result.rows}
        self.assertEqual(set(rows), {'201', '202'})
        first, second = rows['201'], rows['202']
        self.assertEqual((first.sku_price_number, first.product_min_price_number, first.render_min_price_number),
                         ('1.25', '1.25', '1.25'))
        self.assertEqual(first.sku_member_price_number, '1.05')
        self.assertEqual(first.sku_member_price_state, PRESENT_UNCONFIRMED)
        self.assertIsNone(second.sku_member_price_number)
        self.assertEqual(second.sku_member_price_state, 'NOT_OBSERVED')
        self.assertEqual((first.sku_box_price_number, second.sku_box_price_number), ('0', '0.5'))
        self.assertEqual(first.render_origin_number, second.render_origin_number)
        self.assertEqual(first.render_origin_state, PRESENT_UNCONFIRMED)
        self.assertEqual(first.product_full_discount_price_number, '1.1')
        self.assertEqual(first.sku_full_discount_price_state, PRESENT_UNCONFIRMED)
        self.assertEqual(second.sku_full_discount_price_state, 'NOT_OBSERVED')
        self.assertFalse(hasattr(first, 'preferential_feeling_price_number'))
        self.assertEqual(first.currency_status, CURRENCY_NOT_PROVIDED)
        self.assertEqual(first.amount_unit_status, CURRENCY_NOT_PROVIDED)
        self.assertEqual(result.currency_path_status, CURRENCY_NOT_PROVIDED)
        self.assertEqual(result.amount_unit_path_status, CURRENCY_NOT_PROVIDED)
        self.assertTrue(all(value not in ('CNY', 'YUAN') for row in rows.values() for value in row.__dict__.values()))
        self.assertEqual(first.product_unit_role, PRODUCT_MEASURE_NOT_AMOUNT_UNIT)
        self.assertEqual(first.min_price_tail_state, PRESENT_TEXT_NOT_CURRENCY)
        self.assertEqual(first.sku_price_desc_state, 'SOURCE_EMPTY')
        self.assertEqual(first.render_price_desc_state, 'SOURCE_EMPTY')
        self.assertEqual(first.numeric_min_relation, 'EQUAL_PRODUCT_RENDER_AND_MIN_SKU')
        self.assertFalse(first.numeric_relation_proves_currency)
        self.assertFalse(first.numeric_relation_proves_amount_unit)
        self.assertEqual(result.activity_price_path_status, CURRENCY_NOT_PROVIDED)
        self.assertEqual(result.price_desc_tag_path_status, CURRENCY_NOT_PROVIDED)

    def test_currency_path_and_closed_mark_are_not_promoted(self):
        body = price_body()
        body['data']['currency'] = 'CNY'
        body['data']['food_spu_tags'][0]['dynamic_spus'][0]['unit'] = '元'
        body['data']['food_spu_tags'][0]['dynamic_spus'][0]['render_info']['price_info']['min_price_tail'] = '元'
        result = parsed(body)
        row = next(item for item in result.rows if item.sku_id == '201')
        self.assertEqual(result.currency_path_status, PATH_PRESENT_NOT_ADAPTED)
        self.assertEqual(row.currency_status, PATH_PRESENT_NOT_ADAPTED)
        self.assertEqual(row.amount_unit_status, CURRENCY_NOT_PROVIDED)
        self.assertEqual(row.product_unit_role, CLOSED_MARK_NOT_PROMOTED)
        self.assertEqual(row.min_price_tail_state, CLOSED_MARK_NOT_PROMOTED)
        self.assertNotIn('CNY', row.__dict__.values())
        self.assertNotIn('YUAN', row.__dict__.values())

    def test_negative_component_is_not_adapted_as_an_amount(self):
        body = price_body()
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['skus'][0]['member_price'] = -1
        product['full_discount_price'] = -1
        product['skus'][1]['full_discount_price'] = 1.4
        result = parsed(body)
        rows = {row.sku_id: row for row in result.rows}
        self.assertEqual(rows['201'].sku_member_price_state, NEGATIVE_NOT_ADAPTED)
        self.assertIsNone(rows['201'].sku_member_price_number)
        self.assertEqual(rows['201'].product_full_discount_price_state, NEGATIVE_NOT_ADAPTED)
        self.assertEqual(rows['202'].sku_full_discount_price_number, '1.4')
        self.assertEqual(rows['202'].sku_box_price_number, '0.5')
        self.assertEqual(rows['201'].currency_status, CURRENCY_NOT_PROVIDED)

    def test_unequal_minimum_does_not_become_a_unit(self):
        body = price_body()
        body['data']['food_spu_tags'][0]['dynamic_spus'][0]['render_info']['price_info']['min_price'] = 9
        result = parsed(body)
        self.assertTrue(all(row.numeric_min_relation == 'NOT_EQUAL' for row in result.rows))
        self.assertTrue(all(row.currency_status == CURRENCY_NOT_PROVIDED for row in result.rows))

    def test_one_response_does_not_receive_another_response_argument(self):
        earlier = parsed()
        body = price_body()
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['skus'][0].pop('member_price')
        product['min_price'] = product['render_info']['price_info']['min_price'] = 4
        product['skus'][0]['price'] = 4
        later = parsed(body)
        self.assertEqual(earlier.rows[0].sku_member_price_number, '1.05')
        self.assertEqual(next(row for row in later.rows if row.sku_id == '201').sku_member_price_state, 'NOT_OBSERVED')
        self.assertEqual(next(row for row in later.rows if row.sku_id == '201').sku_price_number, '4')
