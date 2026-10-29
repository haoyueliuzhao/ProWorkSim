from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

from proworksim import software_benchmark_deepseek_api_v064 as old
from proworksim import software_benchmark_deepseek_budget_v089 as new
from proworksim import software_benchmark_fd_v085 as fd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('amend89_test', ROOT/'tools/amend_api_budget_v089.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def original_row():
    return {'slot_id': 'v064:fixture:DEEPSEEK_REF_B5000K:17', 'slot_index': 7,
        'condition_id': 'DEEPSEEK_REF_B5000K', 'group_id': 'DEEPSEEK_REF_B5000K',
        'model_key': 'DEEPSEEK', 'instance_id': 'fixture', 'arm': 'REF',
        'input_plus_output_tokens': 5_000_000, 'seed': 17}


def recovery_row():
    old_row = original_row()
    return {**old_row, 'slot_id': old_row['slot_id']+new.RECOVERY_SUFFIX,
        'slot_index': 6000, 'original_slot_id': old_row['slot_id'],
        'original_slot_index': old_row['slot_index'], 'recovery_attempt': 1}


def fixture(tmp_path, *, uncertain=True):
    path = tmp_path/'ledger.sqlite3'
    ledger = fd.ManagedLedger(path)
    row = original_row()
    if uncertain:
        ledger.reserve(request_id=row['slot_id']+':0001', slot_id=row['slot_id'],
            condition=row['condition_id'], usage_id='agent', request_sha256='a'*64,
            max_output_tokens=old.MAX_OUTPUT_TOKENS, prompt_upper_bound=100)
        ledger.uncertain(row['slot_id']+':0001', {'error_type': 'APIUncertainFailure',
            'http_status': None, 'reason': 'attempt_not_proven_settled_no_automatic_retry',
            'shared_system_failure': True})
    return path, {row['slot_id']: row}


def amend(path, originals):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        before = tool.validate_before(db, original_rows=originals)
        marker, after = tool.apply_policy_change(db, expected=before,
            proposal_ref={'path': 'sealed-proposal', 'sha256': 'a'*64},
            backup_ref={'path': 'retained-backup', 'sha256': 'b'*64})
        db.commit()
    return before, marker, after


def test_cap_changes_once_and_all_old_financial_bytes_and_unknowns_are_preserved(tmp_path):
    path, rows = fixture(tmp_path)
    before, marker, after = amend(path, rows)
    assert before['preserved_fingerprints'] == after['preserved_fingerprints']
    assert before['totals'] == after['totals'] and before['request_statuses'] == after['request_statuses']
    assert before['totals']['uncertain'] == old.ABSOLUTE_RESERVATION_NANOYUAN
    assert after['policy']['cap_nanoyuan']-before['policy']['cap_nanoyuan'] == 200*old.NANOYUAN
    assert marker['unknown_reservations_released'] is False
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        with pytest.raises(ValueError, match='exact authorized old ledger'):
            tool.apply_policy_change(db, expected=before, proposal_ref={}, backup_ref={})
        db.rollback()
    snap = new.BudgetLedger(path).snapshot()
    assert snap['cap_nanoyuan'] == 1700*old.NANOYUAN
    assert snap['uncertain_reserved_cny'] == old.ABSOLUTE_RESERVATION_NANOYUAN/old.NANOYUAN
    assert old.CAP_NANOYUAN == 1500*old.NANOYUAN
    with pytest.raises(ValueError, match='another immutable budget'):
        fd.ManagedLedger(path)


def test_live_reservations_or_halts_do_not_get_cleared_for_a_budget_increase(tmp_path):
    path, rows = fixture(tmp_path, uncertain=False)
    row = next(iter(rows.values()))
    ledger = fd.ManagedLedger(path)
    ledger.reserve(request_id=row['slot_id']+':0001', slot_id=row['slot_id'],
        condition=row['condition_id'], usage_id='agent', request_sha256='a'*64,
        max_output_tokens=old.MAX_OUTPUT_TOKENS, prompt_upper_bound=100)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        with pytest.raises(ValueError, match='in-flight cash'):
            tool.validate_before(db, original_rows=rows)
        db.execute("UPDATE requests SET status='settled',settled_nanoyuan=1")
        db.execute("INSERT INTO metadata VALUES('halted','identity_violation')")
        db.commit()
        with pytest.raises(ValueError, match='hard_halt'):
            tool.validate_before(db, original_rows=rows)


def test_changed_price_or_ledger_rows_block_the_transaction_without_writes(tmp_path):
    path, rows = fixture(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        expected = tool.validate_before(db, original_rows=rows)
        db.execute("UPDATE metadata SET value='2' WHERE name='system_failure_streak'")
        db.commit()
        db.execute('BEGIN IMMEDIATE')
        with pytest.raises(ValueError, match='exact authorized old ledger'):
            tool.apply_policy_change(db, expected=expected, proposal_ref={}, backup_ref={})
        db.rollback()
        policy = {**tool.OLD_POLICY, 'pricing_checked_date': 'changed'}
        db.execute("UPDATE metadata SET value=? WHERE name='policy'", (json.dumps(policy),))
        db.commit()
        with pytest.raises(ValueError, match='exact prior'):
            tool.validate_before(db, original_rows=rows)


def test_consistent_readonly_sqlite_backup_preserves_schema_and_full_rows(tmp_path):
    path, rows = fixture(tmp_path)
    backup = tmp_path/'backup.sqlite3'
    with closing(tool.open_read(path)) as source, closing(sqlite3.connect(backup)) as destination:
        before = tool.validate_before(source, original_rows=rows)
        source.backup(destination)
    with closing(tool.open_read(backup)) as copied:
        assert tool.snapshot(copied) == before


def test_new_reservations_use_1700_cap_and_cannot_replay_original_requests(tmp_path):
    path, rows = fixture(tmp_path)
    amend(path, rows)
    ledger = new.BudgetLedger(path)
    with ledger._transaction() as db:
        db.execute("UPDATE requests SET status='settled',settled_nanoyuan=?,settled_peak_nanoyuan=?",
                   (1499*old.NANOYUAN, 1499*old.NANOYUAN))
    row = recovery_row()
    value = ledger.reserve(request_id=row['slot_id']+':0001', slot_id=row['slot_id'],
        condition=row['condition_id'], usage_id='agent', request_sha256='b'*64,
        max_output_tokens=old.MAX_OUTPUT_TOKENS, prompt_upper_bound=100)
    assert value['reserved_nanoyuan'] == old.ABSOLUTE_RESERVATION_NANOYUAN
    with pytest.raises(old.BudgetStopped, match='already_attempted'):
        ledger.reserve(request_id=row['slot_id']+':0001', slot_id=row['slot_id'],
            condition=row['condition_id'], usage_id='agent', request_sha256='b'*64,
            max_output_tokens=old.MAX_OUTPUT_TOKENS, prompt_upper_bound=100)
    with ledger._transaction() as db:
        db.execute("UPDATE requests SET settled_nanoyuan=?,settled_peak_nanoyuan=? WHERE status='settled'",
                   (1700*old.NANOYUAN, 1700*old.NANOYUAN))
        db.execute("UPDATE requests SET status='uncertain' WHERE status='reserved'")
    with pytest.raises(old.BudgetStopped, match='reservation_insufficient'):
        ledger.reserve(request_id=row['slot_id']+':0002', slot_id=row['slot_id'],
            condition=row['condition_id'], usage_id='agent', request_sha256='c'*64,
            max_output_tokens=old.MAX_OUTPUT_TOKENS, prompt_upper_bound=100)


def test_uncertainty_requires_registered_recovery_mapping_and_keeps_full_cash(tmp_path):
    path, originals = fixture(tmp_path)
    amend(path, originals)
    row = recovery_row()
    ledger = new.BudgetLedger(path)
    ledger.reserve(request_id=row['slot_id']+':0001', slot_id=row['slot_id'],
        condition=row['condition_id'], usage_id='agent', request_sha256='b'*64,
        max_output_tokens=old.MAX_OUTPUT_TOKENS, prompt_upper_bound=100)
    ledger.uncertain(row['slot_id']+':0001', {'error_type': 'APIUncertainFailure',
        'http_status': None, 'reason': 'attempt_not_proven_settled_no_automatic_retry', 'shared_system_failure': True})
    qualification = tmp_path/'qualification.json'
    qualification.write_text('{"passed":true}')
    missing = new.budget_status(path=path, qualification=qualification, originals=originals)
    assert missing['state'] == 'shared_halted'
    present = new.budget_status(path=path, qualification=qualification, originals=originals, retry_rows=[row])
    assert present['state'] == 'ready' and present['cap_CNY'] == '1700.00'
    assert present['bounded_uncertain_count'] == 2
    assert present['uncertain_reserved_CNY'] == str(2*old.ABSOLUTE_RESERVATION_NANOYUAN/old.NANOYUAN)
    assert present['unknown_reservations_released'] is False
    for altered in ({**row, 'seed': 999}, {**row, 'recovery_attempt': 2}, {**row, 'slot_id': row['slot_id']+'x'}):
        with pytest.raises(ValueError, match='registry changed'):
            new.validate_retry_registry([altered], originals=originals)


def test_private_initialization_and_fork_never_reinstall_the_old_cap(tmp_path, monkeypatch):
    path, originals = fixture(tmp_path, uncertain=False)
    amend(path, originals)
    monkeypatch.setattr(new.original_budget, 'original_rows', lambda: originals)
    monkeypatch.setattr(new.wire, 'LEDGER', path)
    monkeypatch.setattr(new.wire, 'OfficialDeepSeekCounter', lambda *args, **kwargs: object())
    monkeypatch.setattr(new.API_VIEW, 'load_api_key', lambda _: 'CPU-only-unused-key')
    runtime = new.build_runtime(scope_guard=lambda *args, **kwargs: {}, retry_rows=[recovery_row()],
        inventory_ref={'path': 'fixture'}, identity_file=tmp_path/'identity.json')
    runtime.read_only_preflight = lambda: {'preparation': {'tokenizer_manifest': {'path': 'unused', 'sha256': 'a'},
        'counter_margin_tokens': 0}, 'allowed_tool_names': {'fixture'}}
    runtime.logical_resident = lambda: {'no_network': True}
    wrapped = new.RuntimeView(runtime, fd.FDGuard(probe=lambda: {
        'fd_used': 20, 'soft_limit': 16384, 'hard_limit': 16384, 'fd_free': 16364}))
    assert wrapped.initialize_for_run() == {'no_network': True}
    assert isinstance(runtime.client.ledger, new.BudgetLedger)
    fork = runtime.client.fork_for_episode()
    assert isinstance(fork.ledger, new.BudgetLedger)
    assert fork.ledger.snapshot()['cap_nanoyuan'] == 1700*old.NANOYUAN
    assert old.DeepSeekClient.__init__.__globals__['BudgetLedger'] is old.BudgetLedger
