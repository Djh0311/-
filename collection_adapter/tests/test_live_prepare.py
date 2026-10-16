from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from collection_adapter import CollectionEvent, CollectionEventBatch, CollectionTarget
from collection_adapter.live_execution import MAX_LIVE_WINDOW_SECONDS, LiveP0Request, LiveRequestError
from collection_adapter.live_prepare import SCHEMA_VERSION, UNKNOWN_CONDITIONS, main, prepare_live_entry
from collection_adapter.live_prepare import LivePreparationSpec
from collection_adapter.mitmproxy_bridge import MitmproxyBridgeError, MitmproxySourcePolicy
from collection_core import P0Context
from parser_candidate import Binding, FoodParserConfig, ParserConfig, ParserRegistry


_ISSUED_AT = "2026-08-11T12:00:00Z"
_EXPIRES_AT = "2026-08-11T12:01:00Z"
_SECRET = "synthetic-secret-marker"


class _Flow:
    def __init__(self, response: object, *, path: str = "/current-entry") -> None:
        self._response = response
        self._path = path
        self.request_reads = 0

    @property
    def request(self):
        self.request_reads += 1
        route = _Route()
        route.path = self._path
        return route

    @property
    def response(self):
        return self._response


class _ExplosiveFlow:
    @property
    def request(self):
        raise AssertionError("callback must not be inspected")

    @property
    def response(self):
        raise AssertionError("callback must not be inspected")


class _Route:
    method = "GET"
    host = "loader.local"
    path = "/current-entry"


class _Response:
    def __init__(self, endpoint: str = "FOOD", *, sensitive: bool = False, target: str = "target:p25_demo_01") -> None:
        self.endpoint = endpoint
        self.sensitive = sensitive
        self.target = target
        self.byte_count = 8


def _batch(response: _Response, request) -> CollectionEventBatch:
    if response.endpoint == "FOOD":
        event = CollectionEvent(
            read_scope="READ_P25_01",
            observation_scope="OBS_P25_01",
            event_index=1,
            endpoint_id="FOOD",
            payload_family="runtime_test",
            payload_version="v1",
            payload={"data": {"poi_info": {"poi_id_str": "s1", "name": "store"}}},
        )
    else:
        event = CollectionEvent(
            read_scope="READ_P25_01",
            observation_scope="OBS_P25_01",
            event_index=2,
            endpoint_id="PRODUCTLIST",
            payload_family="runtime_test",
            payload_version="v1",
            payload={"data": {"food_spu_tags": [{"tag": "c", "current_page": 1, "has_next_page": False, "dynamic_spus": [{"id": 1, "name": "p", "min_price": 1, "skus": [{"id": 1, "spec": "s", "price": 1, "status": 1}]}]}]}},
        )
    return CollectionEventBatch(
        run_ref=request.run_ref,
        read_scope="READ_P25_01",
        observation_scope="OBS_P25_01",
        observed_at=request.issued_at,
        events=(event,),
    )


def _registry() -> ParserRegistry:
    return ParserRegistry(
        (ParserConfig(
            payload_family="runtime_test", payload_version="v1",
            category_id=Binding("category_id", "$.data.food_spu_tags[*].tag", ("string",), "category"),
            product_price=Binding("product_price", "$.data.food_spu_tags[*].dynamic_spus[*].min_price", ("number",), "product"),
            sku_price=Binding("sku_price", "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].price", ("number",), "sku"),
        ),),
        (FoodParserConfig(
            payload_family="runtime_test", payload_version="v1",
            merchant_id=Binding("merchant_id", "$.data.poi_info.poi_id_str", ("string",), "merchant"),
            merchant_name=Binding("merchant_name", "$.data.poi_info.name", ("string",), "merchant"),
        ),),
    )


def _context(request) -> P0Context:
    suffix = request.run_ref.split(":", 1)[1]
    return P0Context(
        run_ref=request.run_ref, batch_ref=f"batch:{suffix}", source_ref=request.source_ref,
        source_kind=request.source_kind, provider_contract_ref=request.provider_contract_ref,
        authorization_ref=request.authorization_ref, attempt_ref=request.attempt_ref,
        envelope_ref=f"envelope:{suffix}", observation_ref=f"observation:{suffix}",
        binding_context_ref=f"context:{suffix}", evidence_ref=f"evidence:{suffix}",
        source_integrity_ref=f"source-integrity:{suffix}", coverage_ref=f"coverage:{suffix}",
        coverage_scope_ref=f"scope:{suffix}", evidence_manifest_ref=f"evidence-manifest:{suffix}",
        observed_at=request.issued_at,
    )


def _policy(
    *,
    timeout: float = 1,
    endpoint_matches=None,
    contains_sensitive=None,
    target_matches=None,
    project=None,
    response_size=None,
) -> MitmproxySourcePolicy:
    return MitmproxySourcePolicy(
        endpoint_matches=endpoint_matches or (lambda method, host, path: (method, host, path) == ("GET", "loader.local", "/current-entry")),
        response_size=response_size or (lambda response: response.byte_count),
        contains_sensitive=contains_sensitive or (lambda response: response.sensitive),
        target_matches=target_matches or (lambda response, target: response.target == target.target_ref),
        project=project or (lambda response, request: _batch(response, request)),
        max_response_bytes=16,
        max_events=2,
        observation_timeout_seconds=timeout,
    )


def _references(*, expires_at: str = _EXPIRES_AT) -> dict[str, str]:
    return {
        "source_ref": "source:p25_demo_01",
        "provider_contract_ref": "provider-contract:p25_demo_01",
        "authorization_ref": "authorization:p25_demo_01",
        "run_ref": "run:p25_demo_01",
        "attempt_ref": "attempt:p25_demo_01",
        "input_lock_ref": "input-lock:p25_demo_01",
        "capability_ref": "capability:p25_demo_01",
        "issued_at": _ISSUED_AT,
        "expires_at": expires_at,
    }


def _spec(root: str, **overrides) -> LivePreparationSpec:
    values = {
        "output_root": root,
        "result_name": "p25prep",
        "runtime_target": CollectionTarget("target:p25_demo_01"),
        "target_binding_ref": "target-binding:p25_demo_01",
        "source_entry_ref": "source-entry:p25_demo_01",
        "output_root_ref": "output-root:p25_demo_01",
        "request_references": _references(),
        "now": lambda: _ISSUED_AT,
        "policy": _policy(),
        "parser_registry": _registry(),
        "p0_context_factory": _context,
    }
    values.update(overrides)
    return LivePreparationSpec(**values)


def _root(directory: str) -> str:
    path = Path(directory).resolve()
    path.chmod(0o700)
    return str(path)


def _text(diagnostic: dict[str, object]) -> str:
    return json.dumps(diagnostic, ensure_ascii=True, sort_keys=True)


class LivePreparationTests(unittest.TestCase):
    def test_prepare_command_reports_unknowns_and_consumes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            captured = io.StringIO()
            with redirect_stdout(captured):
                completed = main(["--output-root", root, "--result-name", "p25prep"])
            self.assertEqual(completed, 0)
            self.assertNotIn(root, captured.getvalue())
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            command = [
                sys.executable, "-B", "-m", "collection_adapter.live_prepare",
                "--output-root", root, "--result-name", "p25prep",
            ]
            completed_command = subprocess.run(
                command, cwd=Path(__file__).resolve().parents[2], env=env,
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(completed_command.returncode, 0)
        diagnostic = json.loads(completed_command.stdout)
        self.assertEqual(diagnostic["schema_version"], SCHEMA_VERSION)
        self.assertEqual(diagnostic["program_preparation"], "INCOMPLETE")
        self.assertEqual(diagnostic["developer_match_parameters"], "MISSING")
        self.assertEqual(diagnostic["closure_code"], "DEVELOPER_PARAMETERS_MISSING")
        self.assertEqual(diagnostic["output_precheck"], "PASS")
        self.assertEqual(diagnostic["source_attempts_consumed"], 0)
        self.assertTrue(diagnostic["not_started"])
        self.assertFalse(diagnostic["start_requested"])
        self.assertEqual(diagnostic["real_source_ready"], "UNKNOWN")
        self.assertEqual(diagnostic["network_readiness"], "UNKNOWN")
        self.assertEqual(diagnostic["real_interface_rules"], "UNKNOWN")
        self.assertEqual(diagnostic["real_field_rules"], "UNKNOWN")
        self.assertEqual(diagnostic["field_inventory"], "NOT_STARTED")
        self.assertEqual(diagnostic["product_live_capture_latch"], "CLOSED")
        self.assertEqual(diagnostic["product_execution_latch"], "CLOSED")
        self.assertEqual(diagnostic["unknown_conditions"], list(UNKNOWN_CONDITIONS))
        self.assertNotIn(root, completed_command.stdout)
        self.assertEqual(completed_command.stderr, "")

    def test_prepared_session_does_not_read_callbacks_or_consume_an_attempt(self) -> None:
        calls = []

        def endpoint_matches(method: str, host: str, path: str) -> bool:
            calls.append("endpoint")
            return (method, host, path) == ("GET", "loader.local", "/current-entry")

        with tempfile.TemporaryDirectory() as directory:
            session = prepare_live_entry(_spec(_root(directory), policy=_policy(endpoint_matches=endpoint_matches)))
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic["program_preparation"], "COMPLETE")
            self.assertEqual(diagnostic["receiver_ready"], "NO")
            self.assertEqual(diagnostic["developer_match_parameters"], "SUPPLIED")
            self.assertEqual(diagnostic["real_interface_rules"], "UNKNOWN")
            self.assertEqual(diagnostic["real_field_rules"], "UNKNOWN")
            self.assertEqual(diagnostic["field_inventory"], "NOT_STARTED")
            self.assertEqual(diagnostic["source_attempts_consumed"], 0)
            self.assertTrue(diagnostic["not_started"])
            self.assertFalse(diagnostic["local_receiver_armed"])
            self.assertEqual(diagnostic["closure_code"], "NONE")
            self.assertEqual(diagnostic["closure_status"], "OPEN")
            self.assertEqual(session.accept_callback(_ExplosiveFlow()), "MITMPROXY_BRIDGE_NOT_WAITING")
            self.assertEqual(calls, [])
            self.assertEqual(session.diagnostic()["source_attempts_consumed"], 0)
            self.assertEqual(session.diagnostic()["raw_callback_count"], 0)

    def test_output_precheck_blocks_start_and_a_later_explicit_start_sees_a_changed_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            relative = prepare_live_entry(LivePreparationSpec(output_root="relative/output", result_name="p25prep"))
            self.assertEqual(relative.diagnostic()["closure_code"], "RESULT_ROOT_INVALID")
            self.assertEqual(relative.diagnostic()["source_attempts_consumed"], 0)
            self.assertFalse(relative.start())

            missing = prepare_live_entry(LivePreparationSpec(output_root=str(Path(root) / "missing"), result_name="p25prep"))
            self.assertEqual(missing.diagnostic()["output_precheck"], "FAIL")
            self.assertEqual(missing.diagnostic()["source_attempts_consumed"], 0)

            opened = Path(root) / "opened"
            opened.mkdir(mode=0o755)
            loose = prepare_live_entry(LivePreparationSpec(output_root=str(opened), result_name="p25prep"))
            self.assertEqual(loose.diagnostic()["closure_code"], "RESULT_ROOT_INVALID")

            real = Path(root) / "real"
            real.mkdir(mode=0o700)
            link = Path(root) / "link"
            link.symlink_to(real, target_is_directory=True)
            linked = prepare_live_entry(LivePreparationSpec(output_root=str(link), result_name="p25prep"))
            self.assertEqual(linked.diagnostic()["closure_code"], "RESULT_ROOT_INVALID")
            self.assertFalse(linked.start())

            occupied = Path(root) / "occupied"
            occupied.mkdir(mode=0o700)
            (occupied / "p25prep").mkdir()
            collision = prepare_live_entry(LivePreparationSpec(output_root=str(occupied), result_name="p25prep"))
            self.assertEqual(collision.diagnostic()["closure_code"], "RESULT_TARGET_EXISTS")
            self.assertEqual(collision.diagnostic()["source_attempts_consumed"], 0)
            self.assertNotIn(str(occupied), _text(collision.diagnostic()))

            ready_root = Path(root) / "ready"
            ready_root.mkdir(mode=0o700)
            session = prepare_live_entry(_spec(str(ready_root)))
            self.assertEqual(session.diagnostic()["output_precheck"], "PASS")
            ready_root.chmod(0o755)
            self.assertFalse(session.start())
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic["closure_code"], "RESULT_ROOT_INVALID")
            self.assertEqual(diagnostic["output_precheck"], "FAIL")
            self.assertEqual(diagnostic["source_attempts_consumed"], 0)
            self.assertTrue(diagnostic["not_started"])
            self.assertFalse(diagnostic["start_requested"])
            self.assertEqual(diagnostic["receiver_ready"], "NO")

    def test_window_over_120_seconds_is_rejected_before_an_attempt(self) -> None:
        self.assertEqual(MAX_LIVE_WINDOW_SECONDS, 120)
        with self.assertRaisesRegex(MitmproxyBridgeError, "^MITMPROXY_BRIDGE_WINDOW_LIMIT$"):
            _policy(timeout=121)
        with self.assertRaisesRegex(MitmproxyBridgeError, "^MITMPROXY_BRIDGE_WINDOW_LIMIT$"):
            _policy(timeout=float("inf"))
        with self.assertRaisesRegex(MitmproxyBridgeError, "^MITMPROXY_BRIDGE_WINDOW_LIMIT$"):
            _policy(timeout=float("nan"))
        self.assertEqual(_policy(timeout=120).observation_timeout_seconds, 120)
        issued = datetime.strptime(_ISSUED_AT, "%Y-%m-%dT%H:%M:%SZ")
        allowed = (issued + timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rejected = (issued + timedelta(seconds=121)).strftime("%Y-%m-%dT%H:%M:%SZ")
        LiveP0Request(
            source_purpose="SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE_P0_VALIDATION",
            source_kind="SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE",
            target=CollectionTarget("target:p25_demo_01"),
            capabilities=("SINGLE_NETWORK_SOURCE_READ",),
            **_references(expires_at=allowed),
        )
        with self.assertRaisesRegex(LiveRequestError, "^LIVE_WINDOW_LIMIT$"):
            LiveP0Request(
                source_purpose="SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE_P0_VALIDATION",
                source_kind="SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE",
                target=CollectionTarget("target:p25_demo_01"),
                capabilities=("SINGLE_NETWORK_SOURCE_READ",),
                **_references(expires_at=rejected),
            )
        with tempfile.TemporaryDirectory() as directory:
            session = prepare_live_entry(_spec(
                _root(directory),
                request_references=_references(expires_at=rejected),
            ))
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic["closure_code"], "LIVE_WINDOW_LIMIT")
            self.assertEqual(diagnostic["program_preparation"], "INCOMPLETE")
            self.assertEqual(diagnostic["source_attempts_consumed"], 0)
            self.assertFalse(session.start())
            self.assertEqual(session.diagnostic()["source_attempts_consumed"], 0)

    def test_refreshed_clock_expires_during_the_wait_without_using_the_whole_window(self) -> None:
        calls = []

        def now() -> str:
            calls.append(1)
            return _ISSUED_AT if len(calls) == 1 else _EXPIRES_AT

        with tempfile.TemporaryDirectory() as directory:
            session = prepare_live_entry(_spec(_root(directory), now=now, policy=_policy(timeout=5)))
            started = time.monotonic()
            self.assertTrue(session.start())
            self.assertTrue(session.wait_closed(2))
            elapsed = time.monotonic() - started
        diagnostic = session.diagnostic()
        self.assertLess(elapsed, 1.5)
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(diagnostic["closure_code"], "LIVE_INPUT_LOCK_EXPIRED")
        self.assertEqual(diagnostic["source_attempts_consumed"], 1)
        self.assertTrue(diagnostic["start_requested"])
        self.assertFalse(diagnostic["not_started"])
        self.assertEqual(diagnostic["publish_status"], "NOT_RUN")
        self.assertEqual(diagnostic["qualified_event_count"], 0)
        self.assertEqual(diagnostic["product_live_capture_latch"], "CLOSED")
        self.assertEqual(diagnostic["product_execution_latch"], "CLOSED")
        self.assertFalse(session.start())

    def test_callback_after_expiry_is_not_projected(self) -> None:
        gate = threading.Event()

        def now() -> str:
            return _EXPIRES_AT if gate.is_set() else _ISSUED_AT

        with tempfile.TemporaryDirectory() as directory:
            session = prepare_live_entry(_spec(_root(directory), now=now, policy=_policy(timeout=5)))
            self.assertTrue(session.start())
            self.assertTrue(session.wait_until_receiver(1))
            gate.set()
            started = time.monotonic()
            callback_code = session.accept_callback(_ExplosiveFlow())
            self.assertIn(callback_code, {"LIVE_INPUT_LOCK_EXPIRED", "MITMPROXY_BRIDGE_NOT_WAITING"})
            self.assertTrue(session.wait_closed(2))
            elapsed = time.monotonic() - started
        diagnostic = session.diagnostic()
        self.assertLess(elapsed, 1.5)
        self.assertEqual(diagnostic["closure_code"], "LIVE_INPUT_LOCK_EXPIRED")
        entered = callback_code == "LIVE_INPUT_LOCK_EXPIRED"
        self.assertEqual(diagnostic["raw_callback_count"], int(entered))
        self.assertEqual(diagnostic["callback_entered"], "YES" if entered else "NO")
        self.assertEqual(diagnostic["qualified_event_count"], 0)
        self.assertNotIn(_SECRET, _text(diagnostic))

    def test_cancel_and_exception_paths_close_without_leaking_text_or_retrying(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            prepared = prepare_live_entry(_spec(root))
            cancelled = prepared.cancel()
            self.assertEqual(cancelled["closure_code"], "PREPARATION_CANCELLED")
            self.assertEqual(cancelled["source_attempts_consumed"], 0)
            self.assertTrue(cancelled["not_started"])
            self.assertFalse(prepared.start())
            self.assertEqual(prepared.diagnostic()["source_attempts_consumed"], 0)

        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            session = prepare_live_entry(_spec(root, policy=_policy(timeout=5)))
            self.assertTrue(session.start())
            self.assertTrue(session.wait_until_receiver(1))
            started = time.monotonic()
            diagnostic = session.cancel()
            self.assertTrue(session.wait_closed(2))
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 1.5)
            self.assertEqual(diagnostic["closure_code"], "MITMPROXY_BRIDGE_CANCELLED")
            self.assertEqual(diagnostic["source_attempts_consumed"], 1)
            self.assertEqual(diagnostic["closure_status"], "CLOSED")
            self.assertFalse(diagnostic["automatic_retry"])
            self.assertFalse((Path(root) / "p25prep").exists())
            self.assertFalse(session.start())

        def explode(*_args, **_kwargs):
            raise RuntimeError(_SECRET)

        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            session = prepare_live_entry(_spec(root, policy=_policy(project=explode)))
            self.assertTrue(session.start())
            self.assertTrue(session.wait_until_receiver(1))
            flow = _Flow(_Response())
            self.assertEqual(session.accept_callback(flow), "MITMPROXY_BRIDGE_PROJECTION_REJECTED")
            self.assertTrue(session.wait_closed(2))
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic["closure_code"], "MITMPROXY_BRIDGE_PROJECTION_REJECTED")
            self.assertEqual(diagnostic["raw_callback_count"], 1)
            self.assertEqual(diagnostic["target_match_count"], 1)
            self.assertEqual(diagnostic["qualified_event_count"], 0)
            self.assertEqual(diagnostic["parse_status"], "NOT_RUN")
            self.assertNotIn(_SECRET, _text(diagnostic))
            self.assertFalse((Path(root) / "p25prep").exists())

        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)

            def fail_context(_request):
                raise RuntimeError(_SECRET)

            session = prepare_live_entry(_spec(root, p0_context_factory=fail_context))
            self.assertTrue(session.start())
            self.assertTrue(session.wait_until_receiver(1))
            self.assertEqual(session.accept_callback(_Flow(_Response("FOOD"))), "MITMPROXY_BRIDGE_COLLECTED")
            self.assertEqual(session.accept_callback(_Flow(_Response("PRODUCTLIST"))), "MITMPROXY_BRIDGE_ACCEPTED")
            self.assertTrue(session.wait_closed(2))
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic["events_complete"], "YES")
            self.assertEqual(diagnostic["parse_status"], "REJECTED")
            self.assertEqual(diagnostic["publish_status"], "NOT_RUN")
            self.assertEqual(diagnostic["closure_code"], "LIVE_PARSE_REJECTED")
            self.assertEqual(diagnostic["qualified_event_count"], 0)
            self.assertNotIn(_SECRET, _text(diagnostic))
            self.assertNotIn("store", _text(diagnostic))
            self.assertFalse((Path(root) / "p25prep" / "manifest.json").exists())

    def test_non_target_and_sensitive_callbacks_keep_separate_counts(self) -> None:
        order = []

        def contains_sensitive(response: _Response) -> bool:
            order.append("sensitive")
            return True

        def target_matches(response: _Response, _target: CollectionTarget) -> bool:
            order.append("target")
            return response.target == "target:other"

        def project(response: _Response, request):
            order.append("project")
            return _batch(response, request)

        with tempfile.TemporaryDirectory() as directory:
            session = prepare_live_entry(_spec(_root(directory), policy=_policy(
                contains_sensitive=contains_sensitive,
                target_matches=target_matches,
                project=project,
            )))
            self.assertTrue(session.start())
            self.assertTrue(session.wait_until_receiver(1))
            flow = _Flow(_Response(sensitive=True, target="target:other"))
            self.assertEqual(session.accept_callback(flow), "MITMPROXY_BRIDGE_SENSITIVE_REJECTED")
            self.assertTrue(session.wait_closed(2))
        diagnostic = session.diagnostic()
        self.assertEqual(order, ["sensitive"])
        self.assertEqual(diagnostic["closure_code"], "MITMPROXY_BRIDGE_SENSITIVE_REJECTED")
        self.assertEqual(diagnostic["raw_callback_count"], 1)
        self.assertEqual(diagnostic["target_match_count"], 0)
        self.assertEqual(diagnostic["qualified_event_count"], 0)
        self.assertEqual(diagnostic["callback_entered"], "YES")
        self.assertEqual(diagnostic["target_matched"], "NO")
        self.assertEqual(diagnostic["events_complete"], "NO")

        with tempfile.TemporaryDirectory() as directory:
            seen = []
            session = prepare_live_entry(_spec(_root(directory), policy=_policy(
                target_matches=lambda response, target: seen.append("target") or response.target == target.target_ref,
                project=lambda response, request: seen.append("project") or _batch(response, request),
            )))
            self.assertTrue(session.start())
            self.assertTrue(session.wait_until_receiver(1))
            flow = _Flow(_Response(), path="/other")
            self.assertEqual(session.accept_callback(flow), "MITMPROXY_BRIDGE_IGNORED")
            self.assertTrue(session.diagnostic()["local_receiver_armed"])
            session.cancel()
            self.assertTrue(session.wait_closed(2))
        diagnostic = session.diagnostic()
        self.assertEqual(seen, [])
        self.assertEqual(diagnostic["closure_code"], "MITMPROXY_BRIDGE_CANCELLED")
        self.assertEqual(diagnostic["raw_callback_count"], 1)
        self.assertEqual(diagnostic["target_match_count"], 0)
        self.assertEqual(diagnostic["qualified_event_count"], 0)
        self.assertEqual(flow.request_reads, 1)

    def test_not_started_expiry_does_not_count_as_a_consumed_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session = prepare_live_entry(_spec(_root(directory), now=lambda: _EXPIRES_AT))
            self.assertEqual(session.diagnostic()["source_attempts_consumed"], 0)
            self.assertTrue(session.start())
            self.assertTrue(session.wait_closed(2))
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic["source_attempts_consumed"], 0)
            self.assertTrue(diagnostic["start_requested"])
            self.assertTrue(diagnostic["not_started"])
            self.assertEqual(diagnostic["closure_code"], "LIVE_INPUT_LOCK_EXPIRED")
            self.assertEqual(diagnostic["product_live_capture_latch"], "CLOSED")
            self.assertFalse(session.start())
            self.assertEqual(session.diagnostic()["source_attempts_consumed"], 0)

    def test_bounded_timeout_and_synthetic_publish_keep_product_latches_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            session = prepare_live_entry(_spec(root, policy=_policy(timeout=0.05)))
            started = time.monotonic()
            self.assertTrue(session.start())
            self.assertTrue(session.wait_closed(2))
            elapsed = time.monotonic() - started
            diagnostic = session.diagnostic()
            self.assertLess(elapsed, 1.5)
            self.assertEqual(diagnostic["closure_code"], "MITMPROXY_BRIDGE_TIMEOUT")
            self.assertEqual(diagnostic["source_attempts_consumed"], 1)
            self.assertEqual(diagnostic["raw_callback_count"], 0)
            self.assertEqual(diagnostic["max_window_seconds"], 120)
            self.assertFalse((Path(root) / "p25prep").exists())

        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            session = prepare_live_entry(_spec(root))
            self.assertTrue(session.start())
            self.assertTrue(session.wait_until_receiver(1))
            armed = session.diagnostic()
            self.assertTrue(armed["local_receiver_armed"])
            self.assertEqual(armed["source_attempts_consumed"], 1)
            self.assertEqual(armed["product_live_capture_latch"], "CLOSED")
            self.assertEqual(armed["product_execution_latch"], "CLOSED")
            self.assertEqual(armed["real_source_ready"], "UNKNOWN")
            self.assertEqual(armed["local_lease_scope"], "NOT_PRODUCT_LATCH")
            self.assertEqual(session.accept_callback(_Flow(_Response("FOOD"))), "MITMPROXY_BRIDGE_COLLECTED")
            partial = session.diagnostic()
            self.assertEqual(partial["raw_callback_count"], 1)
            self.assertEqual(partial["target_match_count"], 1)
            self.assertEqual(partial["events_complete"], "NO")
            self.assertEqual(partial["qualified_event_count"], 0)
            self.assertEqual(session.accept_callback(_Flow(_Response("PRODUCTLIST"))), "MITMPROXY_BRIDGE_ACCEPTED")
            self.assertTrue(session.wait_closed(2))
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic["closure_code"], "P0_PUBLISHED")
            self.assertEqual(diagnostic["parse_status"], "ACCEPTED")
            self.assertEqual(diagnostic["publish_status"], "PUBLISHED")
            self.assertEqual(diagnostic["events_complete"], "YES")
            self.assertGreaterEqual(diagnostic["qualified_event_count"], 1)
            self.assertEqual(diagnostic["source_attempts_consumed"], 1)
            self.assertEqual(diagnostic["product_live_capture_latch"], "CLOSED")
            self.assertTrue((Path(root) / "p25prep" / "manifest.json").is_file())
            self.assertNotIn("store", _text(diagnostic))
            self.assertNotIn(root, _text(diagnostic))

    def test_publish_rejection_closes_after_parse_without_a_partial_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            session = prepare_live_entry(_spec(root))
            self.assertTrue(session.start())
            self.assertTrue(session.wait_until_receiver(1))
            (Path(root) / "p25prep").mkdir()
            self.assertEqual(session.accept_callback(_Flow(_Response("FOOD"))), "MITMPROXY_BRIDGE_COLLECTED")
            self.assertEqual(session.accept_callback(_Flow(_Response("PRODUCTLIST"))), "MITMPROXY_BRIDGE_ACCEPTED")
            self.assertTrue(session.wait_closed(2))
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic["parse_status"], "ACCEPTED")
            self.assertEqual(diagnostic["publish_status"], "REJECTED")
            self.assertEqual(diagnostic["closure_code"], "LIVE_PUBLISH_REJECTED")
            self.assertGreaterEqual(diagnostic["qualified_event_count"], 1)
            self.assertFalse((Path(root) / "p25prep" / "manifest.json").exists())
            self.assertNotIn(root, _text(diagnostic))
            self.assertEqual(diagnostic["product_execution_latch"], "CLOSED")

    def test_diagnostic_schema_and_preparation_source_stay_closed(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        schema = json.loads((repository / "contracts/schemas/live-entry-diagnostic-v1.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["real_source_ready"]["const"], "UNKNOWN")
        self.assertEqual(schema["properties"]["product_live_capture_latch"]["const"], "CLOSED")
        self.assertEqual(schema["properties"]["product_execution_latch"]["const"], "CLOSED")
        self.assertEqual(schema["properties"]["max_window_seconds"]["const"], 120)
        self.assertEqual(schema["properties"]["field_inventory"]["const"], "NOT_STARTED")
        with tempfile.TemporaryDirectory() as directory:
            diagnostic = prepare_live_entry(_spec(_root(directory))).diagnostic()
        self.assertEqual(set(diagnostic), set(schema["required"]))
        source = (repository / "collection_adapter/live_prepare.py").read_text(encoding="utf-8")
        for forbidden in ("import socket", "import urllib", "import requests", "import subprocess", "import mitmproxy", "p21_live_companion"):
            self.assertNotIn(forbidden, source)
        bridge = (repository / "collection_adapter/mitmproxy_bridge.py").read_text(encoding="utf-8")
        for forbidden in ("import socket", "import urllib", "import requests", "import subprocess", "import os", "open("):
            self.assertNotIn(forbidden, bridge)
