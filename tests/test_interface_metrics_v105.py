"""Cost denominators and missing telemetry must survive partial live runs."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


metrics = module('summarize_interface_panel_v105')
prepare = module('prepare_interface_panel_v105')


def test_frozen_panel_reuses_only_task_identities_and_new_pair_seeds():
    source = json.loads(prepare.SOURCE.read_bytes())
    panel = prepare.make_panel(source)
    assert panel['task_ids'] == source['task_ids']
    assert len(panel['rows']) == len({r['slot_id'] for r in panel['rows']}) == 100
    assert {r['slot_index'] for r in panel['rows']} == set(range(7000, 7100))
    assert len(panel['repository_counts']) == 12 and set(prepare.REQUESTS) <= set(panel['task_ids'])
    for task in panel['task_ids']:
        pair = [r for r in panel['rows'] if r['instance_id'] == task]
        assert {r['arm'] for r in pair} == {'REF', 'PROJECT'}
        assert len({r['seed'] for r in pair}) == 1
        assert all(r['thinking'] is False and r['provider_seed_sent'] is False for r in pair)
    assert panel['condition_configurations']['REF']['inference'] == panel['condition_configurations']['PROJECT']['inference']


def test_optional_reasoning_and_cache_are_not_fabricated():
    value = metrics.tokens({'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110})
    assert value['reasoning_tokens'] is value['cache_hit_tokens'] is value['cache_miss_tokens'] is None
    with pytest.raises(ValueError):
        metrics.tokens({'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110,
                        'prompt_cache_hit_tokens': 60, 'prompt_cache_miss_tokens': 50})


def test_live_unresolved_usage_and_auxiliary_spend_do_not_bias_task_means(tmp_path):
    panel = prepare.make_panel(json.loads(prepare.SOURCE.read_bytes()))
    ref = next(r for r in panel['rows'] if r['arm'] == 'REF')
    project = next(r for r in panel['rows'] if r['arm'] == 'PROJECT')
    usage = metrics.tokens({'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110,
                            'prompt_cache_hit_tokens': 60, 'prompt_cache_miss_tokens': 40})
    calls = [
        {'request_id': 'r1', 'slot_id': ref['slot_id'], 'condition': ref['condition_id'],
         'status': 'settled', 'usage': usage, 'reserved_nanoyuan': 90, 'settled_nanoyuan': 50},
        {'request_id': 'p1', 'slot_id': project['slot_id'], 'condition': project['condition_id'],
         'status': 'uncertain', 'usage': None, 'reserved_nanoyuan': 90, 'settled_nanoyuan': None},
        {'request_id': 'neutral', 'slot_id': 'v105-neutral', 'condition': 'preparation',
         'status': 'settled', 'usage': usage, 'reserved_nanoyuan': 90, 'settled_nanoyuan': 70},
    ]
    coordinator = {'generation': {r['slot_id']: {'status': 'closed'} for r in (ref, project)}}
    summary, rows = metrics.analyze(panel, calls, {'present': True}, tmp_path, coordinator)
    assert summary['groups']['REF']['planned'] == summary['groups']['PROJECT']['planned'] == 50
    assert summary['groups']['REF']['mean_actual_tokens_complete_called_subset'] == 110
    assert summary['groups']['REF']['mean_actual_tokens_all_planned_tasks'] is None
    assert summary['groups']['PROJECT']['mean_actual_tokens_complete_called_subset'] is None
    assert summary['auxiliary_requests_outside_task_means'] == 1
    assert summary['all_batch_settled_upper_cny'] == 120 / 1e9
    assert summary['all_batch_unresolved_reserved_cny'] == 90 / 1e9
    row = next(r for r in rows if r['slot_id'] == ref['slot_id'])
    assert row['exact_final_tokens']['reasoning_tokens'] is None
    assert summary['groups']['REF']['full_panel_accuracy'] is None


def test_foreign_condition_cannot_enter_frozen_pair_statistics(tmp_path):
    panel = prepare.make_panel(json.loads(prepare.SOURCE.read_bytes()))
    row = panel['rows'][0]
    with pytest.raises(ValueError, match='condition'):
        metrics.analyze(panel, [{'slot_id': row['slot_id'], 'condition': 'OLD_THINKING_GROUP'}],
                        {'present': True}, tmp_path, {})
