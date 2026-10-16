import copy
from dataclasses import replace
import unittest
from unittest.mock import patch

from collection_adapter import p31_initial_relation_export as export
from collection_adapter import p31_context_export as previous
from collection_adapter.tests import test_p29_store_inventory as fixtures
from collection_adapter.tests.test_p29_category_review import synthetic_body
from collection_adapter.p29_store_inventory import _validate
from parser_candidate.p29_category_profile import CategoryCandidateError


class InitialRelationExportTests(unittest.TestCase):
    setUp = fixtures.StoreInventoryTests.setUp
    input = fixtures.StoreInventoryTests.input
    read = fixtures.StoreInventoryTests.read
    write = fixtures.StoreInventoryTests.write

    def view(self, names=None):
        with patch('collection_adapter.p31_business_export._root', return_value=self.root):
            return export.business_view(self.root, self.observation, names or [self.name])

    def test_initial_relation_and_role_are_computed_and_other_values_preserved(self):
        with patch('collection_adapter.p31_business_export._root', return_value=self.root):
            old = previous.business_view(self.root, self.observation, [self.name])
        products, stores, texts = self.view()
        initial = [r for r in products['records'] if r['source_kind']=='CHECKED_INITIAL_PAIR']
        self.assertTrue(initial)
        self.assertTrue(all(r['numeric_min_relation']=='EQUAL_PRODUCT_RENDER_AND_MIN_SKU' for r in initial))
        self.assertTrue(all(r['product_unit_role']=='PRODUCT_MEASURE_TEXT_NOT_AMOUNT_UNIT' for r in initial))
        for before, after in zip(old[0]['records'], products['records']):
            changed = {'numeric_min_relation','product_unit_role'} if before['source_kind']=='CHECKED_INITIAL_PAIR' else set()
            self.assertEqual({k:v for k,v in before.items() if k not in changed}, {k:v for k,v in after.items() if k not in changed})
        self.assertEqual((stores,texts), old[1:])

    def test_later_category_row_never_borrows_initial_role_or_currency(self):
        body = synthetic_body();body['data']['food_spu_tags'][0]['tag']='category_a'
        product=body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['unit']='元'
        name=self.input('f','9','2026-01-01T00:02:00+00:00',body)
        products,_,_=self.view([name])
        self.assertTrue(all(r['source_kind']=='PARTIAL_CATEGORY_CANDIDATE' for r in products['records']))
        self.assertTrue(all(r['numeric_min_relation']=='EQUAL_PRODUCT_RENDER_AND_MIN_SKU' and r['product_unit_role']=='CLOSED_MARK_NOT_PROMOTED_TO_CURRENCY_OR_AMOUNT_UNIT' for r in products['records']))
        self.assertTrue(all(r['currency'] is None and r['amount_unit'] is None for r in products['records']))

    def test_duplicate_or_changed_initial_parse_identity_is_rejected(self):
        original=export.parse_category_price
        for kind in ('duplicate','changed_price'):
            def damaged(source):
                result=original(source)
                rows=list(result.rows)
                if kind=='duplicate':rows[1]=rows[0]
                else:rows[0]=replace(rows[0],sku_price_number='99')
                return replace(result,rows=tuple(rows))
            with self.subTest(kind=kind), patch.object(export,'parse_category_price',side_effect=damaged), self.assertRaises(CategoryCandidateError):
                self.view()

    def test_versioned_bundle_rejects_old_initial_placeholder(self):
        name='p31_initial_relation_'+'e'*32
        with patch('collection_adapter.p31_business_export._root', return_value=self.root):
            export.publish_business_fields(self.root,self.observation,[self.name],name)
        doc=self.read(name+'/records.json')
        self.assertEqual(doc['schema_version'],'p31-business-products/v4')
        self.assertTrue(doc['initial_pair_relation_and_unit_role_reparsed'])
        bad=copy.deepcopy(doc)
        next(r for r in bad['records'] if r['source_kind']=='CHECKED_INITIAL_PAIR')['numeric_min_relation']='NOT_REPARSED_ON_INITIAL_PAIR'
        with self.assertRaises(CategoryCandidateError):_validate(bad,export.PRODUCT_SCHEMA)
