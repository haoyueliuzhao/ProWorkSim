"""A missing approval is not an undisclosed numerical target for the worker."""

import copy

from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World
from proworksim.storage import read_json
from proworksim.validation import evaluate_submission


def test_unavailable_basis_does_not_grade_hidden_assumptions(tmp_path, monkeypatch):
    world = World(
        compile_world(design(743, scenario="unavailable"), tmp_path / "world")
    )
    submission = world.session().call("submit", work_item_id="work-1")
    assert submission["ok"]
    state = world.store.load()
    spec = read_json(world.store.control / "spec.json")
    item = state["work_items"]["work-1"]

    def forbidden_scope(*args, **kwargs):
        raise AssertionError("No hidden scope may stand in for a missing approved basis")

    monkeypatch.setattr("proworksim.validation.scope", forbidden_scope)
    record = evaluate_submission(world.store, state, spec, item, item["submissions"][0])
    assert not record["artifact_valid"]
    assert record["numerical_assessment"] == "blocked_missing_approved_basis"
    failed = {c["name"] for c in record["checks"] if not c["passed"]}
    assert {"approved_basis_applicable", "model_basis_binding"} <= failed
    assert not any(
        c["category"] in {"calculation", "scenario", "recalculability"} for c in record["checks"]
    )
    assert {c["name"] for c in record["checks"] if c["category"] == "inputs"} == {
        "input:revenue",
        "input:operating_margin",
    }
    skipped = {c["name"] for c in record["unassessed_checks"]}
    assert {"input:growth", "output:share_price", "scenario:B2", "recomputation_probe:0"} <= skipped
    assert not record["propagated_failures"]
    assert record["evaluator_version"] == "operating-world-v0.5"


def test_approved_basis_still_supplies_independent_numerical_targets(tmp_path, monkeypatch):
    world = World(compile_world(design(743, delivery="file"), tmp_path / "world"))
    submission = world.session().call("submit", work_item_id="work-1")
    assert submission["ok"]
    state = world.store.load()
    spec = read_json(world.store.control / "spec.json")
    item = state["work_items"]["work-1"]

    def forbidden_scope(*args, **kwargs):
        raise AssertionError("Approved basis must supply the numerical target")

    monkeypatch.setattr("proworksim.validation.scope", forbidden_scope)
    record = evaluate_submission(
        world.store, state, copy.deepcopy(spec), item, item["submissions"][0]
    )
    assert record["numerical_assessment"] == "available"
    assert not record["unassessed_checks"]
    assert any(c["name"] == "input:growth" and not c["passed"] for c in record["checks"])
    assert any(c["name"] == "output:share_price" for c in record["checks"])
    assert not record["passed"]
