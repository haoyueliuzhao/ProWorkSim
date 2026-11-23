"""Five bounded response/state interactions. Fit only complete development panels."""
from collections import Counter, defaultdict
from math import exp, expm1, log, isfinite

from .software_fixed_organization_clone_v131 import clone_function
from . import software_organization_selector_v216 as base

FEATURES = ('anomaly_progress','dependency_pressure','ownership_mismatch','verification_debt','resource_pressure')
SPEC = {**base.SPEC,'version':'v226-anomaly-response-5','features':FEATURES,'initial_theta':[0.]*5,
        'drift_l2':1.0}
ns = {**vars(base),'FEATURES':FEATURES,'SPEC':SPEC}
distribution = clone_function(base.distribution,ns)
ns['distribution']=distribution
fit=clone_function(base.fit,ns)

def response_class(kind, plan):
    """Invariant to tool order, task IDs and member names. Dedupe semantic targets upstream."""
    tools={action['tool'] for action in plan['actions']}
    fields=(plan['diagnosis'],bool(tools & {'assign_work','offer_joint_arrangement'}),
            tuple(sorted(tools & {'add_collaboration','integrate_patch','split_work','change_dependency'})),
            tuple(sorted(tools & {'assign_verification','open_patch_review','run_patch_review_tests','run_tests'})))
    return (kind, *fields)

def evaluate(node, context, candidates, theta):
    if len(theta)!=5 or not candidates or 'KEEP' not in candidates:raise ValueError('Invalid policy support')
    classes={k:response_class(node['anomaly_type'],v) for k,v in candidates.items()}
    sizes=Counter(classes.values())
    r={k:1/(len(sizes)*sizes[g]) for k,g in classes.items()}
    pressures=[context[f] for f in FEATURES]
    if not all(isfinite(x) and 0<=x<=1 for x in pressures):raise ValueError('Need normalized predecision pressures')
    features={}
    for k,c in candidates.items():
        ops={a['tool'] for a in c['actions']}
        interactions=(float(c['diagnosis']!='current'),float(bool(ops & {'integrate_patch','change_dependency'})),
                      float(bool(ops & {'assign_work','offer_joint_arrangement','split_work'})),
                      float(bool(ops & {'assign_verification','run_tests','run_patch_review_tests','open_patch_review'})),
                      min(1,len(c['actions'])/8))
        features[k]=[x*y for x,y in zip(pressures,interactions)]
    q=distribution(theta,features,r)
    return {'features':features,'q':q,'r':r,'classes':classes}

def feedback(decision, outcomes, *, novelty=True):
    q,r=decision['q'],decision['r']
    if set(q)!=set(outcomes) or len(q)<2:raise ValueError('A complete comparative panel is required')
    u={z:base.utility(o['legal_correct'],o['logical_tokens']) for z,o in outcomes.items()}
    center=sum(q[z]*u[z] for z in q)
    c={z:u[z]-center for z in q}
    qm,rm=defaultdict(float),defaultdict(float)
    for z,g in decision['classes'].items():qm[str(g)]+=q[z];rm[str(g)]+=r[z]
    n={z:max(0.,log(rm[str(g)]/qm[str(g)])) for z,g in decision['classes'].items()}
    eps=SPEC['epsilon']
    def weight(z):
        cp=eps+(1-2*eps)/(1+exp(-c[z]/SPEC['t_c']))
        np=eps+(1-2*eps)*(-expm1(-n[z]/SPEC['t_n']))
        return q[z]**SPEC['rho']*r[z]**(1-SPEC['rho'])*(cp**SPEC['alpha']*np**(SPEC['beta'] if novelty else 0))**SPEC['eta']
    weights={z:weight(z) for z in q}
    target={z:(1-SPEC['delta'])*v/sum(weights.values())+SPEC['delta']*r[z] for z,v in weights.items()}
    return {'C':c,'N':n,'target':target,'features':decision['features'],'reference':r}

def context_from(node, organization, remaining_tokens, task_limit=5_000_000):
    """Build predecision pressures from authorized, scoped work only."""
    if not 0<=remaining_tokens<=task_limit:raise ValueError('Invalid available budget')
    work=organization['work']
    leaves=[work[t] for t in node['affected_work'] if t in work and not work[t].get('children')]
    deps=[(w,work[d]) for w in leaves for d in w.get('depends_on',[]) if d in work]
    revisions={str(e.get('source_reference')) for e in node['evidence_refs'] if e.get('source_reference')}
    return dict(zip(FEATURES,(
        min(1,(len(revisions)+node.get('recurrence',0))/4),
        sum(a.get('owner')!=b.get('owner') for a,b in deps)/max(1,len(deps)),
        float(node['anomaly_type'] in ('A1','A2','A5') and bool(leaves) and len({w.get('owner') for w in leaves})==1),
        max(float(node['anomaly_type']=='A4'),sum(not w.get('reviewer') or w.get('reviewer')==w.get('owner') for w in leaves)/max(1,len(leaves))),
        1-remaining_tokens/task_limit)))

def panel_by_effect(plans):
    """Preserve candidate sources; deduplicate identical scoped operational effects."""
    from .software_project_relations_v217 import identity
    import json
    output={}
    for source,plan in plans:
        steps=[]
        for step in plan['actions']:
            args={k:v for k,v in step.get('arguments',{}).items() if k not in ('reason','body','message')}
            steps.append((step['actor'],step['tool'],json.dumps(args,sort_keys=True),
                          json.dumps(step.get('arguments_from_real_receipt'),sort_keys=True)))
        effect=identity([sorted(steps),plan['diagnosis'],sorted(plan.get('response_categories',[]))])
        label='KEEP' if plan.get('keep') and not steps else effect
        if label not in output:output[label]={**plan,'sources':[]}
        output[label]['sources'].append(source)
    return output

def development_update(theta, panels, *, window, novelty=True):
    """No historical rewards. C-only and joint fits consume the same second window."""
    if window not in (1,2) or len(panels)!=2 or len({p['instance_id'] for p in panels})!=2:
        raise ValueError('Exactly two different development states per window')
    rows=[]
    for p in panels:
        if p.get('split')!='development' or p.get('policy_before')!=list(theta):
            raise ValueError('Policy or sample identity mismatch')
        if not p.get('complete') or len(p['decision']['q'])<2 or len({tuple(v) for v in p['decision']['features'].values()})<2:
            return {'updated':False,'theta':list(theta),'reason':'incomplete_or_uninformative_panel'}
        rows.append(feedback(p['decision'],p['outcomes'],novelty=novelty))
    fitted=fit(theta,rows)
    return {'updated':fitted['theta']!=list(theta),'theta':fitted['theta'],'diagnostics':rows,'fit':fitted}

def confirmation_value(probabilities,outcomes):
    if set(probabilities)!=set(outcomes):raise ValueError('Incomplete confirmation panel')
    return sum(probabilities[z]*base.utility(o['legal_correct'],o['logical_tokens']) for z,o in outcomes.items())
