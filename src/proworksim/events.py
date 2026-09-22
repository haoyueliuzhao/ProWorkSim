"""Allowlisted domain event effects; generated specifications cannot execute code."""

import json

from .compiler import disclosure, scope
from .storage import json_bytes, read_json
from .workflow import activate_ready, configure


def apply_rule(world, event):
    state = world.state
    spec = read_json(world.store.control / "spec.json")
    if "workflow" not in state:
        configure(state, spec)
    rule_id = event["payload"].get("rule_id", "next-release")
    rule = next(r for r in state["workflow"]["event_rules"] if r["rule_id"] == rule_id)
    allowed = {"publish_disclosure", "publish_scope", "revise_brief"}
    if any(effect["kind"] not in allowed for effect in rule["effects"]):
        raise ValueError("Unsupported event effect")
    # Guard again at application time; activation is based on committed business state.
    if not all(
        state["work_items"].get(node, {}).get("status") == "accepted"
        for node in rule["after_accepted"]
    ):
        raise ValueError("Event preconditions are not satisfied")
    for effect in rule["effects"]:
        if effect["kind"] == "publish_disclosure":
            aid, actor = "financials", "client"
            body = disclosure(spec, effect["stage"], state["clock"])
        elif effect["kind"] == "publish_scope":
            aid, actor = "scope", "manager"
            body = scope(spec, effect["revision"])
        else:
            aid, actor = "brief", "client"
            body = json.loads(world.store.content(state["artifacts"][aid]))
            body["audience"] = effect["audience"]
        before = state["artifacts"][aid]["current_version"]
        version = world.store.put(state, aid, json_bytes(body), actor)
        world._staff_record(
            actor,
            effect["kind"],
            effect,
            {"artifact_id": aid, "version_id": version["version_id"]},
            writes=[{"artifact_id": aid, "before": before, "after": version["version_id"]}],
        )
        if aid != "scope":
            world._message(
                actor,
                ["analyst", "manager", "reviewer"],
                "项目材料变更",
                {"artifact_id": aid, "release": rule["release"]},
                [{"artifact_id": aid, "version_id": version["version_id"]}],
            )
        elif state["project"]["information_access"] == "mail":
            world._message("manager", ["analyst", "reviewer"], "已确认的新版 scope", body)
    state["released_groups"].append(rule["release"])
    activate_ready(state, spec, event["event_id"])
