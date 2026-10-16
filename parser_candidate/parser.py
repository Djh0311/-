"""Pure, configurable PRODUCTLIST Parser candidate.

The module accepts an already-decoded in-memory mapping and returns a new
mapping. It has no filesystem, network, environment, clock, subprocess, or
Provider capability. Semantic fields must be selected explicitly in config;
there is no candidate fallback or field-name guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping, Sequence, Tuple


CONTRACT_ID = "PRODUCTLIST_CONFIGURABLE_INPUT_CONTRACT_V1"
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_OUTPUT_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ALLOWED_TYPES = frozenset(
    {"array", "boolean", "integer", "null", "number", "object", "string"}
)
_SENSITIVE_FRAGMENTS = frozenset(
    {"token", "authorization", "cookie", "password", "secret", "session", "openid", "unionid"}
)


class ParserError(ValueError):
    """Closed-code Parser failure that never includes input values."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Binding:
    """One explicit semantic or extension mapping."""

    name: str
    path: str
    types: Tuple[str, ...]
    scope: str
    required: bool = True
    output_key: str | None = None
    source_label: str | None = None
    many: bool = False

    def validate(self) -> "Binding":
        if not self.name or _KEY.fullmatch(self.name) is None:
            raise ParserError("PARSER_CONFIG_INVALID")
        if not self.path.startswith("$"):
            raise ParserError("PARSER_CONFIG_INVALID")
        _tokenize(self.path)
        if not self.types or any(item not in _ALLOWED_TYPES for item in self.types):
            raise ParserError("PARSER_CONFIG_INVALID")
        if self.scope not in {"category", "product", "sku", "merchant", "coupon", "root"}:
            raise ParserError("PARSER_CONFIG_INVALID")
        key = self.output_key or self.name
        if _OUTPUT_KEY.fullmatch(key) is None or _is_sensitive_key(key):
            raise ParserError("PARSER_CONFIG_INVALID")
        if self.source_label is not None and (
            _KEY.fullmatch(self.source_label) is None
            or _is_sensitive_key(self.source_label)
        ):
            raise ParserError("PARSER_CONFIG_INVALID")
        if type(self.many) is not bool:
            raise ParserError("PARSER_CONFIG_INVALID")
        return self


@dataclass(frozen=True)
class ParserConfig:
    """Immutable contract configuration with explicit semantic bindings."""

    payload_family: str
    payload_version: str
    category_id: Binding | None
    product_price: Binding | None
    sku_price: Binding | None
    extensions: Tuple[Binding, ...] = ()
    observed_extensions: Tuple[Binding, ...] = ()
    category_container: str = "$.data.food_spu_tags[*]"
    product_container: str = "$.data.food_spu_tags[*].dynamic_spus[*]"
    sku_container: str = "$.data.food_spu_tags[*].dynamic_spus[*].skus[*]"
    current_page_path: str = "$.data.food_spu_tags[*].current_page"
    has_next_page_path: str = "$.data.food_spu_tags[*].has_next_page"
    price_bindings: Tuple[Binding, ...] = ()
    sku_status_types: Tuple[str, ...] = ("integer",)
    sku_status_required: bool = True

    def validate(self) -> "ParserConfig":
        if not _safe_version_token(self.payload_family) or not _safe_version_token(self.payload_version):
            raise ParserError("PARSER_VERSION_UNRESOLVED")
        if not self.sku_status_types or any(t not in {"integer","number"} for t in self.sku_status_types):
            raise ParserError("PARSER_CONFIG_INVALID")
        if type(self.sku_status_required) is not bool:
            raise ParserError("PARSER_CONFIG_INVALID")
        expected = (
            self.category_container,
            self.product_container,
            self.sku_container,
            self.current_page_path,
            self.has_next_page_path,
        )
        if expected != (
            "$.data.food_spu_tags[*]",
            "$.data.food_spu_tags[*].dynamic_spus[*]",
            "$.data.food_spu_tags[*].dynamic_spus[*].skus[*]",
            "$.data.food_spu_tags[*].current_page",
            "$.data.food_spu_tags[*].has_next_page",
        ):
            raise ParserError("PARSER_CONFIG_INVALID")
        if self.category_id is None:
            raise ParserError("CATEGORY_ID_MAPPING_UNRESOLVED")
        if self.product_price is None or self.sku_price is None:
            raise ParserError("PRICE_MAPPING_UNRESOLVED")
        bindings = (
            (self.category_id, self.product_price, self.sku_price)
            + self.extensions
            + self.observed_extensions
            + self.price_bindings
        )
        for binding in bindings:
            binding.validate()
        for binding in self.price_bindings:
            if binding.source_label is None:
                raise ParserError("PRICE_SOURCE_LABEL_UNRESOLVED")
        for binding in self.observed_extensions:
            if binding.source_label is None:
                raise ParserError("PARSER_P1_SOURCE_LABEL_UNRESOLVED")
        _require_prefix(self.category_id.path, self.category_container)
        _require_prefix(self.product_price.path, self.product_container)
        _require_prefix(self.sku_price.path, self.sku_container)
        for binding in self.extensions + self.observed_extensions:
            prefix = {
                "category": self.category_container,
                "product": self.product_container,
                "sku": self.sku_container,
            }[binding.scope]
            _require_prefix(binding.path, prefix)
        for binding in self.price_bindings:
            try:
                prefix = {
                "category": self.category_container,
                "product": self.product_container,
                "sku": self.sku_container,
                "root": "$.data",
                }[binding.scope]
            except KeyError as error:
                raise ParserError("PARSER_CONFIG_INVALID") from error
            _require_prefix(binding.path, prefix)
        return self


@dataclass(frozen=True)
class FoodParserConfig:
    """Explicit FOOD endpoint profile for one merchant observation."""

    payload_family: str
    payload_version: str
    merchant_id: Binding
    merchant_name: Binding
    price_bindings: Tuple[Binding, ...] = ()
    observed_extensions: Tuple[Binding, ...] = ()
    merchant_container: str = "$.data.poi_info"

    def validate(self) -> "FoodParserConfig":
        if not _safe_version_token(self.payload_family) or not _safe_version_token(self.payload_version):
            raise ParserError("PARSER_VERSION_UNRESOLVED")
        if self.merchant_container not in {"$.data.poi_info", "$.data.poi_base_info"}:
            raise ParserError("MERCHANT_MAPPING_INVALID")
        for binding in (self.merchant_id, self.merchant_name) + self.price_bindings + self.observed_extensions:
            binding.validate()
        if self.merchant_id.scope != "merchant" or self.merchant_name.scope != "merchant":
            raise ParserError("MERCHANT_MAPPING_INVALID")
        for binding in self.price_bindings:
            if binding.source_label is None or binding.scope not in {"merchant", "coupon", "root"}:
                raise ParserError("PRICE_SOURCE_LABEL_UNRESOLVED")
            prefix = self.merchant_container if binding.scope != "root" else "$.data"
            _require_prefix(binding.path, prefix)
        for binding in self.observed_extensions:
            if binding.source_label is None or binding.scope not in {"merchant", "root"}:
                raise ParserError("PARSER_P1_SOURCE_LABEL_UNRESOLVED")
            prefix = self.merchant_container if binding.scope == "merchant" else "$.data"
            _require_prefix(binding.path, prefix)
        _require_prefix(self.merchant_id.path, self.merchant_container)
        _require_prefix(self.merchant_name.path, self.merchant_container)
        return self


def parse_productlist(payload: Mapping[str, Any], config: ParserConfig) -> dict[str, Any]:
    """Parse one in-memory PRODUCTLIST payload according to explicit config."""

    config.validate()
    if type(payload) is not dict:
        raise ParserError("UNSUPPORTED_PAYLOAD")
    categories = _select(payload, _tokenize(config.category_container))
    if not categories:
        raise ParserError("REQUIRED_FIELD_MISSING")
    current_tail = _relative_tokens(config.current_page_path, config.category_container)
    next_tail = _relative_tokens(config.has_next_page_path, config.category_container)
    product_tail = _relative_tokens(config.product_container, config.category_container)
    sku_tail = _relative_tokens(config.sku_container, config.product_container)
    if len(categories) > 1:
        top_level_page = _select(payload, _tokenize("$.data.current_page"))
        top_level_next = _select(payload, _tokenize("$.data.has_next_page"))
        if (top_level_page or top_level_next) and any(
            not _select(category, current_tail) or not _select(category, next_tail)
            for category in categories
            if type(category) is dict
        ):
            raise ParserError("MULTI_CATEGORY_PAGE_COLLAPSE")
    result: list[dict[str, Any]] = []
    root_row: dict[str, Any] = {}
    _apply_price_bindings(
        root_row,
        payload.get("data", {}),
        "root",
        config.price_bindings,
        "$.data",
    )
    for category in categories:
        if type(category) is not dict:
            raise ParserError("TYPE_MISMATCH")
        category_row: dict[str, Any] = {
            "category_id": _bound_value(category, config.category_id, config.category_container),
            "current_page": _one(category, current_tail, "REQUIRED_FIELD_MISSING"),
            "has_next_page": _one(category, next_tail, "REQUIRED_FIELD_MISSING"),
            "products": [],
        }
        _apply_price_bindings(
            category_row,
            category,
            "category",
            config.price_bindings,
            config.category_container,
        )
        _expect(category_row["current_page"], ("integer",))
        _expect(category_row["has_next_page"], ("boolean",))
        _apply_extensions(
            category_row,
            category,
            "category",
            config.extensions + config.observed_extensions,
            config.category_container,
        )
        products = _select(category, product_tail)
        for product in products:
            if type(product) is not dict:
                raise ParserError("TYPE_MISMATCH")
            product_row: dict[str, Any] = {
                "id": _required_direct(product, "id", ("integer",)),
                "name": _required_direct(product, "name", ("string",)),
                "price": _bound_value(product, config.product_price, config.product_container),
                "skus": [],
            }
            _apply_price_bindings(
                product_row,
                product,
                "product",
                config.price_bindings,
                config.product_container,
            )
            _apply_extensions(
                product_row,
                product,
                "product",
                config.extensions + config.observed_extensions,
                config.product_container,
            )
            skus = _select(product, sku_tail)
            for sku in skus:
                if type(sku) is not dict:
                    raise ParserError("TYPE_MISMATCH")
                sku_row: dict[str, Any] = {
                    "id": _required_direct(sku, "id", ("integer",)),
                    "spec": _required_direct(sku, "spec", ("string",)),
                    "price": _bound_value(sku, config.sku_price, config.sku_container),
                }
                if config.sku_status_required or "status" in sku:
                    sku_row["status"] = _required_direct(sku, "status", config.sku_status_types)
                _apply_price_bindings(
                    sku_row,
                    sku,
                    "sku",
                    config.price_bindings,
                    config.sku_container,
                )
                _apply_extensions(
                    sku_row,
                    sku,
                    "sku",
                    config.extensions + config.observed_extensions,
                    config.sku_container,
                )
                product_row["skus"].append(sku_row)
            category_row["products"].append(product_row)
        result.append(category_row)
    output = {
        "contract_id": CONTRACT_ID,
        "payload_family": config.payload_family,
        "payload_version": config.payload_version,
        "category_pages": result,
    }
    if root_row.get("prices"):
        output["prices"] = root_row["prices"]
    return output


def parse_food(payload: Mapping[str, Any], config: FoodParserConfig) -> dict[str, Any]:
    """Parse one FOOD payload without joining it to another observation."""

    config.validate()
    if type(payload) is not dict:
        raise ParserError("UNSUPPORTED_PAYLOAD")
    poi_values = _select(payload, _tokenize(config.merchant_container))
    if len(poi_values) != 1 or type(poi_values[0]) is not dict:
        raise ParserError("MERCHANT_FIELD_MISSING")
    poi = poi_values[0]
    merchant = {
        "id": _bound_value(poi, config.merchant_id, config.merchant_container),
        "name": _bound_value(poi, config.merchant_name, config.merchant_container),
        "prices": {},
    }
    _apply_price_bindings(
        merchant,
        poi,
        "merchant",
        config.price_bindings,
        config.merchant_container,
    )
    _apply_price_bindings(
        merchant,
        poi,
        "coupon",
        config.price_bindings,
        config.merchant_container,
    )
    _apply_price_bindings(
        merchant,
        payload.get("data", {}),
        "root",
        config.price_bindings,
        "$.data",
    )
    _apply_extensions(
        merchant,
        poi,
        "merchant",
        config.observed_extensions,
        config.merchant_container,
    )
    _apply_extensions(
        merchant,
        payload.get("data", {}),
        "root",
        config.observed_extensions,
        "$.data",
    )
    return {
        "contract_id": "FOOD_CONFIGURABLE_INPUT_CONTRACT_V1",
        "payload_family": config.payload_family,
        "payload_version": config.payload_version,
        "merchant": merchant,
    }


def _bound_value(entity: Mapping[str, Any], binding: Binding, base: str) -> Any:
    tail = _relative_tokens(binding.path, base)
    values = _select(entity, tail)
    if not values:
        if not binding.required:
            return None
        raise ParserError("REQUIRED_FIELD_MISSING")
    if binding.many:
        for value in values:
            _expect(value, binding.types)
        return values
    if len(values) != 1:
        raise ParserError("FIELD_AMBIGUOUS")
    value = values[0]
    _expect(value, binding.types)
    return value


def _apply_price_bindings(
    row: dict[str, Any],
    entity: Mapping[str, Any],
    scope: str,
    bindings: Iterable[Binding],
    base: str,
) -> None:
    for binding in bindings:
        if binding.scope != scope:
            continue
        value = _bound_value(entity, binding, base)
        row.setdefault("prices", {})[binding.output_key or binding.name] = {
            "value": value,
            "source_label": binding.source_label,
        }


def _apply_extensions(
    row: dict[str, Any],
    entity: Mapping[str, Any],
    scope: str,
    bindings: Iterable[Binding],
    base: str,
) -> None:
    for binding in bindings:
        if binding.scope != scope:
            continue
        value = _bound_value(entity, binding, base)
        if binding.source_label is None:
            row.setdefault("extensions", {})[binding.output_key or binding.name] = value
        else:
            row.setdefault("extensions", {})[binding.output_key or binding.name] = {
                "value": value,
                "source_label": binding.source_label,
            }


def _required_direct(entity: Mapping[str, Any], key: str, types: Sequence[str]) -> Any:
    if key not in entity:
        raise ParserError("REQUIRED_FIELD_MISSING")
    value = entity[key]
    _expect(value, types)
    return value


def _one(node: Any, tokens: Sequence[str], missing_code: str) -> Any:
    values = _select(node, tokens)
    if not values:
        raise ParserError(missing_code)
    if len(values) != 1:
        raise ParserError("FIELD_AMBIGUOUS")
    return values[0]


def _expect(value: Any, types: Sequence[str]) -> None:
    actual = _json_type(value)
    # JSON numbers include integer values; bool remains distinct from both.
    if actual not in types and not (actual == "integer" and "number" in types):
        raise ParserError("TYPE_MISMATCH")


def _select(node: Any, tokens: Sequence[str]) -> list[Any]:
    values = [node]
    for token in tokens:
        next_values: list[Any] = []
        for value in values:
            if token == "*":
                if type(value) is list:
                    next_values.extend(value)
            elif type(value) is dict and token in value:
                next_values.append(value[token])
        values = next_values
    return values


def _tokenize(path: str) -> Tuple[str, ...]:
    if path == "$":
        return ()
    if not path.startswith("$."):
        raise ParserError("PARSER_CONFIG_INVALID")
    tokens: list[str] = []
    index = 1
    while index < len(path):
        if path.startswith("[*]", index):
            tokens.append("*")
            index += 3
            continue
        if path[index] != ".":
            raise ParserError("PARSER_CONFIG_INVALID")
        index += 1
        end = index
        while end < len(path) and path[end] not in ".[":
            end += 1
        key = path[index:end]
        if _KEY.fullmatch(key) is None:
            raise ParserError("PARSER_CONFIG_INVALID")
        tokens.append(key)
        index = end
    return tuple(tokens)


def _relative_tokens(path: str, prefix: str) -> Tuple[str, ...]:
    full = _tokenize(path)
    base = _tokenize(prefix)
    if full[: len(base)] != base:
        raise ParserError("PARSER_CONFIG_INVALID")
    return full[len(base) :]


def _require_prefix(path: str, prefix: str) -> None:
    _relative_tokens(path, prefix)


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    if type(value) is str:
        return "string"
    if type(value) is list:
        return "array"
    if type(value) is dict:
        return "object"
    return "unsupported"


def _is_sensitive_key(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "", value.casefold())
    return any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS)


def _safe_version_token(value: str) -> bool:
    return type(value) is str and bool(value) and len(value) <= 96 and _OUTPUT_KEY.fullmatch(value.replace("-", "_")) is not None
