"""Development-pool partition, real source behavior and frozen boundary guards."""
import copy
import json
import shutil

import pytest

from proworksim import software_tasks_v030 as source


def test_six_distinct_contracts_stay_in_development_and_hide_controller_assets():
    manifest = json.loads((source.ASSETS / "source-manifest.json").read_text())
    assert manifest["development_case_count"] == 6
    assert manifest["independent_repository_count"] == 1
    repositories = list(manifest["source_partition"].values())[:4]
    assert len({repo for group in repositories for repo in group}) == 4
    contracts = set()
    for index, task_id in enumerate(source.TASK_IDS):
        case = source.build_case(task_id)
        assert case["purpose"] == "model_interface_development"
        assert not case["training_eligible"]
        assert not case["contribution_eligible"]
        assert not case["independent_confirmation_eligible"]
        assert not case["task_definitions"] and not case["initial_owners"]
        assert case["active_roles"] == (["member_a"] if index < 4 else ["member_a", "member_b"])
        assert case["category"] == ("api_normal_path" if index < 2 else
                                    "repair_after_real_failure" if index < 4 else "o1_root_goal")
        assert set(case["editable_paths"]) == {"models.py", "consumer.py", "test_member.py"}
        assert not any("reference" in name or "acceptance" in name or "bad-control" in name
                       for name in case["files"])
        assert case["files"]["test_member.py"].startswith("#")
        assert "LICENSE" in case["files"] and "NOTICE" in case["files"]
        contracts.add(case["root_goal"])
        directory = source.ASSETS / task_id
        public = json.loads((directory / "public-checks.json").read_text())["cases"]
        hidden = json.loads((directory / "acceptance.json").read_text())["cases"]
        public_inputs = {json.dumps(row["request"]["args"], sort_keys=True) for row in public}
        hidden_inputs = {json.dumps(row["request"]["args"], sort_keys=True) for row in hidden}
        assert public_inputs.isdisjoint(hidden_inputs)
    assert len(contracts) == 6


@pytest.mark.parametrize("task_id", source.TASK_IDS)
def test_reference_and_incomplete_controls_are_distinguishable(tmp_path, task_id):
    files = source.reference_solution(task_id)
    public = source.run_public_tests(task_id, files, run_root=tmp_path)
    assert public["passed"], public
    assert public["groups"]["upstream_regressions"]["passed"]
    assert public["groups"]["public_normal"]["passed"]
    assessment = source.assess(task_id, files, run_root=tmp_path)
    assert assessment["passed"], assessment
    assert not assessment["expected_values_sent_to_worker"]
    assert not assessment["training_trajectory"]
    for name, bad in source.bad_controls(task_id).items():
        result = source.assess(task_id, bad, run_root=tmp_path)
        assert result["execution"]["executed"], name
        assert not result["passed"], name


@pytest.mark.parametrize("task_id", source.TASK_IDS[2:4])
def test_repair_feedback_is_an_actual_application_failure(tmp_path, task_id):
    case = source.build_case(task_id)
    result = source.run_public_tests(task_id, case["files"], run_root=tmp_path)
    assert result["execution"]["executed"] and result["execution"]["driver_completed"]
    assert result["groups"]["upstream_regressions"]["passed"]
    assert not result["groups"]["public_normal"]["passed"]
    assert any(not test["passed"] for test in result["groups"]["public_normal"]["tests"])


def test_controller_assets_and_public_contract_digests_are_enforced(tmp_path, monkeypatch):
    destination = tmp_path / "assets"
    shutil.copytree(source.ASSETS, destination)
    monkeypatch.setattr(source, "ASSETS", destination)
    task_id = source.TASK_IDS[0]
    reference = destination / task_id / "reference/consumer.py"
    reference.write_text(reference.read_text() + "\n# unregistered change\n")
    with pytest.raises(ValueError, match="Frozen development asset changed"):
        source.reference_solution(task_id)
    fixture = destination / task_id / "acceptance.json"
    fixture.write_text('{"cases": []}\n')
    with pytest.raises(ValueError, match="Frozen development asset changed"):
        source.assess(task_id, source.build_case(task_id)["files"], run_root=tmp_path)


def test_assessment_rejects_edits_to_public_tests_before_execution(tmp_path, monkeypatch):
    case = source.build_case(source.TASK_IDS[0])
    files = copy.deepcopy(case["files"])
    files["test_visible.py"] = "print('passed')\n"
    monkeypatch.setattr(source, "run_isolated", lambda *a, **k: pytest.fail("must not run"))
    with pytest.raises(ValueError, match="Only public editable paths"):
        source.assess(case["task_id"], files, run_root=tmp_path)
