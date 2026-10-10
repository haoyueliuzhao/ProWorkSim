"""Offline historical reshaping binds actual events without adding actions."""
import copy
import json

import pytest

from proworksim.software_organization_v040 import TOOLS as OLD_TOOLS
from proworksim.harness_port import TOOLS as PRIVATE_TOOLS
from proworksim.storage import digest, json_bytes
from scripts.software_context_replay_v042 import reshape_archived_request


def fixture():
    observation = {'world_id':'world-cpu','instance_id':'instance-cpu','branch_id':'branch-cpu',
        'project_id':'project','actor_id':'member_001','profile':'software-organization-v0.40:member_001',
        'interface_revision':'old','initial_diagnostics':[{'initial_only':'not a new test'}]}
    visible = {'public_diagnostics': {'diagnostic_a': {'executed':True,'passed':False,
        'tests':[{'test_id':'original-failure','passed':False,'expected':'A','observed':'B'}]}},
        'source_reference':{'object_id':'object','version_id':'v1'},'files_sha256':'files-digest',
        'executed':True,'passed':False,'scope':'Original visible scope',
        'untested':['independent_acceptance'],'independent_acceptance':'not_run',
        'fixed_submission_is_acceptance':False,'groups':{}}
    envelope={'ok':True,'result':visible,'action_id':'action-1','logical_time':3,
        'command_id':'command-1','command_committed':True,'committed_revision':3}
    observation_message={'role':'user','content':json.dumps({'role_task':'original instruction','observation':observation})}
    request={'model':'cpu','max_tokens':2048,'tools':[
        {'type':'function','function':copy.deepcopy(t)} for t in [*OLD_TOOLS,*PRIVATE_TOOLS]],
        'messages':[{'role':'system','content':'original system'},observation_message,
            {'role':'assistant','content':'','tool_calls':[{'id':'original-call','type':'function',
                'function':{'name':'run_tests','arguments':'{}'}}]},
            {'role':'tool','name':'run_tests','tool_call_id':'original-call','content':json.dumps(envelope)},
            {'role':'user','content':'{"public_format_feedback":{"reason":"original rejection"}}'},
            copy.deepcopy(observation_message)]}
    event={'actor_id':'member_001','kind':'test','action_id':'action-1','operation_id':'command-1',
        'sequence':7,'source_reference':visible['source_reference'],'files_sha256':'files-digest'}
    return request,visible,envelope,event


def test_replay_shape_keeps_original_wrapper_format_feedback_and_actions():
    request,visible,envelope,event=fixture()
    before=digest(json_bytes(request))
    shaped,receipt=reshape_archived_request(request,{'member':'member_001'},{'command-1':event})
    assert digest(json_bytes(request))==before
    assert len(shaped['messages'])==len(request['messages'])
    assert shaped['messages'][2]==request['messages'][2]
    assert shaped['messages'][4]==request['messages'][4]
    current=json.loads(shaped['messages'][3]['content'])
    assert {k:v for k,v in current.items() if k!='result'}=={k:v for k,v in envelope.items() if k!='result'}
    assert current['result']['report_event']=={'sequence':7,'operation_id':'command-1'}
    report=receipt['report_copies'][0]
    assert json.loads(report['body'])==visible
    assert ''.join(p['text'] for p in report['pages'])==report['body']
    assert receipt['new_page_read_actions']==0
    names=[t['function']['name'] for t in shaped['tools']]
    assert names.count('read_test_result')==1
    assert names.index('read_test_result')+1==names.index('work_note')
    latest=json.loads(shaped['messages'][-1]['content'])['observation']
    assert latest['profile']=='software-organization-v0.42:member_001'
    assert latest['initial_diagnostics']==json.loads(request['messages'][-1]['content'])['observation']['initial_diagnostics']


def test_mismatched_actual_event_source_cannot_become_a_paged_historical_copy():
    request,_,_,event=fixture()
    event['source_reference']={'object_id':'object','version_id':'different'}
    with pytest.raises(ValueError,match='actual world event'):
        reshape_archived_request(request,{'member':'member_001'},{'command-1':event})
