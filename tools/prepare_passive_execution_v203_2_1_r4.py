"""Prepare the ten remaining original identities; no model, Docker or parent write."""

from __future__ import annotations
from collections import Counter
import copy
import json
import os
from proworksim import software_benchmark_scope_v203_2_1_r4 as scope
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration


def prepare():
    if (scope.API_ROOT / "execution-started.json").exists():
        raise PermissionError("An entered continuation cannot be prepared again")
    old = scope.parent.load(reference(scope.parent.PLAN_FILE))
    chosen = []
    rows = []
    envs = {}
    sources = {}
    resources = {}
    for ordinal, original in enumerate(old["rows"][2:], start=2):
        row = copy.deepcopy(original)
        row.pop("configuration")
        row["slot_index"] = 2032400 + ordinal
        chosen.append(copy.deepcopy(row))
        config = copy.deepcopy(scope.load(original["configuration"]))
        config.update(
            slot_index=row["slot_index"],
            version="v203.2.1-passive-original-task-continuation-config-r4",
        )
        row["configuration"] = scope.retain(
            scope.BATCH_ROOT / "configs" / (str(row["slot_index"]) + ".json"), config
        )
        rows.append(row)
        task = row["instance_id"]
        envs[task] = {
            **copy.deepcopy(old["environments"][task]),
            "configuration": row["configuration"],
        }
        sources[task] = {
            **copy.deepcopy(old["environment_sources"][task]),
            "previous_deployment_configuration": original["configuration"],
            "previous_deployment_plan": reference(scope.parent.PLAN_FILE),
        }
        for role in ("actor", "controller", "volume", "score", "delivery-score"):
            resources[f"{role}-{row['slot_index']}"] = copy.deepcopy(
                old["resources"][f"{role}-{original['slot_index']}"]
            )
    panel = scope.retain(
        scope.PANEL_FILE,
        {
            "version": scope.VERSION,
            "rows": chosen,
            "task_ids": [r["instance_id"] for r in chosen],
            "parent_panel": reference(scope.parent.PANEL_FILE),
            "original_total_planned_tasks": 12,
            "continuation_planned_tasks": 10,
            "new_logical_attempts": 0,
            "same_task_seed_slot_id_and_model_policy": True,
            "additional_cash_CNY": "0.00",
        },
    )
    cpu = scope.retain(
        scope.CPU_POOL_FILE,
        {
            "version": scope.VERSION,
            "uid": os.getuid(),
            "cpu_ids": sorted(os.sched_getaffinity(0)),
            "captured_before_run": True,
        },
    )
    inventory = scope.retain(
        scope.INVENTORY_FILE,
        {
            "version": scope.VERSION,
            "rows": rows,
            "panel": panel,
            "generation": {},
            "scores": {},
            "deliveries": {},
        },
    )
    plan = {
        "version": scope.VERSION,
        "root": str(scope.BATCH_ROOT),
        "panel": panel,
        "matrix": panel,
        "rows": rows,
        "generation_rows": rows,
        "host_cpu_pool": cpu,
        "inventory": inventory,
        "constraints": scope.CONSTRAINTS,
        "environments": envs,
        "environment_sources": sources,
        "resources": resources,
        "resource_role_counts": dict(Counter(v["role"] for v in resources.values())),
        "diagnostics": [],
        "training": False,
        "old_results_preserved": True,
        "new_runtime_scope": True,
        "model_calls_during_preparation": 0,
        "dispatch_admission": declaration(scope.BATCH_ROOT),
        "parent_plan": reference(scope.parent.PLAN_FILE),
        "parent_source": reference(scope.parent.SOURCE_FILE),
        "predecessor_leaf_source": reference(scope.leaf.SOURCE_FILE),
        "engineering_gate_slot_indices": [2032200, 2032201],
        "revalidation_gate_path": str(scope.REVALIDATION_FILE),
        "wave_policy": {
            "prerequisite": "original_first_two_archive_revalidation_and_closed_predecessors",
            "new_first_two_wave": False,
            "maximum_generations": 8,
            "maximum_graders": 2,
            "maximum_startups": 2,
        },
        "qualification_reuse_from_previous": {
            "controls": [],
            "required_strict_environment_equivalence": True,
            "ordinary_source": str(scope.parent.COORDINATOR_ROOT / "qualifications"),
            "requests_CA_source": str(scope.leaf.QUALIFIED_R3_FILE),
        },
        "same_existing_cash_ledger": str(scope.LEDGER_FILE),
        "additional_cash_CNY": "0.00",
        "new_model_attempts": 0,
        "new_physical_actor_controller_pairs": 10,
        "new_physical_volumes": 10,
        "original_first_two_replayed": False,
        "original_total_planned_tasks": 12,
        "continuation_planned_tasks": 10,
        "model_visible_controller_and_bundle_reused_without_changes": True,
    }
    scope.validate_plan(plan)
    result = {
        "plan": scope.retain(scope.PLAN_FILE, plan),
        "panel": panel,
        "model_calls": 0,
        "Docker_operations": 0,
        "cash_ledger_changes": 0,
        "new_cash_budget_CNY": "0.00",
        "new_physical_indices": [2032402, 2032411],
        "original_engineering_gate_indices": [2032200, 2032201],
        "gate_required_only_at_execution": str(scope.REVALIDATION_FILE),
    }
    scope.retain(scope.ARTIFACT_ROOT / "continuation-r4/preparation.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False))
