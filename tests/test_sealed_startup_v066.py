"""Necessary controls for read-only startup and exact deployment-proof reuse."""
import ast
import copy
import importlib.util
from pathlib import Path

import pytest

from proworksim import software_benchmark_deployment_reuse_v066 as reuse
from proworksim import software_benchmark_dispatch_v066 as policy


ROOT = policy.ROOT


def test_reuse_actual_passed_controls_and_reject_changed_formal_limits(monkeypatch):
    proof = reuse.value()
    assert set(proof['diagnostics']) == {'REF', 'PROJECT'}
    assert proof['new_diagnostic_containers'] == 0
    original = policy.load

    def altered(ref):
        value = original(ref)
        if Path(ref['path']) == policy.PLAN_FILE:
            value = copy.deepcopy(value)
            value['constraints']['controller_memory_bytes'] += 1024**3
        return value

    monkeypatch.setattr(policy, 'load', altered)
    with pytest.raises(ValueError, match='Formal deployment limits'):
        reuse.value()


def test_execution_lifecycle_changes_only_the_prepare_call():
    old_path = ROOT / 'artifacts/software-benchmark-v066/deployment-diagnostic-r2/sources/tools/run_full_benchmark_v066.py'
    new_path = ROOT / 'tools/run_full_benchmark_v066.py'
    old = next(node for node in ast.parse(old_path.read_bytes()).body
               if isinstance(node, ast.FunctionDef) and node.name == 'run')
    new = next(node for node in ast.parse(new_path.read_bytes()).body
               if isinstance(node, ast.FunctionDef) and node.name == 'run')
    changes = 0
    for node in ast.walk(old):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'prepare':
            node.func.id = 'sealed_plan_reference'
            changes += 1
    assert changes == 1
    assert ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False)


def test_sealed_plan_loading_never_prepares_and_rejects_forged_sources(monkeypatch):
    spec = importlib.util.spec_from_file_location('v066_sealed_startup_control', ROOT / 'tools/run_full_benchmark_v066.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def marker(name):
        return {'path': str(name), 'sha256': 'a'*64, 'bytes': 1}
    plan_ref = marker(module.RUN_ROOT / 'coordinator-plan.json')
    proposal_ref = marker('proposal')
    source_refs = [marker('source')]
    plan = {'plan': marker(policy.PLAN_FILE), 'continuation_inventory': marker(policy.RESUME_FILE),
            'sources': source_refs, 'controls': [marker('one-prepared-control')]}
    seen = []
    monkeypatch.setattr(module, 'prepare', lambda: pytest.fail('Runtime must not prepare again'))
    monkeypatch.setattr(module.policy, 'require_v066_allowed', lambda _: {'proposal': proposal_ref})
    monkeypatch.setattr(module.policy, 'sources', lambda: source_refs)
    monkeypatch.setattr(module, 'reference', marker)
    monkeypatch.setattr(module, 'checked', lambda ref: seen.append(ref))
    monkeypatch.setattr(module, 'load', lambda ref: {'coordinator_plan': plan_ref} if ref == proposal_ref else plan)
    assert module.sealed_plan_reference() == plan_ref
    assert seen == plan['controls']
    plan['sources'] = []
    with pytest.raises(ValueError, match='source/configuration'):
        module.sealed_plan_reference()
