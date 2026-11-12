#!/usr/bin/env python3
"""Frozen offline syntax/graph experiments. No model, shell execution or Docker."""
import argparse,copy,datetime,json,os,resource,sys,time,traceback,multiprocessing
from collections import Counter
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from project_graph_materials_v202 import ROOT,read,save,ref,syntax_cases,synthetic_stream,historical_stream,event,ref_version,obj
from proworksim.software_syntax_facts_v202 import SyntaxFacts,document,sha
from proworksim.software_project_graph_v202 import ProjectGraph
from proworksim.software_organization_mapping_v202 import OrganizationMapping

ART=ROOT/'artifacts/software-benchmark-v202'
RUN=ROOT/'runs/software-benchmark-v202'
METHODS=('A0','A1','A2','A3')
MODES=('PG0','PG1','PG2','PG3')
SOURCES=['src/proworksim/software_syntax_facts_v202.py','src/proworksim/software_project_graph_v202.py','src/proworksim/software_organization_mapping_v202.py',
    'tools/project_graph_materials_v202.py','tools/run_project_graph_v202.py','tests/test_project_graph_v202.py',
    'src/proworksim/software_fact_context_v199.py','src/proworksim/software_fact_budget_v200.py','src/proworksim/software_context_graph_v196.py','tools/prepare_dependency_audit_v197.py']

def freeze():
    target=ART/'source-freeze-r1/manifest.json'
    if target.exists():raise RuntimeError('Already frozen; use a distinct revision, never overwrite')
    admission=read('artifacts/software-benchmark-v201/source-admission-r1/summary.json');points={}
    for p in admission['points']:
        if p['slot_id'] not in points or p['decision_index']>points[p['slot_id']]['decision_index']:points[p['slot_id']]=p
    streams=[synthetic_stream()]+[historical_stream(p) for p in points.values()]
    streamrefs=[]
    for i,s in enumerate(streams):
        path=RUN/f'materials-r1/stream-{i:02}.json.gz';save(path,s);streamrefs.append(ref(path))
    cases=syntax_cases();save(RUN/'materials-r1/syntax-cases.json.gz',cases)
    annotation=read('artifacts/software-benchmark-v201/annotations-r1/H11-1.json')['reference_facts'][1]
    point=next(p for p in admission['points'] if p['point']=='H11-1');g=read(point['graph']['path']);origin=annotation['origins'][0];source=g['sources'][origin['source_id']]
    r=obj(source['message']['content'])['result'];text=r['text'];assert text[origin['span'][0]:origin['span'][1]]==annotation['value']
    d=document(text,scope=[point['slot_id'],'member_001'],path=r['path'],version=r['source_reference'],source_id=source['id'],complete=False,
        evidence=[{'source_message_sha256':source['message_sha256'],'file_character_start':r.get('start_character'),'source_scope':'known_v201_development_regression'}])
    regression={'document':d,'reference':annotation,'source_graph':ref(point['graph']['path'])};save(RUN/'materials-r1/known-regression.json.gz',regression)
    files=[]
    for path in SOURCES:
        p=ROOT/path;dst=ART/'source-freeze-r1/sources'/path;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(p.read_bytes());files.append(ref(p))
    save(target,{'frozen_at_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'protocol':ref(ART/'protocol-r1/plan.json'),
        'files':files,'streams':streamrefs,'cases':ref(RUN/'materials-r1/syntax-cases.json.gz'),'regression':ref(RUN/'materials-r1/known-regression.json.gz'),
        'historical_inputs':[{'point':p['point'],'decision_index':p['decision_index'],'graph':ref(p['graph']['path'])} for p in points.values()],
        'old_F1_source_sha256':ref(ROOT/'src/proworksim/software_fact_budget_v200.py')['sha256'],
        'no_future_outputs_or_official_scores_read':True,'new_API_calls':0,'selection':'latest already-opened point per historical task, fixed before outcome measurement',
        'org_controls':['cross_owner_dependency','explicit_handoff_supresses_duplicate','ordinary_change_no_reassignment','blocked_bottleneck','unsafe_new_owner','merge_requires_total_ownership','private_no_route','published_scoped_route']})
    return read(target)

def assert_frozen(manifest):
    for f in manifest['files']:
        if ref(f['path'])['sha256']!=f['sha256']:raise RuntimeError('Measured source changed: '+f['path'])
    for f in manifest['streams']+[manifest['cases'],manifest['regression']]:
        if ref(f['path'])['sha256']!=f['sha256']:raise RuntimeError('Frozen input changed')

def syntax_trial(item):
    label,d,expected=item;s=SyntaxFacts();rows=[];allfacts=[]
    for method in METHODS:
        start=time.perf_counter();r=s.extract(d,method);facts=r['facts'];raw=d['text'].encode();violations=[]
        for f in facts:
            if raw[f['start_byte']:f['end_byte']].decode()!=f['value'] or f['source_hash']!=d['source_hash'] or f['version_id']!=d['version'] or f['scope']!=d['scope']:violations.append(f['fact_id'])
        complete_claims=sum(f['completeness']=='complete' for f in facts)
        exact=cover=None
        if expected:
            a,z=expected;exact=any(f['start_byte']==a and f['end_byte']==z for f in facts);cover=any(f['start_byte']<=a and f['end_byte']>=z for f in facts)
        rows.append({'case':label,'method':method,'facts':len(facts),'span_and_source_violations':violations,'exact_target_span':exact,'target_contained_in_one_fact':cover,
            'full_completeness_claims':complete_claims,'source_complete':d['complete'],'parse_diagnostics':r['diagnostics'],
            'CPU_seconds':r['CPU_seconds'],'wall_seconds':time.perf_counter()-start,'peak_worker_RSS_MiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024})
        allfacts.append(r)
    return label,rows,allfacts

def syntax_experiment(manifest,out):
    cases=read(manifest['cases']['path']);items=[('control:'+c['id'],c['document'],c['expected_span']) for c in cases]
    distinct={}
    for s in manifest['streams'][1:]:
        for d in read(s['path'])['documents']:distinct.setdefault(sha([d['scope'],d['path'],d['version'],d['source_hash'],d['complete']]),d)
    items.extend(('history:'+k,d,None) for k,d in distinct.items())
    reg=read(manifest['regression']['path']);d=reg['document'];text=d['text'];needle='is_type_annotation_import = (';a=text.index(needle);z=text.index('\n                )',a)+len('\n                )')
    target=[len(text[:a].encode()),len(text[:z].encode())];items.append(('known_pylint_regression',d,target))
    rows=[];regfacts=None
    with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('fork')) as pool:
        for label,r,facts in pool.map(syntax_trial,items,chunksize=1):
            rows+=r
            save(RUN/out.name/'syntax'/f'{sha(label)[:20]}.json.gz',{'label':label,'results':facts})
            if label=='known_pylint_regression':regfacts=facts
    save(out/'syntax-trials.json',rows)
    summary={}
    for m in METHODS:
        control=[r for r in rows if r['method']==m and r['case'].startswith('control:')];full=[r for r in control if r['exact_target_span'] is not None];partial=[r for r in control if not r['source_complete']]
        allr=[r for r in rows if r['method']==m]
        summary[m]={'control_full_target_exact':sum(r['exact_target_span'] for r in full),'control_full_target_contained':sum(r['target_contained_in_one_fact'] for r in full),'control_full_denominator':len(full),
            'partial_no_false_full_claim':sum(not r['full_completeness_claims'] for r in partial),'partial_denominator':len(partial),
            'facts_emitted':sum(r['facts'] for r in allr),'span_or_source_violations':sum(len(r['span_and_source_violations']) for r in allr),
            'CPU_seconds':sum(r['CPU_seconds'] for r in allr),'maximum_worker_RSS_MiB':max(r['peak_worker_RSS_MiB'] for r in allr),
            'regression':[r for r in allr if r['case']=='known_pylint_regression'][0]}
    a2=next(r for r in regfacts if r['method']=='A2');branches=[f for f in a2['facts'] if f['value'] in ['imported_name in self._type_annotation_names','as_name in self._type_annotation_names']]
    save(out/'known-regression.json',{'original_reference':reg['reference'],'target_assignment':d['text'].encode()[target[0]:target[1]].decode(),
        'A2_assignment':[f for f in a2['facts'] if [f['start_byte'],f['end_byte']]==target],'A2_branches':branches,'source_is_partial':True,
        'known_development_regression_not_independent_validation':True})
    return {'conditions':summary,'synthetic_cases':len(cases),'historical_distinct_documents':len(distinct),'historical_complete_documents':sum(d['complete'] for d in distinct.values()),
        'historical_tasks':len(manifest['streams'])-1,'known_regression_branch_count':len(branches),'new_agent_retrievals':0,'new_task_or_token_outcomes_measured':False}

def edge_category(t):
    if t in {'validates_selected_scope','has_failure','executes_definition'}:return 'test_validation'
    if t in {'declared_task_dependency','addresses_issue'}:return 'task_dependency'
    if t in {'derived_from','adopts','submitted_version'}:return 'artifact_provenance'
    return 'code_structure_and_source'

def compare_graph(actual,reference):
    result={}
    for key in ('nodes','edges'):
        a,b=actual[key],reference[key];matching={i for i in a.keys()&b.keys() if a[i]==b[i]}
        result[key]={'reference_count':len(b),'actual_count':len(a),'matching':len(matching),'stale_or_extra':len(a)-len(matching),'missing_or_changed':len(b)-len(matching)}
    cats={}
    for key,e in reference['edges'].items():
        cat=edge_category(e['type']);c=cats.setdefault(cat,{'reference':0,'matching':0});c['reference']+=1;c['matching']+=actual['edges'].get(key)==e
    result['edge_categories']=cats;result['exact_graph_match']=actual==reference
    return result

def graph_trial(item):
    index,streamref,outname=item;stream=read(streamref['path']);graphs={m:ProjectGraph(**{k:stream[k] for k in ['scope','repo','commit','members']},mode=m) for m in MODES}
    measurements=[];errors=[];impact_scores=[];initial_snapshot_hashes={m:[] for m in MODES}
    for i,e in enumerate(stream['events']):
        steps={}
        for m,g in graphs.items():
            start=time.perf_counter()
            try:stats=g.apply(e)
            except Exception as exc:
                errors.append({'event_id':e['event_id'],'mode':m,'error':repr(exc),'traceback':traceback.format_exc()});raise
            stats['wall_seconds']=time.perf_counter()-start;steps[m]=stats;initial_snapshot_hashes[m].append(sha(g.snapshot))
        reference=graphs['PG1'].snapshot
        for m,g in graphs.items():measurements.append({'index':i,'event_id':e['event_id'],'event_kind':e['kind'],'mode':m,**steps[m],'comparison':compare_graph(g.snapshot,reference)})
        if e['event_id'] in stream.get('impact_oracles',{}):
            expected=set(stream['impact_oracles'][e['event_id']]);actual=set(steps['PG3']['impact']['potentially_affected']);tp=len(expected&actual)
            impact_scores.append({'event_id':e['event_id'],'expected':sorted(expected),'actual':sorted(actual),'precision':tp/len(actual) if actual else None,'recall':tp/len(expected)})
    summary={}
    for m,g in graphs.items():
        rows=[r for r in measurements if r['mode']==m];all_old_unchanged=initial_snapshot_hashes[m]==[sha(s) for s in g.snapshots]
        summary[m]={'events':len(rows),'exact_match_checkpoints':sum(r['comparison']['exact_graph_match'] for r in rows),'CPU_seconds':sum(r['CPU_seconds'] for r in rows),
            'wall_seconds':sum(r['wall_seconds'] for r in rows),'tree_parses':g.syntax.parses,'tree_incremental_parses':g.syntax.incremental_parses,
            'analysed_file_occurrences':sum(len(r['reanalysed_file_keys']) for r in rows),'all_old_snapshots_unchanged':all_old_unchanged,
            'final_node_types':dict(Counter(n['type'] for n in g.snapshot['nodes'].values())),
            'final_edge_types':dict(Counter(e['type'] for e in g.snapshot['edges'].values())),
            'final_complete_files':sum(d['complete'] for d in g.state['files'].values()),'final_unknown_files':sum(not d['complete'] for d in g.state['files'].values())}
        save(RUN/outname/f'graph-{index:02}-{m}.json.gz',{'events':g.events,'attempts':g.attempts,'final_state':g.state,'snapshots':g.snapshots})
    return {'stream_index':index,'scope':stream['scope'],'repo':stream['repo'],'source_point':stream.get('source_point'),'source_kind':'historical_wire' if index else 'synthetic_control',
        'event_types':dict(Counter(e['kind'] for e in stream['events'])),'conditions':summary,'checkpoints':measurements,'impact_control_scores':impact_scores,
        'historical_malformed_sources':stream.get('malformed_sources',[]),'execution_errors':errors,'peak_worker_RSS_MiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}

def graph_experiment(manifest,out):
    streams=[]
    with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('fork')) as pool:
        for result in pool.map(graph_trial,[(i,s,out.name) for i,s in enumerate(manifest['streams'])],chunksize=1):
            save(out/f'graph-stream-{result["stream_index"]:02}.json',result);streams.append(result)
    summary={}
    for kind in ['synthetic_control','historical_wire']:
        selected=[s for s in streams if s['source_kind']==kind];conditions={}
        for m in MODES:
            sums={k:sum(s['conditions'][m][k] for s in selected) for k in ['events','exact_match_checkpoints','CPU_seconds','wall_seconds','tree_parses','tree_incremental_parses','analysed_file_occurrences']}
            totals={k:Counter() for k in ('nodes','edges')};cats={}
            for s in selected:
                for r in s['checkpoints']:
                    if r['mode']!=m:continue
                    for k in totals:totals[k].update(r['comparison'][k])
                    for cat,v in r['comparison']['edge_categories'].items():cats.setdefault(cat,Counter()).update(v)
            sums.update(micro_structural_counts={k:dict(v) for k,v in totals.items()},edge_categories={k:dict(v) for k,v in cats.items()},
                all_snapshots_unchanged=all(s['conditions'][m]['all_old_snapshots_unchanged'] for s in selected));conditions[m]=sums
        summary[kind]={'streams':len(selected),'conditions':conditions,'errors':sum(len(s['execution_errors']) for s in selected),
            'malformed_input_observations':sum(len(s['historical_malformed_sources']) for s in selected),'peak_worker_RSS_MiB':max(s['peak_worker_RSS_MiB'] for s in selected)}
    summary['controlled_impact']=[r for s in streams for r in s['impact_control_scores']]
    return summary

def organization_controls(out):
    st=synthetic_stream();g=ProjectGraph(**{k:st[k] for k in ['scope','repo','commit','members']},mode='PG3')
    members={m:{'live':True,'tools':['replace_file','run_tests','submit_integration']} for m in st['members']}
    o=OrganizationMapping(members=members,regions={'TA':['pkg/core.py'],'TB':['pkg/client.py'],'TC':['tests/test_client.py']},owners={'TA':st['members'][0],'TB':st['members'][1],'TC':st['members'][1]})
    for e in st['events'][:12]:stats=g.apply(e)
    initial=o.snapshot();candidates=o.proposals(g);results=[{'case':'cross_owner_dependency','pass':len(candidates)==2 and all(p['operation']=='AddHandoff' and p['validation']['valid'] for p in candidates),'candidates':candidates}]
    results.append({'case':'ordinary_change_no_reassignment','pass':not any(p['operation']=='Reassign' for p in candidates) and o.snapshot()==initial})
    o.handoffs.update([('TA','TB'),('TA','TC')]);results.append({'case':'explicit_handoff_supresses_duplicate','pass':not o.proposals(g)})
    for i in range(3):g.apply(event('blocked'+str(i),'task','member_001',{**g.state['tasks']['TA'],'status':'blocked'}))
    candidates=o.proposals(g);results.append({'case':'blocked_bottleneck','pass':len(candidates)==1 and candidates[0]['operation']=='Reassign','candidates':candidates})
    o.members['member_002']['tools']=[];results.append({'case':'unsafe_new_owner','pass':not o.proposals(g)[0]['validation']['valid']})
    results.append({'case':'merge_requires_total_ownership','pass':not o.validate({'operation':'Merge','task_ids':['TA','TB']},g.state['tasks'])['valid']})
    f={'fact_id':'fixture-fact','owner':'member_001','source_ids':['write:interface'],'version':ref_version('member_001',2)}
    private=o.synchronization_plan(g,stats['impact'],[f]);results.append({'case':'private_no_route','pass':not next(p for p in private['routes'] if p['recipient']=='member_002')['facts'],'plan':private})
    f.update(published_to=['member_002'],publication_receipt='fixture-explicit-share');published=o.synchronization_plan(g,stats['impact'],[f]);results.append({'case':'published_scoped_route',
        'pass':bool(next(p for p in published['routes'] if p['recipient']=='member_002')['facts']) and published['transport_calls']==0,'plan':published})
    save(out/'organization-controls.json',results);return {'controls':len(results),'passed':sum(r['pass'] for r in results),'live_mutations':0,'actual_messages_or_model_calls':0,
        'policy_optimization_or_team_outcome_experiment':False}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--freeze',action='store_true');ap.add_argument('--run',action='store_true');ap.add_argument('--revision',default='r2',choices=['r1','r2']);args=ap.parse_args()
    if args.freeze:print(json.dumps({'manifest':ref(ART/'source-freeze-r1/manifest.json')} if (ART/'source-freeze-r1/manifest.json').exists() else {'streams':len(freeze()['streams'])}));return
    if not args.run:ap.error('choose --freeze or --run')
    manifest_path=ART/f'source-freeze-{args.revision}/manifest.json';manifest=read(manifest_path);assert_frozen(manifest);out=ART/f'offline-results-{args.revision}'
    if out.exists():raise RuntimeError('Refusing to overwrite measured results')
    out.mkdir();started=time.perf_counter()
    try:
        a=syntax_experiment(manifest,out);save(out/'syntax-summary.json',a);print('Syntax experiment completed',flush=True)
        b=graph_experiment(manifest,out);save(out/'graph-summary.json',b);print('Graph experiment completed',flush=True)
        org=organization_controls(out)
        save(out/'summary.json',{'syntax':a,'graph':b,'organization':org,'manifest':ref(manifest_path),
            'total_wall_seconds':time.perf_counter()-started,'new_model_API_requests':0,'new_model_input_output_tokens':0,'new_API_cash_CNY':0,
            'Codex_review_cost':'not separately measurable; not claimed zero','new_Docker_GPU_shared_host_changes':0})
        print('Completed',flush=True)
    except Exception:
        save(out/'execution-error.json',{'traceback':traceback.format_exc(),'wall_seconds':time.perf_counter()-started});raise

if __name__=='__main__':main()
