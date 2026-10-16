"""Pure P15 contract for one caller-authorized live P0 execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from typing import Callable, Dict, Tuple

from .contract import CollectionTarget


_REF_TOKEN = r"[A-Za-z0-9_-]{8,96}"
_SOURCE_PURPOSES = {
    "USER_OWNED_EXPORT_P0_VALIDATION": "USER_OWNED_EXPORT",
    "OFFICIAL_PUBLIC_DATASET_P0_VALIDATION": "OFFICIAL_PUBLIC_DATASET",
    "APPROVED_PUBLIC_DOCUMENT_P0_VALIDATION": "APPROVED_PUBLIC_DOCUMENT",
    "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE_P0_VALIDATION": "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE",
}
LIVE_P0_CAPABILITIES = ("SINGLE_NETWORK_SOURCE_READ",)
MAX_LIVE_WINDOW_SECONDS = 120


class LiveRequestError(ValueError):
    """Closed P15 request failure without user-supplied content."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class LiveExecutionError(ValueError):
    """Closed P15 authority or lease failure without source details."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LiveP0Request:
    """One explicit source purpose and target, with no locator or source material."""

    source_purpose: str
    source_kind: str
    target: CollectionTarget
    source_ref: str
    provider_contract_ref: str
    authorization_ref: str
    run_ref: str
    attempt_ref: str
    input_lock_ref: str
    capability_ref: str
    capabilities: Tuple[str, ...]
    issued_at: str
    expires_at: str
    max_attempts: int = 1
    automatic_retry: bool = False
    source_material_persisted: bool = False

    def __post_init__(self) -> None:
        if self.source_purpose not in _SOURCE_PURPOSES:
            raise LiveRequestError("LIVE_SOURCE_PURPOSE_INVALID")
        if self.source_kind != _SOURCE_PURPOSES[self.source_purpose]:
            raise LiveRequestError("LIVE_SOURCE_PURPOSE_MISMATCH")
        if type(self.target) is not CollectionTarget:
            raise LiveRequestError("LIVE_TARGET_INVALID")
        _validate_ref(self.source_ref, "source")
        _validate_ref(self.provider_contract_ref, "provider-contract")
        _validate_ref(self.authorization_ref, "authorization")
        _validate_ref(self.run_ref, "run")
        _validate_ref(self.attempt_ref, "attempt")
        _validate_ref(self.input_lock_ref, "input-lock")
        _validate_ref(self.capability_ref, "capability")
        if type(self.capabilities) is not tuple or self.capabilities != LIVE_P0_CAPABILITIES:
            raise LiveRequestError("LIVE_CAPABILITY_INVALID")
        if self.max_attempts != 1 or self.automatic_retry is not False:
            raise LiveRequestError("LIVE_ATTEMPT_POLICY_INVALID")
        if self.source_material_persisted is not False:
            raise LiveRequestError("LIVE_PRIVACY_POLICY_INVALID")
        issued = _parse_time(self.issued_at, "LIVE_INPUT_LOCK_INVALID")
        expires = _parse_time(self.expires_at, "LIVE_INPUT_LOCK_INVALID")
        if issued >= expires:
            raise LiveRequestError("LIVE_INPUT_LOCK_INVALID")
        if expires - issued > timedelta(seconds=MAX_LIVE_WINDOW_SECONDS):
            raise LiveRequestError("LIVE_WINDOW_LIMIT")

    def public_contract(self) -> Dict[str, object]:
        """Return the closed, value-free contract projection for later orchestration."""

        return {
            "schema_version": "collection-live-p0-execution-request/v1",
            "source_purpose": self.source_purpose,
            "source_kind": self.source_kind,
            "target_ref": self.target.target_ref,
            "source_ref": self.source_ref,
            "provider_contract_ref": self.provider_contract_ref,
            "authorization_ref": self.authorization_ref,
            "run_ref": self.run_ref,
            "attempt_ref": self.attempt_ref,
            "input_lock_ref": self.input_lock_ref,
            "capability_ref": self.capability_ref,
            "capabilities": list(self.capabilities),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "max_attempts": self.max_attempts,
            "automatic_retry": self.automatic_retry,
            "source_material_persisted": self.source_material_persisted,
        }


class LiveP0ExecutionAuthority:
    """Application-local, one-time latch owner for one frozen P15 request."""

    def __init__(self, request: LiveP0Request) -> None:
        if type(request) is not LiveP0Request:
            raise LiveRequestError("LIVE_REQUEST_INVALID")
        self._request = request
        self._consumed = False
        self._active = False
        self._cancelled = False

    def acquire(self, request: LiveP0Request, *, now: str) -> "LiveP0ExecutionLease":
        """Consume the exact request once and open both local latches for a lease."""

        if type(request) is not LiveP0Request:
            raise LiveExecutionError("LIVE_REQUEST_INVALID")
        if request != self._request:
            raise LiveExecutionError("LIVE_INPUT_DRIFT")
        if self._cancelled:
            raise LiveExecutionError("MITMPROXY_BRIDGE_CANCELLED")
        if self._active:
            raise LiveExecutionError("LIVE_LATCH_ACTIVE")
        if self._consumed:
            raise LiveExecutionError("LIVE_INPUT_LOCK_USED")
        current = _parse_time(now, "LIVE_INPUT_LOCK_INVALID")
        if current >= _parse_time(request.expires_at, "LIVE_INPUT_LOCK_INVALID"):
            raise LiveExecutionError("LIVE_INPUT_LOCK_EXPIRED")
        self._consumed = True
        self._active = True
        return LiveP0ExecutionLease(self, request)

    def snapshot(self) -> Dict[str, object]:
        """Expose only local latch state and the bounded attempt counter."""

        state = "OPEN" if self._active else "CLOSED"
        return {
            "live_capture_latch": state,
            "execution_latch": state,
            "source_attempts_consumed": int(self._consumed),
        }

    def _close(self, lease: "LiveP0ExecutionLease") -> None:
        if lease._authority is not self:
            raise LiveExecutionError("LIVE_LATCH_CLOSED")
        self._active = False

    def cancel(self) -> None:
        """Revoke this instance before publication without creating an attempt."""

        self._cancelled = True
        self._active = False


class LiveP0ExecutionLease:
    """A context-managed capability token that closes both latches on every exit."""

    def __init__(self, authority: LiveP0ExecutionAuthority, request: LiveP0Request) -> None:
        self._authority = authority
        self.request = request
        self._closed = False
        self._refresh_clock: Callable[[], str] | None = None

    def bind_refresh_clock(self, clock: Callable[[], str]) -> None:
        """Remember the caller's clock so a wait can see a later expiry."""

        if self._closed or not callable(clock):
            raise LiveExecutionError("LIVE_INPUT_LOCK_INVALID")
        self._refresh_clock = clock

    def refreshed_now(self) -> str | None:
        """Return a new timestamp, or None when this lease has no refresh clock."""

        clock = self._refresh_clock
        if clock is None:
            return None
        value = clock()
        if type(value) is not str:
            raise LiveRequestError("LIVE_INPUT_LOCK_INVALID")
        return value

    def __enter__(self) -> "LiveP0ExecutionLease":
        return self

    def __exit__(self, _exception_type: object, _exception: object, _traceback: object) -> bool:
        self.close()
        return False

    def require_active(self, *, now: str) -> None:
        """Fail closed at expiry and make future source use impossible for this lease."""

        if self._authority._cancelled:
            self.close()
            raise LiveExecutionError("MITMPROXY_BRIDGE_CANCELLED")
        if self._closed or not self._authority._active:
            raise LiveExecutionError("LIVE_LATCH_CLOSED")
        current = _parse_time(now, "LIVE_INPUT_LOCK_INVALID")
        if current >= _parse_time(self.request.expires_at, "LIVE_INPUT_LOCK_INVALID"):
            self.close()
            raise LiveExecutionError("LIVE_INPUT_LOCK_EXPIRED")

    def close(self) -> None:
        """Idempotently close both application-local latches."""

        if not self._closed:
            self._authority._close(self)
            self._closed = True
            self._refresh_clock = None


def _validate_ref(value: object, prefix: str) -> None:
    if type(value) is not str or re.fullmatch(prefix + ":" + _REF_TOKEN, value) is None:
        raise LiveRequestError("LIVE_REQUEST_REFERENCE_INVALID")


def _parse_time(value: object, code: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise LiveRequestError(code)
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise LiveRequestError(code) from None
