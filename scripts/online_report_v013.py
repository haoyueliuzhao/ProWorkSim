"""Read-only compact accounting for recorded online collection/update/evaluation.

Never executes policies, rewards, validators, SQL, training or GPU work. New JSON
must live outside the input trees. Missing/unfinished slots stay explicit.
"""

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

VERSION = "online-readonly-report-v0.13"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class EvidenceFiles:
    def __init__(self):
        self.refs = {}
        self._json = {}

    def text(self, path):
        path = Path(path).resolve()
        key = str(path)
        raw = path.read_bytes()
        if key not in self.refs:
            self.refs[key] = {
                "path": key,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
        return raw.decode()

    def read(self, path, optional=False):
        path = Path(path).resolve()
        if not path.exists() and optional:
            return None
        key = str(path)
        if key not in self._json:
            raw = path.read_bytes()
            self.refs[key] = {
                "path": key,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
            self._json[key] = json.loads(raw)
        return self._json[key]


def transport_kind(payload, declared=None):
    """A direct adapter's HTTP-shaped envelope/base_url is NOT network HTTP."""
    response = payload.get("response", {})
    body = response.get("body", {}) if isinstance(response, dict) else {}
    headers = response.get("response_headers", {}) if isinstance(response, dict) else {}
    if (
        payload.get("backend_id") == "resident_direct"
        or headers.get("x-transport") == "resident-direct"
        or body.get("transport_kind") == "resident_direct"
        or body.get("service_record", {}).get("transport_kind") == "resident_direct"
        or declared == "resident_direct"
    ):
        return "resident_direct"
    if payload.get("endpoint", "").startswith(("http://", "https://")):
        return "network_http"
    return "unknown"


def _usage(body, accounting):
    usage = accounting.get("reported_usage") or body.get("usage")
    if not isinstance(usage, dict) or any(
        type(usage.get(k)) is not int or usage[k] < 0
        for k in ["prompt_tokens", "completion_tokens", "total_tokens"]
    ):
        return None
    return {key: usage[key] for key in ["prompt_tokens", "completion_tokens", "total_tokens"]}


def rejection_followups(events, generations):
    """Same member's next actual returned generation, not a later lucky action."""
    calls = [e for e in events if e["kind"] == "tool_call"]
    result = []
    for failed in calls:
        payload = failed["payload"]
        if payload.get("response", {}).get("ok") is not False:
            continue
        member = failed.get("worker_id")
        following = next(
            (
                g
                for g in generations
                if g["member"] == member and g["sequence"] > failed["sequence"]
            ),
            None,
        )
        row = {
            "member": member,
            "rejection_sequence": failed["sequence"],
            "tool": payload["action"],
            "arguments_sha256": hashlib.sha256(canonical(payload.get("arguments", {}))).hexdigest(),
            "next_generation_call_id": following["call_id"] if following else None,
            "feedback": "no_next_generation",
            "adjustment": "no_next_generation",
        }
        if following:
            request = following["request"]
            messages = [
                e["payload"].get("message")
                for e in events
                if e["kind"] == "model_tool_result"
                and e.get("worker_id") == member
                and e["sequence"] < following["sequence"]
                and e["payload"].get("call_id") == payload.get("model_call_id")
            ]
            row["feedback"] = (
                "missing_actual_request"
                if not isinstance(request, dict)
                else "missing_tool_result_record"
                if not messages
                else "present_in_actual_request"
                if any(m in request.get("messages", []) for m in messages)
                else "absent_from_actual_request"
            )
            next_calls = [
                e
                for e in calls
                if e.get("worker_id") == member
                and e["payload"].get("model_call_id") == following["call_id"]
            ]
            if len(next_calls) == 1:
                nxt = next_calls[0]
                np = nxt["payload"]
                next_result = np.get("response", {}).get("result")
                row.update(
                    next_tool=np["action"],
                    next_tool_sequence=nxt["sequence"],
                    next_response_ok=np.get("response", {}).get("ok"),
                    next_sql_execution_status=next_result.get("execution_status")
                    if isinstance(next_result, dict)
                    else None,
                )
                row["adjustment"] = (
                    "different_tool"
                    if np["action"] != payload["action"]
                    else "changed_arguments_same_tool"
                    if np.get("arguments", {}) != payload.get("arguments", {})
                    else "same_tool_same_arguments"
                )
                row["next_arguments_sha256"] = hashlib.sha256(
                    canonical(np.get("arguments", {}))
                ).hexdigest()
            else:
                row["adjustment"] = (
                    "no_world_tool_for_next_generation"
                    if not next_calls
                    else "ambiguous_multiple_tools"
                )
        result.append(row)
    return {
        "rows": result,
        "counts_by_feedback": dict(Counter(r["feedback"] for r in result)),
        "counts_by_adjustment": dict(Counter(r["adjustment"] for r in result)),
        "interpretation": "Different parameters/tools are observed adjustments, not automatically correct work. No next actual generation is separate from failure to use feedback.",
    }


def summarize_events(events, *, declared_transport=None, actor_identity=None):
    attempts = defaultdict(dict)
    issues = []
    for event in events:
        if event["kind"] != "model_attempt":
            continue
        p = event["payload"]
        key = (event.get("worker_id", p.get("worker_id")), p.get("attempt_id"))
        stage = p.get("stage")
        if stage in attempts[key] and attempts[key][stage]["payload"] != p:
            issues.append(
                {"kind": "conflicting_attempt_records", "attempt_id": key[1], "member": key[0]}
            )
        attempts[key][stage] = event
    members = defaultdict(Counter)
    generations = []
    attempt_rows = []
    seen_responses = set()
    for (member, attempt_id), pair in sorted(
        attempts.items(), key=lambda row: min(e["sequence"] for e in row[1].values())
    ):
        start, end = pair.get("started"), pair.get("finished")
        event = end or start
        p = event["payload"]
        transport = transport_kind(p, declared_transport)
        counts = members[member]
        counts["attempts_started"] += int(start is not None)
        counts["attempts_finished"] += int(end is not None)
        counts[transport + "_attempts_started"] += int(start is not None)
        if start is None:
            issues.append({"kind": "finished_attempt_without_start", "attempt_id": attempt_id})
        body = p.get("response", {}).get("body", {})
        status = p.get("status", "unfinished") if end else "unfinished"
        counts["attempt_status:" + status] += 1
        accounting = p.get("accounting", {})
        usage = _usage(body, accounting) if end else None
        pre_generation = bool(end and body.get("generation_started") is False)
        if usage:
            for name, value in usage.items():
                counts["reported_" + name] += value
        elif end:
            counts["finished_unknown_usage_attempts"] += 1
            if not pre_generation:
                counts["finished_unknown_sampling_usage_attempts"] += 1
        else:
            counts["unfinished_attempts"] += 1
        charged = accounting.get("charged_reservation", {})
        if pre_generation:
            counts["confirmed_pre_generation_rejections"] += 1
            prompt_positions = body.get("error", {}).get("prompt_tokens")
            if type(prompt_positions) is int:
                counts["pre_generation_tokenized_prompt_positions"] += prompt_positions
        counts["unknown_reserved_tokens_charged"] += charged.get("token_reservation", 0)
        generation = bool(body.get("choices") and body["choices"][0].get("message"))
        response_id = body.get("id")
        if generation:
            key = response_id or (member, attempt_id)
            if key in seen_responses:
                issues.append({"kind": "duplicate_completion_id", "completion_id": response_id})
            else:
                seen_responses.add(key)
                counts["returned_generations"] += 1
                trace = body.get("token_trace")
                if isinstance(trace, dict) and isinstance(trace.get("output_ids"), list):
                    counts["generations_with_actual_token_trace"] += 1
                    counts["actual_output_token_positions"] += len(trace["output_ids"])
                    counts["actual_input_token_positions"] += len(trace.get("input_ids", []))
                generations.append(
                    {
                        "member": member,
                        "call_id": p.get("call_id"),
                        "sequence": event["sequence"],
                        "response_id": response_id,
                        "request": p.get("request"),
                        "body": body,
                        "transport": transport,
                        "usage": usage,
                    }
                )
                if actor_identity is not None:
                    counts["actor_identity_match"] += int(
                        body.get("actor_identity") == actor_identity
                    )
                    counts["actor_identity_missing_or_mismatch"] += int(
                        body.get("actor_identity") != actor_identity
                    )
        attempt_rows.append(
            {
                "member": member,
                "attempt_id": attempt_id,
                "call_id": p.get("call_id"),
                "transport": transport,
                "status": status,
                "start_sequence": start["sequence"] if start else None,
                "finish_sequence": end["sequence"] if end else None,
                "response_id": response_id,
                "returned_generation": generation,
                "generation_explicitly_not_started": pre_generation,
                "reported_usage": usage,
                "charged_unknown_reservation": charged or None,
                "unfinished_start_reservation": p.get("reservation") if end is None else None,
            }
        )
    tool_rows = []
    by_tool = defaultdict(Counter)
    by_member_tool = defaultdict(lambda: defaultdict(Counter))
    for event in events:
        if event["kind"] != "tool_call":
            continue
        p = event["payload"]
        response = p.get("response", {})
        ok = response.get("ok")
        status = "ok" if ok is True else "rejected" if ok is False else "unknown"
        error = response.get("error", {})
        rejection = error.get("rejection", {})
        code = rejection.get("code", error.get("type", "unknown"))
        member, tool = event.get("worker_id"), p["action"]
        by_tool[tool][status] += 1
        by_member_tool[member][tool][status] += 1
        members[member]["public_tool_calls"] += 1
        members[member]["public_tool_" + status] += 1
        if status == "rejected":
            by_tool[tool]["rejection:" + str(code)] += 1
            by_member_tool[member][tool]["rejection:" + str(code)] += 1
        result = response.get("result")
        execution = result.get("execution_status") if isinstance(result, dict) else None
        if tool in {"sql_build", "sql_query"}:
            sql_status = execution or (
                "pre_execution_rejected" if ok is False else "execution_status_unavailable"
            )
            by_tool[tool]["sql:" + sql_status] += 1
            by_member_tool[member][tool]["sql:" + sql_status] += 1
        tool_rows.append(
            {
                "sequence": event["sequence"],
                "member": member,
                "tool": tool,
                "status": status,
                "rejection_code": code if status == "rejected" else None,
                "rejection_category": rejection.get("category") if status == "rejected" else None,
                "sql_execution_status": execution,
                "command_id": response.get("command_id"),
                "model_call_id": p.get("model_call_id"),
            }
        )
    controls = Counter()
    started_calls = set()
    for event in events:
        if event["kind"] == "model_call" and event["payload"].get("stage") == "started":
            key = (event.get("worker_id"), event["payload"].get("call_id"))
            if key not in started_calls:
                started_calls.add(key)
                members[key[0]]["model_calls_started"] += 1
        if event["kind"] == "model_control":
            controls[event["payload"].get("kind", "unknown")] += 1
            members[event.get("worker_id")][
                "control:" + str(event["payload"].get("kind", "unknown"))
            ] += 1
    totals = sum((c for c in members.values()), Counter())
    resource = {
        "returned_generations_with_service_resource": 0,
        "generation_seconds_sum": 0.0,
        "max_gpu_allocated_peak_bytes": None,
        "max_rss_bytes": None,
        "max_rss_peak_bytes": None,
    }
    for g in generations:
        service = g["body"].get("service_record", {})
        if service:
            resource["returned_generations_with_service_resource"] += 1
            resource["generation_seconds_sum"] += service.get(
                "seconds", service.get("batch_seconds", 0.0)
            )
            for target, value in [
                ("max_gpu_allocated_peak_bytes", service.get("peak_gpu_bytes")),
                ("max_rss_bytes", service.get("resource", {}).get("rss_bytes")),
                ("max_rss_peak_bytes", service.get("resource", {}).get("rss_peak_bytes")),
            ]:
                if isinstance(value, (int, float)):
                    resource[target] = max(resource[target] or 0, value)
    return {
        "totals": dict(totals),
        "members": {m: dict(v) for m, v in members.items()},
        "attempts": attempt_rows,
        "tools": {t: dict(v) for t, v in by_tool.items()},
        "member_tools": {
            m: {t: dict(v) for t, v in tools.items()} for m, tools in by_member_tool.items()
        },
        "tool_returns": tool_rows,
        "controls_without_world_action": dict(controls),
        "rejection_followups": rejection_followups(events, generations),
        "resources": resource,
        "format_feedback_events": sum(e["kind"] == "model_format_feedback" for e in events),
        "controller_actions": sum(e["kind"] == "controller_action" for e in events),
        "environment_events": sum(e["kind"] == "environment_event" for e in events),
        "response_ids": [g["response_id"] for g in generations],
        "record_issues": issues,
        "counting_limits": "Actual recorded attempts/completions and public-port calls. Tool ok and DuckDB success do not certify business correctness; controls have no world tool action. finished_unknown_usage_attempts preserves the framework's missing-usage accounting; confirmed pre-generation refusals did not sample an output, so they are separated from unknown sampling usage. Charged reservations are not measured model tokens.",
    }


def _reward(value):
    if value is None:
        return None
    return {
        key: copy.deepcopy(value.get(key))
        for key in [
            "version",
            "reward_id",
            "scope",
            "episode_id",
            "manifest_sha256",
            "eligible",
            "reward",
            "completed",
            "preparation_credited",
            "exclusions",
        ]
    } | {
        "components": [
            {
                key: copy.deepcopy(row.get(key))
                for key in ["term_id", "weight", "achieved", "score", "evidence"]
            }
            for row in value.get("components", [])
        ]
    }


def _validity(value):
    if value is None:
        return None
    return {
        "version": value.get("version"),
        "spec_id": value.get("spec_id"),
        "value": value.get("value"),
        "components": {k: v.get("value") for k, v in value.get("components", {}).items()},
    }


def _support(value):
    if value is None:
        return None
    groups = []
    for group in value.get("groups", []):
        row = {
            key: copy.deepcopy(group.get(key))
            for key in [
                "window",
                "active_members",
                "planned",
                "complete",
                "closed",
                "interrupted",
                "not_started",
                "closed_unassessed",
                "closed_joint_M",
                "empirical_distribution_status",
            ]
        }
        support = group.get("support") or {}
        row["slot_ids"] = copy.deepcopy(support.get("slot_ids"))
        row["member_blocks"] = {
            member: {
                key: copy.deepcopy(block.get(key))
                for key in [
                    "M",
                    "n_positive",
                    "n_by_class",
                    "v",
                    "b",
                    "semantic_work_support",
                    "base_actor_mask",
                    "composition_degrees_of_freedom",
                ]
            }
            for member, block in support.get("blocks", {}).items()
        }
        row["baseline_only_materialization"] = group.get("baseline_only_materialization")
        row["Q_equals_B"] = group.get("Q_equals_B")
        groups.append(row)
    return {
        "version": value.get("version"),
        "window_id": value.get("window_id"),
        "complete": value.get("complete"),
        "groups": groups,
        "scope": value.get("scope"),
    }


def _probability(files, path):
    rows = files.read(path, optional=True)
    if rows is None:
        return {"recorded": False, "passed": None}
    if not isinstance(rows, list):
        return {
            "recorded": True,
            "passed": None,
            "diagnostic": "Unknown original check format",
            "ref": str(path.resolve()),
        }
    return {
        "recorded": True,
        "checks": len(rows),
        "passed": all(r.get("passed") is True for r in rows) if rows else None,
        "failed_call_ids": [r.get("call_id") for r in rows if r.get("passed") is False],
        "max_observed_absolute_difference": max(
            (r.get("max_abs_delta", r.get("max_abs", 0)) for r in rows), default=None
        ),
        "max_observed_mean_difference": max(
            (r.get("mean_abs_delta", r.get("mean_abs", 0)) for r in rows), default=None
        ),
        "ref": str(path.resolve()),
        "empty_check_list_is_not_an_executed_probability_gate": not rows,
    }


def _update(files, path):
    value = files.read(path / "report.json", optional=True)
    if value is None:
        return None
    fields = [
        "version",
        "window_id",
        "status",
        "stage",
        "before_actor_identity",
        "after_actor_identity",
        "actor_optimizer_steps",
        "critic_optimizer_steps",
        "training_happened",
        "changed_actor_elements",
        "actor_update_enabled",
        "zero_signal_window",
        "critic_had_nonzero_reward_history",
        "backward_decisions_completed",
        "admitted_decisions",
        "admitted_output_tokens",
        "behavior_probability_passed",
        "gradient_norms",
        "resource",
        "error",
        "probability_recomputation_executed",
        "actor_or_critic_learning_forward_executed",
    ]
    result = {key: copy.deepcopy(value[key]) for key in fields if key in value}
    result.update(
        report_ref=str((path / "report.json").resolve()),
        behavior_probability=_probability(files, path / "behavior-probability-check.json"),
        gradient_probability=_probability(files, path / "gradient-probability-check.json"),
    )
    admission = files.read(path / "admission.json", optional=True)
    if admission is not None:
        decisions = admission.get("decisions", [])
        result["admission"] = {
            "ref": str((path / "admission.json").resolve()),
            "slot_count": admission.get("slot_count"),
            "normalization": admission.get("normalization"),
            "slots": [
                {
                    key: copy.deepcopy(slot.get(key))
                    for key in ["slot_id", "active_members", "exclusions", "members"]
                }
                for slot in admission.get("slots", [])
            ],
            "decision_count": len(decisions),
            "output_token_positions": sum(
                len(d.get("tokens", {}).get("output_ids", [])) for d in decisions
            ),
            "decisions": [
                {
                    key: copy.deepcopy(d.get(key))
                    for key in [
                        "slot_id",
                        "member_id",
                        "call_id",
                        "actor_denominator",
                        "critic_denominator",
                        "actual_response_sha256",
                    ]
                }
                | {"output_token_positions": len(d.get("tokens", {}).get("output_ids", []))}
                for d in decisions
            ],
            "scope": "Saved admission is not an optimizer step or a completed probability gate. Tokens, masks and critic feature arrays remain only in the referenced original.",
        }
    if (
        value.get("before_actor_identity") is not None
        and value.get("after_actor_identity") is not None
    ):
        result["actor_identity_changed"] = (
            value["before_actor_identity"] != value["after_actor_identity"]
        )
    return result


def summarize_collection(directory, files):
    directory = Path(directory).resolve()
    declaration = files.read(directory / "declaration.json")
    original = files.read(directory / "summary.json", optional=True)
    support = files.read(directory / "support.json", optional=True)
    gamma = declaration.get("gamma_identity", {})
    rows = []
    for index, slot in enumerate(declaration["slots"]):
        folder = directory / ("slot-" + str(index))
        manifest = files.read(folder / "episode/manifest.json", optional=True)
        rollout = files.read(folder / "team-rollout.json", optional=True)
        preparation = files.read(folder / "preparation.json", optional=True)
        summary_row = next(
            (r for r in (original or {}).get("slots", []) if r.get("slot_id") == slot["slot_id"]),
            {},
        )
        row = {
            "slot_id": slot["slot_id"],
            "xi_id": slot["xi_id"],
            "xi_fingerprint": slot["xi_fingerprint"],
            "active_members": slot["active_members"],
            "actor_identity": declaration["actor_identity"],
            "boundary": summary_row.get("boundary"),
            "episode_status": manifest.get("status") if manifest else "not_started_or_unrecorded",
            "reward": _reward(
                rollout.get("reward_eligibility") if rollout else summary_row.get("reward")
            ),
            "validity": _validity(
                rollout.get("work_validity") if rollout else summary_row.get("work_validity")
            ),
            "mapping": files.read(folder / "mapping.json", optional=True),
            "original_meters": summary_row.get("meters"),
            "ref": str(folder),
            "events_source": None,
            "events_scope": None,
        }
        events = None
        if manifest and manifest.get("status") == "closed":
            history_path = folder / "episode" / manifest["experience"]["path"]
            history = files.read(history_path)
            if (
                files.refs[str(history_path.resolve())]["sha256"]
                != manifest["experience"]["sha256"]
            ):
                raise ValueError(
                    "Closed episode experience bytes differ from the original manifest"
                )
            events = history["events"][
                manifest["experience"]["start"] : manifest["experience"]["end"]
            ]
            row.update(
                events_source=str(history_path),
                events_scope="original_closed_interval",
                episode_id=manifest["episode_id"],
                source_start=manifest.get("source_start"),
                source_end=manifest.get("source_end"),
            )
        else:
            interruption = files.read(folder / "interruption.json", optional=True)
            runtime = (
                interruption.get("runtime")
                if interruption
                else files.read(folder / "runtime.json", optional=True)
            )
            if runtime and isinstance(runtime.get("experience"), dict):
                events = runtime["experience"]["events"]
                row.update(
                    events_source=str(
                        folder / ("interruption.json" if interruption else "runtime.json")
                    ),
                    events_scope="saved_open_runtime_prefix_no_fabricated_terminal",
                )
            row["interruption"] = {k: v for k, v in (interruption or {}).items() if k != "runtime"}
        if events is not None:
            row["actual"] = summarize_events(
                events,
                declared_transport=gamma.get("transport_kind"),
                actor_identity=declaration["actor_identity"],
            )
            prefix_events = (preparation or {}).get("experience", {}).get("events", [])
            prefix_env_ids = {
                e["payload"].get("event_id")
                for e in prefix_events
                if e["kind"] == "preparation_environment_event"
            }
            row["preparation_exclusion"] = {
                "recorded_preparation_events": len(prefix_events),
                "declared_credited_to_current_actor": (preparation or {}).get(
                    "credited_to_current_actor"
                ),
                "actor_interval_has_preparation_kind": any(
                    e["kind"].startswith("preparation_") for e in events
                ),
                "replayed_preparation_environment_events": [
                    e["payload"].get("event_id")
                    for e in events
                    if e["kind"] == "environment_event"
                    and e["payload"].get("event_id") in prefix_env_ids
                ],
                "episode_start_experience_count": manifest.get("experience_start", {}).get(
                    "event_count"
                )
                if manifest
                else None,
                "interpretation": "Preparation's world facts may be inherited; no preparation action or token becomes current actor training data.",
            }
        else:
            row["actual"] = None
            row["events_scope"] = "unavailable_no_zero_imputation"
        rows.append(row)
    result = {
        "directory": str(directory),
        "window_id": declaration["window_id"],
        "interface": gamma.get("interface_version"),
        "actor_identity": declaration["actor_identity"],
        "gamma_identity": gamma,
        "declared_slots": len(declaration["slots"]),
        "slots": rows,
        "support": _support(support),
        "collection_summary_recorded": original is not None,
        "update": _update(files, directory.parent / "update"),
        "frozen_evaluation": _update(files, directory.parent / "evaluation"),
    }
    totals = Counter()
    for row in rows:
        if row["actual"]:
            totals.update(row["actual"]["totals"])
    result["observed_totals"] = dict(totals)
    result["reward_counts"] = dict(
        Counter(str(row["reward"].get("reward")) if row["reward"] else "unrecorded" for row in rows)
    )
    result["validity_counts"] = dict(
        Counter(
            str(row["validity"].get("value")) if row["validity"] else "unrecorded" for row in rows
        )
    )
    return result


def _launch_summary(files, prefix):
    prefix = Path(prefix)
    record = files.read(str(prefix) + ".launch.json")
    output = None
    command = record.get("command", [])
    if "--output" in command:
        output = str(Path(command[command.index("--output") + 1]).resolve())
    result = {
        "run_directory": output,
        "original": record,
        "launch_ref": str(Path(str(prefix) + ".launch.json").resolve()),
    }
    intervention = files.read(str(prefix) + ".intervention.json", optional=True)
    if intervention is not None:
        result["intervention"] = intervention
        result["intervention_ref"] = str(Path(str(prefix) + ".intervention.json").resolve())
    log = Path(str(prefix) + ".log")
    if log.exists():
        text = files.text(log)
        result["log_ref"] = str(log.resolve())
        result["log_tail"] = text[-5000:]
    resource_path = Path(str(prefix) + ".resources.jsonl")
    if resource_path.exists():
        samples = [
            json.loads(line) for line in files.text(resource_path).splitlines() if line.strip()
        ]
        rss, gpu = [], []
        pid = str(record.get("pid"))
        for sample in samples:
            for line in sample.get("host", {}).get("stdout", "").splitlines():
                parts = line.split()
                if len(parts) > 1 and parts[0] == pid and parts[1].isdigit():
                    rss.append(int(parts[1]) * 1024)
            for line in sample.get("processes", {}).get("stdout", "").splitlines():
                parts = [value.strip() for value in line.split(",")]
                if len(parts) >= 3 and parts[1] == pid:
                    try:
                        gpu.append(float(parts[2]) * 1024**2)
                    except ValueError:
                        pass
        result["resource_samples"] = {
            "ref": str(resource_path.resolve()),
            "count": len(samples),
            "own_pid_max_sampled_rss_bytes": max(rss, default=None),
            "own_pid_max_sampled_gpu_process_bytes": max(gpu, default=None),
            "scope": "Sampled own-PID maxima, not allocator peaks or integrated compute time. Other processes remain only in the original referenced log.",
        }
    return result


def build_report(input_dirs, *, launch_prefixes=()):
    inputs = sorted({str(Path(p).resolve()) for p in input_dirs})
    files = EvidenceFiles()
    collections = {}
    run_reports = []
    input_runs = []
    launches = [_launch_summary(files, prefix) for prefix in launch_prefixes]
    for root in inputs:
        if not Path(root).is_dir():
            raise ValueError(f"Recorded input directory does not exist: {root}")
        for path in sorted(Path(root).rglob("declaration.json")):
            value = files.read(path)
            if value.get("version") == "online-window-support-v0.13" and isinstance(
                value.get("slots"), list
            ):
                collections[str(path.parent)] = path.parent
        # Only known small runner/source facts; never load tensor checkpoints.
        run_facts = {}
        for name in [
            "source-before.json",
            "source-after.json",
            "source-comparison.json",
            "online/protocol.json",
            "online/report.json",
            "resident/owner.json",
            "resident-startup-resource.json",
        ]:
            path = Path(root) / name
            value = files.read(path, optional=True)
            if value is not None:
                run_facts[name] = value
                if name.endswith("report.json"):
                    run_reports.append(
                        {
                            "ref": str(path),
                            **{k: v for k, v in value.items() if k != "windows"},
                            "window_ids": [r.get("window_id") for r in value.get("windows", [])],
                        }
                    )
        protocol = run_facts.get("online/protocol.json", {})
        launch = next((r for r in launches if r["run_directory"] == root), None)
        calls_dir = Path(root) / "resident/calls"
        call_files = list(calls_dir.glob("*.json")) if calls_dir.is_dir() else None
        recorded_collections = [p for p in collections.values() if p.is_relative_to(Path(root))]
        runner_status = run_facts.get("online/report.json", {}).get("status")
        failed_exit = bool(launch and launch["original"].get("exit_code") not in {0, None})
        intervention = bool(launch and launch.get("intervention"))
        terminal_failure = failed_exit or intervention or runner_status == "error"
        status = (
            "interrupted_with_recorded_collection"
            if recorded_collections and (failed_exit or intervention)
            else "error_with_recorded_collection"
            if recorded_collections and runner_status == "error"
            else "preparation_failed_before_collection"
            if not recorded_collections and runner_status == "error"
            else "startup_failed_before_collection"
            if not recorded_collections and terminal_failure
            else "collection_recorded"
            if recorded_collections
            else "no_collection_recorded_or_running"
        )
        planned_windows = []
        for wi, window in enumerate(protocol.get("windows", [])):
            slots = []
            for si, slot in enumerate(window.get("slots", [])):
                folder = Path(root) / f"online/window-{wi}/collection/slot-{si}"
                manifest = files.read(folder / "episode/manifest.json", optional=True)
                runtime = (folder / "runtime.json").exists()
                interruption = (folder / "interruption.json").exists()
                actor_status = (
                    "closed"
                    if manifest and manifest.get("status") == "closed"
                    else "open_or_interrupted"
                    if manifest or runtime or interruption
                    else "not_started_actor"
                    if terminal_failure
                    else "not_started_or_unrecorded"
                )
                slots.append(
                    {
                        "slot_id": slot.get("slot_id"),
                        "case_id": slot.get("case_id"),
                        "actor_status": actor_status,
                        "prepared_world_exists": (folder / "world").is_dir(),
                        "preparation_record_exists": (folder / "preparation.json").is_file(),
                        "episode_manifest_ref": str((folder / "episode/manifest.json").resolve())
                        if manifest
                        else None,
                    }
                )
            planned_windows.append(
                {
                    "window_id": window.get("window_id"),
                    "planned_slots": len(slots),
                    "slot_ids": [s["slot_id"] for s in slots],
                    "slots": slots,
                }
            )
        input_runs.append(
            {
                "directory": root,
                "boundary_status": status,
                "planned_windows": planned_windows,
                "planned_slots": sum(len(w.get("slots", [])) for w in protocol.get("windows", [])),
                "recorded_collection_count": len(recorded_collections),
                "resident_call_files_observed": len(call_files) if call_files is not None else None,
                "zero_recorded_generations_before_collection": bool(
                    not recorded_collections and terminal_failure and call_files == []
                ),
                "stored_runner_status": runner_status,
                "runner_error": run_facts.get("online/report.json", {}).get("error"),
                "source_before": run_facts.get("source-before.json"),
                "source_after": run_facts.get("source-after.json"),
                "source_comparison": run_facts.get("source-comparison.json"),
                "resident_owner": run_facts.get("resident/owner.json"),
                "startup_resource": run_facts.get("resident-startup-resource.json"),
                "launch_ref": launch.get("launch_ref") if launch else None,
                "scope": "All protocol slots remain visible, including pre-actor preparation failures and unstarted later windows after interruption. No episode or terminal actor outcome is fabricated. A prepared world is not an actor sample.",
            }
        )
    windows = [summarize_collection(p, files) for p in sorted(collections.values())]
    totals = Counter()
    generation_resources = {
        "generation_seconds_sum": 0.0,
        "returned_generations_with_service_resource": 0,
        "max_gpu_allocated_peak_bytes": None,
        "max_rss_bytes": None,
        "max_rss_peak_bytes": None,
    }
    completion_ids = Counter()
    for window in windows:
        totals.update(window["observed_totals"])
        for slot in window["slots"]:
            actual = slot.get("actual")
            if actual is None:
                continue
            completion_ids.update(x for x in actual["response_ids"] if x)
            for key, value in actual["resources"].items():
                if key in {"generation_seconds_sum", "returned_generations_with_service_resource"}:
                    generation_resources[key] += value
                elif value is not None:
                    generation_resources[key] = max(generation_resources[key] or 0, value)
    identities = []
    for first, second in zip(windows, windows[1:]):
        update = first.get("update")
        same_run = Path(first["directory"]).parents[1] == Path(second["directory"]).parents[1]
        if same_run and update and update.get("after_actor_identity"):
            identities.append(
                {
                    "first_window": first["window_id"],
                    "next_window": second["window_id"],
                    "same_run_parent": str(Path(first["directory"]).parents[1])
                    == str(Path(second["directory"]).parents[1]),
                    "update_after_matches_next_sampling_identity": update["after_actor_identity"]
                    == second["actor_identity"],
                    "interpretation": "Identity adjacency only; separate evaluation/interface populations must not be pooled.",
                }
            )
    return {
        "version": VERSION,
        "mode": "read_only_saved_facts_no_reassessment",
        "inputs": inputs,
        "input_runs": input_runs,
        "launches": launches,
        "windows": windows,
        "runner_reports": run_reports,
        "observed_resource_totals": dict(totals),
        "observed_generation_resources": generation_resources,
        "duplicate_completion_ids_across_slots": {k: n for k, n in completion_ids.items() if n > 1},
        "actual_network_http_attempts_observed": totals.get("network_http_attempts_started", 0),
        "resident_direct_attempts_observed": totals.get("resident_direct_attempts_started", 0),
        "unknown_transport_attempts_observed": totals.get("unknown_attempts_started", 0),
        "identity_links": identities,
        "references": files.refs,
        "limits": [
            "No reward/V/Mapper/probability/evaluator is rerun. Original scalar and component outcomes remain unchanged.",
            "Direct transport attempt counters may retain legacy http_attempts field names; they are not network HTTP.",
            "Unstarted/unfinished/unrecorded slots remain explicit and are not invented zero outcomes or empirical support.",
            "Tool ok, SQL execution success, reward, scoped V and full-chain completion are separate facts.",
            "Returned generation timing sums are recorded wall intervals, not hardware-active time or end-to-end speedups; memory peaks are maxima, never summed.",
            "No prompt/token/checkpoint tensors are copied; large tensors and model weights are not opened.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True, dest="inputs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--launch",
        action="append",
        type=Path,
        default=[],
        help="Optional saved launcher prefix (reads .launch.json/.log/.resources.jsonl only)",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or any(output.is_relative_to(root.resolve()) for root in args.inputs):
        raise ValueError("Write a new JSON outside every original input tree")
    report = build_report(args.inputs, launch_prefixes=args.launch)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "windows": len(report["windows"]),
                "direct_attempts": report["resident_direct_attempts_observed"],
                "network_http_attempts": report["actual_network_http_attempts_observed"],
            }
        )
    )


if __name__ == "__main__":
    main()
