"""One bounded, developer-operated P26 identification window.

No transport is started here. Routing catalogs contain only necessary metadata;
unselected bodies never enter this object. Selected bodies are held briefly in
memory, checked for sensitive keys before identity/shape, and cleared on close.
No endpoint, payload family, unit or currency is supplied by a fixture.
"""

from __future__ import annotations

import json
import math
import re
import time
import unicodedata
import zlib
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4
from urllib.parse import unquote

from parser_candidate.envelope import _is_sensitive_key
from .observation_time import observation_time


MAX_BODY = 1024 * 1024
MAX_TOTAL = 4 * MAX_BODY
MAX_RESPONSES = 8
MAX_CALLBACKS = 64
MAX_DOMAINS = 8
MAX_MONITORING_DOMAINS = 64
MAX_ROUTES = 16
MAX_MONITORING_ROUTES = 128
MAX_NODES = 40000
MAX_SHAPE = 4096
CURRENT_ROUTE_SUFFIXES = frozenset({"meituan.com", "meituan.net", "dianping.com"})
SENSITIVE_CATEGORIES = ("CREDENTIAL_KEY", "SESSION_KEY", "PERSONAL_KEY", "TRANSPORT_KEY", "UNCLASSIFIED_KEY")
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_HOST = re.compile(r"^(?=.{1,253}$)[a-z0-9.-]+$")
_JSON_NUMBER = re.compile(rb"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_PRIVATE = (
    "userid", "userinfo", "userlocation", "useraddress", "userphone",
    "accountid", "recipient", "receiver", "shippingaddress", "deliveryaddress",
    "orderinfo", "orderid", "paymentinfo", "mobilephone", "phonenumber",
    "username", "userprofile", "useremail", "useraccount", "usercontact",
    "accountprofile", "accountphone", "accountemail", "idcard", "passport",
    "bankaccount", "wechatid", "chatcontent", "messagetext", "apikey", "privatekey",
)
_PROBE_FIELDS = frozenset({
    "id", "name", "title", "price", "minprice", "originalprice", "originprice",
    "saleprice", "currentprice", "activityprice", "discountprice", "unit",
    "currency", "currencycode", "poiid", "poiname", "shopid", "shopname",
    "storeid", "storename", "productid", "productname", "foodid", "foodname",
    "spuid", "skuid", "skuname", "categoryid", "categoryname", "tagname",
})
STATUS_CODES = frozenset({
    "P26_IDENTIFICATION_NOT_STARTED", "P26_ROUTING_IDENTIFICATION",
    "P26_TARGET_SHAPE_OBSERVED", "P26_TARGET_NOT_MATCHED",
    "P26_IDENTIFICATION_CLOSED", "P26_IDENTIFICATION_EXCEPTION", "P26_CLOCK_INVALID",
    "P26_WINDOW_TIMEOUT", "P26_ROUTING_BUDGET", "P26_CALLBACK_BUDGET",
    "P26_RESPONSE_COUNT_LIMIT", "P26_RESPONSE_SIZE_LIMIT", "P26_RESPONSE_PROCESSING_TIMEOUT", "P26_TOTAL_SIZE_LIMIT",
    "P26_ENCODING_INVALID", "P26_ENCODING_UNSUPPORTED", "P26_STRUCTURE_INVALID",
    "P26_STRUCTURE_BUDGET", "P26_SENSITIVE_INPUT", "P26_BUSINESS_JSON_INVALID",
    "P26_RECEIVER_SETUP_FAILED", "P26_RECEIVER_SETUP_TIMEOUT", "P26_RECEIVER_LOST", "P26_START_NOT_REQUESTED",
    "P26_CANCELLED", "P26_HOST_EXCEPTION", "P26_HOST_CLOSED", "P26_ACTIVATION_FAILED",
    "P26_CONNECTION_BUDGET", "P26_STREAM_PID_UNCONFIRMED", "P26_STREAM_COUNT_LIMIT",
    "P26_DIAGNOSTIC_OUTPUT_FAILED",
    "P26_FIELD_LAYOUT_OBSERVED",
    "P26_FORWARDING_EXCEPTION", "P26_FORWARDING_ASYNC_EXCEPTION", "P26_FORWARDING_ENGINE_ERROR",
    "P26_FORWARDING_CONNECT_FAILED", "P26_FORWARDING_CLIENT_TLS_FAILED",
    "P26_FORWARDING_SERVER_TLS_FAILED", "P26_FORWARDING_HTTP_FAILED",
    "P26_RESULT_MAPPING_INVALID", "P26_RESULT_SOURCE_ASSOCIATION_INVALID",
    "P26_RESULT_EVENT_SET_INVALID", "P26_RESULT_PRICE_RULE_CHANGED",
    "P26_RESULT_PROFILE_INVALID", "P26_RESULT_EVENT_SET_EXPIRED",
    "P26_RESULT_PUBLISHED", "P26_RESULT_CLOSED", "P26_RESULT_ASSEMBLY_FAILED",
    "P26_RESULT_NOT_STARTED", "P26_RESULT_RECEIVING", "P26_RESULT_PARSE_FAILED", "P26_RESULT_PUBLISH_FAILED",
})


class IdentificationError(ValueError):
    def __init__(self, code: str, *, category: str | None = None):
        self.code = code
        self.category = category if category in SENSITIVE_CATEGORIES else "UNCLASSIFIED_KEY"
        super().__init__(code)


def structure_budget_error(dimension, observed, stage):
    from .p26_structure_budget import make_detail
    error = IdentificationError('P26_STRUCTURE_BUDGET')
    error.structure_budget = make_detail(dimension, observed, stage)
    return error


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", value).casefold())


def _private_key(key: str) -> bool:
    name = _normalized(key)
    return (_is_sensitive_key(name) or any(term in name for term in _PRIVATE)
            or name in {"user", "users", "account", "accounts", "profile", "profiles"})


def _sensitive_category(key: str) -> str:
    name = _normalized(key)
    if any(term in name for term in ("cookie", "token", "authorization", "password", "passwd",
                                    "secret", "credential", "openid", "unionid", "signature", "apikey", "privatekey")):
        return "CREDENTIAL_KEY"
    if "session" in name:
        return "SESSION_KEY"
    if any(term in name for term in ("request", "response", "header")):
        return "TRANSPORT_KEY"
    if _private_key(key):
        return "PERSONAL_KEY"
    return "UNCLASSIFIED_KEY"


def _shape_key(key: str) -> str:
    # Numbers, non-field strings, long numeric IDs and UUID-like dictionary
    # keys are never exported as field definitions or value hashes.
    if _FIELD.fullmatch(key) and not re.search(r"[0-9]{7,}", key):
        return key
    return "<dynamic>"


def _private_route(path: str) -> bool:
    path = unicodedata.normalize("NFKC", unquote(path, errors="strict"))
    segments = {_normalized(segment) for segment in path.split("/")}
    return _private_key(path) or bool(segments & {
        "user", "users", "account", "accounts", "address", "addresses",
        "order", "orders", "payment", "payments", "session", "sessions",
        "login", "logout", "auth", "credential", "credentials",
        "location", "geolocation", "position", "profile", "profiles", "wallet",
        "chat", "message", "messages", "checkout", "device",
    })


def route_template(path: str) -> str:
    path = path.partition("?")[0].partition("#")[0]
    segments = path.split("/")[:16]
    return "/".join(
        part if (not part or re.fullmatch(r"[A-Za-z_-]{1,32}", part)
                 or (re.fullmatch(r"v[0-9]{1,2}", part) and index + 1 < len(segments)
                     and segments[index + 1] in {"weapp", "api", "poi", "shop", "abtest"}))
        else "<dynamic>" for index, part in enumerate(segments)
    )[:512]


def key_only_layout(body: bytes, *, restricted_fields: list | None = None,
                    public_paths: frozenset[str] = frozenset(), public_values: list | None = None,
                    public_failures: list | None = None,
                    max_public_paths: int = 128) -> tuple[list[dict], dict[str, int]]:
    """Read keys/types only. Scalar values and private subtree keys are opaque."""
    if type(body) is not bytes or len(body) > MAX_BODY:
        raise IdentificationError("P26_RESPONSE_SIZE_LIMIT")
    if (type(max_public_paths) is not int or not 1 <= max_public_paths <= 1024
            or type(public_paths) is not frozenset or len(public_paths) > max_public_paths
            or any(type(path) is not str or not path.startswith("$.") or len(path) > 512
                   or any(_private_key(part.removesuffix("[]")) for part in path[2:].split("."))
                   for path in public_paths)):
        raise IdentificationError("P26_ROUTING_SELECTION_INVALID")
    position = nodes = 0
    fields: dict[tuple[str, str], dict] = {}
    restricted: dict[tuple[str, str], dict] = {}
    categories = {name: 0 for name in SENSITIVE_CATEGORIES}
    def unavailable(path, kind, reason):
        if public_failures is None:
            raise IdentificationError("P26_STRUCTURE_INVALID")
        row = {"path":path,"type":kind,"reason":reason}
        if row not in public_failures:
            public_failures.append(row)

    def fail():
        raise IdentificationError("P26_STRUCTURE_INVALID")

    def whitespace():
        nonlocal position
        while position < len(body) and body[position] in b" \r\n\t":
            position += 1

    def string_end():
        nonlocal position
        start = position
        if position >= len(body) or body[position] != 34:
            fail()
        position += 1
        while position < len(body):
            byte = body[position]
            position += 1
            if byte == 34:
                return start, position
            if byte < 32:
                fail()
            if byte == 92:
                if position >= len(body):
                    fail()
                escape = body[position]
                position += 1
                if escape == 117:
                    if position + 4 > len(body) or any(c not in b"0123456789abcdefABCDEF" for c in body[position:position+4]):
                        fail()
                    position += 4
                elif escape not in b'"\\/bfnrt':
                    fail()
        fail()

    def value(path: str | None, depth: int, private_label: tuple[str, str] | None = None,
              coordinates: tuple[str | int, ...] = ()):
        nonlocal position, nodes
        whitespace()
        nodes += 1
        if nodes > MAX_NODES:
            raise structure_budget_error('NODES', nodes, 'LEXICAL_SCAN')
        if depth > 32:
            raise structure_budget_error('DEPTH', depth, 'LEXICAL_SCAN')
        if position >= len(body):
            fail()
        scalar_start = position
        first = body[position]
        kind = "object" if first == 123 else "array" if first == 91 else "string" if first == 34 else None
        if first in (116, 102): kind = "boolean"
        elif first == 110: kind = "null"
        elif first in b"-0123456789": kind = "number"
        if kind is None:
            fail()
        if path in public_paths and kind not in {"string", "number", "boolean", "null"}:
            unavailable(path, kind, "NONSCALAR")
        if private_label is not None and restricted_fields is not None:
            label, category = private_label
            restricted[(label, kind)] = {"path": label, "type": kind, "category": category}
            if len(restricted) > MAX_SHAPE:
                raise structure_budget_error('RESTRICTED_DEFINITIONS', len(restricted), 'LEXICAL_SCAN')
        if path is not None:
            fields[(path, kind)] = {"path": path, "type": kind}
            if len(fields) > MAX_SHAPE:
                raise structure_budget_error('FIELD_DEFINITIONS', len(fields), 'LEXICAL_SCAN')
        if first == 123:
            position += 1; whitespace()
            if position < len(body) and body[position] == 125:
                position += 1; return
            keys = set()
            while True:
                whitespace(); start, end = string_end()
                key = None
                if path is not None:
                    try: key = json.loads(body[start:end])
                    except (ValueError, UnicodeError): fail()
                    if key in keys: fail()
                    keys.add(key)
                whitespace()
                if position >= len(body) or body[position] != 58: fail()
                position += 1
                child = None
                private_label = None
                if path is not None:
                    if _private_key(key):
                        category = _sensitive_category(key)
                        categories[category] = min(128, categories[category] + 1)
                        private_label = (path + "." + _shape_key(key), category)
                    else:
                        child = path + "." + _shape_key(key)
                value(child, depth + 1, private_label, coordinates + (key,) if child is not None else ())
                whitespace()
                if position >= len(body): fail()
                separator = body[position]; position += 1
                if separator == 125: return
                if separator != 44: fail()
        elif first == 91:
            position += 1; whitespace()
            if position < len(body) and body[position] == 93:
                position += 1; return
            index = 0
            while True:
                value(None if path is None else path + "[]", depth + 1, coordinates=coordinates + (index,))
                index += 1
                whitespace()
                if position >= len(body): fail()
                separator = body[position]; position += 1
                if separator == 93: return
                if separator != 44: fail()
        elif first == 34:
            string_end()  # Never decode a scalar string or inspect its value.
        elif kind == "number":
            number = _JSON_NUMBER.match(body, position)
            if number is None: fail()
            position = number.end()  # No int/float/Decimal conversion.
        else:
            literal = b"true" if first == 116 else b"false" if first == 102 else b"null"
            if body[position:position+len(literal)] != literal: fail()
            position += len(literal)
        if path in public_paths and public_values is not None and kind in {"string", "number", "boolean", "null"}:
            scalar = json.loads(body[scalar_start:position])
            reason = ("STRING_LENGTH" if type(scalar) is str and len(scalar)>256 else
                      "URL_VALUE" if type(scalar) is str and "://" in scalar else
                      "LINE_BREAK" if type(scalar) is str and ("\n" in scalar or "\r" in scalar) else
                      "NONFINITE_NUMBER" if type(scalar) is float and not math.isfinite(scalar) else None)
            if reason: unavailable(path,kind,reason)
            else: public_values.append({"path":path,"coordinates":list(coordinates),"value":scalar})

    whitespace()
    if position >= len(body) or body[position] not in (123, 91): fail()
    value("$", 0); whitespace()
    if position != len(body): fail()
    if restricted_fields is not None:
        restricted_fields.extend(sorted(restricted.values(), key=lambda row: (row["path"], row["type"])))
    return sorted(fields.values(), key=lambda row: (row["path"], row["type"])), categories


def _privacy_shape(payload: object, expected_name: str) -> tuple[list[dict], list[str]]:
    # First pass completes privacy validation before any identity or shape
    # output. There is no partial shape on sensitive rejection.
    stack = [(payload, 0)]
    count = 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if count > MAX_NODES:
            raise structure_budget_error('NODES', count, 'STRICT_SCAN')
        if depth > 32:
            raise structure_budget_error('DEPTH', depth, 'STRICT_SCAN')
        if type(value) is dict:
            for key, child in value.items():
                if type(key) is not str or _private_key(key):
                    raise IdentificationError("P26_SENSITIVE_INPUT", category=_sensitive_category(key) if type(key) is str else None)
                stack.append((child, depth + 1))
        elif type(value) is list:
            stack.extend((child, depth + 1) for child in value)
        elif type(value) not in (str, int, float, bool, type(None)):
            raise IdentificationError("P26_STRUCTURE_INVALID")
        elif type(value) is float and not math.isfinite(value):
            raise IdentificationError("P26_STRUCTURE_INVALID")
    if type(payload) not in (dict, list):
        raise IdentificationError("P26_STRUCTURE_INVALID")
    expected = unicodedata.normalize("NFKC", expected_name).replace(" ", "")
    shape: dict[tuple[str, str], dict] = {}
    identity: set[str] = set()
    stack = [(payload, "$")]
    while stack:
        value, path = stack.pop()
        kind = {dict: "object", list: "array", str: "string", int: "integer",
                float: "number", bool: "boolean", type(None): "null"}[type(value)]
        shape[(path, kind)] = {"path": path, "type": kind}
        if len(shape) > MAX_SHAPE:
            raise structure_budget_error('FIELD_DEFINITIONS', len(shape), 'STRICT_SCAN')
        if type(value) is dict:
            stack.extend((child, path + "." + _shape_key(key)) for key, child in value.items())
        elif type(value) is list:
            stack.extend((child, path + "[]") for child in value)
        elif type(value) is str and "<dynamic>" not in path:
            if unicodedata.normalize("NFKC", value).replace(" ", "") == expected:
                identity.add(path)
    return sorted(shape.values(), key=lambda row: (row["path"], row["type"])), sorted(identity)


class BodyCollector:
    """Both encoded and decoded limits; never ask mitmproxy to retain a body."""

    def __init__(self, owner: "IdentificationWindow", encoding: str, callback: Callable[[bytes], None]):
        self.owner, self.callback = owner, callback
        self.encoded = 0
        self.buffer = bytearray()
        self.finished = False
        self.expires_at = owner.last_clock + 60
        if encoding not in ("identity", "", "gzip", "deflate"):
            raise IdentificationError("P26_ENCODING_UNSUPPORTED")
        self.decoder = zlib.decompressobj(31 if encoding == "gzip" else 15) if encoding in ("gzip", "deflate") else None

    def _append(self, data: bytes) -> None:
        if len(self.buffer) + len(data) > MAX_BODY:
            raise IdentificationError("P26_RESPONSE_SIZE_LIMIT")
        self.owner.decoded_bytes += len(data)
        if self.owner.decoded_bytes > MAX_TOTAL:
            raise IdentificationError("P26_TOTAL_SIZE_LIMIT")
        self.buffer.extend(data)

    def feed(self, chunk: bytes) -> bytes:
        # A streaming callback forwards the original chunk untouched. On close
        # it only discards, including late chunks from an existing connection.
        if self.finished or not self.owner.active():
            self.clear()
            return chunk
        try:
            if chunk:
                self.encoded += len(chunk)
                self.owner.encoded_bytes += len(chunk)
                if self.encoded > MAX_BODY:
                    raise IdentificationError("P26_RESPONSE_SIZE_LIMIT")
                if self.owner.encoded_bytes > MAX_TOTAL:
                    raise IdentificationError("P26_TOTAL_SIZE_LIMIT")
                if self.decoder:
                    data = self.decoder.decompress(chunk, MAX_BODY - len(self.buffer) + 1)
                    if self.decoder.unconsumed_tail:
                        raise IdentificationError("P26_RESPONSE_SIZE_LIMIT")
                else:
                    data = chunk
                self._append(data)
            else:
                self.finished = True
                if self.decoder and (not self.decoder.eof or self.decoder.unused_data):
                    raise IdentificationError("P26_ENCODING_INVALID")
                self.callback(bytes(self.buffer))
                self.buffer.clear()
                self.decoder = None
        except IdentificationError as error:
            self.clear()
            from .p26_structure_budget import record_failure
            record_failure(self.owner, error)
            self.owner.close(error.code)
        except Exception:
            self.clear()
            self.owner.close("P26_IDENTIFICATION_EXCEPTION")
        return chunk

    def clear(self) -> None:
        self.buffer.clear()
        self.decoder = None
        self.finished = True


class IdentificationWindow:
    def __init__(self, expected_store: str, *, clock: Callable[[], float] = time.monotonic,
                 duration_seconds: float | None = 120, route_domain_suffixes: tuple[str, ...] = ()):
        if type(expected_store) is not str or not 1 <= len(expected_store) <= 256:
            raise IdentificationError("P26_CURRENT_CHOICE_REQUIRED")
        if duration_seconds is not None and (type(duration_seconds) not in (int, float)
                                             or not math.isfinite(duration_seconds) or duration_seconds <= 0):
            raise IdentificationError("P26_CLOCK_INVALID")
        if (type(route_domain_suffixes) is not tuple or len(route_domain_suffixes) > 3
                or any(type(suffix) is not str or suffix not in CURRENT_ROUTE_SUFFIXES
                       for suffix in route_domain_suffixes)):
            raise IdentificationError("P26_ROUTING_SELECTION_INVALID")
        self.expected_store, self.clock = expected_store, clock
        self.duration_seconds = duration_seconds
        self.window_ref = "identification:" + uuid4().hex
        self.state, self.code = "PREPARED", "P26_IDENTIFICATION_NOT_STARTED"
        self.attempts = 0
        self.started_at = self.closed_at = None
        self.deadline = None
        self.last_clock = None
        self.domains: list[str] = []
        self.allowed_domains: set[str] = set()
        self.route_domain_suffixes = route_domain_suffixes
        self.routes: list[tuple[str, str, str]] = []
        self.route_origins: dict[int, str] = {}
        self.selected_routes: set[int] = set()
        self.raw_callbacks = self.response_reads = self.target_matches = 0
        self.response_reads_at_least = self.target_matches_at_least = False
        self.next_observation_slot = 0
        self.field_catalog: dict[tuple[int, str, str], dict] = {}
        self.sensitive_rejections = {name: 0 for name in SENSITIVE_CATEGORIES}
        self.last_body_route = None
        self.structure_budget_failure = None
        self.key_layout_only = False
        self.sensitive_key_layout_authorized = False
        self.key_layouts: list[dict] = []
        self.public_projection_paths: dict[str, frozenset[str]] = {}
        self.public_projection_enabled = False
        self.projected_observations: list[dict] = []
        self.request_leases: dict[str, dict] = {}
        self.request_encoded_bytes = self.request_decoded_bytes = self.request_metadata_bodies = 0
        self.request_metadata_bodies_at_least = False
        self.routing_callbacks = 0
        self.route_rejections = {name: 0 for name in (
            "HOST_NOT_SELECTED", "METHOD_NOT_ALLOWED", "PATH_NOT_SUPPORTED", "PRIVATE_ROUTE")}
        self.route_rejections_at_least = False
        self.raw_callbacks_at_least = self.routing_callbacks_at_least = False
        self.encoded_bytes = self.decoded_bytes = 0
        self.observations: list[dict] = []
        self.payloads: dict[int, object] = {}
        self.payload_expiries: dict[int, float] = {}
        self.collectors: list[BodyCollector] = []
        self.public_probes: list[dict] = []

    def start_once(self) -> None:
        if self.state != "PREPARED" or self.attempts:
            raise IdentificationError("P26_WINDOW_ALREADY_USED")
        now = self.clock()
        if not math.isfinite(now):
            raise IdentificationError("P26_CLOCK_INVALID")
        self.deadline = None if self.duration_seconds is None else now + self.duration_seconds
        self.last_clock = now
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.attempts, self.state, self.code = 1, "ACTIVE", "P26_ROUTING_IDENTIFICATION"

    def active(self) -> bool:
        if self.state != "ACTIVE":
            return False
        try:
            now = self.clock()
            if not math.isfinite(now) or now < self.last_clock:
                self.close("P26_CLOCK_INVALID")
            elif self.deadline is not None and now >= self.deadline:
                self.close("P26_WINDOW_TIMEOUT")
            else:
                self.last_clock = now
                self.projected_observations = [row for row in self.projected_observations if row["expires_at"] > now]
                for ref in list(self.request_leases):
                    if self.request_leases[ref]["expires_at"] <= now:
                        self.request_leases.pop(ref)
                if any(not collector.finished and now >= collector.expires_at for collector in self.collectors):
                    self.close("P26_RESPONSE_PROCESSING_TIMEOUT")
                for slot, expiry in list(self.payload_expiries.items()):
                    if now >= expiry:
                        self.payloads.pop(slot, None)
                        self.payload_expiries.pop(slot, None)
        except Exception:
            self.close("P26_CLOCK_INVALID")
        return self.state == "ACTIVE"

    def domain(self, host: str) -> int | None:
        if not self.active() or type(host) is not str or _HOST.fullmatch(host.lower()) is None:
            return None
        if not self._routing_budget():
            return None
        host = host.lower()
        if host not in self.domains:
            limit = MAX_MONITORING_DOMAINS if self.duration_seconds is None else MAX_DOMAINS
            if len(self.domains) >= limit:
                self.close("P26_ROUTING_BUDGET")
                return None
            self.domains.append(host)
        # This optional identification policy acts only on actual current SNI.
        # It permits query-free route metadata, never automatic body reads or
        # a claim that a domain/route belongs to the chosen store.
        if any(host == suffix or host.endswith("." + suffix)
               for suffix in self.route_domain_suffixes):
            self.allowed_domains.add(host)
        return self.domains.index(host)

    def allow_domain(self, slot: int) -> None:
        if not self.active() or type(slot) is not int or not 0 <= slot < len(self.domains):
            raise IdentificationError("P26_ROUTING_SELECTION_INVALID")
        self.allowed_domains.add(self.domains[slot])

    def inspect_current_domain(self, host: str) -> None:
        # Developer supplies a hostname from this session's actual SNI, so its
        # next connection can expose query-free routes immediately. This is
        # preparation, not an observed domain/response or source qualification.
        if (self.state != "PREPARED" or type(host) is not str
                or _HOST.fullmatch(host) is None or len(self.allowed_domains) >= 8):
            raise IdentificationError("P26_ROUTING_SELECTION_INVALID")
        self.allowed_domains.add(host)

    def route(self, method: str, host: str, path: str, *, tls_domain: str | None = None) -> int | None:
        if not self.active():
            return None
        # A local/transparent request authority can differ from its SNI. Route
        # inspection remains gated by the actual selected TLS source; preserve
        # the authority separately, rather than silently relabeling it as SNI.
        origin = host if tls_domain is None else tls_domain
        if (type(host) is not str or len(host) > 253 or type(origin) is not str
                or origin.lower() not in self.allowed_domains):
            return self._route_rejected("HOST_NOT_SELECTED")
        if not self._routing_budget():
            return None
        if type(path) is not str:
            return self._route_rejected("PATH_NOT_SUPPORTED")
        path = path.partition("?")[0].partition("#")[0]
        if not path.startswith("/") or len(path) > 512:
            return self._route_rejected("PATH_NOT_SUPPORTED")
        if method not in ("GET", "POST"):
            return self._route_rejected("METHOD_NOT_ALLOWED")
        try:
            if _private_route(path):
                return self._route_rejected("PRIVATE_ROUTE")
        except UnicodeError:
            return self._route_rejected("PATH_NOT_SUPPORTED")
        route = (method, host.lower(), path)
        origin = origin.lower()
        slot = next((index for index, existing in enumerate(self.routes)
                     if existing == route and self.route_origins[index] == origin), None)
        if slot is None:
            limit = MAX_MONITORING_ROUTES if self.duration_seconds is None else MAX_ROUTES
            if len(self.routes) >= limit:
                self.close("P26_ROUTING_BUDGET")
                return None
            slot = len(self.routes)
            self.routes.append(route)
            self.route_origins[slot] = origin
        return slot

    def _route_rejected(self, reason: str) -> None:
        self.route_rejections_at_least |= self.route_rejections[reason] >= 128
        self.route_rejections[reason] = min(128, self.route_rejections[reason] + 1)
        return None

    def _routing_budget(self) -> bool:
        if self.routing_callbacks >= 128:
            if self.duration_seconds is None:
                self.routing_callbacks_at_least = True
                return True
            self.close("P26_ROUTING_BUDGET")
            return False
        self.routing_callbacks += 1
        return True

    def select_route(self, slot: int) -> None:
        if not self.active() or type(slot) is not int or not 0 <= slot < len(self.routes):
            raise IdentificationError("P26_ROUTING_SELECTION_INVALID")
        self.selected_routes.add(slot)

    def begin_response(self, route: int | None, encoding: str, *, source_request_ref: str | None = None) -> BodyCollector | None:
        if not self.active():
            return None
        if self.raw_callbacks >= MAX_CALLBACKS:
            if self.duration_seconds is not None:
                self.close("P26_CALLBACK_BUDGET")
                return None
            self.raw_callbacks_at_least = True
        self.raw_callbacks = min(self.raw_callbacks + 1, MAX_CALLBACKS)
        if route not in self.selected_routes:
            return None
        self.collectors = [collector for collector in self.collectors if not collector.finished]
        if len(self.collectors) >= MAX_RESPONSES:
            self.close("P26_RESPONSE_COUNT_LIMIT")
            return None
        if self.response_reads >= MAX_RESPONSES and self.duration_seconds is not None:
            self.close("P26_RESPONSE_COUNT_LIMIT")
            return None
        self.response_reads_at_least |= self.response_reads >= MAX_RESPONSES
        self.response_reads = min(self.response_reads + 1, MAX_RESPONSES)
        self.last_body_route = route
        try:
            collector = BodyCollector(self, encoding, lambda body: self._consume(route, body, source_request_ref=source_request_ref))
        except IdentificationError as error:
            self.close(error.code)
            return None
        self.collectors.append(collector)
        return collector

    def _consume(self, route: int, body: bytes, *, source_request_ref: str | None = None) -> None:
        if not self.active():
            return
        self.last_body_route = route
        try:
            # Lexical key validation precedes decoding any scalar value. A
            # sensitive branch stays opaque, including its nested keys.
            restricted_fields = [] if self.key_layout_only and self.sensitive_key_layout_authorized else None
            public_paths = self.public_projection_paths.get(self.routes[route][2], frozenset())
            public_values = [] if public_paths else None
            public_failures = [] if public_paths else None
            fields, categories = key_only_layout(body, restricted_fields=restricted_fields,
                                                 public_paths=public_paths, public_values=public_values,
                                                 public_failures=public_failures)
            for category, count in categories.items():
                self.sensitive_rejections[category] = min(128, self.sensitive_rejections[category] + count)
            if self.key_layout_only:
                self.key_layouts.append({
                    "layout_ref": "layout:" + uuid4().hex, "route_slot": route,
                    "observed_at": observation_time(), "fields": fields,
                    "sensitive_rejections": categories, "field_values_processed": bool(public_paths),
                    "restricted_fields": restricted_fields or [],
                    "public_field_failures": public_failures or [],
                    "target_identity": "NOT_INSPECTED", "meaning": "UNKNOWN"})
                self.key_layouts = self.key_layouts[-MAX_RESPONSES:]
                if public_values is not None:
                    self.projected_observations.append({"projection_ref":"projection:"+uuid4().hex,
                        "route_slot":route,"observed_at":observation_time(),
                        "values":public_values,"meaning":"DEVELOPER_REVIEW_REQUIRED",
                        "unavailable_fields":public_failures,"complete_record":False,
                        "source_request_ref":source_request_ref,
                        "source_identity":"NOT_CONFIRMED","sensitive_values_processed":False,
                        "expires_at":self.last_clock+60})
                    self.projected_observations=self.projected_observations[-MAX_RESPONSES:]
                if any(categories.values()) and not self.sensitive_key_layout_authorized:
                    self.close("P26_SENSITIVE_INPUT")
                else: self.code = "P26_FIELD_LAYOUT_OBSERVED"
                return
            if any(categories.values()):
                self.close("P26_SENSITIVE_INPUT")
                return
            def duplicate_checked(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise IdentificationError("P26_STRUCTURE_INVALID")
                    result[key] = value
                return result
            payload = json.loads(body, object_pairs_hook=duplicate_checked)
            shape, identity = _privacy_shape(payload, self.expected_store)
            slot = self.next_observation_slot
            self.next_observation_slot += 1
            matched = bool(identity)
            self.target_matches_at_least |= matched and self.target_matches >= MAX_RESPONSES
            self.target_matches = min(self.target_matches + int(matched), MAX_RESPONSES)
            row = {
                "slot": slot, "route_slot": route,
                "observation_ref": "observation:" + uuid4().hex,
                "observed_at": observation_time(),
                "target_name_match": matched, "identity_paths": identity, "shape": shape,
                "family_version": "UNKNOWN", "amount_unit": "UNKNOWN", "currency": "UNKNOWN",
            }
            for definition in shape:
                key = (route, definition["path"], definition["type"])
                if key not in self.field_catalog and len(self.field_catalog) >= MAX_SHAPE:
                    raise structure_budget_error('CATALOG_DEFINITIONS', len(self.field_catalog) + 1, 'FIELD_CATALOG')
                self.field_catalog[key] = {**definition, "route_slot": route,
                    "observation_ref": row["observation_ref"], "observed_at": row["observed_at"],
                    "target_name_match": matched, "meaning": "UNKNOWN"}
            self.observations.append(row)
            if len(self.observations) > MAX_RESPONSES:
                expired = self.observations.pop(0)["slot"]
                self.payloads.pop(expired, None)
                self.payload_expiries.pop(expired, None)
            if matched:
                self.payloads[slot] = payload
                # Monitoring duration may be unlimited; raw references are
                # still short-lived, independently of the monitoring session.
                self.payload_expiries[slot] = self.last_clock + 60
            self.code = "P26_TARGET_SHAPE_OBSERVED" if matched else "P26_TARGET_NOT_MATCHED"
        except IdentificationError as error:
            if error.code == "P26_SENSITIVE_INPUT":
                self.sensitive_rejections[error.category] = min(128, self.sensitive_rejections[error.category] + 1)
            from .p26_structure_budget import record_failure
            record_failure(self, error)
            self.close(error.code)
        except (ValueError, UnicodeError, RecursionError):
            self.close("P26_BUSINESS_JSON_INVALID")

    def probe(self, slot: int, path: list[str | int]) -> dict:
        """Developer-selected public scalar only; no raw/container export."""
        if not self.active() or type(slot) is not int or slot not in self.payloads:
            raise IdentificationError("P26_PUBLIC_PROBE_UNAVAILABLE")
        if len(self.public_probes) >= 32:
            raise IdentificationError("P26_PUBLIC_PROBE_LIMIT")
        if type(path) is not list or not 1 <= len(path) <= 32:
            raise IdentificationError("P26_PUBLIC_PROBE_INVALID")
        if type(path[-1]) is not str or _normalized(path[-1]) not in _PROBE_FIELDS:
            raise IdentificationError("P26_PUBLIC_PROBE_INVALID")
        value = self.payloads[slot]
        try:
            for part in path:
                if type(part) is int:
                    if not 0 <= part < 3 or type(value) is not list:
                        raise IdentificationError("P26_PUBLIC_PROBE_INVALID")
                elif type(part) is not str or _FIELD.fullmatch(part) is None or _private_key(part):
                    raise IdentificationError("P26_PUBLIC_PROBE_INVALID")
                value = value[part]
        except (KeyError, IndexError, TypeError):
            raise IdentificationError("P26_PUBLIC_PROBE_INVALID")
        if type(value) not in (str, int, float) or type(value) is bool:
            raise IdentificationError("P26_PUBLIC_PROBE_INVALID")
        if type(value) is str and (len(value) > 256 or "://" in value or "\n" in value):
            raise IdentificationError("P26_PUBLIC_PROBE_INVALID")
        observation = next(row for row in self.observations if row["slot"] == slot)
        result = {"observation_ref": observation["observation_ref"],
                  "path": path, "public_value": value, "meaning": "DEVELOPER_REVIEW_REQUIRED"}
        self.public_probes.append(result)
        return result

    def close(self, code: str = "P26_IDENTIFICATION_CLOSED") -> None:
        if self.state == "CLOSED":
            return
        if code not in STATUS_CODES:
            code = "P26_IDENTIFICATION_EXCEPTION"
        self.state, self.code = "CLOSED", code
        self.closed_at = datetime.now(timezone.utc).isoformat()
        for collector in self.collectors:
            collector.clear()
        self.collectors.clear()
        self.payloads.clear()
        self.payload_expiries.clear()
        self.projected_observations.clear()
        self.public_projection_paths.clear()
        self.request_leases.clear()
        self.domains.clear()
        self.allowed_domains.clear()
        self.route_domain_suffixes = ()
        self.routes.clear()
        self.route_origins.clear()
        self.selected_routes.clear()
        self.expected_store = ""

    def diagnostic(self) -> dict:
        self.active()
        return {
            "schema_version": "p26-identification-diagnostic/v1",
            "window_ref": self.window_ref, "state": self.state, "code": self.code,
            "identification_attempts": self.attempts, "result_attempts": 0,
            "started_at": self.started_at, "closed_at": self.closed_at,
            "raw_callbacks": self.raw_callbacks, "business_responses": self.response_reads,
            "business_responses_at_least": self.response_reads_at_least,
            "raw_callbacks_at_least": self.raw_callbacks_at_least,
            # business_responses counts selected route reads, including rejects.
            # Identification has no complete mapped/parsed/published event.
            "qualified_business_events": 0, "parsed_records": 0, "published_records": 0,
            "routing_callbacks": self.routing_callbacks,
            "routing_callbacks_at_least": self.routing_callbacks_at_least,
            "route_rejections": dict(self.route_rejections),
            "route_rejections_at_least": self.route_rejections_at_least,
            "target_matches": self.target_matches, "encoded_bytes": min(self.encoded_bytes, MAX_TOTAL + MAX_BODY),
            "target_matches_at_least": self.target_matches_at_least,
            "sensitive_rejections": dict(self.sensitive_rejections),
            "privacy_mode": ("SCOPED_PUBLIC_SCALARS_PRIVATE_BRANCHES_OPAQUE" if self.public_projection_enabled
                             else "AUTHORIZED_KEY_METADATA_ONLY" if self.key_layout_only and self.sensitive_key_layout_authorized
                             else "STRICT_STOP"),
            "last_body_route_slot": self.last_body_route,
            "request_encoded_bytes":min(self.request_encoded_bytes,MAX_TOTAL+MAX_BODY),
            "request_decoded_bytes":min(self.request_decoded_bytes,MAX_TOTAL+MAX_BODY),
            "request_metadata_bodies":self.request_metadata_bodies,
            "request_metadata_bodies_at_least":self.request_metadata_bodies_at_least,
            "decoded_bytes": min(self.decoded_bytes, MAX_TOTAL + MAX_BODY),
            "live_capture_latch": "OPEN" if self.state == "ACTIVE" else "CLOSED",
            "execution_latch": "CLOSED", "product_result": "incomplete",
        }
