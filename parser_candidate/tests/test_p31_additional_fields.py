import copy
import json
import unittest

from parser_candidate import p31_additional_fields as fields
from parser_candidate.p29_category_profile import CategoryCandidateError
from parser_candidate.tests.test_p31_public_fields import analysis, product_body
from collection_adapter.tests.test_p28_business_batch import bodies


def additional_body():
    body = product_body()
    p = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
    p.update(group_id=88, ctime=1700000001, spu_category=0, spu_type=-1,
             tag='', activity_tag_id=None, isPremiumSpu=False)
    p.setdefault('render_info', {}).update(img_area={'label_text': 'Synthetic 图片角标'},
                                          sup_info={'ruleTag': 'Synthetic 规则说明'})
    p['skus'][0].update(activity_tag='Synthetic SKU 活动', activity_stock=-1,
        promotion={'activity_text': 'Synthetic 活动文案', 'activity_type': 7},
        promotion_tag=[{'rule_id': 11, 'sub_tags': [{'text': 'Synthetic 标签, "一"'}, {'text': ''}]},
                       {'rule_id': 12, 'sub_tags': [{'text': None}]}])
    return body


class AdditionalFieldTests(unittest.TestCase):
    def test_own_scalar_values_keep_unknown_codes_and_time(self):
        rows = fields.parse_product_fields(analysis(additional_body()))
        row = rows['category_a', '101', '201']
        self.assertEqual(row.get('product_group_id_number'), '88')
        self.assertEqual(row['product_ctime_number'], '1700000001')
        self.assertEqual(row['product_spu_category_code'], '0')
        self.assertEqual(row['product_spu_type_code_state'], 'NEGATIVE_SEMANTICS_UNCONFIRMED')
        self.assertEqual(row['product_tag_text_state'], 'SOURCE_EMPTY')
        self.assertEqual(row['product_activity_tag_id_text_state'], 'SOURCE_NULL')
        self.assertIs(row['product_is_premium_spu_flag'], False)
        self.assertEqual(row['sku_activity_stock_number'], '-1')
        self.assertEqual(row['sku_promotion_activity_text'], 'Synthetic 活动文案')
        self.assertEqual(rows['category_a', '101', '202']['sku_activity_tag_text_state'], 'NOT_OBSERVED')

    def test_label_indices_keep_groups_null_empty_and_are_order_independent(self):
        source = analysis(additional_body())
        row = fields.parse_product_fields(source)['category_a', '101', '201']
        expected = [{'indices': [0, 0], 'value': 'Synthetic 标签, "一"', 'state': 'PRESENT_UNCONFIRMED'},
                    {'indices': [0, 1], 'value': '', 'state': 'SOURCE_EMPTY'},
                    {'indices': [1, 0], 'value': None, 'state': 'SOURCE_NULL'}]
        self.assertEqual(row.get('sku_promotion_tag_texts'), expected)
        self.assertEqual(json.loads(row['sku_promotion_tag_texts_json']), expected)
        self.assertEqual(row['sku_promotion_tag_rule_ids'][1]['indices'], [1])
        source['public_values'].reverse()
        self.assertEqual(fields.parse_product_fields(source)['category_a', '101', '201'], row)

    def test_new_paths_reject_duplicate_wrong_type_or_orphan(self):
        source = analysis(additional_body())
        for problem in ('duplicate', 'orphan', 'type', 'coordinate'):
            bad = copy.deepcopy(source)
            item = next(v for v in bad['public_values'] if v['path'].endswith('.group_id'))
            if problem == 'duplicate': bad['public_values'].append(copy.deepcopy(item))
            if problem == 'orphan': item['coordinates'][4] = 7999
            if problem == 'type': item['value'] = True
            if problem == 'coordinate': item['coordinates'][-1] = 'other'
            with self.subTest(problem=problem), self.assertRaises(CategoryCandidateError):
                fields.parse_product_fields(bad)

    def test_store_labels_exclude_links_styles_and_personal_fields(self):
        food, _ = bodies()
        food['data']['poi_info'].update(brand_id=9, shop_business_type='Synthetic 类型',
            buy_sku_count_threshold=0, has_poi_env=False, has_xbk=False,
            speed_refund_status=2, support_pay=3, restrict_toast='',
            poi_label={'labels': [{'label_text': 'Synthetic 服务', 'label_desc_text': '',
                                  'label_color': 'PRIVATE_STYLE', 'scheme_url': 'https://synthetic.invalid'}]},
            poi_coupon={'fold_coupon_list': [{'coupon_value': 999, 'coupon_status': 1}]},
            is_favorite=1, distance='PRIVATE_CONTEXT')
        parsed = fields.parse_store_fields(analysis(food))
        self.assertEqual(parsed.get('store_brand_id_number'), '9')
        self.assertEqual(parsed.get('store_support_pay_code'), '3')
        self.assertEqual(parsed['store_buy_sku_count_threshold_number'], '0')
        self.assertIs(parsed['store_has_poi_env_flag'], False)
        self.assertEqual(parsed['store_restrict_toast_text_state'], 'SOURCE_EMPTY')
        self.assertEqual(parsed['store_label_texts'][0]['value'], 'Synthetic 服务')
        self.assertEqual(parsed['store_label_descriptions'][0]['state'], 'SOURCE_EMPTY')
        self.assertNotIn('PRIVATE', json.dumps(parsed))
        self.assertNotIn('synthetic.invalid', json.dumps(parsed))
        self.assertFalse(any('coupon' in k or 'favorite' in k or 'distance' in k for k in parsed))
