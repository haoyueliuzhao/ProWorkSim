"""One bounded R1, with target-device telemetry and finite query-failure grace."""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import read_json
from scripts.composition_evidence_v025 import checked
from scripts.evaluate_work_v022 import reference, write
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_credit_v024 import ready_cards
from scripts.run_ne_v021 import lock, read, resources, stop_owned

VERSION = 'same-window-composition-recovery-v0.25-r1'
CAPS = {'train_base': 72000, 'confirm_base': 16200, 'next_base': 3600}
TASK_CAPS = {'loading': 900, 'episode': 1200, 'update': 64800, 'boundary': 600}
ORDER = tuple(CAPS)


def validate(plan):
    from proworksim.composition_recovery_v025 import build_recovery_binding

    if (plan['version'] != VERSION or plan['resource_caps'] != CAPS or plan['task_caps'] != TASK_CAPS
            or plan['internal_gpu_seconds'] != 91800 or plan['max_wall_seconds'] != 172800
            or plan['max_concurrent_model_instances'] != 1 or plan['telemetry_grace_seconds'] != 120
            or plan['gpu_query_timeout_seconds'] != 5 or plan['process_query_timeout_seconds'] != 5
            or plan['automatic_recovery'] is not False or plan['model_api_calls'] != 0
            or plan['new_training_episodes'] != 0 or plan['max_new_episodes'] != 14
            or plan['max_new_actor_steps'] != 1 or plan['max_new_critic_steps'] != 1):
        raise ValueError('Only the declared single R1 attempt and unchanged work are authorized')
    if build_recovery_binding(plan['original_run']) != plan['recovery']:
        raise ValueError('Original failure or exact recovery material changed')
    original = read_json(checked(plan['original_plan']))
    if plan['catalog'] != original['catalog'] or plan['source_pin'] != original['source_pin']:
        raise ValueError('R1 must keep the unstarted original work inventory')
    checked(plan['original_supervisor'])
    checked(plan['original_report'])
    checked(plan['original_support_complete'])
    catalog = read_json(checked(plan['catalog']))
    if len(catalog['confirmation_slots']) != 12 or len(catalog['continuation_slots']) != 2:
        raise ValueError('Original confirmation/continuation counts changed')
    for item in plan['qualification_refs']:
        checked(item)


def card_uuid(sample, index):
    rows = list(csv.reader(io.StringIO(sample['gpus']['stdout'])))
    matching = [r[1].strip() for r in rows if len(r) == 6 and int(r[0].strip()) == index]
    if len(matching) != 1:
        raise ValueError('Admission must bind one exact physical GPU UUID')
    return matching[0]


def other_stop_reason(plan, summary, state, task, *, now, host_rss, size):
    if task.get('kind') not in TASK_CAPS:
        return 'unknown_task_deadline'
    if now - task['started_at'] >= TASK_CAPS[task['kind']] - 30:
        return 'task_time_budget'
    if now - state['started_at'] >= state['budget_seconds'] - 30:
        return 'stage_time_budget'
    if now - summary['started_at'] >= plan['max_wall_seconds'] - 30:
        return 'wall_time_budget'
    if host_rss > 64*1024**3:
        return 'host_rss_limit'
    if size >= 32*1024**3:
        return 'artifact_limit'
    return None


def finish(root, stage, state, process, reason):
    if process.poll() is None:
        stop_owned(process)
    state.update(status='complete' if process.returncode == 0 and reason is None else 'stopped',
        exit_code=process.poll(), stop_reason=reason, ended_at=time.time(),
        task=read(root / stage / 'actual/task.json') or state.get('task'))
    state['elapsed_gpu_seconds'] = state['ended_at'] - state['started_at']
    write(root / stage / 'state.json', state)


def terminal_sample(root, stage, sample, process):
    """Retain even a failed query that returned after a normal worker exit."""
    row = {'sample': sample, 'task': read(root / stage / 'actual/task.json'),
        'rss_bytes': 0, 'all_lines_rss_bytes': 0, 'artifact_bytes': artifact_bytes(root),
        'own_gpu_memory_mib': None, 'process_exit_observed': True,
        'exit_code_observed': process.returncode, 'telemetry_evaluated': False,
        'scope': 'Worker exit was reaped before telemetry judgment; preserve the raw query without converting success to resource failure.'}
    with (root / stage / 'resources.jsonl').open('a') as out:
        out.write(json.dumps(row, ensure_ascii=False)+'\n')


def run(plan_path, root):
    plan = read_json(plan_path)
    validate(plan)
    source = code_identity()
    if source['code_dirty']:
        raise ValueError('Freeze the complete R1 implementation before GPU execution')
    root.mkdir(parents=True, exist_ok=False)
    with lock(root):
        states = {stage: {'stage': stage, 'status': 'waiting', 'attempted': False,
            'budget_seconds': CAPS[stage], 'source': source, 'created_at': time.time()} for stage in ORDER}
        summary = {'version': VERSION, 'status': 'running', 'source': source, 'plan': reference(plan_path),
            'observer_pid': os.getpid(), 'started_at': time.time(), 'caps': CAPS, 'task_caps': TASK_CAPS,
            'max_parallel_model_instances': 1, 'telemetry_grace_seconds': 120,
            'previous_gpu_seconds': plan['previous_gpu_seconds'], 'original_run': plan['original_run'],
            'original_failure_preserved': True, 'no_automatic_second_attempt': True}
        for stage, state in states.items():
            (root / stage).mkdir()
            write(root / stage / 'state.json', state)
        active_process, active_stage = None, None

        def publish():
            summary['stage_statuses'] = {k: v['status'] for k, v in states.items()}
            summary['observed_at'] = time.time()
            used = sum(s.get('elapsed_gpu_seconds', 0.) for s in states.values())
            summary['terminated_gpu_seconds'] = used
            summary['cumulative_terminated_gpu_seconds'] = summary['previous_gpu_seconds'] + used
            write(root / 'supervisor.json', summary)

        publish()
        try:
            for index, stage in enumerate(ORDER):
                state = states[stage]
                if index and states[ORDER[index-1]]['status'] != 'complete':
                    state.update(status='not_started_endpoint_unavailable', ended_at=time.time())
                    write(root / stage / 'state.json', state)
                    publish()
                    continue
                chosen, admitted = None, None
                while chosen is None:
                    if time.time()-summary['started_at'] >= plan['max_wall_seconds']-30:
                        state.update(status='not_started_wall_time_budget', ended_at=time.time())
                        write(root / stage / 'state.json', state)
                        break
                    if code_identity() != source or reference(plan_path) != summary['plan']:
                        raise ValueError('R1 source or plan changed while waiting')
                    sample = resources()
                    cards = ready_cards(sample, training=stage == 'train_base')
                    state.update(last_admission_observation=sample, ready_cards=cards)
                    write(root / stage / 'state.json', state)
                    publish()
                    if cards:
                        check = resources()
                        confirmed = ready_cards(check, training=stage == 'train_base')
                        if cards[0] in confirmed:
                            chosen, admitted = cards[0], check
                            break
                    time.sleep(5)
                if chosen is None:
                    continue
                command = [sys.executable, '-m', 'scripts.composition_recovery_v025', '--plan', str(plan_path),
                    '--run-root', str(root), '--stage', stage, '--output', str(root / stage / 'actual')]
                env = {**os.environ, 'CUDA_VISIBLE_DEVICES': str(chosen), 'PYTHONHASHSEED': plan['python_hash_seed'],
                    'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false'}
                env.pop('PROWORKSIM_REPLICA_GPUS', None)
                state.update(status='launch_intent', attempted=True, gpu=chosen,
                    gpu_uuid=card_uuid(admitted, chosen), started_at=time.time(),
                    command=command, admission_resources=admitted)
                write(root / stage / 'state.json', state)
                with (root / stage / 'model.log').open('x') as log:
                    process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=env,
                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    active_process, active_stage = process, stage
                    identity = worker_identity(process.pid)
                    if not identity.get('available') or identity.get('alive') is not True:
                        raise ValueError('Cannot bind the actual newly launched worker')
                    state.update(status='running', pid=process.pid, worker_start_ticks=identity['start_ticks'])
                    write(root / stage / 'state.json', state)
                    publish()
                    telemetry = TelemetryGuard(chosen, state['gpu_uuid'], identity['start_ticks'],
                        grace_seconds=120, worker_pid=process.pid)
                    last_size_at, size, reason = 0., 0, None
                    while process.poll() is None:
                        sample = target_resources(chosen, worker_pid=process.pid,
                            gpu_timeout_seconds=5, process_timeout_seconds=5)
                        # This parent owns Popen: natural exit wins over a stale
                        # sample that observed the process disappearing.
                        if process.poll() is not None:
                            terminal_sample(root, stage, sample, process)
                            break
                        if sample['worker_identity'].get('alive') is False:
                            try:
                                process.wait(timeout=1)
                            except subprocess.TimeoutExpired:
                                pass
                            if process.poll() is not None:
                                terminal_sample(root, stage, sample, process)
                                break
                        now = time.time()
                        obs = telemetry.observe(sample, now, process.pid, chosen,
                            own_memory_limit_mib=57344 if stage == 'train_base' else 32768)
                        task = read(root / stage / 'actual/task.json') or {
                            'task': 'startup', 'kind': 'loading', 'started_at': state['started_at']}
                        resident = rss(process.pid)
                        if now-last_size_at >= 30:
                            size, last_size_at = artifact_bytes(root), now
                        structural_reason = other_stop_reason(plan, summary, state, task,
                            now=now, host_rss=resident, size=size)
                        reason = structural_reason or obs['stop_reason']
                        row = {'sample': sample, 'task': task, 'rss_bytes': resident,
                            'all_lines_rss_bytes': resident, 'artifact_bytes': size,
                            'own_gpu_memory_mib': obs['own_gpu_memory_mib'], 'telemetry': obs}
                        with (root / stage / 'resources.jsonl').open('a') as out:
                            out.write(json.dumps(row, ensure_ascii=False)+'\n')
                        state.update(task=task, telemetry={k: obs[k] for k in ('fresh','stale','own_gpu_memory_mib',
                            'consecutive_failures','failures_total','failure_since','failure_seconds','recovered_after_seconds','stop_reason')})
                        write(root / stage / 'state.json', state)
                        publish()
                        if reason:
                            break
                        time.sleep(5)
                    finish(root, stage, state, process, reason)
                    active_process, active_stage = None, None
                    publish()
            summary.update(status='complete' if all(s['status']=='complete' for s in states.values())
                           else 'closed_with_incomplete_stages', ended_at=time.time())
        except BaseException as error:
            if active_process is not None:
                finish(root, active_stage, states[active_stage], active_process, 'supervisor_interrupted')
            for stage, state in states.items():
                if state['status']=='waiting':
                    state.update(status='not_started_supervisor_interrupted', ended_at=time.time())
                    write(root / stage / 'state.json', state)
            summary.update(status='supervisor_error', ended_at=time.time(),
                error={'type':type(error).__name__,'message':str(error)})
        finally:
            publish()
    with (root / 'archive.log').open('a') as log:
        subprocess.run([sys.executable, '-m', 'scripts.archive_composition_recovery_v025',
            '--run', str(root), '--plan', str(plan_path)], cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, 'CUDA_VISIBLE_DEVICES':''}, stdout=log, stderr=subprocess.STDOUT,
            timeout=600, check=False)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    run(args.plan.resolve(), args.run_root.resolve())
