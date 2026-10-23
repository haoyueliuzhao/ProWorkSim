"""Adopt the original once-only deferred pass with two same-resource graders.

The original watcher/driver files and endpoint attempt directories are retained.
Only the new driver's progress/summary and explicit takeover evidence are added.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools'), str(ROOT)]
import watch_deferred_scoring_v054 as watcher  # noqa: E402
from proworksim import software_benchmark_deferred_scoring_v054 as original  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new  # noqa: E402
from proworksim.storage import atomic_write, json_bytes  # noqa: E402

VERSION = 'v054-deferred-scoring-parallel-adoption-r2'
OLD_UNIT = 'proworksim-v054-deferred-scoring-r1.service'
OLD = ROOT / 'runs/software-benchmark-v054/deferred-scoring-r1'
OUT = ROOT / 'runs/software-benchmark-v054/deferred-scoring-parallel-r2'
OLD_SEAL = ROOT / 'runs/software-benchmark-v054/deferred-scoring-watch-seal-r1.json'
HOLDS = {'psf__requests-1142', 'matplotlib__matplotlib-26466'}


def now():
    return datetime.now(timezone.utc).isoformat()


def load(ref):
    return json.loads(checked(ref).read_bytes())


def process(pid):
    try:
        raw = (Path('/proc') / str(pid) / 'stat').read_text()
    except FileNotFoundError:
        return None
    fields = raw[raw.rfind(')') + 2:].split()
    return {'pid': pid, 'start_ticks': int(fields[19]), 'state': fields[0], 'ppid': int(fields[1])}


def exact_process_alive(expected, current):
    return (current is not None and current['pid'] == expected['pid']
            and current['start_ticks'] == expected['start_ticks'] and current['state'] != 'Z')


def validate(ref):
    plan = load(ref)
    if (plan.get('version') != VERSION or plan.get('old_output') != str(OLD)
            or plan.get('output') != str(OUT) or plan.get('maximum_workers') != 2
            or plan.get('hold_instance_ids') != sorted(HOLDS)
            or plan.get('maximum_additional_attempts_per_endpoint') != 1
            or plan.get('model_calls') != 0 or plan.get('source') != reference(__file__)):
        raise ValueError('Unexpected parallel deferred scoring plan')
    seal = load(plan['old_watch_seal'])
    watcher.verify_seal(seal)
    for key in ('inventory', 'binding', 'original_trigger', 'parent_freeze_intent', 'parent_frozen'):
        load(plan[key])
    if seal['output'] != str(OLD):
        raise ValueError('Original watcher output root changed')
    return plan


def freeze():
    seal_ref = reference(OLD_SEAL)
    watcher.verify_seal(load(seal_ref))
    inventory_ref = reference(OLD / 'inventory.json')
    inventory = load(inventory_ref)
    held = [x['exception_id'] for x in inventory['exceptions']
            if x['domain'] == 'scoring' and x['slot']['instance_id'] in HOLDS]
    if len(held) != 4:
        raise ValueError('Expected the exact four reviewed deterministic-failure holds')
    freeze_ref = reference(OUT / 'parent-freeze-intent.json')
    frozen_ref = reference(OUT / 'parent-frozen.json')
    intent, frozen = load(freeze_ref), load(frozen_ref)
    if (intent['old_unit'] != OLD_UNIT or frozen['child_signals'] != 0
            or frozen['old_progress_unchanged'] is not True
            or frozen['old_service_not_stopped'] is not True):
        raise ValueError('Missing parent-only handoff evidence')
    ref = write_new(OUT / 'plan.json', {'version': VERSION, 'created_utc': now(),
        'source': reference(__file__), 'old_watch_seal': seal_ref,
        'inventory': inventory_ref, 'binding': reference(OLD / 'binding.json'),
        'original_trigger': reference(OLD / 'watch-trigger.json'),
        'parent_freeze_intent': freeze_ref, 'parent_frozen': frozen_ref,
        'old_output': str(OLD), 'output': str(OUT), 'maximum_workers': 2,
        'hold_instance_ids': sorted(HOLDS), 'held_exception_ids': held,
        'maximum_additional_attempts_per_endpoint': 1,
        'original_endpoint_directories_and_grader_locks_reused': True,
        'old_progress_and_summary_overwritten': False, 'model_calls': 0})
    validate(ref)
    return ref


def observe_child(plan_ref):
    plan = validate(plan_ref)
    intent, frozen = load(plan['parent_freeze_intent']), load(plan['parent_frozen'])
    parent, child = process(intent['parent_before']['pid']), process(intent['child_before']['pid'])
    if (not exact_process_alive(intent['parent_before'], parent) or parent['state'] != 'T'
            or exact_process_alive(intent['child_before'], child)):
        raise ValueError('Exact parent must remain frozen and original child must naturally finish')
    started = load(intent['original_started'])
    request = load(started['retry_request'])
    identity, run_id = original.expected_identity(request, {})
    if run_id != started['retry_run_id']:
        raise ValueError('Original started attempt identity changed')
    official = original.existing_report(request, identity, run_id)
    folder = Path(intent['original_started']['path']).parent
    completion = reference(folder / 'completion.json') if (folder / 'completion.json').exists() else None
    return write_new(OUT / 'natural-child-exit.json', {'version': VERSION, 'observed_utc': now(),
        'plan': plan_ref, 'parent_observation': parent, 'child_observation': child,
        'original_child': intent['original_child'], 'original_started': intent['original_started'],
        'original_endpoint': frozen['active_attempt_ids'][0], 'retry_run_id': run_id,
        'official_report': official, 'original_driver_completion': completion,
        'child_signals': 0, 'child_exit_code_inferred': False,
        'third_attempt_allowed': False, 'old_parent_not_resumed': True,
        'result_if_no_official_report': 'original consumed retry remains unresolved; never redispatch'})


def old_controller_stopped(plan):
    result = subprocess.run(['systemctl', '--user', 'show', OLD_UNIT,
        '--property=ActiveState,MainPID,ControlGroup'], capture_output=True, text=True,
        check=True, timeout=15)
    state = dict(x.split('=', 1) for x in result.stdout.splitlines() if '=' in x)
    if state.get('ActiveState') not in {'inactive', 'failed'} or state.get('MainPID') != '0':
        raise ValueError('Do not take over an active old watcher')
    original_intent = load(plan['parent_freeze_intent'])
    for key in ('parent_before', 'child_before'):
        expected = original_intent[key]
        if exact_process_alive(expected, process(expected['pid'])):
            raise ValueError('Original driver or scorer is still executing')
    group = Path('/sys/fs/cgroup' + original_intent['old_unit_state']['ControlGroup'])
    if group.exists() and 'populated 1' in (group / 'cgroup.events').read_text():
        raise ValueError('Old scoring unit descendants have not drained')
    return state


def disposition(item, root):
    folder = root / 'exceptions' / item['exception_id']
    if (folder / 'result.json').exists():
        return 'existing_result'
    if item['domain'] == 'scoring' and item['slot']['instance_id'] in HOLDS:
        return 'held_for_deterministic_failure_review'
    return 'original_processor'


def validate_result(item, result):
    if (result.get('exception_id') != item['exception_id']
            or result.get('slot_id') != item['slot']['slot_id']
            or result.get('domain') != item['domain']):
        raise ValueError('Endpoint result crosses the original inventory identity')
    return result


class CapacityWait(RuntimeError):
    pass


def waiting_lease(lease_function, *, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + 30
    while True:
        try:
            return lease_function()
        except BlockingIOError:
            if clock() >= deadline:
                raise CapacityWait('Original grader capacity remains busy; endpoint not consumed')
            sleep(0.25)


def run(plan_ref):
    plan = validate(plan_ref)
    quiet_ref = reference(OUT / 'natural-child-exit.json')
    quiet = load(quiet_ref)
    if quiet['plan'] != plan_ref or quiet['child_signals'] != 0:
        raise ValueError('Unbound original scorer completion observation')
    stopped = old_controller_stopped(plan)
    inventory = load(plan['inventory'])
    context = threading.local()
    original_lease = original.grader_lease
    original.grader_lease = lambda: waiting_lease(original_lease)

    def work(item):
        folder = OLD / 'exceptions' / item['exception_id']
        decision = disposition(item, OLD)
        if decision == 'held_for_deterministic_failure_review':
            return {'exception_id': item['exception_id'], 'slot_id': item['slot']['slot_id'],
                    'domain': item['domain'], 'endpoint': item.get('endpoint'), 'status': decision,
                    'reason': 'Four predeclared deterministic-failure holds; no new attempt',
                    'new_model_calls': 0, 'new_scoring_attempts': 0}
        # A previous r2 driver may have exited while its scorer retained both
        # inherited leases. Never invoke old code on that still-owned entry.
        if (folder / 'started.json').exists() and not (folder / 'result.json').exists():
            try:
                lease = original.lock_file(folder / 'attempt.lock')
                lease.close()
            except BlockingIOError:
                return {'exception_id': item['exception_id'], 'slot_id': item['slot']['slot_id'],
                        'domain': item['domain'], 'status': 'held_existing_attempt_still_owned', 'new_model_calls': 0}
        if not hasattr(context, 'datasets'):
            context.datasets = {}
        try:
            return validate_result(item, original.process_exception(item, OLD, datasets=context.datasets))
        except CapacityWait as error:
            return {'exception_id': item['exception_id'], 'slot_id': item['slot']['slot_id'],
                    'domain': item['domain'], 'status': 'held_grader_capacity', 'reason': str(error), 'new_model_calls': 0}

    try:
        with ExitStack() as locks:
            locks.enter_context(original.lock_file(OLD / 'watch.lock'))
            locks.enter_context(original.lock_file(OLD / 'driver.lock'))
            old_controller_stopped(plan)
            adoption = OUT / 'adoption.json'
            if not adoption.exists():
                write_new(adoption, {'version': VERSION, 'adopted_utc': now(), 'plan': plan_ref,
                    'old_controller': stopped, 'natural_child_exit': quiet_ref,
                    'original_watch_and_driver_locks_owned': True, 'new_model_calls': 0,
                    'old_watch_trigger_and_progress_preserved': True})
            elif load(reference(adoption))['plan'] != plan_ref:
                raise ValueError('Another parallel plan already owns this adoption')
            results = {}
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(work, item): item for item in inventory['exceptions']}
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        results[item['exception_id']] = future.result()
                    except Exception as error:
                        results[item['exception_id']] = {'exception_id': item['exception_id'],
                            'slot_id': item['slot']['slot_id'], 'domain': item['domain'],
                            'status': 'driver_observation_unknown', 'error': repr(error),
                            'automatic_replay': False, 'new_model_calls': 0}
                    ordered = [results[x['exception_id']] for x in inventory['exceptions'] if x['exception_id'] in results]
                    atomic_write(OUT / 'progress.json', json_bytes({'version': VERSION, 'plan': plan_ref,
                        'updated_utc': now(), 'processed': len(ordered), 'total': len(inventory['exceptions']),
                        'results': ordered, 'maximum_workers': 2, 'new_model_calls': 0}))
            ordered = [results[x['exception_id']] for x in inventory['exceptions']]
            atomic_write(OUT / 'summary.json', json_bytes({'version': VERSION,
                'status': 'parallel_pass_finished_with_preserved_unknowns_and_holds', 'plan': plan_ref,
                'inventory': plan['inventory'], 'completed_utc': now(), 'results': ordered,
                'original_primary_records_overwritten': False, 'original_watcher_progress_overwritten': False,
                'maximum_additional_scoring_attempts_per_endpoint': 1, 'maximum_workers': 2,
                'new_model_calls': 0, 'hidden_feedback_to_actor': False}))
            return reference(OUT / 'summary.json')
    finally:
        original.grader_lease = original_lease


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('freeze')
    for action in ('observe-child', 'run'):
        p = sub.add_parser(action)
        p.add_argument('--plan', type=Path, required=True)
        p.add_argument('--sha256', required=True)
    args = parser.parse_args()
    if args.action == 'freeze':
        result = freeze()
    else:
        ref = reference(args.plan)
        if ref['sha256'] != args.sha256:
            raise ValueError('Parallel scoring plan SHA differs')
        result = observe_child(ref) if args.action == 'observe-child' else run(ref)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
