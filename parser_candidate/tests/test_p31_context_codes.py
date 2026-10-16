import copy
import unittest

from collection_adapter.tests.test_p28_business_batch import bodies
from parser_candidate.tests.test_p31_public_fields import analysis
from parser_candidate import p31_context_codes as fields
from parser_candidate.p29_category_profile import CategoryCandidateError


def code_bodies():
    food, product = bodies()
    food['data'].update(shop_type=2, has_hotsale_tag=False, calculate_price_from_server=True,
        container_operation_source={'tag':'synthetic_operation','tag_sequence':0,
            'operation_source_list':[{'activity_type':2,'sequence':0,'type':1},
                                     {'activity_type':-1,'sequence':1,'type':None}]},
        pick_goods_tab_info={'delivery':{'activity_info_type':3}})
    product['data'].update(has_hotsale_tag=True, supportPreOrder=False,
        support_cake_product_upgrade=True, poi_box_price_detail={'box_price_type':2},
        required_tag_info={'has_required_tag':True,'required_tag_id':'category_a'})
    product['data']['food_spu_tags'][0].update(buzType=0, health_tag=False, sequence=0,
        type=2, selected=1, TYPE_NORMAL=1, TYPE_ACT_FOOD=2, TYPE_RECOMMEND=3, TYPE_SALE_RANK=4)
    return food, product


class ContextCodeTests(unittest.TestCase):
    def test_codes_keep_types_indices_and_unknown_meaning(self):
        food, product = code_bodies()
        rows=fields.parse_context_codes(analysis(food),'FOOD')
        self.assertEqual(len(rows),11)
        operations=[r for r in rows if r['field']=='operation_activity_type_code']
        self.assertEqual([(r['entry_index'],r['value'],r['state']) for r in operations],
                         [(0,'2','PRESENT_UNCONFIRMED'),(1,'-1','NEGATIVE_SEMANTICS_UNCONFIRMED')])
        self.assertIs(next(r['value'] for r in rows if r['field']=='food_has_hotsale_tag_flag'),False)
        self.assertEqual(next(r['state'] for r in rows if r['field']=='operation_type_code' and r['entry_index']==1),'SOURCE_NULL')
        category=[r for r in fields.parse_context_codes(analysis(product),'PRODUCTLIST') if r['scope']=='CATEGORY']
        self.assertEqual(len(category),4)
        self.assertTrue(all(r['category_ref']=='category_a' and r['category_index']==0 for r in category))
        self.assertNotIn('selected',str(category))
        self.assertNotIn('TYPE_NORMAL',str(category))

    def test_empty_category_missing_and_reordering(self):
        _,product=code_bodies();product['data']['food_spu_tags'].append({'tag':'synthetic_empty','dynamic_spus':[]})
        source=analysis(product);rows=fields.parse_context_codes(source,'PRODUCTLIST')
        empty=[r for r in rows if r['category_ref']=='synthetic_empty']
        self.assertEqual(len(empty),4)
        self.assertTrue(all(r['value'] is None and r['state']=='NOT_OBSERVED' for r in empty))
        source['public_values'].reverse();self.assertEqual(rows,fields.parse_context_codes(source,'PRODUCTLIST'))

    def test_duplicate_orphan_boolean_index_and_wrong_scalar_rejected(self):
        _,product=code_bodies();source=analysis(product)
        target=next(v for v in source['public_values'] if v['path']=='$.data.food_spu_tags[].buzType')
        for kind in ('duplicate','orphan','bool_index','wrong_scalar'):
            bad=copy.deepcopy(source);extra=copy.deepcopy(target)
            if kind=='orphan':extra['coordinates'][2]=99
            if kind=='bool_index':extra['coordinates'][2]=True
            if kind=='wrong_scalar':extra['value']=True;bad['public_values'].remove(next(v for v in bad['public_values'] if v['path']==target['path']))
            bad['public_values'].append(extra)
            with self.subTest(kind=kind),self.assertRaises(CategoryCandidateError):fields.parse_context_codes(bad,'PRODUCTLIST')

    def test_non_scalar_structure_and_noninteger_code_rejected(self):
        for value in ({},[],1.5):
            food,_=code_bodies();food['data']['shop_type']=value
            with self.subTest(value=value),self.assertRaises(CategoryCandidateError):fields.parse_context_codes(analysis(food),'FOOD')
