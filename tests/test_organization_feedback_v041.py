"""Finite saved-JSON controls; no real tokenizer, model, business test or GPU."""
import copy
import json

import pytest

from proworksim.software_context_v041 import deduplicate_static_snapshots
from proworksim.storage import digest, json_bytes
from scripts import measure_organization_feedback_v041 as measure


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def fixture(root, *, first_tool="read_file", finish_reason=None, format_feedback=False,
            fixed_delivery=False, tamper=None, prepared_only=False):
    member, initial_ref = "member_001", {"object_id": "baseline", "version_id": "v1"}
    report = {"diagnostic_id": "case:a", "origin": "environment_initial_diagnostic", "initial_report": True,
              "initial_source_reference": initial_ref, "source_reference": initial_ref, "files_sha256": "initial-files",
              "executed": True, "passed": False, "tests": [{"test_id": "a", "passed": False,
                                                            "request": 1, "observed": 1, "expected": 2}]}
    observation = {"world_id": "world", "instance_id": "instance", "branch_id": "branch", "project_id": "SOFTWARE27",
        "actor_id": member, "interface_revision": "same-world", "workspace_reference": initial_ref,
        "contract": "Produce the requested behavior.", "root_goal": {"task_id": "root_goal", "description": "Produce the requested behavior."},
        "initial_diagnostics": [report], "team_model_budget": {"remaining_attempts": 128}, "tasks": {},
        "action_error_policy": {"version": "errors-v040"}, "acceptance_contract": {"final_fixed_only": True},
        "scheduling": {"protocol": "fair"}, "member_limits": {"live": 4, "births": 6},
        "shared_resource_limits": {"attempts": 128}, "isolation": {"private_workspaces": True},
        "observation_projection": {"version": "unchanged-visible-feedback"},
        "initial_diagnostic_provenance": {"origin": "environment_initial_diagnostic", "model_generated": False},
        "editable_paths": ["product.py"]}
    history = [{"role": "system", "content": "Use the declared native tools."}]
    records, originals, events, world_events = {}, [], [], []
    canonical = None
    tools = [first_tool] if finish_reason else [first_tool, "submit_integration" if fixed_delivery else "write_file", "staff_done"]
    groups = {name: {"executed": True, "passed": True} for name in ("upstream_regressions", "public_normal")}
    for number, tool in enumerate(tools, 1):
        call_id, tool_id, sequence = f"call-{number}", f"tool-{number}", number * 10
        obs = copy.deepcopy(observation)
        obs["team_model_budget"]["remaining_attempts"] -= number - 1
        original = {"max_tokens": 2048, "tools": [{"type": "function", "function": {"name": "read_file"}}],
            "messages": [*copy.deepcopy(history), {"role": "user", "content": json.dumps({"role_task": "Complete the contract.", "observation": obs})}]}
        selected, metadata = deduplicate_static_snapshots(original)
        kept = list(range(len(original["messages"])))
        pairs = [[i, i + 1] for i, m in enumerate(original["messages"]) if m.get("role") == "assistant" and m.get("tool_calls")]
        if number == 2 and tamper == "feedback":
            removed = set(pairs[-1])
            kept = [i for i in kept if i not in removed]
            selected["messages"] = [m for i, m in enumerate(selected["messages"]) if i in kept]
        if number == 2 and tamper == "diagnostic":
            latest = json.loads(selected["messages"][-1]["content"])
            latest["observation"].pop("initial_diagnostics")
            selected["messages"][-1]["content"] = json.dumps(latest)
        if number == 2 and tamper == "permission":
            latest = json.loads(selected["messages"][-1]["content"])
            leaked = {**copy.deepcopy(report), "diagnostic_id": "other-member-report"}
            latest["observation"]["initial_diagnostics"].append(leaked)
            selected["messages"][-1]["content"] = json.dumps(latest)
        projection = {"version": "software-context-v0.34" if tamper == "old" else measure.PROJECTION_VERSION,
            "original_request_sha256": digest(json_bytes(original)), "selected_request_sha256": digest(json_bytes(selected)),
            "input_ids_sha256": f"input-{number}", "selected_prompt_tokens": 1000 + number, "reserved_output_tokens": 2048,
            "context_limit": 16384, "fits": True, "selected_indices": kept,
            "removed_indices": [i for i in range(len(original["messages"])) if i not in kept],
            "complete_tool_rounds": pairs, "latest_complete_round_preserved": pairs[-1] if pairs else None,
            "deduplication": metadata}
        folder = root / "raw-transport" / f"request-{number:05d}"
        save(folder / "original-request.json", original)
        save(folder / "selected-request.json", selected)
        save(folder / "projection.json", projection)
        prep = {"original_request_sha256": projection["original_request_sha256"],
            "selected_request_sha256": projection["selected_request_sha256"], "input_ids_sha256": projection["input_ids_sha256"],
            "prompt_tokens": projection["selected_prompt_tokens"]}
        records[call_id] = {"member": member, "status": "settled", "attempt_started": True,
            "reservation": {"preparation": prep}, "charge": {"reported_usage": {"prompt_tokens": 1000 + number,
                                                                                   "completion_tokens": 10, "total_tokens": 1010 + number}}}
        originals.append({"call_id": call_id, "status": "success", "original_output_present": True,
                          "experience_sequence": sequence, "input_ids_sha256": f"input-{number}"})
        if format_feedback and number == 1:
            value = {"public_format_feedback": {"version": "public-format-feedback-v0.33", "model_call_id": call_id,
                                               "reason": "Choose an exactly declared tool.", "continues_on_later_opportunity": True}}
            canonical = {"role": "user", "content": json.dumps(value)}
            events.append({"sequence": sequence + 3, "kind": "model_format_feedback", "worker_id": member,
                           "payload": {"call_id": call_id, "feedback": value["public_format_feedback"]}})
            history = [*original["messages"], {"role": "assistant", "content": "No native action."}, canonical]
            continue
        args = {"path": "product.py"} if tool in {"read_file", "write_file"} else {}
        body = {"source_reference": initial_ref}
        if tool == "read_file":
            body.update(path="product.py", text="original visible file content")
        if tool == "run_tests":
            body.update(groups=groups, executed=True, passed=True)
        response = {"ok": True, "result": body, "action_id": "action-" + str(number)}
        decision = {"action": tool, "arguments": args, "model_call_id": call_id, "model_tool_call_id": tool_id,
                    "kind": "done" if tool == "staff_done" else "wait" if tool == "staff_wait" else "act"}
        events.extend([
            {"sequence": sequence + 1, "kind": "policy_decision", "worker_id": member, "payload": {"decision": decision}},
            {"sequence": sequence + 2, "kind": "tool_call", "worker_id": member,
             "payload": {"action": tool, "arguments": args, "model_call_id": call_id, "model_tool_call_id": tool_id, "response": response}},
            {"sequence": sequence + 3, "kind": "model_tool_result", "worker_id": member,
             "payload": {"call_id": call_id, "model_tool_call_id": tool_id,
                         "message": {"role": "tool", "tool_call_id": tool_id, "content": json.dumps(response)}, "world_response": response}},
        ])
        if tool in {"staff_done", "staff_wait"}:
            events.append({"sequence": sequence + 4, "kind": "model_control", "worker_id": member,
                           "payload": {"call_id": call_id, "kind": "done" if tool == "staff_done" else "wait"}})
        kind = {"read_file": "read", "write_file": "edit", "run_tests": "test", "submit_integration": "submit"}.get(tool)
        if kind:
            event = {"sequence": len(world_events) + 1, "kind": kind, "actor_id": member, "source_reference": initial_ref,
                     "action_id": response["action_id"]}
            if kind == "test":
                event["groups"] = groups
            if kind == "submit":
                event.update(test_sequence=1, delivery_id="fixed-1")
            world_events.append(event)
        canonical = {"role": "tool", "tool_call_id": tool_id, "name": tool, "content": json.dumps(response)}
        history = [*original["messages"], {"role": "assistant", "content": "", "tool_calls": [{"id": tool_id,
            "type": "function", "function": {"name": tool, "arguments": json.dumps(args)}}]}, canonical]
    end = {"status": "completed", "cause": "completed"}
    boundary = {"terminal_details": {member: end}, "role_stops": {member: "completed"}, "waiting_members": {}, "closure_reason": "all_members_stopped"}
    if finish_reason == "context_capacity":
        end.update(status="model_budget_exhausted", cause="context_capacity", generation_started=False)
        boundary["role_stops"][member] = "model_budget_exhausted"
        events.append({"sequence": 25, "kind": "model_boundary_error", "worker_id": member,
                       "payload": {"budget_kind": "context_capacity", "status": "model_budget_exhausted"}})
        records["rejected"] = {"member": member, "status": "admission_rejected", "attempt_started": False, "budget_kind": "context_capacity"}
        if prepared_only:
            pending = {"max_tokens": 2048, "tools": [], "messages": history}
            save(root / "raw-transport/request-00002/selected-request.json", pending)
            save(root / "raw-transport/request-00002/projection.json", {"selected_request_sha256": "unstarted", "input_ids_sha256": "unstarted"})
    elif finish_reason == "team_budget":
        end.update(status="team_budget_exhausted", cause="shared_team_pool_exhausted")
        boundary.update(role_stops={member: "team_budget_exhausted"}, closure_reason="shared_team_pool_exhausted")
    elif finish_reason == "waiting_without_event":
        end.update(status="worker_waiting", cause="no_reachable_wake_event")
        boundary.update(role_stops={}, waiting_members={member: 1}, closure_reason="no_reachable_future_events")
    elif finish_reason == "execution_fault":
        end.update(status="execution_integrity_error", cause="execution_integrity_error")
        boundary["role_stops"][member] = "execution_integrity_error"
        boundary["execution_integrity_failure"] = {"member": member, "status": "execution_integrity_error"}
    save(root / "prepared/world/control/state.json", {"projects": {"SOFTWARE27": {"software": {
        "initial_diagnostics": {"case:a": report}, "initial_diagnostic_assignments": {member: ["case:a"]}}}}, "software_events": world_events})
    save(root / "organization-evidence.json", {"original_attempts": originals})
    save(root / "slot-result.json", {"slot_id": root.name, "status": "technical_unknown" if finish_reason == "execution_fault" else "closed",
        "R": 0, "boundary": boundary, "team_budget": {"model": {"records": records}}})
    (root / "experience.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return root


def block(value):
    return [{**copy.deepcopy(value), "slot_id": f"slot-{i}"} for i in range(4)]


def test_saved_feedback_actual_input_and_behavior_candidates_are_distinct(tmp_path):
    value = measure.measure_episode(fixture(tmp_path))
    assert value["measurement_gaps"] == []
    assert all(a["status"] == "verified" for a in value["projection_audit"])
    assert value["projection_audit"][1]["declared_duplicate_fields_removed"] == 14
    first = value["feedback_records"][0]
    assert first["generated_and_saved"] is True
    assert first["presentation"]["presented_in_first_actual_followup"] is True
    assert first["following_behavior_candidates"][0]["action"] == "write_file"
    assert first["following_behavior_candidates"][0]["same_explicit_path"] is True
    assert first["following_behavior_candidates"][0]["causal_use"] == "not_inferred"
    assert first["final_fixed_relation"]["status"] == "no_final_fixed_delivery"
    assert value["denominators"]["all_saved_feedback_units"] == 3
    assert value["denominators"]["presented_in_later_actual_generation"] == 2
    assert value["denominators"]["no_followup_reasons"] == {"voluntary_end": 1}
    assert value["environment_initial_diagnostics"][0]["member_discovery"] is False
    assert value["environment_initial_diagnostics"][0]["first_actual_presentation"]
    assert measure.first_block_gate(block(value))["passed"] is True


def test_current_public_test_feedback_can_bind_final_fixed_version_without_causal_claim(tmp_path):
    value = measure.measure_episode(fixture(tmp_path, first_tool="run_tests", fixed_delivery=True))
    first = value["feedback_records"][0]
    assert first["public_test"] is True
    assert first["final_fixed_relation"]["status"] == "exact_test_version_bound_to_fixed_delivery"
    assert first["final_fixed_relation"]["feedback_presented_before_same_member_delivery"] is True
    assert first["final_fixed_relation"]["semantic_use"] == "not_inferred"


@pytest.mark.parametrize("first_tool", ["read_file", "write_file"])
def test_any_real_feedback_blocked_by_context_stops_gate_even_with_unstarted_selected_input(tmp_path, first_tool):
    value = measure.measure_episode(fixture(tmp_path, first_tool=first_tool, finish_reason="context_capacity", prepared_only=True))
    assert value["denominators"]["no_followup_reasons"] == {"context_capacity": 1}
    assert value["denominators"]["presented_in_later_actual_generation"] == 0
    gate = measure.first_block_gate(block(value))
    assert gate["passed"] is False
    assert {r["reason"] for r in gate["reasons"]} == {"input_feedback_block"}


@pytest.mark.parametrize("reason,tool", [("team_budget", "read_file"), ("voluntary_end", "staff_done"), ("waiting_without_event", "staff_wait")])
def test_normal_absent_opportunities_are_counted_and_do_not_select_by_outcome(tmp_path, reason, tool):
    value = measure.measure_episode(fixture(tmp_path, first_tool=tool, finish_reason=reason))
    assert value["denominators"]["no_followup_reasons"] == {reason: 1}
    rows = block(value)
    rows[0].update(R=1, messages=0, births=0)
    rows[1].update(R=0, messages=9, births=4)
    assert measure.first_block_gate(rows)["passed"] is True


@pytest.mark.parametrize("tamper", ["old", "feedback", "diagnostic", "permission"])
def test_old_projection_or_protected_information_change_stops_gate(tmp_path, tamper):
    value = measure.measure_episode(fixture(tmp_path, tamper=tamper))
    assert value["mechanism_gate_inputs"]["projection_violations"]
    assert measure.first_block_gate(block(value))["passed"] is False
    if tamper == "feedback":
        assert value["mechanism_gate_inputs"]["feedback_missing_from_first_actual_followup"]
    if tamper == "permission":
        assert any("unauthorized_or_changed_initial_diagnostic" in a["issues"] for a in value["projection_audit"])


def test_format_feedback_is_real_user_input_and_never_synthetic_tool_execution(tmp_path):
    value = measure.measure_episode(fixture(tmp_path, format_feedback=True))
    first = value["feedback_records"][0]
    assert first["kind"] == "format_feedback" and first["tool"] == "format_feedback"
    assert first["world_receipt_source"] is None
    assert first["presentation"]["presented_in_first_actual_followup"] is True
    assert measure.first_block_gate(block(value))["passed"] is True


def test_fault_missing_original_or_missing_block_measurement_remains_unresolved(tmp_path):
    value = measure.measure_episode(fixture(tmp_path, finish_reason="execution_fault"))
    assert value["denominators"]["no_followup_reasons"] == {"execution_fault": 1}
    assert measure.first_block_gate(block(value))["passed"] is False
    (tmp_path / "raw-transport/request-00001/original-request.json").unlink()
    missing = measure.measure_episode(tmp_path)
    assert missing["projection_audit"][0]["status"] == "unresolved"
    assert measure.first_block_gate([None, None, None, None])["reasons"][0]["reason"] == "gate_unresolved"
    assert measure.first_block_gate([missing, None, None, None])["passed"] is False

    (tmp_path / "slot-result.json").write_text("malformed JSON")
    assert measure.measure_episode(tmp_path)["mechanism_gate_inputs"]["resolved"] is False
