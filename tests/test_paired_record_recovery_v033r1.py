"""Only v0.33-r1 changed paths: retained-prefix exclusion and derivation guards."""
import copy

import pytest

from proworksim import software_runtime_v033 as runtime
from proworksim.storage import read_json
from scripts.recover_paired_records_v033r1 import recover_records, validate_derivation
from test_software_v033 import ScriptedCPUOwner


def test_resume_executes_only_six_original_suffix_slots_with_four_initial_pair_proofs(tmp_path):
    pytest.importorskip("openhands.sdk")
    owner = ScriptedCPUOwner(tmp_path / "projection")
    inventory = runtime.inventory()
    completed = [row["slot_id"] for row in inventory[:2]]
    boundaries = []
    entries = runtime.collect_software_window(owner.facade, runtime.window_spec(owner.window_id), tmp_path / "window",
        completed_slot_ids=completed, on_slot=lambda event, row, folder: boundaries.append((event, row["slot_id"])))
    suffix = inventory[2:]
    assert [entry["slot_id"] for entry in entries] == [row["slot_id"] for row in suffix]
    assert owner.seeds == [(row["sampling_seed"], row["slot_id"]) for row in suffix]
    assert len(owner.requests) == 9
    assert boundaries == [(event, row["slot_id"]) for row in suffix for event in ("started", "closed")]
    assert len(read_json(tmp_path / "window/initial-pair-proofs.json")) == 4
    declaration = read_json(tmp_path / "window/declaration.json")
    assert [row["slot_id"] for row in declaration["slots"]] == [row["slot_id"] for row in suffix]
    assert declaration["gamma_identity"]["budget"] == {"max_slots": 6, "max_model_calls": 768}
    assert [row["slot_id"] for row in read_json(tmp_path / "window/progress.json")] == [row["slot_id"] for row in suffix]
    for index in range(8):
        slot = tmp_path / f"window/slot-{index}"
        assert (slot / "preparation.json").exists()
        assert (slot / "episode").exists() is (index >= 2)
        assert (slot / "entry.json").exists() is (index >= 2)
        if index < 2:
            assert not (slot / "experience.jsonl").exists()
    continuation = read_json(tmp_path / "window/continuation.json")
    assert continuation["new_episode_count"] == 6
    assert continuation["validation_only_prebuilt_slot_ids"] == completed
    assert read_json(tmp_path / "window/summary.json")["retained_completed_slot_ids"] == completed


def test_resume_rejects_partial_reordered_or_later_prefix_before_owner_or_output(tmp_path):
    rows = runtime.inventory()
    first, second = (row["slot_id"] for row in rows[:2])
    assert runtime.validate_completed_slot_ids(()) == ()
    assert runtime.validate_completed_slot_ids([first, second]) == (first, second)
    for invalid in ([first], [second, first], [first, second, rows[2]["slot_id"]], [rows[2]["slot_id"], rows[3]["slot_id"]]):
        with pytest.raises(ValueError, match="completed two-slot prefix"):
            runtime.collect_software_window(object(), runtime.window_spec("cpu-rejected"), tmp_path / "uncreated",
                                             completed_slot_ids=invalid)
        with pytest.raises(ValueError, match="completed two-slot prefix"):
            runtime.collect(object(), runtime.window_spec("cpu-rejected"), tmp_path / "uncreated", tmp_path / "worker",
                            completed_slot_ids=invalid)
    assert not (tmp_path / "uncreated").exists()


def test_recovery_guard_preserves_every_actual_record_reward_and_other_dimension():
    original = {"slot_id": "paired-0-ledger-T", "reward": {"eligible": True, "reward": 0},
                "rollout": {"events": [{"original": "synthetic CPU fixture"}], "work_validity": {
                    "components": {name: {"value": value, "checks": [{"evidence": "original"}]}
                                   for name, value in (("record", None), ("permission", True), ("basis", True), ("delivery", False))}}}}
    derived = copy.deepcopy(original)
    derived["rollout"]["work_validity"]["components"]["record"] = {"value": True, "checks": [{"evidence": "strict non-generation proof"}]}
    assert validate_derivation(original, derived, "T")["record"] == {"original": None, "derived": True}
    changed = copy.deepcopy(derived)
    changed["reward"]["reward"] = 1
    with pytest.raises(ValueError, match="only the derived work-validity"):
        validate_derivation(original, changed, "T")
    changed = copy.deepcopy(derived)
    changed["rollout"]["events"].append({"fabricated_response": "never allowed"})
    with pytest.raises(ValueError, match="only the derived work-validity"):
        validate_derivation(original, changed, "T")
    changed = copy.deepcopy(derived)
    changed["rollout"]["work_validity"]["components"]["permission"]["value"] = False
    with pytest.raises(ValueError, match="permission evidence"):
        validate_derivation(original, changed, "T")
    valid_single = copy.deepcopy(derived)
    assert validate_derivation(valid_single, valid_single, "S")["record"] == {"original": True, "derived": True}
    with pytest.raises(ValueError, match="original S record"):
        changed = copy.deepcopy(valid_single)
        changed["rollout"]["work_validity"]["components"]["record"]["checks"] = []
        validate_derivation(valid_single, changed, "S")


def test_recovery_never_writes_inside_original_or_overwrites_output(tmp_path):
    source = tmp_path / "original"
    source.mkdir()
    for output in (source, source / "derived", tmp_path):
        with pytest.raises(ValueError, match="separate new directory"):
            recover_records(source, output)
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="Never overwrite"):
        recover_records(source, existing)
    assert list(source.iterdir()) == []
