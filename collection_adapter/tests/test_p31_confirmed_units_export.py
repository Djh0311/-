import copy
import csv
import unittest
from unittest.mock import patch

from collection_adapter import p31_confirmed_units_export as export
from collection_adapter import p31_context_codes_export as previous
from collection_adapter.tests import test_p29_store_inventory as fixtures
from collection_adapter.p29_store_inventory import _validate
from parser_candidate.p29_category_profile import CategoryCandidateError


class ConfirmedUnitsTests(unittest.TestCase):
    setUpFixture=fixtures.StoreInventoryTests.setUp
    input=fixtures.StoreInventoryTests.input
    read=fixtures.StoreInventoryTests.read
    write=fixtures.StoreInventoryTests.write

    def setUp(self):
        self.setUpFixture()
        root=patch('collection_adapter.p31_business_export._root',return_value=self.root)
        root.start();self.addCleanup(root.stop)
        self.input_bundle='p31_context_codes_'+'e'*32
        previous.publish_business_fields(self.root,self.observation,[self.name],self.input_bundle)

    def confirmation(self):
        return {'schema_version':'p31-user-amount-confirmation/v1','confirmation_ref':'user-confirmation:p31-cny-yuan',
                'window_ref':self.window,'input_result_name':self.input_bundle,'currency':'CNY','amount_unit':'YUAN',
                'evidence_kind':'EXPLICIT_USER_CONFIRMATION','scope':'EXACT_EXISTING_RESULT_PRICE_AND_FEE_FIELDS',
                'source_unit_presence_unchanged':True,'no_numeric_conversion':True}

    def test_category_units_are_user_confirmed_without_changing_amounts(self):
        with patch.object(export,'_confirmation',return_value=self.confirmation()):
            products,stores,_,_=export.business_view(self.root,self.observation,[self.name])
        category=[r for r in products['records'] if r['source_kind']=='PARTIAL_CATEGORY_CANDIDATE']
        self.assertTrue(all(r['currency']=='CNY' and r['amount_unit']=='YUAN' for r in category))
        old=self.read(self.input_bundle+'/records.json')
        allowed={'currency','amount_unit','currency_status','amount_unit_status','currency_basis','amount_unit_basis'}
        for before,after in zip(old['records'],products['records']):
            self.assertEqual({k:after[k] for k in before if k not in allowed},{k:v for k,v in before.items() if k not in allowed})
            self.assertEqual(after['prior_currency_status'],before['currency_status'])
            self.assertEqual(after['prior_amount_unit_status'],before['amount_unit_status'])
        self.assertEqual(stores['records'][0]['amount_unit'],'YUAN')
        self.assertFalse(products['currency_inferred'])
        self.assertFalse(stores['delivery_terms_apply_to_all_customers'])

    def test_confirmation_cannot_be_reused_for_other_window_or_result(self):
        for key,value in [('window_ref','result:'+'0'*32),('input_result_name','p31_context_codes_'+'f'*32)]:
            confirmation=self.confirmation();confirmation[key]=value
            with self.subTest(key=key),patch.object(export,'_confirmation',return_value=confirmation),self.assertRaises(CategoryCandidateError):
                export.business_view(self.root,self.observation,[self.name])

    def test_confirmation_does_not_cover_changed_data(self):
        saved=self.read(self.input_bundle+'/records.json');saved['records'][0]['sku_price_number']='999'
        self.write(self.input_bundle+'/records.json',saved)
        with patch.object(export,'_confirmation',return_value=self.confirmation()),self.assertRaises(CategoryCandidateError):
            export.business_view(self.root,self.observation,[self.name])

    def test_bundle_columns_and_contract_keep_evidence(self):
        name='p31_confirmed_units_'+'d'*32
        with patch.object(export,'_confirmation',return_value=self.confirmation()):
            export.publish_business_fields(self.root,self.observation,[self.name],name)
        products=self.read(name+'/records.json');stores=self.read(name+'/stores.json')
        for table,doc,filename in [('products',products,'records.csv'),('stores',stores,'stores.csv')]:
            with (self.root/name/filename).open(newline='') as stream:
                reader=csv.DictReader(stream)
                self.assertEqual(list(reader),[{k:previous.base._cell(r[k]) for k in reader.fieldnames} for r in doc['records']])
        bad=copy.deepcopy(products)
        next(r for r in bad['records'] if r['source_kind']=='PARTIAL_CATEGORY_CANDIDATE')['currency_basis']='INITIAL_PAIR_PAGE_CONFIRMATION'
        with self.assertRaises(CategoryCandidateError):_validate(bad,export.PRODUCT_SCHEMA)
