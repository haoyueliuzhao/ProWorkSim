"""Freeze new-role-context source and bind the existing CNY130/Docker grant."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
from proworksim import software_benchmark_scope_v203_2_3 as scope
from proworksim import software_benchmark_alignment_contract_v203_2_3 as alignment
from proworksim.software_benchmark_candidates_v054 import checked, reference

VERSION = 'v203.2.3-source-and-existing-authority-seal-r1'
SNAPSHOT = scope.ARTIFACT_ROOT/'source-snapshot-r1'
REQUIRED = tuple('src/proworksim/'+name+'_v203_2_3.py' for name in (
    'software_benchmark_scope','software_benchmark_alignment_contract','software_benchmark_host_api',
    'software_benchmark_deepseek_api','software_benchmark_episode','software_benchmark_sdk_bundle',
    'software_benchmark_runtime_inputs','software_benchmark_project_closure','software_benchmark_grading',
    'software_benchmark_environment','software_benchmark_grading_views','software_role_context','software_role_context_runtime',
    'software_public_test_retention')) + (
    'tools/run_role_context_pilot_v203_2_3.py','tools/launch_role_context_pilot_v203_2_3.py',
    'tools/prepare_role_context_execution_v203_2_3.py','tools/seal_role_context_pilot_v203_2_3.py',
    'tools/run_role_context_controller_v203_2_3.py','tools/run_offline_scorer_v096.py',
    'tools/check_role_context_public_qualification_v203_2_3.py',
    'tools/check_role_context_sympy_native_v203_2_3.py',
    'src/proworksim/software_benchmark_preparation_grading_v203_2_3.py',
    'src/proworksim/software_benchmark_preparation_grading_v203_2_3_r2.py',
    'src/proworksim/software_benchmark_environment_v203_2_3_r2.py',
    'src/proworksim/software_benchmark_grading_v203_2_3_r2.py',
    'src/proworksim/software_benchmark_grading_views_v203_2_3_r2.py')


def module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def inspect_inputs():
    from proworksim import software_benchmark_sdk_bundle_v203_2_3 as bundle
    paths=[scope.ROOT/name for name in REQUIRED]
    paths += [scope.PLAN_FILE,scope.PANEL_FILE,bundle.OUTPUT/'manifest.json',
        scope.ARTIFACT_ROOT/'runtime-gates-r1/gate.json']
    return {'version':VERSION,'missing':[str(p) for p in paths if not p.is_file()],
        'source_already_sealed':scope.SOURCE_FILE.exists(),'authority_already_bound':scope.AUTH_FILE.exists(),
        'Docker_operations':0,'API_calls':0,'service_operations':0}


def ensure_unentered():
    if scope.SOURCE_FILE.exists() or scope.AUTH_FILE.exists():
        raise PermissionError('Do not overwrite an existing source seal')
    if any((scope.API_ROOT/name).exists() for name in ('execution-started.json','launch-intent.json')):
        raise PermissionError('An entered deployment cannot be resealed')
    claims = scope.BATCH_ROOT/'resource-claims'
    for path in claims.glob('active-*.json'):
        value=scope.load(reference(path))
        if value.get('spec',{}).get('role')!='control' or value['spec'].get('instance_id')!='psf__requests-1766':
            raise PermissionError('An active non-Requests preparation resource prevents sealing')
    preparatory_prefixes = ('public-qualification-', 'control-r2-psf__requests-1766-gold.', 'control-r2-psf__requests-1766-empty.', 'control-psf__requests-1766-gold.', 'control-psf__requests-1766-empty.')
    if any(not p.name.startswith(preparatory_prefixes) for p in claims.glob('*.json') if not p.name.startswith('active-')):
        raise PermissionError('Formal resources have already acquired identities')
    prepared_keys = [v['resource_key'] for v in scope.load(reference(scope.PLAN_FILE)).get('public_qualifications', [])]
    prepared_keys += ['control-psf__requests-1766-gold', 'control-psf__requests-1766-empty']
    for key in prepared_keys:
        claim = claims/(key+'.json')
        if key.startswith('public-qualification-') and claim.exists() and not (claims/(key+'.released.json')).exists():
            raise PermissionError('A public qualification resource has no release proof')


def seal():
    ensure_unentered()
    missing=inspect_inputs()['missing']
    if missing:raise ValueError('Preparation incomplete: '+', '.join(missing))
    from proworksim import software_benchmark_sdk_bundle_v203_2_3 as bundle
    from proworksim import software_benchmark_host_api_v203_2_3 as host
    from proworksim import software_benchmark_grading_v203_2_3_r2 as grading
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    scope.require_runtime_gate()
    scope.validate_first_model_admission()
    bundle_ref=reference(bundle.OUTPUT/'manifest.json');manifest=scope.load(bundle_ref)
    if manifest.get('version') != bundle.VERSION or manifest.get('adapter') != reference(bundle.__file__):
        raise ValueError('The private bundle differs from the final builder')
    probe=manifest.get('probe',{})
    if (probe.get('model_calls') != 0 or probe.get('Docker_operations') != 0
            or probe.get('all_controller_and_worker_entrypoints_imported') is not True
            or probe.get('exact_local_content_counter_executed') is not True
            or any(probe.get('forbidden_operation_counts',{}).values())):
        raise ValueError('Actual private SDK bundle import/preload has not passed')
    for key in ('benchmark_scorer_or_gold_modules_included','host_key_files_included',
                'host_DeepSeek_API_or_cash_ledger_code_included','models_or_weights_included'):
        if manifest.get(key) is not False:raise ValueError('Forbidden payload in solver bundle')
    for ref in (*manifest['source_tools'].values(),*manifest['project_modules'].values(),
                manifest['archive'],manifest['member_inventory'],manifest['probe_source']):checked(ref)
    # The same real wire capabilities fund all three context selections.
    schemas_ref=host.prepare_schemas();schemas=scope.load(schemas_ref)
    from proworksim.software_role_baseline_runtime_v141 import member_wire_tools
    expected={g:{m:member_wire_tools('REVIEW2',m) for m in ('member_001','member_002')} for g in alignment.GROUP_IDS}
    if schemas['schemas'] != expected:raise ValueError('Context arms changed actual REVIEW2 wire tools')
    prepared=grading.prepare_environment_qualifications_local()
    scoring=grading.scorer(grading.scope.dispatch_view())
    completed,pending={},{}
    pending_path=scope.COORDINATOR_ROOT/'pending-qualification-plan.json'
    pending_spec=scope.load(reference(pending_path)) if pending_path.exists() else None
    for task,environment in plan['environments'].items():
        qpath=grading.scope.COORDINATOR_ROOT/'qualifications'/(task+'.json')
        if task=='psf__requests-1766' and pending_spec:
            if pending_spec.get('task')!=task or pending_spec.get('status') not in {'pending_controls','not_qualified'}:
                raise PermissionError('Pending Requests qualification specification differs')
            pending[task]={key:pending_spec[key] for key in ('status','qualification_path','terminal_result_path')}
            if pending[task]['status']=='not_qualified':
                pending[task]['reason']=pending_spec.get('reason','fresh_environment_not_qualified')
            continue
        qref=reference(qpath)
        scoring.validate_qualification(qref,scope.load(environment['configuration']),reference(scope.PLAN_FILE))
        completed[task]=qref
    if set(completed)|set(pending)!=set(plan['environments']):
        raise PermissionError('Every frozen task needs a ready or explicit pending/failed environment state')
    control_completions=[]
    for request_ref in prepared.get('controls',[]):
        request=scope.load(request_ref)
        if request['instance_id']!='psf__requests-1766':
            raise PermissionError('Unexpected prelaunch control identity')
        folder=Path(request['directory'])
        if not (folder/'quiescence.json').exists():
            control_completions.append({'request':request_ref,'status':'pending_preparation_control'})
            continue
        quiet_ref=reference(folder/'quiescence.json');quiet=scope.load(quiet_ref)
        released=reference(scope.BATCH_ROOT/'resource-claims'/(request['resource_key']+'.released.json'))
        if quiet.get('quiescent') is not True:
            raise PermissionError('A completed Requests control lacks cleanup proof')
        control_completions.append({'request':request_ref,'quiescence':quiet_ref,'released':released})
    scope.retain(scope.COORDINATOR_ROOT/'qualification-completion-index.json',{
        'version':VERSION,'plan':reference(scope.PLAN_FILE),'qualifications':completed,'pending_tasks':pending,
        'control_evidence':control_completions,'all_four_tasks_qualified':len(completed)==4,
        'pending_tasks_cannot_call_API':True,'planned_denominator':12})
    launcher=module(scope.ROOT/'tools/launch_role_context_pilot_v203_2_3.py','v203_2_3_seal_launcher')
    unit_ref=launcher.prepare()['specification']
    old=module(scope.ROOT/'tools/seal_role_pilot_v142.py','v203_2_3_source_reader')
    roots=[scope.ROOT/name for name in REQUIRED]
    roots += [Path(r['path']) for r in (*manifest['source_tools'].values(),*manifest['project_modules'].values())]
    code=old.source_closure(scope.ROOT,roots=roots)
    snapshots=[]
    for ref in code:
        source=Path(ref['path']);destination=SNAPSHOT/source.relative_to(scope.ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists():
            if destination.read_bytes()!=source.read_bytes():raise ValueError('Snapshot differs: '+str(destination))
        else:shutil.copyfile(source,destination)
        snapshots.append({'source':ref,'snapshot':reference(destination)})
    snapshot_ref=scope.retain(SNAPSHOT/'manifest.json',{'version':VERSION,'files':snapshots,
        'actual_execution_uses_original_sealed_paths':True,'historical_source_files_modified':False})
    files=code+[reference(p) for p in (scope.PLAN_FILE,scope.PANEL_FILE,scope.CPU_POOL_FILE,
        scope.SOURCE_PANEL_FILE,scope.SOURCE_PLAN_FILE,scope.ARTIFACT_ROOT/'runtime-gates-r1/gate.json')]
    files += [bundle_ref,schemas_ref,schemas['actual_member_inventory'],unit_ref,snapshot_ref,
        reference(scope.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json')]
    for row in plan['rows']:
        config=scope.load(row['configuration'])
        files += [row['configuration'],config['configuration'],config['public_tasks'],config['public_test_registry'],
            config['scorer_request_base']['dataset'],config['scorer_request_base']['baseline_mapping']]
    files += [reference(p) for p in scope.COORDINATOR_ROOT.rglob('*.json')]
    files += [reference(p) for p in grading.scope.COORDINATOR_ROOT.rglob('*.json')]
    files += [reference(p) for p in (scope.GRADING_ROOT/'environments').rglob('*.json')]
    files += [reference(p) for p in (grading.scope.GRADING_ROOT/'environments').rglob('*.json')]
    from proworksim import software_benchmark_preparation_grading_v203_2_3_r2 as control_scope
    files.append(reference(control_scope.CONTROL_PLAN_FILE))
    if pending_spec:
        files += [reference(pending_path), pending_spec['profile'], pending_spec['CA_profile']]
    files += scope.require_runtime_gate()['evidence']
    if manifest.get('public_test_dependencies',{}).get('manifest'):
        files.append(manifest['public_test_dependencies']['manifest'])
    files=list({ref['path']:ref for ref in files}.values())
    ensure_unentered()
    source_ref=scope.retain(scope.SOURCE_FILE,{'version':scope.VERSION,'files':files,'source_snapshot':snapshot_ref,
        'runtime_data_excluded_from_static_source_index':True,'bundle_archive':manifest['archive'],
        'archive_verified_at_seal_and_upload_not_each_request':True,
        'cash_ledger_and_authority_and_execution_receipts_are_not_static_sources':True})
    proposal_ref=scope.retain(scope.PROPOSAL_FILE,{'version':VERSION,'plan':reference(scope.PLAN_FILE),
        'source_index':source_ref,'source_bundle':bundle_ref,'actual_schemas':schemas_ref,'unit':unit_ref,
        'constraints':scope.CONSTRAINTS,'task_count':4,'repository_count':4,'round_count':12,
        'organization_id':'REVIEW2','conditions':list(alignment.GROUP_IDS),'team_tokens':5_000_000,
        'new_cash_cap_CNY':'130.00','ledger':str(scope.LEDGER_FILE),'old_ledgers_untouched':True,
        'cash_policy':'reserve full worst-case team before start, then finish admitted work',
        'cash_start_reservation_CNY':'40.00','started_teams_not_interrupted_by_cash':True,
        'automatic_model_replay':False,'task_substitution':False,'training':False,
        'shared_host_configuration_changes':0,'API_calls':0,'Docker_operations':0,'services_started':0})
    user_ref=scope.retain(scope.USER_GRANT_FILE,{'version':VERSION,'status':'approved','proposal':proposal_ref,
        'authority_source':'User explicitly said continue experiments with a NEW independent CNY130 budget; AGENTS grants noninterfering experimental Docker and ordinary-user project operations without per-batch confirmation.',
        'authorization_is_existing_user_instruction_not_generated_approval':True,'new_cash_CNY':'130.00',
        'host_root_or_shared_configuration_changes_authorized':False,'training_authorized':False})
    auth_ref=scope.retain(scope.AUTH_FILE,{'version':scope.VERSION,'status':'approved',
        'execution_alignment_version':alignment.VERSION,'plan':reference(scope.PLAN_FILE),
        'source_index':source_ref,'proposal':proposal_ref,'API_cash_cap_CNY':scope.CASH_CAP_CNY,
        'cash_budget_scope':scope.CASH_MODE,'ledger_paths':{g:str(p) for g,p in scope.LEDGER_FILES.items()},
        'constraints':scope.CONSTRAINTS,'shared_host_configuration_changes':0,'user_grant':user_ref})
    return {'source_index':source_ref,'source_snapshot':snapshot_ref,'authorization':auth_ref,
        'existing_user_authority_bound':True,'static_source_files':len(code),'API_calls':0,'Docker_operations':0}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--inspect',action='store_true');modes.add_argument('--seal',action='store_true')
    args=parser.parse_args();print(json.dumps(inspect_inputs() if args.inspect else seal(),ensure_ascii=False))
