"""Score frozen selections against independently completed blind annotations.

Event-level default-card recall is not factual comprehension or task success.
Every method still exposes the same original-history reader.
"""
from __future__ import annotations
import sys,json,hashlib,math,re
from pathlib import Path
from collections import Counter,defaultdict
from statistics import mean
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,OUT,BLIND,read,save,ref,frame_for,graph_from_snapshot
from prepare_dependency_disputes_v197 import validate
from proworksim.software_dependency_query_v197 import typed_routes,state

def ratio(a,b):return a/b if b else None
def avg(xs):
    xs=[x for x in xs if x is not None];return mean(xs) if xs else None
def agreement(pairs):
    # Uncertain items do not silently become negative gold labels.
    known=[(a=='essential',b=='essential') for a,b in pairs if 'uncertain' not in (a,b)]
    n=len(known);pa=ratio(sum(a for a,b in known),n);pb=ratio(sum(b for a,b in known),n)
    po=ratio(sum(a==b for a,b in known),n);pe=pa*pb+(1-pa)*(1-pb) if n else None
    kappa=(po-pe)/(1-pe) if n and pe<1 else None
    return {'paired_items':len(pairs),'known_binary_items':n,'uncertain_items_excluded':len(pairs)-n,
        'exact_four_label_agreement':ratio(sum(a==b for a,b in pairs),len(pairs)),
        'essential_binary_agreement':po,'essential_binary_cohen_kappa':kappa,
        'positive_agreement':ratio(2*sum(a and b for a,b in known),sum(a for a,b in known)+sum(b for a,b in known)),
        'undefined_kappa_not_counted_as_gate_pass':True}

def point_metrics(labels,selected,must_keep):
    essential={e for e,l in labels.items() if l=='essential'};relevant={e for e,l in labels.items() if l in {'essential','useful'}}
    irrelevant={e for e,l in labels.items() if l=='irrelevant'};unknown={e for e,l in labels.items() if l=='uncertain'};chosen=set(selected)
    return {'essential_count':len(essential),'essential_selected':len(chosen&essential),
        'essential_recall':ratio(len(chosen&essential),len(essential)),
        'relevant_selected':len(chosen&relevant),'irrelevant_selected':len(chosen&irrelevant),
        'uncertain_selected':len(chosen&unknown),'selected_count':len(chosen),
        'evidence_precision_lower':ratio(len(chosen&relevant),len(chosen)),
        'evidence_precision_upper':ratio(len(chosen&(relevant|unknown)),len(chosen)),
        'critical_failure_count':len(must_keep),'critical_failures_selected':len(chosen&must_keep),
        'critical_failure_recall':ratio(len(chosen&must_keep),len(must_keep))}

def dependency_coverage(point,annotation):
    frame,indices,s,pool,cutoff=frame_for(point);g=graph_from_snapshot(s)
    necessary=[d for d in annotation['dependencies'] if d.get('necessary') is True]
    def path(entity):
        if not isinstance(entity,str):return None
        hits={m.group(1) for m in re.finditer(r'(?:/testbed/)?([\w./-]+\.py)',entity)}&set(g._file_nodes)
        return next(iter(hits)) if len(hits)==1 else None
    identifiable=[];unmapped=[]
    for d in necessary:
        a,b=path(d['from']),path(d['to'])
        if a and b and a!=b:identifiable.append((a,b,d))
        else:unmapped.append(d)
    measures={}
    for condition in ['G3','G4']:
        roots,routes,_=typed_routes(g,state(frame),inferred=condition=='G4');covered=[]
        for a,b,d in identifiable:
            matched=False
            for target,route in routes.items():
                if not route['edges']:continue
                ends={g.nodes[target]['attrs'].get('path'),g.nodes[route['root']]['attrs'].get('path')}
                if {a,b}<=ends:
                    kind=d['relation'];edge_types={g.edges[eid]['type'] for eid in route['edges']}
                    compatible={'import':{'imports'},'call':{'calls'},'test':{'tests'},'version':{'modifies','derived_from'},'other':set()}.get(kind,set())
                    if compatible and compatible&edge_types:matched=True
            if matched:covered.append(d)
        measures[condition]={'annotated_necessary_relations':len(necessary),
            'explicit_observed_cross_file_pairs':len(identifiable),'unmapped_or_not_cross_file':len(unmapped),
            'matched_typed_query_paths':len(covered),'cross_file_query_recall':ratio(len(covered),len(identifiable)),
            'scope':'explicit path endpoint mapping only; not complete symbol-level or runtime dependency recall',
            'covered_annotations':covered}
    return measures

def main():
    dest=OUT/'annotated-results-r1'
    if (dest/'summary.json').exists():raise ValueError('Preserve completed score')
    comparison=read(OUT/'ablation-r1/summary.json');mapping=read(OUT/'private-map-r1/manifest.json')['points']
    pairs=[];jaccards=[];annotations={};review_refs=[];coverage=Counter();disagreements=[];unresolved=0;corrections=0;citation_resolutions=[]
    for p in mapping:
        bid=p['point'];brief=read(BLIND/bid/'brief.json')
        files=[OUT/f'reviewer-{w}-r1/{bid}.json' for w in ['A','B']];a,b=map(read,files)
        aa=validate(a,brief,'A');bb=validate(b,brief,'B')
        for event in aa:pairs.append((aa[event]['label'],bb[event]['label']))
        ae={e for e,l in aa.items() if l['label']=='essential'};be={e for e,l in bb.items() if l['label']=='essential'}
        jaccards.append({'point':bid,'intersection':len(ae&be),'union':len(ae|be),'Jaccard':ratio(len(ae&be),len(ae|be))})
        path=OUT/'adjudicator-r1'/f'{bid}.json';ad=read(path)
        assert ad['point']==bid and ad['review_type']=='AI_blind_adjudication'
        labels={r['event']:r['label'] for r in ad['labels']};assert len(labels)==len(ad['labels']) and set(labels)==set(aa)
        assert set(labels.values())<={'essential','useful','irrelevant','uncertain'}
        prefix=read(BLIND/bid/'visible-prefix.json.gz');indices={s['message_index'] for s in prefix['source_messages']}
        for item in ad['labels']:
            assert item['reason'] and item['source_messages'] and set(item['source_messages'])<=indices
            e=item['event'];different=aa[e]['label']!=bb[e]['label']
            if different:disagreements.append({'point':bid,'event':e,'A':aa[e]['label'],'B':bb[e]['label'],
                'adjudicated':labels[e],'reason':item['reason'],'resolution':item['resolution']})
            elif labels[e]!=aa[e]['label']:
                assert item['resolution']=='source_error_override';corrections+=1
        for dependency_index,d in enumerate(ad['dependencies']):
            if d['source_messages']:
                assert set(d['source_messages'])<=indices
            else:
                # Preserve the adjudicator's explicit issue-level citation;
                # resolve its actual historical source without editing labels.
                assert 'brief.json:issue' in d['reason']
                provenance=read(BLIND/bid/'issue-source.json')
                assert provenance['issue_sha256']==hashlib.sha256(brief['issue'].encode()).hexdigest()
                assert provenance['first_seen_step']<=p['decision_step']
                citation_resolutions.append({'point':bid,'dependency_index':dependency_index,
                    'original_source_messages':[],'explicit_issue_citation':True,'resolved_source':provenance,'labels_changed':False})
            assert d['certainty'] in {'observed_syntax','observed_execution','version_binding','inferred','uncertain'}
        assert set(ad['unresolved_events'])<=set(labels)
        unresolved+=len(ad['unresolved_events']);coverage.update(k for k,v in ad['coverage'].items() if v)
        annotations[bid]={'labels':labels,'must_keep':set(ad['must_keep_failure_events']),'details':ad,'task':p['instance_id']}
        review_refs.extend([ref(f) for f in files]+[ref(path)])
    agree=agreement(pairs);agree['essential_Jaccard_mean_nonempty']=avg([r['Jaccard'] for r in jaccards]);agree['nonempty_essential_union_points']=sum(r['union']>0 for r in jaccards)
    agree['both_empty_essential_points']=sum(r['union']==0 for r in jaccards)
    dependencies={p['point']:dependency_coverage(p,annotations[p['point']]['details']) for p in mapping}
    rows=[]
    for r in comparison['rows']:
        annotation=annotations[r['point']];m=point_metrics(annotation['labels'],r['selected'],annotation['must_keep'])
        rows.append({**r,**m})
    groups=[]
    for name,budget in dict.fromkeys((r['condition'],r['budget']) for r in rows):
        rs=[r for r in rows if (r['condition'],r['budget'])==(name,budget)]
        by_task=defaultdict(list)
        for r in rs:by_task[r['instance_id']].append(r)
        task_values=[{'instance_id':task,'essential_recall':avg([r['essential_recall'] for r in rr]),
            'precision_lower':avg([r['evidence_precision_lower'] for r in rr]),'irrelevant_selected':sum(r['irrelevant_selected'] for r in rr),
            'input_tokens_estimate':sum(r['input_tokens_estimate'] for r in rr)} for task,rr in by_task.items()]
        groups.append({'condition':name,'budget':budget,'points':len(rs),'tasks':len(by_task),
            'macro_essential_recall':avg([r['essential_recall'] for r in rs]),
            'task_balanced_essential_recall':avg([r['essential_recall'] for r in task_values]),
            'essential_points':sum(r['essential_count']>0 for r in rs),
            'micro_essential_recall':ratio(sum(r['essential_selected'] for r in rs),sum(r['essential_count'] for r in rs)),
            'micro_evidence_precision_lower':ratio(sum(r['relevant_selected'] for r in rs),sum(r['selected_count'] for r in rs)),
            'micro_evidence_precision_upper':ratio(sum(r['relevant_selected']+r['uncertain_selected'] for r in rs),sum(r['selected_count'] for r in rs)),
            'essential_items':sum(r['essential_count'] for r in rs),'essential_selected':sum(r['essential_selected'] for r in rs),
            'irrelevant_selected':sum(r['irrelevant_selected'] for r in rs),'uncertain_selected':sum(r['uncertain_selected'] for r in rs),
            'critical_failure_recall':ratio(sum(r['critical_failures_selected'] for r in rs),sum(r['critical_failure_count'] for r in rs)),
            'input_tokens_estimate':sum(r['input_tokens_estimate'] for r in rs),'cards':sum(r['selected_count'] for r in rs),
            'task_summaries':task_values})
    g2=next(g for g in groups if g['condition']=='G2' and g['budget']==4096);g3=next(g for g in groups if g['condition']=='G3' and g['budget']==4096)
    recall_defined=g2['macro_essential_recall'] is not None and g3['macro_essential_recall'] is not None
    improves=recall_defined and (g3['macro_essential_recall']>g2['macro_essential_recall'] or
        (g3['macro_essential_recall']>=g2['macro_essential_recall'] and g3['irrelevant_selected']<g2['irrelevant_selected']))
    agreement_pass=(agree['essential_binary_cohen_kappa'] is not None and agree['essential_binary_cohen_kappa']>=.6 and
        agree['essential_Jaccard_mean_nonempty'] is not None and agree['essential_Jaccard_mean_nonempty']>=.6 and not unresolved)
    gate={'engineering':'PASS','double_blind_AI_annotation_complete':True,'annotation_agreement_gate':bool(agreement_pass),
        'scientific_G3_over_G2_gate':bool(improves),'true_model_experiment_launch':'HOLD',
        'annotation_type':'AI-assisted and correlated model-family reviewers; not human gold',
        'no_cash_or_model_experiment_requested_or_launched':True,
        'same_graph_and_method_fixed_before_annotation_results':True}
    save(dest/'summary.json',{'version':'v197-blind-AI-reference-event-selection-results-r1','agreement':agree,'Jaccards':jaccards,
        'coverage':dict(coverage),'coverage_targets':12,'disagreements':disagreements,'unresolved_events':unresolved,
        'agreed_label_source_error_overrides':corrections,'groups':groups,'rows':rows,'gate':gate,
        'label_distribution':dict(Counter(v for a in annotations.values() for v in a['labels'].values())),
        'dependency_path_diagnostics':dependencies,
        'annotation_sources':review_refs,'comparison':ref(OUT/'ablation-r1/summary.json'),
        'issue_citation_resolutions':citation_resolutions,
        'annotation_model_usage_tokens':None,'annotation_platform_cost_CNY':None,
        'annotation_cost_not_reported_as_zero':True,
        'metrics_scope':'default historical event-card selection conditional on unchanged recent window/actions; not comprehension or task success',
        'recoverable_original_information_same_for_all_conditions':True})
    print(json.dumps({'agreement':agree,'coverage':dict(coverage),'gate':gate},ensure_ascii=False))

if __name__=='__main__':main()
