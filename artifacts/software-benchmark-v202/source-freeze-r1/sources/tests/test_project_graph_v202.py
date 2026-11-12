"""Semantic controls independent of PG1-vs-PG2 equality, no model or world calls."""
import copy
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from project_graph_materials_v202 import syntax_cases,synthetic_stream,event,ref_version
from proworksim.software_syntax_facts_v202 import document,SourceAssembler,SourceConflict,SyntaxFacts,IncrementalSyntax,sha
from proworksim.software_project_graph_v202 import ProjectGraph,version_id
from proworksim.software_organization_mapping_v202 import OrganizationMapping

def graph(mode='PG3'):
    st=synthetic_stream();return ProjectGraph(**{k:st[k] for k in ('scope','repo','commit','members')},mode=mode)

@pytest.mark.parametrize('case',syntax_cases(),ids=lambda c:c['id'])
def test_exact_syntax_and_partial_boundary(case):
    result=SyntaxFacts().extract(case['document'],'A2');raw=case['document']['text'].encode()
    for f in result['facts']:
        assert raw[f['start_byte']:f['end_byte']].decode()==f['value']
        assert f['source_hash']==case['document']['source_hash']
        assert f['span_id'] in result['evidence_spans']
    if case['expected_span']:
        assert any([f['start_byte'],f['end_byte']]==case['expected_span'] for f in result['facts'])
    else:assert all(f['completeness']=='partial' and not f['qualified_scope_known'] for f in result['facts'])

def test_multiline_boolean_children_and_binding():
    r=SyntaxFacts().extract(syntax_cases()[0]['document'],'A2');facts={f['fact_id']:f for f in r['facts']}
    assign=next(f for f in facts.values() if f['fact_type']=='Assign')
    boolean=next(f for f in facts.values() if f['fact_type']=='BooleanOperation')
    branches=[f for f in facts.values() if 'boolean_operand' in f['roles']]
    assert boolean['parent_fact_id']==assign['fact_id']
    assert {f['value'] for f in branches}=={'left in names','right in names'}
    assert all(f['parent_fact_id']==boolean['fact_id'] for f in branches)
    assert any(f['value']=='flag' and 'binding_target' in f['roles'] for f in facts.values())

def test_source_assembly_versions_gaps_conflicts_and_tamper():
    a=SourceAssembler();kw=dict(scope=['s','member_001'],path='a.py',version=ref_version('member_001',1),total=6,message_sha256='source')
    first=a.add(**kw,start=3,end=6,text='= 1',source_id='p1');assert not first['complete']
    full=a.add(**kw,start=0,end=3,text='变量 ',source_id='p2');assert full['complete'] and full['text']=='变量 = 1'
    other=a.add(**{**kw,'version':ref_version('member_001',2)},start=0,end=3,text='变量 ',source_id='p3');assert not other['complete']
    with pytest.raises(SourceConflict):a.add(**kw,start=3,end=6,text='= 2',source_id='conflict')
    full['text']+='\n'
    with pytest.raises(SourceConflict):SyntaxFacts().extract(full)

@pytest.mark.parametrize('old,new',[
    ('x=1\n','y=1\n'),('变量="值"\n','变量="新值"\n'),('def f():\n    return 1\n','def f(x):\n    return x\n'),
    ('a = (\n 1 + 2\n)\n','a = (\n 1 + 3\n)\n'),('','a=1\n'),('a=1\n',''),
])
def test_incremental_tree_equals_fresh_and_retains_prior(old,new):
    p=IncrementalSyntax();t,_=p.parse('file',old);prior=str(t.root_node);fork=p.fork();updated,cost=fork.parse('file',new)
    fresh=p.engine.parser.parse(new.encode());assert str(updated.root_node)==str(fresh.root_node)
    assert str(t.root_node)==prior and p.cache['file'][0]==old.encode()
    assert cost['edit_range'] is not None

def test_versions_runs_adoption_and_incremental_reference():
    st=synthetic_stream();gs={m:graph(m) for m in ['PG0','PG1','PG2','PG3']};old=None
    for i,e in enumerate(st['events'],1):
        stats={m:g.apply(e) for m,g in gs.items()};g=gs['PG3']
        assert gs['PG1'].snapshot==gs['PG2'].snapshot==g.snapshot
        if i==11:old=copy.deepcopy(g.snapshot)
        if i==12:
            assert not any(x['type']=='validates_selected_scope' and x['effective'] for x in g.snapshot['edges'].values())
            assert set(stats['PG3']['impact']['potentially_affected'])==set(st['impact_oracles'][e['event_id']])
        if i==18:
            assert not any(x['type']=='validates_selected_scope' and x['target']==g.state['current']['member_002'] for x in g.snapshot['edges'].values())
            assert g.state['artifacts']['member_001\0patch1']['author']=='member_001'
            assert not g.state['files']['member_002\0pkg/client.py']['complete']
        if i==21:assert 'member_001\0pkg/core.py' not in g.state['files'] and 'member_001\0pkg/engine.py' in g.state['files']
        if i==22:assert 'member_001\0pkg/client.py' not in g.state['files']
        if i==23:assert not any(n['type']=='Symbol' and n['path']=='pkg/engine.py' for n in g.snapshot['nodes'].values())
    assert g.snapshots[10]==old
    assert gs['PG0'].snapshot!=g.snapshot
    assert gs['PG2'].syntax.parses<gs['PG1'].syntax.parses
    assert sum(n['type']=='Commit' for n in g.snapshot['nodes'].values())==1
    assert all(n['is_git_commit'] is False for n in g.snapshot['nodes'].values() if n['type']=='Version')

def test_test_reread_not_new_run_and_conflicting_receipt_rejected():
    g=graph();events=synthetic_stream()['events']
    for e in events[:11]:g.apply(e)
    page=copy.deepcopy(events[10]);page['event_id']='page2';page['source_ids']=['page2-source'];g.apply(page)
    assert len(g.state['runs'])==1
    bad=copy.deepcopy(page);bad['event_id']='changed';bad['data']['passed']=False
    with pytest.raises(SourceConflict):g.apply(bad)
    assert g.state['runs']['member_001\0run1']['passed'] is True
    skipped=copy.deepcopy(page);skipped['event_id']='not-executed';skipped['data'].update(report_id='new',executed=False);g.apply(skipped)
    assert len(g.state['runs'])==1

@pytest.mark.parametrize('where',['fail_after_reduce','fail_after_project'])
def test_transaction_rolls_back_graph_tree_log_and_snapshot(where):
    g=graph();es=synthetic_stream()['events']
    for e in es[:11]:g.apply(e)
    before=sha([g.state,g.snapshot,g.events,g.snapshots]);trees={k:(raw,str(t.root_node)) for k,(raw,t) in g.syntax.cache.items()};count=g.syntax.parses
    with pytest.raises(RuntimeError):g.apply(es[11],**{where:True})
    assert before==sha([g.state,g.snapshot,g.events,g.snapshots])
    assert trees=={k:(raw,str(t.root_node)) for k,(raw,t) in g.syntax.cache.items()} and count==g.syntax.parses
    g.apply(es[11]);assert g.apply(es[11])['idempotent']
    bad=copy.deepcopy(es[11]);bad['data']['extra']='changed'
    with pytest.raises(SourceConflict):g.apply(bad)

def test_private_source_and_adoption_guards():
    g=graph();es=synthetic_stream()['events']
    for e in es[:16]:g.apply(e)
    with pytest.raises(SourceConflict):g.apply(es[17])
    bad=copy.deepcopy(es[11]);bad['event_id']='foreign';bad['data']['document']['scope'][1]='member_002'
    with pytest.raises(SourceConflict):g.apply(bad)
    old=copy.deepcopy(g.snapshot)
    e=event('unknown-change','file_unknown','member_001',{'version':ref_version('member_001',99),'paths':[]});g.apply(e)
    assert all(not d['complete'] for k,d in g.state['files'].items() if k.startswith('member_001\0'))
    assert old!=g.snapshot

def test_partial_source_retains_local_facts_without_fabricated_symbol_scope():
    g=graph();g.apply(synthetic_stream()['events'][0])
    doc=document('    x = (\n        a or b\n    )\n',scope=['controlled-project','member_001'],path='partial.py',version=ref_version('member_001',1),source_id='part',complete=False)
    g.apply(event('part','file_observed','member_001',{'document':doc}))
    facts=[n for n in g.snapshot['nodes'].values() if n['type']=='Fact']
    assert facts and all(f['completeness']=='partial' and not f['qualified_scope_known'] for f in facts)
    assert not any(n['type']=='Symbol' for n in g.snapshot['nodes'].values())

def org():
    return OrganizationMapping(members={m:{'live':True,'tools':['replace_file','run_tests','submit_integration']} for m in ['member_001','member_002']},
        regions={'TA':['pkg/core.py'],'TB':['pkg/client.py'],'TC':['tests/test_client.py']},owners={'TA':'member_001','TB':'member_002','TC':'member_002'})

def test_organization_proposals_do_not_mutate_or_authorize_harness():
    g=graph();o=org();before=o.snapshot()
    for e in synthetic_stream()['events'][:10]:g.apply(e)
    ps=o.proposals(g);assert len(ps)==2 and {p['operation'] for p in ps}=={'AddHandoff'}
    assert all(p['validation']['valid'] and p['not_executed'] for p in ps)
    assert o.snapshot()==before
    o.handoffs.update([('TA','TB'),('TA','TC')]);assert not o.proposals(g)
    for i in range(3):g.apply(event('blocked'+str(i),'task','member_001',{**g.state['tasks']['TA'],'status':'blocked'}))
    assert [p['operation'] for p in o.proposals(g)]==['Reassign']
    o.members['member_002']['tools']=[]
    assert not o.proposals(g)[0]['validation']['valid']
    for op in ('Merge','Split'):
        assert not o.validate({'operation':op,'task_ids':['TA','TB']},g.state['tasks'])['valid']
    assert not o.validate({'operation':'RemoveHandoff','task_ids':['TA','TB']},g.state['tasks'])['valid']

def test_synchronization_preserves_private_history_and_no_fake_receipt():
    g=graph();o=org()
    for e in synthetic_stream()['events'][:12]:stats=g.apply(e)
    f={'fact_id':'f','owner':'member_001','source_ids':['src'],'version':ref_version('member_001',2)}
    r=o.synchronization_plan(g,stats['impact'],[f]);peer=next(p for p in r['routes'] if p['recipient']=='member_002');assert not peer['facts']
    f['published_to']=['member_002'];r=o.synchronization_plan(g,stats['impact'],[f]);assert not next(p for p in r['routes'] if p['recipient']=='member_002')['facts']
    f['publication_receipt']='explicit-share';r=o.synchronization_plan(g,stats['impact'],[f]);assert len(next(p for p in r['routes'] if p['recipient']=='member_002')['facts'])==1
    assert r['transport_calls']==0 and all(not p[k] for p in r['routes'] for k in ('sent','presented','read','used'))
