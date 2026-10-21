"""GPU6-only kernel revision routing over the unchanged deferred-fault queue.

Old workers and shared claims/scoring remain in the original queue. Activation
is an immutable later record, so GPU6 can drain while GPU3/REF7 keep dispatching.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from . import software_benchmark_queue_v054 as base
from . import software_benchmark_fault_queue_v054 as fault
from .software_benchmark_candidates_v054 import checked, reference, write_new

VERSION = "v054-single-gpu-kernel-router-r1"
ACTIVATION_VERSION = "v054-single-gpu-kernel-activation-r1"
FILES = ("src/proworksim/software_benchmark_kernel_queue_v054.py",
         "tools/run_kernel_queue_v054.py", "tools/kernel_queue_bridge_v054.py")
COMMON = ("version", "execution_authorized", "authorization", "plan", "slots", "registry",
          "scorer_manifest", "capacities", "capacity_admission", "prewarm_policy",
          "residency_protocol", "model_loads", "slot_claims", "automatic_start")


def validate_policy(policy_ref, initial=False):
    policy = base.load_ref(policy_ref)
    if (policy.get("version") != VERSION or policy.get("gpu_index") != 6
            or policy.get("automatic_generation_retry") is not False
            or policy.get("old_queue_bindings_preserved") is not True
            or policy.get("original_deferred_policy") is None
            or policy.get("queue_root") != str(base.QUEUE)):
        raise ValueError("Unsupported GPU6 kernel router policy")
    old_policy = fault.validate_policy(policy["original_deferred_policy"], initial=initial)
    if old_policy["original_bindings"] != policy["original_bindings"]:
        raise ValueError("Original deferred policy binding changed")
    old_bindings = base.load_ref(policy["original_bindings"])
    registration = base.load_ref(policy["old_registration"])
    if (registration["gpu_index"] != 6 or registration["mode"] != "MATCH_PROJECT"
            or registration["pool_policy"] != old_bindings["resident_pool_policy"]):
        raise ValueError("GPU6 drain registration differs")
    if {item["reference"]["path"] for item in policy["files"]} != {str(base.ROOT / x) for x in FILES}:
        raise ValueError("Kernel router source set differs")
    for item in policy["files"]:
        if initial:
            checked(item["reference"])
        if base.stat_id(item["reference"]["path"]) != item["stat"]:
            raise ValueError("Kernel host router source changed")
    source_root = Path(policy["new_source_root"])
    activation = Path(policy["activation_path"])
    if (not source_root.is_absolute() or not source_root.is_relative_to(base.ROOT / "runs/software-benchmark-v054")
            or not activation.is_absolute() or not activation.is_relative_to(base.ROOT / "runs/software-benchmark-v054")):
        raise ValueError("Kernel revision/activation must be inside benchmark runs")
    assembly = base.load_ref(policy["bridge_assembly"])
    bridge_path = source_root / "tools/kernel_queue_bridge_v054.py"
    reviewed = next(item["reference"] for item in policy["files"]
                    if Path(item["reference"]["path"]).name == "kernel_queue_bridge_v054.py")
    records = [item for item in assembly["files"] if item["copied"]["path"] == str(bridge_path)]
    if (assembly.get("version") != "v054-kernel-source-root-r1"
            or assembly.get("source_root") != str(source_root)
            or assembly.get("shared_data_root") != str(base.ROOT)
            or assembly.get("old_sources_modified") is not False
            or len(records) != 1 or records[0]["copied"] != policy["assembled_bridge"]
            or any(records[0]["original"][key] != reviewed[key] for key in ("sha256", "bytes"))):
        raise ValueError("Assembled bridge provenance differs from reviewed canonical source")
    if initial:
        checked(policy["assembled_bridge"])
    if base.stat_id(bridge_path) != policy["assembled_bridge_stat"]:
        raise ValueError("Assembled bridge changed")
    return policy


def create_policy(*, deferred_policy, old_registration, new_source_root, activation_path,
                  previous_controller_unit, output):
    previous = fault.validate_policy(reference(deferred_policy), initial=True)
    if not re.fullmatch(r"proworksim-v054-[a-z0-9-]+\.service", previous_controller_unit):
        raise ValueError("Unexpected controller unit")
    refs = [reference(base.ROOT / name) for name in FILES]
    value = {"version": VERSION, "created_utc": base.now(), "gpu_index": 6,
             "original_deferred_policy": reference(deferred_policy),
             "original_bindings": previous["original_bindings"],
             "old_registration": reference(old_registration),
             "new_source_root": str(Path(new_source_root).resolve()),
             "activation_path": str(Path(activation_path).resolve()),
             "bridge_assembly": reference(Path(new_source_root).resolve() / "assembly.json"),
             "assembled_bridge": reference(Path(new_source_root).resolve() / "tools/kernel_queue_bridge_v054.py"),
             "assembled_bridge_stat": base.stat_id(Path(new_source_root).resolve() / "tools/kernel_queue_bridge_v054.py"),
             "previous_controller_unit": previous_controller_unit, "queue_root": str(base.QUEUE),
             "files": [{"reference": item, "stat": base.stat_id(item["path"])} for item in refs],
             "automatic_generation_retry": False, "old_queue_bindings_preserved": True,
             "other_residents_drained": False, "activation_requires_qualified_registration": True,
             "mixed_revision_results_reported_separately": True}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    result = write_new(output, value)
    validate_policy(result, initial=True)
    return result


def bridge(policy, command, body):
    root = Path(policy["new_source_root"])
    script = root / "tools/kernel_queue_bridge_v054.py"
    if reference(script) != policy["assembled_bridge"]:
        raise ValueError("Kernel bridge differs from its reviewed assembled revision")
    with tempfile.TemporaryDirectory(prefix="v054-kernel-router-", dir="/tmp") as temporary:
        path = Path(temporary) / "request.json"
        path.write_text(json.dumps(body))
        env = {**os.environ, "PYTHONPATH": str(root / "src") + os.pathsep + str(root),
               "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
               "TRANSFORMERS_OFFLINE": "1"}
        result = subprocess.run([str(base.HOST_PYTHON), str(script), command, "--request", str(path)],
                                cwd=root, env=env, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise ValueError("Kernel bridge " + command + " failed: " + result.stderr[-4000:])
        return json.loads(result.stdout)


def validate_activation(policy, activation_ref, initial=False):
    activation = base.load_ref(activation_ref)
    if (activation.get("version") != ACTIVATION_VERSION
            or activation.get("original_bindings") != policy["original_bindings"]
            or activation.get("new_source_root") != policy["new_source_root"]
            or activation.get("old_registration") != policy["old_registration"]
            or activation.get("gpu_index") != 6 or activation.get("model_generation_replayed") is not False):
        raise ValueError("Kernel activation identity changed")
    new = base.load_ref(activation["new_bindings"])
    old = base.load_ref(policy["original_bindings"])
    base.validate_frozen(new, initial=initial)
    if any(new.get(key) != old.get(key) for key in COMMON):
        raise ValueError("Kernel activation changed common task/seed/scorer/resource identities")
    registration = base.load_ref(activation["qualified_registration"])
    previous = base.load_ref(policy["old_registration"])
    if (registration["gpu_index"] != 6 or registration["gpu_uuid"] != previous["gpu_uuid"]
            or registration["mode"] != "MATCH_PROJECT" or registration["resident_id"] == previous["resident_id"]
            or registration["pool_policy"] != new["resident_pool_policy"]):
        raise ValueError("Kernel activation registration is not the qualified replacement GPU6")
    if initial:
        observed = bridge(policy, "validate", {"bindings": activation["new_bindings"],
                          "original_bindings": policy["original_bindings"], "initial": True})
        if observed.get("common_identities_unchanged") is not True:
            raise ValueError("Kernel condition validation did not pass")
    return activation


def create_activation(policy_ref, new_bindings, qualified_registration):
    policy = validate_policy(policy_ref, initial=True)
    activation = {"version": ACTIVATION_VERSION, "utc": base.now(), "router_policy": policy_ref,
                  "original_bindings": policy["original_bindings"], "new_bindings": reference(new_bindings),
                  "new_source_root": policy["new_source_root"], "gpu_index": 6,
                  "old_registration": policy["old_registration"],
                  "qualified_registration": reference(qualified_registration),
                  "model_generation_replayed": False, "runtime_revision": "kernel-g6-r1"}
    # Validate the full candidate before making the single visible activation.
    with tempfile.TemporaryDirectory(prefix="v054-kernel-activation-", dir="/tmp") as directory:
        candidate = write_new(Path(directory) / "candidate.json", activation)
        validate_activation(policy, candidate, initial=True)
        observed = bridge(policy, "healthy", {"bindings": activation["new_bindings"]})
        registration = base.load_ref(activation["qualified_registration"])
        resident = observed["healthy"].get(registration["resident_id"])
        if resident is None or resident["registration"] != activation["qualified_registration"]:
            raise ValueError("Qualified replacement is not live/healthy")
    path = Path(policy["activation_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_new(path, activation)


def filtered_old_pool(observed):
    return {key: value for key, value in observed["available"].items()
            if value["declaration"]["gpu_index"] != 6}


class KernelCoordinator(fault.ResilientCoordinator):
    def __init__(self, router_policy_ref, *, system=None, adopting=False):
        self.router_policy_ref = router_policy_ref
        self.router_policy = validate_policy(router_policy_ref, initial=True)
        self.activation_ref = None
        self.activation = None
        super().__init__(self.router_policy["original_deferred_policy"], system=system)
        adopted = self.state.get("kernel_router")
        if adopted and adopted.get("policy") != router_policy_ref:
            self.lease.close()
            raise ValueError("A different kernel router is already adopted")
        if not adopting and not adopted:
            self.lease.close()
            raise ValueError("Explicit stopped-controller kernel adoption is required")

    def validate_state(self):
        super().validate_state()
        validate_policy(self.router_policy_ref)
        path = Path(self.router_policy["activation_path"])
        if path.exists():
            current = reference(path)
            if self.activation_ref is not None and self.activation_ref != current:
                raise ValueError("Immutable kernel activation was replaced")
            self.activation = validate_activation(self.router_policy, current, initial=self.activation_ref is None)
            if self.activation.get("router_policy") != self.router_policy_ref:
                raise ValueError("Kernel activation belongs to another router policy")
            self.activation_ref = current
        elif self.activation_ref is not None:
            raise ValueError("Kernel activation disappeared")
        for row in self.state["rows"]:
            if row.get("kernel_runtime_revision"):
                if (self.activation is None or row["original_execution_bindings"] != self.activation["new_bindings"]
                        or row["kernel_runtime_revision"] != self.activation_ref
                        or row["slot"]["arm"] not in {"MATCH", "PROJECT"}
                        or row["generation"].get("physical_gpu") != 6):
                    raise ValueError("Kernel row execution provenance changed")

    def adopt_router(self):
        if self.state.get("kernel_router"):
            raise ValueError("Kernel router was already adopted")
        if self.system.active(self.router_policy["previous_controller_unit"]):
            raise ValueError("Only the previous coordinator must be stopped before adoption")
        active = []
        for row in self.state["rows"]:
            for endpoint, record in [(None, row["generation"]), *row["scores"].items()]:
                if record["status"] not in base.ACTIVE:
                    continue
                job = base.load_ref(record["job"])
                expected = "generation" if endpoint is None else "score"
                if (job["bindings"] != self.bindings_ref or job["kind"] != expected
                        or job["unit"] != record["unit"]
                        or Path(record["job"]["path"]) != Path(record["worker_directory"]) / "job.json"):
                    raise ValueError("Existing worker is not an unchanged original intent")
                active.append({"slot_id": row["slot"]["slot_id"], "endpoint": endpoint,
                               "job": record["job"], "unit": record["unit"]})
        root = self.root / "kernel-router-r1"
        root.mkdir(parents=True, exist_ok=False)
        snapshot = write_new(root / "state-before-adoption.json", self.state)
        proof = write_new(root / "adoption.json", {"version": VERSION, "utc": base.now(),
            "policy": self.router_policy_ref, "state_before": snapshot, "inherited_workers": active,
            "prior_controller_stopped": True, "controller_lock_owned": True,
            "model_reloads": 0, "formal_claims": 0, "running_jobs_changed": False})
        self.state["kernel_router"] = {"version": VERSION, "policy": self.router_policy_ref,
                                      "adoption": proof, "gpu6_original_dispatch_disabled": True}
        self.state.setdefault("operator_policy_adoptions", []).append(proof)
        self.save()
        return proof

    def start_job(self, record, *, kind, directory, argv):
        new_ref = record.get("kernel_execution_bindings") if kind == "generation" else None
        if new_ref is None:
            return super().start_job(record, kind=kind, directory=directory, argv=argv)
        if self.activation is None or new_ref != self.activation["new_bindings"]:
            raise ValueError("Kernel dispatch does not bind the activated execution revision")
        directory.mkdir(parents=True, exist_ok=False)
        unit = "proworksim-v054-generation-" + hashlib.sha256(str(directory).encode()).hexdigest()[:24] + ".service"
        job = write_new(directory / "job.json", {"kind": kind, "argv": argv, "unit": unit,
                        "bindings": new_ref, "created_utc": base.now(), "kernel_activation": self.activation_ref})
        record.update(status="intent", unit=unit, job=job, worker_directory=str(directory))
        events = self.state.setdefault("generation_dispatches", [])
        events.append({"dispatch_ordinal": len(events) + 1, "intent_utc": base.now(), "job": job,
            "slot_id": record["slot_id"], "slot_index": record["slot_index"],
            "physical_gpu": record["physical_gpu"], "resident_id": record["resident_id"],
            "registration": record["resident_registration"], "pool_policy": record["resident_pool_policy"],
            "worker_started": None, "claim": None, "kernel_activation": self.activation_ref,
            "execution_bindings": new_ref})
        self.save()
        response = self.system.launch(unit, job)
        base.atomic(directory / "launch.json", {"returncode": response.returncode,
                    "stdout": response.stdout, "stderr": response.stderr, "utc": base.now()})
        if response.returncode != 0:
            self.pause("ambiguous_unit_launch", {"unit": unit, "returncode": response.returncode})
            return
        record["status"] = "running"
        self.save()

    def complete_generation(self, row, completion):
        super().complete_generation(row, completion)
        generation = row["generation"]
        if (generation["status"] == "pending" and row.get("kernel_runtime_revision")
                and generation["attempts"][-1]["outcome"] == "resource_wait"):
            # Only a validated zero-call, unclaimed resource wait may return to
            # either pool. Retain its attempted revision in immutable job history.
            row.setdefault("kernel_preclaim_waits", []).append({
                "activation": row.pop("kernel_runtime_revision"),
                "bindings": row.pop("original_execution_bindings"),
                "job": generation["job"]})
            generation.pop("kernel_execution_bindings", None)
            row["next_execution_bindings"] = self.bindings_ref

    def dispatch_generation(self):
        if self.state["status"] != "running":
            return
        from .software_benchmark_deferred_pool_v054 import healthy_residents
        from .software_benchmark_prewarm_v054 import preparation_state, prewarm_health
        health = prewarm_health(self.bindings["prewarm_policy"])
        if health["status"] == "failed":
            raise fault.SharedIntegrityError("Original CPU preparation failed: " + json.dumps(health))
        old_pool = healthy_residents(self.bindings["resident_pool_policy"])
        residents = filtered_old_pool(old_pool)
        new_residents = set()
        new_pool = None
        if self.activation is not None:
            new_pool = bridge(self.router_policy, "healthy", {"bindings": self.activation["new_bindings"]})
            for key, observed in new_pool["available"].items():
                if (observed["declaration"]["gpu_index"] != 6
                        or observed["registration"] != self.activation["qualified_registration"] or key in residents):
                    raise ValueError("New pool escaped its unique qualified GPU6 registration")
                residents[key] = observed
                new_residents.add(key)
        quarantined = self.state.get("quarantined_residents", {})
        residents = {key: value for key, value in residents.items() if key not in quarantined}
        self.state["resident_health"] = {"utc": base.now(), "available": sorted(residents),
            "healthy": sorted(set(old_pool["healthy"]) - {base.load_ref(self.router_policy["old_registration"])["resident_id"]}
                              | (set(new_pool["healthy"]) if new_pool else set())),
            "deferred": old_pool["deferred"] + (new_pool["deferred"] if new_pool else []),
            "quarantined": sorted(quarantined), "old_gpu6_dispatch_disabled": True,
            "kernel_activation": self.activation_ref}
        qualifications = {}

        def is_prepared(row):
            instance = row["slot"]["instance_id"]
            if instance not in qualifications:
                qualifications[instance] = preparation_state(instance,
                    mapping_reference=self.public_entries[instance]["baseline_mapping"],
                    cache_root=base.ROOT / "runs/software-benchmark-v054/native-lazy-cache")
            proof = qualifications[instance]
            if proof["status"] == "failed":
                raise fault.SharedIntegrityError("Fixed CPU preparation failed: " + instance)
            return proof["status"] == "qualified"

        while self.state["status"] == "running":
            selected = base.select_pool_slot(self.state["rows"], residents,
                maximum_active=self.plan["maximum_active_generation_episodes"], is_prepared=is_prepared)
            if selected is None:
                self.state["waiting"] = {"reason": "no_healthy_prepared_resident_session", "slot_claimed": False,
                                         "observed_residents": sorted(residents), "old_gpu6_draining": self.activation is None}
                return
            row, resident_id, observed = selected
            slot, generation = row["slot"], row["generation"]
            if base.claim_path(slot["slot_id"]).parent.exists():
                raise fault.SharedIntegrityError("Pending slot already has a claim; never replay")
            root = self.root / "slots" / str(slot["slot_index"]) / ("preclaim-" + str(len(generation["attempts"]) + 1))
            root.mkdir(parents=True, exist_ok=False)
            new = resident_id in new_residents
            bindings = base.load_ref(self.activation["new_bindings"]) if new else self.bindings
            if new:
                prepared = bridge(self.router_policy, "prepare", {"bindings": self.activation["new_bindings"],
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
                from .software_benchmark_service_factory_v054 import build_service
                from .software_benchmark_slot_factory_v054 import build_slot_config
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
                resident_pool_policy=bindings["resident_pool_policy"])
            self.state.pop("waiting", None)
            with self.context(row):
                self.start_job(generation, kind="generation", directory=root / "worker",
                               argv=argv + ["--config", config["path"], "--output", str(root / "episode")])


def drain_original_gpu6(policy_ref, output, *, stop=False):
    policy = validate_policy(policy_ref, initial=True)
    registration = base.load_ref(policy["old_registration"])
    declaration = base.load_ref(registration["declaration"])

    def state_check():
        state = base.read(base.QUEUE / "state.json")
        if (state.get("kernel_router", {}).get("policy") != policy_ref
                or state["bindings"] != policy["original_bindings"] or state["status"] != "running"):
            raise ValueError("Live queue is not the adopted original GPU6-draining router")
        active = [r["slot"]["slot_id"] for r in state["rows"]
                  if r["generation"]["status"] in base.ACTIVE and r["generation"].get("physical_gpu") == 6]
        return state, active

    state, active = state_check()
    if active:
        return {"status": "waiting_for_original_gpu6_episodes", "active_slots": active, "services_modified": False}
    from .software_benchmark_deferred_pool_v054 import healthy_residents
    observed = healthy_residents(registration["pool_policy"])["healthy"].get(registration["resident_id"])
    if (observed is None or observed["registration"] != policy["old_registration"]
            or observed["active_claims"] or observed["status"].get("inflight") is not None):
        raise ValueError("Original GPU6 is not healthy, empty and ready to stop")
    state, active = state_check()
    if active:
        raise ValueError("GPU6 became active while checking drain")
    path = Path(output)
    path.mkdir(parents=True, exist_ok=False)
    intent = write_new(path / "drain-proof.json", {"version": VERSION, "utc": base.now(), "policy": policy_ref,
        "old_registration": policy["old_registration"], "unit": declaration["unit"],
        "active_gpu6_slots": [], "resident_status": observed["status"], "stop_requested": stop,
        "state_snapshot": write_new(path / "state-before-stop.json", state), "other_residents_modified": False})
    if stop:
        result = subprocess.run(["systemctl", "--user", "stop", declaration["unit"]],
                                capture_output=True, text=True, timeout=30)
        receipt = write_new(path / "stop.json", {"proof": intent, "utc": base.now(), "returncode": result.returncode,
                                               "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            raise ValueError("Original GPU6 stop failed; inspect " + receipt["path"])
        return {"status": "original_gpu6_stopped", "proof": intent, "receipt": receipt}
    return {"status": "original_gpu6_drained", "proof": intent}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    for key in ("deferred-policy", "old-registration", "new-source-root", "activation-path", "output"):
        freeze.add_argument("--" + key, required=True, type=Path)
    freeze.add_argument("--previous-controller-unit", required=True)
    for name in ("adopt", "run", "activate", "drain"):
        command = sub.add_parser(name)
        command.add_argument("--policy", required=True, type=Path)
        command.add_argument("--policy-sha256", required=True)
        if name == "activate":
            command.add_argument("--new-bindings", required=True, type=Path)
            command.add_argument("--qualified-registration", required=True, type=Path)
        if name == "drain":
            command.add_argument("--output", required=True, type=Path)
            command.add_argument("--stop", action="store_true")
    args = parser.parse_args(argv)
    os.umask(0o077)
    if args.command == "freeze":
        options = vars(args).copy()
        options.pop("command")
        print(json.dumps(create_policy(**options)))
        return 0
    policy_ref = reference(args.policy)
    if policy_ref["sha256"] != args.policy_sha256:
        raise ValueError("Router policy differs")
    if args.command == "activate":
        print(json.dumps(create_activation(policy_ref, args.new_bindings, args.qualified_registration)))
        return 0
    if args.command == "drain":
        result = drain_original_gpu6(policy_ref, args.output, stop=args.stop)
        print(json.dumps(result))
        return 75 if result["status"].startswith("waiting_") else 0
    coordinator = KernelCoordinator(policy_ref, adopting=args.command == "adopt")
    try:
        if args.command == "adopt":
            print(json.dumps(coordinator.adopt_router()))
            return 0
        return coordinator.run()
    finally:
        coordinator.lease.close()


if __name__ == "__main__":
    raise SystemExit(main())
