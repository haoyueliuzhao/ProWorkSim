"""Finite source, replay and no-model admission counterexamples."""
from __future__ import annotations

import copy

import pytest

from scripts import software_organization_admission_v048 as admission


class Reader:
    def __init__(self, inventory=None):
        self.inventory = inventory

    def path(self, ref):
        assert ref["sha256"]
        return ref["path"]

    def read(self, ref):
        self.path(ref)
        return self.inventory


def _ref(name):
    return {"path": name, "sha256": "f" * 64}


def _replay():
    target_slots = ["org47-A-r0-P4-B250000"] * 2 + ["org47-A-r2-P4-B250000"] + \
                   ["org47-B-r0-P4-B500000"] * 3 + ["org47-B-r2-P4-B500000"] * 2
    rows = []
    for i in range(21):
        encoded = {"prompt_tokens": 16300, "reserved_output_tokens": 2048,
                   "context_limit": 18432, "fits": True,
                   "input_ids_sha256": "a" * 64, "rendered_prompt_sha256": "b" * 64}
        rows.append({"kind": "hard_context_rejected" if i < 10 else "final_fixed_submit",
                     "slot_id": target_slots[i] if i < 8 else "original-slot-" + str(i),
                     "call_id": "call-" + str(i), "member": "member_001", "stage_id": "stage",
                     "targeted_LA_LB_P4": i < 8, "passed": True,
                     "original_reproduction_checks": {"exact_hash": True},
                     "reference_integrity_checks": {"exact_restoration": True},
                     "gamma0": {"selected": copy.deepcopy(encoded), "protected": copy.deepcopy(encoded)},
                     "gamma1": {"selected": copy.deepcopy(encoded), "protected": copy.deepcopy(encoded)}})
    for row in rows:
        row["historical_source"] = {k: copy.deepcopy(row[k]) for k in
                                    ("kind", "slot_id", "call_id", "member", "stage_id", "targeted_LA_LB_P4")}
        row["historical_source"]["historical_preparation"] = copy.deepcopy(row["gamma0"]["selected"])
    return {"version": admission.REPLAY_VERSION, "passed": True, "source_files": {"old": "sha"},
            "candidate": {"path": "candidate", "sha256": admission.CANDIDATE_SHA},
            "source_inventory": _ref("inventory"), "mechanical_controls": _ref("mechanical"),
            "inventory": dict(admission.EXPECTED_INVENTORY),
            "checks": {name: True for name in admission.REQUIRED_REPLAY_CHECKS}, "rows": rows,
            "new_model_calls": 0, "new_world_actions": 0, "new_tests_or_acceptance_calls": 0,
            "new_gpu_operations": 0, "model_weights_loaded": False}


def _reader(value):
    return Reader({"version": "v048-finite-source-inventory-v1",
                   "requests": [copy.deepcopy(r["historical_source"]) for r in value["rows"]]})


def test_source_reuse_allows_only_isolated_v048_additions():
    original = {"src/old.py": "old"}
    current = {**original, "scripts/new_v048.py": "new"}
    assert admission.source_reuse(original, current)["historical_files_unchanged"]
    with pytest.raises(ValueError, match="historical source"):
        admission.source_reuse(original, {**current, "src/old.py": "changed"})
    with pytest.raises(ValueError, match="isolated"):
        admission.source_reuse(original, {**current, "scripts/new_v049.py": "extra"})


def test_replay_accepts_required_eight_fit_without_requiring_other_two():
    value = _replay()
    for row in value["rows"][8:10]:
        row["gamma1"]["selected"].update(prompt_tokens=18000, fits=False)
        row["gamma1"]["protected"].update(prompt_tokens=18000, fits=False)
    result = admission.validate_replay(value, value["source_files"], _reader(value))
    assert result["passed"] is True


@pytest.mark.parametrize("mutation,reason", [
    (lambda v: v.update(passed=False), "single representation"),
    (lambda v: v["candidate"].update(sha256="other"), "frozen single candidate"),
    (lambda v: v.update(new_model_calls=1), "CPU-only"),
    (lambda v: v["rows"][0]["gamma1"]["selected"].update(prompt_tokens=16385, fits=False), "over capacity"),
    (lambda v: v["rows"][0]["gamma1"]["selected"].update(prompt_tokens=17000, fits=True), "hard-capacity"),
    (lambda v: v["rows"][0]["reference_integrity_checks"].update(exact_restoration=False), "integrity"),
    (lambda v: v["rows"][0].update(slot_id="other-root"), "original 21-source"),
    (lambda v: v["rows"][0]["gamma0"]["selected"].update(input_ids_sha256="wrong"), "Gamma0 selected"),
    (lambda v: v["rows"][0]["historical_source"].update(member="member_002"), "provenance snapshot"),
    (lambda v: v["rows"].__setitem__(1, copy.deepcopy(v["rows"][0])), "duplicate"),
    (lambda v: v["checks"].update(targeted_eight_hard_fit=False), "hard fit"),
])
def test_replay_rejects_target_failure_false_identity_or_unsupported_work(mutation, reason):
    value = _replay()
    reader = _reader(value)
    mutation(value)
    with pytest.raises(ValueError, match=reason):
        admission.validate_replay(value, {"old": "sha"}, reader)


def test_controls_require_all_affected_receipts_and_exact_source():
    value = {"version": admission.CPU_VERSION, "passed": True,
             "source_files": {"old": "sha"}, "source_unchanged_during_controls": True,
             "new_model_calls": 0, "new_backward_calls": 0, "model_weights_loaded": False,
             "controls": {name: {"passed": True} for name in admission.REQUIRED_CONTROLS},
             "ruff": {"returncode": 0}, "pytest": {"tests": 1},
             "artifact_refs": [_ref("tests")]}
    assert admission.validate_cpu(value, value["source_files"], Reader())["passed"]
    with pytest.raises(ValueError, match="source changed"):
        admission.validate_cpu(value, {"old": "changed"}, Reader())
    value["controls"].pop(next(iter(admission.REQUIRED_CONTROLS)))
    with pytest.raises(ValueError, match="controls missing"):
        admission.validate_cpu(value, value["source_files"], Reader())


def test_no_admission_file_is_created_after_failed_candidate(tmp_path, monkeypatch):
    def reject(*args, **kwargs):
        raise ValueError("single candidate failed")

    monkeypatch.setattr(admission, "build_admission", reject)
    output = tmp_path / "admission.json"
    with pytest.raises(ValueError, match="candidate failed"):
        admission.create_admission(tmp_path, "controls", "replay", output)
    assert not output.exists()


def test_host_reference_shape_repair_reuses_exact_replay_and_preserves_original():
    expected = {
        "scripts/software_organization_stop_policy_v048.py",
        "tests/test_software_organization_stop_policy_v048.py",
        "scripts/software_organization_admission_v048.py",
        "tests/test_software_organization_admission_v048.py",
    }
    assert admission.REPLAY_HOST_ONLY_REPAIRS == expected
    value = _replay()
    value["source_files"] = {**value["source_files"], **{name: "old-host-sha" for name in expected},
                             "src/proworksim/software_context_v048.py": "frozen-gamma-sha"}
    original = copy.deepcopy(value)
    current = {**value["source_files"], **{name: "new-host-sha" for name in expected}}
    summary = admission.validate_replay(value, current, _reader(value))
    reuse = summary["replay_source_reuse"]
    assert summary["passed"] is True and reuse["new_tokenizer_calls"] == 0
    assert {r["path"] for r in reuse["changed_host_only_files"]} == expected
    assert all(r["old_sha256"] == "old-host-sha" and r["new_sha256"] == "new-host-sha"
               for r in reuse["changed_host_only_files"])
    assert reuse["unchanged_source_file_count"] == 2
    assert value == original


def test_host_reference_shape_reuse_rejects_context_replay_world_or_inventory_change():
    fixed_paths = (
        "src/proworksim/software_context_v048.py",
        "src/proworksim/software_organization_runtime_v047.py",
        "src/proworksim/software_organization_v047.py",
        "scripts/software_context_replay_v048.py",
    )
    original = {path: "frozen-sha" for path in fixed_paths}
    for path in fixed_paths:
        with pytest.raises(ValueError, match="representation/runtime/numerical source changed"):
            admission.validate_replay_source_reuse(original, {**original, path: "changed"})
    with pytest.raises(ValueError, match="inventory changed"):
        admission.validate_replay_source_reuse(original, {**original, "scripts/extra_v048.py": "new"})
    with pytest.raises(ValueError, match="inventory changed"):
        admission.validate_replay_source_reuse(original, {fixed_paths[0]: "frozen-sha"})
