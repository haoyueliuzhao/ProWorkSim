"""CPU checks of the supplementary scorer's executing scope and lock boundary."""
from __future__ import annotations

import inspect

import pytest

from proworksim import software_benchmark_rescore_v145 as rescore
from proworksim import software_benchmark_stopped_recovery_v145 as recovery
from proworksim import software_benchmark_recovered_validation_v145 as recovered_validation
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def test_official_and_reset_paths_use_new_scoring_scope_and_real_environment_binding():
    scorer = rescore.build_scorer(manifest_provider=lambda: {"CPU_fixture": True})
    namespace = scorer.validate_request.__globals__
    policy = namespace["policy"]
    assert policy.VERSION == rescore.VERSION
    assert policy.PLAN_FILE == rescore.PLAN
    assert policy.BATCH_ROOT == rescore.RUN
    assert policy.require_v066_allowed is rescore.allowed
    assert namespace["diagnostics"].make_repaired_run_instance is (
        rescore.base.original.diagnostics.make_repaired_run_instance
    )
    selected = inspect.getclosurevars(scorer._score).nonlocals
    assert selected["concrete"].__globals__["policy"] is policy
    assert selected["reset"]._score.__globals__["policy"] is policy
    for provider in (scorer.environment.offline, scorer.environment.tls):
        assert provider.validate_environment.__globals__["environment_manifest"] is (
            provider.environment_manifest
        )
        assert rescore.previous.current_environment.assert_runtime_binding(provider)
    authorize = scorer.environment.tls.transport.relay_many.__globals__["_authorize"]
    assert inspect.getclosurevars(authorize).nonlocals["policy"] is policy


def test_two_lane_limit_and_memory_admission_fail_before_resource_creation():
    policy = rescore.policy()
    assert policy.cpu_set("grader", 0) != policy.cpu_set("grader", 1)
    for lane in (None, -1, 2, True):
        with pytest.raises(ValueError):
            policy.cpu_set("grader", lane)
    with pytest.raises(ValueError):
        policy.claim_resource("foreign-score", lane=2)
    namespace = inspect.getclosurevars(policy._budget).nonlocals["ns"]
    namespace["physical_capacity"] = lambda: {
        "passed": True, "memory_available_bytes": 100 * 1024**3
    }
    assert policy._budget([{}], 4, 16 * 1024**3)["reserved_cpu_after"] == 8
    with pytest.raises(rescore.dispatch.ResourceBusy):
        policy._budget([{}, {}], 4, 16 * 1024**3)
    namespace["physical_capacity"] = lambda: {
        "passed": True, "memory_available_bytes": 83 * 1024**3
    }
    with pytest.raises(rescore.dispatch.ResourceBusy):
        policy._budget([], 4, 16 * 1024**3)


def test_plan_cannot_substitute_a_different_lock_after_recovery_validation(tmp_path, monkeypatch):
    scorer = rescore.build_scorer(manifest_provider=lambda: {"CPU_fixture": True})
    original_plan = rescore.load(reference(rescore.previous.scope.PLAN_FILE))
    row = next(r for r in original_plan["rows"] if r["slot_index"] == 10066)
    config = rescore.load(row["configuration"])
    patch = write_new(tmp_path / "candidate.patch", b"retained patch bytes\n")
    value = {"slot": row, "lock_before_grading": True,
             "candidate_selection_after_scoring": False, "patch_receipt": {"patch": patch}}
    authentic = write_new(tmp_path / "authentic-lock.json", value)
    substituted = write_new(tmp_path / "substituted-lock.json", value)
    result = write_new(tmp_path / "recovery-result.json", {"candidate_lock": authentic})
    def reject_unnecessary_deep_validation(*args):
        raise AssertionError("The substituted lock must fail before evidence traversal")

    monkeypatch.setattr(recovered_validation, "validate_recovery_result_bounded",
                        reject_unnecessary_deep_validation)
    plan = {"rows": [row], "candidates": {str(row["slot_index"]): {
        "result": result, "candidate_lock": substituted}}}
    request = {"slot_id": row["slot_id"], "generation_result": result,
               "candidate_lock": substituted, "measurement_kind": recovery.ENDPOINT}
    resource = {"role": "score", "endpoint": recovery.ENDPOINT,
                "image_id": config["scorer_request_base"]["image"]["image_id"]}
    with pytest.raises(ValueError, match="[Ll]ock|candidate|recovery"):
        scorer.validate_candidate_request(request, resource, config, plan)
