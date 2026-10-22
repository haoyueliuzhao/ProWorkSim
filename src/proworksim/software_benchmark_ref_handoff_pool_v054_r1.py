"""Separate host-only REF resource retirement; original solver files stay frozen.

The overlay changes only the GPU retirement gate.  It does not change an old
result, settle an unknown ledger, claim another episode, or mark scoring done.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import secrets
import subprocess

from . import software_benchmark_resident_pool_v054 as pool
from . import software_benchmark_resident_provisioner_v054 as original
from . import software_benchmark_ref_terminal_boundary_v054_r1 as boundary
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_supervision_v054 import process_identity

ROOT = pool.ROOT
VERSION = "v054-ref-generation-terminal-pool-overlay-r1"
CLOSURE_VERSION = "v054-ref-resource-retirement-closure-r1"
TARGET_POLICY = ROOT / "runs/software-benchmark-v054/dynamic-pool-r4/policy.json"
ORIGINAL_MONITOR = "proworksim-v054-dynamic-pool-r4.service"
MODULE = ROOT / "src/proworksim/software_benchmark_ref_handoff_pool_v054_r1.py"
ENTRY = ROOT / "tools/monitor_ref_handoff_pool_v054_r1.py"
_ORIGINAL_READ_POOL = pool.read_pool
_OVERLAY_REF = None


def _stat(path):
    value = Path(path).stat()
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def validate_overlay(ref, *, initial=False):
    value = pool.read_ref(ref)
    if (value.get("version") != VERSION
            or value.get("target_pool_policy", {}).get("path") != str(TARGET_POLICY)
            or value.get("original_monitor_unit") != ORIGINAL_MONITOR
            or value.get("retirement_gate") != "all_original_REF_generation_terminal_and_live_resources_quiescent"
            or value.get("supersedes_only") != "ref_to_mp_after_all_500_scored"
            or value.get("score_completion_required") is not False
            or value.get("historical_results_and_unknown_costs_preserved") is not True
            or value.get("formal_replay_authorized") is not False
            or value.get("other_pool_policies_unchanged") is not True):
        raise ValueError("Unknown independent REF resource-retirement overlay")
    policy = pool.validate_pool_policy(value["target_pool_policy"])
    if value.get("slots") != policy["slots"] or value.get("queue_state_path") != policy["queue_state_path"]:
        raise ValueError("REF handoff changed the original inventory or queue identity")
    expected = {str(MODULE), str(ENTRY), str(Path(boundary.__file__).resolve()), str(TARGET_POLICY)}
    if {row["reference"]["path"] for row in value["files"]} != expected:
        raise ValueError("REF handoff source seal is incomplete")
    for row in value["files"]:
        if initial:
            checked(row["reference"])
        if _stat(row["reference"]["path"]) != row["stat"]:
            raise ValueError("Independent REF handoff source changed")
    return value


def freeze(output):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Handoff overlay must remain in the Qwen run root")
    ref = reference(TARGET_POLICY)
    policy = pool.validate_pool_policy(ref)
    refs = [reference(path) for path in (MODULE, ENTRY, Path(boundary.__file__).resolve(), TARGET_POLICY)]
    output.parent.mkdir(parents=True, exist_ok=False)
    result = write_new(output, {"version": VERSION, "created_utc": pool.now(),
        "target_pool_policy": ref, "slots": policy["slots"], "queue_state_path": policy["queue_state_path"],
        "original_monitor_unit": ORIGINAL_MONITOR,
        "retirement_gate": "all_original_REF_generation_terminal_and_live_resources_quiescent",
        "supersedes_only": "ref_to_mp_after_all_500_scored", "score_completion_required": False,
        "historical_results_and_unknown_costs_preserved": True,
        "formal_replay_authorized": False, "other_pool_policies_unchanged": True,
        "old_frozen_policy_bytes_changed": False, "old_frozen_solver_bytes_changed": False,
        "existing_failed_device_loads_retried": False,
        "new_MP_device_qualification": "original six-request two-session interleave control",
        "files": [{"reference": item, "stat": _stat(item["path"])} for item in refs]})
    validate_overlay(result, initial=True)
    return result


def _validate_new_closure(event, old, overlay_ref, overlay):
    if old is None or old["mode"] != "REF" or old["gpu_index"] != 7:
        raise ValueError("Only the original GPU7 REF registration can retire")
    closure = pool.read_ref(event["closure"])
    if (event.get("registration") != old["event_reference"]
            or event.get("retirement_rule") != VERSION
            or closure.get("version") != CLOSURE_VERSION
            or closure.get("overlay") != overlay_ref
            or closure.get("registration") != old["event_reference"]
            or closure.get("resource_retirement_only") is not True
            or closure.get("score_completion_required") is not False
            or closure.get("historical_results_and_unknown_costs_preserved") is not True
            or "all_500_ref_scored" in closure
            or closure.get("formal_episodes_replayed") != 0
            or closure.get("different_user_processes_stopped") != 0
            or closure.get("stop_returncode") != 0
            or not all(closure.get(key) is True for key in (
                "resident_session_idle", "old_unit_stopped", "old_cgroup_empty", "old_launcher_gone"))):
        raise ValueError("REF retirement lacks an explicit truthful independent closure")
    after = closure.get("post_stop_unit", {})
    if after.get("MainPID", "0") != "0" or after.get("ActiveState") not in {"inactive", "failed", "missing"}:
        raise ValueError("Retired REF unit is not recorded stopped")
    snapshot = pool.read_ref(closure["queue_snapshot"])
    evidence = boundary.ref_generation_evidence(snapshot, pool.read_ref(overlay["slots"]))
    proof = pool.read_ref(closure["runtime_boundary"])
    intent = pool.read_ref(closure["intent"])
    if (evidence.get("eligible") is not True
            or proof.get("version") != boundary.VERSION
            or proof.get("slots") != overlay["slots"]
            or proof.get("source") != reference(boundary.__file__)
            or proof.get("generation_evidence") != evidence
            or proof.get("all_ref_generation_quiescent") is not True
            or proof.get("resident_session_idle") is not True
            or proof.get("resident_inflight") != 0
            or proof.get("all_ref_generation_workers_quiet") is not True
            or proof.get("all_ref_registered_scopes_quiet") is not True
            or proof.get("all_ref_scores_claimed_complete") is not False
            or proof.get("registration") != old["event_reference"]
            or intent.get("registration") != old["event_reference"]
            or intent.get("overlay") != overlay_ref
            or intent.get("queue_snapshot") != closure["queue_snapshot"]
            or intent.get("runtime_boundary") != closure["runtime_boundary"]):
        raise ValueError("REF retirement boundary lost original inventory or live quiescence evidence")


def _read_target_pool(policy_ref, overlay_ref, overlay):
    policy = pool.validate_pool_policy(policy_ref)
    directory = Path(policy["pool_root"]) / "events"
    paths = sorted(directory.glob("*.json")) if directory.exists() else []
    active, events, previous, seen = {}, [], None, set()
    for sequence, path in enumerate(paths, 1):
        if path.name != f"{sequence:08d}.json":
            raise ValueError("Pool registration chain has a gap or renamed event")
        event_ref, event = reference(path), json.loads(path.read_text())
        if (event.get("version") != pool.EVENT_VERSION or event.get("sequence") != sequence
                or event.get("previous_event") != previous or event.get("pool_policy") != policy_ref):
            raise ValueError("Pool event chain identity changed")
        resident = event["resident_id"]
        if event["event"] == "register":
            pool._static_registration(event, policy_ref)
            if (resident in seen or any(x["gpu_uuid"] == event["gpu_uuid"] for x in active.values())
                    or len(active) >= policy["maximum_residents"]):
                raise ValueError("Duplicate physical device/resident or too many residents")
            seen.add(resident)
            active[resident] = {**event, "event_reference": event_ref}
        elif event["event"] == "retire":
            old = active.get(resident)
            if event.get("retirement_rule") == VERSION:
                _validate_new_closure(event, old, overlay_ref, overlay)
            else:
                closure = pool.read_ref(event["closure"])
                if (old is None or old["mode"] != "REF" or old["gpu_index"] != 7
                        or event.get("registration") != old["event_reference"]
                        or closure.get("registration") != old["event_reference"]
                        or not all(closure.get(key) is True for key in (
                            "all_500_ref_scored", "resident_session_idle", "old_unit_stopped",
                            "old_cgroup_empty", "old_launcher_gone"))):
                    raise ValueError("Legacy REF retirement lacks its original closure")
            active.pop(resident)
        else:
            raise ValueError("Unknown pool event")
        events.append(event_ref)
        previous = event_ref
    return {"events": events, "active": active}


def read_pool(policy_ref):
    if _OVERLAY_REF is None:
        return _ORIGINAL_READ_POOL(policy_ref)
    overlay = validate_overlay(_OVERLAY_REF)
    if policy_ref != overlay["target_pool_policy"]:
        return _ORIGINAL_READ_POOL(policy_ref)
    return _read_target_pool(policy_ref, _OVERLAY_REF, overlay)


def install(overlay_ref):
    """Install only in this host/worker process; no file or service mutation."""
    global _OVERLAY_REF
    overlay = validate_overlay(overlay_ref, initial=True)
    if _OVERLAY_REF is not None and _OVERLAY_REF != overlay_ref:
        raise ValueError("Another REF retirement overlay is already installed")
    _OVERLAY_REF = dict(overlay_ref)
    pool.read_pool = read_pool
    # The original provisioner imports read_pool directly; its registration
    # and polling functions need this private binding too. Existing functions
    # registrations/validate_registration already use pool.read_pool globals.
    original.read_pool = read_pool
    return overlay


def append_retirement(overlay_ref, fields):
    overlay = validate_overlay(overlay_ref)
    policy_ref = overlay["target_pool_policy"]
    policy = pool.validate_pool_policy(policy_ref)
    root = Path(policy["pool_root"])
    directory = root / "events"
    with (root / "registry.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = _read_target_pool(policy_ref, overlay_ref, overlay)
        event = {**fields, "event": "retire", "retirement_rule": VERSION,
            "version": pool.EVENT_VERSION, "pool_policy": policy_ref,
            "sequence": len(current["events"]) + 1,
            "previous_event": current["events"][-1] if current["events"] else None,
            "created_utc": pool.now()}
        _validate_new_closure(event, current["active"].get(event["resident_id"]), overlay_ref, overlay)
        temp = directory / (".pending-handoff-" + secrets.token_hex(8))
        write_new(temp, event)
        target = directory / f"{event['sequence']:08d}.json"
        os.link(temp, target)
        temp.unlink()
        fd = os.open(directory, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return reference(target)


class HandoffProvisioner(original.Provisioner):
    def __init__(self, overlay_ref):
        self.overlay_ref = overlay_ref
        self.overlay = install(overlay_ref)
        super().__init__(self.overlay["target_pool_policy"])

    def convert_ref(self, current):
        refs = [row for row in current["active"].values() if row["mode"] == "REF"]
        if not refs or self.state.get("conversion") is not None:
            return
        validate_overlay(self.overlay_ref)
        queue_path = Path(self.policy["queue_state_path"])
        queue = json.loads(queue_path.read_text())
        slots = pool.read_ref(self.policy["slots"])
        evidence = boundary.ref_generation_evidence(queue, slots)
        if not evidence["eligible"]:
            return
        if len(refs) != 1:
            raise ValueError("The original REF resident is not a singleton")
        from .software_benchmark_resident_session_v054 import admitted_resident
        event = refs[0]
        observed = admitted_resident(event["declaration"], pool_policy_reference=self.policy_ref,
                                     registration_reference=event["event_reference"])
        if observed is None:
            raise RuntimeError("Terminal REF inventory has no independently live registered resident")
        status = observed["status"]
        if status.get("active_claim") is not None or status.get("inflight") != 0 or status.get("poisoned") is not False:
            return
        proof = boundary.collect_runtime_boundary(queue, slots, observed,
            slots_reference=self.policy["slots"], queue_state_path=queue_path)
        if (proof.get("all_ref_generation_quiescent") is not True
                or proof.get("resident_session_idle") is not True
                or proof.get("resident_inflight") != 0
                or proof.get("generation_evidence") != evidence
                or proof.get("registration") != event["event_reference"]):
            raise ValueError("Live REF boundary did not pass; no model process changed")
        directory = self.root / "ref-to-mp-generation-terminal-r1"
        directory.mkdir(exist_ok=False)
        snapshot_ref = write_new(directory / "queue-state.json", queue)
        proof_ref = write_new(directory / "runtime-boundary.json", proof)
        ready = observed["ready"]
        intent = write_new(directory / "intent.json", {"version": VERSION,
            "overlay": self.overlay_ref, "registration": event["event_reference"],
            "queue_snapshot": snapshot_ref, "runtime_boundary": proof_ref,
            "resident_status": status, "ready": observed["ready_reference"],
            "unit_state": observed["unit_state"], "same_gpu_uuid": event["gpu_uuid"],
            "created_utc": pool.now(), "score_completion_required": False})
        self.state["conversion"] = {"status": "retirement_intent", "intent": intent,
                                    "resource_retirement_overlay": self.overlay_ref}
        self.save()
        state = original.unit_state(observed["declaration"]["unit"])
        if (state.get("InvocationID") != ready["invocation_id"]
                or int(state.get("MainPID", "0")) != ready["host_process"]["pid"]
                or process_identity(ready["host_process"]["pid"]) != ready["host_process"]):
            raise ValueError("REF invocation changed before one-time conversion")
        result = subprocess.run(["systemctl", "--user", "stop", observed["declaration"]["unit"]],
                                capture_output=True, text=True, timeout=60, check=False)
        after = original.unit_state(observed["declaration"]["unit"])
        group = Path("/sys/fs/cgroup" + ready["cgroup"])
        populated = any(path.read_text().strip() for path in group.rglob("cgroup.procs")) if group.exists() else False
        try:
            gone = process_identity(ready["host_process"]["pid"]) != ready["host_process"]
        except (FileNotFoundError, ProcessLookupError):
            gone = True
        if (result.returncode != 0 or after.get("MainPID", "0") != "0" or populated or not gone
                or after.get("ActiveState") not in {"inactive", "failed", "missing"}):
            raise RuntimeError("Old REF tree was not proven stopped; no MP conversion")
        closure = write_new(directory / "closure.json", {"version": CLOSURE_VERSION,
            "overlay": self.overlay_ref, "registration": event["event_reference"], "intent": intent,
            "queue_snapshot": snapshot_ref, "runtime_boundary": proof_ref,
            "resource_retirement_only": True, "score_completion_required": False,
            "historical_results_and_unknown_costs_preserved": True, "formal_episodes_replayed": 0,
            "resident_session_idle": True, "old_unit_stopped": True,
            "old_cgroup_empty": True, "old_launcher_gone": True,
            "post_stop_unit": after, "stop_returncode": result.returncode,
            "created_utc": pool.now(), "different_user_processes_stopped": 0})
        retirement = append_retirement(self.overlay_ref, {"resident_id": event["resident_id"],
            "registration": event["event_reference"], "closure": closure})
        self.state["conversion"].update(status="ref_retired_waiting_for_mp_capacity",
            closure=closure, retirement=retirement)
        self.save()
