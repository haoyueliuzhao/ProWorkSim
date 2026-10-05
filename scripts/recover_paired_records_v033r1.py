#!/usr/bin/env python3
"""Re-export four sealed v0.33 episodes without executing a world or a model.

Original records, assessments and execution-error history remain byte-for-byte
unchanged. Only the derived record interpretation uses the repaired member view.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proworksim.audit import code_identity  # noqa: E402
from proworksim.software_runtime_v033 import inventory, validate_completed_slot_ids  # noqa: E402
from proworksim.software_training_v033 import export_software_episode  # noqa: E402
from proworksim.storage import atomic_write, digest, json_bytes, read_json  # noqa: E402

VERSION = "paired-record-recovery-v0.33r1"
CANDIDATES = ("qwen3.5-9b", "devstral-small-2507")
GUARD_FIELDS = ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged")
IMPLEMENTATION = ("scripts/recover_paired_records_v033r1.py", "src/proworksim/member_views.py",
    "src/proworksim/team_validity.py", "src/proworksim/team_rollout.py", "src/proworksim/episode.py",
    "src/proworksim/software_runtime_v033.py", "src/proworksim/software_training_v033.py",
    "src/proworksim/software_collaboration_v033.py", "src/proworksim/online_support.py")


def reference(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "sha256": sha}


def tree_manifest(root):
    """Bind every old artifact, including raw requests and idle unused worlds."""
    return {str(path.relative_to(root)): {**reference(path), "bytes": path.stat().st_size}
            for path in sorted(root.rglob("*")) if path.is_file()}


def write(path, value):
    atomic_write(path, json_bytes(value))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_derivation(original, derived, condition):
    """No fixed reward, actual record or other validity dimension may change."""
    expected = copy.deepcopy(original)
    expected["rollout"]["work_validity"] = derived["rollout"]["work_validity"]
    require(expected == derived, "Recovery may change only the derived work-validity interpretation")
    old = original["rollout"]["work_validity"]["components"]
    new = derived["rollout"]["work_validity"]["components"]
    for dimension in ("permission", "basis", "delivery"):
        require(old[dimension] == new[dimension], f"Recovery changed original {dimension} evidence")
    require(new["record"]["value"] is True, "Repaired interpretation still has missing or conflicting records")
    require(old["record"]["value"] is (True if condition == "S" else None), "Unexpected original record status")
    if condition == "S":
        require(original == derived, "The original S record must remain identical")
    return {dimension: {"original": old[dimension]["value"], "derived": new[dimension]["value"]}
            for dimension in ("record", "permission", "basis", "delivery")}


def recover_records(source_root, output_root):
    source, output = Path(source_root).resolve(), Path(output_root).resolve()
    require(source.is_dir() and source != output and source not in output.parents
            and output not in source.parents, "Recovery output must be a separate new directory")
    require(not output.exists(), "Never overwrite a previous record-recovery artifact")
    plan, supervisor = read_json(source / "plan.json"), read_json(source / "supervisor.json")
    require(plan["version"] == "paired-o1-diagnostic-v0.33" and tuple(plan["candidates"]) == CANDIDATES,
            "Recovery is restricted to the two original v0.33 candidates")
    require(supervisor["status"] == "ended_with_execution_stop", "Original supervisor is not frozen at its execution stop")
    prefix = inventory()[:2]
    completed = list(validate_completed_slot_ids(row["slot_id"] for row in prefix))
    source_before = tree_manifest(source)
    source_refs = {"plan": reference(source / "plan.json"), "supervisor": reference(source / "supervisor.json"), "candidates": {}}
    output.mkdir(parents=True, exist_ok=False)
    write(output / "source-artifacts.json", {"version": VERSION, "files": source_before,
          "tree_sha256": digest(json_bytes(source_before))})
    result = {"version": VERSION, "status": "recovering", "passed": False,
              "source_root": str(source), "source_refs": source_refs,
              "source_artifacts": reference(output / "source-artifacts.json"),
              "source_identity": code_identity(), "model_calls": 0, "optimizer_steps": 0,
              "acceptance_executions": 0, "new_episodes": 0, "old_artifacts_unchanged": False,
              "interpreter": {"executable": str(Path(sys.executable).resolve()), "version": sys.version,
                              "binary": reference(Path(sys.executable).resolve())},
              "implementation_files": {name: reference(ROOT / name) for name in IMPLEMENTATION},
              "candidates": {}, "scope": "Derived record interpretation only; original execution errors and assessments are retained. No old episode is rerun and no response or token is fabricated."}
    for candidate in CANDIDATES:
        base = source / candidate
        diagnostics = base / "actual/diagnostics"
        state, report = read_json(base / "state.json"), read_json(base / "actual/report.json")
        progress, declaration = read_json(diagnostics / "progress.json"), read_json(diagnostics / "declaration.json")
        require(state["status"] == "stopped" and state["exit_code"] == 1 and report["status"] == "execution_error", "Original worker status differs")
        require([row["slot_id"] for row in progress] == completed, "Original run has a different completed prefix")
        require(report["source_before"] == report["source_after"] and report["source_before"]["code_dirty"] is False,
                "Original frozen source identity changed")
        common = read_json(diagnostics / "common-restore.json")
        require(common["common_restored_exactly"] is True and common["optimizer_updates"] == 0,
                "Original worker did not restore its common exactly")
        checkpoint = Path(common["checkpoint"])
        if not checkpoint.is_absolute():
            checkpoint = ROOT / checkpoint
        checkpoint_value = read_json(checkpoint)
        require(common["actor_identity"] == checkpoint_value["actor_identity"] == declaration["actor_identity"],
                "Original common identity differs from the sealed declaration")
        require(all(read_json(diagnostics / "evaluation-guard.json")[key] is True for key in GUARD_FIELDS),
                "Original global evaluation guard failed")
        refs = {name: reference(path) for name, path in {
            "state": base / "state.json", "worker": base / "worker.log", "report": base / "actual/report.json",
            "progress": diagnostics / "progress.json", "declaration": diagnostics / "declaration.json",
            "evaluation_guard": diagnostics / "evaluation-guard.json", "common_restore": diagnostics / "common-restore.json",
            "original_common_checkpoint": checkpoint}.items()}
        source_refs["candidates"][candidate] = refs
        derived_candidate = {"status": "recovered", "completed_slot_ids": completed, "rows": [],
                             "source_refs": refs, "original_status": report["status"],
                             "original_source_identity": report["source_before"], "model_calls": 0, "optimizer_steps": 0}
        result["candidates"][candidate] = derived_candidate
        for index, (row, original_progress) in enumerate(zip(prefix, progress, strict=True)):
            folder, target = diagnostics / f"slot-{index}", output / candidate / f"slot-{index}"
            original, assessment = read_json(folder / "entry.json"), read_json(folder / "assessment.json")
            manifest = read_json(folder / "episode/manifest.json")
            boundary = manifest["termination"]
            require(manifest["status"] == "closed" and boundary.get("execution_integrity_failure") is None,
                    "An interrupted or integrity-failed episode cannot be recovered")
            require(assessment["status"] == "evaluable" and original["reward"]["eligible"] is True,
                    "Recovery cannot replace an unknown original assessment")
            require(all(read_json(folder / "evaluation-guard.json")[key] is True for key in GUARD_FIELDS),
                    "Original slot evaluation guard failed")
            if row["condition"] == "T":
                require(original_progress["status"] == "execution_unknown" and
                        original_progress.get("error", {}).get("episode_closed_before_error") is True and
                        boundary["status"] == "bounded_work_closed" and
                        set(boundary["role_stops"].values()) == {"team_budget_exhausted"},
                        "T recovery requires the known post-closure record-interpretation error")
            scenario = read_json(folder / "model-scenario.json")
            case = scenario["variation"]["software_case"]
            prepared = SimpleNamespace(case=case, scenario=scenario, prefix=read_json(folder / "preparation.json"),
                reward_spec=original["reward"]["spec"], active_roles=case["active_roles"])
            derived, evidence = export_software_episode(prepared, folder / "episode", assessment,
                declaration=declaration, slot_id=row["slot_id"], captured=read_json(folder / "public-capture.json"))
            dimensions = validate_derivation(original, derived, row["condition"])
            exclusions = {member: [{"call_id": decision["call_id"], "generation_status": decision["generation_status"],
                                   "actor_required": decision["actor_required"], "proof": decision["non_generation_evidence"]}
                                  for decision in view["decisions"]
                                  if decision["generation_status"] == "not_started_shared_admission_rejection"]
                          for member, view in evidence["member_views"].items()}
            require(all(len(value) == (1 if row["condition"] == "T" else 0) for value in exclusions.values()),
                    "Recovery did not identify exactly the original terminal admission rejections")
            write(target / "entry.json", derived)
            write(target / "software-evidence.json", evidence)
            per_episode_refs = {name: reference(path) for name, path in {
                "entry": folder / "entry.json", "software_evidence": folder / "software-evidence.json",
                "assessment": folder / "assessment.json", "raw_assessment": folder / "raw-independent-assessment.json",
                "manifest": folder / "episode/manifest.json", "experience": folder / "episode/experience.json",
                "public_capture": folder / "public-capture.json", "evaluation_guard": folder / "evaluation-guard.json",
                "team_budget": folder / "team-budget.json", "scenario": folder / "model-scenario.json",
                "preparation": folder / "preparation.json"}.items()}
            recovery = {"version": VERSION, "slot_id": row["slot_id"], "source_refs": per_episode_refs,
                "derived_entry": reference(target / "entry.json"), "derived_evidence": reference(target / "software-evidence.json"),
                "validity_dimensions": dimensions, "excluded_non_generations": exclusions,
                "original_progress_status": original_progress["status"], "original_execution_error": original_progress.get("error"),
                "original_reward": original["reward"], "assessment_reexecuted": False,
                "same_fixed_assessment": {key: assessment.get(key) for key in
                    ("R", "content_correct", "required_process_satisfied", "submitted", "complete_delivery")},
                "model_calls": 0, "optimizer_steps": 0, "actual_events_tokens_and_rewards_unchanged": True}
            write(target / "recovery.json", recovery)
            derived_candidate["rows"].append({**row, "status": "closed", "record_validity": True,
                **recovery["same_fixed_assessment"], "training_eligible": False,
                "source_original_status": original_progress["status"], "source_execution_error": original_progress.get("error"),
                "entry": recovery["derived_entry"], "assessment": per_episode_refs["assessment"],
                "evaluation_guard": per_episode_refs["evaluation_guard"], "record_recovery": reference(target / "recovery.json")})
    require(tree_manifest(source) == source_before, "An original artifact changed during offline interpretation")
    require(all(reference(ROOT / name) == value for name, value in result["implementation_files"].items()),
            "Record interpretation source changed during recovery")
    result.update(status="recovered", passed=True, old_artifacts_unchanged=True,
                  original_tree_sha256=digest(json_bytes(source_before)))
    write(output / "summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = recover_records(args.source_root, args.output)
    print(json.dumps({key: result[key] for key in ("version", "status", "passed", "model_calls", "optimizer_steps", "old_artifacts_unchanged")}))


if __name__ == "__main__":
    main()
