import json

import pytest

from proworksim import software_benchmark_continuation_v061 as continuation
from proworksim.software_benchmark_candidates_v054 import reference


def fixture(tmp_path, monkeypatch, defect=None):
    monkeypatch.setattr(continuation, "BATCH_ROOT", tmp_path)
    rows = [{"measurement_kind": "fresh_generation_recovery", "slot_index": index, "slot_id": "slot-" + str(index)} for index in range(13)]
    plan = {"rows": rows}
    closures = []
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return reference(path)
    for index in (0, 1):
        folder = tmp_path / "residents" / ("model-" + str(index))
        unit = "proworksim-v061-model-" + str(index) + ".service"
        write(folder / "spec.json", {"unit": unit, "gpu_memory_utilization": 0.6})
        closed = {"unit": unit, "child_exited": True, "status": "technical_unknown",
                  "error": {"message": "Owned REF engine exited before readiness"}}
        if defect == "live_child" and index == 0:
            closed["child_exited"] = False
        closed_ref = write(folder / "closed.json", closed)
        closures.append({"unit": unit, "owned_unit_stopped": defect != "unproven_unit", "closed": closed_ref})
        if index == 0 and defect == "ready":
            write(folder / "ready.json", {})
        if index == 0 and defect == "neutral":
            write(folder / "neutral-admission/result.json", {"model_calls": 1})
    summary = {"failure": {"kind": "model_admission_unavailable"}, "generation": {},
        "unentered_generation": [row["slot_id"] for row in rows], "resident_closure": closures}
    if defect == "entered":
        summary["generation"] = {"slot-0": {"status": "closed"}}
    write(tmp_path / "continuation/model-memory-r3/run-summary.json", summary)
    if defect == "claim":
        write(tmp_path / "resource-claims/actor-0.json", {})
    return plan


def test_only_closed_pre_sampling_failures_allow_explicit_compiler_redeployment(tmp_path, monkeypatch):
    plan = fixture(tmp_path, monkeypatch)
    evidence = continuation.compiler_deployment_recovery_evidence(plan)
    assert len(evidence["remaining_generation"]) == 13
    assert len(evidence["prior_residents"]) == 2
    assert evidence["new_unique_user_units"] == 0
    assert evidence["formal_generation_replayed"] is False


@pytest.mark.parametrize("defect", ["live_child", "unproven_unit", "ready", "neutral", "entered", "claim"])
def test_sampling_or_unproven_cleanup_cannot_be_relabelled_as_initialization_failure(tmp_path, monkeypatch, defect):
    plan = fixture(tmp_path, monkeypatch, defect)
    with pytest.raises(ValueError):
        continuation.compiler_deployment_recovery_evidence(plan)
