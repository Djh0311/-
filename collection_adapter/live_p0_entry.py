"""P17 value-free entry policy before any new live source reader is bound."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict

from .contract import CollectionTarget
from .live_execution import LIVE_P0_CAPABILITIES, LiveP0Request


HISTORICAL_TARGET_REF = "TGT-HZ-XCJ-GFTJ-001"
P17_ROUTE_ID = "OWNED_STRUCTURED_EVENT"
P17_SOURCE_KIND = "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE"
P17_SOURCE_PURPOSE = "SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE_P0_VALIDATION"
P17_NETWORK_CAPABILITY = "SINGLE_NETWORK_SOURCE_READ"
P17_FORBIDDEN_CAPABILITIES = (
    "BROWSER_UI",
    "WECHAT_UI",
    "SYSTEM_PROXY",
    "CA_INSTALL_OR_USE",
    "KEYCHAIN",
    "CREDENTIAL_ACCESS",
    "SESSION_ACCESS",
    "TRANSACTION",
)
_BINDING_REF = re.compile(r"^target-binding:[A-Za-z0-9_-]{8,96}$")
_CONFIRMATION_REF = re.compile(r"^target-confirmation:[A-Za-z0-9_-]{8,96}$")


class LiveP0EntryError(ValueError):
    """Closed P17 entry failure with no source locator or raw value."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class HistoricalTargetBinding:
    """An explicit bridge from the stable historical identity to runtime syntax."""

    historical_target_ref: str
    runtime_target: CollectionTarget
    target_binding_ref: str

    def __post_init__(self) -> None:
        if self.historical_target_ref != HISTORICAL_TARGET_REF:
            raise LiveP0EntryError("LIVE_HISTORICAL_TARGET_INVALID")
        if type(self.runtime_target) is not CollectionTarget:
            raise LiveP0EntryError("LIVE_TARGET_BINDING_INVALID")
        if type(self.target_binding_ref) is not str or _BINDING_REF.fullmatch(self.target_binding_ref) is None:
            raise LiveP0EntryError("LIVE_TARGET_BINDING_INVALID")


@dataclass(frozen=True)
class CurrentTargetBinding:
    """Caller attestation for this dispatch's independently confirmed target.

    The opaque confirmation reference must point to the current user choice;
    construction proves syntax only, never source identity or readiness.
    """

    runtime_target: CollectionTarget
    target_binding_ref: str
    target_confirmation_ref: str

    def __post_init__(self) -> None:
        if (
            type(self.runtime_target) is not CollectionTarget
            or type(self.target_binding_ref) is not str
            or _BINDING_REF.fullmatch(self.target_binding_ref) is None
            or type(self.target_confirmation_ref) is not str
            or _CONFIRMATION_REF.fullmatch(self.target_confirmation_ref) is None
        ):
            raise LiveP0EntryError("LIVE_CURRENT_TARGET_BINDING_INVALID")


def bind_current_request(request: LiveP0Request, binding: CurrentTargetBinding) -> Dict[str, object]:
    """Bind a new request without consulting or inserting a historical target."""

    if type(request) is not LiveP0Request or type(binding) is not CurrentTargetBinding:
        raise LiveP0EntryError("LIVE_CURRENT_TARGET_BINDING_INVALID")
    if (
        request.source_kind != P17_SOURCE_KIND
        or request.source_purpose != P17_SOURCE_PURPOSE
        or request.capabilities != LIVE_P0_CAPABILITIES
    ):
        raise LiveP0EntryError("LIVE_P17_SOURCE_POLICY_INVALID")
    if request.target != binding.runtime_target:
        raise LiveP0EntryError("LIVE_TARGET_BINDING_DRIFT")
    return {
        "runtime_target_ref": binding.runtime_target.target_ref,
        "target_binding_ref": binding.target_binding_ref,
        "target_confirmation_ref": binding.target_confirmation_ref,
        "target_confirmation_status": "CALLER_ATTESTED_CURRENT_CHOICE",
        "source_identity_status": "NOT_OBSERVED",
        "route_id": P17_ROUTE_ID,
        "source_kind": P17_SOURCE_KIND,
        "source_purpose": P17_SOURCE_PURPOSE,
        "network_capability": P17_NETWORK_CAPABILITY,
        "forbidden_capabilities": list(P17_FORBIDDEN_CAPABILITIES),
    }


def bind_p17_request(request: LiveP0Request, binding: HistoricalTargetBinding) -> Dict[str, object]:
    """Validate a prospective P17 request without opening a latch or reader."""

    if type(request) is not LiveP0Request or type(binding) is not HistoricalTargetBinding:
        raise LiveP0EntryError("LIVE_P17_REQUEST_INVALID")
    if (
        request.source_kind != P17_SOURCE_KIND
        or request.source_purpose != P17_SOURCE_PURPOSE
        or request.capabilities != LIVE_P0_CAPABILITIES
    ):
        raise LiveP0EntryError("LIVE_P17_SOURCE_POLICY_INVALID")
    if request.target != binding.runtime_target:
        raise LiveP0EntryError("LIVE_TARGET_BINDING_DRIFT")
    return {
        "historical_target_ref": binding.historical_target_ref,
        "historical_target_status": "NOT_OBSERVED",
        "runtime_target_ref": binding.runtime_target.target_ref,
        "target_binding_ref": binding.target_binding_ref,
        "route_id": P17_ROUTE_ID,
        "source_kind": P17_SOURCE_KIND,
        "source_purpose": P17_SOURCE_PURPOSE,
        "network_capability": P17_NETWORK_CAPABILITY,
        "forbidden_capabilities": list(P17_FORBIDDEN_CAPABILITIES),
    }


def source_entry_unavailable_stop() -> Dict[str, object]:
    """Record the zero-attempt P17 conclusion when no new source entry is bound."""

    return {
        "schema_version": "collection-live-p0-entry-stop/v1",
        "stop_code": "LIVE_SOURCE_ENTRY_UNAVAILABLE",
        "historical_target_ref": HISTORICAL_TARGET_REF,
        "historical_target_status": "NOT_OBSERVED",
        "runtime_target_binding": "NOT_BOUND",
        "route_id": P17_ROUTE_ID,
        "source_kind": P17_SOURCE_KIND,
        "source_purpose": P17_SOURCE_PURPOSE,
        "network_capability": P17_NETWORK_CAPABILITY,
        "forbidden_capabilities": list(P17_FORBIDDEN_CAPABILITIES),
        "live_capture_latch": "CLOSED",
        "execution_latch": "CLOSED",
        "source_attempts_consumed": 0,
        "automatic_retry": False,
        "source_material_persisted": False,
        "business_publication_allowed": False,
    }
