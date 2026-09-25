"""Observed information relations and a small predeclared joint-method mapper.

This is not a causal graph or a semantic parser of private reasoning. Relations
are tied to actual IDs, version references, tool results and receipt events.
"""

import copy

from .storage import digest, json_bytes

GRAPH_VERSION = "information-graph-v0.12"
MAPPER_VERSION = "handoff-mapper-v0.12"


def _reference(value):
    if not isinstance(value, dict):
        return None
    oid, vid = value.get("object_id", value.get("artifact_id")), value.get("version_id")
    return (oid, vid) if isinstance(oid, str) and isinstance(vid, str) else None


def information_graph(rollout):
    nodes, edges, handoffs, requests, diagnostics = {}, [], {}, {}, []
    actual_messages, actual_requests = {}, {}

    def edge(source, target, kind, evidence):
        if source not in nodes or target not in nodes:
            raise ValueError("Observed graph edge requires both recorded endpoints")
        row = {"source": source, "target": target, "kind": kind, "evidence": evidence}
        if row not in edges:
            edges.append(row)

    def version(ref):
        key = "version:" + digest(json_bytes(list(ref)))[:24]
        nodes.setdefault(
            key,
            {"node_id": key, "kind": "evidence_version", "object_id": ref[0], "version_id": ref[1]},
        )
        return key

    for event in rollout["events"]:
        kind, payload = event["kind"], event["payload"]
        node_id = "event:" + str(event["sequence"])
        if kind == "tool_call":
            member_id = event.get("worker_id")
            if member_id not in rollout["members"]:
                continue
            member = rollout["members"][member_id]
            response = payload.get("response", {})
            nodes[node_id] = {
                "node_id": node_id,
                "kind": "actual_action",
                "sequence": event["sequence"],
                "member_id": member_id,
                "actor_id": member["actor_id"],
                "origin": member["origin"],
                "action": payload["action"],
                "ok": response.get("ok"),
                "model_call_id": payload.get("model_call_id"),
                "command_id": response.get("command_id"),
            }
            if response.get("ok") is not True:
                continue
            arguments, result = payload.get("arguments", {}), response.get("result", {})
            if not isinstance(result, dict):
                continue
            if payload["action"] == "request_information" and result.get("request_id"):
                request_id = result["request_id"]
                requests[request_id] = node_id
                nodes[node_id].update(
                    request_id=request_id,
                    route_id=arguments.get("route_id"),
                    work_id=arguments.get("work_id"),
                )
            if payload["action"] == "handoff_information":
                handoff_id = result.get("handoff_id")
                if not isinstance(handoff_id, str):
                    diagnostics.append(
                        {
                            "sequence": event["sequence"],
                            "reason": "successful_handoff_identity_missing",
                        }
                    )
                    continue
                if handoff_id in handoffs and result.get("created") is False:
                    nodes[node_id].update(kind="handoff_repeat", handoff_id=handoff_id)
                    edge(
                        handoffs[handoff_id],
                        node_id,
                        "idempotent_repeat",
                        {"handoff_id": handoff_id},
                    )
                    continue
                nodes[node_id].update(
                    kind="member_handoff",
                    handoff_id=handoff_id,
                    route_id=arguments.get("route_id"),
                    work_id=arguments.get("work_id"),
                    request_id=arguments.get("request_id"),
                    status=arguments.get("status", "delivered"),
                )
                handoffs[handoff_id] = node_id
                request_id = arguments.get("request_id")
                if request_id is not None:
                    if request_id in requests:
                        edge(
                            requests[request_id], node_id, "responds_to", {"request_id": request_id}
                        )
                    else:
                        diagnostics.append(
                            {
                                "sequence": event["sequence"],
                                "reason": "request_outside_observed_window",
                                "request_id": request_id,
                            }
                        )
                ref = _reference(arguments.get("reference"))
                if ref:
                    edge(
                        version(ref),
                        node_id,
                        "chosen_evidence",
                        {"strength": "actual_tool_argument"},
                    )
            ref = _reference(result.get("reference"))
            if ref:
                relation = (
                    "observes_version" if payload["action"] == "read_object" else "produces_version"
                )
                edge(version(ref), node_id, relation, {"strength": "actual_tool_result"})
            if payload["action"] in {"adopt", "adopt_version"}:
                ref = _reference(arguments)
                if ref:
                    edge(
                        version(ref),
                        node_id,
                        "adopts_version",
                        {
                            "work_id": arguments.get("work_id"),
                            "work_ids": arguments.get("work_ids"),
                        },
                    )
            for ref in arguments.get("dependencies", []):
                value = _reference(ref)
                if value:
                    edge(
                        version(value),
                        node_id,
                        "declares_dependency",
                        {"strength": "declared_dependency_not_proven_cause"},
                    )
        elif kind == "model_tool_result":
            nodes[node_id] = {
                "node_id": node_id,
                "kind": "public_tool_result",
                "sequence": event["sequence"],
                "member_id": event.get("worker_id"),
                "call_id": payload.get("call_id"),
                "message_sha256": digest(json_bytes(payload["message"])),
            }
            actual_messages[node_id] = payload["message"]
        elif (
            kind == "model_attempt"
            and payload.get("stage") == "finished"
            and payload.get("status") == "success"
        ):
            nodes[node_id] = {
                "node_id": node_id,
                "kind": "actual_actor_input",
                "sequence": event["sequence"],
                "member_id": event.get("worker_id"),
                "call_id": payload.get("call_id"),
                "request_sha256": digest(json_bytes(payload["request"])),
                "context_selection": copy.deepcopy(payload.get("context_selection")),
            }
            actual_requests[node_id] = payload["request"]
        elif kind == "environment_event":
            details = payload.get("payload", payload)
            if not isinstance(details, dict):
                continue
            handoff_id = details.get("handoff_id", details.get("originating_handoff_id"))
            if handoff_id is None:
                continue
            nodes[node_id] = {
                "node_id": node_id,
                "kind": "delivery_event",
                "sequence": event["sequence"],
                "handoff_id": handoff_id,
                "origin": details.get("origin"),
                "sender": details.get("sender"),
                "recipients": copy.deepcopy(details.get("recipients", [])),
                "event_id": payload.get("event_id"),
                "reference": copy.deepcopy(details.get("reference")),
                "outcome": payload.get("outcome"),
            }
            if (
                handoff_id in handoffs
                and details.get("origin") == "member_action"
                and payload.get("outcome") == "applied"
            ):
                edge(handoffs[handoff_id], node_id, "delivered", {"handoff_id": handoff_id})
            else:
                diagnostics.append(
                    {
                        "sequence": event["sequence"],
                        "reason": "delivery_without_observed_member_action",
                        "origin": details.get("origin"),
                    }
                )
    # Compare actual message objects with the exact HTTP request. Saved memory
    # and dropped observations do not establish actor presentation.
    for message_id, message in actual_messages.items():
        returned = nodes[message_id]
        for request_id, request in actual_requests.items():
            incoming = nodes[request_id]
            if (
                returned["member_id"] == incoming["member_id"]
                and returned["sequence"] < incoming["sequence"]
                and message in request.get("messages", [])
            ):
                edge(
                    message_id,
                    request_id,
                    "presented_in_actual_input",
                    {"strength": "exact_actual_message_match"},
                )
        for action in list(nodes.values()):
            if (
                action.get("model_call_id") == returned["call_id"]
                and action.get("member_id") == returned["member_id"]
                and action.get("sequence", -1) < returned["sequence"]
            ):
                edge(
                    action["node_id"],
                    message_id,
                    "returned_to_member",
                    {"model_call_id": returned["call_id"]},
                )
    # Explicit model-call identities connect actual inputs to that member's
    # actual world action; no cross-member output is relabeled as generated text.
    for action in list(nodes.values()):
        if action.get("model_call_id"):
            for observed in list(nodes.values()):
                if (
                    observed["kind"] == "actual_actor_input"
                    and observed.get("call_id") == action["model_call_id"]
                    and observed.get("member_id") == action.get("member_id")
                ):
                    edge(
                        observed["node_id"],
                        action["node_id"],
                        "actual_input_for",
                        {"model_call_id": action["model_call_id"]},
                    )
    # Only record observed temporal/reference linkage, not a causal necessity.
    for delivery in list(nodes.values()):
        if delivery["kind"] != "delivery_event":
            continue
        delivered_ref = _reference(delivery.get("reference"))
        for observed_edge in list(edges):
            action = nodes[observed_edge["target"]]
            ref_node = nodes[observed_edge["source"]]
            if (
                observed_edge["kind"] == "observes_version"
                and delivered_ref
                and (ref_node.get("object_id"), ref_node.get("version_id")) == delivered_ref
                and action.get("actor_id") in delivery.get("recipients", [])
                and action.get("sequence", -1) > delivery["sequence"]
            ):
                edge(
                    delivery["node_id"],
                    action["node_id"],
                    "delivery_before_matching_access",
                    {"strength": "observed_not_causal"},
                )
    return {
        "version": GRAPH_VERSION,
        "rollout_id": rollout["rollout_id"],
        "nodes": list(nodes.values()),
        "edges": edges,
        "diagnostics": diagnostics,
        "scope": "Observed execution/reference relations only, not an identified causal graph. A delivery is not proof of later actor presentation or use.",
    }


def map_joint_method(graph, *, route_id, spec_id):
    """Two classes for one frozen semantic route; neither prompts nor rewards used.

    Text, random object IDs and wall time do not define the class. Direction,
    actual request relation and committed member-to-delivery linkage do.
    """
    if not isinstance(route_id, str) or not route_id or not spec_id:
        raise ValueError("Mapper route and equivalence specification must be predeclared")
    handoffs = [
        node
        for node in graph["nodes"]
        if node["kind"] == "member_handoff"
        and node.get("route_id") == route_id
        and node.get("status") == "delivered"
    ]
    result = {
        "version": MAPPER_VERSION,
        "rollout_id": graph["rollout_id"],
        "spec_id": spec_id,
        "route_id": route_id,
        "status": "unmapped",
        "class_id": None,
        "evidence": [],
        "reason": "No unique observed successful member handoff",
    }
    if len(handoffs) != 1:
        if len(handoffs) > 1:
            result.update(
                status="ambiguous", reason="Multiple handoffs need a richer predeclared mapper"
            )
        return result
    handoff = handoffs[0]
    delivered = [
        edge
        for edge in graph["edges"]
        if edge["source"] == handoff["node_id"] and edge["kind"] == "delivered"
    ]
    chosen = [
        edge
        for edge in graph["edges"]
        if edge["target"] == handoff["node_id"] and edge["kind"] == "chosen_evidence"
    ]
    if not delivered or not chosen:
        result["reason"] = "No actual delivery or exact chosen evidence is observable"
        return result
    requested = handoff.get("request_id") is not None
    response_edges = [
        edge
        for edge in graph["edges"]
        if edge["target"] == handoff["node_id"] and edge["kind"] == "responds_to"
    ]
    if requested and not response_edges:
        result["reason"] = "Requested handoff has no observed request identity"
        return result
    result.update(
        status="mapped",
        class_id="requested_handoff" if requested else "proactive_handoff",
        evidence=[handoff["node_id"], *[edge["target"] for edge in delivered]],
        reason="Frozen explicit handoff/request structure; validity and member support are separate gates",
    )
    return result
