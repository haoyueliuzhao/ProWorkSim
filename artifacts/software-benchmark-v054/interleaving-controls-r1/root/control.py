"""One CPU-only root integration control: real budget/deadline, programmed transport."""
from __future__ import annotations

import ast
from contextlib import contextmanager
import copy
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace
from unittest.mock import patch

REPO=Path('/data0/zhuxinrui/projects/ProWorkSim')
STAGE=Path('/tmp/v054-interleave-root-r1')
OWNER=Path('/tmp/v054-interleave-mp-r1')
OUTPUT=STAGE/'control'
sys.path.insert(0,str(REPO/'src'))
import proworksim
proworksim.__path__[:0]=[str(STAGE/'src/proworksim'),str(OWNER/'src/proworksim')]
transport=importlib.import_module('proworksim.software_benchmark_interleaved_transport_v054')
manager=importlib.import_module('proworksim.software_benchmark_interleaved_owner_v054')
queue=importlib.import_module('proworksim.software_benchmark_queue_v054')
from proworksim.software_calibration_collector_v051 import SingleMemberBudget
from proworksim.software_organization_runtime_v047 import DispatchDeadline,NativeDispatchGate,AdministrativeSoftDeadline
from proworksim.software_benchmark_match_v054 import CONTRACT
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import atomic_write,json_bytes

spec=importlib.util.spec_from_file_location('v054_migration_cpu_control',STAGE/'tools/resume_formal_preclaim_v054.py')
migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
checks={};cases={};failures={}
source_paths=[Path(transport.__file__),Path(manager.__file__),Path(queue.__file__),
 STAGE/'src/proworksim/software_benchmark_runner_transport_v054.py',
 STAGE/'tools/run_benchmark_controller_v054.py',STAGE/'tools/resume_formal_preclaim_v054.py',
 REPO/'src/proworksim/software_calibration_collector_v051.py',
 REPO/'src/proworksim/software_organization_runtime_v047.py',REPO/'src/proworksim/team_budget_v033.py',
 REPO/'src/proworksim/stage_budget_v047.py']
sources_before=[reference(p) for p in source_paths]
def require(name,value):
 checks[name]=bool(value)
 if not value: raise AssertionError(name)
def run(name,callback):
 try: cases[name]=callback()
 except BaseException as error:
  failures[name]={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()}
def reject(callback):
 try: callback()
 except ValueError:return True
 return False

class Clock:
 def __init__(self):self.value=1000.
 def __call__(self):return self.value
class Recorder:
 def __init__(self):self.rows=[]
 def record(self,kind,payload,**kwargs):self.rows.append({'kind':kind,'payload':copy.deepcopy(payload),**kwargs})
class Worker:
 def __init__(self,events,budget):self.events=events;self.budget=budget;self.pending=True;self.attempts=0
 def confirm_native_dispatch(self,call_id):
  assert self.pending and self.budget.snapshot()['records'][call_id]['dispatch_started']
  self.pending=False;self.attempts+=1;self.events.append('worker_confirm')
 def cancel_pending_dispatch(self,call_id):
  assert self.pending
  self.pending=False;self.events.append('worker_cancel')

class ProgrammedClient:
 def __init__(self,mode,clock,guard,events,folder,ledger=None):
  self.mode,self.clock,self.guard,self.events,self.folder=mode,clock,guard,events,folder
  self.ledger=ledger;self.turn_entered=False;self.commits=0;self.guard_deadlines=[]
  self.identity={'session_claim_id':'synthetic-exact-claim','recipe':{},'contract':copy.deepcopy(CONTRACT),
   'path':'project','inference_profile':{},'actor_identity':{'programmed_CPU_only':True}}
 def cancellation(self,operation):
  body={'reason':'queue_expired_before_dispatch','dispatched':False,'generation_calls':0,
   'original_operation':operation,'session_claim':self.identity['session_claim_id'],
   'request_id':'synthetic-request-'+operation,'usage_unknown':False}
  if self.ledger is not None:body['ledger']=copy.deepcopy(self.ledger)
  path=self.folder/('cancel-'+operation+'.json');atomic_write(path,json_bytes(body))
  return manager.InterleaveNotDispatched(body,reference(path))
 @contextmanager
 def turn(self,operation,**arguments):
  self.turn_entered=True;self.events.append('queued')
  self.guard_deadlines.append(json.loads(self.guard.read_text())['request_deadline'])
  if self.mode=='queue_cancel':
   self.clock.value+=10
   raise self.cancellation(operation)
  self.events.append('grant')
  self.clock.value+=20 if self.mode=='grant_cross_soft' else 5
  try:yield {'programmed':True}
  finally:
   if self.commits==0:self.events.append('cancel_uncommitted_ticket')
 def call(self,operation,**arguments):
  if self.mode=='match_cancel':raise self.cancellation(operation)
  self.commits+=1;self.events.append('commit')
  self.guard_deadlines.append(json.loads(self.guard.read_text())['request_deadline'])
  if self.mode=='late_cancel':raise self.cancellation(operation)
  self.clock.value+=7
  return {'http_status':200,'body':{'id':'programmed-only','usage':{
   'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}}}

def project_case(mode):
 folder=OUTPUT/mode;folder.mkdir(exist_ok=False)
 clock=Clock();deadline=DispatchDeadline(clock=clock)
 guard=folder/'guard.json';atomic_write(guard,json_bytes({'stop_requested':False,'request_deadline':None}))
 start={'soft_at':deadline.soft_at,'hard_at':deadline.hard_at,'guard_path':str(guard)}
 events=[];budget=SingleMemberBudget(members=['member_001'],team_id='synthetic-'+mode,require_exact_resident=False)
 call_id='call-'+mode
 budget.consume_decision('member_001',call_id);budget.reserve('member_001',call_id,{'token_reservation':2100});budget.begin_attempt('member_001',call_id)
 original_mark=budget.mark_dispatched
 def observed_mark(*args):events.append('budget_mark');return original_mark(*args)
 budget.mark_dispatched=observed_mark
 worker=Worker(events,budget);recorder=Recorder()
 client=ProgrammedClient(mode,clock,guard,events,folder)
 owner=transport.InterleavedProjectOwner(client,None,transport.InterleavedHostDeadline(start),window_id='synthetic-window')
 gate=transport.InterleavedProjectDispatchGate(owner,deadline)
 require(mode+'_uses_original_NativeDispatchGate',isinstance(gate,NativeDispatchGate))
 gate.context=SimpleNamespace(_turn={'member_id':'member_001','association':{'call_id':call_id}})
 gate.runtime=SimpleNamespace(team_budget=budget,policies={'member_001':worker},recorder=recorder)
 if mode=='grant_cross_soft':clock.value=deadline.soft_at-10
 if mode=='host_soft':clock.value=deadline.soft_at+1
 raised=None;body=None
 with patch.object(transport.time,'monotonic',clock):
  try:body=gate.complete({'synthetic':True},timeout_seconds=600)
  except BaseException as error:raised=error
 snapshot=budget.snapshot();host=json.loads(guard.read_text())
 if mode in {'queue_cancel','grant_cross_soft','host_soft'}:
  require(mode+'_normal_administrative_close',type(raised) is AdministrativeSoftDeadline)
  require(mode+'_decision_retained_and_no_attempt_charge_or_hold',snapshot['decisions']==1 and snapshot['attempts']==snapshot['charged_tokens']==snapshot['held_tokens']==0 and snapshot['records'][call_id]['status']=='cancelled_before_dispatch')
  require(mode+'_zero_dispatch',not deadline.dispatches and client.commits==0 and worker.attempts==0)
  require(mode+'_host_stop_remains_false',host=={'stop_requested':False,'request_deadline':None})
  if mode=='queue_cancel':require('queue_cancel_bound_receipt_recorded',len(gate.scheduler_boundaries)==1 and recorder.rows[0]['kind']=='interleaved_request_cancelled_before_dispatch')
  if mode=='grant_cross_soft':require('grant_cross_soft_cancels_uncommitted_turn','cancel_uncommitted_ticket' in events)
  if mode=='host_soft':require('host_soft_never_enqueued',not client.turn_entered)
 elif mode=='happy':
  require('happy_complete_without_error',raised is None and body['http_status']==200)
  require('grant_before_mark_confirm_commit',events==['queued','grant','budget_mark','worker_confirm','commit'])
  require('happy_original_660_deadline_not_reset',client.guard_deadlines==[1660.,1660.])
  require('happy_one_original_attempt',snapshot['attempts']==1 and snapshot['held_tokens']==2100 and snapshot['charged_tokens']==0 and worker.attempts==1)
  budget.settle('member_001',call_id,body['body']);snapshot=budget.snapshot()
  require('happy_actual_usage_settles_once',snapshot['attempts']==1 and snapshot['held_tokens']==0 and snapshot['charged_tokens']==3)
 elif mode=='late_cancel':
  require('late_cancel_is_fault_not_normal_boundary',type(raised) is RuntimeError and 'trusted dispatch' in str(raised))
  require('late_cancel_attempt_hold_not_zeroed',snapshot['attempts']==1 and snapshot['held_tokens']==2100 and snapshot['charged_tokens']==0 and snapshot['records'][call_id]['dispatch_started'] and not deadline.cancelled)
  require('late_cancel_recorded_failed_dispatch',deadline.dispatches[call_id]['status']=='raised_exception')
  # The real original cleanup charges an uncertain already-attempted reservation.
  budget.cleanup('member_001',call_id);snapshot=budget.snapshot()
  require('late_cancel_original_cleanup_preserves_uncertain_charge',snapshot['attempts']==1 and snapshot['charged_tokens']==2100 and snapshot['records'][call_id]['charge']['usage_status']=='uncertain_attempt_charged_reservation')
 return {'events':events,'raised':type(raised).__name__ if raised else None,'message':str(raised) if raised else None,
         'host_guard':host,'guard_deadlines_at_queue_and_commit':client.guard_deadlines,'budget':snapshot,
         'deadline':deadline.snapshot(budget),'programmed_calls':client.commits,'real_model_calls':0}

for mode in ('queue_cancel','grant_cross_soft','host_soft','happy','late_cancel'):
 run(mode,lambda mode=mode:project_case(mode))

def match_case():
 result=[]
 for operation in ('match_count','match_complete'):
  folder=OUTPUT/operation;folder.mkdir(exist_ok=False);clock=Clock()
  guard=folder/'guard.json';atomic_write(guard,json_bytes({'stop_requested':False,'request_deadline':None}))
  authoritative={'attempts':2,'decisions':1,'known_actual_tokens':9,'complete_actual_tokens':9,
   'uncertain_reserved_tokens':0,'inflight':None,'calls':[{'cpu_fixture_only':True}],'per_usage_id':{}}
  client=ProgrammedClient('match_cancel',clock,guard,[],folder,authoritative)
  gate=transport.InterleavedHostDeadline({'soft_at':6400.,'hard_at':7000.,'guard_path':str(guard)})
  adapter=transport.InterleavedMatchAdapter(client,gate,folder/'ledger')
  raised=None
  with patch.object(transport.time,'monotonic',clock):
   try:
    if operation=='match_count':adapter.count({'synthetic':True})
    else:adapter.complete({'synthetic':True},'agent')
   except BaseException as error:raised=error
  require(operation+'_typed_normal_boundary',type(raised) is transport.InterleaveEpisodeBoundary)
  require(operation+'_authoritative_server_ledger_preserved',adapter.ledger.snapshot()==authoritative)
  require(operation+'_no_transport_unknown',(folder/'ledger/interleaved-queue-boundary.json').exists() and not (folder/'ledger/transport-unknown.json').exists())
  require(operation+'_host_stop_false',json.loads(guard.read_text())=={'stop_requested':False,'request_deadline':None})
  result.append({'operation':operation,'ledger':adapter.ledger.snapshot(),'host_guard':json.loads(guard.read_text())})
 return result
run('MATCH_cancellation',match_case)

def queue_case():
 def row(n,status='pending',resident=None,gpu=None,arm='MATCH'):
  return {'slot':{'slot_id':'synthetic-'+str(n),'instance_id':'synthetic-task-'+str(n),'arm':arm},
          'generation':{'status':status,'resident_id':resident,'physical_gpu':gpu,'claimed':status!='pending'}}
 def resident(index,capacity=2):
  return {'session_capacity':capacity,'active_claims':[],
          'declaration':{'gpu_index':index,'mode':'MATCH_PROJECT',**({'session_protocol':'mp-interleave-v1'} if capacity==2 else {})}}
 mp6=resident(6);pending=row(2,arm='PROJECT');occupied=row(1,'running','mp6',6)
 chosen=queue.select_pool_slot([occupied,pending],{'mp6':mp6},timestamp=1)
 require('queue_second_MP_session_admitted',chosen is not None and chosen[0] is pending and chosen[1]=='mp6')
 require('queue_third_same_resident_rejected',queue.select_pool_slot([occupied,row(3,'running','mp6',6),pending],{'mp6':mp6},timestamp=1) is None)
 require('queue_global_eight_limit',queue.select_pool_slot([row(n,'running','r'+str(n),n) for n in range(8)]+[pending],{'mp6':mp6},timestamp=1) is None)
 require('queue_not_concurrent_with_legacy_same_GPU',queue.select_pool_slot([row(1,'running','legacy6',6),pending],{'mp6':mp6},timestamp=1) is None)
 require('queue_legacy_stays_one_session',queue.select_pool_slot([occupied,pending],{'mp6':resident(6,1)},timestamp=1) is None)
 chosen=queue.select_pool_slot([occupied,pending],{'mp6':mp6,'mp3':resident(3)},timestamp=1)
 require('queue_prefers_empty_resident_before_second_session',chosen[1]=='mp3')
 mp6_busy=copy.deepcopy(mp6);mp6_busy['active_claims']=['first','second']
 require('queue_live_unreflected_claims_count',queue.select_pool_slot([pending],{'mp6':mp6_busy},timestamp=1) is None)
 return {'actual_selector':str(Path(queue.__file__)),'synthetic_rows_only':True}
run('queue',queue_case)

def migration_case():
 old={'authorization':reference(REPO/'config/v054-formal-authorization-r2-dynamic-pool.json'),
      'plan':reference(REPO/'config/v054-formal-execution-plan-r3-dynamic-pool.json')}
 new={'authorization':reference(STAGE/'config/v054-formal-authorization-r3-interleaved.json'),
      'plan':reference(STAGE/'config/v054-formal-execution-plan-r4-interleaved.json'),
      'resident_pool_policy':{'synthetic_control_reference_only':True}}
 proof=migration.verify_resource_revision(old,new)
 require('migration_same_slots_and_budgets_accepted',proof['fixed_slots_and_budget_unchanged'] is True)
 altered=json.loads(Path(new['authorization']['path']).read_text());altered['input_output_token_limit_per_episode']=500001
 path=OUTPUT/'changed-budget-auth.json';atomic_write(path,json_bytes(altered))
 require('migration_changed_budget_rejected',reject(lambda:migration.verify_resource_revision(old,{**new,'authorization':reference(path)})))
 altered=json.loads(Path(new['authorization']['path']).read_text());altered['same_gpu_session_policy']['MATCH_PROJECT']=3
 path=OUTPUT/'changed-session-auth.json';atomic_write(path,json_bytes(altered))
 require('migration_three_sessions_rejected',reject(lambda:migration.verify_resource_revision(old,{**new,'authorization':reference(path)})))
 return proof
run('migration',migration_case)

def controller_case():
 tree=ast.parse((STAGE/'tools/run_benchmark_controller_v054.py').read_text())
 used={node.id for node in ast.walk(tree) if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Load)}
 require('controller_statically_routes_new_deadline_adapters_and_context',{
  'InterleavedHostDeadline','InterleavedMatchAdapter','InterleavedProjectOwner','owner_client','interleaved_context','unwrap_interleave_boundary'}<=used)
 return {'scope':'AST binding check only; no SDK controller instantiated or executed'}
run('controller_static_routing',controller_case)
require('source_files_unchanged_during_control',sources_before==[reference(p) for p in source_paths])
report={'version':'v054-interleave-root-integration-cpu-control-r1','passed':not failures and all(checks.values()),
 'checks':checks,'cases':cases,'failures':failures,'sources':sources_before,
 'model_calls':0,'GPU_queries':0,'GPU_loads':0,'formal_slots_claimed':0,'SDK_conversations_created':0,
 'real_components':['SingleMemberBudget(require_exact_resident=False only for accounting fixture)','Original NativeDispatchGate','DispatchDeadline','staged interleaved transport classes','staged queue selector','staged migration validation'],
 'programmed_components':['turn/call transport, worker and recorder; no numerical owner instantiated']}
atomic_write(OUTPUT/'receipt.json',json_bytes(report))
print(json.dumps({'passed':report['passed'],'checks':checks,'failures':failures,
 'late_commit_host_guard':cases.get('late_cancel',{}).get('host_guard'),
 'receipt':reference(OUTPUT/'receipt.json')},ensure_ascii=False,indent=2))
raise SystemExit(0 if report['passed'] else 1)
