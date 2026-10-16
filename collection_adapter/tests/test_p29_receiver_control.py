import asyncio
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from collection_adapter import p29_receiver_control as control
from collection_adapter import p26_identification_host as host


class ReceiverControlTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.root.chmod(0o700)
        self.script = self.root / 'synthetic_receiver.py'
        self.script.write_text('import sys,json\n'
            'print(json.dumps({"event":"SYNTHETIC_READY","attempts":0}),flush=True)\n'
            'for line in sys.stdin:\n'
            ' command=line.strip()\n'
            ' print(json.dumps({"event":"SYNTHETIC_COMMAND","command":command}),flush=True)\n'
            ' if command=="stop": break\n')
        for p in (patch.object(control, '_git_ignored_root', return_value=True),
                  patch.object(control, '_argv', return_value=[sys.executable, '-B', str(self.script)])):
            p.start(); self.addCleanup(p.stop)
        self.pid = None
        self.child = None
        self.addCleanup(self.terminate)

    def terminate(self):
        if self.pid:
            child = self.child
            if child is not None:
                if child.poll() is None: child.terminate()
                child.wait(timeout=5)

    def wait_event(self, event):
        deadline = time.monotonic()+3
        while time.monotonic()<deadline:
            values = control.read_events(self.root)
            if any(row.get('event')==event for row in values): return values
            time.sleep(0.01)
        self.fail('synthetic event missing')

    def launch(self):
        # Create a harmless historical-receiver stand-in in the test only.
        # Production launch is retired; status/stop must still clean up an
        # already running process without re-enabling its start command.
        os.mkfifo(self.root / control.FIFO, 0o600)
        fifo = os.open(self.root / control.FIFO, os.O_RDWR)
        output = os.open(self.root / control.EVENTS, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        metadata = os.fstat(fifo)
        try:
            self.child = subprocess.Popen(control._argv(self.root, sys.executable),
                stdin=fifo, stdout=output, stderr=subprocess.DEVNULL,
                start_new_session=True, close_fds=True)
            self.pid = self.child.pid
        finally:
            os.close(fifo)
            os.close(output)
        command = os.open(self.root / control.COMMANDS, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(command)
        receipt = {'schema_version': 'p29-owned-receiver-process/v1',
            'output_root': str(self.root), 'pid': self.pid,
            'python_executable': sys.executable, 'interpreter_prefix': sys.base_prefix,
            'fifo_identity': [metadata.st_dev, metadata.st_ino],
            'launched_at': '2026-01-01T00:00:00+00:00', 'control': 'OWNED_FIFO',
            'starts_automatically': False, 'automatic_retry': False,
            'raw_payload_persisted': False}
        host._write_new(self.root, control.PROCESS, receipt)
        self.wait_event('SYNTHETIC_READY')
        return receipt

    def test_historical_receiver_status_is_readable_without_start(self):
        receipt = self.launch()
        self.assertFalse(receipt['starts_automatically'])
        self.assertFalse(receipt['automatic_retry'])
        self.assertEqual(os.getsid(self.pid), self.pid)
        self.assertEqual(control.read_events(self.root), [{'event':'SYNTHETIC_READY','attempts':0}])
        from jsonschema import Draft202012Validator, FormatChecker
        schema=Path(__file__).parents[2]/'contracts/schemas/p29-receiver-process-v1.schema.json'
        validator=Draft202012Validator(json.loads(schema.read_text()),format_checker=FormatChecker())
        self.assertTrue(validator.is_valid(receipt))
        self.assertFalse(validator.is_valid({**receipt,'raw':'synthetic forbidden value'}))
        for name in (control.FIFO,control.EVENTS,control.COMMANDS,control.PROCESS):
            self.assertEqual(stat.S_IMODE((self.root/name).stat().st_mode),0o600)

    def test_independent_writers_do_not_close_receiver_or_duplicate_commands(self):
        self.launch()
        control.send_command(self.root,'status')
        self.wait_event('SYNTHETIC_COMMAND')
        time.sleep(0.05)
        control.send_command(self.root,'layout')
        control.send_command(self.root,'stop')
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            rows=control.read_events(self.root)
            if any(row.get('command')=='stop' for row in rows): break
            time.sleep(0.01)
        self.assertEqual([row['command'] for row in rows if 'command' in row],['status','layout','stop'])

    def test_command_injection_and_used_window_refused(self):
        for command in ('merchant','domain 0','start\nstatus','parameter {}','probe {}'):
            with self.assertRaises(control.ReceiverControlError): control.send_command(self.root,command)
        with self.assertRaisesRegex(control.ReceiverControlError, 'P29_COPY_SOURCE_UNAVAILABLE'):
            control.launch_prepared(self.root)
        self.assertFalse((self.root/control.FIFO).exists())

    def test_command_budget_still_allows_stop(self):
        self.launch()
        (self.root/control.COMMANDS).write_bytes(b'status\n'*control.MAX_COMMANDS)
        with self.assertRaises(control.ReceiverControlError): control.send_command(self.root,'status')
        control.send_command(self.root,'stop')
        rows=self.wait_event('SYNTHETIC_COMMAND')
        self.assertEqual(rows[-1]['command'],'stop')

    def test_symlink_wrong_mode_and_partial_event_guard(self):
        self.launch()
        path=self.root/control.EVENTS
        path.chmod(0o644)
        with self.assertRaises(control.ReceiverControlError): control.read_events(self.root)
        path.chmod(0o600)
        control.send_command(self.root,'stop'); self.wait_event('SYNTHETIC_COMMAND')
        self.child.wait(timeout=5);self.pid=None
        with path.open('ab') as f: f.write(b'{"event":')
        self.assertTrue(control.read_events(self.root))
        original=self.root/'saved-events.jsonl';path.rename(original);path.symlink_to(original)
        with self.assertRaises(control.ReceiverControlError): control.read_events(self.root)

    def test_fifo_replacement_rejected_before_command_write(self):
        self.launch()
        fifo=self.root/control.FIFO;fifo.unlink();os.mkfifo(fifo,0o600)
        replacement=os.open(fifo,os.O_RDWR);self.addCleanup(os.close,replacement)
        with self.assertRaises(control.ReceiverControlError): control.send_command(self.root,'status')
        self.assertFalse((self.root/control.COMMANDS).read_bytes())

    def test_new_controller_launch_drives_real_cli_start_status_stop_with_fake_network(self):
        from collection_adapter.tests.test_forwarding_receiver import prepared_state
        from collection_adapter import forwarding_receiver
        # A real isolated subprocess and FIFO exercise main/command_input/run;
        # all OS network/CA/PID entry points are replaced before the CLI runs.
        repo = str(Path(__file__).resolve().parents[2])
        self.script.write_text('''import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, REPO)
from collection_adapter import p26_identification_host as host
from collection_adapter import forwarding_receiver as receiver
from collection_adapter import p29_receiver_control as control
from collection_adapter.tests.test_forwarding_receiver import FakeEngine, prepared_state
root = Path(__file__).parent.resolve()
state = prepared_state(root)
with patch.object(host, 'prepare', side_effect=lambda _: (state.copy(), {'store': 'Synthetic batch shop'}, 123)), \\
     patch.object(host, '_selected_pid', return_value=123), \\
     patch.object(receiver, 'LocalForwardingEngine', FakeEngine):
    raise SystemExit(host.main(control._argv(root, sys.executable, True)[4:]))
'''.replace('REPO', repr(repo)))
        popen = subprocess.Popen
        def retain(*args, **kwargs):
            self.child = popen(*args, **kwargs)
            self.pid = self.child.pid
            return self.child
        state = prepared_state(self.root)
        with patch.object(host, 'prepare', return_value=(state, {'store': 'Synthetic batch shop'}, 123)), \
                patch.object(control.subprocess, 'Popen', side_effect=retain):
            receipt = control.launch_prepared(self.root, forward_public_copy=True)
        self.assertEqual(receipt['input_mode'], 'FORWARDED_COPY')
        rows = self.wait_event('P29_RECEIVER_PREPARED')
        self.assertFalse(rows[-1]['transport_started'])
        self.assertEqual(rows[-1]['new_attempts'], 0)
        self.assertFalse((self.root / forwarding_receiver.LOCK).exists())
        control.send_command(self.root, 'start')
        self.wait_event('P29_FORWARDING_STARTED')
        control.send_command(self.root, 'status')
        self.wait_event('P29_FORWARDING_STATUS')
        control.send_command(self.root, 'stop')
        rows = self.wait_event('P29_FORWARDING_CLOSED')
        self.assertEqual(self.child.wait(timeout=5), 0)
        self.pid = None
        final = rows[-1]
        self.assertEqual((final['new_attempts'], final['cleanup']), (1, 'COMPLETE'))
        self.assertEqual(final['diagnostic']['execution_latch'], 'CLOSED')
        self.assertFalse((self.root / forwarding_receiver.LOCK).exists())
        from jsonschema import Draft202012Validator, FormatChecker
        schema = Path(__file__).parents[2] / 'contracts/schemas/p29-receiver-process-v1.schema.json'
        Draft202012Validator(json.loads(schema.read_text()), format_checker=FormatChecker()).validate(receipt)

    def test_new_launch_refuses_existing_control_files_before_preparation(self):
        (self.root / control.PROCESS).write_text('{}')
        with patch('collection_adapter.forwarding_receiver.prepare_receiver') as prepare:
            with self.assertRaisesRegex(control.ReceiverControlError, 'P29_CONTROL_WINDOW_ALREADY_USED'):
                control.launch_prepared(self.root, forward_public_copy=True)
        prepare.assert_not_called()


class FileDiagnosticBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_regular_file_has_total_byte_budget_without_free_error_output(self):
        with tempfile.TemporaryFile() as file:
            failures=[]
            with patch.object(host,'MAX_DIAGNOSTIC_QUEUE',80):
                output=host.EventOutput(asyncio.get_running_loop(),file.fileno(),lambda:failures.append(True))
                output.send({'event':'SYNTHETIC_STATUS'})
                output.send({'event':'SYNTHETIC_STATUS'})
                output.send({'event':'SYNTHETIC_STATUS'})
            self.assertEqual(failures,[True])
            self.assertTrue(output.failed)
            self.assertLessEqual(file.tell(),80)


if __name__=='__main__': unittest.main()
