"""Candidate profile pinned to the current P26 observed shop responses.

This registry has no source capability or formal Parser/Provider qualification.
Its required paths/types come from windows 16/19; monetary readiness is a
separate caller precondition, not a default inferred by this registry.
"""
from .parser import Binding, FoodParserConfig, ParserConfig, ParserError
from .registry import ParserRegistry

FAMILY = "meituan_wechat_miniprogram"
VERSION = "p26-observed-shop-v1"
VERSION_V2 = "p26-observed-shop-v2"
PRODUCT = "$.data.food_spu_tags[*].dynamic_spus[*]"


def p26_registry(version=VERSION) -> ParserRegistry:
    if version not in (VERSION, VERSION_V2):
        raise ParserError("PARSER_PROFILE_UNREGISTERED")
    container = "$.data.poi_info" if version == VERSION_V2 else "$.data.poi_base_info"
    food = FoodParserConfig(
        payload_family=FAMILY, payload_version=version,
        merchant_container=container,
        merchant_id=Binding("merchant_id", container + ".poi_id_str", ("string",), "merchant"),
        merchant_name=Binding("merchant_name", container + ".name", ("string",), "merchant"),
    )
    product = ParserConfig(
        payload_family=FAMILY, payload_version=version,
        category_id=Binding("category_id", "$.data.food_spu_tags[*].tag", ("string",), "category"),
        product_price=Binding("product_price", PRODUCT + ".min_price", ("number",), "product"),
        sku_price=Binding("sku_price", PRODUCT + ".skus[*].price", ("number",), "sku"),
        sku_status_types=("number",),
    )
    return ParserRegistry((product,), (food,))
