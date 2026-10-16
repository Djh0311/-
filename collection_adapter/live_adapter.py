"""P16 minimal live P0 Adapter boundary with no built-in network mechanism."""

from __future__ import annotations

from typing import Any, Callable, Dict, Protocol, Tuple

from parser_candidate import CaptureParserEvent

from .contract import AdapterError, CollectionEventBatch
from .live_execution import LiveExecutionError, LiveP0ExecutionAuthority, LiveP0ExecutionLease, LiveP0Request


_STOP_CODES = frozenset(
    {
        "LIVE_SOURCE_READ_FAILED",
        "LIVE_ADAPTER_READER_INVALID",
        "LIVE_ADAPTER_OBSERVATION_INVALID",
        "LIVE_ADAPTER_SCOPE_INVALID",
        "LIVE_P0_CONSUMER_REJECTED",
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
        "LIVE_PARSE_REJECTED",
        "LIVE_PUBLISH_REJECTED",
    }
)


class LiveAdapterError(ValueError):
    """Closed P16 Adapter failure with no source-derived detail."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class LiveP0SourceReader(Protocol):
    """P17-supplied one-shot reader; P16 itself never selects a source or opens I/O."""

    def read_once(self, request: LiveP0Request, lease: LiveP0ExecutionLease) -> "LiveP0Observation":
        """Return one already-decoded, in-memory observation for the locked request."""


class LiveP0Observation:
    """One mutable ownership boundary around a strict in-memory event batch."""

    def __init__(self, batch: CollectionEventBatch) -> None:
        if type(batch) is not CollectionEventBatch:
            raise LiveAdapterError("LIVE_ADAPTER_OBSERVATION_INVALID")
        self._batch: CollectionEventBatch | None = batch
        self._destroyed = False

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def take_parser_events(self, request: LiveP0Request) -> Tuple[CaptureParserEvent, ...]:
        """Transfer a fresh event tuple once, then release this boundary's batch reference."""

        if type(request) is not LiveP0Request or self._destroyed or self._batch is None:
            raise LiveAdapterError("LIVE_ADAPTER_OBSERVATION_INVALID")
        batch = self._batch
        try:
            if batch.run_ref != request.run_ref:
                raise LiveAdapterError("LIVE_ADAPTER_SCOPE_INVALID")
            return batch.to_parser_events()
        except AdapterError:
            raise LiveAdapterError("LIVE_ADAPTER_OBSERVATION_INVALID") from None
        finally:
            self.destroy()

    def destroy(self) -> None:
        """Release the Adapter-held reference to source-derived event material."""

        self._batch = None
        self._destroyed = True


class LiveP0Adapter:
    """Run exactly one injected reader inside the P15 lease and no other source path."""

    def __init__(self, reader: LiveP0SourceReader) -> None:
        if not callable(getattr(reader, "read_once", None)):
            raise LiveAdapterError("LIVE_ADAPTER_READER_INVALID")
        self._reader = reader

    def execute_once(
        self,
        request: LiveP0Request,
        authority: LiveP0ExecutionAuthority,
        *,
        now: str | Callable[[], str],
        consume: Callable[[Tuple[CaptureParserEvent, ...], LiveP0Request, LiveP0ExecutionLease], Any],
    ) -> Any:
        """Read and consume one P15-locked observation without retaining source events."""

        if type(request) is not LiveP0Request or type(authority) is not LiveP0ExecutionAuthority:
            raise LiveAdapterError("LIVE_ADAPTER_OBSERVATION_INVALID")
        if not callable(consume):
            raise LiveAdapterError("LIVE_P0_CONSUMER_REJECTED")
        with authority.acquire(request, now=_fresh_now(now)) as lease:
            if callable(now):
                lease.bind_refresh_clock(now)
            observation: LiveP0Observation | None = None
            events: Tuple[CaptureParserEvent, ...] = ()
            try:
                observation = self._read_once(request, lease)
                lease.require_active(now=_fresh_now(now))
                events = observation.take_parser_events(request)
                lease.require_active(now=_fresh_now(now))
                return consume(events, request, lease)
            except (LiveAdapterError, LiveExecutionError):
                raise
            except Exception:
                raise LiveAdapterError("LIVE_P0_CONSUMER_REJECTED") from None
            finally:
                events = ()
                if observation is not None and not observation.destroyed:
                    observation.destroy()

    def _read_once(self, request: LiveP0Request, lease: LiveP0ExecutionLease) -> LiveP0Observation:
        try:
            observation = self._reader.read_once(request, lease)
        except (LiveAdapterError, LiveExecutionError):
            raise
        except ValueError as error:
            if getattr(error, "code", None) in _STOP_CODES:
                raise LiveAdapterError(error.code) from None
            raise LiveAdapterError("LIVE_SOURCE_READ_FAILED") from None
        except Exception:
            raise LiveAdapterError("LIVE_SOURCE_READ_FAILED") from None
        if type(observation) is not LiveP0Observation:
            raise LiveAdapterError("LIVE_ADAPTER_OBSERVATION_INVALID")
        return observation


def _fresh_now(now: str | Callable[[], str]) -> str:
    """Resolve the clock at each P15 boundary while retaining fixed-time test support."""

    return now() if callable(now) else now


def live_adapter_stop_receipt(request: LiveP0Request, stop_code: str) -> Dict[str, object]:
    """Build a P16 value-free stop receipt after one consumed source attempt."""

    if type(request) is not LiveP0Request or stop_code not in _STOP_CODES:
        raise LiveAdapterError("LIVE_ADAPTER_OBSERVATION_INVALID")
    return {
        "schema_version": "collection-live-p0-adapter-stop/v1",
        "stop_code": stop_code,
        "run_ref": request.run_ref,
        "attempt_ref": request.attempt_ref,
        "source_ref": request.source_ref,
        "provider_contract_ref": request.provider_contract_ref,
        "authorization_ref": request.authorization_ref,
        "capability_ref": request.capability_ref,
        "source_attempt_consumed": 1,
        "automatic_retry": False,
        "business_publication_allowed": False,
        "source_material_persisted": False,
        "latch_state": "CLOSED",
    }
