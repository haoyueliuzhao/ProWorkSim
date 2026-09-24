"""P0 guards nested JSON types and genuine ordered multi-file submission paths."""

import importlib
from itertools import permutations
from pathlib import Path

import pytest

from proworksim.domains.work_product import _equal, _merge_json


@pytest.mark.parametrize(
    "left,right,expected",
    [
        ({"margin": True}, {"margin": 1}, False),
        ({"margin": False}, {"margin": 0}, False),
        ({"margin": {"nested": [True]}}, {"margin": {"nested": [1]}}, False),
        ([{"value": False}], [{"value": 0.0}], False),
        ({"margin": 1}, {"margin": 1.0}, True),
        ([{"values": [1, 2]}], [{"values": [1.0, 2.0]}], True),
        ({"a": 1, "b": 2}, {"b": 2.0, "a": 1.0}, True),
        ([1, 2], [2, 1], False),
        ([1], [1, 1], False),
        ({"a": 1}, {"a": 1, "b": 2}, False),
        ({"a": None}, {"a": None}, True),
        ({"a": float("inf")}, {"a": float("inf")}, False),
        ({"a": "1"}, {"a": 1}, False),
    ],
)
def test_json_equality_truth_at_every_depth(left, right, expected):
    assert _equal(left, right) is expected
    assert _equal(right, left) is expected


def test_all_orders_keep_conflict_even_if_third_file_repeats_a_value():
    documents = [
        {"metrics": {"margin": True}},
        {"metrics": {"margin": 1}},
        {"metrics": {"margin": True}, "note": "separate"},
    ]
    for sequence in permutations(documents):
        data, conflicts = _merge_json(sequence)
        assert conflicts == {"metrics"}
        assert data == {"note": "separate"}


def test_nested_objects_are_whole_fields_and_are_not_deep_merged():
    data, conflicts = _merge_json([{"metrics": {"a": 1}}, {"metrics": {"b": 2}}])
    assert data == {}
    assert conflicts == {"metrics"}
    assert _merge_json([{"a": 1}, {"b": 2}]) == ({"a": 1, "b": 2}, set())


def test_p0_real_sessions_use_explicit_truth_and_preserve_fixed_bindings(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    experiment = importlib.import_module("json_conflict_experiment")
    result = experiment.run_experiment(tmp_path / "p0", workers=2)
    assert result["passed"], [
        {
            "case": branch["case"],
            "error": branch["error"],
            "failed": [check for check in branch["checks"] if not check["passed"]],
        }
        for branch in result["branches"]
        if not branch["passed"]
    ]
    assert result["not_executed_count"] == 0
    assert result["check_pass_count"] == result["check_count"]
    for branch in result["branches"]:
        evaluation = branch["evaluation"]
        assert evaluation["evaluator_version"] == "finite-products-v0.11"
        if experiment.CASES[branch["case"]]["conflicts"]:
            assert evaluation["checks"][0]["reason"] == "Conflicting JSON fields: metrics"
            assert "actual" not in evaluation["checks"][0]
