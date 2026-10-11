"""Original14 release, preserved local-stop semantics, and unique24 accounting."""

import copy
import json

import pytest

from scripts import software_organization_complete_v045 as complete
from scripts import software_organization_v045 as original
from scripts.run_ne_v021 import reference


def row(unit, *, R=1, status="closed"):
    return {**unit, "status": status, "R": R, "submitted": bool(R) if R is not None else None}


def groups():
    units = [u for rows in original.assignments().values() for u in rows]
    return (
        [row(u) for u in units if u["slot_id"] in complete.RETAINED_IDS],
        [row(u) for u in units if u["slot_id"] not in complete.RETAINED_IDS],
    )


def test_original_remaining14_preserves_full_seed_first_member_and_no_budget_transfer():
    inventory = complete.assignments()
    assert list(inventory) == list(complete.WORKERS)
    assert sum(map(len, inventory.values())) == 14
    assert [u["condition"] for u in inventory["block-r1-s1"]] == ["O3", "F2"]
    assert all(
        u["first_member"] == "member_001"
        for rows in inventory.values()
        for u in rows
        if u["condition"] == "S1"
    )
    assert complete.budget_caps()["new"]["total_tokens"] == 7000000
    assert complete.budget_caps()["combined"]["total_tokens"] == 9563352
    assert complete.budget_caps()["transfer_old_unused"] is False
    assert complete.LIMITS == {**original.LIMITS, "max_new_episodes": 14}


def test_full_original_denominator_only_after_all_required_results_known():
    retained, new = groups()
    before = copy.deepcopy(retained)
    ordered, summary = complete.merge_rows(retained, new)
    assert len(ordered) == 24 and retained == before
    assert summary["full_inventory_mean_contrasts"] == {"F2_minus_S1": 0, "O3_minus_F2": 0}
    new[-1].update(status="not_started", R=None, submitted=None)
    _, summary = complete.merge_rows(retained, new)
    assert all(v is None for v in summary["full_inventory_mean_contrasts"].values())


@pytest.mark.parametrize("fault", ["replay", "duplicate", "missing_retained", "identity_changed"])
def test_duplicate_replay_or_changed_identity_rejected(fault):
    retained, new = groups()
    if fault == "replay":
        new[-1] = copy.deepcopy(retained[-1])
    elif fault == "duplicate":
        new[-1] = copy.deepcopy(new[0])
    elif fault == "missing_retained":
        retained.pop()
    else:
        new[-1]["sampling_seed"] += 1
    with pytest.raises(ValueError):
        complete.merge_rows(retained, new)


@pytest.mark.parametrize("decision", ["continue", "measurement_pending", "global_pause"])
def test_same_policy_scope_releases_or_pauses_only_original_unopened_slots(tmp_path, decision):
    root = tmp_path / "run"
    worker = "block-r1-s1"
    slot = "org45-r1-s1-O3"
    folder = root / worker / "actual/episodes" / slot
    folder.mkdir(parents=True)
    for name in ("feedback-loop.json", "slot-result.json"):
        (folder / name).write_text("{}")
    result = complete.record_policy_assessment(
        root, worker, slot, folder, {"slot_id": slot, "decision": decision}
    )
    assert result == (None if decision == "continue" else decision)
    assert bool(complete.mechanism_pauses(root)) == (decision != "continue")
    with pytest.raises(FileExistsError):
        complete.record_policy_assessment(
            root, worker, slot, folder, {"slot_id": slot, "decision": decision}
        )
    with pytest.raises(ValueError):
        old = root / worker / "actual/episodes/org45-r1-s1-S1"
        complete.record_policy_assessment(
            root,
            worker,
            "org45-r1-s1-S1",
            old,
            {"slot_id": "org45-r1-s1-S1", "decision": "continue"},
        )


def test_worker_target_never_reuses_old_or_existing_outputs(tmp_path):
    root, name = tmp_path / "fresh", "block-r2-s0"
    target = root / name / "actual"
    with pytest.raises(ValueError):
        complete.validate_worker_target(root, name, tmp_path / "old" / name / "actual")
    target.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        complete.validate_worker_target(root, name, target)
    with pytest.raises(ValueError):
        complete.validate_worker_target(root, "block-r0-s0", root / "block-r0-s0/actual")


def test_only_authorized_physical_devices_and_three_residents(monkeypatch):
    assert (
        complete.GPU_ORDER == (3, 4, 5, 7) and complete.LIMITS["max_parallel_model_instances"] == 3
    )
    seen = []
    monkeypatch.setattr(
        complete, "target_resources", lambda selector, **kwargs: seen.append(selector)
    )
    complete.allowed_resources()
    assert seen == ["3,4,5,7"]
    for gpu in (0, 1, 2, 6):
        with pytest.raises(ValueError):
            complete.worker_env({}, gpu)


def test_three_phase_cost_counts_each_result_and_worker_once(tmp_path):
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return reference(path)

    old, prior, newroot = [tmp_path / name for name in ("first", "resume", "complete")]
    units = original.assignments()
    original_plan = save(old / "plan.json", {"assignments": units})
    all_units = [(worker, u) for worker, rows in units.items() for u in rows]
    review = []
    for worker, unit in all_units:
        identity = unit["slot_id"]
        folder = (
            old
            if identity == complete.RETAINED_IDS[0]
            else prior
            if identity in complete.RETAINED_IDS
            else newroot
        )
        ep = folder / worker / "actual/episodes" / identity
        value = {
            **row(unit),
            "usage": {
                "decisions": 1,
                "attempts": 1,
                "prompt_tokens": 9,
                "completion_tokens": 1,
                "total_tokens": 10,
                "output_bearing_calls": 1,
                "budget_charged_tokens": 10,
                "uncertain_usage_attempts": 0,
            },
            "team_budget": {"tests": {"used": 1}},
        }
        save(ep / "slot-result.json", value)
        feedback = save(ep / "feedback-loop.json", {})
        work = save(ep / "work-use.json", {})
        stop = save(ep / "batch-stop-assessment.json", {"decision": "continue"})
        if identity in complete.RETAINED_IDS:
            review.append(
                {
                    "slot_id": identity,
                    "old_feedback": feedback,
                    "revised_feedback": feedback,
                    "revised_work": work,
                    "old_stop": stop,
                    "revised_batch_stop": stop,
                }
            )
    old_state = {
        "status": "closed_with_unknowns",
        "states": {"block-r0-s0": {"attempted": True, "elapsed_gpu_seconds": 2}},
    }
    prior_workers = ("block-r0-s0", "block-r0-s1", "block-r1-s0", "block-r1-s1")
    prior_state = {
        "status": "closed_with_unknowns",
        "states": {w: {"attempted": True, "elapsed_gpu_seconds": 3} for w in prior_workers},
    }
    new_state = {
        "status": "complete",
        "states": {w: {"attempted": True, "elapsed_gpu_seconds": 5} for w in complete.WORKERS},
    }
    for root, state in ((old, old_state), (prior, prior_state), (newroot, new_state)):
        save(root / "supervisor.json", state)
    review_ref = save(tmp_path / "review.json", {"slots": review})
    save(
        newroot / "plan.json",
        {
            "original_run_root": str(old),
            "prior_run_root": str(prior),
            "original_plan": original_plan,
            "retained_review": review_ref,
            "assignments": complete.assignments(),
            "source": {},
            "original_execution_source": {},
            "source_partition": {},
            "batch_stop_policy": {},
            "optional_probe": {"enabled": False},
        },
    )
    result = complete.results(newroot)
    assert result["known"] == 24 and result["new_known"] == 14
    assert result["cost"]["recorded_usage"]["attempts"] == 24
    assert result["cost"]["recorded_usage"]["total_tokens"] == 240
    assert result["cost"]["run_tests"] == 24
    assert result["cost"]["closed_worker_gpu_seconds"] == 2 + 12 + 25
    assert len(result["workers"]) == 10
    assert [p["recorded_usage"]["attempts"] for p in result["cost_partitions"].values()] == [
        1,
        9,
        14,
    ]
