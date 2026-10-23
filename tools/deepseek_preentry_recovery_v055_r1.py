"""Finite independent namespace for six proven zero-model astropy slots.

Preparation and --preflight are read-only with respect to the old experiment.
The run operation must be separately invoked after review; it cannot replay a
slot whose original or recovery namespace has entered execution.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/software-benchmark-v055"
RECOVERY = RUN / "pre-entry-recovery-r1"
PLAN = RECOVERY / "plan.json"
AUDIT = ROOT / "artifacts/software-benchmark-v055/exception-reconciliation-r1/deepseek-generation-audit.json"
SOURCE_FILES = (
    "tools/deepseek_preentry_recovery_v055_r1.py",
    "tools/native_uid_clone_preentry_v055_r1.py",
    "tools/native_uid_bootstrap_v055.py",
    "tools/run_deepseek_episode_v055_r4.py",
    "src/proworksim/software_benchmark_runner_v055.py",
    "src/proworksim/software_benchmark_rootfs_v055.py",
)
EXPECTED_INSTANCE = "astropy__astropy-12907"


def reference(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def checked(item):
    path = Path(item["path"])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != item["sha256"]:
        raise ValueError("Frozen recovery input changed: " + str(path))
    return json.loads(raw)


def write_new(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def validate_scope(plan):
    if plan["recovery_root"] != str(RECOVERY) or plan["maximum_recovery_slots"] != 6:
        raise ValueError("Recovery namespace or finite bound differs")
    rows = plan["slots"]
    if len(rows) != 6 or len({row["slot_id"] for row in rows}) != 6:
        raise ValueError("Only six distinct original slots are admitted")
    conditions = {f"{arm}-{thinking}" for arm in ("REF", "MATCH", "PROJECT")
                  for thinking in ("thinking", "nonthinking")}
    if {row["condition_id"] for row in rows} != conditions:
        raise ValueError("Recovery six-condition identity differs")
    for row in rows:
        if row["instance_id"] != EXPECTED_INSTANCE or row["slot_id"] != "v055-" + row["condition_id"] + "-" + EXPECTED_INSTANCE:
            raise ValueError("Recovery includes an unrelated slot")
        expected = RECOVERY / "workers" / hashlib.sha256(row["slot_id"].encode()).hexdigest()[:24]
        if row["output_directory"] != str(expected / "episode"):
            raise ValueError("Recovery output is not the fixed new slot directory")


def load_plan(sha):
    plan = checked({"path": str(PLAN), "sha256": sha})
    validate_scope(plan)
    for item in plan["sources"]:
        path = Path(item["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Recovery source changed: " + str(path))
    return plan


def prepare():
    audit = json.loads(AUDIT.read_bytes())
    rows = [row for row in audit["rows"] if row["category"] == "pre_entry_clone_manifest_prefix_rejected"]
    if len(rows) != 6 or any(not row["zero_model_pre_entry_evidence"]["historical_pre_entry_boundary_supported"] for row in rows):
        raise ValueError("Six exact historical pre-entry proofs required")
    slots = []
    for row in rows:
        proof = row["zero_model_pre_entry_evidence"]
        sid = row["slot_id"]
        slots.append({"slot_id": sid, "condition_id": row["condition_id"], "instance_id": row["instance_id"],
            "slot_index": checked(proof["job_reference"])["slot"]["slot_index"],
            "seed": row["original_seed"], "config": proof["frozen_config_reference"],
            "original_job": proof["job_reference"], "original_result": row["result_reference"],
            "original_completion": row["completion_reference"], "original_claim": row["claim_reference"],
            "original_claim_state": row["claim_state_reference"], "original_routing_result": proof["routing_result_reference"],
            "original_directory": row["directory"],
            "output_directory": str(RECOVERY / "workers" / hashlib.sha256(sid.encode()).hexdigest()[:24] / "episode")})
    slots.sort(key=lambda row: row["slot_index"])
    template_paths = rows[0]["zero_model_pre_entry_evidence"]["native_preparation_paths"]
    public_path = Path(template_paths["rootfs_environment"])
    public = json.loads(public_path.read_bytes())
    manifest_ref = reference(Path(public["rootfs_manifest"]))
    if manifest_ref["sha256"] != public["rootfs_manifest_sha256"]:
        raise ValueError("Qualified public template manifest identity differs")
    manifest = checked(manifest_ref)
    qualification_path = Path(template_paths["qualification"])
    qualification = json.loads(qualification_path.read_bytes())
    if qualification.get("passed") is not True or qualification["instance_id"] != EXPECTED_INSTANCE:
        raise ValueError("Original template initialization is not qualified")
    source = Path(manifest["prepared_root"]).resolve(strict=True)
    plan = {"version": "v055-six-zero-model-pre-entry-recovery-r1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "recovery_root": str(RECOVERY), "maximum_recovery_slots": 6, "maximum_parallel_recovery_workers": 6,
        "parallelism_note": "All six full peaks admitted once under original shared dispatch lock, only after both original generation inventories are terminal; per-worker observations do not replace this aggregate admission.",
        "original_unknowns_and_claims_retained": True, "original_model_config_and_seed_preserved": True,
        "shared_ledger": str(RUN / "budget-r1/ledger.sqlite3"), "budget_cap_cny": 2000,
        "maximum_API_concurrency_unchanged": 64, "audit": reference(AUDIT),
        "sources": [reference(ROOT / path) for path in SOURCE_FILES], "slots": slots,
        "original_budget_r4_activation": checked(slots[0]["config"])["solver_activation"],
        "template": {"public_environment": reference(public_path), "manifest": manifest_ref,
            "prepared_root": str(source), "device": source.stat().st_dev,
            "qualification": reference(qualification_path), "baseline_mapping": qualification["baseline_mapping"],
            "image_id": public["image_id"]},
        "resource_admission": {"minimum_available_memory_bytes": 320 * 1024**3,
            "minimum_primary_free_after_requested_peak_bytes": 256 * 1024**3,
            "maximum_load_1m": 120, "one_recovery_worker_cpu": 4, "one_recovery_worker_memory_bytes": 16 * 1024**3},
        "execution_started": False, "candidate_or_score_reselection_allowed": False}
    validate_scope(plan)
    RECOVERY.mkdir(parents=True, exist_ok=True)
    write_new(PLAN, plan)
    print(json.dumps(reference(PLAN)))


def old_unit_quiet(unit):
    p = subprocess.run(["systemctl", "--user", "show", unit, "-p", "Id", "-p", "MainPID",
        "-p", "ActiveState", "-p", "SubState", "-p", "ControlGroup"],
        check=True, capture_output=True, text=True, timeout=15)
    value = dict(line.split("=", 1) for line in p.stdout.splitlines() if "=" in line)
    if value.get("MainPID") != "0" or value.get("ActiveState") not in ("inactive", "failed"):
        raise ValueError("Original worker has not exited")
    group = value.get("ControlGroup")
    if group:
        events = Path("/sys/fs/cgroup") / group.lstrip("/") / "cgroup.events"
        if events.exists() and "populated 1" in events.read_text():
            raise ValueError("Original worker cgroup still populated")
    return value


def assert_preentry(result, claim_state, routing, api_count):
    if (result.get("entered") is not False or claim_state.get("phase") != "claimed"
            or claim_state.get("entered") is not False or claim_state.get("started") is not None
            or api_count != 0 or routing.get("actual_controller_routing_count") != 0
            or result.get("finally_stopped_scopes") != []):
        raise ValueError("Original slot is not a proven zero-model pre-entry failure")


def full_clone_peak(manifest):
    logical = manifest["regular_file_bytes"]
    if type(logical) is not int or logical < 0:
        raise ValueError("Manifest regular_file_bytes is absent or invalid")
    return 2 * (logical + len(manifest["entries"]) * 8192) + 8 * 1024**3


def preflight(plan, slot):
    result, state = checked(slot["original_result"]), checked(slot["original_claim_state"])
    job, done = checked(slot["original_job"]), checked(slot["original_completion"])
    claim, routing = checked(slot["original_claim"]), checked(slot["original_routing_result"])
    config = checked(slot["config"])
    if (job["slot"] != claim["slot"] or done["job"] != slot["original_job"]
            or config["seed"] != slot["seed"] or config["slot_id"] != slot["slot_id"]
            or config["condition_id"] != slot["condition_id"]):
        raise ValueError("Original slot/config/claim bindings changed")
    claim_root = Path(slot["original_claim"]["path"]).parent
    if any((claim_root / name).exists() for name in ("entered.json", "scope-registry.json", "candidate-result.json")):
        raise ValueError("Original claim now has execution artifacts")
    with sqlite3.connect(Path(plan["shared_ledger"]).as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        count = db.execute("SELECT COUNT(*) FROM requests WHERE slot_id=?", (slot["slot_id"],)).fetchone()[0]
        policy = json.loads(db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0])
        halted = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
    if halted or policy["cap_nanoyuan"] != 2000 * 10**9 or not policy["version"].endswith("-r4"):
        raise ValueError("Shared financial policy is halted or differs")
    assert_preentry(result, state, routing, count)
    unit = old_unit_quiet(job["unit"])
    qwen = json.loads((ROOT / "runs/software-benchmark-v054/formal-queue-r1/state.json").read_bytes())
    deep = json.loads((RUN / "queue-r1/state.json").read_bytes())
    original = next(row for row in deep["rows"] if row["slot"]["slot_id"] == slot["slot_id"])
    if original["generation"]["status"] != "technical_unknown" or original["generation"]["job"] != slot["original_job"]:
        raise ValueError("Original primary inventory row changed")
    if any(row["generation"]["status"] in ("running", "intent") for row in deep["rows"]):
        raise ValueError("Original DeepSeek queue is executing; recovery remains deferred")
    disk = qwen.get("disk_reservation_status", {})
    if disk.get("metadata_error"):
        raise ValueError("Existing Qwen disk reservations are not trustworthy")
    manifest = checked(plan["template"]["manifest"])
    requested = full_clone_peak(manifest)
    stat = os.statvfs(ROOT)
    available = stat.f_bavail * stat.f_frsize
    old_reserved = disk.get("volumes", {}).get("primary", {}).get("active_peak_reserved_bytes")
    if not isinstance(old_reserved, int):
        raise ValueError("Existing primary reservation amount absent")
    gate = plan["resource_admission"]
    memory = {key: int(value.split()[0]) * 1024 for key, value in
              (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())}
    if (available - old_reserved - requested < gate["minimum_primary_free_after_requested_peak_bytes"]
            or memory["MemAvailable"] < gate["minimum_available_memory_bytes"]
            or os.getloadavg()[0] > gate["maximum_load_1m"]):
        raise ValueError("Independent single-worker resource margin unavailable")
    return {"observed_utc": datetime.now(timezone.utc).isoformat(), "original_unit": unit,
        "API_requests_for_original_slot": count, "original_claim_still_preentry": True,
        "primary_available_bytes": available, "old_qwen_peak_reserved_bytes": old_reserved,
        "requested_full_two_clone_peak_bytes": requested,
        "remaining_after_both_reservations_bytes": available - old_reserved - requested,
        "memory_available_bytes": memory["MemAvailable"], "load_1m": os.getloadavg()[0],
        "recovery_workers_maximum": 6, "original_config": slot["config"]}


def admit_batch(plan, sha):
    from proworksim.software_benchmark_budget_runtime_v055_r4 import validate_activation
    validate_activation(plan["original_budget_r4_activation"])
    with (RUN / "disk-dispatch-r4.lock").open("a") as shared, (RECOVERY / "batch-admission.lock").open("a") as own:
        fcntl.flock(shared, fcntl.LOCK_EX)
        fcntl.flock(own, fcntl.LOCK_EX | fcntl.LOCK_NB)
        queue_states = []
        for path in (ROOT / "runs/software-benchmark-v054/formal-queue-r1/state.json", RUN / "queue-r1/state.json"):
            state = json.loads(path.read_bytes())
            if any(row["generation"]["status"] not in ("closed", "technical_unknown") for row in state["rows"]):
                raise ValueError("Original generation inventories are not terminal; do not admit six recovery workers")
            queue_states.append({"path": str(path), "updated_utc": state["updated_utc"],
                                 "status": state.get("status"), "all_generation_rows_terminal": True})
        rows = [{"slot_id": slot["slot_id"], "observation": preflight(plan, slot)} for slot in plan["slots"]]
        total_peak = sum(row["observation"]["requested_full_two_clone_peak_bytes"] for row in rows)
        stat = os.statvfs(ROOT)
        available = stat.f_bavail * stat.f_frsize
        old_reserved = max(row["observation"]["old_qwen_peak_reserved_bytes"] for row in rows)
        remaining = available - old_reserved - total_peak
        if remaining < plan["resource_admission"]["minimum_primary_free_after_requested_peak_bytes"]:
            raise ValueError("Aggregate six-slot worst-case disk admission failed")
        receipt = {"version": plan["version"], "plan_sha256": sha,
            "observed_utc": datetime.now(timezone.utc).isoformat(), "slots": rows,
            "original_generation_inventories": queue_states, "shared_dispatch_lock": str(RUN / "disk-dispatch-r4.lock"),
            "all_six_peaks_counted_once_before_dispatch": True, "primary_available_bytes": available,
            "old_peak_reserved_bytes": old_reserved, "six_recovery_full_peak_bytes": total_peak,
            "remaining_after_all_peaks_bytes": remaining, "minimum_remaining_bytes": 256 * 1024**3,
            "maximum_parallel_recovery_workers": 6, "maximum_CPU_cores_for_six": 24,
            "maximum_memory_bytes_for_six": 96 * 1024**3, "shared_API_cap_retained": 64,
            "separate_scoring_allowance_CPU": 24, "separate_scoring_allowance_memory_bytes": 96 * 1024**3,
            "recovery_models_started": 0, "old_queue_or_claims_modified": False}
        path = RECOVERY / "batch-admission.json"
        write_new(path, receipt)
        print(json.dumps(reference(path)))


def cloned_template(plan, sha, slot, environment_manifest, destination):
    from proworksim.software_benchmark_native_rootfs_v054 import canonical, digest
    template = plan["template"]
    if Path(environment_manifest).resolve() != Path(template["public_environment"]["path"]).resolve():
        raise ValueError("Recovery requested a different template")
    public, manifest = checked(template["public_environment"]), checked(template["manifest"])
    destination = Path(destination).resolve()
    if destination != Path(slot["output_directory"]) / "actor":
        raise ValueError("Recovery actor destination differs")
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    subprocess.run(["sudo", "-n", "/usr/bin/python3", str(ROOT / "tools/native_uid_clone_preentry_v055_r1.py"),
        "--plan-sha256", sha, "--slot-id", slot["slot_id"], "--destination", str(destination / "rootfs")], check=True)
    manifest.update(prepared_root=str(destination / "rootfs"),
        cloned_from_manifest_sha256=template["manifest"]["sha256"],
        cloned_from_environment_sha256=template["public_environment"]["sha256"])
    path = destination / "rootfs-manifest.json"
    path.write_bytes(canonical(manifest))
    public.update(rootfs_manifest=str(path), rootfs_manifest_sha256=digest(path.read_bytes()))
    environment = destination / "public-environment.json"
    environment.write_bytes(canonical(public))
    return {"rootfs": str(destination / "rootfs"), "environment_manifest": str(environment),
            "rootfs_manifest": str(path), "rootfs_manifest_sha256": digest(path.read_bytes())}


def run_one(plan, sha, slot, admission_sha):
    admission = checked({"path": str(RECOVERY / "batch-admission.json"), "sha256": admission_sha})
    if (admission.get("plan_sha256") != sha or not admission.get("all_six_peaks_counted_once_before_dispatch")
            or slot["slot_id"] not in {row["slot_id"] for row in admission["slots"]}):
        raise ValueError("This slot lacks the frozen aggregate admission")
    lock_path = RECOVERY / (hashlib.sha256(slot["slot_id"].encode()).hexdigest() + ".lock")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        observation = preflight(plan, slot)
        output = Path(slot["output_directory"])
        directory = output.parent
        directory.mkdir(parents=True, exist_ok=False)
        write_new(directory / "recovery-intent.json", {"version": plan["version"], "plan_sha256": sha,
            "original_slot": slot, "preflight": observation, "aggregate_admission_sha256": admission_sha,
            "old_unknown_and_claim_retained": True, "old_entered_episode_replayed": False})
        from proworksim import software_benchmark_runner_v055 as runner
        before_root, before_clone, before_episode = runner.RUN_ROOT, runner.clone_prepared_rootfs, runner.ApiEpisode
        runner.RUN_ROOT = RECOVERY
        runner.clone_prepared_rootfs = lambda environment, destination: cloned_template(plan, sha, slot, environment, destination)
        class RecoveryEpisode(before_episode):
            def __init__(self, config):
                super().__init__(config)
                write_new(self.root / "pre-entry-recovery-link.json", {
                    "plan_sha256": sha, "original_slot_id": slot["slot_id"],
                    "original_claim": slot["original_claim"], "original_result": slot["original_result"],
                    "original_seed": slot["seed"], "old_unknown_preserved": True,
                    "old_entered_episode_replayed": False})
        runner.ApiEpisode = RecoveryEpisode
        path = ROOT / "tools/run_deepseek_episode_v055_r4.py"
        spec = importlib.util.spec_from_file_location("sealed_original_v055_r4", path)
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        before_argv = sys.argv
        sys.argv = [str(path), "--config", slot["config"]["path"], "--output", str(output)]
        try:
            code = entry.main()
        finally:
            sys.argv = before_argv
            runner.RUN_ROOT, runner.clone_prepared_rootfs, runner.ApiEpisode = before_root, before_clone, before_episode
        new_claim = RECOVERY / "episode-claims" / hashlib.sha256(slot["slot_id"].encode()).hexdigest() / "claim.json"
        write_new(directory / "recovery-completion.json", {"plan_sha256": sha,
            "finished_utc": datetime.now(timezone.utc).isoformat(), "returncode": code,
            "original_slot_id": slot["slot_id"], "original_result": slot["original_result"],
            "original_claim": slot["original_claim"], "recovery_claim": reference(new_claim),
            "recovery_result": reference(output / "result.json"), "primary_queue_updated": False})
        return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "preflight", "admit-batch", "run-one"))
    parser.add_argument("--plan-sha256")
    parser.add_argument("--slot-id")
    parser.add_argument("--admission-sha256")
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare()
        return 0
    plan = load_plan(args.plan_sha256)
    if args.operation == "admit-batch":
        admit_batch(plan, args.plan_sha256)
        return 0
    slot = next(row for row in plan["slots"] if row["slot_id"] == args.slot_id)
    if args.operation == "preflight":
        print(json.dumps(preflight(plan, slot), ensure_ascii=False))
        return 0
    return run_one(plan, args.plan_sha256, slot, args.admission_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
