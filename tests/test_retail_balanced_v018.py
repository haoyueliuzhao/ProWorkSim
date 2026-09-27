"""The revised design crosses actual quality, not just case-number spelling."""

import pytest
from proworksim.harness_learning_admission import validate_h2_launch
from collections import Counter
import json
from pathlib import Path

from proworksim.templates.retail_balanced import QUALITIES, registry, resolve
from scripts.build_harness_learning_v018 import build_protocols, support_protocol


def test_crossed_catalog_and_fixed_training_evaluation_density():
    catalog = registry()["situations"]
    assert len(catalog) == 54 and len({c["case_id"] for c in catalog}) == 54
    for pool in ("train", "development", "locked"):
        for fact in range(3):
            rows = [
                c
                for c in catalog
                if c["pool"] == pool and c["fact_position"] == fact and c["task"] == "review"
            ]
            assert {c["prepared_submission"] for c in rows} == set(QUALITIES)
            assert len({json.dumps(c["business_facts"], sort_keys=True) for c in rows}) == 1
            assert len({c["slice_id"] for c in rows}) == 1
            assert all("wrong" not in c["case_id"] and "correct" not in c["case_id"] for c in rows)
    h1 = json.loads(
        (
            Path(__file__).resolve().parents[1] / "examples/harness-v17/h1-plan/h1-qwen35-9b.json"
        ).read_text()
    )
    migration, pilot = build_protocols(h1, "native_v15", {"fixture": True})
    assert [len(w["slots"]) for w in pilot["windows"]] == [27, 16, 16, 16, 16, 27]
    assert [len(w["slots"]) for w in migration["windows"]] == [4, 4]
    assert pilot["primary_evaluation"]["task_weights"] == dict.fromkeys(
        ("implement", "review", "pair", "chain"), 0.25
    )
    reviews = Counter()
    for w in pilot["windows"][1:5]:
        assert Counter(s["task"] for s in w["slots"]) == dict.fromkeys(
            ("implement", "review", "pair", "chain"), 4
        )
        assert max(Counter(s["case_id"] for s in w["slots"]).values()) <= 2
        for s in w["slots"]:
            if s["task"] == "review":
                reviews[s["case_id"]] += 1
    assert set(reviews) == {
        resolve("train", f, "review", q)["case_id"] for f in range(3) for q in QUALITIES
    }
    start, end = pilot["windows"][0], pilot["windows"][-1]
    assert {(s["case_id"], s["sampling_seed"]) for s in start["slots"]} == {
        (s["case_id"], s["sampling_seed"]) for s in end["slots"]
    }
    assert Counter(s["task"] for s in start["slots"]) == {
        "implement": 6,
        "review": 9,
        "pair": 6,
        "chain": 6,
    }
    density = support_protocol(h1, "native_v15", {"fixture": True})
    assert len(density["windows"]) == 1 and density["windows"][0]["mode"] == "evaluate"
    assert sorted(Counter(s["case_id"] for s in density["windows"][0]["slots"]).values()) == [8, 8]
    assert density["method_support_density"]["auto_O4"] is False
    assert pilot["method_support_density"]["composition_degrees_of_freedom"] == 0


def test_density_plan_cannot_accidentally_use_fresh_unupdated_base():
    with pytest.raises(ValueError, match="completed pilot"):
        validate_h2_launch(
            {
                "stage": "ID_support_v018",
                "launch_gate": {"state": "awaiting_completed_pilot_final_checkpoint"},
            },
            model_path="not-loaded",
            weight_manifest="not-read",
        )
