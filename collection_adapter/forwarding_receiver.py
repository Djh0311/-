"""Explicit P29 proxy entry: forward first, inspect bounded public copies.

Preparing a receiver does not create a network engine. Only a separate start
command activates the exact, freshly checked PID. Old windows cannot reopen.
"""

import asyncio
import contextlib
import logging
import os
import signal
import sys
from pathlib import Path

from . import p26_identification_host as host
from .p26_identification import IdentificationError
from .p26_public_projection import BUSINESS_DOMAINS, PUBLIC_PATHS
from .p29_store_pages import P29StorePagesWindow

DOMAIN = BUSINESS_DOMAINS[0]
LOCK = 'identification-attempt.lock'
SETUP_TIMEOUT_SECONDS = 90


def prepare_receiver(root):
    root = Path(root)
    state, choice, pid = host.prepare(root)
    if (state['identification_attempts'] or state['result_attempts']
            or (root / LOCK).exists()):
        raise IdentificationError('P26_WINDOW_ALREADY_USED')
    if not host._public_batch_approved(state) or not host._sensitive_key_layout_approved(state):
        raise IdentificationError('P26_MONITORING_SCOPE_INVALID')
    window = P29StorePagesWindow(choice['store'], root,
        'authorization:' + state['monitoring_authorization']['scope_ref'].split(':', 1)[1],
        duration_seconds=state['monitoring_authorization']['time_limit_seconds'],
        identify_category_render=True, numeric_store_binding=True, copy_store_detail=True)
    window.key_layout_only = window.sensitive_key_layout_authorized = True
    window.public_projection_enabled = True
    window.public_projection_paths.update(PUBLIC_PATHS)
    for domain in BUSINESS_DOMAINS:
        window.inspect_current_domain(domain)
    return ForwardedReceiver(root, state, choice, pid, window)


class LocalForwardingEngine:
    """Use the installed engine without default listeners, UI, dumps or replay."""

    def __init__(self, addon, pid, ca_directory):
        self.addon, self.pid, self.ca_directory = addon, pid, ca_directory
        self.server = self.master = self.proxy = self.gate = None
        self.tasks, self.streams = set(), set()
        self.restore_logs = self.restore_failures = None
        self.intercept_cleared = True
        self.setup_stage = 'NOT_STARTED'

    async def open(self):
        self.setup_stage = 'EXISTING_COMPONENT_CHECK'
        if not host._redirector_present():
            raise IdentificationError('P26_RECEIVER_SETUP_FAILED')
        from mitmproxy import hooks, master, options
        from mitmproxy.addons.next_layer import NextLayer
        from mitmproxy.addons.proxyserver import Proxyserver
        from mitmproxy.addons.tlsconfig import TlsConfig
        from mitmproxy.proxy.mode_servers import LocalRedirectorInstance
        import mitmproxy_rs

        logger = logging.getLogger('mitmproxy')
        saved = (logger.handlers[:], logger.level, logger.propagate, logger.disabled)
        logger.handlers, logger.propagate = [logging.NullHandler()], False
        def restore():
            logger.handlers, logger.level, logger.propagate, logger.disabled = saved
        self.restore_logs = restore
        self.restore_failures = host._capture_engine_failures(self.addon.forwarding)
        self.setup_stage = 'ENGINE_CONFIGURATION'
        opts = options.Options(confdir=self.ca_directory, server=False, mode=[])
        self.master = master.Master(opts, with_termlog=False)
        # Do not attach the default dump, flow storage, replay or web addons.
        self.proxy = Proxyserver()
        self.master.addons.add(self.proxy, self.addon, NextLayer(), TlsConfig())
        opts.update(connection_strategy='eager', store_streamed_bodies=False)
        # These are the overrides supplied before addon registration. Emitting
        # every option as changed also probes obsolete TLS versions in 12.2.3;
        # that probe can raise on the installed OpenSSL before capture starts.
        self.master.addons.trigger(hooks.ConfigureHook({'confdir', 'server', 'mode'}))
        await self.master.running()
        if self.addon.transport_window.state != 'PREPARED':
            raise IdentificationError('P26_FORWARDING_ENGINE_ERROR')
        instance = LocalRedirectorInstance.make('local:' + str(self.pid), self.proxy)
        self.gate = host.PIDStreamGate(self.addon.transport_window, self.pid,
            instance.handle_stream, diagnostic=self.addon.forwarding)
        self.setup_stage = 'REDIRECTOR_CONNECTION'
        # mitmproxy_rs otherwise installs/updates /Applications implicitly.
        # This receiver is allowed to use the existing component only.
        prior_keep = os.environ.get('MITMPROXY_KEEP_REDIRECTOR')
        os.environ['MITMPROXY_KEEP_REDIRECTOR'] = '1'
        try:
            self.server = await mitmproxy_rs.local.start_local_redirector(self._accept, self._accept)
        finally:
            if prior_keep is None:
                os.environ.pop('MITMPROXY_KEEP_REDIRECTOR', None)
            else:
                os.environ['MITMPROXY_KEEP_REDIRECTOR'] = prior_keep
        self.intercept_cleared = False
        self.setup_stage = 'INACTIVE_CONFIGURATION'
        self.server.set_intercept(host._inactive_spec(self.pid))
        self.intercept_cleared = True
        self.setup_stage = 'READY'

    async def _accept(self, stream):
        task = asyncio.current_task()
        self.tasks.add(task)
        self.streams.add(stream)
        try:
            await self.gate(stream)
        finally:
            self.streams.discard(stream)
            self.tasks.discard(task)

    def activate(self):
        # Mark uncertain before the call: a partial setup failure needs cleanup.
        self.intercept_cleared = False
        self.server.set_intercept(str(self.pid))

    async def watch(self):
        await host._observe_receiver_close(self.server, self.addon.transport_window)

    async def close(self):
        complete = True
        if self.server is not None:
            try:
                self.server.set_intercept(host._inactive_spec(self.pid))
                self.intercept_cleared = True
            except Exception:
                complete = False
            try:
                self.server.close()
            except Exception:
                complete = False
        for stream in tuple(self.streams):
            try:
                stream.close()
            except Exception:
                complete = False
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=5)
            complete = complete and not pending
        if self.server is not None:
            try:
                await asyncio.wait_for(self.server.wait_closed(), 5)
            except Exception:
                complete = False
        if self.master is not None:
            try:
                await self.master.done()
            except Exception:
                complete = False
        if self.restore_failures:
            self.restore_failures()
        if self.restore_logs:
            self.restore_logs()
        return complete and self.intercept_cleared and not self.tasks


class ForwardedReceiver:
    def __init__(self, root, state, choice, pid, window):
        self.root, self.state, self.choice, self.pid = root, state, choice, pid
        self.addon = host.IdentificationAddon(window, batch_public_json=True)
        from .p29_full_capture import FullCapture
        self.addon.full_capture = FullCapture(root)
        self.transport = self.addon.transport_window
        self.engine = self.monitor = None
        self.lock_identity = None
        self.started = False
        self.closed_result = None
        self.setup_failure = None

    async def start(self):
        if self.engine is not None or self.transport.state != 'PREPARED':
            raise IdentificationError('P26_WINDOW_ALREADY_USED')
        # Recheck the current PID, scopes and CA metadata at the actual start.
        state, choice, pid = host.prepare(self.root)
        if (state != self.state or choice != self.choice or pid != self.pid
                or state['identification_attempts'] or state['result_attempts']):
            raise IdentificationError('P26_APPROVED_PRECONDITIONS_REQUIRED')
        host._write_new(self.root, LOCK, {'window_ref': self.transport.window_ref})
        metadata = (self.root / LOCK).lstat()
        self.lock_identity = (metadata.st_dev, metadata.st_ino)
        self.engine = LocalForwardingEngine(self.addon, self.pid, state['ca_directory'])
        try:
            await asyncio.wait_for(self.engine.open(), SETUP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            self.setup_failure = 'TIMEOUT'
            raise
        except Exception:
            self.setup_failure = 'FAILED'
            raise
        if self.transport.state != 'PREPARED':
            raise IdentificationError('P26_RECEIVER_SETUP_FAILED')
        # A child may change while the engine is loading. Never follow it by name.
        if host._selected_pid(self.root, True) != self.pid:
            raise IdentificationError('P26_NETWORK_OWNER_UNCONFIRMED')
        self.addon.window.start_once()
        with self.addon.analysis.lock:
            self.addon.analysis._refresh()
        self.transport.start_once()
        host._update_state(self.root, self.state, self.transport)
        self.engine.activate()
        self.started = True
        self.monitor = asyncio.create_task(self.engine.watch())

    def status(self, event='P29_FORWARDING_STATUS'):
        gate = getattr(self.engine, 'gate', None)
        return {'event': event, 'input_mode': 'FORWARDED_COPY',
            'transport_started': self.started, 'new_attempts': self.transport.attempts,
            'diagnostic': self.addon.diagnostic(), 'copy_analysis': self.addon.analysis.diagnostic(),
            'forwarding': self.addon.forwarding.snapshot(gate) if gate is not None else None,
            'http_progress': self.addon.http_progress_snapshot(), 'product_result': 'incomplete',
            'setup_stage': getattr(self.engine, 'setup_stage', 'NOT_STARTED'),
            'setup_failure': self.setup_failure}

    async def close(self, code='P26_HOST_CLOSED'):
        if self.closed_result is not None:
            return self.closed_result
        if self.transport.state == 'CLOSED':
            code = self.transport.code
        self.transport.close(code)
        complete = True
        if self.engine:
            try:
                complete = await self.engine.close()
            except Exception:
                complete = False
        if self.monitor:
            self.monitor.cancel()
            await asyncio.gather(self.monitor, return_exceptions=True)
        # The network is released before waiting for any parser/publication work.
        try:
            await asyncio.to_thread(self.addon.finish_analysis, code)
        except Exception:
            complete = False
        self.addon.clear()
        if self.lock_identity:
            try:
                metadata = (self.root / LOCK).lstat()
                if (metadata.st_dev, metadata.st_ino) != self.lock_identity:
                    raise ValueError()
                if complete:
                    host._update_state(self.root, self.state, self.transport)
                    (self.root / LOCK).unlink()
            except Exception:
                complete = False
        result = self.status('P29_FORWARDING_CLOSED')
        result.update(cleanup='COMPLETE' if complete else 'INCOMPLETE',
            intercept_cleared=self.engine is None or self.engine.intercept_cleared,
            active_streams_count=len(self.engine.tasks) if self.engine else 0)
        if not result['intercept_cleared']:
            # Keep the last persisted OPEN state and the lock if interception
            # could still be active. A closed parser is not network cleanup.
            result['diagnostic'].update(live_capture_latch='OPEN', execution_latch='OPEN')
        self.closed_result = result
        return result


@contextlib.asynccontextmanager
async def command_input():
    """Bounded ASCII commands, independent of a tool call's lifetime."""
    loop, queue, pending = asyncio.get_running_loop(), asyncio.Queue(maxsize=64), bytearray()
    fd = sys.stdin.fileno()
    was_blocking = os.get_blocking(fd)
    saved_signals = {}

    def stop():
        while not queue.empty():
            queue.get_nowait()
        queue.put_nowait('stop')

    def readable():
        try:
            data = os.read(fd, 256)
        except BlockingIOError:
            return
        if not data:
            loop.remove_reader(fd)
            stop()
            return
        pending.extend(data)
        if len(pending) > 1024:
            pending.clear()
            stop()
            return
        while b'\n' in pending:
            line, _, tail = pending.partition(b'\n')
            pending[:] = tail
            if line not in (b'start', b'status', b'layout', b'stop') or queue.full():
                stop()
                return
            queue.put_nowait(line.decode('ascii'))

    try:
        os.set_blocking(fd, False)
        loop.add_reader(fd, readable)
        for sig in (signal.SIGINT, signal.SIGTERM):
            saved_signals[sig] = signal.getsignal(sig)
            loop.add_signal_handler(sig, stop)
        yield queue
    finally:
        loop.remove_reader(fd)
        os.set_blocking(fd, was_blocking)
        for sig, handler in saved_signals.items():
            loop.remove_signal_handler(sig)
            signal.signal(sig, handler)


async def _start_with_controls(receiver, commands):
    starting = asyncio.create_task(receiver.start())
    command_task = None
    try:
        while not starting.done():
            command_task = asyncio.create_task(commands.get())
            await asyncio.wait((starting, command_task), return_when=asyncio.FIRST_COMPLETED)
            if command_task.done():
                command = command_task.result()
                if command == 'stop':
                    return False
                if command in ('status', 'layout'):
                    host._emit(receiver.status())
                elif command == 'start':
                    host._emit({'event': 'P29_START_ALREADY_USED'})
                else:
                    raise IdentificationError('P26_ARGUMENTS_INVALID')
            else:
                command_task.cancel()
                await asyncio.gather(command_task, return_exceptions=True)
        await starting
        return True
    finally:
        tasks = [task for task in (starting, command_task) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_receiver(receiver, commands):
    code = 'P26_START_NOT_REQUESTED'
    try:
        host._emit(receiver.status('P29_RECEIVER_PREPARED'))
        while receiver.transport.state != 'CLOSED':
            try:
                command = await asyncio.wait_for(commands.get(), .1)
            except asyncio.TimeoutError:
                if receiver.transport.state == 'ACTIVE':
                    receiver.transport.active()
                continue
            if command == 'stop':
                code = 'P26_HOST_CLOSED'
                break
            if command == 'start':
                if receiver.started:
                    host._emit({'event': 'P29_START_ALREADY_USED'})
                    continue
                if not await _start_with_controls(receiver, commands):
                    code = 'P26_HOST_CLOSED'
                    break
                host._emit(receiver.status('P29_FORWARDING_STARTED'))
            elif command in ('status', 'layout'):
                # Snapshot contains fixed diagnostics, not field values.
                host._emit(receiver.status())
            else:
                raise IdentificationError('P26_ARGUMENTS_INVALID')
        if receiver.transport.state == 'CLOSED':
            code = receiver.transport.code
    except asyncio.CancelledError:
        code = 'P26_CANCELLED'
        raise
    except asyncio.TimeoutError:
        code = 'P26_RECEIVER_SETUP_TIMEOUT' if not receiver.started else 'P26_HOST_EXCEPTION'
    except Exception:
        code = 'P26_RECEIVER_SETUP_FAILED' if not receiver.started else 'P26_HOST_EXCEPTION'
    finally:
        result = await receiver.close(code)
        host._emit(result)
    return result


async def serve_forwarded(root):
    receiver = prepare_receiver(root)
    loop = asyncio.get_running_loop()
    prior_handler, prior_output = loop.get_exception_handler(), host._event_output
    fd = sys.stdout.fileno()
    was_blocking = os.get_blocking(fd)
    output = host.EventOutput(loop, fd,
        lambda: receiver.transport.close('P26_DIAGNOSTIC_OUTPUT_FAILED'))
    try:
        os.set_blocking(fd, False)
        host._event_output = output
        loop.set_exception_handler(receiver.addon.forwarding.loop_exception)
        async with command_input() as commands:
            result = await run_receiver(receiver, commands)
        result['diagnostic_output_complete'] = await output.finish()
        return result
    finally:
        host._event_output = prior_output
        loop.set_exception_handler(prior_handler)
        os.set_blocking(fd, was_blocking)
