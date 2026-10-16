"""Synthetic HTTP phase evidence; never open a socket or inspect a body."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None

from collection_adapter import p26_identification_host as host
from collection_adapter.p26_identification import IdentificationWindow


class Flow:
    def __init__(self, identity='synthetic-flow'):
        self.id = identity
        self.client_conn = SimpleNamespace(sni='example.invalid')
        self.request = SimpleNamespace(method='GET', host='example.invalid', path='/catalog/list')
        self.response = SimpleNamespace(status_code=200, headers={})

    @property
    def error(self):
        raise AssertionError('private error read')


class HTTPProgressTests(unittest.TestCase):
    def setUp(self):
        self.window = IdentificationWindow('Synthetic shop', duration_seconds=None)
        self.window.inspect_current_domain('example.invalid')
        self.window.start_once()
        self.window.domain('example.invalid')
        self.addon = host.IdentificationAddon(self.window, detached_analysis=False)
        self.now = [100.0]
        self.addon.http_progress.clock = lambda: self.now[0]
        self.emit = patch.object(host, '_emit').start()
        self.addCleanup(patch.stopall)

    def snapshot(self):
        return self.addon.http_progress.snapshot(self.window.window_ref, self.window.state)

    def test_response_headers_cannot_be_mistaken_for_response_completion(self):
        flow = Flow()
        self.addon.requestheaders(flow)
        self.assertEqual(self.snapshot()['pending_by_phase']['REQUEST_BODY'], 1)
        self.addon.request(flow)
        self.assertEqual(self.snapshot()['pending_by_phase']['RESPONSE_HEADERS'], 1)
        self.addon.responseheaders(flow)
        self.now[0] += 31
        before = self.snapshot()
        self.assertEqual(self.addon.forwarding.counts['http_responses'], 1)
        self.assertEqual(before['http_responses_completed'], 0)
        self.assertEqual(before['pending_by_phase']['RESPONSE_BODY'], 1)
        self.assertEqual(before['oldest_wait_by_phase']['RESPONSE_BODY'], 'GE_30S')
        self.addon.response(flow)
        after = self.snapshot()
        self.assertEqual(after['http_responses_completed'], 1)
        self.assertEqual(sum(after['pending_by_phase'].values()), 0)
        self.assertEqual(after['oldest_wait_by_phase']['RESPONSE_BODY'], 'NONE')
        self.assertEqual(self.window.state, 'ACTIVE')

    def test_failure_records_only_fixed_phase_and_current_route_slot(self):
        for stage in ('REQUEST_BODY', 'RESPONSE_HEADERS', 'RESPONSE_BODY'):
            with self.subTest(stage=stage):
                self.window = IdentificationWindow('Synthetic shop', duration_seconds=None)
                self.window.inspect_current_domain('example.invalid')
                self.window.start_once()
                self.window.domain('example.invalid')
                self.addon = host.IdentificationAddon(self.window, detached_analysis=False)
                flow = Flow()
                self.addon.requestheaders(flow)
                if stage != 'REQUEST_BODY':
                    self.addon.request(flow)
                if stage == 'RESPONSE_BODY':
                    self.addon.responseheaders(flow)
                self.addon.error(flow)
                result = self.snapshot()
                self.assertEqual(result['last_failure_phase'], stage)
                self.assertEqual(result['last_failure_route_slot'], 0)
                self.assertEqual(result['http_failures'], 1)
                self.assertEqual(self.window.code, 'P26_FORWARDING_HTTP_FAILED')
                self.assertNotIn('example.invalid', json.dumps(result))
                self.assertNotIn('synthetic-flow', json.dumps(result))

    def test_close_preserves_unfinished_phase_without_leaving_active_tracking(self):
        flow = Flow()
        self.addon.requestheaders(flow)
        self.addon.request(flow)
        self.now[0] += 6
        self.window.close()
        self.addon.clear()
        result = self.snapshot()
        self.assertEqual(sum(result['pending_by_phase'].values()), 0)
        self.assertEqual(result['unfinished_at_close_by_phase']['RESPONSE_HEADERS'], 1)
        self.assertEqual(result['oldest_unfinished_at_close_by_phase']['RESPONSE_HEADERS'], '5_TO_30S')
        self.assertEqual(self.addon.http_progress.pending, {})
        self.assertEqual(result['http_failures'], 0)
        self.addon.http_progress.close()
        self.assertEqual(result, self.snapshot())

    def test_tracking_and_counter_limits_do_not_change_forwarding_or_attempts(self):
        progress = self.addon.http_progress
        for i in range(80):
            progress.begin('synthetic-' + str(i), 0)
        self.assertEqual(len(progress.pending), 64)
        self.assertTrue(self.snapshot()['tracking_incomplete'])
        for i in range(64):
            progress.complete('synthetic-' + str(i))
        for i in range(140):
            progress.begin('completed-' + str(i), 0)
            progress.complete('completed-' + str(i))
        self.assertEqual(self.snapshot()['http_responses_completed'], 128)
        self.assertTrue(self.snapshot()['counts_at_least'])
        self.assertEqual(self.window.state, 'ACTIVE')
        self.assertEqual(self.window.attempts, 1)

    def test_invalid_clock_is_unknown_and_never_closes_the_window(self):
        self.addon.requestheaders(Flow())
        self.now[0] = 99
        result = self.snapshot()
        self.assertFalse(result['clock_valid'])
        self.assertEqual(result['oldest_wait_by_phase']['REQUEST_BODY'], 'UNKNOWN')
        self.assertEqual(self.window.state, 'ACTIVE')

    def test_preparation_and_unselected_routes_do_not_start_tracking(self):
        prepared = IdentificationWindow('Synthetic shop', duration_seconds=None)
        addon = host.IdentificationAddon(prepared, detached_analysis=False)
        result = addon.http_progress.snapshot(prepared.window_ref, prepared.state)
        self.assertEqual(result['http_started'], 0)
        self.assertEqual(prepared.attempts, 0)
        flow = Flow()
        flow.client_conn.sni = 'other.invalid'
        self.addon.requestheaders(flow)
        self.addon.request(flow)
        self.addon.responseheaders(flow)
        self.addon.response(flow)
        self.assertEqual(self.snapshot()['http_started'], 0)
        self.assertEqual(self.snapshot()['http_responses_completed'], 0)
        self.assertEqual(self.window.state, 'ACTIVE')

    def test_duplicate_completion_does_not_inflate_counts(self):
        flow = Flow()
        self.addon.requestheaders(flow)
        self.addon.request(flow)
        self.addon.responseheaders(flow)
        self.addon.response(flow)
        self.addon.response(flow)
        result = self.snapshot()
        self.assertEqual(result['http_responses_completed'], 1)
        self.assertEqual(result['http_response_headers_received'], 1)

    def test_http_error_response_is_distinguishable_from_success_without_changing_forwarding(self):
        class UnreadableHeaders(dict):
            def get(self, *args):
                raise AssertionError('unselected response headers read')

        for number, status in enumerate((403, 200)):
            flow = Flow('synthetic-' + str(number))
            flow.request.path = '/catalog/detail' if number == 0 else '/catalog/list'
            flow.response.status_code = status
            flow.response.headers = UnreadableHeaders()
            self.addon.requestheaders(flow)
            self.addon.request(flow)
            self.addon.responseheaders(flow)
            self.addon.response(flow)
            self.assertIs(flow.request.stream, True)
            self.assertIs(flow.response.stream, True)
            self.assertEqual(flow.response.status_code, status)
        result = self.snapshot()
        self.assertEqual(result['http_responses_completed'], 2)
        self.assertEqual(result['http_failures'], 0)
        self.assertEqual(result['recent_responses'], [
            {'route_slot': 0, 'status_code': 403, 'outcome': 'RESPONSE_COMPLETE'},
            {'route_slot': 1, 'status_code': 200, 'outcome': 'RESPONSE_COMPLETE'},
        ])
        self.assertEqual(self.window.state, 'ACTIVE')

    def test_recent_responses_are_bounded_and_partial_response_remains_a_failure(self):
        progress = self.addon.http_progress
        for number in range(20):
            identity = 'synthetic-' + str(number)
            progress.begin(identity, number)
            progress.request_complete(identity)
            progress.response_headers(identity, 200)
            progress.complete(identity)
            progress.complete(identity)
        recent = self.snapshot()['recent_responses']
        self.assertEqual(len(recent), 16)
        self.assertEqual([row['route_slot'] for row in recent], list(range(4, 20)))
        progress.begin('partial', 20)
        progress.response_headers('partial', 502)
        progress.fail('partial')
        self.assertEqual(self.snapshot()['recent_responses'][-1],
            {'route_slot': 20, 'status_code': 502, 'outcome': 'TRANSPORT_FAILED'})
        self.assertEqual(self.snapshot()['http_responses_completed'], 20)
        progress.close()
        self.assertEqual(self.snapshot()['recent_responses'][-1]['outcome'], 'TRANSPORT_FAILED')

    def test_invalid_status_cannot_leak_into_recent_response_metadata(self):
        progress = self.addon.http_progress
        for number, status in enumerate(('private', True, 99, 600, None)):
            identity = 'synthetic-' + str(number)
            progress.begin(identity, 0)
            progress.response_headers(identity, status)
            progress.complete(identity)
        self.assertEqual([row['status_code'] for row in self.snapshot()['recent_responses']],
                         [None] * 5)
        self.assertNotIn('private', json.dumps(self.snapshot()))

    def test_optional_receipt_failure_does_not_interrupt_closed_state_or_leak_errors(self):
        class PrivateError(Exception):
            def __str__(self):
                raise AssertionError('private error text read')
        self.window.close()
        self.addon.clear()
        with patch.object(host, '_write_new', side_effect=PrivateError()):
            self.assertIsNone(host._persist_http_progress(Path('/synthetic'), self.addon))
        event = self.emit.call_args.args[0]
        self.assertEqual(event['event'], 'P26_FORWARDING_HTTP_PROGRESS_OUTPUT_INCOMPLETE')
        self.assertEqual(self.window.state, 'CLOSED')
        self.assertEqual(self.window.payloads, {})
        self.assertEqual(self.window.request_leases, {})

    @unittest.skipUnless(importlib.util.find_spec('mitmproxy'), 'installed engine interpreter required')
    def test_installed_streaming_eof_hooks_drive_phases_without_sockets_or_body_retention(self):
        from mitmproxy import connection, http
        from mitmproxy.options import Options
        from mitmproxy.proxy.context import Context
        from mitmproxy.proxy.layers.http import HttpStream
        from mitmproxy.proxy.layers.http._events import (RequestEndOfMessage,
            ResponseData, ResponseEndOfMessage)
        from mitmproxy.proxy.layers.http._hooks import HttpRequestHook, HttpResponseHook
        options = Options()
        options.add_option('store_streamed_bodies', bool, False, 'synthetic streaming test')
        context = Context(connection.Client(peername=('127.0.0.1', 1),
            sockname=('127.0.0.1', 2)), options)
        context.client.sni = 'example.invalid'
        stream = HttpStream(context, 1)
        flow = http.HTTPFlow(context.client, context.server)
        flow.request = http.Request.make('GET', 'https://example.invalid/catalog/list')
        flow.response = http.Response.make(200, b'')
        stream.flow = flow
        self.addon.requestheaders(flow)
        for command in stream.state_stream_request_body(RequestEndOfMessage(1)):
            if isinstance(command, HttpRequestHook):
                self.addon.request(command.flow)
        self.assertEqual(self.snapshot()['pending_by_phase']['RESPONSE_HEADERS'], 1)
        self.addon.responseheaders(flow)
        list(stream.state_stream_response_body(ResponseData(1, b'synthetic-stream-bytes')))
        self.assertEqual(self.snapshot()['http_responses_completed'], 0)
        for command in stream.state_stream_response_body(ResponseEndOfMessage(1)):
            if isinstance(command, HttpResponseHook):
                self.addon.response(command.flow)
        self.assertEqual(self.snapshot()['http_responses_completed'], 1)
        self.assertEqual(flow.response.raw_content, b'')
        self.assertEqual(len(stream.response_body_buf), 0)

    @unittest.skipUnless(Draft202012Validator, 'schema validator interpreter required')
    def test_closed_contract_rejects_private_fields_and_unbounded_counts(self):
        schema = json.loads((Path(__file__).resolve().parents[2] /
            'contracts/schemas/p26-forwarding-http-progress-v1.schema.json').read_text())
        validator = Draft202012Validator(schema)
        result = self.snapshot()
        validator.validate(result)
        self.assertFalse(validator.is_valid({**result, 'error': 'private'}))
        self.assertFalse(validator.is_valid({**result, 'http_responses_completed': 129}))
        pending = {**result['pending_by_phase'], 'RESPONSE_BODY': 65}
        self.assertFalse(validator.is_valid({**result, 'pending_by_phase': pending}))
        self.assertFalse(validator.is_valid({**result, 'last_failure_route_slot': 128}))
        response = {'route_slot': 0, 'status_code': 403, 'outcome': 'RESPONSE_COMPLETE'}
        self.assertTrue(validator.is_valid({**result, 'recent_responses': [response]}))
        for invalid in ({**response, 'error': 'private'}, {**response, 'status_code': 600},
                        {**response, 'route_slot': 128}, {**response, 'outcome': 'SUCCESS'}):
            self.assertFalse(validator.is_valid({**result, 'recent_responses': [invalid]}))
        self.assertFalse(validator.is_valid({**result, 'recent_responses': [response] * 17}))


if __name__ == '__main__':
    unittest.main()
