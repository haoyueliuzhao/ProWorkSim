"""Preparation failures cannot reach a model supervisor; no real subprocess runs."""
from pathlib import Path

import pytest

from scripts import software_panel_pipeline_v053 as pipeline


@pytest.mark.parametrize("failed_gate", ["environment", "initial_capture"])
def test_failed_preparation_gate_preserves_evidence_and_never_launches_model(tmp_path, monkeypatch, failed_gate):
    base = {
        "project_root": str(tmp_path), "runtime_launcher": "/fixture/runtime",
        "native_python": "/fixture/native-python", "dependency_paths": ["/fixture/numerical-deps"],
    }
    environment_config, inventory = tmp_path / "environment.json", tmp_path / "inventory.json"
    pipeline.native.write(environment_config, {})
    pipeline.native.write(inventory, {})
    config = {
        "host_prepare_config_base": base, "environment_config": str(environment_config),
        "inventory": str(inventory), "harness_python": "/fixture/harness-python",
        "host_python": "/fixture/host-python",
        "paths": {"pipeline_root": str(tmp_path / "pipeline")},
    }
    config_path = tmp_path / "config.json"
    pipeline.native.write(config_path, config)
    monkeypatch.setattr(pipeline, "source_identity", lambda project: {"src": "fixed", "scripts": "fixed"})
    calls = []

    def executor(name, command, cwd, log_path):
        calls.append(name)
        log_path.write_text("Synthetic stage evidence.\n")
        arguments = command[command.index("-m") + 2:]
        output = Path(arguments[arguments.index("--output") + 1])
        if name == "environment_admission":
            pipeline.native.write_new(output, {
                "ready_to_freeze": failed_gate != "environment",
                "paused_common_system_fault": failed_gate == "environment", "model_runs_started": 0,
            })
        elif name == "freeze_panel":
            pipeline.native.write_new(output, {"main_task_ids": ["fixture"], "slots": []})
        elif name == "backend_control":
            pipeline.native.write_new(output, {"passed": True, "model_calls": 0, "generation_tokens": 0})
        elif name == "prepare_snapshot":
            output.mkdir()
            (output / "source").mkdir()
            pipeline.native.write_new(output / "preparation-plan.json", {})
        elif name == "initial_capture":
            output.mkdir()
            pipeline.native.write_new(output / "initial-inputs.json", {
                "passed": False, "rows": [], "new_model_generations": 0})
            return 78
        elif name == "readonly_report":
            pipeline.native.write_new(output, {"status": "paused", "main_completion_rate": None})
        else:
            pytest.fail("A failed preparation gate reached an unapproved stage: " + name)
        return 0

    assert pipeline.run_pipeline(config_path, executor=executor) == 78
    root = tmp_path / "pipeline"
    state = pipeline.host.read(root / "pipeline-state.json")
    assert state["status"] == "paused"
    assert state["formal_supervisor_entered"] is False and state["formal_completion_claimed"] is False
    assert "supervise" not in calls and "seal_model_plan" not in calls
    assert not (root / "evidence/model-admission.json").exists()
    assert not (root / "execution").exists()
    assert (root / "report.json").exists() and state["failure"]
    assert all(Path(stage["log_path"]).exists() for stage in state["stages"])
