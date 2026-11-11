"""Prepare blinded decision-prefix material; no scores or variant outputs."""
from __future__ import annotations
import copy,gzip,hashlib,json,re
from pathlib import Path
from collections import Counter
from proworksim.software_context_compression_v175 import digest,canonical
from proworksim.software_context_selection_v196 import candidates
from proworksim.software_context_graph_v196 import ObservedWorkGraph

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v197'
RUN=ROOT/'runs/software-benchmark-v197'
BLIND=RUN/'blind-material-r1'
AUDIT=Path('/home/zhuxinrui/.codex/attachments/bdbbbe27-4c64-4d5a-98a8-730f873303a4/已粘贴的文本.txt')

def read(p):
    p=Path(p);raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
def ref(p):
    p=Path(p);raw=p.read_bytes();return {'path':str(p.resolve()),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);raw=(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
    if p.suffix=='.gz':raw=gzip.compress(raw,mtime=0)
    p.write_bytes(raw);return ref(p)
def graph_from_snapshot(s):
    g=ObservedWorkGraph(*s['scope']);g.nodes=copy.deepcopy(s['nodes']);g.edges=copy.deepcopy(s['edges']);g.sources=copy.deepcopy(s['sources']);g.events=copy.deepcopy(s['events']);g.current_version=s['current_version'];g.step=s['step']
    g._file_nodes={n['attrs']['path']:nid for nid,n in g.nodes.items() if n['type']=='Code' and n['attrs'].get('entity_kind')=='file'}
    g.focus=lambda:copy.deepcopy(s['focus'])
    return g
def frame_for(point):
    """Restore from the already source-verified v196 M15 view and exact store."""
    folder=ROOT/'runs/software-benchmark-v196/offline-graph-r4'/point['point_id']
    frame=read(folder/'M1-5/payload.json.gz');proof=read(folder/'M1-5/proof.json.gz');store=read(folder/'M1-5/original-evidence.json.gz')
    for m in proof['masked']:
        entry=store[m['reference']];assert entry['message_index']==m['original_index']
        frame['messages'][m['index']]['content']=entry['text'];assert digest(frame['messages'][m['index']])==m['source_sha256']
    projection=read(point['projection']['path']);indices=projection['selected_indices']
    s=read(folder/'graph.json.gz');g=graph_from_snapshot(s)
    tools=[i for i,m in enumerate(frame['messages']) if m['role']=='tool'];cutoff=tools[-5] if len(tools)>5 else 0
    pool=candidates(g,proof['masked'],indices,cutoff)
    return frame,indices,s,pool,cutoff
def parse(value):
    try:return json.loads(value)
    except (ValueError,TypeError):return {}
def text_brief(message):
    b=parse(message.get('content'));o=b.get('observation') if isinstance(b,dict) else None
    if isinstance(o,dict):
        keys=['workspace_reference','logical_time','current_version_test_coverage','delivery_status','tasks','personal_workbench']
        return {'role':message['role'],'observation_state':{k:o[k] for k in keys if k in o}}
    return message

def main():
    if (OUT/'protocol-r1/plan.json').exists():raise ValueError('Protocol already frozen')
    plan={'version':'v197-blinded-dependency-factorial-P0-r1','audit':ref(AUDIT),
        'stage':'offline annotations, query ablation, engineering replay controls; no tested-model API',
        'annotation_reviewers':2,'review_type':'independent isolated Codex AI reviews, not human gold standard',
        'adjudication':'third isolated reviewer, receives disagreements and visible prefixes only',
        'blinding':'no final score, future response, selector result, graph edges, weights or experimental labels',
        'labels':['essential','useful','irrelevant','uncertain'],
        'essential_definition':'old evidence necessary to make the next defensible decision given the task and recent visible state, not already supplied by recent messages or retained actions',
        'quality_budget_levels':[1024,2048,4096],'primary_budget':4096,'max_cards':8,'max_card_tokens':768,
        'max_input_tokens':98304,'recent_tool_cycles':5,'reserve_tokens':'remaining input capacity; no new dynamic budget learner',
        'conditions':{'G0':'M15 baseline','G1':'K-v2 type and time','G2':'path focus and version validity, no edges',
            'G3':'same roots with type-conditioned Confirmed relations','G4':'same query plus explicitly Inferred relations'},
        'primary_query':'same recent-action roots G2/G3/G4; state-specific relation paths; no identity or permission changes',
        'task_retrieval_diagnostic':'common optional issue/symptom literal-name retrieval over already observed entities, reported separately, not mixed into primary G0-G4',
        'query_path_rules':{'code':['contains,calls','imports,depends_on','contains,calls,depends_on','contains,calls,depends_on,calls'],
            'test':['tests','tests,contains','tests,contains,calls','contains','imports,depends_on'],
            'version':['modifies','derived_from','tests'],'locate':['contains','imports,depends_on','contains,calls']},
        'edge_policy':'typed path language, scoped static syntax vs execution vs version vs inferred; no undifferentiated all-edge BFS',
        'ordering':'v196 direct/current/failure scores frozen; relation category has explicit weight; stronger proven paths before inferred paths at equal relevance',
        'annotation_agreement_gate':{'essential_binary_cohen_kappa_min':0.60,'essential_Jaccard_mean_nonempty_min':0.60,
            'unresolved_essential_disagreements_max':0,'all48_double_review_required':True},
        'scientific_gate':'G3 over G2: higher macro essential recall, or nonlower recall with fewer irrelevant selections, at primary4096; report task-cluster effects; no claim of statistical confirmation',
        'evidence_gate':'zero future/private-scope/false-current-validation errors; Inferred never Confirmed',
        'coverage_targets':{'cross_file':12,'failure_and_change':12,'version_change':12},'coverage_shortfalls_do_not_trigger_task_replacement':True,
        'cost_gate':'all maintenance/query/serialization and local-token estimates reported; CPU and tokens not falsely added in common units',
        'new_tested_model_calls':0,'new_API_budget_CNY':0,'old_cash_reallocated':False,'new_Docker_objects':0,
        'future_real_model_stage':'only after gate and new explicit budget; no84-run authorization inferred'}
    save(OUT/'protocol-r1/plan.json',plan)
    manifest=read(ROOT/'artifacts/software-benchmark-v196/fixed-points-r1/manifest.json');mapping=[];inventory=[]
    for n,point in enumerate(manifest['points'],1):
        bid=f'P{n:03d}';frame,indices,s,pool,cutoff=frame_for(point)
        assert all(v['first_seen_step']<=point['decision_step'] for v in s['sources'].values())
        events=sorted(pool,key=lambda e:(e['last_index'],e['event_id']));event_map={e['event_id']:f'E{i+1:03d}' for i,e in enumerate(events)}
        source_rows=[]
        for i,m in zip(indices,frame['messages']):source_rows.append({'message_index':i,'message':m})
        # Remove administrative labels only. Code and test content are retained.
        serialized=json.dumps(source_rows,ensure_ascii=False)
        for h in manifest['histories']:serialized=serialized.replace(h['slot_id'],'BLINDED_EPISODE')
        serialized=re.sub(r'DEEPSEEK_NT_S1_M1_(?:5K|10|5)_V193_B5000K','BLINDED_CONDITION',serialized)
        source_rows=json.loads(serialized)
        issue='';roles=''
        for source in sorted(s['sources'].values(),key=lambda z:z['first_seen_step']):
            b=parse(source['message'].get('content'));o=b.get('observation',{}) if isinstance(b,dict) else {}
            if o.get('root_goal',{}).get('description'):
                issue=o['root_goal']['description'];roles=b.get('role_task','');break
        current=s['nodes'][s['current_version']]['attrs']['source_reference'] if s['current_version'] else None
        catalog=[]
        for e in events:
            fields=[{'name':f['name'],'value':f['value'],'message_index':s['sources'][f['origin']['source_id']]['message_index']} for f in e['fields']]
            previews=[]
            for sid in e['sources'][:2]:
                source=s['sources'][sid];m=source['message'];b=parse(m.get('content'));r=b.get('result',{}) if isinstance(b,dict) else {}
                text=r.get('text') or (r.get('page') or {}).get('text') or ''
                if text:previews.append({'message_index':source['message_index'],'excerpt':text[:1000],'truncated':len(text)>1000})
            catalog.append({'id':event_map[e['event_id']],'kind':e['kind'],'paths':e['paths'],'version_status':e['version_status'],
                'source_version':s['nodes'][e['version']]['attrs']['source_reference'] if e['version'] else None,
                'source_message_indices':sorted({s['sources'][sid]['message_index'] for sid in e['sources']}),
                'facts':fields,'previews':previews})
        recent=[{'message_index':i,'message':text_brief(m)} for i,m in zip(indices[cutoff:],frame['messages'][cutoff:])]
        full=save(BLIND/bid/'visible-prefix.json.gz',{'point':bid,'source_messages':source_rows})
        # Manifest delivered to reviewers has no original identifiers or result paths.
        brief={'point':bid,'issue':issue,'task_and_delivery_rules':roles,'current_version':current,
            'common_recent_window':recent,'historical_candidates':catalog,
            'full_prefix_file':'visible-prefix.json.gz','instructions':'Read only this or earlier decision material. Mark each old candidate, cite message indices. Do not infer necessity from eventual outcomes. Empty essential set is legitimate.'}
        save(BLIND/bid/'brief.json',brief)
        mapping.append({'point':bid,**point,'event_map':event_map,'blind_full':full,'blind_brief':ref(BLIND/bid/'brief.json')})
        inventory.append({'point':bid,'candidates':len(catalog),'brief_bytes':(BLIND/bid/'brief.json').stat().st_size,
            'observed_versions':sum(v['type']=='Version' for v in s['nodes'].values()),
            'has_failure_and_change':any(e['kind']=='failed_test' for e in pool) and any(e['kind']=='change' for e in pool)})
    save(OUT/'private-map-r1/manifest.json',{'original_points':ref(ROOT/'artifacts/software-benchmark-v196/fixed-points-r1/manifest.json'),'points':mapping})
    save(OUT/'coverage-before-labels-r1/inventory.json',inventory)
    instructions='''# Blinded evidence review instructions

You are one independent AI reviewer. This is an AI-assisted reference set, not human gold truth. Only read this folder and your own output directory. Do not read project reports, graph or selector implementation, experimental results, another reviewer, final scores, task solutions, git history or the Internet. These are deliberately hidden. The root task requires two independent reviewers and an adjudicator.

Review P001..P048 sequentially. Each contains only information visible by that decision. Finish and save a point before opening later points; do not revise earlier annotations after seeing later evidence. Read brief.json; consult visible-prefix.json.gz when excerpts are insufficient. Candidate fields are source facts, not selector rankings. Recent observations and all assistant actions remain available in every view. Do not label an old card essential merely because its file is important if the needed fact is already in the recent window or retained action text. You may label no old candidate essential.

For every candidate choose essential/useful/irrelevant/uncertain. Essential means necessary for the next defensible decision with currently visible information, not hindsight success. Useful is relevant but dispensable. Keep uncertainty for unclear evidence. For each point provide a concise current-decision explanation, necessary code entities, old evidence labels with source message citations, critical failed-test evidence, and direct/indirect dependency judgments. Dependencies must cite exact source messages; distinguish static literal syntax, executed relationship, version binding, and inference. Do not turn a reported path into runtime coverage. Unknown dependencies must remain unknown. Record missing evidence rather than inventing it. All raw candidate facts can be recovered; recoverable alone does not make them unnecessary.

Save one JSON file per point in your own output folder with exclusive creation. Schema:
{"point":"P001","reviewer":"A or B","review_type":"AI_blind","decision":"...","necessary_entities":["path"],"labels":[{"event":"E001","label":"essential|useful|irrelevant|uncertain","reason":"...","source_messages":[12]}],"dependencies":[{"from":"path/entity","to":"path/entity","relation":"import|call|test|version|other","necessary":true,"certainty":"observed_syntax|observed_execution|version_binding|inferred|uncertain","source_messages":[12],"reason":"..."}],"must_keep_failure_events":["E003"],"missing_evidence":[],"coverage":{"cross_file":false,"failure_and_change":false,"version_change":false},"confidence":"high|medium|low"}

Read and reason independently; do not auto-label by keyword or a selector. For efficiency, use concise reasons and inspect each task in sequential prefixes. Do not start tools that execute code from the benchmark, containers, API calls or tests; only ordinary reads and writing your annotations. Do not commit/push; root manages the final report. Report progress every 12 points to root without discussing method performance.
'''
    (BLIND/'REVIEW.md').write_text(instructions)
    save(BLIND/'manifest.json',{'points':[r['point'] for r in mapping],'point_count':48,'protocol':'REVIEW.md'})
    print('prepared48; candidate counts',sum(x['candidates'] for x in inventory),'brief bytes',sum(x['brief_bytes'] for x in inventory))

if __name__=='__main__':main()
