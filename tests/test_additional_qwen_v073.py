from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_candidates_v054 import write_new

FILE = Path(__file__).resolve().parents[1] / "tools/launch_additional_qwen_v073.py"
spec = importlib.util.spec_from_file_location("additional_qwen_v073", FILE)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def card(index):
    return {"gpu_index": index, "gpu_uuid": f"GPU-0000000{index}-0000-0000-0000-000000000000", "free_mib": 81152}


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    source = tmp_path / "original-auth.json"
    source.write_text("{}")
    monkeypatch.setattr(launcher, "OUT", tmp_path / "new")
    monkeypatch.setattr(launcher, "AUTH", tmp_path / "new/authorization.json")
    monkeypatch.setattr(launcher, "ordinary_user", lambda: None)
    monkeypatch.setattr(launcher.policy, "AUTHORIZATION_FILE", source)
    monkeypatch.setattr(launcher.policy, "require_v066_allowed", lambda *_: None)
    monkeypatch.setattr(launcher.resident, "RUNS", runs)
    cards, made, launched = [], [], []
    active = [{"index": 1, **card(2)}, {"index": 3, **card(4)}]
    def unused(index):
        return not (runs / f"model-{index}").exists()
    base = SimpleNamespace(active_original_residents=lambda: list(active),
                           validate_active=lambda values: launcher.original_launcher_original_validate(values),
                           unused_identity=unused)
    validator = launcher.original_launcher().validate_active
    monkeypatch.setattr(launcher, "original_launcher_original_validate", validator, raising=False)
    monkeypatch.setattr(launcher, "original_launcher", lambda: base)
    monkeypatch.setattr(launcher.resident, "gpu_capacity", lambda: list(cards))
    monkeypatch.setattr(launcher.resident, "shared_capacity_for", lambda count: count == 1)
    def make(index, selected):
        made.append(index)
        folder = runs / f"model-{index}"
        folder.mkdir()
        value = {"index": index, "root": str(folder), "unit": f"fixture-{index}", **selected}
        write_new(folder / "spec.json", value)
        active.append(value)
        return value
    monkeypatch.setattr(launcher.resident, "make_spec", make)
    monkeypatch.setattr(launcher.resident, "unit_command", lambda value: ["fixture", str(value["index"])])
    monkeypatch.setattr(launcher.resident, "user_manager_environment", lambda: {})
    monkeypatch.setattr(launcher.subprocess, "run", lambda command, **_: (
        launched.append(command) or SimpleNamespace(returncode=0, stdout="", stderr="")))
    return SimpleNamespace(cards=cards, made=made, launched=launched, active=active, runs=runs)


def test_prepare_needs_no_GPU_and_one_card_starts_one_identity(fixture, monkeypatch):
    monkeypatch.setattr(launcher.resident, "gpu_capacity", lambda: pytest.fail("prepare must not query GPUs"))
    assert launcher.prepare()["GPU_queries"] == 0
    monkeypatch.setattr(launcher.resident, "gpu_capacity", lambda: list(fixture.cards))
    fixture.cards.append(card(7))
    result = launcher.launch()
    assert result["residents"]["4"]["status"] == "launch_requested"
    assert result["residents"]["5"]["status"] == "waiting_for_capacity"
    assert result["residents"]["5"]["identity_unconsumed"] is True
    assert fixture.made == [4] and len(fixture.launched) == 1


def test_two_cards_not_reused_and_consumed_identity_never_restarts(fixture):
    launcher.prepare()
    fixture.cards.extend([card(0), card(7)])
    result = launcher.launch()
    assert [result["residents"][str(i)]["actual_gpu_index"] for i in (4, 5)] == [7, 0]
    assert len(fixture.active) == 4 and fixture.made == [4, 5]
    assert all(v["status"] == "identity_already_consumed_no_replay" for v in launcher.launch()["residents"].values())
    assert len(fixture.launched) == 2


def test_shared_capacity_refusal_does_not_consume_identity(fixture, monkeypatch):
    launcher.prepare()
    fixture.cards.append(card(7))
    monkeypatch.setattr(launcher.resident, "shared_capacity_for", lambda count: False)
    result = launcher.launch()
    assert all(v["status"] == "waiting_for_capacity" and v["identity_unconsumed"] for v in result["residents"].values())
    assert fixture.made == fixture.launched == []


def test_authority_and_allowed_GPU_boundaries(fixture):
    launcher.prepare()
    assert launcher.choose_card([card(8), {**card(7), "free_mib": 1}, card(2)], fixture.active) is None
    value = json.loads(launcher.AUTH.read_bytes())
    value["maximum_live_residents"] = 5
    launcher.AUTH.write_text(json.dumps(value))
    assert all(v["status"] == "launch_blocked" for v in launcher.launch()["residents"].values())
    assert fixture.made == fixture.launched == []
