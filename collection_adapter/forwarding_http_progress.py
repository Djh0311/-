"""Bounded HTTP lifecycle evidence, without payloads or error messages."""

import math
import time
from collections import deque


PHASES = ('REQUEST_BODY', 'RESPONSE_HEADERS', 'RESPONSE_BODY')
MAX_PENDING = 64
MAX_COUNT = 128
MAX_RECENT_RESPONSES = 16


class ForwardingHTTPProgress:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        # Keys are the engine's internal flow IDs. They never leave this map.
        self.pending = {}
        self.response_codes = {}
        self.recent_responses = deque(maxlen=MAX_RECENT_RESPONSES)
        self.counts = dict.fromkeys(('http_started', 'http_request_bodies_completed',
            'http_response_headers_received', 'http_responses_completed', 'http_failures'), 0)
        self.counts_at_least = self.tracking_incomplete = self.closed = False
        self.clock_valid = True
        self.last_clock = None
        self.last_failure_phase = self.last_failure_route_slot = None
        self.unfinished = dict.fromkeys(PHASES, 0)
        self.unfinished_ages = dict.fromkeys(PHASES, 'NONE')

    def _now(self):
        try:
            now = self.clock()
            if (type(now) not in (float, int) or not math.isfinite(now)
                    or self.last_clock is not None and now < self.last_clock):
                raise ValueError
            self.last_clock = now
            return now
        except Exception:
            self.clock_valid = False
            return None

    def _note(self, key):
        self.counts_at_least |= self.counts[key] >= MAX_COUNT
        self.counts[key] = min(MAX_COUNT, self.counts[key] + 1)

    def begin(self, identity, route_slot):
        if self.closed or type(identity) is not str or identity in self.pending:
            return
        self._note('http_started')
        if len(self.pending) >= MAX_PENDING:
            self.tracking_incomplete = True
            return
        slot = route_slot if type(route_slot) is int and 0 <= route_slot < 128 else None
        self.pending[identity] = ('REQUEST_BODY', slot, self._now())

    def request_complete(self, identity):
        row = self.pending.get(identity)
        if self.closed or row is None or row[0] != 'REQUEST_BODY':
            return
        self._note('http_request_bodies_completed')
        self.pending[identity] = ('RESPONSE_HEADERS', row[1], self._now())

    def response_headers(self, identity, status_code=None):
        row = self.pending.get(identity)
        if self.closed or row is None or row[0] == 'RESPONSE_BODY':
            return
        self._note('http_response_headers_received')
        self.response_codes[identity] = (status_code if type(status_code) is int
                                         and 100 <= status_code <= 599 else None)
        self.pending[identity] = ('RESPONSE_BODY', row[1], self._now())

    def complete(self, identity):
        if self.closed:
            return
        row = self.pending.pop(identity, None)
        self._record_response(identity, row, 'RESPONSE_COMPLETE')
        if row is not None:
            self._note('http_responses_completed')

    def _record_response(self, identity, row, outcome):
        status_code = self.response_codes.pop(identity, None)
        if row is not None:
            self.recent_responses.append({'route_slot': row[1],
                'status_code': status_code, 'outcome': outcome})

    def fail(self, identity):
        if self.closed:
            return
        row = self.pending.pop(identity, None)
        self._record_response(identity, row, 'TRANSPORT_FAILED')
        self._note('http_failures')
        self.last_failure_phase = row[0] if row else 'UNKNOWN'
        self.last_failure_route_slot = row[1] if row else None

    def _pending_snapshot(self):
        counts = dict.fromkeys(PHASES, 0)
        oldest = dict.fromkeys(PHASES, None)
        now = self._now()
        for phase, _slot, started in self.pending.values():
            counts[phase] += 1
            if started is not None:
                oldest[phase] = started if oldest[phase] is None else min(started, oldest[phase])
        ages = {}
        for phase in PHASES:
            if not counts[phase]:
                ages[phase] = 'NONE'
            elif not self.clock_valid or now is None or oldest[phase] is None:
                ages[phase] = 'UNKNOWN'
            else:
                age = now - oldest[phase]
                ages[phase] = ('LT_1S' if age < 1 else '1_TO_5S' if age < 5
                    else '5_TO_30S' if age < 30 else 'GE_30S')
        return counts, ages

    def close(self):
        if self.closed:
            return
        self.unfinished, self.unfinished_ages = self._pending_snapshot()
        self.pending.clear()
        self.response_codes.clear()
        self.closed = True

    def snapshot(self, window_ref, state):
        if self.closed:
            pending, ages = dict.fromkeys(PHASES, 0), dict.fromkeys(PHASES, 'NONE')
        else:
            pending, ages = self._pending_snapshot()
        return {'schema_version': 'p26-forwarding-http-progress/v1',
            'window_ref': window_ref, 'state': state, **self.counts,
            'counts_at_least': self.counts_at_least,
            'tracking_incomplete': self.tracking_incomplete, 'clock_valid': self.clock_valid,
            'pending_by_phase': pending, 'oldest_wait_by_phase': ages,
            'unfinished_at_close_by_phase': dict(self.unfinished),
            'oldest_unfinished_at_close_by_phase': dict(self.unfinished_ages),
            'last_failure_phase': self.last_failure_phase,
            'last_failure_route_slot': self.last_failure_route_slot,
            'recent_responses': [dict(row) for row in self.recent_responses]}
