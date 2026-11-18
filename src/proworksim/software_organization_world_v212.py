"""Repairable dynamic work contract. New worlds only; v211 stays immutable.

Readiness, work epochs, evidence-only closure and consented joint owner/reviewer
changes. No hidden scoring, synthetic consent, author erasure or automatic submit.
"""
import copy
from pathlib import Path
from . import software_organization_world_v211 as old
from . import software_role_baseline_world_v141 as substrate
from .software_collaboration_v027 import _tool
from .work_interface import _schema_errors
from .world_core import WorldCore
from .storage import digest,json_bytes,atomic_write
VERSION='v212-repairable-work-r1';PROJECT=old.PROJECT
_ID=old._ID;_TEXT=old._TEXT;_LIST=old._LIST
EXTRA_TOOLS=[
 _tool('work_readiness','Read current setup/dependency gaps before editing. Does not accept or change any assignment.',{'task_id':_ID}),
 _tool('reopen_work','Owner explicitly reopens a locally completed work package for revision. Preserve authors and prior artifacts/tests/reviews; old review cannot endorse the new work epoch.',{'task_id':_ID,'reason':_TEXT}),
 _tool('complete_evidence','Complete a no-code-contribution package using exact public requirement anchors and a successful actual same-version test. Reuse a published code version or unchanged baseline; do not fabricate a code patch.',{'task_id':_ID,'requirements':_LIST,'test_sequence':{'type':'integer','minimum':1},'reason':_TEXT}),
 _tool('adopt_evidence','Explicitly align with a published evidence version. No code is copied; first integrate its existing source patch if needed. Identical bytes alone are not recorded adoption.',{'evidence_id':_ID}),
 _tool('review_evidence','Assigned different checker explicitly accepts or requests changes for an adopted evidence record after actual same-version checks. Preserve failed test results; not whole-tree author-blind review.',{'evidence_id':_ID,'decision':{'type':'string','enum':['accept','request_changes']},'reason':_TEXT}),
 _tool('offer_joint_arrangement','Current owner proposes a complete owner/reviewer/mode arrangement for an unfinished package with no recorded code contribution. Prior owner remains accountable until the recipient explicitly accepts.',{'task_id':_ID,'to_member':_ID,'reviewer':_ID,'mode':{'type':'string','enum':['implementation','evidence']},'expected_revision':{'type':'integer','minimum':1},'reason':_TEXT}),
 _tool('accept_joint_arrangement','Addressed member accepts the exact current owner/reviewer/mode arrangement. Atomically activates the agreed metadata, preserves all history, and records real consent.',{'offer_id':_ID}),
 _tool('decline_joint_arrangement','Addressed member explicitly declines a joint arrangement; current responsibility stays unchanged.',{'offer_id':_ID,'reason':_TEXT}),
 _tool('delivery_checklist','Read missing setup, artifacts/evidence, adoption, review, version freshness and final integration requirements. Never edits, accepts or submits.',{},[]),
]
def tool_definitions(case):return old.tool_definitions(case)+copy.deepcopy(EXTRA_TOOLS)

class SoftwareCollaborationWorld(old.SoftwareCollaborationWorld):
 def dynamic(self):
  d=self._software()['dynamic_v212']
  if d['version']!=VERSION:raise ValueError('Wrong repairable-work revision')
  return d
 def _tool_definitions(self,project_id):return tool_definitions(self._software()['case']) if project_id==PROJECT else super()._tool_definitions(project_id)
 def _event_dynamic(self,actor,kind,**facts):return self._event(actor,'organization_v212:'+kind,**facts)
 def epoch(self,tid):return self.dynamic()['epochs'].get(tid,0)
 def _completion_current(self,tid):
  c=self.dynamic()['work'][tid]['completion']
  return bool(c and c.get('work_epoch')==self.epoch(tid) and all(self.epoch(k)==v for k,v in c.get('dependency_epochs',{}).items()))
 def _dependency_gaps(self,actor,tid):
  d=self.dynamic();_,_,bundle=self._bundle(actor);gaps=[]
  for parent,revision in self._task(tid)['dependency_revisions'].items():
   c=d['work'][parent]['completion']
   if not self._completion_current(parent) or self._task(parent)['revision']!=revision:gaps.append({'kind':'upstream_not_current','task_id':parent});continue
   if c.get('kind')=='evidence':
    if not self._same_contents(actor,c['identity']) or (c['author']!=actor and c['evidence_id'] not in d['evidence_adoptions'].get(actor,{})):gaps.append({'kind':'upstream_evidence_version_not_adopted','task_id':parent,'evidence_id':c['evidence_id']})
   elif c['author']!=actor and c['patch_id'] not in bundle['included_patch_ids']:gaps.append({'kind':'upstream_patch_not_adopted','task_id':parent,'patch_id':c['patch_id']})
  return gaps
 def _same_contents(self,actor,identity):
  current=self.org_current_identity(actor)
  return all(current[k]==identity[k] for k in ('files_sha256','entry_metadata_sha256'))
 def _action_work_readiness(self,actor,project_id,task_id):
  d=self.dynamic();w=d['work'].get(task_id);gaps=[]
  if not w or w['children']:return {'ready':False,'gaps':[{'kind':'leaf_required'}]}
  owner=self._task(task_id)['owner'];reviewer=w['reviewer']
  if actor!=owner:gaps.append({'kind':'not_owner','owner':owner})
  if reviewer not in self.live_members() or reviewer==owner or reviewer in w['authors']:gaps.append({'kind':'independent_reviewer_missing_or_invalid','next_tool':'assign_verification'})
  if reviewer and any(edge not in d['collaboration'] for edge in ([task_id,owner,reviewer],[task_id,reviewer,owner])):gaps.append({'kind':'collaboration_missing','next_tool':'add_collaboration'})
  if w['completion'] is not None:gaps.append({'kind':'completed_or_stale_package_requires_reopen','next_tool':'reopen_work'})
  gaps+=self._dependency_gaps(actor,task_id)
  return {'task_id':task_id,'owner':owner,'reviewer':reviewer,'mode':d['modes'].get(task_id,'implementation'),'work_epoch':self.epoch(task_id),'ready':not gaps,'gaps':gaps,'no_automatic_assignment':True}
 def _require_ready(self,actor,tid):
  r=self._action_work_readiness(actor,PROJECT,tid)
  if not r['ready']:self.org_reject('Finish explicit setup/current dependencies before code work','work_setup_incomplete',readiness=r)
  return r
 def _tool_project_action(self,actor,project_id,tool,arguments,interface_profile=None):
  if tool in {t['name'] for t in EXTRA_TOOLS}:
   if actor not in self.live_members() or project_id!=PROJECT:self.org_reject('Actual actor required','dynamic_identity')
   if getattr(self,'fixed_candidates_closed',False):self.org_reject('Candidate already locked','fixed_candidates_closed')
   if getattr(self,'require_scheduled_actions',False) and getattr(self,'scheduled_member',None)!=actor:self.org_reject('Scheduled opportunity required','fixed_organization_schedule')
   spec=next(x for x in EXTRA_TOOLS if x['name']==tool);errors=_schema_errors(spec['parameters'],arguments)
   if errors:self.org_reject('; '.join(errors),'public_argument_schema')
   result=WorldCore._tool_project_action(self,actor,project_id,tool,arguments,interface_profile);self._assert_responsibility();return result
  if tool in old.EDIT_TOOLS:
   tid=self.dynamic()['active_work'].get(actor)
   if tid:
    r=self._require_ready(actor,tid)
    if r['mode']=='evidence':self.org_reject('Evidence-only package cannot silently become code work','evidence_only_no_edit')
  return super()._tool_project_action(actor,project_id,tool,arguments,interface_profile)
 def _action_begin_work(self,actor,project_id,task_id):
  r=self._require_ready(actor,task_id)
  if r['mode']=='evidence':self.org_reject('Run actual checks and complete_evidence; no edit context is created','evidence_only_no_edit')
  self.dynamic()['active_work'][actor]=task_id;e=self._event_dynamic(actor,'work_started',task_id=task_id,work_epoch=self.epoch(task_id))
  return {'task_id':task_id,'owner':actor,'event_sequence':e['sequence']}
 def _action_fix_patch(self,actor,project_id,task_ids,message):
  result=super()._action_fix_patch(actor,project_id,task_ids,message)
  self.dynamic()['artifact_epochs'][result['patch_id']]={tid:self.epoch(tid) for tid in task_ids}
  self._event_dynamic(actor,'artifact_epoch_bound',patch_id=result['patch_id'],work_epochs=self.dynamic()['artifact_epochs'][result['patch_id']])
  return result
 def _artifact_current(self,patch):
  epochs=self.dynamic()['artifact_epochs'].get(patch['patch_id'])
  return epochs is not None and all(self.epoch(k)==v for k,v in epochs.items())
 def _decision_is_current(self,decision,patch):
  return bool(super()._decision_is_current(decision,patch) and self._artifact_current(patch) and all(decision['event_sequence']>self.dynamic()['reopened_at'].get(k,0) for k in patch['task_snapshots']))
 def _fresh_test(self,actor,identity,tids,*,must_pass=False):
  test=self._latest_same_version_test(actor,identity)
  cutoff=max((self.dynamic()['reopened_at'].get(tid,0) for tid in tids),default=0)
  if test is None or test['sequence']<=cutoff or (must_pass and test.get('passed')is not True):self.org_reject('Current work revision needs actual same-version test evidence','work_revision_test_required')
  return test
 def _action_org_review_patch(self,actor,project_id,patch_id,decision,reason):
  patch=self._patch(patch_id)
  if not self._artifact_current(patch):self.org_reject('Publish a candidate for the reopened work revision','stale_work_revision')
  if decision=='accept':self._fresh_test(actor,self.org_current_identity(actor),patch['task_snapshots'])
  return super()._action_org_review_patch(actor,project_id,patch_id,decision,reason)
 def _action_complete_work(self,actor,project_id,task_id,patch_id):
  if not self._artifact_current(self._patch(patch_id)):self.org_reject('Current work-epoch candidate required','stale_work_revision')
  self._fresh_test(actor,self.org_current_identity(actor),[task_id],must_pass=True)
  result=super()._action_complete_work(actor,project_id,task_id,patch_id)
  c=self.dynamic()['work'][task_id]['completion'];c.update(kind='code',work_epoch=self.epoch(task_id),dependency_epochs={k:self.epoch(k) for k in self._task(task_id)['depends_on']})
  self._event_dynamic(actor,'completion_epoch_bound',task_id=task_id,completion=copy.deepcopy(c));return {**result,**copy.deepcopy(c)}
 def _action_reopen_work(self,actor,project_id,task_id,reason):
  w=self._owned_leaf(actor,task_id,allow_complete=True)
  if w['completion'] is None:self.org_reject('Only locally completed/stale completion needs reopening','work_not_completed')
  d=self.dynamic();previous=copy.deepcopy(w['completion']);d['history'].append({'task_id':task_id,'completion':previous,'authors':list(w['authors'])})
  w['completion']=None;d['epochs'][task_id]=self.epoch(task_id)+1;d['active_work'].pop(actor,None)
  e=self._event_dynamic(actor,'work_reopened',task_id=task_id,work_epoch=self.epoch(task_id),previous_completion=previous,authors_preserved=w['authors'],reason=reason)
  d['reopened_at'][task_id]=e['sequence'];return {'event_sequence':e['sequence'],'work_epoch':self.epoch(task_id),'authors':list(w['authors']),'prior_artifacts_tests_reviews_retained':True}
 def _action_offer_joint_arrangement(self,actor,project_id,task_id,to_member,reviewer,mode,expected_revision,reason):
  w=self._owned_leaf(actor,task_id);task=self._task(task_id)
  if w['authors']:self.org_reject('Authored work cannot use the unstarted-work joint path','joint_authored_work_unsupported')
  self._available_recipient(actor,to_member)
  if reviewer not in self.live_members() or reviewer==to_member:self.org_reject('Target owner and verifier must differ','joint_invalid_reviewer')
  if task['revision']!=expected_revision:self.org_reject('Task revision changed','joint_stale')
  d=self.dynamic();oid='joint-'+str(len(d['joint_offers'])+1)
  row={'offer_id':oid,'task_id':task_id,'from_member':actor,'to_member':to_member,'reviewer':reviewer,'mode':mode,'task_revision':expected_revision,'work_epoch':self.epoch(task_id),'previous_reviewer':w['reviewer'],'status':'pending','reason':reason}
  d['joint_offers'][oid]=row;e=self._event_dynamic(actor,'joint_offered',**copy.deepcopy(row));return {**copy.deepcopy(row),'event_sequence':e['sequence'],'owner_unchanged':True}
 def _action_accept_joint_arrangement(self,actor,project_id,offer_id):
  d=self.dynamic();o=d['joint_offers'].get(offer_id)
  if not o or o['status']!='pending' or o['to_member']!=actor:self.org_reject('Choose your pending joint offer','joint_invalid_offer')
  task=self._task(o['task_id']);w=d['work'][o['task_id']]
  if task['owner']!=o['from_member'] or task['revision']!=o['task_revision'] or self.epoch(o['task_id'])!=o['work_epoch'] or w['reviewer']!=o['previous_reviewer'] or w['authors'] or w['completion']:self.org_reject('Joint offer became stale; keep current responsibility','joint_stale')
  if o['reviewer']==actor or o['reviewer']not in self.live_members():self.org_reject('Invalid new reviewer','joint_invalid_reviewer')
  task['owner']=actor;w['reviewer']=o['reviewer'];d['modes'][o['task_id']]=o['mode'];o['status']='accepted'
  for m,tid in list(d['active_work'].items()):
   if tid==o['task_id']:d['active_work'].pop(m)
  e=self._event_dynamic(actor,'joint_accepted',**copy.deepcopy(o),previous_owner=o['from_member'],owner=actor,authors_preserved=w['authors'])
  return {'event_sequence':e['sequence'],'task_id':o['task_id'],'owner':actor,'reviewer':w['reviewer'],'mode':o['mode'],'authors':list(w['authors'])}
 def _action_decline_joint_arrangement(self,actor,project_id,offer_id,reason):
  o=self.dynamic()['joint_offers'].get(offer_id)
  if not o or o['status']!='pending' or o['to_member']!=actor:self.org_reject('Choose your pending offer','joint_invalid_offer')
  o.update(status='declined',decline_reason=reason);e=self._event_dynamic(actor,'joint_declined',**copy.deepcopy(o));return {'event_sequence':e['sequence'],'owner_unchanged':True}
 def _action_complete_evidence(self,actor,project_id,task_id,requirements,test_sequence,reason):
  w=self._owned_leaf(actor,task_id);self._require_ready(actor,task_id)
  if w['authors']:self.org_reject('Preserve authored contribution through complete_work','evidence_cannot_erase_author')
  if sorted(requirements)!=sorted(w['scope']):self.org_reject('Bind every frozen requirement of this package','evidence_scope_mismatch')
  own=self.org_current_identity(actor);test=self._fresh_test(actor,own,[task_id],must_pass=True)
  if test['sequence']!=test_sequence:self.org_reject('Use actual latest same-version test sequence','evidence_test_reference')
  _,_,base_bundle=self._bundle(actor,baseline=True);baseline_hash=digest(json_bytes(base_bundle['files']));candidates=[p for p in self._software()['patches'].values() if all(p[k]==own[k] for k in ('files_sha256','entry_metadata_sha256'))]
  if candidates:
   source=candidates[-1];identity=self.org_patch_identity(source['patch_id']);source_patch=source['patch_id']
  elif own['files_sha256']==baseline_hash:
   artifact,version,_=self._bundle(actor,baseline=True);identity={**own,'source_reference':{'object_id':artifact['artifact_id'],'version_id':version}};source_patch=None
  else:self.org_reject('Publish actual changed code in its own package first; evidence cannot launder unpublished changes','evidence_source_not_fixed')
  d=self.dynamic();eid='evidence-'+str(len(d['evidence'])+1)
  evidence={'evidence_id':eid,'task_id':task_id,'checker':actor,'requirements':list(requirements),'identity':identity,'source_patch_id':source_patch,'source_code_author':source['author'] if source_patch else None,'owner_test':self._test_summary(test),'work_epoch':self.epoch(task_id),'reason':reason,'new_code_patch_created':False}
  d['evidence'][eid]=evidence;w['completion']={'kind':'evidence','evidence_id':eid,'author':actor,'identity':identity,'source_patch_id':source_patch,'work_epoch':self.epoch(task_id),'dependency_epochs':{k:self.epoch(k) for k in self._task(task_id)['depends_on']}}
  e=self._event_dynamic(actor,'evidence_completed',**copy.deepcopy(evidence));return {**copy.deepcopy(evidence),'event_sequence':e['sequence']}
 def _evidence(self,eid):
  e=self.dynamic()['evidence'].get(eid)
  if not e:self.org_reject('Unknown published evidence','evidence_unknown')
  if self.epoch(e['task_id'])!=e['work_epoch']:self.org_reject('Evidence belongs to an old work revision','evidence_stale')
  return e
 def _action_adopt_evidence(self,actor,project_id,evidence_id):
  e=self._evidence(evidence_id);_,_,bundle=self._bundle(actor)
  if not self._same_contents(actor,e['identity']):self.org_reject('Align with the immutable evidence version using its existing source patch','evidence_version_not_aligned',source_patch_id=e['source_patch_id'])
  if e['source_patch_id'] and e['source_code_author']!=actor and e['source_patch_id'] not in bundle['included_patch_ids']:self.org_reject('Explicitly integrate the source contribution before evidence adoption','evidence_source_not_adopted')
  current=self.org_current_identity(actor);self.dynamic()['evidence_adoptions'].setdefault(actor,{})[evidence_id]=current
  event=self._event_dynamic(actor,'evidence_adopted',evidence_id=evidence_id,identity=current,source_identity=e['identity']);return {'event_sequence':event['sequence'],'no_code_copied':True}
 def _action_review_evidence(self,actor,project_id,evidence_id,decision,reason):
  e=self._evidence(evidence_id);w=self.dynamic()['work'][e['task_id']]
  if actor==e['checker'] or actor!=w['reviewer'] or actor in w['authors']:self.org_reject('Assigned independent evidence checker required','evidence_self_review')
  test=None
  if decision=='accept':
   adopted=self.dynamic()['evidence_adoptions'].get(actor,{}).get(evidence_id)
   if not adopted or adopted!=self.org_current_identity(actor) or not self._same_contents(actor,e['identity']):self.org_reject('Explicitly adopt this exact evidence version','evidence_adoption_required')
   test=self._fresh_test(actor,self.org_current_identity(actor),[e['task_id']])
  record={'evidence_id':evidence_id,'task_id':e['task_id'],'reviewer':actor,'decision':decision,'reason':reason,'work_epoch':e['work_epoch'],'test_evidence':self._test_summary(test),'source_code_author_retained':e['source_code_author'],'not_whole_tree_author_blind_review':True}
  event=self._event_dynamic(actor,'evidence_reviewed',**copy.deepcopy(record));record['event_sequence']=event['sequence'];self.dynamic()['evidence_reviews'].append(record);return copy.deepcopy(record)
 def _review_for_completion(self,tid):
  d=self.dynamic();w=d['work'][tid];c=w['completion']
  if not self._completion_current(tid):return None
  if c.get('kind')=='evidence':
   found=[r for r in d['evidence_reviews'] if r['evidence_id']==c['evidence_id'] and r['reviewer']==w['reviewer'] and r['work_epoch']==self.epoch(tid)]
   return found[-1] if found else None
  p=self._patch(c['patch_id']);r=self._decision(p,reviewer=w['reviewer'])
  return r if self._decision_is_current(r,p) else None
 def _action_delivery_checklist(self,actor,project_id):
  d=self.dynamic();_,_,bundle=self._bundle(actor);items=[]
  for tid,w in d['work'].items():
   if w['children']:continue
   gaps=[];c=w['completion'];review=self._review_for_completion(tid)
   if not w['reviewer']:gaps.append('assign_verification')
   if not self._completion_current(tid):gaps.append('complete_current_code_or_evidence' if c is None else 'reopen_stale_completion')
   if not review or review['decision']!='accept':gaps.append('independent_current_review')
   if c and c.get('kind')=='evidence':
    if not self._same_contents(actor,c['identity']):gaps.append('evidence_version_differs_from_final_tree_revalidate')
   elif c and c['author']!=actor and c['patch_id'] not in bundle['included_patch_ids']:gaps.append('integrate_partner_patch')
   items.append({'task_id':tid,'scope':w['scope'],'owner':self._task(tid)['owner'],'reviewer':w['reviewer'],'work_epoch':self.epoch(tid),'completion':copy.deepcopy(c),'missing':gaps})
  return {'version':VERSION,'for_actor':actor,'packages':items,'package_chain_ready':all(not x['missing'] for x in items),'final_fix_test_submit_still_explicit':True,'no_automatic_effect':True}
 def _closing_steps(self,actor):
  value=substrate.SoftwareCollaborationWorld._closing_steps(self,actor);check=self._action_delivery_checklist(actor,PROJECT)
  value.update(requires_independent_review=True,dynamic_revision=VERSION,verification_scope='code_contribution_or_evidence_cross_review',delivery_checklist=check)
  if not check['package_chain_ready']:value.update(next_explicit_tool='delivery_checklist',next_explicit_action={'tool':'delivery_checklist','arguments':{},'note':'Resolve actual package gaps; no automatic completion.'})
  return value
 def _review_gate(self,actor):
  check=self._action_delivery_checklist(actor,PROJECT)
  if not check['package_chain_ready']:self.org_reject('Package/code/evidence chain still incomplete','repairable_delivery_incomplete',checklist=check)
  return {'kind':'repairable_contribution_and_evidence_cross_review','packages':[{'task_id':x['task_id'],'completion':x['completion'],'review':copy.deepcopy(self._review_for_completion(x['task_id']))} for x in check['packages']],'not_whole_tree_author_blind_review':True}
 def _organization_overview(self,actor):
  value=super()._organization_overview(actor);value['dynamic_revision']=VERSION;return value
 def _action_dynamic_status(self,actor,project_id):
  value=super()._action_dynamic_status(actor,project_id);value['version']=VERSION
  for tid,w in value['work'].items():w.update(work_epoch=self.epoch(tid),mode=self.dynamic()['modes'].get(tid,'implementation'),completion_current=self._completion_current(tid) if not w['children'] else False)
  value['joint_offers']=copy.deepcopy(self.dynamic()['joint_offers']);value['delivery_gaps']=self._action_delivery_checklist(actor,project_id)
  return value

class SoftwareCollaborationPort(old.SoftwareCollaborationPort):
 def observe(self):
  v=super().observe();v['dynamic_contract']='Repairable v212 contract: work_readiness before edits, explicit reopen_work for revisions, complete_evidence for no-code work, jointly accepted owner/reviewer changes only for unmodified remaining packages. Preserve authors and old evidence. delivery_checklist is read-only. Old FREE2/v211 hints never bypass these rules.';return v

def attach(prepared,requirements):
 old.attach(prepared,requirements);world=prepared.world
 with world.store.lock():
  world.state=world.store.load();d=world._software().pop('dynamic_v211');d.update(version=VERSION,epochs={},reopened_at={},history=[],artifact_epochs={},modes={},joint_offers={},evidence={},evidence_adoptions={},evidence_reviews=[])
  world.__class__=SoftwareCollaborationWorld;world._software()['dynamic_v212']=d;world.store.save(world.state)
 prepared.prefix.update(dynamic_organization_revision=VERSION,dynamic_initial_state_sha256=digest(json_bytes(world.store.load())))
 atomic_write(Path(world.store.root).parent/'preparation.json',json_bytes(prepared.prefix));return prepared
