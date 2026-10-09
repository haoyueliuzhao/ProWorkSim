"""Finite v039 world/control provenance checks; no model or business-quality claim."""
import copy
import json

import pytest

from proworksim.software_organization_v039 import (
    CASE_IDS, CONTROLLER_TOOL, DIAGNOSTIC_LIMITS, MEMBERS, PROJECT,
    SoftwareCollaborationPort, build_software_collaboration_case, case_spec,
    diagnostic_case_spec, material, member_instruction, validate_case,
)


def build(tmp_path, condition="X3"):
    return build_software_collaboration_case(case_spec(CASE_IDS[0], condition=condition), tmp_path / condition)


def admit_controller(world):
    world.model_budget_snapshot = lambda: {"decisions": 8, "remaining_decisions": 120,
        "remaining_attempts": 120, "available_tokens": 400000}
    world.external_birth_authorized = True


def test_a3_x3_public_instruction_tools_and_initial_observation_are_equal(tmp_path):
    a, x = build(tmp_path, "A3"), build(tmp_path, "X3")
    assert a.case != x.case and a.case["external_intervention"]["enabled"] is False
    assert x.case["external_intervention"]["after_completed_team_decisions"] == 8
    assert member_instruction(a.case) == member_instruction(x.case)
    ports = [SoftwareCollaborationPort(p.world.session(MEMBERS[0], PROJECT), MEMBERS[0]) for p in (a, x)]
    assert ports[0].tools() == ports[1].tools()
    values = [port.observe() for port in ports]
    for value in values:
        for key in ("instance_id", "branch_id"):
            value.pop(key)
        assert value["execution_condition"]["condition"] == "dynamic"
        assert '"X3"' not in json.dumps(value) and "after_completed_team_decisions" not in json.dumps(value)
    assert values[0] == values[1]
    assert CONTROLLER_TOOL not in {item["name"] for item in ports[0].tools()}
    assert a.world._software()["tasks"] == x.world._software()["tasks"] == {}


def test_external_birth_uses_operator_and_baseline_without_private_data_or_repeat(tmp_path):
    prepared = build(tmp_path)
    world = prepared.world
    path = next(p for p in prepared.case["editable_paths"] if p != "test_member.py")
    baseline = material(prepared.case["case_id"])["files"]
    assert world.session(MEMBERS[0], PROJECT).call("write_file", path=path,
        text=baseline[path] + "\n# Private parent change excluded from external initial copy\n")["ok"]
    admit_controller(world)
    denied = world.session(MEMBERS[0], PROJECT).call(CONTROLLER_TOOL, completed_team_decisions=8)
    assert denied["ok"] is False and denied["error"]["rejection"]["code"] == "controller_only"
    response = world.session("operator", PROJECT).call(CONTROLLER_TOOL, completed_team_decisions=8)
    assert response["ok"], response
    member = response["result"]["member_id"]
    record = world._software()["registry"][member]
    assert record["born_by"] == "operator" and record["origin"] == "external_controller"
    assert record["briefing"] == "" and record["model_generated_briefing"] is False
    assert world._bundle(member)[2]["files"] == baseline
    event = world.state["software_events"][-1]
    assert event["kind"] == "member_spawned" and event["actor_id"] == "operator"
    assert event["member_model_output_tokens"] == 0 and event["budget_reset"] is False
    assert event in world.reachable_events(MEMBERS[0], 0)
    repeated = world.session("operator", PROJECT).call(CONTROLLER_TOOL, completed_team_decisions=8)
    assert repeated["ok"] is False and len(world._software()["registry"]) == 3


def test_external_control_rejects_early_unadmitted_and_wrong_condition(tmp_path):
    for condition in ("A3", "X3"):
        prepared = build(tmp_path, condition)
        world = prepared.world
        admit_controller(world)
        if condition == "X3":
            world.external_birth_authorized = False
        assert world.session("operator", PROJECT).call(CONTROLLER_TOOL, completed_team_decisions=8)["ok"] is False
        world.external_birth_authorized = True
        assert world.session("operator", PROJECT).call(CONTROLLER_TOOL, completed_team_decisions=7)["ok"] is False
        assert len(world._software()["registry"]) == 2


def test_probe_setup_has_fixed_comment_then_distinct_private_version_and_retired_fixture(tmp_path):
    case = diagnostic_case_spec("replacement-patch")
    prepared = build_software_collaboration_case(case, tmp_path / "probe")
    world = prepared.world
    setup = world._software()["diagnostic_setup"]
    assert case["purpose"] == "interface_diagnostic" and case["team_limits"] == DIAGNOSTIC_LIMITS
    assert setup["model_calls"] == setup["generated_tokens"] == setup["test_runs"] == 0
    assert all(row["origin"] == "diagnostic_setup" and row["model_generated"] is False for row in setup["events"])
    assert all(row["fixture_session_actor"] == MEMBERS[1] for row in setup["calls"])
    assert world._software()["registry"][MEMBERS[1]]["status"] == "retired"
    assert world._software()["tasks"] == {} and world._software()["deliveries"] == []
    assert setup["patch_source_reference"] != setup["later_private_reference"]
    birth = world.session(MEMBERS[0], PROJECT).call("spawn_member", briefing="Read your exact copy and reply",
        patch_id="patch-1", replaces=MEMBERS[1])
    assert birth["ok"], birth
    child = birth["result"]["member_id"]
    content = world._bundle(child)[2]["files"][setup["path"]]
    assert setup["public_marker"] in content and setup["private_marker"] not in content
    assert birth["result"]["initial_source_reference"] == setup["patch_source_reference"]
    assert birth["result"]["origin"] == "member_request"
    assert world._software()["registry"][child].get("model_generated") is not False
    port = SoftwareCollaborationPort(world.session(child, PROJECT), child)
    assert setup["private_marker"] not in json.dumps(port.observe())


def test_v039_conditions_and_diagnostics_validate_without_old_aliases():
    for condition in ("F2", "A3", "X3"):
        value = case_spec(condition=condition)
        assert validate_case(value) == value
    for changed_key, changed_value in (("condition", "O3"), ("public_condition", "X3")):
        value = copy.deepcopy(case_spec(condition="X3"))
        value[changed_key] = changed_value
        with pytest.raises(ValueError):
            validate_case(value)
    altered = diagnostic_case_spec("birth-message")
    altered["team_limits"]["max_total_tokens"] = 500000
    with pytest.raises(ValueError):
        validate_case(altered)
