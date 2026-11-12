"""Freeze the authorized passive pilot sources and scope; never start resources.

The user has already authorized this fixed twelve-task pilot, the original independent
150-CNY budget (continued, with zero additional cash), and noninterfering experimental Docker use. Sealing binds that
existing authorization to concrete files; it is not a new approval request.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import shutil

from proworksim import software_benchmark_scope_v203_2_1_r2 as scope
from proworksim import software_benchmark_alignment_contract_v203_2_1 as alignment
from proworksim.software_benchmark_candidates_v054 import checked, reference

VERSION='v203.2.1-zero-API-physical-redeployment-source-seal-r2'
SNAPSHOT=scope.ARTIFACT_ROOT/'source-snapshot-r2'
REQUIRED=(
 'src/proworksim/software_benchmark_scope_v203_2_1_r2.py',
 'src/proworksim/software_benchmark_episode_v203_2_1_r2.py',
 'src/proworksim/software_benchmark_host_api_v203_2_1_r2.py',
 'src/proworksim/software_benchmark_deepseek_api_v203_2_1.py',
 'src/proworksim/software_benchmark_grading_v203_2_1_r2.py',
 'src/proworksim/software_benchmark_environment_passive_v203_2_1_r2.py',
 'src/proworksim/software_role_baseline_runtime_v203_2_1.py',
 'src/proworksim/software_benchmark_sdk_bundle_v203_2_1.py',
 'src/proworksim/software_benchmark_alignment_contract_v203_2_1.py',
 'src/proworksim/software_benchmark_runtime_inputs_v203_2_1.py',
 'src/proworksim/software_benchmark_project_closure_v203_2_1.py',
 'src/proworksim/software_observer_journal_v203_2_1.py',
 'src/proworksim/software_observer_views_v203_2_1.py',
 'tools/run_passive_pilot_v203_2_1_r2.py',
 'tools/launch_passive_pilot_v203_2_1_r2.py',
 'tools/run_passive_controller_v203_2_1.py',
 'tools/prepare_passive_execution_v203_2_1_r2.py',
 'tools/seal_passive_pilot_v203_2_1_r2.py',
 'tests/test_passive_deployment_v203_2_1_r2.py',
 'tools/analyze_passive_capture_v203_2_1_r2.py',
 'tools/activate_passive_pilot_v203_2_1_r2.py',
 'tools/run_offline_scorer_v096.py',
)


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def dependency_references(value):
    """Read declared wheel/certificate references without traversing score logs."""
    found=[]
    if isinstance(value,dict):
        if ({'path','sha256','bytes'}<=set(value) and isinstance(value['path'],str)
            and isinstance(value['sha256'],str) and type(value['bytes']) is int):
            found.append({k:value[k] for k in ('path','sha256','bytes')})
        else:
            for child in value.values():found.extend(dependency_references(child))
    elif isinstance(value,list):
        for child in value:found.extend(dependency_references(child))
    return found


def inspect_inputs():
    from proworksim import software_benchmark_sdk_bundle_v203_2_1 as bundle
    paths=[scope.ROOT/name for name in REQUIRED]
    paths += [scope.PLAN_FILE,scope.PANEL_FILE,bundle.OUTPUT/'manifest.json',
        scope.GRADING_ROOT/'environments/bindings.json',
        scope.GRADING_ROOT/'environments/requests2317-offline.json',
        scope.GRADING_ROOT/'environments/pylint4661-appdirs.json',
        scope.COORDINATOR_ROOT/'scorer-manifest.json',
        scope.COORDINATOR_ROOT/'qualification-reuse-decisions.json',
        scope.ARTIFACT_ROOT/'environment-repair-r1/wheelhouse/appdirs-1.4.4-py2.py3-none-any.whl',
        scope.ARTIFACT_ROOT/'environment-repair-r1/appdirs-wheel-provenance.json']
    return {'version':VERSION,'missing':[str(p) for p in paths if not p.is_file()],
        'source_already_sealed':scope.SOURCE_FILE.exists(),'authority_already_bound':scope.AUTH_FILE.exists(),
        'Docker_operations':0,'API_calls':0,'service_operations':0}


def ensure_unentered():
    if scope.SOURCE_FILE.exists() or scope.AUTH_FILE.exists():
        raise PermissionError('This source seal already exists; do not overwrite or reseal it')
    if (scope.API_ROOT/'execution-started.json').exists() or (scope.API_ROOT/'launch-intent.json').exists():
        raise PermissionError('An entered deployment cannot be resealed')
    if list((scope.BATCH_ROOT/'resource-claims').glob('*.json')):
        raise PermissionError('Resources have already acquired identities')


def seal():
    ensure_unentered()
    missing=inspect_inputs()['missing']
    if missing:raise ValueError('Preparation incomplete: '+', '.join(missing))
    from proworksim import software_benchmark_sdk_bundle_v203_2_1 as bundle
    from proworksim import software_benchmark_host_api_v203_2_1_r2 as host
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    bundle_ref=reference(bundle.OUTPUT/'manifest.json');manifest=scope.load(bundle_ref)
    if manifest.get('version')!=bundle.VERSION or manifest.get('adapter')!=reference(bundle.__file__):
        raise ValueError('Prepared private bundle differs from the final builder')
    probe=manifest.get('probe',{})
    if (probe.get('model_calls')!=0 or probe.get('Docker_operations')!=0
        or probe.get('all_controller_and_worker_entrypoints_imported') is not True
        or probe.get('exact_local_content_counter_executed') is not True
        or any(probe.get('forbidden_operation_counts',{}).values())
        or probe.get('organization_ids')!=['REVIEW2']):
        raise ValueError('Actual offline private bundle import/preload has not passed')
    for key in ('benchmark_scorer_or_gold_modules_included','host_key_files_included',
                'host_DeepSeek_API_or_cash_ledger_code_included','models_or_weights_included'):
        if manifest.get(key) is not False:raise ValueError('Forbidden payload in model bundle')
    for ref in (*manifest['source_tools'].values(),*manifest['project_modules'].values(),
                manifest['archive'],manifest['member_inventory'],manifest['probe_source']):checked(ref)
    schemas_ref=host.prepare_schemas();schemas=scope.load(schemas_ref)
    from proworksim.software_role_baseline_runtime_v141 import member_wire_tools
    expected={'REVIEW2':{m:member_wire_tools('REVIEW2',m) for m in ('member_001','member_002')}}
    if schemas['schemas']!=expected:raise ValueError('Actual host schemas changed the original REVIEW2 tools')
    launcher=module(scope.ROOT/'tools/launch_passive_pilot_v203_2_1_r2.py','v203_2_1_seal_launcher')
    unit_ref=launcher.prepare()['specification'];unit=scope.load(unit_ref)
    if unit.get('unit')!=scope.API_UNIT or unit.get('system_parent_slice') is not None:
        raise ValueError('Only the bounded owned ordinary-user coordinator is admitted')
    old=module(scope.ROOT/'tools/seal_role_pilot_v142.py','v203_2_1_source_reader')
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
        scope.SOURCE_PANEL_FILE,scope.SOURCE_PLAN_FILE)]
    files += [bundle_ref,schemas_ref,schemas['actual_member_inventory'],unit_ref,snapshot_ref,
        reference(scope.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json')]
    for row in plan['rows']:
        config=scope.load(row['configuration'])
        files += [row['configuration'],config['configuration'],config['public_tasks'],config['public_test_registry'],
            config['scorer_request_base']['dataset'],config['scorer_request_base']['baseline_mapping']]
    if manifest.get('public_test_dependencies',{}).get('manifest'):
        files.append(manifest['public_test_dependencies']['manifest'])
    for name in ('scorer-manifest.json','qualification-preparation.json','qualification-reuse-decisions.json'):
        p=scope.COORDINATOR_ROOT/name
        if p.is_file():files.append(reference(p))
    files += [reference(p) for p in scope.GRADING_ROOT.glob('control-*/request.json')]
    files += [plan['previous_execution_plan'],plan['zero_request_redeployment_evidence']]
    prior=scope.load(plan['zero_request_redeployment_evidence'])
    files += [prior['prior_coordinator_released'],*prior['prior_episode_quiescence']]
    # New grading descriptors and dependency manifests are immutable preparation
    # inputs; finished runtime score/usage records remain outside this seal.
    for path in (scope.GRADING_ROOT/'environments').rglob('*.json'):
        descriptor_ref=reference(path);files.append(descriptor_ref)
        dependencies=dependency_references(scope.load(descriptor_ref))
        for dependency in dependencies:checked(dependency)
        files.extend(dependencies)
    files.extend(reference(path) for path in (scope.COORDINATOR_ROOT/'qualifications').glob('*.json'))
    wheel_root=scope.ARTIFACT_ROOT/'environment-repair-r1'
    for path in (wheel_root/'wheelhouse/appdirs-1.4.4-py2.py3-none-any.whl',
                 wheel_root/'appdirs-wheel-provenance.json'):
        if path.is_file():files.append(reference(path))
    files=list({ref['path']:ref for ref in files}.values())
    ensure_unentered()
    source_ref=scope.retain(scope.SOURCE_FILE,{'version':scope.VERSION,'files':files,'source_snapshot':snapshot_ref,
        'runtime_data_excluded_from_static_source_index':True,'bundle_archive':manifest['archive'],
        'archive_verified_at_seal_and_upload_not_each_request':True,
        'cash_ledger_and_authority_and_execution_receipts_are_not_static_sources':True})
    proposal={'version':VERSION,'plan':reference(scope.PLAN_FILE),'source_index':source_ref,
        'source_bundle':bundle_ref,'actual_schemas':schemas_ref,'unit':unit_ref,
        'constraints':scope.CONSTRAINTS,'task_count':12,'repository_count':10,'organization_id':'REVIEW2',
        'team_tokens':5_000_000,'total_token_upper_bound':60_000_000,
        'existing_experiment_cash_cap_CNY':'150.00','additional_cash_CNY':'0.00',
        'ledger':str(scope.LEDGER_FILE),'same_r1_ledger_continued':True,'unrelated_old_ledgers_untouched':True,
        'previous_execution_plan':plan['previous_execution_plan'],
        'zero_request_redeployment_evidence':plan['zero_request_redeployment_evidence'],
        'new_logical_model_attempts':0,'new_physical_pairs':12,'new_physical_volumes':12,
        'cash_policy':'reserve worst-case full team at start; release unused capacity after complete settlement',
        'cash_start_reservation_CNY':'40.00','started_teams_not_interrupted_by_cash':True,
        'engineering_gate_slots':[2032200,2032201],'engineering_gate_included_in_twelve':True,
        'second_wave_slots':list(range(2032202,2032212)),
        'gate_is_measurement_and_execution_admission_not_a_new_user_permission':True,
        'automatic_model_replay':False,'task_substitution':False,'training':False,
        'model_visible_tools_prompts_permissions_communication_summaries_organization_changed':False,
        'live_environment_qualification_pending':True,'shared_host_configuration_changes':0,
        'prepared_only':True,'API_calls':0,'Docker_operations':0,'services_started':0}
    proposal_ref=scope.retain(scope.PROPOSAL_FILE,proposal)
    user_ref=scope.retain(scope.USER_GRANT_FILE,{'version':VERSION,'status':'approved','proposal':proposal_ref,
        'authority_source':'Current user request authorizes v203.2.1 fixed twelve-task passive REVIEW2 pilot and the original150-CNY experiment budget; zero-request startup failures are redeployed on fresh physical identities with zero additional cash; AGENTS.md grants noninterfering experimental Docker and ordinary-user project operations.',
        'authorization_is_existing_user_instruction_not_generated_approval':True,
        'existing_cash_cap_CNY':'150.00','additional_cash_CNY':'0.00','standing_Docker_policy':'noninterfering owned experimental containers only',
        'host_root_or_shared_configuration_changes_authorized':False,'training_authorized':False})
    auth={'version':scope.VERSION,'status':'approved','execution_alignment_version':alignment.VERSION,
        'plan':reference(scope.PLAN_FILE),'source_index':source_ref,'proposal':proposal_ref,
        'API_cash_cap_CNY':scope.CASH_CAP_CNY,'cash_budget_scope':scope.CASH_MODE,
        'ledger_paths':{g:str(p) for g,p in scope.LEDGER_FILES.items()},'constraints':scope.CONSTRAINTS,
        'shared_host_configuration_changes':0,'user_grant':user_ref,
        'engineering_gate_required_before_second_wave':True,'services_started':0}
    auth_ref=scope.retain(scope.AUTH_FILE,auth)
    return {'proposal':proposal_ref,'source_index':source_ref,'source_snapshot':snapshot_ref,
        'authorization':auth_ref,'existing_user_authority_bound':True,'static_source_files':len(code),
        'live_environment_qualification_complete':False,'API_calls':0,'Docker_operations':0,'services_started':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--inspect',action='store_true');modes.add_argument('--seal',action='store_true')
    args=parser.parse_args();print(json.dumps(inspect_inputs() if args.inspect else seal(),ensure_ascii=False))
