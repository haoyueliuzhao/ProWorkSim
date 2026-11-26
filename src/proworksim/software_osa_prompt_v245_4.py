"""Receipt-scoped decision prompt for full-task OSA, with the existing controller."""

import json

from . import software_event_orders_v243 as event
from .software_fair_delivery_v245 import Execution as FairExecution
from .software_fixed_organization_clone_v131 import clone_function

VERSION = "v245.4"
GUIDE = """You allocate work between two workers. Use only the public facts in project_graph. A delivery checklist shows what is currently owed; by itself it cannot establish repeated failure or stalled progress.

1. What would stall if the current owner continued? Cite the receipt IDs in basis. Classify repeated failure on the same target (A1), a dependency blockage (A2), an integration conflict (A3), a verification gap (A4), or repeated readiness without delivery (A5). Use STABLE for evidenced progress and UNKNOWN when the facts do not distinguish these cases.
2. Compare KEEP with the routes actually listed. For a change, name who will produce what, for whom, and why it addresses the observed gap. The actor takes the first action; the assignee may produce the added product later. A pending ordinary edit alone gives no reason to move it. An optional review can add value for a specific risk. Assigning a verifier does not certify a review. Explain the trade-off in reason and name one observable event in reconsider_after that would change the choice.
3. Read the dimensions as effects on work. D0 fixes team membership at two. D1 changes a role (e.g. a partner diagnoses a specific failure and returns evidence). D2 transfers an unstarted package to a new owner. D3 records how members cooperate. D4 coordinates a handoff across packages. D5 assigns independent verification. D6 coordinates integration and regression checking. D7 allocates execution opportunities. Collaboration links and reserved turns can accompany a choice. If diagnosis, handoff, or conflict resolution is absent from the menu, report what evidence would warrant reconsideration; do not invent a route. Only IDs in routes and optional_execution_orders can be selected; a dimension label is never a route.
4. Choose one route. Use work_order=none for the route alone, or abstain with an unchanged allocation to defer. A listed order must use one of its compatible_routes and cite its evidence. For current_obligations, list only evidenced outcomes still owed in the selected package, including blocked ones; use [] if none. An inspection is a first action, and is an obligation only if its result is itself owed. UNKNOWN means evidence is missing; NOT_REQUIRED means the current contract waives the review. Neither certifies completed work. Copy both statuses of probed_obligation verbatim. Submit exactly one activate_organization tool call."""


def include_review_contract(receipt, view):
    """Carry the public checklist flag through the legacy evidence projection."""
    packages = {item["task_id"]: item for item in view.get("package_chain", {}).get("packages", [])}
    for item in receipt.get("packages", []):
        flag = packages.get(item["task_id"], {}).get("independent_review_required")
        if isinstance(flag, bool):
            item["independent_review_required"] = flag
    return receipt


def wire(row, choices):
    request = event.wire(row, choices)
    data = json.loads(request["messages"][-1]["content"])
    data["prompt_version"] = VERSION
    routes = data["routes"]
    available = {r["option"] if r["option"] != "WAIT" else "K" for r in routes.values()}
    data["patches"] = {k: v for k, v in data["patches"].items() if k in available}
    for route in routes.values():
        option = row["options"].get(route["option"], {})
        if "assignee" in option:
            route["assignee"] = option["assignee"]

    orders = {}
    for key, order in choices.items():
        compatible = [
            k
            for k, r in routes.items()
            if r["option"] in {"K", "WAIT"} and r["package"] == order["task"]
        ]
        if compatible and order["evidence"] in row["evidence"]:
            orders[key] = {**order, "compatible_routes": compatible}
    data["optional_execution_orders"] = orders

    nodes = data["obligation_graph"]
    constraints = data["organization_graph"]["constraints"]
    constraints.pop("independent_review", None)
    policy = {}
    for node in nodes.values():
        if node["label"] != "independent_review":
            continue
        package = node["package"]
        current = next(
            (
                p
                for eid in reversed(node["evidence"])
                for p in row["evidence"][eid].get("packages", [])
                if p["task_id"] == package and row["evidence"][eid].get("accepted")
            ),
            {},
        )
        required = current.get("independent_review_required")
        policy[package] = {True: "required", False: "optional"}.get(required, "unknown")
        if required is False:
            node.update(
                completion="NOT_REQUIRED",
                readiness="NOT_APPLICABLE",
                completion_evidence="Checklist waives review; no verdict inferred.",
                source="current_delivery_checklist",
            )
        elif node["completion"] == "SATISFIED" and required is not True:
            node.update(
                completion="UNKNOWN",
                readiness="CONDITIONAL",
                completion_evidence="No current review verdict established.",
                source="review_requirement_unknown",
            )
    constraints["review_by_package"] = policy
    for node in nodes.values():
        prerequisites = []
        for key in node["requires"]:
            parent = nodes.get(key, {})
            prerequisites.extend(
                parent["requires"] if parent.get("completion") == "NOT_REQUIRED" else [key]
            )
        node["requires"] = list(dict.fromkeys(prerequisites))

    fields = request["tools"][0]["function"]["parameters"]["properties"]
    pending = [k for k, n in nodes.items() if n["completion"] in {"UNSATISFIED", "STALE"}]
    for key in ("probe_completion", "probe_readiness"):
        fields[key]["enum"] = list(fields[key]["enum"])
    if nodes[data["probed_obligation"]]["completion"] == "NOT_REQUIRED":
        fields["probe_completion"]["enum"].append("NOT_REQUIRED")
    fields["work_order"]["enum"] = ["none", "abstain", *orders]
    fields["current_obligations"] = {"type": "array", "uniqueItems": True}
    if pending:
        fields["current_obligations"]["items"] = {"type": "string", "enum": pending}
    else:
        fields["current_obligations"]["maxItems"] = 0
    request["messages"][0]["content"] = GUIDE
    request["messages"][-1]["content"] = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return request


class Execution(FairExecution):
    decide = clone_function(
        event.Execution.decide, {**event.Execution.decide.__globals__, "wire": wire}
    )
