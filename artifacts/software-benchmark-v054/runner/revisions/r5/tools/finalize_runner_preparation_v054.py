"""Freeze completed small-source preparation evidence; never load a model or claim a slot."""
from __future__ import annotations

import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_service_factory_v054 import condition_reference, templates
from proworksim.software_benchmark_source_freeze_v054 import freeze_sources
from proworksim.storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "artifacts/software-benchmark-v054/runner"
    source = freeze_sources()
    for arm in ("REF", "MATCH", "PROJECT"):
        path = ROOT / ("config/v054-condition-" + arm + ".json")
        condition = json.loads(path.read_text())
        condition["source_manifest"] = source
        atomic_write(path, json_bytes(condition))
    service = write_new(output / "formal-service-templates.json", templates())
    registry = ROOT / "config/v054-public-test-registry.json"
    public = json.loads(registry.read_text())
    if (public["actual_repository_entries_admitted"] != 500 or public["unresolved_tasks"]
            or len(public["entries"]) != 500):
        raise ValueError("The whole planned public panel is not ready")
    control = ROOT / "runs/software-benchmark-v054/deployment-control-r2/receipt.json"
    if json.loads(control.read_text())["status"] != "passed":
        raise ValueError("New deployment boundary has not passed its necessary control")
    deployment = write_new(output / "deployment-control-r2.json", json.loads(control.read_text()))
    boundary = write_new(output / "normal-boundary-control-r2.json", json.loads((
        ROOT / "runs/software-benchmark-v054/normal-boundary-control-r2/receipt.json").read_text()))
    capacity = ROOT / "artifacts/software-benchmark-v054/native-environment/model-capacity-admission.json"
    manifest = {
        "version": "v054-final-single-slot-preparation-v1",
        "single_slot_runner_implemented": True, "cpu_three_arm_integration_passed": True,
        "public_test_registry_ready": True, "planned_tasks": 500, "public_entries_admitted": 500,
        "public_frontend_families_observed": 21, "full_public_suites_executed": 0,
        "lazy_native_factory_implemented": True, "all_500_rootfs_preexpanded": False,
        "fixed_condition_files": {arm: condition_reference(arm) for arm in ("REF", "MATCH", "PROJECT")},
        "formal_model_service_factory_implemented": True, "formal_service_templates": service,
        "condition_and_source_verification_precedes_slot_claim": True,
        "GPU_and_REF_port_leases_precede_slot_claim": True,
        "inherited_lease_descriptors_retained_until_model_cgroup_quiet": True,
        "temporary_rootfs_cleanup_after_complete_evidence_and_quiescence": True,
        "safe_complete_output_bytes_per_stream": 16 * 1024**2,
        "source_manifest": source, "public_test_registry": reference(registry),
        "final_500_actor_baselines": reference(ROOT / "artifacts/software-benchmark-v054/actor/actor-baseline-index-r3.json"),
        "cpu_three_arm_evidence": reference(output / "cpu-integration.json"),
        "deployment_control": deployment,
        "known_preexecution_budget_boundary_closes_candidate": True,
        "normal_boundary_control": boundary,
        "safe_output_cleanup_control": reference(ROOT / "artifacts/software-benchmark-v054/native-environment/rootfs-io-control-r1.json"),
        "lazy_native_evidence": reference(ROOT / "artifacts/software-benchmark-v054/native-environment/lazy-runtime-r3.json"),
        "official_scorer": reference(ROOT / "artifacts/software-benchmark-v054/scorer/installation-manifest-r5.json"),
        "capacity_admission": reference(capacity) if capacity.exists() else None,
        "formal_authorization_separate": True, "formal_execution_authorized_by_this_manifest": False,
        "formal_slots_claimed_by_preparation": 0, "actual_model_calls_in_CPU_controls": 0,
        "actual_GPU_loads_in_CPU_controls": 0,
        "limitations": ["Three-arm CPU integration used explicit programmed responses and prior r2 baseline",
            "Final baseline/version equality uses independent all-500 r3/r3.1 evidence",
            "Only 21 public frontend family controls; no all-500 full suite rerun",
            "Capacity qualification and formal experiment authorization are independent records"],
    }
    print(json.dumps(write_new(output / "preparation-manifest.json", manifest)))


if __name__ == "__main__":
    main()
