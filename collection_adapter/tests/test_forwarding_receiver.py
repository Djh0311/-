"""Full start/copy/publish/stop checks using synthetic data and a fake transport."""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from collection_adapter import forwarding_receiver as receiver
from collection_adapter import p26_identification_host as host
from collection_adapter.p26_public_projection import FOOD_ROUTE, PRODUCT_ROUTE
from collection_adapter.tests.test_p28_business_batch import bodies


def prepared_state(root):
    refs = dict(runtime_target_ref='target:synthetic_current_01',
        target_binding_ref='target-binding:synthetic_current_01',
        target_confirmation_ref='target-confirmation:synthetic_current_01')
    return {**refs, 'identification_attempts': 0, 'result_attempts': 0,
        'live_capture_latch': 'CLOSED', 'execution_latch': 'CLOSED',
        'ca_directory': '/synthetic/unused-ca', 'output_root': str(root),
        'monitoring_authorization': {**refs, 'schema_version': 'p26-monitoring-authorization/v1',
            'scope_ref': 'monitoring:' + 'a' * 32,
            'user_decision': 'CURRENT_USER_NO_TIME_OR_ATTEMPT_LIMIT',
            'time_limit_seconds': None, 'attempt_limit': None},
        'public_business_batch': {**refs, 'schema_version': 'p26-public-business-batch-authorization/v1',
            'user_decision': 'CURRENT_USER_REQUESTED_BATCH_PUBLIC_BUSINESS_INPUT',
            'private_inputs': 'EXCLUDED', 'raw_persistence': False,
            'results_target': 'CURRENT_CONFIRMED_STORE'},
        'sensitive_field_inspection': {**refs,
            'user_decision': 'CURRENT_USER_ALLOWED_SENSITIVE_FIELD_INSPECTION',
            'inspection': 'KEY_PATH_TYPE_ONLY', 'field_values_processed': False,
            'raw_persistence': False}}


class FakeEngine:
    def __init__(self, addon, pid, ca_directory):
        self.addon, self.pid = addon, pid
        self.intercept_cleared, self.tasks = True, set()
        self.closed = asyncio.Event()
        self.activated = self.opened = False

    async def open(self):
        self.opened = True

    def activate(self):
        self.activated = True
        self.intercept_cleared = False

    async def watch(self):
        await self.closed.wait()

    async def close(self):
        self.intercept_cleared = True
        self.closed.set()
        return True


class ForwardingReceiverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.root.chmod(0o700)
        self.state = prepared_state(self.root)
        self.choice = {'store': 'Synthetic batch shop'}
        self.events = []
        for p in (patch.object(host, 'prepare', side_effect=lambda _: (self.state.copy(), self.choice.copy(), 123)),
                  patch.object(host, '_selected_pid', return_value=123),
                  patch.object(host, '_emit', side_effect=self.events.append),
                  patch.object(receiver, 'LocalForwardingEngine', FakeEngine)):
            p.start(); self.addCleanup(p.stop)

    async def idle(self, addon):
        for _ in range(200):
            with addon.analysis.condition:
                idle = not addon.analysis.queue and not addon.analysis.processing
            if idle:
                return
            await asyncio.sleep(.01)
        self.fail('synthetic copy worker did not finish')

    async def feed(self, addon, path, payload, identity):
        flow = SimpleNamespace(id=identity,
            client_conn=SimpleNamespace(sni=receiver.DOMAIN),
            request=SimpleNamespace(method='POST', host=receiver.DOMAIN, path=path,
                headers={'content-type': 'application/x-www-form-urlencoded'}, stream=False),
            response=SimpleNamespace(status_code=200, headers={'content-type': 'application/json'}, stream=False))
        addon.requestheaders(flow)
        form = b'poi_id_str=public_synthetic_42&wm_poi_id=-42'
        self.assertIs(flow.request.stream(form), form)
        self.assertEqual(flow.request.stream(b''), b'')
        addon.request(flow)
        await self.idle(addon)
        addon.responseheaders(flow)
        chunk = json.dumps(payload).encode()
        self.assertIs(flow.response.stream(chunk), chunk)
        self.assertEqual(flow.response.stream(b''), b'')
        addon.response(flow)
        await self.idle(addon)

    async def test_prepare_and_stop_never_construct_network_engine_or_consume_attempt(self):
        session = receiver.prepare_receiver(self.root)
        self.assertEqual(session.addon.window.allowed_domains, set(receiver.BUSINESS_DOMAINS))
        commands = asyncio.Queue()
        commands.put_nowait('status'); commands.put_nowait('stop')
        with patch.object(receiver, 'LocalForwardingEngine') as engine:
            result = await receiver.run_receiver(session, commands)
        engine.assert_not_called()
        self.assertEqual(result['new_attempts'], 0)
        self.assertEqual(result['diagnostic']['live_capture_latch'], 'CLOSED')
        self.assertEqual(result['cleanup'], 'COMPLETE')
        self.assertIs(await session.close(), result)
        self.assertFalse(list(self.root.iterdir()))

    async def test_real_addon_copies_a_synthetic_pair_and_publishes_after_forwarding(self):
        session = receiver.prepare_receiver(self.root)
        self.addAsyncCleanup(session.close)
        self.assertEqual(session.transport.state, 'PREPARED')
        await session.start()
        opened = json.loads((self.root / 'transport-state.json').read_text())
        self.assertEqual((opened['result_attempts'], opened['live_capture_latch']), (1, 'OPEN'))
        food, product = bodies()
        await self.feed(session.addon, FOOD_ROUTE, food, 'synthetic-food')
        await self.feed(session.addon, PRODUCT_ROUTE, product, 'synthetic-product')
        self.assertEqual(len(session.addon.window.snapshots), 0)
        self.assertEqual(session.addon.full_capture.saved, 2)
        finish = session.addon.finish_analysis
        def finish_after_release(code):
            self.assertTrue(session.engine.intercept_cleared)
            finish(code)
        with patch.object(session.addon, 'finish_analysis', side_effect=finish_after_release):
            result = await session.close()
        state = json.loads((self.root / 'transport-state.json').read_text())
        self.assertEqual((state['result_attempts'], state['live_capture_latch'], state['execution_latch']),
                         (1, 'CLOSED', 'CLOSED'))
        self.assertFalse((self.root / receiver.LOCK).exists())
        self.assertEqual(result['cleanup'], 'COMPLETE')
        self.assertEqual(len(list((self.root / 'captured-http').glob('*.json'))) - 1, 2)
        for path in self.root.rglob('*.json'):
            if path.parent.name != 'captured-http' or path.name == 'status.json':
                self.assertNotIn('PRIVATE_VALUE', path.read_text())

    async def test_double_start_is_one_attempt_and_stop_clears_the_engine(self):
        session = receiver.prepare_receiver(self.root)
        commands = asyncio.Queue()
        commands.put_nowait('start')
        running = asyncio.create_task(receiver.run_receiver(session, commands))
        for _ in range(200):
            if any(row['event'] == 'P29_FORWARDING_STARTED' for row in self.events):
                break
            await asyncio.sleep(.01)
        for command in ('start', 'status', 'stop'):
            commands.put_nowait(command)
        result = await asyncio.wait_for(running, 2)
        self.assertEqual(result['new_attempts'], 1)
        self.assertEqual([row['event'] for row in self.events], ['P29_RECEIVER_PREPARED',
            'P29_FORWARDING_STARTED', 'P29_START_ALREADY_USED', 'P29_FORWARDING_STATUS', 'P29_FORWARDING_CLOSED'])
        self.assertTrue(result['intercept_cleared'])

    async def test_store_detail_body_is_forwarded_and_public_copy_is_saved_without_a_product_pair(self):
        import gzip
        from jsonschema import Draft202012Validator
        session = receiver.prepare_receiver(self.root)
        self.addAsyncCleanup(session.close)
        await session.start()
        addon = session.addon
        flow = SimpleNamespace(id='synthetic-store-detail',
            client_conn=SimpleNamespace(sni=receiver.DOMAIN),
            request=SimpleNamespace(method='POST', host=receiver.DOMAIN,
                path='/weapp/shop/v1/poi/detail', headers={}, stream=False),
            response=SimpleNamespace(status_code=200,
                headers={'content-type': 'application/json', 'content-encoding': 'gzip'}, stream=False))
        addon.requestheaders(flow)
        self.assertTrue(callable(flow.request.stream))
        addon.request(flow)
        addon.responseheaders(flow)
        self.assertTrue(callable(flow.response.stream))
        body = gzip.compress(json.dumps({'code': 0, 'data': {
            'name': 'Synthetic batch shop', 'address': 'Synthetic public address',
            'shipping_time': 'Synthetic delivery period',
            'user': {'address': 'PRIVATE_VALUE'}, 'token': 'PRIVATE_VALUE'}}).encode())
        self.assertIs(flow.response.stream(body), body)
        self.assertEqual(flow.response.stream(b''), b'')
        addon.response(flow)
        await self.idle(addon)
        with addon.analysis.lock:
            pass
        self.assertFalse(list(self.root.glob('store_detail_*-public-fields.json')))
        meta_path = self.root / 'captured-http' / '000001.json'
        saved = json.loads(meta_path.read_text())
        self.assertEqual(saved['path'], '/weapp/shop/v1/poi/detail')
        self.assertEqual(saved['content_encoding'], 'gzip')
        self.assertNotIn('PRIVATE_VALUE', meta_path.read_text())
        self.assertEqual(meta_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / 'captured-http' / '000001.response').read_bytes(), body)
        self.assertEqual(addon.window.request_leases, {})
        self.assertEqual(session.status()['copy_analysis']['completed_streams'], 0)
        self.assertEqual(session.status()['diagnostic']['store_detail']['saved_responses'], 0)
        self.assertEqual(session.transport.state, 'ACTIVE')
        schema = json.loads((Path(__file__).resolve().parents[2] /
            'contracts/schemas/p29-store-detail-public-copy-v1.schema.json').read_text())
        self.assertFalse(Draft202012Validator(schema).is_valid({**saved, 'raw_body': 'PRIVATE_VALUE'}))
        diagnostic_schema = json.loads((Path(__file__).resolve().parents[2] /
            'contracts/schemas/p29-store-pages-diagnostic-v1.schema.json').read_text())
        Draft202012Validator(diagnostic_schema).validate(session.status()['diagnostic'])

    async def test_rejected_detail_copy_does_not_stop_later_detail_or_product_copies(self):
        session = receiver.prepare_receiver(self.root)
        self.addAsyncCleanup(session.close)
        await session.start()
        addon = session.addon
        slot = addon.window.route('POST', receiver.DOMAIN,
            '/weapp/shop/v1/poi/detail', tls_domain=receiver.DOMAIN)
        addon.window.select_route(slot)
        collector = addon.window.begin_response(slot, 'identity')
        callback = addon._stream(collector)
        invalid = b'{"code": 0, "data":'
        self.assertIs(callback(invalid), invalid)
        callback(b'')
        await self.idle(addon)
        with addon.analysis.lock:
            pass
        self.assertTrue(addon.analysis.diagnostic()['accepting_copies'])
        self.assertEqual(addon.window.diagnostic()['store_detail']['rejected_responses'], 1)
        self.assertFalse(list(self.root.glob('store_detail_*-public-fields.json')))
        food, product = bodies()
        await self.feed(addon, FOOD_ROUTE, food, 'synthetic-food-after-detail')
        await self.feed(addon, PRODUCT_ROUTE, product, 'synthetic-product-after-detail')
        self.assertEqual(len(addon.window.snapshots), 0)
        self.assertEqual(addon.full_capture.saved, 2)
        self.assertEqual(session.transport.state, 'ACTIVE')

    async def test_nearby_routes_and_non_json_detail_responses_are_only_forwarded(self):
        session = receiver.prepare_receiver(self.root)
        self.addAsyncCleanup(session.close)
        await session.start()
        for number, (path, status, content_type) in enumerate((
                ('/weapp/shop/v1/poi/details', 200, 'application/json'),
                ('/weapp/shop/v1/poi/detail', 503, 'application/json'),
                ('/weapp/shop/v1/poi/detail', 200, 'text/html'))):
            flow = SimpleNamespace(id='synthetic-ignored-' + str(number),
                client_conn=SimpleNamespace(sni=receiver.DOMAIN),
                request=SimpleNamespace(method='POST', host=receiver.DOMAIN,
                    path=path, headers={}, stream=False),
                response=SimpleNamespace(status_code=status,
                    headers={'content-type': content_type}, stream=False))
            session.addon.requestheaders(flow)
            session.addon.request(flow)
            session.addon.responseheaders(flow)
            self.assertTrue(callable(flow.request.stream))
            self.assertTrue(callable(flow.response.stream))
            session.addon.response(flow)
        self.assertFalse(list(self.root.glob('store_detail_*-public-fields.json')))
        self.assertEqual(session.status()['copy_analysis']['completed_streams'], 0)

    async def test_failed_response_header_wait_preserves_later_pair_publication(self):
        session = receiver.prepare_receiver(self.root)
        self.addAsyncCleanup(session.close)
        await session.start()
        addon = session.addon
        failed = SimpleNamespace(id='synthetic-missing-response',
            client_conn=SimpleNamespace(sni=receiver.DOMAIN))
        addon.http_progress.begin(failed.id, 0)
        addon.http_progress.request_complete(failed.id)
        addon.error(failed)
        diagnostic = addon.analysis.diagnostic()
        self.assertTrue(diagnostic['accepting_copies'])
        self.assertIsNone(diagnostic['failure'])
        self.assertTrue(diagnostic['coverage_incomplete'])
        self.assertEqual(diagnostic['dropped_copies'], 1)
        self.assertEqual(addon.http_progress_snapshot()['last_failure_phase'], 'RESPONSE_HEADERS')
        food, product = bodies()
        await self.feed(addon, FOOD_ROUTE, food, 'synthetic-later-food')
        await self.feed(addon, PRODUCT_ROUTE, product, 'synthetic-later-product')
        self.assertEqual(len(addon.window.snapshots), 0)
        self.assertEqual(addon.full_capture.saved, 2)
        self.assertEqual(session.transport.state, 'ACTIVE')
        result = await session.close()
        self.assertEqual(result['cleanup'], 'COMPLETE')
        self.assertFalse(list(self.root.glob('collection_*/records.json')))

    async def test_status_and_close_expose_existing_forwarding_counts(self):
        session = receiver.prepare_receiver(self.root)
        self.addAsyncCleanup(session.close)
        self.assertIsNone(session.status()['forwarding'])
        await session.start()
        session.engine.gate = host.PIDStreamGate(session.transport, 123, None)
        session.engine.gate.peak_concurrent = 2
        for domain in ('other.invalid', receiver.DOMAIN):
            session.addon.tls_clienthello(SimpleNamespace(
                client_hello=SimpleNamespace(sni=domain)))
        session.addon.server_connected(None)
        snapshot = session.status()['forwarding']
        self.assertEqual(snapshot['selected_tls_hellos'], 2)
        self.assertEqual(snapshot['ignored_tls_hellos'], 0)
        self.assertEqual(snapshot['upstream_connected'], 1)
        self.assertEqual(snapshot['http_requests'], 0)
        self.assertEqual(snapshot['peak_active_streams'], 2)
        self.assertEqual((await session.close())['forwarding'], snapshot)

    async def test_pid_change_before_activation_closes_prepared_engine_without_an_attempt(self):
        session = receiver.prepare_receiver(self.root)
        commands = asyncio.Queue(); commands.put_nowait('start')
        with patch.object(host, '_selected_pid', return_value=124):
            result = await receiver.run_receiver(session, commands)
        self.assertFalse(session.engine.activated)
        self.assertEqual((result['new_attempts'], result['cleanup']), (0, 'COMPLETE'))
        self.assertFalse((self.root / receiver.LOCK).exists())

    async def test_activation_error_is_closed_and_never_retried(self):
        session = receiver.prepare_receiver(self.root)
        commands = asyncio.Queue(); commands.put_nowait('start'); commands.put_nowait('start')
        with patch.object(FakeEngine, 'activate', side_effect=RuntimeError('synthetic private error')):
            result = await receiver.run_receiver(session, commands)
        self.assertEqual(result['new_attempts'], 1)
        self.assertEqual(result['cleanup'], 'COMPLETE')
        self.assertEqual(result['diagnostic']['execution_latch'], 'CLOSED')
        self.assertNotIn('synthetic private error', json.dumps(self.events))
        self.assertFalse(any(e['event'] == 'P29_FORWARDING_STARTED' for e in self.events))

    async def test_stop_during_engine_setup_prevents_activation(self):
        session = receiver.prepare_receiver(self.root)
        commands = asyncio.Queue(); commands.put_nowait('start')
        opened = asyncio.Event()
        async def opening(engine):
            opened.set()
            await asyncio.Future()
        with patch.object(FakeEngine, 'open', opening):
            running = asyncio.create_task(receiver.run_receiver(session, commands))
            await asyncio.wait_for(opened.wait(), 2)
            commands.put_nowait('stop')
            result = await asyncio.wait_for(running, 2)
        self.assertFalse(session.engine.activated)
        self.assertEqual((result['new_attempts'], result['cleanup']), (0, 'COMPLETE'))
        self.assertTrue(session.engine.closed.is_set())

    async def test_failed_cleanup_retains_lock_and_reports_incomplete(self):
        session = receiver.prepare_receiver(self.root)
        await session.start()
        with patch.object(FakeEngine, 'close', new=AsyncMock(return_value=False)):
            result = await session.close()
        self.assertEqual(result['cleanup'], 'INCOMPLETE')
        self.assertFalse(result['intercept_cleared'])
        self.assertTrue((self.root / receiver.LOCK).exists())
        self.assertEqual(result['diagnostic']['live_capture_latch'], 'OPEN')
        self.assertEqual(json.loads((self.root / 'transport-state.json').read_text())['live_capture_latch'], 'OPEN')

    async def test_used_root_and_missing_scope_refuse_before_engine(self):
        for changed in ({'result_attempts': 1}, {'public_business_batch': None}):
            with self.subTest(changed=changed):
                previous = self.state
                self.state = {**previous, **changed}
                with self.assertRaises(host.IdentificationError):
                    receiver.prepare_receiver(self.root)
                self.state = previous
        host._write_new(self.root, receiver.LOCK, {'synthetic': True})
        with self.assertRaisesRegex(host.IdentificationError, 'P26_WINDOW_ALREADY_USED'):
            receiver.prepare_receiver(self.root)

    async def test_small_trial_has_one_attempt_and_a_two_minute_transport_deadline(self):
        self.state['monitoring_authorization'].update(
            user_decision='CURRENT_USER_REQUESTED_ONE_SMALL_TRIAL', time_limit_seconds=120, attempt_limit=1)
        session = receiver.prepare_receiver(self.root)
        self.assertEqual(session.transport.duration_seconds, 120)
        await session.start()
        self.assertEqual(session.transport.deadline - session.transport.last_clock, 120)
        await session.close()
        for changed in ({'time_limit_seconds': None}, {'attempt_limit': None}, {'attempt_limit': True}):
            scope = {**self.state['monitoring_authorization'], **changed}
            with self.assertRaisesRegex(host.IdentificationError, 'P26_MONITORING_SCOPE_INVALID'):
                host._monitoring_approved({**self.state, 'monitoring_authorization': scope})

    async def test_continuous_receiving_stays_open_past_two_minutes_until_stop(self):
        self.state['monitoring_authorization'].update(
            user_decision='CURRENT_USER_REQUESTED_CONTINUOUS_RECEIVING',
            time_limit_seconds=None, attempt_limit=1)
        session = receiver.prepare_receiver(self.root)
        self.addAsyncCleanup(session.close)
        await session.start()
        self.assertIsNone(session.transport.deadline)
        later = session.transport.last_clock + 3600
        session.transport.clock = lambda: later
        self.assertTrue(session.transport.active())
        self.assertEqual(session.status()['diagnostic']['live_capture_latch'], 'OPEN')
        self.assertEqual(session.status()['new_attempts'], 1)
        result = await session.close('P26_HOST_CLOSED')
        self.assertEqual(result['diagnostic']['live_capture_latch'], 'CLOSED')
        self.assertTrue(result['intercept_cleared'])
        for changed in ({'time_limit_seconds': 120}, {'attempt_limit': None},
                        {'attempt_limit': True}, {'attempt_limit': 2}):
            scope = {**self.state['monitoring_authorization'], **changed}
            with self.assertRaisesRegex(host.IdentificationError, 'P26_MONITORING_SCOPE_INVALID'):
                host._monitoring_approved({**self.state, 'monitoring_authorization': scope})

    async def test_receiver_loss_releases_interception_without_waiting_for_next_command(self):
        session = receiver.prepare_receiver(self.root)
        commands = asyncio.Queue(); commands.put_nowait('start')
        async def lost(engine):
            engine.addon.transport_window.close('P26_RECEIVER_LOST')
        with patch.object(FakeEngine, 'watch', lost):
            result = await asyncio.wait_for(receiver.run_receiver(session, commands), 2)
        self.assertEqual(result['diagnostic']['code'], 'P26_RECEIVER_LOST')
        self.assertTrue(result['intercept_cleared'])
        self.assertEqual(result['cleanup'], 'COMPLETE')

    async def test_engine_setup_failure_is_cleaned_before_start_event(self):
        session = receiver.prepare_receiver(self.root)
        commands = asyncio.Queue(); commands.put_nowait('start')
        with patch.object(FakeEngine, 'open', new=AsyncMock(side_effect=RuntimeError('synthetic error'))):
            result = await receiver.run_receiver(session, commands)
        self.assertEqual((result['new_attempts'], result['cleanup']), (0, 'COMPLETE'))
        self.assertTrue(session.engine.closed.is_set())
        self.assertFalse(any(e['event'] == 'P29_FORWARDING_STARTED' for e in self.events))

    async def test_setup_timeout_is_distinct_and_does_not_consume_capture_attempt(self):
        session = receiver.prepare_receiver(self.root)
        commands = asyncio.Queue(); commands.put_nowait('start')
        async def never_ready(engine):
            engine.setup_stage = 'REDIRECTOR_CONNECTION'
            await asyncio.Future()
        with patch.object(FakeEngine, 'open', never_ready), \
                patch.object(receiver, 'SETUP_TIMEOUT_SECONDS', .01):
            result = await receiver.run_receiver(session, commands)
        self.assertEqual(result['diagnostic']['code'], 'P26_RECEIVER_SETUP_TIMEOUT')
        self.assertEqual(result['setup_stage'], 'REDIRECTOR_CONNECTION')
        self.assertEqual(result['setup_failure'], 'TIMEOUT')
        self.assertEqual(result['new_attempts'], 0)
        self.assertEqual(result['cleanup'], 'COMPLETE')


@unittest.skipUnless(importlib.util.find_spec('mitmproxy'), 'installed engine interpreter required')
class InstalledForwardingEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_installed_engine_wiring_has_no_automatic_listener_or_body_storage(self):
        from collection_adapter.p26_identification import IdentificationWindow
        window = IdentificationWindow('Synthetic shop')
        addon = host.IdentificationAddon(window)
        engine = receiver.LocalForwardingEngine(addon, 123, '/synthetic/ca')
        calls = []
        class Server:
            def set_intercept(self, spec): calls.append(spec)
            def close(self): calls.append('close')
            async def wait_closed(self): pass
        store = SimpleNamespace(default_ca=SimpleNamespace(has_expired=lambda: False))
        async def connect_existing(*args):
            self.assertEqual(os.environ.get('MITMPROXY_KEEP_REDIRECTOR'), '1')
            return Server()
        previous_keep = os.environ.get('MITMPROXY_KEEP_REDIRECTOR')
        try:
            with patch.object(host, '_redirector_present', return_value=True), \
                    patch('mitmproxy.certs.CertStore.from_store', return_value=store), \
                    patch('mitmproxy_rs.local.start_local_redirector', new=AsyncMock(side_effect=connect_existing)) as start, \
                    patch('asyncio.open_connection', new=AsyncMock(side_effect=AssertionError('network opened'))):
                await engine.open()
                self.assertEqual(addon.transport_window.state, 'PREPARED')
                self.assertEqual(addon.forwarding.counts['engine_errors'], 0)
                self.assertFalse(engine.master.options.server)
                self.assertEqual(engine.master.options.mode, [])
                self.assertFalse(engine.master.options.store_streamed_bodies)
                self.assertFalse(engine.master.options.ssl_insecure)
                self.assertEqual(engine.master.options.tls_version_client_min, 'TLS1_2')
                self.assertEqual(engine.master.options.tls_version_server_min, 'TLS1_2')
                self.assertEqual(engine.master.options.connection_strategy, 'eager')
                self.assertEqual(calls, ['123,!123'])
                self.assertEqual(engine.setup_stage, 'READY')
                self.assertEqual(os.environ.get('MITMPROXY_KEEP_REDIRECTOR'), previous_keep)
                self.assertIs(start.call_args.args[0].__self__, engine)
                engine.activate()
                self.assertTrue(await engine.close())
                self.assertEqual(calls, ['123,!123', '123', '123,!123', 'close'])
        finally:
            addon.finish_analysis()


if __name__ == '__main__':
    unittest.main()
