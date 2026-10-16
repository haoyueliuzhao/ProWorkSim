"""CPU-only exact historical-callchain admission and finite refusal controls."""
import copy
import json
import os

import pytest

from proworksim.resource_monitor_v025 import worker_identity
from scripts import software_learning_startup_audit_v050r5 as audit
from scripts import software_learning_resume_v050r5 as host
from scripts.run_ne_v021 import write


def historical_fixture(root):
    root.mkdir()
    name = "update-Q_minus"
    source = {"code_commit": audit.PARENT_COMMIT, "code_dirty": False}
    expected = ["/python", "-m", "scripts.software_learning_resume_v050r4", "worker", "--run-root",
        str(root), "--worker", name, "--output", str(root / name / "actual")]
    reservation = {"gpu_index": 3, "gpu_uuid": "GPU-3", "target_mib": 73728}
    state = {"worker": name, "status": "stopped", "attempted": True, "stop_reason": "worker_exit_error",
        "exit_code": 1, "pid": 99999999, "process_identity": {"start_ticks": 123},
        "started_at": 10.0, "ended_at": 22.528383493423462, "elapsed_gpu_seconds": 12.528383493423462,
        "command": expected, "source_worktree": str(host.SOURCE), "reservation": reservation}
    plan = {"version": audit.PARENT_VERSION, "source": source, "source_root": str(host.SOURCE),
        "source_files": audit.SOURCE_HASHES, "native_python": "/python",
        "inventory": json.loads(host.original.DESIGN.read_text()),
        "continuation_generation_caps": host.generation_caps(),
        "q_compute_replay": host.seal({"branches": {"Q_minus": {"remaining_seconds": 135481}},
            "allocation": {"branch_seconds": {"Q_minus": 135481}}})}
    plan["single_slot_scheduling"] = host.scheduling_inventory(plan)
    plan = host.seal(plan, "plan_sha256")
    write(root / "plan.json", plan)
    states = {name: state}
    for worker in audit.DEVELOPMENT:
        states[worker] = {"worker": worker, "status": "stopped", "attempted": False,
            "stop_reason": "unopened_work_paused", "elapsed_gpu_seconds": 0,
            "planned_slots": [plan["single_slot_scheduling"][worker]["units"][0]["slot_id"]]}
    write(root / "supervisor.json", {"states": states})
    out = root / name / "actual"
    error = {"type": "RuntimeError", "message": "CUDA error: out of memory\nunchanged raw fault"}
    write(out / "report.json", {"version": audit.PARENT_VERSION, "worker": name, "status": "execution_error",
        "success_boundary": False, "source_before": source, "source_after": source,
        "new_actor_steps": 0, "new_critic_steps": 0, "error": error, "started_at": 11, "ended_at": 14})
    write(out / "task.json", {"task": "own-native-cache-reservation_wait", "kind": "reservation_wait",
        "pid": state["pid"], "new_model_calls": 0, "new_backward_calls": 0, "started_at": 12})
    write(root / "mechanism-stops" / (name + "-supervisor.json"), {"worker_state": state,
        "kind": "execution_fault", "worker": name, "observed_at": state["ended_at"]})
    write(root / "mechanism-stops" / (name + "-execution.json"), {"kind": "execution_fault",
        "worker": name, "error": error, "observed_at": 13})
    launch = {"actual_command": expected, "cwd": str(host.SOURCE), "launch_mode": "popen", "reservation": reservation}
    write(root / name / "worker-launch.json", launch)
    write(root / name / "reservation-binding-verified.json", {**launch, "verified_before_model_load": True})
    frames = [("scripts/software_learning_resume_v050r4.py", 309, "run_worker"),
        ("scripts/software_learning_v050.py", 495, "run_worker"),
        ("scripts/software_learning_resume_v050r3.py", 269, "_load_owner"),
        ("scripts/software_learning_resources_v050r3.py", 225, "reserve_before_load"),
        ("scripts/software_learning_resources_v050r3.py", 170, "cuda_snapshot")]
    trace = "Traceback (most recent call last):\n" + "".join(
        f'File "{host.SOURCE / path}", line {line}, in {function}\n' for path, line, function in frames)
    trace += "free, total = torch.cuda.mem_get_info()\nRuntimeError: CUDA error: out of memory\n"
    (root / name / "worker.log").write_text(trace)
    (root / name / "resources.jsonl").write_text('{"training_compute": null}\n')
    return plan, states


def test_parent_startup_proof_is_deterministic_and_preserves_original_compute_share(tmp_path):
    root = tmp_path / "r4"
    plan, states = historical_fixture(root)
    result = audit.derive_parent_failure(root, plan, states)
    assert result == audit.derive_parent_failure(root, plan, states)
    assert result["status"] == "passed" and result["new_model_calls"] == 0
    assert result["new_training_interval_seconds"] == 0
    assert result["old_worker_seconds"] == 12.528383493423462
    assert result["q_compute_replay"] == plan["q_compute_replay"]
    assert result["live_Q_plus_files_hashed"] is False and result["live_parent_supervisor_hashed"] is False
    assert len(result["closed_parent_workers"]) == 17


@pytest.mark.parametrize("mutation", ["model_intent", "compute_file", "nonzero", "development_started", "source"])
def test_historical_proof_refuses_any_model_work_or_changed_original_inventory(tmp_path, mutation):
    root = tmp_path / "r4"
    plan, states = historical_fixture(root)
    if mutation == "model_intent":
        write(root / "update-Q_minus/model-load-intent.json", {})
    elif mutation == "compute_file":
        write(root / "update-Q_minus/actual/training-compute.json", {})
    elif mutation == "nonzero":
        path = root / "update-Q_minus/actual/task.json"
        value = json.loads(path.read_text())
        value["new_model_calls"] = 1
        write(path, value)
    elif mutation == "development_started":
        states["dev-Q_plus-0"]["attempted"] = True
    else:
        plan = copy.deepcopy(plan)
        plan["source"]["code_commit"] = "different"
    with pytest.raises(ValueError):
        audit.derive_parent_failure(root, plan, states)


def test_historical_process_must_have_actually_exited():
    observed = worker_identity(os.getpid())
    with pytest.raises(ValueError, match="still alive"):
        audit._original_process_absent({"pid": os.getpid(), "process_identity": observed})
