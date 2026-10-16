"""Read-only, exact-source proof of the historical r4 pre-model CUDA startup failure."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

VERSION = "software-learning-premodel-startup-proof-v0.50-r5"
PARENT_VERSION = "software-learning-original-Q-continuation-v0.50-r4"
PARENT_COMMIT = "621219af2483f955c59d9df36b62ad46ba9eeb6d"
SOURCE_HASHES = {
    "scripts/software_learning_resume_v050r4.py": "d081b2cfd90738bbe9516749e8dd2eb32a9b721e97bff6bc4c5f4bbd78f180d0",
    "scripts/software_learning_resume_v050r3.py": "3b9a20bee695656de1d3e38f72a03ef7e9e084d206a652589d0ac7c94ad73419",
    "scripts/software_learning_resources_v050r3.py": "9b1ae6ae34ec4337b072793d0d7cad666d3b290651e7e9b1bd621a815fd2287a",
    "scripts/software_learning_v050.py": "9b218af97cbfe3694ad74eac24e58eeda91189d48182d776a62d3c8c873cbc51",
    "scripts/software_learning_v049.py": "9b6fa4d57996144306ac7cafa4724cb5d59f9ca751d2bcdd7c436e50aa03b3f6",
    "scripts/software_learning_resume_compute_v050r4.py": "1d5d2761adeb221260e845f4e7151d5b4f1226588c605aabfaf53a36d25bec8a",
}
DEVELOPMENT = tuple(f"dev-{branch}-{index}" for branch in ("Q_plus", "Q_minus") for index in range(8))


def _bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def _hash(content):
    return hashlib.sha256(content).hexdigest()


def _read(path):
    return json.loads(Path(path).read_text())


def _ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": _hash(path.read_bytes())}


def _seal(value):
    return {**value, "sha256": _hash(_bytes(value))}


def _check_seal(value, key="sha256"):
    if value.get(key) != _hash(_bytes({k: v for k, v in value.items() if k != key})):
        raise ValueError("Historical artifact seal changed")
    return value


def _original_process_absent(state):
    """A missing /proc identity is accepted only as ENOENT, never permission failure."""
    pid = state.get("pid")
    expected = state.get("process_identity", {}).get("start_ticks")
    if type(pid) is not int or type(expected) is not int or pid <= 0 or expected <= 0:
        raise ValueError("Require the original PID/start_ticks identity")
    # Establish that this is a usable procfs; unsupported/read-denied is not death.
    Path("/proc/self/stat").read_text()
    try:
        fields = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
    except FileNotFoundError:
        return True
    except (OSError, IndexError) as error:
        raise ValueError("Cannot establish the stopped process identity") from error
    try:
        current_start = int(fields[19])
        process_state = fields[0]
    except (ValueError, IndexError) as error:
        raise ValueError("Cannot establish the stopped process identity") from error
    if current_start == expected and process_state not in {"Z", "X"}:
        raise ValueError("The historical worker identity is still alive")
    return True


def derive_parent_failure(root, plan=None, states=None):
    """Return a deterministic sealed proof; never bind live Q-plus/supervisor bytes."""
    root = Path(root).resolve()
    disk_plan = _check_seal(_read(root / "plan.json"), "plan_sha256")
    if plan is not None and plan != disk_plan:
        raise ValueError("Parent plan differs from its frozen file")
    plan = disk_plan
    if states is None:
        states = _read(root / "supervisor.json")["states"]
    if (plan.get("version") != PARENT_VERSION
            or plan.get("source", {}).get("code_commit") != PARENT_COMMIT
            or plan["source"].get("code_dirty") is not False):
        raise ValueError("Only the exact frozen r4 source is covered by this proof")
    source = Path(plan["source_root"]).resolve()
    source_evidence = {}
    for relative, expected in SOURCE_HASHES.items():
        ref = _ref(source / relative)
        if ref["sha256"] != expected or plan["source_files"].get(relative) != expected:
            raise ValueError("The historical source call-chain changed: " + relative)
        source_evidence[relative] = ref

    worker = "update-Q_minus"
    folder, output = root / worker, root / worker / "actual"
    actual_paths = sorted(p.relative_to(output).as_posix() for p in output.rglob("*"))
    if actual_paths != ["report.json", "task.json"]:
        raise ValueError("Require exactly the two pre-model actual files, no load/compute evidence")
    if any(p.is_symlink() for p in output.rglob("*")):
        raise ValueError("Historical actual artifacts must be ordinary files")
    expected_files = ["actual/report.json", "actual/task.json", "reservation-binding-verified.json",
                      "resources.jsonl", "worker-launch.json", "worker.log"]
    files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    if files != expected_files or any(p.is_symlink() for p in folder.rglob("*")):
        raise ValueError("Unexpected historical worker evidence requires independent review")
    task, report = _read(output / "task.json"), _read(output / "report.json")
    stop_path = root / "mechanism-stops" / (worker + "-supervisor.json")
    execution_path = root / "mechanism-stops" / (worker + "-execution.json")
    stop, execution = _read(stop_path), _read(execution_path)
    state = copy.deepcopy(states[worker])
    if (state != stop.get("worker_state") or state.get("worker") != worker
            or state.get("status") != "stopped" or state.get("attempted") is not True
            or state.get("stop_reason") != "worker_exit_error" or state.get("exit_code") != 1
            or stop.get("kind") != "execution_fault" or stop.get("worker") != worker
            or execution.get("kind") != "execution_fault" or execution.get("worker") != worker):
        raise ValueError("Require the original closed failure and its exact stopped state")
    _original_process_absent(state)
    error = report.get("error", {})
    if (report.get("version") != PARENT_VERSION or report.get("worker") != worker
            or report.get("status") != "execution_error" or report.get("success_boundary") is not False
            or report.get("new_actor_steps") != 0 or report.get("new_critic_steps") != 0
            or report.get("source_before") != plan["source"] or report.get("source_after") != plan["source"]
            or error.get("type") != "RuntimeError" or not error.get("message", "").startswith("CUDA error: out of memory\n")
            or execution.get("error") != error
            or task.get("task") != "own-native-cache-reservation_wait"
            or task.get("kind") != "reservation_wait" or task.get("pid") != state["pid"]
            or task.get("new_model_calls") != 0 or task.get("new_backward_calls") != 0):
        raise ValueError("The old exception/task/report is not the proved pre-model OOM")
    if not (state["started_at"] <= report["started_at"] <= task["started_at"]
            <= execution["observed_at"] <= report["ended_at"] <= state["ended_at"]
            == stop["observed_at"]):
        raise ValueError("Historical startup event ordering changed")
    elapsed = state["ended_at"] - state["started_at"]
    if elapsed != state["elapsed_gpu_seconds"] or elapsed != 12.528383493423462:
        raise ValueError("Historical startup worker accounting changed")
    launch, verified = _read(folder / "worker-launch.json"), _read(folder / "reservation-binding-verified.json")
    expected_command = [plan["native_python"], "-m", "scripts.software_learning_resume_v050r4",
                        "worker", "--run-root", str(root), "--worker", worker, "--output", str(output)]
    if (state.get("command") != expected_command or launch.get("actual_command") != expected_command
            or verified.get("actual_command") != expected_command
            or launch.get("cwd") != str(source) or state.get("source_worktree") != str(source)
            or launch.get("launch_mode") != "popen" or verified.get("launch_mode") != "popen"
            or verified.get("verified_before_model_load") is not True
            or launch.get("reservation") != state.get("reservation")
            or verified.get("reservation") != state.get("reservation")):
        raise ValueError("Historical dispatch and resource binding no longer agree")
    trace = (folder / "worker.log").read_text()
    frames = [
        ("scripts/software_learning_resume_v050r4.py", 309, "run_worker"),
        ("scripts/software_learning_v050.py", 495, "run_worker"),
        ("scripts/software_learning_resume_v050r3.py", 269, "_load_owner"),
        ("scripts/software_learning_resources_v050r3.py", 225, "reserve_before_load"),
        ("scripts/software_learning_resources_v050r3.py", 170, "cuda_snapshot"),
    ]
    cursor = 0
    for relative, line, function in frames:
        fragment = f'File "{source / relative}", line {line}, in {function}\n'
        index = trace.find(fragment, cursor)
        if index < 0:
            raise ValueError("Exact first-snapshot traceback chain is missing")
        cursor = index + len(fragment)
    if ("free, total = torch.cuda.mem_get_info()" not in trace[cursor:]
            or "RuntimeError: CUDA error: out of memory\n" not in trace[cursor:]
            or trace.count("Traceback (most recent call last):") != 1):
        raise ValueError("Require the original first mem_get_info CUDA OOM traceback")
    telemetry = [json.loads(line) for line in (folder / "resources.jsonl").read_text().splitlines()]
    if not telemetry or any(x.get("training_compute") is not None for x in telemetry):
        raise ValueError("A historical training interval exists or resource evidence is missing")
    closed = {worker: {"state": state, "report": _ref(output / "report.json")}}
    units = []
    for name in DEVELOPMENT:
        old = copy.deepcopy(states[name])
        planned = plan["single_slot_scheduling"][name]["units"]
        if (len(planned) != 1 or old.get("worker") != name or old.get("status") != "stopped"
                or old.get("attempted") is not False or old.get("stop_reason") != "unopened_work_paused"
                or old.get("elapsed_gpu_seconds") != 0 or (root / name).exists()
                or old.get("planned_slots") != [planned[0]["slot_id"]]):
            raise ValueError("An original development worker is no longer untouched: " + name)
        units.extend(copy.deepcopy(planned))
        closed[name] = {"state": old}
    if len({u["slot_id"] for u in units}) != 16 or sum(u["generation_token_cap"] for u in units) != 8000000:
        raise ValueError("The sixteen original development identities/caps changed")
    replay = _check_seal(plan["q_compute_replay"])
    if (replay["branches"]["Q_minus"]["remaining_seconds"] != 135481
            or replay["allocation"]["branch_seconds"]["Q_minus"] != 135481):
        raise ValueError("The unchanged r4 Q-minus training share is not established")
    refs = [_ref(folder / relative) for relative in files] + [_ref(stop_path), _ref(execution_path)]
    return _seal({"version": VERSION, "status": "passed", "parent_run_root": str(root),
        "parent_plan": _ref(root / "plan.json"), "parent_source": copy.deepcopy(plan["source"]),
        "failure_artifacts": refs, "actual_file_inventory": actual_paths, "worker_file_inventory": files,
        "closed_parent_workers": closed, "source_callchain": [{"source": source_evidence[relative],
            "line": line, "function": function} for relative, line, function in frames],
        "source_evidence": source_evidence, "original_process_identity_no_longer_alive": True,
        "no_model_load_reached": True, "no_reservation_tensor_allocation_reached": True,
        "new_model_calls": 0, "new_backward_calls": 0, "new_actor_steps": 0, "new_critic_steps": 0,
        "new_training_interval_seconds": 0, "old_worker_seconds": elapsed,
        "old_worker_cost_counted_once": True, "old_failure_records_rewritten": False,
        "q_compute_replay": copy.deepcopy(replay), "Q_minus_training_seconds_unconsumed": 135481,
        "development_units": units, "development_generation_caps": copy.deepcopy(plan["continuation_generation_caps"]),
        "live_Q_plus_files_hashed": False, "live_parent_supervisor_hashed": False,
        "Q_plus_result_or_cost_finalized": False, "tensor_files_loaded": 0,
        "torch_imports": 0, "audit_gpu_calls": 0})
