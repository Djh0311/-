from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from collection_adapter import CollectionTarget
from collection_adapter.fake import FakeAdapter, success_fixture
from collection_adapter.request import OfflineOutputIntent, OfflineRunOptions, OfflineRunRequest, OfflineTargetRegistry
from collection_adapter.runner import default_parser_registry, run_request
from collection_core.result_publisher import ResultPublishError, publish_result_set
from collection_core.result_views import P0ResultViews, render_p0_result


def _views():
    request = OfflineRunRequest(
        target_ref="target:offline_demo_01",
        options=OfflineRunOptions(
            adapter_id="offline_fake",
            run_ref="run:stage02_publish_01",
            read_scope="READ_STAGE02_01",
            observation_scope="OBS_STAGE02_01",
            observed_at="2026-08-11T10:00:00Z",
        ),
        output_intent=OfflineOutputIntent(
            output_root="/private/tmp/stage02-results",
            result_name="stage02_publish_01",
            formats=("JSON", "CSV"),
        ),
    )
    config = request.options.to_collection_config()
    run = run_request(
        request,
        OfflineTargetRegistry((CollectionTarget(target_ref="target:offline_demo_01"),)),
        {"offline_fake": FakeAdapter({"target:offline_demo_01": success_fixture(config)})},
        default_parser_registry(),
    )
    return render_p0_result(run.p0_result)


class ResultPublisherTests(unittest.TestCase):
    def test_publishes_one_complete_json_csv_manifest_result_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            root = str(Path(directory).resolve())

            receipt = publish_result_set(root, "stage02_publish_01", _views())

            target = Path(root) / "stage02_publish_01"
            self.assertEqual(receipt["result_name"], "stage02_publish_01")
            self.assertEqual(sorted(item.name for item in target.iterdir()), ["manifest.json", "records.csv", "records.json"])
            with (target / "records.json").open(encoding="utf-8") as handle:
                json_view = json.load(handle)
            with (target / "manifest.json").open(encoding="utf-8") as handle:
                manifest = json.load(handle)
            self.assertEqual(manifest["run_ref"], json_view["run_ref"])
            self.assertEqual(manifest["record_count"], json_view["record_count"])
            self.assertEqual(manifest["files"], ["records.json", "records.csv", "manifest.json"])
            self.assertNotIn("sha256", manifest)

    def test_existing_target_is_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            root = Path(directory).resolve()
            target = root / "stage02_publish_01"
            target.mkdir(mode=0o700)
            marker = target / "existing.json"
            marker.write_text('{"preserve":true}', encoding="utf-8")

            with self.assertRaisesRegex(ResultPublishError, "^RESULT_TARGET_EXISTS$"):
                publish_result_set(str(root), "stage02_publish_01", _views())

            self.assertEqual(marker.read_text(encoding="utf-8"), '{"preserve":true}')

    def test_invalid_root_and_a_write_failure_leave_no_complete_or_partial_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            os.chmod(root, 0o755)
            with self.assertRaisesRegex(ResultPublishError, "^RESULT_ROOT_INVALID$"):
                publish_result_set(str(root), "stage02_publish_01", _views())
            self.assertFalse((root / "stage02_publish_01").exists())

    def test_inconsistent_json_csv_views_are_rejected_before_creating_a_target(self) -> None:
        views = _views()
        inconsistent = P0ResultViews(json_bytes=views.json_bytes, csv_bytes=b"store\nDemo Store\n")
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            root = Path(directory).resolve()

            with self.assertRaisesRegex(ResultPublishError, "^RESULT_INPUT_INVALID$"):
                publish_result_set(str(root), "stage02_publish_01", inconsistent)

            self.assertFalse((root / "stage02_publish_01").exists())

        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            root = Path(directory).resolve()
            with patch("collection_core.result_publisher._write_file", side_effect=OSError("fault")):
                with self.assertRaisesRegex(ResultPublishError, "^RESULT_PUBLISH_FAILED$"):
                    publish_result_set(str(root), "stage02_publish_01", _views())
            self.assertFalse((root / "stage02_publish_01").exists())
