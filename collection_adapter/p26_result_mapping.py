"""Pure mapping of fresh, whitelisted P26 scalars into the candidate boundary."""
from decimal import Decimal
import re
import unicodedata
from urllib.parse import unquote_to_bytes

from parser_candidate import CaptureParserEvent
from parser_candidate.p26_profile import FAMILY, VERSION, VERSION_V2
from .p26_identification import IdentificationError
from .p26_public_projection import (FOOD_ROUTE, PRODUCT_ROUTE, RESULT_PATHS, RESULT_PATHS_V2,
    PUBLIC_ID_PATHS, is_business_origin)

_PART = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)(\[\])?")


def restore_projection(row, route, *, allowed_paths=None):
    """Restore only observed coordinates; missing values are never synthesized."""
    if row.get("unavailable_fields"):
        raise IdentificationError("P26_RESULT_MAPPING_INVALID")
    result = {}
    seen = set()
    for field in row["values"]:
        path, coords, value = field["path"], field["coordinates"], field["value"]
        if path not in (RESULT_PATHS[route] if allowed_paths is None else allowed_paths) or type(coords) is not list or not coords:
            raise IdentificationError("P26_RESULT_MAPPING_INVALID")
        parts = list(_PART.finditer(path[1:]))
        if "".join(p.group(0) for p in parts) != path[1:]:
            raise IdentificationError("P26_RESULT_MAPPING_INVALID")
        expected = []
        for part in parts:
            expected.append(part.group(1))
            if part.group(2): expected.append(None)
        if len(expected)!=len(coords) or any((type(c) is not int or not 0<=c<40000) if e is None
                                             else c!=e for e,c in zip(expected,coords)):
            raise IdentificationError("P26_RESULT_MAPPING_INVALID")
        key = tuple(coords)
        if key in seen: raise IdentificationError("P26_RESULT_MAPPING_INVALID")
        seen.add(key)
        target = result
        for index, part in enumerate(coords):
            if type(target) is list:
                if type(part) is not int: raise IdentificationError("P26_RESULT_MAPPING_INVALID")
                target.extend([None]*(part+1-len(target)))
            elif type(target) is not dict or type(part) is not str:
                raise IdentificationError("P26_RESULT_MAPPING_INVALID")
            if index==len(coords)-1:
                target[part]=value
            else:
                next_type=list if type(coords[index+1]) is int else dict
                child=target[part] if type(target) is list else target.get(part)
                if child is None: child=next_type(); target[part]=child
                if type(child) is not next_type: raise IdentificationError("P26_RESULT_MAPPING_INVALID")
                target=child
    return result


def current_routing_id(window, row, field="wm_poi_id"):
    if field not in {"wm_poi_id","poi_id_str"}:
        raise IdentificationError("P26_RESULT_SOURCE_ASSOCIATION_INVALID")
    ref=row.get("source_request_ref")
    lease=window.request_leases.get(ref)
    if not lease or lease["route_slot"]!=row["route_slot"] or lease["expires_at"]<=window.last_clock:
        raise IdentificationError("P26_RESULT_SOURCE_ASSOCIATION_INVALID")
    if field not in lease["keys"]:
        raise IdentificationError("P26_RESULT_SOURCE_ASSOCIATION_INVALID")
    # This key was observed and compared in window 19. Other FORM values,
    # including private/session/credential fields, remain encoded and opaque.
    for pair in lease["body"].split(b"&"):
        key=unquote_to_bytes(pair.partition(b"=")[0].replace(b"+",b" ")).decode("ascii")
        if key==field:
            try: value=unquote_to_bytes(pair.partition(b"=")[2].replace(b"+",b" ")).decode("ascii")
            except UnicodeError: raise IdentificationError("P26_RESULT_SOURCE_ASSOCIATION_INVALID") from None
            if not value or len(value)>256:
                raise IdentificationError("P26_RESULT_SOURCE_ASSOCIATION_INVALID")
            return value
    raise IdentificationError("P26_RESULT_SOURCE_ASSOCIATION_INVALID")


def check_current_association(window):
    """Value-free checks of the two already-observed public routing keys.

    Each comparison names its exact response field. A placeholder match or
    equality between requests cannot masquerade as the configured identity.
    """
    rows={window.routes[r["route_slot"]][2]:r for r in window.projected_observations}
    if set(rows)!={FOOD_ROUTE,PRODUCT_ROUTE}:
        return None
    def identity_projection(route):
        wanted={"$.code"}
        if route==FOOD_ROUTE:
            wanted |= PUBLIC_ID_PATHS
        row=rows[route]
        return restore_projection({**row,"values":[f for f in row["values"] if f["path"] in wanted],
            "unavailable_fields":[f for f in row.get("unavailable_fields",[]) if f["path"] in wanted]},route,
            allowed_paths=wanted)
    food=identity_projection(FOOD_ROUTE)
    product=identity_projection(PRODUCT_ROUTE)
    containers=[key for key in ("poi_base_info","poi_info") if key in food.get("data",{})]
    container=containers[0] if len(containers)==1 else None
    merchant=food.get("data",{}).get(container,{}) if container else {}
    public_id=merchant.get("poi_id_str");placeholder=merchant.get("id")
    name=merchant.get("name")
    normalize=lambda value:unicodedata.normalize("NFKC",value).replace(" ","")
    result={"schema_version":"p26-result-association-check/v1",
        "window_ref":window.window_ref,"store_name_match":type(name)is str and normalize(name)==normalize(window.expected_store),
        "merchant_container":"$.data."+container if container else "AMBIGUOUS" if containers else "NOT_PROJECTED",
        "public_string_id_ready":type(public_id)is str and bool(public_id),
        "numeric_id_is_negative":type(placeholder)in (int,float) and placeholder<0,
        "public_id_fields_equal_as_text":None if placeholder is None or public_id is None else str(placeholder)==public_id,
        "food_success_code":type(food.get("code"))is int and food["code"]==0,
        "product_success_code":type(product.get("code"))is int and product["code"]==0,
        "same_observation_gap_valid":abs(rows[FOOD_ROUTE]["expires_at"]-rows[PRODUCT_ROUTE]["expires_at"])<=10,
        "raw_payload_persisted":False,"sensitive_values_processed":False}
    for key in ("wm_poi_id","poi_id_str"):
        selected={}
        for label,route in (("food",FOOD_ROUTE),("product",PRODUCT_ROUTE)):
            try: selected[label]=current_routing_id(window,rows[route],key)
            except IdentificationError: selected[label]=None
            value=selected[label]
            result[label+"_"+key+"_ready"]=value is not None
            result[label+"_"+key+"_matches_public_string_id"]=None if value is None or type(public_id)is not str else value==public_id
            result[label+"_"+key+"_matches_numeric_id"]=None if value is None or placeholder is None else value==str(placeholder)
        result[key+"_equal_between_requests"]=None if any(v is None for v in selected.values()) else selected["food"]==selected["product"]
    return result


def map_current_observation(window, profile_ref, read_scope, observation_scope, *, profile=None):
    v2 = profile is not None and profile["payload_version"] == VERSION_V2
    container = "poi_info" if v2 else "poi_base_info"
    routing_key = "poi_id_str" if v2 else "wm_poi_id"
    rows=window.projected_observations
    if len(rows)!=2: raise IdentificationError("P26_RESULT_EVENT_SET_INVALID")
    routes={}
    for row in rows:
        method,_,route=window.routes[row["route_slot"]]
        if method!="POST" or not is_business_origin(window.route_origins[row["route_slot"]]) or route in routes:
            raise IdentificationError("P26_RESULT_EVENT_SET_INVALID")
        routes[route]=row
    if set(routes)!={FOOD_ROUTE,PRODUCT_ROUTE}:
        raise IdentificationError("P26_RESULT_EVENT_SET_INVALID")
    food_row,product_row=routes[FOOD_ROUTE],routes[PRODUCT_ROUTE]
    if abs(food_row["expires_at"]-product_row["expires_at"])>10:
        raise IdentificationError("P26_RESULT_SOURCE_ASSOCIATION_INVALID")
    food=restore_projection(food_row,FOOD_ROUTE,
                            allowed_paths=RESULT_PATHS_V2[FOOD_ROUTE] if v2 else None)
    products=restore_projection(product_row,PRODUCT_ROUTE)
    try:
        if v2 and (set(food.get("data",{})) & {"poi_info","poi_base_info"}) != {"poi_info"}:
            raise IdentificationError("P26_RESULT_SOURCE_ASSOCIATION_INVALID")
        merchant=food["data"][container]
        store_id,name=merchant["poi_id_str"],merchant["name"]
        normalize=lambda value:unicodedata.normalize("NFKC",value).replace(" ","")
        if (type(food["code"]) is not int or food["code"]!=0 or type(products["code"]) is not int
            or products["code"]!=0 or type(store_id) is not str or not store_id
            or type(name) is not str or normalize(name)!=normalize(window.expected_store)
            or any(current_routing_id(window,r,routing_key)!=store_id for r in rows)):
            raise IdentificationError("P26_RESULT_SOURCE_ASSOCIATION_INVALID")
        if v2 and (type(merchant.get("id")) is not int
                   or any(current_routing_id(window,r,"wm_poi_id")!=str(merchant["id"]) for r in rows)):
            raise IdentificationError("P26_RESULT_SOURCE_ASSOCIATION_INVALID")
        details=[]
        for category in products["data"]["food_spu_tags"]:
            for product in category.get("dynamic_spus",[]):
                price=product["min_price"]
                rendered=product["render_info"]["price_info"]
                sku_prices=[s["price"] for s in product["skus"]]
                if (type(price) not in {int,float} or not sku_prices or price!=rendered["min_price"]
                    or price!=min(sku_prices) or not Decimal(str(price)).is_finite()
                    or price<0 or Decimal(str(price))*100!=(Decimal(str(price))*100).to_integral_value()):
                    raise IdentificationError("P26_RESULT_PRICE_RULE_CHANGED")
                details.append({"store_id":store_id,"product_id":str(product["id"]),
                    "category_ref":category["tag"],"category_name":category["name"],
                    "price_suffix":rendered.get("min_price_tail"),
                    "price_description":rendered.get("price_desc")})
        if not details: raise IdentificationError("P26_RESULT_EVENT_SET_INVALID")
    except IdentificationError:
        raise
    except (KeyError,TypeError,ValueError):
        raise IdentificationError("P26_RESULT_MAPPING_INVALID") from None
    proof={"schema_version":"p26-source-observation-proof/v2" if v2 else "p26-source-observation-proof/v1","window_ref":window.window_ref,
        "profile_ref":profile_ref,"read_scope":read_scope,"observation_scope":observation_scope,
        "food_request_ref":food_row["source_request_ref"],"product_request_ref":product_row["source_request_ref"],
        "food_projection_ref":food_row["projection_ref"],"product_projection_ref":product_row["projection_ref"],
        "food_observed_at":food_row["observed_at"],"product_observed_at":product_row["observed_at"],
        "store_name_match":True,"food_parameter_match":True,"product_parameter_match":True,
        "routing_parameter_key":routing_key,
        "same_observation_rule":"FRESH_WINDOW_FIRST_PAIR_SAME_PUBLIC_STORE_WITHIN_10_SECONDS",
        "price_relation":"SPU_MIN_EQUALS_RENDER_AND_MIN_SKU",
        "sensitive_values_processed":False,"raw_payload_persisted":False}
    if v2:
        proof.update(payload_version=VERSION_V2,merchant_container="$.data.poi_info",
            secondary_routing_parameter_key="wm_poi_id",secondary_response_id_path="$.data.poi_info.id",
            food_secondary_parameter_match=True,product_secondary_parameter_match=True)
    events=[CaptureParserEvent(read_scope=read_scope,observation_scope=observation_scope,event_index=i,
              endpoint_id=endpoint,payload_family=FAMILY,payload_version=VERSION_V2 if v2 else VERSION,payload=payload)
            for i,endpoint,payload in [(1,"FOOD",food),(2,"PRODUCTLIST",products)]]
    return events,details,proof
