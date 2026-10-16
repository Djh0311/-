"""Caller-loaded P21 mitmproxy-compatible addon with no mitmproxy dependency.

The addon owns no endpoint, target, payload profile, credentials or system
configuration.  A caller must construct and inject all current policy and P21
references in memory, then manually start the one permitted attempt.
"""

from dataclasses import dataclass
from datetime import datetime
import sys
import threading
from typing import Callable, Dict, Mapping, Optional

_bootstrap_root = None
_bootstrap_added = False
_addon_path = __file__
_suffix = "/collection_adapter/live_mitmproxy_addon.py"
if type(_addon_path) is not str or not _addon_path.endswith(_suffix):
    raise RuntimeError("P21_ADDON_LOCATION_INVALID")
_bootstrap_root = _addon_path[: -len(_suffix)]
if _bootstrap_root not in sys.path:
    sys.path.insert(0, _bootstrap_root)
    _bootstrap_added = True

try:
    from collection_core import (
        P0Context,
        ResultPublishError,
        build_p0_batch,
        precheck_result_destination,
        publish_result_set,
        render_p0_result,
    )
    from parser_candidate import ParserRegistry

    from collection_adapter.live_adapter import LiveAdapterError, LiveP0Adapter, live_adapter_stop_receipt
    from collection_adapter.live_execution import LiveExecutionError, LiveP0Request
    from collection_adapter.mitmproxy_bridge import MitmproxyBridgeError, MitmproxySourceEntry, P21Attempt, _bounded_window
finally:
    if _bootstrap_added:
        if not sys.path or sys.path[0] != _bootstrap_root:
            raise RuntimeError("P21_ADDON_BOOTSTRAP_INVALID")
        del sys.path[0]
del _bootstrap_added, _bootstrap_root



_QUALIFIED_EVENT_CAP = 10000
_ATTEMPT_STOP_CODES = frozenset(
    {
        "LIVE_SOURCE_READ_FAILED",
        "LIVE_ADAPTER_READER_INVALID",
        "LIVE_ADAPTER_OBSERVATION_INVALID",
        "LIVE_ADAPTER_SCOPE_INVALID",
        "LIVE_P0_CONSUMER_REJECTED",
        "LIVE_PARSE_REJECTED",
        "LIVE_PUBLISH_REJECTED",
        "LIVE_INPUT_LOCK_EXPIRED",
        "LIVE_INPUT_LOCK_USED",
        "LIVE_INPUT_DRIFT",
        "MITMPROXY_BRIDGE_ENDPOINT_REJECTED",
        "MITMPROXY_BRIDGE_RESPONSE_BUDGET",
        "MITMPROXY_BRIDGE_EVENT_BUDGET",
        "MITMPROXY_BRIDGE_SENSITIVE_REJECTED",
        "MITMPROXY_BRIDGE_TARGET_DRIFT",
        "MITMPROXY_BRIDGE_PROJECTION_REJECTED",
        "MITMPROXY_BRIDGE_TIMEOUT",
        "MITMPROXY_BRIDGE_REQUEST_DRIFT",
        "MITMPROXY_BRIDGE_LEASE_CLOSED",
        "MITMPROXY_BRIDGE_CANCELLED",
    }
)
_PRECHECK_CODES = frozenset({"RESULT_ROOT_INVALID", "RESULT_TARGET_EXISTS", "RESULT_INPUT_INVALID"})
_FACTORY_CODES = frozenset(
    {
        "MITMPROXY_BRIDGE_FACTORY_INVALID",
        "MITMPROXY_BRIDGE_FACTORY_USED",
        "MITMPROXY_BRIDGE_WINDOW_LIMIT",
    }
)


def _bounded_qualified(result: object) -> int:
    if type(result) is not dict:
        return 0
    records = result.get("business_records")
    if type(records) is not list:
        return 0
    count = len(records)
    if count > _QUALIFIED_EVENT_CAP:
        return _QUALIFIED_EVENT_CAP
    return count


class P21AddonError(ValueError):
    """Closed P21 addon configuration error with no supplied values."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class P21LiveConsumer:
    """Explicit live P0 consume-and-publish policy supplied by the loader."""

    parser_registry: ParserRegistry
    p0_context_factory: Callable[[LiveP0Request], P0Context]
    output_root: str
    result_name: str

    def __post_init__(self) -> None:
        if type(self.parser_registry) is not ParserRegistry or not callable(self.p0_context_factory):
            raise P21AddonError("P21_ADDON_CONFIG_INVALID")
        if type(self.output_root) is not str or type(self.result_name) is not str:
            raise P21AddonError("P21_ADDON_CONFIG_INVALID")

    def consume(self, events: tuple, request: LiveP0Request, _lease: object, *, on_phase: Optional[Callable] = None) -> dict[str, object]:
        """Build and publish only a complete same-observation P0 result."""

        if on_phase is not None:
            on_phase("RUNNING", "NOT_RUN", 0)
        try:
            _lease.require_active(now=_lease.refreshed_now() or request.issued_at)
            context = self.p0_context_factory(request)
            _lease.require_active(now=_lease.refreshed_now() or request.issued_at)
            if type(context) is not P0Context:
                raise LiveAdapterError("LIVE_PARSE_REJECTED")
            result = build_p0_batch(events, self.parser_registry, context)
            rendered = render_p0_result(result)
        except (LiveAdapterError, LiveExecutionError):
            raise
        except Exception:
            raise LiveAdapterError("LIVE_PARSE_REJECTED") from None
        qualified = _bounded_qualified(result)
        if on_phase is not None:
            on_phase("ACCEPTED", "NOT_RUN", qualified)
        _lease.require_active(now=_lease.refreshed_now() or request.issued_at)
        if on_phase is not None:
            on_phase("ACCEPTED", "RUNNING", qualified)
        try:
            return publish_result_set(self.output_root, self.result_name, rendered)
        except Exception:
            error = LiveAdapterError("LIVE_PUBLISH_REJECTED")
            error.qualified_event_count = _bounded_qualified(result)
            raise error from None


@dataclass(frozen=True)
class P21AddonConfig:
    """One complete, caller-supplied in-memory P21 configuration."""

    source_entry: MitmproxySourceEntry
    request_references: Mapping[str, str]
    now: Callable[[], str]
    consumer: P21LiveConsumer
    p15_start_enabled: bool = True

    def __post_init__(self) -> None:
        if (
            type(self.source_entry) is not MitmproxySourceEntry
            or type(self.request_references) is not dict
            or not callable(self.now)
            or type(self.consumer) is not P21LiveConsumer
            or type(self.p15_start_enabled) is not bool
        ):
            raise P21AddonError("P21_ADDON_CONFIG_INVALID")


class P21MitmproxyAddon:
    """Passive addon wrapper that permits exactly one manually started P21 run."""

    def __init__(self) -> None:
        self._config: P21AddonConfig | None = None
        self._attempt: P21Attempt | None = None
        self._thread: threading.Thread | None = None
        self._state = "UNCONFIGURED"
        self._receipt: Dict[str, object] | None = None
        self._lock = threading.Lock()
        self._start_requested = False
        self._cancel_requested = False
        self._cancel_denied = False
        self._closure_code = "NONE"
        self._parse_status = "NOT_RUN"
        self._publish_status = "NOT_RUN"
        self._qualified_event_count = 0

    def configure_once(self, config: P21AddonConfig) -> bool:
        """Accept one explicit policy/configuration without opening a source."""

        with self._lock:
            if self._state != "UNCONFIGURED" or type(config) is not P21AddonConfig:
                return False
            self._config = config
            self._state = "PREPARED"
            return True

    def start_once(self) -> bool:
        """Create the fresh P15 attempt and begin waiting for one future callback."""

        with self._lock:
            if (
                self._state != "PREPARED"
                or self._config is None
                or self._config.p15_start_enabled is not True
            ):
                return False
            try:
                precheck_result_destination(self._config.consumer.output_root, self._config.consumer.result_name)
            except ResultPublishError as error:
                self._closure_code = error.code if error.code in _PRECHECK_CODES else "RESULT_ROOT_INVALID"
                return False
            try:
                attempt = self._config.source_entry.create_p21_attempt(**self._config.request_references)
            except MitmproxyBridgeError as error:
                self._state = "CLOSED"
                self._closure_code = error.code if error.code in _FACTORY_CODES else "CONFIGURATION_REJECTED"
                self._receipt = self._not_started_receipt(self._closure_code)
                return False
            self._attempt = attempt
            self._start_requested = True
            self._closure_code = "NONE"
            self._state = "WAITING"
            try:
                self._thread = threading.Thread(target=self._execute, name="p21-one-shot", daemon=True)
                self._thread.start()
            except Exception:
                attempt.authority.cancel()
                attempt.reader.cancel()
                self._thread = None
                self._state = "CLOSED"
                self._closure_code = "LIVE_WORKER_START_FAILED"
                self._receipt = self._not_started_receipt(self._closure_code)
                return False
            return True

    def response(self, flow: object) -> str:
        """The only mitmproxy callback; it delegates to the injected P20 bridge."""

        with self._lock:
            attempt = self._attempt
        if attempt is None:
            return "MITMPROXY_BRIDGE_NOT_WAITING"
        return attempt.reader.response(flow)

    def cancel(self) -> bool:
        """Close a prepared or waiting addon without opening another attempt."""

        with self._lock:
            attempt = self._attempt
            if self._state in {"UNCONFIGURED", "PREPARED"}:
                self._cancel_requested = True
                self._state = "CLOSED"
                self._closure_code = "PREPARATION_CANCELLED"
                self._receipt = self._not_started_receipt("PREPARATION_CANCELLED")
                return True
            if self._state == "CLOSED":
                return True
            if self._state != "WAITING":
                return False
            if self._publish_status == "RUNNING":
                self._cancel_denied = True
                return False
            self._cancel_requested = True
        if attempt is not None:
            attempt.authority.cancel()
            attempt.reader.cancel()
        self.wait_closed(2)
        return self._state == "CLOSED"

    def diagnostic_facts(self) -> Dict[str, object]:
        """Value-free lifecycle facts. Counts stay capped and carry no source text."""

        with self._lock:
            attempt = self._attempt
            facts: Dict[str, object] = {
                "state": self._state,
                "start_requested": self._start_requested,
                "closure_code": self._closure_code,
                "parse_status": self._parse_status,
                "publish_status": self._publish_status,
                "qualified_event_count": self._qualified_event_count,
                "source_attempts_consumed": 0,
                "cancel_status": "PUBLICATION_IN_PROGRESS" if self._cancel_denied else (
                    "CLOSED" if self._cancel_requested and self._state == "CLOSED" else
                    "REQUESTED" if self._cancel_requested else "NOT_REQUESTED"
                ),
            }
        if attempt is None:
            facts["raw_callback_count"] = 0
            facts["target_match_count"] = 0
            facts["accepted_event_count"] = 0
            facts["reader_state"] = None
            return facts
        facts.update(attempt.reader.diagnostic_counts())
        facts["reader_state"] = attempt.reader.snapshot()["state"]
        facts["source_attempts_consumed"] = int(attempt.authority.snapshot()["source_attempts_consumed"])
        return facts

    def wait_closed(self, timeout: float) -> bool:
        """Wait locally for the one worker to close; no polling or I/O occurs."""

        if not _bounded_window(timeout):
            return False
        thread = self._thread
        if thread is None:
            return self._state == "CLOSED"
        thread.join(timeout)
        return not thread.is_alive() and self._state == "CLOSED"

    def wait_until_waiting(self, timeout: float) -> bool:
        """Wait for the P20 reader to be ready for one future callback."""

        if not _bounded_window(timeout):
            return False
        thread = self._thread
        if thread is None:
            return False
        thread.join(0)
        if not thread.is_alive():
            return False
        attempt = self._attempt
        if attempt is None:
            return False
        return attempt.reader.wait_until_waiting(timeout)

    def readiness(self) -> Dict[str, object]:
        """Return a zero-attempt readiness declaration before a P15 window starts.

        ``PREPARED`` only confirms that caller-owned in-memory configuration was
        accepted. It never makes a source read eligible and cannot inspect a
        callback. ``WAITING`` appears only after ``start_once`` creates P15.
        """

        snapshot = self.snapshot()
        return {
            "state": snapshot["state"],
            "source_attempts_consumed": snapshot["source_attempts_consumed"],
            "live_capture_latch": snapshot["live_capture_latch"],
            "execution_latch": snapshot["execution_latch"],
            "source_read_allowed": snapshot["reader_state"] == "WAITING" and snapshot["live_capture_latch"] == "OPEN",
            "p15_start_available": (
                snapshot["state"] == "PREPARED"
                and self._config is not None
                and self._config.p15_start_enabled is True
            ),
        }

    def snapshot(self) -> Dict[str, object]:
        """Value-free lifecycle snapshot; it never exposes source or output values."""

        with self._lock:
            if self._attempt is None:
                attempts = 0
                capture_latch = "CLOSED"
                execution_latch = "CLOSED"
                reader_state = None
            else:
                authority = self._attempt.authority.snapshot()
                attempts = authority["source_attempts_consumed"]
                capture_latch = authority["live_capture_latch"]
                execution_latch = authority["execution_latch"]
                reader_state = self._attempt.reader.snapshot()["state"]
            return {
                "state": self._state,
                "source_attempts_consumed": attempts,
                "live_capture_latch": capture_latch,
                "execution_latch": execution_latch,
                "reader_state": reader_state,
                "receipt": self._receipt,
            }

    def _execute(self) -> None:
        assert self._config is not None and self._attempt is not None
        with self._lock:
            if self._cancel_requested:
                self._closure_code = "PREPARATION_CANCELLED"
                self._receipt = self._not_started_receipt("PREPARATION_CANCELLED")
                self._state = "CLOSED"
                return
        attempt = self._attempt
        parse_status = "NOT_RUN"
        publish_status = "NOT_RUN"
        qualified = 0
        try:
            adapter = LiveP0Adapter(attempt.reader)
            result = adapter.execute_once(
                attempt.request,
                attempt.authority,
                now=self._config.now,
                consume=self._consume,
            )
            count = result.get("record_count") if type(result) is dict else None
            if type(count) is not int or count < 1:
                raise LiveAdapterError("LIVE_PUBLISH_REJECTED")
            parse_status = "ACCEPTED"
            publish_status = "PUBLISHED"
            qualified = min(count, _QUALIFIED_EVENT_CAP)
            closure = "P0_PUBLISHED"
            receipt: Dict[str, object] = {
                "schema_version": "collection-live-p0-run-receipt/v1",
                "outcome": "P0_PUBLISHED",
                "run_ref": attempt.request.run_ref,
                "attempt_ref": attempt.request.attempt_ref,
                "source_attempt_consumed": 1,
                "automatic_retry": False,
                "source_material_persisted": False,
                "business_publication_allowed": True,
                "live_capture_latch": "CLOSED",
                "execution_latch": "CLOSED",
                "result_published": True,
                "result_record_count": count,
            }
        except (LiveAdapterError, LiveExecutionError, MitmproxyBridgeError, P21AddonError) as error:
            closure = error.code if getattr(error, "code", "") in _ATTEMPT_STOP_CODES else "LIVE_SOURCE_READ_FAILED"
            parse_status = "STOPPED" if self._parse_status == "RUNNING" else self._parse_status
            publish_status = self._publish_status
            qualified = self._qualified_event_count
            if closure == "LIVE_PARSE_REJECTED":
                parse_status = "REJECTED"
            elif closure == "LIVE_PUBLISH_REJECTED":
                parse_status = "ACCEPTED"
                publish_status = "REJECTED"
                reported = getattr(error, "qualified_event_count", 0)
                qualified = reported if type(reported) is int and 0 <= reported <= _QUALIFIED_EVENT_CAP else 0
            receipt = self._attempt_receipt(attempt, closure)
        except Exception:
            closure = "LIVE_SOURCE_READ_FAILED"
            receipt = self._attempt_receipt(attempt, closure)
        with self._lock:
            self._parse_status = parse_status
            self._publish_status = publish_status
            self._qualified_event_count = qualified
            self._closure_code = closure
            self._receipt = receipt
            self._state = "CLOSED"

    def _consume(self, events: tuple, request: LiveP0Request, lease: object) -> dict[str, object]:
        assert self._config is not None
        return self._config.consumer.consume(events, request, lease, on_phase=self._record_phase)

    def _record_phase(self, parse: str, publish: str, qualified: int) -> None:
        with self._lock:
            if publish == "RUNNING" and self._cancel_requested:
                raise LiveExecutionError("MITMPROXY_BRIDGE_CANCELLED")
            self._parse_status = parse
            self._publish_status = publish
            self._qualified_event_count = qualified

    def _attempt_receipt(self, attempt: P21Attempt, code: str) -> Dict[str, object]:
        consumed = int(attempt.authority.snapshot()["source_attempts_consumed"])
        if consumed == 1 and code in _ATTEMPT_STOP_CODES:
            return live_adapter_stop_receipt(attempt.request, code)
        return self._not_started_receipt(code)

    def _not_started_receipt(self, code: str) -> Dict[str, object]:
        return {
            "schema_version": "collection-live-p0-not-started/v1",
            "outcome": "NOT_STARTED",
            "stop_code": code,
            "source_attempt_consumed": 0,
            "automatic_retry": False,
            "source_material_persisted": False,
            "business_publication_allowed": False,
            "live_capture_latch": "CLOSED",
            "execution_latch": "CLOSED",
            "result_published": False,
        }


addons = [P21MitmproxyAddon()]


def configured_addon(config: P21AddonConfig) -> P21MitmproxyAddon:
    """Build one configured addon for a caller-owned private companion script.

    This deliberately does not start an attempt. The companion must call
    ``start_once`` after its user has manually loaded that private script.
    """

    addon = P21MitmproxyAddon()
    if not addon.configure_once(config):
        raise P21AddonError("P21_ADDON_CONFIG_INVALID")
    return addon
