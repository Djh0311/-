from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from parser_candidate import (
    Binding,
    ParserConfig,
    ParserError,
    ParserRegistry,
    SanitizedObservationInput,
    parse_productlist,
    parse_registered,
    parse_sanitized,
)


def config(**changes: object) -> ParserConfig:
    values: dict[str, object] = {
        "payload_family": "synthetic_productlist",
        "payload_version": "v1",
        "category_id": Binding(
            "category_id",
            "$.data.food_spu_tags[*].tag",
            ("string",),
            "category",
        ),
        "product_price": Binding(
            "product_price",
            "$.data.food_spu_tags[*].dynamic_spus[*].min_price",
            ("number",),
            "product",
        ),
        "sku_price": Binding(
            "sku_price",
            "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].price",
            ("number",),
            "sku",
        ),
    }
    values.update(changes)
    return ParserConfig(**values)  # type: ignore[arg-type]


def payload() -> dict[str, object]:
    return {
        "data": {
            "food_spu_tags": [
                {
                    "tag": "category-alpha",
                    "current_page": 1,
                    "has_next_page": True,
                    "dynamic_spus": [
                        {
                            "id": 11,
                            "name": "product-alpha",
                            "min_price": 12.5,
                            "skus": [
                                {"id": 111, "spec": "spec-alpha", "price": 12.5, "status": 1}
                            ],
                        }
                    ],
                },
                {
                    "tag": "category-beta",
                    "current_page": 2,
                    "has_next_page": False,
                    "dynamic_spus": [],
                },
            ]
        }
    }


class ParserCandidateTests(unittest.TestCase):
    def test_parses_nested_pages_without_collapsing_categories(self) -> None:
        result = parse_productlist(payload(), config())
        self.assertEqual([row["category_id"] for row in result["category_pages"]], ["category-alpha", "category-beta"])
        self.assertEqual([row["current_page"] for row in result["category_pages"]], [1, 2])
        self.assertEqual(result["category_pages"][0]["products"][0]["skus"][0]["price"], 12.5)

    def test_unconfigured_semantic_bindings_fail_closed(self) -> None:
        for changes, expected in (
            ({"category_id": None}, "CATEGORY_ID_MAPPING_UNRESOLVED"),
            ({"product_price": None}, "PRICE_MAPPING_UNRESOLVED"),
            ({"sku_price": None}, "PRICE_MAPPING_UNRESOLVED"),
            ({"payload_version": ""}, "PARSER_VERSION_UNRESOLVED"),
        ):
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ParserError, f"^{expected}$"):
                    parse_productlist(payload(), config(**changes))

    def test_selected_type_mismatch_is_rejected(self) -> None:
        bad = payload()
        bad["data"]["food_spu_tags"][0]["tag"] = 9  # type: ignore[index]
        with self.assertRaisesRegex(ParserError, "^TYPE_MISMATCH$"):
            parse_productlist(bad, config())

    def test_integer_prices_satisfy_number_binding(self) -> None:
        integer_payload = payload()
        integer_payload["data"]["food_spu_tags"][0]["dynamic_spus"][0]["min_price"] = 12  # type: ignore[index]
        integer_payload["data"]["food_spu_tags"][0]["dynamic_spus"][0]["skus"][0]["price"] = 12  # type: ignore[index]
        result = parse_productlist(integer_payload, config())
        product = result["category_pages"][0]["products"][0]
        self.assertEqual(product["price"], 12)
        self.assertEqual(product["skus"][0]["price"], 12)

    def test_multi_category_top_level_page_is_rejected(self) -> None:
        collapsed = payload()
        categories = collapsed["data"]["food_spu_tags"]  # type: ignore[index]
        for category in categories:
            category.pop("current_page", None)
            category.pop("has_next_page", None)
        collapsed["data"]["current_page"] = 1  # type: ignore[index]
        collapsed["data"]["has_next_page"] = False  # type: ignore[index]
        with self.assertRaisesRegex(ParserError, "^MULTI_CATEGORY_PAGE_COLLAPSE$"):
            parse_productlist(collapsed, config())

    def test_required_field_missing_is_rejected(self) -> None:
        bad = payload()
        del bad["data"]["food_spu_tags"][0]["has_next_page"]  # type: ignore[index]
        with self.assertRaisesRegex(ParserError, "^REQUIRED_FIELD_MISSING$"):
            parse_productlist(bad, config())

    def test_unknown_path_and_ambiguous_price_fail_closed(self) -> None:
        with self.assertRaisesRegex(ParserError, "^PARSER_CONFIG_INVALID$"):
            parse_productlist(
                payload(),
                config(
                    product_price=Binding(
                        "product_price",
                        "$.data.food_spu_tags[*].unknown_price",
                        ("number",),
                        "product",
                    )
                ),
            )
        bad_config = config(
            product_price=Binding(
                "product_price",
                "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].price",
                ("number",),
                "product",
            )
        )
        ambiguous_payload = payload()
        ambiguous_payload["data"]["food_spu_tags"][0]["dynamic_spus"][0]["skus"].append(  # type: ignore[index]
            {"id": 112, "spec": "spec-beta", "price": 13.5, "status": 1}
        )
        with self.assertRaisesRegex(ParserError, "^FIELD_AMBIGUOUS$"):
            parse_productlist(ambiguous_payload, bad_config)

    def test_explicit_extension_is_carried_only_when_bound(self) -> None:
        result = parse_productlist(
            payload(),
            config(
                extensions=(
                    Binding(
                        "category_label",
                        "$.data.food_spu_tags[*].tag",
                        ("string",),
                        "category",
                    ),
                )
            ),
        )
        self.assertEqual(
            result["category_pages"][0]["extensions"],
            {"category_label": "category-alpha"},
        )

    def test_optional_price_bindings_keep_values_and_source_labels(self) -> None:
        priced = payload()
        product = priced["data"]["food_spu_tags"][0]["dynamic_spus"][0]  # type: ignore[index]
        product["full_discount_price"] = 9.9  # type: ignore[index]
        product["skus"][0]["origin_price"] = 15.0  # type: ignore[index]
        result = parse_productlist(
            priced,
            config(
                price_bindings=(
                    Binding(
                        "product_min_price",
                        "$.data.food_spu_tags[*].dynamic_spus[*].min_price",
                        ("number",),
                        "product",
                        required=False,
                        source_label="H31_PRODUCTLIST_SPU",
                    ),
                    Binding(
                        "full_discount_price",
                        "$.data.food_spu_tags[*].dynamic_spus[*].full_discount_price",
                        ("number",),
                        "product",
                        required=False,
                        source_label="H31_PRODUCTLIST_SPU",
                    ),
                    Binding(
                        "origin_price",
                        "$.data.food_spu_tags[*].dynamic_spus[*].skus[*].origin_price",
                        ("number",),
                        "sku",
                        required=False,
                        source_label="H31_PRODUCTLIST_SKU",
                    ),
                )
            ),
        )
        product_row = result["category_pages"][0]["products"][0]
        self.assertEqual(
            product_row["prices"]["product_min_price"],
            {"value": 12.5, "source_label": "H31_PRODUCTLIST_SPU"},
        )
        self.assertEqual(
            product_row["prices"]["full_discount_price"],
            {"value": 9.9, "source_label": "H31_PRODUCTLIST_SPU"},
        )
        self.assertEqual(
            product_row["skus"][0]["prices"]["origin_price"],
            {"value": 15.0, "source_label": "H31_PRODUCTLIST_SKU"},
        )

        missing = payload()
        missing["data"]["food_spu_tags"][0]["dynamic_spus"][0].pop("full_discount_price", None)  # type: ignore[index]
        missing_result = parse_productlist(
            missing,
            config(
                price_bindings=(
                    Binding(
                        "full_discount_price",
                        "$.data.food_spu_tags[*].dynamic_spus[*].full_discount_price",
                        ("number",),
                        "product",
                        required=False,
                        source_label="H31_PRODUCTLIST_SPU",
                    ),
                )
            ),
        )
        self.assertEqual(
            missing_result["category_pages"][0]["products"][0]["prices"]["full_discount_price"],
            {"value": None, "source_label": "H31_PRODUCTLIST_SPU"},
        )

    def test_price_binding_requires_source_label(self) -> None:
        with self.assertRaisesRegex(ParserError, "^PRICE_SOURCE_LABEL_UNRESOLVED$"):
            parse_productlist(
                payload(),
                config(
                    price_bindings=(
                        Binding(
                            "optional_price",
                            "$.data.food_spu_tags[*].dynamic_spus[*].min_price",
                            ("number",),
                            "product",
                            required=False,
                        ),
                    )
                ),
            )

    def test_many_price_binding_preserves_all_values(self) -> None:
        priced = payload()
        priced["data"]["food_spu_tags"][0]["dynamic_spus"][0]["render_data"] = {  # type: ignore[index]
            "price_component": {"price": [{"value": 10.0}, {"value": 8.5}]}
        }
        result = parse_productlist(
            priced,
            config(
                price_bindings=(
                    Binding(
                        "display_prices",
                        "$.data.food_spu_tags[*].dynamic_spus[*].render_data.price_component.price[*].value",
                        ("number",),
                        "product",
                        required=False,
                        source_label="H31_PRODUCTLIST_PRICE_COMPONENT",
                        many=True,
                    ),
                )
            ),
        )
        self.assertEqual(
            result["category_pages"][0]["products"][0]["prices"]["display_prices"],
            {
                "value": [10.0, 8.5],
                "source_label": "H31_PRODUCTLIST_PRICE_COMPONENT",
            },
        )

    def test_error_output_does_not_echo_payload(self) -> None:
        marker = "synthetic-secret-marker"
        bad = {"data": {"food_spu_tags": [{"tag": marker}]}}
        with self.assertRaises(ParserError) as caught:
            parse_productlist(bad, config())
        self.assertNotIn(marker, str(caught.exception))

    def test_runtime_candidate_sources_have_no_io_imports(self) -> None:
        forbidden = {"os", "pathlib", "socket", "subprocess", "time", "urllib", "requests"}
        for name in (
            "__init__.py",
            "parser.py",
            "registry.py",
            "envelope.py",
            "capture_contract.py",
            "profiles.py",
        ):
            with self.subTest(name=name):
                source = Path(__file__).parents[1].joinpath(name).read_text(encoding="utf-8")
                tree = ast.parse(source)
                imports = {
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
                self.assertTrue(forbidden.isdisjoint(imports))
                self.assertTrue(forbidden.isdisjoint(imported_from))

    def test_registered_profile_is_required_for_entrypoint(self) -> None:
        registry = ParserRegistry((config(),)).validate()
        result = parse_registered(payload(), registry, "synthetic_productlist", "v1")
        self.assertEqual(result["payload_version"], "v1")
        with self.assertRaisesRegex(ParserError, "^PARSER_PROFILE_UNREGISTERED$"):
            parse_registered(payload(), registry, "synthetic_productlist", "v2")

    def test_registry_rejects_duplicate_profiles_and_invalid_profiles(self) -> None:
        with self.assertRaisesRegex(ParserError, "^PARSER_PROFILE_DUPLICATE$"):
            ParserRegistry((config(), config())).validate()
        invalid = config(category_id=None)
        with self.assertRaisesRegex(ParserError, "^CATEGORY_ID_MAPPING_UNRESOLVED$"):
            ParserRegistry((invalid,)).validate()

    def test_sanitized_input_is_copied_and_parsed_through_registered_profile(self) -> None:
        source = payload()
        observation = SanitizedObservationInput.from_mapping(
            "synthetic_productlist", "v1", source
        )
        source["data"]["food_spu_tags"].clear()  # type: ignore[index]
        result = parse_sanitized(observation, ParserRegistry((config(),)))
        self.assertEqual(len(result["category_pages"]), 2)

    def test_sanitized_input_rejects_sensitive_keys_recursively(self) -> None:
        for key in ("request", "response", "headers", "cookie", "access_token", "session_id"):
            with self.subTest(key=key):
                bad = {"data": {"nested": {key: "marker"}}}
                with self.assertRaisesRegex(ParserError, "^OBSERVATION_SENSITIVE_KEY$"):
                    SanitizedObservationInput.from_mapping("synthetic_productlist", "v1", bad)

    def test_sanitized_input_enforces_depth_and_node_budgets(self) -> None:
        deep: dict[str, object] = {}
        cursor = deep
        for _ in range(5):
            child: dict[str, object] = {}
            cursor["child"] = child
            cursor = child
        with self.assertRaisesRegex(ParserError, "^OBSERVATION_DEPTH_LIMIT$"):
            SanitizedObservationInput.from_mapping(
                "synthetic_productlist", "v1", deep, max_depth=3
            )
        with self.assertRaisesRegex(ParserError, "^OBSERVATION_NODE_LIMIT$"):
            SanitizedObservationInput.from_mapping(
                "synthetic_productlist", "v1", {"data": {"items": [1, 2, 3]}}, max_nodes=4
            )

    def test_sanitized_input_requires_exact_family_version_registration(self) -> None:
        observation = SanitizedObservationInput.from_mapping(
            "synthetic_productlist", "v1", payload()
        )
        with self.assertRaisesRegex(ParserError, "^PARSER_PROFILE_UNREGISTERED$"):
            parse_sanitized(observation, ParserRegistry((config(payload_version="v2"),)))
        with self.assertRaisesRegex(ParserError, "^PARSER_VERSION_UNRESOLVED$"):
            SanitizedObservationInput.from_mapping("synthetic_productlist", "", payload())
        with self.assertRaisesRegex(ParserError, "^OBSERVATION_INPUT_INVALID$"):
            parse_sanitized(payload(), ParserRegistry((config(),)))  # type: ignore[arg-type]

    def test_sanitized_input_errors_do_not_echo_input_values(self) -> None:
        marker = "sensitive-observation-marker"
        with self.assertRaises(ParserError) as caught:
            SanitizedObservationInput.from_mapping(
                "synthetic_productlist", "v1", {"headers": marker}
            )
        self.assertNotIn(marker, str(caught.exception))



if __name__ == "__main__":
    unittest.main()
