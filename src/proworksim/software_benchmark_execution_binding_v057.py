"""Bind repaired execution to new slots without reopening the historical panel."""
from __future__ import annotations

import json
from pathlib import Path

from .software_benchmark_candidates_v054 import checked

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v057-ref-execution-policy-r2-shared-server-hold"
REQUIRED_SOURCES = (
    "src/proworksim/software_benchmark_execution_binding_v057.py",
    "src/proworksim/software_benchmark_exact_transport_v057.py",
    "src/proworksim/software_benchmark_native_execution_v057.py",
    "src/proworksim/software_benchmark_runner_v057.py",
    "tools/run_ref_budget_controller_v057.py",
    "src/proworksim/software_benchmark_shared_server_hold_v057.py",
    "config/v057-shared-server-hold.json",
)
POLICY_FIELDS = {
    "version": VERSION, "execution_group": "REF_REPAIRED_V057",
    "reasoning_projection": "v057-exact-native-response-projection-r2-fault-guard",
    "workflow": "v057-public-guidance-and-one-stuck-correction-r1",
    "maximum_stuck_corrections": 1, "native_tool_semantics_changed": False,
    "stuck_detector_retained": True, "ledger_reset": False,
    "additional_agents": 0, "automatic_model_retries": 0,
    "inference_limits_changed": False, "public_guidance_only": True,
    "old_episode_replay_permitted": False,
    "shared_server_hold_required": True,
    "shared_server_hold_version": "v057-shared-server-incident-hold-r1",
    "automatic_experiment_resume": False,
}


def validate_execution_policy(policy_reference):
    policy = json.loads(checked(policy_reference).read_bytes())
    if any(policy.get(key) != value for key, value in POLICY_FIELDS.items()):
        raise ValueError("Unexpected repaired native execution policy")
    sources = policy.get("sources", [])
    if {item["path"] for item in sources} != {str(ROOT / name) for name in REQUIRED_SOURCES}:
        raise ValueError("Repaired execution needs the complete versioned source seal")
    for source in sources:
        checked(source)
    return policy


def validate_new_execution(config):
    policy = validate_execution_policy(config["execution_policy"])
    if (config.get("execution_group") != policy["execution_group"]
            or not isinstance(config.get("slot_id"), str)
            or not config["slot_id"].startswith("v057:")):
        raise ValueError("Repaired execution requires a fresh v057 slot and explicit group")
    return policy
