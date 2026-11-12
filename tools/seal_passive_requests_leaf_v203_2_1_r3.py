"""Seal one still-uncalled original task; no new money or model attempts."""
import importlib.util
import json
import shutil
from pathlib import Path
from proworksim import software_benchmark_scope_passive_leaf_v203_2_1_r3 as scope
from proworksim import software_benchmark_host_api_passive_leaf_v203_2_1_r3 as host
from proworksim import software_benchmark_sdk_bundle_v203_2_1 as bundle
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_benchmark_alignment_contract_v203_2_1 import VERSION as ALIGNMENT


def module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def refs(value):
    if isinstance(value,dict):
        if {'path','sha256','bytes'}<=set(value):
            yield {k:value[k] for k in ('path','sha256','bytes')}
        else:
            for item in value.values():yield from refs(item)
    elif isinstance(value,list):
        for item in value:yield from refs(item)


def seal():
    if scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists():
        raise ValueError('Never reseal an admitted leaf')
    if list((scope.BATCH_ROOT/'resource-claims').glob('*.json')):
        raise ValueError('Leaf physical identities already consumed')
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    row=plan['rows'][0]
    if row['instance_id']!=scope.TASK or row['slot_index']!=2032307:
        raise ValueError('Only the original remaining Requests task is allowed')
    ca=scope.load(reference(scope.CA_RESULT_FILE))
    if not ca.get('qualification_passed') or not ca.get('cleanup_proven') or ca.get('active_owned_claims'):
        raise ValueError('Actual CA controls have not qualified and cleaned')
    schemas=host.prepare_schemas()
    parent_schemas=scope.load(reference(scope.parent.API_ROOT/'api-runtime/member-tool-schemas-r1.json'))
    if scope.load(schemas)['schemas']!=parent_schemas['schemas']:
        raise ValueError('The leaf changed the original model-visible tools')
    launcher=module(Path(__file__).with_name('launch_passive_requests_leaf_v203_2_1_r3.py'),'leaf_launcher')
    unit=launcher.prepare()['specification']
    old=module(Path(__file__).with_name('seal_role_pilot_v142.py'),'source_reader')
    roots=[Path(__file__).resolve(),scope.ROOT/'tools/run_passive_requests_leaf_v203_2_1_r3.py',
        scope.ROOT/'tools/launch_passive_requests_leaf_v203_2_1_r3.py',
        scope.ROOT/'tools/analyze_passive_capture_v203_2_1_r2.py',
        scope.ROOT/'tools/run_offline_scorer_v096.py',Path(scope.__file__),Path(host.__file__),
        scope.ROOT/'src/proworksim/software_benchmark_episode_passive_leaf_v203_2_1_r3.py',
        scope.ROOT/'src/proworksim/software_benchmark_grading_passive_leaf_v203_2_1_r3.py']
    sources=old.source_closure(scope.ROOT,roots=roots)
    snapshot=scope.ARTIFACT_ROOT/'requests-leaf-r3/source-snapshot';rows=[]
    for item in sources:
        source=Path(item['path']);target=snapshot/source.relative_to(scope.ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if target.read_bytes()!=source.read_bytes():raise ValueError('Source snapshot changed')
        else:shutil.copyfile(source,target)
        rows.append({'source':item,'snapshot':reference(target)})
    snap=scope.retain(snapshot/'manifest.json',{'files':rows,'parent_running_sources_unchanged':True})
    files=[*sources,snap,unit,schemas,reference(scope.PLAN_FILE),reference(scope.PANEL_FILE),
        reference(scope.CPU_POOL_FILE),reference(scope.parent.SOURCE_FILE),reference(scope.CA_RESULT_FILE),
        scope.qualified_r3_ref(),reference(bundle.OUTPUT/'manifest.json'),
        reference(scope.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json')]
    config=scope.load(row['configuration'])
    files.extend([row['configuration'],config['configuration'],config['public_tasks'],config['public_test_registry'],
        config['scorer_request_base']['dataset'],config['scorer_request_base']['baseline_mapping']])
    for folder in [scope.COORDINATOR_ROOT,scope.GRADING_ROOT/'environments']:
        for path in folder.rglob('*.json'):
            item=reference(path);files.append(item)
            for child in refs(scope.load(item)):checked(child);files.append(child)
    files=list({r['path']:r for r in files}.values())
    source_index=scope.retain(scope.SOURCE_FILE,{'version':scope.VERSION,'files':files,
        'parent_gate_progress_and_shared_ledger_are_dynamic_not_static_sources':True})
    proposal=scope.retain(scope.PROPOSAL_FILE,{'version':scope.VERSION,'plan':reference(scope.PLAN_FILE),
        'source_index':source_index,'constraints':scope.CONSTRAINTS,
        'remaining_original_slot_id':row['slot_id'],'same_original_seed':row['seed'],
        'physical_index':2032307,'parent_plan':reference(scope.parent.PLAN_FILE),
        'parent_source':reference(scope.parent.SOURCE_FILE),'CA_qualification':scope.qualified_r3_ref(),
        'same_existing_ledger':str(scope.LEDGER_FILE),'cash_cap_CNY':'150.00','additional_cash_CNY':'0.00',
        'new_logical_model_attempts':0,'planned_original_task_model_tokens':5_000_000,
        'wait_for_parent_engineering_and_CA_qualification':True,'parent_state_or_service_modified':False,
        'new_owned_user_unit':scope.API_UNIT,'CPU_pool_offsets':[64,69],'coordinator_memory_GiB':8,
        'new_system_slice':False,'new_GPU_operations':0,'host_root_operations':0})
    grant=scope.retain(scope.USER_GRANT_FILE,{'status':'approved','proposal':proposal,
        'authority':'Existing user authorization of the original twelve tasks and total150 CNY; standing noninterfering experimental Docker authorization. This is the one uncalled original task, not an extra attempt.',
        'additional_cash_CNY':'0.00','parent_model_attempts_replayed':False})
    auth=scope.retain(scope.AUTH_FILE,{'version':scope.VERSION,'status':'approved',
        'execution_alignment_version':ALIGNMENT,'plan':reference(scope.PLAN_FILE),'source_index':source_index,
        'proposal':proposal,'user_grant':grant,'API_cash_cap_CNY':'150.00','cash_budget_scope':scope.CASH_MODE,
        'ledger_paths':{g:str(p) for g,p in scope.LEDGER_FILES.items()},'constraints':scope.CONSTRAINTS,
        'shared_host_configuration_changes':0,'additional_cash_CNY':'0.00',
        'remaining_original_slot_id':row['slot_id'],'parent_gate_required_before_model':True})
    return {'authorization':auth,'proposal':proposal,'source_index':source_index,
        'API_calls':0,'Docker_operations':0,'user_service_started':False}


if __name__=='__main__':print(json.dumps(seal(),ensure_ascii=False))
