"""CPU controls for the single existing GPU2 lease, with simulated proc records."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import signal
import subprocess

import pytest

from scripts import software_learning_reservation_adoption_v050r4 as adoption


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def lease(tmp_path, monkeypatch):
    root = tmp_path / "lease"
    root.mkdir()
    source, run, old = tmp_path / "r4source", tmp_path / "run", tmp_path / "r3source"
    for name, value in {"LEASE_ROOT": root, "SOURCE_ROOT": source, "RUN_ROOT": run,
            "OLD_SOURCE": old, "NATIVE_PYTHON": tmp_path / "python"}.items():
        monkeypatch.setattr(adoption, name, value)
    bootstrap = root / "reserve-then-handoff.py"
    bootstrap.write_text("# immutable simulated bootstrap\n")
    monkeypatch.setattr(adoption, "BOOTSTRAP_SHA256", hashlib.sha256(bootstrap.read_bytes()).hexdigest())
    command = [str(adoption.NATIVE_PYTHON), str(bootstrap), str(root), str(old)]
    reservation = {"version": "software-learning-resources-v0.50-r3", "gpu_index": adoption.GPU,
        "gpu_uuid": adoption.GPU_UUID, "sampled_free_mib": 81154.0, "target_mib": 73728}
    launch = {"pid": adoption.PID, "start_ticks": adoption.START_TICKS,
        "gpu": adoption.GPU, "gpu_uuid": adoption.GPU_UUID, "command": command, "cwd": str(old),
        "reservation": reservation, "launched_at": 100.0, "model_calls_at_launch": 0,
        "bootstrap_sha256": adoption.BOOTSTRAP_SHA256}
    state = {"pid": adoption.PID, "started_at": 101.0, "reserved_at": 102.0,
        "phase": "reserved_waiting_for_frozen_worker", "model_started": False,
        "reservation": {"binding": reservation, "stage": "preload_cache_ready",
            "reserved_bytes": 73728 * 1024**2, "new_model_calls": 0, "empty_cache_called": False}}
    put(root / "launch.json", launch)
    put(root / "state.json", state)
    identity = {"pid": adoption.PID, "available": True, "alive": True, "state": "S",
        "start_ticks": adoption.START_TICKS, "pgid": adoption.PID, "session": adoption.PID,
        "command": command, "cwd": str(old), "cuda_visible_devices": "2", "reservation": reservation}
    monkeypatch.setattr(adoption, "_process_identity", lambda pid: copy.deepcopy(identity))
    binding = adoption.inspect_lease(root, source_root=source, run_root=run)
    return {"root": root, "source": source, "run": run, "binding": binding,
        "state": state, "identity": identity, "launch": launch}


def own(lease):
    binding = lease["binding"]
    state = {"worker": "update-Q_plus", "status": "running", "attempted": True,
        "pid": binding["pid"], "process_identity": {"start_ticks": binding["start_ticks"]},
        "gpu": binding["gpu"], "gpu_uuid": binding["gpu_uuid"], "reservation": binding["reservation"],
        "launch_mode": "adopted_reservation", "command": binding["actual_command"], "lease_binding": binding}
    launch = {"launch_mode": "adopted_reservation", "actual_command": binding["actual_command"],
        "cwd": binding["launch_cwd"], "source_worktree": binding["source_root"],
        "reservation": binding["reservation"], "original_worker": "update-Q_plus", "planned_units": [],
        "lease_binding": binding}
    put(lease["run"] / "plan.json", {"source": {"code_commit": "frozen"}})
    put(lease["run"] / "supervisor.json", {"states": {"update-Q_plus": state}})
    put(lease["run"] / "update-Q_plus/worker-launch.json", launch)
    return state, launch


def enter(lease):
    own(lease)
    handoff = {"source_root": str(lease["source"]), "run_root": str(lease["run"]),
        "worker": "update-Q_plus", "source_commit": "frozen", "pid": adoption.PID,
        "start_ticks": adoption.START_TICKS, "lease_binding": lease["binding"]}
    put(lease["root"] / "handoff.json", handoff)
    lease["state"].update(phase="worker_entry", worker_entry_at=120.0, model_started=True, handoff=handoff)
    put(lease["root"] / "state.json", lease["state"])


def test_inspection_only_reads_ready_lease_without_creating_run(lease):
    assert not lease["run"].exists()
    observation = adoption.observe_lease(lease["binding"], now=115.0)
    assert observation["status"] == "running"
    assert observation["formal_worker_seconds"] == 0
    assert observation["reservation_preworker_seconds"] == observation["total_process_seconds"] == 15
    assert not (lease["root"] / "handoff.json").exists()


@pytest.mark.parametrize(("key", "value"), [
    ("pid", 2111918), ("start_ticks", 449991927), ("worker", "update-Q_minus"),
    ("gpu", 3), ("gpu_uuid", "other"), ("source_root", "/other"), ("run_root", "/other"),
])
def test_lease_cannot_be_retargeted(lease, key, value):
    changed = {**lease["binding"], key: value}
    with pytest.raises(ValueError):
        adoption.validate_lease(changed)


@pytest.mark.parametrize(("key", "value"), [
    ("start_ticks", 2), ("pgid", 2), ("session", 2), ("command", ["other"]),
    ("cuda_visible_devices", "3"), ("reservation", {}), ("alive", False),
])
def test_inspection_requires_exact_live_process_and_gpu_environment(lease, key, value):
    lease["identity"][key] = value
    with pytest.raises(ValueError):
        adoption.inspect_lease(lease["root"], source_root=lease["source"], run_root=lease["run"])


def test_changed_bootstrap_is_rejected(lease):
    (lease["root"] / "reserve-then-handoff.py").write_text("changed")
    with pytest.raises(ValueError):
        adoption.validate_lease(lease["binding"])


def test_handoff_requires_published_exact_supervisor_ownership(lease, monkeypatch):
    state, _ = own(lease)
    state["pid"] += 1
    put(lease["run"] / "supervisor.json", {"states": {"update-Q_plus": state}})
    monkeypatch.setattr(adoption.subprocess, "check_output", lambda *a, **k: pytest.fail("No git before ownership"))
    with pytest.raises(ValueError):
        adoption.write_handoff(lease["binding"], source_commit="frozen")
    assert not (lease["root"] / "handoff.json").exists()


@pytest.mark.parametrize("dirty,head", [(" M changed", "frozen"), ("", "other")])
def test_handoff_requires_clean_frozen_source(lease, monkeypatch, dirty, head):
    own(lease)
    monkeypatch.setattr(adoption.subprocess, "check_output", lambda args, **kw: head if args[1] == "rev-parse" else dirty)
    with pytest.raises(ValueError):
        adoption.write_handoff(lease["binding"], source_commit="frozen")
    assert not (lease["root"] / "handoff.json").exists()


def test_handoff_is_owned_atomic_and_never_overwrites(lease, monkeypatch):
    own(lease)
    monkeypatch.setattr(adoption.subprocess, "check_output", lambda args, **kw: "frozen" if args[1] == "rev-parse" else "")
    reference = adoption.write_handoff(lease["binding"], source_commit="frozen")
    before = Path(reference["path"]).read_bytes()
    assert hashlib.sha256(before).hexdigest() == reference["sha256"]
    assert json.loads(before)["lease_binding"] == lease["binding"]
    with pytest.raises(FileExistsError):
        adoption.write_handoff(lease["binding"], source_commit="frozen")
    assert Path(reference["path"]).read_bytes() == before
    assert not list(lease["root"].glob(".handoff-*.tmp"))


def test_actual_bootstrap_argv_must_not_be_replaced_by_logical_command(lease):
    _, launch = own(lease)
    launch["actual_command"] = ["python", "-m", "scripts.software_learning_resume_v050r4"]
    put(lease["run"] / "update-Q_plus/worker-launch.json", launch)
    with pytest.raises(ValueError):
        adoption.validate_owner_records(lease["binding"])


def test_entry_partitions_time_without_claiming_native_compute(lease):
    enter(lease)
    result = adoption.observe_lease(lease["binding"], now=140.0)
    assert result["reservation_preworker_seconds"] == 20
    assert result["formal_worker_seconds"] == 20
    assert result["total_process_seconds"] == 40
    assert result["model_started_is_entry_intent_only"] is True


def test_nonchild_wait_is_bounded_and_never_calls_waitpid(lease, monkeypatch):
    monkeypatch.setattr(adoption.os, "waitpid", lambda *a: pytest.fail("Non-child waitpid forbidden"))
    process = adoption.AdoptedProcess(lease["binding"])
    assert process.poll() is None
    with pytest.raises(subprocess.TimeoutExpired):
        process.wait(timeout=0)


def test_dead_without_exit_receipt_is_unknown_not_success(lease):
    process = adoption.AdoptedProcess(lease["binding"])
    lease["identity"].update(alive=False, state="Z")
    assert process.wait(timeout=0) == adoption.UNKNOWN_EXIT
    assert process.termination_evidence["status"] == "unknown"
    assert process.termination_evidence["exit_code"] is None


def test_worker_report_alone_cannot_claim_process_exit(lease):
    process = adoption.AdoptedProcess(lease["binding"])
    put(lease["run"] / "update-Q_plus/actual/report.json", {"status": "complete", "success_boundary": True})
    lease["identity"].update(alive=False)
    assert process.poll() == adoption.UNKNOWN_EXIT


def test_bound_exit_receipt_requires_process_exit_and_preserves_elapsed_partition(lease):
    process = adoption.AdoptedProcess(lease["binding"])
    enter(lease)
    lease["state"].update(phase="complete", ended_at=145.0, exit_code=0)
    put(lease["root"] / "state.json", lease["state"])
    assert process.poll() is None
    lease["identity"].update(alive=False, state="Z")
    assert process.wait(timeout=0) == 0
    evidence = process.termination_evidence
    assert evidence["formal_worker_seconds"] == 25
    assert evidence["reservation_preworker_seconds"] == 20
    assert evidence["total_process_seconds"] == 45


def test_reused_pid_is_unknown_and_cannot_be_signalled(lease, monkeypatch):
    process = adoption.AdoptedProcess(lease["binding"])
    lease["identity"]["start_ticks"] += 1
    monkeypatch.setattr(adoption.os, "killpg", lambda *a: pytest.fail("Never signal reused PID"))
    assert process.poll() == adoption.UNKNOWN_EXIT
    with pytest.raises(ValueError):
        process.assert_owned()
    process.terminate()


def test_signal_only_exact_owned_group(lease, monkeypatch):
    process = adoption.AdoptedProcess(lease["binding"])
    calls = []
    monkeypatch.setattr(adoption.os, "killpg", lambda pid, sig: calls.append((pid, sig)))
    process.terminate()
    assert calls == [(adoption.PID, signal.SIGTERM)]
