"""Requirement replacement and explicit current applicability of historical work."""

from .core.work import (
    blocked_terminal,
    current_id,
    current_item,
    current_work_items,
)
from .domains.operating_toy import revise_basis
from .policies.organization import position

__all__ = [
    "blocked_terminal",
    "current_id",
    "current_item",
    "current_work_items",
    "revise_basis",
    "schedule_interruptions",
    "apply_lifecycle_event",
    "validate_lifecycle_policies",
]


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
        if action_record["actor_id"] != trigger.get(
            "actor_id", position(world.state, "worker")
        ) or not action_record["output"].get("ok"):
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
