"""Run the sole C18432 treatment on the four prelocked historical F2 pairs.

Restore the original16K common before explicit capacity metadata binding. No
historical control replay, second length, learning or automatic successor.
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
from proworksim.software_organization_v045 import case_spec
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_support_v036 as support
from scripts.software_allocation_v037 import available_cards, live_free_stop_reason
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write
from scripts.software_development_v028 import task
from scripts import software_organization_v045 as original
from scripts import software_organization_v044 as accounting
from scripts import software_organization_admission_v046 as admission

VERSION = "software-organization-capacity-diagnostic-v0.46"
SOURCE = Path(__file__).resolve().parents[1]
GPU_ORDER = original.GPU_ORDER
WORKERS = admission.WORKERS
LIMITS = {**original.LIMITS, "max_new_episodes": 4}
BASELINE_IDS = admission.BASELINE_IDS
REPORT_PATHS = [
    "docs/experiments/software-organization-v046.md",
    "docs/experiments/software-organization-v046.json",
]
checked, source_files = original.checked, original.source_files


def assignments(plan=None):
    """Runtime always filters the hash-bound historical plan."""
    if plan is None:
        plan = {
            "assignments": original.assignments(),
            "cases": {
                w: [
                    case_spec(
                        u["case_id"], condition=u["condition"], first_member=u["first_member"]
                    )
                    for u in units
                ]
                for w, units in original.assignments().items()
            },
        }
    return admission.paired_inventory(plan)["assignments"]


def budget_caps():
    return admission.budget_caps()


def prepare(data_root, root, admission_path):
    data_root, root = Path(data_root).resolve(), Path(root).resolve()
    if root.exists():
        raise FileExistsError("Fresh v046 treatment root required; no retry or replay")
    admitted = admission.validate_admission(admission_path, source_root=SOURCE)
    parent = read_json(checked(admitted["historical_refs"]["original24_plan"]))
    source = code_identity()
    if (
        source["code_dirty"] is not False
        or source["source_tree_sha256"] != parent["source"]["source_tree_sha256"]
    ):
        raise ValueError(
            "Freeze clean host-only source; native/model-visible src must stay unchanged"
        )
    qualified = admitted["capacity_qualification"]
    from scripts.software_organization_stop_policy_v046 import VERSION as BATCH_STOP_VERSION

    plan = copy.deepcopy(parent)
    plan.pop("plan_sha256", None)
    plan.update(
        version=VERSION,
        purpose="prelocked_four_pair_C18432_capacity_diagnostic",
        source=source,
        source_root=str(SOURCE),
        data_root=str(data_root),
        created_at=time.time(),
        source_files=source_files(),
        capacity_admission=reference(admission_path),
        qualification=admitted["historical_refs"]["model_qualification"],
        cpu_controls=admitted["historical_refs"]["cpu_controls"],
        native_support=admitted["historical_refs"]["native_support"],
        original_plan=admitted["historical_refs"]["original24_plan"],
        original_execution_source=parent["source"],
        original_expected_actor_identity=parent["expected_actor_identity"],
        expected_actor_identity=qualified["capacity_actor_identity"],
        expected_capacity_recipe_sha256=qualified["capacity_recipe_sha256"],
        expected_capacity_profile_sha256=qualified["capacity_profile_sha256"],
        qualification_capacity_binding=qualified["capacity_binding"],
        native_python=str(data_root / "runs/v016-sdk/resident-venv/bin/python"),
        native_python_prefix=qualified["python_prefix"],
        assignments=admitted["remaining_assignments"],
        cases=admitted["remaining_cases"],
        baseline_units=admitted["baseline_units"],
        baseline_refs=admitted["baseline_refs"],
        historical_baseline_actual=admitted["baseline_actual"],
        limits=copy.deepcopy(LIMITS),
        budget_caps=budget_caps(),
        feedback_protocol={**parent["feedback_protocol"], "context_limit": 18432},
        batch_stop_policy={
            **parent["batch_stop_policy"],
            "version": BATCH_STOP_VERSION,
            "capacity_binding": "explicit18432_profile_recipe_after_original_common_restore",
        },
        capacity_treatment={
            "old_context": 16384,
            "context": 18432,
            "reserved_output": 2048,
            "only_recipe_profile_capacity_metadata_changes": True,
            "four_prelocked_pairs": list(BASELINE_IDS),
            "other_lengths": [],
            "post_first_submit_episode_continues": True,
        },
        prior_artifact_roots=support.dense._artifact_roots(
            [
                *parent["prior_artifact_roots"],
                data_root / "runs/software-organization-v045",
                data_root / "runs/software-organization-v045-resume",
                data_root / "runs/software-organization-v045-complete-r1",
                data_root / "runs/v045-complete-r1-final-analysis",
                data_root / "runs/v046-controls",
            ]
        ),
        authorization="User authorized the sole18432 capacity candidate: all four prelocked HA/HB F2 root/seed pairs, including nontriggers, after zero-model support checks and zero-or-one neutral actual qualification. Old controls are reused, not resampled.",
        correction_scope="Only max_length/max_context_tokens and derived profile identity differ after exact original common restoration. All numerical settings, common tensor/optimizer/RNG, work rules, tools, pages, per-slot budget and local stop scope stay unchanged.",
        scheduling="Four independent original root/seed F2 workers, one treatment each, at most3 resident on physical3/4/5/7 under original resource guards. No retries, replacements or automatic successors.",
        optional_probe={
            "enabled": False,
            "this_authorized_module": "C18432",
            "automatic_other_module": False,
        },
        automatic_retries=False,
        automatic_successors=[],
    )
    if plan["assignments"] != assignments(parent):
        raise ValueError("Four-pair treatment inventory changed")
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
        or plan.get("limits") != LIMITS
        or plan.get("budget_caps") != budget_caps()
        or plan.get("gpu_preference") != list(GPU_ORDER)
        or plan.get("automatic_successors") != []
        or plan.get("automatic_retries") is not False
        or any(
            plan.get(k) is not False
            for k in (
                "training_eligible",
                "contribution_eligible",
                "independent_confirmation_eligible",
            )
        )
    ):
        raise ValueError("Frozen sole-capacity source, budgets or stopping scope changed")
    admitted = admission.validate_admission(checked(plan["capacity_admission"]), source_root=SOURCE)
    parent = read_json(checked(plan["original_plan"]))
    for key in admission.DEPENDENCIES:
        expected = (
            plan["original_expected_actor_identity"]
            if key == "expected_actor_identity"
            else plan[key]
        )
        if expected != parent[key]:
            raise ValueError("Original native/common/task dependency changed: " + key)
    if (
        plan["assignments"] != admitted["remaining_assignments"]
        or plan["cases"] != admitted["remaining_cases"]
        or plan["baseline_units"] != admitted["baseline_units"]
        or plan["baseline_refs"] != admitted["baseline_refs"]
        or plan["expected_actor_identity"]
        != admitted["capacity_qualification"]["capacity_actor_identity"]
        or plan["feedback_protocol"] != {**parent["feedback_protocol"], "context_limit": 18432}
    ):
        raise ValueError("Capacity treatment identity or original case changed")
    for key in (
        "qualification",
        "cpu_controls",
        "native_support",
        "qualification_capacity_binding",
        "common",
    ):
        checked(plan[key])
    qualified = admitted["capacity_qualification"]
    if (
        Path(plan["native_python"]).resolve() != Path(qualified["python_executable"]).resolve()
        or Path(plan["native_python_prefix"]).resolve()
        != Path(qualified["python_prefix"]).resolve()
        or plan["expected_capacity_recipe_sha256"] != qualified["capacity_recipe_sha256"]
        or plan["expected_capacity_profile_sha256"] != qualified["capacity_profile_sha256"]
    ):
        raise ValueError("Qualified SDK environment or capacity metadata changed")
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
        raise ValueError("Worker output must be its unique v046 pair")
    if output.exists():
        raise FileExistsError("An attempted v046 treatment may not be replayed")
    return root, output


def validate_worker_interpreter(plan, *, executable=None, prefix=None):
    executable = sys.executable if executable is None else executable
    prefix = sys.prefix if prefix is None else prefix
    if (
        Path(executable).resolve() != Path(plan["native_python"]).resolve()
        or Path(prefix).resolve() != Path(plan["native_python_prefix"]).resolve()
    ):
        raise ValueError("Worker must use the exact qualified original SDK interpreter environment")


def run_worker(root, worker, output):
    root, output = validate_worker_target(root, worker, output)
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.software_learning_v036 import migrate_software_owner, restore_common
    from proworksim.software_organization_runtime_v045 import collect_episode
    from proworksim.software_organization_v045 import build_software_collaboration_case

    root, output = Path(root).resolve(), Path(output).resolve()
    plan = frozen(root)
    validate_worker_interpreter(plan)
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
            or restored["actor_identity"] != plan["original_expected_actor_identity"]
            or (owner.actor_steps, owner.critic_steps) != (3, 3)
        ):
            raise ValueError("All organization conditions must use the exact original 3/3 common")
        write(output / "common-restore.json", restored)
        from scripts.software_organization_capacity_qualification_v046 import apply_capacity_binding

        parent = read_json(checked(plan["original_plan"]))
        binding = apply_capacity_binding(owner, original_plan=parent, common_restore=restored)
        write(output / "capacity-binding.json", binding)
        identity = admission.validate_capacity_binding(binding, parent)
        if (
            identity != plan["expected_actor_identity"]
            or binding["capacity_recipe_sha256"] != plan["expected_capacity_recipe_sha256"]
            or binding["capacity_profile_sha256"] != plan["expected_capacity_profile_sha256"]
        ):
            raise ValueError("Worker differs from the sole qualified capacity metadata binding")
        report.update(
            original_common_actor_identity=restored["actor_identity"],
            capacity_actor_identity=identity,
            capacity_binding=reference(output / "capacity-binding.json"),
        )

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
                from scripts.measure_organization_work_v046 import measure_episode

                write(folder / "work-use.json", measure_episode(folder))
            from scripts.measure_organization_feedback_v046 import (
                measure_episode as measure_feedback,
            )

            feedback = measure_feedback(folder)
            write(folder / "feedback-loop.json", feedback)
            rows.append({**unit, **row})
            write(output / "progress.json", rows)
            write(output / "report.json", report)
            from scripts.software_organization_stop_policy_v046 import assess_episode

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
                            plan["native_python"],
                            "-m",
                            "scripts.software_organization_v046",
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


def summarize_pairs(baselines, treatments):
    if len(baselines) != 4 or [r["slot_id"] for r in baselines] != list(BASELINE_IDS):
        raise ValueError("Exactly the four original historical controls are required")
    expected = {u["slot_id"]: u for units in assignments().values() for u in units}
    if len(treatments) != len({r["slot_id"] for r in treatments}) or set(
        r["slot_id"] for r in treatments
    ) != set(expected):
        raise ValueError(
            "Exactly four unique prelocked treatment identities required, including missing placeholders"
        )
    pairs = []
    byid = {r["slot_id"]: r for r in treatments}
    for baseline, units in zip(baselines, assignments().values(), strict=True):
        unit = units[0]
        row = byid[unit["slot_id"]]
        if (
            not accounting.known(baseline)
            or baseline["R"] != 0
            or baseline["slot_id"] != unit["baseline_slot_id"]
            or any(row.get(k) != v for k, v in unit.items())
        ):
            raise ValueError("Paired identity, seed or historical formal result changed")
        known = accounting.known(row)
        pairs.append(
            {
                "baseline_slot_id": baseline["slot_id"],
                "treatment_slot_id": row["slot_id"],
                "root_label": unit["root_label"],
                "sampling_seed": unit["sampling_seed"],
                "first_member": unit["first_member"],
                "baseline_R": baseline["R"],
                "treatment_R": row["R"] if known else None,
                "difference": row["R"] - baseline["R"] if known else None,
                "baseline_status": baseline["status"],
                "treatment_status": row["status"],
            }
        )
    complete = all(p["difference"] is not None for p in pairs)
    return {
        "pairs": pairs,
        "complete_pairs": sum(p["difference"] is not None for p in pairs),
        "mean_capacity_contrast": sum(p["difference"] for p in pairs) / 4 if complete else None,
        "full_four_pair_comparison_complete": complete,
    }


def results(root):
    root = Path(root).resolve()
    plan = read_json(root / "plan.json")
    state = read(root / "supervisor.json") or {"status": "prepared", "states": {}}
    baselines = []
    for unit, saved in zip(plan["baseline_units"], plan["baseline_refs"], strict=True):
        result = read_json(checked(saved["result"]))
        baselines.append(
            {
                **unit,
                **result,
                "execution_phase": "historical16K_control",
                "result_reference": saved["result"],
            }
        )
    treatments = []
    for worker, units in plan["assignments"].items():
        for row in accounting.recorded_rows(root, state, worker, units):
            row.update(
                execution_phase="new_C18432_treatment",
                batch_stop_assessment=read(
                    root
                    / worker
                    / "actual/episodes"
                    / row["slot_id"]
                    / "batch-stop-assessment.json"
                ),
            )
            treatments.append(row)
    comparison = summarize_pairs(baselines, treatments)
    treatment_cost = accounting.usage_cost(treatments, state, WORKERS)
    baseline_cost = accounting.usage_cost(baselines, {"states": {}}, ())
    baseline_cost.update(
        closed_worker_gpu_seconds=None,
        running_worker_gpu_seconds=None,
        scope="Historical control episode fees only; original workers contained other conditions, so GPU time is not allocated.",
    )
    q = read_json(checked(plan["qualification"]))
    workers = {
        worker: {
            "state": state["states"].get(worker, {}),
            "report": read(root / worker / "actual/report.json"),
        }
        for worker in WORKERS
    }
    new_steps = {
        k: sum((w["report"] or {}).get(k, 0) for w in workers.values())
        for k in ("new_actor_steps", "new_critic_steps", "new_backward_calls")
    }
    return {
        "version": VERSION,
        "status": state["status"],
        "source": plan["source"],
        "plan": reference(root / "plan.json"),
        "historical_baselines": baselines,
        "treatments": treatments,
        **comparison,
        "scheduled": 4,
        "known_treatments": sum(accounting.known(r) for r in treatments),
        "treatment_successes": sum(r["R"] for r in treatments if accounting.known(r)),
        "historical_control_cost": baseline_cost,
        "treatment_cost": treatment_cost,
        "qualification_cost": {
            "new_model_calls": q.get("actual_model_calls"),
            "native_calls_started": q.get("native_calls_started"),
            "usage_complete": q.get("usage_complete"),
            "usage": q.get("usage"),
            "source": plan["qualification"],
        },
        "budget_caps": budget_caps(),
        "workers": workers,
        "supervisor": state,
        "mechanism_pauses": [read_json(p) for p in mechanism_pauses(root)],
        **new_steps,
        "capacity_treatment": plan["capacity_treatment"],
        "feedback_protocol": plan["feedback_protocol"],
        "source_partition": plan["source_partition"],
        "batch_stop_policy": plan["batch_stop_policy"],
        "original_expected_actor_identity": plan["original_expected_actor_identity"],
        "capacity_expected_actor_identity": plan["expected_actor_identity"],
        "allowed_physical_gpus": list(GPU_ORDER),
        "training_eligible": False,
        "contribution_eligible": False,
        "independent_confirmation_eligible": False,
        "automatic_successors": [],
        "scope": "Four prelocked historical16K/F2 controls reused once versus four new18432 treatments from original initial states. Costs are full episodes; first submission does not stop work. Qualification fee is separate. No automatic next length, A, extra seed or training.",
    }


def report(root, destination):
    value = results(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    write(destination / "software-organization-v046.json", value)
    lines = [
        "# v0.46预锁四对C18432容量诊断",
        "",
        f"状态 `{value['status']}`；新处理正式结果已知{value['known_treatments']}/4，成功{value['treatment_successes']}。",
        "",
        f"四对完整均差 ΔC=`{value['mean_capacity_contrast']}`；未齐保持null，不把未启动或技术未知填0。",
        "",
        "原四条F2对照全部保留且不重跑；新增处理包含两个原非触发实例。原16K构造、软件迁移和完整common3/3恢复后，只有recipe/profile容量字段改为18432并生成新容量元数据身份。模型权重、数值路径、工具、3072字符页、退休和每槽500000token/128决定/128attempt/32测试均不变。",
        "",
        "| root | 完整seed | 先手 | 原16K槽/R | 新18432槽/R | 状态 | 差值 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in value["pairs"]:
        lines.append(
            f"| {row['root_label']} | {row['sampling_seed']} | {row['first_member']} | {row['baseline_slot_id']} / {row['baseline_R']} | {row['treatment_slot_id']} / {row['treatment_R']} | {row['treatment_status']} | {row['difference']} |"
        )
    lines += [
        "",
        "首次固定提交不会结束episode，其后活动和实际费用继续记录；本表不是首次交付效率。相同seed不保证后继轨迹相同，不重放旧动作。",
        "",
        f"历史4对照费用（仅引用）：`{value['historical_control_cost']}`。历史对照GPU时间不分摊为null。",
        "",
        f"新4正式处理费用：`{value['treatment_cost']}`。资格费用单列：`{value['qualification_cost']}`。",
        "",
        f"新停止回执：`{value['mechanism_pauses']}`；可信已绑定局部资源终止保持局部，完整性问题和测量未决暂停未开库存。",
        "",
        "新正式上限512决定/attempt、2000000token、128测试；资格最多1请求/18432实际token，总新增上限2018432。原24未用3703444token不转移。仅物理GPU3/4/5/7，最多3驻留，原资源门保持。",
        "",
        f"新增actor/critic/反向：{value['new_actor_steps']}/{value['new_critic_steps']}/{value['new_backward_calls']}。无第二长度、自动A、追加seed、训练或自动后继。",
        "",
        "有限历史配对只回答这两个root、四个root/seed的容量响应。解除一次反馈截断不保证业务完成，文件级使用和新增交付仍需分别核对；不能据R1直接推断协作或经验分配收益。",
        "",
    ]
    (destination / "software-organization-v046.md").write_text(
        "\n".join(lines).replace("None", "null")
    )
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
                "docs: record prelocked v046 C18432 capacity results",
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
    parser.add_argument("mode", choices=("prepare", "worker", "supervise", "report", "finish"))
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--data-root", type=Path, default=SOURCE)
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--worker")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report-repo", type=Path)
    args = parser.parse_args()

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    if args.mode == "prepare":
        prepare(args.data_root, args.run_root, args.admission)
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
