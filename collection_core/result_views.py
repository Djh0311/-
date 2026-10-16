"""Stable, readable JSON and CSV views for a validated in-memory P0 result."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import json
from typing import Any, Mapping

from .p0 import P0Error, validate_p0_batch


_CSV_FIELDS = (
    "store",
    "product",
    "price_yuan",
    "currency",
    "run_ref",
    "batch_ref",
    "observation_ref",
    "business_record_ref",
)


class P0ResultViewError(ValueError):
    """Closed-code rendering failure that never includes a source value."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class P0ResultViews:
    """Canonical bytes ready for a later no-clobber publisher."""

    json_bytes: bytes
    csv_bytes: bytes


def render_p0_result(p0_result: Mapping[str, Any]) -> P0ResultViews:
    """Render JSON and CSV from one complete, validated P0 same-observation batch."""

    try:
        validate_p0_batch(p0_result)
        batch = _mapping(p0_result["observation_batch"])
        all_fields = _list(p0_result["field_observations"])
        records = _list(p0_result["business_records"])
        run_ref = _text(batch.get("run_ref"))
        batch_ref = _text(batch.get("batch_ref"))
        source_kind = _text(batch.get("source_kind"))
        observed_at = _text(batch.get("observed_at"))
        canonical_fields = _canonical_fields(all_fields)
        rows = tuple(
            _record_row(record, run_ref, batch_ref, source_kind, canonical_fields)
            for record in records
        )
    except (P0Error, KeyError, IndexError, TypeError, P0ResultViewError):
        raise P0ResultViewError("RESULT_VIEW_P0_INVALID") from None
    if not rows:
        raise P0ResultViewError("RESULT_VIEW_P0_INVALID")
    payload = {
        "schema_version": "collection-p0-result-view/v1",
        "run_ref": run_ref,
        "batch_ref": batch_ref,
        "source_kind": source_kind,
        "observed_at": observed_at,
        "record_count": len(rows),
        "records": list(rows),
    }
    json_bytes = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return P0ResultViews(json_bytes=json_bytes, csv_bytes=_csv_bytes(rows))


def _record_row(
    record: object,
    run_ref: str,
    batch_ref: str,
    source_kind: str,
    canonical_fields: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    model = _mapping(record)
    if (
        _text(model.get("run_ref")) != run_ref
        or _text(model.get("batch_ref")) != batch_ref
        or _text(model.get("source_kind")) != source_kind
    ):
        raise P0ResultViewError("RESULT_VIEW_P0_INVALID")
    observation_ref = _text(model.get("observation_ref"))
    business_record_ref = _text(model.get("business_record_ref"))
    field_list = _list(model.get("field_observations"))
    if any(
        type(field) is not dict
        or _text(field.get("field_observation_ref")) not in canonical_fields
        or canonical_fields[field["field_observation_ref"]] != field
        for field in field_list
    ):
        raise P0ResultViewError("RESULT_VIEW_P0_INVALID")
    fields = {
        field.get("field_name"): field
        for field in field_list
        if type(field) is dict
    }
    if len(fields) != len(field_list):
        raise P0ResultViewError("RESULT_VIEW_P0_INVALID")
    try:
        store = _text(fields["store_name"].get("public_value_raw"))
        product = _text(fields["product_name"].get("public_value_raw"))
        price_minor = fields["display_price_minor"].get("normalized_value")
        currency = _text(fields["currency"].get("normalized_value"))
    except (AttributeError, KeyError, P0ResultViewError):
        raise P0ResultViewError("RESULT_VIEW_P0_INVALID") from None
    if type(price_minor) is not int or price_minor < 0:
        raise P0ResultViewError("RESULT_VIEW_P0_INVALID")
    return {
        "store": store,
        "product": product,
        "price_yuan": f"{price_minor // 100}.{price_minor % 100:02d}",
        "currency": currency,
        "run_ref": run_ref,
        "batch_ref": batch_ref,
        "observation_ref": observation_ref,
        "business_record_ref": business_record_ref,
    }


def _csv_bytes(rows: tuple[dict[str, str], ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=_CSV_FIELDS, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _canonical_fields(fields: list[Any]) -> dict[str, Mapping[str, Any]]:
    canonical: dict[str, Mapping[str, Any]] = {}
    for field in fields:
        model = _mapping(field)
        ref = _text(model.get("field_observation_ref"))
        if ref in canonical:
            raise P0ResultViewError("RESULT_VIEW_P0_INVALID")
        canonical[ref] = model
    if not canonical:
        raise P0ResultViewError("RESULT_VIEW_P0_INVALID")
    return canonical


def _mapping(value: object) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise P0ResultViewError("RESULT_VIEW_P0_INVALID")
    return value


def _list(value: object) -> list[Any]:
    if type(value) is not list:
        raise P0ResultViewError("RESULT_VIEW_P0_INVALID")
    return value


def _text(value: object) -> str:
    if type(value) is not str or not value or "\n" in value or "\r" in value:
        raise P0ResultViewError("RESULT_VIEW_P0_INVALID")
    return value
