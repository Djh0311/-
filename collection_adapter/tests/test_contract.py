from __future__ import annotations

import unittest

from collection_adapter import (
    AdapterError,
    CollectionEvent,
    CollectionEventBatch,
    CollectionRunConfig,
    CollectionTarget,
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


def _event(index: int, endpoint_id: str = "FOOD") -> CollectionEvent:
    payload = (
        {"data": {"poi_info": {"poi_id_str": "store-demo-01", "name": "Demo Store"}}}
        if endpoint_id == "FOOD"
        else {"data": {"food_spu_tags": []}}
    )
    return CollectionEvent(
        read_scope="READ_DEMO_01",
        observation_scope="OBS_DEMO_01",
        event_index=index,
        endpoint_id=endpoint_id,
        payload_family="synthetic_productlist",
        payload_version="v1",
        payload=payload,
    )


class CollectionContractTests(unittest.TestCase):
    def test_accepts_explicit_target_config_and_exact_events(self) -> None:
        target = _target()
        config = _config()
        batch = CollectionEventBatch.from_events((_event(1), _event(2, "PRODUCTLIST")), config)

        self.assertEqual(target.target_ref, "target:offline_demo_01")
        self.assertEqual(batch.read_scope, config.read_scope)
        self.assertEqual(batch.observation_scope, config.observation_scope)
        self.assertEqual(
            tuple(event.endpoint_id for event in batch.to_parser_events()),
            ("FOOD", "PRODUCTLIST"),
        )

    def test_rejects_invalid_config_and_event_model(self) -> None:
        with self.assertRaisesRegex(AdapterError, "^ADAPTER_TARGET_INVALID$"):
            CollectionTarget(target_ref="demo")
        with self.assertRaisesRegex(AdapterError, "^ADAPTER_CONFIG_INVALID$"):
            CollectionRunConfig(
                adapter_id="offline fake",
                run_ref="run:offline_demo_01",
                read_scope="READ_DEMO_01",
                observation_scope="OBS_DEMO_01",
                observed_at="2026-08-11T10:00:00Z",
            )
        with self.assertRaisesRegex(AdapterError, "^ADAPTER_EVENT_INVALID$"):
            CollectionEvent(
                read_scope="READ_DEMO_01",
                observation_scope="OBS_DEMO_01",
                event_index=1,
                endpoint_id="UNKNOWN",
                payload_family="synthetic_productlist",
                payload_version="v1",
                payload={},
            )

    def test_rejects_empty_and_cross_observation_or_read_scope_input(self) -> None:
        config = _config()
        with self.assertRaisesRegex(AdapterError, "^ADAPTER_EMPTY_RESULT$"):
            CollectionEventBatch.from_events((), config)

        other_observation = CollectionEvent(
            read_scope="READ_DEMO_01",
            observation_scope="OBS_OTHER_01",
            event_index=2,
            endpoint_id="PRODUCTLIST",
            payload_family="synthetic_productlist",
            payload_version="v1",
            payload={"data": {"food_spu_tags": []}},
        )
        with self.assertRaisesRegex(AdapterError, "^ADAPTER_OBSERVATION_SCOPE_MISMATCH$"):
            CollectionEventBatch.from_events((_event(1), other_observation), config)

        other_read = CollectionEvent(
            read_scope="READ_OTHER_01",
            observation_scope="OBS_DEMO_01",
            event_index=2,
            endpoint_id="PRODUCTLIST",
            payload_family="synthetic_productlist",
            payload_version="v1",
            payload={"data": {"food_spu_tags": []}},
        )
        with self.assertRaisesRegex(AdapterError, "^ADAPTER_READ_SCOPE_MISMATCH$"):
            CollectionEventBatch.from_events((_event(1), other_read), config)

    def test_batch_constructor_cannot_bypass_empty_or_scope_validation(self) -> None:
        config = _config()
        with self.assertRaisesRegex(AdapterError, "^ADAPTER_EMPTY_RESULT$"):
            CollectionEventBatch(
                run_ref=config.run_ref,
                read_scope=config.read_scope,
                observation_scope=config.observation_scope,
                observed_at=config.observed_at,
                events=(),
            )

        mismatched = CollectionEvent(
            read_scope=config.read_scope,
            observation_scope="OBS_OTHER_01",
            event_index=2,
            endpoint_id="PRODUCTLIST",
            payload_family="synthetic_productlist",
            payload_version="v1",
            payload={"data": {"food_spu_tags": []}},
        )
        with self.assertRaisesRegex(AdapterError, "^ADAPTER_OBSERVATION_SCOPE_MISMATCH$"):
            CollectionEventBatch(
                run_ref=config.run_ref,
                read_scope=config.read_scope,
                observation_scope=config.observation_scope,
                observed_at=config.observed_at,
                events=(_event(1), mismatched),
            )
