"""Bounded, short-lived FORM keys for the two currently observed shop routes.

Values are opaque until the developer chooses an observed non-sensitive routing
key. That scalar is compared only to the current public store response IDs.
Request bodies never become output artifacts, fixtures or logs.
"""
from urllib.parse import unquote_to_bytes
import unicodedata
from .p26_identification import IdentificationError, BodyCollector, MAX_RESPONSES, _private_key, _shape_key, _normalized
from .observation_time import observation_clock


class RequestBudget:
    def __init__(self, window):
        self.window = window

    @property
    def encoded_bytes(self): return self.window.request_encoded_bytes
    @encoded_bytes.setter
    def encoded_bytes(self,value): self.window.request_encoded_bytes=value
    @property
    def decoded_bytes(self): return self.window.request_decoded_bytes
    @decoded_bytes.setter
    def decoded_bytes(self,value): self.window.request_decoded_bytes=value

    @property
    def last_clock(self): return self.window.last_clock
    def active(self): return self.window.active()
    def close(self, code): self.window.close(code)


def form_keys(body: bytes) -> list[str]:
    result = []
    for pair in body.split(b"&"):
        if not pair: continue
        try: key = unquote_to_bytes(pair.partition(b"=")[0].replace(b"+", b" ")).decode("ascii")
        except (UnicodeError, ValueError): raise IdentificationError("P26_STRUCTURE_INVALID") from None
        if _shape_key(key) != key or key in result or len(result) >= 128:
            raise IdentificationError("P26_STRUCTURE_INVALID")
        result.append(key)
    return result


def begin_form_metadata(window, budget, request_ref: str, route: int, layouts: list):
    if not window.active():
        window.close("P26_RESPONSE_COUNT_LIMIT")
        return None
    # Rejected response headers never reach begin_response's selected-route
    # pruning. Count only live collectors here, including both directions.
    window.collectors = [collector for collector in window.collectors if not collector.finished]
    if len(window.collectors) >= MAX_RESPONSES:
        window.close("P26_RESPONSE_COUNT_LIMIT")
        return None
    def consume(body):
        keys = form_keys(body)
        window.request_metadata_bodies_at_least |= window.request_metadata_bodies>=8
        window.request_metadata_bodies=min(8,window.request_metadata_bodies+1)
        layouts.append({"request_ref":request_ref,"route_slot":route,"keys":keys,
                        "field_values_processed":False})
        del layouts[:-8]
        window.request_leases[request_ref] = {"body":body,"keys":keys,"route_slot":route,
                                             "expires_at":observation_clock(window.last_clock)+60}
        while len(window.request_leases)>8: window.request_leases.pop(next(iter(window.request_leases)))
    collector = BodyCollector(budget,"identity",consume)
    window.collectors.append(collector)
    return collector


def inspect_current_store_parameter(window, request_ref: str, field: str) -> dict:
    if (not window.active() or request_ref not in window.request_leases or type(field) is not str
            or _private_key(field) or _shape_key(field)!=field):
        raise IdentificationError("P26_PUBLIC_PROBE_UNAVAILABLE")
    if _normalized(field) not in {"wmpoiid","poiid","poiidstr","shopid","storeid"}:
        raise IdentificationError("P26_PUBLIC_PROBE_INVALID")
    lease=window.request_leases[request_ref]
    if field not in lease["keys"]: raise IdentificationError("P26_PUBLIC_PROBE_INVALID")
    normalize=lambda value:unicodedata.normalize("NFKC",value).replace(" ","")
    name_paths={"$.data."+container+".name" for container in ("poi_base_info","poi_info")}
    store_rows=[row for row in window.projected_observations if any(
        value['path'] in name_paths and type(value['value']) is str
        and normalize(value['value'])==normalize(window.expected_store) for value in row['values'])]
    id_paths={"$.data."+container+"."+key for container in ("poi_base_info","poi_info")
              for key in ("id","poi_id_str")}
    ids = {value["path"]:str(value["value"]) for row in store_rows for value in row["values"]
           if value["path"] in id_paths}
    if not ids: raise IdentificationError("P26_PUBLIC_PROBE_UNAVAILABLE")
    selected = None
    for pair in lease["body"].split(b"&"):
        key=unquote_to_bytes(pair.partition(b"=")[0].replace(b"+",b" ")).decode("ascii")
        if key==field:
            try: selected=unquote_to_bytes(pair.partition(b"=")[2].replace(b"+",b" ")).decode("ascii")
            except UnicodeError: raise IdentificationError("P26_PUBLIC_PROBE_INVALID") from None
            break
    # This API neither exports unmatched values nor inspects another parameter.
    matched_paths = sorted(path for path, value in ids.items() if selected == value)
    match = bool(matched_paths)
    return {"request_ref":request_ref,"field":field,"matches_current_public_store_id":match,
            "matched_public_id_paths":matched_paths,
            "role":"CURRENT_STORE_ROUTING_ID" if match else "UNKNOWN",
            "sensitive_values_processed":False}
