"""Small per-run manifests and explicit episode outcomes, not a production audit service."""

import hashlib
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .contracts import CONTRACT_VERSION, EVALUATOR_VERSION, LEGACY_EVALUATOR_VERSION
from .formula import ENGINE_VERSION
from .storage import atomic_write, json_bytes, read_json


def code_identity():
    root = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
        )
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    source_hash = hashlib.sha256()
    for path in sorted((root / "src").rglob("*.py")):
        source_hash.update(str(path.relative_to(root)).encode())
        source_hash.update(path.read_bytes())
    return {
        "code_commit": commit,
        "code_dirty": dirty,
        "source_tree_sha256": source_hash.hexdigest(),
    }


def begin_run(world, backend, budget, protocol="full-observation-v1"):
    state = world.store.load()
    run_id = uuid.uuid4().hex
    snapshot = world.store.root.parent / ".snapshots" / world.store.root.name / run_id
    world.snapshot(snapshot)
    spec = read_json(world.store.control / "spec.json")
    manifest = {
        "run_id": run_id,
        **code_identity(),
        "schema_version": state["schema_version"],
        "contract_version": spec.get("contract_version", CONTRACT_VERSION),
        "evaluator_version": EVALUATOR_VERSION
        if spec.get("workflow")
        else LEGACY_EVALUATOR_VERSION,
        "spreadsheet_engine_version": ENGINE_VERSION,
        "actor_policy_versions": state["staff_policies"],
        "world_seed": spec["seed"],
        "lineage_id": state["project"]["lineage_id"],
        "generation_spec": spec,
        "budget": budget,
        "stop_reason": None,
        "provider": backend.provider,
        "policy_version": getattr(backend, "policy_version", backend.model),
        "observation_protocol": protocol,
        "initial_snapshot": str(snapshot),
        "branch_id": state["branch_id"],
        "initial_call_count": len(state["calls"]),
        "initial_action_count": len(state["interactions"]),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write(world.store.control / "runs" / run_id / "manifest.json", json_bytes(manifest))
    return manifest


def finish_run(world, manifest, reason):
    state = world.store.load()
    manifest["stop_reason"] = reason
    manifest["ended_at"] = datetime.now(timezone.utc).isoformat()
    calls = state["calls"][manifest["initial_call_count"] :]
    attempts = [a for c in calls for a in c.get("attempts", [])]
    manifest["logical_calls"] = len(calls)
    manifest["completed_calls"] = sum(bool(c.get("response")) for c in calls)
    manifest["recorded_http_attempts"] = len(attempts)
    manifest["unknown_usage_attempts"] = sum(a.get("usage") is None for a in attempts)
    atomic_write(
        world.store.control / "runs" / manifest["run_id"] / "manifest.json", json_bytes(manifest)
    )
    return manifest


def episode_record(state):
    latest = {}
    for evaluation in state["evaluations"]:
        latest[evaluation["work_item_id"], evaluation["submission_id"]] = evaluation
    finals = []
    for work in state["work_items"].values():
        sub = work["submissions"][-1] if work["submissions"] else None
        finals.append(latest.get((work["work_item_id"], sub["submission_id"] if sub else None)))
    valid = bool(finals) and all(r and r["passed"] for r in finals)
    accepted = all(w["status"] == "accepted" for w in state["work_items"].values())
    return {
        "episode_id": state["branch_id"],
        "instance_id": state["instance_id"],
        "lineage_id": state["project"]["lineage_id"],
        "project": state["project"],
        "call_ids": [c["call_id"] for c in state["calls"]],
        "action_ids": [a["action_id"] for a in state["interactions"]],
        "policy_versions": sorted(
            {c.get("policy_version", c["model_requested"]) for c in state["calls"]}
        ),
        "work_items": state["work_items"],
        "evaluations": state["evaluations"],
        "artifact_valid": valid,
        "business_accepted": accepted,
        "explanation_assessed": False,
        "trajectory_supervision_status": "outcome_conditioned_candidate"
        if valid and accepted
        else "not_verified",
        "professional_gold": False,
    }
