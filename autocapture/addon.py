"""Deny-by-default mitmproxy-compatible response addon.

The module deliberately has no mitmproxy import.  A mitmproxy loader can call
``response(flow)`` on the exported addon, while offline tests use write-trapping
duck-typed flows.
"""

import math
import os
import sys
import time
from dataclasses import dataclass

_script_path = os.path.realpath(__file__)
_package_dir = os.path.dirname(_script_path)
_candidate_root = os.path.dirname(_package_dir)
_bootstrap_root = None
if not __package__:
    if (
        not os.path.isabs(_script_path)
        or os.path.basename(_package_dir) != "autocapture"
        or os.path.basename(_script_path) != "addon.py"
    ):
        raise RuntimeError("ADDON_LOCATION_INVALID")
    if _candidate_root not in sys.path:
        sys.path.insert(0, _candidate_root)
        _bootstrap_root = _candidate_root

try:
    from autocapture.lease import LeaseError, RawLease
    from autocapture.policy import (
        ENDPOINT_MATCH,
        ENDPOINT_METADATA_INVALID,
        CapturePolicy,
        PolicyError,
    )
    from autocapture.shape import (
        SHAPE_ERROR_CODES,
        ShapeAccumulator,
        ShapeProbeError,
    )
    if (
        os.path.realpath(sys.modules[CapturePolicy.__module__].__file__)
        != os.path.join(_package_dir, "policy.py")
        or os.path.realpath(sys.modules[RawLease.__module__].__file__)
        != os.path.join(_package_dir, "lease.py")
        or os.path.realpath(sys.modules[ShapeAccumulator.__module__].__file__)
        != os.path.join(_package_dir, "shape.py")
    ):
        raise RuntimeError("ADDON_IMPORT_ORIGIN_INVALID")
finally:
    if _bootstrap_root is not None:
        if not sys.path or sys.path[0] != _bootstrap_root:
            raise RuntimeError("ADDON_BOOTSTRAP_STATE_INVALID")
        del sys.path[0]
del _bootstrap_root, _candidate_root, _package_dir, _script_path


DISARMED = "DISARMED"
ARMED = "ARMED"
STOPPED = "STOPPED"
COMPLETED = "COMPLETED"


STOP_REASON_CODES = frozenset(
    {
        "BODY_BYTE_LIMIT",
        "BODY_TYPE_UNKNOWN",
        "CONTENT_ENCODING_UNKNOWN",
        "CONTENT_TYPE_UNKNOWN",
        "DECLARED_LENGTH_MISMATCH",
        "DECLARED_LENGTH_UNKNOWN",
        "INTERNAL_FAILURE",
        "LEASE_REJECTED",
        "LEASE_TIMEOUT",
        "OBSERVATION_TIMEOUT",
        "PUBLISH_FAILED",
        "REQUEST_METADATA_INVALID",
        "SHAPE_REJECTED",
        "TOTAL_BYTE_LIMIT",
    }
).union(SHAPE_ERROR_CODES)


@dataclass(frozen=True)
class ValueFreeStopReceipt:
    """Closed stop output containing no data-derived field."""

    reason_code: str

    def __post_init__(self):
        if self.reason_code not in STOP_REASON_CODES:
            raise ValueError("STOP_REASON_CODE_INVALID")

    def to_model(self):
        return {
            "schema_version": "autocapture-stop-receipt/v1",
            "outcome": "STOPPED",
            "reason_code": self.reason_code,
        }


class ResponseCaptureAddon:
    """One-shot, explicitly armed response shape discovery addon."""

    def __init__(self, clock=None):
        self._clock = clock if clock is not None else time.monotonic
        self._state = DISARMED
        self._policy = None
        self._publisher = None
        self._accumulator = None
        self._deadline = None
        self._event_count = 0
        self._total_body_bytes = 0
        self._stop_receipt = None
        self._arm_consumed = False
        self._last_clock = None

    @property
    def state(self):
        return self._state

    @property
    def stop_receipt(self):
        return self._stop_receipt

    @property
    def event_count(self):
        return self._event_count

    def arm(self, policy, publisher):
        """Arm one fresh instance with an already frozen explicit policy."""

        if self._state != DISARMED or self._arm_consumed:
            return False
        self._arm_consumed = True
        if type(policy) is not CapturePolicy:
            return False
        try:
            validated = policy.validated()
        except (AttributeError, PolicyError):
            return False
        try:
            publisher_keys = publisher.allowed_schema_keys
            publish = getattr(publisher, "publish", None)
        except BaseException:
            return False
        if (
            not callable(publish)
            or type(publisher_keys) is not frozenset
            or publisher_keys != frozenset(validated.allowed_json_keys)
        ):
            return False
        try:
            started_at = self._clock_now()
            deadline = started_at + validated.observation_window_seconds
            if not math.isfinite(deadline) or deadline <= started_at:
                raise TimeoutError()
            accumulator = ShapeAccumulator(
                max_depth=validated.max_json_depth,
                max_nodes=validated.max_json_nodes,
                max_paths=validated.max_shape_paths,
                max_events=validated.max_events,
                allowed_schema_keys=publisher_keys,
                clock=self._clock_now,
                deadline=deadline,
            )
        except BaseException:
            return False
        self._policy = validated
        self._publisher = publisher
        self._accumulator = accumulator
        self._deadline = deadline
        self._state = ARMED
        return True

    def response(self, flow):
        """Observe one response without modifying the flow."""

        if self._state != ARMED:
            return
        try:
            now = self._clock_now()
            if now >= self._deadline:
                self._finish()
                return
            if self._event_count >= self._policy.max_events:
                self._finish()
                return
            self._observe_response(flow)
        except TimeoutError:
            self._stop("OBSERVATION_TIMEOUT")
        except ShapeProbeError as error:
            code = error.code if error.code in SHAPE_ERROR_CODES else "SHAPE_REJECTED"
            self._stop(code)
        except LeaseError as error:
            if error.code == "LEASE_EXPIRED":
                self._stop("LEASE_TIMEOUT")
            elif error.code == "LEASE_BODY_LIMIT":
                self._stop("BODY_BYTE_LIMIT")
            else:
                self._stop("LEASE_REJECTED")
        except BaseException:
            self._stop("INTERNAL_FAILURE")

    def done(self):
        """mitmproxy lifecycle hook; publish at most one sanitized shape."""

        self.finalize()

    def finalize(self):
        if self._state != ARMED:
            return False
        try:
            self._finish()
        except BaseException:
            self._stop("PUBLISH_FAILED")
            return False
        return self._state == COMPLETED

    def _observe_response(self, flow):
        policy = self._policy

        request = flow.request
        method = request.method
        host = request.host
        path = request.path
        endpoint_selection = policy.select_endpoint(method, host, path)
        if endpoint_selection == ENDPOINT_METADATA_INVALID:
            self._stop("REQUEST_METADATA_INVALID")
            return
        if endpoint_selection != ENDPOINT_MATCH:
            return

        response = flow.response
        status_code = response.status_code
        if not policy.allows_status(status_code):
            return

        headers = response.headers
        content_type_value = headers.get("content-type")
        content_length_value = headers.get("content-length")
        content_encoding_value = headers.get("content-encoding")

        if not policy.allows_content_type(content_type_value):
            self._stop("CONTENT_TYPE_UNKNOWN")
            return
        if not self._identity_encoding(content_encoding_value):
            self._stop("CONTENT_ENCODING_UNKNOWN")
            return
        declared_length = self._declared_length(content_length_value)
        if declared_length is False:
            self._stop("DECLARED_LENGTH_UNKNOWN")
            return
        if declared_length is not None:
            if declared_length > policy.max_body_bytes:
                self._stop("BODY_BYTE_LIMIT")
                return
            if self._total_body_bytes + declared_length > policy.max_total_body_bytes:
                self._stop("TOTAL_BYTE_LIMIT")
                return
        if self._clock_now() >= self._deadline:
            self._stop("OBSERVATION_TIMEOUT")
            return

        raw_content = None
        lease = None
        try:
            raw_content = response.raw_content
            if type(raw_content) is not bytes:
                self._stop("BODY_TYPE_UNKNOWN")
                return
            actual_length = len(raw_content)
            if declared_length is not None and actual_length != declared_length:
                self._stop("DECLARED_LENGTH_MISMATCH")
                return
            if actual_length > policy.max_body_bytes:
                self._stop("BODY_BYTE_LIMIT")
                return
            if self._total_body_bytes + actual_length > policy.max_total_body_bytes:
                self._stop("TOTAL_BYTE_LIMIT")
                return
            lease = RawLease.from_proxy_bytes(
                raw_content,
                max_bytes=policy.max_body_bytes,
                ttl_seconds=policy.max_lease_seconds,
                clock=self._clock_now,
            )
            with lease:
                owned_buffer = lease.consume_once()
                staged = self._accumulator.stage_json_bytes(owned_buffer)
                if lease.expired():
                    raise LeaseError("LEASE_EXPIRED")
                self._accumulator.commit(staged)
                if lease.expired():
                    raise LeaseError("LEASE_EXPIRED")
            lease = None
            self._event_count += 1
            self._total_body_bytes += actual_length
            if self._event_count >= policy.max_events:
                self._finish()
        finally:
            if lease is not None:
                lease.close()
            raw_content = None

    @staticmethod
    def _identity_encoding(value):
        if value is None:
            return True
        if not isinstance(value, str):
            return False
        return value.strip().lower() in ("", "identity")

    def _clock_now(self):
        failed = False
        raw_value = None
        try:
            raw_value = self._clock()
        except BaseException:
            failed = True
        if failed or type(raw_value) not in (int, float):
            raise TimeoutError()
        value = float(raw_value)
        if (
            not math.isfinite(value)
            or (self._last_clock is not None and value < self._last_clock)
        ):
            raise TimeoutError()
        self._last_clock = value
        return value

    @staticmethod
    def _declared_length(value):
        if value is None:
            return None
        if not isinstance(value, str):
            return False
        normalized = value.strip()
        if (
            not normalized
            or len(normalized) > 20
            or not normalized.isascii()
            or not normalized.isdigit()
        ):
            return False
        try:
            return int(normalized, 10)
        except ValueError:
            return False

    def _finish(self):
        if self._state != ARMED:
            return
        if self._event_count == 0:
            self._state = COMPLETED
            self._total_body_bytes = 0
            self._discard_control_references()
            return
        shape = self._accumulator.build()
        try:
            self._publisher.publish(shape)
        except BaseException:
            self._stop("PUBLISH_FAILED")
            return
        self._state = COMPLETED
        self._total_body_bytes = 0
        self._discard_control_references()

    def _stop(self, reason_code):
        if self._state != ARMED:
            return
        accumulator = self._accumulator
        if accumulator is not None:
            try:
                accumulator.clear()
            except BaseException:
                pass
        self._stop_receipt = ValueFreeStopReceipt(reason_code)
        self._state = STOPPED
        self._event_count = 0
        self._total_body_bytes = 0
        self._discard_control_references()

    def _discard_control_references(self):
        self._policy = None
        self._publisher = None
        self._accumulator = None
        self._deadline = None
        self._last_clock = None


class MitmproxyCaptureAdapter(ResponseCaptureAddon):
    """Named mitmproxy adapter that reuses the single hardened hook path."""

    pass


# Importing the module is safe: this instance is and remains DISARMED until an
# explicit caller supplies both a complete policy and a Publisher.
addons = [ResponseCaptureAddon()]
