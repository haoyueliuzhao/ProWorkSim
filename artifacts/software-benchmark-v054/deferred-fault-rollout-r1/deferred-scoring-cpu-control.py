"""One CPU control of frozen identity, terminal gate and no-replay bookkeeping."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path('/data0/zhuxinrui/projects/ProWorkSim')
STAGE=Path('/tmp/v054-deferred-scoring-r1')
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from proworksim.software_benchmark_candidates_v054 import reference,write_new
p=STAGE/'src/proworksim/software_benchmark_deferred_scoring_v054.py'
spec=importlib.util.spec_from_file_location('proworksim.software_benchmark_deferred_scoring_cpu_control',p)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.ROOT=ROOT
checks={}
def require(name,value):checks[name]=bool(value);assert value,name
def rejected(callback):
 try:callback()
 except ValueError:return True
 return False
out=STAGE/'control/fixtures';out.mkdir(exist_ok=False)
request_path=ROOT/'runs/software-benchmark-v054/formal-queue-r1/slots/93/preclaim-1/episode/official-code-request.json'
request=json.loads(request_path.read_text());before=reference(request_path)
retry=module.make_retry_request(request);module.validate_retry_request(request,retry)
require('only_attempt_changes',retry['attempt']==2 and {k:v for k,v in retry.items() if k!='attempt'}=={k:v for k,v in request.items() if k!='attempt'})
require('same_1800_seconds_and_all_original_resources',retry['limits']==request['limits'] and retry['limits']['timeout_seconds']==1800)
for name,key,value in [('timeout','limits',{**retry['limits'],'timeout_seconds':3600}),('candidate','candidate_tree_sha256','0'*64),('patch','patch',{**retry['patch'],'sha256':'0'*64})]:
 bad=copy.deepcopy(retry);bad[key]=value
 require(name+'_mutation_rejected',rejected(lambda bad=bad:module.validate_retry_request(request,bad)))
datasets={};old_identity,old_run=module.expected_identity(request,datasets)
new_identity,new_run=module.expected_identity(retry,datasets)
original_identity=json.loads((Path(request['trusted_output_root'])/old_run/'identity.json').read_text())
require('original_r5_pure_identity_matches_actual_slot93',old_identity==original_identity and old_run=='v054-REF-code-b6435f5902aff80193beb74f9d12d239e8862dc3')
require('retry_runid_distinct_without_adapter_change',new_run!=old_run and {k:v for k,v in new_identity.items() if k!='attempt'}=={k:v for k,v in old_identity.items() if k!='attempt'})
require('existing_timeout_not_misclassified_as_report',module.existing_report(request,old_identity,old_run) is None)
# An immutable intent survives a coordinator interruption. It cannot execute twice.
folder=out/'once';folder.mkdir()
module.mark_started(folder,{'synthetic':True})
require('second_attempt_intent_rejected',rejected(lambda:module.mark_started(folder,{'synthetic':True})))
item={'exception_id':'synthetic-score-case','slot':{'slot_id':'synthetic-slot'},'domain':'scoring','endpoint':'code','original_request':reference(request_path)}
jobfolder=out/'pass/exceptions'/item['exception_id'];jobfolder.mkdir(parents=True)
module.mark_started(jobfolder,{'original_request':reference(request_path),'retry_run_id':new_run,'synthetic_control':True})
with patch.object(module.subprocess,'Popen',side_effect=AssertionError('No scorer may be launched by this control')),patch.object(module,'grader_lease',side_effect=AssertionError('No production lease touched')):
 result=module.process_exception(item,out/'pass',datasets=datasets)
require('interrupted_retry_never_replayed',result['status']=='unresolved' and result['additional_scoring_attempts']==1 and 'never replay' in result['reason'])
# A genuine prior report may be recovered; status/resource/identity mismatches never qualify.
fake=copy.deepcopy(request);fake['trusted_output_root']=str(out/'synthetic-official')
reportfolder=Path(fake['trusted_output_root'])/old_run;reportfolder.mkdir(parents=True)
from proworksim.software_benchmark_scorer_v054 import canonical,sha256
(reportfolder/'identity.json').write_bytes(canonical(old_identity))
(reportfolder/'receipt.json').write_bytes(canonical({'status':'official_report','resolved':False,'preparation_only':False,'actor_feedback':False,'run_id':old_run,'identity_sha256':sha256(canonical(old_identity))}))
require('existing_bound_report_recovered_without_retry',module.existing_report(fake,old_identity,old_run)['resolved'] is False)
changed=copy.deepcopy(old_identity);changed['attempt']=2
require('wrong_identity_report_rejected',rejected(lambda:module.existing_report(fake,changed,old_run)))
# Full planned inventory metadata, no real claims/processes: only terminal validation.
job=json.loads((ROOT/'runs/software-benchmark-v054/formal-queue-r1/jobs/93/score-code/job.json').read_text())
bindings=module.read_ref(job['bindings']);slots=module.read_ref(bindings['slots'])['slots']
state={'planned_slots':1500,'active_generation':0,'active_graders':0,'rows':[{'slot':slot,'generation':{'status':'closed'},'scores':{'code':{'status':'official_report'}}} for slot in slots]}
state_ref=write_new(out/'synthetic-primary.json',state)
policy_ref=write_new(out/'synthetic-overlay-policy.json',{'deferred_scoring':module.RETRY_POLICY})
marker={'version':module.TERMINAL_VERSION,'status':'primary_inventory_finished_with_deferred_exceptions','planned_slots':1500,'active_generation':0,'active_graders':0,'primary_only':True,'no_generation_retry':True,'queue_state_snapshot':state_ref,'overlay_policy':policy_ref,'bindings':job['bindings']}
require('complete_primary_inventory_gate_accepts',len(module.validate_primary(marker)['rows'])==1500)
badstate=copy.deepcopy(state);badstate['rows'][0]['generation']['status']='pending'
badref=write_new(out/'pending-primary.json',badstate)
require('pending_primary_rejected',rejected(lambda:module.validate_primary({**marker,'queue_state_snapshot':badref})))
require('live_primary_rejected',rejected(lambda:module.validate_primary({**marker,'active_generation':1})))
badstate=copy.deepcopy(state);badstate['rows'][0]['slot']['seed']+=1
badref=write_new(out/'changed-seed-primary.json',badstate)
require('changed_seed_or_task_rejected',rejected(lambda:module.validate_primary({**marker,'queue_state_snapshot':badref})))
# Uncertain billed reservations are not mislabeled as actual known token usage.
controller=write_new(out/'synthetic-accounting.json',{'ledger':{'charged_tokens':103,'held_tokens':0,'records':{'a':{'charge':{'usage_status':'reported_actual_trace','reported_usage':{'total_tokens':3},'charged_tokens':3}},'b':{'charge':{'usage_status':'uncertain_attempt_charged_reservation','reported_usage':None,'charged_tokens':100}}}}})
cost=module.billing({'generation':{'controller_result':controller}})
require('uncertain_billed_reservation_not_called_known_usage',cost['known_actual_tokens']==3 and cost['complete_actual_tokens'] is None and cost['actual_usage_unknown'] and cost['billed_tokens_including_uncertain_reservations']==103)
# Original real exception row appears once despite duplicate audit events.
current,_=module.read_snapshot(ROOT/'runs/software-benchmark-v054/formal-queue-r1/state.json')
row=next(row for row in current['rows'] if row['slot']['slot_index']==93)
small={'planned_slots':1500,'rows':[row],'deferred_exceptions':[{'slot_id':row['slot']['slot_id'],'endpoint':'code'},{'slot_id':row['slot']['slot_id'],'endpoint':'code'}]}
inventory=module.collect_inventory(small,{'synthetic_snapshot':True})
require('one_scoring_exception_per_slot_endpoint',len([r for r in inventory['exceptions'] if r['domain']=='scoring' and r['endpoint']=='code'])==1)
require('unknown_score_original_attempt_resources_billing_retained',inventory['exceptions'][0]['original_attempt']==1 and inventory['exceptions'][0]['frozen_resources']==request['limits'] and inventory['exceptions'][0]['original_run_id']==old_run and inventory['exceptions'][0]['billing']['reference'] is not None)
require('original_request_unchanged',before==reference(request_path))
report={'version':'v054-deferred-scoring-cpu-control-r1','passed':all(checks.values()),'checks':checks,'source':reference(p),'actual_original_identity':reference(Path(request['trusted_output_root'])/old_run/'identity.json'),'original_run_id':old_run,'predicted_retry_run_id':new_run,'retry_request_not_submitted':True,'model_calls':0,'scorer_invocations':0,'GPU_queries':0,'formal_slots_claimed':0,'production_files_modified':False}
ref=write_new(STAGE/'control/receipt.json',report)
print(json.dumps({'passed':report['passed'],'checks':checks,'predicted_retry_run_id':new_run,'receipt':ref},ensure_ascii=False,indent=2))
