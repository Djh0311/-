from __future__ import annotations

import copy
import unittest

from parser_candidate import (
    Binding,
    CaptureParserEvent,
    EVENT_SCHEMA_VERSION,
    OFFLINE_READ_SCOPE_RUNNER_CONTRACT,
    ParserConfig,
    ParserError,
    ParserRegistry,
    parse_capture_event,
    parse_capture_read_scope,
    make_adapter_event,
    run_offline_read_scope,
)


def _config() -> ParserConfig:
    return ParserConfig(
        payload_family="synthetic_productlist",
        payload_version="v1",
        category_id=Binding(
            "category_id",
            "$.data.food_spu_tags[*].tag",
            ("string",),
            "category",
        ),
        product_price=Binding(
            "product_price",
            "$.data.food_spu_tags[*].dynamic_spus[*].min_price",
            ("number",),
            "product",
        ),
        sku_price=Binding(
            "sku_price",
            "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].price",
            ("number",),
            "sku",
        ),
    )


def _payload() -> dict[str, object]:
    return {
        "data": {
            "food_spu_tags": [
                {
                    "tag": "category-alpha",
                    "current_page": 1,
                    "has_next_page": False,
                    "dynamic_spus": [
                        {
                            "id": 11,
                            "name": "product-alpha",
                            "min_price": 12.5,
                            "skus": [
                                {"id": 111, "spec": "regular", "price": 12.5, "status": 1}
                            ],
                        }
                    ],
                }
            ]
        }
    }


def _food_config():
    from parser_candidate import Binding, FoodParserConfig

    return FoodParserConfig(
        payload_family="synthetic_productlist",
        payload_version="v1",
        merchant_id=Binding("merchant_id", "$.data.poi_info.poi_id_str", ("string",), "merchant"),
        merchant_name=Binding("merchant_name", "$.data.poi_info.name", ("string",), "merchant"),
        price_bindings=(
            Binding(
                "poi_min_price",
                "$.data.poi_info.min_price",
                ("number",),
                "merchant",
                required=False,
                source_label="H31_FOOD_POI_INFO",
            ),
        ),
    )


def _food_payload() -> dict[str, object]:
    return {
        "data": {
            "poi_info": {
                "poi_id_str": "merchant-alpha",
                "name": "store-alpha",
                "min_price": 20.0,
            }
        }
    }


class CaptureContractTests(unittest.TestCase):
    @staticmethod
    def _event_model(
        *,
        read_scope: str,
        observation_scope: str = "OBS_01",
        event_index: int,
        endpoint_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return {
            "schema_version": EVENT_SCHEMA_VERSION,
            "read_scope": read_scope,
            "observation_scope": observation_scope,
            "event_index": event_index,
            "endpoint_id": endpoint_id,
            "payload_family": "synthetic_productlist",
            "payload_version": "v1",
            "payload": payload,
        }

    def test_event_copies_one_observation_and_parses_registered_profile(self) -> None:
        source = _payload()
        event = CaptureParserEvent(
            read_scope="H34_READ_01",
            observation_scope="H34_OBS_01",
            event_index=1,
            endpoint_id="PRODUCTLIST",
            payload_family="synthetic_productlist",
            payload_version="v1",
            payload=source,
        )
        source["data"]["food_spu_tags"].clear()  # type: ignore[index]
        result = parse_capture_event(event, ParserRegistry((_config(),)))
        self.assertEqual(result["category_pages"][0]["products"][0]["price"], 12.5)
        self.assertEqual(event.to_observation_input().payload["data"]["food_spu_tags"], [  # type: ignore[index]
            {
                "tag": "category-alpha",
                "current_page": 1,
                "has_next_page": False,
                "dynamic_spus": [
                    {
                        "id": 11,
                        "name": "product-alpha",
                        "min_price": 12.5,
                        "skus": [
                            {"id": 111, "spec": "regular", "price": 12.5, "status": 1}
                        ],
                    }
                ],
            }
        ])

    def test_mapping_requires_exact_schema_and_never_merges_reads(self) -> None:
        payload = _payload()
        model = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "read_scope": "H34_READ_01",
            "observation_scope": "H34_OBS_01",
            "event_index": 1,
            "endpoint_id": "PRODUCTLIST",
            "payload_family": "synthetic_productlist",
            "payload_version": "v1",
            "payload": payload,
        }
        event = CaptureParserEvent.from_mapping(model)
        self.assertEqual(event.read_scope, "H34_READ_01")
        with self.assertRaisesRegex(ParserError, "^CAPTURE_EVENT_INVALID$"):
            CaptureParserEvent.from_mapping({**model, "merge": "H34_READ_02"})

    def test_invalid_scope_endpoint_and_sensitive_payload_fail_closed(self) -> None:
        base = {
            "read_scope": "H34_READ_01",
            "observation_scope": "H34_OBS_01",
            "event_index": 1,
            "endpoint_id": "PRODUCTLIST",
            "payload_family": "synthetic_productlist",
            "payload_version": "v1",
            "payload": _payload(),
        }
        for field, value, code in (
            ("read_scope", "H34 READ 01", "CAPTURE_EVENT_SCOPE_INVALID"),
            ("observation_scope", "H34 OBS 01", "CAPTURE_EVENT_OBSERVATION_SCOPE_INVALID"),
            ("endpoint_id", "OTHER", "CAPTURE_EVENT_ENDPOINT_INVALID"),
            ("event_index", True, "CAPTURE_EVENT_INDEX_INVALID"),
        ):
            with self.subTest(field=field):
                candidate = dict(base)
                candidate[field] = value
                with self.assertRaisesRegex(ParserError, f"^{code}$"):
                    CaptureParserEvent(**candidate)
        sensitive = copy.deepcopy(base["payload"])
        sensitive["data"]["session_id"] = "synthetic"  # type: ignore[index]
        with self.assertRaisesRegex(ParserError, "^OBSERVATION_SENSITIVE_KEY$"):
            CaptureParserEvent(**{**base, "payload": sensitive})

    def test_food_event_and_same_read_scope_binding(self) -> None:
        food = CaptureParserEvent(
            read_scope="READ_01",
            observation_scope="OBS_01",
            event_index=1,
            endpoint_id="FOOD",
            payload_family="synthetic_productlist",
            payload_version="v1",
            payload=_food_payload(),
        )
        product = CaptureParserEvent(
            read_scope="READ_01",
            observation_scope="OBS_01",
            event_index=2,
            endpoint_id="PRODUCTLIST",
            payload_family="synthetic_productlist",
            payload_version="v1",
            payload=_payload(),
        )
        registry = ParserRegistry((_config(),), (_food_config(),))
        food_result = parse_capture_event(food, registry)
        self.assertEqual(food_result["merchant"]["id"], "merchant-alpha")
        joined = parse_capture_read_scope((product, food), registry)
        self.assertEqual(joined["read_scope"], "READ_01")
        self.assertEqual(joined["observation_scope"], "OBS_01")
        self.assertEqual(joined["merchant"]["id"], "merchant-alpha")
        self.assertEqual(len(joined["productlist_events"]), 1)
        self.assertEqual(joined["productlist_events"][0]["category_pages"][0]["products"][0]["id"], 11)

    def test_read_scope_binding_rejects_cross_read_and_ambiguous_endpoint_set(self) -> None:
        food = CaptureParserEvent(
            read_scope="READ_01",
            observation_scope="OBS_01",
            event_index=1,
            endpoint_id="FOOD",
            payload_family="synthetic_productlist",
            payload_version="v1",
            payload=_food_payload(),
        )
        product = CaptureParserEvent(
            read_scope="READ_02",
            observation_scope="OBS_01",
            event_index=2,
            endpoint_id="PRODUCTLIST",
            payload_family="synthetic_productlist",
            payload_version="v1",
            payload=_payload(),
        )
        registry = ParserRegistry((_config(),), (_food_config(),))
        with self.assertRaisesRegex(ParserError, "^CAPTURE_READ_SCOPE_MISMATCH$"):
            parse_capture_read_scope((food, product), registry)
        product_two = CaptureParserEvent(
            read_scope="READ_02",
            observation_scope="OBS_01",
            event_index=3,
            endpoint_id="PRODUCTLIST",
            payload_family="synthetic_productlist",
            payload_version="v1",
            payload=_payload(),
        )
        with self.assertRaisesRegex(ParserError, "^CAPTURE_READ_ENDPOINT_SET_INVALID$"):
            parse_capture_read_scope((product, product_two), registry)

    def test_offline_runner_accepts_exact_synthetic_event_models(self) -> None:
        food_model = self._event_model(
            read_scope="READ_01",
            event_index=1,
            endpoint_id="FOOD",
            payload=_food_payload(),
        )
        product_model = self._event_model(
            read_scope="READ_01",
            event_index=2,
            endpoint_id="PRODUCTLIST",
            payload=_payload(),
        )
        result = run_offline_read_scope(
            (food_model, product_model),
            ParserRegistry((_config(),), (_food_config(),)),
        )
        food_model["payload"]["data"]["poi_info"]["name"] = "changed"  # type: ignore[index]
        self.assertEqual(result["contract_id"], OFFLINE_READ_SCOPE_RUNNER_CONTRACT)
        self.assertEqual(result["read_scope"], "READ_01")
        self.assertEqual(result["observations"][0]["merchant"]["name"], "store-alpha")
        self.assertEqual(len(result["observations"][0]["productlist_events"]), 1)

    def test_adapter_event_factory_requires_explicit_observation_scope(self) -> None:
        model = make_adapter_event(
            read_scope="READ_01",
            observation_scope="OBS_01",
            event_index=1,
            endpoint_id="FOOD",
            payload_family="synthetic_productlist",
            payload_version="v1",
            payload=_food_payload(),
        )
        self.assertEqual(frozenset(model), frozenset({
            "schema_version",
            "read_scope",
            "observation_scope",
            "event_index",
            "endpoint_id",
            "payload_family",
            "payload_version",
            "payload",
        }))
        self.assertEqual(
            model["observation_scope"],
            "OBS_01",
        )
        with self.assertRaisesRegex(ParserError, "^CAPTURE_EVENT_OBSERVATION_SCOPE_INVALID$"):
            make_adapter_event(
                read_scope="READ_01",
                observation_scope="OBS 01",
                event_index=1,
                endpoint_id="FOOD",
                payload_family="synthetic_productlist",
                payload_version="v1",
                payload=_food_payload(),
            )

    def test_offline_runner_rejects_non_sequence_and_cross_read_models(self) -> None:
        registry = ParserRegistry((_config(),), (_food_config(),))
        product_model = self._event_model(
            read_scope="READ_02",
            event_index=2,
            endpoint_id="PRODUCTLIST",
            payload=_payload(),
        )
        food_model = self._event_model(
            read_scope="READ_01",
            event_index=1,
            endpoint_id="FOOD",
            payload=_food_payload(),
        )
        with self.assertRaisesRegex(ParserError, "^CAPTURE_EVENT_INVALID$"):
            run_offline_read_scope(food_model, registry)
        with self.assertRaisesRegex(ParserError, "^CAPTURE_READ_SCOPE_MISMATCH$"):
            run_offline_read_scope((food_model, product_model), registry)

    def test_offline_runner_keeps_multiple_observations_in_one_read_separate(self) -> None:
        registry = ParserRegistry((_config(),), (_food_config(),))
        events = (
            self._event_model(
                read_scope="READ_03",
                observation_scope="OBS_01",
                event_index=1,
                endpoint_id="FOOD",
                payload=_food_payload(),
            ),
            self._event_model(
                read_scope="READ_03",
                observation_scope="OBS_01",
                event_index=2,
                endpoint_id="PRODUCTLIST",
                payload=_payload(),
            ),
            self._event_model(
                read_scope="READ_03",
                observation_scope="OBS_02",
                event_index=3,
                endpoint_id="FOOD",
                payload=_food_payload(),
            ),
            self._event_model(
                read_scope="READ_03",
                observation_scope="OBS_02",
                event_index=4,
                endpoint_id="PRODUCTLIST",
                payload=_payload(),
            ),
        )
        result = run_offline_read_scope(events, registry)
        self.assertEqual(
            [item["observation_scope"] for item in result["observations"]],
            ["OBS_01", "OBS_02"],
        )
        self.assertTrue(
            all(len(item["productlist_events"]) == 1 for item in result["observations"])
        )


if __name__ == "__main__":
    unittest.main()
