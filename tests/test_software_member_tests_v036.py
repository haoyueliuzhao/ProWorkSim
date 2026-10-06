"""Finite new CPU controls; no historical member script or model is replayed."""
import copy
import os
from pathlib import Path

import pytest

from proworksim import software_member_tests_v036 as member
from proworksim.storage import atomic_write, json_bytes


def output(tmp_path, name):
    return Path(os.environ.get("PROWORKSIM_V036_MEMBER_CONTROL_RUN", str(tmp_path))) / name


def unittest_script(*, passing=True, exit=True):
    return ("import unittest\nclass Check(unittest.TestCase):\n"
            "    def test_real_body(self):\n"
            f"        self.assertEqual(1, {1 if passing else 2})\n"
            f"unittest.main(exit={exit!r})\n")


CASES = [
    ("normal_assert_return", "assert 2 + 2 == 4\n", True, "normal_script_return"),
    ("unittest_success_exit_zero", unittest_script(), True, "verified_unittest_main_exit_zero"),
    ("unittest_failure_nonzero", unittest_script(passing=False), False, "unverified_system_exit"),
    ("unittest_success_normal_return", unittest_script(exit=False), True, "normal_script_return"),
    ("unittest_failure_normal_return", unittest_script(passing=False, exit=False), False, "normal_script_return"),
    ("ordinary_exception", "raise ValueError('real exception')\n", False, "script_exception"),
    ("ordinary_assertion_failure", "assert False, 'real assertion failure'\n", False, "script_exception"),
    ("arbitrary_zero_and_ok_text", "import sys\nprint('Ran 100 tests / OK')\nsys.exit(0)\n", False, "unverified_system_exit"),
    ("later_arbitrary_zero_after_passed_runner", unittest_script(exit=False) + "raise SystemExit(0)\n", False, "unverified_system_exit"),
    ("unittest_zero_tests", "import unittest\nunittest.main()\n", False, "unverified_system_exit"),
    ("unittest_zero_tests_normal_return", "import unittest\nunittest.main(exit=False)\n", False, "normal_script_return"),
    ("unittest_only_skipped", "import unittest\n@unittest.skip('not executed')\nclass Check(unittest.TestCase):\n    def test_skipped(self):\n        raise AssertionError('must not run')\nunittest.main()\n", False, "unverified_system_exit"),
    ("fabricated_result_without_runner_execution", "import unittest\nclass FakeRunner:\n    def __init__(self, **kwargs):\n        pass\n    def run(self, suite):\n        result = unittest.TestResult()\n        result.testsRun = 1\n        return result\nunittest.main(testRunner=FakeRunner)\n", False, "unverified_system_exit"),
]


@pytest.mark.parametrize("name,script,passed,completion", CASES, ids=[case[0] for case in CASES])
def test_new_actual_member_completion_cases(tmp_path, name, script, passed, completion):
    root = output(tmp_path, "member-cases")
    result = member.member_test_feedback({"test_member.py": script}, run_root=root / name)
    atomic_write(root / (name + ".json"), json_bytes({"case": name, "script": script, "result": result,
        "model_calls": 0, "optimizer_steps": 0, "historical_script_replayed": False}))
    assert result["executed"] is True
    assert result["passed"] is passed
    assert result["completion_evidence_status"] == "recorded"
    evidence = result["completion_evidence"]
    assert evidence["completion"] == completion
    if passed:
        assert result["execution"]["driver_completed"] is True and result["execution"]["returncode"] == 0
    if name.startswith("unittest_success"):
        assert len(evidence["unittest_runs"]) == 1
        run = evidence["unittest_runs"][0]
        assert run["runner_returned"] is run["actual_unittest_result"] is run["successful"] is True
        assert run["test_methods_started"] == run["test_methods_finished"] == run["tests_run"] == 1
    if name == "arbitrary_zero_and_ok_text":
        assert result["execution"]["returncode"] == 0
        assert result["execution"]["driver_completed"] is False
    if name == "later_arbitrary_zero_after_passed_runner":
        assert evidence["unittest_runs"][0]["qualifies"] is True
        assert result["execution"]["driver_completed"] is False
    if name == "unittest_only_skipped":
        assert evidence["unittest_runs"][0]["tests_run"] == 1
        assert evidence["unittest_runs"][0]["test_methods_started"] == 0


def test_missing_structured_completion_is_not_success(tmp_path, monkeypatch):
    execution = {"executed": True, "driver_completed": True, "returncode": 0, "output": "OK\n"}
    monkeypatch.setattr(member, "run_isolated", lambda *args, **kwargs: copy.deepcopy(execution))
    result = member.member_test_feedback({"test_member.py": "assert True\n"}, run_root=tmp_path)
    assert result["status"] == "failed" and result["passed"] is False
    assert result["completion_evidence"] is None
    assert result["completion_evidence_status"] == "missing_or_ambiguous"
    atomic_write(output(tmp_path, "missing-completion-proof.json"), json_bytes({"passed": True,
        "result": result, "kind": "injected missing-evidence counterexample; no actual script execution", "model_calls": 0}))


def test_empty_member_script_remains_explicitly_untested(tmp_path):
    result = member.member_test_feedback({"test_member.py": '"""Optional tests."""\npass\n'}, run_root=tmp_path)
    assert result["status"] == "untested" and result["executed"] is False and result["passed"] is None


def test_new_world_feedback_identity_current_version_gates_and_preserved_task(tmp_path):
    from proworksim import software_collaboration_v035 as prior_world
    from proworksim import software_collaboration_v036 as world
    from proworksim import software_tasks_v036 as source

    root = output(tmp_path, "world-feedback")
    case = world.case_spec(world.TRAINING_CASE_ID)
    prior = prior_world.case_spec(world.TRAINING_CASE_ID)
    assert case["source_contract"] == prior["source_contract"]
    assert case["root_goal"] == prior["root_goal"]
    assert case["public_feedback_version"] == world.PUBLIC_FEEDBACK_VERSION
    assert case["member_test_protocol"] == member.specification()
    with pytest.raises(ValueError, match="changed"):
        world.validate_case(prior)
    prepared = world.build_software_collaboration_case(case, root / "case")
    initial = world.prove_initial_team(prepared)
    assert initial["initial_task_count"] == 0 and initial["actual_private_work_copies"] == 2
    port = world.SoftwareCollaborationPort(prepared.world.session("member_a", world.PROJECT), "member_a")

    def call(name, **arguments):
        response = port.call(name, **arguments)
        assert response["ok"], response
        return response

    call("create_task", task_id="CPUControl", description="New optional member-test protocol control only")
    call("claim_task", task_id="CPUControl")
    files = source.reference_solution(world.TRAINING_CASE_ID)
    for name in ("reader.py", "report.py"):
        call("write_file", path=name, text=files[name])
    script = ("import unittest\nfrom report import summarize\nclass Check(unittest.TestCase):\n"
              "    def test_real_product(self):\n        self.assertEqual(summarize('SELECT label FROM bins')['total'], 1)\n"
              "unittest.main()\n")
    call("write_file", path="test_member.py", text=script)
    before_test = port.call("submit_integration")
    assert not before_test["ok"] and "Run real tests" in before_test["error"]["message"]
    response = call("run_tests")
    shown = response["result"]
    state = prepared.world.store.load()
    event = next(event for event in state["software_events"] if event["kind"] == "test")
    raw = {key: copy.deepcopy(value) for key, value in event.items() if key not in (
        "sequence", "actor_id", "kind", "logical_time", "operation_id", "action_id", "responsibility_snapshot")}
    saved = copy.deepcopy(raw)
    assert world.project_public_test_feedback(raw) == shown and raw == saved
    assert world.project_public_test_feedback(shown) == shown
    assert all(group["passed"] is True for group in shown["groups"].values())
    assert shown["groups"]["member_tests"]["completion_evidence"]["completion"] == "verified_unittest_main_exit_zero"
    assert shown["feedback_presentation"]["version"] == world.PUBLIC_FEEDBACK_VERSION
    assert shown["feedback_presentation"]["public_projection_algorithm_version"] == source.PUBLIC_FEEDBACK_VERSION
    assert shown["feedback_presentation"]["member_test_version"] == member.VERSION
    assert state["operation_commits"][response["command_id"]]["public_result"]["result"] == shown
    assert raw["public_execution"]["execution"]["output"]
    assert shown["team_test_budget"]["used"] == 1
    before_fixed = port.call("submit_integration")
    assert not before_fixed["ok"] and "Publish a fixed patch" in before_fixed["error"]["message"]
    call("fix_patch", task_ids=["CPUControl"], message="New CPU reference control, not a policy episode")
    submission = call("submit_integration")
    assert submission["result"]["fixed_submission_is_acceptance"] is False
    call("write_file", path="report.py", text=files["report.py"] + "\n# new untested version\n")
    after_edit = port.call("submit_integration")
    assert not after_edit["ok"] and "Run real tests" in after_edit["error"]["message"]
    atomic_write(root / "raw-test-result.json", json_bytes(raw))
    atomic_write(root / "presented-test-result.json", json_bytes(shown))
    atomic_write(root / "proof.json", json_bytes({"passed": True, "initial_team": initial,
        "member_test_specification": member.specification(), "public_feedback_version": world.PUBLIC_FEEDBACK_VERSION,
        "interface_revision": world.INTERFACE_REVISION, "retained_source_contract_unchanged": True,
        "current_version_execution_and_fixed_patch_gates_preserved": True,
        "actual_run_tests": 1, "actual_cpu_sandbox_executions": 2,
        "new_model_calls": 0, "new_optimizer_steps": 0, "new_independent_acceptance_executions": 0,
        "historical_member_scripts_replayed": 0,
        "scope": "One new CPU reference world and finite script controls only; not current-policy support or acceptance."}))
