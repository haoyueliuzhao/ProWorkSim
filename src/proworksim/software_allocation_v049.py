"""One predeclared finite composition direction on the new v049 O1 material.

Support reuses the original member support rules. Actual B leaf gradients only
inspect directions; no gradient here enters an optimizer, no development result
is accepted, and neither missing mass nor residual trajectories are reassigned.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path

from .online_training import tensor_tree_digest
from .software_learning_v049 import MEMBERS, VERSION as LEARNING_VERSION
from .storage import digest, json_bytes
from .support_weights import build_support, materialize_weights

VERSION = "software-finite-direction-v0.49"
MAPPER = "software-work-delivery-mapper-v0.49"
CATEGORIES = ("local_lineage_delivery", "evidenced_peer_product_delivery")
ROOTS = ("LA", "LB")
LOWER, UPPER, TV_LIMIT = .5, 2., .2


def _sealed(value):
    value["seal_sha256"] = digest(json_bytes(value))
    return value


def _check_seal(value):
    if value.get("seal_sha256") != digest(json_bytes({key: item for key, item in value.items() if key != "seal_sha256"})):
        raise ValueError("Frozen support/direction seal changed")


def _inventory(entries, declaration, admission, design):
    scheduled = design["training_slots"]
    if (len(scheduled) != 8 or [row["root"] for row in scheduled] != ["LA"] * 4 + ["LB"] * 4
            or any(row["members"] != list(MEMBERS) or row["purpose"] != "policy_training" for row in scheduled)
            or [row["slot_id"] for row in entries] != [row["slot_id"] for row in scheduled]
            or [row["slot_id"] for row in declaration["slots"]] != [row["slot_id"] for row in scheduled]
            or [row["slot_id"] for row in admission["slots"]] != [row["slot_id"] for row in scheduled]
            or admission["slot_count"] != 8 or admission["window_id"] != declaration["window_id"]
            or admission["actor_identity"] != declaration["actor_identity"]
            or digest(json_bytes(design)) != declaration["gamma_identity"].get("design_sha256")
            or declaration["min_class_count"] != 2 or design["mapper"]["category_order"] != list(CATEGORIES)
            or design["direction"]["weight_lower"] != LOWER or design["direction"]["weight_upper"] != UPPER
            or design["direction"]["total_variation_from_b_max"] != TV_LIMIT):
        raise ValueError("Support must preserve the frozen eight-slot/two-root/two-member design and original admission")
    for slot in declaration["slots"]:
        if slot["active_members"] != list(MEMBERS) or slot["mapping_spec_id"] != MAPPER:
            raise ValueError("Only the declared O1 members and v049 Mapper enter support")
    actual = [entry["rollout"]["rollout_id"] for entry in entries if entry.get("rollout") is not None]
    if len(set(actual)) != len(actual):
        raise ValueError("One original joint episode cannot fill multiple raw support slots")
    row_keys = [(row["slot_id"], row["member_id"], row["call_id"]) for row in admission["decisions"]]
    if len(row_keys) != len(set(row_keys)):
        raise ValueError("Original admitted decisions cannot be duplicated")
    return {row["slot_id"]: row for row in scheduled}


def build_support_report(entries, declaration, *, admission, design, learner_report=None):
    """Keep original M=4 blocks and bind eligibility to actual base admission."""
    from .software_training_v049 import bind_rollout, expected_window
    scheduled = _inventory(entries, declaration, admission, design)
    admitted = {}
    for index, row in enumerate(admission["decisions"]):
        admitted.setdefault((row["slot_id"], row["member_id"]), []).append((index, row))
    advantages = None
    if learner_report is not None:
        advantages = learner_report.get("advantages", [] if not admission["decisions"] else None)
        if (learner_report.get("before_actor_identity") != declaration["actor_identity"]
                or learner_report.get("window_id") != declaration["window_id"]
                or not isinstance(advantages, list) or len(advantages) != len(admission["decisions"])
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in advantages)):
            raise ValueError("Support advantages require the actual same-S0 B learner report")
    byslot = {entry["slot_id"]: entry for entry in entries}
    summaries = {row["slot_id"]: row for row in admission["slots"]}
    bound, raw = {}, []
    for slot in declaration["slots"]:
        sid, entry = slot["slot_id"], byslot[slot["slot_id"]]
        rollout = entry.get("rollout")
        if rollout is None:
            bound[sid] = {"slot_id": sid, "window": expected_window(declaration, sid), "rollout": None}
        else:
            bound[sid] = bind_rollout(declaration, sid, rollout, mapping=entry.get("mapping"))
            mapping = bound[sid]["mapping"]
            if mapping.get("status") == "mapped" and mapping.get("class_id") not in CATEGORIES:
                raise ValueError("Mapper cannot introduce a postcollection category")
        raw.append({"slot_id": sid, "root": scheduled[sid]["root"], "rollout_available": rollout is not None,
            "status": entry.get("status", "closed" if rollout is not None else "unavailable_original_slot"),
            "reward": copy.deepcopy(entry.get("reward")),
            "validity": copy.deepcopy(rollout.get("work_validity")) if rollout else None,
            "mapping": copy.deepcopy(entry.get("mapping")),
            "original_admission": copy.deepcopy(summaries[sid])})
    roots = {}
    for root in ROOTS:
        sids = [row["slot_id"] for row in design["training_slots"] if row["root"] == root]
        blocks = {}
        window = bound[sids[0]]["window"]
        for member in MEMBERS:
            member_slots = []
            projection_exclusions = {}
            for sid in sids:
                item = copy.deepcopy(bound[sid])
                reasons = []
                if item.get("rollout") is not None:
                    projection = item["mapping"].get("member_projections", {}).get(member, {})
                    if (projection.get("support_eligible") is not True
                            or projection.get("class_id") != item["mapping"].get("class_id")
                            or projection.get("complete_actor_trajectory") is not True
                            or projection.get("actual_input_bindings_complete") is not True):
                        # Diagnostic member projection only: the original Mapper
                        # and original training entry above remain unchanged.
                        item["mapping"] = {**item["mapping"], "status": "unmapped", "class_id": None}
                        reasons.append("member_projection_not_supported")
                    if not admitted.get((sid, member)):
                        item["member_views"][member]["complete_actor_trajectory"] = False
                        reasons.append("original_learner_admission_excluded")
                projection_exclusions[sid] = reasons
                member_slots.append(item)
            original = build_support(member_slots, window=window, member_ids=[member], min_class_count=2)
            block = original["blocks"][member]
            for sid in sids:
                block["diagnostics"][sid].extend(projection_exclusions[sid])
                if block["base_actor_mask"][sid] != bool(admitted.get((sid, member))):
                    raise ValueError("Support and original learner disagree on a base target; do not repair by reweighting")
            values = [advantages[index] for sid in sids for index, _ in admitted.get((sid, member), [])] if advantages is not None else None
            original_trajectories = sum(block["base_actor_mask"].values())
            eligible_count = len(block["eligible_slots"])
            blocks[member] = {**block,
                "actual_repeats": sum(bound[sid].get("rollout") is not None for sid in sids),
                "base_training_trajectory_count": original_trajectories,
                "admitted_decision_count": sum(len(admitted.get((sid, member), [])) for sid in sids),
                "actual_advantages": values,
                "actual_advantage_counts": {"positive": sum(value > 0 for value in values),
                    "negative": sum(value < 0 for value in values), "zero": sum(value == 0 for value in values)} if values is not None else None,
                "effective_quality": block["v"],
                "G_raw_within_eligible_trajectory_degrees_of_freedom": max(0, eligible_count - 1),
                "G_raw_within_class_degrees_of_freedom": sum(max(0, count - 1) for count in block["n_by_class"].values()),
                "G_raw_executed": False,
                "base_measure": "Each original member trajectory has mass 1/(8*2), internally averaged over own output tokens; M=4 and v=n/4 describe only this root/member support block."}
        roots[root] = {"root": root, "xi_id": window["xi_id"], "window": window, "slot_ids": sids, "blocks": blocks,
            "min_class_count": 2}
    return _sealed({"version": VERSION, "window_id": declaration["window_id"],
        "actor_identity": copy.deepcopy(declaration["actor_identity"]),
        "design_sha256": declaration["gamma_identity"]["design_sha256"],
        "mapper_spec_sha256": declaration["gamma_identity"]["mapper_spec_sha256"],
        "declaration_sha256": digest(json_bytes(declaration)), "entries_sha256": digest(json_bytes(entries)),
        "admission_sha256": digest(json_bytes(admission)),
        "learner_report_sha256": digest(json_bytes(learner_report)) if learner_report is not None else None,
        "B_behavior_probability_passed": learner_report.get("behavior_probability_passed") if learner_report else None,
        "B_completed_original_decisions": learner_report.get("backward_decisions_completed") if learner_report else None,
        "root_order": list(ROOTS), "member_order": list(MEMBERS), "category_order": list(CATEGORIES),
        "roots": roots, "original_slots": raw,
        "gradient_expected_rows": [{key: row[key] for key in ("slot_id", "member_id", "call_id", "actor_denominator")}
                                   for row in admission["decisions"]],
        "base_weights_by_slot": {row["slot_id"]: dict.fromkeys(MEMBERS, 1.0) for row in entries},
        "base_learning_material_available": bool(admission["decisions"]),
        "original_slot_count": 8, "global_member_denominator_factor": 16,
        "scope": "Finite current O1 support, not statistical power. Validity/Mapper govern optional composition only; trusted failures and unmapped base targets retain unit weights and the unchanged global denominator."})


def feasible_radius(b, category):
    """Exact two-sided simplex, supported-ratio-box and TV radius for e_z-b."""
    if (category not in b or len(b) < 2 or any(not math.isfinite(value) or value <= 0 for value in b.values())
            or not math.isclose(math.fsum(b.values()), 1., rel_tol=0, abs_tol=1e-12)):
        raise ValueError("A supported positive multiclass distribution is required")
    direction = {key: float(key == category) - value for key, value in b.items()}
    limits = [TV_LIMIT / (.5 * math.fsum(abs(value) for value in direction.values()))]
    for key, value in direction.items():
        if value:
            limits.extend(((1 - LOWER) * b[key] / abs(value), (UPPER - 1) * b[key] / abs(value), b[key] / abs(value)))
    return min(limits), direction


def _validate_gradients(support, gradients, receipt, torch):
    if (receipt.get("version") != LEARNING_VERSION or receipt.get("hook_returns") is not None
            or receipt.get("additional_actor_forwards") != 0 or receipt.get("additional_actor_backwards") != 0
            or receipt.get("optimizer_steps") != 0 or receipt.get("observed_baseline_loss_before_shared_clipping") is not True
            or receipt.get("original_rows") != support["gradient_expected_rows"]
            or support.get("B_behavior_probability_passed") is not True
            or support.get("B_completed_original_decisions") != len(support["gradient_expected_rows"])):
        raise ValueError("Direction requires complete same-material actual B gradient observation")
    ref = receipt.get("tensor_file", {})
    path = Path(ref.get("path", ""))
    if not path.is_file() or digest(path.read_bytes()) != ref.get("sha256"):
        raise ValueError("Actual B gradient tensor artifact is missing or changed")
    groups = {(row["slot_id"], row["member_id"]): row for row in receipt["groups"]}
    expected = {(row["slot_id"], row["member_id"]) for row in support["gradient_expected_rows"]}
    actual = {(sid, member) for sid, members in gradients.items() for member in members}
    if len(groups) != len(receipt["groups"]) or set(groups) != expected or actual != expected:
        raise ValueError("Gradient groups must cover exactly the actual admitted original member rows")
    for sid, member in expected:
        values = gradients[sid][member]
        if (len(values) != groups[sid, member]["parameters"]
                or tensor_tree_digest(values, torch) != groups[sid, member]["gradient_sha256"]
                or any(value.device.type != "cpu" or not torch.isfinite(value).all() for value in values.values())):
            raise ValueError("Observed CPU leaf gradients or their exact group digests differ")


def select_direction(support, gradients, *, gradient_receipt, torch):
    """Choose the first supported nonzero actual mixture; never read development."""
    _check_seal(support)
    if support.get("version") != VERSION or support["root_order"] != list(ROOTS) or support["member_order"] != list(MEMBERS):
        raise ValueError("Only the frozen v049 canonical support order is accepted")
    _validate_gradients(support, gradients, gradient_receipt, torch)
    baseline = copy.deepcopy(support["base_weights_by_slot"])
    attempts, selected = [], None
    plus_weights, minus_weights = None, None
    for root in ROOTS:
        group = support["roots"][root]
        for member in MEMBERS:
            block = group["blocks"][member]
            b = block["b"]
            if len(b) < 2:
                attempts.append({"root": root, "member_id": member,
                    "reason": "no_qualified_support" if not b else "single_qualified_category",
                    "qualified_classes": len(b), "I_degrees_of_freedom": block["composition_degrees_of_freedom"],
                    "G_raw_within_class_degrees_of_freedom": block["G_raw_within_class_degrees_of_freedom"]})
                continue
            for category in CATEGORIES:
                if category not in b:
                    continue
                rho, direction = feasible_radius(b, category)
                epsilon = min(.1, rho / 2)
                item = {"root": root, "xi_id": group["xi_id"], "member_id": member,
                    "category": category, "b": copy.deepcopy(b), "direction": direction, "rho": rho, "epsilon": epsilon}
                if not math.isfinite(rho) or rho <= 0 or epsilon <= 0:
                    attempts.append({**item, "reason": "no_two_sided_feasible_radius"})
                    continue
                mixture, class_sums = {}, {key: {} for key in b}
                for sid in group["slot_ids"]:
                    if sid not in block["eligible_slots"]:
                        continue
                    label = block["eligible_slots"][sid]
                    delta_weight = direction[label] / b[label]
                    for name, value in gradients[sid][member].items():
                        value = value.double()
                        contribution = value * delta_weight
                        if name in mixture:
                            mixture[name].add_(contribution)
                        else:
                            mixture[name] = contribution.clone()
                        if name in class_sums[label]:
                            class_sums[label][name].add_(value)
                        else:
                            class_sums[label][name] = value.clone()
                norm = math.sqrt(sum(float(value.square().sum()) for value in mixture.values()))
                class_norms = {key: math.sqrt(sum(float(value.square().sum()) for value in values.values()))
                               / block["n_by_class"][key] for key, values in class_sums.items()}
                item.update(mixture_gradient_l2_norm=norm, mixture_gradient_sha256=tensor_tree_digest(mixture, torch),
                    class_mean_gradient_l2_norms=class_norms,
                    gradient_unit="Sum over original eligible slots of (d[class]/b[class])*actual_B_slot_member_gradient. B gradients already include 1/(8*2*member_output_tokens); no root or minibatch renormalization.",
                    class_mean_equivalence="n_eligible * sum_class d[class] * mean_original_B_gradient_in_class",
                    diagnostic_arithmetic="CPU float64 copies of original B leaf gradients; original training tensors and gradients unchanged")
                nonzero = any(bool(torch.count_nonzero(value)) for value in mixture.values())
                if not nonzero:
                    attempts.append({**item, "reason": "actual_mixture_gradient_zero"})
                    continue
                targets = [{key: b[key] + sign * epsilon * direction[key] for key in b} for sign in (1, -1)]
                for target in targets:
                    if (not math.isclose(math.fsum(target.values()), 1., rel_tol=0, abs_tol=1e-12)
                            or .5 * math.fsum(abs(target[key] - b[key]) for key in b) > TV_LIMIT + 1e-12):
                        raise ValueError("Frozen finite perturbation violated simplex or total variation")
                materials = []
                original_support = {"window": group["window"], "slot_ids": group["slot_ids"], "blocks": group["blocks"]}
                for target in targets:
                    q = {who: copy.deepcopy(value["b"]) for who, value in group["blocks"].items()}
                    q[member] = target
                    materials.append(materialize_weights(original_support, q, lower=LOWER, upper=UPPER))
                plus_weights, minus_weights = copy.deepcopy(baseline), copy.deepcopy(baseline)
                for weights, material in zip((plus_weights, minus_weights), materials):
                    for sid in group["slot_ids"]:
                        weights[sid][member] = material["members"][member]["weights"][sid]
                selected = {**item, "q_plus": targets[0], "q_minus": targets[1], "reason": "first_supported_feasible_nonzero_actual_B_mixture"}
                attempts.append(copy.deepcopy(selected))
                break
            if selected is not None:
                break
        if selected is not None:
            break
    return _sealed({"version": VERSION, "source_support_artifact_sha256": digest(json_bytes(support)),
        "gradient_receipt_sha256": digest(json_bytes(gradient_receipt)), "gradient_tensor_file": gradient_receipt["tensor_file"],
        "design_sha256": support["design_sha256"], "mapper_spec_sha256": support["mapper_spec_sha256"],
        "declaration_sha256": support["declaration_sha256"],
        "status": "one_direction_selected" if selected else "no_admissible_I_direction_B_only",
        "selected": selected, "epsilon": selected["epsilon"] if selected else None,
        "candidate_checks_in_frozen_order": attempts, "baseline_weights_by_slot": baseline,
        "plus_weights_by_slot": plus_weights, "minus_weights_by_slot": minus_weights,
        "development_results_read": False, "additional_samples": 0, "additional_backwards": 0,
        "scope": "A single supported local finite direction. Actual optimizer sensitivity and development utility remain to be measured; zero or absent I freedom does not remove G-raw within-class freedom."})
