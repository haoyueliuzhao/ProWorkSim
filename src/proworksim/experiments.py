"""Parallel mechanism matrix. Counts projects and lineage, not just submissions."""

import platform
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .baseline import run_baseline
from .compiler import compile_world
from .designer import DELIVERIES, INFORMATION_MODES, design
from .kernel import World
from .storage import Store, atomic_write, json_bytes
from .validation import evaluate


def run_matrix(destination, seeds=(11, 29), workers=4):
    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Experiment destination must be empty")
    if workers < 1 or not seeds:
        raise ValueError("Positive worker count and at least one seed are required")
    destination.mkdir(parents=True, exist_ok=True)
    configs = [
        (seed, mode, info) for seed in seeds for mode in DELIVERIES for info in INFORMATION_MODES
    ]
    started = time.monotonic()

    def trial(config):
        seed, mode, info = config
        path = destination / f"seed-{seed}-{mode}-{info}"
        spec = design(seed, mode, info)
        compile_world(spec, path)
        result = run_baseline(World(path).session(), inject_stale_memo=mode == "continuous")
        records = evaluate(path)
        state = Store(path).load()
        final = [item["submissions"][-1]["submission_id"] for item in state["work_items"].values()]
        final_records = [r for r in records if r["submission_id"] in final]
        return {
            "seed": seed,
            "delivery": mode,
            "information": info,
            "lineage_id": spec.project.lineage_id,
            "split": spec.project.split,
            "complete": result["complete"],
            "final_passed": all(r["passed"] for r in final_records),
            "work_items": len(state["work_items"]),
            "submissions": len(records),
            "revisions_requested": sum(
                (s.get("review") or {}).get("decision") == "revision_required"
                for item in state["work_items"].values()
                for s in item["submissions"]
            ),
            "actions": len(state["interactions"]),
            "logical_time": state["clock"],
            "failed_final_checks": [
                c for r in final_records for c in r["checks"] if not c["passed"]
            ],
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        rows = list(executor.map(trial, configs))
    summary = {
        "experiment": "v0.1 mechanism feasibility",
        "policy": "rule_based",
        "python": platform.python_version(),
        "workers": workers,
        "seeds": list(seeds),
        "worlds": len(rows),
        "independent_lineages": len(set(r["lineage_id"] for r in rows)),
        "completed": sum(r["complete"] for r in rows),
        "final_passed": sum(r["final_passed"] for r in rows),
        "wall_seconds": time.monotonic() - started,
        "results": rows,
        "interpretation": "Mechanism feasibility only; no learned policy or training gain measured.",
    }
    atomic_write(destination / "summary.json", json_bytes(summary))
    return summary
