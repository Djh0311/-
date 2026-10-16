"""Synthetic streams only: parsing must not hold the forwarding callback."""

import threading
import gzip
import json
import asyncio
import importlib.util
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from collection_adapter.p26_identification import IdentificationWindow, BodyCollector
from collection_adapter.p26_identification_host import IdentificationAddon


class DetachedAnalysisTests(unittest.TestCase):
    def setup_stream(self, consume):
        window = IdentificationWindow('Synthetic shop', duration_seconds=None)
        window.inspect_current_domain('example.invalid')
        window.start_once()
        window.domain('example.invalid')
        route = window.route('GET', 'example.invalid', '/catalog/list')
        window.select_route(route)
        addon = IdentificationAddon(window)
        addon.route_slots['synthetic'] = route
        flow = SimpleNamespace(id='synthetic', response=SimpleNamespace(
            status_code=200, headers={}, stream=True))
        collector = BodyCollector(window, 'identity', consume)
        window.collectors.append(collector)
        with patch.object(window, 'begin_response', return_value=collector):
            addon.responseheaders(flow)
        return window, addon, flow.response.stream

    def test_slow_parser_does_not_hold_final_response_chunk(self):
        entered, release, forwarded = threading.Event(), threading.Event(), threading.Event()
        bodies = []
        def consume(body):
            bodies.append(body)
            entered.set()
            release.wait(3)
        window, addon, stream = self.setup_stream(consume)
        data = b'{"synthetic":true}'
        self.assertIs(stream(data), data)
        def finish():
            self.assertEqual(stream(b''), b'')
            forwarded.set()
        sender = threading.Thread(target=finish)
        sender.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertTrue(forwarded.wait(.1), 'forwarding waited for parsing')
        finally:
            release.set()
            sender.join(3)
            if hasattr(addon, 'finish_analysis'):
                addon.finish_analysis()
        self.assertEqual(bodies, [data])

    def test_parser_failure_does_not_close_transport(self):
        failed = threading.Event()
        def consume(_body):
            failed.set()
            raise ValueError('synthetic parser failure')
        window, addon, stream = self.setup_stream(consume)
        data = b'{}'
        self.assertIs(stream(data), data)
        self.assertEqual(stream(b''), b'')
        self.assertTrue(failed.wait(1))
        if hasattr(addon, 'finish_analysis'):
            addon.finish_analysis()
        self.assertEqual(addon.forwarding.window.state, 'ACTIVE')

    def test_parser_failure_keeps_the_next_copy(self):
        seen = []
        def consume(body):
            if not seen:
                seen.append('failed')
                raise ValueError('synthetic parser failure')
            seen.append(body)
        window, addon, stream = self.setup_stream(consume)
        self.addCleanup(addon.finish_analysis)
        self.assertIs(stream(b'{}'), b'{}')
        self.assertEqual(stream(b''), b'')
        self.wait_idle(addon)
        self.assertEqual(window.state, 'ACTIVE')
        diagnostic = addon.analysis.diagnostic()
        self.assertEqual(diagnostic['failure'], 'ANALYSIS_REJECTED')
        self.assertEqual(diagnostic['recovery'], 'CONTINUING')
        self.assertTrue(diagnostic['accepting_copies'])
        self.assertTrue(diagnostic['coverage_incomplete'])
        self.assertGreaterEqual(diagnostic['dropped_copies'], 1)
        collector = BodyCollector(window, 'identity', consume)
        window.collectors.append(collector)
        later = addon._stream(collector)
        payload = b'{"next":1}'
        self.assertIs(later(payload), payload)
        self.assertEqual(later(b''), b'')
        self.wait_idle(addon)
        self.assertEqual(seen, ['failed', payload])
        self.assertEqual(addon.transport_window.state, 'ACTIVE')
        self.assertEqual(addon.analysis.diagnostic()['recovery'], 'CONTINUING')
        self.assertGreaterEqual(addon.analysis.diagnostic()['completed_streams'], 1)

    def test_queue_limit_keeps_a_later_copy(self):
        window, addon, stream = self.setup_stream(lambda body: self.fail('overflowed copy parsed: ' + repr(body)))
        self.addCleanup(addon.finish_analysis)
        lane = addon.analysis
        lane.MAX_CHUNKS = 1
        with lane.lock:
            for _ in range(4):
                self.assertIs(stream(b'copy'), b'copy')
            diagnostic = lane.diagnostic()
            self.assertEqual(diagnostic['failure'], 'COPY_QUEUE_LIMIT')
            self.assertEqual(diagnostic['recovery'], 'CONTINUING')
            self.assertTrue(diagnostic['accepting_copies'])
            self.assertEqual(lane.queued_bytes, 0)
        lane.MAX_CHUNKS = lane.__class__.MAX_CHUNKS
        seen = []
        collector = BodyCollector(window, 'identity', seen.append)
        window.collectors.append(collector)
        later = addon._stream(collector)
        payload = b'{"kept":1}'
        self.assertIs(later(payload), payload)
        self.assertEqual(later(b''), b'')
        self.wait_idle(addon)
        self.assertEqual(seen, [payload])
        self.assertEqual(addon.transport_window.state, 'ACTIVE')

    def wait_idle(self, addon):
        lane = addon.analysis
        with lane.condition:
            self.assertTrue(lane.condition.wait_for(
                lambda: not lane.queue and not lane.processing, timeout=3))

    def test_gzip_binary_chunks_are_unchanged_and_decompressed_only_in_worker(self):
        bodies, threads = [], []
        window, addon, _ = self.setup_stream(lambda _: None)
        self.addCleanup(addon.finish_analysis)
        collector = BodyCollector(window, 'gzip',
            lambda body: (bodies.append(body), threads.append(threading.get_ident())))
        window.collectors.append(collector)
        stream = addon._stream(collector)
        compressed = gzip.compress(b'{"synthetic":"payload"}')
        parts = [compressed[:5], compressed[5:12], compressed[12:], b'']
        for part in parts:
            self.assertIs(stream(part), part)
        self.wait_idle(addon)
        self.assertEqual(bodies, [b'{"synthetic":"payload"}'])
        self.assertNotEqual(threads, [threading.get_ident()])

    def test_full_queue_drops_observation_without_blocking_or_closing_transport(self):
        window, addon, stream = self.setup_stream(lambda _: self.fail('partial body parsed'))
        self.addCleanup(addon.finish_analysis)
        lane = addon.analysis
        lane.MAX_CHUNKS = 1
        # Stall just the consumer. The producer must not acquire this lock.
        with lane.lock:
            for _ in range(4):
                data = b'copy'
                self.assertIs(stream(data), data)
            self.assertEqual(stream(b''), b'')
            self.assertEqual(lane.diagnostic()['failure'], 'COPY_QUEUE_LIMIT')
            self.assertEqual(lane.queued_bytes, 0)
            self.assertTrue(lane.diagnostic()['coverage_incomplete'])
            self.assertTrue(lane.diagnostic()['accepting_copies'])
            self.assertEqual(lane.diagnostic()['recovery'], 'CONTINUING')
            self.assertEqual(addon.transport_window.state, 'ACTIVE')
        addon.finish_analysis()
        self.assertEqual(window.collectors, [])

    def test_busy_parser_skips_whole_response_before_headers_or_body_read(self):
        _, addon, _ = self.setup_stream(lambda _: None)
        self.addCleanup(addon.finish_analysis)
        class Response:
            @property
            def headers(self):
                raise AssertionError('headers of skipped copy accessed')
            @property
            def content(self):
                raise AssertionError('body of skipped copy accessed')
        flow = SimpleNamespace(id='busy', response=Response())
        addon.route_slots['busy'] = 0
        with addon.analysis.lock:
            addon.responseheaders(flow)
        self.assertIs(flow.response.stream, True)
        self.assertNotIn('busy', addon.route_slots)
        self.assertIsNone(addon.analysis.diagnostic()['failure'])
        self.assertTrue(addon.analysis.diagnostic()['coverage_incomplete'])
        self.assertEqual(addon.analysis.diagnostic()['recovery'], 'CONTINUING')
        self.assertGreater(addon.analysis.diagnostic()['skipped_headers'], 0)

    def test_response_time_is_receipt_time_not_worker_processing_time(self):
        from collection_adapter.observation_time import observation_time
        times = []
        _, addon, stream = self.setup_stream(lambda _: times.append(observation_time()))
        self.addCleanup(addon.finish_analysis)
        stamp = '2026-01-01T00:00:00+00:00'
        with addon.analysis.lock:
            stream(b'{}')
            with patch('collection_adapter.detached_analysis.datetime') as dt:
                dt.now.return_value.isoformat.return_value = stamp
                stream(b'')
        self.wait_idle(addon)
        self.assertEqual(times, [stamp])

    def test_request_copy_uses_same_nonblocking_lane_and_preserves_form_bytes(self):
        from collection_adapter.p26_public_projection import PUBLIC_PATHS, FOOD_ROUTE
        window = IdentificationWindow('Synthetic shop', duration_seconds=None)
        window.inspect_current_domain('wx.waimai.meituan.com')
        window.start_once()
        window.key_layout_only = True
        window.public_projection_paths = dict(PUBLIC_PATHS)
        addon = IdentificationAddon(window, batch_public_json=True)
        self.addCleanup(addon.finish_analysis)
        flow = SimpleNamespace(id='form', client_conn=SimpleNamespace(sni='wx.waimai.meituan.com'),
            request=SimpleNamespace(method='POST', host='wx.waimai.meituan.com', path=FOOD_ROUTE,
                                    headers={'content-type': 'application/x-www-form-urlencoded'}))
        with patch('collection_adapter.p26_identification_host._emit'):
            addon.requestheaders(flow)
        data = b'poi_id_str=synthetic&wm_poi_id=-42'
        with addon.analysis.lock:
            self.assertIs(flow.request.stream(data), data)
            self.assertEqual(flow.request.stream(b''), b'')
            self.assertFalse(window.request_leases)
        self.wait_idle(addon)
        self.assertEqual(window.request_leases[addon.request_refs['form']]['body'], data)

    def test_complete_synthetic_pair_still_publishes_matching_results(self):
        from collection_adapter.tests.test_p29_store_pages import StorePagesTests
        from collection_adapter.tests.test_p28_business_batch import bodies
        fixture = StorePagesTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.temp.cleanup)
        window = fixture.window
        addon = IdentificationAddon(window, batch_public_json=True)
        self.addCleanup(addon.finish_analysis)
        for slot, body in enumerate(bodies()):
            ref = 'request:synthetic_' + str(slot)
            window.request_leases[ref] = {'body': b'poi_id_str=public_synthetic_42&wm_poi_id=-42',
                'keys': ['poi_id_str', 'wm_poi_id'], 'route_slot': slot, 'expires_at': 160}
            flow = SimpleNamespace(id=str(slot), response=SimpleNamespace(status_code=200,
                headers={'content-type': 'application/json'}, stream=True))
            addon.route_slots[flow.id] = slot
            addon.request_refs[flow.id] = ref
            addon.responseheaders(flow)
            data = json.dumps(body).encode()
            self.assertIs(flow.response.stream(data), data)
            self.assertEqual(flow.response.stream(b''), b'')
            self.wait_idle(addon)
        self.assertEqual(len(window.snapshots), 1)
        public = json.loads(next(fixture.root.glob('observation_*-public-fields.json')).read_text())
        self.assertTrue(public['source_association']['store_name_match'])
        self.assertEqual(len(list(fixture.root.glob('observation_*'))), 2)
        addon.finish_analysis()
        self.assertIsNotNone(window.collection_receipt)

    def test_stopping_discards_pending_copies_and_late_chunks_still_pass(self):
        _, addon, stream = self.setup_stream(lambda _: self.fail('partial input parsed'))
        stream(b'partial')
        self.wait_idle(addon)
        addon.finish_analysis()
        self.assertEqual(addon.window.collectors, [])
        self.assertEqual(addon.analysis.queued_bytes, 0)
        self.assertFalse(addon.analysis.accepting)
        late = b'late unchanged'
        self.assertIs(stream(late), late)

    def test_bad_encoding_disables_copy_without_breaking_response_stream(self):
        window, addon, _ = self.setup_stream(lambda _: None)
        self.addCleanup(addon.finish_analysis)
        addon.route_slots['bad'] = 0
        flow = SimpleNamespace(id='bad', response=SimpleNamespace(status_code=200,
            headers={'content-encoding': 'unsupported-synthetic'}, stream=False))
        addon.responseheaders(flow)
        self.assertIs(flow.response.stream, True)
        diagnostic = addon.analysis.diagnostic()
        self.assertEqual(diagnostic['failure'], 'ANALYSIS_REJECTED')
        self.assertTrue(diagnostic['accepting_copies'])
        self.assertEqual(diagnostic['recovery'], 'CONTINUING')
        self.assertTrue(diagnostic['coverage_incomplete'])
        self.assertEqual(addon.window.state, 'ACTIVE')
        addon.finish_analysis()
        self.assertEqual(addon.transport_window.state, 'ACTIVE')

    def test_parser_busy_does_not_block_transport_dispatch_or_status(self):
        entered, release = threading.Event(), threading.Event()
        def consume(_):
            entered.set()
            release.wait(3)
        _, addon, stream = self.setup_stream(consume)
        stream(b'{}'); stream(b'')
        self.assertTrue(entered.wait(1))
        from collection_adapter.p26_identification_host import PIDStreamGate
        class Stream:
            def get_extra_info(self, _key, _default): return 123
            def close(self): raise AssertionError('transport closed by parser')
        forwarded = []
        async def dispatch(_):
            await asyncio.sleep(0)
            forwarded.append(True)
        async def check():
            gate = PIDStreamGate(addon.transport_window, 123, dispatch,
                                 diagnostic=addon.forwarding)
            await asyncio.wait_for(gate(Stream()), .5)
            status = addon.diagnostic()
            self.assertEqual(status['state'], 'ACTIVE')
            self.assertEqual(status['live_capture_latch'], 'OPEN')
            # Manual transport stop is independent of the busy parser lock.
            addon.transport_window.close('P26_CANCELLED')
            self.assertEqual(addon.transport_window.state, 'CLOSED')
        try:
            asyncio.run(check())
        finally:
            release.set()
            addon.finish_analysis()
        self.assertEqual(forwarded, [True])

    def test_idle_analysis_expires_partial_body_without_transport_activity(self):
        window, addon, stream = self.setup_stream(lambda _: self.fail('partial input parsed'))
        self.addCleanup(addon.finish_analysis)
        clock = [window.last_clock]
        window.clock = lambda: clock[0]
        stream(b'partial')
        self.wait_idle(addon)
        clock[0] += 61
        with addon.analysis.condition:
            self.assertTrue(addon.analysis.condition.wait_for(
                lambda: addon.analysis._snapshot['state'] == 'CLOSED', timeout=2))
        self.assertEqual(window.collectors, [])
        self.assertEqual(addon.transport_window.state, 'ACTIVE')

    def test_unavailable_worker_only_drops_copy(self):
        _, addon, stream = self.setup_stream(lambda _: self.fail('no worker expected'))
        self.addCleanup(addon.finish_analysis)
        data = b'unchanged'
        with patch('threading.Thread.start', side_effect=RuntimeError('synthetic failure')):
            self.assertIs(stream(data), data)
        self.assertEqual(stream(b''), b'')
        self.assertEqual(addon.analysis.diagnostic()['failure'], 'WORKER_UNAVAILABLE')
        self.assertEqual(addon.analysis.diagnostic()['recovery'], 'STOPPED')
        self.assertFalse(addon.analysis.diagnostic()['accepting_copies'])
        self.assertEqual(addon.analysis.queued_bytes, 0)
        self.assertEqual(addon.transport_window.state, 'ACTIVE')

    def test_detached_category_still_requires_own_store_request_before_copy(self):
        from collection_adapter.tests.test_p29_category_render import CategoryRenderTests
        fixture = CategoryRenderTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.pair()
        addon = IdentificationAddon(fixture.window, batch_public_json=True)
        self.addCleanup(addon.finish_analysis)
        for index, matching in enumerate((False, True)):
            ref = fixture.lease(b'poi_id_str=public_synthetic_42&wm_poi_id=-42' if matching
                                else b'poi_id_str=other_synthetic&wm_poi_id=-42')
            identity = 'category-' + str(index)
            addon.route_slots[identity] = 2
            addon.request_refs[identity] = ref
            flow = SimpleNamespace(id=identity, response=SimpleNamespace(status_code=200,
                headers={'content-type': 'application/json'}, stream=False))
            addon.responseheaders(flow)
            if not matching:
                self.assertIs(flow.response.stream, True)
                self.assertFalse(list(fixture.root.glob('category_render_*')))
            else:
                data = b'{"code":0,"data":{"synthetic_products":[{"id":101,"price":15.2}]}}'
                self.assertIs(flow.response.stream(data), data)
                self.assertEqual(flow.response.stream(b''), b'')
                self.wait_idle(addon)
                self.assertEqual(fixture.window.render_inspector.inspected, 1)
                result = json.loads(next(fixture.root.glob('category_render_*-public-fields.json')).read_text())
                self.assertTrue(result['shop_scope_verified'])
                self.assertFalse(result['sensitive_values_processed'])

    def test_copy_diagnostic_is_closed_and_contains_no_body_or_error_text(self):
        from pathlib import Path
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('schema interpreter required')
        _, addon, _ = self.setup_stream(lambda _: None)
        self.addCleanup(addon.finish_analysis)
        path = Path(__file__).resolve().parents[2] / 'contracts/schemas/detached-copy-analysis-v1.schema.json'
        validator = Draft202012Validator(json.loads(path.read_text()))
        report = addon.analysis.diagnostic()
        validator.validate(report)
        self.assertEqual(report['recovery'], 'CONTINUING')
        self.assertFalse(validator.is_valid({**report, 'error': 'synthetic private text'}))
        self.assertFalse(validator.is_valid({**report, 'failure': 'synthetic arbitrary text'}))
        self.assertFalse(validator.is_valid({**report, 'recovery': 'synthetic'}))


@unittest.skipUnless(importlib.util.find_spec('mitmproxy'), 'installed engine interpreter required')
class DetachedHostTests(unittest.IsolatedAsyncioTestCase):
    async def test_installed_engine_cannot_be_started_by_retired_host(self):
        from collection_adapter import p26_identification_host as host
        with patch('mitmproxy_rs.local.start_local_redirector') as redirector, \
                patch('mitmproxy.master.Master') as master, \
                patch.object(host, 'prepare') as prepare:
            result = await host.serve(Path('/synthetic'), analyze_store_pages=True,
                batch_public_json=True, key_layout_only=True, inspect_sensitive_fields=True,
                inspect_public_fields=True, route_inspection_domains=('example.invalid',))
        redirector.assert_not_called()
        master.assert_not_called()
        prepare.assert_not_called()
        self.assertEqual(result['code'], 'P29_COPY_SOURCE_UNAVAILABLE')
        self.assertFalse(result['transport_started'])
        self.assertEqual(result['new_attempts'], 0)


if __name__ == '__main__':
    unittest.main()
