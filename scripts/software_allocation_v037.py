"""Independent v037 execution of the unchanged v036 allocation inventory.

Exact per-row weighted gradients are reused only at their complete-state binding;
new backward work, cache application and model evaluation costs remain distinct.
This runner never changes or stops the original v036 execution or another job.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import copy
import csv
import hashlib
import io
import math
import tarfile
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.experience_allocation_v035 import (
    METHODS, bind_allocation, bind_candidate, development_receipt, select_allocation,
)
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_support_v036 as support
from scripts import software_allocation_v036 as original_allocation
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, resources, write
from scripts.software_development_v028 import task

VERSION = "software-allocation-execution-v0.37"
SOURCE = Path(__file__).resolve().parents[1]
# User's physical-device restriction, independent of CUDA's local renumbering.
# Historical P2/P3 plans retain their original device lists as audit evidence.
GPU_ORDER = (3, 4, 5, 7)
LIMITS = {**copy.deepcopy(support.LIMITS), "max_parallel_model_instances": 4,
          "minimum_free_gpu_mib": 56 * 1024, "own_gpu_memory_mib": 56 * 1024,
          "minimum_live_free_gpu_mib": 6 * 1024, "shared_gpu_capacity_allowed": True,
          "task_seconds": {**support.LIMITS["task_seconds"], "training_step": 900, "cache_wait": None}}
TERMINAL = {"complete", "stopped"}
REPORT_PATHS = ["docs/experiments/software-allocation-v037.md", "docs/experiments/software-allocation-v037.json"]


def _check_references(value, seen=None):
    """Check immutable referenced bytes without relabeling their original source."""
    seen = set() if seen is None else seen
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            key = (value["path"], value["sha256"])
            if key not in seen:
                path = Path(value["path"])
                if not path.is_file() or digest(path.read_bytes()) != value["sha256"]:
                    raise ValueError("Inherited immutable artifact bytes changed")
                if "bytes" in value and path.stat().st_size != value["bytes"]:
                    raise ValueError("Inherited immutable artifact size changed")
                seen.add(key)
        for item in value.values():
            _check_references(item, seen)
    elif isinstance(value, list):
        for item in value:
            _check_references(item, seen)


def inherited_source_manifest(parent_source):
    """Bind every inherited Python source to its actual historical git bytes."""
    if parent_source.get("code_dirty") is not False:
        raise ValueError("Require the original clean frozen source")
    archive = subprocess.check_output(["git", "archive", parent_source["code_commit"], "src", "scripts"], cwd=SOURCE)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        for member in stream.getmembers():
            if member.isfile() and member.name.endswith(".py"):
                data = stream.extractfile(member).read()
                files[member.name] = {"sha256": digest(data), "bytes": len(data)}
    source_hash = hashlib.sha256()
    for name in sorted(files):
        path = SOURCE / name
        if not path.is_file():
            raise ValueError("An inherited numerical source was removed")
        data = path.read_bytes()
        if {"sha256": digest(data), "bytes": len(data)} != files[name]:
            raise ValueError("Inherited source bytes changed: " + name)
        if name.startswith("src/"):
            source_hash.update(name.encode())
            source_hash.update(data)
    if source_hash.hexdigest() != parent_source["source_tree_sha256"]:
        raise ValueError("The historical source tree differs from its P2 identity")
    return files


def verify_parent(parent_root):
    """Validate historical P2 under its own source, with no code-identity override."""
    parent_root = Path(parent_root).resolve()
    plan = support.validate_plan(read_json(parent_root / "plan.json"), check_files=False)
    freeze = read_json(parent_root / "postcollection-freeze.json")
    if (freeze.get("version") != "postcollection-freeze-v0.36"
            or freeze.get("automatic_execution") is not True
            or not freeze.get("automatic_execution_authorization")
            or freeze["P2_plan"] != reference(parent_root / "plan.json")
            or freeze["P2_worker"] != reference(parent_root / support.CANDIDATE / "actual/report.json")
            or freeze["P2_supervisor"] != reference(parent_root / "supervisor.json")):
        raise ValueError("Require the original authorized postcollection freeze")
    _check_references([plan, freeze])
    worker = read_json(support.checked(freeze["P2_worker"]))
    supervisor = read_json(support.checked(freeze["P2_supervisor"]))
    qualification = read_json(support.checked(plan["qualification"]))
    if (worker.get("source_before") != plan["source"] or worker.get("source_after") != plan["source"]
            or worker.get("status") != "complete" or worker.get("common_restored_exactly") is not True
            or worker.get("execution_binding_passed") is not True
            or supervisor.get("status") != "complete"
            or supervisor["states"][support.CANDIDATE].get("status") != "complete"
            or any(worker.get(k) != 3 for k in ("initial_actor_steps", "initial_critic_steps", "actor_steps", "critic_steps"))
            or worker.get("new_actor_optimizer_steps") != 0 or worker.get("new_critic_optimizer_steps") != 0
            or qualification.get("source") != plan["source"] or qualification.get("passed") is not True):
        raise ValueError("Require trusted unchanged P2 with its own frozen source and complete common")
    allocation = freeze["allocation"]
    if (allocation["plan_sha256"] != digest(json_bytes({k: v for k, v in allocation.items() if k != "plan_sha256"}))
            or freeze["actual_inventory"] != allocation["actual_inventory"]
            or freeze["actual_inventory"]["unique_trial_updates"] != 27
            or freeze["actual_inventory"]["formal_updates"] != 3):
        raise ValueError("Preserve the actual 27 trial and three formal update inventory")
    for label, panel in (("units", "development"), ("independent_units", "confirmation")):
        expected = [{"unit_id": r["slot_id"], "root_id": r["case_id"], "seed": r["sampling_seed"], "weight": 1.0}
                    for r in plan["inventories"][panel]]
        if (allocation["development"][label] != expected or len(expected) != 16
                or len({r["root_id"] for r in expected}) != 4):
            raise ValueError("Preserve each original four-root by four-seed panel")
    common = read_json(support.checked(freeze["common"]))
    _check_references(common)
    original = read_json(support.checked(common["common"]))
    _check_references(original)
    if (common["state_tensor_digest"] != original["state_tensor_digest"]
            or common["actor_identity"] != original["actor_identity"]):
        raise ValueError("The inherited complete common changed")
    return plan, freeze


def import_shared_B(parent_root, folder, freeze):
    """Adopt a closed original B without claiming its work as newly executed."""
    parent_root, folder = Path(parent_root).resolve(), Path(folder).resolve()
    if folder != parent_root / "trial-B/actual":
        raise ValueError("Only the actual original shared B can be imported")
    parent_plan = read_json(parent_root / "plan.json")
    supervisor = read_json(parent_root / "p3-supervisor.json")
    state = supervisor["states"]["trial-B"]
    if (state.get("status") != "complete" or state.get("exit_code") != 0
            or state.get("stop_reason") is not None or not state.get("archive")
            or state.get("ended_at") is None):
        raise ValueError("Import only the exited and losslessly archived complete original B")
    _check_references(state["archive"])
    receipt = original_allocation.verified_receipt(parent_root, "trial-B", freeze["allocation"])
    report = read_json(folder / "report.json")
    update = read_json(support.checked(report["update"]))
    material = read_json(support.checked(freeze["training_material_binding"]))
    original_allocation.require_actual_update(update, material)
    required = ["report.json", "panel-summary.json", "development-receipt.json", "common-restore.json",
                "update/report.json", "update/gradients-before-clip.pt", "update/software-consumption.json",
                "updated-state/checkpoint.json", "cold-archive-receipt.json"]
    refs = {name: reference(folder / name) for name in required}
    _check_references(read_json(folder / "updated-state/checkpoint.json"))
    return {"folder": str(folder), "source": parent_plan["source"], "references": refs,
        "original_worker_state": copy.deepcopy(state), "original_development_receipt": receipt,
        "original_actual_backward_decisions": update["backward_decisions_completed"],
        "original_worker_gpu_seconds": state["elapsed_gpu_seconds"],
        "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_decisions": 0,
        "scope": "Previously executed original v036 shared B is counted once in the frozen 27 trials, not as new v037 GPU work. Its per-row gradients were not stored, so this import does not prefill the new exact weighted-gradient cache."}


def worker_folder(root, name, plan=None):
    root = Path(root)
    plan = read_json(root / "plan.json") if plan is None else plan
    imported = plan.get("imported_B")
    if name == "trial-B" and imported:
        return Path(imported["folder"])
    return root / name / "actual"


OPTIMIZATION_CHECKS = ("project_regression_resolved", "ruff_passed", "updater_cpu_bitwise_passed",
                       "tiny_cpu_bitwise_passed", "tiny_cuda_declared_profile_bitwise_passed")
OPTIMIZATION_SOURCES = ("scripts/software_allocation_v037.py", "src/proworksim/software_learning_v037.py",
                        "src/proworksim/gradient_bank_v037.py")


def validate_optimization_controls(path):
    """Bind production-profile qualification to this source and original receipts.

    Exploratory controls can contain an explicitly failed nonproduction profile;
    only the declared mixed-BF16 efficient-only profile is admitted here.
    """
    value = read_json(Path(path))
    checks = value.get("required_checks", {})
    files, evidence = value.get("source_files"), value.get("evidence")
    if (value.get("version") != "gradient-cache-qualification-v0.37"
            or value.get("passed_for_declared_production") is not True
            or value.get("declared_profile") != "original-v0201-mixed-bf16-efficient-only"
            or any(checks.get(name) is not True for name in OPTIMIZATION_CHECKS)
            or not isinstance(files, dict) or not set(OPTIMIZATION_SOURCES).issubset(files)
            or not isinstance(evidence, (dict, list)) or not evidence):
        raise ValueError("Require the complete declared-production optimization qualification")
    for name, expected in files.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or not name.endswith(".py"):
            raise ValueError("Optimization source bindings must be relative Python paths")
        source_path = SOURCE / relative
        if (not source_path.is_file() or not source_path.resolve().is_relative_to(SOURCE.resolve())
                or digest(source_path.read_bytes()) != expected):
            raise ValueError("Qualified optimization source bytes changed: " + name)
    def count_refs(item):
        if isinstance(item, dict):
            if isinstance(item.get("path"), str) and isinstance(item.get("sha256"), str):
                return 1
            return sum(count_refs(child) for child in item.values())
        if isinstance(item, list):
            return sum(count_refs(child) for child in item)
        return 0
    if count_refs(evidence) == 0:
        raise ValueError("Optimization qualification requires original receipt references")
    _check_references(evidence)
    return value


def optimization_qualification_path(root, qualification=None):
    return (Path(qualification) if qualification is not None
            else Path(root).parent / "v037-controls/qualification.json").resolve()


def prepare(parent_root, root, *, imported_B=None, qualification=None):
    parent_root, root = Path(parent_root).resolve(), Path(root).resolve()
    if root.exists() or root == parent_root:
        raise FileExistsError("Use a new independent v037 output directory")
    qualification = optimization_qualification_path(root, qualification)
    validate_optimization_controls(qualification)
    parent, freeze = verify_parent(parent_root)
    inherited = inherited_source_manifest(parent["source"])
    imported = import_shared_B(parent_root, imported_B, freeze) if imported_B is not None else None
    source = code_identity()
    if source.get("code_dirty") is not False:
        raise ValueError("Commit the complete new execution implementation before prepare")
    plan = {"version": VERSION, "status": "prepared", "created_at": time.time(),
        "source": source, "source_root": str(SOURCE), "parent_root": str(parent_root),
        "optimization_qualification": reference(qualification),
        "parent_plan": reference(parent_root / "plan.json"),
        "parent_freeze": reference(parent_root / "postcollection-freeze.json"),
        "parent_source": parent["source"], "inherited_source_files": inherited,
        "numeric_source_manifest_sha256": digest(json_bytes(inherited)),
        "inventories": parent["inventories"], "limits": copy.deepcopy(LIMITS),
        "gpu_preference": list(GPU_ORDER), "runtime_dependency_path": parent["runtime_dependency_path"],
        "prior_artifact_roots": support.dense._artifact_roots([*parent["prior_artifact_roots"], parent_root]),
        "actual_inventory": freeze["actual_inventory"], "imported_B": imported, "shared_cache_root": str(root / "gradient-cache"),
        "automatic_execution_authorization": "User requested runtime optimization and previously authorized completion of the entire frozen allocation experiment and automatic commit/push.",
        "numerical_contract": "Cache the original per-row loss-after-weight backward at exact float.hex weight; reuse only identical complete common, original token row and runtime binding, and accumulate in original order. No unit-gradient scaling, reduced precision, dropped targets or changed denominators.",
        "resource_contract": "New v037 execution: one worker per GPU, at most four; prefer empty cards, admit stable free >=56 GiB even when shared; own <=56 GiB, live free >=6 GiB. Only own workers can be stopped. No reservation or intervention in other processes.",
        "P2_resampled": False, "original_v036_artifacts_modified": False,
        "automatic_retries": False, "independent_outcomes_read": False,
        "full_inventory_retained": True, "gpu_seconds_cap": None, "worker_seconds_cap": None, "wall_deadline": None}
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    write(root / "postcollection-freeze.json", freeze)
    return plan


def frozen(root):
    root = Path(root).resolve()
    plan = read_json(root / "plan.json")
    if (plan.get("version") != VERSION or plan.get("source") != code_identity()
            or plan["source"].get("code_dirty") is not False or plan.get("source_root") != str(SOURCE)
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != list(GPU_ORDER)
            or plan.get("shared_cache_root") != str(root / "gradient-cache")
            or not plan.get("automatic_execution_authorization")
            or plan.get("P2_resampled") is not False or plan.get("full_inventory_retained") is not True):
        raise ValueError("Use the exact clean independently declared v037 execution")
    validate_optimization_controls(support.checked(plan["optimization_qualification"]))
    _check_references([plan["parent_plan"], plan["parent_freeze"]])
    parent, freeze = verify_parent(plan["parent_root"])
    if (plan["parent_plan"] != reference(Path(plan["parent_root"]) / "plan.json")
            or plan["parent_freeze"] != reference(Path(plan["parent_root"]) / "postcollection-freeze.json")):
        raise ValueError("New execution must bind its actual parent paths")
    if plan.get("imported_B"):
        imported = import_shared_B(plan["parent_root"], plan["imported_B"]["folder"], freeze)
        if imported != plan["imported_B"]:
            raise ValueError("Original completed B evidence changed after import")
    inherited = inherited_source_manifest(parent["source"])
    if (plan["parent_source"] != parent["source"] or plan["inherited_source_files"] != inherited
            or plan["numeric_source_manifest_sha256"] != digest(json_bytes(inherited))
            or plan["inventories"] != parent["inventories"] or plan["actual_inventory"] != freeze["actual_inventory"]
            or read_json(root / "postcollection-freeze.json") != freeze):
        raise ValueError("Inherited numerical files, complete inventory or P2 binding changed")
    return plan, freeze


def available_cards(plan, sample, excluded=()):
    """Prefer empty capacity; sharing never authorizes modifying foreign jobs."""
    if any(sample.get(key, {}).get("returncode") != 0 for key in ("gpus", "processes")):
        return []
    occupied, cards = set(), []
    try:
        for row in csv.reader(io.StringIO(sample["processes"]["stdout"]), strict=True):
            if len(row) != 4:
                return []
            occupied.add(row[0].strip())
        for row in csv.reader(io.StringIO(sample["gpus"]["stdout"]), strict=True):
            index, uuid, name, free, total, utilization = (cell.strip() for cell in row)
            index, free, total, utilization = int(index), float(free), float(total), float(utilization)
            if not all(math.isfinite(v) for v in (free, total, utilization)):
                return []
            if (index in GPU_ORDER and index in plan["gpu_preference"] and index not in excluded and "A100" in name
                    and total >= 81920 and plan["limits"]["minimum_free_gpu_mib"] <= free <= total
                    and 0 <= utilization <= 100):
                cards.append({"index": index, "uuid": uuid, "free_mib": free,
                              "utilization_percent": utilization, "shared": uuid in occupied})
    except (ValueError, TypeError, csv.Error):
        return []
    return sorted(cards, key=lambda c: (c["shared"], plan["gpu_preference"].index(c["index"])))


def live_free_stop_reason(sample, gpu_index):
    if sample.get("gpus", {}).get("returncode") != 0:
        return None  # TelemetryGuard handles failed/stale observations.
    try:
        for row in csv.reader(io.StringIO(sample["gpus"]["stdout"]), strict=True):
            index, _, _, free, _, _ = (cell.strip() for cell in row)
            if int(index) == gpu_index and float(free) < LIMITS["minimum_live_free_gpu_mib"]:
                return "shared_device_free_memory_reserve"
    except (ValueError, TypeError, csv.Error):
        return None
    return None


def worker_env(plan, root, name, gpu):
    env = support.original.worker_env(plan, root, name, gpu)
    env["PYTHONPATH"] = os.pathsep.join([plan["runtime_dependency_path"], str(SOURCE / "src"), str(SOURCE)])
    return env


@contextmanager
def training_progress(owner, output):
    """Observe each numerical call without changing tensors, arguments or RNG.

    A forward and its subsequent backward/bookkeeping each have a bounded task
    interval. The complete window has no aggregate GPU or wall-clock deadline.
    """
    original = owner.learning_logprobs
    had_override = "learning_logprobs" in owner.__dict__
    previous_override = owner.__dict__.get("learning_logprobs")
    count = 0
    def observed(*args, **kwargs):
        nonlocal count
        count += 1
        task(output, f"learning-forward-{count:06d}", "training_step")
        result = original(*args, **kwargs)
        task(output, f"learning-backward-or-bookkeeping-{count:06d}", "training_step")
        return result
    owner.learning_logprobs = observed
    try:
        yield
    finally:
        if had_override:
            owner.learning_logprobs = previous_override
        else:
            del owner.learning_logprobs


def require_actual_update(report, material):
    if (report.get("status") != "updated"
            or report.get("behavior_probability_passed") is not True
            or report.get("actor_optimizer_steps") != 1 or report.get("critic_optimizer_steps") != 1
            or report.get("cache_applied_decisions") != material["admitted_decisions"]
            or report.get("cache_actual_backward_decisions", -1) + report.get("cache_hit_decisions", -1) != material["admitted_decisions"]
            or report.get("backward_decisions_completed") != report.get("cache_actual_backward_decisions")
            or report.get("native_accumulation_exact_checks") != report.get("cache_actual_backward_decisions")
            or report.get("admitted_decisions") != material["admitted_decisions"]
            or report.get("admitted_output_tokens") != material["admitted_own_output_tokens"]
            or report.get("scheduled_slots") != 16 or report.get("changed_actor_elements", 0) <= 0):
        raise ValueError("No complete real actor/critic update: retain the original zero/partial/failed outcome and stop without changing rewards or optimizer settings")


def panel_rows(folder):
    rows = read_json(Path(folder) / "progress.json")
    values = [{key: row.get(key) for key in ("slot_id", "case_id", "sampling_seed", "status", "R", "submitted",
        "record_validity", "training_eligible", "started_at", "ended_at", "assessment", "entry")}
        for row in rows]
    for original, value in zip(rows, values):
        budget = original.get("team_budget", {})
        value["actual_usage"] = {key: budget.get("model", {}).get(key) for key in ("decisions", "attempts", "charged_tokens")}
        value["actual_usage"]["test_runs"] = budget.get("tests", {}).get("used")
    return values


def validate_panel(rows, inventory):
    if (len(rows) != len(inventory)
            or any(any(row.get(key) != expected[key] for key in ("slot_id", "case_id", "sampling_seed"))
                   for row, expected in zip(rows, inventory))
            or any(row.get("training_eligible") is not False for row in rows)):
        raise ValueError("Keep every exact frozen nontraining panel unit")
    return all(row["status"] == "closed" and row["record_validity"] is True
               and type(row["R"]) is int and row["R"] in (0, 1) for row in rows)


def run_worker(run_root, worker, output):
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPU_ORDER)):
        raise ValueError("Exactly one permitted physical GPU from 3, 4, 5, 7 is required")
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.online_training import tensor_tree_digest
    from proworksim.software_learning_v036 import migrate_software_owner, restore_common
    from proworksim.software_learning_v037 import update_software_window
    from proworksim.software_runtime_v036 import collect, window_spec

    root, output = Path(run_root).resolve(), Path(output).resolve()
    plan, freeze = frozen(root)
    allocation = freeze["allocation"]
    parent_root = Path(plan["parent_root"])
    parent_plan = read_json(support.checked(plan["parent_plan"]))
    formal = worker.startswith("formal-")
    key = worker.removeprefix("formal-") if formal else worker.removeprefix("trial-")
    if worker != ("formal-" if formal else "trial-") + key or (key not in METHODS if formal else key not in allocation["candidates"]):
        raise ValueError("Worker is outside the complete frozen candidate inventory")
    if worker == "trial-B" and plan.get("imported_B"):
        raise ValueError("The imported original B must never be rerun")
    if worker != "trial-B" and not (root / "shared-B-cost-review.json").exists():
        raise ValueError("Measure and review the real shared B before further trials")
    if formal and not (root / "selection.json").exists():
        raise ValueError("All paired developer outcomes must close before formal selection")
    output.mkdir(parents=True, exist_ok=False)
    report = {"version": VERSION, "worker": worker, "candidate_id": key, "formal": formal,
        "status": "loading", "started_at": time.time(), "source_before": code_identity(),
        "freeze": reference(root / "postcollection-freeze.json"), "new_actor_steps": 0, "new_critic_steps": 0}
    write(output / "report.json", report)
    owner = None
    try:
        task(output, "load-original-9b", "loading")
        sample = resources()
        write(output / "preload-resources.json", sample)
        if int(os.environ["CUDA_VISIBLE_DEVICES"]) not in [c["index"] for c in available_cards({**plan, "limits": LIMITS}, sample)]:
            raise RuntimeError("Assigned shared A100 free capacity changed before loading")
        refs = parent_plan["parent"]["references"]
        saved = read_json(support.checked(refs["owner"]))
        old_plan = read_json(support.checked(refs["plan"]))
        model_plan = read_json(support.checked(old_plan["prior_model_plan"]))
        owner = DeterministicCandidateActor.from_candidate(model_plan["model"], manifest=support.checked(model_plan["manifest"]),
            profile=model_plan["runtime_profile"], recipe=saved["recipe"], output=output / "resident")
        write(output / "software-critic-migration.json", migrate_software_owner(owner, expected_steps=None))
        task(output, "restore-original-complete-common", "boundary")
        common_path = support.checked(freeze["common"])
        common = read_json(common_path)
        if (common_path.resolve() != (parent_root / support.CANDIDATE / "actual/inherited-common.json").resolve()
                or common["state_tensor_digest"] != allocation["development"]["initial_state_sha256"]
                or common["training_rng_sha256"] != allocation["development"]["training_rng_sha256"]):
            raise ValueError("Frozen initial complete state and training RNG disagree with allocation")
        restored = restore_common(owner, support.checked(common["common"]).parent, window_id=support.SUPPORT_WINDOW)
        if (restored["state_sha256"] != common["state_tensor_digest"]
                or restored["rng_sha256"] != common["training_rng_sha256"]
                or restored["actor_identity"] != common["actor_identity"]
                or (owner.actor_steps, owner.critic_steps) != (3, 3)):
            raise ValueError("Every candidate must restore the same actor, critic, optimizers and RNG")
        write(output / "common-restore.json", restored)
        source = parent_root / support.CANDIDATE / "actual/collection"
        entries, declaration, records = [read_json(source / name) for name in ("entries.json", "declaration.json", "records.json")]
        if support.current_support_gate(entries, declaration, records) != read_json(parent_root / support.CANDIDATE / "actual/support-gate.json"):
            raise ValueError("Actual new-window support changed after its complete freeze")
        material = read_json(parent_root / support.CANDIDATE / "actual/training-material-binding.json")
        composition = (bind_allocation(entries, declaration, records, allocation, read_json(root / "selection.json"), method=key)
                       if formal else bind_candidate(entries, declaration, records, allocation, key))
        task(output, "validate-complete-original-window-" + worker, "boundary")
        update_started = time.time()
        report.update(status="training", update_started_at=update_started)
        write(output / "report.json", report)
        with training_progress(owner, output):
            update = update_software_window(owner, entries, output / "update", declaration=declaration,
                request_evidence_root=source, composition=composition, cache_root=root / "gradient-cache",
                binding={"common_state_sha256": common["state_tensor_digest"],
                    "training_rng_sha256": common["training_rng_sha256"], "actor_identity": common["actor_identity"],
                    "material_sha256": freeze["training_material_binding"]["sha256"],
                    "numeric_source_manifest_sha256": plan["numeric_source_manifest_sha256"]})
        update_ended = time.time()
        report.update(new_actor_steps=update["actor_optimizer_steps"], new_critic_steps=update["critic_optimizer_steps"],
            update=reference(output / "update/report.json"), update_ended_at=update_ended,
            complete_material_update_seconds=update_ended - update_started,
            material_scale={k: material[k] for k in ("original_slot_count", "admitted_decisions", "admitted_input_tokens", "admitted_own_output_tokens", "maximum_actual_sequence_tokens")})
        require_actual_update(update, material)
        report["cache_work"] = {key: update.get(key, 0) for key in ("cache_actual_backward_decisions", "cache_hit_decisions", "cache_applied_decisions", "native_accumulation_exact_checks", "behavior_cache_hits", "actual_behavior_forward_decisions")}
        task(output, "save-updated-state-and-gradient-identity", "boundary")
        gradient = owner.torch.load(output / "update/gradients-before-clip.pt", map_location="cpu", weights_only=False)
        report["gradient_tensor_digests"] = {name: tensor_tree_digest(value, owner.torch) for name, value in gradient.items()}
        del gradient
        checkpoint = owner.save_checkpoint(output / "updated-state")
        report.update(updated_actor_identity=checkpoint["actor_identity"], updated_state=reference(output / "updated-state/checkpoint.json"),
                      common_restored_exactly=True, full_material_consumption_passed=True)
        del entries, declaration, records, composition
        name, usage = ("confirmation", "independent_confirmation") if formal else ("development", "contribution_development")
        report.update(status=name)
        write(output / "report.json", report)
        panel_started = time.time()
        collect(owner, window_spec("v037-" + worker + "-" + name, plan["inventories"][name], usage),
                output / name, output)
        rows = panel_rows(output / name)
        known = validate_panel(rows, plan["inventories"][name])
        write(output / "panel-summary.json", {"usage": usage, "all_known": known, "rows": rows,
            "elapsed_seconds": time.time() - panel_started, "optimizer_updates_during_panel": 0})
        report.update(panel=reference(output / "panel-summary.json"), panel_all_known=known,
                      panel_actor_identity_unchanged=owner.freeze_identity() == checkpoint["actor_identity"])
        if not report["panel_actor_identity_unchanged"]:
            raise ValueError("The post-update panel changed actor parameters")
        if not formal:
            utilities = [r["R"] if r["status"] == "closed" and r["record_validity"] is True else None for r in rows]
            write(output / "development-receipt.json", development_receipt(allocation, key, utilities, provenance="current_model_development"))
        report["status"] = "complete" if known else "incomplete_panel"
    except BaseException as error:
        report.update(status="execution_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps,
                          new_actor_steps=max(0, owner.actor_steps - 3), new_critic_steps=max(0, owner.critic_steps - 3),
                          final_actor_identity=owner._make_identity())
        report.update(ended_at=time.time(), source_after=code_identity())
        write(output / "report.json", report)
    return report


def verified_receipt(root, name, allocation):
    plan = read_json(Path(root) / "plan.json")
    folder = worker_folder(root, name, plan)
    report = read_json(folder / "report.json")
    panel = read_json(support.checked(report["panel"]))
    expected_source = plan["imported_B"]["source"] if name == "trial-B" and plan.get("imported_B") else plan["source"]
    if (report["status"] != "complete" or report["source_before"] != expected_source or report["source_after"] != expected_source
            or report.get("new_actor_steps") != 1 or report.get("new_critic_steps") != 1
            or report.get("full_material_consumption_passed") is not True
            or report.get("common_restored_exactly") is not True or not panel["all_known"]
            or not validate_panel(panel["rows"], plan["inventories"]["development"])):
        raise ValueError("Developer feedback requires the real same-common complete update and every known panel outcome")
    key = name.removeprefix("trial-")
    expected = development_receipt(allocation, key, [r["R"] for r in panel["rows"]], provenance="current_model_development")
    receipt = read_json(folder / "development-receipt.json")
    if receipt != expected:
        raise ValueError("Developer receipt differs from executed paired outcomes")
    return receipt


def shared_B_cost_review(root, freeze):
    root = Path(root)
    plan = read_json(root / "plan.json")
    folder = worker_folder(root, "trial-B", plan)
    report = read_json(folder / "report.json")
    panel = read_json(folder / "panel-summary.json")
    verified_receipt(root, "trial-B", freeze["allocation"])
    state = (plan["imported_B"]["original_worker_state"] if plan.get("imported_B")
             else read_json(root / "p3-supervisor.json")["states"]["trial-B"])
    inventory = freeze["actual_inventory"]
    updates = inventory["unique_trial_updates"] + inventory["formal_updates"]
    per_episode = panel["elapsed_seconds"] / 16
    cost = {"version": VERSION, "shared_B_worker": reference(folder / "report.json"),
        "software_consumption": reference(folder / "update/software-consumption.json"),
        "actual_inventory": inventory, "full_window_updates": updates,
        "online_episodes_including_P2": 16 + inventory["development_episodes"] + inventory["independent_episodes"],
        "measured_B_complete_material_update_seconds": report["complete_material_update_seconds"],
        "measured_B_development_panel_seconds": panel["elapsed_seconds"],
        "measured_B_worker_gpu_seconds": state["elapsed_gpu_seconds"],
        "naive_no_cache_update_seconds_at_B_rate": updates * report["complete_material_update_seconds"],
        "measured_B_cache_work": report.get("cache_work"),
        "B_imported_from_original_execution": bool(plan.get("imported_B")),
        "B_counted_as_new_v037_work": not bool(plan.get("imported_B")),
        "remaining_update_forecast_seconds": None,
        "remaining_new_development_episodes": inventory["development_episodes"] - (16 if plan.get("imported_B") else 0),
        "conditional_development_seconds_at_B_rate": (inventory["development_episodes"] - (16 if plan.get("imported_B") else 0)) * per_episode,
        "conditional_confirmation_seconds_at_B_development_rate": inventory["independent_episodes"] * per_episode,
        "estimate_scope": "The naive no-cache value is a comparison only, not the v037 duration forecast. Actual weighted-gradient misses and hits are separately counted; changed weights can require new backward work. Panel costs retain all frozen episodes.",
        "gpu_seconds_cap": None, "worker_seconds_cap": None, "wall_deadline": None,
        "resource_protections": copy.deepcopy(LIMITS), "full_inventory_retained": True,
        "fairness": "Same one complete-window formal update per method, not equal total search cost. Shared B counted once; no artificial I-P burn or G-raw direction deletion.",
        "automatic_continuation_authorized": True, "independent_outcomes_read": False}
    write(root / "shared-B-cost-review.json", cost)
    return cost


def next_stage(stage, states, root, freeze):
    if any(s["status"] not in TERMINAL for s in states.values()):
        raise ValueError("All current-stage workers and their lossless archives must close")
    if any(s["status"] != "complete" for s in states.values()):
        return "incomplete_execution", []
    allocation = freeze["allocation"]
    if stage == "shared_B":
        shared_B_cost_review(root, freeze)
        return "full_trials", ["trial-" + key for key in allocation["candidates"] if key != "B"]
    if stage == "full_trials":
        receipts = [verified_receipt(root, "trial-" + key, allocation) for key in allocation["candidates"]]
        selection = select_allocation(allocation, receipts)
        write(Path(root) / "selection.json", selection)
        return "formal_and_independent_confirmation", ["formal-" + method for method in METHODS]
    if stage == "formal_and_independent_confirmation":
        return "complete", []
    raise ValueError("Unknown stage")


def archive_worker(root, name):
    from proworksim.software_cold_archive_v036 import archive_closed_directory
    folder = Path(root) / name / "actual"
    subdir = "confirmation" if name.startswith("formal-") else "development"
    manifest = archive_closed_directory(folder / subdir, folder / (subdir + "-original.tar.gz"))
    write(folder / "cold-archive-receipt.json", manifest)
    return {"receipt": reference(folder / "cold-archive-receipt.json"),
            "archive": reference(folder / (subdir + "-original.tar.gz")),
            "scope": "Original closed panel bytes preserved; no support material archived"}


def supervise(root):
    root = Path(root).resolve()
    plan, freeze = frozen(root)
    if (root / "p3-supervisor.json").exists():
        raise FileExistsError("Never retry or append a started P3 inventory")
    summary = {"version": VERSION, "status": "waiting", "stage": "shared_B", "states": {},
        "started_at": time.time(), "observer_pid": os.getpid(), "source": code_identity(),
        "frozen_inventory": freeze["actual_inventory"], "automatic_execution_authorized": True}
    active, logs, guards, stable, archives = {}, {}, {}, {}, {}
    stage_names = ["trial-B"]

    def add(names):
        for name in names:
            summary["states"][name] = {"worker": name, "status": "not_started", "attempted": False}

    def publish():
        summary.update(observed_at=time.time(),
            worker_gpu_seconds=sum(s.get("elapsed_gpu_seconds", 0) for s in summary["states"].values()),
            running_gpu_seconds=sum(time.time() - summary["states"][n]["started_at"] for n in active))
        write(root / "p3-supervisor.json", summary)

    def finish_worker(name, reason, pool):
        process = active.pop(name)
        state = summary["states"][name]
        if process.poll() is None:
            support.continuation._stop_worker(process, state)
        process.wait(timeout=15)
        report = read(root / name / "actual/report.json") or {}
        complete = (process.returncode == 0 and reason is None and report.get("status") == "complete"
                    and report.get("source_before") == report.get("source_after") == plan["source"])
        ended = time.time()
        state.update(ended_at=ended, exit_code=process.returncode, stop_reason=reason,
            status="archiving" if complete else "stopped", elapsed_gpu_seconds=ended - state["started_at"])
        logs.pop(name).close()
        if complete:
            archives[name] = pool.submit(archive_worker, root, name)
        publish()

    add(stage_names)
    if plan.get("imported_B"):
        summary["states"]["trial-B"].update(status="complete", imported=True, attempted=False,
            elapsed_gpu_seconds=0, original_evidence=plan["imported_B"])
    with lock(root), ThreadPoolExecutor(max_workers=1) as archive_pool:
        try:
            while True:
                for name, process in list(active.items()):
                    if process.poll() is not None:
                        finish_worker(name, None if process.returncode == 0 else "worker_exit_error", archive_pool)
                for name, future in list(archives.items()):
                    if future.done():
                        result = future.result()
                        summary["states"][name].update(status="complete", archive=result, archive_ended_at=time.time())
                        del archives[name]
                        publish()
                stage_states = {name: summary["states"][name] for name in stage_names}
                if all(s["status"] in TERMINAL for s in stage_states.values()):
                    publish()
                    summary["stage"], stage_names = next_stage(summary["stage"], stage_states, root, freeze)
                    if not stage_names:
                        summary["status"] = summary["stage"]
                        break
                    add(stage_names)
                size = sum(artifact_bytes(Path(path)) for path in support.dense._artifact_roots([*plan["prior_artifact_roots"], root]))
                free = shutil.disk_usage(root).free
                if size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                    for name in list(active):
                        finish_worker(name, "trajectory_storage_reserve", archive_pool)
                    for name in stage_names:
                        if summary["states"][name]["status"] == "not_started":
                            summary["states"][name].update(status="stopped", stop_reason="trajectory_storage_reserve", elapsed_gpu_seconds=0)
                    summary["status"] = "trajectory_storage_reserve"
                    break
                waiting = [name for name in stage_names if summary["states"][name]["status"] == "not_started"]
                if waiting:
                    sample = resources()
                    with (root / "p3-waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    cards = available_cards({**plan, "limits": LIMITS}, sample, [summary["states"][n]["gpu"] for n in active])
                    now = time.time()
                    stable = {c["index"]: stable.get(c["index"], now) for c in cards}
                    for card in cards:
                        if not waiting or len(active) >= LIMITS["max_parallel_model_instances"]:
                            break
                        if now - stable[card["index"]] < LIMITS["gpu_capacity_stability_seconds"]:
                            continue
                        frozen(root)
                        name = waiting.pop(0)
                        folder = root / name
                        folder.mkdir(exist_ok=False)
                        argv = [sys.executable, "-m", "scripts.software_allocation_v037", "worker", "--run-root", str(root),
                                "--worker", name, "--output", str(folder / "actual")]
                        logs[name] = (folder / "worker.log").open("x")
                        started = time.time()
                        process = subprocess.Popen(argv, cwd=SOURCE,
                            env=worker_env(plan, root, name, card["index"]),
                            stdin=subprocess.DEVNULL, stdout=logs[name], stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        summary["states"][name].update(status="running", attempted=True, gpu=card["index"], gpu_uuid=card["uuid"],
                            pid=process.pid, process_identity=identity, started_at=started, command=argv)
                        active[name] = process
                        guards[name] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        publish()
                if active:
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        futures = {n: pool.submit(target_resources, summary["states"][n]["gpu"], worker_pid=p.pid) for n, p in active.items()}
                        samples = {n: f.result() for n, f in futures.items()}
                    for name, process in list(active.items()):
                        if process.poll() is not None:
                            finish_worker(name, None if process.returncode == 0 else "worker_exit_error", archive_pool)
                            continue
                        state = summary["states"][name]
                        guard = guards[name].observe(samples[name], time.time(), process.pid, state["gpu"], own_memory_limit_mib=LIMITS["own_gpu_memory_mib"])
                        current = read(root / name / "actual/task.json") or {"kind": "loading", "started_at": state["started_at"]}
                        own_rss = rss(process.pid)
                        reason = guard.get("stop_reason") or live_free_stop_reason(samples[name], state["gpu"])
                        cap = LIMITS["task_seconds"].get(current.get("kind"))
                        if current.get("kind") not in LIMITS["task_seconds"]:
                            reason = reason or "unknown_task_kind"
                        elif cap is not None and time.time() - current["started_at"] >= cap:
                            reason = reason or "single_task_budget"
                        elif own_rss > LIMITS["host_rss_per_worker_bytes"]:
                            reason = reason or "host_memory_budget"
                        with (root / name / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": samples[name], "guard": guard, "task": current,
                                "rss_bytes": own_rss, "artifact_bytes": size, "volume_free_bytes": free}) + "\n")
                        if reason:
                            finish_worker(name, reason, archive_pool)
                summary["status"] = "running" if active else "archiving" if archives else "waiting"
                publish()
                time.sleep(LIMITS["poll_seconds"])
        except BaseException as error:
            summary.update(status="interrupted", error={"type": type(error).__name__, "message": str(error)})
            for name in list(active):
                finish_worker(name, "supervisor_interrupted", archive_pool)
            raise
        finally:
            summary["ended_at"] = time.time()
            publish()
    return summary


def results(root):
    root = Path(root)
    plan = read_json(root / "plan.json")
    state = read(root / "p3-supervisor.json")
    freeze = read(root / "postcollection-freeze.json")
    workers = {}
    for name, item in (state or {}).get("states", {}).items():
        folder = worker_folder(root, name, plan)
        report = read(folder / "report.json") or {}
        panel = read(folder / "panel-summary.json")
        live_panel = folder / ("confirmation" if name.startswith("formal-") else "development")
        if panel is None and (live_panel / "progress.json").exists():
            panel = {"rows": panel_rows(live_panel), "all_known": False, "partial": True}
        workers[name] = {"state": item, "report": report, "panel": panel,
                         "update_report": read(folder / "update/report.json"),
                         "imported": bool(name == "trial-B" and plan.get("imported_B"))}
    paired = []
    if state and state["status"] == "complete":
        panels = {method: workers["formal-" + method]["panel"]["rows"] for method in METHODS}
        for index, unit in enumerate(plan["inventories"]["confirmation"]):
            values = {method: panels[method][index]["R"] for method in METHODS}
            paired.append({**unit, "R_by_method": values, "I_minus_B": values["I-P"] - values["B"],
                           "I_minus_G_raw": values["I-P"] - values["G-raw"]})
    byroot = {case: {method: sum(r["R_by_method"][method] for r in paired if r["case_id"] == case)
                    for method in METHODS} for case in dict.fromkeys(r["case_id"] for r in paired)}
    intervals = [support.GpuInterval(s["gpu"], round(s["started_at"] * 1_000_000), round(s["ended_at"] * 1_000_000))
                 for s in (state or {}).get("states", {}).values() if s.get("attempted") and s.get("ended_at") is not None]
    usage = [r["actual_usage"] for worker in workers.values() if not worker["imported"] for r in (worker["panel"] or {}).get("rows", [])
             if all(type(v) is int for v in r.get("actual_usage", {}).values()) and len(r.get("actual_usage", {})) == 4]
    cost = {"closed_P3_worker_gpu_seconds": sum(i.end_us - i.start_us for i in intervals) / 1_000_000,
        "closed_P3_worker_interval_union": support.interval_accounting(intervals, [])["totals"]["worker_union"],
        "running_P3_gpu_seconds": (state or {}).get("running_gpu_seconds", 0),
        "known_sampling_usage_units": len(usage),
        "sampling_usage": {key: sum(row[key] for row in usage) for key in ("decisions", "attempts", "charged_tokens", "test_runs")},
        "queue_and_CPU_archive_excluded_from_GPU_cost": True,
        "full_update_and_panel_intervals_are_nested_not_added_twice": True,
        "gradient_work": {key: sum((worker["update_report"] or {}).get(key, 0) for worker in workers.values() if not worker["imported"])
            for key in ("cache_actual_backward_decisions", "cache_hit_decisions", "cache_applied_decisions", "native_accumulation_exact_checks", "behavior_cache_hits", "actual_behavior_forward_decisions")},
        "cache_file_bytes": artifact_bytes(root / "gradient-cache") if (root / "gradient-cache").exists() else 0,
        "old_v036_interrupted_work_counted_as_new": False,
        "imported_B": plan.get("imported_B"),
        "new_v037_optimizer_steps": {"actor": sum(worker["report"].get("new_actor_steps", 0) for worker in workers.values() if not worker["imported"]),
            "critic": sum(worker["report"].get("new_critic_steps", 0) for worker in workers.values() if not worker["imported"])}}
    trial_reports = [worker["report"] for name, worker in workers.items() if name.startswith("trial-")
                     and "gradient_tensor_digests" in worker["report"]]
    complete_geometry = bool(freeze and len(trial_reports) == len(freeze["allocation"]["candidates"]))
    actor_gradients = sorted({row["gradient_tensor_digests"]["actor"] for row in trial_reports})
    geometry = {"measured_trial_gradient_count": len(trial_reports), "all_frozen_trial_gradients_available": complete_geometry,
        "distinct_actor_gradient_tensor_digests": actor_gradients,
        "all_trial_actor_gradients_equal": len(actor_gradients) == 1 if complete_geometry else None,
        "scope": "Exact stored pre-clip gradient tensor equality, not a utility or causal-contribution estimate; incomplete directions remain unmeasured."}
    return {"version": VERSION, "status": state["status"] if state else "not_started", "source": plan["source"], "imported_B": plan.get("imported_B"),
        "allowed_physical_gpus": plan["gpu_preference"],
        "support": {"reused_without_sampling": True, "parent_root": plan["parent_root"], "parent_freeze": plan["parent_freeze"]}, "freeze": freeze, "shared_B_cost_review": read(root / "shared-B-cost-review.json"),
        "selection": read(root / "selection.json"), "workers": workers, "cost": cost, "update_geometry": geometry,
        "independent_paired_units": paired,
        "independent_successes_by_root_out_of_four": byroot,
        "I_minus_B": sum(r["I_minus_B"] for r in paired) / 16 if paired else None,
        "I_minus_G_raw": sum(r["I_minus_G_raw"] for r in paired) / 16 if paired else None,
        "scope": "Finite two-class integration-route mechanism comparison. Same formal full-window update budget, unequal complete search cost. Four roots per purpose do not establish population effects, I-S, I-J or stable contribution precision. Unknown outcomes remain unknown."}


def report(root, destination):
    value = results(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    write(destination / "software-allocation-v037.json", value)
    lines = ["# v0.37 原冻结清单的精确加权梯度复用执行", "",
        f"状态：`{value['status']}`；源码：`{value['source']['code_commit']}`。", "",
        f"允许的物理GPU：`{value['allowed_physical_gpus']}`；没有合格显存时等待，不转用其他卡。", "",
        "复用v036已经闭合的16槽支持和完整冻结清单，不重采P2。若共同B来自原运行，保留原记录并单列旧GPU成本，且不将其计作新反向或新优化器步；其原始逐行梯度未保存，不能据此声称新缓存已填充。每个试训及正式三分支均恢复相同完整common；只复用同一原行、同一精确权重和同一完整状态下的原始反向结果。实际反向次数与缓存应用次数分别记录。开发和确认各4个root×4个seed，原始16槽、失败／unmapped残余及本人分母保持。", "",
        "| worker | 状态 | actor/critic新增步 | 更新秒 | 实际反向/命中/应用 | 配对面板已知 |", "|---|---|---|---:|---|---|"]
    for name, row in value["workers"].items():
        r = row["report"]
        origin = "原v036导入" if row["imported"] else "新v037"
        lines.append(f"| {name} | {origin}/{row['state']['status']} | {r.get('new_actor_steps')}/{r.get('new_critic_steps')} | {r.get('complete_material_update_seconds')} | {r.get('cache_work')} | {r.get('panel_all_known')} |")
    lines += ["", "独立确认逐root（各方法分母4）：", "", "| root | B | G-raw | I-P |", "|---|---:|---:|---:|"]
    for case, scores in value["independent_successes_by_root_out_of_four"].items():
        lines.append(f"| {case} | {scores['B']} | {scores['G-raw']} | {scores['I-P']} |")
    lines += ["", f"独立局部平均差：I−B=`{value['I_minus_B']}`，I−G-raw=`{value['I_minus_G_raw']}`。null表示未测／未闭合，不能填0。", "",
        "D=16仍是有限机制面板，不保证Contribution精度。未检出方向差不能证明真实C=0；若q仅因先验／覆盖锚而变，不能称为发现高价值经历。正式更新预算相同不等于端到端探测资源相同，G-raw完整方向不删除。", "",
        "闭合开发／确认目录通过逐文件SHA复核后无损冷归档，原相对路径与字节均可恢复；原始支持材料保持可读。新执行单独声明共享卡准入：空闲至少56GiB、自身占用不超过56GiB、运行期间设备空闲至少6GiB；优先空卡，最多4卡。仅停止本执行自己的worker。64GiB RSS、128GiB产物及20GiB磁盘余量保护保持；缓存等待不受单次反向900秒限制，无累计GPU／worker／统一墙钟上限。", ""]
    (destination / "software-allocation-v037.md").write_text("\n".join(lines))
    return value


def process_binding(pid):
    """Read Linux process identity without exposing its environment."""
    identity = worker_identity(pid)
    if identity.get("alive") is not True or not identity.get("available"):
        raise ValueError("The declared parent process is no longer alive")
    base = Path("/proc") / str(pid)
    fields = (base / "stat").read_text().rsplit(")", 1)[1].split()
    return {"identity": identity, "parent_pid": int(fields[1]),
            "command": [part.decode() for part in (base / "cmdline").read_bytes().split(b"\0") if part],
            "cwd": str((base / "cwd").resolve())}


def _is_original_command(binding, parent_root, parent_plan, module, mode):
    command = binding["command"]
    expected = ["-m", module, mode]
    return (binding["cwd"] == parent_plan["source_root"]
        and any(command[i:i + 3] == expected for i in range(len(command) - 2))
        and any(command[i:i + 2] == ["--run-root", str(parent_root)] for i in range(len(command) - 1)))


def parent_observer_binding(parent_root, parent_plan, summary):
    if summary.get("source") != parent_plan["source"]:
        raise ValueError("Only the original frozen v036 supervisor can be handed off")
    observer = process_binding(summary["observer_pid"])
    if not _is_original_command(observer, parent_root, parent_plan,
                                "scripts.software_allocation_v036", "supervise"):
        raise ValueError("Parent observer command or source path differs")
    finisher = process_binding(observer["parent_pid"])
    if not _is_original_command(finisher, parent_root, parent_plan,
                                "scripts.software_support_v036", "finish"):
        raise ValueError("Parent finisher command or source path differs")
    return {"observer": observer, "finisher": finisher}


def stop_verified_parent_observer(binding):
    """Signal only the original bound supervisor; it shuts down its own children."""
    expected = binding["observer"]
    pid = expected["identity"]["pid"]
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError("Race-safe pidfd signaling is required for automatic handoff")
    descriptor = os.pidfd_open(pid)
    try:
        current = process_binding(pid)
        if (current["identity"]["start_ticks"] != expected["identity"]["start_ticks"]
                or current["command"] != expected["command"] or current["cwd"] != expected["cwd"]):
            raise ValueError("Parent process identity changed; no signal was sent")
        signal.pidfd_send_signal(descriptor, signal.SIGTERM)
    finally:
        os.close(descriptor)


def _bound_process_alive(binding):
    identity = worker_identity(binding["identity"]["pid"])
    return (identity.get("alive") is True
            and identity.get("start_ticks") == binding["identity"]["start_ticks"])


def handoff(parent_root, root, report_repo, *, qualification=None):
    """Wait for the running B, then take over only its still-unexecuted inventory."""
    parent_root, root, report_repo = (Path(path).resolve() for path in (parent_root, root, report_repo))
    control = root.parent / (root.name + "-handoff")
    if root.exists() or control.exists():
        raise FileExistsError("Never retry an already declared handoff or allocation run")
    qualification = optimization_qualification_path(root, qualification)
    validate_optimization_controls(qualification)
    parent, freeze = verify_parent(parent_root)
    inherited_source_manifest(parent["source"])
    summary = read_json(parent_root / "p3-supervisor.json")
    baseline = summary.get("states", {}).get("trial-B", {})
    if (summary.get("stage") != "shared_B" or summary.get("status") not in {"running", "archiving", "waiting"}
            or baseline.get("status") not in {"running", "archiving"}):
        raise ValueError("Declare the handoff while the original shared B is still running or archiving")
    processes = parent_observer_binding(parent_root, parent, summary)
    source = code_identity()
    if source.get("code_dirty") is not False:
        raise ValueError("Handoff requires the complete committed new execution source")
    request = {"version": VERSION, "created_at": time.time(), "source": source,
        "optimization_qualification": reference(qualification),
        "parent_root": str(parent_root), "new_root": str(root), "report_repo": str(report_repo),
        "parent_plan": reference(parent_root / "plan.json"),
        "parent_freeze": reference(parent_root / "postcollection-freeze.json"),
        "parent_source": parent["source"], "parent_processes": processes,
        "initial_parent_snapshot": copy.deepcopy(summary),
        "execution_sources": {name: reference(SOURCE / name) for name in (
            "scripts/software_allocation_v037.py", "src/proworksim/software_learning_v037.py")},
        "authorization": "User requested runtime optimization while preserving the already authorized complete frozen experiment. Finish the current original B, signal only its identity-verified supervisor, preserve old reports, then reuse B and execute all remaining directions.",
        "signal_before_B_complete": False, "foreign_process_intervention": False,
        "sampling_or_model_calls_while_waiting": 0, "automatic_retries": False,
        "poll_seconds": min(LIMITS["poll_seconds"], 60)}
    control.mkdir(parents=True, exist_ok=False)
    write(control / "request.json", request)
    state = {"version": VERSION, "status": "waiting_for_original_B", "started_at": time.time(),
             "observer_pid": os.getpid(), "request": reference(control / "request.json"), "parent_signal_sent": False}
    with lock(control):
        try:
            while True:
                summary = read_json(parent_root / "p3-supervisor.json")
                baseline = summary.get("states", {}).get("trial-B", {})
                state.update(observed_at=time.time(), parent_status=summary.get("status"),
                    parent_stage=summary.get("stage"), B_status=baseline.get("status"),
                    B_update=read(parent_root / "trial-B/actual/update/report.json"))
                write(control / "status.json", state)
                if baseline.get("status") == "complete":
                    # Validate the original complete numerical update before stopping its supervisor.
                    imported = import_shared_B(parent_root, parent_root / "trial-B/actual", freeze)
                    state["completed_original_B"] = imported
                    _check_references(request["execution_sources"])
                    validate_optimization_controls(support.checked(request["optimization_qualification"]))
                    if code_identity() != request["source"]:
                        raise ValueError("New execution source changed; do not stop the original supervisor")
                    current = parent_observer_binding(parent_root, parent, summary)
                    if (current["observer"]["identity"]["start_ticks"] != processes["observer"]["identity"]["start_ticks"]
                            or current["observer"]["identity"]["pid"] != processes["observer"]["identity"]["pid"]):
                        raise ValueError("Original supervisor was replaced; do not signal a replacement")
                    state.update(status="stopping_original_supervisor_after_B", signal_requested_at=time.time())
                    write(control / "status.json", state)
                    stop_verified_parent_observer(processes)
                    state.update(parent_signal_sent=True, signal_sent_at=time.time(), status="waiting_for_original_reports")
                    write(control / "status.json", state)
                    break
                if (baseline.get("status") == "stopped" or summary.get("status") in {
                        "interrupted", "incomplete_execution", "trajectory_storage_reserve", "complete"}
                        or not _bound_process_alive(processes["observer"])):
                    state.update(status="parent_stopped_before_complete_B", ended_at=time.time())
                    write(control / "status.json", state)
                    return state
                time.sleep(request["poll_seconds"])
            original_finish_path = parent_root.parent / (parent_root.name + "-finish.json")
            while _bound_process_alive(processes["observer"]) or _bound_process_alive(processes["finisher"]):
                state.update(observed_at=time.time(), original_finish_status=(read(original_finish_path) or {}).get("status"))
                write(control / "status.json", state)
                time.sleep(request["poll_seconds"])
            old_finish = read(original_finish_path) or {}
            if not old_finish.get("ended_at") or old_finish.get("P3_reporting_error"):
                raise RuntimeError("Original finisher did not durably close its reports; retain handoff without launching")
            state.update(original_finish=reference(original_finish_path),
                         original_terminal_supervisor=reference(parent_root / "p3-supervisor.json"))
            _check_references(request["execution_sources"])
            validate_optimization_controls(support.checked(request["optimization_qualification"]))
            if code_identity()["source_tree_sha256"] != source["source_tree_sha256"]:
                raise ValueError("New execution source changed while awaiting original B")
            state.update(status="preparing_new_execution", observed_at=time.time())
            write(control / "status.json", state)
            prepare(parent_root, root, imported_B=parent_root / "trial-B/actual", qualification=qualification)
            write(root / "handoff.json", {"request": reference(control / "request.json"),
                "original_finish": state["original_finish"], "original_terminal_supervisor": state["original_terminal_supervisor"],
                "original_B_preserved": True, "old_partial_non_B_workers_counted_as_new": False})
            state["new_execution"] = finish(root, report_repo)
            state["status"] = state["new_execution"]["status"]
        except BaseException as error:
            state.update(status="handoff_error", error={"type": type(error).__name__, "message": str(error)})
            raise
        finally:
            state["ended_at"] = time.time()
            write(control / "status.json", state)
    return state


def finish(root, report_repo):
    """Run the declared successor once, then durably report and publish its outcome."""
    root, report_repo = Path(root).resolve(), Path(report_repo).resolve()
    state = {"version": VERSION, "status": "supervising", "started_at": time.time()}
    path = root / "finish.json"
    write(path, state)
    original_error = None
    try:
        value = supervise(root)
        state["status"] = value["status"]
    except BaseException as error:
        original_error = error
        state.update(status="execution_error", error={"type": type(error).__name__, "message": str(error)})
    finally:
        try:
            value = report(root, report_repo / "docs/experiments")
            state["report_status"] = value["status"]
            state["publication"] = support.publish_report_paths(report_repo, REPORT_PATHS,
                "docs: archive v037 exact weighted-gradient allocation execution")
        except BaseException as error:
            state["reporting_error"] = {"type": type(error).__name__, "message": str(error)}
            if original_error is None:
                state["status"] = "reporting_error"
        state["ended_at"] = time.time()
        write(path, state)
    if original_error is not None:
        raise original_error
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "worker", "supervise", "report", "finish", "handoff"))
    parser.add_argument("--parent-root", type=Path)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--imported-B", dest="imported_B", type=Path)
    parser.add_argument("--report-repo", type=Path)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--worker")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt("v037 P3 received signal " + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    if args.mode == "handoff":
        if args.parent_root is None or args.report_repo is None:
            parser.error("handoff requires --parent-root and --report-repo")
        value = handoff(args.parent_root, args.run_root, args.report_repo, qualification=args.qualification)
    elif args.mode == "prepare":
        if args.parent_root is None:
            parser.error("prepare requires --parent-root")
        value = prepare(args.parent_root, args.run_root, imported_B=args.imported_B, qualification=args.qualification)
    elif args.mode == "finish":
        if args.report_repo is None:
            parser.error("finish requires --report-repo")
        value = finish(args.run_root, args.report_repo)
    elif args.mode == "worker":
        if not args.worker or args.output is None:
            parser.error("worker requires --worker and --output")
        value = run_worker(args.run_root, args.worker, args.output)
    elif args.mode == "supervise":
        value = supervise(args.run_root)
    else:
        if args.output is None:
            parser.error("report requires --output")
        value = report(args.run_root, args.output)
    print(json.dumps({"version": VERSION, "status": value["status"]}))


if __name__ == "__main__":
    main()
