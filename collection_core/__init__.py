"""P0 business-record assembly for structured collection events."""

from .p0 import P0Context, P0Error, build_p0_batch, validate_p0_batch
from .p1_contract import P1_FIELD_SPECS, P1FieldContractError, P1FieldValue, validate_p1_field_set
from .p1 import P1AssemblyError, build_p1_batch, validate_p1_batch
from .p1_result_views import P1ResultViewError, P1ResultViews, render_p1_result
from .publisher import P0PublisherError, publish_p0_bundle
from .result_views import P0ResultViewError, P0ResultViews, render_p0_result
from .result_publisher import ResultPublishError, precheck_result_destination, publish_result_set

__all__ = [
    "P0Context",
    "P0Error",
    "P1_FIELD_SPECS",
    "P1FieldContractError",
    "P1FieldValue",
    "P1AssemblyError",
    "P1ResultViewError",
    "P1ResultViews",
    "P0PublisherError",
    "P0ResultViewError",
    "P0ResultViews",
    "ResultPublishError",
    "build_p0_batch",
    "build_p1_batch",
    "precheck_result_destination",
    "publish_p0_bundle",
    "render_p0_result",
    "publish_result_set",
    "render_p1_result",
    "validate_p0_batch",
    "validate_p1_field_set",
    "validate_p1_batch",
]
