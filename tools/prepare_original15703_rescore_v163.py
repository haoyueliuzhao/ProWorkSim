"""Freeze the exact recovered15703 score scope; no model/Docker/network calls."""
import argparse
import json
from proworksim import software_benchmark_scope_v163 as scope
from proworksim import software_benchmark_grading_v163 as grading
from proworksim.software_benchmark_candidates_v054 import reference


def plan():
 original=scope.load(reference(grading.SOURCE_PLAN));row=next(r for r in original['rows'] if r['slot_index']==15703)
 result=scope.load(reference(grading.RESULT_FILE));config=scope.load(row['configuration'])
 _,code,_,audit=grading.audit_original(config)
 resources={scope.CODE_KEY:{'role':'score','slot_id':scope.SLOT,'instance_id':scope.TASK,
  'image_id':config['scorer_request_base']['image']['image_id'],'endpoint':'code','group_id':'C1','organization_id':'REVIEW2'},
  scope.DELIVERY_KEY:{'role':'delivery_score','slot_id':scope.SLOT,'instance_id':scope.TASK,
  'image_id':config['scorer_request_base']['image']['image_id'],'endpoint':'delivery','group_id':'C1','organization_id':'REVIEW2',
  'skip_when_same_tree':True}}
 value={'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'origin_plan':reference(grading.SOURCE_PLAN),
  'rows':[row],'environments':{scope.TASK:original['environments'][scope.TASK]},'resources':resources,
  'generation_result':reference(grading.RESULT_FILE),'administrative_closure_audit':result['administrative_closure_audit'],
  'original_qualification':reference(grading.SOURCE_QUAL),'original_control_manifest':reference(grading.SOURCE_MANIFEST),
  'candidate_lock':result['candidate_lock'],'candidate_patch':code['patch_receipt']['patch'],
  'same_tree_delivery':True,'code_score_reused_only_for_own_identical_delivery':True,
  'host_cpu_pool':reference(scope.SOURCE_CPU_POOL_FILE),'constraints':scope.CONSTRAINTS,
  'new_model_calls':0,'new_export_or_candidate_selection':False,'controller_result_fabricated':False,
  'observer_coverage_preserved':result['observer_coverage_preserved']}
 scope.validate_plan(value)
 ref=scope.retain(scope.PLAN_FILE,value)
 proposal={'version':scope.VERSION,'plan':ref,'generation_result':reference(grading.RESULT_FILE),
  'original_candidate_patch':code['patch_receipt']['patch'],'maximum_score_containers':2,
  'expected_actual_score_containers':1,'same_tree_delivery_reuse':True,'concurrency':1,
  'grader_CPU':4,'grader_memory_GiB':16,'host_scorer_memory_GiB':4,'CPU_set':scope.cpu_set('grader',0),
  'network_mode':'none','cap_add':[],'cap_drop':['ALL'],'host_bind_mounts':False,'GPU_operations':0,
  'new_model_calls':0,'network_connections':0,'shared_host_configuration_changes':0,
  'preserve_missing_controller_result_and_partial_coverage':True,
  'execution_requires_root_coordination_release':True,'main_grader_leases_must_be_empty':True,
  'no_old_score_cache_reused':True,'old_results_unchanged':True,'read_only_audit':audit}
 return {'plan':ref,'proposal':scope.retain(scope.PROPOSAL_FILE,proposal)}


def sources():
 previous=scope.ROOT/'artifacts/software-benchmark-v157/environment-authorization-r3/sources.json'
 paths={r['path'] for r in scope.load(reference(previous))['files']}
 paths.update(str((scope.ROOT/name).resolve()) for name in (
  'src/proworksim/software_benchmark_scope_v163.py','src/proworksim/software_benchmark_grading_v163.py',
  'src/proworksim/software_benchmark_artifact_recovery_v163.py','tools/prepare_original15703_rescore_v163.py',
  'tools/run_original15703_rescore_v163.py'))
 return scope.retain(scope.SOURCE_FILE,{'version':'v163-original15703-scorer-source-closure-r1',
  'files':[reference(p) for p in sorted(paths)],'model_source_changed':False})


def authority():
 source=sources();prepared=scope.load(reference(scope.COORDINATOR_ROOT/'score-preparation.json'))
 return scope.retain(scope.AUTH_FILE,{'version':'v163-original15703-rescore-authority-r1','status':'approved',
  'scope':reference(scope.__file__),'plan':reference(scope.PLAN_FILE),'source_index':source,
  'standing_policy':reference(scope.STANDING_POLICY_FILE),'proposal':reference(scope.PROPOSAL_FILE),
  'resource_keys':[scope.CODE_KEY,scope.DELIVERY_KEY],'constraints':scope.CONSTRAINTS,
  'request':prepared['request'],'maximum_score_containers':2,'new_model_calls':0,
  'shared_host_configuration_changes':0,'network_connections':0,'host_bind_mounts':False,
  'candidate_content_changed':False,'actual_execution_requires_separate_coordination_release':True,
  'root_instruction':'Score exact original15703 after cold preflight and confirmation main grader leases are empty; no new model'} )


if __name__=='__main__':
 parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
 group.add_argument('--plan',action='store_true');group.add_argument('--grant',action='store_true')
 args=parser.parse_args();print(json.dumps(plan() if args.plan else authority(),ensure_ascii=False))
