"""Eight frozen contemporaneous representation slots over unchanged v047 world."""
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
from scripts import software_organization_admission_v048 as admission
from scripts.software_allocation_v037 import available_cards, live_free_stop_reason
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write
from scripts.software_development_v028 import task

VERSION = "software-organization-representation-diagnostic-v0.48"
SOURCE = Path(__file__).resolve().parents[1]
GPU_ORDER = (3, 4, 5, 7)
CONDITIONS = ("S1", "P4")
REPRESENTATIONS = ("Gamma0", "Gamma1")
ROOT_LABELS = ("LA", "LB")
SEEDS = (202610120481, 202610120482)
WORKERS = ("root-LA", "root-LB")
LIMITS = {**copy.deepcopy(prior.LIMITS), "max_new_episodes": 8,
          "max_parallel_model_instances": 3,
          "task_seconds": {"loading": 900, "episode": 6000, "boundary": 600}}
DEADLINES = {"soft_seconds": 5400, "hard_seconds": 6000, "close_window_seconds": 600}
checked, source_files = original.checked, original.source_files


def assignments():
    result = {}
    orders = (("S1-G0", "S1-G1", "P4-G0", "P4-G1"),
              ("P4-G1", "P4-G0", "S1-G1", "S1-G0"))
    for root, index, seed, order in zip(ROOT_LABELS, (0, 2), SEEDS, orders, strict=True):
        result["root-" + root] = []
        for key in order:
            condition, arm = key.split("-")
            result["root-" + root].append({
                "slot_id": f"org48-{root}-{condition}-{arm}-B500000",
                "case_id": CASE_IDS[index], "root_id": root, "root_label": root,
                "root_index": index,
                "source_family": "artificial_event_interface" if index == 0 else "artificial_rule_interface",
                "condition": condition, "representation": "Gamma" + arm[-1],
                "sampling_seed": seed, "first_member": "member_001",
                "team_token_budget": 500000})
    return result


def budget_caps():
    return {"new": {"slots": 8, "total_tokens": 4000000, "decisions": 1024,
                    "attempts": 1024, "run_tests": 256},
            "new_qualification_model_calls": 0, "new_qualification_actual_tokens": 0,
            "transfer_old_unused": False, "automatic_successors": []}


def cases_for(inventory):
    from proworksim.software_organization_v047 import case_spec
    return {name: [case_spec(u["case_id"], condition=u["condition"],
                            team_token_budget=u["team_token_budget"], first_member=u["first_member"])
                   for u in units] for name, units in inventory.items()}


def prepare(data_root, root, admission_path):
    from scripts.software_organization_stop_policy_v048 import VERSION as stop_policy_version

    data_root, root = Path(data_root).resolve(), Path(root).resolve()
    if root.exists():
        raise FileExistsError("New v048 inventory must not overwrite or replay an attempted pilot")
    admitted = admission.validate_admission(admission_path, source_root=SOURCE)
    parent = read_json(checked(admitted["parent_plan"]))
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Commit all new v048 code and protocol before model work")
    qualified = admitted["capacity_qualification"]
    inventory = assignments()
    plan = {"version": VERSION, "purpose": "same_input_exact_field_reference_diagnostic",
        "created_at": time.time(), "source": source, "source_root": str(SOURCE), "data_root": str(data_root),
        "source_files": source_files(), "admission": reference(admission_path),
        "parent_plan": admitted["parent_plan"], "original_plan": parent["original_plan"],
        "audit": admitted["audit"], "candidate": admitted["candidate"], "common": parent["common"],
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
        "scheduling": "Two independent root workers, each running its four frozen slots in order. At most three residents; no result-based selection or replay.",
        "order_provenance": "Seeds are from the pasted audit. The inaccessible external JSON was not read. LA direct and LB reverse orders are locally frozen before candidate implementation.",
        "sampling": "Original complete common3/3 loaded once per resident; original guard and one seed reset per fresh episode, no birth/phase reseed or parameter update.",
        "estimands": {"R_joint": "Final unique fixed submission under shared token and 90+10 minute policy",
            "R_token": "Equal to R_joint only without administrative work censoring; otherwise null even for known joint success",
            "Q_joint": "Fraction of original private contractual checks passed by the unique valid fixed submission; zero for normal no submission or process-invalid result; null when technical unknown",
            "Q_token": "Q_joint only without administrative work censoring",
            "unknown_interval": "Each condition/representation retains both planned roots; missing outcomes remain null and identification bounds are not confidence intervals"},
        "authorization": "User requested the v047 audit revision and its one representation candidate with eight conditional new slots on 2026-10-12. No old C resumption or learning queue.",
        "training_eligible": False, "contribution_eligible": False, "independent_confirmation_eligible": False,
        "automatic_retries": False, "automatic_successors": [], "old_training_queues_remain_paused": True,
        "shared_gpu_capacity_allowed": True, "gpu_seconds_cap": None, "worker_seconds_cap": None, "wall_deadline": None,
        "prior_artifact_roots": support.dense._artifact_roots([*parent["prior_artifact_roots"],
            data_root / "runs/software-organization-v046", data_root / "runs/software-organization-capacity-qualification-v046",
            data_root / "runs/v046-final-analysis", data_root / "runs/v047-controls",
            data_root / "runs/software-organization-v047", data_root / "runs/v047-final-analysis",
            data_root / "runs/v048-controls"])}
    plan["plan_sha256"] = digest(json_bytes(plan))
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    from scripts.software_organization_stop_policy_v048 import VERSION as stop_policy_version

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
    if plan.get("candidate") != admitted["candidate"]:
        raise ValueError("Frozen representation candidate changed")
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
    for key in ("original_plan", "audit", "candidate", "common", "reused_model_qualification", "qualification_capacity_binding"):
        checked(plan[key])
    return plan


def mechanism_pauses(root):
    return sorted((Path(root) / "mechanism-stops").glob("*.json"))


def eligible_workers(states, gate=None):
    del gate
    return [name for name in WORKERS if states[name]["status"] == "not_started"]


def require_worker_release(root, worker, plan):
    if (worker not in WORKERS or mechanism_pauses(root)
            or plan.get("assignments") != assignments()):
        raise ValueError("Only authorized unopened v048 inventory may start")


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



def representation_binding(unit, plan):
    if unit not in [u for values in assignments().values() for u in values]:
        raise ValueError("Representation binding requires one exact authorized slot")
    gamma = unit["representation"]
    return {"version": "v048-representation-slot-binding-v1", "slot_id": unit["slot_id"],
            "representation": gamma, "candidate": copy.deepcopy(plan["candidate"]),
            "transport_library": "software_context_v044" if gamma == "Gamma0" else "software_context_v048",
            "base_runtime_library": "software_organization_runtime_v047",
            "library_version_scope": "The unchanged collector context_protocol records its base library version, not this slot's Gamma treatment. Original collector records are preserved.",
            "new_model_qualification_calls": 0, "world_or_prompt_instruction_changes": False}


def transport_factory(unit):
    if unit.get("representation") == "Gamma0":
        return None
    if unit.get("representation") == "Gamma1":
        from proworksim.software_context_v048 import SoftwareContextTransport
        return SoftwareContextTransport
    raise ValueError("Unknown representation treatment")


def aggregate_metrics(plan_units, rows):
    from collections import Counter
    from scripts.software_organization_reporting_v047 import (
        _bounds, classify_outcome, cost_values, outcome_values,
    )
    expected = [u for seq in assignments().values() for u in seq]
    if list(plan_units) != expected:
        raise ValueError("The complete frozen eight-slot denominator is required")
    supplied = {r["slot_id"]: r for r in rows}
    if len(supplied) != len(rows) or not set(supplied) <= {u["slot_id"] for u in expected}:
        raise ValueError("Duplicate or outside result slot")
    entries = []
    for unit in expected:
        row = supplied.get(unit["slot_id"])
        if row and any(row.get(k) != unit[k] for k in
                       ("condition", "representation", "sampling_seed", "team_token_budget")):
            raise ValueError("Result and frozen condition identity disagree")
        entries.append({**unit, "outcome_class": classify_outcome(row),
                        **outcome_values(row), "cost": cost_values(row)})
    configurations, pairs = [], []
    outcomes = ("R_joint", "R_token", "Q_joint", "Q_token")
    for condition in CONDITIONS:
        for gamma in REPRESENTATIONS:
            cell = [r for r in entries if r["condition"] == condition and r["representation"] == gamma]
            costs = [r["cost"]["complete_actual_tokens"] for r in cell]
            configurations.append({"condition": condition, "representation": gamma,
                "planned_roots": 2, "statuses": dict(Counter(r["outcome_class"] for r in cell)),
                "outcomes": {k: _bounds([r[k] for r in cell], binary=k.startswith("R")) for k in outcomes},
                "complete_actual_tokens": sum(costs) if all(v is not None for v in costs) else None})
        for root in ROOT_LABELS:
            low, high = [next(r for r in entries if r["condition"] == condition and
                             r["root_id"] == root and r["representation"] == gamma)
                         for gamma in REPRESENTATIONS]
            pairs.append({"root_id": root, "condition": condition,
                          "Gamma0_slot_id": low["slot_id"], "Gamma1_slot_id": high["slot_id"],
                          **{k + "_delta": high[k] - low[k] if high[k] is not None and low[k] is not None else None
                             for k in outcomes}})
    costs = [r["cost"]["complete_actual_tokens"] for r in entries]
    return {"planned_slots": 8, "slots": entries, "configurations": configurations,
            "representation_pairs": pairs,
            "complete_actual_tokens": sum(costs) if all(v is not None for v in costs) else None,
            "outcomes": {k: _bounds([r[k] for r in entries], binary=k.startswith("R")) for k in outcomes},
            "scope": "Two previously observed artificial roots; mechanism diagnostic, not independent task confirmation or causal cooperation/learning gain."}

def run_worker(root, worker, output):
    root, output = validate_worker_target(root, worker, output)
    plan = frozen(root)
    validate_worker_interpreter(plan)
    require_worker_release(root, worker, plan)
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPU_ORDER)):
        raise ValueError("Only authorized unstarted work on one allowed physical GPU may run")
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.software_learning_v036 import migrate_software_owner, restore_common
    from proworksim.software_organization_runtime_v047 import collect_episode
    from proworksim.software_organization_v047 import build_software_collaboration_case, case_spec
    from scripts.software_organization_capacity_qualification_v046 import apply_capacity_binding

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
            write(folder / "representation-binding.json", representation_binding(unit, plan))
            row = collect_episode(owner, prepared, folder, sampling_seed=unit["sampling_seed"],
                                  slot_id=unit["slot_id"], soft_seconds=5400, hard_seconds=6000,
                                  transport_factory=transport_factory(unit))
            task(output, unit["slot_id"] + "-evidence", "boundary")
            from scripts.measure_organization_work_v047 import measure_episode
            from scripts.measure_organization_feedback_v048 import measure_episode as measure_feedback
            from scripts.software_organization_stop_policy_v048 import assess_episode

            write(folder / "work-use.json", measure_episode(folder))
            feedback = measure_feedback(folder, representation=unit["representation"],
                                        candidate_sha256=plan["candidate"]["sha256"])
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
            "scope": "All eight scheduled slots remain the denominator. Administrative joint results do not fill token outcomes; unknown complete usage remains null. Old qualification and v047 outcomes are not new diagnostic slots."}


def report(root, destination):
    value = results(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    write(destination / "software-organization-v048.json", value)
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
                            "scripts.software_organization_v048",
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
