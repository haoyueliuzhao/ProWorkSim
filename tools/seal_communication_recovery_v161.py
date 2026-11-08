"""Review the concrete14-attempt queue; only explicit --seal writes its grants.

No provider ledger registration, Docker operation, service start or API call.
"""
from __future__ import annotations
import argparse,importlib.util,json
from pathlib import Path
from proworksim import software_benchmark_scope_v161 as scope
from proworksim import software_benchmark_sdk_bundle_v161 as bundle
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_benchmark_alignment_contract_v161 import VERSION as ALIGNMENT_VERSION


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def review():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    cpu=reference(scope.ARTIFACT_ROOT/'deployment-controls-r2/summary.json')
    if scope.load(cpu).get('passed') is not True:raise ValueError('Current deployment controls have not passed')
    host_cpu=reference(scope.ARTIFACT_ROOT/'host-budget-controls-r1/summary.json')
    if scope.load(host_cpu).get('passed') is not True:raise ValueError('Independent host/budget controls have not passed')
    for source_ref in scope.load(host_cpu).get('sources',[]):checked(source_ref)
    manifest_ref=reference(bundle.OUTPUT/'manifest.json');manifest=scope.load(manifest_ref)
    if (manifest.get('version')!=bundle.VERSION or manifest.get('probe',{}).get('model_calls')!=0
        or not manifest.get('probe',{}).get('all_controller_and_worker_entrypoints_imported')):
        raise ValueError('Actual current bundle import proof is missing')
    for ref in [*manifest['source_tools'].values(),*manifest['project_modules'].values()]:checked(ref)
    old=scope.ROOT/'artifacts/software-benchmark-v159'
    inherited={key:reference(old/path) for key,path in {
        'source_feedback_replay':'physical-source-admission-r1/summary.json',
        'actual_SDK_feedback_replay':'feedback-sdk-r1/summary.json',
        'finish_binding_increment':'runtime-finish-binding-r1/summary.json',
        'finalization_controls':'finalization-controls-r1/summary.json'}.items()}
    inherited_values={key:scope.load(ref) for key,ref in inherited.items()}
    if (inherited_values['source_feedback_replay'].get('revised_measurement_admission',{}).get('passed') is not True
        or inherited_values['source_feedback_replay'].get('real_API_calls')!=0
        or any(inherited_values[key].get('passed') is not True for key in
            ('actual_SDK_feedback_replay','finish_binding_increment','finalization_controls'))):
        raise ValueError('Inherited actual SDK/source/finish evidence has not passed')
    from proworksim.software_benchmark_grading_v161 import validate_environment_preparation
    env=validate_environment_preparation()
    if env.get('qualified_count')!=5 or env.get('passed') is not True:raise ValueError('Five exact environments are required')
    environment=scope.retain(scope.ARTIFACT_ROOT/'environment-readiness-r1/summary.json',env)
    observer=reference(scope.ROOT/'artifacts/software-benchmark-v167/observer-sdk-r1/summary.json')
    observer_source=reference(scope.ROOT/'artifacts/software-benchmark-v167/physical-source-admission-r1/summary.json')
    observer_cpu=reference(scope.ROOT/'artifacts/software-benchmark-v167/observer-cpu-r1/summary.json')
    explicit_grant=reference(scope.ROOT/'artifacts/software-benchmark-v167/user-recovery-grant-r1/authorization.json')
    if (scope.load(observer).get('passed') is not True
        or scope.load(observer_source).get('revised_measurement_admission',{}).get('passed') is not True
        or scope.load(observer_cpu).get('passed') is not True
        or scope.load(explicit_grant).get('approved') is not True
        or scope.load(explicit_grant).get('maximum_new_team_attempts')!=14):
        raise PermissionError('Observer repair and explicit14-attempt authorization are required')
    inherited.update(observer_SDK=observer,observer_sources=observer_source,observer_CPU=observer_cpu,explicit_user_recovery_grant=explicit_grant)
    launcher=module(scope.ROOT/'tools/launch_communication_pilot_v161.py','v161_review_launch')
    waiter=module(scope.ROOT/'tools/wait_communication_recovery_v161.py','v161_review_wait')
    unit=launcher.prepare()['specification'];wait_unit=waiter.prepare()['specification']
    preparation=scope.retain(scope.PREPARATION_QUALIFICATION_FILE,{
        'version':'v161-independent-technical-recovery-preparation-r1','passed':True,'model_calls':0,
        'recovery_proposal':reference(scope.RECOVERY_PROPOSAL_FILE),'planned_episodes':14,
        'original_context_or_patch_reused':False,'deployment_cpu_controls':cpu,'host_budget_controls':host_cpu,
        'offline_bundle':manifest_ref,**inherited,'current_scoring_environment_admission':environment,
        'new_Docker_diagnostics':0,'new_model_calls':0,'ledger_writes':0})
    gate=scope.retain(scope.ARTIFACT_ROOT/'runtime-authorization-r2/gate.json',{
        'version':'v161-independent-technical-recovery-engineering-gate-r1','passed':True,
        'preparation':preparation,'environment':environment,'CPU_controls':cpu,'host_budget_controls':host_cpu,
        'planned_episodes':14,'one_wave':True,'maximum_attempts_per_original':1,
        'all_model_visible_treatments_still_v157':True,'scores_consulted':False,
        'deferred_until_predecessor_clean':True,'cash_cap_CNY':'500.00','new_cash_allowance_CNY':'0.00'})
    proposal=scope.retain(scope.PROPOSAL_FILE,{
        'version':scope.VERSION,'status':'prepared_pending_root_final_seal','plan':reference(scope.PLAN_FILE),
        'gate':gate,'technical_attempt_proposal':reference(scope.RECOVERY_PROPOSAL_FILE),
        'original_cash_authority':reference(scope.BUDGET_BASELINE_FILE),'ledger_path':str(scope.LEDGER_FILE),
        'API_cash_cap_CNY':'500.00','new_cash_allowance_CNY':'0.00','new_generation_slots':14,
        'maximum_new_input_output_tokens':70_000_000,'maximum_attempts_per_original':1,
        'original_called_slots_preserved':True,'original_15703_locked_candidate_not_replayed':True,
        'deployment_revision':'v167_passive_observer_world_review_receipts_and_bounded_test_metadata',
        'configuration_changed_fields':['slot_id','slot_index'],'model_visible_treatment_unchanged':True,
        'maximum_new_containers':56,'maximum_new_named_volumes':14,'constraints':scope.CONSTRAINTS,
        'ordinary_user_coordinator':unit,'bounded_waiter':wait_unit,
        'predecessor_quiescence_required':True,'scoring_egress_connections':0,
        'shared_host_configuration_changes':0,'other_user_objects_modified':False,'training':False})
    authority=scope.load(reference(scope.RECOVERY_PROPOSAL_FILE))
    authority={**authority,'version':'v161-independent-technical-recovery-authority-r1',
        'status':'prepared_pending_root_final_seal','model_dispatch_enabled':False,
        'deployment_plan':reference(scope.PLAN_FILE),'runtime_proposal':proposal}
    template=scope.retain(scope.ARTIFACT_ROOT/'runtime-authorization-r2/recovery-authority-template.json',authority)
    sealer=module(scope.ROOT/'tools/seal_role_pilot_v143.py','v161_source_closure')
    roots=[scope.ROOT/p for p in ('tools/run_communication_pilot_v161.py','tools/launch_communication_pilot_v161.py',
        'tools/wait_communication_recovery_v161.py','tools/prepare_communication_recovery_v161.py',
        'tools/seal_communication_recovery_v161.py','tools/run_communication_controller_v161.py',
        'src/proworksim/software_benchmark_scope_v161.py','src/proworksim/software_benchmark_grading_v161.py',
        'src/proworksim/software_benchmark_host_api_v161.py','src/proworksim/software_benchmark_sdk_bundle_v161.py')]
    files=sealer.source_closure(roots=roots)
    files += [manifest_ref,manifest['archive'],reference(scope.PLAN_FILE),reference(scope.BUDGET_BASELINE_FILE),
        reference(scope.RECOVERY_PROPOSAL_FILE),preparation,gate,proposal,template,unit,wait_unit,cpu,host_cpu,environment,*inherited.values()]
    sources=scope.retain(scope.SOURCE_FILE,{'version':'v161-finalized-independent-runtime-source-closure-r1',
        'files':files,'original_v157_v159_source_changed':False,'current_model_calls':0,'ledger_registered':False})
    return {'proposal':proposal,'source_index':sources,'gate':gate,'preparation':preparation,
        'authority_template':template,'unit':unit,'waiter':wait_unit,'launch_performed':False,
        'API_calls':0,'Docker_operations':0,'ledger_writes':0}

def seal():
    if scope.AUTH_FILE.exists() or scope.RECOVERY_AUTHORITY_FILE.exists():
        raise PermissionError('A sealed authorization cannot be revised or reissued in place')
    proof=review()
    authority=scope.load(proof['authority_template'])
    authority.update(status='approved',model_dispatch_enabled=True,
        authorization_basis='root-final-seal-of-user-authorized-technical-recovery-within-existing500')
    preflight=scope.retain(scope.ARTIFACT_ROOT/'runtime-authorization-r2/approved-authority-local-check.json',authority)
    from proworksim import software_benchmark_host_api_v161 as host
    host.checked_authority(scope.load(reference(scope.PLAN_FILE)),preflight,
        {group:host.original.api_for(group) for group in host.GROUP_IDS})
    recovery=scope.retain(scope.RECOVERY_AUTHORITY_FILE,authority)
    grant=scope.retain(scope.USER_GRANT_FILE,{'version':'v161-explicit-technical-recovery-existing-budget-grant-r1',
        'approved':True,'proposal':proof['proposal'],'recovery_authority':recovery,
        'basis':'Explicit user reply: 允许14题各独立恢复一次; same500-CNY cap; standing isolated Docker permission',
        'standing_Docker_policy':reference(scope.STANDING_POLICY_FILE),'maximum_new_team_episodes':14,
        'additional_cash_authorized_CNY':'0.00','API_cash_cap_CNY':'500.00',
        'shared_host_configuration_changes_authorized':False})
    auth=scope.retain(scope.AUTH_FILE,{'version':scope.VERSION,'status':'approved',
        'execution_alignment_version':ALIGNMENT_VERSION,'plan':reference(scope.PLAN_FILE),
        'source_index':proof['source_index'],'proposal':proof['proposal'],'user_grant':grant,
        'gate':proof['gate'],'recovery_authority':recovery,'API_cash_cap_CNY':'500.00',
        'original_ledger':str(scope.LEDGER_FILE),'new_cash_budget_CNY':'0.00','constraints':scope.CONSTRAINTS,
        'shared_host_configuration_changes':0,'runtime_start_is_separate':True,
        'predecessor_full_cleanup_required':True})
    scope.require_allowed('v161.wait')
    return {**proof,'authorization':auth,'recovery_authority':recovery,'ledger_registration_performed':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seal',action='store_true')
    args=p.parse_args();print(json.dumps(seal() if args.seal else review(),ensure_ascii=False))
