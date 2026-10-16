from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from collection_adapter import CollectionTarget
from collection_adapter.live_execution import LiveP0Request
from collection_adapter.live_p0_entry import (
    HISTORICAL_TARGET_REF,
    P17_FORBIDDEN_CAPABILITIES,
    P17_NETWORK_CAPABILITY,
    HistoricalTargetBinding,
    LiveP0EntryError,
    bind_p17_request,
    source_entry_unavailable_stop,
)
from collection_adapter.tests.test_live_execution import _request


class LiveP0EntryTests(unittest.TestCase):
    def test_p17_requires_an_explicit_auditable_runtime_mapping_for_the_historical_target(self) -> None:
        request = _request()
        binding = HistoricalTargetBinding(
            historical_target_ref=HISTORICAL_TARGET_REF,
            runtime_target=CollectionTarget(target_ref="target:live_demo_01"),
            target_binding_ref="target-binding:live_demo_01",
        )

        result = bind_p17_request(request, binding)

        self.assertEqual(result, {
            "historical_target_ref": "TGT-HZ-XCJ-GFTJ-001",
            "historical_target_status": "NOT_OBSERVED",
            "runtime_target_ref": "target:live_demo_01",
            "target_binding_ref": "target-binding:live_demo_01",
            "route_id": "OWNED_STRUCTURED_EVENT",
            "source_kind": "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE",
            "source_purpose": "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE_P0_VALIDATION",
            "network_capability": "SINGLE_NETWORK_SOURCE_READ",
            "forbidden_capabilities": list(P17_FORBIDDEN_CAPABILITIES),
        })
        with self.assertRaisesRegex(LiveP0EntryError, "^LIVE_HISTORICAL_TARGET_INVALID$"):
            HistoricalTargetBinding(
                historical_target_ref="TGT-HZ-XCJ-GFTJ-002",
                runtime_target=request.target,
                target_binding_ref="target-binding:live_demo_01",
            )
        with self.assertRaisesRegex(LiveP0EntryError, "^LIVE_TARGET_BINDING_DRIFT$"):
            bind_p17_request(
                request,
                HistoricalTargetBinding(
                    historical_target_ref=HISTORICAL_TARGET_REF,
                    runtime_target=CollectionTarget(target_ref="target:live_demo_02"),
                    target_binding_ref="target-binding:live_demo_02",
                ),
            )
        with self.assertRaisesRegex(LiveP0EntryError, "^LIVE_P17_SOURCE_POLICY_INVALID$"):
            bind_p17_request(
                replace(
                    request,
                    source_purpose="OFFICIAL_PUBLIC_DATASET_P0_VALIDATION",
                    source_kind="OFFICIAL_PUBLIC_DATASET",
                ),
                binding,
            )

    def test_missing_new_source_entry_produces_a_value_free_zero_attempt_closed_stop(self) -> None:
        stop = source_entry_unavailable_stop()

        self.assertEqual(stop, {
            "schema_version": "collection-live-p0-entry-stop/v1",
            "stop_code": "LIVE_SOURCE_ENTRY_UNAVAILABLE",
            "historical_target_ref": "TGT-HZ-XCJ-GFTJ-001",
            "historical_target_status": "NOT_OBSERVED",
            "runtime_target_binding": "NOT_BOUND",
            "route_id": "OWNED_STRUCTURED_EVENT",
            "source_kind": "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE",
            "source_purpose": "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE_P0_VALIDATION",
            "network_capability": P17_NETWORK_CAPABILITY,
            "forbidden_capabilities": list(P17_FORBIDDEN_CAPABILITIES),
            "live_capture_latch": "CLOSED",
            "execution_latch": "CLOSED",
            "source_attempts_consumed": 0,
            "automatic_retry": False,
            "source_material_persisted": False,
            "business_publication_allowed": False,
        })

    def test_entry_stop_contract_is_closed_and_p17_module_has_no_io_imports(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        schema = json.loads(
            (repository / "contracts/schemas/live-p0-entry-stop-v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["stop_code"]["const"], "LIVE_SOURCE_ENTRY_UNAVAILABLE")
        self.assertEqual(schema["properties"]["source_attempts_consumed"]["const"], 0)
        self.assertEqual(schema["properties"]["network_capability"]["const"], P17_NETWORK_CAPABILITY)
        source = (repository / "collection_adapter/live_p0_entry.py").read_text(encoding="utf-8")
        for forbidden in ("import socket", "import urllib", "import requests", "import subprocess", "import os"):
            self.assertNotIn(forbidden, source)
