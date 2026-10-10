"""Sixteen paired frozen organization episodes: evidence layout and team framing.

No training, contribution selection, old-queue successor or automatic retry.
The first root/seed block gates the remaining blocks on mechanism evidence. Within each
episode all logical members use one resident actor and sequential SDK calls.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import io
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
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.software_organization_tasks_v040 import CASE_IDS, build_case, source_partition
from proworksim.software_organization_v042 import CONDITIONS, case_spec
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_support_v036 as support
from scripts.software_allocation_v037 import available_cards, live_free_stop_reason
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write
from scripts.software_development_v028 import task

VERSION = "software-organization-execution-v0.43"
checked = support.checked
SOURCE = Path(__file__).resolve().parents[1]
GPU_ORDER = (3, 4, 5, 7)
SEEDS = (202610100401, 202610100402)
FIRST_BLOCK = "block-r1-s0"
WORKERS = tuple(f"block-r{r}-s{s}" for r in range(2) for s in range(2))
LIMITS = {"max_new_episodes": 16, "max_parallel_model_instances": 4,
    "max_new_actor_steps": 0, "max_new_critic_steps": 0, "max_new_backward_calls": 0,
    "minimum_free_gpu_mib": 56 * 1024, "own_gpu_memory_mib": 56 * 1024,
    "minimum_live_free_gpu_mib": 6 * 1024, "gpu_capacity_stability_seconds": 60,
    "host_rss_per_worker_bytes": 64 * 1024**3, "artifact_bytes": 128 * 1024**3,
    "minimum_volume_free_bytes": 20 * 1024**3,
    "task_seconds": {"loading": 900, "episode": 2400, "boundary": 600},
    "telemetry_grace_seconds": 120, "poll_seconds": 5}
REPORT_PATHS = ["docs/experiments/software-organization-v043.md", "docs/experiments/software-organization-v043.json"]
SDK_POLICY_HOOK = "src/proworksim/harness_sdk.py"
CONTROL_SOURCES = ("scripts/software_organization_v043.py", SDK_POLICY_HOOK,
    "src/proworksim/harness_policy_v040.py", "src/proworksim/software_organization_tasks_v040.py",
    "src/proworksim/software_organization_v040.py", "src/proworksim/software_organization_v042.py",
    "src/proworksim/software_organization_runtime_v042.py",
    "scripts/measure_organization_work_v040.py", "tests/test_harness_policy_v040.py",
    "tests/test_software_organization_tasks_v040.py", "tests/test_software_organization_v042.py",
    "tests/test_software_organization_runtime_v042.py", "tests/test_organization_work_v040.py",
    "tests/test_software_organization_execution_v043.py",
    "scripts/software_organization_admission_v043.py", "tests/test_software_organization_admission_v043.py", "tests/fixtures/v040_original_work_done.json",
    "src/proworksim/software_context_v042.py", "src/proworksim/software_context_replay_v042.py",
    "src/proworksim/software_context_v041.py", "src/proworksim/software_context_replay_v041.py",
    "scripts/software_context_replay_v041.py",
    "scripts/software_context_replay_v042.py",
    "scripts/software_feedback_qualification_v042.py", "scripts/measure_organization_feedback_v042.py",
    "tests/test_software_context_v042.py", "tests/test_software_context_replay_v042.py",
    "tests/test_organization_feedback_v042.py",
    "tests/test_software_feedback_qualification_v042.py")


def assignments():
    result = {}
    for r, case_id in enumerate(CASE_IDS):
        for s, seed in enumerate(SEEDS):
            shift = (2 * r + s + 1) % 4
            first = f"member_{1 + (r + s + 1) % 2:03d}"
            owner = f"member_{1 + (r + 1) % 2:03d}"
            result[f"block-r{r}-s{s}"] = [
                {"slot_id": f"org43-r{r}-s{s}-{condition}", "case_id": case_id,
                 "root_family": "handoff_development", "condition": condition,
                 "information_condition": "shared" if condition[0] == "S" else "split",
                 "framing_condition": "base" if condition[1] == "B" else "team",
                 "sampling_seed": seed, "first_member": first, "diagnostic_a_owner": owner,
                 "balance_scope": "Same first member and allocation plan within each four-condition block; shared receives both reports."}
                for condition in CONDITIONS[shift:] + CONDITIONS[:shift]]
    return result


def source_files():
    names = [*CONTROL_SOURCES,
             *[str(path.relative_to(SOURCE)) for path in sorted((SOURCE / "examples/software-organization-v040").rglob("*"))
               if path.is_file() and "__pycache__" not in path.parts]]
    return {name: digest((SOURCE / name).read_bytes()) for name in names}


def inherited_source_manifest(parent_source):
    """Preserve all old Python bytes except one explicit non-numerical SDK hook.

    Historical frozen checkouts retain their original behavior. The new worker
    opts into its own error policy; no learning/inference arithmetic changes.
    """
    if parent_source.get("code_dirty") is not False:
        raise ValueError("Require the original clean complete-common provenance")
    archive = subprocess.check_output(["git", "archive", parent_source["code_commit"], "src", "scripts"], cwd=SOURCE)
    historical = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        for member in stream.getmembers():
            if member.isfile() and member.name.endswith(".py"):
                historical[member.name] = stream.extractfile(member).read()
    old_source_hash = hashlib.sha256()
    rows, changes = {}, {}
    for name, old in sorted(historical.items()):
        if name.startswith("src/"):
            old_source_hash.update(name.encode())
            old_source_hash.update(old)
        current = (SOURCE / name).read_bytes()
        before = {"sha256": digest(old), "bytes": len(old)}
        after = {"sha256": digest(current), "bytes": len(current)}
        if before != after and name != SDK_POLICY_HOOK:
            raise ValueError("An undeclared inherited source changed: " + name)
        rows[name] = {"historical": before, "current": after, "unchanged": before == after}
        if before != after:
            changes[name] = rows[name]
    if old_source_hash.hexdigest() != parent_source["source_tree_sha256"]:
        raise ValueError("Historical archive differs from original source identity")
    if set(changes) != {SDK_POLICY_HOOK}:
        raise ValueError("Expected exactly the declared SDK policy extension")
    return {"files": rows, "unchanged_count": sum(r["unchanged"] for r in rows.values()),
            "declared_changes": changes, "scope": "Only a protected SDK unknown-name hook; legacy default behavior unchanged and numerical sources byte-identical."}


def qualify(destination, admission):
    """New admission policy controls only; reuse exact bound v042 CPU evidence."""
    from scripts.software_organization_admission_v043 import validate_admission
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    admitted = validate_admission(admission, source_root=SOURCE)
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": ""}
    tests = [name for name in CONTROL_SOURCES if name.startswith("tests/") and name.endswith("_v043.py")]
    commands = [[sys.executable, "-m", "pytest", "-q", *tests,
                 "--basetemp", str(destination / "pytest-tmp")],
                [str(SOURCE / ".venv/bin/python"), "-m", "ruff", "check", "src", "tests", "scripts"]]
    receipts = []
    for i, argv in enumerate(commands):
        started = time.time()
        with (destination / f"check-{i}.log").open("x") as stream:
            result = subprocess.run(argv, cwd=SOURCE, env=env, stdout=stream, stderr=subprocess.STDOUT)
        receipts.append({"command": argv, "exit_code": result.returncode,
            "elapsed_seconds": time.time() - started, "log": reference(destination / f"check-{i}.log")})
    value = {"version": VERSION, "kind": "layered_admission_and_finite_policy_controls",
        "passed": all(r["exit_code"] == 0 for r in receipts) and admitted["passed"],
        "layered_admission": reference(admission), "source_files": source_files(),
        "checks": receipts, "new_model_calls": 0, "new_backward_calls": 0,
        "scope": "Reuse unchanged v042 native-input, exact-page and permission evidence; only new admission/orchestration controls are rerun. Old passed=false remains unchanged; 1024-token protected margin remains a risk diagnostic."}
    write(destination / "qualification.json", value)
    return value


def assess_first_block(root, plan, states):
    """Check execution evidence only; never select by R, message or birth counts."""
    from scripts.measure_organization_feedback_v042 import first_block_gate
    paths = [Path(root) / FIRST_BLOCK / "actual/episodes" / unit["slot_id"] / "feedback-loop.json"
             for unit in plan["assignments"][FIRST_BLOCK]]
    measurements = [read(path) for path in paths]
    value = first_block_gate(measurements)
    if states[FIRST_BLOCK]["status"] != "complete":
        value = {**value, "passed": False,
                 "reasons": [*value.get("reasons", []), "first_block_execution_incomplete"]}
    return {**value, "first_block": FIRST_BLOCK, "checked_at": time.time(),
            "measurements": [reference(path) if path.exists() else None for path in paths],
            "scope": "Mechanism-only gate: does not condition on reward, messaging, births, or collaboration success."}


def require_worker_release(root, worker, plan):
    if worker == FIRST_BLOCK:
        return
    gate = read(Path(root) / "first-block-gate.json")
    state = read(Path(root) / "supervisor.json") or {}
    if (not gate or gate.get("passed") is not True or gate.get("first_block") != FIRST_BLOCK
            or state.get("states", {}).get(FIRST_BLOCK, {}).get("status") != "complete"):
        raise ValueError("Remaining blocks require the completed first-block mechanism gate")
    for ref in gate.get("measurements", []):
        checked(ref)
    current = assess_first_block(root, plan, state["states"])
    if current["passed"] is not True or current["measurements"] != gate.get("measurements"):
        raise ValueError("First-block gate evidence changed or is incomplete")


def eligible_workers(states, gate):
    waiting = [name for name in WORKERS if states[name]["status"] == "not_started"]
    if FIRST_BLOCK in waiting:
        return [FIRST_BLOCK]
    return waiting if gate and gate.get("passed") is True else []


def validate_qualification(path):
    from scripts.software_organization_admission_v043 import validate_admission
    value = read_json(path)
    if (value.get("version") != VERSION or value.get("kind") != "layered_admission_and_finite_policy_controls"
            or value.get("passed") is not True or not value.get("checks")
            or any(r["exit_code"] != 0 for r in value["checks"])
            or value.get("source_files") != source_files()):
        raise ValueError("Require passed new layered-admission controls bound to the frozen implementation")
    for row in value["checks"]:
        checked(row["log"])
    validate_admission(checked(value["layered_admission"]), source_root=SOURCE)
    return value


def prepare(data_root, root, qualification):
    data_root, root = Path(data_root).resolve(), Path(root).resolve()
    if root.exists():
        raise FileExistsError("Use a fresh run; no automatic retry or old inventory reuse")
    validate_qualification(qualification)
    parent_root = data_root / "runs/software-support-v036"
    parent = read_json(parent_root / "plan.json")
    report_path = parent_root / support.CANDIDATE / "actual/report.json"
    prior = read_json(report_path)
    common_path = parent_root / support.CANDIDATE / "actual/inherited-common.json"
    common = read_json(common_path)
    checkpoint = read_json(checked(common["common"]))
    checked(checkpoint["state"])
    if (prior.get("status") != "complete" or prior.get("common_restored_exactly") is not True
            or prior.get("source_before") != parent["source"] or prior.get("source_after") != parent["source"]
            or any(common.get(key) != 3 for key in ("actor_steps", "critic_steps"))
            or checkpoint["actor_identity"] != common["actor_identity"]
            or checkpoint["state_tensor_digest"] != common["state_tensor_digest"]):
        raise ValueError("Require the trusted original pre-B 3/3 complete common")
    inherited = inherited_source_manifest(parent["source"])
    audit_path = SOURCE / "docs/reference/audit-v042-next-v043.md"
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Commit the complete implementation and prior audit before prepare")
    plan = {"version": VERSION, "purpose": "organization_development", "created_at": time.time(),
        "source": source, "source_root": str(SOURCE), "data_root": str(data_root),
        "authorization": "2026-10-10 user explicitly requested implementing the v042 audit and conducting subsequent experiments. This authorizes new v043 layered admission and a catalog four-condition model block, followed conditionally by the other 12 slots. Preserve the entire v042 presentation and original passed=false records; the 1024-token protected margin becomes diagnostic only, while source/information/permission/native-selected hard capacity remain required. Physical GPUs 3,4,5,7 only; no learning.",
        "qualification": reference(qualification), "prior_audit": reference(audit_path),
        "parent_plan": reference(parent_root / "plan.json"), "parent_report": reference(report_path),
        "model_references": copy.deepcopy(parent["parent"]["references"]), "common": reference(common_path),
        "expected_actor_identity": common["actor_identity"], "expected_state_sha256": common["state_tensor_digest"],
        "inherited_source_files": inherited, "assignments": assignments(),
        "stage_rule": "Reuse the exactly bound v042 32 copied-prefix and 32 complete-route evidence: source, information/permission and P_selected<=14336 are required; retain every P_protected 1024-margin deficit as diagnostic only. New layered admission authorizes catalog block-r1-s0 (PT,SB,ST,PB) first within the 16, then three remaining blocks only after actual mechanism evidence passes. Hard context preventing feedback, source/page/version/permission/integrity faults or incomplete evidence stop unstarted slots. Do not gate on protected margin, R, messages, page count, complete reading or births; no hot changes or resampling.",
        "cases": {worker: [case_spec(u["case_id"], condition=u["condition"], first_member=u["first_member"], diagnostic_a_owner=u["diagnostic_a_owner"]) for u in units] for worker, units in assignments().items()},
        "source_partition": source_partition(),
        "business_bindings": {c: build_case(c)["initial_binding"] for c in CASE_IDS},
        "gpu_preference": list(GPU_ORDER), "limits": copy.deepcopy(LIMITS),
        "runtime_dependency_path": parent["runtime_dependency_path"],
        "prior_artifact_roots": support.dense._artifact_roots([*parent["prior_artifact_roots"], parent_root,
            data_root / "runs/software-organization-v038", data_root / "runs/software-organization-v039",
            data_root / "runs/software-organization-v039-recovery", data_root / "runs/software-organization-v040", data_root / "runs/v041-controls", data_root / "runs/v042-controls"]),
        "automatic_retries": False, "automatic_successors": [], "training_eligible": False,
        "independent_confirmation_eligible": False, "shared_gpu_capacity_allowed": True,
        "gpu_seconds_cap": None, "worker_seconds_cap": None, "wall_deadline": None,
        "old_training_queues_remain_paused": True,
        "sampling": "Same inherited actor recipe/profile; reseed once per episode, never on member birth.",
        "scheduling": "First block alone; remaining three root/seed blocks run in parallel only after the predeclared mechanism gate passes. Four conditions per resident block and sequential member calls within each episode.",
        "external_intervention": None,
        "feedback_protocol": {"kind": "directory-plus-exact-v040-visible-test-pages",
            "page_unicode_characters": 3072, "read_tool": "read_test_result", "owner_only": True,
            "complete_read_required_for_submission": False, "new_test_execution_on_read": False,
            "protected_capacity_margin_tokens": 1024, "margin_applies_to": "P_protected risk diagnostic only; not admission or model stopping",
            "model_visible_gamma": "unchanged v042"},
        "seed_reuse": "202610100401/202610100402 were never consumed by a model in v041/v042; re-registered for org43 IDs and new output directories under unchanged v042 Gamma and new v043 admission. All org41/org42 slots remain unstarted.",
        "initial_evidence": "Two actual public preparation diagnostics at the frozen initial branch. Shared/split changes initial observation placement only, not code, tools or recheck permissions. Preparation is never member work.",
        "analysis": "All 16 retained including no communication/recruitment, no submission, ordinary rejected actions, process violations and technical unknowns. Compare four-condition blocks; cross-member use is a separate conservative diagnostic, not causal credit or training support."}
    plan["plan_sha256"] = digest(json_bytes(plan))
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    plan = read_json(Path(root) / "plan.json")
    if (plan.get("version") != VERSION
            or plan.get("plan_sha256") != digest(json_bytes({k: v for k, v in plan.items() if k != "plan_sha256"}))
            or plan.get("source") != code_identity() or plan.get("assignments") != assignments()
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != list(GPU_ORDER)
            or plan.get("automatic_successors") != [] or plan.get("training_eligible") is not False):
        raise ValueError("The frozen organization inventory, implementation or resource contract changed")
    validate_qualification(checked(plan["qualification"]))
    for key in ("common", "parent_plan", "parent_report", "prior_audit"):
        checked(plan[key])
    return plan


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


def run_worker(root, worker, output):
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.software_learning_v036 import migrate_software_owner, restore_common
    from proworksim.software_organization_runtime_v042 import collect_episode
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
            task(output, unit["slot_id"] + "-environment-prepare", "boundary")
            folder = output / "episodes" / unit["slot_id"]
            case = case_spec(unit["case_id"], condition=unit["condition"], first_member=unit["first_member"],
                             diagnostic_a_owner=unit["diagnostic_a_owner"])
            prepared = build_software_collaboration_case(case, folder / "prepared")
            task(output, unit["slot_id"], "episode")
            row = collect_episode(owner, prepared, folder, sampling_seed=unit["sampling_seed"], slot_id=unit["slot_id"])
            task(output, unit["slot_id"] + "-evidence", "boundary")
            if row["status"] == "closed":
                from scripts.measure_organization_work_v040 import measure_episode
                write(folder / "work-use.json", measure_episode(folder))
            from scripts.measure_organization_feedback_v042 import measure_episode as measure_feedback
            write(folder / "feedback-loop.json", measure_feedback(folder))
            rows.append({**unit, **row})
            write(output / "progress.json", rows)
            write(output / "report.json", report)
            if row["status"] != "closed" or type(row["R"]) is not int:
                report["status"] = "technical_unknown"
                break
        else:
            report["status"] = "complete"
        task(output, "final-frozen-state-boundary", "boundary")
    except BaseException as error:
        report.update(status="execution_error", error={"type": type(error).__name__, "message": str(error)})
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
                if (summary["states"][FIRST_BLOCK]["status"] in {"complete", "stopped"}
                        and "first_block_gate" not in summary):
                    gate = assess_first_block(root, plan, summary["states"])
                    write(root / "first-block-gate.json", gate)
                    summary["first_block_gate"] = gate
                    if not gate["passed"]:
                        for state in summary["states"].values():
                            if state["status"] == "not_started":
                                state.update(status="stopped", stop_reason="first_block_mechanism_gate",
                                             elapsed_gpu_seconds=0)
                        summary["status"] = "stopped_by_first_block_gate"
                        break
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
                        name = waiting.pop(0)
                        folder = root / name
                        folder.mkdir(exist_ok=False)
                        argv = [sys.executable, "-m", "scripts.software_organization_v043", "worker",
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
                    with ThreadPoolExecutor(max_workers=4) as pool:
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


def known(row):
    return row.get("status") == "closed" and type(row.get("R")) is int and row["R"] in (0, 1)


def block_contrasts(group):
    values = {c: group[c]["R"] if known(group[c]) else None for c in CONDITIONS}

    def contrast(weights):
        return (sum(values[c] * weight for c, weight in weights.items())
                if all(values[c] is not None for c in weights) else None)

    return {"R": values, "complete": all(v is not None for v in values.values()),
        "split_minus_shared_base": contrast({"PB": 1, "SB": -1}),
        "split_minus_shared_team": contrast({"PT": 1, "ST": -1}),
        "team_minus_base_shared": contrast({"ST": 1, "SB": -1}),
        "team_minus_base_split": contrast({"PT": 1, "PB": -1}),
        "information_main_effect": contrast({"PB": .5, "PT": .5, "SB": -.5, "ST": -.5}),
        "framing_main_effect": contrast({"ST": .5, "PT": .5, "SB": -.5, "PB": -.5}),
        "interaction": contrast({"PT": 1, "PB": -1, "ST": -1, "SB": 1})}


def _partial_cost(folder):
    """Recover recorded costs only; a surviving snapshot never closes an outcome."""
    evidence_path = folder / "organization-evidence.json"
    evidence = read(evidence_path) or {}
    value = {key: evidence[key] for key in ("member_lifecycle", "environment_preparation_cost", "action_error_policy", "initial_diagnostics") if key in evidence}
    budget, budget_path = evidence.get("team_budget"), evidence_path
    if not isinstance(budget, dict):
        budget_path = folder / "team-budget.json"
        budget = read(budget_path)
    if not isinstance(budget, dict):
        budget_path = folder / "runtime-state.json"
        budget = (read(budget_path) or {}).get("team_budget")
    records = (budget or {}).get("model", {}).get("records")
    records = records if isinstance(records, dict) else None
    usage = evidence.get("total_usage")
    info = {"status": "partial_organization_evidence" if isinstance(usage, dict) else
            "partial_budget_ledger" if isinstance(budget, dict) else "unreported_started_episode",
        "cost_incomplete": True, "snapshot_may_precede_stop": True,
        "unsettled_record_ids": [], "unsettled_attempts": None, "attempts_without_reported_token_usage": None,
        "scope": "Recorded costs from an unclosed episode. Missing or unsettled consumption stays unknown; reservations are not actual tokens."}
    if evidence:
        info["organization_evidence"] = reference(evidence_path)
    if isinstance(budget, dict):
        value["team_budget"] = budget
        info["raw_budget"] = reference(budget_path)
    if records is not None:
        rows = list(records.values())
        attempted = [row for row in rows if row.get("attempt_started") is True]
        charges = [row["charge"] for row in attempted if isinstance(row.get("charge"), dict)]
        reports = [charge["reported_usage"] for charge in charges
            if charge.get("usage_status") == "reported_actual_trace"
            and isinstance(charge.get("reported_usage"), dict)
            and all(type(charge["reported_usage"].get(key)) is int and charge["reported_usage"][key] >= 0
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens"))]
        info.update(unsettled_record_ids=[key for key, row in records.items()
            if row.get("status") in {"decision_consumed", "reserved", "attempting"}],
            unsettled_attempts=sum(row.get("status") != "settled" or not isinstance(row.get("charge"), dict)
                                  for row in attempted),
            attempts_without_reported_token_usage=len(attempted) - len(reports))
        if not isinstance(usage, dict):
            usage = {"decisions": len(rows), "attempts": len(attempted),
                "budget_charged_tokens": sum(c["charged_tokens"] for c in charges
                    if type(c.get("charged_tokens")) is int and c["charged_tokens"] >= 0),
                "uncertain_usage_attempts": sum(c.get("usage_status") == "uncertain_attempt_charged_reservation" for c in charges)}
            if reports:
                usage.update({key: sum(r[key] for r in reports)
                              for key in ("prompt_tokens", "completion_tokens", "total_tokens")})
            info["usage_basis"] = "Ledger attempts and settled charges only; output-bearing calls require original response evidence"
    if isinstance(usage, dict):
        value["usage"] = usage
    value["cost_evidence"] = info
    return value


def recorded_rows(root, state, worker, inventory):
    rows = []
    for unit in inventory:
        folder = root / worker / "actual/episodes" / unit["slot_id"]
        result = read(folder / "slot-result.json")
        if result:
            rows.append({**unit, **result, "work_use": read(folder / "work-use.json"),
                "feedback_loop": read(folder / "feedback-loop.json")})
        else:
            started = folder.exists()
            terminal = (state["status"] not in {"prepared", "waiting", "running"}
                or state["states"].get(worker, {}).get("status") in {"complete", "stopped"})
            status = "technical_unknown" if started and terminal else "running" if started else "not_started"
            rows.append({**unit, **(_partial_cost(folder) if started else {}),
                "status": status, "R": None, "submitted": None,
                "training_eligible": False, "worker_state": state["states"].get(worker, {}), "work_use": None})
    return rows


def usage_cost(rows, state, names):
    keys = ("decisions", "attempts", "prompt_tokens", "completion_tokens", "total_tokens", "output_bearing_calls",
            "budget_charged_tokens", "uncertain_usage_attempts")
    costs = [row for row in rows if row.get("usage")]
    started = [row for row in rows if row.get("status") != "not_started"]
    partial = [row for row in started if row.get("cost_evidence", {}).get("cost_incomplete")]
    missing = {key: sum(type(row.get("usage", {}).get(key)) is not int for row in started) for key in keys}
    missing["run_tests"] = sum(type(row.get("team_budget", {}).get("tests", {}).get("used")) is not int for row in started)
    unreported_attempts = sum(row.get("cost_evidence", {}).get("attempts_without_reported_token_usage")
        if type(row.get("cost_evidence", {}).get("attempts_without_reported_token_usage")) is int
        else row.get("usage", {}).get("uncertain_usage_attempts", 0) for row in started)
    return {"episodes_with_recorded_usage": len(costs), "recorded_usage": {
        key: sum(row["usage"][key] for row in costs if type(row["usage"].get(key)) is int) for key in keys},
        "run_tests": sum(row["team_budget"]["tests"]["used"] for row in rows
                         if type(row.get("team_budget", {}).get("tests", {}).get("used")) is int),
        "cost_incomplete": bool(partial or any(missing.values()) or unreported_attempts),
        "partial_cost_episodes": len(partial), "unreported_started_episodes": sum(not row.get("usage") for row in started),
        "unsettled_attempts": sum(row.get("cost_evidence", {}).get("unsettled_attempts", 0) or 0 for row in partial),
        "partial_episodes_without_settlement_counts": sum(row["cost_evidence"].get("unsettled_attempts") is None for row in partial),
        "attempts_without_reported_token_usage": unreported_attempts,
        "metrics_with_missing_episode_records": missing,
        "closed_worker_gpu_seconds": sum(state["states"].get(name, {}).get("elapsed_gpu_seconds", 0) for name in names),
        "running_worker_gpu_seconds": sum(max(0, state.get("observed_at", time.time()) - state["states"][name]["started_at"])
            for name in names if state["states"].get(name, {}).get("status") == "running"),
        "scope": "All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time."}


def results(root):
    root = Path(root)
    plan = read_json(root / "plan.json")
    state = read(root / "supervisor.json") or {"status": "prepared", "states": {}}
    rows = [row for worker, inventory in plan["assignments"].items()
            for row in recorded_rows(root, state, worker, inventory)]
    workers = {worker: {"state": state["states"].get(worker, {}), "report": read(root / worker / "actual/report.json")}
               for worker in WORKERS}
    by_condition = {}
    for condition in CONDITIONS:
        subset = [row for row in rows if row["condition"] == condition]
        closed = [row for row in subset if known(row)]
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
            "cost": usage_cost(subset, {"states": {}}, ())}
    blocks = []
    for worker, units in plan["assignments"].items():
        group = {row["condition"]: row for row in rows if row["slot_id"] in {u["slot_id"] for u in units}}
        blocks.append({"block_id": worker, "case_id": units[0]["case_id"], "sampling_seed": units[0]["sampling_seed"],
            "first_member": units[0]["first_member"], "diagnostic_a_owner": units[0]["diagnostic_a_owner"],
            **block_contrasts(group)})
    keys = ("split_minus_shared_base", "split_minus_shared_team", "team_minus_base_shared", "team_minus_base_split",
            "information_main_effect", "framing_main_effect", "interaction")
    means = {key: sum(block[key] for block in blocks) / 4 if all(block[key] is not None for block in blocks) else None
             for key in keys}
    return {"version": VERSION, "status": state["status"], "plan": reference(root / "plan.json"),
        "source": plan["source"], "purpose": "organization_development", "rows": rows, "workers": workers,
        "by_condition": by_condition, "paired_blocks": blocks, "full_inventory_mean_contrasts": means,
        "first_block_gate": read(root / "first-block-gate.json"),
        "feedback_loops": {"episodes_measured": sum(row.get("feedback_loop") is not None for row in rows),
            "per_episode": [{"slot_id": row["slot_id"], "denominators": row["feedback_loop"].get("denominators"),
                "projection_audit": row["feedback_loop"].get("projection_audit"),
                "page_denominators": row["feedback_loop"].get("page_denominators"),
                "mechanism_gate_inputs": row["feedback_loop"].get("mechanism_gate_inputs")}
                for row in rows if row.get("feedback_loop") is not None]},
        "cost": usage_cost(rows, state, WORKERS),
        "environment_preparation": {"slot_receipts": [{"slot_id": row["slot_id"], **row["environment_preparation_cost"]}
            for row in rows if row.get("environment_preparation_cost")],
            "recorded_totals": {key: sum(row.get("environment_preparation_cost", {}).get(key, 0) for row in rows)
                for key in ("actual_public_driver_executions", "sandbox_elapsed_seconds", "prepare_function_wall_seconds",
                            "model_calls", "model_output_tokens", "team_run_tests_charged")},
            "scope": "Actual recorded preparation executions and cache reuse only. Never member discoveries or extra learner calls; preparation wall times are nested in worker occupancy."},
        "scheduled": 16, "known": sum(known(row) for row in rows),
        "new_actor_steps": sum((worker["report"] or {}).get("new_actor_steps", 0) for worker in workers.values()),
        "new_critic_steps": sum((worker["report"] or {}).get("new_critic_steps", 0) for worker in workers.values()),
        "new_backward_calls": 0, "allowed_physical_gpus": list(GPU_ORDER), "supervisor": state,
        "scope": "Two handoff development variants, four paired evidence/framing conditions, two seeds. Initial preparation is not model work; explicit team framing is a prompt intervention. No independent benchmark claim, causal contribution credit or parameter-learning gain. All 16 original slots retained."}


def report(root, destination):
    value = results(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    write(destination / "software-organization-v043.json", value)
    lines = ["# v0.43 分层准入后的冻结模型组织开发", "",
        f"状态：`{value['status']}`；原16槽中正式结果已知`{value['known']}/16`。执行源码`{value['source']['code_commit']}`。", "",
        "本轮模型可见协议完整沿用v042：v041精确静态去重、3072字符测试正文页和原测试成员专属read_test_result不变。新v043入口严格复用绑定的来源/信息权限/selected硬容量证据，将1024-token protected余量保留为风险诊断；旧v042 passed=false不修改。读页自主、计入原预算、不重新测试、不强制读完；CPU页面路线不当作模型行为。", "",
        f"首块机制门槛：`{value['first_block_gate']}`。停止不把未启动槽填零；继续与否不依赖R、交流或招募。", "",
        "SB=shared/base，ST=shared/team，PB=split/base，PT=split/team。两个承接态root与两枚此前未被模型消费、在org43重新登记的seed构成4个配对块；每块四条件共享相同初态代码、根要求、先手、测试和总预算。所有条件初始2人、允许自主增员（活动≤4/累计≤6），无外生出生。", "",
        "原9B 3/3 common，16K/2048，每槽128决定/attempt、500000实际token、32次测试。环境事先实际运行两组公开检查，shared两人各获两份，split各获一份；成员可自己同权限检查重得信息。G-team额外的共同交付说明是明确提示干预，信息位置和说明都会影响输入长度与取得成本。", "",
        "| 条件 | 已知/计划 | 已知成功 | 已知固定提交 | 自然出生 | 全4槽平均R |",
        "|---|---:|---:|---:|---:|---:|"]
    for c, row in value["by_condition"].items():
        lines.append(f"| {c} | {row['known']}/4 | {row['successes']} | {row['submitted_known']} | {row['member_requested_births']} | {row['mean_R']} |")
    lines += ["", "| 条件 | 已证实跨成员链 | 完整记录未证实 | 未知/未测量 | 可恢复未知名字/参数错误 | 禁止过程请求 |", "|---|---:|---:|---:|---|---:|"]
    for c, row in value["by_condition"].items():
        work, errors = row["cross_member_work"], row["action_errors"]
        lines.append(f"| {c} | {work['evidenced']} | {work['not_evidenced_complete']} | {work['unknown_or_unmeasured']} | {errors['recoverable_unknown_names']}/{errors['recoverable_argument_errors']} | {errors['process_violation_count']} |")
    lines += ["", "工作链列为保守机械证据；信息语义候选、复杂关系或未测量保持未知，不以0代替。测试是否通过、是否连接最后交付及正式R分别记录。", "", "| 配对块 | SB | ST | PB | PT | 信息主效应 | 说明主效应 | 交互 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for block in value["paired_blocks"]:
        lines.append("| " + block["block_id"] + " | " + " | ".join(str(block["R"][c]) for c in CONDITIONS)
            + " | " + " | ".join(str(block[k]) for k in ("information_main_effect", "framing_main_effect", "interaction")) + " |")
    lines += ["", f"全库存平均对比：`{value['full_inventory_mean_contrasts']}`。None表示所需配对未完整，未知或未启动不填零。", "",
        "信息主效应=[(PB+PT)−(SB+ST)]/2；说明主效应=[(ST+PT)−(SB+PB)]/2；交互=PT−PB−ST+SB。每项先在root/seed块内计算，再取原4块平均。这是两root有限开发观察，不是总体稳定性认证。", "",
        "| slot | 状态 | R | 提交 | 决定/调用 | 输入/输出token | 初始/累计人数 | 测试 |",
        "|---|---|---:|---|---|---|---|---:|"]
    for row in value["rows"]:
        usage, life = row.get("usage", {}), row.get("member_lifecycle", {})
        tests = row.get("team_budget", {}).get("tests", {}).get("used")
        lines.append(f"| {row['slot_id']} | {row['status']} | {row['R']} | {row.get('submitted')} | {usage.get('decisions')}/{usage.get('attempts')} | {usage.get('prompt_tokens')}/{usage.get('completion_tokens')} | {len(life.get('initial_members', [])) if life else None}/{life.get('cumulative_births')} | {tests} |")
    lines += ["", "| slot | 报告保存 | 报告有页面实际呈现 | 历史完整覆盖报告 | 真实读页请求 | 实际生成中的工程余量警示 |",
        "|---|---:|---:|---:|---:|---:|"]
    for row in value["rows"]:
        feedback = row.get("feedback_loop") or {}
        pages = feedback.get("page_denominators") or {}
        audits = feedback.get("projection_audit")
        warnings = (sum(type(item.get("protected_headroom_after_margin_tokens")) is int
                        and item["protected_headroom_after_margin_tokens"] < 0 for item in audits)
                    if isinstance(audits, list) else None)
        lines.append(f"| {row['slot_id']} | {pages.get('reports_saved')} | {pages.get('reports_with_any_page_presented')} | {pages.get('reports_historically_fully_presented')} | {pages.get('actual_page_read_requests')} | {warnings} |")
    lines += ["", "工程余量警示只记录protected距13312的不足，不是运行拒绝或成功标准。历史覆盖是同一报告/事件/源版本的片段并集，不代表同时可见、理解或采用；未请求后页不判机械故障。", ""]
    lines += ["", f"全部实际成本：`{value['cost']}`。新增actor/critic步`{value['new_actor_steps']}/{value['new_critic_steps']}`，新增反向`{value['new_backward_calls']}`。", "",
        f"初始环境准备实际新增成本：`{value['environment_preparation']['recorded_totals']}`；每槽缓存复用与原来源见JSON，原准备成本不随复用次数重复累计。", "",
        "逐槽feedback-loop.json分开记录报告保存、目录呈现、页面片段实际selected呈现、同报告历史覆盖并集、后续工作候选和交付关联；重复页费用照计而覆盖不重复。未请求后续页是自主选择，历史覆盖不等于当前同时可见或理解采用。无后续输入分别记录context、团队预算、正常结束、未请求、等待与故障。", "",
        "逐槽work-use.json记录所有成员（包括初始成员）的事实/产物→分享→伙伴实际selected输入→修改/验证→工作结果关系，最终固定交付连接另列。环境初始代码与诊断不算当前模型发现或编辑；信息语义候选保留待人工核查，不能把消息数、任务ID或相同代码自动判成使用。", "",
        "未知工具名在可靠记录、执行前成功阻断时为可恢复动作错误；保留输出和费用，下一真实机会看反馈，不自动改名或免费重试。明确禁止的controller请求仍拒绝、过程违规单列；真正身份/执行效果/记录完整性失败仍停止。正式R与原固定内容验收分层，旧v039未知及两个未启动槽不回改。", "",
        "仅允许物理GPU3、4、5、7；不恢复旧训练、Contribution、独立确认或缓存生产队列。无新增出生接口题、X3、模型筛选或参数学习。", "",
        "[冻结协议](software-organization-v043-protocol.md)；[承接态任务](software-organization-v040-tasks.md)；[审计原文](../reference/audit-v042-next-v043.md)。", ""]
    (destination / "software-organization-v043.md").write_text("\n".join(lines))
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
                "docs: record frozen v043 organization-development outcomes")
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
