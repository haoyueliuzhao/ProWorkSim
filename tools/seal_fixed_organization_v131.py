"""Seal the reviewable five-group runtime; live admissions remain post-grant."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP='True',OPENHANDS_SUPPRESS_BANNER='1',
    HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',TRANSFORMERS_OFFLINE='1')

from proworksim import software_benchmark_scope_v131 as scope
from proworksim.software_benchmark_candidates_v054 import checked,reference,write_new

VERSION='v131-code-seal-with-explicit-postgrant-admission-r1'
REQUIRED_CONTROLS=(
    'scope-controls-r1/summary.json','api-queue-controls-r2/summary.json',
    'host-integration-controls-r1/summary.json',
    'generation-admission-controls-r1/summary.json','grading-binding-controls-r2/summary.json',
    'httpbin-probe-controls-r2/summary.json','organization-sdk-controls-r1/summary.json',
    'seal-activation-controls-r1/summary.json',
    'organization-cash-boundary-control-r1/summary.json',
    'final-cleanup-delta-r1/summary.json',
    'actor-explicit-bindings-r1/summary.json','schema-bundle-revision-r2/summary.json')


def postgrant_sequence():
    return ['bounded_direct_httpbin_probe','cold_grading_preparation',
            'create_or_verify_exact_new_parent','launch_unique_user_coordinator']


def source_closure():
    # All newly added runtime, helpers and CPU controls are explicit seal roots.
    roots=[*scope.ROOT.glob('src/proworksim/*v131.py'),*scope.ROOT.glob('tools/*v131.py'),
           *scope.ROOT.glob('tests/*v131.py'),scope.ROOT/'tools/run_offline_scorer_v096.py']
    pending,found=list(roots),{}
    while pending:
        path=pending.pop().resolve()
        if str(path) in found:
            continue
        found[str(path)]=reference(path)
        try:
            package='.'.join(path.relative_to(scope.ROOT/'src').with_suffix('').parts).rsplit('.',1)[0]
        except ValueError:
            package=None
        for node in ast.walk(ast.parse(path.read_bytes(),filename=str(path))):
            if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value.endswith('.py'):
                literal=node.value
                target=(scope.ROOT/'tools'/literal if Path(literal).name==literal
                        else scope.ROOT/literal if literal.startswith(('tools/','src/')) else None)
                if target is not None and target.is_file():
                    pending.append(target)
            candidates=[]
            if isinstance(node,ast.Import):
                candidates=[item.name for item in node.names]
            elif isinstance(node,ast.ImportFrom):
                if node.level:
                    if package is None:
                        continue
                    base='.'.join(package.split('.')[:len(package.split('.'))-node.level+1])
                    full=base+('.'+node.module if node.module else '')
                else:
                    full=node.module or ''
                candidates=[full,*[full+'.'+item.name for item in node.names]]
            for name in candidates:
                if name.startswith('proworksim'):
                    target=scope.ROOT/'src'/Path(*name.split('.'))
                    for candidate in (target.with_suffix('.py'),target/'__init__.py'):
                        if candidate.is_file():
                            pending.append(candidate)
                            break
    return [found[key] for key in sorted(found)]


def validate_review_shapes(plan,bundle,schemas,parent,unit):
    groups=set(scope.GROUP_IDS)
    if (len(plan.get('rows',[]))!=250 or len(plan.get('environments',{}))!=50
            or plan.get('constraints')!=scope.CONSTRAINTS
            or set(schemas.get('schemas',{}))!=groups or schemas.get('neutral_calls')!=0
            or schemas.get('provider_search_or_fetch') is not False
            or set(bundle.get('probe',{}).get('organization_ids',[]))!=groups
            or bundle.get('probe',{}).get('model_calls')!=0
            or bundle.get('probe',{}).get('all_controller_and_worker_entrypoints_imported') is not True
            or any(bundle.get('probe',{}).get('forbidden_operation_counts',{}).values())):
        raise ValueError('Five real member schemas and the offline runtime probe must match the exact panel')
    if (parent.get('slice')!=scope.CONTAINER_PARENT or parent.get('new_system_manager_objects')!=1
            or parent.get('memory_max_bytes')!=832*scope.GIB or parent.get('cpu_quota_cores')!=144
            or parent.get('memory_swap_max_bytes')!=0
            or parent.get('existing_container_or_process_migrations') is not False
            or unit.get('unit')!=scope.API_UNIT or unit.get('memory_max_bytes')!=32*scope.GIB
            or unit.get('cpu_quota_percent')!=800 or unit.get('restart')!='no'):
        raise ValueError('The reviewed aggregate and coordinator limits differ')
    for group in groups:
        members=next(row['fixed_members'] for row in plan['rows'] if row['organization_id']==group)
        if set(schemas['schemas'][group])!=set(members):
            raise ValueError('A frozen group has another member tool inventory')
    return {'passed':True,'groups':sorted(groups),'postgrant_sequence':postgrant_sequence(),
        'live_environment_admission_complete':False,'runtime_authorized':False}


def seal():
    from proworksim import software_benchmark_api_parent_v131 as parent
    from proworksim import software_benchmark_host_api_v131 as host
    from proworksim import software_benchmark_sdk_bundle_v131 as bundle
    from proworksim.software_benchmark_alignment_contract_v131 import VERSION as ALIGNMENT
    if any(path.exists() for path in (scope.AUTH_FILE,scope.SOURCE_FILE,scope.PROPOSAL_FILE)):
        raise PermissionError('Never reseal an approved or already sealed batch')
    if any(path.exists() for path in scope.LEDGER_FILES.values()):
        raise PermissionError('This proposal is for five fresh organization ledgers, not resumed calls')
    if any((scope.API_ROOT/name).exists() for name in ('launch-intent.json','execution-started.json')):
        raise PermissionError('An entered coordinator identity cannot be sealed again')
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    bundle_ref=reference(bundle.OUTPUT/'manifest.json')
    manifest=scope.load(bundle_ref)
    if manifest.get('version')!=bundle.VERSION or manifest.get('adapter')!=reference(bundle.__file__):
        raise ValueError('The actual prepared runtime bundle belongs to another source')
    for ref in (*manifest['source_tools'].values(),*manifest['project_modules'].values(),
                manifest['archive'],manifest['member_inventory'],manifest['probe_source']):
        checked(ref)
    for key in ('benchmark_scorer_or_gold_modules_included','host_key_files_included',
                'host_DeepSeek_API_or_cash_ledger_code_included','models_or_weights_included'):
        if manifest.get(key) is not False:
            raise ValueError('The actor bundle includes forbidden host/scoring material')
    schemas_ref=host.prepare_schemas()
    schemas=scope.load(schemas_ref)
    if schemas.get('runtime_bundle')!=bundle_ref:
        raise ValueError('Member schemas were prepared against another actual bundle')
    checked(schemas['actual_member_inventory'])
    spec=importlib.util.spec_from_file_location('v131_sealed_launcher',scope.ROOT/'tools/launch_fixed_organization_v131.py')
    launcher=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    unit_ref=launcher.prepare()['specification']
    unit=scope.load(unit_ref)
    parent_ref=parent.prepare_proposal()
    parent_proposal=scope.load(parent_ref)
    if parent_proposal.get('source')!=reference(parent.__file__):
        raise ValueError('The aggregate-parent proposal predates its final source')
    review=validate_review_shapes(plan,manifest,schemas,parent_proposal,unit)
    controls={}
    for name in REQUIRED_CONTROLS:
        ref=reference(scope.ARTIFACT_ROOT/name)
        if scope.load(ref).get('passed') is not True:
            raise ValueError('A necessary CPU control did not pass: '+name)
        controls[name]=ref
    grade=scope.load(controls['grading-binding-controls-r2/summary.json'])
    if grade.get('grading_source')!=reference(scope.ROOT/'src/proworksim/software_benchmark_grading_v131.py'):
        raise ValueError('The group/aggregate scoring control predates its runtime source')
    files=source_closure()+[reference(path) for path in (
        scope.PLAN_FILE,scope.PANEL_FILE,scope.CPU_POOL_FILE,scope.SOURCE_PANEL_FILE,scope.SOURCE_PLAN_FILE,
        scope.CA_PROFILE_FILE,host.TOKENIZER)]
    files += [row['configuration'] for row in plan['rows']]
    files += [scope.load(row['configuration'])['configuration'] for row in plan['rows']]
    files += [bundle_ref,schemas_ref,schemas['actual_member_inventory'],unit_ref,parent_ref,
              manifest['public_test_dependencies']['manifest'],*controls.values()]
    admitted_files={}
    if scope.NETWORK_RESOLUTION_FILE.exists():
        path=scope.ROOT/'tools/activate_fixed_organization_v131.py'
        spec=importlib.util.spec_from_file_location('v131_seal_existing_admissions',path)
        activation=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(activation)
        admitted_files['network']=activation.require_probe_result()
        files.extend(admitted_files['network'].values())
        files.append(reference(activation.PROBE_INTENT))
    cold=scope.ARTIFACT_ROOT/'grading-transport-control-r1/preparation.json'
    if cold.exists():
        value=scope.load(reference(cold))
        if (value.get('passed') is not True or value.get('plan')!=reference(scope.PLAN_FILE)
                or value.get('live_TLS_qualification_still_pending') is not True):
            raise ValueError('The available grading preparation does not bind this plan')
        admitted_files['cold_grading']=reference(cold)
        files.append(reference(cold))
        files += [reference(path) for path in scope.COORDINATOR_ROOT.rglob('*.json')]
        files += [reference(path) for path in scope.GRADING_ROOT.glob('control-v131-*/request.json')]
    files=list({item['path']:item for item in files}.values())
    # These are intentionally not in the code seal: they do not exist until the
    # granted admission runs, or are append-only accounting/runtime state.
    pending={
        'actual_parent_qualification':str(parent.CREATED),
        'actual_zero_model_actor_qualification':str(scope.BATCH_ROOT/'diagnostic-1/result.json'),
        'fresh_official_TLS_controls':4,
        'API_ledgers':{g:str(p) for g,p in scope.LEDGER_FILES.items()},
        'generation_scoring_and_cleanup_receipts':'fresh runtime results; never a code-seal input'}
    if 'network' not in admitted_files:
        pending['network_resolution']=str(scope.NETWORK_RESOLUTION_FILE)
    if 'cold_grading' not in admitted_files:
        pending['grading_preparation']=str(scope.COORDINATOR_ROOT)
    sources=write_new(scope.SOURCE_FILE,{'version':scope.VERSION,'files':files,'controls':controls,
        'runtime_authorized':False,'live_environment_admission_complete':False,
        'postgrant_admission_required':pending,'runtime_data_excluded_from_static_source_index':True,
        'completed_readonly_admission_files':admitted_files,
        'bundle_archive_verified_at_seal_and_before_each_upload':manifest['archive'],
        'archive_not_rehashed_on_every_API_authority_check':True})
    sealed_verification=None
    if 'cold_grading' in admitted_files:
        from proworksim import software_benchmark_grading_v131 as grading
        completed=subprocess.run(grading.command(['--verify-preparation']),cwd=scope.ROOT,
            env=grading.clean_environment(),capture_output=True,text=True,timeout=300,check=False)
        if completed.returncode:
            raise ValueError('Read-only grading identity changed after static seal: '+completed.stderr[-2000:])
        verified=json.loads(completed.stdout)
        if verified.get('passed') is not True or verified.get('artifacts_created_or_modified')!=0:
            raise ValueError('The post-seal grader check did not remain read-only')
        target=scope.ARTIFACT_ROOT/'runtime-authorization-r1/post-seal-grading-verification.json'
        target.parent.mkdir(parents=True,exist_ok=True)
        sealed_verification=write_new(target,{'source_index':sources,'result':verified,
            'AUTH_and_SOURCE_do_not_enter_grading_manifest':True,'model_calls':0,'Docker_operations':0})
    proposal={'version':scope.VERSION,'status':'prepared','runtime_authorized':False,
        'execution_started':False,'execution_alignment_version':ALIGNMENT,
        'plan':reference(scope.PLAN_FILE),'source_index':sources,'constraints':scope.CONSTRAINTS,
        'new_generation_attempts':250,'different_tasks':50,'organizations':list(scope.GROUP_IDS),
        'API_cash_cap_by_group_CNY':{g:'100.00' for g in scope.GROUP_IDS},
        'API_cash_cap_CNY':'500.00','cash_budget_scope':scope.CASH_MODE,
        'ledger_paths':{g:str(p) for g,p in scope.LEDGER_FILES.items()},
        'group_budget_transfer_allowed':False,'budget_guarantees_all_tasks_complete':False,
        'new_model_tokens_upper_bound':1_250_000_000,'tokens_are_shared_per_team_not_per_member':True,
        'new_neutral_API_calls':0,'maximum_containers':1006,'maximum_named_volumes':251,
        'maximum_generation_pairs':48,'maximum_concurrent_startups':8,'maximum_graders':2,
        'new_diagnostic_pairs':1,'diagnostic_model_calls':0,'new_official_control_containers':4,
        'maximum_code_score_containers':250,'maximum_delivery_score_containers':250,
        'same_tree_delivery_reuse':'Only its own group/task/attempt locked code candidate',
        'aggregate_parent_proposal':parent_ref,'new_system_manager_objects':1,
        'parent_CPU_quota_cores':144,'parent_memory_GiB':832,'parent_swap_bytes':0,
        'ordinary_user_unit':scope.API_UNIT,'coordinator_unit':unit_ref,
        'coordinator_CPU_quota_cores':8,'coordinator_memory_GiB':32,
        'combined_CPU_quota_cores':152,'combined_memory_GiB':864,
        'maximum_TLS_scoring_sessions':24,'maximum_external_scoring_connections':12288,
        'maximum_external_scoring_payload_bytes':1536*1024**2,
        'additional_health_probe_connections':4,'additional_health_probe_application_bytes':64*1024,
        'private_diagnostic_loopback_connections':32,'private_diagnostic_maximum_seconds':90,
        'container_network':'none','container_cap_drop':['ALL'],
        'cap_add_except_declared_Requests_graders':[],
        'Requests_grader_cap_add':['NET_ADMIN','NET_BIND_SERVICE'],
        'CA_profile':reference(scope.CA_PROFILE_FILE),'host_binds':0,'host_listeners':0,'GPUs':0,
        'shared_host_configuration_changes':0,'existing_units_or_other_tasks_modified':False,
        'new_slice_is_explicitly_separate_from_existing_host_configuration_changes':True,
        'provider_search_or_fetch':False,'automatic_retry_or_resampling':False,
        'source_bundle':bundle_ref,'actual_member_schemas':schemas_ref,'controls':controls,
        'completed_readonly_admission_files':admitted_files,
        'post_seal_grading_identity_verification':sealed_verification,
        'postgrant_sequence':postgrant_sequence(),'postgrant_admission_required':pending,
        'live_environment_admission_complete':False,'pure_review_shape':review}
    scope.PROPOSAL_FILE.parent.mkdir(parents=True,exist_ok=True)
    return {'proposal':write_new(scope.PROPOSAL_FILE,proposal),'source_index':sources,
            'runtime_authorized':False,'live_environment_admission_complete':False}


if __name__=='__main__':
    print(json.dumps(seal(),ensure_ascii=False))
