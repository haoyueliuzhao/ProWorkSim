"""Prepare the complete paired 500-task matrix without starting any runtime.

Only public task identities and statements are read. Historical model scores,
gold patches and hidden tests are neither inputs nor scheduling criteria.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v064-full-verified-paired-plan-r1"
ORDER_SEED = 20261027064
SEED_NAMESPACE = "v064:20261027064000:"
DATASET_REVISION = "78f471bf655a3137b2e8a75af1501690ec009ec3"
IDENTITY_SHA256 = "6e339ec6a6f6e22a0a04006cf14aa322645fbe33df1b4331e72d0c8e98dc0e69"
PUBLIC_SHA256 = "65d130536d04fda752b6ab36534ec657a8cd9bb0243b36067a1eb45413245aaf"
PUBLIC_FIELDS = ("instance_id", "repo", "base_commit", "image", "problem_statement")
BUDGETS = {"B5000K": 5_000_000, "B7500K": 7_500_000, "B10000K": 10_000_000}
MODEL_KEYS = ("QWEN", "DEEPSEEK")
ARMS = ("REF", "PROJECT")
API_BUDGET_CNY = "1500.00"
COMMON_INFERENCE = {
    "total_context": 131072,
    "maximum_full_input": 98304,
    "output_limit": 32768,
    "max_tokens": 32768,
    "thinking": True,
    "output_includes_reasoning_tokens": True,
}
COMMON_LIMITS = {
    "all_model_attempts": 512,
    "agent_decisions": 512,
    "sdk_iterations": 512,
    "soft_seconds": 21600,
    "hard_seconds": 23400,
    "generation_timeout_seconds": 1800,
}


def reference(path):
    path = Path(path).resolve()
    content = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def retain(path, value):
    """Write once; never replace a frozen matrix or its seeds."""
    path = Path(path)
    content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("Frozen v064 preparation differs: " + str(path))
    else:
        with path.open("xb") as stream:
            stream.write(content)
    return reference(path)


def task_seed(instance_id):
    return int.from_bytes(hashlib.sha256((SEED_NAMESPACE + instance_id).encode()).digest()[:8], "big") % 2**63


def group_profiles():
    groups = {}
    for budget_name, budget in BUDGETS.items():
        for model_key in MODEL_KEYS:
            for arm in ARMS:
                group_id = f"{model_key}_{arm}_{budget_name}"
                groups[group_id] = {
                    "group_id": group_id,
                    "condition_id": group_id,
                    "model_key": model_key,
                    "model": "Qwen/Qwen3.5-9B" if model_key == "QWEN" else "deepseek-flash",
                    "arm": arm,
                    "budget_id": budget_name,
                    "input_plus_output_tokens": budget,
                    "planned_tasks": 500,
                    "inference": copy.deepcopy(COMMON_INFERENCE),
                    "episode_limits": {**COMMON_LIMITS, "input_plus_output_tokens": budget},
                    "single_actual_agent": True,
                    "training": False,
                    "project_training_adapter": None,
                    "execution_protocol": "repaired_native_REF" if arm == "REF" else "managed_PROJECT_S1_aligned_resources",
                    "delivery_endpoint": "last_legal_delivery" if arm == "PROJECT" else None,
                    "provider_seed_sent": model_key == "QWEN",
                    "provider_seed_reproducibility_claim": False,
                }
    return groups


def build_plan(identities, public_tasks):
    """Use every fixed official test identity exactly once in each group."""
    if (identities.get("task_count") != 500
            or identities.get("source", {}).get("revision") != DATASET_REVISION
            or identities.get("source", {}).get("dataset") != "SWE-bench/SWE-bench_Verified"
            or identities.get("source", {}).get("split") != "test"):
        raise ValueError("Require the fixed complete Verified test source")
    identity_rows = identities["tasks"]
    ids = [row["instance_id"] for row in identity_rows]
    if len(ids) != 500 or len(set(ids)) != 500 or len(public_tasks) != 500:
        raise ValueError("The complete 500 unique tasks are mandatory")
    public = {row["instance_id"]: row for row in public_tasks}
    if len(public) != 500 or set(public) != set(ids):
        raise ValueError("Public task identities differ from the official full set")
    for row in identity_rows:
        task = public[row["instance_id"]]
        if set(task) != set(PUBLIC_FIELDS) or any(not isinstance(task[key], str) for key in PUBLIC_FIELDS):
            raise ValueError("Actor projection must contain only the five public fields")
        if any(task[key] != row[key] for key in PUBLIC_FIELDS if key != "problem_statement"):
            raise ValueError("Public repository baseline identity differs")
    repository_counts = dict(sorted(Counter(row["repo"] for row in identity_rows).items()))
    if repository_counts != identities.get("repository_counts"):
        raise ValueError("Repository counts differ from the full dataset")
    order = sorted(ids)
    random.Random(ORDER_SEED).shuffle(order)
    groups = group_profiles()
    names = list(groups)
    rows = []
    for task_index, instance_id in enumerate(order):
        seed = task_seed(instance_id)
        offset = task_index % len(names)
        for group_id in names[offset:] + names[:offset]:
            group = groups[group_id]
            rows.append({
                "slot_index": len(rows),
                "task_index": task_index,
                "slot_id": f"v064:{instance_id}:{group_id}:{seed}",
                "instance_id": instance_id,
                "repo": public[instance_id]["repo"],
                "group_id": group_id,
                "condition_id": group_id,
                "model_key": group["model_key"],
                "model": group["model"],
                "arm": group["arm"],
                "seed": seed,
                "provider_seed_sent": group["provider_seed_sent"],
                "replicate": 0,
                "input_plus_output_tokens": group["input_plus_output_tokens"],
                "generation_token_upper_bound": group["input_plus_output_tokens"],
            })
    token_upper = sum(row["input_plus_output_tokens"] for row in rows)
    api_upper = sum(row["input_plus_output_tokens"] for row in rows if row["model_key"] == "DEEPSEEK")
    assert len(rows) == 6000 and token_upper == 45_000_000_000 and api_upper == 22_500_000_000
    return {
        "version": VERSION,
        "scope": "Complete fixed SWE-bench Verified test set; paired development evaluation",
        "dataset": copy.deepcopy(identities["source"]),
        "task_ids": order,
        "repository_counts": repository_counts,
        "planned_distinct_tasks": 500,
        "planned_groups": 12,
        "planned_episodes": 6000,
        "groups": groups,
        "rows": rows,
        "common_inference": COMMON_INFERENCE,
        "common_limits": COMMON_LIMITS,
        "aggregate_input_output_token_upper_bound": token_upper,
        "api_input_output_token_upper_bound": api_upper,
        "token_upper_bounds_are_forecasts": False,
        "api_total_budget_cny": API_BUDGET_CNY,
        "api_budget_includes": ["formal generation", "condenser", "preparation", "uncertain monetary reservations"],
        "api_budget_exhaustion": "Stop unentered API dispatch; retain all 500 planned identities per group; do not increase the monetary cap",
        "api_budget_exhaustion_not_started_reason": "api_monetary_budget_exhausted",
        "api_budget_guarantees_all_3000_episodes_finish": False,
        "order_seed": ORDER_SEED,
        "seed_namespace": SEED_NAMESPACE,
        "task_order": "Fixed shuffle of sorted complete task IDs; no selection or replacement",
        "group_order": "Twelve groups cyclically rotated by task index; no score-dependent priority",
        "seed_rule": "Same new per-task SHA256 seed in all twelve groups; DeepSeek seed is metadata only and is not sent",
        "same_seed_does_not_guarantee_same_actions": True,
        "independent_initial_states": True,
        "historical_generations_or_workspaces_reused": False,
        "previous_scores_read_by_selector": False,
        "hidden_fields_or_scores_to_actor": False,
        "actor_public_fields": list(PUBLIC_FIELDS),
        "extra_repeats": 0,
        "training": False,
        "runtime_operations_in_preparation": 0,
        "runtime_authorized_by_this_plan_file": False,
        "required_before_dispatch": ["frozen executable model/interface configuration", "actual environment admission", "source and scoped resource authorization", "API monetary reservation for API requests"],
        "analysis_rules": {
            "main_code_denominator_per_group": 500,
            "unfinished_or_technical_unknown_is_not_model_failure": True,
            "official_full_group_point_estimate_requires_all_500_known": True,
            "project_delivery_is_separate_and_ref_is_not_applicable": True,
            "statistics_are_paired_by_task_and_stratified_by_repository": True,
            "independent_confirmation_set_claim": False,
            "actual_tokens_include_prompt_replays_and_condenser": True,
            "reasoning_is_a_subset_of_output_not_an_additional_total": True,
            "cache_hit_and_miss_are_input_subsets_not_extra_tokens": True,
            "reservation_is_not_actual_consumption": True,
        },
    }


def prepare(root=ROOT):
    root = Path(root).resolve()
    identity_path = root / "artifacts/software-benchmark-v054/manifests/identities.json"
    public_path = root / "artifacts/software-benchmark-v054/source/public-tasks.json"
    identity_ref, public_ref = reference(identity_path), reference(public_path)
    if identity_ref["sha256"] != IDENTITY_SHA256 or public_ref["sha256"] != PUBLIC_SHA256:
        raise ValueError("The frozen complete public dataset changed")
    value = build_plan(json.loads(identity_path.read_bytes()), json.loads(public_path.read_bytes()))
    value["sources"] = {"identity_manifest": identity_ref, "public_tasks": public_ref,
                        "selector": reference(__file__)}
    output = root / "artifacts/software-benchmark-v064/preparation-r1"
    plan_ref = retain(output / "plan.json", value)
    summary = {key: value[key] for key in (
        "version", "dataset", "planned_distinct_tasks", "planned_groups", "planned_episodes",
        "repository_counts", "aggregate_input_output_token_upper_bound", "api_input_output_token_upper_bound",
        "api_total_budget_cny", "common_inference", "common_limits", "analysis_rules",
    )}
    summary.update(plan=plan_ref, model_or_runtime_calls=0)
    return {"plan": plan_ref, "summary": retain(output / "summary.json", summary)}
