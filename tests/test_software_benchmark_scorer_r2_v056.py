"""Transport repair must preserve the scored candidate and isolate prior results."""
import os

import pytest

from proworksim import software_benchmark_scorer_r2_v056 as scorer
from proworksim.software_benchmark_candidates_v054 import write_new


def repair_request(tmp_path, monkeypatch):
    cpus = ",".join(map(str, sorted(os.sched_getaffinity(0))[:4]))
    original = {
        "patch": {"original": "immutable"}, "native_candidate_lock": {"lock": "original"},
        "candidate_tree_sha256": "a" * 64, "baseline_tree_sha256": "b" * 64,
        "condition_id": "REF_B5000K", "slot_id": "fixed-slot", "actor_feedback": False,
        "scoring_cpuset_cpus": cpus, "scorer_manifest": {},
        "trusted_output_root": "old-root", "receipt_output": "old-receipt",
        "quiescence_output": "old-quiescence",
    }
    source = write_new(tmp_path / "original.json", original)
    manifest = {"new_scorer": True}
    frozen = write_new(tmp_path / "manifest.json", manifest)
    seen = []
    monkeypatch.setattr(scorer.predecessor, "validate_request", lambda value: seen.append(value))
    monkeypatch.setattr(scorer, "installation_manifest", lambda: manifest)

    def validate(lock, receipt):
        assert lock == original["native_candidate_lock"]
        assert receipt == {"transport": "new-representation"}
        return {key: original[key] for key in ("candidate_tree_sha256", "baseline_tree_sha256")} | {
            "original_patch": original["patch"], "base_tree_sha256": original["baseline_tree_sha256"]}

    monkeypatch.setattr(scorer.transport, "validate_transport", validate)
    request = original | {
        "scorer_manifest": frozen, "scoring_recovery_of": source,
        "patch_transport": {"transport": "new-representation"},
        "trusted_output_root": "new-root", "receipt_output": "new-receipt",
        "quiescence_output": "new-quiescence",
    }
    return request, original, seen


def test_recovery_validates_original_candidate_and_rejects_condition_or_patch_changes(tmp_path, monkeypatch):
    request, original, seen = repair_request(tmp_path, monkeypatch)
    scorer.validate_request(request)
    assert seen == [original]
    for field, replacement in (("patch", {"replacement": True}),
                               ("condition_id", "REF_B10000K"), ("actor_feedback", True)):
        with pytest.raises(ValueError, match="only scorer transport"):
            scorer.validate_request(request | {field: replacement})


def test_recovery_rejects_prior_output_reuse_and_wrong_tree(tmp_path, monkeypatch):
    request, original, _ = repair_request(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="preserve the original"):
        scorer.validate_request(request | {"receipt_output": original["receipt_output"]})
    monkeypatch.setattr(scorer.transport, "validate_transport", lambda *_: {
        "original_patch": original["patch"], "candidate_tree_sha256": "c" * 64,
        "base_tree_sha256": original["baseline_tree_sha256"],
    })
    with pytest.raises(ValueError, match="locked scoring candidate"):
        scorer.validate_request(request)
