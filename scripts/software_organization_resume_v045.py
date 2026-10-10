"""Continue only the original twenty-three unopened v045 diagnostic slots.

Fix a host measurement interface identity binding, preserving the first result,
its original pause, every model-visible byte and the existing local-stop policy.
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
from proworksim.software_organization_v045 import CONDITIONS, case_spec
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_support_v036 as support
from scripts.software_allocation_v037 import available_cards, live_free_stop_reason
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write
from scripts.software_development_v028 import task
from scripts import software_organization_v045 as original
from scripts import software_organization_v044 as accounting

VERSION = "software-organization-resume-v0.45"
SOURCE = Path(__file__).resolve().parents[1]
GPU_ORDER, WORKERS, LIMITS = (
    original.GPU_ORDER,
    original.WORKERS,
    {**original.LIMITS, "max_new_episodes": 23},
)
RETAINED_SLOT = "org45-r0-s0-S1"
REPORT_PATHS = [
    "docs/experiments/software-organization-v045-resume.md",
    "docs/experiments/software-organization-v045-resume.json",
]
checked, source_files = original.checked, original.source_files


def assignments():
    return {
        w: [u for u in units if u["slot_id"] != RETAINED_SLOT]
        for w, units in original.assignments().items()
    }


def budget_caps():
    old = dict(decisions=7, attempts=7, total_tokens=87890, run_tests=2)
    new = dict(decisions=2944, attempts=2944, total_tokens=11500000, run_tests=736)
    return {
        "old_actual": old,
        "new": new,
        "combined": {k: old[k] + new[k] for k in old},
        "old_unused_tokens": 412110,
        "transfer_old_unused": False,
        "optional_probe_budget_authorized": False,
    }


def qualify(destination, admission):
    from scripts.software_organization_resume_admission_v045 import validate_admission

    admitted = validate_admission(admission, source_root=SOURCE)
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    before = source_files()
    commands = [
        [
            str(SOURCE / ".venv/bin/python"),
            "-m",
            "pytest",
            "-q",
            "tests/test_software_organization_resume_admission_v045.py",
            "tests/test_software_organization_resume_v045.py",
            "--basetemp",
            str(destination / "pytest-tmp"),
        ],
        [str(SOURCE / ".venv/bin/python"), "-m", "ruff", "check", "src", "tests", "scripts"],
    ]
    checks = []
    for i, argv in enumerate(commands):
        t = time.time()
        log = destination / f"check-{i}.log"
        with log.open("x") as stream:
            result = subprocess.run(
                argv,
                cwd=SOURCE,
                env={**os.environ, "CUDA_VISIBLE_DEVICES": "", "PYTHONDONTWRITEBYTECODE": "1"},
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
        checks.append(
            {
                "command": argv,
                "exit_code": result.returncode,
                "elapsed_seconds": time.time() - t,
                "skipped": "skipped" in log.read_text(),
                "log": reference(log),
            }
        )
    value = {
        "version": VERSION,
        "passed": admitted["passed"]
        and before == source_files()
        and all(c["exit_code"] == 0 and not c["skipped"] for c in checks),
        "source_files": source_files(),
        "admission": reference(admission),
        "checks": checks,
        "new_model_calls": 0,
        "new_tokenizer_calls": 0,
        "new_test_or_acceptance_executions": 0,
        "scope": "Host-only version measurement binding and unique23 release. Reuse passed seven measurement controls and original business/native qualification; no replay.",
    }
    write(destination / "qualification.json", value)
    return value


def validate_qualification(path):
    from scripts.software_organization_resume_admission_v045 import validate_admission

    value = read_json(path)
    if (
        value.get("version") != VERSION
        or value.get("passed") is not True
        or value.get("source_files") != source_files()
        or len(value.get("checks", [])) != 2
        or any(c["exit_code"] or c.get("skipped") for c in value["checks"])
    ):
        raise ValueError("Require passed source-bound host continuation controls")
    for row in value["checks"]:
        checked(row["log"])
    validate_admission(checked(value["admission"]), source_root=SOURCE)
    return value


def prepare(data_root, root, qualification):
    data_root, root = Path(data_root).resolve(), Path(root).resolve()
    if root.exists():
        raise FileExistsError("Fresh continuation root required; the first slot may not replay")
    qualified = validate_qualification(qualification)
    old_root = data_root / "runs/software-organization-v045"
    parent = read_json(old_root / "plan.json")
    source = code_identity()
    if (
        source["code_dirty"] is not False
        or source["source_tree_sha256"] != parent["source"]["source_tree_sha256"]
    ):
        raise ValueError(
            "Clean host-only continuation source with unchanged model-visible src required"
        )
    review_path = data_root / "runs/v045-resume-controls/first-slot-review/summary.json"
    plan = copy.deepcopy(parent)
    plan.pop("plan_sha256", None)
    plan.update(
        version=VERSION,
        source=source,
        source_root=str(SOURCE),
        data_root=str(data_root),
        created_at=time.time(),
        source_files=source_files(),
        qualification=reference(qualification),
        resume_admission=qualified["admission"],
        original_run_root=str(old_root),
        original_plan=reference(old_root / "plan.json"),
        original_execution_source=parent["source"],
        original_assignments=parent["assignments"],
        assignments=assignments(),
        cases={
            w: [
                c
                for c, u in zip(parent["cases"][w], parent["assignments"][w])
                if u["slot_id"] != RETAINED_SLOT
            ]
            for w in WORKERS
        },
        limits=copy.deepcopy(LIMITS),
        budget_caps=budget_caps(),
        first_slot_review=reference(review_path),
        prior_artifact_roots=support.dense._artifact_roots(
            [
                *parent["prior_artifact_roots"],
                old_root,
                data_root / "runs/v045-final-analysis",
                data_root / "runs/v045-resume-controls",
            ]
        ),
        authorization="Continue the already authorized original24 diagnostic task after correcting its new host measurement interface binding. Preserve the completed S1 and original global pause. Only23 never-started slots, no first-slot rerun, no new seed, work Gamma, stop-scope revision, extra budget or successor.",
        correction_scope="The v045 world deliberately uses its own interface marker; old measurement incorrectly required the v042 marker. New isolated measurement strictly expects v045, with the same projection, retirement and stop algorithms. Original7 requests read-only verified, no new tokenizer or model.",
        scheduling="Eight original blocks retain their remaining order (first block F2/O3 only). Same max3 residents, allowed GPUs, capacity stability and per-task/resource guards. All model-visible dependencies and original per-episode resets unchanged.",
    )
    if (
        root == old_root
        or old_root in root.parents
        or parent["assignments"] != original.assignments()
    ):
        raise ValueError("Original source and inventory remain immutable")
    plan["plan_sha256"] = digest(json_bytes(plan))
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = read_json(Path(root) / "plan.json")
    if (
        plan.get("version") != VERSION
        or plan.get("plan_sha256")
        != digest(json_bytes({k: v for k, v in plan.items() if k != "plan_sha256"}))
        or plan.get("source") != code_identity()
        or plan.get("source_files") != source_files()
        or plan.get("assignments") != assignments()
        or plan.get("original_assignments") != original.assignments()
        or plan.get("limits") != LIMITS
        or plan.get("budget_caps") != budget_caps()
        or plan.get("gpu_preference") != list(GPU_ORDER)
        or plan.get("automatic_successors") != []
        or plan.get("optional_probe", {}).get("enabled") is not False
        or any(
            plan.get(k) is not False
            for k in (
                "training_eligible",
                "contribution_eligible",
                "independent_confirmation_eligible",
            )
        )
    ):
        raise ValueError("Frozen23 continuation source or limits changed")
    qualification = validate_qualification(checked(plan["qualification"]))
    if qualification["admission"] != plan["resume_admission"]:
        raise ValueError("Continuation admission mismatch")
    parent = read_json(checked(plan["original_plan"]))
    for key in (
        "common",
        "model_references",
        "expected_actor_identity",
        "expected_state_sha256",
        "runtime_dependency_path",
        "source_partition",
        "business_bindings",
        "feedback_protocol",
        "batch_stop_policy",
    ):
        if plan[key] != parent[key]:
            raise ValueError("Original work dependency changed: " + key)
    expected = {
        w: [
            c
            for c, u in zip(parent["cases"][w], parent["assignments"][w])
            if u["slot_id"] != RETAINED_SLOT
        ]
        for w in WORKERS
    }
    if (
        plan["cases"] != expected
        or plan["source"]["source_tree_sha256"] != parent["source"]["source_tree_sha256"]
    ):
        raise ValueError("Model-visible source or remaining cases changed")
    checked(plan["first_slot_review"])
    checked(plan["common"])
    return plan


def require_worker_release(root, worker, plan):
    if worker not in WORKERS or mechanism_pauses(root):
        raise ValueError("Only original unstarted inventory can continue")


def mechanism_pauses(root):
    return sorted((Path(root) / "mechanism-stops").glob("*.json"))


def record_policy_assessment(root, worker, slot_id, folder, assessment):
    """Persist host-only interpretation without rewriting results or feedback."""
    root, folder = Path(root).resolve(), Path(folder).resolve()
    expected = root / worker / "actual/episodes" / slot_id
    if (
        worker not in WORKERS
        or slot_id not in {u["slot_id"] for u in assignments()[worker]}
        or folder != expected
        or assessment.get("slot_id") != slot_id
        or assessment.get("decision") not in {"continue", "global_pause", "measurement_pending"}
    ):
        raise ValueError("Policy receipt does not bind the unique new slot")
    destination = folder / "batch-stop-assessment.json"
    if destination.exists():
        raise FileExistsError("Do not overwrite an existing batch policy assessment")
    write(destination, assessment)
    if assessment["decision"] == "continue":
        return None
    write(
        root / "mechanism-stops" / (slot_id + ".json"),
        {
            "kind": assessment["decision"],
            "reason": "batch_stop_policy_assessment",
            "slot_id": slot_id,
            "worker": worker,
            "observed_at": time.time(),
            "assessment": reference(destination),
            "feedback": reference(folder / "feedback-loop.json"),
            "result": reference(folder / "slot-result.json"),
        },
    )
    return assessment["decision"]


def eligible_workers(states, gate=None):
    return [name for name in WORKERS if states[name]["status"] == "not_started"]


def allowed_resources():
    """Only inspect user-authorized GPUs, even when looking for queued capacity."""
    return target_resources(",".join(map(str, GPU_ORDER)), worker_pid=os.getpid())


def worker_env(plan, gpu):
    if gpu not in GPU_ORDER:
        raise ValueError("Only physical GPUs 3,4,5,7 are authorized")
    env = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": str(gpu),
        "TOKENIZERS_PARALLELISM": "false",
        "OMP_NUM_THREADS": "4",
        "MKL_NUM_THREADS": "4",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    env["PYTHONPATH"] = os.pathsep.join(
        [plan["runtime_dependency_path"], str(SOURCE / "src"), str(SOURCE)]
    )
    env.pop("PROWORKSIM_REPLICA_GPUS", None)
    return env


def validate_worker_target(root, worker, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if worker not in WORKERS or output != root / worker / "actual":
        raise ValueError("Worker output must be its unique v045 block")
    if output.exists():
        raise FileExistsError("An attempted v045 block may not be replayed")
    return root, output


def run_worker(root, worker, output):
    root, output = validate_worker_target(root, worker, output)
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.software_learning_v036 import migrate_software_owner, restore_common
    from proworksim.software_organization_runtime_v045 import collect_episode
    from proworksim.software_organization_v045 import build_software_collaboration_case

    root, output = Path(root).resolve(), Path(output).resolve()
    plan = frozen(root)
    if worker not in WORKERS or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(
        map(str, GPU_ORDER)
    ):
        raise ValueError("Require one frozen root shard and one allowed physical GPU")
    require_worker_release(root, worker, plan)
    output.mkdir(parents=True, exist_ok=False)
    owner, rows = None, []
    report = {
        "version": VERSION,
        "worker": worker,
        "status": "loading",
        "started_at": time.time(),
        "source_before": code_identity(),
        "rows": rows,
        "new_actor_steps": 0,
        "new_critic_steps": 0,
        "new_backward_calls": 0,
        "plan": reference(root / "plan.json"),
    }
    write(output / "report.json", report)
    try:
        task(output, "load-original-common-actor", "loading")
        sample = allowed_resources()
        write(output / "preload-resources.json", sample)
        if int(os.environ["CUDA_VISIBLE_DEVICES"]) not in [
            c["index"] for c in available_cards(plan, sample)
        ]:
            raise RuntimeError("Assigned allowed GPU capacity changed before loading")
        refs = plan["model_references"]
        saved = read_json(checked(refs["owner"]))
        old_plan = read_json(checked(refs["plan"]))
        model_plan = read_json(checked(old_plan["prior_model_plan"]))
        owner = DeterministicCandidateActor.from_candidate(
            model_plan["model"],
            manifest=checked(model_plan["manifest"]),
            profile=model_plan["runtime_profile"],
            recipe=saved["recipe"],
            output=output / "resident",
        )
        write(
            output / "software-coordinate-binding.json",
            migrate_software_owner(owner, expected_steps=None),
        )
        task(output, "restore-original-complete-common", "boundary")
        common = read_json(checked(plan["common"]))
        restored = restore_common(owner, checked(common["common"]).parent)
        if (
            restored["state_sha256"] != common["state_tensor_digest"]
            or restored["rng_sha256"] != common["training_rng_sha256"]
            or restored["actor_identity"] != plan["expected_actor_identity"]
            or (owner.actor_steps, owner.critic_steps) != (3, 3)
        ):
            raise ValueError("All organization conditions must use the exact original 3/3 common")
        write(output / "common-restore.json", restored)

        def forbidden(*args, **kwargs):
            raise RuntimeError("Learning computation is disabled for organization development")

        owner.learning_logprobs = forbidden
        owner.update_window = forbidden
        report.update(status="running", common_restored_exactly=True)
        inventory = plan["assignments"][worker]
        for unit in inventory:
            if mechanism_pauses(root):
                report["status"] = "paused_before_next_slot"
                break
            task(output, unit["slot_id"] + "-environment-prepare", "boundary")
            folder = output / "episodes" / unit["slot_id"]
            case = case_spec(
                unit["case_id"], condition=unit["condition"], first_member=unit["first_member"]
            )
            prepared = build_software_collaboration_case(case, folder / "prepared")
            task(output, unit["slot_id"], "episode")
            row = collect_episode(
                owner,
                prepared,
                folder,
                sampling_seed=unit["sampling_seed"],
                slot_id=unit["slot_id"],
            )
            task(output, unit["slot_id"] + "-evidence", "boundary")
            if row["status"] == "closed":
                from scripts.measure_organization_work_v045 import measure_episode

                write(folder / "work-use.json", measure_episode(folder))
            from scripts.measure_organization_feedback_v045r1 import (
                measure_episode as measure_feedback,
            )

            feedback = measure_feedback(folder)
            write(folder / "feedback-loop.json", feedback)
            rows.append({**unit, **row})
            write(output / "progress.json", rows)
            write(output / "report.json", report)
            from scripts.software_organization_stop_policy_v045 import assess_episode

            assessment = assess_episode(folder, row=row, feedback=feedback)
            decision = record_policy_assessment(root, worker, unit["slot_id"], folder, assessment)
            if decision:
                report["status"] = decision
                break
        else:
            report["status"] = "complete"
        task(output, "final-frozen-state-boundary", "boundary")
    except BaseException as error:
        report.update(
            status="execution_error", error={"type": type(error).__name__, "message": str(error)}
        )
        write(
            root / "mechanism-stops" / (worker + "-execution.json"),
            {
                "kind": "execution_fault",
                "reason": "worker_exception",
                "worker": worker,
                "observed_at": time.time(),
                "error": report["error"],
            },
        )
        raise
    finally:
        if owner is not None:
            report.update(
                actor_steps=owner.actor_steps,
                critic_steps=owner.critic_steps,
                new_actor_steps=max(0, owner.actor_steps - 3),
                new_critic_steps=max(0, owner.critic_steps - 3),
                final_actor_identity=owner._make_identity(),
                actor_identity_unchanged=owner._make_identity() == plan["expected_actor_identity"],
            )
        report.update(ended_at=time.time(), source_after=code_identity())
        write(output / "report.json", report)
    return report


def supervise(root):
    root = Path(root).resolve()
    plan = frozen(root)
    summary = {
        "version": VERSION,
        "status": "waiting",
        "started_at": time.time(),
        "observer_pid": os.getpid(),
        "source": plan["source"],
        "states": {
            name: {"worker": name, "status": "not_started", "attempted": False} for name in WORKERS
        },
    }
    active, logs, guards, stable = {}, {}, {}, {}

    def publish():
        summary.update(
            observed_at=time.time(),
            closed_worker_gpu_seconds=sum(
                s.get("elapsed_gpu_seconds", 0) for s in summary["states"].values()
            ),
            running_worker_gpu_seconds=sum(
                time.time() - summary["states"][n]["started_at"] for n in active
            ),
        )
        write(root / "supervisor.json", summary)

    def close(name, reason):
        process = active.pop(name)
        state = summary["states"][name]
        if process.poll() is None:
            support.continuation._stop_worker(process, state)
        process.wait(timeout=15)
        result = read(root / name / "actual/report.json") or {}
        complete = (
            process.returncode == 0
            and reason is None
            and result.get("status") == "complete"
            and result.get("source_before") == result.get("source_after") == plan["source"]
            and result.get("actor_identity_unchanged") is True
            and result.get("new_actor_steps") == result.get("new_critic_steps") == 0
        )
        ended = time.time()
        state.update(
            status="complete" if complete else "stopped",
            stop_reason=reason,
            exit_code=process.returncode,
            ended_at=ended,
            elapsed_gpu_seconds=ended - state["started_at"],
        )
        logs.pop(name).close()
        if not complete:
            normal_pause = (
                process.returncode == 0
                and reason is None
                and result.get("source_before") == result.get("source_after") == plan["source"]
                and result.get("actor_identity_unchanged") is True
                and result.get("new_actor_steps") == result.get("new_critic_steps") == 0
            )
            kind = result.get("status") if normal_pause else "execution_fault"
            if kind not in {"measurement_pending", "global_pause", "paused_before_next_slot"}:
                kind = "execution_fault"
            write(
                root / "mechanism-stops" / (name + "-supervisor.json"),
                {
                    "kind": kind,
                    "reason": reason or result.get("status", "worker_incomplete"),
                    "worker": name,
                    "observed_at": ended,
                    "worker_state": state,
                },
            )
        publish()

    with lock(root):
        if (root / "supervisor.json").exists():
            raise FileExistsError(
                "A started organization inventory is never automatically replayed"
            )
        publish()
        try:
            while True:
                for name, process in list(active.items()):
                    if process.poll() is not None:
                        close(name, None if process.returncode == 0 else "worker_exit_error")
                if mechanism_pauses(root):
                    summary["mechanism_pauses"] = [
                        reference(path) for path in mechanism_pauses(root)
                    ]
                    for state in summary["states"].values():
                        if state["status"] == "not_started":
                            state.update(
                                status="stopped",
                                stop_reason="unopened_work_paused",
                                elapsed_gpu_seconds=0,
                            )
                if all(s["status"] in {"complete", "stopped"} for s in summary["states"].values()):
                    summary["status"] = (
                        "complete"
                        if all(s["status"] == "complete" for s in summary["states"].values())
                        else "closed_with_unknowns"
                    )
                    break
                size = sum(
                    artifact_bytes(Path(path))
                    for path in support.dense._artifact_roots([*plan["prior_artifact_roots"], root])
                )
                free = shutil.disk_usage(root).free
                if size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                    for name in list(active):
                        close(name, "trajectory_storage_reserve")
                    for state in summary["states"].values():
                        if state["status"] == "not_started":
                            state.update(
                                status="stopped",
                                stop_reason="trajectory_storage_reserve",
                                elapsed_gpu_seconds=0,
                            )
                    summary["status"] = "trajectory_storage_reserve"
                    break
                waiting = eligible_workers(summary["states"], summary.get("first_block_gate"))
                if waiting:
                    sample = allowed_resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    cards = available_cards(
                        plan, sample, [summary["states"][n]["gpu"] for n in active]
                    )
                    now = time.time()
                    stable = {c["index"]: stable.get(c["index"], now) for c in cards}
                    for card in cards:
                        if not waiting or len(active) >= LIMITS["max_parallel_model_instances"]:
                            break
                        if now - stable[card["index"]] < LIMITS["gpu_capacity_stability_seconds"]:
                            continue
                        if mechanism_pauses(root):
                            break
                        name = waiting.pop(0)
                        folder = root / name
                        folder.mkdir(exist_ok=False)
                        argv = [
                            sys.executable,
                            "-m",
                            "scripts.software_organization_resume_v045",
                            "worker",
                            "--run-root",
                            str(root),
                            "--worker",
                            name,
                            "--output",
                            str(folder / "actual"),
                        ]
                        logs[name] = (folder / "worker.log").open("x")
                        temporary = folder / "tmp"
                        temporary.mkdir()
                        env = worker_env(plan, card["index"])
                        env.update(TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
                        process = subprocess.Popen(
                            argv,
                            cwd=SOURCE,
                            env=env,
                            stdin=subprocess.DEVNULL,
                            stdout=logs[name],
                            stderr=subprocess.STDOUT,
                            start_new_session=True,
                        )
                        identity = worker_identity(process.pid)
                        summary["states"][name].update(
                            status="running",
                            attempted=True,
                            gpu=card["index"],
                            gpu_uuid=card["uuid"],
                            pid=process.pid,
                            process_identity=identity,
                            started_at=time.time(),
                            command=argv,
                        )
                        active[name] = process
                        guards[name] = TelemetryGuard(
                            card["index"],
                            card["uuid"],
                            identity["start_ticks"],
                            worker_pid=process.pid,
                        )
                        publish()
                if active:
                    with ThreadPoolExecutor(max_workers=3) as pool:
                        futures = {
                            n: pool.submit(
                                target_resources, summary["states"][n]["gpu"], worker_pid=p.pid
                            )
                            for n, p in active.items()
                        }
                        samples = {n: f.result() for n, f in futures.items()}
                    for name, process in list(active.items()):
                        if process.poll() is not None:
                            close(name, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = summary["states"][name]
                        guard = guards[name].observe(
                            samples[name],
                            time.time(),
                            process.pid,
                            state["gpu"],
                            own_memory_limit_mib=LIMITS["own_gpu_memory_mib"],
                        )
                        current = read(root / name / "actual/task.json") or {
                            "kind": "loading",
                            "started_at": state["started_at"],
                        }
                        own_rss = rss(process.pid)
                        reason = guard.get("stop_reason") or live_free_stop_reason(
                            samples[name], state["gpu"]
                        )
                        cap = LIMITS["task_seconds"].get(current.get("kind"))
                        if cap is None:
                            reason = reason or "unknown_task_kind"
                        elif time.time() - current["started_at"] >= cap:
                            reason = reason or "single_task_budget"
                        elif own_rss > LIMITS["host_rss_per_worker_bytes"]:
                            reason = reason or "host_memory_budget"
                        with (root / name / "resources.jsonl").open("a") as stream:
                            stream.write(
                                json.dumps(
                                    {
                                        "sample": samples[name],
                                        "guard": guard,
                                        "task": current,
                                        "rss_bytes": own_rss,
                                        "artifact_bytes": size,
                                        "volume_free_bytes": free,
                                    }
                                )
                                + "\n"
                            )
                        if reason:
                            close(name, reason)
                summary["status"] = "running" if active else "waiting"
                publish()
                time.sleep(LIMITS["poll_seconds"])
        except BaseException as error:
            summary.update(
                status="interrupted", error={"type": type(error).__name__, "message": str(error)}
            )
            for name in list(active):
                close(name, "supervisor_interrupted")
            raise
        finally:
            summary["ended_at"] = time.time()
            publish()
    return summary


def merge_rows(retained, new):
    if (
        len(retained) != 1
        or retained[0].get("slot_id") != RETAINED_SLOT
        or any(r.get("slot_id") == RETAINED_SLOT for r in new)
    ):
        raise ValueError("Retain exactly the original first slot; never replay it")
    rows = retained + new
    summary = original.summarize_rows(rows)
    index = {r["slot_id"]: r for r in rows}
    return [
        index[u["slot_id"]] for units in original.assignments().values() for u in units
    ], summary


def results(root):
    root = Path(root).resolve()
    plan = read_json(root / "plan.json")
    state = read(root / "supervisor.json") or {"status": "prepared", "states": {}}
    old_root = Path(plan["original_run_root"])
    old_state = read_json(old_root / "supervisor.json")
    first = original.assignments()["block-r0-s0"][:1]
    retained = accounting.recorded_rows(old_root, old_state, "block-r0-s0", first)
    review = read_json(checked(plan["first_slot_review"]))
    retained[0].update(
        execution_phase="retained_first_slot",
        original_feedback_loop=review["prior_feedback"],
        corrected_feedback_loop=review["revised_feedback"],
        feedback_loop=read_json(checked(review["revised_feedback"])),
        historical_batch_stop_assessment=review["prior_batch_stop"],
        batch_stop_assessment=read_json(checked(review["revised_batch_stop"])),
    )
    new = []
    for worker, units in assignments().items():
        for row in accounting.recorded_rows(root, state, worker, units):
            row.update(
                execution_phase="original_remaining_twenty_three",
                batch_stop_assessment=read(
                    root
                    / worker
                    / "actual/episodes"
                    / row["slot_id"]
                    / "batch-stop-assessment.json"
                ),
            )
            new.append(row)
    rows, summary = merge_rows(retained, new)
    phases = {
        "retained_first_slot": accounting.usage_cost(retained, old_state, ("block-r0-s0",)),
        "original_remaining_twenty_three": accounting.usage_cost(new, state, WORKERS),
    }
    total = accounting.usage_cost(rows, {"states": {}}, ())
    for key in ("closed_worker_gpu_seconds", "running_worker_gpu_seconds"):
        total[key] = sum(p[key] for p in phases.values())
    workers = {
        phase + "/" + worker: {
            "phase": phase,
            "worker": worker,
            "state": status["states"].get(worker, {}),
            "report": read(folder / worker / "actual/report.json"),
        }
        for phase, folder, status, names in (
            ("retained_first_slot", old_root, old_state, ("block-r0-s0",)),
            ("original_remaining_twenty_three", root, state, WORKERS),
        )
        for worker in names
    }
    return {
        "version": VERSION,
        "status": state["status"],
        "source": plan["source"],
        "original_execution_source": plan["original_execution_source"],
        "plan": reference(root / "plan.json"),
        "rows": rows,
        **summary,
        "scheduled": 24,
        "new_scheduled": 23,
        "retained": 1,
        "known": sum(accounting.known(r) for r in rows),
        "new_known": sum(accounting.known(r) for r in new),
        "workers": workers,
        "supervisor": state,
        "cost": total,
        "cost_partitions": phases,
        "budget_caps": budget_caps(),
        "first_slot_review": plan["first_slot_review"],
        "historical_mechanism_pauses": [
            reference(p) for p in sorted((old_root / "mechanism-stops").glob("*.json"))
        ],
        "mechanism_pauses": [read_json(p) for p in mechanism_pauses(root)],
        "source_partition": plan["source_partition"],
        "batch_stop_policy": plan["batch_stop_policy"],
        "new_actor_steps": sum(
            (w["report"] or {}).get("new_actor_steps", 0) for w in workers.values()
        ),
        "new_critic_steps": sum(
            (w["report"] or {}).get("new_critic_steps", 0) for w in workers.values()
        ),
        "new_backward_calls": 0,
        "allowed_physical_gpus": list(GPU_ORDER),
        "training_eligible": False,
        "contribution_eligible": False,
        "independent_confirmation_eligible": False,
        "optional_probe": plan["optional_probe"],
        "automatic_successors": [],
        "scope": "Original24 only, firstS1 retained and23 unstarted slots continued after host interface measurement correction. No model-visible or local/global-stop policy change. All failures, context endings and actual costs remain; eight-block regime diagnostics, not training benefits.",
    }


def report(root, destination):
    value = results(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    write(destination / "software-organization-v045-resume.json", value)
    lines = [
        "# v0.45原23槽接续与完整库存",
        "",
        f"状态 `{value['status']}`；新增已知{value['new_known']}/23，原唯一库存已知{value['known']}/24。",
        "",
        "首槽S1成功、7调用/87890token保留。旧测量误要求v042接口标签，实际v045输入因此被判投影违规；旧global_pause原件保留。新增隔离测量只修严格接口身份绑定，原投影/分页/退休/停止算法及src工作条件不变。首槽7输入只读核对通过后接续23未启动槽，不重采首槽，不转其未用412110token。",
        "",
        "| 制度 | 已知/8 | 成功 | 固定提交 | 完整均值R |",
        "|---|---:|---:|---:|---:|",
    ]
    for condition, row in value["by_condition"].items():
        lines.append(
            f"| {condition} | {row['known']}/8 | {row['successes']} | {row['submitted_known']} | {row['mean_R']} |"
        )
    lines += ["", "| 块 | S1 | F2 | O3 | F2−S1 | O3−F2 |", "|---|---:|---:|---:|---:|---:|"]
    for block in value["paired_blocks"]:
        lines.append(
            "| "
            + block["block_id"]
            + " | "
            + " | ".join(str(block["R"][c]) for c in CONDITIONS)
            + f" | {block['F2_minus_S1']} | {block['O3_minus_F2']} |"
        )
    lines += [
        "",
        f"八块等权均差：`{value['full_inventory_mean_contrasts']}`。所需结果未齐保持null，未启动不填0，不筛无context子集。",
        "",
        "四个人工业务root来自两个相关任务家族。F2−S1是含多私有历史与协调开销的制度组合比较；O3−F2是动态人数选择权，未增员时不推断实际增员收益。S1无伙伴是正常制度，不作为协作失败。",
        "",
        "| slot | 阶段 | 状态 | R | 提交 | 决定/调用 | 实际token | 宿主决定 | 已证实使用 | 连至固定交付 | 语义待审 |",
        "|---|---|---|---:|---|---|---:|---|---|---|---:|",
    ]
    for row in value["rows"]:
        u = row.get("usage", {})
        work = row.get("work_use") or {}
        lines.append(
            f"| {row['slot_id']} | {row['execution_phase']} | {row['status']} | {row['R']} | {row.get('submitted')} | {u.get('decisions')}/{u.get('attempts')} | {u.get('total_tokens')} | {(row.get('batch_stop_assessment') or {}).get('decision')} | {work.get('has_evidenced_cross_member_chain')} | {work.get('has_use_linked_to_final_fixed_delivery')} | {len(work.get('pending_semantic_relations', [])) if work else None} |"
        )
    lines += [
        "",
        f"新暂停：`{value['mechanism_pauses']}`。旧暂停另存不改；安全局部资源終止仍留在对应槽，真实完整性故障/缺证依原规则暂停。",
        "",
        f"全部实际费用：`{value['cost']}`。首阶段与本阶段worker分阶段计一次；GPU未按条件分摊为null，CPU/测试/验收子时不重复加GPU占用。",
        "",
        "仅物理GPU3/4/5/7、最多3驻留；新23上限2944决定/attempt、11500000token、736tests。加首槽实际上界2951决定/attempt、11587890token、738tests。",
        "",
        f"新增actor/critic/反向 {value['new_actor_steps']}/{value['new_critic_steps']}/{value['new_backward_calls']}，训练/Contribution/独立确认资格false；C/A探针未启用，旧队列暂停，无自动后继。",
        "",
        "[接续协议](software-organization-v045-resume-protocol.md) · [原协议](software-organization-v045-protocol.md) · [原首槽自动报告](software-organization-v045.md)",
        "",
    ]
    (destination / "software-organization-v045-resume.md").write_text("\n".join(lines))
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
        state.update(
            status="execution_error", error={"type": type(caught).__name__, "message": str(caught)}
        )
    finally:
        try:
            state["report_status"] = report(root, report_repo / "docs/experiments")["status"]
            state["publication"] = support.publish_report_paths(
                report_repo,
                REPORT_PATHS,
                "docs: record original v045 twenty-three-slot continuation results",
            )
        except BaseException as caught:
            state["reporting_error"] = {"type": type(caught).__name__, "message": str(caught)}
        state["ended_at"] = time.time()
        write(path, state)
    if error is not None:
        raise error
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("qualify", "prepare", "worker", "supervise", "report", "finish")
    )
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--data-root", type=Path, default=SOURCE)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--worker")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report-repo", type=Path)
    args = parser.parse_args()

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    if args.mode == "qualify":
        result = qualify(args.output, args.admission)
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
