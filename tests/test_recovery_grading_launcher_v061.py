import importlib.util
import json
import os
import pytest
from pathlib import Path
from types import SimpleNamespace

from proworksim.software_benchmark_candidates_v054 import reference

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v061_grading_launcher_test", ROOT / "tools/run_recovery_grading_v061.py")
grading = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grading)


def test_both_bootstrap_paths_remove_inherited_private_python_settings(tmp_path, monkeypatch):
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"):
        monkeypatch.setenv(key, "private-python312-setting")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    monkeypatch.setattr(grading, "BATCH_ROOT", tmp_path)
    monkeypatch.setattr(grading.policy, "require_v061_allowed", lambda *args, **kwargs: {})
    monkeypatch.setattr(grading, "capacity_available", lambda: True)
    seen = []
    def validate(command, kwargs):
        assert command[0] == str(ROOT / ".venv/bin/python")
        assert all(key not in kwargs["env"] for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"))
        assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == ""
        seen.append(command)
    def run(command, **kwargs):
        validate(command, kwargs)
        return SimpleNamespace(stdout=b'{}')
    def popen(command, **kwargs):
        validate(command, kwargs)
        return SimpleNamespace(poll=lambda: 0, returncode=0)
    monkeypatch.setattr(grading.subprocess, "run", run)
    monkeypatch.setattr(grading.subprocess, "Popen", popen)
    grading.prepare_manifest()
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"resource_key": "control-task-gold", "directory": str(tmp_path / "job")}))
    assert grading.run_request(reference(request))["returncode"] == 0
    assert len(seen) == 2
    assert os.environ["PYTHONHOME"] == "private-python312-setting"


def test_retain_creates_nested_directories_and_preserves_existing_records(tmp_path):
    path = tmp_path / "grading" / "control-task-gold" / "request.json"
    ref = grading.retain(path, {"immutable": True})
    assert ref == grading.retain(path, {"immutable": True})
    assert json.loads(path.read_text()) == {"immutable": True}
    with pytest.raises(ValueError, match="record changed"):
        grading.retain(path, {"immutable": False})
