"""One declared recovery of the resource-interrupted suffix, preserving old attempts."""

import argparse
import copy
import math
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import read_json
from scripts import collaboration_carrier_v026 as original
from scripts.evaluate_work_v022 import checked, reference, write
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_collaboration_carrier_v026 import (
    StableIdleAdmission, card_uuid, stop_reason, storage_preflight, worker_environment,
)
from scripts.run_ne_v021 import lock, resources, stop_owned

VERSION = 'reciprocal-carrier-resource-recovery-v0.26-r3'


def remaining_slots(assigned, progress):
    """Keep all closed records; retry only the single interruption and untouched suffix."""
    if (len(assigned) != 8 or len(progress) != 4
            or [row['slot_id'] for row in progress] != [slot['slot_id'] for slot in assigned[:4]]
            or any(row['status'] != 'closed' for row in progress[:3])
            or progress[3]['status'] != 'started'):
        raise ValueError('Recovery requires the observed three closed and one interrupted prefix')
    return copy.deepcopy(assigned[3:])


def validate(plan):
    base = read_json(checked(plan['original_plan']))
    _, assignment = original.validate_plan(base)
    state = read_json(checked(plan['stopped_worker']))
    progress = read_json(checked(plan['stopped_progress']))
    extension = read_json(checked(plan['budget_extension']))
    slots = remaining_slots(assignment['worker-0'], progress)
    charge = math.ceil(state['elapsed_gpu_seconds'])
    if (plan.get('version') != VERSION or plan.get('slots') != slots
            or plan.get('max_new_episodes') != 5
            or state.get('status') != 'stopped' or state.get('stop_reason') != 'own_gpu_memory_limit'
            or state.get('gpu') != 0 or state.get('completed_slot_count') != 0
            or plan.get('resource_caps') != {'recovery': 12306}
            or plan.get('internal_gpu_seconds') != 12306
            or plan.get('own_gpu_memory_mib') != 81920
            or plan.get('max_new_actor_steps') != 0 or plan.get('max_new_critic_steps') != 0
            or plan.get('automatic_successors') != [] or plan.get('automatic_recovery') is not False
            or extension.get('cumulative_gpu_seconds_cap') != 28800
            or extension.get('own_gpu_memory_mib') != 81920
            or 12306+14374+charge+base['previous_attempt']['budget_charge_seconds'] != 28800):
        raise ValueError('Only the fixed five-slot recovery within the authorized cumulative budget is allowed')
    expected_catalog = read_json(checked(base['catalog']))
    expected_catalog['slots'] = slots
    if read_json(checked(plan['catalog'])) != expected_catalog:
        raise ValueError('Recovery report catalog changed the fixed selected slots')
    return base, slots


def run_worker(plan_path, root):
    plan = read_json(plan_path)
    base, slots = validate(plan)
    output = root/'recovery/actual'
    output.mkdir(parents=True, exist_ok=False)
    source = code_identity()
    if source['code_dirty']:
        raise ValueError('Commit recovery orchestration before model execution')
    report = {'version': VERSION, 'status': 'loading', 'source_before': source,
              'plan': reference(plan_path), 'started_at': time.time(), 'slots': slots,
              'new_actor_steps': 0, 'new_critic_steps': 0, 'model_api_calls': 0,
              'learning_probability_recomputation': False, 'automatic_successors': []}
    write(output/'report.json', report)
    owner = None
    try:
        from proworksim.deterministic_work_v024 import DeterministicCandidateActor
        prior = read_json(checked(base['prior_model_plan']))
        recipe = read_json(checked(base['owner_recipe']))['recipe']
        original.task(output, 'recovery-load-original-9b', 'loading')
        sample = resources()
        write(output/'preload-resources.json', sample)
        if int(os.environ['CUDA_VISIBLE_DEVICES']) not in original.released_gpus(plan, sample):
            raise RuntimeError('Recovery GPU lost its idle capacity before loading')
        owner = DeterministicCandidateActor.from_candidate(prior['model'], manifest=checked(prior['manifest']),
                profile=prior['runtime_profile'], recipe=recipe, output=output/'resident')
        original.task(output, 'recover-exact-original-frozen-state', 'boundary')
        report['restoration'] = original.restore_original_endpoint(owner, base, output)
        report['status'] = 'running'
        write(output/'report.json', report)
        report.update(original.collect(owner, base, slots, output))
    except BaseException as error:
        report.update(status='interrupted_or_error', error={'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        if owner is not None:
            report.update(final_actor_identity=owner._make_identity(), actor_steps=owner.actor_steps,
                          critic_steps=owner.critic_steps)
        report.update(ended_at=time.time(), source_after=code_identity())
        report['source_unchanged'] = report['source_before']==report['source_after']
        if (output/'progress.json').exists():
            report['rows'] = read_json(output/'progress.json')
            report['not_started'] = slots[len(report['rows']):]
        write(output/'report.json', report)
    return report


def verify_worker(root, slots, source, base):
    report = read_json(root/'recovery/actual/report.json')
    marker = read_json(checked(base['checkpoint_marker']))
    rows = report.get('rows', [])
    if (report.get('status') != 'complete' or report.get('source_before') != source
            or report.get('source_after') != source or report.get('source_unchanged') is not True
            or report.get('final_actor_identity') != marker['actor_identity']
            or report.get('actor_steps') != 3 or report.get('critic_steps') != 3
            or len(rows) != 5 or [r['slot_id'] for r in rows] != [s['slot_id'] for s in slots]
            or any(r.get('status') != 'closed' or r.get('assessment', {}).get('eligible') is not True
                   or r.get('evaluation_guard', {}).get('learning_unchanged') is not True
                   or r.get('evaluation_guard', {}).get('rng_restored_exactly') is not True for r in rows)):
        raise ValueError('Recovery did not preserve the frozen endpoint and all five known slots')


def run(plan_path, root):
    plan = read_json(plan_path)
    base, slots = validate(plan)
    source = code_identity()
    if source['code_dirty']:
        raise ValueError('Recovery supervisor must run a committed checkout')
    root.mkdir(parents=True, exist_ok=False)
    (root/'recovery').mkdir()
    summary = {'version': VERSION, 'status': 'waiting', 'source': source, 'plan': reference(plan_path),
               'observer_pid': os.getpid(), 'started_at': time.time(), 'parameter_updates': 0,
               'model_api_calls': 0, 'automatic_successors': [], 'caps': plan['resource_caps'],
               'worker_assignments': {'recovery': slots}}
    state = {'worker': 'recovery', 'status': 'waiting', 'attempted': False,
             'budget_seconds': 12306, 'source': source, 'slots': slots}
    process, log = None, None

    def publish():
        summary.update(worker_statuses={'recovery': state['status']}, observed_at=time.time())
        write(root/'supervisor.json', summary)
        write(root/'recovery/state.json', state)

    with lock(root):
        publish()
        try:
            storage_preflight(plan, root, 'recovery')
            gate = StableIdleAdmission(plan)
            while time.time()<plan['queue_deadline_at']:
                sample = resources()
                choices = gate.observe(sample, now=time.time())
                state.update(last_admission_observation=sample, ready_cards=choices,
                             idle_observed_since=dict(gate.since))
                publish()
                if choices:
                    confirmed = resources()
                    choices = gate.observe(confirmed, now=time.time())
                    if choices:
                        gpu = choices[0]
                        break
                time.sleep(5)
            else:
                state.update(status='not_started_queue_wait_deadline', ended_at=time.time())
                summary.update(status='closed_with_incomplete_workers', ended_at=time.time())
                publish()
                return summary
            validate(plan)
            log = (root/'recovery/model.log').open('x')
            command = [sys.executable, '-m', 'scripts.recover_collaboration_carrier_v026',
                       '--plan', str(plan_path), '--run-root', str(root), '--worker']
            state.update(status='launch_intent', attempted=True, gpu=gpu, gpu_uuid=card_uuid(confirmed, gpu),
                         started_at=time.time(), command=command, admission_resources=confirmed)
            publish()
            process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                        env=worker_environment(plan, root, 'recovery', gpu), stdin=subprocess.DEVNULL,
                        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            identity = worker_identity(process.pid)
            if identity.get('alive') is not True:
                raise RuntimeError('Recovery worker identity unavailable')
            state.update(status='running', pid=process.pid, worker_start_ticks=identity['start_ticks'])
            guard = TelemetryGuard(gpu, state['gpu_uuid'], identity['start_ticks'], worker_pid=process.pid)
            summary['status'] = 'running'
            reason, last_size, size = None, 0, 0
            while process.poll() is None:
                now = time.time()
                if now-last_size>=30:
                    size, last_size = artifact_bytes(root), now
                sample = target_resources(gpu, worker_pid=process.pid)
                if process.poll() is not None:
                    break
                observed = guard.observe(sample, time.time(), process.pid, gpu, own_memory_limit_mib=81920)
                task_path = root/'recovery/actual/task.json'
                task = read_json(task_path) if task_path.exists() else {'kind': 'loading', 'started_at': state['started_at']}
                memory = rss(process.pid)
                reason = stop_reason(plan, state, task, now=time.time(), root_started=summary['started_at'],
                         own_rss=memory, all_rss=memory, size=size, free_bytes=shutil.disk_usage(root).free)
                reason = reason or observed['stop_reason']
                state.update(task=task, telemetry=observed)
                with (root/'recovery/resources.jsonl').open('a') as file:
                    import json
                    file.write(json.dumps({'sample': sample, 'telemetry': observed, 'task': task})+'\n')
                publish()
                if reason:
                    stop_owned(process)
                    break
                time.sleep(5)
            process.wait(timeout=15)
            reason = reason or ('worker_failed' if process.returncode else None)
            if reason is None:
                try:
                    verify_worker(root, slots, source, base)
                except (ValueError, KeyError, OSError) as error:
                    reason = 'unqualified_frozen_endpoint'
                    state['verification_error'] = str(error)
            state.update(status='complete' if reason is None else 'stopped', ended_at=time.time(),
                         exit_code=process.returncode, stop_reason=reason)
            state['elapsed_gpu_seconds'] = state['ended_at']-state['started_at']
            summary.update(status='complete' if reason is None else 'closed_with_incomplete_workers',
                           ended_at=time.time())
        except BaseException as error:
            if process is not None and process.poll() is None:
                stop_owned(process)
                process.wait(timeout=15)
            state.update(status='stopped' if state['attempted'] else 'not_started_supervisor_error',
                         ended_at=time.time(), stop_reason='supervisor_error')
            if state.get('started_at'):
                state['elapsed_gpu_seconds'] = state['ended_at']-state['started_at']
            summary.update(status='supervisor_error', ended_at=time.time(),
                           error={'type': type(error).__name__, 'message': str(error)})
            raise
        finally:
            if log is not None:
                log.close()
            publish()
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    result = run_worker(args.plan.resolve(), args.run_root.resolve()) if args.worker else run(args.plan.resolve(), args.run_root.resolve())
    raise SystemExit(0 if result['status']=='complete' else 2)
