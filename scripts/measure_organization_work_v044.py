"""Read-only lifecycle attribution supplement to the unchanged v040 work measure.

Only an original charged staff_done control (native or exact JSON), its actual
executor output, scheduled completion and committed self-retirement can close
the old retirement binding gap. A reason prefix or a terminal state alone is
never a model decision. No model, tokenizer, world action or acceptance runs.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_work_v040 as previous

base = previous.previous
VERSION = "organization-work-use-v0.44"
LIFECYCLE_VERSION = "original-staff-done-retirement-binding-v0.44"


class UnboundLifecycle(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise UnboundLifecycle(reason)


def one(rows, reason):
    require(len(rows) == 1, reason)
    return rows[0]


def source(path, pointer="/"):
    return {**base.pointer(path, pointer), "sha256": digest(path.read_bytes())}


def native_done(body):
    """Inspect the archived accepted output, never parse/generate a new action."""
    require(body.get("protocol_parse_error") is None, "original_native_output_was_rejected")
    choice = one(body.get("choices", []), "ambiguous_original_choice")
    message = choice.get("message", {})
    require(message.get("role") == "assistant", "original_output_not_assistant")
    tools = message.get("tool_calls", [])
    if tools:
        tool = one(tools, "not_single_original_tool_call")
        require(tool.get("type") == "function" and tool.get("function", {}).get("name") == "staff_done",
                "original_output_not_staff_done")
        arguments = json.loads(tool["function"]["arguments"])
        tool_id = tool.get("id")
        require(isinstance(tool_id, str) and bool(tool_id), "missing_original_tool_call_id")
        form = "native_staff_done"
    else:
        control = json.loads(message.get("content", ""))
        require(isinstance(control, dict) and set(control) == {"kind", "reason"}
                and control["kind"] == "done", "not_exact_original_done_control")
        arguments, tool_id, form = {"reason": control["reason"]}, None, "exact_json_done_control"
    require(isinstance(arguments, dict) and set(arguments) == {"reason"}
            and isinstance(arguments["reason"], str) and bool(arguments["reason"].strip()),
            "original_done_arguments_not_exact")
    return arguments, tool_id, form


def bind_retirement(event, *, state, result, evidence, budget, inputs, experience, opportunities, folder):
    """Return positive provenance only; missing, contradictory or external stays unknown."""
    member = event.get("actor_id")
    require(event.get("kind") == "member_retired" and event.get("member_id") == member,
            "not_self_retirement")
    require(base.actual_event(event) and event.get("origin") in {None, "model", "member_request"},
            "external_or_non_model_retirement")
    controls = [row for row in experience if row.get("kind") == "model_control"
                and row.get("worker_id") == member and row.get("payload", {}).get("kind") == "done"
                and event.get("reason") == "staff_done: " + row["payload"].get("reason", "")]
    control = one(controls, "missing_or_ambiguous_original_done_control")
    cp = control["payload"]
    call_id = cp.get("call_id")
    call = inputs.calls.get(call_id)
    require(call is not None and call["member"] == member, "done_call_not_bound_to_actual_charged_input")
    require(cp.get("worker_id") == member and cp.get("decision_id") == call_id
            and cp.get("world_action_executed") is False, "control_identity_or_effect_mismatch")
    record = budget["records"][call_id]
    require(record.get("status") == "settled" and record.get("attempt_started") is True,
            "done_call_not_settled_generation")
    original = one([x for x in evidence.get("original_attempts", []) if x.get("call_id") == call_id],
                   "ambiguous_original_attempt")
    selected_path = Path(call["path"])
    response_path = selected_path.with_name("response.json")
    response = base.read(response_path)
    body = response["body"]
    prep, charge = record["reservation"]["preparation"], record["charge"]
    require(response.get("http_status") == 200 and body.get("id") == original.get("response_id") == charge.get("response_id")
            and digest(json_bytes(body)) == original.get("response_body_sha256") == charge.get("response_body_sha256"),
            "original_response_or_charge_mismatch")
    require(original.get("worker_id") == member and body.get("usage") == original.get("usage") == charge.get("reported_usage"),
            "original_actor_or_usage_mismatch")
    binding = budget.get("binding", {})
    window = binding.get("window_id")
    require(isinstance(window, str) and window.endswith(":" + result["slot_id"])
            and window == prep.get("window_id") == body.get("online_window_id"), "original_window_mismatch")
    identity = binding.get("actor_identity")
    require(identity and identity == prep.get("actor_identity") == body.get("actor_identity") == cp.get("weight_identity"),
            "original_actor_identity_mismatch")
    require(digest(selected_path.read_bytes()) == prep.get("selected_request_sha256"), "selected_request_bytes_changed")
    arguments, tool_id, form = native_done(body)
    reason = arguments["reason"]
    require(cp.get("reason") == reason, "original_control_reason_mismatch")

    def associated(kind, key="model_call_id"):
        return one([x for x in experience if x.get("kind") == kind
                    and x.get("payload", {}).get(key) == call_id], "missing_or_ambiguous_" + kind)

    response_event = associated("model_response", "call_id")
    explicit = None
    if form == "exact_json_done_control":
        # The existing SDK assigns this control identity; it is not a native
        # model tool-call ID and must have its own original conversion receipt.
        tool_id = "control-" + call_id
        explicit = associated("harness_explicit_json_control", "call_id")
        ep = explicit["payload"]
        require(explicit.get("worker_id") == member and ep.get("decision_id") == call_id
                and ep.get("original_response_id") == body["id"]
                and ep.get("original_response_sha256") == digest(json_bytes(body))
                and ep.get("parsed_control") == {"kind": "done", "reason": reason}
                and ep.get("native_tool_call") is False, "explicit_json_control_receipt_mismatch")
    harness = associated("harness_tool_call")
    hp = harness["payload"]
    policy = one([x for x in experience if x.get("kind") == "policy_decision"
                  and x.get("payload", {}).get("decision", {}).get("model_call_id") == call_id],
                 "missing_or_ambiguous_policy_decision")
    decision = policy["payload"]["decision"]
    tool_result = associated("model_tool_result", "call_id")
    expected_output = {"ok": True, "worker_state": "done", "reason": reason, "world_effect": False}
    for row in (response_event, policy, harness, tool_result, control):
        require(row.get("worker_id") == member, "control_record_actor_mismatch")
    require(response_event["payload"].get("response") == body, "experience_response_differs_from_raw_output")
    require(decision == {"kind": "done", "action": "staff_done", "arguments": arguments,
                        "model_call_id": call_id, "model_tool_call_id": tool_id, "decision_id": call_id},
            "policy_decision_not_original_staff_done")
    require(hp.get("action") == "staff_done" and hp.get("arguments") == arguments
            and hp.get("decision_id") == call_id and hp.get("model_tool_call_id") == tool_id
            and hp.get("response") == expected_output, "actual_harness_control_output_mismatch")
    tp = tool_result["payload"]
    require(tp.get("model_tool_call_id") == tool_id and tp.get("world_response") == expected_output
            and json.loads(tp.get("message", {}).get("content", "")) == expected_output,
            "actual_control_tool_result_mismatch")
    order = [original["experience_sequence"], response_event["sequence"], policy["sequence"],
             harness["sequence"], tool_result["sequence"], control["sequence"]]
    require(all(a < b for a, b in zip(order, order[1:])), "original_control_record_order_mismatch")
    require(explicit is None or response_event["sequence"] < explicit["sequence"] < policy["sequence"],
            "explicit_json_control_record_order_mismatch")
    opportunity = cp.get("opportunity_id")
    require(isinstance(opportunity, str) and opportunity.startswith("staff-opportunity-")
            and hp.get("opportunity_id") == opportunity
            and response_event["payload"].get("opportunity_id") == opportunity, "opportunity_identity_mismatch")
    ordinal = int(opportunity.rsplit("-", 1)[1])
    require(1 <= ordinal <= len(opportunities), "missing_scheduled_completion")
    outcome = {"worker_id": member, "status": "completed", "reason": reason, "action_performed": False}
    require(opportunities[ordinal - 1] == outcome
            and result.get("boundary", {}).get("outcomes", [])[ordinal - 1] == outcome,
            "scheduled_outcome_not_actual_member_completion")

    observations = [previous.content(m).get("observation") for m in inputs.messages(call) if m.get("role") == "user"]
    observation = next((x for x in reversed(observations) if isinstance(x, dict)), {})
    require(observation.get("actor_id") == member and observation.get("project_id") == base.PROJECT
            and all(observation.get(k) == state.get(k) and state.get(k) for k in ("world_id", "instance_id", "branch_id"))
            and observation.get("logical_time") == event.get("logical_time"), "retirement_not_at_original_input_world_scope")
    action = one([x for x in state.get("interactions", []) if x.get("action_id") == event.get("action_id")],
                 "missing_or_ambiguous_world_retirement_action")
    require(action.get("actor_id") == member and action.get("action") == "project_action"
            and action.get("inputs") == {"tool": "retire_member", "arguments": {"reason": "staff_done: " + reason},
                                         "project_id": base.PROJECT}, "world_action_not_bound_self_retirement")
    operation = event.get("operation_id")
    commit = state.get("operation_commits", {}).get(operation, {})
    public = commit.get("public_result", {})
    actual_result = {"member_id": member, "status": "retired", "retained_obligations": event.get("retained_obligations")}
    require(operation and action.get("transition_id") == operation and commit.get("operation_id") == operation
            and commit.get("bound_actor") == member and commit.get("receipt", {}).get("contract") == "retire_member"
            and public.get("command_committed") is True and public.get("command_id") == operation
            and public.get("action_id") == event.get("action_id") and public.get("ok") is True
            and public.get("result") == actual_result and action.get("output") == {"ok": True, "result": actual_result},
            "world_retirement_not_committed_with_exact_output")
    registry = state["projects"][base.PROJECT]["software"]["registry"].get(member, {})
    require(registry.get("status") == "retired" and registry.get("retirement_reason") == event["reason"]
            and registry.get("retirement_sequence") == event["sequence"], "retirement_registry_mismatch")
    return {"status": "bound_original_member_staff_done", "member_id": member, "call_id": call_id,
        "model_tool_call_id": tool_id, "control_form": form, "window_id": window, "opportunity_id": opportunity,
        "action_id": event["action_id"], "operation_id": operation, "event_sequence": event["sequence"],
        "original_input": call, "original_response": source(response_path),
        "experience_sequences": dict(zip(("attempt", "response", "policy", "harness_output", "tool_output", "control"), order)),
        "explicit_json_control_sequence": explicit["sequence"] if explicit else None,
        "scheduled_opportunity_index": ordinal - 1,
        "scope": "Original voluntary member control followed by its committed runtime retirement; no cooperation or business-success credit."}


def measure_episode(episode_dir):
    folder = Path(episode_dir).resolve()
    measured = previous.measure_episode(folder)
    old = {key: copy.deepcopy(measured.get(key)) for key in ("version", "status", "recorded_R",
            "has_evidenced_cross_member_chain", "measurement_gaps")}
    measured.update(version=VERSION, lifecycle_attribution={"version": LIFECYCLE_VERSION,
        "prior_measurement": old, "bindings": [], "unresolved": [], "already_bound_action_ids": []})
    lifecycle = measured["lifecycle_attribution"]
    if measured["status"] != "measured":
        return measured
    state_path = folder / "prepared/world/control/state.json"
    if not state_path.is_file():
        state_path = folder / "episode/end/control/state.json"
    state = base.read(state_path)
    retirements = [e for e in state["software_events"] if e["kind"] == "member_retired"]
    if not retirements:
        return measured
    result = base.read(folder / "slot-result.json")
    evidence = base.read(folder / "organization-evidence.json")
    budget = result.get("team_budget", evidence.get("team_budget", {})).get("model", {})
    inputs = base.Inputs(folder, evidence, budget)
    experience_path, opportunities_path = folder / "experience.jsonl", folder / "runtime-opportunities.jsonl"
    experience = [json.loads(line) for line in experience_path.read_text().splitlines()] if experience_path.is_file() else []
    opportunities = [json.loads(line) for line in opportunities_path.read_text().splitlines()] if opportunities_path.is_file() else []
    bound = set()
    for event in retirements:
        if inputs.bound(event):
            lifecycle["already_bound_action_ids"].append(event["action_id"])
            continue
        try:
            link = bind_retirement(event, state=state, result=result, evidence=evidence, budget=budget,
                inputs=inputs, experience=experience, opportunities=opportunities, folder=folder)
        except (UnboundLifecycle, OSError, KeyError, IndexError, TypeError, ValueError) as error:
            lifecycle["unresolved"].append({"event": base.brief_event(event, state_path), "reason": str(error)})
            continue
        bound.add((event["sequence"], event["actor_id"], event["action_id"]))
        link["world_event"] = base.brief_event(event, state_path)
        lifecycle["bindings"].append(link)
        counts = measured["member_work"][event["actor_id"]]["actual_event_counts"]
        counts["member_retired"] = counts.get("member_retired", 0) + 1
    gaps = []
    for gap in measured["measurement_gaps"]:
        if gap.get("reason") != "member_events_without_actual_output_binding":
            gaps.append(gap)
            continue
        remaining = [e for e in gap["events"] if (e.get("sequence"), e.get("actor_id"), e.get("action_id")) not in bound]
        if remaining:
            gaps.append({**gap, "events": remaining})
    measured["measurement_gaps"] = gaps
    measured["has_evidenced_cross_member_chain"] = (True if measured["program_work_chains"] else
        None if measured["information_work_candidates"] or measured["pending_program_relations"]
        or measured["unsupported_relations"] or gaps else False)
    lifecycle["sources"] = {"world": source(state_path), "experience": source(experience_path)}
    if opportunities_path.is_file():
        lifecycle["sources"]["opportunities"] = source(opportunities_path)
    return measured


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json_bytes(measure_episode(args.episode))
    if args.output:
        if args.output.resolve().is_relative_to(args.episode.resolve()):
            raise ValueError("Write revised measurements outside the original episode directory")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(rendered)
    else:
        print(rendered.decode(), end="")


if __name__ == "__main__":
    main()
