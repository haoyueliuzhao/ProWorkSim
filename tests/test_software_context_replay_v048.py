"""Finite inventory/admission gates only; no tokenizer/model/world execution."""
import copy

import pytest

from scripts.software_context_replay_v048 import (
    EXPECTED,
    inventory_counts,
    result_checks,
    validate_inventory,
)


def inventory_rows():
    rows = []
    for i in range(21):
        hard = i < 10
        row = {
            "call_id": f"call-{i}",
            "slot_id": f"slot-{i}",
            "kind": "hard_context_rejected" if hard else "final_fixed_submit",
            "root_id": "LA" if i < 8 or not hard else "HA",
            "condition": "P4" if hard else "S1",
            "targeted_LA_LB_P4": i < 8,
            "historical_preparation": {"context_limit": 18432, "reserved_output_tokens": 2048},
            "historical_generated": not hard,
            "final_fixed_submission": {"call_id": f"call-{i}"},
            "reference_integrity_checks": {"restored": True},
            "gamma1": {"selected": {"fits": i not in {8, 9}}},
        }
        rows.append(row)
    return rows


def test_frozen_21_and_only_eight_targets():
    rows = inventory_rows()
    assert inventory_counts(rows) == EXPECTED
    assert validate_inventory({"requests": rows}) is rows
    assert all(result_checks(rows, originals_complete=True, mechanical_passed=True).values())


def test_duplicate_and_wrong_target_cannot_enter_tokenizer_phase():
    rows = inventory_rows()
    rows[-1]["call_id"] = rows[0]["call_id"]
    with pytest.raises(ValueError, match="predeclared unique"):
        validate_inventory({"requests": rows})
    rows = inventory_rows()
    rows[0]["root_id"] = "HB"
    with pytest.raises(ValueError, match="Target set"):
        validate_inventory({"requests": rows})


@pytest.mark.parametrize("index,failed_key", [(0, "targeted_eight_hard_fit"), (20, "final_submit_eleven_hard_fit")])
def test_one_target_or_final_submit_overflow_closes_single_candidate(index, failed_key):
    rows = copy.deepcopy(inventory_rows())
    rows[index]["gamma1"]["selected"]["fits"] = False
    checks = result_checks(rows, originals_complete=True, mechanical_passed=True)
    assert checks[failed_key] is False
    assert not all(checks.values())


def test_original_binding_and_reference_evidence_are_required_separately():
    rows = inventory_rows()
    rows[4]["reference_integrity_checks"] = {"restored": False}
    checks = result_checks(rows, originals_complete=False, mechanical_passed=True)
    assert checks["original_all_bindings_reproduced"] is False
    assert checks["all_reference_integrity_passed"] is False
    assert checks["targeted_eight_hard_fit"] is True
