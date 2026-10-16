from __future__ import annotations

from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import runpy
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout

from collection_adapter import CollectionEvent, CollectionEventBatch, CollectionTarget
from collection_adapter.live_mitmproxy_addon import (
    P21AddonConfig,
    P21LiveConsumer,
    P21MitmproxyAddon,
    configured_addon,
)
from collection_adapter.live_prepare import LivePreparationSpec, prepare_live_entry
from collection_adapter.mitmproxy_bridge import (
    MitmproxySourceEntry,
    MitmproxySourcePolicy,
    P21OutputBoundary,
)
from collection_core import P0Context
from parser_candidate import Binding, FoodParserConfig, ParserConfig, ParserRegistry


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
        raise AssertionError("request Cookie must not be read")

    @property
    def session(self):
        raise AssertionError("request session must not be read")


class _Response:
    byte_count = 8
    sensitive = False
    target = "target:runtime_p21_01"

    def __init__(self, endpoint: str = "FOOD") -> None:
        self.endpoint = endpoint


class _Flow:
    def __init__(self, endpoint: str = "FOOD") -> None:
        self.request = _ForbiddenRequest()
        self.response = _Response(endpoint)


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _expires() -> str:
    return (datetime.utcnow().replace(microsecond=0) + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _policy() -> MitmproxySourcePolicy:
    def project(response, request) -> CollectionEventBatch:
        if response.endpoint == "FOOD":
            event = CollectionEvent(
                read_scope="READ_P21_01",
                observation_scope="OBS_P21_01",
                event_index=1,
                endpoint_id="FOOD",
                payload_family="runtime_test",
                payload_version="v1",
                payload={"data": {"poi_info": {"poi_id_str": "s1", "name": "store"}}},
            )
        elif response.endpoint == "PRODUCTLIST":
            event = CollectionEvent(
                read_scope="READ_P21_01",
                observation_scope="OBS_P21_01",
                event_index=2,
                endpoint_id="PRODUCTLIST",
                payload_family="runtime_test",
                payload_version="v1",
                payload={"data": {"food_spu_tags": [{"tag": "c", "current_page": 1, "has_next_page": False, "dynamic_spus": [{"id": 1, "name": "p", "min_price": 1, "skus": [{"id": 1, "spec": "s", "price": 1, "status": 1}]}]}]}},
            )
        else:
            raise ValueError("unrecognized endpoint")
        return CollectionEventBatch(
            run_ref=request.run_ref,
            read_scope="READ_P21_01",
            observation_scope="OBS_P21_01",
            observed_at=request.issued_at,
            events=(event,),
        )

    return MitmproxySourcePolicy(
        endpoint_matches=lambda method, host, path: (method, host, path) == ("GET", "loader.local", "/current-entry"),
        response_size=lambda response: response.byte_count,
        contains_sensitive=lambda response: response.sensitive,
        target_matches=lambda response, target: response.target == target.target_ref,
        project=project,
        max_response_bytes=16,
        max_events=2,
        observation_timeout_seconds=1,
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
    suffix = request.run_ref[4:]
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


def _config(output_root: str) -> P21AddonConfig:
    entry = MitmproxySourceEntry(
        policy=_policy(), runtime_target=CollectionTarget("target:runtime_p21_01"),
        target_binding_ref="target-binding:runtime_p21_01", source_entry_ref="source-entry:runtime_p21_01",
        output_boundary=P21OutputBoundary("output-root:runtime_p21_01"),
    )
    return P21AddonConfig(
        source_entry=entry,
        request_references={
            "source_ref": "source:runtime_p21_01", "provider_contract_ref": "provider-contract:runtime_p21_01",
            "authorization_ref": "authorization:runtime_p21_01", "run_ref": "run:runtime_p21_01",
            "attempt_ref": "attempt:runtime_p21_01", "input_lock_ref": "input-lock:runtime_p21_01",
            "capability_ref": "capability:runtime_p21_01", "issued_at": _now(), "expires_at": _expires(),
        },
        now=_now,
        consumer=P21LiveConsumer(
            parser_registry=_registry(), p0_context_factory=_context,
            output_root=output_root, result_name="p21result",
        ),
    )


class P21MitmproxyAddonTests(unittest.TestCase):
    def test_unconfigured_addon_is_passive_and_has_no_attempt(self) -> None:
        addon = P21MitmproxyAddon()

        self.assertEqual(addon.response(_Flow()), "MITMPROXY_BRIDGE_NOT_WAITING")
        self.assertEqual(addon.snapshot(), {
            "state": "UNCONFIGURED", "source_attempts_consumed": 0,
            "live_capture_latch": "CLOSED", "execution_latch": "CLOSED", "reader_state": None, "receipt": None,
        })
        self.assertFalse(addon.start_once())

    def test_addon_rejects_second_configuration_and_never_uses_a_default_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory).chmod(0o700)
            addon = P21MitmproxyAddon()
            config = _config(str(Path(directory).resolve()))
            self.assertTrue(addon.configure_once(config))
            self.assertFalse(addon.configure_once(config))
            self.assertEqual(addon.snapshot(), {
                "state": "PREPARED", "source_attempts_consumed": 0,
                "live_capture_latch": "CLOSED", "execution_latch": "CLOSED", "reader_state": None, "receipt": None,
            })

    def test_prepared_addon_declares_zero_attempt_readiness_and_never_touches_a_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory).chmod(0o700)
            addon = configured_addon(_config(str(Path(directory).resolve())) )

            self.assertEqual(addon.readiness(), {
                "state": "PREPARED", "source_attempts_consumed": 0,
                "live_capture_latch": "CLOSED", "execution_latch": "CLOSED", "source_read_allowed": False,
                "p15_start_available": True,
            })
            self.assertEqual(addon.response(_Flow()), "MITMPROXY_BRIDGE_NOT_WAITING")
            self.assertEqual(addon.readiness()["source_attempts_consumed"], 0)

    def test_prepared_no_start_config_cannot_create_a_p15_attempt_or_inspect_a_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory).chmod(0o700)
            config = _config(str(Path(directory).resolve()))
            addon = P21MitmproxyAddon()
            addon.configure_once(P21AddonConfig(
                config.source_entry, config.request_references, config.now, config.consumer,
                p15_start_enabled=False,
            ))

            class _ExplosiveFlow:
                @property
                def request(self):
                    raise AssertionError("PREPARED must not inspect a flow")

            self.assertEqual(addon.readiness()["p15_start_available"], False)
            self.assertFalse(addon.start_once())
            self.assertEqual(addon.response(_ExplosiveFlow()), "MITMPROXY_BRIDGE_NOT_WAITING")
            self.assertEqual(addon.snapshot()["source_attempts_consumed"], 0)

    def test_configured_addon_creates_one_fresh_attempt_after_start_and_publishes_only_complete_p0(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory).chmod(0o700)
            addon = P21MitmproxyAddon()
            addon.configure_once(_config(str(Path(directory).resolve())))
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertTrue(addon.start_once())
                for _ in range(100):
                    if addon.snapshot()["reader_state"] == "WAITING":
                        break
                    time.sleep(0.002)
                self.assertEqual(addon.response(_Flow("FOOD")), "MITMPROXY_BRIDGE_COLLECTED")
                self.assertEqual(addon.response(_Flow("PRODUCTLIST")), "MITMPROXY_BRIDGE_ACCEPTED")
                self.assertTrue(addon.wait_closed(timeout=1))

            receipt = addon.snapshot()["receipt"]
            self.assertEqual(receipt["outcome"], "P0_PUBLISHED")
            self.assertEqual(receipt["source_attempt_consumed"], 1)
            self.assertEqual(receipt["live_capture_latch"], "CLOSED")
            self.assertTrue((Path(directory) / "p21result" / "manifest.json").is_file())
            self.assertNotIn("store", output.getvalue())
            self.assertFalse(addon.start_once())

    def test_runtime_clock_is_called_to_supply_a_fresh_p15_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory).chmod(0o700)
            calls = []

            def current_time() -> str:
                calls.append(True)
                return _now()

            config = _config(str(Path(directory).resolve()))
            addon = P21MitmproxyAddon()
            addon.configure_once(P21AddonConfig(
                config.source_entry, config.request_references, current_time, config.consumer,
            ))
            self.assertTrue(addon.start_once())
            self.assertTrue(addon.wait_until_waiting(timeout=1))
            self.assertEqual(addon.response(_Flow()), "MITMPROXY_BRIDGE_COLLECTED")
            self.assertEqual(addon.response(_Flow("PRODUCTLIST")), "MITMPROXY_BRIDGE_ACCEPTED")
            self.assertTrue(addon.wait_closed(timeout=1))
            self.assertTrue(calls)
            self.assertEqual(addon.snapshot()["receipt"]["outcome"], "P0_PUBLISHED")

    def test_timeout_retains_the_closed_bridge_status_in_the_real_attempt_stop_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory).chmod(0o700)
            config = _config(str(Path(directory).resolve()))
            short_policy = MitmproxySourcePolicy(
                endpoint_matches=config.source_entry._policy.endpoint_matches,
                response_size=config.source_entry._policy.response_size,
                contains_sensitive=config.source_entry._policy.contains_sensitive,
                target_matches=config.source_entry._policy.target_matches,
                project=config.source_entry._policy.project,
                max_response_bytes=16, max_events=2, observation_timeout_seconds=0,
            )
            entry = MitmproxySourceEntry(
                policy=short_policy, runtime_target=CollectionTarget("target:runtime_p21_01"),
                target_binding_ref="target-binding:runtime_p21_02", source_entry_ref="source-entry:runtime_p21_02",
                output_boundary=P21OutputBoundary("output-root:runtime_p21_02"),
            )
            addon = P21MitmproxyAddon()
            addon.configure_once(P21AddonConfig(entry, config.request_references, _now, config.consumer))
            self.assertTrue(addon.start_once())
            self.assertTrue(addon.wait_closed(timeout=1))
            self.assertEqual(addon.snapshot()["receipt"]["stop_code"], "MITMPROXY_BRIDGE_TIMEOUT")

    def test_addon_source_never_imports_mitmproxy_or_opens_network_or_system_io(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "collection_adapter/live_mitmproxy_addon.py").read_text(encoding="utf-8")
        for forbidden in ("import mitmproxy", "import socket", "import urllib", "import requests", "import subprocess", "import os"):
            self.assertNotIn(forbidden, source)

    def test_addon_can_be_loaded_as_a_direct_script_while_remaining_unconfigured(self) -> None:
        source = Path(__file__).resolve().parents[2] / "collection_adapter/live_mitmproxy_addon.py"
        namespace = runpy.run_path(str(source))
        addon = namespace["addons"][0]
        self.assertEqual(addon.snapshot()["state"], "UNCONFIGURED")
        self.assertEqual(addon.snapshot()["source_attempts_consumed"], 0)

    def test_loader_bootstrap_always_makes_the_project_root_importable(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "collection_adapter/live_mitmproxy_addon.py").read_text(encoding="utf-8")
        self.assertNotIn("if not __package__:", source)
        self.assertIn("if _bootstrap_root not in sys.path:", source)

    def test_loader_avoids_postponed_annotations_that_require_mitmproxy_module_registration(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "collection_adapter/live_mitmproxy_addon.py").read_text(encoding="utf-8")
        self.assertNotIn("from __future__ import annotations", source)

    def test_companion_config_api_never_starts_before_the_private_loader_requests_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory).chmod(0o700)
            addon = configured_addon(_config(str(Path(directory).resolve())))
            self.assertEqual(addon.snapshot()["state"], "PREPARED")
            self.assertEqual(addon.snapshot()["source_attempts_consumed"], 0)

    def test_preparation_entry_defers_start_without_an_external_companion(self) -> None:
        """Prepare stays at zero attempts until an explicit start call.

        This replaced a reader of tmp/p21_live_companion.py. That file is an old
        private technical configuration and is not a source of current rules.
        """

        with tempfile.TemporaryDirectory() as directory:
            root = str(Path(directory).resolve())
            Path(root).chmod(0o700)
            session = prepare_live_entry(LivePreparationSpec(
                output_root=root,
                result_name="p21result",
                runtime_target=CollectionTarget("target:runtime_p21_01"),
                target_binding_ref="target-binding:runtime_p21_01",
                source_entry_ref="source-entry:runtime_p21_01",
                output_root_ref="output-root:runtime_p21_01",
                request_references={
                    "source_ref": "source:runtime_p21_01",
                    "provider_contract_ref": "provider-contract:runtime_p21_01",
                    "authorization_ref": "authorization:runtime_p21_01",
                    "run_ref": "run:runtime_p21_01",
                    "attempt_ref": "attempt:runtime_p21_01",
                    "input_lock_ref": "input-lock:runtime_p21_01",
                    "capability_ref": "capability:runtime_p21_01",
                    "issued_at": _now(),
                    "expires_at": _expires(),
                },
                now=_now,
                policy=_policy(),
                parser_registry=_registry(),
                p0_context_factory=_context,
            ))

            class _ExplosiveFlow:
                @property
                def request(self):
                    raise AssertionError("PREPARED must not inspect a flow")

            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic["program_preparation"], "COMPLETE")
            self.assertEqual(diagnostic["source_attempts_consumed"], 0)
            self.assertTrue(diagnostic["not_started"])
            self.assertFalse(diagnostic["start_requested"])
            self.assertEqual(diagnostic["real_source_ready"], "UNKNOWN")
            self.assertEqual(diagnostic["product_live_capture_latch"], "CLOSED")
            self.assertEqual(diagnostic["product_execution_latch"], "CLOSED")
            self.assertFalse(diagnostic["local_receiver_armed"])
            self.assertEqual(session.accept_callback(_ExplosiveFlow()), "MITMPROXY_BRIDGE_NOT_WAITING")
            self.assertEqual(session.diagnostic()["source_attempts_consumed"], 0)
            self.assertTrue(session.diagnostic()["not_started"])

    def test_success_receipt_schema_is_closed_and_has_no_source_material_fields(self) -> None:
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / "contracts/schemas/live-p0-run-receipt-v1.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["outcome"]["const"], "P0_PUBLISHED")
        for forbidden in ("raw", "url", "header", "cookie", "session", "hash", "error"):
            self.assertNotIn(forbidden, {key.lower() for key in schema["properties"]})
