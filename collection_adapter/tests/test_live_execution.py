from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from collection_adapter import CollectionTarget
from collection_adapter.live_execution import (
    LIVE_P0_CAPABILITIES,
    LiveExecutionError,
    LiveP0ExecutionAuthority,
    LiveP0Request,
    LiveRequestError,
)


_ISSUED_AT = "2026-08-11T12:00:00Z"
_EXPIRES_AT = "2026-08-11T12:01:00Z"


def _request() -> LiveP0Request:
    return LiveP0Request(
        source_purpose="SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE_P0_VALIDATION",
        source_kind="SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE",
        target=CollectionTarget(target_ref="target:live_demo_01"),
        source_ref="source:live_demo_01",
        provider_contract_ref="provider-contract:live_demo_01",
        authorization_ref="authorization:live_demo_01",
        run_ref="run:live_demo_01",
        attempt_ref="attempt:live_demo_01",
        input_lock_ref="input-lock:live_demo_01",
        capability_ref="capability:live_demo_01",
        capabilities=("SINGLE_NETWORK_SOURCE_READ",),
        issued_at=_ISSUED_AT,
        expires_at=_EXPIRES_AT,
    )


class LiveP0ExecutionContractTests(unittest.TestCase):
    def test_complete_explicit_request_has_no_default_target_or_unlisted_capability(self) -> None:
        request = _request()

        self.assertEqual(request.target.target_ref, "target:live_demo_01")
        self.assertEqual(request.capabilities, LIVE_P0_CAPABILITIES)
        self.assertEqual(
            request.public_contract(),
            {
                "schema_version": "collection-live-p0-execution-request/v1",
                "source_purpose": "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE_P0_VALIDATION",
                "source_kind": "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE",
                "target_ref": "target:live_demo_01",
                "source_ref": "source:live_demo_01",
                "provider_contract_ref": "provider-contract:live_demo_01",
                "authorization_ref": "authorization:live_demo_01",
                "run_ref": "run:live_demo_01",
                "attempt_ref": "attempt:live_demo_01",
                "input_lock_ref": "input-lock:live_demo_01",
                "capability_ref": "capability:live_demo_01",
                "capabilities": ["SINGLE_NETWORK_SOURCE_READ"],
                "issued_at": _ISSUED_AT,
                "expires_at": _EXPIRES_AT,
                "max_attempts": 1,
                "automatic_retry": False,
                "source_material_persisted": False,
            },
        )

        with self.assertRaisesRegex(LiveRequestError, "^LIVE_SOURCE_PURPOSE_INVALID$"):
            replace(request, source_purpose="UNSPECIFIED")
        with self.assertRaisesRegex(LiveRequestError, "^LIVE_SOURCE_PURPOSE_MISMATCH$"):
            replace(request, source_kind="OFFICIAL_PUBLIC_DATASET")
        with self.assertRaisesRegex(LiveRequestError, "^LIVE_CAPABILITY_INVALID$"):
            replace(request, capabilities=("SINGLE_NETWORK_SOURCE_READ", "SYSTEM_PROXY"))

    def test_input_lock_latches_only_during_one_live_execution_and_consumes_the_request(self) -> None:
        request = _request()
        authority = LiveP0ExecutionAuthority(request)

        self.assertEqual(authority.snapshot(), {
            "live_capture_latch": "CLOSED",
            "execution_latch": "CLOSED",
            "source_attempts_consumed": 0,
        })
        with authority.acquire(request, now=_ISSUED_AT) as lease:
            self.assertEqual(lease.request, request)
            self.assertEqual(authority.snapshot(), {
                "live_capture_latch": "OPEN",
                "execution_latch": "OPEN",
                "source_attempts_consumed": 1,
            })
            lease.require_active(now="2026-08-11T12:00:30Z")
        self.assertEqual(authority.snapshot(), {
            "live_capture_latch": "CLOSED",
            "execution_latch": "CLOSED",
            "source_attempts_consumed": 1,
        })
        with self.assertRaisesRegex(LiveExecutionError, "^LIVE_INPUT_LOCK_USED$"):
            authority.acquire(request, now=_ISSUED_AT)

    def test_drift_expiry_and_exception_paths_never_leave_either_latch_open(self) -> None:
        request = _request()
        authority = LiveP0ExecutionAuthority(request)
        drifted = replace(request, target=CollectionTarget(target_ref="target:live_demo_02"))

        with self.assertRaisesRegex(LiveExecutionError, "^LIVE_INPUT_DRIFT$"):
            authority.acquire(drifted, now=_ISSUED_AT)
        self.assertEqual(authority.snapshot()["source_attempts_consumed"], 0)
        with self.assertRaisesRegex(LiveExecutionError, "^LIVE_INPUT_LOCK_EXPIRED$"):
            authority.acquire(request, now=_EXPIRES_AT)
        self.assertEqual(authority.snapshot(), {
            "live_capture_latch": "CLOSED",
            "execution_latch": "CLOSED",
            "source_attempts_consumed": 0,
        })

        authority = LiveP0ExecutionAuthority(request)
        with authority.acquire(request, now=_ISSUED_AT) as lease:
            with self.assertRaisesRegex(LiveExecutionError, "^LIVE_INPUT_LOCK_EXPIRED$"):
                lease.require_active(now=_EXPIRES_AT)
        self.assertEqual(authority.snapshot(), {
            "live_capture_latch": "CLOSED",
            "execution_latch": "CLOSED",
            "source_attempts_consumed": 1,
        })

        authority = LiveP0ExecutionAuthority(request)
        with self.assertRaisesRegex(RuntimeError, "^test failure$"):
            with authority.acquire(request, now=_ISSUED_AT):
                raise RuntimeError("test failure")
        self.assertEqual(authority.snapshot()["live_capture_latch"], "CLOSED")
        self.assertEqual(authority.snapshot()["execution_latch"], "CLOSED")

    def test_contract_schema_is_closed_and_live_module_has_no_network_or_system_imports(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        schema = json.loads(
            (repository / "contracts/schemas/live-p0-execution-request-v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["max_attempts"]["const"], 1)
        self.assertEqual(schema["properties"]["automatic_retry"]["const"], False)
        self.assertEqual(schema["properties"]["source_material_persisted"]["const"], False)

        source = (repository / "collection_adapter/live_execution.py").read_text(encoding="utf-8")
        for forbidden in ("import socket", "import urllib", "import requests", "import subprocess", "import os"):
            self.assertNotIn(forbidden, source)
