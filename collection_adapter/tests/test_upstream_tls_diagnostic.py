import json
import importlib.util
from enum import Flag
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from collection_adapter import upstream_tls_diagnostic as diagnostic
from collection_adapter import p26_identification_host as host
from collection_adapter.tests.test_p26_identification import active_window


class GuardedConnection:
    def __init__(self, name):
        self.sni = name
        self._ssl = object()

    @property
    def error(self):
        raise AssertionError('error text must stay unread')

    @property
    def certificate_list(self):
        raise AssertionError('certificates must stay unread')

    @property
    def address(self):
        raise AssertionError('addresses must stay unread')


def event(upstream='example.invalid', client='example.invalid'):
    return SimpleNamespace(conn=GuardedConnection(upstream),
        context=SimpleNamespace(client=GuardedConnection(client)),
        ssl_conn=GuardedConnection(None))


class UpstreamTLSMetadataTests(unittest.TestCase):
    def test_transport_states_are_fixed_snapshots_and_missing_is_unknown(self):
        class State(Flag):
            CLOSED = 0
            CAN_READ = 1
            CAN_WRITE = 2
            OPEN = 3
        module = SimpleNamespace(ConnectionState=State)
        with patch.dict(sys.modules, {'mitmproxy.connection': module}):
            for state in (State.CLOSED, State.CAN_READ, State.CAN_WRITE, State.OPEN):
                data = event()
                data.conn.state = state
                data.context.client.state = State.OPEN
                result = diagnostic.upstream_tls_failure_metadata(data)
                self.assertEqual(result['upstream_transport_state'], state.name)
                self.assertEqual(result['client_transport_state'], 'OPEN')
            for invalid in (None, 3, 'OPEN', object()):
                data.conn.state = invalid
                self.assertEqual(diagnostic.upstream_tls_failure_metadata(data)
                                 ['upstream_transport_state'], 'UNKNOWN')
        result = diagnostic.upstream_tls_failure_metadata(event())
        self.assertEqual(result['upstream_transport_state'], 'UNKNOWN')
        self.assertEqual(result['client_transport_state'], 'UNKNOWN')

    def verify(self, value, constants=None, getter=None):
        library = SimpleNamespace(SSL_get_verify_result=getter or (lambda pointer: value),
                                  **(constants or {}))
        module = SimpleNamespace(SSL=SimpleNamespace(_lib=library))
        with patch.dict(sys.modules, {'OpenSSL': module}):
            return diagnostic._verification_status(GuardedConnection(None))

    def test_known_structured_verification_results_map_to_fixed_codes(self):
        for index, (reason, names) in enumerate(diagnostic._VERIFY_REASONS.items(), 1):
            for name in names:
                with self.subTest(name=name):
                    self.assertEqual(self.verify(index, {name: index}), reason)

    def test_zero_result_does_not_claim_successful_handshake(self):
        self.assertEqual(self.verify(0), 'TLS_VERIFY_NO_ERROR_REPORTED')
        self.assertEqual(self.verify(98765), 'TLS_VERIFY_OTHER')

    def test_unavailable_or_invalid_verify_api_is_unknown(self):
        self.assertEqual(diagnostic._verification_status(None), 'TLS_VERIFY_UNKNOWN')
        for value in (None, True, -1, 'private exception sentinel'):
            self.assertEqual(self.verify(value), 'TLS_VERIFY_UNKNOWN')
        def unavailable(pointer):
            raise RuntimeError('private exception sentinel')
        self.assertEqual(self.verify(None, getter=unavailable), 'TLS_VERIFY_UNKNOWN')

    def test_name_comparison_reduces_hostnames_and_ips_without_values(self):
        for upstream, client, kind, matches in (
            ('Example.invalid.', 'example.invalid', 'HOSTNAME', True),
            ('other.invalid', 'example.invalid', 'HOSTNAME', False),
            ('192.0.2.1', 'example.invalid', 'IP', False),
            ('2001:db8::1', '2001:0db8:0:0:0:0:0:1', 'IP', True),
        ):
            with self.subTest(kind=kind, matches=matches):
                result = diagnostic.upstream_tls_failure_metadata(event(upstream, client))
                self.assertEqual(result['upstream_name_kind'], kind)
                self.assertIs(result['upstream_name_matches_client'], matches)
                self.assertNotIn(upstream, json.dumps(result))
                self.assertNotIn(client, json.dumps(result))

    def test_absent_invalid_and_oversized_names_have_no_comparison(self):
        for value, kind in ((None, 'ABSENT'), ('', 'ABSENT'),
                            ('x'*254, 'UNKNOWN'), ('private/value', 'UNKNOWN'),
                            (b'example.invalid', 'UNKNOWN')):
            result = diagnostic.upstream_tls_failure_metadata(event(value))
            self.assertEqual(result['upstream_name_kind'], kind)
            self.assertIsNone(result['upstream_name_matches_client'])

    def test_only_fixed_metadata_survives_and_guarded_values_are_unread(self):
        with patch.object(diagnostic, '_verification_status', return_value='TLS_VERIFY_EXPIRED'):
            result = diagnostic.upstream_tls_failure_metadata(event('private-name.invalid'))
        self.assertEqual(set(result), {'schema_version', 'verification_status',
            'upstream_name_kind', 'client_name_kind', 'upstream_name_matches_client',
            'upstream_transport_state', 'client_transport_state'})
        self.assertEqual(result['verification_status'], 'TLS_VERIFY_EXPIRED')
        self.assertNotIn('private-name', json.dumps(result))
        result = diagnostic.upstream_tls_failure_metadata(object())
        self.assertEqual(result['verification_status'], 'TLS_VERIFY_UNKNOWN')

    def test_selected_hook_records_metadata_before_closing_once(self):
        window, _clock, _route = active_window()
        addon = host.IdentificationAddon(window, detached_analysis=False)
        original_close = window.close
        def close(code):
            self.assertEqual(addon.forwarding.upstream_tls_failure['verification_status'],
                             'TLS_VERIFY_NAME_MISMATCH')
            original_close(code)
        with patch.object(window, 'close', side_effect=close) as closed, \
                patch.object(diagnostic, '_verification_status', return_value='TLS_VERIFY_NAME_MISMATCH'):
            addon.tls_failed_server(event('192.0.2.1'))
            addon.tls_failed_server(event('192.0.2.1'))
        closed.assert_called_once_with('P26_FORWARDING_SERVER_TLS_FAILED')
        self.assertEqual(window.state, 'CLOSED')
        self.assertEqual(window.diagnostic()['live_capture_latch'], 'CLOSED')
        self.assertEqual(addon.forwarding.counts['selected_server_tls_failed'], 1)

    def test_non_target_hook_does_not_inspect_diagnostics_or_close(self):
        window, _clock, _route = active_window()
        addon = host.IdentificationAddon(window, detached_analysis=False)
        with patch.object(diagnostic, 'upstream_tls_failure_metadata') as inspect:
            addon.tls_failed_server(event(client='other.invalid'))
        inspect.assert_not_called()
        self.assertTrue(window.active())
        self.assertIsNone(addon.forwarding.upstream_tls_failure)

    def test_closed_schemas_accept_old_receipts_and_refuse_error_text(self):
        from jsonschema import Draft202012Validator, ValidationError
        schemas = Path(__file__).resolve().parents[2]/'contracts/schemas'
        schema = json.loads((schemas/'p26-forwarding-diagnostic-v1.schema.json').read_text())
        validator = Draft202012Validator(schema)
        window, _clock, _route = active_window()
        forwarding = host.ForwardingDiagnostics(window)
        gate = SimpleNamespace(concurrent=0, peak_concurrent=1)
        legacy = forwarding.snapshot(gate); legacy.pop('upstream_tls_failure')
        validator.validate(legacy)
        validator.validate(forwarding.snapshot(gate))
        forwarding.upstream_tls_failure = diagnostic.upstream_tls_failure_metadata(event())
        validator.validate(forwarding.snapshot(gate))
        prior = dict(forwarding.upstream_tls_failure)
        prior.pop('upstream_transport_state')
        prior.pop('client_transport_state')
        validator.validate({**legacy, 'upstream_tls_failure': prior})
        for bad in ({'error': 'private exception sentinel'},
                    {'verification_status': 'private exception sentinel'},
                    {'upstream_name_kind': 'private-name.invalid'},
                    {'upstream_transport_state': 'private exception sentinel'},
                    {'client_transport_state': 3}):
            with self.assertRaises(ValidationError):
                validator.validate({**legacy, 'upstream_tls_failure':
                    {**forwarding.upstream_tls_failure, **bad}})
        for name in ('p26-identification-diagnostic-v1.schema.json',
                     'p26-result-diagnostic-v1.schema.json',
                     'p29-store-pages-diagnostic-v1.schema.json'):
            document = json.loads((schemas/name).read_text())
            def find(node):
                if isinstance(node, dict):
                    if node.get('properties', {}).get('schema_version', {}).get('const') == 'p26-forwarding-diagnostic/v1':
                        return node
                    for value in node.values():
                        result = find(value)
                        if result: return result
                elif isinstance(node, list):
                    for value in node:
                        result = find(value)
                        if result: return result
            embedded = find(document)
            self.assertIsNotNone(embedded)
            self.assertEqual(embedded['properties']['upstream_tls_failure'],
                             schema['properties']['upstream_tls_failure'])
            Draft202012Validator(embedded).validate(forwarding.snapshot(gate))


@unittest.skipUnless(importlib.util.find_spec('mitmproxy'),
                     'installed engine interpreter required')
class InstalledTLSFailureStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_eof_and_protocol_failure_have_distinct_hook_transport_snapshots(self):
        # Real installed tunnel/TLS/EOF code, synthetic in-memory bytes only.
        # No sockets, certificates, captured traffic, or free-text diagnostics.
        from OpenSSL import SSL
        from mitmproxy import connection
        from mitmproxy.options import Options
        from mitmproxy.proxy import events, server, tunnel
        from mitmproxy.proxy.context import Context
        from mitmproxy.proxy.layers.tls import ServerTLSLayer, TlsFailedServerHook

        def setup():
            options = Options()
            options.add_option('tcp_timeout', float, 600.0, 'synthetic test')
            context = Context(connection.Client(peername=('127.0.0.1', 1),
                              sockname=('127.0.0.1', 2)), options)
            context.client.sni = context.server.sni = 'example.invalid'
            context.client.state = context.server.state = connection.ConnectionState.OPEN
            layer = ServerTLSLayer(context)
            layer.tunnel_state = tunnel.TunnelState.ESTABLISHING
            layer.tls = SSL.Connection(SSL.Context(SSL.TLS_CLIENT_METHOD))
            layer.tls.set_connect_state()
            return context, layer

        snapshots = []
        def capture(layer, event):
            for command in layer.handle_event(event):
                if isinstance(command, TlsFailedServerHook):
                    snapshots.append(diagnostic.upstream_tls_failure_metadata(command.data))
                    return
            self.fail('expected installed TLS failure hook')

        context, layer = setup()
        capture(layer, events.DataReceived(context.server, b'HTTP/1.1 400 Synthetic\r\n\r\n'))

        context, layer = setup()
        class EOFReader:
            async def read(self, _limit):
                return b''
        class Writer:
            closed = False
            def close(self):
                self.closed = True
        class Handler(server.ConnectionHandler):
            async def handle_hook(self, _hook):
                raise AssertionError('hooks must be inspected synchronously in this test')

            async def server_event(self, event):
                capture(layer, event)
                event.connection.state = connection.ConnectionState.CLOSED
        handler = Handler(context)
        writer = Writer()
        handler.transports[context.server] = SimpleNamespace(reader=EOFReader(), writer=writer)
        await handler.handle_connection(context.server)
        self.assertTrue(writer.closed)
        self.assertEqual(len(snapshots), 2)
        self.assertEqual([x['verification_status'] for x in snapshots],
                         ['TLS_VERIFY_NO_ERROR_REPORTED'] * 2)
        self.assertEqual([x['upstream_transport_state'] for x in snapshots],
                         ['OPEN', 'CAN_WRITE'])
        self.assertEqual([x['client_transport_state'] for x in snapshots], ['OPEN'] * 2)


if __name__ == '__main__':
    unittest.main()
