"""Owned FIFO control for explicitly selected forwarded-copy receivers.

Historical receivers retain status/stop access but cannot be restarted.
"""

import fcntl
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
from datetime import datetime, timezone

from collection_core import precheck_result_destination
from .p26_identification_host import _read_owned
from .p26_transport_preparation import _git_ignored_root

FIFO = 'receiver-control.fifo'
EVENTS = 'receiver-events.jsonl'
COMMANDS = 'receiver-commands.txt'
PROCESS = 'receiver-process.json'
MAX_COMMANDS = 64
MAX_EVENTS_BYTES = 1024 * 1024


class ReceiverControlError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _root(root):
    root = Path(root)
    try:
        precheck_result_destination(str(root), 'receiver_control')
        if not _git_ignored_root(str(root)):
            raise ValueError()
    except Exception:
        raise ReceiverControlError('P29_CONTROL_ROOT_INVALID') from None
    return root


def _open_owned(path, flags, kind):
    fd = None
    try:
        fd = os.open(path, flags | os.O_NOFOLLOW)
        metadata = os.fstat(fd)
        if (metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600
                or not kind(metadata.st_mode)):
            raise ValueError()
        return fd
    except Exception:
        if fd is not None:
            os.close(fd)
        raise ReceiverControlError('P29_CONTROL_FILE_INVALID') from None


def _argv(root, python, forward_public_copy=False):
    from .p26_public_projection import BUSINESS_DOMAINS
    argv = [python, '-B', '-m', 'collection_adapter.p26_identification_host',
        '--output-root', str(root), '--serve-identification']
    for domain in BUSINESS_DOMAINS:
        argv.extend(['--inspect-current-domain', domain])
    argv += ['--batch-public-json', '--identify-field-layout-only',
        '--inspect-sensitive-field-keys', '--inspect-public-fields',
        '--analyze-store-pages', '--identify-category-render',
        '--bind-through-current-numeric-store-ids']
    return argv + (['--forward-public-copy'] if forward_public_copy else [])


def launch_prepared(root, *, forward_public_copy=False):
    if forward_public_copy is not True:
        raise ReceiverControlError('P29_COPY_SOURCE_UNAVAILABLE')
    root = _root(root)
    if any(os.path.lexists(root / name) for name in (COMMANDS, FIFO, EVENTS, PROCESS)):
        raise ReceiverControlError('P29_CONTROL_WINDOW_ALREADY_USED')
    from .forwarding_receiver import prepare_receiver
    receiver = prepare_receiver(root)
    # Preparation is local only. The child will recheck before accepting start.
    receiver.addon.finish_analysis('P26_START_NOT_REQUESTED')
    created, child, fifo, output = [], None, None, None
    try:
        # Exclusive files prevent a second launcher or reusing an old window.
        command = os.open(root / COMMANDS, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(command)
        created.append(root / COMMANDS)
        os.mkfifo(root / FIFO, 0o600)
        created.append(root / FIFO)
        fifo = _open_owned(root / FIFO, os.O_RDWR | os.O_NONBLOCK, stat.S_ISFIFO)
        metadata = os.fstat(fifo)
        output = os.open(root / EVENTS, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        created.append(root / EVENTS)
        child = subprocess.Popen(_argv(root, sys.executable, True), stdin=fifo, stdout=output,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True,
            cwd=Path(__file__).resolve().parent.parent)
        receipt = {'schema_version': 'p29-owned-receiver-process/v1',
            'output_root': str(root), 'pid': child.pid, 'python_executable': sys.executable,
            'interpreter_prefix': sys.base_prefix, 'fifo_identity': [metadata.st_dev, metadata.st_ino],
            'launched_at': datetime.now(timezone.utc).isoformat(), 'control': 'OWNED_FIFO',
            'input_mode': 'FORWARDED_COPY', 'starts_automatically': False,
            'automatic_retry': False, 'raw_payload_persisted': False}
        from .p26_identification_host import _write_new
        _write_new(root, PROCESS, receipt)
        return receipt
    except Exception:
        if child is not None:
            child.terminate()
            child.wait(timeout=5)
        for path in reversed(created):
            path.unlink()
        raise ReceiverControlError('P29_RECEIVER_LAUNCH_FAILED') from None
    finally:
        if fifo is not None:
            os.close(fifo)
        if output is not None:
            os.close(output)


def _current_process(root):
    receipt = _read_owned(root / PROCESS)
    if (receipt.get('schema_version') != 'p29-owned-receiver-process/v1'
            or receipt.get('output_root') != str(root) or type(receipt.get('pid')) is not int):
        raise ReceiverControlError('P29_CONTROL_PROCESS_INVALID')
    result = subprocess.run(['ps', '-ww', '-p', str(receipt['pid']), '-o', 'uid=,command='],
        capture_output=True, text=True, timeout=5, check=False)
    fields = result.stdout.strip().split(None, 1)
    actual = shlex.split(fields[1]) if len(fields) == 2 else []
    if receipt.get('input_mode') not in (None, 'FORWARDED_COPY'):
        raise ReceiverControlError('P29_CONTROL_PROCESS_INVALID')
    expected = (_argv(root, receipt['python_executable'], True)
                if receipt.get('input_mode') == 'FORWARDED_COPY'
                else _argv(root, receipt['python_executable']))
    # macOS's framework launcher replaces argv[0] after Python initializes.
    # Accept only this interpreter's fixed aliases; all other arguments remain
    # exact, including the unique owned root. A PID alone never suffices.
    aliases = {receipt['python_executable'], os.path.realpath(receipt['python_executable']),
        str(Path(receipt['interpreter_prefix']) / 'Resources/Python.app/Contents/MacOS/Python')}
    forwarded = receipt.get('input_mode') == 'FORWARDED_COPY'
    owned_root = False
    if '--output-root' in actual and actual.count('--output-root') == 1:
        owned_root = actual[actual.index('--output-root') + 1] == str(root)
    same_entry = ('-m' in actual and actual[actual.index('-m') + 1] == 'collection_adapter.p26_identification_host'
        and ('--forward-public-copy' in actual) is forwarded and owned_root)
    # Domain flags can change while this process is still the owned receiver.
    # Stop and status must keep working; a PID without this root never matches.
    if (result.returncode or len(fields) != 2 or fields[0] != str(os.getuid())
            or not actual or actual[0] not in aliases
            or not (actual[1:] == expected[1:] or same_entry)):
        raise ReceiverControlError('P29_RECEIVER_NOT_RUNNING')
    return receipt


def send_command(root, command):
    if command not in ('start', 'status', 'layout', 'stop'):
        raise ReceiverControlError('P29_CONTROL_COMMAND_INVALID')
    root = _root(root)
    receipt = _current_process(root)
    if command == 'start' and receipt.get('input_mode') != 'FORWARDED_COPY':
        raise ReceiverControlError('P29_COPY_SOURCE_UNAVAILABLE')
    log = _open_owned(root / COMMANDS, os.O_RDWR, stat.S_ISREG)
    fifo = None
    try:
        fcntl.flock(log, fcntl.LOCK_EX)
        prior = os.read(log, 8193)
        if len(prior) > 8192 or (prior.count(b'\n') >= MAX_COMMANDS and command != 'stop'):
            raise ReceiverControlError('P29_CONTROL_COMMAND_BUDGET')
        fifo = _open_owned(root / FIFO, os.O_WRONLY | os.O_NONBLOCK, stat.S_ISFIFO)
        metadata = os.fstat(fifo)
        if [metadata.st_dev, metadata.st_ino] != receipt['fifo_identity']:
            raise ReceiverControlError('P29_CONTROL_FILE_INVALID')
        data = (command + '\n').encode('ascii')
        if os.write(fifo, data) != len(data):
            raise ReceiverControlError('P29_CONTROL_WRITE_FAILED')
        os.lseek(log, 0, os.SEEK_END)
        os.write(log, data)
    finally:
        if fifo is not None:
            os.close(fifo)
        os.close(log)


def read_events(root):
    root = _root(root)
    fd = _open_owned(root / EVENTS, os.O_RDONLY, stat.S_ISREG)
    try:
        if os.fstat(fd).st_size > MAX_EVENTS_BYTES:
            raise ReceiverControlError('P29_CONTROL_EVENT_BUDGET')
        data = os.read(fd, MAX_EVENTS_BYTES + 1)
    finally:
        os.close(fd)
    result = []
    for line in data.splitlines(keepends=True):
        if not line.endswith(b'\n'):
            break  # The writer may be finishing its last atomic JSON event.
        try:
            event = json.loads(line)
        except Exception:
            raise ReceiverControlError('P29_CONTROL_EVENT_INVALID') from None
        if type(event) is not dict:
            raise ReceiverControlError('P29_CONTROL_EVENT_INVALID')
        result.append(event)
    return result
