"""Synthetic evidence for the real-entry identification boundaries."""

import contextlib
import asyncio
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from collection_adapter.p26_identification import (
    IdentificationWindow, IdentificationError, MAX_BODY, MAX_TOTAL, MAX_NODES, route_template, key_only_layout,
)
from collection_adapter import p26_identification_host as host
from collection_adapter.p26_transport_preparation import REQUIRED_CAPABILITIES, _FILES


class Clock:
    value = 10.0
    def __call__(self):
        return self.value


def active_window():
    clock = Clock()
    window = IdentificationWindow("Synthetic shop", clock=clock)
    window.start_once()
    slot = window.domain("example.invalid")
    window.allow_domain(slot)
    route = window.route("GET", "example.invalid", "/public/catalog?discarded=never-output")
    window.select_route(route)
    return window, clock, route


def feed_json(window, route, value):
    collector = window.begin_response(route, "identity")
    collector.feed(json.dumps(value).encode())
    collector.feed(b"")
    return collector


class IdentificationBoundaryTests(unittest.TestCase):
    def test_monitoring_batch_accepts_more_than_eight_sequential_bodies_with_bounded_raw_and_fields(self):
        clock = Clock()
        window = IdentificationWindow("Synthetic shop", clock=clock, duration_seconds=None)
        window.inspect_current_domain("example.invalid")
        window.start_once(); window.domain("example.invalid")
        route = window.route("GET", "example.invalid", "/public/catalog")
        window.select_route(route)
        for index in range(12):
            feed_json(window, route, {"name":"Synthetic shop", "price":index, f"field_{index}":True})
        self.assertTrue(window.active())
        self.assertEqual(len(window.observations), 8)
        self.assertEqual(len(window.payloads), 8)
        self.assertLessEqual(len(window.collectors), 8)
        self.assertEqual(window.response_reads, 8)
        self.assertTrue(window.response_reads_at_least)
        self.assertTrue(window.target_matches_at_least)
        paths={row["path"] for row in window.field_catalog.values()}
        for index in range(12): self.assertIn(f"$.field_{index}", paths)
        self.assertEqual(window.probe(11,["price"])["public_value"],11)
        with self.assertRaises(IdentificationError): window.probe(0,["price"])
        clock.value += 60; window.active()
        self.assertEqual(window.payloads,{})
        self.assertTrue(window.field_catalog)
        import jsonschema
        schema=json.loads((Path(__file__).resolve().parents[2]/"contracts/schemas/p26-identification-diagnostic-v1.schema.json").read_text())
        jsonschema.validate(window.diagnostic(),schema)
        window.close()
        self.assertEqual(window.payloads,{})

    def test_monitoring_route_catalog_does_not_stop_at_observed_seventeenth_route(self):
        for duration, limit in ((None, 128), (120, 16)):
            window = IdentificationWindow("Synthetic shop", clock=Clock(), duration_seconds=duration)
            window.inspect_current_domain("example.invalid")
            window.start_once(); window.domain("example.invalid")
            for index in range(limit):
                self.assertEqual(window.route("GET", "example.invalid", f"/public/catalog/{index}"), index)
            self.assertTrue(window.active())
            self.assertIsNone(window.route("GET", "example.invalid", "/public/catalog/overflow"))
            self.assertEqual(window.code, "P26_ROUTING_BUDGET")
            self.assertEqual(window.routes, [])
            self.assertEqual(window.response_reads, 0)

    def test_private_route_segments_are_rejected_before_catalog_or_body_selection(self):
        window = IdentificationWindow("Synthetic shop", clock=Clock(), duration_seconds=None)
        window.inspect_current_domain("example.invalid")
        window.start_once(); window.domain("example.invalid")
        for path in ("/weapp/user/allowance/entry", "/api/accounts/status", "/api/address/list",
                     "/api/orders/list", "/api/payment/status", "/api/session/status",
                     "/api/u%73er/profile", "/api/%E7%94%A8%E6%88%B7/ｕｓｅｒ"):
            self.assertIsNone(window.route("POST", "example.invalid", path))
        self.assertEqual(window.route_rejections["PRIVATE_ROUTE"], 8)
        self.assertIsNone(window.route("GET", "example.invalid", "/public/%FF"))
        self.assertEqual(window.route_rejections["PATH_NOT_SUPPORTED"], 1)
        self.assertEqual(window.routes, [])
        self.assertEqual(window.response_reads, 0)
        self.assertEqual(window.route("POST", "example.invalid", "/public/shop/catalog"), 0)

    def test_unified_current_vendor_route_inspection_never_selects_a_body_or_lookalike(self):
        clock = Clock()
        window = IdentificationWindow("Synthetic shop", clock=clock, duration_seconds=None,
                                      route_domain_suffixes=("meituan.com", "meituan.net", "dianping.com"))
        self.assertIsNone(window.domain("catalog.meituan.com"))
        self.assertEqual(window.allowed_domains, set())
        self.assertEqual(window.attempts, 0)
        window.start_once()
        for domain in ("catalog.meituan.com", "nested.catalog.meituan.net", "catalog.dianping.com"):
            window.domain(domain)
            route = window.route("GET", "192.0.2.1", "/public/catalog", tls_domain=domain)
            self.assertIsNotNone(route)
            self.assertIsNone(window.begin_response(route, "identity"))
        for domain in ("ev il.meituan.com", "evilmeituan.com", "meituan.com.evil.invalid", "api.neixin.cn"):
            window.domain(domain)
            self.assertNotIn(domain, window.allowed_domains)
            self.assertIsNone(window.route("GET", domain, "/public/catalog", tls_domain=domain))
        self.assertIsNone(window.route("GET", "192.0.2.1", "/private/order_info", tls_domain="catalog.meituan.com"))
        self.assertEqual(window.response_reads, 0)
        self.assertEqual(window.payloads, {})
        self.assertEqual(window.target_matches, 0)
        window.close()
        self.assertEqual(window.allowed_domains, set())
        self.assertEqual(window.route_domain_suffixes, ())
        for suffixes in (("com",), ("invalid",), ("meituan.com.evil.invalid",), ["meituan.com"]):
            with self.assertRaises(IdentificationError):
                IdentificationWindow("Synthetic shop", route_domain_suffixes=suffixes)

    def test_route_inspection_preserves_authority_and_selected_actual_tls_source(self):
        window=IdentificationWindow("Synthetic shop",clock=Clock(),duration_seconds=None)
        window.inspect_current_domain("example.invalid"); window.start_once(); window.domain("example.invalid")
        slot=window.route("GET","192.0.2.1","/public/catalog?secret=discard",tls_domain="example.invalid")
        self.assertEqual(slot,0)
        self.assertEqual(window.routes[slot],("GET","192.0.2.1","/public/catalog"))
        self.assertEqual(window.route_origins[slot],"example.invalid")
        self.assertEqual(window.response_reads,0)
        self.assertIsNone(window.route("GET","192.0.2.1","/public/catalog",tls_domain="unselected.invalid"))
        self.assertIsNone(window.route("GET","192.0.2.1","/private/user_info",tls_domain="example.invalid"))
        window.close(); self.assertEqual(window.route_origins,{})

    def test_route_rejection_reasons_are_fixed_counts_without_values(self):
        window=IdentificationWindow("Synthetic shop",clock=Clock(),duration_seconds=None)
        self.assertIsNone(window.route("GET","example.invalid","/public/catalog"))
        self.assertFalse(any(window.route_rejections.values()))
        window.inspect_current_domain("example.invalid"); window.start_once()
        for args in (("GET","other.invalid","/public/catalog"),
                     ("OPTIONS","example.invalid","/public/catalog"),
                     ("GET","example.invalid","not-an-origin-path"),
                     ("GET","example.invalid","/private/user_info?secret=never-output")):
            self.assertIsNone(window.route(*args))
        self.assertEqual(set(window.route_rejections.values()),{1})
        for _ in range(200): window.route("GET","other.invalid","/public/catalog")
        self.assertEqual(window.route_rejections["HOST_NOT_SELECTED"],128)
        self.assertTrue(window.route_rejections_at_least)
        import jsonschema
        schema=json.loads((Path(__file__).resolve().parents[2]/"contracts/schemas/p26-identification-diagnostic-v1.schema.json").read_text())
        jsonschema.validate(window.diagnostic(),schema)
        text=json.dumps(window.diagnostic())
        for value in ("never-output","user_info","other.invalid","public/catalog"):
            self.assertNotIn(value,text)

    def test_current_sni_parameter_prepares_route_inspection_without_consuming_input(self):
        window=IdentificationWindow("Synthetic shop",clock=lambda:self.fail("prepared clock read"))
        window.inspect_current_domain("example.invalid")
        self.assertEqual(window.domains,[])
        self.assertEqual(window.diagnostic()["identification_attempts"],0)
        self.assertEqual(window.diagnostic()["routing_callbacks"],0)
        self.assertEqual(window.diagnostic()["business_responses"],0)
        window.clock=Clock(); window.start_once()
        self.assertEqual(window.domain("example.invalid"),0)
        self.assertEqual(window.route("GET","example.invalid","/public/catalog?discard=private"),0)
        self.assertEqual(window.response_reads,0)
        for domain in ("https://example.invalid/private","example.invalid\nprivate",None):
            prepared=IdentificationWindow("Synthetic shop")
            with self.assertRaises(IdentificationError): prepared.inspect_current_domain(domain)

    def test_monitoring_domain_catalog_handles_observed_eight_domain_exhaustion(self):
        window = IdentificationWindow("Synthetic shop", clock=Clock(), duration_seconds=None)
        window.start_once()
        for index in range(64):
            self.assertEqual(window.domain(f"service-{index}.invalid"), index)
        self.assertTrue(window.active())
        self.assertEqual(len(window.domains), 64)
        self.assertIsNone(window.domain("overflow.invalid"))
        self.assertEqual(window.code, "P26_ROUTING_BUDGET")
        self.assertEqual(window.domains, [])
        classic = IdentificationWindow("Synthetic shop", clock=Clock())
        classic.start_once()
        for index in range(8):
            self.assertEqual(classic.domain(f"service-{index}.invalid"), index)
        self.assertIsNone(classic.domain("overflow.invalid"))
        self.assertEqual(classic.code, "P26_ROUTING_BUDGET")

    def test_monitoring_metadata_counters_saturate_without_a_session_cutoff(self):
        window = IdentificationWindow("Synthetic shop", clock=Clock(), duration_seconds=None)
        window.start_once()
        for _ in range(200):
            window.domain("example.invalid")
            window.begin_response(None, "identity")
        receipt = window.diagnostic()
        self.assertEqual(receipt["routing_callbacks"], 128)
        self.assertTrue(receipt["routing_callbacks_at_least"])
        self.assertEqual(receipt["raw_callbacks"], 64)
        self.assertTrue(receipt["raw_callbacks_at_least"])
        self.assertTrue(window.active())
        self.assertEqual(receipt["business_responses"], 0)

    def test_stalled_response_raw_buffer_expires_independently_of_monitoring(self):
        clock = Clock()
        window = IdentificationWindow("Synthetic shop", clock=clock, duration_seconds=None)
        window.start_once()
        domain = window.domain("example.invalid")
        window.allow_domain(domain)
        route = window.route("GET", "example.invalid", "/public/catalog")
        window.select_route(route)
        collector = window.begin_response(route, "identity")
        collector.feed(b'{"name":')
        clock.value += 60
        self.assertFalse(window.active())
        self.assertEqual(window.code, "P26_RESPONSE_PROCESSING_TIMEOUT")
        self.assertEqual(collector.buffer, bytearray())

    def test_explicit_monitoring_has_no_time_cutoff_but_keeps_stop_boundaries(self):
        clock = Clock()
        window = IdentificationWindow("Synthetic shop", clock=clock, duration_seconds=None)
        window.start_once()
        clock.value += 10000
        self.assertTrue(window.active())
        self.assertEqual(window.attempts, 1)
        clock.value -= 1
        self.assertFalse(window.active())
        self.assertEqual(window.code, "P26_CLOCK_INVALID")
        window = IdentificationWindow("Synthetic shop", clock=Clock(), duration_seconds=None)
        window.start_once()
        window.close("P26_CANCELLED")
        self.assertEqual(window.diagnostic()["live_capture_latch"], "CLOSED")

    def test_unlimited_monitoring_does_not_keep_raw_payload_until_session_end(self):
        clock = Clock()
        window = IdentificationWindow("Synthetic shop", clock=clock, duration_seconds=None)
        window.start_once()
        domain = window.domain("example.invalid")
        window.allow_domain(domain)
        route = window.route("GET", "example.invalid", "/public/catalog")
        window.select_route(route)
        feed_json(window, route, {"name": "Synthetic shop", "price": 8})
        self.assertTrue(window.payloads)
        clock.value += 60
        self.assertTrue(window.active())
        self.assertFalse(window.payloads)
        self.assertTrue(window.observations)
        with self.assertRaises(IdentificationError):
            window.probe(0, ["price"])

    def test_prepared_never_reads_clock_or_input_and_is_zero_attempts(self):
        window = IdentificationWindow("Synthetic shop", clock=lambda: self.fail("prepared clock read"))
        self.assertIsNone(window.domain("example.invalid"))
        self.assertIsNone(window.begin_response(0, "identity"))
        self.assertEqual(window.diagnostic()["identification_attempts"], 0)
        self.assertEqual(window.diagnostic()["raw_callbacks"], 0)
        self.assertEqual(window.state, "PREPARED")

    def test_route_selection_and_query_free_metadata_are_separate(self):
        window, _, route = active_window()
        self.assertIsNone(window.begin_response(None, "identity"))
        self.assertEqual(window.raw_callbacks, 1)
        self.assertEqual(window.response_reads, 0)
        self.assertNotIn("discarded", repr(window.routes))
        self.assertIsNone(window.route("GET", "other.invalid", "/public/catalog"))
        self.assertIsNone(window.route("GET", "example.invalid", "/private/user_info"))
        self.assertEqual(route_template("/public/item/987654321?cookie=forbidden"),
                         "/public/item/<dynamic>")
        self.assertEqual(route_template("/v1/weapp/shop/v2/poi/productlist?private=discard"),
                         "/v1/weapp/shop/v2/poi/productlist")
        self.assertEqual(route_template("/v12/items/1234567"), "/<dynamic>/items/<dynamic>")

    def test_key_layout_skips_scalar_decoding_and_private_subtree_keys(self):
        load = json.loads
        decoded_keys = []
        def key_load(token, *args, **kwargs):
            self.assertNotIn(b"PRIVATE_VALUE", token)
            self.assertNotIn(b"secretChild", token)
            self.assertNotIn(b"Synthetic shop", token)
            decoded_keys.append(load(token, *args, **kwargs))
            return decoded_keys[-1]
        blob = (b'{"name":"Synthetic shop","price":8.25,"items":[{"id":1,"on":true,"unit":null}],'
                b'"user":{"secretChild":"PRIVATE_VALUE"},"cookie":"PRIVATE_VALUE",'
                b'"requestId":123,"session_id":false}')
        with patch("collection_adapter.p26_identification.json.loads", side_effect=key_load):
            fields, categories = key_only_layout(blob)
        text = json.dumps(fields)
        for forbidden in ("PRIVATE_VALUE", "secretChild", "Synthetic shop", "requestId", "session_id", "cookie", "$.user"):
            self.assertNotIn(forbidden, text)
        self.assertIn({"path":"$.items[].id","type":"number"}, fields)
        self.assertEqual(categories, {"CREDENTIAL_KEY":1,"SESSION_KEY":1,"PERSONAL_KEY":1,
                                      "TRANSPORT_KEY":1,"UNCLASSIFIED_KEY":0})

    def test_key_layout_syntax_duplicate_and_size_node_depth_budgets(self):
        for blob in (b'{}x', b'{"a":1,"a":2}', b'{"a":01}', b'{"a":1e}', b'{"a":"\\x"}',
                     b'{"a":true,}', b'[1,]', b'{"a":}', b'"scalar"', b'{"a":"line\n"}'):
            with self.subTest(blob=blob):
                with self.assertRaises(IdentificationError) as caught: key_only_layout(blob)
                self.assertEqual(caught.exception.code, "P26_STRUCTURE_INVALID")
        for blob in (b'[' * 34 + b'0' + b']' * 34, b'[' + b'0,' * MAX_NODES + b'0]'):
            with self.assertRaises(IdentificationError) as caught: key_only_layout(blob)
            self.assertEqual(caught.exception.code, "P26_STRUCTURE_BUDGET")
        with self.assertRaises(IdentificationError) as caught: key_only_layout(b'x' * (MAX_BODY + 1))
        self.assertEqual(caught.exception.code, "P26_RESPONSE_SIZE_LIMIT")

    def test_layout_window_has_no_identity_values_raw_payload_or_result(self):
        for private, expected in (({}, "P26_FIELD_LAYOUT_OBSERVED"),
                                  ({"user":{"secretChild":"PRIVATE_VALUE"}}, "P26_SENSITIVE_INPUT")):
            window, _, route = active_window(); window.key_layout_only = True
            feed_json(window, route, {"name":"Synthetic shop","price":8, **private})
            self.assertEqual(window.code, expected)
            self.assertEqual(window.last_body_route, route)
            self.assertEqual(window.target_matches, 0)
            self.assertEqual(window.payloads, {})
            self.assertEqual(window.observations, [])
            self.assertEqual(window.field_catalog, {})
            self.assertFalse(window.key_layouts[0]["field_values_processed"])
            self.assertEqual(window.key_layouts[0]["target_identity"], "NOT_INSPECTED")
            text = json.dumps(window.key_layouts)
            for forbidden in ("Synthetic shop", "PRIVATE_VALUE", "secretChild"):
                self.assertNotIn(forbidden, text)
            import jsonschema
            schema=json.loads((Path(__file__).resolve().parents[2]/"contracts/schemas/p26-identification-diagnostic-v1.schema.json").read_text())
            jsonschema.validate(window.diagnostic(),schema)
            window.close()

    def test_default_sensitive_body_stops_before_whole_json_or_values_are_decoded(self):
        window, _, route = active_window()
        real_load = json.loads
        def only_key(token, *args, **kwargs):
            self.assertFalse(token.startswith(b"{"))
            self.assertNotIn(b"PRIVATE_VALUE",token)
            return real_load(token,*args,**kwargs)
        with patch("collection_adapter.p26_identification.json.loads", side_effect=only_key):
            collector=window.begin_response(route,"identity")
            collector.feed(b'{"name":"Synthetic shop","cookie":"PRIVATE_VALUE"}')
            collector.feed(b"")
        self.assertEqual(window.code,"P26_SENSITIVE_INPUT")
        self.assertEqual(window.sensitive_rejections["CREDENTIAL_KEY"],1)
        self.assertEqual(window.target_matches,0)
        self.assertEqual(window.observations,[])
        self.assertEqual(collector.buffer,bytearray())

    def test_current_authorized_sensitive_inspection_is_keys_types_only_not_values(self):
        window, _, route = active_window()
        window.key_layout_only = window.sensitive_key_layout_authorized = True
        feed_json(window, route, {"cookie":"PRIVATE_VALUE","user":{"secretChild":"PRIVATE_VALUE"},
                                 "price":8,"name":"Synthetic shop"})
        self.assertTrue(window.active())
        self.assertEqual(window.code,"P26_FIELD_LAYOUT_OBSERVED")
        self.assertEqual(window.diagnostic()["privacy_mode"],"AUTHORIZED_KEY_METADATA_ONLY")
        row=window.key_layouts[0]
        self.assertEqual(row["restricted_fields"],[
            {"path":"$.cookie","type":"string","category":"CREDENTIAL_KEY"},
            {"path":"$.user","type":"object","category":"PERSONAL_KEY"}])
        for value in ("PRIVATE_VALUE","secretChild","Synthetic shop"):
            self.assertNotIn(value,json.dumps(row))
        self.assertFalse(window.payloads)
        self.assertEqual(window.target_matches,0)
        # Metadata permission alone never authorizes the ordinary value path.
        plain, _, plain_route=active_window();plain.sensitive_key_layout_authorized=True
        feed_json(plain,plain_route,{"cookie":"PRIVATE_VALUE"})
        self.assertEqual(plain.code,"P26_SENSITIVE_INPUT")

    def test_public_projection_decodes_only_whitelisted_scalars_and_keeps_array_coordinates(self):
        paths=frozenset({"$.items[].name","$.items[].price"});values=[]
        original=json.loads
        def restricted_load(token,*args,**kwargs):
            self.assertNotIn(b"PRIVATE_VALUE",token)
            self.assertNotIn(b"UNSELECTED_VALUE",token)
            self.assertFalse(token.startswith(b"{"))
            return original(token,*args,**kwargs)
        with patch("collection_adapter.p26_identification.json.loads",side_effect=restricted_load):
            key_only_layout(b'{"cookie":"PRIVATE_VALUE","tracking":"UNSELECTED_VALUE",'
                            b'"items":[{"name":"A","price":8},{"name":"B","price":9}]}',
                            public_paths=paths,public_values=values)
        self.assertEqual(values,[{"path":"$.items[].name","coordinates":["items",0,"name"],"value":"A"},
                                 {"path":"$.items[].price","coordinates":["items",0,"price"],"value":8},
                                 {"path":"$.items[].name","coordinates":["items",1,"name"],"value":"B"},
                                 {"path":"$.items[].price","coordinates":["items",1,"price"],"value":9}])
        for path in ("$.cookie","$.user.name","$.request.headers"):
            with self.assertRaises(IdentificationError):
                key_only_layout(b'{}',public_paths=frozenset({path}),public_values=[])

    def test_public_projection_unavailable_fields_are_explicit_without_partial_complete_record(self):
        for value,reason in ((b'{}','NONSCALAR'),(b'"https://example.invalid/private"','URL_VALUE'),
                             (b'1e400','NONFINITE_NUMBER'),(b'"line\\ntext"','LINE_BREAK')):
            window,_,route=active_window()
            window.key_layout_only=window.sensitive_key_layout_authorized=True
            window.public_projection_paths[window.routes[route][2]]=frozenset({"$.price"})
            collector=window.begin_response(route,"identity")
            collector.feed(b'{"price":'+value+b'}');collector.feed(b'')
            self.assertEqual(window.code,"P26_FIELD_LAYOUT_OBSERVED")
            row=window.projected_observations[0]
            self.assertEqual(row['values'],[])
            self.assertEqual(row['unavailable_fields'][0]['reason'],reason)
            self.assertFalse(row['complete_record'])
            self.assertEqual(window.payloads,{})

    def test_public_projection_expires_and_close_clears_values_without_result(self):
        window,clock,route=active_window()
        window.duration_seconds=None;window.deadline=None
        window.key_layout_only=window.sensitive_key_layout_authorized=True
        window.public_projection_paths[window.routes[route][2]]=frozenset({"$.price"})
        feed_json(window,route,{"price":8,"cookie":"PRIVATE_VALUE"})
        self.assertEqual(window.projected_observations[0]["values"][0]["value"],8)
        self.assertFalse(window.projected_observations[0]["sensitive_values_processed"])
        clock.value+=60
        self.assertTrue(window.active())
        self.assertEqual(window.projected_observations,[])
        feed_json(window,route,{"price":9});window.close()
        self.assertEqual(window.projected_observations,[])
        self.assertEqual(window.public_projection_paths,{})

    def test_privacy_completes_before_identity_shape_and_probes(self):
        for key in ("cookie", "access_token", "session_id", "user_info", "receiver", "order_id"):
            window, _, route = active_window()
            feed_json(window, route, {"name": "Synthetic shop", "nested": {key: "forbidden"}})
            self.assertEqual(window.code, "P26_SENSITIVE_INPUT")
            self.assertEqual(window.target_matches, 0)
            self.assertEqual(window.observations, [])
            self.assertEqual(window.payloads, {})
            self.assertEqual(window.state, "CLOSED")

    def test_target_match_is_only_identity_not_unit_currency_or_complete_result(self):
        window, _, route = active_window()
        feed_json(window, route, {"name": "Synthetic shop", "products": [{"name": "Synthetic item", "price": 8.5}]})
        row = window.observations[0]
        self.assertEqual(window.target_matches, 1)
        for field in ("qualified_business_events", "parsed_records", "published_records"):
            self.assertEqual(window.diagnostic()[field], 0)
        self.assertEqual(window.diagnostic()["business_responses"], 1)
        for field in ("family_version", "amount_unit", "currency"):
            self.assertEqual(row[field], "UNKNOWN")
        self.assertNotIn("Synthetic", json.dumps(row))
        self.assertEqual(window.probe(0, ["products", 0, "price"])["public_value"], 8.5)
        for path in (["products"], ["products", 0], ["products", 3, "price"], ["not_present"]):
            with self.assertRaises(IdentificationError):
                window.probe(0, path)
        window.close()
        self.assertEqual(window.payloads, {})
        self.assertEqual(window.expected_store, "")
        self.assertFalse(window.active())
        with self.assertRaises(IdentificationError):
            window.start_once()

    def test_nonmatching_body_has_no_public_probe_or_retained_payload(self):
        window, _, route = active_window()
        feed_json(window, route, {"name": "Other synthetic shop", "price": 9})
        self.assertEqual(window.target_matches, 0)
        self.assertEqual(window.payloads, {})
        with self.assertRaises(IdentificationError):
            window.probe(0, ["price"])

    def test_wait_timeout_late_chunks_and_clock_reversal_clear_data(self):
        window, clock, route = active_window()
        collector = window.begin_response(route, "identity")
        collector.feed(b'{"name":')
        clock.value = 130.0
        self.assertEqual(window.diagnostic()["code"], "P26_WINDOW_TIMEOUT")
        self.assertEqual(collector.buffer, bytearray())
        self.assertEqual(collector.feed(b"late"), b"late")
        self.assertEqual(window.observations, [])
        window, clock, _ = active_window()
        clock.value = 9.0
        self.assertFalse(window.active())
        self.assertEqual(window.code, "P26_CLOCK_INVALID")

    def test_compression_bomb_and_encoded_budget_are_bounded(self):
        window, _, route = active_window()
        collector = window.begin_response(route, "gzip")
        blob = zlib.compressobj(wbits=31)
        compressed = blob.compress(b"x" * (MAX_BODY + 1)) + blob.flush()
        collector.feed(compressed)
        self.assertEqual(window.code, "P26_RESPONSE_SIZE_LIMIT")
        self.assertEqual(collector.buffer, bytearray())
        window, _, route = active_window()
        collector = window.begin_response(route, "identity")
        collector.feed(b"x" * (MAX_BODY + 1))
        self.assertEqual(window.code, "P26_RESPONSE_SIZE_LIMIT")
        window, _, route = active_window()
        window.encoded_bytes = MAX_TOTAL
        window.begin_response(route, "identity").feed(b"x")
        self.assertEqual(window.code, "P26_TOTAL_SIZE_LIMIT")

    def test_valid_gzip_duplicate_keys_encoding_and_callback_budgets(self):
        window, _, route = active_window()
        blob = zlib.compressobj(wbits=31)
        content = blob.compress(b'{"name":"Synthetic shop"}') + blob.flush()
        collector = window.begin_response(route, "gzip")
        for byte in content:
            collector.feed(bytes([byte]))
        collector.feed(b"")
        self.assertEqual(window.target_matches, 1)
        window, _, route = active_window()
        collector = window.begin_response(route, "identity")
        collector.feed(b'{"name":"Synthetic shop","name":"other"}')
        collector.feed(b"")
        self.assertEqual(window.code, "P26_STRUCTURE_INVALID")
        window, _, route = active_window()
        self.assertIsNone(window.begin_response(route, "br"))
        self.assertEqual(window.code, "P26_ENCODING_UNSUPPORTED")
        window, _, _ = active_window()
        for _ in range(65):
            window.begin_response(None, "identity")
        self.assertEqual(window.raw_callbacks, 64)
        self.assertEqual(window.response_reads, 0)
        self.assertEqual(window.code, "P26_CALLBACK_BUDGET")

    def test_dynamic_dictionary_keys_are_not_shape_values(self):
        window, _, route = active_window()
        feed_json(window, route, {"name": "Synthetic shop", "map": {"0123456789": 8}})
        serialized = json.dumps(window.observations)
        self.assertNotIn("0123456789", serialized)
        self.assertIn("<dynamic>", serialized)

    def test_receipt_schema_rejects_free_codes_and_unbounded_counts(self):
        import jsonschema
        schema = json.loads((Path(__file__).resolve().parents[2] / "contracts/schemas/p26-identification-diagnostic-v1.schema.json").read_text())
        window, _, _ = active_window()
        jsonschema.validate(window.diagnostic(), schema)
        window.close("synthetic-private-error-text")
        receipt = window.diagnostic()
        self.assertEqual(receipt["code"], "P26_IDENTIFICATION_EXCEPTION")
        jsonschema.validate(receipt, schema)
        for changed in ({"raw_callbacks": 65}, {"code": "free error"}, {"unknown": True}):
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate({**receipt, **changed}, schema)


class RequestMetadataTests(unittest.TestCase):
    def test_form_names_and_verified_public_store_id_never_decode_private_values(self):
        from collection_adapter.p26_request_metadata import RequestBudget,begin_form_metadata,inspect_current_store_parameter
        from urllib.parse import unquote_to_bytes
        window,_,route=active_window();layouts=[];budget=RequestBudget(window)
        collector=begin_form_metadata(window,budget,'request:synthetic',route,layouts)
        collector.feed(b'wm_poi_id=123&cookie=PRIVATE_VALUE&ui=UNSELECTED_VALUE');collector.feed(b'')
        self.assertEqual(layouts[0]['keys'],['wm_poi_id','cookie','ui'])
        self.assertNotIn('PRIVATE_VALUE',json.dumps(layouts))
        window.projected_observations=[{'values':[
            {'path':'$.data.poi_base_info.name','value':'Synthetic shop'},
            {'path':'$.data.poi_base_info.id','value':123}], 'expires_at':70}]
        def permitted_decode(value):
            self.assertNotIn(b'PRIVATE_VALUE',value);self.assertNotIn(b'UNSELECTED_VALUE',value)
            return unquote_to_bytes(value)
        with patch('collection_adapter.p26_request_metadata.unquote_to_bytes',side_effect=permitted_decode):
            result=inspect_current_store_parameter(window,'request:synthetic','wm_poi_id')
        self.assertTrue(result['matches_current_public_store_id'])
        self.assertNotIn('123',json.dumps(result))
        self.assertEqual(window.response_reads,0);self.assertEqual(window.encoded_bytes,0)
        for name in ('cookie','ui','not_observed'):
            with self.assertRaises(IdentificationError):inspect_current_store_parameter(window,'request:synthetic',name)
        window.close();self.assertEqual(window.request_leases,{})

    def test_request_metadata_byte_and_stalled_buffer_limits_and_lease_expiry(self):
        from collection_adapter.p26_request_metadata import RequestBudget,begin_form_metadata,inspect_current_store_parameter
        window,clock,route=active_window();window.deadline=None;window.duration_seconds=None
        collector=begin_form_metadata(window,RequestBudget(window),'request:synthetic',route,[])
        collector.feed(b'wm_poi_id=123');collector.feed(b'')
        self.assertTrue(window.request_leases)
        clock.value+=60;self.assertTrue(window.active());self.assertEqual(window.request_leases,{})
        collector=begin_form_metadata(window,RequestBudget(window),'request:other',route,[])
        collector.feed(b'wm_poi_id=');clock.value+=60
        self.assertFalse(window.active());self.assertEqual(collector.buffer,bytearray())
        window,_,route=active_window()
        collector=begin_form_metadata(window,RequestBudget(window),'request:large',route,[])
        collector.feed(b'x'*(MAX_BODY+1))
        self.assertEqual(window.code,'P26_RESPONSE_SIZE_LIMIT');self.assertEqual(collector.buffer,bytearray())

    def test_form_duplicate_and_unconfirmed_store_parameter_fail_without_exposure(self):
        from collection_adapter.p26_request_metadata import RequestBudget,begin_form_metadata,inspect_current_store_parameter
        window,_,route=active_window();layouts=[]
        collector=begin_form_metadata(window,RequestBudget(window),'request:synthetic',route,layouts)
        collector.feed(b'wm_poi_id=123&wm_poi_id=456');collector.feed(b'')
        self.assertEqual(window.code,'P26_STRUCTURE_INVALID');self.assertEqual(layouts,[])
        window,_,route=active_window()
        collector=begin_form_metadata(window,RequestBudget(window),'request:synthetic',route,[])
        collector.feed(b'wm_poi_id=123');collector.feed(b'')
        window.projected_observations=[{'values':[{'path':'$.data.poi_base_info.name','value':'Other shop'},
                                               {'path':'$.data.poi_base_info.id','value':123}],'expires_at':70}]
        with self.assertRaises(IdentificationError):inspect_current_store_parameter(window,'request:synthetic','wm_poi_id')


class HostPreparationTests(unittest.TestCase):
    def test_sensitive_key_inspection_requires_current_user_permission_and_exact_binding(self):
        state={"runtime_target_ref":"target:synthetic","target_binding_ref":"binding:synthetic",
               "target_confirmation_ref":"confirmation:synthetic"}
        scope={"user_decision":"CURRENT_USER_ALLOWED_SENSITIVE_FIELD_INSPECTION",
               "inspection":"KEY_PATH_TYPE_ONLY","field_values_processed":False,"raw_persistence":False,**state}
        self.assertTrue(host._sensitive_key_layout_approved({**state,"sensitive_field_inspection":scope}))
        for change in ({"field_values_processed":True},{"raw_persistence":True},{"inspection":"WHOLE_BODY"},
                       {"target_confirmation_ref":"different"},{"user_decision":"NOT_APPROVED"}):
            with self.assertRaises(IdentificationError):
                host._sensitive_key_layout_approved({**state,"sensitive_field_inspection":{**scope,**change}})
        with self.assertRaises(IdentificationError):host._sensitive_key_layout_approved(state)
    def test_key_layout_mode_only_selects_observed_current_shop_routes(self):
        from types import SimpleNamespace
        window=IdentificationWindow("Synthetic shop",clock=Clock(),duration_seconds=None)
        window.key_layout_only=True
        window.inspect_current_domain("wx.waimai.meituan.com")
        window.inspect_current_domain("other.meituan.com")
        window.inspect_current_domain("hcapi-wx.waimai.meituan.com")
        window.inspect_current_domain("apimobile.meituan.com")
        window.inspect_current_domain("web.meituan.com")
        window.start_once(); window.domain("wx.waimai.meituan.com"); window.domain("other.meituan.com")
        addon=host.IdentificationAddon(window,batch_public_json=True, detached_analysis=False)
        class Response:
            stream=False
            @property
            def headers(self): raise AssertionError("outside selected route headers read")
            @property
            def raw_content(self): raise AssertionError("framework raw read")
        for method, origin, path, selected in (
            ("POST","wx.waimai.meituan.com","/v1/weapp/shop/v2/poi/productlist",True),
            ("POST","wx.waimai.meituan.com","/v1/weapp/v1/poi/food",True),
            ("POST","hcapi-wx.waimai.meituan.com","/weapp/v1/poi/food",True),
            ("POST","apimobile.meituan.com","/weapp/shop/v1/poi/productlist",True),
            ("GET","wx.waimai.meituan.com","/v1/weapp/v1/poi/food",False),
            ("POST","other.meituan.com","/v1/weapp/v1/poi/food",False),
            ("POST","web.meituan.com","/weapp/v1/poi/food_detail",False),
            ("POST","wx.waimai.meituan.com","/v1/weapp/v1/poi/food_detail",False),
            ("POST","wx.waimai.meituan.com","/v1/weapp/home/feed",False)):
            route=window.route(method,origin,path)
            self.assertEqual(addon._business_candidate(route),selected)
            if not selected:
                # A manual route command cannot bypass the narrow diagnostic.
                window.select_route(route)
                addon.route_slots["synthetic-flow"]=route
                flow=SimpleNamespace(id="synthetic-flow",response=Response())
                addon.responseheaders(flow)
                self.assertTrue(flow.response.stream)
        self.assertEqual(window.response_reads,0)

    def test_batch_public_json_automatically_collects_candidate_body_with_privacy_before_identity(self):
        from types import SimpleNamespace
        for payload, expected in (({"name":"Synthetic shop","price":8},"P26_TARGET_SHAPE_OBSERVED"),
                                  ({"name":"Synthetic shop","nested":{"cookie":"private"}},"P26_SENSITIVE_INPUT"),
                                  ({"name":"Synthetic shop","nested":{"ｃｏｏｋｉｅ":"private"}},"P26_SENSITIVE_INPUT"),
                                  ({"name":"Synthetic shop","user":{"name":"private"}},"P26_SENSITIVE_INPUT")):
            window=IdentificationWindow("Synthetic shop",clock=Clock(),duration_seconds=None)
            window.inspect_current_domain("example.invalid");window.start_once();window.domain("example.invalid")
            route=window.route("GET","example.invalid","/public/catalog")
            addon=host.IdentificationAddon(window,batch_public_json=True, detached_analysis=False)
            addon.route_slots["synthetic-flow"]=route
            class Response:
                status_code=200
                headers={"content-type":"application/json; charset=utf-8","content-encoding":"identity"}
                stream=True
                @property
                def raw_content(self): raise AssertionError("framework raw read")
            flow=SimpleNamespace(id="synthetic-flow",response=Response())
            addon.responseheaders(flow)
            self.assertTrue(callable(flow.response.stream))
            flow.response.stream(json.dumps(payload).encode());flow.response.stream(b"")
            self.assertEqual(window.code,expected)
            if expected=="P26_SENSITIVE_INPUT":
                self.assertEqual(window.field_catalog,{})
                self.assertEqual(window.observations,[])
                self.assertEqual(window.target_matches,0)
            else:
                self.assertEqual(window.target_matches,1)
                self.assertEqual(window.observations[0]["amount_unit"],"UNKNOWN")
            window.close()

    def test_batch_skips_private_and_observed_unneeded_routes_before_body_or_headers(self):
        from types import SimpleNamespace
        window=IdentificationWindow("Synthetic shop",clock=Clock(),duration_seconds=None)
        window.inspect_current_domain("example.invalid");window.start_once();window.domain("example.invalid")
        addon=host.IdentificationAddon(window,batch_public_json=True, detached_analysis=False)
        class Response:
            stream=False
            @property
            def headers(self): raise AssertionError("unneeded headers read")
            @property
            def raw_content(self): raise AssertionError("unneeded raw read")
        for path in ("/weapp/user/allowance/entry","/api/orders/list","/abtest/frontend","/home/feeds/listwindows"):
            route=window.route("POST","example.invalid",path)
            addon.route_slots["synthetic-flow"]=route
            flow=SimpleNamespace(id="synthetic-flow",response=Response())
            addon.responseheaders(flow)
            self.assertTrue(flow.response.stream)
        self.assertEqual(window.response_reads,0)
        self.assertEqual(window.payloads,{})

    def test_public_batch_mode_requires_matching_current_explicit_authorization(self):
        state={"runtime_target_ref":"target:synthetic","target_binding_ref":"binding:synthetic",
               "target_confirmation_ref":"confirmation:synthetic"}
        scope={"schema_version":"p26-public-business-batch-authorization/v1",
               "user_decision":"CURRENT_USER_REQUESTED_BATCH_PUBLIC_BUSINESS_INPUT",
               "private_inputs":"EXCLUDED","raw_persistence":False,"results_target":"CURRENT_CONFIRMED_STORE",**state}
        with patch.object(host,"_monitoring_approved",return_value=True):
            self.assertTrue(host._public_batch_approved({**state,"public_business_batch":scope}))
            for changes in ({"private_inputs":"INCLUDED"},{"raw_persistence":True},
                            {"target_confirmation_ref":"different"},{"user_decision":"NOT_APPROVED"}):
                with self.assertRaises(IdentificationError):
                    host._public_batch_approved({**state,"public_business_batch":{**scope,**changes}})
            with self.assertRaises(IdentificationError): host._public_batch_approved(state)

    def test_monitoring_connection_budget_handles_observed_thirty_three_connection_burst(self):
        window=IdentificationWindow("Synthetic shop",duration_seconds=None); window.start_once()
        addon=host.IdentificationAddon(window, detached_analysis=False)
        for _ in range(host.CONTINUOUS_STREAM_LIMIT): addon.client_connected(object())
        self.assertTrue(window.active())
        addon.client_disconnected(object())
        addon.client_connected(object())
        self.assertTrue(window.active())
        addon.client_connected(object())
        self.assertTrue(window.active())
        self.assertEqual(addon.connections, host.CONTINUOUS_STREAM_LIMIT)
        classic=IdentificationWindow("Synthetic shop"); classic.start_once()
        addon=host.IdentificationAddon(classic, detached_analysis=False)
        for _ in range(33): addon.client_connected(object())
        self.assertEqual(classic.code,"P26_CONNECTION_BUDGET")

    def test_helper_replacement_requires_one_exact_parent_uid_path_and_socket_owner(self):
        from subprocess import CompletedProcess
        executable = "/Applications/WeChat.app/Contents/MacOS/WeChatAppEx.app/synthetic-helper"
        for fields, parent, sockets_ok, accepted in (
                (["100", str(host.os.getuid()), executable], 100, True, True),
                (["101", str(host.os.getuid()), executable], 100, True, False),
                (["100", str(host.os.getuid()+1), executable], 100, True, False),
                (["100", str(host.os.getuid()), executable+"-other"], 100, True, False),
                (["100", str(host.os.getuid()), executable], 101, True, False),
                (["100", str(host.os.getuid()), executable], 100, False, False)):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); root.chmod(0o700)
                binding = {"applet_pid": 100, "network_pid": 123}
                host._write_new(root, "current-network-process-binding.json", binding)
                scope = {"applet_parent_pid": 100, "original_network_pid": 123,
                         "executable": executable, "replacement_observed": False}
                guard = host.NetworkHelperReplacement(root, scope)
                failure = None if sockets_ok else IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")
                with patch.object(host, "_helper_pid", return_value=parent), \
                        patch.object(host.subprocess, "run", return_value=CompletedProcess([], 0, " ".join(fields), "")), \
                        patch.object(host, "_verify_network_owner_pid", side_effect=failure) as verify, \
                        contextlib.redirect_stdout(io.StringIO()):
                    if accepted:
                        guard.accept(456)
                        verify.assert_called_once_with(100, 456)
                        self.assertEqual(host._read_owned(root/"current-network-process-binding.json")["network_pid"], 456)
                        self.assertTrue(scope["replacement_observed"])
                        with self.assertRaises(IdentificationError):
                            guard.accept(789)
                    else:
                        with self.assertRaises(IdentificationError):
                            guard.accept(456)
                        self.assertEqual(host._read_owned(root/"current-network-process-binding.json"), binding)
                        self.assertFalse(scope["replacement_observed"])

    def test_helper_restart_scope_never_activates_without_specific_matching_authorization(self):
        from subprocess import CompletedProcess
        state = {"runtime_target_ref":"target:synthetic", "target_binding_ref":"binding:synthetic",
                 "target_confirmation_ref":"confirmation:synthetic"}
        executable = "/Applications/WeChat.app/Contents/MacOS/WeChatAppEx.app/synthetic-helper"
        scope = {"schema_version":"p26-network-helper-restart/v1",
                 "user_decision":"CURRENT_USER_APPROVED_ONE_BOUND_HELPER_RESTART",
                 "restart_ref":"helper-restart:"+"a"*32, "replacement_observed":False,
                 "applet_parent_pid":100,"original_network_pid":123,"executable":executable,**state}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); root.chmod(0o700)
            host._write_new(root,"current-network-process-binding.json",{"applet_pid":100,"network_pid":123})
            self.assertIsNone(host._helper_restart_scope(state,root,123))
            with patch.object(host,"_monitoring_approved",return_value=True), \
                    patch.object(host.subprocess,"run",return_value=CompletedProcess([],0,f"100 {host.os.getuid()} {executable}","")):
                self.assertEqual(host._helper_restart_scope({**state,"network_helper_restart":scope},root,123),scope)
                for changed in ({"user_decision":"NOT_APPROVED"}, {"target_confirmation_ref":"different"},
                                {"applet_parent_pid":101},{"original_network_pid":124},
                                {"executable":executable+",other"}):
                    with self.assertRaises(IdentificationError):
                        host._helper_restart_scope({**state,"network_helper_restart":{**scope,**changed}},root,123)

    def test_inactive_spec_is_nonempty_and_excludes_every_synthetic_pid(self):
        spec = host._inactive_spec(123)
        self.assertEqual(spec.split(","), ["123", "!123"])
        # Independently evaluate the documented include/exclude semantics.
        for pid in (1, 123, 124, 9999):
            intercepted = False
            for action in spec.split(","):
                if action.startswith("!"):
                    intercepted = intercepted and pid != int(action[1:])
                else:
                    intercepted = intercepted or pid == int(action)
            self.assertFalse(intercepted)
        for pid in (0, -1, "123", True):
            with self.assertRaises(IdentificationError):
                host._inactive_spec(pid)

    def test_continuous_monitoring_requires_fresh_current_scope_attestation(self):
        state = {"runtime_target_ref": "target:synthetic", "target_binding_ref": "binding:synthetic",
                 "target_confirmation_ref": "confirmation:synthetic"}
        self.assertFalse(host._monitoring_approved(state))
        scope = {"schema_version": "p26-monitoring-authorization/v1",
                 "scope_ref": "monitoring:" + "a" * 32,
                 "user_decision": "CURRENT_USER_NO_TIME_OR_ATTEMPT_LIMIT",
                 "time_limit_seconds": None, "attempt_limit": None, **state}
        self.assertTrue(host._monitoring_approved({**state, "monitoring_authorization": scope}))
        for changed in ({"time_limit_seconds": 120}, {"target_confirmation_ref": "confirmation:other"}):
            with self.assertRaisesRegex(IdentificationError, "P26_MONITORING_SCOPE_INVALID"):
                host._monitoring_approved({**state, "monitoring_authorization": {**scope, **changed}})

    def test_used_window_precheck_preserves_actual_attempt_and_never_reopens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            root.chmod(0o700)
            state = {
                "schema_version": "p26-transport-state/v1", "output_root": str(root),
                "user_decision": "CONFIRMED_CURRENT_SESSION", "capabilities": list(REQUIRED_CAPABILITIES),
                "ca_trust": "USER_ATTESTED_SSL_TRUST", "page_isolation": "USER_ATTESTED_SINGLE_TARGET_APPLET",
                "identification_attempts": 1, "result_attempts": 0,
                "live_capture_latch": "CLOSED", "execution_latch": "CLOSED",
            }
            host._write_new(root, "transport-state.json", state)
            host._write_new(root, "current-business-choice.json", {})
            host._write_new(root, "identification-attempt.lock", {"synthetic": True})
            before = set(root.iterdir())
            with patch.object(host, "_git_ignored_root", return_value=True), \
                    patch.object(host, "_helper_pid", side_effect=AssertionError("used quota must stop first")):
                with self.assertRaisesRegex(IdentificationError, "P26_WINDOW_ALREADY_USED"):
                    host.prepare(root)
            self.assertEqual(set(root.iterdir()), before)

    def test_network_owner_precheck_does_not_replace_root_pid_with_a_child(self):
        from subprocess import CompletedProcess
        replies = [
            CompletedProcess([], 0, "124\n", ""),
            CompletedProcess([], 0, "p124\nf5\nPTCP\n", ""),
        ]
        with patch.object(host.subprocess, "run", side_effect=replies) as run:
            with self.assertRaisesRegex(IdentificationError, "P26_NETWORK_OWNER_UNCONFIRMED"):
                host._verify_network_owner_pid(123)
        args = run.call_args_list[1].args[0]
        self.assertEqual(args, ["lsof", "-nP", "-a", "-p", "123,124", "-i", "-F", "pP"])
        self.assertNotIn("n", args[-1])

    def test_network_owner_precheck_requires_positive_exact_pid_socket_evidence(self):
        from subprocess import CompletedProcess
        for sockets, accepted in (("p123\nf5\nPTCP\n", True), ("", False),
                                  ("p123\nf5\nPTCP\np124\nf6\nPUDP\n", False)):
            replies = [CompletedProcess([], 0, "124\n", ""),
                       CompletedProcess([], 0 if sockets else 1, sockets, "")]
            with patch.object(host.subprocess, "run", side_effect=replies):
                if accepted:
                    host._verify_network_owner_pid(123)
                else:
                    with self.assertRaisesRegex(IdentificationError, "P26_NETWORK_OWNER_UNCONFIRMED"):
                        host._verify_network_owner_pid(123)

    def test_real_host_preparation_only_reads_owned_setup_no_transport_or_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            root.chmod(0o700)
            ca = root / "p26_transport_synthetic"
            ca.mkdir(mode=0o700)
            for name in _FILES:
                (ca / name).write_text("synthetic certificate bytes")
                (ca / name).chmod(0o600)
            info = ca.stat()
            state = {
                "schema_version": "p26-transport-state/v1", "output_root": str(root),
                "user_decision": "CONFIRMED_CURRENT_SESSION", "capabilities": list(REQUIRED_CAPABILITIES),
                "ca_trust": "USER_ATTESTED_SSL_TRUST", "page_isolation": "USER_ATTESTED_SINGLE_TARGET_APPLET",
                "identification_attempts": 0, "result_attempts": 0,
                "live_capture_latch": "CLOSED", "execution_latch": "CLOSED",
                "runtime_target_ref": "target:synthetic_current_01", "target_binding_ref": "target-binding:synthetic_current_01",
                "target_confirmation_ref": "target-confirmation:synthetic_current_01",
                "ca_directory": str(ca), "ca_directory_identity": [info.st_dev, info.st_ino],
            }
            choice = {"schema_version": "p26-current-business-choice/v1", "source": "CURRENT_USER_CONFIRMATION",
                      "store": "Synthetic shop"}
            host._write_new(root, "transport-state.json", state)
            host._write_new(root, "current-business-choice.json", choice)
            before = set(root.iterdir())
            with patch.object(host, "_git_ignored_root", return_value=True), patch.object(host, "_helper_pid", return_value=123):
                self.assertEqual(host.prepare(root)[2], 123)
                self.assertEqual(set(root.iterdir()), before)
                host._write_new(root, "identification-attempt.lock", {"synthetic": True})
                with self.assertRaisesRegex(IdentificationError, "P26_WINDOW_ALREADY_USED"):
                    host.prepare(root)
            with self.assertRaises(FileExistsError):
                host._write_new(root, "transport-state.json", {})

    def test_unselected_response_does_not_touch_body_encoding_cookies_or_header_map(self):
        window, _, _ = active_window()
        addon = host.IdentificationAddon(window, detached_analysis=False)
        class Response:
            stream = False
            @property
            def headers(self):
                raise AssertionError("unselected headers read")
            @property
            def raw_content(self):
                raise AssertionError("raw body read")
        class Flow:
            id = "synthetic-flow"
            response = Response()
        addon.responseheaders(Flow())
        self.assertTrue(Flow.response.stream)
        self.assertEqual(window.raw_callbacks, 1)
        self.assertEqual(window.response_reads, 0)

    def test_argument_errors_do_not_echo_supplied_values(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(host.main(["--unknown", "synthetic-private-argument"]), 2)
        self.assertNotIn("synthetic-private", output.getvalue())

    def test_missing_system_component_never_starts_receiver_or_consumes_attempt(self):
        with patch.object(host, "prepare", return_value=({}, {}, 123)), patch.object(host, "_redirector_present", return_value=False):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = asyncio.run(host.serve(Path("/synthetic")))
        self.assertEqual(result["code"], "P29_COPY_SOURCE_UNAVAILABLE")
        self.assertEqual(result["new_attempts"], 0)
        self.assertEqual(result["live_capture_latch"], "CLOSED")


class PIDGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_diagnostic_output_recovers_real_nonblocking_pipe_backpressure_without_duplicate_json(self):
        reader,writer=os.pipe()
        os.set_blocking(reader,False);os.set_blocking(writer,False)
        loop=asyncio.get_running_loop()
        output=host.EventOutput(loop,writer,lambda:self.fail("temporary backpressure is not failure"))
        try:
            while True:
                try: os.write(writer,b"x"*4096)
                except BlockingIOError: break
            documents=[{"event":"SYNTHETIC_FIRST","count":1},{"event":"SYNTHETIC_SECOND","count":2}]
            for document in documents: output.send(document)
            self.assertTrue(output.pending)
            self.assertFalse(output.failed)
            # Discard only the synthetic filler, then let the ordered writer
            # resume on writability and verify its exact JSON line boundaries.
            while True:
                try: os.read(reader,65536)
                except BlockingIOError: break
            self.assertTrue(await output.finish(timeout=1))
            data=os.read(reader,65536).decode("ascii")
            self.assertEqual([json.loads(line) for line in data.splitlines()],documents)
            self.assertFalse(output.pending)
        finally:
            output._unwatch();os.close(reader);os.close(writer)

    async def test_diagnostic_broken_output_closes_input_with_fixed_code_and_no_error_text(self):
        reader,writer=os.pipe();os.set_blocking(writer,False);os.close(reader)
        window=IdentificationWindow("Synthetic shop",duration_seconds=None);window.start_once()
        output=host.EventOutput(asyncio.get_running_loop(),writer,
                                lambda:window.close("P26_DIAGNOSTIC_OUTPUT_FAILED"))
        try:
            output.send({"event":"SYNTHETIC_STATUS","count":0})
            self.assertFalse(await output.finish(timeout=1))
            self.assertEqual(window.code,"P26_DIAGNOSTIC_OUTPUT_FAILED")
            self.assertEqual(window.state,"CLOSED")
            self.assertEqual(output.pending,bytearray())
            self.assertEqual(window.payloads,{})
        finally:
            output._unwatch();os.close(writer)

    async def test_approved_helper_replacement_is_verified_before_dispatch(self):
        seen=[]
        class Guard:
            def accept(self,pid):
                seen.append("verify")
                if pid != 456:
                    raise IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")
        class Stream:
            closed=False
            def get_extra_info(self,key,default): return 456
            def close(self): self.closed=True
        async def dispatch(stream): seen.append("dispatch")
        window=IdentificationWindow("Synthetic shop",duration_seconds=None); window.start_once()
        gate=host.PIDStreamGate(window,123,dispatch,Guard())
        await gate(Stream())
        self.assertEqual(seen,["verify","dispatch"])
        self.assertEqual(gate.pid,456)

    async def test_continuous_monitoring_limits_concurrency_not_total_streams(self):
        async def dispatch(stream):
            return
        class Stream:
            def get_extra_info(self, key, default):
                return 123
            def close(self):
                raise AssertionError("sequential current stream unexpectedly closed")
        window = IdentificationWindow("Synthetic shop", duration_seconds=None)
        window.start_once()
        gate = host.PIDStreamGate(window, 123, dispatch)
        for _ in range(100):
            await gate(Stream())
        self.assertTrue(window.active())
        self.assertEqual(gate.concurrent, 0)
        self.assertEqual(gate.accepted, 64)
        self.assertTrue(gate.accepted_at_least)

    async def test_continuous_burst_above_the_old_cap_is_accepted(self):
        started = []
        release = asyncio.Event()

        async def dispatch(_stream):
            started.append(True)
            await release.wait()

        class Stream:
            def __init__(self):
                self.closed = False

            def get_extra_info(self, key, default):
                return 123

            def close(self):
                self.closed = True

        self.assertEqual(host.CONTINUOUS_STREAM_LIMIT, 256)
        window = IdentificationWindow("Synthetic shop", duration_seconds=None)
        window.start_once()
        gate = host.PIDStreamGate(window, 123, dispatch)
        tasks = [asyncio.create_task(gate(Stream())) for _ in range(80)]
        for _ in range(50):
            if len(started) == 80:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(len(started), 80)
        self.assertTrue(window.active())
        self.assertEqual(gate.concurrent, 80)
        self.assertNotEqual(window.code, "P26_STREAM_COUNT_LIMIT")
        release.set()
        await asyncio.gather(*tasks)
        self.assertTrue(window.active())

    async def test_receiver_loss_closes_without_inventing_or_resetting_an_attempt(self):
        class Server:
            async def wait_closed(self):
                return
        for started in (False, True):
            window = IdentificationWindow("Synthetic shop", duration_seconds=None)
            if started:
                window.start_once()
            await host._observe_receiver_close(Server(), window)
            self.assertEqual(window.code, "P26_RECEIVER_LOST")
            self.assertEqual(window.attempts, int(started))
            self.assertEqual(window.diagnostic()["raw_callbacks"], 0)
            self.assertEqual(window.diagnostic()["live_capture_latch"], "CLOSED")

    async def test_kernel_pid_checked_before_dispatch_or_bytes(self):
        seen = []
        async def dispatch(stream):
            seen.append(True)
        class Stream:
            closed = False
            pid = 123
            def get_extra_info(self, key, default):
                self.asserted_key = key
                if key != "pid":
                    raise AssertionError("unneeded process metadata")
                return self.pid
            def close(self):
                self.closed = True
            def read(self):
                raise AssertionError("stream bytes read before isolation")
        window = IdentificationWindow("Synthetic shop")
        gate = host.PIDStreamGate(window, 123, dispatch)
        stream = Stream()
        await gate(stream)
        self.assertTrue(stream.closed)
        self.assertEqual(window.attempts, 0)
        self.assertEqual(seen, [])
        window.start_once()
        stream = Stream()
        await gate(stream)
        self.assertEqual(gate.accepted, 1)
        self.assertEqual(seen, [True])
        for pid in (None, 456):
            window = IdentificationWindow("Synthetic shop")
            window.start_once()
            gate = host.PIDStreamGate(window, 123, dispatch)
            stream = Stream()
            stream.pid = pid
            await gate(stream)
            self.assertEqual(window.code, "P26_STREAM_PID_UNCONFIRMED")
            self.assertTrue(stream.closed)
            self.assertEqual(gate.accepted, 0)


if __name__ == "__main__":
    unittest.main()
