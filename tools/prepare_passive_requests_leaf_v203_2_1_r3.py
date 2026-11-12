"""Prepare the original Requests first-model leaf; no runtime or ledger write."""
from __future__ import annotations
from collections import Counter
import copy
import json
import os
from proworksim import software_benchmark_scope_passive_leaf_v203_2_1_r3 as scope
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration


def prepare():
 if (scope.API_ROOT/'execution-started.json').exists():raise PermissionError('Leaf has already entered')
 parent=scope.parent.load(reference(scope.parent.PLAN_FILE));old=next(r for r in parent['rows'] if r['instance_id']==scope.TASK)
 row=copy.deepcopy(old);row.pop('configuration');row['slot_index']=2032307
 panel={'version':scope.VERSION,'rows':[row],'task_ids':[scope.TASK],'task_count':1,
  'parent_plan':reference(scope.parent.PLAN_FILE),'same_original_logical_attempt':True,
  'additional_model_attempts':0,'additional_cash_CNY':'0.00','existing_cash_cap_CNY':'150.00',
  'original_ledger':str(scope.LEDGER_FILE),'parent_engineering_gate_required':True,
  'CA_qualification_required':True,'parent_queue_modified':False}
 panel_ref=scope.retain(scope.PANEL_FILE,panel)
 original=scope.load(old['configuration'])
 config={**copy.deepcopy(original),**row,'version':'v203.2.1-original-Requests-first-model-config-r3'}
 row['configuration']=scope.retain(scope.BATCH_ROOT/'configs/2032307.json',config)
 cpu=scope.retain(scope.CPU_POOL_FILE,scope.parent.load(reference(scope.parent.CPU_POOL_FILE))) if scope.CPU_POOL_FILE!=scope.parent.CPU_POOL_FILE else reference(scope.CPU_POOL_FILE)
 resources={}
 for role in ('actor','controller','volume','score','delivery-score'):
  resources[f'{role}-2032307']=copy.deepcopy(parent['resources'][f'{role}-{old["slot_index"]}'])
 env={**copy.deepcopy(parent['environments'][scope.TASK]),'configuration':row['configuration']}
 inventory=scope.retain(scope.INVENTORY_FILE,{'version':scope.VERSION,'rows':[row],'panel':panel_ref,'generation':{},'scores':{},'deliveries':{}})
 plan={'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'panel':panel_ref,'matrix':panel_ref,
  'rows':[row],'generation_rows':[row],'host_cpu_pool':cpu,'inventory':inventory,
  'environments':{scope.TASK:env},'environment_sources':{scope.TASK:copy.deepcopy(parent['environment_sources'][scope.TASK])},
  'resources':resources,'resource_role_counts':dict(Counter(v['role'] for v in resources.values())),
  'constraints':scope.CONSTRAINTS,'diagnostics':[],'training':False,'model_calls_during_preparation':0,
  'parent_plan':reference(scope.parent.PLAN_FILE),'original_parent_row':old,
  'CA_qualification':scope.qualified_r3_ref(),'CA_result':reference(scope.CA_RESULT_FILE),
  'parent_engineering_gate_path':str(scope.PARENT_GATE_FILE),'must_wait_parent_gate':True,
  'same_existing_cash_ledger':str(scope.LEDGER_FILE),'additional_cash_CNY':'0.00',
  'new_logical_model_attempts':0,'parent_runtime_mutations':0,
  'dispatch_admission':declaration(scope.BATCH_ROOT),'generation_scoring_must_not_overlap':True}
 scope.validate_plan(plan)
 return {'plan':scope.retain(scope.PLAN_FILE,plan),'panel':panel_ref,'API_calls':0,'Docker_operations':0,
  'ledger_changes':0,'parent_gate_at_preparation':scope.gate_status(),
  'physical_index':2032307,'original_logical_slot_id':row['slot_id'],
  'CPU_lanes':{role:scope.cpu_set(role) for role in ('coordinator','actor','controller','grader')}}


if __name__=='__main__':print(json.dumps(prepare(),ensure_ascii=False))
