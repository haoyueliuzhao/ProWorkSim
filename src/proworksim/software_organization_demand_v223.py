"""Evidence-backed reconsideration requests, separate from live action permission.

These are triage hypotheses, not human-labelled organization mismatch gold.
No model or world mutation; test failure counts alone never trigger intervention.
"""
import copy
from .software_project_relations_v217 import identity
VERSION='v223-demand-opportunity-separation-r1'
KINDS=('responsibility_gap','dependency_bottleneck','load_imbalance','verification_gap','integration_conflict')

def inspect_state(state,*,members=('member_001','member_002'),terminal=False):
 work=state['graph']['work'];leaves={k:w for k,w in work.items() if not w.get('children') and w.get('completion') is None}
 mutable={k:w for k,w in leaves.items() if not w.get('authors')};demands=[]
 def add(kind,scope,evidence,reason,urgency='normal',uncertainty='hypothesis'):
  key=identity({'kind':kind,'scope':sorted(scope),'evidence':evidence})
  demands.append({'id':key,'type':kind,'work_ids':sorted(scope),'evidence':copy.deepcopy(evidence),'reason':reason,'urgency':urgency,'uncertainty':uncertainty,'mismatch_not_proven':True})
 for tid,w in leaves.items():
  if w['owner'] not in members:add('responsibility_gap',[tid],{'owner':w['owner']},'No live accountable member; executor support must be checked','high','observed_record')
  if not w.get('reviewer') or w['reviewer']==w['owner'] or w['reviewer'] in w.get('authors',[]):
   add('verification_gap',[tid],{'owner':w['owner'],'reviewer':w.get('reviewer'),'authors':w.get('authors',[])},'Independent verification is not currently assigned; ordinary setup may suffice',uncertainty='observed_record')
  for parent in w.get('depends_on',[]):
   upstream=work.get(parent)
   # A routine unresolved edge alone is not evidence that coordination failed.
   blocked=[x for x in state.get('visible_blockages',[]) if x.get('task_id')==tid and x.get('upstream_task')==parent and x.get('source_receipt')]
   if upstream and upstream['owner']!=w['owner'] and not upstream.get('completion_current',False) and blocked:
    add('dependency_bottleneck',[tid,parent],{'blockages':blocked},'A real visible blocked attempt meets an unresolved cross-owner obligation')
 loads={m:sum(w['owner']==m for w in leaves.values()) for m in members}
 if len(mutable)>=2 and max(loads.values(),default=0)>=2 and min(loads.values(),default=1)==0:
  add('load_imbalance',list(mutable),{'unfinished_packages_by_owner':loads,'available_members':list(members)},'One live member has no owned unfinished package; reassignment value is unproven')
 if state.get('conflict_count',0)>0:
  add('integration_conflict',list(leaves),{'actual_conflict_count':state['conflict_count']},'Current actor-visible merged tree contains actual unresolved conflicts','high','observed_record')
 flags=state.get('reason_flags',{})
 transferable=bool(flags.get('actual_code_progress') and flags.get('subsequent_executed_public_test') and mutable)
 ready=bool(demands and transferable and not terminal and state.get('team_remaining_tokens',0)>=2_000_000)
 return {'version':VERSION,'demands':demands,'demand_detected':bool(demands),'status':'reconsideration_ready' if ready else 'demand_waiting_for_execution_window' if demands else 'monitor_no_supported_demand',
         'proposal_generation_admissible':ready,'joint_action_preconditions_present':transferable,
         'mutable_work_ids':sorted(mutable),'no_test_count_trigger':True,'not_an_execution_authorization':True,
         'reason_flags':copy.deepcopy(flags),'terminal':bool(terminal)}

class Timeline:
 def __init__(self):self.previous=None;self.seen_causes=set();self.records=[];self.blockages=[]
 def record_outcome(self,outcome,state):
  # Only the decision actor's actual response may supply a private blocked attempt.
  if outcome.get('worker_id')!='member_001':return
  response=outcome.get('response',{});task=outcome.get('decision',{}).get('arguments',{}).get('task_id')
  signature=identity(state['graph']['work'])
  self.blockages=[x for x in self.blockages if x['work_signature']==signature and x['task_id']!=task]
  def find(value):
   if isinstance(value,dict):
    if 'gaps' in value and 'task_id' in value:yield value
    for v in value.values():yield from find(v)
   elif isinstance(value,list):
    for v in value:yield from find(v)
  for readiness in find(response):
   for gap in readiness['gaps']:
    if gap.get('kind') not in ('upstream_not_current','upstream_evidence_version_not_adopted','upstream_patch_not_adopted'):continue
    self.blockages.append({'task_id':readiness['task_id'],'upstream_task':gap['task_id'],'work_signature':signature,'source_receipt':{'sha256':identity(response),'command_id':response.get('command_id'),'gap':copy.deepcopy(gap)}})
 def update(self,state,project,*,terminal=False):
  state=copy.deepcopy(state);state['visible_blockages']=[x for x in self.blockages if x['work_signature']==identity(state['graph']['work'])]
  relations={r['id']:r for r in project['relations']};old=self.previous or {}
  delta={'added':sorted(set(relations)-set(old)),'changed':sorted(k for k in set(relations)&set(old) if relations[k]!=old[k]),'removed':sorted(set(old)-set(relations))}
  demand=inspect_state(state,terminal=terminal);fresh=[d['id'] for d in demand['demands'] if d['id'] not in self.seen_causes]
  was_ready=bool(self.records and self.records[-1]['assessment']['proposal_generation_admissible'])
  reconsider=bool(demand['proposal_generation_admissible'] and (fresh or not was_ready))
  self.seen_causes.update(fresh);self.previous=copy.deepcopy(relations)
  event={'index':len(self.records),'graph_id':project['graph_id'],'delta':delta,'new_demand_ids':fresh,'reconsideration_event':reconsider,'assessment':demand,'state_hash':identity(state),'world_actions':0}
  self.records.append(event);return event
 def export(self):return copy.deepcopy({'previous':self.previous,'seen_causes':sorted(self.seen_causes),'records':self.records,'blockages':self.blockages})
 def restore(self,value):self.previous=copy.deepcopy(value['previous']);self.seen_causes=set(value['seen_causes']);self.records=copy.deepcopy(value['records']);self.blockages=copy.deepcopy(value.get('blockages',[]))
