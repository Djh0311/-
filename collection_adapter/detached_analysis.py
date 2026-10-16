"""Bounded RAM-only copies. The forwarding thread never waits for analysis.

One serial worker owns collector feeds. Header admission shares its state lock
but only tries the lock: when analysis is busy, that observation is skipped.
No partially skipped stream is parsed, retried, logged, or written as raw data.

A failure that belongs to one copy is recorded and that copy is dropped. Later
copies keep running, and the diagnostic says CONTINUING. The worker stops only
for an explicit stop, a dead worker, or a real identification-window close.
"""

from collections import deque
from contextlib import contextmanager
from copy import deepcopy
import threading
from datetime import datetime, timezone
import time

from .p26_identification import MAX_BODY, MAX_TOTAL
from .observation_time import received_at, received_clock
from .p26_structure_budget import validate_detail


# One response can fail without closing the identification window. Session
# budgets, clock failures and explicit stops are not in this set.
ISOLATED_CLOSE = frozenset({
    'P26_IDENTIFICATION_EXCEPTION',
    'P26_ENCODING_INVALID',
    'P26_ENCODING_UNSUPPORTED',
    'P26_RESPONSE_SIZE_LIMIT',
})


class DetachedAnalysis:
    MAX_CHUNKS = 256

    def __init__(self, window):
        self.window = window
        self.lock = threading.Lock()
        self.condition = threading.Condition()
        self.queue = deque()
        self.queued_bytes = 0
        self.accepting = True
        self.stopping = False
        self.terminal = False
        self.epoch = 0
        self.discard_open = False
        self.failure = None
        self.skipped_headers = 0
        self.dropped_copies = 0
        self.completed_streams = 0
        self.counts_at_least = False
        self.processing = False
        self._current = None
        self._snapshot = window.diagnostic()
        self._budget_detail = validate_detail(getattr(window, 'structure_budget_failure', None))
        self._thread = None
        self._close = window.close
        window.close = self._request_close

    def _note_locked(self, name, count=1):
        value = getattr(self, name) + count
        self.counts_at_least |= value > 1000000
        setattr(self, name, min(value, 1000000))

    def _request_close(self, code='P26_IDENTIFICATION_CLOSED'):
        if code in ISOLATED_CLOSE and not self.stopping:
            # A single copy failed. Keep the identification window open.
            with self.condition:
                collector = self._current if threading.current_thread() is self._thread else None
                self._gap_locked('ANALYSIS_REJECTED', collector)
            return
        if threading.current_thread() is self._thread:
            self._close(code)
        else:
            # A real window close asked for off the worker. Finalization,
            # including output I/O, stays off the forwarding loop.
            with self.condition:
                self._terminal_locked('ANALYSIS_REJECTED')

    def _refresh(self):
        # Called only while holding the window lock. No values in this view.
        try:
            snapshot = self.window.diagnostic()
        except Exception:
            with self.condition:
                if self.failure != 'ANALYSIS_DIAGNOSTIC_FAILED':
                    self.failure = 'ANALYSIS_DIAGNOSTIC_FAILED'
                    self._note_locked('dropped_copies')
            return
        with self.condition:
            self._snapshot = snapshot
            self._budget_detail = validate_detail(getattr(self.window, 'structure_budget_failure', None))
            self.condition.notify_all()

    @contextmanager
    def admission(self, *, count_skip=True):
        acquired = self.lock.acquire(blocking=False)
        allowed = acquired and self.accepting and self.window.state != 'CLOSED'
        if not allowed and count_skip:
            with self.condition:
                self._note_locked('skipped_headers')
        try:
            yield allowed
        except Exception:
            with self.condition:
                if self.accepting and not self.terminal:
                    self._gap_locked('ANALYSIS_REJECTED')
        finally:
            if acquired:
                self._refresh()
                self.lock.release()

    def _start_locked(self):
        if self._thread is None and not self.terminal:
            try:
                self._thread = threading.Thread(target=self._run,
                                                name='public-copy-analysis', daemon=True)
                self._thread.start()
            except Exception:
                self._thread = None
                self.accepting = False
                self.terminal = True
                self.failure = 'WORKER_UNAVAILABLE'
                self._note_locked('dropped_copies', len(self.queue))
                self.queue.clear()
                self.queued_bytes = 0

    def _drop_collector_locked(self, collector):
        kept = deque()
        removed = 0
        for item in self.queue:
            if item[0] is collector:
                self.queued_bytes -= len(item[1])
                removed += 1
            else:
                kept.append(item)
        if self.queued_bytes < 0:
            self.queued_bytes = 0
        self.queue = kept
        return removed

    def _gap_locked(self, code, collector=None):
        """Record one missed copy and keep accepting later copies."""
        self.failure = code
        removed = self._drop_collector_locked(collector) if collector is not None else 0
        self._note_locked('dropped_copies', max(removed, 1))

    def _terminal_locked(self, code):
        self.accepting = False
        self.terminal = True
        self.failure = code
        pending = len(self.queue)
        if pending:
            self._note_locked('dropped_copies', pending)
        self.queue.clear()
        self.queued_bytes = 0
        self._start_locked()
        self.condition.notify_all()

    def reject_transport_copy(self):
        """Drop in-flight copies from one transport failure; keep later copies."""
        with self.condition:
            if not self.accepting or self.terminal:
                return
            self.epoch += 1
            pending = len(self.queue)
            self.queue.clear()
            self.queued_bytes = 0
            self.failure = 'ANALYSIS_REJECTED'
            self.discard_open = True
            self._note_locked('dropped_copies', max(pending, 1))
            self.condition.notify_all()

    def note_missing_response(self):
        """Record a gap before response copying began; keep other copies usable."""
        with self.condition:
            if self.accepting:
                self._note_locked('dropped_copies')

    def stream(self, collector):
        size = 0
        ended = False
        with self.condition:
            epoch = self.epoch
        try:
            collector.copy_epoch = epoch
        except Exception:
            with self.condition:
                if self.accepting and not self.terminal:
                    self._gap_locked('COPY_METADATA_INVALID', collector)

            def unchanged(chunk):
                return chunk
            return unchanged

        def copy_chunk(chunk):
            nonlocal size, ended
            # bytes are immutable. Retain only a bounded reference for the
            # worker; the exact input object is returned to the proxy engine.
            if ended:
                return chunk
            try:
                queued_at = time.monotonic()
                timestamp = datetime.now(timezone.utc).isoformat() if not chunk else None
                clock = self.window.clock() if not chunk else None
            except Exception:
                with self.condition:
                    if self.accepting and not self.terminal:
                        self._gap_locked('COPY_METADATA_INVALID', collector)
                ended = True
                return chunk
            with self.condition:
                if not self.accepting or epoch != self.epoch:
                    ended = True
                    return chunk
                size += len(chunk)
                if (size > MAX_BODY or self.queued_bytes + len(chunk) > MAX_TOTAL
                        or len(self.queue) >= self.MAX_CHUNKS):
                    ended = True
                    self._gap_locked('COPY_QUEUE_LIMIT', collector)
                    return chunk
                ended = not chunk
                self.queue.append((collector, chunk, queued_at, timestamp, clock, epoch))
                self.queued_bytes += len(chunk)
                self._start_locked()
                self.condition.notify_all()
            return chunk

        return copy_chunk

    def _discard_stale_collectors(self):
        current = self.epoch
        for collector in list(self.window.collectors):
            # Missing epoch means the forwarding thread has not attached this
            # collector yet. Only copies from an older transport generation go.
            if getattr(collector, 'copy_epoch', None) not in (None, current):
                collector.clear()
        self.window.collectors = [collector for collector in self.window.collectors
                                  if not collector.finished]

    def _process_job(self, job):
        collector, chunk, queued_at, timestamp, clock, epoch = job
        if epoch != self.epoch or getattr(collector, 'finished', False):
            with self.condition:
                self.processing = False
                self.condition.notify_all()
            return
        if time.monotonic() - queued_at >= 60:
            with self.condition:
                self._gap_locked('ANALYSIS_REJECTED', collector)
                self.processing = False
                self.condition.notify_all()
            collector.clear()
            return
        token = received_at.set(timestamp)
        clock_token = received_clock.set(clock)
        isolated = False

        def guard_close(code='P26_IDENTIFICATION_CLOSED'):
            nonlocal isolated
            if code in ISOLATED_CLOSE and not self.stopping:
                isolated = True
                with self.condition:
                    self._gap_locked('ANALYSIS_REJECTED', collector)
                return
            self._request_close(code)

        self._current = collector
        self.window.close = guard_close
        try:
            collector.feed(chunk)
        except Exception:
            isolated = True
            with self.condition:
                self._gap_locked('ANALYSIS_REJECTED', collector)
        finally:
            self.window.close = self._request_close
            self._current = None
            received_at.reset(token)
            received_clock.reset(clock_token)
        if not chunk and not isolated:
            with self.condition:
                self._note_locked('completed_streams')
        self._refresh()
        with self.condition:
            self.processing = False
            self.condition.notify_all()

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(
                    lambda: self.queue or self.stopping or self.terminal or self.discard_open,
                    timeout=.2)
                discard = self.discard_open
                self.discard_open = False
                if self.terminal:
                    job = None
                elif self.queue:
                    job = self.queue.popleft()
                    self.queued_bytes -= len(job[1])
                    self.processing = True
                elif self.stopping:
                    return
                else:
                    job = 'expire'
            with self.lock:
                if discard:
                    self._discard_stale_collectors()
                if job is None:
                    if self.window.state != 'CLOSED':
                        self._close('P26_IDENTIFICATION_EXCEPTION')
                    self._refresh()
                    return
                if job == 'expire':
                    # Status reads cached diagnostics; raw leases still need
                    # their original expiry even when no new traffic arrives.
                    self._refresh()
                    if self.window.state == 'CLOSED':
                        with self.condition:
                            self.accepting = False
                            self.terminal = True
                            self.failure = self.failure or 'ANALYSIS_CLOSED'
                        return
                    continue
                self._process_job(job)
                if self.window.state == 'CLOSED':
                    with self.condition:
                        self.accepting = False
                        self.terminal = True
                        self.failure = self.failure or 'ANALYSIS_CLOSED'
                        pending = len(self.queue)
                        if pending:
                            self._note_locked('dropped_copies', pending)
                        self.queue.clear()
                        self.queued_bytes = 0
                    return
            # Do not retain the last body chunk while waiting for another job.
            del job

    def snapshot(self):
        with self.condition:
            return deepcopy(self._snapshot)

    def diagnostic(self):
        with self.condition:
            result = {'schema_version': 'detached-copy-analysis/v1',
                    'accepting_copies': self.accepting,
                    'failure': self.failure,
                    'queued_chunks': len(self.queue), 'queued_bytes': self.queued_bytes,
                    'skipped_headers': self.skipped_headers,
                    'dropped_copies': self.dropped_copies,
                    'completed_streams': self.completed_streams,
                    'counts_at_least': self.counts_at_least,
                    'coverage_incomplete': bool(self.failure or self.skipped_headers or self.dropped_copies),
                    'recovery': 'STOPPED' if (not self.accepting or self.terminal) else 'CONTINUING',
                    'raw_payload_persisted': False}
            if self._budget_detail is not None:
                result['structure_budget'] = dict(self._budget_detail)
            return result

    def finish(self, code='P26_IDENTIFICATION_CLOSED'):
        """Called off the transport loop, after interception has been cleared.

        Explicit stop discards queued copies and waits for the current bounded
        parser operation before closing its window. No concurrent state edits
        or result publication after the final close receipt.
        """
        with self.condition:
            self.accepting = False
            self.stopping = True
            self._note_locked('dropped_copies', len(self.queue))
            self.queue.clear()
            self.queued_bytes = 0
            self.condition.notify_all()
        if self._thread is not None:
            self._thread.join()
        with self.lock:
            self._close(code)
            self._refresh()
            self.window.close = self._close
