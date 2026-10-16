from __future__ import annotations

import json
from pathlib import Path
import threading
import time
import unittest

from collection_adapter import CollectionEvent, CollectionEventBatch, CollectionTarget
from collection_adapter.live_adapter import LiveAdapterError, LiveP0Observation
from collection_adapter.live_execution import LiveP0ExecutionAuthority
from collection_adapter.mitmproxy_bridge import (
    MitmproxyBridgeError,
    MitmproxyCallbackBridge,
    MitmproxySourceEntry,
    MitmproxySourcePolicy,
    P21OutputBoundary,
)
from collection_adapter.tests.test_live_execution import _EXPIRES_AT, _ISSUED_AT, _request


class _ForbiddenRequest:
    method = "GET"
    host = "loader.local"
    path = "/current-entry"

    @property
    def content(self):
        raise AssertionError("request body must not be read")

    @property
    def headers(self):
        raise AssertionError("request headers must not be read")

    @property
    def cookies(self):
        raise AssertionError("request cookies must not be read")

    @property
    def session(self):
        raise AssertionError("request session must not be read")


class _Response:
    def __init__(
        self,
        *,
        endpoint: str = "FOOD",
        byte_count: int = 8,
        sensitive: bool = False,
        target: str = "target:live_demo_01",
        observation_scope: str = "OBS_P20_01",
        payload_family: str = "synthetic_p1_productlist",
        payload_version: str = "v1",
    ) -> None:
        self.endpoint = endpoint
        self.byte_count = byte_count
        self.sensitive = sensitive
        self.target = target
        self.observation_scope = observation_scope
        self.payload_family = payload_family
        self.payload_version = payload_version


class _Flow:
    def __init__(self, response: _Response) -> None:
        self.request = _ForbiddenRequest()
        self.response = response


def _batch(request, response: _Response) -> CollectionEventBatch:
    if response.endpoint == "FOOD":
        payload = {"data": {"poi_info": {"poi_id_str": "m1", "name": "n"}}}
    elif response.endpoint == "PRODUCTLIST":
        payload = {
            "data": {
                "food_spu_tags": [
                    {
                        "tag": "c",
                        "current_page": 1,
                        "has_next_page": False,
                        "dynamic_spus": [
                            {"id": 1, "name": "p", "min_price": 1, "skus": [{"id": 1, "spec": "s", "price": 1, "status": 1}]}
                        ],
                    }
                ]
            }
        }
    else:
        payload = {"data": {}}
    return CollectionEventBatch(
        run_ref=request.run_ref,
        read_scope="READ_P20_01",
        observation_scope=response.observation_scope,
        observed_at=_ISSUED_AT,
        events=(
            CollectionEvent(
                read_scope="READ_P20_01",
                observation_scope=response.observation_scope,
                event_index=1 if response.endpoint == "FOOD" else 2,
                endpoint_id=response.endpoint,
                payload_family=response.payload_family,
                payload_version=response.payload_version,
                payload=payload,
            ),
        ),
    )


def _policy(*, timeout: float = 0.2, max_events: int = 2) -> MitmproxySourcePolicy:
    return MitmproxySourcePolicy(
        endpoint_matches=lambda method, host, path: (method, host, path) == ("GET", "loader.local", "/current-entry"),
        response_size=lambda response: response.byte_count,
        contains_sensitive=lambda response: response.sensitive,
        target_matches=lambda response, target: response.target == target.target_ref,
        project=lambda response, request: _batch(request, response),
        max_response_bytes=16,
        max_events=max_events,
        observation_timeout_seconds=timeout,
    )


def _read_in_thread(bridge: MitmproxyCallbackBridge, request, lease):
    result = {}

    def invoke() -> None:
        try:
            result["observation"] = bridge.read_once(request, lease)
        except Exception as error:  # Test the closed error boundary below.
            result["error"] = error

    thread = threading.Thread(target=invoke)
    thread.start()
    for _ in range(100):
        if bridge.snapshot()["state"] == "WAITING":
            break
        time.sleep(0.001)
    return thread, result


class MitmproxyCallbackBridgeTests(unittest.TestCase):
    def test_two_future_endpoint_callbacks_handoff_one_complete_observation_without_request_surface_access(self) -> None:
        request = _request()
        bridge = MitmproxyCallbackBridge(_policy(), request.target)
        authority = LiveP0ExecutionAuthority(request)
        with authority.acquire(request, now=_ISSUED_AT) as lease:
            thread, result = _read_in_thread(bridge, request, lease)
            self.assertEqual(bridge.response(_Flow(_Response(endpoint="FOOD"))), "MITMPROXY_BRIDGE_COLLECTED")
            self.assertEqual(bridge.snapshot(), {"state": "WAITING", "pending_callback": False, "callbacks_seen": 1})
            self.assertEqual(bridge.response(_Flow(_Response(endpoint="PRODUCTLIST"))), "MITMPROXY_BRIDGE_ACCEPTED")
            thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(result.get("observation"), LiveP0Observation)
        self.assertTrue(result["observation"].destroyed is False)
        self.assertEqual(
            [event.endpoint_id for event in result["observation"]._batch.events],
            ["FOOD", "PRODUCTLIST"],
        )
        result["observation"].destroy()
        self.assertEqual(bridge.snapshot(), {"state": "CLOSED", "pending_callback": False, "callbacks_seen": 2})
        self.assertEqual(authority.snapshot(), {
            "live_capture_latch": "CLOSED",
            "execution_latch": "CLOSED",
            "source_attempts_consumed": 1,
        })

    def test_rejects_unmatched_budget_sensitive_target_drift_and_duplicate_with_closed_codes(self) -> None:
        request = _request()
        cases = (
            (lambda: _Flow(_Response(byte_count=17)), "MITMPROXY_BRIDGE_RESPONSE_BUDGET", lambda flow: None),
            (lambda: _Flow(_Response(sensitive=True)), "MITMPROXY_BRIDGE_SENSITIVE_REJECTED", lambda flow: None),
            (lambda: _Flow(_Response(target="target:live_demo_02")), "MITMPROXY_BRIDGE_TARGET_DRIFT", lambda flow: None),
        )
        for make_flow, code, prepare in cases:
            with self.subTest(code=code):
                bridge = MitmproxyCallbackBridge(_policy(), request.target)
                authority = LiveP0ExecutionAuthority(request)
                with authority.acquire(request, now=_ISSUED_AT) as lease:
                    thread, result = _read_in_thread(bridge, request, lease)
                    flow = make_flow()
                    prepare(flow)
                    self.assertEqual(bridge.response(flow), code)
                    thread.join(timeout=1)
                self.assertFalse(thread.is_alive())
                self.assertEqual(type(result.get("error")), MitmproxyBridgeError)
                self.assertEqual(result["error"].code, code)
                self.assertEqual(bridge.snapshot()["pending_callback"], False)

        bridge = MitmproxyCallbackBridge(_policy(), request.target)
        authority = LiveP0ExecutionAuthority(request)
        with authority.acquire(request, now=_ISSUED_AT) as lease:
            thread, result = _read_in_thread(bridge, request, lease)
            self.assertEqual(bridge.response(_Flow(_Response(endpoint="FOOD"))), "MITMPROXY_BRIDGE_COLLECTED")
            self.assertEqual(bridge.response(_Flow(_Response(endpoint="FOOD"))), "MITMPROXY_BRIDGE_DUPLICATE")
            thread.join(timeout=1)
        self.assertEqual(type(result.get("error")), MitmproxyBridgeError)
        self.assertEqual(result["error"].code, "MITMPROXY_BRIDGE_DUPLICATE")

    def test_rejects_multi_event_callback_and_cross_callback_observation_drift(self) -> None:
        request = _request()

        def multi_event(_response, active_request):
            food = _batch(active_request, _Response(endpoint="FOOD"))
            product = _batch(active_request, _Response(endpoint="PRODUCTLIST"))
            return CollectionEventBatch(
                run_ref=active_request.run_ref,
                read_scope=food.read_scope,
                observation_scope=food.observation_scope,
                observed_at=food.observed_at,
                events=food.events + product.events,
            )

        multi_event_policy = MitmproxySourcePolicy(
            endpoint_matches=_policy().endpoint_matches,
            response_size=_policy().response_size,
            contains_sensitive=_policy().contains_sensitive,
            target_matches=_policy().target_matches,
            project=multi_event,
            max_response_bytes=16,
            max_events=2,
            observation_timeout_seconds=0.2,
        )
        bridge = MitmproxyCallbackBridge(multi_event_policy, request.target)
        authority = LiveP0ExecutionAuthority(request)
        with authority.acquire(request, now=_ISSUED_AT) as lease:
            thread, result = _read_in_thread(bridge, request, lease)
            self.assertEqual(bridge.response(_Flow(_Response(endpoint="FOOD"))), "MITMPROXY_BRIDGE_PROJECTION_REJECTED")
            thread.join(timeout=1)
        self.assertEqual(result["error"].code, "MITMPROXY_BRIDGE_PROJECTION_REJECTED")

        bridge = MitmproxyCallbackBridge(_policy(), request.target)
        authority = LiveP0ExecutionAuthority(request)
        with authority.acquire(request, now=_ISSUED_AT) as lease:
            thread, result = _read_in_thread(bridge, request, lease)
            self.assertEqual(bridge.response(_Flow(_Response(endpoint="FOOD"))), "MITMPROXY_BRIDGE_COLLECTED")
            self.assertEqual(
                bridge.response(_Flow(_Response(endpoint="PRODUCTLIST", observation_scope="OBS_P20_OTHER"))),
                "MITMPROXY_BRIDGE_PROJECTION_REJECTED",
            )
            thread.join(timeout=1)
        self.assertEqual(result["error"].code, "MITMPROXY_BRIDGE_PROJECTION_REJECTED")

    def test_partial_observation_timeout_releases_staged_event_and_non_two_budget_is_rejected(self) -> None:
        request = _request()
        with self.assertRaisesRegex(MitmproxyBridgeError, "^MITMPROXY_BRIDGE_FACTORY_INVALID$"):
            _policy(max_events=1)

        bridge = MitmproxyCallbackBridge(_policy(timeout=0.02), request.target)
        authority = LiveP0ExecutionAuthority(request)
        with authority.acquire(request, now=_ISSUED_AT) as lease:
            thread, result = _read_in_thread(bridge, request, lease)
            self.assertEqual(bridge.response(_Flow(_Response(endpoint="FOOD"))), "MITMPROXY_BRIDGE_COLLECTED")
            thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["error"].code, "MITMPROXY_BRIDGE_TIMEOUT")
        self.assertEqual(bridge.snapshot(), {"state": "CLOSED", "pending_callback": False, "callbacks_seen": 1})
        self.assertEqual(bridge._events_by_endpoint, {})

    def test_timeout_and_callback_before_reader_close_without_a_source_attempt_or_retained_flow(self) -> None:
        request = _request()
        bridge = MitmproxyCallbackBridge(_policy(timeout=0), request.target)
        self.assertEqual(bridge.response(_Flow(_Response())), "MITMPROXY_BRIDGE_NOT_WAITING")
        self.assertEqual(bridge.snapshot(), {"state": "IDLE", "pending_callback": False, "callbacks_seen": 0})
        authority = LiveP0ExecutionAuthority(request)
        with authority.acquire(request, now=_ISSUED_AT) as lease:
            with self.assertRaisesRegex(MitmproxyBridgeError, "^MITMPROXY_BRIDGE_TIMEOUT$"):
                bridge.read_once(request, lease)
        self.assertEqual(bridge.snapshot(), {"state": "CLOSED", "pending_callback": False, "callbacks_seen": 0})
        self.assertEqual(authority.snapshot()["live_capture_latch"], "CLOSED")

    def test_factory_keeps_p20_zero_attempt_closed_until_p21_creates_a_fresh_request(self) -> None:
        entry = MitmproxySourceEntry(
            policy=_policy(),
            runtime_target=CollectionTarget("target:runtime_p20_01"),
            target_binding_ref="target-binding:runtime_p20_01",
            source_entry_ref="source-entry:runtime_p20_01",
            output_boundary=P21OutputBoundary("output-root:runtime_p20_01"),
        )
        self.assertEqual(entry.binding_receipt(), {
            "schema_version": "collection-mitmproxy-source-entry-binding/v1",
            "historical_target_ref": "TGT-HZ-XCJ-GFTJ-001",
            "historical_target_status": "NOT_OBSERVED",
            "runtime_target_ref": "target:runtime_p20_01",
            "target_binding_ref": "target-binding:runtime_p20_01",
            "source_entry_ref": "source-entry:runtime_p20_01",
            "source_entry_kind": "MITMPROXY_PASSIVE_CALLBACK",
            "route_id": "OWNED_STRUCTURED_EVENT",
            "source_kind": "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE",
            "source_purpose": "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE_P0_VALIDATION",
            "network_capability": "SINGLE_NETWORK_SOURCE_READ",
            "forbidden_capabilities": ["BROWSER_UI", "WECHAT_UI", "SYSTEM_PROXY", "CA_INSTALL_OR_USE", "KEYCHAIN", "CREDENTIAL_ACCESS", "SESSION_ACCESS", "TRANSACTION"],
            "output_root_ref": "output-root:runtime_p20_01",
            "output_root_mode": "0700",
            "p21_factory": "IMMEDIATE_FRESH_REQUEST_ONLY",
            "live_capture_latch": "CLOSED",
            "execution_latch": "CLOSED",
            "source_attempts_consumed": 0,
            "automatic_retry": False,
            "source_material_persisted": False,
            "business_publication_allowed": False,
        })
        attempt = entry.create_p21_attempt(
            source_ref="source:runtime_p20_01",
            provider_contract_ref="provider-contract:runtime_p20_01",
            authorization_ref="authorization:runtime_p20_01",
            run_ref="run:runtime_p20_01",
            attempt_ref="attempt:runtime_p20_01",
            input_lock_ref="input-lock:runtime_p20_01",
            capability_ref="capability:runtime_p20_01",
            issued_at=_ISSUED_AT,
            expires_at=_EXPIRES_AT,
        )
        self.assertEqual(attempt.request.target.target_ref, "target:runtime_p20_01")
        self.assertEqual(attempt.authority.snapshot()["source_attempts_consumed"], 0)
        self.assertEqual(attempt.authority.snapshot()["live_capture_latch"], "CLOSED")

    def test_binding_schema_is_closed_and_bridge_has_no_network_or_system_io_imports(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        schema = json.loads(
            (repository / "contracts/schemas/mitmproxy-source-entry-binding-v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["source_attempts_consumed"]["const"], 0)
        self.assertEqual(schema["properties"]["live_capture_latch"]["const"], "CLOSED")
        source = (repository / "collection_adapter/mitmproxy_bridge.py").read_text(encoding="utf-8")
        for forbidden in (
            "import mitmproxy",
            "import socket",
            "import urllib",
            "import requests",
            "import subprocess",
            "import os",
            "open(",
        ):
            self.assertNotIn(forbidden, source)
