from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_candidates_v054 import write_new

FILE = Path(__file__).resolve().parents[1] / "tools/launch_additional_qwen_v071.py"
spec = importlib.util.spec_from_file_location("additional_qwen_v071", FILE)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root, runs = tmp_path / "physical", tmp_path / "residents"
    runs.mkdir()
    root.mkdir()
    (root / "authorization.json").write_text("{}")
    monkeypatch.setattr(launcher, "OUT", tmp_path / "new-grants")
    monkeypatch.setattr(launcher, "ordinary_user", lambda: None)
    monkeypatch.setattr(launcher.policy, "BATCH_ROOT", root)
    monkeypatch.setattr(launcher.policy, "AUTHORIZATION_FILE", root / "authorization.json")
    monkeypatch.setattr(launcher.policy, "require_v066_allowed", lambda *_: None)
    monkeypatch.setattr(launcher.resident, "RUNS", runs)
    cards = [{**card, "free_mib": 70000} for card in launcher.TARGETS.values()]
    made, launched = [], []
    for index in (1, 3):
        folder = runs / f"model-{index}"
        folder.mkdir()
        write_new(folder / "spec.json", {"index": index, "gpu_uuid": f"baseline-{index}", "root": str(folder)})
    def active():
        return [json.loads(path.read_bytes()) for path in sorted(runs.glob("model-*/spec.json"))]
    monkeypatch.setattr(launcher, "active_original_residents", active)
    monkeypatch.setattr(launcher.resident, "gpu_capacity", lambda: list(cards))
    monkeypatch.setattr(launcher.resident, "shared_capacity_for", lambda count: count == 1)
    def make_spec(index, card):
        made.append(index)
        folder = runs / f"model-{index}"
        folder.mkdir()
        value = {"index": index, "root": str(folder), "unit": f"fixture-model-{index}", **card}
        write_new(folder / "spec.json", value)
        return value
    monkeypatch.setattr(launcher.resident, "make_spec", make_spec)
    monkeypatch.setattr(launcher.resident, "unit_command", lambda value: ["fixture-service", str(value["index"])])
    monkeypatch.setattr(launcher.resident, "user_manager_environment", lambda: {})
    def start(command, **_):
        launched.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(launcher.subprocess, "run", start)
    return SimpleNamespace(root=root, runs=runs, cards=cards, made=made, launched=launched, active=active)


def test_prepare_only_seals_two_exact_grants_preserving_original_arguments(fixture):
    value = launcher.prepare()
    assert value["services_started"] == value["resource_reservations_created"] == 0
    assert fixture.made == fixture.launched == []
    assert {int(index) for index in value["residents"]} == {4, 5}
    for index in (4, 5):
        grant = launcher.policy.load(value["residents"][str(index)]["authorization"])
        assert grant["gpu_uuid"] == launcher.TARGETS[index]["gpu_uuid"]
        assert grant["original_server_arguments"] == launcher.resident.server_arguments(launcher.resident.PORTS[index])
        assert grant["memory_GiB"] == 96 and grant["CPU"] == 12
        assert grant["original_model_context"] == 131072 and grant["original_output_limit"] == 32768
        assert grant["maximum_live_residents"] == 4 and grant["gpu_memory_utilization"] == 0.6


def test_missing_first_card_still_launches_second_and_can_later_try_unused_first(fixture):
    launcher.prepare()
    first_card = fixture.cards.pop(0)
    initial = {i: (fixture.runs / f"model-{i}/spec.json").read_bytes() for i in (1, 3)}
    result = launcher.launch()
    assert result["residents"]["4"]["status"] == "waiting_for_capacity"
    assert result["residents"]["4"]["identity_unconsumed"] is True
    assert result["residents"]["5"]["status"] == "launch_requested"
    fixture.cards.append(first_card)
    assert launcher.launch([4])["residents"]["4"]["status"] == "launch_requested"
    assert fixture.made == [5, 4] and len(fixture.active()) == 4
    assert launcher.launch()["residents"]["4"]["status"] == "identity_already_consumed_no_replay"
    assert len(fixture.launched) == 2
    for index, original in initial.items():
        assert (fixture.runs / f"model-{index}/spec.json").read_bytes() == original


def test_failed_second_launch_preserves_success_and_consumed_identity(fixture, monkeypatch):
    launcher.prepare()
    def start(command, **_):
        fixture.launched.append(command)
        if command[-1] == "5":
            raise TimeoutError("fixture ambiguous service acknowledgment")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(launcher.subprocess, "run", start)
    result = launcher.launch()
    assert result["residents"]["4"]["status"] == "launch_requested"
    assert result["residents"]["5"]["status"] == "launch_outcome_unknown_identity_consumed"
    assert result["successful_launch_rollback"] is False
    assert launcher.launch([5])["residents"]["5"]["status"] == "identity_already_consumed_no_replay"
    assert fixture.made == [4, 5] and len(fixture.launched) == 2


def test_unproven_prior_cleanup_blocks_without_consuming_new_identity(fixture, monkeypatch):
    baseline = fixture.active()
    monkeypatch.setattr(launcher, "active_original_residents", lambda: [*baseline, {"index": 2, "gpu_uuid": "unproven-exit"}])
    with pytest.raises(ValueError, match="Unproven predecessor cleanup"):
        launcher.prepare()
    assert fixture.made == fixture.launched == []
