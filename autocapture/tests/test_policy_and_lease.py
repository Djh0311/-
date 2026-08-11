from __future__ import annotations

import math
import pickle
import unittest
from dataclasses import FrozenInstanceError

from autocapture.lease import (
    HARD_MAX_LEASE_BYTES,
    HARD_MAX_LEASE_SECONDS,
    LeaseError,
    RawLease,
)
from autocapture.policy import (
    ENDPOINT_MATCH,
    ENDPOINT_METADATA_INVALID,
    ENDPOINT_MISMATCH,
    HARD_MAX_BODY_BYTES,
    HARD_MAX_JSON_DEPTH,
    HARD_MAX_LEASE_SECONDS as POLICY_MAX_LEASE_SECONDS,
    CapturePolicy,
    EndpointRule,
    PolicyError,
)
from autocapture.tests.fakes import ALLOWED_JSON_KEYS, SENSITIVE_SCHEMA_KEY_VARIANTS


class FakeClock:
    def __init__(self, now: float = 10.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def valid_policy(**changes: object) -> CapturePolicy:
    values = {
        "endpoint_rules": (
            EndpointRule("GET", "api.example.invalid", "/v1/discovery"),
        ),
        "allowed_statuses": (200,),
        "allowed_content_types": ("application/json",),
        "allowed_json_keys": ALLOWED_JSON_KEYS,
        "max_body_bytes": 1024,
        "max_total_body_bytes": 4096,
        "max_json_depth": 12,
        "max_json_nodes": 500,
        "max_shape_paths": 100,
        "max_events": 4,
        "observation_window_seconds": 10.0,
        "max_lease_seconds": 2.0,
    }
    values.update(changes)
    return CapturePolicy(**values)


class CapturePolicyTests(unittest.TestCase):
    def test_validated_returns_same_frozen_policy(self) -> None:
        policy = valid_policy()
        self.assertIs(policy.validated(), policy)
        with self.assertRaises(FrozenInstanceError):
            policy.max_events = 2  # type: ignore[misc]

    def test_allowlists_and_atomic_selector_match_exact_values_only(self) -> None:
        policy = valid_policy().validated()
        self.assertEqual(
            policy.select_endpoint("GET", "api.example.invalid", "/v1/discovery"),
            ENDPOINT_MATCH,
        )
        self.assertEqual(
            policy.select_endpoint("GET", "sub.api.example.invalid", "/v1/discovery"),
            ENDPOINT_MISMATCH,
        )
        self.assertEqual(
            policy.select_endpoint("get", "api.example.invalid", "/v1/discovery"),
            ENDPOINT_METADATA_INVALID,
        )
        self.assertTrue(policy.allows_status(200))
        self.assertFalse(policy.allows_status(True))
        self.assertTrue(policy.allows_content_type("application/json"))
        self.assertFalse(policy.allows_content_type("application/json; charset=utf-8"))

    def test_endpoint_host_rejects_wildcard_scheme_path_port_and_params(self) -> None:
        invalid_hosts = (
            "*.example.invalid",
            "https://api.example.invalid",
            "api.example.invalid/path",
            "api.example.invalid:443",
            "api.example.invalid;param",
            "127.0.0.1",
        )
        for host in invalid_hosts:
            with self.subTest(host=host):
                with self.assertRaisesRegex(PolicyError, "^POLICY_ENDPOINT_HOST_INVALID$"):
                    valid_policy(
                        endpoint_rules=(EndpointRule("GET", host, "/v1/discovery"),)
                    ).validated()

    def test_content_type_rejects_wildcard_params_and_noncanonical_case(self) -> None:
        invalid_types = (
            "application/*",
            "application/json; charset=utf-8",
            "Application/JSON",
            "text/plain",
            "image/png",
        )
        for content_type in invalid_types:
            with self.subTest(content_type=content_type):
                with self.assertRaisesRegex(PolicyError, "^POLICY_CONTENT_TYPE_INVALID$"):
                    valid_policy(allowed_content_types=(content_type,)).validated()

    def test_exact_json_and_structured_json_media_types_are_valid(self) -> None:
        for content_type in (
            "application/json",
            "application/problem+json",
            "application/vnd.synthetic+json",
        ):
            with self.subTest(content_type=content_type):
                self.assertEqual(
                    valid_policy(
                        allowed_content_types=(content_type,)
                    ).validated().allowed_content_types[0],
                    content_type,
                )

    def test_mutable_or_duplicate_allowlists_fail_closed(self) -> None:
        valid_rule = EndpointRule("GET", "api.example.invalid", "/v1/discovery")
        with self.assertRaisesRegex(PolicyError, "^POLICY_ENDPOINT_RULE_SET_INVALID$"):
            valid_policy(endpoint_rules=[valid_rule]).validated()
        with self.assertRaisesRegex(PolicyError, "^POLICY_ENDPOINT_RULE_INVALID$"):
            valid_policy(endpoint_rules=(object(),)).validated()
        with self.assertRaisesRegex(PolicyError, "^POLICY_ENDPOINT_RULE_SET_DUPLICATE$"):
            valid_policy(
                endpoint_rules=(valid_rule, valid_rule)
            ).validated()
        with self.assertRaisesRegex(PolicyError, "^POLICY_STATUS_SET_DUPLICATE$"):
            valid_policy(allowed_statuses=(200, 200)).validated()
        with self.assertRaisesRegex(PolicyError, "^POLICY_JSON_KEY_SET_INVALID$"):
            valid_policy(allowed_json_keys=["store"]).validated()
        with self.assertRaisesRegex(PolicyError, "^POLICY_JSON_KEY_SET_DUPLICATE$"):
            valid_policy(allowed_json_keys=("store", "store")).validated()

    def test_json_key_allowlist_rejects_sensitive_or_dynamic_control_keys(self):
        invalid_keys = SENSITIVE_SCHEMA_KEY_VARIANTS + (
            "apiKey",
            "sk_live_abcdefghijklmnopqrstuvwxyz",
            "SYNTHETIC_SECRET_CANARY",
            "field.with.dot",
            "1234567890123456",
        )
        for key in invalid_keys:
            with self.subTest(key_kind=key[:2]):
                with self.assertRaisesRegex(
                    PolicyError,
                    "^POLICY_JSON_KEY_INVALID$",
                ):
                    valid_policy(allowed_json_keys=(key,)).validated()

    def test_bool_and_hard_limit_values_are_rejected(self) -> None:
        with self.assertRaisesRegex(PolicyError, "^POLICY_INTEGER_BOUND_INVALID$"):
            valid_policy(max_events=True).validated()
        with self.assertRaisesRegex(PolicyError, "^POLICY_INTEGER_BOUND_INVALID$"):
            valid_policy(max_body_bytes=HARD_MAX_BODY_BYTES + 1).validated()
        with self.assertRaisesRegex(PolicyError, "^POLICY_INTEGER_BOUND_INVALID$"):
            valid_policy(max_json_depth=HARD_MAX_JSON_DEPTH + 1).validated()
        with self.assertRaisesRegex(PolicyError, "^POLICY_LEASE_TTL_INVALID$"):
            valid_policy(max_lease_seconds=POLICY_MAX_LEASE_SECONDS + 1).validated()

    def test_cross_bounds_fail_closed(self) -> None:
        with self.assertRaisesRegex(PolicyError, "^POLICY_TOTAL_BODY_BOUND_INVALID$"):
            valid_policy(max_body_bytes=2048, max_total_body_bytes=1024).validated()
        with self.assertRaisesRegex(PolicyError, "^POLICY_SHAPE_BOUND_INVALID$"):
            valid_policy(max_shape_paths=501, max_json_nodes=500).validated()
        with self.assertRaisesRegex(PolicyError, "^POLICY_LEASE_WINDOW_INVALID$"):
            valid_policy(
                observation_window_seconds=1.0,
                max_lease_seconds=2.0,
            ).validated()

    def test_policy_error_is_value_free(self) -> None:
        sentinel = "sensitive-marker.example.invalid/path"
        try:
            valid_policy(
                endpoint_rules=(EndpointRule("GET", sentinel, "/v1/discovery"),)
            ).validated()
        except PolicyError as error:
            self.assertEqual(error.code, "POLICY_ENDPOINT_HOST_INVALID")
            self.assertEqual(str(error), "POLICY_ENDPOINT_HOST_INVALID")
            self.assertNotIn(sentinel, repr(error))
        else:
            self.fail("invalid policy was accepted")

    def test_endpoint_rule_is_frozen_and_subclasses_are_rejected(self) -> None:
        rule = EndpointRule("GET", "api.example.invalid", "/v1/discovery")
        with self.assertRaises(FrozenInstanceError):
            rule.path = "/v1/other"  # type: ignore[misc]

        class DerivedEndpointRule(EndpointRule):
            pass

        with self.assertRaisesRegex(PolicyError, "^POLICY_ENDPOINT_RULE_INVALID$"):
            valid_policy(
                endpoint_rules=(
                    DerivedEndpointRule(
                        "GET",
                        "api.example.invalid",
                        "/v1/discovery",
                    ),
                )
            ).validated()

    def test_endpoint_rule_rejects_noncanonical_method_host_and_path(self) -> None:
        valid = ("GET", "api.example.invalid", "/v1/discovery")
        cases = (
            ("POLICY_ENDPOINT_METHOD_INVALID", ("get", valid[1], valid[2])),
            ("POLICY_ENDPOINT_METHOD_INVALID", ("GET\n", valid[1], valid[2])),
            ("POLICY_ENDPOINT_METHOD_INVALID", ("1", valid[1], valid[2])),
            ("POLICY_ENDPOINT_HOST_INVALID", (valid[0], "API.example.invalid", valid[2])),
            ("POLICY_ENDPOINT_HOST_INVALID", (valid[0], "api.example.invalid?x", valid[2])),
            ("POLICY_ENDPOINT_PATH_INVALID", (valid[0], valid[1], "/")),
            ("POLICY_ENDPOINT_PATH_INVALID", (valid[0], valid[1], "/v1/discovery/")),
            ("POLICY_ENDPOINT_PATH_INVALID", (valid[0], valid[1], "/v1//discovery")),
            ("POLICY_ENDPOINT_PATH_INVALID", (valid[0], valid[1], "/v1/../discovery")),
            ("POLICY_ENDPOINT_PATH_INVALID", (valid[0], valid[1], "/v1/discovery?x=1")),
            ("POLICY_ENDPOINT_PATH_INVALID", (valid[0], valid[1], "/v1/%64iscovery")),
            ("POLICY_ENDPOINT_PATH_INVALID", (valid[0], valid[1], "/v1/{id}")),
            ("POLICY_ENDPOINT_PATH_INVALID", (valid[0], valid[1], "/v1/:id")),
            ("POLICY_ENDPOINT_PATH_INVALID", (valid[0], valid[1], "/v1/123")),
        )
        for expected, values in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(PolicyError, "^" + expected + "$"):
                    valid_policy(endpoint_rules=(EndpointRule(*values),)).validated()

    def test_selector_is_atomic_and_never_forms_a_cross_product(self) -> None:
        first = EndpointRule("GET", "first.example.invalid", "/v1/first")
        second = EndpointRule("POST", "second.example.invalid", "/v2/second")
        policy = valid_policy(endpoint_rules=(first, second)).validated()
        for method in ("GET", "POST"):
            for host in ("first.example.invalid", "second.example.invalid"):
                for path in ("/v1/first", "/v2/second"):
                    with self.subTest(method=method, host=host, path=path):
                        actual = policy.select_endpoint(method, host, path)
                        expected = (
                            ENDPOINT_MATCH
                            if (method, host, path)
                            in {
                                (first.method, first.host, first.path),
                                (second.method, second.host, second.path),
                            }
                            else ENDPOINT_MISMATCH
                        )
                        self.assertEqual(actual, expected)

    def test_selector_metadata_failures_are_closed_and_value_free(self) -> None:
        policy = valid_policy().validated()
        invalid_metadata = (
            (None, "api.example.invalid", "/v1/discovery"),
            ("GET", None, "/v1/discovery"),
            ("GET", "api.example.invalid", None),
            ("GET", "api.example.invalid", "/v1/discovery?query"),
            ("GET", "api.example.invalid", "/v1/[dynamic]"),
            ("GET", "api.example.invalid", "/v1/路径"),
        )
        for method, host, path in invalid_metadata:
            with self.subTest(metadata_type=(type(method), type(host), type(path))):
                self.assertEqual(
                    policy.select_endpoint(method, host, path),
                    ENDPOINT_METADATA_INVALID,
                )


class RawLeaseTests(unittest.TestCase):
    def test_consume_returns_owned_bytearray_and_close_zeroes_same_object(self) -> None:
        raw = b"synthetic sentinel"
        clock = FakeClock()
        lease = RawLease.from_proxy_bytes(raw, 1024, 2.0, clock)
        consumed = lease.consume_once()
        self.assertIsInstance(consumed, bytearray)
        self.assertEqual(consumed, raw)
        self.assertTrue(lease.consumed)
        self.assertFalse(lease.closed)

        lease.close()
        self.assertTrue(lease.closed)
        self.assertEqual(consumed, bytearray(len(raw)))
        lease.close()
        self.assertEqual(consumed, bytearray(len(raw)))

    def test_consume_is_single_use(self) -> None:
        lease = RawLease.from_proxy_bytes(b"synthetic", 1024, 2.0, FakeClock())
        retained = lease.consume_once()
        with self.assertRaisesRegex(LeaseError, "^LEASE_CONSUMED$"):
            lease.consume_once()
        lease.close()
        self.assertTrue(all(value == 0 for value in retained))

    def test_context_manager_closes_on_exception(self) -> None:
        retained = None
        lease = RawLease.from_proxy_bytes(b"synthetic", 1024, 2.0, FakeClock())
        with self.assertRaisesRegex(RuntimeError, "^synthetic-control-error$"):
            with lease:
                retained = lease.consume_once()
                raise RuntimeError("synthetic-control-error")
        self.assertTrue(lease.closed)
        self.assertIsNotNone(retained)
        self.assertTrue(all(value == 0 for value in retained))

    def test_expired_lease_fails_closed_and_zeroes_buffer(self) -> None:
        clock = FakeClock()
        lease = RawLease.from_proxy_bytes(b"synthetic", 1024, 1.0, clock)
        owned = lease._buffer
        clock.now = 11.0
        self.assertTrue(lease.expired())
        with self.assertRaisesRegex(LeaseError, "^LEASE_EXPIRED$"):
            lease.consume_once()
        self.assertTrue(lease.closed)
        self.assertIsNotNone(owned)
        self.assertTrue(all(value == 0 for value in owned))

    def test_copy_time_counts_toward_ttl(self) -> None:
        readings = iter((10.0, 11.0))
        with self.assertRaisesRegex(LeaseError, "^LEASE_EXPIRED$"):
            RawLease.from_proxy_bytes(b"synthetic", 1024, 1.0, lambda: next(readings))

    def test_clock_regression_fails_with_closed_code(self) -> None:
        readings = iter((10.0, 9.0))
        with self.assertRaisesRegex(LeaseError, "^LEASE_CLOCK_INVALID$"):
            RawLease.from_proxy_bytes(b"synthetic", 1024, 1.0, lambda: next(readings))

    def test_clock_failure_during_consume_closes_and_zeroes(self) -> None:
        readings = iter((10.0, 10.0))
        lease = RawLease.from_proxy_bytes(
            b"synthetic",
            1024,
            1.0,
            lambda: next(readings),
        )
        owned = lease._buffer
        with self.assertRaisesRegex(LeaseError, "^LEASE_CLOCK_FAILURE$"):
            lease.consume_once()
        self.assertTrue(lease.closed)
        self.assertIsNotNone(owned)
        self.assertTrue(all(value == 0 for value in owned))

    def test_cancellation_during_consume_closes_and_zeroes(self) -> None:
        class SyntheticCancel(BaseException):
            pass

        readings = iter((10.0, 10.0))

        def clock() -> float:
            try:
                return next(readings)
            except StopIteration:
                raise SyntheticCancel()

        lease = RawLease.from_proxy_bytes(b"synthetic", 1024, 1.0, clock)
        owned = lease._buffer
        with self.assertRaisesRegex(LeaseError, "^LEASE_CLOCK_FAILURE$"):
            lease.consume_once()
        self.assertTrue(lease.closed)
        self.assertIsNotNone(owned)
        self.assertTrue(all(value == 0 for value in owned))

    def test_input_and_bounds_reject_bool_and_hard_limit(self) -> None:
        clock = FakeClock()
        cases = (
            (bytearray(b"x"), 1, 1.0, "LEASE_INPUT_TYPE"),
            (b"x", True, 1.0, "LEASE_MAX_BYTES_INVALID"),
            (b"x", HARD_MAX_LEASE_BYTES + 1, 1.0, "LEASE_MAX_BYTES_INVALID"),
            (b"x", 1, True, "LEASE_TTL_INVALID"),
            (b"x", 1, HARD_MAX_LEASE_SECONDS + 1, "LEASE_TTL_INVALID"),
            (b"x", 1, math.inf, "LEASE_TTL_INVALID"),
        )
        for raw, max_bytes, ttl, code in cases:
            with self.subTest(code=code):
                with self.assertRaisesRegex(LeaseError, "^" + code + "$"):
                    RawLease.from_proxy_bytes(raw, max_bytes, ttl, clock)

    def test_body_limit_error_contains_no_length_or_value(self) -> None:
        raw = b"unique-sensitive-sentinel"
        try:
            RawLease.from_proxy_bytes(raw, 1, 1.0, FakeClock())
        except LeaseError as error:
            self.assertEqual(error.code, "LEASE_BODY_LIMIT")
            self.assertEqual(str(error), "LEASE_BODY_LIMIT")
            self.assertNotIn(str(len(raw)), str(error))
            self.assertNotIn(raw.decode("ascii"), repr(error))
        else:
            self.fail("over-limit input was accepted")

    def test_closed_lease_cannot_be_reentered_or_consumed(self) -> None:
        lease = RawLease.from_proxy_bytes(b"synthetic", 1024, 2.0, FakeClock())
        lease.close()
        with self.assertRaisesRegex(LeaseError, "^LEASE_CLOSED$"):
            lease.consume_once()
        with self.assertRaisesRegex(LeaseError, "^LEASE_CLOSED$"):
            lease.__enter__()

    def test_lease_is_not_serializable(self) -> None:
        lease = RawLease.from_proxy_bytes(b"synthetic", 1024, 2.0, FakeClock())
        try:
            with self.assertRaisesRegex(
                LeaseError,
                "^LEASE_SERIALIZATION_PROHIBITED$",
            ):
                pickle.dumps(lease)
        finally:
            lease.close()


if __name__ == "__main__":
    unittest.main()
