import copy
import csv
import stat
import unittest
from unittest.mock import patch

from collection_adapter import p31_store_promotions_export as export
from collection_adapter.tests import test_p29_store_inventory as fixtures
from collection_adapter.p29_store_inventory import _validate
from collection_core.result_publisher import ResultPublishError
from parser_candidate.p29_category_profile import CategoryCandidateError
from parser_candidate.tests.test_p31_store_promotions import promotion_bodies


class StorePromotionExportTests(unittest.TestCase):
    input = fixtures.StoreInventoryTests.input
    read = fixtures.StoreInventoryTests.read
    write = fixtures.StoreInventoryTests.write

    def setUp(self):
        with patch('collection_adapter.tests.test_p29_store_inventory.bodies', promotion_bodies):
            fixtures.StoreInventoryTests.setUp(self)
        root = patch('collection_adapter.p31_business_export._root', return_value=self.root)
        root.start(); self.addCleanup(root.stop)
        self.bundle_name = 'p31_store_promotions_' + 'b' * 32

    def test_own_source_bundle_csv_and_no_overwrite(self):
        source = next(x for x in self.read(self.observation + '-public-fields.json')['observations']
                      if x['endpoint_id'] == 'FOOD')
        before = (self.root / (self.observation + '-public-fields.json')).read_bytes()
        receipt = export.publish_store_promotions(self.root, self.observation, self.bundle_name)
        self.assertEqual(receipt['record_count'], 4)
        doc = self.read(self.bundle_name + '/records.json')
        for row in doc['records']:
            self.assertEqual(row['scope'], 'STORE_DISPLAY')
            self.assertEqual(row['source_request_ref'], source['source_request_ref'])
            self.assertEqual(row['observed_at'], source['observed_at'])
        dest = self.root / self.bundle_name
        with (dest / 'records.csv').open(newline='') as f:
            reader = csv.DictReader(f)
            self.assertEqual(reader.fieldnames, list(export.COLUMNS))
            self.assertEqual(list(reader), [{k: export.base._cell(r[k]) for k in export.COLUMNS}
                                            for r in doc['records']])
        self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in dest.iterdir()))
        saved = {p.name: p.read_bytes() for p in dest.iterdir()}
        with self.assertRaises(ResultPublishError):
            export.publish_store_promotions(self.root, self.observation, self.bundle_name)
        self.assertEqual(saved, {p.name: p.read_bytes() for p in dest.iterdir()})
        self.assertEqual(before, (self.root / (self.observation + '-public-fields.json')).read_bytes())

    def test_contract_rejects_scope_state_and_extra_values(self):
        doc = export.promotion_view(self.root, self.observation)
        for kind in ('scope', 'endpoint_id', 'state', 'extra', 'group_index'):
            bad = copy.deepcopy(doc)
            if kind == 'scope': bad['records'][0][kind] = 'SKU'
            elif kind == 'endpoint_id': bad['records'][0][kind] = 'PRODUCTLIST'
            elif kind == 'state': bad['records'][0][kind] = 'SOURCE_NULL'
            elif kind == 'group_index': bad['records'][0][kind] = None
            else: bad['records'][0]['private_extra'] = 'Synthetic'
            with self.subTest(kind=kind), self.assertRaises(CategoryCandidateError):
                _validate(bad, export.SCHEMA)

    def test_partial_write_cleanup_preserves_source(self):
        write = export._write_file
        def fail(fd, name, content):
            if name == 'manifest.json': raise OSError()
            write(fd, name, content)
        with patch.object(export, '_write_file', side_effect=fail), self.assertRaises(ResultPublishError):
            export.publish_store_promotions(self.root, self.observation, self.bundle_name)
        self.assertFalse((self.root / self.bundle_name).exists())
        self.assertTrue((self.root / (self.observation + '-public-fields.json')).exists())
