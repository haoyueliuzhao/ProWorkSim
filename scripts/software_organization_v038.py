"""Twenty-four predeclared frozen-actor organization-development episodes.

No training, contribution selection, old-queue successor or automatic retry.
Four independent root shards can share four allowed physical GPUs. Within each
episode all logical members use one resident actor and sequential SDK calls.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.software_organization_tasks_v038 import CASE_IDS, ORIGINAL_IDS, build_case, source_partition
from proworksim.software_organization_v038 import CONDITIONS, case_spec
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_support_v036 as support
from scripts.software_allocation_v037 import available_cards, inherited_source_manifest, live_free_stop_reason
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write
from scripts.software_development_v028 import task

VERSION = "software-organization-execution-v0.38"
checked = support.checked
SOURCE = Path(__file__).resolve().parents[1]
GPU_ORDER = (3, 4, 5, 7)
SEEDS = (202610090101, 202610090102)
WORKERS = tuple(f"root-{i}" for i in range(4))
LIMITS = {"max_new_episodes": 24, "max_parallel_model_instances": 4,
    "max_new_actor_steps": 0, "max_new_critic_steps": 0, "max_new_backward_calls": 0,
    "minimum_free_gpu_mib": 56 * 1024, "own_gpu_memory_mib": 56 * 1024,
    "minimum_live_free_gpu_mib": 6 * 1024, "gpu_capacity_stability_seconds": 60,
    "host_rss_per_worker_bytes": 64 * 1024**3, "artifact_bytes": 128 * 1024**3,
    "minimum_volume_free_bytes": 20 * 1024**3,
    "task_seconds": {"loading": 900, "episode": 2400, "boundary": 600},
    "telemetry_grace_seconds": 120, "poll_seconds": 5}
REPORT_PATHS = ["docs/experiments/software-organization-v038.md", "docs/experiments/software-organization-v038.json"]
CONTROL_SOURCES = ("scripts/software_organization_v038.py",
    "src/proworksim/software_organization_tasks_v038.py", "src/proworksim/software_organization_v038.py",
    "src/proworksim/software_organization_runtime_v038.py", "tests/test_software_organization_v038.py",
    "tests/test_software_organization_runtime_v038.py", "tests/test_software_organization_execution_v038.py")


def assignments():
    result = {}
    for r, case_id in enumerate(CASE_IDS):
        rows = []
        for s, seed in enumerate(SEEDS):
            shift = (2 * r + s) % 3
            for condition in CONDITIONS[shift:] + CONDITIONS[:shift]:
                first_index = (r + 2 * s) % 4 if condition == "O2" else (r + s) % 2
                rows.append({"slot_id": f"org-r{r}-{condition}-s{s}", "case_id": case_id,
                    "original_case_id": ORIGINAL_IDS[case_id], "condition": condition,
                    "sampling_seed": seed, "first_member": f"member_{first_index + 1:03d}"})
        result[WORKERS[r]] = rows
    return result


def qualify(destination):
    """Finite CPU contracts only; no model loading, generation or backward."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}
    tests = [name for name in CONTROL_SOURCES if name.startswith("tests/")]
    commands = [[sys.executable, "-m", "pytest", "-q", *tests,
                 "--basetemp", str(destination / "pytest-tmp")],
                [str(SOURCE / ".venv/bin/python"), "-m", "ruff", "check", "src", "tests", "scripts"]]
    receipts = []
    for i, argv in enumerate(commands):
        started = time.time()
        with (destination / f"check-{i}.log").open("x") as stream:
            result = subprocess.run(argv, cwd=SOURCE, env=env, stdout=stream, stderr=subprocess.STDOUT)
        receipts.append({"command": argv, "exit_code": result.returncode,
            "elapsed_seconds": time.time() - started, "log": reference(destination / f"check-{i}.log")})
    value = {"version": VERSION, "kind": "finite_cpu_contracts", "passed": all(r["exit_code"] == 0 for r in receipts),
        "source_files": {name: digest((SOURCE / name).read_bytes()) for name in CONTROL_SOURCES},
        "checks": receipts, "new_model_calls": 0, "new_backward_calls": 0,
        "scope": "Scripted world/SDK controls do not establish autonomous model usage or quality."}
    write(destination / "qualification.json", value)
    return value


def validate_qualification(path):
    value = read_json(path)
    if (value.get("version") != VERSION or value.get("kind") != "finite_cpu_contracts"
            or value.get("passed") is not True or not value.get("checks")
            or any(r["exit_code"] != 0 for r in value["checks"])
            or value.get("source_files") != {name: digest((SOURCE / name).read_bytes()) for name in CONTROL_SOURCES}):
        raise ValueError("Require passed CPU contracts bound to the complete new implementation")
    for row in value["checks"]:
        checked(row["log"])
    return value


def prepare(data_root, root, qualification):
    data_root, root = Path(data_root).resolve(), Path(root).resolve()
    if root.exists():
        raise FileExistsError("Use a fresh run; no automatic retry or old inventory reuse")
    validate_qualification(qualification)
    parent_root = data_root / "runs/software-support-v036"
    parent = read_json(parent_root / "plan.json")
    report_path = parent_root / support.CANDIDATE / "actual/report.json"
    prior = read_json(report_path)
    common_path = parent_root / support.CANDIDATE / "actual/inherited-common.json"
    common = read_json(common_path)
    checkpoint = read_json(checked(common["common"]))
    checked(checkpoint["state"])
    if (prior.get("status") != "complete" or prior.get("common_restored_exactly") is not True
            or prior.get("source_before") != parent["source"] or prior.get("source_after") != parent["source"]
            or any(common.get(key) != 3 for key in ("actor_steps", "critic_steps"))
            or checkpoint["actor_identity"] != common["actor_identity"]
            or checkpoint["state_tensor_digest"] != common["state_tensor_digest"]):
        raise ValueError("Require the trusted original pre-B 3/3 complete common")
    inherited = inherited_source_manifest(parent["source"])
    audit_path = SOURCE / "docs/experiments/software-organization-v038-prior-audit.json"
    audit = read_json(audit_path)
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Commit the complete implementation and prior audit before prepare")
    if (audit.get("version") != "software-organization-prior-audit-v0.38"
            or audit.get("model_calls") != 0 or audit.get("new_test_or_acceptance_executions") != 0
            or [audit.get("aggregate", {}).get(k, {}).get("episodes") for k in ("P2", "B-development")] != [16, 16]):
        raise ValueError("Stage A must cover the original 32 episodes without new acceptance or model work")
    plan = {"version": VERSION, "purpose": "organization_development", "created_at": time.time(),
        "source": source, "source_root": str(SOURCE), "data_root": str(data_root),
        "authorization": "2026-10-09 user requested audit revisions and subsequent experiments: 24 frozen-actor organization-development units only.",
        "qualification": reference(qualification), "prior_audit": reference(audit_path),
        "parent_plan": reference(parent_root / "plan.json"), "parent_report": reference(report_path),
        "model_references": copy.deepcopy(parent["parent"]["references"]), "common": reference(common_path),
        "expected_actor_identity": common["actor_identity"], "expected_state_sha256": common["state_tensor_digest"],
        "inherited_source_files": inherited, "assignments": assignments(),
        "cases": {c: {o: case_spec(c, condition=o) for o in CONDITIONS} for c in CASE_IDS},
        "source_partition": source_partition(),
        "business_bindings": {c: build_case(c)["initial_binding"] for c in CASE_IDS},
        "gpu_preference": list(GPU_ORDER), "limits": copy.deepcopy(LIMITS),
        "runtime_dependency_path": parent["runtime_dependency_path"],
        "prior_artifact_roots": support.dense._artifact_roots([*parent["prior_artifact_roots"], parent_root]),
        "automatic_retries": False, "automatic_successors": [], "training_eligible": False,
        "independent_confirmation_eligible": False, "shared_gpu_capacity_allowed": True,
        "gpu_seconds_cap": None, "worker_seconds_cap": None, "wall_deadline": None,
        "old_training_queues_remain_paused": True,
        "sampling": "Same inherited actor recipe/profile; reseed once per episode, never on member birth.",
        "scheduling": "Four independent root shards; sequential member calls within one resident model per shard.",
        "analysis": "All 24 retained, including no-spawn, no-submission and technical unknowns. Final fixed delivery only; no unknown-to-zero or success-subset cost estimate."}
    plan["plan_sha256"] = digest(json_bytes(plan))
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = read_json(Path(root) / "plan.json")
    if (plan.get("version") != VERSION
            or plan.get("plan_sha256") != digest(json_bytes({k: v for k, v in plan.items() if k != "plan_sha256"}))
            or plan.get("source") != code_identity() or plan.get("assignments") != assignments()
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != list(GPU_ORDER)
            or plan.get("automatic_successors") != [] or plan.get("training_eligible") is not False):
        raise ValueError("The frozen organization inventory, implementation or resource contract changed")
    validate_qualification(checked(plan["qualification"]))
    for key in ("common", "parent_plan", "parent_report", "prior_audit"):
        checked(plan[key])
    return plan


def allowed_resources():
    """Only inspect user-authorized GPUs, even when looking for queued capacity."""
    return target_resources(",".join(map(str, GPU_ORDER)), worker_pid=os.getpid())


def worker_env(plan, gpu):
    if gpu not in GPU_ORDER:
        raise ValueError("Only physical GPUs 3,4,5,7 are authorized")
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu), "TOKENIZERS_PARALLELISM": "false",
        "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4", "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    env["PYTHONPATH"] = os.pathsep.join([plan["runtime_dependency_path"], str(SOURCE / "src"), str(SOURCE)])
    env.pop("PROWORKSIM_REPLICA_GPUS", None)
    return env


def run_worker(root, worker, output):
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.software_learning_v036 import migrate_software_owner, restore_common
    from proworksim.software_organization_runtime_v038 import collect_episode
    from proworksim.software_organization_v038 import build_software_collaboration_case

    root, output = Path(root).resolve(), Path(output).resolve()
    plan = frozen(root)
    if worker not in WORKERS or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPU_ORDER)):
        raise ValueError("Require one frozen root shard and one allowed physical GPU")
    output.mkdir(parents=True, exist_ok=False)
    owner, rows = None, []
    report = {"version": VERSION, "worker": worker, "status": "loading", "started_at": time.time(),
        "source_before": code_identity(), "rows": rows, "new_actor_steps": 0, "new_critic_steps": 0,
        "new_backward_calls": 0, "plan": reference(root / "plan.json")}
    write(output / "report.json", report)
    try:
        task(output, "load-original-common-actor", "loading")
        sample = allowed_resources()
        write(output / "preload-resources.json", sample)
        if int(os.environ["CUDA_VISIBLE_DEVICES"]) not in [c["index"] for c in available_cards(plan, sample)]:
            raise RuntimeError("Assigned allowed GPU capacity changed before loading")
        refs = plan["model_references"]
        saved = read_json(checked(refs["owner"]))
        old_plan = read_json(checked(refs["plan"]))
        model_plan = read_json(checked(old_plan["prior_model_plan"]))
        owner = DeterministicCandidateActor.from_candidate(model_plan["model"], manifest=checked(model_plan["manifest"]),
            profile=model_plan["runtime_profile"], recipe=saved["recipe"], output=output / "resident")
        write(output / "software-coordinate-binding.json", migrate_software_owner(owner, expected_steps=None))
        task(output, "restore-original-complete-common", "boundary")
        common = read_json(checked(plan["common"]))
        restored = restore_common(owner, checked(common["common"]).parent)
        if (restored["state_sha256"] != common["state_tensor_digest"]
                or restored["rng_sha256"] != common["training_rng_sha256"]
                or restored["actor_identity"] != plan["expected_actor_identity"]
                or (owner.actor_steps, owner.critic_steps) != (3, 3)):
            raise ValueError("All organization conditions must use the exact original 3/3 common")
        write(output / "common-restore.json", restored)

        def forbidden(*args, **kwargs):
            raise RuntimeError("Learning computation is disabled for organization development")

        owner.learning_logprobs = forbidden
        owner.update_window = forbidden
        report.update(status="running", common_restored_exactly=True)
        for unit in plan["assignments"][worker]:
            task(output, unit["slot_id"], "episode")
            folder = output / "episodes" / unit["slot_id"]
            case = case_spec(unit["case_id"], condition=unit["condition"], first_member=unit["first_member"])
            prepared = build_software_collaboration_case(case, folder / "prepared")
            row = collect_episode(owner, prepared, folder, sampling_seed=unit["sampling_seed"], slot_id=unit["slot_id"])
            rows.append({**unit, **row})
            write(output / "progress.json", rows)
            write(output / "report.json", report)
            if row["status"] != "closed" or type(row["R"]) is not int:
                report["status"] = "technical_unknown"
                break
        else:
            report["status"] = "complete"
        task(output, "final-frozen-state-boundary", "boundary")
    except BaseException as error:
        report.update(status="execution_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps,
                new_actor_steps=max(0, owner.actor_steps - 3), new_critic_steps=max(0, owner.critic_steps - 3),
                final_actor_identity=owner._make_identity(),
                actor_identity_unchanged=owner._make_identity() == plan["expected_actor_identity"])
        report.update(ended_at=time.time(), source_after=code_identity())
        write(output / "report.json", report)
    return report


def supervise(root):
    root = Path(root).resolve()
    plan = frozen(root)
    summary = {"version": VERSION, "status": "waiting", "started_at": time.time(), "observer_pid": os.getpid(),
        "source": plan["source"], "states": {name: {"worker": name, "status": "not_started", "attempted": False} for name in WORKERS}}
    active, logs, guards, stable = {}, {}, {}, {}

    def publish():
        summary.update(observed_at=time.time(),
            closed_worker_gpu_seconds=sum(s.get("elapsed_gpu_seconds", 0) for s in summary["states"].values()),
            running_worker_gpu_seconds=sum(time.time() - summary["states"][n]["started_at"] for n in active))
        write(root / "supervisor.json", summary)

    def close(name, reason):
        process = active.pop(name)
        state = summary["states"][name]
        if process.poll() is None:
            support.continuation._stop_worker(process, state)
        process.wait(timeout=15)
        result = read(root / name / "actual/report.json") or {}
        complete = (process.returncode == 0 and reason is None and result.get("status") == "complete"
            and result.get("source_before") == result.get("source_after") == plan["source"]
            and result.get("actor_identity_unchanged") is True
            and result.get("new_actor_steps") == result.get("new_critic_steps") == 0)
        ended = time.time()
        state.update(status="complete" if complete else "stopped", stop_reason=reason,
            exit_code=process.returncode, ended_at=ended, elapsed_gpu_seconds=ended - state["started_at"])
        logs.pop(name).close()
        publish()

    with lock(root):
        if (root / "supervisor.json").exists():
            raise FileExistsError("A started organization inventory is never automatically replayed")
        publish()
        try:
            while True:
                for name, process in list(active.items()):
                    if process.poll() is not None:
                        close(name, None if process.returncode == 0 else "worker_exit_error")
                if all(s["status"] in {"complete", "stopped"} for s in summary["states"].values()):
                    summary["status"] = "complete" if all(s["status"] == "complete" for s in summary["states"].values()) else "closed_with_unknowns"
                    break
                size = sum(artifact_bytes(Path(path)) for path in support.dense._artifact_roots([*plan["prior_artifact_roots"], root]))
                free = shutil.disk_usage(root).free
                if size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                    for name in list(active):
                        close(name, "trajectory_storage_reserve")
                    for state in summary["states"].values():
                        if state["status"] == "not_started":
                            state.update(status="stopped", stop_reason="trajectory_storage_reserve", elapsed_gpu_seconds=0)
                    summary["status"] = "trajectory_storage_reserve"
                    break
                waiting = [n for n in WORKERS if summary["states"][n]["status"] == "not_started"]
                if waiting:
                    sample = allowed_resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    cards = available_cards(plan, sample, [summary["states"][n]["gpu"] for n in active])
                    now = time.time()
                    stable = {c["index"]: stable.get(c["index"], now) for c in cards}
                    for card in cards:
                        if not waiting or len(active) >= LIMITS["max_parallel_model_instances"]:
                            break
                        if now - stable[card["index"]] < LIMITS["gpu_capacity_stability_seconds"]:
                            continue
                        name = waiting.pop(0)
                        folder = root / name
                        folder.mkdir(exist_ok=False)
                        argv = [sys.executable, "-m", "scripts.software_organization_v038", "worker",
                            "--run-root", str(root), "--worker", name, "--output", str(folder / "actual")]
                        logs[name] = (folder / "worker.log").open("x")
                        temporary = folder / "tmp"
                        temporary.mkdir()
                        env = worker_env(plan, card["index"])
                        env.update(TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
                        process = subprocess.Popen(argv, cwd=SOURCE, env=env, stdin=subprocess.DEVNULL,
                            stdout=logs[name], stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        summary["states"][name].update(status="running", attempted=True, gpu=card["index"], gpu_uuid=card["uuid"],
                            pid=process.pid, process_identity=identity, started_at=time.time(), command=argv)
                        active[name] = process
                        guards[name] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        publish()
                if active:
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        futures = {n: pool.submit(target_resources, summary["states"][n]["gpu"], worker_pid=p.pid) for n, p in active.items()}
                        samples = {n: f.result() for n, f in futures.items()}
                    for name, process in list(active.items()):
                        if process.poll() is not None:
                            close(name, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = summary["states"][name]
                        guard = guards[name].observe(samples[name], time.time(), process.pid, state["gpu"], own_memory_limit_mib=LIMITS["own_gpu_memory_mib"])
                        current = read(root / name / "actual/task.json") or {"kind": "loading", "started_at": state["started_at"]}
                        own_rss = rss(process.pid)
                        reason = guard.get("stop_reason") or live_free_stop_reason(samples[name], state["gpu"])
                        cap = LIMITS["task_seconds"].get(current.get("kind"))
                        if cap is None:
                            reason = reason or "unknown_task_kind"
                        elif time.time() - current["started_at"] >= cap:
                            reason = reason or "single_task_budget"
                        elif own_rss > LIMITS["host_rss_per_worker_bytes"]:
                            reason = reason or "host_memory_budget"
                        with (root / name / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": samples[name], "guard": guard, "task": current,
                                "rss_bytes": own_rss, "artifact_bytes": size, "volume_free_bytes": free}) + "\n")
                        if reason:
                            close(name, reason)
                summary["status"] = "running" if active else "waiting"
                publish()
                time.sleep(LIMITS["poll_seconds"])
        except BaseException as error:
            summary.update(status="interrupted", error={"type": type(error).__name__, "message": str(error)})
            for name in list(active):
                close(name, "supervisor_interrupted")
            raise
        finally:
            summary["ended_at"] = time.time()
            publish()
    return summary


def results(root):
    root = Path(root)
    plan = read_json(root / "plan.json")
    state = read(root / "supervisor.json") or {"status": "prepared", "states": {}}
    rows, workers = [], {}
    for worker, inventory in plan["assignments"].items():
        folder = root / worker / "actual"
        workers[worker] = {"state": state["states"].get(worker, {}), "report": read(folder / "report.json")}
        for unit in inventory:
            result = read(folder / "episodes" / unit["slot_id"] / "slot-result.json")
            if result:
                rows.append({**unit, **result})
            else:
                started = (folder / "episodes" / unit["slot_id"]).exists()
                terminal = (state["status"] not in {"prepared", "waiting", "running"}
                    or state["states"].get(worker, {}).get("status") in {"complete", "stopped"})
                status = "technical_unknown" if started and terminal else "running" if started else "not_started"
                rows.append({**unit, "status": status, "R": None, "submitted": None,
                    "training_eligible": False, "worker_state": state["states"].get(worker, {})})
    def known(row):
        return row["status"] == "closed" and type(row["R"]) is int and row["R"] in (0, 1)
    by_condition, by_root = {}, {}
    for condition in CONDITIONS:
        subset = [r for r in rows if r["condition"] == condition]
        closed = [r for r in subset if known(r)]
        by_condition[condition] = {"scheduled": 8, "known": len(closed), "successes": sum(r["R"] for r in closed),
            "unknown_or_pending": 8 - len(closed), "mean_R": sum(r["R"] for r in closed) / 8 if len(closed) == 8 else None,
            "submitted_known": sum(r["submitted"] is True for r in closed),
            "episodes_with_new_births": sum(r["member_lifecycle"]["cumulative_births"] > len(r["member_lifecycle"]["initial_members"]) for r in closed),
            "mean_cost_scope": "No success-only selection; unknown execution costs remain separately recorded."}
    paired = []
    for case_id in CASE_IDS:
        by_root[case_id] = {c: {"known": sum(known(r) for r in rows if r["case_id"] == case_id and r["condition"] == c),
            "successes": sum(r["R"] for r in rows if r["case_id"] == case_id and r["condition"] == c and known(r)), "scheduled": 2} for c in CONDITIONS}
        for seed in SEEDS:
            group = {r["condition"]: r for r in rows if r["case_id"] == case_id and r["sampling_seed"] == seed}
            values = {c: group[c]["R"] if known(group[c]) else None for c in CONDITIONS}
            paired.append({"case_id": case_id, "sampling_seed": seed, "R": values,
                "O3_minus_O1": values["O3"] - values["O1"] if all(values[c] is not None for c in ("O3", "O1")) else None,
                "O3_minus_O2": values["O3"] - values["O2"] if all(values[c] is not None for c in ("O3", "O2")) else None})
    deltas = {key: sum(r[key] for r in paired) / 8 if all(r[key] is not None for r in paired) else None
              for key in ("O3_minus_O1", "O3_minus_O2")}
    costs = [r for r in rows if r.get("usage")]
    cost = {"episodes_with_closed_usage": len(costs), "closed_usage": {
        key: sum(r["usage"].get(key, 0) for r in costs)
        for key in ("decisions", "attempts", "prompt_tokens", "completion_tokens", "total_tokens", "output_bearing_calls",
                    "budget_charged_tokens", "uncertain_usage_attempts")},
        "closed_test_runs": sum(r["team_budget"]["tests"]["used"] for r in costs),
        "closed_worker_gpu_seconds": state.get("closed_worker_gpu_seconds", 0),
        "running_worker_gpu_seconds": state.get("running_worker_gpu_seconds", 0),
        "scope": "Includes successful and failed closed outcomes. Reported token totals exclude unreported usage; uncertain charges stay separate. Partial raw records remain in each worker directory. Worker time includes loading/boundaries and is not summed again with episode time."}
    return {"version": VERSION, "status": state["status"], "plan": reference(root / "plan.json"),
        "source": plan["source"], "purpose": "organization_development", "rows": rows, "workers": workers,
        "by_condition": by_condition, "by_root": by_root, "paired_units": paired, "paired_mean_differences": deltas, "cost": cost,
        "scheduled": 24, "known": sum(known(r) for r in rows), "new_actor_steps": sum((w["report"] or {}).get("new_actor_steps", 0) for w in workers.values()),
        "new_critic_steps": sum((w["report"] or {}).get("new_critic_steps", 0) for w in workers.values()),
        "new_backward_calls": 0, "allowed_physical_gpus": list(GPU_ORDER), "supervisor": state,
        "scope": "Finite organization-development regime comparison on four already-used roots. Not independent confirmation, training gain, contribution evidence or within-team parallel speedup."}


def report(root, destination):
    value = results(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    write(destination / "software-organization-v038.json", value)
    lines = ["# v0.38 冻结模型自主组织开发", "",
        f"状态：`{value['status']}`；原始库存24条，已知结果`{value['known']}/24`。源码`{value['source']['code_commit']}`。", "",
        "原3/3 common actor、四个已用schema根目标、O1/O2/O3各8条，统一共享预算。仅物理GPU 3、4、5、7可调度。原26次试训、正式更新、TextFSM确认与缓存生产测试继续暂停。", "",
        "| 条件 | 已知/计划 | 已知成功 | 已知提交 | 有新增出生的已知槽 | 全8槽平均R |",
        "|---|---:|---:|---:|---:|---:|"]
    for condition, row in value["by_condition"].items():
        lines.append(f"| {condition} | {row['known']}/8 | {row['successes']} | {row['submitted_known']} | {row['episodes_with_new_births']} | {row['mean_R']} |")
    lines += ["", "| root | O1成功/已知/计划 | O2成功/已知/计划 | O3成功/已知/计划 |", "|---|---|---|---|"]
    for case, group in value["by_root"].items():
        lines.append("| " + case + " | " + " | ".join(f"{group[c]['successes']}/{group[c]['known']}/2" for c in CONDITIONS) + " |")
    lines += ["", f"完整配对平均差：`{value['paired_mean_differences']}`。None表示尚未闭合，不填零。", "",
        f"新增actor/critic步：`{value['new_actor_steps']}/{value['new_critic_steps']}`；新增反向：`{value['new_backward_calls']}`。", "",
        "| slot | 状态 | R | 提交 | 有输出调用 | 输入/输出token | 初始/累计/输出参与人数 | 秒 |",
        "|---|---|---:|---|---:|---|---|---:|"]
    for row in value["rows"]:
        usage, life = row.get("usage", {}), row.get("member_lifecycle", {})
        lines.append(f"| {row['slot_id']} | {row['status']} | {row['R']} | {row.get('submitted')} | {usage.get('output_bearing_calls')} | {usage.get('prompt_tokens')}/{usage.get('completion_tokens')} | {len(life['initial_members']) if life else None}/{life.get('cumulative_births')}/{life.get('actual_output_participants')} | {row.get('wall_seconds')} |")
    lines += ["", "逐成员调用、真实输出与控制机会、selected输入、出生/退出、预算、任务和固定版本证据保存在原始episode目录；完整路径及护栏回执见同名JSON。技术未知保留原槽，不自动重试、不补验可变工作区。", "",
        "本轮每个worker仅加载一份模型，成员使用独立会话顺序调用；不同root可并行。活动人数包含等待者，永久退出不复活，出生不增加预算。O3不增员是合法结果；接口控制通过不等于模型实际使用，更不等于组织有效。只解释有限开发条件差，不声称ID-VTDO分配收益或训练收益。", "",
        "协议与实现说明：[software-organization-v038-protocol.md](software-organization-v038-protocol.md)；旧32槽行为审计：[software-organization-v038-prior-audit.md](software-organization-v038-prior-audit.md)。", ""]
    (destination / "software-organization-v038.md").write_text("\n".join(lines))
    return value


def finish(root, report_repo):
    root, report_repo = Path(root).resolve(), Path(report_repo).resolve()
    path = root / "finish.json"
    if path.exists():
        raise FileExistsError("Do not overwrite an existing finisher")
    state = {"version": VERSION, "status": "supervising", "started_at": time.time()}
    write(path, state)
    error = None
    try:
        state["status"] = supervise(root)["status"]
    except BaseException as caught:
        error = caught
        state.update(status="execution_error", error={"type": type(caught).__name__, "message": str(caught)})
    finally:
        try:
            state["report_status"] = report(root, report_repo / "docs/experiments")["status"]
            state["publication"] = support.publish_report_paths(report_repo, REPORT_PATHS,
                "docs: record frozen v038 organization-development outcomes")
        except BaseException as caught:
            state["reporting_error"] = {"type": type(caught).__name__, "message": str(caught)}
        state["ended_at"] = time.time()
        write(path, state)
    if error is not None:
        raise error
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("qualify", "prepare", "worker", "supervise", "report", "finish"))
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--data-root", type=Path, default=SOURCE)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--worker")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report-repo", type=Path)
    args = parser.parse_args()

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    if args.mode == "qualify":
        result = qualify(args.output)
        if not result["passed"]:
            raise SystemExit(1)
    elif args.mode == "prepare":
        prepare(args.data_root, args.run_root, args.qualification)
    elif args.mode == "worker":
        run_worker(args.run_root, args.worker, args.output)
    elif args.mode == "supervise":
        supervise(args.run_root)
    elif args.mode == "report":
        report(args.run_root, args.output)
    else:
        finish(args.run_root, args.report_repo)


if __name__ == "__main__":
    main()
