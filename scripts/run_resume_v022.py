"""One explicitly declared restoration of B1, with all earlier GPU cost retained."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.storage import read_json
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import checked, lock, read, reference, released_cards, resources, stop_owned, write

VERSION = 'same-window-restoration-supervisor-v0.22'


def validate(plan):
    if (plan.get('version') != VERSION or plan.get('line_seconds') != 2400
            or plan.get('update_seconds') != 2100 or plan.get('other_task_seconds') != 900
            or plan.get('total_gpu_seconds') != 7200 or plan.get('new_training_fragments') != 0
            or plan.get('max_total_actor_steps') != 1 or plan.get('max_total_critic_steps') != 1):
        raise ValueError('Unknown or expanded restoration protocol')
    states = {name: read_json(checked(plan['previous_states'][name])) for name in ('N1', 'W1', 'B1')}
    if any(states[name]['status'] != 'complete' for name in ('N1', 'W1')):
        raise ValueError('Original N1/W1 must be closed')
    if states['B1']['status'] != 'stopped' or states['B1'].get('stop_reason') != 'task_time_budget':
        raise ValueError('Only this original finite-time stopped B1 is restorable')
    used = sum(state['elapsed_gpu_seconds'] for state in states.values())
    if used + plan['line_seconds'] > plan['total_gpu_seconds']:
        raise ValueError('Restoration exceeds cumulative original and new GPU limit')
    checked(plan['experiment_plan'])
    return used


def run(plan_path, root):
    plan = read_json(plan_path)
    previous = validate(plan)
    out = root/'R1'
    out.mkdir(parents=True, exist_ok=True)
    source = code_identity()
    if source['code_dirty']:
        raise ValueError('Freeze restoration source')
    with lock(out):
        if (read(out/'state.json') or {}).get('attempted') or (out/'actual').exists():
            raise ValueError('A restoration has one attempt, no further successor')
        state = {'version': VERSION, 'status': 'waiting', 'attempted': False,
                 'source': source, 'plan': reference(plan_path), 'observer_pid': os.getpid(),
                 'previous_gpu_seconds': previous, 'budget_seconds': 2400,
                 'update_task_seconds': 2100, 'other_task_seconds': 900,
                 'new_training_fragments': 0, 'original_failure_preserved': True}
        write(out/'state.json', state)
        process = None
        try:
            while True:
                if code_identity() != source or reference(plan_path) != state['plan']:
                    raise ValueError('Restoration source/plan changed while waiting')
                validate(plan)
                sample = resources()
                ready = [g for g in released_cards(sample) if g in (2, 3, 4, 5, 6)]
                state.update(last_resources=sample, ready_cards=ready)
                write(out/'state.json', state)
                if ready:
                    gpu = ready[0]
                    confirmed = resources()
                    if gpu in released_cards(confirmed):
                        break
                time.sleep(5)
            started = time.time()
            command = [sys.executable, '-m', 'scripts.resume_bridge_v022', '--plan',
                       str(checked(plan['experiment_plan'])), '--output', str(out/'actual')]
            state.update(status='launch_intent', attempted=True, gpu=gpu, started_at=started,
                         command=command, admission_resources=confirmed)
            write(out/'state.json', state)
            env = {**os.environ, 'CUDA_VISIBLE_DEVICES': str(gpu), 'HF_HUB_OFFLINE': '1',
                   'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false'}
            env.pop('PROWORKSIM_REPLICA_GPUS', None)
            with (out/'model.log').open('x') as log:
                process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                state.update(status='running', pid=process.pid)
                write(out/'state.json', state)
                reason = None
                while process.poll() is None:
                    now = time.time()
                    task = read(out/'actual/task.json') or {'task': 'startup', 'started_at': started}
                    cap = 2100 if task['task'] == 'R1-recompute-update' else 900
                    sample = resources()
                    memory = 0.0
                    if any(sample[k]['returncode'] != 0 for k in ('gpus', 'processes')):
                        reason = 'resource_query_failed'
                    else:
                        for line in sample['processes']['stdout'].splitlines():
                            fields = [x.strip() for x in line.split(',', 3)]
                            if len(fields) == 4 and fields[1] == str(process.pid):
                                memory += float(fields[2])
                    resident, size = rss(process.pid), artifact_bytes(root)
                    if now-started >= 2370 or previous + now-started >= 7170:
                        reason = 'restoration_or_total_time_budget'
                    if now-task['started_at'] >= cap-30:
                        reason = 'restoration_task_time_budget'
                    if resident > 64*1024**3 or size >= 8*1024**3 or memory >= 73728:
                        reason = 'unchanged_memory_or_artifact_limit'
                    with (out/'resources.jsonl').open('a') as file:
                        file.write(json.dumps({'sample': sample, 'task': task, 'rss_bytes': resident,
                                              'artifact_bytes': size, 'own_gpu_memory_mib': memory})+'\n')
                    if reason:
                        stop_owned(process)
                        break
                    time.sleep(2)
                state.update(status='complete' if process.returncode == 0 and reason is None else 'stopped',
                    exit_code=process.poll(), stop_reason=reason, ended_at=time.time())
                state['elapsed_gpu_seconds'] = state['ended_at']-started
                state['cumulative_gpu_seconds'] = previous + state['elapsed_gpu_seconds']
                write(out/'state.json', state)
        except BaseException as error:
            if process:
                stop_owned(process)
                state.update(exit_code=process.poll(), ended_at=time.time())
                state['elapsed_gpu_seconds'] = state['ended_at']-state['started_at']
            state.update(status='supervisor_error', error={'type': type(error).__name__, 'message': str(error)})
            write(out/'state.json', state)
            raise
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    run(args.plan.resolve(), args.run_root.resolve())
