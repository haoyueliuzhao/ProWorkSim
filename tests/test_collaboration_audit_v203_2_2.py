import copy
import pytest
from proworksim.software_collaboration_audit_v203_2_2 import agreement, validate_annotation


def sample():
    window = {"window_id": "task-s20", "cutoff": {"sequence": 20}}
    row = {"window_id": "task-s20", "cutoff_sequence": 20, "reviewer_id": "A",
           "reviewer_kind": "independent_ai_auxiliary", "human_gold": False,
           "dependency": "PRESENT", "unmet_need": "UNKNOWN", "misalignment": "UNKNOWN",
           "decision": "ABSTAIN", "confidence": .6, "rationale": "No evidence of unmet need",
           "issues": {key: [] for key in ("technical", "information", "organization", "resource")},
           "evidence_for": [{"sequence": 20, "reason": "handoff receipt only"}], "evidence_against": []}
    return row, window


def test_unknown_is_not_negative_and_dependency_is_not_intervention():
    row, window = sample()
    assert validate_annotation(row, window)["runtime_actions"] == 0
    for decision in ("NO_CHANGE", "INTERVENE"):
        changed = dict(row, decision=decision)
        with pytest.raises(ValueError):
            validate_annotation(changed, window)


def test_reject_future_evidence_and_mismatched_window():
    row, window = sample()
    row["evidence_for"][0]["sequence"] = 21
    with pytest.raises(ValueError):
        validate_annotation(row, window)
    row, window = sample()
    row["window_id"] = "different"
    with pytest.raises(ValueError):
        validate_annotation(row, window)


def test_ai_cannot_claim_human_gold():
    row, window = sample()
    row["human_gold"] = True
    with pytest.raises(ValueError):
        validate_annotation(row, window)


def test_agreement_keeps_unknown_and_undefined_kappa():
    a, _ = sample()
    b = copy.deepcopy(a)
    r = agreement([a], [b])
    assert r["misalignment"]["left"] == {"UNKNOWN": 1}
    assert r["misalignment"]["cohen_kappa"] is None
    b["misalignment"] = "ABSENT"
    b["decision"] = "NO_CHANGE"
    assert agreement([a], [b])["disagreement_ids"] == [a["window_id"]]
    with pytest.raises(ValueError):
        agreement([a, a], [b])
