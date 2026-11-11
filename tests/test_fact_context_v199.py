import copy,json
import pytest
from test_context_graph_v196 import start,call,public_result,version,build
from proworksim.software_global_evidence_v198 import enrich
from proworksim.software_fact_context_v199 import FactInventory,normalize,code_spans,diagnostic_spans,project
from proworksim.software_context_selection_v196 import baseline
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_evidence_bindings_v199 import EvidenceBindings

def count(s):return (len(s)+3)//4
def setup(p):
    g=build(p);idx=list(range(len(p['messages'])));enrich(g,p,idx)
    store=SourceLabeledHistoryReader('point','episode','member_001');base,mask,cut=baseline(p,store,count,idx)
    inv=FactInventory(g,p,idx,mask,cut);entities=EvidenceBindings(g.snapshot(),repo='example/repo',base_commit='a'*40,issue_id='task')
    return g,idx,store,inv,entities
def quiet(p,n=7):
    for i in range(n):call(p['messages'],'search_repository',{'text':'distant'}, {'matches':[],'text':'unrelated observed text '*80})
def diagnostic_fixture():
    p={'messages':start(),'tools':[]};p['messages'].append({'role':'user','content':json.dumps({'observation':{'workspace_reference':version(1)}})})
    call(p['messages'],'run_tests',{'selection':{'kind':'pytest','targets':['test_x.py']}},public_result('r1',text=r'DeprecationWarning: deprecated interface\nFMT <class SymbolFormatter>\nOFFSET NOW 10e3\n> assert False, "probe"'))
    quiet(p);return p

def test_warning_stdout_and_explicit_false_are_distinct_literal_facts():
    g,idx,store,inv,en=setup(diagnostic_fixture());kinds={f['kind'] for f in inv.facts.values()}
    assert {'exception','diagnostic_output','explicit_assert_false'}<=kinds
    assert all(f['status']=='literal_observed_not_generated' for f in inv.facts.values())

def test_code_selector_keeps_complete_control_chain_and_function():
    text='if ascii(host):\n    accept(host)\nelif invalid(host):\n    reject(host)\n\ndef f(x):\n    y = make(x)\n    assert y\n    return y\n'
    spans=code_spans(text)
    assert any(k=='code_control' and 'elif invalid' in text[a:b] for k,a,b in spans)
    assert any(k=='code_function' and 'return y' in text[a:b] for k,a,b in spans)

def test_equal_state_reads_merge_but_A_B_A_has_three_epochs():
    p={'messages':start()}
    for status in ['pending','pending','completed','pending']:
        p['messages'].append({'role':'user','content':json.dumps({'observation':{'workspace_reference':version(1),'delivery_status':{'status':status}}})})
    g,_,_,inv,_=setup(p);states=[x for x in inv.groups.values() if x['kind']=='state']
    assert len(states)==3 and sorted(len(x['members']) for x in states)==[1,1,2]
    assert len(inv.state_transitions)==2

def test_identical_state_value_in_different_versions_does_not_merge():
    p={'messages':start()}
    for n in [1,2]:p['messages'].append({'role':'user','content':json.dumps({'observation':{'workspace_reference':version(n),'delivery_status':{'status':'pending'}}})})
    _,_,_,inv,_=setup(p);assert sum(x['kind']=='state' for x in inv.groups.values())==2

def test_same_run_different_pages_and_rereads_preserve_one_run_and_all_sources():
    p=diagnostic_fixture();call(p['messages'],'read_test_result',{'report_id':'r1'},public_result('r1',text='ValueError: another already visible page'))
    g,_,_,inv,_=setup(p);test_groups=[x for x in inv.groups.values() if x['kind']=='test'];assert len(test_groups)==1
    assert len(test_groups[0]['sources'])==2
    call(p['messages'],'run_tests',{'selection':{'kind':'pytest','targets':['test_x.py']}},public_result('r2'))
    _,_,_,inv,_=setup(p);assert sum(x['kind']=='test' for x in inv.groups.values())==2

def test_code_reads_group_by_exact_private_file_version_without_deleting_occurrences():
    p={'messages':start()}
    for v in [1,1,2]:call(p['messages'],'read_file',{'path':'a.py'}, {'path':'a.py','source_reference':version(v),'text':'def f():\n    return 1\n','start_character':0,'end_character':22,'total_characters':22})
    _,_,_,inv,_=setup(p);groups=[x for x in inv.groups.values() if x['kind']=='code']
    assert len(groups)==2 and sum(len(x['raw_occurrences']) for x in groups)==3

def test_state_fact_names_do_not_disappear_when_boolean_values_equal():
    p={'messages':start()};p['messages'].append({'role':'user','content':json.dumps({'observation':{'workspace_reference':version(1),'delivery_status':{'public_test_executed':False,'public_test_passed':False}}})})
    _,_,_,inv,_=setup(p)
    names={f['name'] for f in inv.facts.values() if f['value'] is False}
    assert {'delivery_status_public_test_executed','delivery_status_public_test_passed'}<=names

def test_factorial_conditions_share_facts_and_E2_only_protects_observed_failed_tests():
    p=diagnostic_fixture();g,idx,store,inv,en=setup(p);proofs={}
    for c in ['E0','E1','E2','E3','E4']:
        out,proof=project(p,c,g,en,inv,SourceLabeledHistoryReader('point','episode','member_001'),count=count,measure=lambda v:count(json.dumps(v)),indices=idx,budget=4096)
        proofs[c]=proof
        cutoff=[i for i,m in enumerate(p['messages']) if m['role']=='tool'][-5]
        assert out['messages'][cutoff:]==p['messages'][cutoff:]
    assert len({v['fact_pool_sha256'] for v in proofs.values()})==1
    assert not proofs['E0']['selected'] and not proofs['E1']['mandatory_groups']
    assert all(s['group_id'] in proofs['E2']['mandatory_groups'] for s in proofs['E2']['selected'])
    assert not proofs['E3']['graph_bonus']

def test_selected_facts_are_exact_source_spans_and_recoverable():
    p=diagnostic_fixture();g,idx,store,inv,en=setup(p)
    out,proof=project(p,'E3',g,en,inv,store,count=count,measure=lambda v:count(json.dumps(v)),indices=idx,budget=4096)
    assert proof['selected']
    for row in proof['selected']:
        assert row['card']['text_is_not_new_validation'] is True
        for f in row['selected_facts']:
            o=f['origin'];actual=g.field(o['source_id'],o['channel'],o['pointer'],call_index=o.get('call_index'),span=o.get('span'))
            assert actual['value']==f['value']
            assert store.read({'reference':f['source_reference'],'start':0},point_id='point',slot_id='episode',member_id='member_001')['text']

def test_mutated_fact_fails_source_verification():
    from proworksim.software_context_graph_v196 import GraphIntegrityError
    p=diagnostic_fixture();g,idx,store,inv,en=setup(p)
    for f in inv.facts.values():f['value']='fabricated'
    with pytest.raises(GraphIntegrityError):project(p,'E3',g,en,inv,store,count=count,measure=lambda v:count(json.dumps(v)),indices=idx,budget=4096)

def test_successful_write_definitions_require_real_receipt_and_do_not_fabricate_reads():
    p={'messages':start()};text='from other import helper as alias\ndef test_new(x):\n    return alias(x)\n'
    call(p['messages'],'create_file',{'path':'test_new.py','text':text},{'source_reference':version(2),'paths':['test_new.py']})
    g=build(p);before=len(g.sources);en=EvidenceBindings(g.snapshot(),repo='example/repo',base_commit='a'*40,issue_id='task')
    assert len(g.sources)==before and en.as_json()['no_synthetic_read_observations']
    assert any(e['kind']=='Symbol' and e['identity'].get('qualified_name')=='test_new' for e in en.entities.values())
    assert any(a['alias']=='alias' for a in en.aliases)
    assert all(e['verification_status']!='Confirmed' for e in en.edges.values() if e['relation_type']=='resolves_to')
    p['messages'][-1]['content']=json.dumps({'ok':False,'error':{'type':'rejected'}})
    en=EvidenceBindings(build(p).snapshot(),repo='example/repo',base_commit='a'*40,issue_id='task')
    assert not en.write_materials

def test_historical_snapshot_is_not_mutated_by_later_fact_normalization():
    p=diagnostic_fixture();g,_,_,inv,_=setup(p);old=inv.snapshot();before=json.dumps(old,sort_keys=True)
    call(p['messages'],'run_tests',{'selection':{'kind':'full'}},public_result('r2',2,True))
    setup(p)
    assert before==json.dumps(old,sort_keys=True)

def test_same_message_index_with_changed_payload_is_not_direct_visibility():
    p=diagnostic_fixture();g,idx,store,inv,en=setup(p)
    changed=copy.deepcopy(p);changed['messages'][3]['content']='a different actual observation'
    # Build from the preserved old source while the current request has changed.
    fresh=FactInventory(g,changed,idx,[],0)
    from_old=[f for f in fresh.facts.values() if any(o['message_index']==3 for o in f['origins'])]
    assert from_old and not any(f['already_direct'] for f in from_old)

def test_nested_code_spans_are_not_quoted_twice_in_one_card():
    p={'messages':start(),'tools':[]};text='# ordinary source documentation\n'*30+'def repair(x):\n    y = transform(x)\n    return y\n'
    quiet(p,1) # The original first observation remains unmasked by design.
    call(p['messages'],'read_file',{'path':'a.py'},{'path':'a.py','text':text,'start_character':0,'end_character':len(text),'total_characters':len(text),'source_reference':version(1)})
    quiet(p);g,idx,store,inv,en=setup(p)
    out,proof=project(p,'E1',g,en,inv,store,count=count,measure=lambda v:count(json.dumps(v)),indices=idx,budget=4096)
    cards=[s for s in proof['selected'] if any(f['kind']=='code_function' for f in s['card']['facts'])]
    assert cards and any(o['reason']=='already_quoted_source_span' for o in cards[0]['omitted_facts'])
    assert sum('return y' in str(f['value']) for f in cards[0]['card']['facts'])==1

def test_wrong_member_cannot_recover_retained_sources():
    p=diagnostic_fixture();g,idx,store,inv,en=setup(p)
    out,proof=project(p,'E3',g,en,inv,store,count=count,measure=lambda v:count(json.dumps(v)),indices=idx,budget=4096)
    ref=proof['selected'][0]['card']['originals'][0]
    with pytest.raises(PermissionError):store.read({'reference':ref,'start':0},point_id='point',slot_id='episode',member_id='other')

def test_saturated_budget_records_unmet_protection_without_exceeding_limit():
    p={'messages':start(),'tools':[]}
    for i in range(8):call(p['messages'],'run_tests',{'selection':{'kind':'pytest','targets':[f'test_{i}.py']}},public_result(f'report{i}',text='ValueError: context '+('long diagnostic '*20)))
    quiet(p);g,idx,store,inv,en=setup(p)
    out,proof=project(p,'E2',g,en,inv,store,count=count,measure=lambda v:count(json.dumps(v)),indices=idx,budget=1024)
    assert proof['unmet_mandatory'] and proof['added_tokens_estimate']<=1024

def test_reference_coverage_requires_source_identity_and_complete_target_span():
    from proworksim.software_fact_metrics_v199 import covers
    origin={'channel':'body','source_id':'s','message_sha256':'h','pointer':'/result/text','span':[10,30]}
    ref={'source_id':'s','message_sha256':'h','pointer':'/result/text','span':[15,20],'value':'56789'}
    assert covers('01234567890123456789',origin,ref)
    assert not covers('01234567890123456789',{**origin,'message_sha256':'other'},ref)
    assert not covers('0123456789', {**origin,'span':[10,20]}, {**ref,'span':[15,21],'value':'567890'})

def test_reference_counts_are_covered_by_structured_parent_not_unrelated_number():
    from proworksim.software_fact_metrics_v199 import covers
    ref={'source_id':'s','message_sha256':'h','pointer':'/result/counts/passed','span':None,'value':185}
    origin={'channel':'body','source_id':'s','message_sha256':'h','pointer':'/result/counts'}
    assert covers({'passed':185,'errors':2},origin,ref)
    assert not covers({'passed':2,'errors':185},origin,ref)

def test_card_keeps_anchor_recovery_when_facts_come_from_an_earlier_page():
    p=diagnostic_fixture()
    call(p['messages'],'read_test_result',{'report_id':'r1'},public_result('r1',text='A low-priority different page '+('ordinary text '*100)))
    quiet(p);g,idx,store,inv,en=setup(p)
    view,proof=project(p,'E3',g,en,inv,store,count=count,measure=lambda v:count(json.dumps(v)),indices=idx,budget=4096)
    assert proof['selected']
    for mask in proof['masked']:assert mask['reference'] in json.dumps(view)

def test_history_occurrence_counter_does_not_create_false_state_transitions():
    p={'messages':start()}
    for counter,note in [(1,{}),(3,{}),(5,{'n':'new actual note'})]:
        p['messages'].append({'role':'user','content':json.dumps({'observation':{'workspace_reference':version(1),
            'personal_workbench':{'observed_history_entries':counter,'notes':note,'todos':{}}}})})
    _,_,_,inv,_=setup(p);states=[g for g in inv.groups.values() if g['kind']=='state']
    assert len(states)==2 and sum(len(g['members']) for g in states)==3
    counters=[f for f in inv.facts.values() if f['presentation_role']=='occurrence_counter']
    assert sorted(f['value'] for f in counters)==[1,3,5] # The source facts are not deleted.

def test_graph_bonus_requires_a_real_current_edge_to_a_new_entity():
    from types import SimpleNamespace
    from proworksim.software_fact_context_v199 import confirmed_bonus
    pool=[{'id':'seed','members':['e1']},{'id':'next','members':['e2']}]
    en=SimpleNamespace(event_bindings={'e1':['a'],'e2':['b']},edges={})
    assert confirmed_bonus(pool,en,{'seed'})=={}
    edge={'edge_id':'ab','source_entity_id':'a','target_entity_id':'b','verification_status':'Confirmed',
        'effective_for_current_workspace':True,'relation_type':'declares'}
    en.edges={'ab':edge};result=confirmed_bonus(pool,en,{'seed'})
    assert set(result)=={'next'} and result['next']['edge_ids']==['ab']
    edge['effective_for_current_workspace']=False;assert confirmed_bonus(pool,en,{'seed'})=={}
    edge.update(effective_for_current_workspace=True,verification_status='Inferred');assert confirmed_bonus(pool,en,{'seed'})=={}
