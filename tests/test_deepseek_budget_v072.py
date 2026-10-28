"""Temporary SQLite controls; no production ledger, key, API or runtime writes."""
from contextlib import contextmanager
import json
import sqlite3

import pytest

from proworksim import software_benchmark_deepseek_api_v064 as api
from proworksim import software_benchmark_deepseek_budget_v072 as budget


def fixture(tmp_path, monkeypatch):
    path = tmp_path / "ledger.sqlite3"
    qualification = tmp_path / "qualification.json"
    qualification.write_text(json.dumps({"passed": True}))
    ledger = api.BudgetLedger(path)
    rows = {}
    identities = []
    for index, (arm, error) in enumerate((("REF", "TimeoutError"), ("PROJECT", "AttributeError")), 1):
        condition = f"DEEPSEEK_{arm}_B5000K"
        slot = f"v064:fixture-{index}:{condition}:{index}"
        rows[slot] = {"slot_id": slot, "model_key": "DEEPSEEK", "condition_id": condition,
                      "input_plus_output_tokens": 5_000_000}
        identity = slot + ":0001"
        ledger.reserve(request_id=identity, slot_id=slot, condition=condition, usage_id="agent",
            request_sha256=str(index) * 64, max_output_tokens=32768, prompt_upper_bound=4096)
        ledger.uncertain(identity, {"error_type": error, "http_status": None,
            "reason": "attempt_not_proven_settled_no_automatic_retry", "shared_system_failure": True})
        identities.append(identity)

    @contextmanager
    def reader():
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            yield db
        finally:
            db.close()

    monkeypatch.setattr(budget, "LEDGER", path)
    monkeypatch.setattr(budget, "QUALIFICATION", qualification)
    monkeypatch.setattr(budget, "_ledger_read", reader)
    monkeypatch.setattr(budget, "original_rows", lambda: rows)
    return path, ledger, rows, identities


def test_two_unknown_outcomes_keep_full_money_and_old_request_ids_cannot_replay(tmp_path, monkeypatch):
    path, ledger, _, identities = fixture(tmp_path, monkeypatch)
    with sqlite3.connect(path) as db:
        before = list(db.execute("SELECT * FROM requests ORDER BY request_id"))
    value = budget.budget_status()
    assert value["state"] == "ready" and value["can_start_generation"] is True
    assert value["bounded_uncertain_request_ids"] == identities
    assert value["bounded_uncertain_count"] == 2
    assert value["bounded_uncertain_reserved_nanoyuan"] == 10_485_760_000
    assert value["uncertain_reserved_CNY"] == "10.48576"
    assert value["committed_upper_CNY"] == "10.48576"
    assert value["remaining_CNY"] == "1489.51424"
    assert value["unknown_usage_reclassified_as_zero"] is False
    assert value["ledger_records_modified"] is False
    with sqlite3.connect(path) as db:
        assert list(db.execute("SELECT * FROM requests ORDER BY request_id")) == before
    with pytest.raises(api.BudgetStopped, match="already_attempted_no_replay"):
        ledger.reserve(request_id=identities[0], slot_id=identities[0].rsplit(":", 1)[0],
            condition="DEEPSEEK_REF_B5000K", usage_id="agent", request_sha256="1" * 64,
            max_output_tokens=32768, prompt_upper_bound=4096)


@pytest.mark.parametrize("mutation", [
    "UPDATE requests SET reserved_nanoyuan=1 WHERE request_id=?",
    "UPDATE requests SET usage_json='{}' WHERE request_id=?",
    "UPDATE requests SET status='unpriced' WHERE request_id=?",
    "UPDATE requests SET condition='DEEPSEEK_REF_B10000K' WHERE request_id=?",
    "UPDATE requests SET request_id='another:identity' WHERE request_id=?",
    "UPDATE requests SET max_output_tokens=65536 WHERE request_id=?",
    "UPDATE requests SET prompt_upper_bound=98305 WHERE request_id=?",
    "UPDATE requests SET failure_json='{}' WHERE request_id=?",
])
def test_partial_cash_or_usage_state_or_identity_faults_still_block(tmp_path, monkeypatch, mutation):
    path, _, _, identities = fixture(tmp_path, monkeypatch)
    with sqlite3.connect(path) as db:
        db.execute(mutation, (identities[0],))
    value = budget.budget_status()
    assert value["state"] == "shared_halted" and value["can_start_generation"] is False
    assert value["reason"].startswith("bounded_uncertainty_validation_failed:")


def test_unreconciled_response_observation_is_not_treated_as_transport_unknown(tmp_path, monkeypatch):
    path, _, _, identities = fixture(tmp_path, monkeypatch)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO response_observations VALUES (?,?,?,?,?,?,?)", (
            identities[0], "2026-10-28T13:00:00+00:00", "provider-response", "deepseek-flash",
            "a" * 64, "null", "[]"))
    value = budget.budget_status()
    assert value["state"] == "shared_halted"
    assert "unreconciled_response" in value["reason"]


def test_original_policy_identity_and_hard_halt_are_preserved(tmp_path, monkeypatch):
    path, _, _, _ = fixture(tmp_path, monkeypatch)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO metadata VALUES ('halted','shared_http_401_authentication_or_account_failure')")
    value = budget.budget_status()
    assert value["state"] == "shared_halted"
    assert value["reason"] == "shared_http_401_authentication_or_account_failure"
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM metadata WHERE name='halted'")
        original = json.loads(db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0])
        original["cap_nanoyuan"] += 1
        db.execute("UPDATE metadata SET value=? WHERE name='policy'", (json.dumps(original),))
    value = budget.budget_status()
    assert value["state"] == "shared_halted"
    assert "money_policy_identity_changed" in value["reason"]


def test_original_repeated_failure_cooldown_is_not_replaced_with_ready(tmp_path, monkeypatch):
    _, ledger, rows, _ = fixture(tmp_path, monkeypatch)
    condition = "DEEPSEEK_REF_B5000K"
    slot = "v064:fixture-3:" + condition + ":3"
    rows[slot] = {"slot_id": slot, "model_key": "DEEPSEEK", "condition_id": condition,
                  "input_plus_output_tokens": 5_000_000}
    ledger.reserve(request_id=slot + ":0001", slot_id=slot, condition=condition, usage_id="agent",
        request_sha256="3" * 64, max_output_tokens=32768, prompt_upper_bound=4096)
    ledger.uncertain(slot + ":0001", {"error_type": "APIUncertainFailure", "http_status": 429,
        "reason": "attempt_not_proven_settled_no_automatic_retry", "shared_system_failure": True})
    value = budget.budget_status()
    assert value["bounded_uncertain_count"] == 3
    assert value["state"] == "waiting_cooldown"
    assert value["temporary_wait"] is True and value["can_start_generation"] is False
    assert value["admission_wait_seconds"] > 0


@pytest.mark.parametrize(("settled_count", "expected_state"), [(297, "cash_exhausted"), (298, "shared_halted")])
def test_full_uncertain_reservations_remain_inside_original_cash_cap(tmp_path, monkeypatch, settled_count, expected_state):
    path, ledger, _, _ = fixture(tmp_path, monkeypatch)
    with sqlite3.connect(path) as db:
        db.executemany("""INSERT INTO requests
            (request_id,slot_id,condition,usage_id,status,request_sha256,reserved_nanoyuan,
             settled_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""", [
                (f"fixture-settled-{i}", "fixture-history", "fixture-condition", "agent", "settled",
                 "a" * 64, api.ABSOLUTE_RESERVATION_NANOYUAN, 5_000_000_000, 32768, 4096,
                 "2026-10-28T13:00:00+00:00") for i in range(settled_count)])
    value = budget.budget_status()
    assert value["state"] == expected_state and value["can_start_generation"] is False
    assert value["uncertain_reserved_CNY"] == "10.48576"
    with pytest.raises(api.BudgetStopped, match="global_cny_budget_reservation_insufficient"):
        ledger.reserve(request_id="a-new-never-dispatched-request", slot_id="fixture-new-slot",
            condition="DEEPSEEK_REF_B5000K", usage_id="agent", request_sha256="4" * 64,
            max_output_tokens=32768, prompt_upper_bound=4096)
