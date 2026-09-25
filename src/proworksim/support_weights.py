"""Pure-Python member/situation support and actor-weight materialization.

No actor/critic update is implemented here. Original slots are never silently
removed, and the policy probability ratio is not this composition weight.
"""

import copy
import math

from .team_rollout import validate_window

SUPPORT_VERSION = "member-support-v0.12"


def build_support(slots, *, window, member_ids, min_class_count=1):
    window = validate_window(window)
    if type(min_class_count) is not int or min_class_count < 1:
        raise ValueError("Support threshold must be frozen before collection")
    if not slots or len({row["slot_id"] for row in slots}) != len(slots):
        raise ValueError("A fixed nonempty unique raw-slot inventory is required")
    if not member_ids or len(member_ids) != len(set(member_ids)):
        raise ValueError("Fixed distinct members are required")
    for slot in slots:
        if slot.get("window") != window:
            raise ValueError("Cannot merge layouts, protocols, policies or collection windows")
    rollout_ids = [
        slot["rollout"]["rollout_id"] for slot in slots if slot.get("rollout") is not None
    ]
    if len(rollout_ids) != len(set(rollout_ids)):
        raise ValueError("Member projections or copied records cannot create new joint samples")
    mapping_specs = {
        slot.get("mapping", {}).get("spec_id") for slot in slots if slot.get("mapping")
    }
    validity_specs = {
        slot["rollout"]["work_validity"].get("spec_id") for slot in slots if slot.get("rollout")
    }
    if len(mapping_specs) > 1 or len(validity_specs) > 1:
        raise ValueError("Mapping and validity contracts must be frozen within a material window")
    blocks = {}
    for member_id in member_ids:
        candidates, semantic, base, diagnostics = {}, {}, {}, {}
        for slot in slots:
            sid = slot["slot_id"]
            rollout, mapping = slot.get("rollout"), slot.get("mapping", {})
            view = slot.get("member_views", {}).get(member_id)
            reasons = []
            if rollout is None:
                base[sid] = False
                diagnostics[sid] = ["unusable_raw_slot_retained"]
                continue
            if rollout["window"] != window or (
                view
                and (
                    view["window"] != window
                    or view["rollout_id"] != rollout["rollout_id"]
                    or view["member_id"] != member_id
                )
            ):
                raise ValueError("Member projection does not belong to this rollout/member/window")
            if mapping.get("rollout_id") not in {None, rollout["rollout_id"]}:
                raise ValueError("Mapped method belongs to another joint rollout")
            reward_ok = rollout["reward_eligibility"].get("eligible") is True
            actor_ok = (
                view is not None
                and view.get("complete_actor_trajectory") is True
                and view.get("own_action_count", 0) > 0
            )
            is_current = rollout["members"].get(member_id, {}).get("origin") == "target_model"
            record_ok = (
                rollout["work_validity"].get("components", {}).get("record", {}).get("value")
                is True
            )
            base[sid] = bool(reward_ok and actor_ok and is_current and record_ok)
            if (
                is_current
                and rollout["work_validity"].get("value") is True
                and mapping.get("status") == "mapped"
                and view is not None
                and view.get("own_action_count", 0) > 0
                and view.get("complete_semantic_trajectory") is True
            ):
                semantic[sid] = mapping["class_id"]
            if not reward_ok:
                reasons.append("reward_unavailable")
            if not record_ok:
                reasons.append("record_integrity_unverified")
            if not actor_ok:
                reasons.append("no_complete_recoverable_own_actions")
            if rollout["members"].get(member_id, {}).get("origin") != "target_model":
                reasons.append("not_current_target_model_origin")
            if rollout["work_validity"].get("value") is not True:
                reasons.append("work_validity_false_or_unknown")
            if mapping.get("status") != "mapped" or not isinstance(mapping.get("class_id"), str):
                reasons.append("joint_method_not_reliably_mapped")
            diagnostics[sid] = reasons
            if not reasons:
                candidates[sid] = mapping["class_id"]
        raw_counts = {}
        for category in candidates.values():
            raw_counts[category] = raw_counts.get(category, 0) + 1
        supported = {category for category, count in raw_counts.items() if count >= min_class_count}
        eligible = {sid: category for sid, category in candidates.items() if category in supported}
        for sid, category in candidates.items():
            if category not in supported:
                diagnostics[sid].append("below_frozen_class_support")
        counts = {
            category: count
            for category, count in sorted(raw_counts.items())
            if category in supported
        }
        n = sum(counts.values())
        blocks[member_id] = {
            "M": len(slots),
            "n_positive": n,
            "v": n / len(slots),
            "n_by_class": counts,
            "b": {category: count / n for category, count in counts.items()},
            "candidate_counts_before_support": raw_counts,
            "semantic_work_support": {
                category: list(semantic.values()).count(category)
                for category in sorted(set(semantic.values()))
            },
            "semantic_work_slots": semantic,
            "semantic_support_is_not_trainable_support": True,
            "eligible_slots": eligible,
            "base_actor_mask": base,
            "diagnostics": diagnostics,
            "composition_degrees_of_freedom": max(0, len(counts) - 1),
        }
    return {
        "version": SUPPORT_VERSION,
        "window": window,
        "slot_ids": [row["slot_id"] for row in slots],
        "min_class_count": min_class_count,
        "blocks": blocks,
        "denominator_contract": "M is the frozen raw joint-slot inventory. Missing/untrusted actor slots contribute zero actor loss, not fake targets; all raw slots remain reported. D3 must preserve its declared base normalization exactly.",
    }


def materialize_weights(support, q, *, lower=0.1, upper=10.0):
    if not (0 < lower <= 1 <= upper) or not all(math.isfinite(value) for value in (lower, upper)):
        raise ValueError("Composition ratio bounds must contain one")
    if set(q) != set(support["blocks"]):
        raise ValueError("No member budget may be silently dropped or transferred")
    result = {}
    for member_id, block in support["blocks"].items():
        b, target = block["b"], q[member_id]
        if set(target) != set(b):
            raise ValueError("Target cannot create unsupported categories")
        if any(
            type(value) not in (int, float) or not math.isfinite(value) or value < 0
            for value in target.values()
        ):
            raise ValueError("Composition must contain finite nonnegative probabilities")
        if b and not math.isclose(sum(target.values()), 1.0, rel_tol=0, abs_tol=1e-12):
            raise ValueError("Composition must be normalized, not clipped without normalization")
        ratios = {category: target[category] / b[category] for category in b}
        if any(not lower <= ratio <= upper for ratio in ratios.values()):
            raise ValueError("Composition is outside the declared ratio box")
        weights = {
            sid: ratios[block["eligible_slots"][sid]] if sid in block["eligible_slots"] else 1.0
            for sid in support["slot_ids"]
        }
        result[member_id] = {
            "q": copy.deepcopy(target),
            "weights": weights,
            "actor_mask": copy.deepcopy(block["base_actor_mask"]),
            "total_slot_weight": sum(weights.values()),
            "eligible_branch_weight": sum(weights[sid] for sid in block["eligible_slots"]),
            "v": block["v"],
            "normalization": "Frozen baseline denominator; never divide by per-minibatch sum of weights",
        }
    return {
        "version": "composition-materialization-v0.12",
        "window": copy.deepcopy(support["window"]),
        "members": result,
        "scope": "Actor weights only; PPO ratio/advantages/critic/entropy/KL remain the independently frozen base recipe",
    }


def weighted_actor_sum(losses, materialized, member_id):
    """Scalar reference only; no absent action is assigned a made-up loss."""
    member = materialized["members"][member_id]
    if set(losses) != set(member["weights"]):
        raise ValueError("Loss slots must preserve the entire original inventory")
    return sum(member["weights"][sid] * losses[sid] for sid in losses if member["actor_mask"][sid])
