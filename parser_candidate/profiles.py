"""Explicit offline Parser profiles for known value-free shapes."""

from __future__ import annotations

from .parser import Binding, FoodParserConfig, ParserConfig


def h31_productlist_config() -> ParserConfig:
    """Return the candidate PRODUCTLIST profile for ``h31-shape-v1``."""

    product_base = "$.data.food_spu_tags[*].dynamic_spus[*]"
    sku_base = product_base + ".skus[*]"
    product_prices = (
        ("full_discount_price", product_base + ".full_discount_price", "H31_PRODUCTLIST_SPU"),
        ("min_price", product_base + ".min_price", "H31_PRODUCTLIST_SPU"),
        (
            "preferential_feeling_price",
            product_base + ".preferential_feeling_price",
            "H31_PRODUCTLIST_SPU",
        ),
        (
            "display_price",
            product_base + ".render_data.component_data.price_component.price[*].price",
            "H31_PRODUCTLIST_PRICE_COMPONENT",
        ),
        (
            "display_underline_price",
            product_base + ".render_data.component_data.price_component.price[*].underline_price",
            "H31_PRODUCTLIST_PRICE_COMPONENT",
        ),
        (
            "coupons_per_price",
            product_base + ".render_info.price_info.coupons_per_price",
            "H31_PRODUCTLIST_RENDER_INFO_PRICE_INFO",
        ),
        (
            "render_min_price",
            product_base + ".render_info.price_info.min_price",
            "H31_PRODUCTLIST_RENDER_INFO_PRICE_INFO",
        ),
        (
            "multi_activity_price",
            product_base + ".render_info.price_info.multi_activity_price",
            "H31_PRODUCTLIST_RENDER_INFO_PRICE_INFO",
        ),
        (
            "render_origin_price",
            product_base + ".render_info.price_info.origin_price",
            "H31_PRODUCTLIST_RENDER_INFO_PRICE_INFO",
        ),
        (
            "show_origin_price",
            product_base + ".render_info.price_info.show_origin_price",
            "H31_PRODUCTLIST_RENDER_INFO_PRICE_INFO",
        ),
        (
            "discount_by_count_discount",
            product_base + ".activity_policy.discount_by_count.discount",
            "H31_PRODUCTLIST_SPU",
        ),
        (
            "max_discount",
            product_base + ".max_discount",
            "H31_PRODUCTLIST_SPU",
        ),
    )
    sku_prices = (
        ("box_price", sku_base + ".box_price"),
        ("full_discount_price", sku_base + ".full_discount_price"),
        ("member_price", sku_base + ".member_price"),
        ("origin_price", sku_base + ".origin_price"),
        ("price", sku_base + ".price"),
        (
            "ladder_package_price",
            sku_base + ".sku_ladder_box_info.ladder_package_price",
        ),
        (
            "discount_by_count_discount",
            sku_base + ".activity_policy.discount_by_count.discount",
        ),
    )
    bindings = [
        Binding(
            name,
            path,
            ("number",),
            "product",
            required=False,
            source_label=source,
            many="[*].price" in path or "[*].underline_price" in path,
        )
        for name, path, source in product_prices
    ]
    bindings.extend(
        Binding(
            name,
            path,
            ("number",),
            "sku",
            required=False,
            source_label="H31_PRODUCTLIST_SKU",
        )
        for name, path in sku_prices
    )
    bindings.extend(
        Binding(
            name,
            path,
            ("number",),
            "root",
            required=False,
            source_label="H31_PRODUCTLIST_RENDER_CONTEXT",
        )
        for name, path in (
            ("render_context_min_price", "$.data.render_context.min_price"),
            ("delivery_fee", "$.data.render_context.delivery_fee"),
            ("final_reduced_shipping_fee", "$.data.render_context.final_reduced_shipping_fee"),
        )
    )
    return ParserConfig(
        payload_family="meituan_wechat_miniprogram",
        payload_version="h31-shape-v1",
        category_id=Binding(
            "category_id",
            "$.data.food_spu_tags[*].tag",
            ("string",),
            "category",
        ),
        product_price=Binding(
            "product_price",
            product_base + ".min_price",
            ("number",),
            "product",
        ),
        sku_price=Binding(
            "sku_price",
            sku_base + ".price",
            ("number",),
            "sku",
        ),
        price_bindings=tuple(bindings),
    )


def h31_food_config() -> FoodParserConfig:
    """Return the candidate FOOD profile for ``h31-shape-v1``."""

    poi = "$.data.poi_info"
    bindings = (
        Binding(
            "poi_min_price",
            poi + ".min_price",
            ("number",),
            "merchant",
            required=False,
            source_label="H31_FOOD_POI_INFO",
        ),
        Binding(
            "shipping_fee",
            poi + ".shipping_fee",
            ("number",),
            "merchant",
            required=False,
            source_label="H31_FOOD_POI_INFO",
        ),
        Binding(
            "shipping_reduce_fee",
            poi + ".shippingReduceFee",
            ("number",),
            "merchant",
            required=False,
            source_label="H31_FOOD_POI_INFO",
        ),
        Binding(
            "coupon_price",
            poi + ".poi_coupon.coupon_list[*].price",
            ("number",),
            "coupon",
            required=False,
            source_label="H31_FOOD_POI_COUPON_LIST",
            many=True,
        ),
        Binding(
            "coupon_origin_value",
            poi + ".poi_coupon.coupon_list[*].coupon_origin_value",
            ("number",),
            "coupon",
            required=False,
            source_label="H31_FOOD_POI_COUPON_LIST",
            many=True,
        ),
        Binding(
            "coupon_total_origin_value",
            poi + ".poi_coupon.coupon_list[*].coupon_total_origin_value",
            ("number",),
            "coupon",
            required=False,
            source_label="H31_FOOD_POI_COUPON_LIST",
            many=True,
        ),
        Binding(
            "coupon_total_value",
            poi + ".poi_coupon.coupon_list[*].coupon_total_value",
            ("number",),
            "coupon",
            required=False,
            source_label="H31_FOOD_POI_COUPON_LIST",
            many=True,
        ),
        Binding(
            "coupon_value",
            poi + ".poi_coupon.coupon_list[*].coupon_value",
            ("number",),
            "coupon",
            required=False,
            source_label="H31_FOOD_POI_COUPON_LIST",
            many=True,
        ),
        Binding(
            "fold_coupon_subsidy_price",
            poi + ".poi_coupon.fold_coupon_list[*].coupon_subsidy_price",
            ("number",),
            "coupon",
            required=False,
            source_label="H31_FOOD_FOLD_COUPON_LIST",
            many=True,
        ),
        Binding(
            "fold_coupon_value",
            poi + ".poi_coupon.fold_coupon_list[*].coupon_value",
            ("number",),
            "coupon",
            required=False,
            source_label="H31_FOOD_FOLD_COUPON_LIST",
            many=True,
        ),
        Binding(
            "cart_min_fee",
            "$.data.shopping_cart.min_fee_cart_tip",
            ("number",),
            "root",
            required=False,
            source_label="H31_FOOD_SHOPPING_CART",
        ),
    )
    return FoodParserConfig(
        payload_family="meituan_wechat_miniprogram",
        payload_version="h31-shape-v1",
        merchant_id=Binding(
            "merchant_id",
            poi + ".poi_id_str",
            ("string",),
            "merchant",
        ),
        merchant_name=Binding(
            "merchant_name",
            poi + ".name",
            ("string",),
            "merchant",
        ),
        price_bindings=bindings,
    )
