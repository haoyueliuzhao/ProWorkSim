"""Exact published-candidate review without merging away a reviewer's own work.

Review tests use the existing isolated public-test callback and an immutable
published source. Main workspaces, authors, code completion and final adoption
remain unchanged. No hidden evaluator or automatic approval is introduced.
"""
import copy
from pathlib import Path
from . import software_organization_world_v212 as old
from .software_collaboration_v027 import _tool
from .software_benchmark_public_tests_v110 import SELECTION_SCHEMA
from .world_core import WorldCore
from .work_interface import _schema_errors
from .storage import digest,json_bytes,atomic_write
VERSION='v213-published-candidate-review-r1';PROJECT=old.PROJECT
EXTRA_TOOLS=[
 _tool('open_patch_review','Explicitly open an immutable published candidate for review without replacing or merging your own working tree. Read source with read_file(patch_id=...). Final integration remains separate.',{'patch_id':old._ID}),
 _tool('run_patch_review_tests','Run actual public tests on your explicitly opened immutable candidate. Uses the same isolated public runner and team test budget; preserves your main workspace. Record accept/request_changes separately with org_review_patch.',{'patch_id':old._ID,'selection':copy.deepcopy(SELECTION_SCHEMA)},['patch_id']),
]
def tool_definitions(case):
 values=old.tool_definitions(case)+copy.deepcopy(EXTRA_TOOLS)
 for value in values:
  if value['name']=='org_review_patch':value['description']='Record explicit independent accept/request_changes for the exact published candidate. Accept after open_patch_review + run_patch_review_tests, OR exact main-workspace integration and testing. Review never performs final integration.'
 return values
class SoftwareCollaborationWorld(old.SoftwareCollaborationWorld):
 def dynamic(self):
  d=self._software()['dynamic_v213']
  if d['version']!=VERSION:raise ValueError('Wrong published review revision')
  return d
 def _event_dynamic(self,actor,kind,**facts):return self._event(actor,'organization_v213:'+kind,**facts)
 def _tool_definitions(self,project_id):return tool_definitions(self._software()['case']) if project_id==PROJECT else super()._tool_definitions(project_id)
 def _bundle(self,actor,*,patch_id=None,reference=None,write=False,baseline=False):
  focus=getattr(self,'_read_only_review_focus',None)
  if focus and actor==focus['actor'] and patch_id is None and reference is None and not baseline:
   if write:raise ValueError('Immutable review test cannot edit main workspace')
   patch_id=focus['patch_id']
  return super()._bundle(actor,patch_id=patch_id,reference=reference,write=write,baseline=baseline)
 def _tool_project_action(self,actor,project_id,tool,arguments,interface_profile=None):
  if tool in {t['name'] for t in EXTRA_TOOLS}:
   if actor not in self.live_members() or project_id!=PROJECT:self.org_reject('Actual actor required','dynamic_identity')
   if getattr(self,'fixed_candidates_closed',False):self.org_reject('Candidate locked','fixed_candidates_closed')
   if getattr(self,'require_scheduled_actions',False) and getattr(self,'scheduled_member',None)!=actor:self.org_reject('Scheduled opportunity required','fixed_organization_schedule')
   spec=next(t for t in EXTRA_TOOLS if t['name']==tool);errors=_schema_errors(spec['parameters'],arguments)
   if errors:self.org_reject('; '.join(errors),'public_argument_schema')
   return WorldCore._tool_project_action(self,actor,project_id,tool,arguments,interface_profile)
  return super()._tool_project_action(actor,project_id,tool,arguments,interface_profile)
 def _review_permission(self,actor,patch_id):
  p=self._patch(patch_id);self._bundle(actor,reference=p['source_reference'])
  if not p['task_snapshots'] or actor==p['author']:self.org_reject('Another author and real work scope required','dynamic_self_review')
  for tid in p['task_snapshots']:
   w=self.dynamic()['work'][tid]
   if w['reviewer']!=actor or actor in w['authors']:self.org_reject('Assigned non-author reviewer required','dynamic_self_review')
  if not self._artifact_current(p):self.org_reject('Candidate belongs to an old work revision','stale_work_revision')
  self._task_revisions(p);return p
 def _action_open_patch_review(self,actor,project_id,patch_id):
  p=self._review_permission(actor,patch_id);identity=self.org_patch_identity(patch_id)
  e=self._event_dynamic(actor,'published_review_opened',patch_id=patch_id,identity=identity,main_workspace_unchanged=True,not_final_integration=True)
  row={'patch_id':patch_id,'identity':identity,'event_sequence':e['sequence']}
  self.dynamic()['review_views'].setdefault(actor,{})[patch_id]=row
  return {**copy.deepcopy(row),'changed_paths':p['changed_paths'],'next_actions':['read_file with patch_id','run_patch_review_tests','org_review_patch'],'main_workspace_unchanged':True,'final_integrate_patch_still_required':True}
 def _action_run_patch_review_tests(self,actor,project_id,patch_id,selection=None):
  p=self._review_permission(actor,patch_id);view=self.dynamic()['review_views'].get(actor,{}).get(patch_id)
  if not view or view['identity']!=self.org_patch_identity(patch_id):self.org_reject('Explicitly open the published candidate first','review_view_required')
  if getattr(self,'_read_only_review_focus',None):raise ValueError('Single-writer review runner')
  before=self.org_current_identity(actor);self._read_only_review_focus={'actor':actor,'patch_id':patch_id}
  try:
   result=super()._action_run_tests(actor,project_id,selection)
   test=self._latest_same_version_test(actor,view['identity'])
   if not test:raise ValueError('Review callback lost exact published-source identity')
  finally:self._read_only_review_focus=None
  if self.org_current_identity(actor)!=before:raise ValueError('Review modified main workspace')
  self._event_dynamic(actor,'published_review_tested',patch_id=patch_id,test_sequence=test['sequence'],passed=test['passed'],source_identity=view['identity'],main_identity=before,main_workspace_unchanged=True)
  return {**result,'review_patch_id':patch_id,'main_workspace_unchanged':True,'final_integrate_patch_still_required':True}
 def _action_org_review_patch(self,actor,project_id,patch_id,decision,reason):
  view=self.dynamic()['review_views'].get(actor,{}).get(patch_id)
  if decision!='accept' or not view:return super()._action_org_review_patch(actor,project_id,patch_id,decision,reason)
  p=self._review_permission(actor,patch_id);identity=self.org_patch_identity(patch_id)
  if not reason.strip():self.org_reject('Explicit review reason required','invalid_review_decision')
  test=self._fresh_test(actor,identity,p['task_snapshots'])
  if test['sequence']<=view['event_sequence']:self.org_reject('Test this opened candidate before accepting','review_view_test_required')
  row={'review_id':'review-'+str(len(self.org_state()['reviews'])+1),'patch_id':patch_id,'actor_id':actor,'author':p['author'],'identity':identity,'task_revisions':self._task_revisions(p),'decision':decision,'reason':reason,'adopted_source_reference':identity['source_reference'],'adoption_kind':'explicit_immutable_review_view','test_evidence':self._test_summary(test),'rework_responsible':None,'automatic_integration':False,'main_workspace_adopted':False,'public_test_is_official_score':False}
  e=self._event(actor,'organization_v141:candidate_reviewed',**copy.deepcopy(row));row.update(event_sequence=e['sequence'],logical_time=e['logical_time']);self.org_state()['reviews'].append(row);return copy.deepcopy(row)
 def _fresh_test(self,actor,identity,tids,*,must_pass=False):
  test=self._latest_same_version_test(actor,identity);cutoff=max((self.dynamic()['reopened_at'].get(tid,0) for tid in tids),default=0)
  if test is None:self.org_reject('No executed public test for this exact version','work_test_missing',required_identity=identity,next_tool='run_tests')
  if test['sequence']<=cutoff:self.org_reject('Test predates the reopened work revision','work_test_stale',test_sequence=test['sequence'],reopened_after_sequence=cutoff,next_tool='run_tests')
  if must_pass and test.get('passed') is not True:
   self.org_reject('This exact-version test exists but failed; another publication cannot turn it into a pass. Inspect saved output, repair applicable failures or explicitly select justified public checks. Do not report failure as success.','work_test_failed',test_evidence=self._test_summary(test),selection=test.get('public_test_selection'),next_tool='read_test_result',same_version_evidence_present=True)
  return test
 def _action_reopen_work(self,actor,project_id,task_id,reason):
  v=super()._action_reopen_work(actor,project_id,task_id,reason);v['next_explicit_action']={'tool':'begin_work','arguments':{'task_id':task_id}};return v
 def _action_offer_joint_arrangement(self,actor,project_id,**arguments):
  events=self.state['software_events'];edits=[e['sequence'] for e in events if e['kind']=='organization_v213:work_performed']
  if not edits or not any(e['kind']=='test' and e.get('executed') is True and e['sequence']>min(edits) for e in events):self.org_reject('Joint remaining-work adaptation requires actual code progress followed by an executed public test','joint_progress_required')
  return super()._action_offer_joint_arrangement(actor,project_id,**arguments)
 def _organization_overview(self,actor):
  v=super()._organization_overview(actor);v['dynamic_revision']=VERSION;v['published_candidate_review']='open_patch_review -> run_patch_review_tests -> org_review_patch; main workspace remains private and unchanged. Final integrate_patch remains mandatory.';return v
 def _closing_steps(self,actor):
  v=super()._closing_steps(actor);v['dynamic_revision']=VERSION;return v
 def _action_delivery_checklist(self,actor,project_id):
  v=super()._action_delivery_checklist(actor,project_id);v['version']=VERSION;return v
 def _action_dynamic_status(self,actor,project_id):
  v=super()._action_dynamic_status(actor,project_id);v['version']=VERSION;v['review_views']=copy.deepcopy(self.dynamic()['review_views'].get(actor,{}));return v

class SoftwareCollaborationPort(old.SoftwareCollaborationPort):
 def observe(self):
  v=super().observe();v['dynamic_contract']+=' v213: review immutable published candidates without discarding your own edits using open_patch_review and run_patch_review_tests, then explicitly org_review_patch. Review is not final integration. Joint arrangement requires actual code progress followed by a test.';return v

def attach(prepared,requirements):
 old.attach(prepared,requirements);w=prepared.world
 with w.store.lock():
  w.state=w.store.load();d=w._software().pop('dynamic_v212');d.update(version=VERSION,review_views={});w.__class__=SoftwareCollaborationWorld;w._software()['dynamic_v213']=d;w.store.save(w.state)
 prepared.prefix.update(dynamic_organization_revision=VERSION,dynamic_initial_state_sha256=digest(json_bytes(w.store.load())))
 atomic_write(Path(w.store.root).parent/'preparation.json',json_bytes(prepared.prefix));return prepared
