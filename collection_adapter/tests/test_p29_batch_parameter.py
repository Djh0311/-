import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import quote_from_bytes

from jsonschema import Draft202012Validator, FormatChecker

from collection_adapter.p28_business_batch import analyze_public_body
from collection_adapter.p29_batch_parameter import inspect_current_batch_parameter
from collection_adapter.tests import test_p29_category_render as render_tests


def response_analysis():
    # Shapes exercise possible encodings; none is asserted as a real grammar.
    return analyze_public_body(json.dumps({'data': {'food_spu_tags': [
        {'tag': '11', 'dynamic_spus': [{'id': 101}, {'id': 102}]},
        {'tag': '22', 'dynamic_spus': [{'id': 101}]}]}}).encode())


class BatchParameterTests(unittest.TestCase):
    setUp = render_tests.CategoryRenderTests.setUp
    pair = render_tests.CategoryRenderTests.pair
    response = render_tests.CategoryRenderTests.response
    lease = render_tests.CategoryRenderTests.lease

    def authorize(self, parameter=None, *, private=b''):
        body = b'poi_id_str=public_synthetic_42&wm_poi_id=-42'
        if parameter is not None:
            body += b'&tag_spu_ids=' + quote_from_bytes(parameter).encode('ascii')
        body += private
        ref = self.lease(body)
        self.assertTrue(self.window.authorize_category_request(2, ref))
        return ref

    def probe(self, ref):
        return inspect_current_batch_parameter(self.window, 2, ref, response_analysis())

    def receive_authorized(self, ref, body):
        collector = self.window.begin_response(2, 'identity', source_request_ref=ref)
        collector.feed(body); collector.feed(b'')

    def array_items(self):
        # Observed keys, entirely synthetic memberships and control values.
        return [{'spuId': product, 'tagId': category, 'childTagId': '', 'tagType': 1}
                for category, product in (('11', 101), ('11', 102), ('22', 101))]

    def array_probe(self, items):
        return self.probe(self.authorize(json.dumps(items).encode()))['array_item_relation']

    def test_observed_array_compares_each_own_item_without_qualifying_result(self):
        self.pair(); ref = self.authorize(json.dumps(self.array_items()).encode())
        report = self.probe(ref); relation = report['array_item_relation']
        self.assertEqual(relation['status'], 'MATCHED_CURRENT_RESPONSE')
        self.assertEqual((relation['item_count'], relation['request_membership_count'],
                          relation['matching_tag_membership_count']), (3, 3, 3))
        self.assertEqual(relation['matching_child_tag_membership_count'], 0)
        self.assertEqual(relation['request_memberships_not_in_response'], 0)
        self.assertEqual(relation['response_memberships_not_in_request'], 0)
        self.assertFalse(report['grammar_qualified'] or report['same_observation_record_ready']
                         or report['can_publish_complete_result'])
        self.assertEqual(relation['tag_type_semantics'], 'UNCONFIRMED')
        self.assertEqual(relation['child_tag_semantics'], 'UNCONFIRMED')
        for value in ('101', '102', '"11"', '"22"'):
            self.assertNotIn(value, json.dumps(report))

    def test_same_category_and_product_id_sets_cannot_hide_a_swapped_membership(self):
        self.pair(); items = self.array_items(); items[1]['tagId'] = '22'
        report = self.probe(self.authorize(json.dumps(items).encode()))
        self.assertEqual((report['matching_category_id_count'], report['matching_product_id_count']), (2, 2))
        relation = report['array_item_relation']
        self.assertEqual(relation['status'], 'MEMBERSHIPS_DIFFER')
        self.assertEqual(relation['matching_tag_membership_count'], 2)
        self.assertEqual(relation['request_memberships_not_in_response'], 1)
        self.assertEqual(relation['response_memberships_not_in_request'], 1)

    def test_duplicate_missing_and_unreturned_array_items_are_distinct_from_matching(self):
        self.pair(); items = self.array_items()
        duplicate = self.array_probe(items + [items[0]])
        self.assertEqual(duplicate['status'], 'MEMBERSHIPS_DIFFER')
        self.assertEqual(duplicate['duplicate_request_memberships'], 1)
        missing = self.array_probe(items[:-1])
        self.assertEqual(missing['response_memberships_not_in_request'], 1)
        extra = self.array_probe(items + [{'spuId': 999, 'tagId': '11', 'childTagId': '', 'tagType': 1}])
        self.assertEqual(extra['request_memberships_not_in_response'], 1)
        self.assertEqual(extra['status'], 'MEMBERSHIPS_DIFFER')

    def test_child_tag_matches_cannot_substitute_for_each_items_tag(self):
        self.pair(); items = self.array_items()
        for item in items:
            item['childTagId'], item['tagId'] = item['tagId'], '99'
        relation = self.array_probe(items)
        self.assertEqual(relation['status'], 'MEMBERSHIPS_DIFFER')
        self.assertEqual(relation['matching_tag_membership_count'], 0)
        self.assertEqual(relation['matching_child_tag_membership_count'], 3)
        self.assertEqual(relation['child_tag_semantics'], 'UNCONFIRMED')

    def test_empty_missing_and_wrong_typed_items_cannot_pass_array_membership_check(self):
        self.pair(); items = self.array_items()
        for malformed in (items + [{}], [{}] + items, items + [{'spuId': 999, 'tagId': '11'}],
                          [{**items[0], 'spuId': 101.0}] + items[1:]):
            with self.subTest():
                self.assertEqual(self.array_probe(malformed)['status'], 'ARRAY_ITEMS_INVALID')
        empty = self.array_probe([])
        self.assertEqual(empty['status'], 'EMPTY_ARRAY')
        self.assertEqual(empty['response_memberships_not_in_request'], 3)
        changed = self.array_probe([{**item, 'new_public_key': 1} for item in items])
        self.assertEqual(changed['status'], 'PROFILE_NOT_OBSERVED')

    def test_array_item_count_keeps_quoted_delimiters_and_private_values_opaque(self):
        self.pair(); items = self.array_items(); items[0]['childTagId'] = '[,]\\"'
        parameter = json.dumps(items).encode().replace(b'"tagType": 1', b'"tagType": 1, "cookie":"\xff"', 1)
        report = self.probe(self.authorize(parameter))
        self.assertEqual(report['array_item_relation']['item_count'], 3)
        self.assertEqual(report['array_item_relation']['status'], 'MATCHED_CURRENT_RESPONSE')
        self.assertEqual(report['private_key_category_counts']['CREDENTIAL_KEY'], 1)
        self.assertNotIn('cookie', json.dumps(report))
        self.assertFalse(report['sensitive_values_processed'])

    def test_empty_array_objects_still_consume_the_item_budget(self):
        from collection_adapter.p26_identification import IdentificationError
        self.pair(); ref = self.authorize(b'[' + b'{},' * 4096 + b'{}]')
        with self.assertRaises(IdentificationError) as raised:
            self.probe(ref)
        self.assertEqual(raised.exception.code, 'P26_STRUCTURE_BUDGET')

    def test_array_relation_is_persisted_only_as_bounded_own_response_metadata(self):
        self.pair(); before = (self.window.published_count, self.window._parsed_total)
        ref = self.authorize(json.dumps(self.array_items()).encode())
        self.receive_authorized(ref, b'{"code":0,"data":{"food_spu_tags":[{"tag":"11","dynamic_spus":[{"id":101},{"id":102}]},{"tag":"22","dynamic_spus":[{"id":101}]}]}}')
        receipt = json.loads(next(self.root.glob('category_render_*-batch-parameter.json')).read_text())
        self.assertEqual(receipt['source_request_ref'], ref)
        self.assertEqual(receipt['probe']['array_item_relation']['status'], 'MATCHED_CURRENT_RESPONSE')
        self.assertEqual(receipt['probe']['array_item_relation']['matching_tag_membership_count'], 3)
        schema = Path(__file__).parents[2]/'contracts/schemas/p29-category-batch-parameter-probe-v2.schema.json'
        self.assertTrue(Draft202012Validator(json.loads(schema.read_text()), format_checker=FormatChecker()).is_valid(receipt))
        self.assertEqual((self.window.published_count, self.window._parsed_total), before)
        self.assertFalse(receipt['probe']['can_publish_complete_result'])

    def test_object_shape_compares_only_current_public_ids_and_never_qualifies_grammar(self):
        self.pair(); ref = self.authorize(b'{"11":[101,"102",999],"22":[101]}')
        report = self.probe(ref)
        self.assertEqual(report['status'], 'STRUCTURE_OBSERVED')
        self.assertEqual(report['root_kind'], 'OBJECT')
        self.assertEqual((report['public_scalar_count'], report['matching_category_id_count'],
                          report['matching_product_id_count'],
                          report['matching_memberships_by_ancestor_key_count']), (4, 2, 2, 3))
        self.assertEqual(report['unmatched_public_scalar_count'], 1)
        text = json.dumps(report)
        for value in ('101', '102', '999', '.11', '.22', 'p29_parameter'):
            self.assertNotIn(value, text)
        self.assertFalse(report['grammar_qualified'] or report['can_publish_complete_result'])
        self.assertEqual(report['termination_semantics'], 'UNCONFIRMED')
        self.assertEqual(report['parameter_role'], 'UNKNOWN')

    def test_array_and_typed_controls_do_not_invent_membership_or_end(self):
        self.pair(); ref = self.authorize(b'[101,"102",101.0,true,null]')
        report = self.probe(ref)
        self.assertEqual(report['root_kind'], 'ARRAY')
        self.assertEqual(report['public_scalar_count'], 5)
        self.assertEqual(report['matching_product_id_count'], 2)
        self.assertEqual(report['matching_memberships_by_ancestor_key_count'], 0)
        self.assertEqual(report['unmatched_public_scalar_count'], 3)
        self.assertFalse(report['same_observation_record_ready'])

    def test_private_form_values_and_nested_private_values_remain_opaque(self):
        self.pair()
        # Invalid UTF-8 is a sentinel proving private string values are not
        # decoded by the lexical reader, in either FORM or JSON branches.
        ref = self.authorize(b'{"11":[101],"session":{"token":"\xff"},"cookie":"\xff"}',
                             private=b'&cookie=%FF&session=%FF')
        report = self.probe(ref)
        self.assertEqual(report['status'], 'STRUCTURE_OBSERVED')
        self.assertEqual(report['public_scalar_count'], 1)
        self.assertEqual(report['private_key_category_counts']['SESSION_KEY'], 1)
        self.assertEqual(report['private_key_category_counts']['CREDENTIAL_KEY'], 1)
        self.assertNotIn('token', json.dumps(report))
        self.assertFalse(report['sensitive_values_processed'])

    def test_unstarted_unauthorized_other_shop_and_used_requests_deny_before_value_decode(self):
        from collection_adapter.p29_store_pages import P29StorePagesWindow
        prepared = P29StorePagesWindow('Synthetic batch shop', self.root,
            'authorization:synthetic_p29', identify_category_render=True)
        with patch('collection_adapter.p29_batch_parameter.unquote_to_bytes') as decode:
            report = inspect_current_batch_parameter(prepared, 2, 'request:' + 'a' * 32, response_analysis())
            self.assertEqual(report['status'], 'SCOPE_UNAVAILABLE')
            self.assertEqual(prepared.attempts, 0)
            self.assertFalse(prepared.request_leases or prepared.collectors)
            decode.assert_not_called()
        ref = self.lease(b'poi_id_str=public_synthetic_42&wm_poi_id=-42&tag_spu_ids=%FF')
        with patch('collection_adapter.p29_batch_parameter.unquote_to_bytes') as decode:
            self.assertEqual(self.probe(ref)['status'], 'SCOPE_UNAVAILABLE')
            decode.assert_not_called()
        self.pair(); ref = self.authorize(b'[101]')
        self.window.request_leases[ref]['body'] = b'poi_id_str=other_synthetic&wm_poi_id=-42&tag_spu_ids=%FF'
        with patch('collection_adapter.p29_batch_parameter.unquote_to_bytes') as decode:
            self.assertEqual(self.probe(ref)['status'], 'SCOPE_UNAVAILABLE')
            decode.assert_not_called()
        ref = self.authorize(b'[101]'); self.window.render_inspector.consumed.add(ref)
        with patch('collection_adapter.p29_batch_parameter.unquote_to_bytes') as decode:
            self.assertEqual(self.probe(ref)['status'], 'SCOPE_UNAVAILABLE')
            decode.assert_not_called()
        self.window.close('P26_CANCELLED')
        with patch('collection_adapter.p29_batch_parameter.unquote_to_bytes') as decode:
            self.assertEqual(self.probe(ref)['status'], 'SCOPE_UNAVAILABLE')
            decode.assert_not_called()

    def test_expired_request_does_not_decode_or_reuse_old_selected_value(self):
        self.pair(); ref = self.authorize(b'[101]'); self.now[0] += 61
        with patch('collection_adapter.p29_batch_parameter.unquote_to_bytes') as decode:
            self.assertEqual(self.probe(ref)['status'], 'REQUEST_LEASE_UNAVAILABLE')
            decode.assert_not_called()

    def test_absent_non_container_invalid_encoding_and_malformed_inputs_keep_fixed_markers(self):
        self.pair(); self.assertEqual(self.probe(self.authorize())['status'], 'ABSENT')
        for parameter, expected in ((b'', 'NOT_A_JSON_CONTAINER'),
                (b'unknown synthetic grammar', 'NOT_A_JSON_CONTAINER'),
                (b'{', 'MALFORMED_STRUCTURE'), (b'{"id":101,"id":102}', 'MALFORMED_STRUCTURE'),
                (b'["\xff"]', 'MALFORMED_STRUCTURE'),
                (b'["https://synthetic.invalid"]', 'UNAVAILABLE_PUBLIC_SCALAR')):
            with self.subTest(expected=expected):
                self.assertEqual(self.probe(self.authorize(parameter))['status'], expected)
        ref = self.authorize(b'[101]')
        self.window.request_leases[ref]['body'] = b'poi_id_str=public_synthetic_42&wm_poi_id=-42&tag_spu_ids=%ZZ'
        self.assertEqual(self.probe(ref)['status'], 'INVALID_ENCODING')

    def test_size_path_and_scalar_budgets_close_with_no_parameter_or_partial_result(self):
        from collection_adapter.p26_identification import IdentificationError
        self.pair(); ref = self.authorize(b'[' + b'1,' * 9000 + b'1]')
        with self.assertRaises(IdentificationError): self.probe(ref)
        for constant in ('MAX_PARAMETER_PATHS', 'MAX_PARAMETER_SCALARS'):
            ref = self.authorize(b'{"items":[101,102]}')
            with self.subTest(constant=constant), patch('collection_adapter.p29_batch_parameter.' + constant, 1):
                with self.assertRaises(IdentificationError): self.probe(ref)
        self.receive_authorized(self.authorize(b'[' + b'1,' * 9000 + b'1]'), b'{"code":0,"data":{}}')
        self.assertEqual(self.window.state, 'CLOSED')
        self.assertEqual(self.window.code, 'P26_STRUCTURE_BUDGET')
        self.assertFalse(list(self.root.glob('category_render_*-batch-parameter.json')))
        self.assertEqual(len(self.window.snapshots), 1)
        self.assertIsNotNone(self.window.collection_receipt)
        self.assertFalse(self.window.request_leases or self.window.render_inspector.authorized)

    def test_shared_public_artifact_budget_stops_before_either_file_is_written(self):
        self.pair(); ref = self.authorize(b'{"11":[101]}')
        with patch('collection_adapter.p29_store_pages.MAX_COLLECTION_BYTES', self.window._public_bytes):
            self.receive_authorized(ref, b'{"code":0,"data":{"food_spu_tags":[{"tag":"11","dynamic_spus":[{"id":101}]}]}}')
        self.assertEqual(self.window.code, 'P26_TOTAL_SIZE_LIMIT')
        self.assertFalse(list(self.root.glob('category_render_*')))
        self.assertEqual(len(self.window.snapshots), 1)

    def test_clock_failure_during_inspection_cannot_publish_after_window_close(self):
        self.pair(); ref = self.authorize(b'{"11":[101]}')
        def analyze_then_invalidate_clock(body):
            result = analyze_public_body(body)
            self.now[0] = float('nan')
            return result
        with patch('collection_adapter.p29_category_render.analyze_public_body', analyze_then_invalidate_clock):
            self.receive_authorized(ref, b'{"code":0,"data":{}}')
        self.assertEqual(self.window.code, 'P26_CLOCK_INVALID')
        self.assertEqual(self.window.state, 'CLOSED')
        self.assertFalse(list(self.root.glob('category_render_*')))
        self.assertFalse(self.window.request_leases or self.window.render_inspector.authorized)
        self.assertEqual(len(self.window.snapshots), 1)

    def test_receipt_is_separate_current_and_closed_result_counts_unchanged(self):
        self.pair(); before = (self.window.published_count, self.window._parsed_total)
        ref = self.authorize(b'{"11":[101]}')
        self.receive_authorized(ref, b'{"code":0,"data":{"food_spu_tags":[{"tag":"11","dynamic_spus":[{"id":101}]}]}}')
        inventory = next(self.root.glob('category_render_*-public-fields.json'))
        receipt = json.loads(next(self.root.glob('category_render_*-batch-parameter.json')).read_text())
        self.assertEqual(receipt['source_request_ref'], ref)
        self.assertEqual(receipt['observed_at'], json.loads(inventory.read_text())['observed_at'])
        self.assertEqual(receipt['probe']['status'], 'STRUCTURE_OBSERVED')
        self.assertEqual((self.window.published_count, self.window._parsed_total), before)
        schema_path = Path(__file__).parents[2]/'contracts/schemas/p29-category-batch-parameter-probe-v2.schema.json'
        validator = Draft202012Validator(json.loads(schema_path.read_text()), format_checker=FormatChecker())
        self.assertTrue(validator.is_valid(receipt))
        self.assertFalse(validator.is_valid({**receipt, 'parameter_value': 'synthetic sentinel'}))
        self.assertFalse(validator.is_valid({**receipt, 'probe': {**receipt['probe'], 'grammar_qualified': True}}))
        self.assertFalse(validator.is_valid({**receipt, 'probe': {**receipt['probe'], 'array_item_relation':
            {**receipt['probe']['array_item_relation'], 'spuId': 101}}}))
        legacy = {**receipt, 'schema_version': 'p29-category-batch-parameter-probe/v1',
            'probe': {k: v for k, v in receipt['probe'].items() if k != 'array_item_relation'}}
        legacy_schema = schema_path.with_name('p29-category-batch-parameter-probe-v1.schema.json')
        self.assertTrue(Draft202012Validator(json.loads(legacy_schema.read_text()),
                                           format_checker=FormatChecker()).is_valid(legacy))
        self.window.close('P26_CANCELLED')
        self.assertFalse(self.window.render_inspector.authorized or self.window.request_leases)


if __name__ == '__main__':
    unittest.main()
