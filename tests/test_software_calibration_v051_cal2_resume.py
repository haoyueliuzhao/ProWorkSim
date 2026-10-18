"""Three pure r2 selection/binding controls; no model, GPU or old test replay."""
import copy
from pathlib import Path

import pytest

from proworksim.storage import read_json
from scripts import software_calibration_v051_cal2 as base
from scripts import software_calibration_v051_cal2_resume as resume


def fixture():
    rows = base.inventory(read_json(Path(__file__).resolve().parents[1] /
        "docs/experiments/software-calibration-v051-repository-inventory.json"))
    states = {row["slot_id"]: {"status": "not_started", "attempts": []} for row in rows}
    for name in resume.EXCLUDED | {resume.ZERO_R}:
        states[name] = {"status": "stopped", "attempts": [{"ended_at": 2, "exit_code": 1 if name == resume.ZERO_R else 0,
            "seconds": 1, "report": {} if name == resume.ZERO_R else {"accounting": {
                "started_generations": 7, "complete_generations": 7}}}]}
    supervisor = {"status": "paused", "ended_at": 2, "states": states}
    audit = {"version": "v051-cal2-R-boltons1-readonly-initial-tree-diagnosis-v1", "read_only_originals": True,
        "initial_document_matches_manifest": True, "frozen_mini_matches_plan": True,
        "source_and_native_worktree_raw_bytes_identical": True, "owner_loaded_raw_release": True,
        "initial_file_count": 112, "observed_file_count": 112, "raw_byte_differences": [],
        "rejection_predicates": {"worktree_path_match": True, "source_initial_map_sha_match": True,
            "read_worktree_map_sha_match": False, "commit_count_one": True, "no_remotes": True},
        "initial_map_sha256": "explicit-CPU-fixture", "origin_initial_map_sha256": "explicit-CPU-fixture",
        "native_generation_prepared": 0, "native_generation_started": 0, "native_generation_complete": 0,
        "native_generation_fault": 0, "actual_model_generation_tokens": 0, "actual_call_files": [],
        "native_episode_files": [], "native_model_ledger_exists": False, "native_trajectory_exists": False,
        "native_evaluation_guard_exists": False,
        "interruption": {"row": next(r for r in rows if r["slot_id"] == resume.ZERO_R),
            "error": {"type": "ValueError", "message": "Native case lacks its exact fresh buggy-only initial worktree binding"}},
        "frozen_read_worktree_differences": [{"path": name, "equal_after_universal_newline_conversion": True}
                                           for name in ("LICENSE", "docs/make.bat")]}
    return rows, supervisor, audit


def test_only_original_fourteen_and_single_unexposed_R_keep_order_seed_and_budget():
    rows, supervisor, audit = fixture()
    before = copy.deepcopy((rows, supervisor, audit))
    selected = resume.select_rows(rows, supervisor, audit)
    assert selected == [row for row in rows if row["slot_id"] not in resume.EXCLUDED]
    assert len(selected) == 15 and selected[0]["slot_id"] == resume.ZERO_R
    assert sum(row["generation_tokens"] for row in selected) == 7500000
    assert sum(row["decisions"] for row in selected) == sum(row["attempts"] for row in selected) == 1920
    assert sum(row["project_public_tests"] or 0 for row in selected) == 288
    assert (rows, supervisor, audit) == before


def test_any_native_preparation_or_trajectory_or_different_fault_forbids_exception():
    rows, supervisor, audit = fixture()
    for key, value in [("native_generation_prepared", 1), ("native_generation_started", 1),
            ("native_generation_complete", 1), ("native_generation_fault", 1),
            ("native_episode_files", ["trajectory.json"]), ("native_trajectory_exists", True),
            ("raw_byte_differences", ["production.py"]), ("initial_document_matches_manifest", False)]:
        changed = copy.deepcopy(audit)
        changed[key] = value
        with pytest.raises(ValueError, match="zero native exposure"):
            resume.select_rows(rows, supervisor, changed)
    changed = copy.deepcopy(supervisor)
    unopened = next(name for name, state in changed["states"].items() if state["status"] == "not_started")
    changed["states"][unopened] = copy.deepcopy(changed["states"][next(iter(resume.EXCLUDED))])
    with pytest.raises(ValueError, match="other entered slot"):
        resume.select_rows(rows, changed, audit)


def test_historical_source_uses_old_snapshot_and_only_worker_module_is_adapted(tmp_path):
    main, snapshot = tmp_path / "main", tmp_path / "original-source"
    name = "src/example.py"
    (main / "src").mkdir(parents=True)
    (snapshot / "src").mkdir(parents=True)
    (main / name).write_text("old_source = True\n")
    (snapshot / name).write_bytes((main / name).read_bytes())
    original = base.ref(main / name)
    (main / name).write_text("corrected_source = True\n")
    old = {"source_root": str(snapshot), "source_files": {name: original["sha256"]}, "evidence": []}
    bound = resume.historical_reference(original, old, repository_root=main)
    assert bound["binding"] == "original_frozen_source_snapshot"
    assert bound["resolved_reference"] == base.ref(snapshot / name)
    wrong = {**original, "sha256": "wrong"}
    with pytest.raises(ValueError, match="original source manifest"):
        resume.historical_reference(wrong, old, repository_root=main)
    original_frozen = base.frozen
    worker, supervisor, proof = resume.algorithm_binding()
    assert worker.__code__ is base.worker.__code__ and worker.__globals__["frozen"] is resume.frozen
    assert supervisor.__globals__["frozen"] is resume.frozen and resume.MODULE in supervisor.__code__.co_consts
    assert proof["AST_constant_replacements"] == 1 and proof["global_rebindings"] == ["VERSION", "frozen"]
    assert base.frozen is original_frozen and base.VERSION != resume.VERSION
