import copy
import unittest

from parser_candidate.p31_store_promotions import parse_store_promotions
from parser_candidate.tests.test_p31_public_fields import analysis
from parser_candidate.p29_category_profile import CategoryCandidateError
from collection_adapter.tests.test_p28_business_batch import bodies


def promotion_bodies():
    food, product = bodies()
    food['data']['poi_info']['poi_normal_tags'] = [
        {'sub_tags': [{'text': 'Synthetic offer A'}, {'text': ''}]},
        {'sub_tags': [{'text': None}, {'text': 'Synthetic offer B'}]},
    ]
    return food, product


class StorePromotionTests(unittest.TestCase):
    def test_nested_indices_text_and_absence_states_are_preserved(self):
        source = analysis(promotion_bodies()[0])
        rows = parse_store_promotions(source)
        self.assertEqual(len(rows), 4)
        self.assertEqual([(r['group_index'], r['tag_index'], r['state']) for r in rows],
                         [(0, 0, 'PRESENT_UNCONFIRMED'), (0, 1, 'SOURCE_EMPTY'),
                          (1, 0, 'SOURCE_NULL'), (1, 1, 'PRESENT_UNCONFIRMED')])
        self.assertEqual(rows[0]['display_text'], 'Synthetic offer A')
        source['public_values'].reverse()
        self.assertEqual(parse_store_promotions(source), rows)

    def test_missing_is_explicit_and_private_cart_is_ignored(self):
        food, _ = bodies()
        food['data']['shopping_cart'] = {'prompt_text': 'PRIVATE_SYNTHETIC'}
        rows = parse_store_promotions(analysis(food))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['state'], 'NOT_OBSERVED')
        self.assertIsNone(rows[0]['group_index'])
        self.assertIsNone(rows[0]['tag_index'])
        self.assertNotIn('PRIVATE_SYNTHETIC', str(rows))

    def test_duplicates_invalid_indices_and_leaf_types_reject(self):
        source = analysis(promotion_bodies()[0])
        item = next(v for v in source['public_values'] if 'poi_normal_tags' in v['path'])
        for kind in ('duplicate', 'boolean_index', 'wrong_path', 'object', 'url'):
            bad = copy.deepcopy(source)
            target = next(v for v in bad['public_values'] if v['coordinates'] == item['coordinates'])
            if kind == 'duplicate': bad['public_values'].append(copy.deepcopy(target))
            elif kind == 'boolean_index': target['coordinates'][4] = True
            elif kind == 'wrong_path': target['coordinates'][3] = 'shopping_cart'
            elif kind == 'object': target['value'] = {}
            else: target['value'] = 'https://synthetic.invalid'
            with self.subTest(kind=kind), self.assertRaises(CategoryCandidateError):
                parse_store_promotions(bad)
