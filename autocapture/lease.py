"""Single-owner, single-consumption memory lease for proxy response bytes."""

from __future__ import annotations

import math
from typing import Callable, Optional


HARD_MAX_LEASE_BYTES = 8 * 1024 * 1024
HARD_MAX_LEASE_SECONDS = 30.0


class LeaseError(RuntimeError):
    """A lease failure whose public representation is a closed code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _valid_max_bytes(value: object) -> bool:
    return type(value) is int and 0 < value <= HARD_MAX_LEASE_BYTES


def _valid_ttl(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    number = float(value)
    return math.isfinite(number) and 0.0 < number <= HARD_MAX_LEASE_SECONDS


def _clock_value(clock: Callable[[], float]) -> float:
    failed = False
    value: object = None
    try:
        value = clock()
    except BaseException:
        failed = True
    if failed:
        raise LeaseError("LEASE_CLOCK_FAILURE")
    if type(value) not in (int, float):
        raise LeaseError("LEASE_CLOCK_INVALID")
    number = float(value)
    if not math.isfinite(number):
        raise LeaseError("LEASE_CLOCK_INVALID")
    return number


def _zero(buffer: bytearray) -> None:
    for index in range(len(buffer)):
        buffer[index] = 0


class RawLease:
    """Own one bounded bytearray until an explicit, idempotent close."""

    __slots__ = (
        "_buffer",
        "_clock",
        "_expires_at",
        "_last_clock",
        "_consumed",
        "_closed",
    )

    def __init__(
        self,
        buffer: bytearray,
        clock: Callable[[], float],
        expires_at: float,
        last_clock: float,
    ) -> None:
        self._buffer: Optional[bytearray] = buffer
        self._clock = clock
        self._expires_at = expires_at
        self._last_clock = last_clock
        self._consumed = False
        self._closed = False

    @classmethod
    def from_proxy_bytes(
        cls,
        raw: bytes,
        max_bytes: int,
        ttl_seconds: float,
        clock: Callable[[], float],
    ) -> "RawLease":
        """Copy exact proxy bytes after validating pre- and post-copy bounds."""

        if type(raw) is not bytes:
            raise LeaseError("LEASE_INPUT_TYPE")
        if not _valid_max_bytes(max_bytes):
            raise LeaseError("LEASE_MAX_BYTES_INVALID")
        if not _valid_ttl(ttl_seconds):
            raise LeaseError("LEASE_TTL_INVALID")
        if not callable(clock):
            raise LeaseError("LEASE_CLOCK_INVALID")

        started_at = _clock_value(clock)
        if len(raw) > max_bytes:
            raise LeaseError("LEASE_BODY_LIMIT")

        copy_failed = False
        owned: Optional[bytearray] = None
        try:
            owned = bytearray(raw)
        except Exception:
            copy_failed = True
        if copy_failed or owned is None:
            raise LeaseError("LEASE_COPY_FAILURE")

        if len(owned) > max_bytes:
            _zero(owned)
            raise LeaseError("LEASE_BODY_LIMIT")

        clock_error: Optional[str] = None
        after_copy = started_at
        try:
            after_copy = _clock_value(clock)
        except LeaseError as error:
            clock_error = error.code
        if clock_error is not None:
            _zero(owned)
            raise LeaseError(clock_error)
        if after_copy < started_at:
            _zero(owned)
            raise LeaseError("LEASE_CLOCK_INVALID")
        expires_at = started_at + float(ttl_seconds)
        if after_copy >= expires_at:
            _zero(owned)
            raise LeaseError("LEASE_EXPIRED")
        return cls(owned, clock, expires_at, after_copy)

    @property
    def consumed(self) -> bool:
        return self._consumed

    @property
    def closed(self) -> bool:
        return self._closed

    def expired(self) -> bool:
        """Check the monotonic deadline without exposing clock values."""

        now = _clock_value(self._clock)
        if now < self._last_clock:
            raise LeaseError("LEASE_CLOCK_INVALID")
        self._last_clock = now
        return now >= self._expires_at

    def consume_once(self) -> bytearray:
        """Return the owned bytearray once; callers must close in finally/with."""

        if self._closed:
            raise LeaseError("LEASE_CLOSED")
        if self._consumed:
            raise LeaseError("LEASE_CONSUMED")
        clock_error: Optional[str] = None
        is_expired = False
        try:
            is_expired = self.expired()
        except LeaseError as error:
            clock_error = error.code
        if clock_error is not None:
            self.close()
            raise LeaseError(clock_error)
        if is_expired:
            self.close()
            raise LeaseError("LEASE_EXPIRED")
        if self._buffer is None:
            self.close()
            raise LeaseError("LEASE_CLOSED")
        self._consumed = True
        return self._buffer

    def close(self) -> None:
        """Zero the owned bytearray in place, release it, and remain idempotent."""

        if self._closed:
            return
        owned = self._buffer
        if owned is not None:
            _zero(owned)
        self._buffer = None
        self._closed = True

    def __enter__(self) -> "RawLease":
        if self._closed:
            raise LeaseError("LEASE_CLOSED")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        self.close()
        return False

    def __reduce__(self) -> object:
        raise LeaseError("LEASE_SERIALIZATION_PROHIBITED")

    def __reduce_ex__(self, protocol: int) -> object:
        raise LeaseError("LEASE_SERIALIZATION_PROHIBITED")

    def __getstate__(self) -> object:
        raise LeaseError("LEASE_SERIALIZATION_PROHIBITED")
