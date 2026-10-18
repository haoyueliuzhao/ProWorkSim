"""Three incremental contracts for the unique original-plus-continuation report."""
import copy

import pytest

from scripts import software_calibration_v051_merged_report as merged
from scripts import software_calibration_v051_report as prior


def fixture_rows():
    original, inventory, continuation = [], [], []
    for index in range(48):
        ordinal, arm = index // 2, prior.ARMS[index % 2]
        frozen = {"slot_id": f"cal1-{ordinal + 1:02d}-{arm}", "ordinal": ordinal,
            "task_id": f"task-{ordinal}", "arm": arm, "seed": 202610170511 + ordinal,
            "maximum_tokens": 1000}
        started = index < 15
        missing = index in (7, 8)
        pending = index < 9
        row = {**frozen, "attempted": started,
            "status": "technical_unknown" if pending else "passed" if started else "not_started",
            "pass_at_1": 1 if started and not pending else None,
            "original_grade_pass_at_1": 1 if started and not missing else None,
            "actual_tokens": 10 if started and not missing else None,
            "binding_issues": ["worker_final_readonly_guard_known_passed"] if pending else []}
        original.append(row)
        if not started:
            inventory.append(frozen)
            continuation.append({**frozen, "attempted": True, "status": "passed", "pass_at_1": 1,
                "original_grade_pass_at_1": 1, "actual_tokens": 20, "binding_issues": []})
    return original, inventory, continuation


def test_unique_panel_retains_original_nine_pending_raw_grades_and_costs():
    original, inventory, continuation = fixture_rows()
    before = copy.deepcopy(original)
    rows = merged.merge_unique_rows(original, inventory, continuation)
    assert rows[:15] == before[:15]
    assert original == before
    assert len(rows) == len({r["slot_id"] for r in rows}) == 48
    assert sum(r["pass_at_1"] is None for r in rows) == 9
    assert sum(r["original_grade_pass_at_1"] == 1 for r in rows) == 46
    metrics, _ = prior.outcome_summary(rows)
    assert metrics["reference"]["pass_at_1"] is None
    assert metrics["project"]["pass_at_1"] is None
    assert metrics["project_minus_reference"]["value"] is None
    bill = prior.generation_ledger(rows)
    assert bill["started_generations"] == 48
    assert bill["complete_generations"] == 46
    assert bill["known_actual_tokens"] == 13 * 10 + 33 * 20
    assert bill["uncertain_reservation_tokens"] == 2000
    assert bill["complete_actual_tokens"] is None
    assert bill["unstarted_slots"] == 0


def test_replay_duplicate_or_changed_original_identity_is_rejected():
    original, inventory, continuation = fixture_rows()
    with pytest.raises(ValueError, match="exact ordered untouched"):
        merged.merge_unique_rows(original, [inventory[0], *inventory], [continuation[0], *continuation])
    with pytest.raises(ValueError, match="exact ordered untouched"):
        merged.merge_unique_rows(original, [original[0], *inventory[1:]], [original[0], *continuation[1:]])
    changed = copy.deepcopy(continuation)
    changed[0]["seed"] += 1
    with pytest.raises(ValueError, match="original slot identity"):
        merged.merge_unique_rows(original, inventory, changed)


def test_worker_intervals_count_old_cost_once_and_reject_duplicate_references():
    def cost(rows):
        return {"attempts": rows, "issues": [], "scope": "whole worker intervals"}
    old = cost([{"output": "/original/attempt-1", "seconds": 8},
                {"output": "/original/attempt-2", "seconds": 21}])
    new = cost([{"output": "/continuation/attempt-1", "seconds": 34}])
    value = merged.merge_worker_cost(old, new)
    assert value["unique_attempts"] == 3
    assert value["gpu_worker_seconds"] == 63
    assert value["gpu_worker_hours"] == 63 / 3600
    with pytest.raises(ValueError, match="never charge twice"):
        merged.merge_worker_cost(old, cost([old["attempts"][0]]))
