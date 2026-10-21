"""Offline projection of one already paid A1; no imports of CUDA or model worker."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path('/data0/zhuxinrui/projects/ProWorkSim')
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from proworksim.software_benchmark_candidates_v054 import checked,reference,write_new
from proworksim.storage import json_bytes
stage=Path('/tmp/v054-interleave-reference-fix-r2')
p=stage/'tools/check_match_interleave_v054.py'
spec=importlib.util.spec_from_file_location('v054_reference_repair_control',p)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
base=ROOT/'runs/software-benchmark-v054/dynamic-pool-r3/devices/GPU-35ddcc29-b60c-a106-93e6-175ccf9abd0c/attempt-1'
folder=base/'handoff/synthetic-v054-interleave-baseline-a-r1'
response_path=folder/'A1-response.json';response=json.loads(response_path.read_text())
original_receipt=reference(base/'handoff/receipt.json')
original_response=reference(response_path)
native_ref=response['ledger']['calls'][-1]['response']
canonical_native=reference(native_ref['path'])
ledger_path=Path(native_ref['path']).parent/'ledger.json';ledger=json.loads(ledger_path.read_text())
permit_path=base/'preparation-permit.json';permit=json.loads(permit_path.read_text())
checks={}
def require(name,value):
 checks[name]=bool(value)
 assert value,name

require('same_native_path_and_original_sha',set(native_ref)=={'path','sha256'} and all(canonical_native[k]==v for k,v in native_ref.items()))
usage=module.accounted_usage(response,'MATCH')
require('settled_usage_available_before_projection',usage=={'prompt_tokens':432,'completion_tokens':3,'total_tokens':435} and ledger['known_actual_tokens']==ledger['complete_actual_tokens']==435 and ledger['attempts']==1 and ledger['inflight'] is None and ledger['uncertain_reserved_tokens']==0)
projected=module.projection(response,'MATCH')
require('actual_retained_A1_projection_complete',projected['output']['raw_generated_text']=='ALPHA<|im_end|>' and len(projected['token_trace']['input_ids'])==432 and len(projected['token_trace']['output_ids'])==len(projected['token_trace']['behavior_logprobs'])==3 and projected['output']['usage']==usage)
bad=copy.deepcopy(response);bad['ledger']['calls'][-1]['response']['sha256']='0'*64
try:module.projection(bad,'MATCH')
except ValueError as error:tampered='content changed' in str(error)
else:tampered=False
require('tampered_native_sha_rejected',tampered)
try:checked(native_ref)
except ValueError:generic_strict=True
else:generic_strict=False
require('generic_checked_not_relaxed',generic_strict)
require('original_r1_permit_builder_unchanged',json_bytes(module.preparation_permit(**permit['deployment']))==permit_path.read_bytes())
r2=module.preparation_permit(**permit['deployment'],run_revision='r2')
require('r2_new_four_ids_no_old_slot_reuse',not {s['slot_id'] for s in r2['sessions']} & {s['slot_id'] for s in permit['sessions']} and all(s['slot_id'].endswith('-r2') for s in r2['sessions']) and sum(s['maximum_generation_requests'] for s in r2['sessions'])==r2['maximum_generation_requests']==6)
require('r2_same_exact_request_plan_and_paired_seeds',r2['requests']==permit['requests'] and r2['execution_plan']==permit['execution_plan'] and [s['seed'] for s in r2['sessions']]==[s['seed'] for s in permit['sessions']])
turn_ref=response['interleave_evidence']['turn'];turn=json.loads(checked(turn_ref).read_text())
require('original_turn_complete_and_parked_rng_restored',turn['original_operation']=='match_complete' and turn['shared_parked_rng_restored'] and turn['cache_absent'] and turn['error'] is None)
projected['rng']={key:turn[key] for key in ('rng_before_sha256','rng_after_sha256')}
projected['provenance']={'original_response':original_response,'native_original_reference':native_ref,'native_verified_reference':canonical_native,'original_owner_ledger':reference(ledger_path),'original_turn':turn_ref,'new_model_calls':0,'scope':'Recovered original baseline A1 evidence only; not a passed six-request control and not resumed in-memory RNG'}
projection_ref=write_new(base/'handoff/A1-recovered-projection-r1.json',projected)
require('original_failure_response_and_native_unchanged',reference(base/'handoff/receipt.json')==original_receipt and reference(response_path)==original_response and reference(native_ref['path'])==canonical_native)
sidecar={'version':'v054-interleave-control-postprocessing-diagnosis-r1','classification':'checker_reference_schema_mismatch_after_settled_generation','original_failed_receipt':original_receipt,'original_A1_response':original_response,'authoritative_owner_ledger':reference(ledger_path),'original_native_reference':native_ref,'verified_native_reference':canonical_native,'only_reference_schema_difference':['bytes'],'native_bytes_match_original_declared_sha256':True,'recovered_A1_projection':projection_ref,'actual_original_model_calls':1,'known_prompt_tokens':432,'known_completion_tokens':3,'known_actual_tokens':435,'unsettled_model_requests':0,'original_helper_reported_known_tokens':0,'original_helper_reported_unsettled_requests':1,'original_helper_receipt_retained_unchanged':True,'new_model_calls':0,'formal_slots_claimed':0,'qualification_status':'incomplete_one_of_six_requests_only','in_memory_resume_supported':False,'resume_reason':'Existing manager is poisoned with a closing original session; no unpoison/host-transfer/RNG-import API. SIGCONT does not repair those state gates. RNG hashes are not importable states.','repair_checker_source':reference(p)}
sidecar_ref=write_new(base/'handoff/postprocessing-diagnosis-r1.json',sidecar)
report={'version':'v054-match-reference-schema-repair-cpu-control-r1','passed':all(checks.values()),'checks':checks,'source':reference(p),'actual_retained_response':original_response,'sidecar':sidecar_ref,'recovered_projection':projection_ref,'model_calls':0,'GPU_queries':0,'GPU_loads':0,'source_model_generations_replayed':0,'original_model_calls_preserved':1,'original_known_actual_tokens':435,'original_unsettled_requests':0,'scope':'One retained A1 projection plus forged-SHA rejection and pure permit revision checks; no new six-request execution'}
ref=write_new(stage/'control/receipt.json',report)
print(json.dumps({'passed':report['passed'],'checks':checks,'receipt':ref,'diagnostic_sidecar':sidecar_ref,'recovered_A1_projection':projection_ref},ensure_ascii=False,indent=2))
