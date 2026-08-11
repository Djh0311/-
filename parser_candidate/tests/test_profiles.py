from __future__ import annotations

import unittest

from parser_candidate import h31_productlist_config, parse_productlist


class H31ProfileTests(unittest.TestCase):
    def test_profile_keeps_all_product_and_sku_price_sources(self) -> None:
        payload = {
            "data": {
                "food_spu_tags": [
                    {
                        "tag": "category-alpha",
                        "current_page": 1,
                        "has_next_page": False,
                        "dynamic_spus": [
                            {
                                "id": 1,
                                "name": "item",
                                "min_price": 10.0,
                                "full_discount_price": 8.0,
                                "preferential_feeling_price": 7.5,
                                "max_discount": 3.2,
                                "activity_policy": {
                                    "discount_by_count": {"discount": 4.5}
                                },
                                "render_data": {
                                    "component_data": {
                                        "price_component": {
                                            "price": [
                                                {"price": 9.0, "underline_price": 11.0},
                                                {"price": 8.5, "underline_price": 10.0},
                                            ]
                                        }
                                    }
                                },
                                "render_info": {
                                    "price_info": {
                                        "coupons_per_price": 6.5,
                                        "min_price": 6.0,
                                        "multi_activity_price": 5.5,
                                        "origin_price": 12.0,
                                        "show_origin_price": 1,
                                    }
                                },
                                "skus": [
                                    {
                                        "id": 2,
                                        "spec": "regular",
                                        "status": 1,
                                        "box_price": 1.0,
                                        "full_discount_price": 8.0,
                                        "member_price": 7.0,
                                        "origin_price": 12.0,
                                        "price": 10.0,
                                        "sku_ladder_box_info": {"ladder_package_price": 0.5},
                                        "activity_policy": {
                                            "discount_by_count": {"discount": 0.4}
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "render_context": {
                    "min_price": 6.0,
                    "delivery_fee": 2.0,
                    "final_reduced_shipping_fee": 1.0,
                },
            }
        }
        result = parse_productlist(payload, h31_productlist_config())
        product = result["category_pages"][0]["products"][0]
        self.assertEqual(product["prices"]["display_price"], {
            "value": [9.0, 8.5],
            "source_label": "H31_PRODUCTLIST_PRICE_COMPONENT",
        })
        self.assertEqual(product["prices"]["render_origin_price"]["source_label"], "H31_PRODUCTLIST_RENDER_INFO_PRICE_INFO")
        self.assertEqual(product["skus"][0]["prices"]["member_price"], {
            "value": 7.0,
            "source_label": "H31_PRODUCTLIST_SKU",
        })
        self.assertEqual(product["prices"]["discount_by_count_discount"], {
            "value": 4.5,
            "source_label": "H31_PRODUCTLIST_SPU",
        })
        self.assertEqual(product["skus"][0]["prices"]["discount_by_count_discount"], {
            "value": 0.4,
            "source_label": "H31_PRODUCTLIST_SKU",
        })
        self.assertEqual(result["prices"]["delivery_fee"], {
            "value": 2.0,
            "source_label": "H31_PRODUCTLIST_RENDER_CONTEXT",
        })

    def test_profile_leaves_unobserved_prices_empty(self) -> None:
        payload = {
            "data": {
                "food_spu_tags": [
                    {
                        "tag": "category-alpha",
                        "current_page": 1,
                        "has_next_page": False,
                        "dynamic_spus": [
                            {
                                "id": 1,
                                "name": "item",
                                "min_price": 10.0,
                                "skus": [
                                    {"id": 2, "spec": "regular", "status": 1, "price": 10.0}
                                ],
                            }
                        ],
                    }
                ]
            }
        }
        result = parse_productlist(payload, h31_productlist_config())
        product = result["category_pages"][0]["products"][0]
        self.assertEqual(product["prices"]["full_discount_price"]["value"], None)
        self.assertEqual(product["skus"][0]["prices"]["member_price"]["value"], None)
        self.assertEqual(result["prices"]["render_context_min_price"]["value"], None)


if __name__ == "__main__":
    unittest.main()
