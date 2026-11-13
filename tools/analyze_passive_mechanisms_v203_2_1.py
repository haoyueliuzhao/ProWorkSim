"""Summarize the twelve existing passive measurements and selected tool receipts.

No archive decompression, model request, grading or world-action replay. Natural
event counts are observations, not dependency necessity or misalignment labels.
"""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/software-benchmark-v203-2-1/final-report-r1"
PLAN = ROOT / "runs/software-benchmark-v203-2-1/passive-pilot12-r2/execution-plan-r2.json"
MEASUREMENTS = [ROOT / f"artifacts/software-benchmark-v203-2-1/capture-recovery-r4/{i}-measurement.json"
                for i in (2032200, 2032201)] + [
    ROOT / f"runs/software-benchmark-v203-2-1/passive-pilot10-r4/api-coordinator/measurement-records/{i}.json"
    for i in range(2032402, 2032412)]
FOCUS = ("declare_dependency", "clear_dependency", "offer_transfer", "accept_transfer", "decline_transfer",
         "create_task", "claim_task", "return_task", "revise_task", "send_message", "handoff_patch",
         "read_work_event", "read_file", "integrate_patch", "org_review_patch", "run_tests",
         "read_test_result", "fix_patch", "submit_integration")
PHASE_MEANINGS = {
    "T0": "记录初态", "T1": "首次任务板创建或认领（不保证已有owner）",
    "T2": "首次接受代码编辑", "T3": "首次发布产物或伙伴产物读取",
    "T4": "首次已执行公开测试失败", "T5": "首次集成、责任转移或失败测试后编辑",
    "T6": "首次提交意图之前；不是提交成功或官方评分",
}


def reference(path):
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def load_analyzer():
    path = ROOT / "tools/analyze_passive_capture_v203_2_1_r4.py"
    spec = importlib.util.spec_from_file_location("existing_passive_capture_reader", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected_observations(path, expected, decoder):
    """Read indexed tool boundaries only, reusing prior complete chain verification."""
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        count = db.execute("SELECT count(*) FROM observations").fetchone()[0]
        head = db.execute("SELECT sequence,chain_sha256 FROM observations ORDER BY sequence DESC LIMIT 1").fetchone()
        conflicts = db.execute("SELECT count(*) FROM conflicts").fetchone()[0]
        if (count != expected["records"] or head[0] != count or head[1] != expected["last_chain_sha256"]
                or conflicts != expected.get("conflicts", 0)):
            raise ValueError("Tool evidence no longer matches the previously verified closed journal")
        query = """SELECT * FROM observations WHERE event_key GLOB 'intent:*'
                   OR event_key GLOB 'receipt:*' OR event_key GLOB 'action-exception:*' ORDER BY sequence"""
        rows = [decoder(row) for row in db.execute(query)]
    return rows, {"path": str(path), "records": count, "last_chain_sha256": head[1],
                  "selected_rows_checked": len(rows), "conflicts": conflicts,
                  "full_chain_validation_reused_from_measurement": True,
                  "selected_record_hashes_rechecked": True, "model_payload_rows_read": False}


def empty_counts():
    return {"attempts": 0, "receipts": 0, "successful_receipts": 0,
            "rejected_receipts": 0, "unknown_receipts": 0, "exceptions": 0}


def analyze_one(path, decoder):
    measurement = json.loads(path.read_bytes())
    episode = measurement["episode_id"]
    capture_path = Path(measurement["sidecar_journal"]["path"])
    capture_summary_path = capture_path.parent / "capture-summary.json"
    capture_summary = json.loads(capture_summary_path.read_bytes())
    if capture_summary.get("episode_id") != episode:
        raise ValueError("Capture summary belongs to another episode")
    rows, journal_proof = selected_observations(capture_path, measurement["sidecar_journal"], decoder)
    tools = defaultdict(empty_counts)
    intents, receipts, exceptions, semantic = {}, [], [], Counter()
    request_decisions = {(item["actor"], item["decision_id"]) for item in measurement["accepted_requests"]
                         if item["decision_id"] is not None}
    matched_intents = matched_receipts = 0
    unmatched = []
    actor_counts = defaultdict(Counter)
    patch_authors, test_reports = {}, {}
    review_decisions, review_evidence, read_kinds, rejection_codes = Counter(), Counter(), Counter(), Counter()
    semantic_ids = defaultdict(set)
    for row in rows:
        payload, kind = row["payload"], row["kind"]
        actor, tool = payload.get("actor"), payload.get("tool")
        association = payload.get("association", {})
        decision = association.get("decision_id")
        linked = ((actor, decision) in request_decisions and association.get("model_call_id") == decision
                  and bool(association.get("model_tool_call_id")))
        if kind == "INTENT":
            key = row["key"].split(":", 1)[1]
            intents[key] = payload
            tools[tool]["attempts"] += 1
            actor_counts[actor]["attempts"] += 1
            matched_intents += linked
            if not linked:
                unmatched.append({"kind": kind, "key": row["key"], "tool": tool})
            continue
        if kind == "ACTION_EXCEPTION":
            tools[tool]["exceptions"] += 1
            exceptions.append(row)
            continue
        if kind != "RECEIPT":
            raise ValueError("Unexpected row in selected executor boundaries")
        key = row["key"].split(":", 1)[1]
        expected = intents.get(key)
        if expected is None or any(expected.get(field) != payload.get(field)
                                   for field in ("actor", "tool", "arguments", "association")):
            raise ValueError("Tool receipt differs from its original captured intent")
        receipts.append(row)
        matched_receipts += linked
        if not linked:
            unmatched.append({"kind": kind, "key": row["key"], "tool": tool})
        response = payload.get("response", {})
        ok, result = response.get("ok"), response.get("result") or {}
        result = result if isinstance(result, dict) else {}
        args = payload.get("arguments") or {}
        tools[tool]["receipts"] += 1
        actor_counts[actor]["receipts"] += 1
        state = "successful_receipts" if ok is True else "rejected_receipts" if ok is False else "unknown_receipts"
        tools[tool][state] += 1
        actor_counts[actor][state] += 1
        if ok is not True:
            error = response.get("error") or {}
            rejection = error.get("rejection") or {}
            rejection_codes[str(rejection.get("code") or error.get("code") or "UNKNOWN")] += 1
            continue
        if tool == "fix_patch" and result.get("patch_id"):
            patch_authors[result["patch_id"]] = result.get("author", actor)
            semantic_ids["published_patches"].add(result["patch_id"])
        if tool in {"send_message", "handoff_patch"}:
            sequence = result.get("message_sequence" if tool == "send_message" else "handoff_sequence")
            label = "sent_messages" if tool == "send_message" else "sent_handoffs"
            if sequence is not None:
                semantic_ids[label].add(sequence)
            else:
                semantic[label + "_identity_unknown"] += 1
        if tool == "read_work_event":
            read_kinds[str(result.get("kind", "UNKNOWN"))] += 1
            if result.get("kind") in {"work_message", "handoff"}:
                semantic["explicit_communication_read_receipts"] += 1
                if result.get("sequence") is not None:
                    semantic_ids["explicitly_read_communication_events"].add((actor, result["sequence"]))
        if tool == "read_file" and args.get("patch_id"):
            author = patch_authors.get(args["patch_id"])
            semantic["published_patch_file_read_receipts"] += 1
            semantic["peer_patch_file_read_receipts" if author and author != actor else
                     "own_patch_file_read_receipts" if author else "patch_file_read_author_unknown"] += 1
        if tool == "integrate_patch":
            author = patch_authors.get(args.get("patch_id"))
            semantic["peer_patch_adoption_receipts" if author and author != actor else
                     "own_patch_adoption_receipts" if author else "patch_adoption_author_unknown"] += 1
            if args.get("patch_id"):
                semantic_ids["actor_patch_adoption_pairs"].add((actor, args["patch_id"]))
            if result.get("conflict_count", 0):
                semantic["successful_integration_receipts_reporting_conflicts"] += 1
        if tool == "org_review_patch":
            review_decisions[str(result.get("decision", args.get("decision", "UNKNOWN")))] += 1
            if result.get("review_id"):
                semantic_ids["review_records"].add(result["review_id"])
            evidence = result.get("test_evidence") or {}
            review_evidence["passed_true" if evidence.get("passed") is True else
                            "passed_false" if evidence.get("passed") is False else "passed_unknown"] += 1
            # A review carries earlier evidence; it is not a new test execution.
        if tool == "run_tests" and result.get("executed") is True:
            semantic["public_test_execution_receipts"] += 1
            report_id = result.get("report_id")
            if report_id:
                evidence = {"actor": actor, "passed": result.get("passed"), "source_reference": result.get("source_reference")}
                if report_id in test_reports and test_reports[report_id] != evidence:
                    raise ValueError("An immutable test report changed identity/version/outcome")
                test_reports[report_id] = evidence
            else:
                semantic["executed_test_report_identity_unknown"] += 1
        if tool == "submit_integration" and result.get("delivery_id"):
            semantic_ids["delivery_records"].add(result["delivery_id"])
    for name, values in semantic_ids.items():
        semantic[name + "_unique"] = len(values)
    for name in ("sent_messages_unique", "sent_handoffs_unique", "published_patches_unique",
                 "explicit_communication_read_receipts", "explicitly_read_communication_events_unique",
                 "published_patch_file_read_receipts", "peer_patch_file_read_receipts", "own_patch_file_read_receipts",
                 "patch_file_read_author_unknown", "peer_patch_adoption_receipts", "own_patch_adoption_receipts",
                 "patch_adoption_author_unknown", "actor_patch_adoption_pairs_unique", "review_records_unique",
                 "public_test_execution_receipts", "executed_test_report_identity_unknown", "delivery_records_unique"):
        semantic.setdefault(name, 0)
    semantic["public_test_reports_unique"] = len(test_reports)
    semantic["public_test_reports_passed"] = sum(item["passed"] is True for item in test_reports.values())
    semantic["public_test_reports_failed"] = sum(item["passed"] is False for item in test_reports.values())
    semantic["public_test_reports_outcome_unknown"] = sum(item["passed"] is not True and item["passed"] is not False for item in test_reports.values())
    for tool in FOCUS:
        tools[tool]
    missing_receipts = set(intents) - {row["key"].split(":", 1)[1] for row in receipts + exceptions}
    phase_rows = {}
    for phase, meaning in PHASE_MEANINGS.items():
        item = measurement["phases"][phase]
        observed = item["observed"]
        sequence = item.get("source", {}).get("observer_sequence")
        ordinal = sum(row["kind"] == "INTENT" and row["sequence"] <= sequence for row in rows) if observed and isinstance(sequence, int) else None
        phase_rows[phase] = {"meaning": meaning, "observed": observed, "source": item.get("source"),
            "executor_tool_attempt_ordinal": ordinal,
            "after_first_40_executor_tool_attempts": ordinal > 40 if ordinal is not None else None,
            "absence_proven_by_operational_definition": item.get("absence_proven") if not observed else None}
    result = {
        "episode_id": episode, "measurement": reference(path), "execution_state": measurement["execution_state"],
        "integrity": {"status": measurement["integrity"]["status"], "dimensions": {key: item["status"] for key, item in measurement["integrity"]["dimensions"].items()}},
        "reconciliation": measurement["reconciliation"],
        "request_counts": {"accepted": len(measurement["accepted_requests"]),
            "sdk_decision_bound": sum(item["decision_id"] is not None for item in measurement["accepted_requests"]),
            "without_agent_decision_binding": sum(item["decision_id"] is None for item in measurement["accepted_requests"]),
            "evidence_modes": dict(Counter(item["evidence_mode"] for item in measurement["accepted_requests"]))},
        "action_links": {"attempts": len(intents), "receipts": len(receipts), "exceptions": len(exceptions),
            "intent_to_verified_sdk_decision": matched_intents, "receipt_to_verified_sdk_decision": matched_receipts,
            "unmatched": unmatched, "intents_without_receipt_or_exception": sorted(missing_receipts)},
        "tools": dict(tools), "semantic_observations": dict(semantic), "actor_counts": dict(actor_counts),
        "work_event_read_kinds": dict(read_kinds), "review_decisions": dict(review_decisions),
        "review_prior_test_evidence": dict(review_evidence), "rejection_codes": dict(rejection_codes),
        "observer_event_kinds": dict(Counter(item["change_type"] for item in measurement["objective_state_changes"])),
        "phases": phase_rows, "stage_assessment_count": len(measurement["stage_assessments"]),
        "stage_assessment_labels": {label: dict(Counter(item[label] for item in measurement["stage_assessments"]))
                                    for label in ("dependency", "misalignment", "decision")},
        "capture_summary": reference(capture_summary_path), "observer_cost": {key: capture_summary.get(key) for key in
            ("observed_boundary_calls", "observer_fault_count", "observer_CPU_seconds", "observer_wall_seconds",
             "controller_peak_RSS_bytes", "storage_bytes", "capture_status")},
        "selected_journal_proof": journal_proof,
        "physical_verification_reused": {key: measurement["physical_journal"].get(key) for key in ("valid", "records", "last_chain_sha256", "conflicts")},
    }
    return result


def main():
    if (OUT / "mechanisms.json").exists():
        raise ValueError("Preserve an existing report; select a new output revision")
    plan = json.loads(PLAN.read_bytes())
    planned = {row["slot_id"]: row for row in plan["rows"]}
    if len(planned) != 12 or any(not path.is_file() for path in MEASUREMENTS):
        raise ValueError("The original twelve planned identities and measurements must all be present")
    analyzer = load_analyzer()
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda path: analyze_one(path, analyzer.ObserverJournal._decode), MEASUREMENTS))
    if {row["episode_id"] for row in rows} != set(planned) or len(rows) != 12:
        raise ValueError("First two plus continuation ten do not match the exact original panel")
    statuses = Counter(row["integrity"]["status"] for row in rows)
    dimensions = defaultdict(Counter)
    phases = {phase: {"observed_tasks": 0, "after_first_40_executor_tool_attempts": 0} for phase in PHASE_MEANINGS}
    tool_totals, semantic_totals, labels, observer_events = defaultdict(Counter), Counter(), defaultdict(Counter), Counter()
    aggregate = Counter()
    read_kinds, review_decisions, costs = Counter(), Counter(), Counter()
    for row in rows:
        original = planned[row["episode_id"]]
        row["instance_id"], row["repo"] = original["instance_id"], original["repo"]
        for name, status in row["integrity"]["dimensions"].items():
            dimensions[name][status] += 1
        for phase, value in row["phases"].items():
            phases[phase]["observed_tasks"] += value["observed"]
            phases[phase]["after_first_40_executor_tool_attempts"] += value["after_first_40_executor_tool_attempts"] is True
        for tool, counts in row["tools"].items():
            tool_totals[tool].update(counts)
            tool_totals[tool]["tasks_with_attempt"] += counts["attempts"] > 0
            tool_totals[tool]["tasks_with_success"] += counts["successful_receipts"] > 0
        semantic_totals.update(row["semantic_observations"])
        observer_events.update(row["observer_event_kinds"])
        for name, counts in row["stage_assessment_labels"].items():
            labels[name].update(counts)
        read_kinds.update(row["work_event_read_kinds"])
        review_decisions.update(row["review_decisions"])
        for name in ("accepted", "sdk_decision_bound", "without_agent_decision_binding"):
            aggregate[name] += row["request_counts"][name]
        for name in ("attempts", "receipts", "exceptions", "intent_to_verified_sdk_decision", "receipt_to_verified_sdk_decision"):
            aggregate[name] += row["action_links"][name]
        aggregate["primary_opportunities"] += row["reconciliation"]["primary_outcomes"]
        aggregate["sidecar_records"] += row["selected_journal_proof"]["records"]
        aggregate["physical_records"] += row["physical_verification_reused"]["records"]
        for name in ("observer_fault_count", "observer_CPU_seconds", "observer_wall_seconds", "storage_bytes"):
            if isinstance(row["observer_cost"][name], (int, float)):
                costs[name] += row["observer_cost"][name]
    result = {
        "schema": "passive-mechanisms-v203.2.1-final-r1", "planned_tasks": 12,
        "different_repositories": len({row["repo"] for row in rows}),
        "execution_states": dict(Counter(row["execution_state"] for row in rows)),
        "task_integrity": {state: statuses[state] for state in ("COMPLETE", "PARTIAL", "INVALID")},
        "dimension_integrity": {name: {state: value[state] for state in ("COMPLETE", "PARTIAL", "INVALID")}
                                for name, value in dimensions.items()},
        "linkage_totals": dict(aggregate), "tool_totals": dict(tool_totals),
        "semantic_observation_totals": dict(semantic_totals), "work_event_read_kinds": dict(read_kinds),
        "review_decisions": dict(review_decisions), "observer_event_kinds": dict(observer_events),
        "phase_coverage": phases, "phase_points": sum(row["observed_tasks"] for row in phases.values()),
        "stage_assessment_labels": dict(labels), "observer_cost_reported_sum": dict(costs),
        "controller_peak_RSS_max_bytes_not_observer_increment": max(row["observer_cost"]["controller_peak_RSS_bytes"] for row in rows),
        "rows": rows, "original_plan": reference(PLAN), "analysis_source": reference(Path(__file__).resolve()),
        "definitions": {
            "attempts": "Recorded executor INTENT, including rejected and role-control actions; not all decision opportunities execute a tool.",
            "success": "response.ok is true; does not prove semantic usefulness, test pass, official correctness or necessary collaboration.",
            "tests": "Unique report IDs from run_tests with executed=true; read_test_result and review evidence do not create new executions.",
            "read": "Explicit read_work_event/read_file receipts only; a message sent, patch published, or phase snapshot does not establish read/understanding.",
            "dependency": "Explicit declarations are candidates. Zero declaration/transfer counts do not negate implicit dependencies or establish organization fitness.",
            "phases": "First operational occurrence per T0-T6 per task; phase points are correlated within tasks, not independent tasks.",
            "observer_cost": "Capture-summary process CPU/wall/storage measurements; controller RSS is not incremental observer memory, and no unobserved baseline latency delta is inferred.",
        },
        "natural_dependency_gold": False, "organizational_misalignment_assessed": False,
        "new_model_calls": 0, "new_grading_calls": 0, "world_actions_replayed": 0,
        "original_archives_decompressed": 0, "raw_model_request_payloads_reread": False,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "mechanisms.json").open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("task_integrity", "linkage_totals", "phase_coverage",
        "semantic_observation_totals", "review_decisions", "observer_cost_reported_sum")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
