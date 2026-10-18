"""Three new CPU-only report contracts, independent of model/runner execution."""
import copy

from scripts import software_calibration_v051_cal2_report as report


def test_fixed_six_equal_weights_unknown_bounds_and_native_delivery_not_applicable():
    rows = [{"task_id": task, "condition": condition, "R_code": int(condition != "R"),
        "R_joint": None if condition == "R" else 1, "administrative_censoring": condition == "P",
        "R_token": None if condition == "P" else 1}
        for task in report.TASKS for condition in report.CONDITIONS]
    rows[-1]["R_code"] = None
    metrics = report.endpoint_metrics(rows, "R_code")
    assert metrics["P_minus_R"]["mean"] == 1
    assert metrics["U"]["mean"] is None
    assert metrics["U"]["bounds"] == [5 / 6, 1]
    assert metrics["U_minus_P"]["mean"] is None
    assert metrics["U_minus_P"]["bounds"] == [5 / 6 - 1, 0]
    fixed = report.endpoint_metrics(rows, "R_joint", conditions=("P", "U"))
    assert fixed["P"]["mean"] == fixed["U"]["mean"] == 1
    assert fixed["R"]["applicable"] is False
    assert fixed["R"]["mean"] is None
    assert "P_minus_R" not in fixed
    assert all(row["R_token"] is None for row in rows if row["condition"] == "P")


def test_collection_unrun_nodes_are_explicit_and_quality_keeps_full_denominator():
    execution = {"executed": True, "source_attributable_collection_failure": True,
        "source_unchanged": True, "test_integrity": True, "unexpected_test_ids": [],
        "all_expected_tests_observed": False}
    native_checks = [{"nodeid": f"test::{i}", "node_outcome_observed": i == 0,
        "pytest_status": "passed" if i == 0 else "not_run_due_to_code_collection_failure",
        "passed": i == 0} for i in range(4)]
    base = {"executed": True, "R_code": 0, "Q_task": .25, "tests_passed": 1, "tests_total": 4}
    native = {**base, "checks": native_checks, "execution": execution}
    pws = {**base, "assessment": {"independent_acceptance": {"execution": execution,
        "checks": [{"case_id": row["nodeid"], "passed": row["passed"],
            "observed": {k: row[k] for k in ("node_outcome_observed", "pytest_status")}} for row in native_checks]}}}
    for terminal in (native, pws):
        value = report.terminal_test_summary(terminal)
        assert value["binding_issues"] == []
        assert value["Q_terminal"] == .25
        assert value["Q_full_node_outcome_bounds"] == [.25, 1]
        assert value["observed_test_nodes"] == 1
        assert value["not_run_count"] == 3
        assert value["observed_failed"] == value["observed_errors"] == 0
    unknown = copy.deepcopy(native)
    unknown.update(executed=False, R_code=None, Q_task=None)
    unknown["execution"]["executed"] = False
    assert report.terminal_test_summary(unknown)["Q_terminal"] is None


def test_unique_native_receipts_separate_actual_reservation_and_undispatched(tmp_path):
    calls = tmp_path / "calls"
    calls.mkdir()
    def write(name, value):
        (calls / name).write_bytes(report.common.json_bytes(value))
    actor = {"test": "CPU-only synthetic identity"}
    native = {"input_ids": [1, 2, 3]}
    for key, reservation in (("a", 8), ("b", 11), ("c", 9)):
        prepared = {"attempt_id": key, "actor_identity": actor, "native_input": native,
                    "reserved_maximum_tokens": reservation, "generation_started": False}
        write(f"{key}-prepared.json", prepared)
        if key != "c":
            write(f"{key}-started.json", {**prepared, "generation_started": True})
    complete = {"attempt_id": "a", "actor_identity": actor, "input": native,
        "output_ids": [4, 5, 6, 7, 8], "path": "project",
        "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}}
    write("a-complete.json", complete)
    write("b-fault.json", {"attempt_id": "b", "generation_started": True, "actual_usage": None})
    value = report.native_receipts(report.common.Reader(), tmp_path)
    assert value["known_actual_tokens"] == 8
    assert value["uncertain_reservation_tokens"] == 11
    assert value["complete_actual_tokens"] is None
    assert value["prepared_without_generation"] == ["c"]
    assert value["started_generations"] == 2 and value["bound_complete_generations"] == 1
    complete["usage"]["total_tokens"] = 7
    write("a-complete.json", complete)
    broken = report.native_receipts(report.common.Reader(), tmp_path)
    assert broken["known_actual_tokens"] == 0
    assert broken["uncertain_reservation_tokens"] == 19
    assert broken["complete_actual_tokens"] is None
    assert broken["integrity_errors"]
