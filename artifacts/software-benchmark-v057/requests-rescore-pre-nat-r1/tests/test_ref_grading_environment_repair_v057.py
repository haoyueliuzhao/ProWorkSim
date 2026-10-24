"""Environment rescoring preserves candidates and never promotes missing outcomes."""
import copy
import importlib.util
import os
from pathlib import Path

import pytest

from proworksim import software_benchmark_scorer_v057 as scorer
from proworksim.software_benchmark_candidates_v054 import write_new

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("requests_rescore_v057", ROOT / "tools/repair_ref_grading_environment_v057.py")
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def fixture():
    rows, outcomes = [], []
    for index in range(16):
        slot = f"fixed-slot-{index}"
        task, condition = f"requests-{index // 4}", f"budget-{index % 4}"
        old, patch, native = {"old_request": slot}, {"patch": slot}, {"lock": slot}
        request, env, qual = {"new_request": slot}, {"environment": "one"}, {"qualification": "all-eight-passed"}
        rows.append({"slot": {"slot_id": slot, "instance_id": task, "condition_id": condition},
            "generation": {"status": "closed", "immutable_result": slot},
            "score": {"status": "official_report", "resolved": False,
                      "dispatched_request": old, "receipt": {"old_receipt": slot}}})
        receipt = {"slot_id": slot, "condition_id": condition, "scoring_recovery_of": old,
            "original_patch": patch, "native_candidate_lock": native,
            "environment_revision": env, "environment_qualification": qual,
            "status": "official_report", "resolved": index == 0,
            "model_calls": 0, "actor_feedback": False, "candidate_changed": False,
            "version": scorer.VERSION}
        outcomes.append({"slot_id": slot, "instance_id": task, "condition_id": condition,
            "known": True, "original_request": old, "request": request,
            "original_patch": patch, "native_candidate_lock": native,
            "environment_revision": env, "environment_qualification": qual,
            "receipt": receipt, "receipt_pointer": {"new_receipt": slot},
            "quiescence_reference": {"quiet": slot}, "completion": {"completed": slot},
            "quiescence": {"slot_id": slot, "condition_id": condition,
                           "quiescent": True, "cleanup_errors": [], "create_result_unknown": False}})
    state = {"rows": rows, "complete": True, "binding": "unchanged", "deferred": ["historical-unknown"]}
    return state, {row["slot"]["slot_id"] for row in rows}, outcomes


def test_known_rescore_preserves_every_generation_and_old_score():
    state, allowed, outcomes = fixture()
    saved = copy.deepcopy(state)
    value, changed, pending = repair.reconciled_state(state, copy.deepcopy(state), allowed, outcomes)
    assert state == saved and len(changed) == 16 and not pending
    assert sum(row["score"]["resolved"] for row in value["rows"]) == 1
    for before, after in zip(state["rows"], value["rows"], strict=True):
        assert after["generation"] == before["generation"] and after["slot"] == before["slot"]
        assert after["prior_scoring_attempts"] == [before["score"]]
    assert value["deferred"] == state["deferred"] and value["binding"] == state["binding"]


def test_uncertain_new_scoring_keeps_old_determinate_score_and_marks_review():
    state, allowed, outcomes = fixture()
    outcomes[0]["receipt"].update(status="technical_unknown", resolved=None)
    value, changed, pending = repair.reconciled_state(state, copy.deepcopy(state), allowed, outcomes)
    assert len(changed) == 15 and pending == ["fixed-slot-0"]
    assert value["rows"][0]["score"] == state["rows"][0]["score"]
    assert value["rows"][0]["environment_review"]["old_score_not_confirmed_in_repaired_environment"] is True
    assert not any(row["score"]["resolved"] for row in value["rows"])


def test_wrong_candidate_or_condition_and_missing_panel_are_rejected():
    state, allowed, outcomes = fixture()
    for field, wrong in (("native_candidate_lock", {"another": "candidate"}), ("condition_id", "another-budget")):
        altered = copy.deepcopy(outcomes)
        altered[0]["receipt"][field] = wrong
        with pytest.raises(ValueError, match="Receipt does not bind"):
            repair.reconciled_state(state, copy.deepcopy(state), allowed, altered)
    with pytest.raises(ValueError, match="Every one"):
        repair.reconciled_state(state, copy.deepcopy(state), allowed, outcomes[:-1])


def test_scorer_preserves_original_candidate_and_requires_same_qualified_environment(tmp_path, monkeypatch):
    cpus = ",".join(map(str, sorted(os.sched_getaffinity(0))[:4]))
    old = {"instance_id": "psf__requests-2931", "patch": {"old_patch": True},
        "native_candidate_lock": {"old_lock": True}, "scorer_manifest": {},
        "trusted_output_root": "old-root", "receipt_output": "old-receipt",
        "quiescence_output": "old-quiet", "scoring_cpuset_cpus": cpus,
        "slot_id": "fixed", "condition_id": "REF_B5000K", "actor_feedback": False}
    manifest = {"new_manifest": True}
    request = old | {"scoring_recovery_of": write_new(tmp_path / "old.json", old),
        "scorer_manifest": write_new(tmp_path / "manifest.json", manifest),
        "trusted_output_root": "new-root", "receipt_output": "new-receipt",
        "quiescence_output": "new-quiet", "environment_revision": {"env": "qualified"},
        "environment_qualification": {"qual": "all-eight"}}
    seen = []
    monkeypatch.setattr(scorer.predecessor, "validate_request", lambda original: seen.append(original))
    monkeypatch.setattr(scorer, "installation_manifest", lambda: manifest)
    monkeypatch.setattr(scorer.qualification, "validate_qualification", lambda *_: {
        "environment_revision": {"env": "qualified"}})
    scorer.validate_request(request)
    assert seen == [old]
    with pytest.raises(ValueError, match="only the qualified"):
        scorer.validate_request(request | {"patch": {"different": True}})
    with pytest.raises(ValueError, match="complete control qualification"):
        scorer.validate_request(request | {"environment_revision": {"env": "unqualified"}})
