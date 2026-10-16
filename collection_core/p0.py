"""Build P0 same-observation business records from the pure Parser boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Iterable, Mapping

from parser_candidate import CaptureParserEvent, ParserError, ParserRegistry, parse_capture_read_scope


ROUTE_ID = "OWNED_STRUCTURED_EVENT"
PARSER_VERSION = "p0-core-v1"
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{8,96}$")
_REF_PREFIXES = frozenset(
    {
        "run",
        "batch",
        "source",
        "provider-contract",
        "authorization",
        "attempt",
        "envelope",
        "observation",
        "context",
        "evidence",
        "source-integrity",
        "coverage",
        "evidence-manifest",
        "scope",
    }
)
_SOURCE_KINDS = frozenset(
    {
        "SYNTHETIC_OFFLINE_FIXTURE",
        "USER_OWNED_EXPORT",
        "OFFICIAL_PUBLIC_DATASET",
        "APPROVED_PUBLIC_DOCUMENT",
        "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE",
    }
)


class P0Error(ValueError):
    """Closed-code P0 assembly failure that never includes source values."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class P0Context:
    """Opaque run references required to assemble one sealed P0 batch."""

    run_ref: str
    batch_ref: str
    source_ref: str
    source_kind: str
    provider_contract_ref: str
    authorization_ref: str
    attempt_ref: str
    envelope_ref: str
    observation_ref: str
    binding_context_ref: str
    evidence_ref: str
    source_integrity_ref: str
    coverage_ref: str
    coverage_scope_ref: str
    evidence_manifest_ref: str
    observed_at: str
    currency: str = "CNY"
    coverage_status: str = "PARTIAL"

    def validate(self) -> "P0Context":
        for name, value in self.__dict__.items():
            if name in {"source_kind", "observed_at", "currency", "coverage_status"}:
                continue
            _validate_ref(value)
        if self.source_kind not in _SOURCE_KINDS:
            raise P0Error("P0_SOURCE_KIND_INVALID")
        if self.currency != "CNY":
            raise P0Error("P0_CURRENCY_INVALID")
        if self.coverage_status not in {"COMPLETE", "PARTIAL", "UNKNOWN"}:
            raise P0Error("P0_COVERAGE_INVALID")
        _validate_time(self.observed_at)
        return self


def build_p0_batch(
    events: Iterable[CaptureParserEvent],
    registry: ParserRegistry,
    context: P0Context,
) -> dict[str, Any]:
    """Bind one Parser read scope into field observations and business records.

    The input remains an explicit in-memory event collection.  This function
    neither opens a source nor accepts cross-read, cross-time, or historical
    fallback values; those boundaries are enforced by the existing capture
    contract and repeated here in the emitted records.
    """

    if type(context) is not P0Context:
        raise P0Error("P0_CONTEXT_INVALID")
    context.validate()
    try:
        parsed = parse_capture_read_scope(events, registry)
    except ParserError as error:
        raise P0Error("P0_PARSE_FAILED") from error
    merchant = _mapping(parsed.get("merchant"), "P0_MERCHANT_INVALID")
    merchant_id = _text(merchant.get("id"), "P0_MERCHANT_INVALID")
    merchant_name = _text(merchant.get("name"), "P0_MERCHANT_INVALID")
    family = _text(parsed.get("payload_family"), "P0_PROFILE_INVALID")
    version = _text(parsed.get("payload_version"), "P0_PROFILE_INVALID")

    fields: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    ordinal = 0
    for event in parsed.get("productlist_events", []):
        for page in _list(event.get("category_pages"), "P0_PRODUCTLIST_INVALID"):
            page_model = _mapping(page, "P0_PRODUCTLIST_INVALID")
            for product in _list(page_model.get("products"), "P0_PRODUCTLIST_INVALID"):
                ordinal += 1
                product_model = _mapping(product, "P0_PRODUCTLIST_INVALID")
                product_id = _opaque_product_ref(product_model.get("id"))
                product_name = _text(product_model.get("name"), "P0_PRODUCT_INVALID")
                display_price_minor = _money_minor(product_model.get("price"))
                record_fields = _record_fields(
                    context,
                    family,
                    version,
                    ordinal,
                    merchant_id,
                    merchant_name,
                    product_id,
                    product_name,
                    display_price_minor,
                )
                fields.extend(record_fields)
                records.append(_business_record(context, ordinal, record_fields))
    if not records:
        raise P0Error("P0_NO_PRODUCT_RECORDS")

    batch = {
        "schema_version": "s2-02.observation-batch.v1",
        "batch_ref": context.batch_ref,
        "run_ref": context.run_ref,
        "source_ref": context.source_ref,
        "route_id": ROUTE_ID,
        "source_kind": context.source_kind,
        "provider_contract_ref": context.provider_contract_ref,
        "authorization_ref": context.authorization_ref,
        "attempt_ref": context.attempt_ref,
        "envelope_ref": context.envelope_ref,
        "observed_at": context.observed_at,
        "binding_context_ref": context.binding_context_ref,
        "coverage_status": context.coverage_status,
        "coverage_scope_ref": context.coverage_scope_ref,
        "payload_family": family,
        "payload_version": version,
        "parser_version": PARSER_VERSION,
        "record_contract_version": "s2-02.business-record.v2",
        "source_integrity_ref": context.source_integrity_ref,
        "privacy_decision": "PASS",
        "batch_state": "SEALED_PRIVACY_SAFE",
        "started_at": context.observed_at,
        "sealed_at": context.observed_at,
        "field_observation_refs": [field["field_observation_ref"] for field in fields],
        "business_record_refs": [record["business_record_ref"] for record in records],
        "coverage_ref": context.coverage_ref,
        "field_observation_count": len(fields),
        "business_record_count": len(records),
        "source_material_persisted": False,
        "privacy_safe_for_resume": True,
        "resume_mode": "SEALED_BATCH_ONLY",
    }
    result = {"observation_batch": batch, "field_observations": fields, "business_records": records}
    validate_p0_batch(result)
    return result


def validate_p0_batch(result: Mapping[str, Any]) -> None:
    """Validate the P0 invariants that JSON Schema alone cannot establish."""

    if type(result) is not dict or frozenset(result) != {
        "observation_batch", "field_observations", "business_records"
    }:
        raise P0Error("P0_RESULT_INVALID")
    batch = _mapping(result["observation_batch"], "P0_RESULT_INVALID")
    fields = _list(result["field_observations"], "P0_RESULT_INVALID")
    records = _list(result["business_records"], "P0_RESULT_INVALID")
    if batch.get("field_observation_count") != len(fields) or batch.get("business_record_count") != len(records):
        raise P0Error("P0_COUNT_MISMATCH")
    field_by_ref = {field.get("field_observation_ref"): field for field in fields if type(field) is dict}
    if len(field_by_ref) != len(fields):
        raise P0Error("P0_FIELD_REF_INVALID")
    shared = ("run_ref", "batch_ref", "observation_ref", "provider_contract_ref", "source_integrity_ref")
    for record in records:
        record_model = _mapping(record, "P0_RECORD_INVALID")
        if record_model.get("record_status") != "ACCEPTED" or record_model.get("route_id") != ROUTE_ID:
            raise P0Error("P0_RECORD_INVALID")
        bindings = _mapping(record_model.get("core_binding"), "P0_RECORD_INVALID")
        binding_refs = tuple(bindings.get(name) for name in (
            "store_field_ref", "product_field_ref", "price_field_ref", "currency_field_ref"
        ))
        if any(ref not in field_by_ref for ref in binding_refs):
            raise P0Error("P0_CORE_BINDING_INVALID")
        for field in record_model.get("field_observations", []):
            field_model = _mapping(field, "P0_RECORD_INVALID")
            if field_model.get("field_observation_ref") not in field_by_ref:
                raise P0Error("P0_RECORD_INVALID")
            if any(field_model.get(name) != record_model.get(name) for name in shared):
                raise P0Error("P0_CROSS_OBSERVATION_VALUE")
        if bindings.get("binding_context_ref") != record_model["field_observations"][0].get("binding_context_ref"):
            raise P0Error("P0_CORE_BINDING_INVALID")


def _record_fields(
    context: P0Context,
    family: str,
    version: str,
    ordinal: int,
    merchant_id: str,
    merchant_name: str,
    product_id: str,
    product_name: str,
    display_price_minor: int,
) -> list[dict[str, Any]]:
    values = (
        ("STORE", "store_ref", merchant_id, "OPAQUE_REF", merchant_id, "p0_store"),
        ("STORE", "store_name", merchant_name, "TEXT", merchant_name, "p0_store"),
        ("PRODUCT", "product_ref", product_id, "OPAQUE_REF", product_id, f"p0_product_{ordinal:04d}"),
        ("PRODUCT", "product_name", product_name, "TEXT", product_name, f"p0_product_{ordinal:04d}"),
        (
            "PRODUCT",
            "display_price_minor",
            display_price_minor,
            "MONEY_MINOR",
            _yuan_text(display_price_minor),
            f"p0_product_{ordinal:04d}",
        ),
        ("PRODUCT", "currency", context.currency, "ISO_CURRENCY", context.currency, f"p0_product_{ordinal:04d}"),
    )
    return [
        _field(context, family, version, ordinal, index, *value)
        for index, value in enumerate(values, start=1)
    ]


def _field(
    context: P0Context,
    family: str,
    version: str,
    ordinal: int,
    index: int,
    entity_kind: str,
    field_name: str,
    normalized_value: str | int,
    value_encoding: str,
    public_value_raw: str | None,
    entity_ref: str,
) -> dict[str, Any]:
    token = f"p0_{ordinal:04d}_{index:02d}"
    return {
        "schema_version": "s2-02.field-observation.v2",
        "field_observation_ref": f"field-observation:{token}",
        "run_ref": context.run_ref,
        "batch_ref": context.batch_ref,
        "observation_ref": context.observation_ref,
        "provider_contract_ref": context.provider_contract_ref,
        "route_id": ROUTE_ID,
        "source_kind": context.source_kind,
        "entity_kind": entity_kind,
        "source_local_entity_ref": f"source-local:{entity_ref}",
        "payload_family": family,
        "payload_version": version,
        "parser_version": PARSER_VERSION,
        "privacy_decision": "PASS",
        "value_safety_class": "PUBLIC_BUSINESS_VALUE_OR_OPAQUE_REF",
        "sensitive_material_persisted": False,
        "field_name": field_name,
        "observation_presence": "PRESENT",
        "public_value_raw": public_value_raw,
        "normalized_value": normalized_value,
        "value_encoding": value_encoding,
        "absence_reason": None,
        "confidence": "1",
        "observed_at": context.observed_at,
        "binding_context_ref": context.binding_context_ref,
        "anchor_ref": f"anchor:{token}",
        "evidence_ref": context.evidence_ref,
        "source_integrity_ref": context.source_integrity_ref,
        "directness": "DIRECT_SAME_OBSERVATION",
        "cross_source_fill": False,
        "cross_time_fill": False,
    }


def _business_record(context: P0Context, ordinal: int, fields: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {field["field_name"]: field["field_observation_ref"] for field in fields}
    return {
        "schema_version": "s2-02.business-record.v2",
        "record_kind": "BUSINESS_OBSERVATION",
        "business_record_ref": f"business-record:p0_{ordinal:04d}",
        "run_ref": context.run_ref,
        "batch_ref": context.batch_ref,
        "observation_ref": context.observation_ref,
        "provider_contract_ref": context.provider_contract_ref,
        "route_id": ROUTE_ID,
        "source_kind": context.source_kind,
        "observed_at": context.observed_at,
        "record_status": "ACCEPTED",
        "core_binding": {
            "binding_context_ref": context.binding_context_ref,
            "store_field_ref": by_name["store_ref"],
            "product_field_ref": by_name["product_ref"],
            "price_field_ref": by_name["display_price_minor"],
            "currency_field_ref": by_name["currency"],
            "binding_status": "SAME_OBSERVATION",
            "cross_source_fill": False,
            "cross_time_fill": False,
        },
        "field_observations": fields,
        "coverage_ref": context.coverage_ref,
        "source_integrity_ref": context.source_integrity_ref,
        "evidence_manifest_ref": context.evidence_manifest_ref,
    }


def _validate_ref(value: object) -> None:
    if type(value) is not str or ":" not in value:
        raise P0Error("P0_REFERENCE_INVALID")
    prefix, token = value.split(":", 1)
    if prefix not in _REF_PREFIXES or _TOKEN.fullmatch(token) is None:
        raise P0Error("P0_REFERENCE_INVALID")


def _validate_time(value: object) -> None:
    if type(value) is not str:
        raise P0Error("P0_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise P0Error("P0_TIME_INVALID") from error
    if parsed.tzinfo is None:
        raise P0Error("P0_TIME_INVALID")


def _mapping(value: object, code: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise P0Error(code)
    return value


def _list(value: object, code: str) -> list[Any]:
    if type(value) is not list:
        raise P0Error(code)
    return value


def _text(value: object, code: str) -> str:
    if type(value) is not str or not value or "\n" in value or "\r" in value:
        raise P0Error(code)
    return value


def _opaque_product_ref(value: object) -> str:
    if type(value) is int and value >= 0:
        return str(value)
    if type(value) is str and value and "\n" not in value and "\r" not in value:
        return value
    raise P0Error("P0_PRODUCT_INVALID")


def _money_minor(value: object) -> int:
    if type(value) not in {int, float} or type(value) is bool:
        raise P0Error("P0_DISPLAY_PRICE_INVALID")
    try:
        minor = Decimal(str(value)) * Decimal(100)
    except (InvalidOperation, ValueError) as error:
        raise P0Error("P0_DISPLAY_PRICE_INVALID") from error
    if not minor.is_finite() or minor != minor.to_integral_value() or minor < 0:
        raise P0Error("P0_DISPLAY_PRICE_INVALID")
    return int(minor)


def _yuan_text(minor: int) -> str:
    return f"{minor // 100}.{minor % 100:02d}"
