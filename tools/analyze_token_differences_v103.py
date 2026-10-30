"""Read frozen benchmark receipts and describe token differences without reruns."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/software-benchmark-v103/token-difference-r1"


def read(path: Path) -> dict | list:
    return json.loads(path.read_text())


def proof(path: Path) -> dict:
    raw = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def write(name: str, value: object) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def summarize(rows: list[dict], count_key: str = "requests") -> dict:
    n = len(rows)
    totals = {
        field: sum(r[field] for r in rows)
        for field in ("input_tokens", "output_tokens", "total_tokens", count_key)
    }
    return {
        "tasks": n,
        "totals": totals,
        "means": {k: v / n for k, v in totals.items()},
        "weighted_mean_input_per_request": totals["input_tokens"] / totals[count_key],
        "weighted_mean_output_per_request": totals["output_tokens"] / totals[count_key],
        "median_total_tokens": median(r["total_tokens"] for r in rows),
    }


def contrast(left: dict, right: dict) -> dict:
    delta = {k: right["means"][k] - left["means"][k] for k in left["means"]}
    return {
        "mean_difference": delta,
        "total_relative_change": right["means"]["total_tokens"]
        / left["means"]["total_tokens"]
        - 1,
        "input_share_of_total_increase": delta["input_tokens"] / delta["total_tokens"],
        "request_relative_change": right["means"]["requests"]
        / left["means"]["requests"]
        - 1,
        "weighted_input_per_request_relative_change": right[
            "weighted_mean_input_per_request"
        ]
        / left["weighted_mean_input_per_request"]
        - 1,
        "descriptive_accounting_not_causal_effect": True,
    }


def qwen() -> None:
    run = ROOT / "runs/software-benchmark-v062/capability-probe-r1-20261026"
    source = run / "coordinator-r2/run-summary.json"
    plan_path = ROOT / "artifacts/software-benchmark-v062/preparation-r1/panel.json"
    index, plan = read(source), read(plan_path)
    rows = []
    for slot in plan["slots"]:
        if slot["repeat_index"] or slot["condition_id"] not in ("FIX5M", "FIX10M"):
            continue
        result_path = Path(index["generation"][slot["slot_id"]]["result"]["path"])
        result = read(result_path)
        controller_path = Path(result["controller_result"]["path"])
        controller = read(controller_path)
        ledger = result["ledger"]
        calls = ledger["calls"]
        assert all(isinstance(c.get("usage"), dict) for c in calls)
        assert ledger["uncertain_reserved_tokens"] == 0 and ledger["inflight"] is None
        prompt = sum(c["usage"]["prompt_tokens"] for c in calls)
        output = sum(c["usage"]["completion_tokens"] for c in calls)
        assert prompt + output == result["known_actual_tokens"]
        pure = [
            c
            for c in calls
            if c.get("finish_reason") == "length"
            and (c["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens")
            == c["usage"]["completion_tokens"]
        ]
        boundary = controller.get("terminal_boundary")
        stop = (
            boundary["reason"]
            if boundary
            else "normal_finish"
            if controller["normal_completion"]
            else "sdk_" + str(controller.get("sdk_execution_status"))
        )
        request = Path(index["scores"][slot["slot_id"]]["request"]["path"])
        receipt = request.parent / "receipt.json"
        if request.parent.name == "score-29":
            receipt = ROOT / "runs/software-benchmark-v063/diagnostic-rescore-r1/grading/score-29/receipt.json"
        scored = read(receipt)
        assert isinstance(scored.get("resolved"), bool)
        rows.append(
            {
                "slot_id": slot["slot_id"],
                "instance_id": slot["instance_id"],
                "condition": slot["condition_id"],
                "seed": slot["seed"],
                "resolved": scored["resolved"],
                "total_tokens": prompt + output,
                "input_tokens": prompt,
                "output_tokens": output,
                "reasoning_tokens_included_in_output": sum(
                    (c["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
                    for c in calls
                ),
                "requests": len(calls),
                "request_usage_id_counts": dict(Counter(c["usage_id"] for c in calls)),
                "tools": controller["tool_calls"],
                "stop": stop,
                "normal_finish": controller["normal_completion"],
                "lifecycle_deadline_reached": result["lifecycle_deadline_reached"],
                "length_requests": sum(c.get("finish_reason") == "length" for c in calls),
                "pure_reasoning_length_requests": len(pure),
                "pure_reasoning_length_output_tokens": sum(c["usage"]["completion_tokens"] for c in pure),
                "pure_reasoning_length_total_tokens": sum(c["usage"]["total_tokens"] for c in pure),
                "execution_policy": controller["execution_policy_observed_counts"],
                "source_result": proof(result_path),
                "source_controller": proof(controller_path),
                "score_receipt": proof(receipt),
            }
        )
    groups = {}
    for condition in ("FIX5M", "FIX10M"):
        selected = [r for r in rows if r["condition"] == condition]
        assert len(selected) == 50
        agg = summarize(selected)
        for field in (
            "reasoning_tokens_included_in_output", "tools", "length_requests",
            "pure_reasoning_length_requests", "pure_reasoning_length_output_tokens",
            "pure_reasoning_length_total_tokens",
        ):
            agg["totals"][field] = sum(r[field] for r in selected)
            agg["means"][field] = agg["totals"][field] / 50
        agg["resolved"] = sum(r["resolved"] for r in selected)
        agg["stops"] = dict(Counter(r["stop"] for r in selected))
        agg["lifecycle_deadline_tasks"] = sum(r["lifecycle_deadline_reached"] for r in selected)
        agg["request_usage_id_counts"] = dict(sum((Counter(r["request_usage_id_counts"]) for r in selected), Counter()))
        agg["policy_totals"] = {
            key: sum(r["execution_policy"][key] for r in selected)
            for key in ("stuck_corrections", "finish_reviews")
        }
        groups[condition] = agg
    by_task = defaultdict(dict)
    for row in rows:
        by_task[row["instance_id"]][row["condition"]] = row
    pairs = []
    for task, arms in by_task.items():
        left, right = arms["FIX5M"], arms["FIX10M"]
        assert left["seed"] == right["seed"]
        pairs.append({
            "instance_id": task,
            "same_planned_seed": True,
            "left_tokens": left["total_tokens"], "right_tokens": right["total_tokens"],
            "difference": right["total_tokens"] - left["total_tokens"],
            "left_requests": left["requests"], "right_requests": right["requests"],
            "left_stop": left["stop"], "right_stop": right["stop"],
            "left_resolved": left["resolved"], "right_resolved": right["resolved"],
            "left_pure_reasoning_length": left["pure_reasoning_length_requests"],
            "right_pure_reasoning_length": right["pure_reasoning_length_requests"],
        })
    pairs.sort(key=lambda r: r["difference"], reverse=True)
    diff = contrast(groups["FIX5M"], groups["FIX10M"])
    diff["pure_reasoning_length_total_share_of_increase"] = (
        diff["mean_difference"]["pure_reasoning_length_total_tokens"]
        / diff["mean_difference"]["total_tokens"]
    )
    summary = {
        "version": "v103-qwen-token-difference-r1",
        "sources": [proof(source), proof(plan_path)],
        "groups": groups, "difference": diff,
        "pairs": {
            "more_tokens": sum(r["difference"] > 0 for r in pairs),
            "fewer_tokens": sum(r["difference"] < 0 for r in pairs),
            "median_difference": median(r["difference"] for r in pairs),
            "top_five_positive_difference": pairs[:5],
            "five_most_negative_difference": pairs[-5:],
            "score_transitions": dict(Counter(f'{r["left_resolved"]}->{r["right_resolved"]}' for r in pairs)),
        },
        "interpretation_boundaries": [
            "Same 50 tasks and same preassigned seed; separate independent initial-state runs, not 5M runs continued to 10M.",
            "Context/output limits and FIX protocol unchanged; aggregate prompt usage is repeated across requests.",
            "Calls include agent and condenser; input/output accounting does not estimate semantic redundancy or isolated tool-schema cost.",
            "Pure reasoning length requests have finish_reason=length and reported reasoning_tokens equal completion_tokens; this is not a complete measure of all repetitive reasoning.",
            "No model, Docker, GPU, or network calls; historical results unchanged.",
        ],
    }
    write("qwen-summary.json", summary)
    write("qwen-per-task.json", {"rows": rows, "paired": pairs})


def deepseek() -> None:
    source = ROOT / "artifacts/software-benchmark-v102/deepseek-token-accounting-r1/per-slot-usage.json"
    original = read(source)["original_panel"]
    rows = [
        {
            "slot_id": r["slot_id"], "instance_id": r["instance_id"], "condition": r["arm"],
            "total_tokens": r["known_total_tokens_lower_bound"],
            "input_tokens": r["known_input_tokens_lower_bound"],
            "output_tokens": r["known_output_tokens_lower_bound"], "requests": r["issued_requests"],
            "original_generation_status": r["original_generation_status"], "code_status": r["code_status"],
        }
        for r in original if r["provider_usage_complete_and_called"]
    ]
    by_arm = {a: {r["instance_id"]: r for r in rows if r["condition"] == a} for a in ("REF", "PROJECT")}
    common = set(by_arm["REF"]) & set(by_arm["PROJECT"])
    known = {i for i in common if all(by_arm[a][i]["code_status"] in ("resolved", "unresolved") for a in by_arm)}
    cohorts = {}
    for name, selected_ids in (("all_complete_called_tasks", None), ("paired_complete_called_tasks", common), ("paired_complete_and_code_scored", known)):
        groups = {}
        for arm, tasks in by_arm.items():
            selected = [r for i, r in tasks.items() if selected_ids is None or i in selected_ids]
            groups[arm] = summarize(selected)
            groups[arm]["original_generation_status_counts"] = dict(Counter(r["original_generation_status"] for r in selected))
        cohorts[name] = {"groups": groups, "difference": contrast(groups["REF"], groups["PROJECT"])}
    pairs = [{
        "instance_id": i,
        "REF": by_arm["REF"][i], "PROJECT": by_arm["PROJECT"][i],
        "total_difference": by_arm["PROJECT"][i]["total_tokens"] - by_arm["REF"][i]["total_tokens"],
    } for i in sorted(common)]
    summary = {
        "version": "v103-deepseek-token-difference-r1", "source": proof(source), "cohorts": cohorts,
        "paired_count": len(pairs),
        "paired_project_more_tokens": sum(r["total_difference"] > 0 for r in pairs),
        "paired_project_fewer_tokens": sum(r["total_difference"] < 0 for r in pairs),
        "paired_median_difference": median(r["total_difference"] for r in pairs),
        "interpretation_boundaries": [
            "Original attempts only; independent 44 recovery attempts excluded.",
            "Complete provider usage and at least one API call required; zero calls and incomplete usage excluded from exact means.",
            "Paired complete-task subset diagnoses cost; it does not replace the full planned 500-task score or erase unscored tasks.",
            "API requests include all task-accounted requests; different interfaces may execute different amounts of work per model request.",
            "Higher per-request input is directly measured; its attribution to tool schema, state rendering, history, condenser, or behavior is not separately tokenized or causally isolated here.",
            "Read-only frozen aggregate source; no new database scan, model, Docker, GPU, or network calls.",
        ],
    }
    write("deepseek-summary.json", summary)
    write("deepseek-paired.json", pairs)


if __name__ == "__main__":
    qwen()
    deepseek()
    print(OUTPUT.relative_to(ROOT))
