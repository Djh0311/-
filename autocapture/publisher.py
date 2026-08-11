"""Atomic, no-clobber publication for value-free sanitized shapes."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from typing import Dict, List, Optional, Tuple

from autocapture.shape import (
    REGISTERED_SAFE,
    SAFE_UNREGISTERED,
    SanitizedShape,
    classify_schema_key,
)


BUNDLE_SCHEMA_VERSION = "autocapture-shape-bundle/v1"
MANIFEST_SCHEMA_VERSION = "autocapture-shape-manifest/v1"
SHAPE_SCHEMA_VERSION = "autocapture-sanitized-shape/v1"

_MAX_EVENTS = 128
_MAX_NODES = 10_000
_MAX_PATH_LENGTH = 4_096
_MAX_PATH_DEPTH = 64
_MAX_STAGING_ATTEMPTS = 8
_ALLOWED_TYPES = frozenset(
    ("array", "boolean", "integer", "null", "number", "object", "string")
)
_ALLOWED_RELATIONS = frozenset(("root", "object_member", "array_item"))


class PublisherError(RuntimeError):
    """A publication failure whose public representation is one fixed code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _DuplicateKey(ValueError):
    pass


def _raise(code: str) -> None:
    raise PublisherError(code)


def _canonical_json(model: object) -> bytes:
    try:
        encoded = json.dumps(
            model,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError):
        _raise("PUBLISH_SCHEMA_INVALID")
    return encoded.encode("utf-8")


def _strict_object(pairs: List[Tuple[str, object]]) -> Dict[str, object]:
    result: Dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey()
        result[key] = value
    return result


def _strict_json_loads(payload: bytes) -> object:
    try:
        text = payload.decode("utf-8", "strict")
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=lambda _: (_ for _ in ()).throw(_DuplicateKey()),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateKey):
        _raise("PUBLISH_REOPEN_INVALID")


def _is_plain_dict(value: object) -> bool:
    return type(value) is dict


def _exact_keys(value: object, expected: frozenset) -> bool:
    return _is_plain_dict(value) and frozenset(value.keys()) == expected


def _decode_pointer_token(token: str) -> Optional[str]:
    output: List[str] = []
    index = 0
    while index < len(token):
        character = token[index]
        if character != "~":
            output.append(character)
            index += 1
            continue
        if index + 1 >= len(token):
            return None
        escaped = token[index + 1]
        if escaped == "0":
            output.append("~")
        elif escaped == "1":
            output.append("/")
        else:
            return None
        index += 2
    return "".join(output)


def _valid_pointer(path: object, allowed_schema_keys: frozenset) -> bool:
    if type(path) is not str or len(path) > _MAX_PATH_LENGTH:
        return False
    if path == "":
        return True
    if not path.startswith("/") or any(
        ord(character) < 0x20 or ord(character) == 0x7F for character in path
    ):
        return False
    encoded_tokens = path[1:].split("/")
    if len(encoded_tokens) > _MAX_PATH_DEPTH:
        return False
    for encoded in encoded_tokens:
        decoded = _decode_pointer_token(encoded)
        if (
            decoded is None
            or (
                decoded != "*"
                and classify_schema_key(decoded, allowed_schema_keys)
                not in (REGISTERED_SAFE, SAFE_UNREGISTERED)
            )
        ):
            return False
    return True


def _expected_parent(path: str) -> Optional[str]:
    if path == "":
        return None
    return path.rsplit("/", 1)[0]


def _valid_positive_int(value: object, maximum: int) -> bool:
    return type(value) is int and 0 < value <= maximum


def _validate_shape_model(
    model: object,
    allowed_schema_keys: frozenset,
) -> str:
    top_keys = frozenset(
        (
            "schema_version",
            "event_count",
            "nodes",
            "sanitized_shape_digest",
        )
    )
    if not _exact_keys(model, top_keys):
        _raise("PUBLISH_SHAPE_SCHEMA_INVALID")
    if model["schema_version"] != SHAPE_SCHEMA_VERSION:
        _raise("PUBLISH_SHAPE_SCHEMA_INVALID")

    event_count = model["event_count"]
    if not _valid_positive_int(event_count, _MAX_EVENTS):
        _raise("PUBLISH_SHAPE_SCHEMA_INVALID")

    nodes = model["nodes"]
    if type(nodes) is not list or not 0 < len(nodes) <= _MAX_NODES:
        _raise("PUBLISH_SHAPE_SCHEMA_INVALID")

    node_keys = frozenset(
        ("path", "types", "parent", "relation", "presence", "cardinality")
    )
    presence_keys = frozenset(("observed_events", "total_events"))
    cardinality_keys = frozenset(("minimum", "maximum"))
    prior_paths = set()
    ordered_paths: List[str] = []
    types_by_path: Dict[str, frozenset] = {}

    for index, node in enumerate(nodes):
        if not _exact_keys(node, node_keys):
            _raise("PUBLISH_SHAPE_SCHEMA_INVALID")
        path = node["path"]
        if not _valid_pointer(path, allowed_schema_keys) or path in prior_paths:
            _raise("PUBLISH_PRIVACY_REJECTED")
        if index == 0:
            if path != "" or node["parent"] is not None or node["relation"] != "root":
                _raise("PUBLISH_SHAPE_SCHEMA_INVALID")
        else:
            if path == "" or node["relation"] not in ("object_member", "array_item"):
                _raise("PUBLISH_SHAPE_SCHEMA_INVALID")
            parent = node["parent"]
            if type(parent) is not str or parent != _expected_parent(path):
                _raise("PUBLISH_SHAPE_SCHEMA_INVALID")
            if parent not in prior_paths:
                _raise("PUBLISH_SHAPE_SCHEMA_INVALID")

        types = node["types"]
        if (
            type(types) is not list
            or not types
            or any(type(item) is not str or item not in _ALLOWED_TYPES for item in types)
            or types != sorted(set(types))
        ):
            _raise("PUBLISH_SHAPE_SCHEMA_INVALID")

        relation = node["relation"]
        if type(relation) is not str or relation not in _ALLOWED_RELATIONS:
            _raise("PUBLISH_SHAPE_SCHEMA_INVALID")
        if path != "":
            final_token = _decode_pointer_token(path.rsplit("/", 1)[1])
            if (
                final_token is None
                or (relation == "array_item" and final_token != "*")
                or (relation == "object_member" and final_token == "*")
            ):
                _raise("PUBLISH_SHAPE_SCHEMA_INVALID")
            parent_types = types_by_path[node["parent"]]
            if relation == "object_member" and "object" not in parent_types:
                _raise("PUBLISH_SHAPE_SCHEMA_INVALID")
            if relation == "array_item" and "array" not in parent_types:
                _raise("PUBLISH_SHAPE_SCHEMA_INVALID")

        presence = node["presence"]
        if not _exact_keys(presence, presence_keys):
            _raise("PUBLISH_SHAPE_SCHEMA_INVALID")
        observed = presence["observed_events"]
        total = presence["total_events"]
        if (
            type(observed) is not int
            or type(total) is not int
            or observed <= 0
            or observed > total
            or total != event_count
        ):
            _raise("PUBLISH_SHAPE_SCHEMA_INVALID")
        if path == "" and observed != event_count:
            _raise("PUBLISH_SHAPE_SCHEMA_INVALID")

        cardinality = node["cardinality"]
        if cardinality is not None:
            if not _exact_keys(cardinality, cardinality_keys):
                _raise("PUBLISH_SHAPE_SCHEMA_INVALID")
            minimum = cardinality["minimum"]
            maximum = cardinality["maximum"]
            if (
                type(minimum) is not int
                or type(maximum) is not int
                or minimum < 0
                or maximum < minimum
                or not set(types).intersection(("array", "object"))
            ):
                _raise("PUBLISH_SHAPE_SCHEMA_INVALID")

        prior_paths.add(path)
        ordered_paths.append(path)
        types_by_path[path] = frozenset(types)

    if ordered_paths != sorted(ordered_paths):
        _raise("PUBLISH_SHAPE_SCHEMA_INVALID")

    digest = model["sanitized_shape_digest"]
    if (
        type(digest) is not str
        or len(digest) != 71
        or not digest.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in digest[7:])
    ):
        _raise("PUBLISH_SHAPE_DIGEST_INVALID")
    unsigned = {
        "schema_version": model["schema_version"],
        "event_count": model["event_count"],
        "nodes": model["nodes"],
    }
    expected = "sha256:" + hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    if digest != expected:
        _raise("PUBLISH_SHAPE_DIGEST_INVALID")
    return digest


def _build_bundle(model: dict, allowed_schema_keys: frozenset) -> dict:
    digest = _validate_shape_model(model, allowed_schema_keys)
    bundle = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "manifest": {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "artifact_kind": "sanitized_shape",
            "sanitized_shape_digest": digest,
        },
        "sanitized_shape": model,
    }
    _validate_bundle(bundle, allowed_schema_keys)
    return bundle


def _validate_bundle(bundle: object, allowed_schema_keys: frozenset) -> None:
    if not _exact_keys(
        bundle,
        frozenset(("schema_version", "manifest", "sanitized_shape")),
    ):
        _raise("PUBLISH_BUNDLE_SCHEMA_INVALID")
    if bundle["schema_version"] != BUNDLE_SCHEMA_VERSION:
        _raise("PUBLISH_BUNDLE_SCHEMA_INVALID")
    manifest = bundle["manifest"]
    if not _exact_keys(
        manifest,
        frozenset(("schema_version", "artifact_kind", "sanitized_shape_digest")),
    ):
        _raise("PUBLISH_MANIFEST_SCHEMA_INVALID")
    if (
        manifest["schema_version"] != MANIFEST_SCHEMA_VERSION
        or manifest["artifact_kind"] != "sanitized_shape"
    ):
        _raise("PUBLISH_MANIFEST_SCHEMA_INVALID")
    shape_digest = _validate_shape_model(
        bundle["sanitized_shape"],
        allowed_schema_keys,
    )
    if manifest["sanitized_shape_digest"] != shape_digest:
        _raise("PUBLISH_MANIFEST_DIGEST_INVALID")


def _file_identity(file_stat: os.stat_result) -> Tuple[int, int]:
    return file_stat.st_dev, file_stat.st_ino


def _lstat_at(root_fd: int, name: str) -> Optional[os.stat_result]:
    try:
        return os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _write_all(file_fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        try:
            written = os.write(file_fd, payload[offset:])
        except InterruptedError:
            continue
        if type(written) is not int or written <= 0:
            _raise("PUBLISH_STAGING_WRITE_FAILED")
        offset += written


def _read_exact(file_fd: int, expected_size: int) -> bytes:
    chunks: List[bytes] = []
    remaining = expected_size + 1
    while remaining > 0:
        try:
            chunk = os.read(file_fd, min(65_536, remaining))
        except InterruptedError:
            continue
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    payload = b"".join(chunks)
    if len(payload) != expected_size:
        _raise("PUBLISH_REOPEN_INVALID")
    return payload


class AtomicShapePublisher:
    """Publish one canonical shape bundle without overwriting any target."""

    def __init__(
        self,
        root_dir: object,
        target_name: str = "shape-bundle.json",
        *,
        allowed_schema_keys: frozenset,
    ) -> None:
        try:
            root_value = os.fspath(root_dir)
        except TypeError:
            _raise("PUBLISH_ROOT_INVALID")
        if type(root_value) is not str or not root_value or "\x00" in root_value:
            _raise("PUBLISH_ROOT_INVALID")
        if (
            type(target_name) is not str
            or not target_name
            or "\x00" in target_name
            or target_name in (".", "..")
            or os.path.isabs(target_name)
            or os.path.basename(target_name) != target_name
            or "/" in target_name
            or "\\" in target_name
        ):
            _raise("PUBLISH_TARGET_NAME_INVALID")
        if (
            type(allowed_schema_keys) is not frozenset
            or not allowed_schema_keys
            or any(
                classify_schema_key(key, allowed_schema_keys) != REGISTERED_SAFE
                for key in allowed_schema_keys
            )
        ):
            _raise("PUBLISH_POLICY_INVALID")
        if not os.path.isabs(root_value):
            _raise("PUBLISH_ROOT_INVALID")
        absolute = os.path.abspath(root_value)
        try:
            if os.path.realpath(absolute) != absolute:
                _raise("PUBLISH_ROOT_INVALID")
            initial = os.lstat(absolute)
            if not stat.S_ISDIR(initial.st_mode) or stat.S_ISLNK(initial.st_mode):
                _raise("PUBLISH_ROOT_INVALID")
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            flags |= getattr(os, "O_CLOEXEC", 0)
            root_fd = os.open(absolute, flags)
            try:
                opened = os.fstat(root_fd)
                current = os.stat(absolute, follow_symlinks=False)
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or opened.st_uid != os.geteuid()
                    or stat.S_IMODE(opened.st_mode) & 0o077
                    or _file_identity(initial) != _file_identity(opened)
                    or _file_identity(current) != _file_identity(opened)
                ):
                    _raise("PUBLISH_ROOT_INVALID")
                root_identity = _file_identity(opened)
            finally:
                os.close(root_fd)
        except PublisherError:
            raise
        except Exception:
            raise PublisherError("PUBLISH_ROOT_INVALID") from None
        self._root_dir = absolute
        self._root_identity = root_identity
        self._target_name = target_name
        self._allowed_schema_keys = allowed_schema_keys

    @property
    def allowed_schema_keys(self) -> frozenset:
        return self._allowed_schema_keys

    def publish(self, shape: object) -> dict:
        """Publish and return the independently reopened bundle."""

        if type(shape) is not SanitizedShape:
            _raise("PUBLISH_SHAPE_TYPE_INVALID")
        try:
            model = shape.to_model()
        except PublisherError:
            raise
        except Exception:
            raise PublisherError("PUBLISH_SHAPE_INVALID") from None
        except BaseException:
            raise PublisherError("PUBLISH_ABORTED") from None
        if type(model) is not dict:
            _raise("PUBLISH_SHAPE_SCHEMA_INVALID")
        bundle = _build_bundle(model, self._allowed_schema_keys)
        payload = _canonical_json(bundle) + b"\n"

        root_fd = -1
        staging_fd = -1
        staging_name: Optional[str] = None
        staging_identity: Optional[Tuple[int, int]] = None
        staging_created = False
        link_succeeded = False
        completed = False
        cleanup_failed = False
        failure: Optional[BaseException] = None
        reopened_bundle: Optional[dict] = None

        try:
            root_fd = self._open_root()
            if _lstat_at(root_fd, self._target_name) is not None:
                _raise("PUBLISH_TARGET_EXISTS")

            (
                staging_name,
                staging_fd,
                staging_identity,
            ) = self._open_staging(root_fd)
            staging_created = True
            try:
                _write_all(staging_fd, payload)
                os.fsync(staging_fd)
                staged_stat = os.fstat(staging_fd)
                if (
                    not stat.S_ISREG(staged_stat.st_mode)
                    or stat.S_IMODE(staged_stat.st_mode) != 0o600
                    or staged_stat.st_size != len(payload)
                    or _file_identity(staged_stat) != staging_identity
                ):
                    _raise("PUBLISH_STAGING_INVALID")
            except PublisherError:
                raise
            except Exception:
                raise PublisherError("PUBLISH_STAGING_WRITE_FAILED") from None

            if _lstat_at(root_fd, self._target_name) is not None:
                _raise("PUBLISH_TARGET_EXISTS")
            staged_stat = _lstat_at(root_fd, staging_name)
            if (
                staged_stat is None
                or not stat.S_ISREG(staged_stat.st_mode)
                or stat.S_IMODE(staged_stat.st_mode) != 0o600
                or staged_stat.st_size != len(payload)
                or _file_identity(staged_stat) != staging_identity
            ):
                _raise("PUBLISH_STAGING_INVALID")

            link_error: Optional[BaseException] = None
            try:
                os.link(
                    staging_name,
                    self._target_name,
                    src_dir_fd=root_fd,
                    dst_dir_fd=root_fd,
                    follow_symlinks=False,
                )
                link_succeeded = True
            except BaseException as error:
                link_error = error

            target_stat = _lstat_at(root_fd, self._target_name)
            if (
                target_stat is not None
                and stat.S_ISREG(target_stat.st_mode)
                and stat.S_IMODE(target_stat.st_mode) == 0o600
                and target_stat.st_size == len(payload)
                and _file_identity(target_stat) == staging_identity
            ):
                # The kernel commit may have succeeded before a cancellation or
                # wrapper fault was raised back into Python.
                link_succeeded = True
            elif link_error is not None:
                if isinstance(link_error, FileExistsError):
                    raise PublisherError("PUBLISH_TARGET_EXISTS") from None
                if isinstance(link_error, Exception):
                    raise PublisherError("PUBLISH_PROMOTION_FAILED") from None
                raise PublisherError("PUBLISH_ABORTED") from None
            else:
                _raise("PUBLISH_PROMOTION_INVALID")

            try:
                os.close(staging_fd)
            except OSError:
                cleanup_failed = True
            staging_fd = -1
            if cleanup_failed:
                _raise("PUBLISH_STAGING_CLEANUP_FAILED")

            if not self._unlink_if_owned(root_fd, staging_name, staging_identity):
                _raise("PUBLISH_STAGING_CLEANUP_FAILED")
            staging_created = False
            try:
                os.fsync(root_fd)
            except Exception:
                raise PublisherError("PUBLISH_DIRECTORY_SYNC_FAILED") from None

            reopened_bundle = self._reopen_and_validate(
                root_fd,
                self._target_name,
                staging_identity,
                payload,
            )
            completed = True
        except BaseException as error:
            failure = error
        finally:
            if staging_fd >= 0:
                try:
                    os.close(staging_fd)
                except OSError:
                    cleanup_failed = True
            if root_fd >= 0:
                if staging_created and staging_name is not None:
                    if staging_identity is None:
                        try:
                            os.unlink(staging_name, dir_fd=root_fd)
                        except FileNotFoundError:
                            pass
                        except OSError:
                            cleanup_failed = True
                    elif not self._unlink_if_owned(
                        root_fd,
                        staging_name,
                        staging_identity,
                    ):
                        cleanup_failed = True
                if staging_created or (not completed and link_succeeded):
                    try:
                        os.fsync(root_fd)
                    except OSError:
                        cleanup_failed = True
                try:
                    os.close(root_fd)
                except OSError:
                    cleanup_failed = True

        if failure is not None:
            if cleanup_failed:
                raise PublisherError("PUBLISH_CLEANUP_FAILED") from None
            if isinstance(failure, PublisherError):
                raise PublisherError(failure.code) from None
            if isinstance(failure, Exception):
                raise PublisherError("PUBLISH_INTERNAL_FAILURE") from None
            raise PublisherError("PUBLISH_ABORTED") from None
        if cleanup_failed:
            _raise("PUBLISH_CLEANUP_FAILED")
        if reopened_bundle is None:
            _raise("PUBLISH_INTERNAL_FAILURE")
        return reopened_bundle

    def _open_root(self) -> int:
        root_fd = -1
        try:
            if os.path.realpath(self._root_dir) != self._root_dir:
                _raise("PUBLISH_ROOT_INVALID")
            initial = os.lstat(self._root_dir)
            if not stat.S_ISDIR(initial.st_mode) or stat.S_ISLNK(initial.st_mode):
                _raise("PUBLISH_ROOT_INVALID")
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            flags |= getattr(os, "O_CLOEXEC", 0)
            root_fd = os.open(self._root_dir, flags)
            opened = os.fstat(root_fd)
            current = os.stat(self._root_dir, follow_symlinks=False)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or stat.S_IMODE(opened.st_mode) & 0o077
                or _file_identity(opened) != self._root_identity
                or _file_identity(initial) != _file_identity(opened)
                or _file_identity(current) != _file_identity(opened)
            ):
                _raise("PUBLISH_ROOT_INVALID")
            result = root_fd
            root_fd = -1
            return result
        except BaseException as error:
            cleanup_failed = False
            if root_fd >= 0:
                try:
                    os.close(root_fd)
                except OSError:
                    cleanup_failed = True
            if cleanup_failed:
                raise PublisherError("PUBLISH_ROOT_INVALID") from None
            if isinstance(error, PublisherError):
                raise PublisherError(error.code) from None
            if isinstance(error, Exception):
                raise PublisherError("PUBLISH_ROOT_INVALID") from None
            raise PublisherError("PUBLISH_ABORTED") from None

    @staticmethod
    def _open_staging(root_fd: int) -> Tuple[str, int, Tuple[int, int]]:
        for _ in range(_MAX_STAGING_ATTEMPTS):
            name = ".autocapture-shape-staging-" + secrets.token_hex(16)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            flags |= getattr(os, "O_CLOEXEC", 0)
            try:
                file_fd = os.open(name, flags, 0o600, dir_fd=root_fd)
            except FileExistsError:
                continue
            except Exception:
                raise PublisherError("PUBLISH_STAGING_CREATE_FAILED") from None
            try:
                os.fchmod(file_fd, 0o600)
                file_stat = os.fstat(file_fd)
                if (
                    not stat.S_ISREG(file_stat.st_mode)
                    or stat.S_IMODE(file_stat.st_mode) != 0o600
                    or file_stat.st_nlink != 1
                ):
                    _raise("PUBLISH_STAGING_INVALID")
                return name, file_fd, _file_identity(file_stat)
            except BaseException:
                try:
                    os.close(file_fd)
                except OSError:
                    pass
                try:
                    os.unlink(name, dir_fd=root_fd)
                except OSError:
                    pass
                raise
        _raise("PUBLISH_STAGING_CREATE_FAILED")

    @staticmethod
    def _unlink_if_owned(
        root_fd: int,
        name: str,
        expected_identity: Tuple[int, int],
    ) -> bool:
        try:
            file_stat = _lstat_at(root_fd, name)
            if file_stat is None:
                return True
            if (
                not stat.S_ISREG(file_stat.st_mode)
                or _file_identity(file_stat) != expected_identity
            ):
                return False
            os.unlink(name, dir_fd=root_fd)
            return True
        except OSError:
            return False

    def _reopen_and_validate(
        self,
        root_fd: int,
        target_name: str,
        expected_identity: Tuple[int, int],
        expected_payload: bytes,
    ) -> dict:
        flags = os.O_RDONLY | os.O_NOFOLLOW
        flags |= getattr(os, "O_CLOEXEC", 0)
        file_fd = -1
        try:
            file_fd = os.open(target_name, flags, dir_fd=root_fd)
            file_stat = os.fstat(file_fd)
            if (
                not stat.S_ISREG(file_stat.st_mode)
                or stat.S_IMODE(file_stat.st_mode) != 0o600
                or _file_identity(file_stat) != expected_identity
                or file_stat.st_size != len(expected_payload)
            ):
                _raise("PUBLISH_REOPEN_INVALID")
            payload = _read_exact(file_fd, len(expected_payload))
        except PublisherError:
            raise
        except Exception:
            raise PublisherError("PUBLISH_REOPEN_FAILED") from None
        finally:
            if file_fd >= 0:
                try:
                    os.close(file_fd)
                except OSError:
                    raise PublisherError("PUBLISH_REOPEN_FAILED") from None

        bundle = _strict_json_loads(payload)
        try:
            _validate_bundle(bundle, self._allowed_schema_keys)
            canonical = _canonical_json(bundle) + b"\n"
        except PublisherError:
            raise PublisherError("PUBLISH_REOPEN_INVALID") from None
        if payload != expected_payload or payload != canonical:
            _raise("PUBLISH_REOPEN_INVALID")
        return bundle
