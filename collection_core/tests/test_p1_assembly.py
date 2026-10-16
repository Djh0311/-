from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from collection_adapter import CollectionEvent, CollectionRunConfig
from collection_adapter.fake import FakeFixture, p1_cross_observation_fixture, p1_success_fixture
from collection_adapter.runner import default_p0_context
from collection_core.p1 import P1AssemblyError, build_p1_batch, validate_p1_batch
from parser_candidate import synthetic_p1_registry


def _config() -> CollectionRunConfig:
    return CollectionRunConfig(
        adapter_id="offline_fake",
        run_ref="run:stage03_assembly_01",
        read_scope="READ_STAGE03_01",
        observation_scope="OBS_STAGE03_01",
        observed_at="2026-08-11T10:00:00Z",
    )


def _build(fixture: FakeFixture) -> dict[str, object]:
    config = _config()
    return build_p1_batch(
        tuple(event.to_parser_event() for event in fixture.events),
        synthetic_p1_registry(),
        default_p0_context(config),
    )


def _replace_event(fixture: FakeFixture, index: int, payload: dict[str, object]) -> FakeFixture:
    event = fixture.events[index]
    replacement = CollectionEvent(
        read_scope=event.read_scope,
        observation_scope=event.observation_scope,
        event_index=event.event_index,
        endpoint_id=event.endpoint_id,
        payload_family=event.payload_family,
        payload_version=event.payload_version,
        payload=payload,
    )
    events = list(fixture.events)
    events[index] = replacement
    return FakeFixture(events=tuple(events))


class P1AssemblyTests(unittest.TestCase):
    def test_p1_batch_and_record_contracts_are_separately_versioned_closed_objects(self) -> None:
        schemas = Path(__file__).parents[2] / "contracts" / "schemas"
        batch = json.loads(schemas.joinpath("p1-batch-v1.schema.json").read_text(encoding="utf-8"))
        record = json.loads(schemas.joinpath("p1-record-v1.schema.json").read_text(encoding="utf-8"))

        self.assertFalse(batch["additionalProperties"])
        self.assertFalse(record["additionalProperties"])
        self.assertEqual(batch["properties"]["schema_version"]["const"], "collection-p1-batch/v1")
        self.assertEqual(record["properties"]["schema_version"]["const"], "collection-p1-record/v1")
        self.assertIn("p0_business_record_ref", record["required"])
        self.assertIn("p1-field-value-v1.schema.json", json.dumps(record))

    def test_builds_same_observation_p1_sku_record_while_preserving_p0_core(self) -> None:
        result = _build(p1_success_fixture(_config()))

        self.assertEqual(result["schema_version"], "collection-p1-batch/v1")
        self.assertEqual(result["p0_result"]["business_records"][0]["core_binding"]["binding_status"], "SAME_OBSERVATION")
        record = result["p1_records"][0]
        self.assertEqual(record["p0_business_record_ref"], "business-record:p0_0001")
        self.assertEqual(record["run_ref"], "run:stage03_assembly_01")
        self.assertEqual(record["observation_ref"], "observation:OBS_STAGE03_01")

        fields = {field["field_name"]: field for field in record["p1_fields"]}
        self.assertEqual(fields["category_name"]["normalized_value"], "Demo Category")
        self.assertEqual(fields["sku_ref"]["normalized_value"], "sku:sku_00001001")
        self.assertEqual(fields["availability_status"]["normalized_value"], "AVAILABLE")
        self.assertEqual(fields["original_price_minor"]["normalized_value"], 1500)
        self.assertEqual(fields["activity_price_minor"]["normalized_value"], 1250)
        self.assertEqual(fields["promotion_discount_minor"]["normalized_value"], 250)
        self.assertEqual(fields["promotion_discount_bps"]["observation_presence"], "NOT_APPLICABLE")
        self.assertEqual(fields["delivery_min_order_minor"]["normalized_value"], 2000)
        self.assertEqual(fields["category_ref"]["owner_entity_kind"], "PRODUCT")
        self.assertEqual(fields["promotion_scope"]["owner_entity_kind"], "SKU")
        self.assertEqual(fields["delivery_status"]["owner_entity_kind"], "STORE")

    def test_missing_optional_values_are_explicit_and_not_replaced_with_zero(self) -> None:
        fixture = p1_success_fixture(_config())
        product_payload = copy.deepcopy(fixture.events[1].payload)
        sku = product_payload["data"]["food_spu_tags"][0]["dynamic_spus"][0]["skus"][0]  # type: ignore[index]
        for key in ("origin_price", "activity_price", "promotion"):
            sku.pop(key)
        fixture = _replace_event(fixture, 1, product_payload)
        food_payload = copy.deepcopy(fixture.events[0].payload)
        poi = food_payload["data"]["poi_info"]  # type: ignore[index]
        for key in ("delivery_fee", "min_order", "delivery_status"):
            poi.pop(key)
        result = _build(_replace_event(fixture, 0, food_payload))

        fields = {field["field_name"]: field for field in result["p1_records"][0]["p1_fields"]}
        for name in ("original_price_minor", "activity_price_minor", "promotion_type", "delivery_fee_minor"):
            self.assertEqual(fields[name]["observation_presence"], "NOT_SHOWN")
            self.assertIsNone(fields[name]["normalized_value"])
            self.assertIsNone(fields[name]["value_encoding"])
            self.assertIsNone(fields[name]["anchor_ref"])

    def test_percent_promotion_uses_explicit_basis_points_without_deriving_a_money_discount(self) -> None:
        fixture = p1_success_fixture(_config())
        product_payload = copy.deepcopy(fixture.events[1].payload)
        promotion = product_payload["data"]["food_spu_tags"][0]["dynamic_spus"][0]["skus"][0]["promotion"]  # type: ignore[index]
        promotion["type"] = "PERCENT_DISCOUNT"
        promotion.pop("discount")
        promotion["discount_bps"] = 8500

        result = _build(_replace_event(fixture, 1, product_payload))
        fields = {field["field_name"]: field for field in result["p1_records"][0]["p1_fields"]}
        self.assertEqual(fields["promotion_discount_bps"]["normalized_value"], 8500)
        self.assertEqual(fields["promotion_discount_minor"]["observation_presence"], "NOT_APPLICABLE")
        self.assertIsNone(fields["promotion_discount_minor"]["normalized_value"])

    def test_keeps_multiple_skus_separate_and_rejects_cross_observation_or_owner_tampering(self) -> None:
        fixture = p1_success_fixture(_config())
        product_payload = copy.deepcopy(fixture.events[1].payload)
        skus = product_payload["data"]["food_spu_tags"][0]["dynamic_spus"][0]["skus"]  # type: ignore[index]
        second = copy.deepcopy(skus[0])
        second["id"] = 1002
        second["spec"] = "large"
        skus.append(second)
        result = _build(_replace_event(fixture, 1, product_payload))
        self.assertEqual(len(result["p1_records"]), 2)
        self.assertEqual(
            [
                {field["field_name"]: field for field in record["p1_fields"]}["sku_ref"]["normalized_value"]
                for record in result["p1_records"]
            ],
            ["sku:sku_00001001", "sku:sku_00001002"],
        )

        with self.assertRaisesRegex(P1AssemblyError, "^P1_PARSE_FAILED$"):
            _build(p1_cross_observation_fixture(_config()))

        cross_observation = copy.deepcopy(result)
        cross_observation["p1_records"][0]["p1_fields"][0]["observation_ref"] = "observation:OBS_STAGE03_02"
        with self.assertRaisesRegex(P1AssemblyError, "^P1_CROSS_OBSERVATION_VALUE$"):
            validate_p1_batch(cross_observation)

        owner_tamper = copy.deepcopy(result)
        promotion = next(
            field for field in owner_tamper["p1_records"][0]["p1_fields"]
            if field["field_name"] == "promotion_scope"
        )
        promotion["owner_entity_kind"] = "STORE"
        with self.assertRaisesRegex(P1AssemblyError, "^P1_OWNER_BINDING_INVALID$"):
            validate_p1_batch(owner_tamper)
