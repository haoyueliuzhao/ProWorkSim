import copy
import importlib.util
from pathlib import Path

import pytest

from proworksim.software_benchmark_candidates_v054 import write_new

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "dead_cursor_test", ROOT / "tools/assemble_dead_api_cursor_v081.py"
)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def row(slot, index):
    return {
        "slot_id": slot,
        "slot_index": index,
        "model_key": "DEEPSEEK",
        "input_plus_output_tokens": 5_000_000,
    }


def cursor():
    return {
        "generation": {"done": {"status": "closed", "result": {"immutable": "original"}}},
        "scores": {"done": {"resolved": True}},
        "deliveries": {},
        "active_generation": ["orphan"],
        "active_grading": [{"old_score": True}],
        "pending_scores": [],
        "pending_controls": [],
    }


def test_original_terminal_history_is_preserved_and_orphans_accounted(tmp_path, monkeypatch):
    before = cursor()
    saved = copy.deepcopy(before)
    monkeypatch.setattr(recovery.original, "BATCH_ROOT", tmp_path)
    rows = [row("done", 1), row("orphan", 2), row("scheduled_only", 3), row("unused", 4)]
    after = recovery.build_cursor(
        before,
        {"orphan": {"status": "technical_unknown", "result": None}},
        {},
        consumed={"orphan"},
        scheduled={"orphan", "scheduled_only"},
        requested={"orphan"},
        rows=rows,
        evidence={"audit": "new"},
    )
    assert before == saved
    assert after["generation"]["done"] == saved["generation"]["done"]
    assert after["scores"] == saved["scores"]
    assert not after["active_generation"] and not after["active_grading"]
    assert after["generation"]["scheduled_only"]["entered"] is False
    assert "unused" not in after["generation"]


def test_conflicting_original_generation_is_never_replaced():
    with pytest.raises(ValueError, match="cannot replace"):
        recovery.build_cursor(
            cursor(),
            {"done": {"status": "technical_unknown"}},
            {},
            consumed=set(),
            scheduled=set(),
            requested=set(),
            rows=[row("done", 1), row("orphan", 2)],
            evidence={},
        )


def test_consumed_scoring_identity_is_not_requeued(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery.original, "BATCH_ROOT", tmp_path)
    claims = tmp_path / "resource-claims"
    claims.mkdir()
    (claims / "score-2.json").write_text("{}")
    before = cursor()
    r = row("orphan", 2)
    before["pending_scores"] = [["code", r, {"request": "old"}, True]]
    after = recovery.build_cursor(
        before,
        {"orphan": {"status": "technical_unknown"}},
        {},
        consumed={"orphan"},
        scheduled=set(),
        requested=set(),
        rows=[row("done", 1), r],
        evidence={},
    )
    assert after["pending_scores"] == []
    assert after["scores"]["orphan"]["status"] == "technical_unknown"
    assert after["scores"]["orphan"]["automatic_replay"] is False


def test_unsettled_usage_is_not_claimed_zero_or_completed(tmp_path):
    r = {**row("orphan", 2), "instance_id": "task", "configuration": {"original": "config"}}
    usage = {
        "settled_request_count": 0,
        "known_actual_tokens_lower_bound": 0,
        "unknown_or_reserved_request_ids": ["one"],
    }
    evidence = write_new(
        tmp_path / "evidence.json",
        {"row": r, "usage_observation": usage, "original_results_modified": False},
    )
    receipt = {
        "slot_id": "orphan",
        "slot_index": 2,
        "quiescent": True,
        "cleanup_errors": [],
        "foreign_objects_modified": False,
        "new_model_calls": 0,
        "replayed_episodes": 0,
        "evidence": evidence,
        "original_result": None,
        "retained_objects": [{"role": "actor"}],
        "export_pending": True,
    }
    result = recovery.generation_entry(
        r, {"receipt": "new"}, receipt, claim_exists=True, request_exists=True
    )
    assert (
        result["status"] == "technical_unknown" and result["actual_model_generation_known"] is None
    )
    assert result["recovered_usage_observation"]["unknown_or_reserved_request_ids"] == ["one"]
    assert result["retained_objects"] == [{"role": "actor"}]
