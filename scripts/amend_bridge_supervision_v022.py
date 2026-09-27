"""Attach a bounded resource amendment to the same still-running B1 process.

This changes resource ceilings only. It never restarts a model, resamples a
world, edits the worker source, changes optimizer data, or launches a successor.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import time

from scripts.run_bounded_v022 import artifact_bytes, resources, rss, write
from proworksim.storage import digest, read_json


def identity(pid):
    root = Path(f'/proc/{pid}')
    try:
        fields = (root/'stat').read_text().split()
        return {'pid': pid, 'start_ticks': fields[21], 'state': fields[2],
                'uid': root.stat().st_uid, 'command': (root/'cmdline').read_bytes().replace(b'\0', b' ').decode()}
    except FileNotFoundError:
        return None


def reference(path):
    return {'path': str(path.resolve()), 'sha256': digest(path.read_bytes())}


def live_matches(expected):
    found = identity(expected['pid'])
    return found is not None and found['state'] != 'Z' and all(found[k] == expected[k] for k in ('pid', 'start_ticks', 'uid', 'command'))


def run(plan_path):
    plan = read_json(plan_path)
    root = Path(plan['run_root'])
    folder = root/'B1'
    worker, observer = plan['worker'], plan['previous_observer']
    if (worker['uid'] != os.getuid() or observer['uid'] != os.getuid()
            or 'scripts.bridge_work_v022' not in worker['command']
            or 'scripts.run_bounded_v022' not in observer['command']
            or not live_matches(worker) or not live_matches(observer)
            or os.getpgid(worker['pid']) != worker['pid'] or os.getpgid(observer['pid']) != observer['pid']):
        raise ValueError('Only the identified own worker and its separate observer can be amended')
    original = read_json(folder/'state.json')
    if original['pid'] != worker['pid'] or original['observer_pid'] != observer['pid'] or original['status'] != 'running':
        raise ValueError('B1 ownership changed')
    closed = [read_json(root/name/'state.json') for name in ('N1', 'W1')]
    if any(x['status'] != 'complete' for x in closed):
        raise ValueError('Only released, closed N1/W1 allocations can support this amendment')
    used = sum(x['elapsed_gpu_seconds'] for x in closed)
    if plan['line_seconds'] != 2400 or plan['update_seconds'] != 1800 or used + 2400 > 7200:
        raise ValueError('Amendment must preserve the two-GPU-hour total ceiling')
    current = read_json(folder/'actual/update/report.json')
    if current['actor_optimizer_steps'] or current['critic_optimizer_steps']:
        raise ValueError('This declared resource correction is before any optimizer step')
    state = {'version': 'same-process-resource-amendment-v0.22', 'status': 'attaching',
             'plan': reference(plan_path), 'original_state': original, 'worker': worker,
             'observer_pid': os.getpid(), 'gpu': original['gpu'], 'started_at': original['started_at'],
             'line_seconds': 2400, 'update_seconds': 1800, 'previous_closed_gpu_seconds': used,
             'model_restarted': False, 'new_sampling_slots': 0, 'source_changed': False}
    write(folder/'state-before-resource-amendment.json', original)
    # Stop only the separate resource observer, not its worker process group.
    # Our observer is already running and owns continuous supervision below.
    os.kill(observer['pid'], signal.SIGSTOP)
    write(folder/'state-amended.json', state)
    os.kill(observer['pid'], signal.SIGKILL)
    original.update(status='resource_observer_superseded', superseded_by_pid=os.getpid(),
                    amendment=reference(plan_path), actual_worker_continues=True)
    write(folder/'state.json', original)
    state['status'] = 'running'
    write(folder/'state-amended.json', state)
    reason = None
    while live_matches(worker):
        now = time.time()
        task = read_json(folder/'actual/task.json')
        cap = 1800 if task['task'] == 'B1-single-shared-update' else 900
        observation = resources()
        memory = 0.0
        if any(observation[k]['returncode'] != 0 for k in ('gpus', 'processes')):
            reason = 'resource_query_failed'
        else:
            for row in observation['processes']['stdout'].splitlines():
                fields = [x.strip() for x in row.split(',', 3)]
                if len(fields) == 4 and fields[1] == str(worker['pid']):
                    memory += float(fields[2])
        resident, size = rss(worker['pid']), artifact_bytes(root)
        if now - state['started_at'] >= 2370:
            reason = 'amended_line_time_budget'
        if now - task['started_at'] >= cap - 30:
            reason = 'amended_task_time_budget'
        if resident > 64 * 1024**3 or size >= 8 * 1024**3 or memory >= 73728:
            reason = 'unchanged_memory_or_artifact_limit'
        with (folder/'resources-amended.jsonl').open('a') as out:
            out.write(json.dumps({'sample': observation, 'task': task, 'rss_bytes': resident,
                                  'artifact_bytes': size, 'own_gpu_memory_mib': memory})+'\n')
        if reason:
            os.killpg(worker['pid'], signal.SIGTERM)
            until = time.monotonic()+5
            while live_matches(worker) and time.monotonic() < until:
                time.sleep(.2)
            if live_matches(worker):
                os.killpg(worker['pid'], signal.SIGKILL)
            break
        time.sleep(2)
    state.update(status='stopped' if reason else 'worker_ended', stop_reason=reason,
                 ended_at=time.time(), exit_code=None,
                 exit_code_scope='Attached observer is not the model parent; no exit code is fabricated.')
    state['elapsed_gpu_seconds'] = state['ended_at']-state['started_at']
    report = folder/'actual/report.json'
    if report.exists():
        state['worker_report'] = reference(report)
        state['worker_report_status'] = read_json(report).get('status')
    write(folder/'state-amended.json', state)
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    run(parser.parse_args().plan)
