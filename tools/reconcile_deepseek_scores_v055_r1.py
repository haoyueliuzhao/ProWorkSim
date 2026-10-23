"""Finite offline reconciliation of the original 47 DeepSeek scoring unknowns.

One additional r6 attempt per locked endpoint, four shared scoring slots, no
model replay. Original strict unknowns and official unresolved reports remain
immutable. The new score execution revision is reported separately.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time

from proworksim import software_benchmark_scorer_v054 as base
from proworksim import software_benchmark_scorer_v055 as parent
from proworksim import software_benchmark_scorer_r6_v055 as r6
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_deferred_scoring_v054 import existing_report
from proworksim.software_benchmark_network_v055 import host_capacity
from proworksim.storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/software-benchmark-v055/exception-reconciliation-r1/deepseek-scoring-r1'
INVENTORY = OUT / 'preflight-inventory.json'
QUEUE = ROOT / 'runs/software-benchmark-v055/queue-r1/state.json'
TRANSPORT = ROOT / 'runs/software-benchmark-v055/exception-reconciliation-r1/patch-transport-r1/manifest.json'
VERSION = 'v055-deepseek-same-candidate-score-reconciliation-r1'
TOOL = ROOT / 'tools/reconcile_deepseek_scores_v055_r1.py'
CONTROL = ROOT / 'tools/check_deepseek_score_reconciliation_v055_r1.py'
EXPECTED_LIMITS = r6.LIMITS
CPUSETS = ('8-11', '12-15', '16-19', '20-23')
WRITE_LOCK = threading.Lock()


def now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def load(ref):
    return json.loads(checked(ref).read_bytes())


def read(path):
    return json.loads(Path(path).read_bytes())


def retry_request(original, folder, original_ref, revision, lane, transport=None):
    if type(original.get('attempt', 1)) is not int or original.get('attempt', 1) != 1:
        raise ValueError('Only the first additional scoring attempt is authorized')
    if type(lane) is not int or lane not in range(4):
        raise ValueError('A fixed one-of-four lane is required')
    result = deepcopy(original)
    result.update(attempt=2, receipt_output=str(Path(folder) / 'retry-receipt-pointer.json'),
        original_scoring_request=original_ref, scoring_execution_revision=revision,
        scoring_cpuset_cpus=CPUSETS[lane])
    if transport is not None:
        result['patch_transport'] = transport
    if (not Path(result['receipt_output']).is_relative_to(OUT)
            or result['receipt_output'] == original['receipt_output']):
        raise ValueError('Only a new independent receipt pointer is allowed')
    return result


def validate_retry(original, revised, folder, item):
    expected = retry_request(original, folder, item['original_request'], item['execution_revision'],
        item['lane'], item.get('patch_transport'))
    if revised != expected:
        raise ValueError('The original scientific request or pinned execution metadata changed')


def frozen_primary():
    raw = QUEUE.read_bytes()
    state = json.loads(raw)
    if state.get('status') != 'primary_inventory_finished' or len(state['rows']) != 3000:
        raise ValueError('The original primary inventory must have ended')
    groups = Counter(row['slot']['condition_id'] for row in state['rows'])
    if (len(groups) != 6 or set(groups.values()) != {500}
            or len({row['slot']['slot_id'] for row in state['rows']}) != 3000
            or any(row['generation']['status'] not in {'closed', 'technical_unknown'} for row in state['rows'])
            or any(score['status'] not in {'official_report', 'technical_unknown'} for row in state['rows'] for score in row['scores'])):
        raise ValueError('Fixed denominators or ended primary work cannot be verified')
    return state, raw


def freeze():
    inventory = read(INVENTORY)
    state, raw = frozen_primary()
    state_ref = {'path': str(QUEUE), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    if inventory['primary_queue_state'] != state_ref:
        raise ValueError('The original audited primary snapshot changed')
    actual = {(row['slot']['slot_id'], score['request']['sha256']) for row in state['rows'] for score in row['scores']
        if score['status'] == 'technical_unknown'}
    declared = {(item['slot']['slot_id'], item['original_request']['sha256']) for item in inventory['items']}
    if actual != declared or len(actual) != 47:
        raise ValueError('Only the exact original 47 scoring endpoints may be reconciled')
    revision = reference(r6.REVISION_PATH)
    transport_ref = reference(TRANSPORT)
    transports = {}
    for ref in load(transport_ref)['receipts']:
        receipt = load(ref)
        key = receipt['original_request']['sha256']
        if key in transports:
            raise ValueError('Duplicate transport for one original scoring request')
        transports[key] = ref
    sources = [reference(path) for path in (TOOL, CONTROL, Path(base.__file__), Path(parent.__file__), Path(r6.__file__),
        ROOT / 'src/proworksim/software_benchmark_candidates_v054.py',
        ROOT / 'src/proworksim/software_benchmark_deferred_scoring_v054.py',
        ROOT / 'src/proworksim/software_benchmark_network_v055.py',
        ROOT / 'tools/run_benchmark_runtime_v054.sh')]
    items, datasets = [], {}
    for index, source in enumerate(inventory['items']):
        item = deepcopy(source)
        original = load(item['original_request'])
        completion = load(item['original_score']['completion'])
        if completion.get('status') != 'process_exited' or type(completion.get('returncode')) is not int:
            raise ValueError('Original scoring worker is not conclusively finished')
        transport = transports.get(item['original_request']['sha256'])
        if (transport is not None) != (item['category'] == 'non_utf8_patch'):
            raise ValueError('Transport eligibility must match the four audited UTF8 errors')
        folder = OUT / 'endpoints' / item['endpoint_id']
        lane = index % 4
        revised = retry_request(original, folder, item['original_request'], revision, lane, transport)
        r6.validate_request(revised)
        patch, replacement = r6.selected_patch(revised, original)
        dataset_key = original['dataset']['sha256']
        if dataset_key not in datasets:
            datasets[dataset_key] = base.read_local_dataset(original['dataset'])
        manifest = {'version': r6.VERSION, 'parent_scorer_manifest': original['scorer_manifest'],
            'adapter': reference(r6.__file__), 'execution_revision': revision}
        identity = r6.execution_identity(revised, datasets[dataset_key][original['instance_id']], manifest, patch, replacement)
        run_id, output, _, _ = r6.output_paths(revised, identity)
        if output.exists() or (folder / 'started.json').exists():
            raise ValueError('This additional attempt already has output or a permanent intent')
        old_identity = item.get('identity')
        old_run_id = None
        if old_identity is not None:
            old_value = load(old_identity)
            old_run_id, old_output, _ = parent.scoring_output_paths(original, base.sha256(base.canonical(old_value)))
            if Path(old_identity['path']) != old_output / 'identity.json':
                raise ValueError('Original identity reference differs from its original cache location')
        item.update(additional_attempt_authorized=True, lane=lane, execution_revision=revision,
            original_identity=old_identity, original_run_id=old_run_id, retry_request=revised,
            retry_identity=identity, retry_run_id=run_id, patch_transport=transport)
        items.append(item)
    return write_new(OUT / 'plan.json', {'version': VERSION, 'created_utc': now(), 'inventory': reference(INVENTORY),
        'primary_snapshot': write_new(OUT / 'primary-state-snapshot.json', raw), 'sources': sources, 'items': items,
        'execution_revision': revision, 'transport_manifest': transport_ref, 'cpusets': list(CPUSETS),
        'maximum_concurrent_deepseek_graders': 4, 'original_qwen_grader_capacity': 2,
        'combined_maximum_graders': 6, 'limits': EXPECTED_LIMITS,
        'shared_grader_locks': str(OUT / 'grader-slots'),
        'maximum_additional_attempts_per_endpoint': 1, 'new_model_calls': 0,
        'hidden_feedback_to_actor': False, 'old_state_overwritten': False,
        'original_official_and_strict_results_preserved_as_two_axes': True,
        'new_visible_cpu_limit': 4, 'official_harness_rules_changed': False})


def validate_plan(ref):
    plan = load(ref)
    if (plan.get('version') != VERSION or plan.get('limits') != EXPECTED_LIMITS
            or plan.get('maximum_concurrent_deepseek_graders') != 4 or plan.get('combined_maximum_graders') != 6
            or plan.get('maximum_additional_attempts_per_endpoint') != 1 or plan.get('new_model_calls') != 0
            or plan.get('hidden_feedback_to_actor') is not False or plan.get('old_state_overwritten') is not False
            or plan.get('official_harness_rules_changed') is not False or plan.get('new_visible_cpu_limit') != 4
            or plan.get('cpusets') != list(CPUSETS) or len(plan['items']) != 47
            or len({i['endpoint_id'] for i in plan['items']}) != 47):
        raise ValueError('Unknown scoring reconciliation plan')
    for source in plan['sources']:
        checked(source)
    checked(plan['inventory'])
    checked(plan['execution_revision'])
    return plan


def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open('a+b')
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        stream.close()
        raise
    return stream


def grader_slot(lane):
    if type(lane) is not int or lane not in range(4):
        raise ValueError('Exactly one fixed shared grader slot is required')
    return lock(OUT / 'grader-slots' / f'{lane}.lock')


def scorer_command(path):
    return [str(ROOT / 'tools/run_benchmark_runtime_v054.sh'), '--write-project', '/usr/bin/env',
        'PYTHONPATH=' + str(ROOT / 'src'), 'PYTHONDONTWRITEBYTECODE=1',
        'HF_HUB_OFFLINE=1', 'HF_DATASETS_OFFLINE=1', 'TRANSFORMERS_OFFLINE=1',
        'HTTP_PROXY=', 'HTTPS_PROXY=', 'ALL_PROXY=', 'http_proxy=', 'https_proxy=', 'all_proxy=',
        'NO_PROXY=*', 'no_proxy=*', 'CUDA_VISIBLE_DEVICES=', 'NVIDIA_VISIBLE_DEVICES=void',
        str(ROOT / 'runs/software-benchmark-v054/scorer-venv/bin/python'), '-B', '-m',
        'proworksim.software_benchmark_scorer_r6_v055', '--request', str(path)]


def initial_result(item, plan_ref):
    return {'version': VERSION, 'slot_id': item['slot']['slot_id'], 'endpoint': item['endpoint'],
        'category': item['category'], 'plan': plan_ref, 'original_request': item['original_request'],
        'status': 'preserved_technical_unknown', 'new_model_calls': 0, 'additional_attempts': 0,
        'original_strict_status_changed': False, 'execution_revision': item['execution_revision'],
        'saved_original_official_report': item.get('official_report'),
        'saved_original_official_report_value': item.get('official_report_value')}


def process_item(item, plan_ref, driver_lease):
    folder = OUT / 'endpoints' / item['endpoint_id']
    folder.mkdir(parents=True, exist_ok=True)
    result_path = folder / 'result.json'
    if result_path.exists():
        result = read(result_path)
        if result['plan'] != plan_ref or result['original_request'] != item['original_request']:
            raise ValueError('Saved result belongs to another reconciliation')
        return result
    result = initial_result(item, plan_ref)
    try:
        with lock(folder / 'attempt.lock') as endpoint_lease:
            original = load(item['original_request'])
            revised = item['retry_request']
            validate_retry(original, revised, folder, item)
            old_report = (existing_report(original, load(item['original_identity']), item['original_run_id'])
                if item['original_identity'] is not None else None)
            if old_report is not None:
                result.update(status='recovered_existing_official_report', official=old_report)
            else:
                new_report = existing_report(revised, item['retry_identity'], item['retry_run_id'])
                started = folder / 'started.json'
                if new_report is not None:
                    if not started.exists():
                        raise ValueError('Existing retry report lacks its authorized permanent intent')
                    result.update(status='recovered_additional_official_report', official=new_report, additional_attempts=1)
                elif started.exists():
                    result.update(reason='One additional attempt has an intent but no determinate report; never replay', additional_attempts=1)
                else:
                    if (Path(revised['trusted_output_root']) / item['retry_run_id']).exists():
                        raise ValueError('New scoring output exists outside this permanent intent')
                    capacity = host_capacity()
                    if not capacity['admit']:
                        return {**result, 'status': 'resource_wait', 'host_capacity': capacity}
                    with grader_slot(item['lane']) as lease:
                        # The child validates the original locked candidate and all
                        # pinned r6 inputs again before creating any container.
                        request_path = folder / 'request.json'
                        request_ref = reference(request_path) if request_path.exists() else write_new(request_path, revised)
                        if load(request_ref) != revised:
                            raise ValueError('Prepared retry request changed')
                        write_new(started, {'version': VERSION, 'created_utc': now(), 'plan': plan_ref,
                            'original_request': item['original_request'], 'retry_request': request_ref,
                            'old_run_id': item['original_run_id'], 'retry_run_id': item['retry_run_id'],
                            'limits': original['limits'], 'execution_revision': item['execution_revision'],
                            'cpuset_cpus': revised['scoring_cpuset_cpus'], 'shared_grader_slot': item['lane'],
                            'original_scientific_request_preserved': True, 'patch_transport': item.get('patch_transport'),
                            'new_model_calls': 0, 'maximum_additional_attempts': 1})
                        result['additional_attempts'] = 1
                        with (folder / 'stdout.log').open('xb') as stdout, (folder / 'stderr.log').open('xb') as stderr:
                            child = subprocess.Popen(scorer_command(request_path), cwd=ROOT, stdin=subprocess.DEVNULL,
                                stdout=stdout, stderr=stderr, pass_fds=(driver_lease.fileno(), endpoint_lease.fileno(), lease.fileno()))
                            write_new(folder / 'child.json', {'pid': child.pid, 'created_utc': now(),
                                'driver_endpoint_and_grader_leases_inherited': True, 'new_model_calls': 0})
                            returncode = child.wait()
                        write_new(folder / 'completion.json', {'returncode': returncode, 'finished_utc': now(),
                            'retry_request': request_ref, 'new_model_calls': 0})
                        new_report = existing_report(revised, item['retry_identity'], item['retry_run_id'])
                        result.update(returncode=returncode, retry_request=request_ref, retry_run_id=item['retry_run_id'])
                        if new_report is not None:
                            result.update(status='recovered_additional_official_report', official=new_report)
                        else:
                            result['reason'] = 'One r6 same-candidate scoring attempt still lacks a strict determinate report'
                        pointer = folder / 'retry-receipt-pointer.json'
                        if pointer.is_file():
                            result['new_receipt_pointer'] = reference(pointer)
    except BlockingIOError:
        return {**result, 'status': 'resource_wait', 'reason': 'Shared endpoint or four-grader capacity lease is occupied'}
    except Exception as error:
        result.update(reason='Scoring reconciliation could not safely complete', error={
            'type': type(error).__name__, 'message': str(error)}, no_automatic_replay=True,
            additional_attempts=int((folder / 'started.json').exists()))
    write_new(result_path, result)
    return result


def safe_process_item(item, plan_ref, lease):
    """Isolate every endpoint, including unexpected errors outside process_item."""
    try:
        return process_item(item, plan_ref, lease)
    except Exception as error:
        folder = OUT / 'endpoints' / item['endpoint_id']
        result = initial_result(item, plan_ref)
        result.update(reason='Unhandled endpoint error isolated from all other lanes', error={
            'type': type(error).__name__, 'message': str(error)}, no_automatic_replay=True,
            additional_attempts=int((folder / 'started.json').exists()))
        path = folder / 'driver-error.json'
        try:
            if not path.exists():
                write_new(path, result)
        except Exception as evidence_error:
            result['evidence_write_error'] = str(evidence_error)
        return result


def run(plan_ref, workers):
    if workers != 4:
        raise ValueError('This plan fixes four sequential lanes and four shared capacity locks')
    plan = validate_plan(plan_ref)
    with lock(OUT / 'driver.lock') as lease:
        results, waiting, lane_errors = {}, set(), []

        def lane_work(number):
            for item in (x for x in plan['items'] if x['lane'] == number):
                while True:
                    result = safe_process_item(item, plan_ref, lease)
                    with WRITE_LOCK:
                        if result['status'] == 'resource_wait':
                            waiting.add(item['endpoint_id'])
                        else:
                            waiting.discard(item['endpoint_id'])
                            results[item['endpoint_id']] = result
                        atomic_write(OUT / 'progress.json', json_bytes({'version': VERSION, 'updated_utc': now(),
                            'processed': len(results), 'planned_endpoints': len(plan['items']),
                            'resource_wait_count': len(waiting), 'results': list(results.values()), 'new_model_calls': 0}))
                    if result['status'] != 'resource_wait':
                        break
                    time.sleep(15)
            return number

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(lane_work, number): number for number in range(4)}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as error:
                    lane_errors.append({'lane': futures[future], 'type': type(error).__name__, 'message': str(error)})
        summary = {'version': VERSION, 'status': 'independent_scoring_pass_finished' if len(results) == 47 and not lane_errors
            else 'independent_scoring_pass_incomplete', 'completed_utc': now(), 'plan': plan_ref,
            'endpoint_count': len(results), 'planned_endpoint_count': 47, 'lane_errors': lane_errors,
            'status_counts': dict(Counter(x['status'] for x in results.values())), 'results': list(results.values()),
            'new_model_calls': 0, 'old_queue_records_modified': False,
            'technical_unknowns_not_automatically_mapped_to_model_failures': True,
            'additional_attempts': sum(x['additional_attempts'] for x in results.values())}
        return write_new(OUT / 'summary.json', summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    sub.add_parser('freeze')
    command = sub.add_parser('run')
    command.add_argument('--plan', required=True, type=Path)
    command.add_argument('--sha256', required=True)
    command.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.operation == 'freeze':
        value = freeze()
    else:
        ref = reference(args.plan)
        if ref['sha256'] != args.sha256:
            raise ValueError('Explicit scoring recovery plan SHA differs')
        value = run(ref, args.workers)
    print(json.dumps(value))


if __name__ == '__main__':
    main()
