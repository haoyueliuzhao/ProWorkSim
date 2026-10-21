#!/usr/bin/env python3
"""Summarize native request timing once, after the existing rollout monitor closes.

Reads only the monitor-selected closed cohorts and their exact controller/native
response and small session timing artifacts. Does not read task trees, world
state, prompts in preflight files, hidden grading, queue state, or NVML.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
VERSION = "v054-kernel-request-timing-supplement-r1"
BUCKETS = ((2048, "0-2047"), (4096, "2048-4095"), (8192, "4096-8191"),
           (12288, "8192-12287"), (16385, "12288-16384"))


def stamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires timezone")
    return parsed.timestamp()


def finite(value, *, positive=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def bucket(value):
    return next((label for upper, label in BUCKETS if value < upper), ">16384")


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "min": None, "median": None, "p90": None, "max": None}
    pos = (len(ordered) - 1) * .9
    lower = int(pos)
    p90 = ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (pos - lower)
    return {"n": len(ordered), "min": ordered[0], "median": statistics.median(ordered),
            "p90": p90, "max": ordered[-1]}


class Reader:
    def __init__(self):
        self.sources = {}

    def read(self, path, expected=None, *, json_lines=False):
        path = Path(path).resolve()
        if not path.is_relative_to(ROOT / "runs"):
            raise ValueError("Input artifact must remain in project runs")
        if any(part in {"managed-world", "public-source", "candidates", "official-output"}
               for part in path.parts):
            raise ValueError("Task/world/hidden output is outside this metadata-only supplement")
        if str(path) in self.sources:
            raise ValueError("Duplicate immutable artifact read: " + str(path))
        data = path.read_bytes()
        ref = {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        if expected and (ref["sha256"] != expected["sha256"]
                         or ("bytes" in expected and ref["bytes"] != expected["bytes"])):
            raise ValueError("Artifact differs from monitor/controller reference: " + str(path))
        self.sources[str(path)] = ref
        return ([json.loads(line) for line in data.splitlines() if line.strip()]
                if json_lines else json.loads(data)), ref


def native_record(base, native, usage, reference, expected_attempt=None, wrapper_seconds=None):
    measured = native.get("usage")
    if (not isinstance(measured, dict) or measured != usage
            or any(type(measured.get(k)) is not int or measured[k] < 0
                   for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
            or measured["prompt_tokens"] + measured["completion_tokens"] != measured["total_tokens"]):
        raise ValueError("Native usage differs from settled controller usage")
    if expected_attempt and native.get("attempt_id") != expected_attempt:
        raise ValueError("Native attempt differs from controller")
    seconds = native.get("seconds")
    if not finite(seconds, positive=True):
        raise ValueError("Missing positive native generate seconds")
    return {**base, "native_attempt_id": native.get("attempt_id"), "usage": measured,
            "prompt_bucket": bucket(measured["prompt_tokens"]), "generate_seconds": seconds,
            "output_tokens_per_generate_second": measured["completion_tokens"] / seconds,
            "complete_wrapper_seconds": wrapper_seconds if finite(wrapper_seconds) else None,
            "native_response": reference}


def session_path(path):
    path = Path(path).resolve()
    if "/owner-service/episodes/" not in str(path) or not path.is_relative_to(ROOT / "runs"):
        raise ValueError("Unexpected resident session location")
    return path


def collect_episode(reader, episode, cohort, requests, turns, errors):
    base = {"cohort": cohort, "slot_id": episode["slot_id"], "arm": episode["arm"],
            "revision": episode["revision"], "gpu": episode["gpu"]}
    controller_ref = episode.get("controller_ledger")
    if not controller_ref or "sha256" not in controller_ref:
        raise ValueError("Monitor did not retain an exact controller reference")
    controller, _ = reader.read(controller_ref["path"], controller_ref)
    ledger = controller["ledger"]
    session = None
    expected_calls = 0
    start_count = len(requests)
    start_turn_count = len(turns)
    if episode["arm"] == "MATCH":
        for call in ledger.get("calls", []):
            if not isinstance(call.get("usage"), dict):
                continue
            expected_calls += 1
            try:
                ref = call["response"]
                path = Path(ref["path"])
                if path.parent.name != "match-ledger":
                    raise ValueError("Unexpected MATCH response location")
                found_session = session_path(path.parent.parent)
                if session is not None and session != found_session:
                    raise ValueError("Controller references different resident sessions")
                session = found_session
                native, native_ref = reader.read(path, ref)
                requests.append(native_record(base, native, call["usage"], native_ref,
                                               call.get("native_attempt_id")))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append({**base, "scope": "native_request", "attempt": call.get("attempt"),
                               "error": str(exc)})
    elif episode["arm"] == "PROJECT":
        finish_path = Path(controller_ref["path"]).parent / "owner-finish.json"
        finish, _ = reader.read(finish_path)
        close_ref = finish["receipt"]
        if Path(close_ref["path"]).name != "owner-close.json":
            raise ValueError("Unexpected PROJECT owner-close reference")
        session = session_path(Path(close_ref["path"]).parent)
        for call in ledger.get("model", {}).get("records", {}).values():
            charge = call.get("charge", {})
            if not isinstance(charge.get("reported_usage"), dict):
                continue
            expected_calls += 1
            try:
                if call.get("status") != "settled":
                    raise ValueError("PROJECT charge is not settled")
                response_id = charge["response_id"]
                if not response_id.startswith("calibration_") or not response_id.replace("_", "").isalnum():
                    raise ValueError("Unexpected PROJECT response ID")
                wrapped, native_ref = reader.read(session / "owner/calls" / (response_id + ".json"))
                if wrapped.get("status") != 200 or wrapped.get("response", {}).get("id") != response_id:
                    raise ValueError("PROJECT response identity/status differs")
                requests.append(native_record(base, wrapped["native_result"], charge["reported_usage"],
                                               native_ref, wrapper_seconds=wrapped.get("elapsed_seconds")))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append({**base, "scope": "native_request", "call_id": call.get("call_id"),
                               "error": str(exc)})
    else:
        raise ValueError("Only MATCH/PROJECT GPU6 cohorts are supported")
    if session is None:
        errors.append({**base, "scope": "queue", "error": "No exact resident session located"})
    else:
        # Flat, small execution receipts only; never read *-preflight.json bodies.
        for pattern, kind in (("*-turn.json", "executed"), ("*-not-dispatched.json", "cancelled")):
            for path in sorted(session.glob(pattern)):
                try:
                    value, ref = reader.read(path)
                    queued = value.get("queued_seconds")
                    if not finite(queued) or not isinstance(value.get("original_operation"), str):
                        raise ValueError("Missing queue seconds or operation identity")
                    start, finish = value.get("started_monotonic"), value.get("finished_monotonic")
                    duration = finish - start if finite(start) and finite(finish) and finish >= start else None
                    turns.append({**base, "kind": kind, "operation": value.get("original_operation"),
                                  "ticket_id": value.get("ticket_id"), "queued_seconds": queued,
                                  "executor_envelope_seconds": duration, "error": value.get("error"),
                                  "receipt": ref})
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    errors.append({**base, "scope": "queue_receipt", "path": str(path), "error": str(exc)})
        if len(turns) == start_turn_count:
            errors.append({**base, "scope": "queue", "error":
                           "No usable queue timing receipts; waiting time is unknown, not zero"})
    return {**base, "started_utc": episode["started_utc"], "completed_utc": episode["completed_utc"],
            "episode_wall_seconds": episode["wall_seconds"],
            "started_before_window": episode.get("started_before_window"),
            "complete_token_ledger": bool(episode.get("tokens", {}).get("complete")) if episode.get("tokens") else False,
            "known_usage_calls": expected_calls, "native_timing_calls": len(requests) - start_count,
            "usable_queue_receipts": len(turns) - start_turn_count,
            "queue_coverage": "observed_receipts_only" if len(turns) > start_turn_count else "unknown",
            "tool_calls_or_actions": controller.get("tool_calls", controller.get("actions")),
            "tool_cpu_seconds": None, "tool_wall_seconds": None,
            "completion": episode["completion"], "controller": controller_ref}


def summarize_requests(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["cohort"], row["arm"], row["revision"], row["prompt_bucket"])].append(row)
    result = []
    for (cohort, arm, revision, prompt_bucket), group in sorted(groups.items()):
        seconds = sum(r["generate_seconds"] for r in group)
        output = sum(r["usage"]["completion_tokens"] for r in group)
        result.append({"cohort": cohort, "arm": arm, "revision": revision,
                       "prompt_bucket": prompt_bucket, "requests": len(group),
                       "episodes": len({r["slot_id"] for r in group}),
                       "prompt_tokens": sum(r["usage"]["prompt_tokens"] for r in group),
                       "output_tokens": output, "generate_seconds_sum": seconds,
                       "output_tokens_per_generate_second_pooled": output / seconds,
                       "generate_seconds": distribution([r["generate_seconds"] for r in group]),
                       "output_tokens_per_generate_second": distribution(
                           [r["output_tokens_per_generate_second"] for r in group])})
    return result


def summarize_queue(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["cohort"], row["arm"], row["revision"], row["kind"], row["operation"])].append(row)
    return [{"cohort": k[0], "arm": k[1], "revision": k[2], "kind": k[3], "operation": k[4],
             "receipts": len(g), "queue_seconds_sum": sum(x["queued_seconds"] for x in g),
             "queue_seconds": distribution([x["queued_seconds"] for x in g]),
             "executor_envelope_seconds": distribution(
                 [x["executor_envelope_seconds"] for x in g if x["executor_envelope_seconds"] is not None])}
            for k, g in sorted(groups.items())]


def write_new(path, value, *, lines=False):
    with path.open("x") as stream:
        if lines:
            for row in value:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monitor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("A fresh supplement output directory is required")
    reader = Reader()
    summary, _ = reader.read(args.monitor / "summary.json")
    if summary.get("status") != "completed":
        raise ValueError("Existing monitor must finish its complete window first; no early execution")
    intent, _ = reader.read(args.monitor / "intent.json")
    baseline, _ = reader.read(args.monitor / "baseline.json")
    trigger, _ = reader.read(args.monitor / "trigger.json")
    observed_path = args.monitor / "closed-episodes.jsonl"
    observed, _ = reader.read(observed_path, json_lines=True) if observed_path.exists() else ([], None)
    bounds = {"baseline": (stamp(baseline["start_utc"]), stamp(baseline["end_utc"])),
              "observed": (stamp(trigger["first_dispatch_utc"]), stamp(trigger["window_end_utc"]))}
    if (bounds["baseline"][1] != stamp(intent["activation_utc"])
            or bounds["baseline"][1] - bounds["baseline"][0] != 2700
            or bounds["observed"][1] - bounds["observed"][0] != 1800):
        raise ValueError("Monitor windows differ from the frozen 45/30 minute comparison")
    requests, turns, episodes, errors, exclusions, seen_slots = [], [], [], [], [], set()
    for cohort, records in (("baseline", baseline["records"]), ("observed", observed)):
        for record in records:
            if record.get("gpu") != 6:
                continue
            slot_id = record["slot_id"]
            closed = stamp(record["completed_utc"])
            valid_revision = ((record["revision"] == intent["new_bindings_sha"])
                              if cohort == "observed" else record["revision"] != intent["new_bindings_sha"])
            if not valid_revision or not bounds[cohort][0] <= closed < bounds[cohort][1]:
                exclusions.append({"slot_id": slot_id, "cohort": cohort, "reason": "revision_or_window"})
                continue
            if slot_id in seen_slots:
                raise ValueError("Duplicate selected episode: " + slot_id)
            seen_slots.add(slot_id)
            try:
                episodes.append(collect_episode(reader, record, cohort, requests, turns, errors))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append({"slot_id": slot_id, "cohort": cohort, "scope": "episode", "error": str(exc)})
    limitations = [
        "Different tasks, outputs, prompt lengths and shared-device conditions; no causal kernel speedup or accuracy-equivalence estimate.",
        "Cohorts contain episodes closed in monitor windows. All settled requests from those episodes are included, including work started before a window. Requests in still-running episodes are excluded, not zeroed.",
        "Native seconds includes prefill, decode, input tensor/start-record setup and output/logprob transfer. It excludes outer FIFO wait and earlier prompt preparation. Output tokens/native second is not isolated decode throughput.",
        "Queue wait includes FIFO and grant/commit delay. Executed and cancelled receipts are separate. Overlapping session waits cannot be read as GPU idle time.",
        "Queue receipts lack a direct native-attempt/prompt-length key. No ordinal-based join is assumed; queue summaries are by cohort/arm/operation, not prompt bucket.",
        "Actual tool CPU time is absent. MATCH native tool transcript has no tool wall timer. PROJECT interaction wall exists only in full world state; this metadata-only supplement does not read those task states. Tool wall/CPU remain null; configured limits and episode residuals are not substituted.",
        "Completion facts are reused from monitor artifacts without rereading each completion. Controller/native refs are checked once; native result files are read only to project usage, identity and timing fields.",
        "Missing timings are reported as errors and excluded from timed denominators. Counts and incomplete ledgers remain visible. No model requests, new GPU samples or service actions are performed.",
    ]
    report = {"version": VERSION, "created_utc": datetime.now(timezone.utc).isoformat(),
              "monitor": str(args.monitor.resolve()), "windows": {
                  "baseline": {"start_utc": baseline["start_utc"], "end_utc": baseline["end_utc"], "seconds": 2700},
                  "observed": {"start_utc": trigger["first_dispatch_utc"], "end_utc": trigger["window_end_utc"], "seconds": 1800}},
              "new_bindings_sha": intent["new_bindings_sha"], "selected_episode_count": len(seen_slots),
              "summarized_episode_count": len(episodes), "native_timing_requests": len(requests),
              "queue_receipts": len(turns), "request_groups": summarize_requests(requests),
              "queue_groups": summarize_queue(turns), "episodes": episodes, "errors": errors,
              "exclusions": exclusions, "monitor_baseline_errors": baseline.get("errors", []),
              "monitor_final_errors": summary.get("last_queue_artifact_errors", []),
              "limitations": limitations, "model_requests": 0, "new_GPU_samples": 0,
              "task_or_service_mutations": 0}
    args.output.mkdir(parents=True, exist_ok=False)
    write_new(args.output / "requests.jsonl", requests, lines=True)
    write_new(args.output / "queue-receipts.jsonl", turns, lines=True)
    write_new(args.output / "sources.json", list(reader.sources.values()))
    write_new(args.output / "report.json", report)
    text = ["# GPU6 native request timing supplement", "", *[f"- {x}" for x in limitations], "",
            f"Selected episodes: {len(seen_slots)}; timed requests: {len(requests)}; extraction errors: {len(errors)}.", "",
            "| Cohort | Arm | Revision | Prompt tokens | Requests | Native seconds total | Output tokens | Output/native second | Median native seconds |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for group in report["request_groups"]:
        text.append(f"| {group['cohort']} | {group['arm']} | {group['revision'][:12]} | {group['prompt_bucket']} | {group['requests']} | "
                    f"{group['generate_seconds_sum']:.3f} | {group['output_tokens']} | "
                    f"{group['output_tokens_per_generate_second_pooled']:.3f} | {group['generate_seconds']['median']:.3f} |")
    text.extend(["", "| Cohort | Arm | Revision | State | Operation | Receipts | Queue seconds total | Median queue seconds |",
                 "| --- | --- | --- | --- | --- | ---: | ---: | ---: |"])
    for group in report["queue_groups"]:
        text.append(f"| {group['cohort']} | {group['arm']} | {group['revision'][:12]} | {group['kind']} | {group['operation']} | "
                    f"{group['receipts']} | {group['queue_seconds_sum']:.3f} | {group['queue_seconds']['median']:.3f} |")
    with (args.output / "report.md").open("x") as stream:
        stream.write("\n".join(text) + "\n")
    print(json.dumps({"report": str((args.output / 'report.json').resolve()),
                      "selected_episodes": len(seen_slots), "timed_requests": len(requests), "errors": len(errors)}))


if __name__ == "__main__":
    main()
