"""Shared graph-review and proposal interfaces, bounded read-only logical roles."""
import copy,json
from .software_project_relations_v217 import identity
from .software_organization_generator_v219 import contextual_tool,parse_proposal
VERSION='v223-shared-graph-worker-context-versus-independent-OA-r1'
GRAPH_TOOL={'type':'function','function':{'name':'annotate_project_graph','description':'Propose at most eight unverified interpretations of visible project relations. No world changes or factual promotion.',
 'parameters':{'type':'object','properties':{'hypotheses':{'type':'array','maxItems':8,'items':{'type':'object','properties':{'work_ids':{'type':'array','items':{'type':'string'},'minItems':1},'evidence_ids':{'type':'array','items':{'type':'string'},'minItems':1},'claim':{'type':'string','minLength':1,'maxLength':1400}},'required':['work_ids','evidence_ids','claim'],'additionalProperties':False}}},'required':['hypotheses'],'additionalProperties':False}}}
GRAPH_INSTRUCTION='You are the read-only Graph Agent. Interpret only the supplied actor-authorized project and organization state. All your new claims remain E3 hypotheses. Cite visible relation IDs and existing work IDs; never invent sources, necessary dependencies, hidden test outcomes or semantic coverage. Distinguish ordinary code failure from organization mismatch. Do not choose, execute or approve an organization plan. Return annotate_project_graph once, with fewer or no claims if uncertain.'

def add_hypotheses(state,data):
 from .work_interface import _schema_errors
 errors=_schema_errors(GRAPH_TOOL['function']['parameters'],data)
 if errors:raise ValueError('; '.join(errors))
 out=copy.deepcopy(state);g=out['project_relations'];ids={r['id'] for r in g['relations']}
 for item in data['hypotheses']:
  if not set(item['work_ids'])<=set(out['graph']['work']) or not set(item['evidence_ids'])<=ids:raise ValueError('Graph Agent cited inaccessible or invented source')
  row={'kind':'graph_agent_hypothesis','source':item['work_ids'][0],'target':','.join(item['work_ids']),'source_event':None,'visible_to':g['actor'],'evidence_level':'E3','fact_status':'member_claim','semantic_dependency_proven':False,'version':None,'details':copy.deepcopy(item)};row['id']=identity(row);g['relations'].append(row)
 g.pop('graph_id',None);g['graph_id']=identity(g);return out

def tool(state):
 t=contextual_tool(state);p=t['function']['parameters'];p['properties']['assessment']={'type':'object','properties':{'decision':{'type':'string','enum':['propose','keep','defer']},'demand_types':{'type':'array','items':{'type':'string','enum':['responsibility_gap','dependency_bottleneck','load_imbalance','verification_gap','integration_conflict']}},'reason':{'type':'string','minLength':1,'maxLength':1800}},'required':['decision','demand_types','reason'],'additionalProperties':False};p['required'].append('assessment');return t

def parse(raw,state):
 from .work_interface import _schema_errors
 def unique(pairs):
  out={}
  for k,v in pairs:
   if k in out:raise ValueError('Duplicate key')
   out[k]=v
  return out
 value=json.loads(raw,object_pairs_hook=unique)
 if set(value)!={'assessment','candidates'}:raise ValueError('Exact assessment and candidates required')
 assessment=value['assessment'];normalized,proof=parse_proposal(json.dumps({'candidates':value['candidates']}),state)
 normalized['assessment']=assessment;errors=_schema_errors(tool(state)['function']['parameters'],normalized)
 if errors:raise ValueError('; '.join(errors))
 if assessment['decision']!='propose' and normalized['candidates']:raise ValueError('KEEP/DEFER must not simultaneously propose changes')
 return normalized,{'raw_sha256':identity(raw),'candidate_normalization':proof,'actual_role_output_retained':True}

def historical_worker_context(request):
 if request['payload']['member_id']!='member_001' or request['payload']['usage_id']!='agent':raise ValueError('Only real member_001 seen context')
 # Copy the last actual submitted context, not imagined private peer memory.
 return {'version':'v223-worker-seen-history-r1','messages':copy.deepcopy(request['payload']['wire']['messages']),
         'physical_request_id':request['physical_id'],'history_boundary':'latest actual member_001 input; current visible graph supplies post-input world changes','fabricated_tool_replies':False}
