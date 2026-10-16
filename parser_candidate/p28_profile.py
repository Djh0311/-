"""Explicit candidate mapping of the P26-authorized public SKU scalars.

This is a new local observation-rule version, not a platform version or a
source capability. Empty SKU labels remain empty; product unit text is not a
SKU label. The optional status field has no interpreted availability enum.
"""

from .parser import Binding, FoodParserConfig, ParserConfig
from .registry import ParserRegistry

FAMILY = "meituan_wechat_miniprogram"
VERSION = "p28-observed-shop-sku-v1"
CATEGORY = "$.data.food_spu_tags[*]"
PRODUCT = CATEGORY + ".dynamic_spus[*]"
SKU = PRODUCT + ".skus[*]"
LABEL = "P28_OBSERVED_PUBLIC_SCALAR"


def p28_registry() -> ParserRegistry:
    product = ParserConfig(
        payload_family=FAMILY, payload_version=VERSION,
        category_id=Binding("category_id", CATEGORY + ".tag", ("string",), "category"),
        product_price=Binding("product_price", PRODUCT + ".min_price", ("number",), "product"),
        sku_price=Binding("sku_price", SKU + ".price", ("number",), "sku"),
        sku_status_types=("number",), sku_status_required=False,
        observed_extensions=(
            Binding("category_name", CATEGORY + ".name", ("string",), "category", source_label=LABEL),
            Binding("product_unit", PRODUCT + ".unit", ("string",), "product", required=False, source_label=LABEL),
            Binding("sku_description", SKU + ".spec_desc", ("string",), "sku", required=False, source_label=LABEL),
        ),
        price_bindings=(
            Binding("render_min_price", PRODUCT + ".render_info.price_info.min_price", ("number",), "product", source_label=LABEL),
            Binding("sku_origin_number", SKU + ".origin_price", ("number",), "sku", required=False, source_label=LABEL),
        ),
    )
    poi = "$.data.poi_info"
    food = FoodParserConfig(
        payload_family=FAMILY, payload_version=VERSION, merchant_container=poi,
        merchant_id=Binding("merchant_id", poi + ".poi_id_str", ("string",), "merchant"),
        merchant_name=Binding("merchant_name", poi + ".name", ("string",), "merchant"),
    )
    return ParserRegistry((product,), (food,)).validate()
