"""Adopt only untouched v056 slots after the empty-tools transport correction.

No model, resident, worker, scorer, or cache is started/stopped by this tool.
Old queue state and per-job records remain unchanged; completed records are
reconciled into an in-memory copy before the independently bound r2 state is saved.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from proworksim import software_benchmark_queue_v056 as queue_api
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.storage import digest

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs/software-benchmark-v056"
VERSION = "v056-ref-budget-pending-adoption-r2"
REVISION = "v056-r2-empty-tools-normalization"
OLD_REVISION = "v056-r1"


def load(item):
    return json.loads(checked(item).read_bytes())


def read_old(directory):
    directory = Path(directory).resolve()
    if not directory.is_relative_to(RUNS) or directory == RUNS:
        raise ValueError("Only an independent v056 queue can be adopted")
    state_ref = reference(directory / "state.json")
    state = load(state_ref)
    binding = load(state["binding"])
    if state.get("version") != queue_api.VERSION or binding.get("version") != "v056-ref-budget-bindings-r1":
        raise ValueError("Unexpected predecessor queue or binding")
    plan = load(binding["plan"])
    if [row["slot"] for row in state["rows"]] != load(plan["slots"])["slots"]:
        raise ValueError("The predecessor inventory differs from its frozen slots")
    sources = load(binding["frozen_sources"])
    module_ref = next(item for item in sources["files"] if item["path"] == str(Path(queue_api.__file__).resolve()))
    checked(module_ref)  # We use precisely the unchanged predecessor reconciliation implementation.
    return state_ref, state, binding, plan


def refresh_copy(directory, state):
    """Reuse r1 completion handling while suppressing every queue write and dispatch."""
    value = queue_api.Queue.__new__(queue_api.Queue)
    value.root = Path(directory)
    value.state = copy.deepcopy(state)
    value.rows = {row["slot"]["slot_id"]: row for row in value.state["rows"]}
    value.children = {}
    events = []
    value.save = lambda: None
    value.event = lambda kind, **body: events.append({"kind": kind, **body})
    value.refresh_jobs()
    return value.state, events


def active_jobs(state):
    return {job_id: job for job_id, job in state["jobs"].items()
            if job["status"] in {"running", "launch_intent"}}


def source_revision_evidence(old_binding, new_binding, index_paths):
    old_sources = load(old_binding["frozen_sources"])
    new_sources = load(new_binding["frozen_sources"])
    old = {item["path"]: item for item in old_sources["files"]}
    new = {item["path"]: item for item in new_sources["files"]}
    archives, indexes = {}, []
    for path in index_paths:
        index_ref = reference(path)
        body = load(index_ref)
        pairs = body.get("copies", [body] if "original" in body else [])
        for pair in pairs:
            original, snapshot = pair["original"], pair["snapshot"]
            if original["path"] not in old or original != old[original["path"]]:
                raise ValueError("An archive is not a declared predecessor source")
            checked(snapshot)
            if (snapshot["sha256"], snapshot["bytes"]) != (original["sha256"], original["bytes"]):
                raise ValueError("An archived source does not retain its exact original bytes")
            archives[original["path"]] = snapshot
        indexes.append(index_ref)
    changed = [path for path in old.keys() & new.keys() if old[path]["sha256"] != new[path]["sha256"]]
    missing = sorted(set(changed) - set(archives))
    if missing:
        raise ValueError("Changed predecessor source lacks an exact archive: " + ", ".join(missing))
    return {"original_manifest": old_binding["frozen_sources"], "new_manifest": new_binding["frozen_sources"],
            "archive_indexes": indexes, "changed_sources": [{"old": old[path], "new": new[path],
                "old_bytes_snapshot": archives[path]} for path in sorted(changed)],
            "added_source_paths": sorted(new.keys() - old.keys()),
            "removed_source_paths": sorted(old.keys() - new.keys())}


def validate_live_adoption(state, old_binding, new_binding):
    evidence = []
    if load(old_binding["scorer_manifest"]) != load(new_binding["scorer_manifest"]):
        raise ValueError("Live adoption cannot also replace the scoring implementation")
    for job_id, job in active_jobs(state).items():
        folder = Path(job["directory"])
        started_ref = reference(folder / "started.json")
        started = load(started_ref)
        if (started.get("job") != job["job"] or started.get("host_process") != job.get("host_process")
                or not queue_api.alive(job.get("host_process"))):
            raise ValueError("Live worker identity must be observed before adoption")
        intent = load(job["job"])
        resource = Path(intent["resource_lock"]).resolve()
        if resource.parent != RUNS / "queue-resource-locks":
            raise ValueError("Live worker does not share the cross-revision resource lease")
        row = next((row for row in state["rows"] if row["slot"]["slot_id"] == job.get("slot_id")), None)
        item = {"job_id": job_id, "job": job["job"], "started": started_ref,
                "host_process": job["host_process"], "resource_lock": str(resource), "kind": job["kind"]}
        if job["kind"] == "generation":
            if row is None or row["generation"].get("job_id") != job_id or row["generation"]["status"] != "running":
                raise ValueError("Live generation occupancy differs from its slot")
            entered_ref = reference(Path(job["payload"]["output"]) / "start.json")
            entered = load(entered_ref)
            if entered.get("slot", {}).get("slot_id") != row["slot"]["slot_id"]:
                raise ValueError("Generation must have entered its already imported r1 controller")
            item["entered"] = entered_ref
            item["resident"] = job["resident"]
        elif job["kind"] == "score":
            if row is None or row["score"].get("job_id") != job_id or row["score"]["status"] != "running":
                raise ValueError("Live scorer occupancy differs from its slot")
            item["grader"] = job["grader"]
        elif job["kind"] not in {"prepare", "reclaim"}:
            raise ValueError("Unknown live work kind")
        evidence.append(item)
    return evidence


def revised_state(old_state, old_binding_ref, new_binding_ref, *, claim_exists):
    """Only never-dispatched pending rows move to r2; all prior records stay r1."""
    value = copy.deepcopy(old_state)
    moved, retained = [], []
    for row in value["rows"]:
        slot_id = row["slot"]["slot_id"]
        if row["generation"]["status"] == "pending":
            if (row["generation"].get("job_id") or row["score"]["status"] != "not_ready"
                    or any(job.get("slot_id") == slot_id and job["kind"] == "generation"
                           for job in value["jobs"].values()) or claim_exists(slot_id)):
                raise ValueError("A nominally pending slot has prior dispatch/claim evidence: " + slot_id)
            row["execution_revision"] = REVISION
            row["generation"]["source_revision"] = REVISION
            row["generation"]["source_binding"] = new_binding_ref
            moved.append(slot_id)
        else:
            row.setdefault("execution_revision", OLD_REVISION)
            row["generation"].setdefault("source_revision", OLD_REVISION)
            row["generation"].setdefault("source_binding", old_binding_ref)
            retained.append(slot_id)
    value.update(binding=new_binding_ref, queue_revision=REVISION, predecessor_binding=old_binding_ref,
                 adopted_utc=queue_api.now(), complete=False)
    # A prior coordinator's read-only final analysis is not the new queue's finalization.
    if "analysis_finalization" in value:
        value["predecessor_analysis_finalization"] = value.pop("analysis_finalization")
    return value, moved, retained


def validate_binding_change(old, new, new_root):
    if (new.get("version") != "v056-ref-budget-bindings-r1"
            or Path(new.get("queue_root", "")).resolve() != Path(new_root).resolve()):
        raise ValueError("The r2 binding must explicitly declare the fresh queue root")
    unchanged = ("plan", "images", "scorer_request_base", "max_generation", "max_scoring", "disk_floor_bytes",
                 "generation_reservation_bytes", "scoring_reservation_bytes", "cold_preparation_reservation_bytes")
    if any(old.get(key) != new.get(key) for key in unchanged):
        raise ValueError("Adoption cannot change tasks, budgets, conditions, scoring, concurrency or disk limits")
    for item in load(new["frozen_sources"])["files"]:
        checked(item)
    load(new["scorer_manifest"])


def inspect(directory):
    with queue_api.lock(Path(directory) / "coordinator.lock"):
        state_ref, state, _, _ = read_old(directory)
        refreshed, events = refresh_copy(directory, state)
        return {"version": VERSION, "mode": "inspect", "original_state": state_ref,
                "after_read_only_reconciliation": queue_api.summary(refreshed),
                "active_jobs": list(active_jobs(refreshed)), "reconciliation_events": events,
                "old_state_changed": False, "model_calls": 0, "dispatches": 0}


def adopt(directory, new_binding_ref, new_root, *, archive_indexes=(), allow_live=False):
    directory, new_root = Path(directory).resolve(), Path(new_root).resolve()
    if new_root == directory or not new_root.is_relative_to(RUNS) or new_root == RUNS:
        raise ValueError("Adoption needs a separate v056 state root")
    with queue_api.lock(directory / "coordinator.lock"), queue_api.lock(new_root / "coordinator.lock"):
        if any((new_root / name).exists() for name in ("state.json", "adoption.json", "adoption-intent.json")):
            raise ValueError("Never overwrite an attempted or running adoption")
        state_ref, original, old_binding, plan = read_old(directory)
        new_binding = load(new_binding_ref)
        validate_binding_change(old_binding, new_binding, new_root)
        revision_evidence = source_revision_evidence(old_binding, new_binding, archive_indexes)
        refreshed, events = refresh_copy(directory, original)
        live = active_jobs(refreshed)
        if live and not allow_live:
            raise ValueError("Inflight r1 work remains; inspect again after closure or explicitly adopt proved live workers")
        live_evidence = validate_live_adoption(refreshed, old_binding, new_binding) if live else []
        state, moved, retained = revised_state(refreshed, original["binding"], new_binding_ref,
            claim_exists=lambda slot_id: (RUNS / "episode-claims" / digest(slot_id.encode())).exists())
        if [row["slot"] for row in state["rows"]] != load(plan["slots"])["slots"]:
            raise ValueError("Slot identity/order changed during adoption")
        # Exact predecessor bytes remain independently available even after subsequent old-worker completions.
        raw_ref = write_new(new_root / "predecessor-state.json", Path(state_ref["path"]).read_bytes())
        refreshed_ref = write_new(new_root / "reconciled-predecessor-state.json", refreshed)
        intent = {"version": VERSION, "utc": queue_api.now(), "old_queue": str(directory),
            "new_queue": str(new_root), "original_state": state_ref, "original_state_snapshot": raw_ref,
            "reconciled_state_snapshot": refreshed_ref, "old_binding": original["binding"],
            "new_binding": new_binding_ref, "plan": old_binding["plan"],
            "migrated_never_started_slot_ids": moved, "retained_prior_slot_ids": retained,
            "source_revisions": revision_evidence, "reconciliation_events": events,
            "live_workers_adopted": live_evidence, "old_job_paths_and_references_preserved": True,
            "both_coordinators_excluded_during_adoption": True, "old_entered_slots_replayed": False,
            "new_task_or_seed_created": False, "models_reloaded_or_stopped": False,
            "generation_or_scoring_dispatched": False}
        intent_ref = write_new(new_root / "adoption-intent.json", intent)
        state["adoption"] = intent_ref
        adopted_ref = write_new(new_root / "state.json", state)
        write_new(new_root / "status.json", queue_api.summary(state))
        result = {"version": VERSION, "status": "adopted_pending_only", "intent": intent_ref,
                  "state": adopted_ref, "migrated_pending": len(moved), "retained_prior": len(retained),
                  "live_workers_adopted": len(live_evidence), "old_state_changed": False,
                  "queue_started": False, "model_calls": 0, "dispatches": 0}
        write_new(new_root / "adoption.json", result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-queue", type=Path, default=RUNS / "queue-r1")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--adopt", action="store_true")
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--binding-sha256")
    parser.add_argument("--new-root", type=Path, default=RUNS / "queue-r2")
    parser.add_argument("--archive-index", action="append", type=Path, default=[])
    parser.add_argument("--allow-live-adoption", action="store_true")
    args = parser.parse_args()
    if args.inspect:
        print(json.dumps(inspect(args.old_queue), ensure_ascii=False, indent=2))
        return 0
    if not args.binding or not args.binding_sha256:
        parser.error("--adopt needs a frozen --binding and --binding-sha256")
    item = reference(args.binding)
    if item["sha256"] != args.binding_sha256:
        raise ValueError("New binding identity changed")
    result = adopt(args.old_queue, item, args.new_root, archive_indexes=args.archive_index,
                   allow_live=args.allow_live_adoption)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
