"""Frozen CAL1 inventory and one-pass host. No training or candidate retries."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from proworksim.online_training import sha_file
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import atomic_write, digest, json_bytes, read_json
from scripts.run_bounded_v022 import artifact_bytes, rss

VERSION = "software-calibration-host-v0.51"
GPU_PREFERENCE = [0, 1, 3, 4, 6, 7]
IDLE_POLICY = {"no_compute_processes": True, "utilization_percent": 0,
    "stable_seconds": 60, "scope": "new-worker admission"}
SOURCE = Path(__file__).resolve().parents[1]
ASSETS = SOURCE / "artifacts/software-calibration-v051"
MODEL = SOURCE / "runs/assets/models/Qwen3.5-9B-c20223623576"
PYTHON = SOURCE / "runs/v016-sdk/resident-venv/bin/python"
DEPS = SOURCE / "runs/v030-runtime-deps"
RESOURCE_SOURCE = SOURCE / "artifacts/software-learning-v050/resume-r6-source/scripts"
CONTRACT = {"context_limit": 131072, "max_output_tokens": 81920,
    "enable_thinking": True, "preserve_thinking": False, "temperature": .6,
    "top_p": .95, "top_k": 20, "repetition_penalty": 1.,
    "eos_token_ids": [248044, 248046], "pad_token_id": 248044,
    "max_generation_seconds": 7200}
LIMITS = {"max_residents": 4, "loading_seconds": 900, "reservation_seconds": 900,
    "generation_seconds": 7800, "scoring_seconds": 600, "boundary_seconds": 600,
    "rss_bytes": 64 * 1024**3, "artifact_bytes": 128 * 1024**3,
    "minimum_volume_free_bytes": 20 * 1024**3, "poll_seconds": 5}


def write(path, value):
    atomic_write(Path(path), json_bytes(value))


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha_file(path), "bytes": path.stat().st_size}


def checked(item):
    path = Path(item["path"])
    if ref(path) != item:
        raise ValueError("Frozen source changed: " + str(path))
    return path


def sealed(value):
    return {**value, "sha256": digest(json_bytes(value))}


def unseal(value):
    if value.get("sha256") != digest(json_bytes({k: v for k, v in value.items() if k != "sha256"})):
        raise ValueError("Frozen record seal changed")
    return value


def inventory(cases):
    if len(cases) != 24 or len({c["task_id"] for c in cases}) != 24:
        raise ValueError("Exactly 24 distinct preselected tasks required")
    rows = []
    for index, case in enumerate(cases):
        if case["ordinal"] != index or case["seed_proposal"] != 202610170511 + index:
            raise ValueError("Static task order/seed changed")
        arms = ["reference", "project"] if index % 2 == 0 else ["project", "reference"]
        for arm in arms:
            rows.append({"slot_id": f"cal1-{index + 1:02d}-{arm}", "task_id": case["task_id"],
                "ordinal": index, "seed": 202610170511 + index,
                "arm": arm, "worker": f"shard-{index // 6}",
                "prompt_tokens": len(case["input_ids"]),
                "maximum_tokens": len(case["input_ids"]) + CONTRACT["max_output_tokens"]})
    if sum(row["maximum_tokens"] for row in rows) != 3959768:
        raise ValueError("Static CAL1 token bound changed")
    return rows


def resource_modules(plan):
    modules = []
    for item in plan["resource_modules"]:
        path = checked(item)
        name = "scripts." + path.stem
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules.append(module)
    return tuple(modules)


def prepare(root):
    root = Path(root).resolve()
    if root.exists():
        raise FileExistsError("Use a fresh CAL1 inventory; no overwrite/replay")
    from proworksim.audit import code_identity
    identity = code_identity()
    if identity.get("code_dirty") is not False:
        raise ValueError("Commit CAL1 source/protocol before the first model work")
    cases_path = ASSETS / "sources/cal1-cases.json"
    rows = inventory(read_json(cases_path))
    root.mkdir(parents=True)
    snapshot = root / "source"
    sources = {}
    for folder in ("src", "scripts"):
        for path in sorted((SOURCE / folder).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(SOURCE)
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            sources[str(relative)] = sha_file(target)
    evidence = [ASSETS / "sources/cal1-source-proposal.json", ASSETS / "sources/stop-policy-correction.json",
        ASSETS / "sources/source-preparation-control.json", ASSETS / "sources/scoring-control-summary.json",
        ASSETS / "runtime-controls-summary.json", ASSETS / "runtime-sampling-cpu-controls.json",
        ASSETS / "host-controls.json", ASSETS / "loading-info-incremental-control.json", SOURCE / "docs/experiments/software-calibration-v051-protocol.md",
        SOURCE / "docs/experiments/software-calibration-v051-source-lock.json"]
    copied_evidence = []
    for index, path in enumerate(evidence):
        target = root / "evidence" / f"{index:02d}-{path.name}"
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, target)
        copied_evidence.append({"original": ref(path), "frozen_copy": ref(target)})
    plan = sealed({"version": VERSION, "created_at": time.time(), "source_commit": identity,
        "source_root": str(snapshot), "source_files": sources,
        "cases": ref(cases_path), "rows": rows, "contract": CONTRACT, "limits": LIMITS,
        "model_path": str(MODEL), "model_manifest": ref(MODEL / "proworksim-manifest.json"),
        "native_python": str(PYTHON), "runtime_dependency_path": str(DEPS),
        "scorer_source": str(ASSETS / "sources/lcb-code"),
        "evidence": copied_evidence,
        "resource_modules": [ref(RESOURCE_SOURCE / (name + ".py")) for name in
            ("software_learning_resources_v050r3", "software_learning_resources_v050r5")],
        "gpu_preference": GPU_PREFERENCE, "maximum_generations": 48,
        "maximum_actual_tokens": 3959768, "maximum_updates": 0, "maximum_backward_calls": 0,
        "new_qualification_calls": 0, "model_retries": False,
        "pre_model_resource_only_retries": True, "automatic_successors": False,
        "gate": "input/source/scoring integrity; no pass-rate or vendor-score threshold",
        "cal2_hold_launch_authorized_by_this_host": False})
    write(root / "plan.json", plan)
    return plan


def remaining_inventory(previous_root, previous_plan, supervisor, relinquishment, reschedule=None):
    """Select only untouched slots after explicitly identified resource stops."""
    previous_root = Path(previous_root).resolve()
    if supervisor.get("status") != "paused" or not supervisor.get("ended_at"):
        raise ValueError("Previous CAL1 host must finish closing its in-flight calls")
    if (relinquishment.get("kind") != "explicit_user_gpu_relinquishment"
            or relinquishment.get("requested_gpu") != 5
            or relinquishment.get("restart_or_resample_authorized") is not False
            or relinquishment.get("release_observation", {}).get("worker_process_exists") is not False):
        raise ValueError("Bound explicit GPU5 release receipt required")
    requested_stops = {relinquishment["pid"]: {"gpu": 5, "reason": "explicit_user_gpu5_relinquishment"}}
    if reschedule is not None:
        if (reschedule.get("kind") != "explicit_user_cancel_active_gpu_and_reschedule_when_idle"
                or reschedule.get("allowed_gpu_indices") != GPU_PREFERENCE
                or reschedule.get("max_residents") != 4
                or reschedule.get("no_started_request_replay") is not True
                or reschedule.get("supervisor_pid") != supervisor.get("observer_pid")
                or reschedule.get("stop_observation", {}).get("host_status") != "paused"
                or {row.get("pid") for row in reschedule.get("stop_observation", {}).get("workers", [])}
                    != {state["attempts"][-1]["pid"] for state in supervisor["states"].values()}
                or any(row.get("exists") is not False
                       for row in reschedule.get("stop_observation", {}).get("workers", []))):
            raise ValueError("Explicit all-worker stop and idle-rescheduling receipt required")
        for row in reschedule["active_workers_at_request"]:
            if row["pid"] in requested_stops or row["task"]["kind"] != "generation":
                raise ValueError("New stop must identify a distinct in-flight generation")
            requested_stops[row["pid"]] = {"gpu": row["gpu"], "reason": "supervisor_interrupted_or_fault"}
    interrupted = []
    for name, state in supervisor["states"].items():
        attempt = state["attempts"][-1]
        if attempt["pid"] in requested_stops:
            expected = requested_stops[attempt["pid"]]
            if attempt["gpu"]["index"] != expected["gpu"] or attempt.get("exit_code") != -15:
                raise ValueError("Explicit interruption identity or exit changed")
            stop = read_json(Path(attempt["output"]) / "host-stop.json")
            if stop.get("reason") != expected["reason"]:
                raise ValueError("Intentional stop receipt missing")
            interrupted.append(name)
        elif (attempt.get("exit_code") != 0
                or attempt.get("report", {}).get("guard", {}).get("passed") is not True
                or attempt["report"].get("status") not in {"complete", "paused_before_next_slot"}):
            raise ValueError("Independent worker did not close with its original guard")
    if len(interrupted) != len(requested_stops):
        raise ValueError("Every interrupted worker must match its explicit stop receipt")
    remaining, excluded, interrupted_slots = [], [], []
    for row in previous_plan["rows"]:
        directory = previous_root / "slots" / row["slot_id"]
        if directory.exists():
            if not (directory / "started.json").is_file():
                raise ValueError("Existing pre-generation slot needs separate diagnosis")
            if (directory / "generation.json").is_file():
                grade = directory / "grade/result.json"
                if not grade.is_file() or read_json(grade).get("pass_at_1") not in (0, 1):
                    raise ValueError("Existing completed output has unresolved scoring")
            else:
                if read_json(directory / "started.json").get("pid") not in requested_stops:
                    raise ValueError("Unexplained interruption outside relinquished worker")
                interrupted_slots.append(row["slot_id"])
            excluded.append(row["slot_id"])
        else:
            remaining.append(row)
    if not remaining or len(remaining) + len(excluded) != 48:
        raise ValueError("Original 48-slot partition changed or has no remaining work")
    if len(interrupted_slots) != len(requested_stops):
        raise ValueError("Each stopped in-flight request must remain unknown")
    return remaining, excluded


def prepare_continuation(root, previous_root):
    """Freeze a host-only continuation; model/scorer source stays byte-identical."""
    root, previous_root = Path(root).resolve(), Path(previous_root).resolve()
    if root.exists():
        raise FileExistsError("Continuation requires a new root")
    from proworksim.audit import code_identity
    identity = code_identity()
    if identity.get("code_dirty") is not False:
        raise ValueError("Commit the continuation before freezing it")
    previous = frozen(previous_root)
    if "continuation" in previous:
        raise ValueError("This bounded handoff only accepts the original CAL1 root")
    receipt = previous_root / "gpu5-relinquishment.json"
    reschedule_path = previous_root / "gpu-idle-reschedule.json"
    supervisor_path = previous_root / "supervisor.json"
    rows, excluded = remaining_inventory(previous_root, previous,
        read_json(supervisor_path), read_json(receipt), read_json(reschedule_path))
    root.mkdir(parents=True)
    snapshot = root / "source"
    shutil.copytree(previous["source_root"], snapshot)
    host_relative = "scripts/software_calibration_v051.py"
    shutil.copyfile(Path(__file__).resolve(), snapshot / host_relative)
    sources = {name: sha_file(snapshot / name) for name in previous["source_files"]}
    if any(value != previous["source_files"][name] for name, value in sources.items()
           if name != host_relative):
        raise ValueError("Continuation changed model-visible or scoring source")
    old_evidence = [ref(p) for p in sorted(previous_root.rglob("*"))
        if p.is_file() and "source" not in p.relative_to(previous_root).parts]
    continuation = {"kind": "explicit_idle_rescheduling_original_unstarted_only",
        "previous_root": str(previous_root), "previous_plan": ref(previous_root / "plan.json"),
        "previous_supervisor": ref(supervisor_path), "release_receipt": ref(receipt),
        "idle_rescheduling_receipt": ref(reschedule_path),
        "previous_evidence": old_evidence, "excluded_started_slots": excluded,
        "unchanged_source_except": [host_relative], "new_candidates": 0,
        "retries": 0, "old_uncertain_reservation_transferred": False}
    plan = sealed({**{k: v for k, v in previous.items() if k != "sha256"},
        "created_at": time.time(), "source_commit": identity,
        "source_root": str(snapshot), "source_files": sources,
        "rows": rows, "gpu_preference": GPU_PREFERENCE,
        "idle_policy": IDLE_POLICY,
        "maximum_generations": len(rows), "maximum_actual_tokens": sum(r["maximum_tokens"] for r in rows),
        "continuation": continuation})
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = unseal(read_json(Path(root) / "plan.json"))
    if plan["version"] != VERSION or plan["contract"] != CONTRACT or plan["limits"] != LIMITS:
        raise ValueError("CAL1 contract changed")
    for name, expected in plan["source_files"].items():
        if sha_file(Path(plan["source_root"]) / name) != expected:
            raise ValueError("CAL1 source snapshot changed: " + name)
    for item in [plan["cases"], plan["model_manifest"], *[e["frozen_copy"] for e in plan["evidence"]]]:
        checked(item)
    original_rows = inventory(read_json(Path(plan["cases"]["path"])))
    continuation = plan.get("continuation")
    if continuation:
        previous_path = checked(continuation["previous_plan"])
        previous = unseal(read_json(previous_path))
        for item in continuation["previous_evidence"]:
            checked(item)
        rows, excluded = remaining_inventory(continuation["previous_root"], previous,
            read_json(checked(continuation["previous_supervisor"])),
            read_json(checked(continuation["release_receipt"])),
            read_json(checked(continuation["idle_rescheduling_receipt"])))
        if (previous["rows"] != original_rows or rows != plan["rows"]
                or excluded != continuation["excluded_started_slots"]
                or plan["gpu_preference"] != GPU_PREFERENCE
                or plan.get("idle_policy") != IDLE_POLICY
                or plan["maximum_generations"] != len(rows)
                or plan["maximum_actual_tokens"] != sum(r["maximum_tokens"] for r in rows)
                or any(value != previous["source_files"][name] for name, value in plan["source_files"].items()
                    if name != "scripts/software_calibration_v051.py")):
            raise ValueError("Original-inventory handoff binding changed")
    elif original_rows != plan["rows"]:
        raise ValueError("CAL1 fixed inventory changed")
    return plan


def ledger(root, rows):
    complete, attempted, actual, uncertain, outcomes = 0, 0, 0, 0, []
    for row in rows:
        directory = Path(root) / "slots" / row["slot_id"]
        start, result = directory / "started.json", directory / "generation.json"
        if result.exists():
            data = read_json(result)
            usage = data["usage"]["total_tokens"]
            if not 0 < usage <= row["maximum_tokens"]:
                raise ValueError("Generation usage escaped its frozen bound")
            complete += 1
            attempted += 1
            actual += usage
        elif start.exists():
            attempted += 1
            uncertain += row["maximum_tokens"]
        grade = directory / "grade/result.json"
        outcomes.append({"slot_id": row["slot_id"], "generation_complete": result.exists(),
            "pass_at_1": read_json(grade).get("pass_at_1") if grade.exists() else None})
    return {"complete_generations": complete, "started_generations": attempted,
        "known_actual_tokens": actual, "uncertain_reservation_tokens": uncertain,
        "complete_actual_tokens": actual if uncertain == 0 else None,
        "ledger_tokens": actual + uncertain, "outcomes": outcomes,
        "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0}


def task(output, kind, slot_id=None):
    write(Path(output) / "task.json", {"kind": kind, "slot_id": slot_id,
        "started_at": time.time(), "pid": os.getpid()})


def worker(root, name, attempt):
    root, output = Path(root).resolve(), Path(attempt).resolve()
    plan = frozen(root)
    if name not in {r["worker"] for r in plan["rows"]} or output.exists():
        raise ValueError("Fresh declared worker attempt required")
    if Path(sys.executable).resolve() != Path(plan["native_python"]).resolve():
        raise ValueError("Use the pinned native interpreter")
    output.mkdir(parents=True)
    res, startup = resource_modules(plan)
    binding = res.binding_from_env()
    task(output, "reservation")
    try:
        startup.acquire_startup_cache(output / "startup", binding,
            identity={"plan": ref(root / "plan.json"), "worker": name})
    except startup.StartupResourceUnavailable:
        write(output / "report.json", {"status": "pre_model_resource_unavailable",
            "model_loader_entered": False, "generation_calls": 0})
        return 75
    task(output, "loading")
    from proworksim.software_calibration_runtime_v051 import load_actor, prepare_native_input
    from proworksim.software_calibration_scoring_v051 import score_cal1_candidate
    rows = [row for row in plan["rows"] if row["worker"] == name]
    owner = load_actor(plan["model_path"], manifest=plan["model_manifest"]["path"],
        contract=plan["contract"], path=rows[0]["arm"], output=output / "resident")
    owner.begin_window("v051-cal1-" + name)
    cases = read_json(Path(plan["cases"]["path"]))
    completed = []
    for row in rows:
        if (root / "pause.json").exists():
            break
        task(output, "boundary", row["slot_id"])
        directory = root / "slots" / row["slot_id"]
        directory.mkdir(parents=True, exist_ok=False)
        case = cases[row["ordinal"]]
        owner.select_path(row["arm"])
        owner.reseed(row["seed"], label=row["slot_id"])
        request = {"model": "Qwen3.5-9B", "messages": case["messages"],
            "temperature": CONTRACT["temperature"], "max_tokens": CONTRACT["max_output_tokens"]}
        native = prepare_native_input(owner.tokenizer, request, plan["contract"])
        if (native["input_ids"] != case["input_ids"]
                or native["rendered_prompt"] != case["rendered_prompt"]):
            raise ValueError("Actual native input differs from preselected upstream input")
        write(directory / "native-input.json", native)
        write(directory / "started.json", {"row": row, "started_at": time.time(),
            "native_input": ref(directory / "native-input.json"), "pid": os.getpid()})
        task(output, "generation", row["slot_id"])
        result = owner.generate_native(native)
        write(directory / "generation.json", result)
        task(output, "scoring", row["slot_id"])
        grade = score_cal1_candidate(result["raw_generated_text"], case["evaluation_sample"],
            source_root=plan["scorer_source"], run_root=directory / "grade", python_executable=plan["native_python"])
        completed.append(row["slot_id"])
        if grade["status"] == "technical_unknown":
            write(root / "pause.json", {"kind": "scoring_integrity_unresolved", "slot_id": row["slot_id"],
                "grade": ref(directory / "grade/result.json"), "at": time.time()})
            break
    task(output, "boundary")
    guard = owner.verify_evaluation_guard()
    write(output / "report.json", {"version": VERSION,
        "status": "complete" if len(completed) == len(rows) else "paused_before_next_slot",
        "completed_slots": completed, "guard": guard, "source_plan": ref(root / "plan.json")})
    return 0


def supervise(root):
    root = Path(root).resolve()
    plan = frozen(root)
    if (root / "supervisor.json").exists():
        raise FileExistsError("Started inventory cannot be automatically replayed")
    res, _ = resource_modules(plan)
    states = {name: {"status": "not_started", "attempts": []}
        for name in dict.fromkeys(row["worker"] for row in plan["rows"])}
    summary = {"version": VERSION, "status": "waiting", "started_at": time.time(),
        "observer_pid": os.getpid(), "plan": ref(root / "plan.json"), "states": states}
    active, streams, guards, idle_history = {}, {}, {}, {}

    def publish():
        summary.update(observed_at=time.time(), ledger=ledger(root, plan["rows"]),
            gpu_worker_seconds=sum(a.get("seconds", time.time() - a["started_at"])
                for s in states.values() for a in s["attempts"]))
        write(root / "supervisor.json", summary)

    def pause(reason, detail):
        if not (root / "pause.json").exists():
            write(root / "pause.json", {"kind": reason, "detail": detail, "at": time.time()})

    def close(name, reason=None):
        process = active.pop(name)
        a = states[name]["attempts"][-1]
        if process.poll() is None:
            write(Path(a["output"]) / "host-stop.json", {"reason": reason, "at": time.time(),
                "target_pid": process.pid, "identity": worker_identity(process.pid)})
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
        result_path = Path(a["output"]) / "report.json"
        result = read_json(result_path) if result_path.exists() else {}
        a.update(ended_at=time.time(), seconds=time.time() - a["started_at"],
            exit_code=process.returncode, reason=reason, report=result)
        streams.pop(name).close()
        guards.pop(name)
        if reason is None and process.returncode == 75 and result == {"status": "pre_model_resource_unavailable",
                "model_loader_entered": False, "generation_calls": 0}:
            states[name]["status"] = "not_started"
        elif (process.returncode == 0 and reason is None and result.get("status") == "complete"
                and result.get("completed_slots") == [r["slot_id"] for r in plan["rows"] if r["worker"] == name]
                and result.get("guard", {}).get("passed") is True
                and result.get("source_plan") == ref(root / "plan.json")):
            states[name]["status"] = "complete"
        else:
            states[name]["status"] = "stopped"
            pause("execution_or_measurement_pause", {"worker": name, "attempt": a})

    def receive(signum, _frame):
        raise InterruptedError("host received signal " + str(signum))

    signal.signal(signal.SIGTERM, receive)
    signal.signal(signal.SIGINT, receive)
    publish()
    try:
        while True:
            for name, process in list(active.items()):
                if process.poll() is not None:
                    close(name)
            if active:
                with ThreadPoolExecutor(max_workers=len(active)) as pool:
                    futures = {name: pool.submit(target_resources,
                        states[name]["attempts"][-1]["gpu"]["index"], worker_pid=process.pid)
                        for name, process in active.items()}
                    for name, future in futures.items():
                        sample = future.result()
                        process, a = active[name], states[name]["attempts"][-1]
                        if process.poll() is not None:
                            close(name)
                            continue
                        verdict = guards[name].observe(sample, time.time(), process.pid,
                            a["gpu"]["index"], own_memory_limit_mib=None)
                        write(Path(a["output"]).parent / (Path(a["output"]).name + "-telemetry.json"), verdict)
                        reason = verdict["stop_reason"]
                        current_path = Path(a["output"]) / "task.json"
                        current = read_json(current_path) if current_path.exists() else {"kind": "loading", "started_at": a["started_at"]}
                        cap = LIMITS.get(current["kind"] + "_seconds")
                        if cap is None or time.time() - current["started_at"] >= cap:
                            reason = reason or "task_deadline"
                        if rss(process.pid) > LIMITS["rss_bytes"]:
                            reason = reason or "host_rss_budget"
                        if reason:
                            close(name, reason)
            if artifact_bytes(root) > LIMITS["artifact_bytes"]:
                pause("artifact_budget", {})
                for name in list(active):
                    close(name, "artifact_budget")
            if not (root / "pause.json").exists() and len(active) < LIMITS["max_residents"]:
                if shutil.disk_usage(root).free < LIMITS["minimum_volume_free_bytes"]:
                    pause("volume_reserve", {})
                else:
                    sample = target_resources(",".join(map(str, plan["gpu_preference"])), worker_pid=os.getpid())
                    write(root / "admission-latest.json", sample)
                    cards = res.available_cards(plan, sample,
                        excluded=[states[n]["attempts"][-1]["gpu"]["index"] for n in active])
                    if plan.get("idle_policy"):
                        cards = idle_ready_cards(cards, idle_history, now=time.time())
                        write(root / "idle-gpu-status.json", {"policy": IDLE_POLICY,
                            "observed_at": time.time(), "allowed_gpu_indices": plan["gpu_preference"],
                            "idle_since": idle_history, "ready_gpu_indices": [c["index"] for c in cards]})
                    pending = [n for n, s in states.items() if s["status"] == "not_started"]
                    for name, card in zip(pending[:LIMITS["max_residents"] - len(active)], cards):
                        output = root / name / f"attempt-{len(states[name]['attempts']) + 1:03d}"
                        output.parent.mkdir(parents=True, exist_ok=True)
                        binding = res.launch_target(card)
                        env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(card["index"]),
                            "TOKENIZERS_PARALLELISM": "false", "OMP_NUM_THREADS": "8", "MKL_NUM_THREADS": "8",
                            "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1",
                            "TRANSFORMERS_OFFLINE": "1", "PYTHONPATH": os.pathsep.join([
                                plan["runtime_dependency_path"], str(Path(plan["source_root"]) / "src"), plan["source_root"]])}
                        env.pop("PROWORKSIM_REPLICA_GPUS", None)
                        env = res.worker_env(env, binding)
                        command = [plan["native_python"], "-m", "scripts.software_calibration_v051", "worker",
                            "--root", str(root), "--worker", name, "--attempt", str(output)]
                        stream = output.with_suffix(".log").open("wb")
                        launched = time.time()
                        process = subprocess.Popen(command, cwd=plan["source_root"], env=env,
                            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        a = {"started_at": launched, "pid": process.pid, "output": str(output),
                            "gpu": card, "binding": binding, "command": command, "identity": identity}
                        states[name]["attempts"].append(a)
                        states[name]["status"] = "running"
                        active[name], streams[name] = process, stream
                        guards[name] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        write(output.with_suffix(".launch.json"), a)
            if not active and ((root / "pause.json").exists() or all(s["status"] == "complete" for s in states.values())):
                break
            summary["status"] = "running" if active else "waiting"
            publish()
            time.sleep(LIMITS["poll_seconds"])
    except BaseException as error:
        pause("supervisor_interrupted_or_fault", {"type": type(error).__name__, "message": str(error)})
        for name in list(active):
            close(name, "supervisor_interrupted_or_fault")
        raise
    finally:
        summary.update(status="complete" if all(s["status"] == "complete" for s in states.values()) else "paused",
            ended_at=time.time())
        publish()
    return summary


def idle_ready_cards(cards, history, *, now):
    """A new process may start only on an unoccupied, steadily idle allowed GPU."""
    eligible = {str(c["index"]): c for c in cards
        if c["index"] in GPU_PREFERENCE and c.get("shared") is False
        and c.get("utilization_percent") == 0}
    for key in set(history) - set(eligible):
        del history[key]
    ready = []
    for key, card in eligible.items():
        if key not in history or history[key]["uuid"] != card["uuid"]:
            history[key] = {"uuid": card["uuid"], "first_seen_idle_at": now}
        if now - history[key]["first_seen_idle_at"] >= IDLE_POLICY["stable_seconds"]:
            ready.append(card)
    return ready


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "prepare-continuation", "supervise", "worker"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--worker")
    parser.add_argument("--attempt", type=Path)
    parser.add_argument("--previous-root", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.root)
    elif args.command == "prepare-continuation":
        if args.previous_root is None:
            parser.error("--previous-root required for continuation")
        prepare_continuation(args.root, args.previous_root)
    elif args.command == "supervise":
        supervise(args.root)
    else:
        raise SystemExit(worker(args.root, args.worker, args.attempt))


if __name__ == "__main__":
    main()
