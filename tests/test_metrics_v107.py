"""CPU-only lifecycle routing and no-call successful admission reuse."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from proworksim import software_benchmark_host_api_v106 as host
from proworksim.software_benchmark_candidates_v054 import write_new
from proworksim.software_benchmark_expansion_episode_v069 import clone_function


def test_report_uses_new_manager_without_mutating_previous_history(tmp_path):
    source = Path(__file__).resolve().parents[1]/'tools/summarize_interface_panel_v107.py'
    spec = importlib.util.spec_from_file_location('metrics_v107_fixture', source)
    metrics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metrics)
    panel = json.loads(metrics.PANEL.read_bytes())
    row = panel['rows'][0]
    old = tmp_path/'api-coordinator-v106'
    old.mkdir()
    old_ref = write_new(old/'run-summary.json', {'generation': {row['slot_id']: {'status': 'technical_unknown'}}})
    original = Path(old_ref['path']).read_bytes()
    current = tmp_path/'api-coordinator-v107'
    current.mkdir()
    write_new(current/'progress.json', {'generation': {row['slot_id']: {'status': 'running'}}})
    result = metrics.run(metrics.PANEL, tmp_path)
    assert Path(result['coordinator_source']['path']).parent == current
    assert result['groups'][row['arm']]['generation_states']['running'] == 1
    assert result['groups']['REF']['planned'] == result['groups']['PROJECT']['planned'] == 50
    assert Path(old_ref['path']).read_bytes() == original
    assert (tmp_path/'reporting-v107/summary.json').exists()


def test_existing_success_returns_before_metadata_or_completion(tmp_path):
    qualification = tmp_path/'result.json'
    expected = {'passed': True, 'model_calls': 2, 'thinking': False}
    write_new(qualification, expected)
    scope = SimpleNamespace(require_allowed=lambda *_a, **_k: None,
                            load=lambda ref: json.loads(Path(ref['path']).read_bytes()))
    qualify = clone_function(host.qualify, {**host.qualify.__globals__,
                                            'scope': scope, 'QUALIFICATION': qualification})
    class NoRequests:
        def __getattr__(self, name):
            raise AssertionError('Successful admission must not call '+name)
    assert qualify(NoRequests(), NoRequests()) == expected
