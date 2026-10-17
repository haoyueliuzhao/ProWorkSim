"""Finite CPU fixture controls; no real repository pytest, model or GPU call."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.repository_sources_v051 import RepositorySources
from proworksim.software_calibration_world_v051 import (
    PROJECT, SoftwareCollaborationPort, assess_software_collaboration,
    assess_terminal_working_tree, build_software_collaboration_case, case_spec, validate_case,
)
from proworksim.storage import digest, json_bytes

SOURCE = Path(__file__).resolve().parents[1] / "artifacts/software-calibration-v051/cal2-sources"
pytestmark = pytest.mark.skipif(not (SOURCE / "cal2/adapter-manifest.json").is_file(), reason="Frozen external CAL-2 source package is not installed")


class RecordedFixtureRunner:
    def __init__(self, *, passed=True, mismatch=False):
        self.passed = passed
        self.mismatch = mismatch
        self.calls = []

    def __call__(self, *, files, task, run_root):
        self.calls.append({"files_sha256": digest(json_bytes(files)), "task": copy.deepcopy(task), "run_root": str(run_root)})
        return {"executed": True, "passed": self.passed, "returncode": 0 if self.passed else 1,
            "tests": [{"nodeid": node, "outcome": "passed" if self.passed else "failed",
                       "longreprtext": "" if self.passed else "CPU PROGRAMMED FIXTURE FAILURE " * 180}
                      for node in task["nodeids"]],
            "stdout": "CPU PROGRAMMED FIXTURE ONLY; NO CANDIDATE OR TEST EXECUTION",
            "input_files_sha256": "invalid" if self.mismatch else digest(json_bytes(files)),
            "source_unchanged": True, "test_integrity": True,
            "isolation": {"scope": "not_executed_cpu_programmed_fixture"}}


def sources(runner=None):
    return RepositorySources(SOURCE, runner=runner or RecordedFixtureRunner())


def prepared(tmp_path, runner=None):
    source = sources(runner)
    result = build_software_collaboration_case(case_spec("cal2-xmltodict-1", provider=source), tmp_path / "prepared", provider=source)
    return source, result


def call(world, name, **kwargs):
    value = world.session("member_001", PROJECT).call(name, **kwargs)
    assert value["ok"], value
    return value["result"]


def edit(world, suffix="\n# CPU TEST FIXTURE\n"):
    _, _, bundle = world._bundle("member_001")
    return call(world, "write_file", path="xmltodict.py", text=bundle["files"]["xmltodict.py"] + suffix)


def submit(world):
    edit(world)
    call(world, "run_tests")
    call(world, "fix_patch", task_ids=[], message="CPU programmed protocol fixture")
    return call(world, "submit_integration", message="CPU fixture")


def test_all_six_original_faulty_trees_bound_without_added_contract_or_oracle():
    provider = sources()
    assert len(provider.case_ids) == 6
    for case_id in provider.case_ids:
        case = provider.build_case(case_id)
        provider.validate_files(case_id, case["files"])
        assert len(case["files"]) <= 200
        assert sum(len(value.encode()) for value in case["files"].values()) < 2_000_000
        assert not {"contract.md", "defect.diff", "task.json", ".git"} & set(case["files"])
        assert "FAIL_TO_PASS" not in case["source_contract"]
        assert "PASS_TO_PASS" not in case["source_contract"]
        assert "patch" not in case["source_contract"]
        spec = provider.runner_spec(case_id)
        assert spec["nodeids"] == sorted(spec["nodeids"])
        assert "cal2" in spec["task_id"]
    with pytest.raises(ValueError):
        provider.build_case("hold-funcy-1")
    assert provider.runner.calls == []


def test_single_member_world_has_no_initial_work_or_hidden_identity(tmp_path):
    provider, p = prepared(tmp_path)
    world = p.world
    assert set(world.store.load()["actors"]) == {"operator", "member_001"}
    assert list(world._software()["registry"]) == ["member_001"]
    assert [x["actor"] for x in p.scenario["roles"]] == ["member_001"]
    assert len(world.state["artifacts"]) == 2
    assert world._software()["tasks"] == {}
    assert world.test_budget.snapshot()["used"] == 0
    assert world.state["software_events"] == []
    assert provider.runner.calls == []
    observation = SoftwareCollaborationPort(world.session("member_001", PROJECT), "member_001").observe()
    assert observation["execution_condition"]["private_working_copies"] == 1
    assert observation["contract"] == provider.build_case("cal2-xmltodict-1")["root_goal"]
    assert observation["initial_diagnostics"] == []
    assert observation["task_formation"]["population"] == "one_real_member"
    tools = {x["name"] for x in world.session("member_001", PROJECT).tools()}
    assert not {"spawn_member", "retire_member"} & tools
    for name, args in [("spawn_member", {"briefing": "no"}), ("retire_member", {"reason": "no"}),
                       ("send_message", {"recipient": "member_002", "task_id": "root_goal", "body": "no"})]:
        assert not world.session("member_001", PROJECT).call(name, **args)["ok"]
    assert list(world._software()["registry"]) == ["member_001"]
    bad = copy.deepcopy(p.case)
    bad["active_roles"].append("member_002")
    with pytest.raises(ValueError):
        validate_case(bad, provider=provider)


def test_original_test_readonly_and_real_production_edit_allowed(tmp_path):
    provider, p = prepared(tmp_path)
    before = provider.build_case(p.case["case_id"])["files"]
    assert not p.world.session("member_001", PROJECT).call("write_file", path="tests/test_xmltodict.py", text="pass")["ok"]
    edit(p.world)
    _, _, bundle = p.world._bundle("member_001")
    provider.validate_files(p.case["case_id"], bundle["files"])
    assert bundle["files"]["tests/test_xmltodict.py"] == before["tests/test_xmltodict.py"]
    assert bundle["files"]["xmltodict.py"] != before["xmltodict.py"]


def test_full_public_union_uses_original_exact_pages_and_one_test_charge(tmp_path):
    runner = RecordedFixtureRunner(passed=False)
    _, p = prepared(tmp_path, runner)
    first = call(p.world, "run_tests")
    assert len(first["page"]["text"]) <= 3072
    stored = p.world._software()["test_reports"][first["report_id"]]
    assert len(stored["pages"]) > 1
    assert set(stored["visible_result"]["groups"]) == {"repository_tests"}
    again = call(p.world, "read_test_result", report_id=first["report_id"], cursor=first["page"]["cursor"])
    assert again["page"] == first["page"]
    assert len(runner.calls) == 1
    assert p.world.test_budget.snapshot()["used"] == 1
    assert len(runner.calls[0]["task"]["nodeids"]) == 60


def test_fixed_and_terminal_same_tree_reuse_one_final_receipt(tmp_path):
    runner = RecordedFixtureRunner()
    _, p = prepared(tmp_path, runner)
    submit(p.world)
    fixed = assess_software_collaboration(p, run_root=tmp_path / "fixed")
    assert fixed["R"] == 1
    assert len(runner.calls) == 2  # one public invocation + one final invocation
    terminal = assess_terminal_working_tree(p, run_root=tmp_path / "terminal", fixed_assessment=fixed)
    assert terminal["R_code"] == 1 and terminal["reused_same_fixed_tree_assessment"]
    assert terminal["new_test_executions"] == 0 and len(runner.calls) == 2
    assert fixed["R"] == 1
    edit(p.world, "\n# later real version in CPU fixture\n")
    other = assess_terminal_working_tree(p, run_root=tmp_path / "later", fixed_assessment=fixed)
    assert other["R_code"] == 1 and not other["reused_same_fixed_tree_assessment"]
    assert other["new_test_executions"] == 1 and len(runner.calls) == 3
    assert other["files_sha256"] != fixed["files_sha256"]


def test_unsubmitted_terminal_code_endpoint_does_not_backfill_fixed_R(tmp_path):
    runner = RecordedFixtureRunner()
    _, p = prepared(tmp_path, runner)
    fixed = assess_software_collaboration(p, run_root=tmp_path / "fixed")
    assert fixed["R"] == 0 and fixed["submitted"] is False
    assert len(runner.calls) == 0
    terminal = assess_terminal_working_tree(p, run_root=tmp_path / "terminal", fixed_assessment=fixed)
    assert terminal["R_code"] == 1 and terminal["new_test_executions"] == 1
    assert fixed["R"] == 0 and fixed["submitted"] is False


def test_receipt_must_bind_exact_candidate_and_runner_is_required(tmp_path):
    provider = sources(RecordedFixtureRunner(mismatch=True))
    with pytest.raises(RuntimeError, match="exact candidate"):
        provider.assess_files(provider.case_ids[0], provider.build_case(provider.case_ids[0])["files"], run_root=tmp_path)
    absent = RepositorySources(SOURCE)
    with pytest.raises(ValueError, match="confined"):
        build_software_collaboration_case(absent.case_ids[0], tmp_path / "absent", provider=absent)


def test_new_collector_rejects_cal1_timeout_and_other_capacity():
    from proworksim.software_calibration_collector_v051 import validate_execution_contract
    contract = {"context_limit": 18432, "max_output_tokens": 2048, "enable_thinking": False,
        "preserve_thinking": False, "temperature": 0.7, "top_p": 1.0, "top_k": 0, "max_generation_seconds": 600}
    owner = SimpleNamespace(contract=contract, recipe={"max_length": 18432, "max_output_tokens": 2048, "temperature": 0.7}, path="project")
    assert validate_execution_contract(owner)["hard_generation_preemption_claimed"] is False
    owner.contract = {**contract, "max_generation_seconds": 7200}
    with pytest.raises(ValueError, match="600s"):
        validate_execution_contract(owner)


def test_real_sdk_single_session_collector_and_legal_test_feedback(tmp_path):
    pytest.importorskip("openhands.sdk")
    from test_software_organization_runtime_v038 import CPUOwner, action
    from test_software_organization_runtime_v040 import SelectedCPUTransport, tokenize
    from proworksim.software_context_v048 import SoftwareContextTransport
    from proworksim.software_calibration_collector_v051 import collect_episode

    runner = RecordedFixtureRunner(passed=False)
    _, p = prepared(tmp_path, runner)
    owner = CPUOwner({"member_001": [action("run_tests"), action("staff_done", reason="CPU fixture complete")]})
    owner.recipe.update(max_length=18432, max_output_tokens=2048, temperature=0.7)
    owner.contract = {"context_limit": 18432, "max_output_tokens": 2048, "enable_thinking": False,
        "preserve_thinking": False, "temperature": 0.7, "top_p": 1.0, "top_k": 0, "max_generation_seconds": 600}
    owner.actor_steps = owner.critic_steps = owner.policy_revision = 0
    owner.path = "project"
    owner.prepare_request = lambda request: (json.dumps(request, ensure_ascii=False, sort_keys=True), None, None)
    owner.tokenizer = tokenize
    owner.transport = SelectedCPUTransport(owner)
    result = collect_episode(owner, p, tmp_path / "collected", sampling_seed=551,
        slot_id="CPU-fixture-v051-cal2", calibration_condition="P",
        transport_factory=lambda current, path: SoftwareContextTransport(current, path, evidence_kind="cpu_programmed_fixture"))
    assert result["condition"] == "S1" and result["calibration_condition"] == "P"
    assert result["R"] == 0 and result["submitted"] is False and result["R_code"] == 0
    assert result["usage"]["attempts"] == 2 and owner.transport.calls == {"member_001": 2}
    assert result["member_lifecycle"]["cumulative_births"] == 1
    assert result["member_lifecycle"]["live_at_end"] == 1
    assert result["host_final_test_executions"] == 1
    assert len(runner.calls) == 2  # public feedback + separate declared terminal endpoint
    assert result["new_backward_calls"] == result["actor_updates"] == result["critic_updates"] == 0
    assert result["deadline_receipt"]["final_assessment_calls"] == 1
    second = json.loads((tmp_path / "collected/raw-transport/request-00002/selected-request.json").read_text())
    assert "paged-public-test-feedback-v0.42" in json.dumps(second)
    guard = json.loads((tmp_path / "collected/evaluation-guard.json").read_text())
    assert guard["learning_unchanged"] and guard["rng_restored_exactly"]


@pytest.mark.parametrize("candidate_bound,expected,returncode", [(True, True, 2), (True, True, 4), (False, False, 4)])
def test_new_collection_failure_attribution_does_not_invent_executed_tests(tmp_path, candidate_bound, expected, returncode):
    class CollectionFixture(RecordedFixtureRunner):
        def __call__(self, *, files, task, run_root):
            result = super().__call__(files=files, task=task, run_root=run_root)
            assert task["frozen_test_hashes"] and task["initial_production_hashes"]
            result.update(command_executed=True, executed=candidate_bound, passed=False, returncode=returncode,
                          tests=[], source_attributable_collection_failure=candidate_bound,
                          collection_errors=[{"nodeid": "tests/test_fixture.py", "longreprtext": "CPU SyntaxError fixture"}])
            return result
    provider = sources(CollectionFixture())
    case = provider.build_case("cal2-xmltodict-1")
    result = provider.assess_files(case["task_id"], case["files"], run_root=tmp_path / "assessment")
    assert result["executed"] is expected
    assert result["passed"] is False
    assert result["test_nodes_observed"] == 0
    assert result["all_expected_tests_observed"] is False
    assert result["observed_pass_fraction"] == (0.0 if candidate_bound else None)
    for row in result["independent_acceptance"]["checks"]:
        assert row["observed"]["node_outcome_observed"] is False
        assert row["observed"]["pytest_status"] == ("not_run_due_to_code_collection_failure" if candidate_bound else "missing")
        assert row["passed"] is (False if candidate_bound else None)
