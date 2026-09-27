"""Saved-record arithmetic fixture, not model learning evidence."""

import json

import pytest

from scripts.harness_learning_report_v017 import build_report


def test_final_missing_is_not_zero_or_a_learning_delta(tmp_path):
    def save(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    spec = {
        "slot_id": "test",
        "case_id": "uci-locked-f0-implement",
        "sampling_seed": 37,
        "task": "implement",
    }
    protocol = {
        "stage": "H2",
        "experiment_id": "h2-pilot-v017",
        "candidate_id": "fixture",
        "harness": "native_v15",
        "selection": {},
        "windows": [
            {"window_id": phase, "phase": phase, "mode": "evaluate", "slots": [spec]}
            for phase in ("initial", "final")
        ],
    }
    save(tmp_path / "launch-protocol.json", protocol)
    save(tmp_path / "online/report.json", {"status": "running", "windows": []})
    save(tmp_path / "online/window-0/collection/slot-0/episode/manifest.json", {"status": "closed"})
    save(
        tmp_path / "online/window-0/collection/summary.json",
        {
            "slots": [
                {"slot_id": "test", "reward": {"eligible": True, "reward": 0.5, "completed": False}}
            ]
        },
    )
    report = build_report(tmp_path)
    assert report["windows"][0]["metrics"]["mean_reward"] == 0.5
    assert report["windows"][1]["metrics"]["states"] == {"not_started": 1}
    assert report["windows"][1]["metrics"]["mean_reward"] is None
    assert report["fixed_harness_learning_delta"] is None
    save(tmp_path / "online/window-1/collection/slot-0/episode/manifest.json", {"status": "closed"})
    save(
        tmp_path / "online/window-1/collection/summary.json",
        {
            "slots": [
                {
                    "slot_id": "test",
                    "reward": {"eligible": False, "reward": None, "completed": False},
                }
            ]
        },
    )
    assert build_report(tmp_path)["windows"][1]["metrics"]["states"] == {"closed_unknown": 1}
    save(
        tmp_path / "online/window-1/collection/summary.json",
        {
            "slots": [
                {"slot_id": "test", "reward": {"eligible": True, "reward": 1, "completed": True}}
            ]
        },
    )
    assert (
        build_report(tmp_path)["fixed_harness_learning_delta"] is None
    )  # guard/complete evidence still missing
    save(
        tmp_path / "online/report.json",
        {
            "status": "complete",
            "windows": [
                {
                    "window_id": phase,
                    "status": "complete",
                    "evaluation_guard": {"learning_unchanged": True, "rng_restored_exactly": True},
                }
                for phase in ("initial", "final")
            ],
        },
    )
    save(tmp_path / "source-comparison.json", {"unchanged": True})
    assert build_report(tmp_path)["fixed_harness_learning_delta"]["mean_reward"] == 0.5
    protocol["windows"][1]["slots"] = [{**spec, "sampling_seed": 38}]
    save(tmp_path / "launch-protocol.json", protocol)
    with pytest.raises(ValueError, match="inventory differs"):
        build_report(tmp_path)
