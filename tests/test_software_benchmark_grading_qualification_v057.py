"""Failed gold or non-discriminating baseline controls must block regrading."""
import copy

import pytest

from proworksim import software_benchmark_grading_qualification_v057 as qualification


def fixture(monkeypatch):
    data = {"plan": {"environment_revision": "environment", "nat_registry": "historical-nat",
                     "tasks": sorted(qualification.TASKS), "preparation_only": True}}
    value = {"version": qualification.VERSION, "passed": True, "tasks": sorted(qualification.TASKS),
             "controls": [], "model_calls": 0, "official_scores_changed": False,
             "environment_revision": "environment", "plan": "plan", "nat_registry": "historical-nat"}
    originals = {}
    for task in sorted(qualification.TASKS):
        original = {"instance_id": task, "image": {"id": task}, "dataset": {"id": "fixed"},
                    "baseline_mapping": {"id": task}, "scorer_manifest": {"id": "official"}}
        originals[task] = original
        for kind in ("gold", "empty"):
            key = task + ":" + kind
            item = {"instance_id": task, "patch_kind": kind}
            for field in ("receipt", "identity", "quiescence", "completion", "initial_container", "original_request"):
                item[field] = key + ":" + field
            data[item["original_request"]] = original
            data[item["identity"]] = {**original, "candidate_kind": kind, "plan": "plan",
                "environment_revision": "environment", "original_request": item["original_request"],
                "nat_lane": {"registry": "historical-nat"}}
            data[item["receipt"]] = {"instance_id": task, "patch_kind": kind, "status": "official_report",
                "model_calls": 0, "preparation_only": True, "actor_feedback": False, "identity": item["identity"],
                "resolved": kind == "gold", "official_result": [task, {task: {
                    "patch_successfully_applied": True, "resolved": kind == "gold", "infra_failure": False,
                    "tests_status": {"FAIL_TO_PASS": {"failure": ["target"] if kind == "empty" else []}}}}]}
            data[item["initial_container"]] = {"nat_lane": {"registry": "historical-nat"},
                "host_network_namespace_shared": False, "timeout_route": {"real_connect_timeout": True},
                "container_id": key}
            data[item["quiescence"]] = {"quiescent": True, "cleanup_errors": [],
                "owned_container_ids": [key], "create_result_unknown": False}
            data[item["completion"]] = {"returncode": 0}
            value["controls"].append(item)
    data["qualification"] = value
    monkeypatch.setattr(qualification, "load", lambda reference: data[reference])
    monkeypatch.setattr(qualification.environment, "validate_environment", lambda reference: {})
    return data, originals


def test_complete_controls_admit_only_the_same_task_environment(monkeypatch):
    _, originals = fixture(monkeypatch)
    request = next(iter(originals.values()))
    assert qualification.validate_qualification("qualification", request)["passed"] is True
    with pytest.raises(ValueError, match="qualified task environment"):
        qualification.validate_qualification("qualification", {**request, "image": {"id": "other-image"}})


@pytest.mark.parametrize("kind", ["gold", "empty"])
def test_one_failed_positive_or_successful_baseline_blocks_all_regrading(monkeypatch, kind):
    data, originals = fixture(monkeypatch)
    item = next(row for row in data["qualification"]["controls"] if row["patch_kind"] == kind)
    receipt = copy.deepcopy(data[item["receipt"]])
    receipt["resolved"] = kind != "gold"
    receipt["official_result"][1][item["instance_id"]]["resolved"] = kind != "gold"
    data[item["receipt"]] = receipt
    with pytest.raises(ValueError, match="reference repair|Unchanged baseline"):
        qualification.validate_qualification("qualification", next(iter(originals.values())))


def test_unproved_owned_container_cleanup_blocks_all_regrading(monkeypatch):
    data, originals = fixture(monkeypatch)
    item = data["qualification"]["controls"][0]
    data[item["quiescence"]]["owned_container_ids"] = ["another-container"]
    with pytest.raises(ValueError, match="quiescence"):
        qualification.validate_qualification("qualification", next(iter(originals.values())))
