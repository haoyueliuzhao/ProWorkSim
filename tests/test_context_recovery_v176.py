import json

import pytest

from proworksim.software_context_compression_v175 import apply,summary_prefix
from proworksim.software_context_recovery_v176 import HistoryEvidenceStore,apply_recoverable_summary


def fixture():
    messages=[{'role':'system','content':'Permissions'},{'role':'user','content':'Task'}]
    for i in range(12):
        messages.extend([{'role':'assistant','tool_calls':[{'id':'call'+str(i),'type':'function',
            'function':{'name':'write_file','arguments':json.dumps({'path':'sample.py','content':'old action '+str(i)})}}]},
            {'role':'tool','tool_call_id':'call'+str(i),'content':('exact old output '+str(i)+'\n')*200}])
    messages.append({'role':'user','content':'Latest unchanged state'})
    original={'messages':messages,'tools':[]}
    store=HistoryEvidenceStore('point','episode','member_001')
    masked,_=apply(original,'M3',store,count=len)
    return original,masked,store,summary_prefix(masked)


def test_summary_without_any_ids_still_restores_original_actions_and_results():
    original,masked,store,prefix=fixture()
    result,proof=apply_recoverable_summary(masked,prefix,'An incomplete prose summary.',
        original_payload=original,store=store,count=len)
    assert proof['adopted']
    assert proof['original_prefix_reference'] in result['messages'][prefix['start']]['content']
    index=store.read({'reference':proof['original_prefix_reference'],'characters':1},
        point_id='point',slot_id='episode',member_id='member_001')['message_offsets']
    chosen=index[2]
    exact=store.read({'reference':proof['original_prefix_reference'],'start':chosen['start'],
        'characters':chosen['end']-chosen['start']},point_id='point',slot_id='episode',member_id='member_001')
    assert json.loads(exact['text'])==original['messages'][chosen['message_index']]
    pages=[];start=0
    while True:
        page=store.read({'reference':proof['original_prefix_reference'],'start':start,'characters':1000},
            point_id='point',slot_id='episode',member_id='member_001')
        assert page['scope']=='previously_presented_private_history'
        assert not page['current_version_validated']
        pages.append(page['text'])
        if page['next_start'] is None:break
        start=page['next_start']
    assert json.loads(''.join(pages))['messages']==original['messages'][prefix['start']:prefix['end']]
    assert result['messages'][-1]==original['messages'][-1]
    with pytest.raises(PermissionError):
        store.read({'reference':proof['original_prefix_reference']},point_id='point',slot_id='episode',member_id='member_002')


def test_pointer_cost_participates_in_no_expansion_check():
    original,masked,store,prefix=fixture()
    result,proof=apply_recoverable_summary(masked,prefix,'Long text '*100000,
        original_payload=original,store=store,count=len)
    assert not proof['adopted'] and result==masked


def test_cannot_archive_altered_action_as_if_it_was_observed():
    original,masked,store,prefix=fixture()
    original['messages'][2]['tool_calls'][0]['function']['arguments']='{"path":"foreign.py"}'
    with pytest.raises(ValueError,match='Only verified observation masking'):
        apply_recoverable_summary(masked,prefix,'Summary',original_payload=original,store=store,count=len)


def test_cannot_substitute_another_members_masked_observation():
    original,masked,store,prefix=fixture()
    original['messages'][5]['content']='never observed private text'
    with pytest.raises(ValueError,match='Original observation is not bound'):
        apply_recoverable_summary(masked,prefix,'Summary',original_payload=original,store=store,count=len)
