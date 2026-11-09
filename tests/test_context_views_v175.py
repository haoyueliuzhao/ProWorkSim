import copy
import json
import pytest

from proworksim.software_context_compression_v175 import (
    EvidenceStore,apply,baseline,observations,summary_prefix,apply_summary)


def payload():
    messages=[{'role':'system','content':'Frozen permissions'}, {'role':'user','content':'Original task'}]
    for i in range(12):
        messages.extend([{'role':'assistant','content':'Act','tool_calls':[{'id':str(i),'type':'function',
            'function':{'name':'read_file','arguments':'{}'}}]},
            {'role':'tool','tool_call_id':str(i),'name':'read_file','content':('exact code observation '+str(i)+'\n')*50}])
    messages.append({'role':'user','content':'Latest real state'})
    return {'model':'deepseek-flash','messages':messages,'tools':[]}


def test_mask_actual_observations_preserves_actions_task_and_recent_context():
    original=payload();snapshot=copy.deepcopy(original)
    store=EvidenceStore('p0','slot','member_001')
    result,metrics=apply(original,'M1',store,count=len)
    assert original==snapshot and len(metrics['replaced'])==6
    assert result['messages'][0:2]==original['messages'][0:2]
    assert result['messages'][-1]==original['messages'][-1]
    for i in observations(original)[-5:]:assert result['messages'][i]==original['messages'][i]
    for changed in metrics['replaced']:
        recovered=store.read({'reference':changed['reference']},point_id='p0',slot_id='slot',member_id='member_001')
        assert recovered['text']==original['messages'][changed['message_index']]['content']
    with pytest.raises(PermissionError):
        store.read({'reference':metrics['replaced'][0]['reference']},point_id='p0',slot_id='slot',member_id='member_002')


def test_neural_extraction_keeps_original_complete_observations_without_code_rewriting():
    original=payload();store=EvidenceStore('p0','slot','member_001')
    _,refs=baseline(original,EvidenceStore('p0','slot','member_001'))
    probabilities={ref:float(index) for index,ref in refs.items()}
    result,metrics=apply(original,'M2',store,count=len,neural_scores=probabilities)
    removed={x['message_index'] for x in metrics['replaced']}
    assert 5 in removed and 15 not in removed
    for i in observations(original):
        if i not in removed:assert result['messages'][i]==original['messages'][i]
    assert metrics['local_token_saving']>0


def test_old_user_role_environment_snapshots_are_masked_but_initial_and_current_are_not():
    value=payload()
    value['messages'][1]['content']=json.dumps({'observation':{'goal':'original task'}})
    # Insert an old large World observation between completed tool rounds.
    value['messages'].insert(4,{'role':'user','content':json.dumps({'observation':{'old_output':'data '*1000}})})
    value['messages'][-1]['content']=json.dumps({'observation':{'current_version':'v8'}})
    transformed,measurement=apply(value,'M1',EvidenceStore('p0','slot','member_001'),count=len)
    assert 4 in {r['message_index'] for r in measurement['replaced']}
    assert transformed['messages'][1]==value['messages'][1]
    assert transformed['messages'][-1]==value['messages'][-1]


def test_hybrid_closed_prefix_does_not_orphan_tool_results_and_rejects_longer_summary():
    original=payload();prefix=summary_prefix(original)
    result,receipt=apply_summary(original,prefix,'Only a derived summary.',count=len)
    assert receipt['adopted']
    assert result['messages'][:2]==original['messages'][:2]
    assert result['messages'][-1]==original['messages'][-1]
    called={t['id'] for m in result['messages'] for t in m.get('tool_calls',[])}
    returned={m['tool_call_id'] for m in result['messages'] if m['role']=='tool'}
    assert called==returned
    unchanged,receipt=apply_summary(original,prefix,'long '*100000,count=len)
    assert unchanged==original and not receipt['adopted']
