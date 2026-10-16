"""Forwarding failure evidence, using only synthetic objects and no sockets."""

import asyncio
import importlib.util
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None

from collection_adapter.p26_identification import IdentificationWindow
from collection_adapter import p26_identification_host as host


def selected_window(start=True):
    window = IdentificationWindow("Synthetic shop", duration_seconds=None)
    window.inspect_current_domain("example.invalid")
    if start:
        window.start_once()
    return window


class PrivateObject:
    def __str__(self):
        raise AssertionError("private text inspected")

    def __getitem__(self, _key):
        raise AssertionError("private context inspected")


class HookData:
    def __init__(self, sni="example.invalid"):
        self.client = SimpleNamespace(sni=sni)
        self.context = SimpleNamespace(client=self.client)

    @property
    def error(self):
        raise AssertionError("private error inspected")


class ForwardingHookTests(unittest.TestCase):
    def test_selected_connect_failure_closes_but_unselected_failure_is_only_counted(self):
        window = selected_window()
        addon = host.IdentificationAddon(window, detached_analysis=False)
        addon.server_connect(HookData())
        addon.server_connect_error(HookData("other.invalid"))
        self.assertEqual(window.state, "ACTIVE")
        addon.server_connect_error(HookData())
        self.assertEqual(window.code, "P26_FORWARDING_CONNECT_FAILED")
        self.assertEqual(addon.forwarding.counts["upstream_connect_failed"], 2)
        self.assertEqual(addon.forwarding.counts["selected_upstream_connect_failed"], 1)
        self.assertEqual(window.attempts, 1)

    def test_tls_and_http_failures_have_distinct_codes_without_reading_errors(self):
        for method, counter, code in (
            ("tls_failed_server", "selected_server_tls_failed", "P26_FORWARDING_SERVER_TLS_FAILED"),
            ("tls_failed_client", "selected_client_tls_failed", "P26_FORWARDING_CLIENT_TLS_FAILED"),
            ("error", "http_failed", "P26_FORWARDING_HTTP_FAILED"),
        ):
            with self.subTest(method=method):
                window = selected_window()
                addon = host.IdentificationAddon(window, detached_analysis=False)
                data = HookData()
                if method == "error":
                    data.id, data.client_conn = "synthetic-flow", data.client
                # tls_failed_client emits only the fixed count protocol.
                from unittest.mock import patch
                with patch.object(host, "_emit") as emit:
                    getattr(addon, method)(data)
                    if emit.called:
                        self.assertEqual(emit.call_args.args[0], {"event": "P26_TLS_CLIENT_FAILED", "count": 1})
                self.assertEqual(window.code, code)
                self.assertEqual(addon.forwarding.counts[counter], 1)

    def test_successful_hooks_do_not_close_and_counts_are_bounded(self):
        window = selected_window()
        addon = host.IdentificationAddon(window, detached_analysis=False)
        addon.server_connected(HookData())
        addon.tls_established_client(HookData())
        addon.tls_established_server(HookData())
        addon.tls_established_client(HookData("other.invalid"))
        for _ in range(200):
            addon.server_connect(HookData())
        self.assertEqual(window.state, "ACTIVE")
        self.assertEqual(addon.forwarding.counts["selected_client_tls_established"], 1)
        self.assertEqual(addon.forwarding.counts["upstream_connect_started"], 128)
        self.assertTrue(addon.forwarding.counts_at_least)

    @unittest.skipUnless(Draft202012Validator, "schema validator interpreter required")
    def test_diagnostic_schema_rejects_extra_text_and_unbounded_counts(self):
        window = selected_window()
        addon = host.IdentificationAddon(window, detached_analysis=False)
        gate = host.PIDStreamGate(window, 123, None)
        snapshot = addon.forwarding.snapshot(gate)
        schema = json.loads((Path(__file__).resolve().parents[2] /
                             "contracts/schemas/p26-forwarding-diagnostic-v1.schema.json").read_text())
        validator = Draft202012Validator(schema)
        validator.validate(snapshot)
        self.assertFalse(validator.is_valid({**snapshot, "exception": "private"}))
        self.assertFalse(validator.is_valid({**snapshot, "upstream_connected": 129}))

    def test_async_and_engine_failure_handlers_never_format_private_objects(self):
        for start in (False, True):
            window = selected_window(start)
            diagnostic = host.ForwardingDiagnostics(window)
            diagnostic.loop_exception(None, PrivateObject())
            self.assertEqual(window.code, "P26_FORWARDING_ASYNC_EXCEPTION")
            self.assertEqual(window.attempts, int(start))
        window = selected_window()
        diagnostic = host.ForwardingDiagnostics(window)
        handler = host._EngineFailureHandler(diagnostic)
        record = SimpleNamespace(levelno=logging.ERROR, msg=PrivateObject(), exc_info=PrivateObject())
        handler.emit(record)
        self.assertEqual(window.code, "P26_FORWARDING_ENGINE_ERROR")
        self.assertEqual(diagnostic.counts["engine_errors"], 1)


class DetachedForwardingFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_failed_connection_does_not_reject_other_forwarded_streams(self):
        from unittest.mock import patch

        for method, counter, code in (
            ("server_connect_error", "selected_upstream_connect_failed", "P26_FORWARDING_CONNECT_FAILED"),
            ("tls_failed_server", "selected_server_tls_failed", "P26_FORWARDING_SERVER_TLS_FAILED"),
            ("tls_failed_client", "selected_client_tls_failed", "P26_FORWARDING_CLIENT_TLS_FAILED"),
            ("error", "http_failed", "P26_FORWARDING_HTTP_FAILED"),
        ):
            with self.subTest(method=method):
                window = selected_window()
                addon = host.IdentificationAddon(window)
                self.addCleanup(addon.finish_analysis)
                collector = SimpleNamespace(feed=lambda _chunk: self.fail("incomplete copy parsed"))
                forward = addon._stream(collector)
                data = HookData()
                data.id, data.client_conn = "failed-synthetic-flow", data.client
                with patch.object(host, "_emit"):
                    getattr(addon, method)(data)

                self.assertEqual(addon.transport_window.state, "ACTIVE")
                self.assertEqual(addon.forwarding.last_failure, code)
                self.assertEqual(addon.forwarding.counts[counter], 1)
                self.assertTrue(addon.analysis.diagnostic()["accepting_copies"])
                self.assertEqual(addon.analysis.diagnostic()["recovery"], "CONTINUING")
                self.assertEqual(addon.analysis.diagnostic()["failure"], "ANALYSIS_REJECTED")
                self.assertTrue(addon.analysis.diagnostic()["coverage_incomplete"])
                for chunk in (b"synthetic-response-unchanged", b""):
                    self.assertIs(forward(chunk), chunk)
                later = []
                follow = addon._stream(SimpleNamespace(feed=lambda chunk: later.append(chunk)))
                self.assertIs(follow(b'{"synthetic":1}'), b'{"synthetic":1}')
                self.assertEqual(follow(b""), b"")
                with addon.analysis.condition:
                    self.assertTrue(addon.analysis.condition.wait_for(
                        lambda: b'{"synthetic":1}' in later, timeout=3))
                self.assertNotIn(b"synthetic-response-unchanged", later)
                self.assertEqual(addon.analysis.diagnostic()["recovery"], "CONTINUING")

                dispatched = []

                class Stream:
                    closed = False

                    def get_extra_info(self, _key, _default):
                        return 123

                    def close(self):
                        self.closed = True

                async def dispatch(stream):
                    dispatched.append(stream)

                gate = host.PIDStreamGate(addon.transport_window, 123, dispatch,
                                          diagnostic=addon.forwarding)
                healthy = Stream()
                await gate(healthy)
                self.assertEqual(dispatched, [healthy])
                self.assertFalse(healthy.closed)

                addon.transport_window.close()
                after_stop = Stream()
                await gate(after_stop)
                self.assertTrue(after_stop.closed)
                self.assertEqual(dispatched, [healthy])

    async def test_unselected_connection_failure_does_not_stop_public_copy_analysis(self):
        addon = host.IdentificationAddon(selected_window())
        self.addCleanup(addon.finish_analysis)
        addon.server_connect_error(HookData("other.invalid"))
        self.assertEqual(addon.transport_window.state, "ACTIVE")
        self.assertTrue(addon.analysis.diagnostic()["accepting_copies"])
        self.assertFalse(addon.analysis.diagnostic()["coverage_incomplete"])
        self.assertEqual(addon.forwarding.counts["upstream_connect_failed"], 1)
        self.assertEqual(addon.forwarding.counts["selected_upstream_connect_failed"], 0)

    async def test_failed_partial_response_still_rejects_incomplete_analysis(self):
        addon = host.IdentificationAddon(selected_window())
        self.addCleanup(addon.finish_analysis)
        data = HookData()
        data.id, data.client_conn = 'synthetic-partial-response', data.client
        addon.http_progress.begin(data.id, 0)
        addon.http_progress.request_complete(data.id)
        addon.http_progress.response_headers(data.id)
        addon.error(data)
        self.assertEqual(addon.http_progress_snapshot()['last_failure_phase'], 'RESPONSE_BODY')
        diagnostic = addon.analysis.diagnostic()
        self.assertTrue(diagnostic['accepting_copies'])
        self.assertEqual(diagnostic['recovery'], 'CONTINUING')
        self.assertEqual(diagnostic['failure'], 'ANALYSIS_REJECTED')
        self.assertTrue(diagnostic['coverage_incomplete'])
        self.assertGreaterEqual(diagnostic['dropped_copies'], 1)
        self.assertEqual(addon.transport_window.state, 'ACTIVE')


class ForwardingAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_exception_clears_leases_and_closes_stream_once(self):
        window = selected_window()
        window.payloads[0] = {"synthetic": "private-must-be-cleared"}
        window.request_leases["synthetic"] = {"expires_at": window.last_clock + 60}
        diagnostic = host.ForwardingDiagnostics(window)
        class Stream:
            closes = 0
            def get_extra_info(self, _key, _default):
                return 123
            def close(self):
                self.closes += 1
        async def failing(_stream):
            raise RuntimeError("synthetic-private-error-must-not-escape")
        stream = Stream()
        gate = host.PIDStreamGate(window, 123, failing, diagnostic=diagnostic)
        await gate(stream)
        self.assertEqual(window.code, "P26_FORWARDING_EXCEPTION")
        self.assertEqual(window.attempts, 1)
        self.assertEqual(window.payloads, {})
        self.assertEqual(window.request_leases, {})
        self.assertEqual(stream.closes, 1)
        self.assertEqual(gate.concurrent, 0)
        self.assertEqual(gate.peak_concurrent, 1)
        self.assertEqual(diagnostic.counts["dispatch_exceptions"], 1)
        self.assertNotIn("synthetic-private", json.dumps(diagnostic.snapshot(gate)))

    async def test_cancelled_dispatch_releases_stream_and_preserves_prior_stop(self):
        for already_closed in (False, True):
            window = selected_window()
            class Stream:
                closed = False
                def get_extra_info(self, _key, _default):
                    return 123
                def close(self):
                    self.closed = True
            async def cancelled(_stream):
                if already_closed:
                    window.close("P26_IDENTIFICATION_CLOSED")
                raise asyncio.CancelledError()
            gate = host.PIDStreamGate(window, 123, cancelled)
            stream = Stream()
            with self.assertRaises(asyncio.CancelledError):
                await gate(stream)
            self.assertTrue(stream.closed)
            self.assertEqual(gate.concurrent, 0)
            self.assertEqual(window.code, "P26_IDENTIFICATION_CLOSED" if already_closed else "P26_CANCELLED")

    @unittest.skipUnless(importlib.util.find_spec("mitmproxy"), "installed engine interpreter required")
    async def test_installed_engine_swallowed_layer_exception_is_detected_without_log_text(self):
        from mitmproxy import connection
        from mitmproxy.options import Options
        from mitmproxy.proxy import events, server
        from mitmproxy.proxy.context import Context
        options = Options()
        options.add_option("tcp_timeout", float, 600.0, "synthetic test")
        context = Context(connection.Client(peername=("127.0.0.1", 1), sockname=("127.0.0.1", 2)), options)
        class Handler(server.ConnectionHandler):
            async def handle_hook(self, _hook):
                pass
        class BrokenLayer:
            def handle_event(self, _event):
                raise RuntimeError("synthetic-private-layer-error")
        window = selected_window()
        diagnostic = host.ForwardingDiagnostics(window)
        handler = Handler(context)
        handler.layer = BrokenLayer()
        previous_disabled = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            # Direct reproduction: the engine swallows the exception; without
            # the fixed severity handler the P26 window stays ACTIVE.
            await handler.server_event(events.Start())
            self.assertEqual(window.state, "ACTIVE")
            restore = host._capture_engine_failures(diagnostic)
            try:
                await handler.server_event(events.Start())
            finally:
                restore()
            self.assertEqual(window.code, "P26_FORWARDING_ENGINE_ERROR")
            self.assertEqual(diagnostic.counts["engine_errors"], 1)
        finally:
            logging.disable(previous_disabled)

    @unittest.skipUnless(importlib.util.find_spec("mitmproxy"), "installed engine interpreter required")
    async def test_installed_opaque_tcp_layer_forwards_without_creating_a_message_flow(self):
        from mitmproxy import connection
        from mitmproxy.options import Options
        from mitmproxy.proxy import commands, events
        from mitmproxy.proxy.context import Context
        from mitmproxy.proxy.layers import TCPLayer
        context = Context(connection.Client(peername=("127.0.0.1", 1), sockname=("127.0.0.1", 2)), Options())
        context.server.timestamp_start = 1
        context.server.state = connection.ConnectionState.OPEN
        layer = TCPLayer(context, ignore=True)
        self.assertEqual(list(layer.handle_event(events.Start())), [])
        output = list(layer.handle_event(events.DataReceived(context.client, b"synthetic-opaque-stream")))
        self.assertIsNone(layer.flow)
        self.assertEqual(len(output), 1)
        self.assertIsInstance(output[0], commands.SendData)
        self.assertEqual(output[0].data, b"synthetic-opaque-stream")


if __name__ == "__main__":
    unittest.main()
