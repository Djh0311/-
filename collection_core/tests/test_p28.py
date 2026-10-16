import copy
from dataclasses import replace
import unittest

from collection_core.p28 import P28Error, build_p28_batch, validate_p28_batch
from collection_core.tests.test_p0 import _context, _events
from parser_candidate import ParserError, parse_capture_read_scope
from parser_candidate.p26_profile import VERSION_V2, p26_registry
from parser_candidate.p28_profile import FAMILY, VERSION, p28_registry


def scenario():
    food, product = _events()
    food = replace(food, payload_family=FAMILY, payload_version=VERSION)
    payload = copy.deepcopy(product.payload)
    category = payload["data"]["food_spu_tags"][0]
    category["name"] = "Synthetic Category"
    item = category["dynamic_spus"][0]
    item["unit"] = "Synthetic product unit"
    item["render_info"] = {"price_info": {"min_price": item["min_price"]}}
    item["skus"] = [
        {"id": 1001, "spec": "", "spec_desc": "", "price": 12.5, "origin_price": 15.0},
        {"id": 1002, "spec": "", "spec_desc": "", "price": 18.75, "origin_price": 21.0},
    ]
    product = replace(product, payload_family=FAMILY, payload_version=VERSION, payload=payload)
    context = replace(_context(), source_kind="SYNTHETIC_OFFLINE_FIXTURE", coverage_status="PARTIAL")
    evidence = {"schema_version": "p28-price-evidence/v1", "basis": "SYNTHETIC_RULE_TEST",
                "evidence_ref": "evidence:p28_test_01", "currency": "CNY", "amount_unit": "YUAN"}
    return (food, product), context, evidence


class P28BindingTests(unittest.TestCase):
    def build(self, modify=None):
        events, context, evidence = scenario()
        if modify:
            modify(events[1].payload["data"]["food_spu_tags"])
        return build_p28_batch(events, p28_registry(), context, evidence)

    def test_multisku_prices_empty_specs_and_unknown_fees_are_separate(self):
        result = self.build()
        self.assertEqual([r["sku_price_minor"] for r in result["sku_records"]], [1250, 1875])
        self.assertEqual({r["product_display_price_minor"] for r in result["sku_records"]}, {1250})
        for row in result["sku_records"]:
            self.assertEqual((row["sku_spec"], row["sku_spec_state"]), ("", "SOURCE_EMPTY"))
            self.assertEqual(row["product_unit_text"], "Synthetic product unit")
            self.assertEqual(row["source_origin_price_state"], "SEMANTICS_UNCONFIRMED")
            for key in ("original_price_minor", "activity_price_minor", "packaging_fee_minor", "availability_status"):
                self.assertIsNone(row[key])
        validate_p28_batch(result)

    def add_category_copy(self, categories):
        second = copy.deepcopy(categories[0])
        second.update(tag="synthetic-category-02", name="Synthetic Category Two")
        categories.append(second)

    def test_cross_category_copy_retains_membership_and_accepts_reordered_skus(self):
        def modify(categories):
            self.add_category_copy(categories)
            categories[1]["dynamic_spus"][0]["skus"].reverse()
        result = self.build(modify)
        rows = result["sku_records"]
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({r["product_id"] for r in rows}), 1)
        self.assertEqual(len({r["sku_id"] for r in rows}), 2)
        self.assertEqual(len({r["category_ref"] for r in rows}), 2)

    def test_cross_category_same_product_name_conflict_is_rejected(self):
        def modify(categories):
            self.add_category_copy(categories)
            categories[1]["dynamic_spus"][0]["name"] = "Conflicting synthetic name"
        with self.assertRaisesRegex(P28Error, "^P28_CROSS_CATEGORY_CONFLICT$"):
            self.build(modify)

    def test_cross_category_same_sku_price_conflict_is_rejected(self):
        def modify(categories):
            self.add_category_copy(categories)
            categories[1]["dynamic_spus"][0]["skus"][1]["price"] = 19.25
        with self.assertRaisesRegex(P28Error, "^P28_CROSS_CATEGORY_CONFLICT$"):
            self.build(modify)

    def test_same_name_different_product_ids_remain_distinct(self):
        def modify(categories):
            item = copy.deepcopy(categories[0]["dynamic_spus"][0])
            item["id"] = 102
            for index, sku in enumerate(item["skus"]):
                sku["id"] = 2001 + index
            categories[0]["dynamic_spus"].append(item)
        result = self.build(modify)
        self.assertEqual(len({r["product_id"] for r in result["sku_records"]}), 2)
        self.assertEqual(len(result["p0_result"]["business_records"]), 2)

    def test_same_sku_id_cannot_have_two_product_owners(self):
        def modify(categories):
            item = copy.deepcopy(categories[0]["dynamic_spus"][0])
            item["id"] = 102
            categories[0]["dynamic_spus"].append(item)
        with self.assertRaisesRegex(P28Error, "^P28_SKU_OWNER_CONFLICT$"):
            self.build(modify)

    def test_duplicate_sku_in_one_product_is_rejected(self):
        def modify(categories):
            item = categories[0]["dynamic_spus"][0]
            item["skus"].append(copy.deepcopy(item["skus"][0]))
        with self.assertRaises(P28Error):
            self.build(modify)

    def test_invalid_sku_prices_and_unproved_minimum_are_rejected(self):
        for value in (True, float("inf"), float("nan"), -1, 12.501, 10.0):
            with self.subTest(value_type=type(value).__name__):
                def modify(categories):
                    categories[0]["dynamic_spus"][0]["skus"][1]["price"] = value
                with self.assertRaises(P28Error):
                    self.build(modify)

    def test_missing_skus_and_inconsistent_render_minimum_are_rejected(self):
        for missing in (True, False):
            def modify(categories):
                item = categories[0]["dynamic_spus"][0]
                if missing:
                    item["skus"] = []
                else:
                    item["render_info"]["price_info"]["min_price"] = 13.0
            with self.subTest(missing=missing), self.assertRaises(P28Error):
                self.build(modify)

    def test_unknown_units_and_synthetic_relabeling_cannot_authorize_money(self):
        events, context, evidence = scenario()
        for change in ({"amount_unit": "MINOR"}, {"currency": "USD"},
                       {"basis": "USER_CONFIRMED_MULTI_SKU_PAGE"}):
            with self.subTest(field=next(iter(change))), self.assertRaises(P28Error):
                build_p28_batch(events, p28_registry(), context, {**evidence, **change})

    def test_cross_observation_or_profile_and_missing_food_are_rejected(self):
        events, context, evidence = scenario()
        alternatives = ((events[0], replace(events[1], observation_scope="OBS_OTHER_SYNTHETIC")),
                        (events[0], replace(events[1], payload_version=VERSION_V2)), (events[1],))
        for changed in alternatives:
            with self.subTest(count=len(changed)), self.assertRaises(P28Error):
                build_p28_batch(changed, p28_registry(), context, evidence)

    def test_row_tampering_does_not_remove_observation_or_unknown_value_checks(self):
        for key, value in (("observation_ref", "observation:p28_other_01"),
                           ("packaging_fee_minor", 0), ("sku_spec_state", "PRESENT")):
            result = self.build()
            result["sku_records"][0][key] = value
            with self.subTest(field=key), self.assertRaises(P28Error):
                validate_p28_batch(result)

    def test_dropped_nonminimum_sku_and_duplicate_inventory_are_rejected(self):
        result = self.build()
        result["sku_records"].pop()
        with self.assertRaisesRegex(P28Error, "^P28_PARTIAL_RECORD_INVALID$"):
            validate_p28_batch(result)
        result = self.build()
        result["sku_inventory"][0]["sku_ids"].append(result["sku_inventory"][0]["sku_ids"][0])
        with self.assertRaisesRegex(P28Error, "^P28_PARTIAL_RECORD_INVALID$"):
            validate_p28_batch(result)

    def test_optional_status_does_not_relax_p26_and_present_wrong_type_is_rejected(self):
        events, _, _ = scenario()
        p26_events = tuple(replace(e, payload_version=VERSION_V2) for e in events)
        with self.assertRaises(ParserError):
            parse_capture_read_scope(p26_events, p26_registry(VERSION_V2))
        def modify(categories):
            categories[0]["dynamic_spus"][0]["skus"][0]["status"] = "unconfirmed"
        with self.assertRaises(P28Error):
            self.build(modify)


if __name__ == "__main__":
    unittest.main()
