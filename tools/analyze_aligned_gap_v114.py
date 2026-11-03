#!/usr/bin/env python3
"""Read-only v111/v113 analysis with explicit v114 continuation/scoring overlays.

No project runtime imports, model calls, Docker calls, hidden reference patches,
source snapshots, or database writes. Optional score overrides must be an
explicit JSON list of {slot_id, code_result: bool, code_status: "scored", evidence}.
Recovered stopped candidates need measurement_kind="recovered_stopped_code";
they are supplemental unless --include-stopped-candidates-in-main is explicit.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


ROOT = Path(__file__).resolve().parents[1]
VERSION = "v114-read-only-aligned-gap-analysis-r2"
TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
CONTINUATION_SLOTS = frozenset({7238, 7239, 7266, 7267})
ORDINARY_RESCORE_SLOTS = frozenset({7232, 7283})
STOPPED_CANDIDATE_SLOTS = frozenset({7244, 7251})


class Reader:
    def __init__(self):
        self.sources = {}

    def text(self, path):
        path = Path(path).resolve()
        data = path.read_bytes()
        self.sources[str(path)] = {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        return data.decode("utf-8")

    def json(self, path, default=None):
        if not Path(path).is_file():
            return default
        return json.loads(self.text(path))


def tally_calls(calls):
    result = {}
    for call in calls:
        purpose = call["purpose"]
        row = result.setdefault(purpose, {"requests": 0, **{f: 0 for f in TOKEN_FIELDS}, "total_tokens": 0, "cost_CNY": 0.0})
        row["requests"] += 1
        for field in TOKEN_FIELDS:
            if call.get(field) is not None:
                row[field] += call[field]
        row["total_tokens"] += call["prompt_tokens"] + call["completion_tokens"]
        row["cost_CNY"] += float(call.get("accounted_cost_cny") or 0)
    return result


def compact(value, limit=1400):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "…[excerpt]"


def public_tests(reader, out):
    results = []
    for path in sorted((out / "public-test-rpc").glob("test-*/response.json")):
        response = reader.json(path)
        request = reader.json(path.with_name("request.json"), {})
        execution = response.get("execution", {})
        output = "\n".join(str(g.get("output", "")) for g in response.get("groups", {}).values())
        results.append({"evidence": str(path), "selection": request.get("public_test_selection"),
                        "source_reference": request.get("source_reference"), "tree_sha256": request.get("tree_sha256"),
                        "executed": execution.get("executed"), "passed": response.get("passed"),
                        "returncode": execution.get("returncode"), "timed_out": execution.get("timed_out"),
                        "wall_seconds": execution.get("wall_seconds"),
                        "collection_errors": response.get("repository_collection_errors", []),
                        "output_excerpt": compact(output[-2800:], 2800)})
    return results


def project_actions(boundary):
    counts, statuses, page_actions, paginated, errors, error_messages = [collections.Counter() for _ in range(6)]
    details = []
    for ordinal, item in enumerate(boundary.get("outcomes", []), 1):
        decision = item.get("decision", {})
        action = decision.get("action")
        args = decision.get("arguments", {})
        response = item.get("response", {})
        result = response.get("result", {})
        statuses[item.get("status", "missing")] += 1
        if action:
            counts[action] += 1
        if args.get("cursor") or args.get("next_cursor"):
            page_actions[action] += 1
        if isinstance(result, dict) and result.get("next_cursor"):
            paginated[action] += 1
        failed = response.get("ok") is False or item.get("status") in {"model_format_feedback", "model_boundary_error"}
        if failed:
            errors[action or item.get("status", "unknown")] += 1
            error_messages[str((response.get("error") or {}).get("message") or item.get("reason") or "unspecified")] += 1
        # Keep actionable evidence, without copying full source-file observations.
        picked = {k: v for k, v in result.items() if k in {"error", "message", "reason", "status", "passed", "source_reference", "version_id", "complete", "next_cursor", "path", "submission_id", "patch_id", "execution", "test_run_id", "scanned_characters", "considered_files"}} if isinstance(result, dict) else result
        if failed or action in {"run_tests", "read_test_output", "read_test_result", "fix_patch", "submit_integration", "edit_file", "replace_file", "write_file", "create_file", "delete_file", "rename_file"} or item.get("status") in {"completed", "model_budget_exhausted"}:
            details.append({"ordinal": ordinal, "status": item.get("status"), "action": action,
                            "arguments": args, "response_ok": response.get("ok"), "result_excerpt": compact(picked),
                            "reason": item.get("reason"), "error": response.get("error")})
    return {"action_counts": dict(counts), "outcome_status_counts": dict(statuses),
            "pagination_continuation_actions": dict(page_actions), "responses_with_next_cursor": dict(paginated),
            "explicit_error_counts": dict(errors), "explicit_error_message_counts": dict(error_messages), "selected_action_evidence": details}


def native_actions(reader, out):
    rows = reader.json(out / "native-rpc-transcript.json", [])
    counts, errors = collections.Counter(), collections.Counter()
    tests = []
    for row in rows:
        request, response = row.get("request", {}), row.get("response", {})
        tool = request.get("tool")
        if not tool:
            continue
        counts[tool] += 1
        observation = response.get("observation", {})
        if observation.get("is_error") or observation.get("exit_code") not in (None, 0):
            errors[tool] += 1
        command = request.get("action", {}).get("command", "")
        if not isinstance(command, str):
            continue
        # A command-level heuristic, never equated with PROJECT run_tests calls.
        if re.search(r"\b(?:pytest|py\.test|runtests\.py|unittest|public-test\.py)\b", command) and not re.match(r"\s*(?:cat|grep|rg|sed|head|tail)\b", command):
            text = "\n".join(str(v.get("text", "")) for v in observation.get("content", []) if isinstance(v, dict))
            tests.append({"request_id": request.get("id"), "command": command, "exit_code": observation.get("exit_code"),
                          "timeout": observation.get("timeout"), "is_error": observation.get("is_error"),
                          "output_excerpt": compact(text[-2600:], 2600)})
    return {"tool_counts": dict(counts), "explicit_error_counts": dict(errors),
            "test_command_heuristic_count": len(tests), "test_command_evidence": tests,
            "test_wall_seconds": None, "timing_limitation": "Native terminal transcript does not provide a comparable per-test wall clock."}


def request_structure(reader, result, out):
    """Predetermined first/middle/last agent requests, not selected by score."""
    calls = [c for c in result.get("ledger", {}).get("calls", []) if c.get("usage_id") == "agent" and c.get("request")]
    samples = []
    if not calls:
        return samples
    for idx in sorted({0, len(calls)//2, len(calls)-1}):
        ref = calls[idx]["request"]
        path = out / str(ref["path"]).removeprefix("/pws/output/")
        if not path.is_file():
            continue
        saved = reader.json(path)
        request = saved.get("request", {})
        messages = request.get("messages", [])
        counts, chars = collections.Counter(), collections.Counter()
        snapshots, role_texts, field_values = [], [], collections.defaultdict(list)
        for message in messages:
            role, content = message.get("role", "unknown"), message.get("content")
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            counts[role] += 1
            chars[role] += len(text)
            if role == "user" and isinstance(content, str) and content.startswith("{"):
                try:
                    value = json.loads(content)
                except ValueError:
                    continue
                if isinstance(value, dict) and "role_task" in value and "observation" in value:
                    snapshots.append(value)
                    role_texts.append(str(value["role_task"]))
                    for key, val in value.get("observation", {}).items():
                        field_values[key].append(json.dumps(val, ensure_ascii=False, sort_keys=True))
        repeated = {key: {"occurrences": len(values), "identical_serialized_value_characters": len(values[0])}
                    for key, values in field_values.items() if len(values) > 1 and len(set(values)) == 1}
        samples.append({"evidence": str(path), "agent_request_ordinal": idx+1, "message_counts_by_role": dict(counts),
                        "content_characters_by_role": dict(chars), "tool_schema_characters": len(json.dumps(request.get("tools"), ensure_ascii=False)),
                        "managed_snapshot_messages": len(snapshots), "role_task_unique_values": len(set(role_texts)),
                        "role_task_characters_total": sum(map(len, role_texts)),
                        "repeated_identical_observation_fields": repeated,
                        "character_counts_are_not_token_attribution": True})
    return samples


def patch_excerpt(reader, path):
    text = reader.text(path)
    chunks = [v for v in re.split(r"(?=^diff --git )", text, flags=re.M) if v.startswith("diff --git ")]
    excluded, included = [], []
    for chunk in chunks:
        header = chunk.splitlines()[0]
        if "GIT binary patch" in chunk or any(value in header for value in ("/__pycache__/", "/.pytest_cache/", "/.mypy_cache/")):
            excluded.append(header)
        else:
            included.append(chunk)
    return {"evidence": str(path), "total_bytes": len(text.encode()), "excluded_generated_or_binary_chunks": len(excluded),
            "included_text_diff": "".join(included), "omission_is_analysis_only_original_candidate_unchanged": True}


def episode(reader, usage):
    row = {k: usage.get(k) for k in ("slot_id", "instance_id", "arm", "entered", "generation_state", "code_result", "code_status", "delivery_result", "administrative_truncation", "usage_capture_complete", "not_started_reason")}
    row["usage"] = tally_calls(usage.get("calls", []))
    row["requests"] = len(usage.get("calls", []))
    row["total_tokens"] = sum(v["total_tokens"] for v in row["usage"].values())
    row["unresolved_usage_calls"] = len(usage.get("unresolved_calls", []))
    ref = usage.get("generation_result")
    if not ref:
        row["termination"] = usage.get("not_started_reason") or "not_started"
        return row
    path = Path(ref["path"])
    result = reader.json(path)
    if any(result.get(key) != usage.get(key) for key in ("slot_id", "instance_id", "arm")):
        raise ValueError("Generation evidence does not belong to this usage record")
    out = path.parent / "controller-output"
    control = reader.json(out / "controller-result.json", {})
    row.update(slot_index=int(path.parent.name), generation_evidence=str(path), controller_evidence=str(out / "controller-result.json"),
               status=result.get("status"), controller_status=control.get("status"),
               decisions=control.get("ledger", {}).get("decisions"),
               candidate_locked=bool(result.get("candidate_lock")), same_code_and_delivery_tree=result.get("same_code_and_delivery_tree"),
               delivery_validation=result.get("delivery_validation"))
    row["request_structure_samples"] = request_structure(reader, result, out)
    if row["arm"] == "REF":
        row["termination"] = control.get("terminal_boundary", {}).get("reason") or control.get("sdk_execution_status") or control.get("status")
        events = reader.json(out / "execution-policy-events.json", [])
        observed = control.get("execution_policy_observed_counts", {})
        row["finish_reviews"] = observed.get("finish_reviews", sum(e.get("kind") == "policy_message_sent" and e.get("phase") == "finish_review" for e in events))
        row["finish_review_events"] = [e for e in events if e.get("phase") == "finish_review" and e.get("kind") in {"policy_message_sent", "continuation_not_sent", "policy_message_not_sent"}]
        row["actions"] = native_actions(reader, out)
        row["public_tests"] = []
    else:
        boundary = control.get("managed_boundary") or reader.json(out / "managed-boundary.json", {})
        stops = boundary.get("role_stops", {})
        row["termination"] = ";".join(sorted(set(stops.values()))) if stops else ("staff_done" if boundary.get("current_work_ended") else control.get("closure_reason"))
        row["terminal_details"] = boundary.get("terminal_details", {})
        row["final_member_claims"] = boundary.get("current_work_ended", {})
        row["finish_reviews"] = control.get("finish_review", {}).get("finish_reviews", 0)
        row["finish_review_events"] = [{k: v for k, v in e.items() if k not in {"message", "original_finish_reason"}} for e in control.get("finish_review", {}).get("events", [])]
        row["actions"] = project_actions(boundary)
        row["public_tests"] = public_tests(reader, out)
    row["budget_truncated"] = "budget" in str(row["termination"]) or "token_reservation" in str(row["termination"])
    row["technical_unknown"] = row["controller_status"] == "technical_unknown" or row.get("code_status") not in {"scored"}
    row["controller_error"] = control.get("error")
    return row


def aggregate(rows):
    called = [r for r in rows if r["requests"]]
    valid = [r for r in rows if type(r.get("code_result")) is bool]
    by_usage = {}
    for r in called:
        for purpose, usage in r["usage"].items():
            target = by_usage.setdefault(purpose, {k: 0 for k in usage})
            for k, value in usage.items():
                target[k] += value
    for value in by_usage.values():
        value["mean_tokens_per_called_task"] = value["total_tokens"] / len(called) if called else None
        value["mean_prompt_tokens_per_request"] = value["prompt_tokens"] / value["requests"] if value["requests"] else None
        value["cache_hit_fraction_of_prompt_tokens"] = value["prompt_cache_hit_tokens"] / value["prompt_tokens"] if value["prompt_tokens"] else None
    project_tests = [test for r in rows for test in r.get("public_tests", [])]
    arm = rows[0]["arm"] if rows else None
    middle_samples = [r["request_structure_samples"][1] for r in rows if len(r.get("request_structure_samples", [])) == 3]
    action_counts, error_counts, error_messages, page_counts, offered_page_counts = [collections.Counter() for _ in range(5)]
    identical_test_repeats = 0
    for row in rows:
        actions = row.get("actions", {})
        action_counts.update(actions.get("action_counts", actions.get("tool_counts", {})))
        error_counts.update(actions.get("explicit_error_counts", {}))
        error_messages.update(actions.get("explicit_error_message_counts", {}))
        page_counts.update(actions.get("pagination_continuation_actions", {}))
        offered_page_counts.update(actions.get("responses_with_next_cursor", {}))
        signatures = collections.Counter((t.get("tree_sha256"), json.dumps(t.get("selection"), sort_keys=True)) for t in row.get("public_tests", []))
        identical_test_repeats += sum(max(0, n-1) for n in signatures.values())
    return {"planned": len(rows), "called": len(called), "scored": len(valid), "passed": sum(r["code_result"] for r in valid),
            "unresolved": len(rows)-len(valid), "mean_tokens_called": statistics.mean(r["total_tokens"] for r in called) if called else None,
            "median_tokens_called": statistics.median(r["total_tokens"] for r in called) if called else None,
            "mean_requests_called": statistics.mean(r["requests"] for r in called) if called else None,
            "mean_decisions_called": statistics.mean(r.get("decisions") or 0 for r in called) if called else None,
            "usage_by_purpose": by_usage, "termination_counts": dict(collections.Counter(str(r.get("termination")) for r in rows)),
            "budget_truncated": sum(r.get("budget_truncated", False) for r in rows),
            "budget_truncated_passed": sum(r.get("budget_truncated", False) and r.get("code_result") is True for r in rows),
            "finish_review_tasks": sum(bool(r.get("finish_reviews")) for r in rows),
            "action_or_native_rpc_counts": dict(action_counts), "explicit_tool_or_format_error_counts": dict(error_counts),
            "PROJECT_explicit_error_message_counts": dict(error_messages),
            "pagination_continuation_actions": dict(page_counts), "responses_with_next_cursor": dict(offered_page_counts),
            "PROJECT_public_test_executions": {"count": len(project_tests), "passed": sum(t.get("passed") is True for t in project_tests),
                 "wall_seconds": sum(t.get("wall_seconds") or 0 for t in project_tests),
                 "timed_out": sum(t.get("timed_out") is True for t in project_tests),
                 "nonzero_returncode": sum(t.get("returncode") not in (None, 0) for t in project_tests),
                 "same_tree_same_selection_repeat_executions": identical_test_repeats,
                 "selection_kind_counts": dict(collections.Counter((t.get("selection") or {}).get("kind", "unknown") for t in project_tests))} if arm == "PROJECT" else None,
            "REF_native_test_command_heuristic_count": sum(r.get("actions", {}).get("test_command_heuristic_count", 0) for r in rows) if arm == "REF" else None,
            "middle_agent_request_structure_sample": {"tasks": len(middle_samples),
                 "mean_content_characters_by_role": {role: statistics.mean(s["content_characters_by_role"].get(role, 0) for s in middle_samples) if middle_samples else None for role in ("system", "user", "assistant", "tool")},
                 "mean_managed_observation_messages": statistics.mean(s["managed_snapshot_messages"] for s in middle_samples) if middle_samples else None,
                 "tasks_with_repeated_identical_role_task": sum(s["managed_snapshot_messages"] > 1 and s["role_task_unique_values"] == 1 for s in middle_samples),
                 "sampling_rule": "first/middle/last actual agent request per called task; this aggregate uses each task's middle request, independent of outcome",
                 "characters_are_not_exact_token_attribution": True},
            "delivery_passed": sum(r.get("delivery_result") is True for r in rows) if arm == "PROJECT" else None,
            "code_passed_delivery_not_passed": sum(r.get("code_result") is True and r.get("delivery_result") is not True for r in rows) if arm == "PROJECT" else None}


def paired_table(pairs):
    table = collections.Counter((p["REF"]["code_result"], p["PROJECT"]["code_result"]) for p in pairs)
    n = len(pairs)
    ref_only, project_only = table[(True, False)], table[(False, True)]
    discordant = ref_only + project_only
    pvalue = min(1, 2 * sum(math.comb(discordant, k) for k in range(min(ref_only, project_only)+1)) / 2**discordant) if discordant else 1.0
    return {"n": n, "both_passed": table[(True, True)], "both_failed": table[(False, False)], "REF_only": ref_only,
            "PROJECT_only": project_only, "REF_passed": table[(True, True)]+ref_only, "PROJECT_passed": table[(True, True)]+project_only,
            "REF_minus_PROJECT_percentage_points": (ref_only-project_only)*100/n if n else None,
            "exact_paired_binomial_two_sided_p": pvalue,
            "inference_caveat": "Exploratory paired sign/McNemar exact diagnostic; repository clustering and repeated development use limit population inference."}


def analysis_view(rows, repos):
    pairs = {}
    for row in rows:
        pairs.setdefault(row["instance_id"], {})[row["arm"]] = row
    common = [p for p in pairs.values() if all(type(p[a].get("code_result")) is bool for a in ("REF", "PROJECT"))]
    discordants = [p for p in common if p["REF"]["code_result"] != p["PROJECT"]["code_result"]]
    value = {"groups_all_planned": {a: aggregate([r for r in rows if r["arm"] == a]) for a in ("REF", "PROJECT")},
             "groups_common_scored": {a: aggregate([p[a] for p in common]) for a in ("REF", "PROJECT")},
             "paired_common_scored": paired_table(common),
             "repo_strata_common_scored": {repo: paired_table([p for p in common if p["REF"]["repo"] == repo]) for repo in sorted(set(repos.values()))},
             "discordant_task_ids": [p["REF"]["instance_id"] for p in discordants]}
    return value, pairs, discordants


def merge_continuation(original, incoming, physical_slots):
    """Accept only four never-called original slots, with immutable task identity.

    A full continuation index may repeat unchanged original records. Such rows
    are ignored, never substituted. Any changed previously-called row is refused.
    """
    merged = dict(original)
    accepted, ignored = [], []
    for slot, new in incoming.items():
        if slot not in original or new.get("slot_id") != slot:
            raise ValueError("Continuation index contains an unplanned logical slot")
        old = original[slot]
        index = physical_slots[slot]
        if new == old:
            ignored.append(slot)
            continue
        if index not in CONTINUATION_SLOTS:
            raise ValueError("A previously called or non-continuation slot cannot be replaced")
        if (old.get("generation_state") != "not_started" or old.get("entered") is not False
                or old.get("calls") != [] or old.get("unresolved_calls") != [] or old.get("generation_result") is not None):
            raise ValueError("Continuation can replace only an original unentered zero-call record")
        if any(new.get(key) != old.get(key) for key in ("slot_id", "instance_id", "arm", "group_id", "model_key")):
            raise ValueError("Continuation changed the original task, arm, model, or group")
        if (new.get("entered") is not True or not new.get("generation_result")
                or not (new.get("calls") or new.get("unresolved_calls"))):
            raise ValueError("Continuation replacement requires evidence of its first actual model attempt")
        if new.get("generation_state") not in {"closed", "technical_unknown"}:
            raise ValueError("Only settled continuation generation records may enter final analysis")
        merged[slot] = new
        accepted.append(slot)
    return merged, {"accepted_first_generation_slots": accepted, "identical_records_ignored": ignored,
                    "previously_called_records_replaced": 0, "original_usage_files_modified": False}


def split_score_overrides(items, original, physical_slots):
    ordinary, supplemental = {}, {}
    for item in items:
        slot = item.get("slot_id")
        if (slot not in original or type(item.get("code_result")) is not bool
                or item.get("code_status") != "scored" or not item.get("evidence")):
            raise ValueError("Every score override needs a planned slot, boolean result, scored status, and evidence")
        if slot in ordinary or slot in supplemental:
            raise ValueError("Duplicate score overrides are ambiguous")
        old, index = original[slot], physical_slots[slot]
        if type(old.get("code_result")) is bool:
            raise ValueError("An already scored original result cannot be overwritten")
        stopped = item.get("measurement_kind") == "recovered_stopped_code"
        if index in STOPPED_CANDIDATE_SLOTS:
            if not stopped or old.get("generation_state") != "technical_unknown":
                raise ValueError("Stopped-code scores must be explicitly supplemental, with original technical stop retained")
            supplemental[slot] = item
        elif index in ORDINARY_RESCORE_SLOTS:
            if stopped or old.get("generation_state") != "closed":
                raise ValueError("Ordinary rescoring requires the original normally closed candidate")
            ordinary[slot] = item
        else:
            raise ValueError("Only the two approved original rescores and two stopped-code supplements are admitted")
    return ordinary, supplemental


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=ROOT / "runs/software-benchmark-v111/aligned-interface-r1")
    parser.add_argument("--usage-index", type=Path)
    parser.add_argument("--continuation-usage-index", type=Path,
                        help="v114 actual-usage-records.json; only first generations for 7238/7239/7266/7267 may replace original zero-call rows")
    parser.add_argument("--score-overrides", type=Path)
    parser.add_argument("--supplemental-scores", type=Path,
                        help="Optional separate score list for 7244/7251, tagged measurement_kind=recovered_stopped_code")
    parser.add_argument("--include-stopped-candidates-in-main", action="store_true",
                        help="Explicitly select the candidate-endpoint view as primary; the strict original-main view is always retained")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/software-benchmark-v114/gap-evidence-final-r1")
    args = parser.parse_args()
    args.output = args.output.resolve()
    if ROOT / "artifacts/software-benchmark-v114" not in args.output.parents:
        raise ValueError("Only new v114 artifact output is permitted")
    frozen_output = ROOT / "artifacts/software-benchmark-v114/gap-evidence-r1"
    if args.output == frozen_output or frozen_output in args.output.parents:
        raise ValueError("The original gap-evidence-r1 analysis is frozen; select a new output directory")
    reader = Reader()
    index = args.usage_index or args.batch / "api-coordinator-v113/actual-usage-records.json"
    refs = reader.json(index)["record_files"]
    plan = reader.json(args.batch / "execution-plan-v113.json")
    physical_slots = {r["slot_id"]: r["slot_index"] for r in plan["rows"]}
    if set(refs) != set(physical_slots):
        raise ValueError("The original index must preserve all 100 planned logical slots")
    original_usage = {slot: reader.json(ref["path"]) for slot, ref in refs.items()}
    usage_records = dict(original_usage)
    continuation = {"accepted_first_generation_slots": [], "identical_records_ignored": [], "previously_called_records_replaced": 0}
    if args.continuation_usage_index:
        continuation_refs = reader.json(args.continuation_usage_index)["record_files"]
        incoming = {slot: reader.json(ref["path"]) for slot, ref in continuation_refs.items()}
        usage_records, continuation = merge_continuation(original_usage, incoming, physical_slots)
    score_items = []
    if args.score_overrides:
        score_items.extend(reader.json(args.score_overrides))
    if args.supplemental_scores:
        supplemental_items = reader.json(args.supplemental_scores)
        if any(item.get("measurement_kind") != "recovered_stopped_code" for item in supplemental_items):
            raise ValueError("The supplemental file may contain only explicitly tagged stopped-code scores")
        score_items.extend(supplemental_items)
    overrides, supplemental = split_score_overrides(score_items, original_usage, physical_slots)
    if args.include_stopped_candidates_in_main and not supplemental:
        raise ValueError("No stopped-code supplemental scores were supplied for the requested alternative primary view")
    rows = []
    for slot, usage in usage_records.items():
        if slot in overrides:
            usage = {**usage, **{k: v for k, v in overrides[slot].items() if k in {"code_result", "code_status", "delivery_result"}}}
        row = episode(reader, usage)
        if slot in continuation["accepted_first_generation_slots"]:
            row["analysis_generation_source"] = "v114_first_generation_after_original_zero_calls"
        if slot in overrides:
            row["analysis_score_override"] = overrides[slot]
        rows.append(row)
    repos = {r["instance_id"]: r["repo"] for r in plan["rows"]}
    for row in rows:
        row["repo"] = repos[row["instance_id"]]
    strict_rows = rows
    strict_view, _, _ = analysis_view(strict_rows, repos)
    supplemented_rows = []
    for row in strict_rows:
        item = supplemental.get(row["slot_id"])
        if item is None:
            supplemented_rows.append(row)
        else:
            supplemented_rows.append({**row, "original_main_code_result": row.get("code_result"),
                                      "code_result": item["code_result"], "code_status": "scored_recovered_stopped_code",
                                      "supplemental_scoring": item, "original_generation_technical_stop_retained": True})
    supplemental_view, _, _ = analysis_view(supplemented_rows, repos)
    rows = supplemented_rows if args.include_stopped_candidates_in_main else strict_rows
    selected_view, pairs, discordants = analysis_view(rows, repos)
    summary = {"version": VERSION, "analysis_status": "explicit_final_merge_view" if args.continuation_usage_index or score_items else "interim_before_remaining_technical_cases_resolved",
               "source_usage_index": str(index), "score_override_source": str(args.score_overrides) if args.score_overrides else None,
               "continuation_usage_index": str(args.continuation_usage_index) if args.continuation_usage_index else None,
               "continuation_merge": continuation, "supplemental_score_source": str(args.supplemental_scores) if args.supplemental_scores else None,
               "primary_view": "candidate_endpoint_including_recovered_stopped_code" if args.include_stopped_candidates_in_main else "strict_original_main",
               "strict_original_main_analysis": strict_view,
               "supplemental_stopped_code_analysis": {"records": list(supplemental.values()), "included_in_primary_by_explicit_flag": args.include_stopped_candidates_in_main,
                    "view_with_supplements": supplemental_view if supplemental else None,
                    "new_model_calls_added_by_supplemental_scoring": 0, "original_generation_stop_reclassified_as_normal": False},
               **selected_view,
               "limitations": ["Missing technical outcomes are retained as unknown, never coded failure.",
                               "Recovered stopped-code scores are a separate candidate endpoint; they do not turn a crashed original model run into normal completion.",
                               "Cache tokens count toward the same cumulative token budget; cost savings do not create extra action opportunity.",
                               "PROJECT test wall time is explicit; native test command counts are only a labeled command-text heuristic, with no comparable wall clock.",
                               "A tool error or public-test failure is observed evidence, not proof of its causal contribution to final score.",
                               "No reference patches or hidden test contents were read; no model, Docker, GPU, network or service actions."]}
    args.output.mkdir(parents=True, exist_ok=True)
    def save(name, value):
        (args.output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n")
    save("summary.json", summary)
    save("episodes.json", rows)
    save("strict-original-episodes.json", strict_rows)
    save("supplemental-stopped-code.json", {"records": list(supplemental.values()), "candidate_endpoint_view": supplemental_view if supplemental else None,
                                           "original_model_cost_unchanged": True, "included_in_primary": args.include_stopped_candidates_in_main})
    save("paired-tasks.json", [{"instance_id": task, "repo": repos[task], **{a: {k:p[a].get(k) for k in ("slot_index", "code_result", "code_status", "total_tokens", "requests", "termination", "finish_reviews")} for a in ("REF", "PROJECT")}} for task,p in pairs.items()])
    detail = []
    for pair in discordants:
        item = {"instance_id": pair["REF"]["instance_id"], "arms": pair}
        for arm in ("REF", "PROJECT"):
            ep = Path(pair[arm]["generation_evidence"]).parent
            item[arm+"_candidate_patch"] = patch_excerpt(reader, ep/"candidate.patch") if (ep/"candidate.patch").exists() else None
        config = reader.json(args.batch / "configs" / (str(pair["REF"]["slot_index"])+".json"))
        item["public_problem_statement"] = config["public_task"]["problem_statement"]
        detail.append(item)
    save("discordant-evidence.json", detail)
    save("sources.json", {"version": VERSION, "tool": str(Path(__file__).resolve()), "sources": list(reader.sources.values())})
    print(json.dumps({"version": VERSION, "output": str(args.output), "paired": summary["paired_common_scored"],
                      "called": {a: summary["groups_all_planned"][a]["called"] for a in ("REF", "PROJECT")}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
