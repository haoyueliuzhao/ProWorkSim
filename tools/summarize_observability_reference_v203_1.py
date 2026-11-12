"""Seal AI reference, preserve disagreements and abstention; never score O4 here."""
import collections,json,math
from pathlib import Path
from inventory_multimember_v203 import ROOT,read,ref,save
ART=ROOT/'artifacts/software-benchmark-v203-1'
def main():
    diagnostic={r['case_id']:r for r in read(ART/'panel-r1/selection-diagnostics.json')};rows=[];pairs=[]
    for n in range(1,37):
        c=f'OBS{n:03}';a=read(ART/f'review-a-r1/{c}.json');b=read(ART/f'review-b-r1/{c}.json')
        common=ART/f'common-confirmation-audit-r1/{c}.json';ad=ART/f'adjudication-r1/{c}.json';selected=common if common.exists() else ad if ad.exists() else ART/f'review-a-r1/{c}.json';r=read(selected)
        packet=read(ROOT/f'runs/software-benchmark-v203-1/review-packets-r1/{c}.json');assert set(r['evidence_event_ids'])<={e['event_id'] for e in packet['events']}
        rows.append({'case_id':c,**{k:diagnostic[c][k] for k in ['split','instance_id','repo','mode']},'reference':r,'reference_source':ref(selected),
            'A':ref(ART/f'review-a-r1/{c}.json'),'B':ref(ART/f'review-b-r1/{c}.json'),'packet':ref(ROOT/f'runs/software-benchmark-v203-1/review-packets-r1/{c}.json'),
            'runtime_dependency_automatically_confirmed':False,'confirmed_reference_scope':'limited_protocol_prerequisite_only' if r['task_dependency']=='Confirmed' else None})
        pairs.append((a,b))
    def agreement(field):
        values=[(str(a[field]),str(b[field])) for a,b in pairs];a=collections.Counter(x for x,y in values);b=collections.Counter(y for x,y in values);observed=sum(x==y for x,y in values)/len(values);chance=sum(a[k]*b[k] for k in a.keys()|b.keys())/len(values)**2
        return {'exact_agreement':observed,'kappa_with_unknown_category':(observed-chance)/(1-chance),'A':dict(a),'B':dict(b),'n':len(values)}
    summary={'tasks':36,'by_split':{},'agreement_before_arbitration':{f:agreement(f) for f in ['organization_mismatch','intervention_needed']},
        'first_disagreements':22,'additional_common_confirmation_checks':4,'AI_review_only_not_human_gold':True,'policy_outputs_hidden_during_review':True,
        'future_and_terminal_scores_hidden':True,'prior32_synthetic_controls_not_used_as_confirmation':True,'G2_G5_pass':False,
        'reason':'Zero supported positive organization-reconfiguration references; uncertainty and repository overlap remain. No method precision/recall or causal comparison calculated.',
        'hypothetical_exact_binomial_95pct_lower_if_all_correct':{str(n):.025**(1/n) for n in [7,30,36]},'new_benchmark_API_calls':0}
    for split in ['development','validation']:
        rs=[r['reference'] for r in rows if r['split']==split]
        summary['by_split'][split]={'n':len(rs),**{f:dict(collections.Counter(str(r[f]) for r in rs)) for f in ['organization_mismatch','intervention_needed','task_dependency']},
            'actions':dict(collections.Counter('|'.join(sorted(r['acceptable_actions'])) for r in rs))}
    save(ART/'reference-r2/per-task.json',rows);save(ART/'reference-r2/summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
