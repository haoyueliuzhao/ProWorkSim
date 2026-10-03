"""Finite-stage isolation and no-support termination, without model sampling."""

import copy

import pytest

from proworksim.storage import atomic_write, json_bytes
from scripts.software_allocation_v029 import (
    LIMITS, RoutedTransport, inventories, next_stage, require_actual_update, window_spec,
)


def put(path, value):
    atomic_write(path, json_bytes(value))


def test_source_purpose_and_window_are_frozen():
    from proworksim.software_runtime_v029 import _validate_window
    rows = inventories()
    assert len(rows['support']) == 8
    assert len({row['sampling_seed'] for group in rows.values() for row in group}) == 18
    spec = window_spec('p1', rows['support'], 'policy_training', 'current_policy_collection')
    assert _validate_window(spec) == rows['support']
    assert spec['budget'] == {'max_slots': 8, 'max_model_calls': 768}
    bad = copy.deepcopy(spec)
    bad['slots'][0]['case_id'] = 'schema-catalog'
    with pytest.raises(ValueError, match='purpose'):
        _validate_window(bad)
    bad = copy.deepcopy(spec)
    bad['mode'] = 'frozen_development'
    with pytest.raises(ValueError, match='purpose'):
        _validate_window(bad)
    assert LIMITS['task_seconds']['training'] is None


def test_support_stop_never_fabricates_baseline_update(tmp_path):
    put(tmp_path / 'support/actual/support-gate.json', {'status': 'no_configurable_support'})
    assert next_stage('support', {'support': {'status': 'complete'}}, tmp_path) == ('no_configurable_support', [])
    assert next_stage('support', {'support': {'status': 'stopped'}}, tmp_path) == ('incomplete_execution', [])
    with pytest.raises(ValueError, match='unfinished'):
        next_stage('support', {'support': {'status': 'running'}}, tmp_path)


def test_shared_B_first_then_every_original_direction(tmp_path):
    put(tmp_path / 'support/actual/support-gate.json', {'status': 'ready'})
    put(tmp_path / 'support/actual/allocation-plan.json', {'candidates': {'B': {}, 'G-a': {}, 'I-b': {}}})
    assert next_stage('support', {'support': {'status': 'complete'}}, tmp_path) == ('baseline_trial', ['trial-B'])
    put(tmp_path / 'trial-B/actual/development-receipt.json', {'outcomes': [{'utility': 0}]})
    assert next_stage('baseline_trial', {'trial-B': {'status': 'complete'}}, tmp_path) == ('trials', ['trial-G-a', 'trial-I-b'])
    put(tmp_path / 'trial-B/actual/development-receipt.json', {'outcomes': [{'utility': None}]})
    assert next_stage('baseline_trial', {'trial-B': {'status': 'complete'}}, tmp_path) == ('incomplete_development', [])


def test_preconstructed_workers_use_the_active_slot_transport():
    router = RoutedTransport()
    workers = [router, router]
    with pytest.raises(RuntimeError, match='slot'):
        router.complete({})

    class Sink:
        def __init__(self):
            self.seen = []

        def complete(self, request, **kwargs):
            self.seen.append((request, kwargs))
            return len(self.seen)

    first, second = Sink(), Sink()
    router.inner = first
    workers[0].complete({'slot': 0}, timeout_seconds=1)
    router.inner = second
    workers[1].complete({'slot': 1}, timeout_seconds=1)
    assert first.seen == [({'slot': 0}, {'timeout_seconds': 1})]
    assert second.seen == [({'slot': 1}, {'timeout_seconds': 1})]


def test_zero_step_probability_or_gradient_rejection_cannot_become_a_candidate():
    require_actual_update({'status': 'updated', 'actor_optimizer_steps': 1, 'critic_optimizer_steps': 1})
    # The original learner may keep an exactly zero-gradient critic unchanged.
    require_actual_update({'status': 'updated', 'actor_optimizer_steps': 1, 'critic_optimizer_steps': 0})
    for status, actor_steps, critic_steps in (
        ('zero_step_probability_mismatch', 0, 0),
        ('zero_step_gradient_probability_mismatch', 0, 0),
        ('zero_step_zero_actor_advantage_or_gradient', 0, 1),
        ('updated', 1, 2),
    ):
        with pytest.raises(ValueError, match='actual complete'):
            require_actual_update({'status': status, 'actor_optimizer_steps': actor_steps,
                                   'critic_optimizer_steps': critic_steps})
