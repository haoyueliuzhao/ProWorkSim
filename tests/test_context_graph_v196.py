import copy
import json
from pathlib import Path
import pytest
from proworksim.software_context_graph_v196 import ObservedWorkGraph,GraphIntegrityError,GraphScopeError
from proworksim.software_context_selection_v196 import project,RULES,PREFIX,candidates,baseline
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_context_critical_v191 import project as old_project


def version(n):return {'object_id':'workspace','version_id':'v'+str(n)}
def start():return [{'role':'system','content':'Keep permissions and original issue.'},{'role':'user','content':'Repair api.py using only observed code.'}]
def call(messages,name,args,result,*,cid=None,ok=True):
    cid=cid or 'call-'+str(len(messages))
    messages.extend([{'role':'assistant','tool_calls':[{'id':cid,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]},
        {'role':'tool','tool_call_id':cid,'content':json.dumps({'ok':ok,'result':result} if ok else {'ok':False,'error':result})}])
    return cid
def public_result(run,ver=1,passed=False,text=''):
    return {'report_id':run,'report_event':{'operation_id':'op-'+run},'source_reference':version(ver),
        'files_sha256':'files-'+str(ver),'executed':True,'passed':passed,
        'counts':{'failed':int(not passed),'passed':int(passed),'errors':0},
        'page':{'text':text},'text':'visible padding '*35}
def old_failed_prefix():
    ms=start()
    call(ms,'read_file',{'path':'parser.py'},{'path':'parser.py','source_reference':version(1),
        'text':'def parse(x):\n    return x\n','start_character':0,'end_character':27,'total_characters':27})
    call(ms,'run_tests',{'selection':{'kind':'pytest','targets':['tests/test_parser.py']}},
        public_result('r1',text='FAILED tests/test_parser.py::test_edge - ValueError: parser.py:2 invalid value'))
    call(ms,'read_test_result',{'report_id':'r1'},public_result('r1',text='ValueError: parser.py:2 invalid value'))
    for _ in range(6):
        call(ms,'read_file',{'path':'api.py'},{'path':'api.py','source_reference':version(1),
            'text':'from parser import parse\ndef api(x):\n    return parse(x)\n'+'# observed\n'*70})
    ms.append({'role':'user','content':json.dumps({'observation':{'workspace_reference':version(1)}})})
    return {'messages':ms,'tools':[]}
def build(payload,*,deps=True):return ObservedWorkGraph('episode','member_001',dependencies_enabled=deps).ingest(payload,step=0)
def view(payload,method='M1-5G',graph=None):
    graph=graph or build(payload);store=SourceLabeledHistoryReader('point','episode','member_001')
    out,proof=project(payload,method,graph,store,count=lambda s:(len(s)+3)//4,decision_step=0)
    return out,proof,store


def test_execution_and_read_are_one_run_with_actionable_diagnostics():
    payload=old_failed_prefix();graph=build(payload)
    runs=[n for n in graph.nodes.values() if n['type']=='TestRun'];assert len(runs)==1
    event=next(e for e in graph.events.values() if e['kind']=='test')
    assert {'failed_test','error_excerpt','declared_selection','reported_location'} <= {f['name'] for f in event['fields']}
    out,p,_=view(payload,'M1-5K-v2',graph)
    ids=[e['event_id'] for e in p['selected']];assert len(ids)==len(set(ids))
    assert sum(e['card']['kind']=='failed_test' for e in p['selected'])==1


def test_actual_rerun_and_new_version_remain_three_distinct_runs():
    payload=old_failed_prefix();ms=payload['messages']
    call(ms,'run_tests',{'selection':{'kind':'pytest','targets':['tests/test_parser.py']}},public_result('r2'))
    call(ms,'replace_file',{'path':'parser.py','old':'x','new':'x+1'},{'source_reference':version(2),'paths':['parser.py']})
    call(ms,'run_tests',{'selection':{'kind':'pytest','targets':['tests/test_parser.py']}},public_result('r3',2,True))
    graph=build(payload);assert len([n for n in graph.nodes.values() if n['type']=='TestRun'])==3
    assert len({e['id'] for e in graph.events.values() if e['kind']=='test'})==3


def test_old_report_read_never_reverts_current_version_or_validates_new_code():
    payload=old_failed_prefix();ms=payload['messages']
    call(ms,'replace_file',{'path':'parser.py','old':'return x','new':'return x+1'},{'source_reference':version(2),'paths':['parser.py']})
    call(ms,'read_test_result',{'report_id':'r1'},public_result('r1'))
    graph=build(payload);assert graph.nodes[graph.current_version]['attrs']['source_reference']==version(2)
    old=next(e for e in graph.events.values() if e['kind']=='test')
    assert graph.version_status(old)=='historical_version'
    assert all(e['target']!=graph.current_version for e in graph.edges.values() if e['type']=='validates')


def test_conflicting_report_identity_is_not_silently_merged():
    payload=old_failed_prefix();call(payload['messages'],'read_test_result',{'report_id':'r1'},public_result('r1',2))
    with pytest.raises(GraphIntegrityError):build(payload)


def test_incremental_repetition_is_idempotent_and_separate_scopes_have_separate_ids():
    p=old_failed_prefix();g=build(p);before=g.snapshot();g.ingest(p,step=0)
    assert before==g.snapshot()
    other=ObservedWorkGraph('other-episode','member_001').ingest(p,step=0)
    assert not set(g.nodes)&set(other.nodes)
    with pytest.raises(GraphScopeError):g.ingest(p,step=1,member='member_002')


def test_future_graph_falls_back_without_exposing_future_fields():
    p=old_failed_prefix();g=build(p);g.step=2
    out,proof,_=view(p,'M1-5G',g);expected,_,_=view(p,'M1-5')
    assert out==expected and proof['fallback']['method']=='M1-5'


def test_inferred_dependencies_cannot_be_promoted_to_confirmed():
    g=build(old_failed_prefix());a,b=list(g.nodes)[:2];sid=next(iter(g.sources))
    eid=g.hypothesis(a,b,[sid],'possible issue relationship');assert g.edges[eid]['status']=='Inferred'
    with pytest.raises(GraphIntegrityError):g.edge('depends_on',a,b,sources=[sid],status='Confirmed')


def test_confirmed_static_edges_are_syntax_not_runtime_coverage():
    g=build(old_failed_prefix())
    assert any(e['type']=='imports' and e['status']=='Confirmed' for e in g.edges.values())
    assert any(e['type']=='calls' and e['attrs']['semantics']=='call_expression_not_confirmed_runtime_dispatch' for e in g.edges.values())
    assert any(e['type']=='depends_on' and e['status']=='Inferred' for e in g.edges.values())


def test_nested_function_calls_do_not_become_outer_function_calls():
    ms=start();call(ms,'read_file',{'path':'nest.py'},{'path':'nest.py','source_reference':version(1),
        'text':'def outer():\n    def inner():\n        target()\n    return inner\n'})
    g=build({'messages':ms,'tools':[]})
    calls=[e for e in g.edges.values() if e['type']=='calls']
    assert len(calls)==1 and g.nodes[calls[0]['source']]['attrs']['symbol']=='inner'


def test_graph_uses_observed_dependency_to_find_related_old_failure():
    p=old_failed_prefix();g=build(p);out,proof,_=view(p,graph=g)
    selected=[x for x in proof['selected'] if x['card']['kind']=='failed_test']
    assert selected and any(x['rank_reason']['dependency_path'] for x in selected)
    store=SourceLabeledHistoryReader('point','episode','member_001')
    _,without=project(p,'M1-5G',g,store,count=lambda s:(len(s)+3)//4,decision_step=0,dependency_edges=False)
    assert not any(x['card']['kind']=='failed_test' for x in without['selected'])


def test_unrelated_historical_failure_is_excluded_from_local_view():
    p=old_failed_prefix();g=build(p)
    failed=next(e for e in g.events.values() if e['kind']=='test');failed['paths']=['unrelated.py']
    g._file('unrelated.py',failed['sources'][0]);failed['version']=g._version(version(0),None,failed['sources'][0])
    # Remove the observed paths for this test node; do not fabricate new edges.
    g.edges={k:e for k,e in g.edges.items() if e['source']!=failed['node'] and e['target']!=failed['node']}
    _,proof,_=view(p,graph=g)
    assert failed['id'] not in {x['event_id'] for x in proof['selected']}


def test_equal_candidate_pool_and_upper_budget_for_flat_and_graph_selection():
    p=old_failed_prefix();plain=build(p,deps=False);graph=build(p)
    _,a,_=view(p,'M1-5K-v2',plain);_,b,_=view(p,'M1-5G',graph)
    assert a['candidate_pool_sha256']==b['candidate_pool_sha256']
    assert a['rules']==b['rules']
    assert all(x['added_content_tokens_local_estimate']<=4096 and len(x['selected'])<=8 for x in (a,b))


def test_baseline_matches_frozen_window_and_preserves_actions_recent_history():
    p=old_failed_prefix();store=SourceLabeledHistoryReader('point','episode','member_001')
    expected,_=old_project(p,'M1-5',store,count=lambda s:(len(s)+3)//4)
    got,_,_=view(p,'M1-5');assert got==expected
    out,_,_=view(p,'M1-5G')
    assert out['messages'][:2]==p['messages'][:2] and out['messages'][-11:]==p['messages'][-11:]
    assert [m for m in out['messages'] if m['role']=='assistant']==[m for m in p['messages'] if m['role']=='assistant']


def test_exact_original_recovery_and_cross_member_denial():
    p=old_failed_prefix();_,proof,store=view(p)
    original={i:m for i,m in enumerate(p['messages'])}
    for item in proof['masked']:
        pieces=[];start=0
        while True:
            r=store.read({'reference':item['reference'],'start':start,'characters':200},point_id='point',slot_id='episode',member_id='member_001')
            pieces.append(r['text'])
            if r['next_start'] is None:break
            start=r['next_start']
        assert ''.join(pieces)==original[item['index']]['content']
    with pytest.raises(PermissionError):store.read({'reference':proof['masked'][0]['reference']},point_id='point',slot_id='episode',member_id='member_002')


def test_corrupt_graph_or_tampered_fact_falls_back_to_original_masked_view():
    p=old_failed_prefix();g=build(p);key=next(iter(g.edges));g.edges[key]['target']='missing'
    got,proof,_=view(p,graph=g);base,_,_=view(p,'M1-5')
    assert got==base and proof['fallback']
    g=build(p);e=next(e for e in g.events.values() if e['kind']=='test')
    e['fields'][0]['value']='fabricated'
    got,proof,_=view(p,'M1-5K-v2',g);assert got==base and proof['fallback']


def test_small_budget_returns_indices_without_shortening_recent_window(monkeypatch):
    p=old_failed_prefix();monkeypatch.setitem(RULES,'added_content_tokens',1)
    got,proof,_=view(p);base,_,_=view(p,'M1-5')
    assert got==base and not proof['selected']


def test_no_filesystem_or_hidden_world_access_and_determinism(monkeypatch):
    monkeypatch.setattr(Path,'read_bytes',lambda *_:pytest.fail('Unobserved source access'))
    p=old_failed_prefix();a,pa,_=view(p);b,pb,_=view(p)
    assert a==b and pa==pb


def test_independent_checker_accepts_sources_and_rejects_forged_evidence():
    from proworksim.software_context_graph_check_v196 import verify_graph,verify_view,sha
    p=old_failed_prefix();g=build(p);snapshot=g.snapshot()
    witnesses={(i,sha(m)) for i,m in enumerate(p['messages'])}
    kwargs=dict(episode='episode',member='member_001',step=0,witnesses=witnesses)
    assert verify_graph(snapshot,**kwargs)['test_runs']==1
    out,proof,store=view(p,graph=g)
    verify_view(p,out,proof,snapshot,store,count=lambda s:(len(s)+3)//4,indices=list(range(len(p['messages']))))
    with pytest.raises(AssertionError):verify_graph(snapshot,**dict(kwargs,witnesses=set()))
    bad=copy.deepcopy(snapshot);next(iter(bad['events'].values()))['fields'][0]['value']='forged'
    with pytest.raises(AssertionError):verify_graph(bad,**kwargs)
    bad=copy.deepcopy(snapshot)
    inferred=next(e for e in bad['edges'].values() if e['status']=='Inferred');inferred['status']='Confirmed'
    with pytest.raises(AssertionError):verify_graph(bad,**kwargs)


def test_incremental_new_projection_of_old_observation_cannot_revert_version():
    p=old_failed_prefix();g=build(p)
    call(p['messages'],'replace_file',{'path':'parser.py','old':'x','new':'x+1'}, {'source_reference':version(2),'paths':['parser.py']})
    g.ingest(p,step=1)
    p['messages'][-3]['content']=json.dumps({'observation':{'workspace_reference':version(1),'newly_projected_old_fact':True}})
    g.ingest(p,step=2)
    assert g.nodes[g.current_version]['attrs']['source_reference']==version(2)


def test_old_static_edges_are_preserved_but_not_used_for_current_dependency_query():
    from proworksim.software_context_selection_v196 import distances
    p=old_failed_prefix();g=build(p)
    old_edges=set(g.edges)
    call(p['messages'],'replace_file',{'path':'api.py','old':'parse(x)','new':'x'}, {'source_reference':version(2),'paths':['api.py']})
    g.ingest(p,step=1)
    assert old_edges<=set(g.edges)
    _,reachable=distances(g)
    assert g._file_nodes['parser.py'] not in reachable


def test_escaped_public_report_paths_and_sympy_failure_names_are_exact():
    ms=start();call(ms,'run_tests',{'selection':{'kind':'sympy','targets':['sympy/core/tests/test_expr.py']}},
        public_result('sympy-r1',text=r'Warning\n/testbed/sympy/core/basic.py:3: warning\n____ sympy/core/tests/test_expr.py:test_relational ____\n  File \"/testbed/sympy/core/expr.py\", line 320, in test_relational'))
    g=build({'messages':ms,'tools':[]});event=next(iter(g.events.values()))
    assert 'sympy/core/tests/test_expr.py:test_relational' in [f['value'] for f in event['fields'] if f['name']=='failed_test']
    assert 'sympy/core/basic.py' in event['paths'] and 'sympy/core/expr.py' in event['paths']
    assert not any(p.startswith('n/testbed/') or '.py:test_' in p for p in event['paths'])


def test_failed_incremental_index_update_serves_M15_without_stopping_or_cross_scope_access():
    from proworksim.software_context_selection_v196 import update_and_project
    p=old_failed_prefix();g=build(p)
    call(p['messages'],'read_test_result',{'report_id':'r1'},public_result('r1',2))
    store=SourceLabeledHistoryReader('point','episode','member_001')
    out,proof=update_and_project(p,'M1-5G',g,store,step=1,count=lambda s:(len(s)+3)//4)
    expected,_,_=baseline(p,SourceLabeledHistoryReader('point','episode','member_001'),lambda s:(len(s)+3)//4,list(range(len(p['messages']))))
    assert out==expected and proof['fallback']['phase']=='graph_update'
    assert g.disabled_after_integrity_error
    with pytest.raises(GraphScopeError):update_and_project(p,'M1-5G',g,SourceLabeledHistoryReader('point','other','member_001'),step=2,count=len)
