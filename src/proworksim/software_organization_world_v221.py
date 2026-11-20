"""Opt-in managed navigation/evidence tools; original world/version guards retained."""
import copy
from . import software_organization_world_v216_2 as old
from .software_collaboration_v027 import _tool
from .work_interface import _schema_errors
from .world_core import WorldCore
from .software_project_navigation_v221 import RepositoryIndex
from .software_project_relations_v217 import Projection,synchronize,allowed_event
from .software_public_requirement_evidence_v221 import bind_check,summarize
PROJECT=old.PROJECT
TEXT={'type':'string','minLength':1,'maxLength':2000}
TOOLS=[
 _tool('locate_work','Find authorized files/symbols using global lexical discovery plus version-bound project relations and static import/reference candidates. Suggestions are not proven causes. Use returned read_file range to inspect. Existing global search remains available.',{'query':TEXT,'patch_id':{'type':'string','minLength':1},'task_id':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':12},'max_chars':{'type':'integer','minimum':1500,'maximum':12000}},['query']),
 _tool('record_public_check','Bind a public requirement claim to your actual executed test and its exact source version. Does not certify semantic coverage, execute tests, accept review or submit. A passing module is not proof of the issue example.',{'requirement_id':TEXT,'test_sequence':{'type':'integer','minimum':1},'check_path':TEXT,'public_input':TEXT,'expected_result':TEXT}),
 _tool('public_check_status','Inspect your authorized requirement-test bindings, version freshness and unverified coverage. Never imports official score or peer private tests. Optional patch_id compares against that authorized fixed source rather than your own workspace.',{'patch_id':{'type':'string','minLength':1}},[])]

def tool_definitions(case):return old.tool_definitions(case)+copy.deepcopy(TOOLS)
class World(old.World):
 def _tool_definitions(self,project_id):return tool_definitions(self._software()['case']) if project_id==PROJECT else super()._tool_definitions(project_id)
 def _tool_project_action(self,actor,project_id,tool,arguments,interface_profile=None):
  if tool in {t['name'] for t in TOOLS}:
   if actor not in self.live_members() or project_id!=PROJECT:self.org_reject('Actual registered member required','navigation_identity')
   if getattr(self,'fixed_candidates_closed',False):self.org_reject('Candidates locked','fixed_candidates_closed')
   if getattr(self,'require_scheduled_actions',False) and getattr(self,'scheduled_member',None)!=actor:self.org_reject('Scheduled member required','fixed_organization_schedule')
   errors=_schema_errors(next(t for t in TOOLS if t['name']==tool)['parameters'],arguments)
   if errors:self.org_reject('; '.join(errors),'public_argument_schema')
   if tool=='record_public_check':
    if self.protocol()['terminal'] is not None:self.org_reject('Episode terminal','episode_terminal')
    if self.protocol().get('proposal') and self.protocol().get('choice') is None:self.org_reject('Explicit organization choice first','explicit_arrangement_choice_required')
   return WorldCore._tool_project_action(self,actor,project_id,tool,arguments,interface_profile)
  return super()._tool_project_action(actor,project_id,tool,arguments,interface_profile)
 def _action_locate_work(self,actor,project_id,query,task_id=None,limit=8,max_chars=8000,patch_id=None):
  # Mandatory permission resolution precedes all caches, every time.
  artifact,version,bundle=self._bundle(actor,patch_id=patch_id)
  ref={'object_id':artifact['artifact_id'],'version_id':version}
  if task_id is not None and task_id not in self.dynamic()['work']:raise ValueError('Unknown public work package')
  if not hasattr(self,'_navigation_indices'):self._navigation_indices={}
  index=self._navigation_indices.setdefault(actor,RepositoryIndex(actor))
  if index.reference!=ref:index.update(bundle['files'],ref,entry_metadata=bundle.get('entry_metadata'))
  if not hasattr(self,'_navigation_projections'):self._navigation_projections={}
  projection=self._navigation_projections.setdefault(actor,Projection(actor));graph=synchronize(projection,self,[])
  result=index.query(query,project=graph,task_id=task_id,limit=limit,max_chars=max_chars-300 if max_chars>=1800 else max_chars)
  if patch_id:
   for hit in result['hits']:hit['next_read']['arguments']['patch_id']=patch_id
   result['fixed_patch_id']=patch_id
  import json
  while len(json.dumps(result,ensure_ascii=False))>max_chars and result['hits']:result['hits'].pop();result['omitted_results']+=1
  self._event(actor,'navigation_v221:located',query=query,task_id=task_id,source_reference=ref,result_paths=[h['path'] for h in result['hits']],index_id=result['source_id'],no_workspace_change=True)
  return result
 def _action_record_public_check(self,actor,project_id,requirement_id,test_sequence,check_path,public_input,expected_result):
  event=next((e for e in self.state['software_events'] if e['sequence']==test_sequence),None)
  if not event or allowed_event(self,event,actor) is None:raise ValueError('Test event unavailable to actor')
  _,_,bundle=self._bundle(actor,reference=event.get('source_reference'))
  row=bind_check(actor=actor,requirement_id=requirement_id,requirements=self.dynamic()['requirements'],test_event=event,check_path=check_path,source_files=bundle['files'],public_input=public_input,expected_result=expected_result)
  e=self._event(actor,'navigation_v221:public_check_bound',**copy.deepcopy({k:v for k,v in row.items() if k!='actor'}));row['binding_sequence']=e['sequence']
  self._software().setdefault('navigation_v221',{'version':'v221-navigation-evidence-r1','checks':[]})['checks'].append(row);return copy.deepcopy(row)
 def _action_public_check_status(self,actor,project_id,patch_id=None):
  self._bundle(actor,patch_id=patch_id)
  visible=[r for r in self._software().get('navigation_v221',{}).get('checks',[]) if r['actor']==actor]
  identity=self.org_patch_identity(patch_id) if patch_id else self.org_current_identity(actor)
  result=summarize(self.dynamic()['requirements'],visible,identity);result['comparison_target']={'patch_id':patch_id,'identity':identity,'kind':'fixed_patch' if patch_id else 'actor_current_workspace'};return result
class Port(old.Port):pass

def attach(prepared,requirements):
 old.attach(prepared,requirements);prepared.world.__class__=World;w=prepared.world
 with w.store.lock():
  w.state=w.store.load();w._software()['navigation_v221']={'version':'v221-navigation-evidence-r1','checks':[]};w.store.save(w.state)
 return prepared
SoftwareCollaborationPort=Port;SoftwareCollaborationWorld=World;register_proposal=old.register_proposal
