import importlib.util
import sqlite3
from pathlib import Path

import pytest

from proworksim import software_benchmark_deepseek_api_v064 as api

spec = importlib.util.spec_from_file_location('cash_recovery', Path(__file__).resolve().parents[1] /
                                             'tools/reconcile_dead_owner_cash_v081.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def fixture_ledger(tmp_path):
    ledger = api.BudgetLedger(tmp_path/'ledger.sqlite3', max_concurrency=64)
    identity = 'v064:fixture:DEEPSEEK_REF_B5000K:1:0001'
    ledger.reserve(request_id=identity, slot_id=identity.rsplit(':',1)[0],
        condition='DEEPSEEK_REF_B5000K', usage_id='agent', request_sha256='a'*64,
        max_output_tokens=32768, prompt_upper_bound=100)
    return ledger, identity


def test_owner_unknown_keeps_full_money_and_request_cannot_replay(tmp_path):
    ledger, identity = fixture_ledger(tmp_path)
    with sqlite3.connect(ledger.path) as db:
        db.row_factory = sqlite3.Row
        rows = recovery.read_rows(db, [identity])
    before, after = recovery.mark_unknown(ledger, rows)
    assert recovery.conserved(before) == recovery.conserved(after)
    assert after['inflight_count'] == 0
    assert after['uncertain_reserved_cny'] == api.ABSOLUTE_RESERVATION_NANOYUAN / api.NANOYUAN
    with pytest.raises(api.BudgetStopped):
        ledger.reserve(request_id=identity, slot_id=identity.rsplit(':',1)[0],
            condition='DEEPSEEK_REF_B5000K', usage_id='agent', request_sha256='a'*64,
            max_output_tokens=32768, prompt_upper_bound=100)


def test_existing_authoritative_response_requires_separate_reconciliation(tmp_path):
    ledger, identity = fixture_ledger(tmp_path)
    with sqlite3.connect(ledger.path) as db:
        db.row_factory = sqlite3.Row
        db.execute('INSERT INTO response_observations VALUES (?,?,?,?,?,?,?)',
                   (identity,'2026-10-29T00:00:00Z','real-response','deepseek-flash','a'*64,'{}','[]'))
        with pytest.raises(ValueError, match='Authoritative'):
            recovery.read_rows(db, [identity])
    assert ledger.snapshot()['inflight_count'] == 1
