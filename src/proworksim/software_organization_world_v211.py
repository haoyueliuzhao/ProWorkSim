"""New isolated dynamic-work overlay on the real managed world.

No global monkeypatching, shell, permissions expansion or host operations.
Six core transforms use real WorldCore transactions and versioned event receipts.
A persisted pending offer keeps the old owner; failures do not roll back history.
"""
from __future__ import annotations
import copy,re
from pathlib import Path
from . import software_role_baseline_world_v141 as previous
from .software_collaboration_v027 import _tool
from .work_interface import _schema_errors
from .world_core import WorldCore
from .storage import digest,json_bytes,atomic_write
VERSION='v211-dynamic-work-r1';PROJECT=previous.PROJECT
_ID={'type':'string','minLength':1,'maxLength':64};_TEXT={'type':'string','minLength':1,'maxLength':2000}
_LIST={'type':'array','items':_ID,'minItems':1,'maxItems':8,'uniqueItems':True}
NEW_TOOLS=[
 _tool('split_work','Owner splits unfinished work into public requirement-anchored child packages. All children initially retain the current owner; transfer requires actual recipient acceptance. Scope cannot be dropped.',{'task_id':_ID,'children':{'type':'array','minItems':2,'maxItems':4,'items':{'type':'object','properties':{'task_id':_ID,'description':_TEXT,'scope':_LIST},'required':['task_id','description','scope'],'additionalProperties':False}},'reason':_TEXT}),
 _tool('assign_work','Current owner offers an owned work package to another live member. This does not change owner until the recipient calls accept_transfer. Never writes recipient consent.',{'task_id':_ID,'to_member':_ID,'reason':_TEXT}),
 _tool('add_collaboration','Owner opens a directed, work-bound collaboration edge to another actual member. Root-goal negotiation remains available; no private histories or code are copied.',{'task_id':_ID,'peer':_ID,'reason':_TEXT}),
 _tool('change_dependency','Owner explicitly adds/removes a task dependency, binding current revisions. Starting downstream code work requires upstream local completion and adoption of its exact patch.',{'task_id':_ID,'depends_on':_ID,'operation':{'type':'string','enum':['add','remove']},'reason':_TEXT}),
 _tool('assign_verification','Owner designates another non-author to verify this package. It does not test, adopt or accept a patch. A later independent explicit review is mandatory.',{'task_id':_ID,'reviewer':_ID,'reason':_TEXT}),
 _tool('begin_work','Owner selects a leaf package for actual code changes. Dependencies must have locally completed, exact adopted patches. Reading and negotiation remain possible while blocked.',{'task_id':_ID}),
 _tool('complete_work','Owner records a fixed, actually tested package version as locally complete. Not official task success. Required independent review and final integration remain separate.',{'task_id':_ID,'patch_id':_ID}),
 _tool('dynamic_status','Read public owner, dependency, collaboration and verification state. No private file contents or hidden tests.',{},[]),
]
DISABLED={'create_task','claim_task','return_task','release_task','revise_task','declare_dependency','remove_dependency'}
EDIT_TOOLS={'write_file','replace_file','create_file','delete_file','rename_file'}

def tool_definitions(case):return [t for t in previous.tool_definitions(case) if t['name'] not in DISABLED]+copy.deepcopy(NEW_TOOLS)

class SoftwareCollaborationWorld(previous.SoftwareCollaborationWorld):
 def dynamic(self):
  d=self._software()['dynamic_v211']
  if d['version']!=VERSION:raise ValueError('Wrong dynamic world revision')
  return d
 def _tool_definitions(self,project_id):return tool_definitions(self._software()['case']) if project_id==PROJECT else super()._tool_definitions(project_id)
 def _owned_leaf(self,actor,task_id,*,allow_complete=False):
  d=self.dynamic();w=d['work'].get(task_id)
  if not w or w['children']:self.org_reject('Select an actual leaf work package','dynamic_leaf_required')
  if self._task(task_id)['owner']!=actor:self.org_reject('Only current accountable owner may act','dynamic_owner_required')
  if w['completion'] is not None and not allow_complete:self.org_reject('This package is locally complete; cannot silently change it','dynamic_completed_work')
  return w
 def _event_dynamic(self,actor,kind,**facts):return self._event(actor,'organization_v211:'+kind,**facts)
 def _tool_project_action(self,actor,project_id,tool,arguments,interface_profile=None):
  if actor not in self.live_members() or project_id!=PROJECT:self.org_reject('Actual registered actor required','dynamic_identity')
  if getattr(self,'fixed_candidates_closed',False):self.org_reject('Candidates already locked','fixed_candidates_closed')
  if getattr(self,'require_scheduled_actions',False) and getattr(self,'scheduled_member',None)!=actor:self.org_reject('Current actor scheduled opportunity required','fixed_organization_schedule')
  definitions={t['name']:t for t in self._tool_definitions(project_id)}
  if tool not in definitions:self.org_reject('Unsupported dynamic-world operation','tool_not_enabled')
  errors=_schema_errors(definitions[tool]['parameters'],arguments)
  if errors:self.org_reject('; '.join(errors),'public_argument_schema')
  d=self.dynamic()
  if tool in EDIT_TOOLS:
   tid=d['active_work'].get(actor)
   if not tid:self.org_reject('Choose your real work package with begin_work first','dynamic_work_context_required')
   w=self._owned_leaf(actor,tid)
   if w['reviewer']==actor:self.org_reject('Assigned independent verifier cannot become this package author','dynamic_self_review')
  if tool=='offer_transfer':self._owned_leaf(actor,arguments['task_id'])
  if tool=='accept_transfer':
   offer=self._offered(actor,arguments['offer_id']);w=d['work'].get(offer['task_id'])
   if not w or w['children'] or w['completion']:self.org_reject('No unfinished leaf offered','dynamic_transfer_scope')
   if w['reviewer']==actor:self.org_reject('Reassign independent verification before accepting implementation','dynamic_verifier_owner_conflict')
  if tool=='send_message' and arguments['task_id']!='root_goal':
   if [arguments['task_id'],actor,arguments['recipient']] not in d['collaboration']:self.org_reject('Open an actual work-bound collaboration edge first','dynamic_collaboration_required')
  if tool=='handoff_patch':
   patch=self._patch(arguments['patch_id']);tasks=list(patch['task_snapshots'])
   if not tasks or any([tid,actor,arguments['to_member']] not in d['collaboration'] for tid in tasks):self.org_reject('Open work-bound collaboration before handing off its patch','dynamic_collaboration_required')
  if tool=='fix_patch':
   if not arguments['task_ids']:self.org_reject('Bind real work package(s), or use all completed packages for final integration','dynamic_patch_scope_required')
   for tid in arguments['task_ids']:
    if tid not in d['work'] or d['work'][tid]['children']:self.org_reject('Fixed patch must bind actual leaf work','dynamic_patch_scope_required')
  if tool=='org_review_patch':
   patch=self._patch(arguments['patch_id']);tasks=list(patch['task_snapshots'])
   if not tasks:self.org_reject('Review an actual work-bound candidate','dynamic_patch_scope_required')
   for tid in tasks:
    w=d['work'][tid]
    if w['reviewer']!=actor or actor in w['authors']:self.org_reject('Actual non-author assigned verifier required','dynamic_self_review')
  new=tool in {t['name'] for t in NEW_TOOLS}
  result=WorldCore._tool_project_action(self,actor,project_id,tool,arguments,interface_profile) if new else super()._tool_project_action(actor,project_id,tool,arguments,interface_profile)
  if tool in EDIT_TOOLS:
   w=d['work'][d['active_work'][actor]]
   if actor not in w['authors']:w['authors'].append(actor)
   self._event_dynamic(actor,'work_performed',task_id=d['active_work'][actor],tool=tool,source_reference=self.org_current_identity(actor)['source_reference'])
  self._assert_responsibility()
  return result
 def _assert_responsibility(self):
  for tid in self.dynamic()['work']:
   if self._task(tid)['owner'] not in self.live_members():raise ValueError('Unaccountable unfinished package')
 def _action_split_work(self,actor,project_id,task_id,children,reason):
  d=self.dynamic();w=self._owned_leaf(actor,task_id)
  if w['authors'] or self._task(task_id)['depends_on'] or any(task_id in self._task(k)['depends_on'] for k in d['work']):self.org_reject('Split before authorship/dependency work; explicit migration is not implemented','dynamic_split_boundary')
  ids=[c['task_id'] for c in children];scope=[s for c in children for s in c['scope']]
  if len(d['work'])+len(ids)>12 or len(set(ids))!=len(ids) or any(i in self._software()['tasks'] or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',i) for i in ids):self.org_reject('New bounded distinct task IDs required','dynamic_split_identity')
  if set(scope)!=set(w['scope']) or len(scope)!=len(set(scope)):self.org_reject('Disjoint complete public scope partition required; overlap not yet enabled','dynamic_scope_conservation')
  receipts=[]
  for c in children:
   created=super()._action_create_task(actor,project_id,c['task_id'],c['description'],task_id)
   claimed=super()._action_claim_task(actor,project_id,c['task_id'],reason)
   d['work'][c['task_id']]={'scope':list(c['scope']),'children':[],'authors':[],'reviewer':None,'completion':None}
   receipts.append({'created':created,'claimed':claimed})
  w['children']=ids;d['active_work'].pop(actor,None)
  e=self._event_dynamic(actor,'work_split',parent=task_id,children=ids,scope=w['scope'],reason=reason,receipts=receipts)
  return {'event_sequence':e['sequence'],'parent':task_id,'children':ids,'all_children_owner':actor,'scope_conserved':True,'not_work_completed':True}
 def _action_assign_work(self,actor,project_id,task_id,to_member,reason):
  self._owned_leaf(actor,task_id)
  return super()._action_offer_transfer(actor,project_id,task_id,to_member,reason)
 def _action_add_collaboration(self,actor,project_id,task_id,peer,reason):
  self._owned_leaf(actor,task_id,allow_complete=True);self._available_recipient(actor,peer);d=self.dynamic()
  # Work-bound two-way exchange, no permissions on private content.
  for edge in ([task_id,actor,peer],[task_id,peer,actor]):
   if edge not in d['collaboration']:d['collaboration'].append(edge)
  e=self._event_dynamic(actor,'collaboration_opened',task_id=task_id,peer=peer,reason=reason)
  return {'event_sequence':e['sequence'],'message_and_handoff_enabled':True,'private_history_copied':False}
 def _action_change_dependency(self,actor,project_id,task_id,depends_on,operation,reason):
  w=self._owned_leaf(actor,task_id)
  if depends_on not in self.dynamic()['work'] or self.dynamic()['work'][depends_on]['children']:self.org_reject('Depend on a leaf work package','dynamic_dependency_scope')
  if w['authors']:self.org_reject('Cannot change dependency after implementation has started','dynamic_dependency_boundary')
  if operation=='add':result=super()._action_declare_dependency(actor,project_id,task_id,depends_on)
  elif operation=='remove':result=super()._action_remove_dependency(actor,project_id,task_id,depends_on,reason)
  else:self.org_reject('Explicit add or remove','dynamic_dependency_operation')
  self._event_dynamic(actor,'dependency_changed',task_id=task_id,depends_on=depends_on,operation=operation,reason=reason)
  return result
 def _action_assign_verification(self,actor,project_id,task_id,reviewer,reason):
  w=self._owned_leaf(actor,task_id)
  if reviewer not in self.live_members() or reviewer==actor or reviewer in w['authors']:self.org_reject('Select an actual independent non-author','dynamic_self_review')
  w['reviewer']=reviewer;e=self._event_dynamic(actor,'verification_assigned',task_id=task_id,reviewer=reviewer,reason=reason)
  return {'event_sequence':e['sequence'],'reviewer':reviewer,'automatic_review':False}
 def _action_begin_work(self,actor,project_id,task_id):
  self._owned_leaf(actor,task_id);d=self.dynamic();_,_,bundle=self._bundle(actor)
  for parent,revision in self._task(task_id)['dependency_revisions'].items():
   upstream=d['work'][parent]['completion']
   if not upstream or self._task(parent)['revision']!=revision or (upstream['author']!=actor and upstream['patch_id'] not in bundle['included_patch_ids']):self.org_reject('Upstream package must locally complete and exact patch must be adopted','dynamic_dependency_not_ready')
  d['active_work'][actor]=task_id;e=self._event_dynamic(actor,'work_started',task_id=task_id)
  return {'task_id':task_id,'event_sequence':e['sequence'],'owner':actor}
 def _action_complete_work(self,actor,project_id,task_id,patch_id):
  w=self._owned_leaf(actor,task_id);p=self._patch(patch_id)
  if p['author']!=actor or task_id not in p['task_snapshots'] or self.org_current_identity(actor)!=self.org_patch_identity(patch_id):self.org_reject('Publish your exact current work-bound version','dynamic_completion_version')
  test=self._latest_same_version_test(actor,self.org_current_identity(actor))
  if not test or test.get('passed')is not True:self.org_reject('Actual successful same-version public test required','dynamic_completion_test')
  if not w['reviewer']:self.org_reject('Assign independent verification first','dynamic_verification_required')
  w['completion']={'patch_id':patch_id,'author':actor,'identity':self.org_patch_identity(patch_id),'test_sequence':test['sequence'],'task_revision':self._task(task_id)['revision']}
  e=self._event_dynamic(actor,'work_locally_completed',task_id=task_id,completion=w['completion'],official_success_known=False)
  return {'event_sequence':e['sequence'],**copy.deepcopy(w['completion']),'official_score':None}
 def _action_dynamic_status(self,actor,project_id):
  return {'version':VERSION,'work':{k:{**copy.deepcopy(w),'owner':self._task(k)['owner'],'task_revision':self._task(k)['revision'],'depends_on':copy.deepcopy(self._task(k)['depends_on'])} for k,w in self.dynamic()['work'].items()},'active_work':copy.deepcopy(self.dynamic()['active_work']),'collaboration':copy.deepcopy(self.dynamic()['collaboration']),'raw_events':'read_work_event(sequence)'}
 def _closing_steps(self,actor):
  value=super()._closing_steps(actor)
  pending=[]
  for tid,w in self.dynamic()['work'].items():
   if w['children']:continue
   comp=w['completion'];review=self._decision(self._patch(comp['patch_id']),reviewer=w['reviewer']) if comp else None
   if not comp or not self._decision_is_current(review,self._patch(comp['patch_id'])) or review['decision']!='accept':pending.append(tid)
  value.update(requires_independent_review=True,verification_scope='per_contribution_cross_review',dynamic_pending_packages=pending,dynamic_revision=VERSION)
  if pending:
   value['next_explicit_tool']='dynamic_status'
   value['next_explicit_action']={'tool':'dynamic_status','arguments':{},'note':'Read actual work owners, dependencies and contribution verification before closing.'}
  return value
 def _organization_overview(self,actor):
  value=super()._organization_overview(actor)
  value['dynamic_revision']=VERSION;value['independent_review_required']=True;value['verification_scope']='per_contribution_cross_review'
  return value
 def _review_gate(self,actor):
  d=self.dynamic();_,_,bundle=self._bundle(actor);proof=[]
  for tid,w in d['work'].items():
   if w['children']:continue
   complete=w['completion']
   if not complete:self.org_reject('Every real leaf must locally complete','dynamic_unfinished_work')
   p=self._patch(complete['patch_id']);review=self._decision(p,reviewer=w['reviewer'])
   if not self._decision_is_current(review,p) or review['decision']!='accept':self.org_reject('Every contribution needs exact independent review','dynamic_review_required')
   if p['author']!=actor and p['patch_id'] not in bundle['included_patch_ids']:self.org_reject('Explicitly integrate each partner contribution','dynamic_integration_required')
   proof.append({'task_id':tid,'completion':copy.deepcopy(complete),'review':copy.deepcopy(review)})
  return {'kind':'contribution_level_cross_review','not_whole_tree_author_blind_review':True,'packages':proof}

class SoftwareCollaborationPort(previous.SoftwareCollaborationPort):
 def observe(self):
  value=super().observe();value['dynamic_organization']=self._session._world._action_dynamic_status(self.role,PROJECT)
  value['dynamic_contract']='All unfinished work has an owner. Use split_work/assign_work and real offer/accept; begin_work before edits. Dependency completion and adoption gate downstream work. Exact per-package independent cross-review plus final tests are required; this is not whole-tree author-blind review.'
  return value

def attach(prepared,requirements):
 """Only a newly prepared FREE2 world. No existing experiment migration."""
 old=prepared.world
 old.state=old.store.load()
 if old.org_kind()!='FREE2' or old._software()['tasks'] or old._software()['patches'] or old.state['software_events']:raise ValueError('Fresh FREE2 substrate required')
 if len(requirements)<2 or len(set(requirements))!=len(requirements):raise ValueError('Multiple frozen public requirement anchors required')
 session=old.session('member_001',PROJECT)
 created=session.call('create_task',request_key='v211-initial-root-create',task_id='work_root',description='Full unchanged public task; responsibility for all requirement anchors.')
 claimed=session.call('claim_task',request_key='v211-initial-root-claim',task_id='work_root',reason='Frozen initial accountable owner')
 if not created.get('ok') or not claimed.get('ok'):raise ValueError('Failed common preparation; do not expose partially initialized world')
 with old.store.lock():
  old.state=old.store.load()
  if len(requirements)<2 or len(set(requirements))!=len(requirements):raise ValueError('Multiple frozen public requirement anchors required')
  old.__class__=SoftwareCollaborationWorld
  old._software()['dynamic_v211']={'version':VERSION,'requirements':list(requirements),'work':{},'active_work':{},'collaboration':[]}
  old.dynamic()['work']['work_root']={'scope':list(requirements),'children':[],'authors':[],'reviewer':None,'completion':None}
  old.dynamic()['initial_receipts']={'created':created,'claimed':claimed,'author_verification_mode':'contribution_level_cross_review'}
  old.store.save(old.state)
 prepared.prefix['dynamic_organization_revision']=VERSION
 prepared.prefix['dynamic_initial_state_sha256']=digest(json_bytes(old.store.load()))
 atomic_write(Path(old.store.root).parent/'preparation.json',json_bytes(prepared.prefix))
 return prepared
