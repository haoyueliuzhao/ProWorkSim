"""Delivery-terminal lifecycle and explicit adaptation choice over v213 semantics.

No host ownership mutation, automatic submission, fabricated consent or scoring
feedback. Existing reopens/versioned evidence implement the repair chain.
"""
import copy,re
from pathlib import Path
from . import software_organization_world_v213 as old
from . import software_organization_performance_v214 as speed
from .software_collaboration_v027 import _tool
from .world_core import WorldCore
from .work_interface import _schema_errors
from .storage import json_bytes,digest,atomic_write
VERSION='v216-delivery-and-adaptation-lifecycle-r1';PROJECT=old.PROJECT
EXTRA=[
 _tool('delivery_readiness','Read exact final delivery gaps, unresolved integration conflicts and next explicit actions. Never performs submission or repair.',{},[]),
 _tool('select_arrangement','Explicitly choose whether to attempt the frozen organization proposal, KEEP the current arrangement, or defer. Choice alone never changes owners, authors, review duties or dependencies.',{'candidate_id':{'type':'string'},'decision':{'type':'string','enum':['attempt','keep','defer']},'reason':{'type':'string','minLength':1}}),
 _tool('abort_episode','Final integrator explicitly abandons this episode, preserving its unique final tree and all costs. Terminal; no further model opportunity.',{'reason':{'type':'string','minLength':1}}),
]
READ_ONLY={'delivery_readiness','delivery_checklist','dynamic_status','org_status','delivery_status','read_file','list_files','read_task','read_work_event','read_test_result','diff_workspace','work_readiness','search_file','search_repository'}
def tool_definitions(case):
 values=old.tool_definitions(case)+copy.deepcopy(EXTRA)
 for t in values:
  if t['name']=='run_tests':
   t['parameters']['properties']['evidence_id']={'type':'string'}
   t['description']+=' Optional evidence_id explicitly tests your adopted immutable evidence source instead of your current tree. Main workspace is unchanged.'
  if t['name']=='adopt_evidence':t['description']='Explicitly open an immutable evidence record for independent checking without changing your private tree. Then run_tests(evidence_id=...) and review_evidence. Final evidence must still match the final integrated tree.'
 return values
class World(speed.World):
 def protocol(self):return self._software()['protocol_v216']
 def _tool_definitions(self,project_id):return tool_definitions(self._software()['case']) if project_id==PROJECT else super()._tool_definitions(project_id)
 def _tool_project_action(self,actor,project_id,tool,arguments,interface_profile=None):
  if self.protocol()['terminal'] in ('DELIVERED','ABORTED') and tool not in READ_ONLY:self.org_reject('Episode is terminal; no more ordinary work','episode_terminal',terminal=self.protocol()['terminal'])
  pending=self.protocol().get('proposal')
  if pending and self.protocol().get('choice') is None and tool not in READ_ONLY|{'select_arrangement','abort_episode'}:
   self.org_reject('Record attempt/keep/defer for the current proposal first; refusal is allowed','explicit_arrangement_choice_required',candidate_id=pending['candidate_id'])
  if tool in {t['name'] for t in EXTRA}:
   if actor not in self.live_members() or project_id!=PROJECT:self.org_reject('Actual member required','dynamic_identity')
   if getattr(self,'fixed_candidates_closed',False):self.org_reject('Candidates already locked','fixed_candidates_closed')
   if getattr(self,'require_scheduled_actions',False) and getattr(self,'scheduled_member',None)!=actor:self.org_reject('Scheduled member required','fixed_organization_schedule')
   errors=_schema_errors(next(t for t in EXTRA if t['name']==tool)['parameters'],arguments)
   if errors:self.org_reject('; '.join(errors),'public_argument_schema')
   return WorldCore._tool_project_action(self,actor,project_id,tool,arguments,interface_profile)
  return super()._tool_project_action(actor,project_id,tool,arguments,interface_profile)
 def _action_select_arrangement(self,actor,project_id,candidate_id,decision,reason):
  p=self.protocol();proposal=p.get('proposal')
  if actor!='member_001':self.org_reject('Integrator records proposal selection; each owner/recipient still acts separately','selection_actor_required')
  if p.get('choice') is not None:self.org_reject('One frozen decision per episode; retain the original choice','choice_already_recorded')
  if not proposal or candidate_id!=proposal['candidate_id']:self.org_reject('Use the actual frozen candidate ID','unknown_arrangement')
  if proposal.get('keep') and decision=='attempt':decision='keep'
  e=self._event(actor,'organization_v216:arrangement_selected',candidate_id=candidate_id,decision=decision,reason=reason,automatic_owner_change=False)
  p['choice']={'actor':actor,'candidate_id':candidate_id,'decision':decision,'reason':reason,'event_sequence':e['sequence']}
  return {**copy.deepcopy(p['choice']),'actual_tools_and_other_member_consent_still_required':True}
 def _action_abort_episode(self,actor,project_id,reason):
  if actor!='member_001':self.org_reject('Only final integrator may abandon the team episode','final_integrator_required')
  e=self._event(actor,'organization_v216:aborted',reason=reason);self.protocol().update(terminal='ABORTED',terminal_event=e['sequence']);return {'state':'ABORTED','event_sequence':e['sequence']}
 def _bundle(self,actor,*,patch_id=None,reference=None,write=False,baseline=False):
  focus=getattr(self,'_evidence_test_focus',None)
  if focus and focus['actor']==actor and patch_id is None and reference is None and not baseline:
   if write:raise ValueError('Immutable evidence test cannot edit a workspace')
   reference=focus['reference']
  return super()._bundle(actor,patch_id=patch_id,reference=reference,write=write,baseline=baseline)
 def _action_adopt_evidence(self,actor,project_id,evidence_id):
  e=self._evidence(evidence_id);w=self.dynamic()['work'][e['task_id']]
  if actor==e['checker'] or actor!=w['reviewer']:self.org_reject('Assigned independent evidence checker required','evidence_self_review')
  self._bundle(actor,reference=e['identity']['source_reference'])
  event=self._event(actor,'organization_v216:evidence_view_adopted',evidence_id=evidence_id,identity=e['identity'],main_workspace_unchanged=True)
  self.protocol()['evidence_views'].setdefault(actor,{})[evidence_id]={'identity':copy.deepcopy(e['identity']),'event_sequence':event['sequence'],'work_epoch':e['work_epoch']}
  self.dynamic()['evidence_adoptions'].setdefault(actor,{})[evidence_id]=copy.deepcopy(e['identity'])
  return {'event_sequence':event['sequence'],'evidence_id':evidence_id,'identity':e['identity'],'main_workspace_unchanged':True,'next_explicit_action':{'tool':'run_tests','arguments':{'evidence_id':evidence_id}},'not_main_workspace_adoption':True}
 def _action_run_tests(self,actor,project_id,selection=None,evidence_id=None):
  if evidence_id is None:return super()._action_run_tests(actor,project_id,selection)
  e=self._evidence(evidence_id);view=self.protocol()['evidence_views'].get(actor,{}).get(evidence_id)
  if not view or view['identity']!=e['identity']:self.org_reject('Explicitly adopt this evidence version first','evidence_adoption_required')
  if getattr(self,'_evidence_test_focus',None) or getattr(self,'_read_only_review_focus',None):raise ValueError('One test source per opportunity')
  before=self.org_current_identity(actor);self._evidence_test_focus={'actor':actor,'reference':e['identity']['source_reference']}
  try:result=super()._action_run_tests(actor,project_id,selection)
  finally:self._evidence_test_focus=None
  if self.org_current_identity(actor)!=before:raise ValueError('Evidence test changed main workspace')
  return {**result,'evidence_id':evidence_id,'main_workspace_unchanged':True}
 def _action_review_evidence(self,actor,project_id,evidence_id,decision,reason):
  if decision!='accept':return super()._action_review_evidence(actor,project_id,evidence_id,decision,reason)
  e=self._evidence(evidence_id);w=self.dynamic()['work'][e['task_id']];view=self.protocol()['evidence_views'].get(actor,{}).get(evidence_id)
  if actor==e['checker'] or actor!=w['reviewer'] or actor in w['authors']:self.org_reject('Assigned independent checker required','evidence_self_review')
  if not view or view['identity']!=e['identity']:self.org_reject('Adopt current evidence first','evidence_adoption_required')
  test=self._fresh_test(actor,e['identity'],[e['task_id']])
  if test['sequence']<=view['event_sequence']:self.org_reject('Test after evidence adoption','evidence_review_test_required')
  record={'evidence_id':evidence_id,'task_id':e['task_id'],'reviewer':actor,'decision':decision,'reason':reason,'work_epoch':e['work_epoch'],'test_evidence':self._test_summary(test),'source_code_author_retained':e['source_code_author'],'adoption_kind':'immutable_evidence_review','not_whole_tree_author_blind_review':True}
  event=self._event(actor,'organization_v213:evidence_reviewed',**copy.deepcopy(record));record['event_sequence']=event['sequence'];self.dynamic()['evidence_reviews'].append(record);return copy.deepcopy(record)
 def _action_integrate_patch(self,actor,project_id,patch_id):
  result=super()._action_integrate_patch(actor,project_id,patch_id)
  if result.get('conflict_count'):
   self.protocol()['integrations'].append({'actor':actor,'patch_id':patch_id,'paths':list(result['conflicts']),'reported_count':result['conflict_count'],'identity':self.org_current_identity(actor)})
   result['repair_instructions']='Resolve conflicts in your owned work context. If locally complete, explicitly reopen_work, begin_work, repair, test, publish and obtain new review. Evidence tied to a previous tree must also be reopened and revalidated. Never inherit old passed status.'
  return result
 def _conflicts(self,actor):
  _,_,bundle=self._bundle(actor);known=set()
  for item in self.protocol()['integrations']:
   if item['actor']==actor:
    known.update(item['paths'])
    if item['reported_count']>len(item['paths']):known.update(self._patch(item['patch_id'])['changed_paths'])
  result=[]
  for path in sorted(known):
   text=bundle['files'].get(path,'');meta=bundle['entry_metadata'].get(path,{})
   if meta.get('encoding')=='utf-8' and re.search(r'^<<<<<<< ',text,re.M) and re.search(r'^>>>>>>> ',text,re.M):result.append(path)
  return result
 def _action_delivery_readiness(self,actor,project_id):
  final='member_001';d=self.dynamic();check=self._action_delivery_checklist(final,PROJECT);current=self.org_current_identity(final);sw=self._software();conflicts=self._conflicts(final)
  # Existing fixed submission implementation still performs the authoritative checks.
  fixed=sw.get('patches',{});current_fixed=[p for p in fixed.values() if p['author']==final and self.org_patch_identity(p['patch_id'])==current]
  test=self._latest_same_version_test(final,current);gaps=[];actions=[]
  for row in check['packages']:
   if row['missing']:gaps.append({'task_id':row['task_id'],'owner':row['owner'],'missing':row['missing']})
   if row['completion'] is None:actions.append({'actor':row['owner'],'tools':['fix_patch','complete_work'],'alternative_for_unmodified_scope':'complete_evidence'})
   elif any('revalidate' in x or 'stale' in x for x in row['missing']):actions.append({'actor':row['owner'],'task_id':row['task_id'],'tools':['reopen_work','run_tests','fix_patch_or_existing_fixed_source','complete_evidence_or_complete_work','independent_review']})
  if conflicts:gaps.append({'kind':'unresolved_final_integration_conflicts','paths':conflicts});actions.append({'actor':final,'tools':['reopen_work_if_completed','begin_work','edit_conflicted_files','run_tests','fix_patch','new_review']})
  if not test or test.get('passed') is not True:gaps.append({'kind':'final_tree_public_test_missing_or_failed'});actions.append({'actor':final,'tools':['run_tests']})
  if not current_fixed:gaps.append({'kind':'final_tree_not_fixed'});actions.append({'actor':final,'tools':['fix_patch']})
  ready=not gaps
  terminal=self.protocol()['terminal'];status=terminal if terminal else ('IN_PROGRESS' if ready else 'BLOCKED')
  return {'state':status,'terminal':bool(terminal),'ready_to_submit':ready and not terminal,'package_chain':check,'final_identity':current,'final_test':self._test_summary(test),'current_fixed_patch_ids':[p['patch_id'] for p in current_fixed],'gaps':gaps,'next_actions':([{'actor':final,'tool':'submit_integration','note':'All visible requirements ready. Explicitly submit now; this does not claim official correctness.'}] if ready and not terminal else actions),'automatic_submission':False,'hidden_score_known':False,'private_peer_code_not_exposed':True}
 def _action_submit_integration(self,actor,project_id,message=''):
  if self._conflicts(actor):self.org_reject('Resolve actual recorded integration conflicts before submission','unresolved_integration_conflict')
  result=super()._action_submit_integration(actor,project_id,message)
  e=self._event(actor,'organization_v216:delivered',delivery_id=result.get('delivery_id'),identity=self.org_current_identity(actor),official_correctness_known=False)
  self.protocol().update(terminal='DELIVERED',terminal_event=e['sequence'],terminal_identity=self.org_current_identity(actor))
  return {**result,'episode_state':'DELIVERED','no_further_model_opportunities':True,'official_score':None}
 def _closing_steps(self,actor):
  v=super()._closing_steps(actor);v['delivery_readiness']=self._action_delivery_readiness(actor,PROJECT)
  if v['delivery_readiness']['ready_to_submit']:v.update(next_explicit_tool='submit_integration',next_explicit_action={'tool':'submit_integration','arguments':{'message':'Deliver this exact version.'}})
  return v
 def _action_dynamic_status(self,actor,project_id):
  v=super()._action_dynamic_status(actor,project_id);v['lifecycle']=copy.deepcopy(self.protocol());return v

class Port(old.SoftwareCollaborationPort):
 def observe(self):
  v=super().observe();w=self._session._world;v['delivery_readiness']=w._action_delivery_readiness(self.role,PROJECT);v['organization_decision']=copy.deepcopy(w.protocol().get('proposal'));v['organization_choice']=copy.deepcopy(w.protocol().get('choice'));return v

def attach(prepared,requirements):
 old.attach(prepared,requirements);speed.attach(prepared);w=prepared.world;w.__class__=World
 with w.store.lock():
  w.state=w.store.load();w._software()['protocol_v216']={'version':VERSION,'terminal':None,'terminal_event':None,'integrations':[],'proposal':None,'choice':None,'evidence_views':{}};w.store.save(w.state)
 prepared.prefix['lifecycle_revision']=VERSION;atomic_write(Path(w.store.root).parent/'preparation.json',json_bytes(prepared.prefix));return prepared

def register_proposal(world,candidate,source):
 """Trusted experiment input only; does not execute a choice or organization operation."""
 with world.store.lock():
  world.state=world.store.load();p=world.protocol()
  if p['proposal'] is not None or p['terminal']:raise ValueError('One predecision assignment in a nonterminal branch')
  p['proposal']={**copy.deepcopy(candidate),'source':source,'host_effects_only_proposal_metadata':True};world.store.save(world.state)

SoftwareCollaborationPort=Port
SoftwareCollaborationWorld=World
