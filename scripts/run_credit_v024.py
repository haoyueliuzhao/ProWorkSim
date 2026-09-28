"""Bounded credit comparison; complete baseline before new training consumption."""
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

VERSION = 'bounded-temporal-credit-v0.24'
CAPS = {'eval_initial': 16200, 'common': 9000, 'train_mc': 36000, 'train_handoff_rtg': 36000, 'eval_mc': 16200, 'eval_handoff_rtg': 16200}
TASK_CAPS = {'loading': 900, 'episode': 1200, 'update': 18000, 'boundary': 600}
ORDER = list(CAPS)


def ready_cards(sample, *, training, excluded=()):
    if any(sample[k]['returncode'] != 0 for k in ('gpus', 'processes')):
        return []
    gpus = {}
    for fields in csv.reader(io.StringIO(sample['gpus']['stdout'])):
        if len(fields) != 6:
            raise ValueError('Unexpected GPU resource schema')
        index, uuid, name, free, total, util = [v.strip() for v in fields]
        if 'A100' not in name:
            continue
        gpus[int(index)] = {'uuid': uuid, 'free': float(free), 'total': float(total), 'util': float(util)}
    minimum = 61440 if training else 40960
    # Prefer physically unoccupied devices, then authorized sharing. All
    # observed co-residents are retained in each resource sample.
    occupied = {row[0].strip() for row in csv.reader(io.StringIO(sample['processes']['stdout'])) if row}
    pool = [2, 3, 4, 5, 6, 0, 1, 7]
    eligible = [i for i in pool if i not in excluded and i in gpus and gpus[i]['free'] >= minimum]
    return sorted(eligible, key=lambda i: (gpus[i]['uuid'] in occupied, pool.index(i)))


def dependency(stage, root, states):
    if stage == 'eval_initial':
        return 'ready'
    parent, marker = ({'common': ('eval_initial', 'baseline-complete.json'),
        'train_mc': ('common', 'common-complete.json'),
        'train_handoff_rtg': ('common', 'common-complete.json'),
        'eval_mc': ('train_mc', 'mc-complete.json'),
        'eval_handoff_rtg': ('train_handoff_rtg', 'handoff_rtg-complete.json')})[stage]
    state = states.get(parent, {})
    if state.get('status') == 'complete' and (root / marker).exists():
        return 'ready'
    if state.get('status') in {'complete', 'stopped', 'supervisor_error', 'not_started_endpoint_unavailable'}:
        return 'unavailable_endpoint'
    return 'waiting'


def validate(plan):
    if (plan['version'] != 'paired-temporal-credit-pilot-v0.24' or plan['resource_caps'] != CAPS
            or plan['task_caps'] != TASK_CAPS or plan['max_concurrent_model_instances'] != 2
            or plan['internal_gpu_seconds'] != 129600 or plan['external_gpu_seconds'] != 0
            or plan['max_actor_steps_per_arm'] != 2 or plan['max_critic_steps_per_arm'] != 2
            or plan['model_api_calls'] != 0 or plan['max_wall_seconds'] != 172800
            or plan['automatic_recovery'] is not False):
        raise ValueError('Frozen finite protocol or resource ceilings changed')
    catalog = read_json(checked(plan['catalog']))
    if (len(catalog['evaluation_slots']) != 12 or len(catalog['evaluation_cases']) != 6
            or len(catalog['all_cases']) != 14 or len(catalog['sampling_windows']) != 3
            or any(len(w['slots']) != 6 for w in catalog['sampling_windows'])):
        raise ValueError('The finite six-situation and three-collection inventory changed')
    checked(plan['source_pin'])
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
                    if size >= 24 * 1024**3:
                        reason = 'artifact_limit'
                    with (root / stage / 'resources.jsonl').open('a') as out:
                        out.write(json.dumps({'sample': sample, 'task': task, 'rss_bytes': own_rss,
                            'all_lines_rss_bytes': all_rss, 'own_gpu_memory_mib': own_memory,
                            'artifact_bytes': size}, ensure_ascii=False) + '\n')
                    if reason:
                        finish(root, stage, state, process, reason)
                        logs.pop(stage).close()
                        del active[stage]
                for stage in ORDER:
                    state = states[stage]
                    if state['status'] != 'waiting':
                        continue
                    dep = dependency(stage, root, states)
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
                    command = [sys.executable, '-m', 'scripts.credit_pilot_v024', '--plan', str(plan_path),
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
            summary['terminated_gpu_seconds'] = sum(v.get('elapsed_gpu_seconds', 0) for v in states.values())
            write(root / 'supervisor.json', summary)
    with (root / 'archive.log').open('a') as archive_log:
        subprocess.run([sys.executable, '-m', 'scripts.archive_credit_v024', '--run', str(root),
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
