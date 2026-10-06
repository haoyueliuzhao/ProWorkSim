"""Conditional, fully frozen v036 B/G-raw/I-P execution from one complete common.

The shared B trial measures real material consumption and full update cost.
All other candidates and formal methods restore the same full state. No outcome
can shrink the frozen directions, panel or original training denominator.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
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
from proworksim.experience_allocation_v035 import (
    METHODS, bind_allocation, bind_candidate, development_receipt, select_allocation,
)
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_support_v036 as support
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, resources, write
from scripts.software_development_v028 import available_cards, task

VERSION = "software-allocation-execution-v0.36"
SOURCE = Path(__file__).resolve().parents[1]
LIMITS = {**copy.deepcopy(support.LIMITS), "max_parallel_model_instances": 4,
          "task_seconds": {**support.LIMITS["task_seconds"], "training_step": 900}}
TERMINAL = {"complete", "stopped"}
REPORT_PATHS = ["docs/experiments/software-allocation-v036.md", "docs/experiments/software-allocation-v036.json"]


def frozen(root):
    root = Path(root)
    plan = support.validate_plan(read_json(root / "plan.json"))
    freeze = read_json(root / "postcollection-freeze.json")
    if (freeze.get("version") != "postcollection-freeze-v0.36"
            or freeze.get("automatic_execution") is not True
            or not freeze.get("automatic_execution_authorization")
            or freeze["P2_plan"] != reference(root / "plan.json")
            or freeze["P2_worker"] != reference(root / support.CANDIDATE / "actual/report.json")
            or freeze["P2_supervisor"] != reference(root / "supervisor.json")):
        raise ValueError("Require the actual trusted postcollection freeze and explicit automatic-execution authorization")
    for ref in freeze["P2_material"].values():
        support.checked(ref)
    support.checked(freeze["training_material_binding"])
    support.checked(freeze["common"])
    support.checked(freeze["support_gate"])
    allocation = freeze["allocation"]
    if allocation["plan_sha256"] != digest(json_bytes({k: v for k, v in allocation.items() if k != "plan_sha256"})):
        raise ValueError("The complete candidate freeze changed")
    if (len(allocation["development"]["units"]) != 16
            or len(allocation["development"]["independent_units"]) != 16
            or any(len({r["root_id"] for r in allocation["development"][panel]}) != 4
                   for panel in ("units", "independent_units"))):
        raise ValueError("Retain both four-root by four-seed local panels")
    return plan, freeze


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
            or report.get("backward_decisions_completed") != material["admitted_decisions"]
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
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.online_training import tensor_tree_digest
    from proworksim.software_learning_v036 import migrate_software_owner, restore_common, update_software_window
    from proworksim.software_runtime_v036 import collect, window_spec

    root, output = Path(run_root).resolve(), Path(output).resolve()
    plan, freeze = frozen(root)
    allocation = freeze["allocation"]
    formal = worker.startswith("formal-")
    key = worker.removeprefix("formal-") if formal else worker.removeprefix("trial-")
    if worker != ("formal-" if formal else "trial-") + key or (key not in METHODS if formal else key not in allocation["candidates"]):
        raise ValueError("Worker is outside the complete frozen candidate inventory")
    if worker != "trial-B" and not (root / "shared-B-cost-review.json").exists():
        raise ValueError("Measure and review the real shared B before further trials")
    if formal and not (root / "selection.json").exists():
        raise ValueError("All paired developer outcomes must close before formal selection")
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, support.GPU_ORDER)):
        raise ValueError("Exactly one declared assigned physical GPU is required")
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
            raise RuntimeError("Assigned empty A100 capacity changed before loading")
        refs = plan["parent"]["references"]
        saved = read_json(support.checked(refs["owner"]))
        old_plan = read_json(support.checked(refs["plan"]))
        model_plan = read_json(support.checked(old_plan["prior_model_plan"]))
        owner = DeterministicCandidateActor.from_candidate(model_plan["model"], manifest=support.checked(model_plan["manifest"]),
            profile=model_plan["runtime_profile"], recipe=saved["recipe"], output=output / "resident")
        write(output / "software-critic-migration.json", migrate_software_owner(owner, expected_steps=None))
        task(output, "restore-original-complete-common", "boundary")
        common_path = support.checked(freeze["common"])
        common = read_json(common_path)
        if (common_path.resolve() != (root / support.CANDIDATE / "actual/inherited-common.json").resolve()
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
        source = root / support.CANDIDATE / "actual/collection"
        entries, declaration, records = [read_json(source / name) for name in ("entries.json", "declaration.json", "records.json")]
        if support.current_support_gate(entries, declaration, records) != read_json(root / support.CANDIDATE / "actual/support-gate.json"):
            raise ValueError("Actual new-window support changed after its complete freeze")
        material = read_json(root / support.CANDIDATE / "actual/training-material-binding.json")
        composition = (bind_allocation(entries, declaration, records, allocation, read_json(root / "selection.json"), method=key)
                       if formal else bind_candidate(entries, declaration, records, allocation, key))
        task(output, "validate-complete-original-window-" + worker, "boundary")
        update_started = time.time()
        report.update(status="training", update_started_at=update_started)
        write(output / "report.json", report)
        with training_progress(owner, output):
            update = update_software_window(owner, entries, output / "update", declaration=declaration,
                request_evidence_root=source, composition=composition)
        update_ended = time.time()
        report.update(new_actor_steps=update["actor_optimizer_steps"], new_critic_steps=update["critic_optimizer_steps"],
            update=reference(output / "update/report.json"), update_ended_at=update_ended,
            complete_material_update_seconds=update_ended - update_started,
            material_scale={k: material[k] for k in ("original_slot_count", "admitted_decisions", "admitted_input_tokens", "admitted_own_output_tokens", "maximum_actual_sequence_tokens")})
        require_actual_update(update, material)
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
        collect(owner, window_spec("v036-" + worker + "-" + name, plan["inventories"][name], usage),
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
    folder = Path(root) / name / "actual"
    report = read_json(folder / "report.json")
    panel = read_json(support.checked(report["panel"]))
    plan = read_json(Path(root) / "plan.json")
    if (report["status"] != "complete" or report["source_before"] != plan["source"] or report["source_after"] != plan["source"]
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
    folder = root / "trial-B/actual"
    report = read_json(folder / "report.json")
    panel = read_json(folder / "panel-summary.json")
    verified_receipt(root, "trial-B", freeze["allocation"])
    state = read_json(root / "p3-supervisor.json")["states"]["trial-B"]
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
        "conditional_update_seconds_at_B_rate": updates * report["complete_material_update_seconds"],
        "conditional_development_seconds_at_B_rate": inventory["development_episodes"] * per_episode,
        "conditional_confirmation_seconds_at_B_development_rate": inventory["independent_episodes"] * per_episode,
        "estimate_scope": "Conditional workload arithmetic from one B observation, not a promise: candidate and TextFSM costs may differ; load/boundary/archive overhead is separate. All directions, failed candidates and three formal updates are counted.",
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
                        support.validate_plan(plan)
                        name = waiting.pop(0)
                        folder = root / name
                        folder.mkdir(exist_ok=False)
                        argv = [sys.executable, "-m", "scripts.software_allocation_v036", "worker", "--run-root", str(root),
                                "--worker", name, "--output", str(folder / "actual")]
                        logs[name] = (folder / "worker.log").open("x")
                        started = time.time()
                        process = subprocess.Popen(argv, cwd=SOURCE,
                            env=support.original.worker_env(plan, root, name, card["index"]),
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
                        own_rss, reason = rss(process.pid), guard.get("stop_reason")
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
        folder = root / name / "actual"
        report = read(folder / "report.json") or {}
        panel = read(folder / "panel-summary.json")
        live_panel = folder / ("confirmation" if name.startswith("formal-") else "development")
        if panel is None and (live_panel / "progress.json").exists():
            panel = {"rows": panel_rows(live_panel), "all_known": False, "partial": True}
        workers[name] = {"state": item, "report": report, "panel": panel,
                         "update_report": read(folder / "update/report.json")}
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
    usage = [r["actual_usage"] for worker in workers.values() for r in (worker["panel"] or {}).get("rows", [])
             if all(type(v) is int for v in r.get("actual_usage", {}).values()) and len(r.get("actual_usage", {})) == 4]
    cost = {"closed_P3_worker_gpu_seconds": sum(i.end_us - i.start_us for i in intervals) / 1_000_000,
        "closed_P3_worker_interval_union": support.interval_accounting(intervals, [])["totals"]["worker_union"],
        "running_P3_gpu_seconds": (state or {}).get("running_gpu_seconds", 0),
        "known_sampling_usage_units": len(usage),
        "sampling_usage": {key: sum(row[key] for row in usage) for key in ("decisions", "attempts", "charged_tokens", "test_runs")},
        "queue_and_CPU_archive_excluded_from_GPU_cost": True,
        "full_update_and_panel_intervals_are_nested_not_added_twice": True}
    trial_reports = [worker["report"] for name, worker in workers.items() if name.startswith("trial-")
                     and "gradient_tensor_digests" in worker["report"]]
    complete_geometry = bool(freeze and len(trial_reports) == len(freeze["allocation"]["candidates"]))
    actor_gradients = sorted({row["gradient_tensor_digests"]["actor"] for row in trial_reports})
    geometry = {"measured_trial_gradient_count": len(trial_reports), "all_frozen_trial_gradients_available": complete_geometry,
        "distinct_actor_gradient_tensor_digests": actor_gradients,
        "all_trial_actor_gradients_equal": len(actor_gradients) == 1 if complete_geometry else None,
        "scope": "Exact stored pre-clip gradient tensor equality, not a utility or causal-contribution estimate; incomplete directions remain unmeasured."}
    return {"version": VERSION, "status": state["status"] if state else "not_started", "source": plan["source"],
        "support": support.results(plan, root), "freeze": freeze, "shared_B_cost_review": read(root / "shared-B-cost-review.json"),
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
    write(destination / "software-allocation-v036.json", value)
    lines = ["# v0.36 条件B／G-raw／I-P真实学习与局部确认", "",
        f"状态：`{value['status']}`；源码：`{value['source']['code_commit']}`。", "",
        "新16槽支持先闭合，合格后冻结实际完整方向与面板。共同B一次测量真实输入／概率／完整反向与更新成本；其他试训及正式三分支均恢复相同完整common。开发和确认各4个root×4个seed，原始16槽、失败／unmapped残余及本人分母保持。", "",
        "| worker | 状态 | actor/critic新增步 | 完整材料更新秒 | 配对面板已知 |", "|---|---|---|---:|---|"]
    for name, row in value["workers"].items():
        r = row["report"]
        lines.append(f"| {name} | {row['state']['status']} | {r.get('new_actor_steps')}/{r.get('new_critic_steps')} | {r.get('complete_material_update_seconds')} | {r.get('panel_all_known')} |")
    lines += ["", "独立确认逐root（各方法分母4）：", "", "| root | B | G-raw | I-P |", "|---|---:|---:|---:|"]
    for case, scores in value["independent_successes_by_root_out_of_four"].items():
        lines.append(f"| {case} | {scores['B']} | {scores['G-raw']} | {scores['I-P']} |")
    lines += ["", f"独立局部平均差：I−B=`{value['I_minus_B']}`，I−G-raw=`{value['I_minus_G_raw']}`。null表示未测／未闭合，不能填0。", "",
        "D=16仍是有限机制面板，不保证Contribution精度。未检出方向差不能证明真实C=0；若q仅因先验／覆盖锚而变，不能称为发现高价值经历。正式更新预算相同不等于端到端探测资源相同，G-raw完整方向不删除。", "",
        "闭合开发／确认目录通过逐文件SHA复核后无损冷归档，原相对路径与字节均可恢复；原始支持材料保持可读。单任务、64GiB RSS、128GiB产物及20GiB磁盘余量保护保持，未恢复累计GPU／worker／统一墙钟上限。", ""]
    (destination / "software-allocation-v036.md").write_text("\n".join(lines))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("worker", "supervise", "report"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--worker")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt("v036 P3 received signal " + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    if args.mode == "worker":
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
