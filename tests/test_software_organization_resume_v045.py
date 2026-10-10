"""Only the original23 may execute; the retained first slot and costs survive."""

import copy

import pytest

from scripts import software_organization_resume_v045 as resume
from scripts import software_organization_v045 as original


def row(unit, *, R=1, status="closed"):
    return {**unit, "status": status, "R": R, "submitted": bool(R) if R is not None else None}


def groups():
    retained = [row(original.assignments()["block-r0-s0"][0])]
    new = [row(u) for units in resume.assignments().values() for u in units]
    return retained, new


def test_remaining_inventory_is_exact_original_order_without_first_slot():
    old = original.assignments()
    new = resume.assignments()
    assert list(new) == list(old) and sum(map(len, new.values())) == 23
    for worker in old:
        assert new[worker] == [u for u in old[worker] if u["slot_id"] != resume.RETAINED_SLOT]
    assert [u["condition"] for u in new["block-r0-s0"]] == ["F2", "O3"]
    assert len({u["slot_id"] for units in new.values() for u in units}) == 23
    assert resume.budget_caps()["combined"] == dict(
        decisions=2951, attempts=2951, total_tokens=11587890, run_tests=738
    )
    assert resume.budget_caps()["old_unused_tokens"] == 412110
    assert resume.budget_caps()["transfer_old_unused"] is False


def test_merge_retains_first_result_and_original_full_eight_block_denominator():
    retained, new = groups()
    before = copy.deepcopy(retained)
    ordered, summary = resume.merge_rows(retained, new)
    assert len(ordered) == 24 and retained == before
    assert ordered[0]["slot_id"] == resume.RETAINED_SLOT
    assert summary["full_inventory_mean_contrasts"] == {"F2_minus_S1": 0, "O3_minus_F2": 0}
    new[-1].update(status="not_started", R=None, submitted=None)
    _, summary = resume.merge_rows(retained, new)
    assert all(v is None for v in summary["full_inventory_mean_contrasts"].values())


@pytest.mark.parametrize("fault", ["replay", "duplicate", "retained_missing", "identity_changed"])
def test_merge_rejects_replay_or_corrupt_inventory_before_indexing(fault):
    retained, new = groups()
    if fault == "replay":
        new[-1] = copy.deepcopy(retained[0])
    elif fault == "duplicate":
        new[-1] = copy.deepcopy(new[0])
    elif fault == "retained_missing":
        retained = []
    else:
        new[-1]["sampling_seed"] += 1
    with pytest.raises(ValueError):
        resume.merge_rows(retained, new)


def test_local_policy_receipt_releases_only_an_unstarted_original_slot(tmp_path):
    root = tmp_path / "run"
    worker = "block-r0-s0"
    slot = resume.assignments()[worker][0]["slot_id"]
    folder = root / worker / "actual/episodes" / slot
    folder.mkdir(parents=True)
    assessment = {"slot_id": slot, "decision": "continue"}
    assert resume.record_policy_assessment(root, worker, slot, folder, assessment) is None
    assert not resume.mechanism_pauses(root)
    with pytest.raises(FileExistsError):
        resume.record_policy_assessment(root, worker, slot, folder, assessment)
    old_folder = root / worker / "actual/episodes" / resume.RETAINED_SLOT
    old_folder.mkdir()
    with pytest.raises(ValueError):
        resume.record_policy_assessment(
            root,
            worker,
            resume.RETAINED_SLOT,
            old_folder,
            {"slot_id": resume.RETAINED_SLOT, "decision": "continue"},
        )


def test_worker_target_cannot_reuse_original_or_existing_output(tmp_path):
    name = "block-r0-s0"
    root = tmp_path / "new"
    target = root / name / "actual"
    with pytest.raises(ValueError):
        resume.validate_worker_target(root, name, tmp_path / "old" / name / "actual")
    target.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        resume.validate_worker_target(root, name, target)
