"""No HTTP/Docker/services: private FD lifetimes and queue admission behavior."""
import errno
import gc
import os
import sqlite3

import pytest

from proworksim import software_benchmark_fd_v085 as fd
from proworksim import software_benchmark_deepseek_api_v064 as api
from test_async_queue_v082 import API, Fixture, execute, planned


def observed(used=20, limit=16384):
    return {'fd_used': used, 'soft_limit': limit, 'hard_limit': limit, 'fd_free': max(0, limit-used)}


def test_fd_reserve_hysteresis_and_original_ceiling_are_preserved():
    state = {'used': 15890}
    guard = fd.FDGuard(probe=lambda: observed(state['used']))
    calls = []
    ceiling = guard.admission(lambda: calls.append(True) or 48, active=lambda: 20)
    assert ceiling() == 0 and not calls
    state['used'] = 15500
    assert ceiling() == 0 and not calls
    state['used'] = 15000
    assert ceiling() == 47 and calls == [True]
    state['used'] = 100
    assert ceiling() == 48


def test_only_descriptor_exhaustion_is_a_temporary_admission_pause():
    guard = fd.FDGuard(probe=observed)
    def exhausted():
        raise OSError(errno.EMFILE, 'fixture')
    assert guard.admission(exhausted)() == 0
    assert guard.snapshot()['last_errno'] == errno.EMFILE
    other = fd.FDGuard(probe=observed)
    def denied():
        raise PermissionError(errno.EACCES, 'identity evidence not authorized')
    with pytest.raises(PermissionError):
        other.admission(denied)()


def test_fd_observation_failure_does_not_invent_budget_admission():
    class Money(API):
        def budget_status(self):
            raise AssertionError('No money read can be trusted with unavailable FD observation')
    def unavailable():
        raise OSError(errno.EMFILE, 'fixture')
    runtime = fd.RuntimeView(Money(), fd.FDGuard(probe=unavailable))
    result = runtime.budget_status()
    assert result['state'] == 'waiting_fd_pressure'
    assert result['can_start_generation'] is False
    assert result['stale_budget_admission'] is False
    assert 'remaining_CNY' not in result


@pytest.mark.parametrize('reason,waits', [('[Errno 24] Too many open files', True),
    ('cash_commitment_exceeded_cap', False), ('unable to open database file', False)])
def test_runtime_preserves_real_cash_and_identity_halts(reason, waits):
    class Money(API):
        def budget_status(self):
            return {'state': 'shared_halted', 'can_start_generation': False, 'reason': reason}
    result = fd.RuntimeView(Money(), fd.FDGuard(probe=observed)).budget_status()
    assert result['state'] == ('waiting_fd_pressure' if waits else 'shared_halted')


def test_sqlite_context_closes_on_commit_and_rollback(tmp_path):
    path = tmp_path/'connection.sqlite3'
    with fd.closing_connect(path) as db:
        db.execute('CREATE TABLE checked(value INTEGER)')
        db.execute('INSERT INTO checked VALUES(1)')
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        db.execute('SELECT 1')
    with pytest.raises(RuntimeError):
        with fd.closing_connect(path) as other:
            other.execute('INSERT INTO checked VALUES(2)')
            raise RuntimeError('rollback fixture')
    with fd.closing_connect(path) as final:
        assert final.execute('SELECT value FROM checked').fetchall() == [(1,)]


def test_ledger_constructor_fd_growth_is_removed_without_waiting_for_gc(tmp_path):
    path = tmp_path/'ledger.sqlite3'
    fd.ManagedLedger(path)
    gc.collect()
    enabled = gc.isenabled()
    gc.disable()
    try:
        initial = len(os.listdir('/proc/self/fd'))
        for _ in range(12):
            fd.ManagedLedger(path)
        managed_growth = len(os.listdir('/proc/self/fd'))-initial
        assert managed_growth <= 1
        for _ in range(12):
            fd.original_api.BudgetLedger(path)
        original_growth = len(os.listdir('/proc/self/fd'))-initial-managed_growth
        assert original_growth >= 12
    finally:
        if enabled:
            gc.enable()
        gc.collect()
    with fd.closing_connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM requests').fetchone()[0] == 0


def test_runtime_initialization_and_episode_forks_use_private_closing_ledger(tmp_path):
    class Runtime:
        def initialize_for_run(self):
            self.client = api.DeepSeekClient(ledger_path=tmp_path/'private.sqlite3',
                api_key='cpu-fixture-unused-key', allowed_tool_names={'fixture'})
            return {'network_calls': 0}
    runtime = Runtime()
    wrapped = fd.RuntimeView(runtime, fd.FDGuard(probe=observed))
    assert wrapped.initialize_for_run() == {'network_calls': 0}
    assert isinstance(runtime.client, fd.ManagedClient)
    fork = runtime.client.fork_for_episode()
    assert isinstance(fork.ledger, fd.ManagedLedger)
    assert fork.ledger.path == runtime.client.ledger.path
    assert api.DeepSeekClient is fd.original_api.DeepSeekClient


def test_single_admission_emfile_does_not_cancel_or_replay_active_queue(tmp_path):
    fixture, rows = Fixture(tmp_path), planned(tmp_path, 8)
    clock = [0]
    guard = fd.FDGuard(probe=observed, clock=lambda: clock[0])
    calls = 0
    def admission():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError(errno.EMFILE, 'resource-claims/active-actor fixture')
        return 2
    protected = guard.admission(admission, active=lambda: fixture.active_scores)
    def limit():
        clock[0] += 2
        return protected()
    result, _, _, _ = execute(tmp_path, fixture, rows, generation_limit=limit,
                              api_runtime=fd.RuntimeView(API(), guard))
    assert calls > 2 and result['failure'] is None
    assert len(result['generation']) == len(result['scores']) == 8
    assert all(count == 1 for count in fixture.calls.values())
    assert all(count == 1 for count in fixture.score_calls.values())
