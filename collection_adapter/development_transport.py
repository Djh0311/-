"""User-requested per-device development CA; capture authority remains separate.

Only its public certificate and ownership metadata may be inspected by callers.
The TLS engine uses the local private key; it is never exported or distributed.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from .p26_transport_preparation import (P26TransportPreparation, _FILES,
    _git_ignored_root, TransportPreparationError)

REGISTRY_NAME = 'development-ca.json'
_KEYS = {'schema_version', 'store_root', 'ca_directory', 'ca_directory_identity',
    'certificate_common_name', 'certificate_not_after', 'persistence', 'scope',
    'user_decision', 'key_exported', 'keychain_modified', 'source_readiness'}
_FLAGS = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)


def _public_certificate_expiry(path):
    from cryptography import x509
    cert = x509.load_pem_x509_certificate(path.read_bytes())
    return cert.not_valid_after_utc.isoformat()


def _read_registry(root):
    fd = os.open(root / REGISTRY_NAME, _FLAGS)
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.getuid()
                or stat.S_IMODE(meta.st_mode) != 0o600 or meta.st_size > 4096):
            raise TransportPreparationError('P26_DEDICATED_CA_INVALID')
        with os.fdopen(os.dup(fd), 'r', encoding='utf-8') as source:
            return json.load(source)
    finally:
        os.close(fd)


def validate_development_ca(store_root):
    """Metadata/public-expiry precheck; no private key, TLS host or network read."""
    try:
        root = Path(store_root)
        meta = root.lstat()
        if (not root.is_absolute() or str(root.resolve()) != str(root)
                or not stat.S_ISDIR(meta.st_mode) or meta.st_uid != os.getuid()
                or stat.S_IMODE(meta.st_mode) != 0o700 or not _git_ignored_root(str(root))):
            raise TransportPreparationError('P26_DEDICATED_CA_INVALID')
        r = _read_registry(root)
        if (type(r) is not dict or set(r) != _KEYS
                or r['schema_version'] != 'development-ca-registry/v1'
                or r['store_root'] != str(root)
                or r['persistence'] != 'RETAIN_UNTIL_EXPLICIT_USER_REMOVAL'
                or r['scope'] != 'LOCAL_DEVICE_ONLY'
                or r['user_decision'] != 'CURRENT_USER_REQUESTED_PERSISTENT_DEVELOPMENT_CA'
                or r['key_exported'] is not False or r['keychain_modified'] is not False
                or r['source_readiness'] != 'UNKNOWN'
                or type(r['certificate_common_name']) is not str
                or re.fullmatch(r'Local Collection Development CA [a-f0-9]{32}', r['certificate_common_name']) is None):
            raise TransportPreparationError('P26_DEDICATED_CA_INVALID')
        expiry = datetime.fromisoformat(r['certificate_not_after'])
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise TransportPreparationError('P26_DEDICATED_CA_INVALID')
        ca = Path(r['ca_directory']); meta = ca.lstat()
        if (ca.parent != root or re.fullmatch(r'p26_transport_[a-f0-9]{32}', ca.name) is None
                or not stat.S_ISDIR(meta.st_mode) or meta.st_uid != os.getuid()
                or stat.S_IMODE(meta.st_mode) != 0o700
                or r['ca_directory_identity'] != [meta.st_dev, meta.st_ino]
                or set(os.listdir(ca)) != set(_FILES)):
            raise TransportPreparationError('P26_DEDICATED_CA_INVALID')
        for filename in _FILES:
            meta = (ca / filename).lstat()
            if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.getuid()
                    or stat.S_IMODE(meta.st_mode) != 0o600 or not 0 < meta.st_size <= 65536):
                raise TransportPreparationError('P26_DEDICATED_CA_INVALID')
        return r
    except TransportPreparationError:
        raise
    except Exception:
        raise TransportPreparationError('P26_DEDICATED_CA_INVALID') from None


def create_development_ca_once(store_root, binding, approval):
    """Explicit setup after the user's persistent-CA decision; never replace one."""
    root = Path(store_root)
    if (root / REGISTRY_NAME).exists():
        raise TransportPreparationError('P26_CA_CREATION_UNAVAILABLE')
    session = P26TransportPreparation(binding, str(root), 'first_result',
        certificate_common_name='Local Collection Development CA ' + uuid4().hex)
    if session.prepare()['transport_preparation'] != 'COMPLETE':
        raise TransportPreparationError('P26_OUTPUT_NOT_GIT_IGNORED')
    if not session.create_ca_once(approval)['ca_created']:
        raise TransportPreparationError('P26_CA_CREATION_FAILED')
    try:
        # Read this newly-created PUBLIC certificate, never the private PEM/P12.
        expiry = _public_certificate_expiry(session._ca_path/'mitmproxy-ca-cert.pem')
        r = {'schema_version': 'development-ca-registry/v1', 'store_root': str(root),
            'ca_directory': str(session._ca_path),
            'ca_directory_identity': list(session._directory_identity),
            'certificate_common_name': session._common_name,
            'certificate_not_after': expiry,
            'persistence': 'RETAIN_UNTIL_EXPLICIT_USER_REMOVAL', 'scope': 'LOCAL_DEVICE_ONLY',
            'user_decision': 'CURRENT_USER_REQUESTED_PERSISTENT_DEVELOPMENT_CA',
            'key_exported': False, 'keychain_modified': False, 'source_readiness': 'UNKNOWN'}
        fd = os.open(root/REGISTRY_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as dest:
            json.dump(r, dest, sort_keys=True, indent=2); dest.write('\n')
        return validate_development_ca(root)
    except Exception:
        # Creation has not delivered an owned usable registry; roll back only own CA.
        session.remove_created_ca()
        raise TransportPreparationError('P26_CA_CREATION_FAILED') from None
