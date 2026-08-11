from __future__ import annotations

import unittest

from parser_candidate import h31_food_config, parse_food


class H31FoodProfileTests(unittest.TestCase):
    def test_food_profile_keeps_merchant_and_coupon_prices(self) -> None:
        payload = {
            "data": {
                "poi_info": {
                    "poi_id_str": "merchant-1",
                    "name": "store",
                    "min_price": 20.0,
                    "shipping_fee": 3.0,
                    "shippingReduceFee": 1.0,
                    "poi_coupon": {
                        "coupon_list": [
                            {
                                "price": 15.0,
                                "coupon_origin_value": 20.0,
                                "coupon_total_origin_value": 20.0,
                                "coupon_total_value": 15.0,
                                "coupon_value": 5.0,
                            }
                        ],
                        "fold_coupon_list": [
                            {"coupon_subsidy_price": 2.0, "coupon_value": 2.0}
                        ],
                    },
                },
                "shopping_cart": {"min_fee_cart_tip": 30.0},
            }
        }
        result = parse_food(payload, h31_food_config())
        merchant = result["merchant"]
        self.assertEqual(merchant["id"], "merchant-1")
        self.assertEqual(merchant["prices"]["poi_min_price"], {
            "value": 20.0,
            "source_label": "H31_FOOD_POI_INFO",
        })
        self.assertEqual(merchant["prices"]["coupon_price"], {
            "value": [15.0],
            "source_label": "H31_FOOD_POI_COUPON_LIST",
        })
        self.assertEqual(merchant["prices"]["fold_coupon_value"], {
            "value": [2.0],
            "source_label": "H31_FOOD_FOLD_COUPON_LIST",
        })
        self.assertEqual(merchant["prices"]["cart_min_fee"], {
            "value": 30.0,
            "source_label": "H31_FOOD_SHOPPING_CART",
        })

    def test_food_profile_leaves_missing_prices_empty(self) -> None:
        payload = {"data": {"poi_info": {"poi_id_str": "merchant-1", "name": "store"}}}
        result = parse_food(payload, h31_food_config())
        self.assertEqual(result["merchant"]["prices"]["poi_min_price"]["value"], None)
        self.assertEqual(result["merchant"]["prices"]["coupon_price"]["value"], None)


if __name__ == "__main__":
    unittest.main()
