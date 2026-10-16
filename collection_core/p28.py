"""Same-observation SKU identities and distinct prices over validated P0.

Only confirmed SKU-price units are normalized. Optional origin numbers are
source observations without an assigned price meaning; no discount, activity,
packaging, availability or SKU label is inferred from them.
"""

from decimal import Decimal, InvalidOperation
import re

from parser_candidate import ParserError, parse_capture_read_scope
from parser_candidate.p28_profile import FAMILY, VERSION, LABEL
from .p0 import P0Context, P0Error, build_p0_batch, validate_p0_batch

ROW_KEYS = frozenset((
    "p0_business_record_ref", "store_id", "product_id", "sku_id", "category_ref", "category_name",
    "sku_spec", "sku_spec_state", "sku_description", "sku_description_state",
    "product_unit_text", "product_unit_state", "sku_price_minor", "product_display_price_minor",
    "source_origin_price_number", "source_origin_price_state", "original_price_minor", "original_price_state",
    "activity_price_minor", "activity_price_state", "packaging_fee_minor", "packaging_fee_state",
    "availability_status", "availability_status_state", "promotion_state",
    "run_ref", "batch_ref", "observation_ref", "observed_at",
))
EVIDENCE_KEYS = frozenset(("schema_version", "basis", "evidence_ref", "currency", "amount_unit"))


class P28Error(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_price_evidence(evidence, source_kind):
    if (type(evidence) is not dict or set(evidence) != EVIDENCE_KEYS
            or evidence["schema_version"] != "p28-price-evidence/v1"
            or evidence["currency"] != "CNY" or evidence["amount_unit"] != "YUAN"
            or type(evidence["evidence_ref"]) is not str
            or re.fullmatch(r"evidence:[A-Za-z0-9_-]{8,96}", evidence["evidence_ref"]) is None):
        raise P28Error("P28_PRICE_EVIDENCE_REQUIRED")
    expected = "SYNTHETIC_RULE_TEST" if source_kind == "SYNTHETIC_OFFLINE_FIXTURE" else "USER_CONFIRMED_MULTI_SKU_PAGE"
    if evidence["basis"] != expected:
        raise P28Error("P28_PRICE_EVIDENCE_REQUIRED")


def build_p28_batch(events, registry, context, price_evidence):
    if type(context) is not P0Context or context.coverage_status != "PARTIAL":
        raise P28Error("P28_CONTEXT_INVALID")
    validate_price_evidence(price_evidence, context.source_kind)
    try:
        events = tuple(events)
        parsed = parse_capture_read_scope(events, registry)
        if parsed["payload_family"] != FAMILY or parsed["payload_version"] != VERSION:
            raise P28Error("P28_PROFILE_INVALID")
        if len(parsed["productlist_events"]) != 1:
            raise P28Error("P28_SINGLE_OBSERVATION_REQUIRED")
        # The version has one merchant container; no legacy/dual fallback.
        food = next(e.payload for e in events if e.endpoint_id == "FOOD")
        if (set(food.get("data", {})) & {"poi_info", "poi_base_info"}) != {"poi_info"}:
            raise P28Error("P28_PROFILE_INVALID")
        p0 = build_p0_batch(events, registry, context)
        # P28 alone gives source IDs typed opaque references and sufficiently
        # long record tokens. Preserve the old P0/P26 output byte contract.
        _version_p0_references(p0)
        rows, inventory = [], []
        records = iter(p0["business_records"])
        store_id = _text(parsed["merchant"]["id"])
        for category in parsed["productlist_events"][0]["category_pages"]:
            category_id = _text(category["category_id"])
            category_name = _text(_labeled(category, "category_name"))
            for product in category["products"]:
                base = next(records)
                minimum = money_minor(product["price"])
                if minimum != money_minor(_labeled(product, "render_min_price", prices=True)) or not product["skus"]:
                    raise P28Error("P28_PRICE_RELATION_INVALID")
                if minimum != min(money_minor(s["price"]) for s in product["skus"]):
                    raise P28Error("P28_PRICE_RELATION_INVALID")
                inventory.append({"p0_business_record_ref": base["business_record_ref"],
                                  "sku_ids": [str(s["id"]) for s in product["skus"]]})
                unit, unit_state = text_state(_labeled(product, "product_unit"))
                for sku in product["skus"]:
                    spec, spec_state = text_state(sku["spec"])
                    description, description_state = text_state(_labeled(sku, "sku_description"))
                    origin = _labeled(sku, "sku_origin_number", prices=True)
                    rows.append({
                        "p0_business_record_ref": base["business_record_ref"],
                        "store_id": store_id, "product_id": str(product["id"]), "sku_id": str(sku["id"]),
                        "category_ref": category_id, "category_name": category_name,
                        "sku_spec": spec, "sku_spec_state": spec_state,
                        "sku_description": description, "sku_description_state": description_state,
                        "product_unit_text": unit, "product_unit_state": unit_state,
                        "sku_price_minor": money_minor(sku["price"]), "product_display_price_minor": minimum,
                        "source_origin_price_number": None if origin is None else source_number(origin),
                        "source_origin_price_state": "NOT_OBSERVED" if origin is None else "SEMANTICS_UNCONFIRMED",
                        "original_price_minor": None, "original_price_state": "NOT_ADAPTED_OR_UNCONFIRMED",
                        "activity_price_minor": None, "activity_price_state": "NOT_ADAPTED_OR_UNCONFIRMED",
                        "packaging_fee_minor": None, "packaging_fee_state": "NOT_ADAPTED_OR_UNCONFIRMED",
                        "availability_status": None, "availability_status_state": "NOT_ADAPTED_OR_UNCONFIRMED",
                        "promotion_state": "NOT_ADAPTED_OR_UNCONFIRMED",
                        **{key: base[key] for key in ("run_ref", "batch_ref", "observation_ref", "observed_at")},
                    })
    except P28Error:
        raise
    except (ParserError, P0Error, KeyError, TypeError, ValueError, StopIteration):
        raise P28Error("P28_ASSEMBLY_INVALID") from None
    result = {"schema_version": "collection-p28-binding-batch/v1", "payload_family": FAMILY,
              "payload_version": VERSION, "p0_result": p0, "price_evidence": dict(price_evidence),
              "coverage_status": "PARTIAL", "coverage_scope": "CURRENT_LIST_RESPONSE_ONLY",
              "sku_inventory": inventory, "sku_records": rows}
    validate_p28_batch(result)
    return result


def validate_p28_batch(result):
    keys = {"schema_version", "payload_family", "payload_version", "p0_result", "price_evidence", "coverage_status", "coverage_scope", "sku_inventory", "sku_records"}
    if (type(result) is not dict or set(result) != keys
            or result["schema_version"] != "collection-p28-binding-batch/v1"
            or (result["payload_family"], result["payload_version"]) != (FAMILY, VERSION)
            or result["coverage_status"] != "PARTIAL" or result["coverage_scope"] != "CURRENT_LIST_RESPONSE_ONLY"):
        raise P28Error("P28_BATCH_INVALID")
    try:
        validate_p0_batch(result["p0_result"])
        batch = result["p0_result"]["observation_batch"]
        if (batch["payload_family"], batch["payload_version"]) != (FAMILY, VERSION) or batch["coverage_status"] != "PARTIAL":
            raise P28Error("P28_PROFILE_INVALID")
        validate_price_evidence(result["price_evidence"], batch["source_kind"])
        bases = {r["business_record_ref"]: r for r in result["p0_result"]["business_records"]}
        inventory = result["sku_inventory"]
        if type(inventory) is not list or len(inventory) != len(bases):
            raise P28Error("P28_PARTIAL_RECORD_INVALID")
        expected = {}
        for entry in inventory:
            if (type(entry) is not dict or set(entry) != {"p0_business_record_ref", "sku_ids"}
                    or type(entry["p0_business_record_ref"]) is not str
                    or entry["p0_business_record_ref"] not in bases
                    or entry["p0_business_record_ref"] in expected
                    or type(entry["sku_ids"]) is not list or not 1 <= len(entry["sku_ids"]) <= 40000
                    or any(type(s) is not str or re.fullmatch(r"-?[0-9]+", s) is None for s in entry["sku_ids"])
                    or len(set(entry["sku_ids"])) != len(entry["sku_ids"])):
                raise P28Error("P28_PARTIAL_RECORD_INVALID")
            expected[entry["p0_business_record_ref"]] = set(entry["sku_ids"])
        rows = result["sku_records"]
        if type(rows) is not list or not 1 <= len(rows) <= 40000:
            raise P28Error("P28_BATCH_INVALID")
        grouped, categories, owners, products, product_names = {}, {}, {}, {}, {}
        for row in rows:
            if type(row) is not dict or set(row) != ROW_KEYS:
                raise P28Error("P28_RECORD_INVALID")
            base = bases[row["p0_business_record_ref"]]
            fields = {f["field_name"]: f["normalized_value"] for f in base["field_observations"]}
            if (_identity_ref("store", row["store_id"]) != fields["store_ref"]
                    or _identity_ref("product", row["product_id"]) != fields["product_ref"]
                    or row["product_display_price_minor"] != fields["display_price_minor"]
                    or any(row[k] != base[k] for k in ("run_ref", "batch_ref", "observation_ref", "observed_at"))):
                raise P28Error("P28_OWNER_OR_OBSERVATION_INVALID")
            for k in ("store_id", "product_id", "sku_id", "category_ref", "category_name"):
                _text(row[k])
            if re.fullmatch(r"-?[0-9]+", row["sku_id"]) is None:
                raise P28Error("P28_RECORD_INVALID")
            for key in ("sku_price_minor", "product_display_price_minor"):
                if type(row[key]) is not int or not 0 <= row[key] <= 10**12:
                    raise P28Error("P28_PRICE_INVALID")
            for name, state in (("sku_spec", "sku_spec_state"), ("sku_description", "sku_description_state"), ("product_unit_text", "product_unit_state")):
                if text_state(row[name])[1] != row[state]:
                    raise P28Error("P28_PRESENCE_INVALID")
            origin = row["source_origin_price_number"]
            if row["source_origin_price_state"] != ("NOT_OBSERVED" if origin is None else "SEMANTICS_UNCONFIRMED"):
                raise P28Error("P28_PRESENCE_INVALID")
            if origin is not None and (type(origin) is not str or not Decimal(origin).is_finite() or str(Decimal(origin)) != origin):
                raise P28Error("P28_PRICE_INVALID")
            for value, state in (("original_price_minor", "original_price_state"), ("activity_price_minor", "activity_price_state"), ("packaging_fee_minor", "packaging_fee_state"), ("availability_status", "availability_status_state")):
                if row[value] is not None or row[state] != "NOT_ADAPTED_OR_UNCONFIRMED":
                    raise P28Error("P28_UNCONFIRMED_VALUE_INVALID")
            if row["promotion_state"] != "NOT_ADAPTED_OR_UNCONFIRMED":
                raise P28Error("P28_UNCONFIRMED_VALUE_INVALID")
            category_key = (row["store_id"], row["category_ref"])
            if categories.setdefault(category_key, row["category_name"]) != row["category_name"]:
                raise P28Error("P28_CATEGORY_CONFLICT")
            owner = (row["store_id"], row["product_id"])
            if product_names.setdefault(owner, fields["product_name"]) != fields["product_name"]:
                raise P28Error("P28_CROSS_CATEGORY_CONFLICT")
            sku_key = (row["store_id"], row["sku_id"])
            if owners.setdefault(sku_key, owner) != owner:
                raise P28Error("P28_SKU_OWNER_CONFLICT")
            group = grouped.setdefault(row["p0_business_record_ref"], {})
            if row["sku_id"] in group:
                raise P28Error("P28_SKU_DUPLICATE")
            group[row["sku_id"]] = row
        if set(grouped) != set(bases) or any(set(grouped[ref]) != expected[ref] for ref in grouped):
            raise P28Error("P28_PARTIAL_RECORD_INVALID")
        seen_pairs = set()
        for ref, group in grouped.items():
            first = next(iter(group.values()))
            if any(r["category_ref"] != first["category_ref"] or r["product_unit_text"] != first["product_unit_text"] for r in group.values()):
                raise P28Error("P28_OWNER_OR_OBSERVATION_INVALID")
            if first["product_display_price_minor"] != min(r["sku_price_minor"] for r in group.values()):
                raise P28Error("P28_PRICE_RELATION_INVALID")
            pair = (first["store_id"], first["product_id"], first["category_ref"])
            if pair in seen_pairs:
                raise P28Error("P28_PRODUCT_CATEGORY_DUPLICATE")
            seen_pairs.add(pair)
            signature = {sid: {k: r[k] for k in ROW_KEYS - {"p0_business_record_ref", "category_ref", "category_name"}} for sid, r in group.items()}
            owner = (first["store_id"], first["product_id"])
            if products.setdefault(owner, signature) != signature:
                raise P28Error("P28_CROSS_CATEGORY_CONFLICT")
    except P28Error:
        raise
    except (P0Error, KeyError, TypeError, ValueError, InvalidOperation):
        raise P28Error("P28_BATCH_INVALID") from None


def _labeled(row, key, *, prices=False):
    value = row.get("prices" if prices else "extensions", {}).get(key)
    if type(value) is not dict or value.get("source_label") != LABEL or set(value) != {"value", "source_label"}:
        raise P28Error("P28_SOURCE_LABEL_INVALID")
    return value["value"]


def _identity_ref(kind, source_id):
    if type(source_id) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,88}", source_id) is None:
        raise P28Error("P28_IDENTITY_INVALID")
    return f"{kind}:meituan_{source_id}"


def _version_p0_references(p0):
    for field in p0["field_observations"]:
        if field["field_name"] in {"store_ref", "product_ref"}:
            kind = field["field_name"].removesuffix("_ref")
            field["normalized_value"] = _identity_ref(kind, field["normalized_value"])
    for ordinal, record in enumerate(p0["business_records"], 1):
        record["business_record_ref"] = f"business-record:p28_{ordinal:05d}"
    p0["observation_batch"]["business_record_refs"] = [r["business_record_ref"] for r in p0["business_records"]]
    validate_p0_batch(p0)


def _text(value, *, empty=False):
    if type(value) is not str or (not empty and not value) or len(value) > 256 or any(t in value for t in ("\n", "\r", "://", "\x00")):
        raise P28Error("P28_TEXT_INVALID")
    return value


def text_state(value):
    if value is None:
        return None, "NOT_OBSERVED"
    _text(value, empty=True)
    return value, "SOURCE_EMPTY" if value == "" else "PRESENT"


def source_number(value):
    if type(value) not in (int, float):
        raise P28Error("P28_PRICE_INVALID")
    number = Decimal(str(value))
    if not number.is_finite():
        raise P28Error("P28_PRICE_INVALID")
    return str(number)


def money_minor(value):
    number = Decimal(source_number(value)) * 100
    if number < 0 or number > 10**12 or number != number.to_integral_value():
        raise P28Error("P28_PRICE_INVALID")
    return int(number)
