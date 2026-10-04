"""One SWE public-path admission repair and its original twelve screening slots.

The already successful v031 numerical/capacity/update controls are inherited
only after restoring the exact same common learner. The old failed read stays
failed. This run neither restarts another candidate nor selects a final model.
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
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import checked, lock, read, reference, resources, write
from scripts.software_development_v028 import available_cards, task

VERSION = "software-path-recovery-v0.31-r2"
SOURCE = Path(__file__).resolve().parents[1]
CANDIDATE = "swe-next-14b"
GPU_ORDER = [4, 6, 5, 0, 1, 2, 3, 7]
LIMITS = copy.deepcopy(previous.LIMITS)
REPORT_PATHS = ["docs/experiments/software-path-recovery-v031r2.md",
                "docs/experiments/software-path-recovery-v031r2.json"]
UNCHANGED = ("data_root", "candidates", "inventories", "candidate_profiles", "selection_rule",
             "purpose", "mode", "interface_revision", "owner_recipe", "prior_model_plan", "checkpoint_marker",
             "source_metadata", "download_manifests", "runtime_dependency_path", "limits")
PATH_LIMITS = {"fresh_native_calls_max": 4, "fresh_native_calls_without_read_correction": 3,
               "read_feedback_corrections_max": 1, "new_optimizer_steps": 0,
               "repeat_near_16k_stress": False, "screening_episodes_max": 12}


def _checked(ref):
    path = Path(ref["path"])
    if digest(path.read_bytes()) != ref["sha256"] or ("bytes" in ref and path.stat().st_size != ref["bytes"]):
        raise ValueError("Frozen inherited artifact changed: " + str(path))
    return path


def implementation_files():
    names = set(previous.implementation_files()) | {
        "scripts/software_path_recovery_v031r2.py", "scripts/continue_model_selection_v031.py",
        "src/proworksim/native_path_admission_v031r2.py"}
    return {name: digest((SOURCE / name).read_bytes()) for name in sorted(names)}


def unchanged_source(prior_plan):
    """Preserve all old Python modules and the exact public software assets."""
    old_root = Path(prior_plan["source_root"])
    names = {str(path.relative_to(old_root)) for prefix in ("src", "scripts")
             for path in (old_root / prefix).rglob("*.py")}
    for prefix in ("examples/software-sources-v030", "examples/software-v15/upstream"):
        names.update(str(path.relative_to(old_root)) for path in (old_root / prefix).rglob("*") if path.is_file())
    hashes = {}
    for name in sorted(names):
        old, current = old_root / name, SOURCE / name
        if not current.is_file() or old.read_bytes() != current.read_bytes():
            raise ValueError("The original native runtime, world, SDK or public assets changed: " + name)
        hashes[name] = digest(current.read_bytes())
    return {"prior_source_root": str(old_root), "prior_source": prior_plan["source"],
            "protected_files_sha256": hashes, "scope": "Only the separate path-admission and one-candidate controller are new"}


def prior_snapshot(prior_run_root):
    """Freeze SWE only; the other v031 worker may continue writing its ledger."""
    root = Path(prior_run_root).resolve()
    actual = root / CANDIDATE / "actual"
    plan, state = read_json(root / "plan.json"), read_json(root / CANDIDATE / "state.json")
    worker, qualification = read_json(actual / "report.json"), read_json(actual / "qualification/report.json")
    common = read_json(actual / "common-state/checkpoint.json")
    owner = read_json(actual / "resident/owner.json")
    if (plan.get("version") != previous.VERSION or plan.get("inventories") != {
            candidate: original.inventory() for candidate in original.CANDIDATES}
            or plan.get("candidate_profiles", {}).get(CANDIDATE) != previous.backend_profile(CANDIDATE)
            or state.get("candidate_id") != CANDIDATE or state.get("status") != "qualification_failed"
            or not state.get("ended_at") or state.get("exit_code") != 0 or state.get("stop_reason") is not None
            or worker.get("candidate_id") != CANDIDATE or worker.get("status") != "qualification_failed"
            or worker.get("rows") != [] or list(actual.glob("screen-*"))
            or worker.get("screening_optimizer_steps") != 0
            or worker.get("source_before") != plan["source"] or worker.get("source_after") != plan["source"]
            or worker.get("qualification") != qualification
            or read_json(actual / "qualification-result.json") != qualification):
        raise ValueError("Only the closed SWE path-failed v031 attempt with zero screening may be reopened once")
    calls, update = qualification.get("calls", []), qualification.get("update") or {}
    if (qualification.get("inference_ready") is not False or qualification.get("training_ready") is not False
            or qualification.get("errors") != [] or qualification.get("native_calls_executed") != 4
            or any(qualification.get(key) is not True for key in (
                "training_integration_ready", "near_16k_capacity_demonstrated", "common_restored_exactly",
                "updated_identity_return_passed", "diagnostic_gradients_cleared"))
            or len(calls) != 4 or any(call.get("actual_trace_complete") is not True for call in calls)
            or calls[0].get("interface_passed") is not False
            or calls[0].get("interface_error", {}).get("message") != "The first public operation must read the declared actual note"
            or any(calls[index].get("interface_passed") is not True for index in (1, 2))
            or update.get("status") != "one_aggregate_diagnostic_update_completed"
            or update.get("actor_optimizer_steps") != 1 or update.get("critic_optimizer_steps") != 1
            or update.get("backward_decisions_completed") != 4
            or any(len(update.get(key, [])) != 4 or any(row.get("passed") is not True for row in update[key])
                   for key in ("behavior_probability_checks", "gradient_probability_checks"))
            or (common.get("actor_steps"), common.get("critic_steps")) != (0, 0)
            or common.get("actor_identity") != worker.get("common_actor_identity")
            or qualification.get("common_before", {}).get("state_tensor_digest") != common.get("state_tensor_digest")
            or qualification.get("common_after", {}).get("state_tensor_digest") != common.get("state_tensor_digest")
            or (worker.get("actor_steps"), worker.get("critic_steps")) != (0, 0)):
        raise ValueError("The sole repaired gate must be the first public path; all inherited numerical/capacity/common controls must have passed")
    first = read_json(actual / "qualification/native-call-1/response.json")
    message = first.get("body", {}).get("choices", [{}])[0].get("message", {})
    tools = message.get("tool_calls", [])
    if (len(tools) != 1 or tools[0].get("function", {}).get("name") != "read_public_note"
            or json.loads(tools[0]["function"]["arguments"]) != {"path": "/public-note.json"}):
        raise ValueError("Recovery must bind the actual original absolute-path output without rewriting it")
    references = {"plan": reference(root / "plan.json"), "worker_state": reference(root / CANDIDATE / "state.json"),
        "worker_report": reference(actual / "report.json"), "qualification": reference(actual / "qualification/report.json"),
        "qualification_result": reference(actual / "qualification-result.json"),
        "owner": reference(actual / "resident/owner.json"), "common": reference(actual / "common-state/checkpoint.json"),
        "common_state": copy.deepcopy(common["state"]), "base_manifest": copy.deepcopy(owner["base_identity"]["manifest"]),
        "aggregate_update": reference(actual / "qualification/aggregate-update.json"),
        "updated_checkpoint": reference(actual / "qualification/updated-checkpoint/checkpoint.json"),
        "updated_state": copy.deepcopy(qualification["checkpoint_roundtrip"]["checkpoint"]["state"]),
        "updated_return": reference(actual / "qualification/updated-return-probe/updated-identity-return.json"),
        "updated_return_guard": reference(actual / "qualification/updated-return-probe/evaluation-guard.json")}
    if (read_json(_checked(references["aggregate_update"])) != update
            or read_json(_checked(references["updated_checkpoint"])) != qualification["checkpoint_roundtrip"]["checkpoint"]
            or read_json(_checked(references["updated_return"])) != qualification["return_probe"]
            or any(qualification.get("checkpoint_roundtrip", {}).get(key) is not True for key in (
                "common_reload_exact", "updated_reload_exact", "updated_identity_changed", "updated_optimizer_states_changed"))):
        raise ValueError("The inherited update/reload/SDK return evidence must bind the actual archived records")
    for index in range(1, 5):
        for kind in ("request", "response"):
            references[f"native_call_{index}_{kind}"] = reference(actual / "qualification" / f"native-call-{index}" / (kind + ".json"))
        if calls[index - 1].get("response_path") != references[f"native_call_{index}_response"]["path"]:
            raise ValueError("Inherited probability controls must bind their own archived response paths")
    for ref in references.values():
        _checked(ref)
    seconds = previous._seconds(state.get("elapsed_gpu_seconds"), "all prior SWE attempts")
    parts = state.get("cost_components")
    if not isinstance(parts, dict) or abs(sum(previous._seconds(value, key) for key, value in parts.items()) - seconds) > 1e-6:
        raise ValueError("Preserve every previous SWE cost component exactly once")
    return {"run_root": str(root), "actual_directory": str(actual), "references": references,
            "source": plan["source"], "state": state, "historical_gpu_seconds": seconds,
            "historical_cost_components": copy.deepcopy(parts), "common_actor_identity": common["actor_identity"],
            "common_state_tensor_digest": common["state_tensor_digest"],
            "original_path_failure": {"path": "/public-note.json", "interface_passed": False,
                                      "response": references["native_call_1_response"]}}


def make_plan(data_root, cpu_qualification, prior_run_root, reservation_directory=None):
    prior = prior_snapshot(prior_run_root)
    old = read_json(_checked(prior["references"]["plan"]))
    if str(Path(data_root).resolve()) != old["data_root"]:
        raise ValueError("Use the same completed model files and historical data root")
    roots = previous._artifact_roots([*old["prior"]["prior_artifact_roots"], prior["run_root"]])
    return {**{key: copy.deepcopy(old[key]) for key in UNCHANGED},
        "version": VERSION, "created_at": time.time(), "source": code_identity(), "source_root": str(SOURCE),
        "implementation_files_sha256": implementation_files(), "qualification": reference(cpu_qualification),
        "prior": prior, "unchanged_source": unchanged_source(old), "artifact_roots": roots,
        "gpu_preference": GPU_ORDER, "execution_candidates": [CANDIDATE], "max_new_model_instances": 1,
        "new_screening_episodes_max": 12, "path_admission_limits": copy.deepcopy(PATH_LIMITS),
        "automatic_retries": False, "automatic_model_replacement": False, "automatic_successors": [],
        "final_model_selection": False, "allocation_experiment_started": False,
        "total_gpu_seconds": None, "worker_gpu_seconds": None, "queue_deadline_at": None, "wall_deadline_at": None,
        "reservation_directory": str(Path(reservation_directory).resolve()) if reservation_directory else None,
        "authorization": "User requested repair of SWE public-path admission, continuation, and reservation of free GPU4.",
        "statistics_scope": "One independent SWE path-admission repair with inherited positive v031 controls and its unchanged twelve development slots. Other candidates remain read-only references.",
        "cost_rule": "Every prior SWE component once plus the entire new assigned-worker duration; no final three-model ranking in this run"}


def validate_plan(plan, *, check_files=True):
    if (plan.get("version") != VERSION or plan.get("execution_candidates") != [CANDIDATE]
            or plan.get("candidates") != list(original.CANDIDATES)
            or plan.get("inventories") != {candidate: original.inventory() for candidate in original.CANDIDATES}
            or plan.get("candidate_profiles") != {candidate: previous.backend_profile(candidate) for candidate in previous.EXECUTED}
            or plan.get("selection_rule") != original.SELECTION_RULE or plan.get("limits") != LIMITS
            or plan.get("gpu_preference") != GPU_ORDER or plan.get("max_new_model_instances") != 1
            or plan.get("new_screening_episodes_max") != 12 or plan.get("path_admission_limits") != PATH_LIMITS
            or plan.get("automatic_retries") is not False or plan.get("automatic_model_replacement") is not False
            or plan.get("automatic_successors") != [] or plan.get("final_model_selection") is not False
            or plan.get("allocation_experiment_started") is not False
            or any(plan.get(key) is not None for key in ("total_gpu_seconds", "worker_gpu_seconds", "queue_deadline_at", "wall_deadline_at"))):
        raise ValueError("Only the one fixed SWE path repair and unchanged twelve-slot screening are authorized")
    if check_files:
        if (plan.get("source") != code_identity() or plan["source"].get("code_dirty") is not False
                or plan.get("source_root") != str(SOURCE) or plan.get("implementation_files_sha256") != implementation_files()):
            raise ValueError("Use the exact clean CPU-qualified source snapshot")
        cpu = read_json(checked(plan["qualification"]))
        if cpu.get("passed") is not True or cpu.get("model_calls") != 0 or cpu.get("source") != plan["source"]:
            raise ValueError("Same-source passing CPU qualification is required")
        if prior_snapshot(plan["prior"]["run_root"]) != plan["prior"]:
            raise ValueError("The original closed SWE attempt changed")
        old = read_json(_checked(plan["prior"]["references"]["plan"]))
        if any(plan.get(key) != old.get(key) for key in UNCHANGED) or unchanged_source(old) != plan["unchanged_source"]:
            raise ValueError("The old runtime, learning recipe, public world, seeds or ranking changed")
        expected_roots = previous._artifact_roots([*old["prior"]["prior_artifact_roots"], plan["prior"]["run_root"]])
        if plan.get("artifact_roots") != expected_roots:
            raise ValueError("Count all original, recovery, numerical-probe and live v031 artifacts")
        if original.download_state(plan, CANDIDATE).get("status") != "ready":
            raise ValueError("The same fixed SWE model download must already be complete")
    return plan


def artifact_usage(plan, root):
    return sum(artifact_bytes(Path(path)) for path in previous._artifact_roots([*plan["artifact_roots"], root]))


def run_worker(plan_path, output):
    from proworksim.native_path_admission_v031r2 import qualify_path
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
              "plan": reference(plan_path), "prior_attempt": plan["prior"], "path_repair_only": True,
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
                raise ValueError("Undeclared path-admission stage")
            task(output, label, kind)

        qualification = qualify_path(owner, output / "qualification", common_dir=common_dir,
                                     prior_qualification=refs["qualification"], on_stage=stage)
        report["qualification"] = qualification
        write(output / "qualification-result.json", qualification)
        if (tensor_tree_digest(owner._state_bundle(), owner.torch) != common["state_tensor_digest"]
                or owner.freeze_identity() != common["actor_identity"] or (owner.actor_steps, owner.critic_steps) != (0, 0)):
            raise ValueError("Path admission did not restore the exact original common learner")
        if not all(qualification.get(key) is True for key in ("inference_ready", "training_ready", "common_restored_exactly")):
            report["status"] = "qualification_failed"
            return report
        if (qualification.get("new_optimizer_steps") != 0 or qualification.get("optimizer_steps") != 0
                or qualification.get("native_calls_executed") not in (3, 4)
                or qualification.get("native_calls_executed") != len(qualification.get("calls", []))
                or qualification.get("correction_calls_executed") not in (0, 1)
                or qualification["native_calls_executed"] != 3 + qualification["correction_calls_executed"]
                or qualification.get("near_16k_stress_rerun") is not False):
            raise ValueError("The path-only repair permits three calls plus at most one correction, zero new optimizer steps and no repeated stress")
        report["status"] = "screening"
        write(output / "report.json", report)
        for row in plan["inventories"][CANDIDATE]:
            if owner.freeze_identity() != common["actor_identity"] or (owner.actor_steps, owner.critic_steps) != (0, 0):
                raise ValueError("Frozen screening cannot change the restored identity or optimizer counters")
            folder = output / row["slot_id"]
            entries = original.collect(owner, original.window_spec("v031r2-" + CANDIDATE + "-" + row["slot_id"], [row]), folder, output)
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
             "cost_components": {**copy.deepcopy(plan["prior"]["historical_cost_components"]), "v031r2_worker_gpu_seconds": 0.0},
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
        state["cost_components"]["v031r2_worker_gpu_seconds"] = max(0, ended - state["started_at"]) if state.get("started_at") else 0.0
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
                        argv = [sys.executable, "-m", "scripts.software_path_recovery_v031r2", "worker",
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
    old_root = Path(plan["prior"]["run_root"])
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
        "final_model_selection": None, "selected_candidate": None, "allocation_experiment_started": False,
        "selection_scope": "No final three-model chooser runs in this independent path recovery, even if another candidate becomes terminal",
        "scope": plan["statistics_scope"], "cost_rule": plan["cost_rule"]}
    output.mkdir(parents=True, exist_ok=True)
    write(output / "software-path-recovery-v031r2.json", value)
    lines = ["# SWE v0.31-r2 公开路径准入修复与独立筛选", "",
        f"状态：`{supervisor['status']}`；源码：`{plan['source']['code_commit']}`；原始目录：`{root}`。", "",
        "仅针对原 SWE 首次输出 `/public-note.json` 未满足已声明相对路径的准入失败。旧调用、旧资格失败及其全部成本保留不变。新准入公开唯一相对路径，首次真实读取失败时最多一次真实错误反馈纠正；最多4次新原生调用，不执行新的 optimizer step。", "",
        "原同一 common actor 的近16K完整概率／反向、1次诊断更新、保存重载及新身份SDK回流已有正证据。本次先恢复完全相同的actor／critic／optimizer／RNG common再继承这些证据，不重复长stress，也不声称它们是本次重新测量。新调用仍逐条保留完整轨迹并通过原概率门和完整反向。", "",
        f"新推理准入：`{qualification.get('inference_ready')}`；训练准入：`{qualification.get('training_ready')}`；完整common恢复：`{qualification.get('common_restored_exactly')}`。", "",
        "通过路径准入后才执行原六开发合同×两seed的完整12槽一次；SDK、原生协议、模型profile、数值门、世界、role预算、分类门和排名定义不变。未启动／未闭合不补0分。", "",
        "| 案例／seed | 状态 | 完整交付 | R |", "|---|---|---|---:|"]
    rows = {row["slot_id"]: row for row in worker.get("rows", [])}
    for slot in plan["inventories"][CANDIDATE]:
        row = rows.get(slot["slot_id"], {})
        lines.append(f"| {slot['case_id']} / {slot['sampling_seed']} | {row.get('status', 'not_started_or_not_closed')} | {row.get('complete_work')} | {row.get('R')} |")
    lines += ["", "| 类别 | 完整成功／已知 |", "|---|---:|"]
    for category, counts in result["categories"].items():
        lines.append(f"| {category} | {counts['successful_complete_deliveries']}/{counts['known']} |")
    lines += ["", f"SWE本次是否满足原候选可选门：`{result['selection_eligible']}`；这不等于三模型最终选中。", "",
              "本运行不重启9B或Devstral，不控制其进程，不覆盖原v031报告；其他候选仅记录读取时状态。此独立运行不执行最终三模型选择或后续B/G-raw/I-P实验。", "",
              "| 成本阶段 | GPU秒 |", "|---|---:|"]
    for key, seconds in supervisor["states"][CANDIDATE]["cost_components"].items():
        lines.append(f"| {key} | {seconds:.6f} |")
    lines += ["", "GPU成本为分配单张GPU后的完整worker墙钟，包括导入、加载、补验、筛选、清理及失败；预约和排队另存记录，不重复加旧累计成本。资源限制仍为每worker64GiB RSS、全部旧新产物合计128GiB及卷预留20GiB，无累计GPU／队列／总墙钟截止。", "",
              "以上是已见开发材料上的运行准入与筛选证据，不是参数训练收益或分配算法收益。机器可读报告保留全部原件引用、继承范围、补验细节和失败原因。", ""]
    (output / "software-path-recovery-v031r2.md").write_text("\n".join(lines))
    return value


def finish(plan_path, run_root, report_repo, *, publish=False):
    plan_path, run_root, report_repo = (Path(path).resolve() for path in (plan_path, run_root, report_repo))
    if run_root.exists():
        raise FileExistsError("A new independent path-recovery directory is required")
    state_path = run_root.parent / (run_root.name + "-finish.json")
    state = {"version": VERSION, "status": "supervising", "started_at": time.time(), "run_root": str(run_root)}
    write(state_path, state)
    process = subprocess.run([sys.executable, "-m", "scripts.software_path_recovery_v031r2", "supervise",
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
                subprocess.run(["git", "commit", "--only", "-m", "docs: archive SWE path admission recovery v031r2", "--", *REPORT_PATHS],
                               cwd=report_repo, check=True)
            elif changed != 0:
                raise RuntimeError("Cannot determine the fixed v031r2 report change set")
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
        raise KeyboardInterrupt("Path recovery received signal " + str(signum))
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
