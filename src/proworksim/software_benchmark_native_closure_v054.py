"""Bind existing lossless candidate exporters to the host quiescence boundary."""
from __future__ import annotations

from pathlib import Path

from .repository_sources_v054 import capture_repository
from .software_benchmark_candidates_v054 import (
    checked, export_git_patch, lock_episode_candidates, reference, write_new,
)
from .storage import read_json

VERSION = "software-benchmark-native-closure-v054"


def lock_native_candidate(episode, *, baseline_reference, public_worktree,
                          public_task, dataset_revision, output, file_policy=None):
    if episode.slot["arm"] not in {"REF", "MATCH"}:
        raise ValueError("PROJECT uses its existing dual endpoint lock")
    if public_task["instance_id"] != episode.slot["instance_id"]:
        raise ValueError("Candidate source task differs from the claimed slot")
    with episode.candidate_boundary() as quiescence:
        root = Path(output)
        root.mkdir(parents=True, exist_ok=False)
        baseline = read_json(checked(baseline_reference))
        manifest = capture_repository(
            public_worktree, root / "terminal-snapshot",
            task_id=public_task["instance_id"], problem_statement=public_task["problem_statement"],
            source_identity={
                **{key: public_task[key] for key in ("instance_id", "repo", "base_commit")},
                "dataset_revision": dataset_revision,
            }, file_policy=file_policy)
        candidate_path = manifest.parent / "initial-tree.json"
        candidate = read_json(candidate_path)
        patch = export_git_patch(
            baseline, candidate, root / "candidate.patch", policy=file_policy)
        result = write_new(root / "lock.json", {
            "version": VERSION, "claim_id": episode.claim_id, "slot": episode.slot,
            "endpoint": "terminal_code", "quiescence": quiescence,
            "baseline": baseline_reference, "candidate": reference(candidate_path),
            "source_manifest": reference(manifest), "patch_receipt": patch,
            "tree_sha256": patch["candidate_tree_sha256"], "delivery": None,
            "lock_before_grading": True, "model_calls": 0, "grading_calls": 0,
        })
        write_new(episode.root / "candidate-result.json", {"lock": result})
        return result


def lock_project_candidates(episode, prepared, *, output):
    if episode.slot["arm"] != "PROJECT" or prepared.case["case_id"] != episode.slot["instance_id"]:
        raise ValueError("Wrong managed task or arm")
    with episode.candidate_boundary() as quiescence:
        result = lock_episode_candidates(prepared, run_root=output)
        write_new(episode.root / "candidate-result.json", {
            "lock": result, "quiescence": quiescence,
            "original_project_delivery_semantics_unchanged": True,
        })
        return result
