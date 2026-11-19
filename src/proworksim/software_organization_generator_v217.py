"""Relation-grounded complete targets with optional adoption and no forced transfer."""
import copy,inspect
from . import software_organization_generator_v216_1 as prior
from . import software_organization_generator_v216 as core
VERSION='v217-relation-grounded-targets-r1'
ns=dict(vars(prior));source=inspect.getsource(prior.compile_target)
source=source.replace(" if not any(op['op']=='JOINT_ASSIGN' for op in ops):raise ValueError('Mechanism probe needs at least one other-member arrangement')\n",'')
# An adoption-only plan can have no structural ops; retain exact work graph.
source=source.replace(" result=validate_program(graph,{'reason':proposal['reason'],'operations':ops})", " result=validate_program(graph,{'reason':proposal['reason'],'operations':ops}) if ops else {'target':copy.deepcopy(graph),'operations':[],'actions':[],'keep':False,'reason':proposal['reason']}")
exec(compile(source,__file__+':compile-base','exec'),ns)
_base=ns['compile_target']
def compile_target(state,proposal):
 fields={'reason','remaining_work','dependencies','adoptions','basis'}
 if set(proposal)!=fields:raise ValueError('Exact target, adoption and evidence fields required')
 pg=state['project_relations'];basis=proposal['basis'];rels={r['id']:r for r in pg['relations']}
 if set(basis)!={'graph_id','relation_ids','trigger_events','need','expected_benefit','switch_cost'} or basis['graph_id']!=pg['graph_id']:raise ValueError('Bind this exact graph')
 if not basis['relation_ids'] or not set(basis['relation_ids'])<=set(rels):raise ValueError('Cite actual visible project relations')
 if not set(basis['trigger_events'])<={r['source_event'] for r in rels.values() if r['source_event'] is not None}:raise ValueError('Cite actual visible events')
 if any(not isinstance(basis[k],str) or not 0<len(basis[k])<=2000 for k in ('need','expected_benefit','switch_cost')):raise ValueError('Bounded hypothesis and cost explanation required')
 result=_base(state['graph'],{k:proposal[k] for k in ('reason','remaining_work','dependencies')})
 published={r['target']:r for r in rels.values() if r['kind']=='work_fixed_artifact'};adoptions=[]
 for a in proposal['adoptions']:
  if set(a)!={'actor','patch_id','task_id'} or a['actor'] not in core.MEMBERS or a['task_id'] not in state['graph']['work'] or a['patch_id'] not in published:raise ValueError('Adoption must name a visible actual patch, actor and task')
  r=published[a['patch_id']]
  if r['details']['author']==a['actor']:raise ValueError('No cosmetic own-patch adoption')
  if any(x['kind']=='artifact_adopted' and x['source']==a['patch_id'] and x['target']==a['actor'] for x in rels.values()):raise ValueError('Already adopted in observed world')
  if a in adoptions:raise ValueError('Duplicate adoption')
  adoptions.append(a);result['actions'].append({'actor':a['actor'],'tool':'integrate_patch','arguments':{'patch_id':a['patch_id']},'context_task':a['task_id'],'actual_model_action_required':True})
 if core.target_id(result['target'])==core.target_id(state['graph']) and not adoptions:raise ValueError('Equivalent KEEP/no-op')
 affected={o['arguments']['task_id'] for o in result['operations']}|{a['task_id'] for a in adoptions}
 cited=[rels[k] for k in basis['relation_ids']]
 for tid in affected:
  originals={tid}|{k for k,w in state['graph']['work'].items() if tid in result['target']['work'] and set(result['target']['work'][tid]['scope'])<=set(w['scope'])}
  if not any(r['source'] in originals or r['target'] in originals for r in cited):raise ValueError('Every affected work package must have a cited visible relation')
 result.update(candidate_id=core.digest({'organization':core.target_id(result['target']),'planned_adoptions':sorted(adoptions,key=core.canonical)}),planned_adoptions=adoptions,basis=copy.deepcopy(basis),version=VERSION,model_target=copy.deepcopy(proposal),host_execution=False)
 return result
GENERATOR_INSTRUCTION=prior.GENERATOR_INSTRUCTION.replace('propose exactly two DIFFERENT','propose up to two DIFFERENT').replace('At least one leaf in each target must move to the other member.','Responsibility transfer is OPTIONAL, never mandatory. A plan can keep all owners and improve missing verification, collaboration or evidence-backed dependency/adoption arrangements. Return no artificial variants when no distinct supported plan exists.').replace('candidates [{reason, remaining_work, dependencies}]','candidates [{reason, remaining_work, dependencies, adoptions, basis}]')+'''
Every plan MUST cite the exact actual_decision_state.project_relations.graph_id and actual relation IDs in basis={graph_id,relation_ids,trigger_events,need,expected_benefit,switch_cost}. Cite at least one relation touching EACH affected original work package. Explain an evidence-backed collaboration need, expected benefit and switching cost as hypotheses, not observed success. Distinguish directly observed facts, member claims and unknowns. Removing an execution dependency does not erase an engineering requirement. adoptions is an array of {actor,patch_id,task_id} proposing actual adoption of a VISIBLE fixed partner artifact when needed; no patch IDs may be invented. Adoption remains a real member tool action and does not certify tests. All current public issue requirements and authors must remain. Return zero, one or two genuinely different valid plans; KEEP is always supplied. No extra planning model, no hidden score, no browsing.'''
TOOL=copy.deepcopy(prior.TOOL);schema=TOOL['function']['parameters']['properties']['candidates'];schema['minItems']=0
item=schema['items'];item['required']+=['adoptions','basis']
item['properties']['adoptions']={'type':'array','maxItems':4,'items':{'type':'object','properties':{k:{'type':'string'} for k in ('actor','patch_id','task_id')},'required':['actor','patch_id','task_id'],'additionalProperties':False}}
item['properties']['basis']={'type':'object','properties':{'graph_id':{'type':'string'},'relation_ids':{'type':'array','items':{'type':'string'},'minItems':1},'trigger_events':{'type':'array','items':{'type':'integer'}},**{k:{'type':'string','minLength':1,'maxLength':2000} for k in ('need','expected_benefit','switch_cost')}},'required':['graph_id','relation_ids','trigger_events','need','expected_benefit','switch_cost'],'additionalProperties':False}
TOOL['function']['description']='Propose up to two complete relation-grounded arrangements; no live action.'
