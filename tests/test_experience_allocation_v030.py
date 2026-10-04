"""Synthetic CPU proofs of the visible first-order rule, not model gain tests."""
import copy
import inspect
import math

import pytest

from proworksim import experience_allocation_v030 as allocation

BINDING = {"window_id": "current", "situation_id": "case-a", "member_id": "member-a"}


def history(q, *, coordinates="original_member_trajectory", initial=False):
    return allocation.freeze_history_anchor(
        q, binding=BINDING, coordinate_system=coordinates,
        source_window_id="current" if initial else "previous",
        source_configuration_sha256="a" * 64,
        transport_rule="synthetic frozen identity transport on unchanged support",
        kind="declared_initial_configuration" if initial else "transported_previous_configuration",
    )


def limits(**changes):
    return {**allocation.DEFAULT_CONSTRAINTS, **changes}


def objective(q, c, h, r, configuration):
    n = {key: max(0, math.log(r[key] / h[key])) for key in q}
    return math.fsum(q[key] * (c[key] + configuration["beta"] * n[key])
                     - configuration["lambda_h"] * q[key] * math.log(q[key] / h[key])
                     - configuration["lambda_r"] * q[key] * math.log(q[key] / r[key])
                     for key in q)


def test_simplex_closed_form_uses_distinct_history_and_both_positive_anchors():
    b = {"s1": 0.5, "s2": 0.3, "s3": 0.2}
    h = {"s1": 0.2, "s2": 0.4, "s3": 0.4}
    r = {"s1": 0.3, "s2": 0.2, "s3": 0.5}
    c = {"s1": 0.7, "s2": -0.2, "s3": 0.1}
    configuration = limits(lower=0.01, upper=100, tv_limit=1, lambda_h=0.7, lambda_r=1.3,
                           beta=0.6)
    result = allocation.solve_first_order(b, c, r, history=history(h), binding=BINDING,
                                           constraints=configuration)
    n = {key: max(0, math.log(r[key] / h[key])) for key in h}
    expected = {key: h[key] ** 0.35 * r[key] ** 0.65
                * math.exp((c[key] + 0.6 * n[key]) / 2) for key in h}
    total = sum(expected.values())
    expected = {key: value / total for key, value in expected.items()}
    assert result["q"] == pytest.approx(expected, abs=1e-11)
    assert result["objective"] == pytest.approx(objective(result["q"], c, h, r, configuration))
    assert result["N"] == pytest.approx(n)
    assert result["history_anchor"]["distribution"] != result["base"]
    assert result["tv_multiplier"] == 0
    assert result["rule"]["tv_center"] == "explicit_history"
    assert result["training_updates"] == 0 and not result["effectiveness_evidence"]


def test_one_coordinate_and_zero_radius_preserve_declared_feasible_history():
    one = {"only": 1.0}
    result = allocation.solve_g_raw(one, {"only": 4.0}, history=history(one), binding=BINDING)
    assert result["q"] == one and result["weights"] == one
    assert result["N"] == {"only": 0}
    assert result["tv"] == result["kl_history"] == result["kl_coverage"] == 0
    b, h = {"a": 0.5, "b": 0.5}, {"a": 0.6, "b": 0.4}
    fixed = allocation.solve_g_raw(b, {"a": -100, "b": 100}, history=history(h),
                                   binding=BINDING, constraints=limits(tv_limit=0))
    assert fixed["q"] == h
    assert fixed["weights"] == {"a": 1.2, "b": 0.8}
    assert fixed["tv"] == 0
    assert fixed["tv_from_base_diagnostic"] == pytest.approx(0.1)


def test_log_deficit_uses_history_not_observed_base_frequency():
    h, r = {"a": 0.8, "b": 0.2}, {"a": 0.5, "b": 0.5}
    assert allocation.log_novelty(h, r) == pytest.approx({"a": 0, "b": math.log(2.5)})
    assert allocation.log_novelty(h, h) == {"a": 0, "b": 0}
    b = {"a": 0.5, "b": 0.5}
    result = allocation.solve_g_raw(b, dict.fromkeys(b, 0), history=history(h), binding=BINDING,
                                   constraints=limits(lower=0.2, tv_limit=1, beta=0))
    assert result["q"]["a"] == pytest.approx(2 / 3, abs=1e-11)
    assert result["N"] != allocation.log_novelty(b, r)


def test_tight_box_and_history_tv_solution_dominates_a_feasible_grid():
    b = {"a": 0.5, "b": 0.3, "c": 0.2}
    h = {"a": 0.45, "b": 0.3, "c": 0.25}
    r = dict.fromkeys(b, 1 / 3)
    c = {"a": -2.0, "b": 0.2, "c": 4.0}
    configuration = limits(lower=0.8, upper=1.3, tv_limit=0.07)
    result = allocation.solve_first_order(b, c, r, history=history(h), binding=BINDING,
                                           constraints=configuration)
    assert sum(result["q"].values()) == pytest.approx(1, abs=1e-12)
    assert result["tv"] <= configuration["tv_limit"] + 1e-12
    assert all(0.8 - 1e-12 <= weight <= 1.3 + 1e-12 for weight in result["weights"].values())
    for i in range(80, 131):
        for j in range(48, 79):
            q = {"a": i / 200, "b": j / 200, "c": (200 - i - j) / 200}
            if any(q[key] < 0.8 * b[key] or q[key] > 1.3 * b[key] for key in b):
                continue
            if sum(abs(q[key] - h[key]) for key in b) / 2 > configuration["tv_limit"]:
                continue
            assert objective(q, c, h, r, configuration) <= result["objective"] + 1e-10
    trust = allocation.solve_g_raw(
        b, c, history=history(h), binding=BINDING,
        constraints=limits(lower=0.1, upper=5, tv_limit=0.02),
    )
    assert trust["tv"] == pytest.approx(0.02, abs=1e-11)
    assert trust["tv_multiplier"] > 0
    boxed = allocation.solve_g_raw(
        b, c, history=history(b), binding=BINDING,
        constraints=limits(lower=1, upper=1, tv_limit=1),
    )
    assert boxed["q"] == b


def test_history_is_mandatory_bound_and_never_silently_projected_or_reset_to_base():
    b = {"a": 0.5, "b": 0.5}
    c = {"a": 0.0, "b": 0.0}
    initial = history(b, initial=True)
    assert initial["kind"] == "declared_initial_configuration"
    assert history(b)["kind"] == "transported_previous_configuration"
    with pytest.raises(TypeError):
        allocation.solve_g_raw(b, c, binding=BINDING)
    changed = copy.deepcopy(initial)
    changed["distribution"]["a"] += 0.01
    with pytest.raises(ValueError, match="changed"):
        allocation.solve_g_raw(b, c, history=changed, binding=BINDING)
    with pytest.raises(ValueError, match="exact current window"):
        allocation.solve_g_raw(b, c, history=initial, binding={**BINDING, "window_id": "other"})
    with pytest.raises(ValueError, match="exact support"):
        allocation.solve_g_raw(b, c, history=history({"different": 1}), binding=BINDING)
    with pytest.raises(ValueError, match="explicitly transferred"):
        allocation.solve_g_raw(b, c, history=history({"a": 0.99, "b": 0.01}), binding=BINDING)
    with pytest.raises(ValueError, match="coordinate system"):
        allocation.solve_i_p(b, c, b, history=initial, binding=BINDING)


@pytest.mark.parametrize("bad", [0, -0.1, float("nan"), float("inf"), True, None])
def test_nonpositive_or_unknown_support_is_rejected_without_smoothing(bad):
    with pytest.raises(ValueError, match="positive finite normalized"):
        allocation.log_novelty({"a": bad, "b": 1}, {"a": 0.5, "b": 0.5})


def test_unknown_contribution_and_nonpositive_anchor_are_not_filled_in():
    b = {"a": 0.5, "b": 0.5}
    with pytest.raises(ValueError, match="unknown is not zero"):
        allocation.solve_g_raw(b, {"a": None, "b": 0}, history=history(b), binding=BINDING)
    with pytest.raises(ValueError, match="positive history/coverage"):
        allocation.solve_g_raw(b, dict.fromkeys(b, 0), history=history(b), binding=BINDING,
                               constraints=limits(lambda_h=0))


def test_g_raw_is_class_free_while_g_lift_and_i_p_name_their_shared_class_prior():
    b = {"t1": 0.25, "t2": 0.25, "t3": 0.25, "t4": 0.25}
    c = {"t1": 1, "t2": -1, "t3": 0, "t4": 0}
    classes = {"t1": "majority", "t2": "majority", "t3": "majority", "t4": "minority"}
    class_b = {"majority": 0.75, "minority": 0.25}
    class_r = dict.fromkeys(class_b, 0.5)
    parameters = inspect.signature(allocation.solve_g_raw).parameters
    assert not {"classes", "class_by_trajectory", "class_coverage", "graph", "support"} & set(parameters)
    raw = allocation.solve_g_raw(b, c, history=history(b), binding=BINDING)
    assert raw["coverage_anchor"] == b
    assert raw["N"] == dict.fromkeys(b, 0)
    assert not raw["semantic_class_input_used"] and not raw["class_shared_weights"]
    with pytest.raises(TypeError):
        allocation.solve_g_raw(b, c, history=history(b), binding=BINDING,
                               class_by_trajectory=classes)
    lifted = allocation.solve_g_lift(b, c, classes, class_r, history=history(b), binding=BINDING)
    assert lifted["coverage_anchor"] == pytest.approx({"t1": 1 / 6, "t2": 1 / 6, "t3": 1 / 6, "t4": 0.5})
    assert lifted["weights"]["t1"] != pytest.approx(lifted["weights"]["t2"])
    assert lifted["semantic_class_input_used"] and not lifted["class_shared_weights"]
    structured = allocation.solve_i_p(
        class_b, dict.fromkeys(class_b, 0), class_r,
        history=history(class_b, coordinates="member_class"), binding=BINDING,
    )
    weights = allocation.materialize_class_weights(structured, classes)
    assert weights["t1"] == weights["t2"] == weights["t3"]
    assert structured["class_shared_weights"] and structured["semantic_class_input_used"]
    assert structured["method"] == "I-P" and lifted["method"] == "G-lift" and raw["method"] == "G-raw"


def test_g_lift_and_i_p_agree_for_class_constant_contributions_and_lifted_history():
    raw_b = {"s1": 0.4, "s2": 0.2, "s3": 0.4}
    classes = {"s1": "x", "s2": "x", "s3": "y"}
    class_b, class_h = {"x": 0.6, "y": 0.4}, {"x": 0.5, "y": 0.5}
    raw_h = {"s1": 1 / 3, "s2": 1 / 6, "s3": 0.5}
    class_r, c = {"x": 0.4, "y": 0.6}, {"x": -0.3, "y": 0.7}
    lifted = allocation.solve_g_lift(
        raw_b, {sid: c[z] for sid, z in classes.items()}, classes, class_r,
        history=history(raw_h), binding=BINDING,
    )
    structured = allocation.solve_i_p(
        class_b, c, class_r, history=history(class_h, coordinates="member_class"), binding=BINDING,
    )
    weights = allocation.materialize_class_weights(structured, classes)
    assert lifted["weights"] == pytest.approx(weights, abs=1e-11)
    assert lifted["objective"] == pytest.approx(structured["objective"], abs=1e-11)
