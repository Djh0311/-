"""Pure, offline collection Adapter boundary used by Stage 01."""

from .contract import (
    Adapter,
    AdapterError,
    CollectionEvent,
    CollectionEventBatch,
    CollectionRunConfig,
    CollectionTarget,
)
from .fake import FakeAdapter, FakeFixture
from .live_execution import (
    LIVE_P0_CAPABILITIES,
    LiveExecutionError,
    LiveP0ExecutionAuthority,
    LiveP0ExecutionLease,
    LiveP0Request,
    LiveRequestError,
)
from .live_adapter import LiveAdapterError, LiveP0Adapter, LiveP0Observation, LiveP0SourceReader, live_adapter_stop_receipt
from .live_p0_entry import (
    HISTORICAL_TARGET_REF,
    P17_FORBIDDEN_CAPABILITIES,
    P17_NETWORK_CAPABILITY,
    HistoricalTargetBinding,
    LiveP0EntryError,
    bind_p17_request,
    source_entry_unavailable_stop,
)
from .mitmproxy_bridge import (
    MitmproxyBridgeError,
    MitmproxyCallbackBridge,
    MitmproxySourceEntry,
    MitmproxySourcePolicy,
    P21Attempt,
    P21OutputBoundary,
)
from .live_mitmproxy_addon import P21AddonConfig, P21AddonError, P21LiveConsumer, P21MitmproxyAddon
from .request import (
    OfflineOutputIntent,
    OfflineRequestError,
    OfflineRunOptions,
    OfflineRunRequest,
    OfflineTargetRegistry,
)

__all__ = [
    "Adapter",
    "AdapterError",
    "CollectionEvent",
    "CollectionEventBatch",
    "CollectionRunConfig",
    "CollectionTarget",
    "FakeAdapter",
    "FakeFixture",
    "LIVE_P0_CAPABILITIES",
    "LiveExecutionError",
    "LiveP0ExecutionAuthority",
    "LiveP0ExecutionLease",
    "LiveP0Request",
    "LiveRequestError",
    "LiveAdapterError",
    "LiveP0Adapter",
    "LiveP0Observation",
    "LiveP0SourceReader",
    "live_adapter_stop_receipt",
    "HISTORICAL_TARGET_REF",
    "P17_FORBIDDEN_CAPABILITIES",
    "P17_NETWORK_CAPABILITY",
    "HistoricalTargetBinding",
    "LiveP0EntryError",
    "bind_p17_request",
    "source_entry_unavailable_stop",
    "MitmproxyBridgeError",
    "MitmproxyCallbackBridge",
    "MitmproxySourceEntry",
    "MitmproxySourcePolicy",
    "P21Attempt",
    "P21OutputBoundary",
    "P21AddonConfig",
    "P21AddonError",
    "P21LiveConsumer",
    "P21MitmproxyAddon",
    "OfflineOutputIntent",
    "OfflineRequestError",
    "OfflineRunOptions",
    "OfflineRunRequest",
    "OfflineTargetRegistry",
]
