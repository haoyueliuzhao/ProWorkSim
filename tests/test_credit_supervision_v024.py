from scripts.run_credit_v024 import CAPS, TASK_CAPS, dependency, ready_cards
from test_pilot_supervision_v023 import sample


def test_reserve_evaluations_and_separate_window_cap():
    assert sum(CAPS.values()) == 36 * 3600
    assert all(CAPS[n] >= 12 * TASK_CAPS['episode'] + TASK_CAPS['loading'] + 600 for n in ['eval_initial','eval_mc','eval_handoff_rtg'])
    assert TASK_CAPS['update'] == 5 * 3600
    assert ready_cards(sample(), training=True) == [3, 7]


def test_complete_baseline_not_success_is_entry_and_arms_are_independent(tmp_path):
    states = {'eval_initial': {'status': 'running'}}
    (tmp_path/'baseline-complete.json').write_text('{}')
    assert dependency('common', tmp_path, states) == 'waiting'
    states['eval_initial']['status'] = 'complete'
    assert dependency('common', tmp_path, states) == 'ready'
    states['eval_initial']['status'] = 'stopped'
    assert dependency('common', tmp_path, states) == 'unavailable_endpoint'
    states.update(train_mc={'status':'stopped'}, train_handoff_rtg={'status':'complete'})
    (tmp_path/'handoff_rtg-complete.json').write_text('{}')
    assert dependency('eval_mc', tmp_path, states) == 'unavailable_endpoint'
    assert dependency('eval_handoff_rtg', tmp_path, states) == 'ready'
