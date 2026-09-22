"""The independent oracle must remain capable of detecting a permissive UUT."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("bounded_state_experiment")


def test_reference_rejects_reapproval_without_calling_uut(experiment, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Reference called the implementation under test")

    monkeypatch.setattr(experiment.work, "approve_submission", forbidden)
    monkeypatch.setattr(experiment.work, "current_id", forbidden)
    monkeypatch.setattr(experiment.conditions, "match_response", forbidden)
    ledger = experiment.Ledger()
    assert ledger.apply(("submit", "A", 1, "owner", 1, "valid")) == "allowed"
    assert ledger.apply(("approve", "A", 1, "reviewer", 1, "valid")) == "allowed"
    assert ledger.apply(("approve", "A", 1, "reviewer", 1, "valid")) == "not_pending"
    assert ledger.apply(("submit", "B", 1, "owner", 1, "valid")) == "allowed"
    assert ledger.apply(("revise", "A", 1, "reviewer", 0, "valid")) == "allowed"
    assert ledger.apply(("approve", "B", 1, "reviewer", 1, "valid")) == "dependencies"


def test_bfs_returns_shortest_wrong_actor_counterexample(experiment, monkeypatch):
    original = experiment.work.submit_work

    def ignore_actor(state, actor, work_item_id, *args, **kwargs):
        return original(state, "owner", work_item_id, *args, **kwargs)

    monkeypatch.setattr(experiment.work, "submit_work", ignore_actor)
    result = experiment.explore(2)
    assert not result["passed"]
    example = result["shortest_counterexample"]
    assert len(example["sequence"]) == 1
    assert example["expected"] == "authority"
    assert example["observed"] == "allowed"


def test_bounded_protocol_rejects_unfrozen_expansion(experiment):
    with pytest.raises(ValueError, match="depth 1..4"):
        experiment.explore(6)
