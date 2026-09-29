"""One supported member's composition weights, on the original actor targets.

No reward/advantage/PPO/critic/denominator changes; no support extrapolation.
The composition object is consumption metadata, never part of model recipe or
checkpoint state. Real-world validity and mapping belong to the work projection.
"""

from __future__ import annotations

import copy
import math

from .online_support import bind_rollout
from .storage import digest, json_bytes
from .support_weights import build_support, materialize_weights

VERSION = "member-composition-training-v0.25"
LOWER, UPPER, TV_LIMIT, EPSILON = 0.5, 2.0, 0.1, 0.1


def baseline_configuration(supports_by_xi):
    return {
        xi: {member: copy.deepcopy(block["b"]) for member, block in support["blocks"].items()}
        for xi, support in supports_by_xi.items()
    }


def _selected(supports, selected):
    if (
        not isinstance(selected, dict)
        or not {"xi_id", "member_id", "class_order"} <= set(selected)
        or set(selected) - {"xi_id", "member_id", "class_order", "task", "perturb_class_id"}
    ):
        raise ValueError(
            "Selected block needs exact situation, member and frozen canonical class order"
        )
    if selected.get("task", "joint_a") != "joint_a":
        raise ValueError("The pre-model v025 gate permits configuration only for qualified task A")
    xi, member = selected["xi_id"], selected["member_id"]
    block = supports.get(xi, {}).get("blocks", {}).get(member)
    if (
        block is None
        or len(block["b"]) != 2
        or len(selected["class_order"]) != 2
        or len(set(selected["class_order"])) != 2
        or set(selected["class_order"]) != set(block["b"])
        or block["composition_degrees_of_freedom"] != 1
    ):
        raise ValueError("Only one actually supported two-class member block can be configured")
    if selected.get("perturb_class_id", selected["class_order"][0]) != selected["class_order"][0]:
        raise ValueError("Probe must use the first frozen canonical supported class")
    return xi, member, block


def _tv(q, b):
    return 0.5 * math.fsum(abs(q[k] - b[k]) for k in b)


def probe_configuration(supports_by_xi, selected_block, *, epsilon=EPSILON):
    if epsilon != EPSILON:
        raise ValueError("The single predeclared probe epsilon is exactly 0.1")
    xi, member, block = _selected(supports_by_xi, selected_block)
    q = baseline_configuration(supports_by_xi)
    z = selected_block["class_order"][0]
    direction = {k: float(k == z) - value for k, value in block["b"].items()}
    q[xi][member] = {k: block["b"][k] + epsilon * direction[k] for k in block["b"]}
    materialize_weights(supports_by_xi[xi], q[xi], lower=LOWER, upper=UPPER)
    return {
        "version": VERSION,
        "selected_block": copy.deepcopy(selected_block),
        "epsilon": epsilon,
        "probed_class": z,
        "direction": direction,
        "q_by_xi": q,
        "target_tv": _tv(q[xi][member], block["b"]),
        "ratio_bounds": [LOWER, UPPER],
    }


def solve_two_class(b, contribution, *, class_order):
    """Exact constrained one-dimensional dual-KL maximum (both lambdas one).

    q0=B, uniform coverage r, beta=0. The strictly concave objective has one
    unconstrained logistic optimum; project that coordinate onto the complete
    feasible interval, including both ratio coordinates and TV <= 0.1.
    """
    if (
        len(b) != 2
        or len(class_order) != 2
        or set(class_order) != set(b)
        or set(contribution) != set(b)
        or len(set(class_order)) != 2
        or any(
            type(v) not in (int, float) or not math.isfinite(v)
            for v in [*b.values(), *contribution.values()]
        )
        or any(v <= 0 for v in b.values())
        or not math.isclose(sum(b.values()), 1.0, abs_tol=1e-12)
    ):
        raise ValueError("Finite two-class supported distributions and contributions required")
    z, other = class_order
    bz, bo = b[z], b[other]
    low = max(LOWER * bz, 1 - UPPER * bo, bz - TV_LIMIT)
    high = min(UPPER * bz, 1 - LOWER * bo, bz + TV_LIMIT)
    if low > high:
        raise ValueError("Empty predeclared composition feasible interval")
    log_odds = (contribution[z] - contribution[other] + math.log(bz / bo)) / 2
    optimum = (
        1 / (1 + math.exp(-log_odds))
        if log_odds >= 0
        else math.exp(log_odds) / (1 + math.exp(log_odds))
    )
    coordinate = min(high, max(low, optimum))
    # A rounded complement must not cross support_weights' exact ratio gate.
    for _ in range(4):
        q = {z: coordinate, other: 1 - coordinate}
        if all(LOWER <= q[k] / b[k] <= UPPER for k in b):
            break
        coordinate = math.nextafter(coordinate, bz)
    else:
        raise ValueError("Floating-point ratio boundary cannot be represented safely")
    if _tv(q, b) > TV_LIMIT + 1e-12:
        raise ValueError("Configured target exceeds the frozen TV radius")

    def kl(a, reference):
        return math.fsum(a[k] * math.log(a[k] / reference[k]) for k in a)

    coverage = dict.fromkeys(class_order, 0.5)
    objective = math.fsum(q[k] * contribution[k] for k in q) - kl(q, b) - kl(q, coverage)
    return {
        "q": q,
        "unconstrained_coordinate": optimum,
        "feasible_coordinate_interval": [low, high],
        "objective": objective,
        "historical_kl": kl(q, b),
        "coverage_kl": kl(q, coverage),
        "tv": _tv(q, b),
        "ratios": {k: q[k] / b[k] for k in q},
        "lambda_h": 1.0,
        "lambda_r": 1.0,
        "beta": 0.0,
        "q0": copy.deepcopy(b),
        "r": coverage,
        "solver": "Exact strictly-concave two-class logistic solution clipped to complete feasible interval",
    }


def configure_from_development(supports_by_xi, selected_block, baseline_y, probe_y):
    probe = probe_configuration(supports_by_xi, selected_block)
    q = baseline_configuration(supports_by_xi)
    xi, member, block = _selected(supports_by_xi, selected_block)
    if (
        not isinstance(baseline_y, list)
        or not isinstance(probe_y, list)
        or len(baseline_y) != 6
        or len(probe_y) != 6
        or any(type(v) not in (bool, type(None)) for v in baseline_y + probe_y)
    ):
        raise ValueError(
            "Exactly six fixed complete-responsibility Boolean/unknown outcomes per development branch required"
        )
    result = {
        "version": VERSION,
        "selected_block": copy.deepcopy(selected_block),
        "baseline_y": list(baseline_y),
        "probe_y": list(probe_y),
        "epsilon": EPSILON,
        "q_by_xi": q,
        "changed": False,
        "contribution_estimate": None,
        "scope": "One noisy finite-difference development observation, not an exact derivative or independent confirmation.",
    }
    if any(v is None for v in baseline_y + probe_y):
        return {**result, "reason": "development_outcome_unknown_keep_Q_equals_B"}
    delta = (sum(probe_y) - sum(baseline_y)) / 6
    if delta == 0:
        return {
            **result,
            "reason": "no_identifiable_development_difference_keep_Q_equals_B",
            "utility_difference": 0.0,
        }
    estimate = delta / EPSILON
    z = probe["probed_class"]
    contribution = {k: estimate / (1 - block["b"][z]) if k == z else 0.0 for k in block["b"]}
    solution = solve_two_class(block["b"], contribution, class_order=selected_block["class_order"])
    q[xi][member] = solution["q"]
    materialize_weights(supports_by_xi[xi], q[xi], lower=LOWER, upper=UPPER)
    return {
        **result,
        "q_by_xi": q,
        "changed": q[xi][member] != block["b"],
        "reason": "measured_single_direction_dual_KL_configuration",
        "utility_difference": delta,
        "contribution_estimate": estimate,
        "contribution_coordinates": contribution,
        "directional_inner_product": math.fsum(
            probe["direction"][k] * contribution[k] for k in contribution
        ),
        "solution": solution,
    }


def _supports_and_bindings(entries, declaration, mappings):
    if (
        [e["slot_id"] for e in entries] != [s["slot_id"] for s in declaration["slots"]]
        or len(mappings) != len(entries)
        or set(mappings) != {e["slot_id"] for e in entries}
        or declaration["min_class_count"] != 2
    ):
        raise ValueError(
            "Composition retains the complete declared slot inventory and support threshold two"
        )
    if (
        declaration.get("gamma_identity", {}).get("purpose", "composition_training")
        != "composition_training"
    ):
        raise ValueError("Continuation diagnostics cannot become a new composition update")
    groups, bindings = {}, {}
    for entry, slot in zip(entries, declaration["slots"]):
        if (
            entry["active_members"] != slot["active_members"]
            or entry["rollout"] is None
            or entry["reward"] != entry["rollout"]["reward_eligibility"]
        ):
            raise ValueError(
                "Original active members, raw rollout and attached reward must remain exact"
            )
        if "mapping" in entry and entry["mapping"] != mappings[entry["slot_id"]]:
            raise ValueError("Composition mapping differs from original projected method evidence")
        bound = bind_rollout(
            declaration, entry["slot_id"], entry["rollout"], mapping=mappings[entry["slot_id"]]
        )
        xi = slot["xi_id"]
        group = groups.setdefault(
            xi, {"slots": [], "window": slot["window"], "members": slot["active_members"]}
        )
        if group["window"] != slot["window"] or group["members"] != slot["active_members"]:
            raise ValueError("Do not pool different situations, windows or member layouts")
        group["slots"].append(bound)
        bindings[entry["slot_id"]] = bound
    supports = {
        xi: build_support(
            g["slots"], window=g["window"], member_ids=g["members"], min_class_count=2
        )
        for xi, g in groups.items()
    }
    return supports, bindings


def materialize_composition(entries, declaration, records, *, q_by_xi=None, selected_block=None):
    """Bind support_weights outputs to exact raw entries; do not duplicate them."""
    byslot = {r["slot_id"]: r for r in records}
    if len(byslot) != len(records) or set(byslot) != {e["slot_id"] for e in entries}:
        raise ValueError("Every actual collection slot needs exactly one original support record")
    mappings = {}
    for entry in entries:
        record = byslot[entry["slot_id"]]
        if record.get("status") != "closed" or record.get("rollout") != entry["rollout"]:
            raise ValueError(
                "Support records must reference the same closed original rollout, not a copy from another window"
            )
        mappings[entry["slot_id"]] = copy.deepcopy(record["mapping"])
    supports, _ = _supports_and_bindings(entries, declaration, mappings)
    baseline = baseline_configuration(supports)
    q = copy.deepcopy(baseline if q_by_xi is None else q_by_xi)
    if set(q) != set(baseline):
        raise ValueError("No situation budget may be dropped, added or transferred")
    selected = _selected(supports, selected_block)[:2] if selected_block is not None else None
    if selected is not None:
        selected_tasks = {
            entry["rollout"].get("online_scope", {}).get("task", entry["reward"].get("scope"))
            for entry in entries
            if entry["rollout"]["window"]["xi_id"] == selected[0]
        }
        if selected_tasks != {"joint_a"} and not (
            selected_tasks == {None}
            and declaration.get("gamma_identity", {}).get("explicit_CPU_fixture") is True
        ):
            raise ValueError(
                "Only actual task A source slots may receive the selected configuration"
            )
    changed_blocks, materialized = [], {}
    for xi, support in supports.items():
        materialized[xi] = materialize_weights(support, q[xi], lower=LOWER, upper=UPPER)
        for member, block in support["blocks"].items():
            if q[xi][member] != block["b"]:
                if (xi, member) != selected:
                    raise ValueError("Only the single selected supported member block may change")
                if _tv(q[xi][member], block["b"]) > TV_LIMIT + 1e-12:
                    raise ValueError("Composition exceeds the predeclared TV radius")
                changed_blocks.append({"xi_id": xi, "member_id": member})
    return {
        "version": VERSION,
        "window_id": declaration["window_id"],
        "actor_identity": copy.deepcopy(declaration["actor_identity"]),
        "entries_sha256": digest(json_bytes(entries)),
        "declaration_sha256": digest(json_bytes(declaration)),
        "declaration": copy.deepcopy(declaration),
        "mappings": mappings,
        "supports_by_xi": supports,
        "q_by_xi": q,
        "selected_block": copy.deepcopy(selected_block),
        "materialized_by_xi": materialized,
        "changed_blocks": changed_blocks,
        "Q_equals_B": not changed_blocks,
        "ratio_bounds": [LOWER, UPPER],
        "tv_limit": TV_LIMIT,
        "scope": "Only supported slot/member actor terms receive q/b; residual and all other members stay one. Original masks/denominators/critic/PPO ratios unchanged.",
    }


def validate_composition(entries, prepared, composition):
    """Rebuild support/materialization and return one weight per admitted row."""
    if not isinstance(composition, dict) or composition.get("version") != VERSION:
        raise ValueError("Exact bound v025 composition required")
    declaration = composition["declaration"]
    records = [
        {
            "slot_id": e["slot_id"],
            "status": "closed",
            "rollout": e["rollout"],
            "mapping": composition["mappings"].get(e["slot_id"]),
        }
        for e in entries
    ]
    rebuilt = materialize_composition(
        entries,
        declaration,
        records,
        q_by_xi=composition["q_by_xi"],
        selected_block=composition["selected_block"],
    )
    if (
        rebuilt != composition
        or prepared["window_id"] != composition["window_id"]
        or prepared["actor_identity"] != composition["actor_identity"]
    ):
        raise ValueError(
            "Composition does not match original window, actor, entries or canonical materialization"
        )
    _, bound = _supports_and_bindings(entries, declaration, composition["mappings"])
    byslot = {e["slot_id"]: e for e in entries}
    weights, row_records, seen = [], [], set()
    for row in prepared["decisions"]:
        sid, member, call = row["slot_id"], row["member_id"], row["call_id"]
        if (sid, member, call) in seen:
            raise ValueError("A member own-token decision cannot be counted twice")
        seen.add((sid, member, call))
        item = bound[sid]
        xi = item["window"]["xi_id"]
        view = item["member_views"].get(member)
        if view is None or member not in byslot[sid]["active_members"]:
            raise ValueError("Composition cannot transfer targets across members")
        decisions = [d for d in view["decisions"] if d["call_id"] == call and d["actor_required"]]
        if len(decisions) != 1:
            raise ValueError("Unique actual own generated decision required")
        d = decisions[0]
        trace = d["tokens"]
        required = sum(x["actor_required"] for x in view["decisions"])
        if (
            row["tokens"] != trace
            or row["actual_response_sha256"] != d["response_sha256"]
            or d["loss_mask"] != [0] * len(trace["input_ids"]) + [1] * len(trace["output_ids"])
            or row["actor_denominator"]
            != len(entries) * len(byslot[sid]["active_members"]) * view["own_action_tokens"]
            or row["critic_denominator"]
            != len(entries) * len(byslot[sid]["active_members"]) * required
        ):
            raise ValueError("Own tokens, masks or original normalization changed")
        mat = composition["materialized_by_xi"][xi]["members"][member]
        if not mat["actor_mask"][sid]:
            raise ValueError(
                "Composition may not admit targets excluded by original actor evidence"
            )
        weight = mat["weights"][sid]
        weights.append(weight)
        row_records.append(
            {
                "slot_id": sid,
                "member_id": member,
                "call_id": call,
                "weight": weight,
                "own_output_tokens": len(trace["output_ids"]),
                "tokens_sha256": digest(json_bytes(trace)),
                "actor_denominator": row["actor_denominator"],
                "critic_denominator": row["critic_denominator"],
            }
        )
    return weights, {
        "version": VERSION,
        "composition_sha256": digest(json_bytes(composition)),
        "Q_equals_B": composition["Q_equals_B"],
        "changed_blocks": composition["changed_blocks"],
        "rows": row_records,
        "original_normalization_preserved": True,
    }
