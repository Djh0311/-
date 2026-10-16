"""Stable JSON and CSV views for validated synthetic P1 records."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import json
from typing import Any, Mapping

from .p1 import P1AssemblyError, validate_p1_batch
from .p1_contract import P1_FIELD_SPECS
from .result_views import render_p0_result


_CORE_FIELDS = (
    "store",
    "product",
    "price_yuan",
    "currency",
    "run_ref",
    "batch_ref",
    "observation_ref",
    "business_record_ref",
)
_P1_FIELD_NAMES = tuple(P1_FIELD_SPECS)
_P1_METADATA = (
    "presence",
    "entity_kind",
    "source_local_entity_ref",
    "owner_entity_kind",
    "owner_entity_ref",
    "source_label",
    "value_encoding",
)


def _display_name(field_name: str) -> str:
    if field_name.endswith("_minor"):
        return field_name[:-6] + "_yuan"
    return field_name


P1_CSV_FIELDS = _CORE_FIELDS + tuple(
    name
    for field_name in _P1_FIELD_NAMES
    for name in (_display_name(field_name),) + tuple(f"{field_name}_{suffix}" for suffix in _P1_METADATA)
)


class P1ResultViewError(ValueError):
    """Closed-code P1 view failure without raw values or parser errors."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class P1ResultViews:
    """Canonical P1 bytes ready for the existing local no-clobber publisher."""

    json_bytes: bytes
    csv_bytes: bytes


def render_p1_result(p1_result: Mapping[str, Any]) -> P1ResultViews:
    """Render complete P1 rows from one validated same-observation P1 batch."""

    try:
        validate_p1_batch(p1_result)
        p0_payload = json.loads(render_p0_result(p1_result["p0_result"]).json_bytes)
        base_rows = {row["business_record_ref"]: row for row in _list(p0_payload["records"])}
        rows = tuple(_p1_row(record, base_rows) for record in _list(p1_result["p1_records"]))
        run_ref = _text(p0_payload["run_ref"])
        batch_ref = _text(p0_payload["batch_ref"])
        source_kind = _text(p0_payload["source_kind"])
        observed_at = _text(p0_payload["observed_at"])
    except (P1AssemblyError, KeyError, TypeError, json.JSONDecodeError, P1ResultViewError):
        raise P1ResultViewError("P1_RESULT_VIEW_INVALID") from None
    if not rows or any(row["run_ref"] != run_ref or row["batch_ref"] != batch_ref for row in rows):
        raise P1ResultViewError("P1_RESULT_VIEW_INVALID")
    payload = {
        "schema_version": "collection-p1-result-view/v1",
        "run_ref": run_ref,
        "batch_ref": batch_ref,
        "source_kind": source_kind,
        "observed_at": observed_at,
        "record_count": len(rows),
        "records": list(rows),
    }
    json_bytes = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return P1ResultViews(json_bytes=json_bytes, csv_bytes=_csv_bytes(rows))


def _p1_row(record: object, base_rows: Mapping[str, Mapping[str, str]]) -> dict[str, str]:
    model = _mapping(record)
    base = base_rows.get(_text(model.get("p0_business_record_ref")))
    if base is None or _text(model.get("observation_ref")) != base["observation_ref"]:
        raise P1ResultViewError("P1_RESULT_VIEW_INVALID")
    fields = {_text(field.get("field_name")): _mapping(field) for field in _list(model.get("p1_fields"))}
    if tuple(fields) != _P1_FIELD_NAMES:
        raise P1ResultViewError("P1_RESULT_VIEW_INVALID")
    row = {name: base[name] for name in _CORE_FIELDS}
    for field_name in _P1_FIELD_NAMES:
        field = fields[field_name]
        presence = _text(field.get("observation_presence"))
        value = _display_value(field, presence)
        row[_display_name(field_name)] = value
        row[f"{field_name}_presence"] = presence
        for suffix in _P1_METADATA[1:]:
            row[f"{field_name}_{suffix}"] = _text(field.get(suffix)) if field.get(suffix) is not None else ""
    if tuple(row) != P1_CSV_FIELDS:
        raise P1ResultViewError("P1_RESULT_VIEW_INVALID")
    return row


def _display_value(field: Mapping[str, Any], presence: str) -> str:
    value = field.get("normalized_value")
    encoding = field.get("value_encoding")
    if presence != "PRESENT":
        if value is not None or encoding is not None:
            raise P1ResultViewError("P1_RESULT_VIEW_INVALID")
        return ""
    if encoding == "MONEY_MINOR":
        if type(value) is not int or value < 0:
            raise P1ResultViewError("P1_RESULT_VIEW_INVALID")
        return f"{value // 100}.{value % 100:02d}"
    if type(value) is int:
        return str(value)
    return _text(value)


def _csv_bytes(rows: tuple[dict[str, str], ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=P1_CSV_FIELDS, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _mapping(value: object) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise P1ResultViewError("P1_RESULT_VIEW_INVALID")
    return value


def _list(value: object) -> list[Any]:
    if type(value) is not list:
        raise P1ResultViewError("P1_RESULT_VIEW_INVALID")
    return value


def _text(value: object) -> str:
    if type(value) is not str or not value or "\n" in value or "\r" in value:
        raise P1ResultViewError("P1_RESULT_VIEW_INVALID")
    return value
