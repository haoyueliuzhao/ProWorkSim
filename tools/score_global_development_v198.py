"""Development regression on frozen AI references; new evidence stays unknown."""
import sys,json,random,csv
from pathlib import Path
from collections import Counter,defaultdict
from statistics import mean
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref

BASE=ROOT/'artifacts/software-benchmark-v198'
def ratio(a,b):return a/b if b else None
def main():
    data=read(BASE/'development-r1/summary.json');points=read(ROOT/'artifacts/software-benchmark-v197/private-map-r1/manifest.json')['points'];labels={};essential={}
    for p in points:
        inverse={v:k for k,v in p['event_map'].items()};ad=read(ROOT/'artifacts/software-benchmark-v197/adjudicator-r1'/f'{p["point"]}.json')
        labels[p['point']]={inverse[x['event']]:x['label'] for x in ad['labels']};essential[p['point']]={e for e,l in labels[p['point']].items() if l=='essential'}
    rows=[]
    for r in data['rows']:
        chosen=set(r['selected']);known=labels[r['point']];required=essential[r['point']]
        relevant={e for e,l in known.items() if l in {'essential','useful'}};irrelevant={e for e,l in known.items() if l=='irrelevant'};unknown=chosen-set(known)
        rows.append({**r,'old_required':len(required),'old_required_selected':len(required&chosen),
            'old_relevant_selected':len(chosen&relevant),'old_irrelevant_selected':len(chosen&irrelevant),'new_unlabelled_selected':len(unknown),
            'old_required_recall':ratio(len(required&chosen),len(required)),
            'precision_lower':ratio(len(chosen&relevant),len(chosen)),'precision_upper':ratio(len(chosen&relevant)+len(unknown),len(chosen))})
    groups=[]
    for budget in [1024,2048,4096]:
        for method in ['G0','G1','G2','G3','G4']:
            rs=[r for r in rows if r['condition']==method and r['budget']==budget];n=sum(len(r['selected']) for r in rs)
            by_task=defaultdict(list)
            for r in rs:
                if r['old_required_recall'] is not None:by_task[r['instance_id']].append(r['old_required_recall'])
            groups.append({'condition':method,'budget':budget,'points':len(rs),'tasks':len({r['instance_id'] for r in rs}),
                'old_essential_selected':sum(r['old_required_selected'] for r in rs),'old_essential_denominator':sum(r['old_required'] for r in rs),
                'old_essential_recall':ratio(sum(r['old_required_selected'] for r in rs),sum(r['old_required'] for r in rs)),
                'task_balanced_old_recall':mean(mean(v) for v in by_task.values()) if by_task else None,
                'input_tokens_estimate_sum':sum(r['input_tokens_estimate'] for r in rs),'added_tokens_estimate_sum':sum(r['added_tokens_estimate'] for r in rs),
                'cards':n,'old_irrelevant_selected':sum(r['old_irrelevant_selected'] for r in rs),
                'new_unlabelled_selected':sum(r['new_unlabelled_selected'] for r in rs),
                'precision_lower':ratio(sum(r['old_relevant_selected'] for r in rs),n),
                'precision_upper':ratio(sum(r['old_relevant_selected']+r['new_unlabelled_selected'] for r in rs),n),
                'coverage_infeasible_points':sum(not r['coverage_constraint_satisfied'] for r in rs),
                'unmet_mandatory_events':sum(len(r['unmet_mandatory']) for r in rs)})
    changed={};set_changed={};payload_changed={}
    for a,b in [('G2','G3'),('G3','G4')]:
        for budget in [1024,2048,4096]:
            left={r['point']:r for r in rows if r['condition']==a and r['budget']==budget};right={r['point']:r for r in rows if r['condition']==b and r['budget']==budget}
            changed[f'{a}:{b}:{budget}']=sum(left[p]['selected']!=right[p]['selected'] for p in left)
            set_changed[f'{a}:{b}:{budget}']=sum(set(left[p]['selected'])!=set(right[p]['selected']) for p in left)
            payload_changed[f'{a}:{b}:{budget}']=sum(left[p]['payload']['sha256']!=right[p]['payload']['sha256'] for p in left)
    save(BASE/'development-score-r1/summary.json',{'groups':groups,'rows':rows,'selection_changes':changed,
        'selected_set_changes':set_changed,'actual_presented_payload_changes':payload_changed,
        'selection_changes_means_internal_ordered_list_not_necessarily_changed_input':True,
        'reference':'unchanged v197 AI labels; no independent/human gold claim','new_pool_items_unlabelled_not_counted_as_false':True,
        'precision_bounds_are_missing_label_bounds_not_confidence_intervals':True,'new_task_success_not_measured':True})
    # Sample source gaps independently of which algorithms selected them.
    corpus=[];seen=set()
    for inv in data['inventories']:
        for e in inv['additional_candidates']:
            key=(inv['instance_id'],e['event_id'])
            if key not in seen:corpus.append({'point':inv['point'],'instance_id':inv['instance_id'],**e});seen.add(key)
    rng=random.Random(20261111198);rng.shuffle(corpus);sample=corpus[:12]
    save(BASE/'open-world-review-r1/source-sample.json',{'seed':20261111198,'unique_additional_events':len(corpus),'rows':sample,'selected_without_method_outcomes':True})
    for g in groups:
        if g['budget']==4096:print(g)
    print('changed',changed)
if __name__=='__main__':main()
