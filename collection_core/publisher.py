"""Deterministic no-clobber publisher for validated P0 business bundles."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from typing import Any, Mapping

from .p0 import P0Error, validate_p0_batch


class P0PublisherError(RuntimeError):
    """Closed-code publishing failure without source values or filesystem paths."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def publish_p0_bundle(root: str, target_name: str, result: Mapping[str, Any]) -> dict[str, str]:
    """Publish one canonical P0 bundle using atomic link-based no-clobber promotion."""

    try:
        validate_p0_batch(result)
    except P0Error as error:
        raise P0PublisherError("P0_BUNDLE_INVALID") from error
    if type(root) is not str or not os.path.isabs(root) or os.path.realpath(root) != root:
        raise P0PublisherError("P0_ROOT_INVALID")
    if type(target_name) is not str or not target_name.endswith(".json") or "/" in target_name:
        raise P0PublisherError("P0_TARGET_INVALID")
    try:
        root_stat = os.stat(root)
    except OSError as error:
        raise P0PublisherError("P0_ROOT_INVALID") from error
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_IMODE(root_stat.st_mode) != 0o700:
        raise P0PublisherError("P0_ROOT_INVALID")
    bundle = {
        "schema_version": "collection-p0-bundle/v1",
        "records": result,
        "readable_records": _readable_records(result),
    }
    payload = json.dumps(bundle, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    target = os.path.join(root, target_name)
    staging = os.path.join(root, ".p0-" + secrets.token_hex(12))
    try:
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(staging, target, follow_symlinks=False)
        except FileExistsError as error:
            raise P0PublisherError("P0_TARGET_EXISTS") from error
        finally:
            os.unlink(staging)
        with open(target, "rb") as published:
            if published.read() != payload:
                raise P0PublisherError("P0_REOPEN_FAILED")
    except P0PublisherError:
        raise
    except OSError as error:
        raise P0PublisherError("P0_PUBLISH_FAILED") from error
    finally:
        try:
            if os.path.exists(staging):
                os.unlink(staging)
        except OSError:
            pass
    return {"sha256": digest, "target_name": target_name}


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:])
        if written <= 0:
            raise P0PublisherError("P0_PUBLISH_FAILED")
        offset += written


def _readable_records(result: Mapping[str, Any]) -> list[dict[str, str]]:
    readable: list[dict[str, str]] = []
    for record in result["business_records"]:
        values = {field["field_name"]: field for field in record["field_observations"]}
        price_minor = values["display_price_minor"]["normalized_value"]
        if type(price_minor) is not int:
            raise P0PublisherError("P0_BUNDLE_INVALID")
        readable.append(
            {
                "store": values["store_name"]["public_value_raw"],
                "product": values["product_name"]["public_value_raw"],
                "price_yuan": f"{price_minor // 100}.{price_minor % 100:02d}",
                "currency": values["currency"]["normalized_value"],
            }
        )
    return readable
