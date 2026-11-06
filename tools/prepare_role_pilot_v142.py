"""Freeze a score-independent 40-issue engineering panel; start nothing."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random

from proworksim.software_benchmark_alignment_contract_v141 import (
    GROUP_IDS, TEAM_TOKEN_BUDGET, condition, validate_plan_identity,
)
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/software-benchmark-v118/preparation-r1/panel.json"
OUTPUT = ROOT / "artifacts/software-benchmark-v142/pilot-design-r1"
SELECTION_SEED = 20261106141
ORDER_SEED = 20261106142
EPISODE_SEED_BASE = 20261106014200
FIRST_PHYSICAL_INDEX = 10000


def select_tasks(public_tasks):
    """At most four issues/repo, keeping every source repo represented."""
    groups = defaultdict(list)
    for task in public_tasks:
        if set(task) != {"instance_id", "repo", "base_commit", "problem_statement"}:
            raise ValueError("Selection accepts public task identity and issue text only")
        groups[task["repo"]].append(task)
    if len(public_tasks) != 50 or len({t["instance_id"] for t in public_tasks}) != 50 or len(groups) != 12:
        raise ValueError("This pilot must use the existing50/12 engineering pool")
    rng = random.Random(SELECTION_SEED)
    selected, remainder = [], {}
    for repo in sorted(groups):
        tasks = sorted(groups[repo], key=lambda task: task["instance_id"])
        rng.shuffle(tasks)
        first = min(3, len(tasks))
        selected.extend(tasks[:first])
        remainder[repo] = tasks[first:]
    eligible = [repo for repo in sorted(remainder) if remainder[repo]]
    rng.shuffle(eligible)
    for repo in eligible:
        if len(selected) == 40:
            break
        selected.append(remainder[repo][0])
    if len(selected) != 40 or len({task["repo"] for task in selected}) != 12:
        raise ValueError("The fixed stratified pilot cannot be constructed")
    return selected


def build(source):
    selected = select_tasks(source["public_tasks"])
    rng = random.Random(ORDER_SEED)
    rng.shuffle(selected)
    all_orders = [
        ("S1", "FREE2", "REVIEW2"), ("S1", "REVIEW2", "FREE2"),
        ("FREE2", "S1", "REVIEW2"), ("FREE2", "REVIEW2", "S1"),
        ("REVIEW2", "S1", "FREE2"), ("REVIEW2", "FREE2", "S1"),
    ]
    # Six-order blocks balance early/late condition positions. No score is read.
    order_cycle = []
    while len(order_cycle) < len(selected):
        block = list(all_orders)
        rng.shuffle(block)
        order_cycle.extend(block)
    rows = []
    for index, task in enumerate(selected):
        seed = EPISODE_SEED_BASE + index
        for position, group in enumerate(order_cycle[index]):
            spec = condition(group)
            row = {
                "logical_index": len(rows), "slot_index": FIRST_PHYSICAL_INDEX + len(rows),
                "task_index": index, "within_task_order": position,
                "instance_id": task["instance_id"], "repo": task["repo"],
                "source_slot_id": "v054-PROJECT-" + task["instance_id"],
                "slot_id": f"v142:{task['instance_id']}:{spec['condition_id']}:{seed}",
                "seed": seed, "provider_seed_sent": False,
                "condition_id": spec["condition_id"], "group_id": group,
                "organization_id": group, "fixed_members": spec["fixed_members"],
                "member_count": spec["member_count"],
                "arm": "PROJECT", "execution_arm": "PROJECT",
                "model_key": "DEEPSEEK", "model": "deepseek-flash", "thinking": False,
                "replicate": 0, "repeat_index": 0,
                "budget_tokens": TEAM_TOKEN_BUDGET,
                "input_plus_output_tokens": TEAM_TOKEN_BUDGET,
                "generation_token_upper_bound": TEAM_TOKEN_BUDGET,
                "budget_scope": "whole_team_including_summaries_and_communication",
                "measurement_kind": "full_verified_comparison",
                "panel_kind": "engineering_mechanism_pilot_not_confirmation",
                "independent_initial_state": True,
            }
            validate_plan_identity(row)
            rows.append(row)
    public_hash = hashlib.sha256(json.dumps(selected, ensure_ascii=False, sort_keys=True,
                                            separators=(",", ":")).encode()).hexdigest()
    return {
        "version": "v142-three-baseline40-pilot-selection-r1",
        "source": reference(SOURCE),
        "source_pool": "Previously exposed50-task12-repository development/calibration panel",
        "selection_seed": SELECTION_SEED, "condition_order_seed": ORDER_SEED,
        "selection_rule": "Sorted repos; seeded per-repo shuffle; up to3 each, then one extra from shuffled eligible repos until40.",
        "selection_uses_scores_patches_or_previous_success": False,
        "independent_confirmation_set": False,
        "repo_isolated_independent_confirmation_prepared": False,
        "distinct_tasks": 40, "repositories": 12, "planned_generations": 120,
        "extra_repeats": 0, "conditions": list(GROUP_IDS),
        "task_ids": [task["instance_id"] for task in selected],
        "repository_counts": dict(Counter(task["repo"] for task in selected)),
        "public_tasks": selected, "public_task_sha256": public_hash,
        "actor_public_fields": ["instance_id", "repo", "base_commit", "problem_statement"],
        "rows": rows,
        "generation_token_upper_bound": 600_000_000,
        "token_upper_bound_is_expected_consumption": False,
        "cash_budget_CNY": "400.00", "cash_ledger_scope": "new_pilot_only_all_three_conditions",
        "old_ledgers_modified": False, "cash_guarantees_all_120_complete": False,
        "cash_stop_is_recorded_without_changing_planned_denominator": True,
        "primary_metric": "official_last_legal_delivery_resolved",
        "secondary_metric": "official_unique_final001_code_resolved",
        "metrics_to_keep_separate": ["technical_unknown", "environment_not_qualified", "token_boundary", "cash_boundary"],
        "statistical_scope": "Paired engineering pilot, not a powered architecture ranking",
        "source_blocked_task_substitution": False, "automatic_resampling": False,
        "future_P2_P3_P4_enabled": False, "model_parameter_training": False,
        "new_API_calls": 0, "new_Docker_objects": 0,
        "runtime_authorized_by_this_plan": False,
        "required_before_generation": [
            "P0 public-report, explicit-handoff, state, observability and memory CPU controls",
            "Actual private SDK/bundle wiring and source freeze",
            "Explicit new Docker object scope and ordinary-user coordinator ownership",
            "Actual per-source gold/empty admission or valid source-bound equivalence",
            "New400CNY hard ledger and direct no-search model route",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    source = json.loads(SOURCE.read_text())
    panel = build(source)
    args.output.mkdir(parents=True, exist_ok=True)
    result = write_new(args.output / "panel.json", panel)
    print(json.dumps({"panel": result, "tasks": panel["distinct_tasks"],
                      "rows": len(panel["rows"]), "repositories": panel["repository_counts"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
