"""Bounded asynchronous official rescoring; task failures stay in an exception set."""
from __future__ import annotations

import argparse
from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import importlib.util
import json
from pathlib import Path
import signal
import threading
import time

from proworksim import software_benchmark_rescore_v095 as scoring
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace
from proworksim.storage import atomic_write, json_bytes


def host(context, policy):
    spec = importlib.util.spec_from_file_location('v095_original_grade_owner',
        scoring.ROOT/'tools/run_capability_grading_v066.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    namespace = clone_namespace(module, policy=policy)

    def fixed_python(arguments):
        if arguments[:2] != ['-m', 'proworksim.software_benchmark_scorer_v066']:
            raise PermissionError('Only the bounded official scorer child is redirected')
        return module.fixed_python(['-m', 'proworksim.software_benchmark_rescore_v095', *arguments[2:]])

    namespace['fixed_python'] = fixed_python
    return type('BoundScoringHost', (), {key: staticmethod(value) for key, value in namespace.items()
                                       if key in ('run_request', 'trustworthy_cleanup')})()


def verified_official(context, job, request_ref):
    folder = context.grading_root/job['resource_key']
    if not (folder/'receipt.json').exists():
        return None
    receipt = scoring.load(reference(folder/'receipt.json'))
    if receipt.get('status') != 'official_report' or type(receipt.get('resolved')) is not bool:
        return None
    identity = scoring.load(receipt['identity'])
    quiet = scoring.load(reference(folder/'quiescence.json'))
    completion = scoring.load(reference(folder/'completion.json'))
    report = receipt['official_result'][1][job['row_instance_id']]
    if (identity.get('request') != request_ref or identity.get('candidate_lock') != job['candidate_lock']
            or identity.get('configuration') != job['configuration'] or identity.get('plan') != context.plan_ref
            or identity.get('scorer_manifest') != context.plan['scorer_manifest']
            or receipt.get('slot_id') != job['slot_id'] or receipt.get('resource_key') != job['resource_key']
            or report.get('resolved') is not receipt['resolved'] or report.get('patch_successfully_applied') is not True
            or report.get('infra_failure') or completion.get('returncode') != 0
            or quiet.get('quiescent') is not True or quiet.get('cleanup_errors')
            or quiet.get('create_result_unknown')):
        raise ValueError('Official result cannot be bound to this exact candidate and clean scoring run')
    return {'resolved': receipt['resolved'], 'receipt': reference(folder/'receipt.json'), 'identity': receipt['identity']}


def run(plan_file):
    context = scoring.Context(reference(plan_file))
    context.allowed()
    output = context.root/'coordinator'
    output.mkdir(exist_ok=True)
    if (output/'started.json').exists():
        raise PermissionError('The rescoring owner is single-use; do not restart consumed jobs')
    bound_policy = scoring.policy(context)
    owner = host(context, bound_policy)
    scorer = scoring.build_scorer(context, bound_policy)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    rows = {row['slot_id']: row for row in context.plan['rows']}
    all_jobs = [{**job, 'row_instance_id': rows[job['slot_id']]['instance_id'],
                 'arm': rows[job['slot_id']]['arm']} for job in context.jobs.values()]
    code_jobs = [job for job in all_jobs if job['endpoint'] == 'code']
    delivery_jobs = {job['slot_id']: job for job in all_jobs if job['endpoint'] == 'delivery'}
    first = [next(job for job in code_jobs if job['arm'] == arm and not job.get('administrative_recovery_audit'))
             for arm in ('REF', 'PROJECT')]
    selected = {job['resource_key'] for job in first}
    pending = deque(first+[job for job in code_jobs if job['resource_key'] not in selected])
    active, completed, healthy, failure_messages = {}, {}, set(), Counter()
    shared_failure = None

    def event(kind, **values):
        with (output/'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'unix': time.time(), 'kind': kind, **values}, ensure_ascii=False)+'\n')

    def one(job):
        request_ref = reference(context.grading_root/job['resource_key']/'request.json')
        completion = owner.run_request(request_ref, stop_event=stop)
        quiet = owner.trustworthy_cleanup(request_ref)
        known = verified_official(context, job, request_ref) if quiet else None
        result = {'resource_key': job['resource_key'], 'slot_id': job['slot_id'], 'arm': job['arm'],
            'status': 'official_report' if known else 'score_unknown', 'official': known,
            'completion': completion, 'cleanup_proven': quiet, 'delivery': None}
        if job['arm'] == 'PROJECT' and quiet:
            try:
                generation = scoring.load(job['generation_result'])
                if job.get('administrative_recovery_audit'):
                    audit = scoring.load(job['administrative_recovery_audit'])
                    if audit.get('submitted') is not False or generation.get('delivery_candidate_lock') is not None:
                        raise ValueError('Recovered code artifact cannot invent a legal delivery')
                    result['delivery'] = {'status': 'no_legal_delivery', 'resolved': False}
                else:
                    config = scoring.load(job['configuration'])
                    folder = scoring.original_policy.BATCH_ROOT/'episodes'/str(rows[job['slot_id']]['slot_index'])
                    proof = scorer.validate_project_delivery(generation, config, folder)
                    if not proof['submitted']:
                        result['delivery'] = {'status': 'no_legal_delivery', 'resolved': False, 'proof': proof}
                    elif proof['same_tree']:
                        code_lock = scoring.load(generation['candidate_lock'])
                        delivery_lock = scoring.load(generation['delivery_candidate_lock'])
                        if (code_lock['tree_sha256'] != delivery_lock['tree_sha256']
                                or code_lock['patch_receipt']['base_tree_sha256'] != delivery_lock['patch_receipt']['base_tree_sha256']):
                            raise ValueError('Same-tree delivery cannot reuse another version')
                        result['delivery'] = {'status': 'same_tree_official_result_reused' if known else 'score_unknown',
                            'resolved': known['resolved'] if known else None, 'code_score': known, 'proof': proof,
                            'code_candidate_lock': generation['candidate_lock'],
                            'delivery_candidate_lock': generation['delivery_candidate_lock'], 'new_containers': 0}
                    else:
                        separate = delivery_jobs[job['slot_id']]
                        separate_ref = reference(context.grading_root/separate['resource_key']/'request.json')
                        owner.run_request(separate_ref, stop_event=stop)
                        actual = verified_official(context, separate, separate_ref)
                        result['delivery'] = {'status': 'official_report' if actual else 'score_unknown', 'official': actual}
            except Exception as error:
                result['delivery'] = {'status': 'technical_unknown', 'error': {'type': type(error).__name__, 'message': str(error)}}
        if known is None:
            stderr = context.grading_root/job['resource_key']/'stderr.log'
            lines = stderr.read_text(errors='replace').strip().splitlines() if stderr.exists() else []
            result['pretest_failure'] = not (context.grading_root/job['resource_key']/'official-output/identity.json').exists()
            result['last_error'] = lines[-1] if lines else None
        return result

    write_new(output/'started.json', {'version': scoring.VERSION, 'plan': context.plan_ref,
        'unix': time.time(), 'new_model_calls': 0, 'initial_parallelism': 2, 'maximum_parallelism': 4})
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix='v095-official-score') as executor:
        while pending or active:
            limit = 4 if healthy == {'REF', 'PROJECT'} else 2
            while pending and len(active) < limit and not stop.is_set():
                job = pending.popleft()
                active[executor.submit(one, job)] = job
                event('scoring_started', resource_key=job['resource_key'], arm=job['arm'])
            if not active:
                break
            done, _ = wait(active, timeout=1, return_when=FIRST_COMPLETED)
            for future in done:
                job = active.pop(future)
                try:
                    value = future.result()
                except Exception as error:
                    value = {'resource_key': job['resource_key'], 'slot_id': job['slot_id'], 'arm': job['arm'],
                        'status': 'score_unknown', 'error': {'type': type(error).__name__, 'message': str(error)},
                        'pretest_failure': not (context.grading_root/job['resource_key']/'official-output/identity.json').exists(),
                        'last_error': type(error).__name__+': '+str(error)}
                completed[job['resource_key']] = value
                if value['status'] == 'official_report':
                    healthy.add(job['arm'])
                if value.get('cleanup_proven') is False:
                    shared_failure = 'unproven_owned_scoring_cleanup'
                error = value.get('last_error')
                if value.get('pretest_failure') and error:
                    failure_messages[error] += 1
                    if 'Capability scorer changed after freezing' in error or failure_messages[error] >= 2:
                        shared_failure = error
                if shared_failure:
                    stop.set()
                write_new(output/(job['resource_key']+'.json'), value)
                event('scoring_finished', resource_key=job['resource_key'], status=value['status'])
            atomic_write(output/'progress.json', json_bytes({'version': scoring.VERSION, 'unix': time.time(),
                'planned_code_candidates': len(code_jobs), 'completed': len(completed), 'pending': len(pending),
                'actual_active_graders': len(active), 'effective_limit': 4 if healthy == {'REF', 'PROJECT'} else 2,
                'confirmed_interfaces': sorted(healthy), 'health_uses_score_value': False,
                'shared_failure': shared_failure, 'status_counts': dict(Counter(x['status'] for x in completed.values()))}))
    summary = {'version': scoring.VERSION, 'finished_unix': time.time(), 'plan': context.plan_ref,
        'results': completed, 'not_started': [job['resource_key'] for job in pending],
        'shared_failure': shared_failure, 'confirmed_interfaces': sorted(healthy),
        'new_model_calls': 0, 'old_records_overwritten': False}
    write_new(output/'run-summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=scoring.PLAN_FILE)
    parser.add_argument('--execute', required=True, action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.plan), ensure_ascii=False))
