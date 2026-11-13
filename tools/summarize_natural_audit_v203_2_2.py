"""Join existing offline evidence; no runtime, grading, model or label generation."""
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/software-benchmark-v203-2-2/natural-audit-r1"


def load(path):
    return json.loads(path.read_text())


def source(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def usage(rows):
    # A full provider request is counted once, never per action or cached subset.
    unique = {r["physical_request_id"]: r for r in rows}
    return {"requests": len(unique),
            "input_tokens": sum(r["usage"]["prompt_tokens"] for r in unique.values()),
            "output_tokens": sum(r["usage"]["completion_tokens"] for r in unique.values()),
            "total_tokens": sum(r["usage"]["total_tokens"] for r in unique.values())}


def main():
    paths = {"test_budget": OUT / "test-budget-audit.json", "chains": OUT / "chain-summary.json",
             "original": ROOT / "artifacts/software-benchmark-v203-2-1/final-report-r1/summary.json"}
    b, c, original = (load(paths[k]) for k in ("test_budget", "chains", "original"))
    rows = [r for task in b["tasks"] for r in task["token_timeline"]]
    total = usage(rows)
    assert total["requests"] == 915 and total["total_tokens"] == 49381273
    action_groups = {}
    for tool in ("send_message", "handoff_patch", "integrate_patch", "org_review_patch", "run_tests"):
        selected = [r for r in rows if any(a["tool"] == tool for a in r["actions"])]
        action_groups[tool] = {**usage(selected), "physical_request_ids": [r["physical_request_id"] for r in selected]}
    bad_test_ids = {(t["episode_id"], p["decision_id"]) for t in b["tasks"] for p in t["public_tests"]
                    if p.get("classification", {}).get("subtype") == "harness_plugin_bootstrap_warning_as_error"}
    selected = [r for t in b["tasks"] for r in t["token_timeline"] if (t["episode_id"], r["decision_id"]) in bad_test_ids]
    assert len(selected) == 17
    astropy = next(t for t in b["tasks"] if t["instance_id"] == "astropy__astropy-13453")
    first_failure = min(p["capture_time"] for p in astropy["public_tests"])
    after = [r for r in astropy["token_timeline"] if datetime.fromisoformat(r["reserved_utc"]).timestamp() > first_failure]
    first_author_candidate = {}
    timeline_path = OUT / "task_event_timeline.jsonl"
    for line in timeline_path.open():
        event = json.loads(line)
        payload = event.get("payload", {})
        if (event["kind"] == "RECEIPT" and payload.get("tool") == "fix_patch"
                and payload.get("actor") == "member_001"
                and payload.get("response", {}).get("ok") is True):
            first_author_candidate.setdefault(event["task_id"], event["source_reference"])
    pre_candidate_rows, pre_candidate_tasks = [], []
    for task in b["tasks"]:
        first = first_author_candidate.get(task["instance_id"])
        selected_pre = [r for r in task["token_timeline"] if r["actor"] == "member_002"
                        and (first is None or datetime.fromisoformat(r["finished_utc"]).timestamp() <= first["capture_time"])]
        pre_candidate_rows.extend(selected_pre)
        pre_candidate_tasks.append({"task": task["instance_id"], "first_author_publication": first,
                                    "reviewer_usage_before_first_candidate": usage(selected_pre)})
    costs = {"total": total, "request_action_groups": action_groups,
             "astropy_requests_dispatching_17_bootstrap_failures": usage(selected),
             "astropy_all_requests_started_after_first_bootstrap_failure": usage(after),
             "cost_definition": "Whole physical requests that dispatch each action, including existing context and output; groups may overlap. This is not isolated communication/test overhead or counterfactual savings.",
             "after_failure_definition": "All subsequent requests, including other repair work and summaries; chronology only, not wasted-token attribution.",
             "reviewer_before_first_author_candidate": {"usage": usage(pre_candidate_rows), "tasks": pre_candidate_tasks,
                 "definition": "Member 002 requests completed before the first successful member 001 fix_patch receipt; includes all reviewer requests if no author candidate was published. Includes preparation, independent inspection, communication and summaries, not automatically idle/wasted work.",
                 "timeline_source": source(timeline_path)},
             "sources": {k: source(v) for k, v in paths.items()}}
    (OUT / "request-action-costs.json").write_text(json.dumps(costs, ensure_ascii=False, indent=2) + "\n")
    n, x, z = 12, 7, 1.959963984540054
    p = x / n
    center = (p + z*z/(2*n)) / (1+z*z/n)
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1+z*z/n)
    summary = {"version": "v203.2.2-offline-audit-r1", "new_benchmark_model_requests": 0,
               "new_official_scoring": 0, "new_experiment_cash": 0,
               "codex_review_usage_not_separately_available": True,
               "original_score_unchanged": {"code": "7/12", "delivery": "7/12",
                    "task_binomial_Wilson_95": [center-half, center+half],
                    "ignores_repository_clustering_and_historical_exposure": True},
               "event_chains": c["totals"], "test_and_budget": b["totals"],
               "request_action_cost_source": source(OUT / "request-action-costs.json"),
               "human_reference_available": False, "v203_3_admission": "HOLD",
               "v203_2_3_live_pilot_started": False, "v204_started": False,
               "budget_and_delivery_explanations": [{"task": t["instance_id"],
                   "budget_gate_count": len(t["budget_gates"]),
                   "explanation": t["delivery"]["contemporaneous_explanation_zh"]} for t in b["tasks"]],
               "sources": {k: source(v) for k, v in paths.items()}}
    (OUT / "audit-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"whole_request_costs": {k: {x: v[x] for x in ("requests", "input_tokens", "output_tokens", "total_tokens")} for k,v in action_groups.items()},
                      "bootstrap_requests": costs["astropy_requests_dispatching_17_bootstrap_failures"],
                      "astropy_after_first_failure": costs["astropy_all_requests_started_after_first_bootstrap_failure"],
                      "reviewer_pre_candidate": costs["reviewer_before_first_author_candidate"]["usage"],
                      "wilson": summary["original_score_unchanged"]["task_binomial_Wilson_95"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
