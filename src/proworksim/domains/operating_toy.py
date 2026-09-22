"""The synthetic operating-analysis domain; no professional-realism claim.

Stage-wide approval changes are explicit domain policy because work in a stage
shares one analysis artifact. Generic requirement replacement remains target-local.
"""

from ..basis import issue_basis, read_basis
from ..core.work import current_id, current_work_items, revise_requirement
from ..policies.organization import position, require_authority
from ..storage import json_bytes


def revise_basis(world, targets, growth_delta, reason, actor=None):
    state = world.state
    actor = actor or position(state, "coordinator")
    if not targets or any(
        current_id(state, target) not in state["work_items"] for target in targets
    ):
        raise ValueError("Revision requires existing current work")
    requested = [state["work_items"][current_id(state, target)] for target in targets]
    stages = {
        (w.get("scenario_revision", 1), w.get("source_stage"), w.get("source_version"))
        for w in requested
    }
    if len(stages) != 1:
        raise ValueError("One approval revision cannot span analytical stages")
    stage = next(iter(stages))
    items = [
        w
        for w in current_work_items(state)
        if (w.get("scenario_revision", 1), w.get("source_stage"), w.get("source_version")) == stage
    ]
    selected = {w["work_item_id"] for w in items}
    if any(
        w["work_item_id"] not in selected
        and any(current_id(state, d) in selected for d in w["dependencies"])
        for w in current_work_items(state)
    ):
        raise ValueError("A successor stage is already active; revise that current stage instead")
    if not isinstance(growth_delta, (int, float)) or isinstance(growth_delta, bool):
        raise ValueError("growth_delta must be numeric")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A concrete revision reason is required")
    items = sorted(items, key=lambda item: item["work_item_id"])
    for item in items:
        require_authority(
            state,
            actor,
            "revise_requirement",
            "analytical_assumptions",
            work_node=item.get("node_id", item["work_item_id"]),
        )
    revision = max(w["requirement_version"] for w in items) + 1
    if any(
        f"{w.get('node_id', w['work_item_id'])}@r{revision}" in state["work_items"] for w in items
    ):
        raise ValueError("Requirement revision already exists")
    old_ref = next((w.get("required_basis") for w in items if w.get("required_basis")), None)
    if old_ref is None:
        raise ValueError("Cannot revise an unavailable approval")
    old_basis = read_basis(world.store, state, old_ref["version_id"])
    assumptions = {
        **old_basis["assumptions"],
        "growth": round(old_basis["assumptions"]["growth"] + growth_delta, 8),
    }
    affected_nodes = {w.get("node_id", w["work_item_id"]) for w in items}
    # Include not-yet-activated downstream work in the same analytical stage.
    for node in state["workflow"]["nodes"]:
        if node["scenario_revision"] == items[0].get("scenario_revision", 1):
            affected_nodes.add(node["node_id"])
    basis = issue_basis(
        world.store,
        state,
        assumptions,
        old_basis["period"],
        revision,
        sorted(affected_nodes),
        items[0].get("scenario_revision", 1),
        public=state["project"]["information_access"] == "mail",
        confirmer=actor,
    )
    world.store.put(
        state,
        "scope",
        json_bytes(
            {
                "requirement_version": revision,
                "assumptions": assumptions,
                "source_period": old_basis["period"],
                "approved_basis": {"artifact_id": "basis", "version_id": basis["version_id"]},
            }
        ),
        actor,
    )
    basis_ref = {"artifact_id": "basis", "version_id": basis["version_id"]}
    replacements = revise_requirement(
        state,
        [item["work_item_id"] for item in items],
        {"required_credentials": [basis_ref], "requirement_dimension": "analytical_assumptions"},
        actor,
        reason,
    )
    for new_id in replacements.values():
        item = state["work_items"][new_id]
        # These fields are the operating template's adapter representation.
        item["basis_requirement_version"] = revision
        item["required_basis"] = dict(basis_ref)
        item["visible_requirements"].append(
            f"需求已修订：适用批准依据为 basis/{basis['version_id']}，请核验并修订实际产物。"
        )
    # Previously queued completion events must await the replacement approval.
    cancelled_rules = {
        r["rule_id"]
        for r in state["workflow"]["event_rules"]
        if any(node in affected_nodes for node in r["after_accepted"])
    }
    state["events"] = [
        event
        for event in state["events"]
        if not (event["kind"] == "apply_rule" and event["payload"]["rule_id"] in cancelled_rules)
    ]
    state["fired_rules"] = [rule for rule in state["fired_rules"] if rule not in cancelled_rules]
    world._message(
        actor,
        [position(state, "worker"), position(state, "reviewer")],
        "执行中需求修订",
        {
            "reason": reason,
            "replacements": replacements,
            "requirement_version": revision,
            "basis_ref": {"artifact_id": "basis", "version_id": basis["version_id"]},
            "assumptions_visible": state["project"]["information_access"] == "mail",
        },
        [{"artifact_id": "basis", "version_id": basis["version_id"]}]
        if state["project"]["information_access"] == "mail"
        else [],
    )
    world._staff_record(
        actor,
        "revise_requirements",
        {"targets": targets, "reason": reason},
        {"replacements": replacements, "basis_version": basis["version_id"]},
    )
    # Approval issuance precedes replacement creation; assess the final work scope.
    from ..freshness import refresh_freshness

    refresh_freshness(state)
    return replacements
