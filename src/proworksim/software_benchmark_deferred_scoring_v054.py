"""Trusted end-stage exception inventory and one same-candidate scoring retry.

This host-only module does not alter the primary queue, model lifecycle, frozen
r5 grader or resource limits. It never constructs a model or runs actor tools.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / "runs/software-benchmark-v054/formal-queue-r1"
VERSION = "v054-deferred-scoring-r1"
TERMINAL_VERSION = "v054-deferred-primary-completion-v1"
SLOTS_SHA = "55899d0b83a5bab1082bccb50496fb6c1d7111ecb951fc4d61c222be19d88676"
RETRY_POLICY = {"enabled": True, "phase": "after_primary_inventory",
    "maximum_additional_attempts_per_endpoint": 1, "resources": "identical_to_original_request",
    "model_retry": False, "patch_selection": False}


def now():
    return datetime.now(timezone.utc).isoformat()


def read_ref(value):
    return json.loads(checked(value).read_bytes())


def read_snapshot(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return json.loads(raw), {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def optional_reference(path):
    return reference(path) if Path(path).is_file() else None


def pinned_value(value):
    if value is None:
        return None, None
    try:
        return read_ref(value), None
    except (OSError, ValueError, KeyError, TypeError) as error:
        return None, {"type": type(error).__name__, "message": str(error), "reference": value}


def billing(row):
    generation = row["generation"]
    ref = generation.get("actual_cost_ledger") or generation.get("controller_result")
    if ref is None:
        directory = generation.get("episode_output")
        if directory:
            ref = optional_reference(Path(directory) / "controller-result.json")
    body, error = pinned_value(ref)
    if body is None:
        return {"reference": ref, "known_actual_tokens": None, "complete_actual_tokens": None,
                "actual_usage_unknown": True, "not_assumed_zero": True, "evidence_error": error}
    ledger = body.get("ledger", {})
    ledger = ledger.get("model", ledger)
    records = ledger.get("records")
    known = ledger.get("known_actual_tokens")
    if "known_actual_tokens" not in ledger and isinstance(records, dict):
        # A PROJECT uncertain reservation is a billed upper bound, not known
        # actual usage. Only completely reported charges contribute here.
        known = sum(record["charge"]["reported_usage"]["total_tokens"]
                    for record in records.values()
                    if record.get("charge", {}).get("usage_status") == "reported_actual_trace")
    complete = ledger.get("complete_actual_tokens")
    unsettled = bool(ledger.get("inflight") or ledger.get("held_tokens", 0)
                     or ledger.get("uncertain_reserved_tokens", 0)
                     or ledger.get("integrity_failure") or body.get("execution_integrity_failure"))
    if "complete_actual_tokens" not in ledger:
        records = ledger.get("records", {})
        uncertain = any(record.get("charge", {}).get("usage_status") == "uncertain_attempt_charged_reservation"
                        for record in records.values())
        complete = known if type(known) is int and not unsettled and not uncertain else None
    return {"reference": ref, "known_actual_tokens": known,
            "complete_actual_tokens": complete, "actual_usage_unknown": complete is None or unsettled,
            "billed_tokens_including_uncertain_reservations": ledger.get("charged_tokens"),
            "held_tokens": ledger.get("held_tokens"),
            "uncertain_reserved_tokens": ledger.get("uncertain_reserved_tokens"),
            "inflight": copy.deepcopy(ledger.get("inflight")),
            "accounting_snapshot": copy.deepcopy(ledger), "not_assumed_zero": True}


def original_run_id(score, arm, endpoint):
    directory = score.get("worker_directory")
    if not directory:
        return None
    path = Path(directory) / "stdout.log"
    if not path.is_file():
        return None
    try:
        value = json.loads(next(line for line in reversed(path.read_text().splitlines()) if line.strip()))
        run_id = value["run_id"]
    except (OSError, ValueError, KeyError, StopIteration):
        return None
    return run_id if re.fullmatch(f"v054-{arm}-{endpoint}-[0-9a-f]{{40}}", run_id) else None


def collect_inventory(state, state_reference):
    """Collect all terminal exception types without changing primary records."""
    records = []
    for row in state["rows"]:
        generation, slot = row["generation"], row["slot"]
        score_errors = [(endpoint, score) for endpoint, score in row.get("scores", {}).items()
                        if score.get("status") == "technical_unknown"]
        bad_generation = generation.get("status") == "technical_unknown"
        cost = billing(row) if bad_generation or score_errors else None
        accounting_unknown = bool(cost and cost["actual_usage_unknown"])
        if not (bad_generation or score_errors):
            continue
        result, result_error = pinned_value(generation.get("result"))
        claim_root = ROOT / "runs/software-benchmark-v054/episode-claims" / hashlib.sha256(slot["slot_id"].encode()).hexdigest()
        common = {"slot": copy.deepcopy(slot), "generation_status": generation.get("status"),
            "generation_attempts": copy.deepcopy(generation.get("attempts", [])),
            "model_configuration": generation.get("config"),
            "original_execution_bindings": row.get("original_execution_bindings", row.get("next_execution_bindings")),
            "original_result": generation.get("result"), "result_evidence_error": result_error,
            "claim": optional_reference(claim_root / "claim.json"),
            "seed_receipt": optional_reference(claim_root / "seed.json"),
            "resident_release": result.get("resident_release") if result else None,
            "candidate_lock": result.get("candidate") if result else None,
            "billing": cost, "model_retry_allowed": False,
            "actor_feedback_allowed": False, "patch_reselection_allowed": False}
        if bad_generation:
            records.append({**common, "exception_id": hashlib.sha256((slot["slot_id"] + ':generation').encode()).hexdigest()[:32],
                "domain": "generation", "fault": copy.deepcopy(generation.get("error") or (result or {}).get("error")),
                "automatic_action": "none_preserve_original_generation_fault"})
        if accounting_unknown:
            records.append({**common, "exception_id": hashlib.sha256((slot["slot_id"] + ':accounting').encode()).hexdigest()[:32],
                "domain": "accounting", "automatic_action": "none_preserve_uncertain_usage"})
        for endpoint, score in score_errors:
            request, error = pinned_value(score.get("request"))
            run_id = original_run_id(score, slot["arm"], endpoint)
            output = Path(request["trusted_output_root"]) / run_id if request and run_id else None
            completion = (optional_reference(Path(score["worker_directory"]) / "completion.json")
                          if score.get("worker_directory") else None)
            records.append({**common,
                "exception_id": hashlib.sha256((slot["slot_id"] + ':scoring:' + endpoint).encode()).hexdigest()[:32],
                "domain": "scoring", "endpoint": endpoint, "fault": copy.deepcopy(score.get("error")),
                "original_score": copy.deepcopy(score), "original_request": score.get("request"),
                "request_evidence_error": error, "original_attempt": request.get("attempt", 1) if request else None,
                "original_run_id": run_id, "original_identity": optional_reference(output / "identity.json") if output else None,
                "original_receipt": optional_reference(output / "receipt.json") if output else None,
                "original_completion": completion,
                "frozen_resources": copy.deepcopy(request.get("limits")) if request else None,
                "patch": request.get("patch") if request else None,
                "candidate_tree_sha256": request.get("candidate_tree_sha256") if request else None,
                "baseline_tree_sha256": request.get("baseline_tree_sha256") if request else None,
                "dataset": request.get("dataset") if request else None,
                "image": copy.deepcopy(request.get("image")) if request else None,
                "scorer_manifest": request.get("scorer_manifest") if request else None,
                "candidate_lock": request.get("episode_candidate_lock") if request else common["candidate_lock"],
                "retry_requires_original_locked_candidate": True,
                "automatic_action": "inspect_existing_report_then_at_most_one_same_resource_scoring_attempt"})
    return {"version": VERSION, "created_utc": now(), "queue_state": state_reference,
            "planned_slots": state.get("planned_slots", len(state["rows"])), "exceptions": records,
            "original_deferred_events": copy.deepcopy(state.get("deferred_exceptions", [])),
            "model_retry_allowed": False, "unknown_usage_not_zeroed": True,
            "hidden_feedback_to_actor": False, "new_model_calls": 0}


def validate_primary(marker):
    if (marker.get("version") != TERMINAL_VERSION
            or marker.get("status") != "primary_inventory_finished_with_deferred_exceptions"
            or marker.get("planned_slots") != 1500 or marker.get("active_generation") != 0
            or marker.get("active_graders") != 0 or marker.get("primary_only") is not True
            or marker.get("no_generation_retry") is not True):
        raise ValueError("Only an immutable completed primary inventory admits end-stage scoring")
    policy = read_ref(marker["overlay_policy"])
    if policy.get("deferred_scoring") != RETRY_POLICY:
        raise ValueError("Explicit one-attempt same-resource deferred scoring authorization is required")
    bindings = read_ref(marker["bindings"])
    if (bindings.get("execution_authorized") is not True
            or bindings["slots"]["sha256"] != SLOTS_SHA):
        raise ValueError("The original 1500-slot authorized panel is required")
    declared = read_ref(bindings["slots"])["slots"]
    state = read_ref(marker["queue_state_snapshot"])
    rows = state["rows"]
    if (len(rows) != 1500 or len({r["slot"]["slot_id"] for r in rows}) != 1500
            or state.get("active_generation") != 0 or state.get("active_graders") != 0
            or any(r["generation"].get("status") not in {"closed", "technical_unknown"} for r in rows)
            or any(s.get("status") not in {"official_report", "technical_unknown"}
                   for r in rows for s in r.get("scores", {}).values())):
        raise ValueError("Pending or live primary work cannot be bypassed by deferred scoring")
    if {row["slot"]["slot_id"]: row["slot"] for row in rows} != {
            slot["slot_id"]: slot for slot in declared}:
        raise ValueError("The primary terminal snapshot changed the frozen tasks or seeds")
    return state


def make_retry_request(request):
    if request.get("preparation_only") is not False or request.get("actor_feedback") is not False:
        raise ValueError("Only the original closed formal candidate may be rescored offline")
    attempt = request.get("attempt", 1)
    if type(attempt) is not int or attempt < 1:
        raise ValueError("Invalid original grading attempt")
    result = copy.deepcopy(request)
    result["attempt"] = attempt + 1
    return result


def validate_retry_request(original, revised):
    if revised != make_retry_request(original):
        raise ValueError("Deferred scoring may change only the explicit attempt number")


def expected_identity(request, datasets=None):
    """Use the original pure identity builder, without importing Docker or scoring."""
    from . import software_benchmark_scorer_v054 as base
    from . import software_benchmark_scorer_r5_v054 as scorer
    datasets = {} if datasets is None else datasets
    dataset_key = request["dataset"]["sha256"]
    if dataset_key not in datasets:
        datasets[dataset_key] = base.read_local_dataset(request["dataset"])
    manifest = read_ref(request["scorer_manifest"])
    patch = checked(request["patch"]).read_bytes()
    scorer.check_candidate(request)
    identity, _ = base.make_identity(
        instance=datasets[dataset_key][request["instance_id"]], arm=request["arm"], endpoint=request["endpoint"],
        patch=patch, candidate_tree_sha256=request["candidate_tree_sha256"],
        baseline_tree_sha256=request["baseline_tree_sha256"], dataset_reference=request["dataset"],
        scorer_manifest=manifest, image_record=request["image"], config_sha256=request["config_sha256"],
        limits=request["limits"], preparation_only=False, attempt=request.get("attempt", 1))
    identity.update(version=scorer.VERSION, baseline_mapping=request["baseline_mapping"])
    digest = base.sha256(base.canonical(identity))
    return identity, f"v054-{request['arm']}-{request['endpoint']}-{digest[:40]}"


def existing_report(request, identity, run_id):
    from .software_benchmark_scorer_v054 import canonical, sha256
    directory = Path(request["trusted_output_root"]) / run_id
    receipt_path, identity_path = directory / "receipt.json", directory / "identity.json"
    if not receipt_path.is_file() or not identity_path.is_file():
        return None
    actual_identity, receipt = json.loads(identity_path.read_bytes()), json.loads(receipt_path.read_bytes())
    if actual_identity != identity or receipt.get("run_id") != run_id or receipt.get("identity_sha256") != sha256(canonical(identity)):
        raise ValueError("An existing grader output belongs to a different immutable scoring identity")
    if (receipt.get("status") != "official_report" or type(receipt.get("resolved")) is not bool
            or receipt.get("preparation_only") is not False or receipt.get("actor_feedback") is not False):
        return None
    return {"resolved": receipt["resolved"], "receipt": reference(receipt_path),
            "identity": reference(identity_path), "run_id": run_id}


def lock_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        stream.close()
        raise
    return stream


def grader_lease():
    for index in range(2):
        try:
            return lock_file(QUEUE / "locks" / f"grader-{index}.lock")
        except BlockingIOError:
            continue
    raise BlockingIOError("Original two-grader capacity is still occupied; no retry started")


def scorer_argv(request_path):
    return [str(ROOT / "tools/run_benchmark_runtime_v054.sh"), "--write-project", "/usr/bin/env",
            "PYTHONPATH=" + str(ROOT / "src"), "HF_HUB_OFFLINE=1", "HF_DATASETS_OFFLINE=1",
            "TRANSFORMERS_OFFLINE=1", "NO_PROXY=*", "no_proxy=*", "HTTP_PROXY=", "HTTPS_PROXY=",
            "ALL_PROXY=", "http_proxy=", "https_proxy=", "all_proxy=",
            str(ROOT / "runs/software-benchmark-v054/scorer-venv/bin/python"), "-B", "-m",
            "proworksim.software_benchmark_scorer_r5_v054", "--request", str(request_path)]


def mark_started(folder, value):
    """Permanent attempt intent; even an ambiguous startup is never replayed."""
    if (folder / "started.json").exists():
        raise ValueError("This endpoint's one additional scoring attempt was already consumed")
    return write_new(folder / "started.json", value)


def process_exception(item, root, *, datasets):
    folder = root / "exceptions" / item["exception_id"]
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "result.json").exists():
        return json.loads((folder / "result.json").read_bytes())
    result = {"exception_id": item["exception_id"], "slot_id": item["slot"]["slot_id"],
        "domain": item["domain"], "endpoint": item.get("endpoint"),
        "status": "unresolved", "new_model_calls": 0, "automatic_generation_retry": False}
    if item["domain"] != "scoring":
        result["reason"] = "Generation and billing exceptions are preserved without model replay"
        write_new(folder / "result.json", result)
        return result
    try:
        with lock_file(folder / "attempt.lock") as attempt_lock:
            original = read_ref(item["original_request"])
            old_identity, old_run = expected_identity(original, datasets)
            recovered = existing_report(original, old_identity, old_run)
            if recovered is not None:
                result.update(status="recovered_existing_official_report", official=recovered,
                              additional_scoring_attempts=0)
            else:
                revised = make_retry_request(original)
                validate_retry_request(original, revised)
                identity, run_id = expected_identity(revised, datasets)
                recovered = existing_report(revised, identity, run_id)
                if recovered is not None:
                    if not (folder / "started.json").exists():
                        raise ValueError("An additional attempt exists without this authorized intent")
                    result.update(status="official_report", official=recovered,
                                  additional_scoring_attempts=1, recovered_after_driver_interruption=True)
                elif (folder / "started.json").exists():
                    result.update(reason="Prior retry started without a complete determinate report; never replay",
                                  additional_scoring_attempts=1, retry_run_id=run_id)
                else:
                    completion = read_ref(item["original_completion"])
                    if completion.get("status") != "exited" or type(completion.get("returncode")) is not int:
                        raise ValueError("The original scoring worker has not finished")
                    if (Path(revised["trusted_output_root"]) / run_id).exists():
                        raise ValueError("The distinct retry output already exists; no implicit cache reuse")
                    if (folder / "request.json").exists():
                        if json.loads((folder / "request.json").read_bytes()) != revised:
                            raise ValueError("Prepared retry request changed")
                        request_ref = reference(folder / "request.json")
                    else:
                        request_ref = write_new(folder / "request.json", revised)
                    with grader_lease() as lease:
                        intent = {"version": VERSION, "original_request": item["original_request"],
                            "retry_request": request_ref, "old_run_id": old_run, "retry_run_id": run_id,
                            "original_attempt": original.get("attempt", 1), "attempt": revised["attempt"],
                            "resources": copy.deepcopy(original["limits"]), "only_attempt_changed": True,
                            "started_utc": now(), "driver_pid": os.getpid(), "new_model_calls": 0}
                        mark_started(folder, intent)
                        env = dict(os.environ, PYTHONPATH=str(ROOT / "src") + os.pathsep + str(ROOT),
                                   PYTHONDONTWRITEBYTECODE="1")
                        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                            env[key] = ""
                        with (folder / "stdout.log").open("xb") as stdout, (folder / "stderr.log").open("xb") as stderr:
                            child = subprocess.Popen(scorer_argv(request_ref["path"]), cwd=ROOT, env=env,
                                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                pass_fds=(lease.fileno(), attempt_lock.fileno()))
                            write_new(folder / "child.json", {"pid": child.pid, "started_utc": now(),
                                      "original_grader_lease_inherited": True})
                            code = child.wait()
                        write_new(folder / "completion.json", {"returncode": code, "completed_utc": now(),
                                  "retry_request": request_ref, "new_model_calls": 0})
                        recovered = existing_report(revised, identity, run_id)
                        result.update(additional_scoring_attempts=1, retry_run_id=run_id,
                                      retry_request=request_ref, returncode=code)
                        if recovered is not None and code == 0:
                            result.update(status="official_report", official=recovered)
                        else:
                            result["reason"] = "One identical-resource retry remained unknown; no further retry"
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result.update(reason="Deferred scoring was not safely completed", error={
            "type": type(error).__name__, "message": str(error)}, no_automatic_replay=True)
    write_new(folder / "result.json", result)
    return result


def run_deferred(primary_completion, output):
    marker, marker_ref = read_snapshot(primary_completion)
    state = validate_primary(marker)
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    with lock_file(root / "driver.lock"):
        if (root / "binding.json").exists():
            if read_ref(reference(root / "binding.json"))["primary_completion"] != marker_ref:
                raise ValueError("This deferred pass belongs to another primary completion")
        else:
            write_new(root / "binding.json", {"version": VERSION, "primary_completion": marker_ref,
                "driver_source": reference(__file__), "created_utc": now(), "maximum_additional_attempts": 1})
        inventory_path = root / "inventory.json"
        if inventory_path.exists():
            inventory = json.loads(inventory_path.read_bytes())
            if inventory["queue_state"] != marker["queue_state_snapshot"]:
                raise ValueError("Existing exception inventory belongs to another primary snapshot")
        else:
            inventory = collect_inventory(state, marker["queue_state_snapshot"])
            write_new(inventory_path, inventory)
        results, datasets = [], {}
        for item in inventory["exceptions"]:
            results.append(process_exception(item, root, datasets=datasets))
            atomic_write(root / "progress.json", json_bytes({"version": VERSION,
                "primary_completion": marker_ref, "processed": len(results), "total": len(inventory["exceptions"]),
                "results": results, "new_model_calls": 0}))
        unresolved = [row for row in results if row["status"] == "unresolved"]
        summary = {"version": VERSION, "status": "deferred_pass_finished_with_unresolved" if unresolved
                   else "deferred_pass_finished", "primary_completion": marker_ref,
                   "inventory": reference(inventory_path), "results": results, "unresolved": unresolved,
                   "unresolved_unique_slot_count": len({item["slot_id"] for item in unresolved}),
                   "primary_records_overwritten": False, "unknowns_counted_as_model_failure": False,
                   "new_model_calls": 0, "hidden_feedback_to_actor": False,
                   "maximum_additional_scoring_attempts_per_endpoint": 1, "completed_utc": now()}
        atomic_write(root / "summary.json", json_bytes(summary))
        return reference(root / "summary.json")
