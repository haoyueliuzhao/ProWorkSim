"""Necessary no-archive counterexamples for original source/stop binding."""

import copy

import pytest

from proworksim import software_benchmark_stopped_recovery_v122 as recovery


def original_values():
    folder = recovery.BATCH / "episodes/8524"
    row = next(
        row
        for row in recovery.load(recovery.reference(recovery.BATCH / "execution-plan.json"))["rows"]
        if row["slot_index"] == 8524
    )
    result = recovery.load(recovery.reference(folder / "result.json"))
    return [
        row,
        result,
        recovery.load(result["final_writer_quiescence"]),
        recovery.load(result["quiescence"]),
        recovery.load(result["failure_controller_output_transfer"]),
        recovery.load(result["interrupted_worktree"]),
        recovery.load(recovery.reference(folder / "baseline-snapshot-provenance.json")),
    ]


def test_original_stopped_controller_source_is_required_and_actor_cannot_substitute():
    values = original_values()
    recovery.validate_original(*values)
    for changed in (
        "actor_instead_of_controller",
        "different_claim",
        "still_running",
        "changed_original_endpoint",
    ):
        bad = copy.deepcopy(values)
        if changed == "actor_instead_of_controller":
            bad[4]["transfer"]["role"] = "actor"
        elif changed == "different_claim":
            bad[4]["transfer"]["container_claim"] = {"wrong": "claim"}
        elif changed == "still_running":
            bad[2]["writers"][0]["state"]["Running"] = True
        else:
            bad[5]["official_final_candidate"] = True
        with pytest.raises(ValueError):
            recovery.validate_original(*bad)


def test_current_version_must_be_committed_and_unique_no_highest_or_orphan_fallback():
    def artifact(alias, filename):
        return {
            "alias": alias,
            "filename": filename,
            "project_id": "SOFTWARE27",
            "artifact_id": "object-" + alias,
            "kind": "json",
            "current_version": "v1",
            "versions": {"v1": {"sha256": "a" * 64}},
        }

    state = {
        "runtime_kind": "world_core",
        "state_revision": 0,
        "operation_commits": {},
        "artifacts": {
            "base": artifact("baseline", "baseline.json"),
            "member": artifact("member_001", "member_001.json"),
        },
    }
    chosen = recovery.artifact_paths(state)
    assert chosen["member_001"][1].endswith("/v1/member_001.json")
    state["artifacts"]["member"]["current_version"] = "v2"
    with pytest.raises(ValueError):
        recovery.artifact_paths(state)
