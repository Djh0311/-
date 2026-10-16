"""P26 current-target regression; all inputs are synthetic, with no transport."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from collection_adapter import CollectionTarget
from collection_adapter.live_p0_entry import (
    CurrentTargetBinding, HistoricalTargetBinding, LiveP0EntryError,
    bind_current_request, HISTORICAL_TARGET_REF,
)
from collection_adapter.live_prepare import prepare_current_live_entry
from collection_adapter.mitmproxy_bridge import MitmproxySourceEntry, P21OutputBoundary, MitmproxyBridgeError
from collection_adapter.tests.test_live_prepare import _root, _spec, _ExplosiveFlow


class CurrentTargetBindingTests(unittest.TestCase):
    def _binding(self, spec):
        return CurrentTargetBinding(spec.runtime_target, spec.target_binding_ref,
                                    "target-confirmation:p26_synthetic_01")

    def test_current_factory_never_constructs_a_historical_binding_and_stays_zero_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = _spec(_root(directory))
            binding = self._binding(spec)
            with patch("collection_adapter.mitmproxy_bridge.HistoricalTargetBinding", side_effect=AssertionError):
                entry = MitmproxySourceEntry(
                    policy=spec.policy, runtime_target=spec.runtime_target,
                    target_binding_ref=spec.target_binding_ref, source_entry_ref=spec.source_entry_ref,
                    output_boundary=P21OutputBoundary(spec.output_root_ref), current_target_binding=binding,
                )
                receipt = entry.binding_receipt()
                schema = json.loads(Path("contracts/schemas/mitmproxy-source-entry-binding-v2.schema.json").read_text())
                Draft202012Validator(schema).validate(receipt)
                self.assertNotIn(HISTORICAL_TARGET_REF, json.dumps(receipt))
                self.assertNotIn("historical_target_ref", receipt)
                self.assertEqual(receipt["source_identity_status"], "NOT_OBSERVED")
                self.assertEqual(receipt["source_attempts_consumed"], 0)
                attempt = entry.create_p21_attempt(**spec.request_references)
                self.assertIs(attempt.target_binding, binding)
                self.assertEqual(attempt.authority.snapshot()["source_attempts_consumed"], 0)
                self.assertEqual(attempt.authority.snapshot()["live_capture_latch"], "CLOSED")
                self.assertEqual(bind_current_request(attempt.request, binding)["source_identity_status"], "NOT_OBSERVED")
                with self.assertRaisesRegex(MitmproxyBridgeError, "^MITMPROXY_BRIDGE_FACTORY_USED$"):
                    entry.create_p21_attempt(**spec.request_references)

    def test_current_prepare_missing_confirmation_cannot_fall_back_to_legacy_or_be_reprepared(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = _spec(_root(directory))
            session = prepare_current_live_entry(spec)
            session.prepare()
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic["closure_code"], "LIVE_CURRENT_TARGET_BINDING_INVALID")
            self.assertEqual(diagnostic["source_attempts_consumed"], 0)
            self.assertFalse(session.start())
            self.assertEqual(session.accept_callback(_ExplosiveFlow()), "MITMPROXY_BRIDGE_NOT_WAITING")
            Draft202012Validator(json.loads(Path("contracts/schemas/live-entry-diagnostic-v1.schema.json").read_text())).validate(diagnostic)

    def test_current_prepare_is_not_source_confirmation_and_never_calls_the_clock_or_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            spec = _spec(root)
            spec = replace(spec, current_target_binding=self._binding(spec), now=lambda: self.fail("no clock before start"))
            with patch("collection_adapter.mitmproxy_bridge.HistoricalTargetBinding", side_effect=AssertionError):
                session = prepare_current_live_entry(spec)
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic["program_preparation"], "COMPLETE")
            self.assertEqual(diagnostic["real_source_ready"], "UNKNOWN")
            self.assertEqual(diagnostic["receiver_ready"], "NO")
            self.assertEqual(diagnostic["source_attempts_consumed"], 0)
            self.assertEqual(session.accept_callback(_ExplosiveFlow()), "MITMPROXY_BRIDGE_NOT_WAITING")
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_target_drift_or_historical_confirmation_is_rejected_without_an_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = _spec(_root(directory))
            drift = CurrentTargetBinding(CollectionTarget("target:p26_drift_01"), spec.target_binding_ref,
                                         "target-confirmation:p26_synthetic_01")
            for binding in (drift, HistoricalTargetBinding(HISTORICAL_TARGET_REF, spec.runtime_target, spec.target_binding_ref)):
                session = prepare_current_live_entry(replace(spec, current_target_binding=binding))
                self.assertEqual(session.diagnostic()["program_preparation"], "INCOMPLETE")
                self.assertEqual(session.diagnostic()["closure_code"], "LIVE_CURRENT_TARGET_BINDING_INVALID")
                self.assertEqual(session.diagnostic()["source_attempts_consumed"], 0)
                self.assertFalse(session.start())
            with self.assertRaisesRegex(LiveP0EntryError, "^LIVE_CURRENT_TARGET_BINDING_INVALID$"):
                CurrentTargetBinding(spec.runtime_target, spec.target_binding_ref, HISTORICAL_TARGET_REF)


if __name__ == "__main__":
    unittest.main()
