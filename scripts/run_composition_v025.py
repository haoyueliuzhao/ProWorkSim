"""Reuse bounded stage execution for one conditional member-composition window."""
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
from proworksim.storage import read_json
from scripts.evaluate_work_v022 import checked, reference, write
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, resources, stop_owned

from scripts.run_credit_v024 import ready_cards
from scripts.composition_evidence_v025 import maybe_decide, terminal

VERSION = 'bounded-member-composition-v0.25'
CAPS = {'support': 21600, 'train_base': 43200, 'train_probe': 43200,
        'dev_base': 9000, 'dev_probe': 9000, 'train_configured': 43200,
        'confirm_base': 16200, 'confirm_configured': 16200,
        'next_base': 3600, 'next_configured': 3600}
TASK_CAPS = {'loading': 900, 'episode': 1200, 'update': 39600, 'boundary': 600}
ORDER = list(CAPS)


def dependency(stage, root, states):
    if stage == 'support':
        return 'ready'
    support_state = states['support']
    marker_path = root / 'support-complete.json'
    if support_state['status'] != 'complete' or not marker_path.exists():
        return 'unavailable_endpoint' if terminal(support_state) else 'waiting'
    marker = read_json(marker_path)
    selected = marker['selected_block']
    if stage == 'train_base':
        return 'ready'
    if stage in {'train_probe', 'dev_base', 'dev_probe'} and selected is None:
        return 'not_required'
    if stage == 'train_probe':
        return 'ready'
    if stage.startswith('dev_'):
        parent = 'train_' + stage[4:]
    else:
        decision_path = root / 'configuration-decision.json'
        if not decision_path.exists():
            return 'waiting'
        decision = read_json(decision_path)
        if stage in {'train_configured', 'confirm_configured', 'next_configured'} and not decision['changed']:
            return 'not_required'
        if stage == 'train_configured':
            return 'ready' if decision['development_complete'] else 'unavailable_endpoint'
        parent = {'confirm_base': 'train_base', 'confirm_configured': 'train_configured',
                  'next_base': 'confirm_base', 'next_configured': 'confirm_configured'}[stage]
    state = states[parent]
    if state['status'] == 'complete':
        return 'ready'
    return 'unavailable_endpoint' if terminal(state) else 'waiting'


def validate(plan):
    if (plan['version'] != 'member-composition-pilot-v0.25' or plan['resource_caps'] != CAPS
            or plan['task_caps'] != TASK_CAPS or plan['max_concurrent_model_instances'] != 2
            or plan['internal_gpu_seconds'] != sum(CAPS.values()) or sum(CAPS.values()) != 58*3600
            or plan['external_gpu_seconds'] != 0 or plan['max_new_steps_per_branch'] != 1
            or plan['model_api_calls'] != 0 or plan['max_wall_seconds'] != 72*3600
            or plan['artifact_bytes'] != 32*1024**3 or plan['automatic_recovery'] is not False
            or plan['composition'] != {'epsilon': .1, 'ratio_bounds': [.5, 2.], 'tv_limit': .1,
                'lambda_h': 1., 'lambda_r': 1., 'beta': 0., 'coverage': 'uniform_within_actual_support',
                'min_class_count': 2, 'primary_utility': 'full_responsibility',
                'selection': ['joint_a:implementer', 'joint_a:provider']}):
        raise ValueError('Frozen experiment and new independent ceilings changed')
    catalog = read_json(checked(plan['catalog']))
    if (len(catalog['training_window']['slots']) != 16 or len(catalog['training_cases']) != 2
            or len(catalog['development_slots']) != 6 or len(catalog['confirmation_slots']) != 12
            or len(catalog['continuation_slots']) != 2 or len(catalog['all_cases']) != 16):
        raise ValueError('Predeclared support/development/confirmation/continuation inventory changed')
    checked(plan['source_pin'])
    checked(plan['prior_endpoint'])
    for ref in plan['qualification_refs']:
        checked(ref)


def finish(root, stage, state, process, reason):
    if process.poll() is None:
        stop_owned(process)
    state['task'] = read(root / stage / 'actual/task.json') or state.get('task')
    state.update(ended_at=time.time(), exit_code=process.poll(), stop_reason=reason,
                 status='complete' if process.returncode == 0 and reason is None else 'stopped')
    state['elapsed_gpu_seconds'] = state['ended_at'] - state['started_at']
    write(root / stage / 'state.json', state)


def run(plan_path, root):
    plan = read_json(plan_path)
    validate(plan)
    source = code_identity()
    if source['code_dirty']:
        raise ValueError('Commit and freeze the full experiment before GPU execution')
    root.mkdir(parents=True, exist_ok=True)
    with lock(root):
        if (root / 'supervisor.json').exists():
            raise ValueError('No automatic supervisor restart or outcome-driven resampling')
        summary = {'version': VERSION, 'status': 'running', 'source': source,
                   'plan': reference(plan_path), 'observer_pid': os.getpid(), 'started_at': time.time(),
                   'caps': CAPS, 'task_caps': TASK_CAPS, 'max_parallel_model_instances': 2}
        write(root / 'supervisor.json', summary)
        states, active, logs = {}, {}, {}
        for stage in ORDER:
            states[stage] = {'stage': stage, 'status': 'waiting', 'attempted': False,
                             'budget_seconds': CAPS.get(stage, 0), 'source': source, 'created_at': time.time()}
            (root / stage).mkdir()
            write(root / stage / 'state.json', states[stage])
        last_artifact_check, size = 0.0, 0
        try:
            while True:
                now = time.time()
                sample = resources()
                if now - summary['started_at'] >= plan['max_wall_seconds'] - 30:
                    for stage, process in list(active.items()):
                        finish(root, stage, states[stage], process, 'wall_time_budget')
                        logs.pop(stage).close()
                        del active[stage]
                    for stage, state in states.items():
                        if state['status'] == 'waiting':
                            state.update(status='not_started_wall_time_budget', ended_at=time.time())
                            write(root / stage / 'state.json', state)
                    break
                if now - last_artifact_check >= 30:
                    size = artifact_bytes(root)
                    last_artifact_check = now
                all_rss = sum(rss(p.pid) for p in active.values())
                for stage, process in list(active.items()):
                    state = states[stage]
                    if process.poll() is not None:
                        finish(root, stage, state, process, None if process.returncode == 0 else 'worker_failed')
                        logs.pop(stage).close()
                        del active[stage]
                        continue
                    task = read(root / stage / 'actual/task.json') or {'kind': 'loading', 'task': 'startup',
                                                                      'started_at': state['started_at']}
                    own_rss, own_memory = rss(process.pid), 0.0
                    reason = None
                    if any(sample[k]['returncode'] != 0 for k in ('gpus', 'processes')):
                        reason = 'resource_query_failed'
                    else:
                        for row in csv.reader(io.StringIO(sample['processes']['stdout'])):
                            if len(row) >= 3 and row[1].strip() == str(process.pid):
                                own_memory += float(row[2])
                    state['task'] = task
                    kind = task.get('kind')
                    if kind not in TASK_CAPS:
                        reason = 'unknown_task_deadline'
                    elif now - task['started_at'] >= TASK_CAPS[kind] - 30:
                        reason = 'task_time_budget'
                    if now - state['started_at'] >= state['budget_seconds'] - 30:
                        reason = 'stage_time_budget'
                    if own_rss > 64 * 1024**3 or all_rss > 64 * 1024**3:
                        reason = 'host_rss_limit'
                    if own_memory >= (57344 if stage.startswith('train') else 32768):
                        reason = 'own_gpu_memory_limit'
                    if size >= plan['artifact_bytes']:
                        reason = 'artifact_limit'
                    with (root / stage / 'resources.jsonl').open('a') as out:
                        out.write(json.dumps({'sample': sample, 'task': task, 'rss_bytes': own_rss,
                            'all_lines_rss_bytes': all_rss, 'own_gpu_memory_mib': own_memory,
                            'artifact_bytes': size}, ensure_ascii=False) + '\n')
                    if reason:
                        finish(root, stage, state, process, reason)
                        logs.pop(stage).close()
                        del active[stage]
                maybe_decide(root, plan, states, source)
                for stage in ORDER:
                    state = states[stage]
                    if state['status'] != 'waiting':
                        continue
                    dep = dependency(stage, root, states)
                    if dep == 'not_required':
                        state.update(status='not_required', ended_at=time.time(),
                                     reason='predeclared_no_support_or_unchanged_configuration_branch')
                        write(root / stage / 'state.json', state)
                        continue
                    if dep == 'unavailable_endpoint':
                        state.update(status='not_started_endpoint_unavailable', ended_at=time.time())
                        write(root / stage / 'state.json', state)
                        continue
                    if dep != 'ready' or len(active) >= 2:
                        continue
                    excluded = [states[name]['gpu'] for name in active]
                    choices = ready_cards(sample, training=stage.startswith('train'), excluded=excluded)
                    state.update(last_observation=sample, ready_cards=choices)
                    write(root / stage / 'state.json', state)
                    if not choices:
                        continue
                    confirm = resources()
                    choices = ready_cards(confirm, training=stage.startswith('train'), excluded=excluded)
                    if not choices:
                        continue
                    if code_identity() != source or reference(plan_path) != summary['plan']:
                        raise ValueError('Frozen source or plan changed before launch')
                    gpu = choices[0]
                    command = [sys.executable, '-m', 'scripts.composition_pilot_v025', '--plan', str(plan_path),
                               '--run-root', str(root), '--stage', stage, '--output', str(root / stage / 'actual')]
                    state.update(status='launch_intent', attempted=True, gpu=gpu, started_at=time.time(),
                                 command=command, admission_resources=confirm)
                    write(root / stage / 'state.json', state)
                    env = {**os.environ, 'CUDA_VISIBLE_DEVICES': str(gpu), 'PYTHONHASHSEED': plan['python_hash_seed'], 'HF_HUB_OFFLINE': '1',
                           'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false'}
                    env.pop('PROWORKSIM_REPLICA_GPUS', None)
                    logs[stage] = (root / stage / 'model.log').open('x')
                    process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=env,
                        stdin=subprocess.DEVNULL, stdout=logs[stage], stderr=subprocess.STDOUT, start_new_session=True)
                    active[stage] = process
                    state.update(status='running', pid=process.pid)
                    write(root / stage / 'state.json', state)
                summary['stage_statuses'] = {k: v['status'] for k, v in states.items()}
                summary['observed_at'] = time.time()
                summary['terminated_gpu_seconds'] = sum(v.get('elapsed_gpu_seconds', 0) for v in states.values())
                write(root / 'supervisor.json', summary)
                if not active and all(s['status'] != 'waiting' for s in states.values()):
                    break
                time.sleep(5)
            summary.update(status='complete' if all(s['status'] in {'complete', 'not_required'} for s in states.values()) else 'closed_with_incomplete_stages',
                           ended_at=time.time())
        except BaseException as error:
            for stage, process in active.items():
                finish(root, stage, states[stage], process, 'supervisor_interrupted')
                logs[stage].close()
            summary.update(status='supervisor_error', error={'type': type(error).__name__, 'message': str(error)}, ended_at=time.time())
            for stage, state in states.items():
                if state['status'] == 'waiting':
                    state.update(status='not_started_supervisor_interrupted', ended_at=time.time())
                    write(root / stage / 'state.json', state)
        finally:
            summary['stage_statuses'] = {k: v['status'] for k, v in states.items()}
            summary['terminated_gpu_seconds'] = sum(v.get('elapsed_gpu_seconds', 0) for v in states.values())
            write(root / 'supervisor.json', summary)
    with (root / 'archive.log').open('a') as archive_log:
        subprocess.run([sys.executable, '-m', 'scripts.archive_composition_v025', '--run', str(root),
                        '--plan', str(plan_path)], cwd=Path(__file__).resolve().parents[1],
                       env={**os.environ, 'CUDA_VISIBLE_DEVICES': ''}, stdout=archive_log,
                       stderr=subprocess.STDOUT, timeout=600, check=False)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    run(args.plan.resolve(), args.run_root.resolve())
