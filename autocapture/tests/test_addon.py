import json
import runpy
import unittest
from pathlib import Path
from unittest import mock

from autocapture.addon import (
    ARMED,
    COMPLETED,
    DISARMED,
    STOPPED,
    MitmproxyCaptureAdapter,
    ResponseCaptureAddon,
    ValueFreeStopReceipt,
    addons,
)
from autocapture.lease import RawLease
from autocapture.policy import CapturePolicy, EndpointRule
from autocapture.shape import SanitizedShape, ShapeAccumulator
from autocapture.tests.fakes import (
    ALLOWED_JSON_KEYS,
    ManualClock,
    SENSITIVE_SCHEMA_KEY_VARIANTS,
    SyntheticCancellation,
    generated_sensitive_marker,
    synthetic_flow,
)


class RecordingPublisher:
    def __init__(self, failure=None, allowed_schema_keys=ALLOWED_JSON_KEYS):
        self.shapes = []
        self.failure = failure
        self.allowed_schema_keys = allowed_schema_keys

    def publish(self, shape):
        if self.failure is not None:
            raise self.failure
        if not isinstance(shape, SanitizedShape):
            raise AssertionError("PUBLISHER_RECEIVED_WRONG_TYPE")
        self.shapes.append(shape)
        return {"outcome": "PUBLISHED"}


def policy(
    max_events=1,
    max_body_bytes=4096,
    max_total_body_bytes=8192,
    allowed_json_keys=ALLOWED_JSON_KEYS,
):
    return CapturePolicy(
        endpoint_rules=(
            EndpointRule("GET", "api.synthetic.invalid", "/v1/discovery"),
        ),
        allowed_statuses=(200,),
        allowed_content_types=("application/json",),
        allowed_json_keys=allowed_json_keys,
        max_body_bytes=max_body_bytes,
        max_total_body_bytes=max_total_body_bytes,
        max_json_depth=8,
        max_json_nodes=64,
        max_shape_paths=32,
        max_events=max_events,
        observation_window_seconds=30.0,
        max_lease_seconds=2.0,
    )


def safe_body():
    model = {
        "store": {"name": "alpha"},
        "items": [{"label": "beta", "price": 12.5}],
    }
    return json.dumps(model, separators=(",", ":")).encode("utf-8")


class AddonTests(unittest.TestCase):
    def test_named_mitmproxy_adapter_is_disarmed_and_forwards_lifecycle(self):
        publisher = RecordingPublisher()
        adapter = MitmproxyCaptureAdapter()
        self.assertEqual(adapter.state, DISARMED)

        flow, tracker = synthetic_flow(safe_body())
        adapter.response(flow)
        self.assertEqual(sum(tracker.values()), 0)

        self.assertTrue(adapter.arm(policy(), publisher))
        adapter.response(flow)
        self.assertEqual(adapter.state, COMPLETED)
        self.assertEqual(adapter.event_count, 1)
        self.assertEqual(len(publisher.shapes), 1)
        self.assertEqual(tracker["response_body_reads"], 1)
        self.assertEqual(tracker["flow_mutations"], 0)

    def test_module_exports_one_disarmed_addon(self):
        self.assertIs(type(addons), list)
        self.assertEqual(len(addons), 1)
        self.assertIs(type(addons[0]), ResponseCaptureAddon)
        self.assertEqual(addons[0].state, DISARMED)

        flow, tracker = synthetic_flow(safe_body())
        addons[0].response(flow)
        self.assertEqual(sum(tracker.values()), 0)

    def test_direct_script_loader_uses_canonical_policy_and_can_arm(self):
        addon_path = Path(__file__).resolve().parents[1] / "addon.py"
        namespace = runpy.run_path(
            str(addon_path),
            run_name="mitmproxy_script_addon",
        )
        self.assertIs(namespace["CapturePolicy"], CapturePolicy)
        self.assertIs(type(namespace["addons"]), list)
        self.assertEqual(len(namespace["addons"]), 1)
        self.assertIs(type(namespace["addons"][0]), namespace["ResponseCaptureAddon"])
        self.assertEqual(namespace["addons"][0].state, DISARMED)
        flow, tracker = synthetic_flow(safe_body())
        namespace["addons"][0].response(flow)
        self.assertEqual(sum(tracker.values()), 0)
        script_addon = namespace["ResponseCaptureAddon"]()
        self.assertTrue(script_addon.arm(policy(), RecordingPublisher()))
        self.assertEqual(script_addon.state, ARMED)

    def test_disarmed_reads_nothing_and_invalid_policy_does_not_arm(self):
        flow, tracker = synthetic_flow(safe_body())
        addon = ResponseCaptureAddon()
        addon.response(flow)
        self.assertEqual(sum(tracker.values()), 0)
        self.assertFalse(
            ResponseCaptureAddon().arm(
                policy(),
                RecordingPublisher(
                    allowed_schema_keys=frozenset(("store",))
                ),
            )
        )
        self.assertFalse(addon.arm(object(), RecordingPublisher()))
        for sensitive_key in SENSITIVE_SCHEMA_KEY_VARIANTS:
            with self.subTest(sensitive_key=sensitive_key):
                invalid_keys = frozenset((sensitive_key,))
                self.assertFalse(
                    ResponseCaptureAddon().arm(
                        policy(allowed_json_keys=invalid_keys),
                        RecordingPublisher(allowed_schema_keys=invalid_keys),
                    )
                )
        self.assertEqual(addon.state, DISARMED)
        addon.response(flow)
        self.assertEqual(sum(tracker.values()), 0)

    def test_explicit_arm_is_one_shot(self):
        addon = ResponseCaptureAddon()
        self.assertTrue(addon.arm(policy(), RecordingPublisher()))
        self.assertEqual(addon.state, ARMED)
        self.assertFalse(addon.arm(policy(), RecordingPublisher()))

    def test_non_target_metadata_never_reads_body(self):
        cases = (
            {"host": "other.synthetic.invalid"},
            {"status_code": 204},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                addon = ResponseCaptureAddon()
                self.assertTrue(addon.arm(policy(), RecordingPublisher()))
                flow, tracker = synthetic_flow(safe_body(), **overrides)
                addon.response(flow)
                self.assertEqual(tracker["response_body_reads"], 0)
                self.assertEqual(tracker["forbidden_request_reads"], 0)
                self.assertEqual(tracker["forbidden_response_header_reads"], 0)
                self.assertEqual(tracker["flow_mutations"], 0)

    def test_request_tuple_mismatches_do_not_touch_response_surface(self):
        cases = (
            {"method": "POST"},
            {"host": "other.synthetic.invalid"},
            {"path": "/v1/other"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                addon = ResponseCaptureAddon()
                self.assertTrue(addon.arm(policy(), RecordingPublisher()))
                flow, tracker = synthetic_flow(safe_body(), **overrides)
                addon.response(flow)
                self.assertEqual(addon.state, ARMED)
                self.assertEqual(tracker["request_method_reads"], 1)
                self.assertEqual(tracker["request_host_reads"], 1)
                self.assertEqual(tracker["request_path_reads"], 1)
                self.assertEqual(tracker["response_object_reads"], 0)
                self.assertEqual(tracker["response_status_reads"], 0)
                self.assertEqual(tracker["response_headers_object_reads"], 0)
                self.assertEqual(tracker["response_body_reads"], 0)
                self.assertEqual(tracker["forbidden_request_reads"], 0)
                self.assertEqual(tracker["flow_mutations"], 0)

    def test_invalid_request_metadata_latches_before_response_and_future_flows(self):
        cases = (
            {"method": "get"},
            {"method": None},
            {"path": "/v1/discovery?unexpected"},
            {"path": "/v1/:dynamic"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                addon = ResponseCaptureAddon()
                self.assertTrue(addon.arm(policy(), RecordingPublisher()))
                flow, tracker = synthetic_flow(safe_body(), **overrides)
                addon.response(flow)
                self.assertEqual(addon.state, STOPPED)
                self.assertEqual(
                    addon.stop_receipt.reason_code,
                    "REQUEST_METADATA_INVALID",
                )
                self.assertEqual(tracker["request_method_reads"], 1)
                self.assertEqual(tracker["request_host_reads"], 1)
                self.assertEqual(tracker["request_path_reads"], 1)
                self.assertEqual(tracker["response_object_reads"], 0)
                self.assertEqual(tracker["response_status_reads"], 0)
                self.assertEqual(tracker["response_headers_object_reads"], 0)
                self.assertEqual(tracker["response_body_reads"], 0)
                self.assertEqual(tracker["forbidden_request_reads"], 0)
                later, later_tracker = synthetic_flow(safe_body())
                addon.response(later)
                self.assertEqual(sum(later_tracker.values()), 0)

    def test_exact_request_tuple_uses_one_atomic_selector_and_closed_request_surface(self):
        addon = ResponseCaptureAddon()
        capture_policy = policy()
        self.assertTrue(addon.arm(capture_policy, RecordingPublisher()))
        flow, tracker = synthetic_flow(safe_body())
        with mock.patch.object(
            CapturePolicy,
            "select_endpoint",
            autospec=True,
            side_effect=CapturePolicy.select_endpoint,
        ) as selector:
            addon.response(flow)
        self.assertEqual(selector.call_count, 1)
        self.assertEqual(tracker["request_method_reads"], 1)
        self.assertEqual(tracker["request_host_reads"], 1)
        self.assertEqual(tracker["request_path_reads"], 1)
        for field in (
            "request_query_reads",
            "request_url_reads",
            "request_headers_reads",
            "request_body_reads",
            "request_content_reads",
            "request_raw_content_reads",
            "request_path_components_reads",
            "forbidden_request_reads",
        ):
            self.assertEqual(tracker[field], 0)

    def test_target_unknown_metadata_stops_before_body(self):
        cases = (
            {"content_type": "text/plain"},
            {"content_encoding": "gzip"},
            {"content_length": "not-a-number"},
            {"content_length": "１２"},
            {"content_length": "9" * 5000},
            {"content_length": "999999"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                addon = ResponseCaptureAddon()
                self.assertTrue(addon.arm(policy(), RecordingPublisher()))
                flow, tracker = synthetic_flow(safe_body(), **overrides)
                addon.response(flow)
                self.assertEqual(addon.state, STOPPED)
                self.assertEqual(tracker["response_body_reads"], 0)
                self.assertEqual(tracker["flow_mutations"], 0)

    def test_accepted_flow_reads_exact_closed_surface_and_publishes_shape(self):
        publisher = RecordingPublisher()
        addon = ResponseCaptureAddon()
        self.assertTrue(addon.arm(policy(), publisher))
        body = safe_body()
        flow, tracker = synthetic_flow(body, content_length=str(len(body)))
        addon.response(flow)
        self.assertEqual(addon.state, COMPLETED)
        self.assertEqual(addon.event_count, 1)
        self.assertEqual(len(publisher.shapes), 1)
        model = publisher.shapes[0].to_model()
        self.assertEqual(model["schema_version"], "autocapture-sanitized-shape/v1")
        self.assertNotIn("payload_family", model)
        self.assertNotIn("payload_version", model)
        self.assertEqual(tracker["response_body_reads"], 1)
        self.assertEqual(tracker["forbidden_request_reads"], 0)
        self.assertEqual(tracker["forbidden_response_header_reads"], 0)
        self.assertEqual(tracker["forbidden_response_reads"], 0)
        self.assertEqual(tracker["flow_mutations"], 0)

    def test_sensitive_event_clears_prior_shape_and_latches_stop(self):
        publisher = RecordingPublisher()
        addon = ResponseCaptureAddon()
        self.assertTrue(addon.arm(policy(max_events=2), publisher))
        first, first_tracker = synthetic_flow(safe_body())
        addon.response(first)
        self.assertEqual(addon.state, ARMED)
        self.assertEqual(addon.event_count, 1)

        marker = generated_sensitive_marker()
        unsafe = json.dumps(
            {"access_token": marker}, separators=(",", ":")
        ).encode("utf-8")
        second, second_tracker = synthetic_flow(unsafe)
        addon.response(second)
        self.assertEqual(addon.state, STOPPED)
        self.assertEqual(len(publisher.shapes), 0)
        receipt = addon.stop_receipt.to_model()
        serialized = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(marker, serialized)
        self.assertEqual(
            set(receipt),
            {"schema_version", "outcome", "reason_code"},
        )
        self.assertEqual(first_tracker["flow_mutations"], 0)
        self.assertEqual(second_tracker["response_body_reads"], 1)

        later, later_tracker = synthetic_flow(safe_body())
        addon.response(later)
        self.assertEqual(sum(later_tracker.values()), 0)

    def test_sensitive_value_sentinel_clears_prior_shape_and_zeroes_lease(self):
        marker = generated_sensitive_marker()
        publisher = RecordingPublisher()
        addon = ResponseCaptureAddon()
        self.assertTrue(addon.arm(policy(max_events=3), publisher))
        first, _first_tracker = synthetic_flow(safe_body())
        addon.response(first)
        self.assertEqual(addon.event_count, 1)

        retained = []
        original_factory = RawLease.from_proxy_bytes

        def tracked_factory(*args, **kwargs):
            lease = original_factory(*args, **kwargs)
            retained.append((lease, lease._buffer))
            return lease

        body = json.dumps(
            {"catalog": [{"note": marker}]}, separators=(",", ":")
        ).encode("utf-8")
        flow, tracker = synthetic_flow(body)
        with mock.patch(
            "autocapture.addon.RawLease.from_proxy_bytes",
            side_effect=tracked_factory,
        ):
            addon.response(flow)

        self.assertEqual(addon.state, STOPPED)
        self.assertEqual(addon.event_count, 0)
        self.assertEqual(publisher.shapes, [])
        self.assertEqual(tracker["response_body_reads"], 1)
        self.assertEqual(len(retained), 1)
        lease, owned = retained[0]
        self.assertTrue(lease.closed)
        self.assertTrue(all(value == 0 for value in owned))
        self.assertNotIn(marker, json.dumps(addon.stop_receipt.to_model()))

        later, later_tracker = synthetic_flow(safe_body())
        addon.response(later)
        self.assertEqual(sum(later_tracker.values()), 0)

    def test_dynamic_sensitive_key_never_reaches_shape_or_publisher(self):
        marker = generated_sensitive_marker()
        publisher = RecordingPublisher()
        addon = ResponseCaptureAddon()
        self.assertTrue(addon.arm(policy(), publisher))
        body = json.dumps(
            {"catalog": {marker: {"price": 1}}},
            separators=(",", ":"),
        ).encode("utf-8")
        flow, tracker = synthetic_flow(body)
        addon.response(flow)
        self.assertEqual(addon.state, STOPPED)
        self.assertEqual(publisher.shapes, [])
        self.assertEqual(tracker["response_body_reads"], 1)
        self.assertNotIn(marker, json.dumps(addon.stop_receipt.to_model()))

    def test_true_unknown_key_discards_prior_stage_and_latches_value_free_stop(self):
        publisher = RecordingPublisher()
        addon = ResponseCaptureAddon()
        self.assertTrue(addon.arm(policy(max_events=2), publisher))
        first, _first_tracker = synthetic_flow(safe_body())
        addon.response(first)
        self.assertEqual(addon.state, ARMED)
        self.assertEqual(addon.event_count, 1)

        unknown_key = "event.field"
        body = json.dumps(
            {"store": {unknown_key: "synthetic"}},
            separators=(",", ":"),
        ).encode("utf-8")
        flow, tracker = synthetic_flow(body)
        addon.response(flow)

        self.assertEqual(addon.state, STOPPED)
        self.assertEqual(addon.event_count, 0)
        self.assertEqual(publisher.shapes, [])
        self.assertEqual(addon.stop_receipt.reason_code, "UNKNOWN_SCHEMA_KEY")
        self.assertNotIn(unknown_key, json.dumps(addon.stop_receipt.to_model()))
        self.assertEqual(tracker["response_body_reads"], 1)
        later, later_tracker = synthetic_flow(safe_body())
        addon.response(later)
        self.assertEqual(sum(later_tracker.values()), 0)

    def test_decode_failure_is_value_free_and_future_body_reads_are_zero(self):
        addon = ResponseCaptureAddon()
        publisher = RecordingPublisher()
        self.assertTrue(addon.arm(policy(max_events=2), publisher))
        marker = generated_sensitive_marker()
        malformed = ("{\"field\":\"" + marker).encode("utf-8")
        flow, tracker = synthetic_flow(malformed)
        addon.response(flow)
        self.assertEqual(addon.state, STOPPED)
        self.assertEqual(tracker["response_body_reads"], 1)
        receipt = addon.stop_receipt.to_model()
        self.assertNotIn(marker, json.dumps(receipt))
        self.assertEqual(publisher.shapes, [])
        later, later_tracker = synthetic_flow(safe_body())
        addon.response(later)
        self.assertEqual(later_tracker["response_body_reads"], 0)

    def test_body_read_cancellation_never_exposes_exception_content(self):
        marker = generated_sensitive_marker()
        addon = ResponseCaptureAddon()
        self.assertTrue(addon.arm(policy(), RecordingPublisher()))
        failure = SyntheticCancellation(marker)
        flow, tracker = synthetic_flow(safe_body(), read_failure=failure)
        addon.response(flow)
        self.assertEqual(addon.state, STOPPED)
        self.assertEqual(tracker["response_body_reads"], 1)
        self.assertNotIn(
            marker,
            json.dumps(addon.stop_receipt.to_model(), sort_keys=True),
        )

    def test_owned_lease_is_zeroed_after_success_decode_and_sensitive_paths(self):
        cases = (
            safe_body(),
            b"{",
            b'{"access_token":"synthetic"}',
        )
        for case_index, body in enumerate(cases):
            with self.subTest(case_index=case_index):
                retained = []
                original_factory = RawLease.from_proxy_bytes

                def tracked_factory(*args, **kwargs):
                    lease = original_factory(*args, **kwargs)
                    retained.append((lease, lease._buffer))
                    return lease

                addon = ResponseCaptureAddon()
                self.assertTrue(addon.arm(policy(), RecordingPublisher()))
                flow, _tracker = synthetic_flow(body)
                with mock.patch(
                    "autocapture.addon.RawLease.from_proxy_bytes",
                    side_effect=tracked_factory,
                ):
                    addon.response(flow)
                self.assertEqual(len(retained), 1)
                lease, owned = retained[0]
                self.assertTrue(lease.closed)
                self.assertIsNotNone(owned)
                self.assertTrue(all(value == 0 for value in owned))

    def test_owned_lease_is_zeroed_when_projection_is_cancelled(self):
        marker = generated_sensitive_marker()
        retained = []
        original_factory = RawLease.from_proxy_bytes

        def tracked_factory(*args, **kwargs):
            lease = original_factory(*args, **kwargs)
            retained.append((lease, lease._buffer))
            return lease

        addon = ResponseCaptureAddon()
        self.assertTrue(addon.arm(policy(), RecordingPublisher()))
        flow, _tracker = synthetic_flow(safe_body())
        with mock.patch(
            "autocapture.addon.RawLease.from_proxy_bytes",
            side_effect=tracked_factory,
        ), mock.patch.object(
            ShapeAccumulator,
            "stage_json_bytes",
            side_effect=SyntheticCancellation(marker),
        ):
            addon.response(flow)
        self.assertEqual(addon.state, STOPPED)
        self.assertEqual(len(retained), 1)
        lease, owned = retained[0]
        self.assertTrue(lease.closed)
        self.assertIsNotNone(owned)
        self.assertTrue(all(value == 0 for value in owned))
        self.assertNotIn(marker, json.dumps(addon.stop_receipt.to_model()))

    def test_owned_lease_expiry_after_projection_zeroes_and_clears(self):
        class StepClock:
            def __init__(self):
                self.value = 0.0

            def __call__(self):
                self.value += 0.4
                return self.value

        clock = StepClock()
        retained = []
        original_factory = RawLease.from_proxy_bytes

        def tracked_factory(*args, **kwargs):
            lease = original_factory(*args, **kwargs)
            retained.append((lease, lease._buffer))
            return lease

        addon = ResponseCaptureAddon(clock=clock)
        expiring_policy = policy()
        self.assertTrue(addon.arm(expiring_policy, RecordingPublisher()))
        flow, _tracker = synthetic_flow(safe_body())
        with mock.patch(
            "autocapture.addon.RawLease.from_proxy_bytes",
            side_effect=tracked_factory,
        ):
            addon.response(flow)
        self.assertEqual(addon.state, STOPPED)
        self.assertEqual(addon.event_count, 0)
        self.assertEqual(len(retained), 1)
        lease, owned = retained[0]
        self.assertTrue(lease.closed)
        self.assertIsNotNone(owned)
        self.assertTrue(all(value == 0 for value in owned))

    def test_length_mismatch_and_actual_body_limit_fail_closed(self):
        cases = (
            (
                safe_body(),
                {"content_length": str(len(safe_body()) + 1)},
                "DECLARED_LENGTH_MISMATCH",
                512,
            ),
            (
                b'{"field":"' + (b"x" * 80) + b'"}',
                {},
                "BODY_BYTE_LIMIT",
                64,
            ),
        )
        for body, options, code, body_limit in cases:
            with self.subTest(code=code):
                addon = ResponseCaptureAddon()
                self.assertTrue(
                    addon.arm(
                        policy(
                            max_body_bytes=body_limit,
                            max_total_body_bytes=1024,
                        ),
                        RecordingPublisher(),
                    )
                )
                flow, tracker = synthetic_flow(body, **options)
                addon.response(flow)
                self.assertEqual(addon.state, STOPPED)
                self.assertEqual(addon.stop_receipt.reason_code, code)
                self.assertEqual(tracker["response_body_reads"], 1)
                self.assertEqual(addon.event_count, 0)

    def test_cumulative_body_limit_clears_prior_aggregate(self):
        body = json.dumps({"field": "safe"}, separators=(",", ":")).encode("utf-8")
        publisher = RecordingPublisher()
        addon = ResponseCaptureAddon()
        self.assertTrue(
            addon.arm(
                policy(
                    max_events=3,
                    max_body_bytes=len(body),
                    max_total_body_bytes=len(body) + 1,
                ),
                publisher,
            )
        )
        first, _first_tracker = synthetic_flow(body)
        addon.response(first)
        self.assertEqual(addon.event_count, 1)

        second, second_tracker = synthetic_flow(body)
        addon.response(second)
        self.assertEqual(addon.state, STOPPED)
        self.assertEqual(addon.stop_receipt.reason_code, "TOTAL_BYTE_LIMIT")
        self.assertEqual(second_tracker["response_body_reads"], 1)
        self.assertEqual(addon.event_count, 0)
        self.assertEqual(publisher.shapes, [])

        later, later_tracker = synthetic_flow(body)
        addon.response(later)
        self.assertEqual(sum(later_tracker.values()), 0)

    def test_done_publishes_multiple_events_exactly_once(self):
        publisher = RecordingPublisher()
        addon = ResponseCaptureAddon()
        self.assertTrue(addon.arm(policy(max_events=3), publisher))
        for body in (b'{"field":1}', b'{"field":"safe"}'):
            flow, _tracker = synthetic_flow(body)
            addon.response(flow)
        self.assertEqual(addon.state, ARMED)
        addon.done()
        self.assertEqual(addon.state, COMPLETED)
        self.assertEqual(len(publisher.shapes), 1)
        self.assertEqual(publisher.shapes[0].event_count, 2)
        self.assertTrue(addon.finalize() is False)

    def test_window_expiry_reads_no_flow_and_publishes_nothing(self):
        clock = ManualClock()
        publisher = RecordingPublisher()
        addon = ResponseCaptureAddon(clock=clock)
        self.assertTrue(addon.arm(policy(), publisher))
        clock.advance(31)
        flow, tracker = synthetic_flow(safe_body())
        addon.response(flow)
        self.assertEqual(addon.state, COMPLETED)
        self.assertEqual(sum(tracker.values()), 0)
        self.assertEqual(publisher.shapes, [])

    def test_invalid_or_regressing_clock_stops_before_body_read(self):
        class SequenceClock:
            def __init__(self, values):
                self._values = iter(values)

            def __call__(self):
                return next(self._values)

        invalid_values = (
            float("nan"),
            float("inf"),
            True,
            "1.0",
            object(),
        )
        for invalid in invalid_values + (float("1.7976931348623157e308"),):
            with self.subTest(stage="arm", invalid_type=type(invalid).__name__):
                addon = ResponseCaptureAddon(clock=lambda invalid=invalid: invalid)
                self.assertFalse(addon.arm(policy(), RecordingPublisher()))
                self.assertEqual(addon.state, DISARMED)

        for invalid in invalid_values:
            for values, stage in (
                ((0.0, invalid), "entry"),
                ((0.0, 0.1, invalid), "pre_body"),
            ):
                with self.subTest(stage=stage, invalid_type=type(invalid).__name__):
                    addon = ResponseCaptureAddon(clock=SequenceClock(values))
                    self.assertTrue(addon.arm(policy(), RecordingPublisher()))
                    flow, tracker = synthetic_flow(safe_body())
                    addon.response(flow)
                    self.assertEqual(addon.state, STOPPED)
                    self.assertEqual(
                        addon.stop_receipt.reason_code,
                        "OBSERVATION_TIMEOUT",
                    )
                    self.assertEqual(tracker["response_body_reads"], 0)
                    self.assertEqual(tracker["flow_mutations"], 0)

        addon = ResponseCaptureAddon(clock=SequenceClock((10.0, 9.0)))
        self.assertTrue(addon.arm(policy(), RecordingPublisher()))
        flow, tracker = synthetic_flow(safe_body())
        addon.response(flow)
        self.assertEqual(addon.state, STOPPED)
        self.assertEqual(addon.stop_receipt.reason_code, "OBSERVATION_TIMEOUT")
        self.assertEqual(tracker["response_body_reads"], 0)

    def test_window_expiring_during_metadata_gate_never_reads_body(self):
        clock = ManualClock()
        addon = ResponseCaptureAddon(clock=clock)
        self.assertTrue(addon.arm(policy(), RecordingPublisher()))

        def advance_after_last_header(name):
            if name == "content-encoding":
                clock.advance(31)

        flow, tracker = synthetic_flow(
            safe_body(),
            after_header_read=advance_after_last_header,
        )
        addon.response(flow)
        self.assertEqual(addon.state, STOPPED)
        self.assertEqual(addon.stop_receipt.reason_code, "OBSERVATION_TIMEOUT")
        self.assertEqual(tracker["response_body_reads"], 0)

    def test_publisher_exception_is_replaced_by_closed_stop(self):
        marker = generated_sensitive_marker()
        publisher = RecordingPublisher(RuntimeError(marker))
        addon = ResponseCaptureAddon()
        self.assertTrue(addon.arm(policy(), publisher))
        flow, tracker = synthetic_flow(safe_body())
        addon.response(flow)
        self.assertEqual(addon.state, STOPPED)
        self.assertNotIn(
            marker,
            json.dumps(addon.stop_receipt.to_model(), sort_keys=True),
        )
        self.assertEqual(tracker["flow_mutations"], 0)

    def test_stop_receipt_constructor_has_closed_model(self):
        receipt = ValueFreeStopReceipt("CONTENT_TYPE_UNKNOWN").to_model()
        self.assertEqual(
            receipt,
            {
                "schema_version": "autocapture-stop-receipt/v1",
                "outcome": "STOPPED",
                "reason_code": "CONTENT_TYPE_UNKNOWN",
            },
        )
        with self.assertRaisesRegex(ValueError, "^STOP_REASON_CODE_INVALID$"):
            ValueFreeStopReceipt(generated_sensitive_marker())


if __name__ == "__main__":
    unittest.main()
