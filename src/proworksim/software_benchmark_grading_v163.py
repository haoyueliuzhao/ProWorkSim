"""Score only15703's exact administratively recovered, already locked tree.

No controller-result.json is fabricated and no coverage flag is upgraded. The
old raw result remains technical_unknown. This private scorer consumes the
separately verified original candidate and legal same-tree delivery evidence.
"""
from __future__ import annotations
from functools import lru_cache
import copy
import inspect
import json
from pathlib import Path
import sqlite3
from types import FunctionType

from . import software_benchmark_scope_v163 as scope
from . import software_benchmark_grading_v105 as base
from . import software_benchmark_scorer_v066 as original
from . import software_benchmark_grading_v131 as cleanup_binding
from . import software_benchmark_project_closure_v157 as closure
from .software_benchmark_candidates_v054 import reference,checked
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function

VERSION='v163-original15703-locked-candidate-official-rescore-r1'
REUSE_VERSION='v163-original15703-unchanged-environment-proof-r1'
MODULE=__name__
RECOVERY=scope.ROOT/'artifacts/software-benchmark-v163/locked-candidate-recovery-r2'
RESULT_FILE=RECOVERY/'recovered-result.json'
EXPECTED_RESULT_SHA='b0ded72fc99f22882a51222c3de1b2cabf26d689c7a42169995ea0d01dc856f1'
EXPECTED_AUDIT_SHA='9da9cb6190d0d3974adef7b03324cd23a2e86a259bd8ab19fd8bb2a76cbe575e'
EXPECTED_ARCHIVE_SHA='c80f7e7a5421565484691ddca46de7867efb2eca0c62b2629b5879b83d58f659'
EXPECTED_TREE='13cdc997eef7a73068608a4655925d39b8d8c9bfa6b06a5ee587cd0f95250d11'
EXPECTED_PATCH='1b0314d64b21928c6299a2ceee24891281764a43617f4ad58ad3e1091624c846'
ORIGINAL_EPISODE=scope.ROOT/'runs/software-benchmark-v157/communication-pilot24-r1/episodes/15703'
SOURCE_PLAN=scope.ROOT/'runs/software-benchmark-v157/communication-pilot24-r1/execution-plan-r2.json'
SOURCE_QUAL=scope.ROOT/'runs/software-benchmark-v157/communication-pilot24-r1/grading-coordinator-r3/qualifications/sympy__sympy-17318.json'
SOURCE_MANIFEST=scope.ROOT/'runs/software-benchmark-v157/communication-pilot24-r1/grading-coordinator-r3/scorer-manifest.json'
_namespace=clone_namespace(base,scope=scope,VERSION=VERSION,REUSE_VERSION=REUSE_VERSION,MODULE=MODULE,__file__=__file__)
_parent_scorer=_namespace['scorer'];_parent_host=_namespace['host']


def audit_original(config):
 result_ref=reference(RESULT_FILE)
 if result_ref['sha256']!=EXPECTED_RESULT_SHA:raise ValueError('Only the exact approved15703 recovered result is admitted')
 result=scope.load(result_ref);audit_ref=result['administrative_closure_audit']
 if audit_ref['sha256']!=EXPECTED_AUDIT_SHA:raise ValueError('The original administrative audit changed')
 audit=scope.load(audit_ref);archive_ref=audit['archive_verification']
 if archive_ref['sha256']!=EXPECTED_ARCHIVE_SHA:raise ValueError('The previously completed archive verification changed')
 archive=scope.load(archive_ref);raw=scope.load(result['original_result'])
 if (result.get('slot_id')!=scope.SLOT or result.get('instance_id')!=scope.TASK
     or result.get('configuration')!=reference(ORIGINAL_EPISODE.parents[1]/'configs/15703.json')
     or config!=scope.load(result['configuration']) or result.get('group_id')!='C1'
     or result.get('organization_id')!='REVIEW2' or result.get('original_status')!='technical_unknown'
     or result.get('controller_result_reconstructed') is not False
     or 'controller_result' in result or 'controller_exit_code' in result
     or raw.get('status')!='technical_unknown' or raw.get('error',{}).get('type')!='FileNotFoundError'
     or (ORIGINAL_EPISODE/'controller-output/controller-result.json').exists()
     or audit.get('coverage_reconstructed_or_invented') is not False
     or audit.get('unique_original_candidate_preserved') is not True
     or audit.get('actor_interrupted_tree_selected_as_candidate') is not False
     or audit.get('model_calls_added')!=0 or audit.get('candidate_content_changed') is not False
     or result.get('model_calls_added')!=0 or result.get('known_actual_tokens')!=2819481
     or result.get('candidate_lock')!=audit.get('candidate_lock')
     or result.get('delivery_candidate_lock')!=audit.get('delivery_candidate_lock')
     or archive.get('full_archive_verified') is not True or archive.get('candidate_reselected') is not False):
  raise ValueError('The exact original closure/lock/audit boundary was altered')
 boundary=scope.load(audit['managed_boundary']);observer=scope.load(audit['observer'])
 if (boundary.get('status')!='bounded_work_closed' or boundary.get('continuation') is not False
     or boundary.get('execution_integrity_failure') is not None
     or observer.get('completion_status')!='normal' or observer.get('runtime_measurement_errors')!=[]
     or observer.get('coverage',{}).get('presentations') is not True
     or observer.get('coverage')!=audit['observer_original_coverage']
     or result.get('observer_coverage_preserved')!=observer['coverage']):
  raise ValueError('Original managed/observer closure is not the audited one; missing coverage stays missing')
 quiet=scope.load(result['quiescence']);writers=scope.load(result['writer_quiescence'])
 if (quiet.get('quiescent') is not True or quiet.get('cleanup_errors')!=[]
     or quiet.get('create_result_unknown') is not False or quiet.get('retained_objects')!=[]
     or writers.get('all_quiet') is not True or writers.get('errors')!=[]
     or {r['role'] for r in writers['writers']}!={'actor','controller'}
     or any(r['state'].get('Running') is not False or r['state'].get('Pid')!=0 for r in writers['writers'])):
  raise ValueError('Original writers or containers have not closed')
 selected=archive['selected']
 for ref in (audit['managed_boundary'],audit['observer'],result['delivery_evidence'],
             result['delivery_snapshot'],result['project_baseline_snapshot'],audit['actor_sync_response']):
  if ref not in selected.values():raise ValueError('Audited endpoint is absent from the verified original archive index')
  checked(ref)
 actor=audit['actor_export_same_tree'];sync=scope.load(audit['actor_sync_response'])['result']
 if (actor.get('same_locked_candidate_tree') is not True or actor.get('source_entries_verified')!=1686
     or actor.get('actor_worktree_selected_as_new_candidate') is not False
     or sync.get('tree_sha256')!=EXPECTED_TREE or sync.get('terminal_locked') is not True
     or sync.get('exact_complete_tree') is not True or sync.get('model_can_resume') is not False):
  raise ValueError('Original synchronized actor is not the already locked complete tree')
 ledger=Path(audit['usage']['source_ledger'])
 with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro',uri=True) as db:
  rows=db.execute('SELECT status,usage_json FROM requests WHERE slot_id=?',(scope.SLOT,)).fetchall()
 if (len(rows)!=53 or any(status!='settled' or not usage for status,usage in rows)
     or sum(json.loads(usage)['total_tokens'] for _,usage in rows)!=2819481):
  raise ValueError('The original53 physical requests must remain fully settled; no new original-slot calls')
 code=original._locked_candidate(result['candidate_lock'],config,endpoint='terminal_code')
 delivery=original._locked_candidate(result['delivery_candidate_lock'],config,endpoint='last_legal_delivery')
 if (code['tree_sha256']!=EXPECTED_TREE or delivery['tree_sha256']!=EXPECTED_TREE
     or code['patch_receipt']['patch']['sha256']!=EXPECTED_PATCH
     or code.get('administrative_relocation_only') is not True
     or code['patch_receipt'].get('patch_regenerated') is not False
     or any(lock.get('model_calls')!=0 or lock.get('grading_calls')!=0 for lock in (code,delivery))):
  raise ValueError('Never regenerate/reselect the approved original patch')
 for lock in (code,delivery):
  if lock['candidate'] not in selected.values() or lock['patch_receipt']['patch'] not in selected.values():
   raise ValueError('The native lock does not point to original verified archive bytes')
 return result,code,delivery,{'administrative_audit':audit_ref,'archive_verification':archive_ref,
  'original_generation_status':'technical_unknown','missing_controller_result_preserved':True,
  'observer_coverage_preserved':observer['coverage'],'new_model_calls':0,'original_settled_requests':53,
  'original_actual_tokens':2819481,'archive_not_rescanned_or_reexported':True}


def delivery_proof(result,config):
 verified,code,delivery,audit=audit_original(config)
 if result!=verified:raise ValueError('Delivery validation cannot use another recovered result')
 evidence=scope.load(result['delivery_evidence']);snapshot=scope.load(result['delivery_snapshot'])
 baseline=scope.load(result['project_baseline_snapshot']);candidate=scope.load(code['candidate'])
 proof=closure.validate_delivery_evidence(evidence,snapshot,baseline)
 if (proof!=result['delivery_validation'] or proof.get('submitted') is not True or proof.get('same_tree') is not True
     or proof.get('organization_submission_verified') is not True
     or proof.get('managed_tree_sha256')!=EXPECTED_TREE
     or snapshot['candidate']['files']!=candidate['files']
     or snapshot['candidate']['entry_metadata']!=candidate['entry_metadata']
     or result['project_baseline_snapshot']!=code['baseline']):
  raise ValueError('Same-tree reuse needs the exact legitimate accepted REVIEW2 delivery')
 return {**proof,'native_delivery_tree_sha256':delivery['tree_sha256'],'original_administrative_audit':audit}


def validate_source_qualification(config):
 from . import software_benchmark_grading_v157 as historical
 from . import software_benchmark_scope_v157 as historical_scope
 manifest=scope.load(reference(SOURCE_MANIFEST))
 scorer=historical.scorer(historical_scope.dispatch_view(historical_scope.require_grading_allowed),
                         manifest_provider=lambda:manifest)
 value=scorer.validate_qualification(reference(SOURCE_QUAL),config,reference(SOURCE_PLAN))
 if value.get('passed') is not True:raise ValueError('Original exact Sympy gold/empty controls do not qualify')
 return value


def scorer(policy,*,manifest_provider=None):
 value=_parent_scorer(policy,manifest_provider=manifest_provider);ns=value.score_request.__globals__
 environment=ns['environment'];environment.TASKS=environment.TLS_TASKS=environment.OFFLINE_TASKS=frozenset()
 def fields(task):
  if task!=scope.TASK:raise ValueError('Foreign task')
  return {'environment_revision':None,'network_resolution':None}
 def validate_environment(request,task):
  if any(request.get(k)!=v for k,v in fields(task).items()):raise ValueError('Pure Sympy scoring has no network provider')
 environment.request_fields=fields;environment.validate_request=validate_environment
 environment.provider=lambda task:None;environment.capabilities=lambda task:[]
 def generation(request,config,plan):
  if request.get('generation_result')!=reference(RESULT_FILE):raise ValueError('Foreign recovered candidate record')
  row=plan['rows'][0]
  if request['slot_id']!=scope.SLOT or row['configuration']!=reference(Path(config_path:=request['configuration']['path'])):
   raise ValueError('Original slot/configuration identity changed')
  result,_,_,_=audit_original(config)
  return row,result,ORIGINAL_EPISODE
 def qualification(ref,config,plan_ref):
  if ref!=reference(SOURCE_QUAL) or plan_ref!=reference(scope.PLAN_FILE):raise ValueError('Foreign original environment qualification')
  old=validate_source_qualification(config)
  prior=scope.load(reference(SOURCE_MANIFEST));current=ns['installation_manifest']()
  for key in ('parent','archive_adapter','limits','cap_add','cap_drop','no_new_privileges',
              'official_tests_and_scoring_rules_changed','host_namespace_mount_or_daemon_operations'):
   if current.get(key)!=prior.get(key):raise ValueError('The actual official test/scorer environment changed: '+key)
  return old
 def candidate(request,resource,config,plan):
  _,result,_=generation(request,config,plan)
  endpoint='last_legal_delivery' if resource['role']=='delivery_score' else 'terminal_code'
  field='delivery_candidate_lock' if resource['role']=='delivery_score' else 'candidate_lock'
  if (request.get('candidate_lock')!=result[field] or resource.get('slot_id')!=scope.SLOT
      or request.get('group_id')!='C1' or request.get('organization_id')!='REVIEW2'):
   raise ValueError('Only the audited original endpoint and communication condition may be scored')
  lock=original._locked_candidate(request[field if field in request else 'candidate_lock'],config,endpoint=endpoint)
  if lock!=scope.load(result[field]):raise ValueError('The relocated lock changed')
  if resource['role']=='delivery_score':delivery_proof(result,config)
  qualification(request['qualification'],config,request['plan'])
  if config['scorer_request_base']['image']['image_id']!=resource['image_id']:raise ValueError('Pinned score image changed')
  return lock
 ns.update(_generation_result=generation,validate_project_delivery=lambda result,config,folder:delivery_proof(result,config),
           validate_candidate_request=candidate,validate_qualification=qualification,validate_delivery_evidence=closure.validate_delivery_evidence)
 for name in ('validate_capacity_claim','validate_request'):
  source=inspect.getsource(getattr(original,name))
  if source.count('range(4)')!=1:raise ValueError('Original four-lane guard changed')
  compiled={};exec(compile(source.replace('range(4)','range(1)'),__file__+':one-'+name,'exec'),ns,compiled)
  ns[name]=compiled[name]
 inherited=ns['installation_manifest']
 def manifest():
  existing=inherited()
  if manifest_provider is not None:return existing
  return {**existing,'original_candidate_recovery_adapter':reference(__file__),
      'original_recovery_result':reference(RESULT_FILE),'administrative_closure_audit':reference(RECOVERY/'administrative-closure-audit.json'),
      'recovery_helper_unchanged':reference(scope.ROOT/'src/proworksim/software_benchmark_artifact_recovery_v163.py'),
      'managed_delivery_validator':reference(closure.__file__),'missing_controller_result_not_fabricated':True,
      'official_scoring_or_tests_changed':False,'model_replayed':False,'network_mode':'none','only_original_slot':scope.SLOT}
 ns['installation_manifest']=manifest
 ns['cleanup']=clone_function(cleanup_binding.bind_physical_cleanup,{**cleanup_binding.bind_physical_cleanup.__globals__,'VERSION':VERSION})(ns)
 for name in ('_generation_result','validate_project_delivery','validate_candidate_request','validate_qualification',
              'validate_delivery_evidence','validate_capacity_claim','validate_request','installation_manifest','cleanup'):
  setattr(value,name,ns[name])
 return value


def prepare_original_request():
 plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)));row=plan['rows'][0]
 config=scope.load(row['configuration']);result,code,delivery,audit=audit_original(config)
 legal=delivery_proof(result,config);validate_source_qualification(config)
 scoring=scorer(scope.dispatch_view(scope.require_grading_allowed))
 manifest=scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json',scoring.installation_manifest())
 request={'version':VERSION,'resource_key':scope.CODE_KEY,'instance_id':scope.TASK,'slot_id':scope.SLOT,
  'plan':reference(scope.PLAN_FILE),'configuration':row['configuration'],'generation_result':reference(RESULT_FILE),
  'candidate_lock':result['candidate_lock'],'qualification':reference(SOURCE_QUAL),
  'measurement_kind':row['measurement_kind'],'source_slot_id':row['source_slot_id'],
  'group_id':'C1','organization_id':'REVIEW2','limits':scoring.LIMITS,'scorer_manifest':manifest,
  'cpuset_cpus':None,'directory':str(scope.GRADING_ROOT/scope.CODE_KEY),
  'environment_revision':None,'network_resolution':None}
 ref=scope.retain(scope.GRADING_ROOT/scope.CODE_KEY/'request.json',request)
 return scope.retain(scope.COORDINATOR_ROOT/'score-preparation.json',{'version':VERSION,'request':ref,
  'audit':audit,'delivery':legal,'same_tree':True,'no_delivery_container_needed':True,
  'candidate_patch':code['patch_receipt']['patch'],'new_model_calls':0,'Docker_operations':0})


_namespace.update(scorer=scorer)
_namespace['cold_manifest']=lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__,_namespace))
_namespace['Grading']=type('Grading',(base.Grading,),{name:clone_function(value,_namespace)
 for name,value in vars(base.Grading).items() if isinstance(value,FunctionType)})
globals().update({key:value for key,value in _namespace.items() if not key.startswith('__')})
def main_original():
 import argparse
 parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
 group.add_argument('--manifest',action='store_true');group.add_argument('--prepare-original',action='store_true')
 group.add_argument('--request',type=Path);group.add_argument('--validate-request',type=Path)
 args=parser.parse_args()
 if args.manifest:value=scorer(scope.dispatch_view(scope.require_grading_allowed)).installation_manifest()
 elif args.prepare_original:value=prepare_original_request()
 else:
  request=json.loads((args.request or args.validate_request).read_bytes())
  value=score_request(request,validate_only=args.validate_request is not None)
  if args.request:value={key:value[key] for key in ('resource_key','status','resolved')}
 print(json.dumps(value,ensure_ascii=False))

if __name__=='__main__':main_original()
