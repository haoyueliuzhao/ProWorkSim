"""Finite structure feasibility and paired context inheritance experiments."""

import argparse
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.baseline import run_baseline
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World
from proworksim.learning import export_bundle
from proworksim.runtime import DeepSeekBackend, load_env, run_model
from proworksim.storage import Store, atomic_write, digest, json_bytes
from proworksim.validation import evaluate

TOPOLOGIES = ("chain", "fork", "selective", "coordination")


def summarize(path, initial_call_count=0):
    records = evaluate(path)
    state = Store(path).load()
    final = {
        work["submissions"][-1]["submission_id"]
        for work in state["work_items"].values()
        if work["submissions"]
    }
    final_records = [r for r in records if r["submission_id"] in final]
    calls = state["calls"][initial_call_count:]
    return {
        "project": state["project"],
        "work_items": len(state["work_items"]),
        "business_complete": World(path).observe()["complete"],
        "artifact_valid": len(final_records) == len(state["work_items"])
        and all(r["passed"] for r in final_records),
        "failed_checks": [
            {
                "work_item_id": r["work_item_id"],
                "checks": [c["name"] for c in r["checks"] if not c["passed"]],
            }
            for r in records
            if not r["passed"]
        ],
        "logical_calls": len(calls),
        "http_attempts": sum(len(c.get("attempts", [])) for c in calls),
        "usage": {
            k: sum((c.get("usage") or {}).get(k, 0) for c in calls)
            for k in ("prompt_tokens", "completion_tokens", "total_tokens")
        },
        "artifact_versions": {a: v["current_version"] for a, v in state["artifacts"].items()},
        "freshness": {a: v.get("freshness") for a, v in state["artifacts"].items()},
        "revision_requests": sum(
            (sub.get("review") or {}).get("decision") == "revision_required"
            for w in state["work_items"].values()
            for sub in w["submissions"]
        ),
    }


def semantic_state(state):
    keys = (
        "clock",
        "project",
        "roles",
        "artifacts",
        "messages",
        "events",
        "event_history",
        "work_items",
        "knowledge",
        "workflow",
        "released_groups",
        "fired_rules",
        "layout",
    )
    return digest(json_bytes({k: state[k] for k in keys if k in state}))


def run_experiment(args):
    base = Path(args.output)
    if base.exists():
        raise ValueError("Experiment destination must not exist")
    if args.workers < 1:
        raise ValueError("workers must be positive")
    base.mkdir(parents=True)
    identity = code_identity()
    load_env(args.env_file)
    if args.kind != "mechanism":
        DeepSeekBackend()

    def structure_trial(config):
        seed, topology, layout = config
        path = compile_world(
            design(seed, topology=topology, layout=layout), base / f"{seed}-{topology}-{layout}"
        )
        try:
            if args.kind == "mechanism":
                run = run_baseline(
                    World(path).session(), inject_stale_memo=topology == "coordination"
                )
            else:
                run = run_model(
                    World(path),
                    DeepSeekBackend(),
                    args.max_turns,
                    progress=lambda p: print(json.dumps({"topology": topology, **p}), flush=True),
                )
            result = {"run": run, **summarize(path)}
            if args.kind == "live":
                result["export"] = export_bundle(path, base / "exports" / path.name)["counts"]
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}", "path": str(path)}
        atomic_write(path / "result.json", json_bytes(result))
        return result

    def paired_trial(seed):
        initial = compile_world(
            design(seed, information="clarification"), base / f"{seed}-stage-one"
        )
        world = World(initial)
        try:
            prefix = run_model(
                world,
                DeepSeekBackend(),
                args.max_turns,
                stop_when=lambda obs: any(w["requirement_version"] == 2 for w in obs["work_items"]),
                progress=lambda p: print(
                    json.dumps({"seed": seed, "condition": "prefix", **p}), flush=True
                ),
            )
            if prefix["reason"] != "experiment_boundary":
                return {"seed": seed, "error": "No matched second-stage boundary", "prefix": prefix}
            state = world.store.load()
            if state["work_items"]["work-2"]["status"] != "open":
                return {
                    "seed": seed,
                    "error": "Stage two already advanced inside a parallel tool batch",
                }
            evaluate(initial, "work-1")
            first_grade = world.store.load()["evaluations"][-1]
            if not first_grade["passed"]:
                return {
                    "seed": seed,
                    "error": "Stage one artifacts did not pass independent checks",
                    "evaluation": first_grade,
                }
            snapshot = world.snapshot(base / f"{seed}-boundary")
            conditions = []
            for condition in ("history", "reset_context"):
                branch = World.restore(snapshot, base / f"{seed}-{condition}")
                if condition == "reset_context":
                    with branch.store.lock():
                        branch_state = branch.store.load()
                        previous = branch_state.get("runtime", {}).pop("analyst", None)
                        branch_state.setdefault("context_archives", []).append(
                            copy.deepcopy(previous)
                        )
                        branch.store.save(branch_state)
                count = len(branch.store.load()["calls"])
                start_hash = semantic_state(branch.store.load())
                result = run_model(
                    branch,
                    DeepSeekBackend(),
                    args.max_turns,
                    progress=lambda p: print(
                        json.dumps({"seed": seed, "condition": condition, **p}), flush=True
                    ),
                )
                conditions.append(
                    {
                        "condition": condition,
                        "initial_semantic_state_sha256": start_hash,
                        "run": result,
                        **summarize(branch.store.root, count),
                    }
                )
            return {
                "seed": seed,
                "prefix": prefix,
                "conditions": conditions,
                "matched_initial_world": len(
                    {c["initial_semantic_state_sha256"] for c in conditions}
                )
                == 1,
            }
        except Exception as exc:
            return {"seed": seed, "error": f"{type(exc).__name__}: {exc}"}

    if args.kind == "paired":
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            results = list(executor.map(paired_trial, args.seeds))
    else:
        configs = [
            (seed, topology, layout)
            for seed in args.seeds
            for topology in TOPOLOGIES
            for layout in (("standard", "shifted") if args.kind == "mechanism" else ("shifted",))
        ]
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            results = list(executor.map(structure_trial, configs))
    report = {
        **identity,
        "kind": args.kind,
        "seeds": args.seeds,
        "max_turns": args.max_turns,
        "workers": args.workers,
        "results": results,
        "interpretation": "feasibility only; no statistically powered learning-gain or causality claim",
    }
    atomic_write(base / "summary.json", json_bytes(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("mechanism", "live", "paired"))
    parser.add_argument("output")
    parser.add_argument("--seeds", type=int, nargs="+", default=[211, 223])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-turns", type=int, default=60)
    parser.add_argument("--env-file", default=".env")
    run_experiment(parser.parse_args())
