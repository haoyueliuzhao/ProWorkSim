"""Resume only unchanged post-update work, with private data-volume temporary storage."""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import read_json
from scripts.composition_evidence_v025 import checked
from scripts.evaluate_work_v022 import reference, write
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_composition_recovery_v025 import card_uuid, finish, terminal_sample
from scripts.run_credit_v024 import ready_cards
from scripts.run_ne_v021 import lock, read, resources

VERSION = "postupdate-evaluation-resume-v0.25-r2"
ORDER = ("confirm_base", "next_base")
TASK_CAPS = {"loading": 900, "episode": 1200, "boundary": 600}


def validate(plan):
    prior = read_json(checked(plan["prior_supervisor"]))
    prior_plan = read_json(checked(plan["worker_plan"]))
    marker = read_json(checked(plan["base_marker"]))
    saved = read_json(checked(plan["checkpoint"]))
    checked(saved["state"])
    failed = read_json(checked(plan["failed_confirmation"]))
    progress = read_json(checked(plan["failed_progress"]))
    prior_root = Path(plan["prior_run"]).resolve()
    if (
        checked(plan["prior_supervisor"]).parent != prior_root
        or Path(plan["run_root"]).resolve() == prior_root
    ):
        raise ValueError("Use a new attempt directory without changing the prior run")
    if (
        prior["status"] != "closed_with_incomplete_stages"
        or not prior.get("ended_at")
        or prior["stage_statuses"]
        != {
            "train_base": "complete",
            "confirm_base": "stopped",
            "next_base": "not_started_endpoint_unavailable",
        }
        or failed["status"] != "interrupted_or_error"
        or len(progress) != 1
        or progress[0]["status"] != "interrupted_or_unassessed"
        or progress[0].get("assessment", {}).get("eligible") is not False
    ):
        raise ValueError("Resume only the one preserved unknown evaluation after complete training")
    if (
        plan["version"] != VERSION
        or plan["max_concurrent_model_instances"] != 1
        or plan["max_new_actor_steps"] != 0
        or plan["max_new_critic_steps"] != 0
        or plan["model_api_calls"] != 0
        or plan["max_new_episodes"] != 14
        or plan["automatic_recovery"] is not False
        or plan["task_caps"] != TASK_CAPS
    ):
        raise ValueError("Only confirmation and continuation are authorized; no further training")
    if (
        marker["checkpoint"] != plan["checkpoint"]
        or marker["source"] != plan["worker_source"]
        or marker["source"] != prior["source"]
        or marker["label"] != "base"
        or marker["actor_identity"] != saved["actor_identity"]
        or saved["actor_steps"] != 3
        or saved["critic_steps"] != 3
        or saved["serialized_reload_exact"] is not True
    ):
        raise ValueError(
            "Keep the exact saved post-update endpoint and its original source identity"
        )
    if (
        plan["worker_plan"] != prior["plan"]
        or Path(plan["worker_checkout"]).resolve() != checked(plan["worker_plan"]).parents[2]
    ):
        raise ValueError("Execute the original frozen worker with its original frozen plan")
    for stage in ORDER:
        spent = read_json(prior_root / stage / "state.json").get("elapsed_gpu_seconds", 0.0)
        expected = prior_plan["resource_caps"][stage] - spent
        if expected <= 30 or not math.isclose(
            plan["resource_caps"].get(stage, -1), expected, abs_tol=1e-6, rel_tol=0
        ):
            raise ValueError("Evaluation budgets must subtract previous actual stage usage")
    if set(plan["resource_caps"]) != set(ORDER):
        raise ValueError("No training stage in an evaluation recovery")
    if (
        plan["previous_gpu_seconds"] != prior["cumulative_terminated_gpu_seconds"]
        or plan["internal_gpu_seconds"] != sum(plan["resource_caps"].values())
        or plan["wall_deadline_at"] != prior["started_at"] + prior_plan["max_wall_seconds"]
        or plan["minimum_temp_free_bytes"] != 1024**3
    ):
        raise ValueError(
            "Keep cumulative costs, the original wall deadline and finite disk reserve"
        )
    return marker


def worker_environment(plan, root, gpu):
    worker = Path(plan["worker_checkout"]).resolve()
    temp = root / "tmp"
    env = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": str(gpu),
        "PYTHONHASHSEED": read_json(checked(plan["worker_plan"]))["python_hash_seed"],
        "PYTHONPATH": str(worker / "src") + os.pathsep + str(worker),
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "TMPDIR": str(temp),
        "TMP": str(temp),
        "TEMP": str(temp),
    }
    env.pop("PROWORKSIM_REPLICA_GPUS", None)
    return env


def preflight(plan, root):
    """The actual frozen SQL executor must create and remove its private database."""
    temp = root / "tmp"
    temp.mkdir(mode=0o700)
    if temp.stat().st_dev == Path("/tmp").stat().st_dev:
        raise ValueError(
            "Use a different data volume from the exhausted system temporary directory"
        )
    if shutil.disk_usage(temp).free < plan["minimum_temp_free_bytes"]:
        raise ValueError("Insufficient free bytes on the experiment temporary volume")
    code = """import json, pathlib, tempfile
from proworksim.audit import code_identity
from proworksim.domains.executable_project import execute
result = execute(code={"models":[{"name":"probe", "sql":"SELECT 1 AS x"}], "config":{"exports":["probe"]}})
assert result["status"] == "success" and result["tables"]["probe"]["rows"] == [[1]]
print(json.dumps({"source":code_identity(), "temporary_directory":tempfile.gettempdir(), "sql_status":result["status"], "database_file_created":result["database"]["file_created"]}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=plan["worker_checkout"],
        env=worker_environment(plan, root, ""),
        capture_output=True,
        text=True,
        timeout=90,
        check=True,
    )
    proof = json.loads(result.stdout)
    if (
        proof["source"] != plan["worker_source"]
        or Path(proof["temporary_directory"]).resolve() != temp
    ):
        raise ValueError("Frozen import path or actual temporary-directory selection differs")
    proof.update(free_bytes=shutil.disk_usage(temp).free, actor_loaded=False, model_calls=0)
    write(root / "storage-preflight.json", proof)
    return proof


def other_stop_reason(plan, summary, state, task, *, now, host_rss, size):
    if task.get("kind") not in TASK_CAPS:
        return "unapproved_task_kind"
    if now - task["started_at"] >= TASK_CAPS[task["kind"]] - 30:
        return "task_time_budget"
    if now - state["started_at"] >= state["budget_seconds"] - 30:
        return "stage_time_budget"
    if now >= plan["wall_deadline_at"] - 30:
        return "wall_time_budget"
    if host_rss > 64 * 1024**3:
        return "host_rss_limit"
    if size >= 32 * 1024**3:
        return "artifact_limit"
    if shutil.disk_usage(Path(plan["run_root"]) / "tmp").free < plan["minimum_temp_free_bytes"]:
        return "temporary_volume_reserve"
    return None


def verify_completed_stage(plan, root, stage):
    report = read_json(root / stage / "actual/report.json")
    marker = read_json(checked(plan["base_marker"]))
    if (
        report.get("status") != "complete"
        or report.get("actor_steps") != 3
        or report.get("critic_steps") != 3
        or report.get("source_unchanged") is not True
        or report.get("source_before") != plan["worker_source"]
        or report.get("source_after") != plan["worker_source"]
        or report.get("final_actor_identity") != marker["actor_identity"]
    ):
        raise ValueError("Evaluation must preserve the exact frozen source and 3/3 endpoint")


def run(plan_path, root):
    plan = read_json(plan_path)
    validate(plan)
    if root != Path(plan["run_root"]).resolve():
        raise ValueError("Run root differs from the declared separate attempt")
    source = code_identity()
    if source["code_dirty"]:
        raise ValueError("Freeze the evaluation-only supervisor before GPU execution")
    root.mkdir(parents=True, exist_ok=False)
    preflight(plan, root)
    (root / "checkpoints").mkdir()
    shutil.copyfile(checked(plan["base_marker"]), root / "checkpoints/base.json")
    with lock(root):
        states = {
            stage: {
                "stage": stage,
                "status": "waiting",
                "attempted": False,
                "budget_seconds": plan["resource_caps"][stage],
                "source": source,
                "created_at": time.time(),
            }
            for stage in ORDER
        }
        summary = {
            "version": VERSION,
            "status": "running",
            "source": source,
            "plan": reference(plan_path),
            "observer_pid": os.getpid(),
            "started_at": time.time(),
            "caps": plan["resource_caps"],
            "task_caps": TASK_CAPS,
            "max_parallel_model_instances": 1,
            "telemetry_grace_seconds": 120,
            "previous_gpu_seconds": plan["previous_gpu_seconds"],
            "prior_run": plan["prior_run"],
            "worker_source": plan["worker_source"],
            "original_failure_preserved": True,
            "no_automatic_second_attempt": True,
        }
        for stage, state in states.items():
            (root / stage).mkdir()
            write(root / stage / "state.json", state)
        active_process, active_stage = None, None

        def publish():
            summary["stage_statuses"] = {k: v["status"] for k, v in states.items()}
            summary["observed_at"] = time.time()
            used = sum(s.get("elapsed_gpu_seconds", 0.0) for s in states.values())
            summary["terminated_gpu_seconds"] = used
            summary["cumulative_terminated_gpu_seconds"] = summary["previous_gpu_seconds"] + used
            write(root / "supervisor.json", summary)

        publish()
        try:
            for index, stage in enumerate(ORDER):
                state = states[stage]
                if index and states[ORDER[index - 1]]["status"] != "complete":
                    state.update(status="not_started_endpoint_unavailable", ended_at=time.time())
                    write(root / stage / "state.json", state)
                    publish()
                    continue
                chosen, admitted = None, None
                while chosen is None:
                    if time.time() >= plan["wall_deadline_at"] - 30:
                        state.update(status="not_started_wall_time_budget", ended_at=time.time())
                        write(root / stage / "state.json", state)
                        break
                    if code_identity() != source or reference(plan_path) != summary["plan"]:
                        raise ValueError("Supervisor source or resume plan changed while waiting")
                    sample = resources()
                    cards = ready_cards(sample, training=False)
                    state.update(last_admission_observation=sample, ready_cards=cards)
                    write(root / stage / "state.json", state)
                    publish()
                    if cards:
                        check = resources()
                        confirmed = ready_cards(check, training=False)
                        if cards[0] in confirmed:
                            chosen, admitted = cards[0], check
                            break
                    time.sleep(5)
                if chosen is None:
                    continue
                command = [
                    sys.executable,
                    "-m",
                    "scripts.composition_recovery_v025",
                    "--plan",
                    str(checked(plan["worker_plan"])),
                    "--run-root",
                    str(root),
                    "--stage",
                    stage,
                    "--output",
                    str(root / stage / "actual"),
                ]
                env = worker_environment(plan, root, chosen)
                state.update(
                    status="launch_intent",
                    attempted=True,
                    gpu=chosen,
                    gpu_uuid=card_uuid(admitted, chosen),
                    started_at=time.time(),
                    command=command,
                    admission_resources=admitted,
                )
                write(root / stage / "state.json", state)
                with (root / stage / "model.log").open("x") as log:
                    process = subprocess.Popen(
                        command,
                        cwd=plan["worker_checkout"],
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    active_process, active_stage = process, stage
                    identity = worker_identity(process.pid)
                    if not identity.get("available") or identity.get("alive") is not True:
                        raise ValueError("Cannot bind the actual newly launched worker")
                    state.update(
                        status="running",
                        pid=process.pid,
                        worker_start_ticks=identity["start_ticks"],
                    )
                    write(root / stage / "state.json", state)
                    publish()
                    telemetry = TelemetryGuard(
                        chosen,
                        state["gpu_uuid"],
                        identity["start_ticks"],
                        grace_seconds=120,
                        worker_pid=process.pid,
                    )
                    last_size_at, size, reason = 0.0, 0, None
                    while process.poll() is None:
                        sample = target_resources(
                            chosen,
                            worker_pid=process.pid,
                            gpu_timeout_seconds=5,
                            process_timeout_seconds=5,
                        )
                        # This parent owns Popen: natural exit wins over a stale
                        # sample that observed the process disappearing.
                        if process.poll() is not None:
                            terminal_sample(root, stage, sample, process)
                            break
                        if sample["worker_identity"].get("alive") is False:
                            try:
                                process.wait(timeout=1)
                            except subprocess.TimeoutExpired:
                                pass
                            if process.poll() is not None:
                                terminal_sample(root, stage, sample, process)
                                break
                        now = time.time()
                        obs = telemetry.observe(
                            sample, now, process.pid, chosen, own_memory_limit_mib=32768
                        )
                        task = read(root / stage / "actual/task.json") or {
                            "task": "startup",
                            "kind": "loading",
                            "started_at": state["started_at"],
                        }
                        resident = rss(process.pid)
                        if now - last_size_at >= 30:
                            size, last_size_at = artifact_bytes(root), now
                        structural_reason = other_stop_reason(
                            plan, summary, state, task, now=now, host_rss=resident, size=size
                        )
                        reason = structural_reason or obs["stop_reason"]
                        row = {
                            "sample": sample,
                            "task": task,
                            "rss_bytes": resident,
                            "all_lines_rss_bytes": resident,
                            "artifact_bytes": size,
                            "own_gpu_memory_mib": obs["own_gpu_memory_mib"],
                            "telemetry": obs,
                        }
                        with (root / stage / "resources.jsonl").open("a") as out:
                            out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        state.update(
                            task=task,
                            telemetry={
                                k: obs[k]
                                for k in (
                                    "fresh",
                                    "stale",
                                    "own_gpu_memory_mib",
                                    "consecutive_failures",
                                    "failures_total",
                                    "failure_since",
                                    "failure_seconds",
                                    "recovered_after_seconds",
                                    "stop_reason",
                                )
                            },
                        )
                        write(root / stage / "state.json", state)
                        publish()
                        if reason:
                            break
                        time.sleep(5)
                    if process.returncode == 0 and reason is None:
                        try:
                            verify_completed_stage(plan, root, stage)
                        except (ValueError, OSError) as error:
                            reason = "unqualified_frozen_endpoint"
                            state["verification_error"] = str(error)
                    finish(root, stage, state, process, reason)
                    active_process, active_stage = None, None
                    publish()
            summary.update(
                status="complete"
                if all(s["status"] == "complete" for s in states.values())
                else "closed_with_incomplete_stages",
                ended_at=time.time(),
            )
        except BaseException as error:
            if active_process is not None:
                finish(
                    root,
                    active_stage,
                    states[active_stage],
                    active_process,
                    "supervisor_interrupted",
                )
            for stage, state in states.items():
                if state["status"] == "waiting":
                    state.update(status="not_started_supervisor_interrupted", ended_at=time.time())
                    write(root / stage / "state.json", state)
            summary.update(
                status="supervisor_error",
                ended_at=time.time(),
                error={"type": type(error).__name__, "message": str(error)},
            )
        finally:
            publish()
    with (root / "archive.log").open("a") as log:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.report_evaluation_resume_v025",
                "--run",
                str(root),
                "--plan",
                str(plan_path),
            ],
            cwd=Path(__file__).resolve().parents[1],
            env={
                **os.environ,
                "CUDA_VISIBLE_DEVICES": "",
                "TMPDIR": str(root / "tmp"),
                "TMP": str(root / "tmp"),
                "TEMP": str(root / "tmp"),
            },
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=600,
            check=False,
        )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    run(args.plan.resolve(), args.run_root.resolve())
