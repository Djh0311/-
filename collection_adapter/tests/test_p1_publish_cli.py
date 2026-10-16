from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from collection_adapter.runner import main


def _args(root: str) -> tuple[str, ...]:
    return (
        "--p1",
        "--target", "target:offline_demo_01",
        "--adapter-id", "offline_fake",
        "--run-ref", "run:stage03_cli_01",
        "--read-scope", "READ_STAGE03_01",
        "--observation-scope", "OBS_STAGE03_01",
        "--observed-at", "2026-08-11T10:00:00Z",
        "--output-root", root,
        "--result-name", "stage03_cli_01",
        "--formats", "JSON_CSV",
    )


class P1ExplicitPublishCommandTests(unittest.TestCase):
    def test_p1_command_publishes_an_explicit_synthetic_no_clobber_result_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            root = str(Path(directory).resolve())
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(_args(root))

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["result_name"], "stage03_cli_01")
            target = Path(root) / "stage03_cli_01"
            self.assertEqual(sorted(item.name for item in target.iterdir()), ["manifest.json", "records.csv", "records.json"])
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "collection-p1-result-manifest/v1")
            self.assertEqual(manifest["source_kind"], "SYNTHETIC_OFFLINE_FIXTURE")
