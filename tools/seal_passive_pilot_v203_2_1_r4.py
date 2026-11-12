"""Seal ten still-uncalled original tasks; no new money or model attempts."""
import importlib.util
import json
import shutil
from pathlib import Path
from proworksim import software_benchmark_scope_v203_2_1_r4 as scope
from proworksim import software_benchmark_host_api_v203_2_1_r4 as host
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
        raise ValueError('Never reseal an admitted continuation')
    if list((scope.BATCH_ROOT/'resource-claims').glob('*.json')):
        raise ValueError('Leaf physical identities already consumed')
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    if len(plan['rows'])!=10 or [r['slot_index'] for r in plan['rows']]!=list(range(2032402,2032412)):
        raise ValueError('Only the ten uncalled original identities may continue')
    scope.require_continuation_gate()
    schemas=host.prepare_schemas()
    parent_schemas=scope.load(reference(scope.parent.API_ROOT/'api-runtime/member-tool-schemas-r1.json'))
    if scope.load(schemas)['schemas']!=parent_schemas['schemas']:
        raise ValueError('The leaf changed the original model-visible tools')
    launcher=module(Path(__file__).with_name('launch_passive_pilot_v203_2_1_r4.py'),'leaf_launcher')
    unit=launcher.prepare()['specification']
    old=module(Path(__file__).with_name('seal_role_pilot_v142.py'),'source_reader')
    roots=[Path(__file__).resolve(),scope.ROOT/'tools/run_passive_pilot_v203_2_1_r4.py',
        scope.ROOT/'tools/launch_passive_pilot_v203_2_1_r4.py',
        scope.ROOT/'tools/prepare_passive_revalidation_gate_v203_2_1_r4.py',
        scope.ROOT/'tools/prepare_passive_execution_v203_2_1_r4.py',
        scope.ROOT/'tests/test_passive_continuation_queue_v203_2_1_r4.py',
        scope.ROOT/'tests/test_passive_continuation_scope_v203_2_1_r4.py',
        scope.ROOT/'tools/analyze_passive_capture_v203_2_1_r4.py',
        scope.ROOT/'tools/run_offline_scorer_v096.py',Path(scope.__file__),Path(host.__file__),
        scope.ROOT/'src/proworksim/software_benchmark_episode_v203_2_1_r4.py',
        scope.ROOT/'src/proworksim/software_benchmark_grading_v203_2_1_r4.py']
    sources=old.source_closure(scope.ROOT,roots=roots)
    snapshot=scope.ARTIFACT_ROOT/'continuation-r4/source-snapshot';rows=[]
    for item in sources:
        source=Path(item['path']);target=snapshot/source.relative_to(scope.ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if target.read_bytes()!=source.read_bytes():raise ValueError('Source snapshot changed')
        else:shutil.copyfile(source,target)
        rows.append({'source':item,'snapshot':reference(target)})
    snap=scope.retain(snapshot/'manifest.json',{'files':rows,'parent_running_sources_unchanged':True})
    files=[*sources,snap,unit,schemas,reference(scope.PLAN_FILE),reference(scope.PANEL_FILE),
        reference(scope.CPU_POOL_FILE),reference(scope.parent.SOURCE_FILE),reference(scope.REVALIDATION_FILE),reference(bundle.OUTPUT/'manifest.json'),
        reference(scope.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json')]
    for row in plan['rows']:
        config=scope.load(row['configuration'])
        files.extend([row['configuration'],config['configuration'],config['public_tasks'],config['public_test_registry'],
            config['scorer_request_base']['dataset'],config['scorer_request_base']['baseline_mapping']])
    for dependency in refs(scope.load(reference(scope.REVALIDATION_FILE))):
        checked(dependency);files.append(dependency)
    for folder in [scope.COORDINATOR_ROOT,scope.GRADING_ROOT/'environments']:
        for path in folder.rglob('*.json'):
            item=reference(path);files.append(item)
            for child in refs(scope.load(item)):checked(child);files.append(child)
    files=list({r['path']:r for r in files}.values())
    source_index=scope.retain(scope.SOURCE_FILE,{'version':scope.VERSION,'files':files,
        'parent_gate_progress_and_shared_ledger_are_dynamic_not_static_sources':True})
    proposal=scope.retain(scope.PROPOSAL_FILE,{'version':scope.VERSION,'plan':reference(scope.PLAN_FILE),
        'source_index':source_index,'constraints':scope.CONSTRAINTS,
        'remaining_original_slot_ids':[r['slot_id'] for r in plan['rows']],
        'physical_indices':[r['slot_index'] for r in plan['rows']],
        'parent_plan':reference(scope.parent.PLAN_FILE),'parent_source':reference(scope.parent.SOURCE_FILE),
        'original_first_two_reanalysis_gate':reference(scope.REVALIDATION_FILE),
        'same_existing_ledger':str(scope.LEDGER_FILE),'cash_cap_CNY':'150.00','additional_cash_CNY':'0.00',
        'new_logical_model_attempts':0,'remaining_original_task_model_tokens':50_000_000,
        'original_total_planned_tasks':12,'original_first_two_replayed':False,
        'original_tools_prompts_model_seeds_sdk_and_budgets_unchanged':True,
        'scores_used_for_admission':False,'source_archives_not_modified':True,
        'new_owned_user_unit':scope.API_UNIT,'maximum_generations':8,'maximum_graders':2,
        'maximum_CPUs':64,'maximum_memory_GiB':456,
        'new_system_slice':False,'new_GPU_operations':0,'host_root_operations':0})
    grant=scope.retain(scope.USER_GRANT_FILE,{'status':'approved','proposal':proposal,
        'authority':'Existing user authorization of the original twelve tasks and total150 CNY; standing noninterfering experimental Docker authorization. These are ten uncalled original tasks, not additional attempts.',
        'additional_cash_CNY':'0.00','parent_model_attempts_replayed':False})
    auth=scope.retain(scope.AUTH_FILE,{'version':scope.VERSION,'status':'approved',
        'execution_alignment_version':ALIGNMENT,'plan':reference(scope.PLAN_FILE),'source_index':source_index,
        'proposal':proposal,'user_grant':grant,'API_cash_cap_CNY':'150.00','cash_budget_scope':scope.CASH_MODE,
        'ledger_paths':{g:str(p) for g,p in scope.LEDGER_FILES.items()},'constraints':scope.CONSTRAINTS,
        'shared_host_configuration_changes':0,'additional_cash_CNY':'0.00',
        'remaining_original_slot_ids':[r['slot_id'] for r in plan['rows']],
        'recovered_original_first_two_gate_required_before_model':True})
    return {'authorization':auth,'proposal':proposal,'source_index':source_index,
        'API_calls':0,'Docker_operations':0,'user_service_started':False}


if __name__=='__main__':print(json.dumps(seal(),ensure_ascii=False))
