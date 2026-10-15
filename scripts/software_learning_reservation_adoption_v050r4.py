"""CPU-only ownership and handoff of the already running GPU2 reservation.

The bootstrap and its PID are immutable historical inputs. No CUDA import,
allocation, child process creation, cache release or model call occurs here.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

VERSION = "software-learning-reservation-adoption-v0.50-r4"
PROJECT = Path("/data1/zhuxinrui/projects/ProWorkSim")
LEASE_ROOT = PROJECT / "runs/software-learning-v050-gpu2-reservation-r4"
SOURCE_ROOT = PROJECT / "artifacts/software-learning-v050/resume-r4-source"
RUN_ROOT = PROJECT / "runs/software-learning-v050-resume-r4"
OLD_SOURCE = PROJECT / "artifacts/software-learning-v050/resume-r3-source"
NATIVE_PYTHON = PROJECT / "runs/v016-sdk/resident-venv/bin/python"
PID, START_TICKS, GPU = 2111917, 449991926, 2
GPU_UUID = "GPU-88a33540-ff55-746e-d82b-45821b463102"
BOOTSTRAP_SHA256 = "4e3f374d2a09b1f2d5f340b326fe0f545d52aaf75a03a59a01e685ca1def3ac3"
UNKNOWN_EXIT = 255  # Local proxy sentinel, never represented as an OS exit receipt.


def _read(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError("Object receipt required")
    return value


def _reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _timestamp(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _process_identity(pid):
    """Read only proc metadata; do not expose unrelated environment variables."""
    root = Path("/proc") / str(pid)
    try:
        text = (root / "stat").read_text()
        fields = text[text.rfind(")") + 2:].split()
        result = {"pid": pid, "available": True, "alive": fields[0] not in {"Z", "X"},
            "state": fields[0], "start_ticks": int(fields[19]), "pgid": int(fields[2]),
            "session": int(fields[3])}
        if result["alive"]:
            env = {}
            for item in (root / "environ").read_bytes().split(b"\0"):
                key, sep, value = item.partition(b"=")
                if sep and key in {b"CUDA_VISIBLE_DEVICES", b"PROWORKSIM_V050R3_RESERVATION"}:
                    env[key.decode()] = value.decode()
            result.update(command=[p.decode() for p in (root / "cmdline").read_bytes().split(b"\0") if p],
                cwd=str((root / "cwd").resolve()), cuda_visible_devices=env.get("CUDA_VISIBLE_DEVICES"),
                reservation=json.loads(env.get("PROWORKSIM_V050R3_RESERVATION", "null")))
        return result
    except (FileNotFoundError, ProcessLookupError):
        return {"pid": pid, "available": True, "alive": False, "start_ticks": None}
    except (OSError, ValueError, IndexError) as error:
        return {"pid": pid, "available": False, "alive": None, "error": str(error)}


def validate_lease(binding):
    """Bind exclusively this historical PID, cache target, source and new run."""
    if (not isinstance(binding, dict) or binding.get("version") != VERSION
            or binding.get("lease_root") != str(LEASE_ROOT)
            or binding.get("source_root") != str(SOURCE_ROOT)
            or binding.get("run_root") != str(RUN_ROOT)
            or binding.get("worker") != "update-Q_plus"
            or type(binding.get("pid")) is not int or binding["pid"] != PID
            or binding.get("start_ticks") != START_TICKS
            or binding.get("gpu") != GPU or binding.get("gpu_uuid") != GPU_UUID):
        raise ValueError("Only the authorized existing GPU2 reservation may be adopted")
    launch = _read(LEASE_ROOT / "launch.json")
    expected_command = [str(NATIVE_PYTHON), str(LEASE_ROOT / "reserve-then-handoff.py"),
        str(LEASE_ROOT), str(OLD_SOURCE)]
    expected_reservation = {"version": "software-learning-resources-v0.50-r3", "gpu_index": GPU,
        "gpu_uuid": GPU_UUID, "sampled_free_mib": 81154.0, "target_mib": 73728}
    if (launch.get("pid") != PID or launch.get("start_ticks") != START_TICKS
            or launch.get("gpu") != GPU or launch.get("gpu_uuid") != GPU_UUID
            or launch.get("command") != expected_command or launch.get("cwd") != str(OLD_SOURCE)
            or launch.get("reservation") != expected_reservation
            or launch.get("bootstrap_sha256") != BOOTSTRAP_SHA256
            or launch.get("model_calls_at_launch") != 0
            or not _timestamp(launch.get("launched_at"))
            or binding.get("launch_ref") != _reference(LEASE_ROOT / "launch.json")
            or binding.get("bootstrap_ref") != _reference(LEASE_ROOT / "reserve-then-handoff.py")
            or binding["bootstrap_ref"]["sha256"] != BOOTSTRAP_SHA256
            or binding.get("actual_command") != expected_command
            or binding.get("launch_cwd") != str(OLD_SOURCE)
            or binding.get("reservation") != expected_reservation
            or binding.get("launched_at") != launch["launched_at"]):
        raise ValueError("Historical launch, bootstrap, reservation and delegated binding disagree")
    return binding


def _check_alive(binding, identity):
    if (identity.get("available") is not True or identity.get("alive") is not True
            or identity.get("pid") != binding["pid"]
            or identity.get("start_ticks") != binding["start_ticks"]
            or identity.get("pgid") != binding["pid"] or identity.get("session") != binding["pid"]
            or identity.get("command") != binding["actual_command"]
            or identity.get("cwd") not in {binding["launch_cwd"], binding["source_root"]}
            or identity.get("cuda_visible_devices") != str(binding["gpu"])
            or identity.get("reservation") != binding["reservation"]):
        raise ValueError("Exact owned process identity, group and GPU environment are required")


def _lease_state(binding):
    state = _read(Path(binding["lease_root"]) / "state.json")
    reservation = state.get("reservation", {})
    if (state.get("pid") != binding["pid"]
            or not _timestamp(state.get("started_at"))
            or state["started_at"] < binding["launched_at"]
            or not _timestamp(state.get("reserved_at"))
            or state["reserved_at"] < state["started_at"]
            or reservation.get("binding") != binding["reservation"]
            or reservation.get("stage") != "preload_cache_ready"
            or reservation.get("reserved_bytes", 0) < binding["reservation"]["target_mib"] * 1024**2
            or reservation.get("new_model_calls") != 0
            or reservation.get("empty_cache_called") is not False):
        raise ValueError("Lease state is not the established resource-only reservation")
    return state


def inspect_lease(lease_root, *, source_root, run_root, worker="update-Q_plus"):
    """Freeze the existing resource-only reservation; the new run need not exist."""
    lease_root, source_root, run_root = map(lambda p: Path(p).resolve(), (lease_root, source_root, run_root))
    launch = _read(lease_root / "launch.json")
    binding = {"version": VERSION, "lease_root": str(lease_root), "source_root": str(source_root),
        "run_root": str(run_root), "worker": worker, "pid": launch["pid"],
        "start_ticks": launch["start_ticks"], "gpu": launch["gpu"], "gpu_uuid": launch["gpu_uuid"],
        "actual_command": launch["command"], "launch_cwd": launch["cwd"],
        "reservation": launch["reservation"], "launched_at": launch["launched_at"],
        "launch_ref": _reference(lease_root / "launch.json"),
        "bootstrap_ref": _reference(lease_root / "reserve-then-handoff.py")}
    validate_lease(binding)
    state = _lease_state(binding)
    if (state.get("phase") != "reserved_waiting_for_frozen_worker"
            or state.get("model_started") is not False or (lease_root / "handoff.json").exists()):
        raise ValueError("Reservation has already been handed off or is not ready")
    _check_alive(binding, _process_identity(binding["pid"]))
    return binding


def _bound_handoff(binding, handoff):
    if (not isinstance(handoff, dict) or handoff.get("source_root") != binding["source_root"]
            or handoff.get("run_root") != binding["run_root"] or handoff.get("worker") != binding["worker"]
            or handoff.get("pid") != binding["pid"] or handoff.get("start_ticks") != binding["start_ticks"]
            or handoff.get("lease_binding") != binding):
        raise ValueError("Worker acknowledgement is not bound to the owned handoff")
    plan = _read(Path(binding["run_root"]) / "plan.json")
    if plan["source"]["code_commit"] != handoff.get("source_commit"):
        raise ValueError("Worker acknowledgement source differs from the frozen plan")
    if handoff != _read(Path(binding["lease_root"]) / "handoff.json"):
        raise ValueError("Worker acknowledgement differs from the published handoff")


def observe_lease(binding, *, now=None):
    """Observe non-child lifetime; missing exit evidence can never imply success."""
    validate_lease(binding)
    state = _lease_state(binding)
    identity = _process_identity(binding["pid"])
    now = time.time() if now is None else now
    entry = state.get("worker_entry_at")
    phase = state.get("phase")
    if phase not in {"reserved_waiting_for_frozen_worker", "handoff_to_frozen_worker", "worker_entry", "complete", "failed"}:
        raise ValueError("Unknown reservation lifecycle phase")
    if state.get("handoff") is not None:
        _bound_handoff(binding, state["handoff"])
    if entry is not None and (not _timestamp(entry) or entry < state["reserved_at"]
            or state.get("handoff") is None):
        raise ValueError("Worker entry lacks a bound handoff or monotonic timestamp")
    ended = state.get("ended_at")
    exit_code = state.get("exit_code")
    terminal = (phase in {"complete", "failed"} and _timestamp(ended)
        and ended >= (entry or state["reserved_at"]) and type(exit_code) is int
        and exit_code == (0 if phase == "complete" else 1)
        and (phase != "complete" or entry is not None))
    error = None
    if identity.get("alive") is True:
        try:
            _check_alive(binding, identity)
            status = "running"
        except ValueError as exception:
            status, error = "unknown", str(exception)
    elif identity.get("available") is True and identity.get("alive") is False:
        if identity.get("start_ticks") not in (None, binding["start_ticks"]):
            status, error = "unknown", "PID identity changed"
        else:
            status = "terminal" if terminal else "unknown"
            if not terminal:
                error = "Owned process ended without a bound exit receipt"
    else:
        status, error = "unknown", "Process identity is unavailable"
    boundary = ended if terminal and status == "terminal" else now
    total = max(0.0, boundary - binding["launched_at"])
    preworker = max(0.0, (entry or boundary) - binding["launched_at"])
    return {"version": VERSION, "status": status, "phase": phase, "lease_state": state,
        "process_identity": identity, "worker_entry_at": entry,
        "exit_code": exit_code if status == "terminal" else None, "error": error,
        "model_started_is_entry_intent_only": True,
        "reservation_preworker_seconds": min(total, preworker),
        "formal_worker_seconds": max(0.0, total - preworker), "total_process_seconds": total}


def validate_owner_records(binding):
    """Require supervisor ownership and actual bootstrap argv before handoff."""
    validate_lease(binding)
    root, worker = Path(binding["run_root"]), binding["worker"]
    state = _read(root / "supervisor.json")["states"][worker]
    launch = _read(root / worker / "worker-launch.json")
    if (state.get("worker") != worker or state.get("status") != "running"
            or state.get("attempted") is not True or state.get("pid") != binding["pid"]
            or state.get("process_identity", {}).get("start_ticks") != binding["start_ticks"]
            or state.get("gpu") != binding["gpu"] or state.get("gpu_uuid") != binding["gpu_uuid"]
            or state.get("reservation") != binding["reservation"]
            or state.get("launch_mode") != "adopted_reservation"
            or state.get("command") != binding["actual_command"]
            or state.get("lease_binding") != binding
            or launch.get("launch_mode") != "adopted_reservation"
            or launch.get("actual_command") != binding["actual_command"]
            or launch.get("cwd") != binding["launch_cwd"]
            or launch.get("source_worktree") != binding["source_root"]
            or launch.get("reservation") != binding["reservation"]
            or launch.get("original_worker") != worker or launch.get("planned_units") != []
            or launch.get("lease_binding") != binding):
        raise ValueError("Supervisor, actual bootstrap launch and lease ownership disagree")
    return state


def write_handoff(binding, *, source_commit):
    """Publish once, only after a clean frozen source and exact host ownership."""
    validate_owner_records(binding)
    _check_alive(binding, _process_identity(binding["pid"]))
    state = _lease_state(binding)
    if state.get("phase") != "reserved_waiting_for_frozen_worker" or state.get("model_started") is not False:
        raise ValueError("This resource reservation cannot be handed off twice")
    root = Path(binding["run_root"])
    plan = _read(root / "plan.json")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=binding["source_root"], text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=binding["source_root"], text=True)
    if dirty or head != source_commit or plan["source"]["code_commit"] != head:
        raise ValueError("Handoff requires the exact clean frozen source commit")
    value = {"source_root": binding["source_root"], "run_root": binding["run_root"],
        "worker": binding["worker"], "source_commit": source_commit, "pid": binding["pid"],
        "start_ticks": binding["start_ticks"], "lease_binding": binding, "requested_at": time.time()}
    path = Path(binding["lease_root"]) / "handoff.json"
    temporary = path.with_name(".handoff-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # Atomic no-replace publication; bootstrap never sees partial JSON.
    finally:
        temporary.unlink(missing_ok=True)
    return _reference(path)


class AdoptedProcess:
    """Popen-shaped non-child proxy; never calls waitpid or launches a process."""

    def __init__(self, binding):
        self.binding = validate_lease(binding)
        self.pid, self.args = binding["pid"], binding["actual_command"]
        self.returncode = None
        self.termination_evidence = None
        self.assert_owned()

    def assert_owned(self):
        identity = _process_identity(self.pid)
        _check_alive(self.binding, identity)
        return identity

    def poll(self):
        if self.returncode is None:
            observation = observe_lease(self.binding)
            if observation["status"] != "running":
                self.termination_evidence = observation
                self.returncode = observation["exit_code"] if observation["status"] == "terminal" else UNKNOWN_EXIT
        return self.returncode

    def wait(self, timeout=None):
        start = time.monotonic()
        while self.poll() is None:
            if timeout is not None and time.monotonic() - start >= timeout:
                raise subprocess.TimeoutExpired(self.args, timeout)
            time.sleep(min(0.1, max(0.0, timeout - (time.monotonic() - start))) if timeout is not None else 0.1)
        return self.returncode

    def send_signal(self, sig):
        if self.poll() is None:
            self.assert_owned()
            os.killpg(self.pid, sig)

    def terminate(self):
        self.send_signal(signal.SIGTERM)

    def kill(self):
        self.send_signal(signal.SIGKILL)
