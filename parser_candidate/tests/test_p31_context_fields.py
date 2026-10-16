import copy
import unittest

from collection_adapter.tests.test_p28_business_batch import bodies
from parser_candidate.tests.test_p31_public_fields import analysis
from parser_candidate import p31_context_fields as fields
from parser_candidate.p29_category_profile import CategoryCandidateError


def context_bodies():
    food, product = bodies()
    food['data'].update(
        container_operation_source={'tag_name': 'Synthetic 运营',
            'operation_source_list': [{'content': ''}, {'content': 'Synthetic 说明'}]},
        moderate_ordering_reminder='Synthetic 适量点餐',
        pick_goods_tab_info={'delivery': {'text': 'Synthetic 配送'}, 'self_pick': {'text': None}},
        shopping_cart={'tips': 'PRIVATE_SYNTHETIC'},
    )
    product['data']['required_tag_info'] = {'tips': 'Synthetic 必选', 'toast': ''}
    product['data']['food_spu_tags'][0].update(
        activity_info={'activity_text': ''}, activity_tag='Synthetic 活动',
        description='Synthetic 分类, "说明"', fold_dynamic_spus_text='Synthetic 展开',
        tag_description=None,
    )
    return food, product


class ContextFieldTests(unittest.TestCase):
    def test_root_and_category_text_preserve_scope_indices_and_empty_states(self):
        food, product = context_bodies()
        roots = fields.parse_context_fields(analysis(food), 'FOOD')
        self.assertEqual(len(roots), 6)
        indexed = [r for r in roots if r['field'] == 'operation_content_text']
        self.assertEqual([(r['entry_index'], r['value'], r['state']) for r in indexed],
                         [(0, '', 'SOURCE_EMPTY'), (1, 'Synthetic 说明', 'PRESENT_UNCONFIRMED')])
        self.assertTrue(all(r['scope'] == 'FOOD_ROOT' and r['category_ref'] is None for r in roots))
        rows = fields.parse_context_fields(analysis(product), 'PRODUCTLIST')
        category = [r for r in rows if r['scope'] == 'CATEGORY']
        self.assertEqual(len(category), 5)
        self.assertTrue(all(r['category_ref'] == 'category_a' and r['category_index'] == 0 for r in category))
        self.assertEqual(next(r['state'] for r in category if r['field'] == 'category_tag_description_text'), 'SOURCE_NULL')
        self.assertNotIn('PRIVATE_SYNTHETIC', str(roots + rows))

    def test_empty_category_and_missing_field_do_not_borrow_other_values(self):
        _, product = context_bodies()
        product['data']['food_spu_tags'].append({'tag': 'synthetic_empty', 'dynamic_spus': []})
        source = analysis(product)
        rows = fields.parse_context_fields(source, 'PRODUCTLIST')
        empty = [r for r in rows if r['category_ref'] == 'synthetic_empty']
        self.assertEqual(len(empty), 5)
        self.assertTrue(all(r['value'] is None and r['state'] == 'NOT_OBSERVED' for r in empty))
        source['public_values'].reverse()
        self.assertEqual(fields.parse_context_fields(source, 'PRODUCTLIST'), rows)

    def test_malformed_duplicate_or_orphan_coordinates_reject(self):
        _, product = context_bodies()
        source = analysis(product)
        target = next(v for v in source['public_values'] if v['path'] == '$.data.food_spu_tags[].description')
        for change in ('duplicate', 'orphan', 'bool_index', 'wrong_path'):
            bad = copy.deepcopy(source); extra = copy.deepcopy(target)
            if change == 'orphan': extra['coordinates'][2] = 19
            if change == 'bool_index': extra['coordinates'][2] = True
            if change == 'wrong_path': extra['coordinates'][-1] = 'other'
            bad['public_values'].append(extra)
            with self.subTest(change=change), self.assertRaises(CategoryCandidateError):
                fields.parse_context_fields(bad, 'PRODUCTLIST')

    def test_non_text_structure_and_unknown_endpoint_reject(self):
        for value in ({}, [], 2, 'https://synthetic.invalid'):
            food, _ = context_bodies(); food['data']['moderate_ordering_reminder'] = value
            source = analysis(food)
            if type(value) is str:
                source['public_values'].append({'path': '$.data.moderate_ordering_reminder',
                    'coordinates': ['data', 'moderate_ordering_reminder'], 'value': value})
            with self.subTest(kind=type(value).__name__), self.assertRaises(CategoryCandidateError):
                fields.parse_context_fields(source, 'FOOD')
        with self.assertRaises(CategoryCandidateError):
            fields.parse_context_fields(analysis(context_bodies()[0]), 'OTHER')
