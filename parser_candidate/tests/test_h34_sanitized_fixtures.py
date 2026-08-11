from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import re
import unittest

from parser_candidate import (
    Binding,
    EVENT_SCHEMA_VERSION,
    ParserRegistry,
    ParserConfig,
    ParserError,
    SanitizedObservationInput,
    h31_food_config,
    h31_productlist_config,
    parse_sanitized,
    run_offline_read_scope,
)


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "h34"
SYNTHETIC_TEXT = re.compile(r"^synthetic_text_[0-9]{6}$")
URL = re.compile(r"(?:https?|ftp|file)://", re.IGNORECASE)
SENSITIVE_FRAGMENTS = (
    "request",
    "response",
    "header",
    "cookie",
    "token",
    "authorization",
    "credential",
    "password",
    "session",
    "openid",
    "unionid",
    "signature",
    "url",
    "uri",
    "host",
    "query",
    "method",
)

EXPECTED_PRICE_SOURCES = {
    "$.data.poi_info.min_price": "H31_FOOD_POI_INFO",
    "$.data.poi_info.poi_coupon.coupon_list[*].price": "H31_FOOD_POI_COUPON_LIST",
    "$.data.poi_info.poi_coupon.fold_coupon_list[*].coupon_subsidy_price": "H31_FOOD_FOLD_COUPON_LIST",
    "$.data.food_spu_tags[*].dynamic_spus[*].full_discount_price": "H31_PRODUCTLIST_SPU",
    "$.data.food_spu_tags[*].dynamic_spus[*].min_price": "H31_PRODUCTLIST_SPU",
    "$.data.food_spu_tags[*].dynamic_spus[*].preferential_feeling_price": "H31_PRODUCTLIST_SPU",
    "$.data.food_spu_tags[*].dynamic_spus[*].render_data.component_data.price_component.price[*].price": "H31_PRODUCTLIST_PRICE_COMPONENT",
    "$.data.food_spu_tags[*].dynamic_spus[*].render_data.component_data.price_component.price[*].underline_price": "H31_PRODUCTLIST_PRICE_COMPONENT",
    "$.data.food_spu_tags[*].dynamic_spus[*].render_info.price_info.coupons_per_price": "H31_PRODUCTLIST_RENDER_INFO_PRICE_INFO",
    "$.data.food_spu_tags[*].dynamic_spus[*].render_info.price_info.min_price": "H31_PRODUCTLIST_RENDER_INFO_PRICE_INFO",
    "$.data.food_spu_tags[*].dynamic_spus[*].render_info.price_info.multi_activity_price": "H31_PRODUCTLIST_RENDER_INFO_PRICE_INFO",
    "$.data.food_spu_tags[*].dynamic_spus[*].render_info.price_info.origin_price": "H31_PRODUCTLIST_RENDER_INFO_PRICE_INFO",
    "$.data.food_spu_tags[*].dynamic_spus[*].render_info.price_info.show_origin_price": "H31_PRODUCTLIST_RENDER_INFO_PRICE_INFO",
    "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].box_price": "H31_PRODUCTLIST_SKU",
    "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].full_discount_price": "H31_PRODUCTLIST_SKU",
    "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].member_price": "H31_PRODUCTLIST_SKU",
    "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].origin_price": "H31_PRODUCTLIST_SKU",
    "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].price": "H31_PRODUCTLIST_SKU",
    "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].sku_ladder_box_info.ladder_package_price": "H31_PRODUCTLIST_SKU",
    "$.data.render_context.min_price": "H31_PRODUCTLIST_RENDER_CONTEXT",
}
EXPECTED_MONETARY_SOURCES = {
    "$.data.poi_info.poi_coupon.coupon_list[*].coupon_origin_value": "H31_FOOD_POI_COUPON_LIST",
    "$.data.poi_info.poi_coupon.coupon_list[*].coupon_total_origin_value": "H31_FOOD_POI_COUPON_LIST",
    "$.data.poi_info.poi_coupon.coupon_list[*].coupon_total_value": "H31_FOOD_POI_COUPON_LIST",
    "$.data.poi_info.poi_coupon.coupon_list[*].coupon_value": "H31_FOOD_POI_COUPON_LIST",
    "$.data.poi_info.poi_coupon.fold_coupon_list[*].coupon_value": "H31_FOOD_FOLD_COUPON_LIST",
    "$.data.poi_info.shippingReduceFee": "H31_FOOD_POI_INFO",
    "$.data.poi_info.shipping_fee": "H31_FOOD_POI_INFO",
    "$.data.shopping_cart.min_fee_cart_tip": "H31_FOOD_SHOPPING_CART",
    "$.data.food_spu_tags[*].dynamic_spus[*].activity_policy.discount_by_count.discount": "H31_PRODUCTLIST_SPU",
    "$.data.food_spu_tags[*].dynamic_spus[*].max_discount": "H31_PRODUCTLIST_SPU",
    "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].activity_policy.discount_by_count.discount": "H31_PRODUCTLIST_SKU",
    "$.data.render_context.delivery_fee": "H31_PRODUCTLIST_RENDER_CONTEXT",
    "$.data.render_context.final_reduced_shipping_fee": "H31_PRODUCTLIST_RENDER_CONTEXT",
}


def h34_config() -> ParserConfig:
    return ParserConfig(
        payload_family="h34_synthetic_productlist",
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


class H34SanitizedFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
        cls.events: list[dict[str, object]] = []
        cls.event_paths: list[Path] = []
        for read in cls.manifest["read_scopes"]:
            for relative_path in read["fixture_files"]:
                path = FIXTURE_ROOT / relative_path
                cls.event_paths.append(path)
                cls.events.append(json.loads(path.read_text(encoding="utf-8")))

    def test_manifest_keeps_three_reads_separate(self) -> None:
        self.assertEqual(
            self.manifest["source_input_refs"],
            ["H34_LOCKED_INPUT_01", "H34_LOCKED_INPUT_02", "H34_LOCKED_INPUT_03"],
        )
        self.assertEqual(len(self.manifest["read_scopes"]), 3)
        self.assertEqual(sum(item["fixture_event_count"] for item in self.manifest["read_scopes"]), 8)
        self.assertEqual(
            self.manifest["isolation"],
            {
                "aggregate_fixture": "PROHIBITED",
                "cross_endpoint_join": "PROHIBITED",
                "cross_read_join": "PROHIBITED",
                "cross_time_join": "PROHIBITED",
                "historical_field_backfill": "PROHIBITED",
            },
        )
        self.assertTrue(all(not item["error_codes"] for item in self.manifest["read_scopes"]))
        for index, read in enumerate(self.manifest["read_scopes"], start=1):
            self.assertEqual(read["read_scope"], f"H34_READ_{index:02d}")
            self.assertTrue(all(path.startswith(f"read_{index:02d}/") for path in read["fixture_files"]))
        self.assertNotIn("aggregate_payload", self.manifest)

    def test_fixture_payloads_are_synthetic_and_value_safe(self) -> None:
        self.assertEqual(len(self.events), 8)
        self.assertFalse(self.manifest["raw_material_written"])
        self.assertFalse(self.manifest["raw_file_hash_written"])
        self.assertFalse(self.manifest["request_or_response_written"])
        self.assertFalse(self.manifest["url_written"])
        self.assertFalse(self.manifest["credential_or_session_written"])
        self.assertFalse(self.manifest["business_scalar_written"])
        for path, event in zip(self.event_paths, self.events):
            with self.subTest(path=path.as_posix()):
                self._assert_synthetic_value(event["payload"])
                serialized = path.read_text(encoding="utf-8")
                self.assertIsNone(URL.search(serialized))
                self.assertNotIn("all-meituan", serialized)
                self.assertNotIn("wechat-miniprogram-capture-live", serialized)
                self.assertNotIn("sha256", serialized.casefold())

    def test_all_price_and_monetary_source_labels_are_retained(self) -> None:
        catalog = {
            row["shape_path"]: row["source_label"]
            for row in self.manifest["price_source_catalog"]
        }
        monetary_catalog = {
            row["shape_path"]: row["source_label"]
            for row in self.manifest["unclassified_monetary_catalog"]
        }
        self.assertEqual(catalog, EXPECTED_PRICE_SOURCES)
        self.assertEqual(monetary_catalog, EXPECTED_MONETARY_SOURCES)
        observed_prices: dict[str, str] = {}
        observed_monetary: dict[str, str] = {}
        for event in self.events:
            endpoint_kind = event["endpoint_kind"]
            for relation in event["price_source_relations"]:
                observed_prices[relation["shape_path"]] = relation["source_label"]
                self._assert_endpoint_label(endpoint_kind, relation["source_label"])
            for relation in event["unclassified_monetary_relations"]:
                observed_monetary[relation["shape_path"]] = relation["source_label"]
                self._assert_endpoint_label(endpoint_kind, relation["source_label"])
        self.assertEqual(observed_prices, EXPECTED_PRICE_SOURCES)
        self.assertEqual(observed_monetary, EXPECTED_MONETARY_SOURCES)

    def test_read_scope_and_endpoint_join_are_never_merged(self) -> None:
        event_refs = set()
        for event in self.events:
            with self.subTest(event_ref=event["event_ref"]):
                self.assertNotIn(event["event_ref"], event_refs)
                event_refs.add(event["event_ref"])
                self.assertRegex(event["read_scope"], r"^H34_READ_0[123]$")
                self.assertEqual(event["cross_read_join"], "PROHIBITED")
                self.assertEqual(event["cross_time_join"], "PROHIBITED")
                self.assertEqual(event["cross_endpoint_join"], "PROHIBITED")
                self.assertEqual(event["historical_field_backfill"], "PROHIBITED")
                self.assertEqual(
                    event["missing_field_rule"],
                    "UNOBSERVED_IN_THIS_EVENT_NO_CROSS_READ_BACKFILL",
                )
        self.assertEqual(
            {event["read_scope"] for event in self.events},
            {"H34_READ_01", "H34_READ_02", "H34_READ_03"},
        )

    def test_productlist_fixtures_parse_with_a_synthetic_profile_only(self) -> None:
        registry = ParserRegistry((h34_config(),))
        product_events = [
            event for event in self.events if event["endpoint_kind"] == "PRODUCTLIST"
        ]
        self.assertEqual(len(product_events), 4)
        for event in product_events:
            with self.subTest(event_ref=event["event_ref"]):
                observation = SanitizedObservationInput.from_mapping(
                    "h34_synthetic_productlist",
                    "v1",
                    event["payload"],
                    max_nodes=100_000,
                )
                result = parse_sanitized(observation, registry)
                self.assertEqual(result["payload_family"], "h34_synthetic_productlist")
                self.assertEqual(result["payload_version"], "v1")
                self.assertTrue(result["category_pages"])
                for category in result["category_pages"]:
                    self.assertIsInstance(category["current_page"], int)
                    self.assertIsInstance(category["has_next_page"], bool)
        self.assertNotIn("meituan_wechat_miniprogram", str(registry.profiles))

    def test_offline_read_scope_runner_smoke_keeps_reads_and_prices_separate(self) -> None:
        registry = ParserRegistry(
            (h31_productlist_config(),),
            (h31_food_config(),),
        )
        for read_index in (1, 2):
            read = self.manifest["read_scopes"][read_index - 1]
            models = []
            for event_index, relative_path in enumerate(read["fixture_files"], start=1):
                event = json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))
                models.append(
                    {
                        "schema_version": EVENT_SCHEMA_VERSION,
                        "read_scope": event["read_scope"],
                        "observation_scope": f"{event['read_scope']}_OBS_01",
                        "event_index": event_index,
                        "endpoint_id": event["endpoint_kind"],
                        "payload_family": "meituan_wechat_miniprogram",
                        "payload_version": "h31-shape-v1",
                        "payload": event["payload"],
                    }
                )
            with self.subTest(read_scope=read["read_scope"]):
                result = run_offline_read_scope(
                    models,
                    registry,
                    max_nodes=100_000,
                )
                self.assertEqual(result["read_scope"], read["read_scope"])
                self.assertEqual(result["payload_family"], "meituan_wechat_miniprogram")
                self.assertEqual(len(result["observations"]), 1)
                self.assertEqual(
                    result["observations"][0]["merchant"]["prices"]["poi_min_price"]["source_label"],
                    "H31_FOOD_POI_INFO",
                )
                self.assertTrue(
                    result["observations"][0]["productlist_events"][0]["category_pages"]
                )

        read_three = self.manifest["read_scopes"][2]
        models = []
        for event_index, relative_path in enumerate(read_three["fixture_files"], start=1):
            event = json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))
            models.append(
                {
                    "schema_version": EVENT_SCHEMA_VERSION,
                    "read_scope": event["read_scope"],
                    "observation_scope": f"{event['read_scope']}_OBS_{(event_index + 1) // 2:02d}",
                    "event_index": event_index,
                    "endpoint_id": event["endpoint_kind"],
                    "payload_family": "meituan_wechat_miniprogram",
                    "payload_version": "h31-shape-v1",
                    "payload": event["payload"],
                }
            )
        result = run_offline_read_scope(models, registry, max_nodes=100_000)
        self.assertEqual(result["read_scope"], "H34_READ_03")
        self.assertEqual(
            [item["observation_scope"] for item in result["observations"]],
            ["H34_READ_03_OBS_01", "H34_READ_03_OBS_02"],
        )

    def test_missing_price_fails_without_cross_read_backfill(self) -> None:
        event = next(
            item for item in self.events if item["endpoint_kind"] == "PRODUCTLIST"
        )
        payload = deepcopy(event["payload"])
        target_product = None
        for category in payload["data"]["food_spu_tags"]:
            if category["dynamic_spus"]:
                target_product = category["dynamic_spus"][0]
                break
        self.assertIsNotNone(target_product)
        target_product.pop("min_price")
        observation = SanitizedObservationInput.from_mapping(
            "h34_synthetic_productlist",
            "v1",
            payload,
            max_nodes=100_000,
        )
        with self.assertRaisesRegex(ParserError, "^REQUIRED_FIELD_MISSING$"):
            parse_sanitized(observation, ParserRegistry((h34_config(),)))
        self.assertEqual(
            event["missing_field_rule"],
            "UNOBSERVED_IN_THIS_EVENT_NO_CROSS_READ_BACKFILL",
        )

    def test_runtime_candidate_modules_do_not_import_network_or_io(self) -> None:
        forbidden = {
            "os",
            "pathlib",
            "socket",
            "subprocess",
            "time",
            "urllib",
            "requests",
            "http",
            "httpx",
        }
        runtime_root = Path(__file__).parents[1]
        for name in ("__init__.py", "parser.py", "registry.py", "envelope.py"):
            with self.subTest(name=name):
                tree = ast.parse(runtime_root.joinpath(name).read_text(encoding="utf-8"))
                imported = {
                    alias.name.split(".", 1)[0]
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                }
                imported_from = {
                    node.module.split(".", 1)[0]
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module
                }
                self.assertTrue(forbidden.isdisjoint(imported))
                self.assertTrue(forbidden.isdisjoint(imported_from))

    def _assert_synthetic_value(self, value: object) -> None:
        if type(value) is dict:
            for key, child in value.items():
                normalized = re.sub(r"[^a-z0-9]+", "", key.casefold())
                self.assertFalse(
                    any(fragment in normalized for fragment in SENSITIVE_FRAGMENTS),
                    key,
                )
                self._assert_synthetic_value(child)
            return
        if type(value) is list:
            for child in value:
                self._assert_synthetic_value(child)
            return
        if type(value) is str:
            self.assertIsNotNone(SYNTHETIC_TEXT.fullmatch(value))
            return
        if type(value) is int:
            self.assertLessEqual(value, -1_000_001)
            return
        if type(value) is float:
            self.assertLessEqual(value, -1_000_001.5)
            return
        if type(value) is bool:
            self.assertFalse(value)
            return
        self.assertIsNone(value)

    def _assert_endpoint_label(self, endpoint_kind: object, source_label: object) -> None:
        if endpoint_kind == "FOOD":
            self.assertTrue(str(source_label).startswith("H31_FOOD_"))
        elif endpoint_kind == "PRODUCTLIST":
            self.assertTrue(str(source_label).startswith("H31_PRODUCTLIST_"))
        else:
            self.fail(f"unexpected endpoint kind: {endpoint_kind}")


if __name__ == "__main__":
    unittest.main()
