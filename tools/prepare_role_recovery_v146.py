"""Prepare or seal the authorized independent recovery; no runtime side effects."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
import os

from proworksim import software_benchmark_scope_v146 as scope
from proworksim import software_benchmark_scope_v143 as old
from proworksim.software_benchmark_candidates_v054 import reference, checked


def prepare():
    if os.getuid() == 0 or scope.SOURCE_FILE.exists() or scope.AUTH_FILE.exists():
        raise PermissionError('Only an unsealed ordinary-user preparation may be written')
    previous = old.load(reference(old.PLAN_FILE))
    outcomes_ref = reference(old.API_ROOT/'task-outcomes.json')
    outcomes = old.load(outcomes_ref)['rows']
    unknown = {r['slot_id']:r for r in outcomes if r['generation_status']=='technical_unknown'}
    originals = [r for r in previous['rows'] if r['slot_id'] in unknown]
    if len(originals) != 21:
        raise ValueError('The approved21 source unknown attempts changed')
    rows, resources, environments = [], {}, {}
    for attempt in (1,2):
        for i, original in enumerate(originals):
            index = 10200+i+21*(attempt-1)
            row = {**original, 'logical_index':len(rows), 'slot_index':index,
                'slot_id':f"v146:{original['slot_id']}:attempt{attempt}",
                'original_slot_id':original['slot_id'], 'recovery_of_slot_id':original['slot_id'],
                'original_slot_index':original['slot_index'], 'recovery_task_index':i,
                'recovery_round':attempt, 'recovery_attempt':attempt,
                'retry_of_slot_id':f"v146:{original['slot_id']}:attempt1" if attempt==2 else None,
                'original_generation_result':unknown[original['slot_id']]['generation_result'],
                'analysis_endpoint':'independent_api_recovery_v146', 'independent_initial_state':True,
                'automatic_original_replay':False,
                'conditional_after_first_round_transient_failure':attempt==2}
            config = copy.deepcopy(old.load(original['configuration']))
            config.update({key:value for key,value in row.items() if key != 'configuration'})
            config['version'] = 'v146-independent-role-recovery-config-r1'
            config['original_configuration'] = original['configuration']
            row['configuration'] = scope.retain(scope.BATCH_ROOT/'configs'/f'{index}.json',config)
            scope.validate_plan_identity(row)
            rows.append(row)
            for prefix in ('actor','controller','volume','score','delivery-score'):
                prior = previous['resources'][f"{prefix}-{original['slot_index']}"]
                base = {**prior,'slot_id':row['slot_id'],'recovery_round':attempt,
                    'original_slot_id':original['slot_id'],'original_resource_key':f"{prefix}-{original['slot_index']}"}
                resources[f'{prefix}-{index}'] = {**base, 'score_retry':False}
                if prefix in ('score','delivery-score'):
                    resources[f'{prefix}-retry-{index}'] = {**base,'score_retry':True,
                        'retry_of_resource_key':f'{prefix}-{index}', 'same_locked_candidate_required':True}
            task = row['instance_id']
            environments.setdefault(task, {**previous['environments'][task],'configuration':row['configuration']})
    task_ids = list(environments)
    panel = scope.retain(scope.PANEL_FILE, {'version':scope.VERSION,'rows':rows,'task_ids':task_ids,
        'distinct_tasks':len(task_ids),'planned_first_recovery_attempts':21,'conditional_second_attempts':21,
        'source_plan':reference(old.PLAN_FILE),'source_outcomes':outcomes_ref,
        'normal_model_failures_are_not_resampled':True,'original_results_preserved':True,
        'whole_team_token_budget':5_000_000,'new_token_upper_bound':210_000_000,
        'cumulative_cash_cap_CNY':scope.ORIGINAL_TOTAL_CAP_CNY,
        'new_subledger_cap_CNY':scope.CASH_CAP_CNY,'cash_authority':reference(scope.BUDGET_BASELINE_FILE)})
    inventory = scope.retain(scope.INVENTORY_FILE, {'version':scope.VERSION,
        'allowed_generation_slot_ids':[r['slot_id'] for r in rows],
        'first_round_slot_ids':[r['slot_id'] for r in rows if r['recovery_round']==1],
        'conditional_second_slot_ids':[r['slot_id'] for r in rows if r['recovery_round']==2],
        'original_generation_results':[unknown[r['slot_id']]['generation_result'] for r in originals],
        'new_diagnostic_calls':0,'new_environment_control_calls':0})
    plan = {'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'deployment_root':str(scope.BATCH_ROOT),
        'panel':panel,'matrix':panel,'rows':rows,'generation_rows':rows,'host_cpu_pool':reference(scope.CPU_POOL_FILE),
        'inventory':inventory,'constraints':scope.CONSTRAINTS,'environments':environments,
        'environment_sources':previous.get('environment_sources',{}),'resources':resources,
        'resource_role_counts':dict(Counter(r['role'] for r in resources.values())),
        'diagnostics':[],'training':False,'old_results_preserved':True,'new_runtime_scope':True,
        'model_calls_during_preparation':0,'previous_plan':reference(old.PLAN_FILE),
        'new_initial_attempts':21,'conditional_recovery_attempts':21,
        'automatic_second_attempt_only_after_transient_failure':True,
        'dispatch_admission':previous.get('dispatch_admission',{})}
    plan_ref = scope.retain(scope.PLAN_FILE,plan)
    scope.validate_plan(plan)
    qualifications = old.load(reference(old.API_ROOT/'qualification-status.json'))['qualifications']
    selected = {task:qualifications[task] for task in task_ids}
    scope.retain(scope.API_ROOT/'qualification-status.json', {'version':scope.VERSION,
        'qualifications':selected,'control_completions':{},'original_qualification_status':reference(old.API_ROOT/'qualification-status.json'),
        'new_control_containers':0,'original_images_tests_and_scoring_environment_unchanged':True})
    scope.retain(scope.PREPARATION_QUALIFICATION_FILE, {'version':scope.VERSION,'passed':True,
        'original_preparation':reference(old.PREPARATION_QUALIFICATION_FILE),
        'new_diagnostics':0,'new_API_calls':0,'unchanged_actor_and_public_tests':True,
        'new_host_identity_and_api_transport_require_separate_CPU_controls':True})
    scope.retain(scope.PRIOR_COMPLETION_FILE, {'version':scope.VERSION,
        'original_coordinator_finalization':reference(old.API_ROOT/'coordinator-finalization.json'),
        'original_run_summary':reference(old.API_ROOT/'run-summary.json'),
        'original120_attempts_have_terminal_records':True,'new_run_does_not_resume_or_overwrite_originals':True})
    scope.retain(scope.USER_GRANT_FILE, {'version':scope.VERSION,'record_kind':'derived_authorization_summary',
        'status':'authorized_by_user_instruction','verbatim_user_quote':False,
        'basis':'User requested actual tests and a recovery/retest queue for network failures, and explicitly raised the cumulative API cap to CNY450.',
        'maximum_first_independent_attempts':21,'maximum_conditional_second_attempts':21,
        'second_attempt_only_for_first_round_transient_technical_failure':True,
        'same_candidate_scoring_retry_maximum':1,'normal_model_failure_retries':0,
        'cash_authority':reference(scope.BUDGET_BASELINE_FILE),
        'budget_amendment':reference(scope.BUDGET_BASELINE_FILE.with_name('user-budget-amendment.json')),
        'standing_experimental_docker_permission':reference(scope.STANDING_POLICY_FILE),
        'maximum_containers':252,'maximum_named_volumes':42,
        'shared_host_configuration_changes':0,'other_root_operations_authorized':False})
    return {'plan':plan_ref,'panel':panel,'inventory':inventory,'runtime_started':False}


def seal():
    if os.getuid()==0 or scope.SOURCE_FILE.exists() or scope.AUTH_FILE.exists():
        raise PermissionError('An entered or sealed recovery cannot be resealed')
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    file = scope.ROOT/'tools/seal_role_pilot_v143.py'
    spec = importlib.util.spec_from_file_location('role_recovery_source_closure',file)
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    roots = [p for folder in ('src/proworksim','tools') for p in (scope.ROOT/folder).glob('*v146.py')]
    files = loader.source_closure(roots=roots)
    files += [reference(p) for p in (scope.PLAN_FILE,scope.PANEL_FILE,scope.INVENTORY_FILE,
        scope.CPU_POOL_FILE,scope.USER_GRANT_FILE,scope.PRIOR_COMPLETION_FILE,scope.BUDGET_BASELINE_FILE,
        scope.PREPARATION_QUALIFICATION_FILE,scope.API_ROOT/'qualification-status.json')]
    files += [row['configuration'] for row in plan['rows']]
    schemas = reference(scope.API_ROOT/'api-runtime/member-tool-schemas-r1.json')
    schema_value = scope.load(schemas)
    bundle = reference(scope.ROOT/'runs/software-benchmark-v146/sdk-bundle-r1/manifest.json')
    bundle_value = scope.load(bundle)
    controls = reference(scope.ROOT/'artifacts/software-benchmark-v146/cpu-controls-r1/summary.json')
    actual_inventory = schema_value['original_actual_member_inventory']
    inventory_schemas = scope.load(actual_inventory)['schemas']
    actual_schema_sha = hashlib.sha256(json.dumps(inventory_schemas, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()
    if (scope.load(controls).get('passed') is not True
            or bundle_value['probe'].get('member_schema_sha256') != actual_schema_sha
            or schema_value.get('schemas') != {g:inventory_schemas[g] for g in scope.GROUP_IDS}):
        raise ValueError('Actual runtime schemas and necessary CPU controls must be complete before sealing')
    cold_manifest = reference(scope.COORDINATOR_ROOT/'scorer-manifest.json')
    qualification_files = [reference(scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'))
                           for task in plan['environments']]
    files += [schemas, actual_inventory, bundle, controls,
              cold_manifest, *qualification_files]
    from proworksim.software_benchmark_archive_storage_v064 import stream_reference
    archive = bundle_value['archive']
    if stream_reference(archive['path']) != archive:
        raise ValueError('The concrete prepared controller bundle archive changed')
    payloads = {'runtime_bundle_manifest':bundle,'runtime_bundle_archive':archive,
        'validated_at_seal':True,'large_payload_checked_again_before_owned_upload':True,
        'large_payload_not_rehashed_for_each_API_call':True}
    files=list({r['path']:r for r in files}.values())
    for ref in files:
        checked(ref)
    sources=scope.retain(scope.SOURCE_FILE,{'version':scope.VERSION,'files':files,
        'runtime_data_excluded_from_static_source_index':True,'old_frozen_sources_modified':False,
        'payloads':payloads,'cpu_controls':controls,'cold_scorer_manifest':cold_manifest})
    auth=scope.retain(scope.AUTH_FILE,{'version':scope.VERSION,'status':'authorized_by_user_instruction',
        'plan':reference(scope.PLAN_FILE),'source_index':sources,'user_grant':reference(scope.USER_GRANT_FILE),
        'cash_authority':reference(scope.BUDGET_BASELINE_FILE),'API_cash_cap_CNY':scope.CASH_CAP_CNY,
        'original_cumulative_cash_cap_CNY':scope.ORIGINAL_TOTAL_CAP_CNY,
        'ledger_paths':{g:str(p) for g,p in scope.LEDGER_FILES.items()},'constraints':scope.CONSTRAINTS,
        'payloads':payloads,'cpu_controls':controls,'cold_scorer_manifest':cold_manifest,
        'shared_host_configuration_changes':0})
    return {'source_index':sources,'authorization':auth,'runtime_started':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal',action='store_true')
    args=parser.parse_args()
    print(json.dumps(seal() if args.seal else prepare(),ensure_ascii=False))
