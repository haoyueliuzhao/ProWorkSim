"""Same-candidate updates must preserve the prior v058 repairs and unknowns."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reconcile_v060", ROOT / "tools/reconcile_legacy_requests_rescore_v060.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def evidence():
    old_test = importlib.util.spec_from_file_location("prior_evidence_fixture", ROOT / "tests/test_ref_grading_environment_repair_v058.py")
    helper = importlib.util.module_from_spec(old_test)
    old_test.loader.exec_module(helper)
    state, _, outcomes = helper.fixture()
    conditions = ("REF_B0500K", "REF_B2000K", "REF_B5000K", "REF_B10000K")
    planned = []
    for index, (row, outcome) in enumerate(zip(state["rows"][:8], outcomes[:8], strict=True)):
        task, condition = sorted(repair.TASKS)[index // 4], conditions[index % 4]
        row["slot"].update(instance_id=task, condition_id=condition)
        row["environment_review"] = {"status": "unresolved"}
        outcome.update(instance_id=task, condition_id=condition)
        outcome["receipt"].update(condition_id=condition, version="v060")
        outcome["quiescence"]["condition_id"] = condition
        planned.append({"instance_id": task, "condition_id": condition, "slot_id": outcome["slot_id"]})
    for row in state["rows"][8:]:
        row["score"].update(resolved=True, scoring_revision="v058")
    return state, {"rows": planned}, outcomes[:8]


def test_eight_rescores_preserve_prior_repairs_and_generations():
    before, plan, outcomes = evidence()
    saved = copy.deepcopy(before)
    after, changed, unknown = repair.reconcile_evidence(before, copy.deepcopy(before), plan, outcomes)
    assert before == saved and len(changed) == 8 and unknown == []
    assert after["rows"][8:] == before["rows"][8:]
    assert all(a["generation"] == b["generation"] for a, b in zip(after["rows"], before["rows"], strict=True))
    assert not any("environment_review" in row for row in after["rows"][:8])


def test_cleanup_unknown_is_not_a_model_failure_or_success():
    before, plan, outcomes = evidence()
    outcomes[0]["quiescence"]["quiescent"] = False
    after, changed, unknown = repair.reconcile_evidence(before, copy.deepcopy(before), plan, outcomes)
    assert len(changed) == 7 and unknown == [outcomes[0]["slot_id"]]
    assert after["rows"][0]["score"] == before["rows"][0]["score"]
    measured = repair.legacy.measurement_state(after)
    assert measured["rows"][0]["score"]["resolved"] is None
    assert measured["rows"][0]["score"]["status"] == "technical_unknown"
    assert measured["rows"][8:] == before["rows"][8:]


def test_scope_and_candidate_substitution_fail_closed():
    before, plan, outcomes = evidence()
    wrong = copy.deepcopy(plan)
    wrong["rows"][0]["instance_id"] = "psf__requests-2931"
    with pytest.raises(ValueError, match="restricted"):
        repair.reconcile_evidence(before, copy.deepcopy(before), wrong, outcomes)
    outcomes[0]["receipt"]["original_patch"] = {"different_candidate": True}
    with pytest.raises(ValueError, match="Receipt does not bind"):
        repair.reconcile_evidence(before, copy.deepcopy(before), plan, outcomes)


def test_updated_queue_and_missing_outcome_are_rejected():
    before, plan, outcomes = evidence()
    prior = copy.deepcopy(before)
    before["new_external_write"] = True
    with pytest.raises(ValueError, match="state changed"):
        repair.reconcile_evidence(before, prior, plan, outcomes)
    with pytest.raises(ValueError, match="Every one"):
        repair.reconcile_evidence(before, copy.deepcopy(before), plan, outcomes[:-1])
