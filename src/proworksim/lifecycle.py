"""Requirement replacement and explicit current applicability of historical work."""

import copy

from .basis import issue_basis, read_basis
from .storage import json_bytes

INACTIVE = {"superseded", "cancelled"}


def current_id(state, work_id):
    seen = set()
    while work_id in state.get("work_replacements", {}):
        if work_id in seen:
            raise ValueError("Cyclic work replacement")
        seen.add(work_id)
        work_id = state["work_replacements"][work_id]
    return work_id


def current_item(state, work_id):
    return state["work_items"].get(current_id(state, work_id))


def current_work_items(state):
    return [
        item
        for key, item in state["work_items"].items()
        if current_id(state, key) == key and item["status"] not in INACTIVE
    ]


def blocked_terminal(state):
    active = [w for w in current_work_items(state) if w["status"] != "accepted"]
    return (
        bool(active)
        and not state["events"]
        and all(
            w["status"] == "blocked"
            and any(
                state.get("blockers", {}).get(bid, {}).get("status") == "unavailable"
                for bid in w.get("blocker_ids", [])
            )
            for w in active
        )
    )


def schedule_interruptions(world, action_record):
    for policy in world.state.get("lifecycle_events", []):
        if policy["event_id"] in world.state.setdefault("triggered_lifecycle_events", []):
            continue
        trigger = policy["trigger"]
        if any(
            current_id(world.state, target) not in world.state["work_items"]
            for target in policy["effect"]["targets"]
        ):
            continue
        if action_record["actor_id"] != trigger.get("actor_id", "analyst") or not action_record[
            "output"
        ].get("ok"):
            continue
        if action_record["action"] != trigger["action"]:
            continue
        if trigger.get("work_item_id") and current_id(
            world.state, action_record["inputs"].get("work_item_id")
        ) != current_id(world.state, trigger["work_item_id"]):
            continue
        if trigger.get("topic") and action_record["inputs"].get("topic") != trigger["topic"]:
            continue
        world.state["triggered_lifecycle_events"].append(policy["event_id"])
        world._event("lifecycle_change", {"policy_id": policy["event_id"]}, policy.get("delay", 0))


def revise_basis(world, targets, growth_delta, reason):
    state = world.state
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
    old_ref = next((w.get("required_basis") for w in items if w.get("required_basis")), None)
    if old_ref is None:
        raise ValueError("Cannot revise an unavailable approval")
    old_basis = read_basis(world.store, state, old_ref["version_id"])
    revision = max(w["requirement_version"] for w in items) + 1
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
        "manager",
    )
    replacements = {}
    for old in items:
        old_id = old["work_item_id"]
        new_id = f"{old.get('node_id', old_id)}@r{revision}"
        if new_id in state["work_items"]:
            raise ValueError("Requirement revision already exists")
        new = copy.deepcopy(old)
        new.update(
            work_item_id=new_id,
            requirement_version=revision,
            basis_requirement_version=revision,
            status="open",
            submissions=[],
            blocker=None,
            blocker_ids=[],
            activated_at=state["clock"],
            applicability="current",
            origin_event=reason,
            required_basis={"artifact_id": "basis", "version_id": basis["version_id"]},
            supersedes=old_id,
        )
        state["work_items"][new_id] = new
        state.setdefault("work_replacements", {})[old_id] = new_id
        old["applicability"] = "superseded_requirements"
        old["superseded_by"] = new_id
        if old["status"] != "accepted":
            old["status"] = "superseded"
        for sub in old["submissions"]:
            sub["current_applicability"] = "superseded_requirements"
            if sub.get("review") is None:
                sub["invalidated"] = True
                sub["invalidation_reason"] = reason
        for blocker_id in old.get("blocker_ids", []):
            from .blockers import supersede_blocker

            if state["blockers"][blocker_id]["status"] in ("open", "unavailable"):
                supersede_blocker(state, blocker_id, reason, {"work_item_id": new_id})
        replacements[old_id] = new_id
    for new_id in replacements.values():
        item = state["work_items"][new_id]
        item["dependencies"] = [current_id(state, dep) for dep in item["dependencies"]]
        if any(state["work_items"][dep]["status"] != "accepted" for dep in item["dependencies"]):
            item["status"] = "waiting_dependencies"
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
        "manager",
        ["analyst", "reviewer"],
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
        "manager",
        "revise_requirements",
        {"targets": targets, "reason": reason},
        {"replacements": replacements, "basis_version": basis["version_id"]},
    )
    # Approval issuance precedes replacement creation; assess the final work scope.
    from .freshness import refresh_freshness

    refresh_freshness(state)
    return replacements


def apply_lifecycle_event(world, event):
    policy = next(
        p for p in world.state["lifecycle_events"] if p["event_id"] == event["payload"]["policy_id"]
    )
    effect = policy["effect"]
    if effect["kind"] != "revise_basis":
        raise ValueError("Unsupported lifecycle effect")
    return revise_basis(world, effect["targets"], effect["growth_delta"], policy["event_id"])


def validate_lifecycle_policies(policies, workflow):
    ids = {node["node_id"] for node in workflow["nodes"]}
    policy_ids = [policy["event_id"] for policy in policies]
    if len(set(policy_ids)) != len(policy_ids):
        raise ValueError("Lifecycle event IDs must be unique")
    for policy in policies:
        trigger, effect = policy["trigger"], policy["effect"]
        if trigger["action"] not in {"sheet_update", "write_file", "mail_send", "submit", "wait"}:
            raise ValueError("Unsupported lifecycle trigger")
        if trigger.get("work_item_id") is not None and trigger["work_item_id"] not in ids:
            raise ValueError("Unknown lifecycle trigger work")
        if (
            effect["kind"] != "revise_basis"
            or not effect["targets"]
            or not set(effect["targets"]) <= ids
        ):
            raise ValueError("Invalid lifecycle revision targets")
        if type(policy.get("delay", 0)) is not int or not 0 <= policy.get("delay", 0) <= 100:
            raise ValueError("Invalid lifecycle event delay")
