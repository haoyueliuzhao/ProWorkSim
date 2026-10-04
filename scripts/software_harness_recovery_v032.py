"""One independent SWE harness revision; preserve every previous score and cost.

The original numerical learner/profile/common state is unchanged. A fresh
zero-argument interface check gates twelve original development slots under the
new public manual, feedback and exact local token-reservation implementation.
"""
from __future__ import annotations

import argparse
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
from proworksim.storage import digest, read_json
from scripts import continue_model_selection_v031 as continuation
from scripts import software_model_selection_v030 as original
from scripts import software_model_selection_v031 as previous
from scripts import software_path_recovery_v031r2 as path_recovery
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import checked, lock, read, reference, resources, write
from scripts.software_development_v028 import available_cards, task

VERSION = "software-harness-recovery-v0.32"
SOURCE = Path(__file__).resolve().parents[1]
CANDIDATE = "swe-next-14b"
GPU_ORDER = [4, 6, 5, 0, 1, 2, 3, 7]
LIMITS = copy.deepcopy(previous.LIMITS)
REPORT_PATHS = ["docs/experiments/software-harness-recovery-v032.md",
                "docs/experiments/software-harness-recovery-v032.json"]
UNCHANGED = ("data_root", "candidates", "inventories", "candidate_profiles", "selection_rule",
             "purpose", "mode", "interface_revision", "owner_recipe", "prior_model_plan", "checkpoint_marker",
             "source_metadata", "download_manifests", "runtime_dependency_path", "limits")
HARNESS_LIMITS = {"fresh_native_calls_max": 4, "fresh_native_calls_without_read_correction": 3,
               "read_feedback_corrections_max": 1, "new_optimizer_steps": 0,
               "repeat_near_16k_stress": False, "screening_episodes_max": 12}


def _checked(ref):
    path = Path(ref["path"])
    if digest(path.read_bytes()) != ref["sha256"] or ("bytes" in ref and path.stat().st_size != ref["bytes"]):
        raise ValueError("Frozen inherited artifact changed: " + str(path))
    return path


def implementation_files():
    names = set(previous.implementation_files()) | {
        "scripts/software_harness_recovery_v032.py", "scripts/continue_model_selection_v031.py",
        "src/proworksim/native_harness_admission_v032.py"}
    return {name: digest((SOURCE / name).read_bytes()) for name in sorted(names)}


ALLOWED_SOURCE_REVISIONS = (
    "scripts/software_development_v028.py", "scripts/software_model_selection_v030.py",
    "src/proworksim/harness_sdk.py", "src/proworksim/model_policy.py",
    "src/proworksim/native_codecs_v031.py", "src/proworksim/software_context_v028.py",
    "src/proworksim/software_runtime_v030.py",
)


def unchanged_source(prior_plan):
    """Bind the seven declared harness edits and byte-preserve all other old code."""
    old_root = Path(prior_plan["source_root"])
    names = {str(path.relative_to(old_root)) for prefix in ("src", "scripts")
             for path in (old_root / prefix).rglob("*.py")}
    for prefix in ("examples/software-sources-v030", "examples/software-v15/upstream"):
        names.update(str(path.relative_to(old_root)) for path in (old_root / prefix).rglob("*") if path.is_file())
    protected, revisions = {}, {}
    for name in sorted(names):
        before, after = old_root / name, SOURCE / name
        if not after.is_file():
            raise ValueError("An inherited runtime or public asset disappeared: " + name)
        old_hash, new_hash = digest(before.read_bytes()), digest(after.read_bytes())
        if name in ALLOWED_SOURCE_REVISIONS:
            revisions[name] = {"before_sha256": old_hash, "after_sha256": new_hash,
                               "changed": old_hash != new_hash}
        elif old_hash != new_hash:
            raise ValueError("An undeclared numerical/runtime/world source changed: " + name)
        else:
            protected[name] = new_hash
    if set(revisions) != set(ALLOWED_SOURCE_REVISIONS):
        raise ValueError("The frozen r2 checkout must contain every declared harness revision path")
    return {"prior_source_root": str(old_root), "prior_source": prior_plan["source"],
            "protected_files_sha256": protected, "declared_revisions": revisions,
            "scope": "Only the seven declared manual/feedback/budget/terminal paths may differ. Original actor, profile, probability, full-gradient, world, seed and acceptance implementation stays byte-identical."}


def prior_snapshot(prior_run_root):
    """Bind original v031 numerical proof plus the complete unrejudged r2 run."""
    root = Path(prior_run_root).resolve()
    plan = read_json(root / "plan.json")
    if plan.get("version") != path_recovery.VERSION:
        raise ValueError("Use the closed v031r2 path recovery as this revision's immediate predecessor")
    inherited = path_recovery.prior_snapshot(plan["prior"]["run_root"])
    if inherited != plan["prior"]:
        raise ValueError("The original v031 SWE numerical/path-failure evidence changed after r2")
    actual = root / CANDIDATE / "actual"
    state = read_json(root / CANDIDATE / "state.json")
    worker = read_json(actual / "report.json")
    qualification = read_json(actual / "qualification/report.json")
    if (plan.get("execution_candidates") != [CANDIDATE] or plan.get("new_screening_episodes_max") != 12
            or state.get("candidate_id") != CANDIDATE or state.get("status") != "complete"
            or state.get("exit_code") != 0 or state.get("stop_reason") is not None or not state.get("ended_at")
            or worker.get("candidate_id") != CANDIDATE or worker.get("status") != "complete"
            or worker.get("source_before") != plan["source"] or worker.get("source_after") != plan["source"]
            or worker.get("qualification") != qualification or read_json(actual / "qualification-result.json") != qualification
            or worker.get("screening_optimizer_steps") != 0 or (worker.get("actor_steps"), worker.get("critic_steps")) != (0, 0)
            or read_json(actual / "progress.json") != worker.get("rows")):
        raise ValueError("The previous SWE r2 worker must be complete and retain every original screening row")
    if (any(qualification.get(key) is not True for key in ("inference_ready", "training_ready", "common_restored_exactly"))
            or qualification.get("optimizer_steps") != 0 or qualification.get("new_optimizer_steps") != 0
            or qualification.get("errors") != [] or qualification.get("near_16k_stress_rerun") is not False
            or any(qualification.get(key, {}).get("state_tensor_digest") != inherited["common_state_tensor_digest"]
                   for key in ("common_before", "common_after"))):
        raise ValueError("Preserve r2's passed zero-step path admission and exact original common restoration")
    result = original.candidate_result(plan, CANDIDATE, worker, state)
    if (not result["all_12_known"] or result["screening_rows_recorded"] != 12
            or any(row.get("R") != 0 or row.get("complete_work") is not False for row in worker["rows"])):
        raise ValueError("Bind exactly the twelve closed original r2 failures without reclassification")
    references = {"plan": reference(root / "plan.json"), "worker_state": reference(root / CANDIDATE / "state.json"),
        "worker_report": reference(actual / "report.json"), "qualification": reference(actual / "qualification/report.json"),
        "qualification_result": reference(actual / "qualification-result.json"), "progress": reference(actual / "progress.json")}
    for row in worker["rows"]:
        for kind in ("entry", "assessment", "evaluation_guard"):
            references[row["slot_id"] + "/" + kind] = copy.deepcopy(row[kind])
            _checked(row[kind])
        guard = read_json(_checked(row["evaluation_guard"]))
        if any(guard.get(key) is not True for key in (
                "learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged")):
            raise ValueError("The previous r2 screening must have retained its complete frozen evaluation guard")
    for index in range(1, qualification["native_calls_executed"] + 1):
        for kind in ("request", "response"):
            references[f"native_call_{index}_{kind}"] = reference(actual / "qualification" / f"native-call-{index}" / (kind + ".json"))
    seconds = previous._seconds(state.get("elapsed_gpu_seconds"), "cumulative v031 plus r2 SWE cost")
    parts = state.get("cost_components", {})
    expected_parts = {**inherited["historical_cost_components"],
                      "v031r2_worker_gpu_seconds": previous._seconds(parts.get("v031r2_worker_gpu_seconds"), "r2 worker")}
    if (parts != expected_parts or abs(sum(parts.values()) - seconds) > 1e-6
            or abs(seconds - inherited["historical_gpu_seconds"] - parts["v031r2_worker_gpu_seconds"]) > 1e-6):
        raise ValueError("Count the old 3080-second lineage and r2 assigned worker exactly once")
    return {"run_root": str(root), "original_run_root": inherited["run_root"],
            "actual_directory": inherited["actual_directory"], "references": inherited["references"],
            "original_source": inherited["source"], "source": plan["source"], "state": state,
            "historical_gpu_seconds": seconds, "historical_cost_components": copy.deepcopy(parts),
            "common_actor_identity": inherited["common_actor_identity"],
            "common_state_tensor_digest": inherited["common_state_tensor_digest"],
            "original_path_failure": inherited["original_path_failure"],
            "r2": {"references": references, "candidate_result": result, "rows": worker["rows"],
                   "prior_common_restored_exactly": True, "old_scores_reclassified": False}}


def make_plan(data_root, cpu_qualification, prior_run_root, reservation_directory=None):
    prior = prior_snapshot(prior_run_root)
    old = read_json(_checked(prior["r2"]["references"]["plan"]))
    if str(Path(data_root).resolve()) != old["data_root"]:
        raise ValueError("Use the same completed model files and historical data root")
    roots = previous._artifact_roots([*old["artifact_roots"], prior["run_root"]])
    return {**{key: copy.deepcopy(old[key]) for key in UNCHANGED},
        "version": VERSION, "created_at": time.time(), "source": code_identity(), "source_root": str(SOURCE),
        "implementation_files_sha256": implementation_files(), "qualification": reference(cpu_qualification),
        "prior": prior, "unchanged_source": unchanged_source(old), "artifact_roots": roots,
        "allowed_source_revisions": list(ALLOWED_SOURCE_REVISIONS), "native_profile_unchanged": True,
        "old_scores_reclassified": False, "harness_development_revision": True,
        "gpu_preference": GPU_ORDER, "execution_candidates": [CANDIDATE], "max_new_model_instances": 1,
        "new_screening_episodes_max": 12, "harness_admission_limits": copy.deepcopy(HARNESS_LIMITS),
        "automatic_retries": False, "automatic_model_replacement": False, "automatic_successors": [],
        "final_model_selection": False, "allocation_experiment_started": False,
        "total_gpu_seconds": None, "worker_gpu_seconds": None, "queue_deadline_at": None, "wall_deadline_at": None,
        "reservation_directory": str(Path(reservation_directory).resolve()) if reservation_directory else None,
        "authorization": "User requested diagnosis and repair of SWE termination causes, continuation as a new revision, and reservation of free GPU4.",
        "statistics_scope": "One independent SWE harness-development revision after the complete r2 zero-of-twelve result. Inherit original numerical controls, rerun the same twelve development slots, retain old scores and other candidates read-only.",
        "cost_rule": "Original v031 cumulative SWE cost plus r2 worker once plus v032 assigned-worker duration; no old score rewrite or final three-model ranking"}


def validate_plan(plan, *, check_files=True):
    if (plan.get("version") != VERSION or plan.get("execution_candidates") != [CANDIDATE]
            or plan.get("candidates") != list(original.CANDIDATES)
            or plan.get("inventories") != {candidate: original.inventory() for candidate in original.CANDIDATES}
            or plan.get("candidate_profiles") != {candidate: previous.backend_profile(candidate) for candidate in previous.EXECUTED}
            or plan.get("selection_rule") != original.SELECTION_RULE or plan.get("limits") != LIMITS
            or plan.get("gpu_preference") != GPU_ORDER or plan.get("max_new_model_instances") != 1
            or plan.get("new_screening_episodes_max") != 12 or plan.get("harness_admission_limits") != HARNESS_LIMITS
            or plan.get("automatic_retries") is not False or plan.get("automatic_model_replacement") is not False
            or plan.get("automatic_successors") != [] or plan.get("final_model_selection") is not False
            or plan.get("allocation_experiment_started") is not False
            or plan.get("allowed_source_revisions") != list(ALLOWED_SOURCE_REVISIONS)
            or plan.get("native_profile_unchanged") is not True or plan.get("old_scores_reclassified") is not False
            or plan.get("harness_development_revision") is not True
            or any(plan.get(key) is not None for key in ("total_gpu_seconds", "worker_gpu_seconds", "queue_deadline_at", "wall_deadline_at"))):
        raise ValueError("Only the declared SWE harness revision and unchanged twelve-slot development screening are authorized")
    if check_files:
        if (plan.get("source") != code_identity() or plan["source"].get("code_dirty") is not False
                or plan.get("source_root") != str(SOURCE) or plan.get("implementation_files_sha256") != implementation_files()):
            raise ValueError("Use the exact clean CPU-qualified source snapshot")
        cpu = read_json(checked(plan["qualification"]))
        if cpu.get("passed") is not True or cpu.get("model_calls") != 0 or cpu.get("source") != plan["source"]:
            raise ValueError("Same-source passing CPU qualification is required")
        if prior_snapshot(plan["prior"]["run_root"]) != plan["prior"]:
            raise ValueError("The original v031 and complete r2 SWE evidence changed")
        old = read_json(_checked(plan["prior"]["r2"]["references"]["plan"]))
        if any(plan.get(key) != old.get(key) for key in UNCHANGED) or unchanged_source(old) != plan["unchanged_source"]:
            raise ValueError("The old runtime, learning recipe, public world, seeds or ranking changed")
        expected_roots = previous._artifact_roots([*old["artifact_roots"], plan["prior"]["run_root"]])
        if plan.get("artifact_roots") != expected_roots:
            raise ValueError("Count all original, recovery, numerical-probe, v031 and r2 artifacts")
        if original.download_state(plan, CANDIDATE).get("status") != "ready":
            raise ValueError("The same fixed SWE model download must already be complete")
    return plan


def artifact_usage(plan, root):
    return sum(artifact_bytes(Path(path)) for path in previous._artifact_roots([*plan["artifact_roots"], root]))


def run_worker(plan_path, output):
    from proworksim.native_harness_admission_v032 import qualify_harness
    from proworksim.online_training import tensor_tree_digest
    from proworksim.software_learning_v029 import migrate_software_owner

    plan = validate_plan(read_json(plan_path))
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if visible not in {str(index) for index in GPU_ORDER}:
        raise ValueError("Bind the one SWE worker to one declared physical GPU")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"version": VERSION, "candidate_id": CANDIDATE, "status": "loading", "started_at": time.time(),
              "source_before": code_identity(), "rows": [], "screening_optimizer_steps": 0,
              "plan": reference(plan_path), "prior_attempt": plan["prior"], "harness_development_revision": True, "old_scores_reclassified": False,
              "inherited_controls_reexecuted": False, "allocation_experiment_started": False}
    owner = None
    write(output / "report.json", report)
    try:
        task(output, "load-original-v031-SWE", "loading")
        sample = resources()
        write(output / "preload-resources.json", sample)
        if int(visible) not in [row["index"] for row in available_cards(plan, sample)]:
            raise RuntimeError("Assigned empty A100 capacity changed before loading")
        refs = plan["prior"]["references"]
        prior_owner = read_json(_checked(refs["owner"]))
        ready = original.download_state(plan, CANDIDATE)
        if (Path(ready["model_path"]).resolve() != Path(prior_owner["base_identity"]["path"]).resolve()
                or _checked(ready["manifest"]) != _checked(refs["base_manifest"])):
            raise ValueError("Restore the same original global model and manifest")
        owner = previous.load_owner(ready["model_path"], manifest=_checked(refs["base_manifest"]),
            profile=plan["candidate_profiles"][CANDIDATE], output=output / "resident", recipe=prior_owner["recipe"])
        write(output / "software-critic-migration.json", migrate_software_owner(owner, expected_steps=None))
        if owner.inference_profile != prior_owner["inference_profile"] or owner.base_identity != prior_owner["base_identity"]:
            raise ValueError("The actual native runtime/base identity differs from the inherited proof")
        task(output, "restore-original-v031-common", "boundary")
        common_dir = _checked(refs["common"]).parent
        common = read_json(common_dir / "checkpoint.json")
        restored = owner.restore_checkpoint(common_dir)
        if (restored != common or tensor_tree_digest(owner._state_bundle(), owner.torch) != common["state_tensor_digest"]
                or owner.freeze_identity() != common["actor_identity"] or (owner.actor_steps, owner.critic_steps) != (0, 0)):
            raise ValueError("The inherited actor/critic/optimizers/RNG common state did not restore exactly")
        write(output / "inherited-common.json", {"checkpoint": refs["common"], "restored_exactly": True,
                                               "state_tensor_digest": common["state_tensor_digest"], "actor_identity": owner.freeze_identity()})
        report.update(status="qualifying", common_actor_identity=owner.freeze_identity())
        write(output / "report.json", report)

        def stage(kind, label):
            if kind not in LIMITS["task_seconds"]:
                raise ValueError("Undeclared harness-admission stage")
            task(output, label, kind)

        qualification = qualify_harness(owner, output / "qualification", common_dir=common_dir,
                                     prior_qualification=refs["qualification"], on_stage=stage)
        report["qualification"] = qualification
        write(output / "qualification-result.json", qualification)
        if (tensor_tree_digest(owner._state_bundle(), owner.torch) != common["state_tensor_digest"]
                or owner.freeze_identity() != common["actor_identity"] or (owner.actor_steps, owner.critic_steps) != (0, 0)):
            raise ValueError("Harness admission did not restore the exact original common learner")
        if not all(qualification.get(key) is True for key in ("inference_ready", "training_ready", "common_restored_exactly")):
            report["status"] = "qualification_failed"
            return report
        if (qualification.get("new_optimizer_steps") != 0 or qualification.get("optimizer_steps") != 0
                or qualification.get("native_calls_executed") not in (3, 4)
                or qualification.get("native_calls_executed") != len(qualification.get("calls", []))
                or qualification.get("correction_calls_executed") not in (0, 1)
                or qualification["native_calls_executed"] != 3 + qualification["correction_calls_executed"]
                or qualification.get("near_16k_stress_rerun") is not False):
            raise ValueError("The harness admission permits three calls plus at most one correction, zero new optimizer steps and no repeated stress")
        report["status"] = "screening"
        write(output / "report.json", report)
        for row in plan["inventories"][CANDIDATE]:
            if owner.freeze_identity() != common["actor_identity"] or (owner.actor_steps, owner.critic_steps) != (0, 0):
                raise ValueError("Frozen screening cannot change the restored identity or optimizer counters")
            folder = output / row["slot_id"]
            entries = original.collect(owner, original.window_spec("v032-" + CANDIDATE + "-" + row["slot_id"], [row]), folder, output)
            report["rows"].append(original._screen_row(row, entries[0], folder))
            write(output / "progress.json", report["rows"])
            write(output / "report.json", report)
        report["status"] = "complete"
    except BaseException as exception:
        report.update(status="interrupted_or_error", error={"type": type(exception).__name__, "message": str(exception)})
        raise
    finally:
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps, final_actor_identity=owner._make_identity())
        report.update(ended_at=time.time(), source_after=code_identity())
        write(output / "report.json", report)
    return report


def supervise(plan_path, run_root):
    plan = validate_plan(read_json(plan_path))
    root = Path(run_root).resolve()
    if any(root == Path(old) or root.is_relative_to(Path(old)) or Path(old).is_relative_to(root) for old in plan["artifact_roots"]):
        raise ValueError("Use an independent new run directory outside every previous artifact root")
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    state = {"candidate_id": CANDIDATE, "status": "not_started", "attempted": False,
             "historical_gpu_seconds": plan["prior"]["historical_gpu_seconds"],
             "cost_components": {**copy.deepcopy(plan["prior"]["historical_cost_components"]), "v032_worker_gpu_seconds": 0.0},
             "elapsed_gpu_seconds": plan["prior"]["historical_gpu_seconds"]}
    summary = {"version": VERSION, "status": "waiting", "source": plan["source"], "started_at": time.time(),
               "observer_pid": os.getpid(), "states": {CANDIDATE: state}, "final_model_selection": False,
               "new_screening_episodes_max": 12, "other_workers_controlled": False}
    process, log, guard, stable = None, None, None, {}
    reservation_done = not plan.get("reservation_directory")
    reservation_plan = {"canonical_plan": plan, "reservation_directory": plan.get("reservation_directory")}

    def publish():
        summary.update(observed_at=time.time(), worker_gpu_seconds=state["elapsed_gpu_seconds"],
                       running_gpu_seconds=time.time() - state["started_at"] if process is not None and state["status"] == "running" else 0)
        write(root / "supervisor.json", summary)
        write(root / CANDIDATE / "state.json", state)

    def close(reason):
        if process is not None:
            continuation._stop_worker(process, state)
            process.wait(timeout=15)
        worker = read(root / CANDIDATE / "actual/report.json") or {}
        okay = (process is not None and process.returncode == 0 and reason is None
                and worker.get("status") in {"complete", "qualification_failed"}
                and worker.get("source_before") == plan["source"] and worker.get("source_after") == plan["source"])
        if not okay and reason is None:
            reason = "worker_report_not_terminal_or_same_source"
        ended = time.time()
        state.update(status=worker["status"] if okay else "stopped", ended_at=ended,
                     exit_code=process.returncode if process is not None else None, stop_reason=reason)
        state["cost_components"]["v032_worker_gpu_seconds"] = max(0, ended - state["started_at"]) if state.get("started_at") else 0.0
        state["elapsed_gpu_seconds"] = sum(state["cost_components"].values())
        if log is not None:
            log.close()
        summary["status"] = state["status"]
        publish()

    with lock(root):
        try:
            while state["status"] not in original.TERMINAL:
                if process is not None and process.poll() is not None:
                    close(None if process.returncode == 0 else "worker_exit_error")
                    break
                size, free = artifact_usage(plan, root), shutil.disk_usage(root).free
                if size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                    close("trajectory_storage_reserve")
                    break
                if process is None:
                    card = None
                    if not reservation_done:
                        card = continuation.handoff_reservation(reservation_plan, root)
                        receipt = read(root / "reservation-handoff.json") or {}
                        reservation_done = receipt.get("status") == "released"
                        if reservation_done and card is None:
                            stable.pop(receipt["launch"]["physical_gpu"], None)
                    if card is None:
                        sample = resources()
                        with (root / "waiting-resources.jsonl").open("a") as stream:
                            stream.write(json.dumps(sample) + "\n")
                        cards, now = available_cards(plan, sample), time.time()
                        stable = {row["index"]: stable.get(row["index"], now) for row in cards}
                        card = next((row for row in cards if now - stable[row["index"]] >= LIMITS["gpu_capacity_stability_seconds"]), None)
                    if card is not None:
                        validate_plan(plan)
                        folder = root / CANDIDATE
                        folder.mkdir(exist_ok=True)
                        argv = [sys.executable, "-m", "scripts.software_harness_recovery_v032", "worker",
                                "--plan", str(root / "plan.json"), "--output", str(folder / "actual")]
                        log = (folder / "worker.log").open("x")
                        state.update(attempted=True, started_at=time.time(), gpu=card["index"], gpu_uuid=card["uuid"], command=argv)
                        process = subprocess.Popen(argv, cwd=SOURCE, env=original.worker_env(plan, root, CANDIDATE, card["index"]),
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        state.update(status="running", pid=process.pid, process_identity=identity)
                        guard = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        if not reservation_done:
                            continuation._cancel_declared_reservation(reservation_plan, root)
                            reservation_done = True
                if process is not None:
                    sample = target_resources(state["gpu"], worker_pid=process.pid)
                    if process.poll() is not None:
                        close(None if process.returncode == 0 else "worker_exit_error")
                        break
                    observation = guard.observe(sample, time.time(), process.pid, state["gpu"], own_memory_limit_mib=LIMITS["own_gpu_memory_mib"])
                    current = read(root / CANDIDATE / "actual/task.json") or {"kind": "loading", "started_at": state["started_at"]}
                    own_rss, reason = rss(process.pid), observation.get("stop_reason")
                    cap = LIMITS["task_seconds"].get(current.get("kind"))
                    if current.get("kind") not in LIMITS["task_seconds"]:
                        reason = reason or "unknown_task_kind"
                    elif cap is not None and time.time() - current["started_at"] >= cap:
                        reason = reason or "single_task_budget"
                    elif own_rss > LIMITS["host_rss_per_worker_bytes"]:
                        reason = reason or "host_memory_budget"
                    with (root / CANDIDATE / "resources.jsonl").open("a") as stream:
                        stream.write(json.dumps({"sample": sample, "guard": observation, "task": current,
                                                 "rss_bytes": own_rss, "artifact_bytes": size, "volume_free_bytes": free}) + "\n")
                    if reason:
                        close(reason)
                        break
                summary["status"] = "running" if process is not None else "waiting"
                publish()
                time.sleep(LIMITS["poll_seconds"])
        except BaseException as exception:
            summary["error"] = {"type": type(exception).__name__, "message": str(exception)}
            if state["status"] not in original.TERMINAL:
                close("supervisor_interrupted")
            raise
        finally:
            if not reservation_done:
                continuation._cancel_declared_reservation(reservation_plan, root)
            summary["ended_at"] = time.time()
            publish()
    return summary


def report(run_root, output_dir):
    root, output = Path(run_root).resolve(), Path(output_dir).resolve()
    plan, supervisor = read_json(root / "plan.json"), read_json(root / "supervisor.json")
    actual = root / CANDIDATE / "actual"
    worker = read(actual / "report.json") or {}
    current = read(actual / "progress.json")
    if current is not None and len(current) > len(worker.get("rows", [])):
        worker = {**worker, "rows": current}
    qualification = read(actual / "qualification/report.json") or worker.get("qualification") or {}
    result = original.candidate_result(plan, CANDIDATE, worker, supervisor["states"][CANDIDATE])
    old_root = Path(plan["prior"]["original_run_root"])
    live_supervisor = read(old_root / "supervisor.json") or {}
    references = {}
    for candidate in original.CANDIDATES:
        if candidate == CANDIDATE:
            continue
        prior_worker = read(old_root / candidate / "actual/report.json") or {}
        prior_state = live_supervisor.get("states", {}).get(candidate, {"status": "not_observed"})
        references[candidate] = {"state_observed": copy.deepcopy(prior_state),
            "worker_report": reference(old_root / candidate / "actual/report.json") if prior_worker else None,
            "screening_rows_recorded": len(prior_worker.get("rows", [])),
            "status": prior_state.get("status"), "rerun_by_this_recovery": False,
            "scope": "Read-only observation; the original v031 controller may continue updating this candidate"}
    value = {"version": VERSION, "generated_at": time.time(), "run_root": str(root), "plan": plan,
        "plan_reference": reference(root / "plan.json"), "supervisor": supervisor,
        "worker_report": reference(actual / "report.json") if (actual / "report.json").exists() else None,
        "qualification": qualification, "candidate_result": result, "outcomes": worker.get("rows", []),
        "prior_path_failure": copy.deepcopy(plan["prior"]["original_path_failure"]), "reference_candidates": references,
        "prior_r2_outcomes": copy.deepcopy(plan["prior"]["r2"]["rows"]), "old_scores_reclassified": False,
        "allowed_source_revisions": plan["allowed_source_revisions"], "native_profile_unchanged": True,
        "final_model_selection": None, "selected_candidate": None, "allocation_experiment_started": False,
        "selection_scope": "No final three-model chooser runs in this independent harness revision, even if another candidate becomes terminal",
        "scope": plan["statistics_scope"], "cost_rule": plan["cost_rule"]}
    output.mkdir(parents=True, exist_ok=True)
    write(output / "software-harness-recovery-v032.json", value)
    lines = ["# SWE v0.32 工具说明、反馈与预算准入修订", "",
        f"状态：`{supervisor['status']}`；源码：`{plan['source']['code_commit']}`；原始目录：`{root}`。", "",
        "本次为独立的新harness开发修订。原v031路径准入失败和r2已闭合12槽0/12全部原样保留，未重判或覆盖旧成绩。仅修改显式允许的公开工具手册、错误反馈、精确本地token预约／透传和终态细分代码；原actor、native syntax、profile、数值门、世界、两seed、role额度和验收／排名规则不变。", "",
        "先恢复原v031完整actor／critic／optimizer／RNG common，再做真实无参读取＋8K事实／10K实际错误反馈的新技术准入。通常3次调用，首次真实读取失败且完整trace时最多一次纠正，总计最多4次。每条新完整轨迹都经原概率门与完整零step反向；原16K／1次更新／保存重载／新身份回流证据只在同一common下继承，不重复长stress，不声称本次重新测量。", "",
        f"新推理准入：`{qualification.get('inference_ready')}`；训练准入：`{qualification.get('training_ready')}`；完整common恢复：`{qualification.get('common_restored_exactly')}`。", "",
        "通过新准入才执行原六开发合同×两seed完整12槽一次。停止减少、合法调用增加、测试通过或任务创建均不自动等于固定集成交付；新修订是否改善结果以本次实际记录为准，不能由修订设计推断。未启动／未闭合不补0。", "",
        "| 案例／seed | 原r2 R | v032状态 | v032完整交付 | v032 R |", "|---|---:|---|---|---:|"]
    rows = {row["slot_id"]: row for row in worker.get("rows", [])}
    old_rows = {row["slot_id"]: row for row in plan["prior"]["r2"]["rows"]}
    for slot in plan["inventories"][CANDIDATE]:
        row = rows.get(slot["slot_id"], {})
        lines.append(f"| {slot['case_id']} / {slot['sampling_seed']} | {old_rows[slot['slot_id']]['R']} | {row.get('status', 'not_started_or_not_closed')} | {row.get('complete_work')} | {row.get('R')} |")
    lines += ["", "| 类别 | v032完整成功／已知 |", "|---|---:|"]
    for category, counts in result["categories"].items():
        lines.append(f"| {category} | {counts['successful_complete_deliveries']}/{counts['known']} |")
    lines += ["", f"SWE本次是否满足原候选可选门：`{result['selection_eligible']}`；这不等于三模型最终选中。", "",
              "本运行不重启或控制9B／Devstral，不覆盖其报告；其他候选仅保留读取时状态。不执行三模型最终chooser，也不自动启动B/G-raw/I-P。", "",
              "| 成本阶段 | GPU秒 |", "|---|---:|"]
    for key, seconds in supervisor["states"][CANDIDATE]["cost_components"].items():
        lines.append(f"| {key} | {seconds:.6f} |")
    lines += ["", "旧v031累计成本和r2实际worker各只加一次，再加v032完整分配worker墙钟；预约／排队另存记录。原每worker64GiB RSS、全部旧新产物128GiB、卷预留20GiB和单任务帽保持，无累计GPU／排队／总墙钟截止。", "",
              "这仍是已见开发材料上的harness准入和筛选比较，不是参数训练收益、独立确认或分配算法收益。配套JSON保留允许变更前后文件hash、逐字节不变的数值／世界文件、原common、原22项数值证据、r2完整12槽、所有旧成本和新轨迹。", ""]
    (output / "software-harness-recovery-v032.md").write_text("\n".join(lines))
    return value


def finish(plan_path, run_root, report_repo, *, publish=False):
    plan_path, run_root, report_repo = (Path(path).resolve() for path in (plan_path, run_root, report_repo))
    if run_root.exists():
        raise FileExistsError("A new independent harness-recovery directory is required")
    state_path = run_root.parent / (run_root.name + "-finish.json")
    state = {"version": VERSION, "status": "supervising", "started_at": time.time(), "run_root": str(run_root)}
    write(state_path, state)
    process = subprocess.run([sys.executable, "-m", "scripts.software_harness_recovery_v032", "supervise",
                              "--plan", str(plan_path), "--run-root", str(run_root)], cwd=SOURCE, check=False)
    state["supervisor_exit_code"] = process.returncode
    if not (run_root / "supervisor.json").exists():
        state.update(status="failed_before_run_archive", ended_at=time.time())
        write(state_path, state)
        return state
    report(run_root, report_repo / "docs/experiments")
    state["status"] = "reported"
    write(state_path, state)
    if publish:
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=report_repo, text=True).strip()
        if branch != "main":
            state["publish_status"] = "not_published_repository_branch_changed"
        else:
            subprocess.run(["git", "add", "--", *REPORT_PATHS], cwd=report_repo, check=True)
            changed = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *REPORT_PATHS], cwd=report_repo).returncode
            if changed == 1:
                subprocess.run(["git", "commit", "--only", "-m", "docs: archive SWE harness development v032", "--", *REPORT_PATHS],
                               cwd=report_repo, check=True)
            elif changed != 0:
                raise RuntimeError("Cannot determine the fixed v032 report change set")
            state["report_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=report_repo, text=True).strip()
            env = {key: value for key, value in os.environ.items() if key.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
            attempts = []
            for index in range(3):
                result = subprocess.run(["git", "push", "origin", "main"], cwd=report_repo, env=env,
                                        text=True, capture_output=True, timeout=90)
                attempts.append({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
                if result.returncode == 0:
                    break
                if index < 2:
                    time.sleep(10)
            state.update(publish_status="pushed" if attempts[-1]["returncode"] == 0 else "push_failed", push_attempts=attempts)
    state["ended_at"] = time.time()
    write(state_path, state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "worker", "supervise", "report", "finish"])
    for name in ("data-root", "cpu-qualification", "prior-run-root", "reservation-directory", "plan", "output", "run-root", "report-repo"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    required = {"prepare": ("data_root", "cpu_qualification", "prior_run_root", "output"),
                "worker": ("plan", "output"), "supervise": ("plan", "run_root"),
                "report": ("run_root", "output"), "finish": ("plan", "run_root", "report_repo")}
    if any(getattr(args, name) is None for name in required[args.mode]):
        parser.error(args.mode + " requires " + ", ".join(required[args.mode]))
    def interrupted(signum, frame):
        raise KeyboardInterrupt("Harness recovery received signal " + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    if args.mode == "prepare":
        value = validate_plan(make_plan(args.data_root, args.cpu_qualification, args.prior_run_root, args.reservation_directory))
        write(args.output, value)
    elif args.mode == "worker":
        value = run_worker(args.plan, args.output)
    elif args.mode == "supervise":
        value = supervise(args.plan, args.run_root)
    elif args.mode == "report":
        value = report(args.run_root, args.output)
    else:
        value = finish(args.plan, args.run_root, args.report_repo, publish=args.publish)
    print(json.dumps({"version": VERSION, "status": value.get("status", "written")}))


if __name__ == "__main__":
    main()
