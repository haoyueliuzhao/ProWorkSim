"""Read existing small evidence for the 161 original DeepSeek generation unknowns.

No model replay, source workspace traversal, archive extraction, queue changes or
claim changes. Managed errors are located by their recorded sequence in bounded
experience metadata; model messages and patch contents are never copied out.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/software-benchmark-v055"
OUT = ROOT / "artifacts/software-benchmark-v055/exception-reconciliation-r1"
STATE = RUN / "queue-r1/state.json"
READS = Counter()
MAX_JSON = 2 * 1024**2


def ref(path, raw):
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def small(path, expected=None):
    if not path.is_file():
        return None, None
    if path.stat().st_size > MAX_JSON:
        raise ValueError("Metadata exceeds bounded JSON read: " + str(path))
    raw = path.read_bytes()
    READS["metadata_bytes"] += len(raw)
    READS["metadata_files"] += 1
    identity = ref(path, raw)
    if expected and identity["sha256"] != expected.get("sha256"):
        raise ValueError("Retained metadata reference mismatch: " + str(path))
    return json.loads(raw), identity


def pick(value, names):
    return {key: value[key] for key in names if key in value}


def first_error(error):
    message = (error or {}).get("message", "").split("\n")[0]
    if message.startswith("Conversation run failed for id="):
        message = message.split(": ", 1)[-1]
    return {"type": (error or {}).get("type"), "message": message[:1500]}


def error_event(ep, boundary):
    wanted = {e["sequence"] for detail in boundary.get("terminal_details", {}).values()
              for e in detail.get("evidence", []) if e.get("kind") in ("interface_error", "model_service_error")}
    if not wanted:
        return []
    path = ep / "managed-runtime/experience.jsonl"
    if not path.is_file():
        return []
    found, consumed = [], 0
    with path.open("rb") as stream:
        for line in stream:
            offset = consumed
            consumed += len(line)
            if consumed > 32 * 1024**2:
                break
            if b'"interface_error"' not in line and b'"model_service_error"' not in line:
                continue
            item = json.loads(line)
            if item.get("sequence") not in wanted:
                continue
            payload = item.get("payload", {})
            found.append({"sequence": item["sequence"], "kind": item["kind"],
                "error": first_error(payload), "action_already_performed": payload.get("action_already_performed"),
                "source": {"path": str(path), "offset": offset, "line_bytes": len(line),
                           "line_sha256": hashlib.sha256(line).hexdigest()}})
            if len(found) == len(wanted):
                break
    READS["bounded_managed_metadata_stream_bytes"] += consumed
    return found


def ledger():
    requests, failures = {}, defaultdict(list)
    with sqlite3.connect((RUN / "budget-r1/ledger.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        for sid, count, settled, uncertain, reserved in db.execute("""SELECT slot_id,COUNT(*),
            SUM(status='settled'),SUM(status='uncertain'),SUM(status='reserved')
            FROM requests GROUP BY slot_id"""):
            requests[sid] = {"request_count": count, "settled": settled,
                             "uncertain": uncertain, "reserved": reserved}
        for values in db.execute("""SELECT request_id,slot_id,status,max_output_tokens,
            settled_nanoyuan,reserved_nanoyuan,usage_json,failure_json FROM requests
            WHERE failure_json IS NOT NULL"""):
            request, sid, status, maximum, settled, reserved, usage, failure = values
            detail = json.loads(failure)
            failures[sid].append({"request_id": request, "status": status,
                "requested_max_output_tokens": maximum, "settled_cny": settled / 1e9 if settled is not None else None,
                "reserved_cny": reserved / 1e9, "usage": json.loads(usage) if usage else None,
                "failure": detail})
    return requests, failures


def classify(result, controller, events, provider_failures, stderr):
    outer = result.get("error", {}).get("message", "")
    if result.get("entered") is False and "native_uid_bootstrap" in outer:
        return "pre_entry_clone_manifest_prefix_rejected"
    if any(item["status"] == "uncertain" for item in provider_failures):
        return "historical_provider_accounting_uncertain"
    if any(item["failure"].get("reason") == "provider_output_exceeded_requested_max_tokens"
           for item in provider_failures):
        return "provider_output_over_requested_limit_settled_withheld"
    if controller.get("status") == "closed" and "quiescence" in outer:
        return "controller_closed_without_complete_bound_quiescence"
    error = first_error(controller.get("error"))["message"]
    managed = " | ".join(item["error"]["message"] for item in events)
    combined = managed or error
    if "second model decision in one opportunity" in combined:
        return "managed_sdk_second_decision_in_one_opportunity"
    if "must be followed by tool messages" in combined:
        return "native_sdk_missing_tool_result_pairing"
    if "reasoning provenance" in combined or "must preserve reasoning_content" in combined:
        return "native_thinking_reasoning_provenance_or_history"
    if "SDK changed the arguments" in combined:
        return "native_sdk_changed_original_tool_arguments"
    if any(text in combined for text in ("Unterminated string", "Expecting value", "Expecting property name",
                                         "Expecting ',' delimiter", "Expecting ':' delimiter")):
        return "provider_tool_arguments_json_parse_failed"
    if "Failed RPC cannot establish quiescence" in error:
        return "native_rpc_shutdown_could_not_prove_quiescence"
    if controller.get("error", {}).get("type") == "BrokenPipeError":
        return "native_rpc_broken_pipe"
    if not controller:
        return "controller_result_absent_after_worker_failure"
    if controller.get("execution_integrity_failure"):
        return "managed_execution_integrity_other"
    return "unclassified_retained_error"


def inspect(row, requests, provider_failures):
    slot, gen = row["slot"], row["generation"]
    sid = slot["slot_id"]
    directory = Path(gen["directory"])
    ep = directory / "episode"
    claim_dir = RUN / "episode-claims" / hashlib.sha256(sid.encode()).hexdigest()
    result, result_ref = small(ep / "result.json", gen.get("result"))
    done, done_ref = small(directory / "completion.json", gen.get("completion"))
    controller, controller_ref = small(ep / "controller-result.json")
    controller = controller or {}
    claim, claim_ref = small(claim_dir / "claim.json")
    claim_state, claim_state_ref = small(claim_dir / "state.json")
    quiet, quiet_ref = small(claim_dir / "quiescence.json")
    boundary, boundary_ref = small(ep / "managed-boundary.json")
    events = error_event(ep, boundary or {}) if controller.get("execution_integrity_failure") else []
    api = requests.get(sid, {"request_count": 0, "settled": 0, "uncertain": 0, "reserved": 0})
    failures = provider_failures.get(sid, [])
    candidate_paths = {name: (path.exists(), str(path)) for name, path in {
        "claim_candidate_result": claim_dir / "candidate-result.json",
        "candidate_directory": ep / "candidates",
        "official_code_request": ep / "official-code-request.json",
        "official_delivery_request": ep / "official-delivery-request.json"}.items()}
    if result["slot_id"] != sid or controller and controller.get("slot_id") != sid:
        raise ValueError("Result crosses original slot identity")
    if done.get("job") != gen.get("job") or claim["slot"] != slot:
        raise ValueError("Original completion or claim differs from slot identity")
    stderr = ""
    if result.get("entered") is False:
        stderr = (directory / "stderr.log").read_text()[:8192]
    category = classify(result, controller, events, failures, stderr)
    observations = {"slot_id": sid, "condition_id": slot["condition_id"], "instance_id": slot["instance_id"],
        "original_seed": slot["seed"], "original_generation_status": gen["status"], "directory": str(directory),
        "category": category, "result": pick(result, ("status", "entered", "entered_model", "slot_claimed",
            "controller_status", "error", "resource_release", "finally_stopped_scopes")),
        "result_reference": result_ref, "completion": pick(done, ("returncode", "status", "started_utc", "finished_utc")),
        "completion_reference": done_ref, "controller_reference": controller_ref,
        "controller": {**pick(controller, ("version", "status", "entered_model", "actual_model_calls",
            "candidate_selected", "writer_shutdown_requested", "process_tree_quiescence_proven",
            "execution_integrity_failure", "closure_reason")), "error": first_error(controller.get("error"))},
        "controller_token_accounting": pick(controller.get("ledger", {}), (
            "attempts", "known_actual_tokens", "complete_actual_tokens", "uncertain_reserved_tokens")),
        "managed_error_events": events, "managed_boundary_reference": boundary_ref,
        "claim_reference": claim_ref, "claim_state": claim_state, "claim_state_reference": claim_state_ref,
        "retained_quiescence": {"reference": quiet_ref, **pick(quiet or {}, ("all_quiet", "reason", "errors"))},
        "api_request_counts": api, "provider_failures": failures,
        "candidate_presence": {key: {"exists": exists, "path": path} for key, (exists, path) in candidate_paths.items()},
        "trusted_existing_locked_candidate_found": any(exists for exists, _ in candidate_paths.values()),
        "immediate_no_model_rescoring_possible": False,
        "rootfs_archival_marker_present": (ep / "actor/rootfs.lossless-archive-r1.json").is_file(),
        "rootfs_directory_present_without_traversal": (ep / "actor/rootfs").is_dir(),
        "recovery_assessment": "retain_original_unknown_no_trusted_locked_candidate"}
    if category == "provider_tool_arguments_json_parse_failed":
        calls = controller.get("ledger", {}).get("calls", [])
        response_ref = next((item.get("response") for item in reversed(calls) if item.get("response")), None)
        if response_ref:
            response, identity = small(Path(response_ref["path"]), response_ref)
            parsed = []
            for choice in response.get("choices", []):
                for call in choice.get("message", {}).get("tool_calls") or []:
                    try:
                        json.loads(call["function"]["arguments"])
                        parsed.append(True)
                    except (ValueError, KeyError, TypeError):
                        parsed.append(False)
            observations["last_retained_response_shape"] = {"reference": identity,
                "finish_reasons": [choice.get("finish_reason") for choice in response.get("choices", [])],
                "usage": response.get("usage"), "tool_arguments_valid_json": parsed,
                "no_tool_argument_or_message_content_exported": True}
    if category == "pre_entry_clone_manifest_prefix_rejected":
        job, job_ref = small(directory / "job.json", gen["job"])
        config_path = Path(job["argv"][job["argv"].index("--config") + 1])
        if config_path.parent != directory:
            raise ValueError("Pre-entry config is outside the original job directory")
        config, config_ref = small(config_path)
        routing, routing_ref = small(directory / "solver-routing.json")
        route_result, route_result_ref = small(directory / "solver-routing-result.json")
        prep, prep_ref = small(ep / "native-preparation.json")
        condition, condition_ref = small(Path(config["configuration"]["path"]), config["configuration"])
        # These exact artifacts precede actor/controller launch in the original runner.
        absent = {name: not path.exists() for name, path in {
            "entered_record": claim_dir / "entered.json", "scope_registry": claim_dir / "scope-registry.json",
            "watchdog_spec": claim_dir / "watchdog-spec.json", "actor_ready": ep / "worker-ready.json",
            "controller_ready": ep / "controller-ready.json", "controller_result": ep / "controller-result.json",
            "start_record": ep / "start.json", "resource_slice": ep / "resource-slice.json"}.items()}
        matches = (slot == job["slot"] == claim["slot"] and all(config[k] == slot[k]
                   for k in ("slot_id", "instance_id", "seed", "condition_id", "arm", "thinking")))
        routing_matches = routing.get("config") == config_ref
        before_enter = (result.get("entered") is False and api["request_count"] == 0
            and claim_state.get("entered") is False and claim_state.get("phase") == "claimed"
            and not result.get("finally_stopped_scopes") and all(absent.values())
            and route_result.get("actual_controller_routing_count") == 0 and matches and routing_matches
            and "Bootstrap only accepts this project's new preparation manifests" in stderr)
        observations["zero_model_pre_entry_evidence"] = {
            "historical_pre_entry_boundary_supported": before_enter,
            "does_not_replace_fresh_process_lock_and_resource_admission": True,
            "slot_seed_condition_consistent_across_queue_job_claim_config": matches,
            "provider_seed_supported": config.get("provider_seed_supported"), "seed_role": config.get("seed_role"),
            "frozen_config_reference": config_ref, "job_reference": job_ref,
            "routing_reference": routing_ref, "routing_config_binding_matches": routing_matches,
            "routing_result_reference": route_result_ref, "actual_controller_routing_count": route_result.get("actual_controller_routing_count"),
            "condition_reference": condition_ref, "configuration_matches_original_claim": claim["configuration"] == config["configuration"],
            "frozen_slots_reference": config["slots"], "authorization_reference": config["authorization"],
            "native_preparation_reference": prep_ref, "native_preparation_paths": prep,
            "absent_preentry_artifacts": absent, "original_claim_resume_or_resample_permitted": claim.get("resume_or_resample_permitted"),
            "stderr_reference": ref(directory / "stderr.log", stderr.encode()), "bootstrap_error_excerpt": stderr.splitlines()[-1],
            "original_runner_order": "ApiEpisode claim -> clone_prepared_rootfs -> create resources -> actor/controller launch -> entered.json",
            "bootstrap_rejection_order": "manifest prefix check precedes manifest read, destination creation and cp",
            "recovery_executed": False}
        observations["recovery_assessment"] = "historical_zero_model_boundary_supported_independent_recovery_decision_required" if before_enter else "preentry_evidence_incomplete"
    return observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-read-only", action="store_true", required=True)
    parser.parse_args()
    raw = STATE.read_bytes()
    state = json.loads(raw)
    rows = [row for row in state["rows"] if row["generation"]["status"] == "technical_unknown"]
    if len(rows) != 161:
        raise ValueError("Expected the original fixed 161 generation unknowns")
    requests, failures = ledger()
    inspected, errors, previous_partial = [], [], None
    prior_path = OUT / "deepseek-generation-audit-initial-partial.json"
    if prior_path.is_file():
        prior_raw = prior_path.read_bytes()
        prior = json.loads(prior_raw)
        if prior["source_queue"] != ref(STATE, raw):
            raise ValueError("Original queue changed since partial metadata audit")
        inspected = prior["rows"]
        READS.update(prior.get("read_volume", {}))
        previous_partial = ref(prior_path, prior_raw)
    existing = {row["slot_id"] for row in inspected}
    for row in rows:
        if row["slot"]["slot_id"] in existing:
            continue
        try:
            inspected.append(inspect(row, requests, failures))
        except Exception as error:
            errors.append({"slot_id": row["slot"]["slot_id"], "type": type(error).__name__, "message": str(error)})
    categories = Counter(row["category"] for row in inspected)
    condition_categories = {condition: dict(Counter(row["category"] for row in inspected if row["condition_id"] == condition))
                            for condition in sorted({row["slot"]["condition_id"] for row in rows})}
    ids = {row["slot"]["slot_id"] for row in rows}
    report = {"version": "v055-deepseek-generation-exception-reconciliation-r1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_queue": ref(STATE, raw), "source_queue_updated_utc": state["updated_utc"],
        "planned_original_unknown_count": 161, "inspected_count": len(inspected), "audit_errors": errors,
        "prior_partial_audit_preserved": previous_partial,
        "primary_category_counts": dict(categories), "condition_category_counts": condition_categories,
        "existing_trusted_candidate_count": sum(row["trusted_existing_locked_candidate_found"] for row in inspected),
        "historical_zero_model_pre_entry_supported_count": sum(row.get("zero_model_pre_entry_evidence", {}).get("historical_pre_entry_boundary_supported", False) for row in inspected),
        "archived_rootfs_marker_count": sum(row["rootfs_archival_marker_present"] for row in inspected),
        "provider_failure_records_on_original_unknowns": {sid: values for sid, values in failures.items() if sid in ids},
        "provider_failure_records_outside_original_unknowns": {sid: values for sid, values in failures.items() if sid not in ids},
        "rows": inspected, "read_volume": dict(READS),
        "scope": {"API_or_model_calls": 0, "GPU_queries": 0, "systemd_queries": 0, "queue_or_claim_writes": 0,
            "workspace_or_rootfs_traversals": 0, "archive_extractions": 0, "candidate_reselection": 0,
            "generation_replays": 0, "original_status_changes": 0},
        "interpretation": "161 retained original generation unknowns; no current model failure or resolved result inferred. Zero-model pre-entry evidence is historical eligibility for an independent operator decision, not permission to clear claims or replay entered episodes."}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "deepseek-generation-audit.json"
    with path.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(path), "inspected": len(inspected), "categories": dict(categories),
        "candidate_count": report["existing_trusted_candidate_count"],
        "zero_model_supported": report["historical_zero_model_pre_entry_supported_count"], "errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
