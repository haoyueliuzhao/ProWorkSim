import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('natural_handoff87_test', ROOT/'tools/complete_natural_api_handoff_v087.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def completed():
    records = {'generation': {'old': {'status': 'closed', 'result': {'same': True}},
                               'new': {'status': 'not_started'}}, 'scores': {}, 'deliveries': {}}
    summary = {'version': 'v085-FD-bounded-original-API-recovery-r1', 'failure': None,
        'finished_unix': 110, 'provider_failures': {'DEEPSEEK': {'reason': 'api_monetary_budget_exhausted'}},
        'last_api_status': {'state': 'cash_exhausted'}, 'pending_grading_jobs': [],
        'unentered_controls': [], 'unentered_scores': [], 'retained_objects': [], **copy.deepcopy(records)}
    cursor = {'failure': None, 'active_generation': [], 'active_grading': [],
        'active_grading_jobs': [], 'pending_grading_jobs': [], 'pending_scores': [],
        'pending_controls': [], **copy.deepcopy(records)}
    return summary, cursor


def test_natural_summary_filters_successor_identity_and_retains_original():
    summary, cursor = completed()
    value = helper.validate_summary(summary, cursor, old_owned={'old'}, gate_unix=100)
    assert value['generation'] == {'old': summary['generation']['old']}
    assert 'new' not in value['generation']


def test_no_active_async_job_or_unproven_failure_can_be_adopted():
    summary, cursor = completed()
    for field in ('active_generation', 'active_grading_jobs', 'pending_grading_jobs'):
        with pytest.raises(ValueError, match='unsettled'):
            helper.validate_summary(summary, {**cursor, field: ['unfinished']}, old_owned={'old'}, gate_unix=100)
    with pytest.raises(ValueError, match='natural monetary-budget'):
        helper.validate_summary({**summary, 'failure': {'kind': 'OOM'}}, cursor, old_owned={'old'}, gate_unix=100)
    with pytest.raises(ValueError, match='natural monetary-budget'):
        helper.validate_summary({**summary, 'last_api_status': {'state': 'ready'}}, cursor, old_owned={'old'}, gate_unix=100)


def test_summary_cursor_conflict_and_missing_owned_identity_are_rejected():
    summary, cursor = completed()
    cursor['scores']['old'] = {'changed': True}
    with pytest.raises(ValueError, match='disagree'):
        helper.validate_summary(summary, cursor, old_owned={'old'}, gate_unix=100)
    with pytest.raises(ValueError, match='missing'):
        helper.validate_summary(summary, cursor, old_owned={'missing'}, gate_unix=100)


def test_publication_is_signal_free_and_preserves_prior_parent_release(tmp_path, monkeypatch):
    handoff = tmp_path/'handoff'
    api = tmp_path/'api'
    handoff.mkdir()
    api.mkdir()
    monkeypatch.setattr(helper.scope, 'HANDOFF_ROOT', handoff)
    monkeypatch.setattr(helper.scope, 'API_ROOT', api)
    monkeypatch.setattr(helper, 'OUT', handoff/'natural')
    monkeypatch.setattr(helper.handoff, 'stage_value', lambda: {'exact': True})
    monkeypatch.setattr(helper, 'require_inactive', lambda _: {'proved': True})
    summary, _ = completed()
    proof = {'version': helper.VERSION, 'source': {'exact': True}, 'stage': {}, 'inventory': {},
        'summary': {}, 'cursor': {}, 'progress': {}, 'old_owned_slot_ids': ['old'],
        'history': {k: {s: v for s, v in summary[k].items() if s == 'old'} for k in ('generation', 'scores', 'deliveries')},
        'old_auxiliary_release': {'already_released': True}, 'parent_release_already_present': {'original': True}}
    monkeypatch.setattr(helper, 'observe', lambda: proof)
    value = helper.publish()
    marker = helper.read(handoff/'stopped.json')
    assert value['signals_sent'] == 0 and marker['signal'] is None
    assert marker['kind'] == 'natural_budget_exit' and marker['helper_parent_operations'] == 0
    assert marker['parent_release_already_present'] == {'original': True}
    assert helper.read(api/'historical-results.json')['generation'] == {'old': summary['generation']['old']}
    assert helper.publish()['status'] == 'handoff_already_completed'


def test_signal_attempt_and_different_existing_history_are_never_overwritten(tmp_path, monkeypatch):
    handoff = tmp_path/'handoff'
    handoff.mkdir()
    monkeypatch.setattr(helper.scope, 'HANDOFF_ROOT', handoff)
    monkeypatch.setattr(helper, 'observe', lambda: {})
    monkeypatch.setattr(helper.handoff, 'stage_value', lambda: {})
    monkeypatch.setattr(helper, 'require_inactive', lambda _: {})
    (handoff/'signal-intent.json').write_text('{}')
    with pytest.raises(ValueError, match='signal path'):
        helper.publish()


def test_watcher_is_bounded_and_quits_after_existing_handoff(tmp_path, monkeypatch):
    monkeypatch.setattr(helper, 'WATCH_ROOT', tmp_path)
    monkeypatch.setattr(helper.scope, 'HANDOFF_ROOT', tmp_path)
    (tmp_path/'stopped.json').write_text('{}')
    monkeypatch.setattr(helper, 'publish', lambda: {'status': 'handoff_already_completed'})
    assert helper.watch(interval_seconds=15, maximum_seconds=1)['status'] == 'handoff_already_completed'
    with pytest.raises(ValueError, match='four hours'):
        helper.watch(maximum_seconds=14401)


def test_watcher_skips_all_heavy_validation_until_a_summary_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(helper, 'WATCH_ROOT', tmp_path/'progress')
    monkeypatch.setattr(helper.scope, 'HANDOFF_ROOT', tmp_path/'handoff')
    monkeypatch.setattr(helper.scope, 'OLD_API_ROOT', tmp_path/'old')
    monkeypatch.setattr(helper, 'publish', lambda: pytest.fail('No source hashes or result scan while old still runs'))
    value = helper.watch(interval_seconds=1, maximum_seconds=1)
    assert value['status'] == 'watch_deadline_reached'
    assert not value['history_completion_claimed']
