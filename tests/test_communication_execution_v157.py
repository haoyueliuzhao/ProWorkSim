"""Necessary CPU controls for real message publication, projections and ACL."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_communication_execution_v157 import (
    CommunicationBridge, source_facts, source_from_event, RealCommunicationRenderer, bind_world,
)
from proworksim.software_communication_pilot_v156 import FIELDS, ImmutableCommunicationStore
from proworksim.software_role_baseline_runtime_v157 import prepare_schema_inventory
from proworksim.software_sdk_input_sources_v157 import observation_text, annotate_message
from proworksim.software_role_baseline_world_v141 import PROJECT, SoftwareCollaborationPort


ROOT = Path(__file__).resolve().parents[1]


def fixture(folder):
    spec = importlib.util.spec_from_file_location('actual_roles_cpu', ROOT/'tests/test_role_baseline_world_v141.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare(folder, 'REVIEW2')


class Owner:
    window_id = 'cpu-v157:team'
    spec = {'id': 'REVIEW2'}
    def __init__(self, remove_critical=False):
        self.calls, self.remove = [], remove_critical
    def compress(self, payload, identity):
        self.calls.append((copy.deepcopy(payload), identity))
        data = json.loads(payload['messages'][1]['content'])
        selected = {field: [f['fact_id'] for f in data['facts'] if f['field'] == field and
                           (f['critical'] if not self.remove else not f['critical'])] for field in FIELDS}
        return {'id': 'cpu-compressor', 'model': 'cpu-no-api', 'system_fingerprint': 'scripted',
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({
                'source_id': data['source_id'], 'version_hash': data['version_hash'], 'fields': selected})}}],
            'usage': {'prompt_tokens': 111, 'completion_tokens': 22, 'total_tokens': 133}}


def test_complete_spans_protect_negative_test_and_version():
    raw = 'Context: an ordinary explanation.\nTests: pytest failed at sample.py:2.\nNext action: review patch-1.'
    facts, complete, _ = source_facts(raw)
    assert complete and len(facts) == 3
    assert not facts[0]['critical']
    assert all(f['critical'] for f in facts[1:])
    assert all(raw[f['start_character']:f['end_character']] for f in facts)
    natural, ok, _ = source_facts('Changed internal handling because a simpler implementation avoids duplicated branches.\nPlease review the candidate.')
    assert ok and natural[0]['field'] == 'change' and natural[0]['critical'] is False
    assert natural[1]['critical'] is True
    assert source_facts('Things are surprisingly strange here.')[1] is False
    assert source_facts('```python\nprint(1)\n```')[1] is False


@pytest.mark.parametrize('condition', ['C0', 'C1', 'C2'])
def test_actual_world_projection_cache_and_bounded_fallback(tmp_path, condition):
    prepared, ports, call, _ = fixture(tmp_path/'case')
    owner = Owner()
    bridge = CommunicationBridge(prepared.world, owner, tmp_path/'communication', condition, lambda s: len(s.split()))
    bind_world(prepared.world, bridge)
    text = 'Context: ' + 'ordinary background explanation '*20 + '\nTests: pytest failed.\nNext action: review patch-1.'
    result = call('member_001', 'send_message', recipient='member_002', task_id='root_goal', body=text)
    assert result['ok'], result
    bridge.sync()
    observation = SoftwareCollaborationPort(prepared.world.session('member_002', PROJECT), 'member_002').observe()
    projected = bridge.project(observation, 'member_002')
    again = bridge.project(observation, 'member_002')
    assert projected == again
    item = projected['messages'][0]
    if condition == 'C0':
        assert item['body'] == text[:500] and len(owner.calls) == 0
    else:
        assert 'pytest failed' in item['body'] and 'ordinary background' not in item['body']
        assert len(owner.calls) == 1
        assert item['communication']['representation'] != 'raw'
    record = bridge.records[item['sequence']]
    l2 = bridge.read('member_002', PROJECT, item['sequence'], 'L2', record['ref']['version_hash'])
    l3 = bridge.read('member_002', PROJECT, item['sequence'], 'L3', record['ref']['version_hash'])
    assert 'pytest failed' in l2['text'] and 'ordinary background' not in l2['text']
    assert l3['text'] == text
    assert bridge.read('member_002', PROJECT, item['sequence'])['body'] == text
    with pytest.raises(ValueError):
        bridge.read('member_002', PROJECT, item['sequence'], 'L3', '0'*64)
    assert bridge.read('member_001', PROJECT, item['sequence'], 'L3', record['ref']['version_hash'])['text'] == text
    assert bridge.authorize(record['ref'], 'unrelated_member', 'L3') is False


def test_missing_critical_retains_paid_usage_raw_preview_and_ambiguous_no_call(tmp_path):
    prepared, _, call, _ = fixture(tmp_path/'case')
    owner = Owner(remove_critical=True)
    bridge = CommunicationBridge(prepared.world, owner, tmp_path/'communication', 'C2', lambda s: len(s.split()))
    bind_world(prepared.world, bridge)
    text = 'Tests: pytest failed.\nNext action: review patch-1.'
    assert call('member_001', 'send_message', recipient='member_002', task_id='root_goal', body=text)['ok']
    obs = SoftwareCollaborationPort(prepared.world.session('member_002', PROJECT), 'member_002').observe()
    result = bridge.project(obs, 'member_002')['messages'][0]
    rendered = next(iter(bridge.rendered.values()))
    assert result['body'] == text and rendered['fallback_reason'] == 'critical_fact_omitted'
    assert rendered['compressor_attempts'][0]['usage']['total_tokens'] == 133
    assert call('member_001', 'send_message', recipient='member_002', task_id='root_goal', body='Something rather unusual happened.')['ok']
    obs = SoftwareCollaborationPort(prepared.world.session('member_002', PROJECT), 'member_002').observe()
    bridge.project(obs, 'member_002')
    assert len(owner.calls) == 1


def test_same_schema_and_explicit_compressed_and_retrieved_sources():
    inventory = prepare_schema_inventory()['schemas']
    assert inventory['C0'] == inventory['C1'] == inventory['C2']
    assert len(inventory['C0']['member_001']) == 38
    message = {'sequence': 7, 'actor_id': 'member_001', 'recipient': 'member_002',
        'body': 'test_status: Tests failed.', 'communication': {'source_id': 'team:world-message:7:body',
        'version_hash': 'a'*64, 'representation': 'L0_L1'}}
    tagged = observation_text(json.dumps({'role_task': 'task', 'observation': {'messages': [message]}}),
        event_id='sdk:obs', member='member_002', episode_id='team', artifact_bindings={
            '_communication_v157': {'team:world-message:7:body': {'version_hash': 'a'*64,
                'representation': 'L0_L1', 'text': message['body'], 'segments': [
                    {'text': 'test_status: ', 'fact_id': None}, {'text': 'Tests failed.', 'fact_id': 'f001'}]}}})
    peers = [s.source for s in tagged.segments if s.source and s.source.category == 'Peer-message']
    assert peers and all(s.transformation == 'compressed' for s in peers)
    assert all(s.parent_source_ids == ('team:world-message:7:body',) for s in peers)
    result = {'ok': True, 'result': {'kind': 'communication_pull', 'source_id': 'team:world-message:7:body',
        'version_hash': 'a'*64, 'sequence': 7, 'actor_id': 'member_001', 'recipient': 'member_002',
        'level': 'L3', 'text': 'Exact original text.'}}
    tagged = annotate_message({'role': 'tool', 'content': json.dumps(result), 'name': 'read_work_event'},
        {'event_ids': ['read'], 'event_types': ['ObservationEvent']}, member='member_002', episode_id='team')
    reads = [s.source for s in tagged['content'].segments if s.source and s.source.category == 'Retrieved']
    assert reads and reads[0].origin_member_id == 'member_001'
    assert reads[0].parent_source_ids[0] == 'team:world-message:7:body'


def test_compressor_unknown_retains_reservation_and_finish_review_can_close(tmp_path):
    from proworksim.software_benchmark_deepseek_api_v157 import APIUncertainFailure
    from proworksim.software_communication_finish_v157 import FinishReviewPolicy, require_known_usage
    from proworksim.software_benchmark_finish_review_v117 import FINISH_REVIEW
    prepared, _, call, _ = fixture(tmp_path/'case')
    owner = Owner()
    provider = {'source': 'one_shared_physical_provider_sqlite', 'team_id': owner.window_id,
        'known_actual_tokens': 281, 'uncertain_reserved_tokens': 768, 'available_tokens': 5_000_000-1049,
        'token_limit': 5_000_000, 'inflight_count': 0,
        'per_usage_id': {'compressor': {'uncertain_reserved_tokens': 768}}}
    owner.shared_provider_budget = lambda: copy.deepcopy(provider)
    def failed(payload, identity):
        raise APIUncertainFailure('scripted_transport_unknown_after_send')
    owner.compress = failed
    bridge = CommunicationBridge(prepared.world, owner, tmp_path/'communication', 'C2', lambda s: len(s.split()))
    bind_world(prepared.world, bridge)
    assert call('member_001', 'send_message', recipient='member_002', task_id='root_goal', body='Please review patch-1.')['ok']
    obs = SoftwareCollaborationPort(prepared.world.session('member_002', PROJECT), 'member_002').observe()
    result = bridge.project(obs, 'member_002')['messages'][0]
    assert result['body'] == 'Please review patch-1.'
    assert result['communication']['fallback_reason'] == 'compressor_transport_failed_accounting_retained'
    snapshot = {'complete_actual_tokens': None, 'known_actual_tokens': 281, 'inflight': None,
        'uncertain_reserved_tokens': 768, 'authoritative_provider_snapshot': provider,
        'attempts': 2, 'decisions': 1, 'token_limit': 5_000_000,
        'all_model_attempt_limit': 512, 'agent_decision_limit': 512}
    policy = FinishReviewPolicy(started={'started': 0, 'soft_at': 21600, 'hard_at': 23400},
        limits={'input_plus_output_tokens': 5_000_000, 'all_model_attempts': 512, 'agent_decisions': 512,
            'soft_seconds': 21600, 'hard_seconds': 23400}, clock=lambda: 5)
    offered = policy.offer(snapshot, intent_id='first', reason='Done')
    assert offered['permitted'] and offered['message'] == FINISH_REVIEW
    assert policy.offer(snapshot, intent_id='second', reason='Checked')['accepted_finish']
    assert snapshot['complete_actual_tokens'] is None and snapshot['uncertain_reserved_tokens'] == 768
    broken = copy.deepcopy(snapshot)
    broken['authoritative_provider_snapshot']['per_usage_id'] = {'agent': {'uncertain_reserved_tokens': 768}}
    with pytest.raises(RuntimeError):
        require_known_usage(broken)
