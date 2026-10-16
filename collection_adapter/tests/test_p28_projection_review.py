import json
import os
from pathlib import Path
import tempfile
import unittest

from collection_adapter.p28_projection_review import (
    PATHS, FOOD_ROUTE, PRODUCT_ROUTE, build_authorized_projection_review, read_authorized_projection,
)
from collection_core.p28 import P28Error
from collection_core.tests.test_p28 import scenario


def projection_scenario():
    events, _, _ = scenario()
    events[0].payload["code"] = 0
    events[1].payload["code"] = 0
    rows = []
    for index, (route, event) in enumerate(((FOOD_ROUTE, events[0]), (PRODUCT_ROUTE, events[1])), 1):
        fields = []
        def walk(value, path="$", coords=()):
            if type(value) is dict:
                for key, child in value.items():
                    walk(child, path + "." + key, coords + (key,))
            elif type(value) is list:
                for position, child in enumerate(value):
                    walk(child, path + "[]", coords + (position,))
            elif path in PATHS[route]:
                fields.append({"path": path, "coordinates": list(coords), "value": value})
        walk(event.payload)
        rows.append({"projection_ref": "projection:" + str(index) * 32, "route_slot": index,
            "observed_at": "2026-08-11T10:00:00Z", "values": fields, "meaning": "DEVELOPER_REVIEW_REQUIRED",
            "unavailable_fields": [], "complete_record": False, "source_request_ref": "request:" + str(index) * 32,
            "source_identity": "NOT_CONFIRMED", "sensitive_values_processed": False})
    evidence = {"schema_version": "p28-price-evidence/v1", "basis": "USER_CONFIRMED_MULTI_SKU_PAGE",
                "evidence_ref": "evidence:p28_projection_test", "currency": "CNY", "amount_unit": "YUAN"}
    return {"schema_version": "p26-public-scalar-inspection/v1", "window_ref": "identification:" + "3" * 32,
            "observations": rows, "store_name_match": True, "product_store_association": "NOT_CONFIRMED",
            "sensitive_values_processed": False, "product_result": "incomplete"}, evidence


class P28ProjectionTests(unittest.TestCase):
    def test_preserves_source_time_and_does_not_claim_live_capture_or_success(self):
        projection, evidence = projection_scenario()
        views, receipt = build_authorized_projection_review(projection, "Store One", evidence)
        payload = json.loads(views.json_bytes)
        self.assertEqual(payload["observed_at"], "2026-08-11T10:00:00Z")
        self.assertEqual(payload["source_kind"], "USER_OWNED_EXPORT")
        self.assertEqual((receipt["record_count"], receipt["sku_count"]), (2, 2))
        self.assertFalse(receipt["complete"])
        self.assertFalse(receipt["new_capture"])
        self.assertEqual((receipt["new_result_attempts"], receipt["runtime_business_files_written"]), (0, 0))
        self.assertEqual(receipt["source_association"], "CORROBORATION_ONLY_NOT_NEW_ROUTING_PROOF")

    def test_target_time_sensitive_flag_and_oversized_coordinate_are_rejected(self):
        for mutation in ("target", "time", "sensitive", "budget", "missing-core"):
            projection, evidence = projection_scenario()
            expected = "Different Synthetic Store" if mutation == "target" else "Store One"
            if mutation == "time":
                projection["observations"][1]["observed_at"] = "2026-08-11T10:00:11Z"
            elif mutation == "sensitive":
                projection["sensitive_values_processed"] = True
            elif mutation == "budget":
                item = next(f for f in projection["observations"][1]["values"] if f["path"].endswith(".skus[].id"))
                item["coordinates"][-2] = 7999
                # All array capacities together exceed the restoration budget.
            elif mutation == "missing-core":
                projection["observations"][1]["unavailable_fields"] = [{"path": "$.data.food_spu_tags[].dynamic_spus[].skus[].price", "reason": "NOT_PROJECTED", "type": "number"}]
            with self.subTest(mutation=mutation), self.assertRaises(P28Error):
                build_authorized_projection_review(projection, expected, evidence)

    def test_nonselected_rejected_url_does_not_bypass_selected_field_validation(self):
        projection, evidence = projection_scenario()
        projection["observations"][1]["unavailable_fields"] = [{
            "path": "$.data.food_spu_tags[].dynamic_spus[].render_info.price_info.price_desc_tag",
            "reason": "UNSAFE_PUBLIC_VALUE", "type": "string",
        }]
        _, receipt = build_authorized_projection_review(projection, "Store One", evidence)
        self.assertEqual(receipt["record_count"], 2)
        field = next(f for f in projection["observations"][1]["values"] if f["path"].endswith(".skus[].spec"))
        field["value"] = "https://invalid.example/synthetic"
        with self.assertRaises(P28Error):
            build_authorized_projection_review(projection, "Store One", evidence)

    def test_reader_rejects_raw_names_symlinks_and_permissive_files(self):
        projection, _ = projection_scenario()
        name = "identification-public-projection-" + "4" * 32 + ".json"
        with tempfile.TemporaryDirectory() as temp:
            root = os.path.realpath(temp)
            os.chmod(root, 0o700)
            path = Path(root) / name
            path.write_text(json.dumps(projection))
            os.chmod(path, 0o600)
            self.assertEqual(read_authorized_projection(root, name), projection)
            with self.assertRaises(P28Error):
                read_authorized_projection(root, "historical-raw.json")
            os.chmod(path, 0o644)
            with self.assertRaises(P28Error):
                read_authorized_projection(root, name)
            path.unlink()
            path.symlink_to(Path(root) / "absent")
            with self.assertRaises(P28Error):
                read_authorized_projection(root, name)


if __name__ == "__main__":
    unittest.main()
