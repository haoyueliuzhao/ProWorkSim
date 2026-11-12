"""Private FD ownership and conservative admission for the API successor.

No host limits are changed here. A launcher sets the new service's own limit;
unknown FD or budget evidence blocks admission rather than declaring it ready.
"""
from __future__ import annotations

import errno
import os
import resource
import sqlite3
import threading
import time
from types import SimpleNamespace

from . import software_benchmark_deepseek_api_v064 as original_api
from .software_benchmark_deepseek_runtime_v069 import private_function

VERSION = 'v085-private-FD-lifetime-and-admission-r1'


def is_fd_exhaustion(error):
    return isinstance(error, OSError) and error.errno in {errno.EMFILE, errno.ENFILE}


def descriptor_snapshot():
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    with os.scandir('/proc/self/fd') as entries:
        used = sum(1 for _ in entries)-1  # This observation's directory FD.
    if soft <= 0 or hard <= 0 or used < 0:
        raise ValueError('A finite verified process FD boundary is required')
    return {'fd_used': used, 'soft_limit': soft, 'hard_limit': hard,
            'fd_free': max(0, soft-used), 'observation_unix': time.time()}


class FDGuard:
    def __init__(self, *, minimum_free=512, resume_free=1024, fd_per_new_episode=32,
                 probe=descriptor_snapshot, clock=time.monotonic):
        if not 0 < minimum_free < resume_free or fd_per_new_episode <= 0:
            raise ValueError('FD reserve and hysteresis must be positive and ordered')
        self.minimum_free, self.resume_free = minimum_free, resume_free
        self.fd_per_new_episode, self.probe, self.clock = fd_per_new_episode, probe, clock
        self.lock = threading.Lock()
        self.paused, self.retry_at = False, 0.0
        self.last_errno = None
        self.last = {}

    def note_error(self, error):
        if not is_fd_exhaustion(error):
            raise error
        with self.lock:
            self.paused = True
            self.retry_at = max(self.retry_at, self.clock()+1)
            self.last_errno = error.errno

    def snapshot(self):
        try:
            value = self.probe()
            if (any(type(value.get(key)) is not int for key in ('fd_used', 'fd_free', 'soft_limit', 'hard_limit'))
                    or value['fd_used'] < 0 or value['soft_limit'] <= 0
                    or value['fd_free'] != max(0, value['soft_limit']-value['fd_used'])):
                raise ValueError('Inconsistent FD count and process limit')
        except (OSError, ValueError) as error:
            with self.lock:
                self.paused = True
                self.last = {'version': VERSION, 'admit': False, 'qualified': False,
                    'reason': 'fd_observation_unavailable', 'error_type': type(error).__name__,
                    'last_errno': getattr(error, 'errno', None), 'observation_unix': time.time()}
                return dict(self.last)
        with self.lock:
            if value['fd_free'] < self.minimum_free:
                self.paused = True
            elif value['fd_free'] >= self.resume_free and self.clock() >= self.retry_at:
                self.paused = False
            self.last = {**value, 'version': VERSION, 'qualified': True, 'admit': not self.paused,
                'reason': 'fd_reserve_pause' if self.paused else 'fd_reserve_available',
                'minimum_free': self.minimum_free, 'resume_free': self.resume_free,
                'last_errno': self.last_errno, 'process_limit_modified': False}
            return dict(self.last)

    def admission(self, original_ceiling, *, active=lambda: 0):
        """Only FD exhaustion in this admission read pauses; other faults escape."""
        def ceiling():
            observed = self.snapshot()
            if not observed['admit']:
                return 0
            try:
                value = original_ceiling()
                existing = active()
            except OSError as error:
                if not is_fd_exhaustion(error):
                    raise
                self.note_error(error)
                return 0
            if type(value) is not int or not 0 <= value <= 48 or type(existing) is not int or existing < 0:
                raise ValueError('FD gate cannot expand the original generation ceiling')
            additional = max(0, (observed['fd_free']-self.minimum_free)//self.fd_per_new_episode)
            return min(value, existing+additional)
        return ceiling


class ClosingConnection(sqlite3.Connection):
    """Keep SQLite commit/rollback semantics, then release owned descriptors."""
    def __exit__(self, *exc):
        try:
            return super().__exit__(*exc)
        finally:
            self.close()


def closing_connect(*args, **kwargs):
    if 'factory' in kwargs:
        raise ValueError('The private original ledger preflight has no custom connection factory')
    return sqlite3.connect(*args, **kwargs, factory=ClosingConnection)


_sqlite_view = SimpleNamespace(**{**vars(sqlite3), 'connect': closing_connect})


class ManagedLedger(original_api.BudgetLedger):
    # The original constructor's raw read-only policy check now closes exactly
    # at its with-boundary. Existing _connect() already has a finally close.
    __init__ = private_function(original_api.BudgetLedger.__init__, sqlite3=_sqlite_view)


class ManagedClient(original_api.DeepSeekClient):
    __init__ = private_function(original_api.DeepSeekClient.__init__, BudgetLedger=ManagedLedger)


class RuntimeView:
    """Delegate actual HTTP/money work; keep temporary observation failure local."""
    def __init__(self, runtime, guard):
        self.runtime, self.guard = runtime, guard

    def __getattr__(self, name):
        return getattr(self.runtime, name)

    def initialize_for_run(self):
        original = self.runtime.initialize_for_run.__func__
        api = original.__globals__.get('api')
        if api is None or api.DeepSeekClient is not original_api.DeepSeekClient:
            raise ValueError('Only the original frozen API client constructor may be privately bound')
        view = SimpleNamespace(**{**vars(api), 'DeepSeekClient': ManagedClient})
        return private_function(original, api=view)(self.runtime)

    def _waiting(self):
        return {'version': VERSION, 'state': 'waiting_fd_pressure', 'can_start_generation': False,
                'temporary_wait': True, 'fd_pressure': self.guard.snapshot(),
                'budget_observation_unavailable': True, 'stale_budget_admission': False,
                'cancel_existing_requests': False, 'ledger_records_modified': False}

    def budget_status(self):
        if not self.guard.snapshot()['admit']:
            return self._waiting()
        try:
            value = self.runtime.budget_status()
        except OSError as error:
            if not is_fd_exhaustion(error):
                raise
            self.guard.note_error(error)
            return self._waiting()
        # The original reader captures OSError into an explicit reason string.
        # Only exact OS errno evidence is softened; ordinary ledger corruption,
        # unavailable SQLite databases and monetary hard halts stay unchanged.
        reason = value.get('reason')
        if (value.get('state') == 'shared_halted' and isinstance(reason, str)
                and ('[Errno 24]' in reason or '[Errno 23]' in reason)):
            self.guard.note_error(OSError(errno.EMFILE, 'Original ledger read exhausted descriptors'))
            return self._waiting()
        return value
