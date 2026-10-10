"""Complete only the original nine slots under an explicit batch-stop revision.

Model-visible work and per-episode handling are unchanged. A fully bound safe
local context termination no longer cancels independent authorized episodes.
All seven prior outcomes and their historical stop records remain immutable.
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
from scripts import software_organization_resume_v044 as prior
from scripts.software_organization_stop_policy_v044 import VERSION as BATCH_STOP_POLICY_VERSION

VERSION = "software-organization-completion-v0.44-r2"
SOURCE = Path(__file__).resolve().parents[1]
GPU_ORDER = original.GPU_ORDER
FIRST_BLOCK = original.FIRST_BLOCK
WORKERS = tuple(w for w in original.WORKERS if w != FIRST_BLOCK)
LIMITS = {**copy.deepcopy(original.LIMITS), "max_new_episodes": 9, "max_parallel_model_instances": 3}
REPORT_PATHS = ["docs/experiments/software-organization-v044-completion.md", "docs/experiments/software-organization-v044-completion.json"]
NEW_SOURCES = (
    "scripts/software_organization_stop_policy_v044.py",
    "scripts/software_organization_completion_admission_v044.py",
    "scripts/software_organization_complete_v044.py",
    "tests/test_organization_stop_policy_v044.py",
    "tests/test_software_organization_completion_admission_v044.py",
    "tests/test_software_organization_complete_v044.py",
)


def checked(ref):
    from scripts.software_organization_admission_v044 import EvidenceReader
    return EvidenceReader().path(ref)


def all_assignments():
    return original.assignments()


def assignments():
    return {w: units[1:] for w, units in all_assignments().items() if w != FIRST_BLOCK}


def budget_caps():
    old = dict(decisions=267, attempts=256, total_tokens=3369138, run_tests=26)
    new = dict(decisions=1152, attempts=1152, total_tokens=4500000, run_tests=288)
    return {"old_actual": old, "new": new, "combined": {k: old[k] + new[k] for k in old},
            "transfer_old_unused": False, "unused_old_tokens": 130862}


def source_files():
    return {name: digest((SOURCE / name).read_bytes()) for name in NEW_SOURCES}


def qualify(destination, admission):
    from scripts.software_organization_completion_admission_v044 import validate_admission
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
    value = {"version": VERSION, "kind": "explicit_batch_stop_scope_revision_controls", "passed":
        admitted["passed"] and all(r["exit_code"] == 0 for r in receipts),
        "admission": reference(admission), "source_files": source_files(), "checks": receipts,
        "new_model_calls": 0, "new_tokenizer_calls": 0, "new_test_or_acceptance_executions": 0,
        "scope": "Host-only batch-stop scope and original nine inventory/launch/merge controls. Same work Gamma and per-member/per-episode treatment. Reuse original qualification, no tokenizer/page-route/acceptance replay."}
    write(destination / "qualification.json", value)
    return value


def validate_qualification(path):
    from scripts.software_organization_completion_admission_v044 import validate_admission
    value = read_json(path)
    if (value.get("version") != VERSION or value.get("kind") != "explicit_batch_stop_scope_revision_controls"
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
        raise FileExistsError("Use a fresh completion root; no old episode or worker replay")
    qualified = validate_qualification(qualification)
    admitted = read_json(checked(qualified["admission"]))
    old_root = Path(admitted["original_run_root"]).resolve()
    resume_root = Path(admitted["resume_run_root"]).resolve()
    if (old_root != data_root / "runs/software-organization-v044"
            or resume_root != data_root / "runs/software-organization-v044-resume"):
        raise ValueError("Data root differs from admitted historical roots")
    validate_new_root(root, (old_root, resume_root))
    old = read_json(checked(admitted["original_refs"]["plan"]))
    previous = read_json(checked(admitted["resume_refs"]["plan"]))
    for historical, ref in ((old_root, admitted["original_refs"]["plan"]),
                             (resume_root, admitted["resume_refs"]["plan"])):
        if Path(ref["path"]).resolve() != historical / "plan.json":
            raise ValueError("Historical plan is not the admitted original")
    source = code_identity()
    if (source["code_dirty"] is not False or admitted.get("passed") is not True
            or source["source_tree_sha256"] != old["source"]["source_tree_sha256"]):
        raise ValueError("Freeze clean host controls with unchanged model-visible source")
    if admitted["remaining_assignments"] != assignments():
        raise ValueError("Only the original nine unopened slots are authorized")
    plan = copy.deepcopy(old)
    for key in ("plan_sha256", "qualification", "prior_audit"):
        plan.pop(key, None)
    plan.update(version=VERSION, created_at=time.time(), source=source, source_root=str(SOURCE),
        data_root=str(data_root), original_run_root=str(old_root), resume_run_root=str(resume_root),
        original_plan=admitted["original_refs"]["plan"], resume_plan=admitted["resume_refs"]["plan"],
        original_execution_source=old["source"], first_continuation_source=previous["source"],
        original_assignments=old["assignments"], assignments=assignments(),
        cases={w: old["cases"][w][1:] for w in WORKERS}, limits=copy.deepcopy(LIMITS),
        qualification=reference(qualification), completion_admission=qualified["admission"],
        prior_audit=reference(SOURCE / "docs/reference/audit-v044-resume-next-completion.md"),
        budget_caps=budget_caps(), correction_summary=admitted["revised_first_block"]["summary"],
        prior_local_context_assessment=admitted["policy_receipt"],
        batch_stop_policy={"version": BATCH_STOP_POLICY_VERSION,
            "safe_known_preexecution_local_context": "record_and_continue_other_authorized_episodes",
            "R_or_submission_dependent": False, "model_visible_gamma_changed": False,
            "member_or_episode_runtime_changed": False,
            "integrity_permission_identity_charge_or_shared_service_fault": "pause_unopened_inventory",
            "insufficient_evidence": "measurement_pending_pause_unopened_inventory",
            "restore_stopped_member": False, "rewrite_unseen_feedback": False},
        prior_artifact_roots=support.dense._artifact_roots([*previous["prior_artifact_roots"], resume_root,
            data_root / "runs/v044-resume-final-analysis", data_root / "runs/v044-completion-controls"]),
        authorization="2026-10-10 user requested implementing the new v044 continuation audit and subsequent experiments. Explicitly revise only batch-stop scope: a fully bound safe, preexecution local context rejection with closed evaluable result does not cancel other independent original episodes, equally for R0/R1 and before/after submission. Preserve all seven old outcomes and historical stops; collect only original remaining nine. No new work Gamma, seed, replay, learning or later 24-slot study.",
        stage_rule="No new first block or universal all-feedback-fit requirement. Preserve context interruption and original member/episode runtime. Assess source/identity/permission/charge/record integrity after each episode; safe local resource termination does not write a global pause. Unresolved evidence or real integrity/shared-service fault pauses unopened work.",
        scheduling="Three original blocks, each with only its three original remaining slots in original order. At most three resident workers on physical GPUs3,4,5,7; sequential calls within episodes. In-flight episodes close before an applicable global pause; no replay or retry.",
        seeds="Original 202610100441/202610100442 and org44 identities unchanged. Each block restores the original complete common once and keeps parameters frozen; each episode uses the original environment reset and seed. No previous patch/history or audit injected.",
        analysis="Original sixteen under unchanged model-visible working conditions and an explicitly revised batch-stop policy. Retain all results including local context endings; separate context/feedback/submission/work/cost. Four-block contrasts only when all required R known; no context-free subset replacement or automatic successor.")
    if plan["original_assignments"] != all_assignments():
        raise ValueError("Original inventory changed")
    plan["plan_sha256"] = digest(json_bytes(plan))
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    return plan


def validate_new_root(root, historical_roots):
    root = Path(root).resolve()
    if any(root == Path(old).resolve() or Path(old).resolve() in root.parents for old in historical_roots):
        raise ValueError("Both historical run roots are immutable")
    return root


def frozen(root):
    plan = read_json(Path(root) / "plan.json")
    if (plan.get("version") != VERSION
            or plan.get("plan_sha256") != digest(json_bytes({k: v for k, v in plan.items() if k != "plan_sha256"}))
            or plan.get("source") != code_identity() or plan.get("assignments") != assignments()
            or plan.get("original_assignments") != all_assignments()
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != list(GPU_ORDER)
            or plan.get("budget_caps") != budget_caps() or plan.get("automatic_successors") != []
            or plan.get("training_eligible") is not False
            or plan.get("batch_stop_policy", {}).get("version") != BATCH_STOP_POLICY_VERSION):
        raise ValueError("Frozen completion source, inventory or contract changed")
    qualified = validate_qualification(checked(plan["qualification"]))
    if plan["completion_admission"] != qualified["admission"]:
        raise ValueError("Completion admission mismatch")
    admitted = read_json(checked(plan["completion_admission"]))
    if (plan["original_run_root"] != admitted["original_run_root"]
            or plan["resume_run_root"] != admitted["resume_run_root"]
            or plan["original_plan"] != admitted["original_refs"]["plan"]
            or plan["resume_plan"] != admitted["resume_refs"]["plan"]
            or plan["correction_summary"] != admitted["revised_first_block"]["summary"]
            or plan["prior_local_context_assessment"] != admitted["policy_receipt"]
            or plan["assignments"] != admitted["remaining_assignments"]):
        raise ValueError("Completion proof chain differs from admitted original evidence")
    validate_new_root(root, (plan["original_run_root"], plan["resume_run_root"]))
    for key in ("original_plan", "resume_plan", "common", "parent_plan", "parent_report", "prior_audit", "correction_summary", "prior_local_context_assessment"):
        checked(plan[key])
    old = read_json(checked(plan["original_plan"]))
    for key in ("model_references", "common", "feedback_protocol", "business_bindings", "source_partition", "runtime_dependency_path"):
        if plan.get(key) != old.get(key):
            raise ValueError("Original model-visible dependency changed: " + key)
    if plan["cases"] != {w: old["cases"][w][1:] for w in WORKERS}:
        raise ValueError("Remaining original cases changed")
    return plan


def require_worker_release(root, worker, plan):
    if worker not in WORKERS or worker == FIRST_BLOCK:
        raise ValueError("Only the original unopened nine may launch")
    validate_qualification(checked(plan["qualification"]))
    if mechanism_pauses(root):
        raise ValueError("Unopened work is paused by execution or measurement evidence")


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
            from scripts.software_organization_stop_policy_v044 import assess_episode
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
                        argv = [sys.executable, "-m", "scripts.software_organization_complete_v044", "worker",
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
    return prior.summarize_rows(rows)


def results(root):
    root = Path(root).resolve()
    plan = read_json(root / "plan.json")
    state = read(root / "supervisor.json") or {"status": "prepared", "states": {}}
    old_root, resume_root = Path(plan["original_run_root"]), Path(plan["resume_run_root"])
    old_state, resume_state = read_json(old_root / "supervisor.json"), read_json(resume_root / "supervisor.json")
    corrected = read_json(checked(plan["correction_summary"]))
    retained = original.recorded_rows(old_root, old_state, FIRST_BLOCK, all_assignments()[FIRST_BLOCK])
    for row in retained:
        row["original_feedback_loop"] = reference(old_root / FIRST_BLOCK / "actual/episodes" / row["slot_id"] / "feedback-loop.json")
        corrected_ref = corrected["measurements_by_slot"][row["slot_id"]]
        row["feedback_loop"] = read_json(checked(corrected_ref))
        row["corrected_feedback_loop"] = corrected_ref
        row["execution_phase"] = "retained_original_four"
    previous = [dict(row, execution_phase="retained_first_continuation_three") for worker in WORKERS
                for row in original.recorded_rows(resume_root, resume_state, worker, all_assignments()[worker][:1])]
    new = [dict(row, execution_phase="new_original_remaining_nine") for worker, units in assignments().items()
           for row in original.recorded_rows(root, state, worker, units)]
    # Validate identities before any lookup, so malformed saved IDs cannot redirect receipts.
    unordered = retained + previous + new
    summary = summarize_rows(unordered)
    for row in new:
        folder = root / next(w for w, units in assignments().items() if row["slot_id"] in {u["slot_id"] for u in units}) / "actual/episodes" / row["slot_id"]
        row["batch_stop_assessment"] = read(folder / "batch-stop-assessment.json")
    index = {row["slot_id"]: row for row in unordered}
    rows = [index[u["slot_id"]] for units in all_assignments().values() for u in units]
    phases = (("original_four", old_root, old_state, (FIRST_BLOCK,)),
              ("first_continuation", resume_root, resume_state, WORKERS),
              ("completion", root, state, WORKERS))
    workers = {phase + "/" + worker: {"phase": phase, "worker": worker,
        "state": phase_state["states"].get(worker, {}), "report": read(phase_root / worker / "actual/report.json")}
        for phase, phase_root, phase_state, names in phases for worker in names}
    partitions = {"retained_original_four": original.usage_cost(retained, old_state, (FIRST_BLOCK,)),
        "retained_first_continuation_three": original.usage_cost(previous, resume_state, WORKERS),
        "new_original_remaining_nine": original.usage_cost(new, state, WORKERS)}
    total_cost = original.usage_cost(rows, {"states": {}}, ())
    for key in ("closed_worker_gpu_seconds", "running_worker_gpu_seconds"):
        total_cost[key] = sum(part[key] for part in partitions.values())
    return {"version": VERSION, "status": state["status"], "plan": reference(root / "plan.json"),
        "source": plan["source"], "original_execution_source": plan["original_execution_source"],
        "first_continuation_source": plan["first_continuation_source"],
        "batch_stop_policy": plan["batch_stop_policy"], "rows": rows, "workers": workers, **summary,
        "first_block_gate": read_json(checked(corrected["revised_gate"])),
        "original_first_block_gate": read_json(old_root / "first-block-gate.json"),
        "prior_local_context_assessment": plan["prior_local_context_assessment"],
        "historical_first_continuation_stops": [reference(p) for p in sorted((resume_root / "mechanism-stops").glob("*.json"))],
        "mechanism_pauses": [read_json(path) for path in mechanism_pauses(root)],
        "cost": total_cost, "cost_partitions": partitions,
        "cost_scope": "Three execution phases counted exactly once. Reused worker names are phase-qualified. CPU control costs are separate; nested environment/test/acceptance time is not added to GPU worker occupancy.",
        "environment_preparation": {"slot_receipts": [{"slot_id": row["slot_id"], **row["environment_preparation_cost"]}
            for row in rows if row.get("environment_preparation_cost")],
            "recorded_totals": {key: sum(row.get("environment_preparation_cost", {}).get(key, 0) for row in rows)
                for key in ("actual_public_driver_executions", "sandbox_elapsed_seconds", "prepare_function_wall_seconds",
                            "model_calls", "model_output_tokens", "team_run_tests_charged")}},
        "scheduled": 16, "new_scheduled": 9, "retained": 7, "known": sum(original.known(row) for row in rows),
        "new_known": sum(original.known(row) for row in new), "budget_caps": budget_caps(),
        "new_actor_steps": sum((worker["report"] or {}).get("new_actor_steps", 0) for worker in workers.values()),
        "new_critic_steps": sum((worker["report"] or {}).get("new_critic_steps", 0) for worker in workers.values()),
        "new_backward_calls": 0, "allowed_physical_gpus": list(GPU_ORDER), "supervisor": state,
        "scope": "Same model-visible work conditions, explicitly revised batch-stop policy. Original sixteen only, seven retained and nine completed without replay/new seeds. Context endings remain in the full inventory; no context-free selection, causal contribution or parameter-learning claim."}


def report(root, destination):
    value = results(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    write(destination / "software-organization-v044-completion.json", value)
    lines = ["# v0.44 批次停止政策修订后的原九槽收口", "",
        f"状态 `{value['status']}`；新九槽已知 `{value['new_known']}/9`，唯一原十六槽已知 `{value['known']}/16`。", "",
        "本轮明确修订批次停止作用域。模型可见工作条件与单成员/episode处理不变；充分绑定的安全局部context终止保留为工作结果，不再自动取消其它独立episode。真实权限、身份、输入、计费、原始记录或共同服务故障仍暂停，证据不足保持测量未决。对R0/R1及提交前后相同，不补生成、不复活成员、不改未呈现反馈。", "",
        "原4及前次接续3全部保留，旧false、修订true和真实ST context停止事实不改。只运行原剩余9槽，无新seed、新首块、新16槽或后继24条研究。原9B完整common3/3、16K/2048及每槽128决定/attempt、500000实际token、32测试不变；旧130862 token不转移。", "",
        f"本次实际宿主源 `{value['source']['code_commit']}`；原两阶段源 `{value['original_execution_source']['code_commit']}` / `{value['first_continuation_source']['code_commit']}`。", "",
        "| 条件 | 已知/4 | 成功 | 固定提交 | 均值R |", "|---|---:|---:|---:|---:|"]
    for c, row in value["by_condition"].items():
        lines.append(f"| {c} | {row['known']}/4 | {row['successes']} | {row['submitted_known']} | {row['mean_R']} |")
    lines += ["", "| 块 | SB | ST | PB | PT | 信息效应 | 说明效应 | 交互 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for block in value["paired_blocks"]:
        lines.append("| " + block["block_id"] + " | " + " | ".join(str(block["R"][c]) for c in CONDITIONS)
            + " | " + " | ".join(str(block[k]) for k in ("information_main_effect", "framing_main_effect", "interaction")) + " |")
    lines += ["", f"原四块等权平均：`{value['full_inventory_mean_contrasts']}`。None代表必要结果未完整，不补零。", "",
        "信息效应=[PB+PT−SB−ST]/2；说明效应=[ST+PT−SB−PB]/2；交互=PT−PB−ST+SB。固定16K与预算下，此为信息布局、取得成本、历史容量及模型行为共同作用的有限开发比较，不是去除容量影响后的纯协作效应或总体稳定收益。", "",
        "| slot | 阶段 | 状态 | R | 提交 | 决定/调用 | 实际token | context反馈未见数 | 新批次决定 | 跨成员链 |", "|---|---|---|---:|---|---|---:|---:|---|---|"]
    for row in value["rows"]:
        u = row.get("usage", {})
        facts = (row.get("feedback_loop") or {}).get("mechanism_gate_inputs", {})
        context = len(facts["context_blocked_feedback_ids"]) if "context_blocked_feedback_ids" in facts else None
        lines.append(f"| {row['slot_id']} | {row['execution_phase']} | {row['status']} | {row['R']} | {row.get('submitted')} | {u.get('decisions')}/{u.get('attempts')} | {u.get('total_tokens')} | {context} | {(row.get('batch_stop_assessment') or {}).get('decision')} | {(row.get('work_use') or {}).get('has_evidenced_cross_member_chain')} |")
    lines += ["", f"新全局暂停：`{value['mechanism_pauses']}`。旧停止记录原样留在历史运行目录，不伪装所有旧门曾通过。", ""]
    for phase, cost in value["cost_partitions"].items():
        lines += [f"{phase}成本：`{cost}`。", ""]
    lines += [f"逻辑原16全部实际成本：`{value['cost']}`。", "",
        "新九槽上限1152决定/attempt、4500000实际token、288测试；原七实际加新增上界1419决定、1408attempt、7869138token、314测试。三阶段成本各计一次，同名worker按阶段分列。CPU修订与嵌套测试/验收成本另列。", "",
        f"新增actor/critic/反向 `{value['new_actor_steps']}/{value['new_critic_steps']}/{value['new_backward_calls']}`。仅GPU3、4、5、7，最多三驻留；旧训练/Contribution/正式更新/确认/缓存生产继续暂停，无自动后继。", "",
        "[冻结收口协议](software-organization-v044-completion-protocol.md)；[新审计](../reference/audit-v044-resume-next-completion.md)；[前次接续报告](software-organization-v044-resume-final.md)。", ""]
    (destination / "software-organization-v044-completion.md").write_text("\n".join(lines))
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
                "docs: record original v044 nine-slot completion under revised batch stop policy")
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
