"""Finite first-order B/G/I allocation over one current, exact support window.

This module performs no model calls or updates. Development receipts are evidence
supplied by a runner, not proof that a trial update actually took place. Synthetic
receipts exercise the selector only and cannot establish allocation effectiveness.
"""

from __future__ import annotations

import copy
import math
import re
from collections import Counter

from .online_support import bind_rollout, diagnose_window
from .storage import digest, json_bytes
from .support_weights import build_support, materialize_weights
from .team_rollout import validate_window

VERSION = "experience-allocation-v0.27"
DEFAULT_CONSTRAINTS = {
    "lower": 0.5,
    "upper": 2.0,
    "tv_limit": 0.2,
    "probe_tv": 0.05,
    "lambda_b": 1.0,
    "lambda_coverage": 1.0,
    "beta": 0.25,
}
PURPOSE = "contribution_development"


def _sha(value):
    return digest(json_bytes(value))


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _tv(q, b):
    return math.fsum(abs(q[k] - b[k]) for k in b) / 2


def _baseline(supports):
    return {
        xi: {member: copy.deepcopy(block["b"]) for member, block in support["blocks"].items()}
        for xi, support in supports.items()
    }


def _validate_supports(supports):
    if not isinstance(supports, dict) or not supports:
        raise ValueError("At least one exact situation support is required")
    windows, slots = set(), set()
    for xi, support in supports.items():
        window = validate_window(support["window"])
        if window["xi_id"] != xi:
            raise ValueError("Support key must identify its exact situation")
        windows.add((window["window_id"], window["gamma_fingerprint"]))
        inventory = support["slot_ids"]
        if not inventory or len(set(inventory)) != len(inventory) or slots.intersection(inventory):
            raise ValueError("Original slots must remain unique across exact situations")
        slots.update(inventory)
        if not support["blocks"]:
            raise ValueError("Stable active members are required")
        for block in support["blocks"].values():
            counts = dict(Counter(block["eligible_slots"].values()))
            n = sum(counts.values())
            if (
                block["M"] != len(inventory)
                or block["n_by_class"] != counts
                or block["n_positive"] != n
                or block["v"] != n / len(inventory)
                or block["b"] != {k: count / n for k, count in counts.items()}
                or block["composition_degrees_of_freedom"] != max(0, len(counts) - 1)
                or set(block["base_actor_mask"]) != set(inventory)
                or any(type(v) is not bool for v in block["base_actor_mask"].values())
                or not set(block["eligible_slots"]) <= set(inventory)
                or any(not block["base_actor_mask"][sid] for sid in block["eligible_slots"])
                or any(count < support["min_class_count"] for count in counts.values())
            ):
                raise ValueError("Support counts, members, masks and original slots must agree")
        materialize_weights(support, _baseline({xi: support})[xi])
    if len(windows) != 1:
        raise ValueError("Do not pool policy collection windows or execution protocols")


def _constraints(value):
    value = copy.deepcopy(DEFAULT_CONSTRAINTS if value is None else value)
    if (
        set(value) != set(DEFAULT_CONSTRAINTS)
        or any(not _finite(v) for v in value.values())
        or not 0 < value["lower"] < 1 < value["upper"]
        or not 0 < value["probe_tv"] <= value["tv_limit"] <= 1
        or value["lambda_b"] <= 0
        or value["lambda_coverage"] <= 0
        or value["beta"] < 0
    ):
        raise ValueError("Freeze finite ratio/TV limits and positive B/coverage anchors")
    return value


def _development(value):
    fields = {
        "purpose", "dataset_id", "split_manifest_sha256", "initial_state_sha256",
        "training_rng_sha256", "units", "independent_unit_ids", "provenance",
    }
    if not isinstance(value, dict) or set(value) != fields or value["purpose"] != PURPOSE:
        raise ValueError("Only a frozen contribution-development manifest may select weights")
    if value["provenance"] not in {"synthetic_cpu_control", "current_model_development"}:
        raise ValueError("Development provenance must distinguish synthetic and real evidence")
    for field in ("split_manifest_sha256", "initial_state_sha256", "training_rng_sha256"):
        if not isinstance(value[field], str) or not re.fullmatch(r"[0-9a-f]{64}", value[field]):
            raise ValueError("Common split, complete initial state and RNG require SHA256 identities")
    units = value["units"]
    if not value["dataset_id"] or not isinstance(units, list) or not units:
        raise ValueError("A nonempty common development inventory is required")
    ids = []
    for row in units:
        if (
            set(row) != {"unit_id", "seed", "weight"}
            or not isinstance(row["unit_id"], str)
            or not row["unit_id"]
            or type(row["seed"]) is not int
            or not _finite(row["weight"])
            or row["weight"] <= 0
        ):
            raise ValueError("Each development unit needs a stable id, paired seed and positive weight")
        ids.append(row["unit_id"])
    independent = value["independent_unit_ids"]
    if (
        len(ids) != len(set(ids))
        or not isinstance(independent, list)
        or any(not isinstance(k, str) or not k for k in independent)
        or len(independent) != len(set(independent))
        or set(ids).intersection(independent)
    ):
        raise ValueError("Independent confirmation must remain disjoint from weight selection")
    return copy.deepcopy(value)


def _method_supports(supports, method, eligible):
    """G's atoms are original member trajectories, never copied joint samples."""
    transformed = copy.deepcopy(supports)
    if method == "G":
        for xi, member in eligible:
            block = transformed[xi]["blocks"][member]
            slots = block["eligible_slots"]
            block["b"] = {sid: 1 / len(slots) for sid in slots}
            block["n_by_class"] = dict.fromkeys(slots, 1)
            block["eligible_slots"] = {sid: sid for sid in slots}
    return transformed


def _coverage(original, method):
    """Identical per-slot coverage target for G and I; no value inference."""
    counts, b = original["n_by_class"], original["b"]
    if method == "G":
        r = {sid: 1 / (len(b) * counts[z]) for sid, z in original["eligible_slots"].items()}
        novelty = {
            sid: max(0.0, 1 - b[z] * len(b))
            for sid, z in original["eligible_slots"].items()
        }
    else:
        r = dict.fromkeys(b, 1 / len(b))
        novelty = {z: max(0.0, 1 - b[z] * len(b)) for z in b}
    return r, novelty


def _helmert(keys):
    """Complete deterministic orthonormal simplex basis; no first-class shortcut."""
    for j in range(1, len(keys)):
        scale = math.sqrt(j * (j + 1))
        yield {key: (1 / scale if i < j else -j / scale if i == j else 0.0)
               for i, key in enumerate(keys)}


def _materialize(supports, q, constraints):
    if set(q) != set(supports):
        raise ValueError("All exact situation shares must be retained")
    result = {}
    for xi, support in supports.items():
        result[xi] = materialize_weights(
            support, q[xi], lower=constraints["lower"], upper=constraints["upper"]
        )
        for member, block in support["blocks"].items():
            if _tv(q[xi][member], block["b"]) > constraints["tv_limit"] + 1e-12:
                raise ValueError("Allocation exceeds its frozen per-member TV limit")
    return result


def _weights_hash(materialized):
    return _sha({xi: {m: {"weights": row["weights"], "actor_mask": row["actor_mask"]}
                      for m, row in value["members"].items()}
                 for xi, value in materialized.items()})


def freeze_allocation_plan(
    supports_by_xi, *, eligible_blocks, development, budget, constraints=None
):
    """Declare all probes before feedback; reject insufficient full-coordinate budgets.

    `eligible_blocks` is a list of [xi_id, stable_member_id]. Both G and I may
    change only these same currently supported branches. G measures every raw
    trajectory contrast; I measures every supported class contrast.
    """
    _validate_supports(supports_by_xi)
    limits, dev = _constraints(constraints), _development(development)
    eligible = [tuple(pair) for pair in eligible_blocks]
    if len(eligible) != len(set(eligible)):
        raise ValueError("A stable member/situation block cannot be configured twice")
    for pair in eligible:
        if len(pair) != 2:
            raise ValueError("Eligible blocks identify exact situation and stable member")
        xi, member = pair
        block = supports_by_xi.get(xi, {}).get("blocks", {}).get(member)
        if block is None or len(block["b"]) < 2:
            raise ValueError("Both methods require the same actual multi-class supported branches")
    if (
        set(budget) != {"max_trial_updates_per_method", "max_development_evaluations_per_method",
                       "formal_updates_per_method"}
        or any(type(v) is not int or v < 1 for v in budget.values())
        or budget["formal_updates_per_method"] != 1
    ):
        raise ValueError("Freeze common finite trial/development budgets and one formal update")
    plan = {
        "version": VERSION, "supports_by_xi": copy.deepcopy(supports_by_xi),
        "eligible_blocks": [list(p) for p in sorted(eligible)], "constraints": limits,
        "development": dev, "development_sha256": _sha(dev), "budget": copy.deepcopy(budget),
        "status": "ready" if eligible else "no_configurable_support",
        "methods": {}, "candidates": {},
        "scope": "Actor composition only; original task/member shares and failure residuals fixed",
    }
    baseline = _baseline(supports_by_xi)
    base_mat = _materialize(supports_by_xi, baseline, limits)
    plan["candidates"]["B"] = {
        "method": "B", "q_by_xi": baseline, "weights_sha256": _weights_hash(base_mat)
    }
    for method in ("G", "I"):
        supports = _method_supports(supports_by_xi, method, eligible)
        base = _baseline(supports)
        directions = []
        for xi, member in sorted(eligible):
            b = supports[xi]["blocks"][member]["b"]
            for index, direction in enumerate(_helmert(sorted(b))):
                radius = limits["probe_tv"] / (math.fsum(abs(v) for v in direction.values()) / 2)
                for key, value in direction.items():
                    if value:
                        radius = min(radius, b[key] * (1 - limits["lower"]) / abs(value),
                                     b[key] * (limits["upper"] - 1) / abs(value))
                radius *= 1 - 1e-12  # Strictly interior representable ratio limits.
                ids = []
                for sign in (-1, 1):
                    q = copy.deepcopy(base)
                    q[xi][member] = {k: b[k] + sign * radius * direction[k] for k in b}
                    cid = method + "-" + _sha([xi, member, index, sign])[:20]
                    mat = _materialize(supports, q, limits)
                    plan["candidates"][cid] = {
                        "method": method, "q_by_xi": q, "weights_sha256": _weights_hash(mat)
                    }
                    ids.append(cid)
                directions.append({"xi_id": xi, "member_id": member, "direction": direction,
                                   "radius": radius, "minus_id": ids[0], "plus_id": ids[1]})
        count = 1 + 2 * len(directions) if directions else 0
        evaluations = count * len(dev["units"])
        if (count > budget["max_trial_updates_per_method"]
                or evaluations > budget["max_development_evaluations_per_method"]):
            raise ValueError(
                f"{method} needs {count} trial updates and {evaluations} development evaluations; "
                "do not truncate the raw-trajectory baseline to fit an inadequate budget"
            )
        plan["methods"][method] = {
            "directions": directions, "required_trial_updates": count,
            "required_development_evaluations": evaluations,
            "baseline_q_by_xi": base,
        }
    plan["plan_sha256"] = _sha(plan)
    return plan


def _check_plan(plan):
    body = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if plan.get("version") != VERSION or plan.get("plan_sha256") != _sha(body):
        raise ValueError("The frozen allocation plan changed")


def candidate_materialization(plan, candidate_id):
    """Return the exact q/b weights a paired trial runner must consume."""
    _check_plan(plan)
    candidate = plan["candidates"][candidate_id]
    supports = _method_supports(
        plan["supports_by_xi"], candidate["method"], plan["eligible_blocks"]
    )
    materialized = _materialize(supports, candidate["q_by_xi"], plan["constraints"])
    if _weights_hash(materialized) != candidate["weights_sha256"]:
        raise ValueError("Candidate weight identity differs from its frozen plan")
    return materialized


def development_receipt(plan, candidate_id, utilities, *, provenance):
    """Format (do not execute/certify) a trial's paired developer outcomes."""
    _check_plan(plan)
    if len(utilities) != len(plan["development"]["units"]):
        raise ValueError("Every declared development unit, including unknowns, must be reported")
    dev = plan["development"]
    return {
        "candidate_id": candidate_id,
        "weights_sha256": plan["candidates"][candidate_id]["weights_sha256"],
        "development_sha256": plan["development_sha256"], "purpose": PURPOSE,
        "initial_state_sha256": dev["initial_state_sha256"],
        "training_rng_sha256": dev["training_rng_sha256"], "provenance": provenance,
        "outcomes": [{"unit_id": row["unit_id"], "seed": row["seed"], "utility": value}
                     for row, value in zip(dev["units"], utilities)],
    }


def _receipts(plan, receipts):
    result = {}
    dev = plan["development"]
    for receipt in receipts:
        cid = receipt.get("candidate_id")
        if cid not in plan["candidates"] or cid in result:
            raise ValueError("Only one receipt for each frozen development candidate is allowed")
        outcomes = receipt.get("outcomes", [])
        expected = development_receipt(
            plan, cid, [row.get("utility") for row in outcomes], provenance=dev["provenance"]
        )
        if receipt != expected or any(set(row) != {"unit_id", "seed", "utility"} for row in outcomes):
            raise ValueError("Receipt must preserve common development units, state, RNG and provenance")
        values = [row["utility"] for row in outcomes]
        if any(value is not None and not _finite(value) for value in values):
            raise ValueError("Development utility must be finite or explicitly unknown")
        result[cid] = values
    return result


def solve_first_order(b, contribution, coverage, novelty, *, constraints=None):
    """Maximize linear C+beta*N minus two KL anchors under ratio and TV bounds.

    A scalar normalization multiplier and a nonnegative TV multiplier solve the
    strictly concave problem. This is a finite-difference surrogate, not a claim
    of an exact derivative of the model's development utility.
    """
    limits = _constraints(constraints)
    if (
        not b or any(set(values) != set(b) for values in (contribution, coverage, novelty))
        or any(not _finite(v) for d in (b, contribution, coverage, novelty) for v in d.values())
        or any(b[k] <= 0 or coverage[k] <= 0 or novelty[k] < 0 for k in b)
        or not math.isclose(math.fsum(b.values()), 1.0, abs_tol=1e-12)
        or not math.isclose(math.fsum(coverage.values()), 1.0, abs_tol=1e-12)
    ):
        raise ValueError("Supported finite normalized distributions and contribution coordinates required")
    scale = limits["lambda_b"] + limits["lambda_coverage"]
    log_a = {k: (contribution[k] + limits["beta"] * novelty[k]
                 + limits["lambda_b"] * math.log(b[k])
                 + limits["lambda_coverage"] * math.log(coverage[k])) / scale for k in b}
    low = {k: limits["lower"] * b[k] for k in b}
    high = {k: min(1.0, limits["upper"] * b[k]) for k in b}

    def at(tv_multiplier):
        def values(normalizer):
            answer = {}
            for k in b:
                raw = log_a[k] - normalizer
                log_b = math.log(b[k])
                value = (math.exp(max(-745.0, min(709.0, raw))) if raw < log_b else
                         math.exp(max(-745.0, min(709.0, raw - tv_multiplier)))
                         if raw - tv_multiplier > log_b else b[k])
                answer[k] = min(high[k], max(low[k], value))
            return answer
        left = min(log_a.values()) - tv_multiplier - 750
        right = max(log_a.values()) + 750
        for _ in range(100):
            mid = (left + right) / 2
            if math.fsum(values(mid).values()) > 1:
                left = mid
            else:
                right = mid
        return values((left + right) / 2)

    q, multiplier = at(0), 0.0
    if _tv(q, b) > limits["tv_limit"]:
        left, right = 0.0, 1.0
        while _tv(at(right), b) > limits["tv_limit"]:
            right *= 2
        for _ in range(80):
            mid = (left + right) / 2
            if _tv(at(mid), b) > limits["tv_limit"]:
                left = mid
            else:
                right = mid
        multiplier, q = right, at(right)
    # Move a negligible distance toward B for exact downstream ratio comparisons.
    q = {k: b[k] + (1 - 1e-12) * (q[k] - b[k]) for k in b}
    residual = 1 - math.fsum(q.values())
    key = max(b, key=lambda k: min(q[k] - low[k], high[k] - q[k]))
    q[key] += residual
    if any(not limits["lower"] <= q[k] / b[k] <= limits["upper"] for k in b):
        raise ValueError("Numerical solution violates the frozen ratio constraints")
    kl_b = math.fsum(q[k] * math.log(q[k] / b[k]) for k in b)
    kl_r = math.fsum(q[k] * math.log(q[k] / coverage[k]) for k in b)
    return {
        "q": q, "contribution": copy.deepcopy(contribution), "N": copy.deepcopy(novelty),
        "coverage_anchor": copy.deepcopy(coverage), "baseline_anchor": copy.deepcopy(b),
        "kl_b": kl_b, "kl_coverage": kl_r, "tv": _tv(q, b),
        "tv_multiplier": multiplier * scale,
        "objective": math.fsum(q[k] * (contribution[k] + limits["beta"] * novelty[k]) for k in b)
                     - limits["lambda_b"] * kl_b - limits["lambda_coverage"] * kl_r,
        "constraints": limits,
    }


def select_allocation(plan, receipts):
    """Select B/G/I from paired development only; unknown method feedback -> B."""
    _check_plan(plan)
    observed = _receipts(plan, receipts)
    units = plan["development"]["units"]
    total = math.fsum(row["weight"] for row in units)
    selections = {"B": {"method": "B", "q_by_xi": copy.deepcopy(plan["candidates"]["B"]["q_by_xi"]),
                         "reason": "baseline", "solutions": [], "Q_equals_B": True}}
    for method in ("G", "I"):
        spec = plan["methods"][method]
        q = copy.deepcopy(spec["baseline_q_by_xi"])
        required = {"B"} | {d[k] for d in spec["directions"] for k in ("minus_id", "plus_id")}
        unknown = sorted(cid for cid in required if cid not in observed
                         or any(value is None for value in observed[cid]))
        solutions = []
        if not spec["directions"]:
            reason = "no_configurable_support_keep_B"
        elif unknown:
            reason = "development_unknown_keep_B"
        else:
            reason = "paired_finite_difference_C_and_observed_support_N"
            estimates = {(xi, member): dict.fromkeys(q[xi][member], 0.0)
                         for xi, member in plan["eligible_blocks"]}
            for direction in spec["directions"]:
                # Difference of paired differences relative to the shared B trial.
                delta = math.fsum(row["weight"] * (plus - minus)
                                  for row, plus, minus in zip(
                                      units, observed[direction["plus_id"]],
                                      observed[direction["minus_id"]])) / total
                slope = delta / (2 * direction["radius"])
                c = estimates[(direction["xi_id"], direction["member_id"])]
                for k, value in direction["direction"].items():
                    c[k] += slope * value
            for xi, member in plan["eligible_blocks"]:
                coverage, novelty = _coverage(plan["supports_by_xi"][xi]["blocks"][member], method)
                solution = solve_first_order(q[xi][member], estimates[(xi, member)], coverage,
                                             novelty, constraints=plan["constraints"])
                q[xi][member] = solution["q"]
                solutions.append({"xi_id": xi, "member_id": member, **solution})
        supports = _method_supports(plan["supports_by_xi"], method, plan["eligible_blocks"])
        materialized = _materialize(supports, q, plan["constraints"])
        selections[method] = {
            "method": method, "q_by_xi": q, "reason": reason, "unknown_candidates": unknown,
            "solutions": solutions,
            "Q_equals_B": _weights_hash(materialized) == plan["candidates"]["B"]["weights_sha256"],
        }
    return {
        "version": VERSION, "plan_sha256": plan["plan_sha256"], "receipts": copy.deepcopy(receipts),
        "selections": selections, "provenance": plan["development"]["provenance"],
        "effectiveness_evidence": False,
        "scope": "Selected surrogate configuration; independent post-update confirmation not performed",
    }


def materialize_allocation(plan, selection, method):
    """Canonical q/b materialization, including raw-trajectory G via singleton atoms."""
    if method not in {"B", "G", "I"}:
        raise ValueError("Allocation method must be B, G or I")
    if select_allocation(plan, selection["receipts"]) != selection:
        raise ValueError("Selection differs from the frozen rule and development evidence")
    selected = selection["selections"][method]
    supports = _method_supports(plan["supports_by_xi"], method, plan["eligible_blocks"])
    return _materialize(supports, selected["q_by_xi"], plan["constraints"])


def inspect_allocation_window(declaration, records):
    """Retain missing/unknown slots and return a reportable gate before selection."""
    diagnostic = diagnose_window(declaration, records)
    ready = all(group["support"] is not None for group in diagnostic["groups"])
    byslot = {row["slot_id"]: row for row in records}
    return {
        "version": VERSION,
        "status": "ready" if ready else "incomplete_keep_original_inventory",
        "supports_by_xi": {group["window"]["xi_id"]: group["support"]
                           for group in diagnostic["groups"]} if ready else None,
        "raw_slot_inventory": [
            {"slot_id": row["slot_id"], "xi_id": row["xi_id"],
             "status": byslot.get(row["slot_id"], {}).get("status", "not_started")}
            for row in declaration["slots"]
        ],
        "diagnostic": diagnostic,
        "scope": "Unknown/unstarted slots are retained, never relabeled as false or removed",
    }


def supports_from_entries(entries, declaration, records):
    """Rebuild support from original closed member actions; no reward-based relabeling."""
    if [e["slot_id"] for e in entries] != [s["slot_id"] for s in declaration["slots"]]:
        raise ValueError("Retain the complete declared original-slot inventory and order")
    byslot = {row["slot_id"]: row for row in records}
    if len(byslot) != len(records) or set(byslot) != {e["slot_id"] for e in entries}:
        raise ValueError("Exactly one support record is required per original slot")
    groups, bindings = {}, {}
    for entry, slot in zip(entries, declaration["slots"]):
        sid = entry["slot_id"]
        record = byslot[sid]
        if (record.get("status") != "closed" or record.get("rollout") != entry["rollout"]
                or entry["active_members"] != slot["active_members"]
                or entry["reward"] != entry["rollout"]["reward_eligibility"]
                or ("mapping" in entry and entry["mapping"] != record["mapping"])):
            raise ValueError("Original closed rollout, member, mapping and reward bindings must agree")
        bound = bind_rollout(declaration, sid, entry["rollout"], mapping=record["mapping"])
        xi = slot["xi_id"]
        group = groups.setdefault(xi, {"slots": [], "window": slot["window"],
                                      "members": slot["active_members"]})
        if group["window"] != slot["window"] or group["members"] != slot["active_members"]:
            raise ValueError("Do not pool different exact situations or member layouts")
        group["slots"].append(bound)
        bindings[sid] = bound
    supports = {xi: build_support(g["slots"], window=g["window"], member_ids=g["members"],
                                 min_class_count=declaration["min_class_count"])
                for xi, g in groups.items()}
    return supports, bindings


def bind_allocation(entries, declaration, records, plan, selection, *, method):
    """Create updater consumption metadata, bound to original current-policy entries."""
    if not plan["eligible_blocks"]:
        raise ValueError("No configurable support: this finite allocation trial ends without an update")
    supports, _ = supports_from_entries(entries, declaration, records)
    if supports != plan["supports_by_xi"]:
        raise ValueError("Plan support differs from original current-window actions")
    materialized = materialize_allocation(plan, selection, method)
    return {
        "version": VERSION, "kind": "formal", "window_id": declaration["window_id"],
        "actor_identity": copy.deepcopy(declaration["actor_identity"]),
        "entries_sha256": _sha(entries), "declaration": copy.deepcopy(declaration),
        "records": copy.deepcopy(records), "plan": copy.deepcopy(plan),
        "selection": copy.deepcopy(selection), "method": method,
        "materialized_by_xi": materialized,
        "Q_equals_B": selection["selections"][method]["Q_equals_B"],
    }


def bind_candidate(entries, declaration, records, plan, candidate_id):
    """Bind a planned trial before any feedback exists; use the same actor updater.

    The runner must restore and verify the full declared state/RNG before each
    trial. This function verifies action/support binding, not external execution.
    """
    if not plan["eligible_blocks"]:
        raise ValueError("No configurable support: this finite allocation trial ends without an update")
    supports, _ = supports_from_entries(entries, declaration, records)
    if supports != plan["supports_by_xi"]:
        raise ValueError("Plan support differs from original current-window actions")
    materialized = candidate_materialization(plan, candidate_id)
    return {
        "version": VERSION, "kind": "trial", "window_id": declaration["window_id"],
        "actor_identity": copy.deepcopy(declaration["actor_identity"]),
        "entries_sha256": _sha(entries), "declaration": copy.deepcopy(declaration),
        "records": copy.deepcopy(records), "plan": copy.deepcopy(plan),
        "candidate_id": candidate_id, "method": plan["candidates"][candidate_id]["method"],
        "materialized_by_xi": materialized,
        "Q_equals_B": _weights_hash(materialized) == plan["candidates"]["B"]["weights_sha256"],
    }


def validate_allocation(entries, prepared, allocation):
    """Return actor weights after checking raw own-token attribution and denominators."""
    if allocation.get("version") != VERSION:
        raise ValueError("A bound v027 allocation is required")
    if allocation.get("kind") == "trial":
        rebuilt = bind_candidate(entries, allocation["declaration"], allocation["records"],
                                 allocation["plan"], allocation["candidate_id"])
    elif allocation.get("kind") == "formal":
        rebuilt = bind_allocation(entries, allocation["declaration"], allocation["records"],
                                  allocation["plan"], allocation["selection"],
                                  method=allocation["method"])
    else:
        raise ValueError("Allocation must distinguish a planned trial from a formal update")
    if (rebuilt != allocation or prepared["window_id"] != allocation["window_id"]
            or prepared["actor_identity"] != allocation["actor_identity"]):
        raise ValueError("Allocation differs from original entries, window or actor")
    _, bindings = supports_from_entries(entries, allocation["declaration"], allocation["records"])
    byslot = {e["slot_id"]: e for e in entries}
    seen, weights, rows = set(), [], []
    for row in prepared["decisions"]:
        sid, member, call = row["slot_id"], row["member_id"], row["call_id"]
        if (sid, member, call) in seen:
            raise ValueError("A member's original action cannot be counted twice")
        seen.add((sid, member, call))
        bound = bindings[sid]
        view = bound["member_views"].get(member)
        if view is None or member not in byslot[sid]["active_members"]:
            raise ValueError("Allocation cannot transfer actions across stable members")
        own = [d for d in view["decisions"] if d["call_id"] == call and d["actor_required"]]
        if len(own) != 1:
            raise ValueError("Exactly one recoverable own-token decision is required")
        decision, tokens = own[0], own[0]["tokens"]
        members = len(byslot[sid]["active_members"])
        if (row["tokens"] != tokens or row["actual_response_sha256"] != decision["response_sha256"]
                or decision["loss_mask"] != [0] * len(tokens["input_ids"]) + [1] * len(tokens["output_ids"])
                or row["actor_denominator"] != len(entries) * members * view["own_action_tokens"]
                or row["critic_denominator"] != len(entries) * members
                * sum(d["actor_required"] for d in view["decisions"])):
            raise ValueError("Own tokens, masks and baseline normalization must remain unchanged")
        mat = allocation["materialized_by_xi"][bound["window"]["xi_id"]]["members"][member]
        if not mat["actor_mask"][sid]:
            raise ValueError("Allocation cannot admit an actor target excluded by base evidence")
        weight = mat["weights"][sid]
        weights.append(weight)
        rows.append({"slot_id": sid, "member_id": member, "call_id": call, "weight": weight,
                     "tokens_sha256": _sha(tokens), "actor_denominator": row["actor_denominator"],
                     "critic_denominator": row["critic_denominator"]})
    changed = [{"xi_id": xi, "member_id": member}
               for xi, value in allocation["materialized_by_xi"].items()
               for member, row in value["members"].items()
               if any(weight != 1 for weight in row["weights"].values())]
    return weights, {"version": VERSION, "allocation_sha256": _sha(allocation),
                     "Q_equals_B": allocation["Q_equals_B"], "changed_blocks": changed,
                     "rows": rows, "original_normalization_preserved": True}
