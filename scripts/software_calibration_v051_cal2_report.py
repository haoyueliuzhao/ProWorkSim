"""Read-only fixed-six-task CAL2 report; no model, tokenizer or test execution."""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import software_calibration_v051_report as common

VERSION = "software-calibration-v051-cal2-report-v1"
CONDITIONS = ("R", "P", "U")
TASKS = tuple(f"cal2-{repo}-{i}" for repo in ("boltons", "parse", "xmltodict") for i in (1, 2))
HOST_VERSION = "software-calibration-cal2-host-v0.51"


def validate_inventory(rows):
    if len(rows) != 18 or len({r["slot_id"] for r in rows}) != 18:
        raise ValueError("Keep the original eighteen unique slots, including unknown/unstarted")
    for i, task in enumerate(TASKS):
        order = (("R", "P", "U"), ("P", "U", "R"), ("U", "R", "P"))[i % 3]
        for row, condition in zip(rows[i * 3:i * 3 + 3], order, strict=True):
            if (row["task_id"] != task or row["condition"] != condition
                    or row["slot_id"] != f"v051-{task}-{condition}"
                    or row["seed"] != 202610170551 + i or row["generation_tokens"] != 500000
                    or row["decisions"] != 128 or row["attempts"] != 128
                    or row["project_public_tests"] != (None if condition == "R" else 32)):
                raise ValueError("CAL2 task, condition, seed, budget or order changed")


def finite_summary(values):
    if len(values) != 6 or any(v is not None and (isinstance(v, bool)
            or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1) for v in values):
        raise ValueError("Require the six fixed bounded task outcomes, with null for unknown")
    known = [v for v in values if v is not None]
    unresolved = 6 - len(known)
    return {"planned_tasks": 6, "known": len(known), "unknown": unresolved,
        "mean": sum(known) / 6 if unresolved == 0 else None,
        "bounds": [sum(known) / 6, (sum(known) + unresolved) / 6],
        "scope": "Six tasks equally weighted; missing outcomes are not failed tasks"}


def endpoint_metrics(rows, field, *, conditions=CONDITIONS):
    indexed = {(row["task_id"], row["condition"]): row for row in rows}
    if len(indexed) != 18 or set(indexed) != {(task, c) for task in TASKS for c in CONDITIONS}:
        raise ValueError("Metrics require the unique fixed6x3 panel")
    result = {condition: finite_summary([indexed[task, condition][field] for task in TASKS])
              for condition in conditions}
    if "R" not in conditions:
        result["R"] = {"applicable": False, "mean": None,
                       "reason": "Native mini framework has no project fixed-delivery endpoint"}
    for left, right in (("P", "R"), ("U", "P")):
        if left not in conditions or right not in conditions:
            continue
        a, b = result[left], result[right]
        result[f"{left}_minus_{right}"] = {
            "mean": a["mean"] - b["mean"] if a["mean"] is not None and b["mean"] is not None else None,
            "bounds": [a["bounds"][0] - b["bounds"][1], a["bounds"][1] - b["bounds"][0]],
            "paired_tasks": [{"task_id": task, "difference": indexed[task, left][field] - indexed[task, right][field]
                if indexed[task, left][field] is not None and indexed[task, right][field] is not None else None}
                for task in TASKS], "denominator": 6}
    return result


def terminal_test_summary(terminal):
    """Observe existing test receipts; do not turn unrun node bodies into failures."""
    assessment = terminal.get("assessment") or {}
    independent = assessment.get("independent_acceptance") or {}
    checks = independent.get("checks") or []
    execution = independent.get("execution") or {}
    if "checks" in terminal:
        checks = [{"case_id": row["nodeid"], "passed": row.get("passed"),
            "observed": {"pytest_status": row.get("pytest_status"),
                         "node_outcome_observed": row.get("node_outcome_observed")}}
            for row in terminal["checks"]]
        execution = terminal.get("execution") or {}
    observed = [row for row in checks if row.get("observed", {}).get("node_outcome_observed") is True]
    not_run = [row["case_id"] for row in checks
               if row.get("observed", {}).get("node_outcome_observed") is not True]
    passed = sum(row.get("observed", {}).get("pytest_status") == "passed" for row in observed)
    collection = execution.get("source_attributable_collection_failure") is True
    known = terminal.get("executed") is True and execution.get("executed") is True and bool(checks)
    q = passed / len(checks) if known else None
    issues = []
    if len({row["case_id"] for row in checks}) != len(checks):
        issues.append("duplicate_terminal_test_node")
    if known and (execution.get("source_unchanged") is not True or execution.get("test_integrity") is not True
                  or execution.get("unexpected_test_ids") or not_run and not collection):
        issues.append("terminal_test_source_or_missing_outcome_unresolved")
    if known and (terminal.get("Q_task") != q or terminal.get("tests_total") != len(checks)
                  or terminal.get("tests_passed") != passed):
        issues.append("terminal_observed_quality_does_not_match_full_denominator")
    expected_r = int(passed == len(checks) and not not_run) if known else None
    if terminal.get("R_code") != expected_r:
        issues.append("terminal_code_score_does_not_match_original_test_outcomes")
    return {"frozen_test_count": len(checks), "observed_test_nodes": len(observed),
        "observed_passed": passed if known else None,
        "observed_failed": sum(r["observed"]["pytest_status"] == "failed" for r in observed),
        "observed_errors": sum(r["observed"]["pytest_status"] == "error" for r in observed),
        "observed_skipped": sum(r["observed"]["pytest_status"] == "skipped" for r in observed),
        "not_run_count": len(not_run), "not_run_test_ids": not_run,
        "collection_failure": collection, "all_expected_tests_observed": execution.get("all_expected_tests_observed"),
        "Q_terminal": q, "Q_full_node_outcome_bounds": [q, (passed + len(not_run)) / len(checks)] if known else [0, 1],
        "Q_scope": "Observed passes / full original test denominator. With source-bound collection failure this is a conservative observed fraction; unrun nodes did not execute and fail.",
        "execution": execution, "binding_issues": issues}


def optional(reader, path, issues):
    path = Path(path)
    if not path.exists():
        return None
    try:
        return reader.load(path)
    except (OSError, ValueError) as error:
        issues.append({"kind": "unreadable_source", "path": str(path), "error": str(error)})
        return None


def native_receipts(reader, resident):
    """Each actual dispatch is keyed once, regardless of repeated framework refs."""
    calls = Path(resident) / "calls"
    groups, issues = {}, []
    for kind in ("prepared", "started", "complete", "fault"):
        groups[kind] = {p.name.removesuffix(f"-{kind}.json"): optional(reader, p, issues)
                        for p in sorted(calls.glob(f"*-{kind}.json"))}
    actual, reserved, unknown_reservations, bound_complete = 0, 0, 0, 0
    rows = []
    for key in sorted(set().union(*(set(items) for items in groups.values()))):
        prep, start, complete, fault = [groups[kind].get(key) for kind in groups]
        errors = []
        if start is not None and (prep is None or start.get("attempt_id") != key
                or start.get("generation_started") is not True
                or any(start.get(k) != prep.get(k) for k in ("actor_identity", "native_input", "reserved_maximum_tokens"))):
            errors.append("start_not_bound_to_preparation")
        charge = None
        if complete is not None:
            usage = complete.get("usage", {})
            if (start is None or complete.get("attempt_id") != key
                    or complete.get("input") != start.get("native_input")
                    or complete.get("actor_identity") != start.get("actor_identity")
                    or any(type(usage.get(k)) is not int for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
                    or usage["prompt_tokens"] != len(complete.get("input", {}).get("input_ids", []))
                    or usage["completion_tokens"] != len(complete.get("output_ids", []))
                    or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]
                    or not 0 < usage["total_tokens"] <= start.get("reserved_maximum_tokens", 0)):
                errors.append("complete_receipt_not_bound_to_actual_usage")
            elif not errors:
                charge = usage["total_tokens"]
                actual += charge
                bound_complete += 1
        uncertainty = 0
        if start is not None and charge is None:
            reservation = start.get("reserved_maximum_tokens")
            if type(reservation) is int and reservation > 0:
                uncertainty = reservation
                reserved += reservation
            else:
                uncertainty = None
                unknown_reservations += 1
                errors.append("unknown_reservation_amount")
        if complete is not None and start is None:
            unknown_reservations += 1
        if errors:
            issues.append({"attempt_id": key, "problems": errors})
        rows.append({"native_attempt_id": key, "generation_started": start is not None,
            "complete_record_present": complete is not None, "bound_actual_tokens": charge,
            "uncertain_reservation_tokens": uncertainty, "fault": fault,
            "actor_identity": (complete or start or prep or {}).get("actor_identity"),
            "generation_path": (complete or {}).get("path"),
            "finish_reason": (complete or {}).get("finish_reason"), "binding_issues": errors,
            "sources": {kind: reader.reference(calls / f"{key}-{kind}.json")
                        for kind in groups if key in groups[kind]}})
    return {"prepared_requests": len(groups["prepared"]), "started_generations": len(groups["started"]),
        "complete_generations": len(groups["complete"]), "bound_complete_generations": bound_complete,
        "known_actual_tokens": actual, "uncertain_reservation_tokens": reserved,
        "unknown_reservation_amount_count": unknown_reservations,
        "complete_actual_tokens": actual if not reserved and not unknown_reservations and not issues else None,
        "ledger_tokens": actual + reserved if not unknown_reservations else None,
        "prepared_without_generation": sorted(set(groups["prepared"]) - set(groups["started"])),
        "integrity_errors": issues, "rows": rows,
        "scope": "Known actual sum is a proved lower subtotal; unknown fees are not zero. Reservations are bounds, not actual billed tokens."}


def _guard_issues(report, owner, plan, condition):
    issues = []
    identity = owner.get("actor_identity", {})
    guard, episode = report.get("guard", {}), report.get("episode_guard", {})
    if (guard.get("passed") is not True or guard.get("actor_identity") != identity
            or not all(episode.get(k) is True for k in ("learning_unchanged", "rng_restored_exactly"))
            or owner.get("inference_profile", {}).get("path") != "project"
            or owner.get("inference_profile", {}).get("contract") != plan["contract"]
            or owner.get("optimizer_constructed") is not False or owner.get("critic_constructed") is not False
            or identity.get("base_manifest") != plan["model_manifest"]):
        issues.append("actor_numeric_path_or_final_guard_unresolved")
    if condition == "U":
        if (identity.get("checkpoint") != plan["S_star"]["checkpoint"]
                or identity.get("adapter_sha256") != plan["S_star"]["actor_identity"]["adapter_sha256"]
                or owner.get("historical_checkpoint_steps") != [4, 4]):
            issues.append("retained_S_star_actor_identity_unresolved")
    elif (identity.get("raw_release") is not True or identity.get("checkpoint") is not None
          or identity.get("trained_adapter_loaded") is not False):
        issues.append("raw_release_identity_unresolved")
    return issues


def refusal_counts(reader, result, measurement, condition, issues):
    if condition == "R":
        references = result.get("ledger", {}).get("preexecution_rejections")
        if references is None:
            return {"counts": None, "scope": "native refusal inventory unavailable"}
        reasons = []
        for item in references:
            try:
                path = Path(item["path"])
                actual = reader.reference(path)
                if actual["sha256"] != item["sha256"] or "bytes" in item and actual["bytes"] != item["bytes"]:
                    raise ValueError("Native refusal receipt bytes changed")
                reasons.append(reader.load(path)["reason"])
            except (OSError, KeyError, ValueError) as error:
                issues.append({"native_rejection_source_unresolved": str(error)})
                return {"counts": None, "references": references}
        return {"counts": dict(Counter(reasons)), "source_scope": "native exact preexecution receipts"}
    stop = measurement.get("stop_assessment", {})
    if (measurement.get("decision") != "continue" or not stop
            or stop.get("unresolved") or stop.get("global_violations")):
        return {"counts": None, "scope": "refusal measurement unresolved; missing proof is not zero"}
    proofs = stop.get("local_resource_rejections", {})
    return {"counts": dict(Counter(proof["reason"] for proof in proofs.values())),
        "proofs": proofs, "context_events": stop.get("local_context_events", []),
        "scope": "Existing bound member stop proofs, not feedback occurrences or repeated historical pages"}


def read_slot(reader, root, row, plan, state):
    folder = root / "slots" / row["slot_id"]
    issues = []
    start = optional(reader, folder / "started.json", issues)
    closed = optional(reader, folder / "closed.json", issues)
    selected = [] if start is None else [a for a in state["attempts"]
        if Path(a["output"]).resolve() == Path(start.get("attempt", "")).resolve()
        and a.get("pid") == start.get("pid")]
    report, accounting, tests, raw, evidence = {}, None, {}, {}, {}
    startup_only_known = not state["attempts"]
    if start is None and state["attempts"]:
        startup_only_known = True
        for attempt in state["attempts"]:
            path = Path(attempt["output"]) / "report.json"
            saved = optional(reader, path, issues)
            expected = {"status": "pre_model_resource_unavailable", "model_loader_entered": False,
                "generation_calls": 0, "slot_id": row["slot_id"], "source_plan": reader.reference(root / "plan.json")}
            if (saved != expected or saved != attempt.get("report") or attempt.get("exit_code") != 75
                    or attempt.get("reason") is not None):
                startup_only_known = False
        if not startup_only_known:
            issues.append("worker_attempt_without_bound_zero_model_startup_or_slot_entry")
    if start is not None:
        if (start.get("row") != row or start.get("source_plan") != reader.reference(root / "plan.json")
                or len(selected) != 1):
            issues.append("slot_start_not_bound_to_unique_host_attempt")
        if len(selected) == 1:
            attempt = selected[0]
            output = Path(attempt["output"])
            report = optional(reader, output / "report.json", issues) or {}
            accounting = native_receipts(reader, output / "resident")
            owner = optional(reader, output / "resident/owner.json", issues) or {}
            for name in ("interruption.json", "host-stop.json", "measurement.json",
                         "episode/interruption.json", "episode/deadline-receipt.json"):
                value = optional(reader, output / name, issues)
                if value is not None:
                    evidence[name] = {"source": reader.reference(output / name), "value": value}
            if (not report or not closed or closed.get("report") != reader.reference(output / "report.json")
                    or report != attempt.get("report") or report.get("row") != row
                    or report.get("source_plan") != reader.reference(root / "plan.json")
                    or attempt.get("exit_code") != 0 or state.get("status") != "complete"
                    or report.get("verdict", {}).get("decision") != "continue"
                    or report.get("measurement", {}).get("decision") != "continue"
                    or not attempt.get("child_cleanup")
                    or not all(c.get("passed") is True for c in attempt["child_cleanup"])):
                issues.append("worker_closure_or_mechanical_measurement_unresolved")
            issues.extend(_guard_issues(report, owner, plan, row["condition"]))
            saved_guard = optional(reader, output / "episode/evaluation-guard.json", issues)
            if saved_guard != report.get("episode_guard") or not saved_guard:
                issues.append("episode_guard_record_missing_or_different")
            if accounting["integrity_errors"] or accounting["complete_actual_tokens"] is None:
                issues.append("native_accounting_unresolved")
            for call in accounting["rows"]:
                if (call["actor_identity"] != owner.get("actor_identity")
                        or call["complete_record_present"] and call["generation_path"] != "project"):
                    issues.append("actual_native_actor_or_numerical_path_mismatch")
            host_accounting = report.get("accounting", {})
            if report and any(host_accounting.get(k) != accounting[k] for k in (
                    "prepared_requests", "started_generations", "complete_generations", "known_actual_tokens",
                    "uncertain_reservation_tokens", "complete_actual_tokens")):
                issues.append("host_accounting_differs_from_unique_native_receipts")
            raw = report.get("result", {})
            terminal = raw.get("terminal_code") or {}
            tests = terminal_test_summary(terminal)
            issues.extend(tests["binding_issues"])
            terminal_path = output / ("terminal-code/terminal-code-assessment.json" if row["condition"] == "R"
                                      else "episode/terminal-code/terminal-code-assessment.json")
            saved_terminal = optional(reader, terminal_path, issues)
            if saved_terminal != terminal or not terminal:
                issues.append("terminal_code_record_missing_or_different")
            if (raw.get("R_code") != terminal.get("R_code")
                    or raw.get("Q_task_terminal") != terminal.get("Q_task")):
                issues.append("terminal_result_values_differ")
            execution = tests.get("execution", {})
            if execution.get("evidence"):
                run_result = optional(reader, Path(execution["evidence"]) / "result.json", issues)
                if (not run_result or run_result.get("input_files_sha256") != execution.get("input_files_sha256")
                        or run_result.get("returncode") != execution.get("returncode")
                        or run_result.get("source_unchanged") is not True or run_result.get("test_integrity") is not True):
                    issues.append("shared_test_runner_source_unresolved")
            else:
                issues.append("shared_test_runner_evidence_missing")
            if row["condition"] == "R":
                if raw.get("task_id") != row["task_id"] or raw.get("seed") != row["seed"]:
                    issues.append("native_episode_task_or_seed_mismatch")
                canonical = terminal.get("canonical_tree") or {}
                raw_candidate = optional(reader, output / "terminal-code/raw-candidate-files.json", issues)
                grade_candidate = optional(reader, output / "terminal-code/grading-files.json", issues)
                canonical_source = optional(reader, output / "terminal-code/canonical-tree-receipt.json", issues)
                if (not canonical or canonical != canonical_source
                        or canonical.get("initial_files_sha256") != raw.get("initial_files_sha256")
                        or canonical.get("candidate_files_sha256") != raw.get("candidate_files_sha256")
                        or common.sha(common.json_bytes(raw_candidate)) != raw.get("candidate_files_sha256")
                        or common.sha(common.json_bytes(grade_candidate)) != terminal.get("grading_files_sha256")
                        or execution.get("input_files_sha256") != terminal.get("grading_files_sha256")):
                    issues.append("native_raw_and_authoritative_tree_binding_unresolved")
            elif (raw.get("slot_id") != row["slot_id"] or raw.get("case_id") != row["task_id"]
                    or raw.get("sampling_seed") != row["seed"] or raw.get("calibration_condition") != row["condition"]):
                issues.append("project_episode_identity_mismatch")
    elif closed:
        issues.append("closed_slot_missing_started_source")
    raw_code, raw_q = raw.get("R_code"), raw.get("Q_task_terminal")
    applicable = row["condition"] in ("P", "U")
    if start is not None and (type(raw_code) is not int or raw_code not in (0, 1)):
        issues.append("terminal_code_unknown")
    if start is not None and applicable and (type(raw.get("R_joint")) is not int or raw["R_joint"] not in (0, 1)):
        issues.append("fixed_delivery_unknown")
    refusals = refusal_counts(reader, raw, report.get("measurement", {}), row["condition"], issues)
    bound = start is not None and not issues
    if accounting is not None and not bound:
        accounting["complete_actual_tokens"] = None
    native_ledger = raw.get("ledger", {})
    administrative = (raw.get("administrative_censoring") if applicable else
        native_ledger.get("stop_reason") == "administrative_soft_deadline"
        or raw.get("upstream_limit_receipt", {}).get("terminal_status") == "TimeExceeded") if raw else None
    return {**row, "status": "closed" if bound else "technical_unknown" if start is not None or issues else "not_started",
        "source_bound": bound, "binding_issues": issues, "slot_entered": start is not None,
        "cost_integrity_known": bound or start is None and startup_only_known,
        "raw_R_code": raw_code, "R_code": raw_code if bound else None,
        "raw_Q_terminal": raw_q, "Q_terminal": raw_q if bound else None,
        "R_joint_applicable": applicable, "raw_R_joint": raw.get("R_joint") if applicable else None,
        "R_joint": raw.get("R_joint") if applicable and bound else None,
        "R_token": raw.get("R_token") if applicable and bound else None,
        "administrative_censoring": administrative,
        "raw_native_submission_signal": raw.get("native_submission_signal") if not applicable else None,
        "raw_stop_reason": native_ledger.get("stop_reason") if not applicable else raw.get("boundary"),
        "raw_preexecution_rejections": native_ledger.get("preexecution_rejections") if not applicable else None,
        "preexecution_refusal_measurement": refusals,
        "measurement": report.get("measurement"), "original_verdict": report.get("verdict"),
        "terminal_tests": tests, "accounting": accounting,
        "project_team_budget": raw.get("team_budget") if applicable else None,
        "raw_native_actions": raw.get("actions") if not applicable else None,
        "raw_native_public_tests": raw.get("public_tests") if not applicable else None,
        "host_final_evaluation_attempts": raw.get("host_final_evaluation_attempts",
            raw.get("terminal_code", {}).get("host_final_evaluation_attempts")),
        "host_final_test_executions": raw.get("host_final_test_executions",
            raw.get("terminal_code", {}).get("host_final_test_executions")),
        "worker_attempt": selected[0]["output"] if len(selected) == 1 else None,
        "gpu_index": selected[0].get("gpu", {}).get("index") if len(selected) == 1 else None,
        "report_source": reader.reference(Path(selected[0]["output"]) / "report.json") if report else None,
        "evidence": evidence}


def aggregate_cost(rows):
    usages = [r["accounting"] for r in rows if r["accounting"] is not None]
    known = sum(r["known_actual_tokens"] for r in usages)
    reserved = sum(r["uncertain_reservation_tokens"] for r in usages)
    source_unknown = any(r.get("cost_integrity_known") is not True for r in rows)
    keys = [(r["worker_attempt"], call["native_attempt_id"]) for r in rows if r["accounting"]
            for call in r["accounting"]["rows"] if call["generation_started"]]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate native request referenced by multiple slots")
    unknown_amount = sum(r["unknown_reservation_amount_count"] for r in usages)
    return {"known_actual_tokens": known, "uncertain_reservation_tokens": reserved,
        "unknown_reservation_amount_count": unknown_amount,
        "complete_actual_tokens": None if source_unknown else known,
        "known_plus_reserved_tokens": known + reserved if not unknown_amount else None,
        "started_generations": sum(r["started_generations"] for r in usages),
        "complete_generations": sum(r["complete_generations"] for r in usages),
        "source_bound_complete_generations": sum(r["bound_complete_generations"] for r in usages),
        "prepared_without_generation": sum(len(r["prepared_without_generation"]) for r in usages),
        "unstarted_slots": sum(not r["slot_entered"] for r in rows),
        "scope": "CAL2 only; CAL1 and nested generation/scoring durations are not added"}


def build_report(root, *, cal1_report=None):
    root, reader = Path(root).resolve(), common.Reader()
    plan, supervisor = reader.load(root / "plan.json"), reader.load(root / "supervisor.json")
    common._require_final(supervisor)
    if (plan.get("version") != HOST_VERSION or plan.get("sha256") != common.sha(common.json_bytes(
            {k: v for k, v in plan.items() if k != "sha256"}))
            or supervisor.get("plan") != reader.reference(root / "plan.json")):
        raise ValueError("Require the closed host and exact sealed CAL2 plan")
    validate_inventory(plan["rows"])
    states = supervisor["states"]
    if set(states) != {row["slot_id"] for row in plan["rows"]}:
        raise ValueError("Host slot inventory differs from the fixed18")
    costs = common.worker_cost(states)
    rows = [read_slot(reader, root, row, plan, states[row["slot_id"]]) for row in plan["rows"]]
    billing = aggregate_cost(rows)
    issues = [{"slot_id": row["slot_id"], "problems": row["binding_issues"]}
              for row in rows if row["binding_issues"]]
    issues.extend(costs["issues"])
    if not math.isclose(costs["gpu_worker_seconds"], supervisor.get("gpu_worker_seconds", -1), abs_tol=1e-6):
        issues.append({"kind": "host_worker_seconds_mismatch"})
    for key in ("known_actual_tokens", "uncertain_reservation_tokens", "started_generations", "complete_generations"):
        if supervisor.get("ledger", {}).get(key) != billing[key]:
            issues.append({"kind": "host_ledger_mismatch", "field": key,
                           "host": supervisor.get("ledger", {}).get(key), "bound": billing[key]})
    metrics = {field: endpoint_metrics(rows, field, conditions=("P", "U") if "joint" in field else CONDITIONS)
               for field in ("R_code", "raw_R_code", "Q_terminal", "raw_Q_terminal", "R_joint", "raw_R_joint")}
    ancillary = None
    if cal1_report is not None:
        old = reader.load(cal1_report)
        ancillary = {"source": reader.reference(cal1_report), "billing": old["billing"],
            "worker_cost": old["worker_cost"], "included_in_CAL2_costs": False}
    return {"version": VERSION, "created_at_beijing": dt.datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "root": str(root), "read_only": True, "plan": reader.reference(root / "plan.json"),
        "supervisor": reader.reference(root / "supervisor.json"), "host_status": supervisor["status"],
        "source_commit": plan["source_commit"], "source_files": plan["source_files"],
        "report_source": reader.reference(Path(__file__)), "binding_library": reader.reference(Path(common.__file__)),
        "rows": rows, "metrics": metrics, "billing": billing, "worker_cost": costs,
        "host_ledger": supervisor.get("ledger"), "integrity_issues": issues,
        "all18_source_bound": all(r["source_bound"] for r in rows),
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "original_pause": reader.load(root / "pause.json") if (root / "pause.json").exists() else None,
        "administrative_censoring_counts": {c: sum(r["administrative_censoring"] is True
            for r in rows if r["condition"] == c) for c in CONDITIONS},
        "contract": plan["contract"], "limits": plan["limits"], "gpu_preference": plan["gpu_preference"],
        "CAL1_ancillary_cost_only": ancillary, "source_manifest": list(reader.manifest.values()),
        "original_records_modified": False, "new_model_calls": 0, "new_scoring_calls": 0,
        "new_tokenizer_calls": 0, "new_actor_updates": 0, "new_critic_updates": 0,
        "new_backward_calls": 0, "HOLD_material_opened": False, "next_stage_released": False}


def display(value):
    return "null" if value is None else f"{value:.6f}" if isinstance(value, float) else str(value)


def markdown(report):
    b, cost = report["billing"], report["worker_cost"]
    lines = ["# v051 CAL2：固定六题、三条件只读结案", "",
        f"宿主终态`{report['host_status']}`；槽状态`{report['status_counts']}`。固定18槽全部来源闭合："
        f"`{report['all18_source_bound']}`。报告只读取原件，不新增模型、评分、分词或更新。", "",
        "R为原始mini-SWE单agent，P为原始模型的ProWorkSim S1，U为S_star actor4/4的同一S1。"
        "三条件均用同一project数值路径、独立fresh resident和原任务初态；R_code比较各自最终工作树。"
        "P/U的R_joint只衡量固定交付，R对此不适用，不能填0。", ""]
    for field, title in (("R_code", "末树代码正确性：来源绑定"), ("raw_R_code", "末树代码正确性：原记录"),
                         ("Q_terminal", "完整原测试观察分数：来源绑定"), ("R_joint", "固定交付：仅P/U")):
        lines += [f"## {title}", "", "| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |",
                  "|---|---|---:|---|"]
        for key, value in report["metrics"][field].items():
            if value.get("applicable") is False:
                lines.append(f"| {key} | N/A | N/A | N/A |")
            else:
                lines.append(f"| {key} | {value.get('known', 'paired')}/6 | {display(value['mean'])} | {value['bounds']} |")
        lines.append("")
    lines += ["每题等权，不按原测试数量、成功、提交或提前终止筛选。任一相关未知使完整均值或配对差保持null；"
        "界限只是未知结果在[0,1]内的范围。原结果与来源绑定口径并列，原非空值不因缺证被删除。", "",
        "## 完整18槽与原测试观察", "",
        "| 槽 | 原R_code | 绑定R_code | 原Q_terminal | 绑定Q_terminal | R_joint | 行政删失 | 测试已观察/总数 | 未运行 | 状态 |",
        "|---|---:|---:|---:|---:|---:|---|---|---:|---|"]
    for row in report["rows"]:
        t = row["terminal_tests"]
        lines.append(f"| {row['slot_id']} | {display(row['raw_R_code'])} | {display(row['R_code'])} | "
            f"{display(row['raw_Q_terminal'])} | {display(row['Q_terminal'])} | "
            f"{display(row['R_joint']) if row['R_joint_applicable'] else 'N/A'} | {display(row['administrative_censoring'])} | "
            f"{t.get('observed_test_nodes')}/{t.get('frozen_test_count')} | {t.get('not_run_count')} | {row['status']} |")
    lines += ["", "Q_terminal的分母固定为完整原测试集合。源码归因成立的collection失败可使R_code=0；"
        "未运行节点列为not-run，不能说这些节点执行后失败。此时已观察通过数/完整分母是保守观察分数，"
        "逐槽还列出缺节点及全节点结果界限。runner、权限或来源故障保留未知。", "",
        "## 费用、停止与资源", "",
        f"CAL2实际已知 **{b['known_actual_tokens']} token**，不确定预约 **{b['uncertain_reservation_tokens']} token**，"
        f"预约金额本身未知的请求{b['unknown_reservation_amount_count']}个；完整实际费用`{b['complete_actual_tokens']}`。"
        f"实际开始{b['started_generations']}次、完整回包{b['complete_generations']}次；"
        f"已准备但未派发{b['prepared_without_generation']}次。预约不是已知收费。", "",
        f"worker唯一{cost['unique_attempts']}个区间，共{cost['gpu_worker_seconds']:.6f}秒"
        f"（{cost['gpu_worker_hours']:.6f}小时）。装载、生成、测试与闭合已包含在内，不加嵌套时长。"
        "CAL1费用只在可选附列中给出，未加入CAL2费用。", "",
        "逐槽JSON保留context与预算执行前拒绝原件、宿主测量判定、原停止和中断回执。"
        "安全预算/context终止不自动变成技术未知；真实fault、费用/副作用或worker绑定未决不能填0。"
        "行政soft截止保留joint-policy观察；P/U的R_token在实际删失时保持null，不冒称纯token估计。", "",
        "## 解释范围", "",
        "只有三个公开仓库的六个人工合成缺陷任务；不是外部真实自然issue总体。R允许最多128次原生bash行动，"
        "P/U至多32次项目公开测试，界面、可用动作和交付流程不同，P−R并非单一组件的因果分离。"
        "末树代码正确性与固定交付不能互换。U−P仅描述本固定面板上的保留actor差异；没有新训练，"
        "不从有限任务推广一般协作、通用能力或训练收益。没有读取HOLD任务，也不自动启动下一阶段。", "",
        f"来源/测量未决：`{json.dumps(report['integrity_issues'], ensure_ascii=False)}`。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    parser.add_argument("--cal1-report", type=Path)
    args = parser.parse_args()
    outputs = [Path(str(args.output_prefix) + suffix) for suffix in (".json", ".md")]
    if any(p.exists() for p in outputs):
        raise FileExistsError("Preserve reports; use a fresh output prefix")
    result = build_report(args.root, cal1_report=args.cal1_report)
    for path, content in zip(outputs, [common.json_bytes(result), markdown(result).encode()]):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)
    print(json.dumps({"outputs": [str(p) for p in outputs], "statuses": result["status_counts"],
                      "billing": result["billing"], "new_model_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
