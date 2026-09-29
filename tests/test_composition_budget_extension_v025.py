"""Real small parent/child handover controls, never a model or GPU process."""
import copy
import fcntl
import json
import os
import signal
import subprocess
import sys
import time

import pytest

from scripts.extend_composition_budget_v025 import (
    EFFECTIVE, ORIGINAL, UNCHANGED, alive, bound_process, process_identity,
    resource_reason, stop_bound_worker, suspended_observer,
)

PARENT = r'''
import fcntl,json,subprocess,sys,time
from pathlib import Path
root=Path(sys.argv[1])
lock=(root/'original.lock').open('a+')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
child=subprocess.Popen([sys.executable,'-c',"import sys,time;from pathlib import Path;p=Path(sys.argv[1]);[(p.write_text(str(i)),time.sleep(.08)) for i in range(12)]",str(root/'ticks')],start_new_session=True)
(root/'pids.json').write_text(json.dumps({'worker':child.pid}))
start=time.time()
while True:
    code=child.poll()
    if code is not None:
        (root/'result.json').write_text(json.dumps({'exit_code':code,'successor_runs':1 if code==0 else 0}))
        break
    if time.time()-start>1.4:
        child.terminate();child.wait()
        (root/'result.json').write_text(json.dumps({'old_deadline_killed_worker':True}))
        break
    time.sleep(.02)
'''


def wait_for(predicate, timeout=4):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.01)
    raise AssertionError('Bounded CPU process fixture did not reach its boundary')


@pytest.mark.parametrize('mode', ['natural_exit', 'resource_stop', 'guard_exception'])
def test_parent_lock_child_progress_real_exit_and_failure_cleanup(tmp_path, mode):
    parent = subprocess.Popen([sys.executable, '-c', PARENT, str(tmp_path)])
    worker = None
    try:
        wait_for(lambda: (tmp_path/'pids.json').exists())
        pid = json.loads((tmp_path/'pids.json').read_text())['worker']
        observer, worker = process_identity(parent.pid), process_identity(pid)
        wait_for(lambda: (tmp_path/'ticks').exists())
        if mode == 'guard_exception':
            with pytest.raises(RuntimeError, match='explicit CPU'):
                with suspended_observer(observer, worker):
                    raise RuntimeError('explicit CPU guard failure')
        else:
            with suspended_observer(observer, worker):
                assert bound_process(observer)['state'] == 'T'
                assert bound_process(worker)['state'] != 'T'
                with (tmp_path/'original.lock').open('a+') as another:
                    with pytest.raises(BlockingIOError):
                        fcntl.flock(another, fcntl.LOCK_EX|fcntl.LOCK_NB)
                if mode == 'natural_exit':
                    wait_for(lambda: bound_process(worker)['state'] == 'Z')
                    assert (tmp_path/'ticks').read_text() == '11'
                    # Exceed the OLD parent deadline while the worker is already
                    # a zombie. Parent must reap success before checking timeout.
                    time.sleep(.6)
                else:
                    stop_bound_worker(worker)
        parent.wait(timeout=4)
        result = json.loads((tmp_path/'result.json').read_text())
        assert 'old_deadline_killed_worker' not in result
        assert result['exit_code'] == (0 if mode == 'natural_exit' else -15)
        assert result['successor_runs'] == (1 if mode == 'natural_exit' else 0)
    finally:
        if parent.poll() is None:
            os.kill(parent.pid, signal.SIGCONT)
        if worker:
            stop_bound_worker(worker)
        if parent.poll() is None:
            parent.terminate()
            parent.wait(timeout=4)


def test_identity_bounds_and_unchanged_resource_gates():
    me = process_identity(os.getpid())
    wrong = copy.deepcopy(me)
    wrong['start_ticks'] += 1
    with pytest.raises(ValueError, match='identity changed'):
        bound_process(wrong)
    amendment = {'timing': {'run_started_at': 0., 'stage_started_at': 0.}}
    task = {'kind': 'update', 'started_at': 0.}
    sample = {'gpus': {'returncode': 0}, 'processes': {'returncode': 0}}
    args = (amendment, task, sample, 45000, 20*1024**3, 3*1024**3)
    assert resource_reason(*args, ORIGINAL['stage_seconds']+10) is None
    assert resource_reason(*args, EFFECTIVE['update_seconds']-30) == 'amended_task_time_budget'
    assert resource_reason(amendment, task, sample, 57344, 0, 0, 100) == 'own_gpu_memory_limit'
    assert resource_reason(amendment, task, sample, 0, UNCHANGED['host_rss_bytes']+1, 0, 100) == 'host_rss_limit'
    assert resource_reason(amendment, task, sample, 0, 0, UNCHANGED['artifact_bytes'], 100) == 'artifact_limit'
    assert resource_reason(amendment, {'kind':'boundary','started_at':0.}, sample, 0, 0, 0, 570) == 'unchanged_task_time_budget'
    sample['gpus']['returncode'] = 1
    assert resource_reason(amendment, task, sample, 0, 0, 0, 100) == 'resource_query_failed'


def test_exit_transition_and_orphan_cleanup(tmp_path, monkeypatch):
    from scripts import extend_composition_budget_v025 as guard
    real_identity = guard.process_identity
    me = real_identity(os.getpid())
    empty = {**me, 'state': 'R', 'command_sha256': guard.digest(b'')}
    with monkeypatch.context() as patch:
        patch.setattr(guard, 'process_identity', lambda pid: empty)
        assert guard.alive(me) is True
        assert guard.bound_process(me)['empty_cmdline_exit_transition'] is True
    parent = subprocess.Popen([sys.executable, '-c', PARENT, str(tmp_path)])
    worker = None
    try:
        wait_for(lambda: (tmp_path/'pids.json').exists())
        pid = json.loads((tmp_path/'pids.json').read_text())['worker']
        wait_for(lambda: (tmp_path/'ticks').exists())
        observer, worker = real_identity(parent.pid), real_identity(pid)
        with pytest.raises(RuntimeError, match='explicit lost'):
            with suspended_observer(observer, worker):
                parent.kill()
                parent.wait(timeout=3)
                wait_for(lambda: real_identity(pid)['ppid'] != observer['pid'])
                raise RuntimeError('explicit lost observer CPU control')
        assert not alive(worker, allow_reparented=True)
    finally:
        if worker:
            stop_bound_worker(worker, allow_reparented=True)
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)
