"""User-authorized finite extension without restarting the live learner.

Suspend only the original observer PID, retain its lock and Popen ownership,
monitor the same independent worker, then let the observer reap its real status
and execute its untouched successors. Frozen experiment source/plan stay intact.
"""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.composition_evidence_v025 import checked
from scripts.evaluate_work_v022 import reference, write
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import read, resources

VERSION = 'authorized-v025-budget-extension-v1'
ID = 'v025-budget-extension-20260929-01'
ORIGINAL = {'update_seconds': 39600, 'stage_seconds': 43200,
            'plan_gpu_seconds': 208800, 'no_support_gpu_seconds': 84600}
EFFECTIVE = {'update_seconds': 64800, 'stage_seconds': 72000,
             'plan_gpu_seconds': 237600, 'no_support_gpu_seconds': 113400}
UNCHANGED = {'wall_seconds': 259200, 'host_rss_bytes': 68719476736,
             'own_gpu_memory_mib': 57344, 'artifact_bytes': 34359738368}
IDENTITY_FIELDS = ('pid', 'uid', 'start_ticks', 'ppid', 'pgid', 'sid', 'command_sha256')


def process_identity(pid):
    path = Path('/proc') / str(pid)
    try:
        data = (path / 'stat').read_text().rsplit(')', 1)[1].split()
        command = (path / 'cmdline').read_bytes()
        return {'pid': pid, 'uid': path.stat().st_uid, 'state': data[0],
            'ppid': int(data[1]), 'pgid': int(data[2]), 'sid': int(data[3]),
            'start_ticks': int(data[19]), 'command_sha256': digest(command)}
    except (FileNotFoundError, ProcessLookupError):
        return None


def bound_process(expected, *, allow_reparented=False):
    actual = process_identity(expected['pid'])
    if actual is None:
        return None
    stable = tuple(k for k in IDENTITY_FIELDS if k != 'command_sha256'
                   and not (allow_reparented and k == 'ppid'))
    if any(actual[k] != expected[k] for k in stable):
        raise ValueError('Process identity changed; never signal a recycled/unrelated PID')
    # Linux may clear cmdline before stat reaches Z. Equal pid/uid/start/session
    # identity is still this process; an empty command is NOT an exit status.
    # Continue bounded supervision until Z/disappearance or the actual deadline.
    if actual['state'] == 'Z' or actual['command_sha256'] == expected['command_sha256']:
        return actual
    if actual['command_sha256'] == digest(b''):
        return {**actual, 'empty_cmdline_exit_transition': True}
    raise ValueError('Live process command identity changed')


def alive(expected, *, allow_reparented=False):
    state = bound_process(expected, allow_reparented=allow_reparented)
    return state is not None and state['state'] != 'Z'


def stop_bound_worker(expected, *, allow_reparented=False):
    if not alive(expected, allow_reparented=allow_reparented):
        return
    if expected['pgid'] != expected['pid'] or expected['sid'] != expected['pid']:
        raise ValueError('Only the originally independent worker session may be stopped')
    os.killpg(expected['pid'], signal.SIGTERM)
    deadline = time.monotonic() + 5
    while alive(expected, allow_reparented=allow_reparented) and time.monotonic() < deadline:
        time.sleep(.05)
    if alive(expected, allow_reparented=allow_reparented):
        os.killpg(expected['pid'], signal.SIGKILL)
        deadline = time.monotonic() + 5
        while alive(expected, allow_reparented=allow_reparented) and time.monotonic() < deadline:
            time.sleep(.05)
    if alive(expected, allow_reparented=allow_reparented):
        raise RuntimeError('Worker did not exit after the bounded resource stop')


@contextmanager
def suspended_observer(observer, worker):
    """No process-group STOP; child continues and remains reapable by its parent."""
    if (observer['uid'] != os.getuid() or worker['uid'] != os.getuid()
            or worker['ppid'] != observer['pid'] or worker['sid'] != worker['pid']
            or worker['pgid'] != worker['pid'] or observer['pid'] == worker['pid']):
        raise ValueError('Exact same-user observer/independent-worker relationship required')
    if not alive(observer) or not alive(worker):
        raise ValueError('Both bound processes must still be live before handover')
    stopped = False
    yielded = False
    try:
        os.kill(observer['pid'], signal.SIGSTOP)
        stopped = True
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            parent = bound_process(observer)
            if parent and parent['state'] == 'T':
                break
            time.sleep(.02)
        else:
            raise RuntimeError('Original observer did not enter stopped state')
        child = bound_process(worker)
        if child is None or child['state'] in {'Z', 'T', 't'}:
            raise RuntimeError('Worker changed boundary during handover; restore original supervision')
        yielded = True
        yield
    except BaseException:
        if yielded:
            stop_bound_worker(worker, allow_reparented=True)
        raise
    finally:
        if stopped:
            parent = bound_process(observer)
            if parent and parent['state'] != 'Z':
                os.kill(observer['pid'], signal.SIGCONT)


def inspect_run(root, amendment, *, require_pause=False):
    summary = read_json(root / 'supervisor.json')
    state = read_json(root / 'train_base/state.json')
    task = read_json(root / 'train_base/actual/task.json')
    if (summary['source'] != amendment['original_source'] or summary['plan'] != amendment['original_plan']
            or summary['status'] != 'running' or summary['observer_pid'] != amendment['supervisor_identity']['pid']
            or state['status'] != 'running' or state['pid'] != amendment['worker_identity']['pid']
            or state['started_at'] != amendment['timing']['stage_started_at']
            or summary['started_at'] != amendment['timing']['run_started_at']
            or task['pid'] != amendment['worker_identity']['pid']):
        raise ValueError('Original run identity, active stage or start time changed')
    active = []
    for path in root.glob('*/state.json'):
        value = read_json(path)
        if value.get('status') in {'running', 'launch_intent'}:
            active.append(path.parent.name)
    if active != ['train_base']:
        raise ValueError('Only the exact sole base worker can receive this handover')
    if require_pause:
        parent = bound_process(amendment['supervisor_identity'])
        if parent is None or parent['state'] != 'T':
            raise ValueError('Original observer must remain paused while delegated')
    return summary, state, task


def validate_amendment(root, amendment):
    if (amendment.get('version') != VERSION or amendment.get('amendment_id') != ID
            or Path(amendment['run_root']).resolve() != root or amendment.get('stage') != 'train_base'
            or amendment['authorization']['user_instruction'] != '提高预算，继续实验'
            or amendment['original_limits'] != ORIGINAL or amendment['effective_limits'] != EFFECTIVE
            or amendment['unchanged_limits'] != UNCHANGED):
        raise ValueError('Only the recorded finite user-authorized extension is permitted')
    plan = read_json(checked(amendment['original_plan']))
    if (plan['internal_gpu_seconds'] != ORIGINAL['plan_gpu_seconds']
            or plan['resource_caps']['train_base'] != ORIGINAL['stage_seconds']
            or plan['task_caps']['update'] != ORIGINAL['update_seconds']):
        raise ValueError('The frozen original budget must remain unmodified')
    for key in ('supervisor_identity', 'worker_identity'):
        identity = amendment[key]
        if any(field not in identity for field in IDENTITY_FIELDS) or not alive(identity):
            raise ValueError('Bound process is no longer live')
    summary, state, task = inspect_run(root, amendment)
    old_deadline = min(state['started_at'] + ORIGINAL['stage_seconds'],
                       task['started_at'] + ORIGINAL['update_seconds']) - 30
    if (task['kind'] != 'update' or task['started_at'] != amendment['timing']['update_started_at']
            or time.time() >= old_deadline - 30 or state.get('stop_reason') is not None):
        raise ValueError('Handover must occur safely before any original stop condition')
    if time.time() >= summary['started_at'] + UNCHANGED['wall_seconds'] - 30:
        raise ValueError('Original overall wall limit is unchanged')
    return plan


def resource_reason(amendment, task, sample, memory, host_rss, size, now):
    if any(sample[k]['returncode'] != 0 for k in ('gpus', 'processes')):
        return 'resource_query_failed'
    kind = task.get('kind')
    limits = {'update': EFFECTIVE['update_seconds'], 'boundary': 600, 'loading': 900, 'episode': 1200}
    if kind not in limits:
        return 'unknown_task_deadline'
    if now - task['started_at'] >= limits[kind] - 30:
        return 'amended_task_time_budget' if kind == 'update' else 'unchanged_task_time_budget'
    if now - amendment['timing']['stage_started_at'] >= EFFECTIVE['stage_seconds'] - 30:
        return 'amended_stage_time_budget'
    if now - amendment['timing']['run_started_at'] >= UNCHANGED['wall_seconds'] - 30:
        return 'original_wall_time_budget'
    if host_rss > UNCHANGED['host_rss_bytes']:
        return 'host_rss_limit'
    if memory >= UNCHANGED['own_gpu_memory_mib']:
        return 'own_gpu_memory_limit'
    if size >= UNCHANGED['artifact_bytes']:
        return 'artifact_limit'
    return None


def annotate_after_archive(root, amendment_path, checkout, state, state_path):
    """CPU-only, bounded wait for the unchanged original observer's final archive."""
    deadline = state['run_started_at'] + UNCHANGED['wall_seconds'] + 900
    while time.time() < deadline:
        archived = read(root / 'archive-status.json')
        if archived and archived.get('ended_at'):
            from scripts.annotate_composition_budget_v025 import annotate
            result = annotate(root, amendment_path, checkout)
            state['terminal_annotation'] = result
            write(state_path, state)
            if subprocess.check_output(['git', 'branch', '--show-current'], cwd=checkout, text=True).strip() != 'main':
                raise ValueError('Do not switch another working branch to publish reports')
            files = result['files']
            subprocess.run(['git', 'add', '--', *files], cwd=checkout, check=True)
            subprocess.run(['git', 'diff', '--cached', '--check', '--', *files], cwd=checkout, check=True)
            subprocess.run(['git', 'commit', '--only', '-m', 'Record the authorized v0.25 runtime budget extension in terminal reports', '--', *files], cwd=checkout, check=True, timeout=60)
            subprocess.run(['git', 'push', 'origin', 'main'], cwd=checkout, check=True, timeout=120)
            state['terminal_annotation_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
            return
        summary = read(root / 'supervisor.json')
        if not (summary and summary.get('ended_at')) and not alive(state['original_supervisor_identity']):
            raise RuntimeError('Original supervisor disappeared without terminal record')
        time.sleep(30)
    raise TimeoutError('Original finite study/archive did not close within its wall allowance')


def run(root, amendment_path, checkout):
    root, amendment_path, checkout = root.resolve(), amendment_path.resolve(), checkout.resolve()
    amendment = read_json(amendment_path)
    validate_amendment(root, amendment)
    folder = root / 'budget-extension'
    folder.mkdir(exist_ok=True)
    state_path = folder / 'state.json'
    with (folder / 'guard.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if state_path.exists():
            raise ValueError('No automatic handover repeat or worker restart')
        state = {'version': VERSION, 'amendment': reference(amendment_path), 'status': 'validated',
            'guard_pid': os.getpid(), 'guard_source': code_identity(), 'started_at': time.time(),
            'run_started_at': amendment['timing']['run_started_at'],
            'original_supervisor_identity': amendment['supervisor_identity'],
            'worker_identity': amendment['worker_identity'], 'worker_restarted': False,
            'effective_limits': EFFECTIVE, 'unchanged_limits': UNCHANGED}
        write(state_path, state)
        worker, observer = amendment['worker_identity'], amendment['supervisor_identity']
        paused_verified = False
        try:
            with suspended_observer(observer, worker):
                # The parent may have reached a boundary just before STOP. Check
                # again while its files and process inventory are stable.
                inspect_run(root, amendment, require_pause=True)
                paused_verified = True
                write(folder / 'original-supervisor-at-handover.json', read_json(root / 'supervisor.json'))
                write(folder / 'original-stage-at-handover.json', read_json(root / 'train_base/state.json'))
                state.update(status='guarding_same_worker_original_observer_paused', observer_paused_at=time.time())
                write(state_path, state)
                print(json.dumps({'status': state['status'], 'worker_pid': worker['pid'], 'guard_pid': os.getpid()}), flush=True)
                last_size_at, size = 0., 0
                while alive(worker):
                    if not alive(observer) or bound_process(observer)['state'] != 'T':
                        raise RuntimeError('Delegated observer relationship changed')
                    now = time.time()
                    task = read_json(root / 'train_base/actual/task.json')
                    if task['pid'] != worker['pid']:
                        raise ValueError('Task belongs to another worker')
                    sample, memory = resources(), 0.
                    if sample['processes']['returncode'] == 0:
                        for line in sample['processes']['stdout'].splitlines():
                            fields = [x.strip() for x in line.split(',')]
                            if len(fields) >= 3 and fields[1] == str(worker['pid']):
                                memory += float(fields[2])
                    resident = rss(worker['pid'])
                    if now-last_size_at >= 30:
                        size, last_size_at = artifact_bytes(root), now
                    reason = resource_reason(amendment, task, sample, memory, resident, size, now)
                    row = {'sample': sample, 'task': task, 'rss_bytes': resident,
                        'all_lines_rss_bytes': resident, 'own_gpu_memory_mib': memory, 'artifact_bytes': size,
                        'budget_extension': ID, 'observer_pid': os.getpid()}
                    with (root / 'train_base/resources.jsonl').open('a') as out:
                        out.write(json.dumps(row, ensure_ascii=False)+'\n')
                    progress = read(root / 'train_base/actual/update/report.json') or {}
                    state.update(observed_at=time.time(), current_task=task,
                        backward_decisions_completed=progress.get('backward_decisions_completed'),
                        admitted_decisions=progress.get('admitted_decisions'),
                        actor_optimizer_steps=progress.get('actor_optimizer_steps'),
                        critic_optimizer_steps=progress.get('critic_optimizer_steps'),
                        own_gpu_memory_mib=memory, host_rss_bytes=resident, last_stop_reason=reason)
                    write(state_path, state)
                    if reason:
                        stop_bound_worker(worker)
                        break
                    time.sleep(5)
                state.update(status='worker_exited_original_parent_will_reap', worker_exit_observed_at=time.time(),
                    exit_code_scope='The original parent Popen.poll will reap the actual OS code; this guard does not invent it.')
                write(state_path, state)
        except BaseException as error:
            # The context stops only the bound child on a body error BEFORE
            # CONT, then guarantees parent restoration. This is a fallback
            # check for a still-live child, never a restart or another PID.
            if paused_verified:
                try:
                    stop_bound_worker(worker, allow_reparented=True)
                except BaseException as cleanup_error:
                    state['cleanup_error'] = {'type': type(cleanup_error).__name__, 'message': str(cleanup_error)}
            state.update(status='guard_error', error={'type': type(error).__name__, 'message': str(error)}, ended_at=time.time())
            write(state_path, state)
            raise
        state.update(status='original_observer_resumed', observer_resumed_at=time.time())
        write(state_path, state)
        try:
            annotate_after_archive(root, amendment_path, checkout, state, state_path)
            state.update(status='complete_annotated_and_pushed', ended_at=time.time())
        except BaseException as error:
            state.update(status='supervision_handed_back_annotation_failed',
                annotation_error={'type': type(error).__name__, 'message': str(error)}, ended_at=time.time())
            write(state_path, state)
            raise
        write(state_path, state)
        return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--amendment', type=Path, required=True)
    parser.add_argument('--checkout', type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    run(args.run, args.amendment, args.checkout)
