from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError, replace

from autocapture.shape import (
    REGISTERED_SAFE,
    SAFE_UNREGISTERED,
    SCHEMA_VERSION,
    SENSITIVE,
    SENSITIVE_KEY_TOKENS,
    TRUE_UNKNOWN,
    SanitizedShape,
    ShapeAccumulator,
    ShapeProbeError,
    classify_schema_key,
    normalize_sensitive_key,
)
from autocapture.tests.fakes import (
    ALLOWED_JSON_KEYS,
    SENSITIVE_SCHEMA_KEY_VARIANTS,
    generated_sensitive_marker,
)


def make_accumulator(**overrides):
    options = {
        "max_depth": 8,
        "max_nodes": 128,
        "max_paths": 64,
        "max_events": 4,
        "allowed_schema_keys": ALLOWED_JSON_KEYS,
        "clock": lambda: 0.0,
        "deadline": 10.0,
    }
    options.update(overrides)
    return ShapeAccumulator(**options)


def stage_and_commit(accumulator, payload):
    staged = accumulator.stage_json_bytes(bytearray(payload))
    accumulator.commit(staged)
    return staged


class ShapeProjectionTests(unittest.TestCase):
    def test_exact_model_pointer_wildcard_presence_types_and_cardinality(self):
        accumulator = make_accumulator()
        stage_and_commit(
            accumulator,
            b'{"store":{"id":7,"tags":["alpha-value","beta-value"]},'
            b'"address":"public-shop-address","phone":"public-shop-phone"}',
        )
        stage_and_commit(
            accumulator,
            b'{"store":{"id":"synthetic-id","tags":["gamma-value"]},'
            b'"name":"public-shop-name"}',
        )

        shape = accumulator.build()
        model = shape.to_model()

        self.assertEqual(
            list(model),
            [
                "schema_version",
                "event_count",
                "nodes",
                "sanitized_shape_digest",
            ],
        )
        self.assertEqual(model["schema_version"], SCHEMA_VERSION)
        self.assertEqual(model["event_count"], 2)
        self.assertRegex(
            model["sanitized_shape_digest"], r"^sha256:[0-9a-f]{64}$"
        )

        nodes = {node["path"]: node for node in model["nodes"]}
        self.assertEqual(list(nodes), sorted(nodes))
        self.assertEqual(
            nodes[""],
            {
                "path": "",
                "types": ["object"],
                "parent": None,
                "relation": "root",
                "presence": {"observed_events": 2, "total_events": 2},
                "cardinality": {"minimum": 2, "maximum": 3},
            },
        )
        self.assertEqual(nodes["/store/id"]["types"], ["integer", "string"])
        self.assertEqual(
            nodes["/store/tags"]["cardinality"],
            {"minimum": 1, "maximum": 2},
        )
        self.assertEqual(nodes["/store/tags/*"]["parent"], "/store/tags")
        self.assertEqual(nodes["/store/tags/*"]["relation"], "array_item")
        self.assertEqual(nodes["/address"]["cardinality"], None)
        self.assertEqual(
            nodes["/address"]["presence"],
            {"observed_events": 1, "total_events": 2},
        )

        encoded = json.dumps(model, ensure_ascii=False, sort_keys=True)
        for scalar in (
            "alpha-value",
            "beta-value",
            "gamma-value",
            "synthetic-id",
            "public-shop-address",
            "public-shop-phone",
            "public-shop-name",
        ):
            self.assertNotIn(scalar, encoded)
        self.assertNotIn("family", model)
        self.assertNotIn("version", model)
        self.assertNotIn("scalar", model)
        self.assertNotIn("value_hash", model)

    def test_array_wildcard_and_unknown_key_fail_closed(self):
        accumulator = make_accumulator()
        stage_and_commit(accumulator, b'{"items":[{"z":1},null]}')

        nodes = {
            node["path"]: node for node in accumulator.build().to_model()["nodes"]
        }
        self.assertIn("/items", nodes)
        self.assertIn("/items/*", nodes)
        self.assertIn("/items/*/z", nodes)
        self.assertEqual(
            nodes["/items/*"]["types"], ["null", "object"]
        )
        self.assertEqual(
            nodes["/items/*/z"]["parent"], "/items/*"
        )
        with self.assertRaises(ShapeProbeError) as caught:
            make_accumulator().stage_json_bytes(bytearray(b'{"a/b~c":1}'))
        self.assertEqual(caught.exception.code, "UNKNOWN_SCHEMA_KEY")

    def test_digest_is_canonical_sanitized_base_model_only(self):
        accumulator = make_accumulator()
        stage_and_commit(accumulator, b'{"x":123,"items":[true,false]}')
        shape = accumulator.build()
        model = shape.to_model()
        base = dict(model)
        digest = base.pop("sanitized_shape_digest")
        canonical = json.dumps(
            base,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        expected = "sha256:" + hashlib.sha256(canonical).hexdigest()

        self.assertEqual(digest, expected)
        self.assertEqual(shape.recompute_digest(), expected)
        shape.validate()

    def test_sanitized_shape_is_frozen_and_rejects_digest_tampering(self):
        accumulator = make_accumulator()
        stage_and_commit(accumulator, b'{"x":1}')
        shape = accumulator.build()

        with self.assertRaises(FrozenInstanceError):
            shape.event_count = 2
        tampered = replace(shape, sanitized_shape_digest="sha256:" + "0" * 64)
        with self.assertRaises(ShapeProbeError) as caught:
            tampered.validate()
        self.assertEqual(caught.exception.code, "SANITIZED_DIGEST_MISMATCH")

    def test_safe_unregistered_nested_list_keys_are_pointer_only(self):
        accumulator = make_accumulator(
            allowed_schema_keys=frozenset(("store", "items"))
        )
        stage_and_commit(
            accumulator,
            b'{"store":{"discoveryExtra":[{"nestedField":"value"}]},'
            b'"items":[{"listExtra":1}]}',
        )
        model = accumulator.build().to_model()
        paths = {node["path"] for node in model["nodes"]}
        self.assertTrue(
            {
                "/store/discoveryExtra",
                "/store/discoveryExtra/*/nestedField",
                "/items/*/listExtra",
            }.issubset(paths)
        )
        encoded = json.dumps(model, sort_keys=True)
        for forbidden in (
            "classification",
            "candidate",
            "observed_key",
            "key_hash",
            "key_length",
            "fragment",
            "value",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_sanitized_shape_revalidates_safe_and_unsafe_pointer_tokens(self):
        accumulator = make_accumulator(allowed_schema_keys=frozenset(("x",)))
        stage_and_commit(accumulator, b'{"x":1}')
        shape = accumulator.build()
        root, child = shape.nodes

        safe_node = replace(child, path="/unregisteredField", parent="")
        safe_shape = replace(shape, nodes=(root, safe_node), sanitized_shape_digest="")
        safe_shape = replace(
            safe_shape,
            sanitized_shape_digest=safe_shape.recompute_digest(),
        )
        safe_shape.validate()

        for path in ("/access_token", "/unknown.field"):
            with self.subTest(path_kind=path[1:2]):
                unsafe_node = replace(child, path=path, parent="")
                unsafe_shape = replace(
                    shape,
                    nodes=(root, unsafe_node),
                    sanitized_shape_digest="",
                )
                unsafe_shape = replace(
                    unsafe_shape,
                    sanitized_shape_digest=unsafe_shape.recompute_digest(),
                )
                with self.assertRaises(ShapeProbeError) as caught:
                    unsafe_shape.validate()
                self.assertEqual(caught.exception.code, "INVALID_SHAPE_MODEL")


class ShapeFailureTests(unittest.TestCase):
    def assert_code(self, expected, operation):
        with self.assertRaises(ShapeProbeError) as caught:
            operation()
        self.assertEqual(caught.exception.code, expected)
        self.assertEqual(str(caught.exception), expected)
        self.assertEqual(caught.exception.args, (expected,))
        return caught.exception

    def test_strict_utf8_json_duplicate_and_nonfinite_fail_closed(self):
        cases = (
            ("INVALID_UTF8", bytearray(b'{"x":"\xff"}')),
            ("INVALID_JSON", bytearray(b'{"x":')),
            ("DUPLICATE_KEY", bytearray(b'{"x":1,"x":2}')),
            ("NONFINITE_NUMBER", bytearray(b'{"x":NaN}')),
            ("NONFINITE_NUMBER", bytearray(b'{"x":1e9999}')),
        )
        for case_index, (code, raw) in enumerate(cases):
            with self.subTest(case_index=case_index, code=code):
                accumulator = make_accumulator()
                self.assert_code(code, lambda: accumulator.stage_json_bytes(raw))
                self.assertEqual(accumulator.event_count, 0)

    def test_schema_key_classifier_has_one_sensitive_first_four_state_table(self):
        registered = frozenset(("store", "registeredField", "accessToken"))
        cases = (
            ("accessToken", SENSITIVE),
            ("store", REGISTERED_SAFE),
            ("registeredField", REGISTERED_SAFE),
            ("eventLocalField", SAFE_UNREGISTERED),
            ("field.with.dot", TRUE_UNKNOWN),
            ("field000000", TRUE_UNKNOWN),
            ("x" * 65, TRUE_UNKNOWN),
            ("non_ascii_\u8def", TRUE_UNKNOWN),
            ("bad\x01control", TRUE_UNKNOWN),
            (None, TRUE_UNKNOWN),
        )
        for key, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_schema_key(key, registered), expected)

        self.assertEqual(
            classify_schema_key("accessToken", frozenset(("accessToken",))),
            SENSITIVE,
        )
        self.assertEqual(
            classify_schema_key("registeredField", ("registeredField",)),
            TRUE_UNKNOWN,
        )

    def test_root_scalar_and_unsupported_values_fail_closed(self):
        for case_index, raw in enumerate((b"null", b"true", b"123", b'"text"')):
            with self.subTest(case_index=case_index):
                self.assert_code(
                    "ROOT_SCALAR",
                    lambda raw=raw: make_accumulator().stage_json_bytes(
                        bytearray(raw)
                    ),
                )
        self.assert_code(
            "UNSUPPORTED_VALUE",
            lambda: make_accumulator().stage_json_bytes(
                bytearray(b'{"x":"\\ud800"}')
            ),
        )
        self.assert_code(
            "UNSUPPORTED_INPUT",
            lambda: make_accumulator().stage_json_bytes(b'{"x":1}'),
        )

    def test_sensitive_key_closed_set_has_frozen_minimum(self):
        minimum = {
            "authorization",
            "cookie",
            "token",
            "access_token",
            "refresh_token",
            "session",
            "session_id",
            "password",
            "passwd",
            "secret",
            "credential",
            "captcha",
            "verification_code",
            "sms_code",
            "openid",
            "unionid",
            "user_id",
            "account_id",
            "device_id",
            "id_card",
            "idcard",
            "recipient_phone",
            "recipient_mobile",
            "recipient_name",
            "delivery_address",
            "home_address",
            "personal_email",
        }
        self.assertTrue(minimum.issubset(SENSITIVE_KEY_TOKENS))

        for token in minimum:
            raw = bytearray(json.dumps({token: "sensitive-sentinel"}).encode())
            with self.subTest(token=token):
                error = self.assert_code(
                    "SENSITIVE_KEY",
                    lambda raw=raw: make_accumulator().stage_json_bytes(raw),
                )
                self.assertNotIn(token, str(error))
                self.assertNotIn("sensitive-sentinel", str(error))

    def test_sensitive_key_normalization_is_exact_not_generic(self):
        self.assertEqual(normalize_sensitive_key("accessToken"), "access_token")
        self.assertEqual(normalize_sensitive_key("recipient-phone"), "recipient_phone")
        self.assertEqual(normalize_sensitive_key("OpenID"), "open_id")

        accumulator = make_accumulator()
        stage_and_commit(
            accumulator,
            b'{"id":1,"name":"shop","phone":"public","email":"public",'
            b'"address":"public","account":"business"}',
        )
        paths = {
            node["path"] for node in accumulator.build().to_model()["nodes"]
        }
        self.assertTrue(
            {"/id", "/name", "/phone", "/email", "/address", "/account"}.issubset(
                paths
            )
        )

        benign_business_keys = frozenset(
            ("productId", "storeId", "orderId", "userPaid", "capillaryMonkey")
        )
        benign = make_accumulator(allowed_schema_keys=benign_business_keys)
        stage_and_commit(
            benign,
            b'{"productId":1,"storeId":2,"orderId":3,'
            b'"userPaid":true,"capillaryMonkey":"public"}',
        )
        self.assertEqual(benign.event_count, 1)

    def test_sensitive_value_sentinel_stops_at_nested_and_list_positions(self):
        marker = generated_sensitive_marker()
        cases = (
            ({"catalog": {"note": marker}}, marker),
            ({"catalog": [{"note": marker}]}, marker),
            (
                {"catalog": {"note": "SYNTHETIC_SECRET_CANARY"}},
                "SYNTHETIC_SECRET_CANARY",
            ),
            (
                {"catalog": [{"note": "sk_live_abcdefghijklmnopqrstuvwxyz"}]},
                "sk_live_abcdefghijklmnopqrstuvwxyz",
            ),
        )
        for payload, sentinel in cases:
            with self.subTest(container=type(payload["catalog"]).__name__):
                raw = bytearray(
                    json.dumps(payload, separators=(",", ":")).encode("utf-8")
                )
                error = self.assert_code(
                    "SENSITIVE_VALUE",
                    lambda raw=raw: make_accumulator().stage_json_bytes(raw),
                )
                self.assertNotIn(sentinel, str(error))

    def test_sensitive_or_dynamic_schema_keys_fail_before_path_creation(self):
        marker = generated_sensitive_marker()
        cases = tuple(
            ("SENSITIVE_KEY", key)
            for key in SENSITIVE_SCHEMA_KEY_VARIANTS
        ) + (
            ("SENSITIVE_KEY", "apiKey"),
            ("SENSITIVE_KEY", marker),
            ("UNKNOWN_SCHEMA_KEY", "1234567890123456"),
            ("UNKNOWN_SCHEMA_KEY", "field.with.dot"),
        )
        for code, key in cases:
            with self.subTest(code=code):
                raw = bytearray(
                    json.dumps({key: {"price": 1}}, separators=(",", ":")).encode(
                        "utf-8"
                    )
                )
                error = self.assert_code(
                    code,
                    lambda raw=raw: make_accumulator().stage_json_bytes(raw),
                )
                self.assertNotIn(key, str(error))

    def test_numeric_token_length_is_version_independent_and_value_free(self):
        marker = "9" * 5000
        raw = bytearray(b'{"number":' + marker.encode("ascii") + b"}")
        error = self.assert_code(
            "NUMERIC_TOKEN_LIMIT",
            lambda: make_accumulator().stage_json_bytes(raw),
        )
        self.assertNotIn(marker, str(error))

    def test_depth_node_and_path_budgets_are_fail_closed(self):
        cases = (
            (
                "MAX_DEPTH_EXCEEDED",
                make_accumulator(max_depth=1),
                b'{"a":{"b":1}}',
            ),
            (
                "MAX_NODES_EXCEEDED",
                make_accumulator(max_nodes=2),
                b'{"a":1,"b":2}',
            ),
            (
                "MAX_PATHS_EXCEEDED",
                make_accumulator(max_paths=2),
                b'{"a":1,"b":2}',
            ),
        )
        for code, accumulator, raw in cases:
            with self.subTest(code=code):
                self.assert_code(
                    code,
                    lambda accumulator=accumulator, raw=raw: accumulator.stage_json_bytes(
                        bytearray(raw)
                    ),
                )
                self.assertEqual(accumulator.event_count, 0)

    def test_event_budget_and_failed_stage_do_not_mutate_aggregate(self):
        accumulator = make_accumulator(max_events=1)
        stage_and_commit(accumulator, b'{"x":1}')
        before = accumulator.build().to_model()

        staged = accumulator.stage_json_bytes(bytearray(b'{"y":2}'))
        self.assert_code("MAX_EVENTS_EXCEEDED", lambda: accumulator.commit(staged))
        self.assert_code(
            "SENSITIVE_KEY",
            lambda: accumulator.stage_json_bytes(
                bytearray(b'{"recipient_phone":"sensitive-sentinel"}')
            ),
        )
        self.assertEqual(accumulator.build().to_model(), before)

    def test_observation_deadline_is_checked_before_stage_and_commit(self):
        now = [0.0]
        accumulator = make_accumulator(clock=lambda: now[0], deadline=5.0)
        staged = accumulator.stage_json_bytes(bytearray(b'{"x":1}'))
        self.assertEqual(accumulator.event_count, 0)

        now[0] = 5.0
        self.assert_code(
            "OBSERVATION_WINDOW_EXPIRED", lambda: accumulator.commit(staged)
        )
        self.assertEqual(accumulator.event_count, 0)
        self.assert_code(
            "OBSERVATION_WINDOW_EXPIRED",
            lambda: accumulator.stage_json_bytes(bytearray(b'{"x":1}')),
        )

    def test_stage_owner_consumption_clear_and_empty_build(self):
        first = make_accumulator()
        second = make_accumulator()
        staged = first.stage_json_bytes(bytearray(b'{"x":1}'))

        self.assert_code("INVALID_STAGE", lambda: second.commit(staged))
        first.commit(staged)
        self.assert_code("INVALID_STAGE", lambda: first.commit(staged))
        first.clear()
        self.assertEqual(first.event_count, 0)
        self.assert_code("EMPTY_SHAPE", first.build)
        self.assert_code("INVALID_STAGE", lambda: first.commit(staged))

    def test_build_is_allowed_after_window_closes(self):
        now = [0.0]
        accumulator = make_accumulator(clock=lambda: now[0], deadline=5.0)
        stage_and_commit(accumulator, b'{"x":1}')
        now[0] = 5.0

        self.assertIsInstance(accumulator.build(), SanitizedShape)

    def test_invalid_policy_fails_with_stable_code(self):
        cases = (
            {"max_depth": 0},
            {"max_nodes": True},
            {"max_paths": -1},
            {"max_events": 0},
            {"clock": None},
            {"deadline": True},
            {"deadline": float("inf")},
        )
        for override in cases:
            with self.subTest(override=override):
                self.assert_code(
                    "INVALID_POLICY", lambda override=override: make_accumulator(**override)
                )

    def test_clock_failure_is_reduced_to_stable_value_free_code(self):
        def broken_clock():
            raise RuntimeError("clock-sensitive-sentinel")

        accumulator = make_accumulator(clock=broken_clock)
        error = self.assert_code(
            "OBSERVATION_WINDOW_EXPIRED",
            lambda: accumulator.stage_json_bytes(bytearray(b'{"x":1}')),
        )
        self.assertNotIn("clock-sensitive-sentinel", str(error))


if __name__ == "__main__":
    unittest.main()
