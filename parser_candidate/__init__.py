"""Isolated offline Parser candidate for the configurable PRODUCTLIST contract."""

from .envelope import SanitizedObservationInput
from .capture_contract import (
    CaptureParserEvent,
    EVENT_SCHEMA_VERSION,
    OFFLINE_READ_SCOPE_RUNNER_CONTRACT,
    make_adapter_event,
    parse_capture_event,
    parse_capture_read_scope,
    run_offline_read_scope,
)
from .parser import (
    Binding,
    FoodParserConfig,
    ParserConfig,
    ParserError,
    parse_food,
    parse_productlist,
)
from .registry import (
    ParserRegistry,
    parse_food_registered,
    parse_food_sanitized,
    parse_registered,
    parse_sanitized,
)
from .profiles import h31_food_config, h31_productlist_config

__all__ = [
    "Binding",
    "CaptureParserEvent",
    "EVENT_SCHEMA_VERSION",
    "OFFLINE_READ_SCOPE_RUNNER_CONTRACT",
    "make_adapter_event",
    "FoodParserConfig",
    "ParserConfig",
    "ParserError",
    "ParserRegistry",
    "SanitizedObservationInput",
    "parse_productlist",
    "parse_food",
    "parse_capture_event",
    "parse_capture_read_scope",
    "run_offline_read_scope",
    "parse_food_registered",
    "parse_food_sanitized",
    "parse_registered",
    "parse_sanitized",
    "h31_productlist_config",
    "h31_food_config",
]
