"""One combined cold SDK regression; all generation and public tests are scripted."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

import pytest

from proworksim.software_benchmark_sdk_bundle_v066 import runtime_environment


def test_real_aligned_factory_summarizes_reviews_and_keeps_delivery_version():
    root = Path(__file__).resolve().parents[1]
    sdk = root/'runs/software-benchmark-v108/sdk-bundle-r1/stage/opt/pws-runtime'
    if not (sdk/'bin/python').is_file():
        pytest.skip('The pinned local SDK bundle is required; this control never downloads one')
    env = runtime_environment(sdk)
    env.update(PYTHONPATH=str(root/'src')+os.pathsep+env['PYTHONPATH'],
        LITELLM_LOCAL_MODEL_COST_MAP='True', OPENHANDS_SUPPRESS_BANNER='1')
    parent = root/'runs/software-benchmark-v117/cpu-controls'
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='regression-', dir=parent) as directory:
        output = Path(directory)/'combined'
        result = subprocess.run([str(sdk/'bin/python'), str(root/'tools/check_repair_sdk_v117.py'),
            '--output', str(output), '--force-summary'], env=env, cwd=root,
            capture_output=True, text=True, timeout=90, check=False)
        assert result.returncode == 0, result.stdout[-3000:] + '\n' + result.stderr[-9000:]
        evidence = json.loads((output/'result.json').read_bytes())
        assert evidence['passed'] is True
        assert evidence['scripted_agent_responses'] == 7
        assert evidence['scripted_summary_responses'] == 1
        assert evidence['scripted_total_tokens'] == 2240
        assert evidence['old_legal_delivery_preserved'] is True
        assert evidence['old_delivery_is_final_tree'] is False
        assert evidence['final_tree_automatically_tested_or_delivered'] is False
        assert not any(evidence['prohibited_operations'].values())
