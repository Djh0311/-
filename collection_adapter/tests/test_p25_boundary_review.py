"""Direct P25 counterexamples; only synthetic helpers and disposable output."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from collection_adapter.live_prepare import LiveEntrySession, main, prepare_live_entry
from collection_adapter.tests.test_live_prepare import (
    _context, _EXPIRES_AT, _Flow, _ISSUED_AT, _policy, _Response, _root, _spec,
)


class P25BoundaryReviewTests(unittest.TestCase):
    def _validator(self, name):
        path = Path(__file__).resolve().parents[2] / 'contracts/schemas' / name
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def _complete_callbacks(self, session):
        self.assertTrue(session.start())
        self.assertTrue(session.wait_until_receiver(1))
        session.accept_callback(_Flow(_Response('FOOD')))
        session.accept_callback(_Flow(_Response('PRODUCTLIST')))

    def test_expired_before_acquire_and_worker_start_failure_are_valid_zero_attempt_stops(self):
        validator = self._validator('live-p0-not-started-v1.schema.json')
        for failure in ('EXPIRED', 'THREAD_CREATE', 'THREAD_START'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = _root(directory)
                session = prepare_live_entry(_spec(root, now=lambda: _EXPIRES_AT if failure == 'EXPIRED' else _ISSUED_AT))
                if failure == 'EXPIRED':
                    self.assertTrue(session.start())
                else:
                    target = 'collection_adapter.live_mitmproxy_addon.threading.Thread'
                    if failure == 'THREAD_START':
                        target += '.start'
                    with patch(target, side_effect=RuntimeError('synthetic-marker')):
                        self.assertFalse(session.start())
                self.assertTrue(session.wait_closed(1))
                diagnostic = session.diagnostic()
                self.assertTrue(diagnostic['not_started'])
                self.assertEqual(diagnostic['source_attempts_consumed'], 0)
                self.assertEqual(diagnostic['closure_status'], 'CLOSED')
                self.assertFalse(session.start())
                receipt = session._addon.snapshot()['receipt']
                validator.validate(receipt)
                self.assertEqual(list(Path(root).iterdir()), [])

    def test_cancel_during_parse_revokes_lease_and_prevents_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            entered, release = threading.Event(), threading.Event()

            def context(request):
                entered.set()
                release.wait(5)
                return _context(request)

            session = prepare_live_entry(_spec(root, p0_context_factory=context))
            try:
                self._complete_callbacks(session)
                self.assertTrue(entered.wait(1))
                self.assertEqual(session.diagnostic()['parse_status'], 'RUNNING')
                with patch.object(session._addon, 'wait_closed', return_value=False):
                    diagnostic = session.cancel()
                self.assertEqual(diagnostic['cancel_status'], 'REQUESTED')
                self.assertEqual(session._addon._attempt.authority.snapshot()['execution_latch'], 'CLOSED')
            finally:
                release.set()
                session.wait_closed(2)
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic['closure_code'], 'MITMPROXY_BRIDGE_CANCELLED')
            self.assertEqual(diagnostic['parse_status'], 'STOPPED')
            self.assertEqual(diagnostic['publish_status'], 'NOT_RUN')
            self.assertEqual(diagnostic['closure_status'], 'CLOSED')
            self.assertEqual(list(Path(root).iterdir()), [])
            self.assertFalse(session.start())

    def test_expiry_during_parse_is_checked_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            clock = [_ISSUED_AT]

            def context(request):
                clock[0] = _EXPIRES_AT
                return _context(request)

            session = prepare_live_entry(_spec(root, now=lambda: clock[0], p0_context_factory=context))
            self._complete_callbacks(session)
            self.assertTrue(session.wait_closed(2))
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic['closure_code'], 'LIVE_INPUT_LOCK_EXPIRED')
            self.assertEqual(diagnostic['publish_status'], 'NOT_RUN')
            self.assertEqual(session._addon._attempt.authority.snapshot()['execution_latch'], 'CLOSED')
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_cancel_after_publication_begins_preserves_the_committed_result(self):
        from collection_core import publish_result_set

        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            entered, release = threading.Event(), threading.Event()

            def publish(*args):
                entered.set()
                release.wait(5)
                return publish_result_set(*args)

            session = prepare_live_entry(_spec(root))
            with patch('collection_adapter.live_mitmproxy_addon.publish_result_set', side_effect=publish):
                try:
                    self._complete_callbacks(session)
                    self.assertTrue(entered.wait(1))
                    self.assertEqual(session.diagnostic()['parse_status'], 'ACCEPTED')
                    self.assertEqual(session.diagnostic()['publish_status'], 'RUNNING')
                    self.assertEqual(session.cancel()['cancel_status'], 'PUBLICATION_IN_PROGRESS')
                finally:
                    release.set()
                    session.wait_closed(2)
            self.assertEqual(session.diagnostic()['closure_code'], 'P0_PUBLISHED')
            self.assertTrue((Path(root) / 'p25prep' / 'manifest.json').is_file())

    def test_unrelated_route_is_ignored_without_response_reads_or_deadline_extension(self):
        class Unrelated:
            request = type('Route', (), {'method': 'GET', 'host': 'loader.local', 'path': '/other'})()

            @property
            def response(self):
                raise AssertionError('unrelated response must not be read')

        with tempfile.TemporaryDirectory() as directory:
            session = prepare_live_entry(_spec(_root(directory)))
            self.assertEqual(session.diagnostic()['receiver_ready'], 'NO')
            self.assertTrue(session.start())
            self.assertTrue(session.wait_until_receiver(1))
            self.assertEqual(session.diagnostic()['receiver_ready'], 'READY')
            deadline = session._addon._attempt.reader._deadline
            self.assertEqual(session.accept_callback(Unrelated()), 'MITMPROXY_BRIDGE_IGNORED')
            self.assertEqual(session._addon._attempt.reader._deadline, deadline)
            session.accept_callback(_Flow(_Response('FOOD')))
            session.accept_callback(_Flow(_Response('PRODUCTLIST')))
            self.assertTrue(session.wait_closed(2))
            diagnostic = session.diagnostic()
            self.assertEqual(diagnostic['raw_callback_count'], 3)
            self.assertEqual(diagnostic['target_match_count'], 2)
            self.assertEqual(diagnostic['qualified_event_count'], 1)
            self.assertEqual(diagnostic['closure_code'], 'P0_PUBLISHED')

    def test_non_boolean_or_throwing_matchers_stop_without_business_projection(self):
        def fail(*_args):
            raise RuntimeError('synthetic-marker')

        for matcher in (lambda *_args: 1, fail):
            with tempfile.TemporaryDirectory() as directory:
                session = prepare_live_entry(_spec(_root(directory), policy=_policy(endpoint_matches=matcher)))
                self.assertTrue(session.start())
                self.assertTrue(session.wait_until_receiver(1))
                session.accept_callback(_Flow(_Response()))
                self.assertTrue(session.wait_closed(2))
                self.assertEqual(session.diagnostic()['qualified_event_count'], 0)
                self.assertEqual(session.diagnostic()['closure_code'], 'MITMPROXY_BRIDGE_ENDPOINT_REJECTED')
                self.assertNotIn('synthetic-marker', json.dumps(session.diagnostic()))

    def test_duplicate_pending_callback_is_counted_without_inspecting_its_body(self):
        class Unreadable:
            @property
            def request(self):
                raise AssertionError('pending duplicate must not be inspected')

        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            session = prepare_live_entry(_spec(root))
            self.assertTrue(session.start())
            self.assertTrue(session.wait_until_receiver(1))
            reader = session._addon._attempt.reader
            with reader._condition:
                session.accept_callback(_Flow(_Response('FOOD')))
                session.accept_callback(_Flow(_Response('PRODUCTLIST')))
                self.assertEqual(session.accept_callback(Unreadable()), 'MITMPROXY_BRIDGE_DUPLICATE')
            self.assertTrue(session.wait_closed(2))
            self.assertEqual(session.diagnostic()['raw_callback_count'], 3)
            self.assertEqual(session.diagnostic()['target_match_count'], 2)
            self.assertEqual(session.diagnostic()['qualified_event_count'], 0)
            self.assertEqual(list(Path(root).iterdir()), [])
            self.assertIsNone(reader._request)
            self.assertIsNone(reader._lease)
            self.assertIsNone(reader._observation)
            self.assertEqual(reader._events_by_endpoint, {})

    def test_unwritable_output_is_rejected_before_attempt_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = _root(directory)
            with patch('collection_core.result_publisher.os.access', return_value=False):
                session = prepare_live_entry(_spec(root))
            self.assertFalse(session.start())
            self.assertEqual(session.diagnostic()['closure_code'], 'RESULT_ROOT_INVALID')
            self.assertEqual(session.diagnostic()['source_attempts_consumed'], 0)
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_invalid_arguments_emit_only_a_valid_closed_diagnostic(self):
        validator = self._validator('live-entry-diagnostic-v1.schema.json')
        for arguments in ([], ['--unknown', 'synthetic-marker'], ['--output-root']):
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                self.assertEqual(main(arguments), 2)
            diagnostic = json.loads(output.getvalue())
            validator.validate(diagnostic)
            self.assertEqual(diagnostic['closure_code'], 'PREPARATION_ARGUMENTS_INVALID')
            self.assertEqual(errors.getvalue(), '')
            self.assertNotIn('synthetic-marker', output.getvalue())

    def test_invalid_wait_arguments_and_cancel_before_prepare_are_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            session = prepare_live_entry(_spec(_root(directory)))
            for timeout in (float('nan'), float('inf'), 121, 10**1000):
                with self.assertRaisesRegex(ValueError, '^MITMPROXY_BRIDGE_WINDOW_LIMIT$'):
                    _policy(timeout=timeout)
                self.assertFalse(session.wait_closed(timeout))
                self.assertFalse(session.wait_until_receiver(timeout))
            session.cancel()
            fresh = LiveEntrySession(_spec(_root(directory)))
            fresh.cancel()
            fresh.prepare()
            self.assertFalse(fresh.start())
            self.assertEqual(fresh.diagnostic()['source_attempts_consumed'], 0)

    def test_unknown_diagnostic_codes_and_duplicate_unknown_conditions_are_rejected(self):
        validator = self._validator('live-entry-diagnostic-v1.schema.json')
        with tempfile.TemporaryDirectory() as directory:
            diagnostic = prepare_live_entry(_spec(_root(directory))).diagnostic()
            validator.validate(diagnostic)
            unknown = dict(diagnostic, closure_code='UNREGISTERED_CODE')
            self.assertFalse(validator.is_valid(unknown))
            repeated = dict(diagnostic, unknown_conditions=[diagnostic['unknown_conditions'][0]] * len(diagnostic['unknown_conditions']))
            self.assertFalse(validator.is_valid(repeated))
