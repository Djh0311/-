import copy
import csv
import stat
import unittest
from unittest.mock import patch

from collection_adapter import p31_context_codes_export as export
from collection_adapter import p31_initial_relation_export as previous
from collection_adapter.tests import test_p29_store_inventory as fixtures
from collection_adapter.p29_store_inventory import _validate
from collection_core.result_publisher import ResultPublishError
from parser_candidate.p29_category_profile import CategoryCandidateError
from parser_candidate.tests.test_p31_context_codes import code_bodies


class ContextCodesExportTests(unittest.TestCase):
    setUpFixture=fixtures.StoreInventoryTests.setUp
    input=fixtures.StoreInventoryTests.input
    read=fixtures.StoreInventoryTests.read
    write=fixtures.StoreInventoryTests.write

    def setUp(self):
        with patch('collection_adapter.tests.test_p29_store_inventory.bodies',code_bodies):self.setUpFixture()
        root=patch('collection_adapter.p31_business_export._root',return_value=self.root)
        root.start();self.addCleanup(root.stop)
        self.bundle_name='p31_context_codes_'+'e'*32

    def test_own_source_codes_are_separate_and_old_tables_preserved(self):
        old=previous.business_view(self.root,self.observation,[self.name])
        p,s,t,c=export.business_view(self.root,self.observation,[self.name])
        self.assertEqual((p,s,t),old)
        self.assertEqual(len(c['records']),25)
        sources={o['endpoint_id']:o for o in self.read(self.observation+'-public-fields.json')['observations']}
        for row in c['records']:
            self.assertEqual(row['source_file'],self.observation+'-public-fields.json')
            self.assertEqual(row['source_request_ref'],sources[row['endpoint_id']]['source_request_ref'])
            self.assertEqual(row['observed_at'],sources[row['endpoint_id']]['observed_at'])
        empty=[r for r in c['records'] if r['category_ref']=='synthetic_category']
        self.assertEqual(len(empty),4)
        self.assertTrue(all(r['state']=='NOT_OBSERVED' for r in empty))

    def test_bundle_contract_csv_permissions_and_no_overwrite(self):
        export.publish_business_fields(self.root,self.observation,[self.name],self.bundle_name)
        dest=self.root/self.bundle_name
        self.assertEqual(set(p.name for p in dest.iterdir()),set(export.FILES))
        doc=self.read(self.bundle_name+'/public_codes.json')
        with (dest/'public_codes.csv').open(newline='') as stream:
            reader=csv.DictReader(stream)
            self.assertEqual(reader.fieldnames,list(export.CODE_COLUMNS))
            self.assertEqual(list(reader),[{k:export.base._cell(r[k]) for k in reader.fieldnames} for r in doc['records']])
        for change in ('wrong_value_type','wrong_endpoint','private_extra'):
            bad=copy.deepcopy(doc)
            if change=='wrong_value_type':bad['records'][0]['value']=True
            if change=='wrong_endpoint':bad['records'][0]['endpoint_id']='PRODUCTLIST'
            if change=='private_extra':bad['records'][0]['personal_cart']=True
            with self.subTest(change=change),self.assertRaises(CategoryCandidateError):_validate(bad,export.CODE_SCHEMA)
        self.assertEqual(stat.S_IMODE(dest.stat().st_mode),0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in dest.iterdir()))
        saved={p.name:p.read_bytes() for p in dest.iterdir()}
        with self.assertRaises(ResultPublishError):export.publish_business_fields(self.root,self.observation,[self.name],self.bundle_name)
        self.assertEqual(saved,{p.name:p.read_bytes() for p in dest.iterdir()})

    def test_late_write_failure_cleans_all_eleven_owned_files(self):
        original=export._write_file
        def fail(fd,name,payload):
            if name=='manifest.json':raise OSError()
            original(fd,name,payload)
        with patch.object(export,'_write_file',side_effect=fail),self.assertRaises(ResultPublishError):
            export.publish_business_fields(self.root,self.observation,[self.name],self.bundle_name)
        self.assertFalse((self.root/self.bundle_name).exists())
        self.assertTrue((self.root/self.name).exists())
