from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from collection_core import P0Context, P0Error, P0PublisherError, build_p0_batch, publish_p0_bundle, validate_p0_batch
from parser_candidate import Binding, CaptureParserEvent, FoodParserConfig, ParserConfig, ParserRegistry


def _registry() -> ParserRegistry:
    return ParserRegistry(
        (
            ParserConfig(
                payload_family="synthetic_productlist",
                payload_version="v1",
                category_id=Binding("category_id", "$.data.food_spu_tags[*].tag", ("string",), "category"),
                product_price=Binding("product_price", "$.data.food_spu_tags[*].dynamic_spus[*].min_price", ("number",), "product"),
                sku_price=Binding("sku_price", "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].price", ("number",), "sku"),
            ),
        ),
        (
            FoodParserConfig(
                payload_family="synthetic_productlist",
                payload_version="v1",
                merchant_id=Binding("merchant_id", "$.data.poi_info.poi_id_str", ("string",), "merchant"),
                merchant_name=Binding("merchant_name", "$.data.poi_info.name", ("string",), "merchant"),
            ),
        ),
    )


def _context() -> P0Context:
    return P0Context(
        run_ref="run:p0_test_01",
        batch_ref="batch:p0_test_01",
        source_ref="source:p0_test_01",
        source_kind="USER_OWNED_EXPORT",
        provider_contract_ref="provider-contract:p0_test_01",
        authorization_ref="authorization:p0_test_01",
        attempt_ref="attempt:p0_test_01",
        envelope_ref="envelope:p0_test_01",
        observation_ref="observation:p0_test_01",
        binding_context_ref="context:p0_test_01",
        evidence_ref="evidence:p0_test_01",
        source_integrity_ref="source-integrity:p0_test_01",
        coverage_ref="coverage:p0_test_01",
        coverage_scope_ref="scope:p0_test_01",
        evidence_manifest_ref="evidence-manifest:p0_test_01",
        observed_at="2026-08-11T10:00:00Z",
    )


def _events() -> tuple[CaptureParserEvent, CaptureParserEvent]:
    food = CaptureParserEvent(
        read_scope="READ_P0_01",
        observation_scope="OBS_P0_01",
        event_index=1,
        endpoint_id="FOOD",
        payload_family="synthetic_productlist",
        payload_version="v1",
        payload={"data": {"poi_info": {"poi_id_str": "store-01", "name": "Store One"}}},
    )
    product = CaptureParserEvent(
        read_scope="READ_P0_01",
        observation_scope="OBS_P0_01",
        event_index=2,
        endpoint_id="PRODUCTLIST",
        payload_family="synthetic_productlist",
        payload_version="v1",
        payload={
            "data": {
                "food_spu_tags": [{
                    "tag": "category-01",
                    "current_page": 1,
                    "has_next_page": False,
                    "dynamic_spus": [{
                        "id": 101,
                        "name": "Product One",
                        "min_price": 12.5,
                        "skus": [{"id": 1001, "spec": "regular", "price": 12.5, "status": 1}],
                    }],
                }]
            }
        },
    )
    return food, product


class P0BatchTests(unittest.TestCase):
    def test_builds_a_same_observation_store_product_display_price_record(self) -> None:
        result = build_p0_batch(_events(), _registry(), _context())

        batch = result["observation_batch"]
        record = result["business_records"][0]
        self.assertEqual(batch["business_record_count"], 1)
        self.assertEqual(batch["field_observation_count"], 6)
        self.assertEqual(record["core_binding"]["binding_status"], "SAME_OBSERVATION")
        fields = {field["field_name"]: field for field in record["field_observations"]}
        self.assertEqual(fields["display_price_minor"]["normalized_value"], 1250)
        self.assertEqual(fields["display_price_minor"]["public_value_raw"], "12.50")
        self.assertEqual(fields["currency"]["normalized_value"], "CNY")
        self.assertTrue(all(field["cross_source_fill"] is False for field in fields.values()))
        validate_p0_batch(result)

    def test_rejects_non_minor_display_price_and_cross_observation_tampering(self) -> None:
        product = _events()[1]
        bad_payload = copy.deepcopy(product.payload)
        bad_payload["data"]["food_spu_tags"][0]["dynamic_spus"][0]["min_price"] = 12.345
        bad_product = CaptureParserEvent(
            read_scope=product.read_scope,
            observation_scope=product.observation_scope,
            event_index=product.event_index,
            endpoint_id=product.endpoint_id,
            payload_family=product.payload_family,
            payload_version=product.payload_version,
            payload=bad_payload,
        )
        with self.assertRaisesRegex(P0Error, "^P0_DISPLAY_PRICE_INVALID$"):
            build_p0_batch((_events()[0], bad_product), _registry(), _context())

        result = build_p0_batch(_events(), _registry(), _context())
        result["business_records"][0]["field_observations"][0]["observation_ref"] = "observation:p0_other_01"
        with self.assertRaisesRegex(P0Error, "^P0_CROSS_OBSERVATION_VALUE$"):
            validate_p0_batch(result)

    def test_publisher_is_deterministic_and_never_overwrites_a_target(self) -> None:
        result = build_p0_batch(_events(), _registry(), _context())
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            root = str(Path(directory).resolve())
            first = publish_p0_bundle(root, "p0-records.json", result)
            self.assertEqual(len(first["sha256"]), 64)
            published = Path(root) / "p0-records.json"
            self.assertTrue(published.is_file())
            with published.open(encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["readable_records"][0]["price_yuan"], "12.50")
            with self.assertRaisesRegex(P0PublisherError, "^P0_TARGET_EXISTS$"):
                publish_p0_bundle(root, "p0-records.json", result)

    def test_accepts_an_explicit_synthetic_offline_fixture_source_kind(self) -> None:
        context = _context()
        synthetic_context = P0Context(
            **{**context.__dict__, "source_kind": "SYNTHETIC_OFFLINE_FIXTURE"}
        )

        result = build_p0_batch(_events(), _registry(), synthetic_context)

        self.assertEqual(
            result["observation_batch"]["source_kind"],
            "SYNTHETIC_OFFLINE_FIXTURE",
        )

    def test_synthetic_source_kind_is_allowed_by_each_p0_output_contract(self) -> None:
        root = Path(__file__).resolve().parents[2]
        for name in (
            "observation-batch.schema.json",
            "field-observation-v2.schema.json",
            "business-record-v2.schema.json",
        ):
            with self.subTest(name=name):
                with (root / "contracts" / "schemas" / name).open(encoding="utf-8") as handle:
                    schema = json.load(handle)
                self.assertIn(
                    "SYNTHETIC_OFFLINE_FIXTURE",
                    schema["properties"]["source_kind"]["enum"],
                )
