"""Auditable planning-only syntax/identity projection. Never used on world tools."""
import copy,json,re
from .software_organization_generator_v217 import compile_target,TOOL,GENERATOR_INSTRUCTION
from .software_organization_opportunity_v218 import distinct_structure,structure
from .work_interface import _schema_errors
from .storage import digest,json_bytes
VERSION='v219-explicit-mutable-target-and-recorded-parser-r1'
def mutable_tasks(state):return {k:w for k,w in state['graph']['work'].items() if not w['children'] and not w['authors'] and w['completion'] is None}
def contextual_tool(state):
 tool=copy.deepcopy(TOOL);item=tool['function']['parameters']['properties']['candidates']['items'];rw=item['properties']['remaining_work'];ids=sorted(mutable_tasks(state));rw['minItems']=rw['maxItems']=len(ids);rw['items']['properties']['source_task_id']['enum']=ids
 tool['function']['description']+=' ONLY these mutable leaf IDs, exactly once each: '+json.dumps(ids)+'. Authored/parent/completed work must be omitted.'
 return tool

def parse_proposal(raw,state):
 notes=[]
 def unique(pairs):
  d={}
  for k,v in pairs:
   if k in d:raise ValueError('Duplicate JSON key: '+k)
   d[k]=v
  return d
 decoder=json.JSONDecoder(object_pairs_hook=unique);s=raw.lstrip();data,end=decoder.raw_decode(s);tail=s[end:].strip()
 if tail:
  if not re.fullmatch(r'[}\]]{1,8}',tail):raise ValueError('Trailing semantic payload or second JSON object')
  notes.append({'repair':'redundant_trailing_closers','suffix':tail})
 if not isinstance(data,dict) or not isinstance(data.get('candidates'),list):raise ValueError('Exact proposal object required')
 data=copy.deepcopy(data);mutable=mutable_tasks(state)
 for n,p in enumerate(data['candidates']):
  if not isinstance(p,dict):raise ValueError('Candidate object required')
  basis=p.get('basis',{})
  for k in list(basis):
   if k in ('expected_benefit_note','relation_ids_extra_note') and (basis[k] is None or isinstance(basis[k],str) and len(basis[k])<=2000):
    notes.append({'candidate':n,'repair':'nonoperative_annotation_separated','key':k,'value':basis.pop(k)})
  specs=p.get('remaining_work',[]);new=[];seen=set()
  for spec in specs:
   tid=spec.get('source_task_id')
   if tid in seen:raise ValueError('Duplicate work identity')
   seen.add(tid)
   if tid not in mutable:
    w=state['graph']['work'].get(tid)
    expected={'source_task_id':tid,'parts':[{'scope':w['scope'],'owner':w['owner'],'mode':w.get('mode','implementation')}]} if w else None
    if not w or w['children'] or spec!=expected:raise ValueError('Attempted change to immutable/unknown work')
    notes.append({'candidate':n,'repair':'unchanged_immutable_work_omitted','task_id':tid,'original':spec})
   else:new.append(spec)
  p['remaining_work']=new
 errors=_schema_errors(contextual_tool(state)['function']['parameters'],data)
 if errors:raise ValueError('; '.join(errors))
 return data,{'version':VERSION,'raw_sha256':digest(raw.encode()),'normalized_sha256':digest(json_bytes(data)),'repairs':notes,'live_action_executed':False,'candidate_choice_not_changed':True}

def validated_candidates(raw,state):
 data,proof=parse_proposal(raw,state);valid={};errors=[]
 for i,p in enumerate(data['candidates']):
  try:
   c=compile_target(state,p)
   if not distinct_structure(state,c):raise ValueError('No structural alternative to KEEP')
   for action in c['actions']:
    err=_schema_errors(state['proposal_tool_schemas'][action['tool']],action.get('arguments',{'offer_id':'actual-receipt-placeholder-for-schema-only'}))
    if err:raise ValueError('; '.join(err))
   valid[digest(json_bytes(structure(c['target'])))]=c
  except (ValueError,KeyError,TypeError) as e:errors.append({'candidate':i,'error':str(e)})
 return valid,errors,proof
