"""Read-only postprocessing of one passive controller and optional physical capture.

Independent primary ledgers/outcomes supply coverage denominators. This tool never
replays actions, invokes a model, edits capture records, or assigns natural-task
dependency/misalignment truth. Output is stdout unless --output is explicitly set.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
import copy
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proworksim.software_observer_journal_v203_2_1 import (  # noqa: E402
    FORMAT, GENESIS, ObserverJournal,
)
from proworksim.software_observer_views_v203_2_1 import (  # noqa: E402
    AcceptedRequest, INTEGRITY_DIMENSIONS, ObserverViews, assess_integrity,
    validate_stage_assessment,
)
from proworksim.software_passive_observer_v203_2 import PassiveState  # noqa: E402


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path, sources, issues):
    path = Path(path)
    if not path.is_file():
        return None
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
        sources[str(path)] = {"sha256": sha(raw), "bytes": len(raw)}
        return value
    except (OSError, ValueError) as error:
        issues.append({"source": str(path), "kind": "invalid_primary_json", "error": str(error)})
        return None


def read_journal(path):
    """Check a committed SQLite snapshot without initializing or updating it."""
    path = Path(path).resolve()
    proof = {"path": str(path), "present": path.is_file(), "valid": False,
             "records": 0, "valid_prefix_records": 0, "issues": []}
    rows = []
    if not path.is_file():
        return rows, proof
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            if db.execute("SELECT value FROM metadata WHERE key='format'").fetchone()[0] != FORMAT:
                raise ValueError("Unsupported capture format")
            previous = GENESIS
            for raw in db.execute("SELECT * FROM observations ORDER BY sequence"):
                row = ObserverJournal._decode(raw)
                if row["sequence"] != len(rows) + 1 or row["previous_sha256"] != previous:
                    raise ValueError("Capture sequence/hash chain is broken")
                rows.append(row)
                previous = row["chain_sha256"]
            proof.update(valid=True, records=len(rows), last_chain_sha256=previous,
                         conflicts=db.execute("SELECT count(*) FROM conflicts").fetchone()[0])
    except Exception as error:
        proof["issues"].append({"kind": "invalid_journal", "error": str(error)})
    proof["valid_prefix_records"] = len(rows)
    return rows, proof


def reference_json(reference, controller, sources, issues):
    if not isinstance(reference, dict) or not reference.get("path"):
        return None
    original = Path(reference["path"])
    try:
        if str(original).startswith("/pws/output/"):
            path = controller / original.relative_to("/pws/output")
        else:
            path = original if original.is_absolute() else controller / original
        path = path.resolve()
        path.relative_to(controller)
        raw = path.read_bytes()
        if sha(raw) != reference.get("sha256") or len(raw) != reference.get("bytes"):
            raise ValueError("Primary ledger reference byte/hash mismatch")
        value = json.loads(raw)
        sources[str(path)] = {"sha256": sha(raw), "bytes": len(raw)}
        return value
    except (OSError, ValueError) as error:
        issues.append({"source": str(original), "kind": "invalid_primary_reference", "error": str(error)})
        return None


def actor_of(value):
    return value.get("actor") or value.get("member_id") or value.get("worker_id")


def known_time(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def action_projection(value):
    decision = value.get("decision") or {}
    tool = value.get("tool") or value.get("action") or decision.get("action")
    arguments = value.get("arguments", decision.get("arguments"))
    actor = actor_of(value)
    if not tool or not actor or arguments is None or "response" not in value:
        return None
    return {"actor": actor, "tool": tool, "arguments": arguments, "response": value["response"]}


def action_dimensions(tool):
    dimensions = ["tool_receipts"]
    groups = {
        "ownership": {"create_task", "claim_task", "return_task", "revise_task", "accept_transfer", "org_matrix_scope", "org_chief_assign"},
        "dependencies": {"create_task", "revise_task", "declare_dependency", "clear_dependency"},
        "communication": {"send_message", "handoff_patch", "read_work_event", "read_file", "integrate_patch"},
        "versions": {"write_file", "replace_file", "create_file", "delete_file", "rename_file", "integrate_patch", "fix_patch", "run_tests", "read_test_result", "org_review_patch"},
        "delivery": {"fix_patch", "org_review_patch", "submit_integration", "delivery_status"},
    }
    return dimensions + [name for name, tools in groups.items() if tool in tools]


def primary_trace(controller, boundary, sources, issues):
    path = controller / "managed-runtime/experience.jsonl"
    if not path.is_file():
        return [], False, {}
    selected, decisions, seen, digest = [], set(), set(), hashlib.sha256()
    model_responses = {}
    previous, final = None, None
    try:
        with path.open("rb") as stream:
            for line in stream:
                digest.update(line)
                if not line.endswith(b"\n"):
                    raise ValueError("Primary runtime trace has an incomplete tail")
                event = json.loads(line)
                sequence = event["sequence"]
                if previous is not None and sequence != previous + 1:
                    raise ValueError("Primary runtime trace is not contiguous")
                previous = sequence
                p = event["payload"]
                if event["kind"] == "model_response":
                    key = (event.get("worker_id"), p.get("service_completion_id"))
                    if key in model_responses and model_responses[key] != p:
                        raise ValueError("Provider response has conflicting SDK decision attribution")
                    model_responses[key] = p
                if event["kind"] == "run_boundary":
                    final = p
                if event["kind"] not in {"policy_decision", "tool_call", "harness_tool_call"}:
                    continue
                value = p.get("decision", {}) if event["kind"] == "policy_decision" else p
                key = canonical([event.get("worker_id"), value.get("model_call_id"),
                    value.get("model_tool_call_id"), value.get("decision_id"),
                    value.get("action"), value.get("arguments")])
                if event["kind"] == "policy_decision":
                    decisions.add(key)
                elif key in decisions and key not in seen:
                    projection = action_projection({**value, "actor": event.get("worker_id")})
                    if projection is not None:
                        selected.append(projection)
                        seen.add(key)
        sources[str(path)] = {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}
        return selected, final is not None and final == boundary and decisions == seen, model_responses
    except (OSError, ValueError, KeyError, TypeError) as error:
        issues.append({"kind": "invalid_primary_runtime_trace", "error": str(error)})
        return selected, False, model_responses


def analyze_capture(controller, episode, host=None):
    controller = Path(controller).resolve()
    host = Path(host).resolve() if host is not None else None
    sources, issues, fatal = {}, [], []
    ledger = read_json(controller / "model-ledger/ledger.json", sources, issues)
    boundary = read_json(controller / "managed-boundary.json", sources, issues)
    terminal = read_json(controller / "controller-result.json", sources, issues)
    if boundary is None and isinstance(terminal, dict):
        boundary = terminal.get("managed_boundary")
    trace_actions, trace_closed, model_responses = primary_trace(controller, boundary, sources, issues)
    capture_dir = controller / "model-ledger/passive-observer"
    capture_summary = read_json(capture_dir / "capture-summary.json", sources, issues) or {}
    capture_fault = read_json(capture_dir / "capture-fault.json", sources, issues)
    rows, journal = read_journal(capture_dir / "events.sqlite")
    physical_path = host / "physical-observer/events.sqlite" if host else None
    if host and not physical_path.is_file():
        candidates = list(host.glob("**/physical-observer/events.sqlite"))
        if len(candidates) == 1:
            physical_path = candidates[0]
        elif len(candidates) > 1:
            issues.append({"kind": "ambiguous_physical_journal", "count": len(candidates)})
    physical_rows, physical_journal = read_journal(physical_path) if physical_path else (
        [], {"present": False, "valid": False, "issues": [], "records": 0})
    by_kind = defaultdict(list)
    for row in rows:
        by_kind[row["kind"]].append(row)
        claimed = row["source"].get("episode_id")
        if claimed is not None and claimed != episode:
            fatal.append("sidecar_episode_attribution_mismatch")
    if ledger and ledger.get("slot_id") != episode:
        fatal.append("primary_ledger_episode_attribution_mismatch")
    initial = by_kind["INITIAL"][0]["payload"] if by_kind["INITIAL"] else {}
    members = set(initial.get("fixed_members", []))
    members.update((boundary or {}).get("initial_members", []))
    members.update((ledger or {}).get("per_member", {}))
    calls = list((ledger or {}).get("calls", []))
    members.update(call["member_id"] for call in calls if call.get("member_id"))
    views = ObserverViews(episode, sorted(members)) if members else None
    required_dimensions = INTEGRITY_DIMENSIONS + ("lifecycle",)
    expected = {name: [] for name in required_dimensions}
    observed = {name: [] for name in required_dimensions}
    invalid = {name: [] for name in required_dimensions}
    request_rows = {row["payload"].get("request_id"): row for row in by_kind["MODEL_REQUEST"]}
    response_rows = {row["payload"].get("request_id"): row for row in by_kind["MODEL_RESPONSE"]}
    physical = defaultdict(dict)
    for row in physical_rows:
        if row["kind"] not in {"HTTP_REQUEST", "HTTP_RESPONSE"}:
            continue
        p = row["payload"]
        context = p.get("context", {})
        logical = context.get("logical_id")
        physical_id = context.get("physical_id")
        try:
            if not logical or not physical_id or context.get("slot_id") != episode:
                raise ValueError("Physical context is not bound to this episode/request")
            raw = base64.b64decode(p["raw_base64"], validate=True)
            if sha(raw) != p.get("raw_sha256") or len(raw) != p.get("raw_bytes"):
                raise ValueError("Physical raw-byte hash/length mismatch")
            json.loads(raw)
            key = (logical, str(physical_id))
            if row["kind"] in physical[key]:
                raise ValueError("Physical attempt identity is ambiguous")
            physical[key][row["kind"]] = {"raw": raw, "payload": p, "source": row["source"]}
        except (ValueError, KeyError, TypeError) as error:
            issues.append({"kind": "invalid_physical_capture", "logical_id": logical, "error": str(error)})
            invalid["requests" if row["kind"] == "HTTP_REQUEST" else "responses"].append(
                f"physical:{logical}:{physical_id}")
    accepted_ids, accepted_meta = [], []
    for call in calls:
        request_id, actor = call.get("request_id"), call.get("member_id")
        if not request_id or not actor:
            issues.append({"kind": "unattributed_primary_call", "attempt": call.get("attempt")})
            expected["requests"].append("unattributed-primary-call")
            continue
        req_ref, resp_ref = "request:" + request_id, "response:" + request_id
        expected["requests"].append(req_ref)
        expected["responses"].append(resp_ref)
        request = reference_json(call.get("request"), controller, sources, issues)
        response = reference_json(call.get("response"), controller, sources, issues)
        sr, ss = request_rows.get(request_id), response_rows.get(request_id)
        wire = request.get("request") if isinstance(request, dict) else None
        body = ss["payload"].get("body") if ss else None
        req_valid = bool(sr and wire is not None and sr["payload"].get("wire") == wire
                         and actor_of(sr["payload"]) == actor)
        resp_valid = bool(ss and response is not None and response == body
                          and actor_of(ss["payload"]) == actor and body.get("usage") == call.get("usage")
                          and body.get("id") == call.get("response_id"))
        if sr and wire is not None and not req_valid:
            invalid["requests"].append(req_ref)
        if ss and response is not None and not resp_valid:
            invalid["responses"].append(resp_ref)
        if resp_valid:
            observed["responses"].append(resp_ref)
        sdk_response = model_responses.get((actor, call.get("response_id")))
        decision_id = None
        if (sdk_response and sdk_response.get("response") == body
                and isinstance(sdk_response.get("decision_id"), str)):
            decision_id = sdk_response["decision_id"]
        if call.get("usage_id", "agent") == "agent":
            expected["requests"].append("decision-link:" + request_id)
            if decision_id:
                observed["requests"].append("decision-link:" + request_id)
        pairs = []
        for (logical, physical_id), pair in physical.items():
            if logical != request_id or set(pair) != {"HTTP_REQUEST", "HTTP_RESPONSE"}:
                continue
            pr, ps = pair["HTTP_REQUEST"], pair["HTTP_RESPONSE"]
            if ps["payload"].get("metadata", {}).get("http_status") != 200:
                continue
            try:
                if (json.loads(pr["raw"]) != wire or json.loads(ps["raw"]) != body
                        or any(item["payload"]["context"].get("member_id") != actor for item in (pr, ps))
                        or pr["payload"]["observed_at"] > ps["payload"]["observed_at"]):
                    raise ValueError("Physical/controller request-response attribution or bytes differ")
                pairs.append((physical_id, pr, ps))
            except (ValueError, KeyError, TypeError) as error:
                invalid["requests"].append(req_ref)
                invalid["responses"].append(resp_ref)
                issues.append({"kind": "physical_primary_mismatch", "request_id": request_id, "error": str(error)})
        expected["responses"].append("raw-response:" + request_id)
        if len(pairs) != 1 or not req_valid or not resp_valid or views is None:
            if len(pairs) > 1:
                invalid["requests"].append(req_ref)
            continue
        physical_id, pr, ps = pairs[0]
        try:
            mode = pr["payload"].get("evidence_mode", "real_provider")
            accepted = AcceptedRequest.from_bytes(
                episode_id=episode, actor=actor, request_id=request_id,
                decision_id=decision_id, accepted_at=ps["payload"]["observed_at"],
                raw_request=pr["raw"], request_sha256=pr["payload"]["raw_sha256"],
                provider_receipt=body, mode=mode,
            )
            views.add_request(accepted)
            accepted_ids.append(request_id)
            observed["requests"].append(req_ref)
            observed["responses"].append("raw-response:" + request_id)
            accepted_meta.append({"request_id": request_id, "actor": actor,
                "decision_id": decision_id, "decision_link_status": "BOUND" if decision_id else "UNKNOWN",
                "accepted_at": accepted.accepted_at, "request_sha256": accepted.request_sha256,
                "physical_id": physical_id, "usage": body["usage"], "evidence_mode": mode})
        except (ValueError, PermissionError) as error:
            invalid["requests"].append(req_ref)
            issues.append({"kind": "rejected_member_request", "request_id": request_id, "error": str(error)})
    primary_ids = {call.get("request_id") for call in calls}
    unmatched = sorted(set(request_rows) - primary_ids, key=str)
    inflight = (ledger or {}).get("inflight")
    if inflight:
        expected["requests"].append("inflight:" + str(inflight.get("request_id")))
        expected["responses"].append("inflight:" + str(inflight.get("request_id")))
    outcomes = (boundary or {}).get("outcomes", [])
    side_outcomes = [row["payload"] for row in by_kind["OPPORTUNITY"]]
    opportunities_match = isinstance(outcomes, list) and canonical(outcomes) == canonical(side_outcomes)
    primary_actions = [action_projection(outcome) for outcome in outcomes]
    unprojectable = [index for index, (outcome, projection) in enumerate(zip(outcomes, primary_actions))
                     if outcome.get("action_performed") and projection is None]
    primary_actions = [value for value in primary_actions if value is not None]
    if trace_closed:
        trace_counter = Counter(canonical(item) for item in trace_actions)
        if any(trace_counter[key] < count for key, count in Counter(canonical(item) for item in primary_actions).items()):
            trace_closed = False
            issues.append({"kind": "primary_trace_outcome_mismatch"})
        else:
            primary_actions = trace_actions
            unprojectable = []
    receipt_actions = [action_projection(row["payload"]) for row in by_kind["RECEIPT"]]
    primary_counter = Counter(canonical(item) for item in primary_actions)
    receipt_counter = Counter(canonical(item) for item in receipt_actions if item is not None)
    action_match = primary_counter == receipt_counter and not unprojectable
    for index, item in enumerate(primary_actions):
        source = "primary-action:" + str(index) + ":" + sha(canonical(item).encode())
        for dimension in action_dimensions(item["tool"]):
            expected[dimension].append(source)
            signature = canonical(item)
            occurrence = sum(canonical(prior) == signature for prior in primary_actions[:index + 1])
            if receipt_counter[signature] >= occurrence:
                observed[dimension].append(source)
    intent_counter = Counter(canonical({key: row["payload"].get(key) for key in ("actor", "tool", "arguments")})
                             for row in by_kind["INTENT"])
    for index, item in enumerate(primary_actions):
        intent = {key: item[key] for key in ("actor", "tool", "arguments")}
        key = canonical(intent)
        source = "primary-intent:" + str(index) + ":" + sha(key.encode())
        for dimension in action_dimensions(item["tool"]):
            expected[dimension].append(source)
            occurrence = sum({key: prior[key] for key in ("actor", "tool", "arguments")} == intent
                             for prior in primary_actions[:index + 1])
            if intent_counter[key] >= occurrence:
                observed[dimension].append(source)
    for dimension in ("ownership", "dependencies", "communication", "versions", "delivery"):
        expected[dimension].append("initial-condition")
        if initial and initial.get("episode_id") == episode:
            observed[dimension].append("initial-condition")
    expected["delivery"].append("controller-terminal-result")
    if terminal is not None and terminal.get("status") == "closed":
        observed["delivery"].append("controller-terminal-result")
    journal_bad = journal["present"] and not journal["valid"]
    physical_bad = physical_journal["present"] and not physical_journal["valid"]
    if journal_bad:
        for dimension in INTEGRITY_DIMENSIONS:
            invalid[dimension].append("sidecar-chain-invalid")
    if physical_bad:
        for dimension in ("requests", "responses"):
            invalid[dimension].append("physical-chain-invalid")
    capture_closed = bool(by_kind["CAPTURE_CLOSED"] and journal["valid"] and not capture_fault
                          and capture_summary.get("observer_fault_count") == 0)
    request_closed = bool(ledger is not None and not inflight and not unmatched and capture_closed
                          and physical_journal["valid"])
    action_inventory_closed = bool(boundary is not None and (trace_closed or not unprojectable))
    time_coverage = True
    for row in rows:
        source = "capture-time:" + row["key"]
        expected["lifecycle"].append(source)
        if known_time(row["source"].get("capture_time")):
            observed["lifecycle"].append(source)
        else:
            time_coverage = False
    action_closed = bool(action_inventory_closed and opportunities_match and action_match and capture_closed and time_coverage)
    for index, outcome in enumerate(outcomes):
        source = "primary-opportunity:" + str(index)
        expected["lifecycle"].append(source)
        if index < len(side_outcomes) and side_outcomes[index] == outcome:
            observed["lifecycle"].append(source)
    expected["lifecycle"].extend(["initial-condition", "capture-closed", "primary-boundary"])
    if initial and initial.get("episode_id") == episode:
        observed["lifecycle"].append("initial-condition")
    if capture_closed:
        observed["lifecycle"].append("capture-closed")
    if boundary and any(all(row["payload"].get(key) == boundary.get(key)
                           for key in ("status", "closure_reason", "opportunities", "actions"))
                        for row in by_kind["BOUNDARY"]):
        observed["lifecycle"].append("primary-boundary")
    if journal_bad:
        invalid["lifecycle"].append("sidecar-chain-invalid")
    dimensions = {}
    for dimension in required_dimensions:
        closed = request_closed if dimension in {"requests", "responses"} else action_inventory_closed
        # Unexplained extra receipts mean the primary action inventory is not exhaustive.
        if dimension == "tool_receipts" and not action_match:
            closed = False
        dimensions[dimension] = {"expected_sources": expected[dimension], "observed_sources": observed[dimension],
            "invalid_sources": invalid[dimension], "coverage_closed": closed,
            "coverage_evidence": ["primary-ledger/physical/sidecar-reconciliation" if dimension in {"requests", "responses"}
                                  else "primary-outcomes/sidecar-reconciliation"] if closed else []}
    state = PassiveState(episode, sorted(members))
    stage_events, opportunities = [], []
    for row in rows:
        p, kind = row["payload"], row["kind"]
        source = {**row["source"], "observer_sequence": row["sequence"], "record_sha256": row["record_sha256"]}
        if kind == "OPPORTUNITY":
            opportunities.append({"actor": actor_of(p), "status": p.get("status"), "source": source,
                                  "organization_misalignment_not_inferred": True})
        if kind not in {"INITIAL", "INTENT", "RECEIPT"}:
            continue
        if kind == "INITIAL":
            p = {"issue": p.get("public_initial_message"), "organization": p.get("organization"),
                 "members": p.get("fixed_members"), "case_id": p.get("case_id"),
                 "source_kind": "actual_controller_initial_condition"}
        try:
            prior = len(state.events)
            state.apply({"kind": kind, "key": row["key"], "payload": p, "source": source})
            for event in state.events[prior:]:
                stage_events.append({"event_id": event["event_id"], "change_type": event["kind"],
                    "actor": event.get("actor"), "task": event.get("task"), "version": event.get("version"),
                    "test_passed": event.get("passed"), "source": source,
                    "requires_collaboration_change": "UNKNOWN", "necessity": "UNKNOWN"})
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            issues.append({"kind": "phase_projection_failed", "sequence": row["sequence"], "error": str(error)})
            dimensions["lifecycle"]["invalid_sources"].append("phase-projection:" + str(row["sequence"]))
    phases, member_inputs, stage_assessments = {}, {}, []
    for phase in (f"T{index}" for index in range(7)):
        point = state.phases.get(phase)
        if point is None:
            phases[phase] = {"observed": False, "absence_proven": action_closed,
                             "organization_misalignment": "UNKNOWN"}
            continue
        at_time = point["source"].get("capture_time")
        phases[phase] = {"observed": True, "source": point["source"], "metadata": point["metadata"],
                         "global_evaluator_state": point["state"], "member_view_requests": {}}
        if views is None or not known_time(at_time):
            phases[phase]["member_views_available"] = False
            continue
        views.add_global_event({"episode_id": episode, "event_id": "phase:" + phase,
                                "occurred_at": at_time, "payload": {"phase": phase, "source": point["source"]}})
        evaluator_view = views.global_view(at_time)
        for task_id, task in point["state"]["tasks"].items():
            if type(task.get("revision")) is not int:
                continue
            stage_assessments.append(validate_stage_assessment({
                "episode_id": episode, "task_id": task_id, "task_revision": task["revision"],
                "at_time": at_time, "phase": phase, "view_scope": "GLOBAL_EVALUATOR",
            }, evaluator_view))
        for actor in sorted(members):
            view = views.member_view(actor, at_time)
            projected = view.to_dict()
            phases[phase]["member_view_requests"][actor] = projected["request_id"]
            if projected["request_id"]:
                member_inputs.setdefault(projected["request_id"], projected)
    integrity = assess_integrity(episode, dimensions, required_dimensions=required_dimensions,
                                 fatal_errors=tuple(sorted(set(fatal))))
    return {
        "schema": "passive-capture-analysis-v203.2.1", "episode_id": episode,
        "integrity": integrity, "source_files": sources,
        "sidecar_journal": journal, "physical_journal": physical_journal,
        "reconciliation": {"primary_calls": len(calls), "accepted_byte_bound_requests": len(accepted_ids),
            "sidecar_requests_without_settled_primary": unmatched, "opportunities_match": opportunities_match,
            "primary_outcomes": len(outcomes), "sidecar_opportunities": len(side_outcomes),
            "primary_action_receipts_match": action_match, "unprojectable_primary_actions": unprojectable,
            "independent_runtime_trace_closed": trace_closed,
            "sidecar_time_coverage": time_coverage,
            "capture_closed": capture_closed},
        "accepted_requests": accepted_meta, "phases": phases, "member_inputs": member_inputs,
        "stage_assessments": stage_assessments, "objective_state_changes": stage_events,
        "opportunities": opportunities, "issues": issues,
        "natural_dependency_gold": False, "organizational_misalignment_detector": False,
        "new_model_requests": 0, "world_actions_replayed": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", type=Path, required=True)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--host", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = analyze_capture(args.controller, args.episode, args.host)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            stream.write(text)
        print(json.dumps({"output": str(args.output), "status": report["integrity"]["status"]}))
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
