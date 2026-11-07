"""Prepare and score the twenty-one original stopped candidates, with no API calls."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import threading
import time

from proworksim import software_benchmark_rescore_v145 as scoring
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT, RUN = scoring.ROOT, scoring.RUN
MODULE = 'proworksim.software_benchmark_rescore_v145'


def command(*args):
    return [str(ROOT/'.venv/bin/python'), '-B', str(ROOT/'tools/run_offline_scorer_v096.py'),
            '-m', MODULE, *map(str, args)]


def prepare():
    from proworksim import software_benchmark_stopped_recovery_v145 as recovery
    from proworksim import software_benchmark_recovered_validation_v145 as bounded
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN/'coordinator').mkdir(exist_ok=True)
    old = scoring.load(reference(scoring.previous.scope.PLAN_FILE))
    outcomes = scoring.load(reference(scoring.previous.scope.API_ROOT/'task-outcomes.json'))['rows']
    slots = {Path(r['generation_result']['path']).parent.name for r in outcomes
             if r['generation_status'] == 'technical_unknown'}
    if len(slots) != 21 or {int(s) for s in slots} != set(recovery.TASKS):
        raise ValueError('Only all twenty-one original unknowns are selected, before scores')
    rows = [r for r in old['rows'] if str(r['slot_index']) in slots]
    plan = {'version': scoring.VERSION, 'original_plan': reference(scoring.previous.scope.PLAN_FILE),
        'rows': [{**r, 'measurement_kind': recovery.ENDPOINT} for r in rows],
        'resources': {}, 'environments': {}, 'candidates': {}, 'qualifications': {},
        'constraints': scoring.CONSTRAINTS, 'new_model_calls': 0,
        'original_generation_unknown_preserved': True}
    qualified = scoring.load(reference(scoring.previous.scope.API_ROOT/'qualification-status.json'))['qualifications']
    for row in rows:
        index, task = row['slot_index'], row['instance_id']
        result_ref = reference(recovery.OUTPUT/str(index)/'recovery-result.json')
        bounded.validate_recovery_result_bounded(result_ref, row)
        result = scoring.load(result_ref)
        config = scoring.load(row['configuration'])
        key = 'stopped-score-'+str(index)
        plan['resources'][key] = {'role': 'score', 'slot_id': row['slot_id'], 'instance_id': task,
            'group_id': row['group_id'], 'organization_id': row['organization_id'],
            'image_id': config['scorer_request_base']['image']['image_id'], 'endpoint': recovery.ENDPOINT}
        plan['candidates'][str(index)] = {'result': result_ref, 'candidate_lock': result['candidate_lock']}
        plan['environments'][task] = old['environments'][task]
        q = qualified[task]
        plan['qualifications'][task] = q.get('qualification', q)
    # Requests refer to the plan, so request references live in a separate index.
    plan_ref = write_new(scoring.PLAN, plan)
    completed = subprocess.run(command('--manifest'), cwd=ROOT, env=scoring.base.clean_environment(),
        capture_output=True, text=True, timeout=120, check=True)
    manifest = json.loads(completed.stdout)
    manifest_ref = write_new(RUN/'coordinator/scorer-manifest.json', manifest)
    scorer = scoring.build_scorer(manifest_provider=lambda: manifest)
    scorer.environment.prepare()
    requests = []
    for row in plan['rows']:
        index, task = row['slot_index'], row['instance_id']
        job, key = plan['candidates'][str(index)], 'stopped-score-'+str(index)
        request = {'version': scoring.VERSION, 'resource_key': key, 'instance_id': task,
            'plan': plan_ref, 'configuration': row['configuration'], 'candidate_lock': job['candidate_lock'],
            'generation_result': job['result'], 'measurement_kind': recovery.ENDPOINT,
            'source_slot_id': row['source_slot_id'], 'slot_id': row['slot_id'],
            'group_id': row['group_id'], 'organization_id': row['organization_id'],
            'qualification': plan['qualifications'][task], 'limits': scorer.LIMITS,
            'scorer_manifest': manifest_ref, 'cpuset_cpus': None, 'directory': str(scoring.GRADING/key),
            'patch_kind': None, 'delivery_evidence': None, **scorer.environment.request_fields(task)}
        (scoring.GRADING/key).mkdir(parents=True, exist_ok=True)
        requests.append({'slot_index': index, 'group_id': row['group_id'], 'instance_id': task,
                         'request': write_new(scoring.GRADING/key/'request.json', request)})
    index_ref = write_new(RUN/'requests.json', {'version': scoring.VERSION, 'rows': requests})
    original_sources = reference(scoring.previous.scope.SOURCE_FILE)
    frozen = [reference(scoring.__file__), reference(__file__), reference(recovery.__file__),
              reference(bounded.__file__), original_sources]
    for ref in scoring.load(original_sources)['files']:
        scoring.checked(ref)
        if ref not in frozen:
            frozen.append(ref)
    source_ref = write_new(scoring.SOURCE, {'files': frozen, 'original_runtime_sources': original_sources})
    auth = write_new(scoring.AUTH, {'status': 'authorized_by_current_user_instructions',
        'plan': plan_ref, 'source_index': source_ref, 'constraints': scoring.CONSTRAINTS,
        'user_instruction': '处理相关问题，此外本问题经常出现，排查根本原因',
        'standing_permission': '实验测试相关的docker使用在不干扰服务器及其他用户的情况下可以使用，无需发起请求。',
        'scope': '21 unique stopped member_001 candidates; no generation or API charge; original records preserved'})
    return {'plan': plan_ref, 'requests': index_ref, 'authorization': auth}


def run():
    scoring.allowed()
    write_new(RUN/'started.json', {'unix': time.time(), 'pid': os.getpid(), 'new_model_calls': 0})
    requests = scoring.load(reference(RUN/'requests.json'))['rows']
    bound = scoring.policy()
    available = [0, 1]
    condition, tls = threading.Condition(), threading.Lock()
    outcomes, stop = [], threading.Event()

    def task(row):
        request = scoring.load(row['request'])
        key, folder = request['resource_key'], Path(request['directory'])
        is_tls = row['instance_id'] in scoring.previous.TLS_TASKS
        if is_tls:
            tls.acquire()
        lane = None
        claim = None
        try:
            with condition:
                while not available and not stop.is_set():
                    condition.wait(.5)
                if stop.is_set():
                    return {**row, 'status': 'not_started_shared_cleanup_failure'}
                lane = available.pop(0)
            deadline = time.monotonic()+600
            while True:
                try:
                    claim = bound.claim_resource(key, lane=lane)
                    break
                except scoring.dispatch.ResourceBusy:
                    if time.monotonic() > deadline or stop.wait(2):
                        return {**row, 'status': 'not_started_capacity'}
            write_new(folder/'capacity-claim.json', {'prepared_request': row['request'], 'claim': claim})
            with (folder/'stdout.log').open('xb') as stdout, (folder/'stderr.log').open('xb') as stderr:
                process = subprocess.Popen(command('--request', row['request']['path']), cwd=ROOT,
                    env=scoring.base.clean_environment(), stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
                try:
                    code = process.wait(timeout=2100)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    code = process.wait(timeout=240)
            quiet_path = folder/'quiescence.json'
            quiet = json.loads(quiet_path.read_bytes()) if quiet_path.exists() else {}
            cleanup = quiet.get('quiescent') is True and quiet.get('cleanup_errors') == []
            if not cleanup:
                stop.set()
            receipt_path = folder/'receipt.json'
            receipt = json.loads(receipt_path.read_bytes()) if receipt_path.exists() else {}
            valid = code == 0 and cleanup and receipt.get('status') == 'official_report'
            result = {**row, 'returncode': code, 'cleanup_proven': cleanup,
                'status': 'scored' if valid else 'technical_unknown',
                'resolved': receipt.get('resolved') if valid else None,
                'receipt': reference(receipt_path) if receipt_path.exists() else None,
                'original_generation_status': 'technical_unknown',
                'measurement_kind': 'recovered_stopped_code', 'new_model_calls': 0}
            write_new(folder/'completion.json', result)
            return result
        except Exception as error:
            if claim is not None:
                stop.set()  # Only unproven cleanup blocks new infrastructure work.
            return {**row, 'status': 'technical_unknown',
                    'error': {'type': type(error).__name__, 'message': str(error)}}
        finally:
            if lane is not None:
                with condition:
                    available.append(lane)
                    condition.notify_all()
            if is_tls:
                tls.release()

    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(task, row) for row in requests]):
            result = future.result()
            outcomes.append(result)
            atomic_write(RUN/'progress.json', json_bytes({'completed': len(outcomes), 'planned': len(requests),
                'outcomes': outcomes, 'shared_cleanup_stop': stop.is_set()}))
            print(json.dumps({k: result.get(k) for k in ('slot_index','status','resolved','error')}, ensure_ascii=False), flush=True)
    return write_new(RUN/'summary.json', {'version': scoring.VERSION, 'outcomes': outcomes,
        'finished_unix': time.time(), 'new_model_calls': 0, 'old_results_changed': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--run', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else run(), ensure_ascii=False))
