"""Refresh diagnostics on copies of seven completed fixed-model worlds.

This does not call a model or replay worker actions. Original calls, messages,
observations, approvals, manifests and artifact versions remain historical facts.
Only derived current-state freshness and evaluation records change in each copy.
"""

import argparse
import copy
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.contracts import EVALUATOR_VERSION
from proworksim.freshness import refresh_freshness
from proworksim.lifecycle import blocked_terminal, current_work_items
from proworksim.storage import Store, atomic_write, digest, json_bytes
from proworksim.validation import evaluate
from proworksim.workflow import is_complete


def object_hash(value):
    return digest(json_bytes(value))


def file_inventory(root):
    """Record relative paths and exact bytes, without opening a writable store."""
    return {
        str(path.relative_to(root)): digest(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def preserved_state(state):
    # Includes calls (and their original observations), messages, interactions,
    # requests, blockers, work/submission reviews, events and runtime contexts.
    return {
        key: value
        for key, value in state.items()
        if key not in {"artifacts", "evaluations"}
    }


def artifact_version_records(state):
    return {
        aid: {
            "current_version": artifact["current_version"],
            "versions": artifact["versions"],
        }
        for aid, artifact in state["artifacts"].items()
    }


def capture(path):
    state_bytes = (path / "control/state.json").read_bytes()
    state = json.loads(state_bytes)
    inventories = {
        name: file_inventory(path / folder)
        for name, folder in (
            ("versions", "control/versions"),
            ("manifests", "control/runs"),
            ("workspace", "workspace"),
            ("role_files", "control/role_files"),
        )
    }
    fingerprints = {
        "state_sha256": digest(state_bytes),
        "calls_sha256": object_hash(state["calls"]),
        "call_count": len(state["calls"]),
        "messages_sha256": object_hash(state["messages"]),
        "interactions_sha256": object_hash(state["interactions"]),
        "preserved_runtime_state_sha256": object_hash(preserved_state(state)),
        "artifact_version_records_sha256": object_hash(artifact_version_records(state)),
        **{
            f"{name}_tree_sha256": object_hash(inventory)
            for name, inventory in inventories.items()
        },
    }
    return state, inventories, fingerprints


def freshness(state):
    return {
        aid: {
            key: value
            for key, value in artifact.items()
            if key == "possibly_stale"
            or "freshness" in key
            or key.startswith("basis_applicability")
        }
        for aid, artifact in state["artifacts"].items()
    }


def business_state(state):
    return {
        item["work_item_id"]: {
            "status": item["status"],
            "applicability": item.get("applicability"),
            "submissions": [
                {
                    "submission_id": sub["submission_id"],
                    "artifact_versions": sub["artifact_versions"],
                    "review": sub.get("review"),
                    "invalidated": sub.get("invalidated"),
                    "current_applicability": sub.get("current_applicability"),
                }
                for sub in item["submissions"]
            ],
        }
        for item in state["work_items"].values()
    }


def terminal_state(state):
    return {
        "business_complete": is_complete(state),
        "blocked_unavailable": blocked_terminal(state),
        "active_work_statuses": {
            item["work_item_id"]: item["status"] for item in current_work_items(state)
        },
        "pending_events": len(state["events"]),
    }


def assessment(record):
    if record is None:
        return None
    return {
        key: record.get(key)
        for key in (
            "evaluator_version",
            "passed",
            "artifact_valid",
            "business_accepted",
            "currently_applicable",
            "numerical_assessment",
            "root_causes",
            "propagated_failures",
        )
    } | {
        "failed_checks": [
            check["name"] for check in record["checks"] if not check["passed"]
        ],
        "unassessed_checks": record.get("unassessed_checks", []),
    }


def reevaluate_world(source, destination, original_result):
    name = original_result["case"]
    source_path = source / name
    target = destination / "worlds" / name
    original, inventories_before, source_before = capture(source_path)
    # Copy only each actual world, not the experiment's redundant .snapshots.
    # Original result.json and control/runs manifests are retained byte-for-byte.
    shutil.copytree(source_path, target, ignore=shutil.ignore_patterns("world.lock"))
    copy_before, copy_inventories_before, copied_before = capture(target)
    if source_before != copied_before or inventories_before != copy_inventories_before:
        raise RuntimeError(f"Initial copy differs from source: {name}")

    store = Store(target)
    refreshed = copy.deepcopy(copy_before)
    refresh_freshness(refreshed)
    store.save(refreshed)
    current_evaluations = evaluate(target)
    copied, copy_inventories_after, copied_after = capture(target)
    _, inventories_after, source_after = capture(source_path)

    protected_fingerprints = (
        "calls_sha256",
        "call_count",
        "messages_sha256",
        "interactions_sha256",
        "preserved_runtime_state_sha256",
        "artifact_version_records_sha256",
        "versions_tree_sha256",
        "manifests_tree_sha256",
        "workspace_tree_sha256",
        "role_files_tree_sha256",
    )
    preserved_original_evaluations = all(
        row in copied["evaluations"] for row in original["evaluations"]
    )
    invariants = {
        "source_state_bytes_unchanged": source_before["state_sha256"]
        == source_after["state_sha256"],
        "source_calls_unchanged": source_before["calls_sha256"] == source_after["calls_sha256"],
        "source_version_bytes_unchanged": inventories_before["versions"]
        == inventories_after["versions"],
        "all_source_fingerprints_unchanged": source_before == source_after,
        "all_source_inventories_unchanged": inventories_before == inventories_after,
        "copy_initial_state_bytes_equal_source": copied_before["state_sha256"]
        == source_before["state_sha256"],
        "copy_calls_not_added_or_modified": copied_before["call_count"]
        == copied_after["call_count"]
        and copied_before["calls_sha256"] == copied_after["calls_sha256"],
        "original_runtime_messages_and_observations_unchanged": all(
            copied_before[key] == copied_after[key]
            for key in (
                "calls_sha256",
                "messages_sha256",
                "interactions_sha256",
                "preserved_runtime_state_sha256",
            )
        ),
        "copy_versions_bytes_equal_original": inventories_before["versions"]
        == copy_inventories_after["versions"],
        "original_manifests_preserved": inventories_before["manifests"]
        == copy_inventories_after["manifests"],
        "all_copy_protected_fingerprints_unchanged": all(
            copied_before[key] == copied_after[key] for key in protected_fingerprints
        ),
        "original_evaluations_retained": preserved_original_evaluations,
    }
    old_records = {
        (row["work_item_id"], row["submission_id"]): row for row in original["evaluations"]
    }
    changes = [
        {
            "work_item_id": row["work_item_id"],
            "submission_id": row["submission_id"],
            "original": assessment(
                old_records.get((row["work_item_id"], row["submission_id"]))
            ),
            "reevaluated": assessment(row),
        }
        for row in current_evaluations
    ]
    old_freshness, new_freshness = freshness(original), freshness(copied)
    old_business, new_business = business_state(original), business_state(copied)
    old_terminal, new_terminal = terminal_state(original), terminal_state(copied)
    report = {
        "case": name,
        "original_world": str(source_path),
        "copied_world": str(target),
        "original_run": original_result.get("run"),
        "source_fingerprints_before": source_before,
        "source_fingerprints_after": source_after,
        "copy_fingerprints_before": copied_before,
        "copy_fingerprints_after": copied_after,
        "immutable_version_file_hashes": inventories_before["versions"],
        "original_manifest_file_hashes": inventories_before["manifests"],
        "invariants": invariants,
        "integrity_passed": all(invariants.values()),
        "evaluation_changes": changes,
        "original_evaluations": original["evaluations"],
        "new_evaluations": current_evaluations,
        "freshness_changes": {
            aid: {"original": old_freshness[aid], "refreshed_copy": new_freshness[aid]}
            for aid in old_freshness
            if old_freshness[aid] != new_freshness[aid]
        },
        "original_freshness": old_freshness,
        "refreshed_copy_freshness": new_freshness,
        "business_state": {
            "changed": old_business != new_business,
            "original": old_business,
            "copy": new_business,
        },
        "terminal_state": {
            "changed": old_terminal != new_terminal,
            "original": old_terminal,
            "copy": new_terminal,
        },
        "original_worker_task_outcome_as_expected": original_result.get(
            "worker_task_outcome_as_expected"
        ),
        "new_model_calls": copied_after["call_count"] - copied_before["call_count"],
    }
    atomic_write(target / "reevaluation.json", json_bytes(report))
    return report


def reevaluate(source, destination, workers=3):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or source == destination or source in destination.parents:
        raise ValueError("Destination must be a new directory outside the source experiment")
    if workers < 1:
        raise ValueError("workers must be positive")
    summary_path = source / "summary.json"
    source_summary_bytes = summary_path.read_bytes()
    original_summary = json.loads(source_summary_bytes)
    results = original_summary["results"]
    names = [row["case"] for row in results]
    if len(names) != 7 or len(set(names)) != 7 or any(
        not isinstance(name, str)
        or Path(name).name != name
        or not (source / name / "control/state.json").is_file()
        for name in names
    ):
        raise ValueError("Expected seven distinct completed source world directories")
    identity_before = code_identity()
    destination.mkdir(parents=True)
    atomic_write(destination / "original_summary.json", source_summary_bytes)
    with ThreadPoolExecutor(max_workers=min(workers, len(results))) as executor:
        rows = list(
            executor.map(lambda row: reevaluate_world(source, destination, row), results)
        )
    identity_after = code_identity()
    source_summary_after = digest(summary_path.read_bytes())
    source_summary_before = digest(source_summary_bytes)
    code_unchanged = identity_before == identity_after
    report = {
        "experiment": "posthoc_fixed_staff_reevaluation",
        "source_experiment": str(source),
        "source_summary_sha256_before": source_summary_before,
        "source_summary_sha256_after": source_summary_after,
        "source_summary_unchanged": source_summary_before == source_summary_after,
        "original_code_identity": {
            key: original_summary.get(key)
            for key in ("code_commit", "code_dirty", "source_tree_sha256")
        },
        "original_code_after": original_summary.get("code_after"),
        "reevaluation_code_identity_before": identity_before,
        "reevaluation_code_identity_after": identity_after,
        "reevaluation_code_unchanged": code_unchanged,
        "evaluator_version": EVALUATOR_VERSION,
        "fresh_api_trajectories": False,
        "worker_actions_replayed": False,
        "runtime_observations_rewritten": False,
        "new_model_calls": sum(row["new_model_calls"] for row in rows),
        "original_worlds_modified": not all(
            row["invariants"]["all_source_fingerprints_unchanged"] for row in rows
        ),
        "initial_snapshots_copied": False,
        "original_manifests_retained": True,
        "manifest_path_references": "Preserved as recorded; may point to original snapshots.",
        "integrity_passed": all(row["integrity_passed"] for row in rows)
        and source_summary_before == source_summary_after
        and code_unchanged,
        "interpretation": (
            "Post-hoc diagnostics on byte-preserved copies of historical trajectories. "
            "Refreshed labels and new evaluations were not shown to the original worker. "
            "Business reviews, blocked outcomes and worker behavior are unchanged; "
            "this is neither a new API experiment nor evidence of improved worker behavior."
        ),
        "results": rows,
    }
    atomic_write(destination / "summary.json", json_bytes(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    report = reevaluate(args.source, args.destination, args.workers)
    print(
        json.dumps(
            {
                "summary": str(Path(args.destination) / "summary.json"),
                "evaluator_version": report["evaluator_version"],
                "integrity_passed": report["integrity_passed"],
                "new_model_calls": report["new_model_calls"],
                "worlds": [
                    {
                        "case": row["case"],
                        "integrity_passed": row["integrity_passed"],
                        "freshness_changed": sorted(row["freshness_changes"]),
                        "business_changed": row["business_state"]["changed"],
                        "terminal_changed": row["terminal_state"]["changed"],
                    }
                    for row in report["results"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not report["integrity_passed"]:
        raise SystemExit(1)
