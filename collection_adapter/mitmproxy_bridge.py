"""Passive, one-shot mitmproxy callback bridge with no mitmproxy dependency.

The loader owns addon loading and policy construction.  This module neither
opens a listener nor discovers a source: it only hands one future callback to
the P16 pull reader within the same process.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re
import threading
import time
from typing import Callable, Dict

from .contract import CollectionEvent, CollectionEventBatch, CollectionTarget
from .live_adapter import LiveP0Observation
from .live_execution import (
    LIVE_P0_CAPABILITIES,
    MAX_LIVE_WINDOW_SECONDS,
    LiveExecutionError,
    LiveP0ExecutionAuthority,
    LiveP0ExecutionLease,
    LiveP0Request,
)
from .live_p0_entry import (
    HISTORICAL_TARGET_REF,
    P17_FORBIDDEN_CAPABILITIES,
    P17_NETWORK_CAPABILITY,
    P17_ROUTE_ID,
    P17_SOURCE_KIND,
    P17_SOURCE_PURPOSE,
    CurrentTargetBinding,
    HistoricalTargetBinding,
    bind_current_request,
    bind_p17_request,
)


_REF_TOKEN = r"[A-Za-z0-9_-]{8,96}"
_SOURCE_ENTRY_REF = re.compile(r"^source-entry:" + _REF_TOKEN + r"$")
_OUTPUT_ROOT_REF = re.compile(r"^output-root:" + _REF_TOKEN + r"$")
_BINDING_REF = re.compile(r"^target-binding:" + _REF_TOKEN + r"$")
_STOP_CODES = frozenset(
    {
        "MITMPROXY_BRIDGE_NOT_WAITING",
        "MITMPROXY_BRIDGE_DUPLICATE",
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
        "MITMPROXY_BRIDGE_WINDOW_LIMIT",
        "MITMPROXY_BRIDGE_FACTORY_USED",
        "MITMPROXY_BRIDGE_FACTORY_INVALID",
    }
)
_DIAGNOSTIC_COUNT_CAP = 8
_REQUIRED_ENDPOINTS = frozenset(("FOOD", "PRODUCTLIST"))
_REQUIRED_CALLBACKS = 2


class MitmproxyBridgeError(ValueError):
    """Closed bridge error; it intentionally carries no flow detail."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _bounded_window(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    return 0 <= value <= MAX_LIVE_WINDOW_SECONDS and math.isfinite(value)


@dataclass(frozen=True)
class MitmproxySourcePolicy:
    """Loader-owned in-memory policy for one two-response bridge instance."""

    endpoint_matches: Callable[[str, str, str], bool]
    response_size: Callable[[object], int]
    contains_sensitive: Callable[[object], bool]
    target_matches: Callable[[object, CollectionTarget], bool]
    project: Callable[[object, LiveP0Request], CollectionEventBatch]
    max_response_bytes: int
    max_events: int
    observation_timeout_seconds: float

    def __post_init__(self) -> None:
        if (
            not all(
                callable(item)
                for item in (
                    self.endpoint_matches,
                    self.response_size,
                    self.contains_sensitive,
                    self.target_matches,
                    self.project,
                )
            )
            or type(self.max_response_bytes) is not int
            or self.max_response_bytes < 1
            or type(self.max_events) is not int
            or self.max_events != _REQUIRED_CALLBACKS
        ):
            raise MitmproxyBridgeError("MITMPROXY_BRIDGE_FACTORY_INVALID")
        if not _bounded_window(self.observation_timeout_seconds):
            raise MitmproxyBridgeError("MITMPROXY_BRIDGE_WINDOW_LIMIT")


class MitmproxyCallbackBridge:
    """Two-response callback-to-P16 reader handoff.

    ``response`` is the only addon callback surface.  It reads request routing
    metadata only, never request body, headers, Cookie or session fields, and
    retains neither the flow nor response after projection.  A complete P0
    observation requires exactly one ``FOOD`` event and one ``PRODUCTLIST``
    event from separate future callbacks in the same short waiting window.
    """

    def __init__(self, policy: MitmproxySourcePolicy, runtime_target: CollectionTarget) -> None:
        if type(policy) is not MitmproxySourcePolicy or type(runtime_target) is not CollectionTarget:
            raise MitmproxyBridgeError("MITMPROXY_BRIDGE_FACTORY_INVALID")
        self._policy = policy
        self._target = runtime_target
        self._condition = threading.Condition()
        self._state = "IDLE"
        self._request: LiveP0Request | None = None
        self._deadline = 0.0
        self._observation: LiveP0Observation | None = None
        self._error: str | None = None
        self._callbacks_seen = 0
        self._raw_callback_count = 0
        self._target_match_count = 0
        self._events_by_endpoint: Dict[str, CollectionEvent] = {}
        self._observation_shape: tuple[str, str, str, str, str] | None = None
        self._lease: LiveP0ExecutionLease | None = None
        self._observed_now: str | None = None

    def response(self, flow: object) -> str:
        """Collect one required endpoint callback while P16 is waiting."""

        with self._condition:
            if self._state == "PENDING":
                self._increment_count("_raw_callback_count")
                return self._close_with("MITMPROXY_BRIDGE_DUPLICATE")
            if self._state != "WAITING" or self._request is None:
                return "MITMPROXY_BRIDGE_NOT_WAITING"
            self._increment_count("_raw_callback_count")
            if not self._lock_still_active():
                return self._error or "LIVE_INPUT_LOCK_EXPIRED"
            if time.monotonic() >= self._deadline:
                return self._close_with("MITMPROXY_BRIDGE_TIMEOUT")
            if self._callbacks_seen >= self._policy.max_events:
                return self._close_with("MITMPROXY_BRIDGE_EVENT_BUDGET")
            try:
                request_metadata = flow.request
                method = request_metadata.method
                host = request_metadata.host
                path = request_metadata.path
            except Exception:
                return self._close_with("MITMPROXY_BRIDGE_ENDPOINT_REJECTED")
            try:
                matched = self._policy.endpoint_matches(method, host, path)
            except Exception:
                return self._close_with("MITMPROXY_BRIDGE_ENDPOINT_REJECTED")
            if matched is False:
                return "MITMPROXY_BRIDGE_IGNORED"
            if matched is not True:
                return self._close_with("MITMPROXY_BRIDGE_ENDPOINT_REJECTED")
            try:
                response = flow.response
                response_size = self._policy.response_size(response)
                if type(response_size) is not int or response_size < 0 or response_size > self._policy.max_response_bytes:
                    return self._close_with("MITMPROXY_BRIDGE_RESPONSE_BUDGET")
                if self._policy.contains_sensitive(response) is not False:
                    return self._close_with("MITMPROXY_BRIDGE_SENSITIVE_REJECTED")
                if self._policy.target_matches(response, self._target) is not True:
                    return self._close_with("MITMPROXY_BRIDGE_TARGET_DRIFT")
                self._increment_count("_target_match_count")
                batch = self._policy.project(response, self._request)
                if (
                    type(batch) is not CollectionEventBatch
                    or batch.run_ref != self._request.run_ref
                    or len(batch.events) != 1
                ):
                    return self._close_with("MITMPROXY_BRIDGE_PROJECTION_REJECTED")
                event = batch.events[0]
                if event.endpoint_id not in _REQUIRED_ENDPOINTS:
                    return self._close_with("MITMPROXY_BRIDGE_PROJECTION_REJECTED")
                shape = (
                    batch.read_scope,
                    batch.observation_scope,
                    batch.observed_at,
                    event.payload_family,
                    event.payload_version,
                )
                if self._observation_shape is None:
                    self._observation_shape = shape
                elif self._observation_shape != shape:
                    return self._close_with("MITMPROXY_BRIDGE_PROJECTION_REJECTED")
                if event.endpoint_id in self._events_by_endpoint:
                    return self._close_with("MITMPROXY_BRIDGE_DUPLICATE")
                if any(existing.event_index == event.event_index for existing in self._events_by_endpoint.values()):
                    return self._close_with("MITMPROXY_BRIDGE_PROJECTION_REJECTED")
                self._events_by_endpoint[event.endpoint_id] = event
                self._callbacks_seen += 1
                if self._callbacks_seen > self._policy.max_events:
                    return self._close_with("MITMPROXY_BRIDGE_EVENT_BUDGET")
                if frozenset(self._events_by_endpoint) != _REQUIRED_ENDPOINTS:
                    return "MITMPROXY_BRIDGE_COLLECTED"
                complete_batch = CollectionEventBatch(
                    run_ref=batch.run_ref,
                    read_scope=batch.read_scope,
                    observation_scope=batch.observation_scope,
                    observed_at=batch.observed_at,
                    events=tuple(sorted(self._events_by_endpoint.values(), key=lambda item: item.event_index)),
                )
                observation = LiveP0Observation(complete_batch)
            except Exception:
                return self._close_with("MITMPROXY_BRIDGE_PROJECTION_REJECTED")
            finally:
                # The raw callback objects have no bridge-owned lifetime.
                response = None
                batch = None
            self._events_by_endpoint = {}
            self._observation_shape = None
            self._observation = observation
            self._state = "PENDING"
            self._condition.notify_all()
            return "MITMPROXY_BRIDGE_ACCEPTED"

    def read_once(self, request: LiveP0Request, lease: LiveP0ExecutionLease) -> LiveP0Observation:
        """Wait once for the callback belonging to this exact active request."""

        if type(request) is not LiveP0Request or type(lease) is not LiveP0ExecutionLease:
            raise MitmproxyBridgeError("MITMPROXY_BRIDGE_REQUEST_DRIFT")
        if request.target != self._target or lease.request != request or lease._closed or not lease._authority._active:
            raise MitmproxyBridgeError("MITMPROXY_BRIDGE_REQUEST_DRIFT")
        with self._condition:
            if self._state != "IDLE":
                code = self._error if self._error in _STOP_CODES else "MITMPROXY_BRIDGE_LEASE_CLOSED"
                self._release()
                raise MitmproxyBridgeError(code)
            self._state = "WAITING"
            self._request = request
            self._lease = lease
            self._deadline = time.monotonic() + self._policy.observation_timeout_seconds
            self._condition.notify_all()
            while self._state == "WAITING":
                if not self._lock_still_active():
                    break
                remaining = self._deadline - time.monotonic()
                if remaining <= 0:
                    self._close_with("MITMPROXY_BRIDGE_TIMEOUT")
                    break
                slice_seconds = self._refresh_slice(remaining)
                if slice_seconds <= 0:
                    if self._lock_still_active():
                        self._close_with("MITMPROXY_BRIDGE_LEASE_CLOSED")
                    break
                self._condition.wait(min(remaining, slice_seconds))
            if self._state == "PENDING" and self._observation is not None:
                observation = self._observation
                self._observation = None
                self._request = None
                self._lease = None
                self._state = "CLOSED"
                return observation
            code = self._error or "MITMPROXY_BRIDGE_LEASE_CLOSED"
            self._release()
            raise MitmproxyBridgeError(code)

    def snapshot(self) -> Dict[str, object]:
        """Value-free bridge state for local test and closure verification.

        ``callbacks_seen`` is the bounded count of callbacks consumed by the
        one P15 attempt, not a source value or identifier.
        """

        with self._condition:
            return {
                "state": self._state,
                "pending_callback": self._observation is not None,
                "callbacks_seen": self._callbacks_seen,
            }

    def diagnostic_counts(self) -> Dict[str, int]:
        """Separate raw callbacks, target matches, and accepted endpoint events."""

        with self._condition:
            return {
                "raw_callback_count": self._raw_callback_count,
                "target_match_count": self._target_match_count,
                "accepted_event_count": self._callbacks_seen,
            }

    def cancel(self) -> str:
        """Close this bridge once. Already closed calls stay closed."""

        with self._condition:
            if self._state == "CLOSED":
                return self._error or "MITMPROXY_BRIDGE_CANCELLED"
            return self._close_with("MITMPROXY_BRIDGE_CANCELLED")

    def wait_until_waiting(self, timeout: float) -> bool:
        """Wait for the read side to arm without touching a source or flow."""

        if not _bounded_window(timeout):
            return False
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._state in {"IDLE", "WAITING"}:
                if self._state == "WAITING":
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return False

    def _increment_count(self, name: str) -> None:
        current = getattr(self, name)
        if type(current) is int and current < _DIAGNOSTIC_COUNT_CAP:
            setattr(self, name, current + 1)

    def _lock_still_active(self) -> bool:
        """Re-read the P15 clock. A stale timestamp must not keep the wait open."""

        lease = self._lease
        if lease is None:
            return True
        try:
            current = lease.refreshed_now()
        except Exception:
            self._close_with("MITMPROXY_BRIDGE_LEASE_CLOSED")
            return False
        self._observed_now = current if type(current) is str else None
        if current is None:
            return True
        try:
            lease.require_active(now=current)
        except LiveExecutionError as error:
            code = error.code if error.code in {"LIVE_INPUT_LOCK_EXPIRED", "LIVE_LATCH_CLOSED", "MITMPROXY_BRIDGE_CANCELLED"} else "MITMPROXY_BRIDGE_LEASE_CLOSED"
            self._close_with(code)
            return False
        except Exception:
            self._close_with("MITMPROXY_BRIDGE_LEASE_CLOSED")
            return False
        return True

    def _refresh_slice(self, monotonic_remaining: float) -> float:
        """Cap one wait at the refreshed P15 remainder so expiry is not deferred."""

        current = self._observed_now
        lease = self._lease
        if current is None or lease is None:
            return monotonic_remaining
        try:
            current_at = datetime.strptime(current, "%Y-%m-%dT%H:%M:%SZ")
            expires_at = datetime.strptime(lease.request.expires_at, "%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            return 0
        wall_remaining = (expires_at - current_at).total_seconds()
        if wall_remaining < monotonic_remaining:
            return max(0.0, wall_remaining)
        return monotonic_remaining

    def _close_with(self, code: str) -> str:
        self._error = code
        self._release()
        self._state = "CLOSED"
        self._condition.notify_all()
        return code

    def _release(self) -> None:
        if self._observation is not None:
            self._observation.destroy()
        self._observation = None
        self._events_by_endpoint = {}
        self._observation_shape = None
        self._request = None
        self._lease = None
        self._observed_now = None


@dataclass(frozen=True)
class P21OutputBoundary:
    """Opaque contract for P21's caller-owned 0700 output root."""

    output_root_ref: str
    output_root_mode: str = "0700"

    def __post_init__(self) -> None:
        if type(self.output_root_ref) is not str or _OUTPUT_ROOT_REF.fullmatch(self.output_root_ref) is None or self.output_root_mode != "0700":
            raise MitmproxyBridgeError("MITMPROXY_BRIDGE_FACTORY_INVALID")


@dataclass(frozen=True)
class P21Attempt:
    """Fresh, not-yet-consumed P21 runtime inputs created at the point of use."""

    request: LiveP0Request
    authority: LiveP0ExecutionAuthority
    reader: MitmproxyCallbackBridge
    target_binding: HistoricalTargetBinding | CurrentTargetBinding
    output_boundary: P21OutputBoundary


class MitmproxySourceEntry:
    """P20 binding and the one-use factory for P21's fresh runtime inputs."""

    def __init__(
        self,
        *,
        policy: MitmproxySourcePolicy,
        runtime_target: CollectionTarget,
        target_binding_ref: str,
        source_entry_ref: str,
        output_boundary: P21OutputBoundary,
        current_target_binding: CurrentTargetBinding | None = None,
    ) -> None:
        if (
            type(policy) is not MitmproxySourcePolicy
            or type(runtime_target) is not CollectionTarget
            or type(target_binding_ref) is not str
            or _BINDING_REF.fullmatch(target_binding_ref) is None
            or type(source_entry_ref) is not str
            or _SOURCE_ENTRY_REF.fullmatch(source_entry_ref) is None
            or type(output_boundary) is not P21OutputBoundary
        ):
            raise MitmproxyBridgeError("MITMPROXY_BRIDGE_FACTORY_INVALID")
        if current_target_binding is not None and (
            type(current_target_binding) is not CurrentTargetBinding
            or current_target_binding.runtime_target != runtime_target
            or current_target_binding.target_binding_ref != target_binding_ref
        ):
            raise MitmproxyBridgeError("MITMPROXY_BRIDGE_FACTORY_INVALID")
        self._policy = policy
        self._runtime_target = runtime_target
        self._binding = (
            current_target_binding if current_target_binding is not None
            else HistoricalTargetBinding(HISTORICAL_TARGET_REF, runtime_target, target_binding_ref)
        )
        self._source_entry_ref = source_entry_ref
        self._output_boundary = output_boundary
        self._factory_used = False

    def binding_receipt(self) -> Dict[str, object]:
        """Return P20's value-free, zero-attempt binding receipt."""

        receipt: Dict[str, object] = {
            "schema_version": "collection-mitmproxy-source-entry-binding/v1",
            "historical_target_ref": HISTORICAL_TARGET_REF,
            "historical_target_status": "NOT_OBSERVED",
            "runtime_target_ref": self._runtime_target.target_ref,
            "target_binding_ref": self._binding.target_binding_ref,
            "source_entry_ref": self._source_entry_ref,
            "source_entry_kind": "MITMPROXY_PASSIVE_CALLBACK",
            "route_id": P17_ROUTE_ID,
            "source_kind": P17_SOURCE_KIND,
            "source_purpose": P17_SOURCE_PURPOSE,
            "network_capability": P17_NETWORK_CAPABILITY,
            "forbidden_capabilities": list(P17_FORBIDDEN_CAPABILITIES),
            "output_root_ref": self._output_boundary.output_root_ref,
            "output_root_mode": self._output_boundary.output_root_mode,
            "p21_factory": "IMMEDIATE_FRESH_REQUEST_ONLY",
            "live_capture_latch": "CLOSED",
            "execution_latch": "CLOSED",
            "source_attempts_consumed": 0,
            "automatic_retry": False,
            "source_material_persisted": False,
            "business_publication_allowed": False,
        }
        if type(self._binding) is CurrentTargetBinding:
            receipt.pop("historical_target_ref")
            receipt.pop("historical_target_status")
            receipt["schema_version"] = "collection-mitmproxy-source-entry-binding/v2"
            receipt["target_confirmation_ref"] = self._binding.target_confirmation_ref
            receipt["target_confirmation_status"] = "CALLER_ATTESTED_CURRENT_CHOICE"
            receipt["source_identity_status"] = "NOT_OBSERVED"
            receipt["fresh_factory"] = receipt.pop("p21_factory")
        return receipt

    def create_p21_attempt(self, **references: str) -> P21Attempt:
        """Create exactly one fresh P15 request, authority and passive reader."""

        if self._factory_used:
            raise MitmproxyBridgeError("MITMPROXY_BRIDGE_FACTORY_USED")
        try:
            request = LiveP0Request(
                source_purpose=P17_SOURCE_PURPOSE,
                source_kind=P17_SOURCE_KIND,
                target=self._runtime_target,
                capabilities=LIVE_P0_CAPABILITIES,
                **references,
            )
            if type(self._binding) is CurrentTargetBinding:
                bind_current_request(request, self._binding)
            else:
                bind_p17_request(request, self._binding)
        except Exception:
            raise MitmproxyBridgeError("MITMPROXY_BRIDGE_FACTORY_INVALID") from None
        self._factory_used = True
        return P21Attempt(
            request=request,
            authority=LiveP0ExecutionAuthority(request),
            reader=MitmproxyCallbackBridge(self._policy, self._runtime_target),
            target_binding=self._binding,
            output_boundary=self._output_boundary,
        )
