import csv
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from collection_core.p28_result_views import render_p28_result
from collection_core.result_publisher import ResultPublishError, publish_result_set
from collection_core.tests import test_p28 as binding_tests


class P28ResultTests(unittest.TestCase):
    def build(self, cross_category=False):
        helper = binding_tests.P28BindingTests()
        return helper.build(helper.add_category_copy if cross_category else None)

    def test_per_sku_rows_keep_prices_unknowns_and_category_membership(self):
        views = render_p28_result(self.build(cross_category=True))
        payload = json.loads(views.json_bytes)
        rows = payload["records"]
        self.assertEqual((payload["record_count"], payload["product_count"], payload["sku_count"], payload["category_count"]), (4, 1, 2, 2))
        self.assertEqual([r["sku_price_yuan"] for r in rows], ["12.50", "18.75", "12.50", "18.75"])
        self.assertEqual({r["product_display_price_yuan"] for r in rows}, {"12.50"})
        self.assertEqual(list(csv.DictReader(io.StringIO(views.csv_bytes.decode()))), rows)
        for row in rows:
            self.assertEqual((row["sku_spec"], row["sku_spec_state"]), ("", "SOURCE_EMPTY"))
            self.assertEqual((row["packaging_fee_yuan"], row["packaging_fee_state"]), ("", "NOT_ADAPTED_OR_UNCONFIRMED"))
            self.assertEqual(row["source_origin_price_state"], "SEMANTICS_UNCONFIRMED")

    def test_publisher_json_csv_manifest_consistency_and_no_clobber(self):
        views = render_p28_result(self.build())
        with tempfile.TemporaryDirectory() as root:
            root = os.path.realpath(root)
            os.chmod(root, 0o700)
            published = publish_result_set(root, "synthetic_p28", views)
            result = Path(root) / "synthetic_p28"
            manifest = json.loads(result.joinpath("manifest.json").read_bytes())
            self.assertEqual((published["record_count"], manifest["record_count"], manifest["sku_count"]), (2, 2, 2))
            self.assertEqual(manifest["price_evidence"]["basis"], "SYNTHETIC_RULE_TEST")
            self.assertEqual(manifest["coverage_status"], "PARTIAL")
            previous = {p.name: p.read_bytes() for p in result.iterdir()}
            self.assertEqual(set(previous), {"records.json", "records.csv", "manifest.json"})
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in result.iterdir()))
            with self.assertRaisesRegex(ResultPublishError, "^RESULT_TARGET_EXISTS$"):
                publish_result_set(root, "synthetic_p28", views)
            self.assertEqual(previous, {p.name: p.read_bytes() for p in result.iterdir()})

    def test_tampered_json_csv_or_binding_rejected_before_output_creation(self):
        views = render_p28_result(self.build())
        payload = json.loads(views.json_bytes)
        payload["records"].pop()
        payload["record_count"] = 1
        forged = replace(views, json_bytes=json.dumps(payload).encode())
        truncated = replace(views, csv_bytes=views.csv_bytes.splitlines(keepends=True)[0])
        for changed in (forged, truncated):
            with self.subTest(kind="json" if changed is forged else "csv"), tempfile.TemporaryDirectory() as root:
                root = os.path.realpath(root)
                os.chmod(root, 0o700)
                with self.assertRaisesRegex(ResultPublishError, "^RESULT_INPUT_INVALID$"):
                    publish_result_set(root, "synthetic_p28", changed)
                self.assertEqual(list(Path(root).iterdir()), [])
        views.binding_batch["sku_records"].pop()
        with tempfile.TemporaryDirectory() as root:
            root = os.path.realpath(root)
            os.chmod(root, 0o700)
            with self.assertRaisesRegex(ResultPublishError, "^RESULT_INPUT_INVALID$"):
                publish_result_set(root, "synthetic_p28", views)
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_closed_schemas_validate_real_model_shape_and_reject_extras(self):
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
        schemas = Path(__file__).parents[2] / "contracts" / "schemas"
        registry = Registry()
        for path in schemas.glob("*.schema.json"):
            registry = registry.with_resource(path.name, Resource.from_contents(json.loads(path.read_text())))
        binding = self.build()
        # Exercise absence as well as the observed, uninterpreted source number.
        binding["sku_records"][0].update(source_origin_price_number=None, source_origin_price_state="NOT_OBSERVED")
        views = render_p28_result(binding)
        from collection_core.p28_result_views import p28_manifest
        manifest = json.loads(p28_manifest(views, "synthetic_p28")[0])
        for name, value in (
            ("p28-binding-batch-v1.schema.json", binding),
            ("p28-result-view-v1.schema.json", json.loads(views.json_bytes)),
            ("p28-result-manifest-v1.schema.json", manifest),
        ):
            with self.subTest(schema=name):
                schema = json.loads(schemas.joinpath(name).read_text())
                Draft202012Validator.check_schema(schema)
                validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
                errors = list(validator.iter_errors(value))
                self.assertEqual([(list(e.path), e.validator) for e in errors], [])
                self.assertFalse(validator.is_valid({**value, "unexpected": "synthetic"}))


if __name__ == "__main__":
    unittest.main()
