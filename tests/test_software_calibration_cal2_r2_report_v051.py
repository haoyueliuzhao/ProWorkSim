"""Three finite controls for historical layering, paused inventory and audit overlay."""
import copy

import pytest

from scripts import software_calibration_v051_cal2_r2_report as report


def usage(name, amount=10):
    return {"started_generations": 1, "complete_generations": 1, "bound_complete_generations": 1,
        "known_actual_tokens": amount, "uncertain_reservation_tokens": 0,
        "unknown_reservation_amount_count": 0, "complete_actual_tokens": amount, "integrity_errors": [],
        "prepared_without_generation": [], "rows": [{"generation_started": True,
            "native_attempt_id": name, "bound_actual_tokens": amount}]}


def panel(*, new_started=15):
    original, inventory, fresh = [], [], []
    for i, task in enumerate(report.base.TASKS):
        order = (("R", "P", "U"), ("P", "U", "R"), ("U", "R", "P"))[i % 3]
        for condition in order:
            name = f"v051-{task}-{condition}"
            frozen = {"slot_id": name, "task_id": task, "condition": condition,
                "seed": 202610170551 + i, "generation_tokens": 500000,
                "decisions": 128, "attempts": 128, "project_public_tests": None if condition == "R" else 32}
            entered = name in report.EXCLUDED | {report.ZERO_R}
            account = usage("old-" + name) if name in report.EXCLUDED else None
            if name == report.ZERO_R:
                account = {**usage("unused", 0), "started_generations": 0, "complete_generations": 0,
                           "bound_complete_generations": 0, "rows": []}
            old = {**frozen, "status": "technical_unknown" if entered else "not_started",
                "slot_entered": entered, "source_bound": False, "R_code": None, "Q_terminal": None,
                "raw_R_code": None, "raw_Q_terminal": None, "R_joint": None,
                "raw_R_joint": 0 if name in report.EXCLUDED else None,
                "R_joint_applicable": condition != "R", "binding_issues": ["old fault"] if entered else [],
                "accounting": account, "cost_integrity_known": not entered,
                "worker_attempt": "/old/" + name if entered else None}
            original.append(old)
            if name not in report.EXCLUDED:
                inventory.append(frozen)
                started = len(fresh) < new_started
                fresh.append({**copy.deepcopy(old), "status": "closed" if started else "not_started",
                    "slot_entered": started, "source_bound": started, "R_code": 0 if started else None,
                    "Q_terminal": 0.0 if started else None, "raw_R_code": 0 if started else None,
                    "raw_Q_terminal": 0.0 if started else None, "R_joint": 0 if started and condition != "R" else None,
                    "raw_R_joint": 0 if started and condition != "R" else None, "binding_issues": [],
                    "accounting": usage("new-" + name) if started else None,
                    "cost_integrity_known": True, "worker_attempt": "/new/" + name if started else None})
    return original, inventory, fresh


def bill(rows):
    return report.base.aggregate_cost(rows)


def zero_audit():
    return {"actual_model_generation_tokens": 0, "native_generation_prepared": 0,
        "native_generation_started": 0, "native_generation_complete": 0,
        "native_generation_fault": 0, "actual_call_files": []}


def test_original_eighteen_and_R_dual_history_keep_unknowns_but_close_native_fees():
    old, inventory, fresh = panel()
    original = copy.deepcopy(old)
    rows, history = report.merge_logical_rows(old, inventory, fresh)
    assert len(rows) == len({r["slot_id"] for r in rows}) == 18
    assert len(history) == 4 and all(r["status"] == "technical_unknown" for r in history)
    assert old == original
    assert next(r for r in history if r["slot_id"] == report.ZERO_R)["R_code"] is None
    assert next(r for r in rows if r["slot_id"] == report.ZERO_R)["R_code"] == 0
    for field in ("R_code", "raw_R_code", "Q_terminal"):
        metrics = report.base.endpoint_metrics(rows, field)
        assert metrics["P_minus_R"]["mean"] is None
        assert metrics["U_minus_P"]["mean"] is None
    old_bill, new_bill = bill(old), bill(fresh)
    assert old_bill["complete_actual_tokens"] is None
    old_fee = report.native_fee_evidence(old, old_bill, zero_generation_audit=zero_audit())
    new_fee = report.native_fee_evidence(fresh, new_bill)
    total = report.combine_billing(old_bill, new_bill, rows, original_fee=old_fee, new_fee=new_fee)
    assert total["known_actual_tokens"] == total["complete_actual_tokens"] == 180
    assert total["complete_generations"] == 18
    assert old_fee["reported_complete_actual_tokens_preserved"] is None
    assert old_bill["complete_actual_tokens"] is None


def test_pause_keeps_seven_unopened_and_rejects_replay_or_live_finalization():
    old, inventory, fresh = panel(new_started=8)
    rows, _ = report.merge_logical_rows(old, inventory, fresh)
    assert sum(r["status"] == "not_started" for r in rows) == 7
    assert all(r["R_code"] is None for r in rows if r["status"] == "not_started")
    changed = copy.deepcopy(inventory)
    changed[0] = {**changed[0], "slot_id": next(iter(report.EXCLUDED))}
    with pytest.raises(ValueError, match="exact fourteen untouched"):
        report.merge_logical_rows(old, changed, fresh)
    bad_old = copy.deepcopy(old)
    next(r for r in bad_old if r["slot_id"] in report.EXCLUDED)["R_code"] = 0
    with pytest.raises(ValueError, match="unknowns must be preserved"):
        report.merge_logical_rows(bad_old, inventory, fresh)
    with pytest.raises(ValueError, match="terminal"):
        report.base.common._require_final({"status": "running", "states": {}})


def test_environment_overlay_preserves_raw_rows_delivery_zero_and_known_fees():
    old, inventory, fresh = panel(new_started=8)
    rows, _ = report.merge_logical_rows(old, inventory, fresh)
    before = copy.deepcopy(rows)
    effects = [{"slot_id": name, "strict_code_status": "technical_unknown", "strict_R_code": None,
        "strict_Q_task_terminal": None, "preserve_original_R_joint": True,
        "reason": "source-bound socket fixture invalidates original async test"}
        for name in sorted(report.ENVIRONMENT_AFFECTED)]
    result = report.apply_environment_overlay(rows, effects)
    assert rows == before
    assert sum(r["status"] == "technical_unknown" for r in result) == 6
    assert sum(r["status"] == "not_started" for r in result) == 7
    for row in result:
        if row["slot_id"] in report.ENVIRONMENT_AFFECTED:
            assert row["R_code"] is row["Q_terminal"] is None
            assert row["raw_R_code"] == 0 and row["raw_Q_terminal"] == 0
            assert row["cost_integrity_known"] is True
            assert row["R_joint"] == (0 if row["condition"] == "U" else None)
    adjusted_new = [r for r in result if r["slot_id"] not in report.EXCLUDED]
    assert report.native_fee_evidence(adjusted_new, bill(fresh))["complete_actual_tokens"] == 80
