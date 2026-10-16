import json
import unittest

from collection_adapter.p28_business_batch import analyze_public_body
from parser_candidate.p29_category_profile import CategoryCandidateError
from parser_candidate.p29_category_price import (
    CLOSED_MARK_NOT_PROMOTED, NEGATIVE_NOT_ADAPTED, PRESENT_UNCONFIRMED,
)
from parser_candidate.p29_price_rules import PARSED_RULE_PATHS, parse_price_rules
from parser_candidate.tests.test_p29_category_price import price_body


def rules_body():
    body = price_body()
    product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
    product['activity_policy'] = {'discount_by_count': {'count': 0, 'discount': 2}}
    product['max_discount'] = 0
    product['preferential_feeling_price'] = 4
    product['render_info']['price_info'].update(
        coupon_count=0, coupons_per_price=0, multi_activity_price=-1, show_origin_price=-2)
    product['render_info']['sup_info'] = {
        'discountTag': 'synthetic_rule_text', 'border_color': 'synthetic_border', 'font_size': 12,
    }
    product['skus'][0]['activity_policy'] = {'discount_by_count': {'count': 0, 'discount': 3}}
    product['skus'][0]['sku_ladder_box_info'] = {
        'ladder_package_food_num': 2, 'ladder_package_price': 0, 'ladder_color': 'synthetic_ladder_color',
    }
    product['skus'][0]['full_discount_tag'] = [
        {'sub_tags': [
            {'text': 'synthetic_rule_a', 'color': 'synthetic_color', 'icon': 'synthetic_icon'},
            {'text': 'synthetic_rule_b'},
        ]},
        {'sub_tags': [{'text': 'synthetic_rule_c', 'fontSize': 11}]},
    ]
    product['skus'][1]['activity_policy'] = {'discount_by_count': {'discount': 4}}
    return body


def parsed(body=None):
    return parse_price_rules(analyze_public_body(json.dumps(body or rules_body()).encode()))


class PriceRuleTests(unittest.TestCase):
    def test_whitelist_is_the_observed_rule_paths_only(self):
        self.assertEqual(PARSED_RULE_PATHS, (
            '$.data.food_spu_tags[].dynamic_spus[].activity_policy.discount_by_count.count',
            '$.data.food_spu_tags[].dynamic_spus[].activity_policy.discount_by_count.discount',
            '$.data.food_spu_tags[].dynamic_spus[].max_discount',
            '$.data.food_spu_tags[].dynamic_spus[].preferential_feeling_price',
            '$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.coupon_count',
            '$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.coupons_per_price',
            '$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.multi_activity_price',
            '$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.show_origin_price',
            '$.data.food_spu_tags[].dynamic_spus[].render_info.sup_info.discountTag',
            '$.data.food_spu_tags[].dynamic_spus[].skus[].activity_policy.discount_by_count.count',
            '$.data.food_spu_tags[].dynamic_spus[].skus[].activity_policy.discount_by_count.discount',
            '$.data.food_spu_tags[].dynamic_spus[].skus[].full_discount_tag[].sub_tags[].text',
            '$.data.food_spu_tags[].dynamic_spus[].skus[].sku_ladder_box_info.ladder_package_food_num',
            '$.data.food_spu_tags[].dynamic_spus[].skus[].sku_ladder_box_info.ladder_package_price',
        ))

    def test_product_and_sku_rules_stay_separate(self):
        result = parsed()
        rows = {row.sku_id: row for row in result.rows}
        first, second = rows['201'], rows['202']
        self.assertEqual(first.product_discount_by_count.scope, 'PRODUCT')
        self.assertEqual(first.sku_discount_by_count.scope, 'SKU')
        self.assertEqual((first.product_discount_by_count.count_number,
                          first.product_discount_by_count.discount_number), ('0', '2'))
        self.assertEqual((first.sku_discount_by_count.count_number,
                          first.sku_discount_by_count.discount_number), ('0', '3'))
        self.assertEqual(second.product_discount_by_count.discount_number, '2')
        self.assertEqual(second.sku_discount_by_count.pair_state, 'COUNT_KEY_NOT_OBSERVED')
        self.assertEqual(second.sku_discount_by_count.count_state, 'NOT_OBSERVED')
        self.assertIsNone(second.sku_discount_by_count.count_number)
        self.assertEqual(second.sku_discount_by_count.discount_number, '4')
        self.assertEqual(second.sku_ladder_package.pair_state, 'BOTH_KEYS_NOT_OBSERVED')
        self.assertEqual(first.sku_ladder_package.food_num_number, '2')
        self.assertEqual(first.sku_ladder_package.price_number, '0')
        self.assertEqual(first.sku_full_discount_tag_texts_state, 'PRESENT_INDEXED_GROUP')
        self.assertEqual([(item.tag_index, item.sub_tag_index, item.text)
                          for item in first.sku_full_discount_tag_texts],
                         [(0, 0, 'synthetic_rule_a'), (0, 1, 'synthetic_rule_b'),
                          (1, 0, 'synthetic_rule_c')])
        self.assertEqual(second.sku_full_discount_tag_texts_state, 'NOT_OBSERVED')
        self.assertEqual(second.sku_full_discount_tag_texts, ())
        self.assertEqual(first.product_discount_tag_text, 'synthetic_rule_text')
        rendered = json.dumps([row.__dict__ for row in result.rows], default=lambda item: item.__dict__)
        for display in ('synthetic_border', 'synthetic_color', 'synthetic_icon', 'synthetic_ladder_color'):
            self.assertNotIn(display, rendered)
        self.assertNotIn('synthetic_rule_a synthetic_rule_b', rendered)
        self.assertFalse(hasattr(first, 'coupon_pair_state'))
        self.assertFalse(result.display_only_fields_passed_through)
        self.assertFalse(result.nested_rules_concatenated)

    def test_negative_zero_and_null_do_not_invent_semantics(self):
        result = parsed()
        row = next(item for item in result.rows if item.sku_id == '201')
        self.assertEqual(row.product_max_discount_number, '0')
        self.assertEqual(row.product_max_discount_state, PRESENT_UNCONFIRMED)
        self.assertEqual(row.product_coupon_count_number, '0')
        self.assertEqual(row.product_coupons_per_price_state, PRESENT_UNCONFIRMED)
        self.assertIsNone(row.product_multi_activity_price_number)
        self.assertEqual(row.product_multi_activity_price_state, NEGATIVE_NOT_ADAPTED)
        self.assertEqual(row.product_show_origin_price_state, NEGATIVE_NOT_ADAPTED)
        self.assertEqual(row.sku_ladder_package.price_state, PRESENT_UNCONFIRMED)
        self.assertFalse(result.count_zero_means_no_threshold)
        self.assertFalse(result.discount_number_proves_algorithm)
        self.assertFalse(result.zero_amount_means_free)
        self.assertFalse(result.negative_adapted_as_amount)
        body = rules_body()
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['activity_policy']['discount_by_count']['discount'] = -5
        product['activity_policy']['discount_by_count']['count'] = None
        product['render_info']['sup_info']['discountTag'] = '元'
        product['skus'][0]['sku_ladder_box_info'].pop('ladder_package_price')
        ruled = parsed(body)
        current = next(item for item in ruled.rows if item.sku_id == '201')
        self.assertEqual(current.product_discount_by_count.pair_state, 'BOTH_KEYS_PRESENT')
        self.assertEqual(current.product_discount_by_count.count_state, 'SOURCE_NULL')
        self.assertIsNone(current.product_discount_by_count.count_number)
        self.assertEqual(current.product_discount_by_count.discount_state, NEGATIVE_NOT_ADAPTED)
        self.assertIsNone(current.product_discount_by_count.discount_number)
        self.assertEqual(current.product_discount_tag_text_state, CLOSED_MARK_NOT_PROMOTED)
        self.assertNotIn('CNY', current.__dict__.values())
        self.assertNotIn('YUAN', current.__dict__.values())
        self.assertEqual(current.sku_ladder_package.pair_state, 'PRICE_KEY_NOT_OBSERVED')
        self.assertEqual(current.sku_ladder_package.food_num_number, '2')
        self.assertIsNone(current.sku_ladder_package.price_number)

    def test_short_duplicate_and_mismatched_rule_coordinates_use_fixed_error(self):
        analysis = analyze_public_body(json.dumps(rules_body()).encode())
        path = '$.data.food_spu_tags[].dynamic_spus[].max_discount'
        for change in ('short', 'duplicate', 'mismatch'):
            broken = json.loads(json.dumps(analysis))
            selected = next(value for value in broken['public_values'] if value['path'] == path)
            if change == 'short':
                selected['coordinates'] = ['data', 'food_spu_tags', 0, 'dynamic_spus']
            elif change == 'duplicate':
                broken['public_values'].append(json.loads(json.dumps(selected)))
            else:
                selected['coordinates'][-1] = 'name'
            with self.subTest(change=change):
                with self.assertRaises(CategoryCandidateError) as raised:
                    parse_price_rules(broken)
                self.assertEqual(raised.exception.code, 'P29_CATEGORY_CANDIDATE_INVALID')

    def test_one_response_does_not_receive_another_response_rule(self):
        earlier = parsed()
        body = rules_body()
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product.pop('max_discount')
        product['skus'][0].pop('sku_ladder_box_info')
        product['skus'][0].pop('full_discount_tag')
        later = parsed(body)
        self.assertEqual(next(row for row in earlier.rows if row.sku_id == '201').product_max_discount_number, '0')
        current = next(row for row in later.rows if row.sku_id == '201')
        self.assertEqual(current.product_max_discount_state, 'NOT_OBSERVED')
        self.assertIsNone(current.product_max_discount_number)
        self.assertEqual(current.sku_ladder_package.pair_state, 'BOTH_KEYS_NOT_OBSERVED')
        self.assertEqual(current.sku_full_discount_tag_texts_state, 'NOT_OBSERVED')

    def test_nested_text_indexes_follow_coordinates_not_list_order(self):
        analysis = analyze_public_body(json.dumps(rules_body()).encode())
        path = '$.data.food_spu_tags[].dynamic_spus[].skus[].full_discount_tag[].sub_tags[].text'
        texts = [value for value in analysis['public_values'] if value['path'] == path]
        analysis['public_values'] = [value for value in analysis['public_values'] if value['path'] != path]
        analysis['public_values'].extend(reversed(texts))
        row = next(item for item in parse_price_rules(analysis).rows if item.sku_id == '201')
        self.assertEqual([(item.tag_index, item.sub_tag_index) for item in row.sku_full_discount_tag_texts],
                         [(0, 0), (0, 1), (1, 0)])
        self.assertEqual([item.text for item in row.sku_full_discount_tag_texts],
                         ['synthetic_rule_a', 'synthetic_rule_b', 'synthetic_rule_c'])


if __name__ == '__main__':
    unittest.main()
