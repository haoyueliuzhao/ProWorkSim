"""Fixed successor guards with filesystem/process fixtures only; no GPU work."""

import copy
import json

import pytest

from scripts.continue_harness_v017 import (
    CANDIDATES,
    LANES,
    MIN_FREE_MIB,
    admit_pilot,
    h1_finished,
    launch_job,
    migration_allows_admission,
    observe_job,
    resource_decision,
)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_only_both_actual_launcher_exits_release_H1_guard(tmp_path):
    paths = {name: tmp_path / (name + ".json") for name in CANDIDATES}
    write(paths[CANDIDATES[0]], {"end": 2, "exit_code": 0})
    write(paths[CANDIDATES[1]], {"pid": 123, "start": 1})
    assert h1_finished(paths)[0] is False
    # Nonzero ending is real closure, not an imputed score. Reporter decides eligibility later.
    write(paths[CANDIDATES[1]], {"end": 3, "exit_code": 1})
    assert h1_finished(paths)[0] is True
    assert set(tmp_path.iterdir()) == set(paths.values())


def test_literal_capacity_thresholds_and_disjoint_lanes():
    raw = {
        "gpu_returncode": 0,
        "process_returncode": 0,
        "gpu_stdout": "0, GPU-A, 65536, 81920, 3\n1, GPU-B, 65535, 81920, 90\n",
        "process_stdout": "GPU-B, 99, 16385, another-project\n",
    }
    original = copy.deepcopy(raw)
    assert resource_decision(raw, [0, 1], MIN_FREE_MIB["qwen35-9b"])["ready"] is False
    raw["gpu_stdout"] = raw["gpu_stdout"].replace("65535", "65536")
    assert resource_decision(raw, [0, 1], MIN_FREE_MIB["qwen35-9b"])["ready"] is True
    assert resource_decision(raw, [0, 1], MIN_FREE_MIB["qwen38-27b"])["ready"] is False
    assert original["process_stdout"] == raw["process_stdout"]
    for lanes in LANES.values():
        assert set(lanes["learning"]).isdisjoint(lanes["projects"])
    assert LANES["qwen38-27b"] == {"learning": [0, 1, 2, 3], "projects": [4, 5, 6, 7]}


def test_pilot_file_written_only_after_actual_migration_validator_accepts(tmp_path):
    planned = {
        "experiment_id": "h2-pilot-v017",
        "initialization": {"restore_checkpoint_permitted": False},
        "launch_gate": {"state": "awaiting_actual_migration"},
        "windows": ["fixed-112-slots"],
    }
    plan = tmp_path / "pilot-planned.json"
    migration = tmp_path / "migration/online/report.json"
    admitted = tmp_path / "pilot-admitted.json"
    write(plan, planned)
    write(migration, {"status": "complete", "actor_steps_total": 0})
    calls = []

    def reject(protocol, **kwargs):
        calls.append(protocol)
        assert not admitted.exists()
        assert kwargs["restore_checkpoint"] is None
        raise ValueError("No actual shared update")

    with pytest.raises(ValueError, match="actual shared update"):
        admit_pilot(
            plan,
            migration,
            admitted,
            model="fixed-model",
            manifest="fixed-manifest",
            validator=reject,
        )
    assert not admitted.exists() and json.loads(plan.read_text()) == planned

    def accept(protocol, **kwargs):
        assert not admitted.exists()
        assert protocol["windows"] == planned["windows"]
        assert protocol["launch_gate"]["migration_report"]["path"] == str(migration)
        return {"status": "admitted"}

    admit_pilot(
        plan, migration, admitted, model="fixed-model", manifest="fixed-manifest", validator=accept
    )
    assert (
        json.loads(admitted.read_text())["initialization"]["restore_checkpoint_permitted"] is False
    )
    with pytest.raises(FileExistsError):
        admit_pilot(plan, migration, admitted, model="x", manifest="y", validator=accept)


def test_launch_success_is_not_actual_stage_success_or_retry(tmp_path):
    run = tmp_path / "migration"
    prefix = tmp_path / "launch/migration"
    job = {
        "name": "migration",
        "status": "running",
        "prefix": str(prefix),
        "output": str(run),
        "command": ["fixed", "--output", str(run)],
        "gpus": [0, 1],
        "launch_attempted": True,
        "launch_attempt_count": 1,
    }
    write(
        prefix.with_suffix(".launch.json"),
        {
            "command": job["command"],
            "CUDA_VISIBLE_DEVICES": "0,1",
            "pid": 9,
            "end": 10,
            "exit_code": 0,
        },
    )
    write(
        run / "online/report.json",
        {"status": "stopped_probability_mismatch", "actor_steps_total": 0},
    )
    observe_job(job)
    assert job["status"] == "failed_or_incomplete"
    assert migration_allows_admission(job) is False
    observe_job(job)
    assert job["launch_attempt_count"] == 1
    job.update(status="complete", actual_status="complete")
    assert migration_allows_admission(job) is True
    job["exit_code"] = 1
    assert migration_allows_admission(job) is False


def test_detached_launch_has_persisted_single_intent_and_no_restart(tmp_path, monkeypatch):
    from scripts import continue_harness_v017 as module

    launcher = tmp_path / "launcher.py"
    launcher.write_text("fixture only")
    config = {
        "source": str(tmp_path),
        "source_commit": "fixed",
        "python": "fixture-python",
        "launcher": module.ref(launcher),
        "environment": {},
    }
    job = {
        "name": "migration",
        "status": "waiting_resources",
        "launch_attempted": False,
        "launch_attempt_count": 0,
        "output": str(tmp_path / "new-run"),
        "prefix": str(tmp_path / "launch/migration"),
        "gpus": [0, 1],
        "command": ["fixed", "arguments"],
    }
    state = {"jobs": {"migration": job}}
    calls = []
    monkeypatch.setattr(module, "assert_source", lambda *args: "fixed")

    def launch(command, **kwargs):
        recorded = json.loads((tmp_path / "state.json").read_text())["jobs"]["migration"]
        assert recorded["status"] == "launch_intent" and recorded["launch_attempt_count"] == 1
        assert kwargs["start_new_session"] is True
        assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "0,1"
        calls.append(command)
        return type("Child", (), {"pid": 77})()

    monkeypatch.setattr(module.subprocess, "Popen", launch)
    launch_job(config, state, job, tmp_path)
    assert job["status"] == "running" and len(calls) == 1
    with pytest.raises(ValueError, match="restarted"):
        launch_job(config, state, job, tmp_path)
    assert len(calls) == 1
