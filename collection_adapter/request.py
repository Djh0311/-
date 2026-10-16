"""Closed, pure input contract for a user-directed synthetic offline run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Iterable, Tuple

from .contract import AdapterError, CollectionRunConfig, CollectionTarget


_ADAPTER_ID = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_RESULT_NAME = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_P0_REF_TOKEN = re.compile(r"^[A-Za-z0-9_-]{8,96}$")


class OfflineRequestError(ValueError):
    """Closed-code request failure that never includes a user-supplied value."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class OfflineRunOptions:
    """Explicit run-boundary options with no source, filesystem, or retry behavior."""

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
            or _P0_REF_TOKEN.fullmatch(self.run_ref[4:]) is None
            or not _safe_p0_token(self.read_scope)
            or not _safe_p0_token(self.observation_scope)
            or not _safe_time(self.observed_at)
        ):
            raise OfflineRequestError("OFFLINE_RUN_OPTIONS_INVALID")

    def to_collection_config(self) -> CollectionRunConfig:
        return CollectionRunConfig(
            adapter_id=self.adapter_id,
            run_ref=self.run_ref,
            read_scope=self.read_scope,
            observation_scope=self.observation_scope,
            observed_at=self.observed_at,
        )


@dataclass(frozen=True)
class OfflineOutputIntent:
    """A caller-declared local result intent, validated without touching the filesystem."""

    output_root: str
    result_name: str
    formats: Tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not _safe_output_root(self.output_root)
            or type(self.result_name) is not str
            or _RESULT_NAME.fullmatch(self.result_name) is None
            or type(self.formats) is not tuple
            or self.formats != ("JSON", "CSV")
        ):
            raise OfflineRequestError("OFFLINE_OUTPUT_INTENT_INVALID")


@dataclass(frozen=True)
class OfflineRunRequest:
    """A complete explicit request that never chooses a target by default."""

    target_ref: str
    options: OfflineRunOptions
    output_intent: OfflineOutputIntent

    def __post_init__(self) -> None:
        try:
            CollectionTarget(target_ref=self.target_ref)
        except AdapterError:
            raise OfflineRequestError("OFFLINE_TARGET_INVALID") from None
        if type(self.options) is not OfflineRunOptions:
            raise OfflineRequestError("OFFLINE_RUN_OPTIONS_INVALID")
        if type(self.output_intent) is not OfflineOutputIntent:
            raise OfflineRequestError("OFFLINE_OUTPUT_INTENT_INVALID")

    def to_collection_inputs(
        self,
        registry: "OfflineTargetRegistry",
    ) -> tuple[CollectionTarget, CollectionRunConfig]:
        if type(registry) is not OfflineTargetRegistry:
            raise OfflineRequestError("OFFLINE_TARGET_REGISTRY_INVALID")
        return registry.resolve(self.target_ref), self.options.to_collection_config()


class OfflineTargetRegistry:
    """Closed target directory; it can reject unknown values but cannot provide a default."""

    def __init__(self, targets: Iterable[CollectionTarget]) -> None:
        if isinstance(targets, (str, bytes)):
            raise OfflineRequestError("OFFLINE_TARGET_REGISTRY_INVALID")
        try:
            target_list = tuple(targets)
        except TypeError:
            raise OfflineRequestError("OFFLINE_TARGET_REGISTRY_INVALID") from None
        if not target_list or any(type(target) is not CollectionTarget for target in target_list):
            raise OfflineRequestError("OFFLINE_TARGET_REGISTRY_INVALID")
        refs = tuple(target.target_ref for target in target_list)
        if len(set(refs)) != len(refs):
            raise OfflineRequestError("OFFLINE_TARGET_REGISTRY_INVALID")
        self._targets = {target.target_ref: target for target in target_list}

    def resolve(self, target_ref: str) -> CollectionTarget:
        if type(target_ref) is not str:
            raise OfflineRequestError("OFFLINE_TARGET_INVALID")
        try:
            return self._targets[target_ref]
        except KeyError:
            raise OfflineRequestError("OFFLINE_TARGET_UNKNOWN") from None


def _safe_token(value: object) -> bool:
    return type(value) is str and _TOKEN.fullmatch(value) is not None


def _safe_p0_token(value: object) -> bool:
    return type(value) is str and _P0_REF_TOKEN.fullmatch(value) is not None


def _safe_time(value: object) -> bool:
    if type(value) is not str or not value.endswith("Z"):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _safe_output_root(value: object) -> bool:
    if type(value) is not str or value == "/" or not value.startswith("/"):
        return False
    parts = value.split("/")
    return all(part not in {".", ".."} for part in parts)
