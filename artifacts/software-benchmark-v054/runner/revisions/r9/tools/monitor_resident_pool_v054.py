"""Freeze a deployment policy or run its durable dynamic resident monitor."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_resident_pool_v054 import POLICY_VERSION, read_ref, validate_pool_policy
from proworksim.software_benchmark_resident_provisioner_v054 import Provisioner, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--source-manifest", type=Path, required=True)
    prepare.add_argument("--inherited-registry", type=Path, required=True)
    prepare.add_argument("--inherited-admission", type=Path, required=True)
    prepare.add_argument("--queue-state", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--policy", type=Path, required=True)
    run.add_argument("--sha256", required=True)
    run.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.operation == "prepare":
        output = args.output.resolve()
        if not output.is_relative_to(ROOT / "runs/software-benchmark-v054"):
            raise ValueError("Pool output must be a new private project run directory")
        registry = reference(args.inherited_registry)
        inherited = read_ref(reference(args.inherited_admission))
        if inherited["registry"] != registry:
            raise ValueError("Existing real handoff evidence belongs to another registry")
        output.mkdir(parents=True, exist_ok=False)
        value = {"version": POLICY_VERSION, "pool_root": str(output),
            "physical_gpus": list(range(8)), "maximum_residents": 8,
            "minimum_free_mib": 46080, "minimum_total_mib": 81920,
            "allowed_gpu_names": ["NVIDIA A800-SXM4-80GB"],
            "allow_co_residency": True, "require_idle": False,
            "maximum_actual_load_attempts_per_gpu": 1,
            "maximum_preparation_calls_per_new_resident": 2,
            "automatic_retry_after_load_failure": False,
            "model_loading_authorized": True, "preparation_generation_authorized": True,
            "ref_to_mp_after_all_500_scored": True, "training_authorized": False,
            "source_manifest": reference(args.source_manifest),
            "inherited_registry": registry, "inherited_admission": reference(args.inherited_admission),
            "match_template_declaration": read_ref(registry)["residents"]["MATCH_PROJECT"],
            "slots": reference(ROOT / "artifacts/software-benchmark-v054/manifests/slots.json"),
            "queue_state_path": str(args.queue_state.resolve()),
            "formal_authorization_not_changed": True,
            "formal_tasks_added": 0, "formal_task_replays": 0,
            "eligibility": "Only exact GPU model, total/free capacity and physical/global leases; other users' jobs and utilization are not exclusion gates",
            "new_device_qualification": "Reuse original identical numerical/model capacity proof; this device gets fresh capacity/startup and exactly two independent synthetic session calls, not a full-context capacity rerun",
            "runtime_revision": "dynamic-resident-pool-r1"}
        item = write_new(output / "policy.json", value)
        validate_pool_policy(item)
        print(json.dumps({"policy": item, "model_loads": 0, "formal_claims": 0}))
    else:
        item = reference(args.policy)
        if item["sha256"] != args.sha256:
            raise ValueError("Monitor policy changed")
        checked(item)
        Provisioner(item).run(once=args.once)


if __name__ == "__main__":
    main()
