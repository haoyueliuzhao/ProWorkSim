import copy
import hashlib
import json

from proworksim.software_input_provenance_v156 import AnnotatedText
from proworksim.software_sdk_input_sources_v159 import annotate_message


def fixture():
    original = json.dumps({'public_format_feedback': {'model_call_id': 'call-1',
        'status': 'decision_rejected', 'reason': 'Exactly one native tool call',
        'original_response_id': 'response-1', 'world_action_executed': False}})
    compact = json.dumps({'public_format_feedback': {'model_call_id': 'call-1',
        'status': 'decision_rejected', 'reason': 'Exactly one native tool call',
        'world_action_executed': False}})
    event = {'id': 'sdk-1', 'kind': 'MessageEvent', 'source': 'user',
             'llm_message': {'role': 'user', 'content': [{'type': 'text', 'text': original}]}}
    origin = {'event_ids': ['sdk-1'], 'event_types': ['MessageEvent'], 'events': [event]}
    record = {'feedback_id': 'member_001:call-1', 'runner_source': 'model_format_feedback',
        'source_event_id': 'runner-event:1', 'member_id': 'member_001', 'call_id': 'call-1',
        'association': {'worker_id': 'member_001'}, 'original_message': {'role': 'user', 'content': original},
        'visible_message': {'role': 'user', 'content': compact},
        'original_content_sha256': hashlib.sha256(original.encode()).hexdigest()}
    return original, compact, origin, {'member_001:call-1': record}


def test_registered_feedback_and_exact_compact_projection_share_the_producer():
    original, compact, origin, records = fixture()
    for content in (original, compact):
        output = annotate_message({'role': 'user', 'content': content}, origin,
            member='member_001', episode_id='episode', feedback_records=records)
        assert isinstance(output['content'], AnnotatedText)
        assert ''.join(p.text for p in output['content'].segments) == content
        assert {p.source.category for p in output['content'].segments} == {'Tool-feedback'}
        assert {p.source.origin_event_id for p in output['content'].segments} == {'runner-event:1'}


def test_same_json_field_or_another_members_registry_does_not_grant_authority():
    original, _, origin, records = fixture()
    message = {'role': 'user', 'content': original}
    for registry in ({}, {'member_002:call-1': records['member_001:call-1']}):
        output = annotate_message(message, origin, member='member_001', feedback_records=registry)
        assert output['content'] == original
    corrupted = copy.deepcopy(origin)
    corrupted['events'][0]['llm_message']['content'][0]['text'] += ' '
    output = annotate_message(message, corrupted, member='member_001', feedback_records=records)
    assert output['content'] == original
