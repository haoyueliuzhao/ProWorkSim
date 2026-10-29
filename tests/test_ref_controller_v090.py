"""Finite integration checks for the explicitly CPU-only v090 controller path."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_ref_controller_v090 import run_scripted_session

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('missing_label', ['delegate', 'rpc'])
def test_live_dependencies_cannot_enter_the_cpu_only_factory(tmp_path, missing_label):
    condition = json.loads((ROOT / 'runs/software-benchmark-v064/full-verified-r1/conditions/QWEN_REF_B5000K.json').read_bytes())
    delegate = SimpleNamespace(condition=condition, scripted_cpu_only=missing_label != 'delegate')
    rpc = type('UnstartedRPC', (), {'scripted_cpu_only': missing_label != 'rpc'})
    with pytest.raises(ValueError, match='scripted Qwen REF'):
        run_scripted_session(delegate=delegate, native_rpc_type=rpc, native_rpc_kwargs={},
            condition=condition, public_task='CPU fixture', public_context='',
            public_python='/synthetic/bin/python', output=tmp_path / 'controller', workspace=tmp_path,
            started={'guard_path': str(tmp_path / 'controller/guard.json')})
    assert not (tmp_path / 'controller').exists()


def test_real_sdk_controller_path_propagates_feedback_and_distinguishes_endpoints(tmp_path):
    runtime = ROOT / 'runs/software-benchmark-v066/sdk-bundle-r1/stage/opt/pws-runtime'
    python = runtime / 'bin/python'
    if not python.is_file():
        pytest.skip('Existing frozen SDK runtime is unavailable')
    env = os.environ.copy()
    env.update(PYTHONPATH=os.pathsep.join(map(str, [ROOT / 'src', runtime / 'site', runtime / 'overlay',
                                                 runtime / 'upstream-tools'])),
               OH_PERSISTENCE_DIR=str(tmp_path / 'empty-user-config'),
               LITELLM_LOCAL_MODEL_COST_MAP='True', PYTHON_DOTENV_DISABLED='1',
               PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='', NVIDIA_VISIBLE_DEVICES='void')
    run = subprocess.run([str(python), str(ROOT / 'tools/check_ref_controller_v090.py'),
                          '--output', str(tmp_path / 'control')],
                         env=env, capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stdout[-5000:] + run.stderr[-5000:]
    receipt = json.loads((tmp_path / 'control/result.json').read_bytes())
    assert receipt['passed'] and len(receipt['cases']) == 4
    assert not any(receipt['forbidden_operations'].values())
    assert receipt['model_calls'] == receipt['API_calls'] == receipt['Docker_operations'] == 0
    cases = {case['case']: case for case in receipt['cases']}
    assert cases['feedback_truncation']['boundary_kind'] == 'settled_output_truncation'
    assert not cases['feedback_truncation']['native_finished']
    assert cases['native_finish']['normal_completion']
    assert cases['technical_failure']['status'] == 'technical_unknown'
    assert cases['resource_boundary']['boundary_kind'] == 'original_resource_boundary'
    assert all(case['code_resolved'] is None for case in cases.values())
