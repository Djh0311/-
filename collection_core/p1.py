"""Same-observation P1 assembly over the frozen P0 core result."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from parser_candidate import CaptureParserEvent, ParserError, ParserRegistry, parse_capture_read_scope

from .p0 import P0Context, P0Error, build_p0_batch, validate_p0_batch
from .p1_contract import P1_FIELD_SPECS, P1FieldContractError, P1FieldValue, validate_p1_field_set


_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "p1_record_ref",
        "p0_business_record_ref",
        "run_ref",
        "batch_ref",
        "observation_ref",
        "provider_contract_ref",
        "source_integrity_ref",
        "observed_at",
        "store_entity_ref",
        "product_entity_ref",
        "sku_entity_ref",
        "category_entity_ref",
        "promotion_entity_ref",
        "delivery_entity_ref",
        "p1_fields",
    }
)
_FIELD_KEYS = frozenset(P1FieldValue.__dataclass_fields__)
_P1_FIELD_NAMES = frozenset(P1_FIELD_SPECS)


class P1AssemblyError(ValueError):
    """Closed-code P1 assembly failure without source values or paths."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_p1_batch(
    events: Iterable[CaptureParserEvent],
    registry: ParserRegistry,
    context: P0Context,
) -> dict[str, Any]:
    """Build P1 SKU records without changing the embedded P0 result."""

    if type(registry) is not ParserRegistry or type(context) is not P0Context:
        raise P1AssemblyError("P1_CONTEXT_INVALID")
    if isinstance(events, (str, bytes, Mapping)):
        raise P1AssemblyError("P1_PARSE_FAILED")
    try:
        event_list = tuple(events)
    except TypeError:
        raise P1AssemblyError("P1_PARSE_FAILED") from None
    if not event_list or any(type(event) is not CaptureParserEvent for event in event_list):
        raise P1AssemblyError("P1_PARSE_FAILED")
    try:
        p0_result = build_p0_batch(event_list, registry, context)
        parsed = parse_capture_read_scope(event_list, registry)
    except (P0Error, ParserError):
        raise P1AssemblyError("P1_PARSE_FAILED") from None
    if (
        parsed.get("payload_family") != "synthetic_p1_productlist"
        or parsed.get("payload_version") != "v1"
    ):
        raise P1AssemblyError("P1_PROFILE_INVALID")
    try:
        records = _assemble_records(parsed, p0_result)
    except (KeyError, IndexError, TypeError, P1AssemblyError, P1FieldContractError):
        raise P1AssemblyError("P1_ASSEMBLY_INVALID") from None
    result = {
        "schema_version": "collection-p1-batch/v1",
        "p0_result": p0_result,
        "p1_records": records,
    }
    validate_p1_batch(result)
    return result


def validate_p1_batch(result: Mapping[str, Any]) -> None:
    """Validate P0 preservation plus every P1 entity and observation binding."""

    if type(result) is not dict or frozenset(result) != {"schema_version", "p0_result", "p1_records"}:
        raise P1AssemblyError("P1_RESULT_INVALID")
    if result.get("schema_version") != "collection-p1-batch/v1":
        raise P1AssemblyError("P1_RESULT_INVALID")
    p0_result = result.get("p0_result")
    try:
        validate_p0_batch(p0_result)
    except P0Error:
        raise P1AssemblyError("P1_P0_INVALID") from None
    p0_records = _list(p0_result["business_records"], "P1_RESULT_INVALID")
    p0_by_ref = {record.get("business_record_ref"): record for record in p0_records if type(record) is dict}
    if len(p0_by_ref) != len(p0_records):
        raise P1AssemblyError("P1_P0_INVALID")
    p1_records = _list(result.get("p1_records"), "P1_RESULT_INVALID")
    if not p1_records:
        raise P1AssemblyError("P1_RESULT_INVALID")
    seen_p1_refs: set[str] = set()
    for record in p1_records:
        _validate_p1_record(record, p0_by_ref, seen_p1_refs)


def _assemble_records(parsed: Mapping[str, Any], p0_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    merchant = _mapping(parsed.get("merchant"), "P1_ASSEMBLY_INVALID")
    store_ref = "source-local:p1_store_0001"
    delivery_ref = "source-local:p1_delivery_0001"
    _required_labeled(merchant, "p1_delivery_status", "SYNTHETIC_P1_DELIVERY", optional=True)
    _required_labeled(merchant, "p1_delivery_fee", "SYNTHETIC_P1_DELIVERY", optional=True, prices=True)
    _required_labeled(merchant, "p1_delivery_min_order", "SYNTHETIC_P1_DELIVERY", optional=True, prices=True)
    p0_records = _list(p0_result.get("business_records"), "P1_ASSEMBLY_INVALID")
    p0_index = 0
    records: list[dict[str, Any]] = []
    record_number = 0
    categories = _list(_list(parsed.get("productlist_events"), "P1_ASSEMBLY_INVALID")[0].get("category_pages"), "P1_ASSEMBLY_INVALID")
    for category_number, category in enumerate(categories, start=1):
        category_model = _mapping(category, "P1_ASSEMBLY_INVALID")
        category_name = _required_labeled(category_model, "p1_category_name", "SYNTHETIC_P1_CATEGORY")
        _required_labeled(category_model, "p1_category_ref", "SYNTHETIC_P1_CATEGORY")
        category_ref = f"source-local:p1_category_{category_number:04d}"
        for product_number, product in enumerate(_list(category_model.get("products"), "P1_ASSEMBLY_INVALID"), start=1):
            product_model = _mapping(product, "P1_ASSEMBLY_INVALID")
            if p0_index >= len(p0_records):
                raise P1AssemblyError("P1_P0_RECORD_MISMATCH")
            p0_record = _mapping(p0_records[p0_index], "P1_P0_RECORD_MISMATCH")
            p0_index += 1
            product_ref = f"source-local:p1_product_{category_number:04d}_{product_number:04d}"
            skus = _list(product_model.get("skus"), "P1_ASSEMBLY_INVALID")
            sku_models = skus or [None]
            for sku_number, sku in enumerate(sku_models, start=1):
                record_number += 1
                sku_ref = f"source-local:p1_sku_{category_number:04d}_{product_number:04d}_{sku_number:04d}"
                promotion_ref = f"source-local:p1_promotion_{category_number:04d}_{product_number:04d}_{sku_number:04d}"
                fields = _p1_fields(
                    category_name,
                    category_ref,
                    product_ref,
                    sku_ref,
                    promotion_ref,
                    store_ref,
                    delivery_ref,
                    sku,
                    merchant,
                    p0_record["observation_ref"],
                    record_number,
                )
                records.append(
                    {
                        "schema_version": "collection-p1-record/v1",
                        "p1_record_ref": f"p1-record:p1_{record_number:08d}",
                        "p0_business_record_ref": p0_record["business_record_ref"],
                        "run_ref": p0_record["run_ref"],
                        "batch_ref": p0_record["batch_ref"],
                        "observation_ref": p0_record["observation_ref"],
                        "provider_contract_ref": p0_record["provider_contract_ref"],
                        "source_integrity_ref": p0_record["source_integrity_ref"],
                        "observed_at": p0_record["observed_at"],
                        "store_entity_ref": store_ref,
                        "product_entity_ref": product_ref,
                        "sku_entity_ref": sku_ref,
                        "category_entity_ref": category_ref,
                        "promotion_entity_ref": promotion_ref,
                        "delivery_entity_ref": delivery_ref,
                        "p1_fields": [_field_mapping(field) for field in fields],
                    }
                )
    if p0_index != len(p0_records):
        raise P1AssemblyError("P1_P0_RECORD_MISMATCH")
    return records


def _p1_fields(
    category_name: object,
    category_ref: str,
    product_ref: str,
    sku_ref: str,
    promotion_ref: str,
    store_ref: str,
    delivery_ref: str,
    sku: object,
    merchant: Mapping[str, Any],
    observation_ref: str,
    record_number: int,
) -> tuple[P1FieldValue, ...]:
    fields: list[P1FieldValue] = []
    append = fields.append
    append(_present("category_ref", "CATEGORY", category_ref, "PRODUCT", product_ref, f"category:category_{record_number:08d}", observation_ref, record_number))
    append(_present("category_name", "CATEGORY", category_ref, "PRODUCT", product_ref, _text(category_name), observation_ref, record_number))
    if sku is None:
        append(_absent("sku_ref", "SKU", sku_ref, "PRODUCT", product_ref, "NOT_SHOWN", observation_ref))
        append(_absent("spec_text", "SKU", sku_ref, "PRODUCT", product_ref, "NOT_SHOWN", observation_ref))
        append(_absent("availability_status", "SKU", sku_ref, "PRODUCT", product_ref, "NOT_SHOWN", observation_ref))
        append(_absent("original_price_minor", "SKU", sku_ref, "PRODUCT", product_ref, "NOT_SHOWN", observation_ref))
        append(_absent("activity_price_minor", "SKU", sku_ref, "PRODUCT", product_ref, "NOT_SHOWN", observation_ref))
        append(_absent("promotion_type", "PROMOTION", promotion_ref, "SKU", sku_ref, "NOT_SHOWN", observation_ref))
        append(_absent("promotion_discount_minor", "PROMOTION", promotion_ref, "SKU", sku_ref, "NOT_SHOWN", observation_ref))
        append(_absent("promotion_discount_bps", "PROMOTION", promotion_ref, "SKU", sku_ref, "NOT_SHOWN", observation_ref))
        append(_absent("promotion_scope", "PROMOTION", promotion_ref, "SKU", sku_ref, "NOT_SHOWN", observation_ref))
    else:
        sku_model = _mapping(sku, "P1_ASSEMBLY_INVALID")
        sku_id = _required_labeled(sku_model, "p1_sku_ref", "SYNTHETIC_P1_SKU")
        append(_present("sku_ref", "SKU", sku_ref, "PRODUCT", product_ref, _opaque("sku", sku_id), observation_ref, record_number))
        append(_present("spec_text", "SKU", sku_ref, "PRODUCT", product_ref, _text(_required_labeled(sku_model, "p1_spec_text", "SYNTHETIC_P1_SKU")), observation_ref, record_number))
        availability = _required_labeled(sku_model, "p1_availability_status", "SYNTHETIC_P1_SKU")
        append(_present("availability_status", "SKU", sku_ref, "PRODUCT", product_ref, _availability(availability), observation_ref, record_number))
        append(_price_field("original_price_minor", sku_ref, product_ref, sku_model, "p1_original_price", "SYNTHETIC_P1_SKU", observation_ref, record_number))
        append(_price_field("activity_price_minor", sku_ref, product_ref, sku_model, "p1_activity_price", "SYNTHETIC_P1_SKU", observation_ref, record_number))
        fields.extend(_promotion_fields(sku_model, promotion_ref, sku_ref, observation_ref, record_number))
    fields.extend(_delivery_fields(merchant, delivery_ref, store_ref, observation_ref, record_number))
    try:
        return validate_p1_field_set(tuple(fields))
    except P1FieldContractError:
        raise P1AssemblyError("P1_FIELD_INVALID") from None


def _promotion_fields(sku: Mapping[str, Any], promotion_ref: str, sku_ref: str, observation_ref: str, record_number: int) -> tuple[P1FieldValue, ...]:
    promotion_type = _required_labeled(sku, "p1_promotion_type", "SYNTHETIC_P1_PROMOTION", optional=True)
    promotion_scope = _required_labeled(sku, "p1_promotion_scope", "SYNTHETIC_P1_PROMOTION", optional=True)
    discount = _required_labeled(sku, "p1_promotion_discount", "SYNTHETIC_P1_PROMOTION", optional=True, prices=True)
    bps = _required_labeled(sku, "p1_promotion_discount_bps", "SYNTHETIC_P1_PROMOTION", optional=True, prices=True)
    if promotion_type is None:
        if any(value is not None for value in (promotion_scope, discount, bps)):
            raise P1AssemblyError("P1_PROMOTION_INCOMPLETE")
        return (
            _absent("promotion_type", "PROMOTION", promotion_ref, "SKU", sku_ref, "NOT_SHOWN", observation_ref),
            _absent("promotion_discount_minor", "PROMOTION", promotion_ref, "SKU", sku_ref, "NOT_SHOWN", observation_ref),
            _absent("promotion_discount_bps", "PROMOTION", promotion_ref, "SKU", sku_ref, "NOT_SHOWN", observation_ref),
            _absent("promotion_scope", "PROMOTION", promotion_ref, "SKU", sku_ref, "NOT_SHOWN", observation_ref),
        )
    if promotion_scope is None:
        raise P1AssemblyError("P1_PROMOTION_INCOMPLETE")
    owner_kind = _text(promotion_scope)
    owner_ref = sku_ref
    if owner_kind != "SKU":
        raise P1AssemblyError("P1_OWNER_BINDING_INVALID")
    if _text(promotion_type) == "PERCENT_DISCOUNT":
        if bps is None or discount is not None:
            raise P1AssemblyError("P1_PROMOTION_INCOMPLETE")
        discount_field = _absent("promotion_discount_minor", "PROMOTION", promotion_ref, owner_kind, owner_ref, "NOT_APPLICABLE", observation_ref)
        bps_field = _present("promotion_discount_bps", "PROMOTION", promotion_ref, owner_kind, owner_ref, _integer(bps), observation_ref, record_number)
    else:
        if discount is None or bps is not None:
            raise P1AssemblyError("P1_PROMOTION_INCOMPLETE")
        discount_field = _present("promotion_discount_minor", "PROMOTION", promotion_ref, owner_kind, owner_ref, _minor(discount), observation_ref, record_number)
        bps_field = _absent("promotion_discount_bps", "PROMOTION", promotion_ref, owner_kind, owner_ref, "NOT_APPLICABLE", observation_ref)
    return (
        _present("promotion_type", "PROMOTION", promotion_ref, owner_kind, owner_ref, _text(promotion_type), observation_ref, record_number),
        discount_field,
        bps_field,
        _present("promotion_scope", "PROMOTION", promotion_ref, owner_kind, owner_ref, owner_kind, observation_ref, record_number),
    )


def _delivery_fields(merchant: Mapping[str, Any], delivery_ref: str, store_ref: str, observation_ref: str, record_number: int) -> tuple[P1FieldValue, ...]:
    fee = _required_labeled(merchant, "p1_delivery_fee", "SYNTHETIC_P1_DELIVERY", optional=True, prices=True)
    minimum = _required_labeled(merchant, "p1_delivery_min_order", "SYNTHETIC_P1_DELIVERY", optional=True, prices=True)
    status = _required_labeled(merchant, "p1_delivery_status", "SYNTHETIC_P1_DELIVERY", optional=True)
    return (
        _optional_money("delivery_fee_minor", delivery_ref, store_ref, fee, observation_ref, record_number),
        _optional_money("delivery_min_order_minor", delivery_ref, store_ref, minimum, observation_ref, record_number),
        _present("delivery_status", "DELIVERY", delivery_ref, "STORE", store_ref, _text(status), observation_ref, record_number)
        if status is not None
        else _absent("delivery_status", "DELIVERY", delivery_ref, "STORE", store_ref, "NOT_SHOWN", observation_ref),
    )


def _price_field(field_name: str, sku_ref: str, product_ref: str, sku: Mapping[str, Any], key: str, label: str, observation_ref: str, record_number: int) -> P1FieldValue:
    value = _required_labeled(sku, key, label, optional=True, prices=True)
    return _optional_money(field_name, sku_ref, product_ref, value, observation_ref, record_number, entity_kind="SKU")


def _optional_money(field_name: str, entity_ref: str, owner_ref: str, value: object, observation_ref: str, record_number: int, *, entity_kind: str = "DELIVERY") -> P1FieldValue:
    owner_kind = "PRODUCT" if entity_kind == "SKU" else "STORE"
    if value is None:
        return _absent(field_name, entity_kind, entity_ref, owner_kind, owner_ref, "NOT_SHOWN", observation_ref)
    return _present(field_name, entity_kind, entity_ref, owner_kind, owner_ref, _minor(value), observation_ref, record_number)


def _present(field_name: str, entity_kind: str, entity_ref: str, owner_kind: str, owner_ref: str, value: str | int, observation_ref: str, record_number: int) -> P1FieldValue:
    return P1FieldValue(
        field_name=field_name,
        entity_kind=entity_kind,
        source_local_entity_ref=entity_ref,
        owner_entity_kind=owner_kind,
        owner_entity_ref=owner_ref,
        source_label=P1_FIELD_SPECS[field_name].source_label,
        observation_ref=observation_ref,
        observation_presence="PRESENT",
        normalized_value=value,
        value_encoding=P1_FIELD_SPECS[field_name].value_encoding,
        absence_reason=None,
        anchor_ref=f"anchor:p1_{record_number:08d}_{field_name}",
    )


def _absent(field_name: str, entity_kind: str, entity_ref: str, owner_kind: str, owner_ref: str, reason: str, observation_ref: str) -> P1FieldValue:
    return P1FieldValue(
        field_name=field_name,
        entity_kind=entity_kind,
        source_local_entity_ref=entity_ref,
        owner_entity_kind=owner_kind,
        owner_entity_ref=owner_ref,
        source_label=P1_FIELD_SPECS[field_name].source_label,
        observation_ref=observation_ref,
        observation_presence=reason,
        normalized_value=None,
        value_encoding=None,
        absence_reason=reason,
        anchor_ref=None,
    )


def _required_labeled(row: Mapping[str, Any], key: str, label: str, *, optional: bool = False, prices: bool = False) -> object:
    container = _mapping(row.get("prices" if prices else "extensions"), "P1_ASSEMBLY_INVALID")
    value = _mapping(container.get(key), "P1_ASSEMBLY_INVALID")
    if frozenset(value) != {"value", "source_label"} or value.get("source_label") != label:
        raise P1AssemblyError("P1_FIELD_SOURCE_INVALID")
    selected = value.get("value")
    if selected is None and not optional:
        raise P1AssemblyError("P1_REQUIRED_FIELD_MISSING")
    return selected


def _validate_p1_record(record: object, p0_by_ref: Mapping[object, Mapping[str, Any]], seen_refs: set[str]) -> None:
    model = _mapping(record, "P1_RECORD_INVALID")
    if frozenset(model) != _RECORD_KEYS or model.get("schema_version") != "collection-p1-record/v1":
        raise P1AssemblyError("P1_RECORD_INVALID")
    p1_ref = _text(model.get("p1_record_ref"))
    if p1_ref in seen_refs:
        raise P1AssemblyError("P1_RECORD_INVALID")
    seen_refs.add(p1_ref)
    p0 = p0_by_ref.get(model.get("p0_business_record_ref"))
    if p0 is None:
        raise P1AssemblyError("P1_P0_RECORD_MISMATCH")
    for key in ("run_ref", "batch_ref", "observation_ref", "provider_contract_ref", "source_integrity_ref", "observed_at"):
        if model.get(key) != p0.get(key):
            raise P1AssemblyError("P1_CROSS_OBSERVATION_VALUE")
    for key in ("store_entity_ref", "product_entity_ref", "sku_entity_ref", "category_entity_ref", "promotion_entity_ref", "delivery_entity_ref"):
        if not _source_local_ref(model.get(key)):
            raise P1AssemblyError("P1_OWNER_BINDING_INVALID")
    fields = _list(model.get("p1_fields"), "P1_RECORD_INVALID")
    values = tuple(_field_from_mapping(field) for field in fields)
    try:
        validate_p1_field_set(values)
    except P1FieldContractError as error:
        if error.code == "P1_FIELD_CROSS_OBSERVATION":
            raise P1AssemblyError("P1_CROSS_OBSERVATION_VALUE") from None
        raise P1AssemblyError("P1_FIELD_INVALID") from None
    if {field.field_name for field in values} != _P1_FIELD_NAMES or len(values) != len(_P1_FIELD_NAMES):
        raise P1AssemblyError("P1_RECORD_INVALID")
    if any(field.observation_ref != model["observation_ref"] for field in values):
        raise P1AssemblyError("P1_CROSS_OBSERVATION_VALUE")
    _validate_owner_bindings(model, values)


def _validate_owner_bindings(record: Mapping[str, Any], fields: tuple[P1FieldValue, ...]) -> None:
    by_name = {field.field_name: field for field in fields}
    expected = {
        "category_ref": ("PRODUCT", record["product_entity_ref"], record["category_entity_ref"]),
        "category_name": ("PRODUCT", record["product_entity_ref"], record["category_entity_ref"]),
        "sku_ref": ("PRODUCT", record["product_entity_ref"], record["sku_entity_ref"]),
        "spec_text": ("PRODUCT", record["product_entity_ref"], record["sku_entity_ref"]),
        "availability_status": ("PRODUCT", record["product_entity_ref"], record["sku_entity_ref"]),
        "original_price_minor": ("PRODUCT", record["product_entity_ref"], record["sku_entity_ref"]),
        "activity_price_minor": ("PRODUCT", record["product_entity_ref"], record["sku_entity_ref"]),
        "delivery_fee_minor": ("STORE", record["store_entity_ref"], record["delivery_entity_ref"]),
        "delivery_min_order_minor": ("STORE", record["store_entity_ref"], record["delivery_entity_ref"]),
        "delivery_status": ("STORE", record["store_entity_ref"], record["delivery_entity_ref"]),
    }
    for name, (owner_kind, owner_ref, entity_ref) in expected.items():
        field = by_name[name]
        if field.owner_entity_kind != owner_kind or field.owner_entity_ref != owner_ref or field.source_local_entity_ref != entity_ref:
            raise P1AssemblyError("P1_OWNER_BINDING_INVALID")
    promotion = tuple(by_name[name] for name in ("promotion_type", "promotion_discount_minor", "promotion_discount_bps", "promotion_scope"))
    if any(field.source_local_entity_ref != record["promotion_entity_ref"] for field in promotion):
        raise P1AssemblyError("P1_OWNER_BINDING_INVALID")
    if len({(field.owner_entity_kind, field.owner_entity_ref) for field in promotion}) != 1:
        raise P1AssemblyError("P1_OWNER_BINDING_INVALID")
    scope = by_name["promotion_scope"]
    if scope.observation_presence == "PRESENT" and scope.normalized_value != scope.owner_entity_kind:
        raise P1AssemblyError("P1_OWNER_BINDING_INVALID")


def _field_mapping(field: P1FieldValue) -> dict[str, object]:
    return {name: getattr(field, name) for name in P1FieldValue.__dataclass_fields__}


def _field_from_mapping(value: object) -> P1FieldValue:
    model = _mapping(value, "P1_FIELD_INVALID")
    if frozenset(model) != _FIELD_KEYS:
        raise P1AssemblyError("P1_FIELD_INVALID")
    try:
        return P1FieldValue(**model)
    except TypeError:
        raise P1AssemblyError("P1_FIELD_INVALID") from None


def _minor(value: object) -> int:
    if type(value) not in {int, float} or type(value) is bool:
        raise P1AssemblyError("P1_MONEY_INVALID")
    try:
        minor = Decimal(str(value)) * Decimal(100)
    except (InvalidOperation, ValueError):
        raise P1AssemblyError("P1_MONEY_INVALID") from None
    if not minor.is_finite() or minor != minor.to_integral_value() or minor < 0:
        raise P1AssemblyError("P1_MONEY_INVALID")
    return int(minor)


def _integer(value: object) -> int:
    if type(value) is not int or value < 0:
        raise P1AssemblyError("P1_PROMOTION_INCOMPLETE")
    return value


def _availability(value: object) -> str:
    if value == 1:
        return "AVAILABLE"
    if value == 0:
        return "UNAVAILABLE"
    raise P1AssemblyError("P1_FIELD_INVALID")


def _opaque(prefix: str, value: object) -> str:
    if type(value) is not int or value < 0:
        raise P1AssemblyError("P1_FIELD_INVALID")
    return f"{prefix}:{prefix}_{value:08d}"


def _source_local_ref(value: object) -> bool:
    return type(value) is str and value.startswith("source-local:") and len(value) > len("source-local:") + 7


def _mapping(value: object, code: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise P1AssemblyError(code)
    return value


def _list(value: object, code: str) -> list[Any]:
    if type(value) is not list:
        raise P1AssemblyError(code)
    return value


def _text(value: object) -> str:
    if type(value) is not str or not value or "\n" in value or "\r" in value:
        raise P1AssemblyError("P1_FIELD_INVALID")
    return value
