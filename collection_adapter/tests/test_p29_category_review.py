import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource

from collection_adapter.p28_business_batch import analyze_public_body
from collection_adapter.p29_category_review import main, review_category_batch, review_category_inventory
from collection_core.result_publisher import _manifest_from_views, ResultPublishError
from parser_candidate.p29_category_profile import (CategoryCandidateError,
    parse_category_public_values)


def synthetic_body():
    return {'code': 0, 'data': {'food_spu_tags': [{'tag': 'synthetic_category',
        'dynamic_spus': [{'id': 101, 'name': 'Synthetic render product', 'unit': 'Synthetic unit',
            'min_price': 1.25, 'render_info': {'price_info': {'min_price': 1.25}},
            'skus': [{'id': 201, 'price': 1.25, 'spec': '', 'spec_desc': None, 'origin_price': 2},
                     {'id': 202, 'price': 2.75, 'spec': 'Synthetic larger'}]}]}]}}


def analysis(body=None):
    return analyze_public_body(json.dumps(body if body is not None else synthetic_body()).encode())


class CategoryReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.root.chmod(0o700)
        self.name = 'category_render_' + 'a' * 32 + '-public-fields.json'
        self.ref = 'result:' + 'b' * 32

    def write(self, name, document):
        p = self.root / name
        p.write_text(json.dumps(document)); p.chmod(0o600)
        return p

    def document(self):
        return {'schema_version': 'p29-category-render-inspection/v1', 'window_ref': self.ref,
            'source_request_ref': 'request:' + 'c' * 32, 'route': '/weapp/poi/food/render',
            'observed_at': '2026-01-01T00:01:00+00:00',
            'source_context_result_name': 'observation_' + 'd' * 32,
            'source_context_observed_at': '2026-01-01T00:00:00+00:00',
            'request_field_keys': ['poi_id_str', 'wm_poi_id'],
            'shop_scope_verified': True, 'poi_id_str_matches_context': True,
            'wm_poi_id_matches_context': True, 'source_context_age_within_10_seconds': False,
            'same_observation_record_ready': False, 'payload_family': 'UNKNOWN',
            'payload_version': 'UNKNOWN', 'business_record_count': 0, 'coverage_status': 'PARTIAL',
            'public_analysis': analysis(), 'raw_payload_persisted': False,
            'sensitive_values_processed': False}

    def prepare_input(self, doc=None):
        self.write(self.name, doc or self.document())
        self.write('transport-state.json', {'output_root': str(self.root)})
        self.write('result-attempt-' + 'b' * 32 + '.lock',
                   {'schema_version': 'p26-attempt-reservation/v1', 'window_ref': self.ref})

    def review(self):
        with patch('collection_adapter.p29_category_review._root', return_value=self.root), \
             patch('collection_adapter.p29_receiver_control._root', return_value=self.root):
            return review_category_inventory(self.root, self.name)

    def forwarded_input(self):
        self.prepare_input()
        (self.root / ('result-attempt-' + 'b' * 32 + '.lock')).unlink()
        self.write('transport-state.json', {'output_root': str(self.root), 'result_attempts': 1})
        self.write('receiver-process.json', {'schema_version': 'p29-owned-receiver-process/v1',
            'input_mode': 'FORWARDED_COPY', 'output_root': str(self.root)})
        return {'event': 'P29_FORWARDING_STARTED', 'input_mode': 'FORWARDED_COPY',
            'transport_started': True, 'new_attempts': 1,
            'diagnostic': {'window_ref': self.ref, 'state': 'ACTIVE', 'result_attempts': 1,
                'live_capture_latch': 'OPEN', 'execution_latch': 'OPEN'}}

    def write_events(self, events):
        path = self.root / 'receiver-events.jsonl'
        path.write_text(''.join(json.dumps(e) + '\n' for e in events)); path.chmod(0o600)

    def test_forwarded_start_event_supports_review_after_receiver_closes(self):
        started = self.forwarded_input()
        self.write_events([started, {'event': 'P29_FORWARDING_CLOSED'}])
        report, rows = self.review()
        self.assertEqual((report['window_ref'], len(rows)), (self.ref, 2))
        self.assertFalse((self.root / ('result-attempt-' + 'b' * 32 + '.lock')).exists())

    def test_forwarded_review_requires_own_actual_start(self):
        for change in ('prepared', 'wrong_window', 'duplicate_start', 'not_started'):
            started = self.forwarded_input()
            if change == 'prepared': started['event'] = 'P29_RECEIVER_PREPARED'
            elif change == 'wrong_window': started['diagnostic']['window_ref'] = 'result:' + 'e' * 32
            elif change == 'not_started': started['transport_started'] = False
            self.write_events([started] * (2 if change == 'duplicate_start' else 1))
            with self.subTest(change=change), \
                 patch('collection_adapter.p29_category_review.parse_category_public_values') as parse:
                with self.assertRaises(CategoryCandidateError): self.review()
                parse.assert_not_called()

    def test_forwarded_start_cannot_override_mismatched_existing_reservation(self):
        started = self.forwarded_input(); self.write_events([started])
        self.write('result-attempt-' + 'b' * 32 + '.lock',
                   {'schema_version': 'p26-attempt-reservation/v1', 'window_ref': 'result:' + 'e' * 32})
        with self.assertRaises(CategoryCandidateError): self.review()

    def test_actual_shape_preserves_each_sku_and_empty_labels_without_unit_guess(self):
        rows = parse_category_public_values(analysis())
        self.assertEqual(len(rows), 2)
        self.assertEqual({r.sku_id: r.sku_price_number for r in rows}, {'201': '1.25', '202': '2.75'})
        self.assertEqual(rows[0].sku_spec, '')
        self.assertIsNone(rows[0].sku_description)
        self.assertFalse(hasattr(rows[0], 'currency') or hasattr(rows[0], 'store_name'))

    def test_later_observation_keeps_own_price_and_never_borrows_optional_field(self):
        earlier = parse_category_public_values(analysis())
        body = synthetic_body(); product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        del product['unit']; product['name'] = 'Synthetic later product'
        product['skus'][0]['price'] = 9.75
        later = parse_category_public_values(analysis(body))
        self.assertEqual(later[0].sku_price_number, '9.75')
        self.assertIsNone(later[0].product_unit)
        self.assertEqual(earlier[0].sku_price_number, '1.25')

    def test_missing_core_rejects_entire_candidate_without_partial_rows(self):
        for key in ('id', 'name', 'min_price', 'skus'):
            with self.subTest(key=key):
                body = synthetic_body(); del body['data']['food_spu_tags'][0]['dynamic_spus'][0][key]
                with self.assertRaises(CategoryCandidateError): parse_category_public_values(analysis(body))

    def test_coordinate_path_mismatch_duplicate_and_huge_index_rejected(self):
        original = analysis()
        for change in ('mismatch', 'duplicate', 'huge', 'bool'):
            a = copy.deepcopy(original)
            selected = next(v for v in a['public_values'] if v['path'].endswith('dynamic_spus[].id'))
            if change == 'mismatch': selected['coordinates'][-1] = 'name'
            elif change == 'duplicate': a['public_values'].append(copy.deepcopy(selected))
            elif change == 'huge': selected['coordinates'][4] = 999999
            else: selected['coordinates'][2] = True
            with self.subTest(change=change), self.assertRaises(CategoryCandidateError):
                parse_category_public_values(a)

    def test_changed_sku_owner_rejected_but_cross_category_membership_preserved(self):
        body = synthetic_body(); category = copy.deepcopy(body['data']['food_spu_tags'][0])
        category['tag'] = 'synthetic_other_category'; body['data']['food_spu_tags'].append(category)
        self.assertEqual(len(parse_category_public_values(analysis(body))), 4)
        category['dynamic_spus'][0]['id'] = 102
        with self.assertRaises(CategoryCandidateError): parse_category_public_values(analysis(body))

    def test_invalid_number_or_text_has_only_closed_error_code(self):
        for bad in (True, -1, float('inf')):
            a = analysis(); item = next(v for v in a['public_values'] if v['path'].endswith('skus[].price'))
            item['value'] = bad
            with self.assertRaises(CategoryCandidateError) as caught: parse_category_public_values(a)
            self.assertEqual(str(caught.exception), 'P29_CATEGORY_CANDIDATE_INVALID')
        a = analysis(); next(v for v in a['public_values'] if v['path'].endswith('dynamic_spus[].name'))['value'] = 'https://synthetic.invalid'
        with self.assertRaises(CategoryCandidateError): parse_category_public_values(a)

    def test_opaque_private_branches_never_reach_candidate_or_report(self):
        body = synthetic_body(); body['data']['session'] = {'cookie': 'synthetic private sentinel'}
        a = analysis(body)
        self.assertNotIn('synthetic private sentinel', json.dumps(a))
        self.assertEqual(len(parse_category_public_values(a)), 2)
        a['sensitive_values_processed'] = True
        with self.assertRaises(CategoryCandidateError): parse_category_public_values(a)

    def test_budget_or_empty_input_rejected(self):
        a = analysis(); a['public_values'] = a['public_values'] * 8001
        with self.assertRaises(CategoryCandidateError): parse_category_public_values(a)
        a['public_values'] = []
        with self.assertRaises(CategoryCandidateError): parse_category_public_values(a)

    def test_named_owned_review_counts_only_and_never_becomes_complete_result(self):
        self.prepare_input(); report, rows = self.review()
        self.assertEqual((report['candidate_row_count'], report['product_count'], report['sku_count']), (2, 1, 2))
        self.assertFalse(report['can_publish_complete_result'])
        self.assertEqual(report['business_result_rows_added'], 0)
        self.assertNotIn('Synthetic render product', json.dumps(report))
        self.assertFalse(report['source_context_age_within_10_seconds'])
        schema = json.loads((Path(__file__).parents[2]/'contracts/schemas/p29-category-candidate-review-v1.schema.json').read_text())
        validator = Draft202012Validator(schema)
        self.assertTrue(validator.is_valid(report))
        self.assertFalse(validator.is_valid({**report, 'can_publish_complete_result': True}))
        self.assertFalse(validator.is_valid({**report, 'raw': 'synthetic private sentinel'}))
        with self.assertRaises(ResultPublishError): _manifest_from_views(rows, 'synthetic_review')

    def test_wrong_window_or_false_scope_stops_before_candidate_parse(self):
        self.prepare_input()
        self.write('result-attempt-' + 'b' * 32 + '.lock',
                   {'schema_version': 'p26-attempt-reservation/v1', 'window_ref': 'result:' + 'e' * 32})
        with patch('collection_adapter.p29_category_review.parse_category_public_values') as parse:
            with self.assertRaises(CategoryCandidateError): self.review()
            parse.assert_not_called()
        self.prepare_input({**self.document(), 'shop_scope_verified': False})
        with self.assertRaises(CategoryCandidateError): self.review()

    def test_argument_errors_cannot_echo_supplied_text(self):
        out = io.StringIO()
        with patch('sys.argv', ['review', '--unknown', 'synthetic private argument']), contextlib.redirect_stdout(out):
            self.assertEqual(main(), 1)
        self.assertEqual(json.loads(out.getvalue()), {'code': 'P29_CATEGORY_ARGUMENTS_INVALID'})

    def test_v2_root_code_failures_reject_before_candidate_parse(self):
        for status in ('NONZERO', 'ABSENT', 'INVALID_TYPE'):
            doc = {**self.document(), 'schema_version': 'p29-category-render-inspection/v2',
                   'response_code_status': status}
            self.prepare_input(doc)
            with self.subTest(status=status), patch('collection_adapter.p29_category_review.parse_category_public_values') as parse:
                with self.assertRaises(CategoryCandidateError): self.review()
                parse.assert_not_called()
        self.prepare_input({**self.document(), 'schema_version': 'p29-category-render-inspection/v2',
                            'response_code_status': 'ZERO'})
        report, rows = self.review()
        self.assertEqual(report['response_code_status'], 'ZERO')
        self.assertNotIn('RESPONSE_SUCCESS_CODE', report['unconfirmed_facts'])
        self.assertFalse(report['can_publish_complete_result'])

    def batch(self, names):
        with patch('collection_adapter.p29_category_review._root', return_value=self.root):
            return review_category_batch(self.root, names)

    def second_input(self, *, category=None, owner=None, later=True):
        doc = self.document()
        doc['schema_version'] = 'p29-category-render-inspection/v2'
        doc['response_code_status'] = 'ZERO'
        doc['source_request_ref'] = 'request:' + 'e' * 32
        if later:
            doc['observed_at'] = '2026-01-01T00:02:00+00:00'
        body = synthetic_body()
        if category is not None:
            body['data']['food_spu_tags'][0]['tag'] = category
        product = body['data']['food_spu_tags'][0]['dynamic_spus'][0]
        if owner is not None:
            product['id'] = owner
        product.pop('unit')
        product['skus'][0]['price'] = 9.75
        doc['public_analysis'] = analysis(body)
        name = 'category_render_' + 'f' * 32 + '-public-fields.json'
        self.write(name, doc)
        return name, doc

    def test_batch_latest_whole_candidate_keeps_own_time_and_absence(self):
        self.prepare_input(); second, _ = self.second_input()
        report, rows = self.batch([second, self.name])
        self.assertEqual((report['input_candidate_rows'], report['candidate_row_count'],
                          report['deduplicated_candidate_rows']), (4, 2, 2))
        self.assertEqual(report['response_code_status_counts'], {'ZERO': 1, 'UNOBSERVED': 1})
        self.assertTrue(all(r.source_file == second for r in rows))
        self.assertTrue(all(r.observed_at == '2026-01-01T00:02:00+00:00' for r in rows))
        self.assertEqual(rows[0].candidate.sku_price_number, '9.75')
        self.assertIsNone(rows[0].candidate.product_unit)
        self.assertFalse(report['cross_observation_fields_copied'])
        self.assertFalse(report['can_publish_complete_result'])
        self.assertNotIn('Synthetic render product', json.dumps(report))
        with self.assertRaises(ResultPublishError): _manifest_from_views(rows, 'synthetic_batch')

    def test_batch_preserves_cross_category_membership_and_rejects_owner_change(self):
        self.prepare_input(); second, _ = self.second_input(category='synthetic_other')
        report, rows = self.batch([self.name, second])
        self.assertEqual((report['candidate_row_count'], report['sku_count'], report['category_count']), (4, 2, 2))
        self.assertEqual(len({r.candidate.category_ref for r in rows}), 2)
        self.second_input(category='synthetic_other', owner=102)
        with self.assertRaises(CategoryCandidateError) as caught: self.batch([self.name, second])
        self.assertEqual(caught.exception.code, 'P29_CATEGORY_SKU_OWNER_CHANGED')

    def test_batch_reused_input_request_or_mixed_window_rejected(self):
        self.prepare_input(); second, doc = self.second_input()
        with self.assertRaises(CategoryCandidateError): self.batch([self.name, self.name])
        original = copy.deepcopy(doc)
        doc['source_request_ref'] = self.document()['source_request_ref']; self.write(second, doc)
        with self.assertRaises(CategoryCandidateError): self.batch([self.name, second])
        doc = original; doc['window_ref'] = 'result:' + '1' * 32; self.write(second, doc)
        self.write('result-attempt-' + '1' * 32 + '.lock',
                   {'schema_version': 'p26-attempt-reservation/v1', 'window_ref': doc['window_ref']})
        with self.assertRaises(CategoryCandidateError): self.batch([self.name, second])

    def test_batch_finite_file_row_and_byte_budgets(self):
        self.prepare_input(); second, _ = self.second_input()
        with patch('collection_adapter.p29_category_review.MAX_OBSERVATIONS', 1):
            with self.assertRaises(CategoryCandidateError): self.batch([self.name, second])
        with patch('collection_adapter.p29_category_review.MAX_ROWS', 1):
            with self.assertRaises(CategoryCandidateError): self.batch([self.name])
        with patch('collection_adapter.p29_category_review.MAX_COLLECTION_BYTES', 1):
            with self.assertRaises(CategoryCandidateError): self.batch([self.name])
        for names in ([], [False], ['../synthetic_private.json']):
            with self.subTest(names=names), self.assertRaises(CategoryCandidateError): self.batch(names)

    def test_batch_conflicting_rows_at_identical_time_cannot_be_ordered(self):
        self.prepare_input(); second, _ = self.second_input(later=False)
        with self.assertRaises(CategoryCandidateError) as caught: self.batch([self.name, second])
        self.assertEqual(caught.exception.code, 'P29_CATEGORY_BATCH_ORDER_AMBIGUOUS')

    def test_batch_category_budget_applies_to_union_not_each_response_only(self):
        self.prepare_input(); second, doc = self.second_input()
        for name,document,prefix in [(self.name,self.document(),'synthetic_first_'),
                                     (second,doc,'synthetic_second_')]:
            body = synthetic_body(); template = body['data']['food_spu_tags'][0]
            categories = []
            for index in range(130):
                category = copy.deepcopy(template); category['tag'] = prefix + str(index)
                categories.append(category)
            body['data']['food_spu_tags'] = categories
            document['public_analysis'] = analysis(body); self.write(name,document)
        with self.assertRaises(CategoryCandidateError) as caught: self.batch([self.name,second])
        self.assertEqual(caught.exception.code, 'P29_CATEGORY_BATCH_BUDGET')

    def test_batch_cli_and_closed_report_contract_are_value_free(self):
        self.prepare_input(); second, _ = self.second_input()
        out = io.StringIO()
        with patch('collection_adapter.p29_category_review._root', return_value=self.root), \
                patch('sys.argv', ['review', '--output-root', str(self.root),
                                  '--input-name', self.name, '--input-name', second]), \
                contextlib.redirect_stdout(out):
            self.assertEqual(main(), 0)
        report = json.loads(out.getvalue())
        self.assertNotIn('Synthetic render product', out.getvalue())
        schema_root = Path(__file__).parents[2] / 'contracts/schemas'
        resources = {p.name: Resource.from_contents(json.loads(p.read_text()))
                     for p in schema_root.glob('*.schema.json')}
        def local(uri):
            if uri in resources: return resources[uri]
            raise NoSuchResource(ref=uri)
        registry = Registry(retrieve=local).with_resources(resources.items())
        validator = Draft202012Validator(json.loads(
            (schema_root/'p29-category-candidate-batch-review-v1.schema.json').read_text()), registry=registry)
        self.assertTrue(validator.is_valid(report))
        self.assertFalse(validator.is_valid({**report, 'can_publish_complete_result': True}))
        self.assertFalse(validator.is_valid({**report, 'raw': 'synthetic_private'}))


if __name__ == '__main__':
    unittest.main()
