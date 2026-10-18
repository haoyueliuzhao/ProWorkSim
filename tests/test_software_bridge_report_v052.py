"""One new pure contract: fixed12/6, two-condition difference, unknown and N/A."""
import copy

import pytest

from scripts.software_bridge_v052_report import CONDITIONS, GUARDS, TASKS, formal_outcomes, metrics_for


def test_original_twelve_six_task_denominators_missing_values_and_native_joint_NA():
    rows = []
    reports = {}
    for index, task in enumerate(TASKS):
        for condition in CONDITIONS:
            row = {'slot_id': f'v052-{task}-{condition}', 'task_id': task, 'condition': condition}
            result = {'slot_id': row['slot_id'], 'R_code': int(condition == 'PS1' and index == 0),
                      'Q_task_terminal': int(condition == 'PS1' and index == 0),
                      'R_joint': 0 if condition == 'PS1' else None,
                      'Q_joint': 0.0 if condition == 'PS1' else None,
                      'project_delivery_endpoint': 'not_applicable' if condition == 'OH_ref' else 'fixed',
                      'calibration_condition': 'P' if condition == 'PS1' else None,
                      'status': 'safe_local_stop', 'stop_reason': 'full_native_context_preexecution_rejection'}
            report = {'result': result, 'status': 'closed', 'guard': {'passed': True},
                      'episode_guard': dict.fromkeys(GUARDS, True),
                      'accounting': {'all_started_settled': True, 'integrity_errors': []},
                      'verdict': {'decision': 'continue'}, 'measurement': {'decision': 'continue'}}
            raw, formal, issues = formal_outcomes(row, 'complete', report, source_bindings_closed=True)
            assert issues == []  # A safe context stop with known code zero is not a failure of evidence.
            rows.append({**row, 'raw_outcomes': raw, **formal})
            reports[row['slot_id']] = report
    initial = metrics_for(rows)
    assert initial['R_code']['OH_ref']['known'] == initial['R_code']['PS1']['denominator'] == 6
    assert initial['R_code']['PS1_minus_OH_ref']['mean'] == pytest.approx(1 / 6)
    assert initial['R_joint']['OH_ref'] == {'applicable': False, 'denominator': None, 'known': None,
        'unknown': None, 'mean': None, 'bounds': None, 'reason': 'Native OH has no project fixed-delivery contract'}
    assert initial['R_joint']['PS1']['mean'] == 0
    # Raw success with a missing final guard stays raw, while formal becomes unknown.
    changed = copy.deepcopy(reports[rows[0]['slot_id']])
    changed['result']['R_code'] = 1
    changed['episode_guard'].pop('rng_restored_exactly')
    raw, formal, issues = formal_outcomes(rows[0], 'complete', changed, source_bindings_closed=True)
    assert 'episode_guard_missing_or_failed' in issues and raw['R_code'] == 1
    rows[0].update(raw_outcomes=raw, **formal)
    # A never-started PS1 row also stays unknown; no fabricated zero outcome.
    raw, formal, issues = formal_outcomes(rows[3], 'not_started', None, source_bindings_closed=False)
    rows[3].update(raw_outcomes=raw, **formal)
    final = metrics_for(rows)
    assert final['R_code']['OH_ref']['known'] == final['R_code']['PS1']['known'] == 5
    assert final['R_code']['OH_ref']['mean'] is final['R_code']['PS1']['mean'] is None
    assert final['R_code']['PS1_minus_OH_ref']['mean'] is None
    assert final['R_code']['PS1_minus_OH_ref']['known_pairs'] == 4
    assert final['R_code']['PS1_minus_OH_ref']['denominator'] == 6
    assert metrics_for(rows, raw=True)['R_code']['OH_ref']['mean'] == pytest.approx(1 / 6)
    assert final['Q_joint']['OH_ref']['applicable'] is False
    with pytest.raises(ValueError, match='twelve unique rows'):
        metrics_for(rows[:-1])
