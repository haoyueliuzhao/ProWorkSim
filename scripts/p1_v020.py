"""One bounded, single-resident P1: own-token numerics then four development worlds.

This is initialization diagnosis, not the 144-episode pilot or a new trainer.
The watchdog only signals its own child process group, never another project.
"""

import argparse
import copy
import importlib.metadata
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.storage import atomic_write, digest, json_bytes, read_json

VERSION = "single-resident-p1-v0.20"
LIMITS = {"gpu_count": 1, "gpu_seconds": 3600, "task_seconds": 900,
          "host_rss_bytes": 64 * 1024**3, "output_bytes": 5 * 1024**3,
          "model_api_calls": 0, "minimum_free_gpu_mib": 40960,
          "gpu_process_memory_limit_mib": 40960}
ALLOWED_GPUS = (2, 3, 4, 5, 6)
PROBE_INVENTORY = Path(__file__).resolve().parents[1] / "examples/throughput-v19/probe-inventory.json"


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def checked(value):
    path = Path(value["path"])
    if ref(path) != value:
        raise ValueError("Declared input reference changed")
    return path


def write(path, value):
    atomic_write(Path(path), json_bytes(value))


def execution_class(execution_profile):
    if execution_profile == "v0.20":
        from proworksim.candidate_runtime_v020 import CandidateActor
    elif execution_profile == "v0.20.1":
        from proworksim.candidate_runtime_v0201 import CandidateActor
    else:
        raise ValueError("Only the two explicitly declared P1 numerical profiles are permitted")
    return CandidateActor


def prior_budget(execution_profile, prior_attempt_ref):
    if execution_profile == "v0.20":
        if prior_attempt_ref is not None:
            raise ValueError("Initial P1 has no prior execution")
        return 0.0, 0
    if execution_profile != "v0.20.1" or prior_attempt_ref is None:
        raise ValueError("The sole follow-up requires the closed original P1 launch reference")
    path = checked(prior_attempt_ref)
    launch = read_json(path)
    report = read_json(path.parent / "report.json")
    prior_plan = read_json(checked(report["plan"]))
    elapsed = launch.get("elapsed_seconds")
    if (launch.get("version") != VERSION or launch.get("status") != "stopped"
            or launch.get("exit_code") != 2 or launch.get("downstream_started") is not False
            or launch.get("limits") != LIMITS or launch.get("ended_at") is None
            or type(elapsed) not in (int, float) or not math.isfinite(elapsed) or not 0 < elapsed < LIMITS["gpu_seconds"]
            or prior_plan["runtime_profile"].get("version") != "candidate-runtime-v0.20"
            or report.get("status") != "stopped_numeric_gate" or report.get("source_unchanged") is not True
            or report.get("actor_steps") != 0 or report.get("critic_steps") != 0
            or report.get("work_episodes_started") != 0):
        raise ValueError("Prior attempt is not the closed original zero-update P1 numeric failure")
    size = sum(p.stat().st_size for p in path.parent.rglob("*") if p.is_file())
    return elapsed, size


def build_plan(model, manifest, inventory, *, execution_profile="v0.20", prior_attempt_ref=None):
    from proworksim.templates.retail_balanced import resolve

    candidate_profile = execution_class(execution_profile).profile_factory
    prior_seconds, prior_bytes = prior_budget(execution_profile, prior_attempt_ref)

    slots = []
    for i, (task, fact, quality) in enumerate((
        ("implement", 0, None), ("review", 0, "wrong_count"),
        ("pair", 1, None), ("chain", 2, None),
    )):
        case = resolve("development", fact, task, quality)
        slots.append({"slot_id": f"v020-p1-{i}-{task}", "case_id": case["case_id"],
                      "task": task, "pool": case["pool"], "family": case["family"],
                      "repeat": 0, "sampling_seed": 202609274100 + i,
                      "role_decision_limits": copy.deepcopy(case["role_decision_limits"]),
                      "purpose": "interface_development_not_locked_evaluation"})
    return {"version": VERSION, "purpose": "interface_development", "candidate": "qwen35-9b",
            "execution_profile": execution_profile, "prior_attempt_ref": copy.deepcopy(prior_attempt_ref),
            "prior_elapsed_gpu_seconds": prior_seconds, "remaining_gpu_seconds": LIMITS["gpu_seconds"] - prior_seconds,
            "prior_output_bytes": prior_bytes,
            "model": str(Path(model).resolve()), "manifest": ref(manifest),
            "authorization": "User explicitly resumed this bounded single-GPU P1 on 2026-09-27; no P2 or successor authorization.",
            "limits": copy.deepcopy(LIMITS), "allowed_gpus_in_priority_order": list(ALLOWED_GPUS),
            "runtime_profile": candidate_profile("qwen3.5-9b", devices=1),
            "recipe": {"seed": 2026093041, "max_length": 16384, "max_output_tokens": 2048,
                       "max_rss_bytes": LIMITS["host_rss_bytes"], "diagnostic_max_groups": 0,
                       "post_update_max_decisions": 0},
            "numerical_requests": [{"request": {k: row["record"][k] for k in ("path", "sha256")},
                                    "purpose": row["purpose"], "seed": 202609274000 + i}
                                   for i, row in enumerate(inventory["candidates"]["qwen35-9b"])],
            "work_window": {"window_id": "v020-p1-work", "mode": "evaluate", "stage": "P1_v020",
                            "template": "retail_balanced", "harness": "native_v15", "interface": "v14",
                            "presentation": "compact_v14", "external_tick_per_sweep": 1,
                            "min_class_count": 2, "slots": slots},
            "optimizer_steps": 0, "resident_instances": 1, "sampling_replicas": 0, "automatic_successors": [],
            "scope": "Current-policy sampling and diagnostic backward plus actual local-information work. Borrow old public prompts only, never old outputs/probabilities or rewards. Not optimizer-step capacity, learning gain, P2 source admission, or ID-VTDO support."}


def validate_plan(plan):
    candidate_profile = execution_class(plan.get("execution_profile")).profile_factory
    if (plan.get("version") != VERSION or plan.get("limits") != LIMITS
            or plan.get("candidate") != "qwen35-9b" or plan.get("optimizer_steps") != 0
            or plan.get("resident_instances") != 1 or plan.get("sampling_replicas") != 0
            or plan.get("automatic_successors") != []
            or plan.get("allowed_gpus_in_priority_order") != list(ALLOWED_GPUS)
            or plan.get("runtime_profile") != candidate_profile("qwen3.5-9b", devices=1)):
        raise ValueError("P1 declaration differs from the authorized fixed experiment")
    inventory = read_json(PROBE_INVENTORY)
    expected = build_plan(plan["model"], checked(plan["manifest"]), inventory,
                          execution_profile=plan["execution_profile"], prior_attempt_ref=plan.get("prior_attempt_ref"))
    if expected != plan or len(plan["numerical_requests"]) != 3:
        raise ValueError("P1 cases, seeds, recipe or responsibilities changed")
    for row in plan["numerical_requests"]:
        checked(row["request"])


def heartbeat(out, task):
    write(out / "task.json", {"task": task, "started_at": time.time(), "pid": os.getpid()})


def numerical(owner, plan, out):
    import torch
    from proworksim.online_training import probability_check

    rows = []
    owner.begin_window("v020-p1-numerical")
    original_identity = owner.freeze_identity()
    for i, spec in enumerate(plan["numerical_requests"]):
        heartbeat(out, f"numerical-{i}")
        request = copy.deepcopy(read_json(checked(spec["request"]))["request"])
        request["max_tokens"] = 2048
        owner.reseed(spec["seed"], label=f"p1-numerical-{i}")
        start = time.monotonic()
        response = owner.complete(request, timeout_seconds=600)
        row = {"request": spec["request"], "http_status": response["http_status"],
               "generation_seconds": time.monotonic() - start,
               "response_id": response["body"].get("id"), "usage": response["body"].get("usage"),
               "service": response["body"].get("service_record")}
        rows.append(row)
        write(out / "numerical.json", {"status": "running", "rows": rows, "optimizer_steps": 0})
        if response["http_status"] != 200:
            row["error"] = response["body"]
            break
        trace = response["body"]["token_trace"]
        row["raw_trace_integrity"] = (bool(trace.get("output_ids"))
            and trace.get("raw_output_ids") == trace["output_ids"]
            and trace.get("raw_behavior_logprobs") == trace.get("behavior_logprobs")
            and len(trace.get("behavior_logprobs", [])) == len(trace["output_ids"]))
        if not row["raw_trace_integrity"]:
            break
        owner.model.eval()
        row["learning_forward_calls_attempted"] = 1
        with torch.no_grad():
            probs = owner.learning_logprobs(trace)
        row["recomputed_logprobs_dtype"] = str(probs.dtype)
        if hasattr(owner, "execution_diagnostics"):
            row["recompute_execution"] = owner.execution_diagnostics()
        row["probability"] = probability_check(probs.detach().cpu().tolist(), trace["behavior_logprobs"], owner.recipe)
        del probs
        write(out / "numerical.json", {"status": "running", "rows": rows, "optimizer_steps": 0})
        if not row["probability"]["passed"]:
            break
        owner.model.train()
        owner.actor_optimizer.zero_grad(set_to_none=True)
        start = time.monotonic()
        row["learning_forward_calls_attempted"] += 1
        probs = owner.learning_logprobs(trace)
        check = probability_check(probs.detach().cpu().tolist(), trace["behavior_logprobs"], owner.recipe)
        row["gradient_probability"] = check
        row["gradient_logprobs_dtype"] = str(probs.dtype)
        if hasattr(owner, "execution_diagnostics"):
            row["gradient_forward_execution"] = owner.execution_diagnostics()
        if not check["passed"]:
            del probs
            break
        row["backward_attempted"] = True
        write(out / "numerical.json", {"status": "running", "rows": rows, "optimizer_steps": 0})
        (-probs.mean()).backward()
        torch.cuda.synchronize()
        gradients = [p.grad for p in owner.actor_parameters.values() if p.grad is not None]
        row["backward"] = {"seconds": time.monotonic() - start,
                           "finite": bool(gradients) and all(bool(torch.isfinite(g).all()) for g in gradients),
                           "nonzero_elements": sum(int(torch.count_nonzero(g)) for g in gradients),
                           "optimizer_steps": 0}
        owner.actor_optimizer.zero_grad(set_to_none=True)
        owner.model.eval()
        del probs, gradients
        write(out / "numerical.json", {"status": "running", "rows": rows, "optimizer_steps": 0})
        if not row["backward"]["finite"] or row["backward"]["nonzero_elements"] == 0:
            break
    owner.actor_optimizer.zero_grad(set_to_none=True)
    owner.model.eval()
    passed = len(rows) == 3 and all(
        x.get("raw_trace_integrity") and x.get("probability", {}).get("passed")
        and x.get("gradient_probability", {}).get("passed")
        and x.get("backward", {}).get("finite") and x["backward"]["nonzero_elements"] > 0
        for x in rows)
    if owner._make_identity() != original_identity or owner.actor_steps or owner.critic_steps:
        raise ValueError("The P1 diagnostic altered parameters or optimizer steps")
    # Explicit diagnostic closure: finish_evaluation would falsely claim no
    # learner forward/backward, so do not emit that evaluation-only record.
    owner.clear_generation_cache()
    owner.phase = "idle"
    result = {"status": "passed" if passed else "failed", "rows": rows, "optimizer_steps": 0,
              "diagnostic_learning_forward_and_backward": any("backward" in row for row in rows),
              "learning_forward_calls_attempted": sum(row.get("learning_forward_calls_attempted", 0) for row in rows),
              "backward_calls_attempted": sum(bool(row.get("backward_attempted")) for row in rows),
              "backward_calls_completed": sum("backward" in row for row in rows),
              "actor_identity": original_identity}
    write(out / "numerical.json", result)
    return passed


def child(plan, out):
    validate_plan(plan)
    source = code_identity()
    if source["code_dirty"]:
        raise ValueError("Freeze the clean source before P1")
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in {str(i) for i in ALLOWED_GPUS}:
        raise ValueError("Exactly one physical GPU required")
    CandidateActor = execution_class(plan["execution_profile"])
    from proworksim.harness_collection import collect_window
    from proworksim.online_training import run_online_windows

    report = {"version": VERSION, "status": "running", "source_before": source,
              "plan": ref(out / "plan.json"), "numeric_completed": False, "work_episodes_started": 0,
              "model_api_calls": 0, "optimizer_steps": 0}
    write(out / "report.json", report)
    owner = None
    try:
        heartbeat(out, "model-loading")
        if importlib.metadata.version("duckdb") != "1.5.5":
            raise ValueError("Pinned world executor required")
        owner = CandidateActor.from_candidate(plan["model"], manifest=checked(plan["manifest"]),
                                             profile=plan["runtime_profile"], recipe=plan["recipe"], output=out / "resident")
        if not numerical(owner, plan, out):
            report["status"] = "stopped_numeric_gate"
            return 2
        report["numeric_completed"] = True
        write(out / "report.json", report)
        windows = []
        for row in plan["work_window"]["slots"]:
            spec = copy.deepcopy(plan["work_window"])
            spec.update(window_id=row["slot_id"], slots=[row])
            windows.append(spec)

        def collect(current_owner, spec, destination):
            heartbeat(out, spec["window_id"])
            report["work_episodes_started"] += 1
            write(out / "report.json", report)
            return collect_window(current_owner, spec, destination)

        result = run_online_windows(owner, {"mode": "evaluate", "windows": windows}, out / "work", collect)
        report.update(status=result["status"], work_report=ref(out / "work/report.json"))
        return 0 if result["status"] == "complete" else 1
    except BaseException as error:
        report.update(status="interrupted_or_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report.update(source_after=code_identity(), actor_steps=owner.actor_steps if owner else None,
                      critic_steps=owner.critic_steps if owner else None)
        report["source_unchanged"] = report["source_before"] == report["source_after"]
        write(out / "report.json", report)


def query_gpus():
    p = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,memory.free,memory.total,utilization.gpu,name",
                        "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=15, check=True)
    return [{"index": int(i), "uuid": uuid, "free_mib": float(free), "total_mib": float(total),
             "utilization": float(util), "name": name} for i, uuid, free, total, util, name in
            ([v.strip() for v in line.split(",")] for line in p.stdout.splitlines())]


def stop_owned_child(process):
    """Only the Popen child started in its own session; escalation is bounded."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # The owned process exited between the poll and signal.


def parent(plan, out):
    validate_plan(plan)
    source = code_identity()
    if source["code_dirty"]:
        raise ValueError("Clean frozen source required")
    if out.exists():
        raise FileExistsError("P1 may only start in a new directory; no automatic retry")
    cards = query_gpus()
    by_id = {c["index"]: c for c in cards}
    eligible = [i for i in ALLOWED_GPUS if i in by_id and "A100" in by_id[i]["name"]
                and by_id[i]["free_mib"] >= LIMITS["minimum_free_gpu_mib"]]
    if not eligible:
        raise RuntimeError("No authorized GPU meets the fixed free-memory threshold; no queue or model started")
    gpu = eligible[0]
    out.mkdir(parents=True)
    write(out / "plan.json", plan)
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu), "HF_HUB_OFFLINE": "1",
           "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"}
    env.pop("PROWORKSIM_REPLICA_GPUS", None)
    started = time.time()
    command = [sys.executable, "-m", "scripts.p1_v020", "--child", "--plan", str(out / "plan.json"), "--output", str(out)]
    state = {"version": VERSION, "status": "launch_intent", "started_at": started, "gpu": gpu,
             "source": source, "command": command, "limits": LIMITS, "before_resources": cards,
             "execution_profile": plan["execution_profile"], "prior_attempt_ref": plan["prior_attempt_ref"],
             "prior_elapsed_gpu_seconds": plan["prior_elapsed_gpu_seconds"],
             "remaining_gpu_seconds": plan["remaining_gpu_seconds"]}
    write(out / "launch.json", state)
    with (out / "model.log").open("x") as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
        state.update(pid=process.pid, status="running")
        write(out / "launch.json", state)
        reason = None
        try:
            while process.poll() is None:
                now = time.time()
                task = read_json(out / "task.json") if (out / "task.json").exists() else {"started_at": started, "task": "startup"}
                try:
                    rss = int(Path(f"/proc/{process.pid}/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
                except FileNotFoundError:
                    rss = 0
                size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) + plan["prior_output_bytes"]
                if now - started >= plan["remaining_gpu_seconds"]:
                    reason = "total_gpu_time_limit"
                elif now - task["started_at"] >= LIMITS["task_seconds"]:
                    reason = "single_task_time_limit"
                elif rss > LIMITS["host_rss_bytes"]:
                    reason = "host_memory_limit"
                elif size > LIMITS["output_bytes"]:
                    reason = "artifact_size_limit"
                result = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_gpu_memory,process_name",
                                         "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=15)
                own_memory = 0
                if result.returncode != 0:
                    reason = reason or "gpu_resource_query_failed"
                for line in result.stdout.splitlines():
                    fields = [v.strip() for v in line.split(",", 3)]
                    if len(fields) == 4 and fields[1] == str(process.pid):
                        try:
                            own_memory += float(fields[2])
                        except ValueError:
                            reason = reason or "gpu_resource_query_unparseable"
                if own_memory > LIMITS["gpu_process_memory_limit_mib"]:
                    reason = "gpu_process_memory_limit"
                with (out / "resources.jsonl").open("a") as stream:
                    stream.write(json_bytes({"time": now, "pid": process.pid, "task": task, "rss_bytes": rss,
                        "output_bytes": size, "own_gpu_memory_mib": own_memory,
                        "process_returncode": result.returncode, "processes": result.stdout, "query_stderr": result.stderr}).decode().replace("\n", " ") + "\n")
                if reason:
                    stop_owned_child(process)
                    break
                time.sleep(2)
        except BaseException as error:
            reason = reason or "watchdog_error:" + type(error).__name__
            stop_owned_child(process)
            raise
        finally:
            code = process.wait()
            state.update(status="complete" if code == 0 else "stopped", exit_code=code,
                         ended_at=time.time(), limit_reason=reason, elapsed_seconds=time.time()-started,
                         cumulative_gpu_seconds=plan["prior_elapsed_gpu_seconds"] + time.time() - started,
                         no_retry=True, downstream_started=False)
            write(out / "launch.json", state)
    return code


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--child", action="store_true")
    args = p.parse_args()
    plan = read_json(args.plan)
    return child(plan, args.output.resolve()) if args.child else parent(plan, args.output.resolve())


if __name__ == "__main__":
    sys.exit(main())
