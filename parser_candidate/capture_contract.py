"""Offline event contract between a capture adapter and the Parser candidate."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping

from .envelope import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    SanitizedObservationInput,
)
from .parser import ParserError, _safe_version_token
from .registry import ParserRegistry, parse_food_sanitized, parse_sanitized


EVENT_SCHEMA_VERSION = "mitmproxy-parser-event/v2"
OFFLINE_READ_SCOPE_RUNNER_CONTRACT = "offline-read-scope-runner/v2"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_ENDPOINTS = frozenset(("FOOD", "PRODUCTLIST"))
_EVENT_KEYS = frozenset(
    (
        "schema_version",
        "read_scope",
        "observation_scope",
        "event_index",
        "endpoint_id",
        "payload_family",
        "payload_version",
        "payload",
    )
)


def _safe_token(value: object) -> bool:
    return type(value) is str and _TOKEN.fullmatch(value) is not None


def make_adapter_event(
    *,
    read_scope: str,
    observation_scope: str,
    event_index: int,
    endpoint_id: str,
    payload_family: str,
    payload_version: str,
    payload: Mapping[str, Any],
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> dict[str, Any]:
    """Build one exact v2 event model from an already-decoded payload.

    The caller must supply the observation boundary explicitly. This helper
    performs no inference, I/O, or access to request/response objects.
    """

    event = CaptureParserEvent(
        read_scope=read_scope,
        observation_scope=observation_scope,
        event_index=event_index,
        endpoint_id=endpoint_id,
        payload_family=payload_family,
        payload_version=payload_version,
        payload=payload,
        max_depth=max_depth,
        max_nodes=max_nodes,
    )
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "read_scope": event.read_scope,
        "observation_scope": event.observation_scope,
        "event_index": event.event_index,
        "endpoint_id": event.endpoint_id,
        "payload_family": event.payload_family,
        "payload_version": event.payload_version,
        "payload": event.to_observation_input().payload,
    }


@dataclass(frozen=True)
class CaptureParserEvent:
    """One response event handed from an adapter to one Parser invocation.

    ``payload`` is copied and validated into the event's private in-memory
    envelope.  The object intentionally has no serialization or merge API.
    """

    read_scope: str
    observation_scope: str
    event_index: int
    endpoint_id: str
    payload_family: str
    payload_version: str
    payload: Mapping[str, Any]
    max_depth: int = DEFAULT_MAX_DEPTH
    max_nodes: int = DEFAULT_MAX_NODES

    def __post_init__(self) -> None:
        if not _safe_token(self.read_scope):
            raise ParserError("CAPTURE_EVENT_SCOPE_INVALID")
        if not _safe_token(self.observation_scope):
            raise ParserError("CAPTURE_EVENT_OBSERVATION_SCOPE_INVALID")
        if type(self.event_index) is not int or not 1 <= self.event_index <= 100_000:
            raise ParserError("CAPTURE_EVENT_INDEX_INVALID")
        if self.endpoint_id not in _ENDPOINTS:
            raise ParserError("CAPTURE_EVENT_ENDPOINT_INVALID")
        if not _safe_version_token(self.payload_family) or not _safe_version_token(
            self.payload_version
        ):
            raise ParserError("PARSER_VERSION_UNRESOLVED")
        observation = SanitizedObservationInput.from_mapping(
            self.payload_family,
            self.payload_version,
            self.payload,
            max_depth=self.max_depth,
            max_nodes=self.max_nodes,
        )
        object.__setattr__(self, "payload", observation.payload)

    @classmethod
    def from_mapping(
        cls,
        event: Mapping[str, Any],
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
    ) -> "CaptureParserEvent":
        """Accept one exact adapter event mapping, with no extra fields."""

        if type(event) is not dict or frozenset(event) != _EVENT_KEYS:
            raise ParserError("CAPTURE_EVENT_INVALID")
        if event["schema_version"] != EVENT_SCHEMA_VERSION:
            raise ParserError("CAPTURE_EVENT_SCHEMA_INVALID")
        return cls(
            read_scope=event["read_scope"],
            observation_scope=event["observation_scope"],
            event_index=event["event_index"],
            endpoint_id=event["endpoint_id"],
            payload_family=event["payload_family"],
            payload_version=event["payload_version"],
            payload=event["payload"],
            max_depth=max_depth,
            max_nodes=max_nodes,
        )

    def to_observation_input(self) -> SanitizedObservationInput:
        """Return a fresh Parser envelope for this single event."""

        return SanitizedObservationInput.from_mapping(
            self.payload_family,
            self.payload_version,
            self.payload,
            max_depth=self.max_depth,
            max_nodes=self.max_nodes,
        )


def parse_capture_event(
    event: CaptureParserEvent,
    registry: ParserRegistry,
) -> dict[str, Any]:
    """Parse exactly one adapter event through the registered profile."""

    if type(event) is not CaptureParserEvent:
        raise ParserError("CAPTURE_EVENT_INVALID")
    observation = event.to_observation_input()
    if event.endpoint_id == "PRODUCTLIST":
        return parse_sanitized(observation, registry)
    return parse_food_sanitized(observation, registry)


def parse_capture_read_scope(
    events: Iterable[CaptureParserEvent],
    registry: ParserRegistry,
) -> dict[str, Any]:
    """Parse and bind FOOD plus PRODUCTLIST events from one observation.

    Product pages remain separate in event order. Every event must have the
    same ``read_scope`` and explicit ``observation_scope``.
    """

    event_list = list(events)
    if not event_list or any(type(item) is not CaptureParserEvent for item in event_list):
        raise ParserError("CAPTURE_EVENT_INVALID")
    read_scope = event_list[0].read_scope
    if any(item.read_scope != read_scope for item in event_list):
        raise ParserError("CAPTURE_READ_SCOPE_MISMATCH")
    observation_scope = event_list[0].observation_scope
    if any(item.observation_scope != observation_scope for item in event_list):
        raise ParserError("CAPTURE_OBSERVATION_SCOPE_MISMATCH")
    indexes = [item.event_index for item in event_list]
    if len(set(indexes)) != len(indexes):
        raise ParserError("CAPTURE_EVENT_INDEX_DUPLICATE")
    versions = {(item.payload_family, item.payload_version) for item in event_list}
    if len(versions) != 1:
        raise ParserError("CAPTURE_READ_PROFILE_MISMATCH")
    ordered = sorted(event_list, key=lambda item: item.event_index)
    food_events = [item for item in ordered if item.endpoint_id == "FOOD"]
    product_events = [item for item in ordered if item.endpoint_id == "PRODUCTLIST"]
    if len(food_events) != 1 or not product_events:
        raise ParserError("CAPTURE_READ_ENDPOINT_SET_INVALID")
    return {
        "contract_id": "MITMPROXY_OBSERVATION_PARSE_CONTRACT_V2",
        "read_scope": read_scope,
        "observation_scope": observation_scope,
        "payload_family": ordered[0].payload_family,
        "payload_version": ordered[0].payload_version,
        "merchant": parse_capture_event(food_events[0], registry)["merchant"],
        "productlist_events": [parse_capture_event(item, registry) for item in product_events],
    }


def run_offline_read_scope(
    event_models: Iterable[Mapping[str, Any]],
    registry: ParserRegistry,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> dict[str, Any]:
    """Run one synthetic read-scope input through the closed Parser contract.

    This is the offline boundary for adapter-shaped event dictionaries. It
    performs no file, network, process, or Provider operation.
    """

    if isinstance(event_models, Mapping) or isinstance(event_models, (str, bytes)):
        raise ParserError("CAPTURE_EVENT_INVALID")
    try:
        events = tuple(
            CaptureParserEvent.from_mapping(
                model,
                max_depth=max_depth,
                max_nodes=max_nodes,
            )
            for model in event_models
        )
    except TypeError as error:
        raise ParserError("CAPTURE_EVENT_INVALID") from error
    if not events:
        raise ParserError("CAPTURE_EVENT_INVALID")
    read_scope = events[0].read_scope
    if any(event.read_scope != read_scope for event in events):
        raise ParserError("CAPTURE_READ_SCOPE_MISMATCH")
    indexes = [event.event_index for event in events]
    if len(set(indexes)) != len(indexes):
        raise ParserError("CAPTURE_EVENT_INDEX_DUPLICATE")
    versions = {(event.payload_family, event.payload_version) for event in events}
    if len(versions) != 1:
        raise ParserError("CAPTURE_READ_PROFILE_MISMATCH")
    groups: dict[str, list[CaptureParserEvent]] = {}
    for event in sorted(events, key=lambda item: item.event_index):
        groups.setdefault(event.observation_scope, []).append(event)
    observations = [
        parse_capture_read_scope(group, registry)
        for group in groups.values()
    ]
    return {
        "contract_id": OFFLINE_READ_SCOPE_RUNNER_CONTRACT,
        "read_scope": read_scope,
        "payload_family": events[0].payload_family,
        "payload_version": events[0].payload_version,
        "observations": observations,
    }
