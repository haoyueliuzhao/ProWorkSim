"""Read-only six-run study accounting, preserving unfinished planned slots.

Use --allow-incomplete for an explicitly partial snapshot. No model, evaluator,
SQL, optimizer, checkpoint tensor or mutable world is executed or loaded.
"""

import argparse
import copy
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from scripts.online_report_v013 import _reward, _support, summarize_events

VERSION = "learning-study-readonly-v0.14"
TASKS = {"handoff", "implement", "review", "chain"}


class Reader:
    """Retain references, not hundreds of large episode payloads in memory."""

    def __init__(self):
        self.refs = {}

    def read(self, path, optional=True):
        path = Path(path).resolve()
        if optional and not path.is_file():
            return None
        raw = path.read_bytes()
        self.refs[str(path)] = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        return json.loads(raw)

    def ref(self, path):
        path = Path(path).resolve()
        if not path.is_file():
            return None
        if str(path) not in self.refs:
            sha, size = hashlib.sha256(), 0
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    sha.update(block)
                    size += len(block)
            self.refs[str(path)] = {"path": str(path), "sha256": sha.hexdigest(), "bytes": size}
        return copy.deepcopy(self.refs[str(path)])


def node_label(window, inherited_mode):
    mode = window.get("mode", inherited_mode)
    if mode not in {"online", "evaluate"}:
        raise ValueError("Unknown actual window mode")
    name = window["window_id"]
    if name.endswith("-dev-initial"):
        phase, node = "development", "0"
    elif match := re.search(r"-dev-(\d+)$", name):
        phase, node = "development", match[1]
    elif name.endswith("-locked-initial-common"):
        phase, node = "locked", "initial_common"
    elif name.endswith("-locked-final"):
        phase, node = "locked", "final"
    elif match := re.search(r"-train-(\d+)$", name):
        phase, node = "training", match[1]
    else:
        phase, node = "other", name
    if phase == "training" and mode != "online" or phase in {"locked", "development"} and mode != "evaluate":
        raise ValueError("Window label and declared actual mode disagree")
    return mode, phase, node


def steps_for_window(mode, update, started):
    """Never sum actor_steps_total; those are cumulative even in evaluations."""
    issues = []
    if mode == "evaluate":
        recorded = {name: (update or {}).get(name) for name in ("actor_optimizer_steps", "critic_optimizer_steps")}
        if any(value not in (None, 0) for value in recorded.values()):
            issues.append("evaluation_record_reports_nonzero_optimizer_steps")
        result = {"actor": 0, "critic": 0, "basis": "declared_evaluation_mode_no_update", "recorded_increment_fields": recorded}
    elif update is not None:
        result = {"actor": update.get("actor_optimizer_steps"), "critic": update.get("critic_optimizer_steps"), "basis": "saved_window_increment_fields"}
        for key in ("actor", "critic"):
            if type(result[key]) is not int or result[key] < 0:
                result[key] = None
                issues.append("missing_or_invalid_" + key + "_increment")
    elif not started:
        result = {"actor": 0, "critic": 0, "basis": "window_not_started_no_update"}
    else:
        result = {"actor": None, "critic": None, "basis": "started_online_window_update_unrecorded"}
    result["recorded_cumulative_totals"] = {key: (update or {}).get(key) for key in ("actor_steps_total", "critic_steps_total")}
    result["issues"] = issues
    return result


def aggregate_slots(slots):
    states = Counter(row["state"] for row in slots)
    known = [row for row in slots if row["state"] == "closed_known"]
    all_known = len(known) == len(slots) and bool(slots)
    rewards = [row["reward"]["reward"] for row in known]
    components = defaultdict(Counter)
    validity = Counter()
    for row in slots:
        value = row.get("work_validity")
        validity["missing" if value is None else str(value.get("value"))] += 1
    for row in known:
        for part in row["reward"].get("components", []):
            components[part["term_id"]]["observed"] += 1
            components[part["term_id"]]["achieved"] += part.get("achieved") is True
            components[part["term_id"]]["score_sum"] += part.get("score") or 0
    counts = {key: states.get(key, 0) for key in ("closed_known", "closed_unknown", "open", "interrupted_open", "not_started")}
    counts.update(planned=len(slots), closed=counts["closed_known"] + counts["closed_unknown"])
    return {"counts": counts, "all_planned_rewards_known": all_known,
            "observed_reward_sum": sum(rewards), "observed_reward_count": len(rewards),
            "mean_reward": sum(rewards) / len(slots) if all_known else None,
            "completed_work_count": sum(row["reward"].get("completed") is True for row in known),
            "components": {key: dict(value) for key, value in components.items()},
            "validity_counts": dict(validity),
            "scope": "Missing/interrupted/unstarted rewards are not zeros. Mean is withheld unless every planned slot has a known original reward. V and task completion are separate."}


def _slot(reader, folder, declared, summary, declaration, run_terminal):
    manifest = reader.read(folder / "episode/manifest.json")
    interrupted = reader.read(folder / "interruption.json")
    saved = summary.get(declared["slot_id"], {})
    reward, validity = saved.get("reward"), saved.get("work_validity")
    if manifest and manifest.get("status") == "closed" and (reward is None or validity is None):
        rollout = reader.read(folder / "team-rollout.json")
        if rollout:
            reward, validity = rollout.get("reward_eligibility"), rollout.get("work_validity")
    reward = _reward(reward)
    closed = bool(manifest and manifest.get("status") == "closed")
    numeric = bool(reward and reward.get("eligible") is True
                   and type(reward.get("reward")) in (int, float) and math.isfinite(reward["reward"]))
    state = ("closed_known" if numeric else "closed_unknown") if closed else (
        "interrupted_open" if manifest and run_terminal else "open" if manifest else "not_started")
    case = declared.get("case_id") or declared.get("case", {}).get("case_id")
    task = declared.get("case", {}).get("task") or (case or "").rsplit("-", 1)[-1]
    if task not in TASKS:
        raise ValueError("Cannot identify declared task responsibility")
    row = {"slot_id": declared["slot_id"], "case_id": case, "sampling_seed": declared.get("sampling_seed"),
           "pool": case.split("-v14-", 1)[0], "task": task,
           "deployment": "shared_weight_team" if task == "chain" else "single_role",
           "state": state, "prepared_world_exists": (folder / "world").is_dir(),
           "reward": reward, "work_validity": copy.deepcopy(validity),
           "active_members": (declaration or {}).get("active_members"),
           "boundary": saved.get("boundary"), "episode_id": (manifest or {}).get("episode_id"),
           "episode_manifest_ref": reader.ref(folder / "episode/manifest.json"),
           "interruption_ref": reader.ref(folder / "interruption.json"),
           "original_summary_status": saved.get("status"), "sampling": None}
    events, event_ref, scope = None, None, None
    if closed:
        history_path = folder / "episode" / manifest["experience"]["path"]
        history = reader.read(history_path, optional=False)
        event_ref = reader.ref(history_path)
        if event_ref["sha256"] != manifest["experience"]["sha256"]:
            raise ValueError("Closed experience hash differs from original manifest")
        events = history["events"][manifest["experience"]["start"]:manifest["experience"]["end"]]
        scope = "original_closed_episode_interval"
    elif manifest:
        runtime = (interrupted or {}).get("runtime") or reader.read(folder / "runtime.json")
        if runtime and isinstance(runtime.get("experience"), dict):
            events = runtime["experience"]["events"]
            event_ref = reader.ref(folder / ("interruption.json" if (interrupted or {}).get("runtime") else "runtime.json"))
            scope = "saved_open_prefix_only_no_fabricated_terminal"
    if events is not None:
        measured = summarize_events(events, declared_transport="resident_direct")
        row["sampling"] = {"scope": scope, "events_ref": event_ref,
                           "totals": measured["totals"], "members": measured["members"],
                           "resources": measured["resources"], "record_issues": measured["record_issues"],
                           "context_stops": sum(a["status"] == "backend_context_limit" for a in measured["attempts"])}
    return row


def _run(reader, job, scheduler_job, project, source):
    root = project / job["run"]
    protocol = reader.read(source / job["protocol"], optional=False)
    actual_protocol = reader.read(root / "online/protocol.json")
    report = reader.read(root / "online/report.json") or {}
    owner = reader.read(root / "resident/owner.json") or {}
    initial = reader.read(root / "online/initial-checkpoint/checkpoint.json") or {}
    condition, seed = protocol["condition"], protocol["replicate_index"]
    if condition not in {"mc", "rtg"} or type(seed) is not int:
        raise ValueError("Unknown declared study condition/seed")
    terminal = report.get("status") in {"complete", "error", "interrupted", "stopped_probability_mismatch"} or scheduler_job.get("status") == "finished"
    initial_identity = initial.get("actor_identity")
    issues = []
    if actual_protocol is not None and actual_protocol != protocol:
        issues.append("saved_protocol_differs_from_frozen_declared_protocol")
    if initial_identity and owner.get("initial_actor_identity") != initial_identity:
        issues.append("initial_owner_checkpoint_identity_mismatch")
    if initial and (initial.get("actor_steps") != 0 or initial.get("critic_steps") != 0):
        issues.append("initial_checkpoint_is_not_zero_step")
    if initial and initial.get("serialized_reload_exact") is not True:
        issues.append("initial_checkpoint_reload_not_verified")
    windows, task_rows, all_slots, sampling_totals = [], [], [], Counter()
    recorded_windows = {row["window_id"]: row for row in report.get("windows", [])}
    prior_identity, planned_training_seen = initial_identity, 0
    for wi, spec in enumerate(protocol["windows"]):
        folder = root / f"online/window-{wi}"
        collection = folder / "collection"
        mode, phase, node = node_label(spec, protocol.get("mode", "online"))
        declared = reader.read(collection / "declaration.json")
        saved_summary = reader.read(collection / "summary.json")
        progress = None if saved_summary else reader.read(collection / "progress.json")
        summary = {row["slot_id"]: row for row in (saved_summary or {}).get("slots", progress or [])}
        window_record = recorded_windows.get(spec["window_id"], {})
        update_path = folder / ("evaluation" if mode == "evaluate" else "update") / "report.json"
        update = reader.read(update_path) or window_record.get("update")
        checkpoint = reader.read(folder / "checkpoint/checkpoint.json")
        steps = steps_for_window(mode, update, bool(window_record or declared or folder.exists()))
        identity = (declared or {}).get("actor_identity") or window_record.get("before_actor_identity")
        row = {"index": wi, "window_id": spec["window_id"], "mode": mode, "phase": phase, "node": node,
               "planned_prior_training_windows": planned_training_seen, "status": window_record.get("status", "not_started"),
               "actor_identity": identity, "steps": steps, "checkpoint": checkpoint,
               "checkpoint_ref": reader.ref(folder / "checkpoint/checkpoint.json"),
               "update_ref": reader.ref(update_path), "update_status": (update or {}).get("status"),
               "update_evidence": {key: copy.deepcopy((update or {}).get(key)) for key in (
                   "before_actor_identity", "after_actor_identity", "behavior_probability_passed", "gradient_norms", "error")},
               "evaluation_guard": reader.read(folder / "evaluation-guard.json"),
               "declaration_ref": reader.ref(collection / "declaration.json"),
               "slots": []}
        if identity and prior_identity and identity != prior_identity:
            issues.append({"window_id": spec["window_id"], "reason": "sampling_identity_differs_from_prior_checkpoint"})
        if checkpoint:
            prior_identity = checkpoint.get("actor_identity")
        elif window_record.get("after_actor_identity"):
            prior_identity = window_record["after_actor_identity"]
        for si, slot in enumerate(spec["slots"]):
            declared_slot = next((s for s in (declared or {}).get("slots", []) if s["slot_id"] == slot["slot_id"]), None)
            item = _slot(reader, collection / f"slot-{si}", slot, summary, declared_slot, terminal)
            row["slots"].append(item)
            all_slots.append(item)
            if item["sampling"]:
                sampling_totals.update(item["sampling"]["totals"])
        row["progress"] = aggregate_slots(row["slots"])
        support = reader.read(collection / "support.json")
        row["support"] = _support(support)
        row["support_ref"] = reader.ref(collection / "support.json")
        row["support_pooling"] = "none; saved per-window xi/theta/Gamma/member blocks and b only"
        signal_path = folder / "update/signal-diagnostics.json"
        signal = reader.read(signal_path)
        row["signal"] = None if signal is None else {
            "ref": reader.ref(signal_path), "version": signal.get("version"), "scope": signal.get("scope"),
            "groups": [{k: copy.deepcopy(v) for k, v in group.items() if k != "call_ids"} for group in signal.get("groups", [])],
            "gradient_capture": copy.deepcopy(signal.get("gradient_capture"))}
        shift_path = folder / "update/post-update-sampled-policy.json"
        row["post_update_sampled_policy_ref"] = reader.ref(shift_path)
        grouped = defaultdict(list)
        for item in row["slots"]:
            grouped[(item["pool"], item["task"], item["deployment"])].append(item)
        for (pool, task, deployment), items in grouped.items():
            task_rows.append({"condition": condition, "seed": seed, "window_id": spec["window_id"],
                              "window_index": wi, "phase": phase, "node": node, "pool": pool,
                              "task": task, "deployment": deployment, **aggregate_slots(items),
                              "slot_refs": [{"slot_id": item["slot_id"], "case_id": item["case_id"], "sampling_seed": item["sampling_seed"],
                                             "manifest": item["episode_manifest_ref"]} for item in items]})
        planned_training_seen += mode == "online"
        windows.append(row)
    observed_steps = {key: sum(w["steps"][key] for w in windows if w["steps"][key] is not None) for key in ("actor", "critic")}
    unknown_step_windows = [w["window_id"] for w in windows if any(w["steps"][key] is None for key in ("actor", "critic"))]
    for key in ("actor", "critic"):
        total = report.get(key + "_steps_total")
        if total is not None and not unknown_step_windows and total != observed_steps[key]:
            issues.append("recorded_final_" + key + "_total_differs_from_sum_of_window_increments")
    initial_probe = next((window for window in windows if window["phase"] == "development" and window["node"] == "0"), None)
    initial_learning_guard = (initial_probe or {}).get("evaluation_guard")
    launch = project / job["launch"]
    refs = {suffix: reader.ref(str(launch) + suffix) for suffix in (".launch.json", ".resources.jsonl", ".log")}
    launch_record = reader.read(str(launch) + ".launch.json")
    return {"name": job["name"], "condition": condition, "seed": seed, "root": str(root.resolve()),
            "scheduler_job": copy.deepcopy(scheduler_job), "runner_status": report.get("status", "not_started_or_unrecorded"),
            "runner_report_ref": reader.ref(root / "online/report.json"), "source_before": reader.read(root / "source-before.json"),
            "source_after": reader.read(root / "source-after.json"), "source_comparison": reader.read(root / "source-comparison.json"),
            "declared_protocol_ref": reader.ref(source / job["protocol"]), "saved_protocol_ref": reader.ref(root / "online/protocol.json"),
            "saved_protocol_equals_declared": None if actual_protocol is None else actual_protocol == protocol,
            "initial_actor_identity": initial_identity, "owner_initial_actor_identity": owner.get("initial_actor_identity"),
            "initial_learning_guard": initial_learning_guard,
            "initial_learning_guard_ref": reader.ref(root / f"online/window-{initial_probe['index']}/evaluation-guard.json") if initial_probe else None,
            "initial_checkpoint": initial, "initial_checkpoint_ref": reader.ref(root / "online/initial-checkpoint/checkpoint.json"),
            "owner_ref": reader.ref(root / "resident/owner.json"), "final_actor_identity": report.get("final_actor_identity"),
            "observed_optimizer_step_increments": observed_steps, "unknown_step_windows": unknown_step_windows,
            "recorded_cumulative_final_steps": {key: report.get(key + "_steps_total") for key in ("actor", "critic")},
            "windows": windows, "task_summaries": task_rows, "progress": aggregate_slots(all_slots),
            "observed_sampling_totals": dict(sampling_totals),
            "sampling_accounting_scope": "Known closed episodes and saved open prefixes only; live/unrecorded sampling is unknown, never invented zero usage.",
            "launch_record": launch_record, "launcher_resource_refs": refs, "issues": issues}


def shared_baselines(runs):
    result = []
    for seed in sorted({run["seed"] for run in runs}):
        pair = {run["condition"]: run for run in runs if run["seed"] == seed}
        mc, rtg = pair.get("mc"), pair.get("rtg")
        if mc is None or rtg is None:
            result.append({"seed": seed, "reuse_allowed": False, "reason": "missing_declared_condition_pair", "source_window": None})
            continue
        ids = [run.get("initial_actor_identity") for run in (mc, rtg)]
        initial_match = None if any(identity is None for identity in ids) else ids[0] == ids[1]
        owner_match = all(run.get("owner_initial_actor_identity") == identity and identity is not None for run, identity in zip((mc, rtg), ids))
        zero_step = all(run["initial_checkpoint"].get("actor_steps") == 0 and run["initial_checkpoint"].get("critic_steps") == 0
                        and run["initial_checkpoint"].get("serialized_reload_exact") is True for run in (mc, rtg))
        learning_keys = ("actor", "critic", "actor_optimizer", "critic_optimizer", "policy_revision", "actor_steps", "critic_steps", "critic_has_nonzero_reward_history")
        guards = [run.get("initial_learning_guard") or {} for run in (mc, rtg)]
        learning_values = [{key: guard.get("learning_before_sha256", {}).get(key) for key in learning_keys} for guard in guards]
        learning_recorded = all(value is not None for row in learning_values for value in row.values())
        learning_equal = learning_values[0] == learning_values[1] if learning_recorded else None
        learning_unchanged = all(guard.get("learning_unchanged") is True and guard.get("rng_restored_exactly") is True for guard in guards)
        candidates = [w for w in mc["windows"] if w["phase"] == "locked" and w["node"] == "initial_common"]
        if len(candidates) != 1:
            raise ValueError("Exactly one MC common initial locked window per seed is required")
        if any(w["phase"] == "locked" and w["node"] == "initial_common" for w in rtg["windows"]):
            raise ValueError("RTG must reference, not duplicate, the declared common locked baseline")
        baseline = candidates[0]
        sampled_match = None if baseline["actor_identity"] is None or ids[0] is None else baseline["actor_identity"] == ids[0]
        allowed = initial_match is True and owner_match and zero_step and sampled_match is True
        result.append({"seed": seed, "source_condition": "mc", "source_run": mc["name"],
                       "source_window": baseline["window_id"], "reused_for_conditions": ["mc", "rtg"],
                       "initial_actor_identity_match": initial_match, "owner_checkpoint_identities_match": owner_match,
                       "initial_checkpoints_zero_step_and_reload_exact": zero_step,
                       "initial_actor_critic_optimizer_fingerprints_match": learning_equal,
                       "initial_learning_fingerprints": {"mc": learning_values[0], "rtg": learning_values[1]},
                       "initial_probe_learning_and_rng_guards_passed": learning_unchanged,
                       "initial_learning_guard_refs": [run.get("initial_learning_guard_ref") for run in (mc, rtg)],
                       "initial_state_scope": "Compares actual saved initial-probe fingerprints of actor, critic, both optimizer states and step/revision fields. Whole checkpoint digests differ by the declared credit recipe and are not equated. No tensor file is loaded.",
                       "baseline_sampling_identity_matches_initial": sampled_match, "reuse_allowed": allowed,
                       "complete_baseline": baseline["progress"]["all_planned_rewards_known"],
                       "initial_checkpoint_refs": [mc["initial_checkpoint_ref"], rtg["initial_checkpoint_ref"]],
                       "baseline_declaration_ref": baseline["declaration_ref"], "baseline_progress": baseline["progress"],
                       "task_summary_refs": [{key: row[key] for key in ("window_id", "pool", "task", "deployment")}
                                             for row in mc["task_summaries"] if row["window_id"] == baseline["window_id"]],
                       "scope": "Count baseline episodes/tokens once under their original MC run. Reuse links are not new RTG trajectories or independent source samples."})
    return result


def locked_comparisons(runs, baselines):
    result = []
    for run in runs:
        baseline = next(b for b in baselines if b["seed"] == run["seed"])
        origin = next((r for r in runs if r["seed"] == run["seed"] and r["condition"] == "mc"), None)
        initial = [r for r in (origin or {}).get("task_summaries", []) if r["phase"] == "locked" and r["node"] == "initial_common"]
        finals = [r for r in run["task_summaries"] if r["phase"] == "locked" and r["node"] == "final"]
        for final in finals:
            first = next((r for r in initial if (r["pool"], r["task"], r["deployment"]) == (final["pool"], final["task"], final["deployment"])), None)
            same_cases = bool(first) and [(r["case_id"], r["sampling_seed"]) for r in first["slot_refs"]] == [(r["case_id"], r["sampling_seed"]) for r in final["slot_refs"]]
            ready = baseline["reuse_allowed"] and same_cases and first["all_planned_rewards_known"] and final["all_planned_rewards_known"]
            result.append({"condition": run["condition"], "seed": run["seed"], "pool": final["pool"],
                           "task": final["task"], "deployment": final["deployment"],
                           "initial_source_window": baseline.get("source_window"), "final_window": final["window_id"],
                           "same_declared_cases_and_sampling_seeds": same_cases, "comparison_ready": ready,
                           "initial_mean_reward": first["mean_reward"] if first and baseline["reuse_allowed"] else None,
                           "final_mean_reward": final["mean_reward"],
                           "delta_mean_reward": final["mean_reward"] - first["mean_reward"] if ready else None,
                           "initial_counts": first["counts"] if first else None, "final_counts": final["counts"],
                           "scope": "Incomplete/mismatched groups have no delta; a mean change is descriptive, not a statistical/generalization conclusion."})
    return result


def build_report(scheduler_path, *, project_root, allow_incomplete=False):
    reader = Reader()
    scheduler = reader.read(scheduler_path, optional=False)
    manifest = scheduler["manifest"]
    jobs = manifest["jobs"]
    if len({j["name"] for j in jobs}) != len(jobs):
        raise ValueError("Manifest job names must be unique")
    source, project = Path(scheduler["source"]).resolve(), Path(project_root).resolve()
    running = {job["name"]: job for job in scheduler.get("jobs", [])}
    runs = [_run(reader, job, running.get(job["name"], {}), project, source) for job in jobs]
    if len({(run["condition"], run["seed"]) for run in runs}) != len(runs):
        raise ValueError("Duplicate declared condition/seed run")
    complete = all(run["runner_status"] == "complete" and run["progress"]["all_planned_rewards_known"] for run in runs)
    if not complete and not allow_incomplete:
        raise ValueError("Study is incomplete; explicitly use --allow-incomplete for a progress snapshot")
    terminal_statuses = {"complete", "error", "interrupted", "stopped_probability_mismatch"}
    all_terminal = all(run["runner_status"] in terminal_statuses or run["scheduler_job"].get("status") == "finished" for run in runs)
    baselines = shared_baselines(runs)
    all_slots = [slot for run in runs for window in run["windows"] for slot in window["slots"]]
    totals = Counter()
    for run in runs:
        totals.update(run["observed_sampling_totals"])
    return {"version": VERSION, "status": "complete_recorded_study" if complete else "terminated_incomplete_study" if all_terminal else "incomplete_progress_snapshot",
            "all_declared_runs_terminal": all_terminal, "all_planned_episode_rewards_known": complete,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(), "mode": "read_only_original_scores_no_reassessment",
            "scheduler_status": scheduler.get("status"), "scheduler_ref": reader.ref(scheduler_path),
            "declared_manifest": manifest, "frozen_source_root": str(source), "planned_runs": len(jobs),
            "runs": runs, "shared_initial_locked_baselines": baselines,
            "locked_comparisons": locked_comparisons(runs, baselines), "progress": aggregate_slots(all_slots),
            "observed_sampling_totals": dict(totals),
            "observed_optimizer_step_increments": {key: sum(run["observed_optimizer_step_increments"][key] for run in runs) for key in ("actor", "critic")},
            "references": reader.refs,
            "limitations": [
                "A live report is a per-file read snapshot, not a globally atomic scheduler/episode snapshot; it is not a premature success/failure conclusion.",
                "No model/evaluator/SQL/optimizer execution or tensor checkpoint load occurs. Scalar/component rewards and V are original saved values.",
                "Unknown, open and unstarted slots remain distinct; absent rewards are never zero. Only complete known groups get mean rewards/deltas.",
                "Optimizer increments come from each window's actual mode and increment fields; cumulative totals on evaluation/checkpoints are never summed as new steps.",
                "Initial MC locked episodes are counted once per seed and reused only after actual initial actor/checkpoint identity validation; reuse creates no new samples.",
                "Current support b/class counts retain each original xi/theta/Gamma/member window; they are never pooled across policies or conditions.",
                "Single-role responsibility and shared-weight full-team chains are separate groupings; seeds are replications within one source family, not independent projects.",
                "Direct transport retains HTTP-shaped field names but has no implied network HTTP. Unrecorded live sampling is not zero resource usage.",
            ]}



def compact_report(report, full_reference):
    """Archival table; full evidence and raw component citations remain linked."""
    result = {key: copy.deepcopy(report[key]) for key in (
        "version", "status", "all_declared_runs_terminal", "all_planned_episode_rewards_known",
        "captured_at_utc", "mode", "scheduler_status", "scheduler_ref", "planned_runs", "progress",
        "observed_sampling_totals", "observed_optimizer_step_increments", "shared_initial_locked_baselines",
        "locked_comparisons", "limitations",
    )}
    result.update(full_report=full_reference, runs=[])
    for run in report["runs"]:
        row = {key: copy.deepcopy(run[key]) for key in (
            "name", "condition", "seed", "runner_status", "runner_report_ref", "source_before", "source_after",
            "source_comparison", "declared_protocol_ref", "saved_protocol_ref", "saved_protocol_equals_declared",
            "initial_actor_identity", "initial_checkpoint_ref", "initial_learning_guard_ref", "final_actor_identity",
            "observed_optimizer_step_increments", "recorded_cumulative_final_steps", "unknown_step_windows",
            "progress", "observed_sampling_totals", "sampling_accounting_scope", "task_summaries",
            "launch_record", "launcher_resource_refs", "issues",
        )}
        row["windows"] = []
        for window in run["windows"]:
            item = {key: copy.deepcopy(window[key]) for key in (
                "index", "window_id", "mode", "phase", "node", "planned_prior_training_windows", "status",
                "actor_identity", "steps", "checkpoint_ref", "update_ref", "update_status", "update_evidence",
                "declaration_ref", "progress", "support", "support_ref", "support_pooling", "post_update_sampled_policy_ref",
            )}
            item["signal_ref"] = (window.get("signal") or {}).get("ref")
            item["slot_outcomes"] = []
            for slot in window["slots"]:
                reward = slot.get("reward")
                validity = slot.get("work_validity")
                item["slot_outcomes"].append({
                    **{key: copy.deepcopy(slot[key]) for key in ("slot_id", "case_id", "sampling_seed", "pool", "task", "deployment", "state", "episode_manifest_ref")},
                    "reward": None if reward is None else {key: copy.deepcopy(reward.get(key)) for key in ("eligible", "reward", "completed", "exclusions")},
                    "reward_components": None if reward is None else [{key: copy.deepcopy(part.get(key)) for key in ("term_id", "weight", "achieved", "score")} for part in reward.get("components", [])],
                    "work_validity": None if validity is None else {"value": validity.get("value"), "spec_id": validity.get("spec_id"),
                        "components": {key: value.get("value") for key, value in validity.get("components", {}).items()}},
                    "sampling": None if slot["sampling"] is None else {key: copy.deepcopy(slot["sampling"][key]) for key in ("scope", "events_ref", "totals", "context_stops", "resources")},
                })
            row["windows"].append(item)
        result["runs"].append(row)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheduler", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--summary", type=Path, help="Optional new archival JSON linked to the full report")
    args = parser.parse_args()
    scheduler = json.loads(args.scheduler.read_text())
    protected = [Path(scheduler["source"]).resolve(), args.scheduler.resolve().parent]
    protected += [(args.project_root / job["run"]).resolve() for job in scheduler["manifest"]["jobs"]]
    output = args.output.resolve()
    destinations = [output] + ([args.summary.resolve()] if args.summary is not None else [])
    if len(set(destinations)) != len(destinations) or any(target.exists() or any(target.is_relative_to(path) for path in protected) for target in destinations):
        raise ValueError("Write new distinct reports outside original run/scheduler/frozen-source trees")
    report = build_report(args.scheduler, project_root=args.project_root, allow_incomplete=args.allow_incomplete)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    if args.summary is not None:
        raw = output.read_bytes()
        summary = compact_report(report, {"path": str(output), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(output), "status": report["status"], "planned_runs": report["planned_runs"],
                      "progress": report["progress"]["counts"], "new_optimizer_steps": report["observed_optimizer_step_increments"]}))


if __name__ == "__main__":
    main()
