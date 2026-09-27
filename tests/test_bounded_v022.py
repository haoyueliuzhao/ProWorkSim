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


def test_w1_starts_independently_but_bridge_requires_separate_exact_qualification(tmp_path, monkeypatch):
    from proworksim import bridge_admission_v022 as admission

    assert bounded.validate(plan(tmp_path, 'W1')) == 'W1'
    value = plan(tmp_path, 'B1')
    calls = []
    def rejected(value):
        calls.append(value)
        raise ValueError('N1 and token projection not qualified')
    monkeypatch.setattr(admission, 'validate_bridge_qualification', rejected)
    with pytest.raises(ValueError, match='token projection'):
        bounded.validate(value)
    assert calls == [value]
    monkeypatch.setattr(admission, 'validate_bridge_qualification', lambda value: {'passed': True})
    assert bounded.validate(value) == 'B1'


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
