"""Resume only unentered Qwen slots after the one evidenced prewarm disk failure.

This is a separate host revision. The original solver sources, resident models,
slot identities, claims, scoring and GPU6 kernel activation remain untouched.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path

import run_kernel_queue_transition_v054 as transition
from proworksim import software_benchmark_fault_queue_v054 as fault
from proworksim import software_benchmark_kernel_queue_v054 as kernel
from proworksim import software_benchmark_prewarm_v054 as prewarm
from proworksim import software_benchmark_queue_v054 as base
from proworksim import software_benchmark_queue_native_host_v055_r4 as disk
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

VERSION = "v054-qualified-template-resource-recovery-host-r1"
TOOL = "tools/run_qwen_resource_recovery_v054_r1.py"
GUARD = "src/proworksim/software_benchmark_queue_native_host_v055_r4.py"
INSTANCE = "matplotlib__matplotlib-25122"
DISK_ERROR = "Native rootfs disk reserve gate during export"
PREVIOUS_UNIT = "proworksim-v054-formal-queue-kernel-r4.service"
EVENT_ROOT = base.ROOT / "runs/software-benchmark-v054/native-prewarm-r4/events"
NEW_QUEUE = base.ROOT / "runs/software-benchmark-v055/queue-r1/state.json"


def admitted_prewarm_health(health, recovery):
    """Only the sealed disk-export failure and its ended worker are deferred."""
    if (health.get("status") != "failed"
            or health.get("active_preparation") != []
            or health.get("failures") != recovery["allowed_prewarm_failures"]
            or health.get("last_event") != recovery["disk_failure_event"]):
        raise fault.SharedIntegrityError("Prewarm health differs from the exact reviewed disk failure")
    return {"status": "deferred_disk_preparation_failure", "original_health": health,
            "failed_instance": INSTANCE, "original_failure_preserved": True,
            "only_qualified_templates_may_dispatch": True}


def prepared_for_dispatch(instance_id, proof, recovery):
    if proof.get("instance_id") != instance_id:
        raise fault.SharedIntegrityError("CPU template identity differs")
    if proof["status"] == "failed":
        if (instance_id == INSTANCE and proof.get("failure") == recovery["template_failure"]
                and proof.get("reason") == "retained_incomplete_native_preparation"):
            return False
        raise fault.SharedIntegrityError("An unreviewed CPU preparation failed: " + instance_id)
    if proof["status"] not in {"pending", "preparing", "qualified"}:
        raise fault.SharedIntegrityError("Unknown CPU preparation status")
    return proof["status"] == "qualified"


def validate_recovery(recovery_ref, *, initial=False):
    recovery = base.load_ref(recovery_ref)
    if (recovery.get("version") != VERSION or recovery.get("queue_root") != str(base.QUEUE)
            or recovery.get("previous_controller_unit") != PREVIOUS_UNIT
            or recovery.get("disk_policy") != disk.POLICY
            or recovery.get("automatic_generation_replay") is not False
            or recovery.get("model_reload") is not False
            or recovery.get("failed_instance") != INSTANCE):
        raise ValueError("Unknown resource recovery identity")
    if {row["reference"]["path"] for row in recovery["files"]} != {
            str(base.ROOT / TOOL), str(base.ROOT / GUARD)}:
        raise ValueError("Resource recovery source set differs")
    for row in recovery["files"]:
        if initial:
            checked(row["reference"])
        if base.stat_id(row["reference"]["path"]) != row["stat"]:
            raise ValueError("Resource recovery source changed")
    event = base.load_ref(recovery["disk_failure_event"])
    failure = base.load_ref(recovery["template_failure"])
    worker = base.load_ref(recovery["worker_started_event"])
    if (event.get("event") != "failed" or event.get("instance_id") != INSTANCE
            or event.get("error") != {"type": "RuntimeError", "message": DISK_ERROR}
            or event.get("model_calls") != 0 or event.get("formal_claims") != 0
            or failure.get("instance_id") != INSTANCE or failure.get("error") != DISK_ERROR
            or failure.get("error_type") != "RuntimeError" or failure.get("model_calls") != 0
            or failure.get("slot_claimed") is not False or worker.get("event") != "worker_started"
            or event["policy"] != worker["policy"]
            or recovery["allowed_prewarm_failures"] != [recovery["disk_failure_event"], recovery["worker_started_event"]]):
        raise ValueError("Reviewed disk failure provenance changed")
    return recovery


def freeze(output):
    output = Path(output).resolve()
    root = output.parent
    if not root.is_relative_to(base.ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Recovery evidence must stay in the Qwen run root")
    state = base.read(base.QUEUE / "state.json")
    if state["status"] != "paused_technical_unknown" or state.get("source_changed"):
        raise ValueError("Expected the evidenced technical pause, not another state")
    root.mkdir(parents=True, exist_ok=False)
    prior = write_new(root / "state-before-freeze.json", state)
    disk_failure = reference(EVENT_ROOT / "00000299.json")
    worker_started = reference(EVENT_ROOT / "00000001.json")
    mapping = base.load_ref(disk_failure)["baseline_mapping"]
    template_failure = reference(base.ROOT / "runs/software-benchmark-v054/native-lazy-cache"
                                 / INSTANCE / mapping["sha256"][:16] / "preparation-failure.json")
    files = [reference(base.ROOT / value) for value in (TOOL, GUARD)]
    value = {"version": VERSION, "created_utc": base.now(), "queue_root": str(base.QUEUE),
        "evidence_root": str(root), "previous_controller_unit": PREVIOUS_UNIT,
        "original_transition": state["kernel_router"]["transition"],
        "original_bindings": state["bindings"], "state_before_freeze": prior,
        "expected_terminal_fault": state["faults"][-1],
        "disk_failure_event": disk_failure, "worker_started_event": worker_started,
        "template_failure": template_failure, "failed_instance": INSTANCE,
        "allowed_prewarm_failures": [disk_failure, worker_started], "disk_policy": disk.POLICY,
        "files": [{"reference": item, "stat": base.stat_id(item["path"])} for item in files],
        "automatic_generation_replay": False, "model_reload": False,
        "solver_and_scientific_configuration_unchanged": True,
        "shared_dispatch_lock": str(base.ROOT / "runs/software-benchmark-v055/disk-dispatch-r4.lock")}
    failure = value["expected_terminal_fault"]
    if (failure.get("kind") != "controller_fault"
            or failure.get("detail", {}).get("type") != "SharedIntegrityError"
            or not failure["detail"]["message"].startswith("Original CPU preparation failed: ")):
        raise ValueError("Unexpected cause of the last shared pause")
    original_health = json.loads(failure["detail"]["message"].split(": ", 1)[1])
    admitted_prewarm_health(original_health, value)
    result = write_new(output, value)
    validate_recovery(result, initial=True)
    return result


class RecoveryCoordinator(transition.TransitionCoordinator):
    def __init__(self, recovery_ref, *, system=None, adopting=False):
        self.recovery_ref = recovery_ref
        self.recovery = validate_recovery(recovery_ref, initial=True)
        self._manifest_costs = {}
        super().__init__(self.recovery["original_transition"], system=system)
        adopted = self.state.get("resource_recovery")
        if adopted and adopted.get("revision") != recovery_ref:
            self.lease.close()
            raise ValueError("Another recovery revision is already active")
        if not adopting and not adopted:
            self.lease.close()
            raise ValueError("Explicit paused-state recovery adoption is required")

    def validate_state(self):
        super().validate_state()
        validate_recovery(self.recovery_ref)

    def adopt_recovery(self):
        if self.state.get("resource_recovery"):
            raise ValueError("Recovery already adopted; never adopt twice")
        if self.system.active(self.recovery["previous_controller_unit"]):
            raise ValueError("Previous coordinator is still active")
        before = base.load_ref(self.recovery["state_before_freeze"])
        if self.state != before or self.state.get("source_changed"):
            raise ValueError("The reviewed paused state changed before adoption")
        if any(row["generation"]["status"] in base.ACTIVE
               or any(score["status"] in base.ACTIVE for score in row["scores"].values())
               for row in self.state["rows"]):
            raise ValueError("This recovery requires the already-drained old queue")
        for row in self.state["rows"]:
            if row["generation"]["status"] == "pending" and base.claim_path(row["slot"]["slot_id"]).parent.exists():
                raise fault.SharedIntegrityError("Pending slot already has a claim; never replay")
        original_health = prewarm.prewarm_health(self.bindings["prewarm_policy"])
        deferred = admitted_prewarm_health(original_health, self.recovery)
        original_rows, original_faults = deepcopy(self.state["rows"]), deepcopy(self.state["faults"])
        proof = write_new(Path(self.recovery["evidence_root"]) / "adoption.json", {
            "version": VERSION, "utc": base.now(), "revision": self.recovery_ref,
            "state_before": self.recovery["state_before_freeze"], "deferred_preparation": deferred,
            "controller_lock_owned": True, "previous_controller_stopped": True,
            "old_failure_history_preserved": True, "unchanged_original_slots": 1500,
            "model_calls": 0, "GPU_loads": 0, "formal_claims": 0,
            "generation_replayed": False, "running_jobs_signalled": False})
        self.state["resource_recovery"] = {"revision": self.recovery_ref, "adoption": proof}
        self.state.setdefault("explicit_operational_recoveries", []).append(proof)
        self.state["status"] = "running"
        self.state["waiting"] = {"reason": "resource_recovery_adopted_disk_admission_pending", "slot_claimed": False}
        if self.state["rows"] != original_rows or self.state["faults"] != original_faults:
            raise AssertionError("Recovery changed a formal row or previous failure")
        self.save()
        return proof

    def dispatch_generation(self):
        if self.state["status"] != "running":
            return
        from proworksim.software_benchmark_deferred_pool_v054 import healthy_residents
        health = prewarm.prewarm_health(self.bindings["prewarm_policy"])
        self.state["deferred_preparation_health"] = admitted_prewarm_health(health, self.recovery)
        old_pool = healthy_residents(self.bindings["resident_pool_policy"])
        residents = kernel.filtered_old_pool(old_pool)
        new_residents, new_pool = set(), None
        if self.activation is not None:
            new_pool = kernel.bridge(self.router_policy, "healthy", {"bindings": self.activation["new_bindings"]})
            for key, observed in new_pool["available"].items():
                if (observed["declaration"]["gpu_index"] != 6
                        or observed["registration"] != self.activation["qualified_registration"] or key in residents):
                    raise fault.SharedIntegrityError("New pool escaped its qualified GPU6 registration")
                residents[key] = observed
                new_residents.add(key)
        quarantined = self.state.get("quarantined_residents", {})
        residents = {key: value for key, value in residents.items() if key not in quarantined}
        self.state["resident_health"] = {"utc": base.now(), "available": sorted(residents),
            "healthy": sorted((set(old_pool["healthy"]) - {base.load_ref(self.router_policy["old_registration"])["resident_id"]})
                              | (set(new_pool["healthy"]) if new_pool else set())),
            "deferred": old_pool["deferred"] + (new_pool["deferred"] if new_pool else []),
            "quarantined": sorted(quarantined), "old_gpu6_dispatch_disabled": True,
            "kernel_activation": self.activation_ref}
        qualifications = {}

        def is_prepared(row):
            instance = row["slot"]["instance_id"]
            if instance not in qualifications:
                qualifications[instance] = prewarm.preparation_state(instance,
                    mapping_reference=self.public_entries[instance]["baseline_mapping"],
                    cache_root=base.ROOT / "runs/software-benchmark-v054/native-lazy-cache")
            return prepared_for_dispatch(instance, qualifications[instance], self.recovery)

        while self.state["status"] == "running":
            # Both hosts serialize fresh disk/state observations through durable
            # intent + launch. Existing running jobs are fully reserved again.
            with disk.disk_dispatch_lock():
                selected = base.select_pool_slot(self.state["rows"], residents,
                    maximum_active=self.plan["maximum_active_generation_episodes"], is_prepared=is_prepared)
                if selected is None:
                    self.state["waiting"] = {"reason": "no_healthy_prepared_resident_session", "slot_claimed": False,
                        "observed_residents": sorted(residents), "old_gpu6_draining": self.activation is None}
                    return
                row, resident_id, observed = selected
                slot, generation = row["slot"], row["generation"]
                try:
                    other_state = base.read(NEW_QUEUE)
                except (OSError, ValueError, TypeError) as error:
                    self.state["waiting"] = {"reason": "shared_disk_metadata_unavailable", "slot_claimed": False,
                        "error": {"type": type(error).__name__, "message": str(error)}}
                    return
                snapshot = disk.shared_disk_snapshot(v055_state=other_state, v054_state=self.state,
                                                     cache=self._manifest_costs)
                self.state["disk_reservation_status"] = snapshot
                try:
                    estimate = disk.generation_estimate(slot["instance_id"], other_state, self._manifest_costs)
                    gate = disk.admission(snapshot["free_bytes"], snapshot["active_peak_reserved_bytes"],
                                          estimate["peak_bytes"], kind="generation")
                except (OSError, ValueError, KeyError, TypeError) as error:
                    estimate = None
                    gate = {"admitted": False, "metadata_error": {"type": type(error).__name__, "message": str(error)}}
                if snapshot["metadata_error"]:
                    gate.update(admitted=False, shared_observation_error=snapshot["metadata_error"])
                gate.update(instance_id=slot["instance_id"], observed_utc=base.now(), estimate=estimate)
                self.state["last_disk_dispatch_admission"] = gate
                if not gate["admitted"]:
                    self.state["waiting"] = {"reason": "shared_disk_peak_reservation_gate", "slot_claimed": False}
                    return
                if base.claim_path(slot["slot_id"]).parent.exists():
                    raise fault.SharedIntegrityError("Pending slot already has a claim; never replay")
                root = self.root / "slots" / str(slot["slot_index"]) / ("preclaim-" + str(len(generation["attempts"]) + 1))
                root.mkdir(parents=True, exist_ok=False)
                new = resident_id in new_residents
                bindings = base.load_ref(self.activation["new_bindings"]) if new else self.bindings
                if new:
                    prepared = kernel.bridge(self.router_policy, "prepare", {"bindings": self.activation["new_bindings"],
                        "slot": slot, "observed": observed, "root": str(root)})
                    service_ref, config = prepared["service"], prepared["config"]
                    row["original_execution_bindings"] = self.activation["new_bindings"]
                    row["kernel_runtime_revision"] = self.activation_ref
                    row.pop("next_execution_bindings", None)
                    generation["kernel_execution_bindings"] = self.activation["new_bindings"]
                    newroot = Path(self.router_policy["new_source_root"])
                    argv = ["/usr/bin/env", "PYTHONPATH=" + str(newroot / "src") + os.pathsep + str(newroot),
                            str(base.HOST_PYTHON), str(newroot / "tools/run_benchmark_episode_v054.py")]
                else:
                    from proworksim.software_benchmark_service_factory_v054 import build_service
                    from proworksim.software_benchmark_slot_factory_v054 import build_slot_config
                    base.validate_frozen(bindings)
                    declaration = observed["declaration"]
                    service_ref = build_service(arm=slot["arm"],
                        capacity_reference=bindings["capacities"]["REF" if slot["arm"] == "REF" else "MATCH"],
                        card={"index": declaration["gpu_index"], "uuid": declaration["gpu_uuid"],
                              "admission": "immutable_pool_registration_and_live_resident"}, directory=root / "service",
                        resident_reference=observed["declaration_reference"], registration_reference=observed["registration"],
                        pool_policy_reference=bindings["resident_pool_policy"])
                    config = build_slot_config(slot_id=slot["slot_id"], condition_reference=bindings["conditions"][slot["arm"]],
                        model_service=base.load_ref(service_ref), registry_reference=bindings["registry"],
                        scorer_manifest_reference=bindings["scorer_manifest"], output=root / "config.json",
                        authorization=bindings["authorization"], prewarm_policy_reference=bindings["prewarm_policy"])
                    argv = [str(base.HOST_PYTHON), str(base.ROOT / "tools/run_benchmark_episode_v054.py")]
                generation.update(config=config, service=service_ref, episode_output=str(root / "episode"), claimed=False,
                    slot_id=slot["slot_id"], slot_index=slot["slot_index"], physical_gpu=observed["declaration"]["gpu_index"],
                    resident_id=resident_id, resident_registration=observed["registration"],
                    resident_pool_policy=bindings["resident_pool_policy"],
                    disk_reservation={"host_revision": self.recovery_ref, **gate})
                row["resource_host_revision"] = self.recovery_ref
                self.state.pop("waiting", None)
                with self.context(row):
                    self.start_job(generation, kind="generation", directory=root / "worker",
                        argv=argv + ["--config", config["path"], "--output", str(root / "episode")])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    command = commands.add_parser("freeze")
    command.add_argument("--output", type=Path, required=True)
    for name in ("adopt", "run"):
        command = commands.add_parser(name)
        command.add_argument("--revision", type=Path, required=True)
        command.add_argument("--sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.operation == "freeze":
        print(json.dumps(freeze(args.output)))
        return 0
    ref = reference(args.revision)
    if ref["sha256"] != args.sha256:
        raise ValueError("Resource recovery seal SHA mismatch")
    coordinator = RecoveryCoordinator(ref, adopting=args.operation == "adopt")
    try:
        if args.operation == "adopt":
            print(json.dumps(coordinator.adopt_recovery()))
            return 0
        return coordinator.run()
    finally:
        coordinator.lease.close()


if __name__ == "__main__":
    raise SystemExit(main())
