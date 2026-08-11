"""Sanitized in-memory observation boundary for the offline Parser candidate."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Mapping

from .parser import ParserError, _safe_version_token


DEFAULT_MAX_DEPTH = 32
DEFAULT_MAX_NODES = 10_000
HARD_MAX_DEPTH = 64
HARD_MAX_NODES = 100_000
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_NON_TOKEN = re.compile(r"[^0-9a-z]+")
_SENSITIVE_FRAGMENTS = frozenset(
    {
        "request",
        "response",
        "header",
        "headers",
        "cookie",
        "cookies",
        "token",
        "authorization",
        "session",
        "password",
        "passwd",
        "secret",
        "credential",
        "credentials",
        "openid",
        "unionid",
        "signature",
    }
)


@dataclass(frozen=True)
class SanitizedObservationInput:
    """Validated, copied, in-memory payload bound to one Parser profile."""

    payload_family: str
    payload_version: str
    payload: Mapping[str, Any]
    max_depth: int = DEFAULT_MAX_DEPTH
    max_nodes: int = DEFAULT_MAX_NODES

    def __post_init__(self) -> None:
        _validate_limits(self.max_depth, self.max_nodes)
        if not _safe_version_token(self.payload_family) or not _safe_version_token(self.payload_version):
            raise ParserError("PARSER_VERSION_UNRESOLVED")
        copied, count = _sanitize_mapping(self.payload, self.max_depth, self.max_nodes)
        if count > self.max_nodes:
            raise ParserError("OBSERVATION_NODE_LIMIT")
        object.__setattr__(self, "payload", copied)

    @classmethod
    def from_mapping(
        cls,
        payload_family: str,
        payload_version: str,
        payload: Mapping[str, Any],
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
    ) -> "SanitizedObservationInput":
        """Build a sanitized envelope without reading files or external state."""

        return cls(payload_family, payload_version, payload, max_depth, max_nodes)

    def validate(self) -> "SanitizedObservationInput":
        """Re-check the copied payload in case a caller mutated a nested object."""

        _validate_limits(self.max_depth, self.max_nodes)
        if not _safe_version_token(self.payload_family) or not _safe_version_token(self.payload_version):
            raise ParserError("PARSER_VERSION_UNRESOLVED")
        _sanitize_mapping(self.payload, self.max_depth, self.max_nodes)
        return self


def _validate_limits(max_depth: int, max_nodes: int) -> None:
    if (
        type(max_depth) is not int
        or type(max_nodes) is not int
        or not 0 <= max_depth <= HARD_MAX_DEPTH
        or not 1 <= max_nodes <= HARD_MAX_NODES
    ):
        raise ParserError("OBSERVATION_LIMIT_CONFIG_INVALID")


def _sanitize_mapping(
    payload: Mapping[str, Any], max_depth: int, max_nodes: int
) -> tuple[dict[str, Any], int]:
    if not isinstance(payload, Mapping):
        raise ParserError("OBSERVATION_INPUT_INVALID")
    count = [0]
    copied = _sanitize_value(payload, 0, max_depth, max_nodes, count)
    if type(copied) is not dict:
        raise ParserError("OBSERVATION_INPUT_INVALID")
    return copied, count[0]


def _sanitize_value(
    value: Any,
    depth: int,
    max_depth: int,
    max_nodes: int,
    count: list[int],
) -> Any:
    count[0] += 1
    if count[0] > max_nodes:
        raise ParserError("OBSERVATION_NODE_LIMIT")
    if depth > max_depth:
        raise ParserError("OBSERVATION_DEPTH_LIMIT")
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, child in value.items():
            if type(key) is not str or _KEY.fullmatch(key) is None:
                raise ParserError("OBSERVATION_KEY_INVALID")
            if _is_sensitive_key(key):
                raise ParserError("OBSERVATION_SENSITIVE_KEY")
            copied[key] = _sanitize_value(child, depth + 1, max_depth, max_nodes, count)
        return copied
    if type(value) is list:
        return [
            _sanitize_value(child, depth + 1, max_depth, max_nodes, count)
            for child in value
        ]
    if type(value) is tuple or type(value) is set or type(value) is bytes:
        raise ParserError("OBSERVATION_VALUE_INVALID")
    if type(value) is float and not math.isfinite(value):
        raise ParserError("OBSERVATION_VALUE_INVALID")
    if type(value) in {type(None), bool, int, float, str}:
        return value
    raise ParserError("OBSERVATION_VALUE_INVALID")


def _is_sensitive_key(key: str) -> bool:
    normalized = _NON_TOKEN.sub("", key.casefold())
    return any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS)
