"""Batch strict boundary and actual SDK controls in the existing private runtime."""
import json

import pytest


def test_real_pinned_sdk_gateway_chain(tmp_path):
    import os
    from pathlib import Path
    import subprocess

    root = Path(__file__).resolve().parents[1]
    runtime = root / "runs/software-benchmark-v066/sdk-bundle-r1/stage/opt/pws-runtime"
    python = runtime / "bin/python"
    if not python.is_file():
        pytest.skip("Existing pinned SDK bundle is unavailable")
    env = os.environ.copy()
    env.update(PYTHONPATH=os.pathsep.join(map(str, [root / "src", runtime / "site",
                                                 runtime / "overlay", runtime / "upstream-tools"])),
               OH_PERSISTENCE_DIR=str(tmp_path / "empty-user-config"),
               LITELLM_LOCAL_MODEL_COST_MAP="True", PYTHON_DOTENV_DISABLED="1",
               PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="", NVIDIA_VISIBLE_DEVICES="void")
    run = subprocess.run([str(python), str(root / "tools/check_nullable_cursor_v090.py"),
                          "--output", str(tmp_path / "sdk")],
                         env=env, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-3000:]
    receipt = json.loads((tmp_path / "sdk/result.json").read_text())
    assert receipt["passed"] and receipt["baseline_null_rejected"]
    assert len(receipt["positive_cases"]) == 16 and len(receipt["negative_cases"]) == 4
    assert receipt["scripted_responses"] == 21
    assert receipt["strict_boundary_controls"] == 19
    assert receipt["model_calls"] == receipt["remote_tool_calls"] == 0
    assert not any(receipt["forbidden_operations"].values())
