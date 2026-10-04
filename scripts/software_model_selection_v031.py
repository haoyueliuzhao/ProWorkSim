"""New v031 runtime-combination batch; retain the unchanged 9B reference only.

Only two new candidates execute, once each. The public world, six development
contracts, two seeds, role budgets and ranking are inherited unchanged. Original
v030 loading failures and r1 technical failures remain separate source records.
An actual old-trace GPU numerical proof is required before any new native call.
"""
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
from proworksim.storage import digest, json_bytes, read_json
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from scripts import software_model_selection_v030 as original
from scripts.recover_software_model_selection_v030 import cancel_reservation, consume_reservation
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import checked, lock, read, reference, resources, stop_owned, write
from scripts.software_development_v028 import available_cards, task

VERSION = "software-model-selection-v0.31"
SOURCE = Path(__file__).resolve().parents[1]
RETAINED = original.CANDIDATES[0]
EXECUTED = original.CANDIDATES[1:]
GPU_ORDER = [4, 6, 5, 0, 1, 2, 3, 7]
LIMITS = copy.deepcopy(original.LIMITS)
REPORT_PATHS = ["docs/experiments/software-model-selection-v031.md",
                "docs/experiments/software-model-selection-v031.json"]
NUMERIC_PROOF_FILES = frozenset({
    "src/proworksim/candidate_runtime_v031.py", "src/proworksim/functional_dense_v031.py",
    "src/proworksim/native_codecs_v031.py",
})


def backend_profile(candidate):
    from proworksim.candidate_runtime_v031 import candidate_profile
    return candidate_profile(candidate)


def load_owner(model_path, *, manifest, profile, output, recipe):
    from proworksim.candidate_runtime_v031 import CandidateActor
    return CandidateActor.from_candidate(model_path, manifest=manifest, profile=profile,
                                          output=output, recipe=recipe)


def implementation_files():
    names = set(original._implementation_reference()) | {
        "scripts/software_model_selection_v031.py", "scripts/recover_software_model_selection_v030.py"}
    return {name: digest((SOURCE / name).read_bytes()) for name in sorted(names)}


def _seconds(value, field):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Actual finite nonnegative GPU cost required: " + field)
    return float(value)


def _artifact_roots(roots):
    """Count each resolved directory once, including any nested run only once."""
    result = []
    for root in sorted({Path(value).resolve() for value in roots}, key=lambda value: (len(value.parts), str(value))):
        if not any(root.is_relative_to(parent) for parent in result):
            result.append(root)
    return [str(root) for root in result]


def bind_artifact_inventory(prior, probes, data_root):
    """Bind the whole numerical ledger, including its controller records."""
    numeric = _artifact_roots(proof["probe_ledger_directory"] for proof in probes.values())
    models = (Path(data_root) / "runs/assets/models").resolve()
    for name in numeric:
        root = Path(name)
        if root.is_relative_to(models) or models.is_relative_to(root):
            raise ValueError("Numerical artifact roots must not include or reside in model assets")
    roots = _artifact_roots([prior["original_root"], prior["recovery_root"], *numeric])
    return {**copy.deepcopy(prior),
            "historical_run_artifact_bytes": prior["prior_artifact_bytes"],
            "numeric_probe_artifact_roots": numeric, "prior_artifact_roots": roots,
            "prior_artifact_bytes": sum(artifact_bytes(Path(root)) for root in roots),
            "artifact_accounting": "Declaration size includes old runs and complete probe ledgers; runtime remeasures their union with the new run without nested duplication"}


def artifact_usage(plan, run_root):
    roots = _artifact_roots([*plan["prior"]["prior_artifact_roots"], run_root])
    return sum(artifact_bytes(Path(root)) for root in roots)


def prior_snapshot(original_root, recovery_root):
    old, recovered = Path(original_root).resolve(), Path(recovery_root).resolve()
    plan = read_json(old / "plan.json")
    recovery_plan = read_json(recovered / "plan.json")
    states = read_json(old / "supervisor.json")
    recovery_states = read_json(recovered / "supervisor.json")
    if (plan.get("version") != original.VERSION or plan.get("candidates") != list(original.CANDIDATES)
            or plan.get("inventories") != {name: original.inventory() for name in original.CANDIDATES}
            or recovery_plan.get("inventories") != plan["inventories"]
            or any(not snapshot.get("ended_at") or snapshot.get("running_gpu_seconds") != 0
                   for snapshot in (states, recovery_states))):
        raise ValueError("Use the closed original v030 and r1 inventories without changing any seed")
    workers = {}
    for candidate in original.CANDIDATES:
        old_report_path, new_report_path = (directory / candidate / "actual/report.json"
                                            for directory in (old, recovered))
        before, recovery = read_json(old_report_path), read_json(new_report_path)
        initial_state, recovery_state = states["states"][candidate], recovery_states["states"][candidate]
        if any(state.get("status") not in original.TERMINAL for state in (initial_state, recovery_state)):
            raise ValueError("Every previous model attempt must be terminal")
        if candidate == RETAINED:
            result = original.candidate_result(plan, candidate, before, initial_state)
            if (initial_state["status"] != "complete" or before.get("status") != "complete"
                    or not result["all_12_known"] or not result["qualification_complete"]
                    or before != recovery or before.get("screening_optimizer_steps") != 0):
                raise ValueError("Retain exactly the unchanged complete 9B twelve-slot comparison")
            for row in before["rows"]:
                for field in ("entry", "assessment", "evaluation_guard"):
                    checked(row[field])
            historical_cost = _seconds(initial_state.get("elapsed_gpu_seconds"), "9B original worker")
            detail = {"original_worker_gpu_seconds": historical_cost, "r1_worker_gpu_seconds": 0.0}
        else:
            if (before.get("rows") != [] or recovery.get("rows") != []
                    or any(list((directory / candidate / "actual").glob("screen-*"))
                           for directory in (old, recovered))):
                raise ValueError("The two changed combinations must have no prior formal screening episode")
            initial_cost = _seconds(initial_state.get("elapsed_gpu_seconds"), "original loading attempt")
            repeat_cost = _seconds(recovery_state.get("recovery_worker_gpu_seconds"), "r1 technical attempt")
            historical_cost = initial_cost + repeat_cost
            if not math.isclose(historical_cost, _seconds(recovery_state.get("elapsed_gpu_seconds"), "r1 cumulative"),
                                rel_tol=0, abs_tol=1e-6):
                raise ValueError("Previous recovery cost must include the initial failure exactly once")
            detail = {"original_worker_gpu_seconds": initial_cost, "r1_worker_gpu_seconds": repeat_cost}
        workers[candidate] = {
            "original_report": reference(old_report_path), "recovery_report": reference(new_report_path),
            "original_state": copy.deepcopy(initial_state), "recovery_state": copy.deepcopy(recovery_state),
            "original_actual_directory": str(old / candidate / "actual"),
            "recovery_actual_directory": str(recovered / candidate / "actual"),
            "original_source": before.get("source_before"), "recovery_source": recovery.get("source_before"),
            "historical_gpu_seconds": historical_cost, "historical_cost_components": detail,
        }
    return {"original_root": str(old), "recovery_root": str(recovered),
            "original_plan": reference(old / "plan.json"), "recovery_plan": reference(recovered / "plan.json"),
            "original_supervisor": reference(old / "supervisor.json"),
            "recovery_supervisor": reference(recovered / "supervisor.json"), "workers": workers,
            "prior_artifact_bytes": artifact_bytes(old) + artifact_bytes(recovered)}


def comparison_proof(prior):
    """Byte-preserve the public task/SDK and every historical 9B source module.

    The dense v030 loader is the only old module excluded: its earlier change was
    the documented JSON evidence repair and it is not the retained 9B backend.
    All other old source files, original assets and shared scripts stay exact.
    """
    old_plan = read_json(checked(prior["original_plan"]))
    old_root = Path(old_plan["source_root"])
    names = {str(path.relative_to(old_root)) for path in (old_root / "src").rglob("*.py")}
    names.discard("src/proworksim/candidate_runtime_v030.py")
    for prefix in ("examples/software-sources-v030", "examples/software-v15/upstream"):
        names.update(str(path.relative_to(old_root)) for path in (old_root / prefix).rglob("*") if path.is_file())
    names.update(original._implementation_reference())
    result = {}
    for name in sorted(names):
        old, current = old_root / name, SOURCE / name
        if not current.is_file() or current.read_bytes() != old.read_bytes():
            raise ValueError("Retained 9B comparison world, source asset, SDK or old path changed: " + name)
        result[name] = digest(current.read_bytes())
    return {"old_source_root": str(old_root), "old_source": old_plan["source"],
            "protected_files_sha256": result, "protected_file_count": len(result),
            "scope": "Old 9B/public world unchanged; new dense native and numerical modules are separate combinations"}


def validate_numeric_proof(path, candidate, profile):
    """Bind a terminal GPU proof; only a passing one authorizes new sampling."""
    report_path = Path(path)
    value = read_json(report_path)
    profile_sha256 = digest(json_bytes(profile))
    passed = value.get("passed")
    if (value.get("candidate_id") != candidate or type(passed) is not bool
            or value.get("status") != ("passed" if passed else "failed")
            or value.get("profile_sha256") != profile_sha256
            or value.get("new_model_calls") != 0 or value.get("optimizer_steps") != 0
            or not isinstance(value.get("source"), dict)
            or not value.get("ended_at")
            or passed and any(value.get(key) is not True for key in (
                "all_full_tokens_retained", "all_behavior_and_gradient_probability_passed",
                "full_backward_completed", "original_actor_identity_matched", "common_restored_exactly"))):
        raise ValueError("New formal sampling requires the bound GPU old-trace probability/full-backward proof")
    traces = value.get("original_trace_refs")
    if not isinstance(traces, list) or len(traces) != 1:
        raise ValueError("The GPU numerical proof uses exactly the original failing complete trace")
    for trace in traces:
        checked(trace)
    fingerprints = value.get("tested_files_sha256")
    if not isinstance(fingerprints, dict) or not NUMERIC_PROOF_FILES <= fingerprints.keys():
        raise ValueError("The actual GPU proof must bind its tested implementation files")
    for name, expected in fingerprints.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or digest((SOURCE / name).read_bytes()) != expected:
            raise ValueError("Numerical proof implementation changed: " + name)
    seconds = _seconds(value.get("actual_worker_gpu_seconds"), "old-trace GPU proof")
    directories = {}
    for field, expected in (("artifact_directory", report_path.resolve().parent),
                            ("probe_ledger_directory", report_path.resolve().parent.parent)):
        directory = value.get(field)
        if not isinstance(directory, str) or Path(directory).resolve() != expected:
            raise ValueError("GPU proof artifact directory must bind its actual admission location: " + field)
        directories[field] = str(expected)
    return {"report": reference(report_path), "candidate_id": candidate, "passed": passed,
            "status": value["status"], "elapsed_gpu_seconds": seconds,
            "profile_sha256": profile_sha256, "original_trace_refs": copy.deepcopy(traces),
            "tested_files_sha256": copy.deepcopy(fingerprints), "source": value.get("source"), **directories}


def _trace_binding(prior, candidate, proof):
    number = 1 if candidate == EXECUTED[0] else 3
    expected = Path(prior["workers"][candidate]["recovery_actual_directory"]) / "qualification" / f"native-call-{number}" / "response.json"
    if proof["original_trace_refs"] != [reference(expected)]:
        raise ValueError("The GPU proof must use that candidate's archived original failing trace")


def make_plan(data_root, qualification, prior_original_root, prior_recovery_root,
              numeric_probe_reports, reservation_dir=None):
    inherited = original.make_plan(data_root, qualification)
    prior = prior_snapshot(prior_original_root, prior_recovery_root)
    profiles = {candidate: backend_profile(candidate) for candidate in EXECUTED}
    if set(numeric_probe_reports) != set(EXECUTED):
        raise ValueError("Exactly the two fixed dense candidates need GPU numerical proofs")
    probes = {candidate: validate_numeric_proof(Path(numeric_probe_reports[candidate]), candidate, profiles[candidate])
              for candidate in EXECUTED}
    for candidate in EXECUTED:
        _trace_binding(prior, candidate, probes[candidate])
    prior = bind_artifact_inventory(prior, probes, data_root)
    return {**inherited, "version": VERSION, "candidate_profiles": profiles, "source": code_identity(),
            "implementation_files_sha256": implementation_files(), "gpu_preference": GPU_ORDER,
            "prior": prior, "retained_candidates": [RETAINED], "execution_candidates": list(EXECUTED),
            "retained_comparison": comparison_proof(prior), "numeric_probes": probes,
            "max_new_model_instances": 2, "new_screening_episodes_max": 24,
            "cumulative_screening_episodes_max": 36, "automatic_additional_recovery": False,
            "authorization": "User requested fixes and subsequent experiments; only the two previously unscreened dense runtime combinations change.",
            "reservation_directory": str(Path(reservation_dir).resolve()) if reservation_dir else None,
            "statistics_scope": "New v031 native/numerical combinations with unchanged old-source 9B reference. Neither v030 reranking nor a logging-only recovery.",
            "cost_rule": "original attempt + r1 attempt + declared GPU numerical proof + v031 assigned-worker duration; no duplicate old cost"}


def validate_plan(plan, *, check_files=True):
    if (plan.get("version") != VERSION or plan.get("candidates") != list(original.CANDIDATES)
            or plan.get("inventories") != {candidate: original.inventory() for candidate in original.CANDIDATES}
            or plan.get("retained_candidates") != [RETAINED] or plan.get("execution_candidates") != list(EXECUTED)
            or plan.get("candidate_profiles") != {candidate: backend_profile(candidate) for candidate in EXECUTED}
            or plan.get("gpu_preference") != GPU_ORDER or plan.get("limits") != LIMITS
            or plan.get("selection_rule") != original.SELECTION_RULE
            or plan.get("purpose") != original.PURPOSE or plan.get("mode") != original.MODE
            or plan.get("interface_revision") != original.INTERFACE_REVISION
            or plan.get("max_new_model_instances") != 2 or plan.get("new_screening_episodes_max") != 24
            or plan.get("cumulative_screening_episodes_max") != 36 or plan.get("max_screening_episodes") != 36
            or plan.get("screening_episodes_per_candidate") != 12
            or plan.get("automatic_retries") is not False or plan.get("automatic_model_replacement") is not False
            or plan.get("automatic_additional_recovery") is not False or plan.get("automatic_successors") != []
            or plan.get("shared_gpu_capacity_allowed") is not False
            or plan.get("model_api_calls") != 0
            or plan.get("stop_after") != "fixed_model_interface_screening_and_selection"
            or plan.get("qualification_limits") != {"native_calls_per_candidate": 4, "updated_identity_fragments_per_candidate": 1,
                "calls_per_updated_identity_fragment": 1, "diagnostic_updates_per_candidate": 1, "development_cases_used_for_update": False}
            or any(plan.get(key) is not None for key in ("total_gpu_seconds", "worker_gpu_seconds", "queue_deadline_at", "wall_deadline_at"))):
        raise ValueError("The v031 batch must preserve world, two seeds, quotas, thresholds and the two new combinations")
    if set(plan.get("numeric_probes", {})) != set(EXECUTED):
        raise ValueError("Both numerical GPU proofs must be fixed before formal reopening")
    for candidate in original.CANDIDATES:
        original._validate_window(original.window_spec("validate-v031-" + candidate, plan["inventories"][candidate]))
    if check_files:
        if (plan.get("source") != code_identity() or plan["source"].get("code_dirty") is not False
                or plan.get("source_root") != str(SOURCE)
                or plan.get("implementation_files_sha256") != implementation_files()):
            raise ValueError("Run only the clean frozen v031 implementation")
        observed_prior = bind_artifact_inventory(
            prior_snapshot(plan["prior"]["original_root"], plan["prior"]["recovery_root"]),
            plan["numeric_probes"], plan["data_root"])
        # The numerical driver may still append controller/continuation records.
        # Bind its directories and original receipts, not an immutable byte size;
        # the unchanged budget uses live measurements of the complete union.
        if ({key: value for key, value in observed_prior.items() if key != "prior_artifact_bytes"}
                != {key: value for key, value in plan["prior"].items() if key != "prior_artifact_bytes"}
                or type(plan["prior"].get("prior_artifact_bytes")) is not int
                or plan["prior"]["prior_artifact_bytes"] < 0):
            raise ValueError("Archived v030/r1 outcomes or costs changed after the v031 declaration")
        if comparison_proof(plan["prior"]) != plan["retained_comparison"]:
            raise ValueError("The retained 9B/public-world comparison changed")
        cpu = read_json(checked(plan["qualification"]))
        if cpu.get("passed") is not True or cpu.get("source") != plan["source"] or cpu.get("model_calls") != 0:
            raise ValueError("Same-source CPU admission is required before the new batch")
        for candidate in EXECUTED:
            proof = plan["numeric_probes"][candidate]
            if validate_numeric_proof(checked(proof["report"]), candidate, plan["candidate_profiles"][candidate]) != proof:
                raise ValueError("Frozen GPU numerical proof changed")
            _trace_binding(plan["prior"], candidate, proof)
            if original.download_state(plan, candidate)["status"] != "ready":
                raise ValueError("Both existing fixed downloads must be complete before v031 launch")
        old = read_json(checked(plan["prior"]["original_plan"]))
        for field in ("owner_recipe", "prior_model_plan", "checkpoint_marker", "source_metadata", "download_manifests",
                      "runtime_dependency_path", "selection_rule", "qualification_limits"):
            if plan[field] != old[field]:
                raise ValueError("The frozen old task/model-origin protocol changed: " + field)
    return plan


def run_worker(plan_path, candidate, output):
    from proworksim.model_qualification_v030 import qualify
    from proworksim.online_training import tensor_tree_digest
    from proworksim.software_learning_v029 import migrate_software_owner

    plan = validate_plan(read_json(plan_path))
    if candidate not in EXECUTED or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPU_ORDER)):
        raise ValueError("Only the two new combinations may start a single-GPU v031 owner")
    if plan["numeric_probes"][candidate]["passed"] is not True:
        raise ValueError("Failed numerical preflight cannot create an owner or sample new tokens")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"version": VERSION, "candidate_id": candidate, "status": "loading", "started_at": time.time(),
              "source_before": code_identity(), "rows": [], "screening_optimizer_steps": 0,
              "plan": reference(plan_path), "runtime_combination_only": True, "model_replacement": False,
              "prior_attempts": plan["prior"]["workers"][candidate], "numeric_proof": plan["numeric_probes"][candidate]}
    owner = None
    write(output / "report.json", report)
    try:
        task(output, "load-v031-" + candidate, "loading")
        sample = resources()
        write(output / "preload-resources.json", sample)
        if int(os.environ["CUDA_VISIBLE_DEVICES"]) not in [card["index"] for card in available_cards(plan, sample)]:
            raise RuntimeError("Assigned exclusive GPU capacity changed before loading")
        ready = original.download_state(plan, candidate)
        recipe = read_json(checked(plan["owner_recipe"]))["recipe"]
        write(output / "model-download-manifest.json", read_json(checked(ready["manifest"])))
        owner = load_owner(ready["model_path"], manifest=checked(ready["manifest"]),
                           profile=plan["candidate_profiles"][candidate], output=output / "resident", recipe=recipe)
        if (owner.actor_steps, owner.critic_steps) != (0, 0):
            raise ValueError("New dense combinations start from official weights and fresh project optimizers")
        write(output / "software-critic-migration.json", migrate_software_owner(owner, expected_steps=None))
        task(output, "common-state", "boundary")
        common_dir = output / "common-state"
        common = owner.save_checkpoint(common_dir)
        write(output / "common.json", {**common, "directory": str(common_dir), "recipe": owner.recipe})
        report.update(status="qualifying", initial_actor_steps=0, initial_critic_steps=0,
                      common_actor_identity=owner.freeze_identity())
        write(output / "report.json", report)

        def stage(kind, label):
            if kind not in LIMITS["task_seconds"]:
                raise ValueError("Qualification stage was not declared")
            task(output, label, kind)

        qualification = qualify(owner, output / "qualification", common_dir=common_dir,
            return_probe=lambda actual_owner, folder: original.return_probe(actual_owner, candidate, folder, output),
            on_stage=stage)
        report["qualification"] = qualification
        write(output / "qualification-result.json", qualification)
        if tensor_tree_digest(owner._state_bundle(), owner.torch) != common["state_tensor_digest"]:
            raise ValueError("The technical diagnostic did not restore the full original common state")
        if not (qualification.get("inference_ready") is True and qualification.get("training_ready") is True):
            report["status"] = "qualification_failed"
            return report
        report["status"] = "screening"
        write(output / "report.json", report)
        for row in plan["inventories"][candidate]:
            if owner.freeze_identity() != common["actor_identity"] or (owner.actor_steps, owner.critic_steps) != (0, 0):
                raise ValueError("Frozen screening cannot change model identity or optimizer counters")
            folder = output / row["slot_id"]
            entries = original.collect(owner, original.window_spec("v031-" + candidate + "-" + row["slot_id"], [row]), folder, output)
            report["rows"].append(original._screen_row(row, entries[0], folder))
            write(output / "progress.json", report["rows"])
            write(output / "report.json", report)
        report["status"] = "complete"
    except BaseException as exception:
        report.update(status="interrupted_or_error", error={"type": type(exception).__name__, "message": str(exception)})
        raise
    finally:
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps,
                          final_actor_identity=owner._make_identity())
        report.update(ended_at=time.time(), source_after=code_identity())
        write(output / "report.json", report)
    return report


def select_candidate(plan, states, reports):
    result = original.select_candidate(plan, states, reports)
    result.update(version=VERSION, retained_reference_source=plan["prior"]["workers"][RETAINED]["original_source"],
                  executed_combination_source=plan["source"], statistics_scope=plan["statistics_scope"])
    for candidate, row in result["candidate_results"].items():
        row["cost_scope"] = plan["cost_rule"]
        row["cost_components"] = copy.deepcopy(states[candidate]["cost_components"])
        row["retained_original_reference"] = candidate == RETAINED
    return result


def supervise(plan_path, root):
    plan = validate_plan(read_json(plan_path))
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    (root / RETAINED).symlink_to(Path(plan["prior"]["original_root"]) / RETAINED, target_is_directory=True)
    states = {}
    for candidate in original.CANDIDATES:
        prior = plan["prior"]["workers"][candidate]
        probe_seconds = plan["numeric_probes"][candidate]["elapsed_gpu_seconds"] if candidate in EXECUTED else 0.0
        parts = {**copy.deepcopy(prior["historical_cost_components"]),
                 "v031_old_trace_gpu_proof_seconds": probe_seconds, "v031_worker_gpu_seconds": 0.0}
        numeric_failed = candidate in EXECUTED and not plan["numeric_probes"][candidate]["passed"]
        states[candidate] = {"candidate_id": candidate,
            "status": "complete" if candidate == RETAINED else "qualification_failed" if numeric_failed else "not_started",
            "attempted": False, "retained_original": candidate == RETAINED, "cost_components": parts,
            "historical_gpu_seconds": prior["historical_gpu_seconds"],
            "elapsed_gpu_seconds": prior["historical_gpu_seconds"] + probe_seconds}
        if numeric_failed:
            states[candidate].update(preflight_status="numeric_preflight_failed", native_calls=0,
                                     formal_screening_episodes=0, ended_at=time.time())
            write(root / candidate / "actual/report.json", {
                "version": VERSION, "candidate_id": candidate, "status": "qualification_failed",
                "stage": "numeric_preflight_failed", "controller_closed_without_loading_or_sampling": True,
                "source_before": plan["source"], "source_after": plan["source"],
                "numeric_proof": plan["numeric_probes"][candidate], "rows": [], "screening_optimizer_steps": 0,
                "qualification": {"status": "numeric_preflight_failed", "inference_ready": None,
                    "training_ready": False, "training_integration_ready": None,
                    "native_calls_executed": 0, "scope": "Old-trace numeric repair did not qualify; no new native or formal episode attempted"}})
            write(root / candidate / "state.json", states[candidate])
    summary = {"version": VERSION, "status": "waiting", "source": code_identity(), "started_at": time.time(),
               "observer_pid": os.getpid(), "states": states, "retained_screening_episodes": 12,
               "max_new_screening_episodes": 24, "statistics_scope": plan["statistics_scope"]}
    active, logs, guards, stable = {}, {}, {}, {}
    reservation_done = False
    reservation_plan = {"reservation_directory": plan.get("reservation_directory"), "canonical_plan": plan}

    def publish():
        summary["observed_at"] = time.time()
        summary["worker_gpu_seconds"] = sum(state["elapsed_gpu_seconds"] for state in states.values())
        summary["running_gpu_seconds"] = sum(time.time() - states[candidate]["started_at"] for candidate in active)
        summary["new_completed_worker_gpu_seconds"] = sum(states[candidate]["cost_components"]["v031_worker_gpu_seconds"]
                                                         for candidate in EXECUTED)
        write(root / "supervisor.json", summary)

    def finish(candidate, reason):
        process = active.pop(candidate)
        if process.poll() is None:
            stop_owned(process)
        process.wait(timeout=15)
        worker = read(root / candidate / "actual/report.json") or {}
        okay = process.returncode == 0 and reason is None and worker.get("status") in {"complete", "qualification_failed"}
        state = states[candidate]
        state.update(status=worker["status"] if okay else "stopped", ended_at=time.time(),
                     exit_code=process.returncode, stop_reason=reason)
        state["cost_components"]["v031_worker_gpu_seconds"] = state["ended_at"] - state["started_at"]
        state["elapsed_gpu_seconds"] = sum(state["cost_components"].values())
        logs.pop(candidate).close()
        write(root / candidate / "state.json", state)

    def launch(candidate, card, *, reserved=False):
        if code_identity() != plan["source"] or implementation_files() != plan["implementation_files_sha256"]:
            raise ValueError("Frozen v031 implementation changed while queued")
        if (artifact_usage(plan, root) > LIMITS["artifact_bytes"]
                or shutil.disk_usage(root).free < LIMITS["minimum_volume_free_bytes"]):
            raise RuntimeError("Prior, numeric-probe and new-run artifacts exceed the unchanged storage reserve")
        folder = root / candidate
        folder.mkdir(exist_ok=False)
        argv = [sys.executable, "-m", "scripts.software_model_selection_v031", "worker", "--plan", str(root / "plan.json"),
                "--output", str(folder / "actual"), "--candidate", candidate]
        logs[candidate] = (folder / "worker.log").open("x")
        process = subprocess.Popen(argv, cwd=SOURCE, env=original.worker_env(plan, root, candidate, card["index"]),
            stdin=subprocess.DEVNULL, stdout=logs[candidate], stderr=subprocess.STDOUT, start_new_session=True)
        identity = worker_identity(process.pid)
        states[candidate].update(status="running", attempted=True, gpu=card["index"], gpu_uuid=card["uuid"],
            pid=process.pid, process_identity=identity, started_at=time.time(), command=argv, reservation_handoff=reserved)
        active[candidate] = process
        guards[candidate] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
        write(folder / "state.json", states[candidate])
        publish()

    with lock(root):
        try:
            while True:
                now = time.time()
                for candidate, process in list(active.items()):
                    if process.poll() is not None:
                        finish(candidate, None if process.returncode == 0 else "worker_exit_error")
                if all(states[candidate]["status"] in original.TERMINAL for candidate in EXECUTED):
                    reports = {candidate: read(root / candidate / "actual/report.json") or {} for candidate in original.CANDIDATES}
                    selection = select_candidate(plan, states, reports)
                    write(root / "selection.json", selection)
                    summary.update(status=selection["status"], selected_candidate=selection["selected_candidate"])
                    break
                waiting = [candidate for candidate in EXECUTED if states[candidate]["status"] == "not_started"]
                if waiting and len(active) < 2:
                    if not reservation_done and plan.get("reservation_directory"):
                        card = consume_reservation(reservation_plan, root)
                        reservation_done = (read(root / "reservation-handoff.json") or {}).get("status") == "released"
                        if card is not None:
                            launch(waiting.pop(0), card, reserved=True)
                    if waiting and len(active) < 2:
                        sample = resources()
                        with (root / "waiting-resources.jsonl").open("a") as stream:
                            stream.write(json.dumps(sample) + "\n")
                        cards = available_cards(plan, sample, [states[candidate]["gpu"] for candidate in active])
                        stable = {card["index"]: stable.get(card["index"], now) for card in cards}
                        for card in cards:
                            if not waiting or len(active) >= 2:
                                break
                            if now - stable[card["index"]] >= LIMITS["gpu_capacity_stability_seconds"]:
                                launch(waiting.pop(0), card)
                if not waiting and not reservation_done:
                    cancel_reservation(reservation_plan, root)
                    reservation_done = True
                if active:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = {candidate: pool.submit(target_resources, states[candidate]["gpu"], worker_pid=process.pid)
                                   for candidate, process in active.items()}
                        samples = {candidate: future.result() for candidate, future in futures.items()}
                    size = artifact_usage(plan, root)
                    free = shutil.disk_usage(root).free
                    for candidate, process in list(active.items()):
                        if process.poll() is not None:
                            finish(candidate, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        current = states[candidate]
                        guard = guards[candidate].observe(samples[candidate], time.time(), process.pid, current["gpu"],
                            own_memory_limit_mib=LIMITS["own_gpu_memory_mib"])
                        running_task = read(root / candidate / "actual/task.json") or {"kind": "loading", "started_at": current["started_at"]}
                        own_rss, reason = rss(process.pid), guard.get("stop_reason")
                        cap = LIMITS["task_seconds"].get(running_task.get("kind"))
                        if running_task.get("kind") not in LIMITS["task_seconds"]:
                            reason = "unknown_task_kind"
                        elif cap is not None and time.time() - running_task["started_at"] >= cap:
                            reason = "single_task_budget"
                        elif own_rss > LIMITS["host_rss_per_worker_bytes"]:
                            reason = "host_memory_budget"
                        elif size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                            reason = "trajectory_storage_reserve"
                        with (root / candidate / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": samples[candidate], "guard": guard, "task": running_task,
                                "rss_bytes": own_rss, "artifact_bytes": size}) + "\n")
                        if reason:
                            finish(candidate, reason)
                summary["status"] = "running" if active else "waiting"
                publish()
                time.sleep(LIMITS["poll_seconds"])
        except BaseException as exception:
            summary.update(status="supervisor_interrupted", error={"type": type(exception).__name__, "message": str(exception)})
            for candidate in list(active):
                finish(candidate, "supervisor_interrupted")
            raise
        finally:
            if not reservation_done:
                cancel_reservation(reservation_plan, root)
            summary["ended_at"] = time.time()
            publish()
    return summary


def report(run_root, output_dir):
    """Read v031 outcomes without changing any original worker or prior result."""
    root, output = Path(run_root).resolve(), Path(output_dir).resolve()
    plan, supervisor = read_json(root / "plan.json"), read_json(root / "supervisor.json")
    selection = read(root / "selection.json")
    candidates = {}
    for candidate in original.CANDIDATES:
        actual = root / candidate / "actual"
        worker = read(actual / "report.json") or {}
        qualification = read(actual / "qualification/report.json") or worker.get("qualification") or {}
        rows = worker.get("rows", [])
        progress = read(actual / "progress.json")
        if progress is not None and len(progress) > len(rows):
            rows = progress
        byslot = {row["slot_id"]: row for row in rows}
        outcomes = []
        for slot in plan["inventories"][candidate]:
            row = byslot.get(slot["slot_id"])
            outcomes.append({**copy.deepcopy(slot), "category": original.case_spec(slot["case_id"])["category"],
                "status": row.get("status") if row else "not_started_or_not_closed",
                "R": row.get("R") if row else None, "complete_work": row.get("complete_work") if row else None,
                "record": row, "trajectory_directory": str((actual / slot["slot_id"] / "slot-0").resolve())})
        update = qualification.get("update") or {}
        candidates[candidate] = {
            "state": copy.deepcopy(supervisor["states"][candidate]),
            "source": worker.get("source_before"), "retained_original": candidate == RETAINED,
            "worker_report": reference(actual / "report.json") if (actual / "report.json").exists() else None,
            "qualification_report": reference(actual / "qualification/report.json")
                if (actual / "qualification/report.json").exists() else None,
            "qualification": {key: qualification.get(key) for key in (
                "status", "inference_ready", "training_integration_ready", "training_ready",
                "near_16k_capacity_demonstrated", "capacity_status", "common_restored_exactly",
                "native_calls_executed", "updated_identity_return_passed", "errors")},
            "native_lengths": [{key: call.get(key) for key in (
                "index", "input_tokens", "output_tokens", "total_tokens", "finish_reason",
                "interface_passed", "actual_trace_complete", "interface_error", "trace_error")}
                for call in qualification.get("calls", [])],
            "probability_summary": {group: [{key: check.get(key) for key in (
                "trace_index", "passed", "max_abs_delta", "mean_abs_delta")}
                for check in update.get(group, [])]
                for group in ("behavior_probability_checks", "gradient_probability_checks")},
            "diagnostic_update": {key: update.get(key) for key in (
                "status", "actor_optimizer_steps", "critic_optimizer_steps", "backward_decisions_completed",
                "changed_actor_elements", "changed_critic_elements", "elapsed_seconds", "resources")},
            "screening_optimizer_steps": worker.get("screening_optimizer_steps"),
            "numeric_proof": copy.deepcopy(plan["numeric_probes"].get(candidate)), "outcomes": outcomes,
        }
    value = {"version": VERSION, "generated_at": time.time(), "run_root": str(root),
        "plan": plan, "plan_reference": reference(root / "plan.json"), "supervisor": supervisor,
        "selection": selection, "candidates": candidates, "allocation_experiment_started": False,
        "scope": plan["statistics_scope"], "cost_rule": plan["cost_rule"]}
    output.mkdir(parents=True, exist_ok=True)
    write(output / "software-model-selection-v031.json", value)
    text = ["# v0.31 原生接口与数值路径修订后的有限选型", "",
        f"状态：`{supervisor['status']}`；新批执行源码：`{plan['source']['code_commit']}`。",
        f"原始记录：`{root}`。", "",
        "本批仅改变SWE-Next与Devstral的原生接口／密集学习路径；公共世界、六开发合同、SDK、9B路径、两seed及所有选择门均保持。9B的原12槽和旧source只读保留，未重跑或挑选其成功子集。",
        "v0.30原加载失败及r1技术资格失败均保留独立引用与成本；这不是logging-only恢复，也不是把新运行改写为v0.30成功。六案例仍是已见开发材料，不能用于训练支持、贡献估计或独立确认。", "",
        "## 旧trace数值证明与新鲜资格", "",
        "| 组合 | 来源 | 旧trace GPU门 | 当前状态 | 新鲜推理资格 | 更新接入 | 近16K | 完整恢复 |",
        "|---|---|---|---|---|---|---|---|"]
    for name, row in candidates.items():
        q, proof = row["qualification"], row["numeric_proof"]
        text.append(f"| {name} | {'原9B保留' if row['retained_original'] else '新v031组合'} | "
                    f"{'不适用' if proof is None else proof['status']} | {row['state']['status']} | "
                    f"{q['inference_ready']} | {q['training_integration_ready']} | "
                    f"{q['near_16k_capacity_demonstrated']} | {q['common_restored_exactly']} |")
    text += ["", "旧trace GPU控制只消费原失败的完整token，零新生成／零optimizer step，不证明16K容量。失败臂在numeric_preflight_failed终结，0新资格调用、0正式筛选；另一已准入臂可继续。新鲜资格仍需4条完整trace、原概率门、最多1次真实技术更新、1次新身份回流及完整common恢复。`None`表示未执行或无该项证据，不填成0分。", "",
             "## 正式筛选逐槽结果", "", "| 案例／seed | 9B原结果 | SWE-Next新组合 | Devstral新组合 |",
             "|---|---|---|---|"]
    for index, slot in enumerate(plan["inventories"][RETAINED]):
        cells = []
        for name in original.CANDIDATES:
            row = candidates[name]["outcomes"][index]
            cells.append(str(row["R"]) if row["status"] == "closed" else row["status"])
        text.append("| " + slot["case_id"] + " / " + str(slot["sampling_seed"]) + " | " + " | ".join(cells) + " |")
    text += ["", "公开测试绿色、任务数、消息数和固定提交都不等于完整验收。每臂须12槽全已知且API／修复／O1各至少2/4完整通过才可入选；三类成绩分开，未知或未启动不补零。", "",
             "## 分类与选择", ""]
    if selection:
        text += [f"预定选择结果：`{selection['status']}`；选定组合：`{selection['selected_candidate']}`。", "",
                 "| 组合 | API成功／已知 | 修复成功／已知 | O1成功／已知 | 可选 |", "|---|---:|---:|---:|---|"]
        for name, row in selection["candidate_results"].items():
            cells = [f"{row['categories'][category]['successful_complete_deliveries']}/{row['categories'][category]['known']}"
                     for category in original.CATEGORIES]
            text.append("| " + name + " | " + " | ".join(cells) + " | " + str(row["selection_eligible"]) + " |")
    else:
        text.append("两新组合尚未全部终态，未执行最终选择。")
    text += ["", "## 成本与解释范围", "",
             "| 组合 | 原v030 GPU秒 | r1 GPU秒 | 旧trace GPU证明秒 | v031新worker秒 | 累计GPU小时 |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, row in candidates.items():
        state, parts = row["state"], row["state"]["cost_components"]
        text.append(f"| {name} | {parts['original_worker_gpu_seconds']:.6f} | {parts['r1_worker_gpu_seconds']:.6f} | "
                    f"{parts['v031_old_trace_gpu_proof_seconds']:.6f} | {parts['v031_worker_gpu_seconds']:.6f} | "
                    f"{state['elapsed_gpu_seconds']/3600:.6f} |")
    text += ["", "成本排名使用上表实际分阶段总成本；原失败不丢弃、r1累计字段中的原失败不重复加。worker成本是单张GPU分配期间墙钟，不是按利用率积分；下载／排队与预约占用另留原始记录。", "",
             "本批不修改9B模型或原成绩，不根据已知隐藏失败补公开案例，不降低概率／完整交付／分类门。新旧差异只能作为已见开发集上的运行组合选型；没有B/G-raw/I-P配置试训、独立确认或算法收益结论。完整来源身份、实际trace长度、失败原因、数值回执和逐槽证据引用见配套JSON。", ""]
    (output / "software-model-selection-v031.md").write_text("\n".join(text))
    return value


def finish(plan_path, run_root, report_repo, *, publish=False):
    """Supervise once, archive v031 only, then optionally commit the two reports."""
    plan_path, run_root, report_repo = Path(plan_path).resolve(), Path(run_root).resolve(), Path(report_repo).resolve()
    state_path = run_root.parent / (run_root.name + "-finish.json")
    state = {"version": VERSION, "status": "supervising", "started_at": time.time(), "run_root": str(run_root)}
    write(state_path, state)
    process = subprocess.run([sys.executable, "-m", "scripts.software_model_selection_v031", "supervise",
                              "--plan", str(plan_path), "--output", str(run_root)], cwd=SOURCE, check=False)
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
                subprocess.run(["git", "commit", "--only", "-m", "docs: archive v0.31 native and replay selection", "--", *REPORT_PATHS],
                               cwd=report_repo, check=True)
            elif changed != 0:
                raise RuntimeError("Cannot determine the fixed v031 report change set")
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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--candidate", choices=EXECUTED)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--original-root", type=Path)
    parser.add_argument("--recovery-root", type=Path)
    parser.add_argument("--numeric-probe-reports", type=Path)
    parser.add_argument("--reservation-directory", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--report-repo", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.mode == "prepare":
        if not all((args.data_root, args.qualification, args.original_root, args.recovery_root, args.numeric_probe_reports, args.output)):
            parser.error("prepare requires data-root, qualification, both prior roots and numeric-probe-reports")
        made = make_plan(args.data_root, args.qualification, args.original_root, args.recovery_root,
                         read_json(args.numeric_probe_reports), args.reservation_directory)
        write(args.output, validate_plan(made))
    elif args.mode == "worker":
        if not args.plan or not args.candidate or not args.output:
            parser.error("worker requires plan, candidate and output")
        run_worker(args.plan, args.candidate, args.output)
    elif args.mode == "supervise":
        if not args.plan or not args.output:
            parser.error("supervise requires plan and output")
        supervise(args.plan, args.output)
    elif args.mode == "report":
        if not args.run_root or not args.output:
            parser.error("report requires run-root and output")
        report(args.run_root, args.output)
    else:
        if not all((args.plan, args.run_root, args.report_repo)):
            parser.error("finish requires plan, run-root and report-repo")
        finish(args.plan, args.run_root, args.report_repo, publish=args.publish)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("owned v031 supervisor stop")))
    main()
