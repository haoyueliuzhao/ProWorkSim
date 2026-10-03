"""New-source qualification only: CPU controls, never current-policy support."""
import copy
from pathlib import Path

import pytest

from proworksim import software_tasks_v028 as source
from proworksim.episode import begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.software_collaboration_v029 import (
    CASE_IDS, MEMBERS, PROJECT, SoftwareCollaborationPort,
    assess_files, assess_software_collaboration, build_software_collaboration_case,
    case_spec, validate_case,
)
from proworksim.storage import atomic_write, json_bytes


def checked(port, tool, **arguments):
    response = port.call(tool, **arguments)
    assert response["ok"], response
    return response["result"]


def setup(root, task_id=CASE_IDS[0]):
    prepared = build_software_collaboration_case(case_spec(task_id), root)
    return prepared, *(SoftwareCollaborationPort(prepared.world.session(member, PROJECT), member) for member in MEMBERS)


def control_world(root, task_id, variant):
    """Retain actual WorldCore/captures for three frozen-source CPU controls."""
    root = Path(root)
    prepared, *raw_ports = setup(root / "case", task_id)
    captures = {member: [] for member in MEMBERS}
    a, b = [capture_port(port, captures[member]) for member, port in zip(MEMBERS, raw_ports, strict=True)]
    recorder = ExperienceRecorder()
    begin_episode(prepared.world, root / "episode", experience=recorder.snapshot(), work_ids=[],
                  scenario={"variation": {"software_case": prepared.case}},
                  policies={member: {"origin": "rule", "purpose": "CPU_source_contract_control"} for member in MEMBERS})
    for port in (a, b):
        port.tools()
        port.observe()
    checked(a, "claim_task", task_id="library_repair")
    checked(b, "claim_task", task_id="consumer_export")
    initial = source.build_case(task_id)["files"]
    joint = source.reference_solution(task_id)
    if variant in {"joint", "library_only"}:
        for path in prepared.case["editable_paths"]:
            if path != "consumer.py" and initial[path] != joint[path]:
                checked(a, "write_file", path=path, text=joint[path])
        fixed = checked(a, "fix_patch", task_ids=["library_repair"], message="CPU source repair control")
        checked(b, "declare_dependency", task_id="consumer_export", depends_on="library_repair")
        checked(b, "integrate_patch", patch_id=fixed["patch_id"])
    if variant in {"joint", "consumer_only"}:
        checked(b, "write_file", path="consumer.py", text=joint["consumer.py"])
    checked(b, "run_tests")
    checked(b, "fix_patch", task_ids=["consumer_export"], message="CPU fixed combined tree control")
    delivery = checked(b, "submit_integration", message="Explicit CPU program witness; not model experience")
    finish_episode(prepared.world, root / "episode", experience=recorder.snapshot(),
                   termination={"status": "CPU_source_contract_control_complete"})
    assessment = assess_software_collaboration(prepared, run_root=root / "assessment-execution")
    for key in ("independent_acceptance", "api_acceptance", "regression_acceptance", "consumer_api_observation"):
        assert assessment[key]["source_reference"] == delivery["source_reference"]
        assert assessment[key]["files_sha256"] == delivery["files_sha256"]
    record = {"kind": "CPU_rule_control", "current_policy_trajectory": False,
              "task_id": task_id, "variant": variant, "assessment": assessment,
              "model_calls": 0, "training_support": False}
    atomic_write(root / "control.json", json_bytes(record))
    atomic_write(root / "captures.json", json_bytes(captures))
    return prepared, record


@pytest.mark.parametrize("task_id", CASE_IDS)
@pytest.mark.parametrize("variant", ["joint", "library_only", "consumer_only"])
def test_complete_delivery_requires_library_consumer_and_regression(tmp_path, task_id, variant):
    prepared, record = control_world(tmp_path / variant, task_id, variant)
    result = record["assessment"]
    assert result["status"] == "evaluable" and result["submitted"]
    assert result["R"] == int(variant == "joint")
    assert result["components"]["selected_upstream_regressions"] == (variant != "consumer_only")
    assert result["components"]["independent_source_and_consumer_api"] == (variant == "joint")
    assert result["components"]["consumer_api_calls_observed"] == (variant == "joint")
    assert record["current_policy_trajectory"] is False
    assert prepared.case["training_eligible"] == (task_id == CASE_IDS[0])


def test_frozen_source_purpose_hashes_and_editable_contract(tmp_path):
    prepared, a, b = setup(tmp_path / "case")
    observed = a.observe()
    assert observed["editable_paths"] == source.build_case(CASE_IDS[0])["editable_paths"]
    assert all(task["owner"] is None for task in observed["tasks"].values())
    assert "acceptance.json" not in {row["path"] for row in checked(a, "list_files")["files"]}
    assert not a.call("write_file", path="contract.md", text="New easier contract")["ok"]
    assert not a.call("write_file", path="test_visible.py", text="print('pass')")["ok"]
    assert not a.call("write_file", path="acceptance.json", text="{}")["ok"]
    assert not b.call("diff_workspace", source_reference=a.observe()["workspace_reference"])["ok"]
    for key, value in (("purpose", "contribution_development"), ("training_eligible", False)):
        tampered = copy.deepcopy(prepared.case)
        tampered[key] = value
        with pytest.raises(ValueError, match="source/purpose"):
            validate_case(tampered)
    tampered = copy.deepcopy(prepared.case)
    tampered["source_contract"]["upstream_commit"] = "unfrozen-revision"
    with pytest.raises(ValueError, match="source/purpose"):
        validate_case(tampered)
    assert [case_spec(task)["purpose"] for task in CASE_IDS] == [
        "policy_training", "contribution_development", "independent_confirmation"]


def test_actual_api_call_probe_rejects_a_second_parser_even_if_finite_outputs_match(tmp_path):
    files = source.reference_solution(CASE_IDS[0])
    files["consumer.py"] = (
        "import re\n"
        "def comparison_records(expressions):\n"
        "    rows = []\n"
        "    for expression in expressions:\n"
        "        left, right = re.split(r'\\s*(?:!=|>=|<=|=|>|<)\\s*', expression, maxsplit=1)\n"
        "        rows.append({'left': left, 'right': right})\n"
        "    return rows\n")
    result = assess_files(CASE_IDS[0], files, run_root=tmp_path)
    assert result["api_acceptance"]["passed"]
    assert result["regression_acceptance"]["passed"]
    assert not result["consumer_api_observation"]["passed"]
    assert not result["passed"]
    assert all(not row["api_calls_observed"] for row in result["consumer_api_observation"]["checks"])


def test_fixed_versions_three_way_conflicts_and_paged_diff_are_preserved(tmp_path):
    prepared, a, b = setup(tmp_path / "case")
    checked(a, "claim_task", task_id="library_repair")
    checked(b, "claim_task", task_id="consumer_export")
    old = prepared.world._bundle(MEMBERS[0])[2]["files"]["consumer.py"]
    checked(a, "write_file", path="consumer.py", text="from_a = 1\n" + "# a\n" * 2000)
    fixed = checked(a, "fix_patch", task_ids=["library_repair"], message="Fixed public source")
    first = checked(b, "diff_workspace", source_reference=fixed["source_reference"])
    assert first["has_more"]
    checked(a, "write_file", path="consumer.py", text="later_private = True\n")
    assert not b.call("diff_workspace", source_reference=a.observe()["workspace_reference"])["ok"]
    second = checked(b, "diff_workspace", offset=first["next_offset"], source_reference=fixed["source_reference"])
    assert second["diff_sha256"] == first["diff_sha256"]
    assert "later_private" not in second["diff"]
    checked(b, "write_file", path="consumer.py", text="from_b = 2\n")
    merged = checked(b, "integrate_patch", patch_id=fixed["patch_id"])
    assert merged["conflicts"] == ["consumer.py"]
    assert "<<<<<<< working-copy" in prepared.world._bundle(MEMBERS[1])[2]["files"]["consumer.py"]
    assert prepared.world._bundle(MEMBERS[1], baseline=True)[2]["files"]["consumer.py"] == old
    assert assess_software_collaboration(prepared, run_root=tmp_path / "none")["R"] == 0
    assert not b.call("submit_integration", message="No test or current fixed patch")["ok"]
