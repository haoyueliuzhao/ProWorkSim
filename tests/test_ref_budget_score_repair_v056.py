"""Score repair may close scoring unknowns, never replace generation evidence."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v056_score_repair", ROOT / "tools/repair_ref_budget_scores_v056.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def fixtures():
    slot = {"slot_id": "one", "condition_id": "REF_B5000K"}
    old_request = {"path": "original-request"}
    old_score = {"status": "deferred", "dispatched_request": old_request,
                 "reason": "original UnicodeDecodeError", "job_id": "original-score-job"}
    state = {"binding": {"unchanged": True}, "rows": [
        {"slot": slot, "generation": {"status": "closed", "result": {"sha256": "frozen"}}, "score": old_score},
        {"slot": {"slot_id": "other"}, "generation": {"status": "deferred"}, "score": {"status": "not_applicable"}}],
        "jobs": {"original": "unchanged"}, "deferred": [
            {"slot_id": "one", "phase": "score", "reason": "original UnicodeDecodeError"},
            {"slot_id": "other", "phase": "generation", "reason": "original generation unknown"}]}
    transport = {"path": "equivalent-patch-receipt"}
    result = {"slot_id": "one", "condition_id": "REF_B5000K", "original_request": old_request,
        "request": {"path": "new-request"}, "patch_transport": transport,
        "receipt": {"slot_id": "one", "condition_id": "REF_B5000K", "status": "official_report",
            "resolved": True, "model_calls": 0, "actor_feedback": False, "candidate_changed": False,
            "scoring_recovery_of": old_request, "patch_transport": transport, "version": "new-scorer"},
        "quiescence": {"slot_id": "one", "condition_id": "REF_B5000K", "quiescent": True,
            "cleanup_errors": [], "create_result_unknown": False},
        "receipt_pointer": {"path": "new-score-pointer"}, "quiescence_reference": {"path": "new-quiescence"},
        "completion": {"path": "new-completion"}}
    return state, result


def test_merge_preserves_generation_slots_binding_and_original_failure():
    state, outcome = fixtures()
    before = copy.deepcopy(state)
    merged, changed = repair.reconciled_state(state, before, {"one"}, [outcome])
    assert state == before and changed == ["one"]
    assert merged["binding"] == state["binding"] and merged["jobs"] == state["jobs"]
    assert [(r["slot"], r["generation"]) for r in merged["rows"]] == [(r["slot"], r["generation"]) for r in state["rows"]]
    assert merged["rows"][0]["score"]["resolved"] is True
    assert merged["rows"][0]["prior_scoring_attempts"] == [state["rows"][0]["score"]]
    assert merged["resolved_deferred"] == [state["deferred"][0]]
    assert merged["deferred"] == [state["deferred"][1]]


@pytest.mark.parametrize("corruption", ["slot", "condition", "candidate", "state"])
def test_wrong_identity_or_changed_predecessor_is_rejected(corruption):
    state, outcome = fixtures()
    prior = copy.deepcopy(state)
    if corruption == "slot":
        outcome["receipt"]["slot_id"] = "wrong"
    elif corruption == "condition":
        outcome["quiescence"]["condition_id"] = "REF_B2000K"
    elif corruption == "candidate":
        outcome["receipt"]["patch_transport"] = {"path": "wrong-candidate"}
    else:
        state["rows"][0]["generation"]["result"] = {"sha256": "changed"}
    with pytest.raises(ValueError):
        repair.reconciled_state(state, prior, {"one"}, [outcome])


def test_unproved_quiescence_does_not_convert_unknown_to_failure():
    state, outcome = fixtures()
    outcome["quiescence"]["quiescent"] = False
    merged, changed = repair.reconciled_state(state, copy.deepcopy(state), {"one"}, [outcome])
    assert changed == [] and merged["rows"] == state["rows"]
    assert merged["deferred"] == state["deferred"]
