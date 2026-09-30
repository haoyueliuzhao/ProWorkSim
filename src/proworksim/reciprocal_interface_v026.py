"""Explicit C1 communication intervention inside the existing command boundary.

Normal business artifacts and review tools are shared by both conditions. The
single-pass arm permits one original demand packet, not arbitrary extra prose.
It does not claim that artifact-mediated information flow is restricted to one edge.
"""

import copy

from .core.world import object_identity
from .tool_outcomes import ToolRejection

NORMAL = "work-interface-v0.26-normal"
SINGLE = "work-interface-v0.26-single-pass"
PREFIXES = {NORMAL, SINGLE}
ROLES = {"maintainer", "consumer"}
BUSINESS = (
    "read_alias",
    "read_version",
    "read_messages",
    "adopt",
    "adopt_version",
    "write_object",
    "sql_build",
    "sql_query",
    "preflight_submission",
    "submit",
    "withdraw",
    "inspect_submission",
    "raise_issue",
    "respond_issue",
    "decide_issue",
    "approve",
    "wait",
)
COMMUNICATION = ("request_information", "handoff_information")
SINGLE_PACKET_BODY = "Original demand document."


def definitions(core, profile):
    from .work_interface import DESCRIPTIONS, REFERENCE

    prefix, _, role = profile.partition(":")
    if prefix not in PREFIXES or role not in ROLES:
        raise ValueError("Unknown reciprocal interface profile")
    indexed = {d["name"]: d for d in core}
    result = []
    for name in (*BUSINESS, *COMMUNICATION):
        if name not in indexed:
            continue
        definition = copy.deepcopy(indexed[name])
        definition["description"] = DESCRIPTIONS[name]
        parameters = definition["parameters"]
        props = parameters["properties"]
        for key, value in props.items():
            value.pop("description", None)
            if value.get("type") == "string":
                value["minLength"] = 1
            if key == "reference":
                props[key] = copy.deepcopy(REFERENCE)
            elif key in {"dependencies", "evidence"}:
                value["items"] = copy.deepcopy(REFERENCE)
            elif key in {"artifacts", "work_ids", "input_aliases"}:
                value["items"] = {"type": "string", "minLength": 1}
                value["minItems"] = 1
            elif key == "locator":
                value["items"] = {"type": ["string", "integer"]}
                value["minItems"] = 1
        if name == "write_object":
            props.pop("object_id", None)
            if "alias" not in parameters["required"]:
                parameters["required"].append("alias")
        if name == "adopt_version" and "work_id" not in parameters["required"]:
            parameters["required"].append("work_id")
        if name == "adopt":
            props["policy"]["enum"] = ["fixed", "current_applicable", "current_published"]
        if name == "handoff_information":
            props["status"]["enum"] = ["delivered", "unavailable"]
            if prefix == SINGLE:
                props["body"] = {"type": "string", "const": SINGLE_PACKET_BODY}
                definition["description"] = (
                    "Single-pass diagnostic: consumer may once hand off the exact original demand v1 through its declared route, after actually reading it. Set body exactly to Original demand document. No custom explanation or reply. Maintainer sends no extra packet. Managed product reading, SQL, submissions and formal reviews remain available."
                )
            else:
                definition["description"] += (
                    " Your observation includes reply_options with exact scope fields for each pending addressed request. Copy the chosen request fields and supply evidence you chose; writing a body alone does not close a request."
                )
        if name == "request_information" and prefix == SINGLE:
            definition["description"] = (
                "Additional explanatory requests are disabled in this single-pass diagnostic; use unchanged business tools and the one original demand packet."
            )
        result.append(definition)
    return result


def guard(state, actor, project_id, profile, action, arguments):
    """No writes; rejected attempts become ordinary trusted command refusals."""
    prefix, _, role = profile.partition(":")
    if prefix not in PREFIXES:
        return
    if state is None or role != actor:
        raise ValueError("A reciprocal interface must be bound to its actual world role")
    if prefix == NORMAL or action not in COMMUNICATION:
        return
    if action != "handoff_information":
        raise ToolRejection(
            "Single-pass condition permits only the one original demand packet; extra information requests are not available.",
            code="single_pass_communication",
            category="policy_error",
        )
    routes = state["projects"][project_id].get("information_routes", [])
    route = next((r for r in routes if r["route_id"] == arguments.get("route_id")), None)
    original = {"object_id": object_identity(project_id, "demand"), "version_id": "v1"}
    already_sent = any(
        h.get("project_id") == project_id and h.get("origin") == "member_action"
        for h in state.get("handoffs", {}).values()
    )
    if (
        actor != "consumer"
        or not route
        or route.get("object_alias") != "demand"
        or route.get("provider") != actor
        or arguments.get("reference") != original
        or arguments.get("body") != SINGLE_PACKET_BODY
        or arguments.get("request_id") is not None
        or arguments.get("status", "delivered") != "delivered"
        or already_sent
    ):
        raise ToolRejection(
            "Only one original demand v1 packet from consumer is allowed; only the fixed Original demand document. header, no extra explanation, requests or repeat. Business artifacts and formal review remain unchanged.",
            code="single_pass_communication",
            category="policy_error",
        )


def observation_notes(observation, profile):
    prefix, _, role = profile.partition(":")
    observation["communication_contract"] = {
        "condition": "normal" if prefix == NORMAL else "single_pass",
        "scope": "Only extra explanatory request/handoff channels vary. Normal managed artifact/version access, SQL, adoption, submission and formal review remain available; they can themselves convey information.",
        "single_pass_limit": None
        if prefix == NORMAL
        else "One original demand v1 packet, consumer to maintainer, fixed body Original demand document. and no custom explanation. No other explanatory requests or handoffs.",
        "no_minimum_turns": True,
    }
    # These fields were already visible in the real public condition/route view.
    # This table selects no evidence and performs no reply, adoption or work.
    options = []
    for condition in observation.get("conditions", {}).values():
        if role not in condition.get("providers", []) or not condition.get("request_id"):
            continue
        route = next(
            (
                r
                for r in observation.get("information_routes", [])
                if r.get("work_id") == condition.get("work_item_id")
                and r.get("provider") == role
                and r.get("purpose") == condition.get("purpose")
            ),
            None,
        )
        if route and condition.get("status") in {"open", "unavailable"}:
            options.append(
                {
                    "request_id": condition["request_id"],
                    "work_id": condition["work_item_id"],
                    "route_id": route["route_id"],
                }
            )
    observation["reply_options"] = options
    return observation
