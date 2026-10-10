"""Finite archived JSON/page controls; no real tokenizer, model or business execution."""
import copy
import json

import pytest

from proworksim.software_context_v041 import deduplicate_static_snapshots
from proworksim.software_organization_v042 import READ_TEST_RESULT_TOOL, build_test_report, test_result_page as report_page
from proworksim.storage import digest, json_bytes
from scripts import measure_organization_feedback_v042 as measure


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def fixture(root, actions, *, end_reason="voluntary_end", tamper=None, prepared_only=False):
    members = sorted({action.get("member", "member_001") for action in actions})
    initial_ref = {"object_id": "baseline", "version_id": "v1"}
    initial = {"diagnostic_id": "case:initial", "origin": "environment_initial_diagnostic", "initial_report": True,
        "source_reference": initial_ref, "initial_source_reference": initial_ref, "files_sha256": "initial-files",
        "executed": True, "passed": False, "tests": [{"test_id": "initial", "passed": False, "request": 1, "observed": 1, "expected": 2}]}
    histories = {member: [{"role": "system", "content": "Use declared tools."}] for member in members}
    versions = dict.fromkeys(members, 1)
    reports, ordered_reports, world_events, events, records, originals = {}, [], [], [], {}, []
    first_test = None
    for number, action in enumerate(actions, 1):
        member, tool = action.get("member", "member_001"), action["tool"]
        call_id, tool_id = f"call-{number}", f"native-{number}"
        obs = {"world_id": "world", "instance_id": "instance", "branch_id": "branch", "project_id": "SOFTWARE27",
            "actor_id": member, "interface_revision": measure.PAGE_INTERFACE,
            "workspace_reference": {"object_id": "workspace-" + member, "version_id": "v" + str(versions[member])},
            "contract": "Produce the requested behavior.", "root_goal": {"task_id": "root_goal", "description": "Produce the requested behavior."},
            "initial_diagnostics": [initial], "team_model_budget": {"remaining_attempts": 129 - number}, "tasks": {}}
        original = {"max_tokens": 2048, "tools": [{"type": "function", "function": READ_TEST_RESULT_TOOL}],
            "messages": [*copy.deepcopy(histories[member]), {"role": "user", "content": json.dumps({"role_task": "Read exact saved pages if useful.", "observation": obs})}]}
        selected, deduplication = deduplicate_static_snapshots(original)
        pairs = [[i, i + 1] for i, msg in enumerate(original["messages"]) if msg.get("role") == "assistant" and msg.get("tool_calls")]
        kept = list(range(len(original["messages"])))
        if tamper == "drop_current_page" and number == 2:
            kept = [i for i in kept if i not in pairs[-1]]
            selected["messages"] = [msg for i, msg in enumerate(selected["messages"]) if i in kept]
        projection = {"version": measure.PROJECTION_VERSION, "fits": True, "context_limit": 16384,
            "reserved_output_tokens": 2048, "selected_prompt_tokens": 2000 + number,
            "original_request_sha256": digest(json_bytes(original)), "selected_request_sha256": digest(json_bytes(selected)),
            "input_ids_sha256": "input-" + str(number), "selected_indices": kept,
            "removed_indices": [i for i in range(len(original["messages"])) if i not in kept],
            "complete_tool_rounds": pairs, "latest_complete_round_preserved": pairs[-1] if pairs else None,
            "protected_prompt_tokens": 1800, "protected_request_sha256": "protected-request",
            "protected_input_ids_sha256": "protected-ids", "protected_rendered_prompt_sha256": "protected-render",
            "deduplication": deduplication}
        folder = root / "raw-transport" / f"request-{number:05d}"
        save(folder / "original-request.json", original)
        save(folder / "selected-request.json", selected)
        save(folder / "projection.json", projection)
        records[call_id] = {"member": member, "attempt_started": True, "status": "settled",
            "reservation": {"preparation": {key: projection[key] for key in
                ("original_request_sha256", "selected_request_sha256", "input_ids_sha256")}
                | {"prompt_tokens": 2000 + number}},
            "charge": {"reported_usage": {"prompt_tokens": 2000 + number, "completion_tokens": 10, "total_tokens": 2010 + number}}}
        originals.append({"call_id": call_id, "status": "success", "original_output_present": True,
            "experience_sequence": number * 10, "input_ids_sha256": "input-" + str(number)})
        args, action_id = {}, "action-" + str(number)
        source_ref = copy.deepcopy(obs["workspace_reference"])
        if tool == "run_tests":
            test_seq = len(world_events) + 1
            operation = "operation-" + str(number)
            visible = {"source_reference": source_ref, "files_sha256": "files-" + source_ref["version_id"],
                "executed": True, "passed": False, "scope": "Original public checks only.", "untested": ["independent_acceptance"],
                "independent_acceptance": "not_run", "fixed_submission_is_acceptance": False,
                "groups": {"public_normal": {"executed": True, "passed": False,
                    "tests": [{"test_id": "long-unicode-entry", "passed": False, "request": {"name": "visible"},
                               "observed": "界🙂é" * 2300, "expected": "precise expected value"}]},
                    "upstream_regressions": {"executed": True, "passed": True, "tests": [{"test_id": "upstream", "passed": True}]}}}
            identity = {key: obs[key] for key in ("world_id", "instance_id", "branch_id", "project_id", "actor_id")}
            identity.update(test_event_sequence=test_seq, operation_id=operation)
            report = build_test_report(visible, actor_id=member, event_identity=identity)
            reports[report["report_id"]] = report
            ordered_reports.append(report)
            world_events.append({"sequence": test_seq, "kind": "test", "actor_id": member, "action_id": action_id,
                "operation_id": operation, "source_reference": source_ref, "groups": visible["groups"]})
            first_test = first_test or test_seq
            world_events.append({"sequence": test_seq + 1, "kind": "test_report_saved", "actor_id": member,
                "action_id": action_id, "report_id": report["report_id"], "test_event_sequence": test_seq,
                "body_sha256": report["body_sha256"], "source_reference": source_ref})
            result = report_page(report)
            response = {"ok": True, "result": result, "action_id": action_id}
        elif tool == "read_test_result":
            report = ordered_reports[action.get("report", 0)]
            page = report["pages"][action.get("page", 1)]
            args = {"report_id": report["report_id"], "cursor": page["cursor"]}
            if member != report["actor_id"] and tamper != "permission":
                response = {"ok": False, "error": {"code": "test_report_not_readable", "message": "No report is readable by this member"}, "action_id": action_id}
            else:
                response = {"ok": True, "result": report_page(report, page["cursor"]), "action_id": action_id}
                world_events.append({"sequence": len(world_events) + 1, "kind": "test_report_page_read", "actor_id": member,
                    "action_id": action_id, "report_id": report["report_id"], "page_index": page["index"], "test_rerun": False})
        else:
            if tool == "write_file":
                versions[member] += 1
                source_ref["version_id"] = "v" + str(versions[member])
                args = {"path": "product.py", "text": "member edit"}
                world_events.append({"sequence": len(world_events) + 1, "kind": "edit", "actor_id": member,
                                     "source_reference": source_ref, "action_id": action_id, "path": "product.py"})
            if tool == "submit_integration":
                world_events.append({"sequence": len(world_events) + 1, "kind": "submit", "actor_id": member,
                    "source_reference": source_ref, "action_id": action_id, "delivery_id": "fixed-1", "test_sequence": first_test})
            response = {"ok": True, "result": {"source_reference": source_ref}, "action_id": action_id}
        if tool == "run_tests" and tamper == "page_text":
            response["result"]["page"]["text"] = "changed current page"
        if tool == "read_test_result" and response["ok"] and tamper == "version":
            response["result"]["source_reference"] = {"object_id": "workspace-" + member, "version_id": "v999"}
        decision = {"action": tool, "arguments": args, "model_call_id": call_id, "model_tool_call_id": tool_id,
                    "kind": "done" if tool == "staff_done" else "wait" if tool == "staff_wait" else "act"}
        events.extend([
            {"sequence": number * 10 + 1, "kind": "policy_decision", "worker_id": member, "payload": {"decision": decision}},
            {"sequence": number * 10 + 2, "kind": "tool_call", "worker_id": member,
             "payload": {**decision, "response": response}},
            {"sequence": number * 10 + 3, "kind": "model_tool_result", "worker_id": member,
             "payload": {"call_id": call_id, "model_tool_call_id": tool_id, "world_response": response,
                         "message": {"role": "tool", "tool_call_id": tool_id, "content": json.dumps(response)}}},
        ])
        if tool in {"staff_done", "staff_wait"}:
            events.append({"sequence": number * 10 + 4, "kind": "model_control", "worker_id": member,
                           "payload": {"kind": "done" if tool == "staff_done" else "wait", "call_id": call_id}})
        histories[member] = [*original["messages"], {"role": "assistant", "content": "", "tool_calls": [{"id": tool_id,
            "type": "function", "function": {"name": tool, "arguments": json.dumps(args)}}]},
            {"role": "tool", "tool_call_id": tool_id, "content": json.dumps(response)}]
    terminal = {member: {"status": "completed", "cause": "completed"} for member in members}
    boundary = {"terminal_details": terminal, "role_stops": dict.fromkeys(members, "completed"), "waiting_members": {}}
    if end_reason == "context_capacity":
        member = actions[-1].get("member", "member_001")
        terminal[member].update(status="model_budget_exhausted", cause="context_capacity", generation_started=False)
        boundary["role_stops"][member] = "model_budget_exhausted"
        events.append({"sequence": 10 * len(actions) + 5, "kind": "model_boundary_error", "worker_id": member,
                       "payload": {"budget_kind": "context_capacity"}})
        records["rejected"] = {"member": member, "attempt_started": False, "status": "admission_rejected", "budget_kind": "context_capacity"}
        if prepared_only:
            save(root / "raw-transport/request-99999/selected-request.json", {"messages": histories[member]})
            save(root / "raw-transport/request-99999/projection.json", {"selected_request_sha256": "unstarted", "input_ids_sha256": "unstarted"})
    elif end_reason == "team_budget":
        boundary["closure_reason"] = "shared_team_pool_exhausted"
        for value in terminal.values():
            value.update(status="team_budget_exhausted", cause="shared_team_pool_exhausted")
        boundary["role_stops"] = dict.fromkeys(members, "team_budget_exhausted")
    elif end_reason == "waiting_without_event":
        boundary.update(role_stops={}, waiting_members=dict.fromkeys(members, 1))
        for value in terminal.values():
            value.update(status="worker_waiting", cause="no_reachable_wake_event")
    if tamper == "archive":
        ordered_reports[0]["body"] += "corrupted after save"
    save(root / "prepared/world/control/state.json", {"projects": {"SOFTWARE27": {"software": {
        "initial_diagnostics": {initial["diagnostic_id"]: initial}, "initial_diagnostic_assignments": {member: [initial["diagnostic_id"]] for member in members},
        "test_reports": reports}}}, "software_events": world_events})
    save(root / "organization-evidence.json", {"original_attempts": originals})
    save(root / "slot-result.json", {"slot_id": root.name, "status": "closed", "R": 0, "boundary": boundary,
                                    "team_budget": {"model": {"records": records}}})
    (root / "experience.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n")
    return root


def block(value):
    return [{**copy.deepcopy(value), "slot_id": f"catalog-block-{index}"} for index in range(4)]


def test_report_storage_directory_pages_and_historical_union_are_separate(tmp_path):
    value = measure.measure_episode(fixture(tmp_path, [
        {"tool": "run_tests"}, {"tool": "read_test_result", "page": 1},
        {"tool": "write_file"}, {"tool": "read_test_result", "page": 1}, {"tool": "staff_done"}]))
    assert value["measurement_gaps"] == []
    report = value["report_histories"][0]
    assert report["status"] == "verified" and report["directory_presented_in_actual_generation"] is True
    assert report["coverage"]["historically_fully_presented"] is False
    assert report["coverage"]["historically_presented_characters"] == report["coverage"]["historically_presented_intervals"][0][1]
    assert report["coverage"]["page_returns_later_presented"] == 3
    assert report["actual_page_read_requests"] == 2
    assert report["page_read_reported_usage"]["total_tokens"] == 2012 + 2014
    assert report["coverage"]["presentation_occurrences"] > 3
    assert report["source_reference"]["version_id"] == "v1"
    assert all(row["report_page"]["source_reference"]["version_id"] == "v1" for row in value["feedback_records"] if row.get("report_page"))
    assert measure.first_block_gate(block(value))["passed"] is True


def test_equal_bodies_from_independent_events_never_combine_coverage(tmp_path):
    value = measure.measure_episode(fixture(tmp_path, [
        {"tool": "run_tests"}, {"tool": "run_tests"},
        {"tool": "read_test_result", "report": 0, "page": 1},
        {"tool": "read_test_result", "report": 1, "page": 2}, {"tool": "staff_done"}]))
    left, right = value["report_histories"]
    assert left["body_sha256"] == right["body_sha256"]
    assert left["report_id"] != right["report_id"] and left["report_event"] != right["report_event"]
    assert left["coverage"]["historically_presented_intervals"] != right["coverage"]["historically_presented_intervals"]
    assert not left["coverage"]["historically_fully_presented"] and not right["coverage"]["historically_fully_presented"]
    assert measure.first_block_gate(block(value))["passed"] is True


def test_stored_report_and_unstarted_input_do_not_count_as_directory_or_page_seen(tmp_path):
    value = measure.measure_episode(fixture(tmp_path, [{"tool": "run_tests"}], end_reason="context_capacity", prepared_only=True))
    report = value["report_histories"][0]
    assert report["status"] == "verified"
    assert report["directory_presented_in_actual_generation"] is False
    assert report["coverage"]["historically_presented_characters"] == 0
    assert report["continuation"]["reason"] == "context_capacity"
    assert any(row["reason"] == "input_feedback_block" for row in measure.first_block_gate(block(value))["reasons"])


@pytest.mark.parametrize("tool,reason", [("staff_done", "voluntary_end"), ("staff_wait", "waiting_without_event"), ("write_file", "not_requested")])
def test_not_reading_all_pages_is_a_choice_and_never_a_gate_criterion(tmp_path, tool, reason):
    end = "waiting_without_event" if tool == "staff_wait" else "voluntary_end"
    value = measure.measure_episode(fixture(tmp_path, [{"tool": "run_tests"}, {"tool": tool}], end_reason=end))
    assert value["report_histories"][0]["coverage"]["historically_fully_presented"] is False
    assert value["report_histories"][0]["continuation"]["reason"] == reason
    rows = block(value)
    rows[0].update(R=1, messages=0, pages_read=0, births=0)
    rows[1].update(R=0, messages=9, pages_read=100, births=4)
    assert measure.first_block_gate(rows)["passed"] is True


def test_team_budget_is_not_a_context_page_defect(tmp_path):
    value = measure.measure_episode(fixture(tmp_path, [{"tool": "run_tests"}], end_reason="team_budget"))
    assert value["report_histories"][0]["continuation"]["reason"] == "team_budget"
    assert value["report_histories"][0]["coverage"]["historically_presented_characters"] == 0
    assert measure.first_block_gate(block(value))["passed"] is True


@pytest.mark.parametrize("tamper", ["page_text", "version", "archive", "drop_current_page"])
def test_body_version_archive_or_current_page_loss_is_mechanical_failure(tmp_path, tamper):
    value = measure.measure_episode(fixture(tmp_path, [{"tool": "run_tests"}, {"tool": "read_test_result"}, {"tool": "staff_done"}], tamper=tamper))
    assert measure.first_block_gate(block(value))["passed"] is False
    if tamper == "drop_current_page":
        assert value["mechanism_gate_inputs"]["feedback_missing_from_first_actual_followup"]
    else:
        assert value["mechanism_gate_inputs"]["page_protocol_violations"]


@pytest.mark.parametrize("leak", [False, True])
def test_report_id_is_not_partner_permission_but_correct_rejection_is_allowed(tmp_path, leak):
    value = measure.measure_episode(fixture(tmp_path, [{"tool": "run_tests"},
        {"tool": "read_test_result", "member": "member_002"}, {"tool": "staff_done", "member": "member_002"},
        {"tool": "staff_done"}], tamper="permission" if leak else None))
    read = next(row for row in value["feedback_records"] if row["tool"] == "read_test_result")
    assert read["report_page"]["page_actual_inputs"] == []
    assert measure.first_block_gate(block(value))["passed"] is (not leak)
    if not leak:
        assert read["report_page"]["status"] == "request_rejected_without_page"


def test_partial_report_can_relate_to_fixed_delivery_without_full_read_or_use_claim(tmp_path):
    value = measure.measure_episode(fixture(tmp_path, [{"tool": "run_tests"}, {"tool": "submit_integration"}, {"tool": "staff_done"}]))
    report = value["report_histories"][0]
    assert report["coverage"]["historically_fully_presented"] is False
    relation = report["subsequent_work_and_fixed_delivery"][0]["final_fixed_relation"]
    assert relation["status"] == "exact_test_version_bound_to_fixed_delivery"
    assert relation["semantic_use"] == "not_inferred"
    assert measure.first_block_gate(block(value))["passed"] is True
    assert measure.first_block_gate([None, None, None, None])["passed"] is False
