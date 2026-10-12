"""Changed reader wiring must preserve missing evidence and the Gamma binding."""
import copy

import pytest

from proworksim.software_context_v048 import CANDIDATE_SHA256
from scripts import measure_organization_feedback_v048 as measurement


@pytest.mark.parametrize("gamma", ["Gamma0", "Gamma1"])
def test_missing_originals_remain_unresolved_under_bound_representation(tmp_path, gamma):
    result = measurement.measure_episode(tmp_path, representation=gamma,
                                         candidate_sha256=CANDIDATE_SHA256)
    assert result["version"] == measurement.VERSION
    assert result["status"] == "unresolved"
    assert result["representation"] == {
        "representation": gamma, "candidate_sha256": CANDIDATE_SHA256}
    assert result["mechanism_gate_inputs"]["resolved"] is False
    assert result["new_model_calls"] == result["new_tokenizer_calls"] == 0


def test_no_budget_evidence_does_not_reclassify_unknown_or_rewrite_input():
    baseline = {"status": "unresolved", "representation": {
        "representation": "Gamma1", "candidate_sha256": CANDIDATE_SHA256},
        "feedback_records": [{"feedback_id": "f1", "member": "member_001",
            "no_actual_followup": {"reason": "unknown_no_actual_followup"}}]}
    before = copy.deepcopy(baseline)
    result = measurement.apply_budget_revision(baseline, {}, [])
    assert result["feedback_records"] == before["feedback_records"]
    assert result["representation"] == before["representation"]
    assert baseline == before
