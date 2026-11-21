"""Small shared selector over frozen legal banks; no task/repo IDs are features."""
import copy,math,random,collections
from . import software_organization_selector_v217 as prior
from . import software_organization_selector_v216 as fit_base
from .software_fixed_organization_clone_v131 import clone_function
from .storage import digest,json_bytes
VERSION='v224-project-organization-mapping-CN-r1'
FEATURES=(*prior.FEATURES,'multi_scope_fraction','independent_review_fraction','observed_region_coverage','failed_test_times_distributed_work','uncertain_relation_times_mapping_change')
SPEC={**copy.deepcopy(fit_base.SPEC),'version':VERSION,'features':FEATURES,'initial_theta':[0.]*len(FEATURES),'novelty_mapping_weight':.5,'mapping_bins':[0,.25,.75,1],'within_task_updates':False}
ns={**vars(fit_base),'FEATURES':FEATURES,'SPEC':SPEC};ns['distribution']=clone_function(fit_base.distribution,ns);distribution=ns['distribution'];fit=clone_function(fit_base.fit,ns);utility=fit_base.utility

def feature_vector(state,candidate,remaining):
 v=prior.features(state,candidate,remaining,'P');work=candidate['target']['work'];leaves={k:w for k,w in work.items() if not w.get('children')};count=max(1,len(leaves));rels=state['project_relations']['relations'];original=state['graph']['work']
 def origins(w):return [k for k,o in original.items() if set(w['scope'])<=set(o['scope']) and not o.get('children')]
 review=sum(w.get('reviewer') in ('member_001','member_002') and w['reviewer']!=w['owner'] and w['reviewer'] not in w.get('authors',[]) for w in leaves.values())/count
 covered=sum(any(r['kind'] in ('work_code_region','work_observed_region') and r['source'] in origins(w) for r in rels) for w in leaves.values())/count
 current=[r for r in rels if r['kind']=='test_version' and r.get('validity')=='current' and r.get('details',{}).get('executed')]
 failure=sum(r['details'].get('passed') is False for r in current)/max(1,len(current))
 uncertain=sum(r.get('evidence_level') in ('E2','E3') for r in rels)/max(1,len(rels))
 changes=sum(not any(o['owner']==w['owner'] and set(o['scope'])==set(w['scope']) and o.get('mode','implementation')==w.get('mode','implementation') for o in original.values()) for w in leaves.values())/count
 v += [sum(len(w['scope'])>1 for w in leaves.values())/count,review,covered,failure*sum(w['owner']!='member_001' for w in leaves.values())/count,uncertain*changes]
 if len(v)!=len(FEATURES) or any(not math.isfinite(x) or not 0<=x<=1 for x in v):raise ValueError('Finite bounded mapping features required')
 return v

def structure_descriptor(candidate):
 work=candidate['target']['work'];leaves={k:w for k,w in work.items() if not w.get('children')}
 def label(w):return (w['owner'],w.get('reviewer'),w.get('mode','implementation'),len(w['scope']))
 nodes=sorted((label(w) for w in leaves.values()),key=repr);edges=sorted([(label(w),label(work[p])) for w in leaves.values() for p in w.get('depends_on',[]) if p in leaves],key=repr)
 return digest(json_bytes({'nodes':nodes,'dependency_role_pairs':edges}))

def mapping_descriptor(v):
 def bucket(x):return 0 if x==0 else 1 if x<=.25 else 2 if x<=.75 else 3
 return tuple(bucket(v[i]) for i in (0,1,2,3,8,9,10,11))

def initialize():return {'version':VERSION,'update':0,'theta':[0.]*len(FEATURES),'history':[],'spec':SPEC}
def evaluate(state,bank,policy,seed):
 cs=bank['candidates'];r={z:1/len(cs) for z in cs};fs={z:feature_vector(state,c,bank['remaining_branch_token_limit']) for z,c in cs.items()};q=distribution(policy['theta'],fs,r)
 u=random.Random(seed).random();acc=0;selected=None
 for z in sorted(cs):
  acc+=q[z]
  if selected is None and u<acc:selected=z
 return {'policy_update':policy['update'],'features':fs,'reference':r,'probabilities':q,'mapping_groups':{z:mapping_descriptor(fs[z]) for z in cs},'structure_groups':{z:structure_descriptor(cs[z]) for z in cs},'selected':selected,'random_u':u,'seed':seed,'frozen_before_outcomes':True,'feature_degenerate':len(cs)>1 and len({tuple(f) for f in fs.values()})==1}

def target(decision,utilities):
 q,r=decision['probabilities'],decision['reference'];keys=set(q)
 if keys!=set(utilities) or any(not math.isfinite(x) for x in utilities.values()):raise ValueError('Every candidate must have a known utility')
 def grouped_novelty(groups):
  qm=collections.defaultdict(float);rm=collections.defaultdict(float)
  for z in q:k=str(groups[z]);qm[k]+=q[z];rm[k]+=r[z]
  return {z:max(0.,math.log(rm[str(groups[z])]/qm[str(groups[z])])) for z in q}
 nm=grouped_novelty(decision['mapping_groups']);ns=grouped_novelty(decision['structure_groups']);gamma=SPEC['novelty_mapping_weight'];n={z:gamma*nm[z]+(1-gamma)*ns[z] for z in q};center=sum(q[z]*utilities[z] for z in q);c={z:utilities[z]-center for z in q};eps=SPEC['epsilon']
 cp={z:eps+(1-2*eps)/(1+math.exp(-c[z]/SPEC['t_c'])) for z in q};np={z:eps+(1-2*eps)*(-math.expm1(-n[z]/SPEC['t_n'])) for z in q}
 logs={z:SPEC['rho']*math.log(q[z])+(1-SPEC['rho'])*math.log(r[z])+SPEC['eta']*(SPEC['alpha']*math.log(cp[z])+SPEC['beta']*math.log(np[z])) for z in q};mx=max(logs.values());w={z:math.exp(v-mx) for z,v in logs.items()};den=sum(w.values());d=SPEC['delta'];after={z:(1-d)*w[z]/den+d*r[z] for z in q}
 return {'C':c,'N_mapping':nm,'N_structure':ns,'N':n,'positive_C':cp,'positive_N':np,'q_after':after,'observed_utility_is_noisy_estimate':True}

def update(policy,records,window):
 eligible=[x for x in records if x.get('complete') and len(x['outcomes'])>=2 and not x['decision']['feature_degenerate']];out=copy.deepcopy(policy)
 if not eligible:
  out['history'].append({'window':window,'updated':False,'reason':'no_complete_informative_candidate_panel','records':[]});return out
 targets=[];details=[]
 for row in eligible:
  if set(row['outcomes'])!=set(row['decision']['reference']):raise ValueError('No partial-panel update')
  values={z:utility(v['legal_correct'],v['logical_tokens']) for z,v in row['outcomes'].items()};t=target(row['decision'],values);targets.append({'features':row['decision']['features'],'reference':row['decision']['reference'],'target':t['q_after']});details.append({'index':row['index'],'utilities':values,'target':t})
 result=fit(policy['theta'],targets);out['theta']=result['theta'];out['update']+=1;out['history'].append({'window':window,'updated':True,'records':[x['index'] for x in eligible],'details':details,'fit':result,'weights_changed':result['theta']!=policy['theta']});return out
