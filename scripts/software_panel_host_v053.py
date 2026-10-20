"""Prepare and supervise the fixed 200/40 native panel without loading a host model."""
from __future__ import annotations

import argparse
import copy
import csv
import fcntl
import http.client
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import time
from urllib.parse import urlencode

from proworksim import software_panel_native_v053 as native
from proworksim import software_panel_resources_v053 as resources
from scripts import software_panel_run_v053 as runner

VERSION = "software-panel-host-v053"
PHASE_SECONDS = {
    "boot": 120, "reservation": 900, "loading": 900, "preparation": 600,
    "generation": 660, "episode": 6000, "scoring": 600, "measurement": 600, "closed": 120,
}
ACTIVE_POLL_SECONDS = 5
IDLE_POLL_SECONDS = 60
TERMINATION_GRACE_SECONDS = 30


def read(path):
    return json.loads(Path(path).read_bytes())


def stat_identity(path):
    stat = Path(path).lstat()
    return {
        "dev": stat.st_dev, "ino": stat.st_ino, "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns, "ctime_ns": stat.st_ctime_ns, "mode": stat.st_mode,
    }


def freeze_snapshot(project_root, destination):
    """Freeze committed src/scripts and read-only-by-contract asset path aliases."""
    project, destination = Path(project_root).resolve(), Path(destination).resolve()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "src", "scripts"],
        cwd=project, text=True)
    if dirty:
        raise ValueError("Commit all new source and scripts before freezing the execution snapshot")
    names = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "src", "scripts"], cwd=project).decode().split("\0")
    names = [name for name in names if name]
    if not names or destination.exists():
        raise ValueError("Use one fresh snapshot destination and a nonempty tracked source inventory")
    destination.mkdir(parents=True)
    files = {}
    for name in names:
        source, target = project / name, destination / name
        if not source.is_file() or source.is_symlink():
            raise ValueError("Snapshot tracked sources must be regular files: " + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        files[name] = native.digest(target.read_bytes())
        target.chmod(0o444)
    aliases = {}
    for name in ("artifacts", "runs"):
        target = (project / name).resolve()
        (destination / name).symlink_to(target, target_is_directory=True)
        aliases[name] = {"path": str(target), "use": "read_existing_assets_only"}
    for directory in sorted(
            (path for name in ("src", "scripts") for path in (destination / name).rglob("*")
             if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
        directory.chmod(0o555)
    for name in ("src", "scripts"):
        (destination / name).chmod(0o555)
    destination.chmod(0o555)
    stats = {".": stat_identity(destination)}
    for name in ("src", "scripts"):
        for path in [destination / name, *(destination / name).rglob("*")]:
            stats[str(path.relative_to(destination))] = stat_identity(path)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project, text=True).strip()
    return {
        "source_root": str(destination), "source_files": files, "source_stats": stats,
        "source_commit": commit, "asset_aliases": aliases,
        "alias_scope": "trusted runner reads only; model terminal containers have no host mounts",
    }


def prepare(config_path, panel_path, output):
    config, output = read(config_path), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    required = (
        "project_root", "runtime_launcher", "native_python", "model_path",
        "model_manifest", "model_source_receipt", "reference_runtime",
        "backend_config", "task_source_root", "dependency_paths", "environment_admission_ref",
    )
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError("Preparation config lacks: " + ", ".join(missing))
    numerical = (Path(config["project_root"]) / "runs/v030-runtime-deps").resolve()
    if (not config["dependency_paths"]
            or Path(config["dependency_paths"][0]).resolve() != numerical):
        raise ValueError("The original numerical dependency overlay must precede harness dependencies")
    snapshot = freeze_snapshot(config["project_root"], output / "source")
    plan = {
        "version": VERSION, **copy.deepcopy(config), **snapshot,
        "panel_ref": native.ref(panel_path), "preparation_config": native.ref(config_path),
        "contract": copy.deepcopy(native.CONTRACT), "limits": copy.deepcopy(native.LIMITS),
        "phase_limits": PHASE_SECONDS, "max_residents": 4, "maximum_slots": 280,
        "maximum_actual_tokens": 140000000, "created_at": time.time(),
        "new_parameter_updates": 0, "new_backward_calls": 0,
        "model_retries": False, "zero_model_resource_retries": True,
        "automatic_successors": False, "admission_ref": None,
        "runtime_files": [
            native.ref(config["runtime_launcher"]),
            native.ref(Path(config["runtime_launcher"]).resolve().parent / "enter-namespace.sh"),
        ],
        "resource_modules": [
            native.ref(Path(config["project_root"]) / "artifacts/software-learning-v050/"
                       "resume-r6-source/scripts" / (name + ".py"))
            for name in ("software_learning_resources_v050r3", "software_learning_resources_v050r5")
        ],
    }
    plan_path = output / "preparation-plan.json"
    native.write_new(plan_path, plan)
    runner.validate_plan(plan_path, require_admission=False)
    return native.ref(plan_path)


def capture_panel(plan_path, output):
    """One tokenizer load, one planned first request per distinct task, zero generations."""
    plan, panel = runner.validate_plan(plan_path, require_admission=False)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(plan["model_path"], local_files_only=True)
    owner = native.MetadataOwner(tokenizer, model_manifest=plan["model_manifest"])
    rows = []
    for row in panel["slots"]:
        if row["repeat_index"] != 1:
            continue
        task = runner.task_for(plan, panel, row["task_id"])
        folder = output / row["slot_id"]
        result = native.collect_episode(
            owner=owner, row=row, panel_sha256=plan["panel_ref"]["sha256"], task=task,
            backend=runner.CaptureBackend(task), reference_runtime=plan["reference_runtime"],
            episode_folder=folder, initial_capture=lambda request, record: None)
        record = read(native.checked(result["native_input"]))
        result["fits"] = record["fits"]
        result_ref = native.write_new(folder / "capture-result.json", result)
        rows.append({
            "task_id": row["task_id"], "slot_id": row["slot_id"],
            "fits": record["fits"], "prompt_tokens": record["prompt_tokens"],
            "output_reservation": native.CONTRACT["max_output_tokens"], "capture": result_ref,
        })
        native.write(output / "progress.json", {
            "completed_tasks": len(rows), "fits": sum(row["fits"] for row in rows),
            "model_generations": 0,
        })
    if len(rows) != 200 or len({row["task_id"] for row in rows}) != 200:
        raise ValueError("Initial input inventory must contain all 200 distinct planned tasks")
    result = {
        "version": VERSION + "-initial-inputs", "source_plan": native.ref(plan_path),
        "panel_ref": plan["panel_ref"], "reference_runtime": plan["reference_runtime"],
        "contract": native.CONTRACT, "rows": rows, "passed": all(row["fits"] for row in rows),
        "tokenizer_loads": 1, "new_model_generations": 0, "new_model_loads": 0,
        "new_tool_executions": 0, "new_candidate_exports": 0, "new_grading_executions": 0,
        "scope": "actual initial SDK requests only; later conversation fit is not guaranteed",
    }
    native.write_new(output / "initial-inputs.json", result)
    return result


def seal_plan(preparation_plan, admission_path, output):
    plan, _ = runner.validate_plan(preparation_plan, require_admission=False)
    plan["admission_ref"] = native.ref(admission_path)
    plan["preparation_plan"] = native.ref(preparation_plan)
    plan["sealed_at"] = time.time()
    native.write_new(output, plan)
    runner.validate_plan(output, require_admission=True)
    return native.ref(output)


def query_gpus():
    result = subprocess.run([
        "nvidia-smi", "--query-gpu=index,uuid,name,memory.free,memory.total",
        "--format=csv,noheader,nounits",
    ], capture_output=True, text=True, timeout=30, check=True)
    cards = []
    for fields in csv.reader(result.stdout.splitlines()):
        if len(fields) != 5:
            raise ValueError("GPU observation has an unexpected field count")
        index, uuid, name, free, total = (field.strip() for field in fields)
        if not re.fullmatch(r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", uuid):
            raise ValueError("GPU observation lacks its full physical UUID")
        cards.append({"index": int(index), "uuid": uuid, "name": name,
                      "free_mib": int(free), "total_mib": int(total)})
    if len({card["index"] for card in cards}) != len(cards):
        raise ValueError("Duplicate GPU identity in one observation")
    return cards


def worker_command(plan, plan_path, slot_id, attempt_path, binding):
    root = Path(plan["source_root"])
    paths = [str(root / "src"), str(root), *plan["dependency_paths"]]
    environment = {
        "PYTHONPATH": ":".join(paths), "PYTHONDONTWRITEBYTECODE": "1",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True", "OPENHANDS_SUPPRESS_BANNER": "1",
        "CUDA_VISIBLE_DEVICES": binding["gpu_uuid"],
        "PROWORKSIM_HOST_GPU_DEVICES": str(binding["gpu_index"]),
        "PROWORKSIM_V053_GPU_BINDING": json.dumps(binding, sort_keys=True, separators=(",", ":")),
        "PYTORCH_CUDA_ALLOC_CONF": "backend:native", "PYTORCH_ALLOC_CONF": "backend:native",
    }
    return [
        plan["runtime_launcher"], "--write-project", "--gpu", str(binding["gpu_index"]),
        "/usr/bin/env", *(key + "=" + value for key, value in environment.items()),
        "/bin/sh", "-c", "cd " + shlex.quote(str(root)) + ' && exec "$@"', "v053-worker",
        plan["native_python"], "-B", "-m", "scripts.software_panel_run_v053",
        "worker", "--plan", str(Path(plan_path).resolve()), "--slot-id", slot_id,
        "--output", str(Path(attempt_path).resolve()),
    ]


def initial_state(panel, plan_ref, now, *, panel_sha256):
    return {
        "version": VERSION, "plan_ref": plan_ref, "panel_sha256": panel_sha256,
        "started_at": now, "updated_at": now, "status": "waiting_resources",
        "pause_reasons": [], "active": {},
        "slots": [{**copy.deepcopy(row), "status": "pending", "attempts": [], "R_code": None}
                  for row in panel["slots"]],
    }


def pending_slots(state, now):
    """Keep frozen order, including a cooling-down zero-model resource attempt."""
    result = []
    for slot in state["slots"]:
        if slot["status"] not in ("pending", "resource_wait"):
            continue
        if slot.get("next_retry_at", 0) > now:
            break
        result.append(slot)
    return result


def resource_wait_proven(report, attempt_path, exit_code, row):
    path = Path(attempt_path)
    receipt = report.get("resource_receipt", {})
    return (
        exit_code == 75 and report.get("status") == "resource_wait" and report.get("row") == row
        and report.get("loader_not_entered") is True
        and report.get("model_loader_entered") is False and report.get("resident_exists") is False
        and report.get("model_calls") == 0 and report.get("known_actual_tokens") == 0
        and report.get("fresh_process_resource_retry_allowed") is True
        and receipt.get("retryable") is True and receipt.get("loader_not_entered") is True
        and not (path / "model-entered.json").exists() and not (path / "resident").exists()
        and not (path / "episode").exists()
    )


def settle_attempt(slot, *, row, plan_ref, exit_code, now):
    attempt = slot["attempts"][-1]
    path = Path(attempt["path"])
    attempt.update(ended_at=now, exit_code=exit_code,
                   model_entered=(path / "model-entered.json").exists())
    report_path = path / "report.json"
    try:
        report = read(report_path) if report_path.is_file() else {}
    except (ValueError, OSError):
        slot.update(status="technical_unknown", R_code=None, failure_type="invalid_worker_receipt")
        return "invalid_worker_receipt"
    if report and report.get("source_plan") != plan_ref:
        slot.update(status="technical_unknown", R_code=None, failure_type="worker_plan_binding")
        return "worker_plan_binding"
    if resource_wait_proven(report, path, exit_code, row):
        attempt["resource_wait"] = True
        waits = sum(attempt.get("resource_wait") is True for attempt in slot["attempts"])
        delay = min(600, 60 * 2 ** min(waits - 1, 4))
        slot.update(status="resource_wait", R_code=None, next_retry_at=now + delay)
        attempt["report_ref"] = native.ref(report_path)
        return None
    verdict = report.get("verdict", {})
    if (report.get("status") == "complete" and report.get("row") == row
            and verdict.get("decision") == "continue"
            and type(report.get("R_code")) is int and report["R_code"] in (0, 1)
            and attempt["model_entered"]):
        slot.update(status="complete", R_code=report["R_code"],
                    failure_type=verdict.get("failure_type"))
        attempt["report_ref"] = native.ref(report_path)
        return None if exit_code == 0 else "nonzero_worker_exit_after_authoritative_closure"
    slot.update(status="technical_unknown", R_code=None,
                failure_type="worker_technical_unknown_or_unclosed")
    if report_path.exists():
        attempt["report_ref"] = native.ref(report_path)
    if (path / "interruption.json").exists():
        attempt["interruption_ref"] = native.ref(path / "interruption.json")
    return slot["failure_type"]


def guard_reason(attempt, phase, now):
    episode = phase.get("episode_started_at")
    if episode is not None and now - episode > native.LIMITS["hard_seconds"]:
        return "episode_hard_deadline"
    name = phase.get("phase", "boot")
    if name not in PHASE_SECONDS:
        return "unknown_worker_phase"
    if now - phase.get("at", attempt["started_at"]) > PHASE_SECONDS[name]:
        return name + "_deadline"
    return None


def verify_frozen_stats(plan, plan_path, plan_ref):
    if native.ref(plan_path) != plan_ref:
        raise ValueError("The sealed plan changed after supervisor entry")
    root = Path(plan["source_root"])
    for name, expected in plan["source_stats"].items():
        if stat_identity(root / name) != expected:
            raise ValueError("Frozen source identity changed: " + name)
    for reference in [*plan["runtime_files"], *plan["resource_modules"]]:
        native.checked(reference)


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=30)
        self.socket_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def docker_request(docker_host, method, path):
    if not docker_host.startswith("unix://"):
        raise ValueError("Use this experiment's explicit private Unix Docker socket")
    connection = UnixHTTPConnection(docker_host.removeprefix("unix://"))
    try:
        connection.request(method, path)
        response = connection.getresponse()
        content = response.read()
        if response.status == 404:
            return None
        if response.status >= 300:
            raise RuntimeError(f"Docker cleanup HTTP {response.status}: {content[:500]!r}")
        return json.loads(content) if content else None
    finally:
        connection.close()


def cleanup_containers(plan, slot_id, attempt_path):
    labels = {
        "proworksim.version": "software-panel-docker-v053-v1",
        "proworksim.slot_id": slot_id,
        "proworksim.worker_root": str(Path(attempt_path).resolve() / "backend"),
    }
    host = plan["backend_config"]["docker_host"]
    filters = json.dumps({"label": [key + "=" + value for key, value in labels.items()]})
    rows = docker_request(host, "GET", "/containers/json?" + urlencode({"all": 1, "filters": filters}))
    removed = []
    for row in rows or []:
        if (any(row.get("Labels", {}).get(key) != value for key, value in labels.items())
                or not re.fullmatch(r"[0-9a-f]{64}", row.get("Id", ""))):
            raise ValueError("Docker cleanup response did not match the exact owned episode labels")
        docker_request(host, "DELETE", "/containers/" + row["Id"] + "?force=1&v=0")
        removed.append(row["Id"])
    return {"labels": labels, "removed_container_ids": removed}


def pause(state, reason):
    state["status"] = "paused"
    if reason not in state["pause_reasons"]:
        state["pause_reasons"].append(reason)


def save_state(path, state):
    state["updated_at"] = time.time()
    native.write(path, state)


def signal_owned_process(process, number):
    """Only a Popen child launched with start_new_session is passed here."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, number)
    except ProcessLookupError:
        # The child may finish between poll and signal; settle its receipt next.
        pass


def supervise(plan_path, run_root):
    plan_path, run_root = Path(plan_path).resolve(), Path(run_root).resolve()
    plan, panel = runner.validate_plan(plan_path, require_admission=True)
    if (plan.get("version") != VERSION or plan.get("limits") != native.LIMITS
            or plan.get("phase_limits") != PHASE_SECONDS or plan.get("max_residents") != 4):
        raise ValueError("The frozen host phase/resource policy differs")
    run_root.mkdir(parents=True, exist_ok=True)
    lock = (run_root / "supervisor.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state_path, plan_ref = run_root / "state.json", native.ref(plan_path)
    if state_path.exists():
        state = read(state_path)
        if state["plan_ref"] != plan_ref:
            raise ValueError("An existing run root belongs to another frozen plan")
        if state["active"]:
            pause(state, "previous_supervisor_has_unresolved_active_workers")
            save_state(state_path, state)
            raise ValueError("Previous active workers must be reconciled without replay")
        if state["status"] == "complete":
            return 0
        if state["status"] == "paused":
            raise ValueError("A public system pause requires a separately identified continuation")
    else:
        state = initial_state(panel, plan_ref, time.time(), panel_sha256=plan["panel_ref"]["sha256"])
        save_state(state_path, state)
    rows = {row["slot_id"]: row for row in panel["slots"]}
    slots = {slot["slot_id"]: slot for slot in state["slots"]}
    processes = {}
    requested_signal = []
    previous_handlers = {}

    def signal_handler(number, frame):
        requested_signal.append(number)

    for number in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[number] = signal.signal(number, signal_handler)
    last_sample, last_stat_check = -float("inf"), -float("inf")
    try:
        while True:
            now = time.time()
            if requested_signal:
                pause(state, "supervisor_received_" + signal.Signals(requested_signal[0]).name)
                for slot_id, process in processes.items():
                    if process.poll() is None and "termination_requested_at" not in state["active"][slot_id]:
                        signal_owned_process(process, signal.SIGTERM)
                        state["active"][slot_id].update(
                            termination_requested_at=now, termination_reason="supervisor_signal")
            for slot_id, process in list(processes.items()):
                slot, active = slots[slot_id], state["active"][slot_id]
                attempt = slot["attempts"][-1]
                attempt["model_entered"] = (Path(attempt["path"]) / "model-entered.json").exists()
                active["model_entered"] = attempt["model_entered"]
                code = process.poll()
                if code is not None:
                    reason = settle_attempt(
                        slot, row=rows[slot_id], plan_ref=plan_ref, exit_code=code, now=now)
                    if reason:
                        pause(state, slot_id + ":" + reason)
                    try:
                        cleanup = cleanup_containers(plan, slot_id, attempt["path"])
                        native.write_new(Path(attempt["path"]).parent / (
                            Path(attempt["path"]).name + ".cleanup.json"), cleanup)
                    except Exception as error:
                        pause(state, slot_id + ":container_cleanup:" + str(error))
                    del processes[slot_id]
                    del state["active"][slot_id]
                    save_state(state_path, state)
                    continue
                phase_path = Path(attempt["path"]) / "phase.json"
                phase = read(phase_path) if phase_path.exists() else {}
                reason = guard_reason(attempt, phase, now)
                if reason and "termination_requested_at" not in active:
                    pause(state, slot_id + ":" + reason)
                    active.update(termination_requested_at=now, termination_reason=reason)
                    signal_owned_process(process, signal.SIGTERM)
                if ("sigkill_at" not in active
                        and now - active.get("termination_requested_at", now) > TERMINATION_GRACE_SECONDS):
                    signal_owned_process(process, signal.SIGKILL)
                    active["sigkill_at"] = now
            if state["status"] == "paused" and not processes:
                save_state(state_path, state)
                return 78
            if all(slot["status"] == "complete" for slot in state["slots"]):
                state["status"], state["completed_at"] = "complete", now
                save_state(state_path, state)
                return 0
            if state["status"] != "paused" and now - last_stat_check >= 30:
                try:
                    verify_frozen_stats(plan, plan_path, plan_ref)
                except Exception as error:
                    pause(state, "frozen_source_drift:" + str(error))
                last_stat_check = now
            ready = pending_slots(state, now)
            if (state["status"] != "paused" and ready and len(processes) < 4
                    and now - last_sample >= IDLE_POLL_SECONDS):
                try:
                    verify_frozen_stats(plan, plan_path, plan_ref)
                    observed = query_gpus()
                    with (run_root / "gpu-observations.jsonl").open("a") as stream:
                        stream.write(json.dumps({"at": now, "gpus": observed}) + "\n")
                    cards = resources.select_cards(
                        observed, excluded=[entry["gpu_index"] for entry in state["active"].values()])
                    for slot, card in zip(ready[:4 - len(processes)], cards, strict=False):
                        binding = resources.binding_for(card)
                        directory = run_root / "slots" / slot["slot_id"]
                        directory.mkdir(parents=True, exist_ok=True)
                        attempt_path = directory / f"attempt-{len(slot['attempts']) + 1:03d}"
                        if attempt_path.exists():
                            raise FileExistsError("Do not overwrite an existing resource/model attempt")
                        command = worker_command(plan, plan_path, slot["slot_id"], attempt_path, binding)
                        launcher_path = directory / (attempt_path.name + ".launcher.json")
                        native.write_new(launcher_path, {
                            "command": command, "binding": binding, "source_plan": plan_ref,
                            "slot_id": slot["slot_id"], "at": time.time(),
                        })
                        log_path = directory / (attempt_path.name + ".stdout.log")
                        with log_path.open("xb") as log:
                            process = subprocess.Popen(
                                command, cwd=plan["source_root"], stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
                        started = time.time()
                        slot["status"] = "running"
                        slot["attempts"].append({
                            "path": str(attempt_path), "pid": process.pid, "started_at": started,
                            "ended_at": None, "exit_code": None, "model_entered": False,
                            "gpu_index": binding["gpu_index"], "gpu_uuid": binding["gpu_uuid"],
                            "launcher_ref": native.ref(launcher_path), "stdout_path": str(log_path),
                        })
                        state["active"][slot["slot_id"]] = {
                            "pid": process.pid, "gpu_index": binding["gpu_index"],
                            "gpu_uuid": binding["gpu_uuid"], "attempt_path": str(attempt_path),
                            "started_at": started,
                        }
                        processes[slot["slot_id"]] = process
                        save_state(state_path, state)
                except Exception as error:
                    pause(state, "dispatch_system_fault:" + str(error))
                last_sample = now
            if state["status"] != "paused":
                state["status"] = "running" if processes else "waiting_resources"
            save_state(state_path, state)
            time.sleep(ACTIVE_POLL_SECONDS if processes else IDLE_POLL_SECONDS)
    except BaseException as error:
        pause(state, "supervisor_fault:" + type(error).__name__ + ":" + str(error))
        save_state(state_path, state)
        raise
    finally:
        # Unexpected host failure must not leave unmonitored model residents.
        for slot_id, process in processes.items():
            if process.poll() is None:
                signal_owned_process(process, signal.SIGTERM)
        for slot_id, process in processes.items():
            try:
                process.wait(timeout=TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                signal_owned_process(process, signal.SIGKILL)
                process.wait(timeout=10)
            slot = slots[slot_id]
            settle_attempt(slot, row=rows[slot_id], plan_ref=plan_ref,
                           exit_code=process.returncode, now=time.time())
            try:
                cleanup_containers(plan, slot_id, slot["attempts"][-1]["path"])
            except Exception as error:
                pause(state, slot_id + ":final_cleanup:" + str(error))
            state["active"].pop(slot_id, None)
        if processes:
            save_state(state_path, state)
        for number, handler in previous_handlers.items():
            signal.signal(number, handler)
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("--config", required=True)
    command.add_argument("--panel", required=True)
    command.add_argument("--output", required=True)
    command = commands.add_parser("capture-panel")
    command.add_argument("--plan", required=True)
    command.add_argument("--output", required=True)
    command = commands.add_parser("seal")
    command.add_argument("--plan", required=True)
    command.add_argument("--admission", required=True)
    command.add_argument("--output", required=True)
    command = commands.add_parser("supervise")
    command.add_argument("--plan", required=True)
    command.add_argument("--run-root", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        print(json.dumps(prepare(args.config, args.panel, args.output)))
        return 0
    if args.command == "capture-panel":
        result = capture_panel(args.plan, args.output)
        print(json.dumps({"passed": result["passed"], "tasks": len(result["rows"])}))
        return 0 if result["passed"] else 78
    if args.command == "seal":
        print(json.dumps(seal_plan(args.plan, args.admission, args.output)))
        return 0
    return supervise(args.plan, args.run_root)


if __name__ == "__main__":
    raise SystemExit(main())
