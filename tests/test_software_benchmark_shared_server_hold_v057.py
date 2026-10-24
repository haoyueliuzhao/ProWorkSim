"""Shared-server hold is fail-closed before every new experiment resource entry."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from proworksim import software_benchmark_shared_server_hold_v057 as hold


def tool(name):
    path = Path(__file__).resolve().parents[1] / "tools" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_resource_entries_reject_before_configs_files_processes_or_containers(tmp_path, monkeypatch):
    from proworksim import software_benchmark_grader_nat_v057 as nat
    from proworksim import software_benchmark_grading_environment_v057 as environment
    from proworksim import software_benchmark_runner_v057 as runner
    from proworksim import software_benchmark_scorer_v057 as scorer

    admission = tool("check_ref_grading_environment_v057.py")
    rescore = tool("repair_ref_grading_environment_v057.py")
    controller = tool("run_ref_budget_controller_v057.py")
    config = tmp_path / "hold.json"
    config.write_text(json.dumps({"version": hold.VERSION, "hold": True,
                                 "automatic_release": False, "reason": "fixture incident"}))
    monkeypatch.setattr(hold, "HOLD_FILE", config)
    monkeypatch.setattr(runner, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["controller", "--config", str(tmp_path / "does-not-exist.json")])
    resource_calls = []

    def forbidden(*args, **kwargs):
        resource_calls.append((args, kwargs))
        pytest.fail("Shared-server hold must precede external resources")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(nat, "docker", forbidden)
    calls = [
        lambda: nat.start_registry(tmp_path / "nat"),
        lambda: environment.EnvironmentContainers.create(object.__new__(environment.EnvironmentContainers)),
        lambda: environment.EnvironmentContainer.start(object.__new__(environment.EnvironmentContainer)),
        lambda: scorer.score_request({}),
        lambda: runner.run({}, tmp_path / "model-slot"),
        lambda: admission.worker({}, 0),
        lambda: admission.run_one(tmp_path / "admission", {}, 0),
        lambda: admission.execute(tmp_path / "admission", None),
        lambda: rescore.prepare(tmp_path / "rescore", None),
        lambda: rescore.run_one({}, {}),
        lambda: rescore.run(tmp_path / "rescore"),
        controller.main,
    ]
    for operation in calls:
        with pytest.raises(hold.SharedServerHold, match="shared-server hold blocks"):
            operation()
    assert not resource_calls
    assert sorted(p.name for p in tmp_path.iterdir()) == ["hold.json"]


def test_missing_invalid_and_unreviewed_release_configuration_remain_held(tmp_path, monkeypatch):
    config = tmp_path / "hold.json"
    monkeypatch.setattr(hold, "HOLD_FILE", config)
    monkeypatch.setenv("PROWORKSIM_IGNORE_HOLD", "1")
    assert hold.read_hold()["hold"] is True
    for value in ("not json", "[]", json.dumps({"version": hold.VERSION, "hold": False,
                                               "automatic_release": False, "release_authorization": None})):
        config.write_text(value)
        assert hold.read_hold()["hold"] is True
        with pytest.raises(hold.SharedServerHold):
            hold.require_experiment_dispatch_allowed("fixture")
