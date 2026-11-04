"""No privileged operations: fake exact-parent cleanup preserves refusals."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def manager():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('v131_cleanup_CPU', root/'tools/run_fixed_organization_v131.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_empty_owned_parent_uses_approved_exact_gate_and_records_release(tmp_path):
    target = manager()
    calls = []
    release = {'path': 'CPU-only-owned-release', 'sha256': 'a'*64, 'bytes': 0}
    parent = SimpleNamespace(approved=lambda: calls.append('approved'),
        stop_empty=lambda: (calls.append('stop_empty') or release))
    result = target.cleanup_owned_parent(parent=parent, record_path=tmp_path/'cleanup.json')
    assert calls == ['approved', 'stop_empty']
    assert result['status'] == 'released' and result['parent_release'] == release
    assert result['force_stop'] is False and result['cleanup_deferred'] is False
    assert json.loads((tmp_path/'cleanup.json').read_bytes())['status'] == 'released'


def test_refused_cleanup_preserves_objects_and_the_original_exception(tmp_path):
    target = manager()
    calls = []
    def no_grant():
        raise PermissionError('CPU fixture: no exact parent grant')
    def never_stop():
        calls.append('forbidden stop')
        raise AssertionError('No grant means no stop call')
    denied = target.cleanup_owned_parent(parent=SimpleNamespace(approved=no_grant, stop_empty=never_stop),
        record_path=tmp_path/'not-authorized.json')
    assert not calls and denied['cleanup_deferred'] and not denied['root_grant_verified']
    def active_parent():
        calls.append('empty gate refused')
        raise PermissionError('CPU fixture: unknown or active owned child remains')
    with pytest.raises(ValueError, match='original task failure'):
        try:
            raise ValueError('original task failure')
        finally:
            result = target.cleanup_owned_parent(parent=SimpleNamespace(approved=lambda: None, stop_empty=active_parent),
                record_path=tmp_path/'active.json')
    assert calls == ['empty gate refused']
    assert result['status'] == 'cleanup_deferred' and result['owned_parent_preserved_for_review']
    assert json.loads((tmp_path/'active.json').read_bytes())['force_stop'] is False
