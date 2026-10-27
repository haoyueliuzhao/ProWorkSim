"""Materialize the twelve conditions and 6000 public task bindings offline."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from proworksim.software_benchmark_full_plan_v064 import COMMON_LIMITS
from proworksim.software_benchmark_ref_plan_v062 import retain
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_benchmark_baseline_v054 import validate_mapping

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "runs/software-benchmark-v064/full-verified-r1"
PANEL = ROOT / "artifacts/software-benchmark-v064/preparation-r1/plan.json"
REGISTRY = ROOT / "config/v054-public-test-registry.json"
PUBLIC = ROOT / "artifacts/software-benchmark-v054/source/public-tasks.json"
BASE = ROOT / "config/v056-condition-REF_B5000K.json"
VERSION = "v064-runtime-config-index-r1"


def condition(group):
    value = json.loads(BASE.read_bytes())
    value.update(version="v064-full-comparison-condition-r1", condition_id=group["group_id"],
                 arm=group["arm"], model_key=group["model_key"], planned_tasks=500,
                 scope="Full Verified test set; development-informed paired interface comparison",
                 thinking=True, formal_execution_authorized=False)
    value.pop("historical_condition", None)
    value["episode_limits"] = {**COMMON_LIMITS,
        "input_plus_output_tokens": group["input_plus_output_tokens"],
        "unknown_usage": "Retain uncertain reservation; never treat missing usage as zero"}
    value["actor_resources"]["pids"] = 512
    value["interface"]["execution_revision"] = "v064_fixed_native" if group["arm"] == "REF" else "v064_managed_S1"
    if group["arm"] == "PROJECT":
        value["interface"] = {"SDK": "1.49.6", "factory": "software_benchmark_managed_v064",
            "context_history": "full_history_then_authorized_capacity_selection",
            "context_limit": 131072, "maximum_full_input": 98304, "output_limit": 32768,
            "all_model_attempts": 512, "agent_decisions": 512, "public_tests": 512,
            "single_managed_action_per_world_step": True, "MCP": False, "browser": False,
            "subagent": False, "unmanaged_shell": False}
        value["delivery_endpoint"] = "last legitimate fixed submission with same-version public-test evidence"
    if group["model_key"] == "DEEPSEEK":
        value["model"] = {"name": "deepseek-flash", "thinking": {"type": "enabled"},
            "reasoning_effort": "high", "expected_provider_release": "DeepSeek-V4.1-Flash-1017",
            "project_adapter": None, "training": False}
        value["numerical_provider"] = "direct official DeepSeek HTTPS; no proxy"
        value["inference"] = {"total_context": 131072, "maximum_full_input": 98304,
            "output_limit": 32768, "max_tokens": 32768, "top_p": .95,
            "thinking": {"type": "enabled"}, "reasoning_effort": "high",
            "automatic_retries": 0, "generation_timeout_seconds": 1800,
            "host_timeout_seconds": 1860, "seed_source": "recorded pairing seed; provider does not support a seed",
            "temperature_and_penalties": "omitted: ineffective in provider thinking mode"}
    return value


def prepare():
    panel = json.loads(PANEL.read_bytes())
    registry = json.loads(REGISTRY.read_bytes())
    entries = {row["instance_id"]: row for row in registry["entries"]}
    public = {row["instance_id"]: row for row in json.loads(PUBLIC.read_bytes())}
    if len(entries) != 500 or len(public) != 500 or set(entries) != set(public):
        raise ValueError("Require the complete fixed public 500-task environment inventory")
    registry_ref, public_ref = reference(REGISTRY), reference(PUBLIC)
    groups = panel["groups"]
    conditions = {key: retain(BATCH / "conditions" / (key + ".json"), condition(group))
                  for key, group in groups.items()}
    sample = json.loads((ROOT / "runs/software-benchmark-v062/capability-probe-r1-20261026/configs/0.json").read_bytes())
    original = sample["scorer_request_base"]
    base_by_task, environments = {}, []
    for task, entry in entries.items():
        if entry.get("admitted") is not True or entry.get("hidden_material_used") is not False:
            raise ValueError("Unadmitted public test environment: " + task)
        mapping = json.loads(checked(entry["baseline_mapping"]).read_bytes())
        image = {"instance_id": task, "repo": public[task]["repo"],
                 "base_commit": public[task]["base_commit"],
                 "image_id": mapping["official_image_id"],
                 "manifest_digest": mapping["official_manifest_digest"]}
        validate_mapping(mapping, instance=public[task], image=image)
        base_by_task[task] = {**{key: copy.deepcopy(original[key]) for key in (
            "dataset", "docker_cli", "docker_socket", "scorer_manifest")},
            "image": image, "baseline_mapping": entry["baseline_mapping"]}
        environments.append({"instance_id": task, "actor_image_id": mapping["actor_image_id"],
                             "image_id": mapping["official_image_id"], "mapping": entry["baseline_mapping"]})
    by_task = {row["instance_id"]: row for row in environments}
    index = []
    for row in panel["rows"]:
        task = row["instance_id"]
        value = {"version": "v064-private-full-condition-config-r1", **row,
            "condition_id": row["group_id"], "execution_arm": row["arm"], "replicate": 0,
            "source_slot_id": "v054-" + row["arm"] + "-" + task,
            "measurement_kind": "full_verified_comparison", "thinking": True,
            "configuration": conditions[row["group_id"]], "public_tasks": public_ref,
            "public_test_registry": registry_ref, "public_test_entry": entries[task],
            "public_task": {key: public[task][key] for key in (
                "instance_id", "repo", "base_commit", "problem_statement")},
            "scorer_request_base": base_by_task[task],
            "hidden_material_in_actor_payload": False, "preparation_only": False}
        ref = retain(BATCH / "configs" / (str(row["slot_index"]) + ".json"), value)
        index.append({"slot_index": row["slot_index"], "configuration": ref,
                      "actor_image_id": by_task[task]["actor_image_id"],
                      "image_id": by_task[task]["image_id"]})
    result = {"version": VERSION, "panel": reference(PANEL), "rows": index,
              "environments": environments, "conditions": conditions,
              "runtime_operations": 0, "model_calls": 0}
    return retain(BATCH / "config-index.json", result)


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False))
