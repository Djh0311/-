from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from collection_adapter import CollectionEvent, CollectionTarget
from collection_adapter.fake import FakeAdapter, FakeFixture, cross_observation_fixture, format_error_fixture, success_fixture
from collection_adapter.request import OfflineOutputIntent, OfflineRunOptions, OfflineRunRequest, OfflineTargetRegistry
from collection_adapter.runner import (
    OfflineRunError,
    default_p0_context,
    default_parser_registry,
    run_request,
)


def _request(target_ref: str = "target:offline_demo_01") -> OfflineRunRequest:
    return OfflineRunRequest(
        target_ref=target_ref,
        options=OfflineRunOptions(
            adapter_id="offline_fake",
            run_ref="run:stage02_demo_01",
            read_scope="READ_STAGE02_01",
            observation_scope="OBS_STAGE02_01",
            observed_at="2026-08-11T10:00:00Z",
        ),
        output_intent=OfflineOutputIntent(
            output_root="/private/tmp/stage02-results",
            result_name="stage02_demo_01",
            formats=("JSON", "CSV"),
        ),
    )


def _targets() -> OfflineTargetRegistry:
    return OfflineTargetRegistry((CollectionTarget(target_ref="target:offline_demo_01"),))


def _adapters(fixture: FakeFixture) -> dict[str, FakeAdapter]:
    return {"offline_fake": FakeAdapter({"target:offline_demo_01": fixture})}


class P0RunOrchestrationTests(unittest.TestCase):
    def test_explicit_request_builds_one_same_observation_p0_run(self) -> None:
        request = _request()
        config = request.options.to_collection_config()

        run = run_request(
            request,
            _targets(),
            _adapters(success_fixture(config)),
            default_parser_registry(),
        )

        self.assertEqual(run.target.target_ref, "target:offline_demo_01")
        self.assertEqual(run.p0_result["observation_batch"]["run_ref"], "run:stage02_demo_01")
        self.assertEqual(run.p0_result["observation_batch"]["source_kind"], "SYNTHETIC_OFFLINE_FIXTURE")
        self.assertEqual(run.p0_result["business_records"][0]["core_binding"]["binding_status"], "SAME_OBSERVATION")

    def test_adapter_parser_p0_and_cross_observation_failures_do_not_return_partial_runs(self) -> None:
        request = _request()
        config = request.options.to_collection_config()
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
        for fixture, factory, code in (
            (format_error_fixture(), default_p0_context, "RUNNER_ADAPTER_FAILED"),
            (cross_observation_fixture(config), default_p0_context, "RUNNER_ADAPTER_FAILED"),
            (parser_failure, default_p0_context, "RUNNER_PARSER_FAILED"),
            (
                success_fixture(config),
                lambda value: replace(default_p0_context(value), currency="USD"),
                "RUNNER_P0_REJECTED",
            ),
        ):
            with self.subTest(code=code):
                with self.assertRaisesRegex(OfflineRunError, f"^{code}$"):
                    run_request(
                        request,
                        _targets(),
                        _adapters(fixture),
                        default_parser_registry(),
                        p0_context_factory=factory,
                    )

    def test_request_runner_has_no_output_path_or_publication_side_effect(self) -> None:
        request = _request()
        config = request.options.to_collection_config()
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "existing-result.json"
            marker.write_text('{"preserve":true}', encoding="utf-8")

            run = run_request(
                request,
                _targets(),
                _adapters(success_fixture(config)),
                default_parser_registry(),
            )

            self.assertFalse(hasattr(run, "output_path"))
            self.assertEqual(marker.read_text(encoding="utf-8"), '{"preserve":true}')
