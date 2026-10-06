"""Conservative fixed-product method mapping, separate from validity and targets.

Labels describe the delivered version's evidenced work route. They do not assign
code authorship, causal contribution, understanding or information independence.
"""
from __future__ import annotations

import copy

from .storage import digest, json_bytes
from .team_rollout import optimizer_scope_allows_update, validate_window

MAPPER_VERSION = MAPPER = "software-fixed-product-method-v0.35"
CLASS_ORDER = ("own_tree_delivery", "peer_fixed_product_delivery")


def mapping_spec():
    """Freeze this finite rule before collection; frequency gates are separate."""
    return {"version": MAPPER_VERSION, "spec_id": MAPPER, "class_order": list(CLASS_ORDER),
            "validity_gate": "Existing complete record/permission/basis/delivery validity must be true; never regrade an archive.",
            "binding": "Exact window_id, xi_id, xi_fingerprint, gamma_fingerprint and team_policy_fingerprint; stable actual member IDs. Do not pool roots, sources, first member, information conditions or policies.",
            "own_tree_delivery": "A verified current tested fixed delivery with own production edits, a complete version ancestry and no peer fixed-product import in that ancestry or actual peer-source acquisition by its deliverer before submission. Peer work on another branch and organizational task-board activity do not change this route class.",
            "peer_fixed_product_delivery": "A verified peer-authored fixed patch was actually integrated on the delivery ancestry. Its metadata and real import receipt appeared in the recipient's actual selected inputs before subsequent validation. At least one nontrivially changed whole production file was changed by the import and remains byte-identical through every descendant to the tested fixed delivery. No unresolved/conflicting import or wholly overwritten peer payload is promoted.",
            "unmapped": "Missing actual selected-input evidence, uncertain version ancestry, manual borrowing, conflicts, partial rewrites without the whole-file witness, overwritten peer payload, false/unknown complete validity or no retained own production work remain unmapped.",
            "production_content_rule": "The frozen public contract function/class definitions must change under normalized Python AST, excluding comments/format/docstrings and unrelated added module helpers. This is a conservative syntactic witness, not authorship, semantic equivalence or causal utility. Dynamic aliases and unrecognized definitions stay unmapped.",
            "information_boundary": "World materialization/verification and actor-visible selected request contents are separate. Visible import metadata/receipt can prove tool consumption without claiming peer source text was shown. Backend full test traces and independent acceptance are never actor-visible facts unless actually present in input.",
            "member_projection": "Keep the original member_view own actual output IDs/behavior records/labels/masks. Every trusted own action remains base data; membership does not require code authorship or two-member editing. No frequency filtering is performed here.",
            "purpose": "Development mappings are diagnostics only and cannot become current-policy support or optimizer material.",
            "scope": "Two work-route classes only; no arbitrary before/after, speaker or author subclasses. Conservative unmapped does not mean no cooperation occurred."}


def map_software_method(rollout, evidence, *, spec=None):
    """Return the standard online_support mapping without rewriting any rollout."""
    frozen = mapping_spec()
    if spec is not None and spec != frozen:
        raise ValueError("Mapper specification differs from the frozen v035 rule")
    if (evidence.get("rollout_sha256") != digest(json_bytes(rollout))
            or evidence.get("rollout_id") != rollout.get("rollout_id")
            or evidence.get("manifest_sha256") != rollout.get("manifest_sha256")
            or evidence.get("window") != validate_window(rollout["window"])):
        raise ValueError("Method evidence belongs to another exact rollout/window")
    supplied = evidence.get("evidence_sha256")
    if supplied != digest(json_bytes({k: v for k, v in evidence.items() if k != "evidence_sha256"})):
        raise ValueError("Method evidence seal differs from its actual payload")
    training_allowed = optimizer_scope_allows_update(rollout)
    result = {"version": MAPPER_VERSION, "rollout_id": rollout["rollout_id"], "spec_id": MAPPER,
              "status": "unmapped", "class_id": None, "window": copy.deepcopy(rollout["window"]),
              "evidence_sha256": supplied, "mapper_spec_sha256": digest(json_bytes(frozen)),
              "source_purpose_allows_support": training_allowed,
              "composition_support_eligible": False, "member_projections": {},
              "reason": "Complete trusted work and a verified fixed delivery chain are required",
              "scope": "Observed delivery route only; no causal value, unique code authorship or knowledge/understanding inference."}
    members = evidence.get("members", {})
    if set(members) != set(rollout["members"]):
        raise ValueError("Method member projection differs from actual stable member identities")
    for member, view in members.items():
        if view.get("member_id") != member or view.get("origin") != rollout["members"][member]["origin"]:
            raise ValueError("Method member projection identity changed")
        result["member_projections"][member] = {
            "member_id": member, "origin": view["origin"],
            "own_action_count": view["own_action_count"], "own_action_tokens": view["own_action_tokens"],
            "complete_actor_trajectory": view["complete_actor_trajectory"],
            "own_targets_sha256": view["own_targets_sha256"],
            "base_actor_targets_unchanged": True, "class_id": None, "support_eligible": False,
            "scope": "Own actual model targets only; no colleague output or background trace added. No author/causal-contribution filter."}
    if rollout.get("work_validity", {}).get("value") is not True:
        result["reason"] = "Complete validity is false or unknown; retain original base material"
        return result
    chain = evidence.get("delivery_chain", {})
    if not evidence.get("actual_visibility_complete") or not chain.get("verified"):
        result["reason"] = "Actual selected-input binding or fixed-delivery ancestry is incomplete"
        return result
    if not chain.get("current_test_feedback_seen_before_submit"):
        result["reason"] = "No actual selected input proves receipt of the tested delivery-version feedback"
        return result
    imports = chain.get("peer_integrations", [])
    if imports:
        if not all(item.get("qualifying_fixed_product_consumption") is True for item in imports):
            result["reason"] = "Conflict, missing visible receipt or uncertain/overwritten peer production content"
            return result
        category = "peer_fixed_product_delivery"
    elif chain.get("peer_fixed_content_acquisitions"):
        result["reason"] = "Peer fixed source was acquired without a verified retained import chain; manual borrowing stays unmapped"
        return result
    elif chain.get("unresolved_peer_dependencies"):
        result["reason"] = "Declared peer product dependencies lack a verified actual ancestry"
        return result
    elif not chain.get("retained_own_production_edit_paths"):
        result["reason"] = "No retained own production work is proved for a delivery with no peer product chain"
        return result
    else:
        category = "own_tree_delivery"
    result.update(status="mapped", class_id=category,
                  reason="Complete valid work with the frozen observable fixed-product route",
                  composition_support_eligible=training_allowed)
    for member, projection in result["member_projections"].items():
        view = members[member]
        projection["class_id"] = category
        projection["support_eligible"] = bool(training_allowed and view["origin"] == "target_model"
            and view["complete_actor_trajectory"] and view["own_action_count"] > 0
            and view["own_action_tokens"] > 0 and view["actual_input_bindings_complete"])
    return result
