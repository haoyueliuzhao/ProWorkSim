"""Real WorldCore with explicit fake responses; not model performance evidence."""
import copy
import json
from pathlib import Path

import pytest

from proworksim.retail_project_collection import collect_project_episode
from proworksim.retail_project_rewards import assess_project_episode
from proworksim.scenarios import ScenarioDeployment
from proworksim.storage import read_json
from proworksim.templates.online_work import PreparedOnlineCase
from proworksim.templates.retail_projects_v017 import case_spec, scenario
from proworksim.world_core import WorldCore
from scripts.retail_project_model_v017 import execute
from scripts.retail_projects_experiment_v017 import run_case


class ExplicitOwner:
    recipe = {'temperature': 0.7, 'max_output_tokens': 128, 'max_length': 16384}
    actor_steps = critic_steps = 0

    def __init__(self, mode='format'):
        self.transport = self
        self.mode, self.calls, self.seeds, self.responses = mode, {}, [], []

    def freeze_identity(self):
        return {'policy_version': 'explicit-v018-response-fixture', 'fixture': True}

    def complete(self, request, *, timeout_seconds):
        observed = next(json.loads(m['content'])['observation'] for m in reversed(request['messages'])
                        if m['role'] == 'user' and 'observation' in json.loads(m['content']))
        role = observed['actor_id']
        self.calls[role] = self.calls.get(role, 0) + 1
        if role == 'source_steward' and self.mode == 'service':
            body = {'error': {'code': 'explicit_fixture_service_unavailable'}, 'actor_identity': self.freeze_identity()}
            result = {'http_status': 503, 'body': body, 'raw_body': json.dumps(body)}
        else:
            malformed = role == 'source_steward' and self.mode in {'format', 'missing_identity'}
            message = {'role': 'assistant', 'content': 'not a valid native tool call or control JSON'} if malformed else {
                'role': 'assistant', 'content': None, 'tool_calls': [{'id': role + '-done-' + str(self.calls[role]),
                'type': 'function', 'function': {'name': 'staff_done', 'arguments': '{"reason":"explicit CPU fixture stop"}'}}]}
            if role == 'source_steward' and self.mode == 'world_rejection' and self.calls[role] == 1:
                message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'exact-missing-alias', 'type': 'function',
                           'function': {'name': 'read_alias', 'arguments': '{"alias":"__known_missing_alias__"}'}}]}
            if role == 'integrator' and self.mode == 'submit_integration_once' and self.calls[role] == 1:
                work_id = next(wid for wid, w in observed['work_items'].items() if w['is_current'] and w['status'] != 'accepted')
                message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'actual-fixed-initial-integration', 'type': 'function',
                           'function': {'name': 'submit', 'arguments': json.dumps({'work_id': work_id, 'artifacts': ['code', 'result']})}}]}
            body = {'id': role + '-' + str(self.calls[role]), 'actor_identity': self.freeze_identity(),
                    'model': 'explicit-v018-response-fixture', 'object': 'chat.completion', 'created': 0,
                    'choices': [{'message': message, 'finish_reason': 'stop' if malformed else 'tool_calls'}],
                    'usage': {'prompt_tokens': 2, 'completion_tokens': 2, 'total_tokens': 4},
                    'token_trace': {'input_ids': [11, 12], 'output_ids': [21, 22], 'raw_output_ids': [21, 22],
                                    'behavior_logprobs': [-0.1, -0.2], 'raw_behavior_logprobs': [-0.1, -0.2], 'fixture_only': True}}
            if self.mode == 'missing_identity' and role == 'source_steward':
                del body['actor_identity']
            result = {'http_status': 200, 'body': body, 'raw_body': json.dumps(body)}
        self.responses.append(copy.deepcopy(result))
        return result

    def capture_evaluation_state(self):
        return 'explicit-nonnumeric-fixture'

    def begin_window(self, window_id):
        self.window_id = window_id

    def reseed(self, seed, *, label):
        self.seeds.append((seed, label))

    def finish_evaluation(self, entries, output):
        assert entries == []
        return {'fixture_only': True, 'actor_optimizer_steps': 0, 'critic_optimizer_steps': 0}

    def finish_evaluation_guard(self, snapshot):
        assert snapshot == 'explicit-nonnumeric-fixture'
        return {'fixture_only': True, 'learning_unchanged': True, 'rng_restored_exactly': True}


def completed_preparation(root):
    """A real CPU-delivered inherited world; never called model-created work."""
    report = run_case(root)
    assert report['assessment']['reward'] == 1
    case = case_spec('retail-projects-v17-static')
    spec = scenario(case)
    deployment = ScenarioDeployment(spec=spec, world=WorldCore(root / 'world'))
    return PreparedOnlineCase(deployment, case, spec['variation']['project_reward'], read_json(root / 'preparation.json'))


def test_complete_raw_format_failure_is_known_and_all_planned_cases_continue(tmp_path):
    owner = ExplicitOwner()
    plan = read_json(Path(__file__).resolve().parents[1] / 'examples/retail-projects-v17/model-evaluation-plan.json')
    output = tmp_path / 'study'
    output.mkdir()
    report = execute(owner, {'selected_candidate': 'explicit-fixture', 'selected_harness': 'native_v15'}, output, plan)
    assert report['status'] == 'complete' and len(report['episodes']) == 4
    assert [s[0] for s in owner.seeds] == [s['sampling_seed'] for s in plan['slots']]
    assert owner.calls == {'source_steward': 8, 'metrics_engineer': 4, 'customer_analyst': 4, 'integrator': 4}
    for slot in plan['slots']:
        result = read_json(output / slot['slot_id'] / 'result.json')
        assert result['termination']['role_stops']['P0'] == 'model_format_error'
        assert result['record_trust']['trusted'] is True
        assert result['independent_assessment']['reward'] == result['assessment']['reward'] == 0
        assert result['diagnostics']['initial_delivery']['business_completed'] is False
        if slot['case_id'].endswith('change'):
            assert result['diagnostics']['change']['triggered'] is False
            assert result['diagnostics']['change']['handling_measured'] is False
            assert result['diagnostics']['breakpoint'] == 'initial_delivery_not_completed_change_not_entered'


def test_format_error_after_inherited_real_delivery_preserves_known_one(tmp_path, monkeypatch):
    prepared = completed_preparation(tmp_path / 'real_cpu_inherited_world')
    monkeypatch.setattr('proworksim.retail_project_collection.build_project_case', lambda case, root: prepared)
    result = collect_project_episode(ExplicitOwner(), 'retail-projects-v17-static', tmp_path / 'later_format_episode', harness='native_v15')
    assert result['record_trust']['trusted'] is True
    assert result['independent_assessment']['reward'] == result['assessment']['reward'] == 1
    assert result['termination']['role_stops']['P0'] == 'model_format_error'
    assert result['diagnostics']['initial_delivery']['inherited_fixed_deliveries'] is True


@pytest.mark.parametrize('mode', ['service', 'missing_identity'])
def test_service_or_identity_gap_remains_unknown(tmp_path, mode):
    result = collect_project_episode(ExplicitOwner(mode), 'retail-projects-v17-static', tmp_path / mode, harness='native_v15')
    assert result['independent_assessment']['reward'] == 0
    assert result['record_trust']['trusted'] is False
    assert result['assessment']['reward'] is None
    assert result['assessment']['eligible'] is False
    # Other roles still received their own bounded opportunity before close.
    assert set(result['termination']['role_stops']) == {'P0', 'P1', 'P2', 'P3'}
    assert assess_project_episode(tmp_path / mode / 'episode')['reward'] == 0



def test_exact_world_refusal_remains_known_but_missing_receipt_capture_does_not(tmp_path):
    from proworksim.retail_project_rewards import assess_collection_records, combine_project_measurement
    owner = ExplicitOwner('world_rejection')
    result = collect_project_episode(owner, 'retail-projects-v17-static', tmp_path / 'world-refusal', harness='native_v15')
    assert result['record_trust']['trusted'] is True
    assert result['record_trust']['verified_world_calls'] == 1
    assert result['assessment']['reward'] == 0
    captures = read_json(tmp_path / 'world-refusal/capture.json')
    captures['P0'] = [r for r in captures['P0'] if r['kind'] != 'tool_call']
    damaged = assess_collection_records(tmp_path / 'world-refusal/episode', captures, owner.freeze_identity())
    assert damaged['trusted'] is False
    assert any(i['kind'] == 'independent_world_capture_differs' for i in damaged['issues'])
    assert combine_project_measurement(result['independent_assessment'], damaged)['reward'] is None


def test_sdk_actual_change_receipt_and_budget_are_reported_without_new_business_work(tmp_path, monkeypatch):
    pytest.importorskip('openhands.sdk')
    prepared = completed_preparation(tmp_path / 'inherited_initial_delivery')
    # Leave a real, correctly built initial integration awaiting its actual
    # fixed submission. Other roles can say done before that submit triggers
    # the declared client change. No live state is edited behind WorldCore.
    changed = prepared.world.session('operator', 'P3').call('revise', work_id='P3::build',
        updates={'goal': 'Initial integration still requires a new fixed delivery'}, reason='Explicit CPU initial-delivery fixture')
    assert changed['ok']
    from proworksim.core.work import current_id
    work_id = current_id(prepared.world.state, 'P3::build')
    port = prepared.world.session('integrator', 'P3')
    for alias in ('metrics', 'analysis', 'basis'):
        read = port.call('read_alias', alias=alias, work_id=work_id)
        assert read['ok']
        assert port.call('adopt', alias=alias, **read['result']['reference'], policy='current_published', work_ids=[work_id])['ok']
    built = port.call('sql_build', work_id=work_id, code_alias='code', output_alias='result', input_aliases=['metrics', 'analysis', 'basis'])
    assert built['ok'] and built['result']['execution_status'] == 'success'
    prepared.case = case_spec('retail-projects-v17-change')
    prepared.deployment.spec = scenario(prepared.case)
    prepared.reward_spec = prepared.deployment.spec['variation']['project_reward']
    monkeypatch.setattr('proworksim.retail_project_collection.build_project_case', lambda case, root: prepared)
    owner = ExplicitOwner('submit_integration_once')
    result = collect_project_episode(owner, prepared.case['case_id'], tmp_path / 'actual_change_fixture', harness='openhands_v16')
    assert result['record_trust']['trusted'] is True
    diagnostic = result['diagnostics']
    assert diagnostic['initial_delivery']['inherited_fixed_deliveries'] is False
    assert diagnostic['initial_delivery']['business_completed'] is True
    assert diagnostic['change']['triggered'] is True and diagnostic['change']['handling_measured'] is True
    assert result['assessment']['reward'] == 0  # New fixed obligations were not performed by the stop-only fixture.
    for role in ('P1', 'P2', 'P3'):
        row = diagnostic['roles'][role]
        assert row['observed_in_actual_model_input'] is True
        assert row['same_sdk_conversation'] is True
        if role in {'P1', 'P2'}:
            assert row['reactivation_preserved_budget'] is True
        else:
            assert row['reactivation_count'] == 0  # Still active, no done latch to release.
        assert row['decisions_used_before_receipt'] == 1
        assert row['remaining_decisions_at_receipt'] == prepared.case['role_decision_limits'][role] - 1
        assert row['successor_fixed_delivery_completed'] is False
    assert owner.calls == {'source_steward': 1, 'metrics_engineer': 2, 'customer_analyst': 2, 'integrator': 2}
