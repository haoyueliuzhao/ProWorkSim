"""Seal the concrete v062 plan and pending new grant without runtime operations."""
from __future__ import annotations

import importlib.util
import json

from proworksim import software_benchmark_dispatch_v062 as policy
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_ref_host_v061 import prepare_runtime
from proworksim.software_benchmark_ref_plan_v062 import retain
from proworksim.software_benchmark_sdk_bundle_v062 import prepare_bundle


def prepare():
    plan = policy.create_plan()
    bundle = prepare_bundle()
    model_runtime = prepare_runtime()
    spec = importlib.util.spec_from_file_location(
        "prepare_v062_coordinator", policy.ROOT / "tools/run_ref_capability_v062.py")
    coordinator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(coordinator)
    coordinator_plan = coordinator.prepare()
    sources = policy.sources()
    constraints = policy.CONSTRAINTS
    assert len(plan["rows"]) == 174
    assert sum(row["generation_token_upper_bound"] for row in plan["rows"]) == 1240000000
    root = policy.ROOT / "artifacts/software-benchmark-v062/runtime-authorization-r1"
    proposal = {
        "version": policy.VERSION,
        "status": "prepared_pending_specific_rootful_permission",
        "user_goal": "修复相关问题，进一步探测模型能力上限",
        "plan": reference(policy.PLAN_FILE), "coordinator_plan": coordinator_plan,
        "constraints": constraints, "operations": sorted(policy.OPERATIONS), "sources": sources,
        "experiment": {
            "model": "original raw Qwen3.5-9B BF16 without adapter",
            "panel_tasks": 50, "repositories": 12,
            "main_conditions": {"BASE5M": 50, "FIX5M": 50, "FIX10M": 50},
            "preselected_repeat_tasks": 12, "extra_FIX10M_repeats_per_task": 2,
            "total_fresh_episodes": 174, "formal_token_upper_bound": 1240000000,
            "neutral_calls_at_most": 2, "neutral_tokens_at_most": 4096,
            "main_results_use_first_predeclared_run": True,
            "repeat_results_are_separate_diagnostics": True,
            "training": False, "multiple_agents": False,
            "prior_scores_or_generations_overwritten": False,
            "scope": "Development/calibration panel; no claim of mathematical capability ceiling",
        },
        "runtime": {
            "sdk_bundle_manifest": reference(policy.ROOT / "runs/software-benchmark-v062/sdk-bundle-r1/manifest.json"),
            "sdk_archive": bundle["archive"], "model_python": model_runtime,
            "model_ports": [18171, 18172],
            "short_socket_directories": [str(policy.ROOT / "runs/g62c1" / f"model-{i}") for i in (0, 1)],
            "existing_user_manager_configuration_changed": False,
            "existing_daemon_start_or_restart": False,
            "host_mount_network_driver_or_linger_changes": False,
            "automatic_model_or_episode_replay": False,
        },
        "rootful_scope": {
            "existing_project_docker_api_only": True,
            "new_owned_containers_at_most": 630,
            "new_owned_named_volumes_at_most": 178,
            "concurrent_actor_controller_pairs": 2, "concurrent_graders": 2,
            "owned_object_cleanup_only": True,
            "host_bind_mounts_or_devices": False,
            "actor_controller_and_ordinary_grader_cap_add": [],
            "requests_offline_grader_cap_add": ["NET_ADMIN"],
            "requests_tls_grader_cap_add": ["NET_ADMIN", "NET_BIND_SERVICE"],
            "all_containers_network": "none", "all_containers_cap_drop": ["ALL"],
            "network_changes_confined_to_owned_private_grader_namespace": True,
        },
        "egress_scope": {
            "actor_or_controller_public_network": False,
            "provider": "bounded grading-only raw TCP through Docker exec",
            "hostname": "httpbin.org", "ports": [80, 443],
            "fixed_prior_resolution": "v060 verified numeric address and immutable resolution receipt",
            "new_dns_or_host_listener": False, "proxy_or_reverse_proxy": False,
            "sessions_at_most": 10, "connections_per_session_at_most": 512,
            "active_connections_per_session_at_most": 16,
            "application_payload_bytes_per_session_at_most": 67108864,
            "application_payload_bytes_total_at_most": 671088640,
            "original_CA_and_TLS_validation_preserved": True,
        },
        "diagnostics": {
            "initial_pairs": {"1": "BASE", "2": "FIX"},
            "reserved_revision_pairs": {"3": "BASE", "4": "FIX"},
            "reserve_requires_prior_zero_model_quiescence_and_changed_sources": True,
            "no_redundant_retest_of_current_qualified_sources": True,
            "automatic_use_of_reserves": False,
        },
        "validation_evidence": [reference(policy.ROOT / path) for path in (
            "artifacts/software-benchmark-v062/native-control-validation-r1/validation.json",
            "artifacts/software-benchmark-v062/runtime-coordinator-validation-r2/validation.json",
        )],
        "actual_model_calls_at_preparation": 0, "actual_container_operations_at_preparation": 0,
        "incident_hold_unchanged": True, "previous_completed_grants_reopened": False,
    }
    proposal_ref = retain(root / "proposal.json", proposal)
    pending = {"version": policy.VERSION, "status": "pending",
        "explicit_rootful_authorization": None, "automatic_release": False,
        "constraints": constraints, "plan": reference(policy.PLAN_FILE),
        "proposal": proposal_ref, "sources": sources}
    retain(root / "pending-authorization.json", pending)
    retain(policy.AUTHORIZATION_FILE, pending)
    return {"proposal": proposal_ref, "authorization": reference(policy.AUTHORIZATION_FILE),
            "coordinator_plan": coordinator_plan, "status": "pending"}


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False))
