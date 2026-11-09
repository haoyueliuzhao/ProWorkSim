"""Prepare14 independently named technical recoveries; no API/Docker/ledger write."""
from __future__ import annotations
import argparse,copy,json,importlib.util
from collections import Counter
from proworksim import software_benchmark_scope_v170 as scope
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration

def prepare_plan():
    if scope.PLAN_FILE.exists():
        plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
        return {'plan':reference(scope.PLAN_FILE),'rows':len(plan['rows']),'already_prepared':True}
    original=scope.original_scope.validate_plan(scope.load(reference(scope.original_scope.PLAN_FILE)))
    originals={r['slot_id']:r for r in original['rows']}
    proposal=scope.load(reference(scope.RECOVERY_PROPOSAL_FILE))
    rows=[];resources={}
    for attempt in proposal['attempts']:
        row=copy.deepcopy(originals[attempt['original_slot_id']])
        row.update(slot_id=attempt['recovery_slot_id'],slot_index=attempt['slot_index'],configuration=attempt['configuration'])
        rows.append(row)
        for role in ('actor','controller','volume','score','delivery-score'):
            spec=copy.deepcopy(original['resources'][f"{role}-{attempt['original_slot_index']}"])
            spec['slot_id']=row['slot_id'];resources[f"{role}-{row['slot_index']}"]=spec
    tasks={r['instance_id'] for r in rows}
    inventory=scope.retain(scope.INVENTORY_FILE,{'version':scope.VERSION,'rows':rows,
        'generation':{},'scores':{},'deliveries':{},'original_plan':reference(scope.original_scope.PLAN_FILE)})
    plan={'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'original_plan':reference(scope.original_scope.PLAN_FILE),
        'recovery_proposal':reference(scope.RECOVERY_PROPOSAL_FILE),
        'panel':reference(scope.PANEL_FILE),'matrix':reference(scope.PANEL_FILE),'rows':rows,'generation_rows':rows,
        'original_ledger':str(scope.LEDGER_FILE),'new_cash_budget_CNY':'50.00',
        'input_plus_output_token_upper_bound_for_remaining':65_000_000,
        'constraints':scope.CONSTRAINTS,'host_cpu_pool':reference(scope.CPU_POOL_FILE),'inventory':inventory,
        'environments':{k:v for k,v in original['environments'].items() if k in tasks},
        'environment_sources':copy.deepcopy(original['environment_sources']),
        'resources':resources,'resource_role_counts':dict(Counter(x['role'] for x in resources.values())),
        'diagnostics':[],'training':False,'old_results_preserved':True,'model_calls_during_preparation':0,
        'independent_recovery_original_slots':[a['original_slot_id'] for a in proposal['attempts']],
        'dispatch_admission':declaration(scope.BATCH_ROOT),
        'wave_policy':{'waves':1,'planned_episodes':13,'prior_patch_context_feedback_reused':False,
            'scores_consulted':False,'maximum_attempts_per_original':1,
            'wait_for_predecessor_all_objects_removed':True}}
    scope.validate_plan(plan);ref=scope.retain(scope.PLAN_FILE,plan)
    scope.retain(scope.STATE_ROOT/'admission-control.json',{'version':'v132-fair-group-admission-r1',
        'batch_root':str(scope.BATCH_ROOT),'mode':'run','groups':[],'maximum_generations':16,
        'revision':0,'reason':'independent_technical_recovery_after_predecessor_cleanup'})
    return {'plan':ref,'rows':13,'fresh_resource_identities':65,'model_calls':0,'Docker_operations':0,'ledger_writes':0}

def prepare_bundle():
    from proworksim.software_benchmark_sdk_bundle_v170 import prepare_bundle
    return prepare_bundle()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',action='store_true')
    args=parser.parse_args();print(json.dumps(prepare_bundle() if args.bundle else prepare_plan(),ensure_ascii=False))
