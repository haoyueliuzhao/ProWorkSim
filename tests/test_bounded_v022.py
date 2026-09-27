"""Controls for the actual new paired order and finite launch authority."""
import json
from pathlib import Path

import pytest

from scripts import run_bounded_v022 as bounded
from scripts.evaluate_work_v022 import paired_order


def plan(tmp_path, name):
    source = tmp_path / 'experiment.json'
    source.write_text('{}')
    return {'version': bounded.VERSION, 'line': name, 'budget_seconds': bounded.CAPS[name],
            'limits': bounded.LIMITS.copy(), 'gpu_pool': [2, 3, 4, 5, 6],
            'module': bounded.MODULES[name], 'experiment_plan': bounded.reference(source),
            'allow_parameter_updates': name == 'B1'}


def test_w1_starts_independently_but_bridge_requires_actual_frozen_guards(tmp_path):
    # A failed/absent N1 must not gate the independent W1 work measurement.
    assert bounded.validate(plan(tmp_path, 'W1')) == 'W1'
    value = plan(tmp_path, 'B1')
    n, w = tmp_path / 'n.json', tmp_path / 'w.json'
    n.write_text(json.dumps({'qualification_passed': False}))
    w.write_text(json.dumps({'status': 'complete', 'final_identity_matches_initial': True,
                            'source_unchanged': True, 'actor_steps': 0, 'critic_steps': 0,
                            'rows': []}))
    value.update(N1_qualification=bounded.reference(n), W1_qualification=bounded.reference(w))
    with pytest.raises(ValueError, match='completed N1'):
        bounded.validate(value)
    n.write_text(json.dumps({'qualification_passed': True}))
    value['N1_qualification'] = bounded.reference(n)
    with pytest.raises(ValueError, match='incomplete W1'):
        bounded.validate(value)
    record = json.loads(w.read_text())
    record['rows'] = [{'status': 'closed', 'assessment': {'eligible': True},
                       'evaluation_guard': {'learning_unchanged': True, 'rng_restored_exactly': True}} for _ in range(12)]
    w.write_text(json.dumps(record))
    value['W1_qualification'] = bounded.reference(w)
    assert bounded.validate(value) == 'B1'
    record['rows'][8]['evaluation_guard']['learning_unchanged'] = False
    w.write_text(json.dumps(record))
    value['W1_qualification'] = bounded.reference(w)
    with pytest.raises(ValueError, match='trustworthy'):
        bounded.validate(value)


def test_closed_launch_is_never_restarted_and_frozen_plan_change_is_rejected(tmp_path, monkeypatch):
    value = plan(tmp_path, 'N1')
    source = tmp_path / 'supervisor.json'
    source.write_text(json.dumps(value))
    out = tmp_path / 'runs/N1'
    out.mkdir(parents=True)
    bounded.write(out / 'state.json', {'attempted': True, 'status': 'stopped'})
    monkeypatch.setattr(bounded, 'code_identity', lambda: {'code_dirty': False})
    with pytest.raises(ValueError, match='single launch'):
        bounded.run(value, source, tmp_path / 'runs')
    Path(value['experiment_plan']['path']).write_text('{"changed":true}')
    with pytest.raises(ValueError, match='reference changed'):
        bounded.validate(value)


def test_all_paired_cases_have_same_seed_and_predeclared_alternating_order():
    cases = {'situations': [{'case_id': f'new-{i}'} for i in range(6)]}
    rows = paired_order(cases)
    assert len(rows) == 12
    for i in range(6):
        first, second = rows[2*i:2*i+2]
        assert first['case_id'] == second['case_id'] == f'new-{i}'
        assert first['sampling_seed'] == second['sampling_seed'] == 202609290100+i
        assert [first['arm'], second['arm']] == (['original_history', 'compact_work'] if i % 2 == 0 else ['compact_work', 'original_history'])
    assert sum(bounded.CAPS.values()) == 7200
