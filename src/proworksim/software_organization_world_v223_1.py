"""New-batch-only navigation, test-label feedback and explicit decision handoff."""
import copy,importlib.util
from pathlib import Path
from . import software_organization_world_v222 as prior
from .software_fixed_organization_clone_v131 import clone_function
from .software_project_navigation_v223_1 import RepositoryIndex
from .software_project_relations_v223_1 import Projection,synchronize
from .software_runtime_performance_v222_1 import install
from .software_public_feedback_v223_1 import compact
PROJECT=prior.PROJECT;VERSION='v223.1-targeted-managed-interface-r1'
p=Path(__file__).resolve().parents[2]/'tools/public_test_library_v223_1.py';spec=importlib.util.spec_from_file_location('_public_v223_1',p);library=importlib.util.module_from_spec(spec);spec.loader.exec_module(library)

def tool_definitions(case):
 values=copy.deepcopy(prior.tool_definitions(case))
 for t in values:
  if t['name']=='run_tests':t['description']+=' Django labels are relative to tests/ (app.module.Class.method). A redundant tests. prefix is normalized only against the current public tree. Read exact failed-target feedback. Default test feedback gives failure excerpts; complete immutable report pages remain readable.'
  if t['name']=='read_test_result':t['description']+=' Copy a cursor from page.next_cursor or diagnostic_summary.detail_pages; do not invent page hashes. Default feedback is bounded; the body pages retain the complete original evidence.'
  if t['name']=='search_repository':t['description']+=' If complete=false, an empty matches page is NOT a negative search result. Use the exact returned continue_search arguments without changing query/version.'
  if t['name']=='assign_work':t['description']+=' This initial owner offer is distinct from later offer_joint_arrangement; it does not require a previous edit/test, but the actual recipient must accept_transfer and independent review setup must remain valid.'
 return values
class World(prior.World):
 _action_locate_work=clone_function(prior.World._action_locate_work,{**prior.World._action_locate_work.__globals__,'RepositoryIndex':RepositoryIndex,'Projection':Projection,'synchronize':synchronize})
 def _tool_definitions(self,project_id):return tool_definitions(self._software()['case']) if project_id==PROJECT else super()._tool_definitions(project_id)
 def _select(self,actor,selection,*,patch_id=None,evidence_id=None):
  ref=None
  if evidence_id:
   e=self._evidence(evidence_id);view=self.protocol()['evidence_views'].get(actor,{}).get(evidence_id)
   if not view or view['identity']!=e['identity']:self.org_reject('Explicitly adopt the evidence first','evidence_adoption_required')
   ref=e['identity']['source_reference']
  _,_,bundle=self._bundle(actor,patch_id=patch_id,reference=ref)
  try:return library.selected_entry(self.public_test_entry,selection,files=bundle['files'],entry_metadata=bundle['entry_metadata'])[1]
  except ValueError as e:self.org_reject(str(e),'public_test_selection_invalid')
 def _feedback(self,actor,result):
  report=self._software()['test_reports'].get(result.get('report_id'))
  if report is None:raise ValueError('Missing saved test report')
  return compact(report,result,actor)
 def _action_run_tests(self,actor,project_id,selection=None,evidence_id=None):
  chosen=self._select(actor,selection,evidence_id=evidence_id)
  result=super()._action_run_tests(actor,project_id,selection=chosen,evidence_id=evidence_id)
  out=self._feedback(actor,result);out['selection_normalization']={'requested':copy.deepcopy(selection),'executed':chosen,'revision':library.IMPLEMENTATION_REVISION};return out
 def _action_run_patch_review_tests(self,actor,project_id,patch_id,selection=None):
  self._review_permission(actor,patch_id);chosen=self._select(actor,selection,patch_id=patch_id)
  result=super()._action_run_patch_review_tests(actor,project_id,patch_id,selection=chosen)
  out=self._feedback(actor,result);out['selection_normalization']={'requested':copy.deepcopy(selection),'executed':chosen,'revision':library.IMPLEMENTATION_REVISION};return out
 def _action_read_test_result(self,actor,project_id,report_id,cursor=None):return self._feedback(actor,super()._action_read_test_result(actor,project_id,report_id,cursor))
 def _action_search_repository(self,actor,project_id,text,path_prefix=None,cursor=None):
  result=super()._action_search_repository(actor,project_id,text,path_prefix,cursor)
  if not result['complete']:
   args={'text':text,'cursor':result['next_cursor']}
   if path_prefix is not None:args['path_prefix']=path_prefix
   result['search_status']='partial_scan_not_a_negative_result';result['continue_search']={'tool':'search_repository','arguments':args,'same_actor_query_and_version_required':True}
  return result
class Port(prior.Port):
 def observe(self):
  value=super().observe();proposal=self._session._world.protocol().get('proposal') or {}
  if proposal.get('decision_assessment'):
   value['organization_decision_explanation']=copy.deepcopy(proposal['decision_assessment']);value['organization_decision_explanation']['execution_boundary']='KEEP/DEFER retains current scope, owners and dependencies. Old informal transfer plans do not override this selection. Missing verification setup is still allowed.' if proposal.get('keep') else 'A proposal is not consent. Use actual offers, acceptance and current version evidence.'
  return value

def attach(prepared,requirements,*,condition='G'):
 prior.attach(prepared,requirements,condition=condition);prepared.world.__class__=World;install(prepared.world);return prepared
SoftwareCollaborationWorld=World;SoftwareCollaborationPort=Port;register_proposal=prior.register_proposal
