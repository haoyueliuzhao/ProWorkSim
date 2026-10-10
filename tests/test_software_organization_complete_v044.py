"""CPU-only inventory, scoped stop and three-phase accounting controls."""
import copy
from collections import Counter

import pytest

from scripts import software_organization_complete_v044 as complete
from scripts import software_organization_v044 as original


EXPECTED = {
    "block-r0-s0": ("sc-record-views-handoff-v040", 202610100441,
                    ("PB", "PT", "SB"), "member_002", "member_002"),
    "block-r0-s1": ("sc-record-views-handoff-v040", 202610100442,
                    ("PT", "SB", "ST"), "member_001", "member_002"),
    "block-r1-s1": ("sc-record-catalog-handoff-v040", 202610100442,
                    ("ST", "PB", "PT"), "member_002", "member_001"),
}
MAIN_CONTRASTS = ("information_main_effect", "framing_main_effect", "interaction")
PARTITIONS = ("retained_original_four", "retained_first_continuation_three", "new_original_remaining_nine")


def panel_rows():
    # Preserve the seven real endpoints, then give one synthetic new slot R=1.
    successes = {"org44-r1-s0-PT", "org44-r0-s0-ST", "org44-r0-s1-PB", "org44-r1-s1-ST"}
    rows = []
    for serial, unit in enumerate((u for block in complete.all_assignments().values() for u in block), 1):
        rows.append({**copy.deepcopy(unit), "status": "closed", "R": int(unit["slot_id"] in successes),
            "submitted": unit["slot_id"] in successes,
            "usage": {"decisions": serial + 1, "attempts": serial, "prompt_tokens": 10 * serial,
                "completion_tokens": serial, "total_tokens": 11 * serial, "output_bearing_calls": serial,
                "budget_charged_tokens": 11 * serial, "uncertain_usage_attempts": 0},
            "team_budget": {"tests": {"used": serial % 3}}})
    return rows


def three_phase_fixture(tmp_path, *, new_started=True):
    old, previous, root = (tmp_path / name for name in ("original", "first-continuation", "completion"))
    rows = {row["slot_id"]: row for row in panel_rows()}
    inventories = [({complete.FIRST_BLOCK: complete.all_assignments()[complete.FIRST_BLOCK]}, old, (13,)),
        ({w: complete.all_assignments()[w][:1] for w in complete.WORKERS}, previous, (17, 19, 23)),
        (complete.assignments(), root, (31, 37, 41))]
    for inventory, phase_root, seconds in inventories:
        active = phase_root != root or new_started
        states = {w: {"status": "complete" if active else "not_started",
                      "elapsed_gpu_seconds": elapsed if active else 0} for w, elapsed in zip(inventory, seconds)}
        complete.write(phase_root / "supervisor.json", {"status": "complete" if active else "prepared", "states": states})
        if not active:
            continue
        for worker, units in inventory.items():
            complete.write(phase_root / worker / "actual/report.json", {"new_actor_steps": 0, "new_critic_steps": 0})
            for unit in units:
                folder = phase_root / worker / "actual/episodes" / unit["slot_id"]
                complete.write(folder / "slot-result.json", rows[unit["slot_id"]])
                complete.write(folder / "feedback-loop.json", {"mechanism_gate_inputs": {"context_blocked_feedback_ids": []}})
    # Historical stop facts remain present but do not enter the new pause folder.
    complete.write(old / "first-block-gate.json", {"passed": False})
    complete.write(previous / "mechanism-stops/old-context.json", {"kind": "mechanism_fault", "slot_id": "org44-r0-s0-ST"})
    complete.write(tmp_path / "revised-gate.json", {"passed": True})
    corrected = {"revised_gate": complete.reference(tmp_path / "revised-gate.json"), "measurements_by_slot": {}}
    for unit in complete.all_assignments()[complete.FIRST_BLOCK]:
        path = old / complete.FIRST_BLOCK / "actual/episodes" / unit["slot_id"] / "feedback-loop.json"
        corrected["measurements_by_slot"][unit["slot_id"]] = complete.reference(path)
    complete.write(tmp_path / "corrected-summary.json", corrected)
    complete.write(root / "plan.json", {"original_run_root": str(old), "resume_run_root": str(previous),
        "correction_summary": complete.reference(tmp_path / "corrected-summary.json"),
        "source": {"code_commit": "completion-fixture"}, "original_execution_source": {"code_commit": "original-fixture"},
        "first_continuation_source": {"code_commit": "continuation-fixture"},
        "batch_stop_policy": {"R_or_submission_dependent": False}, "prior_local_context_assessment": {}})
    return root, old, previous


def test_only_original_nine_can_run_in_original_order_and_coordinates():
    assigned = complete.assignments()
    assert complete.WORKERS == tuple(EXPECTED)
    assert complete.all_assignments() == original.assignments()
    assert assigned == {w: original.assignments()[w][1:] for w in EXPECTED}
    new = [u for block in assigned.values() for u in block]
    old = original.assignments()[original.FIRST_BLOCK] + [original.assignments()[w][0] for w in EXPECTED]
    assert len(new) == len({u["slot_id"] for u in new}) == 9
    assert len(old) == 7 and not {u["slot_id"] for u in old} & {u["slot_id"] for u in new}
    assert {u["slot_id"] for u in old + new} == {u["slot_id"] for block in original.assignments().values() for u in block}
    assert Counter(u["condition"] for u in new) == {"SB": 2, "ST": 2, "PB": 2, "PT": 3}
    for worker, (case, seed, order, first, owner) in EXPECTED.items():
        assert tuple(u["condition"] for u in assigned[worker]) == order
        assert all((u["case_id"], u["sampling_seed"], u["first_member"], u["diagnostic_a_owner"])
                   == (case, seed, first, owner) for u in assigned[worker])


def test_completion_caps_preserve_per_episode_limits_and_do_not_transfer_old_tokens():
    assert complete.GPU_ORDER == (3, 4, 5, 7)
    assert complete.LIMITS == {**original.LIMITS, "max_new_episodes": 9, "max_parallel_model_instances": 3}
    caps = complete.budget_caps()
    assert caps["old_actual"] == {"decisions": 267, "attempts": 256, "total_tokens": 3369138, "run_tests": 26}
    assert caps["new"] == {"decisions": 1152, "attempts": 1152, "total_tokens": 4500000, "run_tests": 288}
    assert caps["combined"] == {"decisions": 1419, "attempts": 1408, "total_tokens": 7869138, "run_tests": 314}
    assert caps["transfer_old_unused"] is False and caps["unused_old_tokens"] == 130862


def test_three_phases_preserve_original_four_block_pairing_and_equal_weights():
    rows = panel_rows()
    before = copy.deepcopy(rows)
    result = complete.summarize_rows(rows)
    assert rows == before and len(result["paired_blocks"]) == 4
    assert all(block["complete"] for block in result["paired_blocks"])
    assert [result["full_inventory_mean_contrasts"][k] for k in MAIN_CONTRASTS] == [0, .25, -.5]
    assert {c: x["mean_R"] for c, x in result["by_condition"].items()} == {"SB": 0, "ST": .5, "PB": .25, "PT": .25}


@pytest.mark.parametrize("status", ["not_started", "running", "technical_unknown"])
def test_any_unobserved_new_endpoint_keeps_primary_four_block_estimates_null(status):
    rows = panel_rows()
    missing = next(r for r in rows if r["slot_id"] == "org44-r0-s0-PT")
    missing.update(status=status, R=None, submitted=None)
    result = complete.summarize_rows(rows)
    assert missing["R"] is None
    assert all(result["full_inventory_mean_contrasts"][k] is None for k in MAIN_CONTRASTS)
    assert result["by_condition"]["PT"]["mean_R"] is None
    assert sum(block["complete"] for block in result["paired_blocks"]) == 3


@pytest.mark.parametrize("mutation", ["missing", "old_four_again", "previous_three_again", "new_id"])
def test_merge_refuses_replays_or_changed_inventory(mutation):
    rows = panel_rows()
    if mutation == "missing":
        rows.pop()
    elif mutation == "new_id":
        rows[-1]["slot_id"] = "org45-unregistered-PT"
    else:
        replay_ids = ({u["slot_id"] for u in original.assignments()[original.FIRST_BLOCK]}
            if mutation == "old_four_again" else {original.assignments()[w][0]["slot_id"] for w in EXPECTED})
        rows.extend(copy.deepcopy([r for r in rows if r["slot_id"] in replay_ids]))
    with pytest.raises(ValueError, match="sixteen distinct"):
        complete.summarize_rows(rows)


def test_three_phase_results_count_each_row_and_each_worker_occupancy_once(tmp_path):
    root, old, previous = three_phase_fixture(tmp_path)
    historical = {p: p.read_bytes() for base in (old, previous) for p in base.rglob("*.json")}
    result = complete.results(root)
    assert result["scheduled"] == result["known"] == 16 and result["new_scheduled"] == result["new_known"] == 9
    assert result["retained"] == 7 and len({r["slot_id"] for r in result["rows"]}) == 16
    assert Counter(r["execution_phase"] for r in result["rows"]) == dict(zip(PARTITIONS, (4, 3, 9)))
    assert len(result["workers"]) == 7
    assert all(f"{phase}/{worker}" in result["workers"] for phase in ("first_continuation", "completion") for worker in EXPECTED)
    assert [result["cost_partitions"][p]["recorded_usage"]["total_tokens"] for p in PARTITIONS] == [462, 209, 825]
    assert [result["cost_partitions"][p]["closed_worker_gpu_seconds"] for p in PARTITIONS] == [13, 59, 109]
    cost = result["cost"]
    assert (cost["recorded_usage"]["decisions"], cost["recorded_usage"]["attempts"], cost["recorded_usage"]["total_tokens"]) == (152, 136, 1496)
    assert cost["run_tests"] == 16 and cost["closed_worker_gpu_seconds"] == 181 and not cost["cost_incomplete"]
    assert result["original_first_block_gate"]["passed"] is False and result["first_block_gate"]["passed"] is True
    assert len(result["historical_first_continuation_stops"]) == 1 and result["mechanism_pauses"] == []
    assert all(p.read_bytes() == content for p, content in historical.items())


def test_prepared_completion_preserves_seven_results_and_nine_unstarted_without_zero_rewards(tmp_path):
    root, _, _ = three_phase_fixture(tmp_path, new_started=False)
    result = complete.results(root)
    assert result["known"] == 7 and result["new_known"] == 0
    new = [r for r in result["rows"] if r["execution_phase"] == PARTITIONS[-1]]
    assert len(new) == 9 and all(r["status"] == "not_started" and r["R"] is None for r in new)
    assert all(result["full_inventory_mean_contrasts"][k] is None for k in MAIN_CONTRASTS)
    assert result["cost"]["recorded_usage"]["total_tokens"] == 671
    assert result["cost"]["closed_worker_gpu_seconds"] == 72 and not result["cost"]["cost_incomplete"]


def test_unclosed_new_slot_keeps_recorded_cost_and_unknown_reward(tmp_path):
    root, _, _ = three_phase_fixture(tmp_path)
    slot = complete.assignments()[complete.WORKERS[0]][0]["slot_id"]
    folder = root / complete.WORKERS[0] / "actual/episodes" / slot
    row = complete.read(folder / "slot-result.json")
    complete.write(folder / "organization-evidence.json", {"total_usage": row["usage"], "team_budget": row["team_budget"]})
    (folder / "slot-result.json").unlink()
    result = complete.results(root)
    unknown = next(r for r in result["rows"] if r["slot_id"] == slot)
    assert unknown["status"] == "technical_unknown" and unknown["R"] is None
    assert result["known"] == 15 and result["cost"]["recorded_usage"]["total_tokens"] == 1496
    assert result["cost"]["cost_incomplete"] is True
    assert all(result["full_inventory_mean_contrasts"][k] is None for k in MAIN_CONTRASTS)


def test_result_identity_collision_cannot_be_hidden_by_dict_indexing(tmp_path):
    root, _, _ = three_phase_fixture(tmp_path)
    slot = complete.assignments()[complete.WORKERS[0]][0]["slot_id"]
    path = root / complete.WORKERS[0] / "actual/episodes" / slot / "slot-result.json"
    row = complete.read(path)
    row["slot_id"] = "org44-r1-s0-PT"
    complete.write(path, row)
    with pytest.raises(ValueError, match="sixteen distinct"):
        complete.results(root)


def test_entry_requires_one_fresh_canonical_worker_output(tmp_path):
    root, worker = tmp_path / "completion", complete.WORKERS[0]
    output = root / worker / "actual"
    assert complete.validate_worker_target(root, worker, output) == (root, output)
    assert not root.exists()
    for bad in (tmp_path / "alternate", root / worker / "retry", root / complete.WORKERS[1] / "actual"):
        with pytest.raises(ValueError, match="unique original"):
            complete.validate_worker_target(root, worker, bad)
    with pytest.raises(ValueError, match="unique original"):
        complete.validate_worker_target(root, complete.FIRST_BLOCK, root / complete.FIRST_BLOCK / "actual")
    output.mkdir(parents=True)
    with pytest.raises(FileExistsError, match="may not be replayed"):
        complete.validate_worker_target(root, worker, output)


def test_neither_historical_root_nor_its_descendants_can_be_completion_output(tmp_path):
    historical = (tmp_path / "original", tmp_path / "first-continuation")
    for old in historical:
        for root in (old, old / "new-attempt"):
            with pytest.raises(ValueError, match="immutable"):
                complete.validate_new_root(root, historical)
    fresh = tmp_path / "completion"
    assert complete.validate_new_root(fresh, historical) == fresh
    assert not any(p.exists() for p in (*historical, fresh))


def test_canonical_worker_output_cannot_escape_through_symlink(tmp_path):
    root, outside = tmp_path / "completion", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    worker = complete.WORKERS[0]
    (root / worker).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="unique original"):
        complete.validate_worker_target(root, worker, root / worker / "actual")
    assert not (outside / "actual").exists()


@pytest.mark.parametrize("reward", [0, 1])
def test_bound_local_context_receipt_does_not_pause_independent_work_or_edit_episode(tmp_path, monkeypatch, reward):
    root, worker = tmp_path / "completion", complete.WORKERS[0]
    slot = complete.assignments()[worker][0]["slot_id"]
    folder = root / worker / "actual/episodes" / slot
    row = {"slot_id": slot, "status": "closed", "R": reward, "submitted": bool(reward)}
    feedback = {"mechanism_gate_inputs": {"context_blocked_feedback_ids": ["unseen-feedback"]}}
    complete.write(folder / "slot-result.json", row)
    complete.write(folder / "feedback-loop.json", feedback)
    originals = {p: p.read_bytes() for p in folder.iterdir()}
    assessment = {"slot_id": slot, "decision": "continue", "local_context_events": [{"feedback_id": "unseen-feedback"}]}
    assert complete.record_policy_assessment(root, worker, slot, folder, assessment) is None
    assert complete.read(folder / "batch-stop-assessment.json") == assessment
    assert complete.mechanism_pauses(root) == []
    monkeypatch.setattr(complete, "checked", lambda ref: ref)
    monkeypatch.setattr(complete, "validate_qualification", lambda path: {"passed": True})
    complete.require_worker_release(root, complete.WORKERS[1], {"qualification": "fixture"})
    assert all(p.read_bytes() == content for p, content in originals.items())


@pytest.mark.parametrize("decision", ["global_pause", "measurement_pending"])
def test_global_or_unresolved_assessment_pauses_unopened_work(tmp_path, monkeypatch, decision):
    root, worker = tmp_path / "completion", complete.WORKERS[0]
    slot = complete.assignments()[worker][0]["slot_id"]
    folder = root / worker / "actual/episodes" / slot
    complete.write(folder / "slot-result.json", {"slot_id": slot})
    complete.write(folder / "feedback-loop.json", {})
    assessment = {"slot_id": slot, "decision": decision}
    assert complete.record_policy_assessment(root, worker, slot, folder, assessment) == decision
    markers = complete.mechanism_pauses(root)
    assert len(markers) == 1 and complete.read(markers[0])["kind"] == decision
    assert complete.checked(complete.read(markers[0])["assessment"]) == folder / "batch-stop-assessment.json"
    monkeypatch.setattr(complete, "checked", lambda ref: ref)
    monkeypatch.setattr(complete, "validate_qualification", lambda path: {"passed": True})
    with pytest.raises(ValueError, match="paused"):
        complete.require_worker_release(root, complete.WORKERS[1], {"qualification": "fixture"})


def test_policy_receipts_cannot_write_old_slots_or_replace_existing_assessment(tmp_path):
    root, worker = tmp_path / "completion", complete.WORKERS[0]
    old_slot = complete.all_assignments()[worker][0]["slot_id"]
    with pytest.raises(ValueError, match="unique new slot"):
        complete.record_policy_assessment(root, worker, old_slot, root / worker / "actual/episodes" / old_slot,
                                          {"slot_id": old_slot, "decision": "continue"})
    assert not root.exists()
    slot = complete.assignments()[worker][0]["slot_id"]
    folder = root / worker / "actual/episodes" / slot
    assessment = {"slot_id": slot, "decision": "continue"}
    for bad_folder, bad_assessment in ((tmp_path / "outside", assessment),
            (folder, {"slot_id": old_slot, "decision": "continue"}),
            (folder, {"slot_id": slot, "decision": "unknown"})):
        with pytest.raises(ValueError, match="unique new slot"):
            complete.record_policy_assessment(root, worker, slot, bad_folder, bad_assessment)
    assert not root.exists()
    complete.record_policy_assessment(root, worker, slot, folder, assessment)
    with pytest.raises(FileExistsError, match="overwrite"):
        complete.record_policy_assessment(root, worker, slot, folder, assessment)
