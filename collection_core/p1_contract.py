"""Closed P1 field values for synthetic same-observation assembly."""

from __future__ import annotations

from dataclasses import dataclass
import re


_TOKEN = re.compile(r"^[A-Za-z0-9_-]{8,96}$")
_REFS = {
    "source_local_entity_ref": "source-local",
    "owner_entity_ref": "source-local",
    "observation_ref": "observation",
    "anchor_ref": "anchor",
}
_ABSENCE = frozenset(
    {
        "NOT_SHOWN",
        "NOT_OBSERVED",
        "NOT_APPLICABLE",
        "PARSE_FAILED",
        "SOURCE_FAILED",
        "REDACTED",
        "AMBIGUOUS",
    }
)


class P1FieldContractError(ValueError):
    """Closed-code P1 contract failure without a field value echo."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class P1FieldSpec:
    """The one allowed owner and value representation for a P1 field."""

    entity_owner_pairs: frozenset[tuple[str, str]]
    value_encoding: str
    source_label: str
    enum_values: frozenset[str] = frozenset()


P1_FIELD_SPECS: dict[str, P1FieldSpec] = {
    "category_ref": P1FieldSpec(frozenset({("CATEGORY", "PRODUCT")}), "OPAQUE_REF", "SYNTHETIC_P1_CATEGORY"),
    "category_name": P1FieldSpec(frozenset({("CATEGORY", "PRODUCT")}), "TEXT", "SYNTHETIC_P1_CATEGORY"),
    "sku_ref": P1FieldSpec(frozenset({("SKU", "PRODUCT")}), "OPAQUE_REF", "SYNTHETIC_P1_SKU"),
    "spec_text": P1FieldSpec(frozenset({("SKU", "PRODUCT")}), "TEXT", "SYNTHETIC_P1_SKU"),
    "availability_status": P1FieldSpec(
        frozenset({("SKU", "PRODUCT")}), "ENUM", "SYNTHETIC_P1_SKU", frozenset({"AVAILABLE", "UNAVAILABLE"})
    ),
    "original_price_minor": P1FieldSpec(
        frozenset({("PRODUCT", "PRODUCT"), ("SKU", "PRODUCT")}), "MONEY_MINOR", "SYNTHETIC_P1_SKU"
    ),
    "activity_price_minor": P1FieldSpec(
        frozenset({("PRODUCT", "PRODUCT"), ("SKU", "PRODUCT")}), "MONEY_MINOR", "SYNTHETIC_P1_SKU"
    ),
    "promotion_type": P1FieldSpec(
        frozenset({("PROMOTION", "STORE"), ("PROMOTION", "PRODUCT"), ("PROMOTION", "SKU")}),
        "ENUM",
        "SYNTHETIC_P1_PROMOTION",
        frozenset({"DIRECT_REDUCTION", "PERCENT_DISCOUNT", "STORE_COUPON", "SKU_COUPON"}),
    ),
    "promotion_discount_minor": P1FieldSpec(
        frozenset({("PROMOTION", "STORE"), ("PROMOTION", "PRODUCT"), ("PROMOTION", "SKU")}),
        "MONEY_MINOR",
        "SYNTHETIC_P1_PROMOTION",
    ),
    "promotion_discount_bps": P1FieldSpec(
        frozenset({("PROMOTION", "STORE"), ("PROMOTION", "PRODUCT"), ("PROMOTION", "SKU")}),
        "INTEGER_LOWER_BOUND",
        "SYNTHETIC_P1_PROMOTION",
    ),
    "promotion_scope": P1FieldSpec(
        frozenset({("PROMOTION", "STORE"), ("PROMOTION", "PRODUCT"), ("PROMOTION", "SKU")}),
        "ENUM",
        "SYNTHETIC_P1_PROMOTION",
        frozenset({"STORE", "PRODUCT", "SKU"}),
    ),
    "delivery_fee_minor": P1FieldSpec(frozenset({("DELIVERY", "STORE")}), "MONEY_MINOR", "SYNTHETIC_P1_DELIVERY"),
    "delivery_min_order_minor": P1FieldSpec(frozenset({("DELIVERY", "STORE")}), "MONEY_MINOR", "SYNTHETIC_P1_DELIVERY"),
    "delivery_status": P1FieldSpec(
        frozenset({("DELIVERY", "STORE")}), "ENUM", "SYNTHETIC_P1_DELIVERY", frozenset({"AVAILABLE", "UNAVAILABLE"})
    ),
}


@dataclass(frozen=True)
class P1FieldValue:
    """A value or explicit absence for one P1 field in one observation."""

    field_name: str
    entity_kind: str
    source_local_entity_ref: str
    owner_entity_kind: str
    owner_entity_ref: str
    source_label: str
    observation_ref: str
    observation_presence: str
    normalized_value: str | int | None
    value_encoding: str | None
    absence_reason: str | None
    anchor_ref: str | None

    def validate(self) -> "P1FieldValue":
        spec = P1_FIELD_SPECS.get(self.field_name)
        if spec is None:
            raise P1FieldContractError("P1_FIELD_NAME_INVALID")
        if (self.entity_kind, self.owner_entity_kind) not in spec.entity_owner_pairs:
            raise P1FieldContractError("P1_FIELD_ENTITY_INVALID")
        _validate_ref("source_local_entity_ref", self.source_local_entity_ref)
        _validate_ref("owner_entity_ref", self.owner_entity_ref)
        if self.source_label != spec.source_label:
            raise P1FieldContractError("P1_FIELD_SOURCE_INVALID")
        _validate_ref("observation_ref", self.observation_ref)
        if self.observation_presence == "PRESENT":
            self._validate_present(spec)
        elif self.observation_presence in _ABSENCE:
            self._validate_absent()
        else:
            raise P1FieldContractError("P1_FIELD_PRESENCE_INVALID")
        return self

    def _validate_present(self, spec: P1FieldSpec) -> None:
        if self.absence_reason is not None or self.value_encoding != spec.value_encoding:
            raise P1FieldContractError("P1_FIELD_VALUE_INVALID")
        _validate_ref("anchor_ref", self.anchor_ref)
        value = self.normalized_value
        if spec.value_encoding == "MONEY_MINOR":
            if type(value) is not int or value < 0:
                raise P1FieldContractError("P1_FIELD_VALUE_INVALID")
        elif spec.value_encoding == "TEXT":
            _validate_text(value)
        elif spec.value_encoding == "OPAQUE_REF":
            if type(value) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,31}:[A-Za-z0-9_-]{8,96}", value) is None:
                raise P1FieldContractError("P1_FIELD_VALUE_INVALID")
        elif spec.value_encoding == "ENUM":
            if type(value) is not str or value not in spec.enum_values:
                raise P1FieldContractError("P1_FIELD_VALUE_INVALID")
        elif spec.value_encoding == "INTEGER_LOWER_BOUND":
            if type(value) is not int or value < 0:
                raise P1FieldContractError("P1_FIELD_VALUE_INVALID")
        else:
            raise P1FieldContractError("P1_FIELD_VALUE_INVALID")

    def _validate_absent(self) -> None:
        if (
            self.normalized_value is not None
            or self.value_encoding is not None
            or self.absence_reason != self.observation_presence
            or self.anchor_ref is not None
        ):
            raise P1FieldContractError("P1_FIELD_ABSENCE_INVALID")


def validate_p1_field_set(fields: object) -> tuple[P1FieldValue, ...]:
    """Validate one immutable, same-observation P1 field collection."""

    if type(fields) is not tuple or not fields:
        raise P1FieldContractError("P1_FIELD_SET_INVALID")
    observation_ref: str | None = None
    seen: set[tuple[str, str]] = set()
    for field in fields:
        if type(field) is not P1FieldValue:
            raise P1FieldContractError("P1_FIELD_SET_INVALID")
        field.validate()
        if observation_ref is None:
            observation_ref = field.observation_ref
        elif field.observation_ref != observation_ref:
            raise P1FieldContractError("P1_FIELD_CROSS_OBSERVATION")
        key = (field.field_name, field.source_local_entity_ref)
        if key in seen:
            raise P1FieldContractError("P1_FIELD_DUPLICATE")
        seen.add(key)
    return fields


def _validate_ref(name: str, value: object) -> None:
    prefix = _REFS[name]
    if type(value) is not str or ":" not in value:
        raise P1FieldContractError("P1_FIELD_REFERENCE_INVALID")
    actual_prefix, token = value.split(":", 1)
    if actual_prefix != prefix or _TOKEN.fullmatch(token) is None:
        raise P1FieldContractError("P1_FIELD_REFERENCE_INVALID")


def _validate_text(value: object) -> None:
    if type(value) is not str or not value or len(value) > 1024 or "\n" in value or "\r" in value:
        raise P1FieldContractError("P1_FIELD_VALUE_INVALID")
