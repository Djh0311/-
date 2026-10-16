from __future__ import annotations

from pathlib import Path
import unittest

from collection_adapter import CollectionRunConfig, CollectionTarget
from collection_adapter.fake import FakeAdapter, success_fixture
from collection_adapter.live_adapter import (
    LiveAdapterError,
    LiveP0Adapter,
    LiveP0Observation,
    live_adapter_stop_receipt,
)
from collection_adapter.live_execution import LiveExecutionError, LiveP0ExecutionAuthority
from collection_adapter.tests.test_live_execution import _EXPIRES_AT, _ISSUED_AT, _request


def _batch():
    request = _request()
    config = CollectionRunConfig(
        adapter_id="offline_fake",
        run_ref=request.run_ref,
        read_scope="READ_LIVE_TEST_01",
        observation_scope="OBS_LIVE_TEST_01",
        observed_at=_ISSUED_AT,
    )
    return FakeAdapter({request.target.target_ref: success_fixture(config)}).collect(request.target, config)


class _Reader:
    def __init__(self, observation: LiveP0Observation) -> None:
        self.observation = observation
        self.calls = 0

    def read_once(self, _request, _lease) -> LiveP0Observation:
        self.calls += 1
        return self.observation


class LiveP0AdapterTests(unittest.TestCase):
    def test_adapter_maps_one_locked_in_memory_observation_and_destroys_its_boundary_reference(self) -> None:
        request = _request()
        observation = LiveP0Observation(_batch())
        reader = _Reader(observation)
        adapter = LiveP0Adapter(reader)
        authority = LiveP0ExecutionAuthority(request)

        result = adapter.execute_once(
            request,
            authority,
            now=_ISSUED_AT,
            consume=lambda events, supplied_request, lease: {
                "event_count": len(events),
                "target_ref": supplied_request.target.target_ref,
                "lease_open": lease.require_active(now="2026-08-11T12:00:30Z") is None,
            },
        )

        self.assertEqual(result, {
            "event_count": 2,
            "target_ref": "target:live_demo_01",
            "lease_open": True,
        })
        self.assertEqual(reader.calls, 1)
        self.assertTrue(observation.destroyed)
        self.assertEqual(authority.snapshot(), {
            "live_capture_latch": "CLOSED",
            "execution_latch": "CLOSED",
            "source_attempts_consumed": 1,
        })
        with self.assertRaisesRegex(LiveExecutionError, "^LIVE_INPUT_LOCK_USED$"):
            adapter.execute_once(request, authority, now=_ISSUED_AT, consume=lambda *_: None)
        self.assertEqual(reader.calls, 1)

    def test_scope_timeout_source_and_consumer_failures_close_latches_without_error_echoes(self) -> None:
        request = _request()
        wrong_batch = _batch()
        wrong_batch = type(wrong_batch)(
            run_ref="run:other_demo_01",
            read_scope=wrong_batch.read_scope,
            observation_scope=wrong_batch.observation_scope,
            observed_at=wrong_batch.observed_at,
            events=wrong_batch.events,
        )
        cases = (
            (
                LiveP0Adapter(_Reader(LiveP0Observation(wrong_batch))),
                lambda _events, _request, _lease: None,
                "LIVE_ADAPTER_SCOPE_INVALID",
            ),
            (
                LiveP0Adapter(_ExpiringReader()),
                lambda _events, _request, _lease: None,
                "LIVE_INPUT_LOCK_EXPIRED",
            ),
            (
                LiveP0Adapter(_FailingReader()),
                lambda _events, _request, _lease: None,
                "LIVE_SOURCE_READ_FAILED",
            ),
            (
                LiveP0Adapter(_Reader(LiveP0Observation(_batch()))),
                lambda _events, _request, _lease: (_ for _ in ()).throw(RuntimeError("source text must not escape")),
                "LIVE_P0_CONSUMER_REJECTED",
            ),
        )
        for adapter, consume, code in cases:
            with self.subTest(code=code):
                authority = LiveP0ExecutionAuthority(request)
                with self.assertRaisesRegex((LiveAdapterError, LiveExecutionError), f"^{code}$"):
                    adapter.execute_once(request, authority, now=_ISSUED_AT, consume=consume)
                self.assertEqual(authority.snapshot()["live_capture_latch"], "CLOSED")
                self.assertEqual(authority.snapshot()["execution_latch"], "CLOSED")

    def test_fresh_clock_prevents_consume_after_waiting_reader_reaches_expiry(self) -> None:
        request = _request()
        observation = LiveP0Observation(_batch())
        reader = _Reader(observation)
        consumed = []
        authority = LiveP0ExecutionAuthority(request)

        with self.assertRaisesRegex(LiveExecutionError, "^LIVE_INPUT_LOCK_EXPIRED$"):
            LiveP0Adapter(reader).execute_once(
                request,
                authority,
                now=_AdvancingClock((_ISSUED_AT, _EXPIRES_AT)),
                consume=lambda *_: consumed.append(True),
            )

        self.assertEqual(reader.calls, 1)
        self.assertEqual(consumed, [])
        self.assertTrue(observation.destroyed)
        self.assertEqual(authority.snapshot(), {
            "live_capture_latch": "CLOSED",
            "execution_latch": "CLOSED",
            "source_attempts_consumed": 1,
        })

    def test_value_free_stop_receipt_and_no_io_capability_surface(self) -> None:
        receipt = live_adapter_stop_receipt(_request(), "LIVE_SOURCE_READ_FAILED")
        self.assertEqual(receipt, {
            "schema_version": "collection-live-p0-adapter-stop/v1",
            "stop_code": "LIVE_SOURCE_READ_FAILED",
            "run_ref": "run:live_demo_01",
            "attempt_ref": "attempt:live_demo_01",
            "source_ref": "source:live_demo_01",
            "provider_contract_ref": "provider-contract:live_demo_01",
            "authorization_ref": "authorization:live_demo_01",
            "capability_ref": "capability:live_demo_01",
            "source_attempt_consumed": 1,
            "automatic_retry": False,
            "business_publication_allowed": False,
            "source_material_persisted": False,
            "latch_state": "CLOSED",
        })
        repository = Path(__file__).resolve().parents[2]
        source = (repository / "collection_adapter/live_adapter.py").read_text(encoding="utf-8")
        for forbidden in ("import socket", "import urllib", "import requests", "import subprocess", "import os"):
            self.assertNotIn(forbidden, source)


class _ExpiringReader:
    def read_once(self, _request, lease) -> LiveP0Observation:
        lease.require_active(now=_EXPIRES_AT)
        raise AssertionError("unreachable")


class _FailingReader:
    def read_once(self, _request, _lease) -> LiveP0Observation:
        raise RuntimeError("source text must not escape")


class _AdvancingClock:
    def __init__(self, values) -> None:
        self._values = iter(values)

    def __call__(self) -> str:
        return next(self._values)
