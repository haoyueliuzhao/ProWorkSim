from copy import deepcopy

import pytest

from proworksim.software_communication_admission_v157 import (
    DEPLOYMENT_GATES, REQUIRED_GATES, VERSION, assess_dispatch, assess_measurement,
    assess_wave, validate_amendment,
)


def grant():
    return {"version": VERSION, "source_attribution_basis": "local_fragment_estimate",
            "total_token_authority": "physical_provider_usage",
            "provider_exact_source_claim": False, "planned_tasks": 24,
            "planned_team_episodes": 72, "conditions": ["C0", "C1", "C2"],
            "organization_id": "REVIEW2", "team_input_output_token_cap": 5_000_000,
            "batch_input_output_token_upper_bound": 360_000_000,
            "cash_scope": "new_independent_shared_ledger", "old_ledgers_changed": False,
            "model_start_authorized": True, "completion_guaranteed_by_cash_cap": False,
            "cash_cap_CNY": "500.00", "user_response": "继续，预算为500元",
            "answered_question": "API总账精确、来源分账标为估算；本轮预算？"}


def measurement():
    return {"gates": {**dict.fromkeys(REQUIRED_GATES, True), "G0-2-provider-exact": False},
            "payload_local_estimated_unattributed_fraction": 0.0,
            "payload_local_estimated_request_p95": 0.0}


def test_revision_does_not_rewrite_precision_or_excuse_missing_usage():
    original = measurement()
    before = deepcopy(original)
    result = assess_measurement(original, grant())
    assert result["passed"] and not result["provider_exact_source_claim"]
    assert original == before and not original["gates"]["G0-2-provider-exact"]
    original["gates"]["G0-3"] = False
    assert not assess_measurement(original, grant())["passed"]


def test_local_unknown_thresholds_and_deployment_still_apply():
    value = measurement()
    value["payload_local_estimated_request_p95"] = 0.051
    assert not assess_measurement(value, grant())["passed"]
    assert not assess_dispatch(measurement(), grant(), {})["dispatch_enabled"]
    assert not assess_dispatch(measurement(), grant(), {})["passed"]
    bindings = {name: {"passed": True, "evidence": {"path": name, "sha256": "a"*64}}
                for name in DEPLOYMENT_GATES}
    assert assess_dispatch(measurement(), grant(), bindings)["dispatch_enabled"]


def test_shared_cash_and_score_blind_wave_progress():
    bad = grant()
    bad["cash_scope"] = "500_per_condition"
    with pytest.raises(ValueError):
        validate_amendment(bad)
    good = assess_wave(1, measurement(), grant(), planned_episodes=36,
                      terminal_episodes=36, unresolved_attempts=[{"slot": 3, "reason": "timeout"}],
                      frozen_source_verified=True, protocol_unchanged=True)
    assert good["advance_to_wave_2"] and not good["scores_consulted"]
    assert len(good["exceptions_deferred"]) == 1
