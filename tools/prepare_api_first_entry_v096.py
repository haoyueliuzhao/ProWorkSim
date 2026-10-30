"""Prepare the 79-row continuation and a reviewable proposal; never approve or launch it."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import copy
import importlib.util
import json
from pathlib import Path
import time

from proworksim import software_benchmark_api_scope_v096 as scope
from proworksim.software_benchmark_candidates_v054 import reference,write_new

VERSION='v096-original-first-entry-preparation-r1'
NEW_FILES=(
 'src/proworksim/software_benchmark_api_scope_v096.py',
 'src/proworksim/software_benchmark_api_budget_v096.py',
 'src/proworksim/software_benchmark_runtime_v096.py',
 'src/proworksim/software_benchmark_pressure_v096.py',
 'src/proworksim/software_benchmark_grading_v096.py',
 'src/proworksim/software_benchmark_api_parent_v096.py',
 'src/proworksim/software_benchmark_sdk_bundle_v096.py',
 'src/proworksim/software_benchmark_managed_actor_v096.py',
 'src/proworksim/software_benchmark_managed_v096.py',
 'src/proworksim/software_benchmark_nullable_cursor_v090.py',
 'src/proworksim/software_benchmark_managed_sync_v095.py',
 'src/proworksim/software_benchmark_rescore_v095.py',
 'tools/run_project_controller_v096.py','tools/run_managed_worker_docker_v096.py',
 'tools/prepare_api_first_entry_v096.py','tools/run_api_first_entry_v096.py',
 'tools/launch_api_first_entry_v096.py','tools/check_api_first_entry_v096.py',
 'tools/check_scoring_first_entry_v096.py',
 'tools/run_adaptive_v076.py','tools/run_api_recovery_v088.py',
 'tools/run_capability_grading_v066.py','tools/run_offline_scorer_v058.py',
 'tools/run_offline_scorer_v096.py',
)


def preflight_files():
    rows=scope.selected_original_rows()
    zero=scope.zero_request_snapshot(rows)
    conflicts=[]
    for index in range(6090,6169):
        if (scope.original.BATCH_ROOT/'episodes'/str(index)).exists() or any(
                (scope.original.BATCH_ROOT/'resource-claims'/f'{role}-{index}.json').exists()
                for role in ('actor','controller','volume','score','delivery-score')):
            conflicts.append(index)
    if conflicts:
        raise PermissionError('Physical identities already consumed: '+str(conflicts))
    return {'zero_API':zero,'physical_indices':list(range(6090,6169)),
        'physical_destinations_unconsumed':True,'host_service_state_not_modified':True}


def prepare_plan():
    if scope.PLAN_FILE.exists() or scope.INVENTORY_FILE.exists() or scope.CANONICAL_INVENTORY_FILE.exists():
        raise ValueError('Plan preparation is single-use; preserve prior preparation')
    ready=preflight_files()
    scope.BATCH_ROOT.mkdir(parents=True,exist_ok=False)
    source_rows=scope.selected_original_rows()
    ancestor=scope.load(reference(scope.original.PLAN_FILE))
    history=scope.load(reference(scope.ORIGINAL_SUMMARY))
    canonical=write_new(scope.CANONICAL_INVENTORY_FILE,{'version':scope.VERSION,'rows':source_rows,
        'source_plan':reference(scope.original.PLAN_FILE),'zero_API_audit':reference(scope.ZERO_API_FILE),
        'historical_inventory_summary':reference(scope.AUDIT_FILE),'original_first_model_attempts':79,
        'additional_model_attempts':0,'API_ledger':str(scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3')})
    rows,configs,resources=[],[],{}
    for position,old in enumerate(source_rows):
        fields=scope.physical_fields(old,position)
        index=fields['slot_index']
        config={**scope.load(old['configuration']),'slot_index':index}
        path=scope.BATCH_ROOT/'configs'/f'{index}.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        config_ref=write_new(path,config)
        row={**old,**fields,'configuration':config_ref}
        scope._validate_physical_mapping_at(row,old,config,scope.load(old['configuration']),position)
        rows.append(row)
        configs.append({'slot_id':row['slot_id'],'physical_index':index,'original_slot_index':old['slot_index'],
            'configuration':config_ref,'canonical_configuration':old['configuration']})
        for prefix in ('actor','controller','volume','score','delivery-score'):
            previous=ancestor['resources'].get(f'{prefix}-{old["slot_index"]}')
            if previous is not None:
                resources[f'{prefix}-{index}']={**previous,
                    'prior_physical_slot_index':old['slot_index'],
                    'physical_launch_attempt':fields['physical_launch_attempt']}
    tasks={row['instance_id'] for row in rows}
    configuration_index=write_new(scope.BATCH_ROOT/'active-configurations.json',{'version':VERSION,'rows':configs})
    inventory=write_new(scope.INVENTORY_FILE,{'version':VERSION,'rows':rows,
        'canonical_original_inventory':canonical,'zero_API_audit':reference(scope.ZERO_API_FILE),
        'historical_inventory_summary':reference(scope.AUDIT_FILE),'source_original_summary':reference(scope.ORIGINAL_SUMMARY),
        'generation':{},'scores':{},'deliveries':{},'usage_record_files':[],
        'qualifications':{task:history['qualifications'][task] for task in tasks},
        'allowed_generation_slot_ids':[row['slot_id'] for row in rows],
        'continuation_slot_ids':[row['slot_id'] for row in rows],
        'API_ledger':str(scope.original.PREDECESSOR_ROOT/'api-budget/ledger.sqlite3'),
        'financial_recovery_inventory':reference(scope.FINANCIAL_RECOVERY_INVENTORY),
        'logical_first_model_attempts':79,'additional_model_attempts':0,
        'remaining_original_input_output_upper_bound':395_000_000,
        'model_resampling':False,'old_results_and_claims_preserved':True,
        'source_original_panel_denominator':1000,
        'lineage':[{'slot_id':r['slot_id'],'original_slot_index':r['original_slot_index'],
                    'physical_index':r['slot_index'],'physical_launch_attempt':r['physical_launch_attempt']}
                   for r in rows]})
    from proworksim.software_benchmark_runtime_v096 import bindings
    from proworksim import software_benchmark_sdk_bundle_v096 as bundle
    bundle_manifest=bundle.prepare_bundle()
    plan={**copy.deepcopy(ancestor),'version':scope.VERSION,'rows':rows,'resources':resources,
        'resource_role_counts':dict(Counter(v['role'] for v in resources.values())),
        'environments':{task:copy.deepcopy(ancestor['environments'][task]) for task in tasks},
        'constraints':copy.deepcopy(bindings.dispatch_view(lambda *_a,**_k:None).CONSTRAINTS),
        'continuation_inventory':inventory,'inventory':inventory,'canonical_original_inventory':canonical,
        'remaining_generation_slots':79,'remaining_original_token_upper_bound':395_000_000,
        'original_plan':reference(scope.original.PLAN_FILE),'active_configurations':configuration_index,
        'historical_results_preserved':True,'training':False,'model_calls_during_preparation':0,
        'administrative_root':str(scope.BATCH_ROOT),'logical_first_model_attempts':79,
        'additional_model_attempts':0,'old_raw_results_overwritten':False,
        'fixed_runtime_bundle':bundle_manifest,'original_first_attempt_panel_denominator':1000,
        'new_container_upper_bound':278,'new_named_volume_upper_bound':79,
        'previous_removed_zero_API_containers':144,'previous_removed_zero_API_named_volumes':78,
        'historical_plus_new_lineage_container_upper_bound':422,
        'historical_plus_new_lineage_volume_upper_bound':157,
        'startup_health_gate':{'maximum_unconfirmed_launches':2,'required_interfaces':['REF','PROJECT'],
            'success_criterion':'at_least_one_settled_paid_API_request_per_preselected_interface',
            'task_scores_used':False,'after_pass_generation_limit':48}}
    plan_ref=write_new(scope.PLAN_FILE,plan)
    scope.validate_complete_plan(plan,scope.load(inventory))
    return write_new(scope.BATCH_ROOT/'plan-prepared.json',{'version':VERSION,'plan':plan_ref,
        'inventory':inventory,'canonical_original_inventory':canonical,'read_only_admission':ready,
        'source_sealed':False,'production_authorization_created':False,
        'model_calls':0,'Docker_operations':0,'service_operations':0})


def source_closure():
    # Explicit entry files plus their actual Python import dependencies. There
    # is no wildcard over unfinished v096 files or another agent's new work.
    pending=[scope.ROOT/name for name in NEW_FILES]
    result={}
    while pending:
        path=pending.pop().resolve()
        if str(path) in result:
            continue
        if not path.is_file():
            raise FileNotFoundError('Required explicit source is not ready: '+str(path))
        result[str(path)]=reference(path)
        try:
            relative=path.relative_to(scope.ROOT/'src')
            module='.'.join(relative.with_suffix('').parts)
            package=module.rsplit('.',1)[0]
        except ValueError:
            package=None
        for node in ast.walk(ast.parse(path.read_bytes(),filename=str(path))):
            if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value.endswith('.py'):
                literal=node.value
                if Path(literal).name==literal:
                    dynamic_tool=scope.ROOT/'tools'/literal
                elif literal.startswith('tools/'):
                    dynamic_tool=scope.ROOT/literal
                else:
                    dynamic_tool=None
                if dynamic_tool is not None and dynamic_tool.is_file():
                    pending.append(dynamic_tool)
            candidates=[]
            if isinstance(node,ast.Import):
                candidates=[a.name for a in node.names]
            elif isinstance(node,ast.ImportFrom):
                if node.level:
                    if package is None:
                        continue
                    base='.'.join(package.split('.')[:len(package.split('.'))-node.level+1])
                    full=base+('.'+node.module if node.module else '')
                else:
                    full=node.module or ''
                candidates=[full,*[full+'.'+a.name for a in node.names]]
            for name in candidates:
                if not name.startswith('proworksim'):
                    continue
                target=scope.ROOT/'src'/Path(*name.split('.'))
                for possible in [target.with_suffix('.py'),target/'__init__.py']:
                    if possible.is_file():
                        pending.append(possible)
                        break
    return [result[key] for key in sorted(result)]


def seal(cpu_control):
    ready=preflight_files()
    control_ref=reference(cpu_control)
    control=scope.load(control_ref)
    if (control.get('passed') is not True or control.get('runtime_initialized') is not True
            or control.get('actual_episode_thread_entry_checked') is not True
            or control.get('interfaces_checked')!=['REF','PROJECT']
            or control.get('production_ledger_modified') is not False
            or any(control.get(k)!=0 for k in ['model_calls','HTTP_calls','Docker_operations','GPU_operations'])):
        raise PermissionError('Real initialization and bound FIFO controls must pass before sealing')
    scorer_control_ref=reference(scope.ROOT/'artifacts/software-benchmark-v096/scorer-isolation-control-r1/summary.json')
    scorer_control=scope.load(scorer_control_ref)
    if (scorer_control.get('passed') is not True or scorer_control.get('actual_child_validate_request') is not True
            or scorer_control.get('production_records_written') is not False
            or scorer_control.get('manifest',{}).get('scoring_adapter') != reference(scope.ROOT/'src/proworksim/software_benchmark_grading_v096.py')
            or control.get('cold_scorer_manifest_stable_after_API_counter') is not True):
        raise PermissionError('Actual cold scorer validation and counter-isolated manifest controls are required')
    if scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists():
        raise ValueError('Do not overwrite a production authority or prior source seal')
    plan=scope.load(reference(scope.PLAN_FILE))
    scope.validate_complete_plan(plan,scope.load(reference(scope.INVENTORY_FILE)))
    spec=importlib.util.spec_from_file_location('v096_launcher',scope.ROOT/'tools/launch_api_first_entry_v096.py')
    launcher=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    unit=launcher.prepare()
    scope.COORDINATOR_ROOT.mkdir(parents=True,exist_ok=True)
    sources=write_new(scope.SOURCE_FILE,{'version':scope.VERSION,'files':source_closure(),
        'selection':'explicit entrypoints plus recursively resolved in-repository Python imports; no glob',
        'bundle':plan['fixed_runtime_bundle']})
    proposed_authority={'version':scope.VERSION,'status':'pending_explicit_runtime_review',
        'source_index':sources,'plan':reference(scope.PLAN_FILE),'inventory':reference(scope.INVENTORY_FILE),
        'canonical_original_inventory':reference(scope.CANONICAL_INVENTORY_FILE),
        'zero_API_audit':scope.require_physical_audit(),'historical_inventory_summary':reference(scope.AUDIT_FILE),
        'logical_first_model_attempts':79,'original_first_model_attempts':79,
        'additional_model_attempts':0,'additional_attempts_to_original_panel':0,'API_cash_cap_CNY':'1700.00',
        'old_records_overwritten':False,'Qwen_lifecycle_operations':0,
        'unit':unit['specification'],'CPU_execution_control':control_ref,'cold_scoring_CPU_control':scorer_control_ref,
        'maximum_new_containers':278,'maximum_new_named_volumes':79,
        'new_parent_creation':False,'existing_parent':reference(scope.parent_module().CREATED),
        'grading_external_network_authorized':False,'GPU_operations':0,'host_configuration_changes':0,
        'original_first_entry_continuation_not_independent_resampling':True}
    proposal=write_new(scope.BATCH_ROOT/'runtime-authorization-proposal.json',proposed_authority)
    return write_new(scope.BATCH_ROOT/'preparation.json',{'version':VERSION,'unix':time.time(),
        'proposal':proposal,'production_authorization_created':False,'read_only_admission':ready,
        'CPU_execution_control':control_ref,'service_operations':0,'model_calls':0,
        'execution_requires_approved_authorization_at':str(scope.AUTH_FILE)})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--plan-only',action='store_true')
    group.add_argument('--seal',action='store_true')
    parser.add_argument('--cpu-control',type=Path)
    args=parser.parse_args()
    if args.seal and args.cpu_control is None:
        parser.error('--seal requires --cpu-control')
    print(json.dumps(prepare_plan() if args.plan_only else seal(args.cpu_control),ensure_ascii=False))
