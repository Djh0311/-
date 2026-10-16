"""Capability-gated transport preparation for the existing mitmproxy framework.

Preparation checks the current binding and destination only. It never loads a
TLS host, opens a source window, enables a redirector, or touches a keychain.
CA creation is a separate, explicitly approved operation in a new directory.
No legacy confdir, companion configuration, certificate or input is read.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from uuid import uuid4
from dataclasses import dataclass

from collection_core import ResultPublishError, precheck_result_destination

from .contract import CollectionTarget
from .live_p0_entry import CurrentTargetBinding, LiveP0EntryError


REQUIRED_CAPABILITIES = (
    "DEDICATED_TEMPORARY_CA_CREATE_AND_USE",
    "USER_MANUAL_CA_TRUST_AND_REMOVAL",
    "MACOS_PID_LOCAL_CAPTURE_SETUP",
)
_CAPABILITY_REF = re.compile(r"^capability:[A-Za-z0-9_-]{8,96}$")
_FILES = (
    "mitmproxy-ca.pem", "mitmproxy-ca.p12", "mitmproxy-ca-cert.pem",
    "mitmproxy-ca-cert.cer", "mitmproxy-ca-cert.p12", "mitmproxy-dhparam.pem",
)
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


class TransportPreparationError(ValueError):
    """Fixed code only; never forward library errors or supplied values."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SpecificTransportApproval:
    """Caller record of a real user's specific approval, not an authorization source.

    The caller must have the user's actual decision before constructing this
    record. Neither a reference nor this object establishes source readiness.
    """

    capability_ref: str
    target_confirmation_ref: str
    capabilities: tuple[str, ...]


def _git_ignored_root(root: str) -> bool:
    repo = str(Path(__file__).resolve().parent.parent)
    try:
        result = subprocess.run(
            ["git", "-C", repo, "check-ignore", "--quiet", "--", root],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=5, check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def _create_dedicated_ca(path: Path, common_name: str) -> None:
    # Import only after a matching specific approval and exclusive mkdir.
    from mitmproxy.certs import CertStore

    CertStore.create_store(path, "mitmproxy", 2048, organization="P26", cn=common_name)


class P26TransportPreparation:
    """Prepare, then optionally create one CA; no network start API."""

    def __init__(self, binding: CurrentTargetBinding, output_root: str, result_name: str,
                 *, certificate_common_name: str | None = None) -> None:
        if type(binding) is not CurrentTargetBinding:
            raise TransportPreparationError("P26_CURRENT_BINDING_REQUIRED")
        self.binding = binding
        self.output_root = output_root
        self.result_name = result_name
        if (certificate_common_name is not None and
                (type(certificate_common_name) is not str or re.fullmatch(
                 r"Local Collection Development CA [a-f0-9]{32}", certificate_common_name) is None)):
            raise TransportPreparationError("P26_SPECIFIC_CAPABILITY_REQUIRED")
        self._requested_common_name = certificate_common_name
        self._prepared = False
        self._creation_requested = False
        self._created = False
        self._code = "P26_TRANSPORT_NOT_PREPARED"
        self._cleanup = "NOT_REQUIRED"
        self._ca_path: Path | None = None
        self._common_name: str | None = None
        self._directory_identity: tuple[int, int] | None = None

    def prepare(self) -> dict[str, object]:
        """Read directory/ignore metadata; do not import TLS or create any file."""

        if self._creation_requested:
            return self.diagnostic()
        self._prepared = False
        self._code = self._destination_code() or "P26_SPECIFIC_CAPABILITY_REQUIRED"
        self._prepared = self._code == "P26_SPECIFIC_CAPABILITY_REQUIRED"
        return self.diagnostic()

    def _destination_code(self) -> str | None:
        try:
            precheck_result_destination(self.output_root, self.result_name)
        except ResultPublishError as error:
            return error.code
        if not _git_ignored_root(self.output_root):
            return "P26_OUTPUT_NOT_GIT_IGNORED"
        return None

    def create_ca_once(self, approval: SpecificTransportApproval) -> dict[str, object]:
        """Separate setup action; requires the actual, scope-matching user decision."""

        if (
            type(approval) is not SpecificTransportApproval
            or type(approval.capability_ref) is not str
            or _CAPABILITY_REF.fullmatch(approval.capability_ref) is None
            or approval.target_confirmation_ref != self.binding.target_confirmation_ref
            or type(approval.capabilities) is not tuple
            or approval.capabilities != REQUIRED_CAPABILITIES
        ):
            raise TransportPreparationError("P26_SPECIFIC_CAPABILITY_REQUIRED")
        if not self._prepared or self._creation_requested:
            raise TransportPreparationError("P26_CA_CREATION_UNAVAILABLE")
        code = self._destination_code()
        if code:
            self._prepared = False
            self._code = code
            return self.diagnostic()
        self._creation_requested = True
        name = "p26_transport_" + uuid4().hex
        path = Path(self.output_root) / name
        common_name = self._requested_common_name or "P26 Temporary CA " + uuid4().hex
        root_fd = child_fd = None
        created_directory = False
        old_umask = None
        try:
            root_fd = os.open(self.output_root, _DIRECTORY_FLAGS)
            root_stat = os.fstat(root_fd)
            if stat.S_IMODE(root_stat.st_mode) != 0o700 or root_stat.st_uid != os.getuid():
                raise TransportPreparationError("RESULT_ROOT_INVALID")
            os.mkdir(name, 0o700, dir_fd=root_fd)
            created_directory = True
            child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
            old_umask = os.umask(0o077)
            _create_dedicated_ca(path, common_name)
            if set(os.listdir(child_fd)) != set(_FILES):
                raise TransportPreparationError("P26_CA_CREATION_FAILED")
            for filename in _FILES:
                metadata = os.stat(filename, dir_fd=child_fd, follow_symlinks=False)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 65536:
                    raise TransportPreparationError("P26_CA_CREATION_FAILED")
                os.chmod(filename, 0o600, dir_fd=child_fd, follow_symlinks=False)
            self._created = True
            self._ca_path = path
            self._common_name = common_name
            child_stat = os.fstat(child_fd)
            self._directory_identity = (child_stat.st_dev, child_stat.st_ino)
            self._code = "P26_CA_CREATED_TRUST_PENDING"
        except Exception:
            self._code = "P26_CA_CREATION_FAILED"
        finally:
            if old_umask is not None:
                os.umask(old_umask)
            if not self._created and created_directory:
                self._cleanup = "COMPLETE"
                if child_fd is None:
                    self._cleanup = "INCOMPLETE"
                else:
                    for filename in _FILES:
                        try:
                            os.unlink(filename, dir_fd=child_fd)
                        except FileNotFoundError:
                            pass
                        except OSError:
                            self._cleanup = "INCOMPLETE"
                    try:
                        os.rmdir(name, dir_fd=root_fd)
                    except OSError:
                        self._cleanup = "INCOMPLETE"
            if child_fd is not None:
                os.close(child_fd)
            if root_fd is not None:
                os.close(root_fd)
        return self.diagnostic()

    def remove_created_ca(self) -> dict[str, object]:
        """After the caller closes capture, remove only this session's fixed files.

        This does not remove user trust or uninstall a network extension. The
        user must remove the named public certificate from their keychain.
        """

        if not self._created or self._ca_path is None:
            raise TransportPreparationError("P26_CA_CREATION_UNAVAILABLE")
        root_fd = child_fd = None
        self._cleanup = "INCOMPLETE"
        try:
            root_fd = os.open(self.output_root, _DIRECTORY_FLAGS)
            child_fd = os.open(self._ca_path.name, _DIRECTORY_FLAGS, dir_fd=root_fd)
            metadata = os.fstat(child_fd)
            if (metadata.st_dev, metadata.st_ino) != self._directory_identity:
                return self.diagnostic()
            if set(os.listdir(child_fd)) != set(_FILES):
                return self.diagnostic()
            for filename in _FILES:
                os.unlink(filename, dir_fd=child_fd)
            os.rmdir(self._ca_path.name, dir_fd=root_fd)
            self._created = False
            self._cleanup = "COMPLETE"
            self._code = "P26_CA_REMOVED_MANUAL_TRUST_REMOVAL_REQUIRED"
        except OSError:
            pass
        finally:
            if child_fd is not None:
                os.close(child_fd)
            if root_fd is not None:
                os.close(root_fd)
        return self.diagnostic()

    def manual_trust_instructions(self) -> dict[str, str]:
        """Public certificate locator only, never a private key or its bytes."""

        if not self._created or self._ca_path is None or self._common_name is None:
            raise TransportPreparationError("P26_CA_CREATION_UNAVAILABLE")
        return {
            "certificate_path": str(self._ca_path / "mitmproxy-ca-cert.pem"),
            "certificate_common_name": self._common_name,
        }

    def diagnostic(self) -> dict[str, object]:
        return {
            "schema_version": "p26-transport-preparation/v1",
            "transport_preparation": "COMPLETE" if self._prepared else "INCOMPLETE",
            "closure_code": self._code,
            "current_target_binding": "CALLER_ATTESTED_CURRENT_CHOICE",
            "source_identity": "NOT_OBSERVED",
            "flow_isolation": "UNKNOWN",
            "real_source_ready": "UNKNOWN",
            "ca_created": self._created,
            "ca_trust": "NOT_CONFIRMED",
            "cleanup_status": self._cleanup,
            "required_capabilities": list(REQUIRED_CAPABILITIES),
            "identification_attempts": 0,
            "result_attempts": 0,
            "live_capture_latch": "CLOSED",
            "execution_latch": "CLOSED",
            "network_extension_started": False,
            "keychain_modified": False,
        }


class _FixedArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise TransportPreparationError("P26_PREPARATION_ARGUMENTS_INVALID")


def main(argv: list[str] | None = None) -> int:
    parser = _FixedArgumentParser(description="P26 local-only transport preflight; never starts capture.")
    for name in ("output-root", "result-name", "target-ref", "target-binding-ref", "target-confirmation-ref"):
        parser.add_argument("--" + name, required=True)
    try:
        args = parser.parse_args(argv)
        binding = CurrentTargetBinding(
            CollectionTarget(args.target_ref), args.target_binding_ref, args.target_confirmation_ref,
        )
        session = P26TransportPreparation(binding, args.output_root, args.result_name)
        print(json.dumps(session.prepare(), ensure_ascii=True, sort_keys=True))
        return 0 if session._prepared else 2
    except (TransportPreparationError, LiveP0EntryError, ValueError):
        print('{"closure_code":"P26_PREPARATION_ARGUMENTS_INVALID"}')
        return 2


if __name__ == "__main__":
    sys.exit(main())
