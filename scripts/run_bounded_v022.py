"""One launch per v0.22 line; N1/W1 may overlap, bridge depends on both.

Each line has its own frozen source and budget. The caps add to exactly two
GPU hours, including loading, with no repeat attempts or successor search.
"""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.storage import read_json
from scripts.run_ne_v021 import checked, lock, read, reference, released_cards, resources, stop_owned, write

VERSION = 'bounded-experiments-v0.22'
CAPS = {'N1': 1800, 'W1': 3600, 'B1': 1800}
MODULES = {'N1': 'scripts.functional_paths_v022', 'W1': 'scripts.evaluate_work_v022',
           'B1': 'scripts.bridge_work_v022'}
LIMITS = {'task_seconds': 900, 'shutdown_reserve_seconds': 30,
          'host_rss_per_line_bytes': 64 * 1024**3, 'host_rss_all_lines_bytes': 64 * 1024**3,
          'artifact_bytes': 8 * 1024**3, 'gpu_process_memory_mib': 73728,
          'model_api_calls': 0, 'max_concurrent_model_instances': 2,
          'max_actor_steps': 1, 'max_critic_steps': 1}


def validate(plan):
    name = plan.get('line')
    if (plan.get('version') != VERSION or name not in CAPS or plan.get('budget_seconds') != CAPS[name]
            or plan.get('limits') != LIMITS or plan.get('gpu_pool') != [2, 3, 4, 5, 6]
            or plan.get('module') != MODULES[name]):
        raise ValueError('Unknown line or changed finite resource limits')
    checked(plan['experiment_plan'])
    if name != 'B1' and plan.get('allow_parameter_updates') is not False:
        raise ValueError('Only B1 can update')
    if name == 'B1':
        if plan.get('allow_parameter_updates') is not True:
            raise ValueError('Bridge update authorization absent')
        n = read_json(checked(plan['N1_qualification']))
        w = read_json(checked(plan['W1_qualification']))
        if (n.get('qualification_passed') is not True or w.get('status') != 'complete'
                or w.get('final_identity_matches_initial') is not True or w.get('source_unchanged') is not True
                or w.get('actor_steps') != 0 or w.get('critic_steps') != 0):
            raise ValueError('Bridge requires completed N1 and trusted frozen W1')
        if any(r.get('status') != 'closed' or not r.get('assessment', {}).get('eligible')
               or r.get('evaluation_guard', {}).get('learning_unchanged') is not True
               or r.get('evaluation_guard', {}).get('rng_restored_exactly') is not True for r in w.get('rows', [])):
            raise ValueError('All paired frozen records must remain trustworthy')
        if len(w.get('rows', [])) != 12:
            raise ValueError('Bridge cannot fill an incomplete W1')
    return name


def rss(pid):
    total, pending, seen = 0, [pid], set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            total += int(Path(f'/proc/{current}/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
            pending.extend(int(p) for p in Path(f'/proc/{current}/task/{current}/children').read_text().split())
        except (FileNotFoundError, ProcessLookupError):
            continue
    return total


def artifact_bytes(root):
    total = 0
    for path in root.rglob('*'):
        try:
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:
            pass  # Atomic temp-file rename raced with this sample.
    return total


def sibling_rss(root):
    total = 0
    for name in CAPS:
        state = read(root / name / 'state.json') or {}
        if state.get('status') == 'running' and type(state.get('pid')) is int:
            total += rss(state['pid'])
    return total


def terminal(root, state, reason, process=None):
    if process:
        stop_owned(process)
    if state.get('attempted'):
        state.update(ended_at=time.time(), exit_code=process.poll() if process else None)
        state['elapsed_gpu_seconds'] = state['ended_at'] - state['started_at']
    state.update(status='complete' if process and process.returncode == 0 and reason is None else 'stopped',
                 stop_reason=reason)
    write(root / 'state.json', state)


def run(plan, plan_path, run_root, preferred=None):
    name = validate(plan)
    out = run_root / name
    out.mkdir(parents=True, exist_ok=True)
    source = code_identity()
    if source['code_dirty']:
        raise ValueError('Freeze the actual line source before observing GPU availability')
    with lock(out):
        previous = read(out / 'state.json')
        if previous and previous.get('attempted'):
            raise ValueError('This line already had its single launch; never auto-retry')
        if (out / 'actual').exists():
            raise FileExistsError('Never reuse an existing experimental output')
        state = {'version': VERSION, 'line': name, 'status': 'waiting', 'attempted': False,
                 'source': source, 'plan': reference(plan_path), 'observer_pid': os.getpid(),
                 'budget_seconds': CAPS[name], 'limits': LIMITS, 'created_at': time.time()}
        write(out / 'state.json', state)
        process = None
        try:
            while True:
                if code_identity() != source or reference(plan_path) != state['plan']:
                    raise ValueError('Frozen source/plan changed while waiting')
                validate(plan)
                sample = resources()
                ready = [g for g in released_cards(sample) if g in plan['gpu_pool']]
                if preferred is not None:
                    ready = [g for g in ready if g == preferred]
                state.update(last_observation=sample, ready_cards=ready)
                write(out / 'state.json', state)
                if ready:
                    gpu = ready[0]
                    # Recheck immediately; no reservation by stale memory readings.
                    confirmation = resources()
                    if gpu in released_cards(confirmation):
                        break
                time.sleep(5)
            started = time.time()
            argv = [sys.executable, '-m', MODULES[name], '--plan', str(checked(plan['experiment_plan'])),
                    '--output', str(out / 'actual')]
            state.update(status='launch_intent', attempted=True, gpu=gpu, started_at=started,
                         command=argv, admission_resources=confirmation)
            write(out / 'state.json', state)
            env = {**os.environ, 'CUDA_VISIBLE_DEVICES': str(gpu), 'HF_HUB_OFFLINE': '1',
                   'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false'}
            env.pop('PROWORKSIM_REPLICA_GPUS', None)
            with (out / 'model.log').open('x') as log:
                process = subprocess.Popen(argv, cwd=Path(__file__).resolve().parents[1], env=env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                state.update(status='running', pid=process.pid)
                write(out / 'state.json', state)
                reason = None
                while process.poll() is None:
                    now = time.time()
                    sample = resources()
                    task = read(out / 'actual/task.json') or {'task': 'startup', 'started_at': started}
                    own = rss(process.pid)
                    all_rss = sibling_rss(run_root)
                    artifacts = artifact_bytes(run_root)
                    memory = 0.0
                    if any(sample[k]['returncode'] != 0 for k in ('gpus', 'processes')):
                        reason = 'resource_query_failed'
                    else:
                        for line in sample['processes']['stdout'].splitlines():
                            fields = [x.strip() for x in line.split(',', 3)]
                            if len(fields) == 4 and fields[1] == str(process.pid):
                                memory += float(fields[2])
                    if now - started >= CAPS[name] - LIMITS['shutdown_reserve_seconds']:
                        reason = 'line_time_budget'
                    if now - task['started_at'] >= LIMITS['task_seconds'] - LIMITS['shutdown_reserve_seconds']:
                        reason = 'task_time_budget'
                    if own > LIMITS['host_rss_per_line_bytes'] or all_rss > LIMITS['host_rss_all_lines_bytes']:
                        reason = 'host_rss_limit'
                    if artifacts >= LIMITS['artifact_bytes']:
                        reason = 'artifact_limit'
                    if memory >= LIMITS['gpu_process_memory_mib']:
                        reason = 'gpu_memory_limit'
                    with (out / 'resources.jsonl').open('a') as file:
                        from proworksim.storage import json_bytes
                        file.write(json_bytes({'sample': sample, 'task': task, 'rss_bytes': own,
                            'all_lines_rss_bytes': all_rss, 'artifact_bytes': artifacts,
                            'own_gpu_memory_mib': memory}).decode() + '\n')
                    if reason:
                        break
                    time.sleep(2)
                terminal(out, state, reason, process)
        except BaseException as error:
            state['supervisor_error'] = {'type': type(error).__name__, 'message': str(error)}
            terminal(out, state, 'supervisor_exception', process)
            raise
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--gpu', type=int)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    run(read_json(args.plan), args.plan.resolve(), args.run_root.resolve(), args.gpu)


if __name__ == '__main__':
    main()
