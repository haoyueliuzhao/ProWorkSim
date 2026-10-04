"""Three fixed runtime combinations: technical admission, 36 bounded screens, selection.

There is no allocation experiment, automatic successor, model replacement, or
model retry in this DAG. All six source cases remain interface development data.
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
from proworksim.candidate_runtime_v030 import MODELS, candidate_profile
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.software_collaboration_v030 import CASE_IDS, INTERFACE_REVISION, PURPOSE, case_spec
from proworksim.software_runtime_v030 import MODE, _validate_window
from proworksim.storage import digest, json_bytes, read_json
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import checked, lock, read, reference, resources, stop_owned, write
from scripts.software_development_v028 import DurableTransport, available_cards, restore, task

VERSION = "software-model-selection-v0.30"
SOURCE = Path(__file__).resolve().parents[1]
CANDIDATES = ("qwen3.5-9b", "swe-next-14b", "devstral-small-2507")
SEEDS = (202610040701, 202610040702)
CATEGORIES = ("api_normal_path", "repair_after_real_failure", "o1_root_goal")
TERMINAL = frozenset({"complete", "qualification_failed", "download_failed", "stopped"})
LIMITS = {
    "max_parallel_model_instances": 3, "minimum_free_gpu_mib": 78000,
    "gpu_capacity_stability_seconds": 60, "own_gpu_memory_mib": 81920,
    "host_rss_per_worker_bytes": 64 * 1024**3,
    "artifact_bytes": 128 * 1024**3, "minimum_volume_free_bytes": 20 * 1024**3,
    "task_seconds": {"loading": 900, "episode": 2400, "boundary": 600,
                     "qualification_inference": 900, "qualification_update": None},
    "poll_seconds": 5,
}
SELECTION_RULE = {
    "minimum_successes_per_category": 2, "cases_per_category": 2, "seeds_per_case": 2,
    "require_all_12_known": True, "require_inference_and_training_qualification": True,
    "rank_order": ["o1_root_goal_successes_desc", "repair_after_real_failure_successes_desc",
                   "api_normal_path_successes_desc", "cases_passing_both_seeds_desc",
                   "format_errors_asc", "actual_worker_gpu_seconds_asc", "fixed_candidate_order"],
    "counts_not_used_for_ranking": ["messages", "method_classes", "cooperative_appearance"],
    "interpretation": "Runtime-combination selection; not a causal parameter-count comparison",
}


def inventory():
    """One common immutable ordering: seed outer, then the six distinct cases."""
    return [{"slot_id": f"screen-{repeat}-{index}", "case_id": case_id, "sampling_seed": seed,
             "first_member": "member_a", "role_decision_limits": dict.fromkeys(case_spec(case_id)["active_roles"], 64)}
            for repeat, seed in enumerate(SEEDS) for index, case_id in enumerate(CASE_IDS)]


def window_spec(window_id, rows):
    return {"window_id": window_id, "harness": "openhands_v16", "usage": PURPOSE, "mode": MODE,
            "min_class_count": 2, "slots": copy.deepcopy(rows),
            "budget": {"max_slots": len(rows), "max_model_calls": sum(sum(row["role_decision_limits"].values()) for row in rows)}}


def _implementation_reference():
    # code_identity covers src. This additionally freezes the supervisor and
    # resource/transport scripts actually imported by the queue.
    paths = ["scripts/software_model_selection_v030.py", "scripts/software_development_v028.py",
             "scripts/run_ne_v021.py", "scripts/run_bounded_v022.py"]
    return {name: digest((SOURCE / name).read_bytes()) for name in paths}


def make_plan(data_root, qualification):
    root = Path(data_root).resolve()
    metadata = root / "runs/v030-models/metadata"
    return {
        "version": VERSION, "created_at": time.time(), "source": code_identity(),
        "implementation_files_sha256": _implementation_reference(), "source_root": str(SOURCE),
        "data_root": str(root), "authorization": "User requested audited revisions, subsequent experiments and old 27B cleanup; project resource use and push are authorized.",
        "purpose": PURPOSE, "mode": MODE, "interface_revision": INTERFACE_REVISION,
        "candidates": list(CANDIDATES), "inventories": {candidate: inventory() for candidate in CANDIDATES},
        "candidate_profiles": {candidate: candidate_profile(candidate) for candidate in CANDIDATES[1:]},
        "source_metadata": {candidate: reference(metadata / MODELS[candidate]["repo_id"].replace("/", "--") / "model-info.json")
                            for candidate in CANDIDATES[1:]},
        "download_manifests": {candidate: str(root / "runs/v030-models/downloads" / (candidate + ".json")) for candidate in CANDIDATES[1:]},
        "runtime_dependency_path": str(root / "runs/v030-runtime-deps"),
        "gpu_preference": list(range(8)), "limits": copy.deepcopy(LIMITS),
        "total_gpu_seconds": None, "worker_gpu_seconds": None, "queue_deadline_at": None, "wall_deadline_at": None,
        "automatic_retries": False, "automatic_model_replacement": False, "automatic_successors": [],
        "max_screening_episodes": 36, "screening_episodes_per_candidate": 12,
        "qualification_limits": {"native_calls_per_candidate": 4, "updated_identity_fragments_per_candidate": 1,
                                 "calls_per_updated_identity_fragment": 1, "diagnostic_updates_per_candidate": 1,
                                 "development_cases_used_for_update": False},
        "selection_rule": copy.deepcopy(SELECTION_RULE),
        "qualification": reference(qualification),
        "prior_model_plan": reference(root / "runs/domain-v0201-p1-9b/plan.json"),
        "owner_recipe": reference(root / "runs/domain-v025-r1/train_base/actual/resident/owner.json"),
        "checkpoint_marker": reference(root / "runs/domain-v025-r1/checkpoints/base.json"),
        "shared_gpu_capacity_allowed": False, "model_api_calls": 0,
        "stop_after": "fixed_model_interface_screening_and_selection",
        "source_scope": "New six-case development pool only; schema contribution and TextFSM confirmation cannot select a model or become these screening cases.",
    }


def validate_plan(plan, *, check_files=True):
    if (plan.get("version") != VERSION or plan.get("candidates") != list(CANDIDATES)
            or plan.get("inventories") != {candidate: inventory() for candidate in CANDIDATES}
            or plan.get("candidate_profiles") != {candidate: candidate_profile(candidate) for candidate in CANDIDATES[1:]}
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != list(range(8))
            or plan.get("selection_rule") != SELECTION_RULE or plan.get("purpose") != PURPOSE or plan.get("mode") != MODE
            or plan.get("interface_revision") != INTERFACE_REVISION
            or plan.get("max_screening_episodes") != 36 or plan.get("screening_episodes_per_candidate") != 12
            or plan.get("qualification_limits") != {"native_calls_per_candidate": 4, "updated_identity_fragments_per_candidate": 1,
                "calls_per_updated_identity_fragment": 1, "diagnostic_updates_per_candidate": 1, "development_cases_used_for_update": False}
            or plan.get("automatic_retries") is not False or plan.get("automatic_model_replacement") is not False
            or plan.get("automatic_successors") != [] or plan.get("shared_gpu_capacity_allowed") is not False
            or plan.get("model_api_calls") != 0 or plan.get("stop_after") != "fixed_model_interface_screening_and_selection"
            or any(plan.get(key) is not None for key in ("total_gpu_seconds", "worker_gpu_seconds", "queue_deadline_at", "wall_deadline_at"))):
        raise ValueError("Fixed v030 candidate list, source inventory, admission, ranking or resource protocol differs")
    root = Path(plan["data_root"])
    if plan.get("download_manifests") != {
            candidate: str(root / "runs/v030-models/downloads" / (candidate + ".json")) for candidate in CANDIDATES[1:]}:
        raise ValueError("A pending download can only complete at its predeclared manifest path")
    if plan.get("runtime_dependency_path") != str(root / "runs/v030-runtime-deps"):
        raise ValueError("Use the isolated declared runtime dependencies")
    for candidate in CANDIDATES:
        _validate_window(window_spec("validate-" + candidate, plan["inventories"][candidate]))
    if check_files:
        if (plan.get("source") != code_identity() or plan["source"].get("code_dirty") is not False
                or plan.get("source_root") != str(SOURCE) or plan.get("implementation_files_sha256") != _implementation_reference()):
            raise ValueError("Run only the clean frozen source snapshot, including its supervisor scripts")
        qualification = read_json(checked(plan["qualification"]))
        if qualification.get("passed") is not True or qualification.get("source") != plan["source"] or qualification.get("model_calls") != 0:
            raise ValueError("Require same-source CPU interface/SDK qualification before GPU work")
        original = read_json(checked(plan["owner_recipe"]))["recipe"]
        prior = read_json(checked(plan["prior_model_plan"]))
        marker = read_json(checked(plan["checkpoint_marker"]))
        saved = read_json(checked(marker["checkpoint"]))
        checked(prior["manifest"])
        if (prior["runtime_profile"]["candidate_id"] != CANDIDATES[0]
                or original["max_length"] != 16384 or original["max_output_tokens"] != 2048
                or original["credit_assignment"] != "terminal_mc"
                or saved["actor_steps"] != 3 or saved["critic_steps"] != 3):
            raise ValueError("Freeze the original 9B 3/3 full learner and common numerical recipe")
        for candidate in CANDIDATES[1:]:
            metadata = read_json(checked(plan["source_metadata"][candidate]))
            if metadata["id"] != MODELS[candidate]["repo_id"] or metadata["sha"] != MODELS[candidate]["revision"]:
                raise ValueError("Official candidate metadata revision differs")
    return plan


def download_state(plan, candidate):
    """Pending or failed downloads never occupy a GPU and never substitute models."""
    if candidate == CANDIDATES[0]:
        return {"status": "ready", "manifest": plan["prior_model_plan"]}
    manifest = read(Path(plan["download_manifests"][candidate]))
    if manifest is None:
        return {"status": "waiting_download"}
    if (manifest.get("candidate_id") != candidate or manifest.get("repo_id") != MODELS[candidate]["repo_id"]
            or manifest.get("declared_hf_revision") != MODELS[candidate]["revision"]
            or manifest.get("source_metadata_sha256") != plan["source_metadata"][candidate]["sha256"]):
        return {"status": "download_failed", "reason": "Downloaded source identity differs from frozen official metadata"}
    status = manifest.get("status", "")
    if status == "complete":
        return {"status": "ready", "manifest": reference(plan["download_manifests"][candidate]),
                "model_path": manifest["model_path"]}
    if "failed" in status or "error" in status:
        return {"status": "download_failed", "reason": status}
    return {"status": "waiting_download", "download_status": status}


class RoutedTransport:
    """One stable SDK transport handle whose only active inner is the current slot."""
    def __init__(self):
        self.inner = None

    def complete(self, request, **kwargs):
        if self.inner is None:
            raise RuntimeError("No predeclared screening or technical return slot is active")
        return self.inner.complete(request, **kwargs)


class CollectionOwner:
    def __init__(self, owner):
        from proworksim.software_context_v028 import VERSION as CONTEXT_POLICY
        self.owner, self.transport = owner, RoutedTransport()
        self.software_context_policy = self.software_context_projection = CONTEXT_POLICY

    def __getattr__(self, name):
        return getattr(self.owner, name)


def collect(owner, spec, output, worker_output, *, task_kind="episode"):
    """Frozen collection; close through the existing owner and restore Torch RNG."""
    from proworksim.software_context_v028 import SoftwareContextTransport
    from proworksim.software_runtime_v030 import collect_software_window
    output = Path(output)
    before = owner.capture_evaluation_state()
    identity = owner.freeze_identity()
    binding = {key: copy.deepcopy(getattr(owner, key)) for key in ("recipe", "inference_profile", "base_identity", "software_learning_binding")}
    facade = CollectionOwner(owner)
    owner.begin_window(spec["window_id"])

    def boundary(event, row, folder):
        if event == "started":
            task(worker_output, row["slot_id"], task_kind)
            directory = folder / "raw-transport"
            facade.transport.inner = DurableTransport(
                SoftwareContextTransport(owner, directory / "context-projections"), directory, owner.window_id)
        else:
            task(worker_output, "close-" + row["slot_id"], "boundary")
            facade.transport.inner = None

    try:
        entries = collect_software_window(facade, spec, output, on_slot=boundary)
        owner.finish_evaluation(entries, output / "frozen-collection-close")
    finally:
        facade.transport.inner = None
        guard = owner.finish_evaluation_guard(before)
        guard["software_binding_unchanged"] = all(getattr(owner, key) == value for key, value in binding.items())
        guard["actor_identity_unchanged"] = owner.freeze_identity() == identity
        guard["software_binding_before_sha256"] = digest(json_bytes(binding))
        write(output / "evaluation-guard.json", guard)
    if not all(guard[key] for key in ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged")):
        raise ValueError("Frozen screening changed learning state, binding or failed to restore Torch RNG")
    return entries


def return_probe(owner, candidate, output, worker_output):
    """Exactly one updated-identity WorldCore opportunity; outside 36 screens."""
    folder = Path(output)
    row = {"slot_id": "technical-return", "case_id": CASE_IDS[0], "sampling_seed": 202610040700,
           "first_member": "member_a", "role_decision_limits": {"member_a": 1}}
    expected = owner.freeze_identity()
    wid = "v030-technical-return-" + candidate
    collect(owner, window_spec(wid, [row]), folder, worker_output, task_kind="qualification_inference")
    responses = []
    for path in sorted((folder / "slot-0/raw-transport").glob("call-*.finished.json")):
        record = read_json(path)
        body = record.get("response", {}).get("body", {})
        if isinstance(body, dict) and body.get("token_trace") is not None:
            responses.append(body)
    guard = read_json(folder / "evaluation-guard.json")
    result = {"calls": len(responses), "expected_actor_identity": expected,
              "observed_actor_identities": [row.get("actor_identity") for row in responses],
              "window_ids": [row.get("online_window_id") for row in responses],
              "learning_unchanged": guard["learning_unchanged"], "rng_restored_exactly": guard["rng_restored_exactly"],
              "source": "one_actual_updated_identity_WorldCore_fragment_not_screening_or_training",
              "screening_episode_count": 0, "business_success_required": False}
    write(folder / "updated-identity-return.json", result)
    return result


def _screen_row(row, entry, folder):
    case = case_spec(row["case_id"])
    events = [json.loads(line) for line in (Path(folder) / "slot-0/experience.jsonl").read_text().splitlines()]
    format_errors = sum(event["kind"] == "model_format_error" for event in events)
    reward = entry["reward"]
    return {**copy.deepcopy(row), "category": case["category"], "active_members": case["active_roles"],
            "status": "closed" if reward["eligible"] else "execution_unknown", "R": reward["reward"],
            "complete_work": entry["rollout"]["work_validity"]["value"],
            "record_validity": entry["rollout"]["work_validity"]["components"]["record"]["value"],
            "format_errors": format_errors, "training_eligible": False,
            "entry": reference(Path(folder) / "slot-0/entry.json"),
            "assessment": reference(Path(folder) / "slot-0/assessment.json"),
            "evaluation_guard": reference(Path(folder) / "evaluation-guard.json"),
            "process_diagnostics": copy.deepcopy(entry["process_diagnostics"])}


def run_worker(plan_path, run_root, worker, output):
    from proworksim.candidate_runtime_v030 import DenseCandidateActor
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.model_qualification_v030 import qualify
    from proworksim.online_training import tensor_tree_digest
    from proworksim.software_learning_v029 import migrate_software_owner

    del run_root  # Every candidate owns one resident process and no other worker's state.
    plan = validate_plan(read_json(plan_path))
    if worker not in CANDIDATES or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, plan["gpu_preference"])):
        raise ValueError("A fixed candidate worker requires one declared physical GPU")
    ready = download_state(plan, worker)
    if ready["status"] != "ready":
        raise ValueError("A worker cannot occupy a GPU while its official download is pending")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    owner = None
    report = {"version": VERSION, "candidate_id": worker, "status": "loading", "started_at": time.time(),
              "source_before": code_identity(), "rows": [], "screening_optimizer_steps": 0,
              "runtime_combination_only": True, "model_replacement": False, "plan": reference(plan_path)}
    write(output / "report.json", report)
    try:
        task(output, "load-" + worker, "loading")
        sample = resources()
        write(output / "preload-resources.json", sample)
        if int(os.environ["CUDA_VISIBLE_DEVICES"]) not in [card["index"] for card in available_cards(plan, sample)]:
            raise RuntimeError("Assigned exclusive GPU capacity changed before loading")
        original = read_json(checked(plan["owner_recipe"]))["recipe"]
        if worker == CANDIDATES[0]:
            prior = read_json(checked(plan["prior_model_plan"]))
            owner = DeterministicCandidateActor.from_candidate(prior["model"], manifest=checked(prior["manifest"]),
                profile=prior["runtime_profile"], recipe=original, output=output / "resident")
            restore(owner, plan, output)
            migration = migrate_software_owner(owner)
        else:
            frozen_manifest = read_json(checked(ready["manifest"]))
            write(output / "model-download-manifest.json", frozen_manifest)
            owner = DenseCandidateActor.from_candidate(ready["model_path"], manifest=checked(ready["manifest"]),
                profile=plan["candidate_profiles"][worker], recipe=original, output=output / "resident")
            if (owner.actor_steps, owner.critic_steps) != (0, 0):
                raise ValueError("New architectures must not inherit 9B adapters or optimizer history")
            migration = migrate_software_owner(owner, expected_steps=None)
        write(output / "software-critic-migration.json", migration)
        task(output, "common-state", "boundary")
        common_dir = output / "common-state"
        common = owner.save_checkpoint(common_dir)
        write(output / "common.json", {**common, "directory": str(common_dir), "recipe": owner.recipe})
        report.update(status="qualifying", initial_actor_steps=owner.actor_steps, initial_critic_steps=owner.critic_steps,
                      common_actor_identity=owner.freeze_identity())
        write(output / "report.json", report)

        def stage(kind, label):
            if kind not in LIMITS["task_seconds"]:
                raise ValueError("Qualification named an undeclared resource stage: " + str(kind))
            task(output, label, kind)

        qualification = qualify(owner, output / "qualification", common_dir=common_dir,
            return_probe=lambda qualified_owner, folder: return_probe(qualified_owner, worker, folder, output), on_stage=stage)
        report["qualification"] = qualification
        write(output / "qualification-result.json", qualification)
        if tensor_tree_digest(owner._state_bundle(), owner.torch) != common["state_tensor_digest"]:
            raise ValueError("Technical qualification did not restore the complete common learner/RNG state")
        if not (qualification.get("inference_ready") is True and qualification.get("training_ready") is True):
            report["status"] = "qualification_failed"
            return report
        report["status"] = "screening"
        write(output / "report.json", report)
        for row in plan["inventories"][worker]:
            if owner.freeze_identity() != common["actor_identity"]:
                raise ValueError("Screening actor differs from its common prequalification identity")
            folder = output / row["slot_id"]
            entries = collect(owner, window_spec("v030-" + worker + "-" + row["slot_id"], [row]), folder, output)
            report["rows"].append(_screen_row(row, entries[0], folder))
            write(output / "progress.json", report["rows"])
            write(output / "report.json", report)
        report["status"] = "complete"
    except BaseException as error:
        report.update(status="interrupted_or_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps, final_actor_identity=owner._make_identity())
        report.update(ended_at=time.time(), source_after=code_identity())
        write(output / "report.json", report)
    return report


def candidate_result(plan, candidate, report, state):
    rows = report.get("rows", [])
    expected = plan["inventories"][candidate]
    if len(rows) > len(expected) or any(any(row.get(key) != value for key, value in canonical.items())
                                      for row, canonical in zip(rows, expected)):
        raise ValueError("Candidate screening results must retain the exact frozen inventory prefix")
    qualification = report.get("qualification", {})
    ready = qualification.get("inference_ready") is True and qualification.get("training_ready") is True
    known = len(rows) == 12 and all(row.get("status") == "closed" and type(row.get("R")) is int and row["R"] in (0, 1) for row in rows)
    categories = {category: {"expected": 4, "known": 0, "successful_complete_deliveries": 0} for category in CATEGORIES}
    successes = {}
    for row in rows:
        category = case_spec(row["case_id"])["category"]
        if row.get("category") != category:
            raise ValueError("A screening outcome cannot change its source category")
        is_known = row.get("status") == "closed" and type(row.get("R")) is int and row["R"] in (0, 1)
        success = is_known and row["R"] == 1 and row.get("complete_work") is True
        categories[category]["known"] += int(is_known)
        categories[category]["successful_complete_deliveries"] += int(success)
        successes.setdefault(row["case_id"], []).append(success)
    consistent = sum(len(values) == 2 and all(values) for values in successes.values())
    errors = sum(row.get("format_errors", 0) for row in rows)
    seconds = state.get("elapsed_gpu_seconds")
    cost_known = type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0
    eligible = bool(state["status"] == "complete" and report.get("status") == "complete" and ready and known and cost_known
                    and all(values["successful_complete_deliveries"] >= 2 for values in categories.values()))
    return {"candidate_id": candidate, "status": state["status"], "qualification_complete": ready,
            "screening_rows_recorded": len(rows), "all_12_known": known, "categories": categories,
            "cases_passing_both_seeds": consistent, "format_errors": errors,
            "actual_worker_gpu_seconds": seconds if cost_known else None, "selection_eligible": eligible,
            "cost_scope": "Single-GPU assigned worker wall duration including load, qualification and screening; not utilization-weighted computation",
            "screening_is_training_support": False}


def select_candidate(plan, states, reports):
    if set(states) != set(CANDIDATES) or any(state["status"] not in TERMINAL for state in states.values()):
        raise ValueError("Selection waits for all three fixed candidates to become terminal")
    results = {candidate: candidate_result(plan, candidate, reports.get(candidate, {}), states[candidate]) for candidate in CANDIDATES}

    def ranking(candidate):
        row = results[candidate]
        counts = row["categories"]
        return (-counts["o1_root_goal"]["successful_complete_deliveries"],
                -counts["repair_after_real_failure"]["successful_complete_deliveries"],
                -counts["api_normal_path"]["successful_complete_deliveries"],
                -row["cases_passing_both_seeds"], row["format_errors"], row["actual_worker_gpu_seconds"], CANDIDATES.index(candidate))

    ranked = sorted((candidate for candidate, row in results.items() if row["selection_eligible"]), key=ranking)
    return {"version": VERSION, "status": "selected" if ranked else "finite_batch_no_qualified_candidate",
            "selected_candidate": ranked[0] if ranked else None, "eligible_candidate_order": ranked,
            "candidate_results": results, "selection_rule": copy.deepcopy(SELECTION_RULE),
            "automatic_successors": [], "allocation_experiment_started": False,
            "scope": "Fixed runtime-combination selection. Categories remain separate; no allocation-effect or causal model-size conclusion."}


def worker_env(plan, root, candidate, gpu):
    temporary = Path(root) / candidate / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu), "PYTHONHASHSEED": "0",
           "PYTHONPATH": os.pathsep.join([plan["runtime_dependency_path"], str(SOURCE / "src"), str(SOURCE)]),
           "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "TOKENIZERS_PARALLELISM": "false", "TMPDIR": str(temporary), "TMP": str(temporary), "TEMP": str(temporary)}
    env.pop("PROWORKSIM_REPLICA_GPUS", None)
    return env


def supervise(plan_path, root):
    plan = validate_plan(read_json(plan_path))
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    summary = {"version": VERSION, "status": "waiting", "started_at": time.time(),
               "observer_pid": os.getpid(), "source": code_identity(),
               "states": {candidate: {"candidate_id": candidate, "status": "not_started", "attempted": False}
                          for candidate in CANDIDATES}}
    active, logs, guards, stable = {}, {}, {}, {}

    def publish():
        summary["observed_at"] = time.time()
        summary["worker_gpu_seconds"] = sum(state.get("elapsed_gpu_seconds", 0) for state in summary["states"].values())
        summary["running_gpu_seconds"] = sum(time.time() - summary["states"][name]["started_at"] for name in active)
        write(root / "supervisor.json", summary)

    def finish(candidate, reason):
        process = active.pop(candidate)
        if process.poll() is None:
            stop_owned(process)
        process.wait(timeout=15)
        report = read(root / candidate / "actual/report.json") or {}
        okay = process.returncode == 0 and reason is None and report.get("status") in {"complete", "qualification_failed"}
        state = summary["states"][candidate]
        state.update(ended_at=time.time(), exit_code=process.returncode, stop_reason=reason,
                     status=report["status"] if okay else "stopped")
        state["elapsed_gpu_seconds"] = state["ended_at"] - state["started_at"]
        logs.pop(candidate).close()
        write(root / candidate / "state.json", state)

    with lock(root):
        try:
            while True:
                now = time.time()
                for candidate, process in list(active.items()):
                    if process.poll() is not None:
                        finish(candidate, None if process.returncode == 0 else "worker_exit_error")
                for candidate, state in summary["states"].items():
                    if state["status"] in {"not_started", "waiting_download"}:
                        source = download_state(plan, candidate)
                        if source["status"] == "download_failed":
                            state.update(status="download_failed", attempted=False, ended_at=now,
                                         elapsed_gpu_seconds=0, download_result=source)
                        else:
                            state["status"] = "not_started" if source["status"] == "ready" else "waiting_download"
                if all(state["status"] in TERMINAL for state in summary["states"].values()):
                    reports = {candidate: read(root / candidate / "actual/report.json") or {} for candidate in CANDIDATES}
                    selection = select_candidate(plan, summary["states"], reports)
                    write(root / "selection.json", selection)
                    summary.update(status=selection["status"], selected_candidate=selection["selected_candidate"])
                    break
                waiting = [candidate for candidate in CANDIDATES if summary["states"][candidate]["status"] == "not_started"]
                if waiting:
                    sample = resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    ready = available_cards(plan, sample, [summary["states"][candidate]["gpu"] for candidate in active])
                    stable = {card["index"]: stable.get(card["index"], now) for card in ready}
                    for card in ready:
                        if not waiting or len(active) >= LIMITS["max_parallel_model_instances"]:
                            break
                        if now - stable[card["index"]] < LIMITS["gpu_capacity_stability_seconds"]:
                            continue
                        if code_identity() != plan["source"] or _implementation_reference() != plan["implementation_files_sha256"]:
                            raise ValueError("Frozen source snapshot changed while queued")
                        if shutil.disk_usage(root).free < LIMITS["minimum_volume_free_bytes"]:
                            raise RuntimeError("Insufficient storage reserve for original trajectories")
                        candidate = waiting.pop(0)
                        folder = root / candidate
                        folder.mkdir(exist_ok=False)
                        argv = [sys.executable, "-m", "scripts.software_model_selection_v030", "worker", "--plan", str(plan_path),
                                "--run-root", str(root), "--output", str(folder / "actual"), "--worker", candidate]
                        logs[candidate] = (folder / "worker.log").open("x")
                        process = subprocess.Popen(argv, cwd=SOURCE, env=worker_env(plan, root, candidate, card["index"]),
                            stdin=subprocess.DEVNULL, stdout=logs[candidate], stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        summary["states"][candidate].update(status="running", attempted=True, gpu=card["index"],
                            gpu_uuid=card["uuid"], pid=process.pid, process_identity=identity, started_at=time.time(), command=argv)
                        active[candidate] = process
                        guards[candidate] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        write(folder / "state.json", summary["states"][candidate])
                        publish()
                else:
                    # A card must be observed continuously after a download
                    # becomes ready; old idle samples cannot satisfy stability.
                    stable = {}
                if active:
                    with ThreadPoolExecutor(max_workers=3) as pool:
                        futures = {candidate: pool.submit(target_resources, summary["states"][candidate]["gpu"], worker_pid=process.pid)
                                   for candidate, process in active.items()}
                        samples = {candidate: future.result() for candidate, future in futures.items()}
                    size, free = artifact_bytes(root), shutil.disk_usage(root).free
                    for candidate, process in list(active.items()):
                        if process.poll() is not None:
                            finish(candidate, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = summary["states"][candidate]
                        guard = guards[candidate].observe(samples[candidate], time.time(), process.pid, state["gpu"],
                                                          own_memory_limit_mib=LIMITS["own_gpu_memory_mib"])
                        current = read(root / candidate / "actual/task.json") or {"kind": "loading", "started_at": state["started_at"]}
                        own_rss, reason = rss(process.pid), guard.get("stop_reason")
                        cap = LIMITS["task_seconds"].get(current.get("kind"))
                        if current.get("kind") not in LIMITS["task_seconds"]:
                            reason = "unknown_task_kind"
                        elif cap is not None and time.time() - current["started_at"] >= cap:
                            reason = "single_task_budget"
                        elif own_rss > LIMITS["host_rss_per_worker_bytes"]:
                            reason = "host_memory_budget"
                        elif size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                            reason = "trajectory_storage_reserve"
                        with (root / candidate / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": samples[candidate], "guard": guard, "task": current,
                                                     "rss_bytes": own_rss, "artifact_bytes": size}) + "\n")
                        if reason:
                            finish(candidate, reason)
                summary["status"] = "running" if active else "waiting"
                publish()
                time.sleep(LIMITS["poll_seconds"])
        except BaseException as error:
            summary.update(status="supervisor_interrupted", error={"type": type(error).__name__, "message": str(error)})
            for candidate in list(active):
                finish(candidate, "supervisor_interrupted")
            raise
        finally:
            summary["ended_at"] = time.time()
            publish()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "worker", "supervise"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--worker", choices=CANDIDATES)
    args = parser.parse_args()
    if args.mode == "prepare":
        if not args.data_root or not args.qualification:
            parser.error("prepare requires --data-root and --qualification")
        write(args.output, validate_plan(make_plan(args.data_root, args.qualification)))
    elif args.mode == "worker":
        if not args.plan or not args.run_root or not args.worker:
            parser.error("worker requires --plan, --run-root and --worker")
        run_worker(args.plan, args.run_root, args.worker, args.output)
    else:
        if not args.plan:
            parser.error("supervise requires --plan")
        supervise(args.plan, args.output)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("owned supervisor stop")))
    main()
