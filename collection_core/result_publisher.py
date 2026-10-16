"""Local, no-clobber publisher for one complete P0 JSON/CSV result set."""

from __future__ import annotations

import json
import csv
import io
import os
import re
import stat
from typing import Any

from .p1_result_views import P1_CSV_FIELDS, P1ResultViews
from .result_views import P0ResultViews
from .p26_result_views import P26ResultViews, P26_CSV_FIELDS
from .p28 import P28Error
from .p28_result_views import P28ResultViews, p28_manifest
from .p29 import P29Error, P29ResultViews, collection_manifest


_RESULT_NAME = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_FILES = ("records.json", "records.csv", "manifest.json")
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
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


class ResultPublishError(RuntimeError):
    """Closed-code local publishing failure without paths or source values."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def precheck_result_destination(root: str, result_name: str) -> None:
    """Reject an unusable destination before a run creates an attempt.

    The check stats the directory and the result name only. It does not create
    the result directory, follow a result symlink, or read any file body.
    """

    if type(result_name) is not str or _RESULT_NAME.fullmatch(result_name) is None:
        raise ResultPublishError("RESULT_INPUT_INVALID")
    _validate_root(root)
    if not os.access(root, os.W_OK | os.X_OK):
        raise ResultPublishError("RESULT_ROOT_INVALID")
    try:
        os.lstat(os.path.join(root, result_name))
    except FileNotFoundError:
        return
    except OSError:
        raise ResultPublishError("RESULT_ROOT_INVALID") from None
    raise ResultPublishError("RESULT_TARGET_EXISTS")


def publish_result_set(root: str, result_name: str, views: P0ResultViews | P1ResultViews | P26ResultViews | P28ResultViews | P29ResultViews) -> dict[str, object]:
    """Create one exclusive result directory and write JSON, CSV, then its manifest.

    ``manifest.json`` is the completion marker. The directory is created with
    ``mkdir`` exclusivity, so an existing result name is never opened, removed,
    or overwritten. On a local failure only this call's fixed child names are
    removed; no recursive cleanup is used.
    """

    manifest, record_count = _manifest_from_views(views, result_name)
    _validate_root(root)
    root_fd: int | None = None
    result_fd: int | None = None
    created = False
    success = False
    try:
        root_fd = os.open(root, _DIRECTORY_FLAGS)
        try:
            os.mkdir(result_name, 0o700, dir_fd=root_fd)
        except FileExistsError:
            raise ResultPublishError("RESULT_TARGET_EXISTS") from None
        created = True
        result_fd = os.open(result_name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        _write_file(result_fd, "records.json", views.json_bytes)
        _write_file(result_fd, "records.csv", views.csv_bytes)
        _write_file(result_fd, "manifest.json", manifest)
        os.fsync(result_fd)
        os.fsync(root_fd)
        success = True
    except ResultPublishError:
        raise
    except OSError:
        raise ResultPublishError("RESULT_PUBLISH_FAILED") from None
    finally:
        if not success and created:
            _cleanup_created_result(root_fd, result_fd, result_name)
        if result_fd is not None:
            try:
                os.close(result_fd)
            except OSError:
                pass
        if root_fd is not None:
            try:
                os.close(root_fd)
            except OSError:
                pass
    return {
        "result_name": result_name,
        "file_names": _FILES,
        "record_count": record_count,
    }


def _validate_root(root: object) -> None:
    if type(root) is not str or not os.path.isabs(root) or os.path.realpath(root) != root:
        raise ResultPublishError("RESULT_ROOT_INVALID")
    try:
        root_stat = os.stat(root, follow_symlinks=False)
    except OSError:
        raise ResultPublishError("RESULT_ROOT_INVALID") from None
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_IMODE(root_stat.st_mode) != 0o700:
        raise ResultPublishError("RESULT_ROOT_INVALID")


def _manifest_from_views(views: object, result_name: object) -> tuple[bytes, int]:
    if type(result_name) is not str or _RESULT_NAME.fullmatch(result_name) is None:
        raise ResultPublishError("RESULT_INPUT_INVALID")
    if type(views) is P29ResultViews:
        try:
            return collection_manifest(views, result_name)
        except P29Error:
            raise ResultPublishError("RESULT_INPUT_INVALID") from None
    if type(views) is P28ResultViews:
        try:
            return p28_manifest(views, result_name)
        except P28Error:
            raise ResultPublishError("RESULT_INPUT_INVALID") from None
    if type(views) is P0ResultViews:
        view_schema = "collection-p0-result-view/v1"
        manifest_schema = "collection-p0-result-manifest/v1"
        csv_fields = _CSV_FIELDS
    elif type(views) is P1ResultViews:
        view_schema = "collection-p1-result-view/v1"
        manifest_schema = "collection-p1-result-manifest/v1"
        csv_fields = P1_CSV_FIELDS
    elif type(views) is P26ResultViews:
        view_schema = "collection-p26-result-view/v1"
        manifest_schema = "collection-p26-result-manifest/v1"
        csv_fields = P26_CSV_FIELDS
    else:
        raise ResultPublishError("RESULT_INPUT_INVALID")
    try:
        payload = json.loads(views.json_bytes)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        raise ResultPublishError("RESULT_INPUT_INVALID") from None
    if type(payload) is not dict or payload.get("schema_version") != view_schema:
        raise ResultPublishError("RESULT_INPUT_INVALID")
    records = payload.get("records")
    count = payload.get("record_count")
    if (
        type(records) is not list
        or type(count) is not int
        or count != len(records)
        or count < 1
        or any(type(record) is not dict for record in records)
        or any(frozenset(record) != frozenset(csv_fields) for record in records)
        or any(any(type(value) is not str for value in record.values()) for record in records)
    ):
        raise ResultPublishError("RESULT_INPUT_INVALID")
    try:
        run_ref = _text(payload["run_ref"])
        batch_ref = _text(payload["batch_ref"])
        source_kind = _text(payload["source_kind"])
        observed_at = _text(payload["observed_at"])
        observation_refs = {_text(record["observation_ref"]) for record in records}
    except (KeyError, ResultPublishError):
        raise ResultPublishError("RESULT_INPUT_INVALID") from None
    if len(observation_refs) != 1:
        raise ResultPublishError("RESULT_INPUT_INVALID")
    if any(
        record["run_ref"] != run_ref
        or record["batch_ref"] != batch_ref
        for record in records
    ):
        raise ResultPublishError("RESULT_INPUT_INVALID")
    _validate_csv_view(views.csv_bytes, records, csv_fields)
    if type(views) is P26ResultViews:
        proof=payload.get("source_proof")
        if (type(proof) is not dict or proof.get("schema_version") not in {"p26-source-observation-proof/v1","p26-source-observation-proof/v2"}
            or any(proof.get(key) is not True for key in ("store_name_match","food_parameter_match","product_parameter_match"))
            or proof.get("run_ref")!=run_ref or proof.get("observation_ref")!=next(iter(observation_refs))
            or proof.get("product_observed_at")!=observed_at
            or proof.get("sensitive_values_processed") is not False or proof.get("raw_payload_persisted") is not False
            or source_kind!="SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE"
            or payload.get("coverage_status")!="PARTIAL" or payload.get("coverage_scope")!="CURRENT_LIST_RESPONSE_ONLY"
            or payload.get("unit_evidence")!="CURRENT_USER_PUBLIC_PAGE_CONFIRMATION_WITH_PRICE_MATCH"
            or any(r["currency"]!="CNY" or r["price_unit"]!="YUAN"
                   or r["price_meaning"]!="PRODUCT_LIST_MINIMUM_SKU_PRICE"
                   or r["observed_at"]!=observed_at or re.fullmatch(r"[0-9]+\.[0-9]{2}",r["price_yuan"]) is None for r in records)):
            raise ResultPublishError("RESULT_INPUT_INVALID")
        v2=proof["schema_version"]=="p26-source-observation-proof/v2"
        if (payload.get("payload_version")!=("p26-observed-shop-v2" if v2 else "p26-observed-shop-v1")
            or (v2 and (proof.get("payload_version")!="p26-observed-shop-v2"
                or proof.get("routing_parameter_key")!="poi_id_str"
                or proof.get("merchant_container")!="$.data.poi_info"
                or proof.get("secondary_routing_parameter_key")!="wm_poi_id"
                or proof.get("secondary_response_id_path")!="$.data.poi_info.id"
                or any(proof.get(k) is not True for k in ("food_secondary_parameter_match","product_secondary_parameter_match"))))):
            raise ResultPublishError("RESULT_INPUT_INVALID")
    manifest = {
        "schema_version": manifest_schema,
        "result_name": result_name,
        "run_ref": run_ref,
        "batch_ref": batch_ref,
        "observation_ref": next(iter(observation_refs)),
        "source_kind": source_kind,
        "observed_at": observed_at,
        "record_count": count,
        "files": list(_FILES),
    }
    if type(views) is P26ResultViews:
        manifest.update({key:payload[key] for key in (
            "payload_family","payload_version","coverage_status","coverage_scope","unit_evidence","source_proof")})
    return (json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8"), count


def _write_file(directory_fd: int, name: str, payload: bytes) -> None:
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory_fd)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise OSError("write failed")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)


def _validate_csv_view(csv_bytes: object, records: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    if type(csv_bytes) is not bytes:
        raise ResultPublishError("RESULT_INPUT_INVALID")
    try:
        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
        if tuple(reader.fieldnames or ()) != fields:
            raise ResultPublishError("RESULT_INPUT_INVALID")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error, ResultPublishError):
        raise ResultPublishError("RESULT_INPUT_INVALID") from None
    if rows != records:
        raise ResultPublishError("RESULT_INPUT_INVALID")


def _cleanup_created_result(root_fd: int | None, result_fd: int | None, result_name: str) -> None:
    if result_fd is not None:
        for name in _FILES:
            try:
                os.unlink(name, dir_fd=result_fd)
            except FileNotFoundError:
                pass
            except OSError:
                pass
    if root_fd is not None:
        try:
            os.rmdir(result_name, dir_fd=root_fd)
        except OSError:
            pass


def _text(value: object) -> str:
    if type(value) is not str or not value or "\n" in value or "\r" in value:
        raise ResultPublishError("RESULT_INPUT_INVALID")
    return value
