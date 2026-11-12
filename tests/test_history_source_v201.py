import copy,hashlib,json
import pytest
from proworksim.software_history_source_v201 import WireIdentity,verify_request_capture,STATIC_MARKER
from proworksim.software_context_compression_v175 import digest
from proworksim.software_context_graph_v196 import GraphIntegrityError

def test_wire_ids_survive_condensation_and_preserve_different_calls():
    tracker=WireIdentity();a={'role':'assistant','tool_calls':[{'id':'c1'}]};t={'role':'tool','tool_call_id':'c1','content':'one'}
    first=tracker.assign({'messages':[{'role':'system','content':'system'},a,t]},'r1')
    second=tracker.assign({'messages':[{'role':'system','content':'system'},{'role':'user','content':'observed SDK summary'},a,t,{'role':'tool','tool_call_id':'c2','content':'one'}]},'r2')
    assert first[1:]==second[2:4] and second[4]!=first[2]

def test_registered_static_link_needs_prior_real_full_source_and_exact_anchor():
    tracker=WireIdentity();original={'observation':{'workspace_reference':{'version_id':'v1'},'root_goal':{'description':'task'}}}
    text=json.dumps(original);full={'role':'user','content':text};first=tracker.assign({'messages':[full]},'r1')
    reduced=copy.deepcopy(original);del reduced['observation']['root_goal']
    reduced[STATIC_MARKER]={'original_content_sha256':hashlib.sha256(text.encode()).hexdigest(),'anchor_message_index':1,'anchor_content_sha256':hashlib.sha256(text.encode()).hexdigest(),'omitted_equal_paths':['/observation/root_goal']}
    payload={'messages':[{'role':'user','content':json.dumps(reduced)},full]}
    indexes=tracker.assign(payload,'r2');assert indexes[0]==first[0] and indexes[1]!=indexes[0]
    with pytest.raises(GraphIntegrityError):WireIdentity().assign(payload,'r2')
    payload['messages'][1]['content']='tampered'
    with pytest.raises(GraphIntegrityError):tracker.assign(payload,'r3')

def test_capture_requires_exact_client_and_provider_receipts(tmp_path):
    payload={'messages':[{'role':'system','content':'real'}]};raw=json.dumps({'request':payload,'usage_id':'agent'}).encode();p=tmp_path/'request.json';p.write_bytes(raw)
    call={'request':{'sha256':hashlib.sha256(raw).hexdigest()},'usage_id':'agent','request_id':'task:member_001:0001'}
    provider={'status':'settled','request_sha256':digest(payload),'slot_id':'task','usage_id':'agent'}
    assert verify_request_capture(p,call,provider,expected_slot='task')==payload
    with pytest.raises(GraphIntegrityError):verify_request_capture(p,call,{**provider,'status':'reserved'},expected_slot='task')
    with pytest.raises(GraphIntegrityError):verify_request_capture(p,call,{**provider,'request_sha256':'other'},expected_slot='task')
    with pytest.raises(GraphIntegrityError):verify_request_capture(p,call,provider,expected_slot='another_task')
    p.write_bytes(raw+b' ')
    with pytest.raises(GraphIntegrityError):verify_request_capture(p,call,provider,expected_slot='task')
