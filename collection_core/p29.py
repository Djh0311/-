"""Bounded collections of complete observations; never merge row fields."""

from copy import deepcopy
import csv
from dataclasses import dataclass
from datetime import datetime
import io
import json
import re

from .p28 import P28Error
from .p28_result_views import P28_CSV_FIELDS, P28ResultViews, p28_manifest
from .p29_source_association import p29_association_ready, NUMERIC_VERSION

MAX_OBSERVATIONS = 32
MAX_ROWS = 40000
MAX_COLLECTION_BYTES = 16 * 1024 * 1024
CSV_FIELDS = P28_CSV_FIELDS + ("collection_observation_index",)
_CATEGORY_KEYS = frozenset({"category_ref", "category_name", "source_page_number",
    "source_has_next_page", "source_reported_product_count", "folded_product_ids",
    "loaded_product_ids", "page_semantics", "termination_semantics"})
_ASSOCIATION_REQUIRED = ("store_name_match", "food_success_code", "product_success_code",
    "same_observation_gap_valid", "public_string_id_ready",
    "food_poi_id_str_matches_public_string_id", "product_poi_id_str_matches_public_string_id",
    "poi_id_str_equal_between_requests", "food_wm_poi_id_matches_numeric_id",
    "product_wm_poi_id_matches_numeric_id", "wm_poi_id_equal_between_requests")
_ASSOCIATION_KEYS = frozenset({"schema_version", "window_ref", "store_name_match",
    "merchant_container", "public_string_id_ready", "numeric_id_is_negative",
    "public_id_fields_equal_as_text", "food_success_code", "product_success_code",
    "same_observation_gap_valid", "raw_payload_persisted", "sensitive_values_processed"}
    | {label + "_" + key + suffix for label in ("food", "product")
       for key in ("wm_poi_id", "poi_id_str")
       for suffix in ("_ready", "_matches_public_string_id", "_matches_numeric_id")}
    | {key + "_equal_between_requests" for key in ("wm_poi_id", "poi_id_str")})


class P29Error(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class P29ResultViews:
    json_bytes: bytes
    csv_bytes: bytes
    snapshots: tuple


def _category_check(categories, records):
    if type(categories) is not list or not 1 <= len(categories) <= 256:
        raise P29Error("P29_COVERAGE_INVALID")
    seen = set()
    for c in categories:
        if type(c) is not dict or set(c) != _CATEGORY_KEYS:
            raise P29Error("P29_COVERAGE_INVALID")
        for key in ("category_ref", "category_name"):
            if (type(c[key]) is not str or not 1 <= len(c[key]) <= 256
                    or any(ch in c[key] for ch in ('\r', '\n', '\0'))):
                raise P29Error("P29_COVERAGE_INVALID")
        if c["category_ref"] in seen:
            raise P29Error("P29_COVERAGE_INVALID")
        seen.add(c["category_ref"])
        for key in ("source_page_number", "source_reported_product_count"):
            if c[key] is not None and (type(c[key]) is not int or not 0 <= c[key] <= MAX_ROWS):
                raise P29Error("P29_COVERAGE_INVALID")
        if c["source_has_next_page"] is not None and type(c["source_has_next_page"]) is not bool:
            raise P29Error("P29_COVERAGE_INVALID")
        if c["page_semantics"] != "UNCONFIRMED" or c["termination_semantics"] != "UNCONFIRMED":
            raise P29Error("P29_TERMINATION_UNPROVEN")
        for key in ("loaded_product_ids", "folded_product_ids"):
            ids = c[key]
            if (type(ids) is not list or len(ids) > MAX_ROWS
                    or any(type(i) is not str or re.fullmatch(r"-?[0-9]+", i) is None for i in ids)
                    or len(set(ids)) != len(ids)):
                raise P29Error("P29_COVERAGE_INVALID")
        loaded = {r["product_id"] for r in records if r["category_ref"] == c["category_ref"]}
        if loaded != set(c["loaded_product_ids"]):
            raise P29Error("P29_COVERAGE_INVALID")
        if any(r['category_name'] != c['category_name'] for r in records
               if r['category_ref'] == c['category_ref']):
            raise P29Error('P29_COVERAGE_INVALID')
    if any(r["category_ref"] not in seen for r in records):
        raise P29Error("P29_COVERAGE_INVALID")


def snapshot_from_views(views, categories, association, window_ref, result_name=None):
    """Accept the bound model, not an arbitrary JSON/CSV object."""
    if type(views) is not P28ResultViews:
        raise P29Error("P29_OBSERVATION_INVALID")
    try:
        p28_manifest(views, "observation_check")
        view = json.loads(views.json_bytes)
        if (not p29_association_ready(association, window_ref)
                or type(window_ref) is not str or re.fullmatch(r"result:[a-f0-9]{32}", window_ref) is None
                or result_name is not None and (type(result_name) is not str
                    or re.fullmatch(r"observation_[a-f0-9]{32}", result_name) is None)
                or view['source_kind'] == 'SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE' and result_name is None):
            raise P29Error("P29_SOURCE_ASSOCIATION_INVALID")
        _category_check(categories, view["records"])
        return {"view": view, "binding": deepcopy(views.binding_batch),
                "categories": deepcopy(categories), "source_association": deepcopy(association),
                "window_ref": window_ref, "result_name": result_name}
    except P29Error:
        raise
    except (P28Error, ValueError, TypeError, KeyError):
        raise P29Error("P29_OBSERVATION_INVALID") from None


def render_collection(snapshots):
    """Select the last complete row per membership, retaining all source snapshots."""
    if type(snapshots) not in (list, tuple) or not 1 <= len(snapshots) <= MAX_OBSERVATIONS:
        raise P29Error("P29_COLLECTION_BUDGET")
    try:
        if len(json.dumps(snapshots, ensure_ascii=True, allow_nan=False).encode()) > MAX_COLLECTION_BYTES:
            raise P29Error("P29_COLLECTION_BUDGET")
    except P29Error:
        raise
    except (ValueError, TypeError):
        raise P29Error("P29_OBSERVATION_INVALID") from None
    selected, owners, store_ids, batches, observation_refs, observations, coverage = {}, {}, set(), set(), set(), [], []
    rows_read = 0
    source_kind = None
    last_time = None
    for index, snapshot in enumerate(snapshots, 1):
        try:
            if type(snapshot) is not dict or set(snapshot) != {"view", "binding", "categories", "source_association", "window_ref", "result_name"}:
                raise P29Error("P29_OBSERVATION_INVALID")
            from .p28_result_views import render_p28_result
            regenerated = render_p28_result(snapshot["binding"])
            if json.loads(regenerated.json_bytes) != snapshot["view"]:
                raise P29Error("P29_OBSERVATION_INVALID")
            checked = snapshot_from_views(regenerated, snapshot["categories"], snapshot["source_association"], snapshot["window_ref"], snapshot["result_name"])
            v = checked["view"]
            observation_ref = v['records'][0]['observation_ref']
            if v["batch_ref"] in batches or observation_ref in observation_refs:
                raise P29Error("P29_OBSERVATION_REUSED")
            batches.add(v["batch_ref"])
            observation_refs.add(observation_ref)
            current_time = datetime.fromisoformat(v["observed_at"])
            if current_time.tzinfo is None or last_time is not None and current_time < last_time:
                raise P29Error("P29_OBSERVATION_ORDER_INVALID")
            last_time = current_time
            if source_kind is not None and source_kind != v["source_kind"]:
                raise P29Error("P29_SOURCE_CHANGED")
            source_kind = v["source_kind"]
            observations.append({"index": index, "run_ref": v["run_ref"], "batch_ref": v["batch_ref"],
                "observed_at": v["observed_at"], "window_ref": snapshot["window_ref"],
                "record_count": v["record_count"], "product_count": v["product_count"],
                "sku_count": v["sku_count"], "category_count": v["category_count"],
                "payload_family": v["payload_family"], "payload_version": v["payload_version"],
                "price_evidence": deepcopy(v["price_evidence"]), "result_name": snapshot["result_name"],
                "source_association": deepcopy(snapshot["source_association"])})
            coverage.append({"observation_index": index, "categories": deepcopy(snapshot["categories"])})
            for row in v["records"]:
                rows_read += 1
                if rows_read > MAX_ROWS:
                    raise P29Error("P29_COLLECTION_BUDGET")
                store_ids.add(row["store_id"])
                if len(store_ids) != 1:
                    raise P29Error("P29_SOURCE_CHANGED")
                owner_key = (row["store_id"], row["sku_id"])
                if owner_key in owners and owners[owner_key] != row["product_id"]:
                    raise P29Error("P29_SKU_OWNER_CHANGED")
                owners[owner_key] = row["product_id"]
                key = (row["store_id"], row["sku_id"], row["category_ref"])
                # No field is taken from any other observation.
                selected[key] = {**deepcopy(row), "collection_observation_index": str(index)}
        except P29Error:
            raise
        except (P28Error, ValueError, TypeError, KeyError):
            raise P29Error("P29_OBSERVATION_INVALID") from None
    rows = list(selected.values())
    products = {(r["store_id"], r["product_id"]) for r in rows}
    skus = {(r["store_id"], r["sku_id"]) for r in rows}
    categories = {(r["store_id"], r["category_ref"]) for r in rows}
    last_categories = {}
    for page in coverage:
        for c in page["categories"]:
            last_categories[c["category_ref"]] = c
    folded = {i for c in last_categories.values() for i in c["folded_product_ids"]}
    loaded_ids = {r["product_id"] for r in rows}
    loaded_memberships = {(r["category_ref"], r["product_id"]) for r in rows}
    folded_memberships = {(c["category_ref"], i) for c in last_categories.values()
                           for i in c["folded_product_ids"]}
    if len(last_categories) > 256 or len(folded_memberships) > MAX_ROWS:
        raise P29Error('P29_COLLECTION_BUDGET')
    version = 'v2' if any(o['source_association']['schema_version'] == NUMERIC_VERSION
                         for o in observations) else 'v1'
    view = {"schema_version": "collection-p29-result-view/" + version, "source_kind": source_kind,
        "record_count": len(rows), "product_count": len(products), "sku_count": len(skus),
        "category_count": len(categories), "source_category_count": len(last_categories),
        "observation_count": len(observations), "input_record_count": rows_read,
        "deduplicated_record_count": rows_read - len(rows),
        "folded_product_references_not_loaded": len(folded - loaded_ids),
        "category_product_references_not_loaded": len(folded_memberships - loaded_memberships),
        "coverage_status": "PARTIAL", "coverage_scope": "OBSERVED_COMPLETE_SNAPSHOTS_ONLY",
        "page_semantics": "UNCONFIRMED", "termination_semantics": "UNCONFIRMED",
        "deduplication": "LATEST_COMPLETE_ROW_PER_STORE_SKU_CATEGORY",
        "observations": observations, "category_observations": coverage, "records": rows}
    data = json.dumps(view, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n", extrasaction="raise")
    writer.writeheader(); writer.writerows(rows)
    csv_data = stream.getvalue().encode()
    if len(data) + len(csv_data) > MAX_COLLECTION_BYTES:
        raise P29Error("P29_COLLECTION_BUDGET")
    return P29ResultViews(data, csv_data, tuple(deepcopy(snapshots)))


def collection_manifest(views, result_name):
    if type(views) is not P29ResultViews:
        raise P29Error("P29_RESULT_VIEW_INVALID")
    rebuilt = render_collection(views.snapshots)
    if rebuilt.json_bytes != views.json_bytes or rebuilt.csv_bytes != views.csv_bytes:
        raise P29Error("P29_RESULT_VIEW_INVALID")
    v = json.loads(views.json_bytes)
    metadata = {k: deepcopy(v[k]) for k in v if k not in {"records", "category_observations"}}
    metadata.update(schema_version=v['schema_version'].replace('result-view/', 'result-manifest/'), result_name=result_name,
                    files=["records.json", "records.csv", "manifest.json"])
    return json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(), v["record_count"]
