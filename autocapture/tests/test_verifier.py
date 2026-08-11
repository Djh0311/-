"""Fault-injection tests for the production strict verifier."""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


EXPECTED_FILES = frozenset(
    {
        "autocapture/__init__.py",
        "autocapture/addon.py",
        "autocapture/policy.py",
        "autocapture/lease.py",
        "autocapture/shape.py",
        "autocapture/publisher.py",
        "autocapture/build-manifest.json",
        "autocapture/tools/verify_autocapture_build.py",
        "autocapture/tests/__init__.py",
        "autocapture/tests/fakes.py",
        "autocapture/tests/test_addon.py",
        "autocapture/tests/test_policy_and_lease.py",
        "autocapture/tests/test_shape.py",
        "autocapture/tests/test_publisher.py",
        "autocapture/tests/test_verifier.py",
        "docs/design/autocapture-shape-discovery-v1.md",
    }
)
MANIFEST_RELATIVE = "autocapture/build-manifest.json"
MANIFEST_SCHEMA = "autocapture-build-manifest.v1"
PRODUCTION_FILES = (
    "autocapture/addon.py",
    "autocapture/policy.py",
    "autocapture/lease.py",
    "autocapture/shape.py",
    "autocapture/publisher.py",
)


def _generated_canary():
    return "".join(("SYNTHETIC", "_PRIVATE", "_CANARY"))


class StrictVerifierFaultInjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.verifier = cls.repo_root / "autocapture/tools/verify_autocapture_build.py"

    def _copy_candidate(self, destination):
        root = Path(destination)
        for relative in sorted(EXPECTED_FILES):
            source = self.repo_root / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(target))
        return root

    def _run(self, candidate):
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(self.verifier),
                "--repo-root",
                str(candidate),
                "--strict",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env={"PYTHONDONTWRITEBYTECODE": "1"},
            timeout=20,
        )

    def _payload(self, completed):
        combined = (completed.stdout + "\n" + completed.stderr).strip().splitlines()
        self.assertTrue(combined, "verifier produced no machine-readable result")
        try:
            return json.loads(combined[-1])
        except json.JSONDecodeError as exc:
            self.fail("verifier result was not JSON: {0}".format(exc))

    def _assert_passes(self, candidate):
        completed = self._run(candidate)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = self._payload(completed)
        self.assertEqual(payload.get("status"), "AUTOCAPTURE_STRICT_VERIFY_PASS")
        self.assertNotIn(_generated_canary(), completed.stdout + completed.stderr)

    def _assert_fails(self, candidate, reason):
        completed = self._run(candidate)
        self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = self._payload(completed)
        self.assertEqual(payload.get("status"), "AUTOCAPTURE_STRICT_VERIFY_FAIL")
        self.assertEqual(payload.get("reason"), reason)
        self.assertNotIn(_generated_canary(), completed.stdout + completed.stderr)

    def _rewrite_manifest(self, root):
        entries = []
        for relative in sorted(EXPECTED_FILES - {MANIFEST_RELATIVE}):
            payload = (root / relative).read_bytes()
            entries.append(
                {
                    "path": relative,
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        manifest = {
            "schema_version": MANIFEST_SCHEMA,
            "hash_algorithm": "sha256",
            "entries": entries,
        }
        (root / MANIFEST_RELATIVE).write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _mutate_source(self, root, relative, suffix):
        path = root / relative
        path.write_text(path.read_text(encoding="utf-8") + suffix, encoding="utf-8")
        self._rewrite_manifest(root)

    def test_baseline_temp_copy_passes(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-baseline-") as temporary:
            candidate = self._copy_candidate(temporary)
            self._assert_passes(candidate)

    def test_every_required_file_is_required(self):
        for relative in sorted(EXPECTED_FILES):
            with self.subTest(relative=relative):
                with tempfile.TemporaryDirectory(prefix="autocapture-verifier-missing-") as temporary:
                    candidate = self._copy_candidate(temporary)
                    (candidate / relative).unlink()
                    self._assert_fails(candidate, "MISSING_FILE")

    def test_extra_regular_file_and_directory_are_rejected(self):
        cases = (
            ("autocapture/rogue.py", False, "EXTRA_FILE"),
            ("autocapture/rogue-directory", True, "EXTRA_DIRECTORY"),
        )
        for relative, directory, reason in cases:
            with self.subTest(relative=relative):
                with tempfile.TemporaryDirectory(prefix="autocapture-verifier-extra-") as temporary:
                    candidate = self._copy_candidate(temporary)
                    target = candidate / relative
                    if directory:
                        target.mkdir()
                    else:
                        target.write_text("# extra\n", encoding="utf-8")
                    self._assert_fails(candidate, reason)

    def test_cache_and_capture_residue_are_rejected(self):
        cases = (
            ("autocapture/__pycache__", True),
            ("autocapture/cache", True),
            ("autocapture/.cache", True),
            ("autocapture/capture.raw", False),
            ("autocapture/capture.har", False),
            ("autocapture/capture.pcap", False),
            ("autocapture/capture.pcapng", False),
            ("autocapture/capture.dump", False),
            ("autocapture/module.pyc", False),
        )
        for relative, directory in cases:
            with self.subTest(relative=relative):
                with tempfile.TemporaryDirectory(prefix="autocapture-verifier-residue-") as temporary:
                    candidate = self._copy_candidate(temporary)
                    target = candidate / relative
                    if directory:
                        target.mkdir()
                    else:
                        target.write_bytes(b"synthetic-residue")
                    self._assert_fails(candidate, "FORBIDDEN_ARTIFACT")

    def test_symlink_inside_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-link-") as temporary:
            candidate = self._copy_candidate(temporary)
            target = candidate / "autocapture/shape.py"
            target.unlink()
            target.symlink_to("policy.py")
            self._assert_fails(candidate, "SYMLINK_FORBIDDEN")

    def test_symlink_scope_escape_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-escape-") as temporary:
            container = Path(temporary)
            candidate = self._copy_candidate(container / "candidate")
            outside = container / "outside.py"
            outside.write_text("# outside\n", encoding="utf-8")
            target = candidate / "autocapture/shape.py"
            target.unlink()
            target.symlink_to(outside)
            self._assert_fails(candidate, "SCOPE_ESCAPE")

    def test_non_regular_node_is_rejected(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO creation is unavailable")
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-fifo-") as temporary:
            candidate = self._copy_candidate(temporary)
            target = candidate / "autocapture/shape.py"
            target.unlink()
            os.mkfifo(str(target), 0o600)
            self._assert_fails(candidate, "NON_REGULAR_FILE")

    def test_os_open_callsite_escape_is_rejected_after_manifest_rehash(self):
        faults = (
            '\n_FAULT_FD = os.open("/etc/passwd", os.O_RDONLY)\n',
            (
                '        """Publish and return the independently reopened bundle."""'
                '\n\n        _fault_fd = os.open("/etc/passwd", os.O_RDONLY)'
            ),
        )
        for index, fault in enumerate(faults):
            with self.subTest(index=index):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-os-open-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    path = candidate / "autocapture/publisher.py"
                    source = path.read_text(encoding="utf-8")
                    if index == 0:
                        source += fault
                    else:
                        marker = '        """Publish and return the independently reopened bundle."""'
                        self.assertIn(marker, source)
                        source = source.replace(marker, fault, 1)
                    path.write_text(source, encoding="utf-8")
                    self._rewrite_manifest(candidate)
                    self._assert_fails(candidate, "FORBIDDEN_CAPABILITY")

    def test_os_capability_surface_is_closed_after_manifest_rehash(self):
        faults = (
            '\nos.symlink("synthetic-source", "synthetic-target")\n',
            "\n_FAULT_CAPABILITY = os.symlink\n",
        )
        for index, fault in enumerate(faults):
            with self.subTest(index=index):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-os-surface-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    self._mutate_source(
                        candidate,
                        "autocapture/publisher.py",
                        fault,
                    )
                    self._assert_fails(candidate, "FORBIDDEN_CAPABILITY")

    def test_forbidden_import_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-import-") as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(candidate, "autocapture/addon.py", "\nimport socket\n")
            self._assert_fails(candidate, "FORBIDDEN_IMPORT")

    def test_addon_bootstrap_escape_is_rejected_after_manifest_rehash(self):
        faults = ("extra_insert", "origin_bypass")
        for fault in faults:
            with self.subTest(fault=fault):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-bootstrap-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    path = candidate / "autocapture/addon.py"
                    source = path.read_text(encoding="utf-8")
                    if fault == "extra_insert":
                        source += '\nsys.path.insert(0, "/tmp")\n'
                    else:
                        self.assertIn('"policy.py"', source)
                        source = source.replace('"policy.py"', '"other.py"', 1)
                    path.write_text(source, encoding="utf-8")
                    self._rewrite_manifest(candidate)
                    self._assert_fails(candidate, "ADDON_BOOTSTRAP_INVALID")

    def test_dynamic_builtins_import_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-builtins-") as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/addon.py",
                '\n_FAULT_CAPABILITY = __builtins__["__import__"]("socket")\n',
            )
            self._assert_fails(candidate, "FORBIDDEN_CAPABILITY")

    def test_dynamic_os_capability_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-getattr-") as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/publisher.py",
                '\n_FAULT_CAPABILITY = getattr(os, "system")\n',
            )
            self._assert_fails(candidate, "FORBIDDEN_CAPABILITY")

    def test_callable_capability_alias_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(
            prefix="autocapture-verifier-capability-alias-"
        ) as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/publisher.py",
                '\n_fault_capability = os.system\n_fault_capability("synthetic")\n',
            )
            self._assert_fails(candidate, "FORBIDDEN_CAPABILITY")

    def test_dynamic_flow_attribute_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(
            prefix="autocapture-verifier-flow-getattr-"
        ) as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/addon.py",
                (
                    "\ndef _fault_dynamic_flow_attribute(candidate):\n"
                    '    return getattr(candidate, "request").url\n'
                ),
            )
            self._assert_fails(candidate, "FORBIDDEN_CAPABILITY")

    def test_dunder_capability_lookup_is_rejected_after_manifest_rehash(self):
        faults = (
            '\n_FAULT_CAPABILITY = os.__getattribute__("system")\n',
            '\n_FAULT_CAPABILITY = object.__getattribute__(os, "system")\n',
        )
        for fault in faults:
            with self.subTest(fault=fault.strip()):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-dunder-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    self._mutate_source(
                        candidate,
                        "autocapture/publisher.py",
                        fault,
                    )
                    self._assert_fails(candidate, "FORBIDDEN_CAPABILITY")

    def test_forbidden_request_field_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-flow-") as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/addon.py",
                "\ndef _fault_request_read(flow):\n    return flow.request.url\n",
            )
            self._assert_fails(candidate, "FLOW_FIELD_FORBIDDEN")

    def test_renamed_flow_parameter_remains_tainted_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-flow-alias-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/addon.py"
            source = path.read_text(encoding="utf-8")
            signature = "    def _observe_response(self, flow):"
            request_read = "        request = flow.request"
            self.assertIn(signature, source)
            self.assertIn(request_read, source)
            source = source.replace(signature, "    def _observe_response(self, candidate_flow):", 1)
            source = source.replace(
                request_read,
                "        request = candidate_flow.request\n        _fault = request.url",
                1,
            )
            path.write_text(source, encoding="utf-8")
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "FLOW_FIELD_FORBIDDEN")

    def test_flow_default_capture_is_rejected_after_manifest_rehash(self):
        faults = (
            (
                "        def _fault(candidate=request):\n"
                "            return candidate.url\n"
                "        _fault()\n"
            ),
            (
                "        def _fault(*, candidate=request):\n"
                "            return candidate.url\n"
                "        _fault()\n"
            ),
            (
                "        _fault = lambda candidate=request: candidate.url\n"
                "        _fault()\n"
            ),
        )
        for fault in faults:
            with self.subTest(fault=fault.splitlines()[0].strip()):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-flow-default-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    path = candidate / "autocapture/addon.py"
                    source = path.read_text(encoding="utf-8")
                    marker = "        request = flow.request\n"
                    self.assertIn(marker, source)
                    path.write_text(source.replace(marker, marker + fault, 1), encoding="utf-8")
                    self._rewrite_manifest(candidate)
                    self._assert_fails(candidate, "FLOW_OBJECT_ESCAPE")

    def test_arbitrary_flow_alias_names_are_tainted_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-flow-name-") as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/addon.py",
                (
                    "\ndef _unrelated_name(candidate):\n"
                    "    local_alias = candidate\n"
                    "    return local_alias.request.url\n"
                ),
            )
            self._assert_fails(candidate, "FLOW_FIELD_FORBIDDEN")

    def test_early_raw_content_read_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-body-order-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/addon.py"
            source = path.read_text(encoding="utf-8")
            signature = "    def _observe_response(self, flow):"
            self.assertIn(signature, source)
            path.write_text(
                source.replace(
                    signature,
                    signature + "\n        _fault_length = len(flow.response.raw_content)",
                    1,
                ),
                encoding="utf-8",
            )
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "FLOW_BODY_GATE_INVALID")

    def test_reversed_metadata_gate_is_rejected_after_manifest_rehash(self):
        gates = (
            (
                "if endpoint_selection == ENDPOINT_METADATA_INVALID:",
                "if endpoint_selection != ENDPOINT_METADATA_INVALID:",
            ),
            (
                "if endpoint_selection != ENDPOINT_MATCH:",
                "if endpoint_selection == ENDPOINT_MATCH:",
            ),
            (
                "if not policy.allows_status(status_code):",
                "if policy.allows_status(status_code):",
            ),
            (
                "if not policy.allows_content_type(content_type_value):",
                "if policy.allows_content_type(content_type_value):",
            ),
            (
                "if not self._identity_encoding(content_encoding_value):",
                "if self._identity_encoding(content_encoding_value):",
            ),
        )
        for original, replacement in gates:
            with self.subTest(gate=original):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-gate-direction-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    path = candidate / "autocapture/addon.py"
                    source = path.read_text(encoding="utf-8")
                    self.assertIn(original, source)
                    path.write_text(
                        source.replace(original, replacement, 1),
                        encoding="utf-8",
                    )
                    self._rewrite_manifest(candidate)
                    self._assert_fails(candidate, "FLOW_BODY_GATE_INVALID")

    def test_host_only_endpoint_selector_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-host-only-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/policy.py"
            source = path.read_text(encoding="utf-8")
            original = (
                "        candidate = EndpointRule(method, host, path)\n"
                "        if candidate in self.endpoint_rules:\n"
            )
            replacement = "        if host in {rule.host for rule in self.endpoint_rules}:\n"
            self.assertIn(original, source)
            path.write_text(source.replace(original, replacement, 1), encoding="utf-8")
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "ENDPOINT_SELECTOR_INVALID")

    def test_split_endpoint_selector_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-split-selector-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/policy.py"
            source = path.read_text(encoding="utf-8")
            original = (
                "        candidate = EndpointRule(method, host, path)\n"
                "        if candidate in self.endpoint_rules:\n"
            )
            replacement = (
                "        methods = {rule.method for rule in self.endpoint_rules}\n"
                "        hosts = {rule.host for rule in self.endpoint_rules}\n"
                "        paths = {rule.path for rule in self.endpoint_rules}\n"
                "        if method in methods and host in hosts and path in paths:\n"
            )
            self.assertIn(original, source)
            path.write_text(source.replace(original, replacement, 1), encoding="utf-8")
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "ENDPOINT_SELECTOR_INVALID")

    def test_endpoint_selector_response_order_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-selector-order-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/addon.py"
            source = path.read_text(encoding="utf-8")
            selector = "        endpoint_selection = policy.select_endpoint(method, host, path)\n"
            self.assertIn(selector, source)
            path.write_text(
                source.replace(selector, selector + "        response = flow.response\n", 1),
                encoding="utf-8",
            )
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "FLOW_BODY_GATE_INVALID")

    def test_endpoint_selector_request_surface_is_exact_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-selector-request-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/addon.py"
            source = path.read_text(encoding="utf-8")
            marker = "        path = request.path\n"
            self.assertIn(marker, source)
            path.write_text(
                source.replace(marker, marker + "        _fault_query = request.query\n", 1),
                encoding="utf-8",
            )
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "FLOW_FIELD_FORBIDDEN")

    def test_endpoint_selector_gate_removal_or_reversal_is_rejected_after_manifest_rehash(self):
        gates = (
            "if endpoint_selection == ENDPOINT_METADATA_INVALID:",
            "if endpoint_selection != ENDPOINT_MATCH:",
        )
        for gate in gates:
            with self.subTest(gate=gate):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-selector-gate-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    path = candidate / "autocapture/addon.py"
                    source = path.read_text(encoding="utf-8")
                    self.assertIn(gate, source)
                    path.write_text(source.replace(gate, "if False:", 1), encoding="utf-8")
                    self._rewrite_manifest(candidate)
                    self._assert_fails(candidate, "FLOW_BODY_GATE_INVALID")

    def test_duplicate_schema_key_classifier_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-classifier-copy-") as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/policy.py",
                "\ndef classify_schema_key(key, registered_schema_keys):\n    return \"REGISTERED_SAFE\"\n",
            )
            self._assert_fails(candidate, "SENSITIVE_RULE_INVALID")

    def test_schema_key_classifier_bypass_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-classifier-bypass-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/shape.py"
            source = path.read_text(encoding="utf-8")
            classifier_call = "                    key_classification = classify_schema_key("
            self.assertIn(classifier_call, source)
            path.write_text(
                source.replace(
                    classifier_call,
                    "                    key_classification = _bypass_classifier(",
                    1,
                ),
                encoding="utf-8",
            )
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "SENSITIVE_RULE_UNUSED")

    def test_loader_exact_export_and_disarmed_state_are_rejected_after_manifest_rehash(self):
        faults = (
            (
                "addons = [ResponseCaptureAddon()]",
                "addons = (ResponseCaptureAddon(),)",
            ),
            ("self._state = DISARMED", "self._state = ARMED"),
        )
        for original, replacement in faults:
            with self.subTest(original=original):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-loader-contract-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    path = candidate / "autocapture/addon.py"
                    source = path.read_text(encoding="utf-8")
                    self.assertIn(original, source)
                    path.write_text(
                        source.replace(original, replacement, 1),
                        encoding="utf-8",
                    )
                    self._rewrite_manifest(candidate)
                    self._assert_fails(candidate, "MITMPROXY_ADDON_INVALID")

    def test_loader_mitmproxy_import_and_auto_arm_are_rejected_after_manifest_rehash(self):
        faults = (
            ("\nimport mitmproxy\n", "FORBIDDEN_IMPORT"),
            ("\naddons[0].arm(None, None)\n", "MITMPROXY_ADDON_INVALID"),
            ("\ndef load(_loader):\n    return None\n", "MITMPROXY_ADDON_INVALID"),
        )
        for suffix, reason in faults:
            with self.subTest(reason=reason, suffix_kind=suffix.splitlines()[1][:4]):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-loader-escape-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    self._mutate_source(candidate, "autocapture/addon.py", suffix)
                    self._assert_fails(candidate, reason)

    def test_flow_container_aliases_are_rejected_after_manifest_rehash(self):
        cases = (
            ("    return holder[0].request.url\n", "FLOW_OBJECT_ESCAPE"),
            (
                '    return holder[0].response.headers.get("authorization")\n',
                "FLOW_OBJECT_ESCAPE",
            ),
            ('    holder[0].response.raw_content = b""\n', "FLOW_MUTATION_FORBIDDEN"),
        )
        for fault, reason in cases:
            with self.subTest(fault=fault.strip()):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-flow-container-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    self._mutate_source(
                        candidate,
                        "autocapture/addon.py",
                        "\ndef _fault_container(flow):\n    holder = [flow]\n" + fault,
                    )
                    self._assert_fails(candidate, reason)

    def test_body_escape_paths_are_rejected_after_manifest_rehash(self):
        faults = (
            "    return candidate.response.raw_content\n",
            "    _fault_sink(candidate.response.raw_content)\n",
            "    return [candidate.response.raw_content]\n",
        )
        for fault in faults:
            with self.subTest(fault=fault.strip()):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-body-escape-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    self._mutate_source(
                        candidate,
                        "autocapture/addon.py",
                        "\ndef _fault_body_escape(candidate):\n" + fault,
                    )
                    self._assert_fails(candidate, "FLOW_BODY_GATE_INVALID")

    def test_body_load_outside_addon_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(
            prefix="autocapture-verifier-body-global-"
        ) as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/shape.py",
                (
                    "\ndef _fault_body_outside_addon(candidate):\n"
                    "    return candidate.response.raw_content\n"
                ),
            )
            self._assert_fails(candidate, "FLOW_BODY_GATE_INVALID")

    def test_forbidden_response_header_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-header-") as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/addon.py",
                (
                    "\ndef _fault_header_read(flow):\n"
                    "    return flow.response.headers.get(\"authorization\")\n"
                ),
            )
            self._assert_fails(candidate, "FLOW_HEADER_FORBIDDEN")

    def test_flow_mutation_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-mutation-") as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/addon.py",
                "\ndef _fault_flow_write(flow):\n    flow.response.raw_content = b\"\"\n",
            )
            self._assert_fails(candidate, "FLOW_MUTATION_FORBIDDEN")

    def test_raw_and_value_hash_output_keys_are_rejected_after_manifest_rehash(self):
        for key in ("raw", "value_hash"):
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory(prefix="autocapture-verifier-key-") as temporary:
                    candidate = self._copy_candidate(temporary)
                    self._mutate_source(
                        candidate,
                        "autocapture/shape.py",
                        (
                            "\ndef _fault_output_key():\n"
                            "    return {{\"{0}\": \"synthetic\"}}\n".format(key)
                        ),
                    )
                    self._assert_fails(candidate, "FORBIDDEN_OUTPUT_KEY")

    def test_dynamic_value_hash_key_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-dynamic-key-") as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/shape.py",
                (
                    "\ndef _fault_dynamic_output_key():\n"
                    '    dynamic_key = "value_" + "hash"\n'
                    '    return {dynamic_key: "synthetic"}\n'
                ),
            )
            self._assert_fails(candidate, "FORBIDDEN_OUTPUT_KEY")

    def test_encoded_dynamic_value_hash_key_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(
            prefix="autocapture-verifier-encoded-key-"
        ) as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/publisher.py",
                (
                    "\n_INJECTED_DYNAMIC_OUTPUT = {\n"
                    '    bytes.fromhex("76616c75655f68617368").decode("ascii"): "synthetic"\n'
                    "}\n"
                ),
            )
            self._assert_fails(candidate, "FORBIDDEN_OUTPUT_KEY")

    def test_contiguous_sensitive_canary_is_rejected_without_echo(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-canary-") as temporary:
            candidate = self._copy_candidate(temporary)
            self._mutate_source(
                candidate,
                "autocapture/shape.py",
                "\n# fault: " + _generated_canary() + "\n",
            )
            self._assert_fails(candidate, "SENSITIVE_CANARY_LEAK")

    def test_deleted_sensitive_rule_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-sensitive-rule-") as temporary:
            candidate = self._copy_candidate(temporary)
            mutated = False
            for relative in PRODUCTION_FILES:
                path = candidate / relative
                source = path.read_text(encoding="utf-8")
                updated = source.replace('"authorization"', '"authorization_removed"')
                updated = updated.replace("'authorization'", "'authorization_removed'")
                if updated != source:
                    path.write_text(updated, encoding="utf-8")
                    mutated = True
            self.assertTrue(mutated, "candidate did not expose the frozen sensitive rule")
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "SENSITIVE_RULE_INCOMPLETE")

    def test_unused_sensitive_rule_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-sensitive-unused-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/shape.py"
            source = path.read_text(encoding="utf-8")
            classifier_call = "                    key_classification = classify_schema_key("
            self.assertIn(classifier_call, source)
            path.write_text(
                source.replace(
                    classifier_call,
                    "                    key_classification = _bypass_classifier(",
                    1,
                ),
                encoding="utf-8",
            )
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "SENSITIVE_RULE_UNUSED")

    def test_statically_disabled_sensitive_rule_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(
            prefix="autocapture-verifier-sensitive-disabled-"
        ) as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/shape.py"
            source = path.read_text(encoding="utf-8")
            membership = "    if _schema_key_has_sensitive_semantics(key):"
            self.assertIn(membership, source)
            path.write_text(
                source.replace(
                    membership,
                    "    if False:",
                    1,
                ),
                encoding="utf-8",
            )
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "SENSITIVE_RULE_INVALID")

    def test_split_sensitive_rule_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-sensitive-split-") as temporary:
            candidate = self._copy_candidate(temporary)
            shape_path = candidate / "autocapture/shape.py"
            shape_source = shape_path.read_text(encoding="utf-8")
            self.assertIn('"authorization"', shape_source)
            shape_path.write_text(
                shape_source.replace('"authorization"', '"authorization_removed"', 1),
                encoding="utf-8",
            )
            publisher_path = candidate / "autocapture/publisher.py"
            publisher_path.write_text(
                publisher_path.read_text(encoding="utf-8")
                + '\nSENSITIVE_KEY_TOKENS = frozenset({"authorization"})\n',
                encoding="utf-8",
            )
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "SENSITIVE_RULE_INCOMPLETE")

    def test_sensitive_execution_helpers_are_required_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(
            prefix="autocapture-verifier-sensitive-helper-"
        ) as temporary:
            candidate = self._copy_candidate(temporary)
            shape_path = candidate / "autocapture/shape.py"
            shape_source = shape_path.read_text(encoding="utf-8")
            normalizer = (
                '    separated = _ACRONYM_BOUNDARY.sub(r"\\1_\\2", key)\n'
                '    separated = _CAMEL_BOUNDARY.sub(r"\\1_\\2", separated)\n'
                '    separated = _LETTER_DIGIT_BOUNDARY.sub(r"\\1_\\2", separated)\n'
                '    separated = _DIGIT_LETTER_BOUNDARY.sub(r"\\1_\\2", separated)\n'
                "    lowered = separated.casefold()\n"
                '    return _NON_TOKEN.sub("_", lowered).strip("_")'
            )
            self.assertIn(normalizer, shape_source)
            shape_path.write_text(
                shape_source.replace(normalizer, '    return ""', 1),
                encoding="utf-8",
            )
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "SENSITIVE_RULE_INVALID")

    def test_unreachable_sensitive_gate_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(
            prefix="autocapture-verifier-sensitive-unreachable-"
        ) as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/shape.py"
            source = path.read_text(encoding="utf-8")
            membership = "                    if key_classification == SENSITIVE:"
            self.assertIn(membership, source)
            source = source.replace(membership, "                    if False:", 1)
            path.write_text(source, encoding="utf-8")
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "SENSITIVE_RULE_UNUSED")

    def test_manifest_missing_duplicate_extra_and_mismatch_are_rejected(self):
        cases = ("missing", "duplicate", "extra", "hash", "bytes")
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory(prefix="autocapture-verifier-manifest-") as temporary:
                    candidate = self._copy_candidate(temporary)
                    path = candidate / MANIFEST_RELATIVE
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                    entries = manifest["entries"]
                    if case == "missing":
                        del entries[0]
                        reason = "MANIFEST_MISMATCH"
                    elif case == "duplicate":
                        entries.append(dict(entries[0]))
                        reason = "MANIFEST_SCHEMA_INVALID"
                    elif case == "extra":
                        entries.append(
                            {
                                "path": "autocapture/ghost.py",
                                "bytes": 0,
                                "sha256": "0" * 64,
                            }
                        )
                        reason = "MANIFEST_MISMATCH"
                    elif case == "hash":
                        entries[0]["sha256"] = "0" * 64
                        reason = "MANIFEST_MISMATCH"
                    else:
                        entries[0]["bytes"] += 1
                        reason = "MANIFEST_MISMATCH"
                    path.write_text(
                        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    self._assert_fails(candidate, reason)

    def test_manifest_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-json-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / MANIFEST_RELATIVE
            path.write_text(
                (
                    '{"schema_version":"autocapture-build-manifest.v1",'
                    '"schema_version":"autocapture-build-manifest.v1",'
                    '"hash_algorithm":"sha256","entries":[]}\n'
                ),
                encoding="utf-8",
            )
            self._assert_fails(candidate, "MANIFEST_JSON_INVALID")

    def test_clobber_primitive_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-clobber-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/publisher.py"
            source = path.read_text(encoding="utf-8")
            self.assertIn("os.link(", source)
            path.write_text(source.replace("os.link(", "os.rename(", 1), encoding="utf-8")
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "FORBIDDEN_CAPABILITY")

    def test_dead_code_publisher_proof_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-dead-proof-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/publisher.py"
            source = path.read_text(encoding="utf-8")
            self.assertIn("os.link(", source)
            source = source.replace("os.link(", "_unsafe_publish(", 1)
            source += (
                "\ndef _dead_publisher_proof():\n"
                "    if False:\n"
                "        os.link(\n"
                '            \"staging\", \"target\", src_dir_fd=-1, dst_dir_fd=-1,\n'
                "            follow_symlinks=False,\n"
                "        )\n"
                "        _reopen_decoy()\n"
            )
            path.write_text(source, encoding="utf-8")
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "NO_CLOBBER_GUARD_MISSING")

    def test_unreachable_publish_link_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(
            prefix="autocapture-verifier-unreachable-link-"
        ) as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/publisher.py"
            source = path.read_text(encoding="utf-8")
            marker = '        """Publish and return the independently reopened bundle."""'
            self.assertIn("os.link(", source)
            self.assertIn(marker, source)
            source = source.replace("os.link(", "_unsafe_publish(", 1)
            source = source.replace(
                marker,
                (
                    marker
                    + "\n\n        if False:\n"
                    "            os.link(\n"
                    "                staging_name,\n"
                    "                self._target_name,\n"
                    "                src_dir_fd=root_fd,\n"
                    "                dst_dir_fd=root_fd,\n"
                    "                follow_symlinks=False,\n"
                    "            )"
                ),
                1,
            )
            path.write_text(source, encoding="utf-8")
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "NO_CLOBBER_GUARD_MISSING")

    def test_direct_target_unlink_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-target-unlink-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/publisher.py"
            source = path.read_text(encoding="utf-8")
            marker = '        """Publish and return the independently reopened bundle."""'
            self.assertIn(marker, source)
            source = source.replace(
                marker,
                marker + "\n\n        os.unlink(self._target_name)",
                1,
            )
            path.write_text(source, encoding="utf-8")
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "CLOBBER_PRIMITIVE_FORBIDDEN")

    def test_target_alias_clobber_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(
            prefix="autocapture-verifier-target-alias-"
        ) as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/publisher.py"
            source = path.read_text(encoding="utf-8")
            marker = "            root_fd = self._open_root()\n"
            self.assertIn(marker, source)
            path.write_text(
                source.replace(
                    marker,
                    (
                        marker
                        + "            target_alias = self._target_name\n"
                        + "            os.unlink(target_alias, dir_fd=root_fd)\n"
                    ),
                    1,
                ),
                encoding="utf-8",
            )
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "CLOBBER_PRIMITIVE_FORBIDDEN")

    def test_owned_target_cleanup_is_rejected_after_manifest_rehash(self):
        faults = (
            (
                "            self._unlink_if_owned(\n"
                "                root_fd,\n"
                "                self._target_name,\n"
                "                staging_identity,\n"
                "            )\n"
            ),
            (
                "            cleanup_target = self._unlink_if_owned\n"
                "            cleanup_target(\n"
                "                root_fd,\n"
                "                self._target_name,\n"
                "                staging_identity,\n"
                "            )\n"
            ),
        )
        for index, fault in enumerate(faults):
            with self.subTest(index=index):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-owned-target-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    path = candidate / "autocapture/publisher.py"
                    source = path.read_text(encoding="utf-8")
                    marker = "            reopened_bundle = self._reopen_and_validate(\n"
                    self.assertIn(marker, source)
                    path.write_text(
                        source.replace(marker, fault + marker, 1),
                        encoding="utf-8",
                    )
                    self._rewrite_manifest(candidate)
                    self._assert_fails(candidate, "CLOBBER_PRIMITIVE_FORBIDDEN")

    def test_missing_reopen_guard_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(prefix="autocapture-verifier-reopen-") as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/publisher.py"
            source = path.read_text(encoding="utf-8")
            call = "            reopened_bundle = self._reopen_and_validate("
            self.assertIn(call, source)
            path.write_text(source.replace(call, call.replace("reopen", "review"), 1), encoding="utf-8")
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "REOPEN_GUARD_MISSING")

    def test_required_fault_test_deletion_is_rejected_after_manifest_rehash(self):
        with tempfile.TemporaryDirectory(
            prefix="autocapture-verifier-test-inventory-"
        ) as temporary:
            candidate = self._copy_candidate(temporary)
            path = candidate / "autocapture/tests/test_verifier.py"
            source = path.read_text(encoding="utf-8")
            required = (
                "    def test_host_only_endpoint_selector_is_rejected_after_manifest_rehash(self):"
            )
            self.assertIn(required, source)
            path.write_text(
                source.replace(required, required.replace("test_", "removed_", 1), 1),
                encoding="utf-8",
            )
            self._rewrite_manifest(candidate)
            self._assert_fails(candidate, "VERIFIER_TESTS_INCOMPLETE")

    def test_semantic_manifest_swap_is_rejected(self):
        for fault in ("source_swap", "extra_file"):
            with self.subTest(fault=fault):
                with tempfile.TemporaryDirectory(
                    prefix="autocapture-verifier-snapshot-"
                ) as temporary:
                    candidate = self._copy_candidate(temporary)
                    self._rewrite_manifest(candidate)
                    namespace = runpy.run_path(str(self.verifier))
                    strict_verify = namespace["_strict_verify"]
                    runtime = strict_verify.__globals__
                    original = runtime["_semantic_checks"]

                    def swap_after_semantics(root, *, require_manifest):
                        snapshot = original(root, require_manifest=require_manifest)
                        if fault == "source_swap":
                            path = Path(root) / "autocapture/addon.py"
                            path.write_text(
                                path.read_text(encoding="utf-8") + "\nimport socket\n",
                                encoding="utf-8",
                            )
                            self._rewrite_manifest(Path(root))
                        else:
                            (Path(root) / "autocapture/rogue.py").write_text(
                                "# late extra\n",
                                encoding="utf-8",
                            )
                        return snapshot

                    runtime["_semantic_checks"] = swap_after_semantics
                    try:
                        with self.assertRaises(namespace["VerificationFailure"]) as raised:
                            strict_verify(candidate.resolve())
                    finally:
                        runtime["_semantic_checks"] = original
                    self.assertEqual(raised.exception.code, "TREE_CHANGED_DURING_VERIFY")


if __name__ == "__main__":
    unittest.main()
