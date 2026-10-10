"""Finite lifecycle evidence controls; no world, tokenizer, model or acceptance."""
import copy
import json

import pytest

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_work_v044 as measure
from test_organization_work_v040 import fixture, save


def archive(root, *, form="native", chain=False):
    fixture(root, variant="positive" if chain else "unchanged")
    state_path = root / "prepared/world/control/state.json"
    state = json.loads(state_path.read_text())
    state.update(world_id="world", instance_id="instance", branch_id="branch")
    member, cid, action, operation = "member_001", "done-call", "action-10", "operation-10"
    reason, window, opportunity = "No further work", "organization-v044:fixture", "staff-opportunity-test-10"
    identity = {"adapter_sha256": "frozen-actor"}
    arguments = {"reason": reason}
    tool_id = "done-tool" if form == "native" else "control-" + cid
    message = {"role": "assistant", "content": ""}
    if form == "native":
        message["tool_calls"] = [{"id": tool_id, "type": "function",
            "function": {"name": "staff_done", "arguments": json.dumps(arguments)}}]
    else:
        message["content"] = json.dumps({"kind": "done", "reason": reason})
    body = {"id": "done-response", "actor_identity": identity, "online_window_id": window,
        "protocol_parse_error": None, "choices": [{"message": message}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
    raw = root / "raw-transport/request-00010"
    raw.mkdir()
    selected = {"messages": [{"role": "user", "content": json.dumps({"observation": {
        "actor_id": member, "world_id": "world", "instance_id": "instance", "branch_id": "branch",
        "project_id": "SOFTWARE27", "logical_time": 10}})}]}
    (raw / "selected-request.json").write_bytes(json_bytes(selected))
    selected_sha, body_sha = digest(json_bytes(selected)), digest(json_bytes(body))
    save(raw / "projection.json", {"selected_request_sha256": selected_sha, "input_ids_sha256": "input-done"})
    save(raw / "response.json", {"http_status": 200, "body": body})
    result = json.loads((root / "slot-result.json").read_text())
    budget = result["team_budget"]["model"]
    budget["binding"] = {"window_id": window, "actor_identity": identity}
    budget["records"][cid] = {"call_id": cid, "member": member, "attempt_started": True, "status": "settled",
        "reservation": {"preparation": {"selected_request_sha256": selected_sha, "input_ids_sha256": "input-done",
            "window_id": window, "actor_identity": identity}},
        "charge": {"reported_usage": body["usage"], "response_id": body["id"], "response_body_sha256": body_sha}}
    evidence = json.loads((root / "organization-evidence.json").read_text())
    evidence["original_attempts"].append({"call_id": cid, "worker_id": member, "status": "success",
        "original_output_present": True, "experience_sequence": 100, "input_ids_sha256": "input-done",
        "response_id": body["id"], "response_body_sha256": body_sha, "usage": body["usage"]})
    save(root / "organization-evidence.json", evidence)
    control_output = {"ok": True, "worker_state": "done", "reason": reason, "world_effect": False}
    association = {"model_call_id": cid, "model_tool_call_id": tool_id, "decision_id": cid}
    added = [
        ("model_response", {"call_id": cid, "response": body, "opportunity_id": opportunity}),
        ("policy_decision", {"decision": {"kind": "done", "action": "staff_done", "arguments": arguments, **association}}),
        ("harness_tool_call", {"action": "staff_done", "arguments": arguments, "response": control_output,
            "opportunity_id": opportunity, **association}),
        ("model_tool_result", {"call_id": cid, "model_tool_call_id": tool_id, "world_response": control_output,
            "message": {"role": "tool", "tool_call_id": tool_id, "content": json.dumps(control_output)}}),
        ("model_control", {"call_id": cid, "decision_id": cid, "worker_id": member, "kind": "done",
            "reason": reason, "world_action_executed": False, "weight_identity": identity, "opportunity_id": opportunity}),
    ]
    if form == "json":
        added.insert(1, ("harness_explicit_json_control", {"call_id": cid, "decision_id": cid,
            "original_response_id": body["id"], "original_response_sha256": body_sha,
            "parsed_control": {"kind": "done", "reason": reason}, "native_tool_call": False}))
    with (root / "experience.jsonl").open("a") as stream:
        for index, (kind, payload) in enumerate(added, 101):
            stream.write(json.dumps({"sequence": index, "kind": kind, "worker_id": member, "payload": payload}) + "\n")
    outcome = {"worker_id": member, "status": "completed", "reason": reason, "action_performed": False}
    opportunities = [{} for _ in range(9)] + [outcome]
    (root / "runtime-opportunities.jsonl").write_text("\n".join(json.dumps(x) for x in opportunities) + "\n")
    result["boundary"] = {"outcomes": opportunities}
    save(root / "slot-result.json", result)
    event = {"kind": "member_retired", "sequence": 10, "actor_id": member, "member_id": member,
        "action_id": action, "operation_id": operation, "logical_time": 10,
        "reason": "staff_done: " + reason, "retained_obligations": []}
    state["software_events"].append(event)
    actual_result = {"member_id": member, "status": "retired", "retained_obligations": []}
    state["interactions"] = [{"action_id": action, "actor_id": member, "action": "project_action",
        "inputs": {"tool": "retire_member", "arguments": {"reason": event["reason"]}, "project_id": "SOFTWARE27"},
        "output": {"ok": True, "result": actual_result}, "transition_id": operation}]
    state["operation_commits"] = {operation: {"operation_id": operation, "bound_actor": member,
        "receipt": {"contract": "retire_member"}, "public_result": {"ok": True, "result": actual_result,
            "command_committed": True, "command_id": operation, "action_id": action}}}
    state["projects"]["SOFTWARE27"]["software"]["registry"][member].update(status="retired",
        retirement_sequence=10, retirement_reason=event["reason"])
    save(state_path, state)
    return root


def rewrite_experience(root, change):
    path = root / "experience.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    change(rows)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")


@pytest.mark.parametrize("form", ["native", "json"])
def test_actual_done_control_closes_only_lifecycle_gap_and_preserves_originals(tmp_path, form):
    root = archive(tmp_path, form=form)
    old = measure.previous.measure_episode(root)
    assert old["has_evidenced_cross_member_chain"] is None
    paths = list(root.rglob("*.json")) + list(root.rglob("*.jsonl"))
    before = {str(p): digest(p.read_bytes()) for p in paths}
    actual = measure.measure_episode(root)
    assert actual["has_evidenced_cross_member_chain"] is False
    assert actual["recorded_R"] == old["recorded_R"] == 1
    assert actual["measurement_gaps"] == []
    assert actual["lifecycle_attribution"]["prior_measurement"]["has_evidenced_cross_member_chain"] is None
    assert len(actual["lifecycle_attribution"]["bindings"]) == 1
    assert actual["member_work"]["member_001"]["actual_event_counts"]["member_retired"] == 1
    assert before == {str(p): digest(p.read_bytes()) for p in paths}


@pytest.mark.parametrize("source", ["system_timeout", "administrator", "scheduler"])
def test_non_model_retirement_cannot_become_staff_done_even_with_same_reason(tmp_path, source):
    root = archive(tmp_path)
    path = root / "prepared/world/control/state.json"
    state = json.loads(path.read_text())
    state["software_events"][-1]["origin"] = source
    save(path, state)
    actual = measure.measure_episode(root)
    assert actual["lifecycle_attribution"]["bindings"] == []
    assert actual["has_evidenced_cross_member_chain"] is None


@pytest.mark.parametrize("change", ["missing_receipt", "invented_tool_id"])
def test_json_done_requires_original_explicit_control_receipt_and_sdk_identity(tmp_path, change):
    root = archive(tmp_path, form="json")
    def mutate(rows):
        if change == "missing_receipt":
            rows.remove(next(x for x in rows if x["kind"] == "harness_explicit_json_control"))
        else:
            next(x for x in rows if x["kind"] == "policy_decision")["payload"]["decision"]["model_tool_call_id"] = "invented"
    rewrite_experience(root, mutate)
    actual = measure.measure_episode(root)
    assert actual["lifecycle_attribution"]["bindings"] == []
    assert actual["has_evidenced_cross_member_chain"] is None


@pytest.mark.parametrize("mismatch", ["missing_control", "actor", "call", "action", "window", "uncommitted",
                                      "scheduled_timeout", "response", "ambiguous_control", "input_time"])
def test_missing_or_conflicting_links_remain_unknown(tmp_path, mismatch):
    root = archive(tmp_path)
    if mismatch in {"missing_control", "actor", "call", "ambiguous_control"}:
        def change(rows):
            control = next(x for x in rows if x["kind"] == "model_control")
            if mismatch == "missing_control":
                rows.remove(control)
            elif mismatch == "actor":
                control["worker_id"] = "member_002"
            elif mismatch == "call":
                control["payload"]["call_id"] = "another-call"
            else:
                rows.append(copy.deepcopy(control))
        rewrite_experience(root, change)
    elif mismatch in {"action", "uncommitted", "input_time"}:
        path = root / "prepared/world/control/state.json"
        state = json.loads(path.read_text())
        if mismatch == "action":
            state["interactions"][0]["action_id"] = "another-action"
        elif mismatch == "input_time":
            state["software_events"][-1]["logical_time"] += 1
        else:
            state["operation_commits"]["operation-10"]["public_result"]["command_committed"] = False
        save(path, state)
    elif mismatch == "window":
        path = root / "slot-result.json"
        result = json.loads(path.read_text())
        result["team_budget"]["model"]["binding"]["window_id"] = "organization-v044:other-slot"
        save(path, result)
    elif mismatch == "response":
        rewrite_experience(root, lambda rows: next(x for x in rows if x["kind"] == "harness_tool_call")["payload"]["response"].update(ok=False))
    else:
        path = root / "runtime-opportunities.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[-1]["status"] = "system_timeout"
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    actual = measure.measure_episode(root)
    assert actual["has_evidenced_cross_member_chain"] is None
    assert actual["lifecycle_attribution"]["bindings"] == []
    assert actual["measurement_gaps"]


def test_valid_lifecycle_does_not_erase_an_independent_gap_or_existing_chain(tmp_path):
    root = archive(tmp_path / "gap")
    path = root / "raw-transport/request-00001/selected-request.json"
    path.unlink()
    actual = measure.measure_episode(root)
    assert len(actual["lifecycle_attribution"]["bindings"]) == 1
    assert actual["has_evidenced_cross_member_chain"] is None
    assert actual["measurement_gaps"]
    positive = measure.measure_episode(archive(tmp_path / "positive", chain=True))
    assert positive["has_evidenced_cross_member_chain"] is True
    assert len(positive["program_work_chains"]) == 1
