"""Learn on matched, active organization graphs. Public terminal scores are evaluator-side."""
from collections import defaultdict
from math import isfinite

from . import software_anomaly_selector_v226 as previous
from . import software_organization_selector_v216 as estimator
from .software_fixed_organization_clone_v131 import clone_function
from .software_osa_session_v226 import fingerprint

TYPES = ('A1','A2','A3','A4','A5')
OPERATIONS = ('diagnosis','verify','transfer_unstarted','release_diagnosis')
FEATURES = (*TYPES,*OPERATIONS,'used_budget')
Q0 = [0.] * len(FEATURES)
SPEC = {**previous.SPEC,'version':'v229-controlled-graph-pairs','features':FEATURES,'initial_theta':Q0}
namespace = {**vars(estimator),'FEATURES':FEATURES,'SPEC':SPEC}
distribution = clone_function(estimator.distribution,namespace)
fit = clone_function(estimator.fit,{**namespace,'distribution':distribution})


def support(menu, choice, checkpoint, remaining, theta):
    if not checkpoint or not 0 < remaining <= 5_000_000 or len(theta)!=len(Q0) or not all(map(isfinite,theta)):
        raise ValueError('Invalid saved decision state or policy')
    if menu['base_sha256']!=fingerprint(menu['graph']) or menu['anomaly'] not in TYPES:
        raise ValueError('Unknown organization or anomaly')
    if set(choice)!={'option','reason','evidence'} or not isinstance(choice['reason'],str) or not choice['reason'].strip():
        raise ValueError('Controller must submit a reason and cite current evidence')
    if not isinstance(choice['evidence'],list) or not choice['evidence'] or not all(isinstance(i,str) and i in menu['evidence'] for i in choice['evidence']):
        raise ValueError('Unbound evidence')
    candidate=menu['options'][choice['option']]
    kind=menu['anomaly']; op=candidate['op']
    if op!='keep' and op not in OPERATIONS:raise ValueError('Unsupported graph transform')
    features={'KEEP':[0.]*len(Q0)}
    if op!='keep':
        features['CHANGE']=[float(t==kind) for t in TYPES]+[float(t==op) for t in OPERATIONS]+[1-remaining/5_000_000]
    r={arm:1/len(features) for arm in features}
    decision={'features':features,'r':r,'q':distribution(theta,features,r),
              'classes':{arm:(kind,op if arm=='CHANGE' else 'keep') for arm in features}}
    return {'menu':menu,'choice':choice,'checkpoint':checkpoint,'remaining':remaining,'before':list(theta),
            'kind':kind,'decision':decision}


def sample(panel, theta):
    bank=panel['bank']; arms=panel['arms']
    if bank['before']!=list(theta) or set(bank['decision']['q'])!={'KEEP','CHANGE'} or set(arms)!={'KEEP','CHANGE'}:
        raise ValueError('Incomplete controlled support')
    outcomes={}
    for arm, item in arms.items():
        expected=bank['choice']['option'] if arm=='CHANGE' else 'K'
        if (item.get('status')!='closed' or item.get('checkpoint')!=bank['checkpoint']
                or item.get('activated_option')!=expected or item.get('changed') is not (arm=='CHANGE')):
            raise ValueError('Arm activation or checkpoint mismatch')
        outcomes[arm]={'legal_correct':item['legal_correct'],'logical_tokens':item['logical_tokens']}
    return previous.feedback(bank['decision'],outcomes)


def update_window(theta, panels, planned_ids):
    ids=[p['instance_id'] for p in panels]
    if len(planned_ids)!=4 or len(set(planned_ids))!=4 or len(ids)!=len(set(ids)) or not set(ids)<=set(planned_ids):
        raise ValueError('One development admission per prospective state identity')
    records=[]; by_kind=defaultdict(list)
    for p in panels:
        if p['phase'] not in ('dev1','dev2'):raise ValueError('Confirmation cannot train a policy')
        res=sample(p,theta)
        records.append(res)
        by_kind[p['bank']['kind']].append({'instance_id':p['instance_id'],'C':res['C'],'N':res['N']})
    if len({p['phase'] for p in panels})>1 or len({p['bank']['checkpoint'] for p in panels})!=len(panels):
        raise ValueError('Distinct checkpoints in a single window required')
    diagnostics={kind:by_kind.get(kind,[]) for kind in TYPES}
    if len(records)<4:
        return {'fitted':False,'theta':list(theta),'paired_states':len(records),'by_anomaly':diagnostics}
    result=fit(theta,records)
    return {'fitted':True,'theta':result['theta'],'paired_states':4,'by_anomaly':diagnostics,'fit':result}


def paired_value(bank, arms, theta):
    if set(arms)!={'KEEP','CHANGE'}:raise ValueError('Both confirmation outcomes required')
    # Validate activation and terminal semantics even when evaluating another frozen policy.
    sample({'bank':bank,'arms':arms},bank['before'])
    d=bank['decision']
    probabilities=distribution(theta,d['features'],d['r'])
    value=sum(probabilities[a]*estimator.utility(arms[a]['legal_correct'],arms[a]['logical_tokens']) for a in arms)
    return {'q':probabilities,'value':value}
