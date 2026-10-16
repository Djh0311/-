from __future__ import annotations

import copy
import csv
import io
import json
import unittest

from collection_adapter import CollectionEvent, CollectionTarget
from collection_adapter.fake import FakeAdapter, FakeFixture, success_fixture
from collection_adapter.request import OfflineOutputIntent, OfflineRunOptions, OfflineRunRequest, OfflineTargetRegistry
from collection_adapter.runner import default_parser_registry, run_request
from collection_core.result_views import P0ResultViewError, render_p0_result


def _p0_result(product_name: str = "Demo Product") -> dict[str, object]:
    request = OfflineRunRequest(
        target_ref="target:offline_demo_01",
        options=OfflineRunOptions(
            adapter_id="offline_fake",
            run_ref="run:stage02_view_01",
            read_scope="READ_STAGE02_01",
            observation_scope="OBS_STAGE02_01",
            observed_at="2026-08-11T10:00:00Z",
        ),
        output_intent=OfflineOutputIntent(
            output_root="/private/tmp/stage02-results",
            result_name="stage02_view_01",
            formats=("JSON", "CSV"),
        ),
    )
    config = request.options.to_collection_config()
    fixture = success_fixture(config)
    if product_name != "Demo Product":
        payload = copy.deepcopy(fixture.events[1].payload)
        payload["data"]["food_spu_tags"][0]["dynamic_spus"][0]["name"] = product_name
        fixture = FakeFixture(
            events=(
                fixture.events[0],
                CollectionEvent(
                    read_scope=config.read_scope,
                    observation_scope=config.observation_scope,
                    event_index=2,
                    endpoint_id="PRODUCTLIST",
                    payload_family="synthetic_productlist",
                    payload_version="v1",
                    payload=payload,
                ),
            )
        )
    run = run_request(
        request,
        OfflineTargetRegistry((CollectionTarget(target_ref="target:offline_demo_01"),)),
        {"offline_fake": FakeAdapter({"target:offline_demo_01": fixture})},
        default_parser_registry(),
    )
    return run.p0_result


class P0ResultViewTests(unittest.TestCase):
    def test_json_and_csv_views_have_consistent_readable_same_observation_rows(self) -> None:
        views = render_p0_result(_p0_result())

        json_view = json.loads(views.json_bytes)
        csv_rows = list(csv.DictReader(io.StringIO(views.csv_bytes.decode("utf-8"))))
        self.assertEqual(json_view["schema_version"], "collection-p0-result-view/v1")
        self.assertEqual(json_view["record_count"], 1)
        self.assertEqual(json_view["records"], [
            {
                "store": "Demo Store",
                "product": "Demo Product",
                "price_yuan": "12.50",
                "currency": "CNY",
                "run_ref": "run:stage02_view_01",
                "batch_ref": "batch:stage02_view_01",
                "observation_ref": "observation:OBS_STAGE02_01",
                "business_record_ref": "business-record:p0_0001",
            }
        ])
        self.assertEqual(csv_rows, json_view["records"])

    def test_csv_uses_standard_escaping_without_changing_the_json_value(self) -> None:
        views = render_p0_result(_p0_result('Demo, "Product"'))

        csv_rows = list(csv.DictReader(io.StringIO(views.csv_bytes.decode("utf-8"))))
        json_row = json.loads(views.json_bytes)["records"][0]
        self.assertEqual(csv_rows[0]["product"], 'Demo, "Product"')
        self.assertEqual(json_row["product"], 'Demo, "Product"')

    def test_mismatched_inlined_field_is_rejected_before_rendering(self) -> None:
        result = copy.deepcopy(_p0_result())
        result["business_records"][0]["field_observations"] = copy.deepcopy(
            result["business_records"][0]["field_observations"]
        )
        for field in result["business_records"][0]["field_observations"]:
            if field["field_name"] == "product_name":
                field["public_value_raw"] = "Different Product"

        with self.assertRaisesRegex(P0ResultViewError, "^RESULT_VIEW_P0_INVALID$"):
            render_p0_result(result)

    def test_invalid_or_incomplete_p0_input_fails_without_an_error_echo(self) -> None:
        with self.assertRaisesRegex(P0ResultViewError, "^RESULT_VIEW_P0_INVALID$"):
            render_p0_result({"observation_batch": {}})

        result = copy.deepcopy(_p0_result())
        result["business_records"][0]["field_observations"] = []
        with self.assertRaisesRegex(P0ResultViewError, "^RESULT_VIEW_P0_INVALID$"):
            render_p0_result(result)

    def test_view_never_carries_payload_or_source_material_fields(self) -> None:
        views = render_p0_result(_p0_result())
        text = views.json_bytes.decode("utf-8")
        self.assertNotIn("payload", text)
        self.assertNotIn("source_ref", text)
        self.assertNotIn("cookie", text.lower())
        self.assertNotIn("session", text.lower())
