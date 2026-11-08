import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from proworksim.software_input_provenance_v156 import (
    AnnotatedText, SourceFragment, TextSegment, build_request,
)
from proworksim.software_sdk_input_sources_v156 import (
    annotate_agent_wire, annotate_message, published_version_bindings, raw, sha,
)
from proworksim.software_communication_runtime_v156 import (
    AccountingConflict, AuditedRequestGateway, SharedTeamPool,
)


def identity(request='r1'):
    return {'request_id': request, 'episode_id': 'team', 'member_id': 'member_002',
            'decision_id': 'd1', 'attempt_id': request, 'model_alias': 'deepseek-flash',
            'request_time': '2026-11-08T00:00:00Z'}


def test_actual_json_escapes_duplicates_and_event_ids_are_not_text_search():
    text = json.dumps({'role_task': 'review', 'observation': {
        'source_contract_sha256': 'a'*64, 'root_goal': {'description': 'repair'},
        'messages': [{'sequence': 7, 'actor_id': 'member_001', 'recipient': 'member_002',
                      'body': 'same\n"内容"'},
                     {'sequence': 8, 'actor_id': 'member_001', 'recipient': 'member_002',
                      'body': 'same\n"内容"'}],
        'patches': [{'patch_id': 'patch-1', 'version_id': 'v2'}]}}, ensure_ascii=False)
    messages = [{'role': 'user', 'content': text}, {'role': 'user', 'content': 'Unregistered free text'}]
    wire = {'model': 'deepseek-flash', 'messages': messages, 'tools': [], 'max_tokens': 10}
    origins = [{'event_ids': ['observed1'], 'event_types': ['MessageEvent'], 'wire_message': messages[0]},
               {'event_ids': [], 'event_types': [], 'wire_message': messages[1]}]
    annotated, template, _ = annotate_agent_wire(wire, origins, member='member_002')
    built = build_request(annotated, identity(), template_source=template)
    assert built.payload_bytes == raw(wire)
    sources = [s['source'] for s in built.manifest['spans'] if s.get('source')]
    peers = {s['origin_event_id'] for s in sources if s['category'] == 'Peer-message'}
    assert peers == {'unbound-local-control:world-message:7', 'unbound-local-control:world-message:8'}
    assert {'Task', 'Artifact', 'Tool-feedback'} <= {s['category'] for s in sources}
    assert any(s.get('source') is None for s in built.manifest['spans'])


def test_source_projection_mismatch_is_unknown_instead_of_invented_history():
    wire = {'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': 'x'}], 'tools': []}
    annotated, template, evidence = annotate_agent_wire(wire, [], member='member_002')
    assert annotated == wire
    assert evidence['source_mapping'] == 'unavailable_index_projection'


def test_registered_lossless_history_keeps_origin_after_static_task_field_deduplication():
    original = {'role': 'user', 'content': json.dumps({'role_task': 'review', 'observation': {'status': 'working'}})}
    changed = {'role': 'user', 'content': json.dumps({'observation': {'status': 'working'},
        '_v117_same_input_static_fields': {'omitted_equal_paths': ['/role_task'], 'anchor_message_index': 1}})}
    wire = {'messages': [changed], 'tools': [], 'model': 'deepseek-flash'}
    origins = [{'event_ids': ['observation1'], 'event_types': ['MessageEvent'], 'wire_message': original}]
    annotated, template, _ = annotate_agent_wire(wire, origins, member='member_002', projection={
        'observation_history_projection': {'validation': {'passed': True}}})
    built = build_request(annotated, identity(), template_source=template)
    assert built.payload_bytes == raw(wire)
    assert all(s['source'] is not None for s in built.manifest['spans'] if s['semantic_input'])
    unverified, _, _ = annotate_agent_wire(wire, origins, member='member_002')
    assert unverified['messages'][0]['content'] == changed['content']


def test_gateway_captures_exact_bytes_usage_identity_and_blocks_cross_directory_replay(tmp_path):
    class CPU:
        evidence_domain = 'cpu_synthetic'
        calls = []

        def __call__(self, payload, *, identity):
            self.calls.append(payload)
            return {'id': 'response1', 'model': 'scripted-provider', 'system_fingerprint': 'cpu-only',
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12},
                    'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'ok'}}]}

    pool = SharedTeamPool(tmp_path/'pool', 'team')
    transport = CPU()
    gateway = AuditedRequestGateway(tmp_path/'capture', pool, transport)
    fact = SourceFragment('Task', 'task', 'task-event', 'public-task')
    wire = {'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': AnnotatedText((TextSegment('task', fact),))}]}
    returned = gateway.complete(wire, identity=identity(), purpose='agent', input_upper=20, max_output=10)
    assert returned['usage']['total_tokens'] == pool.snapshot()['known_actual_tokens'] == 12
    folder = tmp_path/'capture'/hashlib.sha256(b'r1').hexdigest()
    assert transport.calls == [(folder/'payload.json').read_bytes()]
    response = json.loads((folder/'response.json').read_bytes())
    assert response['provider_fingerprint']['value'] == 'cpu-only'
    other = AuditedRequestGateway(tmp_path/'another-capture', pool, transport)
    with pytest.raises(AccountingConflict):
        other.complete(wire, identity=identity(), purpose='agent', input_upper=20, max_output=10)
    assert len(transport.calls) == 1


def test_peer_retrieval_keeps_original_author_lineage_without_double_primary_class():
    event = {'sequence': 7, 'kind': 'work_message', 'actor_id': 'member_001',
             'recipient': 'member_002', 'body': 'failed test remains unresolved'}
    message = {'role': 'tool', 'tool_call_id': 'read-7',
               'content': json.dumps({'ok': True, 'result': event})}
    origin = {'event_ids': ['tool-result'], 'event_types': ['ObservationEvent'],
              'tool_name': 'read_work_event', 'wire_message': message}
    annotated = annotate_message(message, origin, member='member_002', episode_id='team')
    built = build_request({'messages': [annotated]}, identity())
    sources = [s['source'] for s in built.manifest['spans'] if s.get('source')]
    read = [s for s in sources if s['category'] == 'Retrieved']
    assert read and all(s['origin_member_id'] == 'member_001' for s in read)
    assert all(s['parent_source_ids'] == ['team:world-message:7:body',
        'sdk-tool-call:team:member_002:read-7'] for s in read)
    assert not any(s['category'] == 'Peer-message' for s in sources)


def test_artifact_version_comes_from_actual_publication_identity_not_leaf_text():
    reference = {'object_id': 'source-1', 'version_id': 'v2'}
    content = {'files_sha256': 'a'*64, 'entry_metadata_sha256': 'b'*64}
    row = {'event_id': 'publication-1', 'kind': 'artifact_published',
           'data': {'source_reference': reference, 'content_identity': content}}
    owner = SimpleNamespace(observation=SimpleNamespace(log=SimpleNamespace(_rows={'publication-1': row})))
    bindings = published_version_bindings(owner)
    expected = sha({'source_reference': reference, **content})
    assert bindings[sha(reference)]['version_identity_sha256'] == expected
    message = {'role': 'tool', 'tool_call_id': 'fix', 'content': json.dumps({
        'ok': True, 'result': {'patch_id': 'patch-1', 'source_reference': reference}})}
    origin = {'event_ids': ['fix-result'], 'event_types': ['ObservationEvent'], 'tool_name': 'fix_patch'}
    annotated = annotate_message(message, origin, member='member_002', artifact_bindings=bindings)
    built = build_request({'messages': [annotated]}, identity())
    sources = [s['source'] for s in built.manifest['spans'] if s.get('source')]
    assert all(s['version_sha256'] == expected for s in sources)
    assert expected != sha('patch-1')
