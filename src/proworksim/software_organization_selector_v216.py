"""Task-shared low-dimensional selector, no task/repo/graph-ID learned features.

Offline until stage-A gate passes. Whole candidate utility, not credit to each
operator; actual permissions remain exclusively in the managed world.
"""
import math
from .software_organization_space_v210 import update_bank
VERSION='v216-shared-cn-selector-r1'
FEATURES=('owner_load_balance','cross_owner_dependencies','verification_debt','projected_integration_debt','coordination_steps','budget_pressure_times_coordination','dependency_times_verification')
SPEC={'version':VERSION,'features':FEATURES,'delta':.05,'initial_theta':[0.]*7,'epsilon':.05,'t_c':1.,'t_n':1.,'alpha':1.,'beta':1.,'rho':.8,'eta':.5,'cost_weight':.1,'drift_l2':.1,'fit_steps':400,'learning_rate':.05,'task_ids_as_features':False,'within_task_updates':False,'confirmation_runs_all_candidates':True}
def feature_vector(state,target,steps,remaining_tokens):
 if not 0<remaining_tokens<=5_000_000 or steps<0:raise ValueError('Actual remaining task budget required')
 leaves={k:w for k,w in target['work'].items() if not w.get('children')};remaining={k:w for k,w in leaves.items() if w.get('completion') is None}
 loads={m:sum(len(w['scope']) for w in remaining.values() if w['owner']==m) for m in ('member_001','member_002')};total=max(1,sum(loads.values()))
 used={m:state.get('member_usage',{}).get(m,{}).get('known_actual_tokens',0)/5_000_000 for m in loads}
 projected={m:used[m]+loads[m]/total*(remaining_tokens/5_000_000) for m in loads}
 balance=1-min(1.,abs(projected['member_001']-projected['member_002']))
 deps=[(k,p) for k,w in leaves.items() for p in w.get('depends_on',[])];cross=sum(target['work'][a]['owner']!=target['work'][b]['owner'] for a,b in deps)/max(1,len(deps))
 debt=min(1.,sum(not w.get('completion_current',False) or w.get('needs_review',True) for w in leaves.values())/8)
 pending=state.get('pending_peer_patches',0);integration=min(1.,(pending+sum(w['owner']!='member_001' for w in remaining.values())+state.get('conflict_count',0))/max(1,len(leaves)+pending))
 coordination=min(1.,steps/16);pressure=1-remaining_tokens/5_000_000
 return [balance,cross,debt,integration,coordination,pressure*coordination,cross*debt]

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

def target_distribution(q,r,u,*,use_novelty=True,use_contribution=True):
 result=update_bank(q,r,u,epsilon=SPEC['epsilon'],t_c=SPEC['t_c'],t_n=SPEC['t_n'],alpha=SPEC['alpha'] if use_contribution else 0,beta=SPEC['beta'] if use_novelty else 0,rho=SPEC['rho'],eta=SPEC['eta'],support_mass=SPEC['delta'])
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
