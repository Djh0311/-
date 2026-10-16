import copy
import unittest

from parser_candidate import p31_remaining_fields as fields
from parser_candidate.p29_category_profile import CategoryCandidateError
from parser_candidate.tests.test_p31_public_fields import analysis, product_body
from collection_adapter.tests.test_p28_business_batch import bodies


def remaining_bodies():
    food, _ = bodies()
    food['data']['poi_info'].update(share_tip={
        'activity_id': 71, 'channels': [3, 1], 'description': 'Synthetic 分享, "介绍"',
        'share_info': {'title': 'Synthetic 标题', 'content': '',
                       'weixin_url': 'https://synthetic.invalid',
                       'share_recommend': {'label_text': 'Synthetic 推荐'}}},
        dine_in_restaurant_label=None, platform_promotion_info=None, label_info=None)
    product = product_body()
    product['data']['food_spu_tags'][0]['dynamic_spus'][0].setdefault('render_info', {}).setdefault('price_info', {})['status'] = 2
    return food, product


class RemainingFieldTests(unittest.TestCase):
    def test_public_share_texts_and_channel_indices_exclude_navigation(self):
        food, _ = remaining_bodies()
        row = fields.parse_store_fields(analysis(food))
        self.assertEqual(row.get('store_share_title_text'), 'Synthetic 标题')
        self.assertEqual(row['store_share_content_text_state'], 'SOURCE_EMPTY')
        self.assertEqual(row['store_share_channel_codes'], [
            {'indices': [0], 'value': '3', 'state': 'PRESENT_UNCONFIRMED'},
            {'indices': [1], 'value': '1', 'state': 'PRESENT_UNCONFIRMED'}])
        self.assertNotIn('synthetic.invalid', str(row))

    def test_explicit_null_is_not_absence_and_unknown_structure_rejects(self):
        food, _ = remaining_bodies()
        row = fields.parse_store_fields(analysis(food))
        self.assertEqual(row.get('store_platform_promotion_info_null_state'), 'SOURCE_NULL')
        self.assertEqual(row['store_regular_promotion_info_null_state'], 'NOT_OBSERVED')
        source = analysis(food)
        entry = next(v for v in source['public_values'] if v['path'].endswith('.platform_promotion_info'))
        for value in (0, '', False, {'unexpected': 'Synthetic'}):
            entry['value'] = value
            with self.subTest(kind=type(value).__name__), self.assertRaises(CategoryCandidateError):
                fields.parse_store_fields(source)
        for value in ({}, [], {'new_field': 'Synthetic'}):
            food['data']['poi_info']['platform_promotion_info'] = value
            with self.subTest(structure=type(value).__name__), self.assertRaises(CategoryCandidateError):
                fields.parse_store_fields(analysis(food))

    def test_render_price_status_is_not_sku_stock_and_coupon_ids_are_excluded(self):
        _, product = remaining_bodies()
        p = product['data']['food_spu_tags'][0]['dynamic_spus'][0]
        p['coupon_id'] = 999
        p['skus'][0]['goods_coupon_view_id'] = 'Synthetic account-bound possibility'
        rows = fields.parse_product_fields(analysis(product))
        self.assertEqual(rows['category_a','101','201'].get('product_render_price_status_code'), '2')
        self.assertEqual(set(rows['category_a','101','201']), {'product_render_price_status_code','product_render_price_status_code_state'})

    def test_duplicate_share_channel_or_malformed_coordinate_rejects(self):
        food, _ = remaining_bodies()
        source = analysis(food)
        entry = next(v for v in source['public_values'] if v['path'].endswith('.channels[]'))
        for problem in ('duplicate', 'coordinate'):
            bad = copy.deepcopy(source)
            extra = copy.deepcopy(entry)
            if problem == 'coordinate': extra['coordinates'][-1] = True
            bad['public_values'].append(extra)
            with self.subTest(problem=problem), self.assertRaises(CategoryCandidateError):
                fields.parse_store_fields(bad)
