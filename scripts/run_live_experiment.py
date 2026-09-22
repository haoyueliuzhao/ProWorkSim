"""Reproduce one real-model world per delivery, keeping provider and grading results."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.compiler import compile_world
from proworksim.designer import DELIVERIES, design
from proworksim.kernel import World
from proworksim.learning import export_bundle
from proworksim.runtime import DeepSeekBackend, load_env, run_model
from proworksim.storage import Store, atomic_write, json_bytes
from proworksim.validation import evaluate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--seed", type=int, default=101)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=50)
    parser.add_argument("--model")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()
    base = Path(args.output)
    if base.exists():
        parser.error("Output directory must not exist")
    if args.workers < 1:
        parser.error("workers must be positive")
    load_env(args.env_file)
    DeepSeekBackend(model=args.model)  # fail early if credentials are missing
    base.mkdir(parents=True)

    def trial(mode):
        world_path = base / mode
        spec = design(args.seed, mode, "clarification" if mode == "continuous" else "mail")
        compile_world(spec, world_path)
        try:
            result = run_model(
                World(world_path),
                DeepSeekBackend(model=args.model),
                args.max_turns,
                progress=lambda update: print(json.dumps({"delivery": mode, **update}), flush=True),
            )
            records = evaluate(world_path)
            state = Store(world_path).load()
            latest = {}
            for record in records:
                latest[record["work_item_id"]] = record
            result.update(
                {
                    "delivery": mode,
                    "lineage_id": spec.project.lineage_id,
                    "split": spec.project.split,
                    "independent_passed": all(r["passed"] for r in latest.values()),
                    "model_calls": len(state["calls"]),
                    "evaluations": records,
                    "usage": {
                        key: sum((c["usage"] or {}).get(key, 0) for c in state["calls"])
                        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                    },
                }
            )
            result["export"] = export_bundle(world_path, base / "exports" / mode)
        except Exception as exc:
            result = {"delivery": mode, "complete": False, "error": f"{type(exc).__name__}: {exc}"}
        atomic_write(world_path / "result.json", json_bytes(result))
        return result

    with ThreadPoolExecutor(max_workers=min(args.workers, len(DELIVERIES))) as executor:
        results = list(executor.map(trial, DELIVERIES))
    atomic_write(base / "summary.json", json_bytes(results))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if not all(r.get("complete") and r.get("independent_passed") for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
