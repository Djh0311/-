import copy
import csv
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collection_adapter import p29_store_detail
from collection_adapter.p28_business_batch import analyze_public_body
from collection_adapter.p29_store_inventory import _validate
from collection_adapter import p31_detail_gap_review as review
from collection_core.result_publisher import ResultPublishError
from parser_candidate.p29_category_profile import CategoryCandidateError


def document(extra=None):
    body = {'code': 0, 'data': {
        'poi_id_str': 'synthetic-store', 'wm_poi_id': -123, 'name': 'Synthetic Store',
        'shipping_time': '10:00-14:00,17:00-21:00',
        'deliveryInfoRpc': {'deliveryType': 'SYNTHETIC_DELIVERY'},
        'delivery_info_v2': {'text': '说明', 'type': '1', 'icon': 'https://example.invalid/icon'},
        'delivery_type': 2, 'distance': '1.2km', 'map_display_range': 3, 'poi_map_type': 4,
        'latitude': 424242, 'pic_url': 'https://example.invalid/pic', 'dp_address': {},
    }}
    if extra:
        body['data'].update(extra)
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


def _keys(value, found):
    if isinstance(value, dict):
        found.update(value)
        for child in value.values():
            _keys(child, found)
    elif isinstance(value, list):
        for child in value:
            _keys(child, found)


class GapReviewTests(unittest.TestCase):
    def bundle(self, doc=None):
        doc = document() if doc is None else doc
        return review.bundle_view(doc, 'store_detail_' + 'b' * 32 + '-public-fields.json',
                                   'p31_detail_gap_' + 'c' * 32)

    def test_delivery_scalars_export_without_relabeling_hours_or_copying_excluded_values(self):
        doc = document()
        bundle = self.bundle(doc)
        row = bundle['delivery']['records'][0]
        self.assertEqual(row['delivery_service_text']['value'], 'SYNTHETIC_DELIVERY')
        self.assertEqual(row['delivery_info_type_text']['value'], '1')
        self.assertEqual(row['delivery_type_code'], {'value': '2', 'state': 'PRESENT_UNCONFIRMED'})
        self.assertEqual(row['distance_text']['value'], '1.2km')
        self.assertEqual(row['map_display_range_number']['value'], '3')
        self.assertEqual(row['map_type_code']['value'], '4')
        self.assertNotIn('opening_hours', row)
        self.assertNotIn('delivery_period', row)
        self.assertFalse(bundle['delivery']['opening_hours_filled_from_delivery_period'])
        dumped = json.dumps(bundle['delivery'])
        self.assertNotIn('10:00-14:00,17:00-21:00', dumped)
        self.assertNotIn('424242', dumped)
        self.assertNotIn('https://example.invalid', dumped)
        disposition = bundle['path_disposition']
        keys = set()
        _keys(disposition, keys)
        self.assertNotIn('value', keys)
        text = json.dumps(disposition)
        self.assertNotIn('SYNTHETIC_DELIVERY', text)
        self.assertNotIn('1.2km', text)
        self.assertNotIn('https://example.invalid', text)
        self.assertEqual(disposition['counts']['UNCLASSIFIED'], 0)
        self.assertEqual(sum(disposition['counts'].values()), len(disposition['paths']))
        by_path = {item['path']: item['disposition'] for item in disposition['paths']}
        self.assertEqual(by_path['$.data.shipping_time'], 'ALREADY_EXPORTED')
        self.assertEqual(by_path['$.data.distance'], 'DELIVERY_SCALAR_EXPORTED')
        self.assertEqual(by_path['$.data.pic_url'], 'IMAGE_OR_URL_EXCLUDED')
        self.assertEqual(by_path['$.data.latitude'], 'STORE_COORDINATE_NOT_EXPORTED')
        self.assertEqual(by_path['$.data.dp_address'], 'OBJECT_WITHOUT_PUBLIC_SCALARS')
        gaps = {item['field']: item['status'] for item in bundle['coverage']['gaps']}
        self.assertEqual(gaps['opening_hours'], 'PATH_ABSENT')
        self.assertEqual(gaps['complete_promotion_rules'], 'PATH_ABSENT')
        self.assertEqual(gaps['complete_delivery_rules'], 'PARTIAL_SOURCE_SCALARS')
        self.assertEqual(bundle['coverage']['product_result'], 'incomplete')
        _validate(bundle, review.SCHEMA)

    def test_observed_hour_or_promotion_path_stays_out_of_the_delivery_row(self):
        doc = document()
        analysis = doc['public_analysis']
        analysis['fields'].append({'path': '$.data.business_hours', 'type': 'string'})
        analysis['fields'].append({'path': '$.data.promotion_text', 'type': 'string'})
        analysis['public_values'].extend((
            {'path': '$.data.business_hours', 'coordinates': ['data', 'business_hours'],
             'value': 'SYNTHETIC_HOURS'},
            {'path': '$.data.promotion_text', 'coordinates': ['data', 'promotion_text'],
             'value': 'SYNTHETIC_PROMO'},
        ))
        bundle = self.bundle(doc)
        dumped = json.dumps(bundle['delivery'])
        self.assertNotIn('SYNTHETIC_HOURS', dumped)
        self.assertNotIn('SYNTHETIC_PROMO', dumped)
        self.assertEqual(bundle['path_disposition']['counts']['UNCLASSIFIED'], 2)
        gaps = {item['field']: item['status'] for item in bundle['coverage']['gaps']}
        self.assertEqual(gaps['opening_hours'], 'OBSERVED_NOT_EXPORTED')
        self.assertEqual(gaps['complete_promotion_rules'], 'OBSERVED_NOT_EXPORTED')
        _validate(bundle, review.SCHEMA)

    def test_duplicate_delivery_scalar_refuses(self):
        doc = document()
        values = doc['public_analysis']['public_values']
        distance = next(item for item in values if item['path'] == '$.data.distance')
        values.append(copy.deepcopy(distance))
        with self.assertRaises(CategoryCandidateError):
            self.bundle(doc)

    def test_contract_rejects_relabel_completion_and_extra_fields(self):
        original = self.bundle()
        for kind in ('extra', 'complete', 'relabel', 'hours'):
            bundle = copy.deepcopy(original)
            if kind == 'extra':
                bundle['delivery']['records'][0]['opening_hours'] = {'value': 'x', 'state': 'PRESENT_AS_OBSERVED'}
            if kind == 'complete':
                bundle['coverage']['product_result'] = 'complete'
            if kind == 'relabel':
                bundle['delivery']['opening_hours_filled_from_delivery_period'] = True
            if kind == 'hours':
                bundle['coverage']['gaps'][0]['status'] = 'PRESENT_AS_OBSERVED'
            with self.subTest(kind=kind), self.assertRaises(CategoryCandidateError):
                _validate(bundle, review.SCHEMA)


class GapPublishTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.root.chmod(0o700)
        self.detail_file = 'store_detail_' + 'b' * 32 + '-public-fields.json'
        self.result_name = 'p31_detail_gap_' + 'c' * 32
        payload = json.dumps(document()).encode()
        fd = os.open(self.root / self.detail_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as output:
            output.write(payload)
        patcher = patch('collection_adapter.p29_receiver_control._git_ignored_root', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: self._cleanup())

    def _cleanup(self):
        for path in sorted(self.root.rglob('*'), reverse=True):
            if path.is_symlink() or path.is_file():
                path.unlink()
            else:
                path.rmdir()
        self.root.rmdir()

    def test_publish_permissions_csv_and_no_overwrite(self):
        before = (self.root / self.detail_file).read_bytes()
        review.publish_detail_gap(self.root, self.detail_file, self.result_name)
        dest = self.root / self.result_name
        self.assertEqual(set(path.name for path in dest.iterdir()), set(review.FILES))
        self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in dest.iterdir()))
        bundle = {name: json.loads((dest / name).read_text()) for name in (
            'delivery.json', 'field_dictionary.json', 'path_disposition.json',
            'coverage.json', 'manifest.json')}
        _validate({key[:-5]: value for key, value in bundle.items()}, review.SCHEMA)
        with (dest / 'delivery.csv').open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(rows, [{key: review.base._cell(value) for key, value in
                                 review.csv_row(bundle['delivery.json']['records'][0]).items()}])
        with self.assertRaises(ResultPublishError):
            review.publish_detail_gap(self.root, self.detail_file, self.result_name)
        self.assertEqual(before, (self.root / self.detail_file).read_bytes())

    def test_late_failure_removes_only_new_output(self):
        before = (self.root / self.detail_file).read_bytes()
        original = review._write_file

        def fail(fd, name, data):
            if name == 'manifest.json':
                raise OSError()
            original(fd, name, data)

        with patch.object(review, '_write_file', side_effect=fail), self.assertRaises(ResultPublishError):
            review.publish_detail_gap(self.root, self.detail_file, self.result_name)
        self.assertFalse((self.root / self.result_name).exists())
        self.assertEqual(before, (self.root / self.detail_file).read_bytes())


if __name__ == '__main__':
    unittest.main()
