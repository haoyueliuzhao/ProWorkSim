"""Prepare eight explicit unresolved endpoints without replaying any model."""

from __future__ import annotations

import copy
import json
from collections import Counter

from proworksim import software_benchmark_scope_v114 as scope
from proworksim import software_benchmark_scope_v113 as prior
from proworksim.software_benchmark_candidates_v054 import reference

GENERATION_INDICES = frozenset({7238, 7239, 7266, 7267})
LOCKED_INDICES = frozenset({7232, 7283})
STOPPED_INDICES = frozenset({7244, 7251})
FRESH_CONTROLS = (
    "psf__requests-1766",
    "psf__requests-1921",
    "sphinx-doc__sphinx-10614",
    "pylint-dev__pylint-6528",
)


def prepare():
    if scope.AUTH_FILE.exists() or (scope.API_ROOT / "execution-started.json").exists():
        raise PermissionError("No re-preparation after approval or entry")
    old = scope.load(reference(prior.PLAN_FILE))
    summary_ref = reference(prior.API_ROOT / "run-summary.json")
    summary = scope.load(summary_ref)
    if (
        summary.get("failure") is not None
        or summary.get("pending_grading_jobs")
        or list((scope.BATCH_ROOT / "resource-claims").glob("active-*.json"))
    ):
        raise PermissionError("The original queue must be terminal and quiescent")
    selected = GENERATION_INDICES | LOCKED_INDICES | STOPPED_INDICES
    rows = [copy.deepcopy(row) for row in old["rows"] if row["slot_index"] in selected]
    generations = [row for row in rows if row["slot_index"] in GENERATION_INDICES]
    recoveries = []
    resources = {}
    for row in rows:
        index = row["slot_index"]
        old_state = summary["generation"][row["slot_id"]]
        if index in GENERATION_INDICES:
            if old_state.get("status") != "not_started" or old_state.get("entered") is not False:
                raise PermissionError(
                    "Only never-entered original generation identities may continue"
                )
            if (scope.BATCH_ROOT / "episodes" / str(index)).exists():
                raise PermissionError("An original generation workspace already exists")
            for role in ("actor", "controller", "volume", "score"):
                key = f"{role}-{index}"
                if (scope.BATCH_ROOT / "resource-claims" / (key + ".json")).exists():
                    raise PermissionError("Unstarted resource identity was consumed")
                resources[key] = copy.deepcopy(old["resources"][key])
            if row["arm"] == "PROJECT":
                key = f"delivery-score-{index}"
                resources[key] = copy.deepcopy(old["resources"][key])
        else:
            source = old_state["result"]
            if index in LOCKED_INDICES:
                if old_state["status"] != "closed":
                    raise ValueError("Original locked generation must stay closed")
                kind = "original_locked"
                result = source
                endpoint = "code"
            else:
                if old_state["status"] != "technical_unknown":
                    raise ValueError("Original failed generation must stay unknown")
                result = reference(
                    scope.ROOT
                    / f"runs/software-benchmark-v114/stopped-code-recovery-r1/{index}/recovery-result.json"
                )
                kind = "recovered_stopped_code"
                endpoint = kind
            recoveries.append(
                {
                    "row": row,
                    "kind": kind,
                    "result": result,
                    "endpoint": "code",
                    "original_generation_result": source,
                }
            )
            key = f"score-v114-{index}"
            resources[key] = {
                **copy.deepcopy(old["resources"][f"score-{index}"]),
                "endpoint": endpoint,
                "recovery_kind": kind,
            }
    tasks = {row["instance_id"] for row in rows}
    environments = {task: copy.deepcopy(old["environments"][task]) for task in tasks}
    for task in FRESH_CONTROLS:
        for kind in ("gold", "empty"):
            key = f"control-v114-{task}-{kind}"
            resources[key] = {
                "role": "control",
                "instance_id": task,
                "patch_kind": kind,
                "image_id": environments[task]["image_id"],
                "endpoint": "environment_control",
            }
    counts = dict(Counter(value["role"] for value in resources.values()))
    if counts != {
        "actor": 4,
        "controller": 4,
        "volume": 4,
        "score": 8,
        "delivery_score": 2,
        "control": 8,
    }:
        raise ValueError("Unexpected recovery object count")
    plan = {
        "version": scope.VERSION,
        "root": str(scope.BATCH_ROOT),
        "rows": rows,
        "generation_rows": generations,
        "score_recoveries": recoveries,
        "fresh_control_tasks": list(FRESH_CONTROLS),
        "panel": reference(scope.PANEL_FILE),
        "matrix": reference(scope.PANEL_FILE),
        "host_cpu_pool": reference(scope.CPU_POOL_FILE),
        "constraints": copy.deepcopy(scope.CONSTRAINTS),
        "environments": environments,
        "environment_sources": {task: old["environment_sources"][task] for task in tasks},
        "resources": resources,
        "resource_role_counts": counts,
        "diagnostics": [],
        "original_plan": reference(prior.PLAN_FILE),
        "original_summary": summary_ref,
        "network_resolution": reference(scope.NETWORK_RESOLUTION_FILE),
        "CA_profile": reference(scope.CA_PROFILE_FILE),
        "reused_API_qualification": reference(scope.BATCH_ROOT / "api-qualification/result.json"),
        "generation_input_output_upper_bound": 20_000_000,
        "real_model_calls_during_preparation": 0,
        "Docker_operations": 0,
        "old_results_overwritten": False,
        "old_called_models_resampled": False,
        "stopped_tree_scores_replace_original_primary_results": False,
    }
    scope.validate_plan(plan)
    return {
        "plan": scope.retain(scope.PLAN_FILE, plan),
        "resource_role_counts": counts,
        "first_generations": 4,
        "original_locked_rescores": 2,
        "supplemental_stopped_tree_scores": 2,
        "new_controls": 8,
        "authorized": False,
    }


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False))
