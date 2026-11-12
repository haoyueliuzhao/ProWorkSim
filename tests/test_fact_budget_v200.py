import copy,json
import pytest
from test_fact_context_v199 import setup,count,quiet,diagnostic_fixture
from test_context_graph_v196 import start,call,version,public_result
from proworksim.software_fact_budget_v200 import FactCatalogue,project,slices,subtract,fragments_for,Presentation
from proworksim.software_fact_context_v199 import project as old_project
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_context_selection_v196 import baseline
from proworksim.software_context_graph_v196 import GraphScopeError

def fixture():
    p={'messages':start(),'tools':[]};quiet(p,1)
    # Many independent exact observations of one file version.
    text=''.join(f'def function_{i}(x):\n    value = x + {i}\n    assert value > 0\n    return value\n\n' for i in range(18))
    call(p['messages'],'read_file',{'path':'library.py'},{'path':'library.py','source_reference':version(1),'text':text,'start_character':0,'end_character':len(text),'total_characters':len(text)})
    quiet(p);return p

def run(p,c,budget=4096):
    g,idx,store,inv,en=setup(p);cat=FactCatalogue(inv,en,count)
    view,proof=project(p,c,g,en,inv,cat,store,count=count,measure=lambda v:count(json.dumps(v)),indices=idx,budget=budget)
    return view,proof,cat,store

def test_F0_is_exact_frozen_event_baseline():
    p=fixture();view,proof,cat,store=run(p,'F0');inv=cat.inventory
    expected,_=old_project(p,'E3',inv.graph,cat.entities,inv,SourceLabeledHistoryReader('point','episode','member_001'),count=count,measure=lambda v:count(json.dumps(v)),indices=inv.indices,budget=4096)
    assert view==expected

def test_one_event_can_have_multiple_bounded_cards_under_one_shared_budget():
    view,proof,cat,store=run(fixture(),'F1')
    groups={x['group_id'] for x in proof['selected']};assert any(sum(x['group_id']==g for x in proof['selected'])>1 for g in groups)
    assert all(x['tokens']<=768 for x in proof['selected']) and proof['added_tokens_estimate']<=4096
    assert len(proof['selected'])>len(run(fixture(),'F0')[1]['selected'])

def test_splitting_a_large_fact_is_lossless_and_exact():
    text=('αβγ = ordinary_source_line\n'*100);parts=slices(text,count)
    assert len(parts)>1 and ''.join(text[a:z] for a,z in parts)==text
    assert all(count(text[a:z])<=360 for a,z in parts)

@pytest.mark.parametrize('condition',['F1','F2','F3','F4'])
def test_same_pool_actions_recent_context_references_and_literal_sources(condition):
    p=diagnostic_fixture();view,proof,cat,store=run(p,condition,1024)
    for mask in proof['masked']:assert mask['reference'] in json.dumps(view)
    tools=[i for i,m in enumerate(p['messages']) if m['role']=='tool'];assert view['messages'][tools[-5]:]==p['messages'][tools[-5]:]
    for old,new in zip(p['messages'],view['messages']):
        if old['role']=='assistant':assert old==new
    seen=set()
    for card in proof['selected']:
        for f in card['selected_facts']:
            o=f['origin'];assert cat.inventory.graph.field(o['source_id'],o['channel'],o['pointer'],call_index=o.get('call_index'),span=o.get('span'))['value']==f['value']
            assert f['presentation_id'] not in seen;seen.add(f['presentation_id'])
    assert proof['added_tokens_estimate']<=1024

def test_overlap_subtraction_handles_containment_disjoint_and_partial():
    assert subtract((10,30),[(0,5),(15,20),(25,40)])==[(10,15),(20,25)]
    assert subtract((10,30),[(0,40)])==[]

def test_redundancy_trim_keeps_all_origins_at_the_same_literal_slice():
    _,_,cat,_=run(fixture(),'F1');unit=next(u for u in cat.units.values() if isinstance(u['value'],str) and len(u['value'])>30 and u['origin'].get('span'))
    prefix=copy.deepcopy(unit);prefix['value']=unit['value'][:10]
    for o in [prefix['origin'],*prefix['origins']]:o['span'][1]=o['span'][0]+10
    fragments=fragments_for(unit,cat,[prefix],merge=True);assert len(fragments)==1 and fragments[0]['value']==unit['value'][10:]
    assert fragments[0]['origin']['span']==next(o['span'] for o in fragments[0]['origins'] if o['source_id']==fragments[0]['origin']['source_id'])

def test_duplicate_text_from_different_execution_or_version_never_merges():
    p=diagnostic_fixture();call(p['messages'],'run_tests',{'selection':{'kind':'full'}},public_result('r2',2,False,text='DeprecationWarning: deprecated interface'))
    quiet(p);_,_,cat,_=run(p,'F4');a=next(u for u in cat.units.values() if u['kind']=='exception')
    b=copy.deepcopy(a);b['group_id']='different-real-run'
    assert fragments_for(b,cat,[a],merge=True)

def test_invalid_or_unverified_edges_cannot_create_fact_dependencies():
    p=fixture();g,idx,store,inv,en=setup(p)
    for e in en.edges.values():e['verification_status']='Inferred'
    assert not FactCatalogue(inv,en,count).dependencies
    for e in en.edges.values():e.update(verification_status='Confirmed',effective_for_current_workspace=False)
    assert not FactCatalogue(inv,en,count).dependencies

def test_private_scope_denied_and_overflow_explicit():
    p=fixture();g,idx,store,inv,en=setup(p);cat=FactCatalogue(inv,en,count)
    with pytest.raises(GraphScopeError):project(p,'F1',g,en,inv,cat,SourceLabeledHistoryReader('point','episode','other'),count=count,measure=lambda v:count(json.dumps(v)),indices=idx,budget=1024)
    _,proof,_,_=run(p,'F1',1024)
    assert any(x['reason']=='total_budget' for x in proof['omitted'])

def test_unknown_fact_is_never_rephrased_as_certain_test_success():
    p=diagnostic_fixture();view,proof,cat,store=run(p,'F1')
    assert all(c['card']['text_is_not_new_validation'] for c in proof['selected'])
    assert all(u['status']=='literal_observed_fragment' for u in cat.units.values())

def test_metric_requires_complete_union_and_exact_source_for_split_target():
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
    from score_fact_budget_v200 import witnessed
    target={'source_id':'s','message_sha256':'h','pointer':'/result/text','span':[0,6],'value':'abcdef'}
    def f(text,a,z,sha='h'):return {'value':text,'origin':{'source_id':'s','message_sha256':sha,'channel':'body','pointer':'/result/text','span':[a,z]}}
    assert witnessed(target,[f('abc',0,3),f('def',3,6)])
    assert not witnessed(target,[f('abc',0,3),f('ef',4,6)])
    assert not witnessed(target,[f('abc',0,3),f('def',3,6,'other')])

def test_same_claimed_source_interval_with_conflicting_bytes_is_not_merged():
    from proworksim.software_context_graph_v196 import GraphIntegrityError
    _,_,cat,_=run(fixture(),'F1');unit=next(u for u in cat.units.values() if u['kind']=='code_function')
    fake=copy.deepcopy(unit);fake['value']='X'*len(unit['value'])
    with pytest.raises(GraphIntegrityError):fragments_for(unit,cat,[fake],merge=True)
