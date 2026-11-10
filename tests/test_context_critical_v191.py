import copy,json
import pytest
from proworksim.software_context_critical_v191 import project,inventory,RULES,PREFIX
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader

def fixture():
    messages=[{'role':'system','content':'Original permission constraints'},
        {'role':'user','content':'Original task must be repaired'}]
    for n in range(12):
        tool='run_tests' if n==1 else 'read_file'
        arguments={'selection':{'kind':'pytest','targets':['test_x.py']}} if n==1 else {'path':'x.py'}
        result={'source_reference':{'object_id':'workspace','version_id':'v1'},'path':'x.py','text':'observed code '*300}
        if n==1:result={'source_reference':{'object_id':'workspace','version_id':'v1'},'passed':False,
            'counts':{'failed':1,'passed':0},'execution':{'argv':['python','-m','pytest','test_x.py'],
                'returncode':1,'public_test_selection':arguments['selection']},'text':'test diagnostic '*300}
        messages.extend([{'role':'assistant','tool_calls':[{'id':'call-'+str(n),'type':'function','function':{'name':tool,'arguments':json.dumps(arguments)}}]},
            {'role':'tool','tool_call_id':'call-'+str(n),'content':json.dumps({'ok':True,'result':result})}])
    messages.append({'role':'user','content':json.dumps({'observation':{'workspace_reference':{'object_id':'workspace','version_id':'v2'}}})})
    return {'messages':messages,'tools':[]}

def run(payload,method):
    store=SourceLabeledHistoryReader('point','episode','member_001')
    value,proof=project(payload,method,store,count=lambda s:(len(s)+3)//4)
    return value,proof,store

def test_old_failure_is_preserved_with_explicit_stale_version_and_original_source():
    payload=fixture();baseline,_,_=run(payload,'M1-5');value,proof,store=run(payload,'M1-5K')
    assert '"failed": 1' not in baseline['messages'][5]['content']
    card=proof['critical_cards'][0];assert card['category']=='test_failure'
    assert card['version_status']=='historical_workspace_version'
    text=value['messages'][card['index']]['content'];assert text.startswith(PREFIX)
    assert '"current_version_validated":false' in text
    entry=store.entries[card['reference']];assert entry['text']==payload['messages'][card['index']]['content']
    assert any(f['pointer']=='/result/counts' and f['value']['failed']==1 for f in card['fields'])

def test_current_observation_and_all_actions_remain_byte_equal():
    payload=fixture();value,proof,_=run(payload,'M1-5K')
    assert value['messages'][-11:]==payload['messages'][-11:]
    assert value['messages'][:2]==payload['messages'][:2]
    for a,b in zip(value['messages'],payload['messages']):
        if b['role']=='assistant':assert a==b
        assert a.get('tool_call_id')==b.get('tool_call_id')
    assert proof['critical_card_tokens_estimate']<=RULES['maximum_critical_tokens']

def test_new_result_same_selector_supersedes_old_failed_result():
    payload=fixture();old=copy.deepcopy(payload['messages'][4:6]);old[0]['tool_calls'][0]['id']='fresh-test'
    old[1]['tool_call_id']='fresh-test';body=json.loads(old[1]['content'])
    body['result'].update(passed=True,counts={'failed':0,'passed':1},source_reference={'object_id':'workspace','version_id':'v2'})
    old[1]['content']=json.dumps(body);payload['messages'][-1:-1]=old
    value,proof,_=run(payload,'M1-5K')
    assert not proof['critical_cards']
    assert 'Retained historical critical event' not in value['messages'][5]['content']
    events,_=inventory(payload);assert events[0]['superseded_by_message_index']==len(payload['messages'])-2

def test_unknown_version_never_becomes_current_validation():
    payload=fixture();body=json.loads(payload['messages'][5]['content']);body['result'].pop('source_reference')
    payload['messages'][5]['content']=json.dumps(body)
    _,proof,_=run(payload,'M1-5K');assert proof['critical_cards'][0]['version_status']=='unknown'

def test_original_reference_has_exact_pages_and_private_permission():
    payload=fixture();_,proof,store=run(payload,'M1-5K');card=proof['critical_cards'][0]
    pages=[];start=0
    while True:
        v=store.read({'reference':card['reference'],'start':start,'characters':500},point_id='point',slot_id='episode',member_id='member_001')
        pages.append(v['text'])
        if v['next_start'] is None:break
        start=v['next_start']
    assert ''.join(pages)==payload['messages'][card['index']]['content']
    with pytest.raises(PermissionError):store.read({'reference':card['reference']},point_id='point',slot_id='other',member_id='member_001')

def test_no_model_or_filesystem_input_and_deterministic_output(monkeypatch):
    from pathlib import Path
    payload=fixture()
    monkeypatch.setattr(Path,'read_bytes',lambda *_:pytest.fail('Hidden source lookup'))
    a,pa,_=run(payload,'M1-5K');b,pb,_=run(payload,'M1-5K')
    assert a==b and pa==pb

def test_card_budget_falls_back_to_the_same_raw_reference(monkeypatch):
    monkeypatch.setitem(RULES,'maximum_card_tokens',1)
    value,proof,store=run(fixture(),'M1-5K')
    assert not proof['critical_cards'] and proof['critical_fallbacks']
    card=proof['critical_fallbacks'][0];assert card['reference'] in value['messages'][card['index']]['content']
    assert card['reference'] in store.entries

@pytest.mark.parametrize('method',['M1-5','M1-10'])
def test_comparison_views_match_the_frozen_v181_projection(method):
    from proworksim.software_context_runtime_v181 import ContextState
    payload=fixture();expected_store=SourceLabeledHistoryReader('point','episode','member_001')
    state=ContextState.__new__(ContextState);state.condition=method;state.count=lambda s:(len(s)+3)//4
    state.store=expected_store;state.selected_indices=None;state.persist=lambda:None
    expected,_=state.projection(payload,original=payload)
    observed,_,_=run(payload,method)
    assert observed==expected
