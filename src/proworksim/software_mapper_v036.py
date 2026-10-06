"""Frozen v036 product-route representation; never a causal-credit label."""
from __future__ import annotations

import copy

from .storage import digest, json_bytes
from .team_rollout import optimizer_scope_allows_update, validate_window

MAPPER_VERSION = MAPPER = "software-evidenced-product-route-v0.36"
CLASS_ORDER = ("local_lineage_delivery", "evidenced_peer_product_delivery")
EVIDENCE_VERSION = "software-method-evidence-v0.36"


def mapping_spec():
    """This finite syntax/visibility rule is frozen before the new collection."""
    return {
        "version": MAPPER_VERSION, "spec_id": MAPPER, "class_order": list(CLASS_ORDER),
        "validity": "Keep original complete validity and exact tested/fixed/submitted version; do not regrade any archive.",
        "binding": "Exact rollout seal, manifest, stable member IDs, window/xi/Gamma/policy identity and v036 evidence/spec seal.",
        "local_lineage_delivery": "Verified final ancestry with retained own public-production edits and no final-chain peer import or unexplained peer fixed-source acquisition. This does not mean one person worked or that there was no cooperation.",
        "evidenced_peer_product_delivery": "At least one explained final-chain peer fixed-product consumption and no unexplained critical dependency. Every related import must have a known fixed source, verified version transition, actual metadata/receipt presentation and an explained consumed/discarded/nonproductive state; not every import must retain positive content.",
        "production_unit": "One declared top-level public function/class under normalized Python AST; comments, format and docstrings are ignored. The incoming unit must differ separately from the patch starter and the recipient immediately before import. Unrelated helpers and recipient-already-present/no-op production cannot create the peer class.",
        "retained_relation": "A complete normalized public unit is introduced by the real import or restored by a later same-path edit, then remains structurally equal through every later ancestor to final delivery. Other public units/files may be rewritten. Arbitrary within-unit semantic rewrites are not inferred equivalent.",
        "direct_merge": "A merged import may directly materialize a retained unit; source text need not be reread. Metadata must be visible by import, and its real receipt before the final current-version test.",
        "recovery": "A recovery edit must follow actual input containing the fixed metadata and import receipt plus a matching conflict diagnosis or relevant incoming production text. A later restoration after an already parseable replacement additionally needs a fresh relevant source-text presentation after that replacement. Information presented only after editing cannot justify the earlier transformation.",
        "discarded_import": "A nonretained productive import is explained as discarded only by a visible-receipt-following real reset to each recipient-before/starter public unit, with no later reappearance of the incoming unit. It can precede a later qualified import. A wholly overwritten sole peer import or arbitrary untraceable rewrite remains unmapped.",
        "dependencies": "Final declared public units must parse and be free of conflict markers. Retained units require statically resolved module bindings; changed/ambiguous local helpers, dynamic lookup and unresolved imported production symbols block that witness. Cross-production definition differences are recorded with verified version changes, never called semantic equivalence. Unknown included patches or peer-source acquisitions without a final-chain import block the route.",
        "orthogonal_attributes": ["direct_merge", "conflict_resolved", "partial_rewrite", "discarded_import", "nonproductive_import", "source_text_presented"],
        "information_boundary": "Materialized product, actual metadata/receipt, actual source fragments, and backend full execution are separate facts. No model thoughts, source authorship, necessity, semantic equivalence or positive learning value are inferred from normalized AST.",
        "member_projection": "Preserve all original own output targets, behavior records, masks and original joint-slot denominators. Stable members project the same joint route without a code-authorship filter.",
        "support_admission": "Only source-eligible new collection rollouts whose online_scope.method_mapper_spec_sha256 equals this frozen spec may supply composition support. Old windows can receive shadow labels only; they are never pooled into new support or P3.",
        "unmapped": "False/unknown validity, incomplete real input or ancestry, unseen test feedback, no positive witnessed unit, only discarded/nonproductive imports, unexplained dependencies, or unsupported dynamic/semantic transformations retain original base material but no method support.",
    }


def map_software_method(rollout, evidence, *, spec=None):
    frozen = mapping_spec()
    spec_sha = digest(json_bytes(frozen))
    if spec is not None and spec != frozen:
        raise ValueError("Mapper specification differs from the frozen v036 rule")
    if (evidence.get("version") != EVIDENCE_VERSION
            or evidence.get("mapper_spec_sha256") != spec_sha):
        raise ValueError("Method evidence does not bind the v036 rule")
    if (evidence.get("rollout_sha256") != digest(json_bytes(rollout))
            or evidence.get("rollout_id") != rollout.get("rollout_id")
            or evidence.get("manifest_sha256") != rollout.get("manifest_sha256")
            or evidence.get("window") != validate_window(rollout["window"])):
        raise ValueError("Method evidence belongs to another exact rollout/window")
    supplied = evidence.get("evidence_sha256")
    if supplied != digest(json_bytes({k: v for k, v in evidence.items() if k != "evidence_sha256"})):
        raise ValueError("Method evidence seal differs from its actual payload")
    source_allowed = optimizer_scope_allows_update(rollout)
    new_binding = rollout.get("online_scope", {}).get("method_mapper_spec_sha256") == spec_sha
    support_allowed = source_allowed and new_binding
    result = {"version": MAPPER_VERSION, "rollout_id": rollout["rollout_id"], "spec_id": MAPPER,
              "status": "unmapped", "class_id": None, "window": copy.deepcopy(rollout["window"]),
              "evidence_sha256": supplied, "mapper_spec_sha256": spec_sha,
              "source_purpose_allows_support": source_allowed,
              "collection_mapper_binding_matches": new_binding, "shadow_diagnostic_only": not new_binding,
              "composition_support_eligible": False, "member_projections": {},
              "reason": "Complete trusted work and an explained fixed delivery route are required",
              "process_attributes": copy.deepcopy(evidence.get("delivery_chain", {}).get("process_attributes", {})),
              "scope": "Observed finite product-route relation only; not causal value, unique authorship, independent completion or semantic equivalence."}
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
            "scope": "Own actual targets; all original members/base masks/denominators retained, without an authorship filter."}
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
    if (not chain.get("final_production_units_recognized") or not chain.get("final_conflict_free")
            or chain.get("unexplained_critical_dependencies") or chain.get("unresolved_peer_dependencies")):
        result["reason"] = "Final production or a critical peer dependency is not fully explained"
        return result
    imports = chain.get("peer_integrations", [])
    if imports:
        if any(item.get("explanation_complete") is not True
               or item.get("route_state") not in {"consumed", "discarded", "nonproductive"} for item in imports):
            result["reason"] = "Every relevant import must be explained, including discarded attempts"
            return result
        if not any(item.get("qualifying_fixed_product_consumption") is True
                   and item.get("route_state") == "consumed" and item.get("retained_production_units") for item in imports):
            result["reason"] = "Explained discarded/nonproductive imports alone do not prove a retained peer route"
            return result
        category = CLASS_ORDER[1]
    elif chain.get("peer_fixed_content_acquisitions"):
        result["reason"] = "Peer fixed source acquired without a verified final-chain import remains unmapped"
        return result
    elif not chain.get("retained_own_production_edit_paths"):
        result["reason"] = "No retained own public production work is proved"
        return result
    else:
        category = CLASS_ORDER[0]
    result.update(status="mapped", class_id=category,
                  reason="Complete valid work with a frozen evidenced v036 product route",
                  composition_support_eligible=support_allowed)
    for member, projection in result["member_projections"].items():
        view = members[member]
        projection["class_id"] = category
        projection["support_eligible"] = bool(support_allowed and view["origin"] == "target_model"
            and view["complete_actor_trajectory"] and view["own_action_count"] > 0
            and view["own_action_tokens"] > 0 and view["actual_input_bindings_complete"])
    return result
