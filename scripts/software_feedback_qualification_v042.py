"""v042 P0-B/C: exact report pages and complete SDK feedback routes on CPU.

No weights or sampler are loaded. Explicit private-program actions exercise the
same SDK and v040 business world through the new paged feedback interface.
Every native request is encoded with the original tokenizer. Selected requests
must fit 14336 prompt tokens; protected requests must fit 13312. The latter is
a separate engineering qualification, never a fake SDK admission rejection.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

from proworksim.software_context_replay_v042 import (
    DEFAULT_PLAN, load_native_measurement, measure_request, reference,
)
from proworksim.software_context_v028 import BUDGET_PREPARATION_VERSION
from proworksim.software_context_v034 import observation_messages
from proworksim.software_organization_tasks_v040 import reference_solution
from proworksim.software_organization_v040 import ROOT_GOAL_ID
from proworksim.software_organization_v042 import (
    CASE_IDS, CONDITIONS, MEMBERS, PAGE_BODY_CHARACTERS,
    build_software_collaboration_case, case_spec, material,
)
from proworksim.storage import atomic_write, digest, json_bytes

VERSION = "software-feedback-route-qualification-v0.42"
SOURCE = Path(__file__).resolve().parents[1]
CORE_REQUIRED_STAGES = frozenset({"initial_request", "after_read_file", "after_failed_public_tests",
    "after_failed_report_complete", "after_repair", "after_passed_public_tests",
    "after_passed_report_complete", "after_fix_patch", "after_submit_integration"})
REPRESENTATIVES = ("largest_legal_read", "repair_diff", "message_4000", "format_rejection",
                   "task_growth_4", "newborn")
REPRESENTATIVE_REQUIRED_STAGES = {
    "largest_legal_read": {"initial_request", "after_largest_legal_read"},
    "repair_diff": {"initial_request", "before_maximum_diff_page", "after_maximum_diff_page"},
    "message_4000": {"initial_request", "peer_send_maximum_message",
        "message_enters_recipient_observation", "after_exact_message_read"},
    "format_rejection": {"initial_request", "after_actual_format_rejection", "after_format_recovery_read"},
    "task_growth_4": {"initial_request", "after_task_growth_1", "after_task_growth_2",
        "after_task_growth_3", "after_four_task_state_growth"},
    "newborn": {"initial_request", "newborn_initial_request", "newborn_after_read_file"},
}
PAGINATION_COMBINATIONS = ("long_item_event_cursor_permissions", "test_with_format_feedback",
                          "later_page_with_four_tasks", "newborn_own_report_pages")
PAGINATION_REQUIRED_STAGES = {
    "long_item_event_cursor_permissions": {"initial_request", "long_item_test", "same_content_second_test",
        "repeat_middle_page", "repeat_final_page", "edit_after_report", "old_cursor_after_edit",
        "partner_id_is_not_permission", "spawn_after_report", "newborn_parent_id_is_not_permission",
        "after_pagination_counterexamples"},
    "test_with_format_feedback": {"initial_request", "test_home_then_format_rejection",
        "test_page_and_format_feedback_coexist", "after_format_report_complete"},
    "later_page_with_four_tasks": {"initial_request", "after_task_growth_1", "after_task_growth_2",
        "after_task_growth_3", "test_with_four_tasks", "later_page_with_dynamic_tasks", "after_task_report_complete"},
    "newborn_own_report_pages": {"initial_request", "newborn_own_test", "newborn_own_later_page",
        "after_newborn_report_complete"},
}
INVARIANT_KEYS = frozenset({"tools_unchanged", "native_sampling_fields_unchanged",
    "full_latest_observation_retained", "full_latest_initial_diagnostics_retained",
    "full_latest_role_task_retained", "latest_complete_visible_round_exact",
    "retained_nonuser_messages_are_original", "format_feedback_exact"})
SOURCE_PATHS = (
    "scripts/software_feedback_qualification_v042.py", "tests/test_software_feedback_qualification_v042.py",
    "src/proworksim/software_context_replay_v042.py", "src/proworksim/software_context_v042.py",
    "src/proworksim/software_context_replay_v041.py", "src/proworksim/software_context_v041.py",
    "src/proworksim/software_context_v034.py", "src/proworksim/software_context_v028.py",
    "src/proworksim/candidate_runtime_v015.py", "src/proworksim/harness_sdk.py",
    "src/proworksim/harness_policy_v040.py", "src/proworksim/harness_runtime.py",
    "src/proworksim/harness_port.py", "src/proworksim/software_organization_v040.py",
    "src/proworksim/software_organization_v042.py", "src/proworksim/software_organization_runtime_v042.py",
    "src/proworksim/software_organization_runtime_v040.py", "src/proworksim/team_budget_v033.py",
    "src/proworksim/software_organization_tasks_v040.py", "src/proworksim/software_tasks_v034.py",
)
_MEASUREMENT = None


def write(path, value):
    atomic_write(Path(path), json_bytes(value))


def configuration_inventory():
    return [{"route_id": f"core-r{index}-{condition}-{member}", "kind": "core",
        "case_id": case_id, "condition": condition, "member": member}
        for index, case_id in enumerate(CASE_IDS) for condition in CONDITIONS for member in MEMBERS[:2]]


def representative_inventory():
    return [{"route_id": f"representative-r{index}-{kind}", "kind": kind,
        "case_id": case_id, "condition": "ST", "member": MEMBERS[0]}
        for index, case_id in enumerate(CASE_IDS) for kind in REPRESENTATIVES]


def pagination_inventory():
    return [{"route_id": "pagination-catalog-" + kind, "kind": kind,
        "case_id": CASE_IDS[1], "condition": "ST", "member": MEMBERS[0]}
        for kind in PAGINATION_COMBINATIONS]


def largest_legal_file_page(files):
    """Freeze the largest actual 180-line page, not a page chosen after fit."""
    pages = []
    for path, text in sorted(files.items()):
        lines = text.splitlines()
        for offset in range(max(1, len(lines))):
            content = "\n".join(lines[offset:offset + 180])
            pages.append({"path": path, "start_line": offset + 1, "max_lines": 180,
                "characters": len(content), "utf8_bytes": len(content.encode()),
                "total_lines": len(lines), "returned_text_sha256": digest(content.encode())})
    return max(pages, key=lambda value: (value["utf8_bytes"], value["characters"],
                                       value["path"], -value["start_line"]))


def large_message():
    prefix = "CPU private-program capacity fixture; this text is not model-authored.\n"
    facts = [f"Public fact {index:03d}: all members retain equal public programming and testing permissions; "
             "a message transfers text, never workspace ownership or a private history."
             for index in range(30)]
    return (prefix + "\n".join(facts))[:4000]


def largest_string(value):
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return max((largest_string(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return max((largest_string(item) for item in value), default=0)
    return 0


def feedback_invariants(original, selected):
    """Verify complete latest v040-visible feedback, not host-only raw output."""
    originals = original["messages"]
    selected_messages = selected["messages"]
    observations = list(observation_messages(original))
    selected_observations = list(observation_messages(selected))
    latest = observations[-1][1]
    current = selected_observations[-1][1]
    normalized_latest = copy.deepcopy(latest)
    goal = normalized_latest["observation"].get("root_goal", {})
    if goal.get("description") == normalized_latest["observation"].get("contract"):
        goal.pop("description", None)
    tools = [m for m in originals if m.get("role") == "tool"]
    latest_round = []
    if tools:
        last = tools[-1]
        assistant = next(m for m in originals if m.get("role") == "assistant"
            and any(c["id"] == last["tool_call_id"] for c in m.get("tool_calls", [])))
        latest_round = [assistant, last]
    format_feedback = [m for m in originals if m.get("role") == "user"
        and isinstance(m.get("content"), str) and '"public_format_feedback"' in m["content"]]
    original_nonuser = [m for m in originals if m.get("role") != "user"]
    return {"tools_unchanged": selected.get("tools") == original.get("tools"),
        "native_sampling_fields_unchanged": all(selected.get(key) == original.get(key)
            for key in ("model", "max_tokens", "temperature", "tool_choice", "stream")),
        "full_latest_observation_retained": current == normalized_latest,
        "full_latest_initial_diagnostics_retained": current["observation"].get("initial_diagnostics")
            == latest["observation"].get("initial_diagnostics"),
        "full_latest_role_task_retained": current.get("role_task") == latest.get("role_task"),
        "latest_complete_visible_round_exact": all(message in selected_messages for message in latest_round),
        "retained_nonuser_messages_are_original": all(message in original_nonuser
            for message in selected_messages if message.get("role") != "user"),
        "format_feedback_exact": all(message in selected_messages for message in format_feedback)}


class PrivateProgramTransport:
    """Explicit CPU action provider. Its responses are fixtures, never samples.

    Input IDs are the actual native encoding. Output IDs encode only the JSON
    program action for SDK bookkeeping and are labeled accordingly; they do not
    assert a sampled model continuation or measured model output consumption.
    """
    def __init__(self, owner, measurement, directory):
        self.owner, self.measurement, self.directory = owner, measurement, Path(directory)
        self.stage = self.action = self.pending = None
        self.rows = []
        self.program_responses = 0

    def prepare_for_budget(self, request):
        if self.pending is not None or self.stage is None or self.action is None:
            raise ValueError("A qualification stage needs exactly one declared program action")
        measured = measure_request(request, self.measurement)
        selected, encoding = measured["new"]["selected"], measured["new"]["encoding"]
        protected = measured["new"]["protected_encoding"]
        projection = measured["new"]["projection"]
        stage_dir = self.directory / f"{len(self.rows):03d}-{self.stage}"
        stage_dir.mkdir(parents=True, exist_ok=False)
        write(stage_dir / "original-request.json", request)
        write(stage_dir / "old-selected-request.json", measured["old"]["selected"])
        write(stage_dir / "selected-request.json", selected)
        write(stage_dir / "projection.json", projection)
        write(stage_dir / "native-encoding.json", encoding)
        write(stage_dir / "protected-request.json", measured["new"]["protected_selected"])
        write(stage_dir / "protected-native-encoding.json", protected)
        checks = feedback_invariants(request, selected)
        protected_checks = feedback_invariants(request, measured["new"]["protected_selected"])
        row = {"stage": self.stage, "planned_program_action": copy.deepcopy(self.action),
            "origin": "cpu_private_program", "model_generated": False,
            "member_id": list(observation_messages(request))[-1][1]["observation"]["actor_id"],
            "original_prompt_tokens": measured["original"]["encoding"]["prompt_tokens"],
            "old_prompt_tokens": measured["old"]["encoding"]["prompt_tokens"],
            "old_headroom_tokens": measured["old"]["encoding"]["headroom_tokens"],
            "prompt_tokens": encoding["prompt_tokens"], "headroom_tokens": encoding["headroom_tokens"],
            "protected_prompt_tokens": protected["prompt_tokens"],
            "protected_headroom_tokens": protected["headroom_tokens"],
            "protected_engineering_margin_tokens": 1024,
            "protected_headroom_after_margin_tokens": protected["headroom_after_margin_tokens"],
            "protected_margin_fits": protected["margin_fits"],
            "context_limit": encoding["context_limit"], "reserved_output_tokens": encoding["reserved_output_tokens"],
            "fits": encoding["fits"], "feedback_invariants": checks,
            "protected_feedback_invariants": protected_checks,
            "rendered_prompt_sha256": encoding["rendered_prompt_sha256"],
            "input_ids_sha256": encoding["input_ids_sha256"],
            "protected_rendered_prompt_sha256": protected["rendered_prompt_sha256"],
            "protected_input_ids_sha256": protected["input_ids_sha256"],
            "original_request_sha256": digest(json_bytes(request)),
            "selected_request_sha256": digest(json_bytes(selected)),
            "latest_tool_feedback_characters": len(next((m["content"] for m in reversed(request["messages"])
                if m.get("role") == "tool"), "")),
            "sources": {name: reference(stage_dir / name) for name in ["original-request.json",
                "old-selected-request.json", "selected-request.json", "projection.json", "native-encoding.json",
                "protected-request.json", "protected-native-encoding.json"]}}
        self.rows.append(row)
        write(stage_dir / "measurement.json", row)
        prepared = {"version": BUDGET_PREPARATION_VERSION,
            **{key: row[key] for key in ["original_request_sha256", "selected_request_sha256",
                "rendered_prompt_sha256", "input_ids_sha256", "prompt_tokens", "reserved_output_tokens",
                "context_limit", "fits"]}, "actor_identity": self.owner.freeze_identity(),
            "window_id": self.owner.window_id, "recipe_sha256": digest(json_bytes(self.owner.recipe))}
        prepared["preparation_sha256"] = digest(json_bytes(prepared))
        self.pending = {"request": copy.deepcopy(request), "encoding": encoding,
            "prepared": prepared, "stage_dir": stage_dir}
        return copy.deepcopy(prepared)

    def discard_prepared_request(self, request):
        if self.pending is not None and self.pending["request"] != request:
            raise ValueError("Rejected preparation belongs to another request")
        self.pending = None

    def complete(self, request, **kwargs):
        pending, self.pending = self.pending, None
        if pending is None or pending["request"] != request or not pending["encoding"]["fits"]:
            raise ValueError("CPU action requires its own actually fitting native request")
        self.program_responses += 1
        name, arguments = self.action
        identifier = digest(json_bytes([self.owner.window_id, self.stage, self.program_responses]))[:32]
        message = {"role": "assistant", "content": None, "tool_calls": [{"id": "call_" + identifier,
            "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}
        output_ids = self.measurement.tokenizer(json.dumps(message, ensure_ascii=False),
                                                add_special_tokens=False)["input_ids"]
        if not 0 < len(output_ids) <= 2048:
            raise ValueError("Declared CPU program action exceeds the unchanged output allowance")
        input_ids = pending["encoding"]["input_ids"]
        body = {"id": "cpu_program_" + identifier, "object": "chat.completion", "created": 0,
            "model": "cpu-private-program-not-a-model", "actor_identity": self.owner.freeze_identity(),
            "online_window_id": self.owner.window_id,
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": message}],
            "usage": {"prompt_tokens": len(input_ids), "completion_tokens": len(output_ids),
                "total_tokens": len(input_ids) + len(output_ids)},
            "token_trace": {"input_ids": input_ids, "output_ids": output_ids, "fixture_only": True,
                "output_semantics": "Actual tokenizer encoding of a scripted JSON action for SDK accounting; not sampled native model output"},
            "cpu_program_provenance": {"model_generated": False, "model_calls": 0, "weights_loaded": False,
                "scope": "Private CPU route only; no behavior, probability, reward or training evidence"}}
        response = {"http_status": 200, "body": body, "raw_body": json.dumps(body)}
        write(pending["stage_dir"] / "cpu-program-response.json", response)
        return response


class RouteStopped(Exception):
    pass


class Route:
    def __init__(self, specification, directory, measurement):
        from proworksim.software_organization_runtime_v042 import build_runtime
        self.specification, self.directory = specification, Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        identity = {"policy_version": "cpu-private-program-v042", "adapter_sha256": "no-model-weights"}
        self.owner = SimpleNamespace(window_id=specification["route_id"], recipe=copy.deepcopy(measurement.recipe),
            freeze_identity=lambda: copy.deepcopy(identity))
        self.transport = PrivateProgramTransport(self.owner, measurement, self.directory / "requests")
        self.owner.transport = self.transport
        self.prepared = build_software_collaboration_case(case_spec(specification["case_id"],
            condition=specification["condition"]), self.directory / "prepared")
        self.runtime, self.captured, self.interfaces = build_runtime(self.owner, self.prepared,
            self.directory / "sdk-runtime", require_exact_resident=True)
        self.actions, self.checks, self.extra, self.recovery = [], {}, {}, []

    def step(self, stage, member, name, *, expect_denied=False, **arguments):
        self.runtime.sync_members()
        self.runtime.cursor = self.runtime.labels.index(member)
        self.transport.stage, self.transport.action = stage, (name, arguments)
        before = len(self.transport.rows)
        outcome = self.runtime.step()
        self.runtime.after_completed_opportunity(outcome)
        self.runtime.sync_members()
        entry = {"stage": stage, "member": member, "program_action": name, "arguments": arguments,
            "outcome": outcome, "origin": "cpu_private_program", "model_generated": False}
        self.actions.append(entry)
        write(self.directory / "program-actions.json", self.actions)
        if len(self.transport.rows) != before + 1:
            raise RouteStopped("SDK did not construct the next native request: " + str(outcome.get("status")))
        measurement = self.transport.rows[-1]
        if not measurement["fits"]:
            raise RouteStopped("context_capacity:" + stage)
        if (not all(measurement["feedback_invariants"].values())
                or not all(measurement["protected_feedback_invariants"].values())):
            raise RouteStopped("visible_feedback_or_static_fact_changed:" + stage)
        if expect_denied:
            response = outcome.get("response") or {}
            self.check(stage + "_actually_denied", response.get("ok") is False)
            return response
        if outcome["status"] not in {"running", "completed", "model_format_feedback"}:
            raise RouteStopped("SDK/world route failed: " + str(outcome.get("status")))
        if outcome["status"] == "model_format_feedback" and name != "work_done":
            raise RouteStopped("Unexpected program format rejection: " + stage)
        return outcome.get("response")

    def check(self, name, value):
        self.checks[name] = bool(value)
        if not value:
            raise RouteStopped("route_contract_failed:" + name)

    def repair(self, member, first_stage="repair_write_0"):
        files = self.prepared.world._bundle(member)[2]["files"]
        reference_files = reference_solution(self.specification["case_id"])
        paths = [path for path in self.prepared.case["editable_paths"]
                 if path != "test_member.py" and files[path] != reference_files[path]]
        self.check("private_reference_has_actual_repair", bool(paths))
        self.extra["program_repair_paths"] = paths
        for index, path in enumerate(paths):
            stage = first_stage if index == 0 else f"after_repair_write_{index}"
            self.step(stage, member, "write_file", path=path, text=reference_files[path])

    def report(self, report_id):
        return copy.deepcopy(self.prepared.world._software()["test_reports"][report_id])

    def read_complete_report(self, label, member, home, *, first_stage):
        """Read only pages returned by actual authorized SDK tool actions."""
        report_id = home["report_id"]
        saved = self.report(report_id)
        self.check(label + "_report_owned_by_reader", saved["actor_id"] == member)
        baseline_tests = self.prepared.world.test_budget.snapshot()["used"]
        baseline_decisions = self.runtime.team_budget.snapshot()["decisions"]
        pages, results, current = [], [], home
        expected_start = 0
        while True:
            page = current["page"]
            self.check(label + f"_page_{page['index']}_exact_bounds",
                current["report_id"] == report_id and page["index"] == len(pages)
                and page["start"] == expected_start and page["end"] - page["start"] == len(page["text"])
                and 0 < len(page["text"]) <= 3072 and digest(page["text"].encode()) == page["sha256"])
            pages.append(page)
            results.append(copy.deepcopy(current))
            expected_start = page["end"]
            if page["next_cursor"] is None:
                self.check(label + "_explicit_last_page", page["is_last"] is True and page["remaining_pages"] == 0)
                break
            self.check(label + "_nonfinal_page_marks_remaining", page["is_last"] is False and page["remaining_pages"] > 0)
            stage = first_stage if len(pages) == 1 else f"{label}_after_page_{page['index']}"
            reply = self.step(stage, member, "read_test_result", report_id=report_id, cursor=page["next_cursor"])
            current = reply["result"]
        body = "".join(page["text"] for page in pages)
        recovered = json.loads(body)
        exact = body == saved["body"] and digest(body.encode()) == saved["body_sha256"] and recovered == saved["visible_result"]
        self.check(label + "_exact_visible_report_recovery", exact)
        self.check(label + "_reading_never_reruns_test", self.prepared.world.test_budget.snapshot()["used"] == baseline_tests)
        page_file = self.directory / ("recovered-" + label + ".json")
        write(page_file, {"origin": "cpu_private_program", "actor_id": member, "report_id": report_id,
            "page_results_from_actual_tools": results, "body": body, "visible_result": recovered,
            "event_identity": saved["event_identity"], "body_sha256": saved["body_sha256"], "exact_recovery": exact})
        record = {"label": label, "actor_id": member, "report_id": report_id,
            "event_identity": saved["event_identity"], "page_count": len(pages),
            "body_characters": len(body), "body_sha256": saved["body_sha256"],
            "page_sha256": [page["sha256"] for page in pages], "exact_recovery": exact,
            "run_tests_count_unchanged_by_page_reads": True,
            "read_page_program_decisions": self.runtime.team_budget.snapshot()["decisions"] - baseline_decisions,
            "recovery_source": reference(page_file)}
        self.recovery.append(record)
        return recovered, results

    def deny_report(self, stage, member, report_id, cursor):
        tests_before = self.prepared.world.test_budget.snapshot()["used"]
        reply = self.step(stage, member, "read_test_result", expect_denied=True,
                          report_id=report_id, cursor=cursor)
        error = reply.get("error", {})
        self.check(stage + "_correct_capability_error", error.get("rejection", {}).get("code") == "test_report_not_readable")
        self.check(stage + "_no_report_or_page_leaked", "result" not in reply and "page" not in error and "body" not in error)
        self.check(stage + "_no_free_retest", self.prepared.world.test_budget.snapshot()["used"] == tests_before)

    def core(self):
        member = self.specification["member"]
        self.step("initial_request", member, "read_file", path="records.py", start_line=1, max_lines=180)
        failed = self.step("after_read_file", member, "run_tests")
        self.check("real_initial_public_test_failed", failed["ok"] and failed["result"]["executed"]
                   and failed["result"]["passed"] is False)
        self.read_complete_report("failed", member, failed["result"], first_stage="after_failed_public_tests")
        self.repair(member, "after_failed_report_complete")
        passed = self.step("after_repair", member, "run_tests")
        self.check("real_repaired_public_test_passed", passed["ok"] and passed["result"]["executed"]
                   and passed["result"]["passed"] is True)
        self.read_complete_report("passed", member, passed["result"], first_stage="after_passed_public_tests")
        self.check("initial_failure_and_new_success_are_different_reports",
                   failed["result"]["report_id"] != passed["result"]["report_id"])
        self.step("after_passed_report_complete", member, "fix_patch", task_ids=[],
                  message="CPU private-program fixed repair; not model-generated")
        self.step("after_fix_patch", member, "submit_integration",
                  message="CPU private-program submit route; no private acceptance or model success claim")
        self.step("after_submit_integration", member, "staff_done", reason="CPU qualification route complete")
        self.check("actual_fixed_submission_exists", len(self.prepared.world._software()["deliveries"]) == 1)

    def representative(self):
        member, kind = self.specification["member"], self.specification["kind"]
        if kind == "largest_legal_read":
            page = largest_legal_file_page(material(self.specification["case_id"])["files"])
            self.extra["largest_actual_page"] = page
            reply = self.step("initial_request", member, "read_file",
                **{key: page[key] for key in ("path", "start_line", "max_lines")})
            self.check("full_maximum_actual_page_returned", digest(reply["result"]["text"].encode())
                       == page["returned_text_sha256"])
            self.step("after_largest_legal_read", member, "staff_done", reason="CPU larger-return control complete")
        elif kind == "repair_diff":
            self.step("initial_request", member, "read_file", path="records.py", start_line=1, max_lines=180)
            self.repair(member)
            reply = self.step("before_maximum_diff_page", member, "diff_workspace", offset=0, max_chars=6000)
            self.extra["actual_diff_response"] = reply
            self.step("after_maximum_diff_page", member, "staff_done", reason="CPU diff-page control complete")
        elif kind == "message_4000":
            peer = MEMBERS[1]
            self.step("initial_request", member, "read_file", path="records.py", start_line=1, max_lines=180)
            body = large_message()
            self.extra["message_characters"] = len(body)
            sent = self.step("peer_send_maximum_message", peer, "send_message",
                recipient=member, task_id=ROOT_GOAL_ID, body=body)
            self.step("message_enters_recipient_observation", member, "read_work_event",
                sequence=sent["result"]["message_sequence"])
            self.step("after_exact_message_read", member, "staff_done", reason="CPU message control complete")
        elif kind == "format_rejection":
            self.step("initial_request", member, "work_done", reason="CPU rejected-name fixture")
            self.step("after_actual_format_rejection", member, "read_file", path="records.py", start_line=1, max_lines=180)
            self.step("after_format_recovery_read", member, "staff_done", reason="CPU format control complete")
        elif kind == "task_growth_4":
            for index in range(4):
                self.step("initial_request" if index == 0 else f"after_task_growth_{index}", member,
                    "create_task", task_id=f"cpu-capacity-task-{index + 1}",
                    description=f"CPU private-program capacity fixture {index + 1}: inspect a public branch artifact, "
                    "record exact version evidence, and retain the immutable common root contract. "
                    "This fixture assigns no member and makes no model-work claim.")
            self.step("after_four_task_state_growth", member, "staff_done", reason="CPU four-task control complete")
            self.check("four_unassigned_tasks", len(self.prepared.world._software()["tasks"]) == 4
                and all(t["owner"] is None for t in self.prepared.world._software()["tasks"].values()))
        elif kind == "newborn":
            born = self.step("initial_request", member, "spawn_member", briefing=large_message())
            child = born["result"]["member_id"]
            child_observation = self.interfaces[child].observe()
            self.check("newborn_has_no_free_initial_diagnostic", child_observation["initial_diagnostics"] == [])
            self.check("newborn_has_no_parent_history", self.runtime.birth_records[child]["private_history_copied"] is False)
            self.extra["child_member_id"] = child
            self.extra["briefing_characters"] = len(large_message())
            self.step("newborn_initial_request", child, "read_file", path="records.py", start_line=1, max_lines=180)
            self.step("newborn_after_read_file", child, "staff_done", reason="CPU newborn control complete")
        else:
            raise ValueError("Undeclared representative control")

    def pagination_combination(self):
        member, kind = self.specification["member"], self.specification["kind"]
        if kind == "long_item_event_cursor_permissions":
            script = ("# CPU private-program long visible member-output fixture.\n"
                "print('CPU-LONG-ITEM:' + ''.join('record%04d;' % i for i in range(650)))\n")
            self.step("initial_request", member, "write_file", path="test_member.py", text=script)
            first = self.step("long_item_test", member, "run_tests")["result"]
            visible, pages = self.read_complete_report("long_item", member, first,
                first_stage="after_long_item_homepage")
            first_report = self.report(first["report_id"])
            self.check("legitimate_member_output_contains_long_single_item", largest_string(visible) > 3072)
            self.check("long_item_was_split_explicitly", any(p["page"]["split_entries"] for p in pages))
            self.check("long_report_has_middle_and_final_pages", len(pages) >= 3)
            second = self.step("same_content_second_test", member, "run_tests")["result"]
            second_report = self.report(second["report_id"])
            self.check("same_business_results_distinct_reports_and_events",
                first["report_id"] != second["report_id"]
                and first_report["event_identity"] != second_report["event_identity"]
                and all(visible["public_diagnostics"][group]["tests"]
                    == second_report["visible_result"]["public_diagnostics"][group]["tests"]
                    for group in visible["public_diagnostics"]))
            self.extra["same_content_scope"] = ("Two actual tests of the same source preserve identical public business observations; "
                "event/report IDs remain separate. Budget/execution metadata may differ and are not erased.")
            self.extra["same_content_reports"] = [first["report_id"], second["report_id"]]
            tests_before_reads = self.prepared.world.test_budget.snapshot()["used"]
            middle, final = pages[len(pages) // 2], pages[-1]
            for stage, expected in (("repeat_middle_page", middle), ("repeat_final_page", final)):
                repeated = self.step(stage, member, "read_test_result", report_id=first["report_id"],
                                     cursor=expected["page"]["cursor"])["result"]
                self.check(stage + "_identical_piece", repeated["report_id"] == first["report_id"]
                    and repeated["page"] == expected["page"])
            original = self.prepared.world._bundle(member)[2]["files"]["records.py"]
            self.step("edit_after_report", member, "write_file", path="records.py",
                      text=original + "\n# CPU version witness after the saved report.\n")
            old = self.step("old_cursor_after_edit", member, "read_test_result", report_id=first["report_id"],
                            cursor=middle["page"]["cursor"])["result"]
            self.check("old_cursor_is_bound_to_saved_event_and_source", old["page"] == middle["page"]
                and self.report(first["report_id"]) == first_report
                and digest(json_bytes(self.prepared.world._bundle(member)[2]["files"])) != visible["files_sha256"])
            self.deny_report("partner_id_is_not_permission", MEMBERS[1], first["report_id"], middle["page"]["cursor"])
            born = self.step("spawn_after_report", member, "spawn_member",
                briefing="CPU permission control: the parent report ID is not permission: " + first["report_id"])["result"]
            self.deny_report("newborn_parent_id_is_not_permission", born["member_id"],
                             first["report_id"], middle["page"]["cursor"])
            self.check("repeats_edits_and_denials_never_rerun_test",
                       self.prepared.world.test_budget.snapshot()["used"] == tests_before_reads)
            self.step("after_pagination_counterexamples", member, "staff_done", reason="CPU page-identity controls complete")
        elif kind == "test_with_format_feedback":
            home = self.step("initial_request", member, "run_tests")["result"]
            self.step("test_home_then_format_rejection", member, "work_done", reason="CPU correction feedback coexists with a real test page")
            self.read_complete_report("format", member, home, first_stage="test_page_and_format_feedback_coexist")
            self.step("after_format_report_complete", member, "staff_done", reason="CPU test/format combination complete")
        elif kind == "later_page_with_four_tasks":
            for index in range(4):
                self.step("initial_request" if index == 0 else f"after_task_growth_{index}", member,
                    "create_task", task_id=f"cpu-page-task-{index + 1}",
                    description=f"CPU page/state fixture {index + 1}: preserve current source versions and exact public facts. "
                    "The common root contract is unchanged; this is an unassigned program-created qualification task.")
            home = self.step("test_with_four_tasks", member, "run_tests")["result"]
            self.read_complete_report("tasks", member, home, first_stage="later_page_with_dynamic_tasks")
            self.check("four_real_tasks_remain_in_current_state", len(self.prepared.world._software()["tasks"]) == 4)
            self.step("after_task_report_complete", member, "staff_done", reason="CPU page/dynamic-state combination complete")
        elif kind == "newborn_own_report_pages":
            born = self.step("initial_request", member, "spawn_member", briefing=large_message())["result"]
            child = born["member_id"]
            self.check("newborn_report_route_has_no_free_initial_facts",
                       self.interfaces[child].observe()["initial_diagnostics"] == [])
            home = self.step("newborn_own_test", child, "run_tests")["result"]
            self.read_complete_report("newborn", child, home, first_stage="newborn_own_later_page")
            self.check("newborn_only_receives_report_it_actually_executed", self.report(home["report_id"])["actor_id"] == child)
            self.step("after_newborn_report_complete", child, "staff_done", reason="CPU newborn own-page combination complete")
        else:
            raise ValueError("Undeclared pagination combination")

    def complete_page_input_evidence(self):
        """A saved page return is not yet proof of its next request presentation."""
        presented = {}
        for stage in self.transport.rows:
            if not stage["fits"]:
                continue
            request = json.loads(Path(stage["sources"]["selected-request.json"]["path"]).read_text())
            for message in request["messages"]:
                if message.get("role") != "tool":
                    continue
                payload = json.loads(message["content"])
                result = payload.get("result") if isinstance(payload, dict) else None
                if not isinstance(result, dict) or "report_id" not in result or not isinstance(result.get("page"), dict):
                    continue
                page = result["page"]
                key = (stage["member_id"], result["report_id"], page["index"], page["sha256"])
                presented.setdefault(key, []).append(stage["stage"])
        for recovery in self.recovery:
            coverage = []
            for index, sha in enumerate(recovery["page_sha256"]):
                stages = presented.get((recovery["actor_id"], recovery["report_id"], index, sha), [])
                coverage.append({"page_index": index, "sha256": sha, "fitting_selected_stages": stages})
            recovery["subsequent_selected_input_coverage"] = coverage
            recovery["all_pages_presented_in_subsequent_fitting_requests"] = all(row["fitting_selected_stages"] for row in coverage)

    def finish(self, error=None):
        from proworksim.software_organization_runtime_v042 import close_runtime
        close_runtime(self.runtime)
        self.complete_page_input_evidence()
        rows = self.transport.rows
        write(self.directory / "team-budget-cpu-fixture.json", self.runtime.team_budget.snapshot())
        write(self.directory / "public-capture-cpu-fixture.json", self.captured)
        value = {**self.specification, "version": VERSION, "origin": "cpu_private_program",
            "passed": error is None and bool(rows) and all(row["fits"] and row["protected_margin_fits"]
                and all(row["feedback_invariants"].values()) and all(row["protected_feedback_invariants"].values()) for row in rows),
            "operational_route_completed": error is None,
            "selected_capacity_passed": bool(rows) and all(row["fits"] for row in rows),
            "protected_engineering_margin_passed": bool(rows) and all(row["protected_margin_fits"] for row in rows),
            "stopped_reason": error, "checks": self.checks, "stages": rows,
            "max_prompt_tokens": max((row["prompt_tokens"] for row in rows), default=None),
            "minimum_headroom_tokens": min((row["headroom_tokens"] for row in rows), default=None),
            "max_protected_prompt_tokens": max((row["protected_prompt_tokens"] for row in rows), default=None),
            "minimum_protected_headroom_after_margin_tokens": min(
                (row["protected_headroom_after_margin_tokens"] for row in rows), default=None),
            "sdk_program_responses": self.transport.program_responses, "model_calls": 0,
            "model_weights_loaded": False, "new_backward_calls": 0,
            "accepted_cpu_run_tests_calls": self.prepared.world.test_budget.snapshot()["used"],
            "environment_preparation_cost": self.prepared.world._software()["environment_preparation_cost"],
            "extra": self.extra, "report_recovery": self.recovery,
            "scope": "Finite programmed environment/SDK capacity evidence only; no sampled policy behavior, hidden acceptance or model success evidence"}
        if any(recovery["all_pages_presented_in_subsequent_fitting_requests"] is not True for recovery in self.recovery):
            value["passed"] = False
        write(self.directory / "route.json", value)
        return value


def _initialize_worker(plan_path):
    global _MEASUREMENT
    _MEASUREMENT = load_native_measurement(plan_path)


def _run_route(specification, destination):
    route = Route(specification, Path(destination) / specification["route_id"], _MEASUREMENT)
    error = None
    try:
        if specification["kind"] == "core":
            route.core()
        elif specification["kind"] in REPRESENTATIVES:
            route.representative()
        else:
            route.pagination_combination()
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    return route.finish(error)


def qualification_gate(routes):
    expected = configuration_inventory() + representative_inventory() + pagination_inventory()
    indexed = {route["route_id"]: route for route in routes}
    missing = sorted({row["route_id"] for row in expected} - set(indexed))
    unexpected = sorted(set(indexed) - {row["route_id"] for row in expected})
    failures = []
    for spec in expected:
        route = indexed.get(spec["route_id"])
        if route is None:
            continue
        if any(route.get(key) != value for key, value in spec.items()):
            failures.append({"route_id": spec["route_id"], "reason": "configuration_identity_changed"})
        if not route.get("passed"):
            failures.append({"route_id": spec["route_id"], "reason": "route_not_passed", "detail": route.get("stopped_reason")})
        for stage in route.get("stages", []):
            invariants = stage.get("feedback_invariants", {})
            protected_invariants = stage.get("protected_feedback_invariants", {})
            capacity_valid = (stage.get("context_limit") == 16384 and stage.get("reserved_output_tokens") == 2048
                and type(stage.get("prompt_tokens")) is int and stage["prompt_tokens"] > 0
                and stage.get("headroom_tokens") == 16384 - 2048 - stage["prompt_tokens"]
                and stage["headroom_tokens"] >= 0 and stage.get("fits") is True)
            if (not capacity_valid or set(invariants) != INVARIANT_KEYS
                    or any(value is not True for value in invariants.values())):
                failures.append({"route_id": spec["route_id"], "stage": stage["stage"], "reason": "capacity_or_information_invariant"})
            protected_valid = (type(stage.get("protected_prompt_tokens")) is int
                and 0 < stage["protected_prompt_tokens"] <= 13312
                and stage.get("protected_engineering_margin_tokens") == 1024
                and stage.get("protected_headroom_tokens") == 14336 - stage["protected_prompt_tokens"]
                and stage.get("protected_headroom_after_margin_tokens") == 13312 - stage["protected_prompt_tokens"]
                and stage.get("protected_margin_fits") is True)
            if (not protected_valid or set(protected_invariants) != INVARIANT_KEYS
                    or any(value is not True for value in protected_invariants.values())):
                failures.append({"route_id": spec["route_id"], "stage": stage["stage"], "reason": "protected_engineering_margin_or_information_invariant"})
        required = (CORE_REQUIRED_STAGES if spec["kind"] == "core" else
                    REPRESENTATIVE_REQUIRED_STAGES.get(spec["kind"], PAGINATION_REQUIRED_STAGES.get(spec["kind"])))
        absent = required - {stage["stage"] for stage in route.get("stages", [])}
        if absent:
            failures.append({"route_id": spec["route_id"], "reason": "missing_feedback_loop_stages", "stages": sorted(absent)})
        if spec["kind"] == "core":
            recoveries = route.get("report_recovery", [])
            if ({r.get("label") for r in recoveries} != {"failed", "passed"}
                    or any(r.get("exact_recovery") is not True
                        or r.get("all_pages_presented_in_subsequent_fitting_requests") is not True for r in recoveries)):
                failures.append({"route_id": spec["route_id"], "reason": "incomplete_exact_failed_and_passed_report_recovery"})
        elif spec["kind"] in PAGINATION_COMBINATIONS:
            recoveries = route.get("report_recovery", [])
            if not recoveries or any(r.get("exact_recovery") is not True
                    or r.get("all_pages_presented_in_subsequent_fitting_requests") is not True for r in recoveries):
                failures.append({"route_id": spec["route_id"], "reason": "pagination_combination_not_recovered_and_presented"})
    return {"passed": not missing and not unexpected and not failures and len(routes) == len(indexed),
        "expected_core_shapes": 16, "expected_representative_routes": len(representative_inventory()),
        "expected_pagination_combination_routes": len(pagination_inventory()),
        "missing_routes": missing, "unexpected_routes": unexpected, "failures": failures}


def qualify(destination, *, plan_path=DEFAULT_PLAN, workers=4):
    if not 1 <= workers <= 4:
        raise ValueError("Use one to four CPU qualification workers")
    if PAGE_BODY_CHARACTERS != 3072:
        raise ValueError("This qualification declares one fixed 3072-character page candidate")
    os.environ.update(CUDA_VISIBLE_DEVICES="", TOKENIZERS_PARALLELISM="false", OMP_NUM_THREADS="4")
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    source_before = {name: reference(SOURCE / name) for name in SOURCE_PATHS}
    snapshot = destination / "source-snapshot"
    snapshots = {}
    for name, expected in source_before.items():
        data = (SOURCE / name).read_bytes()
        if digest(data) != expected["sha256"]:
            raise ValueError("Qualification source changed before snapshot: " + name)
        atomic_write(snapshot / name, data)
        snapshots[name] = reference(snapshot / name)
    write(snapshot / "manifest.json", {"version": VERSION, "source_files": snapshots,
        "scope": "Exact implementation bytes bound before this single-candidate CPU qualification"})
    measurement = load_native_measurement(plan_path)
    write(destination / "native-measurement-identity.json", measurement.identity)
    specs = configuration_inventory() + representative_inventory() + pagination_inventory()
    write(destination / "declared-inventory.json", specs)
    started = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_initialize_worker, initargs=(str(plan_path),)) as pool:
        futures = {pool.submit(_run_route, spec, str(destination)): spec for spec in specs}
        for future in as_completed(futures):
            spec = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {**spec, "passed": False, "stages": [],
                    "stopped_reason": {"type": type(error).__name__, "message": str(error)}}
            results.append(result)
            write(destination / "progress.json", results)
    order = {row["route_id"]: index for index, row in enumerate(specs)}
    results.sort(key=lambda row: order[row["route_id"]])
    gate = qualification_gate(results)
    source_after = {name: reference(SOURCE / name) for name in SOURCE_PATHS}
    if source_before != source_after:
        gate["passed"] = False
        gate["failures"].append({"reason": "qualification_source_changed_during_measurement"})
    stages = [stage for route in results for stage in route.get("stages", [])]
    value = {"version": VERSION, "kind": "p0_b_c_exact_pages_feedback_route_capacity", **gate,
        "new_model_calls": 0, "model_weights_loaded": False, "new_backward_calls": 0,
        "context_limit": 16384, "reserved_output_tokens": 2048, "page_body_characters": 3072,
        "protected_engineering_margin_tokens": 1024, "maximum_selected_prompt_tokens": 14336,
        "maximum_protected_prompt_tokens": 13312,
        "native_measurement_identity": measurement.identity,
        "source_files": source_before, "source_unchanged_during_measurement": source_before == source_after,
        "source_snapshot_manifest": reference(snapshot / "manifest.json"),
        "started_at": started, "ended_at": time.time(), "cpu_processes": workers,
        "max_prompt_tokens": max((stage["prompt_tokens"] for stage in stages), default=None),
        "minimum_headroom_tokens": min((stage["headroom_tokens"] for stage in stages), default=None),
        "max_protected_prompt_tokens": max((stage["protected_prompt_tokens"] for stage in stages), default=None),
        "minimum_protected_headroom_after_margin_tokens": min(
            (stage["protected_headroom_after_margin_tokens"] for stage in stages), default=None),
        "program_routes": results,
        "declared_larger_returns": {"read_file": "Largest actual 180-line page across each root's installed public files, selected before capacity measurement",
            "diff_workspace": "Real reference repair diff; request the unchanged maximum 6000-character page",
            "message": "One 4000-character legitimate addressed CPU fixture, then exact message read and next request",
            "task_growth": "Four explicit unassigned 232-character-class task descriptions",
            "newborn": "Real baseline spawn with a 4000-character CPU fixture briefing; initial and post-read requests"},
        "scope": "Original tokenizer and native renderer, actual SDK and CPU tools only. Program actions are neither sampled behavior nor suggested model work. The report body is exactly the v040 visible feedback; it is now delivered as directory plus exact 3072-character pages under v042. Selected hard admission and protected engineering margin are separate. Either failed gate blocks the model inventory; no shorter replacement page, altered output reserve or capacity fallback is used."}
    write(destination / "qualification.json", value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=SOURCE / "runs/v042-controls/feedback-route")
    parser.add_argument("--prior-plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    value = qualify(args.output, plan_path=args.prior_plan, workers=args.workers)
    print(json.dumps({key: value[key] for key in ["version", "passed", "expected_core_shapes",
        "expected_representative_routes", "expected_pagination_combination_routes", "max_prompt_tokens",
        "minimum_headroom_tokens", "max_protected_prompt_tokens", "minimum_protected_headroom_after_margin_tokens", "failures"]}, ensure_ascii=False))
    return 0 if value["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
