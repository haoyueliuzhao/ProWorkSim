"""Only the new zero-model bootstrap accounting seam; no old controls replay."""
import copy

import pytest

from scripts.software_bridge_v052_completion_report_r2 import (
    BOOTSTRAP_AUDIT_SHA256, BOOTSTRAP_SECONDS, include_bootstrap,
)
from scripts.software_bridge_v052_completion_report import REMAINING


def test_bootstrap_adds_cost_no_samples_and_rejects_false_zero_or_duplicate_attempt():
    root = '/fixture/software-bridge-v052-resume-r1'
    seconds = [5.018754005432129, 5.019733667373657, 5.018822431564331]
    intervals, rows = [], []
    for index, slot in enumerate(REMAINING):
        output = f'{root}/workers/{slot}/attempt-001'
        interval = {'slot_id': slot, 'output': output, 'seconds': seconds[index], 'ended_at': 100 + index}
        intervals.append(interval)
        absent = {f'{root}/slots/{slot}/started.json': True,
                  **{f'{output}/{name}': True for name in ('task.json', 'resident', 'resident/calls', 'prepared', 'episode')}}
        rows.append({'slot_id': slot, 'host_state': 'stopped', 'slot_entered': False,
                     'model_loader_entered': False, 'generation_started': False,
                     'business_sample_exposure_added': False, 'new_model_calls': 0,
                     'known_actual_tokens': 0, 'uncertain_reservation_tokens': 0,
                     'attempts': [{**interval, 'exit_code': 1, 'failure_present_in_log': True,
                                   'all_expected_pre_model_paths_absent': True, 'absent_before_model_paths': absent}]})
    ledger = dict.fromkeys(('known_actual_tokens', 'uncertain_reservation_tokens', 'started_generations',
                           'complete_generations', 'ledger_tokens', 'complete_actual_tokens',
                           'new_actor_steps', 'new_critic_steps', 'new_backward_calls'), 0)
    ledger.update(integrity_errors=[], outcomes=[{'slot_id': slot, 'started': False, 'closed': False} for slot in REMAINING])
    audit = {'version': 'v052-resume-r1-zero-entry-readonly-audit-v1', 'root': root, 'passed': True,
             'host_status': 'paused', 'host_ended_at': 104, 'checks': {'zero_entry': True},
             'rows': rows, 'original_ledger': ledger, 'worker_cost': {'unique_intervals': 3, 'intervals': intervals,
                 'known_interval_seconds': BOOTSTRAP_SECONDS, 'gpu_worker_seconds': BOOTSTRAP_SECONDS,
                 'unknown_seconds_intervals': 0}}
    reference = {'path': '/fixture/audit.json', 'bytes': 1, 'sha256': BOOTSTRAP_AUDIT_SHA256}
    report = {'root': '/fixture/software-bridge-v052-resume-r2', 'logical_slots': 12,
              'rows': [{'slot_id': f'synthetic-{index}', 'R_code': None if index < 4 else 0} for index in range(12)],
              'formal_metrics': {'mean': None, 'bounds': [0, 1]},
              'billing': {'known_actual_tokens': 1795219 + 3000, 'uncertain_reservation_tokens': 14512,
                          'complete_actual_tokens': None, 'started_generations': 161, 'complete_generations': 160},
              'stages': [{'kind': 'original_first_stage'}, {'kind': 'original_three_continuation'}],
              'worker_cost': {'intervals': [{'output': '/fixture/first/attempt-001'}, {'output': '/fixture/r2/attempt-001'}],
                              'unique_intervals': 2, 'known_interval_seconds': 2700, 'gpu_worker_seconds': 2700,
                              'unknown_seconds_intervals': 0}, 'interpretation': []}
    before, original_audit = copy.deepcopy(report), copy.deepcopy(audit)
    result = include_bootstrap(report, audit, reference)
    assert report == before and audit == original_audit
    assert result['rows'] == report['rows'] and len(result['rows']) == 12
    assert result['formal_metrics'] == report['formal_metrics']
    assert result['billing'] == report['billing']
    assert result['billing']['uncertain_reservation_tokens'] == 14512
    assert result['billing']['complete_actual_tokens'] is None
    assert result['bootstrap_scientific_rows_added'] == result['bootstrap_model_calls_added'] == 0
    assert result['worker_cost']['unique_intervals'] == 5
    assert result['worker_cost']['gpu_worker_seconds'] == 2700 + BOOTSTRAP_SECONDS
    assert [stage['kind'] for stage in result['stages']] == [
        'original_first_stage', 'zero_model_bootstrap_only', 'original_three_continuation']
    assert result['stages'][1]['worker_cost'] == audit['worker_cost']
    with pytest.raises(ValueError, match='once'):
        include_bootstrap(result, audit, reference)
    fake = copy.deepcopy(audit)
    fake['original_ledger']['uncertain_reservation_tokens'] = 1
    with pytest.raises(ValueError, match='generation, unknown reservation'):
        include_bootstrap(report, fake, reference)
    fake = copy.deepcopy(audit)
    fake['original_ledger']['outcomes'][0]['started'] = True
    with pytest.raises(ValueError, match='slot-start'):
        include_bootstrap(report, fake, reference)
    fake = copy.deepcopy(audit)
    fake['rows'][0]['model_loader_entered'] = True
    with pytest.raises(ValueError, match='no model'):
        include_bootstrap(report, fake, reference)
    fake = copy.deepcopy(audit)
    fake['rows'][0]['attempts'][0]['absent_before_model_paths'][f'{root}/slots/{REMAINING[0]}/started.json'] = False
    with pytest.raises(ValueError, match='absence must be explicit'):
        include_bootstrap(report, fake, reference)
    reused = copy.deepcopy(report)
    reused['worker_cost']['intervals'][1]['output'] = intervals[0]['output']
    with pytest.raises(ValueError, match='only once across all three stages'):
        include_bootstrap(reused, audit, reference)
