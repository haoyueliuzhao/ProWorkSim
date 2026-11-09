"""Regression tests cover the concrete controller imports, not just a module alias."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_role_baseline_runtime_v172 as managed
from proworksim.software_collaboration_runtime_observer_v172 import RuntimeObservationBridge
from proworksim.storage import json_bytes

ROOT = Path(__file__).resolve().parents[1]


def controller_runtime_bindings():
    tree = ast.parse((ROOT/'tools/run_communication_controller_v172.py').read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    selected = [n for n in main.body if
        (isinstance(n, ast.ImportFrom) and any(a.asname == 'managed' for a in n.names))
        or (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Tuple)
            and [getattr(e, 'id', None) for e in n.targets[0].elts] == ['run_fragment', 'close_runtime'])]
    assert len(selected) == 2
    assert not any(isinstance(n, ast.ImportFrom) and any(a.name == 'run_fragment' for a in n.names)
                   for n in ast.walk(main))
    ns = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])),
        'actual-controller-runtime-bindings', 'exec'), ns)
    assert ns['managed'] is managed
    return ns


@pytest.mark.parametrize('pending', [False, True])
def test_actual_controller_binding_preserves_export_for_passive_error_only(monkeypatch, pending):
    ns = controller_runtime_bindings()
    original = {'status': 'bounded_work_closed', 'execution_integrity_failure': None}
    monkeypatch.setattr(managed.previous.observed, 'run_fragment', lambda *a, **kw: copy.deepcopy(original))
    observation = SimpleNamespace(errors=[{'scope': 'public_tests', 'message': 'metric fault'}],
        safely=lambda *a: None, close_partial=lambda *a: None)
    runtime = SimpleNamespace(owner=SimpleNamespace(observation=observation,
        source_capture_v157=SimpleNamespace(pending={'unreturned': 1} if pending else {})))
    boundary = ns['run_fragment'](None, runtime)
    assert boundary['measurement_partial'] is True
    assert boundary['execution_integrity_failure'] == ('measurement_capture_incomplete' if pending else None)
    assert ns['close_runtime'] is managed.close_runtime


def test_actual_17002_large_public_report_roundtrip(tmp_path):
    child = json.loads((ROOT/'runs/software-benchmark-v170/completion-recovery13-r1/episodes/17002/'
        'controller-output/controller-result.json').read_bytes())
    reports = []
    def walk(value):
        if isinstance(value, dict):
            report = value.get('test_evidence')
            if isinstance(report, dict) and len(json_bytes(report)) > 4*1024**2:
                reports.append((value, report))
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(child['managed_boundary'])
    assert reports, 'The original failure must exercise the derived4MiB mismatch'
    value, report = reports[0]
    source = value.get('source_reference', {'object_id': 'source', 'version_id': 'v1'})
    bridge = RuntimeObservationBridge(tmp_path, team_id='actual17002', members=['member_001'])
    result = {'source_reference': source, 'test_evidence': report, 'passed': False,
        'validation_status': value.get('validation_status', 'failed'),
        'execution': {'executed': True, 'argv': ['pytest'], 'returncode': 1, 'timed_out': False}}
    before = json_bytes(result)
    event = bridge.observe_public_test('member_001', result)
    assert bridge.observe_public_test('member_001', result) == event
    data = bridge.log._rows[event]['data']
    assert json_bytes(result) == before  # Passive observer cannot alter model feedback.
    assert Path(data['report']['path']).read_bytes() == json_bytes(report)
    assert len(data['sessions']) == 1
    assert bridge.log.summary()['public_tests']['executed'] == 1
    bridge.log.close()


def test_team_factory_uses_the_repaired_observer():
    builder = managed.build_team_owner.__globals__['observed'].build_team_owner
    assert builder.__globals__['RuntimeObservationBridge'] is RuntimeObservationBridge
