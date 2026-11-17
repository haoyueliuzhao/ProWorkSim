"""SEWG organization proposal prototype. Pure planning, never a live world mutator.

A target graph is not an executed organization. Runtime binding remains gated;
unsupported operator mappings must never become successful no-ops.
"""
from __future__ import annotations
import copy,hashlib,json,math
OPERATORS=('CREATE_ROLE','ASSIGN_WORK','SPLIT_WORK','MERGE_WORK','TRANSFER_OWNERSHIP','ADD_COLLABORATION','REMOVE_COLLABORATION','CHANGE_DEPENDENCY','CHANGE_EXECUTION_ORDER','ASSIGN_VERIFICATION','CREATE_SUBTEAM','DISSOLVE_SUBTEAM')
CAPABILITIES={
 'CREATE_ROLE':{'mapping':['org_declare_role'],'status':'self_declaration_only_not_permission_or_execution'},
 'ASSIGN_WORK':{'mapping':['claim_task'],'status':'recipient_action_required'},
 'SPLIT_WORK':{'mapping':['create_task','revise_task','declare_dependency'],'status':'multi_step_coverage_and_receipt_binding_required'},
 'MERGE_WORK':{'mapping':[],'status':'not_supported_atomic_merge_missing'},
 'TRANSFER_OWNERSHIP':{'mapping':['offer_transfer','accept_transfer','decline_transfer'],'status':'explicit_consent_required'},
 'ADD_COLLABORATION':{'mapping':['send_message'],'status':'messages_exist_dynamic_topology_not_bound'},
 'REMOVE_COLLABORATION':{'mapping':[],'status':'not_supported_dynamic_topology_missing'},
 'CHANGE_DEPENDENCY':{'mapping':['declare_dependency','remove_dependency'],'status':'owner_and_task_revision_binding_required'},
 'CHANGE_EXECUTION_ORDER':{'mapping':[],'status':'not_supported_scheduler_binding_missing'},
 'ASSIGN_VERIFICATION':{'mapping':['integrate_patch','run_tests','org_review_patch'],'status':'patch_evidence_exists_dynamic_delivery_gate_missing'},
 'CREATE_SUBTEAM':{'mapping':[],'status':'not_supported_group_lifecycle_missing'},
 'DISSOLVE_SUBTEAM':{'mapping':[],'status':'not_supported_group_lifecycle_missing'},
}
class InvalidOrganization(ValueError):pass

def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def identity(value):
 v=copy.deepcopy(value)
 if isinstance(v,dict) and 'members' in v and 'work' in v:
  for name in ('collaboration','dependencies'):v[name]=sorted(v[name])
  v['roles']={k:sorted(set(xs)) for k,xs in v['roles'].items()}
  v['subteams']={k:sorted(set(xs)) for k,xs in v['subteams'].items()}
  for w in v['work'].values():
   for name in ('scope','contributors','authors'):w[name]=sorted(set(w.get(name,[])))
 return hashlib.sha256(canonical(v).encode()).hexdigest()

def validate(state):
 members=state['members'];tasks=state['work'];m=set(members)
 if len(m)!=2 or any(v.get('status')!='live' for v in members.values()):raise InvalidOrganization('Prototype fixes two live agents, not fixed roles')
 if state['delivery_member'] not in m:raise InvalidOrganization('Fixed unique export identity required')
 if not tasks or len(tasks)>8:raise InvalidOrganization('One to eight real work packages')
 if set(state['execution_order'])!=set(tasks) or len(state['execution_order'])!=len(tasks):raise InvalidOrganization('Execution priority must cover tasks once')
 if set(state['roles'])!=m:raise InvalidOrganization('Roles must describe actual members')
 for a,roles in state['roles'].items():
  if not roles or not set(roles)<={'diagnose','implement','test','review','integrate','coordinate'}:raise InvalidOrganization('Use grounded duty vocabulary; cosmetic role renaming is not exploration')
 observed=set()
 for k,w in tasks.items():
  if w.get('owner') not in m|{None} or not set(w.get('contributors',[]))<=m:raise InvalidOrganization('Unknown responsible member')
  if not w.get('scope') or not set(w['scope'])<=set(state['requirements']):raise InvalidOrganization('Public requirement anchors required')
  observed.update(w['scope'])
  if w.get('status') not in ('open','blocked'):raise InvalidOrganization('Planning cannot claim work complete')
 if observed!=set(state['requirements']):raise InvalidOrganization('Cannot discard original acceptance scope')
 deps=state['dependencies'];edges={k:[] for k in tasks}
 if len({tuple(e) for e in deps})!=len(deps):raise InvalidOrganization('Duplicate dependency')
 for child,parent in deps:
  if child not in tasks or parent not in tasks or child==parent:raise InvalidOrganization('Dependency must bind distinct real tasks')
  edges[child].append(parent)
 visiting=set();done=set()
 def visit(k):
  if k in visiting:raise InvalidOrganization('Dependency cycle')
  if k in done:return
  visiting.add(k)
  for p in edges[k]:visit(p)
  visiting.remove(k);done.add(k)
 for k in tasks:visit(k)
 if len({tuple(e) for e in state['collaboration']})!=len(state['collaboration']):raise InvalidOrganization('Duplicate collaboration edge')
 for a,b in state['collaboration']:
  if a not in m or b not in m or a==b:raise InvalidOrganization('Invalid member edge')
 for k,v in state['verification'].items():
  if k not in tasks or v not in m:raise InvalidOrganization('Unknown verification responsibility')
  # Authorship is separately supplied from trusted world evidence, not role labels.
  if v in set(tasks[k].get('authors',[])):raise InvalidOrganization('Author cannot be its own independent verifier')
 for group,people in state['subteams'].items():
  if not group or len(set(people))<2 or not set(people)<=m:raise InvalidOrganization('Subteam cannot create members')
 return state

def proposal(state,ops):
 validate(state)
 if not isinstance(ops,list) or len(ops)>4:raise InvalidOrganization('At most four bounded composable transformations')
 g=copy.deepcopy(state);trace=[]
 for op in ops:
  kind=op.get('op');actor=op.get('actor');args=op.get('args',{})
  if set(op)!={'op','actor','args'} or kind not in OPERATORS or actor not in g['members']:raise InvalidOrganization('Unknown operation or actor')
  before=identity(g)
  if kind=='CREATE_ROLE':
   if args['member']!=actor:raise InvalidOrganization('Role declarations belong to self')
   g['roles'][actor]=list(args['roles'])
  elif kind=='ASSIGN_WORK':
   w=g['work'][args['task']]
   if w['owner'] is not None:raise InvalidOrganization('Use consented transfer for an owned task')
   g['work'][args['task']]['owner']=args['member']
  elif kind=='TRANSFER_OWNERSHIP':
   w=g['work'][args['task']]
   if w['owner']!=actor or args['member']==actor:raise InvalidOrganization('Only current owner may propose transfer')
   w['owner']=args['member'] # hypothetical only; target never assigned to live state
  elif kind=='SPLIT_WORK':
   old=args['task'];w=g['work'][old];children=args['children']
   if w['owner']!=actor or w.get('authors') or len(children)<2:raise InvalidOrganization('Owned unimplemented work required')
   if set(children)&(set(g['work'])-{old}):raise InvalidOrganization('Work ID collision')
   scopes=[s for v in children.values() for s in v['scope']]
   if set(scopes)!=set(w['scope']) or len(scopes)!=len(set(scopes)):raise InvalidOrganization('Split must preserve a disjoint public scope partition')
   if any(old in e for e in g['dependencies']) or old in g['verification']:raise InvalidOrganization('Explicit dependency/verification migration must precede split')
   del g['work'][old]
   for k,v in children.items():g['work'][k]={'scope':list(v['scope']),'owner':None,'contributors':[],'authors':[],'status':'open'}
   pos=g['execution_order'].index(old);g['execution_order'][pos:pos+1]=list(children)
  elif kind=='MERGE_WORK':
   ids=args['tasks'];new=args['new_task']
   if len(set(ids))<2 or new in g['work']:raise InvalidOrganization('New merge identity required')
   if any(g['work'][k]['owner']!=actor or g['work'][k].get('authors') for k in ids):raise InvalidOrganization('Only same-owner unimplemented work')
   if any(set(e)&set(ids) for e in g['dependencies']) or set(ids)&set(g['verification']):raise InvalidOrganization('Explicit boundary migration required')
   scopes=sorted({s for k in ids for s in g['work'][k]['scope']})
   for k in ids:del g['work'][k]
   g['work'][new]={'scope':scopes,'owner':actor,'contributors':[],'authors':[],'status':'open'}
   g['execution_order']=[k for k in g['execution_order'] if k not in ids]+[new]
  elif kind in ('ADD_COLLABORATION','REMOVE_COLLABORATION'):
   edge=[actor,args['peer']]
   if kind.startswith('ADD'):g['collaboration'].append(edge)
   else:g['collaboration'].remove(edge)
  elif kind=='CHANGE_DEPENDENCY':
   if g['work'][args['task']]['owner']!=actor:raise InvalidOrganization('Dependency owner authority required')
   edge=[args['task'],args['depends_on']]
   if args['operation']=='add':g['dependencies'].append(edge)
   elif args['operation']=='remove':g['dependencies'].remove(edge)
   else:raise InvalidOrganization('Explicit add/remove required')
  elif kind=='CHANGE_EXECUTION_ORDER':g['execution_order']=list(args['order'])
  elif kind=='ASSIGN_VERIFICATION':g['verification'][args['task']]=args['member']
  elif kind=='CREATE_SUBTEAM':
   if args['id'] in g['subteams'] or actor not in args['members']:raise InvalidOrganization('New subteam containing proposer')
   g['subteams'][args['id']]=list(args['members'])
  elif kind=='DISSOLVE_SUBTEAM':
   if actor not in g['subteams'][args['id']]:raise InvalidOrganization('Only a member may propose dissolution')
   del g['subteams'][args['id']]
  validate(g)
  if identity(g)==before:raise InvalidOrganization('No-op edits do not count as organization exploration')
  trace.append({'operation':copy.deepcopy(op),'before':before,'after':identity(g),'capability':CAPABILITIES[kind]})
 signature=[]
 for dimension,fields in {'roles':['roles'],'tasks':['work','dependencies'],'ownership':['work'],'collaboration':['collaboration','subteams'],'execution_verification':['execution_order','verification']}.items():
  if dimension=='ownership':
   changed={k:(v.get('owner'),sorted(v.get('contributors',[]))) for k,v in g['work'].items()}!={k:(v.get('owner'),sorted(v.get('contributors',[]))) for k,v in state['work'].items()}
  elif dimension=='tasks':
   changed=g['dependencies']!=state['dependencies'] or {k:sorted(v['scope']) for k,v in g['work'].items()}!={k:sorted(v['scope']) for k,v in state['work'].items()}
  else:changed=any(g[k]!=state[k] for k in fields)
  if changed:signature.append(dimension)
 return {'coverage_signature':signature or ['unchanged'],'source_state_hash':identity(state),'target_state_hash':identity(g),'target':g,'trace':trace,'unchanged_baseline':not ops,'live_execution':False,'runtime_admission':'blocked_pending_actual_harness_binding','syntactic_validity_is_not_effectiveness':True}

def deduplicate(proposals):
 """Different operation strings yielding identical states are not new architectures."""
 by={}
 for p in proposals:by.setdefault(p['target_state_hash'],p)
 return list(by.values())

def structured_reference(proposals,family_weights):
 """Explicit finite-bank reference: family mass, then unique targets within family.

It is not uniform over all reachable graphs. Family assignment and candidate bank
must be frozen before outcomes. Proposals cannot buy mass via duplicate traces.
"""
 if not proposals or any(v<=0 or not math.isfinite(v) for v in family_weights.values()):raise ValueError('Positive declared family coverage')
 seen={};groups={}
 for p in proposals:
  key=p['target_state_hash'];family=p['coverage_family']
  if family not in family_weights:raise ValueError('Undeclared family')
  if key in seen:raise ValueError('Deduplicate target states before coverage allocation')
  seen[key]=family;groups.setdefault(family,[]).append(key)
 total=sum(family_weights[f] for f in groups)
 return {k:family_weights[f]/total/len(keys) for f,keys in groups.items() for k in keys}

def update_bank(q,r,utility,*,epsilon=.05,t_c=1.,t_n=1.,alpha=1.,beta=1.,rho=.8,eta=.5,support_mass=.05):
 """Supplement formula on one frozen finite candidate bank; CPU prototype only.

q must come from the same frozen generator/selector version and support. Do not
carry per-graph probabilities across unrelated tasks by relabeling graph IDs.
"""
 keys=set(q)
 if not keys or set(r)!=keys or set(utility)!=keys:raise ValueError('Common complete legal candidate support required')
 if not 0<epsilon<.5 or min(t_c,t_n)<=0 or not 0<=rho<=1 or not 0<=support_mass<1:raise ValueError('Invalid frozen parameters')
 for d in (q,r):
  if any(not math.isfinite(v) or v<=0 for v in d.values()) or abs(sum(d.values())-1)>1e-10:raise ValueError('Positive normalized support')
 if any(not math.isfinite(v) for v in utility.values()):raise ValueError('No technical unknown as utility')
 center=sum(q[k]*utility[k] for k in q);c={k:utility[k]-center for k in q};n={k:max(0.,math.log(r[k]/q[k])) for k in q}
 def sigmoid(v):return 1/(1+math.exp(-v)) if v>=0 else math.exp(v)/(1+math.exp(v))
 cp={k:epsilon+(1-2*epsilon)*sigmoid(c[k]/t_c) for k in q};np={k:epsilon+(1-2*epsilon)*(-math.expm1(-n[k]/t_n)) for k in q}
 logs={k:rho*math.log(q[k])+(1-rho)*math.log(r[k])+eta*(alpha*math.log(cp[k])+beta*math.log(np[k])) for k in q}
 maximum=max(logs.values());w={k:math.exp(v-maximum) for k,v in logs.items()};den=sum(w.values());new={k:(1-support_mass)*w[k]/den+support_mass*r[k] for k in q}
 return {'contribution':c,'undercoverage_novelty':n,'positive_C':cp,'positive_N':np,'q_after':new,'minimum_support_is_reference_mixture_not_per_candidate_5_percent':True,'new_formula_not_retroactive_to_v204':True}
