"""Declarative build contracts; no trusted helper writes world state."""

import copy
import json
from pathlib import Path

import pytest

from proworksim.scenarios import (
    ScenarioController,
    build_scenario,
    initial_business_state,
    validate_scenario,
)

EXAMPLES = Path(__file__).parents[1] / "examples" / "scenarios-v10"


def spec(name="finance-direct"):
    return json.loads((EXAMPLES / (name + ".json")).read_text())


def test_same_spec_has_identical_initial_business_state(tmp_path):
    first = build_scenario(spec(), tmp_path / "first")
    second = build_scenario(spec(), tmp_path / "second")
    assert first.status == second.status == "ready"
    assert initial_business_state(first.world) == initial_business_state(second.world)
    assert first.world.state["instance_id"] != second.world.state["instance_id"]
    assert not first.world.state["releases"]
    assert all(not w["submissions"] for w in first.world.state["work_items"].values())


@pytest.mark.parametrize(
    "name",
    [
        "finance-direct",
        "finance-route",
        "report-direct",
        "chain-accepted",
        "chain-before-submit",
        "chain-pending",
        "report-pending-start",
    ],
)
def test_examples_deploy_without_historical_approvals(tmp_path, name):
    built = build_scenario(spec(name), tmp_path / name)
    assert built.status == "ready", built.diagnostics
    assert all(not w["submissions"] for w in built.world.state["work_items"].values())
    assert all(x["result"]["ok"] for x in built.deployment_log)


def test_route_changes_information_distribution_only(tmp_path):
    direct = build_scenario(spec(), tmp_path / "direct")
    routed = build_scenario(spec("finance-route"), tmp_path / "route")
    d = direct.world.session("analyst", "FINANCE").observe()
    r = routed.world.session("analyst", "FINANCE").observe()
    assert "statement" in d["workspaces"]["FINANCE"]
    assert "statement" not in r["workspaces"]["FINANCE"]
    assert r["information_routes"]
    assert not d["information_routes"]


def test_unresolved_cross_reference_is_unbuildable(tmp_path):
    broken = spec("chain-accepted")
    broken["projects"][1]["parameters"]["source_alias"] = "missing"
    built = build_scenario(broken, tmp_path / "bad")
    assert built.status == "unbuildable"
    assert "Unresolved" in built.diagnostics[0]
    assert not built.role_bindings()


def test_rejected_setup_is_not_silently_repaired(tmp_path):
    broken = spec()
    broken["setup"] = [
        {
            "actor": "reviewer",
            "project": "FINANCE",
            "tool": "write_object",
            "arguments": {"alias": "ledger", "data": {}},
        }
    ]
    built = build_scenario(broken, tmp_path / "bad")
    assert built.status == "unbuildable"
    assert built.deployment_log[-1]["result"]["ok"] is False
    assert (
        built.world.state["artifacts"][built.world.state["workspaces"]["FINANCE"]["ledger"]][
            "current_version"
        ]
        == "v1"
    )


def test_event_executes_only_declared_effect_once(tmp_path):
    declaration = spec()
    declaration["events"] = [
        {
            "event_id": "rename-source",
            "when": {"clock_at_least": 0},
            "fire_once": True,
            "effects": [
                {
                    "actor": "analyst",
                    "project": "FINANCE",
                    "tool": "write_object",
                    "arguments": {"alias": "ledger", "data": {"declared": "external replacement"}},
                }
            ],
        }
    ]
    built = build_scenario(declaration, tmp_path / "world")
    controller = ScenarioController(built)
    assert len(controller.tick()) == 1
    assert controller.tick() == []
    resumed = ScenarioController(built, controller.snapshot())
    assert resumed.tick() == []
    assert built.world.session("analyst", "FINANCE").call("read_object", alias="ledger")["result"][
        "data"
    ] == {"declared": "external replacement"}
    assert (
        controller.log[0]["effects"][0]["arguments"]
        == declaration["events"][0]["effects"][0]["arguments"]
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.update(evaluation_answer={}),
        lambda s: s["roles"].append(copy.deepcopy(s["roles"][0])),
        lambda s: s.update(
            events=[
                {
                    "event_id": "dynamic",
                    "when": {"evaluation_failed": True},
                    "fire_once": True,
                    "effects": [
                        {"actor": "analyst", "project": "FINANCE", "tool": "wait", "arguments": {}}
                    ],
                }
            ]
        ),
    ],
)
def test_unsupported_or_conflicting_spec_rejected(change):
    declaration = spec()
    change(declaration)
    with pytest.raises(ValueError):
        validate_scenario(declaration)


def test_pending_start_executes_real_prefix_and_keeps_experience(tmp_path):
    from proworksim.scenarios import bind_runtime, run_scenario
    from proworksim.storage import digest, json_bytes

    built = build_scenario(spec("report-pending-start"), tmp_path / "world")
    runtime = bind_runtime(built)
    prefix = built.prepare_start(runtime)
    assert prefix["prefix_executed"] and prefix["status"] == "reached"
    assert prefix["opportunities"]
    begin, end = prefix["experience_range"]
    assert prefix["experience_sha256"] == digest(json_bytes(runtime.recorder.events[begin:end]))
    assert any(
        e["kind"] == "tool_call" and e["payload"]["action"] == "submit"
        for e in runtime.recorder.events[begin:end]
    )
    before = copy.deepcopy(runtime.recorder.events)
    resumed = bind_runtime(built, checkpoint=prefix["worker_checkpoint"])
    result = run_scenario(built, resumed)
    assert result["status"] == "completed"
    assert result["experience"]["events"][: len(before)] == before


def test_untriggered_event_cannot_be_silently_ignored(tmp_path):
    from proworksim.scenarios import run_scenario

    declaration = spec("report-direct")
    declaration["events"] = [
        {
            "event_id": "future",
            "when": {"clock_at_least": 10000},
            "fire_once": True,
            "effects": [
                {"actor": "author", "project": "REPORT", "tool": "wait", "arguments": {"ticks": 1}}
            ],
        }
    ]
    built = build_scenario(declaration, tmp_path / "world")
    result = run_scenario(built)
    assert result["status"] == "worker_waiting"
    assert result["untriggered_events"] == ["future"]
    assert not result["controller"]["log"]
