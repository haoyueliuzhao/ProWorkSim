"""Task-shared low-dimensional selector, no task/repo/graph-ID learned features.

Offline until stage-A gate passes. Whole candidate utility, not credit to each
operator; actual permissions remain exclusively in the managed world.
"""
import math
from .software_organization_space_v210 import update_bank
VERSION='v212-shared-selector-r1'
FEATURES=('owner_load_balance','cross_owner_dependency_fraction','closure_per_remaining_scope','proposal_steps_per_remaining_budget','steps_times_cross_owner_dependencies')
SPEC={'version':VERSION,'features':FEATURES,'delta':.05,'initial_theta':[0.]*5,'epsilon':.05,'t_c':1.,'t_n':1.,'alpha':1.,'beta':1.,'rho':.8,'eta':.5,'cost_weight':.1,'drift_l2':.1,'fit_steps':400,'learning_rate':.05,'task_ids_as_features':False,'within_task_updates':False,'confirmation_runs_all_candidates':True}

def feature_vector(state,target,steps,remaining_tokens):
 """Both states are trusted dynamic-status projections; no hidden outcome inputs."""
 if not 0<remaining_tokens<=5_000_000 or steps<0:raise ValueError('Remaining budget and actual proposed steps required')
 leaves={k:w for k,w in target['work'].items() if not w.get('children') and not w.get('completion')}
 if not leaves:raise ValueError('No unfinished work')
 loads={m:sum(len(w['scope']) for w in leaves.values() if w['owner']==m) for m in ('member_001','member_002')};total=sum(loads.values())
 if not total:raise ValueError('Scope required')
 balance=1-abs(loads['member_001']-loads['member_002'])/total
 edges=[(k,parent) for k,w in leaves.items() for parent in w.get('depends_on',[])];cross=sum(target['work'][a]['owner']!=target['work'][b]['owner'] for a,b in edges)/max(1,len(edges))
 closure=len(leaves)/total
 effort=min(1.,steps/max(1.,20*remaining_tokens/5_000_000))
 return [balance,cross,closure,effort,effort*cross]

def distribution(theta,features,reference):
 keys=set(features)
 if keys!=set(reference) or not keys or abs(sum(reference.values())-1)>1e-10 or any(x<=0 for x in reference.values()):raise ValueError('Positive same-support reference required')
 if len(theta)!=len(FEATURES) or any(len(v)!=len(theta) for v in features.values()):raise ValueError('Frozen low-dimensional features required')
 logs={k:math.log(reference[k])+sum(a*b for a,b in zip(theta,features[k])) for k in features}
 mx=max(logs.values());p={k:math.exp(v-mx) for k,v in logs.items()};den=sum(p.values());p={k:v/den for k,v in p.items()}
 d=SPEC['delta'];return {k:(1-d)*p[k]+d*reference[k] for k in p}

def utility(correct_legal,tokens,budget=5_000_000):
 if type(correct_legal)is not bool or not 0<=tokens<=budget:raise ValueError('Known legal correctness and complete actual usage required')
 return float(correct_legal)-SPEC['cost_weight']*tokens/budget

def target_distribution(q,r,u,*,use_novelty=True):
 result=update_bank(q,r,u,epsilon=SPEC['epsilon'],t_c=SPEC['t_c'],t_n=SPEC['t_n'],alpha=SPEC['alpha'],beta=SPEC['beta'] if use_novelty else 0,rho=SPEC['rho'],eta=SPEC['eta'],support_mass=SPEC['delta'])
 if max(result['undercoverage_novelty'].values())>math.log(1/SPEC['delta'])+1e-10:raise ValueError('Support-mixture bound violated')
 return result

def fit(theta_old,records):
 """Fixed-step KL target fit with task-shared parameters and drift penalty.

records contain precomputed feature/reference/target dictionaries. State keys are
only joins; coefficients have fixed FEATURES dimensions, never candidate IDs.
"""
 if not records:raise ValueError('Complete development states required')
 theta=list(theta_old);d=SPEC['delta'];lam=SPEC['drift_l2']
 for _ in range(SPEC['fit_steps']):
  gradient=[lam*(x-old) for x,old in zip(theta,theta_old)]
  for row in records:
   f,r,t=row['features'],row['reference'],row['target'];q=distribution(theta,f,r)
   if set(t)!=set(q) or abs(sum(t.values())-1)>1e-10 or any(v<=0 for v in t.values()):raise ValueError('Complete positive target required')
   p={k:(q[k]-d*r[k])/(1-d) for k in q};mean=[sum(p[k]*f[k][j] for k in p) for j in range(len(theta))]
   for k in q:
    factor=-t[k]*(1-d)*p[k]/q[k]/len(records)
    for j in range(len(theta)):gradient[j]+=factor*(f[k][j]-mean[j])
  theta=[x-SPEC['learning_rate']*g for x,g in zip(theta,gradient)]
 errors=[]
 for row in records:
  q=distribution(theta,row['features'],row['reference']);t=row['target'];errors.append({'KL':sum(t[k]*math.log(t[k]/q[k]) for k in q),'TV':.5*sum(abs(t[k]-q[k]) for k in q)})
 return {'theta':theta,'old_theta':list(theta_old),'fit_errors':errors,'mean_KL':sum(x['KL'] for x in errors)/len(errors),'spec':SPEC}

def policy_value(q,results):
 """All confirmation candidates observed, no draw-based pseudo-comparison."""
 if set(q)!=set(results):raise ValueError('Every frozen candidate must have a known result')
 return {'utility':sum(q[k]*utility(results[k]['correct_legal'],results[k]['tokens']) for k in q),'quality':sum(q[k]*results[k]['correct_legal'] for k in q),'tokens':sum(q[k]*results[k]['tokens'] for k in q)}

def leave_one_out(theta,records):
 if len(records)<2:raise ValueError('At least two distinct states')
 return [fit(theta,records[:i]+records[i+1:]) for i in range(len(records))]
