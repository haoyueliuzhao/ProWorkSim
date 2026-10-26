"""Execute the fixed new capability panel with bounded independent runtime lanes."""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import resource
import shutil
import signal
import threading
import time
import traceback

from proworksim import software_benchmark_dispatch_v062 as policy
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT, BATCH_ROOT = policy.ROOT, policy.BATCH_ROOT
RUN_ROOT = policy.COORDINATOR_RUN_ROOT
VERSION = "v062-fixed-capability-coordinator-r1"
DOCKER_CONFIG = ROOT / 'runs/software-panel-v053/docker/config/daemon.json'
DISK_FLOOR_BYTES = 128 * 1024**3

def coordinator_limits():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("The capability coordinator must run as the ordinary project user")
    rows = Path("/proc/self/cgroup").read_text().splitlines()
    paths = [line.split(":", 2)[2] for line in rows if line.startswith("0::")]
    if len(paths) != 1:
        raise ValueError("The coordinator requires its own unified cgroup")
    relative = PurePosixPath(paths[0])
    if relative.name != "proworksim-v062-ref-development.service" or ".." in relative.parts:
        raise ValueError("Run formal capability evaluation only in the newly owned bounded coordinator unit")
    folder = Path("/sys/fs/cgroup") / str(relative).lstrip("/")
    values = {name: (folder / name).read_text().strip()
              for name in ("memory.max", "memory.swap.max", "pids.max")}
    cpu_file = folder / "cpu.max"
    values["cpu.max"] = cpu_file.read_text().strip() if cpu_file.exists() else None
    cpu = values["cpu.max"].split() if values["cpu.max"] is not None else None
    expected_affinity = [int(value) for value in policy.cpu_set("coordinator", 0).split(",")]
    actual_affinity = sorted(os.sched_getaffinity(0))
    if (
        values["memory.max"] != str(16 * 1024**3)
        or values["memory.swap.max"] != "0"
        or values["pids.max"] != "512"
        or actual_affinity != expected_affinity
        or (cpu is not None and (len(cpu) != 2 or not all(value.isdigit() for value in cpu)
            or int(cpu[1]) <= 0 or int(cpu[0]) <= 0 or int(cpu[0]) > 4 * int(cpu[1])))
    ):
        raise ValueError("Actual coordinator CPU/RAM/PID/swap hard limits differ from the grant")
    return {
        "cgroup": paths[0],
        "actual_limits": values,
        "actual_cpu_affinity": actual_affinity,
        "cpu_hard_boundary": "fixed process affinity",
        "cpu_quota_controller_available": cpu is not None,
        "cpu_quota_enforced": cpu is not None,
        "uid": os.getuid(),
        "host_configuration_changed": False,
    }

def load(ref):
    return json.loads(checked(ref).read_bytes())

def _result_is_quiet(result):
    """A local failure may continue only when its owned runtime was cleaned."""
    proof = result.get("quiescence")
    if isinstance(proof, dict) and set(proof) == {"path", "bytes", "sha256"}:
        proof = load(proof)
    return (
        isinstance(proof, dict)
        and proof.get("quiescent") is True
        and not proof.get("cleanup_errors")
    )

def _handle_termination(event):
    if threading.current_thread() is not threading.main_thread():
        return {}
    return {
        sig: signal.signal(sig, lambda *_: event.set()) for sig in (signal.SIGTERM, signal.SIGINT)
    }

def _restore_termination(previous):
    for sig, handler in previous.items():
        signal.signal(sig, handler)

def diagnostic_host_limits():
    allowed = sorted(os.sched_getaffinity(0))
    if len(allowed) < 4:
        raise ValueError("The zero-model diagnostic requires four available logical CPUs")
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    cap = 16 * 1024**3 if hard == resource.RLIM_INFINITY else min(hard, 16 * 1024**3)
    if cap < 4 * 1024**3:
        raise ValueError("The inherited address-space limit cannot fit the private SDK diagnostic")
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    os.sched_setaffinity(0, set(allowed[:4]))
    return {
        "address_space_bytes": cap,
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "scope": "current ordinary diagnostic process and its children only",
    }


def grading_module():
    spec = importlib.util.spec_from_file_location("v062_capability_grading", ROOT / "tools/run_capability_grading_v062.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare():
    """Materialize only immutable local plans; no runtime or model access."""
    dispatch = policy.create_plan()
    rows = dispatch['rows']
    if (len(rows) != 174 or len({row['slot_id'] for row in rows}) != 174
            or [row['slot_index'] for row in rows] != list(range(174))
            or any(row['replicate'] != 0 for row in rows[:150])
            or any(row['replicate'] == 0 for row in rows[150:])):
        raise ValueError('Require the fixed 150 main slots followed by 24 predeclared repeats')
    grading = grading_module()
    grading.prepare_manifest()
    reused = grading.prepare_reused_qualifications()
    controls = grading.prepare_controls()
    value = {'version': VERSION, 'plan': reference(policy.PLAN_FILE), 'controls': controls,
             'reused_qualifications': reused, 'sources': policy.sources(),
             'disk_boundary': prepare_disk_boundary(),
             'new_generation_rows': [row['slot_index'] for row in rows],
             'new_generation_token_upper_bound': sum(row['generation_token_upper_bound'] for row in rows),
             'automatic_replay': False, 'prepared_without_runtime_operations': True}
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    path = RUN_ROOT / 'coordinator-plan.json'
    if path.exists():
        if json.loads(path.read_bytes()) != value:
            raise ValueError('Prepared coordinator plan changed; never overwrite its evidence')
        return reference(path)
    return write_new(path, value)


def prepare_disk_boundary():
    """Read local daemon config and filesystem identities; never contact Docker."""
    source = reference(DOCKER_CONFIG)
    config = load(source)
    data_root = Path(config['data-root']).resolve()
    expected = ROOT / 'runs/software-panel-v053/docker/data'
    if data_root != expected.resolve():
        raise ValueError('The dedicated Docker data-root differs from the reviewed project daemon')
    paths = [ROOT.resolve(), data_root]
    devices = {str(path): path.stat().st_dev for path in paths}
    return {'daemon_configuration': source, 'paths_and_devices': devices,
            'same_filesystem': len(set(devices.values())) == 1, 'minimum_free_bytes': DISK_FLOOR_BYTES,
            'poll_seconds': 5, 'disk_hard_quota': False,
            'scope': 'admission and early cancellation only; shared filesystem is unchanged'}


def check_disk_boundary(boundary):
    checked(boundary['daemon_configuration'])
    if boundary['minimum_free_bytes'] != DISK_FLOOR_BYTES or boundary.get('disk_hard_quota') is not False:
        raise ValueError('The disk guard is a fixed free-space floor, not a hard quota')
    observed = {}
    for path, device in boundary['paths_and_devices'].items():
        if Path(path).stat().st_dev != device:
            raise ValueError('A guarded filesystem changed since local preparation')
        if device not in observed:
            observed[device] = {'path': path, 'device': device, 'free_bytes': shutil.disk_usage(path).free}
    return {'passed': bool(observed) and all(row['free_bytes'] >= DISK_FLOOR_BYTES for row in observed.values()),
            'filesystems': list(observed.values()), 'minimum_free_bytes': DISK_FLOOR_BYTES,
            'disk_hard_quota': False}


def _event(kind, **values):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    with (RUN_ROOT / 'events.jsonl').open('a') as stream:
        stream.write(json.dumps({'unix': time.time(), 'kind': kind, **values}, ensure_ascii=False) + '\n')


def _progress(value):
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_write(RUN_ROOT / 'progress.json', json_bytes({'version': VERSION, 'unix': time.time(), **value}))


def model_admission_exhausted(ready):
    if ready:
        return False
    folders = [BATCH_ROOT / 'residents' / f'model-{index}' for index in (0, 1)]
    return all((folder / 'spec.json').exists() and (folder / 'closed.json').exists() for folder in folders)


def _diagnostic_arm(index):
    if type(index) is not int or index not in (1, 2, 3, 4):
        raise ValueError('Use one of the four explicitly reserved diagnostic identities')
    return 'BASE' if index % 2 else 'FIX'


def diagnostic_admission(index):
    arm = _diagnostic_arm(index)
    if (RUN_ROOT / 'execution-started.json').exists():
        raise ValueError('Diagnostics cannot run after this panel has entered execution')
    qualifications = BATCH_ROOT / 'diagnostic-qualifications' / arm
    for path in qualifications.glob('*.json'):
        if load(reference(path)).get('sources') == policy.sources():
            raise ValueError('This protocol has already passed for current sources; do not repeat it')
    attempts = BATCH_ROOT / 'diagnostic-attempts'
    if (attempts / f'{index}-intent.json').exists() or (attempts / f'{index}.json').exists():
        raise ValueError('An entered diagnostic identity cannot be retried')
    if index > 2:
        prior = load(reference(attempts / f'{index - 2}.json'))
        result = load(prior['result']) if prior.get('result') else None
        if (not isinstance(result, dict) or result.get('model_calls') != 0 or not _result_is_quiet(result)
                or prior.get('sources') == policy.sources()):
            raise ValueError('A reserved diagnostic requires a cleaned zero-model prior attempt and revised sources')
    return arm


def diagnose(index=1):
    policy.require_v062_allowed('v062.run')
    arm = diagnostic_admission(index)
    sources = policy.sources()
    limits = diagnostic_host_limits()
    attempts = BATCH_ROOT / 'diagnostic-attempts'
    attempts.mkdir(parents=True, exist_ok=True)
    write_new(attempts / f'{index}-intent.json', {'version': VERSION, 'arm': arm, 'index': index,
              'sources': sources, 'actual_host_limits': limits})
    from proworksim.software_benchmark_episode_v062 import run_diagnostic

    stopped = threading.Event()
    handlers = _handle_termination(stopped)
    record = {'version': VERSION, 'arm': arm, 'diagnostic_index': index,
              'sources': sources, 'actual_host_limits': limits, 'result': None}
    try:
        record['result'] = run_diagnostic(index=index, stop_event=stopped)
    except BaseException as error:
        record.update(status='runtime_exception', error={'type': type(error).__name__, 'message': str(error)},
                      traceback=traceback.format_exc(), cleanup_not_inferred_without_result=True)
        raise
    finally:
        write_new(attempts / f'{index}.json', record)
        _restore_termination(handlers)
    result = load(record['result'])
    if (result.get('passed') is not True or result.get('model_calls') != 0
            or not _result_is_quiet(result) or sources != policy.sources()):
        raise ValueError('Zero-model protocol diagnostic must pass, be cleaned and bind the current sources')
    directory = BATCH_ROOT / 'diagnostic-qualifications' / arm
    directory.mkdir(parents=True, exist_ok=True)
    return write_new(directory / f'{index}.json', record)


def diagnostic_qualifications():
    results = {}
    for arm in ('BASE', 'FIX'):
        matches = [load(reference(path)) for path in (BATCH_ROOT / 'diagnostic-qualifications' / arm).glob('*.json')
                   if load(reference(path)).get('sources') == policy.sources()]
        if len(matches) != 1:
            raise ValueError('Each native protocol needs exactly one current-source qualification')
        record = matches[0]
        result = load(record['result'])
        if (record.get('version') != VERSION or record.get('arm') != arm
                or record.get('sources') != policy.sources() or result.get('passed') is not True
                or not _result_is_quiet(result) or result.get('model_calls') != 0):
            raise ValueError('Both native protocols need current, clean zero-model qualifications')
        results[arm] = record['result']
    return results


def generation_stop_reason(result):
    if not _result_is_quiet(result):
        return 'unproven_generation_cleanup'
    ledger = result.get('ledger')
    if (not isinstance(ledger, dict) or ledger.get('complete_actual_tokens') is None
            or ledger.get('complete_actual_tokens') != ledger.get('known_actual_tokens')
            or ledger.get('inflight') is not None or ledger.get('uncertain_reserved_tokens', 0)):
        return 'unresolved_generation_accounting'
    if result.get('response_projection_fault') or result.get('batch_stop_required') is True:
        return 'generation_integrity_failure'
    if result.get('status') == 'closed' or result.get('failure_scope') == 'local':
        return None
    return 'unclassified_generation_failure'


@contextmanager
def _executor_pair(stop):
    """Signal owned tasks before executor shutdown waits after an exception."""
    with ThreadPoolExecutor(max_workers=2) as generation, ThreadPoolExecutor(max_workers=2) as grading:
        try:
            yield generation, grading
        finally:
            stop.set()


def execute_queue(rows, *, controls, qualifications, grading, runtime, run_episode,
                  stop_event=None, progress_sink=_progress, event_sink=_event, disk_check=None):
    """Two generation lanes and two grader lanes; never put entered rows back."""
    stop = stop_event if stop_event is not None else threading.Event()
    pending = list(rows)
    control_queue, score_queue = list(controls), []
    qualified = dict(qualifications)
    generations, scores, controls_done = {}, {}, {}
    grade_futures, generation_futures = {}, {}
    lanes = [0, 1]
    failure, residents, closure, disk_observation = None, [], [], None
    entered = set()
    if len({row['slot_id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate new slot identity cannot enter the queue')

    def fail(kind, **values):
        nonlocal failure
        failure = failure or {'kind': kind, **values}
        stop.set()

    def report():
        progress_sink({'phase': 'stopping' if stop.is_set() else 'running',
            'planned_generation': len(rows), 'entered_generation': len(entered),
            'finished_generation': len(generations), 'pending_generation': len(pending),
            'active_generation': len(generation_futures), 'active_grading': len(grade_futures),
            'pending_controls': len(control_queue), 'pending_scores': len(score_queue),
            'finished_scores': len(scores), 'failure': failure, 'disk_guard': disk_observation})

    try:
        if disk_check is not None:
            disk_observation = disk_check()
            if disk_observation.get('passed') is not True:
                fail('disk_free_space_floor', observation=disk_observation)
                raise RuntimeError('The shared-filesystem free-space floor did not pass admission')
        residents = runtime.start_residents()
        last_capacity = last_disk = time.monotonic()
        with _executor_pair(stop) as (generation_pool, grade_pool):
            while pending or control_queue or score_queue or generation_futures or grade_futures:
                if stop.is_set() and failure is None:
                    fail('coordinator_cancellation_requested')
                if disk_check is not None and time.monotonic() - last_disk >= 5:
                    disk_observation = disk_check()
                    last_disk = time.monotonic()
                    if disk_observation.get('passed') is not True:
                        fail('disk_free_space_floor', observation=disk_observation)
                if not stop.is_set() and time.monotonic() - last_capacity > 60:
                    residents = runtime.start_residents()
                    last_capacity = time.monotonic()
                while not stop.is_set() and lanes and (score_queue or control_queue):
                    lane = lanes[0]
                    if score_queue:
                        result_ref = score_queue[0]
                        request_ref = grading.prepare_score(result_ref, lane=lane)
                        score_queue.pop(0)
                        kind = 'score'
                    else:
                        matches = [(candidate, ref) for candidate in lanes for ref in control_queue
                                   if load(ref)['cpuset_cpus'] == grading.selected_cpus(candidate)]
                        if not matches:
                            fail('unmatched_control_cpu_lane')
                            break
                        lane, request_ref = matches[0]
                        control_queue.remove(request_ref)
                        kind = 'control'
                    lanes.remove(lane)
                    future = grade_pool.submit(grading.run_request, request_ref, stop_event=stop)
                    grade_futures[future] = kind, request_ref, lane
                # Known environment failures remain in the fixed panel as blocked rows.
                for row in list(pending):
                    if qualified.get(row['instance_id'], {}).get('status') == 'not_qualified':
                        pending.remove(row)
                        generations[row['slot_id']] = {'status': 'not_qualified', 'entered': False,
                                                      'qualification': qualified[row['instance_id']]}
                if not stop.is_set() and pending and len(generation_futures) < 2:
                    residents = runtime.ready_residents()
                    if model_admission_exhausted(residents):
                        fail('model_admission_exhausted', reason='Both resident identities closed; no automatic restart')
                while not stop.is_set() and residents and len(generation_futures) < 2:
                    main_remaining = any(row['replicate'] == 0 for row in pending) or any(
                        row['replicate'] == 0 for row, _ in generation_futures.values())
                    row = next((row for row in pending
                                if (not main_remaining or row['replicate'] == 0)
                                and qualified.get(row['instance_id'], {}).get('status') == 'qualified'), None)
                    if row is None:
                        break
                    counts = {resident['root']: sum(active['root'] == resident['root']
                              for _, active in generation_futures.values()) for resident in residents}
                    resident = min(residents, key=lambda item: (counts[item['root']], item['root']))
                    if counts[resident['root']] >= 2:
                        break
                    pending.remove(row)
                    if row['slot_id'] in entered:
                        raise RuntimeError('A consumed slot was placed back in the pending queue')
                    entered.add(row['slot_id'])
                    event_sink('generation_entered', slot_id=row['slot_id'], resident=resident['root'])
                    future = generation_pool.submit(run_episode, row, resident, stop_event=stop)
                    generation_futures[future] = row, resident
                report()
                futures = list(grade_futures) + list(generation_futures)
                if not futures:
                    if stop.is_set() or not (pending or control_queue or score_queue):
                        break
                    if pending and not control_queue and any(
                            qualified.get(row['instance_id'], {}).get('status') not in {'qualified', 'not_qualified'}
                            for row in pending):
                        fail('missing_environment_qualification')
                        continue
                    stop.wait(1)
                    continue
                completed, _ = wait(futures, timeout=1, return_when=FIRST_COMPLETED)
                for future in completed:
                    if future in grade_futures:
                        kind, request_ref, lane = grade_futures.pop(future)
                        lanes.append(lane)
                        request = load(request_ref)
                        try:
                            completion = future.result()
                        except Exception as error:
                            completion = {'status': 'technical_unknown', 'error': str(error)}
                        if not grading.trustworthy_cleanup(request_ref):
                            fail('unproven_grader_cleanup', request=request_ref)
                        if kind == 'score':
                            scores[request['slot_id']] = {'request': request_ref, 'completion': completion}
                        else:
                            task = request['instance_id']
                            controls_done.setdefault(task, {})[request['patch_kind']] = completion
                            if set(controls_done[task]) == {'empty', 'gold'}:
                                try:
                                    qualified[task] = {'status': 'qualified', 'qualification': grading.qualify(task)}
                                except Exception as error:
                                    qualified[task] = {'status': 'not_qualified', 'reason': str(error)}
                        event_sink('grading_finished', job_kind=kind, request=request_ref, status=completion.get('status'))
                    else:
                        row, resident = generation_futures.pop(future)
                        try:
                            result_ref = future.result()
                            result = load(result_ref)
                            if result.get('slot_id') != row['slot_id']:
                                raise ValueError('Episode result belongs to another new slot')
                            generations[row['slot_id']] = {'result': result_ref, 'status': result.get('status'), 'entered': True,
                                                          'retained_objects': result.get('retained_objects', [])}
                            reason = generation_stop_reason(result)
                            if reason:
                                fail(reason, result=result_ref)
                            elif result.get('status') == 'closed':
                                score_queue.append(result_ref)
                        except Exception as error:
                            generations[row['slot_id']] = {'status': 'technical_unknown', 'entered': True, 'error': str(error)}
                            fail('generation_failed_without_trusted_result', slot_id=row['slot_id'])
                        event_sink('generation_finished', slot_id=row['slot_id'], status=generations[row['slot_id']]['status'])
                if stop.is_set() and not grade_futures and not generation_futures:
                    break
    except Exception as error:
        fail('coordinator_error', error={'type': type(error).__name__, 'message': str(error)})
    finally:
        stop.set()
        try:
            closure = runtime.stop_residents()
        except Exception as error:
            closure = [{'owned_unit_stopped': False, 'error': str(error)}]
        if any(record.get('owned_unit_stopped') is not True for record in closure):
            failure = failure or {'kind': 'resident_cleanup_unconfirmed'}
        report()
    return {'version': VERSION, 'generation': generations, 'scores': scores, 'qualifications': qualified,
            'unentered_generation': [row['slot_id'] for row in pending], 'unentered_controls': control_queue,
            'unentered_scores': score_queue, 'resident_closure': closure, 'failure': failure,
            'last_disk_guard': disk_observation,
            'automatic_replay': False, 'historical_results_overwritten': False,
            'retained_objects': [{'slot_id': slot, **obj} for slot, result in generations.items()
                                 for obj in result.get('retained_objects', [])],
            'quiescence_does_not_imply_all_owned_objects_removed': True}


def run():
    authorization = policy.require_v062_allowed('v062.run')
    host_limits = coordinator_limits()
    if (RUN_ROOT / 'execution-started.json').exists():
        raise ValueError('An entered capability batch is not automatically replayed')
    plan_ref = prepare()
    plan = load(plan_ref)
    diagnostics = diagnostic_qualifications()
    dispatch = load(plan['plan'])
    write_new(RUN_ROOT / 'execution-started.json', {'version': VERSION, 'unix': time.time(),
              'authorization': authorization, 'plan': plan_ref, 'actual_host_limits': host_limits,
              'diagnostics': diagnostics})
    from proworksim import software_benchmark_ref_resident_v062 as runtime
    from proworksim.software_benchmark_episode_v062 import run_episode

    stopped = threading.Event()
    handlers = _handle_termination(stopped)
    try:
        result = execute_queue(dispatch['rows'], controls=plan['controls'],
            qualifications=plan['reused_qualifications'], grading=grading_module(), runtime=runtime,
            run_episode=run_episode, stop_event=stopped,
            disk_check=lambda: check_disk_boundary(plan['disk_boundary']))
    finally:
        _restore_termination(handlers)
    result.update(plan=plan_ref, diagnostics=diagnostics, finished_unix=time.time())
    write_new(RUN_ROOT / 'run-summary.json', result)
    _progress({'phase': 'closed' if result['failure'] is None else 'stopped',
               'planned_generation': 174, 'finished_generation': len(result['generation']),
               'finished_scores': len(result['scores']), 'pending_generation': len(result['unentered_generation']),
               'failure': result['failure'], 'summary': reference(RUN_ROOT / 'run-summary.json')})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--execute', action='store_true')
    group.add_argument('--diagnostic', type=int, choices=(1, 2, 3, 4))
    args = parser.parse_args()
    result = prepare() if args.prepare else diagnose(args.diagnostic) if args.diagnostic else run()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
