from __future__ import annotations

import unittest

from collection_adapter import CollectionTarget
from collection_adapter.request import (
    OfflineOutputIntent,
    OfflineRequestError,
    OfflineRunOptions,
    OfflineRunRequest,
    OfflineTargetRegistry,
)


def _options() -> OfflineRunOptions:
    return OfflineRunOptions(
        adapter_id="offline_fake",
        run_ref="run:stage02_demo_01",
        read_scope="READ_STAGE02_01",
        observation_scope="OBS_STAGE02_01",
        observed_at="2026-08-11T10:00:00Z",
    )


def _intent() -> OfflineOutputIntent:
    return OfflineOutputIntent(
        output_root="/private/tmp/stage02-results",
        result_name="stage02_demo_01",
        formats=("JSON", "CSV"),
    )


def _registry() -> OfflineTargetRegistry:
    return OfflineTargetRegistry((CollectionTarget(target_ref="target:offline_demo_01"),))


class OfflineRequestContractTests(unittest.TestCase):
    def test_resolves_one_explicit_known_target_and_run_options(self) -> None:
        request = OfflineRunRequest(
            target_ref="target:offline_demo_01",
            options=_options(),
            output_intent=_intent(),
        )

        target, config = request.to_collection_inputs(_registry())

        self.assertEqual(target.target_ref, "target:offline_demo_01")
        self.assertEqual(config.run_ref, "run:stage02_demo_01")
        self.assertEqual(request.output_intent.formats, ("JSON", "CSV"))

    def test_invalid_target_options_and_output_intent_fail_closed(self) -> None:
        with self.assertRaisesRegex(OfflineRequestError, "^OFFLINE_TARGET_INVALID$"):
            OfflineRunRequest(target_ref="demo", options=_options(), output_intent=_intent())
        with self.assertRaisesRegex(OfflineRequestError, "^OFFLINE_RUN_OPTIONS_INVALID$"):
            OfflineRunOptions(
                adapter_id="offline fake",
                run_ref="run:stage02_demo_01",
                read_scope="READ_STAGE02_01",
                observation_scope="OBS_STAGE02_01",
                observed_at="2026-08-11T10:00:00Z",
            )
        with self.assertRaisesRegex(OfflineRequestError, "^OFFLINE_OUTPUT_INTENT_INVALID$"):
            OfflineOutputIntent(
                output_root="relative-results",
                result_name="stage02_demo_01",
                formats=("JSON", "CSV"),
            )

    def test_unknown_target_is_not_replaced_by_the_demo_target(self) -> None:
        request = OfflineRunRequest(
            target_ref="target:offline_demo_02",
            options=_options(),
            output_intent=_intent(),
        )

        with self.assertRaisesRegex(OfflineRequestError, "^OFFLINE_TARGET_UNKNOWN$"):
            request.to_collection_inputs(_registry())

    def test_formats_are_closed_to_the_required_json_csv_pair(self) -> None:
        with self.assertRaisesRegex(OfflineRequestError, "^OFFLINE_OUTPUT_INTENT_INVALID$"):
            OfflineOutputIntent(
                output_root="/private/tmp/stage02-results",
                result_name="stage02_demo_01",
                formats=("JSON",),
            )
