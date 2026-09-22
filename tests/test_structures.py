from dataclasses import replace

import pytest

from proworksim.baseline import run_baseline
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World
from proworksim.storage import digest
from proworksim.validation import evaluate
from proworksim.workflow import validate_workflow


@pytest.mark.parametrize(
    "topology,count", [("chain", 2), ("fork", 6), ("selective", 4), ("coordination", 2)]
)
@pytest.mark.parametrize("layout", ["standard", "shifted"])
def test_structural_witness_and_layout_invariance(tmp_path, topology, count, layout):
    root = compile_world(design(23, topology=topology, layout=layout), tmp_path / "world")
    world = World(root)
    assert run_baseline(world.session())["complete"]
    state = world.store.load()
    assert len(state["work_items"]) == count
    assert all(r["passed"] for r in evaluate(root))
    if topology == "fork":
        assert state["work_items"]["memo-1"]["dependencies"] == ["model-1"]
        assert state["work_items"]["note-1"]["dependencies"] == ["model-1"]
    if topology == "selective":
        assert len(state["artifacts"]["model"]["versions"]) == 2
        assert len(state["artifacts"]["memo"]["versions"]) == 2
        assert len(state["artifacts"]["note"]["versions"]) == 3
        assert state["artifacts"]["model"]["freshness"] == "current"
        assert state["artifacts"]["memo"]["freshness"] == "current"


def test_extra_stage_is_defined_in_spec_without_kernel_changes(tmp_path):
    spec = design(7, topology="selective")
    node = {
        **spec.workflow["nodes"][-1],
        "node_id": "note-3",
        "dependencies": ["note-2"],
        "release": "third",
        "requirement_version": 3,
    }
    flow = {
        **spec.workflow,
        "nodes": [*spec.workflow["nodes"], node],
        "event_rules": [
            *spec.workflow["event_rules"],
            {
                "rule_id": "third-brief",
                "after_accepted": ["note-2"],
                "effects": [{"kind": "revise_brief", "audience": "investment_committee"}],
                "release": "third",
                "delay": 2,
            },
        ],
    }
    root = compile_world(replace(spec, workflow=flow), tmp_path / "custom")
    world = World(root)
    assert run_baseline(world.session())["complete"]
    assert len(world.store.load()["work_items"]) == 5
    assert all(r["passed"] for r in evaluate(root))


def test_selective_invalidation_does_not_rewrite_unrelated_bytes(tmp_path):
    root = compile_world(design(6, topology="selective"), tmp_path / "selective")
    world = World(root)
    run_baseline(world.session())
    state = world.store.load()
    before = {
        a: digest(world.store.content(state["artifacts"][a])) for a in ("model", "memo", "note")
    }
    response = world.act(
        "client", "write_file", {"artifact_id": "brief", "content": '{"audience":"new_audience"}'}
    )
    assert response["ok"]
    after = world.store.load()
    assert after["artifacts"]["note"]["freshness"] == "stale"
    assert after["artifacts"]["model"]["freshness"] == "current"
    assert after["artifacts"]["memo"]["freshness"] == "current"
    assert before == {a: digest(world.store.content(after["artifacts"][a])) for a in before}


def test_invalid_workflow_dependencies_are_rejected():
    flow = design().workflow
    flow["nodes"][0]["dependencies"] = ["work-2"]
    with pytest.raises(ValueError, match="Cyclic"):
        validate_workflow(flow)
