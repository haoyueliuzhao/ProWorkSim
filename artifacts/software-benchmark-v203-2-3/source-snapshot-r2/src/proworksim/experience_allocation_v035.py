"""Bind the v030 first-order rule to original current-window actor material.

This module freezes complete probes and validates their consumption. It does not
run updates or certify a caller's execution receipts. The experiment runner must
bind real common restoration, successful updates and subsequent developer work.
"""
from __future__ import annotations

import copy
import math

from . import experience_allocation_v030 as rule
from .experience_allocation_v027 import (
    _baseline, _helmert, _materialize, _validate_supports, _weights_hash,
    inspect_allocation_window, supports_from_entries,
)
from .storage import digest, json_bytes

VERSION = "experience-allocation-v0.35-log-n-bound"
MEMBERS = ("member_a", "member_b")
METHODS = ("B", "G-raw", "I-P")
SUPPORT_M = 16
PROBE_TV = 0.05


def _sha(value):
    return digest(json_bytes(value))


def allocation_gate(entries, declaration, records):
    """Inspect all sixteen slots; never turn a finite support gate into sampling."""
    slots = declaration["slots"]
    if (len(slots) != SUPPORT_M or declaration["min_class_count"] != 2
            or len({row["xi_id"] for row in slots}) != 1
            or any(row["active_members"] != list(MEMBERS) for row in slots)
            or [row["slot_id"] for row in entries] != [row["slot_id"] for row in slots]):
        raise ValueError("Keep sixteen raw slots in one exact situation and two stable members")
    byslot = {row["slot_id"]: row for row in records}
    if len(byslot) != len(records) or set(byslot) - {row["slot_id"] for row in slots}:
        raise ValueError("Retain each declared raw slot once")
    if len(records) != len(slots) or any(row.get("status") != "closed" for row in records):
        return {"version": VERSION, "status": "incomplete_keep_original_inventory",
                "original_slot_count": SUPPORT_M, "supports_by_xi": None,
                "eligible_blocks": [], "selected_block": None,
                "raw_slot_inventory": [{"slot_id": row["slot_id"], "xi_id": row["xi_id"],
                    "status": byslot.get(row["slot_id"], {}).get("status", "not_started")} for row in slots],
                "gradient_or_update_identifiability_checked": False, "automatic_P3_execution": False}
    diagnostic = inspect_allocation_window(declaration, records)
    result = {**diagnostic, "version": VERSION, "original_slot_count": SUPPORT_M,
              "eligible_blocks": [], "selected_block": None,
              "member_selection_order": list(MEMBERS), "member_support_states": {},
              "gradient_or_update_identifiability_checked": False,
              "automatic_P3_execution": False}
    if diagnostic["status"] != "ready":
        return result
    supports, _ = supports_from_entries(entries, declaration, records)
    if supports != diagnostic["supports_by_xi"]:
        raise ValueError("Diagnostic and original-entry support reconstruction differ")
    xi = slots[0]["xi_id"]
    for member in MEMBERS:
        block = supports[xi]["blocks"][member]
        raw, supported = block["candidate_counts_before_support"], block["b"]
        if not raw:
            state = "no_mapped_valid_support"
        elif len(raw) == 1:
            state = "single_supported_class" if supported else "single_class_below_frequency"
        elif len(supported) < 2:
            state = "multiple_classes_below_frequency"
        else:
            state = "formal_composition_freedom_gradient_unchecked"
        result["member_support_states"][member] = state
        if len(supported) >= 2 and result["selected_block"] is None:
            result.update(eligible_blocks=[[xi, member]], selected_block=[xi, member])
    result["status"] = "ready_for_postcollection_freeze" if result["selected_block"] else "no_configurable_support"
    result["scope"] = ("Whole original current-policy window; first qualifying member only. "
                       "Failure/unmapped/rare and other-member branches retain baseline treatment. "
                       "Formal support freedom does not certify distinguishable gradients or updates.")
    return result


def _method_supports(original, method, eligible):
    value = copy.deepcopy(original)
    if method == "G-raw":
        for xi, member in eligible:
            block = value[xi]["blocks"][member]
            raw = sorted(block["eligible_slots"])
            block.update(b=dict.fromkeys(raw, 1 / len(raw)),
                         n_by_class=dict.fromkeys(raw, 1),
                         eligible_slots={sid: sid for sid in raw})
    elif method not in {"B", "I-P"}:
        raise ValueError("Use the separately named B/G-raw/I-P methods")
    return value


def _development(value):
    fields = {"purpose", "split_manifest_sha256", "initial_state_sha256", "training_rng_sha256",
              "units", "independent_units", "provenance"}
    if (not isinstance(value, dict) or set(value) != fields
            or value["purpose"] != "contribution_development"
            or value["provenance"] not in {"synthetic_cpu_control", "current_model_development"}):
        raise ValueError("Freeze a separate paired contribution panel before feedback")
    for key in ("split_manifest_sha256", "initial_state_sha256", "training_rng_sha256"):
        token = value[key]
        if not isinstance(token, str) or len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
            raise ValueError("Bind the full common, training RNG and purpose split by SHA256")
    groups = []
    for panel in ("units", "independent_units"):
        rows = value[panel]
        if not isinstance(rows, list) or not rows:
            raise ValueError("Keep nonempty development and independent panels")
        for row in rows:
            if (set(row) != {"unit_id", "root_id", "seed", "weight"}
                    or any(not isinstance(row[key], str) or not row[key] for key in ("unit_id", "root_id"))
                    or type(row["seed"]) is not int or type(row["weight"]) not in (int, float)
                    or not math.isfinite(row["weight"]) or row["weight"] <= 0):
                raise ValueError("Each panel unit requires root, paired seed and positive weight")
        ids, roots = {row["unit_id"] for row in rows}, {row["root_id"] for row in rows}
        if len(ids) != len(rows) or len(roots) < 2:
            raise ValueError("Each panel must cover at least two different root goals")
        groups.append((ids, roots))
    if groups[0][0] & groups[1][0] or groups[0][1] & groups[1][1]:
        raise ValueError("Independent root goals and units cannot select configuration")
    return copy.deepcopy(value)


def freeze_allocation_plan(supports_by_xi, *, eligible_blocks, development,
                           budget, constraints=None, probe_tv=PROBE_TV):
    """Freeze all raw/class directions after collection and before any C feedback."""
    _validate_supports(supports_by_xi)
    limits = rule._limits(constraints)
    if (type(probe_tv) not in (int, float) or not math.isfinite(probe_tv)
            or not 0 < probe_tv <= limits["tv_limit"]
            or not limits["lower"] < 1 < limits["upper"]):
        raise ValueError("Freeze a positive interior finite-difference radius")
    eligible = [list(pair) for pair in eligible_blocks]
    if len(eligible) != 1 or len(eligible[0]) != 2:
        raise ValueError("Configure only the first eligible member block")
    xi, member = eligible[0]
    first = next(([key, actor] for key in sorted(supports_by_xi) for actor in MEMBERS
                  if len(supports_by_xi[key]["blocks"].get(actor, {}).get("b", {})) >= 2), None)
    if eligible[0] != first:
        raise ValueError("Use the predeclared member ordering, never favorable subset selection")
    block = supports_by_xi[xi]["blocks"][member]
    if (len(supports_by_xi) != 1 or block["M"] != SUPPORT_M or len(block["b"]) != 2
            or supports_by_xi[xi]["min_class_count"] != 2
            or set(supports_by_xi[xi]["blocks"]) != set(MEMBERS)):
        raise ValueError("This finite study has one sixteen-slot situation and two frozen work classes")
    dev = _development(development)
    fields = {"max_unique_trial_updates", "max_development_episodes", "formal_updates_per_method",
              "independent_episodes_per_method"}
    if (not isinstance(budget, dict) or set(budget) != fields
            or any(type(v) is not int or v < 1 for v in budget.values())
            or budget["formal_updates_per_method"] != 1
            or budget["independent_episodes_per_method"] != len(dev["independent_units"])):
        raise ValueError("Freeze complete trial, formal-update and confirmation counts")
    plan = {"version": VERSION, "supports_by_xi": copy.deepcopy(supports_by_xi),
            "eligible_blocks": eligible, "constraints": limits, "probe_tv": probe_tv,
            "development": dev, "development_sha256": _sha(dev), "budget": copy.deepcopy(budget),
            "methods": {}, "candidates": {}, "history_initialization": "explicit h=b in the first window",
            "history_transport_implemented": False, "solver_version": rule.VERSION,
            "fairness_regime": "one identical complete-window formal update per method; not equal-total-compute efficiency",
            "scope": "Original member actor composition only; all baseline shares, masks, advantages and critic rules remain."}
    baseline = _baseline(supports_by_xi)
    base_mat = _materialize(supports_by_xi, baseline, limits)
    plan["candidates"]["B"] = {"method": "B", "q_by_xi": baseline, "weights_sha256": _weights_hash(base_mat)}
    for method in METHODS[1:]:
        supports = _method_supports(supports_by_xi, method, eligible)
        base = _baseline(supports)
        b = base[xi][member]
        binding = {"window_id": supports[xi]["window"]["window_id"], "situation_id": xi, "member_id": member}
        initial = {"binding": binding, "method": method, "q": b, "declared_initial_history": "h=b"}
        history = rule.freeze_history_anchor(b, binding=binding,
            coordinate_system="original_member_trajectory" if method == "G-raw" else "member_class",
            source_window_id=binding["window_id"], source_configuration_sha256=_sha(initial),
            transport_rule="Declared first-window h=b; no cross-window history transport",
            kind="declared_initial_configuration")
        directions = []
        for index, direction in enumerate(_helmert(sorted(b))):
            radius = probe_tv / (math.fsum(abs(v) for v in direction.values()) / 2)
            for key, component in direction.items():
                if component:
                    radius = min(radius, b[key] * (1 - limits["lower"]) / abs(component),
                                 b[key] * (limits["upper"] - 1) / abs(component))
            radius *= 1 - 1e-12
            ids = []
            for sign in (-1, 1):
                q = copy.deepcopy(base)
                q[xi][member] = {key: b[key] + sign * radius * direction[key] for key in b}
                cid = method + "-" + _sha([xi, member, index, sign])[:20]
                mat = _materialize(supports, q, limits)
                plan["candidates"][cid] = {"method": method, "q_by_xi": q, "weights_sha256": _weights_hash(mat)}
                ids.append(cid)
            directions.append({"xi_id": xi, "member_id": member, "direction": direction,
                               "radius": radius, "minus_id": ids[0], "plus_id": ids[1]})
        plan["methods"][method] = {"directions": directions, "baseline_q_by_xi": base,
            "binding": binding, "history": history, "coverage": dict.fromkeys(b, 1 / len(b)),
            "coverage_rule": "uniform_original_trajectories" if method == "G-raw" else "uniform_supported_work_classes",
            "required_trial_updates_including_shared_B": 1 + 2 * len(directions)}
    count = len(plan["candidates"])
    if (count > budget["max_unique_trial_updates"]
            or count * len(dev["units"]) > budget["max_development_episodes"]):
        raise ValueError("Budget cannot cover all raw and class directions; do not drop trajectories or probes")
    plan["actual_inventory"] = {"n_positive": block["n_positive"], "K": len(block["b"]),
        "unique_trial_updates": count, "shared_B_copies": 1,
        "development_episodes": count * len(dev["units"]), "formal_updates": 3,
        "independent_episodes": 3 * len(dev["independent_units"])}
    plan["plan_sha256"] = _sha(plan)
    return plan


def _check_plan(plan):
    if (plan.get("version") != VERSION
            or plan.get("plan_sha256") != _sha({k: v for k, v in plan.items() if k != "plan_sha256"})):
        raise ValueError("The postcollection allocation freeze changed")


def candidate_materialization(plan, candidate_id):
    _check_plan(plan)
    candidate = plan["candidates"][candidate_id]
    supports = _method_supports(plan["supports_by_xi"], candidate["method"], plan["eligible_blocks"])
    materialized = _materialize(supports, candidate["q_by_xi"], plan["constraints"])
    if _weights_hash(materialized) != candidate["weights_sha256"]:
        raise ValueError("Candidate weights changed after freezing")
    return materialized


def development_receipt(plan, candidate_id, utilities, *, provenance):
    """Format supplied post-update outcomes; the runner separately certifies execution."""
    _check_plan(plan)
    dev = plan["development"]
    if provenance != dev["provenance"] or len(utilities) != len(dev["units"]):
        raise ValueError("Every paired developer unit and its declared provenance must be retained")
    if any(v is not None and (type(v) not in (int, float) or not math.isfinite(v)) for v in utilities):
        raise ValueError("Unknown utility is None, not a fabricated zero")
    if provenance == "current_model_development" and any(v is not None and (type(v) is not int or v not in (0, 1)) for v in utilities):
        raise ValueError("Actual development uses complete R=0/1 or unknown")
    return {"candidate_id": candidate_id, "weights_sha256": plan["candidates"][candidate_id]["weights_sha256"],
            "development_sha256": plan["development_sha256"], "provenance": provenance,
            "initial_state_sha256": dev["initial_state_sha256"], "training_rng_sha256": dev["training_rng_sha256"],
            "outcomes": [{**unit, "utility": value} for unit, value in zip(dev["units"], utilities)]}


def select_allocation(plan, receipts):
    """Estimate centered post-update C, then call the existing logarithmic-N solver."""
    _check_plan(plan)
    observed = {}
    for receipt in receipts:
        cid = receipt.get("candidate_id")
        if cid not in plan["candidates"] or cid in observed:
            raise ValueError("Only one receipt per frozen unique candidate")
        utilities = [row.get("utility") for row in receipt.get("outcomes", [])]
        if receipt != development_receipt(plan, cid, utilities, provenance=plan["development"]["provenance"]):
            raise ValueError("Development receipt differs from frozen paired units/common/RNG")
        observed[cid] = utilities
    if set(observed) != set(plan["candidates"]) or any(v is None for values in observed.values() for v in values):
        raise ValueError("Incomplete or unknown development blocks formal selection; never fill unknown with zero")
    xi, member = plan["eligible_blocks"][0]
    units = plan["development"]["units"]
    denominator = math.fsum(row["weight"] for row in units)
    def utility(cid):
        return math.fsum(row["weight"] * value for row, value in zip(units, observed[cid])) / denominator
    selections = {"B": {"method": "B", "q_by_xi": copy.deepcopy(plan["candidates"]["B"]["q_by_xi"]),
                         "Q_equals_B": True, "reason": "Q=B without composition intervention", "solutions": []}}
    for method in METHODS[1:]:
        spec = plan["methods"][method]
        q = copy.deepcopy(spec["baseline_q_by_xi"])
        b = q[xi][member]
        slopes, contrasts = dict.fromkeys(b, 0.0), []
        for direction in spec["directions"]:
            plus, minus = utility(direction["plus_id"]), utility(direction["minus_id"])
            derivative = (plus - minus) / (2 * direction["radius"])
            for key, component in direction["direction"].items():
                slopes[key] += derivative * component
            contrasts.append({**direction, "plus_minus_utility": plus - minus,
                              "plus_minus_B": plus - utility("B"), "minus_minus_B": minus - utility("B")})
        offset = math.fsum(b[key] * slopes[key] for key in b)
        centered = {key: slopes[key] - offset for key in b}
        if method == "G-raw":
            # No work classes, graph, semantic coverage, or grouped C enters this call.
            solution = rule.solve_g_raw(b, centered, history=spec["history"], binding=spec["binding"],
                                        constraints=plan["constraints"])
        else:
            solution = rule.solve_i_p(b, centered, spec["coverage"], history=spec["history"],
                                      binding=spec["binding"], constraints=plan["constraints"])
        q[xi][member] = solution["q"]
        materialized = _materialize(_method_supports(plan["supports_by_xi"], method, plan["eligible_blocks"]), q, plan["constraints"])
        zero = all(row["plus_minus_utility"] == 0 for row in contrasts)
        weight_delta = max(abs(weight - 1) for value in materialized.values()
                           for branch in value["members"].values() for weight in branch["weights"].values())
        selections[method] = {"method": method, "q_by_xi": q,
            "Q_equals_B": _weights_hash(materialized) == plan["candidates"]["B"]["weights_sha256"],
            "maximum_absolute_weight_delta": weight_delta,
            "Q_equals_B_within_1e12": weight_delta <= 1e-12,
            "solutions": [{"xi_id": xi, "member_id": member, **solution}],
            "finite_differences": contrasts, "centering_offset": offset,
            "all_observed_direction_differences_zero": zero,
            "reason": ("No directional difference detected on this panel; any q change comes from declared priors/anchors or numerical roundoff"
                       if zero else "Configuration uses centered derivatives of paired post-update developer work"),
            "true_contribution_proved_zero": False}
    return {"version": VERSION, "plan_sha256": plan["plan_sha256"], "receipts": copy.deepcopy(receipts),
            "selections": selections, "provenance": plan["development"]["provenance"],
            "effectiveness_evidence": False,
            "scope": "Post-update developer selection only; independent utility gains remain unmeasured here."}


def _bind(entries, declaration, records, plan, *, candidate_id=None, selection=None, method=None):
    supports, _ = supports_from_entries(entries, declaration, records)
    if supports != plan["supports_by_xi"]:
        raise ValueError("Frozen support differs from the original current-policy actions")
    if candidate_id is not None:
        materialized = candidate_materialization(plan, candidate_id)
        extra = {"kind": "trial", "candidate_id": candidate_id,
                 "method": plan["candidates"][candidate_id]["method"]}
    else:
        if method not in METHODS or select_allocation(plan, selection["receipts"]) != selection:
            raise ValueError("Formal selection must follow the frozen v030 rule and exact developer evidence")
        q = selection["selections"][method]["q_by_xi"]
        materialized = _materialize(_method_supports(supports, method, plan["eligible_blocks"]), q, plan["constraints"])
        extra = {"kind": "formal", "selection": copy.deepcopy(selection), "method": method}
    return {"version": VERSION, "window_id": declaration["window_id"],
            "actor_identity": copy.deepcopy(declaration["actor_identity"]), "entries_sha256": _sha(entries),
            "declaration": copy.deepcopy(declaration), "records": copy.deepcopy(records),
            "plan": copy.deepcopy(plan), "materialized_by_xi": materialized,
            "Q_equals_B": _weights_hash(materialized) == plan["candidates"]["B"]["weights_sha256"], **extra}


def bind_candidate(entries, declaration, records, plan, candidate_id):
    return _bind(entries, declaration, records, plan, candidate_id=candidate_id)


def bind_allocation(entries, declaration, records, plan, selection, *, method):
    return _bind(entries, declaration, records, plan, selection=selection, method=method)


def validate_allocation(entries, prepared, allocation):
    """Validate original own actions, masks and fixed denominators for the updater."""
    if allocation.get("version") != VERSION:
        raise ValueError("Use a bound v035 allocation")
    if allocation.get("kind") == "trial":
        rebuilt = bind_candidate(entries, allocation["declaration"], allocation["records"],
                                 allocation["plan"], allocation["candidate_id"])
    elif allocation.get("kind") == "formal":
        rebuilt = bind_allocation(entries, allocation["declaration"], allocation["records"],
                                  allocation["plan"], allocation["selection"], method=allocation["method"])
    else:
        raise ValueError("Distinguish a planned trial from a formal update")
    if (rebuilt != allocation or prepared["window_id"] != allocation["window_id"]
            or prepared["actor_identity"] != allocation["actor_identity"]):
        raise ValueError("Allocation differs from its entries, common actor or window")
    _, bindings = supports_from_entries(entries, allocation["declaration"], allocation["records"])
    byslot = {entry["slot_id"]: entry for entry in entries}
    seen, weights, rows = set(), [], []
    for row in prepared["decisions"]:
        sid, member, call = row["slot_id"], row["member_id"], row["call_id"]
        if (sid, member, call) in seen:
            raise ValueError("An original member action cannot be counted twice")
        seen.add((sid, member, call))
        bound = bindings[sid]
        view = bound["member_views"].get(member)
        if view is None or member not in byslot[sid]["active_members"]:
            raise ValueError("No cross-member transfer of targets")
        own = [d for d in view["decisions"] if d["call_id"] == call and d["actor_required"]]
        if len(own) != 1:
            raise ValueError("Exactly one recoverable original own action is required")
        decision, tokens = own[0], own[0]["tokens"]
        member_count = len(byslot[sid]["active_members"])
        if (row["tokens"] != tokens or row["actual_response_sha256"] != decision["response_sha256"]
                or decision["loss_mask"] != [0] * len(tokens["input_ids"]) + [1] * len(tokens["output_ids"])
                or row["actor_denominator"] != len(entries) * member_count * view["own_action_tokens"]
                or row["critic_denominator"] != len(entries) * member_count
                   * sum(d["actor_required"] for d in view["decisions"])):
            raise ValueError("Keep original tokens, loss masks and full baseline denominators")
        mat = allocation["materialized_by_xi"][bound["window"]["xi_id"]]["members"][member]
        if not mat["actor_mask"][sid]:
            raise ValueError("Composition cannot admit an excluded base target")
        weight = mat["weights"][sid]
        weights.append(weight)
        rows.append({"slot_id": sid, "member_id": member, "call_id": call, "weight": weight,
                     "tokens_sha256": _sha(tokens), "actor_denominator": row["actor_denominator"],
                     "critic_denominator": row["critic_denominator"]})
    changed = [{"xi_id": xi, "member_id": member}
               for xi, value in allocation["materialized_by_xi"].items()
               for member, row in value["members"].items() if any(v != 1 for v in row["weights"].values())]
    return weights, {"version": VERSION, "allocation_sha256": _sha(allocation),
                     "Q_equals_B": allocation["Q_equals_B"], "changed_blocks": changed,
                     "rows": rows, "original_normalization_preserved": True}
