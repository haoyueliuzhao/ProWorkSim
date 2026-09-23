"""Actual CLI calls resume public policy state and validate before world mutation."""

import json
import os
import subprocess
import sys
from pathlib import Path

from proworksim.storage import digest
from scripts.continuous_worker_experiment import Evidence


def cli(*arguments):
    source = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run(
        [sys.executable, "-m", "proworksim", *map(str, arguments)],
        env={**os.environ, "PYTHONPATH": source}, capture_output=True, text=True,
    )


def setup(tmp_path):
    evidence = Evidence(tmp_path / "fixture", "budget")
    evidence.install()
    ports = tmp_path / "ports.json"
    ports.write_text(json.dumps({"A": {"actor": "alice", "project": "A"},
                                 "B": {"actor": "bob", "project": "B"}}))
    return evidence, ports


def test_cli_initial_budget_and_completed_step_checkpoint_resume(tmp_path):
    ev, ports = setup(tmp_path)
    first_path, second_path = tmp_path / "first.json", tmp_path / "second.json"
    first = cli("world-continue", ev.world.store.root, "--ports", ports,
                "--max-actions", 1, "--output", first_path)
    assert first.returncode == 0, first.stderr
    initial = json.loads(first_path.read_text())
    assert initial["result"]["status"] == "budget_exhausted"
    assert initial["checkpoint"]["actions"] == 1
    second = cli("world-continue", ev.world.store.root, "--ports", ports,
                 "--checkpoint", first_path, "--max-actions", 30, "--output", second_path)
    assert second.returncode == 0, second.stderr
    resumed = json.loads(second_path.read_text())
    assert resumed["result"]["status"] == "completed"
    assert resumed["checkpoint"]["run_id"] == initial["checkpoint"]["run_id"]
    prefix = initial["checkpoint"]["transcript"]
    assert resumed["checkpoint"]["transcript"][:len(prefix)] == prefix
    calls = [row["value"] for row in resumed["checkpoint"]["transcript"] if row["kind"] == "tool_call"]
    assert len({row["request_key"] for row in calls}) == len(calls) == resumed["result"]["actions"]
    assert ev.delivered_values() == {"A::work-1": 11, "B::work-1": 7}
    assert all(row["evaluation"]["passed"] for row in ev.evaluations())


def test_cli_invalid_inputs_and_output_paths_leave_world_bytes_unchanged(tmp_path):
    ev, ports = setup(tmp_path)
    root = ev.world.store.root
    before = {str(path.relative_to(root)): digest(path.read_bytes())
              for path in root.rglob("*") if path.is_file()}
    bad_ports = tmp_path / "bad-ports.json"
    bad_ports.write_text(json.dumps({"A": {"actor": "not-an-actor", "project": "A"}}))
    duplicate_ports = tmp_path / "duplicate-ports.json"
    duplicate_ports.write_text('{"A":{"actor":"alice","project":"A"},"A":{"actor":"bob","project":"B"}}')
    bad_checkpoint = tmp_path / "bad-checkpoint.json"
    bad_checkpoint.write_text(json.dumps({"checkpoint_version": "unsupported"}))
    fresh = tmp_path / "never-created.json"
    attempts = [
        ["--ports", bad_ports, "--output", fresh],
        ["--ports", duplicate_ports, "--output", fresh],
        ["--ports", ports, "--output", root / "control" / "forbidden.json"],
        ["--ports", ports, "--output", ports],
        ["--ports", ports, "--output", fresh, "--max-actions", 0],
        ["--ports", ports, "--output", fresh, "--checkpoint", bad_checkpoint],
    ]
    for arguments in attempts:
        result = cli("world-continue", root, *arguments)
        assert result.returncode == 2, (arguments, result.stdout, result.stderr)
        assert not fresh.exists()
        assert {str(path.relative_to(root)): digest(path.read_bytes())
                for path in root.rglob("*") if path.is_file()} == before
