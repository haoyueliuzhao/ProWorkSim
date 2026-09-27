"""Read-only H1 accounting and frozen relative model/harness selection.

No model, optimizer, evaluator, SQL, or hidden answer is executed. Missing values
stay unknown; final selection waits for both actual model processes to end.
"""

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from proworksim.storage import digest, json_bytes
from scripts.build_harness_study_v017 import SELECTION

VERSION = "harness-readonly-report-v0.17"
CANDIDATES = ("qwen35-9b", "qwen38-27b")
HARNESSES = ("native_v15", "openhands_v16")
TASKS = ("implement", "review", "pair", "chain")
AUXILIARY = {"work_note", "work_todo", "work_history_search", "work_history_read"}
TERMINAL = {"complete", "error", "interrupted", "stopped_probability_mismatch"}


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


class Reader:
    def __init__(self):
        self.cache, self.references, self.errors = {}, {}, []

    def read(self, path):
        path = Path(path).resolve()
        key = str(path)
        if key not in self.cache:
            try:
                raw = path.read_bytes()
            except FileNotFoundError:
                self.cache[key] = None
            else:
                self.references[key] = {
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                }
                try:
                    self.cache[key] = json.loads(raw)
                except (ValueError, UnicodeError) as error:
                    self.errors.append({"path": key, "error": type(error).__name__})
                    self.cache[key] = None
        return self.cache[key]

    def ref(self, path):
        self.read(path)
        key = str(Path(path).resolve())
        return {"path": key, **self.references[key]} if key in self.references else None


def counts_and_means(rows):
    known = [r for r in rows if r["state"] == "closed_known"]
    all_known = bool(rows) and len(known) == len(rows)
    states = Counter(r["state"] for r in rows)
    task_rows = {task: [r for r in rows if r["task"] == task] for task in TASKS}
    means = {
        task: sum(r["reward"] for r in items) / len(items)
        if items and all(r["state"] == "closed_known" for r in items)
        else None
        for task, items in task_rows.items()
    }
    return {
        "planned": len(rows),
        "states": dict(states),
        "known": len(known),
        "observed_reward_sum": sum(r["reward"] for r in known),
        "observed_complete_count": sum(r["completed"] is True for r in known),
        "raw_mean": sum(r["reward"] for r in known) / len(rows) if all_known else None,
        "completion_rate": sum(r["completed"] is True for r in known) / len(rows)
        if all_known
        else None,
        "task_means": means,
        "task_counts": {task: len(items) for task, items in task_rows.items()},
        "task_macro_mean": sum(means.values()) / 4
        if all(v is not None for v in means.values())
        else None,
        "missing_rule": "Means/rates withheld when any declared constituent is unknown or unstarted; no zero imputation.",
    }


def paired_comparison(rows):
    grouped = {}
    for row in rows:
        key = (row["case_id"], row["repeat"])
        group = grouped.setdefault(key, {})
        if row["harness"] in group:
            raise ValueError("Duplicate case/repeat/harness measurement")
        group[row["harness"]] = row
    pairs = []
    for (case_id, repeat), group in sorted(grouped.items()):
        native, sdk = group.get("native_v15"), group.get("openhands_v16")
        known = (
            native is not None
            and sdk is not None
            and all(r["state"] == "closed_known" for r in (native, sdk))
        )
        pairs.append(
            {
                "case_id": case_id,
                "repeat": repeat,
                "task": (native or sdk)["task"],
                "native_slot": native["slot_id"] if native else None,
                "sdk_slot": sdk["slot_id"] if sdk else None,
                "native_reward": native["reward"] if native else None,
                "sdk_reward": sdk["reward"] if sdk else None,
                "known_pair": known,
                "sdk_minus_native": sdk["reward"] - native["reward"] if known else None,
            }
        )
    complete = len(pairs) == 12 and all(p["known_pair"] for p in pairs)
    task_deltas = {}
    for task in TASKS:
        subset = [p for p in pairs if p["task"] == task]
        task_deltas[task] = (
            sum(p["sdk_minus_native"] for p in subset) / len(subset)
            if subset and all(p["known_pair"] for p in subset)
            else None
        )
    return {
        "pairs": pairs,
        "planned_pairs": len(pairs),
        "known_pairs": sum(p["known_pair"] for p in pairs),
        "paired_raw_delta": sum(p["sdk_minus_native"] for p in pairs) / 12 if complete else None,
        "task_deltas": task_deltas,
        "paired_task_macro_delta": sum(task_deltas.values()) / 4 if complete else None,
        "fact_denominator": len({p["case_id"] for p in pairs}),
        "interpretation": "Six development situations with two repeats, not 24 independent projects. Same seeds do not imply identical text. No subtraction from S1.",
    }


def _observations(messages):
    for message in messages:
        if message.get("role") != "user" or not isinstance(message.get("content"), str):
            continue
        try:
            value = json.loads(message["content"])
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get("observation"), dict):
            yield value["observation"]


def _tool_result_present(messages, tool_id, result):
    for message in messages:
        if message.get("role") != "tool" or message.get("tool_call_id") != tool_id:
            continue
        try:
            if json.loads(message.get("content", "")) == result:
                return True
        except (ValueError, TypeError):
            pass
    return False


def behavior(events, reward, limits, *, reader, run_root):
    """Extract factual breakpoints, without labeling causality or re-evaluating SQL."""
    attempts = [
        e
        for e in events
        if e.get("kind") == "model_attempt" and e.get("payload", {}).get("stage") == "finished"
    ]
    responses = {
        e["payload"]["call_id"]: e["payload"]["response"]
        for e in events
        if e.get("kind") == "model_response"
    }
    decisions, decision_seen = [], set()
    for event in events:
        if event.get("kind") != "policy_decision":
            continue
        decision = event["payload"]["decision"]
        call_id = decision.get("model_call_id")
        if call_id in decision_seen:
            continue
        decision_seen.add(call_id)
        decisions.append(
            {"sequence": event["sequence"], "role": event.get("worker_id"), **decision}
        )
    decision_by_call = {d["model_call_id"]: d for d in decisions if d.get("model_call_id")}
    attempt_by_call = {a["payload"]["call_id"]: a for a in attempts}
    world = [e for e in events if e.get("kind") == "tool_call"]

    def position(event):
        p = event["payload"]
        attempt = attempt_by_call.get(p.get("model_call_id"))
        index = attempt["payload"].get("decision_index") if attempt else None
        role = event.get("worker_id")
        return {
            "sequence": event["sequence"],
            "role": role,
            "model_call_id": p.get("model_call_id"),
            "decision_index": index,
            "role_limit": limits.get(role),
            "remaining_role_decisions": limits[role] - index
            if type(index) is int and role in limits
            else None,
        }

    builds = [
        {
            **position(e),
            "gateway_ok": e["payload"]["response"].get("ok"),
            "execution_status": e["payload"]["response"].get("result", {}).get("execution_status"),
            "reference": e["payload"]["response"].get("result", {}).get("reference"),
        }
        for e in world
        if e["payload"].get("action") == "sql_build"
    ]
    components = {c["term_id"]: c for c in reward.get("components", [])}
    correct = components.get("correct_actual_build", {})
    authoritative_sequence = (
        (correct.get("evidence") or {}).get("action_sequence") if correct.get("achieved") else None
    )
    first_correct = next((b for b in builds if b["sequence"] == authoritative_sequence), None)
    submissions = [
        {
            **position(e),
            "ok": e["payload"]["response"].get("ok"),
            "response": e["payload"]["response"],
        }
        for e in world
        if e["payload"].get("action") == "submit"
    ]
    errors = []
    for event in world:
        p = event["payload"]
        result = p["response"]
        result_payload = result.get("result") if isinstance(result.get("result"), dict) else {}
        execution_error = result_payload.get("execution_status") == "execution_error"
        if result.get("ok") is not False and not execution_error:
            continue
        later = next(
            (
                a
                for a in attempts
                if a.get("worker_id") == event.get("worker_id")
                and a["sequence"] > event["sequence"]
            ),
            None,
        )
        public_next = None
        native_next = None
        rendered_next = None
        next_action = None
        if later:
            lp = later["payload"]
            public_next = _tool_result_present(
                lp["request"]["messages"], p.get("model_tool_call_id"), result
            )
            body = lp.get("response", {}).get("body") or {}
            owner_path = run_root / "resident/calls" / (str(body.get("id")) + ".json")
            owner = reader.read(owner_path)
            if owner:
                native_next = _tool_result_present(
                    owner.get("actual_prompt_messages", []), p.get("model_tool_call_id"), result
                )
                rendered_next = any(
                    m.get("role") == "tool"
                    and m.get("tool_call_id") == p.get("model_tool_call_id")
                    and m.get("content", "") in owner.get("rendered_prompt", "")
                    for m in lp["request"]["messages"]
                )
            decision = decision_by_call.get(lp["call_id"])
            if decision:
                obligation = p.get("arguments", {}).get("work_id")
                next_action = {
                    "name": decision.get("action"),
                    "arguments": decision.get("arguments"),
                    "same_explicit_work_id": decision.get("arguments", {}).get("work_id")
                    == obligation
                    if obligation is not None and "work_id" in decision.get("arguments", {})
                    else None,
                    "repair_effect": "unknown_not_inferred_from_tool_name",
                }
        errors.append(
            {
                **position(event),
                "tool": p["action"],
                "actual_error": result.get("error") or result_payload.get("error"),
                "next_actual_request_contains_exact_result": public_next,
                "next_native_prompt_contains_exact_result": native_next,
                "next_rendered_prompt_contains_exact_text": rendered_next,
                "next_action": next_action,
            }
        )
    providers = []
    for event in attempts:
        p = event["payload"]
        role = event.get("worker_id")
        obligations = []
        for obs in _observations(p.get("request", {}).get("messages", [])):
            for condition_id, condition in obs.get("conditions", {}).items():
                if role in condition.get("providers", []) and condition.get("status") == "open":
                    obligations.append(
                        {
                            "condition_id": condition_id,
                            "request_id": condition.get("request_id"),
                            "work_id": condition.get("work_item_id"),
                            "purpose": condition.get("purpose"),
                        }
                    )
        if obligations:
            providers.append(
                {
                    "role": role,
                    "decision_index": p.get("decision_index"),
                    "model_call_id": p["call_id"],
                    "visible_open_obligations": obligations,
                    "chosen_action": decision_by_call.get(p["call_id"], {}).get("action"),
                    "diagnostic": "Visible in actual selected input; understanding or use is not inferred.",
                }
            )
    auxiliary = []
    for decision in decisions:
        if decision.get("action") not in AUXILIARY:
            continue
        body = responses.get(decision["model_call_id"], {})
        trace = body.get("token_trace", {})
        auxiliary.append(
            {
                "role": decision["role"],
                "model_call_id": decision["model_call_id"],
                "action": decision["action"],
                "one_model_decision": True,
                "input_tokens": len(trace["input_ids"])
                if isinstance(trace.get("input_ids"), list)
                else None,
                "output_tokens": len(trace["output_ids"])
                if isinstance(trace.get("output_ids"), list)
                else None,
            }
        )
    token_lengths = []
    for attempt in attempts:
        body = attempt["payload"].get("response", {}).get("body") or {}
        trace = body.get("token_trace", {}) if isinstance(body, dict) else {}
        token_lengths.append(
            {
                name: len(trace[key]) if isinstance(trace.get(key), list) else None
                for name, key in (("input", "input_ids"), ("output", "output_ids"))
            }
        )
    return {
        "actual_builds": builds,
        "first_actual_build": builds[0] if builds else None,
        "saved_independent_correct_build": first_correct,
        "correct_build_evidence": correct.get("evidence"),
        "earliest_correct_build": "unknown_unless_saved_evaluator_identifies_it; no reward replay",
        "submit_attempts": submissions,
        "correct_fixed_submission": components.get("correct_fixed_submission", {}).get("achieved"),
        "review_decision": components.get("correct_review_decision", {}).get("achieved"),
        "staff_done_count": sum(
            d.get("kind") == "done" or d.get("action") == "staff_done" for d in decisions
        ),
        "errors_and_next_inputs": errors,
        "provider_obligation_actions": providers,
        "auxiliary_decisions": auxiliary,
        "auxiliary_opportunities": len(auxiliary),
        "auxiliary_input_tokens": sum(a["input_tokens"] for a in auxiliary)
        if all(a["input_tokens"] is not None for a in auxiliary)
        else None,
        "auxiliary_output_tokens": sum(a["output_tokens"] for a in auxiliary)
        if all(a["output_tokens"] is not None for a in auxiliary)
        else None,
        "all_model_attempts": len(attempts),
        "input_tokens": sum(row["input"] for row in token_lengths)
        if all(row["input"] is not None for row in token_lengths)
        else None,
        "output_tokens": sum(row["output"] for row in token_lengths)
        if all(row["output"] is not None for row in token_lengths)
        else None,
        "attempts_missing_original_token_counts": sum(
            any(x is None for x in row.values()) for row in token_lengths
        ),
        "measured_input_tokens": sum(
            row["input"] for row in token_lengths if row["input"] is not None
        ),
        "measured_output_tokens": sum(
            row["output"] for row in token_lengths if row["output"] is not None
        ),
        "causal_failure_explanation": None,
        "counting_scope": "One model call per decision; work_replace_text world write receipt is not a second actor action. Tool ok/build/submit/review/staff_done are separate.",
    }


def _validity(rollout, dimension):
    return (
        (rollout or {})
        .get("work_validity", {})
        .get("components", {})
        .get(dimension, {})
        .get("value")
    )


def _guard(window_record):
    guard = window_record.get("evaluation_guard", {})
    update = window_record.get("update", {})
    return (
        window_record.get("status") == "complete"
        and window_record.get("mode") == "evaluate"
        and guard.get("learning_unchanged") is True
        and guard.get("rng_restored_exactly") is True
        and bool(guard.get("learning_before_sha256"))
        and guard.get("learning_before_sha256") == guard.get("learning_after_sha256")
        and bool(guard.get("rng_before_sha256"))
        and guard.get("rng_before_sha256") == guard.get("rng_after_restore_sha256")
        and update.get("actor_optimizer_steps") == 0
        and update.get("critic_optimizer_steps") == 0
    )


def read_model(candidate, run_root, launch_path, protocol_path=None, *, reader):
    run_root = Path(run_root).resolve()
    launch = reader.read(launch_path)
    saved = reader.read(run_root / "launch-protocol.json")
    declared = reader.read(protocol_path) if protocol_path else None
    protocol = saved or declared
    if protocol is None:
        return {
            "candidate_id": candidate,
            "state": "not_started_no_protocol",
            "ended": False,
            "rows": [],
            "arms": [],
            "issues": ["missing declared protocol"],
        }
    if (
        protocol.get("candidate_id") != candidate
        or protocol.get("combination_selection") != SELECTION
    ):
        raise ValueError("Candidate identity or frozen selection rule differs")
    if (
        saved
        and declared
        and (
            {k: v for k, v in saved.items() if k != "launch_gate"}
            != {k: v for k, v in declared.items() if k != "launch_gate"}
        )
    ):
        raise ValueError("Supplied protocol differs from actual launch protocol outside admission")
    source_before = reader.read(run_root / "source-before.json")
    source_after = reader.read(run_root / "source-after.json")
    source_comparison = reader.read(run_root / "source-comparison.json")
    online = reader.read(run_root / "online/report.json") or {}
    saved_online_protocol = reader.read(run_root / "online/protocol.json")
    owner = reader.read(run_root / "resident/owner.json") or {}
    initial = owner.get("initial_actor_identity")
    devices = protocol["runtime"]["profile"]["devices"]
    ended = bool(launch and finite(launch.get("end")) and type(launch.get("exit_code")) is int)
    process_seconds = launch.get("elapsed") if ended and finite(launch.get("elapsed")) else None
    command = (launch or {}).get("command", [])
    command_output = command[command.index("--output") + 1] if "--output" in command else None
    launch_binding = bool(
        command_output
        and Path(command_output).resolve() == run_root
        and len((launch or {}).get("CUDA_VISIBLE_DEVICES", "").split(",")) == devices
    )
    fresh = (
        protocol.get("initialization", {}).get("kind") == "fresh_public_base"
        and protocol["initialization"].get("same_resident_actor_for_all_four_windows") is True
        and protocol["initialization"].get("restore_checkpoint_permitted") is False
        and "--restore-checkpoint" not in command
        and not (run_root / "restored-checkpoint.json").exists()
        and bool(initial)
    )
    source_ok = bool(
        source_before
        and source_after
        and source_before == source_after
        and source_before.get("code_dirty") is False
        and (source_comparison or {}).get("unchanged") is True
    )
    zero = online.get("actor_steps_total") == online.get("critic_steps_total") == 0
    protocol_ok = bool(
        saved
        and saved_online_protocol == saved
        and online.get("protocol_sha256") == digest(json_bytes(saved))
    )
    final_identity = online.get("final_actor_identity")
    identity_ok = bool(initial and final_identity == initial)
    windows = {w["window_id"]: w for w in online.get("windows", [])}
    rows = []
    for wi, spec in enumerate(protocol["windows"]):
        collection = run_root / f"online/window-{wi}/collection"
        summary = reader.read(collection / "summary.json")
        progress = reader.read(collection / "progress.json") or []
        summaries = (summary or {}).get("slots", progress)
        observed = {s["slot_id"]: s for s in summaries}
        if len(observed) != len(summaries) or set(observed) - {s["slot_id"] for s in spec["slots"]}:
            raise ValueError("Collector contains duplicate or undeclared slot IDs")
        wr = windows.get(spec["window_id"], {})
        guarded = _guard(wr)
        window_identity_ok = bool(
            initial
            and wr.get("before_actor_identity") == initial
            and wr.get("after_actor_identity") == initial
            and (summary or {}).get("actor_identity") == initial
        )
        for si, slot in enumerate(spec["slots"]):
            folder = collection / f"slot-{si}"
            record = observed.get(slot["slot_id"], {})
            rollout = reader.read(folder / "team-rollout.json")
            manifest = reader.read(folder / "episode/manifest.json")
            experience = reader.read(folder / "episode/experience.json")
            runtime = reader.read(folder / "runtime.json")
            interruption = reader.read(folder / "interruption.json")
            reward = (rollout or {}).get("reward_eligibility") or record.get("reward") or {}
            closed = (manifest or {}).get("status") == "closed"
            raw_events = (experience or {}).get("events", [])
            linkage = bool(
                rollout
                and experience
                and rollout.get("events") == raw_events
                and rollout.get("manifest_sha256")
                == (reader.ref(folder / "episode/manifest.json") or {}).get("sha256")
            )
            if record.get("reward") is not None and record["reward"] != reward:
                linkage = False
            known = (
                closed
                and reward.get("eligible") is True
                and finite(reward.get("reward"))
                and type(reward.get("completed")) is bool
            )
            state = (
                "closed_known"
                if known
                else "closed_unknown"
                if closed
                else "interrupted_open"
                if interruption
                else "open"
                if manifest
                else "not_started"
            )
            elapsed = (
                record.get("ended_at", 0) - record.get("started_at", 0)
                if finite(record.get("started_at")) and finite(record.get("ended_at"))
                else None
            )
            if elapsed is not None and elapsed < 0:
                elapsed = None
            measured_identities = [
                e["payload"]["response"].get("actor_identity")
                for e in raw_events
                if e.get("kind") == "model_response"
            ]
            actual_identity_ok = bool(
                initial and measured_identities and all(i == initial for i in measured_identities)
            )
            row = {
                "candidate_id": candidate,
                "harness": spec["harness"],
                "window_id": spec["window_id"],
                "slot_id": slot["slot_id"],
                "case_id": slot["case_id"],
                "task": slot["task"],
                "fact_position": slot["fact_position"],
                "repeat": slot["repeat"],
                "sampling_seed": slot["sampling_seed"],
                "role_decision_limits": slot["role_decision_limits"],
                "state": state,
                "reward": reward.get("reward") if known else None,
                "completed": reward.get("completed") if known else None,
                "record_validity": _validity(rollout, "record"),
                "permission_validity": _validity(rollout, "permission"),
                "raw_evidence_linkage": linkage,
                "evaluation_guard": guarded,
                "window_identity_matches_initial": window_identity_ok,
                "all_actual_actor_identities_match_initial": actual_identity_ok,
                "slot_elapsed_seconds": elapsed,
                "allocated_device_seconds": elapsed * devices if elapsed is not None else None,
                "unknown_reasons": reward.get("exclusions", []) if not known else [],
                "interruption": {k: (interruption or {}).get(k) for k in ("type", "message")}
                if interruption
                else None,
                "references": {
                    "rollout": reader.ref(folder / "team-rollout.json"),
                    "runtime": reader.ref(folder / "runtime.json"),
                    "manifest": reader.ref(folder / "episode/manifest.json"),
                    "experience": reader.ref(folder / "episode/experience.json"),
                },
                "runtime_role_status": {
                    role: {
                        k: value.get(k) for k in ("status", "reason", "opportunities", "actions")
                    }
                    for role, value in (runtime or {}).get("roles", {}).items()
                },
            }
            row["behavior"] = (
                behavior(
                    raw_events,
                    reward,
                    slot["role_decision_limits"],
                    reader=reader,
                    run_root=run_root,
                )
                if experience
                else None
            )
            rows.append(row)
    arms = []
    for harness in HARNESSES:
        arm_rows = [r for r in rows if r["harness"] == harness]
        metrics = counts_and_means(arm_rows)
        structural = len(arm_rows) == 12 and Counter(r["task"] for r in arm_rows) == {
            "implement": 4,
            "review": 4,
            "pair": 2,
            "chain": 2,
        }
        requirements = {
            "twelve_declared_slots": structural,
            "all_twelve_known": len(arm_rows) == 12
            and all(r["state"] == "closed_known" for r in arm_rows),
            "all_records_valid": bool(arm_rows)
            and all(r["record_validity"] is True and r["raw_evidence_linkage"] for r in arm_rows),
            "all_evaluation_guards": bool(arm_rows)
            and all(r["evaluation_guard"] for r in arm_rows),
            "all_actual_actor_identities_match_fresh_initial": fresh
            and identity_ok
            and all(
                r["window_identity_matches_initial"]
                and r["all_actual_actor_identities_match_initial"]
                for r in arm_rows
            ),
            "zero_actual_updates": zero,
            "unchanged_clean_source": source_ok,
            "launch_and_protocol_bound": launch_binding and protocol_ok,
            "all_slot_resources_measured": bool(arm_rows)
            and all(r["allocated_device_seconds"] is not None for r in arm_rows),
        }
        all_cost = requirements["all_slot_resources_measured"]
        arms.append(
            {
                "candidate_id": candidate,
                "harness": harness,
                "run_root": str(run_root),
                "protocol_ref": reader.ref(run_root / "launch-protocol.json"),
                "initial_actor_identity": initial,
                "metrics": metrics,
                "eligibility_checks": requirements,
                "eligible": all(requirements.values()),
                "ineligible_reasons": [k for k, v in requirements.items() if not v],
                "complete_implement_review": sum(
                    r["completed"] is True for r in arm_rows if r["task"] in {"implement", "review"}
                ),
                "complete_pair_chain": sum(
                    r["completed"] is True for r in arm_rows if r["task"] in {"pair", "chain"}
                ),
                "allocated_device_seconds": sum(r["allocated_device_seconds"] for r in arm_rows)
                if all_cost
                else None,
                "measured_partial_device_seconds": sum(
                    r["allocated_device_seconds"]
                    for r in arm_rows
                    if r["allocated_device_seconds"] is not None
                ),
            }
        )
    measured_slot_seconds = sum(
        r["slot_elapsed_seconds"] for r in rows if r["slot_elapsed_seconds"] is not None
    )
    return {
        "candidate_id": candidate,
        "run_root": str(run_root),
        "state": "ended" if ended else "running" if launch else "not_started",
        "ended": ended,
        "runner_status": online.get("status"),
        "launch_exit_code": (launch or {}).get("exit_code"),
        "actual_initial_actor_identity": initial,
        "actual_final_actor_identity": final_identity,
        "fresh_shared_owner": fresh,
        "source_before": source_before,
        "source_after": source_after,
        "actor_steps_total": online.get("actor_steps_total"),
        "critic_steps_total": online.get("critic_steps_total"),
        "declared_devices": devices,
        "whole_process_seconds_including_loading": process_seconds,
        "whole_process_allocated_device_seconds_including_loading": process_seconds * devices
        if process_seconds is not None
        else None,
        "measured_slot_seconds": measured_slot_seconds,
        "shared_unattributed_process_seconds": process_seconds - measured_slot_seconds
        if process_seconds is not None
        else None,
        "cost_rule": "Arm cost sums actual slot seconds times assigned device count. Whole-process loading/preparation/checkpoint cost is shown once per model, never assigned twice to arms. Device-seconds are allocation, not kernel-active time.",
        "rows": rows,
        "arms": arms,
        "paired": paired_comparison(rows),
        "references": {
            "launch": reader.ref(launch_path),
            "protocol": reader.ref(run_root / "launch-protocol.json"),
            "runner": reader.ref(run_root / "online/report.json"),
            "owner": reader.ref(run_root / "resident/owner.json"),
        },
    }


def select_combination(models):
    if {m["candidate_id"] for m in models} != set(CANDIDATES) or not all(
        m["ended"] for m in models
    ):
        return {"status": "waiting_for_both_models_to_end", "selected": None, "rule": SELECTION}
    eligible = [arm for model in models for arm in model["arms"] if arm["eligible"]]
    eligible.sort(
        key=lambda a: (
            -a["complete_implement_review"],
            -a["complete_pair_chain"],
            a["allocated_device_seconds"],
            a["candidate_id"],
            a["harness"],
        )
    )
    return {
        "status": "selected" if eligible else "no_eligible_combination",
        "selected": eligible[0] if eligible else None,
        "eligible_ranked": eligible,
        "rule": SELECTION,
        "interpretation": "Relative development initialization only. No capability threshold or preferred SDK was added after results.",
    }


def build_report(runs, launches, protocols=None):
    reader = Reader()
    protocols = protocols or {}
    models = [
        read_model(
            candidate, runs[candidate], launches[candidate], protocols.get(candidate), reader=reader
        )
        for candidate in CANDIDATES
    ]
    return {
        "version": VERSION,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "models": models,
        "estimands": {
            "raw_task_weights": {
                "implement": 1 / 3,
                "review": 1 / 3,
                "pair": 1 / 6,
                "chain": 1 / 6,
            },
            "secondary_task_macro_weights": {task: 0.25 for task in TASKS},
            "situations_per_model": 6,
            "repeats_per_situation_per_arm": 2,
            "same_seed_implies_same_text": False,
            "subtract_S1_means": False,
        },
        "selection": select_combination(models),
        "read_errors": reader.errors,
        "source_references": reader.references,
        "scope": "Read-only snapshot from saved actual records; no rescoring, retokenization, model execution, probability recomputation, or causal inference. Snapshots are not globally atomic while jobs run.",
    }


def markdown(report):
    lines = [
        "# H1 v0.17 只读比较",
        "",
        f"观察时间：{report['recorded_at']}",
        "",
        "| 模型 | harness | 已知/计划 | 已知完整责任 | 原均值 | 四任务宏均值 | 分配设备秒 | 可进入选择 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]

    def show(value):
        return (
            "未知"
            if value is None
            else str(round(value, 6))
            if isinstance(value, float)
            else str(value)
        )

    for model in report["models"]:
        for arm in model["arms"]:
            m = arm["metrics"]
            lines.append(
                f"| {model['candidate_id']} | {arm['harness']} | {m['known']}/{m['planned']} | {m['observed_complete_count']} | {show(m['raw_mean'])} | {show(m['task_macro_mean'])} | {show(arm['allocated_device_seconds'])} | {arm['eligible']} |"
            )
    lines += [
        "",
        "未知未填零。每臂每模型12例来自6个开发情境×2重复；原均值权重为实现/复核各1/3、pair/chain各1/6，宏均值四任务等权。",
        "",
    ]
    for model in report["models"]:
        paired = model.get("paired", {})
        lines.append(
            f"{model['candidate_id']}：状态 {model['state']}；已知配对 {paired.get('known_pairs', 0)}/12；SDK−native均差 {show(paired.get('paired_raw_delta'))}；整进程含加载设备秒 {show(model.get('whole_process_allocated_device_seconds_including_loading'))}。"
        )
    selected = report["selection"].get("selected")
    lines += ["", "选择状态：" + report["selection"]["status"] + "。"]
    if selected:
        lines.append(
            f"相对选中：{selected['candidate_id']} / {selected['harness']}。这不是基础能力充分的认证。"
        )
    lines += [
        "",
        "完整case/repeat、岗位、实际权重身份、guard、原始引用及行为断点在report.json。行为分析只报告可观察关联；无法证明的恢复效果与失败原因保持未知。",
    ]
    return "\n".join(lines) + "\n"


def assignments(values):
    result = {}
    for text in values or []:
        key, value = text.split("=", 1)
        if key not in CANDIDATES or key in result:
            raise ValueError("Use each registered candidate once")
        result[key] = Path(value)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", help="candidate=actual run directory")
    parser.add_argument("--launch", action="append", help="candidate=actual launcher JSON")
    parser.add_argument(
        "--protocol", action="append", help="candidate=declared protocol for not-yet-started jobs"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Report output must be a new directory")
    runs = {c: Path("runs") / f"harness-v017-h1-{c}" for c in CANDIDATES}
    runs.update(assignments(args.run))
    launches = {c: Path("runs/v017-launch") / f"h1-{c}.launch.json" for c in CANDIDATES}
    launches.update(assignments(args.launch))
    result = build_report(runs, launches, assignments(args.protocol))
    args.output.mkdir(parents=True)
    (args.output / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    (args.output / "report.md").write_text(markdown(result))
    report_path = (args.output / "report.json").resolve()
    selection = {
        **result["selection"],
        "report_ref": {
            "path": str(report_path),
            "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        },
    }
    (args.output / "selection.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "status": result["selection"]["status"],
                "models": [
                    {"candidate": m["candidate_id"], "state": m["state"], "rows": len(m["rows"])}
                    for m in result["models"]
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
