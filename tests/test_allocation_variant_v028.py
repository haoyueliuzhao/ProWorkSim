"""Reporting identities cannot change old probes, weights or selection arithmetic."""

import copy
import math

import pytest

from proworksim.experience_allocation_v027 import (
    ALLOCATION_VARIANT, select_allocation, solve_first_order,
)
from proworksim.storage import digest, json_bytes
from test_experience_allocation_v027 import fixture_window, linear_receipts, plan_for


def test_linear_N_base_anchor_and_G_prior_are_explicit_without_reselecting_old_results():
    _, _, _, supports, _ = fixture_window()
    plan = plan_for(supports, eligible=[["api-contract", "member-one"]])
    new = select_allocation(plan, linear_receipts(plan))
    assert new["allocation_variant"] == ALLOCATION_VARIANT
    assert ALLOCATION_VARIANT["history_configuration_inherited"] is False
    assert ALLOCATION_VARIANT["N_rule"] == "N_z = max(0, 1 - K * b_z)"
    assert "common support and coverage priors" in ALLOCATION_VARIANT["G_name"]
    # No new metadata is backfilled into an old unannotated frozen plan/report.
    old = copy.deepcopy(plan)
    del old["allocation_variant"]
    old["plan_sha256"] = digest(json_bytes({k: v for k, v in old.items() if k != "plan_sha256"}))
    old_result = select_allocation(old, linear_receipts(old))
    assert "allocation_variant" not in old_result
    assert old["candidates"] == plan["candidates"]
    for method in ("B", "G", "I"):
        assert old_result["selections"][method]["q_by_xi"] == new["selections"][method]["q_by_xi"]


def test_coordinate_slope_and_b_centered_contribution_differ_only_by_constant():
    _, _, _, supports, _ = fixture_window()
    plan = plan_for(supports, eligible=[["api-contract", "member-one"]])
    result = select_allocation(plan, linear_receipts(plan))
    for method in ("G", "I"):
        for solution in result["selections"][method]["solutions"]:
            g, c, b = (solution["helmert_zero_arithmetic_mean_slope"],
                       solution["b_centered_contribution"], solution["baseline_anchor"])
            assert g == solution["contribution"]
            assert math.fsum(g.values()) == pytest.approx(0, abs=1e-12)
            assert math.fsum(b[k] * c[k] for k in c) == pytest.approx(0, abs=1e-12)
            offset = solution["contribution_centering_offset"]
            assert all(g[k] - c[k] == pytest.approx(offset) for k in g)
            centered = solve_first_order(b, c, solution["coverage_anchor"], solution["N"],
                                        constraints=solution["constraints"])
            assert centered["q"] == pytest.approx(solution["q"], abs=1e-12)
