from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from collection_adapter.runner import main


def _args(root: str, target: str = "target:offline_demo_01") -> tuple[str, ...]:
    return (
        "--target", target,
        "--adapter-id", "offline_fake",
        "--run-ref", "run:stage02_cli_01",
        "--read-scope", "READ_STAGE02_01",
        "--observation-scope", "OBS_STAGE02_01",
        "--observed-at", "2026-08-11T10:00:00Z",
        "--output-root", root,
        "--result-name", "stage02_cli_01",
        "--formats", "JSON_CSV",
    )


class ExplicitPublishCommandTests(unittest.TestCase):
    def test_explicit_command_publishes_a_complete_result_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            root = str(Path(directory).resolve())
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(_args(root))

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["result_name"], "stage02_cli_01")
            self.assertEqual(
                sorted(item.name for item in (Path(root) / "stage02_cli_01").iterdir()),
                ["manifest.json", "records.csv", "records.json"],
            )

    def test_unknown_explicit_target_does_not_create_an_output_or_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            root = str(Path(directory).resolve())
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(_args(root, target="target:offline_demo_02"))

            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(output.getvalue()), {"error": "RUNNER_REQUEST_FAILED"})
            self.assertFalse((Path(root) / "stage02_cli_01").exists())
