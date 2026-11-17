"""Offline statistical design and passive evidence; no API, Docker or live mutation."""
from __future__ import annotations
import math, random, collections
ARMS=('KEEP','ASSIST','TRANSFER')
def validate(q):
 if set(q)!=set(ARMS) or any(not math.isfinite(v) or v<=0 for v in q.values()) or abs(sum(q.values())-1)>1e-12:raise ValueError('Positive normalized three-arm distribution required')
 return q

def choose(q,u):
 validate(q)
 if not 0<=u<1:raise ValueError('Uniform draw outside [0,1)')
 c=0
 for z in ARMS:
  c+=q[z]
  if u<c:return z
 return ARMS[-1]

def distances(q,p):
 validate(q);validate(p)
 return {'TV':sum(abs(q[z]-p[z]) for z in ARMS)/2,'KL_q_p':sum(q[z]*math.log(q[z]/p[z]) for z in ARMS),'entropy_nats':-sum(q[z]*math.log(q[z]) for z in ARMS)}

def coupling(q,p):
 """Exact disagreement of common inverse CDF, distinct from maximal coupling TV."""
 cuts={0.,1.}
 for d in (q,p):
  c=0
  for z in ARMS[:-1]:c+=d[z];cuts.add(c)
 cuts=sorted(cuts)
 common=sum(b-a for a,b in zip(cuts,cuts[1:]) if choose(q,(a+b)/2)!=choose(p,(a+b)/2))
 return {'TV':distances(q,p)['TV'],'common_inverse_cdf_disagreement':common,'independent_draw_disagreement':1-sum(q[z]*p[z] for z in ARMS)}

def apportioned(q,n,seed):
 """Randomized systematic quotas: sum=n, E[count_z]=n*q_z. No score input.

Each realized count is floor/ceil of n*q. A separately seeded permutation assigns
labels to the panel; independently call per condition. Retain same-arm pairs.
"""
 validate(q)
 if type(n)!=int or n<1:raise ValueError('Positive panel size')
 rng=random.Random(seed);offset=rng.random();labels=[choose(q,(j+offset)/n) for j in range(n)];rng.shuffle(labels)
 return {'labels':labels,'counts':{z:labels.count(z) for z in ARMS},'offset':offset,'seed':seed,'expected_counts':{z:n*q[z] for z in ARMS}}

def contribution(q,rows,lam=.1):
 """Independent reconstruction, not importing old update implementation."""
 validate(q)
 if not rows or len({r['state_id'] for r in rows})!=len(rows):raise ValueError('Distinct complete states required')
 raw={z:[] for z in ARMS};quality={z:[] for z in ARMS};cost={z:[] for z in ARMS};repos=[]
 for row in rows:
  if row.get('stage')!='development' or set(row['results'])!=set(ARMS):raise ValueError('Development-only complete blocks')
  yy={};tt={}
  for z,v in row['results'].items():
   if type(v['y']) is not bool or type(v['tokens']) is not int or not 0<=v['tokens']<=5_000_000:raise ValueError('Known outcomes and full-team token ceiling')
   yy[z]=int(v['y']);tt[z]=v['tokens']
  u={z:yy[z]-lam*tt[z]/5_000_000 for z in ARMS}
  for z in ARMS:
   quality[z].append(yy[z]-yy['KEEP']);cost[z].append(-(tt[z]-tt['KEEP'])/5_000_000);raw[z].append(u[z]-u['KEEP'])
  repos.append(row['repo'])
 n=len(rows);means={z:sum(raw[z])/n for z in ARMS};center=sum(q[z]*means[z] for z in ARMS)
 c={z:means[z]-center for z in ARMS}
 # Task-weighted mean with repository-cluster sandwich SE; not G independent tasks.
 uncertainty={}
 for z in ARMS:
  values=[raw[z][i]-sum(q[k]*raw[k][i] for k in ARMS) for i in range(n)]
  residuals=collections.defaultdict(float)
  for repo,v in zip(repos,values):residuals[repo]+=v-c[z]
  g=len(residuals)
  se=math.sqrt(g/(g-1)*sum(v*v for v in residuals.values())/n**2) if g>1 else None
  uncertainty[z]={'estimate':c[z],'cluster_SE':se,'diagnostic_normal_95_interval':None if se is None else [c[z]-1.96*se,c[z]+1.96*se],'safe_kappa1_diagnostic_only':None if se is None else c[z]-se,'states':n,'repo_clusters':g,'small_cluster_warning':g<8,'per_state_centered':values,'not_used_for_update':True}
 return {'raw_paired_total':raw,'mean_total':means,'contribution':c,'mean_quality':{z:sum(quality[z])/n for z in ARMS},'mean_cost':{z:sum(cost[z])/n for z in ARMS},'raw_quality':quality,'raw_cost':cost,'uncertainty':uncertainty}

def reconstruct_update(q,r,rows):
 validate(r);result=contribution(q,rows);c=result['contribution'];novel={z:max(0.,math.log(r[z]/q[z])) for z in ARMS}
 logs={z:.8*math.log(q[z])+(1-.8)*math.log(r[z])+.5*(c[z]+novel[z]) for z in ARMS}
 m=max(logs.values());w={z:math.exp(logs[z]-m) for z in ARMS};den=sum(w.values())
 new={z:.05+(1-3*.05)*w[z]/den for z in ARMS}
 return {**result,'novelty':novel,'q_after':new,'distance_from_previous':distances(new,q),'distance_from_reference':distances(new,r)}

def guarded_update(q,r,rows,min_states=8,min_repos=4,maximum_step_tv=.05):
 """New protocol: incomplete/undersized windows never update; cap drift by mixing.

CI and safe-C are diagnostic only. Convex interpolation preserves >=5% support.
"""
 if len(rows)<min_states or len({x['repo'] for x in rows})<min_repos:raise ValueError('Insufficient independent states/repositories; do not update a partial window')
 v=reconstruct_update(q,r,rows);tv=v['distance_from_previous']['TV'];mix=min(1.,maximum_step_tv/tv) if tv else 1.
 v['uncapped_q_after']=v['q_after'];v['q_after']={z:q[z]+mix*(v['uncapped_q_after'][z]-q[z]) for z in ARMS};v['step_mixing_weight']=mix
 v['distance_from_previous']=distances(v['q_after'],q);v['distance_from_reference']=distances(v['q_after'],r)
 return v

def action_chain(candidate,events,*,presented,after_sequence=0,task='diagnose',developer='member_001',peer='member_002'):
 """Evidence IDs only. Recipient work is temporal observation, not proven causality."""
 if candidate not in ARMS:raise ValueError('Unknown candidate')
 ee=sorted((e for e in events if e['sequence']>after_sequence),key=lambda e:e['sequence'])
 def ids(es):return [{'sequence':e['sequence'],'operation_id':e.get('operation_id'),'action_id':e.get('action_id')} for e in es]
 scoped=[e for e in ee if e.get('task_id')==task]
 offers=[e for e in scoped if e['kind']=='transfer_offered' and e.get('from_member')==developer and e.get('recipient')==peer]
 def accepted(o,frm,to):return [e for e in scoped if e['kind']=='transfer_accepted' and e['sequence']>o['sequence'] and e.get('offer_id')==o.get('offer_id') and e.get('previous_owner')==frm and e.get('owner')==to and e.get('actor_id')==to]
 accepts=[e for o in offers for e in accepted(o,developer,peer)]
 assist=[e for e in scoped if e['kind']=='work_message' and e.get('actor_id')==developer and e.get('recipient')==peer]
 initiated=offers if candidate=='TRANSFER' else assist if candidate=='ASSIST' else []
 begin=min((e['sequence'] for e in (accepts if candidate=='TRANSFER' else assist)),default=None)
 releases=[e for e in scoped if begin is not None and e['sequence']>begin and e['kind']=='task_returned' and e.get('actor_id')==peer]
 back_offers=[e for e in scoped if begin is not None and e['sequence']>begin and e['kind']=='transfer_offered' and e.get('from_member')==peer and e.get('recipient')==developer]
 back=[e for o in back_offers for e in accepted(o,peer,developer) if not any(begin<release['sequence']<e['sequence'] for release in releases)]
 end=min((e['sequence'] for e in releases+back),default=float('inf'))
 work=[e for e in ee if begin is not None and begin<e['sequence']<end and e.get('actor_id')==peer and e['kind'] in ('read','search','repository_search','test')]
 findings=[e for e in scoped if begin is not None and e['sequence']>begin and e['kind']=='work_message' and e.get('actor_id')==peer and e.get('recipient')==developer]
 decline=[e for e in scoped if e['kind']=='transfer_declined' and e.get('offer_id') in {o.get('offer_id') for o in offers}]
 return {'selected':candidate,'instruction_presented':presented,'committed_initiation':ids(initiated),'offer':ids(offers),'accept_and_owner_change':ids(accepts),'recipient_work_observed':ids(work),'findings_message_observed':ids(findings),'legal_return_offer_accept':ids(back),'release_to_unassigned_not_legal_return':ids(releases),'declined':ids(decline),'organization_changed':bool(accepts) if candidate=='TRANSFER' else bool(assist and (work or findings)) if candidate=='ASSIST' else None,'diagnostic_evidence_validated':None,'work_outcome_requires_separate_exact_version_score':True,'no_inference_from_lifecycle_finished':True}
