"""Prepare preserved candidates and a child-produced scorer manifest; no Docker."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
import os
from pathlib import Path
import subprocess

from proworksim import software_benchmark_rescore_v095 as scoring
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim import software_benchmark_dispatch_v066 as original
from proworksim import software_benchmark_api_scope_v094 as recovery


def module_command(*arguments):
    return [str(scoring.ROOT/'.venv/bin/python'), '-B', str(scoring.ROOT/'tools/run_offline_scorer_v058.py'),
            '-m', 'proworksim.software_benchmark_rescore_v095', *arguments]


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
        if not run_root.is_relative_to((scoring.ROOT/'runs/software-benchmark-v095').resolve()):
            raise PermissionError('Only a separately named v095 preparation root is allowed')
        scoring.RUN_ROOT = run_root
        scoring.PLAN_FILE = run_root/'plan.json'
        scoring.AUTH_FILE = scoring.ROOT/'config'/('v095-'+run_root.name+'-authorization.json')
        scoring.SOURCE_FILE = run_root/'runtime-sources.json'
    if scoring.PLAN_FILE.exists():
        raise ValueError('Core rescoring preparation is single use')
    summary_ref = reference(recovery.API_ROOT/'run-summary.json')
    summary = scoring.load(summary_ref)
    if len(summary['scores']) != 43:
        raise ValueError('The exact 43 failed score requests changed')
    entries = []
    for slot, value in summary['scores'].items():
        request = scoring.load(value['request'])
        old_folder = Path(request['directory'])
        quiet_ref = reference(old_folder/'quiescence.json')
        quiet = scoring.load(quiet_ref)
        if ((old_folder/'receipt.json').exists() or quiet.get('quiescent') is not True
                or quiet.get('cleanup_errors') or quiet.get('create_result_unknown')
                or quiet.get('owned_container_ids')):
            raise ValueError('Expected the preserved pre-Docker manifest rejection')
        entries.append(entry(value['request'], source_family='recovery_v094', cleanup=quiet_ref))
    historical_request = reference(original.GRADING_ROOT/'score-3536/request.json')
    inspection = reference(scoring.ROOT/'artifacts/software-benchmark-v095/original-score-cleanup-r1/score-3536-inspection.json')
    observed = scoring.load(inspection)
    claim = reference(original.BATCH_ROOT/'resource-claims/score-3536.json')
    released = reference(original.BATCH_ROOT/'resource-claims/score-3536.released.json')
    if observed.get('exact_container_not_found') is not True or scoring.load(released).get('claim') != claim:
        raise ValueError('Historical score3536 lacks exact no-live-object and capacity-release evidence')
    entries.append(entry(historical_request, source_family='original_v066', cleanup={
        'inspection': inspection, 'claim': claim, 'release': released, 'original_quiescence_missing': True}))
    recovered_root = scoring.ROOT/'runs/software-benchmark-v095/managed-terminal-recovery-r1/6068'
    recovered_ref = reference(recovered_root/'recovered-result.json')
    recovered = scoring.load(recovered_ref)
    audit_ref = reference(recovered_root/'administrative-closure-audit.json')
    audit = scoring.load(audit_ref)
    origin_plan = reference(recovery.PLAN_FILE)
    row = next(row for row in scoring.load(origin_plan)['rows'] if row['slot_index'] == 6068)
    qualification = scoring.load(reference(recovery.INVENTORY_FILE))['qualifications'][row['instance_id']]['qualification']
    lock = scoring.original_scorer._locked_candidate(recovered['candidate_lock'], scoring.load(row['configuration']), endpoint='terminal_code')
    if audit.get('candidate_lock') != recovered['candidate_lock'] or recovered.get('administrative_closure_audit') != audit_ref:
        raise ValueError('Only the exact recovered6068 terminal lock is admitted')
    entries.append({'slot_id': row['slot_id'], 'row': row, 'source_family': 'recovery_v094',
        'origin_request': None, 'origin_plan': origin_plan, 'generation_result': recovered_ref,
        'configuration': row['configuration'], 'candidate_lock': recovered['candidate_lock'],
        'qualification': qualification, 'patch': lock['patch_receipt']['patch'],
        'administrative_recovery_audit': audit_ref, 'prior_scoring_cleanup': None,
        'delivery_validation_at_generation': {'submitted': False, 'same_tree': False}})
    if len(entries) != 45 or len({value['slot_id'] for value in entries}) != 45:
        raise ValueError('The core list must remain exactly 45 distinct locked model attempts')
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
            key = ('score' if endpoint == 'code' else 'delivery-score')+f'-v095-core-{number:03d}'
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
        'constraints': constraints, 'scorer_manifest': manifest_ref, 'source_recovery_summary': summary_ref,
        'code_candidates': 45, 'delivery_slots_optional': len(jobs)-45, 'new_model_calls': 0,
        'candidate_selection_changed': False, 'original_records_overwritten': False,
        'held_historical_scores': [{'resource_key': 'score-1675', 'reason': 'offline_build_dependency_and_official_test_reset'},
                                  {'resource_key': 'score-5530', 'reason': 'official_test_patch_rename_reset_conflict'}],
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
    return {'plan': plan_ref, 'manifest': manifest_ref, 'code_candidates': 45,
        'optional_delivery_endpoints': len(jobs)-45, 'Docker_operations': 0, 'model_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', required=True, action='store_true')
    parser.add_argument('--run-root', type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.run_root), ensure_ascii=False))
