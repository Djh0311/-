"""Value-free JSON shape projection for the offline autocapture foundation.

This module deliberately has no mitmproxy, filesystem, logging, or network
capability.  It accepts an addon-owned ``bytearray`` and produces only a
sanitized structural model.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Set, Tuple


SCHEMA_VERSION = "autocapture-sanitized-shape/v1"
SANITIZED_DIGEST_PREFIX = "sha256:"
JSON_TYPES = frozenset(
    {"array", "boolean", "integer", "null", "number", "object", "string"}
)
RELATIONS = frozenset({"root", "object_member", "array_item"})

# The classifier is intentionally a closed four-state interface.  Consumers
# may retain only safe keys as JSON Pointer structure; no classification result
# is serialized into a shape, candidate table, or registry.
SENSITIVE = "SENSITIVE"
REGISTERED_SAFE = "REGISTERED_SAFE"
SAFE_UNREGISTERED = "SAFE_UNREGISTERED"
TRUE_UNKNOWN = "TRUE_UNKNOWN"

# Exact normalized keys only.  Generic business keys such as ``id``, ``name``,
# ``phone``, ``email``, ``address``, and ``account`` are intentionally absent.
SENSITIVE_KEY_TOKENS = frozenset(
    {
        "api_key",
        "api_secret",
        "authorization",
        "client_secret",
        "cookie",
        "set_cookie",
        "token",
        "access_token",
        "refresh_token",
        "session",
        "session_id",
        "password",
        "passwd",
        "secret",
        "secret_key",
        "credential",
        "captcha",
        "verification_code",
        "sms_code",
        "openid",
        "open_id",
        "unionid",
        "union_id",
        "user_id",
        "account_id",
        "device_id",
        "id_card",
        "idcard",
        "recipient_phone",
        "recipient_mobile",
        "recipient_name",
        "receiver_phone",
        "receiver_mobile",
        "receiver_name",
        "consignee_phone",
        "consignee_mobile",
        "consignee_name",
        "delivery_address",
        "home_address",
        "personal_email",
    }
)

SHAPE_ERROR_CODES = frozenset(
    {
        "INVALID_POLICY",
        "OBSERVATION_WINDOW_EXPIRED",
        "UNSUPPORTED_INPUT",
        "INVALID_UTF8",
        "INVALID_JSON",
        "DUPLICATE_KEY",
        "NONFINITE_NUMBER",
        "UNSUPPORTED_VALUE",
        "ROOT_SCALAR",
        "SENSITIVE_KEY",
        "SENSITIVE_VALUE",
        "UNKNOWN_SCHEMA_KEY",
        "NUMERIC_TOKEN_LIMIT",
        "MAX_DEPTH_EXCEEDED",
        "MAX_NODES_EXCEEDED",
        "MAX_PATHS_EXCEEDED",
        "MAX_EVENTS_EXCEEDED",
        "UNSUPPORTED_STRUCTURE",
        "INVALID_STAGE",
        "EMPTY_SHAPE",
        "INVALID_SHAPE_MODEL",
        "SANITIZED_DIGEST_MISMATCH",
    }
)

_ACRONYM_BOUNDARY = re.compile(r"([A-Z]+)([A-Z][a-z])")
_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_LETTER_DIGIT_BOUNDARY = re.compile(r"([A-Za-z])([0-9])")
_DIGIT_LETTER_BOUNDARY = re.compile(r"([0-9])([A-Za-z])")
_NON_TOKEN = re.compile(r"[^0-9a-z]+")
_SCHEMA_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,127}$")
_LONG_DIGIT_RUN = re.compile(r"\d{6,}")
_HEX_DYNAMIC = re.compile(r"^[0-9A-Fa-f]{24,}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_BAD_POINTER_ESCAPE = re.compile(r"~(?![01])")
_MAX_NUMERIC_TOKEN_LENGTH = 128
_SYNTHETIC_SENTINEL_WORDS = frozenset(("synthetic", "private", "canary"))
_SYNTHETIC_SECRET_WORDS = frozenset(
    ("secret", "sensitive", "token", "credential")
)
_HIGH_CONFIDENCE_SECRET_PREFIXES = (
    "-----begin ",
    "ghp_",
    "github_pat_",
    "rk_live_",
    "sk_live_",
    "sk_test_",
    "xoxb-",
    "xoxp-",
)
_SENSITIVE_SCHEMA_WORDS = frozenset(
    (
        "authorization",
        "captcha",
        "cookie",
        "credential",
        "credentials",
        "header",
        "headers",
        "openid",
        "passwd",
        "password",
        "raw",
        "secret",
        "session",
        "snippet",
        "token",
        "traceback",
        "unionid",
        "uid",
        "uuid",
        "guid",
    )
)
_SENSITIVE_SCHEMA_SEQUENCES = (
    ("access", "key"),
    ("access", "token"),
    ("account", "id"),
    ("api", "key"),
    ("api", "secret"),
    ("client", "secret"),
    ("consignee", "mobile"),
    ("consignee", "name"),
    ("consignee", "phone"),
    ("delivery", "address"),
    ("device", "id"),
    ("home", "address"),
    ("id", "card"),
    ("open", "id"),
    ("personal", "email"),
    ("private", "key"),
    ("receiver", "mobile"),
    ("receiver", "name"),
    ("receiver", "phone"),
    ("recipient", "mobile"),
    ("recipient", "name"),
    ("recipient", "phone"),
    ("refresh", "token"),
    ("session", "id"),
    ("set", "cookie"),
    ("sms", "code"),
    ("union", "id"),
    ("user", "id"),
    ("user", "guid"),
    ("user", "uid"),
    ("user", "uuid"),
    ("value", "hash"),
    ("verification", "code"),
    ("otp", "code"),
    ("oauth", "code"),
    ("sess", "id"),
    ("device", "guid"),
    ("device", "uid"),
    ("device", "uuid"),
    ("recipient", "tel"),
    ("receiver", "tel"),
    ("consignee", "tel"),
)
_SENSITIVE_SCHEMA_COLLAPSED_FRAGMENTS = (
    "accesskey",
    "accesstoken",
    "accountid",
    "apikey",
    "apisecret",
    "authorization",
    "captcha",
    "clientsecret",
    "consigneemobile",
    "consigneename",
    "consigneephone",
    "cookie",
    "credential",
    "deliveryaddress",
    "deviceid",
    "homeaddress",
    "idcard",
    "neighborcontent",
    "openid",
    "password",
    "passwd",
    "privatekey",
    "pwd",
    "personalemail",
    "rawerror",
    "rawpayload",
    "rawvalue",
    "receivermobile",
    "receivername",
    "receiverphone",
    "recipientmobile",
    "recipientname",
    "recipientphone",
    "refreshtoken",
    "secret",
    "session",
    "sessid",
    "setcookie",
    "smscode",
    "snippet",
    "token",
    "traceback",
    "unionid",
    "userid",
    "valuehash",
    "verificationcode",
    "oauthcode",
)
_SENSITIVE_SCHEMA_SINGULAR_WORDS = {
    "addresses": "address",
    "cards": "card",
    "codes": "code",
    "cookies": "cookie",
    "credentials": "credential",
    "emails": "email",
    "guids": "guid",
    "ids": "id",
    "keys": "key",
    "mobiles": "mobile",
    "names": "name",
    "passwords": "password",
    "phones": "phone",
    "secrets": "secret",
    "sessions": "session",
    "tels": "tel",
    "tokens": "token",
    "uids": "uid",
    "uuids": "uuid",
}
_SENSITIVE_SCHEMA_VERSION_ANCHORS = frozenset(
    (
        "account",
        "api",
        "client",
        "consignee",
        "delivery",
        "device",
        "home",
        "open",
        "personal",
        "receiver",
        "recipient",
        "union",
        "user",
        "verification",
    )
)


class ShapeProbeError(Exception):
    """A value-free failure carrying only a stable closed-set code."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        if code not in SHAPE_ERROR_CODES:
            raise ValueError("unknown shape error code")
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise ShapeProbeError(code)


def normalize_sensitive_key(key: str) -> str:
    """Normalize a JSON member name for exact sensitive-key matching."""

    separated = _ACRONYM_BOUNDARY.sub(r"\1_\2", key)
    separated = _CAMEL_BOUNDARY.sub(r"\1_\2", separated)
    separated = _LETTER_DIGIT_BOUNDARY.sub(r"\1_\2", separated)
    separated = _DIGIT_LETTER_BOUNDARY.sub(r"\1_\2", separated)
    lowered = separated.casefold()
    return _NON_TOKEN.sub("_", lowered).strip("_")


def _normalized_words(value: str) -> Tuple[str, ...]:
    separated = _ACRONYM_BOUNDARY.sub(r"\1_\2", value)
    separated = _CAMEL_BOUNDARY.sub(r"\1_\2", separated)
    separated = _LETTER_DIGIT_BOUNDARY.sub(r"\1_\2", separated)
    separated = _DIGIT_LETTER_BOUNDARY.sub(r"\1_\2", separated)
    lowered = separated.casefold()
    return tuple(token for token in _NON_TOKEN.split(lowered) if token)


def _is_sensitive_sentinel(value: str) -> bool:
    """Classify high-confidence secret/sentinel scalars without retaining them."""

    words = _normalized_words(value)
    word_set = frozenset(words)
    if _SYNTHETIC_SENTINEL_WORDS.issubset(word_set):
        return True
    if (
        "synthetic" in word_set
        and "canary" in word_set
        and word_set.intersection(_SYNTHETIC_SECRET_WORDS)
    ):
        return True
    folded = value.strip().casefold()
    if folded.startswith(_HIGH_CONFIDENCE_SECRET_PREFIXES):
        return True
    if folded.startswith("akia") and len(folded) == 20:
        return True
    if folded.startswith(("bearer ", "basic ")):
        return True
    if len(value) >= 24 and value.count(".") == 2:
        segments = value.split(".")
        if all(
            segment
            and all(
                character.isalnum() or character in "-_"
                for character in segment
            )
            for segment in segments
        ):
            return True
    return False


def _schema_key_has_sensitive_semantics(key: str) -> bool:
    """Recognize fixed high-confidence sensitive words anywhere in a key."""

    if _is_sensitive_sentinel(key):
        return True
    collapsed_letters = "".join(
        character
        for character in key.casefold()
        if "a" <= character <= "z"
    )
    if any(
        fragment in collapsed_letters
        for fragment in _SENSITIVE_SCHEMA_COLLAPSED_FRAGMENTS
    ):
        return True
    words_list: List[str] = []
    for word in _normalized_words(key):
        canonical = _SENSITIVE_SCHEMA_SINGULAR_WORDS.get(word, word)
        if (
            canonical.endswith("v")
            and canonical[:-1] in _SENSITIVE_SCHEMA_VERSION_ANCHORS
        ):
            words_list.extend((canonical[:-1], "v"))
        elif not canonical.isdigit():
            words_list.append(canonical)
    words = tuple(words_list)
    word_set = frozenset(words)
    if _SYNTHETIC_SENTINEL_WORDS.issubset(word_set):
        return True
    if normalize_sensitive_key(key) in SENSITIVE_KEY_TOKENS:
        return True
    if word_set.intersection(_SENSITIVE_SCHEMA_WORDS):
        return True
    for sequence in _SENSITIVE_SCHEMA_SEQUENCES:
        cursor = 0
        for word in words:
            if word == sequence[cursor]:
                cursor += 1
                if cursor == len(sequence):
                    return True
    return False


def _has_conservative_schema_key_structure(key: str) -> bool:
    """Accept only a static, bounded structural token, never a dynamic key."""

    if (
        not key
        or len(key) > 64
        or not key.isascii()
        or _contains_surrogate(key)
        or _contains_control_character(key)
        or _SCHEMA_KEY.fullmatch(key) is None
    ):
        return False
    digits = sum(character.isdigit() for character in key)
    if (
        (len(key) >= 12 and digits * 2 >= len(key))
        or _LONG_DIGIT_RUN.search(key) is not None
        or (
            _HEX_DYNAMIC.fullmatch(key) is not None
            and any(character.isdigit() for character in key)
        )
    ):
        return False
    return True


def classify_schema_key(key: object, registered_schema_keys: object) -> str:
    """Return the one closed key classification without observing any scalar.

    Sensitive semantics deliberately win before structure or membership.
    ``REGISTERED_SAFE`` is possible only for a conservatively valid key in an
    exact immutable registry.  A structurally safe key outside that registry is
    still permitted only as an event-local sanitized JSON Pointer token.
    """

    if type(key) is not str:
        return TRUE_UNKNOWN
    if _schema_key_has_sensitive_semantics(key):
        return SENSITIVE
    if not _has_conservative_schema_key_structure(key):
        return TRUE_UNKNOWN
    if type(registered_schema_keys) is not frozenset:
        return TRUE_UNKNOWN
    if key in registered_schema_keys:
        return REGISTERED_SAFE
    return SAFE_UNREGISTERED


def _contains_surrogate(text: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in text)


def _contains_control_character(text: str) -> bool:
    return any(ord(character) < 0x20 or ord(character) == 0x7F for character in text)


def _escape_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _child_pointer(parent: str, token: str) -> str:
    escaped = _escape_pointer_token(token)
    return "/" + escaped if parent == "" else parent + "/" + escaped


def _array_pointer(parent: str) -> str:
    return "/*" if parent == "" else parent + "/*"


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        if not math.isfinite(value):
            _fail("NONFINITE_NUMBER")
        return "number"
    if type(value) is str:
        if _contains_surrogate(value):
            _fail("UNSUPPORTED_VALUE")
        if _is_sensitive_sentinel(value):
            _fail("SENSITIVE_VALUE")
        return "string"
    if type(value) is dict:
        return "object"
    if type(value) is list:
        return "array"
    _fail("UNSUPPORTED_VALUE")
    raise AssertionError("unreachable")


def _strict_object(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    value: Dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail("DUPLICATE_KEY")
        value[key] = item
    return value


def _strict_float(token: str) -> float:
    if len(token) > _MAX_NUMERIC_TOKEN_LENGTH:
        _fail("NUMERIC_TOKEN_LIMIT")
    try:
        value = float(token)
    except (OverflowError, ValueError):
        _fail("NONFINITE_NUMBER")
    if not math.isfinite(value):
        _fail("NONFINITE_NUMBER")
    return 0.0


def _strict_int(token: str) -> int:
    if len(token) > _MAX_NUMERIC_TOKEN_LENGTH:
        _fail("NUMERIC_TOKEN_LIMIT")
    return 0


def _reject_constant(_token: str) -> None:
    _fail("NONFINITE_NUMBER")


def _decode_json(raw: bytearray) -> Any:
    if type(raw) is not bytearray:
        _fail("UNSUPPORTED_INPUT")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _fail("INVALID_UTF8")
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_int=_strict_int,
            parse_float=_strict_float,
            parse_constant=_reject_constant,
        )
    except ShapeProbeError:
        raise
    except RecursionError:
        _fail("MAX_DEPTH_EXCEEDED")
    except (json.JSONDecodeError, TypeError, ValueError):
        _fail("INVALID_JSON")
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class _SanitizedNode:
    path: str
    types: Tuple[str, ...]
    parent: Optional[str]
    relation: str
    observed_events: int
    cardinality_minimum: Optional[int]
    cardinality_maximum: Optional[int]

    def to_model(self, event_count: int) -> Dict[str, Any]:
        cardinality: Optional[Dict[str, int]]
        if self.cardinality_minimum is None:
            cardinality = None
        else:
            cardinality = {
                "minimum": self.cardinality_minimum,
                "maximum": self.cardinality_maximum,
            }
        return {
            "path": self.path,
            "types": list(self.types),
            "parent": self.parent,
            "relation": self.relation,
            "presence": {
                "observed_events": self.observed_events,
                "total_events": event_count,
            },
            "cardinality": cardinality,
        }


def _base_model(
    event_count: int, nodes: Tuple[_SanitizedNode, ...]
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "event_count": event_count,
        "nodes": [node.to_model(event_count) for node in nodes],
    }


def _canonical_digest(base_model: Mapping[str, Any]) -> str:
    try:
        canonical = json.dumps(
            base_model,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError):
        _fail("INVALID_SHAPE_MODEL")
    return SANITIZED_DIGEST_PREFIX + hashlib.sha256(canonical).hexdigest()


def _pointer_tokens(path: str) -> Optional[Tuple[str, ...]]:
    if path == "":
        return ()
    if not path.startswith("/") or _BAD_POINTER_ESCAPE.search(path) is not None:
        return None
    return tuple(
        token.replace("~1", "/").replace("~0", "~")
        for token in path[1:].split("/")
    )


@dataclass(frozen=True)
class SanitizedShape:
    """Immutable value-free model accepted by the shape publisher."""

    event_count: int
    nodes: Tuple[_SanitizedNode, ...]
    sanitized_shape_digest: str
    _allowed_schema_keys: frozenset = field(repr=False, compare=False)

    def _base_model(self) -> Dict[str, Any]:
        return _base_model(self.event_count, self.nodes)

    def recompute_digest(self) -> str:
        """Recompute the digest from the sanitized model with digest removed."""

        return _canonical_digest(self._base_model())

    def validate(self) -> None:
        """Fail closed unless all schema and digest invariants hold."""

        if (
            type(self._allowed_schema_keys) is not frozenset
            or not self._allowed_schema_keys
            or any(
                classify_schema_key(key, self._allowed_schema_keys)
                != REGISTERED_SAFE
                for key in self._allowed_schema_keys
            )
        ):
            _fail("INVALID_SHAPE_MODEL")
        if type(self.event_count) is not int or self.event_count <= 0:
            _fail("INVALID_SHAPE_MODEL")
        if type(self.nodes) is not tuple or not self.nodes:
            _fail("INVALID_SHAPE_MODEL")
        if not _DIGEST.fullmatch(self.sanitized_shape_digest):
            _fail("INVALID_SHAPE_MODEL")

        paths: Set[str] = set()
        previous_path: Optional[str] = None
        root_count = 0
        for node in self.nodes:
            if type(node) is not _SanitizedNode:
                _fail("INVALID_SHAPE_MODEL")
            pointer_tokens = _pointer_tokens(node.path)
            if pointer_tokens is None or node.path in paths:
                _fail("INVALID_SHAPE_MODEL")
            if any(
                token != "*"
                and classify_schema_key(token, self._allowed_schema_keys)
                not in (REGISTERED_SAFE, SAFE_UNREGISTERED)
                for token in pointer_tokens
            ):
                _fail("INVALID_SHAPE_MODEL")
            if previous_path is not None and node.path <= previous_path:
                _fail("INVALID_SHAPE_MODEL")
            paths.add(node.path)
            previous_path = node.path

            if (
                type(node.types) is not tuple
                or not node.types
                or tuple(sorted(set(node.types))) != node.types
                or not set(node.types).issubset(JSON_TYPES)
            ):
                _fail("INVALID_SHAPE_MODEL")
            if node.relation not in RELATIONS:
                _fail("INVALID_SHAPE_MODEL")
            if node.path == "":
                root_count += 1
                if node.parent is not None or node.relation != "root":
                    _fail("INVALID_SHAPE_MODEL")
            elif (
                type(node.parent) is not str
                or node.relation == "root"
                or _pointer_tokens(node.parent) is None
            ):
                _fail("INVALID_SHAPE_MODEL")
            if node.path != "":
                last_token = pointer_tokens[-1]
                if (
                    (node.relation == "array_item" and last_token != "*")
                    or (node.relation == "object_member" and last_token == "*")
                ):
                    _fail("INVALID_SHAPE_MODEL")
            if (
                type(node.observed_events) is not int
                or node.observed_events <= 0
                or node.observed_events > self.event_count
            ):
                _fail("INVALID_SHAPE_MODEL")

            if node.cardinality_minimum is None:
                if node.cardinality_maximum is not None:
                    _fail("INVALID_SHAPE_MODEL")
            elif (
                type(node.cardinality_minimum) is not int
                or type(node.cardinality_maximum) is not int
                or node.cardinality_minimum < 0
                or node.cardinality_maximum < node.cardinality_minimum
                or not set(node.types).intersection({"array", "object"})
            ):
                _fail("INVALID_SHAPE_MODEL")

        if root_count != 1:
            _fail("INVALID_SHAPE_MODEL")
        for node in self.nodes:
            if node.path != "" and node.parent not in paths:
                _fail("INVALID_SHAPE_MODEL")
        if self.recompute_digest() != self.sanitized_shape_digest:
            _fail("SANITIZED_DIGEST_MISMATCH")

    def to_model(self) -> Dict[str, Any]:
        """Return the exact public v1 model as a fresh dictionary."""

        self.validate()
        model = self._base_model()
        model["sanitized_shape_digest"] = self.sanitized_shape_digest
        return model


@dataclass
class _StageNodeBuilder:
    path: str
    types: Set[str]
    parent: Optional[str]
    relation: str
    cardinality_minimum: Optional[int] = None
    cardinality_maximum: Optional[int] = None

    def observe(self, value_type: str, cardinality: Optional[int]) -> None:
        self.types.add(value_type)
        if cardinality is None:
            return
        if self.cardinality_minimum is None:
            self.cardinality_minimum = cardinality
            self.cardinality_maximum = cardinality
            return
        self.cardinality_minimum = min(self.cardinality_minimum, cardinality)
        self.cardinality_maximum = max(self.cardinality_maximum, cardinality)


@dataclass(frozen=True)
class _StagedNode:
    path: str
    types: Tuple[str, ...]
    parent: Optional[str]
    relation: str
    cardinality_minimum: Optional[int]
    cardinality_maximum: Optional[int]


@dataclass(frozen=True)
class StagedShape:
    """Attempt-local sanitized projection that has not been committed."""

    nodes: Tuple[_StagedNode, ...]
    node_count: int
    _owner: object = field(repr=False, compare=False)
    _epoch: int
    _token: object = field(repr=False, compare=False)


@dataclass(frozen=True)
class _AggregateNode:
    path: str
    types: Tuple[str, ...]
    parent: Optional[str]
    relation: str
    observed_events: int
    cardinality_minimum: Optional[int]
    cardinality_maximum: Optional[int]


class ShapeAccumulator:
    """Two-phase, bounded accumulator for value-free JSON event shapes."""

    def __init__(
        self,
        *,
        max_depth: int,
        max_nodes: int,
        max_paths: int,
        max_events: int,
        allowed_schema_keys: frozenset,
        clock: Callable[[], float],
        deadline: float,
    ) -> None:
        budgets = (max_depth, max_nodes, max_paths, max_events)
        if any(type(value) is not int or value <= 0 for value in budgets):
            _fail("INVALID_POLICY")
        if (
            type(allowed_schema_keys) is not frozenset
            or not allowed_schema_keys
            or any(
                classify_schema_key(key, allowed_schema_keys) != REGISTERED_SAFE
                for key in allowed_schema_keys
            )
        ):
            _fail("INVALID_POLICY")
        if not callable(clock):
            _fail("INVALID_POLICY")
        if type(deadline) not in (int, float):
            _fail("INVALID_POLICY")
        parsed_deadline = float(deadline)
        if not math.isfinite(parsed_deadline):
            _fail("INVALID_POLICY")

        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.max_paths = max_paths
        self.max_events = max_events
        self.allowed_schema_keys = allowed_schema_keys
        self._clock = clock
        self.deadline = parsed_deadline
        self._owner = object()
        self._epoch = 0
        self._event_count = 0
        self._nodes: Dict[str, _AggregateNode] = {}
        self._consumed_stage_tokens: Set[object] = set()

    @property
    def event_count(self) -> int:
        return self._event_count

    def _now(self) -> float:
        try:
            raw_value = self._clock()
            if type(raw_value) not in (int, float):
                _fail("OBSERVATION_WINDOW_EXPIRED")
            value = float(raw_value)
        except ShapeProbeError:
            raise
        except Exception:
            _fail("OBSERVATION_WINDOW_EXPIRED")
        if not math.isfinite(value):
            _fail("OBSERVATION_WINDOW_EXPIRED")
        return value

    def _check_window(self) -> None:
        if self._now() >= self.deadline:
            _fail("OBSERVATION_WINDOW_EXPIRED")

    def stage_json_bytes(self, raw: bytearray) -> StagedShape:
        """Parse and project one event without changing committed state."""

        self._check_window()
        root = _decode_json(raw)
        if type(root) not in (dict, list):
            _fail("ROOT_SCALAR")

        builders: Dict[str, _StageNodeBuilder] = {}
        node_count = 0
        stack: List[Tuple[Any, str, Optional[str], str, int]] = [
            (root, "", None, "root", 0)
        ]

        while stack:
            self._check_window()
            value, path, parent, relation, depth = stack.pop()
            if depth > self.max_depth:
                _fail("MAX_DEPTH_EXCEEDED")
            node_count += 1
            if node_count > self.max_nodes:
                _fail("MAX_NODES_EXCEEDED")

            value_type = _json_type(value)
            cardinality = len(value) if value_type in {"array", "object"} else None
            builder = builders.get(path)
            if builder is None:
                if len(builders) >= self.max_paths:
                    _fail("MAX_PATHS_EXCEEDED")
                builder = _StageNodeBuilder(
                    path=path,
                    types=set(),
                    parent=parent,
                    relation=relation,
                )
                builders[path] = builder
            elif builder.parent != parent or builder.relation != relation:
                _fail("UNSUPPORTED_STRUCTURE")
            builder.observe(value_type, cardinality)

            if value_type == "object":
                children: List[Tuple[Any, str, Optional[str], str, int]] = []
                for key, child in value.items():
                    key_classification = classify_schema_key(
                        key,
                        self.allowed_schema_keys,
                    )
                    if key_classification == SENSITIVE:
                        _fail("SENSITIVE_KEY")
                    if key_classification == TRUE_UNKNOWN:
                        _fail("UNKNOWN_SCHEMA_KEY")
                    children.append(
                        (
                            child,
                            _child_pointer(path, key),
                            path,
                            "object_member",
                            depth + 1,
                        )
                    )
                stack.extend(reversed(children))
            elif value_type == "array":
                child_path = _array_pointer(path)
                stack.extend(
                    (child, child_path, path, "array_item", depth + 1)
                    for child in reversed(value)
                )

        self._check_window()
        staged_nodes = tuple(
            _StagedNode(
                path=builder.path,
                types=tuple(sorted(builder.types)),
                parent=builder.parent,
                relation=builder.relation,
                cardinality_minimum=builder.cardinality_minimum,
                cardinality_maximum=builder.cardinality_maximum,
            )
            for builder in sorted(builders.values(), key=lambda item: item.path)
        )
        return StagedShape(
            nodes=staged_nodes,
            node_count=node_count,
            _owner=self._owner,
            _epoch=self._epoch,
            _token=object(),
        )

    def commit(self, staged: StagedShape) -> None:
        """Atomically merge one successfully staged event."""

        if (
            type(staged) is not StagedShape
            or staged._owner is not self._owner
            or staged._epoch != self._epoch
            or staged._token in self._consumed_stage_tokens
        ):
            _fail("INVALID_STAGE")
        self._check_window()
        next_event_count = self._event_count + 1
        if next_event_count > self.max_events:
            _fail("MAX_EVENTS_EXCEEDED")

        next_nodes = dict(self._nodes)
        for incoming in staged.nodes:
            current = next_nodes.get(incoming.path)
            if current is None:
                if len(next_nodes) >= self.max_paths:
                    _fail("MAX_PATHS_EXCEEDED")
                next_nodes[incoming.path] = _AggregateNode(
                    path=incoming.path,
                    types=incoming.types,
                    parent=incoming.parent,
                    relation=incoming.relation,
                    observed_events=1,
                    cardinality_minimum=incoming.cardinality_minimum,
                    cardinality_maximum=incoming.cardinality_maximum,
                )
                continue
            if (
                current.parent != incoming.parent
                or current.relation != incoming.relation
            ):
                _fail("UNSUPPORTED_STRUCTURE")
            minimums = [
                value
                for value in (
                    current.cardinality_minimum,
                    incoming.cardinality_minimum,
                )
                if value is not None
            ]
            maximums = [
                value
                for value in (
                    current.cardinality_maximum,
                    incoming.cardinality_maximum,
                )
                if value is not None
            ]
            next_nodes[incoming.path] = replace(
                current,
                types=tuple(sorted(set(current.types).union(incoming.types))),
                observed_events=current.observed_events + 1,
                cardinality_minimum=min(minimums) if minimums else None,
                cardinality_maximum=max(maximums) if maximums else None,
            )

        self._check_window()
        self._nodes = next_nodes
        self._event_count = next_event_count
        self._consumed_stage_tokens.add(staged._token)

    def clear(self) -> None:
        """Drop every aggregate and invalidate all previously staged events."""

        self._nodes = {}
        self._event_count = 0
        self._consumed_stage_tokens = set()
        self._epoch += 1

    def build(self) -> SanitizedShape:
        """Build and validate the immutable sanitized aggregate."""

        if self._event_count <= 0:
            _fail("EMPTY_SHAPE")
        nodes = tuple(
            _SanitizedNode(
                path=node.path,
                types=node.types,
                parent=node.parent,
                relation=node.relation,
                observed_events=node.observed_events,
                cardinality_minimum=node.cardinality_minimum,
                cardinality_maximum=node.cardinality_maximum,
            )
            for node in sorted(self._nodes.values(), key=lambda item: item.path)
        )
        digest = _canonical_digest(_base_model(self._event_count, nodes))
        shape = SanitizedShape(
            event_count=self._event_count,
            nodes=nodes,
            sanitized_shape_digest=digest,
            _allowed_schema_keys=self.allowed_schema_keys,
        )
        shape.validate()
        return shape


__all__ = [
    "REGISTERED_SAFE",
    "SAFE_UNREGISTERED",
    "SCHEMA_VERSION",
    "SENSITIVE",
    "SENSITIVE_KEY_TOKENS",
    "SHAPE_ERROR_CODES",
    "SanitizedShape",
    "ShapeAccumulator",
    "ShapeProbeError",
    "StagedShape",
    "TRUE_UNKNOWN",
    "classify_schema_key",
    "normalize_sensitive_key",
]
