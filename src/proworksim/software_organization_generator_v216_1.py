"""Model selects a target partition/ownership; compiler only emits proposed tool steps.

No live ownership mutation. Author history remains fixed. This revision removes
procedural actor bookkeeping from model output, not consent from execution.
"""
import copy,inspect,json
from . import software_organization_generator_v216 as old
VERSION='v216.1-model-target-compiler-r1';target_id=old.target_id;digest=old.digest
ns={**vars(old),'VERSION':VERSION};source=inspect.getsource(old.validate).replace('1<=len(ops)<=6','1<=len(ops)<=12').replace('One to six supported operations','One to twelve compiled operations');exec(compile(source,__file__+':validator','exec'),ns);validate_program=ns['validate']
def compile_target(graph,proposal):
 if set(proposal)!={'reason','remaining_work','dependencies'}:raise ValueError('Exact target fields required')
 mutable={k:w for k,w in graph['work'].items() if not w['children'] and not w['authors'] and w['completion'] is None}
 specs=proposal['remaining_work'];ids=[s['source_task_id'] for s in specs]
 if len(ids)!=len(set(ids)) or set(ids)!=set(mutable):raise ValueError('Describe every and only unstarted remaining leaf once')
 ops=[];current=copy.deepcopy(graph);newids={}
 def emit(op,actor,**arguments):ops.append({'op':op,'actor':actor,'arguments':arguments})
 for spec in specs:
  if set(spec)!={'source_task_id','parts'}:raise ValueError('Target work requires source_task_id and parts')
  tid=spec['source_task_id'];w=mutable[tid];parts=spec['parts'];all_scopes=[s for p in parts for s in p['scope']]
  if not 1<=len(parts)<=3 or len(set(all_scopes))!=len(all_scopes) or sorted(all_scopes)!=sorted(w['scope']):raise ValueError('Partition only this source leaf scope exactly; one anchor cannot split into two nonempty scopes')
  for part in parts:
   if set(part)!={'scope','owner','mode'} or not part['scope'] or part['owner'] not in old.MEMBERS or part['mode'] not in ('implementation','evidence'):raise ValueError('Each target part has exact nonempty scope/actual owner/mode')
  children=[]
  for part in parts:
   child=tid if len(parts)==1 else tid+'_'+digest(part['scope'])[:8];newids[(tid,tuple(sorted(part['scope'])))]=child;children.append({'task_id':child,'description':'Public remaining scope: '+', '.join(part['scope']),'scope':part['scope']})
  if len(parts)>1:emit('SPLIT_WORK',w['owner'],task_id=tid,children=children)
  for part,child in zip(parts,children):
   key=child['task_id'];owner=part['owner'];reviewer=next(m for m in old.MEMBERS if m!=owner);prior_mode=w.get('mode','implementation') if len(parts)==1 else 'implementation'
   if owner!=w['owner']:emit('JOINT_ASSIGN',w['owner'],task_id=key,to_member=owner,reviewer=reviewer,mode=part['mode'])
   elif part['mode']!=prior_mode:raise ValueError('Keeping owner must keep current permission mode; evidence completion is still allowed without changing mode')
   elif len(parts)>1 or w['reviewer']!=reviewer:emit('ASSIGN_VERIFICATION',owner,task_id=key,reviewer=reviewer)
   if len(parts)>1 or any(e not in graph['collaboration'] for e in ([key,owner,reviewer],[key,reviewer,owner])):emit('ADD_COLLABORATION',owner,task_id=key,peer=reviewer)
   current['work'][key]={**copy.deepcopy(w),'owner':owner,'reviewer':reviewer,'scope':part['scope'],'children':[]}
 for dep in proposal['dependencies']:
  if set(dep)!={'task_id','depends_on','operation'}:raise ValueError('Explicit existing leaf dependency fields required')
  tid=dep['task_id']
  if tid not in current['work']:raise ValueError('Dependency task does not exist')
  emit('CHANGE_DEPENDENCY',current['work'][tid]['owner'],**dep)
 result=validate_program(graph,{'reason':proposal['reason'],'operations':ops})
 if not any(op['op']=='JOINT_ASSIGN' for op in ops):raise ValueError('Mechanism probe needs at least one other-member arrangement')
 result['model_target']=copy.deepcopy(proposal);result['compiler_does_not_execute_actions']=True;return result

GENERATOR_INSTRUCTION='''You are a fixed organization TARGET generator, not an autonomous worker. Given a real mid-work state, propose exactly two DIFFERENT target arrangements for the remaining unstarted leaves. KEEP is supplied separately. Preserve all already-authored work and original public requirements. Do not solve code or use hidden material. Return propose_organization with candidates [{reason, remaining_work, dependencies}]. remaining_work must cover each unstarted leaf exactly once: {source_task_id, parts:[{scope:[the original anchor IDs], owner:member_001|member_002, mode:implementation|evidence}]}. A part retains current task identity if there is only one part. Multiple parts must be nonempty, disjoint and cover ONLY that source leaf's original anchors; a single-anchor leaf CANNOT split. Keeping the same owner must keep its current mode. An implementation-mode unmodified package may still complete evidence without changing mode. Moving a leaf to the other member may select implementation or evidence mode. The compiler assigns the mandatory other-member verifier and necessary collaboration, emits real offer/accept steps with correct actors, but NEVER executes consent or modifies a live world. You choose ownership/partitions; do not write procedural actor steps. At least one leaf in each target must move to the other member. dependencies is an optional array of {task_id,depends_on,operation:add|remove} for existing non-split leaves. Avoid unnecessary dependencies. Concentration or distribution can both be reasonable; extra people editing is not itself a reward. No owner quota exists; all members share the same remaining team budget. No new agents, task merges, scheduling priority or removal of collaboration is supported.'''
TOOL={'type':'function','function':{'name':'propose_organization','description':'Return two distinct target organizations, no live execution.','parameters':{'type':'object','properties':{'candidates':{'type':'array','minItems':2,'maxItems':2,'items':{'type':'object','properties':{'reason':{'type':'string'},'remaining_work':{'type':'array','items':{'type':'object','properties':{'source_task_id':{'type':'string'},'parts':{'type':'array','minItems':1,'maxItems':3,'items':{'type':'object','properties':{'scope':{'type':'array','items':{'type':'string'}},'owner':{'type':'string','enum':list(old.MEMBERS)},'mode':{'type':'string','enum':['implementation','evidence']}},'required':['scope','owner','mode'],'additionalProperties':False}}},'required':['source_task_id','parts'],'additionalProperties':False}},'dependencies':{'type':'array','items':{'type':'object','properties':{'task_id':{'type':'string'},'depends_on':{'type':'string'},'operation':{'type':'string','enum':['add','remove']}},'required':['task_id','depends_on','operation'],'additionalProperties':False}}},'required':['reason','remaining_work','dependencies'],'additionalProperties':False}}},'required':['candidates'],'additionalProperties':False}}}
