import copy
import csv
import json
import stat
import unittest
from unittest.mock import patch

from collection_adapter import p31_additional_export as export
from collection_adapter import p31_business_export as base
from collection_adapter.tests import test_p29_store_inventory as fixtures
from collection_adapter.tests.test_p28_business_batch import bodies
from collection_adapter.tests.test_p29_category_review import synthetic_body
from collection_adapter.p29_store_inventory import _validate
from collection_core.result_publisher import ResultPublishError
from parser_candidate.p29_category_profile import CategoryCandidateError
from parser_candidate.tests.test_p31_additional_fields import additional_body


def extended_bodies():
    food, _ = bodies()
    food['data']['poi_info'].update(brand_id=9, poi_label={'labels': [{'label_text': 'Synthetic 服务'}]})
    return food, additional_body()


class AdditionalExportTests(unittest.TestCase):
    setUpFixture = fixtures.StoreInventoryTests.setUp
    input = fixtures.StoreInventoryTests.input
    read = fixtures.StoreInventoryTests.read
    write = fixtures.StoreInventoryTests.write

    def setUp(self):
        with patch('collection_adapter.tests.test_p29_store_inventory.bodies', extended_bodies):
            self.setUpFixture()
        root_patch = patch('collection_adapter.p31_business_export._root', return_value=self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.bundle_name = 'p31_additional_fields_' + 'f' * 32

    def test_own_additional_fields_reach_export(self):
        products, stores = export.business_view(self.root, self.observation, [self.name])
        row = next(r for r in products['records'] if r['source_kind'] == 'CHECKED_INITIAL_PAIR')
        self.assertEqual(row.get('product_group_id_number'), '88')
        self.assertEqual(stores['records'][0]['store_label_texts'][0]['value'], 'Synthetic 服务')

    def test_v_two_preserves_all_old_fields_and_csv_dictionary_contracts(self):
        before, old_stores = base.business_view(self.root, self.observation, [self.name])
        export.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        destination = self.root / self.bundle_name
        products = self.read(self.bundle_name + '/records.json')
        stores = self.read(self.bundle_name + '/stores.json')
        self.assertEqual(products['schema_version'], 'p31-business-products/v2')
        for old, row in zip(before['records'] + old_stores['records'], products['records'] + stores['records']):
            self.assertEqual({k: row[k] for k in old}, old)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in destination.iterdir()))
        dictionary = self.read(self.bundle_name + '/field_dictionary.json')
        for table, doc, filename in [('products', products, 'records.csv'), ('stores', stores, 'stores.csv')]:
            with (destination / filename).open(newline='') as stream:
                reader = csv.DictReader(stream)
                self.assertEqual([x['field'] for x in dictionary['fields'] if x['table'] == table], reader.fieldnames)
                self.assertEqual(list(reader), [{k: base._cell(r[k]) for k in reader.fieldnames} for r in doc['records']])
        coverage = self.read(self.bundle_name + '/coverage.json')
        self.assertTrue(all(sum(f['states'].values()) == f['row_count'] for f in coverage['fields']))
        bad = copy.deepcopy(products)
        bad['records'][0]['product_ctime_number'] = '2026-01-01'
        with self.assertRaises(CategoryCandidateError): _validate(bad, export.PRODUCT_SCHEMA)
        bad = copy.deepcopy(products)
        bad['records'][0]['sku_promotion_tag_texts'][0]['unsafe'] = 'x'
        with self.assertRaises(CategoryCandidateError): _validate(bad, export.PRODUCT_SCHEMA)
        saved = {p.name: p.read_bytes() for p in destination.iterdir()}
        with self.assertRaises(ResultPublishError):
            export.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        self.assertEqual(saved, {p.name: p.read_bytes() for p in destination.iterdir()})

    def test_equal_time_additional_conflicts_are_rejected(self):
        body = synthetic_body()
        p = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        p['group_id'] = 10
        first = self.input('a', 'c', '2026-01-01T00:01:00+00:00', body)
        p['group_id'] = 20
        second = self.input('b', 'd', '2026-01-01T00:01:00+00:00', body)
        with self.assertRaises(CategoryCandidateError) as raised:
            export.business_view(self.root, self.observation, [first, second])
        self.assertEqual(raised.exception.code, 'P31_EXPORT_EQUAL_TIME_FIELDS_CONFLICT')

    def test_newer_missing_fields_do_not_borrow_from_older_source(self):
        body = synthetic_body()
        p = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        p['group_id'] = 10
        first = self.input('a', 'c', '2026-01-01T00:01:00+00:00', body)
        del p['group_id']
        second = self.input('b', 'd', '2026-01-01T00:02:00+00:00', body)
        products, _ = export.business_view(self.root, self.observation, [first, second])
        rows = [r for r in products['records'] if r['source_kind'] != 'CHECKED_INITIAL_PAIR']
        self.assertTrue(rows)
        self.assertTrue(all(r['product_group_id_number'] is None and r['product_group_id_number_state'] == 'NOT_OBSERVED' for r in rows))

    def test_budget_and_partial_write_fail_closed(self):
        with patch.object(export, 'MAX_COLLECTION_BYTES', 1), self.assertRaises(CategoryCandidateError):
            export.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        self.assertFalse((self.root / self.bundle_name).exists())
        original = export._write_file
        def fail(fd, filename, content):
            if filename == 'stores.csv': raise OSError()
            original(fd, filename, content)
        with patch.object(export, '_write_file', side_effect=fail), self.assertRaises(ResultPublishError):
            export.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        self.assertFalse((self.root / self.bundle_name).exists())
