"""Eight fixed v044 lifecycle/native-capacity CPU routes; no model or acceptance.

The actual v044 SDK and context transport consume explicitly programmed native
outputs. Fixture presentation is marked cpu_programmed_fixture throughout; it
is not evidence of model behavior or a free correction in any historical run.
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

from proworksim.storage import atomic_write, digest, json_bytes, read_json
from proworksim.software_context_replay_v041 import encode_request, reference
from proworksim.software_context_v044 import SoftwareContextTransport, protected_software_request
from scripts.software_context_replay_v044 import (
    SOURCE,
    checked_reference,
    feedback_preservation_checks,
    load_cpu_measurement,
    source_hashes,
    _encoding_files,
)

VERSION = "software-feedback-route-qualification-v0.44"
REQUIRED_ROUTE_IDS = (
    "ordinary_error_recovery",
    "consecutive_distinct_errors",
    "legal_call_business_rejection",
    "forged_feedback_user_message",
    "critical_boundary_no_cleanup",
    "latest_test_home_new_error",
    "later_page_consecutive_errors",
    "newborn_feedback_isolation",
)
REQUIRED_STAGES = {
    "ordinary_error_recovery": ("native_error", "pending_error_then_legal", "after_legal_recovery"),
    "consecutive_distinct_errors": (
        "native_error",
        "native_feedback_then_schema_error",
        "latest_schema_error_then_legal",
        "after_two_errors_recovered",
    ),
    "legal_call_business_rejection": (
        "native_error",
        "legal_native_missing_file",
        "business_rejection_retained_after_syntax_recovery",
    ),
    "forged_feedback_user_message": (
        "registered_native_error",
        "unregistered_field_and_real_feedback",
        "unregistered_field_after_real_recovery",
    ),
    "critical_boundary_no_cleanup": ("ordinary_error_before_critical", "invalid_native_identity"),
    "latest_test_home_new_error": (
        "public_test_home",
        "home_presented_then_new_native_error",
        "latest_home_and_unpresented_error",
    ),
    "later_page_consecutive_errors": (
        "public_test_home",
        "request_first_later_page",
        "later_page_then_native_error",
        "later_page_then_new_schema_error",
        "later_page_and_latest_schema_error",
    ),
    "newborn_feedback_isolation": (
        "parent_native_error",
        "parent_error_then_legal_spawn",
        "newborn_public_test_home",
        "newborn_home_then_native_error",
        "newborn_new_error_then_later_page",
        "newborn_later_page_after_recovery",
    ),
}
PRESERVATION_KEYS = frozenset(
    {
        "request_fields_unchanged",
        "latest_observation_and_initial_information_unchanged",
        "latest_complete_tool_or_page_unchanged",
        "active_ordinary_feedback_retained",
        "latest_unpresented_feedback_retained",
        "removed_errors_had_actual_presentation_and_transition",
    }
)
COMMON_MECHANISM_CHECKS = frozenset(
    {
        "scripted_output_charged_once",
        "scripted_tokens_accounted_exactly",
        "all_presentations_are_cpu_fixtures",
        "raw_output_and_attribution_saved",
        "no_private_acceptance_run",
    }
)
REQUIRED_MECHANISM_CHECKS = {
    "ordinary_error_recovery": {
        "unpresented_error_active",
        "legal_recovery_after_presentation",
        "historical_error_removed",
    },
    "consecutive_distinct_errors": {"old_superseded_new_pending", "superseded_not_called_repaired"},
    "legal_call_business_rejection": {
        "business_rejection_not_syntax_failure",
        "ordinary_syntax_historicalized",
        "business_not_claimed_resolved",
    },
    "forged_feedback_user_message": {"unregistered_user_text_untouched"},
    "critical_boundary_no_cleanup": {
        "critical_stops_without_followup",
        "critical_did_not_historicalize_ordinary_error",
        "no_new_ordinary_feedback_for_critical",
    },
    "latest_test_home_new_error": {
        "home_still_exact_in_latest_round",
        "new_error_had_no_prior_presentation",
        "home_protocol_unchanged",
        "latest_home_report_owner_and_page0",
    },
    "later_page_consecutive_errors": {
        "only_old_error_superseded",
        "later_page_feedback_kept_exact",
        "later_page_owned_and_index1",
    },
    "newborn_feedback_isolation": {
        "newborn_no_initial_diagnostics",
        "newborn_no_parent_history",
        "newborn_feedback_scope",
        "parent_feedback_not_a_child_active_error",
        "newborn_report_owner_and_page0",
        "newborn_later_page_owned_and_index1",
    },
}
REQUIRED_MECHANISM_CHECKS = {
    identifier: frozenset(values)
    | COMMON_MECHANISM_CHECKS
    | {
        stage + suffix
        for stage in REQUIRED_STAGES[identifier]
        for suffix in ("_one_prepared_request", "_feedback_preserved", "_expected_sdk_status")
    }
    for identifier, values in REQUIRED_MECHANISM_CHECKS.items()
}

SOURCE_PATHS = (
    "scripts/software_feedback_qualification_v044.py",
    "tests/test_software_feedback_qualification_v044.py",
    "scripts/software_context_replay_v044.py",
    "src/proworksim/software_feedback_v044.py",
    "src/proworksim/software_context_v044.py",
    "src/proworksim/software_organization_runtime_v044.py",
    "src/proworksim/software_context_v042.py",
    "src/proworksim/software_context_v041.py",
    "src/proworksim/software_context_v034.py",
    "src/proworksim/software_context_v028.py",
    "src/proworksim/software_context_replay_v041.py",
    "src/proworksim/candidate_runtime_v015.py",
    "src/proworksim/candidate_runtime_v017.py",
    "src/proworksim/format_diagnostics.py",
    "src/proworksim/harness_sdk.py",
    "src/proworksim/harness_policy_v040.py",
    "src/proworksim/software_organization_v042.py",
    "src/proworksim/software_organization_runtime_v042.py",
    "src/proworksim/software_organization_v040.py",
    "src/proworksim/software_organization_tasks_v040.py",
)
# These contracts are reused by exact source hash, never called new-Gamma capacity proof.
PAGING_PERMISSION_SOURCES = (
    "src/proworksim/software_organization_v042.py",
    "src/proworksim/software_organization_v040.py",
    "src/proworksim/software_organization_tasks_v040.py",
)


def native_program_text(name, arguments):
    parts = ["<tool_call>", f"<function={name}>"]
    for key, value in arguments.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        parts.append(f"<parameter={key}>\\n{text}\\n</parameter>".replace("\\n", "\n"))
    return "\n".join([*parts, "</function>", "</tool_call>"])


class ProgrammedOutput:
    def __init__(self, owner, measurement):
        self.owner, self.measurement = owner, measurement
        self.action = None
        self.count = 0
        self.responses = []

    def complete(self, request, **kwargs):
        from proworksim.candidate_runtime_v017 import parse_candidate_generated

        self.count += 1
        action = self.action
        raw = (
            action.get("raw")
            if "raw" in action
            else native_program_text(action["name"], action.get("arguments", {}))
        )
        message, parse_error = parse_candidate_generated(raw, request)
        if action.get("critical_invalid_identity"):
            message["tool_calls"][0]["id"] = ""
        encoding = encode_request(request, self.measurement)
        output_ids = self.measurement.tokenizer(raw, add_special_tokens=False)["input_ids"]
        if not 0 < len(output_ids) <= 2048:
            raise ValueError("CPU scripted output exceeds unchanged allowance")
        body = {
            "id": "cpu_program_" + digest(json_bytes([self.owner.window_id, self.count, raw]))[:32],
            "object": "chat.completion",
            "created": 0,
            "model": "cpu-private-program-not-model",
            "actor_identity": self.owner.freeze_identity(),
            "online_window_id": self.owner.window_id,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
                    "message": message,
                }
            ],
            "usage": {
                "prompt_tokens": encoding["prompt_tokens"],
                "completion_tokens": len(output_ids),
                "total_tokens": encoding["prompt_tokens"] + len(output_ids),
            },
            "token_trace": {
                "input_ids": encoding["input_ids"],
                "output_ids": output_ids,
                "fixture_only": True,
                "output_semantics": "Original tokenizer encoding of explicit CPU native text, not sampled model tokens",
            },
            "raw_generated_text": raw,
            "protocol_parse_error": parse_error,
            "cpu_program_provenance": {
                "model_generated": False,
                "model_calls": 0,
                "weights_loaded": False,
            },
        }
        response = {
            "http_status": 200,
            "body": body,
            "raw_body": json.dumps(body, ensure_ascii=False),
        }
        self.responses.append(
            {
                "response_id": body["id"],
                "response_body_sha256": digest(json_bytes(body)),
                "raw_text_sha256": digest(raw.encode()),
                "output_ids_sha256": digest(json_bytes(output_ids)),
                "usage": body["usage"],
            }
        )
        return response


class RecordingContext(SoftwareContextTransport):
    def __init__(self, owner, directory, measurement, measurements):
        super().__init__(owner, directory, evidence_kind="cpu_programmed_fixture")
        self.measurement, self.measurements = measurement, Path(measurements)
        self.rows = []
        self.stage = None

    def prepare_for_budget(self, request):
        before = self.feedback_ledger.snapshot()
        prepared = super().prepare_for_budget(request)
        pending = self._prepared
        selected, projection = pending["selected"], pending["projection"]
        protected, protected_projection = protected_software_request(
            request, ledger=before, member_id=self._turn["member_id"]
        )
        selected_encoding = encode_request(selected, self.measurement)
        protected_encoding = encode_request(protected, self.measurement)
        checks, active = feedback_preservation_checks(
            request, selected, projection, ledger=before, member_id=self._turn["member_id"]
        )
        protected_checks, _ = feedback_preservation_checks(
            request, protected, projection, ledger=before, member_id=self._turn["member_id"]
        )
        folder = self.measurements / f"{len(self.rows):03d}-{self.stage}"
        folder.mkdir(parents=True, exist_ok=False)
        refs = []
        for prefix, value, encoding, projection_value in (
            ("original", request, encode_request(request, self.measurement), None),
            ("selected", selected, selected_encoding, projection),
            ("protected", protected, protected_encoding, protected_projection),
        ):
            refs.extend(_encoding_files(folder, prefix, value, encoding, projection_value))
        atomic_write(folder / "lifecycle-before.json", json_bytes(before))
        refs.append(reference(folder / "lifecycle-before.json"))
        row = {
            "stage": self.stage,
            "member": self._turn["member_id"],
            "call_id": self._turn["association"]["call_id"],
            "prompt_tokens": selected_encoding["prompt_tokens"],
            "headroom_tokens": selected_encoding["headroom_tokens"],
            "selected_hard_capacity_passed": selected_encoding["fits"],
            "protected_prompt_tokens": protected_encoding["prompt_tokens"],
            "protected_headroom_after_margin_tokens": protected_encoding["headroom_tokens"] - 1024,
            "protected_margin_diagnostic_only": True,
            "context_limit": 16384,
            "reserved_output_tokens": 2048,
            "preservation_checks": checks,
            "protected_preservation_checks": protected_checks,
            "active_errors": active,
            "format_projection": projection["format_feedback_projection"],
            "selected_indices": projection["selected_indices"],
            "removed_indices": projection["removed_indices"],
            "artifacts": refs,
            "programmed_action": copy.deepcopy(self.owner.transport.action),
            "origin": "cpu_programmed_fixture",
            "model_generated": False,
        }
        self.rows.append(row)
        atomic_write(folder / "measurement.json", json_bytes(row))
        row["measurement_ref"] = reference(folder / "measurement.json")
        return prepared


class RouteStopped(Exception):
    pass


class Route:
    def __init__(self, route_id, directory, measurement):
        from proworksim.software_organization_v042 import (
            CASE_IDS,
            build_software_collaboration_case,
            case_spec,
        )
        from proworksim.software_organization_runtime_v038 import _CollectionOwner
        from proworksim.software_organization_runtime_v044 import build_runtime

        self.route_id, self.directory, self.measurement = route_id, Path(directory), measurement
        self.directory.mkdir(parents=True, exist_ok=False)
        identity = {
            "policy_version": "cpu-private-program-v044",
            "adapter_sha256": "no-model-weights",
        }
        owner = SimpleNamespace(
            window_id="cpu-v044:" + route_id,
            recipe=copy.deepcopy(measurement.recipe),
            prepare_request=measurement.render,
            tokenizer=measurement.tokenizer,
            freeze_identity=lambda: copy.deepcopy(identity),
        )
        self.program = ProgrammedOutput(owner, measurement)
        owner.transport = self.program
        self.context = RecordingContext(
            owner, self.directory / "raw-transport", measurement, self.directory / "measurements"
        )
        facade = _CollectionOwner(owner, self.context)
        condition = (
            "PT"
            if route_id == "newborn_feedback_isolation"
            else "ST"
            if route_id == "later_page_consecutive_errors"
            else "SB"
        )
        self.prepared = build_software_collaboration_case(
            case_spec(CASE_IDS[1], condition=condition), self.directory / "prepared"
        )
        self.runtime, self.captured, self.interfaces = build_runtime(
            facade, self.prepared, self.directory / "sdk-runtime", require_exact_resident=True
        )
        self.actions = []
        self.checks = {}
        self.terminal_boundary = None

    def check(self, name, value):
        self.checks[name] = bool(value)
        if not value:
            raise RouteStopped("mechanism_check_failed:" + name)

    def step(
        self,
        stage,
        member="member_001",
        name="read_file",
        *,
        raw=None,
        critical=False,
        expected="running",
        **arguments,
    ):
        self.runtime.sync_members()
        self.runtime.cursor = self.runtime.labels.index(member)
        self.context.stage = stage
        self.program.action = (
            {"raw": raw} if raw is not None else {"name": name, "arguments": arguments}
        )
        if critical:
            self.program.action["critical_invalid_identity"] = True
        before = len(self.context.rows)
        outcome = self.runtime.step()
        self.runtime.after_completed_opportunity(outcome)
        self.runtime.sync_members()
        action = {
            "stage": stage,
            "member": member,
            "scripted_output": copy.deepcopy(self.program.action),
            "outcome": outcome,
            "origin": "cpu_programmed_fixture",
            "model_generated": False,
        }
        self.actions.append(action)
        atomic_write(self.directory / "program-actions.json", json_bytes(self.actions))
        self.check(stage + "_one_prepared_request", len(self.context.rows) == before + 1)
        row = self.context.rows[-1]
        if not row["selected_hard_capacity_passed"]:
            raise RouteStopped("context_capacity:" + stage)
        self.check(
            stage + "_feedback_preserved",
            all(row["preservation_checks"].values())
            and all(row["protected_preservation_checks"].values()),
        )
        self.check(stage + "_expected_sdk_status", outcome["status"] == expected)
        return outcome

    def read(self, stage, member="member_001"):
        return self.step(stage, member, path="records.py", start_line=1, max_lines=30)

    def reject(self, stage, member="member_001", kind="native"):
        raw = (
            "<tool_call><function=read_file>"
            if kind == "native"
            else "<tool_call><function=read_file></function></tool_call>"
        )
        return self.step(stage, member, raw=raw, expected="model_format_feedback")

    def states(self, member="member_001"):
        return [
            r
            for r in self.context.feedback_ledger.snapshot()["records"]
            if r["member_id"] == member
        ]

    def page_from(self, outcome):
        reply = outcome.get("response") or {}
        self.check(
            "actual_public_test_returned_page_" + str(len(self.actions)),
            reply.get("ok") is True and isinstance(reply.get("result", {}).get("page"), dict),
        )
        return reply["result"]

    def run(self):
        kind = self.route_id
        if kind == "ordinary_error_recovery":
            self.reject("native_error")
            self.check(
                "unpresented_error_active",
                self.states()[0]["state"] == "pending_or_presented"
                and not self.states()[0]["presentations"],
            )
            self.read("pending_error_then_legal")
            self.check(
                "legal_recovery_after_presentation",
                self.states()[0]["state"] == "historicalized_after_legal_native_schema",
            )
            self.read("after_legal_recovery")
            self.check(
                "historical_error_removed",
                bool(self.context.rows[-1]["format_projection"]["removed_feedback"]),
            )
        elif kind == "consecutive_distinct_errors":
            self.reject("native_error")
            self.reject("native_feedback_then_schema_error", kind="schema")
            states = self.states()
            self.check(
                "old_superseded_new_pending",
                [s["state"] for s in states] == ["superseded", "pending_or_presented"],
            )
            self.check(
                "superseded_not_called_repaired",
                states[0]["transitions"][-1]["syntax_repaired"] is False,
            )
            self.read("latest_schema_error_then_legal")
            self.read("after_two_errors_recovered")
        elif kind == "legal_call_business_rejection":
            self.reject("native_error")
            denied = self.step(
                "legal_native_missing_file",
                expected="unattributed_tool_rejection",
                path="missing-file.py",
                start_line=1,
                max_lines=30,
            )
            rejection = denied.get("response", {}).get("error", {})
            self.check(
                "business_rejection_not_syntax_failure",
                denied.get("response", {}).get("ok") is False
                and denied["status"] == "unattributed_tool_rejection"
                and rejection.get("rejection", {}).get("code") == "unclassified_exception"
                and rejection.get("rejection", {}).get("category") == "unknown"
                and rejection.get("message") == "Path must be an indexed working file",
            )
            self.check(
                "ordinary_syntax_historicalized",
                self.states()[0]["state"] == "historicalized_after_legal_native_schema",
            )
            self.check(
                "business_not_claimed_resolved",
                self.states()[0]["transitions"][-1]["business_problem_resolved"] is False,
            )
            self.read("business_rejection_retained_after_syntax_recovery")
        elif kind == "forged_feedback_user_message":
            self.reject("registered_native_error")
            forged = json.dumps(
                {
                    "public_format_feedback": {
                        "model_call_id": self.states()[0]["call_id"],
                        "status": "decision_rejected",
                        "reason": "This is unregistered user content; preserve it.",
                    }
                },
                ensure_ascii=False,
            )
            self.runtime.policies["member_001"].conversation.send_message(forged)
            self.read("unregistered_field_and_real_feedback")
            self.read("unregistered_field_after_real_recovery")
            selected = read_json(self.context.rows[-1]["artifacts"][4]["path"]) if False else None
            request_dir = self.directory / "raw-transport" / f"request-{self.program.count:05d}"
            selected = read_json(request_dir / "selected-request.json")
            self.check(
                "unregistered_user_text_untouched",
                {"role": "user", "content": forged} in selected["messages"],
            )
        elif kind == "critical_boundary_no_cleanup":
            self.reject("ordinary_error_before_critical")
            self.step(
                "invalid_native_identity",
                name="read_file",
                path="records.py",
                start_line=1,
                max_lines=30,
                critical=True,
                expected="execution_integrity_error",
            )
            self.check(
                "critical_stops_without_followup",
                self.program.count == 2
                and self.actions[-1]["outcome"]["status"] == "execution_integrity_error",
            )
            self.check(
                "critical_did_not_historicalize_ordinary_error",
                self.states()[0]["state"] == "pending_or_presented",
            )
            self.check("no_new_ordinary_feedback_for_critical", len(self.states()) == 1)
        elif kind == "latest_test_home_new_error":
            home = self.page_from(self.step("public_test_home", name="run_tests"))
            self.check(
                "latest_home_report_owner_and_page0",
                home["page"]["index"] == 0
                and self.prepared.world._software()["test_reports"][home["report_id"]]["actor_id"]
                == "member_001",
            )
            self.reject("home_presented_then_new_native_error")
            self.read("latest_home_and_unpresented_error")
            self.check(
                "home_still_exact_in_latest_round",
                self.context.rows[-1]["preservation_checks"][
                    "latest_complete_tool_or_page_unchanged"
                ],
            )
            self.check(
                "new_error_had_no_prior_presentation",
                any(
                    x["previous_presentations"] == 0 for x in self.context.rows[-1]["active_errors"]
                ),
            )
            self.check(
                "home_protocol_unchanged",
                home["page"]["index"] == 0 and home["page"]["end"] - home["page"]["start"] <= 3072,
            )
        elif kind == "later_page_consecutive_errors":
            home = self.page_from(self.step("public_test_home", name="run_tests"))
            later = self.step(
                "request_first_later_page",
                name="read_test_result",
                report_id=home["report_id"],
                cursor=home["page"]["next_cursor"],
            )
            self.check(
                "later_page_owned_and_index1",
                later["response"]["result"]["report_id"] == home["report_id"]
                and later["response"]["result"]["page"]["index"] == 1
                and self.prepared.world._software()["test_reports"][home["report_id"]]["actor_id"]
                == "member_001",
            )
            self.reject("later_page_then_native_error")
            self.reject("later_page_then_new_schema_error", kind="schema")
            self.read("later_page_and_latest_schema_error")
            self.check("only_old_error_superseded", self.states()[0]["state"] == "superseded")
            self.check(
                "later_page_feedback_kept_exact",
                self.context.rows[-1]["preservation_checks"][
                    "latest_complete_tool_or_page_unchanged"
                ],
            )
        elif kind == "newborn_feedback_isolation":
            self.reject("parent_native_error")
            born = self.step(
                "parent_error_then_legal_spawn",
                name="spawn_member",
                briefing="CPU fixture: inspect your own public workspace; no copied parent feedback.",
            )
            child = born["response"]["result"]["member_id"]
            observation = self.interfaces[child].observe()
            self.check("newborn_no_initial_diagnostics", observation["initial_diagnostics"] == [])
            self.check(
                "newborn_no_parent_history",
                self.runtime.birth_records[child]["private_history_copied"] is False,
            )
            home = self.page_from(self.step("newborn_public_test_home", child, name="run_tests"))
            self.check(
                "newborn_report_owner_and_page0",
                home["page"]["index"] == 0
                and self.prepared.world._software()["test_reports"][home["report_id"]]["actor_id"]
                == child,
            )
            self.reject("newborn_home_then_native_error", child)
            later = self.step(
                "newborn_new_error_then_later_page",
                child,
                name="read_test_result",
                report_id=home["report_id"],
                cursor=home["page"]["next_cursor"],
            )
            self.check(
                "newborn_later_page_owned_and_index1",
                later["response"]["result"]["report_id"] == home["report_id"]
                and later["response"]["result"]["page"]["index"] == 1
                and self.prepared.world._software()["test_reports"][home["report_id"]]["actor_id"]
                == child,
            )
            self.read("newborn_later_page_after_recovery", child)
            self.check(
                "newborn_feedback_scope",
                len(self.states(child)) == 1
                and all(r["member_id"] == child for r in self.states(child)),
            )
            self.check(
                "parent_feedback_not_a_child_active_error",
                all(
                    x["feedback_id"].startswith(child + ":")
                    for row in self.context.rows
                    if row["member"] == child
                    for x in row["active_errors"]
                ),
            )
        else:
            raise ValueError("Unknown frozen CPU route")

    def finish(self, error=None):
        from proworksim.software_organization_runtime_v038 import close_runtime

        snapshot = self.context.feedback_ledger.snapshot()
        budget = self.runtime.team_budget.snapshot()
        self.checks["scripted_output_charged_once"] = (
            budget["attempts"] == self.program.count == len(self.program.responses)
        )
        self.checks["scripted_tokens_accounted_exactly"] = budget["charged_tokens"] == sum(
            r["usage"]["total_tokens"] for r in self.program.responses
        )
        self.checks["all_presentations_are_cpu_fixtures"] = all(
            g.get("evidence_kind") == "cpu_programmed_fixture"
            and g.get("generation_started") is False
            for g in snapshot["generations"]
        )
        self.checks["raw_output_and_attribution_saved"] = all(
            (self.directory / "raw-transport" / f"request-{i + 1:05d}" / "response.json").is_file()
            for i in range(self.program.count)
        )
        self.checks["no_private_acceptance_run"] = not (
            self.directory / "private-assessment"
        ).exists()
        rows = self.context.rows
        result = {
            "route_id": self.route_id,
            "passed": error is None
            and bool(rows)
            and all(r["selected_hard_capacity_passed"] for r in rows)
            and all(self.checks.values()),
            "selected_hard_capacity_passed": bool(rows)
            and all(r["selected_hard_capacity_passed"] for r in rows),
            "mechanism_checks": self.checks,
            "error": error,
            "stages": rows,
            "programmed_opportunities": len(self.actions),
            "programmed_responses": self.program.count,
            "programmed_accounting": budget,
            "lifecycle": snapshot,
            "new_model_calls": 0,
            "new_backward_calls": 0,
            "new_acceptance_executions": 0,
            "model_weights_loaded": False,
            "native_encoding_counts": self.measurement.statistics,
            "scope": "CPU scripted fixture only; no model behavior, new historical trace or independent task acceptance.",
        }
        atomic_write(self.directory / "qualification.json", json_bytes(result))
        close_runtime(self.runtime)
        return result


def qualification_gate(rows):
    identifiers = [r.get("route_id") for r in rows]
    issues = []
    if (
        len(identifiers) != len(REQUIRED_ROUTE_IDS)
        or set(identifiers) != set(REQUIRED_ROUTE_IDS)
        or len(set(identifiers)) != len(identifiers)
    ):
        issues.append("route_inventory")
    for row in rows:
        identifier = row.get("route_id")
        if identifier not in REQUIRED_STAGES:
            continue
        stages = row.get("stages", [])
        mechanisms = row.get("mechanism_checks", {})
        if tuple(s.get("stage") for s in stages) != REQUIRED_STAGES[identifier]:
            issues.append(identifier + ":stage_inventory")
        if not REQUIRED_MECHANISM_CHECKS[identifier].issubset(mechanisms) or not all(
            v is True for v in mechanisms.values()
        ):
            issues.append(identifier + ":mechanism_checks")
        if row.get("passed") is not True or row.get("selected_hard_capacity_passed") is not True:
            issues.append(identifier + ":recorded_status")
        if (
            any(
                type(row.get(key)) is not int or row[key] != 0
                for key in ("new_model_calls", "new_backward_calls", "new_acceptance_executions")
            )
            or row.get("model_weights_loaded") is not False
        ):
            issues.append(identifier + ":non_cpu_execution")
        if row.get("programmed_opportunities") != len(stages) or row.get(
            "programmed_responses"
        ) != len(stages):
            issues.append(identifier + ":programmed_opportunity_denominator")
        accounting = row.get("programmed_accounting", {})
        generations = row.get("lifecycle", {}).get("generations", [])
        if (
            accounting.get("attempts") != row.get("programmed_responses")
            or accounting.get("decisions") != row.get("programmed_opportunities")
            or accounting.get("held_tokens") != 0
            or row.get("lifecycle", {}).get("evidence_kind") != "cpu_programmed_fixture"
            or len(generations) != len(stages)
            or {(g.get("call_id"), g.get("member_id")) for g in generations}
            != {(stage.get("call_id"), stage.get("member")) for stage in stages}
            or any(
                g.get("evidence_kind") != "cpu_programmed_fixture"
                or g.get("generation_started") is not False
                or g.get("programmed_response_observed") is not True
                for g in generations
            )
        ):
            issues.append(identifier + ":fixture_origin_or_accounting")
        for stage in stages:
            if (
                stage.get("origin") != "cpu_programmed_fixture"
                or stage.get("model_generated") is not False
            ):
                issues.append(identifier + ":" + str(stage.get("stage")) + ":stage_origin")
            tokens = stage.get("prompt_tokens")
            headroom = stage.get("headroom_tokens")
            if (
                type(tokens) is not int
                or tokens < 0
                or type(headroom) is not int
                or stage.get("context_limit") != 16384
                or stage.get("reserved_output_tokens") != 2048
                or headroom != 14336 - tokens
                or headroom < 0
                or stage.get("selected_hard_capacity_passed") is not True
            ):
                issues.append(identifier + ":" + str(stage.get("stage")) + ":hard_capacity")
            for key in ("preservation_checks", "protected_preservation_checks"):
                checks = stage.get(key, {})
                if not PRESERVATION_KEYS.issubset(checks) or not all(
                    v is True for v in checks.values()
                ):
                    issues.append(identifier + ":" + str(stage.get("stage")) + ":" + key)
    return {
        "passed": not issues,
        "issues": issues,
        "required_route_ids": list(REQUIRED_ROUTE_IDS),
        "protected_margin_diagnostic_only": True,
    }


def _run_route(route_id, output, plan_path):
    measurement = load_cpu_measurement(plan_path)
    route = Route(route_id, Path(output) / route_id, measurement)
    error = None
    try:
        route.run()
    except Exception as exception:
        error = {"type": type(exception).__name__, "message": str(exception)}
    return route.finish(error)


def qualify(output, *, plan_path=None, workers=4, development_attempt=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    plan_path = Path(plan_path or SOURCE / "runs/software-organization-v043/plan.json").resolve()
    before = source_hashes(SOURCE_PATHS)
    started = time.time()
    rows = []
    plan = read_json(plan_path)
    admission_path = checked_reference(plan["qualification"])
    admission = read_json(admission_path)
    layered_path = checked_reference(admission["layered_admission"])
    layered = read_json(layered_path)
    prior_path = checked_reference(layered["evidence_refs"]["complete_feedback_routes"])
    prior = read_json(prior_path)
    prior_hashes = {
        key: (value["sha256"] if isinstance(value, dict) else value)
        for key, value in prior["source_files"].items()
    }
    refs = [
        reference(plan_path),
        reference(admission_path),
        reference(layered_path),
        reference(prior_path),
    ]
    inherited = {
        "scope": "Exact unchanged paging/source permission contracts only; old selected-capacity results do not qualify new Gamma.",
        "source_files": {key: before[key] for key in PAGING_PERMISSION_SOURCES},
        "evidence_refs": [reference(prior_path)],
        "linked_v043_qualification_version": admission["version"],
        "exact_paging_permission_source_match": all(
            prior_hashes.get(key) == before[key] for key in PAGING_PERMISSION_SOURCES
        ),
        "original_information_permission_layer_passed": layered.get("passed") is True
        and layered.get("layers", {}).get("information_permissions", {}).get("passed") is True,
    }
    with ProcessPoolExecutor(max_workers=min(workers, len(REQUIRED_ROUTE_IDS))) as pool:
        jobs = [
            pool.submit(_run_route, identifier, str(output), str(plan_path))
            for identifier in REQUIRED_ROUTE_IDS
        ]
        for job in as_completed(jobs):
            rows.append(job.result())
    rows.sort(key=lambda r: REQUIRED_ROUTE_IDS.index(r["route_id"]))
    gate = qualification_gate(rows)
    after = source_hashes(SOURCE_PATHS)
    for path in sorted(output.rglob("*")):
        if path.is_file():
            refs.append(reference(path))
    development = None
    if development_attempt is not None:
        prior_attempt_path = Path(development_attempt).resolve()
        old_attempt = read_json(prior_attempt_path)
        old_source = (
            prior_attempt_path.parent
            / "source-snapshot/scripts/software_feedback_qualification_v044.py"
        )
        if (
            digest(old_source.read_bytes())
            != old_attempt["source_files"]["scripts/software_feedback_qualification_v044.py"]
        ):
            raise ValueError(
                "Development runner source snapshot differs from its actual qualification"
            )
        refs.extend([reference(prior_attempt_path), reference(old_source)])
        development = {
            "qualification": reference(prior_attempt_path),
            "runner_source": reference(old_source),
            "passed": old_attempt["passed"],
            "programmed_responses": sum(
                r["programmed_responses"] for r in old_attempt["route_results"]
            ),
            "programmed_charged_tokens": sum(
                r["programmed_accounting"]["charged_tokens"] for r in old_attempt["route_results"]
            ),
            "reason": "Fixture incorrectly expected running for the unchanged unclassified_exception/unknown/unattributed_tool_rejection of an unindexed file. Only that expected status and precise original refusal checks were corrected; original failed records remain intact.",
            "feedback_candidate_changed": False,
            "historical112_repeated": False,
        }
    value = {
        "version": VERSION,
        "kind": "v044-eight-fixed-sdk-lifecycle-native-capacity-routes",
        "passed": gate["passed"]
        and before == after
        and inherited["exact_paging_permission_source_match"]
        and inherited["original_information_permission_layer_passed"],
        "required_route_ids": list(REQUIRED_ROUTE_IDS),
        "route_results": rows,
        "route_gate": gate,
        "development_attempt": development,
        "source_files": before,
        "source_unchanged_during_measurement": before == after,
        "artifact_refs": list({r["path"]: r for r in refs}.values()),
        "inherited_paging_permission_evidence": inherited,
        "new_model_calls": 0,
        "new_backward_calls": 0,
        "new_acceptance_executions": 0,
        "model_weights_loaded": False,
        "context_limit": 16384,
        "reserved_output_tokens": 2048,
        "protected_margin_tokens": 1024,
        "protected_margin_diagnostic_only": True,
        "started_at": started,
        "ended_at": time.time(),
        "scope": "Single ordinary-feedback Gamma candidate. Eight fixed CPU programmed routes, not 370 old routes, model trials or behavioral counterfactuals. Critical expected termination is a positive boundary control. The missing-file world refusal retains its original unknown/unattributed category; this demonstrates that legal syntax is not execution success, not a newly classified business_constraint or business recovery.",
    }
    atomic_write(output / "qualification.json", json_bytes(value))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(SOURCE / "runs/v044-controls/feedback-routes"))
    parser.add_argument("--plan", default=str(SOURCE / "runs/software-organization-v043/plan.json"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--development-attempt")
    args = parser.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    value = qualify(
        args.output,
        plan_path=args.plan,
        workers=args.workers,
        development_attempt=args.development_attempt,
    )
    print(
        json.dumps(
            {
                "passed": value["passed"],
                "routes": len(value["route_results"]),
                "passed_routes": sum(r["passed"] for r in value["route_results"]),
            }
        )
    )


if __name__ == "__main__":
    main()
