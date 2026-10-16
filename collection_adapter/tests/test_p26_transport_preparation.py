"""Synthetic evidence for capability and filesystem gates; no real CA or network."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from collection_adapter.contract import CollectionTarget
from collection_adapter.live_p0_entry import CurrentTargetBinding, HistoricalTargetBinding, HISTORICAL_TARGET_REF
from collection_adapter import p26_transport_preparation as transport


class TransportPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.binding = CurrentTargetBinding(
            CollectionTarget('target:p26_synthetic_current'),
            'target-binding:p26_synthetic_current', 'target-confirmation:p26_synthetic_current',
        )
        self.session = transport.P26TransportPreparation(self.binding, str(self.root), 'first_result')
        self.ignored = patch.object(transport, '_git_ignored_root', return_value=True)
        self.ignored.start()
        self.addCleanup(self.ignored.stop)
        self.approval = transport.SpecificTransportApproval(
            'capability:p26_synthetic_explicit', self.binding.target_confirmation_ref,
            transport.REQUIRED_CAPABILITIES,
        )

    def assert_receipt(self, receipt):
        schema_path = Path(__file__).resolve().parents[2] / 'contracts/schemas/p26-transport-preparation-v1.schema.json'
        schema = json.loads(schema_path.read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(receipt)
        self.assertEqual(receipt['identification_attempts'], 0)
        self.assertEqual(receipt['result_attempts'], 0)
        self.assertEqual(receipt['live_capture_latch'], 'CLOSED')
        self.assertEqual(receipt['execution_latch'], 'CLOSED')
        self.assertFalse(receipt['network_extension_started'])
        self.assertFalse(receipt['keychain_modified'])
        self.assertEqual(receipt['real_source_ready'], 'UNKNOWN')

    @staticmethod
    def fake_ca(path, _common_name):
        for filename in transport._FILES:
            (path / filename).write_bytes(b'synthetic-ca-test-only')

    def test_prepare_and_cli_do_not_import_tls_or_create_files(self):
        with patch.object(transport, '_create_dedicated_ca', side_effect=AssertionError('must not create')) as factory:
            receipt = self.session.prepare()
            self.assert_receipt(receipt)
            self.assertEqual(receipt['closure_code'], 'P26_SPECIFIC_CAPABILITY_REQUIRED')
            self.assertFalse(receipt['ca_created'])
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                result = transport.main([
                    '--output-root', str(self.root), '--result-name', 'first_result',
                    '--target-ref', self.binding.runtime_target.target_ref,
                    '--target-binding-ref', self.binding.target_binding_ref,
                    '--target-confirmation-ref', self.binding.target_confirmation_ref,
                ])
            self.assertEqual(result, 0)
            self.assert_receipt(json.loads(output.getvalue()))
            self.assertEqual(errors.getvalue(), '')
            factory.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_incomplete_or_other_target_approval_cannot_create(self):
        self.session.prepare()
        bad = [None, transport.SpecificTransportApproval(
            self.approval.capability_ref, 'target-confirmation:p26_other_current', transport.REQUIRED_CAPABILITIES,
        ), transport.SpecificTransportApproval(
            self.approval.capability_ref, self.binding.target_confirmation_ref, transport.REQUIRED_CAPABILITIES[:1],
        )]
        with patch.object(transport, '_create_dedicated_ca') as factory:
            for approval in bad:
                with self.assertRaises(transport.TransportPreparationError) as caught:
                    self.session.create_ca_once(approval)
                self.assertEqual(str(caught.exception), 'P26_SPECIFIC_CAPABILITY_REQUIRED')
            factory.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])
        self.assert_receipt(self.session.diagnostic())

    def test_historical_binding_is_not_a_transport_target(self):
        historical = HistoricalTargetBinding(HISTORICAL_TARGET_REF, self.binding.runtime_target, self.binding.target_binding_ref)
        with self.assertRaises(transport.TransportPreparationError) as caught:
            transport.P26TransportPreparation(historical, str(self.root), 'first_result')
        self.assertEqual(str(caught.exception), 'P26_CURRENT_BINDING_REQUIRED')

    def test_nonignored_root_is_rejected_before_creation(self):
        with patch.object(transport, '_git_ignored_root', return_value=False):
            receipt = self.session.prepare()
            self.assert_receipt(receipt)
            self.assertEqual(receipt['closure_code'], 'P26_OUTPUT_NOT_GIT_IGNORED')
            with self.assertRaises(transport.TransportPreparationError):
                self.session.create_ca_once(self.approval)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_destination_is_checked_again_and_existing_results_preserved(self):
        self.session.prepare()
        result = self.root / 'first_result'
        result.mkdir()
        marker = result / 'existing.txt'
        marker.write_text('synthetic-existing-result')
        with patch.object(transport, '_create_dedicated_ca') as factory:
            receipt = self.session.create_ca_once(self.approval)
            factory.assert_not_called()
        self.assert_receipt(receipt)
        self.assertEqual(receipt['closure_code'], 'RESULT_TARGET_EXISTS')
        self.assertEqual(marker.read_text(), 'synthetic-existing-result')
        self.assertEqual(list(self.root.iterdir()), [result])

    def test_creation_uses_new_directory_and_does_not_reuse_old_ca(self):
        legacy = self.root / 'legacy-confdir'
        legacy.mkdir()
        old = legacy / 'mitmproxy-ca.pem'
        old.write_text('synthetic-legacy-private-key-must-not-be-read')
        self.session.prepare()
        with patch.object(transport, '_create_dedicated_ca', side_effect=self.fake_ca) as factory:
            receipt = self.session.create_ca_once(self.approval)
            self.assert_receipt(receipt)
            self.assertEqual(receipt['closure_code'], 'P26_CA_CREATED_TRUST_PENDING')
            self.assertTrue(receipt['ca_created'])
            path, common_name = factory.call_args.args
            self.assertNotEqual(path, legacy)
            self.assertTrue(path.name.startswith('p26_transport_'))
            self.assertTrue(common_name.startswith('P26 Temporary CA '))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
            for child in path.iterdir():
                self.assertEqual(stat.S_IMODE(child.stat().st_mode), 0o600)
            with self.assertRaises(transport.TransportPreparationError):
                self.session.create_ca_once(self.approval)
            self.assertEqual(factory.call_count, 1)
        instructions = self.session.manual_trust_instructions()
        self.assertEqual(Path(instructions['certificate_path']).name, 'mitmproxy-ca-cert.pem')
        self.assertEqual(old.read_text(), 'synthetic-legacy-private-key-must-not-be-read')
        self.assertFalse((self.root / 'first_result').exists())

    def test_exception_is_closed_and_cleans_only_created_files(self):
        preserved = self.root / 'preserved.txt'
        preserved.write_text('synthetic-existing')
        self.session.prepare()
        def failing_ca(path, _common_name):
            (path / 'mitmproxy-ca.pem').write_bytes(b'synthetic-partial-key')
            raise ValueError('synthetic-sensitive-error-text-must-not-escape')
        with patch.object(transport, '_create_dedicated_ca', side_effect=failing_ca):
            receipt = self.session.create_ca_once(self.approval)
        self.assert_receipt(receipt)
        self.assertEqual(receipt['closure_code'], 'P26_CA_CREATION_FAILED')
        self.assertEqual(receipt['cleanup_status'], 'COMPLETE')
        self.assertNotIn('synthetic-sensitive', json.dumps(receipt))
        self.assertEqual(list(self.root.iterdir()), [preserved])
        self.assertEqual(preserved.read_text(), 'synthetic-existing')

    def test_rollback_removes_only_the_created_ca_and_preserves_results(self):
        self.session.prepare()
        with patch.object(transport, '_create_dedicated_ca', side_effect=self.fake_ca):
            self.session.create_ca_once(self.approval)
        result = self.root / 'first_result'
        result.mkdir()
        marker = result / 'records.json'
        marker.write_text('synthetic-existing-result')
        receipt = self.session.remove_created_ca()
        self.assert_receipt(receipt)
        self.assertFalse(receipt['ca_created'])
        self.assertEqual(receipt['cleanup_status'], 'COMPLETE')
        self.assertEqual(receipt['closure_code'], 'P26_CA_REMOVED_MANUAL_TRUST_REMOVAL_REQUIRED')
        self.assertEqual(list(self.root.iterdir()), [result])
        self.assertEqual(marker.read_text(), 'synthetic-existing-result')

    def test_rollback_refuses_a_replaced_directory(self):
        self.session.prepare()
        with patch.object(transport, '_create_dedicated_ca', side_effect=self.fake_ca) as factory:
            self.session.create_ca_once(self.approval)
        original_path = factory.call_args.args[0]
        held = self.root / 'held-created-ca'
        original_path.rename(held)
        original_path.mkdir()
        self.fake_ca(original_path, '')
        receipt = self.session.remove_created_ca()
        self.assert_receipt(receipt)
        self.assertEqual(receipt['cleanup_status'], 'INCOMPLETE')
        self.assertEqual(len(list(original_path.iterdir())), 6)
        self.assertEqual(len(list(held.iterdir())), 6)

    def test_created_symlink_is_refused_without_touching_its_target(self):
        preserved = self.root / 'preserved.txt'
        preserved.write_text('synthetic-existing')
        self.session.prepare()
        def symlink_ca(path, common_name):
            self.fake_ca(path, common_name)
            item = path / 'mitmproxy-ca.pem'
            item.unlink()
            item.symlink_to(preserved)
        with patch.object(transport, '_create_dedicated_ca', side_effect=symlink_ca):
            receipt = self.session.create_ca_once(self.approval)
        self.assert_receipt(receipt)
        self.assertEqual(receipt['closure_code'], 'P26_CA_CREATION_FAILED')
        self.assertEqual(receipt['cleanup_status'], 'COMPLETE')
        self.assertEqual(preserved.read_text(), 'synthetic-existing')
        self.assertEqual(list(self.root.iterdir()), [preserved])

    def test_unexpected_files_are_not_recursively_deleted(self):
        self.session.prepare()
        def extra_file_ca(path, common_name):
            self.fake_ca(path, common_name)
            (path / 'unowned.txt').write_text('synthetic-unknown-owner')
        with patch.object(transport, '_create_dedicated_ca', side_effect=extra_file_ca):
            receipt = self.session.create_ca_once(self.approval)
        self.assert_receipt(receipt)
        self.assertEqual(receipt['closure_code'], 'P26_CA_CREATION_FAILED')
        self.assertEqual(receipt['cleanup_status'], 'INCOMPLETE')
        dirs = list(self.root.iterdir())
        self.assertEqual(len(dirs), 1)
        self.assertEqual([p.name for p in dirs[0].iterdir()], ['unowned.txt'])

    def test_cli_argument_errors_never_echo_values(self):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            result = transport.main(['--unknown', 'synthetic-sensitive-argument'])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue()), {'closure_code': 'P26_PREPARATION_ARGUMENTS_INVALID'})
        self.assertEqual(errors.getvalue(), '')
        self.assertNotIn('synthetic-sensitive', output.getvalue())


if __name__ == '__main__':
    unittest.main()
