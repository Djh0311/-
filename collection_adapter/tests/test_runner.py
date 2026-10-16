from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from collection_adapter import CollectionEvent, CollectionRunConfig, CollectionTarget
from collection_adapter.fake import FakeAdapter, FakeFixture, format_error_fixture, success_fixture
from collection_adapter.runner import (
    OfflineRunError,
    default_p0_context,
    default_parser_registry,
    main,
    run_offline,
)


def _target() -> CollectionTarget:
    return CollectionTarget(target_ref="target:offline_demo_01")


def _config() -> CollectionRunConfig:
    return CollectionRunConfig(
        adapter_id="offline_fake",
        run_ref="run:offline_demo_01",
        read_scope="READ_DEMO_01",
        observation_scope="OBS_DEMO_01",
        observed_at="2026-08-11T10:00:00Z",
    )


def _run(fixture: FakeFixture, *, context=None) -> dict[str, object]:
    config = _config()
    return run_offline(
        {"offline_fake": FakeAdapter({"target:offline_demo_01": fixture})},
        _target(),
        config,
        default_parser_registry(),
        context or default_p0_context(config),
    )


class OfflineRunnerTests(unittest.TestCase):
    def test_successfully_runs_fake_events_through_parser_and_p0(self) -> None:
        result = _run(success_fixture(_config()))

        self.assertEqual(result["source_kind"], "SYNTHETIC_OFFLINE_FIXTURE")
        self.assertEqual(result["readable_records"], [{
            "store": "Demo Store",
            "product": "Demo Product",
            "price_yuan": "12.50",
            "currency": "CNY",
        }])

    def test_adapter_parser_and_p0_failures_return_no_partial_result(self) -> None:
        config = _config()
        parser_failure = FakeFixture(
            events=(
                success_fixture(config).events[0],
                CollectionEvent(
                    read_scope=config.read_scope,
                    observation_scope=config.observation_scope,
                    event_index=2,
                    endpoint_id="PRODUCTLIST",
                    payload_family="synthetic_productlist",
                    payload_version="v1",
                    payload={"data": {"food_spu_tags": []}},
                ),
            )
        )
        for fixture, context, code in (
            (format_error_fixture(), None, "RUNNER_ADAPTER_FAILED"),
            (parser_failure, None, "RUNNER_PARSER_FAILED"),
            (success_fixture(config), replace(default_p0_context(config), currency="USD"), "RUNNER_P0_REJECTED"),
        ):
            with self.subTest(code=code):
                with self.assertRaisesRegex(OfflineRunError, f"^{code}$"):
                    _run(fixture, context=context)

    def test_runner_has_no_output_path_and_cannot_overwrite_a_caller_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "existing.json"
            marker.write_text('{"preserve":true}', encoding="utf-8")

            result = _run(success_fixture(_config()))

            self.assertNotIn("output_path", result)
            self.assertEqual(marker.read_text(encoding="utf-8"), '{"preserve":true}')

    def test_command_prints_complete_json_only_after_success(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(("--scenario", "success"))

        self.assertEqual(exit_code, 0)
        rendered = json.loads(output.getvalue())
        self.assertEqual(rendered["readable_records"][0]["price_yuan"], "12.50")

        failure_output = io.StringIO()
        with redirect_stdout(failure_output):
            failure_code = main(("--scenario", "format-error"))
        self.assertEqual(failure_code, 2)
        self.assertEqual(json.loads(failure_output.getvalue()), {"error": "RUNNER_ADAPTER_FAILED"})
