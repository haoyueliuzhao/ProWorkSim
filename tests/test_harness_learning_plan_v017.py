"""Frozen counts/splits protect the finite direct-learning comparison."""

from pathlib import Path
import json

from scripts.build_harness_learning_v017 import build_protocols


def test_training_probe_and_locked_budgets_are_separate_and_fixed():
    root = Path(__file__).resolve().parents[1]
    h1 = json.loads((root / "examples/harness-v17/h1-plan/h1-qwen35-9b.json").read_text())
    migration, pilot = build_protocols(
        h1, "openhands_v16", {"path": "fixture-selection", "sha256": "fixture"}
    )
    assert [len(w["slots"]) for w in migration["windows"]] == [4, 4]
    assert [len(w["slots"]) for w in pilot["windows"]] == [24, 16, 16, 16, 16, 24]
    assert pilot["runtime"] == h1["runtime"]
    assert pilot["recipe"]["lora"] == h1["recipe"]["lora"]
    assert pilot["recipe"]["credit_assignment"] == "terminal_mc"
    for protocol in (migration, pilot):
        for w in protocol["windows"]:
            assert w["harness"] == "openhands_v16"
            if w["mode"] == "online":
                assert {s["pool"] for s in w["slots"]} == {"train"}
    start, end = pilot["windows"][0], pilot["windows"][-1]
    assert {(s["case_id"], s["sampling_seed"]) for s in start["slots"]} == {
        (s["case_id"], s["sampling_seed"]) for s in end["slots"]
    }
    assert {s["pool"] for s in start["slots"]} == {"locked"}
    assert pilot["launch_gate"]["state"] == "awaiting_actual_migration"
    assert pilot["initialization"]["restore_checkpoint_permitted"] is False
