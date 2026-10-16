"""Read-only P28 review of an explicitly authorized public scalar export.

This opens no receiver, request, window or attempt. Original observation times
are retained; an identification export is never called a new live result.
"""

import argparse
from datetime import datetime
import json
import math
import os
import re
import stat
import unicodedata
from uuid import uuid4

from collection_core.p0 import P0Context
from collection_core.p28 import P28Error, build_p28_batch
from collection_core.p28_result_views import render_p28_result, p28_manifest
from parser_candidate import CaptureParserEvent
from parser_candidate.p28_profile import FAMILY, VERSION, p28_registry
from .p26_identification import IdentificationError
from .p26_public_projection import FOOD_ROUTE, PRODUCT_ROUTE
from .p26_result_mapping import restore_projection

_PRODUCT = "$.data.food_spu_tags[].dynamic_spus[]"
PATHS = {
    FOOD_ROUTE: frozenset({"$.code", "$.data.poi_info.id", "$.data.poi_info.poi_id_str", "$.data.poi_info.name"}),
    PRODUCT_ROUTE: frozenset({"$.code", "$.data.food_spu_tags[].tag", "$.data.food_spu_tags[].name",
                              "$.data.food_spu_tags[].current_page", "$.data.food_spu_tags[].has_next_page"}
        | {_PRODUCT + "." + f for f in ("id", "name", "unit", "min_price")}
        | {_PRODUCT + ".skus[]." + f for f in ("id", "spec", "spec_desc", "price", "origin_price", "status")}
        | {_PRODUCT + ".render_info.price_info.min_price"}),
}
_REF = r"[a-f0-9]{32}"
_MAX_BYTES = 4 * 1024 * 1024


def read_authorized_projection(root, name):
    """Only a named public projection; no symlinks, raw discovery or log output."""
    if (type(root) is not str or not os.path.isabs(root) or os.path.realpath(root) != root
            or type(name) is not str or re.fullmatch(r"identification-public-projection-" + _REF + r"\.json", name) is None):
        raise P28Error("P28_INPUT_FILE_INVALID")
    directory_fd = file_fd = None
    try:
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        ds = os.fstat(directory_fd)
        if ds.st_uid != os.getuid() or stat.S_IMODE(ds.st_mode) != 0o700:
            raise P28Error("P28_INPUT_FILE_INVALID")
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        fs = os.fstat(file_fd)
        if not stat.S_ISREG(fs.st_mode) or fs.st_uid != os.getuid() or stat.S_IMODE(fs.st_mode) != 0o600 or not 1 <= fs.st_size <= _MAX_BYTES:
            raise P28Error("P28_INPUT_FILE_INVALID")
        content = bytearray()
        while len(content) <= _MAX_BYTES:
            part = os.read(file_fd, min(65536, _MAX_BYTES + 1 - len(content)))
            if not part:
                break
            content.extend(part)
        if len(content) > _MAX_BYTES:
            raise P28Error("P28_INPUT_BUDGET_EXCEEDED")
        return json.loads(content)
    except P28Error:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise P28Error("P28_INPUT_FILE_INVALID") from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def build_authorized_projection_review(projection, expected_store, price_evidence):
    """Return in-memory views plus a value-free review; not capture success."""
    try:
        keys = {"schema_version", "window_ref", "observations", "store_name_match", "product_store_association", "sensitive_values_processed", "product_result"}
        if (type(projection) is not dict or set(projection) != keys
                or projection["schema_version"] != "p26-public-scalar-inspection/v1"
                or re.fullmatch("identification:" + _REF, projection["window_ref"]) is None
                or projection["sensitive_values_processed"] is not False or projection["store_name_match"] is not True
                or projection["product_result"] != "incomplete" or projection["product_store_association"] != "NOT_CONFIRMED"
                or type(expected_store) is not str or not expected_store or len(expected_store) > 256):
            raise P28Error("P28_PROJECTION_INVALID")
        observations = projection["observations"]
        if type(observations) is not list or len(observations) != 2:
            raise P28Error("P28_PROJECTION_INVALID")
        restored, rows = {}, {}
        for row in observations:
            row_keys = {"projection_ref", "route_slot", "observed_at", "values", "meaning", "unavailable_fields", "complete_record", "source_request_ref", "source_identity", "sensitive_values_processed"}
            if (type(row) is not dict or set(row) != row_keys or row["sensitive_values_processed"] is not False
                    or row["complete_record"] is not False or row["source_identity"] != "NOT_CONFIRMED"
                    or row["meaning"] != "DEVELOPER_REVIEW_REQUIRED"
                    or type(row["route_slot"]) is not int or not 1 <= row["route_slot"] <= 24
                    or re.fullmatch("projection:" + _REF, row["projection_ref"]) is None
                    or re.fullmatch("request:" + _REF, row["source_request_ref"]) is None
                    or type(row["values"]) is not list or not 1 <= len(row["values"]) <= 8000
                    or type(row["unavailable_fields"]) is not list or len(row["unavailable_fields"]) > 8000):
                raise P28Error("P28_PROJECTION_INVALID")
            paths = set()
            for field in row["values"]:
                if type(field) is not dict or set(field) != {"path", "coordinates", "value"} or type(field["path"]) is not str:
                    raise P28Error("P28_PROJECTION_INVALID")
                paths.add(field["path"])
            if "$.data.poi_info.poi_id_str" in paths and not any(p.startswith(_PRODUCT) for p in paths):
                route = FOOD_ROUTE
            elif "$.data.food_spu_tags[].tag" in paths and not any(p.startswith("$.data.poi_info.") for p in paths):
                route = PRODUCT_ROUTE
            else:
                raise P28Error("P28_PROJECTION_INVALID")
            if route in restored:
                raise P28Error("P28_PROJECTION_INVALID")
            selected = [f for f in row["values"] if f["path"] in PATHS[route]]
            capacities = {}
            for field in selected:
                coords, value = field["coordinates"], field["value"]
                if (type(coords) is not list or not 1 <= len(coords) <= 12
                        or type(value) not in (str, int, float, bool)
                        or (type(value) is str and len(value) > 1024)
                        or (type(value) is float and not math.isfinite(value))):
                    raise P28Error("P28_PROJECTION_INVALID")
                for index, coord in enumerate(coords):
                    if type(coord) is int:
                        if not 0 <= coord < 8000:
                            raise P28Error("P28_INPUT_BUDGET_EXCEEDED")
                        prefix = tuple(coords[:index])
                        capacities[prefix] = max(capacities.get(prefix, 0), coord + 1)
                    elif type(coord) is not str or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", coord) is None:
                        raise P28Error("P28_PROJECTION_INVALID")
            if sum(capacities.values()) > 8000:
                raise P28Error("P28_INPUT_BUDGET_EXCEEDED")
            unavailable = []
            for field in row["unavailable_fields"]:
                if type(field) is not dict or set(field) != {"path", "reason", "type"} or type(field["path"]) is not str:
                    raise P28Error("P28_PROJECTION_INVALID")
                if field["path"] in PATHS[route]:
                    unavailable.append(field)
            restored[route] = restore_projection({**row, "values": selected, "unavailable_fields": unavailable}, route, allowed_paths=PATHS[route])
            rows[route] = row
        if set(restored) != set(PATHS):
            raise P28Error("P28_PROJECTION_INVALID")
        food, product = restored[FOOD_ROUTE], restored[PRODUCT_ROUTE]
        if any(type(p.get("code")) is not int or p["code"] != 0 for p in (food, product)):
            raise P28Error("P28_PROJECTION_INVALID")
        normalize = lambda value: unicodedata.normalize("NFKC", value).replace(" ", "")
        if normalize(food["data"]["poi_info"]["name"]) != normalize(expected_store):
            raise P28Error("P28_TARGET_MISMATCH")
        times = [datetime.fromisoformat(rows[r]["observed_at"].replace("Z", "+00:00")) for r in (FOOD_ROUTE, PRODUCT_ROUTE)]
        if (any(t.utcoffset() is None for t in times) or abs((times[0] - times[1]).total_seconds()) > 10
                or len({row["projection_ref"] for row in observations}) != 2
                or len({row["source_request_ref"] for row in observations}) != 2
                or len({row["route_slot"] for row in observations}) != 2):
            raise P28Error("P28_OBSERVATION_INVALID")
        source_token = projection["window_ref"].split(":")[1]
        review_token = uuid4().hex
        ref = lambda prefix: prefix + ":" + review_token
        context = P0Context(
            run_ref=ref("run"), batch_ref=ref("batch"), source_ref="source:" + source_token,
            source_kind="USER_OWNED_EXPORT", provider_contract_ref=ref("provider-contract"),
            authorization_ref=ref("authorization"), attempt_ref="attempt:" + source_token,
            envelope_ref=ref("envelope"), observation_ref="observation:" + source_token,
            binding_context_ref=ref("context"), evidence_ref=price_evidence["evidence_ref"],
            source_integrity_ref=ref("source-integrity"), coverage_ref=ref("coverage"),
            coverage_scope_ref=ref("scope"), evidence_manifest_ref=ref("evidence-manifest"),
            observed_at=rows[PRODUCT_ROUTE]["observed_at"],
        )
        events = [CaptureParserEvent(read_scope="READ_" + review_token, observation_scope="OBS_" + source_token,
                  event_index=i, endpoint_id=endpoint, payload_family=FAMILY, payload_version=VERSION, payload=payload)
                  for i, endpoint, payload in ((1, "FOOD", food), (2, "PRODUCTLIST", product))]
        binding = build_p28_batch(events, p28_registry(), context, price_evidence)
        views = render_p28_result(binding)
        p28_manifest(views, "p28_memory_review")
        payload = json.loads(views.json_bytes)
        report = {"schema_version": "p28-public-projection-review/v1", "status": "PASS_IN_MEMORY_REVIEW",
                  "source_mode": "EXISTING_AUTHORIZED_PUBLIC_SCALAR_EXPORT", "new_capture": False,
                  "source_association": "CORROBORATION_ONLY_NOT_NEW_ROUTING_PROOF",
                  "complete": False, "product_result": "incomplete", "business_values_included": False,
                  "original_observation_time_preserved": True, "json_csv_manifest_consistent": True,
                  "new_identification_attempts": 0, "new_result_attempts": 0,
                  "runtime_business_files_written": 0, "sensitive_values_processed": False,
                  "raw_payload_persisted": False,
                  **{k: payload[k] for k in ("record_count", "product_count", "sku_count", "category_count")}}
        return views, report
    except P28Error:
        raise
    except (IdentificationError, KeyError, TypeError, ValueError, OverflowError):
        raise P28Error("P28_PROJECTION_INVALID") from None


class _Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise P28Error("P28_ARGUMENTS_INVALID")


def main():
    try:
        parser = _Arguments(description="Read-only P28 review of an authorized public scalar export; fixed diagnostics only.")
        parser.add_argument("--root", required=True)
        parser.add_argument("--projection-file", required=True)
        parser.add_argument("--expected-store", required=True)
        parser.add_argument("--price-evidence-ref", required=True)
        args = parser.parse_args()
        evidence = {"schema_version": "p28-price-evidence/v1", "basis": "USER_CONFIRMED_MULTI_SKU_PAGE",
                    "evidence_ref": args.price_evidence_ref, "currency": "CNY", "amount_unit": "YUAN"}
        _, report = build_authorized_projection_review(read_authorized_projection(args.root, args.projection_file), args.expected_store, evidence)
        print(json.dumps(report, sort_keys=True))
        return 0
    except P28Error as error:
        print(json.dumps({"status": error.code, "complete": False, "product_result": "incomplete", "new_identification_attempts": 0, "new_result_attempts": 0}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
