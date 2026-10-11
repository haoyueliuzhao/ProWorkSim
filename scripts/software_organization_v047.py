"""Frozen 28 + 16 architecture/seat and real-budget pilot, with no learning."""
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
from proworksim.software_organization_tasks_v045 import CASE_IDS
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_support_v036 as support
from scripts import software_organization_v045 as original
from scripts import software_organization_v046 as prior
from scripts import software_organization_admission_v046 as capacity_admission
from scripts import software_organization_admission_v047 as admission
from scripts.software_allocation_v037 import available_cards, live_free_stop_reason
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write
from scripts.software_development_v028 import task

VERSION = "software-organization-architecture-pilot-v0.47"
SOURCE = Path(__file__).resolve().parents[1]
GPU_ORDER = (3, 4, 5, 7)
CONDITIONS = ("S1", "D2", "D4", "I2", "I4", "P2", "P4")
HIGH_BUDGET_CONDITIONS = ("S1", "D4", "I4", "P4")
ROOT_LABELS = ("LA", "HA", "LB", "HB")
SEEDS = (202610110471, 202610110472, 202610110473, 202610110474)
WORKERS = tuple(f"stage-{stage}-r{r}" for stage in ("A", "B") for r in range(4))
LIMITS = {**copy.deepcopy(prior.LIMITS), "max_new_episodes": 44,
          "max_parallel_model_instances": 3,
          "task_seconds": {"loading": 900, "episode": 6000, "boundary": 600}}
DEADLINES = {"soft_seconds": 5400, "hard_seconds": 6000, "close_window_seconds": 600}
checked, source_files = original.checked, original.source_files


def assignments():
    result = {}
    for stage, choices, budget in (("A", CONDITIONS, 250000), ("B", HIGH_BUDGET_CONDITIONS, 500000)):
        for r, case_id in enumerate(CASE_IDS):
            shift = (2 * r if stage == "A" else r) % len(choices)
            order = choices[shift:] + choices[:shift]
            result[f"stage-{stage}-r{r}"] = [
                {"slot_id": f"org47-{stage}-r{r}-{condition}-B{budget}",
                 "case_id": case_id, "root_id": ROOT_LABELS[r], "root_label": ROOT_LABELS[r],
                 "root_index": r, "source_family": "artificial_event_interface" if r < 2 else "artificial_rule_interface",
                 "condition": condition, "sampling_seed": SEEDS[r], "first_member": "member_001",
                 "team_token_budget": budget, "stage": stage, "pilot_stage": stage}
                for condition in order]
    return result


def budget_caps():
    return {"stage_A": {"slots": 28, "total_tokens": 7000000, "decisions": 3584, "attempts": 3584, "run_tests": 896},
            "stage_B": {"slots": 16, "total_tokens": 8000000, "decisions": 2048, "attempts": 2048, "run_tests": 512},
            "new": {"slots": 44, "total_tokens": 15000000, "decisions": 5632, "attempts": 5632, "run_tests": 1408},
            "new_qualification_model_calls": 0, "new_qualification_actual_tokens": 0,
            "transfer_old_unused": False, "automatic_successors": []}


def cases_for(inventory):
    from proworksim.software_organization_v047 import case_spec
    return {name: [case_spec(u["case_id"], condition=u["condition"],
                            team_token_budget=u["team_token_budget"], first_member=u["first_member"])
                   for u in units] for name, units in inventory.items()}


def prepare(data_root, root, admission_path):
    from scripts.software_organization_stop_policy_v047 import VERSION as stop_policy_version

    data_root, root = Path(data_root).resolve(), Path(root).resolve()
    if root.exists():
        raise FileExistsError("New v047 inventory must not overwrite or replay an attempted pilot")
    admitted = admission.validate_admission(admission_path, source_root=SOURCE)
    parent = read_json(checked(admitted["parent_plan"]))
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Commit all new v047 code and protocol before model work")
    qualified = admitted["capacity_qualification"]
    inventory = assignments()
    plan = {"version": VERSION, "purpose": "architecture_seats_and_budget_execution_pilot",
        "created_at": time.time(), "source": source, "source_root": str(SOURCE), "data_root": str(data_root),
        "source_files": source_files(), "admission": reference(admission_path),
        "parent_plan": admitted["parent_plan"], "original_plan": parent["original_plan"],
        "audit": admitted["audit"], "common": parent["common"],
        "model_references": copy.deepcopy(parent["model_references"]),
        "expected_state_sha256": parent["expected_state_sha256"],
        "original_expected_actor_identity": parent["original_expected_actor_identity"],
        "expected_actor_identity": qualified["capacity_actor_identity"],
        "expected_capacity_recipe_sha256": qualified["capacity_recipe_sha256"],
        "expected_capacity_profile_sha256": qualified["capacity_profile_sha256"],
        "qualification_capacity_binding": qualified["capacity_binding"],
        "reused_model_qualification": admitted["reused_model_qualification"],
        "new_qualification_model_calls": 0, "new_qualification_actual_tokens": 0,
        "native_python": str(data_root / "runs/v016-sdk/resident-venv/bin/python"),
        "native_python_prefix": qualified["python_prefix"], "runtime_dependency_path": parent["runtime_dependency_path"],
        "source_partition": copy.deepcopy(parent["source_partition"]),
        "business_bindings": copy.deepcopy(parent["business_bindings"]),
        "assignments": inventory, "cases": cases_for(inventory), "limits": copy.deepcopy(LIMITS),
        "budget_caps": budget_caps(), "deadline_policy": copy.deepcopy(DEADLINES), "gpu_preference": list(GPU_ORDER),
        "feedback_protocol": copy.deepcopy(parent["feedback_protocol"]),
        "original_v046_preserved": {"started_technical_unknown": 1, "unstarted": 3, "resumed": False, "R_and_delta_C": None},
        "batch_stop_policy": {"version": stop_policy_version,
            "safe_closed_token_context_stage_or_administrative_stop": "continue_independent_slots",
            "integrity_or_incomplete_billing": "pause_unopened", "unresolved_mechanism": "measurement_pending",
            "outcome_or_birth_or_message_selection": False},
        "scheduling": "Stage A all four root workers before the fixed Stage B list. At most three residents; each worker runs its frozen sequence. No result-based selection or replay.",
        "order_provenance": "The pasted audit's linked machine seed/order proposal was not supplied locally. These four new seeds and cyclic orders are independently frozen before the first pilot model call, not represented as that unavailable JSON.",
        "sampling": "Original complete common3/3 loaded once per resident; original guard and one seed reset per fresh episode, no birth/phase reseed or parameter update.",
        "estimands": {"R_joint": "Final unique fixed submission under shared token and 90+10 minute policy",
            "R_token": "Equal to R_joint only without administrative work censoring; otherwise null even for known joint success",
            "Q_joint": "Fraction of original private contractual checks passed by the unique valid fixed submission; zero for normal no submission or process-invalid result; null when technical unknown",
            "Q_token": "Q_joint only without administrative work censoring",
            "unknown_interval": "[known_successes/4,(known_successes+unknown_count)/4], not a confidence interval"},
        "authorization": "User explicitly requested implementing the v046 audit and subsequent 28+16 architecture/seat/budget pilot on 2026-10-11. No old C resumption or learning queue.",
        "training_eligible": False, "contribution_eligible": False, "independent_confirmation_eligible": False,
        "automatic_retries": False, "automatic_successors": [], "old_training_queues_remain_paused": True,
        "shared_gpu_capacity_allowed": True, "gpu_seconds_cap": None, "worker_seconds_cap": None, "wall_deadline": None,
        "prior_artifact_roots": support.dense._artifact_roots([*parent["prior_artifact_roots"],
            data_root / "runs/software-organization-v046", data_root / "runs/software-organization-capacity-qualification-v046",
            data_root / "runs/v046-final-analysis", data_root / "runs/v047-controls"])}
    plan["plan_sha256"] = digest(json_bytes(plan))
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    from scripts.software_organization_stop_policy_v047 import VERSION as stop_policy_version

    plan = read_json(Path(root) / "plan.json")
    if (plan.get("version") != VERSION
            or plan.get("plan_sha256") != digest(json_bytes({k: v for k, v in plan.items() if k != "plan_sha256"}))
            or plan.get("source") != code_identity() or plan.get("source_files") != source_files()
            or plan.get("assignments") != assignments() or plan.get("cases") != cases_for(assignments())
            or plan.get("limits") != LIMITS or plan.get("deadline_policy") != DEADLINES
            or plan.get("budget_caps") != budget_caps() or plan.get("gpu_preference") != list(GPU_ORDER)
            or plan.get("batch_stop_policy", {}).get("version") != stop_policy_version
            or plan.get("automatic_retries") is not False or plan.get("automatic_successors") != []
            or any(plan.get(k) is not False for k in ("training_eligible", "contribution_eligible", "independent_confirmation_eligible"))):
        raise ValueError("Frozen pilot source, inventory, time/budget policy or outcome selection changed")
    admitted = admission.validate_admission(checked(plan["admission"]), source_root=SOURCE)
    parent = read_json(checked(plan["parent_plan"]))
    for key in ("common", "model_references", "expected_state_sha256", "original_expected_actor_identity",
                "runtime_dependency_path", "source_partition", "business_bindings", "feedback_protocol"):
        if plan[key] != parent[key]:
            raise ValueError("Original common/numerical/business dependency changed: " + key)
    qualified = admitted["capacity_qualification"]
    if (plan["expected_actor_identity"] != qualified["capacity_actor_identity"]
            or plan["expected_capacity_recipe_sha256"] != qualified["capacity_recipe_sha256"]
            or plan["expected_capacity_profile_sha256"] != qualified["capacity_profile_sha256"]
            or Path(plan["native_python"]).resolve() != Path(qualified["python_executable"]).resolve()
            or Path(plan["native_python_prefix"]).resolve() != Path(qualified["python_prefix"]).resolve()):
        raise ValueError("The qualified capacity/numerical environment changed")
    for key in ("original_plan", "audit", "common", "reused_model_qualification", "qualification_capacity_binding"):
        checked(plan[key])
    return plan


def mechanism_pauses(root):
    return sorted((Path(root) / "mechanism-stops").glob("*.json"))


def eligible_workers(states, gate=None):
    del gate
    if any(states[name]["status"] != "complete" for name in WORKERS[:4]):
        return [name for name in WORKERS[:4] if states[name]["status"] == "not_started"]
    return [name for name in WORKERS[4:] if states[name]["status"] == "not_started"]


def require_worker_release(root, worker, plan):
    if worker not in WORKERS or mechanism_pauses(root):
        raise ValueError("Only authorized unopened pilot inventory may start")
    if worker in WORKERS[4:]:
        supervisor = read(Path(root) / "supervisor.json") or {}
        states = supervisor.get("states", {})
        if (supervisor.get("source") != plan["source"]
                or any(states.get(name, {}).get("status") != "complete" for name in WORKERS[:4])):
            raise ValueError("Stage B cannot load before every frozen Stage A worker completed")


def record_policy_assessment(root, worker, slot_id, folder, assessment):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    if (worker not in WORKERS or slot_id not in {u["slot_id"] for u in assignments()[worker]}
            or folder != root / worker / "actual/episodes" / slot_id
            or assessment.get("slot_id") != slot_id
            or assessment.get("decision") not in {"continue", "global_pause", "measurement_pending"}):
        raise ValueError("Policy decision does not bind one original pilot slot")
    destination = folder / "batch-stop-assessment.json"
    if destination.exists():
        raise FileExistsError("Retain original stop receipts")
    write(destination, assessment)
    if assessment["decision"] == "continue":
        return None
    write(root / "mechanism-stops" / (slot_id + ".json"), {
        "kind": assessment["decision"], "reason": "batch_stop_policy_assessment", "slot_id": slot_id,
        "worker": worker, "observed_at": time.time(), "assessment": reference(destination),
        "feedback": reference(folder / "feedback-loop.json"), "result": reference(folder / "slot-result.json")})
    return assessment["decision"]


def validate_worker_target(root, worker, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if worker not in WORKERS or output != root / worker / "actual":
        raise ValueError("Worker must bind one unique pilot root/stage inventory")
    if output.exists():
        raise FileExistsError("Attempted pilot work is never replayed")
    return root, output


def run_worker(root, worker, output):
    root, output = validate_worker_target(root, worker, output)
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.software_learning_v036 import migrate_software_owner, restore_common
    from proworksim.software_organization_runtime_v047 import collect_episode
    from proworksim.software_organization_v047 import build_software_collaboration_case, case_spec
    from scripts.software_organization_capacity_qualification_v046 import apply_capacity_binding

    plan = frozen(root)
    validate_worker_interpreter(plan)
    require_worker_release(root, worker, plan)
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPU_ORDER)):
        raise ValueError("Only authorized unstarted work on one allowed physical GPU may run")
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
        saved, old_plan = read_json(checked(refs["owner"])), read_json(checked(refs["plan"]))
        model_plan = read_json(checked(old_plan["prior_model_plan"]))
        owner = DeterministicCandidateActor.from_candidate(model_plan["model"], manifest=checked(model_plan["manifest"]),
            profile=model_plan["runtime_profile"], recipe=saved["recipe"], output=output / "resident")
        write(output / "software-coordinate-binding.json", migrate_software_owner(owner, expected_steps=None))
        task(output, "restore-original-complete-common", "boundary")
        common = read_json(checked(plan["common"]))
        restored = restore_common(owner, checked(common["common"]).parent)
        if (restored["state_sha256"] != common["state_tensor_digest"]
                or restored["rng_sha256"] != common["training_rng_sha256"]
                or restored["actor_identity"] != plan["original_expected_actor_identity"]
                or (owner.actor_steps, owner.critic_steps) != (3, 3)):
            raise ValueError("Exact original complete common3/3 is required")
        write(output / "common-restore.json", restored)
        original_plan = read_json(checked(plan["original_plan"]))
        binding = apply_capacity_binding(owner, original_plan=original_plan, common_restore=restored)
        write(output / "capacity-binding.json", binding)
        identity = capacity_admission.validate_capacity_binding(binding, original_plan)
        if (identity != plan["expected_actor_identity"]
                or binding["capacity_recipe_sha256"] != plan["expected_capacity_recipe_sha256"]
                or binding["capacity_profile_sha256"] != plan["expected_capacity_profile_sha256"]):
            raise ValueError("Resident differs from the reused numerical/capacity qualification")
        report.update(original_common_actor_identity=restored["actor_identity"], capacity_actor_identity=identity,
                      capacity_binding=reference(output / "capacity-binding.json"))

        def forbidden(*args, **kwargs):
            raise RuntimeError("Learning computation is disabled for this execution pilot")

        owner.learning_logprobs = forbidden
        owner.update_window = forbidden
        report.update(status="running", common_restored_exactly=True)
        write(output / "report.json", report)
        for unit in plan["assignments"][worker]:
            if mechanism_pauses(root):
                report["status"] = "paused_before_next_slot"
                break
            task(output, unit["slot_id"] + "-environment-prepare", "boundary")
            folder = output / "episodes" / unit["slot_id"]
            case = case_spec(unit["case_id"], condition=unit["condition"],
                             team_token_budget=unit["team_token_budget"], first_member=unit["first_member"])
            prepared = build_software_collaboration_case(case, folder / "prepared")
            task(output, unit["slot_id"], "episode")
            row = collect_episode(owner, prepared, folder, sampling_seed=unit["sampling_seed"],
                                  slot_id=unit["slot_id"], soft_seconds=5400, hard_seconds=6000)
            task(output, unit["slot_id"] + "-evidence", "boundary")
            from scripts.measure_organization_work_v047 import measure_episode
            from scripts.measure_organization_feedback_v047 import measure_episode as measure_feedback
            from scripts.software_organization_stop_policy_v047 import assess_episode

            write(folder / "work-use.json", measure_episode(folder))
            feedback = measure_feedback(folder)
            write(folder / "feedback-loop.json", feedback)
            rows.append({**unit, **row})
            write(output / "progress.json", rows)
            write(output / "report.json", report)
            decision = record_policy_assessment(root, worker, unit["slot_id"], folder,
                                                assess_episode(folder, row=row, feedback=feedback))
            if decision:
                report["status"] = decision
                break
        else:
            report["status"] = "complete"
        task(output, "final-frozen-state-boundary", "boundary")
    except BaseException as error:
        report.update(status="execution_error", error={"type": type(error).__name__, "message": str(error)})
        write(root / "mechanism-stops" / (worker + "-execution.json"), {
            "kind": "execution_fault", "reason": "worker_exception", "worker": worker,
            "observed_at": time.time(), "error": report["error"]})
        raise
    finally:
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps,
                new_actor_steps=max(0, owner.actor_steps - 3), new_critic_steps=max(0, owner.critic_steps - 3),
                final_actor_identity=owner._make_identity(), actor_identity_unchanged=owner._make_identity() == plan["expected_actor_identity"])
        report.update(ended_at=time.time(), source_after=code_identity())
        write(output / "report.json", report)
    return report


def results(root):
    from scripts.software_organization_reporting_v047 import aggregate_metrics
    root = Path(root).resolve()
    plan = read_json(root / "plan.json")
    supervisor = read(root / "supervisor.json") or {"status": "prepared", "states": {}}
    rows, workers = [], {}
    for worker, units in plan["assignments"].items():
        state = supervisor.get("states", {}).get(worker, {})
        worker_report = read(root / worker / "actual/report.json")
        workers[worker] = {"state": state, "report": worker_report}
        for unit in units:
            folder = root / worker / "actual/episodes" / unit["slot_id"]
            row = read(folder / "slot-result.json")
            if row is None:
                rows.append({**unit, "status": "technical_unknown" if folder.exists() else "not_started",
                             "R_joint": None, "R_token": None, "Q_joint": None, "Q_token": None,
                             "usage_complete": False if folder.exists() else None,
                             "worker": worker, "episode_folder": str(folder)})
            else:
                rows.append({**unit, **row, "worker": worker, "episode_folder": str(folder),
                    "work_use": read(folder / "work-use.json"), "feedback_loop": read(folder / "feedback-loop.json"),
                    "evaluation_guard": read(folder / "evaluation-guard.json"),
                    "batch_stop_assessment": read(folder / "batch-stop-assessment.json")})
    units = [u for seq in plan["assignments"].values() for u in seq]
    return {"version": VERSION, "status": supervisor["status"], "plan": reference(root / "plan.json"),
            "source": plan["source"], "rows": rows, "metrics": aggregate_metrics(units, rows),
            "supervisor": supervisor, "workers": workers, "budget_caps": plan["budget_caps"],
            "new_qualification_actual_tokens": 0, "new_actor_steps": 0, "new_critic_steps": 0,
            "new_backward_calls": 0, "automatic_successors": [], "old_queues_remain_paused": True,
            "scope": "All44 scheduled denominator. Administrative joint results do not fill token outcomes; unknown usage is never imputed as zero. Historical qualifications/control outcomes are not new pilot runs."}


def report(root, destination):
    value = results(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    write(destination / "software-organization-v047.json", value)
    return value


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

def validate_worker_interpreter(plan, *, executable=None, prefix=None):
    executable = sys.executable if executable is None else executable
    prefix = sys.prefix if prefix is None else prefix
    if (
        Path(executable).resolve() != Path(plan["native_python"]).resolve()
        or Path(prefix).resolve() != Path(plan["native_python_prefix"]).resolve()
    ):
        raise ValueError("Worker must use the exact qualified original SDK interpreter environment")

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
                            "scripts.software_organization_v047",
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
                            reason = reason or ("episode_hard_deadline" if current.get("kind") == "episode" else "single_task_budget")
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "worker", "supervise", "report"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=SOURCE)
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--worker")
    parser.add_argument("--output", type=Path)
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
    else:
        report(args.run_root, args.output)


if __name__ == "__main__":
    main()
