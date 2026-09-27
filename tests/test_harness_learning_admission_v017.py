"""Saved H1 metadata fixture admits migration, never an unmeasured pilot."""

import copy
import json
from pathlib import Path

import pytest

from proworksim.harness_learning_admission import validate_h2_launch
from proworksim.storage import json_bytes
from scripts.build_harness_learning_v017 import build_protocols
from scripts.build_harness_study_v016 import ref
from test_candidate_selection_v015 import guard


def test_migration_binds_actual_selection_and_pilot_waits(tmp_path):
    def save(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json_bytes(data))

    h1root = tmp_path / "h1"
    model = tmp_path / "base"
    model.mkdir()
    manifest = tmp_path / "weights.json"
    save(manifest, {"fixture": True})
    repo = Path(__file__).resolve().parents[1]
    h1 = json.loads((repo / "examples/harness-v17/h1-plan/h1-qwen35-9b.json").read_text())
    source = h1root / "launch-protocol.json"
    save(source, h1)
    save(
        h1root / "online/report.json",
        {
            "status": "complete",
            "actor_steps_total": 0,
            "critic_steps_total": 0,
            "windows": [{"evaluation_guard": guard()}],
        },
    )
    save(
        h1root / "resident/owner.json",
        {"base_identity": {"path": str(model), "manifest": ref(manifest)}},
    )
    choice = {
        "candidate_id": "qwen35-9b",
        "harness": "openhands_v16",
        "run_root": str(h1root),
        "protocol_ref": ref(source),
        "initial_actor_identity": {"adapter_sha256": "fixture-initial"},
    }
    chosen = {"status": "selected", "selected": choice}
    models = []
    for c in ("qwen35-9b", "qwen38-27b"):
        launch = tmp_path / f"{c}-launch.json"
        save(launch, {"exit_code": 0, "end": 1.0})
        models.append({"candidate_id": c, "ended": True, "references": {"launch": ref(launch)}})
    report = tmp_path / "report.json"
    save(report, {"selection": chosen, "models": models})
    selection = tmp_path / "selection.json"
    save(selection, {**chosen, "report_ref": ref(report)})
    migration, pilot = build_protocols(h1, "openhands_v16", ref(selection))
    args = {"model_path": model, "weight_manifest": manifest}
    assert (
        validate_h2_launch(migration, **args)["expected_initial_adapter_sha256"]
        == "fixture-initial"
    )
    with pytest.raises(ValueError, match="waits for an actual"):
        validate_h2_launch(pilot, **args)
    bad = copy.deepcopy(migration)
    bad["windows"][0]["slots"][0]["pool"] = "locked"
    with pytest.raises(ValueError, match="worlds or budgets differ"):
        validate_h2_launch(bad, **args)
    with pytest.raises(ValueError, match="fresh after migration"):
        validate_h2_launch(migration, **args, restore_checkpoint="old")
