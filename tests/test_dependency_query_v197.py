import copy,json
import pytest
from test_context_graph_v196 import old_failed_prefix,build,call,public_result,version
from proworksim.software_dependency_query_v197 import project,typed_routes,state,task_roots
from proworksim.software_context_selection_v196 import project as previous
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_context_graph_v196 import GraphScopeError

def count(s):return (len(s)+3)//4
def run(p,g,c='G3',budget=4096,**kw):
    store=SourceLabeledHistoryReader('point','episode','member_001')
    return project(p,c,g,store,count=count,measure=lambda v:count(json.dumps(v)),indices=list(range(len(p['messages']))),budget=budget,**kw)

def test_five_conditions_have_identical_candidate_pool_and_bounded_same_renderer():
    p=old_failed_prefix();g=build(p);proofs=[run(p,g,c)[1] for c in ('G0','G1','G2','G3','G4')]
    assert len({r['candidate_pool_sha256'] for r in proofs})==1
    assert all(len(r['selected'])<=8 and r['added_content_tokens_local_estimate']<=4096 for r in proofs)
    for budget in [1024,2048]:
        assert run(p,g,'G4',budget)[1]['added_content_tokens_local_estimate']<=budget

def test_confirmed_and_inferred_queries_do_not_share_unverified_resolution():
    g=build(old_failed_prefix())
    _,confirmed,_=typed_routes(g,'code',inferred=False)
    _,inferred,_=typed_routes(g,'code',inferred=True)
    assert g._file_nodes['parser.py'] not in confirmed
    assert inferred[g._file_nodes['parser.py']]['inferred_edges']==1
    assert all(g.edges[e]['status']=='Confirmed' for r in confirmed.values() for e in r['edges'])

def test_typed_code_and_test_queries_are_not_one_untyped_bfs():
    p=old_failed_prefix();g=build(p)
    _,code,_=typed_routes(g,'code');_,tests,_=typed_routes(g,'test')
    assert code!=tests
    assert any(r['types']==['contains','calls'] for r in code.values())
    assert state(p)=='code'
    call(p['messages'],'run_tests',{'selection':{'kind':'pytest','targets':['tests/test_parser.py']}},public_result('r2'))
    assert state(p)=='test'

def test_stale_edges_not_followed_even_when_query_has_high_weight():
    p=old_failed_prefix();g=build(p)
    call(p['messages'],'replace_file',{'path':'api.py','old':'parse(x)','new':'x'},{'source_reference':version(2),'paths':['api.py']})
    g.ingest(p,step=1)
    _,routes,info=typed_routes(g,'code',inferred=True)
    assert g._file_nodes['parser.py'] not in routes and info['stale_edges_excluded']>0

def test_common_baseline_matches_old_recent_window_and_actions():
    p=old_failed_prefix();g=build(p)
    expected,_=previous(p,'M1-5',g,SourceLabeledHistoryReader('point','episode','member_001'),count=count)
    assert run(p,g,'G0')[0]==expected
    for c in ('G1','G2','G3','G4'):
        out,_=run(p,g,c)
        assert out['messages'][-11:]==p['messages'][-11:]
        assert [m for m in out['messages'] if m['role']=='assistant']==[m for m in p['messages'] if m['role']=='assistant']

def test_task_lookup_only_returns_existing_visible_entities_without_promoting_claim():
    p=old_failed_prefix();g=build(p)
    # Real historical task is a user observation; include an explicit task.
    p['messages'].append({'role':'user','content':json.dumps({'observation':{'root_goal':{'description':'Repair parser.py; mystery_unseen.py also mentioned.'}}})})
    g.ingest(p,step=1)
    assert task_roots(g)=={'parser.py':'literal_path_in_original_issue'}
    assert all(n['attrs'].get('path')!='mystery_unseen.py' for n in g.nodes.values())

def test_cross_private_scope_is_denied_and_corrupt_fact_falls_back():
    p=old_failed_prefix();g=build(p)
    with pytest.raises(GraphScopeError):project(p,'G3',g,SourceLabeledHistoryReader('p','foreign','member_001'),count=count,measure=len,indices=list(range(len(p['messages']))))
    for e in g.events.values():
        if e['fields']:e['fields'][0]['value']='forged'
    out,proof=run(p,g,'G1');base,_=run(p,g,'G0')
    assert out==base and proof['fallback']['condition']=='G0'

def test_snapshot_is_immutable_and_exact_historical_version_is_recoverable():
    p=old_failed_prefix();g=build(p);before=g.snapshot();frozen=json.dumps(before,sort_keys=True)
    call(p['messages'],'replace_file',{'path':'parser.py','old':'x','new':'x+1'},{'source_reference':version(2),'paths':['parser.py']})
    call(p['messages'],'run_tests',{'selection':{'kind':'pytest','targets':['tests/test_parser.py']}},public_result('r2',2,True))
    g.ingest(p,step=1)
    assert json.dumps(before,sort_keys=True)==frozen
    assert before['current_version']!=g.current_version
    assert set(before['nodes'])<=set(g.nodes)
    assert len([n for n in before['nodes'].values() if n['type']=='TestRun'])==1
    assert len([n for n in g.nodes.values() if n['type']=='TestRun'])==2

def test_new_call_is_added_only_after_new_code_is_actually_visible():
    p=old_failed_prefix();g=build(p)
    call(p['messages'],'replace_file',{'path':'api.py','old':'return parse(x)','new':'return helper(x)'},
        {'source_reference':version(2),'paths':['api.py']})
    g.ingest(p,step=1)
    assert not any(n['attrs'].get('symbol')=='helper' for n in g.nodes.values())
    call(p['messages'],'read_file',{'path':'api.py'}, {'path':'api.py','source_reference':version(2),
        'text':'def helper(x):\n    return x\ndef api(x):\n    return helper(x)\n'})
    g.ingest(p,step=2)
    calls=[e for e in g.edges.values() if e['type']=='calls' and e['attrs'].get('version')==g.current_version]
    assert any(g.nodes[e['target']]['attrs']['symbol']=='helper' for e in calls)
    assert all(e['status']=='Confirmed' and e['proof']=='static_syntax' for e in calls)
