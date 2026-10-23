"""Four held Qwen endpoints: one independent r6 score, original grader leases.

Original r5 started identities are never fabricated. A separate transfer marker
and unresolved pointer reserve each endpoint for this finite independent pass.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from proworksim import software_benchmark_deferred_scoring_v054 as old  # noqa: E402
from proworksim import software_benchmark_scorer_r6_v055 as scorer  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new  # noqa: E402
from proworksim.storage import atomic_write, json_bytes  # noqa: E402

VERSION = 'v055-qwen-four-held-endpoint-r6-pass-r1'
OLD = ROOT / 'runs/software-benchmark-v054/deferred-scoring-r1'
OUT = ROOT / 'runs/software-benchmark-v055/exception-reconciliation-r1/qwen-four-endpoint-r6'
SCORER_REVISION = ROOT / 'runs/software-benchmark-v055/exception-reconciliation-r1/scorer-r6/revision.json'
TRANSPORT = ROOT / 'runs/software-benchmark-v055/exception-reconciliation-r1/patch-transport-r1/qwen-ref-matplotlib-26466/transport-receipt.json'
TARGETS = {'v054-' + arm + '-psf__requests-1142' for arm in ('REF', 'MATCH', 'PROJECT')}
TARGETS.add('v054-REF-matplotlib__matplotlib-26466')
CPUSETS = ('0-3', '4-7')


def now():
    return datetime.now(timezone.utc).isoformat()


def load(ref):
    return json.loads(checked(ref).read_bytes())


def revised_request(original, original_ref, execution_ref, cpuset, pointer, transport=None):
    if original.get('attempt', 1) != 1:
        raise ValueError('Only the first additional attempt is authorized')
    revised = dict(original, attempt=2, receipt_output=str(pointer),
        original_scoring_request=original_ref, scoring_execution_revision=execution_ref,
        scoring_cpuset_cpus=cpuset)
    if transport is not None:
        revised['patch_transport'] = transport
    return revised


def freeze():
    inventory_ref = reference(OLD / 'inventory.json')
    inventory = load(inventory_ref)
    items = [x for x in inventory['exceptions'] if x['domain'] == 'scoring' and x['slot']['slot_id'] in TARGETS]
    if len(items) != 4 or {x['slot']['slot_id'] for x in items} != TARGETS:
        raise ValueError('The original exact four held scoring endpoints are required')
    OUT.mkdir(parents=True, exist_ok=False)
    execution_ref = reference(SCORER_REVISION)
    transport_ref = reference(TRANSPORT)
    datasets, rows = {}, []
    for ordinal, item in enumerate(items):
        legacy = OLD / 'exceptions' / item['exception_id']
        if (legacy / 'started.json').exists() or (legacy / 'result.json').exists():
            raise ValueError('A held original endpoint was already entered or reassigned')
        folder = OUT / item['exception_id']
        folder.mkdir()
        original = load(item['original_request'])
        transport = transport_ref if item['slot']['instance_id'] == 'matplotlib__matplotlib-26466' else None
        request = revised_request(original, item['original_request'], execution_ref, CPUSETS[ordinal % 2],
                                  folder / 'official-pointer.json', transport)
        scorer.validate_request(request)
        patch, replacement = scorer.selected_patch(request, original)
        dataset_key = request['dataset']['sha256']
        if dataset_key not in datasets:
            datasets[dataset_key] = scorer.base.read_local_dataset(request['dataset'])
        instance = datasets[dataset_key][request['instance_id']]
        manifest = {'version': scorer.VERSION, 'parent_scorer_manifest': request['scorer_manifest'],
                    'adapter': reference(scorer.__file__), 'execution_revision': execution_ref}
        identity = scorer.execution_identity(request, instance, manifest, patch, replacement)
        run_id, output, pointer, identity_sha = scorer.output_paths(request, identity)
        if output.exists() or pointer.exists():
            raise ValueError('r6 candidate output already exists before its first intent')
        rows.append({'exception_id': item['exception_id'], 'slot': item['slot'], 'endpoint': item['endpoint'],
            'original_request': item['original_request'], 'legacy_folder': str(legacy), 'folder': str(folder),
            'worker_index': ordinal % 2, 'cpuset': CPUSETS[ordinal % 2],
            'request': write_new(folder / 'request.json', request),
            'expected_identity': write_new(folder / 'expected-identity.json', identity),
            'run_id': run_id, 'output': str(output), 'pointer': str(pointer), 'identity_sha256': identity_sha})
    result = write_new(OUT / 'plan.json', {'version': VERSION, 'created_utc': now(), 'source': reference(__file__),
        'original_inventory': inventory_ref, 'scorer_execution_revision': execution_ref,
        'rows': rows, 'maximum_parallel_graders': 2, 'cpu_sets': list(CPUSETS),
        'original_global_grader_locks': [str(old.QUEUE / 'locks' / f'grader-{i}.lock') for i in range(2)],
        'maximum_additional_attempts_per_endpoint': 1, 'original_r5_started_not_fabricated': True,
        'new_model_calls': 0, 'original_candidate_reselected': False})
    validate_plan(result)
    return result


def validate_plan(ref):
    plan = load(ref)
    if (plan.get('version') != VERSION or plan.get('source') != reference(__file__)
            or plan.get('maximum_parallel_graders') != 2 or plan.get('cpu_sets') != list(CPUSETS)
            or plan.get('maximum_additional_attempts_per_endpoint') != 1
            or plan.get('original_r5_started_not_fabricated') is not True
            or plan.get('new_model_calls') != 0 or plan.get('original_candidate_reselected') is not False
            or {x['slot']['slot_id'] for x in plan['rows']} != TARGETS or len(plan['rows']) != 4):
        raise ValueError('Unknown exact four-endpoint r6 scoring plan')
    load(plan['original_inventory'])
    load(plan['scorer_execution_revision'])
    for row in plan['rows']:
        request = load(row['request'])
        scorer.validate_request(request)
        if (request['scoring_execution_revision'] != plan['scorer_execution_revision']
                or request['original_scoring_request'] != row['original_request']
                or request['scoring_cpuset_cpus'] != row['cpuset']
                or row['cpuset'] != CPUSETS[row['worker_index']]
                or row['legacy_folder'] != str(OLD / 'exceptions' / row['exception_id'])
                or row['folder'] != str(OUT / row['exception_id'])):
            raise ValueError('Request escaped its original endpoint/capacity assignment')
        load(row['expected_identity'])
    return plan


def transfer_body(plan_ref, row):
    return {'version': VERSION, 'plan': plan_ref, 'exception_id': row['exception_id'],
            'slot_id': row['slot']['slot_id'], 'original_request': row['original_request'],
            'new_request': row['request'], 'original_attempt': 1, 'reserved_additional_attempt': 2,
            'original_r5_started_written': False, 'new_model_calls': 0}


def register_transfer(plan_ref, row):
    legacy, folder = Path(row['legacy_folder']), Path(row['folder'])
    legacy.mkdir(parents=True, exist_ok=True)
    with old.lock_file(legacy / 'attempt.lock'):
        if (legacy / 'started.json').exists():
            raise ValueError('Original r5 additional attempt already entered; no second execution revision')
        body = transfer_body(plan_ref, row)
        transfer = folder / 'transfer.json'
        if transfer.exists():
            transfer_ref = reference(transfer)
            if load(transfer_ref) != body:
                raise ValueError('Existing transfer belongs to another revision')
        else:
            if (legacy / 'result.json').exists():
                raise ValueError('Original endpoint already has an unrelated result')
            transfer_ref = write_new(transfer, body)
        marker = {'exception_id': row['exception_id'], 'slot_id': row['slot']['slot_id'],
            'domain': 'scoring', 'endpoint': row['endpoint'], 'status': 'unresolved',
            'reason': 'Reserved for independent r6 scoring; authoritative result is separate',
            'r6_transfer': transfer_ref, 'new_model_calls': 0, 'automatic_generation_retry': False,
            'original_r5_started_written': False}
        result = legacy / 'result.json'
        if result.exists():
            if json.loads(result.read_bytes()) != marker:
                raise ValueError('Existing original result differs from this exact transfer')
        else:
            write_new(result, marker)
        return transfer_ref


def receipt(row):
    pointer = Path(row['pointer'])
    if not pointer.exists():
        return None
    linked = json.loads(pointer.read_bytes())
    identity, report = load(linked['identity']), load(linked['receipt'])
    request = load(row['request'])
    if (identity != load(row['expected_identity']) or report.get('run_id') != row['run_id']
            or report.get('identity_sha256') != row['identity_sha256']
            or report.get('execution_revision') != request['scoring_execution_revision']
            or report.get('original_request') != row['original_request']
            or report.get('cpuset_cpus') != row['cpuset']
            or report.get('model_calls') != 0 or report.get('actor_feedback') is not False
            or report.get('preparation_only') is not False
            or (report.get('status') == 'official_report' and type(report.get('resolved')) is not bool)):
        raise ValueError('r6 receipt crosses locked endpoint/execution identity')
    return {'pointer': reference(pointer), **linked, 'run_id': report['run_id'],
            'status': report['status'], 'resolved': report.get('resolved')}


def scorer_argv(path):
    argv = old.scorer_argv(path)
    index = argv.index('proworksim.software_benchmark_scorer_r5_v054')
    argv[index] = 'proworksim.software_benchmark_scorer_r6_v055'
    return argv


def grader_lease():
    while True:
        try:
            return old.grader_lease()
        except BlockingIOError:
            time.sleep(0.5)


def process_row(plan_ref, row):
    folder, legacy = Path(row['folder']), Path(row['legacy_folder'])
    result_path = folder / 'result.json'
    if result_path.exists():
        result = json.loads(result_path.read_bytes())
        if result['plan'] != plan_ref or result['exception_id'] != row['exception_id']:
            raise ValueError('Another result owns this endpoint')
        return result
    result = {'version': VERSION, 'plan': plan_ref, 'exception_id': row['exception_id'],
        'slot_id': row['slot']['slot_id'], 'endpoint': row['endpoint'], 'status': 'technical_unknown',
        'new_model_calls': 0, 'automatic_retry': False, 'maximum_additional_attempts': 1}
    try:
        with old.lock_file(legacy / 'attempt.lock') as attempt:
            if (legacy / 'started.json').exists():
                raise ValueError('r5 consumed the additional attempt; r6 cannot run')
            if (folder / 'started.json').exists():
                recovered = receipt(row)
                result.update(official=recovered, additional_attempt_consumed=True,
                              reason='Prior r6 intent preserved; no automatic redispatch')
                if recovered and recovered['status'] == 'official_report':
                    result.update(status='official_report', resolved=recovered['resolved'])
            else:
                if Path(row['output']).exists() or Path(row['pointer']).exists():
                    raise ValueError('Unowned r6 output exists before permanent attempt intent')
                with grader_lease() as lease:
                    write_new(folder / 'started.json', {'version': VERSION, 'plan': plan_ref,
                        'request': row['request'], 'original_request': row['original_request'],
                        'run_id': row['run_id'], 'started_utc': now(), 'driver_pid': os.getpid(),
                        'attempt': 2, 'cpuset_cpus': row['cpuset'], 'original_grader_lease_owned': True,
                        'old_endpoint_attempt_lock_owned': True, 'new_model_calls': 0})
                    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src') + ':' + str(ROOT), PYTHONDONTWRITEBYTECODE='1')
                    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
                        env[key] = ''
                    with (folder / 'stdout.log').open('xb') as stdout, (folder / 'stderr.log').open('xb') as stderr:
                        child = subprocess.Popen(scorer_argv(row['request']['path']), cwd=ROOT, env=env,
                            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                            pass_fds=(lease.fileno(), attempt.fileno()))
                        write_new(folder / 'child.json', {'pid': child.pid, 'started_utc': now(),
                            'grader_and_endpoint_leases_inherited': True})
                        try:
                            code = child.wait(timeout=1920)
                        except subprocess.TimeoutExpired:
                            result.update(reason='Host scorer exceeded bounded observation; child and inherited locks retained',
                                          additional_attempt_consumed=True, child_pid=child.pid, child_killed=False)
                        else:
                            write_new(folder / 'completion.json', {'returncode': code, 'completed_utc': now(),
                                'request': row['request'], 'new_model_calls': 0})
                            recovered = receipt(row)
                            result.update(returncode=code, official=recovered, additional_attempt_consumed=True)
                            if code == 0 and recovered and recovered['status'] == 'official_report':
                                result.update(status='official_report', resolved=recovered['resolved'])
                            else:
                                result['reason'] = 'The single r6 additional attempt remains technical unknown; no third attempt'
    except BlockingIOError:
        # Do not finalize an entry while its already-started child owns the lock.
        return {**result, 'status': 'existing_attempt_still_owned', 'reason': 'No duplicate scorer started'}
    except Exception as error:
        result.update(reason='Independent r6 endpoint did not close safely', error={'type': type(error).__name__, 'message': str(error)},
                      additional_attempt_consumed=(folder / 'started.json').exists())
    result['finished_utc'] = now()
    write_new(result_path, result)
    return result


def run(plan_ref):
    plan = validate_plan(plan_ref)
    with ExitStack() as stack:
        stack.enter_context(old.lock_file(OUT / 'driver.lock'))
        for row in plan['rows']:
            register_transfer(plan_ref, row)
        write_path = OUT / 'adoption.json'
        if not write_path.exists():
            write_new(write_path, {'version': VERSION, 'plan': plan_ref, 'adopted_utc': now(),
                'original_r5_attempts_reserved_by_explicit_transfers': True,
                'maximum_parallel_graders_across_r2_and_r6': 2, 'new_model_calls': 0})
        def worker(index):
            return [process_row(plan_ref, row) for row in plan['rows'] if row['worker_index'] == index]
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker, index) for index in range(2)]
            results = [value for future in futures for value in future.result()]
        atomic_write(OUT / 'summary.json', json_bytes({'version': VERSION, 'plan': plan_ref,
            'finished_utc': now(), 'results': results, 'new_model_calls': 0,
            'original_primary_results_overwritten': False, 'maximum_additional_attempts_per_endpoint': 1,
            'GPU_models_released': False}))
        return reference(OUT / 'summary.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('freeze')
    p = sub.add_parser('run')
    p.add_argument('--plan', required=True, type=Path)
    p.add_argument('--sha256', required=True)
    args = parser.parse_args()
    if args.action == 'freeze':
        result = freeze()
    else:
        ref = reference(args.plan)
        if ref['sha256'] != args.sha256:
            raise ValueError('Four-endpoint plan SHA differs')
        result = run(ref)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
