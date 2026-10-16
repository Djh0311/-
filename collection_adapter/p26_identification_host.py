"""Scoped streaming helpers and an explicit forwarded-copy entry.

Legacy invocations remain retired. The new P29 entry requires an explicit
forwarded-copy choice, fresh preparation, and a separate start command.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
import ipaddress
import json
import logging
import os
from pathlib import Path
import stat
import subprocess
import sys
import unicodedata
from uuid import uuid4
from urllib.parse import unquote

from collection_core import precheck_result_destination
from .p26_identification import IdentificationError, IdentificationWindow, route_template
from .p26_transport_preparation import REQUIRED_CAPABILITIES, _FILES, _git_ignored_root
from .contract import CollectionTarget
from .live_p0_entry import CurrentTargetBinding

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_REDIRECTOR = Path("/Applications/Mitmproxy Redirector.app")
_event_output = None
MAX_DIAGNOSTIC_QUEUE = 1024 * 1024
MAX_LAYOUT_SNAPSHOTS = 8
_PRECHECK_CODES = frozenset({
    "P26_LOCAL_STATE_INVALID", "P26_EXACT_APPLET_PID_REQUIRED", "P26_OUTPUT_ROOT_INVALID",
    "P26_OUTPUT_NOT_GIT_IGNORED", "P26_APPROVED_PRECONDITIONS_REQUIRED",
    "P26_CURRENT_CHOICE_REQUIRED", "P26_DEDICATED_CA_INVALID", "P26_WINDOW_ALREADY_USED",
    "P26_NETWORK_OWNER_UNCONFIRMED", "P26_MONITORING_SCOPE_INVALID",
    "P26_RESULT_PROFILE_INVALID",
})


def _redirector_present() -> bool:
    return (_REDIRECTOR.is_dir() and not _REDIRECTOR.is_symlink()
            and (_REDIRECTOR / "Contents/MacOS/Mitmproxy Redirector").is_file())


def _read_owned(path: Path, limit: int = 8192) -> dict:
    fd = os.open(path, os.O_RDONLY | _NOFOLLOW)
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > limit):
            raise IdentificationError("P26_LOCAL_STATE_INVALID")
        with os.fdopen(os.dup(fd), "r", encoding="utf-8") as source:
            result = json.load(source)
        if type(result) is not dict:
            raise IdentificationError("P26_LOCAL_STATE_INVALID")
        return result
    finally:
        os.close(fd)


def _write_new(root: Path, name: str, document: dict) -> None:
    fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(document, output, ensure_ascii=True, sort_keys=True, indent=2)
        output.write("\n")


def _helper_pid() -> int:
    result = subprocess.run(["pgrep", "-x", "WeChatAppEx"], capture_output=True,
                            text=True, timeout=5, check=False)
    values = result.stdout.split()
    if result.returncode or len(values) != 1 or not values[0].isdigit():
        raise IdentificationError("P26_EXACT_APPLET_PID_REQUIRED")
    return int(values[0])


def _monitoring_approved(state: dict) -> bool:
    scope = state.get("monitoring_authorization")
    if scope is None:
        return False
    if (type(scope) is not dict or scope.get("schema_version") != "p26-monitoring-authorization/v1"
            or type(scope.get("scope_ref")) is not str
            or not scope["scope_ref"].startswith("monitoring:") or len(scope["scope_ref"]) != 43
            or any(scope.get(key) != state.get(key) for key in (
                "runtime_target_ref", "target_binding_ref", "target_confirmation_ref"))):
        raise IdentificationError("P26_MONITORING_SCOPE_INVALID")
    unlimited = (scope.get('user_decision') == 'CURRENT_USER_NO_TIME_OR_ATTEMPT_LIMIT'
        and scope.get('time_limit_seconds', False) is None
        and scope.get('attempt_limit', False) is None)
    trial = (scope.get('user_decision') == 'CURRENT_USER_REQUESTED_ONE_SMALL_TRIAL'
        and type(scope.get('time_limit_seconds')) is int and scope['time_limit_seconds'] == 120
        and type(scope.get('attempt_limit')) is int and scope['attempt_limit'] == 1)
    continuous = (scope.get('user_decision') == 'CURRENT_USER_REQUESTED_CONTINUOUS_RECEIVING'
        and scope.get('time_limit_seconds', False) is None
        and type(scope.get('attempt_limit')) is int and scope['attempt_limit'] == 1)
    if not (unlimited or trial or continuous):
        raise IdentificationError('P26_MONITORING_SCOPE_INVALID')
    return True


def _public_batch_approved(state: dict) -> bool:
    scope = state.get("public_business_batch")
    if (not _monitoring_approved(state) or type(scope) is not dict
            or scope.get("schema_version") != "p26-public-business-batch-authorization/v1"
            or scope.get("user_decision") != "CURRENT_USER_REQUESTED_BATCH_PUBLIC_BUSINESS_INPUT"
            or scope.get("private_inputs") != "EXCLUDED" or scope.get("raw_persistence") is not False
            or scope.get("results_target") != "CURRENT_CONFIRMED_STORE"
            or any(scope.get(key) != state.get(key) for key in (
                "runtime_target_ref", "target_binding_ref", "target_confirmation_ref"))):
        raise IdentificationError("P26_MONITORING_SCOPE_INVALID")
    return True


def _sensitive_key_layout_approved(state: dict) -> bool:
    scope = state.get("sensitive_field_inspection")
    if (type(scope) is not dict
            or scope.get("user_decision") != "CURRENT_USER_ALLOWED_SENSITIVE_FIELD_INSPECTION"
            or scope.get("inspection") != "KEY_PATH_TYPE_ONLY"
            or scope.get("field_values_processed") is not False
            or scope.get("raw_persistence") is not False
            or any(scope.get(key) != state.get(key) for key in (
                "runtime_target_ref", "target_binding_ref", "target_confirmation_ref"))):
        raise IdentificationError("P26_MONITORING_SCOPE_INVALID")
    return True


def _verify_network_owner_pid(pid: int, owner_pid: int | None = None) -> None:
    """Socket ownership metadata only; never choose another PID or read addresses."""
    children = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True,
                              text=True, timeout=5, check=False)
    values = children.stdout.split()
    if children.returncode not in (0, 1) or len(values) > 16 or any(not p.isdigit() for p in values):
        raise IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")
    owners = {pid, *(int(p) for p in values)}
    sockets = subprocess.run(["lsof", "-nP", "-a", "-p", ",".join([str(pid), *values]),
                              "-i", "-F", "pP"], capture_output=True,
                             text=True, timeout=5, check=False)
    if sockets.returncode not in (0, 1) or len(sockets.stdout) > 8192:
        raise IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")
    current = None
    network_owners = set()
    for line in sockets.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            current = int(line[1:])
        elif line in ("PTCP", "PUDP") and current in owners:
            network_owners.add(current)
    if network_owners != {pid if owner_pid is None else owner_pid}:
        raise IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")


def _helper_restart_scope(state: dict, root: Path, pid: int) -> dict | None:
    scope = state.get("network_helper_restart")
    if scope is None:
        return None
    if (type(scope) is not dict or scope.get("schema_version") != "p26-network-helper-restart/v1"
            or scope.get("user_decision") != "CURRENT_USER_APPROVED_ONE_BOUND_HELPER_RESTART"
            or type(scope.get("replacement_observed")) is not bool
            or type(scope.get("restart_ref")) is not str
            or not scope["restart_ref"].startswith("helper-restart:")
            or len(scope["restart_ref"]) != len("helper-restart:") + 32
            or any(scope.get(key) != state.get(key) for key in (
                "runtime_target_ref", "target_binding_ref", "target_confirmation_ref"))):
        raise IdentificationError("P26_MONITORING_SCOPE_INVALID")
    if scope["replacement_observed"]:
        return None  # The one authorized process replacement is already used.
    binding = _read_owned(root / "current-network-process-binding.json", 2048)
    executable = scope.get("executable")
    if (not _monitoring_approved(state) or scope.get("applet_parent_pid") != binding.get("applet_pid")
            or scope.get("original_network_pid") != pid
            or type(executable) is not str or len(executable) > 512
            or not executable.startswith("/Applications/WeChat.app/Contents/MacOS/WeChatAppEx.app/")
            or any(c in executable for c in (",", "!", ":", "\n", "\0"))):
        raise IdentificationError("P26_MONITORING_SCOPE_INVALID")
    metadata = subprocess.run(["ps", "-p", str(pid), "-o", "ppid=,uid=,comm="],
                              capture_output=True, text=True, timeout=5, check=False)
    if (metadata.returncode or metadata.stdout.strip().split(None, 2)
            != [str(scope["applet_parent_pid"]), str(os.getuid()), executable]):
        raise IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")
    return scope


class NetworkHelperReplacement:
    """One explicitly approved replacement, still verified before stream bytes."""

    def __init__(self, root: Path, scope: dict):
        self.root, self.scope = root, scope
        self.count = 0

    def accept(self, pid: int) -> None:
        if self.count or type(pid) is not int or pid <= 0:
            raise IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")
        parent = self.scope["applet_parent_pid"]
        if _helper_pid() != parent:
            raise IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")
        metadata = subprocess.run(["ps", "-p", str(pid), "-o", "ppid=,uid=,comm="],
                                  capture_output=True, text=True, timeout=5, check=False)
        if (metadata.returncode or metadata.stdout.strip().split(None, 2)
                != [str(parent), str(os.getuid()), self.scope["executable"]]):
            raise IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")
        # Require this exact child to be the sole current socket owner in the
        # same applet parent. A different parent/path/UID or parallel owner stops.
        _verify_network_owner_pid(parent, pid)
        binding = _read_owned(self.root / "current-network-process-binding.json", 2048)
        if (binding.get("applet_pid") != parent
                or binding.get("network_pid") != self.scope["original_network_pid"]):
            raise IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")
        binding["network_pid"] = pid
        name = "network-binding-" + uuid4().hex + ".tmp"
        _write_new(self.root, name, binding)
        os.replace(self.root / name, self.root / "current-network-process-binding.json")
        self.count = 1
        self.scope["replacement_observed"] = True
        _emit({"event": "P26_NETWORK_HELPER_REBOUND", "network_helper_replacements": 1})


def _selected_pid(root: Path, monitoring: bool) -> int:
    parent = _helper_pid()
    if not monitoring:
        return parent
    binding = _read_owned(root / "current-network-process-binding.json", 2048)
    pid = binding.get("network_pid")
    if (binding.get("schema_version") != "p26-network-process-precheck/v1"
            or binding.get("applet_pid") != parent or type(pid) is not int or pid <= 0
            or binding.get("selection_basis") != "DIRECT_CHILD_CURRENT_SOCKET_OWNER"):
        raise IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")
    metadata = subprocess.run(["ps", "-p", str(pid), "-o", "ppid=,uid=,comm="],
                              capture_output=True, text=True, timeout=5, check=False)
    fields = metadata.stdout.strip().split(None, 2)
    if (metadata.returncode or len(fields) != 3 or fields[:2] != [str(parent), str(os.getuid())]
            or not fields[2].startswith("/Applications/WeChat.app/Contents/MacOS/WeChatAppEx.app/")):
        raise IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")
    _verify_network_owner_pid(pid)
    return pid


def prepare(root: Path) -> tuple[dict, dict, int]:
    # No mitmproxy import or file creation, no clock, callbacks or attempt.
    if not root.is_absolute() or root.is_symlink():
        raise IdentificationError("P26_OUTPUT_ROOT_INVALID")
    precheck_result_destination(str(root), "first_result")
    if not _git_ignored_root(str(root)):
        raise IdentificationError("P26_OUTPUT_NOT_GIT_IGNORED")
    state = _read_owned(root / "transport-state.json")
    choice = _read_owned(root / "current-business-choice.json", 2048)
    if (state.get("schema_version") != "p26-transport-state/v1"
            or state.get("output_root") != str(root)
            or state.get("user_decision") != "CONFIRMED_CURRENT_SESSION"
            or state.get("capabilities") != list(REQUIRED_CAPABILITIES)
            or state.get("ca_trust") != "USER_ATTESTED_SSL_TRUST"
            or state.get("page_isolation") != "USER_ATTESTED_SINGLE_TARGET_APPLET"
            or type(state.get("identification_attempts")) is not int or state["identification_attempts"] < 0
            or type(state.get("result_attempts")) is not int or state["result_attempts"] < 0
            or state.get("live_capture_latch") != "CLOSED"
            or state.get("execution_latch") != "CLOSED"):
        raise IdentificationError("P26_APPROVED_PRECONDITIONS_REQUIRED")
    monitoring = _monitoring_approved(state)
    if not monitoring and (state["identification_attempts"] or state["result_attempts"]
                           or (root / "identification-attempt.lock").exists()):
        raise IdentificationError("P26_WINDOW_ALREADY_USED")
    CurrentTargetBinding(CollectionTarget(state["runtime_target_ref"]),
                         state["target_binding_ref"], state["target_confirmation_ref"])
    if (choice.get("schema_version") != "p26-current-business-choice/v1"
            or choice.get("source") != "CURRENT_USER_CONFIRMATION"
            or type(choice.get("store")) is not str
            or not 1 <= len(choice["store"]) <= 256):
        raise IdentificationError("P26_CURRENT_CHOICE_REQUIRED")
    ca = Path(state["ca_directory"])
    development_binding = state.get("development_ca")
    if development_binding is not None:
        from .development_transport import validate_development_ca
        from .p26_transport_preparation import TransportPreparationError
        if (type(development_binding) is not dict
                or set(development_binding) != {"schema_version", "store_root"}
                or development_binding.get("schema_version") != "development-ca-binding/v1"):
            raise IdentificationError("P26_DEDICATED_CA_INVALID")
        store_root = Path(development_binding["store_root"])
        if store_root.parent != root.parent or store_root.name != "development-transport":
            raise IdentificationError("P26_DEDICATED_CA_INVALID")
        try:
            registry = validate_development_ca(store_root)
        except TransportPreparationError:
            raise IdentificationError("P26_DEDICATED_CA_INVALID") from None
        if (registry["ca_directory"] != str(ca)
                or registry["ca_directory_identity"] != state["ca_directory_identity"]
                or registry["certificate_common_name"] != state.get("ca_common_name")):
            raise IdentificationError("P26_DEDICATED_CA_INVALID")
    elif ca.parent != root:
        raise IdentificationError("P26_DEDICATED_CA_INVALID")
    if ca.is_symlink() or not ca.name.startswith("p26_transport_"):
        raise IdentificationError("P26_DEDICATED_CA_INVALID")
    metadata = ca.stat()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or list((metadata.st_dev, metadata.st_ino)) != state["ca_directory_identity"]
            or set(os.listdir(ca)) != set(_FILES)):
        raise IdentificationError("P26_DEDICATED_CA_INVALID")
    for filename in _FILES:
        metadata = (ca / filename).lstat()
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > 65536):
            raise IdentificationError("P26_DEDICATED_CA_INVALID")
    pid = _selected_pid(root, monitoring)
    _helper_restart_scope(state, root, pid)
    return state, choice, pid


class EventOutput:
    """Ordered nonblocking JSON lines; stdin and stdout may share a TTY FD."""

    def __init__(self, loop, fd: int, on_failure):
        self.loop, self.fd, self.on_failure = loop, fd, on_failure
        self.pending = bytearray()
        self.idle = asyncio.Event()
        self.idle.set()
        self.failed = self.watching = False
        self.total_bytes = 0
        self.file_byte_limit = (MAX_DIAGNOSTIC_QUEUE
                               if stat.S_ISREG(os.fstat(fd).st_mode) else None)

    def _unwatch(self):
        if self.watching:
            self.loop.remove_writer(self.fd)
            self.watching = False

    def _fail(self):
        self.failed = True
        self.pending.clear()
        self._unwatch()
        self.idle.set()
        self.on_failure()

    def send(self, document: dict) -> None:
        if self.failed:
            return
        data = (json.dumps(document, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")
        if (len(self.pending) + len(data) > MAX_DIAGNOSTIC_QUEUE
                or self.file_byte_limit is not None
                and self.total_bytes + len(data) > self.file_byte_limit):
            self._fail()
            return
        self.total_bytes += len(data)
        self.pending.extend(data)
        self.idle.clear()
        self._pump()

    def _pump(self):
        while self.pending and not self.failed:
            try:
                written = os.write(self.fd, self.pending)
                if written <= 0:
                    self._fail()
                    return
                del self.pending[:written]
            except BlockingIOError:
                if not self.watching:
                    try:
                        self.loop.add_writer(self.fd, self._pump)
                        self.watching = True
                    except (OSError, ValueError):
                        self._fail()
                return
            except OSError:
                self._fail()
                return
        if not self.pending:
            self._unwatch()
            self.idle.set()

    async def finish(self, timeout: float = 5) -> bool:
        try:
            await asyncio.wait_for(self.idle.wait(), timeout)
        except asyncio.TimeoutError:
            self._fail()
        return not self.failed


def _emit(document: dict) -> None:
    if _event_output is not None:
        _event_output.send(document)
    else:
        print(json.dumps(document, ensure_ascii=True, separators=(",", ":")), flush=True)


def _inactive_spec(pid: int) -> str:
    # Include then exclude the same PID is false for every process. Unlike
    # an empty protobuf message, it survives the macOS 0.12.11 IPC decoder.
    if type(pid) is not int or pid <= 0:
        raise IdentificationError("P26_LOCAL_STATE_INVALID")
    return f"{pid},!{pid}"


async def _observe_receiver_close(server, window: IdentificationWindow) -> None:
    try:
        await server.wait_closed()
    except asyncio.CancelledError:
        return
    except Exception:
        pass
    if window.state != "CLOSED":
        window.close("P26_RECEIVER_LOST")


def _update_state(root: Path, state: dict, window: IdentificationWindow) -> None:
    is_result=getattr(window,"phase",None)=="RESULT"
    state = {**state, "identification_attempts": state["identification_attempts"] + (0 if is_result else window.attempts),
             "result_attempts":state["result_attempts"]+(window.attempts if is_result else 0),
             "live_capture_latch": "OPEN" if window.state == "ACTIVE" else "CLOSED",
             "execution_latch": "OPEN" if is_result and window.state=="ACTIVE" else "CLOSED"}
    name = "transport-state-" + uuid4().hex + ".tmp"
    _write_new(root, name, state)
    os.replace(root / name, root / "transport-state.json")


class ForwardingDiagnostics:
    """Fixed, saturating hook counts; never consult an error or payload."""

    COUNTERS = (
        "selected_tls_hellos", "ignored_tls_hellos",
        "selected_client_tls_established", "selected_server_tls_established",
        "selected_client_tls_failed", "selected_server_tls_failed",
        "upstream_connect_started", "upstream_connected", "upstream_connect_failed",
        "selected_upstream_connect_failed", "http_requests", "http_responses", "http_failed",
        "opaque_tcp_layers", "opaque_udp_layers", "dispatch_exceptions",
        "async_exceptions", "engine_errors",
    )

    def __init__(self, window):
        self.window = window
        self.counts = dict.fromkeys(self.COUNTERS, 0)
        self.counts_at_least = False
        self.last_failure = None
        self.upstream_tls_failure = None

    def note(self, key):
        self.counts_at_least |= self.counts[key] >= 128
        self.counts[key] = min(self.counts[key] + 1, 128)

    def fail(self, key, code, *, close_window=True):
        self.note(key)
        if self.window.state != "CLOSED":
            self.last_failure = code
            if close_window:
                self.window.close(code)

    def loop_exception(self, _loop, _context):
        # The loop context can contain private exception text and connection
        # objects. Do not enumerate it, stringify it or inspect any values.
        self.fail("async_exceptions", "P26_FORWARDING_ASYNC_EXCEPTION")

    def snapshot(self, gate):
        return {"schema_version": "p26-forwarding-diagnostic/v1", **self.counts,
                "counts_at_least": self.counts_at_least,
                "active_streams": gate.concurrent, "peak_active_streams": gate.peak_concurrent,
                "last_failure": self.last_failure,
                "upstream_tls_failure": self.upstream_tls_failure}


class _EngineFailureHandler(logging.Handler):
    def __init__(self, diagnostic):
        super().__init__(logging.ERROR)
        self.diagnostic = diagnostic

    def emit(self, record):
        # mitmproxy catches some layer/addon exceptions and reports them only
        # to these loggers. Use severity alone, without formatting the record.
        if record.levelno >= logging.ERROR:
            self.diagnostic.fail("engine_errors", "P26_FORWARDING_ENGINE_ERROR")


def _capture_engine_failures(diagnostic):
    saved = []
    handler = _EngineFailureHandler(diagnostic)
    for name in ("mitmproxy.proxy.server", "mitmproxy.addonmanager"):
        logger = logging.getLogger(name)
        saved.append((logger, logger.handlers[:], logger.level, logger.propagate, logger.disabled))
        logger.handlers = [handler]
        logger.setLevel(logging.ERROR)
        logger.propagate = logger.disabled = False
    old_disabled = logging.root.manager.disable
    logging.disable(logging.NOTSET)

    def restore():
        logging.disable(old_disabled)
        for logger, handlers, level, propagate, disabled in saved:
            logger.handlers = handlers
            logger.setLevel(level)
            logger.propagate, logger.disabled = propagate, disabled
        handler.close()

    return restore


# A live applet reconnects with far more than 64 sockets. Continuous capture
# accepts that burst. Timed trials keep the original small cap.
CONTINUOUS_STREAM_LIMIT = 256
TIMED_STREAM_LIMIT = 64


class PIDStreamGate:
    """Check kernel-reported PID before any stream bytes/protocol processing."""

    def __init__(self, window: IdentificationWindow, pid: int, dispatch, replacement=None, diagnostic=None):
        self.window, self.pid, self.dispatch = window, pid, dispatch
        self.replacement = replacement
        self.accepted = 0
        self.accepted_at_least = False
        self.concurrent = 0
        self.peak_concurrent = 0
        self.diagnostic = diagnostic

    async def __call__(self, stream):
        if not self.window.active():
            stream.close()
            return
        kernel_pid = stream.get_extra_info("pid", None)
        if kernel_pid != self.pid:
            try:
                if self.replacement is None:
                    raise IdentificationError("P26_NETWORK_OWNER_UNCONFIRMED")
                self.replacement.accept(kernel_pid)
                self.pid = kernel_pid
            except Exception:
                self.window.close("P26_STREAM_PID_UNCONFIRMED")
                stream.close()
                return
        # Continuous capture keeps the applet's reconnect burst. Only a timed
        # trial ends at its small cap; past the continuous cap the session stays up.
        limit = CONTINUOUS_STREAM_LIMIT if self.window.duration_seconds is None else TIMED_STREAM_LIMIT
        if self.concurrent >= limit or (self.window.duration_seconds is not None and self.accepted >= TIMED_STREAM_LIMIT):
            if self.window.duration_seconds is None:
                self.accepted_at_least = True
                stream.close()
                return
            self.window.close("P26_STREAM_COUNT_LIMIT")
            stream.close()
            return
        self.accepted_at_least |= self.accepted >= TIMED_STREAM_LIMIT
        self.accepted = min(self.accepted + 1, TIMED_STREAM_LIMIT)
        self.concurrent += 1
        self.peak_concurrent = max(self.peak_concurrent, self.concurrent)
        try:
            await self.dispatch(stream)
        except asyncio.CancelledError:
            self.window.close("P26_CANCELLED")
            stream.close()
            raise
        except Exception:
            if self.diagnostic is not None:
                self.diagnostic.fail("dispatch_exceptions", "P26_FORWARDING_EXCEPTION")
            else:
                self.window.close("P26_FORWARDING_EXCEPTION")
            stream.close()
        finally:
            self.concurrent -= 1


class IdentificationAddon:
    """Scoped streaming inspection; no cookies, full URLs or header maps."""

    def __init__(self, window: IdentificationWindow, *, batch_public_json: bool = False,
                 detached_analysis: bool = True):
        self.window = window
        self.analysis = None
        self.transport_window = window
        if detached_analysis:
            from .detached_analysis import DetachedAnalysis
            self.transport_window = IdentificationWindow(window.expected_store,
                clock=window.clock, duration_seconds=window.duration_seconds)
            self.transport_window.window_ref = window.window_ref
            self.transport_window.phase = getattr(window, 'phase', None)
            self.transport_window.allowed_domains = set(window.allowed_domains)
            if window.state == 'ACTIVE':
                self.transport_window.start_once()
            self.analysis = DetachedAnalysis(window)
        self.batch_public_json = batch_public_json
        self.route_slots: dict[str, int | None] = {}
        self.reported_domains: set[int] = set()
        self.reported_routes: set[int] = set()
        self.reported_observations = 0
        self.tls_failures = 0
        self.connections = 0
        self.forwarding = ForwardingDiagnostics(self.transport_window)
        from .forwarding_http_progress import ForwardingHTTPProgress
        self.http_progress = ForwardingHTTPProgress()
        from .p26_request_metadata import RequestBudget
        self.request_budget = RequestBudget(window)
        self.request_layouts = []
        self.request_refs = {}
        self.full_capture = None

    def _admission(self, *, count_skip=True):
        return self.analysis.admission(count_skip=count_skip) if self.analysis else nullcontext(True)

    def _stream(self, collector):
        return self.analysis.stream(collector) if self.analysis else collector.feed

    def finish_analysis(self, code='P26_IDENTIFICATION_CLOSED'):
        if self.analysis:
            self.analysis.finish(code)

    def _forwarding_flow_failed(self, counter, code, *, response_not_started=False):
        # The engine owns the failed connection. A per-connection error must
        # not make the PID gate reject every other connection in the window.
        # Reject incomplete inspection data separately from transport lifetime.
        self.forwarding.fail(counter, code, close_window=self.analysis is None)
        if self.analysis:
            if response_not_started:
                self.analysis.note_missing_response()
            else:
                self.analysis.reject_transport_copy()

    def diagnostic(self):
        if not self.analysis:
            return self.window.diagnostic()
        result = self.analysis.snapshot()
        # The parser can stop while the transport still forwards. Never report
        # CLOSED latches merely because a copied observation was rejected.
        control = self.transport_window
        result.update(state=control.state, started_at=control.started_at,
                      closed_at=control.closed_at,
                      live_capture_latch='OPEN' if control.state == 'ACTIVE' else 'CLOSED',
                      execution_latch='OPEN' if control.state == 'ACTIVE' and
                      getattr(self.window, 'phase', None) == 'RESULT' else 'CLOSED')
        return result

    def client_connected(self, client):
        if not self.transport_window.active():
            return
        self.connections += 1
        limit = CONTINUOUS_STREAM_LIMIT if self.transport_window.duration_seconds is None else 32
        if self.connections > limit:
            if self.transport_window.duration_seconds is None:
                self.connections = limit
                return
            self.transport_window.close("P26_CONNECTION_BUDGET")

    def client_disconnected(self, client):
        self.connections = max(0, self.connections - 1)

    def next_layer(self, nextlayer):
        # Never decrypt UDP/QUIC or classify plaintext payloads. These bypass
        # the HTTP inspection path as opaque streams, without message storage.
        from mitmproxy.proxy.layers import TCPLayer, UDPLayer
        context = nextlayer.context
        if context.client.transport_protocol == "udp":
            nextlayer.layer = UDPLayer(context, ignore=True)
            self.forwarding.note("opaque_udp_layers")
        elif len(context.layers) == 1:
            prefix = nextlayer.data_client()[:3]
            if len(prefix) >= 3 and not prefix.startswith(b"\x16\x03"):
                nextlayer.layer = TCPLayer(context, ignore=True)
                self.forwarding.note("opaque_tcp_layers")

    def _remember_domain(self, host):
        window = self.window
        if not window.active() or type(host) is not str or host.lower() in window.domains:
            return
        if len(window.domains) >= 64:
            return
        slot = window.domain(host)
        if slot is not None and slot not in self.reported_domains:
            self.reported_domains.add(slot)
            _emit({"event": "P26_DOMAIN_METADATA", "slot": slot, "domain": window.domains[slot]})

    def tls_clienthello(self, data):
        host = data.client_hello.sni
        if self.full_capture is not None:
            from .p29_full_capture import passthrough_sni
            data.ignore_connection = not self.transport_window.active() or passthrough_sni(host)
            if self.transport_window.state == "ACTIVE":
                self.forwarding.note("ignored_tls_hellos" if data.ignore_connection else "selected_tls_hellos")
                if not data.ignore_connection:
                    self._remember_domain(host)
            return
        with self._admission(count_skip=False) as admitted:
            if admitted:
                slot = self.window.domain(host)
                if slot is not None and slot not in self.reported_domains:
                    self.reported_domains.add(slot)
                    _emit({"event": "P26_DOMAIN_METADATA", "slot": slot, "domain": self.window.domains[slot]})
        data.ignore_connection = not self.transport_window.active() or host not in self.transport_window.allowed_domains
        if self.transport_window.state == "ACTIVE":
            self.forwarding.note("ignored_tls_hellos" if data.ignore_connection else "selected_tls_hellos")

    def tls_established_client(self, data):
        if self.transport_window.active() and data.context.client.sni in self.transport_window.allowed_domains:
            self.forwarding.note("selected_client_tls_established")

    def tls_established_server(self, data):
        if self.transport_window.active() and data.context.client.sni in self.transport_window.allowed_domains:
            self.forwarding.note("selected_server_tls_established")

    def tls_failed_server(self, data):
        if self.transport_window.active() and data.context.client.sni in self.transport_window.allowed_domains:
            from .upstream_tls_diagnostic import upstream_tls_failure_metadata
            self.forwarding.upstream_tls_failure = upstream_tls_failure_metadata(data)
            self._forwarding_flow_failed("selected_server_tls_failed", "P26_FORWARDING_SERVER_TLS_FAILED")

    def server_connect(self, _data):
        if self.transport_window.active():
            self.forwarding.note("upstream_connect_started")

    def server_connected(self, _data):
        if self.transport_window.active():
            self.forwarding.note("upstream_connected")

    def server_connect_error(self, data):
        if self.transport_window.active():
            self.forwarding.note("upstream_connect_failed")
            if data.client.sni in self.transport_window.allowed_domains:
                self._forwarding_flow_failed("selected_upstream_connect_failed", "P26_FORWARDING_CONNECT_FAILED")

    def tls_failed_client(self, data):
        if self.transport_window.active():
            self.tls_failures = min(self.tls_failures + 1, 64)
            _emit({"event": "P26_TLS_CLIENT_FAILED", "count": self.tls_failures})
            if data.context.client.sni in self.transport_window.allowed_domains:
                self._forwarding_flow_failed("selected_client_tls_failed", "P26_FORWARDING_CLIENT_TLS_FAILED")

    def requestheaders(self, flow):
        self.forwarding.note("http_requests")
        if self.full_capture is not None and self.transport_window.active():
            self.full_capture.open_request(flow)
            flow.request.stream = self.full_capture.request_stream(flow.id)
            return
        flow.request.stream = True
        with self._admission() as admitted:
            if admitted:
                self._inspect_requestheaders(flow)
            elif self.transport_window.state == 'ACTIVE' and flow.client_conn.sni in self.transport_window.allowed_domains:
                self.http_progress.begin(flow.id, None)

    def _inspect_requestheaders(self, flow):
        # Query strings/headers are not inspected. Slots retain only the exact
        # query-free route in bounded RAM and expire with this window.
        slot = self.window.route(flow.request.method, flow.request.host, flow.request.path,
                                 tls_domain=flow.client_conn.sni)
        if self.window.state == "ACTIVE" and flow.client_conn.sni in self.window.allowed_domains:
            self.http_progress.begin(flow.id, slot)
        if len(self.route_slots) >= 64:
            self.window.close("P26_CALLBACK_BUDGET")
            return
        self.route_slots[flow.id] = slot
        if slot is not None and slot not in self.reported_routes:
            self.reported_routes.add(slot)
            method, host, path = self.window.routes[slot]
            origin = self.window.route_origins[slot]
            # A TLS metadata hook may have been skipped while the worker held
            # the state lock. Admit this already-selected origin here as well.
            domain_slot = (self.window.domains.index(origin) if origin in self.window.domains
                           else self.window.domain(origin))
            if domain_slot is None:
                return
            try:
                ipaddress.ip_address(host)
                destination_kind = "IP"
            except ValueError:
                destination_kind = "HOSTNAME" if host else "ABSENT"
            _emit({"event": "P26_ROUTE_METADATA", "slot": slot,
                   "method": method, "domain_slot": domain_slot,
                   "destination_host_kind": destination_kind, "destination_equals_tls": host == origin,
                   "path_template": route_template(path)})
            if self.window.public_projection_paths and path in self.window.public_projection_paths and self._business_candidate(slot):
                query = flow.request.path.partition("?")[2].partition("#")[0]
                if len(query) > 8192:
                    self.window.close("P26_STRUCTURE_BUDGET")
                    return
                keys = sorted({unquote(pair.partition("=")[0], errors="strict")
                               for pair in query.split("&") if pair})
                if len(keys) > 128 or any(not key.isascii() or not key.replace("_", "").isalnum() or len(key)>64 for key in keys):
                    self.window.close("P26_STRUCTURE_BUDGET")
                    return
                kind = flow.request.headers.get("content-type", "").partition(";")[0].lower()
                _emit({"event":"P26_REQUEST_FIELD_METADATA", "route_slot":slot, "query_keys":keys,
                       "body_kind":"JSON" if kind=="application/json" else "FORM" if kind=="application/x-www-form-urlencoded" else "OTHER",
                       "field_values_processed":False})
        if slot is not None and self.window.public_projection_paths and self.window.routes[slot][2] in self.window.public_projection_paths and self._business_candidate(slot):
            kind = flow.request.headers.get("content-type", "").partition(";")[0].lower()
            if kind == "application/x-www-form-urlencoded":
                from .p26_request_metadata import begin_form_metadata
                ref = "request:"+uuid4().hex
                self.request_refs[flow.id]=ref
                collector=begin_form_metadata(self.window,self.request_budget,ref,slot,self.request_layouts)
                if collector: flow.request.stream=self._stream(collector)

    def request(self, flow):
        self.http_progress.request_complete(flow.id)

    def responseheaders(self, flow):
        self.forwarding.note("http_responses")
        if self.full_capture is not None and self.transport_window.active():
            keep = self.full_capture.open_response(flow)
            flow.response.stream = self.full_capture.response_stream(flow.id) if keep else True
            return
        # Stream every response. No framework body retention even for ignored
        # routes; only a developer-selected public route gets a bounded copy.
        flow.response.stream = True
        if flow.id in self.http_progress.pending:
            self.http_progress.response_headers(flow.id, flow.response.status_code)
        with self._admission() as admitted:
            if admitted:
                self._inspect_responseheaders(flow)
            else:
                self.route_slots.pop(flow.id, None)
                self.request_refs.pop(flow.id, None)

    def _inspect_responseheaders(self, flow):
        slot = self.route_slots.pop(flow.id, None)
        request_ref = self.request_refs.pop(flow.id,None)
        if not self.window.active() or slot is None:
            self.window.begin_response(None, "identity")
            return
        if getattr(self.window, 'is_store_detail_route', lambda slot: False)(slot):
            kind = flow.response.headers.get('content-type', '').partition(';')[0].strip().lower()
            if (flow.response.status_code != 200 or not (kind == 'application/json'
                    or kind.startswith('application/') and kind.endswith('+json'))):
                self.window.begin_response(None, 'identity')
                return
        if getattr(self.window, 'is_category_route', lambda slot: False)(slot):
            kind = flow.response.headers.get('content-type', '').partition(';')[0].strip().lower()
            is_json = kind == 'application/json' or (kind.startswith('application/') and kind.endswith('+json'))
            if flow.response.status_code != 200 or not is_json:
                self.window.render_inspector._reject('RESPONSE_NOT_JSON', request_ref)
                self.window.begin_response(None, 'identity')
                return
            if not self.window.authorize_category_request(slot, request_ref):
                # Request IDs isolate this shop before any response body is read.
                self.window.begin_response(None, "identity")
                return
        if self.window.key_layout_only and not self._business_candidate(slot):
            self.window.begin_response(None, "identity")
            return
        if slot not in self.window.selected_routes:
            if not self.batch_public_json or not self._business_candidate(slot):
                self.window.begin_response(None, "identity")
                return
            if flow.response.status_code != 200:
                self.window.begin_response(None, "identity")
                return
            kind = flow.response.headers.get("content-type", "").partition(";")[0].strip().lower()
            if kind != "application/json" and not (kind.startswith("application/") and kind.endswith("+json")):
                self.window.begin_response(None, "identity")
                return
            self.window.select_route(slot)
        if flow.response.status_code != 200:
            self.window.begin_response(None, "identity")
            return
        # Read only the encoding needed for the bounded decoder, never headers.
        collector = self.window.begin_response(slot, flow.response.headers.get("content-encoding", "identity"),
                                               source_request_ref=request_ref)
        if collector:
            flow.response.stream = self._stream(collector)

    def _business_candidate(self, slot: int) -> bool:
        # These origins/route functions were observed in this session's route
        # metadata. They are not needed to identify the current store. Other
        # JSON remains a candidate: privacy and actual identity still decide.
        origin = self.window.route_origins[slot]
        if origin in {
            "catfront.dianping.com", "logan-rtl.dreport.meituan.net", "dreport.meituan.net",
            "ops.meituan.com", "lx0.meituan.com", "alita.waimai.meituan.com",
            "portal-portm.meituan.com", "wmdxlwss.meituan.com",
        }:
            return False
        path = self.window.routes[slot][2]
        if self.window.key_layout_only:
            if getattr(self.window, 'is_store_detail_route', lambda slot: False)(slot):
                return True
            if getattr(self.window, 'is_category_route', lambda slot: False)(slot):
                return True
            from .p26_public_projection import is_business_origin
            return (is_business_origin(origin)
                    and self.window.routes[slot][0] == "POST"
                    and path.endswith(("/poi/productlist", "/poi/food")))
        return not (set(path.lower().split("/")) & {
            "abtest", "home", "alitareport", "horn", "log", "metric", "pv", "speed",
        })

    def response(self, flow):
        if self.full_capture is not None:
            self.http_progress.complete(flow.id)
            self.full_capture.finish(flow.id)
            return
        self.http_progress.complete(flow.id)
        # HTTP responses entirely included in their headers can bypass the
        # framework streaming callback. Their content is already empty: do
        # not consult raw_content/content/text as a fallback.
        with self._admission(count_skip=False) as admitted:
            if admitted:
                for row in self.window.observations:
                    if row["slot"] >= self.reported_observations:
                        self.reported_observations = row["slot"] + 1
                        _emit({"event": "P26_VALUE_FREE_OBSERVATION", **row})

    def error(self, flow):
        if self.full_capture is not None:
            self.full_capture.drop(flow.id)
        self.route_slots.pop(flow.id, None)
        self.request_refs.pop(flow.id, None)
        if self.transport_window.active() and flow.client_conn.sni in self.transport_window.allowed_domains:
            phase = self.http_progress.pending.get(flow.id, ('UNKNOWN',))[0]
            self.http_progress.fail(flow.id)
            # A completed request with no response headers has no partial
            # response collector to reject. Its request lease expires normally.
            self._forwarding_flow_failed("http_failed", "P26_FORWARDING_HTTP_FAILED",
                                        response_not_started=phase == 'RESPONSE_HEADERS')

    def clear(self):
        self.http_progress.close()
        self.route_slots.clear()
        self.request_refs.clear()

    def http_progress_snapshot(self):
        return self.http_progress.snapshot(self.transport_window.window_ref, self.transport_window.state)


def _persist_http_progress(root, addon):
    name = "forwarding-http-progress-" + addon.window.window_ref.split(":")[1] + ".json"
    snapshot = addon.http_progress_snapshot()
    try:
        _write_new(root, name, snapshot)
    except Exception:
        # An optional diagnostic artifact must not prevent latch/lock cleanup.
        _emit({"event": "P26_FORWARDING_HTTP_PROGRESS_OUTPUT_INCOMPLETE", **snapshot})
        return None
    _emit({"event": "P26_FORWARDING_HTTP_PROGRESS_CLOSED", "receipt_file": name, **snapshot})
    return name


async def serve(root: Path, *, route_inspection_domains: tuple[str, ...] = (),
                route_domain_suffixes: tuple[str, ...] = (), batch_public_json: bool = False,
                key_layout_only: bool = False, inspect_sensitive_fields: bool = False,
                inspect_public_fields: bool = False, result_profile_control: str | None = None,
                analyze_current_store_batch: bool = False,
                analyze_store_pages: bool = False,
                identify_category_render: bool = False,
                numeric_store_binding: bool = False,
                forward_public_copy: bool = False) -> dict:
    if forward_public_copy:
        from .forwarding_receiver import serve_forwarded
        from .p26_public_projection import BUSINESS_DOMAINS
        if (not all((analyze_store_pages, identify_category_render, numeric_store_binding,
                     batch_public_json, key_layout_only, inspect_sensitive_fields, inspect_public_fields))
                or result_profile_control or analyze_current_store_batch or route_domain_suffixes
                or route_inspection_domains != BUSINESS_DOMAINS):
            raise IdentificationError('P26_ARGUMENTS_INVALID')
        return await serve_forwarded(root)
    # Old launch arguments and historical directories never opt into forwarding.
    return copy_source_unavailable()


def copy_source_unavailable() -> dict:
    """This invocation's status, not a claim about historical process cleanup."""
    return {"code": "P29_COPY_SOURCE_UNAVAILABLE", "state": "NOT_STARTED",
            "input_mode": "COPY_ONLY", "source_ready": False,
            "transport_started": False, "new_attempts": 0,
            "live_capture_latch": "CLOSED", "execution_latch": "CLOSED",
            "product_result": "incomplete"}


class _Arguments(argparse.ArgumentParser):
    def error(self, message):
        raise IdentificationError("P26_ARGUMENTS_INVALID")


def read_result_profile(root,state,name):
    from .p26_result_window import validate_profile
    if (type(name) is not str or not name.startswith("p26-result-profile-") or not name.endswith(".json")
            or Path(name).name!=name or len(name)>96):
        raise IdentificationError("P26_RESULT_PROFILE_INVALID")
    return validate_profile(_read_owned(root/name),state)


def main(argv=None) -> int:
    parser = _Arguments()
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--serve-identification", action="store_true")
    parser.add_argument("--serve-result", action="store_true")
    parser.add_argument("--result-profile-control")
    parser.add_argument("--inspect-current-domain", action="append", default=[])
    parser.add_argument("--inspect-current-domain-suffix", action="append", default=[])
    parser.add_argument("--batch-public-json", action="store_true")
    parser.add_argument("--identify-field-layout-only", action="store_true")
    parser.add_argument("--inspect-sensitive-field-keys", action="store_true")
    parser.add_argument("--inspect-public-fields", action="store_true")
    parser.add_argument("--analyze-current-store-batch", action="store_true")
    parser.add_argument("--analyze-store-pages", action="store_true")
    parser.add_argument("--identify-category-render", action="store_true")
    parser.add_argument("--bind-through-current-numeric-store-ids", action="store_true")
    parser.add_argument("--forward-public-copy", action="store_true")
    forwarded = False
    try:
        args = parser.parse_args(argv)
        forwarded = args.forward_public_copy
        root = Path(args.output_root)
        if args.serve_identification and args.serve_result or args.serve_result and not args.result_profile_control:
            raise IdentificationError("P26_ARGUMENTS_INVALID")
        if args.analyze_current_store_batch and (not args.serve_identification or args.serve_result):
            raise IdentificationError("P26_ARGUMENTS_INVALID")
        if args.analyze_store_pages and (not args.serve_identification or args.serve_result
                                        or args.analyze_current_store_batch):
            raise IdentificationError("P26_ARGUMENTS_INVALID")
        if args.identify_category_render and not args.analyze_store_pages:
            raise IdentificationError('P26_ARGUMENTS_INVALID')
        if args.bind_through_current_numeric_store_ids and not args.analyze_store_pages:
            raise IdentificationError('P26_ARGUMENTS_INVALID')
        if forwarded:
            result = asyncio.run(serve(root,
                route_inspection_domains=tuple(args.inspect_current_domain),
                route_domain_suffixes=tuple(args.inspect_current_domain_suffix),
                batch_public_json=args.batch_public_json,
                key_layout_only=args.identify_field_layout_only,
                inspect_sensitive_fields=args.inspect_sensitive_field_keys,
                inspect_public_fields=args.inspect_public_fields,
                result_profile_control=args.result_profile_control,
                analyze_current_store_batch=args.analyze_current_store_batch,
                analyze_store_pages=args.analyze_store_pages,
                identify_category_render=args.identify_category_render,
                numeric_store_binding=args.bind_through_current_numeric_store_ids,
                forward_public_copy=True))
            return 0 if (result['cleanup'] == 'COMPLETE'
                and result['diagnostic']['code'] in ('P26_HOST_CLOSED', 'P26_START_NOT_REQUESTED', 'P26_WINDOW_TIMEOUT')
                and result['diagnostic_output_complete']) else 2
        _emit(copy_source_unavailable())
        return 2
    except Exception:
        diagnostic = ({'code': 'P29_FORWARDING_ENTRY_FAILED', 'state': 'UNKNOWN',
            'input_mode': 'FORWARDED_COPY',
            'product_result': 'incomplete'} if forwarded else copy_source_unavailable())
        if not forwarded:
            diagnostic["code"] = "P26_ARGUMENTS_INVALID"
        _emit(diagnostic)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
