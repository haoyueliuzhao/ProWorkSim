"""Fixed-model usability checks of lifecycle semantics; no training or context A/B study."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World
from proworksim.lifecycle import current_work_items
from proworksim.runtime import DeepSeekBackend, load_env, run_model
from proworksim.storage import Store, atomic_write, json_bytes
from proworksim.validation import evaluate


class FixedStaffBackend(DeepSeekBackend):
    def payload(self, messages):
        return {**super().payload(messages), "temperature": 0.0}


CASES = {
    "direct_confirmation": {"delivery": "file"},
    "basis_only": {"scenario": "basis_only"},
    "during_update": {"scenario": "during_update"},
    "waiting_reply": {"scenario": "waiting_reply"},
    "during_review": {"scenario": "during_review"},
    "audience_only": {"topology": "selective"},
    "unavailable": {"scenario": "unavailable"},
}


def run_trials(output, cases, seed=743, workers=3, max_turns=45, model=None):
    root = Path(output)
    if root.exists():
        raise ValueError("Output must be a new directory")
    identity = code_identity()
    FixedStaffBackend(model=model)
    root.mkdir(parents=True)

    def trial(name):
        path = compile_world(design(seed, **CASES[name]), root / name)
        try:
            run = run_model(
                World(path),
                FixedStaffBackend(model=model),
                max_turns=max_turns,
                progress=lambda record: print(json.dumps({"case": name, **record}), flush=True),
            )
            records = evaluate(path)
            state = Store(path).load()
            latest = {row["work_item_id"]: row for row in records}
            active = current_work_items(state)
            validity = bool(active) and all(
                latest[item["work_item_id"]]["artifact_valid"] for item in active
            )
            calls = state["calls"]
            interactions = [r for r in state["interactions"] if r["actor_id"] == "analyst"]
            writes = [r for r in interactions if r["writes"]]
            submissions = [s for item in state["work_items"].values() for s in item["submissions"]]
            requests = list(state.get("requests", {}).values())
            outcome = run["reason"]
            expected = "blocked_unavailable" if name == "unavailable" else "complete"
            observational_checks = {
                "expected_stop_reason": outcome == expected,
                "current_artifacts_valid": None if name == "unavailable" else validity,
                "unavailable_no_fabricated_submission": not submissions
                if name == "unavailable"
                else None,
                "stale_replies_do_not_resolve_new_blockers": all(
                    not any(
                        b["request_id"] == r["request_id"]
                        and b["status"] == "resolved"
                        and b["creation_requirement_version"] != r["requirement_version"]
                        for b in state.get("blockers", {}).values()
                    )
                    for r in requests
                    if r["status"] == "outdated_reply"
                ),
            }
            result = {
                "case": name,
                "project": state["project"],
                "run": run,
                "expected_outcome": expected,
                "observational_checks": observational_checks,
                "worker_task_outcome_as_expected": all(
                    v for v in observational_checks.values() if v is not None
                ),
                "model_calls": len(calls),
                "http_attempts": sum(len(c.get("attempts", [])) for c in calls),
                "models_returned": sorted(
                    {c["model_returned"] for c in calls if c.get("model_returned")}
                ),
                "usage": {
                    key: sum((c.get("usage") or {}).get(key, 0) for c in calls)
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                },
                "analyst_actions": len(interactions),
                "successful_analyst_actions": sum(r["output"]["ok"] for r in interactions),
                "write_actions": len(writes),
                "scope_requests": sum(r["topic"] == "scope" for r in requests),
                "outdated_replies": sum(r["status"] == "outdated_reply" for r in requests),
                "blocked_conditions": state.get("blockers", {}),
                "work_statuses": {
                    k: {
                        "status": w["status"],
                        "applicability": w.get("applicability"),
                        "required_basis": w.get("required_basis"),
                    }
                    for k, w in state["work_items"].items()
                },
                "current_artifact_versions": {
                    aid: a["current_version"] for aid, a in state["artifacts"].items()
                },
                "evaluations": records,
                "interpretation": "A fixed worker trial is one legal/erroneous path; task success is not a proof of world validity.",
            }
        except Exception as exc:
            result = {
                "case": name,
                "error": f"{type(exc).__name__}: {exc}",
                "worker_task_outcome_as_expected": False,
            }
        atomic_write(path / "result.json", json_bytes(result))
        return result

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(trial, cases))
    report = {
        **identity,
        "code_after": code_identity(),
        "experiment": "work-world-semantics-fixed-staff",
        "seed": seed,
        "cases": cases,
        "max_turns": max_turns,
        "workers": workers,
        "model_requested": model or FixedStaffBackend().model,
        "temperature": 0.0,
        "training_performed": False,
        "local_gpu_used": False,
        "results": results,
        "statement": "Mechanism coverage and tool usability, not a training-gain or context-comparison experiment.",
    }
    atomic_write(root / "summary.json", json_bytes(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--cases", choices=tuple(CASES), nargs="+", default=list(CASES))
    parser.add_argument("--seed", type=int, default=743)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=45)
    parser.add_argument("--model")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()
    load_env(args.env_file)
    report = run_trials(
        args.output, args.cases, args.seed, args.workers, args.max_turns, args.model
    )
    print(
        json.dumps(
            {
                "cases": len(report["results"]),
                "outcomes_as_expected": sum(
                    r["worker_task_outcome_as_expected"] for r in report["results"]
                ),
            },
            indent=2,
        )
    )
