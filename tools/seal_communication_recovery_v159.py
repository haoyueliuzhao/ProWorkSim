"""Seal the reviewed same-budget source/lifecycle repair; does not launch it."""
from __future__ import annotations
import importlib.util,json
from pathlib import Path
from proworksim import software_benchmark_scope_v159 as scope
from proworksim import software_benchmark_sdk_bundle_v159 as bundle
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_benchmark_alignment_contract_v157 import VERSION as ALIGNMENT_VERSION


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def seal():
    if scope.AUTH_FILE.exists():raise PermissionError('Already sealed recovery cannot be revised in place')
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    original=scope.original_scope
    measurement_ref=reference(scope.ARTIFACT_ROOT/'physical-source-admission-r1/summary.json')
    feedback_ref=reference(scope.ARTIFACT_ROOT/'feedback-sdk-r1/summary.json')
    binding_ref=reference(scope.ARTIFACT_ROOT/'runtime-finish-binding-r1/summary.json')
    finish_ref=reference(scope.ARTIFACT_ROOT/'finalization-controls-r1/summary.json')
    env_ref=reference(scope.ARTIFACT_ROOT/'environment-readiness-r1/summary.json')
    measurement=scope.load(measurement_ref);environment=scope.load(env_ref)
    if (measurement['revised_measurement_admission']['passed'] is not True
        or measurement.get('real_API_calls')!=0 or measurement.get('issues')
        or scope.load(feedback_ref).get('passed') is not True
        or scope.load(binding_ref).get('passed') is not True
        or scope.load(finish_ref).get('passed') is not True
        or environment.get('passed') is not True or environment.get('qualified_count')!=24
        or environment.get('blocked_tasks')):
        raise ValueError('Current source/finalization or actual environment evidence is incomplete')
    current_bundle=scope.load(reference(bundle.OUTPUT/'manifest.json'))
    if current_bundle.get('version')!=bundle.VERSION or current_bundle['probe']['model_calls']!=0:
        raise ValueError('New bundle import/probe is not the finalized recovery version')
    for ref in [*current_bundle['source_tools'].values(),*current_bundle['project_modules'].values()]:checked(ref)
    launcher=module(scope.ROOT/'tools/launch_communication_pilot_v159.py','recovery_launch_seal')
    unit=launcher.prepare()['specification']
    preparation=scope.retain(scope.PREPARATION_QUALIFICATION_FILE,{
        'version':'v159-source-finalization-preparation-r1','passed':True,'model_calls':0,
        'no_previously_called_slot_restarted':True,'source_feedback_replay':measurement_ref,
        'actual_SDK_feedback_replay':feedback_ref,'finish_binding_increment':binding_ref,
        'finalization_controls':finish_ref,'offline_bundle':reference(bundle.OUTPUT/'manifest.json'),
        'predecessor_drain':plan['predecessor_drain'],'coexistence_policy':reference(scope.COEXISTENCE_FILE),
        'current_scoring_environment_admission':env_ref,'new_Docker_diagnostics':0})
    gate=scope.retain(scope.ARTIFACT_ROOT/'runtime-authorization-r1/gate.json',{
        'version':'v159-source-finalization-recovery-gate-r1','passed':True,
        'source_token_mode':'estimated_provider_total_authoritative','source_feedback_replay':measurement_ref,
        'actual_SDK_feedback_replay':feedback_ref,'finish_binding_increment':binding_ref,
        'finalization_controls':finish_ref,'preparation':preparation,'environment':env_ref,
        'new_version_first_wave_episodes':sum(r['wave']==1 for r in plan['rows']),
        'old_failed_measurement_not_relabelled_passed':True,'scores_consulted':False,
        'cash_cap_CNY':'500.00','new_cash_allowance_CNY':'0.00','remaining_original_episodes':len(plan['rows']),
        'called_original_episodes_not_restarted':len(plan['used_original_slots'])})
    proposal=scope.retain(scope.PROPOSAL_FILE,{
        'version':scope.VERSION,'status':'reviewable_authorized_continuation_prepared',
        'plan':reference(scope.PLAN_FILE),'gate':gate,'original_experiment_authority':reference(original.AUTH_FILE),
        'original_cash_authority':reference(scope.BUDGET_BASELINE_FILE),'ledger_path':str(scope.LEDGER_FILE),
        'API_cash_cap_CNY':'500.00','new_cash_allowance_CNY':'0.00',
        'tasks_conditions_seeds_and_team5M_unchanged':True,'source_and_finalizer_repairs_separately_versioned':True,
        'new_generation_slots':len(plan['rows']),'used_original_slots_preserved':len(plan['used_original_slots']),
        'actual_objects_upper_bound':len(plan['rows'])*4,'actual_named_volumes_upper_bound':len(plan['rows']),
        'constraints':scope.CONSTRAINTS,'ordinary_user_unit':unit,
        'predecessor_coexistence':scope.coexistence_status(),
        'maximum1724_score_sessions':6,'maximum1724_connections':3072,'maximum1724_payload_bytes':384*1024**2,
        'score_network_only':'qualified1724 frozen httpbin.org public endpoint80/443; no model/actor network',
        'shared_host_configuration_changes':0,'other_user_objects_modified':False,'training':False})
    grant=scope.retain(scope.USER_GRANT_FILE,{
        'version':'v159-existing-user-authority-unused-original-continuation-r1','approved':True,
        'basis':'existing user continuation500-CNY grant, abnormal-run recovery request and noninterfering experimental Docker standing permission',
        'original_user_amendment':reference(original.ARTIFACT_ROOT/'user-amendment-r1/authorization.json'),
        'standing_Docker_policy':reference(scope.STANDING_POLICY_FILE),
        'user_recovery_instruction':'我们需要的是真实测试结果，不要过度防御，网络等问题应该纳入恢复或者重新测试队列',
        'API_cash_cap_CNY':'500.00','additional_cash_authorized_CNY':'0.00','proposal':proposal,
        'original_called_slots_resampling_authorized_by_this_scope':False,
        'other_root_or_shared_host_configuration_changes_authorized':False})
    sealer=module(scope.ROOT/'tools/seal_role_pilot_v143.py','recovery_source_closure')
    roots=[scope.ROOT/p for p in ('tools/run_communication_pilot_v159.py','tools/launch_communication_pilot_v159.py',
        'tools/advance_communication_wave_v159.py','tools/prepare_communication_recovery_v159.py',
        'tools/seal_communication_recovery_v159.py','tools/run_communication_controller_v159.py',
        'src/proworksim/software_benchmark_scope_v159.py','src/proworksim/software_benchmark_grading_v159.py',
        'src/proworksim/software_benchmark_host_api_v159.py','src/proworksim/software_benchmark_sdk_bundle_v159.py')]
    files=sealer.source_closure(roots=roots)
    files += [reference(bundle.OUTPUT/'manifest.json'),current_bundle['archive'],reference(scope.PLAN_FILE),
        reference(scope.COEXISTENCE_FILE),reference(scope.BUDGET_BASELINE_FILE),preparation,gate,proposal,grant,unit,
        measurement_ref,feedback_ref,binding_ref,env_ref]
    sources=scope.retain(scope.SOURCE_FILE,{'version':'v159-finalized-runtime-source-closure-r1','files':files,
        'new_source_distinct_from_original_v157':True,'old_source_changed':False,'current_model_calls':0})
    auth=scope.retain(scope.AUTH_FILE,{'version':scope.VERSION,'status':'approved',
        'execution_alignment_version':ALIGNMENT_VERSION,'plan':reference(scope.PLAN_FILE),'source_index':sources,
        'proposal':proposal,'user_grant':grant,'gate':gate,'API_cash_cap_CNY':'500.00',
        'original_ledger':str(scope.LEDGER_FILE),'new_cash_budget_CNY':'0.00','constraints':scope.CONSTRAINTS,
        'shared_host_configuration_changes':0,'new_neutral_API_calls':0,
        'used_original_team_resampling':False,'runtime_start_is_separate':True})
    scope.require_allowed('v159.run')
    return {'authorization':auth,'source_index':sources,'gate':gate,'preparation':preparation,
        'unit':unit,'remaining_original_episodes':len(plan['rows']),'launch_performed':False}

if __name__=='__main__':print(json.dumps(seal(),ensure_ascii=False))
