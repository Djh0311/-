import copy
import csv
import json
import stat
import unittest
from unittest.mock import patch

from collection_adapter import p29_store_detail
from collection_adapter.p28_business_batch import analyze_public_body
from collection_adapter.p29_store_inventory import _validate
from collection_adapter import p31_store_detail_export as export
from collection_adapter.tests import test_p31_context_codes_export as existing
from collection_adapter import p31_context_codes_export as previous
from parser_candidate.p29_category_profile import CategoryCandidateError
from collection_core.result_publisher import ResultPublishError


def detail_document():
    body = {'code': 0, 'data': {
        'poi_id_str': 'synthetic-store', 'wm_poi_id': -123,
        'name': 'Synthetic Store', 'address': 'Synthetic address',
        'shipping_time': '10:00-20:00', 'bulletin': '',
        'phone_list': ['000-0000', None],
        'poi_service_info': [{'content': 'Synthetic service'}],
        'poi_attribute_tags': [], 'delivery_tip': None,
    }}
    return {
        'schema_version': 'p29-store-detail-public-copy/v1',
        'window_ref': 'result:' + 'a' * 32, 'route': p29_store_detail.DETAIL_ROUTE,
        'route_slot': 7, 'observed_at': '2026-10-14T17:00:00Z',
        'page_scope': 'CURRENT_USER_SELECTED_STORE_PAGE',
        'store_identity_verified': False, 'business_record_count': 0,
        'response_code_status': 'ZERO',
        'public_analysis': analyze_public_body(json.dumps(body).encode()),
        'raw_payload_persisted': False, 'sensitive_values_processed': False,
    }


class DetailViewTests(unittest.TestCase):
    def test_public_detail_can_be_exported_without_turning_delivery_into_opening_hours(self):
        # Existing capture saves a projection, but has no business-table conversion.
        from collection_adapter import p31_store_detail_export as export
        doc = detail_document()
        store = export.detail_record(doc, 'store_detail_' + 'b' * 32 + '-public-fields.json')
        self.assertIn('delivery_period', store)
        self.assertEqual(store['delivery_period']['value'], '10:00-20:00')
        self.assertNotIn('opening_hours', store)
        self.assertEqual(store['address']['value'], 'Synthetic address')
        self.assertEqual(store['bulletin']['state'], 'SOURCE_EMPTY')
        self.assertEqual(store['delivery_tip']['state'], 'SOURCE_NULL')
        self.assertEqual(store['delivery_description']['state'], 'NOT_OBSERVED')
        self.assertEqual(store['tags']['state'], 'SOURCE_EMPTY')
        self.assertEqual(store['phones']['items'][1]['state'], 'SOURCE_NULL')
        self.assertEqual(store['phones']['items'][1]['index'], 1)
        self.assertEqual(doc['business_record_count'], 0)

    def test_duplicate_wrong_coordinate_and_scalar_type_refuse(self):
        for kind in ('duplicate', 'coordinate', 'type', 'unsuccessful'):
            doc = detail_document()
            values = doc['public_analysis']['public_values']
            address = next(v for v in values if v['path'] == '$.data.address')
            if kind == 'duplicate':
                values.append(copy.deepcopy(address))
            elif kind == 'coordinate':
                address['coordinates'] = ['data', 'name']
            elif kind == 'type':
                address['value'] = 42
            else:
                doc['response_code_status'] = 'NONZERO'
            with self.subTest(kind=kind), self.assertRaises(CategoryCandidateError):
                export.detail_record(doc, 'store_detail_' + 'b' * 32 + '-public-fields.json')

    def test_rejected_text_is_not_reported_as_absent_and_arrays_keep_indices(self):
        doc = detail_document()
        body = {'data': {'poi_id_str': 'synthetic-store', 'wm_poi_id': -123,
                        'name': 'Synthetic', 'address': 'Synthetic\naddress',
                        'phone_list': ['000-0000', 'Synthetic\nphone', '000-0002']}}
        doc['public_analysis'] = analyze_public_body(json.dumps(body).encode())
        result = export.detail_record(doc, 'store_detail_' + 'b' * 32 + '-public-fields.json')
        self.assertEqual(result['address'], {'value': None, 'state': 'SOURCE_REJECTED'})
        self.assertEqual(result['phones']['state'], 'PARTIAL_REJECTED')
        self.assertEqual([x['index'] for x in result['phones']['items']], [0, 2])


class DetailBundleTests(unittest.TestCase):
    setUpFixture = existing.ContextCodesExportTests.setUpFixture
    input = existing.ContextCodesExportTests.input
    read = existing.ContextCodesExportTests.read
    write = existing.ContextCodesExportTests.write

    def setUp(self):
        existing.ContextCodesExportTests.setUp(self)
        previous.publish_business_fields(self.root, self.observation, [self.name], self.bundle_name)
        patcher = patch('collection_adapter.p29_receiver_control._git_ignored_root', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.detail_file = 'store_detail_' + 'b' * 32 + '-public-fields.json'
        doc = detail_document()
        store = self.read(self.bundle_name + '/stores.json')['records'][0]
        for v in doc['public_analysis']['public_values']:
            if v['path'] == '$.data.poi_id_str': v['value'] = store['store_id']
            if v['path'] == '$.data.wm_poi_id': v['value'] = int(store['store_numeric_id_number'])
            if v['path'] == '$.data.name': v['value'] = store['store_name']
        self.write(self.detail_file, doc)
        self.result_name = 'p31_store_detail_' + 'c' * 32

    def publish(self):
        return export.publish_store_detail(self.root, self.detail_file, self.root,
                                           self.bundle_name, self.result_name)

    def view(self):
        return export.bundle_view(self.root, self.detail_file, self.root,
                                  self.bundle_name, self.result_name)

    def test_bundle_contract_csv_provenance_permissions_and_no_overwrite(self):
        originals = {p: p.read_bytes() for p in (self.root / self.bundle_name).iterdir()}
        originals[self.root / self.detail_file] = (self.root / self.detail_file).read_bytes()
        bundle = self.view()
        self.assertTrue(bundle['association']['numeric_id_match'])
        self.assertFalse(bundle['association']['values_are_same_observation'])
        self.assertNotEqual(bundle['association']['product_window_ref'],
                            bundle['association']['detail_window_ref'])
        self.publish()
        dest = self.root / self.result_name
        self.assertEqual(set(p.name for p in dest.iterdir()), set(export.FILES))
        self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in dest.iterdir()))
        reconstructed = {k: self.read(self.result_name + '/' + k + '.json') for k in bundle}
        _validate(reconstructed, export.SCHEMA)
        self.assertEqual(reconstructed, bundle)
        with (dest / 'stores.csv').open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(rows, [{k: export.base._cell(v) for k, v in
            export.csv_row(bundle['stores']['records'][0]).items()}])
        with self.assertRaises(ResultPublishError): self.publish()
        self.assertTrue(all(p.read_bytes() == data for p, data in originals.items()))

    def test_same_name_does_not_override_wrong_or_missing_id(self):
        original = self.read(self.detail_file)
        for kind in ('string', 'numeric', 'missing'):
            doc = copy.deepcopy(original)
            values = doc['public_analysis']['public_values']
            for v in values:
                if kind == 'string' and v['path'] == '$.data.poi_id_str': v['value'] = 'other-store'
                if kind == 'numeric' and v['path'] == '$.data.wm_poi_id': v['value'] = 999
            if kind == 'missing':
                doc['public_analysis']['public_values'] = [v for v in values if v['path'] != '$.data.poi_id_str']
            self.write(self.detail_file, doc)
            with self.subTest(kind=kind), self.assertRaises(CategoryCandidateError): self.publish()
            self.assertFalse((self.root / self.result_name).exists())

    def test_product_count_and_window_mismatch_refuse_output(self):
        filename = self.bundle_name + '/records.json'
        original = self.read(filename)
        for kind in ('count', 'window'):
            doc = copy.deepcopy(original)
            if kind == 'count': doc['record_count'] += 1
            else: doc['records'][0]['window_ref'] = 'result:' + '9' * 32
            self.write(filename, doc)
            with self.subTest(kind=kind), self.assertRaises(CategoryCandidateError): self.publish()
            self.assertFalse((self.root / self.result_name).exists())

    def test_contract_rejects_extra_fields_and_unjustified_completion(self):
        original = self.view()
        for kind in ('extra', 'complete', 'same_time', 'null_state'):
            bundle = copy.deepcopy(original)
            if kind == 'extra': bundle['stores']['records'][0]['extra'] = 'Synthetic'
            if kind == 'complete': bundle['coverage']['product_result'] = 'complete'
            if kind == 'same_time': bundle['association']['values_are_same_observation'] = True
            if kind == 'null_state': bundle['stores']['records'][0]['address']['state'] = 'SOURCE_NULL'
            with self.subTest(kind=kind), self.assertRaises(CategoryCandidateError):
                _validate(bundle, export.SCHEMA)

    def test_late_failure_removes_only_new_output(self):
        before = (self.root / self.detail_file).read_bytes()
        original = export._write_file
        def fail(fd, name, data):
            if name == 'manifest.json': raise OSError()
            original(fd, name, data)
        with patch.object(export, '_write_file', side_effect=fail), self.assertRaises(ResultPublishError):
            self.publish()
        self.assertFalse((self.root / self.result_name).exists())
        self.assertEqual(before, (self.root / self.detail_file).read_bytes())
        self.assertTrue((self.root / self.bundle_name / 'manifest.json').is_file())

    def test_unowned_or_symlinked_input_refuses(self):
        path = self.root / self.detail_file
        path.chmod(0o644)
        with self.assertRaises(ValueError): self.publish()
        path.chmod(0o600)
        moved = path.with_name('synthetic-source.json')
        path.rename(moved)
        path.symlink_to(moved)
        with self.assertRaises(OSError): self.publish()
        self.assertFalse((self.root / self.result_name).exists())


if __name__ == '__main__':
    unittest.main()
