"""Finite information/framing controls; real CPU checks, no model samples."""
import copy
import json

import pytest

from proworksim.software_organization_v040 import (
    CASE_IDS, CONDITIONS, MEMBERS, PROJECT, TEAM_FRAMING, SoftwareCollaborationPort,
    build_software_collaboration_case, case_spec, material, member_instruction, validate_case,
)
from proworksim.storage import digest, json_bytes


def test_conditions_change_only_initial_report_allocation_and_team_framing(tmp_path):
    prepared = [build_software_collaboration_case(case_spec(CASE_IDS[0], condition=condition), tmp_path / condition)
                for condition in CONDITIONS]
    instructions = [member_instruction(p.case) for p in prepared]
    assert instructions[0] == instructions[2]
    assert instructions[1] == instructions[3] == instructions[0] + "\n" + TEAM_FRAMING
    tools = []
    for p in prepared:
        facts = p.world._software()
        assert facts["tasks"] == {} and facts["deliveries"] == []
        assert p.case["member_limits"]["initial_members"] == 2
        assert p.case["member_limits"]["max_live_members"] == 4
        assert p.case["member_limits"]["max_cumulative_births"] == 6
        assert not p.case["external_intervention"]["enabled"]
        for member in MEMBERS[:2]:
            port = SoftwareCollaborationPort(p.world.session(member, PROJECT), member)
            observation = port.observe()
            tools.append(port.tools())
            reports = observation["initial_diagnostics"]
            assert len(reports) == (2 if p.case["information_condition"] == "shared" else 1)
            assert [r["diagnostic_id"] for r in reports] == facts["initial_diagnostic_assignments"][member]
            rendered = json.dumps(observation)
            assert "initial_diagnostic_assignments" not in rendered
            assert "diagnostic_a_owner" not in rendered and '"condition": "' + p.case["condition"] + '"' not in rendered
            for identifier in set(facts["initial_diagnostics"]) - set(facts["initial_diagnostic_assignments"][member]):
                assert identifier not in rendered
            assert p.world._bundle(member)[2]["files"] == material(CASE_IDS[0])["files"]
            for report in reports:
                assert report["initial_report"] is True
                assert report["files_sha256"] == digest(json_bytes(material(CASE_IDS[0])["files"]))
                assert report["source_reference"] == report["initial_source_reference"]
                assert report["origin"] == "environment_initial_diagnostic"
                assert report["model_generated"] is False and report["autonomous_discovery"] is False
        assert facts["environment_preparation_cost"]["team_run_tests_charged"] == 0
        assert facts["environment_preparation_cost"]["model_calls"] == 0
    assert all(value == tools[0] for value in tools)
    assert "controller_add_neutral_member" not in {tool["name"] for tool in tools[0]}


def test_either_member_can_reobtain_both_current_reports_and_child_has_no_initial_inheritance(tmp_path):
    p = build_software_collaboration_case(case_spec(CASE_IDS[0], condition="PB"), tmp_path / "case")
    world = p.world
    session = world.session(MEMBERS[1], PROJECT)
    initial = copy.deepcopy(world._software()["initial_diagnostics"])
    files = material(CASE_IDS[0])["files"]
    path = next(path for path in p.case["editable_paths"] if path != "test_member.py")
    assert session.call("write_file", path=path, text=files[path] + "\n# CPU current-version witness\n")["ok"]
    reply = session.call("run_tests")
    assert reply["ok"], reply
    current = reply["result"]["public_diagnostics"]
    assert {row["diagnostic_id"] for row in current.values()} == set(initial)
    for report in current.values():
        assert report["origin"] == "member_public_test_execution" and report["initial_report"] is False
        assert report["source_reference"] != initial[report["diagnostic_id"]]["source_reference"]
        assert report["files_sha256"] != initial[report["diagnostic_id"]]["files_sha256"]
    assert world._software()["initial_diagnostics"] == initial
    born = session.call("spawn_member", briefing="Only this parent-written briefing is transferred")
    assert born["ok"], born
    child = born["result"]["member_id"]
    observation = SoftwareCollaborationPort(world.session(child, PROJECT), child).observe()
    assert observation["initial_diagnostics"] == []
    assert all(identifier not in json.dumps(observation) for identifier in initial)
    denied = session.call("controller_add_neutral_member", completed_team_decisions=8)
    assert denied["ok"] is False and len(world._software()["registry"]) == 3


def test_case_contract_cannot_reintroduce_old_conditions_or_change_allocation():
    for condition in CONDITIONS:
        case = case_spec(condition=condition, first_member=MEMBERS[1], diagnostic_a_owner=MEMBERS[1])
        assert validate_case(case) == case
    with pytest.raises(ValueError):
        case_spec(condition="X3")
    case = case_spec()
    case["information_condition"] = "split"
    with pytest.raises(ValueError):
        validate_case(case)
