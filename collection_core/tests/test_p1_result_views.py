from __future__ import annotations

import copy
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from collection_adapter import CollectionRunConfig
from collection_adapter.fake import p1_success_fixture
from collection_adapter.runner import default_p0_context
from collection_core.p1 import build_p1_batch
from collection_core.p1_result_views import P1ResultViewError, render_p1_result
from collection_core.result_publisher import ResultPublishError, publish_result_set
from parser_candidate import synthetic_p1_registry


def _p1_result() -> dict[str, object]:
    config = CollectionRunConfig(
        adapter_id="offline_fake",
        run_ref="run:stage03_view_01",
        read_scope="READ_STAGE03_01",
        observation_scope="OBS_STAGE03_01",
        observed_at="2026-08-11T10:00:00Z",
    )
    fixture = p1_success_fixture(config)
    return build_p1_batch(
        tuple(event.to_parser_event() for event in fixture.events),
        synthetic_p1_registry(),
        default_p0_context(config),
    )


class P1ResultViewTests(unittest.TestCase):
    def test_json_and_csv_share_complete_p1_rows_with_yuan_and_presence(self) -> None:
        views = render_p1_result(_p1_result())

        payload = json.loads(views.json_bytes)
        rows = list(csv.DictReader(io.StringIO(views.csv_bytes.decode("utf-8"))))
        row = payload["records"][0]
        self.assertEqual(payload["schema_version"], "collection-p1-result-view/v1")
        self.assertEqual(payload["record_count"], 1)
        self.assertEqual(rows, payload["records"])
        self.assertEqual(row["price_yuan"], "12.50")
        self.assertEqual(row["original_price_yuan"], "15.00")
        self.assertEqual(row["activity_price_yuan"], "12.50")
        self.assertEqual(row["promotion_discount_yuan"], "2.50")
        self.assertEqual(row["promotion_discount_bps"], "")
        self.assertEqual(row["promotion_discount_bps_presence"], "NOT_APPLICABLE")
        self.assertEqual(row["delivery_fee_yuan"], "3.00")
        self.assertEqual(row["delivery_min_order_yuan"], "20.00")
        self.assertEqual(row["promotion_scope_owner_entity_kind"], "SKU")
        self.assertEqual(row["delivery_status_source_label"], "SYNTHETIC_P1_DELIVERY")
        self.assertNotIn("payload", views.json_bytes.decode("utf-8"))

    def test_invalid_p1_field_tampering_is_rejected_before_rendering(self) -> None:
        result = copy.deepcopy(_p1_result())
        result["p1_records"][0]["p1_fields"][0]["source_label"] = "OTHER"

        with self.assertRaisesRegex(P1ResultViewError, "^P1_RESULT_VIEW_INVALID$"):
            render_p1_result(result)

    def test_p1_view_publishes_a_no_clobber_json_csv_manifest_set(self) -> None:
        views = render_p1_result(_p1_result())
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            root = str(Path(directory).resolve())

            receipt = publish_result_set(root, "stage03_view_01", views)
            target = Path(root) / "stage03_view_01"
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["record_count"], 1)
            self.assertEqual(manifest["schema_version"], "collection-p1-result-manifest/v1")
            self.assertEqual(manifest["record_count"], 1)

            with self.assertRaisesRegex(ResultPublishError, "^RESULT_TARGET_EXISTS$"):
                publish_result_set(root, "stage03_view_01", views)
