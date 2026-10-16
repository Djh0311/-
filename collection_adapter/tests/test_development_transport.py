from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from collection_adapter.contract import CollectionTarget
from collection_adapter.live_p0_entry import CurrentTargetBinding
from collection_adapter.p26_transport_preparation import (SpecificTransportApproval,
    REQUIRED_CAPABILITIES, TransportPreparationError, _FILES)
from collection_adapter.development_transport import (create_development_ca_once,
    validate_development_ca, REGISTRY_NAME)


class DevelopmentCATests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()/'development-transport'; self.root.mkdir(mode=0o700)
        self.binding = CurrentTargetBinding(CollectionTarget('target:synthetic_current'),
            'target-binding:synthetic_current', 'target-confirmation:synthetic_current')
        self.approval = SpecificTransportApproval('capability:synthetic_current',
            self.binding.target_confirmation_ref, REQUIRED_CAPABILITIES)
        for module in ('collection_adapter.p26_transport_preparation',
                       'collection_adapter.development_transport'):
            p = patch(module + '._git_ignored_root', return_value=True); p.start(); self.addCleanup(p.stop)
        def fake_ca(path, common_name):
            self.assertTrue(common_name.startswith('Local Collection Development CA '))
            for name in _FILES: (path/name).write_bytes(b'SYNTHETIC_CERTIFICATE_ONLY')
        p = patch('collection_adapter.p26_transport_preparation._create_dedicated_ca', side_effect=fake_ca)
        self.factory = p.start(); self.addCleanup(p.stop)
        p = patch('collection_adapter.development_transport._public_certificate_expiry',
            return_value=(datetime.now(timezone.utc)+timedelta(days=3650)).isoformat())
        p.start(); self.addCleanup(p.stop)

    def create(self): return create_development_ca_once(self.root, self.binding, self.approval)

    def test_create_once_then_metadata_only_reuse_does_not_recreate_or_read_private_key(self):
        registry = self.create(); ca = Path(registry['ca_directory'])
        original = os.open
        private_names = {'mitmproxy-ca.pem', 'mitmproxy-ca.p12', 'mitmproxy-ca-cert.p12'}
        def guarded(path, *args, **kwargs):
            if Path(path).name in private_names: self.fail('private material read')
            return original(path, *args, **kwargs)
        with patch('collection_adapter.development_transport.os.open', side_effect=guarded):
            self.assertEqual(validate_development_ca(self.root), registry)
        self.assertEqual(self.factory.call_count, 1)
        with self.assertRaisesRegex(TransportPreparationError, '^P26_CA_CREATION_UNAVAILABLE$'): self.create()
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(registry['persistence'], 'RETAIN_UNTIL_EXPLICIT_USER_REMOVAL')
        self.assertTrue(all((ca/n).stat().st_mode & 0o777 == 0o600 for n in _FILES))

    def test_capture_cleanup_does_not_delete_persistent_ca(self):
        from collection_adapter.p26_identification import IdentificationWindow
        registry = self.create(); before = {n: (Path(registry['ca_directory'])/n).stat().st_ino for n in _FILES}
        window = IdentificationWindow('Synthetic'); window.start_once(); window.close('P26_CANCELLED')
        self.assertEqual(validate_development_ca(self.root), registry)
        self.assertEqual(before, {n: (Path(registry['ca_directory'])/n).stat().st_ino for n in _FILES})
        self.assertEqual(window.diagnostic()['live_capture_latch'], 'CLOSED')

    def test_registry_expiry_permissions_identity_and_symlink_fail_closed(self):
        registry = self.create(); file = self.root/REGISTRY_NAME
        for change in ({'ca_directory_identity': [0, 0]}, {'certificate_not_after': '2000-01-01T00:00:00+00:00'},
                       {'source_readiness': 'READY'}, {'unexpected': 'synthetic'}):
            file.write_text(json.dumps({**registry, **change})); file.chmod(0o600)
            with self.subTest(change=next(iter(change))), self.assertRaisesRegex(TransportPreparationError, '^P26_DEDICATED_CA_INVALID$'):
                validate_development_ca(self.root)
        file.write_text(json.dumps(registry)); file.chmod(0o644)
        with self.assertRaises(TransportPreparationError): validate_development_ca(self.root)
        file.chmod(0o600)
        ca = Path(registry['ca_directory']); original = ca/'mitmproxy-ca-cert.cer'
        original.unlink(); original.symlink_to(ca/'mitmproxy-ca-cert.pem')
        with self.assertRaises(TransportPreparationError): validate_development_ca(self.root)

    def test_wrong_scope_does_not_generate_ca(self):
        bad = SpecificTransportApproval('capability:synthetic_other',
            'target-confirmation:synthetic_other', REQUIRED_CAPABILITIES)
        with self.assertRaises(TransportPreparationError):
            create_development_ca_once(self.root, self.binding, bad)
        self.factory.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_two_fresh_host_controls_reuse_ca_without_transport_or_attempt(self):
        from collection_adapter import p26_identification_host as host
        registry = self.create()
        original_ca = registry['ca_directory']
        for index in (1, 2):
            root = self.root.parent/('synthetic_capture_' + str(index)); root.mkdir(mode=0o700)
            state = {'schema_version': 'p26-transport-state/v1', 'output_root': str(root),
                'user_decision': 'CONFIRMED_CURRENT_SESSION', 'capabilities': list(REQUIRED_CAPABILITIES),
                'ca_trust': 'USER_ATTESTED_SSL_TRUST', 'page_isolation': 'USER_ATTESTED_SINGLE_TARGET_APPLET',
                'identification_attempts': 0, 'result_attempts': 0, 'live_capture_latch': 'CLOSED',
                'execution_latch': 'CLOSED', 'runtime_target_ref': 'target:synthetic_fresh_' + str(index),
                'target_binding_ref': 'target-binding:synthetic_fresh_' + str(index),
                'target_confirmation_ref': 'target-confirmation:synthetic_fresh_' + str(index),
                'ca_directory': original_ca, 'ca_directory_identity': registry['ca_directory_identity'],
                'ca_common_name': registry['certificate_common_name'],
                'development_ca': {'schema_version': 'development-ca-binding/v1', 'store_root': str(self.root)}}
            host._write_new(root, 'transport-state.json', state)
            host._write_new(root, 'current-business-choice.json', {'schema_version': 'p26-current-business-choice/v1',
                'source': 'CURRENT_USER_CONFIRMATION', 'store': 'Synthetic shop'})
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with patch.object(host, '_git_ignored_root', return_value=True), patch.object(host, '_helper_pid', return_value=123):
                prepared, _, pid = host.prepare(root)
                self.assertEqual((prepared['identification_attempts'], prepared['result_attempts'], pid), (0, 0, 123))
                self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)
                # An outside CA is forbidden without the exact owned development binding.
                del state['development_ca']
                (root/'transport-state.json').write_text(json.dumps(state))
                with self.assertRaisesRegex(host.IdentificationError, '^P26_DEDICATED_CA_INVALID$'):
                    host.prepare(root)
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(validate_development_ca(self.root)['ca_directory'], original_ca)


if __name__ == '__main__': unittest.main()
