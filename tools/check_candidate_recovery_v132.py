"""One immutable real closed team plus narrow negative controls, without dispatch."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    def deny(event, unused):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto", "subprocess.Popen"}:
            raise AssertionError("The original-candidate recovery control has no subprocess/network/API permission")

    sys.addaudithook(deny)
    from proworksim import software_benchmark_candidate_recovery_v132 as recovery
    from proworksim.software_benchmark_candidates_v054 import reference, write_new, checked

    plan_ref = reference(recovery.ORIGINAL_PLAN)
    row = next(item for item in recovery.load(plan_ref)["rows"] if item["slot_index"] == 9042)
    original_ref = reference(recovery.ORIGINAL_BATCH / "episodes/9042/result.json")
    original = recovery.load(original_ref)
    child_original = original["controller_result"]
    result_ref = recovery.recover_closed_candidate(row, original_ref, output / "9042", original_plan_ref=plan_ref)
    result = recovery.validate_recovered_result(result_ref, original_plan_ref=plan_ref)
    assert result["status"] == "closed" and result["original_status"] == "technical_unknown"
    assert result["ledger"]["known_actual_tokens"] == 4_943_824
    assert result["model_calls"] == 93 and result["new_model_calls"] == 0
    assert result["delivery_validation"]["organization_submission_verified"] is True
    assert result["same_code_and_delivery_tree"] is True
    for name in ("candidate_lock", "delivery_candidate_lock"):
        lock = recovery.load(result[name])
        patch = lock["patch_receipt"]
        assert checked(patch["patch"]).read_bytes() == checked(patch["original_patch"]).read_bytes()
    assert reference(original_ref["path"]) == original_ref
    assert reference(child_original["path"]) == child_original
    negative = []
    original_load = recovery.load

    def reject(label, target, mutate):
        def altered(ref):
            value = original_load(ref)
            if ref == target:
                value = copy.deepcopy(value)
                mutate(value)
            return value
        recovery.load = altered
        try:
            recovery.inspect_recoverable(row, original_ref, original_plan_ref=plan_ref)
        except (ValueError, KeyError, FileNotFoundError) as error:
            negative.append({"case": label, "rejected": True, "error": str(error)})
        else:
            raise AssertionError("Ineligible original accepted: " + label)
        finally:
            recovery.load = original_load

    reject("missing_controller_other_failure", original_ref, lambda v: v.update(
        error={"type": "FileNotFoundError", "message": "controller-result.json missing"}))
    reject("original_controller_not_closed", child_original, lambda v: v.update(status="technical_unknown"))
    reject("original_writer_OOM", original["writer_quiescence"], lambda v: v["writers"][0]["state"].update(OOMKilled=True))
    pair_ref = result["project_closure"]["project_candidate_lock"]
    reject("original_candidate_not_locked_before_scoring", pair_ref, lambda v: v.update(locked_before_grading=False))
    fake = copy.deepcopy(result)
    fake["known_actual_tokens"] -= 1
    fake_ref = write_new(output / "9042/forged-result.json", fake)
    try:
        recovery.validate_recovered_result(fake_ref, original_plan_ref=plan_ref)
    except ValueError as error:
        negative.append({"case": "forged_recovery_usage", "rejected": True, "error": str(error)})
    else:
        raise AssertionError("Derived result changed the historical actual tokens")
    summary = {"passed": True, "version": recovery.VERSION,
        "real_original_slot": 9042, "original_result": original_ref,
        "original_controller_result": child_original, "derived_result": result_ref,
        "same_original_code_and_delivery_patch_bytes": True,
        "original_unknown_retained": True, "original_actual_tokens": 4_943_824,
        "original_actual_calls": 93, "negative_controls": negative,
        "subprocesses": 0, "API_calls": 0, "Docker_operations": 0, "new_model_calls": 0,
        "new_scoring_calls": 0, "runtime_source": reference(recovery.__file__),
        "control_source": reference(__file__)}
    print(json.dumps(write_new(output / "summary.json", summary)))


if __name__ == "__main__":
    main()
