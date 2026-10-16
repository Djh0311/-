"""Local preparation entry for one future live window.

The entry checks a developer-supplied destination and, when the developer has
also supplied match parameters, configures the existing one-shot addon. It does
not start a listener, read a callback, create a P15 attempt, or open a product
latch. Real interface, field, parameter, and network facts stay UNKNOWN.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Callable, Mapping

from collection_core import ResultPublishError, precheck_result_destination
from parser_candidate import ParserRegistry

from .contract import CollectionTarget
from .live_execution import MAX_LIVE_WINDOW_SECONDS, LiveP0Request, LiveRequestError
from .live_mitmproxy_addon import P21AddonConfig, P21AddonError, P21LiveConsumer, P21MitmproxyAddon
from .live_p0_entry import CurrentTargetBinding, LiveP0EntryError
from .mitmproxy_bridge import MitmproxyBridgeError, MitmproxySourceEntry, MitmproxySourcePolicy, P21OutputBoundary, _bounded_window


SCHEMA_VERSION = "collection-live-entry-diagnostic/v1"
UNKNOWN_CONDITIONS = (
    "REAL_INTERFACE_RULES",
    "REAL_FIELD_RULES",
    "REAL_REQUEST_PARAMETERS",
    "NETWORK_READINESS",
    "PROXY_STATE",
    "TARGET_PAGE_STATE",
    "PRIVATE_CONFIGURATION",
    "LAST_TIMEOUT_CAUSE",
)
_REQUIRED_REFERENCES = (
    "source_ref",
    "provider_contract_ref",
    "authorization_ref",
    "run_ref",
    "attempt_ref",
    "input_lock_ref",
    "capability_ref",
    "issued_at",
    "expires_at",
)
_CLOSURE_CODES = frozenset(
    {
        "NONE",
        "DEVELOPER_PARAMETERS_MISSING",
        "LIVE_WINDOW_LIMIT",
        "LIVE_INPUT_LOCK_INVALID",
        "LIVE_REQUEST_REFERENCE_INVALID",
        "LIVE_SOURCE_PURPOSE_INVALID",
        "LIVE_SOURCE_PURPOSE_MISMATCH",
        "LIVE_TARGET_INVALID",
        "LIVE_CAPABILITY_INVALID",
        "LIVE_ATTEMPT_POLICY_INVALID",
        "LIVE_PRIVACY_POLICY_INVALID",
        "LIVE_REQUEST_INVALID",
        "LIVE_HISTORICAL_TARGET_INVALID",
        "LIVE_CURRENT_TARGET_BINDING_INVALID",
        "LIVE_TARGET_BINDING_INVALID",
        "LIVE_TARGET_BINDING_DRIFT",
        "LIVE_P17_REQUEST_INVALID",
        "LIVE_P17_SOURCE_POLICY_INVALID",
        "CONFIGURATION_REJECTED",
        "MITMPROXY_BRIDGE_FACTORY_INVALID",
        "MITMPROXY_BRIDGE_FACTORY_USED",
        "MITMPROXY_BRIDGE_WINDOW_LIMIT",
        "RESULT_ROOT_INVALID",
        "RESULT_TARGET_EXISTS",
        "RESULT_INPUT_INVALID",
        "PREPARATION_CANCELLED",
        "P0_PUBLISHED",
        "LIVE_SOURCE_READ_FAILED",
        "LIVE_WORKER_START_FAILED",
        "PREPARATION_ARGUMENTS_INVALID",
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
        "MITMPROXY_BRIDGE_NOT_WAITING",
    }
)
_PARSE_STATUS = frozenset({"NOT_RUN", "RUNNING", "ACCEPTED", "REJECTED", "STOPPED"})
_PUBLISH_STATUS = frozenset({"NOT_RUN", "RUNNING", "PUBLISHED", "REJECTED"})
_OPEN_STATES = frozenset({"UNCONFIGURED", "PREPARED", "WAITING"})


class LivePreparationError(ValueError):
    """Closed preparation failure. The message is the code and nothing else."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LivePreparationSpec:
    """In-memory technical parameters. Omitted match rules stay unknown."""

    output_root: str
    result_name: str
    runtime_target: CollectionTarget | None = None
    target_binding_ref: str | None = None
    source_entry_ref: str | None = None
    output_root_ref: str | None = None
    request_references: Mapping[str, str] | None = None
    now: Callable[[], str] | None = None
    policy: MitmproxySourcePolicy | None = None
    parser_registry: ParserRegistry | None = None
    p0_context_factory: Callable[..., object] | None = None
    current_target_binding: CurrentTargetBinding | None = None

    def __post_init__(self) -> None:
        if self.request_references is None:
            return
        if type(self.request_references) is not dict:
            raise LivePreparationError("LIVE_REQUEST_REFERENCE_INVALID")
        copied: dict[str, str] = {}
        for key, value in self.request_references.items():
            if type(key) is not str or type(value) is not str:
                raise LivePreparationError("LIVE_REQUEST_REFERENCE_INVALID")
            copied[key] = value
        object.__setattr__(self, "request_references", copied)


class LiveEntrySession:
    """One prepare/start/cancel session. Start is never implied by prepare."""

    def __init__(self, spec: LivePreparationSpec, *, require_current_target: bool = False) -> None:
        if type(spec) is not LivePreparationSpec:
            raise LivePreparationError("LIVE_REQUEST_INVALID")
        self._spec = spec
        self._require_current_target = require_current_target
        self._addon: P21MitmproxyAddon | None = None
        self._prepare_once = False
        self._output_precheck = "NOT_RUN"
        self._parameters = "MISSING"
        self._program = "INCOMPLETE"
        self._closure_code = "NONE"
        self._cancelled = False

    def prepare(self) -> None:
        """Validate the local destination and configure the addon when rules exist."""

        if self._prepare_once or self._cancelled:
            return
        self._prepare_once = True
        precheck_code = self._run_precheck()
        parameter_code = self._parameter_code()
        if precheck_code is not None:
            self._close_preparation(precheck_code)
            return
        if parameter_code is not None:
            self._close_preparation(parameter_code)
            return
        try:
            self._configure()
        except (MitmproxyBridgeError, P21AddonError, LiveP0EntryError, LiveRequestError, LivePreparationError) as error:
            self._close_preparation(_known(getattr(error, "code", "")))
            return
        self._program = "COMPLETE"
        self._closure_code = "NONE"

    def start(self) -> bool:
        """Create the one local attempt. Refuses when preparation is incomplete."""

        if self._program != "COMPLETE" or self._addon is None:
            return False
        started = self._addon.start_once()
        if started:
            return True
        facts = self._addon.diagnostic_facts()
        if facts.get("start_requested") is True:
            return False
        code = facts.get("closure_code")
        if code in {"RESULT_ROOT_INVALID", "RESULT_TARGET_EXISTS", "RESULT_INPUT_INVALID"}:
            self._output_precheck = "FAIL"
            self._closure_code = str(code)
        return False

    def cancel(self) -> dict[str, object]:
        """Close this session once. A second cancel does not start a retry."""

        if self._addon is None:
            self._cancelled = True
            self._closure_code = "PREPARATION_CANCELLED"
            return self.diagnostic()
        self._addon.cancel()
        return self.diagnostic()

    def accept_callback(self, flow: object) -> str:
        """Forward one in-process callback. Before start, the flow is not read."""

        if self._addon is None:
            return "MITMPROXY_BRIDGE_NOT_WAITING"
        return self._addon.response(flow)

    def wait_until_receiver(self, timeout: float) -> bool:
        if not _bounded_window(timeout):
            return False
        if self._addon is None:
            return False
        return self._addon.wait_until_waiting(timeout)

    def wait_closed(self, timeout: float) -> bool:
        if not _bounded_window(timeout):
            return False
        if self._addon is None:
            return self._program != "COMPLETE"
        return self._addon.wait_closed(timeout)

    def diagnostic(self) -> dict[str, object]:
        """Closed phases and capped counts. Product latches stay CLOSED."""

        facts = self._facts()
        raw = _count(facts.get("raw_callback_count"))
        matched = _count(facts.get("target_match_count"))
        accepted = _count(facts.get("accepted_event_count"))
        qualified = _count(facts.get("qualified_event_count"), 10000)
        attempts = facts.get("source_attempts_consumed")
        if attempts not in (0, 1):
            attempts = 0
        state = facts.get("state")
        parse_status = facts.get("parse_status")
        publish_status = facts.get("publish_status")
        if parse_status not in _PARSE_STATUS:
            parse_status = "NOT_RUN"
        if publish_status not in _PUBLISH_STATUS:
            publish_status = "NOT_RUN"
        closure = self._public_closure(facts)
        ready = (
            self._program == "COMPLETE"
            and state == "WAITING"
            and facts.get("reader_state") == "WAITING"
            and self._output_precheck == "PASS"
            and closure == "NONE"
        )
        if state == "CLOSED" or self._program != "COMPLETE":
            closure_status = "CLOSED"
        else:
            closure_status = "OPEN"
        return {
            "schema_version": SCHEMA_VERSION,
            "program_preparation": "COMPLETE" if self._program == "COMPLETE" else "INCOMPLETE",
            "real_source_ready": "UNKNOWN",
            "network_readiness": "UNKNOWN",
            "real_interface_rules": "UNKNOWN",
            "real_field_rules": "UNKNOWN",
            "developer_match_parameters": "SUPPLIED" if self._parameters == "SUPPLIED" else "MISSING",
            "field_inventory": "NOT_STARTED",
            "identification_boundary": "P26_AUTHORIZED_WINDOW_ONLY",
            "unknown_conditions": list(UNKNOWN_CONDITIONS),
            "not_started": attempts == 0,
            "receiver_ready": "READY" if ready else "NO",
            "callback_entered": "YES" if raw else "NO",
            "target_matched": "YES" if matched else "NO",
            "events_complete": "YES" if accepted >= 2 else "NO",
            "parse_status": parse_status,
            "publish_status": publish_status,
            "cancel_status": facts.get("cancel_status", "CLOSED" if self._cancelled else "NOT_REQUESTED"),
            "closure_status": closure_status,
            "closure_code": closure,
            "raw_callback_count": raw,
            "target_match_count": matched,
            "qualified_event_count": qualified,
            "source_attempts_consumed": attempts,
            "start_requested": facts.get("start_requested") is True,
            "product_live_capture_latch": "CLOSED",
            "product_execution_latch": "CLOSED",
            "local_receiver_armed": facts.get("reader_state") == "WAITING",
            "automatic_retry": False,
            "output_precheck": self._output_precheck if self._output_precheck in {"NOT_RUN", "PASS", "FAIL"} else "NOT_RUN",
            "local_lease_scope": "NOT_PRODUCT_LATCH",
            "max_window_seconds": MAX_LIVE_WINDOW_SECONDS,
        }

    def _facts(self) -> dict[str, object]:
        if self._addon is None:
            return {
                "state": "UNCONFIGURED",
                "start_requested": False,
                "closure_code": self._closure_code,
                "parse_status": "NOT_RUN",
                "publish_status": "NOT_RUN",
                "qualified_event_count": 0,
                "source_attempts_consumed": 0,
                "raw_callback_count": 0,
                "target_match_count": 0,
                "accepted_event_count": 0,
                "reader_state": None,
            }
        return self._addon.diagnostic_facts()

    def _public_closure(self, facts: Mapping[str, object]) -> str:
        if self._program != "COMPLETE":
            return _known(self._closure_code)
        code = facts.get("closure_code")
        if type(code) is str and code in _CLOSURE_CODES and code != "NONE":
            return code
        if facts.get("publish_status") == "PUBLISHED":
            return "P0_PUBLISHED"
        state = facts.get("state")
        if state in _OPEN_STATES:
            return "NONE"
        return "LIVE_SOURCE_READ_FAILED"

    def _run_precheck(self) -> str | None:
        try:
            precheck_result_destination(self._spec.output_root, self._spec.result_name)
        except ResultPublishError as error:
            self._output_precheck = "FAIL"
            return _known(error.code)
        self._output_precheck = "PASS"
        return None

    def _parameter_code(self) -> str | None:
        spec = self._spec
        if self._require_current_target and type(spec.current_target_binding) is not CurrentTargetBinding:
            self._parameters = "MISSING"
            return "LIVE_CURRENT_TARGET_BINDING_INVALID"
        references = spec.request_references
        supplied = (
            type(spec.policy) is MitmproxySourcePolicy
            and type(spec.parser_registry) is ParserRegistry
            and callable(spec.p0_context_factory)
            and callable(spec.now)
            and type(spec.runtime_target) is CollectionTarget
            and type(spec.target_binding_ref) is str
            and type(spec.source_entry_ref) is str
            and type(spec.output_root_ref) is str
            and type(references) is dict
            and all(name in references for name in _REQUIRED_REFERENCES)
        )
        if not supplied:
            self._parameters = "MISSING"
            return "DEVELOPER_PARAMETERS_MISSING"
        self._parameters = "SUPPLIED"
        if spec.current_target_binding is not None and (
            type(spec.current_target_binding) is not CurrentTargetBinding
            or spec.current_target_binding.runtime_target != spec.runtime_target
            or spec.current_target_binding.target_binding_ref != spec.target_binding_ref
        ):
            return "LIVE_CURRENT_TARGET_BINDING_INVALID"
        assert references is not None
        assert spec.runtime_target is not None
        try:
            LiveP0Request(
                source_purpose="SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE_P0_VALIDATION",
                source_kind="SEPARATELY_AUTHORIZED_STRUCTURED_SOURCE",
                target=spec.runtime_target,
                capabilities=("SINGLE_NETWORK_SOURCE_READ",),
                **{name: references[name] for name in _REQUIRED_REFERENCES},
            )
        except LiveRequestError as error:
            return _known(error.code)
        return None

    def _configure(self) -> None:
        spec = self._spec
        assert spec.policy is not None
        assert spec.runtime_target is not None
        assert spec.target_binding_ref is not None
        assert spec.source_entry_ref is not None
        assert spec.output_root_ref is not None
        assert spec.parser_registry is not None
        assert spec.p0_context_factory is not None
        assert spec.now is not None
        assert spec.request_references is not None
        entry = MitmproxySourceEntry(
            policy=spec.policy,
            runtime_target=spec.runtime_target,
            target_binding_ref=spec.target_binding_ref,
            source_entry_ref=spec.source_entry_ref,
            output_boundary=P21OutputBoundary(spec.output_root_ref),
            current_target_binding=spec.current_target_binding,
        )
        consumer = P21LiveConsumer(
            parser_registry=spec.parser_registry,
            p0_context_factory=spec.p0_context_factory,
            output_root=spec.output_root,
            result_name=spec.result_name,
        )
        references = {name: spec.request_references[name] for name in _REQUIRED_REFERENCES}
        addon = P21MitmproxyAddon()
        if not addon.configure_once(P21AddonConfig(entry, references, spec.now, consumer)):
            raise LivePreparationError("CONFIGURATION_REJECTED")
        self._addon = addon

    def _close_preparation(self, code: str) -> None:
        self._program = "INCOMPLETE"
        self._closure_code = _known(code)


def prepare_live_entry(spec: LivePreparationSpec) -> LiveEntrySession:
    """Prepare one session. The returned object has not called start."""

    session = LiveEntrySession(spec)
    session.prepare()
    return session


def prepare_current_live_entry(spec: LivePreparationSpec) -> LiveEntrySession:
    """P26 preparation: missing current attestation cannot use the legacy path."""

    session = LiveEntrySession(spec, require_current_target=True)
    session.prepare()
    return session


def _known(code: object) -> str:
    if type(code) is str and code in _CLOSURE_CODES:
        return code
    return "CONFIGURATION_REJECTED"


def _count(value: object, cap: int = 8) -> int:
    if type(value) is not int or value < 0:
        return 0
    if value > cap:
        return cap
    return value


class _ClosedArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise LivePreparationError("PREPARATION_ARGUMENTS_INVALID")


def main(argv: list[str] | None = None) -> int:
    """Report local preparation. This command never starts the addon."""

    parser = _ClosedArgumentParser(description="Prepare a local live entry without starting it.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--result-name", required=True)
    try:
        args = parser.parse_args(argv)
    except LivePreparationError:
        session = LiveEntrySession(LivePreparationSpec(output_root="", result_name=""))
        session._close_preparation("PREPARATION_ARGUMENTS_INVALID")
        json.dump(session.diagnostic(), sys.stdout, ensure_ascii=True, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    session = prepare_live_entry(LivePreparationSpec(output_root=args.output_root, result_name=args.result_name))
    diagnostic = session.diagnostic()
    json.dump(diagnostic, sys.stdout, ensure_ascii=True, sort_keys=True)
    sys.stdout.write("\n")
    if diagnostic["output_precheck"] == "FAIL":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
