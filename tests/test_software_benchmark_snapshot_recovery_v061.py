"""Recovery must use a preselected, quiescent terminal tree and exact blob bytes."""
import copy

import pytest

from proworksim import software_benchmark_snapshot_recovery_v061 as recovery
from proworksim.software_benchmark_native_artifact_v054 import snapshot_native_candidate


def evidence():
    slot = {"slot_id": recovery.SLOT_ID, "slot_index": 163, "instance_id": recovery.TASK,
            "arm": "REF", "condition_id": "REF_B5000K", "seed": 20261024056040}
    config = {"slot_id": recovery.SLOT_ID, "condition_id": "REF_B5000K", "configuration": {"sha256": "fixed"},
              "public_task": {"instance_id": recovery.TASK, "repo": "scikit-learn/scikit-learn",
                              "base_commit": "original", "problem_statement": "public task"},
              "dataset_revision": "fixed-test-revision"}
    refs = {"quiescence": {"sha256": "original-quiet"}, "baseline": {"sha256": "b", "bytes": 10},
            "terminal": {"sha256": "t", "bytes": 12}}
    values = {
        "claim": {"slot": slot, "claim_id": "original", "configuration": config["configuration"]},
        "original_config": config,
        "controller": {"slot_id": recovery.SLOT_ID, "condition_id": "REF_B5000K", "status": "closed",
                       "normal_completion": True, "native_finished": True,
                       "hidden_feedback_received": False, "preparation_only": False},
        "sdk_terminal": {"execution_status": "finished"},
        "dispatch_closed": {"claim_id": "original", "reason": "ref_budget_controller_returned"},
        "quiescence": {"claim_id": "original", "all_quiet": True, "errors": [],
                       "scopes": [{"unit": role, "role": role, "claim_id": "original"}
                                  for role in ("actor", "controller")],
                       "stopped": [{"unit": role, "populated": False, "registered_main_exited": True,
                                    "active_state": "inactive"} for role in ("actor", "controller")]},
        "candidate_claim": {"claim_id": "original", "quiescence": refs["quiescence"],
                            "selection_after_scoring": False},
    }
    identity = {k: config["public_task"][k] for k in ("instance_id", "repo", "base_commit")}
    identity["dataset_revision"] = config["dataset_revision"]
    for kind in ("baseline", "terminal"):
        values[kind + "_manifest"] = {"version": recovery.PROTOCOL, "tasks": [{
            "task_id": recovery.TASK, "source_identity": identity, "problem_statement": "public task",
            "initial_tree": {"path": "initial-tree.json", **refs[kind]}}]}
    return values, refs


def test_finished_candidate_preserves_original_slot_and_seed():
    records, refs = evidence()
    assert recovery.validate_history(records, refs) == records["claim"]["slot"]


@pytest.mark.parametrize("section,key,value", [
    ("controller", "status", "technical_unknown"),
    ("sdk_terminal", "execution_status", "running"),
    ("candidate_claim", "selection_after_scoring", True),
    ("candidate_claim", "quiescence", {"sha256": "another"}),
    ("quiescence", "all_quiet", False),
    ("dispatch_closed", "reason", "ref_budget_runner_exception"),
])
def test_incomplete_or_reselected_candidate_is_not_recovered(section, key, value):
    records, refs = evidence()
    records[section][key] = value
    with pytest.raises(ValueError):
        recovery.validate_history(records, refs)


def test_snapshot_source_substitution_and_live_writer_are_rejected():
    records, refs = evidence()
    wrong = copy.deepcopy(records)
    wrong["terminal_manifest"]["tasks"][0]["initial_tree"]["sha256"] = "replaced"
    with pytest.raises(ValueError, match="snapshot bytes"):
        recovery.validate_history(wrong, refs)
    records["quiescence"]["stopped"][0]["populated"] = True
    with pytest.raises(ValueError, match="writers"):
        recovery.validate_history(records, refs)


def test_binary_modes_deletion_and_links_survive_single_export(tmp_path):
    work = tmp_path / "fixture"
    work.mkdir()
    (work / "code.py").write_bytes(b"before\r\n")
    (work / "delete").write_text("gone")
    (work / "run.sh").write_text("exit 0\n")
    (work / "link").symlink_to("code.py")
    before = snapshot_native_candidate(work)
    (work / "code.py").write_bytes(b"after\r\n")
    (work / "delete").unlink()
    (work / "run.sh").chmod(0o755)
    (work / "binary[1].pdf").write_bytes(b"%PDF \xff\xfe no NUL\n")
    (work / "link").unlink()
    (work / "link").symlink_to("/opaque/absolute/target")
    terminal = snapshot_native_candidate(work)
    # The live tree is deliberately changed again; export must ignore it.
    (work / "code.py").write_text("later unselected code")
    patch = tmp_path / "candidate.patch"
    result = recovery.export_utf8_patch(before, terminal, patch)
    text = patch.read_text(encoding="utf-8", errors="strict")
    assert "GIT binary patch" in text and "+after" in text and "later unselected" not in text
    assert result["candidate_tree_sha256"] == terminal["tree"]["tree_sha256"]
    assert result["round_trip_verified"] is True and result["utf8_strict"] is True
    assert result["forced_binary_paths"] == ["binary[1].pdf"]
    assert result["deleted_paths"] == ["delete"]
    assert result["modified_paths"] == ["code.py", "link", "run.sh"]
    assert result["symlink_targets_followed"] is False
