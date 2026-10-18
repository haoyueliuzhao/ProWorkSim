"""One pure control for original inventory, immutable unknowns and unique costs."""
import copy

import pytest

from scripts.software_bridge_v052_completion_report import INTERRUPTED, REMAINING, merge_stages
from scripts.software_bridge_v052_report import TASKS


def test_replace_only_original_three_preserve_unknowns_and_count_each_stage_once():
    rows = []
    for index, task in enumerate(TASKS):
        for condition in (('PS1', 'OH_ref') if index % 2 else ('OH_ref', 'PS1')):
            slot = f'v052-{task}-{condition}'
            status = 'technical_unknown' if slot in INTERRUPTED else 'not_started' if slot in REMAINING else 'closed'
            value = 0 if status == 'closed' else None
            outcomes = {'R_code': value, 'Q_task_terminal': value,
                        'R_joint': value if condition == 'PS1' else None,
                        'Q_joint': value if condition == 'PS1' else None}
            rows.append({'slot_id': slot, 'task_id': task, 'condition': condition,
                         'seed': 202610180521 + index, 'first_member': 'member_001',
                         'status': status, 'raw_outcomes': copy.deepcopy(outcomes), **outcomes})
    first = {'version': 'software-bridge-v052-final-v1', 'host_status': 'paused', 'root': '/synthetic/first',
             'plan': {'path': '/synthetic/first/plan.json', 'sha256': 'a', 'bytes': 1},
             'supervisor': {'path': '/synthetic/first/supervisor.json', 'sha256': 'b', 'bytes': 1},
             'rows': rows, 'billing': {'known_actual_tokens': 1795219, 'uncertain_reservation_tokens': 14512,
                 'started_generations': 158, 'complete_generations': 157, 'ledger_tokens': 1809731,
                 'complete_actual_tokens': None, 'new_actor_steps': 0, 'new_critic_steps': 0, 'new_backward_calls': 0},
             'worker_cost': {'intervals': [{'output': '/synthetic/first/attempt-001', 'seconds': 2683.403012275696}],
                 'known_interval_seconds': 2683.403012275696, 'gpu_worker_seconds': 2683.403012275696,
                 'unknown_seconds_intervals': 0, 'issues': []}}
    new = [copy.deepcopy(row) for row in rows if row['slot_id'] in REMAINING]
    for row in new:
        row.update(status='closed', R_code=1, Q_task_terminal=1)
        row['raw_outcomes'].update(R_code=1, Q_task_terminal=1)
    next_stage = {'root': '/synthetic/resume', 'host_status': 'complete',
                  'plan': {'path': '/synthetic/resume/plan.json', 'sha256': 'c', 'bytes': 1},
                  'supervisor': {'path': '/synthetic/resume/supervisor.json', 'sha256': 'd', 'bytes': 1},
                  'rows': new, 'billing': {'known_actual_tokens': 3000, 'uncertain_reservation_tokens': 0,
                      'started_generations': 3, 'complete_generations': 3, 'ledger_tokens': 3000,
                      'complete_actual_tokens': 3000, 'new_actor_steps': 0, 'new_critic_steps': 0, 'new_backward_calls': 0},
                  'worker_cost': {'intervals': [{'output': f'/synthetic/resume/attempt-{i}', 'seconds': 10} for i in range(3)],
                      'known_interval_seconds': 30, 'gpu_worker_seconds': 30, 'unknown_seconds_intervals': 0, 'issues': []}}
    before = copy.deepcopy(first)
    result = merge_stages(first, next_stage)
    assert first == before and len(result['rows']) == 12
    assert result['status_counts'] == {'closed': 8, 'technical_unknown': 4}
    assert [row for row in result['rows'] if row['slot_id'] not in REMAINING] == [row for row in rows if row['slot_id'] not in REMAINING]
    assert all(row['R_code'] is None for row in result['rows'] if row['slot_id'] in INTERRUPTED)
    assert result['overall_primary_metrics']['R_code']['denominator'] == 12
    assert result['overall_primary_metrics']['R_code']['mean'] is None
    for condition in ('PS1', 'OH_ref'):
        assert result['formal_metrics']['R_code'][condition]['denominator'] == 6
        assert result['formal_metrics']['R_code'][condition]['mean'] is None
    assert result['formal_metrics']['R_code']['PS1_minus_OH_ref']['mean'] is None
    assert result['billing']['known_actual_tokens'] == 1798219
    assert result['billing']['uncertain_reservation_tokens'] == 14512
    assert result['billing']['complete_actual_tokens'] is None
    assert result['billing']['logical_inventory'] == 12
    assert result['billing']['started_generations'] == 161
    assert result['billing']['complete_generations'] == 160
    assert result['worker_cost']['unique_intervals'] == 4
    assert result['worker_cost']['gpu_worker_seconds'] == pytest.approx(2713.403012275696)
    assert result['stages'][0]['billing'] == first['billing']
    invalid = copy.deepcopy(next_stage)
    invalid['rows'].append(copy.deepcopy(rows[0]))
    with pytest.raises(ValueError, match='exactly the original three'):
        merge_stages(first, invalid)
    invalid = copy.deepcopy(next_stage)
    invalid['rows'][0] = copy.deepcopy(next(row for row in rows if row['slot_id'] in INTERRUPTED))
    with pytest.raises(ValueError, match='exactly the original three'):
        merge_stages(first, invalid)
    invalid_first = copy.deepcopy(first)
    next(row for row in invalid_first['rows'] if row['slot_id'] in INTERRUPTED)['R_code'] = 0
    with pytest.raises(ValueError, match='must remain unknown'):
        merge_stages(invalid_first, next_stage)
    invalid = copy.deepcopy(next_stage)
    invalid['worker_cost']['intervals'][0]['output'] = first['worker_cost']['intervals'][0]['output']
    with pytest.raises(ValueError, match='only once'):
        merge_stages(first, invalid)
    invalid = copy.deepcopy(next_stage)
    invalid['rows'][0]['seed'] += 1
    with pytest.raises(ValueError, match='row/seed/condition identity'):
        merge_stages(first, invalid)
