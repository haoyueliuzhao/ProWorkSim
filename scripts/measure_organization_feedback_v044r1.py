"""Read-only v044r1 termination attribution; the model-visible v044 Gamma is unchanged.

Re-materialize the unchanged v044 feedback measurement and explain only a
uniquely bound, committed native self-retirement. Its return is still unseen.
No model, tokenizer, world execution, business test or acceptance is invoked.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import copy
import json
from pathlib import Path

from proworksim.storage import atomic_write, digest, json_bytes
from scripts import measure_organization_feedback_v044 as previous

VERSION = "organization-feedback-opportunities-v0.44r1"
ATTRIBUTION_VERSION = "committed-native-self-retirement-attribution-v0.44r1"
ROOT = Path(__file__).resolve().parents[1]
FIRST_SLOTS = tuple("org44-r1-s0-" + condition for condition in ("PT", "SB", "ST", "PB"))
REASON = "voluntary_self_retirement"


class UnboundRetirement(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise UnboundRetirement(reason)


def one(rows, reason):
    require(len(rows) == 1, reason)
    return rows[0]


def reference(path, pointer=None):
    path = Path(path).resolve()
    data = path.read_bytes()
    result = {"path": str(path), "sha256": digest(data), "bytes": len(data)}
    if pointer is not None:
        result["json_pointer"] = pointer
    return result


def read(path):
    return json.loads(Path(path).read_text())


def bind_self_retirement(row, *, state, result, evidence, budget, inputs, experience, folder):
    """Bind the original call and committed self target; never infer from retired alone."""
    member, call_id = row.get("member"), row.get("originating_call_id")
    require(row.get("kind") == "native_tool_feedback" and row.get("tool") == "retire_member"
            and row.get("generated_and_saved") is True and row.get("actual_originating_generation_bound") is True,
            "not_an_original_native_retirement_feedback")
    presentation = row.get("presentation", {})
    require(row.get("no_actual_followup") is not None and presentation.get("later_actual_generation_count") == 0
            and presentation.get("first_exact_presentation") is None
            and presentation.get("matching_actual_request_count") == 0,
            "retirement_feedback_has_actual_followup_or_missing_presentation_account")
    boundary = result.get("boundary", {})
    require(result.get("status") == "closed" and not boundary.get("execution_integrity_failure")
            and boundary.get("role_stops", {}).get(member) == "retired", "retirement_terminal_boundary_mismatch")
    call = inputs.calls.get(call_id)
    require(call is not None and call["member"] == member, "retirement_call_not_bound_to_original_member")
    require(not [item for item in inputs.by_member(member) if item["experience_sequence"] > row["experience_sequence"]],
            "actual_member_generation_after_retirement")
    record = budget.get("records", {}).get(call_id, {})
    require(record.get("member") == member and record.get("attempt_started") is True
            and record.get("status") == "settled", "retirement_call_not_started_and_settled")
    original = one([item for item in evidence.get("original_attempts", []) if item.get("call_id") == call_id],
                   "missing_or_ambiguous_original_generation")
    selected_path = Path(call["path"])
    raw_path = selected_path.with_name("response.json")
    selected, raw = read(selected_path), read(raw_path)
    body = raw.get("body", {})
    prep, charge = record.get("reservation", {}).get("preparation", {}), record.get("charge", {})
    trace, usage = body.get("token_trace", {}), body.get("usage")
    require(raw.get("http_status") == 200 and original.get("status") == "success"
            and original.get("original_output_present") is True and original.get("worker_id") == member
            and body.get("id") == original.get("response_id") == charge.get("response_id")
            and digest(json_bytes(body)) == original.get("response_body_sha256") == charge.get("response_body_sha256"),
            "original_retirement_response_identity_mismatch")
    require(isinstance(trace.get("input_ids"), list) and bool(trace["input_ids"])
            and isinstance(trace.get("output_ids"), list) and bool(trace["output_ids"])
            and digest(json_bytes(selected)) == prep.get("selected_request_sha256") == call.get("selected_request_sha256")
            and digest(json_bytes(trace["input_ids"])) == prep.get("input_ids_sha256") == original.get("input_ids_sha256")
            and digest(json_bytes(trace["output_ids"])) == original.get("output_ids_sha256"),
            "original_selected_or_actual_token_trace_mismatch")
    require(isinstance(usage, dict) and usage == original.get("usage") == charge.get("reported_usage")
            and usage.get("prompt_tokens") == len(trace["input_ids"]) == prep.get("prompt_tokens")
            and usage.get("completion_tokens") == len(trace["output_ids"])
            and charge.get("usage_status") == "reported_actual_trace"
            and charge.get("charged_tokens") == usage.get("total_tokens")
            and usage.get("total_tokens") == usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
            "original_retirement_usage_not_exactly_charged")
    binding = budget.get("binding", {})
    window, identity = binding.get("window_id"), binding.get("actor_identity")
    require(isinstance(window, str) and window == "organization-v044:" + result["slot_id"]
            and window == prep.get("window_id") == body.get("online_window_id"), "original_retirement_window_mismatch")
    require(identity and identity == prep.get("actor_identity") == body.get("actor_identity"),
            "original_retirement_actor_identity_mismatch")
    require(body.get("protocol_parse_error") is None, "original_native_retirement_parse_failed")
    choice = one(body.get("choices", []), "ambiguous_retirement_native_choice")
    require(choice.get("finish_reason") in {"stop", "tool_calls"}, "incomplete_retirement_native_choice")
    message = choice.get("message", {})
    require(message.get("role") == "assistant", "retirement_output_not_assistant")
    native = one(message.get("tool_calls", []), "not_single_native_retirement_call")
    require(native.get("type") == "function" and native.get("function", {}).get("name") == "retire_member",
            "original_native_tool_is_not_retire_member")
    arguments = json.loads(native["function"]["arguments"])
    require(isinstance(arguments, dict) and set(arguments) == {"reason"}
            and isinstance(arguments["reason"], str) and bool(arguments["reason"].strip()),
            "retirement_has_rewritten_or_invented_target_arguments")
    tool_id = native.get("id")
    require(isinstance(tool_id, str) and tool_id and tool_id == row.get("model_tool_call_id")
            and arguments == row.get("arguments"), "retirement_feedback_call_or_arguments_mismatch")

    def event(kind, predicate):
        value = one([item for item in experience if item.get("kind") == kind and predicate(item.get("payload", {}))],
                    "missing_or_ambiguous_original_" + kind)
        require(value.get("worker_id") == member, "retirement_event_actor_mismatch:" + kind)
        return value

    response_event = event("model_response", lambda p: p.get("call_id") == call_id)
    proposal = event("model_call", lambda p: p.get("call_id") == call_id and p.get("stage") == "finished" and p.get("status") == "proposed_action")
    policy = event("policy_decision", lambda p: p.get("decision", {}).get("model_call_id") == call_id)
    committed = event("tool_call", lambda p: p.get("model_call_id") == call_id)
    link = event("model_action_link", lambda p: p.get("model_call_id") == call_id)
    feedback = event("model_tool_result", lambda p: p.get("call_id") == call_id)
    pp, dp, cp, lp, fp = proposal["payload"], policy["payload"]["decision"], committed["payload"], link["payload"], feedback["payload"]
    association = {"model_call_id": call_id, "model_tool_call_id": tool_id, "decision_id": call_id}
    require(response_event["payload"].get("response") == body, "recorded_response_not_original_retirement_output")
    require(pp.get("worker_id") == member and pp.get("decision_id") == call_id
            and pp.get("model_tool_call_id") == tool_id and pp.get("weight_identity") == identity
            and pp.get("proposed_action") == {"action": "retire_member", "arguments": arguments},
            "retirement_proposal_not_original_native_and_schema_call")
    require(dp == {"kind": "act", "action": "retire_member", "arguments": arguments, **association},
            "retirement_policy_decision_mismatch")
    require(cp.get("action") == "retire_member" and cp.get("arguments") == arguments
            and all(cp.get(key) == value for key, value in association.items())
            and all(lp.get(key) == value for key, value in association.items()), "retirement_tool_or_action_link_identity_mismatch")
    opportunity = pp.get("opportunity_id")
    require(isinstance(opportunity, str) and opportunity.startswith("staff-opportunity-")
            and opportunity == cp.get("opportunity_id") == lp.get("opportunity_id")
            == response_event["payload"].get("opportunity_id"), "retirement_opportunity_mismatch")
    world_response = cp.get("response", {})
    action_id, operation = world_response.get("action_id"), world_response.get("command_id")
    require(world_response.get("ok") is True and world_response.get("command_committed") is True
            and isinstance(action_id, str) and action_id and isinstance(operation, str) and operation
            and lp.get("world_action_id") == action_id and lp.get("world_command_id") == operation
            and lp.get("world_response") == world_response
            and lp.get("request_key") == cp.get("request_key"), "retirement_world_receipt_not_committed_or_linked")
    require(fp.get("model_tool_call_id") == tool_id and fp.get("world_response") == world_response
            and fp.get("message", {}).get("role") == "tool" and fp["message"].get("tool_call_id") == tool_id
            and json.loads(fp["message"].get("content", "")) == world_response
            and feedback["sequence"] == row["experience_sequence"]
            and row.get("feedback_payload_sha256") == digest(json_bytes(world_response)),
            "retirement_feedback_not_exact_committed_return")
    order = [original["experience_sequence"], response_event["sequence"], proposal["sequence"], policy["sequence"],
             committed["sequence"], link["sequence"], feedback["sequence"]]
    require(all(a < b for a, b in zip(order, order[1:])), "retirement_experience_event_order_mismatch")
    require(not [item for item in inputs.by_member(member) if item["call_id"] != call_id
                 and item["experience_sequence"] > committed["sequence"]],
            "actual_member_generation_after_committed_retirement")
    retirement = one([item for item in state.get("software_events", []) if item.get("kind") == "member_retired"
        and (item.get("actor_id") == member or item.get("member_id") == member)], "missing_or_ambiguous_self_retirement_event")
    require(previous.base.actual_event(retirement) and retirement.get("origin") in {None, "model", "member_request"}
            and retirement.get("actor_id") == retirement.get("member_id") == member
            and retirement.get("action_id") == action_id and retirement.get("operation_id") == operation
            and retirement.get("reason") == arguments["reason"], "external_or_mismatched_retirement_world_event")
    observed = [previous.decoded(item).get("observation") for item in selected.get("messages", [])
                if item.get("role") == "user" and isinstance(previous.decoded(item), dict)]
    observation = next((item for item in reversed(observed) if isinstance(item, dict)), {})
    require(observation.get("actor_id") == member and observation.get("project_id") == previous.base.PROJECT
            and all(observation.get(key) == state.get(key) and state.get(key) for key in ("world_id", "instance_id", "branch_id"))
            and observation.get("logical_time") == retirement.get("logical_time"), "retirement_input_world_scope_mismatch")
    action = one([item for item in state.get("interactions", []) if item.get("action_id") == action_id],
                 "missing_or_ambiguous_retirement_world_action")
    actual_result = {"member_id": member, "status": "retired", "retained_obligations": retirement.get("retained_obligations")}
    require(action.get("actor_id") == member and action.get("action") == "project_action"
            and action.get("inputs") == {"tool": "retire_member", "arguments": arguments, "project_id": previous.base.PROJECT}
            and action.get("transition_id") == operation and action.get("request_key") == cp.get("request_key")
            and action.get("output") == {"ok": True, "result": actual_result}, "retirement_world_action_or_self_target_mismatch")
    commit = state.get("operation_commits", {}).get(operation, {})
    require(commit.get("operation_id") == operation and commit.get("bound_actor") == member
            and commit.get("public_result") == world_response and world_response.get("result") == actual_result
            and commit.get("receipt", {}).get("contract") == "retire_member"
            and commit["receipt"].get("bound_actor") == member
            and commit["receipt"].get("execution_outcome") == "committed"
            and commit["receipt"].get("transition_id") == operation
            and commit.get("committed_revision") == world_response.get("committed_revision"),
            "retirement_committed_operation_or_target_mismatch")
    registry = state["projects"][previous.base.PROJECT]["software"]["registry"].get(member, {})
    require(registry.get("member_id") == member and registry.get("status") == "retired"
            and registry.get("retirement_sequence") == retirement["sequence"]
            and registry.get("retirement_reason") == retirement["reason"], "retirement_committed_registry_mismatch")
    later = [item for item in experience if item.get("worker_id") == member and item.get("sequence", -1) > feedback["sequence"]]
    require(not any(item.get("kind") == "model_boundary_error" for item in later), "unexplained_boundary_after_retirement")
    require(not any(item.get("kind") in {"process_violation", "execution_integrity_error", "permission_violation"}
                    and (item.get("payload", {}).get("call_id") == call_id or item.get("payload", {}).get("model_call_id") == call_id)
                    for item in experience), "retirement_has_unexplained_integrity_or_permission_record")
    return {"version": ATTRIBUTION_VERSION, "status": "bound_original_committed_self_retirement", "reason": REASON,
        "member_id": member, "call_id": call_id, "model_tool_call_id": tool_id, "window_id": window,
        "opportunity_id": opportunity, "action_id": action_id, "operation_id": operation,
        "retirement_world_event_sequence": retirement["sequence"], "registry_retirement_sequence": registry["retirement_sequence"],
        "experience_sequences": dict(zip(("generation", "response", "proposal", "policy", "committed_tool", "action_link", "feedback"), order)),
        "target_source": "Original returned member_id, event member_id and committed registry key; all equal actor. Original schema only reason.",
        "actual_feedback_presentation_added": False, "later_member_actual_generations": 0,
        "R_used_for_classification": False, "obligations_removed": False,
        "retained_obligations": copy.deepcopy(retirement.get("retained_obligations")),
        "selected_request": reference(selected_path), "original_response": reference(raw_path),
        "scope": "Normal member termination explains no followup; it does not establish return visibility, task completion or cooperation. Event order is checked within experience; world sequence is joined by action/operation, never numerically compared across logs."}


def apply_termination_revision(baseline, bindings, failures):
    """Change explanations only; preserve every feedback record and presentation field."""
    result = copy.deepcopy(baseline)
    changes = []
    for row in result.get("feedback_records", []):
        proof = bindings.get(row["feedback_id"])
        if proof is None:
            continue
        prior = copy.deepcopy(row["no_actual_followup"])
        row["no_actual_followup"] = {**prior, "reason": REASON}
        row["termination_attribution"] = proof
        changes.append({"slot_id": result.get("slot_id"), "feedback_id": row["feedback_id"],
            "member": row["member"], "call_id": row["originating_call_id"],
            "previous_reason": prior["reason"], "revised_reason": REASON,
            "presentation_unchanged": True, "feedback_denominator_retained": True})
    result.update(version=VERSION, inherited_feedback_version=previous.VERSION,
        original_v044_remeasurement_sha256=digest(json_bytes(baseline)),
        termination_revision={"version": ATTRIBUTION_VERSION, "bindings": list(bindings.values()),
            "unresolved": failures, "classification_changes": changes,
            "actual_model_visibility_unchanged": True, "original_R_unchanged": True})
    if baseline.get("status") != "measured":
        return result
    reasons = Counter(row["no_actual_followup"]["reason"] for row in result["feedback_records"] if row.get("no_actual_followup"))
    result["denominators"]["no_followup_reasons"] = dict(reasons)
    for tool, count in result["denominators"].get("by_tool", {}).items():
        count["no_followup_reasons"] = dict(Counter(row["no_actual_followup"]["reason"] for row in result["feedback_records"]
            if (row.get("tool") or "unknown") == tool and row.get("no_actual_followup")))
    facts = result["mechanism_gate_inputs"]
    unresolved = [row["feedback_id"] for row in result["feedback_records"] if row.get("no_actual_followup")
        and row["no_actual_followup"]["reason"] in {"unknown_no_actual_followup", "episode_unclosed_or_fault"}]
    facts["unresolved_no_followup_ids"] = unresolved
    result["measurement_gaps"].extend({"reason": "direct_retirement_attribution_unresolved", **item} for item in failures)
    facts["resolved"] = (not result["measurement_gaps"] and not unresolved
        and not facts.get("page_protocol_unresolved") and result.get("episode_closed") is True)
    facts["termination_attribution_unresolved"] = [item["feedback_id"] for item in failures]
    return result


def measure_episode(episode_dir):
    folder = Path(episode_dir).resolve()
    baseline = previous.measure_episode(folder)
    bindings, failures = {}, []
    candidates = [row for row in baseline.get("feedback_records", []) if row.get("tool") == "retire_member"
                  and row.get("no_actual_followup") is not None]
    if candidates:
        try:
            result = read(folder / "slot-result.json")
            evidence = read(folder / "organization-evidence.json")
            budget = result.get("team_budget", evidence.get("team_budget", {})).get("model", {})
            state_path = folder / "prepared/world/control/state.json"
            if not state_path.is_file():
                state_path = folder / "episode/end/control/state.json"
            state = read(state_path)
            inputs = previous.base.Inputs(folder, evidence, budget)
            relevant = {"model_response", "model_call", "policy_decision", "tool_call", "model_action_link", "model_tool_result",
                        "model_boundary_error", "process_violation", "execution_integrity_error", "permission_violation"}
            experience = []
            with (folder / "experience.jsonl").open() as stream:
                for line in stream:
                    if any('"kind": "' + kind + '"' in line for kind in relevant):
                        item = json.loads(line)
                        if item.get("kind") in relevant:
                            experience.append(item)
            require(not inputs.issues, "independent_actual_input_binding_unresolved")
            for row in candidates:
                # A rejected retirement is ordinary business feedback, not a
                # successful termination claim. Preserve its existing budget/
                # wait/end explanation unless the recorded member was retired.
                if row.get("feedback_ok") is False and result.get("boundary", {}).get("role_stops", {}).get(row.get("member")) != "retired":
                    continue
                try:
                    proof = bind_self_retirement(row, state=state, result=result, evidence=evidence, budget=budget,
                        inputs=inputs, experience=experience, folder=folder)
                    proof["source_refs"] = {name: reference(path) for name, path in {
                        "result": folder / "slot-result.json", "evidence": folder / "organization-evidence.json",
                        "world_state": state_path, "experience": folder / "experience.jsonl"}.items()}
                    bindings[row["feedback_id"]] = proof
                except (UnboundRetirement, OSError, KeyError, IndexError, TypeError, ValueError) as error:
                    failures.append({"feedback_id": row["feedback_id"], "member": row.get("member"), "detail": str(error)})
        except (UnboundRetirement, OSError, KeyError, IndexError, TypeError, ValueError) as error:
            failures.extend({"feedback_id": row["feedback_id"], "member": row.get("member"), "detail": str(error)} for row in candidates)
    return apply_termination_revision(baseline, bindings, failures)


def first_block_gate(measurements):
    gate = previous.first_block_gate(measurements)
    reasons = copy.deepcopy(gate["reasons"])
    for row in measurements:
        if not isinstance(row, dict) or row.get("version") != VERSION or "termination_revision" not in row:
            reasons.append({"slot_id": row.get("slot_id") if isinstance(row, dict) else None, "reason": "revised_termination_measurement_missing"})
        elif row["termination_revision"].get("unresolved"):
            reasons.append({"slot_id": row.get("slot_id"), "reason": "termination_attribution_unresolved"})
    return {**gate, "version": VERSION, "inherited_gate_version": previous.VERSION,
            "passed": not reasons, "reasons": reasons,
            "scope": "Same v044 mechanical gate plus strict original self-retirement attribution. No R, task completion, reading, messaging or recruitment selection; no feedback is removed from its denominator or marked seen."}


def aggregate_denominators(measurements):
    keys = ("all_saved_feedback_units", "protocol_feedback_saved_exactly", "with_later_actual_generation",
            "presented_in_later_actual_generation", "presented_in_first_actual_followup", "without_later_actual_generation")
    reasons = Counter()
    for row in measurements:
        reasons.update(row.get("denominators", {}).get("no_followup_reasons", {}))
    return {**{key: sum(row.get("denominators", {}).get(key, 0) for row in measurements) for key in keys},
            "no_followup_reasons": dict(reasons)}


def materialize_first_block(run_root, output, *, workers=4):
    run_root, output = Path(run_root).resolve(), Path(output).resolve()
    require(not output.exists(), "Revised evidence must be written to a new output directory")
    episodes = [run_root / "block-r1-s0/actual/episodes" / slot for slot in FIRST_SLOTS]
    original_gate_path = run_root / "first-block-gate.json"
    protected = [original_gate_path]
    originals, old_measurements = [], []
    for folder in episodes:
        for name in ("slot-result.json", "feedback-loop.json", "team-budget.json", "organization-evidence.json", "experience.jsonl"):
            protected.append(folder / name)
        result = read(folder / "slot-result.json")
        require(result.get("slot_id") == folder.name and result.get("status") == "closed", "First block is not four original closed slots")
        old_measurements.append(read(folder / "feedback-loop.json"))
        originals.append({"slot_id": folder.name, "R": result.get("R"), "submitted": result.get("submitted"),
            "slot_result": reference(folder / "slot-result.json"), "original_feedback": reference(folder / "feedback-loop.json")})
    before = {str(path): reference(path) for path in protected}
    output.mkdir(parents=True)
    refs = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        measurements = list(pool.map(measure_episode, episodes))
    for folder, old, value in zip(episodes, old_measurements, measurements):
        require(value["original_v044_remeasurement_sha256"] == digest(json_bytes(old)), "Original v044 complete remeasurement changed")
        destination = output / "slots" / (folder.name + ".json")
        atomic_write(destination, json_bytes(value))
        refs.append(reference(destination))
    gate = first_block_gate(measurements)
    atomic_write(output / "gate.json", json_bytes(gate))
    after = {str(path): reference(path) for path in protected}
    require(before == after, "Read-only remeasurement changed original artifacts")
    old_denominators, revised_denominators = aggregate_denominators(old_measurements), aggregate_denominators(measurements)
    stable_keys = set(old_denominators) - {"no_followup_reasons"}
    require(all(old_denominators[key] == revised_denominators[key] for key in stable_keys), "Retirement classification changed presentation denominators")
    changes = [change for value in measurements for change in value["termination_revision"]["classification_changes"]]
    summary = {"version": VERSION, "passed": gate["passed"], "read_only": True,
        "new_model_calls": 0, "new_tokenizer_calls": 0, "new_test_or_acceptance_executions": 0,
        "slot_ids": list(FIRST_SLOTS), "slot_measurements": refs,
        "measurements_by_slot": dict(zip(FIRST_SLOTS, refs)), "revised_gate": reference(output / "gate.json"),
        "original_gate": before[str(original_gate_path)], "original_gate_value": read(original_gate_path),
        "original_slots": originals, "classification_changes": changes,
        "original_denominators": old_denominators, "revised_denominators": revised_denominators,
        "original_artifacts_unchanged": True, "protected_original_artifacts": list(before.values()),
        "source_bindings": [reference(ROOT / name) for name in ("scripts/measure_organization_feedback_v044r1.py",
            "tests/test_organization_feedback_v044r1.py", "scripts/measure_organization_feedback_v044.py", "scripts/software_context_replay_v044.py",
            "src/proworksim/software_feedback_v044.py", "src/proworksim/software_context_v044.py")],
        "scope": "Recomputed all four original slots from unchanged artifacts. A self-retirement return remains unseen; the original false gate, R and stopped inventory are preserved. This receipt itself launches nothing."}
    atomic_write(output / "summary.json", json_bytes(summary))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--first-block", type=Path)
    args = parser.parse_args()
    if args.first_block:
        require(args.output is not None, "First-block rematerialization needs a separate output directory")
        value = materialize_first_block(args.first_block, args.output)
        print(json.dumps({"passed": value["passed"], "summary": str(args.output / "summary.json")}, ensure_ascii=False))
    else:
        require(args.episode is not None, "An archived episode is required")
        value = measure_episode(args.episode)
        if args.output:
            require(not args.output.exists(), "Do not overwrite an original measurement")
            atomic_write(args.output, json_bytes(value))
        else:
            print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
