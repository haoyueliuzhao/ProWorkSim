"""Freeze a repository-stratified 50-task, four-budget REF diagnostic panel."""
from __future__ import annotations

from collections import Counter, defaultdict
import copy
import json
from pathlib import Path
import random

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_ref_budget_v056 import BUDGETS, COMMON_LIMITS, validate_condition

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/software-benchmark-v056"
SEED = 20261024056


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    public = ROOT / "artifacts/software-benchmark-v054/source/public-tasks.json"
    public_ref = reference(public)
    if public_ref["sha256"] != "65d130536d04fda752b6ab36534ec657a8cd9bb0243b36067a1eb45413245aaf":
        raise ValueError("Public Verified task projection changed")
    tasks = json.loads(public.read_bytes())
    by_repo = defaultdict(list)
    for task in sorted(tasks, key=lambda task: task["instance_id"]):
        by_repo[task["repo"]].append(task)
    rng = random.Random(SEED)
    repos = sorted(by_repo)
    for repo in repos:
        rng.shuffle(by_repo[repo])
    rng.shuffle(repos)
    selected = []
    while len(selected) < 50:
        for repo in repos:
            if by_repo[repo] and len(selected) < 50:
                selected.append(by_repo[repo].pop())
    rng.shuffle(selected)
    conditions = {}
    original = json.loads((ROOT / "config/v054-condition-REF.json").read_bytes())
    for name, budget in BUDGETS.items():
        condition = copy.deepcopy(original)
        condition.update(version="v056-ref-budget-condition-r1", condition_id=name,
                         planned_tasks=50, formal_execution_authorized=True, thinking=True)
        condition["episode_limits"].update(COMMON_LIMITS, input_plus_output_tokens=budget)
        condition["interface"]["max_iteration_per_run"] = 512
        for key in ("source_manifest", "residency_protocol", "resource_scheduling_protocol", "service"):
            condition.pop(key, None)
        condition["historical_condition"] = reference(ROOT / "config/v054-condition-REF.json")
        condition["scope"] = "Independent S1 budget calibration, not a new full-500 benchmark score"
        validate_condition(condition)
        conditions[name] = write_new(ROOT / "config" / ("v056-condition-" + name + ".json"), condition)
    rows = []
    names = list(BUDGETS)
    for task_index, task in enumerate(selected):
        seed = SEED * 1000 + task_index
        rotation = task_index % len(names)
        for name in names[rotation:] + names[:rotation]:
            rows.append({"slot_index": len(rows) + 1, "task_index": task_index + 1,
                         "slot_id": f"v056:{task['instance_id']}:{name}:{seed}",
                         "instance_id": task["instance_id"], "repo": task["repo"],
                         "arm": "REF", "condition_id": name, "seed": seed,
                         "input_plus_output_tokens": BUDGETS[name]})
    slots = write_new(OUT / "slots.json", {"version": "v056-ref-budget-slots-r1", "slots": rows})
    permit = write_new(ROOT / "config/v056-ref-budget-authorization.json", {
        "version": "v056-ref-budget-authorization-r1", "execution_authorized": True,
        "authorization": "2026-10-24 user: adjust budget, control groups, only Qwen REF; several large gradients to measure completion boundary",
        "slots_sha256": slots["sha256"], "slot_ids": [row["slot_id"] for row in rows],
        "planned_distinct_tasks": 50, "planned_episodes": 200,
        "aggregate_input_output_token_upper_bound": 50 * sum(BUDGETS.values()),
        "only_model": "Qwen/Qwen3.5-9B", "only_arm": "REF", "training_authorized": False,
        "physical_gpus": list(range(8)), "maximum_active_generation_episodes": 6,
        "maximum_active_official_graders": 2, "automatic_generation_retry": False,
        "dispatch_requires_frozen_source_and_actual_environment_admission": True,
    })
    plan = write_new(OUT / "plan.json", {
        "version": "v056-ref-budget-plan-r1", "selection_seed": SEED,
        "selection": "Shuffled within repository; repository round-robin without replacement; then fixed shuffled task order",
        "selection_uses_previous_scores": False, "previous_scores_read_by_selector": False,
        "task_ids": [row["instance_id"] for row in selected],
        "repository_counts": dict(sorted(Counter(row["repo"] for row in selected).items())),
        "public_tasks": public_ref, "public_test_registry": reference(ROOT / "config/v054-public-test-registry.json"),
        "slots": slots, "conditions": conditions, "authorization": permit,
        "budgets": BUDGETS, "common_limits": COMMON_LIMITS,
        "planned_distinct_tasks": 50, "planned_episodes": 200,
        "aggregate_input_output_token_upper_bound": 50 * sum(BUDGETS.values()),
        "independent_initial_states": True, "same_task_same_seed_across_budgets": True,
        "previous_run_workspaces_or_feedback_reused": False,
        "cache_root": str(ROOT / "runs/software-benchmark-v054/v056-budget-cache-r1"),
        "stdlib": str(ROOT / "runs/software-benchmark-v054/native-binding-control/r3/REF/control-stdlib"),
        "sdk_runtime": str(ROOT / "runs/software-benchmark-v054/native-binding-control/r3/sdk-runtime"),
        "docker_socket": str(ROOT / "runs/software-panel-v053/docker/docker.sock"),
        "maximum_active_generation_episodes": 6, "maximum_active_official_graders": 2,
        "cache_prewarm_ahead_tasks": 2, "disk_minimum_free_bytes": 128 * 1024**3,
        "partial_results_stop_or_task_replacement": False,
        "generation_and_scoring": "Independent asynchronous queues, per-slot exceptions deferred",
        "analysis": ["Official code result; native finish; budget/context/attempt/time/stuck/error separately",
                     "Keep full planned denominator and technical unknowns",
                     "Paired per task and repository; report non-monotonic changes",
                     "No universal sufficient budget claim from 50 tasks or a right-censored maximum tier"],
        "selector_source": reference(__file__),
    })
    print(json.dumps({"plan": plan, "tasks": 50, "episodes": 200,
                      "repository_counts": dict(sorted(Counter(row["repo"] for row in selected).items()))}))


if __name__ == "__main__":
    main()
