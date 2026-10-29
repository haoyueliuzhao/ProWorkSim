"""Build a new administrative cursor; never rewrite old experiment evidence."""

from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
import sqlite3
import time

from proworksim import software_benchmark_dispatch_v066 as original
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = original.ROOT
OLD = ROOT / "runs/software-benchmark-v076/adaptive-concurrency-r1/api-coordinator"
RECOVERY = ROOT / "runs/software-benchmark-v080/dead-api-owner-r1"
PROPOSAL = ROOT / "artifacts/software-benchmark-v080/dead-owner-recovery-r1/proposal.json"
OUT = ROOT / "artifacts/software-benchmark-v081/dead-owner-recovery-r1"
VERSION = "v081-dead-owner-administrative-API-cursor-r1"


def load(ref):
    return json.loads(checked(ref).read_bytes())


def generation_entry(row, recovery_ref, receipt, *, claim_exists, request_exists):
    if (
        receipt.get("slot_id") != row["slot_id"]
        or receipt.get("slot_index") != row["slot_index"]
        or receipt.get("quiescent") is not True
        or receipt.get("cleanup_errors") != []
        or receipt.get("foreign_objects_modified") is not False
        or receipt.get("new_model_calls") != 0
        or receipt.get("replayed_episodes") != 0
    ):
        raise ValueError("Recovered episode is not this exact quiet original identity")
    evidence = load(receipt["evidence"])
    if evidence.get("row") != row or evidence.get("original_results_modified") is not False:
        raise ValueError("Retained evidence differs from the original task")
    usage = evidence["usage_observation"]
    old_result = receipt.get("original_result")
    if old_result is not None:
        value = load(old_result)
        if (
            value.get("slot_id") != row["slot_id"]
            or value.get("configuration") != row["configuration"]
            or value.get("instance_id") != row["instance_id"]
            or value.get("status") not in {"closed", "technical_unknown"}
        ):
            raise ValueError("Original result identity is not trustworthy")
        status = value["status"]
    else:
        status = "technical_unknown"
    known_model = (
        True if usage.get("settled_request_count", 0) else None if request_exists else False
    )
    return {
        "status": status,
        "entered": bool(claim_exists or request_exists),
        "result": old_result,
        "administrative_owner_recovery": recovery_ref,
        "candidate_evidence": receipt["evidence"],
        "actual_model_generation_known": known_model,
        "known_actual_tokens_lower_bound": usage["known_actual_tokens_lower_bound"],
        "recovered_usage_observation": usage,
        "retained_objects": receipt.get("retained_objects", []),
        "export_pending": receipt.get("export_pending", False),
        "automatic_replay": False,
        "error": None
        if status == "closed"
        else "Original API owner OOM before durable episode result; evidence retained",
    }


def build_cursor(
    before, additions, score_additions, *, consumed, scheduled, requested, rows, evidence
):
    """Pure assembly preserves every old terminal entry byte-equivalently."""
    targets = {
        row["slot_id"]: row
        for row in rows
        if row["model_key"] == "DEEPSEEK" and row["input_plus_output_tokens"] == 5_000_000
    }
    if not set(before["generation"]) <= targets.keys():
        raise ValueError("The previous cursor contains tasks outside the original API 5M panel")
    after = copy.deepcopy(before)
    for slot, entry in additions.items():
        if slot not in targets or (
            slot in after["generation"] and after["generation"][slot] != entry
        ):
            raise ValueError(
                "Administrative reconstruction cannot replace original terminal history"
            )
        after["generation"].setdefault(slot, entry)
    for slot in (
        set(before.get("active_generation", [])) | set(consumed) | set(scheduled) | set(requested)
    ) & targets.keys():
        if slot not in after["generation"]:
            after["generation"][slot] = {
                "status": "technical_unknown",
                "entered": slot in consumed or slot in requested,
                "result": None,
                "actual_model_generation_known": None if slot in requested else False,
                "error": "Previously scheduled or consumed original identity lacks a durable final result",
                "automatic_replay": False,
                "administrative_owner_recovery": evidence,
            }
    for slot, value in score_additions.items():
        if slot not in targets:
            raise ValueError("Score recovery belongs to another task")
        if slot not in after["scores"]:
            after["scores"][slot] = value
    # Root has already proven all live resources physically quiet. Pending
    # scores may only retain an original identity that has never been consumed.
    pending = []
    for kind, row, item, prepared in before.get("pending_scores", []):
        if row != targets.get(row["slot_id"]) or kind not in {"code", "delivery"}:
            raise ValueError("Pending score does not bind the original task row")
        key = ("score-" if kind == "code" else "delivery-score-") + str(row["slot_index"])
        if (original.BATCH_ROOT / "resource-claims" / (key + ".json")).exists():
            destination = "scores" if kind == "code" else "deliveries"
            after[destination].setdefault(
                row["slot_id"],
                {
                    "status": "technical_unknown",
                    "error": "Consumed scoring identity has no imported trusted endpoint",
                    "request": item if prepared else None,
                    "automatic_replay": False,
                },
            )
        else:
            pending.append([kind, row, item, prepared])
    after.update(
        unix=time.time(),
        phase="administratively_closed_after_owner_OOM",
        active_generation=[],
        active_grading=[],
        pending_controls=[],
        pending_scores=pending,
        administrative_owner_recovery={
            "version": VERSION,
            "evidence": evidence,
            "new_model_calls": 0,
            "replayed_episodes": 0,
            "original_results_changed": False,
            "original_scores_changed": False,
            "ledger_modified": False,
        },
    )
    return after


def assemble():
    proposal = load(reference(PROPOSAL))
    before_ref = reference(OLD / "cursor.json")
    before = load(before_ref)
    rows = load(reference(original.PLAN_FILE))["rows"]
    targets = {
        row["slot_id"]: row
        for row in rows
        if row["model_key"] == "DEEPSEEK" and row["input_plus_output_tokens"] == 5_000_000
    }
    if len(rows) != 6000 or len(targets) != 1000:
        raise ValueError("The exact original 6000/1000 identity panel is required")
    ledger = original.PREDECESSOR_ROOT / "api-budget/ledger.sqlite3"
    with sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True) as db:
        requested = {slot for (slot,) in db.execute("select distinct slot_id from requests")}
    event_ref = reference(OLD / "events.jsonl")
    scheduled = {
        event["slot_id"]
        for raw in checked(event_ref).read_bytes().splitlines()
        if raw and (event := json.loads(raw)).get("kind") == "generation_scheduled"
    }
    consumed = {
        slot
        for slot, row in targets.items()
        if any(
            (root / "resource-claims" / f"{role}-{row['slot_index']}.json").exists()
            for root in (original.PREDECESSOR_ROOT, original.BATCH_ROOT)
            for role in ("actor", "controller", "volume")
        )
    }
    additions, receipts, retained, usage_by_group = {}, {}, [], {}
    for item in proposal["rows"]:
        row = item["row"]
        slot = row["slot_id"]
        if row != targets.get(slot):
            raise ValueError("Recovery proposal changed an original task")
        ref = reference(RECOVERY / "episodes" / str(row["slot_index"]) / "completed.json")
        receipt = load(ref)
        entry = generation_entry(
            row, ref, receipt, claim_exists=slot in consumed, request_exists=slot in requested
        )
        receipts[slot] = ref
        retained.extend({"slot_id": slot, **value} for value in receipt.get("retained_objects", []))
        group = usage_by_group.setdefault(
            row["group_id"],
            {
                "tasks": 0,
                "known_actual_tokens_lower_bound": 0,
                "settled_request_count": 0,
                "unknown_or_reserved_request_ids": [],
            },
        )
        usage = entry["recovered_usage_observation"]
        group["tasks"] += 1
        group["known_actual_tokens_lower_bound"] += usage["known_actual_tokens_lower_bound"]
        group["settled_request_count"] += usage["settled_request_count"]
        group["unknown_or_reserved_request_ids"].extend(usage["unknown_or_reserved_request_ids"])
        if slot not in before["generation"]:
            additions[slot] = entry
    grader_ref = reference(RECOVERY / "grading/score-3536/completed.json")
    grade = load(grader_ref)
    if (
        grade.get("quiescent") is not True
        or grade.get("cleanup_errors") != []
        or grade.get("foreign_objects_modified") is not False
        or grade.get("new_official_test_calls") != 0
    ):
        raise ValueError("Original grader recovery is not complete")
    grade_request_ref = reference(original.GRADING_ROOT / "score-3536/request.json")
    grade_request = load(grade_request_ref)
    score_additions = {
        grade_request["slot_id"]: {
            "status": "technical_unknown",
            "request": grade_request_ref,
            "recovery_cleanup": grader_ref,
            "error": "Original host scoring owner OOM; consumed score identity is not replayed",
            "automatic_replay": False,
        }
    }
    OUT.mkdir(parents=True, exist_ok=True)
    proof_ref = write_new(
        OUT / "cursor-assembly-evidence.json",
        {
            "version": VERSION,
            "original_cursor": before_ref,
            "original_events": event_ref,
            "recovery_proposal": reference(PROPOSAL),
            "episode_receipts": receipts,
            "grader_receipt": grader_ref,
            "retained_objects": retained,
            "recovered_usage_by_group": usage_by_group,
            "source": reference(__file__),
            "new_model_calls": 0,
            "replayed_episodes": 0,
            "original_results_changed": False,
        },
    )
    after = build_cursor(
        before,
        additions,
        score_additions,
        consumed=consumed,
        scheduled=scheduled,
        requested=requested,
        rows=rows,
        evidence=proof_ref,
    )
    for key in ("generation", "scores", "deliveries"):
        assert all(after[key].get(slot) == value for slot, value in before[key].items())
    # Copy original checkpoint into a new audit path, leaving the original alone.
    original_copy = write_new(OUT / "original-api-cursor.json", checked(before_ref).read_bytes())
    after_ref = write_new(OUT / "administrative-api-cursor.json", after)
    quiet = write_new(
        OUT / "object-quiescence.json",
        {
            "version": VERSION,
            "quiescent": True,
            "cleanup_errors": [],
            "foreign_objects_modified": False,
            "episode_receipts": receipts,
            "grader_receipt": grader_ref,
            "all_objects_removed": not retained,
            "retained_objects": retained,
            "retained_objects_are_stopped_unique_candidate_sources": True,
            "new_model_calls": 0,
        },
    )
    return {
        "version": VERSION,
        "original_cursor": original_copy,
        "administrative_cursor": after_ref,
        "quiescence": quiet,
        "evidence": proof_ref,
        "generation_status_counts": dict(
            Counter(item["status"] for item in after["generation"].values())
        ),
        "newly_accounted_original_tasks": len(after["generation"]) - len(before["generation"]),
        "new_model_calls": 0,
        "original_cursor_written": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assemble", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(assemble(), ensure_ascii=False))
