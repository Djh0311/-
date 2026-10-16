import copy
import csv
import stat
import unittest
from unittest.mock import patch

from collection_adapter import p31_context_export as export
from collection_adapter import p31_remaining_export as previous
from collection_adapter.tests import test_p29_store_inventory as fixtures
from collection_adapter.p29_store_inventory import _validate
from collection_core.result_publisher import ResultPublishError
from parser_candidate.p29_category_profile import CategoryCandidateError
from parser_candidate.tests.test_p31_context_fields import context_bodies


class ContextExportTests(unittest.TestCase):
    setUpFixture = fixtures.StoreInventoryTests.setUp
    input = fixtures.StoreInventoryTests.input
    read = fixtures.StoreInventoryTests.read
    write = fixtures.StoreInventoryTests.write

    def setUp(self):
        with patch('collection_adapter.tests.test_p29_store_inventory.bodies', context_bodies):
            self.setUpFixture()
        root = patch('collection_adapter.p31_business_export._root', return_value=self.root)
        root.start(); self.addCleanup(root.stop)
        self.bundle_name = 'p31_context_fields_' + 'e' * 32

    def test_texts_keep_initial_endpoint_and_category_ownership(self):
        old = previous.business_view(self.root, self.observation, [self.name])
        products, stores, texts = export.business_view(self.root, self.observation, [self.name])
        self.assertEqual((products, stores), old)
        self.assertEqual(len(texts['records']), 18)
        original = self.read(self.observation + '-public-fields.json')
        refs = {o['endpoint_id']: o for o in original['observations']}
        for row in texts['records']:
            self.assertEqual(row['source_file'], self.observation + '-public-fields.json')
            self.assertEqual(row['source_request_ref'], refs[row['endpoint_id']]['source_request_ref'])
            self.assertEqual(row['observed_at'], refs[row['endpoint_id']]['observed_at'])
        categories = [r for r in texts['records'] if r['category_ref'] == 'synthetic_category']
        self.assertEqual(len(categories), 5)
        self.assertTrue(all(r['state'] == 'NOT_OBSERVED' for r in categories))

    def test_nine_file_bundle_csv_contract_and_existing_destination(self):
        export.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        dest = self.root / self.bundle_name
        self.assertEqual(set(p.name for p in dest.iterdir()), set(export.FILES))
        texts = self.read(self.bundle_name + '/public_texts.json')
        dictionary = self.read(self.bundle_name + '/field_dictionary.json')
        with (dest/'public_texts.csv').open(newline='') as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames, [d['field'] for d in dictionary['fields'] if d['table']=='public_texts'])
            self.assertEqual(list(reader), [{k: previous.base._cell(r[k]) for k in reader.fieldnames} for r in texts['records']])
        bad = copy.deepcopy(texts); bad['records'][0]['private_extra'] = 'Synthetic'
        with self.assertRaises(CategoryCandidateError): _validate(bad, export.TEXT_SCHEMA)
        bad = copy.deepcopy(texts); bad['records'][0]['endpoint_id'] = 'PRODUCTLIST'
        with self.assertRaises(CategoryCandidateError): _validate(bad, export.TEXT_SCHEMA)
        bad = copy.deepcopy(texts); bad['records'][0]['state'] = 'SOURCE_NULL'
        with self.assertRaises(CategoryCandidateError): _validate(bad, export.TEXT_SCHEMA)
        self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in dest.iterdir()))
        saved = {p.name:p.read_bytes() for p in dest.iterdir()}
        with self.assertRaises(ResultPublishError):
            export.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        self.assertEqual(saved, {p.name:p.read_bytes() for p in dest.iterdir()})

    def test_late_write_failure_removes_all_nine_owned_files(self):
        original = export._write_file
        def fail(fd, name, payload):
            if name == 'manifest.json': raise OSError()
            original(fd, name, payload)
        with patch.object(export, '_write_file', side_effect=fail), self.assertRaises(ResultPublishError):
            export.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        self.assertFalse((self.root/self.bundle_name).exists())
        self.assertTrue((self.root/self.name).exists())
