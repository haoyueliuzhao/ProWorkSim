"""Pure original-inventory, budget and merge controls; never start a worker."""
import copy
from collections import Counter

import pytest

from scripts import software_organization_resume_v044 as resume
from scripts import software_organization_v044 as original


EXPECTED = {
    "block-r0-s0": ("sc-record-views-handoff-v040", 202610100441,
                    ("ST", "PB", "PT", "SB"), "member_002", "member_002"),
    "block-r0-s1": ("sc-record-views-handoff-v040", 202610100442,
                    ("PB", "PT", "SB", "ST"), "member_001", "member_002"),
    "block-r1-s1": ("sc-record-catalog-handoff-v040", 202610100442,
                    ("SB", "ST", "PB", "PT"), "member_002", "member_001"),
}
MAIN_CONTRASTS = ("information_main_effect", "framing_main_effect", "interaction")


def complete_rows():
    # The retained real first block has only PT successful. Three synthetic
    # remaining blocks each give a different condition the sole success.
    winner = {"block-r1-s0": "PT", "block-r0-s0": "ST", "block-r0-s1": "PB", "block-r1-s1": "SB"}
    return [{**copy.deepcopy(unit), "status": "closed", "R": int(unit["condition"] == winner[worker]),
             "submitted": unit["condition"] == winner[worker]}
            for worker, units in resume.all_assignments().items() for unit in units]


def test_new_inventory_is_only_original_remaining_twelve_with_frozen_coordinates():
    assignments = resume.assignments()
    assert resume.WORKERS == tuple(EXPECTED)
    assert assignments == {worker: original.assignments()[worker] for worker in EXPECTED}
    assert resume.all_assignments() == original.assignments()
    units = [unit for block in assignments.values() for unit in block]
    assert len(units) == len({unit["slot_id"] for unit in units}) == 12
    assert original.FIRST_BLOCK not in assignments
    assert Counter(unit["condition"] for unit in units) == dict.fromkeys(original.CONDITIONS, 3)
    for worker, (case, seed, conditions, first, diagnostic_owner) in EXPECTED.items():
        block = assignments[worker]
        assert tuple(unit["condition"] for unit in block) == conditions
        assert all((unit["case_id"], unit["sampling_seed"], unit["first_member"], unit["diagnostic_a_owner"])
                   == (case, seed, first, diagnostic_owner) for unit in block)
        assert [unit["slot_id"] for unit in block] == ["org44-" + worker.removeprefix("block-") + "-" + c for c in conditions]


def test_resume_changes_only_new_worker_and_episode_caps_without_transferring_old_balance():
    assert resume.VERSION != original.VERSION
    assert resume.GPU_ORDER == (3, 4, 5, 7)
    assert resume.LIMITS == {**original.LIMITS, "max_new_episodes": 12, "max_parallel_model_instances": 3}
    caps = resume.budget_caps()
    assert caps["new"] == {"decisions": 1536, "attempts": 1536, "total_tokens": 6000000, "run_tests": 384}
    assert caps["old_actual"] == {"decisions": 150, "attempts": 144, "total_tokens": 1892846, "run_tests": 14}
    assert caps["combined"] == {"decisions": 1686, "attempts": 1680, "total_tokens": 7892846, "run_tests": 398}
    assert caps["transfer_old_unused"] is False
    assert caps["combined"]["total_tokens"] != 8000000


def test_logical_panel_has_sixteen_unique_rows_and_four_equally_weighted_blocks():
    rows = complete_rows()
    before = copy.deepcopy(rows)
    measured = resume.summarize_rows(rows)
    assert rows == before
    assert len(rows) == len({row["slot_id"] for row in rows}) == 16
    assert sum(row["R"] for row in rows) == 4
    assert len(measured["paired_blocks"]) == 4
    assert {block["block_id"] for block in measured["paired_blocks"]} == set(original.WORKERS)
    assert all(block["complete"] is True for block in measured["paired_blocks"])
    for condition in original.CONDITIONS:
        row = measured["by_condition"][condition]
        assert row["scheduled"] == row["known"] == 4
        assert row["successes"] == 1 and row["mean_R"] == 0.25
    assert all(measured["full_inventory_mean_contrasts"][key] == 0 for key in MAIN_CONTRASTS)
    old = next(block for block in measured["paired_blocks"] if block["block_id"] == original.FIRST_BLOCK)
    assert [old[key] for key in MAIN_CONTRASTS] == [0.5, 0.5, 1]


@pytest.mark.parametrize("status", ["not_started", "running", "technical_unknown"])
def test_absent_or_unknown_new_result_remains_null_without_partial_primary_estimate(status):
    rows = complete_rows()
    missing = next(row for row in rows if row["slot_id"] == "org44-r0-s0-PT")
    missing.update(status=status, R=None, submitted=None)
    before = copy.deepcopy(rows)
    measured = resume.summarize_rows(rows)
    assert rows == before and missing["R"] is None
    condition = measured["by_condition"]["PT"]
    assert condition["known"] == 3 and condition["unknown_or_pending"] == 1 and condition["mean_R"] is None
    block = next(row for row in measured["paired_blocks"] if row["block_id"] == "block-r0-s0")
    assert block["R"]["PT"] is None and block["complete"] is False
    assert all(measured["full_inventory_mean_contrasts"][key] is None for key in MAIN_CONTRASTS)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "new_id", "old_four_again"])
def test_merge_refuses_missing_duplicate_new_or_twenty_slot_inventory(mutation):
    rows = complete_rows()
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = copy.deepcopy(rows[0])
    elif mutation == "new_id":
        rows[-1]["slot_id"] = "org45-new-unregistered-PB"
    else:
        old_ids = {unit["slot_id"] for unit in resume.all_assignments()[original.FIRST_BLOCK]}
        rows.extend(copy.deepcopy([row for row in rows if row["slot_id"] in old_ids]))
    with pytest.raises(ValueError):
        resume.summarize_rows(rows)


def resolved_feedback():
    return {"mechanism_gate_inputs": {"resolved": True, "actual_generated_requests": 2,
        "requests_verified_under_v044": 2, "projection_unresolved": [], "page_protocol_unresolved": [],
        "unresolved_no_followup_ids": [], "page_protocol_violations": [], "projection_violations": [],
        "feedback_missing_from_first_actual_followup": [], "context_blocked_feedback_ids": []}}


@pytest.mark.parametrize("reward", [0, 1])
def test_normal_retirement_or_business_failure_never_selects_continuation_by_reward(reward):
    row = {"status": "closed", "R": reward, "submitted": bool(reward),
        "boundary": {"role_stops": {"member_001": "completed", "member_002": "retired"},
                     "execution_integrity_failure": None},
        "member_lifecycle": {"member_requested_births": 0}, "work_use": {"has_evidenced_cross_member_chain": False}}
    feedback = resolved_feedback()
    before = copy.deepcopy((row, feedback))
    assert resume.stop_decision(row, feedback) is None
    assert (row, feedback) == before


@pytest.mark.parametrize("field", ["page_protocol_violations", "projection_violations",
    "feedback_missing_from_first_actual_followup", "context_blocked_feedback_ids"])
def test_actual_mechanism_fault_is_distinct_from_pending_measurement(field):
    feedback = resolved_feedback()
    feedback["mechanism_gate_inputs"].update(resolved=False, **{field: ["original-evidence-id"]})
    decision = resume.stop_decision({"status": "closed", "R": 0}, feedback)
    assert decision["kind"] == "mechanism_fault" and decision["reason"]


@pytest.mark.parametrize("change", ["no_feedback", "unresolved", "unverified_requests"])
def test_measurement_gap_stops_unopened_work_without_becoming_execution_fault(change):
    feedback = resolved_feedback()
    if change == "no_feedback":
        feedback = None
    elif change == "unresolved":
        feedback["mechanism_gate_inputs"].update(resolved=False, unresolved_no_followup_ids=["unknown-terminal"])
    else:
        feedback["mechanism_gate_inputs"]["requests_verified_under_v044"] = 1
    decision = resume.stop_decision({"status": "closed", "R": 0}, feedback)
    assert decision["kind"] == "measurement_pending" and decision["reason"]


@pytest.mark.parametrize("row", [{"status": "technical_unknown", "R": None},
    {"status": "closed", "R": None}, {"status": "closed", "R": 2}, {"status": "closed", "R": True}])
def test_execution_fault_is_not_cleared_by_an_optimistic_feedback_summary(row):
    decision = resume.stop_decision(row, resolved_feedback())
    assert decision["kind"] == "execution_fault" and decision["reason"]


@pytest.mark.parametrize("field,value", [("condition", "different"), ("sampling_seed", 202610100443),
    ("first_member", "member_003"), ("diagnostic_a_owner", "member_003"), ("case_id", "different-root")])
def test_summary_cannot_relabel_original_pairing_coordinates(field, value):
    rows = complete_rows()
    rows[0][field] = value
    with pytest.raises(ValueError, match="pairing"):
        resume.summarize_rows(rows)


def test_direct_release_cannot_launch_the_original_first_block_or_any_new_inventory(tmp_path):
    for worker in (original.FIRST_BLOCK, "block-r2-s0", "diagnostic-first-block"):
        with pytest.raises(ValueError, match="Only original"):
            resume.require_worker_release(tmp_path, worker, {})


def test_worker_output_must_be_the_one_fresh_canonical_remaining_block(tmp_path):
    root = tmp_path / "continuation"
    worker = resume.WORKERS[0]
    output = root / worker / "actual"
    assert resume.validate_worker_target(root, worker, output) == (root.resolve(), output.resolve())
    assert not root.exists()  # Validation itself cannot create an execution trace.
    for wrong in (tmp_path / "another-run", root / resume.WORKERS[1] / "actual", root / worker / "second-attempt"):
        with pytest.raises(ValueError, match="unique original"):
            resume.validate_worker_target(root, worker, wrong)
    with pytest.raises(ValueError, match="unique original"):
        resume.validate_worker_target(root, original.FIRST_BLOCK, root / original.FIRST_BLOCK / "actual")
    output.mkdir(parents=True)
    with pytest.raises(FileExistsError, match="may not be replayed"):
        resume.validate_worker_target(root, worker, output)


def test_worker_output_cannot_escape_through_a_block_directory_symlink(tmp_path):
    root, outside = tmp_path / "continuation", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    worker = resume.WORKERS[0]
    (root / worker).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="unique original"):
        resume.validate_worker_target(root, worker, root / worker / "actual")
    assert not (outside / "actual").exists()
