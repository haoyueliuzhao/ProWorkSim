"""One matched single/team O1 diagnostic; no repeated behavior-qualification quiz."""
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
from proworksim.storage import digest, read_json
from scripts import continue_model_selection_v031 as continuation
from scripts import software_model_selection_v030 as original
from scripts import software_model_selection_v031 as dense
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, resources, write
from scripts.software_development_v028 import available_cards, task

VERSION = "paired-o1-diagnostic-v0.33"
SOURCE = Path(__file__).resolve().parents[1]
CANDIDATES = ("qwen3.5-9b", "devstral-small-2507")
GPU_ORDER = [4, 6, 5, 0, 1, 2, 3, 7]
LIMITS = {**copy.deepcopy(original.LIMITS), "max_parallel_model_instances": 2}
TERMINAL = {"complete", "stopped"}
REPORT_PATHS = ["docs/experiments/software-paired-o1-v033.md", "docs/experiments/software-paired-o1-v033.json"]
COMMON_NUMERIC = ("src/proworksim/online_training.py", "src/proworksim/local_model_service.py",
    "src/proworksim/training.py", "src/proworksim/candidate_runtime_v015.py",
    "src/proworksim/candidate_runtime_v020.py", "src/proworksim/candidate_runtime_v0201.py",
    "src/proworksim/software_learning_v029.py")
NUMERIC = {
    CANDIDATES[0]: (*COMMON_NUMERIC, "src/proworksim/collaboration_actor_v022.py",
        "src/proworksim/deterministic_work_v024.py", "src/proworksim/functional_qwen_v022.py"),
    CANDIDATES[1]: (*COMMON_NUMERIC, "src/proworksim/candidate_runtime_v030.py",
        "src/proworksim/candidate_runtime_v031.py", "src/proworksim/functional_dense_v031.py"),
}
NEXT_STAGE_RULE = {
    "purpose": "Identify a local carrier for fresh training-source support, never retroactively select a v030 winner",
    "require_all_eight_valid_known": True, "minimum_complete_team_episodes": 1,
    "rank_order": ["team_successes_desc", "pairs_both_conditions_successful_desc", "fixed_candidate_order"],
    "all_team_zero": "No winner; propose a new root goal with less domain complexity while preserving O1",
    "automatic_allocation_updates": False, "automatic_model_search": False,
    "development_records_may_become_training": False,
}


def checked(ref):
    """Bind both plain JSON references and tensor references with exact sizes."""
    if not isinstance(ref, dict) or not {"path", "sha256"} <= set(ref) or set(ref) - {"path", "sha256", "bytes"}:
        raise ValueError("Expected a frozen file reference with optional byte size")
    path = Path(ref["path"])
    if (digest(path.read_bytes()) != ref["sha256"]
            or ("bytes" in ref and (type(ref["bytes"]) is not int or path.stat().st_size != ref["bytes"]))):
        raise ValueError("Frozen artifact content or size changed: " + str(path))
    return path


def inventory():
    from proworksim.software_runtime_v033 import inventory as paired_inventory
    return paired_inventory()


def numerical_sources(old_root, candidate):
    values = {}
    for name in NUMERIC[candidate]:
        old, current = Path(old_root) / name, SOURCE / name
        if old.read_bytes() != current.read_bytes():
            raise ValueError("Inherited numerical implementation changed: " + name)
        values[name] = digest(current.read_bytes())
    return values


def inherited_candidate(data_root, candidate):
    root = Path(data_root).resolve()
    run = root / "runs" / ("software-model-selection-v030" if candidate == CANDIDATES[0] else "software-model-selection-v031")
    actual = run / candidate / "actual"
    plan, state = read_json(run / "plan.json"), read_json(run / candidate / "state.json")
    worker = read_json(actual / "report.json")
    qualification = read_json(actual / "qualification/report.json")
    owner = read_json(actual / "resident/owner.json")
    common = read_json(actual / "common-state/checkpoint.json")
    update = qualification.get("update") or {}
    if (state.get("status") != "complete" or state.get("exit_code") != 0 or state.get("stop_reason") is not None
            or worker.get("status") != "complete" or len(worker.get("rows", [])) != 12
            or worker.get("screening_optimizer_steps") != 0
            or worker.get("source_before") != plan["source"] or worker.get("source_after") != plan["source"]
            or worker.get("qualification") != qualification
            or any(qualification.get(key) is not True for key in (
                "training_integration_ready", "near_16k_capacity_demonstrated", "common_restored_exactly",
                "diagnostic_gradients_cleared", "updated_identity_return_passed"))
            or update.get("actor_optimizer_steps") != 1 or update.get("critic_optimizer_steps") != 1
            or update.get("backward_decisions_completed") != 4
            or any(len(update.get(key, [])) != 4 or any(row.get("passed") is not True for row in update[key])
                   for key in ("behavior_probability_checks", "gradient_probability_checks"))
            or qualification.get("common_before", {}).get("state_tensor_digest") != common["state_tensor_digest"]
            or qualification.get("common_after", {}).get("state_tensor_digest") != common["state_tensor_digest"]
            or common["actor_identity"] != worker["common_actor_identity"]):
        raise ValueError("Require immutable completed original work and full numerical/common proof for " + candidate)
    expected_steps = 3 if candidate == CANDIDATES[0] else 0
    if (common.get("actor_steps"), common.get("critic_steps")) != (expected_steps, expected_steps):
        raise ValueError("Restore the original candidate-specific numerical state, not a fresh or promoted endpoint")
    references = {"plan": reference(run / "plan.json"), "state": reference(run / candidate / "state.json"),
        "worker": reference(actual / "report.json"), "qualification": reference(actual / "qualification/report.json"),
        "owner": reference(actual / "resident/owner.json"), "common": reference(actual / "common-state/checkpoint.json"),
        "common_state": common["state"], "base_manifest": owner["base_identity"]["manifest"],
        "aggregate_update": reference(actual / "qualification/aggregate-update.json"),
        "updated_checkpoint": reference(actual / "qualification/updated-checkpoint/checkpoint.json"),
        "updated_state": qualification["checkpoint_roundtrip"]["checkpoint"]["state"],
        "updated_return": reference(actual / "qualification/updated-return-probe/updated-identity-return.json"),
        "updated_return_guard": reference(actual / "qualification/updated-return-probe/evaluation-guard.json")}
    for index in range(1, 5):
        for kind in ("request", "response"):
            references[f"native_call_{index}_{kind}"] = reference(actual / "qualification" / f"native-call-{index}" / (kind + ".json"))
    for value in references.values():
        checked(value)
    if (read_json(checked(references["aggregate_update"])) != update
            or read_json(checked(references["updated_checkpoint"])) != qualification["checkpoint_roundtrip"]["checkpoint"]
            or read_json(checked(references["updated_return"])) != qualification["return_probe"]):
        raise ValueError("Inherited numerical receipts must remain bound to their actual original records")
    return {"candidate_id": candidate, "run_root": str(run), "source": plan["source"],
            "references": references, "common_actor_identity": common["actor_identity"],
            "common_state_tensor_digest": common["state_tensor_digest"], "common_steps": expected_steps,
            "numeric_source_sha256": numerical_sources(plan["source_root"], candidate),
            "prior_selection_reclassified": False, "learning_evidence_inherited": True,
            "fresh_technical_quiz_calls": 0, "repeat_near_16k_stress": False}


def make_plan(data_root, cpu_qualification):
    root = Path(data_root).resolve()
    parents = {candidate: inherited_candidate(root, candidate) for candidate in CANDIDATES}
    base = read_json(checked(parents[CANDIDATES[0]]["references"]["plan"]))
    old_runs = [root / "runs" / name for name in (
        "software-model-selection-v030", "software-model-selection-v030-recovery", "v031-dense-probes",
        "software-model-selection-v031", "software-path-recovery-v031r2", "software-harness-recovery-v032")]
    return {"version": VERSION, "created_at": time.time(), "source": code_identity(), "source_root": str(SOURCE),
        "data_root": str(root), "qualification": reference(cpu_qualification), "parents": parents,
        "candidates": list(CANDIDATES), "inventories": {candidate: inventory() for candidate in CANDIDATES},
        "limits": copy.deepcopy(LIMITS), "gpu_preference": GPU_ORDER,
        "runtime_dependency_path": base["runtime_dependency_path"],
        "prior_artifact_roots": dense._artifact_roots(old_runs),
        "audit": reference(SOURCE / "docs/reference/audit-v032-next-v033.md"),
        "protocol": reference(SOURCE / "docs/experiments/software-paired-o1-v033-protocol.md"),
        "frozen_development_episodes": 16, "optimizer_updates_allowed": False,
        "fresh_technical_quiz_calls": 0, "repeat_near_16k_stress": False,
        "automatic_retries": False, "automatic_successors": [], "automatic_model_replacement": False,
        "total_gpu_seconds": None, "worker_gpu_seconds": None, "queue_deadline_at": None, "wall_deadline_at": None,
        "four_layers": {"execution_trust": "CPU interface controls plus per-call identity/token/permission/evidence checks",
                        "learning_integration": "Inherited actual original common/profile/full-gradient/capacity evidence",
                        "work_behavior": "New matched S/T work; mistakes are outcomes, not invalidation of numerical evidence",
                        "allocation_support": "Not provided by these development records; fresh training-source collection required"},
        "next_stage_rule": copy.deepcopy(NEXT_STAGE_RULE), "old_selected_candidate": None,
        "old_results_reclassified": False, "swe_rerun": False, "new_model_downloads": False,
        "authorization": "User supplied the v033 audit and requested revisions and subsequent experiments",
        "scope": "One finite two-model, two-O1-root, S/T, two-seed development diagnostic. Matched team budgets; zero parameter updates. No general model qualification loop or new candidate search."}


def validate_plan(plan, *, check_files=True):
    if (plan.get("version") != VERSION or plan.get("candidates") != list(CANDIDATES)
            or plan.get("inventories") != {c: inventory() for c in CANDIDATES}
            or plan.get("limits") != LIMITS or plan.get("gpu_preference") != GPU_ORDER
            or plan.get("frozen_development_episodes") != 16 or plan.get("optimizer_updates_allowed") is not False
            or plan.get("fresh_technical_quiz_calls") != 0 or plan.get("repeat_near_16k_stress") is not False
            or plan.get("automatic_retries") is not False or plan.get("automatic_successors") != []
            or plan.get("automatic_model_replacement") is not False or plan.get("swe_rerun") is not False
            or plan.get("new_model_downloads") is not False or plan.get("old_results_reclassified") is not False
            or plan.get("next_stage_rule") != NEXT_STAGE_RULE or plan.get("old_selected_candidate") is not None
            or any(plan.get(key) is not None for key in ("total_gpu_seconds", "worker_gpu_seconds", "queue_deadline_at", "wall_deadline_at"))):
        raise ValueError("Use exactly the one predeclared 16-episode paired diagnostic and new matched budget policy")
    if check_files:
        if plan["source"] != code_identity() or plan["source"].get("code_dirty") is not False or plan["source_root"] != str(SOURCE):
            raise ValueError("Use the exact clean, CPU-qualified execution checkout")
        cpu = read_json(checked(plan["qualification"]))
        if cpu.get("passed") is not True or cpu.get("source") != plan["source"] or cpu.get("model_calls") != 0:
            raise ValueError("Require passing same-source v033 CPU interface/world/budget controls")
        for candidate in CANDIDATES:
            if inherited_candidate(plan["data_root"], candidate) != plan["parents"][candidate]:
                raise ValueError("Inherited candidate evidence changed")
        checked(plan["audit"])
        checked(plan["protocol"])
    return plan


def observed_rows(actual, expected):
    rows = read(Path(actual) / "diagnostics/progress.json") or []
    if len(rows) > len(expected):
        raise ValueError("More episodes than the original eight-slot inventory")
    for current, declared in zip(rows, expected):
        if any(current.get(key) != value for key, value in declared.items()):
            raise ValueError("A paired result changed its condition, seed, goal or team budget")
    return rows


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
        "old_results_reclassified": False, "learning_evidence_inherited": True}
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
                report["rows"] = observed_rows(output, plan["inventories"][candidate])
                write(output / "report.json", report)
        entries = collect(owner, window_spec("v033-" + candidate), output / "diagnostics", output,
                          common_dir=common_dir, on_slot=on_slot)
        verify_common()
        report["rows"] = observed_rows(output, plan["inventories"][candidate])
        if len(entries) != 8 or len(report["rows"]) != 8:
            raise ValueError("A complete one-time diagnostic must retain all eight original slots")
        report.update(status="complete", common_restored_exactly=True)
    except BaseException as error:
        report.update(status="execution_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report["rows"] = observed_rows(output, plan["inventories"][candidate])
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps,
                          final_actor_identity=owner._make_identity())
        report.update(ended_at=time.time(), source_after=code_identity())
        write(output / "report.json", report)
    return report


def results(plan, root):
    root = Path(root)
    supervisor = read_json(root / "supervisor.json")
    outcomes, pairs, candidate_results = {}, [], {}
    for candidate in CANDIDATES:
        actual = root / candidate / "actual"
        rows = observed_rows(actual, plan["inventories"][candidate])
        worker = read(actual / "report.json") or {}
        outcomes[candidate] = rows
        def known(row):
            return (row.get("status") == "closed" and row.get("record_validity") is True
                    and type(row.get("R")) is int and row["R"] in (0, 1))
        conditions = {}
        for condition in ("S", "T"):
            subset = [row for row in rows if row["condition"] == condition]
            conditions[condition] = {"expected": 4, "known": sum(known(row) for row in subset),
                "complete_deliveries": sum(known(row) and row["R"] == 1 and row.get("complete_delivery") is True for row in subset),
                "content_known": sum(type(row.get("content_correct")) is bool for row in subset),
                "content_correct": sum(row.get("content_correct") is True for row in subset),
                "process_known": sum(type(row.get("required_process_satisfied")) is bool for row in subset),
                "process_satisfied": sum(row.get("required_process_satisfied") is True for row in subset)}
        complete_pairs = 0
        pair_keys = sorted({(row["case_id"], row["sampling_seed"]) for row in plan["inventories"][candidate]})
        for case, seed in pair_keys:
            matching = {row["condition"]: row for row in rows if (row["case_id"], row["sampling_seed"]) == (case, seed)}
            s, t = matching.get("S", {}), matching.get("T", {})
            assessed = known(s) and known(t)
            sr, tr = (s["R"], t["R"]) if assessed else (None, None)
            outcome = ({(0, 0): "both_failed", (1, 0): "single_only", (0, 1): "team_only", (1, 1): "both_succeeded"}[(sr, tr)] if assessed else "unknown_or_not_started")
            complete_pairs += int(outcome == "both_succeeded")
            pairs.append({"candidate_id": candidate, "case_id": case, "sampling_seed": seed,
                          "S": sr, "T": tr, "T_minus_S": tr - sr if assessed else None, "pattern": outcome})
        all_known = len(rows) == 8 and all(known(row) for row in rows)
        ready = (supervisor["states"][candidate]["status"] == "complete" and worker.get("status") == "complete"
                 and worker.get("execution_binding_passed") is True and worker.get("common_restored_exactly") is True
                 and worker.get("screening_optimizer_steps") == 0 and all_known and conditions["T"]["complete_deliveries"] >= 1)
        candidate_results[candidate] = {"conditions": conditions, "all_eight_known_valid": all_known,
            "pairs_both_succeeded": complete_pairs, "local_team_feasibility": ready,
            "worker_status": worker.get("status"), "state": supervisor["states"][candidate]}
    terminal = all(state["status"] in TERMINAL for state in supervisor["states"].values())
    eligible = [c for c in CANDIDATES if candidate_results[c]["local_team_feasibility"]] if terminal else []
    eligible.sort(key=lambda c: (-candidate_results[c]["conditions"]["T"]["complete_deliveries"],
                                -candidate_results[c]["pairs_both_succeeded"], CANDIDATES.index(c)))
    next_stage = {"status": "pending" if not terminal else "fresh_support_candidate_identified" if eligible else "no_local_team_carrier",
        "support_collection_candidate": eligible[0] if eligible else None, "rule": NEXT_STAGE_RULE,
        "prior_v030_selected_candidate": None, "old_selection_reclassified": False,
        "automatic_execution": False, "development_records_are_training_support": False,
        "required_next_design": "Freeze a fresh training-source root goal, current-strategy collection, actual support/method/frequency/gradient checks and affordable fair B/G/I probe dimensions" if eligible else
                                "If all team results remain zero, design a new less domain-complex root goal while retaining empty-task O1 and true API-consumer dependency; do not add a model or relabel old episodes"}
    return {"version": VERSION, "generated_at": time.time(), "status": supervisor["status"], "plan": plan,
            "supervisor": supervisor, "outcomes": outcomes, "candidate_results": candidate_results,
            "paired_outcomes": pairs, "next_stage": next_stage, "selected_candidate": None,
            "scope": plan["scope"], "allocation_experiment_started": False}


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
                        argv = [sys.executable, "-m", "scripts.software_paired_o1_v033", "worker", "--plan", str(root / "plan.json"),
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
            summary["status"] = "interrupted"
            raise
        finally:
            summary["ended_at"] = time.time()
            publish()
    write(root / "next-stage-decision.json", results(plan, root)["next_stage"])
    return summary


def report(run_root, output_dir):
    root, output = Path(run_root).resolve(), Path(output_dir).resolve()
    value = results(read_json(root / "plan.json"), root)
    output.mkdir(parents=True, exist_ok=True)
    write(output / "software-paired-o1-v033.json", value)
    lines = ["# v0.33 同一O1根目标的单执行者／双成员有限诊断", "",
        f"状态：`{value['status']}`；执行源码：`{value['plan']['source']['code_commit']}`；原始记录：`{root}`。", "",
        "仅9B与Devstral，两个相同根目标×S/T×两个固定seed，每模型8槽，总16槽。两条件共同团队总预算128次决定、500000 token、32次run_tests；T不按人数翻倍。旧三个候选无赢家结论不改，SWE不复测。", "",
        "旧实际数值／16K／更新／恢复证据在同一common和未变数值实现下继承；没有新增三题资格、压力反向或诊断优化。普通schema错误保留原输出、实际消耗机会并反馈到共同预算，身份／权限／关键记录问题独立阻断。内容、规定API过程和完整固定交付分列。", "",
        "| 模型 | 根目标 | seed | S完整R | T完整R | T-S | 配对观察 |", "|---|---|---:|---:|---:|---:|---|"]
    for pair in value["paired_outcomes"]:
        lines.append(f"| {pair['candidate_id']} | {pair['case_id']} | {pair['sampling_seed']} | {pair['S']} | {pair['T']} | {pair['T_minus_S']} | {pair['pattern']} |")
    lines += ["", "| 模型 | 条件 | 完整交付／已知 | 内容通过／已知 | 规定过程通过／已知 |", "|---|---|---:|---:|---:|"]
    for c, result in value["candidate_results"].items():
        for condition, row in result["conditions"].items():
            lines.append(f"| {c} | {condition} | {row['complete_deliveries']}/{row['known']} | {row['content_correct']}/{row['content_known']} | {row['process_satisfied']}/{row['process_known']} |")
    lines += ["", f"后续支持采集决策：`{value['next_stage']['status']}`；局部载体：`{value['next_stage']['support_collection_candidate']}`。", "",
        "这不是追认旧v0.30候选入选，也不是通用模型或团队优劣排名。两个seed仅描述本开发复测；完整比较保持同根目标、初始代码／合同／验收、总资源和固定参数，S为T合法初始信息并集，T使用两个私有工作副本。", "",
        "有局部团队可行性后应转入新训练来源的当前支持采集，不能把这些开发轨迹改作训练；必须再冻结实际支持、方法频数、可辨识梯度和公平可承担的B/G/I试训维度。没有自动追加本诊断、搜索模型或启动未冻结分配更新。", "",
        f"已闭合worker成本：{value['supervisor'].get('worker_gpu_seconds', 0):.6f} GPU秒；当前运行：{value['supervisor'].get('running_gpu_seconds', 0):.6f}秒。", "",
        "GPU成本为分配单卡worker墙钟；预约与worker总占卡应按每张卡的区间并集另算，不把二者直接相加。所有原先累计时限仍为None，单任务／内存／产物保护门保留。", "",
        "本轮是工作行为诊断，零正式参数更新，无ID-VTDO效果或独立来源泛化结论。未开始／技术未知不补0分。完整团队预算账、逐槽结果、源状态及配对证明见JSON与服务器原件。", ""]
    (output / "software-paired-o1-v033.md").write_text("\n".join(lines))
    return value


def finish(plan_path, run_root, report_repo, *, publish=False):
    plan_path, run_root, report_repo = (Path(p).resolve() for p in (plan_path, run_root, report_repo))
    if run_root.exists():
        raise FileExistsError("Do not retry or append a previously started paired diagnostic")
    path = run_root.parent / (run_root.name + "-finish.json")
    state = {"version": VERSION, "status": "supervising", "started_at": time.time(), "run_root": str(run_root)}
    write(path, state)
    process = subprocess.run([sys.executable, "-m", "scripts.software_paired_o1_v033", "supervise", "--plan", str(plan_path),
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
                subprocess.run(["git", "commit", "--only", "-m", "docs: archive v033 matched single-team O1 diagnostic", "--", *REPORT_PATHS], cwd=report_repo, check=True)
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
    for name in ("data-root", "cpu-qualification", "plan", "run-root", "output", "report-repo"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--candidate", choices=CANDIDATES)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    required = {"prepare": ("data_root", "cpu_qualification", "output"), "worker": ("plan", "candidate", "output"),
                "supervise": ("plan", "run_root"), "report": ("run_root", "output"), "finish": ("plan", "run_root", "report_repo")}
    if any(getattr(args, key) is None for key in required[args.mode]):
        parser.error(args.mode + " requires " + ", ".join(required[args.mode]))
    def interrupted(signum, frame):
        raise KeyboardInterrupt("Paired diagnostic received signal " + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    if args.mode == "prepare":
        value = validate_plan(make_plan(args.data_root, args.cpu_qualification))
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
