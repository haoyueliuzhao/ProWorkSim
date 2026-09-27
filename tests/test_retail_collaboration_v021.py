"""Bounded collaboration boundaries; no GPU/API and no model-support counts."""
from collections import Counter

import pytest

from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.episode import begin_episode, finish_episode
from proworksim.online_collection import run_fragment
from proworksim.staff_runtime import PolicyBoundaryError, StaffRuntime
from proworksim.storage import digest, json_bytes
from proworksim.templates import retail_collaboration_v021 as c
from scripts.retail_collaboration_experiment_v021 import run_control


def test_e6_and_b_prepared_qualities_share_public_policy(tmp_path):
    catalog = c.registry()['situations']
    assert Counter(x['task'] for x in catalog) == {'implement': 2, 'review': 2, 'joint_a': 1, 'joint_b': 1}
    assert sum(sum(x['role_decision_limits'].values()) for x in catalog) == 122
    values = []
    for quality in c.retail_balanced.QUALITIES:
        p = c.build_case(c.cpu_variant(quality), tmp_path / quality)
        values.append({'reward': p.reward_spec, 'tasks': [x['config']['task'] for x in p.scenario['roles']],
                       'sources': {alias: digest(p.world.store.content(p.world.state['artifacts'][p.world.state['workspaces']['TEAM'][alias]])) for alias in ('data', 'basis', 'audit_basis')}})
        assert p.prefix['credited_to_current_actor'] is False
        assert len(p.world.state['work_items'][c.WORK]['submissions']) == 1
        for role in p.active_roles:
            observation = json_bytes(p.world.session(role, 'TEAM').observe()).decode()
            assert all(label not in observation for label in ('wrong_count', 'wrong_amount', 'prepared_submission'))
    assert len({json_bytes(x) for x in values}) == 1


def test_actual_feedback_repair_and_delivery_without_use(tmp_path):
    _, positive = run_control(c.cpu_variant('wrong_count'), tmp_path / 'repair', 'feedback')
    assert positive['completed'] and positive['reward'] == 1
    assert positive['facts']['initial_correct'] is False
    assert positive['facts']['current_repair_build']['current_actor_build']
    assert positive['mapper']['class_id'] == 'evidenced_review_then_targeted_repair'
    a = next(x for x in c.registry()['situations'] if x['task'] == 'joint_a')
    _, incomplete = run_control(a, tmp_path / 'unused', 'delivered_unused')
    assert incomplete['eligible'] and incomplete['reward'] == .2 and not incomplete['completed']


class BoundaryPolicy:
    """Explicit fake control exercises the real StaffRuntime boundary only."""
    def __init__(self, status):
        self.status = status
        self.config = {'fake_cpu_control': status}

    def decide(self, context):
        raise PolicyBoundaryError(self.status, 'Explicit CPU fake boundary', memory={})


@pytest.mark.parametrize('status,eligible', [('model_format_error', True), ('model_service_error', False)])
def test_format_termination_keeps_known_zero_service_remains_unknown(tmp_path, status, eligible):
    p = c.build_case(c.cpu_variant('correct'), tmp_path / 'case')
    recorder = ExperienceRecorder()
    ports = {r: capture_port(p.world.session(r, 'TEAM'), []) for r in p.active_roles}
    runtime = StaffRuntime(ports, {r: BoundaryPolicy(status) for r in p.active_roles}, recorder=recorder)
    episode = tmp_path / 'episode'
    begin_episode(p.world, episode, experience=recorder.snapshot(), work_ids=[c.WORK], scenario=p.scenario, policies=runtime.policy_identities)
    terminal = run_fragment(p, runtime)
    finish_episode(p.world, episode, experience=recorder.snapshot(), termination=terminal)
    result = c.assess_episode(episode)
    assert result['eligible'] is eligible
    assert result['reward'] == (0 if eligible else None)
    assert set(terminal['role_stops']) == {'implementer', 'reviewer'}
    assert len(terminal['outcomes']) == 2  # One role boundary does not cancel the other.


def test_format_boundary_after_real_joint_work_retains_known_success(tmp_path):
    from scripts.retail_work_experiment_v015 import PublicWitnessPolicy

    class FinishWithFormatBoundary(PublicWitnessPolicy):
        def decide(self, context):
            result = super().decide(context)
            if result['kind'] == 'done':
                raise PolicyBoundaryError('model_format_error', 'Explicit fake late format boundary', memory=result['memory'])
            return result

    case = next(x for x in c.registry()['situations'] if x['task'] == 'joint_a')
    p = c.build_case(case, tmp_path / 'case')
    recorder = ExperienceRecorder()
    ports = {r: capture_port(p.world.session(r, 'TEAM'), []) for r in p.active_roles}
    policies = {r: FinishWithFormatBoundary(role=r, task='pair', limit=case['role_decision_limits'][r]) for r in p.active_roles}
    runtime = StaffRuntime(ports, policies, recorder=recorder)
    episode = tmp_path / 'episode'
    begin_episode(p.world, episode, experience=recorder.snapshot(), work_ids=[c.WORK], scenario=p.scenario, policies=runtime.policy_identities)
    terminal = run_fragment(p, runtime)
    finish_episode(p.world, episode, experience=recorder.snapshot(), termination=terminal)
    result = c.assess_episode(episode)
    assert set(terminal['role_stops'].values()) == {'model_format_error'}
    assert result['eligible'] and result['completed'] and result['reward'] == 1
