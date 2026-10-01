"""Take over only resource supervision for the two already-running C1 workers.

No model process is restarted or signalled during handoff. Original parents are
paused, then resumed for native child reaping after both workers have exited.
A pidfd watchdog restores those parents if this controller itself exits.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import digest, read_json
from scripts.evaluate_work_v022 import checked, reference, write
from scripts.report_collaboration_carrier_v026 import load_run, markdown
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_collaboration_carrier_v026 import stop_reason, verify_completed_worker
from scripts.run_ne_v021 import lock

VERSION = 'c1-live-resource-budget-extension-v0.26'
CAPS = {'worker-0': 14374, 'worker-1': 14374}


def process_spec(pid):
    value = worker_identity(pid)
    if value.get('alive') is not True:
        raise ValueError('The declared process is not alive')
    return {'pid': pid, 'start_ticks': value['start_ticks'],
            'command_sha256': digest(Path(f'/proc/{pid}/cmdline').read_bytes()),
            'cwd': str(Path(f'/proc/{pid}/cwd').resolve())}


def open_verified(spec):
    fd = os.pidfd_open(spec['pid'])
    try:
        if process_spec(spec['pid']) != spec:
            raise ValueError('Process identity changed before supervision handoff')
    except BaseException:
        os.close(fd)
        raise
    return fd


def exited(fd):
    return bool(select.select([fd], [], [], 0)[0])


def send(fd, sig):
    if not exited(fd):
        signal.pidfd_send_signal(fd, sig)


def pause(fd, pid):
    send(fd, signal.SIGSTOP)
    for _ in range(100):
        if worker_identity(pid).get('state') in {'T', 't'}:
            return
        if exited(fd):
            raise RuntimeError('Original parent exited during handoff')
        time.sleep(.01)
    raise RuntimeError('Original parent did not acknowledge pause')


def watchdog(declaration, root, guard_pid):
    """Never restart work; release original resource control on guard death."""
    value = read_json(declaration)
    fds = {name: open_verified(value[name]) for name in ('supervisor_process', 'driver_process')}
    guard = os.pidfd_open(guard_pid)
    write(root/'watchdog-ready.json', {'pid': os.getpid(), 'guard_pid': guard_pid})
    select.select([guard], [], [])
    for fd in fds.values():
        send(fd, signal.SIGCONT)
        os.close(fd)
    write(root/'watchdog-finished.json', {'at': time.time(), 'original_parents_released': True})
    os.close(guard)


def validate_declaration(value, summary, states):
    plan = read_json(checked(value['original_plan']))
    if (value.get('version') != VERSION or value.get('resource_caps') != CAPS
            or value.get('cumulative_gpu_seconds_cap') != 28800
            or value.get('own_gpu_memory_mib') != 81920
            or value.get('additional_episodes') != 0 or value.get('parameter_updates') != 0
            or value.get('automatic_recovery') is not False
            or value.get('automatic_successors') != []
            or summary.get('plan') != value['original_plan']
            or summary.get('source') != value['worker_source']
            or plan.get('version') != 'reciprocal-carrier-development-v0.26-r2'
            or sum(CAPS.values())+plan['previous_attempt']['budget_charge_seconds'] != 28800
            or set(states) != set(CAPS)):
        raise ValueError('Only the authorized existing sixteen-slot eight-GPU-hour extension is allowed')
    for name, state in states.items():
        bound = value['workers'][name]
        process = bound.get('process')
        if process is None:
            if state != read_json(checked(bound['terminal_state'])) or state.get('status') not in {'stopped', 'complete'}:
                raise ValueError('An already terminal worker record changed: '+name)
            continue
        if (state.get('status') != 'running' or state.get('attempted') is not True
                or state.get('pid') != process['pid']
                or state.get('worker_start_ticks') != process['start_ticks']
                or state.get('gpu') != bound['gpu'] or state.get('gpu_uuid') != bound['gpu_uuid']
                or state.get('started_at') != bound['started_at']
                or state.get('budget_seconds') != plan['resource_caps'][name]
                or state.get('slots') != summary['worker_assignments'][name]
                or state.get('source') != value['worker_source']):
            raise ValueError('A worker changed identity, budget or fixed slot partition: '+name)
    effective = copy.deepcopy(plan)
    effective['own_gpu_memory_mib'] = value['own_gpu_memory_mib']
    return effective


def snapshot(root, summary, states, extension, observer, now):
    result = copy.deepcopy(summary)
    result.update(budget_extension=extension, resource_observer=observer,
                  original_observer_pid=summary['observer_pid'], observer_pid=os.getpid(),
                  original_caps=summary['caps'], caps=CAPS,
                  worker_statuses={name: state['status'] for name, state in states.items()},
                  observed_at=now,
                  terminated_gpu_seconds=sum(state.get('elapsed_gpu_seconds', 0) for state in states.values()),
                  running_gpu_seconds=sum(now-state['started_at'] for state in states.values()
                                          if state['status']=='running'))
    write(root/'supervisor.json', result)


def stop_attached(fd):
    send(fd, signal.SIGTERM)
    deadline = time.monotonic()+10
    while not exited(fd) and time.monotonic()<deadline:
        time.sleep(.1)
    if not exited(fd):
        send(fd, signal.SIGKILL)
    deadline = time.monotonic()+10
    while not exited(fd) and time.monotonic()<deadline:
        time.sleep(.1)
    if not exited(fd):
        raise RuntimeError('An owned worker did not exit after bounded termination')


def run(declaration, output):
    declaration, output = Path(declaration).resolve(), Path(output).resolve()
    value, extension = read_json(declaration), reference(declaration)
    root = Path(value['run_root'])
    summary = read_json(root/'supervisor.json')
    states = {name: read_json(root/name/'state.json') for name in CAPS}
    plan = validate_declaration(value, summary, states)
    observer = {'pid': os.getpid(), 'source': code_identity(), 'declaration': extension}
    if observer['source']['code_dirty']:
        raise ValueError('Resource controller must use its own committed clean checkout')
    output.mkdir(parents=True, exist_ok=True)
    if (output/'state.json').exists():
        raise ValueError('This live resource handoff is single-use')
    parent_fds, worker_fds = {}, {}
    control = {'version': VERSION, 'phase': 'preparing', 'observer': observer,
               'started_at': time.time(), 'workers_restarted': 0, 'new_episodes': 0}
    terminal, reasons = {}, {}
    try:
        with lock(output):
            for name in ('supervisor_process', 'driver_process'):
                parent_fds[name] = open_verified(value[name])
            worker_fds = {name: open_verified(value['workers'][name]['process']) for name in CAPS
                          if value['workers'][name].get('process') is not None}
            subprocess.Popen([sys.executable, '-m', 'scripts.extend_collaboration_budget_v026',
                              '--declaration', str(declaration), '--output', str(output),
                              '--watch-guardian', str(os.getpid())],
                             cwd=Path(__file__).resolve().parents[1], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            deadline = time.monotonic()+15
            while not (output/'watchdog-ready.json').exists() and time.monotonic()<deadline:
                time.sleep(.1)
            if not (output/'watchdog-ready.json').exists():
                raise RuntimeError('Original-parent release watchdog did not become ready')
            # Pause only orchestration, never either CUDA worker.
            pause(parent_fds['driver_process'], value['driver_process']['pid'])
            pause(parent_fds['supervisor_process'], value['supervisor_process']['pid'])
            summary = read_json(root/'supervisor.json')
            states = {name: read_json(root/name/'state.json') for name in CAPS}
            validate_declaration(value, summary, states)
            write(output/'original-supervisor-at-handoff.json', summary)
            for name, state in states.items():
                write(output/(name+'-at-handoff.json'), state)
                if name in worker_fds:
                    state.update(original_budget_seconds=state['budget_seconds'], budget_seconds=CAPS[name],
                                 budget_extension=extension, resource_observer=observer)
                    write(root/name/'state.json', state)
                else:
                    terminal[name] = state['ended_at']
                    if state.get('stop_reason'):
                        reasons[name] = state['stop_reason']
            guards = {name: TelemetryGuard(state['gpu'], state['gpu_uuid'], state['worker_start_ticks'],
                      worker_pid=state['pid'], grace_seconds=120) for name, state in states.items()
                      if name in worker_fds}
            control['phase'] = 'monitoring'
            write(output/'state.json', control)
            last_size, size = 0, 0
            with ThreadPoolExecutor(max_workers=2) as pool:
                while len(terminal)<len(CAPS):
                    now = time.time()
                    if now-last_size>=30:
                        size, last_size = artifact_bytes(root), now
                    active = [name for name in CAPS if name not in terminal]
                    samples = {name: pool.submit(target_resources, states[name]['gpu'],
                               worker_pid=states[name]['pid']) for name in active if not exited(worker_fds[name])}
                    all_rss = sum(rss(states[name]['pid']) for name in active)
                    for name in active:
                        state, fd = states[name], worker_fds[name]
                        if not exited(fd):
                            sample = samples[name].result()
                            observed = guards[name].observe(sample, time.time(), state['pid'], state['gpu'],
                                       own_memory_limit_mib=plan['own_gpu_memory_mib'])
                            task = read_json(root/name/'actual/task.json')
                            own_rss = rss(state['pid'])
                            reason = stop_reason(plan, state, task, now=time.time(),
                                     root_started=summary['started_at'], own_rss=own_rss, all_rss=all_rss,
                                     size=size, free_bytes=shutil.disk_usage(root).free) or observed['stop_reason']
                            state.update(task=task, telemetry=observed)
                            with (root/name/'resources.jsonl').open('a') as file:
                                file.write(json.dumps({'sample': sample, 'task': task,
                                    'rss_bytes': own_rss, 'all_lines_rss_bytes': all_rss,
                                    'artifact_bytes': size, 'telemetry': observed,
                                    'resource_observer': observer})+'\n')
                            if reason and not exited(fd):
                                reasons[name] = reason
                                stop_attached(fd)
                        if exited(fd):
                            terminal[name] = time.time()
                            state.update(status='exited_awaiting_parent_reap',
                                         process_exit_observed_at=terminal[name],
                                         elapsed_gpu_seconds=terminal[name]-state['started_at'])
                        write(root/name/'state.json', state)
                    snapshot(root, summary, states, extension, observer, time.time())
                    control.update(observed_at=time.time(), terminal_workers=terminal,
                                   stop_reasons=reasons, active_workers=[name for name in CAPS if name not in terminal])
                    write(output/'state.json', control)
                    if len(terminal)<len(CAPS):
                        time.sleep(5)
            # Both pidfds are terminal: the original parent can now reap children
            # without interrupting any active model, even if its old timer fires.
            control['phase'] = 'finalizing'
            write(output/'state.json', control)
            send(parent_fds['supervisor_process'], signal.SIGCONT)
            deadline = time.monotonic()+600
            while not exited(parent_fds['supervisor_process']) and time.monotonic()<deadline:
                time.sleep(.5)
            if not exited(parent_fds['supervisor_process']):
                raise RuntimeError('Original terminal archive did not finish within ten minutes')
            raw_summary = read_json(root/'supervisor.json')
            write(output/'original-parent-final-supervisor.json', raw_summary)
            for name in CAPS:
                state = read_json(root/name/'state.json')
                write(output/(name+'-original-parent-final.json'), state)
                reason = reasons.get(name)
                if state.get('exit_code') != 0:
                    reason = reason or 'worker_failed'
                if reason is None:
                    try:
                        verify_completed_worker(plan, root, name, summary['worker_assignments'][name],
                                                value['worker_source'])
                    except (ValueError, KeyError, OSError) as error:
                        reason = 'unqualified_frozen_endpoint'
                        state['extension_verification_error'] = str(error)
                state.update(parent_cleanup_stop_reason=state.get('stop_reason'),
                             parent_reaped_at=state.get('ended_at'),
                             ended_at=terminal[name], elapsed_gpu_seconds=terminal[name]-state['started_at'],
                             budget_seconds=CAPS[name] if name in worker_fds else state['budget_seconds'],
                             original_budget_seconds=plan['resource_caps'][name],
                             budget_extension=extension, resource_observer=observer,
                             status='complete' if reason is None else 'stopped', stop_reason=reason)
                states[name] = state
                write(root/name/'state.json', state)
            summary.update(status='complete' if all(s['status']=='complete' for s in states.values())
                           else 'closed_with_incomplete_workers', ended_at=time.time())
            snapshot(root, summary, states, extension, observer, time.time())
            report = load_run(root, require_terminal=True)
            for name in ('json', 'md'):
                path = Path(value['reports'][name])
                if path.exists():
                    shutil.copy2(path, output/('original-wrapper-report.'+name))
            original_report = read_json(Path(value['reports']['json']))
            report['finish_wrapper'] = original_report.get('finish_wrapper')
            report['live_budget_extension'] = {'declaration': extension, 'observer': observer,
                                              'process_exit_observed_at': terminal,
                                              'original_workers_preserved': True, 'new_model_launches': 0}
            write(Path(value['reports']['json']), report)
            Path(value['reports']['md']).write_text(markdown(report))
            control.update(phase='complete', final_run_status=report['run_status'],
                           report_corrected_before_original_driver_publication=True)
    except BaseException as error:
        control.update(phase='failed', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        control['ended_at'] = time.time()
        write(output/'state.json', control)
        # Also performed by the pidfd watchdog if this process is externally killed.
        for name in ('supervisor_process', 'driver_process'):
            if name in parent_fds:
                send(parent_fds[name], signal.SIGCONT)
                os.close(parent_fds[name])
        for fd in worker_fds.values():
            os.close(fd)
    return control


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--declaration', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--watch-guardian', type=int)
    args = parser.parse_args()
    if args.watch_guardian:
        watchdog(args.declaration.resolve(), args.output.resolve(), args.watch_guardian)
    else:
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        run(args.declaration, args.output)
