"""Wait for a released A100, then run the independent N and E experiments once.

No old P1 budget is reused. N completion/qualification is never an E gate.
This is a fixed two-line supervisor, not a retry/configuration search queue.
"""

import argparse
from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.storage import atomic_write, digest, json_bytes, read_json

VERSION = "independent-n-e-supervisor-v0.21"
LIMITS = {"gpu_count": 1, "N_gpu_seconds": 1200, "E_gpu_seconds": 2400,
          "task_seconds": 900, "host_rss_bytes": 64 * 1024**3,
          "artifact_bytes": 5 * 1024**3, "gpu_process_memory_mib": 73728,
          "minimum_free_gpu_mib": 78000, "model_api_calls": 0, "optimizer_steps": 0,
          "shutdown_reserve_seconds": 30}
GPU_POOL = list(range(8))
SOURCE = Path(__file__).resolve().parents[1]


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def write(path, value):
    atomic_write(Path(path), json_bytes(value))


def read(path):
    return read_json(Path(path)) if Path(path).exists() else None


def checked(ref):
    path = Path(ref["path"])
    if reference(path) != ref:
        raise ValueError("Frozen artifact reference changed")
    return path


def validate_plan(plan):
    if (plan.get("version") != VERSION or plan.get("limits") != LIMITS
            or plan.get("gpu_pool") != GPU_POOL or plan.get("order") != ["N", "E"]
            or plan.get("runtime") != "candidate-runtime-v0.20.1"
            or plan.get("allow_parameter_updates") is not False
            or plan.get("automatic_successors") != []):
        raise ValueError("The N/E declaration differs from its bounded authorization")
    for key in ("N_prior_plan", "N_saved_response", "N_saved_numeric", "E_catalog"):
        checked(plan[key])
    prior_path = checked(plan["N_prior_plan"])
    if prior_path.name != "plan.json":
        raise ValueError("N prior plan must be its original run plan.json")
    prior_numeric = prior_path.parent / "numerical.json"
    if reference(prior_numeric) != plan["N_saved_numeric"]:
        raise ValueError("N numeric reference does not belong to the declared prior run")
    numeric = read_json(prior_numeric)
    if len(numeric.get("rows", [])) != 1:
        raise ValueError("N requires the one closed archived numerical request")
    response = prior_path.parent / "resident/calls" / (numeric["rows"][0]["response_id"] + ".json")
    if reference(response) != plan["N_saved_response"]:
        raise ValueError("N response reference does not belong to its archived numerical result")
    original = read_json(prior_path)
    if original["runtime_profile"]["version"] != plan["runtime"]:
        raise ValueError("Use the original existing numerical configuration")
    from proworksim.templates.retail_collaboration_v021 import registry
    catalog = read_json(checked(plan["E_catalog"]))
    if catalog != registry() or len(catalog["situations"]) != 6:
        raise ValueError("The six E situations changed before launch")


def resources():
    result = {"time": time.time()}
    for key, args in (
        ("gpus", ["--query-gpu=index,uuid,name,memory.free,memory.total,utilization.gpu"]),
        ("processes", ["--query-compute-apps=gpu_uuid,pid,used_gpu_memory,process_name"]),
    ):
        try:
            done = subprocess.run(["nvidia-smi", *args, "--format=csv,noheader,nounits"],
                                  text=True, capture_output=True, timeout=10)
            result[key] = {"returncode": done.returncode, "stdout": done.stdout, "stderr": done.stderr}
        except (OSError, subprocess.TimeoutExpired) as error:
            result[key] = {"returncode": None, "stdout": "", "stderr": str(error)}
    return result


def released_cards(sample):
    if any(sample.get(k, {}).get("returncode") != 0 for k in ("gpus", "processes")):
        return []
    occupied = set()
    for line in sample["processes"]["stdout"].splitlines():
        fields = [s.strip() for s in line.split(",", 3)]
        if len(fields) != 4:
            return []
        occupied.add(fields[0])
    ready = []
    try:
        for line in sample["gpus"]["stdout"].splitlines():
            i, uuid, name, free, total, util = [s.strip() for s in line.split(",")]
            free, total, util = float(free), float(total), float(util)
            if (int(i) in GPU_POOL and "A100" in name and uuid not in occupied
                    and all(math.isfinite(x) for x in (free, total, util))
                    and free >= LIMITS["minimum_free_gpu_mib"] and total >= 81920 and util <= 5):
                ready.append(int(i))
    except ValueError:
        return []
    return sorted(ready)


@contextmanager
def lock(output):
    with (output / "observer.lock").open("a+") as file:
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("One live supervisor already owns this declared run") from error
        try:
            yield
        finally:
            fcntl.flock(file, fcntl.LOCK_UN)


def command(plan, name, destination):
    if name == "N":
        return [sys.executable, "-m", "scripts.numeric_paths_v021", "--prior-run",
                str(checked(plan["N_prior_plan"]).parent), "--output", str(destination)]
    if name == "E":
        return [sys.executable, "-m", "scripts.evaluate_work_v021", "--plan",
                str(plan["plan_path"]), "--output", str(destination)]
    raise ValueError("No third line or configuration is permitted")


def stop_owned(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def prelaunch_boundary(state, output):
    used = sum(job.get("elapsed_gpu_seconds", 0) for job in state["jobs"].values())
    remaining = LIMITS["N_gpu_seconds"] + LIMITS["E_gpu_seconds"] - used
    if remaining <= 0:
        return "total_budget_exhausted", remaining
    if sum(p.stat().st_size for p in output.rglob("*") if p.is_file()) >= LIMITS["artifact_bytes"]:
        return "total_artifact_limit", remaining
    if remaining <= LIMITS["shutdown_reserve_seconds"]:
        return "insufficient_shutdown_reserve", remaining
    return None, remaining


def run_line(plan, state, name, gpu, output):
    job = state["jobs"][name]
    if job.get("attempted"):
        raise ValueError("An attempted line is never restarted or replaced")
    if code_identity() != state["source"]:
        raise ValueError("Source changed before a model launch")
    if reference(plan["plan_path"]) != state["plan"]:
        raise ValueError("The original plan changed while waiting; no model launch")
    destination = output / name
    if destination.exists():
        raise FileExistsError("An independent new experiment directory is required")
    argv = command(plan, name, destination)
    boundary, remaining = prelaunch_boundary(state, output)
    if boundary is not None:
        job.update(status="not_started_" + boundary, attempted=False)
        write(output / "state.json", state)
        return
    started = time.time()
    job.update(status="launch_intent", attempted=True, command=argv, gpu=gpu,
               started_at=started, gpu_budget_seconds=min(LIMITS[name + "_gpu_seconds"], remaining),
               shutdown_reserve_seconds=LIMITS["shutdown_reserve_seconds"],
               stop_after_seconds=min(LIMITS[name + "_gpu_seconds"], remaining) - LIMITS["shutdown_reserve_seconds"])
    write(output / "state.json", state)
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu), "HF_HUB_OFFLINE": "1",
           "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"}
    env.pop("PROWORKSIM_REPLICA_GPUS", None)
    with (output / f"{name}.log").open("x") as log:
        process = subprocess.Popen(argv, cwd=SOURCE, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        job.update(status="running", pid=process.pid)
        write(output / "state.json", state)
        reason = None
        try:
            while process.poll() is None:
                now = time.time()
                task = read(destination / "task.json") or {"task": "startup", "started_at": started}
                try:
                    rss = int(Path(f"/proc/{process.pid}/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
                except FileNotFoundError:
                    rss = 0
                bytes_ = sum(p.stat().st_size for p in output.rglob("*") if p.is_file())
                sample = resources()
                if any(sample[k]["returncode"] != 0 for k in ("gpus", "processes")):
                    reason = "resource_query_failed"
                own = 0.0
                for line in sample["processes"]["stdout"].splitlines():
                    fields = [x.strip() for x in line.split(",", 3)]
                    if len(fields) == 4 and fields[1] == str(process.pid):
                        value = float(fields[2])
                        if not math.isfinite(value):
                            raise ValueError("Unknown actual GPU memory observation")
                        own += value
                if now - started >= job["stop_after_seconds"]:
                    reason = "line_time_limit"
                elif now - task["started_at"] >= LIMITS["task_seconds"] - LIMITS["shutdown_reserve_seconds"]:
                    reason = "single_task_limit"
                elif rss > LIMITS["host_rss_bytes"]:
                    reason = "host_memory_limit"
                elif bytes_ > LIMITS["artifact_bytes"]:
                    reason = "total_artifact_limit"
                elif own > LIMITS["gpu_process_memory_mib"]:
                    reason = "own_gpu_memory_limit"
                with (output / f"{name}-resources.jsonl").open("a") as stream:
                    stream.write(json.dumps({"sample": sample, "task": task, "rss_bytes": rss,
                        "artifact_bytes": bytes_, "own_gpu_memory_mib": own}, ensure_ascii=False) + "\n")
                if reason:
                    stop_owned(process)
                    break
                time.sleep(2)
        except BaseException as error:
            reason = reason or "supervisor_error:" + type(error).__name__
            stop_owned(process)
            raise
        finally:
            code = process.wait()
            job.update(status="complete" if code == 0 else "stopped", exit_code=code,
                       ended_at=time.time(), elapsed_gpu_seconds=time.time() - started,
                       stop_reason=reason, actual_report=reference(destination / "report.json")
                       if (destination / "report.json").exists() else None)
            write(output / "state.json", state)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt("Supervisor interrupted; only its owned active child is stopped")
    signal.signal(signal.SIGTERM, interrupted)
    plan = read_json(a.plan)
    validate_plan(plan)
    source = code_identity()
    if source["code_dirty"]:
        raise ValueError("Freeze the source before persistent waiting")
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan_ref = reference(a.plan)
    with lock(out):
        state = read(out / "state.json")
        if state:
            if state["plan"] != plan_ref or state["source"] != source:
                raise ValueError("Restart must retain original source and declaration")
            # Orphan recovery is read-only/manual; never duplicate an uncertain launch.
            if any(j.get("attempted") for j in state["jobs"].values()):
                raise ValueError("This supervisor has attempted a line; observe its records, do not restart")
        else:
            state = {"version": VERSION, "status": "waiting_released_gpu", "source": source,
                     "plan": plan_ref, "created_at": time.time(), "observer_pid": os.getpid(),
                     "jobs": {name: {"status": "pending", "attempted": False} for name in ("N", "E")}}
            write(out / "plan.json", plan)
            write(out / "state.json", state)
        internal = {**plan, "plan_path": str(a.plan.resolve())}
        try:
            for name in ("N", "E"):
                boundary, _ = prelaunch_boundary(state, out)
                if boundary is not None:
                    state["jobs"][name].update(status="not_started_" + boundary, attempted=False)
                    write(out / "state.json", state)
                    continue
                state.update(status="waiting_released_gpu", waiting_line=name)
                while True:
                    sample = resources()
                    ready = released_cards(sample)
                    if state.get("selected_gpu") is not None:
                        ready = [i for i in ready if i == state["selected_gpu"]]
                    state.update(observed_at=time.time(), last_resources=sample,
                                 ready_cards=ready, observer_pid=os.getpid())
                    write(out / "state.json", state)
                    if ready:
                        # A second fresh observation closes a stale readiness gap.
                        second = resources()
                        ready = [i for i in ready if i in released_cards(second)]
                        if ready:
                            state["jobs"][name]["admission_resources"] = second
                            state["selected_gpu"] = ready[0]
                            break
                    time.sleep(5)
                state["status"] = "running_" + name
                run_line(internal, state, name, ready[0], out)
                # Qualification/mismatch or a model failure in N does not gate E.
            state["status"] = "closed"
            state["total_gpu_seconds"] = sum(j.get("elapsed_gpu_seconds", 0) for j in state["jobs"].values())
            state["automatic_training_started"] = False
        except BaseException as error:
            state.update(status="supervisor_stopped", error={"type": type(error).__name__, "message": str(error)})
            raise
        finally:
            state["last_written_at"] = time.time()
            write(out / "state.json", state)
            try:
                from scripts.summarize_ne_v021 import summarize
                summarize(out)
                state["terminal_summary"] = reference(out / "summary.json")
            except Exception as report_error:
                state["terminal_summary_error"] = {"type": type(report_error).__name__, "message": str(report_error)}
            write(out / "state.json", state)


if __name__ == "__main__":
    main()
