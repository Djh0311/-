"""Closed, in-memory contract between a collection Adapter and the Parser candidate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Iterable, Mapping, Protocol, Tuple

from parser_candidate import CaptureParserEvent, ParserError


_REF = re.compile(r"^target:[A-Za-z0-9_-]{8,96}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_ADAPTER_ID = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")


class AdapterError(ValueError):
    """Closed-code Adapter failure that never includes target or event values."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CollectionTarget:
    """Opaque explicit target supplied by the caller; it has no source lookup behavior."""

    target_ref: str

    def __post_init__(self) -> None:
        if type(self.target_ref) is not str or _REF.fullmatch(self.target_ref) is None:
            raise AdapterError("ADAPTER_TARGET_INVALID")


@dataclass(frozen=True)
class CollectionRunConfig:
    """Explicit runtime boundary for a single offline read scope."""

    adapter_id: str
    run_ref: str
    read_scope: str
    observation_scope: str
    observed_at: str

    def __post_init__(self) -> None:
        if (
            type(self.adapter_id) is not str
            or _ADAPTER_ID.fullmatch(self.adapter_id) is None
            or type(self.run_ref) is not str
            or not self.run_ref.startswith("run:")
            or _TOKEN.fullmatch(self.run_ref[4:]) is None
            or not _safe_token(self.read_scope)
            or not _safe_token(self.observation_scope)
            or not _safe_time(self.observed_at)
        ):
            raise AdapterError("ADAPTER_CONFIG_INVALID")


@dataclass(frozen=True)
class CollectionEvent:
    """One exact Parser-compatible event with a validated private payload copy."""

    read_scope: str
    observation_scope: str
    event_index: int
    endpoint_id: str
    payload_family: str
    payload_version: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        try:
            event = CaptureParserEvent(
                read_scope=self.read_scope,
                observation_scope=self.observation_scope,
                event_index=self.event_index,
                endpoint_id=self.endpoint_id,
                payload_family=self.payload_family,
                payload_version=self.payload_version,
                payload=self.payload,
            )
        except (ParserError, TypeError):
            raise AdapterError("ADAPTER_EVENT_INVALID") from None
        object.__setattr__(self, "payload", event.payload)

    def to_parser_event(self) -> CaptureParserEvent:
        """Create a fresh Parser event without exposing a mutable source envelope."""

        try:
            return CaptureParserEvent(
                read_scope=self.read_scope,
                observation_scope=self.observation_scope,
                event_index=self.event_index,
                endpoint_id=self.endpoint_id,
                payload_family=self.payload_family,
                payload_version=self.payload_version,
                payload=self.payload,
            )
        except ParserError:
            raise AdapterError("ADAPTER_EVENT_INVALID") from None


@dataclass(frozen=True)
class CollectionEventBatch:
    """One sealed Adapter return value for exactly one run and observation scope."""

    run_ref: str
    read_scope: str
    observation_scope: str
    observed_at: str
    events: Tuple[CollectionEvent, ...]

    def __post_init__(self) -> None:
        if (
            type(self.run_ref) is not str
            or not self.run_ref.startswith("run:")
            or _TOKEN.fullmatch(self.run_ref[4:]) is None
            or not _safe_token(self.read_scope)
            or not _safe_token(self.observation_scope)
            or not _safe_time(self.observed_at)
        ):
            raise AdapterError("ADAPTER_CONFIG_INVALID")
        if type(self.events) is not tuple or not self.events:
            raise AdapterError("ADAPTER_EMPTY_RESULT")
        if any(type(event) is not CollectionEvent for event in self.events):
            raise AdapterError("ADAPTER_EVENT_INVALID")
        if any(event.read_scope != self.read_scope for event in self.events):
            raise AdapterError("ADAPTER_READ_SCOPE_MISMATCH")
        if any(event.observation_scope != self.observation_scope for event in self.events):
            raise AdapterError("ADAPTER_OBSERVATION_SCOPE_MISMATCH")
        indexes = tuple(event.event_index for event in self.events)
        if len(set(indexes)) != len(indexes):
            raise AdapterError("ADAPTER_EVENT_INDEX_DUPLICATE")
        versions = {(event.payload_family, event.payload_version) for event in self.events}
        if len(versions) != 1:
            raise AdapterError("ADAPTER_PROFILE_MISMATCH")

    @classmethod
    def from_events(
        cls,
        events: Iterable[CollectionEvent],
        config: CollectionRunConfig,
    ) -> "CollectionEventBatch":
        if type(config) is not CollectionRunConfig:
            raise AdapterError("ADAPTER_CONFIG_INVALID")
        if isinstance(events, (str, bytes, Mapping)):
            raise AdapterError("ADAPTER_EVENT_INVALID")
        try:
            event_list = tuple(events)
        except TypeError:
            raise AdapterError("ADAPTER_EVENT_INVALID") from None
        return cls(
            run_ref=config.run_ref,
            read_scope=config.read_scope,
            observation_scope=config.observation_scope,
            observed_at=config.observed_at,
            events=event_list,
        )

    def to_parser_events(self) -> Tuple[CaptureParserEvent, ...]:
        return tuple(event.to_parser_event() for event in self.events)


class Adapter(Protocol):
    """A replaceable Adapter with no implied source, I/O, or retry capability."""

    def collect(self, target: CollectionTarget, config: CollectionRunConfig) -> CollectionEventBatch:
        """Return one already-decoded, closed event batch or raise ``AdapterError``."""


def _safe_token(value: object) -> bool:
    return type(value) is str and _TOKEN.fullmatch(value) is not None


def _safe_time(value: object) -> bool:
    if type(value) is not str or not value.endswith("Z"):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True
