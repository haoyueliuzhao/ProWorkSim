"""Prepare preserved candidates and a child-produced scorer manifest; no Docker."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
import os
from pathlib import Path
import subprocess

from proworksim import software_benchmark_recovered_scores_v098 as scoring
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim import software_benchmark_dispatch_v066 as original


def module_command(*arguments):
    return [str(scoring.ROOT/'.venv/bin/python'), '-B', str(scoring.ROOT/'tools/run_offline_scorer_v058.py'),
            '-m', 'proworksim.software_benchmark_recovered_scores_v098', *arguments]


def child_manifest():
    environment = {key: value for key, value in os.environ.items()
        if key not in {'PYTHONHOME', 'PYTHONPATH', 'PYTHONEXECUTABLE', 'LD_LIBRARY_PATH', 'LD_PRELOAD'}}
    result = subprocess.run(module_command('--manifest'), env=environment,
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError('Isolated scorer manifest failed: '+result.stderr[-2000:])
    return json.loads(result.stdout)


def entry(request_ref, *, source_family, cleanup=None):
    request = scoring.load(request_ref)
    source_plan = scoring.load(request['plan'])
    row = next(row for row in source_plan['rows'] if row['slot_id'] == request['slot_id'])
    result = scoring.load(request['generation_result'])
    quiet = scoring.load(result['quiescence'])
    if (result.get('status') != 'closed' or quiet.get('quiescent') is not True
            or quiet.get('cleanup_errors') or quiet.get('create_result_unknown')):
        raise ValueError('Only preserved, closed and quiet generation candidates may enter')
    original_scorer = scoring.original_scorer
    lock = original_scorer._locked_candidate(request['candidate_lock'], scoring.load(row['configuration']), endpoint='terminal_code')
    return {'slot_id': row['slot_id'], 'row': row, 'source_family': source_family,
        'origin_request': request_ref, 'origin_plan': request['plan'], 'generation_result': request['generation_result'],
        'configuration': row['configuration'], 'candidate_lock': request['candidate_lock'],
        'qualification': request['qualification'], 'patch': lock['patch_receipt']['patch'],
        'administrative_recovery_audit': None, 'prior_scoring_cleanup': cleanup,
        'delivery_validation_at_generation': result.get('delivery_validation')}


def prepare(run_root=None):
    if run_root is not None:
        run_root = Path(run_root).resolve()
        if not run_root.is_relative_to((scoring.ROOT/'runs/software-benchmark-v098').resolve()):
            raise PermissionError('Only a separately named v098 preparation root is allowed')
        scoring.RUN_ROOT = run_root
        scoring.PLAN_FILE = run_root/'plan.json'
        scoring.AUTH_FILE = scoring.ROOT/'config'/('v098-'+run_root.name+'-authorization.json')
        scoring.SOURCE_FILE = run_root/'runtime-sources.json'
    if scoring.PLAN_FILE.exists():
        raise ValueError('Core rescoring preparation is single use')
    summary_ref = reference(scoring.READY_FILE)
    ready = scoring.load(summary_ref)
    origin_plan = reference(original.PLAN_FILE)
    origin = scoring.load(origin_plan)
    entries = []
    for item in ready['rows']:
        if item['slot_index'] == 6068:
            continue
        row = next(r for r in origin['rows'] if r['slot_index'] == item['slot_index'])
        result = scoring.load(item['recovered_result'])
        config = scoring.load(row['configuration'])
        lock = scoring.original_scorer._locked_candidate(result['candidate_lock'], config, endpoint='terminal_code')
        qualification = reference(original.COORDINATOR_RUN_ROOT/'qualifications'/(row['instance_id']+'.json'))
        entries.append({'slot_id': row['slot_id'], 'row': row, 'source_family': 'original_v066',
            'origin_request': None, 'origin_plan': origin_plan, 'generation_result': item['recovered_result'],
            'configuration': row['configuration'], 'candidate_lock': result['candidate_lock'],
            'qualification': qualification, 'patch': lock['patch_receipt']['patch'],
            'administrative_recovery_audit': result['administrative_closure_audit'],
            'prior_scoring_cleanup': None, 'delivery_validation_at_generation': result.get('delivery_validation')})
    if len(entries) != 25 or len({x['slot_id'] for x in entries}) != 25:
        raise ValueError('The separately frozen second batch is exactly 25 distinct original candidates')
    scoring.RUN_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_ref = write_new(scoring.RUN_ROOT/'scorer-manifest.json', child_manifest())
    jobs, resources, rows, environments = [], {}, [], {}
    for number, item in enumerate(entries, 1):
        row = item['row']
        rows.append(row)
        source_plan = scoring.load(item['origin_plan'])
        environment = source_plan['environments'][row['instance_id']]
        environments.setdefault(row['instance_id'], environment)
        result = scoring.load(item['generation_result'])
        endpoints = [('code', item['candidate_lock'])]
        if row['arm'] == 'PROJECT' and result.get('delivery_candidate_lock') is not None:
            endpoints.append(('delivery', result['delivery_candidate_lock']))
        for endpoint, lock_ref in endpoints:
            key = ('score' if endpoint == 'code' else 'delivery-score')+f'-v098-recovered-{number:03d}'
            job = {key_: copy.deepcopy(value) for key_, value in item.items() if key_ != 'row'}
            job.update(resource_key=key, endpoint=endpoint, candidate_lock=lock_ref,
                delivery_evidence=result.get('delivery_evidence') if endpoint == 'delivery' else None)
            jobs.append(job)
            resources[key] = {'role': 'score' if endpoint == 'code' else 'delivery_score',
                'slot_id': row['slot_id'], 'instance_id': row['instance_id'],
                'image_id': environment['image_id'], 'endpoint': endpoint}
    ancestor = scoring.load(reference(original.PLAN_FILE))
    constraints = {**original.CONSTRAINTS, 'maximum_containers': len(jobs),
        'maximum_named_volumes': 0, 'maximum_model_residents': 0,
        'maximum_actor_containers': 0, 'maximum_controller_containers': 0,
        'maximum_active_containers': 4}
    value = {**ancestor, 'version': scoring.VERSION, 'administrative_root': str(scoring.RUN_ROOT),
        'authorization_path': str(scoring.AUTH_FILE), 'source_index_path': str(scoring.SOURCE_FILE),
        'rows': rows, 'jobs': jobs, 'resources': resources, 'environments': environments,
        'resource_role_counts': dict(Counter(item['role'] for item in resources.values())),
        'constraints': constraints, 'scorer_manifest': manifest_ref, 'candidate_recovery_index': summary_ref,
        'code_candidates': 25, 'delivery_slots_optional': len(jobs)-25, 'new_model_calls': 0,
        'candidate_selection_changed': False, 'original_records_overwritten': False,
        'score_child_max_concurrent': 4, 'host_child_address_space_bytes': scoring.HOST_MEMORY_BYTES,
        'startup_health_gate': 'one REF and one PROJECT official_report with boolean resolved; score value not used'}
    plan_ref = write_new(scoring.PLAN_FILE, value)
    for job in jobs:
        folder = scoring.RUN_ROOT/'grading'/job['resource_key']
        folder.mkdir(parents=True)
        row = next(row for row in rows if row['slot_id'] == job['slot_id'])
        request = {'version': scoring.original_scorer.VERSION, 'resource_key': job['resource_key'],
            'slot_id': job['slot_id'], 'instance_id': row['instance_id'], 'source_slot_id': row['source_slot_id'],
            'measurement_kind': row['measurement_kind'], 'configuration': job['configuration'],
            'generation_result': job['generation_result'], 'candidate_lock': job['candidate_lock'],
            'qualification': job['qualification'], 'plan': plan_ref, 'scorer_manifest': manifest_ref,
            'directory': str(folder), 'limits': scoring.original_scorer.LIMITS, 'cpuset_cpus': None,
            'patch_kind': None, 'delivery_evidence': job['delivery_evidence'],
            **scoring.original_scorer.environment.request_fields(row['instance_id'])}
        if request['environment_revision'] is not None:
            raise PermissionError('Requests transport extensions require a separately reviewed scope')
        write_new(folder/'request.json', request)
    return {'plan': plan_ref, 'manifest': manifest_ref, 'code_candidates': 25,
        'optional_delivery_endpoints': len(jobs)-25, 'Docker_operations': 0, 'model_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', required=True, action='store_true')
    parser.add_argument('--run-root', type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.run_root), ensure_ascii=False))
