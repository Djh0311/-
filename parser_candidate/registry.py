"""Immutable family/version registry for the offline Parser candidate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from .envelope import SanitizedObservationInput
from .parser import FoodParserConfig, ParserConfig, ParserError, parse_food, parse_productlist


@dataclass(frozen=True)
class ParserRegistry:
    """Closed registry whose profile keys are unique and explicitly registered."""

    profiles: Tuple[ParserConfig, ...] = ()
    food_profiles: Tuple[FoodParserConfig, ...] = ()

    def validate(self) -> "ParserRegistry":
        seen: set[tuple[str, str, str]] = set()
        for profile in self.profiles:
            profile.validate()
            key = ("PRODUCTLIST", profile.payload_family, profile.payload_version)
            if key in seen:
                raise ParserError("PARSER_PROFILE_DUPLICATE")
            seen.add(key)
        for profile in self.food_profiles:
            profile.validate()
            key = ("FOOD", profile.payload_family, profile.payload_version)
            if key in seen:
                raise ParserError("PARSER_PROFILE_DUPLICATE")
            seen.add(key)
        return self

    def resolve(self, family: str, version: str) -> ParserConfig:
        self.validate()
        for profile in self.profiles:
            if profile.payload_family == family and profile.payload_version == version:
                return profile
        raise ParserError("PARSER_PROFILE_UNREGISTERED")

    def resolve_food(self, family: str, version: str) -> FoodParserConfig:
        self.validate()
        for profile in self.food_profiles:
            if profile.payload_family == family and profile.payload_version == version:
                return profile
        raise ParserError("PARSER_PROFILE_UNREGISTERED")


def parse_registered(
    payload: Mapping[str, Any],
    registry: ParserRegistry,
    family: str,
    version: str,
) -> dict[str, Any]:
    """Resolve an exact registered profile, then invoke the pure Parser."""

    profile = registry.resolve(family, version)
    return parse_productlist(payload, profile)


def parse_sanitized(
    observation: SanitizedObservationInput,
    registry: ParserRegistry,
) -> dict[str, Any]:
    """Parse only a validated, family/version-bound in-memory envelope."""

    if type(observation) is not SanitizedObservationInput:
        raise ParserError("OBSERVATION_INPUT_INVALID")
    observation.validate()
    profile = registry.resolve(observation.payload_family, observation.payload_version)
    return parse_productlist(observation.payload, profile)


def parse_food_registered(
    payload: Mapping[str, Any],
    registry: ParserRegistry,
    family: str,
    version: str,
) -> dict[str, Any]:
    """Resolve an exact FOOD profile, then invoke the pure Parser."""

    profile = registry.resolve_food(family, version)
    return parse_food(payload, profile)


def parse_food_sanitized(
    observation: SanitizedObservationInput,
    registry: ParserRegistry,
) -> dict[str, Any]:
    """Parse one validated FOOD envelope through its registered profile."""

    if type(observation) is not SanitizedObservationInput:
        raise ParserError("OBSERVATION_INPUT_INVALID")
    observation.validate()
    profile = registry.resolve_food(observation.payload_family, observation.payload_version)
    return parse_food(observation.payload, profile)
