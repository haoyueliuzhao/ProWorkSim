"""Live budget checks preserve process identity and the existing worker clock."""

import copy
import os
import signal
import subprocess
import sys

import pytest

from scripts import collaboration_carrier_v026 as worker
from scripts import extend_collaboration_budget_v026 as extension
from scripts.evaluate_work_v022 import reference, write
from scripts.run_collaboration_carrier_v026 import stop_reason


def test_extended_budget_keeps_original_start_and_task_limits():
    plan = worker.FIXED_LIMITS
    state = {'started_at': 0, 'budget_seconds': 7174}
    kwargs = {'root_started': 0, 'own_rss': 0, 'all_rss': 0, 'size': 0,
              'free_bytes': 2*1024**3}
    task = {'kind': 'episode', 'started_at': 7100}
    assert stop_reason(plan, state, task, now=7114, **kwargs) == 'worker_gpu_budget'
    state['budget_seconds'] = extension.CAPS['worker-0']
    assert stop_reason(plan, state, task, now=7114, **kwargs) is None
    assert stop_reason(plan, state, task, now=8240, **kwargs) == 'task_time_budget'
    task['started_at'] = 14300
    assert stop_reason(plan, state, task, now=14314, **kwargs) == 'worker_gpu_budget'


def fixture(tmp_path):
    plan = {'version': 'reciprocal-carrier-development-v0.26-r2',
            'previous_attempt': {'budget_charge_seconds': 52},
            'resource_caps': {'worker-0': 7174, 'worker-1': 7174}}
    write(tmp_path/'plan.json', plan)
    source = {'scope': 'explicit process metadata test fixture'}
    states, bindings, assignments = {}, {}, {}
    for i, name in enumerate(extension.CAPS):
        bound = {'process': {'pid': i+100, 'start_ticks': i+1000},
                 'gpu': [0, 4][i], 'gpu_uuid': 'GPU-'+str(i), 'started_at': 2000+i}
        assignments[name] = [{'slot_id': name+'-fixture'}]
        bindings[name] = bound
        states[name] = {'status': 'running', 'attempted': True, 'pid': i+100,
                        'worker_start_ticks': i+1000, 'gpu': bound['gpu'],
                        'gpu_uuid': bound['gpu_uuid'], 'started_at': bound['started_at'],
                        'budget_seconds': 7174, 'slots': assignments[name], 'source': source}
    value = {'version': extension.VERSION, 'resource_caps': extension.CAPS,
             'cumulative_gpu_seconds_cap': 28800, 'own_gpu_memory_mib': 81920, 'additional_episodes': 0,
             'parameter_updates': 0, 'automatic_recovery': False, 'automatic_successors': [],
             'original_plan': reference(tmp_path/'plan.json'), 'worker_source': source,
             'workers': bindings}
    summary = {'plan': value['original_plan'], 'source': source, 'worker_assignments': assignments}
    return value, summary, states


def test_extension_rejects_rebound_workers_or_reset_elapsed_clock(tmp_path):
    value, summary, states = fixture(tmp_path)
    extension.validate_declaration(value, summary, states)
    changed = copy.deepcopy(states)
    changed['worker-0']['started_at'] += 1
    with pytest.raises(ValueError, match='changed identity'):
        extension.validate_declaration(value, summary, changed)
    changed = copy.deepcopy(states)
    changed['worker-1']['worker_start_ticks'] += 1
    with pytest.raises(ValueError, match='changed identity'):
        extension.validate_declaration(value, summary, changed)
    value['additional_episodes'] = 1
    with pytest.raises(ValueError, match='existing sixteen-slot'):
        extension.validate_declaration(value, summary, states)


@pytest.mark.skipif(not hasattr(os, 'pidfd_open'), reason='Use the resident Python for Linux pidfd integration')
def test_pidfd_pause_resume_does_not_follow_reused_identity():
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    fd = None
    try:
        import time
        for _ in range(100):
            spec = extension.process_spec(process.pid)
            if spec['command_sha256'] != extension.digest(b''):
                break
            time.sleep(.01)
        wrong = {**spec, 'start_ticks': spec['start_ticks']+1}
        with pytest.raises(ValueError, match='identity changed'):
            extension.open_verified(wrong)
        fd = extension.open_verified(spec)
        extension.pause(fd, process.pid)
        assert extension.worker_identity(process.pid)['state'] in {'T', 't'}
        extension.send(fd, signal.SIGCONT)
        assert not extension.exited(fd)
        extension.send(fd, signal.SIGTERM)
        process.wait(timeout=5)
        assert extension.exited(fd)
    finally:
        if fd is not None:
            extension.send(fd, signal.SIGCONT)
            os.close(fd)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
