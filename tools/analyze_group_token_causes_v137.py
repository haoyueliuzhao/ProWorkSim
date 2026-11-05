"""Decompose the frozen v136 subset's token use without new experiment work."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/software-benchmark-v136"
OUTPUT = ROOT / "artifacts/software-benchmark-v137/token-causes-r1"


def read(path):
    raw = path.read_bytes()
    return json.loads(raw), {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def build():
    score, score_ref = read(BASE / "cash-excluded-analysis-r1/summary.json")
    rows, rows_ref = read(BASE / "cash-excluded-analysis-r1/selected-per-task.json")
    mechanism, mechanism_ref = read(BASE / "cash-excluded-mechanism-r1/summary.json")
    result = {
        "version": "v137-fixed-subset-token-decomposition-r1",
        "created_UTC": datetime.now(timezone.utc).isoformat(),
        "sources": {"score_and_usage": score_ref, "selected_rows": rows_ref, "mechanism": mechanism_ref},
        "selected_tasks": len(rows), "groups": {},
        "boundaries": [
            "The exact v136 cash/unknown-excluded task selection is retained; no new score selection.",
            "Calls times mean billed tokens per call is an accounting identity, not a causal intervention.",
            "Tool-attributed request tokens include the whole prompt history, not the marginal cost of that tool.",
            "A member's token share is expenditure, not its share of useful contribution.",
            "Multiple private histories can repeat context, but repeated semantic work was not measured here.",
            "API calls include agent and condenser calls; cached input is still part of task token accounting.",
        ],
        "new_API_calls": 0, "new_tests_or_grading": 0, "Docker_operations": 0,
    }
    for group, data in score["groups"].items():
        selected = [row for row in rows if row["group"] == group]
        behavior = mechanism["groups"][group]["behavior"]
        if len(selected) != data["n"] or behavior["actual_tokens"] != data["team_tokens"]["total_tokens"]:
            raise ValueError("Frozen subset token denominator changed")
        calls, s1_calls = sum(row["requests"] for row in selected), sum(row["S1_requests"] for row in selected)
        tokens, s1_tokens = data["team_tokens"], data["S1_tokens"]
        if calls != behavior["actual_calls"]:
            raise ValueError("Behavior call count and usage count disagree")
        per_call, s1_per_call = tokens["total_tokens"] / calls, s1_tokens["total_tokens"] / s1_calls
        factor = calls / s1_calls * (per_call / s1_per_call)
        if abs(factor - data["token_ratio_to_same_task_S1"]) > 1e-12:
            raise ValueError("Call and per-call factorization does not reconcile")
        roles = mechanism["groups"][group]["member_role_costs"]
        members = {
            member: {**values, "mean_tokens_per_team_task": values["tokens"] / data["n"]}
            for member, values in roles.items()
        }
        by_outcome = {}
        for outcome in (True, False):
            subset = [row for row in selected if row["code_passed"] is outcome]
            by_outcome["passed" if outcome else "failed"] = {
                "n": len(subset), "tokens": sum(row["tokens"]["total_tokens"] for row in subset),
                "mean_tokens": sum(row["tokens"]["total_tokens"] for row in subset) / len(subset)
                if subset else None,
                "mean_calls": sum(row["requests"] for row in subset) / len(subset) if subset else None,
                "instances": [row["instance_id"] for row in subset],
            }
        result["groups"][group] = {
            "n": data["n"], "code_passed": data["code_passed"],
            "S1_code_passed_same_tasks": data["S1_code_passed_on_same_tasks"],
            "team_mean_tokens": data["mean_team_tokens"], "S1_mean_tokens": data["mean_S1_tokens"],
            "team_mean_calls": calls / data["n"], "S1_mean_calls": s1_calls / data["n"],
            "call_count_factor": calls / s1_calls,
            "mean_team_input_per_call": tokens["input_tokens"] / calls,
            "mean_S1_input_per_call": s1_tokens["input_tokens"] / s1_calls,
            "mean_total_tokens_per_call_factor": per_call / s1_per_call,
            "total_token_factor": factor,
            "input_fraction": tokens["input_tokens"] / tokens["total_tokens"],
            "output_fraction": tokens["output_tokens"] / tokens["total_tokens"],
            "condenser_fraction": behavior["condenser_tokens"] / tokens["total_tokens"],
            "members": members,
            "operations": {
                category: {**value, "mean_actions": value["dispatched"] / data["n"],
                           "action_share": value["dispatched"] / behavior["performed_actions"],
                           "whole_request_tokens_share": value["request_tokens"] / tokens["total_tokens"]}
                for category, value in behavior["categories"].items()
            },
            "collaboration_action_share": behavior["collaboration_action_fraction"],
            "end_reasons": data["end_reasons"], "by_code_outcome": by_outcome,
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Preserve the existing token-cause snapshot")
    result = build()
    args.output.mkdir(parents=True)
    (args.output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({group: {key: values[key] for key in (
        "n", "call_count_factor", "mean_total_tokens_per_call_factor", "total_token_factor",
        "input_fraction", "condenser_fraction")}
        for group, values in result["groups"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
