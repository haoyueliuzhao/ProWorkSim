"""Seal13 completion attempts and the user's50-CNY/start-only cash amendment."""
from __future__ import annotations
import importlib.util
import json

from proworksim import software_benchmark_scope_v170 as scope
from proworksim import software_benchmark_sdk_bundle_v170 as bundle
from proworksim import software_benchmark_completion_api_v170 as cash
from proworksim import software_benchmark_host_api_v157 as account
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_benchmark_alignment_contract_v170 import VERSION as ALIGNMENT_VERSION


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def seal():
    if scope.AUTH_FILE.exists():raise PermissionError('A sealed completion owner cannot be overwritten')
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    user=reference(scope.ARTIFACT_ROOT/'user-amendment-r1/authorization.json')
    proposal=scope.load(reference(scope.RECOVERY_PROPOSAL_FILE))
    cpu=reference(scope.ARTIFACT_ROOT/'deployment-controls-r1/summary.json')
    cash_cpu=reference(scope.ARTIFACT_ROOT/'cash-controls-r1/summary.json')
    for proof in (cpu,cash_cpu):
        value=scope.load(proof)
        if value.get('passed') is not True:raise ValueError('Current CPU admission has not passed')
        for ref in value['sources']:checked(ref)
    manifest=reference(bundle.OUTPUT/'manifest.json');packed=scope.load(manifest)
    if (packed['version']!=bundle.VERSION or packed['probe'].get('model_calls')!=0
            or packed['probe'].get('all_controller_and_worker_entrypoints_imported') is not True):
        raise ValueError('Actual current controller/worker import proof is missing')
    for ref in [*packed['source_tools'].values(),*packed['project_modules'].values()]:checked(ref)
    from proworksim.software_benchmark_grading_v170 import validate_environment_preparation
    env=validate_environment_preparation()
    if env.get('passed') is not True or env.get('qualified_count')!=7 or env['blocked_tasks']:
        raise ValueError('The seven exact task environments are not fully qualified')
    env_ref=scope.retain(scope.ARTIFACT_ROOT/'environment-readiness-r1/summary.json',env)
    quiet=scope.predecessor_quiescence_status()
    if quiet.get('passed') is not True:raise PermissionError('Previous owned resources are still active')
    quiet_ref=scope.retain(scope.ARTIFACT_ROOT/'predecessor-cleanup-r1/summary.json',quiet)
    authority={'version':cash.AUTH_VERSION,'approved':True,'user_grant':user,
        'base_policy_sha256':cash.base.sha(account.api_for('C0').POLICY),
        'ledger_path':str(scope.LEDGER_FILE),'new_team_start_threshold_nanoyuan':cash.THRESHOLD,
        'additional_nominal_nanoyuan':50_000_000_000,'started_teams_finish_above_threshold':True,
        'team_token_limit':5_000_000,'maximum_new_attempts':13,'attempts':proposal['attempts'],
        'no_score_based_selection':True,'old_records_and_costs_retained':True,
        'maximum_added_input_output_tokens':65_000_000,'automatic_additional_retries':False}
    preview=scope.retain(scope.ARTIFACT_ROOT/'runtime-authorization-r2/authority-checked.json',authority)
    cash.validate_authority(account.api_for('C0'),preview)  # No registration or spending.
    authority_ref=scope.retain(scope.RECOVERY_AUTHORITY_FILE,authority)
    old=scope.ROOT/'artifacts/software-benchmark-v167'
    inherited={'observer_SDK':reference(old/'observer-sdk-r1/summary.json'),
        'observer_sources':reference(old/'physical-source-admission-r1/summary.json'),
        'observer_CPU':reference(old/'observer-cpu-r1/summary.json'),
        'source_feedback_replay':reference(old/'physical-source-admission-r1/summary.json'),
        'finalization_controls':reference(scope.ROOT/'artifacts/software-benchmark-v159/finalization-controls-r1/summary.json')}
    for ref in inherited.values():checked(ref)
    unit=module(scope.ROOT/'tools/launch_communication_pilot_v170.py','completion_launch').prepare()['specification']
    preparation=scope.retain(scope.PREPARATION_QUALIFICATION_FILE,{
        'version':'v170-completion-technical-recovery-preparation-r1','passed':True,'model_calls':0,
        'planned_episodes':13,'original_context_or_patch_reused':False,
        'recovery_proposal':reference(scope.RECOVERY_PROPOSAL_FILE),'deployment_cpu_controls':cpu,
        'cash_policy_controls':cash_cpu,'offline_bundle':manifest,'explicit_user_recovery_grant':user,
        'environment':env_ref,'predecessor':quiet_ref,**inherited})
    gate=scope.retain(scope.ARTIFACT_ROOT/'runtime-authorization-r2/gate.json',{
        'passed':True,'preparation':preparation,'cash_policy_controls':cash_cpu,
        'planned_attempts':13,'same_model_visible_configuration':True,'scores_consulted':False,
        'start_threshold_CNY':'550.00','started_teams_finish_above_threshold':True})
    runtime_proposal=scope.retain(scope.PROPOSAL_FILE,{
        'version':scope.VERSION,'plan':reference(scope.PLAN_FILE),'gate':gate,'user_grant':user,
        'generation_attempts':13,'candidate_only_rescores_separate':2,'team_token_cap':5_000_000,
        'maximum_added_input_output_tokens':65_000_000,'maximum_new_containers':52,'maximum_new_volumes':13,
        'nominal_addition_CNY':'50.00','new_team_start_threshold_CNY':'550.00',
        'finish_started_teams_above_threshold':True,'threshold_is_absolute_total_ceiling':False,
        'new_teams_not_started_after_threshold':True,'old_cash_POLICY_unchanged':True,
        'ledger':str(scope.LEDGER_FILE),'ordinary_user_coordinator':unit,'constraints':scope.CONSTRAINTS,
        'shared_host_configuration_changes':0,'automatic_more_independent_attempts':False})
    grant=scope.retain(scope.USER_GRANT_FILE,{'approved':True,'user_message':scope.load(user)['user_message'],
        'original_user_grant':user,'concrete_proposal':runtime_proposal,
        'standing_isolated_Docker_policy':reference(scope.STANDING_POLICY_FILE),
        'additional_nominal_CNY':'50.00','already_started_cash_interruptions_forbidden':True})
    builder=module(scope.ROOT/'tools/seal_role_pilot_v143.py','completion_source_builder')
    paths=['tools/run_communication_pilot_v170.py','tools/run_communication_controller_v170.py',
        'tools/launch_communication_pilot_v170.py','tools/seal_communication_completion_v170.py',
        'tools/prepare_communication_completion_v170.py','src/proworksim/software_benchmark_scope_v170.py',
        'src/proworksim/software_benchmark_host_api_v170.py','src/proworksim/software_benchmark_grading_v170.py',
        'src/proworksim/software_benchmark_sdk_bundle_v170.py']
    files=builder.source_closure(roots=[scope.ROOT/p for p in paths])
    files += [reference(scope.PLAN_FILE),reference(scope.RECOVERY_PROPOSAL_FILE),manifest,packed['archive'],
        preparation,authority_ref,cpu,cash_cpu,env_ref,quiet_ref,unit,gate,runtime_proposal,grant,user,*inherited.values()]
    sources=scope.retain(scope.SOURCE_FILE,{'version':'v170-completion-runtime-source-closure-r1',
        'files':files,'historical_runtime_sources_changed':False})
    auth=scope.retain(scope.AUTH_FILE,{'version':scope.VERSION,'status':'approved',
        'execution_alignment_version':ALIGNMENT_VERSION,'plan':reference(scope.PLAN_FILE),
        'source_index':sources,'proposal':runtime_proposal,'user_grant':grant,'gate':gate,
        'API_cash_cap_CNY':'550.00','cash_limit_mode':'new_team_start_only',
        'original_ledger':str(scope.LEDGER_FILE),'new_cash_budget_CNY':'50.00',
        'constraints':scope.CONSTRAINTS,'shared_host_configuration_changes':0,
        'recovery_authority':authority_ref,'model_dispatch_performed':False})
    scope.require_allowed()
    return {'authorization':auth,'source_index':sources,'gate':gate,
        'cash_registration_performed':False,'model_calls':0,'Docker_operations':0}


if __name__=='__main__':print(json.dumps(seal()))
