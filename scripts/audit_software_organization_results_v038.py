"""Read-only behavioral audit of the 24 completed frozen v038 organization slots.

Uses original world events, model outputs/tool receipts and terminal records.
Does not import the simulator, execute model/code/tests, rehash artifacts, or
reassess an unsubmitted workspace. No training or independent-confirmation data
are opened. An addressed-message input scan is made only if such events exist.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re

SOURCE = Path(__file__).resolve().parents[1]
ACTION_EVENTS = {
    "create_task": "task_created", "claim_task": "claim", "revise_task": "task_revised",
    "offer_transfer": "transfer_offered", "accept_transfer": "transfer_accepted",
    "decline_transfer": "transfer_declined", "return_task": "task_returned",
    "declare_dependency": "dependency_declared", "remove_dependency": "dependency_removed",
    "send_message": "work_message", "handoff_patch": "handoff", "spawn_member": "member_spawned",
    "retire_member": "member_retired", "fix_patch": "patch_fixed", "integrate_patch": "integrate",
    "submit_integration": "submit", "run_tests": "test",
}
ADDRESSED = {"work_message", "handoff", "transfer_offered", "transfer_accepted", "transfer_declined"}
PUBLIC_GROUPS = ("upstream_regressions", "public_normal")


def read(path):
    return json.loads(path.read_text())


def source(path, *, pointer=None, line=None):
    return {"path": str(path), **({"json_pointer": pointer} if pointer is not None else {}),
            **({"line": line} if line is not None else {})}


def event_summary(event, path, lines):
    keys = ("sequence", "actor_id", "kind", "logical_time", "action_id", "task_id", "task_snapshot",
        "previous_owner", "owner", "recipient", "body", "reason", "patch_id", "task_ids", "offer_id",
        "source_reference", "included_patch_ids", "delivery_id", "test_sequence", "conflicts",
        "changed_paths", "path", "retained_obligations", "member_id", "orphan_takeover")
    result = {key: event[key] for key in keys if key in event}
    result["source"] = source(path, pointer=f"/software_events/{event['sequence'] - 1}",
                              line=lines.get(event["sequence"]))
    if event["kind"] == "test":
        result["groups"] = {name: {k: group.get(k) for k in ("status", "executed", "passed")}
                            for name, group in event.get("groups", {}).items()}
        result["public_groups_passed"] = all(event.get("groups", {}).get(name, {}).get("passed") is True
                                               for name in PUBLIC_GROUPS)
        result["public_groups_executed"] = all(event.get("groups", {}).get(name, {}).get("executed") is True
                                                 for name in PUBLIC_GROUPS)
    return result


def brief_arguments(action, value):
    if not isinstance(value, dict):
        return {"unparsed": str(value)[:160]}
    if action in ACTION_EVENTS or action in {"staff_done", "staff_wait"}:
        return value
    return {k: value[k] for k in ("path", "patch_id", "start_line", "max_lines") if k in value}


def scan_experience(path):
    outputs, calls, controls, format_errors, boundaries = {}, [], [], [], []
    for line, raw in enumerate(path.open(), 1):
        event = json.loads(raw)
        kind, payload = event["kind"], event["payload"]
        evidence = {"experience_sequence": event["sequence"], "worker_id": event.get("worker_id"),
                    "source": source(path, line=line)}
        if kind == "model_response":
            response = payload.get("response", {})
            names = [call.get("function", {}).get("name") for choice in response.get("choices", [])
                     for call in choice.get("message", {}).get("tool_calls", [])]
            outputs[payload["call_id"]] = names or re.findall(
                r"<function=([A-Za-z_]+)>", response.get("raw_generated_text", ""))
        elif kind in {"tool_call", "harness_tool_call"}:
            response = payload.get("response", {})
            calls.append({**evidence, "kind": kind, "action": payload.get("action"),
                "arguments": brief_arguments(payload.get("action"), payload.get("arguments")),
                "model_call_id": payload.get("model_call_id"), "ok": response.get("ok"),
                "world_action_id": response.get("action_id"), "error": response.get("error")})
        elif kind == "model_control":
            controls.append({**evidence, "kind": payload["kind"], "reason": payload.get("reason"),
                             "call_id": payload.get("call_id")})
        elif kind == "model_format_error":
            format_errors.append({**evidence, "call_id": payload.get("call_id"), "reason": payload.get("reason"),
                                  "named_calls": outputs.get(payload.get("call_id"), [])})
        elif kind == "model_boundary_error":
            budget = payload.get("team_budget", {})
            boundaries.append({**evidence, **{k: payload[k] for k in (
                "type", "status", "message", "limits", "budget_kind", "opportunity_id") if k in payload},
                "budget_at_boundary": {k: budget[k] for k in ("decisions", "attempts", "charged_tokens",
                    "held_tokens", "available_tokens", "remaining_decisions", "remaining_attempts") if k in budget}})
    return {"calls": calls, "controls": controls, "format_errors": format_errors, "boundaries": boundaries,
            "model_responses": len(outputs)}


def message_visibility(folder, events, model_budget):
    addressed = [e for e in events if e["kind"] in ADDRESSED and e.get("recipient")]
    if not addressed:
        return {"addressed_events": 0, "selected_requests_scanned": 0, "events": [],
                "scope": "No addressed world message/transfer/handoff event; no recipient-input claim or unnecessary scan"}
    actual = {v.get("reservation", {}).get("preparation", {}).get("selected_request_sha256"): key
              for key, v in model_budget["records"].items() if v.get("attempt_started") and v.get("charge")}
    found = defaultdict(list)
    scans = 0
    for path in sorted((folder / "raw-transport").glob("request-*/selected-request.json")):
        projection = read(path.with_name("projection.json"))
        request_hash = projection.get("selected_request_sha256")
        if request_hash not in actual:
            continue
        scans += 1
        for index, message in enumerate(read(path).get("messages", [])):
            if message.get("role") != "user":
                continue
            try:
                observation = json.loads(message.get("content", "")).get("observation", {})
            except (TypeError, ValueError):
                continue
            for event in addressed:
                if observation.get("actor_id") != event["recipient"]:
                    continue
                rows = observation.get("messages", []) + observation.get("handoffs", [])
                rows += observation.get("transfer_offers", [])
                if any(row.get("sequence") == event["sequence"] for row in rows):
                    found[event["sequence"]].append({"source": source(path, pointer=f"/messages/{index}"),
                        "model_call_id": actual[request_hash], "selected_request_sha256": request_hash,
                        "input_ids_sha256": projection.get("input_ids_sha256")})
    return {"addressed_events": len(addressed), "selected_requests_scanned": scans,
        "events": [{"world_sequence": e["sequence"], "recipient": e["recipient"],
            "selected_occurrences": len(found[e["sequence"]]),
            "first_selected_input": next(iter(found[e["sequence"]]), None)} for e in addressed],
        "scope": "Exact actual selected input only; visibility does not establish understanding or causal response"}


def slot_audit(root, worker, unit):
    folder = root / worker / "actual/episodes" / unit["slot_id"]
    result = read(folder / "slot-result.json")
    world_path = folder / "prepared/world/control/state.json"
    raw_state = world_path.read_text()
    state = json.loads(raw_state)
    start = raw_state.index('  "software_events": [')
    offsets = {int(m[1]): raw_state.count("\n", 0, start + m.start()) + 1
               for m in re.finditer(r'^      "sequence": (\d+),?$', raw_state[start:], re.MULTILINE)}
    events = state["software_events"]
    software = state["projects"]["SOFTWARE27"]["software"]
    evidence = read(folder / "organization-evidence.json")
    runtime = read(folder / "runtime-state.json")
    experience = scan_experience(folder / "experience.jsonl")
    calls = experience["calls"]
    model_budget = result["team_budget"]["model"]
    if experience["model_responses"] != evidence["total_usage"]["attempts"]:
        raise ValueError("Unexpected response/actual-attempt count: " + unit["slot_id"])
    if result["status"] != "closed" or type(result["R"]) is not int or result["R"] not in (0, 1):
        raise ValueError("This audit requires the actual complete frozen 24-slot panel")
    def summarize(event):
        return event_summary(event, world_path, offsets)

    event_counts = Counter(e["kind"] for e in events)
    action_counts = {}
    for action, kind in ACTION_EVENTS.items():
        selected = [c for c in calls if c["action"] == action]
        malformed = sum(e["named_calls"].count(action) for e in experience["format_errors"])
        action_counts[action] = {"recorded_tool_calls": len(selected),
            "successful_tool_calls": sum(c["ok"] is True for c in selected),
            "rejected_tool_calls": sum(c["ok"] is False for c in selected),
            "format_rejected_named_calls": malformed, "world_events": event_counts[kind]}
    edits = [e for e in events if e["kind"] == "edit"]
    created = [e for e in events if e["kind"] == "task_created"]
    editors = defaultdict(set)
    for event in edits:
        editors[event["path"]].add(event["actor_id"])
    members = {}
    for member in evidence["member_lifecycle"]["registry"]:
        own = [e for e in events if e["actor_id"] == member]
        own_calls = [c for c in calls if c["worker_id"] == member]
        obj = state["workspaces"]["SOFTWARE27"][member]
        current = {"object_id": obj, "version_id": state["artifacts"][obj]["current_version"]}
        tests = [e for e in own if e["kind"] == "test"]
        fixed = [e for e in own if e["kind"] == "patch_fixed"]
        last_test = summarize(tests[-1]) if tests else None
        current_tested = bool(last_test and last_test.get("source_reference") == current)
        if not tests:
            stage = "no_executed_tests"
        elif not current_tested:
            stage = "edited_after_latest_test_current_version_untested"
        elif last_test["public_groups_passed"]:
            stage = "current_version_public_groups_passed"
        else:
            stage = "current_version_public_groups_not_all_passed"
        members[member] = {"current_workspace_reference": current,
            "latest_accepted_model_tool_call": next((c for c in reversed(own_calls) if c["ok"] is True), None),
            "latest_model_tool_call": next(iter(reversed(own_calls)), None),
            "last_edit": next((summarize(e) for e in reversed(own) if e["kind"] == "edit"), None),
            "last_test": last_test, "last_test_is_current_version": current_tested,
            "current_public_groups_passed": current_tested and last_test["public_groups_passed"],
            "public_pass_test_count": sum(all(e.get("groups", {}).get(n, {}).get("passed") is True
                for n in PUBLIC_GROUPS) for e in tests),
            "last_fixed_patch": summarize(fixed[-1]) if fixed else None,
            "last_fixed_patch_is_current_version": bool(fixed and fixed[-1].get("source_reference") == current),
            "unsubmitted_observable_stage": stage if not result["submitted"] else None,
            "terminal_detail": result["boundary"]["terminal_details"].get(member),
            "runtime_availability_at_end": runtime["availability"][member],
            "owned_tasks_at_end": [t for t, value in software["tasks"].items() if value.get("owner") == member],
            "test_fixed_submit_calls": [c for c in own_calls if c["action"] in {
                "run_tests", "fix_patch", "submit_integration"}],
            "test_fixed_submit_format_rejections": [e for e in experience["format_errors"] if e["worker_id"] == member
                and set(e["named_calls"]) & {"run_tests", "fix_patch", "submit_integration"}]}
    return {**unit, "worker": worker, "status": result["status"], "R": result["R"],
        "submitted": result["submitted"], "complete_delivery": result["complete_delivery"],
        "sources": {name: source(folder / name) for name in ("slot-result.json", "organization-evidence.json",
            "prepared/world/control/state.json", "experience.jsonl", "runtime-state.json")},
        "event_counts": dict(event_counts), "action_counts": action_counts,
        "successful_organization_and_product_events": [summarize(e) for e in events if e["kind"] in
            set(ACTION_EVENTS.values()) - {"test"}],
        "task_formation": {"first_edit_sequence": edits[0]["sequence"] if edits else None,
            "first_task_sequence": created[0]["sequence"] if created else None,
            "first_edit_before_first_task": bool(edits and created and edits[0]["sequence"] < created[0]["sequence"]),
            "terminal_tasks": software["tasks"], "terminal_transfer_offers": software["transfer_offers"]},
        "overlap": {"editors_by_path": {p: sorted(v) for p, v in sorted(editors.items())},
            "overlapping_production_paths": [p for p, v in sorted(editors.items()) if len(v) >= 2 and p != "test_member.py"],
            "members_with_successful_edit": sorted({e["actor_id"] for e in edits}),
            "scope": "Same path modified by at least two members; neutral overlap, not automatically wasted work"},
        "members": members, "lifecycle": {k: evidence["member_lifecycle"][k] for k in (
            "initial_members", "cumulative_births", "live_at_end", "peak_live", "actual_output_participants",
            "participating_members", "live_count_trajectory")},
        "controls": experience["controls"], "format_rejections": experience["format_errors"],
        "world_tool_rejections": [c for c in calls if c["ok"] is False],
        "boundary_events": experience["boundaries"],
        "boundary": {k: result["boundary"].get(k) for k in ("status", "role_stops", "waiting_members",
            "terminal_details", "closure_reason", "execution_integrity_failure")},
        "budget": {k: model_budget[k] for k in ("limits", "decisions", "attempts", "charged_tokens",
            "available_tokens", "remaining_decisions", "remaining_attempts")},
        "test_budget": {k: result["team_budget"]["tests"][k] for k in ("limit", "used", "remaining")},
        "usage": result["usage"], "usage_by_member": result["usage_by_member"],
        "message_visibility": message_visibility(folder, events, model_budget),
        "interpretation": "Latest tests are existing finite public observations only. No hidden assessment of unsubmitted mutable code; budget stop is an observed boundary, not the unique cause of failure. Registry live does not mean runnable after episode closure."}


def aggregate(rows):
    out = {}
    for condition in ("O1", "O2", "O3", "all"):
        group = [r for r in rows if condition == "all" or r["condition"] == condition]
        counts, stop_counts, controls = Counter(), Counter(), Counter()
        for r in group:
            counts.update(r["event_counts"])
            stop_counts.update(m["terminal_detail"]["cause"] for m in r["members"].values())
            controls.update(c["kind"] for c in r["controls"])
        unsubmitted = [r for r in group if not r["submitted"]]
        stages = Counter(m["unsubmitted_observable_stage"] for r in unsubmitted for m in r["members"].values())
        out[condition] = {"episodes": len(group), "successes": sum(r["R"] for r in group),
            "submitted": sum(r["submitted"] for r in group), "unsubmitted": len(unsubmitted),
            "event_counts": dict(counts), "action_counts": {action: {field: sum(r["action_counts"][action][field]
                for r in group) for field in next(iter(group))["action_counts"][action]} for action in ACTION_EVENTS},
            "control_counts": dict(controls), "member_stop_causes": dict(stop_counts),
            "episodes_with_context_boundary": sum(any(m["terminal_detail"]["cause"] == "context_capacity"
                for m in r["members"].values()) for r in group),
            "episodes_with_budget_boundary": sum(any(m["terminal_detail"]["cause"] == "team_budget_exhausted"
                for m in r["members"].values()) for r in group),
            "slots_with_created_tasks": sum(bool(r["task_formation"]["terminal_tasks"]) for r in group),
            "submitted_slots_without_tasks": sum(r["submitted"] and not r["task_formation"]["terminal_tasks"] for r in group),
            "fixed_patches_without_task_binding": sum(e["kind"] == "patch_fixed" and e.get("task_ids") == []
                for r in group for e in r["successful_organization_and_product_events"]),
            "unsubmitted_fixed_patch_attempts": sum(r["action_counts"]["fix_patch"]["recorded_tool_calls"] for r in unsubmitted),
            "unsubmitted_submit_attempts": sum(r["action_counts"]["submit_integration"]["recorded_tool_calls"] for r in unsubmitted),
            "slots_edit_before_task_creation": sum(r["task_formation"]["first_edit_before_first_task"] for r in group),
            "slots_with_overlapping_production_edits": sum(bool(r["overlap"]["overlapping_production_paths"]) for r in group),
            "actual_output_participant_count_sum": sum(r["lifecycle"]["actual_output_participants"] for r in group),
            "live_at_end_sum": sum(r["lifecycle"]["live_at_end"] for r in group),
            "member_unsubmitted_stages": dict(stages),
            "unsubmitted_with_any_current_public_pass_member": sum(any(m["current_public_groups_passed"]
                for m in r["members"].values()) for r in unsubmitted),
            "unsubmitted_with_any_public_pass_test": sum(any(m["public_pass_test_count"]
                for m in r["members"].values()) for r in unsubmitted),
            "format_rejected_outputs": sum(len(r["format_rejections"]) for r in group),
            "rejected_world_tool_calls": sum(len(r["world_tool_rejections"]) for r in group)}
    return out


def cases(rows):
    selected = {
        "org-r0-O1-s0": "Direct unbound patch and accepted final delivery without creating any execution task",
        "org-r1-O3-s0": "Only task creation/claim in the whole panel; late self-assignment but no fixed patch or submission",
        "org-r2-O3-s0": "Peer patch integration after first member's delivery/retirement, conflicts, later final delivery",
        "org-r2-O2-s1": "Four output participants but one first-decision done; concentrated successful delivery and side-branch integration",
    }
    return [{"slot_id": row["slot_id"], "selection_reason": selected[row["slot_id"]],
             "key_events": row["successful_organization_and_product_events"], "controls": row["controls"],
             "latest_member_tests": {m: {"last_test": value["last_test"],
                 "last_test_is_current_version": value["last_test_is_current_version"]}
                 for m, value in row["members"].items()},
             "rejected_publication_attempts": [call for call in row["world_tool_rejections"]
                 if call["action"] in {"fix_patch", "submit_integration"}],
             "R": row["R"], "submitted": row["submitted"], "scope": "Purpose-selected illustrations, not randomly selected causal comparisons"}
            for row in rows if row["slot_id"] in selected]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SOURCE / "runs/software-organization-v038")
    parser.add_argument("--output", type=Path, default=SOURCE / "runs/v038-report-controls/organization-audit.json")
    args = parser.parse_args()
    root = args.root.resolve()
    plan = read(root / "plan.json")
    rows = [slot_audit(root, worker, unit) for worker, units in plan["assignments"].items() for unit in units]
    if len(rows) != 24 or len({r["slot_id"] for r in rows}) != 24:
        raise ValueError("Audit retains exactly the original 24 unique inventory slots")
    result = {"version": "software-organization-results-audit-v0.38", "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_plan": source(root / "plan.json"), "root": str(root), "aggregate": aggregate(rows),
        "rows": rows, "representative_cases": cases(rows), "model_calls": 0, "gpu_used": False,
        "new_test_or_acceptance_executions": 0, "artifact_rehashes": 0,
        "scope": "Read-only audit of the original 24 v038 organization-development slots. No completion claims from model prose; exact current-version tests, actual calls and original terminal causes kept separate.",
        "counting": {"recorded_tool_calls": "Actual runtime tool receipts, including rejects; excludes syntax/schema-rejected outputs before execution",
            "format_rejected_named_calls": "Named native calls or native function tags in format-rejected model output; reported separately, not world execution",
            "world_retirement_events": "Includes runtime retirement caused by staff_done; distinct from model-issued retire_member tool calls",
            "participants": "Members with actual output tokens, including control-only output; not a count of productive contributors",
            "live_at_end": "Original registry live state; budget/context-stopped live members are no longer runnable",
            "overlap": "At least two members edited the same production path; no automatic waste or causal label"}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["aggregate"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
