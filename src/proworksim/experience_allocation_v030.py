"""CPU first-order rule from the locally supplied design, sections 11.1--11.2.

This is a numerical rule and three separately named coordinate interfaces. It
does not execute contribution trials, certify support, bind training tokens or
modify the v0.27 runner. It is not a full implementation of an unavailable V1.3.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re

VERSION = "experience-allocation-v0.30-first-order-cpu"
DEFAULT_CONSTRAINTS = {
    "lower": 0.5, "upper": 2.0, "tv_limit": 0.2,
    "lambda_h": 1.0, "lambda_r": 1.0, "beta": 0.25,
}
RULE = {
    "source": "docs/reference/id-vtdo-v1-data-design.md#11",
    "scope": "visible_first_order_clauses_only_not_full_V1.3",
    "novelty": "max(log(coverage/history), 0)",
    "objective": "dot(q,C+beta*N)-lambda_h*KL(q||history)-lambda_r*KL(q||coverage)",
    "weight_ratio": "q/base",
    "tv_center": "explicit_history",
    "history_initialization": "explicitly_declared_and_bound_never_silently_set_to_base",
    "contribution_trials_executed": False,
    "effectiveness_evidence": False,
}


def _sha(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _distribution(value, name, keys=None):
    if (not isinstance(value, dict) or not value
            or any(not isinstance(key, str) or not key for key in value)
            or any(not _finite(v) or v <= 0 for v in value.values())
            or not math.isclose(math.fsum(value.values()), 1, rel_tol=0, abs_tol=1e-12)
            or keys is not None and set(value) != set(keys)):
        raise ValueError(name + " must be a positive finite normalized distribution on exact support")
    return {key: float(value[key]) for key in sorted(value)}


def _binding(value):
    if (not isinstance(value, dict) or set(value) != {"window_id", "situation_id", "member_id"}
            or any(not isinstance(v, str) or not v for v in value.values())):
        raise ValueError("Binding requires exact current window, situation and stable member")
    return copy.deepcopy(value)


def freeze_history_anchor(distribution, *, binding, coordinate_system, source_window_id,
                          source_configuration_sha256, transport_rule, kind):
    """Bind an already transferred history; do not invent missing support mass.

    A digest is a binding, not proof that the referenced historical computation
    ran. A future runner must check its source receipt and transfer procedure.
    """
    q = _distribution(distribution, "History")
    identity = _binding(binding)
    if coordinate_system not in {"original_member_trajectory", "member_class"}:
        raise ValueError("Freeze original member-trajectory or member-class coordinates")
    if (not isinstance(source_window_id, str) or not source_window_id
            or not isinstance(source_configuration_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", source_configuration_sha256) is None
            or not isinstance(transport_rule, str) or not transport_rule.strip()):
        raise ValueError("Historical source identity, configuration digest and transport rule required")
    if kind not in {"declared_initial_configuration", "transported_previous_configuration"}:
        raise ValueError("Declare initial history separately from transported previous history")
    if ((kind == "declared_initial_configuration")
            != (source_window_id == identity["window_id"])):
        raise ValueError("Initial history uses the current window; previous history names another window")
    result = {"version": VERSION, "binding": identity, "coordinate_system": coordinate_system,
              "distribution": q, "source_window_id": source_window_id,
              "source_configuration_sha256": source_configuration_sha256,
              "transport_rule": transport_rule, "kind": kind}
    result["history_sha256"] = _sha(result)
    return result


def _history(history, binding, keys, coordinate_system=None):
    fields = {"version", "binding", "coordinate_system", "distribution", "source_window_id",
              "source_configuration_sha256", "transport_rule", "kind", "history_sha256"}
    if not isinstance(history, dict) or set(history) != fields:
        raise ValueError("An explicit frozen history anchor is required")
    body = {key: value for key, value in history.items() if key != "history_sha256"}
    if history.get("version") != VERSION or history.get("history_sha256") != _sha(body):
        raise ValueError("Frozen history anchor changed")
    expected = freeze_history_anchor(
        history["distribution"], binding=history["binding"],
        coordinate_system=history["coordinate_system"], source_window_id=history["source_window_id"],
        source_configuration_sha256=history["source_configuration_sha256"],
        transport_rule=history["transport_rule"], kind=history["kind"],
    )
    if expected != history or history["binding"] != _binding(binding):
        raise ValueError("History must bind to this exact current window, situation and member")
    if coordinate_system is not None and history["coordinate_system"] != coordinate_system:
        raise ValueError("History coordinate system does not match the named method")
    return _distribution(history["distribution"], "History", keys)


def _limits(constraints):
    value = copy.deepcopy(DEFAULT_CONSTRAINTS if constraints is None else constraints)
    if (not isinstance(value, dict) or set(value) != set(DEFAULT_CONSTRAINTS)
            or any(not _finite(v) for v in value.values())
            or not 0 < value["lower"] <= 1 <= value["upper"]
            or not 0 <= value["tv_limit"] <= 1
            or value["lambda_h"] <= 0 or value["lambda_r"] <= 0 or value["beta"] < 0
            or not math.isfinite(value["lambda_h"] + value["lambda_r"])):
        raise ValueError("Finite q/base box, TV radius and positive history/coverage coefficients required")
    return value


def _tv(q, center):
    return math.fsum(abs(q[key] - center[key]) for key in q) / 2


def log_novelty(history_distribution, coverage):
    """Frozen positive-support log deficit, with no development-score input."""
    h = _distribution(history_distribution, "History")
    r = _distribution(coverage, "Coverage", h)
    return {key: max(0.0, math.log(r[key]) - math.log(h[key])) for key in h}


def solve_first_order(base, contribution, coverage, *, history, binding, constraints=None):
    """Solve the two-anchor linear surrogate with exact box and history-TV bounds.

    The history must already be feasible in the current q/base box. Unsupported
    support transfer, implicit smoothing and projection are deliberately absent.
    """
    b = _distribution(base, "Base")
    h = _history(history, binding, b)
    r = _distribution(coverage, "Coverage", b)
    limits = _limits(constraints)
    if (not isinstance(contribution, dict) or set(contribution) != set(b)
            or any(not _finite(v) for v in contribution.values())):
        raise ValueError("Every supported contribution coordinate must be finite; unknown is not zero")
    if any(not limits["lower"] <= h[key] / b[key] <= limits["upper"] for key in b):
        raise ValueError("History must be explicitly transferred into the current feasible q/base box")
    novelty = log_novelty(h, r)
    score = {key: contribution[key] + limits["beta"] * novelty[key] for key in b}
    scale = limits["lambda_h"] + limits["lambda_r"]
    log_a = {key: (score[key] + limits["lambda_h"] * math.log(h[key])
                   + limits["lambda_r"] * math.log(r[key])) / scale for key in b}
    low = {key: limits["lower"] * b[key] for key in b}
    high = {key: min(1.0, limits["upper"] * b[key]) for key in b}
    if any(not math.isfinite(log_a[key]) or low[key] <= 0 for key in b):
        raise ValueError("Frozen scales are outside representable positive numerical support")
    # Common shifts do not change the simplex solution and improve log stability.
    shift = max(log_a.values())
    log_a = {key: value - shift for key, value in log_a.items()}
    if any(not math.isfinite(value) for value in log_a.values()):
        raise ValueError("Frozen score differences exceed representable numerical scales")
    log_h = {key: math.log(h[key]) for key in b}
    log_low = {key: math.log(low[key]) for key in b}
    log_high = {key: math.log(high[key]) for key in b}

    def at(tv_multiplier):
        def values(normalizer):
            answer = {}
            for key in b:
                raw = log_a[key] - normalizer
                exponent = (raw if raw < log_h[key] else raw - tv_multiplier
                            if raw - tv_multiplier > log_h[key] else log_h[key])
                answer[key] = (low[key] if exponent <= log_low[key] else high[key]
                               if exponent >= log_high[key] else math.exp(exponent))
            return answer
        left = min(log_a[key] - log_high[key] for key in b) - tv_multiplier
        right = max(log_a[key] - log_low[key] for key in b)
        for _ in range(120):
            midpoint = left / 2 + right / 2
            if midpoint in (left, right):
                break
            if math.fsum(values(midpoint).values()) > 1:
                left = midpoint
            else:
                right = midpoint
        return values(left / 2 + right / 2)

    multiplier = 0.0
    if limits["tv_limit"] == 0 or limits["lower"] == limits["upper"] == 1 or len(b) == 1:
        q = dict(h)
    else:
        q = at(0)
        if _tv(q, h) > limits["tv_limit"]:
            left, right = 0.0, 1.0
            for _ in range(1024):
                if _tv(at(right), h) <= limits["tv_limit"]:
                    break
                right *= 2
                if not math.isfinite(right):
                    raise ValueError("Could not bracket the TV multiplier at declared scales")
            else:
                raise ValueError("Could not bracket the TV multiplier")
            for _ in range(90):
                midpoint = left / 2 + right / 2
                if _tv(at(midpoint), h) > limits["tv_limit"]:
                    left = midpoint
                else:
                    right = midpoint
            multiplier, q = right, at(right)
        # A tiny feasible contraction avoids ratio comparisons landing outside
        # a bound due to rounding; it is not a clip-and-renormalize heuristic.
        q = {key: h[key] + (1 - 1e-12) * (q[key] - h[key]) for key in b}
        residual = 1 - math.fsum(q.values())
        coordinate = max(b, key=lambda key: high[key] - q[key] if residual >= 0 else q[key] - low[key])
        q[coordinate] += residual
    if (not math.isclose(math.fsum(q.values()), 1, rel_tol=0, abs_tol=1e-12)
            or any(q[key] < low[key] - 1e-13 or q[key] > high[key] + 1e-13 for key in b)
            or _tv(q, h) > limits["tv_limit"] + 1e-12):
        raise ValueError("Numerical solution violates declared simplex, q/base box or history-TV bounds")
    kl_h = math.fsum(q[key] * (math.log(q[key]) - math.log(h[key])) for key in b)
    kl_r = math.fsum(q[key] * (math.log(q[key]) - math.log(r[key])) for key in b)
    return {"version": VERSION, "rule": copy.deepcopy(RULE), "binding": _binding(binding),
            "q": q, "base": b, "history_anchor": copy.deepcopy(history), "coverage_anchor": r,
            "contribution": dict(contribution), "N": novelty, "score": score,
            "weights": {key: q[key] / b[key] for key in b},
            "kl_history": kl_h, "kl_coverage": kl_r, "tv": _tv(q, h),
            "tv_from_base_diagnostic": _tv(q, b),
            "tv_multiplier": None if limits["tv_limit"] == 0 and len(b) > 1 else multiplier * scale,
            "objective": math.fsum(q[key] * score[key] for key in b)
                         - limits["lambda_h"] * kl_h - limits["lambda_r"] * kl_r,
            "constraints": limits, "effectiveness_evidence": False,
            "contribution_estimation_executed": False, "training_updates": 0}


def solve_g_raw(base, contribution, *, history, binding, coverage=None,
                coverage_rule="uniform_original_trajectories", constraints=None):
    """General raw member-trajectory coordinates; no classes or graph accepted.

    An externally supplied coverage vector must be predeclared and nonsemantic.
    A caller cannot prove that provenance merely by supplying this rule label.
    """
    b = _distribution(base, "Original trajectory base")
    _history(history, binding, b, "original_member_trajectory")
    if coverage_rule not in {"uniform_original_trajectories", "predeclared_nonsemantic"}:
        raise ValueError("G-raw coverage cannot request a semantic class or graph prior")
    uniform = dict.fromkeys(b, 1 / len(b))
    if coverage is None:
        if coverage_rule != "uniform_original_trajectories":
            raise ValueError("Supply the frozen nonsemantic coverage explicitly")
        coverage = uniform
    elif coverage_rule == "uniform_original_trajectories" and coverage != uniform:
        raise ValueError("Nonuniform raw coverage requires an explicit nonsemantic declaration")
    result = solve_first_order(b, contribution, coverage, history=history, binding=binding,
                               constraints=constraints)
    result.update(method="G-raw", coordinate_system="original_member_trajectory",
                  coverage_rule=coverage_rule, semantic_class_input_used=False,
                  graph_input_used=False, class_shared_weights=False)
    return result


def solve_g_lift(base, contribution, class_by_trajectory, class_coverage, *, history,
                 binding, constraints=None):
    """Auxiliary raw baseline with a declared class prior, independent slot weights."""
    b = _distribution(base, "Original trajectory base")
    _history(history, binding, b, "original_member_trajectory")
    if (not isinstance(class_by_trajectory, dict) or set(class_by_trajectory) != set(b)
            or any(not isinstance(z, str) or not z for z in class_by_trajectory.values())):
        raise ValueError("G-lift needs one frozen semantic class for every original trajectory")
    classes = set(class_by_trajectory.values())
    target = _distribution(class_coverage, "Class coverage", classes)
    class_base = {z: math.fsum(b[sid] for sid in b if class_by_trajectory[sid] == z)
                  for z in sorted(classes)}
    lifted = {sid: target[class_by_trajectory[sid]] * b[sid] / class_base[class_by_trajectory[sid]]
              for sid in b}
    result = solve_first_order(b, contribution, lifted, history=history, binding=binding,
                               constraints=constraints)
    result.update(method="G-lift", coordinate_system="original_member_trajectory",
                  coverage_rule="class_coverage_lifted_by_frozen_base_conditional",
                  class_by_trajectory=copy.deepcopy(class_by_trajectory), class_coverage=target,
                  semantic_class_input_used=True, graph_input_used=False, class_shared_weights=False)
    return result


def solve_i_p(class_base, class_contribution, class_coverage, *, history, binding,
              constraints=None):
    """Member-class first-order rule; every trajectory in a class shares q_z/b_z."""
    b = _distribution(class_base, "Class base")
    _history(history, binding, b, "member_class")
    result = solve_first_order(b, class_contribution, class_coverage, history=history,
                               binding=binding, constraints=constraints)
    result.update(method="I-P", coordinate_system="member_class",
                  coverage_rule="frozen_supported_class_target", semantic_class_input_used=True,
                  graph_input_used=False, class_shared_weights=True)
    return result


def materialize_class_weights(solution, class_by_trajectory):
    """Pure coordinate expansion, not authority to train any supplied trajectory."""
    if (solution.get("method") != "I-P" or not isinstance(class_by_trajectory, dict)
            or not class_by_trajectory
            or set(class_by_trajectory.values()) != set(solution["weights"])):
        raise ValueError("I-P expansion needs exactly the selected supported classes")
    return {sid: solution["weights"][z] for sid, z in class_by_trajectory.items()}
