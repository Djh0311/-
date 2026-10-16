from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from collection_core.p1_contract import (
    P1_FIELD_SPECS,
    P1FieldContractError,
    P1FieldValue,
    validate_p1_field_set,
)


def _present(
    field_name: str,
    entity_kind: str,
    normalized_value: str | int,
    value_encoding: str,
) -> P1FieldValue:
    owner_kind, owner_ref = {
        "CATEGORY": ("PRODUCT", "source-local:p1_product_0001"),
        "SKU": ("PRODUCT", "source-local:p1_product_0001"),
        "PRODUCT": ("PRODUCT", "source-local:p1_product_0001"),
        "PROMOTION": ("SKU", "source-local:p1_sku_0001"),
        "DELIVERY": ("STORE", "source-local:p1_store_0001"),
    }[entity_kind]
    source_label = {
        "CATEGORY": "SYNTHETIC_P1_CATEGORY",
        "SKU": "SYNTHETIC_P1_SKU",
        "PRODUCT": "SYNTHETIC_P1_SKU",
        "PROMOTION": "SYNTHETIC_P1_PROMOTION",
        "DELIVERY": "SYNTHETIC_P1_DELIVERY",
    }[entity_kind]
    return P1FieldValue(
        field_name=field_name,
        entity_kind=entity_kind,
        source_local_entity_ref="source-local:p1_entity_0001",
        owner_entity_kind=owner_kind,
        owner_entity_ref=owner_ref,
        source_label=source_label,
        observation_ref="observation:OBS_STAGE03_01",
        observation_presence="PRESENT",
        normalized_value=normalized_value,
        value_encoding=value_encoding,
        absence_reason=None,
        anchor_ref="anchor:p1_field_0001",
    )


class P1FieldContractTests(unittest.TestCase):
    def test_p1_field_catalog_is_closed_and_accepts_each_declared_value_kind(self) -> None:
        fields = (
            _present("category_ref", "CATEGORY", "category:category_0001", "OPAQUE_REF"),
            _present("category_name", "CATEGORY", "Demo Category", "TEXT"),
            _present("sku_ref", "SKU", "sku:sku_0001", "OPAQUE_REF"),
            _present("spec_text", "SKU", "Standard", "TEXT"),
            _present("availability_status", "SKU", "AVAILABLE", "ENUM"),
            _present("original_price_minor", "SKU", 1500, "MONEY_MINOR"),
            _present("activity_price_minor", "SKU", 1250, "MONEY_MINOR"),
            _present("promotion_type", "PROMOTION", "DIRECT_REDUCTION", "ENUM"),
            _present("promotion_discount_minor", "PROMOTION", 250, "MONEY_MINOR"),
            _present("promotion_discount_bps", "PROMOTION", 8500, "INTEGER_LOWER_BOUND"),
            _present("promotion_scope", "PROMOTION", "SKU", "ENUM"),
            _present("delivery_fee_minor", "DELIVERY", 300, "MONEY_MINOR"),
            _present("delivery_min_order_minor", "DELIVERY", 2000, "MONEY_MINOR"),
            _present("delivery_status", "DELIVERY", "AVAILABLE", "ENUM"),
        )

        self.assertEqual(
            frozenset(P1_FIELD_SPECS),
            {
                "category_ref",
                "category_name",
                "sku_ref",
                "spec_text",
                "availability_status",
                "original_price_minor",
                "activity_price_minor",
                "promotion_type",
                "promotion_discount_minor",
                "promotion_discount_bps",
                "promotion_scope",
                "delivery_fee_minor",
                "delivery_min_order_minor",
                "delivery_status",
            },
        )
        self.assertEqual(validate_p1_field_set(fields), fields)

    def test_explicit_absence_has_no_default_value_or_anchor(self) -> None:
        absent = P1FieldValue(
            field_name="promotion_discount_minor",
            entity_kind="PROMOTION",
            source_local_entity_ref="source-local:p1_entity_0001",
            owner_entity_kind="SKU",
            owner_entity_ref="source-local:p1_sku_0001",
            source_label="SYNTHETIC_P1_PROMOTION",
            observation_ref="observation:OBS_STAGE03_01",
            observation_presence="NOT_SHOWN",
            normalized_value=None,
            value_encoding=None,
            absence_reason="NOT_SHOWN",
            anchor_ref=None,
        )

        self.assertEqual(validate_p1_field_set((absent,)), (absent,))
        with self.assertRaisesRegex(P1FieldContractError, "^P1_FIELD_ABSENCE_INVALID$"):
            validate_p1_field_set((replace(absent, normalized_value=0),))

    def test_rejects_imprecise_money_wrong_entity_and_unknown_enum(self) -> None:
        money = _present("original_price_minor", "SKU", 1500, "MONEY_MINOR")
        with self.assertRaisesRegex(P1FieldContractError, "^P1_FIELD_VALUE_INVALID$"):
            validate_p1_field_set((replace(money, normalized_value=12.5),))
        with self.assertRaisesRegex(P1FieldContractError, "^P1_FIELD_ENTITY_INVALID$"):
            validate_p1_field_set((replace(money, entity_kind="DELIVERY"),))

        status = _present("delivery_status", "DELIVERY", "AVAILABLE", "ENUM")
        with self.assertRaisesRegex(P1FieldContractError, "^P1_FIELD_VALUE_INVALID$"):
            validate_p1_field_set((replace(status, normalized_value="DEFAULT"),))

    def test_rejects_missing_source_anchor_and_cross_observation(self) -> None:
        field = _present("sku_ref", "SKU", "sku:sku_0001", "OPAQUE_REF")
        with self.assertRaisesRegex(P1FieldContractError, "^P1_FIELD_REFERENCE_INVALID$"):
            validate_p1_field_set((replace(field, source_local_entity_ref="sku_001"),))
        with self.assertRaisesRegex(P1FieldContractError, "^P1_FIELD_REFERENCE_INVALID$"):
            validate_p1_field_set((replace(field, anchor_ref=None),))
        with self.assertRaisesRegex(P1FieldContractError, "^P1_FIELD_CROSS_OBSERVATION$"):
            validate_p1_field_set(
                (field, replace(field, field_name="spec_text", normalized_value="Standard", value_encoding="TEXT",
                                observation_ref="observation:OBS_STAGE03_02"))
            )

    def test_schema_evolution_is_versioned_and_does_not_expand_p0_v2(self) -> None:
        schemas = Path(__file__).parents[2] / "contracts" / "schemas"
        p1_schema = json.loads(schemas.joinpath("p1-field-value-v1.schema.json").read_text(encoding="utf-8"))
        p0_schema = json.loads(schemas.joinpath("field-observation-v2.schema.json").read_text(encoding="utf-8"))

        self.assertEqual(set(p1_schema["properties"]["field_name"]["enum"]), set(P1_FIELD_SPECS))
        self.assertTrue({"owner_entity_kind", "owner_entity_ref"}.issubset(p1_schema["required"]))
        self.assertIn("source_label", p1_schema["required"])
        self.assertFalse(
            {"promotion_type", "promotion_discount_minor", "promotion_discount_bps", "promotion_scope", "delivery_min_order_minor", "delivery_status"}
            & set(p0_schema["properties"]["field_name"]["enum"])
        )
