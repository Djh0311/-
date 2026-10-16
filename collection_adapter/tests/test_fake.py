from __future__ import annotations

import unittest

from collection_adapter import AdapterError, CollectionRunConfig, CollectionTarget
from collection_adapter.fake import (
    FakeAdapter,
    cross_observation_fixture,
    empty_fixture,
    format_error_fixture,
    success_fixture,
)


def _target() -> CollectionTarget:
    return CollectionTarget(target_ref="target:offline_demo_01")


def _config() -> CollectionRunConfig:
    return CollectionRunConfig(
        adapter_id="offline_fake",
        run_ref="run:offline_demo_01",
        read_scope="READ_DEMO_01",
        observation_scope="OBS_DEMO_01",
        observed_at="2026-08-11T10:00:00Z",
    )


class FakeAdapterTests(unittest.TestCase):
    def test_success_fixture_returns_a_single_same_observation_event_batch(self) -> None:
        config = _config()
        adapter = FakeAdapter({"target:offline_demo_01": success_fixture(config)})

        batch = adapter.collect(_target(), config)

        self.assertEqual(batch.read_scope, "READ_DEMO_01")
        self.assertEqual(batch.observation_scope, "OBS_DEMO_01")
        self.assertEqual([event.endpoint_id for event in batch.events], ["FOOD", "PRODUCTLIST"])

    def test_empty_and_format_error_fixtures_fail_with_closed_codes(self) -> None:
        config = _config()
        for fixture, code in (
            (empty_fixture(), "ADAPTER_EMPTY_RESULT"),
            (format_error_fixture(), "ADAPTER_FORMAT_INVALID"),
        ):
            with self.subTest(code=code):
                adapter = FakeAdapter({"target:offline_demo_01": fixture})
                with self.assertRaisesRegex(AdapterError, f"^{code}$"):
                    adapter.collect(_target(), config)

    def test_cross_observation_fixture_is_rejected_by_the_contract(self) -> None:
        config = _config()
        adapter = FakeAdapter({"target:offline_demo_01": cross_observation_fixture(config)})

        with self.assertRaisesRegex(AdapterError, "^ADAPTER_OBSERVATION_SCOPE_MISMATCH$"):
            adapter.collect(_target(), config)

    def test_unknown_target_never_falls_back_to_another_fixture(self) -> None:
        config = _config()
        adapter = FakeAdapter({"target:offline_demo_01": success_fixture(config)})
        unknown_target = CollectionTarget(target_ref="target:offline_demo_02")

        with self.assertRaisesRegex(AdapterError, "^ADAPTER_TARGET_UNAVAILABLE$"):
            adapter.collect(unknown_target, config)
