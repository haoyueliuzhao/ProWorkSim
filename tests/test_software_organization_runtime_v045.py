"""New regime collector controls; scripted CPU outputs are not model results."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.software_context_v044 import SoftwareContextTransport
from proworksim.software_feedback_v044 import OrdinaryFeedbackLedger
from proworksim.software_organization_runtime_v045 import build_runtime, close_runtime, collect_episode, run_fragment
from proworksim.software_organization_v045 import CASE_IDS, MEMBERS, build_software_collaboration_case, case_spec
from test_software_organization_runtime_v038 import CPUOwner, ScriptedWorker, action
from test_software_organization_runtime_v040 import SelectedCPUTransport, tokenize


def synthetic_runtime(tmp_path, condition, script):
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0], condition=condition), tmp_path/'case')
    identity = {'policy_version': 'cpu-v045-no-weights', 'adapter_sha256': 'cpu-fixture'}
    owner = SimpleNamespace(window_id='organization-v045:cpu-fixture', recipe={
        'temperature': 0.7, 'max_output_tokens': 2048, 'max_length': 16384},
        freeze_identity=lambda: copy.deepcopy(identity), transport=SimpleNamespace(script=script,
            feedback_ledger=OrdinaryFeedbackLedger(evidence_kind='cpu_programmed_fixture')))
    runtime, captured, interfaces = build_runtime(owner, prepared, tmp_path/'runtime', worker_factory=ScriptedWorker)
    return prepared, runtime, captured, interfaces


def test_s1_builds_one_session_and_opportunity_snapshots_do_not_invent_a_partner(tmp_path):
    prepared, runtime, captured, interfaces = synthetic_runtime(tmp_path, 'S1', {
        MEMBERS[0]: [action('read_file', path='contract.md'), action('staff_done', reason='CPU end')]})
    try:
        assert list(runtime.policies) == list(runtime.ports) == list(captured) == list(interfaces) == [MEMBERS[0]]
        assert runtime.team_budget.snapshot()['members'] == [MEMBERS[0]]
        assert not any(e['kind'] == 'model_attempt' for e in runtime.recorder.events)
        boundary = run_fragment(prepared, runtime)
        assert boundary['execution_integrity_failure'] is None
        assert boundary['role_stops'] == {MEMBERS[0]: 'completed'}
        assert prepared.world._software()['case']['condition'] == 'S1'
        snapshots = [e['payload'] for e in runtime.recorder.events if e['kind'] == 'organization_work_opportunity_v045']
        assert [(s['phase'], s['opportunity_ordinal']) for s in snapshots] == [('before', 1), ('after', 1), ('before', 2), ('after', 2)]
        for before, after in zip(snapshots[::2], snapshots[1::2]):
            assert before['opportunity_id'] == after['opportunity_id']
            assert after['team_budget']['attempts'] == before['team_budget']['attempts'] + 1
            assert after['team_budget']['charged_tokens'] == before['team_budget']['charged_tokens'] + 3
            assert before['model_visible'] is after['model_visible'] is False
            assert set(before['availability']) == {MEMBERS[0]}
    finally:
        close_runtime(runtime)


def test_f2_runtime_retirement_does_not_spawn_or_relabel(tmp_path):
    prepared, runtime, _, _ = synthetic_runtime(tmp_path, 'F2', {
        MEMBERS[0]: [action('retire_member', reason='Voluntary early stop')],
        MEMBERS[1]: [action('spawn_member', briefing='Forbidden replacement', replaces=MEMBERS[0]), action('staff_done', reason='CPU end')]})
    try:
        boundary = run_fragment(prepared, runtime)
        assert boundary['execution_integrity_failure'] is None
        assert prepared.case['condition'] == 'F2'
        assert len(runtime.policies) == 2
        assert runtime.team_budget.snapshot()['attempts'] == 3
        assert not runtime.policies[MEMBERS[1]].results[0]['ok']
        assert len(prepared.world._software()['registry']) == 2
    finally:
        close_runtime(runtime)


def test_native_sdk_o3_birth_is_same_actor_private_session_and_shared_charged_pool(tmp_path):
    pytest.importorskip('openhands.sdk')
    secret = 'PRIVATE_PARENT_ONLY_V045_CPU'
    briefing = 'Choose any useful action from the public root; no assigned role.'
    script = {MEMBERS[0]: [action('work_note', key='secret', text=secret), action('spawn_member', briefing=briefing),
        action('staff_done', reason='Parent ends')], MEMBERS[1]: [action('staff_wait', reason='No chosen work')],
        MEMBERS[2]: [action('read_file', path='contract.md'), action('staff_done', reason='Child ends')]}
    owner = CPUOwner(script)
    owner.prepare_request = lambda request: (json.dumps(request, ensure_ascii=False, sort_keys=True), None, None)
    owner.tokenizer = tokenize
    owner.transport = SelectedCPUTransport(owner)
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0], condition='O3'), tmp_path/'case')
    folder = tmp_path/'collection'
    result = collect_episode(owner, prepared, folder, sampling_seed=451, slot_id='cpu-native-O3',
        transport_factory=lambda o, d: SoftwareContextTransport(o, d, evidence_kind='cpu_programmed_fixture'))
    assert owner.phase == 'idle' and owner.window_id == 'organization-v045:cpu-native-O3'
    assert result['version'] == 'software-organization-runtime-v0.45'
    assert result['context_protocol'] == 'software-context-v0.44'
    assert result['test_feedback_protocol'] == 'paged-public-test-feedback-v0.42'
    assert result['actor_updates'] == result['critic_updates'] == result['new_backward_calls'] == 0
    assert result['R'] == 0 and result['submitted'] is False
    assert result['boundary']['execution_integrity_failure'] is None
    assert result['usage']['attempts'] == len(owner.transport.requests)
    assert result['usage']['total_tokens'] == sum(body['usage']['total_tokens'] for body in owner.transport.responses)
    assert result['team_budget']['model']['limits'] == {'max_decisions': 128, 'max_attempts': 128, 'max_total_tokens': 500000}
    assert result['team_budget']['model']['members'] == list(MEMBERS[:3])
    assert all(body['actor_identity'] == owner.freeze_identity() for body in owner.transport.responses)
    events = [json.loads(line) for line in (folder/'experience.jsonl').read_text().splitlines()]
    born = [e for e in events if e['kind'] == 'organization_session_born' and e['worker_id'] == MEMBERS[2]]
    assert len(born) == 1 and born[0]['payload']['private_history_copied'] is False
    assert born[0]['payload']['new_budget_granted'] is False
    child_requests = []
    for request in owner.transport.requests:
        observation = next(json.loads(m['content'])['observation'] for m in reversed(request['messages'])
            if m['role'] == 'user' and '"observation"' in m.get('content', ''))
        if observation['actor_id'] == MEMBERS[2]:
            child_requests.append(request)
            assert len(observation['initial_diagnostics']) == 2
    assert child_requests and secret not in json.dumps(child_requests)
    assert briefing in json.dumps(child_requests[0])
    assert not any(m['role'] == 'assistant' for m in child_requests[0]['messages'])
    assert prepared.world._software()['registry'][MEMBERS[2]]['origin'] == 'member_request'
    opportunities = [e['payload'] for e in events if e['kind'] == 'organization_work_opportunity_v045']
    assert len(opportunities) == 2 * len(result['boundary']['outcomes'])
    assert all(e['model_visible'] is False for e in opportunities)
    evidence = json.loads((folder/'organization-evidence.json').read_text())
    assert len(evidence['work_opportunity_snapshots']) == len(opportunities)
    assert all(e['payload']['phase'] in {'before','after'} for e in evidence['work_opportunity_snapshots'])
