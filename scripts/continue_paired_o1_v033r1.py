"""Resume only the twelve unstarted v033 slots after offline record repair."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
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
from proworksim.storage import digest, json_bytes, read_json
from scripts import continue_model_selection_v031 as continuation
from scripts import software_model_selection_v030 as original
from scripts import software_model_selection_v031 as dense
from scripts import software_paired_o1_v033 as prior
from scripts.gpu_occupancy_accounting import GpuInterval, interval_accounting
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, resources, write
from scripts.software_development_v028 import available_cards, task

VERSION = "paired-o1-recovery-v0.33r1"
SOURCE = Path(__file__).resolve().parents[1]
CANDIDATES = prior.CANDIDATES
GPU_ORDER = prior.GPU_ORDER
LIMITS = copy.deepcopy(prior.LIMITS)
TERMINAL = prior.TERMINAL
NEXT_STAGE_RULE = copy.deepcopy(prior.NEXT_STAGE_RULE)
REPORT_PATHS = ["docs/experiments/software-paired-o1-v033-recovery.md",
                "docs/experiments/software-paired-o1-v033-recovery.json"]
GUARD_KEYS = ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged",
              "actor_identity_unchanged")
SCORES = ("R", "content_correct", "required_process_satisfied", "submitted", "complete_delivery")
checked = prior.checked
inventory = prior.inventory


def known(row):
    return (row.get("status") == "closed" and row.get("record_validity") is True
            and type(row.get("R")) is int and row["R"] in (0, 1))


def observe_rows(actual, expected):
    rows = read(Path(actual) / "diagnostics/progress.json") or []
    if len(rows) > len(expected) or any(
        any(row.get(key) != value for key, value in slot.items())
        for row, slot in zip(rows, expected)
    ):
        raise ValueError("Recovery progress must be an exact prefix of original slots 2..7")
    return rows


def unstarted_slot_proof(actual, slots):
    """Prepared worlds are allowed; any episode, transport or SDK event forbids replay."""
    result = []
    for index, slot in enumerate(slots, start=2):
        folder = Path(actual) / "diagnostics" / f"slot-{index}"
        for name in ("episode", "raw-transport", "runtime-opportunities.jsonl", "runtime-state.json",
                     "team-budget.json", "assessment.json", "entry.json", "public-capture",
                     "experience.jsonl", "evaluation-guard.json", "interruption.json"):
            if (folder / name).exists():
                raise ValueError("A supposedly unstarted slot has execution evidence: " + str(folder / name))
        files = []
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(folder).as_posix()
            is_base = relative.startswith("sdk-conversations/") and path.name == "base_state.json"
            if not (relative in {"preparation.json", "model-scenario.json"}
                    or relative.startswith("world/") or is_base):
                raise ValueError("A supposedly unstarted slot has execution evidence: " + str(path))
            if is_base:
                value = read_json(path)
                if (value.get("execution_status") != "idle" or value.get("agent_state") != {}
                        or value.get("stats", {}).get("usage_to_metrics") != {}):
                    raise ValueError("Unstarted SDK state contains execution/model usage")
            files.append({"relative_path": relative, "sha256": digest(path.read_bytes())})
        if not files or not (folder / "preparation.json").is_file():
            raise ValueError("Expected the original prebuilt but unstarted slot")
        result.append({"slot_index": index, "slot_id": slot["slot_id"], "directory": str(folder.resolve()),
                       "file_count": len(files), "file_manifest_sha256": digest(json_bytes(files)),
                       "episode_started": False, "model_generation_evidence_present": False})
    return result


def record_recovery_path(value):
    path = Path(value).resolve()
    return path / "summary.json" if path.is_dir() else path


def validate_recovered_rows(recovery, old_plan, original_run):
    if (recovery.get("status") != "recovered" or recovery.get("passed") is not True
            or recovery.get("model_calls") != 0 or recovery.get("optimizer_steps") != 0
            or recovery.get("acceptance_executions") != 0 or recovery.get("new_episodes") != 0
            or recovery.get("old_artifacts_unchanged") is not True
            or Path(recovery["source_root"]).resolve() != Path(original_run).resolve()
            or set(recovery.get("candidates", {})) != set(CANDIDATES)):
        raise ValueError("Require a passing zero-generation offline recovery of this exact prior run")
    for candidate in CANDIDATES:
        expected = old_plan["inventories"][candidate][:2]
        item = recovery["candidates"][candidate]
        if (item.get("status") != "recovered"
                or item.get("completed_slot_ids") != [row["slot_id"] for row in expected]
                or len(item.get("rows", [])) != 2):
            raise ValueError("Only the two already executed original prefix slots can be reused")
        for index, (row, slot) in enumerate(zip(item["rows"], expected)):
            if any(row.get(key) != value for key, value in slot.items()) or not known(row):
                raise ValueError("Recovered prefix must retain exact original inventory and known records")
            original_slot = Path(original_run) / candidate / "actual/diagnostics" / f"slot-{index}"
            if (row["assessment"] != reference(original_slot / "assessment.json")
                    or row["evaluation_guard"] != reference(original_slot / "evaluation-guard.json")):
                raise ValueError("Recovered assessments and guards must reference original immutable files")
            assessment = read_json(checked(row["assessment"]))
            if any(row.get(key) != assessment.get(key) for key in SCORES):
                raise ValueError("Offline recovery must preserve the original assessment, without regrading")
            guard = read_json(checked(row["evaluation_guard"]))
            if any(guard.get(key) is not True for key in GUARD_KEYS):
                raise ValueError("Reused episode did not preserve the original frozen learner")
            entry = read_json(checked(row["entry"]))
            reward = entry.get("reward", {})
            if (entry.get("slot_id") != slot["slot_id"] or reward.get("eligible") is not True
                    or reward.get("reward") != row["R"]
                    or reward.get("source_assessment_sha256") != row["assessment"]["sha256"]):
                raise ValueError("Recovered entry must remain bound to its original slot and assessment")
    return recovery


def original_binding(original_run, recovery):
    root = Path(original_run).resolve()
    old_plan = read_json(root / "plan.json")
    prior.validate_plan(old_plan, check_files=False)
    supervisor = read_json(root / "supervisor.json")
    if (supervisor.get("status") != "ended_with_execution_stop"
            or supervisor.get("source") != old_plan["source"]
            or any(supervisor["states"][c].get("status") != "stopped" for c in CANDIDATES)):
        raise ValueError("Bind the terminal original execution-stop; never relabel its controller state")
    validate_recovered_rows(recovery, old_plan, root)
    candidates = {}
    for candidate in CANDIDATES:
        actual = root / candidate / "actual"
        state = read_json(root / candidate / "state.json")
        worker = read_json(actual / "report.json")
        rows = observe_rows(actual, old_plan["inventories"][candidate])
        parent = old_plan["parents"][candidate]
        guard = read_json(actual / "diagnostics/evaluation-guard.json")
        restore = read_json(actual / "diagnostics/common-restore.json")
        if (state != supervisor["states"][candidate] or len(rows) != 2
                or worker.get("status") != "execution_error" or worker.get("rows") != rows
                or worker.get("source_before") != old_plan["source"]
                or worker.get("source_after") != old_plan["source"]
                or worker.get("execution_binding_passed") is not True
                or any(worker.get(key) != 0 for key in (
                    "fresh_technical_quiz_calls", "diagnostic_optimizer_steps", "screening_optimizer_steps"))
                or any(worker.get(key) != parent["common_steps"] for key in (
                    "initial_actor_steps", "initial_critic_steps", "actor_steps", "critic_steps"))
                or worker.get("final_actor_identity") != parent["common_actor_identity"]
                or any(guard.get(key) is not True for key in GUARD_KEYS)
                or restore.get("common_restored_exactly") is not True
                or restore.get("optimizer_updates") != 0
                or restore.get("actor_identity") != parent["common_actor_identity"]
                or restore.get("checkpoint") != parent["references"]["common"]["path"]):
            raise ValueError("Original interrupted work must prove unchanged common and exactly two executed slots")
        candidates[candidate] = {
            "state": reference(root / candidate / "state.json"),
            "worker": reference(actual / "report.json"),
            "progress": reference(actual / "diagnostics/progress.json"),
            "evaluation_guard": reference(actual / "diagnostics/evaluation-guard.json"),
            "common_restore": reference(actual / "diagnostics/common-restore.json"),
            "completed_slot_ids": [row["slot_id"] for row in rows],
            "unstarted_slots": unstarted_slot_proof(actual, old_plan["inventories"][candidate][2:]),
        }
    return {
        "run_root": str(root), "source": old_plan["source"], "source_root": old_plan["source_root"],
        "plan": reference(root / "plan.json"), "supervisor": reference(root / "supervisor.json"),
        "worker_gpu_seconds": supervisor["worker_gpu_seconds"], "candidates": candidates,
        "original_execution_stop_preserved": True,
    }


def make_plan(data_root, cpu_qualification, prior_run_root, record_recovery):
    root = Path(data_root).resolve()
    original_run = Path(prior_run_root).resolve()
    recovery_path = record_recovery_path(record_recovery)
    recovery = read_json(recovery_path)
    old = read_json(original_run / "plan.json")
    if old["data_root"] != str(root):
        raise ValueError("The recovery data root must remain the original data root")
    binding = original_binding(original_run, recovery)
    return {
        "version": VERSION, "created_at": time.time(), "source": code_identity(), "source_root": str(SOURCE),
        "data_root": str(root), "qualification": reference(cpu_qualification),
        "original": binding, "record_recovery": reference(recovery_path), "parents": copy.deepcopy(old["parents"]),
        "candidates": list(CANDIDATES), "inventories": copy.deepcopy(old["inventories"]),
        "remaining_inventories": {c: copy.deepcopy(old["inventories"][c][2:]) for c in CANDIDATES},
        "completed_slot_ids": {c: [row["slot_id"] for row in old["inventories"][c][:2]] for c in CANDIDATES},
        "limits": copy.deepcopy(LIMITS), "gpu_preference": list(GPU_ORDER),
        "runtime_dependency_path": old["runtime_dependency_path"],
        "prior_artifact_roots": dense._artifact_roots([*old["prior_artifact_roots"], original_run, recovery_path.parent]),
        "protocol": reference(SOURCE / "docs/experiments/software-paired-o1-v033-recovery-protocol.md"),
        "frozen_development_episodes": 16, "reused_completed_episodes": 4, "new_sampling_episodes": 12,
        "optimizer_updates_allowed": False, "fresh_technical_quiz_calls": 0, "repeat_near_16k_stress": False,
        "automatic_retries": False, "automatic_successors": [], "automatic_model_replacement": False,
        "total_gpu_seconds": None, "worker_gpu_seconds": None, "queue_deadline_at": None, "wall_deadline_at": None,
        "next_stage_rule": copy.deepcopy(NEXT_STAGE_RULE), "old_selected_candidate": None,
        "old_results_reclassified": False, "historical_v030_v032_results_reclassified": False,
        "v033_record_validity_reinterpreted": True, "business_assessments_regraded": False,
        "swe_rerun": False, "new_model_downloads": False,
        "original_execution_stop_preserved": True, "resample_completed_slots": False,
        "authorization": "User requested repair and continuation of the interrupted finite experiment",
        "scope": "The same original 16 logical slots: four already executed records recovered offline, twelve unstarted slots sampled once. Same common/profile/seeds/contracts/team budgets; no updates or new technical quiz.",
    }


def validate_plan(plan, *, check_files=True):
    expected = {c: inventory() for c in CANDIDATES}
    if (plan.get("version") != VERSION or plan.get("candidates") != list(CANDIDATES)
            or plan.get("inventories") != expected
            or plan.get("remaining_inventories") != {c: rows[2:] for c, rows in expected.items()}
            or plan.get("completed_slot_ids") != {c: [row["slot_id"] for row in rows[:2]] for c, rows in expected.items()}
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != GPU_ORDER
            or plan.get("frozen_development_episodes") != 16 or plan.get("reused_completed_episodes") != 4
            or plan.get("new_sampling_episodes") != 12 or plan.get("optimizer_updates_allowed") is not False
            or plan.get("fresh_technical_quiz_calls") != 0 or plan.get("repeat_near_16k_stress") is not False
            or plan.get("automatic_retries") is not False or plan.get("automatic_successors") != []
            or plan.get("automatic_model_replacement") is not False or plan.get("swe_rerun") is not False
            or plan.get("new_model_downloads") is not False or plan.get("old_results_reclassified") is not False
            or plan.get("historical_v030_v032_results_reclassified") is not False
            or plan.get("v033_record_validity_reinterpreted") is not True
            or plan.get("business_assessments_regraded") is not False
            or plan.get("original_execution_stop_preserved") is not True or plan.get("resample_completed_slots") is not False
            or plan.get("next_stage_rule") != NEXT_STAGE_RULE or plan.get("old_selected_candidate") is not None
            or any(plan.get(key) is not None for key in ("total_gpu_seconds", "worker_gpu_seconds", "queue_deadline_at", "wall_deadline_at"))):
        raise ValueError("Recovery must reuse exactly four original slots and sample only the twelve unstarted slots")
    if check_files:
        if (plan["source"] != code_identity() or plan["source"].get("code_dirty") is not False
                or plan["source_root"] != str(SOURCE)):
            raise ValueError("Use the exact clean CPU-qualified recovery checkout")
        cpu = read_json(checked(plan["qualification"]))
        if (cpu.get("passed") is not True or cpu.get("source") != plan["source"]
                or cpu.get("model_calls") != 0 or cpu.get("gpu_used") is not False):
            raise ValueError("Require same-source zero-model zero-GPU recovery controls")
        recovery = read_json(checked(plan["record_recovery"]))
        if original_binding(plan["original"]["run_root"], recovery) != plan["original"]:
            raise ValueError("The original stopped run, prepared slots or offline recovery changed")
        old = read_json(checked(plan["original"]["plan"]))
        for candidate in CANDIDATES:
            if (plan["parents"][candidate] != old["parents"][candidate]
                    or prior.inherited_candidate(plan["data_root"], candidate) != plan["parents"][candidate]):
                raise ValueError("Original candidate-specific common and numerical evidence changed")
        checked(plan["protocol"])
    return plan


def run_worker(plan_path, candidate, output):
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.online_training import tensor_tree_digest
    from proworksim.software_learning_v029 import migrate_software_owner
    from proworksim.software_runtime_v033 import collect, window_spec

    plan = validate_plan(read_json(plan_path))
    if candidate not in CANDIDATES or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPU_ORDER)):
        raise ValueError("One declared candidate per assigned physical GPU")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"version": VERSION, "candidate_id": candidate, "status": "loading", "started_at": time.time(),
        "source_before": code_identity(), "rows": [], "plan": reference(plan_path),
        "fresh_technical_quiz_calls": 0, "diagnostic_optimizer_steps": 0, "screening_optimizer_steps": 0,
        "old_results_reclassified": False, "historical_v030_v032_results_reclassified": False,
        "v033_record_validity_reinterpreted": True, "business_assessments_regraded": False,
        "learning_evidence_inherited": True,
        "completed_slot_ids_skipped": plan["completed_slot_ids"][candidate], "new_sampling_episodes": 6}
    owner = None
    write(output / "report.json", report)
    try:
        task(output, "load-original-common-" + candidate, "loading")
        sample = resources()
        write(output / "preload-resources.json", sample)
        if int(os.environ["CUDA_VISIBLE_DEVICES"]) not in [card["index"] for card in available_cards(plan, sample)]:
            raise RuntimeError("Assigned empty A100 capacity changed before loading")
        parent = plan["parents"][candidate]
        refs = parent["references"]
        saved_owner = read_json(checked(refs["owner"]))
        old_plan = read_json(checked(refs["plan"]))
        if candidate == CANDIDATES[0]:
            loading = read_json(checked(old_plan["prior_model_plan"]))
            owner = DeterministicCandidateActor.from_candidate(loading["model"], manifest=checked(loading["manifest"]),
                profile=loading["runtime_profile"], recipe=saved_owner["recipe"], output=output / "resident")
        else:
            profile = old_plan["candidate_profiles"][candidate]
            owner = dense.load_owner(saved_owner["base_identity"]["path"], manifest=checked(refs["base_manifest"]),
                profile=profile, recipe=saved_owner["recipe"], output=output / "resident")
        write(output / "software-critic-migration.json", migrate_software_owner(owner, expected_steps=None))
        if owner.inference_profile != saved_owner["inference_profile"] or owner.base_identity != saved_owner["base_identity"]:
            raise ValueError("Actual native runtime/base identity differs from inherited numerical evidence")
        task(output, "restore-full-original-common", "boundary")
        common_dir = checked(refs["common"]).parent
        common = read_json(common_dir / "checkpoint.json")
        if owner.restore_checkpoint(common_dir) != common:
            raise ValueError("Restore must return the exact original common checkpoint")
        def verify_common():
            if (tensor_tree_digest(owner._state_bundle(), owner.torch) != common["state_tensor_digest"]
                    or owner.freeze_identity() != common["actor_identity"]
                    or (owner.actor_steps, owner.critic_steps) != (parent["common_steps"], parent["common_steps"])):
                raise ValueError("Actor/critic/optimizers/RNG identity is not the original common")
        verify_common()
        report.update(status="collecting", common_actor_identity=owner.freeze_identity(),
                      initial_actor_steps=owner.actor_steps, initial_critic_steps=owner.critic_steps,
                      inherited_learning_evidence=parent, execution_binding_passed=True)
        write(output / "inherited-common.json", {"restored_exactly": True, "common": refs["common"],
              "state_tensor_digest": common["state_tensor_digest"], "actor_identity": owner.freeze_identity(),
              "no_new_learning_or_capacity_probe": True})
        write(output / "report.json", report)
        def on_slot(event, row, folder):
            if event == "closed":
                report["rows"] = observe_rows(output, plan["remaining_inventories"][candidate])
                write(output / "report.json", report)
        entries = collect(owner, window_spec("v033r1-" + candidate), output / "diagnostics", output,
                          common_dir=common_dir, on_slot=on_slot,
                          completed_slot_ids=tuple(plan["completed_slot_ids"][candidate]))
        verify_common()
        report["rows"] = observe_rows(output, plan["remaining_inventories"][candidate])
        if len(entries) != 6 or len(report["rows"]) != 6:
            raise ValueError("Recovery must collect exactly the six previously unstarted slots")
        report.update(status="complete", common_restored_exactly=True)
    except BaseException as error:
        report.update(status="execution_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report["rows"] = observe_rows(output, plan["remaining_inventories"][candidate])
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps,
                          final_actor_identity=owner._make_identity())
        report.update(ended_at=time.time(), source_after=code_identity())
        write(output / "report.json", report)
    return report



def supervise(plan_path, run_root):
    plan = validate_plan(read_json(plan_path))
    root = Path(run_root).resolve()
    if any(root == Path(old) or root.is_relative_to(Path(old)) or Path(old).is_relative_to(root) for old in plan["prior_artifact_roots"]):
        raise ValueError("Use a new run outside every previous immutable artifact root")
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    states = {c: {"candidate_id": c, "status": "not_started", "attempted": False} for c in CANDIDATES}
    summary = {"version": VERSION, "status": "waiting", "started_at": time.time(), "observer_pid": os.getpid(),
               "source": plan["source"], "states": states}
    active, logs, guards, stable = {}, {}, {}, {}
    def publish():
        summary.update(observed_at=time.time(), worker_gpu_seconds=sum(x.get("elapsed_gpu_seconds", 0) for x in states.values()),
                       running_gpu_seconds=sum(time.time() - states[c]["started_at"] for c in active))
        write(root / "supervisor.json", summary)
        for c, state in states.items():
            write(root / c / "state.json", state)
    def finish(candidate, reason):
        process = active.pop(candidate)
        state = states[candidate]
        if process.poll() is None:
            continuation._stop_worker(process, state)
        process.wait(timeout=15)
        worker = read(root / candidate / "actual/report.json") or {}
        okay = (process.returncode == 0 and reason is None and worker.get("status") == "complete"
                and worker.get("source_before") == plan["source"] and worker.get("source_after") == plan["source"])
        ended = time.time()
        state.update(status="complete" if okay else "stopped", ended_at=ended, exit_code=process.returncode,
                     stop_reason=reason if reason is not None or okay else "worker_not_complete_same_source",
                     elapsed_gpu_seconds=max(0, ended - state["started_at"]))
        logs.pop(candidate).close()
        publish()
    with lock(root):
        try:
            while not all(s["status"] in TERMINAL for s in states.values()):
                for c, process in list(active.items()):
                    if process.poll() is not None:
                        finish(c, None if process.returncode == 0 else "worker_exit_error")
                size = sum(artifact_bytes(Path(path)) for path in dense._artifact_roots([*plan["prior_artifact_roots"], root]))
                free = shutil.disk_usage(root).free
                if size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                    for c in list(active):
                        finish(c, "trajectory_storage_reserve")
                    for c, state in states.items():
                        if state["status"] == "not_started":
                            state.update(status="stopped", stop_reason="trajectory_storage_reserve", ended_at=time.time(), elapsed_gpu_seconds=0)
                    break
                waiting = [c for c in CANDIDATES if states[c]["status"] == "not_started"]
                if waiting:
                    sample = resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    cards = available_cards(plan, sample, [states[c]["gpu"] for c in active])
                    now = time.time()
                    stable = {card["index"]: stable.get(card["index"], now) for card in cards}
                    for card in cards:
                        if not waiting or len(active) >= 2:
                            break
                        if now - stable[card["index"]] < LIMITS["gpu_capacity_stability_seconds"]:
                            continue
                        validate_plan(plan)
                        c = waiting.pop(0)
                        folder = root / c
                        folder.mkdir(exist_ok=True)
                        argv = [sys.executable, "-m", "scripts.continue_paired_o1_v033r1", "worker", "--plan", str(root / "plan.json"),
                                "--candidate", c, "--output", str(folder / "actual")]
                        logs[c] = (folder / "worker.log").open("x")
                        started = time.time()
                        process = subprocess.Popen(argv, cwd=SOURCE, env=original.worker_env(plan, root, c, card["index"]),
                            stdin=subprocess.DEVNULL, stdout=logs[c], stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        states[c].update(status="running", attempted=True, started_at=started, gpu=card["index"], gpu_uuid=card["uuid"],
                                         pid=process.pid, process_identity=identity, command=argv)
                        active[c] = process
                        guards[c] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        publish()
                else:
                    stable = {}
                if active:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = {c: pool.submit(target_resources, states[c]["gpu"], worker_pid=p.pid) for c, p in active.items()}
                        samples = {c: f.result() for c, f in futures.items()}
                    for c, process in list(active.items()):
                        if process.poll() is not None:
                            finish(c, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = states[c]
                        observation = guards[c].observe(samples[c], time.time(), process.pid, state["gpu"], own_memory_limit_mib=LIMITS["own_gpu_memory_mib"])
                        current = read(root / c / "actual/task.json") or {"kind": "loading", "started_at": state["started_at"]}
                        own_rss, reason = rss(process.pid), observation.get("stop_reason")
                        cap = LIMITS["task_seconds"].get(current.get("kind"))
                        if current.get("kind") not in LIMITS["task_seconds"]:
                            reason = reason or "unknown_task_kind"
                        elif cap is not None and time.time() - current["started_at"] >= cap:
                            reason = reason or "single_task_budget"
                        elif own_rss > LIMITS["host_rss_per_worker_bytes"]:
                            reason = reason or "host_memory_budget"
                        with (root / c / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": samples[c], "guard": observation, "task": current,
                                                     "rss_bytes": own_rss, "artifact_bytes": size, "volume_free_bytes": free}) + "\n")
                        if reason:
                            finish(c, reason)
                summary["status"] = "running" if active else "waiting"
                publish()
                if not all(s["status"] in TERMINAL for s in states.values()):
                    time.sleep(LIMITS["poll_seconds"])
            summary["status"] = "complete" if all(s["status"] == "complete" for s in states.values()) else "ended_with_execution_stop"
        except BaseException as error:
            summary["error"] = {"type": type(error).__name__, "message": str(error)}
            for c in list(active):
                finish(c, "supervisor_interrupted")
            for state in states.values():
                if state["status"] == "not_started":
                    state.update(status="stopped", stop_reason="supervisor_interrupted",
                                 ended_at=time.time(), elapsed_gpu_seconds=0)
            summary["status"] = "interrupted"
            raise
        finally:
            summary["ended_at"] = time.time()
            publish()
    write(root / "next-stage-decision.json", results(plan, root)["next_stage"])
    return summary



def compact_row(row, slot, *, origin, progress_ref, progress_index, original_row=None,
                recovery_ref=None):
    value = {**copy.deepcopy(slot), "status": row.get("status", "not_started"),
             "record_validity": row.get("record_validity"),
             **{key: row.get(key) for key in SCORES}, "training_eligible": False,
             "evidence_origin": origin,
             "evidence": {"progress": progress_ref, "progress_index": progress_index}}
    for key in ("entry", "assessment", "evaluation_guard"):
        if key in row:
            value["evidence"][key] = row[key]
    if recovery_ref is not None:
        value["evidence"]["record_recovery"] = recovery_ref
    budget_row = original_row if original_row is not None else row
    budget = budget_row.get("team_budget", {})
    model, tests = budget.get("model", {}), budget.get("tests", {})
    value["recorded_usage"] = {key: model.get(key) for key in (
        "decisions", "attempts", "charged_tokens", "held_tokens")}
    value["recorded_usage"]["test_runs"] = tests.get("used")
    for key in ("started_at", "ended_at"):
        value[key] = budget_row.get(key)
    if original_row is not None:
        value["source_original_status"] = original_row.get("status")
        value["source_execution_error"] = original_row.get("error")
        value["original_worker_status_preserved"] = "execution_error"
    return value


def cost_summary(plan, supervisor):
    old = read_json(checked(plan["original"]["supervisor"]))
    intervals, old_intervals, new_intervals = [], [], []
    for stage, summary, output in (("original_v033", old, old_intervals),
                                   ("new_v033r1", supervisor, new_intervals)):
        for candidate in CANDIDATES:
            state = summary["states"][candidate]
            if not state.get("attempted") or state.get("ended_at") is None:
                continue
            start, end = state["started_at"], state["ended_at"]
            if (not all(isinstance(value, (int, float)) and math.isfinite(value)
                        for value in (start, end)) or end < start):
                raise ValueError("Invalid recorded worker interval")
            output.append(GpuInterval(state["gpu"], round(start * 1_000_000), round(end * 1_000_000)))
            intervals.append({"stage": stage, "candidate_id": candidate, "gpu": state["gpu"],
                              "pid": state.get("pid"), "started_at": start, "ended_at": end,
                              "recorded_worker_seconds": state["elapsed_gpu_seconds"]})
    calculated = interval_accounting(old_intervals, new_intervals)
    mapping = {"worker_union": "original_worker_union", "reservation_union": "new_worker_union",
               "worker_reservation_overlap": "original_new_overlap", "combined_union": "combined_worker_union"}
    return {
        "original_worker_gpu_seconds": old["worker_gpu_seconds"],
        "new_distinct_worker_gpu_seconds": sum(row["recorded_worker_seconds"] for row in intervals
                                                if row["stage"] == "new_v033r1"),
        "new_running_gpu_seconds": supervisor.get("running_gpu_seconds", 0),
        "recorded_worker_intervals": intervals,
        "interval_unions": {renamed: calculated["totals"][key] for key, renamed in mapping.items()},
        "per_gpu": [{"gpu": item["gpu"], **{renamed: item[key] for key, renamed in mapping.items()}}
                    for item in calculated["per_gpu"]],
        "scope": "Terminal single-GPU worker assigned-to-end intervals only; per-GPU union explicitly removes overlap. Historical and new costs stay separate. Offline record export has zero model/GPU cost; CPU work and unrecorded reservation intervals are excluded.",
    }


def results(plan, root):
    root = Path(root)
    supervisor = read_json(root / "supervisor.json")
    recovery = read_json(checked(plan["record_recovery"]))
    outcomes, pairs, candidate_results = {}, [], {}
    for candidate in CANDIDATES:
        actual = root / candidate / "actual"
        fresh = observe_rows(actual, plan["remaining_inventories"][candidate])
        worker = read(actual / "report.json") or {}
        old_progress_ref = plan["original"]["candidates"][candidate]["progress"]
        old_rows = read_json(checked(old_progress_ref))
        recovered_rows = recovery["candidates"][candidate]["rows"]
        fresh_progress = actual / "diagnostics/progress.json"
        fresh_progress_ref = reference(fresh_progress) if fresh_progress.exists() else None
        rows = []
        for index, slot in enumerate(plan["inventories"][candidate]):
            if index < 2:
                rows.append(compact_row(recovered_rows[index], slot, origin="offline_recovered_original_v033",
                    progress_ref=old_progress_ref, progress_index=index, original_row=old_rows[index],
                    recovery_ref=plan["record_recovery"]))
            else:
                row = fresh[index - 2] if index - 2 < len(fresh) else {}
                rows.append(compact_row(row, slot, origin="new_v033r1" if row else "not_started",
                    progress_ref=fresh_progress_ref if row else None,
                    progress_index=index - 2 if row else None))
        outcomes[candidate] = rows
        conditions = {}
        for condition in ("S", "T"):
            subset = [row for row in rows if row["condition"] == condition]
            conditions[condition] = {
                "expected": 4, "known": sum(known(row) for row in subset),
                "not_started": sum(row["status"] == "not_started" for row in subset),
                "technical_unknown": sum(not known(row) and row["status"] != "not_started" for row in subset),
                "complete_deliveries": sum(known(row) and row["R"] == 1 and row["complete_delivery"] is True for row in subset),
                "content_known": sum(type(row["content_correct"]) is bool for row in subset),
                "content_correct": sum(row["content_correct"] is True for row in subset),
                "process_known": sum(type(row["required_process_satisfied"]) is bool for row in subset),
                "process_satisfied": sum(row["required_process_satisfied"] is True for row in subset),
            }
        complete_pairs = 0
        for case, seed in sorted({(row["case_id"], row["sampling_seed"]) for row in rows}):
            matching = {row["condition"]: row for row in rows
                        if (row["case_id"], row["sampling_seed"]) == (case, seed)}
            single, team = matching["S"], matching["T"]
            sr, tr = single["R"] if known(single) else None, team["R"] if known(team) else None
            assessed = sr is not None and tr is not None
            pattern = ({(0, 0): "both_failed", (1, 0): "single_only", (0, 1): "team_only", (1, 1): "both_succeeded"}[(sr, tr)]
                       if assessed else "unknown_or_not_started")
            complete_pairs += int(pattern == "both_succeeded")
            pairs.append({"candidate_id": candidate, "case_id": case, "sampling_seed": seed,
                          "S": sr, "T": tr, "T_minus_S": tr - sr if assessed else None, "pattern": pattern})
        all_known = all(known(row) for row in rows)
        trusted_worker = (supervisor["states"][candidate]["status"] == "complete"
            and worker.get("status") == "complete" and worker.get("execution_binding_passed") is True
            and worker.get("common_restored_exactly") is True and worker.get("screening_optimizer_steps") == 0
            and worker.get("diagnostic_optimizer_steps") == 0
            and worker.get("source_before") == plan["source"] and worker.get("source_after") == plan["source"])
        candidate_results[candidate] = {
            "conditions": conditions, "all_eight_known_valid": all_known,
            "recovery_worker_trusted": trusted_worker, "pairs_both_succeeded": complete_pairs,
            "local_team_feasibility": trusted_worker and all_known and conditions["T"]["complete_deliveries"] >= 1,
            "worker_status": worker.get("status"), "state_status": supervisor["states"][candidate]["status"],
            "state_stop_reason": supervisor["states"][candidate].get("stop_reason"),
            "worker": reference(actual / "report.json") if (actual / "report.json").exists() else None,
        }
    terminal = all(supervisor["states"][c]["status"] in TERMINAL for c in CANDIDATES)
    eligible = [c for c in CANDIDATES if candidate_results[c]["local_team_feasibility"]] if terminal else []
    eligible.sort(key=lambda c: (-candidate_results[c]["conditions"]["T"]["complete_deliveries"],
                                -candidate_results[c]["pairs_both_succeeded"], CANDIDATES.index(c)))
    unresolved = any(not row["all_eight_known_valid"] or not row["recovery_worker_trusted"]
                     for row in candidate_results.values())
    if not terminal:
        status = "pending"
    elif eligible:
        status = "fresh_support_candidate_identified"
    elif unresolved:
        status = "technical_unknown_no_carrier_decision"
    else:
        status = "no_local_team_carrier"
    next_stage = {"status": status, "support_collection_candidate": eligible[0] if eligible else None,
        "rule": NEXT_STAGE_RULE, "prior_v030_selected_candidate": None, "old_selection_reclassified": False,
        "automatic_execution": False, "development_records_are_training_support": False,
        "all_team_zero_branch_applied": status == "no_local_team_carrier",
        "required_next_design": (
            "Continue the fixed remaining slots as GPU capacity becomes available" if status == "pending" else
            "Freeze fresh training-source current-strategy support and fair affordable B/G/I dimensions" if eligible else
            "Resolve the technical unknown without treating it as an observed zero score" if unresolved else
            "Design a less domain-complex root goal retaining empty-task O1 and true API-consumer dependency"),
    }
    counts = {}
    for origin in ("offline_recovered_original_v033", "new_v033r1"):
        selected = [row for rows in outcomes.values() for row in rows if row["evidence_origin"] == origin]
        counts[origin] = {"rows_observed": len(selected),
            "recorded_attempts": sum(row["recorded_usage"]["attempts"] or 0 for row in selected),
            "recorded_charged_tokens": sum(row["recorded_usage"]["charged_tokens"] or 0 for row in selected),
            "usage_known_rows": sum(type(row["recorded_usage"]["attempts"]) is int for row in selected)}
    return {
        "version": VERSION, "generated_at": time.time(), "status": supervisor["status"],
        "source": plan["source"], "plan": reference(root / "plan.json"),
        "supervisor": reference(root / "supervisor.json"), "record_recovery": plan["record_recovery"],
        "original_plan": plan["original"]["plan"], "original_supervisor": plan["original"]["supervisor"],
        "original_execution_status": "ended_with_execution_stop", "original_execution_stop_preserved": True,
        "historical_v030_v032_results_reclassified": False, "v033_record_validity_reinterpreted": True,
        "business_assessments_regraded": False,
        "outcomes": outcomes, "candidate_results": candidate_results, "paired_outcomes": pairs,
        "next_stage": next_stage, "selected_candidate": None, "allocation_experiment_started": False,
        "optimizer_steps": 0, "fresh_technical_quiz_calls": 0, "repeat_near_16k_stress": False,
        "logical_inventory_count": 16, "recovered_original_slots": 4, "new_slot_limit": 12,
        "sampling_summary": counts, "cost": cost_summary(plan, supervisor), "scope": plan["scope"],
        "detail_storage": "Full boundaries, member views, traces and team-ledger records remain in referenced runs artifacts; this published report contains compact rows and immutable references only.",
    }


def report(run_root, output_dir):
    root, output = Path(run_root).resolve(), Path(output_dir).resolve()
    value = results(read_json(root / "plan.json"), root)
    output.mkdir(parents=True, exist_ok=True)
    write(output / "software-paired-o1-v033-recovery.json", value)
    lines = ["# v0.33r1 原固定单人／团队诊断的记录修复与未开始槽接续", "",
        f"状态：`{value['status']}`；新源码：`{value['source']['code_commit']}`；新原件：`{root}`。", "",
        "原 v030–v032 业务结果和候选筛选结论不改。此次确实修正 v033 的记录分类：原 T 行的 unknown 经离线成员视图重导出成为派生可信记录；原业务验收分数仍取原 assessment，原 v033 execution-stop 原件保持原样。四条已经执行的记录不重新验收、重采样或产生参数更新。这里只新执行原库存余下十二槽，每模型六槽；合并后仍是原两模型各八槽、共十六个逻辑槽。", "",
        "同一原 common、原模型 profile、固定 seed、根目标、合同与初始信息关系不变；S/T 各有共同团队总上限 128 决定、128 尝试、500000 token、32 次 run_tests。没有新增资格题、16K 压力、优化步骤或自动重试。", "",
        "| 模型 | 根目标 | seed | S 完整 R | T 完整 R | T-S | 配对观察 |",
        "|---|---|---:|---:|---:|---:|---|"]
    for pair in value["paired_outcomes"]:
        def display(key):
            return "未知/未开始" if pair[key] is None else str(pair[key])
        lines.append(f"| {pair['candidate_id']} | {pair['case_id']} | {pair['sampling_seed']} | {display('S')} | {display('T')} | {display('T_minus_S')} | {pair['pattern']} |")
    lines += ["", "每一侧独立展示其已知结果；只有两侧都已知才计算 T-S。未知和未开始不补零。", "",
              "| 模型 | 条件 | 完整交付／已知 | 内容通过／已知 | 过程通过／已知 | 未开始 | 技术未知 |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for candidate, result in value["candidate_results"].items():
        for condition, row in result["conditions"].items():
            lines.append(f"| {candidate} | {condition} | {row['complete_deliveries']}/{row['known']} | {row['content_correct']}/{row['content_known']} | {row['process_satisfied']}/{row['process_known']} | {row['not_started']} | {row['technical_unknown']} |")
    decision, cost = value["next_stage"], value["cost"]
    union = cost["interval_unions"]
    lines += ["", f"后续决策：`{decision['status']}`；新训练来源支持采集候选：`{decision['support_collection_candidate']}`。",
        "局部候选仍须该模型八条完整可信、common 保持一致且 T 至少一条完整交付；这不追认原 v030 winner。若无合格候选而尚有技术未知，不使用“全 T 为零”的研究分支。另一模型技术停止不会抹去一个已经完整合格模型的事前资格。", "",
        "| 成本口径 | GPU 秒 |", "|---|---:|",
        f"| 原 v033 两 worker 已记录成本 | {cost['original_worker_gpu_seconds']:.9f} |",
        f"| 本次新 distinct worker 成本 | {cost['new_distinct_worker_gpu_seconds']:.9f} |",
        f"| 原／新区间同卡交集 | {union['original_new_overlap']['gpu_seconds']:.6f} |",
        f"| 原／新已结束 worker 区间并集 | {union['combined_worker_union']['gpu_seconds']:.6f} |",
        f"| 当前新 worker 运行中墙钟（暂未闭合） | {cost['new_running_gpu_seconds']:.6f} |", "",
        "这些是按每卡 assigned→ended 区间计算的 worker GPU 秒，不代表 GPU 利用率；原成本、新增成本和并集分列。离线导出不新增模型调用或 GPU 工作，CPU 修订成本未计入。", "",
        "| 记录来源 | 已观察槽 | 已记录模型尝试 | 已记录 token | 有用量记录槽 |", "|---|---:|---:|---:|---:|"]
    for origin, row in value["sampling_summary"].items():
        lines.append(f"| {origin} | {row['rows_observed']} | {row['recorded_attempts']} | {row['recorded_charged_tokens']} | {row['usage_known_rows']} |")
    lines += ["", "用量汇总只覆盖有留存账本的观察行，未开始和未能导出的技术未知不会被猜测为零次执行。旧记录在合并视图只计一次，不把导出操作当新采样。每行列出原/新/派生来源和原件引用；完整 boundary、成员视图、transport、team ledger 只保存在服务器 runs 原件。", "",
        "这仍是有限开发工作行为诊断，正式优化步骤为零；不能推出 ID-VTDO 收益、训练效果、通用团队优劣或独立来源泛化。后续训练必须使用新冻结的训练来源和当前策略采集，开发记录不转作训练。", ""]
    (output / "software-paired-o1-v033-recovery.md").write_text("\n".join(lines))
    return value


def finish(plan_path, run_root, report_repo, *, publish=False):
    plan_path, run_root, report_repo = (Path(p).resolve() for p in (plan_path, run_root, report_repo))
    if run_root.exists():
        raise FileExistsError("Do not retry or append a previously started paired diagnostic")
    path = run_root.parent / (run_root.name + "-finish.json")
    state = {"version": VERSION, "status": "supervising", "started_at": time.time(), "run_root": str(run_root)}
    write(path, state)
    process = subprocess.run([sys.executable, "-m", "scripts.continue_paired_o1_v033r1", "supervise", "--plan", str(plan_path),
                              "--run-root", str(run_root)], cwd=SOURCE, check=False)
    state["supervisor_exit_code"] = process.returncode
    if not (run_root / "supervisor.json").exists():
        state.update(status="failed_before_run_archive", ended_at=time.time())
        write(path, state)
        return state
    report(run_root, report_repo / "docs/experiments")
    state["status"] = "reported"
    write(path, state)
    if publish:
        if subprocess.check_output(["git", "branch", "--show-current"], cwd=report_repo, text=True).strip() != "main":
            state["publish_status"] = "repository_branch_changed"
        else:
            subprocess.run(["git", "add", "--", *REPORT_PATHS], cwd=report_repo, check=True)
            change = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *REPORT_PATHS], cwd=report_repo).returncode
            if change == 1:
                subprocess.run(["git", "commit", "--only", "-m", "docs: archive v033 recovery without repeated completed slots", "--", *REPORT_PATHS], cwd=report_repo, check=True)
            elif change != 0:
                raise RuntimeError("Cannot inspect the fixed v033 report paths")
            state["report_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=report_repo, text=True).strip()
            env = {key: value for key, value in os.environ.items() if key.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
            attempts = []
            for index in range(3):
                result = subprocess.run(["git", "push", "origin", "main"], cwd=report_repo, env=env, capture_output=True, text=True, timeout=90)
                attempts.append({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
                if result.returncode == 0:
                    break
                if index < 2:
                    time.sleep(10)
            state.update(publish_status="pushed" if attempts[-1]["returncode"] == 0 else "push_failed", push_attempts=attempts)
    state["ended_at"] = time.time()
    write(path, state)
    return state



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "worker", "supervise", "report", "finish"])
    for name in ("data-root", "cpu-qualification", "prior-run-root", "record-recovery", "plan",
                 "run-root", "output", "report-repo"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--candidate", choices=CANDIDATES)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    required = {
        "prepare": ("data_root", "cpu_qualification", "prior_run_root", "record_recovery", "output"),
        "worker": ("plan", "candidate", "output"), "supervise": ("plan", "run_root"),
        "report": ("run_root", "output"), "finish": ("plan", "run_root", "report_repo"),
    }
    if any(getattr(args, key) is None for key in required[args.mode]):
        parser.error(args.mode + " requires " + ", ".join(required[args.mode]))
    def interrupted(signum, frame):
        raise KeyboardInterrupt("Paired recovery received signal " + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    if args.mode == "prepare":
        value = validate_plan(make_plan(args.data_root, args.cpu_qualification,
                                       args.prior_run_root, args.record_recovery))
        write(args.output, value)
    elif args.mode == "worker":
        value = run_worker(args.plan, args.candidate, args.output)
    elif args.mode == "supervise":
        value = supervise(args.plan, args.run_root)
    elif args.mode == "report":
        value = report(args.run_root, args.output)
    else:
        value = finish(args.plan, args.run_root, args.report_repo, publish=args.publish)
    print(json.dumps({"version": VERSION, "status": value.get("status", "written")}))


if __name__ == "__main__":
    main()
