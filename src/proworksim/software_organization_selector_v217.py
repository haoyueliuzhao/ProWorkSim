"""Frozen seven-dimensional ledger vs relation features; equal fitting protocol."""
import copy,math,random
from . import software_organization_selector_v216 as base
SPEC=copy.deepcopy(base.SPEC);SPEC.update(version='v217-relation-ledger-shared-CN-r1',reference='uniform over frozen deduplicated effective candidates',missing_project_information='unit workload plus 0.5 unknown evidence obligation',same_support=True)
FEATURES=base.FEATURES
distribution=base.distribution;utility=base.utility;target_distribution=base.target_distribution;fit=base.fit;policy_value=base.policy_value
POLICIES=('L_CN','P_C','P_CN')
def features(state,candidate,remaining,kind):
 g=candidate['target'];steps=len(candidate.get('actions',[]));v=base.feature_vector(state,g,steps,remaining)
 if kind=='L':return v
 if kind!='P':raise ValueError('Ledger L or project P required')
 rel=state['project_relations']['relations'];work=g['work'];leaves={t:w for t,w in work.items() if not w['children']};pending={t:w for t,w in leaves.items() if not w.get('completion_current',False)}
 regions={t:{r['target'] for r in rel if r['source']==t and r['kind'] in ('work_code_region','work_observed_region')} for t in leaves}
 # New split children inherit visible region associations by scope, never private source.
 for t,w in leaves.items():
  if t not in state['graph']['work']:
   for orig,x in state['graph']['work'].items():
    if set(w['scope'])<=set(x['scope']):regions[t]|={r['target'] for r in rel if r['source']==orig and r['kind'] in ('work_code_region','work_observed_region')}
 weights={t:(1+min(4,len(regions[t]))+len(w['scope'])/2)*(0.5 if w.get('mode')=='evidence' else 1) for t,w in pending.items()};total=max(1,sum(weights.values()))
 loads={m:state.get('member_usage',{}).get(m,{}).get('known_actual_tokens',0)/5_000_000+sum(weights[t] for t,w in pending.items() if w['owner']==m)/total*(remaining/5_000_000) for m in ('member_001','member_002')}
 v[0]=1-min(1,abs(loads['member_001']-loads['member_002']))
 # Persistent member claims are potential needs, not proven software semantics.
 deps={(r['source'],r['target']) for r in rel if r['kind']=='work_requires_claim' and r['source'] in leaves and r['target'] in leaves}
 overlaps={(a,b) for a in leaves for b in leaves if a<b and regions[a]&regions[b]}
 risks=deps|overlaps
 v[1]=sum(leaves[a]['owner']!=leaves[b]['owner'] for a,b in risks)/max(1,len(risks))
 debt=0
 for t,w in leaves.items():
  c=w.get('completion');tested=[r for r in rel if r['kind']=='test_version' and r['target']==w['owner'] and r['validity']=='current']
  fixed={r['target'] for r in rel if r['kind']=='work_fixed_artifact' and r['source']==t}
  candidate_id=(c or {}).get('patch_id') or (c or {}).get('evidence_id')
  reviewed=any(r['kind']=='review_candidate' and r['target']==candidate_id and r['details'].get('decision')=='accept' and r['version']==(c or {}).get('identity',{}).get('source_reference') and ((isinstance(r['work_revision'],dict) and r['work_revision'].get(t)==w.get('task_revision')) or r['work_revision']==w.get('work_epoch')) for r in rel)
  debt+=0 if c and w.get('completion_current') and reviewed else (1 if tested and not all(r['details'].get('passed') for r in tested) else .5 if not tested else 1)
 v[2]=min(1,debt/8)
 artifacts={r['target'] for r in rel if r['kind']=='work_fixed_artifact' and r['details'].get('author')!='member_001'}
 adopted={r['source'] for r in rel if r['kind']=='artifact_adopted' and r['target']=='member_001'}
 planned={a['patch_id'] for a in candidate.get('planned_adoptions',[]) if a['actor']=='member_001'}
 v[3]=min(1,(len(artifacts-adopted-planned)+sum(weights[t] for t,w in pending.items() if w['owner']!='member_001')/max(1,total)+state.get('conflict_count',0))/max(1,len(leaves)))
 v[5]=(1-remaining/5_000_000)*v[4];v[6]=v[1]*v[2]
 if any(not math.isfinite(x) for x in v):raise ValueError('Finite bounded features required')
 return v

def initialize():return {'version':SPEC['version'],'update':0,'theta':{p:[0.]*7 for p in POLICIES},'fit_history':[],'spec':SPEC}
def evaluate(state,bank,policy,seed):
 cs=bank['candidates'];r={z:1/len(cs) for z in cs};remaining=bank['remaining_branch_token_limit']
 fs={kind:{z:features(state,c,remaining,kind) for z,c in cs.items()} for kind in ('L','P')}
 qs={'q0':r,**{p:distribution(policy['theta'][p],fs[p[0]],r) for p in POLICIES},'KEEP':{z:float(z=='KEEP') for z in cs}}
 u=random.Random(seed).random();acc=0;chosen=None
 for z in sorted(cs):
  acc+=qs['P_CN'][z]
  if chosen is None and u<acc:chosen=z
 return {'policy_update':policy['update'],'features':fs,'probabilities':qs,'reference':r,'random_u':u,'selected':chosen,'selected_policy':'P_CN','seed':seed,'frozen_before_results':True,'feature_degenerate':len(cs)>1 and len({tuple(v) for v in fs['P'].values()})==1}

def update(policy,records,window):
 if not records:raise ValueError('No complete development state to update')
 out=copy.deepcopy(policy);details={}
 for p in POLICIES:
  targets=[];ds=[]
  for record in records:
   dec=record['decision'];q=dec['probabilities'][p];u={z:utility(v['legal_correct'],v['logical_tokens']) for z,v in record['outcomes'].items()}
   if set(q)!=set(u):raise ValueError('No partial candidate panel learning')
   result=target_distribution(q,dec['reference'],u,use_novelty=p!='P_C')
   targets.append({'features':dec['features'][p[0]],'reference':dec['reference'],'target':result['q_after']})
   ds.append({'index':record['index'],'before':q,'utilities':u,'update':result})
  fitted=fit(policy['theta'][p],targets);out['theta'][p]=fitted['theta'];details[p]={'states':ds,'fit':fitted}
 out['update']+=1;out['fit_history'].append({'window':window,'records':[r['index'] for r in records],'details':details});return out
