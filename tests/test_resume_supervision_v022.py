"""Restoration budget includes the original failed GPU computation."""
import json

import pytest

from scripts import run_resume_v022 as supervisor
from scripts.run_ne_v021 import reference


def test_restoration_cannot_hide_failed_cost_or_restart_a_completed_update(tmp_path):
    states = {}
    for name, status, seconds in [('N1', 'complete', 958), ('W1', 'complete', 2066), ('B1', 'stopped', 1093)]:
        path = tmp_path / f'{name}.json'
        path.write_text(json.dumps({'status': status, 'elapsed_gpu_seconds': seconds,
                                    'stop_reason': 'task_time_budget' if name == 'B1' else None}))
        states[name] = reference(path)
    experiment = tmp_path/'experiment.json'
    experiment.write_text('{}')
    plan = {'version': supervisor.VERSION, 'line_seconds': 2400, 'update_seconds': 2100,
            'other_task_seconds': 900, 'total_gpu_seconds': 7200,
            'new_training_fragments': 0, 'max_total_actor_steps': 1, 'max_total_critic_steps': 1,
            'previous_states': states, 'experiment_plan': reference(experiment)}
    assert supervisor.validate(plan) == 4117
    path = tmp_path/'B1.json'
    path.write_text(json.dumps({'status': 'stopped', 'elapsed_gpu_seconds': 2200, 'stop_reason': 'task_time_budget'}))
    states['B1'] = reference(path)
    with pytest.raises(ValueError, match='cumulative'):
        supervisor.validate(plan)
    path.write_text(json.dumps({'status': 'complete', 'elapsed_gpu_seconds': 1093, 'stop_reason': None}))
    states['B1'] = reference(path)
    with pytest.raises(ValueError, match='stopped B1'):
        supervisor.validate(plan)
