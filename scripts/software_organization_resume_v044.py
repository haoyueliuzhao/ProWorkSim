"""Resume only the original twelve unopened v044 slots after read-only repair.

The original four episodes and false gate are immutable. No model-visible change,
new seed, replay, learning, extra qualification episode or automatic successor.
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
from proworksim.software_organization_v042 import CONDITIONS, case_spec
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_support_v036 as support
from scripts.software_allocation_v037 import available_cards, live_free_stop_reason
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write
from scripts.software_development_v028 import task
from scripts import software_organization_v044 as original

VERSION = "software-organization-resume-v0.44-r1"
SOURCE = Path(__file__).resolve().parents[1]
GPU_ORDER = original.GPU_ORDER
FIRST_BLOCK = original.FIRST_BLOCK
WORKERS = tuple(w for w in original.WORKERS if w != FIRST_BLOCK)
LIMITS = {**copy.deepcopy(original.LIMITS), "max_new_episodes": 12, "max_parallel_model_instances": 3}
REPORT_PATHS = ["docs/experiments/software-organization-v044-resume.md", "docs/experiments/software-organization-v044-resume.json"]
NEW_SOURCES = (
    "scripts/measure_organization_feedback_v044r1.py",
    "scripts/software_organization_resume_admission_v044.py",
    "scripts/software_organization_resume_v044.py",
    "tests/test_organization_feedback_v044r1.py",
    "tests/test_software_organization_resume_admission_v044.py",
    "tests/test_software_organization_resume_v044.py",
)


def checked(ref):
    from scripts.software_organization_admission_v044 import EvidenceReader
    return EvidenceReader().path(ref)


def all_assignments():
    return original.assignments()


def assignments():
    return {w: units for w, units in all_assignments().items() if w != FIRST_BLOCK}


def budget_caps():
    old = dict(decisions=150, attempts=144, total_tokens=1892846, run_tests=14)
    new = dict(decisions=1536, attempts=1536, total_tokens=6000000, run_tests=384)
    return {"old_actual": old, "new": new, "combined": {k: old[k] + new[k] for k in old},
            "transfer_old_unused": False, "unused_old_tokens": 107154}


def source_files():
    return {name: digest((SOURCE / name).read_bytes()) for name in NEW_SOURCES}


def qualify(destination, admission):
    from scripts.software_organization_resume_admission_v044 import validate_admission
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    admitted = validate_admission(admission, source_root=SOURCE)
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}
    commands = [[str(SOURCE / ".venv/bin/python"), "-m", "pytest", "-q",
                 *[name for name in NEW_SOURCES if name.startswith("tests/")],
                 "--basetemp", str(destination / "pytest-tmp")],
                [str(SOURCE / ".venv/bin/python"), "-m", "ruff", "check", "src", "tests", "scripts"]]
    receipts = []
    for i, argv in enumerate(commands):
        start = time.time()
        with (destination / f"check-{i}.log").open("x") as stream:
            result = subprocess.run(argv, cwd=SOURCE, env=env, stdout=stream, stderr=subprocess.STDOUT)
        receipts.append({"command": argv, "exit_code": result.returncode,
                         "elapsed_seconds": time.time() - start, "log": reference(destination / f"check-{i}.log")})
    value = {"version": VERSION, "kind": "same_gamma_resume_readonly_controls", "passed":
        admitted["passed"] and all(r["exit_code"] == 0 for r in receipts),
        "admission": reference(admission), "source_files": source_files(), "checks": receipts,
        "new_model_calls": 0, "new_tokenizer_calls": 0, "new_test_or_acceptance_executions": 0,
        "scope": "Read-only retirement binding and original inventory/launch/merge controls only. Reuse original qualification by exact dependencies; no old capacity, page-route, business-test or acceptance replay."}
    write(destination / "qualification.json", value)
    return value


def validate_qualification(path):
    from scripts.software_organization_resume_admission_v044 import validate_admission
    value = read_json(path)
    if (value.get("version") != VERSION or value.get("kind") != "same_gamma_resume_readonly_controls"
            or value.get("passed") is not True or value.get("source_files") != source_files()
            or not value.get("checks") or any(r["exit_code"] != 0 for r in value["checks"])):
        raise ValueError("Require passed source-bound read-only resume controls")
    for row in value["checks"]:
        checked(row["log"])
    validate_admission(checked(value["admission"]), source_root=SOURCE)
    return value


def prepare(data_root, root, qualification):
    data_root, root = Path(data_root).resolve(), Path(root).resolve()
    if root.exists():
        raise FileExistsError("Use a fresh continuation root; no replay")
    qualified = validate_qualification(qualification)
    admitted = read_json(checked(qualified["admission"]))
    old_root = Path(admitted["original_run_root"]).resolve()
    if old_root != data_root / "runs/software-organization-v044":
        raise ValueError("Data root differs from the admitted original run")
    if root == old_root or old_root in root.parents:
        raise ValueError("Continuation must never write inside the immutable original root")
    old = read_json(checked(admitted["original_refs"]["plan"]))
    if Path(admitted["original_refs"]["plan"]["path"]).resolve() != old_root / "plan.json":
        raise ValueError("Admitted original plan path mismatch")
    source = code_identity()
    if source["code_dirty"] is not False or source["source_tree_sha256"] != old["source"]["source_tree_sha256"]:
        raise ValueError("Freeze clean host controls with unchanged model-visible source before prepare")
    # The explicit admission also verifies that these are the original twelve unopened slots.
    if admitted.get("passed") is not True:
        raise ValueError("Require repaired admission")
    plan = copy.deepcopy(old)
    for key in ("plan_sha256", "qualification", "prior_audit"):
        plan.pop(key, None)
    plan.update(version=VERSION, created_at=time.time(), source=source, source_root=str(SOURCE),
        data_root=str(data_root), original_run_root=str(old_root), original_plan=admitted["original_refs"]["plan"],
        original_execution_source=old["source"], original_assignments=old["assignments"],
        assignments=assignments(), cases={w: old["cases"][w] for w in WORKERS}, limits=copy.deepcopy(LIMITS),
        qualification=reference(qualification), resume_admission=qualified["admission"],
        prior_audit=reference(SOURCE / "docs/reference/audit-v044-resume.md"), budget_caps=budget_caps(),
        correction_summary=admitted["revised_first_block"]["summary"],
        prior_artifact_roots=support.dense._artifact_roots([*old["prior_artifact_roots"], old_root,
            data_root / "runs/v044-final-analysis", data_root / "runs/v044-resume-controls"]),
        authorization="2026-10-10 user explicitly requested implementing the v044 audit and conducting subsequent experiments: repair read-only voluntary retirement classification, preserve original four and old false gate, resume only original remaining twelve under identical Gamma after corrected gate/source admission. No new seed, first-block replay, resampling, model-visible change or learning.",
        stage_rule="Corrected original-four mechanism gate is required once. No new first block. Every new slot is checked for real mechanical/integrity failure or measurement pending; stop unopened work without selecting on R, communication, recruitment or normal termination.",
        scheduling="Only the three original unopened blocks, at most three resident workers on physical GPUs 3,4,5,7. Each block retains original order and sequential member calls. Current in-flight episodes may close after a mechanism pause; no next slot may open.",
        seeds="Original 202610100441/202610100442 and org44 identities unchanged; original first four retained once.",
        analysis="Merge unique original sixteen, old-four and new-twelve costs separate and sum once. Full four-block effects only when every required R is known. No automatic successor.")
    if plan["original_assignments"] != all_assignments():
        raise ValueError("Original inventory changed")
    plan["plan_sha256"] = digest(json_bytes(plan))
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = read_json(Path(root) / "plan.json")
    if (plan.get("version") != VERSION
            or plan.get("plan_sha256") != digest(json_bytes({k: v for k, v in plan.items() if k != "plan_sha256"}))
            or plan.get("source") != code_identity() or plan.get("assignments") != assignments()
            or plan.get("original_assignments") != all_assignments()
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != list(GPU_ORDER)
            or plan.get("budget_caps") != budget_caps() or plan.get("automatic_successors") != []
            or plan.get("training_eligible") is not False):
        raise ValueError("Frozen continuation source, inventory or contract changed")
    qualified = validate_qualification(checked(plan["qualification"]))
    if plan["resume_admission"] != qualified["admission"]:
        raise ValueError("Admission mismatch")
    admitted = read_json(checked(plan["resume_admission"]))
    if (plan["original_run_root"] != admitted["original_run_root"]
            or plan["original_plan"] != admitted["original_refs"]["plan"]
            or plan["correction_summary"] != admitted["revised_first_block"]["summary"]
            or plan["assignments"] != admitted["remaining_assignments"]):
        raise ValueError("Continuation proof chain differs from admitted original evidence")
    original_root = Path(plan["original_run_root"]).resolve()
    if Path(root).resolve() == original_root or original_root in Path(root).resolve().parents:
        raise ValueError("Original run root is immutable")
    for key in ("original_plan", "common", "parent_plan", "parent_report", "prior_audit", "correction_summary"):
        checked(plan[key])
    old = read_json(checked(plan["original_plan"]))
    for key in ("model_references", "common", "feedback_protocol", "business_bindings", "source_partition", "runtime_dependency_path"):
        if plan.get(key) != old.get(key):
            raise ValueError("Original model-visible dependency changed: " + key)
    return plan


def require_worker_release(root, worker, plan):
    if worker not in WORKERS or worker == FIRST_BLOCK:
        raise ValueError("Only original unopened twelve may launch")
    validate_qualification(checked(plan["qualification"]))
    if mechanism_pauses(root):
        raise ValueError("Unopened work is paused by execution or measurement evidence")


def mechanism_pauses(root):
    return sorted((Path(root) / "mechanism-stops").glob("*.json"))


def stop_decision(row, feedback):
    """Same mechanical conditions as old gate, without a four-slot batch gate."""
    if row.get("status") != "closed" or type(row.get("R")) is not int or row["R"] not in (0, 1):
        return {"kind": "execution_fault", "reason": "episode_not_closed_with_known_outcome"}
    facts = (feedback or {}).get("mechanism_gate_inputs", {})
    violations = {key: facts[key] for key in ("page_protocol_violations", "projection_violations",
        "feedback_missing_from_first_actual_followup", "context_blocked_feedback_ids") if facts.get(key)}
    if violations:
        return {"kind": "mechanism_fault", "reason": "execution_or_feedback_violation", "details": violations}
    if (not facts.get("resolved") or not facts.get("actual_generated_requests")
            or facts.get("projection_unresolved")
            or facts.get("requests_verified_under_v044") != facts.get("actual_generated_requests")):
        return {"kind": "measurement_pending", "reason": "unresolved_original_evidence_classification",
                "details": facts}
    return None


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
        raise ValueError("Worker output must be its unique original continuation block")
    if output.exists():
        raise FileExistsError("An attempted continuation block may not be replayed")
    return root, output


def run_worker(root, worker, output):
    root, output = validate_worker_target(root, worker, output)
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.software_learning_v036 import migrate_software_owner, restore_common
    from proworksim.software_organization_runtime_v044 import collect_episode
    from proworksim.software_organization_v042 import build_software_collaboration_case

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
            case = case_spec(unit["case_id"], condition=unit["condition"], first_member=unit["first_member"],
                             diagnostic_a_owner=unit["diagnostic_a_owner"])
            prepared = build_software_collaboration_case(case, folder / "prepared")
            task(output, unit["slot_id"], "episode")
            row = collect_episode(owner, prepared, folder, sampling_seed=unit["sampling_seed"], slot_id=unit["slot_id"])
            task(output, unit["slot_id"] + "-evidence", "boundary")
            if row["status"] == "closed":
                from scripts.measure_organization_work_v044 import measure_episode
                write(folder / "work-use.json", measure_episode(folder))
            from scripts.measure_organization_feedback_v044r1 import measure_episode as measure_feedback
            feedback = measure_feedback(folder)
            write(folder / "feedback-loop.json", feedback)
            rows.append({**unit, **row})
            write(output / "progress.json", rows)
            write(output / "report.json", report)
            decision = stop_decision(row, feedback)
            if decision:
                write(root / "mechanism-stops" / (unit["slot_id"] + ".json"),
                      {**decision, "slot_id": unit["slot_id"], "worker": worker, "observed_at": time.time(),
                       "feedback": reference(folder / "feedback-loop.json"), "result": reference(folder / "slot-result.json")})
                report["status"] = decision["kind"]
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
            if kind not in {"measurement_pending", "mechanism_fault", "paused_before_next_slot"}:
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
                        argv = [sys.executable, "-m", "scripts.software_organization_resume_v044", "worker",
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
    expected = {u["slot_id"]: u for units in all_assignments().values() for u in units}
    ids = [row["slot_id"] for row in rows]
    if len(ids) != 16 or len(set(ids)) != 16 or set(ids) != set(expected):
        raise ValueError("Require exactly sixteen distinct original slot identities")
    for row in rows:
        for key in ("condition", "case_id", "sampling_seed", "first_member", "diagnostic_a_owner"):
            if row.get(key) != expected[row["slot_id"]][key]:
                raise ValueError("Original pairing identity changed: " + row["slot_id"] + ":" + key)
    by_condition = {}
    for condition in CONDITIONS:
        subset = [row for row in rows if row["condition"] == condition]
        closed = [row for row in subset if original.known(row)]
        by_condition[condition] = {"scheduled": 4, "known": len(closed), "successes": sum(row["R"] for row in closed),
            "unknown_or_pending": 4 - len(closed), "mean_R": sum(row["R"] for row in closed) / 4 if len(closed) == 4 else None,
            "submitted_known": sum(row["submitted"] is True for row in closed),
            "member_requested_births": sum(row.get("member_lifecycle", {}).get("member_requested_births", 0) for row in subset),
            "episodes_with_work_use_measurement": sum(row.get("work_use") is not None for row in subset),
            "cross_member_work": {"evidenced": sum((row.get("work_use") or {}).get("has_evidenced_cross_member_chain") is True for row in subset),
                "not_evidenced_complete": sum((row.get("work_use") or {}).get("has_evidenced_cross_member_chain") is False for row in subset),
                "unknown_or_unmeasured": sum((row.get("work_use") or {}).get("has_evidenced_cross_member_chain") is None for row in subset)},
            "action_errors": {key: sum(row.get("action_error_policy", {}).get(key, 0) for row in subset)
                for key in ("recoverable_unknown_names", "recoverable_argument_errors", "other_format_errors", "process_violation_count")},
            "cost": original.usage_cost(subset, {"states": {}}, ())}
    blocks = []
    for worker, units in all_assignments().items():
        group = {row["condition"]: row for row in rows if row["slot_id"] in {u["slot_id"] for u in units}}
        blocks.append({"block_id": worker, "case_id": units[0]["case_id"], "sampling_seed": units[0]["sampling_seed"],
            "first_member": units[0]["first_member"], "diagnostic_a_owner": units[0]["diagnostic_a_owner"],
            **original.block_contrasts(group)})
    keys = ("split_minus_shared_base", "split_minus_shared_team", "team_minus_base_shared", "team_minus_base_split",
            "information_main_effect", "framing_main_effect", "interaction")
    means = {key: sum(block[key] for block in blocks) / 4 if all(block[key] is not None for block in blocks) else None
             for key in keys}
    return {"by_condition": by_condition, "paired_blocks": blocks, "full_inventory_mean_contrasts": means}


def results(root):
    root = Path(root).resolve()
    plan = read_json(root / "plan.json")
    state = read(root / "supervisor.json") or {"status": "prepared", "states": {}}
    old_root = Path(plan["original_run_root"])
    old_state = read_json(old_root / "supervisor.json")
    corrected = read_json(checked(plan["correction_summary"]))
    retained = original.recorded_rows(old_root, old_state, FIRST_BLOCK, all_assignments()[FIRST_BLOCK])
    for row in retained:
        row["original_feedback_loop"] = reference(old_root / FIRST_BLOCK / "actual/episodes" / row["slot_id"] / "feedback-loop.json")
        corrected_ref = corrected["measurements_by_slot"][row["slot_id"]]
        row["feedback_loop"] = read_json(checked(corrected_ref))
        row["corrected_feedback_loop"] = corrected_ref
        row["execution_phase"] = "retained_original_four"
    new = [dict(row, execution_phase="new_original_remaining_twelve") for worker, units in assignments().items()
           for row in original.recorded_rows(root, state, worker, units)]
    index = {row["slot_id"]: row for row in retained + new}
    rows = [index[u["slot_id"]] for units in all_assignments().values() for u in units]
    combined_state = {**state, "states": {**state["states"], FIRST_BLOCK: old_state["states"][FIRST_BLOCK]}}
    workers = {worker: {"state": combined_state["states"].get(worker, {}), "report":
        read((old_root if worker == FIRST_BLOCK else root) / worker / "actual/report.json")}
        for worker in original.WORKERS}
    return {"version": VERSION, "status": state["status"], "plan": reference(root / "plan.json"),
        "source": plan["source"], "original_execution_source": plan["original_execution_source"],
        "rows": rows, "workers": workers, **summarize_rows(rows),
        "first_block_gate": read_json(checked(corrected["revised_gate"])),
        "original_first_block_gate": read_json(old_root / "first-block-gate.json"),
        "mechanism_pauses": [read_json(path) for path in mechanism_pauses(root)],
        "cost": original.usage_cost(rows, combined_state, original.WORKERS),
        "cost_partitions": {
            "retained_original_four": original.usage_cost(retained, old_state, (FIRST_BLOCK,)),
            "new_original_remaining_twelve": original.usage_cost(new, state, WORKERS),
            "scope": "Original cost counted exactly once. Read-only CPU repair is separate; nested environment/test CPU time is not added to GPU worker occupancy."},
        "environment_preparation": {"slot_receipts": [{"slot_id": row["slot_id"], **row["environment_preparation_cost"]}
            for row in rows if row.get("environment_preparation_cost")],
            "recorded_totals": {key: sum(row.get("environment_preparation_cost", {}).get(key, 0) for row in rows)
                for key in ("actual_public_driver_executions", "sandbox_elapsed_seconds", "prepare_function_wall_seconds",
                            "model_calls", "model_output_tokens", "team_run_tests_charged")}},
        "scheduled": 16, "new_scheduled": 12, "retained": 4, "known": sum(original.known(row) for row in rows),
        "new_known": sum(original.known(row) for row in new), "budget_caps": budget_caps(),
        "new_actor_steps": sum((worker["report"] or {}).get("new_actor_steps", 0) for worker in workers.values()),
        "new_critic_steps": sum((worker["report"] or {}).get("new_critic_steps", 0) for worker in workers.values()),
        "new_backward_calls": 0, "allowed_physical_gpus": list(GPU_ORDER), "supervisor": state,
        "scope": "Same-Gamma original sixteen, retained four plus original remaining twelve, without replay or new seeds. Full-panel contrasts only when all required outcomes known. Limited development comparison, not causal credit or learning benefit."}


def report(root, destination):
    value = results(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    write(destination / "software-organization-v044-resume.json", value)
    lines = ["# v0.44 原十二槽续跑与十六槽合并结果", "",
        f"状态：`{value['status']}`；新增原十二槽已知 `{value['new_known']}/12`，唯一原十六槽已知 `{value['known']}/16`。", "",
        "本轮只修订只读退休归因及宿主续跑入口。原四槽、旧gate=false、原调用与R完整保留；新门读取原144调用重物化证据。模型可见Γ、common3/3、root/seed/顺序、预算和验收不变，无首块重跑或新增样本。", "",
        f"旧执行源码 `{value['original_execution_source']['code_commit']}`；新测量/启动冻结源码 `{value['source']['code_commit']}`。", "",
        "| 条件 | 已知/4 | 成功 | 固定提交 | 均值R |", "|---|---:|---:|---:|---:|"]
    for c, row in value["by_condition"].items():
        lines.append(f"| {c} | {row['known']}/4 | {row['successes']} | {row['submitted_known']} | {row['mean_R']} |")
    lines += ["", "| 块 | SB | ST | PB | PT | 信息效应 | 说明效应 | 交互 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for block in value["paired_blocks"]:
        lines.append("| " + block["block_id"] + " | " + " | ".join(str(block["R"][c]) for c in CONDITIONS)
            + " | " + " | ".join(str(block[k]) for k in ("information_main_effect", "framing_main_effect", "interaction")) + " |")
    lines += ["", f"四块等权平均：`{value['full_inventory_mean_contrasts']}`。None代表必要结果未完整，不补零、不按成功筛选。", "",
        "信息效应=[(PB+PT)−(SB+ST)]/2；说明效应=[(ST+PT)−(SB+PB)]/2；交互=PT−PB−ST+SB。先块内计算，再取原四块等权均值。仅两开发变体、两seed，不作总体稳定性或学习收益推论。", "",
        "| 槽 | 来源 | 状态 | R | 决定/调用 | 实际token | 测试 | 跨成员工作链 |", "|---|---|---|---:|---|---:|---:|---|"]
    for row in value["rows"]:
        u = row.get("usage", {})
        lines.append(f"| {row['slot_id']} | {row['execution_phase']} | {row['status']} | {row['R']} | {u.get('decisions')}/{u.get('attempts')} | {u.get('total_tokens')} | {row.get('team_budget', {}).get('tests', {}).get('used')} | {(row.get('work_use') or {}).get('has_evidenced_cross_member_chain')} |")
    lines += ["", f"执行/测量暂停记录：`{value['mechanism_pauses']}`。正常R0、自退役、预算结束不作为样本继续条件。", "",
        f"原四槽成本：`{value['cost_partitions']['retained_original_four']}`。", "",
        f"新增十二槽成本：`{value['cost_partitions']['new_original_remaining_twelve']}`。", "",
        f"合并唯一十六槽成本：`{value['cost']}`。", "",
        "原四槽未用107154 token不转移。新增最多1536决定/attempt、6000000实际token、384测试；原实际成本加新增上界为7892846 token。CPU只读修订另列，嵌套沙箱时间不叠加GPU占用。", "",
        f"新增actor/critic/反向 `{value['new_actor_steps']}/{value['new_critic_steps']}/{value['new_backward_calls']}`。仅物理GPU3、4、5、7，最多三驻留worker；旧训练/Contribution/确认/缓存生产继续暂停，无自动后继。", "",
        "[续跑协议](software-organization-v044-resume-protocol.md)；[审计原文](../reference/audit-v044-resume.md)；[原四槽详细报告](software-organization-v044-final.md)。", ""]
    (destination / "software-organization-v044-resume.md").write_text("\n".join(lines))
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
                "docs: record original v044 twelve-slot continuation and merged outcomes")
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
