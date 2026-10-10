"""Frozen v045 S1/F2/O3 organization diagnostics on four new artificial roots."""
from __future__ import annotations

import argparse
from collections import Counter
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
from proworksim.software_organization_tasks_v045 import CASE_IDS, build_case, source_partition
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_support_v036 as support
from scripts.software_allocation_v037 import available_cards, live_free_stop_reason
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write
from scripts.software_development_v028 import task
from scripts import software_organization_v044 as original
from scripts.software_organization_stop_policy_v045 import VERSION as BATCH_STOP_POLICY_VERSION

VERSION = "software-organization-diagnostic-v0.45"
SOURCE = Path(__file__).resolve().parents[1]
GPU_ORDER = (3, 4, 5, 7)
SEEDS = (202610100451, 202610100452)
WORKERS = tuple(f"block-r{r}-s{s}" for r in range(4) for s in range(2))
ORDERS = (("S1", "F2", "O3"), ("F2", "O3", "S1"), ("O3", "S1", "F2"),
          ("S1", "O3", "F2"), ("O3", "F2", "S1"), ("F2", "S1", "O3"),
          ("S1", "F2", "O3"), ("F2", "O3", "S1"))
LIMITS = {**copy.deepcopy(original.LIMITS), "max_new_episodes": 24, "max_parallel_model_instances": 3}
REPORT_PATHS = ["docs/experiments/software-organization-v045.md", "docs/experiments/software-organization-v045.json"]


def checked(ref):
    path = Path(ref["path"])
    if not path.is_file() or digest(path.read_bytes()) != ref["sha256"]:
        raise ValueError("Frozen evidence changed: " + str(path))
    return path


def assignments():
    result = {}
    for r, case_id in enumerate(CASE_IDS):
        for s, seed in enumerate(SEEDS):
            result[f"block-r{r}-s{s}"] = [
                {"slot_id": f"org45-r{r}-s{s}-{condition}", "case_id": case_id,
                 "root_label": ("LA", "HA", "LB", "HB")[r],
                 "source_family": "artificial_event_interface" if r < 2 else "artificial_rule_interface",
                 "condition": condition, "sampling_seed": seed,
                 "first_member": "member_001" if condition == "S1" else f"member_{1 + (r+s)%2:03d}"}
                for condition in ORDERS[2*r+s]]
    return result


def budget_caps():
    return {"new": {"decisions": 3072, "attempts": 3072, "total_tokens": 12000000, "run_tests": 768},
            "per_condition": {"decisions": 1024, "attempts": 1024, "total_tokens": 4000000, "run_tests": 256},
            "old_unused_tokens": 487739, "transfer_old_unused": False, "optional_probe_budget_authorized": False}


def source_files():
    paths = [p for folder in ("src", "scripts", "tests") for p in (SOURCE / folder).rglob("*.py")]
    paths += [p for p in (SOURCE / "examples/software-organization-v045").rglob("*")
              if p.is_file() and "__pycache__" not in p.parts]
    return {str(p.relative_to(SOURCE)): digest(p.read_bytes()) for p in sorted(paths)}


def qualify(destination, admission=None):
    from scripts.software_organization_qualification_v045 import qualify as run_qualification
    return run_qualification(destination)


def validate_qualification(path):
    from scripts.software_organization_admission_v045 import validate_admission
    return validate_admission(path, source_root=SOURCE)


def prepare(data_root, root, qualification):
    data_root, root = Path(data_root).resolve(), Path(root).resolve()
    if root.exists():
        raise FileExistsError("New v045 inventory needs a fresh root; no replay")
    validate_qualification(qualification)
    parent_path = data_root / "runs/software-organization-v044-completion/plan.json"
    parent = read_json(parent_path)
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Freeze and commit complete v045 sources before prepare")
    common = read_json(checked(parent["common"]))
    if (common.get("actor_steps"), common.get("critic_steps")) != (3, 3):
        raise ValueError("Original complete common3/3 required")
    plan = {"version": VERSION, "purpose": "frozen_organization_development_diagnostic", "created_at": time.time(),
        "source": source, "source_root": str(SOURCE), "source_files": source_files(), "data_root": str(data_root),
        "qualification": reference(qualification), "prior_audit": reference(SOURCE / "docs/reference/audit-v044-complete-next-v045.md"),
        "parent_plan": reference(parent_path), "common": parent["common"],
        "model_references": copy.deepcopy(parent["model_references"]),
        "expected_actor_identity": parent["expected_actor_identity"], "expected_state_sha256": parent["expected_state_sha256"],
        "runtime_dependency_path": parent["runtime_dependency_path"], "assignments": assignments(),
        "cases": {w: [case_spec(u["case_id"], condition=u["condition"], first_member=u["first_member"]) for u in units]
                  for w, units in assignments().items()},
        "source_partition": source_partition(), "business_bindings": {c: build_case(c)["initial_binding"] for c in CASE_IDS},
        "gpu_preference": list(GPU_ORDER), "limits": copy.deepcopy(LIMITS), "budget_caps": budget_caps(),
        "prior_artifact_roots": support.dense._artifact_roots([*parent["prior_artifact_roots"],
            data_root / "runs/software-organization-v044-completion", data_root / "runs/v044-completion-final-analysis",
            data_root / "runs/v045-controls"]),
        "batch_stop_policy": {"version": BATCH_STOP_POLICY_VERSION, "inherited_semantics": "v044r2",
            "safe_local_context": "retain_member_stop_and_unseen_feedback_continue_independent_slots",
            "integrity_failure": "pause_unopened", "insufficient_evidence": "measurement_pending",
            "uses_outcome_or_submission_for_scope": False},
        "feedback_protocol": {"context_projection": "software-context-v0.44", "pages": "paged-public-test-feedback-v0.42",
            "context_limit": 16384, "output_reservation": 2048, "page_unicode_characters": 3072,
            "protected_margin_diagnostic_only": 1024},
        "authorization": "User requested implementing the complete v044 audit and subsequent experiments on 2026-10-10. Authorize four new artificial roots x two new seeds x S1/F2/O3, exactly 24 frozen-common diagnostic episodes after finite affected CPU controls. No learning, historical replay, automatic optional probe or successor.",
        "order_provenance": "The pasted audit specifies seeds451/452 and 2-or-3 appearances at each position but its linked full order file was not provided locally. This explicit balanced order is frozen here before any model call, not represented as that unavailable file.",
        "sampling": "Restore original common3/3 once per resident, reset each episode and reseed once per episode. No birth reseeding, parameter updates, budget resets or inherited private history.",
        "scheduling": "Eight independent root/seed workers, three fixed conditions each. At most three residents on allowed physical GPUs; sequential calls inside each episode. No success/use/birth gate or automatic replay.",
        "optional_probe": {"enabled": False, "baseline_slots": [u["slot_id"] for units in assignments().values() for u in units
            if u["root_label"] in {"HA", "HB"} and u["condition"] == "F2"], "priority_if_later_authorized": ["C", "A"]},
        "training_eligible": False, "contribution_eligible": False, "independent_confirmation_eligible": False,
        "automatic_retries": False, "automatic_successors": [], "old_training_queues_remain_paused": True,
        "shared_gpu_capacity_allowed": True, "gpu_seconds_cap": None, "worker_seconds_cap": None, "wall_deadline": None}
    plan["plan_sha256"] = digest(json_bytes(plan))
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = read_json(Path(root) / "plan.json")
    if (plan.get("version") != VERSION or plan.get("plan_sha256") != digest(json_bytes({k:v for k,v in plan.items() if k != "plan_sha256"}))
            or plan.get("source") != code_identity() or plan.get("source_files") != source_files()
            or plan.get("assignments") != assignments() or plan.get("limits") != LIMITS
            or plan.get("budget_caps") != budget_caps() or plan.get("gpu_preference") != list(GPU_ORDER)
            or plan.get("automatic_successors") != [] or plan.get("optional_probe", {}).get("enabled") is not False
            or any(plan.get(k) is not False for k in ("training_eligible", "contribution_eligible", "independent_confirmation_eligible"))):
        raise ValueError("Frozen v045 source, inventory or limits changed")
    validate_qualification(checked(plan["qualification"]))
    for key in ("common", "parent_plan", "prior_audit"):
        checked(plan[key])
    expected = {w: [case_spec(u["case_id"], condition=u["condition"], first_member=u["first_member"]) for u in units]
                for w, units in assignments().items()}
    if plan["cases"] != expected or plan["batch_stop_policy"]["version"] != BATCH_STOP_POLICY_VERSION:
        raise ValueError("Scenario or local termination policy changed")
    return plan


def require_worker_release(root, worker, plan):
    if worker not in WORKERS or mechanism_pauses(root):
        raise ValueError("Only authorized unopened v045 work may launch")


def mechanism_pauses(root):
    return sorted((Path(root) / "mechanism-stops").glob("*.json"))

def record_policy_assessment(root, worker, slot_id, folder, assessment):
    """Persist host-only interpretation without rewriting results or feedback."""
    root, folder = Path(root).resolve(), Path(folder).resolve()
    expected = root / worker / "actual/episodes" / slot_id
    if (worker not in WORKERS or slot_id not in {u["slot_id"] for u in assignments()[worker]}
            or folder != expected or assessment.get("slot_id") != slot_id
            or assessment.get("decision") not in {"continue", "global_pause", "measurement_pending"}):
        raise ValueError("Policy receipt does not bind the unique new slot")
    destination = folder / "batch-stop-assessment.json"
    if destination.exists():
        raise FileExistsError("Do not overwrite an existing batch policy assessment")
    write(destination, assessment)
    if assessment["decision"] == "continue":
        return None
    write(root / "mechanism-stops" / (slot_id + ".json"),
          {"kind": assessment["decision"], "reason": "batch_stop_policy_assessment", "slot_id": slot_id,
           "worker": worker, "observed_at": time.time(), "assessment": reference(destination),
           "feedback": reference(folder / "feedback-loop.json"), "result": reference(folder / "slot-result.json")})
    return assessment["decision"]

def eligible_workers(states, gate=None):
    return [name for name in WORKERS if states[name]["status"] == "not_started"]

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
    if worker not in WORKERS or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPU_ORDER)):
        raise ValueError("Require one frozen root shard and one allowed physical GPU")
    require_worker_release(root, worker, plan)
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
        inventory = plan["assignments"][worker]
        for unit in inventory:
            if mechanism_pauses(root):
                report["status"] = "paused_before_next_slot"
                break
            task(output, unit["slot_id"] + "-environment-prepare", "boundary")
            folder = output / "episodes" / unit["slot_id"]
            case = case_spec(unit["case_id"], condition=unit["condition"], first_member=unit["first_member"])
            prepared = build_software_collaboration_case(case, folder / "prepared")
            task(output, unit["slot_id"], "episode")
            row = collect_episode(owner, prepared, folder, sampling_seed=unit["sampling_seed"], slot_id=unit["slot_id"])
            task(output, unit["slot_id"] + "-evidence", "boundary")
            if row["status"] == "closed":
                from scripts.measure_organization_work_v045 import measure_episode
                write(folder / "work-use.json", measure_episode(folder))
            from scripts.measure_organization_feedback_v045 import measure_episode as measure_feedback
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
        report.update(status="execution_error", error={"type": type(error).__name__, "message": str(error)})
        write(root / "mechanism-stops" / (worker + "-execution.json"),
              {"kind": "execution_fault", "reason": "worker_exception", "worker": worker,
               "observed_at": time.time(), "error": report["error"]})
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
        if not complete:
            normal_pause = (process.returncode == 0 and reason is None
                and result.get("source_before") == result.get("source_after") == plan["source"]
                and result.get("actor_identity_unchanged") is True
                and result.get("new_actor_steps") == result.get("new_critic_steps") == 0)
            kind = result.get("status") if normal_pause else "execution_fault"
            if kind not in {"measurement_pending", "global_pause", "paused_before_next_slot"}:
                kind = "execution_fault"
            write(root / "mechanism-stops" / (name + "-supervisor.json"),
                  {"kind": kind, "reason": reason or result.get("status", "worker_incomplete"),
                   "worker": name, "observed_at": ended, "worker_state": state})
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
                if mechanism_pauses(root):
                    summary["mechanism_pauses"] = [reference(path) for path in mechanism_pauses(root)]
                    for state in summary["states"].values():
                        if state["status"] == "not_started":
                            state.update(status="stopped", stop_reason="unopened_work_paused", elapsed_gpu_seconds=0)
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
                waiting = eligible_workers(summary["states"], summary.get("first_block_gate"))
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
                        if mechanism_pauses(root):
                            break
                        name = waiting.pop(0)
                        folder = root / name
                        folder.mkdir(exist_ok=False)
                        argv = [sys.executable, "-m", "scripts.software_organization_v045", "worker",
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
                    with ThreadPoolExecutor(max_workers=3) as pool:
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

def summarize_rows(rows):
    expected = {u['slot_id']: u for units in assignments().values() for u in units}
    if len(rows) != 24 or len({r['slot_id'] for r in rows}) != 24 or set(expected) != {r['slot_id'] for r in rows}:
        raise ValueError('Require all twenty-four unique scheduled identities before indexing')
    for row in rows:
        if any(row.get(k) != u for k, u in expected[row['slot_id']].items()):
            raise ValueError('Scheduled identity mismatch')
    by_condition = {}
    for condition in CONDITIONS:
        selected = [r for r in rows if r['condition'] == condition]
        closed = [r for r in selected if original.known(r)]
        cost = original.usage_cost(selected, {'states': {}}, ())
        cost.update(closed_worker_gpu_seconds=None, running_worker_gpu_seconds=None,
                    gpu_time_scope='Not allocated by condition; use worker/whole-panel timing')
        by_condition[condition] = {'scheduled': 8, 'known': len(closed), 'successes': sum(r['R'] for r in closed),
            'mean_R': sum(r['R'] for r in closed)/8 if len(closed) == 8 else None,
            'observed_mean_R': sum(r['R'] for r in closed)/len(closed) if closed else None,
            'submitted_known': sum(r.get('submitted') is True for r in closed),
            'cross_member_work': dict(Counter(str((r.get('work_use') or {}).get('has_evidenced_cross_member_chain')) for r in selected)),
            'use_linked_to_fixed_delivery': dict(Counter(str((r.get('work_use') or {}).get('has_use_linked_to_final_fixed_delivery')) for r in selected)),
            'pending_semantic_relations_in_measured_slots': sum(len((r.get('work_use') or {}).get('pending_semantic_relations', [])) for r in selected),
            'cost': cost}
    blocks = []
    index = {r['slot_id']: r for r in rows}
    for name, units in assignments().items():
        group = [index[u['slot_id']] for u in units]
        known = all(original.known(r) for r in group)
        scores = {r['condition']: r['R'] if original.known(r) else None for r in group}
        blocks.append({'block_id': name, 'root_label': group[0]['root_label'], 'case_id': group[0]['case_id'],
                       'source_family': group[0]['source_family'], 'sampling_seed': group[0]['sampling_seed'],
                       'R': scores, 'complete': known,
                       'F2_minus_S1': scores['F2']-scores['S1'] if known else None,
                       'O3_minus_F2': scores['O3']-scores['F2'] if known else None})
    return {'by_condition': by_condition, 'paired_blocks': blocks,
            'full_inventory_mean_contrasts': {k: sum(b[k] for b in blocks)/8 if all(b['complete'] for b in blocks) else None
                                              for k in ('F2_minus_S1', 'O3_minus_F2')}}


def results(root):
    root = Path(root).resolve()
    plan = read_json(root / 'plan.json')
    state = read(root / 'supervisor.json') or {'status': 'prepared', 'states': {}}
    rows = []
    for worker, units in assignments().items():
        group = original.recorded_rows(root, state, worker, units)
        for row in group:
            row['batch_stop_assessment'] = read(root / worker / 'actual/episodes' / row['slot_id'] / 'batch-stop-assessment.json')
        rows.extend(group)
    workers = {worker: {'state': state['states'].get(worker, {}), 'report': read(root / worker / 'actual/report.json')}
               for worker in WORKERS}
    return {'version': VERSION, 'status': state['status'], 'source': plan['source'], 'plan': reference(root / 'plan.json'),
        'rows': rows, **summarize_rows(rows), 'workers': workers, 'supervisor': state,
        'scheduled': 24, 'known': sum(original.known(r) for r in rows),
        'source_partition': plan['source_partition'], 'batch_stop_policy': plan['batch_stop_policy'],
        'cost': original.usage_cost(rows, state, WORKERS), 'budget_caps': budget_caps(),
        'mechanism_pauses': [read_json(p) for p in mechanism_pauses(root)],
        'new_actor_steps': sum((w['report'] or {}).get('new_actor_steps', 0) for w in workers.values()),
        'new_critic_steps': sum((w['report'] or {}).get('new_critic_steps', 0) for w in workers.values()),
        'new_backward_calls': 0, 'allowed_physical_gpus': list(GPU_ORDER),
        'training_eligible': False, 'contribution_eligible': False, 'independent_confirmation_eligible': False,
        'optional_probe': plan['optional_probe'], 'automatic_successors': [],
        'scope': 'Four artificial specification roots, two related task families, eight paired development blocks. All failures and local context endings retained. F2-S1 compares a bundled organization regime; O3-F2 compares availability of dynamic population choices. No causal contribution/learning or general effect claim.'}


def report(root, destination):
    value = results(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    write(destination / 'software-organization-v045.json', value)
    lines = ['# v0.45 冻结模型组织诊断', '',
        f"状态 `{value['status']}`；已知 `{value['known']}/24`。四个人工派生业务root、两个任务家族、两个seed，八个配对块。", '',
        'S1真实单成员；F2固定两名出生集合、可退休不补员；O3初始两名、活动≤4、累计≤6。同根目标与公共事实、中性说明、空任务表，允许集中完成。', '',
        '原9B完整common3/3冻结；16K/2048、3072精确分页，每槽128决定/attempt、500000实际token、32测试；不转旧预算。', '',
        '| 条件 | 已知/8 | 成功 | 提交 | 完整条件均值 |', '|---|---:|---:|---:|---:|']
    for c, row in value['by_condition'].items():
        lines.append(f"| {c} | {row['known']}/8 | {row['successes']} | {row['submitted_known']} | {row['mean_R']} |")
    lines += ['', '| 块 | root | S1 | F2 | O3 | F2−S1 | O3−F2 |', '|---|---|---:|---:|---:|---:|---:|']
    for block in value['paired_blocks']:
        lines.append('| '+block['block_id']+' | '+block['root_label']+' | '+' | '.join(str(block['R'][c]) for c in CONDITIONS)
                     +f" | {block['F2_minus_S1']} | {block['O3_minus_F2']} |")
    lines += ['', f"原八块等权均差：`{value['full_inventory_mean_contrasts']}`。必要结果未齐保持null，不填零、不筛context-free子集。", '',
        'F2−S1含多份私有历史、多个行动者与协调开销；O3−F2是动态人数选择权比较。没有实际出生时，不能解释成已测得增员收益。24episode不是24独立任务来源。', '',
        '| slot | 状态 | R | 提交 | 决定/调用 | 实际token | context反馈未见 | 宿主决定 | 已证实使用 | 连至固定交付 | 待审语义关系 |',
        '|---|---|---:|---|---|---:|---:|---|---|---|---:|']
    for row in value['rows']:
        usage = row.get('usage', {})
        facts = (row.get('feedback_loop') or {}).get('mechanism_gate_inputs', {})
        unseen = len(facts['context_blocked_feedback_ids']) if 'context_blocked_feedback_ids' in facts else None
        lines.append(f"| {row['slot_id']} | {row['status']} | {row['R']} | {row.get('submitted')} | {usage.get('decisions')}/{usage.get('attempts')} | {usage.get('total_tokens')} | {unseen} | {(row.get('batch_stop_assessment') or {}).get('decision')} | {(row.get('work_use') or {}).get('has_evidenced_cross_member_chain')} | {(row.get('work_use') or {}).get('has_use_linked_to_final_fixed_delivery')} | {len(row['work_use'].get('pending_semantic_relations', [])) if row.get('work_use') else None} |")
    lines += ['', '当前成果产生、合法公开、实际取得、可核验使用、连至最终固定交付分别记录。初始代码与诊断不冒作成员新成果；阅读不等于使用，合作后失败保留原使用链与失败。', '',
        f"全部实际成本：`{value['cost']}`。未按条件分摊GPU worker时间，条件级对应字段为null。嵌套CPU/测试/验收不重复加到worker GPU时间。", '',
        f"全局暂停：`{value['mechanism_pauses']}`。已知安全局部终止保留成员停止与未呈现反馈，继续其它独立槽；输入、权限、身份、账目、记录或共同服务故障仍暂停，缺证pending。", '',
        f"新增actor/critic/反向：{value['new_actor_steps']}/{value['new_critic_steps']}/{value['new_backward_calls']}。旧训练/Contribution/正式更新/独立确认及缓存生产暂停，无自动后继。", '',
        '额外C/A探针未启用，没有自动追加预算。', '',
        '[冻结协议](software-organization-v045-protocol.md) · [新审计](../reference/audit-v044-complete-next-v045.md)', '']
    (destination / 'software-organization-v045.md').write_text('\n'.join(lines))
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
                "docs: record v045 frozen organization diagnostic results")
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
