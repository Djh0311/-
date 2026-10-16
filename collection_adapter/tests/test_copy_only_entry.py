"""A copy-only launch must never reach the previous transport preparation."""

import asyncio
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from collection_adapter import p26_identification_host as host
from collection_adapter import p29_receiver_control as control


class CopyOnlyEntryTests(unittest.TestCase):
    def test_direct_host_refuses_before_reading_state_or_starting_transport(self):
        with patch.object(host, 'prepare', side_effect=AssertionError('transport reached')) as prepare:
            result = asyncio.run(host.serve(Path('/synthetic'), analyze_store_pages=True))
        prepare.assert_not_called()
        self.assertEqual(result['code'], 'P29_COPY_SOURCE_UNAVAILABLE')
        self.assertEqual(result['live_capture_latch'], 'CLOSED')
        self.assertEqual(result['execution_latch'], 'CLOSED')
        self.assertFalse(result['transport_started'])
        self.assertEqual(result['new_attempts'], 0)

    def test_legacy_cli_flags_cannot_restore_proxy_or_report_ready(self):
        for flags in ([], ['--serve-identification'],
                      ['--serve-identification', '--analyze-store-pages'],
                      ['--serve-result', '--result-profile-control', 'synthetic.json']):
            with self.subTest(flags=flags), patch.object(host, 'prepare') as prepare:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = host.main(['--output-root', '/synthetic', *flags])
                self.assertEqual(code, 2)
                self.assertEqual(json.loads(output.getvalue())['code'], 'P29_COPY_SOURCE_UNAVAILABLE')
                prepare.assert_not_called()

    def test_controller_launch_refuses_before_root_checks_fifo_or_child_creation(self):
        with patch.object(control, '_root', side_effect=AssertionError('root touched')) as root:
            with self.assertRaisesRegex(control.ReceiverControlError, '^P29_COPY_SOURCE_UNAVAILABLE$'):
                control.launch_prepared('/synthetic')
        root.assert_not_called()

    def test_start_cannot_reactivate_an_old_receiver(self):
        with patch.object(control, '_root', return_value=Path('/synthetic')), \
                patch.object(control, '_current_process', return_value={}), \
                patch.object(control, '_open_owned') as opened:
            with self.assertRaisesRegex(control.ReceiverControlError, '^P29_COPY_SOURCE_UNAVAILABLE$'):
                control.send_command('/synthetic', 'start')
        opened.assert_not_called()


if __name__ == '__main__':
    unittest.main()
