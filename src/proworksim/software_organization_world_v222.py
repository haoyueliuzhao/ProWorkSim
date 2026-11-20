"""Matched 57-tool L/G world: only information routing differs."""
import copy,json,time
from . import software_organization_world_v221 as prior
from .software_project_navigation_v221 import RepositoryIndex
from .software_project_relations_v217 import Projection,synchronize
from .software_project_information_v222 import type_relations,estimated_object_bytes
PROJECT=prior.PROJECT;tool_definitions=prior.tool_definitions
class World(prior.World):
 def _action_locate_work(self,actor,project_id,query,task_id=None,limit=8,max_chars=8000,patch_id=None):
  started=time.perf_counter();artifact,version,bundle=self._bundle(actor,patch_id=patch_id);ref={'object_id':artifact['artifact_id'],'version_id':version}
  if task_id is not None and task_id not in self.dynamic()['work']:raise ValueError('Unknown work package')
  if not hasattr(self,'_navigation_indices'):self._navigation_indices={}
  index=self._navigation_indices.setdefault(actor,RepositoryIndex(actor));cold=index.reference is None;updated=index.reference!=ref;update_started=time.perf_counter()
  if updated:index.update(bundle['files'],ref,entry_metadata=bundle.get('entry_metadata'))
  update_seconds=time.perf_counter()-update_started
  if cold:index.estimated_memory_bytes=estimated_object_bytes(vars(index))
  if not hasattr(self,'_navigation_projections'):self._navigation_projections={}
  projection=self._navigation_projections.setdefault(actor,Projection(actor));graph=type_relations(synchronize(projection,self,[]))
  condition=getattr(self,'information_condition','L');result=index.query(query,project=graph,task_id=task_id,limit=limit,max_chars=max_chars-300 if max_chars>=1800 else max_chars,use_graph=condition=='G')
  if patch_id:
   for hit in result['hits']:hit['next_read']['arguments']['patch_id']=patch_id
   result['fixed_patch_id']=patch_id
  while len(json.dumps(result,ensure_ascii=False))>max_chars and result['hits']:result['hits'].pop();result['omitted_results']+=1
  self._event(actor,'navigation_v222:located',query=query,task_id=task_id,source_reference=ref,result_paths=[h['path'] for h in result['hits']],index_id=result['source_id'],condition=condition,output_chars=len(json.dumps(result,ensure_ascii=False)),cold_build=cold,version_update=updated,update_seconds=update_seconds,estimated_initial_index_bytes=index.estimated_memory_bytes,memory_measurement='recursive Python objects at cold build, not RSS',wall_seconds=time.perf_counter()-started,no_workspace_change=True)
  return result
class Port(prior.Port):pass

def attach(prepared,requirements,*,condition='L'):
 if condition not in ('L','G'):raise ValueError('Frozen condition')
 prior.attach(prepared,requirements);prepared.world.__class__=World;prepared.world.information_condition=condition;return prepared
SoftwareCollaborationPort=Port;SoftwareCollaborationWorld=World;register_proposal=prior.register_proposal
