"""Closed, value-free policy validation for the capture addon.

The endpoint selector is intentionally atomic: a rule is one immutable
``(method, host, path)`` tuple, never three independently combinable
allowlists.  Validation and selection return only stable control-plane codes;
they never echo rejected request metadata.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import FrozenSet, Tuple, Union

from autocapture.shape import REGISTERED_SAFE, classify_schema_key


ImmutableStrings = Union[Tuple[str, ...], FrozenSet[str]]
ImmutableStatuses = Union[Tuple[int, ...], FrozenSet[int]]
ImmutableEndpointRules = Union[Tuple["EndpointRule", ...], FrozenSet["EndpointRule"]]


MAX_ALLOWED_ENDPOINT_RULES = 32
MAX_ALLOWED_STATUSES = 32
MAX_ALLOWED_CONTENT_TYPES = 16
MAX_ALLOWED_JSON_KEYS = 512
HARD_MAX_BODY_BYTES = 8 * 1024 * 1024
HARD_MAX_TOTAL_BODY_BYTES = 64 * 1024 * 1024
HARD_MAX_JSON_DEPTH = 64
HARD_MAX_JSON_NODES = 100_000
HARD_MAX_SHAPE_PATHS = 10_000
HARD_MAX_EVENTS = 128
HARD_MAX_OBSERVATION_WINDOW_SECONDS = 300.0
HARD_MAX_LEASE_SECONDS = 30.0


ENDPOINT_MATCH = "MATCH"
ENDPOINT_MISMATCH = "MISMATCH"
ENDPOINT_METADATA_INVALID = "METADATA_INVALID"


_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_HTTP_TOKEN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Z]+$")
_STATIC_PATH_SEGMENT = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_MEDIA_TOKEN = re.compile(r"^[!#$%&'+.^_`|~0-9a-z-]+$")


class PolicyError(ValueError):
    """A policy failure whose public representation is a closed code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _is_immutable_collection(value: object) -> bool:
    return type(value) in (tuple, frozenset)


def _has_duplicate_tuple_items(value: object) -> bool:
    return type(value) is tuple and len(value) != len(set(value))


def _is_positive_int(value: object, hard_max: int) -> bool:
    return type(value) is int and 0 < value <= hard_max


def _is_positive_seconds(value: object, hard_max: float) -> bool:
    if type(value) not in (int, float):
        return False
    number = float(value)
    return math.isfinite(number) and 0.0 < number <= hard_max


def _valid_http_method(method: object) -> bool:
    if type(method) is not str:
        return False
    if (
        not method
        or len(method) > 32
        or not method.isascii()
        or method != method.upper()
        or _HTTP_TOKEN.fullmatch(method) is None
    ):
        return False
    return any("A" <= character <= "Z" for character in method)


def _valid_exact_host(host: object) -> bool:
    if type(host) is not str:
        return False
    if not host or len(host) > 253 or not host.isascii() or host != host.lower():
        return False
    if any(marker in host for marker in ("*", "://", "/", "\\", "?", "#", "@", ":", ";")):
        return False
    if host.startswith(".") or host.endswith("."):
        return False
    labels = host.split(".")
    if all(label.isdigit() for label in labels):
        return False
    return all(_HOST_LABEL.fullmatch(label) is not None for label in labels)


def _valid_static_path(path: object) -> bool:
    """Accept one bounded, canonical, non-root static path template only."""

    if type(path) is not str:
        return False
    if (
        not path
        or len(path) > 512
        or not path.isascii()
        or not path.startswith("/")
        or path == "/"
        or path.endswith("/")
        or "//" in path
    ):
        return False
    if any(marker in path for marker in ("?", "#", "%", "\\", "*", "{", "}", "[", "]", ":")):
        return False
    segments = path[1:].split("/")
    return all(
        segment not in (".", "..")
        and not segment.isdigit()
        and _STATIC_PATH_SEGMENT.fullmatch(segment) is not None
        for segment in segments
    )


def _valid_exact_content_type(content_type: object) -> bool:
    if type(content_type) is not str:
        return False
    if (
        not content_type
        or not content_type.isascii()
        or content_type != content_type.lower()
        or content_type.count("/") != 1
        or "*" in content_type
        or ";" in content_type
        or any(character.isspace() for character in content_type)
    ):
        return False
    media_type, media_subtype = content_type.split("/", 1)
    tokens_valid = (
        _MEDIA_TOKEN.fullmatch(media_type) is not None
        and _MEDIA_TOKEN.fullmatch(media_subtype) is not None
    )
    return tokens_valid and (
        media_subtype == "json" or media_subtype.endswith("+json")
    )


@dataclass(frozen=True)
class EndpointRule:
    """One exact request tuple eligible to reach response metadata gates."""

    method: str
    host: str
    path: str

    def validated(self) -> "EndpointRule":
        if not _valid_http_method(self.method):
            raise PolicyError("POLICY_ENDPOINT_METHOD_INVALID")
        if not _valid_exact_host(self.host):
            raise PolicyError("POLICY_ENDPOINT_HOST_INVALID")
        if not _valid_static_path(self.path):
            raise PolicyError("POLICY_ENDPOINT_PATH_INVALID")
        return self


@dataclass(frozen=True)
class CapturePolicy:
    """Immutable endpoint rules and resource bounds for one observation window."""

    endpoint_rules: ImmutableEndpointRules
    allowed_statuses: ImmutableStatuses
    allowed_content_types: ImmutableStrings
    allowed_json_keys: ImmutableStrings
    max_body_bytes: int
    max_total_body_bytes: int
    max_json_depth: int
    max_json_nodes: int
    max_shape_paths: int
    max_events: int
    observation_window_seconds: float
    max_lease_seconds: float

    def validated(self) -> "CapturePolicy":
        """Return this policy after closed validation, otherwise raise."""

        if not _is_immutable_collection(self.endpoint_rules) or not self.endpoint_rules:
            raise PolicyError("POLICY_ENDPOINT_RULE_SET_INVALID")
        if len(self.endpoint_rules) > MAX_ALLOWED_ENDPOINT_RULES:
            raise PolicyError("POLICY_ENDPOINT_RULE_SET_LIMIT")
        if not all(type(rule) is EndpointRule for rule in self.endpoint_rules):
            raise PolicyError("POLICY_ENDPOINT_RULE_INVALID")
        for rule in self.endpoint_rules:
            rule.validated()
        if _has_duplicate_tuple_items(self.endpoint_rules):
            raise PolicyError("POLICY_ENDPOINT_RULE_SET_DUPLICATE")

        if not _is_immutable_collection(self.allowed_statuses) or not self.allowed_statuses:
            raise PolicyError("POLICY_STATUS_SET_INVALID")
        if len(self.allowed_statuses) > MAX_ALLOWED_STATUSES:
            raise PolicyError("POLICY_STATUS_SET_LIMIT")
        if not all(type(status) is int and 100 <= status <= 599 for status in self.allowed_statuses):
            raise PolicyError("POLICY_STATUS_INVALID")
        if _has_duplicate_tuple_items(self.allowed_statuses):
            raise PolicyError("POLICY_STATUS_SET_DUPLICATE")

        if (
            not _is_immutable_collection(self.allowed_content_types)
            or not self.allowed_content_types
        ):
            raise PolicyError("POLICY_CONTENT_TYPE_SET_INVALID")
        if len(self.allowed_content_types) > MAX_ALLOWED_CONTENT_TYPES:
            raise PolicyError("POLICY_CONTENT_TYPE_SET_LIMIT")
        if not all(
            _valid_exact_content_type(content_type)
            for content_type in self.allowed_content_types
        ):
            raise PolicyError("POLICY_CONTENT_TYPE_INVALID")
        if _has_duplicate_tuple_items(self.allowed_content_types):
            raise PolicyError("POLICY_CONTENT_TYPE_SET_DUPLICATE")

        if (
            not _is_immutable_collection(self.allowed_json_keys)
            or not self.allowed_json_keys
        ):
            raise PolicyError("POLICY_JSON_KEY_SET_INVALID")
        if len(self.allowed_json_keys) > MAX_ALLOWED_JSON_KEYS:
            raise PolicyError("POLICY_JSON_KEY_SET_LIMIT")
        if not all(type(key) is str for key in self.allowed_json_keys):
            raise PolicyError("POLICY_JSON_KEY_INVALID")
        if _has_duplicate_tuple_items(self.allowed_json_keys):
            raise PolicyError("POLICY_JSON_KEY_SET_DUPLICATE")
        registered_keys = frozenset(self.allowed_json_keys)
        if not all(
            classify_schema_key(key, registered_keys) == REGISTERED_SAFE
            for key in self.allowed_json_keys
        ):
            raise PolicyError("POLICY_JSON_KEY_INVALID")

        integer_bounds = (
            (self.max_body_bytes, HARD_MAX_BODY_BYTES),
            (self.max_total_body_bytes, HARD_MAX_TOTAL_BODY_BYTES),
            (self.max_json_depth, HARD_MAX_JSON_DEPTH),
            (self.max_json_nodes, HARD_MAX_JSON_NODES),
            (self.max_shape_paths, HARD_MAX_SHAPE_PATHS),
            (self.max_events, HARD_MAX_EVENTS),
        )
        if not all(_is_positive_int(value, hard_max) for value, hard_max in integer_bounds):
            raise PolicyError("POLICY_INTEGER_BOUND_INVALID")
        if self.max_total_body_bytes < self.max_body_bytes:
            raise PolicyError("POLICY_TOTAL_BODY_BOUND_INVALID")
        if self.max_shape_paths > self.max_json_nodes:
            raise PolicyError("POLICY_SHAPE_BOUND_INVALID")

        if not _is_positive_seconds(
            self.observation_window_seconds,
            HARD_MAX_OBSERVATION_WINDOW_SECONDS,
        ):
            raise PolicyError("POLICY_WINDOW_INVALID")
        if not _is_positive_seconds(self.max_lease_seconds, HARD_MAX_LEASE_SECONDS):
            raise PolicyError("POLICY_LEASE_TTL_INVALID")
        if float(self.max_lease_seconds) > float(self.observation_window_seconds):
            raise PolicyError("POLICY_LEASE_WINDOW_INVALID")
        return self

    def select_endpoint(self, method: object, host: object, path: object) -> str:
        """Classify one request tuple without normalizing or retaining it."""

        if not (
            _valid_http_method(method)
            and _valid_exact_host(host)
            and _valid_static_path(path)
        ):
            return ENDPOINT_METADATA_INVALID
        candidate = EndpointRule(method, host, path)
        if candidate in self.endpoint_rules:
            return ENDPOINT_MATCH
        return ENDPOINT_MISMATCH

    def allows_status(self, status: object) -> bool:
        """Return true only for an exact integer HTTP status match."""

        return type(status) is int and status in self.allowed_statuses

    def allows_content_type(self, content_type: object) -> bool:
        """Return true only for the complete allowlisted media type."""

        return type(content_type) is str and content_type in self.allowed_content_types
