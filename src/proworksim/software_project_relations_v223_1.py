"""Preserve position units in the actor-authorized incremental projection."""
import copy
from .software_project_relations_v217 import Projection as Prior,synchronize,allowed_event,identity
VERSION='v223.1-character-typed-project-relations-r1'
class Projection(Prior):
 def snapshot(self,work,requirements):
  graph=super().snapshot(work,requirements)
  for r in graph['relations']:
   if r['kind']=='work_observed_region':
    d=r['details'];d['start_character']=d.pop('start',None);d['end_character']=d.pop('end',None);d['position_unit']='Unicode_characters';d['end_exclusive']=True
  graph['position_schema_revision']=VERSION;graph.pop('graph_id',None);graph['graph_id']=identity(graph);return graph
