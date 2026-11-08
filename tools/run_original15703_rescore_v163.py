"""One original15703 code score; identical legal delivery reuses that result."""
import argparse
import json
from pathlib import Path
import shutil
from proworksim import software_benchmark_scope_v163 as scope
from proworksim import software_benchmark_grading_v163 as grading
from proworksim.software_benchmark_candidates_v054 import reference


def preflight():
 scope.require_grading_allowed('v163.run')
 prepared=scope.load(reference(scope.COORDINATOR_ROOT/'score-preparation.json'))
 worker=grading.factory();policy=scope.dispatch_view(scope.require_grading_allowed)
 ref=prepared['request'];request=scope.load(ref);folder=Path(request['directory'])
 claim=policy.claim_resource(scope.CODE_KEY,lane=0)
 scope.retain(folder/'capacity-claim.json',{'prepared_request':ref,'claim':claim})
 output=scope.ARTIFACT_ROOT/'actual-request-preflight-r1';output.mkdir(parents=True,exist_ok=True)
 try:
  execution=worker.scorer.resolve_execution_request(request);worker.scorer.validate_request(execution)
  result={'passed':True,'actual_resolve_execution_request':True,'actual_validate_request':True,
   'request':ref,'new_model_calls':0,'Docker_operations':0,'original_patch_unchanged':True}
 finally:
  policy.release_resource(claim,quiescent=True)
  for path in (folder/'capacity-claim.json',Path(claim['path']),Path(claim['path']).with_name(scope.CODE_KEY+'.released.json')):
   shutil.move(path,output/('capacity-admission.json' if path.name=='capacity-claim.json' else path.name))
 return scope.retain(output/'summary.json',result)


def release():
 scope.require_grading_allowed('v163.run')
 preflight=scope.load(reference(scope.ARTIFACT_ROOT/'actual-request-preflight-r1/summary.json'))
 if preflight.get('passed') is not True or scope.main_grader_claims():raise RuntimeError('Wait for actual main grading vacancy after passed preflight')
 return scope.retain(scope.RELEASE_FILE,{'approved':True,'plan':reference(scope.PLAN_FILE),
  'authority':reference(scope.AUTH_FILE),'task':scope.TASK,
  'coordination_basis':'root_confirmed_main_grader_slot_available',
  'main_grader_leases_observed':[],'scope_maximum_containers':2,'expected_actual_containers':1,
  'new_model_calls':0,'network_connections':0})


def run():
 scope.require_grading_allowed('v066.grader.create',instance_id=scope.TASK)
 prepared=scope.load(reference(scope.COORDINATOR_ROOT/'score-preparation.json'))
 worker=grading.factory();ref=prepared['request'];completed=worker.run_request(ref)
 quiet=worker.trustworthy_cleanup(ref);folder=Path(scope.load(ref)['directory'])
 receipt_ref=reference(folder/'receipt.json');receipt=scope.load(receipt_ref)
 if quiet is not True:raise RuntimeError('Owned supplemental grader cleanup is incomplete')
 if receipt.get('status')!='official_report' or type(receipt.get('resolved')) is not bool:
  return scope.retain(scope.COORDINATOR_ROOT/'result.json',{'status':'scoring_technical_unknown',
   'generation_result':reference(grading.RESULT_FILE),'score_receipt':receipt_ref,'completion':completed,
   'new_model_calls':0,'automatic_replay':False})
 result=scope.load(reference(grading.RESULT_FILE));config=scope.load(result['configuration'])
 delivery=grading.delivery_proof(result,config)
 same=scope.retain(scope.COORDINATOR_ROOT/'same-tree-delivery.json',{
  'version':grading.VERSION,'same_tree':True,'legal_delivery':delivery,'code_receipt':receipt_ref,
  'code_candidate':result['candidate_lock'],'delivery_candidate':result['delivery_candidate_lock'],
  'R_delivery':receipt['resolved'],'extra_scoring_container_created':False,'new_model_calls':0})
 return scope.retain(scope.COORDINATOR_ROOT/'result.json',{'version':grading.VERSION,'status':'scored_original_locked_candidate',
  'original_result':result['original_result'],'recovered_result':reference(grading.RESULT_FILE),
  'original_status':'technical_unknown','controller_result_fabricated':False,
  'observer_coverage_preserved':result['observer_coverage_preserved'],
  'code_receipt':receipt_ref,'R_code':receipt['resolved'],'R_delivery':receipt['resolved'],
  'same_tree_delivery':same,'scoring_containers':1,'new_model_calls':0,'network_connections':0,
  'quiescence':reference(folder/'quiescence.json'),'original_patch_changed':False})


if __name__=='__main__':
 parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
 group.add_argument('--preflight',action='store_true');group.add_argument('--release',action='store_true');group.add_argument('--execute',action='store_true')
 args=parser.parse_args();print(json.dumps(preflight() if args.preflight else release() if args.release else run(),ensure_ascii=False))
