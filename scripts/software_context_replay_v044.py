"""v044: 108 actual requests plus four hard rejections, CPU-only native replay.

Historical request recovery and lifecycle reconstruction are independent of any
saved projection snapshot. Original output, billing, actor and event order bind
presentation; projected copies never create a new historical action or result.
"""

from __future__ import annotations

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
from types import SimpleNamespace
import time

from proworksim.storage import atomic_write, digest, json_bytes, read_json
from proworksim.software_context_replay_v041 import reference

VERSION = "software-context-replay-v0.44"
SOURCE = Path(__file__).resolve().parents[1]
ASSOCIATION_KEYS = (
    "call_id",
    "decision_id",
    "worker_id",
    "opportunity_id",
    "decision_index",
    "requested_model",
    "backend_id",
    "action_protocol",
    "model_revision",
    "weight_identity",
    "harness_version",
    "identity_epoch",
)
EVENT_KINDS = frozenset(
    {
        "model_call",
        "model_attempt",
        "model_response",
        "model_format_error",
        "model_format_feedback",
        "harness_sdk_event",
        "model_tool_result",
        "harness_explicit_json_control",
        "process_violation",
        "execution_integrity_error",
        "permission_violation",
        "model_boundary_error",
    }
)
EXPECTED_COUNTS = {"generated": 108, "hard_context_rejected": 4}
SOURCE_PATHS = (
    "scripts/software_context_replay_v044.py",
    "tests/test_software_context_replay_v044.py",
    "src/proworksim/software_feedback_v044.py",
    "src/proworksim/software_context_v044.py",
    "src/proworksim/software_context_v042.py",
    "src/proworksim/software_context_v041.py",
    "src/proworksim/software_context_v034.py",
    "src/proworksim/software_context_v028.py",
    "src/proworksim/software_context_replay_v041.py",
    "src/proworksim/candidate_runtime_v015.py",
    "src/proworksim/harness_sdk.py",
    "src/proworksim/format_diagnostics.py",
)


def association(payload):
    return {key: copy.deepcopy(payload[key]) for key in ASSOCIATION_KEYS if key in payload}


def _require(value, message):
    if not value:
        raise ValueError(message)


def _message_bank_add(bank, message, source):
    bank.setdefault(
        digest(json_bytes(message)), {"message": copy.deepcopy(message), "source": source}
    )


def recover_request(start_event, template, message_bank, preparation):
    """Recover a rejected SDK request only from exact recorded message hashes."""
    payload = start_event["payload"]
    selection = payload["context_selection"]
    request = copy.deepcopy(template)
    messages, witnesses = [], []
    for index in selection["selected_indices"]:
        expected = selection["messages"][index]
        actual = message_bank.get(expected["sha256"])
        _require(actual is not None, "Missing exact SDK-selected message witness")
        messages.append(copy.deepcopy(actual["message"]))
        witnesses.append(
            {"sdk_message_index": index, "sha256": expected["sha256"], **actual["source"]}
        )
    request["messages"] = messages
    _require(
        digest(json_bytes(messages)) == selection["selected_messages_sha256"],
        "Recovered selected SDK messages differ",
    )
    _require(
        digest(json_bytes(request))
        == payload["request_sha256"]
        == preparation["original_request_sha256"],
        "Recovered whole request differs",
    )
    return request, witnesses


def _brief_lifecycle_event(event, source):
    from proworksim.software_feedback_v044 import event_identity

    payload = event["payload"]
    common = {
        "sequence": event["sequence"],
        "kind": event["kind"],
        "worker_id": event["worker_id"],
        "source": source,
        "runner_event_identity": event_identity(event["kind"], payload),
    }
    if event["kind"] == "model_attempt":
        if payload.get("stage") != "finished":
            return None
        reduced = {
            **association(payload),
            **{
                key: copy.deepcopy(payload[key])
                for key in ("stage", "status", "accounting", "team_accounting", "will_retry")
                if key in payload
            },
            "response_sha256": digest(json_bytes(payload.get("response"))),
            "response_body_sha256": digest(json_bytes(payload.get("response", {}).get("body"))),
            "request_sha256": digest(json_bytes(payload["request"])),
        }
    elif event["kind"] == "model_response":
        reduced = {
            **association(payload),
            "response_body_sha256": digest(json_bytes(payload["response"])),
            "response_id": payload["response"].get("id"),
        }
    elif event["kind"] == "model_call":
        reduced = copy.deepcopy(payload)
        reduced.pop("meter", None)
    elif event["kind"] in {"harness_sdk_event", "model_tool_result"}:
        return None  # used only for the exact-message recovery bank
    else:
        reduced = copy.deepcopy(payload)
        if event["kind"] == "model_boundary_error":
            reduced.pop("team_budget", None)
            reduced.pop("memory", None)
    return {**common, "payload": reduced}


def load_episode_history(episode):
    """Bind actual inputs/output/usage and original SDK events, old or v044.

    No tokenizer, model, world, acceptance or projection is executed here. The
    result is reusable by CPU replay and the independent real-run measurement.
    """
    episode = Path(episode).resolve()
    evidence_path, budget_path, events_path = (
        episode / name
        for name in ("organization-evidence.json", "team-budget.json", "experience.jsonl")
    )
    evidence, budget = read_json(evidence_path), read_json(budget_path)["model"]
    attempts = {entry["call_id"]: entry for entry in evidence["original_attempts"]}
    _require(
        len(attempts) == len(evidence["original_attempts"]), "Duplicate original attempt identity"
    )
    records = budget["records"]
    by_response = {}
    for call, record in records.items():
        response_id = record.get("charge", {}).get("response_id")
        if response_id:
            _require(response_id not in by_response, "One original response charged to two calls")
            by_response[response_id] = call
    bank, templates, generated, source_refs = (
        {},
        {},
        {},
        [reference(evidence_path), reference(budget_path), reference(events_path)],
    )
    for directory in sorted((episode / "raw-transport").glob("request-*")):
        paths = {
            key: directory / name
            for key, name in {
                "original": "original-request.json",
                "selected": "selected-request.json",
                "preparation": "budget-preparation.json",
                "projection": "projection.json",
                "response": "response.json",
            }.items()
        }
        _require(
            all(p.is_file() for p in paths.values()),
            "Actual transport request lacks immutable artifacts",
        )
        values = {key: read_json(path) for key, path in paths.items()}
        original, selected, preparation, response = (
            values[key] for key in ("original", "selected", "preparation", "response")
        )
        body = response.get("body", {})
        call = by_response.get(body.get("id"))
        _require(
            call in attempts and call not in generated,
            "Transport response lacks one original settled attempt",
        )
        record, attempt = records[call], attempts[call]
        member = record["member"]
        trace = body.get("token_trace", {})
        checks = {
            "started_settled": record.get("attempt_started") is True
            and record.get("status") == "settled",
            "original_output": attempt.get("status") == "success"
            and attempt.get("original_output_present") is True
            and response.get("http_status") == 200
            and bool(trace.get("output_ids")),
            "preparation": record.get("reservation", {}).get("preparation") == preparation,
            "original_request": digest(json_bytes(original))
            == preparation["original_request_sha256"]
            == attempt["request_sha256"],
            "selected_request": digest(json_bytes(selected))
            == preparation["selected_request_sha256"],
            "native_input": digest(json_bytes(trace.get("input_ids")))
            == preparation["input_ids_sha256"]
            == attempt["input_ids_sha256"],
            "native_output": digest(json_bytes(trace.get("output_ids")))
            == attempt["output_ids_sha256"],
            "response": digest(json_bytes(body))
            == record["charge"]["response_body_sha256"]
            == attempt["response_body_sha256"],
            "charged_usage": record["charge"].get("usage_status") == "reported_actual_trace"
            and record["charge"].get("reported_usage") == body.get("usage") == attempt.get("usage")
            and record["charge"].get("charged_tokens") == body.get("usage", {}).get("total_tokens"),
            "actor": attempt.get("worker_id") == member
            and body.get("actor_identity") == preparation.get("actor_identity"),
            "window": body.get("online_window_id") == preparation.get("window_id"),
            "prompt_count": len(trace.get("input_ids", []))
            == preparation["prompt_tokens"]
            == body.get("usage", {}).get("prompt_tokens"),
        }
        _require(
            all(checks.values()),
            "Historical generated request identity failed: "
            + str([k for k, v in checks.items() if not v]),
        )
        sources = {key: reference(path) for key, path in paths.items()}
        source_refs.extend(sources.values())
        generated[call] = {
            "kind": "generated",
            "slot_id": episode.name,
            "call_id": call,
            "member": member,
            "raw_request_id": directory.name,
            "original_request": original,
            "selected_request": selected,
            "response": response,
            "recorded_projection": values["projection"],
            "recorded_preparation": preparation,
            "team_accounting": copy.deepcopy(record["charge"]),
            "source_checks": checks,
            "sources": sources,
        }
        templates.setdefault(member, original)
        for index, message in enumerate(original["messages"]):
            _message_bank_add(
                bank, message, {**sources["original"], "json_pointer": f"/messages/{index}"}
            )
        for choice in body.get("choices", []):
            _message_bank_add(
                bank,
                choice["message"],
                {**sources["response"], "json_pointer": "/body/choices/0/message"},
            )
    events, starts, format_errors = [], {}, {}
    with events_path.open() as stream:
        for line_number, line in enumerate(stream, 1):
            if not any('"kind": "' + kind + '"' in line for kind in EVENT_KINDS):
                continue
            event = json.loads(line)
            kind, payload = event["kind"], event.get("payload")
            if kind not in EVENT_KINDS or not isinstance(payload, dict):
                continue
            src = {
                "path": str(events_path),
                "jsonl_line": line_number,
                "experience_sequence": event["sequence"],
            }
            if kind == "model_call" and payload.get("stage") == "started":
                _require(payload["call_id"] not in starts, "Duplicate original model-call start")
                starts[payload["call_id"]] = {
                    "sequence": event["sequence"],
                    "worker_id": event["worker_id"],
                    "payload": payload,
                    "source": src,
                }
            if kind == "model_format_error":
                format_errors[payload["call_id"]] = event
            if kind == "model_format_feedback":
                err = format_errors.get(payload["call_id"])
                _require(
                    err is not None
                    and err["sequence"] < event["sequence"]
                    and err["worker_id"] == event["worker_id"],
                    "Feedback lacks its earlier runner format-error event",
                )
            if kind == "harness_sdk_event":
                sdk = payload.get("event", {})
                if sdk.get("kind") == "MessageEvent":
                    message = sdk["llm_message"]
                    blocks = message["content"]
                    _require(
                        len(blocks) == 1 and blocks[0].get("type") == "text",
                        "Unexpected SDK message structure",
                    )
                    _message_bank_add(
                        bank, {"content": blocks[0]["text"], "role": message["role"]}, src
                    )
                elif sdk.get("kind") == "ObservationEvent":
                    blocks = sdk["observation"]["content"]
                    _require(
                        len(blocks) == 1 and blocks[0].get("type") == "text",
                        "Unexpected tool observation structure",
                    )
                    _message_bank_add(
                        bank,
                        {
                            "content": blocks[0]["text"],
                            "role": "tool",
                            "tool_call_id": sdk["tool_call_id"],
                            "name": sdk["tool_name"],
                        },
                        src,
                    )
            reduced = _brief_lifecycle_event(event, src)
            if reduced is not None:
                events.append(reduced)
    requests = []
    for call, start in starts.items():
        record = records[call]
        if call in generated:
            row = generated[call]
            _require(
                start["payload"]["request_sha256"] == digest(json_bytes(row["original_request"])),
                "Started request differs from actual original",
            )
        elif record.get("status") == "admission_rejected":
            _require(
                record.get("attempt_started") is False and call not in attempts,
                "Rejected shape has a generated attempt",
            )
            preparation = record["rejected_reservation"]["preparation"]
            request, witnesses = recover_request(
                start, templates[record["member"]], bank, preparation
            )
            row = {
                "kind": "hard_context_rejected"
                if record.get("budget_kind") == "context_capacity"
                else "team_budget_rejected",
                "slot_id": episode.name,
                "call_id": call,
                "member": record["member"],
                "raw_request_id": None,
                "original_request": request,
                "selected_request": None,
                "response": None,
                "recorded_projection": None,
                "recorded_preparation": preparation,
                "team_accounting": None,
                "source_checks": {"original_request_reconstructed": True, "no_generation": True},
                "message_witnesses": witnesses,
                "sources": {"budget": reference(budget_path), "events": reference(events_path)},
            }
        else:
            continue  # team reservations are outside the declared historical112 denominator
        _require(
            row["member"] == start["worker_id"] == start["payload"].get("worker_id"),
            "Started member ownership mismatch",
        )
        row.update(
            model_call_experience_sequence=start["sequence"],
            association=association(start["payload"]),
            start_source=start["source"],
        )
        requests.append(row)
    _require(
        len(generated) == sum(r["kind"] == "generated" for r in requests),
        "Generated request has no original start",
    )
    by_call = {r["call_id"]: r for r in requests}
    for event in events:
        payload = event["payload"]
        call = payload.get("call_id")
        row = by_call.get(call)
        if (
            row is None
            or row["kind"] != "generated"
            or event["kind"]
            not in {
                "model_call",
                "model_attempt",
                "model_response",
                "model_format_error",
                "model_format_feedback",
                "harness_explicit_json_control",
            }
        ):
            continue
        _require(
            event["worker_id"] == row["member"] and association(payload) == row["association"],
            "Lifecycle event association changed",
        )
        if event["kind"] == "model_attempt":
            _require(
                payload.get("status") == "success"
                and payload["request_sha256"] == digest(json_bytes(row["original_request"]))
                and payload["response_sha256"] == digest(json_bytes(row["response"]))
                and payload["team_accounting"] == row["team_accounting"],
                "Actual attempt disagrees with original transport/accounting",
            )
        if event["kind"] == "model_response":
            _require(
                payload["response_body_sha256"] == digest(json_bytes(row["response"]["body"])),
                "Original model-response body differs",
            )
    return {
        "version": VERSION,
        "episode": str(episode),
        "requests": sorted(requests, key=lambda r: r["model_call_experience_sequence"]),
        "events": events,
        "source_refs": list({r["path"]: r for r in source_refs}.values()),
        "counts": {kind: sum(r["kind"] == kind for r in requests) for kind in EXPECTED_COUNTS},
        "scope": "Read-only exact original request recovery; no tokenization, world/model action or new presentation.",
    }


def reconstruct_feedback_timeline(history):
    """Replay independently bound runner events; snapshots freeze before each call."""
    from proworksim.software_feedback_v044 import OrdinaryFeedbackLedger

    ledger = OrdinaryFeedbackLedger()
    by_call = {r["call_id"]: r for r in history["requests"]}
    before, checks, seen_attempts = {}, [], set()
    for event in history["events"]:
        payload = copy.deepcopy(event["payload"])
        kind = event["kind"]
        call = payload.get("call_id")
        row = by_call.get(call)
        if kind == "model_call" and payload.get("stage") == "started" and row is not None:
            before[call] = ledger.snapshot()
        binding = {}
        if (
            kind == "model_attempt"
            and payload.get("stage") == "finished"
            and payload.get("status") == "success"
        ):
            _require(
                row is not None and row["kind"] == "generated",
                "Actual generation absent from bound originals",
            )
            _require(call not in seen_attempts, "Duplicate actual generation")
            seen_attempts.add(call)
            payload["response"] = copy.deepcopy(row["response"])
            binding = {
                "selected_request": row["selected_request"],
                "selected_input_ids_sha256": row["recorded_preparation"]["input_ids_sha256"],
                "selected_request_ref": row["sources"]["selected"],
                "response_ref": row["sources"]["response"],
            }
        transitions = ledger.observe_event(
            kind,
            payload,
            source_event_id=event["runner_event_identity"],
            **binding,
        )
        if transitions:
            checks.append(
                {
                    "kind": kind,
                    "call_id": call,
                    "source": event["source"],
                    "transition_count": len(transitions) if isinstance(transitions, list) else 1,
                }
            )
    _require(len(before) == len(by_call), "Missing request-before lifecycle snapshot")
    _require(
        len(seen_attempts) == sum(r["kind"] == "generated" for r in by_call.values()),
        "Generation replay denominator differs",
    )
    return {
        "before_call": before,
        "final_snapshot": ledger.snapshot(),
        "event_checks": checks,
        "independently_bound_actual_generations": len(seen_attempts),
        "scope": "Only original actual generation and runner events update lifecycle; CPU copies do not create historical presentation or recovery.",
    }


def inventory(run_root, output):
    run_root, output = Path(run_root).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    plan = read_json(run_root / "plan.json")
    rows = []
    refs = [reference(run_root / "plan.json")]
    counts = {k: 0 for k in EXPECTED_COUNTS}
    for worker, units in plan["assignments"].items():
        for unit in units:
            episode = run_root / worker / "actual/episodes" / unit["slot_id"]
            if not (episode / "slot-result.json").exists():
                continue
            history = load_episode_history(episode)
            folder = output / unit["slot_id"]
            folder.mkdir()
            history_path = folder / "history.json"
            atomic_write(history_path, json_bytes(history))
            history_ref = reference(history_path)
            refs.append(history_ref)
            refs.extend(history["source_refs"])
            for request in history["requests"]:
                if request["kind"] not in EXPECTED_COUNTS:
                    continue
                path = folder / (request["call_id"] + "-original-request.json")
                atomic_write(path, json_bytes(request["original_request"]))
                rows.append(
                    {
                        key: request[key]
                        for key in (
                            "kind",
                            "slot_id",
                            "call_id",
                            "member",
                            "raw_request_id",
                            "model_call_experience_sequence",
                            "recorded_preparation",
                            "source_checks",
                            "sources",
                            "start_source",
                        )
                    }
                    | {"recovered_original_request": reference(path), "history": history_ref}
                )
                counts[request["kind"]] += 1
    passed = counts == EXPECTED_COUNTS and len(rows) == 112
    result = {
        "version": VERSION,
        "kind": "v044-historical112-original-source-inventory",
        "passed": passed,
        "expected_requests": 112,
        "generated_requests": counts["generated"],
        "hard_rejected_requests": counts["hard_context_rejected"],
        "rows": rows,
        "artifact_refs": list({r["path"]: r for r in refs}.values()),
        "new_tokenizer_calls": 0,
        "new_model_calls": 0,
        "new_backward_calls": 0,
        "model_weights_loaded": False,
        "scope": "Original exact JSON shapes and original measured hashes/tokens only; no new capacity conclusion yet.",
    }
    atomic_write(output / "inventory.json", json_bytes(result))
    _require(passed, "Historical denominator differs from fixed108+4")
    return result


def source_hashes(paths=SOURCE_PATHS):
    return {name: digest((SOURCE / name).read_bytes()) for name in paths}


def checked_reference(item):
    path = Path(item["path"])
    _require(digest(path.read_bytes()) == item["sha256"], "Frozen CPU input changed: " + str(path))
    return path


def load_cpu_measurement(plan_path):
    """Use original native renderer/tokenizer; cache identical complete encodings."""
    from proworksim.software_context_replay_v041 import load_native_measurement

    original = load_native_measurement(plan_path)
    renders, encodings, statistics = {}, {}, {"native_render_calls": 0, "native_tokenizer_calls": 0}

    def render(request):
        key = digest(json_bytes(request))
        if key not in renders:
            renders[key] = original.render(request)
            statistics["native_render_calls"] += 1
        return renders[key]

    def tokenizer(text, **kwargs):
        key = (text, json.dumps(kwargs, sort_keys=True))
        if key not in encodings:
            encodings[key] = original.tokenizer(text, **kwargs)
            statistics["native_tokenizer_calls"] += 1
        return encodings[key]

    return SimpleNamespace(
        render=render,
        prepare_request=render,
        tokenizer=tokenizer,
        recipe=original.recipe,
        inference_profile=original.inference_profile,
        identity={
            **original.identity,
            "measurement_version": VERSION,
            "cache_scope": "Exact repeated complete rendered prompt and tokenizer options only; no segment arithmetic or length estimate.",
        },
        statistics=statistics,
    )


def measure_new_request(request, measurement, *, ledger, member_id):
    from proworksim.software_context_replay_v041 import encode_request
    from proworksim.software_context_v044 import (
        project_software_request,
        protected_software_request,
    )

    selected, projection = project_software_request(
        request,
        render=measurement.render,
        tokenizer=measurement.tokenizer,
        context_limit=16384,
        ledger=ledger,
        member_id=member_id,
    )
    protected, protected_projection = protected_software_request(
        request, ledger=ledger, member_id=member_id
    )
    selected_encoding = encode_request(selected, measurement)
    protected_encoding = encode_request(protected, measurement)
    for key, encoding in (("selected", selected_encoding), ("protected", protected_encoding)):
        _require(
            projection[key + "_prompt_tokens"] == encoding["prompt_tokens"],
            "Projection/native prompt count differs",
        )
        hash_prefix = "" if key == "selected" else "protected_"
        _require(
            projection[hash_prefix + "input_ids_sha256"] == encoding["input_ids_sha256"]
            and projection[hash_prefix + "rendered_prompt_sha256"]
            == encoding["rendered_prompt_sha256"],
            "Projection/native hashes differ",
        )
    return {
        "selected": selected,
        "projection": projection,
        "encoding": selected_encoding,
        "protected": protected,
        "protected_projection": protected_projection,
        "protected_encoding": protected_encoding,
    }


def feedback_preservation_checks(original, selected, projection, *, ledger, member_id):
    """Check current page and pending error independently of fit and source flags."""
    from proworksim.software_context_v034 import observation_messages

    originals, kept = original["messages"], selected["messages"]
    observations = list(observation_messages(original))
    after = list(observation_messages(selected))
    current = copy.deepcopy(observations[-1][1]) if observations else None
    if current is not None:
        goal = current["observation"].get("root_goal", {})
        if goal.get("description") == current["observation"].get("contract"):
            goal.pop("description", None)
    tools = [m for m in originals if m.get("role") == "tool"]
    latest = []
    if tools:
        final = tools[-1]
        prior = [
            m
            for m in originals
            if m.get("role") == "assistant"
            and any(c.get("id") == final.get("tool_call_id") for c in m.get("tool_calls", []))
        ]
        _require(len(prior) == 1, "Newest feedback lacks one native assistant identity")
        latest = [prior[0], final]
    active = []
    for record in ledger.get("records", []):
        if (
            record["member_id"] != member_id
            or not record["ordinary"]
            or record["state"] != "pending_or_presented"
        ):
            continue
        matches = [
            i
            for i, m in enumerate(originals)
            if m in (record["original_message"], record["visible_message"])
        ]
        if len(matches) == 1:
            active.append(
                {
                    "feedback_id": record["feedback_id"],
                    "previous_presentations": len(record["presentations"]),
                    "visible_body_retained": record["visible_message"] in kept,
                }
            )
    removed = projection["format_feedback_projection"]["removed_feedback"]
    return {
        "request_fields_unchanged": {k: v for k, v in selected.items() if k != "messages"}
        == {k: v for k, v in original.items() if k != "messages"},
        "latest_observation_and_initial_information_unchanged": bool(
            current is None or (after and after[-1][1] == current)
        ),
        "latest_complete_tool_or_page_unchanged": all(m in kept for m in latest),
        "active_ordinary_feedback_retained": all(r["visible_body_retained"] for r in active),
        "latest_unpresented_feedback_retained": all(
            r["visible_body_retained"] for r in active if r["previous_presentations"] == 0
        ),
        "removed_errors_had_actual_presentation_and_transition": all(
            r["presentations"] and r["transitions"] for r in removed
        ),
    }, active


def _encoding_files(folder, prefix, request, encoding, projection=None):
    values = {
        prefix + "-request.json": json_bytes(request),
        prefix + "-native-prompt.txt": encoding["rendered_prompt"].encode(),
        prefix + "-input-ids.json": json_bytes(encoding["input_ids"]),
        prefix + "-encoding.json": json_bytes(
            {
                k: v
                for k, v in encoding.items()
                if k not in {"rendered_prompt", "input_ids", "native_messages"}
            }
        ),
    }
    if projection is not None:
        values[prefix + "-projection.json"] = json_bytes(projection)
    refs = []
    for name, data in values.items():
        path = folder / name
        atomic_write(path, data)
        refs.append(reference(path))
    return refs


def _replay_history(history_ref, plan_path, output):
    from proworksim.software_context_replay_v041 import encode_request
    from proworksim.software_context_v042 import project_software_request as old_project
    from proworksim.software_feedback_v044 import project_format_feedback

    history = read_json(checked_reference(history_ref))
    timeline = reconstruct_feedback_timeline(history)
    measurement = load_cpu_measurement(plan_path)
    output = Path(output) / Path(history["episode"]).name
    output.mkdir(parents=True, exist_ok=False)
    timeline_path = output / "lifecycle-timeline.json"
    atomic_write(timeline_path, json_bytes(timeline))
    refs = [reference(timeline_path), history_ref]
    rows = []
    for historical in history["requests"]:
        if historical["kind"] not in EXPECTED_COUNTS:
            continue
        original = historical["original_request"]
        preparation = historical["recorded_preparation"]
        state = timeline["before_call"][historical["call_id"]]
        old, old_projection = old_project(
            original,
            render=measurement.render,
            tokenizer=measurement.tokenizer,
            context_limit=16384,
        )
        old_encoding = encode_request(old, measurement)
        reproduction = {
            "original_request": digest(json_bytes(original))
            == preparation["original_request_sha256"],
            "selected_request": digest(json_bytes(old)) == preparation["selected_request_sha256"],
            "prompt_tokens": old_encoding["prompt_tokens"] == preparation["prompt_tokens"],
            "rendered_prompt": old_encoding["rendered_prompt_sha256"]
            == preparation["rendered_prompt_sha256"],
            "input_ids": old_encoding["input_ids_sha256"] == preparation["input_ids_sha256"],
            "context_limit": old_encoding["context_limit"] == preparation["context_limit"] == 16384,
            "output_reservation": old_encoding["reserved_output_tokens"]
            == preparation["reserved_output_tokens"]
            == 2048,
            "stored_selected": historical["selected_request"] is None
            or old == historical["selected_request"],
        }
        _require(
            all(reproduction.values()),
            "Original v042 request reproduction failed before new projection",
        )
        new = measure_new_request(
            original, measurement, ledger=state, member_id=historical["member"]
        )
        formatted, format_evidence = project_format_feedback(
            original, ledger=state, member_id=historical["member"]
        )
        selected_checks, active = feedback_preservation_checks(
            original,
            new["selected"],
            new["projection"],
            ledger=state,
            member_id=historical["member"],
        )
        protected_checks, _ = feedback_preservation_checks(
            original,
            new["protected"],
            new["projection"],
            ledger=state,
            member_id=historical["member"],
        )
        folder = output / historical["call_id"]
        folder.mkdir()
        artifacts = []
        for prefix, request, encoding, projection in (
            ("original", original, encode_request(original, measurement), None),
            ("v042-selected", old, old_encoding, old_projection),
            ("v044-format", formatted, encode_request(formatted, measurement), format_evidence),
            ("v044-selected", new["selected"], new["encoding"], new["projection"]),
            (
                "v044-protected",
                new["protected"],
                new["protected_encoding"],
                new["protected_projection"],
            ),
        ):
            artifacts.extend(_encoding_files(folder, prefix, request, encoding, projection))
        encoding, protected = new["encoding"], new["protected_encoding"]
        row = {
            "slot_id": historical["slot_id"],
            "member": historical["member"],
            "call_id": historical["call_id"],
            "historical_kind": historical["kind"],
            "original_reproduction_passed": all(reproduction.values()),
            "original_reproduction_checks": reproduction,
            "old_selected_prompt_tokens": old_encoding["prompt_tokens"],
            "new_selected_prompt_tokens": encoding["prompt_tokens"],
            "new_selected_hard_capacity_passed": encoding["fits"],
            "new_selected_headroom_tokens": encoding["headroom_tokens"],
            "new_protected_prompt_tokens": protected["prompt_tokens"],
            "new_protected_headroom_tokens": protected["headroom_tokens"],
            "new_protected_headroom_after_margin_tokens": protected["headroom_tokens"] - 1024,
            "protected_margin_diagnostic_only": True,
            "context_limit": 16384,
            "reserved_output_tokens": 2048,
            "latest_unpresented_feedback_retained": selected_checks[
                "latest_unpresented_feedback_retained"
            ]
            and protected_checks["latest_unpresented_feedback_retained"],
            "selected_preservation_checks": selected_checks,
            "protected_preservation_checks": protected_checks,
            "active_errors": active,
            "feedback_states": [
                {
                    k: r.get(k)
                    for k in (
                        "feedback_id",
                        "member_id",
                        "call_id",
                        "source_event_id",
                        "state",
                        "ordinary",
                    )
                }
                | {"prior_actual_presentations": len(r["presentations"])}
                for r in state["records"]
            ],
            "format_projection": format_evidence,
            "selected_indices": new["projection"]["selected_indices"],
            "removed_indices": new["projection"]["removed_indices"],
            "protected_indices": new["projection"]["protected_selected_indices"],
            "sources": historical["sources"],
            "artifacts": artifacts,
            "passed": all(reproduction.values())
            and encoding["fits"]
            and all(selected_checks.values())
            and all(protected_checks.values()),
            "scope": "Copied-input CPU capacity only. Historical output/actions/R are not counterfactual new-Gamma outcomes.",
        }
        atomic_write(folder / "measurement.json", json_bytes(row))
        refs.extend(artifacts + [reference(folder / "measurement.json")])
        rows.append(row)
    return {
        "rows": rows,
        "artifact_refs": refs,
        "native_measurement_identity": measurement.identity,
        "native_encoding_counts": measurement.statistics,
    }


def replay(inventory_root, output, *, plan_path=None, workers=4):
    inventory_root, output = Path(inventory_root).resolve(), Path(output).resolve()
    manifest_path = inventory_root / "inventory.json"
    manifest = read_json(manifest_path)
    _require(
        manifest["passed"]
        and manifest["expected_requests"] == 112
        and manifest["generated_requests"] == 108
        and manifest["hard_rejected_requests"] == 4,
        "Require frozen historical112 inventory",
    )
    plan_path = Path(plan_path or SOURCE / "runs/software-organization-v043/plan.json").resolve()
    histories = list({r["history"]["path"]: r["history"] for r in manifest["rows"]}.values())
    output.mkdir(parents=True, exist_ok=False)
    before = source_hashes()
    started = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=min(workers, len(histories))) as pool:
        jobs = [pool.submit(_replay_history, h, str(plan_path), str(output)) for h in histories]
        for job in as_completed(jobs):
            results.append(job.result())
    rows = sorted(
        [r for result in results for r in result["rows"]],
        key=lambda r: (r["slot_id"], r["call_id"]),
    )
    after = source_hashes()
    original_ok = len(rows) == 112 and all(r["original_reproduction_passed"] for r in rows)
    fits = len(rows) == 112 and all(r["new_selected_hard_capacity_passed"] for r in rows)
    pending = len(rows) == 112 and all(r["latest_unpresented_feedback_retained"] for r in rows)
    artifacts = (
        manifest["artifact_refs"]
        + [reference(manifest_path), reference(plan_path)]
        + [r for result in results for r in result["artifact_refs"]]
    )
    result = {
        "version": VERSION,
        "kind": "v044-historical112-single-candidate-native-replay",
        "passed": original_ok
        and fits
        and pending
        and all(r["passed"] for r in rows)
        and before == after,
        "expected_requests": 112,
        "generated_requests": sum(r["historical_kind"] == "generated" for r in rows),
        "hard_rejected_requests": sum(
            r["historical_kind"] == "hard_context_rejected" for r in rows
        ),
        "original_reproduction_passed": original_ok,
        "new_selected_hard_capacity_passed": fits,
        "latest_unpresented_feedback_retained": pending,
        "fit_requests": sum(r["new_selected_hard_capacity_passed"] for r in rows),
        "maximum_selected_prompt_tokens": max(r["new_selected_prompt_tokens"] for r in rows),
        "minimum_selected_headroom_tokens": min(r["new_selected_headroom_tokens"] for r in rows),
        "protected_margin_deficit_requests": sum(
            r["new_protected_headroom_after_margin_tokens"] < 0 for r in rows
        ),
        "source_files": before,
        "source_unchanged_during_measurement": before == after,
        "artifact_refs": list({r["path"]: r for r in artifacts}.values()),
        "native_measurement_identity": results[0]["native_measurement_identity"],
        "native_encoding_counts": {
            k: sum(r["native_encoding_counts"][k] for r in results)
            for k in ("native_render_calls", "native_tokenizer_calls")
        },
        "rows": rows,
        "new_model_calls": 0,
        "new_backward_calls": 0,
        "new_acceptance_executions": 0,
        "model_weights_loaded": False,
        "context_limit": 16384,
        "reserved_output_tokens": 2048,
        "protected_margin_tokens": 1024,
        "protected_margin_diagnostic_only": True,
        "started_at": started,
        "ended_at": time.time(),
        "scope": "One v044 presentation candidate. Hard selected capacity and exact pending feedback govern; 1024-token protected margin is diagnostic only. No old result, action, output, charge, page or permission changes.",
    }
    atomic_write(output / "qualification.json", json_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inventory", "replay"))
    parser.add_argument("--run-root", default=str(SOURCE / "runs/software-organization-v043"))
    parser.add_argument("--output", default=str(SOURCE / "runs/v044-controls/historical-inventory"))
    parser.add_argument(
        "--inventory-root", default=str(SOURCE / "runs/v044-controls/historical-inventory")
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    result = (
        inventory(args.run_root, args.output)
        if args.command == "inventory"
        else replay(
            args.inventory_root,
            args.output,
            plan_path=Path(args.run_root) / "plan.json",
            workers=args.workers,
        )
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "passed",
                    "expected_requests",
                    "generated_requests",
                    "hard_rejected_requests",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
