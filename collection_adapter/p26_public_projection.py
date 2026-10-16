"""Public scalar inspection paths observed in P26 window 16, not a Parser profile.

The field names/types were read from the current authorised key layout. No
source value, monetary unit, currency or product/store association is inferred.
"""

FOOD_ROUTE = "/weapp/v1/poi/food"
PRODUCT_ROUTE = "/weapp/shop/v1/poi/productlist"
# The first host is the original shop API. The others appeared on the current
# single applet and already serve the same public POST routes. Logs, images,
# and messaging hosts are intentionally absent.
BUSINESS_DOMAINS = (
    "wx.waimai.meituan.com",
    "hcapi-wx.waimai.meituan.com",
    "apimobile.meituan.com",
    "web.meituan.com",
    "open.meituan.com",
)


def is_business_origin(origin: str) -> bool:
    return origin in BUSINESS_DOMAINS
PUBLIC_ID_PATHS = frozenset("$.data." + container + "." + field
    for container in ("poi_base_info", "poi_info") for field in ("id", "poi_id_str", "name"))

_PRODUCT = "$.data.food_spu_tags[].dynamic_spus[]"
PUBLIC_PATHS = {
    # Both containers were directly observed (19 and 21). Discovery reports
    # which one exists; this union is not a fallback rule for result parsing.
    FOOD_ROUTE: frozenset({"$.code"}) | PUBLIC_ID_PATHS,
    PRODUCT_ROUTE: frozenset({"$.code", "$.data.food_spu_tags[].tag", "$.data.food_spu_tags[].name",
                             "$.data.food_spu_tags[].current_page", "$.data.food_spu_tags[].has_next_page",
                             "$.data.food_spu_tags[].product_count"}
        | {_PRODUCT + "." + field for field in ("id", "name", "unit", "min_price", "status")}
        | {_PRODUCT + ".skus[]." + field for field in ("id", "spec", "spec_desc", "price", "origin_price", "price_desc")}
        | {_PRODUCT + ".render_info.price_info." + field for field in (
            "min_price", "min_price_tail", "origin_price", "price_desc", "price_desc_tag")}),
}

# The SKU status key/type was directly observed in windows 16 and 19. A result
# projection requires it for the existing strict candidate contract. The URL
# price tag diagnosed in window 19 is unnecessary for the basic price record.
RESULT_PATHS = {
    FOOD_ROUTE: frozenset({"$.code","$.data.poi_base_info.name","$.data.poi_base_info.poi_id_str",
                           "$.data.poi_base_info.id"}),
    PRODUCT_ROUTE: frozenset({"$.code","$.data.food_spu_tags[].tag","$.data.food_spu_tags[].name",
        "$.data.food_spu_tags[].current_page","$.data.food_spu_tags[].has_next_page"}
        | {_PRODUCT+"."+f for f in ("id","name","min_price")}
        | {_PRODUCT+".skus[]."+f for f in ("id","spec","price","status")}
        | {_PRODUCT+".render_info.price_info."+f for f in ("min_price","min_price_tail","price_desc")}),
}
RESULT_PATHS_V2 = {**RESULT_PATHS, FOOD_ROUTE: frozenset({"$.code"}) | PUBLIC_ID_PATHS}
RESULT_PATHS_BY_VERSION = {"p26-observed-shop-v1": RESULT_PATHS,
                           "p26-observed-shop-v2": RESULT_PATHS_V2}


def validate_observed_paths(layouts: list[dict]) -> bool:
    """Check a new policy against actual field definitions, never a fixture."""
    observed = {row["route_slot"]: {field["path"] for field in row["fields"]} for row in layouts}
    return PUBLIC_PATHS[FOOD_ROUTE] <= observed.get(4, set()) and PUBLIC_PATHS[PRODUCT_ROUTE] <= observed.get(3, set())
