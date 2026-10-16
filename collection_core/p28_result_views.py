"""Canonical per-SKU views of one validated, partial public observation."""

from copy import deepcopy
import csv
from dataclasses import dataclass
import io
import json

from .p28 import P28Error, validate_p28_batch
from .result_views import P0ResultViewError, render_p0_result


P28_CSV_FIELDS = (
    "store", "store_id", "product", "product_id", "sku_id", "category_ref", "category_name",
    "sku_spec", "sku_spec_state", "sku_description", "sku_description_state",
    "product_unit_text", "product_unit_state", "sku_price_yuan", "product_display_price_yuan",
    "currency", "price_unit", "sku_price_meaning", "display_price_meaning",
    "source_origin_price_number", "source_origin_price_state", "original_price_yuan", "original_price_state",
    "activity_price_yuan", "activity_price_state", "packaging_fee_yuan", "packaging_fee_state",
    "availability_status", "availability_status_state", "promotion_state",
    "run_ref", "batch_ref", "observation_ref", "business_record_ref", "observed_at",
)


@dataclass(frozen=True)
class P28ResultViews:
    json_bytes: bytes
    csv_bytes: bytes
    binding_batch: dict


def render_p28_result(binding_batch):
    """Keep category membership; never deduplicate by name or substitute prices."""
    try:
        validate_p28_batch(binding_batch)
        base_view = json.loads(render_p0_result(binding_batch["p0_result"]).json_bytes)
        bases = {r["business_record_ref"]: r for r in base_view["records"]}
        rows = []
        for sku in binding_batch["sku_records"]:
            base = bases[sku["p0_business_record_ref"]]
            row = {k: base[k] for k in ("store", "product", "currency", "run_ref", "batch_ref", "observation_ref", "business_record_ref")}
            for key in P28_CSV_FIELDS:
                if key in sku:
                    row[key] = "" if sku[key] is None else sku[key]
            row.update(
                sku_price_yuan=_yuan(sku["sku_price_minor"]),
                product_display_price_yuan=_yuan(sku["product_display_price_minor"]),
                price_unit="YUAN", sku_price_meaning="OBSERVED_SKU_CURRENT_PRICE",
                display_price_meaning="PRODUCT_LIST_MINIMUM_SKU_PRICE",
                original_price_yuan="", activity_price_yuan="", packaging_fee_yuan="",
            )
            if set(row) != set(P28_CSV_FIELDS) or any(type(v) is not str for v in row.values()):
                raise P28Error("P28_RESULT_VIEW_INVALID")
            rows.append(row)
        payload = {k: base_view[k] for k in ("run_ref", "batch_ref", "source_kind", "observed_at")}
        payload.update(
            schema_version="collection-p28-result-view/v1",
            payload_family=binding_batch["payload_family"], payload_version=binding_batch["payload_version"],
            coverage_status="PARTIAL", coverage_scope="CURRENT_LIST_RESPONSE_ONLY",
            price_evidence=deepcopy(binding_batch["price_evidence"]),
            record_count=len(rows),
            product_count=len({(r["store_id"], r["product_id"]) for r in rows}),
            sku_count=len({(r["store_id"], r["sku_id"]) for r in rows}),
            category_count=len({(r["store_id"], r["category_ref"]) for r in rows}),
            records=rows,
        )
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=P28_CSV_FIELDS, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
        return P28ResultViews(_json_bytes(payload), stream.getvalue().encode("utf-8"), deepcopy(binding_batch))
    except P28Error:
        raise
    except (P0ResultViewError, KeyError, TypeError, ValueError):
        raise P28Error("P28_RESULT_VIEW_INVALID") from None


def p28_manifest(views, result_name):
    """Re-render the binding model before the publisher opens a destination."""
    if type(views) is not P28ResultViews or type(views.json_bytes) is not bytes or type(views.csv_bytes) is not bytes:
        raise P28Error("P28_RESULT_VIEW_INVALID")
    canonical = render_p28_result(views.binding_batch)
    if canonical.json_bytes != views.json_bytes or canonical.csv_bytes != views.csv_bytes:
        raise P28Error("P28_RESULT_VIEW_INVALID")
    payload = json.loads(canonical.json_bytes)
    manifest = {k: payload[k] for k in (
        "run_ref", "batch_ref", "source_kind", "observed_at", "payload_family", "payload_version",
        "coverage_status", "coverage_scope", "price_evidence", "record_count", "product_count", "sku_count", "category_count",
    )}
    manifest.update(schema_version="collection-p28-result-manifest/v1", result_name=result_name,
                    observation_ref=payload["records"][0]["observation_ref"],
                    files=["records.json", "records.csv", "manifest.json"])
    return _json_bytes(manifest), payload["record_count"]


def _yuan(minor):
    return f"{minor // 100}.{minor % 100:02d}"


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
