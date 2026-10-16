import contextlib
import copy
import csv
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from collection_adapter.p29_category_export import CSV_FIELDS, main, publish_category_candidates
from collection_adapter.tests.test_p29_category_review import analysis, synthetic_body
from collection_core.result_publisher import ResultPublishError, _manifest_from_views
from parser_candidate.p29_category_profile import CategoryCandidateError


class CategoryExportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.root.chmod(0o700)
        self.window = 'result:' + 'b' * 32
        self.result_name = 'category_candidates_' + 'e' * 32
        self.write('transport-state.json', {'output_root': str(self.root)})
        self.write('result-attempt-' + 'b' * 32 + '.lock',
                   {'schema_version': 'p26-attempt-reservation/v1', 'window_ref': self.window})
        for module in ('p29_category_export', 'p29_category_review'):
            p = patch('collection_adapter.' + module + '._root', return_value=self.root)
            p.start(); self.addCleanup(p.stop)
        self.name = self.input('a', 'c', '2026-01-01T00:01:00+00:00')

    def write(self, name, document):
        p = self.root / name; p.write_text(json.dumps(document)); p.chmod(0o600)

    def read(self, name):
        return json.loads((self.root / name).read_text())

    def test_numeric_identity_versions_keep_distinct_string_proofs_through_export(self):
        for version, basis in (('v3', 'CURRENT_PAIR_REQUEST_STRINGS'),
                               ('v4', 'CURRENT_RESPONSE_PUBLIC_STRING')):
            with self.subTest(version=version):
                document = self.read(self.name)
                document.update(schema_version='p29-category-render-inspection/' + version,
                    store_context_identity_basis='CURRENT_RESPONSE_NUMERIC_ID_MATCHES_BOTH_REQUESTS',
                    string_context_basis=basis)
                self.write(self.name, document)
                from collection_adapter.p29_category_export import _view
                view, _, _ = _view(self.root, [self.name])
                self.assertEqual(view['record_count'], 2)
                self.assertFalse(view['can_publish_complete_result'])
                self.assertFalse(view['cross_observation_fields_copied'])
                # A version cannot borrow the other's identity assertion.
                document['string_context_basis'] = (
                    'CURRENT_PAIR_REQUEST_STRINGS' if version == 'v4'
                    else 'CURRENT_RESPONSE_PUBLIC_STRING')
                self.write(self.name, document)
                with self.assertRaises(CategoryCandidateError):
                    _view(self.root, [self.name])

    def input(self, file_letter, request_letter, observed_at, body=None):
        name = 'category_render_' + file_letter * 32 + '-public-fields.json'
        document = {
            'schema_version': 'p29-category-render-inspection/v2', 'window_ref': self.window,
            'source_request_ref': 'request:' + request_letter * 32,
            'route': '/weapp/poi/food/render', 'observed_at': observed_at,
            'source_context_result_name': 'observation_' + 'd' * 32,
            'source_context_observed_at': '2026-01-01T00:00:00+00:00',
            'request_field_keys': ['poi_id_str', 'wm_poi_id', 'tag_spu_ids'],
            'shop_scope_verified': True, 'poi_id_str_matches_context': True,
            'wm_poi_id_matches_context': True, 'source_context_age_within_10_seconds': False,
            'same_observation_record_ready': False, 'payload_family': 'UNKNOWN',
            'payload_version': 'UNKNOWN', 'business_record_count': 0, 'coverage_status': 'PARTIAL',
            'response_code_status': 'ZERO', 'public_analysis': analysis(body),
            'raw_payload_persisted': False, 'sensitive_values_processed': False,
        }
        relation = {
            'profile_version': 'p29-observed-batch-array-v1', 'status': 'MATCHED_CURRENT_RESPONSE',
            'item_count': 1, 'request_membership_count': 1, 'matching_tag_membership_count': 1,
            'matching_child_tag_membership_count': 0, 'request_memberships_not_in_response': 0,
            'response_memberships_not_in_request': 0, 'duplicate_request_memberships': 0,
            'tag_type_semantics': 'UNCONFIRMED', 'child_tag_semantics': 'UNCONFIRMED',
        }
        fields = [('$', 'array', 0), ('$[]', 'object', 0), ('$[].childTagId', 'string', 1),
                  ('$[].spuId', 'number', 1), ('$[].tagId', 'string', 1), ('$[].tagType', 'number', 1)]
        probe = {'schema_version': 'p29-category-batch-parameter-probe/v2',
            **{k: document[k] for k in ('window_ref', 'source_request_ref', 'observed_at',
                                      'route', 'source_context_result_name')},
            'probe': {'key': 'tag_spu_ids', 'status': 'STRUCTURE_OBSERVED', 'root_kind': 'ARRAY',
                'fields': [{'path': p, 'type': t, 'public_scalar_count': n} for p, t, n in fields],
                'public_scalar_count': 4, 'response_category_count': 1, 'response_product_count': 1,
                'response_category_product_membership_count': 1, 'matching_category_id_count': 1,
                'matching_product_id_count': 1, 'matching_memberships_by_ancestor_key_count': 0,
                'array_item_relation': relation, 'unmatched_public_scalar_count': 2,
                'private_key_category_counts': {k: 0 for k in ('CREDENTIAL_KEY', 'SESSION_KEY',
                    'PERSONAL_KEY', 'TRANSPORT_KEY', 'UNCLASSIFIED_KEY')},
                'parameter_role': 'UNKNOWN', 'grammar_qualified': False,
                'termination_semantics': 'UNCONFIRMED', 'same_observation_record_ready': False,
                'can_publish_complete_result': False, 'parameter_values_persisted': False,
                'business_values_in_report': False, 'sensitive_values_processed': False,
                'raw_payload_persisted': False}}
        self.write(name, document)
        self.write(name.replace('-public-fields.json', '-batch-parameter.json'), probe)
        return name

    def publish(self, names=None):
        return publish_category_candidates(self.root, names or [self.name], self.result_name)

    def test_json_csv_manifest_keep_unknowns_empty_and_missing_states(self):
        result = self.publish(); destination = self.root / result['result_name']
        view = self.read(result['result_name'] + '/records.json')
        manifest = self.read(result['result_name'] + '/manifest.json')
        rows = view['records']
        self.assertEqual([r['sku_price_number'] for r in rows], ['1.25', '2.75'])
        self.assertEqual((rows[0]['sku_spec'], rows[0]['sku_spec_state']), ('', 'SOURCE_EMPTY'))
        self.assertEqual((rows[0]['sku_description'], rows[0]['sku_description_state']), (None, 'NOT_OBSERVED'))
        self.assertEqual((rows[1]['sku_origin_number'], rows[1]['sku_origin_number_state']), (None, 'NOT_OBSERVED'))
        self.assertTrue(all(r['currency'] == r['amount_unit'] == 'UNKNOWN' for r in rows))
        self.assertFalse(view['can_publish_complete_result'])
        with (destination / 'records.csv').open(newline='') as stream:
            reader = csv.DictReader(stream); csvrows = list(reader)
            self.assertEqual(tuple(reader.fieldnames), CSV_FIELDS)
        self.assertEqual(csvrows, [{k: '' if v is None else v for k, v in r.items()} for r in rows])
        for key in view:
            if key not in ('schema_version', 'records'): self.assertEqual(manifest[key], view[key])
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in destination.iterdir()))
        with self.assertRaises(ResultPublishError): _manifest_from_views(view, 'complete_result')

    def test_latest_whole_candidate_preserves_older_unrepeated_sku_without_borrowing(self):
        body = synthetic_body(); product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        product['name'] = 'Synthetic later product'; product.pop('unit')
        product['min_price'] = 1.75; product['render_info']['price_info']['min_price'] = 1.75
        product['skus'] = [{'id': 201, 'price': 1.75}]
        later = self.input('f', '9', '2026-01-01T00:02:00+00:00', body)
        self.publish([later, self.name])
        view = self.read(self.result_name + '/records.json')
        a, b = view['records']
        self.assertEqual((a['sku_id'], a['source_file'], a['sku_price_number']), ('201', later, '1.75'))
        self.assertEqual((a['product_unit'], a['product_unit_state']), (None, 'NOT_OBSERVED'))
        self.assertEqual((b['sku_id'], b['source_file'], b['sku_price_number']), ('202', self.name, '2.75'))
        self.assertEqual(view['deduplicated_candidate_rows'], 1)
        self.assertFalse(view['cross_observation_fields_copied'])

    def test_same_sku_in_another_category_retains_both_memberships(self):
        body = synthetic_body(); body['data']['food_spu_tags'][0]['tag'] = 'synthetic_second_category'
        other = self.input('f', '9', '2026-01-01T00:02:00+00:00', body)
        result = self.publish([self.name, other])
        self.assertEqual((result['record_count'], result['sku_count'], result['category_count']), (4, 2, 2))

    def test_bad_or_mismatched_proof_rejects_before_destination_exists(self):
        probe_name = self.name.replace('-public-fields.json', '-batch-parameter.json')
        original = self.read(probe_name)
        for change in ('request', 'time', 'window', 'context', 'status', 'extra', 'missing',
                       'duplicate', 'count', 'private', 'probe_status', 'root_kind', 'fields', 'scalars'):
            probe = copy.deepcopy(original); relation = probe['probe']['array_item_relation']
            if change == 'request': probe['source_request_ref'] = 'request:' + '1' * 32
            elif change == 'time': probe['observed_at'] = '2026-01-01T00:02:00+00:00'
            elif change == 'window': probe['window_ref'] = 'result:' + '1' * 32
            elif change == 'context': probe['source_context_result_name'] = 'observation_' + '1' * 32
            elif change == 'status': relation['status'] = 'MEMBERSHIPS_DIFFER'
            elif change == 'extra': relation['request_memberships_not_in_response'] = 1
            elif change == 'missing': relation['response_memberships_not_in_request'] = 1
            elif change == 'duplicate': relation['duplicate_request_memberships'] = 1
            elif change == 'count': relation['request_membership_count'] = 2
            elif change == 'probe_status': probe['probe']['status'] = 'ABSENT'
            elif change == 'root_kind': probe['probe']['root_kind'] = 'OBJECT'
            elif change == 'fields': probe['probe']['fields'] = []
            elif change == 'scalars': probe['probe']['public_scalar_count'] = 0
            else: probe['probe']['sensitive_values_processed'] = True
            self.write(probe_name, probe)
            with self.subTest(change=change), self.assertRaises(CategoryCandidateError): self.publish()
            self.assertFalse((self.root / self.result_name).exists())

    def test_legacy_absent_and_unsuccessful_response_do_not_export(self):
        original = self.read(self.name)
        for change in ('legacy', 'nonzero', 'missing_probe'):
            document = copy.deepcopy(original)
            if change == 'legacy':
                document['schema_version'] = 'p29-category-render-inspection/v1'
                document.pop('response_code_status')
            elif change == 'nonzero': document['response_code_status'] = 'NONZERO'
            else: (self.root / self.name.replace('-public-fields.json', '-batch-parameter.json')).unlink()
            self.write(self.name, document)
            with self.subTest(change=change), self.assertRaises((CategoryCandidateError, ValueError)): self.publish()
            self.assertFalse((self.root / self.result_name).exists())

    def test_inconsistent_product_minimum_does_not_export(self):
        body = synthetic_body(); body['data']['food_spu_tags'][0]['dynamic_spus'][0]['min_price'] = 1.5
        self.input('a', 'c', '2026-01-01T00:01:00+00:00', body)
        with self.assertRaises(CategoryCandidateError) as caught: self.publish()
        self.assertEqual(caught.exception.code, 'P29_CATEGORY_EXPORT_PRICE_RELATION_INVALID')
        self.assertFalse((self.root / self.result_name).exists())

    def test_existing_destination_and_symlink_are_never_changed(self):
        previous = self.root / self.result_name; previous.mkdir(mode=0o700)
        sentinel = previous / 'keep'; sentinel.write_bytes(b'synthetic existing output')
        with self.assertRaises(ResultPublishError): self.publish(['not-an-input'])
        self.assertEqual(sentinel.read_bytes(), b'synthetic existing output')
        previous.rename(self.root / 'previous')
        previous.symlink_to(self.root / 'previous', target_is_directory=True)
        with self.assertRaises(ResultPublishError): self.publish()
        self.assertEqual((self.root / 'previous' / 'keep').read_bytes(), b'synthetic existing output')

    def test_publish_failure_cleans_only_current_exclusive_directory(self):
        previous = self.root / 'previous'; previous.mkdir(mode=0o700)
        sentinel = previous / 'records.json'; sentinel.write_bytes(b'synthetic previous result')
        from collection_adapter.p29_category_export import _write_file
        def write(directory_fd, name, payload):
            if name == 'manifest.json': raise OSError('synthetic private failure')
            return _write_file(directory_fd, name, payload)
        with patch('collection_adapter.p29_category_export._write_file', side_effect=write), self.assertRaises(ResultPublishError) as caught:
            self.publish()
        self.assertEqual(str(caught.exception), 'RESULT_PUBLISH_FAILED')
        self.assertFalse((self.root / self.result_name).exists())
        self.assertEqual(sentinel.read_bytes(), b'synthetic previous result')

    def test_budget_and_unsafe_root_refused_without_new_attempt(self):
        attempt = (self.root / ('result-attempt-' + 'b' * 32 + '.lock')).read_bytes()
        with patch('collection_adapter.p29_category_export.MAX_COLLECTION_BYTES', 1), self.assertRaises(CategoryCandidateError): self.publish()
        self.assertFalse((self.root / self.result_name).exists())
        self.root.chmod(0o755)
        with self.assertRaises(ResultPublishError): self.publish()
        self.assertEqual((self.root / ('result-attempt-' + 'b' * 32 + '.lock')).read_bytes(), attempt)

    def test_cli_counts_only_private_values_stay_opaque_and_closed_schema_rejects_promotion(self):
        body = synthetic_body(); body['data']['session'] = {'cookie': 'synthetic private sentinel'}
        self.input('a', 'c', '2026-01-01T00:01:00+00:00', body)
        before = (self.root / ('result-attempt-' + 'b' * 32 + '.lock')).read_bytes()
        stream = io.StringIO()
        with patch('sys.argv', ['export', '--output-root', str(self.root), '--input-name', self.name,
                                '--result-name', self.result_name]), contextlib.redirect_stdout(stream):
            self.assertEqual(main(), 0)
        result = json.loads(stream.getvalue()); self.assertEqual(result['live_attempts_consumed'], 0)
        self.assertNotIn('Synthetic render product', stream.getvalue())
        view = self.read(self.result_name + '/records.json')
        self.assertNotIn('synthetic private sentinel', json.dumps(view))
        self.assertEqual((self.root / ('result-attempt-' + 'b' * 32 + '.lock')).read_bytes(), before)
        schemas = Path(__file__).resolve().parents[2] / 'contracts/schemas'
        validator = Draft202012Validator(json.loads((schemas / 'p29-category-candidate-result-v1.schema.json').read_text()))
        self.assertTrue(validator.is_valid(view))
        for key, value in [('can_publish_complete_result', True), ('coverage_status', 'COMPLETE')]:
            changed = copy.deepcopy(view); changed[key] = value
            self.assertFalse(validator.is_valid(changed))
        changed = copy.deepcopy(view); changed['records'][0]['currency'] = 'CNY'
        self.assertFalse(validator.is_valid(changed))


if __name__ == '__main__':
    unittest.main()
