"""Response receipt time survives deferred processing; lifecycle clocks do not."""

from contextvars import ContextVar
from datetime import datetime, timezone

received_at = ContextVar('public_response_received_at', default=None)
received_clock = ContextVar('public_response_received_clock', default=None)


def observation_time():
    return received_at.get() or datetime.now(timezone.utc).isoformat()


def observation_clock(fallback):
    value = received_clock.get()
    return fallback if value is None else value
