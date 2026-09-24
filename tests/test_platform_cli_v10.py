"""The declared platform is usable without a business-specific experiment driver."""

import json
import subprocess
import sys
from pathlib import Path

from proworksim.storage import Store, digest

ROOT = Path(__file__).resolve().parents[1]


def cli(*arguments, expected=0):
    completed = subprocess.run([sys.executable, "-m", "proworksim", *map(str, arguments)],
                               capture_output=True, text=True)
    assert completed.returncode == expected, completed.stdout + completed.stderr
    return json.loads(completed.stdout) if completed.stdout else completed.stderr


def test_declare_run_cut_continue_and_assess_without_mutating_the_world(tmp_path):
    world = tmp_path / "world"
    spec = ROOT / "examples/scenarios-v10/report-direct.json"
    assert cli("scenario-build", world, "--spec", spec)["status"] == "ready"
    first = tmp_path / "cut.json"
    cut = cli("staff-run", world, "--max-opportunities", 4, "--output", first)
    assert cut["status"] == "budget_exhausted"
    initial = json.loads(first.read_text())
    previous_events = initial["worker_checkpoint"]["experience"]["events"]
    assert previous_events
    second = tmp_path / "continued.json"
    result = cli("staff-run", world, "--checkpoint", first, "--output", second)
    assert result["status"] == "completed"
    final = json.loads(second.read_text())
    assert final["worker_checkpoint"]["experience"]["events"][:len(previous_events)] == previous_events
    assert final["scenario_sha256"] == initial["scenario_sha256"]
    state = Store(world).load()
    assert all(item["status"] == "accepted" for item in state["work_items"].values())
    original_state = (Store(world).control / "state.json").read_bytes()
    original_versions = {str(path): digest(path.read_bytes())
                         for path in (world / "control" / "versions").rglob("*") if path.is_file()}
    assert original_versions
    output = tmp_path / "assessment.json"
    assessment = cli("episode-assess", world, "--experience", second, "--output", output)
    assert assessment["status"] == "complete"
    parsed = json.loads(output.read_text())["assessment"]
    assert "passed" not in parsed
    assert parsed["independent_targets"]["status"] == "unassessed"
    assert parsed["process_constraints"]["status"] == "unassessed"
    assert (Store(world).control / "state.json").read_bytes() == original_state
    assert {str(path): digest(path.read_bytes())
            for path in (world / "control" / "versions").rglob("*") if path.is_file()} == original_versions
    before = (Store(world).control / "state.json").read_bytes()
    cli("staff-run", world, "--checkpoint", first, "--output", tmp_path / "stale.json", expected=2)
    cli("staff-run", world, "--output", tmp_path / "no-checkpoint.json", expected=2)
    cli("staff-run", world, "--checkpoint", second, "--output", world / "unsafe.json", expected=2)
    assert (Store(world).control / "state.json").read_bytes() == before


def test_unbuildable_scenario_is_reported_without_substituting_a_template(tmp_path):
    spec = json.loads((ROOT / "examples/scenarios-v10/finance-direct.json").read_text())
    spec["projects"][0]["recipe"] = "not-a-template"
    path = tmp_path / "bad-spec.json"
    path.write_text(json.dumps(spec))
    result = cli("scenario-build", tmp_path / "world", "--spec", path, expected=1)
    assert result["status"] == "unbuildable"
    assert result["manifest"] is None
    assert not (tmp_path / "world").exists()
