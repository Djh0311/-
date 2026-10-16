"""Only synthetic, bounded inputs; no network or raw capture replay."""

import json
import unittest
from unittest.mock import patch

from collection_adapter.p26_identification import (
    IdentificationError, IdentificationWindow, key_only_layout, _privacy_shape,
    structure_budget_error,
)
from collection_adapter.p28_business_batch import analyze_public_body
from collection_adapter.p26_structure_budget import record_failure


class StructureBudgetDetailTests(unittest.TestCase):
    def test_distinct_limits_keep_the_same_stop_code_but_identify_the_dimension(self):
        cases = (
            ('NODES', b'[' + b'0,' * 40000 + b'0]', 40000),
            ('DEPTH', b'[' * 34 + b'0' + b']' * 34, 32),
            ('FIELD_DEFINITIONS', json.dumps({f'field_{i}': 0 for i in range(4096)}).encode(), 4096),
            ('RESTRICTED_DEFINITIONS', json.dumps({f'token_{i}': 0 for i in range(4097)}).encode(), 4096),
        )
        for dimension, body, limit in cases:
            with self.subTest(dimension=dimension), self.assertRaises(IdentificationError) as caught:
                key_only_layout(body, restricted_fields=[])
            self.assertEqual(caught.exception.code, 'P26_STRUCTURE_BUDGET')
            detail = getattr(caught.exception, 'structure_budget', None)
            self.assertIsNotNone(detail, 'budget reason is lost at the exception boundary')
            self.assertEqual(detail['dimension'], dimension)
            self.assertEqual(detail['limit'], limit)
            self.assertEqual(detail['observed'], limit + 1)
            self.assertNotIn('field_0', json.dumps(detail))

    def test_public_scalar_limit_is_distinct_and_boundary_stays_unchanged(self):
        accepted = json.dumps({'data': {'items': [0] * 8000}}).encode()
        self.assertEqual(len(analyze_public_body(accepted)['public_values']), 8000)
        with self.assertRaises(IdentificationError) as caught:
            analyze_public_body(json.dumps({'data': {'items': [0] * 8001}}).encode())
        detail = getattr(caught.exception, 'structure_budget', None)
        self.assertIsNotNone(detail)
        self.assertEqual(detail['dimension'], 'PUBLIC_VALUES')
        self.assertEqual((detail['observed'], detail['limit']), (8001, 8000))

    def test_strict_scan_and_catalog_have_distinct_stages(self):
        with self.assertRaises(IdentificationError) as caught:
            _privacy_shape({f'field_{i}': 0 for i in range(4096)}, 'Synthetic')
        self.assertEqual(caught.exception.structure_budget['stage'], 'STRICT_SCAN')
        window = IdentificationWindow('Synthetic', duration_seconds=None)
        window.start_once()
        window.routes = [('GET', 'synthetic.invalid', '/catalog/list')]
        window.field_catalog = {i: {} for i in range(4096)}
        window._consume(0, b'{"name":"Synthetic"}')
        self.assertEqual(window.code, 'P26_STRUCTURE_BUDGET')
        self.assertEqual(window.structure_budget_failure['dimension'], 'CATALOG_DEFINITIONS')

    def test_failure_survives_async_close_without_changing_forwarded_bytes(self):
        from collection_adapter.tests.test_detached_analysis import DetachedAnalysisTests
        from collection_adapter.p29_store_inventory import _validate
        window, addon, stream = DetachedAnalysisTests.setup_stream(self, analyze_public_body)
        body = json.dumps({'data': {'items': [0] * 8001}}).encode()
        try:
            self.assertIs(stream(body), body)
            self.assertEqual(stream(b''), b'')
            addon.analysis._thread.join(3)
            self.assertFalse(addon.analysis._thread.is_alive())
            self.assertEqual(window.code, 'P26_STRUCTURE_BUDGET')
            self.assertEqual(addon.transport_window.state, 'ACTIVE')
            diagnostic = addon.analysis.diagnostic()
            self.assertEqual(diagnostic['structure_budget']['dimension'], 'PUBLIC_VALUES')
            _validate(diagnostic, 'detached-copy-analysis-v1.schema.json')
            self.assertFalse(diagnostic['accepting_copies'])
        finally:
            addon.transport_window.close('P26_CANCELLED')
            addon.finish_analysis('P26_CANCELLED')
        self.assertEqual(addon.analysis.diagnostic()['structure_budget'], diagnostic['structure_budget'])

    def test_invalid_detail_or_other_error_cannot_export_free_text(self):
        window = IdentificationWindow('Synthetic')
        error = IdentificationError('P26_STRUCTURE_BUDGET')
        error.structure_budget = {'dimension': 'PRIVATE_SYNTHETIC'}
        record_failure(window, error)
        self.assertIsNone(window.structure_budget_failure)
        valid = structure_budget_error('NODES', 40001, 'LEXICAL_SCAN')
        valid.code = 'P26_STRUCTURE_INVALID'
        record_failure(window, valid)
        self.assertIsNone(window.structure_budget_failure)

    def test_batch_pair_records_failure_before_clearing_the_bodies(self):
        from collection_adapter.tests.test_p28_business_batch import BatchWindowTests, bodies
        BatchWindowTests.setUp(self)
        self.addCleanup(self.temp.cleanup)
        food, product = bodies()
        BatchWindowTests.response(self, 0, food)
        with patch('collection_adapter.p28_business_batch.analyze_public_body',
                   side_effect=structure_budget_error('PUBLIC_VALUES', 8001, 'PUBLIC_PROJECTION')):
            BatchWindowTests.response(self, 1, product)
        self.assertEqual(self.window.code, 'P26_STRUCTURE_BUDGET')
        self.assertEqual(self.window.structure_budget_failure['dimension'], 'PUBLIC_VALUES')
        self.assertFalse(self.window._bodies)


class CategoryBudgetDetailTests(unittest.TestCase):
    from collection_adapter.tests.test_p29_category_render import CategoryRenderTests as _Fixture
    pair = _Fixture.pair
    response = _Fixture.response
    lease = _Fixture.lease
    render = _Fixture.render
    setUp = _Fixture.setUp

    def test_category_failure_preserves_diagnostic_and_previous_result(self):
        self.pair()
        with patch('collection_adapter.p29_category_render.analyze_public_body',
                   side_effect=structure_budget_error('PUBLIC_VALUES', 8001, 'PUBLIC_PROJECTION')):
            self.render()
        self.assertEqual(self.window.code, 'P26_STRUCTURE_BUDGET')
        self.assertEqual(self.window.structure_budget_failure['dimension'], 'PUBLIC_VALUES')
        self.assertTrue(list(self.root.glob('observation_*')))
        self.assertFalse(self.window.request_leases)
