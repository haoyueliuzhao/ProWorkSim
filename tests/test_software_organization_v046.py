"""Necessary host-only four-pair accounting and scheduler boundary controls."""

import copy
from pathlib import Path

import pytest

from scripts import software_organization_v046 as trial
from scripts import software_organization_v045 as original


def groups():
    old = {u["slot_id"]: u for rows in original.assignments().values() for u in rows}
    base = [
        {**old[sid], "status": "closed", "R": 0, "submitted": False} for sid in trial.BASELINE_IDS
    ]
    new = [
        {**u, "status": "closed", "R": int(i == 0), "submitted": i == 0}
        for i, rows in enumerate(trial.assignments().values())
        for u in rows
    ]
    return base, new


def test_four_pairs_preserve_both_original_trigger_and_nontrigger_controls():
    baseline, new = groups()
    before = copy.deepcopy((baseline, new))
    value = trial.summarize_pairs(baseline, new)
    assert (baseline, new) == before and value["complete_pairs"] == 4
    assert value["mean_capacity_contrast"] == 0.25
    assert value["full_four_pair_comparison_complete"] is True
    assert {r["condition"] for r in new} == {"F2"}
    assert [r["first_member"] for r in new] == [
        "member_002",
        "member_001",
        "member_002",
        "member_001",
    ]


@pytest.mark.parametrize("status", ["not_started", "technical_unknown", "running"])
def test_unknown_or_unstarted_never_becomes_zero_or_partial_pair_mean(status):
    baseline, new = groups()
    new[-1].update(status=status, R=None, submitted=None)
    value = trial.summarize_pairs(baseline, new)
    assert value["complete_pairs"] == 3 and value["mean_capacity_contrast"] is None
    assert value["pairs"][-1]["difference"] is None


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "missing_nontrigger",
        "seed",
        "first",
        "old_R",
        "baseline_order",
        "condition",
        "context",
    ],
)
def test_pair_merge_rejects_selection_or_changed_identity(fault):
    baseline, new = groups()
    if fault == "duplicate":
        new[-1] = copy.deepcopy(new[0])
    elif fault == "missing_nontrigger":
        new.pop(1)
    elif fault == "seed":
        new[0]["sampling_seed"] += 1
    elif fault == "first":
        new[0]["first_member"] = "member_001"
    elif fault == "old_R":
        baseline[0]["R"] = 1
    elif fault == "baseline_order":
        baseline.reverse()
    elif fault == "condition":
        new[0]["condition"] = "O3"
    else:
        new[0]["context_limit"] = 32768
    with pytest.raises(ValueError):
        trial.summarize_pairs(baseline, new)


def test_resource_limits_reuse_original_and_only_authorized_gpu_queries(monkeypatch):
    assert trial.GPU_ORDER == (3, 4, 5, 7)
    assert trial.LIMITS == {**original.LIMITS, "max_new_episodes": 4}
    assert trial.LIMITS["max_parallel_model_instances"] == 3
    seen = []
    monkeypatch.setattr(trial, "target_resources", lambda selector, **kwargs: seen.append(selector))
    trial.allowed_resources()
    assert seen == ["3,4,5,7"]
    for gpu in (0, 1, 2, 6):
        with pytest.raises(ValueError):
            trial.worker_env({}, gpu)


def test_worker_output_is_unique_and_never_replays_a_started_treatment(tmp_path):
    worker = trial.WORKERS[0]
    root = tmp_path / "new"
    path = root / worker / "actual"
    assert trial.validate_worker_target(root, worker, path) == (root.resolve(), path.resolve())
    path.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        trial.validate_worker_target(root, worker, path)
    with pytest.raises(ValueError):
        trial.validate_worker_target(root, worker, tmp_path / "old" / worker / "actual")


@pytest.mark.parametrize("decision", ["continue", "measurement_pending", "global_pause"])
def test_local_or_integrity_policy_receipt_keeps_original_stop_scope(tmp_path, decision):
    root = tmp_path / "run"
    worker = trial.WORKERS[0]
    slot = trial.assignments()[worker][0]["slot_id"]
    folder = root / worker / "actual/episodes" / slot
    folder.mkdir(parents=True)
    for name in ("feedback-loop.json", "slot-result.json"):
        (folder / name).write_text("{}")
    out = trial.record_policy_assessment(
        root, worker, slot, folder, {"slot_id": slot, "decision": decision}
    )
    assert out == (None if decision == "continue" else decision)
    assert bool(trial.mechanism_pauses(root)) == (decision != "continue")
    with pytest.raises(FileExistsError):
        trial.record_policy_assessment(
            root, worker, slot, folder, {"slot_id": slot, "decision": decision}
        )
    old = trial.BASELINE_IDS[0]
    with pytest.raises(ValueError):
        trial.record_policy_assessment(
            root, worker, old, folder, {"slot_id": old, "decision": "continue"}
        )


def test_worker_interpreter_requires_sdk_prefix_even_if_binary_target_matches(tmp_path):
    binary = tmp_path / "python"
    binary.write_text("binary marker")
    sdk = tmp_path / "sdk"
    sdk.mkdir()
    sdkpython = sdk / "python"
    sdkpython.symlink_to(binary)
    plan = {"native_python": str(sdkpython), "native_python_prefix": str(sdk)}
    trial.validate_worker_interpreter(plan, executable=str(sdkpython), prefix=str(sdk))
    with pytest.raises(ValueError, match="SDK interpreter"):
        trial.validate_worker_interpreter(plan, executable=str(binary), prefix="/usr")
    other = tmp_path / "otherpython"
    other.write_text("different binary")
    with pytest.raises(ValueError, match="SDK interpreter"):
        trial.validate_worker_interpreter(plan, executable=str(other), prefix=str(sdk))
    assert Path(plan["native_python"]).is_absolute()
