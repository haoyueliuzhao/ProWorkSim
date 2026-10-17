"""One-shot, read-only CAL1 final aggregation; never generates or grades code.

The final host state must be complete/paused and all recorded worker attempts
closed. Missing or unstarted outcomes retain the original 24-task denominator.
No weight files, GPU APIs, candidate code, or official scorer are executed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo


VERSION = "software-calibration-v051-cal1-final-v1"
ARMS = ("reference", "project")
EXPECTED_TASKS = 24
EXPECTED_SLOTS = 48
UPSTREAM_REVISION = "28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24"
ROOT = Path(__file__).resolve().parents[1]
GRADER_FILES = (
    "lcb_runner/lm_styles.py", "lcb_runner/utils/extraction_utils.py",
    "lcb_runner/evaluation/testing_util.py",
    "lcb_runner/evaluation/compute_code_generation_metrics.py",
    "lcb_runner/evaluation/pass_k_utils.py",
)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


class Reader:
    """Read each artifact once and retain its exact byte identity."""

    def __init__(self):
        self.cache = {}
        self.manifest = {}

    def read(self, path):
        path = Path(path).resolve()
        if path not in self.cache:
            value = path.read_bytes()
            self.cache[path] = value
            self.manifest[str(path)] = {
                "path": str(path), "bytes": len(value), "sha256": sha(value)}
        return self.cache[path]

    def reference(self, path):
        self.read(path)
        return dict(self.manifest[str(Path(path).resolve())])

    def load(self, path):
        return json.loads(self.read(path))

    def verified(self, item):
        path = Path(item["path"])
        if not path.is_absolute():
            path = ROOT / path
        actual = self.reference(path)
        if actual["sha256"] != item["sha256"] or actual["bytes"] != item["bytes"]:
            raise ValueError("Frozen source reference mismatch: " + str(path))
        return path


def outcome_summary(rows):
    """Fixed-denominator estimates and bounds, never an observed-only mean."""
    if len(rows) != EXPECTED_SLOTS:
        raise ValueError("Require all48 frozen CAL1 slots, including unstarted ones")
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in ARMS}
    result = {}
    for arm, subset in by_arm.items():
        if len(subset) != EXPECTED_TASKS or len({r["ordinal"] for r in subset}) != EXPECTED_TASKS:
            raise ValueError("Each path requires all24 distinct fixed task ordinals")
        if any(r["pass_at_1"] not in (0, 1, None) for r in subset):
            raise ValueError("Invalid outcome")
        successes = sum(r["pass_at_1"] == 1 for r in subset)
        failures = sum(r["pass_at_1"] == 0 for r in subset)
        unresolved = EXPECTED_TASKS - successes - failures
        result[arm] = {
            "planned_tasks": EXPECTED_TASKS, "successes": successes, "known_failures": failures,
            "known_outcomes": successes + failures, "unresolved": unresolved,
            "technical_unknown": sum(r["status"] == "technical_unknown" for r in subset),
            "not_started": sum(r["status"] == "not_started" for r in subset),
            "pass_at_1": successes / EXPECTED_TASKS if unresolved == 0 else None,
            "pass_at_1_bounds": [successes / EXPECTED_TASKS,
                                 (successes + unresolved) / EXPECTED_TASKS],
        }
    ref, project = result["reference"], result["project"]
    both_complete = ref["unresolved"] == project["unresolved"] == 0
    result["project_minus_reference"] = {
        "value": project["pass_at_1"] - ref["pass_at_1"] if both_complete else None,
        "bounds": [project["pass_at_1_bounds"][0] - ref["pass_at_1_bounds"][1],
                   project["pass_at_1_bounds"][1] - ref["pass_at_1_bounds"][0]],
        "denominator": EXPECTED_TASKS,
        "scope": "Full fixed paired panel; bounds describe unresolved outcomes, not imputed failures",
    }
    pairs = []
    for ordinal in range(EXPECTED_TASKS):
        pair = {arm: next(r for r in by_arm[arm] if r["ordinal"] == ordinal) for arm in ARMS}
        a, b = pair["reference"], pair["project"]
        if a["task_id"] != b["task_id"] or a["seed"] != b["seed"]:
            raise ValueError("Paired task/seed identity differs")
        x, y = a["pass_at_1"], b["pass_at_1"]
        label = "unresolved" if x is None or y is None else {
            (1, 1): "both_pass", (0, 0): "both_fail",
            (1, 0): "reference_only_pass", (0, 1): "project_only_pass"}[x, y]
        costs = [a.get("actual_tokens"), b.get("actual_tokens")]
        output_shas = [a.get("output_ids_sha256"), b.get("output_ids_sha256")]
        pairs.append({"ordinal": ordinal, "task_id": a["task_id"], "seed": a["seed"],
            "reference": x, "project": y, "classification": label,
            "project_minus_reference": y - x if x is not None and y is not None else None,
            "actual_token_difference": costs[1] - costs[0] if all(v is not None for v in costs) else None,
            "output_ids_equal": output_shas[0] == output_shas[1] if all(output_shas) else None})
    result["paired_classifications"] = dict(Counter(p["classification"] for p in pairs))
    return result, pairs


def generation_ledger(rows):
    complete = sum(r["actual_tokens"] is not None for r in rows)
    started = sum(r["attempted"] for r in rows)
    actual = sum(r["actual_tokens"] or 0 for r in rows)
    uncertain = sum(r["maximum_tokens"] for r in rows
                    if r["attempted"] and r["actual_tokens"] is None)
    return {"complete_generations": complete, "started_generations": started,
        "known_actual_tokens": actual, "uncertain_reservation_tokens": uncertain,
        "complete_actual_tokens": actual if uncertain == 0 else None,
        "ledger_tokens": actual + uncertain, "unstarted_slots": len(rows) - started,
        "scope": "Executed-generation cost only; unstarted inventory is not a zero-cost completed candidate"}


def worker_cost(states):
    """One cost for each unique worker attempt; never add nested model durations."""
    seen, attempts, issues, total = set(), [], [], 0.0
    for worker, state in states.items():
        for attempt in state.get("attempts", []):
            key = str(Path(attempt["output"]).resolve())
            if key in seen:
                issues.append({"kind": "duplicate_worker_attempt_reference", "output": key})
                continue
            seen.add(key)
            seconds = attempt.get("seconds")
            if (not isinstance(seconds, (int, float)) or isinstance(seconds, bool)
                    or not math.isfinite(seconds) or seconds < 0
                    or not isinstance(attempt.get("ended_at"), (int, float))):
                raise ValueError("A recorded worker attempt is not closed: " + key)
            total += seconds
            attempts.append({"worker": worker, "output": key, "pid": attempt.get("pid"),
                "gpu_index": attempt.get("gpu", {}).get("index"),
                "started_at": attempt.get("started_at"), "ended_at": attempt["ended_at"],
                "seconds": seconds, "exit_code": attempt.get("exit_code"),
                "host_stop_reason": attempt.get("reason"),
                "reported_status": attempt.get("report", {}).get("status")})
    return {"unique_attempts": len(attempts), "gpu_worker_seconds": total,
        "gpu_worker_hours": total / 3600, "attempts": attempts, "issues": issues,
        "scope": "Whole worker intervals including load/reservation/CPU grading/closure/failures; not kernel busy time. Nested generation seconds are not added."}


def _require_final(supervisor):
    if supervisor.get("status") not in ("complete", "paused") or supervisor.get("ended_at") is None:
        raise ValueError("Final aggregation requires a terminal complete/paused supervisor; no polling")
    if any(s.get("status") == "running" for s in supervisor.get("states", {}).values()):
        raise ValueError("A worker is still marked running")


def _evidence(reader, plan, suffix):
    items = [e["frozen_copy"] for e in plan["evidence"]
             if Path(e["frozen_copy"]["path"]).name.endswith(suffix)]
    if len(items) != 1:
        raise ValueError("One exact frozen evidence copy required: " + suffix)
    return reader.verified(items[0])


def _optional(reader, path, issues, label):
    if not path.exists():
        return None
    try:
        return reader.load(path)
    except (ValueError, OSError) as error:
        issues.append({"kind": "unreadable_record", "scope": label,
                       "path": str(path), "error": str(error)})
        return None


def external_interventions(reader, root, costs):
    """Bind the explicit new GPU relinquishment without renaming original stops."""
    result = []
    path = Path(root) / "gpu5-relinquishment.json"
    if path.exists():
        value = reader.load(path)
        matches = [attempt for attempt in costs["attempts"]
                   if attempt.get("pid") == value.get("pid")
                   and attempt.get("gpu_index") == value.get("requested_gpu")]
        bound = (value.get("kind") == "explicit_user_gpu_relinquishment"
                 and value.get("requested_gpu") == 5 and len(matches) == 1)
        result.append({"source": reader.reference(path), "kind": value.get("kind"),
             "reason": value.get("reason"), "requested_gpu": value.get("requested_gpu"),
             "pid": value.get("pid"), "at": value.get("at"),
             "worker_binding_known": bound,
             "worker_attempt": matches[0]["output"] if bound else None,
             "classification": "explicit_user_resource_relinquishment" if bound else "unresolved_external_receipt",
             "restart_or_resample_authorized": value.get("restart_or_resample_authorized"),
             "worker_released": value.get("release_observation", {}).get("worker_process_exists") is False,
             "original_host_stop_and_unknown_records_preserved": True,
             "not_an_algorithm_or_ordinary_resource_failure": bound})
    path = Path(root) / "gpu-idle-reschedule.json"
    if path.exists():
        value = reader.load(path)
        active = value.get("active_workers_at_request", [])
        matches = [[attempt for attempt in costs["attempts"]
                    if attempt.get("pid") == item.get("pid")
                    and attempt.get("gpu_index") == item.get("gpu")]
                   for item in active]
        bound = (value.get("kind") == "explicit_user_cancel_active_gpu_and_reschedule_when_idle"
                 and bool(active) and all(len(items) == 1 for items in matches)
                 and value.get("no_started_request_replay") is True)
        result.append({"source": reader.reference(path), "kind": value.get("kind"),
            "instruction": value.get("instruction"), "at": value.get("requested_at"),
            "worker_binding_known": bound,
            "worker_attempts": [items[0]["output"] for items in matches] if bound else None,
            "classification": "explicit_user_idle_rescheduling" if bound else "unresolved_external_receipt",
            "allowed_gpu_indices": value.get("allowed_gpu_indices"),
            "max_residents": value.get("max_residents"),
            "no_started_request_replay": value.get("no_started_request_replay"),
            "original_host_stop_and_unknown_records_preserved": True,
            "not_an_algorithm_or_ordinary_resource_failure": bound})
    return result


def _slot(reader, root, row, case, task_metadata, plan, source_lock, states):
    directory = root / "slots" / row["slot_id"]
    problems = []

    def check(value, label):
        if not value:
            problems.append(label)

    parse_issues = []
    start = _optional(reader, directory / "started.json", parse_issues, row["slot_id"])
    native = _optional(reader, directory / "native-input.json", parse_issues, row["slot_id"])
    generated = _optional(reader, directory / "generation.json", parse_issues, row["slot_id"])
    grade = _optional(reader, directory / "grade/result.json", parse_issues, row["slot_id"])
    attempted = (directory / "started.json").exists() or (directory / "generation.json").exists()
    actual_tokens, output_hash, finish, seconds = None, None, None, None
    gpu_index, worker_attempt = None, None
    if start is not None:
        check(start.get("row") == row, "started_row_identity")
        if native is not None:
            check(start.get("native_input") == reader.reference(directory / "native-input.json"),
                  "started_native_input_source")
        matches = [a for a in states[row["worker"]]["attempts"]
                   if a.get("pid") == start.get("pid")
                   and a["started_at"] <= start.get("started_at", -1) <= a["ended_at"]]
        check(len(matches) == 1, "unique_own_worker_attempt")
        if len(matches) == 1:
            gpu_index = matches[0].get("gpu", {}).get("index")
            worker_attempt = matches[0]["output"]
            check(matches[0].get("report", {}).get("guard", {}).get("passed") is True,
                  "worker_final_readonly_guard_known_passed")
    if generated is not None:
        check(start is not None and native is not None, "complete_generation_has_prepared_sources")
        check(generated.get("path") == row["arm"], "generation_path_identity")
        check(generated.get("input") == native, "generation_native_input_exact")
        if isinstance(native, dict):
            check(native.get("input_ids") == case["input_ids"], "exact_locked_input_ids")
            check(native.get("rendered_prompt") == case["rendered_prompt"], "exact_locked_rendering")
            check(native.get("sha256") == sha(json_bytes({k: v for k, v in native.items() if k != "sha256"})),
                  "native_input_seal")
        usage, ids = generated.get("usage", {}), generated.get("output_ids")
        usage_ok = (isinstance(ids, list) and 0 < len(ids) <= plan["contract"]["max_output_tokens"]
                    and all(type(v) is int for v in ids)
                    and usage.get("prompt_tokens") == len(case["input_ids"])
                    and usage.get("completion_tokens") == len(ids)
                    and usage.get("total_tokens") == len(case["input_ids"]) + len(ids)
                    and usage["total_tokens"] <= row["maximum_tokens"])
        check(usage_ok, "actual_token_accounting")
        if usage_ok:
            actual_tokens = usage["total_tokens"]
            output_hash = sha(canonical_bytes(ids))
        identity = generated.get("actor_identity", {})
        check(identity.get("raw_release") is True and identity.get("trained_adapter_loaded") is False
              and identity.get("checkpoint") is None, "raw_release_without_trained_adapter")
        check(identity.get("base_manifest") == plan["model_manifest"], "base_manifest_identity")
        check(all(generated.get(k) == 0 for k in ("new_actor_steps", "new_critic_steps", "new_backward_calls")),
              "zero_learning_counters")
        finish, seconds = generated.get("finish_reason"), generated.get("seconds")
        check(finish in ("stop", "length", "time_limit"), "identified_native_finish")
        if isinstance(ids, list):
            ends = [i for i, value in enumerate(ids) if value in plan["contract"]["eos_token_ids"]]
            check(not ends or ends == [len(ids) - 1], "no_post_EOS_tail")
            check((finish == "stop" and bool(ends))
                  or (finish == "length" and not ends
                      and len(ids) == plan["contract"]["max_output_tokens"])
                  or (finish == "time_limit" and not ends
                      and isinstance(seconds, (int, float))
                      and seconds >= plan["contract"]["max_generation_seconds"]),
                  "native_finish_matches_saved_boundary")
    if parse_issues:
        problems.extend(item["kind"] + ":" + item["path"] for item in parse_issues)
    reported_grade = grade.get("pass_at_1") if isinstance(grade, dict) else None
    result = None
    if grade is not None:
        check(generated is not None, "grade_has_original_generation")
        check(grade.get("evaluation_sample_sha256") == sha(canonical_bytes(case["evaluation_sample"])),
              "same_all_public_private_sample")
        check(grade.get("per_test_seconds") == 6 and grade.get("grading_attempts") == 1
              and grade.get("candidate_generations_added") == 0, "frozen_score_budget")
        expected_sources = {r["path"]: r["sha256"] for r in source_lock["scoring"]["upstream_files"]}
        upstream = grade.get("upstream", {})
        check(upstream.get("revision") == UPSTREAM_REVISION
              and upstream.get("files") == {k: expected_sources[k] for k in GRADER_FILES},
              "exact_official_grader_sources")
        code_path = directory / "grade/extracted-code.py"
        check(code_path.exists(), "extracted_code_preserved")
        if code_path.exists():
            check(grade.get("code_sha256") == sha(reader.read(code_path)), "exact_extracted_code")
        if generated is not None:
            raw = generated.get("raw_generated_text")
            check(isinstance(raw, str) and grade.get("raw_output_sha256") == sha(raw.encode()),
                  "score_of_exact_generated_output")
        tests = json.loads(case["evaluation_sample"]["input_output"])
        check(grade.get("official_test_count") == len(tests["inputs"]), "all_locked_tests_declared")
        if grade.get("status") in ("passed", "official_incorrect"):
            reply = grade.get("official_reply") or {}
            values, metadata = reply.get("results"), reply.get("metadata")
            valid = (isinstance(values, list) and bool(values)
                     and all(type(v) in (int, bool, float) for v in values)
                     and len(values) <= len(tests["inputs"]) and isinstance(metadata, dict)
                     and metadata.get("error_code") != -5)
            check(valid, "native_score_reply_present")
            if valid:
                expected = int(all(v > 0 for v in values))
                check(expected == reported_grade and type(reported_grade) is int,
                      "reported_pass_matches_native_results")
                check(not expected or len(values) == len(tests["inputs"]), "positive_reply_complete")
                check(grade.get("sandbox") is not None and grade.get("returncode") == 0
                      and grade.get("host_wall_timeout") is False
                      and grade.get("output_truncated") is False, "score_envelope_closed")
                if not problems:
                    result = reported_grade
        else:
            check(grade.get("status") == "technical_unknown" and reported_grade is None,
                  "explicit_unknown_score_not_imputed")
    status = ("passed" if result == 1 else "official_incorrect" if result == 0 else
              "technical_unknown" if attempted or grade is not None or problems else "not_started")
    metadata = ((grade or {}).get("official_reply") or {}).get("metadata") or {}
    return {**row, "difficulty": task_metadata["difficulty"], "contest_date": task_metadata["contest_date"],
        "status": status, "pass_at_1": result, "original_grade_pass_at_1": reported_grade,
        "original_grade_status": (grade or {}).get("status"), "attempted": attempted,
        "generation_record_present": (directory / "generation.json").exists(),
        "actual_tokens": actual_tokens, "output_ids_sha256": output_hash,
        "native_finish_reason": finish, "generation_seconds_nested": seconds,
        "extraction_empty": (grade or {}).get("extraction_empty"),
        "native_error_code": metadata.get("error_code"), "native_error_message": metadata.get("error_message"),
        "grader_host_wall_timeout": (grade or {}).get("host_wall_timeout"),
        "grader_returncode": (grade or {}).get("returncode"),
        "gpu_index": gpu_index, "worker_attempt": worker_attempt,
        "binding_issues": problems,
        "generation_source": reader.reference(directory / "generation.json") if generated is not None else None,
        "grade_source": reader.reference(directory / "grade/result.json") if grade is not None else None}


def build_report(root):
    root, reader = Path(root).resolve(), Reader()
    supervisor = reader.load(root / "supervisor.json")
    _require_final(supervisor)
    plan = reader.load(root / "plan.json")
    if (plan.get("version") != "software-calibration-host-v0.51"
            or plan.get("sha256") != sha(json_bytes({k: v for k, v in plan.items() if k != "sha256"}))):
        raise ValueError("Require the original sealed CAL1 plan")
    if len(plan["rows"]) != EXPECTED_SLOTS or plan["maximum_actual_tokens"] != 3959768:
        raise ValueError("Frozen CAL1 inventory or token bound changed")
    if (supervisor.get("plan") != reader.reference(root / "plan.json")
            or sum(r["maximum_tokens"] for r in plan["rows"]) != plan["maximum_actual_tokens"]):
        raise ValueError("Terminal host/plan identity or fixed token sum differs")
    source_lock = reader.load(_evidence(reader, plan, "software-calibration-v051-source-lock.json"))
    cases = reader.load(reader.verified(plan["cases"]))
    tasks = {t["ordinal"]: t for t in source_lock["tasks"]}
    if len(cases) != EXPECTED_TASKS or set(tasks) != set(range(EXPECTED_TASKS)):
        raise ValueError("Require all24 locked cases and metadata")
    states = supervisor["states"]
    if set(states) != {f"shard-{i}" for i in range(4)}:
        raise ValueError("Frozen worker inventory changed")
    costs = worker_cost(states)
    issues = list(costs["issues"])
    worker_evidence = []
    declared_outputs = {str(Path(a["output"]).resolve()) for s in states.values() for a in s["attempts"]}
    for name, state in states.items():
        observed = {str(p.resolve()) for p in (root / name).glob("attempt-*") if p.is_dir()}
        if observed - declared_outputs:
            issues.append({"kind": "worker_directory_not_in_final_host_state", "paths": sorted(observed - declared_outputs)})
        for attempt in state["attempts"]:
            output = Path(attempt["output"])
            record = {"worker": name, "output": str(output), "host_attempt": attempt}
            for filename in ("report.json", "task.json", "host-stop.json",
                             "startup/startup-resource-receipt.json"):
                path = output / filename
                if path.exists():
                    value = reader.load(path)
                    record[filename] = {"source": reader.reference(path), "value": value}
                    if filename == "report.json" and value != attempt.get("report"):
                        issues.append({"kind": "worker_report_differs_from_host_closure", "path": str(path)})
            faults = []
            for path in sorted((output / "resident/calls").glob("*-fault.json")):
                value = reader.load(path)
                faults.append({"source": reader.reference(path), "attempt_id": value.get("attempt_id"),
                    "generation_started": value.get("generation_started"), "error": value.get("error"),
                    "reserved_maximum_tokens": value.get("reserved_maximum_tokens"),
                    "actual_usage": value.get("actual_usage"), "scope": "Nested call evidence, not an additional worker charge"})
            record["native_faults"] = faults
            worker_evidence.append(record)
    rows = []
    for row in plan["rows"]:
        ordinal, arm = row["ordinal"], row["arm"]
        if (arm not in ARMS or row["slot_id"] != f"cal1-{ordinal + 1:02d}-{arm}"
                or row["seed"] != 202610170511 + ordinal
                or row["worker"] != f"shard-{ordinal // 6}"
                or row["task_id"] != cases[ordinal]["task_id"]
                or row["task_id"] != tasks[ordinal]["task_id"]
                or row["prompt_tokens"] != len(cases[ordinal]["input_ids"])
                or row["maximum_tokens"] != row["prompt_tokens"] + plan["contract"]["max_output_tokens"]):
            raise ValueError("Frozen task identity or order changed")
        rows.append(_slot(reader, root, row, cases[ordinal], tasks[ordinal], plan, source_lock, states))
    metrics, pairs = outcome_summary(rows)
    billing = generation_ledger(rows)
    original_ledger = supervisor.get("ledger", {})
    compare_keys = ("complete_generations", "started_generations", "known_actual_tokens",
                    "uncertain_reservation_tokens", "complete_actual_tokens", "ledger_tokens")
    ledger_matches = all(original_ledger.get(k) == billing[k] for k in compare_keys)
    if not ledger_matches:
        issues.append({"kind": "host_ledger_differs_from_bound_generation_records",
                       "fields": {k: {"host": original_ledger.get(k), "analysis": billing[k]}
                                  for k in compare_keys if original_ledger.get(k) != billing[k]}})
    original_seconds = supervisor.get("gpu_worker_seconds")
    if (not isinstance(original_seconds, (int, float))
            or not math.isclose(original_seconds, costs["gpu_worker_seconds"], abs_tol=1e-6)):
        issues.append({"kind": "host_worker_seconds_differ", "host": original_seconds,
                       "unique_attempt_sum": costs["gpu_worker_seconds"]})
    preparation = {}
    for suffix in ("source-preparation-control.json", "scoring-control-summary.json",
                   "runtime-controls-summary.json", "runtime-sampling-cpu-controls.json",
                   "host-controls.json", "loading-info-incremental-control.json",
                   "stop-policy-correction.json"):
        path = _evidence(reader, plan, suffix)
        preparation[suffix] = {"source": reader.reference(path), "value": reader.load(path)}
    group_item = source_lock["artifacts"]["scoring_process_group_correction"]
    group_path = reader.verified(group_item)
    preparation["scoring-process-group-correction.json"] = {
        "source": reader.reference(group_path), "value": reader.load(group_path)}
    pause = reader.load(root / "pause.json") if (root / "pause.json").exists() else None
    external = external_interventions(reader, root, costs)
    if any(row["binding_issues"] for row in rows):
        issues.append({"kind": "slot_binding_issues", "slots": [r["slot_id"] for r in rows if r["binding_issues"]]})
    diagnostics = {arm: {
        "native_finish_counts": dict(Counter(r["native_finish_reason"] or "no_complete_generation" for r in rows if r["arm"] == arm)),
        "extraction_empty": sum(r["extraction_empty"] is True for r in rows if r["arm"] == arm),
        "native_error_codes": dict(Counter(str(r["native_error_code"]) for r in rows if r["arm"] == arm and r["native_error_code"] is not None)),
        "known_actual_tokens": sum(r["actual_tokens"] or 0 for r in rows if r["arm"] == arm),
        "complete_generations": sum(r["actual_tokens"] is not None for r in rows if r["arm"] == arm),
    } for arm in ARMS}
    return {
        "version": VERSION, "created_at_beijing": dt.datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "root": str(root), "read_only": True, "original_records_modified": False,
        "new_model_calls": 0, "new_scoring_calls": 0, "new_tokenizer_calls": 0,
        "new_actor_updates": 0, "new_critic_updates": 0, "new_backward_calls": 0,
        "plan": reader.reference(root / "plan.json"), "source_commit": plan["source_commit"],
        "report_generator_source": reader.reference(Path(__file__)),
        "original_supervisor_status": supervisor["status"], "original_supervisor": reader.reference(root / "supervisor.json"),
        "original_pause": pause, "contract": plan["contract"], "limits": plan["limits"],
        "external_interventions": external,
        "metrics": metrics, "pairs": pairs, "rows": rows, "diagnostics": diagnostics,
        "all48_source_bound_outcomes_known": all(r["pass_at_1"] is not None for r in rows),
        "billing": billing, "original_host_ledger": original_ledger,
        "host_ledger_matches": ledger_matches, "worker_cost": costs,
        "original_host_worker_seconds": original_seconds, "worker_evidence": worker_evidence,
        "integrity_issues": issues, "source_and_measurement_integrity": not issues,
        "preparation_and_corrections": preparation,
        "source_manifest": list(reader.manifest.values()),
        "scope": "CAL1 only. CAL0 was an earlier read-only check; CAL2/HOLD readiness or outcomes are not inferred here.",
        "interpretation": [
            "24 difficulty-stratified v6-increment tasks; not the cumulative1055 or vendor65.6 replication.",
            "Both paths share HF generator and common BF16 backbone/FP32 head; not independent engines.",
            "No learning update, no after-output correction, no extra candidate, no score threshold.",
            "Fixed24 denominator includes unresolved and unstarted slots; full mean/difference null until every relevant outcome known.",
            "Worker time includes nested generation and CPU scoring exactly once; not GPU kernel utilization.",
        ],
    }


def _value(value, digits=6):
    return "null" if value is None else f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def markdown(report):
    metrics, billing, costs = report["metrics"], report["billing"], report["worker_cost"]
    lines = ["# v051 CAL-1：原始Qwen3.5-9B两路推理桥接终态", "",
        f"正式宿主终态为`{report['original_supervisor_status']}`。固定48个单候选槽中，"
        f"{billing['complete_generations']}个生成有完整费用，"
        f"{billing['started_generations'] - billing['complete_generations']}个已开始但缺完整回包，"
        f"{billing['unstarted_slots']}槽未启动。"
        "本报告只读汇总原始结果，没有新增生成、评分、分词或参数更新。", "",
        f"冻结执行提交：`{report['source_commit']['code_commit']}`。来源绑定是否全部闭合："
        f"`{report['source_and_measurement_integrity']}`；48槽来源绑定后的结果全部已知："
        f"`{report['all48_source_bound_outcomes_known']}`。原停止与未决记录均保留。", "",
        "## 固定24题的结果", "",
        "| 路径 | 成功 | 已知失败 | 技术未知 | 未启动 | 完整pass@1 | unresolved上下界 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for arm in ARMS:
        value = metrics[arm]
        bounds = value["pass_at_1_bounds"]
        lines.append(f"| {arm} | {value['successes']}/24 | {value['known_failures']} | "
                     f"{value['technical_unknown']} | {value['not_started']} | {_value(value['pass_at_1'])} | "
                     f"[{_value(bounds[0])}, {_value(bounds[1])}] |")
    delta = metrics["project_minus_reference"]
    lines += ["", f"完整配对差project−reference为 **{_value(delta['value'])}**。"
              "存在未决时，该值保持null；区间是未决结果的显式界，不是把未知当失败。",
              f"配对分类：`{json.dumps(metrics['paired_classifications'], ensure_ascii=False, sort_keys=True)}`。", "",
              "| 题 | reference | project | project−reference | 输出IDs同值 | token差 |",
              "|---|---:|---:|---:|---|---:|"]
    for pair in report["pairs"]:
        lines.append(f"| `{pair['task_id']}` | {_value(pair['reference'])} | {_value(pair['project'])} | "
                     f"{_value(pair['project_minus_reference'])} | {_value(pair['output_ids_equal'])} | "
                     f"{_value(pair['actual_token_difference'])} |")
    lines += ["", "这些读数只涉及事前固定的24题、每路单候选。"
              "[官方Qwen模型卡](https://huggingface.co/Qwen/Qwen3.5-9B)的LCB v6=65.6不作为门槛；"
              "本面板是[官方v6增量来源](https://huggingface.co/datasets/livecodebench/code_generation_lite/tree/0fe84c3912ea0c4d4a78037083943e8f0c4dd505)的难度分层样本，"
              "不是累计1,055题或厂商完整recipe复现。", "",
              "## 停止、提取与费用", "",
              "| 路径 | 完整生成 | 已知实际token | 原生终止计数 | 提取为空 | 官方错误码 |",
              "|---|---:|---:|---|---:|---|"]
    for arm in ARMS:
        d = report["diagnostics"][arm]
        lines.append(f"| {arm} | {d['complete_generations']} | {d['known_actual_tokens']:,} | "
                     f"`{json.dumps(d['native_finish_counts'], sort_keys=True)}` | {d['extraction_empty']} | "
                     f"`{json.dumps(d['native_error_codes'], sort_keys=True)}` |")
    lines += ["", f"已知实际生成量 **{billing['known_actual_tokens']:,} token**；"
              f"无完整回包的保守预约 **{billing['uncertain_reservation_tokens']:,} token**；"
              f"完整实际费用为`{billing['complete_actual_tokens']}`。预约不是已证实实际费用。"
              f"原宿主账本与只读重算一致：`{report['host_ledger_matches']}`。", "",
              f"唯一{costs['unique_attempts']}个worker区间共 **{costs['gpu_worker_seconds']:.6f}秒"
              f"（{costs['gpu_worker_hours']:.6f}小时）**。包含装载、资源预留、生成、CPU评分、收尾和失败区间；"
              "原生生成耗时已经嵌套其中，不再次加总。这不是GPU kernel忙时。", "",
              "| worker | attempt | GPU | 秒 | 退出码 | 原终态/停止原因 |",
              "|---|---|---:|---:|---:|---|"]
    for a in costs["attempts"]:
        lines.append(f"| {a['worker']} | `{Path(a['output']).name}` | {a['gpu_index']} | "
                     f"{a['seconds']:.6f} | {a['exit_code']} | "
                     f"{a['reported_status']} / {a['host_stop_reason']} |")
    if report.get("external_interventions"):
        lines += ["", "本轮另有用户明确要求让渡GPU5、撤销在途GPU实验并改为空闲调度的外部有意中断。"
                  "该回执按GPU、PID绑定原worker，并保留宿主原停止名称与调用未知；"
                  "不将它解释为算法失败或普通显存故障，也不据此重采。",
                  f"外部干预：`{json.dumps(report['external_interventions'], ensure_ascii=False)}`。"]
    lines += ["", "## 全48槽附表", "",
              "| 槽 | seed | GPU | 终态 | pass@1 | finish | native错误码 | 实际token |",
              "|---|---:|---:|---|---:|---|---|---:|"]
    for row in report["rows"]:
        lines.append(f"| `{row['slot_id']}` | {row['seed']} | {_value(row['gpu_index'])} | "
                     f"{row['status']} | {_value(row['pass_at_1'])} | {row['native_finish_reason']} | "
                     f"{row['native_error_code']} | {_value(row['actual_tokens'])} |")
    lines += ["", "## 原件与解释限制", "",
              "报告JSON逐项列出generation、grade、原始task/worker/账本、native故障与来源SHA。"
              "评分严格复用同一完整公共+私有样本；未重新执行候选代码。"
              "官方空metadata故障、原生fatal退出或评分缺回包保留技术未知，未补为0。"
              "若worker的终态只读guard缺失，原grade分数仍单独保留，来源绑定后的分析值为null。", "",
              "准备阶段的下载截断/ETag判断、tokenizer返回类型、宿主Path类型和测试收集错误均继续保留。"
              "双EOS修订、loading-info序列化增量控制，以及评分子进程继承worker进程组的静态修订各有独立回执；"
              "原控制汇总和原失败没有回写。报告生成不重复这些控制。", "",
              "两路共享HF生成器、BF16主干与FP32输出头；reference为官方支持入口下的共同数值桥接，"
              "project保留v020注意力路径。相同题、seed、模式、解码和评分减少比较混杂，但不证明逐token等价，"
              "也不把有限差异唯一归因于某一组件。新增训练为0，结果不构成学习收益证据。", "",
              "CAL-0是先前独立的只读核查；CAL-2/HOLD的任务资格与结果不由本报告推断。"
              "本报告不启动任何后继、旧训练或缓存生产。", "",
              f"来源/测量问题：`{json.dumps(report['integrity_issues'], ensure_ascii=False)}`。",
              f"原pause记录：`{json.dumps(report['original_pause'], ensure_ascii=False)}`。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    destinations = [Path(str(args.output_prefix) + suffix) for suffix in (".json", ".md")]
    if any(path.exists() for path in destinations):
        raise FileExistsError("Keep original reports; use a new output prefix instead of overwriting")
    report = build_report(args.root)
    text = markdown(report)
    for path in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
    with destinations[0].open("xb") as stream:
        stream.write(json_bytes(report))
    with destinations[1].open("x") as stream:
        stream.write(text)
    print(json.dumps({"status": report["original_supervisor_status"],
        "output": [str(p.resolve()) for p in destinations],
        "complete_generations": report["billing"]["complete_generations"],
        "metrics": report["metrics"], "new_model_calls": 0, "new_scoring_calls": 0},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
