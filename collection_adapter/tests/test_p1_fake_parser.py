from __future__ import annotations

import copy
from dataclasses import replace
import unittest

from collection_adapter import AdapterError, CollectionEvent, CollectionRunConfig, CollectionTarget
from collection_adapter.fake import FakeAdapter, FakeFixture, p1_cross_observation_fixture, p1_success_fixture
from parser_candidate import ParserError, parse_capture_read_scope, synthetic_p1_productlist_config, synthetic_p1_registry


def _config() -> CollectionRunConfig:
    return CollectionRunConfig(
        adapter_id="offline_fake",
        run_ref="run:stage03_parser_01",
        read_scope="READ_STAGE03_01",
        observation_scope="OBS_STAGE03_01",
        observed_at="2026-08-11T10:00:00Z",
    )


def _target() -> CollectionTarget:
    return CollectionTarget(target_ref="target:offline_demo_01")


def _parsed(fixture: FakeFixture) -> dict[str, object]:
    config = _config()
    batch = FakeAdapter({"target:offline_demo_01": fixture}).collect(_target(), config)
    return parse_capture_read_scope(batch.to_parser_events(), synthetic_p1_registry())


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


class P1SyntheticParserTests(unittest.TestCase):
    def test_registered_synthetic_profile_preserves_each_p1_value_and_source_label(self) -> None:
        parsed = _parsed(p1_success_fixture(_config()))

        merchant = parsed["merchant"]
        category = parsed["productlist_events"][0]["category_pages"][0]
        product = category["products"][0]
        sku = product["skus"][0]
        self.assertEqual(category["extensions"]["p1_category_ref"], {
            "value": "category-demo-01", "source_label": "SYNTHETIC_P1_CATEGORY"
        })
        self.assertEqual(category["extensions"]["p1_category_name"], {
            "value": "Demo Category", "source_label": "SYNTHETIC_P1_CATEGORY"
        })
        self.assertEqual(sku["extensions"]["p1_sku_ref"], {
            "value": 1001, "source_label": "SYNTHETIC_P1_SKU"
        })
        self.assertEqual(sku["extensions"]["p1_spec_text"], {
            "value": "regular", "source_label": "SYNTHETIC_P1_SKU"
        })
        self.assertEqual(sku["extensions"]["p1_availability_status"], {
            "value": 1, "source_label": "SYNTHETIC_P1_SKU"
        })
        self.assertEqual(sku["prices"]["p1_original_price"], {
            "value": 15.0, "source_label": "SYNTHETIC_P1_SKU"
        })
        self.assertEqual(sku["prices"]["p1_activity_price"], {
            "value": 12.5, "source_label": "SYNTHETIC_P1_SKU"
        })
        self.assertEqual(sku["extensions"]["p1_promotion_type"], {
            "value": "DIRECT_REDUCTION", "source_label": "SYNTHETIC_P1_PROMOTION"
        })
        self.assertEqual(sku["prices"]["p1_promotion_discount"], {
            "value": 2.5, "source_label": "SYNTHETIC_P1_PROMOTION"
        })
        self.assertEqual(sku["extensions"]["p1_promotion_scope"], {
            "value": "SKU", "source_label": "SYNTHETIC_P1_PROMOTION"
        })
        self.assertEqual(merchant["prices"]["p1_delivery_fee"], {
            "value": 3.0, "source_label": "SYNTHETIC_P1_DELIVERY"
        })
        self.assertEqual(merchant["prices"]["p1_delivery_min_order"], {
            "value": 20.0, "source_label": "SYNTHETIC_P1_DELIVERY"
        })
        self.assertEqual(merchant["extensions"]["p1_delivery_status"], {
            "value": "AVAILABLE", "source_label": "SYNTHETIC_P1_DELIVERY"
        })

    def test_optional_p1_paths_stay_explicitly_missing_with_their_labels(self) -> None:
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
        parsed = _parsed(_replace_event(fixture, 0, food_payload))

        merchant = parsed["merchant"]
        sku = parsed["productlist_events"][0]["category_pages"][0]["products"][0]["skus"][0]
        self.assertEqual(sku["prices"]["p1_original_price"], {
            "value": None, "source_label": "SYNTHETIC_P1_SKU"
        })
        self.assertEqual(sku["extensions"]["p1_promotion_type"], {
            "value": None, "source_label": "SYNTHETIC_P1_PROMOTION"
        })
        self.assertEqual(merchant["prices"]["p1_delivery_fee"], {
            "value": None, "source_label": "SYNTHETIC_P1_DELIVERY"
        })
        self.assertEqual(merchant["extensions"]["p1_delivery_status"], {
            "value": None, "source_label": "SYNTHETIC_P1_DELIVERY"
        })

    def test_type_error_multi_sku_categories_and_cross_observation_fail_closed(self) -> None:
        fixture = p1_success_fixture(_config())
        product_payload = copy.deepcopy(fixture.events[1].payload)
        product_payload["data"]["food_spu_tags"][0]["dynamic_spus"][0]["skus"][0]["origin_price"] = "invalid"  # type: ignore[index]
        with self.assertRaisesRegex(ParserError, "^TYPE_MISMATCH$"):
            _parsed(_replace_event(fixture, 1, product_payload))

        multi_payload = copy.deepcopy(fixture.events[1].payload)
        first_category = multi_payload["data"]["food_spu_tags"][0]  # type: ignore[index]
        second_sku = copy.deepcopy(first_category["dynamic_spus"][0]["skus"][0])
        second_sku["id"] = 1002
        second_sku["spec"] = "large"
        first_category["dynamic_spus"][0]["skus"].append(second_sku)
        second_category = copy.deepcopy(first_category)
        second_category["tag"] = "category-demo-02"
        second_category["name"] = "Demo Category Two"
        second_category["current_page"] = 2
        second_category["has_next_page"] = False
        second_category["dynamic_spus"] = []
        multi_payload["data"]["food_spu_tags"].append(second_category)  # type: ignore[index]
        parsed = _parsed(_replace_event(fixture, 1, multi_payload))
        pages = parsed["productlist_events"][0]["category_pages"]
        self.assertEqual(len(pages), 2)
        self.assertEqual(len(pages[0]["products"][0]["skus"]), 2)

        with self.assertRaisesRegex(AdapterError, "^ADAPTER_OBSERVATION_SCOPE_MISMATCH$"):
            FakeAdapter({"target:offline_demo_01": p1_cross_observation_fixture(_config())}).collect(
                _target(), _config()
            )

    def test_p1_profile_rejects_any_unlabelled_observed_path(self) -> None:
        profile = synthetic_p1_productlist_config()
        invalid = replace(
            profile,
            observed_extensions=(replace(profile.observed_extensions[0], source_label=None),),
        )
        with self.assertRaisesRegex(ParserError, "^PARSER_P1_SOURCE_LABEL_UNRESOLVED$"):
            invalid.validate()
