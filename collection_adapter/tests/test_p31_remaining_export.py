import csv
import copy
import json
import stat
import unittest
from unittest.mock import patch

from collection_adapter import p31_remaining_export as export, p31_additional_export as previous
from collection_adapter.tests import test_p29_store_inventory as fixtures
from collection_adapter.tests.test_p29_category_review import synthetic_body
from collection_adapter.p29_store_inventory import _validate
from collection_core.result_publisher import ResultPublishError
from parser_candidate.p29_category_profile import CategoryCandidateError
from parser_candidate.tests.test_p31_remaining_fields import remaining_bodies


class RemainingExportTests(unittest.TestCase):
    setUpFixture = fixtures.StoreInventoryTests.setUp
    input = fixtures.StoreInventoryTests.input
    read = fixtures.StoreInventoryTests.read
    write = fixtures.StoreInventoryTests.write

    def setUp(self):
        with patch('collection_adapter.tests.test_p29_store_inventory.bodies', remaining_bodies):
            self.setUpFixture()
        root = patch('collection_adapter.p31_business_export._root', return_value=self.root)
        root.start(); self.addCleanup(root.stop)
        self.bundle_name = 'p31_remaining_fields_' + 'e' * 32

    def test_remaining_fields_reach_own_store_and_product_rows(self):
        products, stores = export.business_view(self.root, self.observation, [self.name])
        self.assertEqual(stores['records'][0].get('store_share_title_text'), 'Synthetic 标题')
        self.assertEqual(stores['records'][0]['store_platform_promotion_info_null_state'], 'SOURCE_NULL')
        row = next(r for r in products['records'] if r['source_kind'] == 'CHECKED_INITIAL_PAIR')
        self.assertEqual(row['product_render_price_status_code'], '2')

    def test_versioned_bundle_preserves_old_fields_and_validates_csv_nulls(self):
        old_products, old_stores = previous.business_view(self.root, self.observation, [self.name])
        export.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        dest = self.root / self.bundle_name
        products, stores = [self.read(self.bundle_name + '/' + n) for n in ('records.json','stores.json')]
        self.assertEqual(products['schema_version'], 'p31-business-products/v3')
        for old, row in zip(old_products['records']+old_stores['records'], products['records']+stores['records']):
            self.assertEqual({k: row[k] for k in old}, old)
        dictionary = self.read(self.bundle_name + '/field_dictionary.json')
        self.assertEqual(dictionary['schema_version'], 'p31-field-dictionary/v2')
        for table,doc,file in [('products',products,'records.csv'),('stores',stores,'stores.csv')]:
            with (dest/file).open(newline='') as stream:
                reader=csv.DictReader(stream)
                self.assertEqual(reader.fieldnames,[d['field'] for d in dictionary['fields'] if d['table']==table])
                self.assertEqual(list(reader),[{k:previous.base._cell(row[k]) for k in reader.fieldnames} for row in doc['records']])
        bad=copy.deepcopy(stores)
        bad['records'][0]['store_platform_promotion_info_null'] = 'invented'
        with self.assertRaises(CategoryCandidateError): _validate(bad, export.STORE_SCHEMA)
        bad=copy.deepcopy(stores)
        bad['records'][0]['personal_coupon'] = 'not allowed'
        with self.assertRaises(CategoryCandidateError): _validate(bad, export.STORE_SCHEMA)
        self.assertEqual(stat.S_IMODE(dest.stat().st_mode),0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in dest.iterdir()))
        saved={p.name:p.read_bytes() for p in dest.iterdir()}
        with self.assertRaises(ResultPublishError):
            export.publish_business_fields(self.root,self.observation,[self.name],self.bundle_name)
        self.assertEqual(saved,{p.name:p.read_bytes() for p in dest.iterdir()})

    def test_equal_time_render_status_conflict_and_newer_absence(self):
        body=synthetic_body();p=body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        p['render_info']['price_info']['status']=1
        first=self.input('a','c','2026-01-01T00:01:00+00:00',body)
        p['render_info']['price_info']['status']=2
        second=self.input('b','d','2026-01-01T00:01:00+00:00',body)
        with self.assertRaises(CategoryCandidateError):export.business_view(self.root,self.observation,[first,second])
        del p['render_info']['price_info']['status']
        later=self.input('f','9','2026-01-01T00:02:00+00:00',body)
        products,_=export.business_view(self.root,self.observation,[first,later])
        self.assertTrue(all(r['product_render_price_status_code_state']=='NOT_OBSERVED' for r in products['records'] if r['source_kind']!='CHECKED_INITIAL_PAIR'))

    def test_late_write_failure_cleans_only_new_bundle(self):
        original=export._write_file
        def fail(fd,name,payload):
            if name=='manifest.json':raise OSError()
            original(fd,name,payload)
        with patch.object(export,'_write_file',side_effect=fail),self.assertRaises(ResultPublishError):
            export.publish_business_fields(self.root,self.observation,[self.name],self.bundle_name)
        self.assertFalse((self.root/self.bundle_name).exists())
