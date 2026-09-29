"""Synthetic telemetry observations only: no GPU model or process signals."""
import copy
import json
import subprocess

import pytest

from proworksim import resource_monitor_v025 as monitoring

UUID = 'GPU-target'
PID = 1357
START = 2468


def sample(at, memory=1024, *, gpu_ok=True, process_ok=True):
    result = {'time': at, 'scope': {'kind': 'target_gpu', 'gpu_selector': '4'},
              'worker_identity': {'pid': PID, 'available': True, 'alive': True, 'start_ticks': START},
              'gpus': {'returncode': 0, 'stdout': f'4, {UUID}, NVIDIA A100, 70000, 81920, 93\n', 'stderr': ''},
              'processes': {'returncode': 0, 'stdout': f'{UUID}, {PID}, {memory}, worker\n', 'stderr': ''}}
    for key, ok in [('gpus', gpu_ok), ('processes', process_ok)]:
        if not ok:
            result[key] = {'returncode': None, 'stdout': '', 'stderr': 'synthetic timeout',
                           'error': {'type': 'TimeoutExpired', 'message': 'synthetic timeout', 'timeout_seconds': 5}}
    return result


def guard():
    return monitoring.TelemetryGuard(4, UUID, START, worker_pid=PID)


def observe(g, s, now):
    return g.observe(s, now, PID, 4, own_memory_limit_mib=57344)


def test_timeout_recovery_keeps_partial_fresh_measurement_and_stale_reference_separate():
    g = guard()
    assert observe(g, sample(0), 1)['fresh']
    failure = sample(10, 2048, gpu_ok=False)
    original = copy.deepcopy(failure)
    r = observe(g, failure, 20)
    assert failure == original
    assert r['failure_since'] == 10 and r['failure_seconds'] == 10
    assert r['consecutive_failures'] == 1 and r['stop_reason'] is None
    assert not r['fresh'] and r['stale'] and r['last_success_reference_only']
    assert r['own_gpu_memory_mib'] == 2048 and r['own_memory_fresh']
    assert r['last_success']['own_gpu_memory_mib'] == 1024
    unavailable = observe(g, sample(40, process_ok=False), 50)
    assert unavailable['own_gpu_memory_mib'] is None
    assert not unavailable['own_memory_fresh']
    assert json.loads(json.dumps(unavailable))['own_gpu_memory_mib'] is None
    restored = observe(g, sample(70, 3000), 71)
    assert restored['fresh'] and not restored['stale']
    assert restored['failure_since'] is None and restored['consecutive_failures'] == 0
    assert restored['failures_total'] == 2 and restored['recovered_after_seconds'] == 61
    assert restored['own_gpu_memory_mib'] == 3000


def test_continuous_failure_has_exact_120_second_bound_from_first_query_start():
    g = guard()
    first = observe(g, sample(100, gpu_ok=False, process_ok=False), 110)
    assert first['failure_since'] == 100 and first['own_gpu_memory_mib'] is None
    assert first['last_success'] is None and not first['stale']
    assert observe(g, sample(210, process_ok=False), 219)['stop_reason'] is None
    expired = observe(g, sample(215, gpu_ok=False), 220)
    assert expired['stop_reason'] == 'telemetry_unavailable_budget'
    assert expired['consecutive_failures'] == 3 and expired['failure_seconds'] == 120


@pytest.mark.parametrize('gpu_ok', [True, False])
def test_fresh_process_measurement_over_limit_stops_even_during_gpu_query_failure(gpu_ok):
    result = observe(guard(), sample(0, 57344, gpu_ok=gpu_ok), 5)
    assert result['stop_reason'] == 'own_gpu_memory_limit'
    assert result['own_gpu_memory_mib'] == 57344 and result['own_memory_fresh']


@pytest.mark.parametrize('rows', [f'{UUID}, {PID}, N/A, worker\n', f'{UUID}, {PID}\n',
                                 f'{UUID}, {PID}, 100, worker\n{UUID}, {PID}, 100, worker\n'])
def test_incomplete_or_duplicate_process_records_never_become_zero(rows):
    s = sample(0)
    s['processes']['stdout'] = rows
    r = observe(guard(), s, 5)
    assert r['own_gpu_memory_mib'] is None and not r['process_query_complete']
    assert not r['fresh'] and r['stop_reason'] is None
    assert any(e['kind'] == 'incomplete_process_measurement' for e in r['errors'])


def test_complete_empty_process_list_means_no_cuda_allocation_not_dead_os_worker():
    s = sample(0)
    s['processes']['stdout'] = ''
    r = observe(guard(), s, 1)
    assert r['fresh'] and r['own_gpu_memory_mib'] == 0
    assert r['stop_reason'] is None


@pytest.mark.parametrize('alteration,reason', [('start', 'worker_identity_changed'),
    ('gone', 'worker_lost'), ('unreadable', 'worker_identity_unavailable'), ('gpu', 'gpu_identity_changed')])
def test_worker_or_gpu_identity_failures_stop_without_grace(alteration, reason):
    s = sample(0)
    if alteration == 'start':
        s['worker_identity']['start_ticks'] += 1
    elif alteration == 'gone':
        s['worker_identity'].update(available=False, alive=False)
    elif alteration == 'unreadable':
        s['worker_identity'].update(available=False, alive=None)
    else:
        s['gpus']['stdout'] = s['gpus']['stdout'].replace(UUID, 'GPU-other')
    r = observe(guard(), s, 5)
    assert r['stop_reason'] == reason
    assert r['own_gpu_memory_mib'] is None


def test_reusing_old_sample_does_not_reset_failure_timer_or_reuse_memory():
    g = guard()
    original = sample(0)
    assert observe(g, original, 1)['fresh']
    repeated = observe(g, original, 20)
    assert not repeated['fresh'] and repeated['own_gpu_memory_mib'] is None
    assert repeated['last_success']['sample_time'] == 0
    assert observe(g, original, 140)['stop_reason'] == 'telemetry_unavailable_budget'


def test_target_queries_keep_timeouts_and_raw_errors_without_signalling(monkeypatch):
    calls = []
    def runner(command, **kwargs):
        calls.append((command, kwargs))
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, 5, output=b'partial stdout', stderr=b'raw stderr')
        return subprocess.CompletedProcess(command, 0, stdout=f'{UUID}, {PID}, 123, worker\n', stderr='')
    monkeypatch.setattr(monitoring, 'worker_identity', lambda pid: {'pid': pid, 'available': True, 'alive': True, 'start_ticks': START})
    ticks = iter([0, 0, 5, 5, 6, 6])
    result = monitoring.target_resources(UUID, worker_pid=PID, runner=runner, clock=lambda: next(ticks))
    assert result['time'] == 0 and result['finished_at'] == 6
    assert len(calls) == 2
    assert all('--id=' + UUID in command and kwargs['timeout'] == 5 for command, kwargs in calls)
    assert result['gpus']['error']['stdout'] == 'partial stdout'
    assert result['gpus']['error']['stderr'] == 'raw stderr'
    assert result['gpus']['returncode'] is None and result['processes']['returncode'] == 0
    r = observe(guard(), result, 6)
    assert r['failure_since'] == 0 and r['failure_seconds'] == 6
    assert r['own_gpu_memory_mib'] == 123 and r['stop_reason'] is None


def test_success_output_older_than_grace_cannot_masquerade_as_fresh():
    r = observe(guard(), sample(0), 120)
    assert not r['fresh'] and r['own_gpu_memory_mib'] is None
    assert r['failure_since'] == 0 and r['stop_reason'] == 'telemetry_unavailable_budget'


@pytest.mark.parametrize('bad_first', [True, False])
def test_unrelated_incomplete_row_cannot_hide_new_own_memory_breach(bad_first):
    s = sample(0, 60000)
    bad = f'{UUID}, 9876, N/A, other-worker\n'
    valid = s['processes']['stdout']
    s['processes']['stdout'] = bad + valid if bad_first else valid + bad
    r = observe(guard(), s, 5)
    assert r['own_gpu_memory_mib'] is None and not r['fresh']
    assert r['own_memory_observed_lower_bound_mib'] == 60000
    assert r['own_memory_lower_bound_fresh']
    assert r['stop_reason'] == 'own_gpu_memory_limit'
