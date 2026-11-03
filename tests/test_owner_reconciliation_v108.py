"""Local reservation changes only; no live services, API or Docker calls."""
import importlib.util

import pytest

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim import software_benchmark_scope_v107 as previous


def test_exact_stopped_owner_release_requires_physical_and_reservation_proof(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('owner_reconciliation_cpu_v108',
        previous.ROOT/'tools/reconcile_nonthinking_owner_v108.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    claims = tmp_path/'claims'
    claims.mkdir()
    api = tmp_path/'api'
    api.mkdir()
    authorization = write_new(tmp_path/'auth.json', {'synthetic': True})
    lease = claims/'active-v107-coordinator.json'
    claim = write_new(api/'capacity.json', {
        'spec': {'role': 'auxiliary_coordinator', 'unit': previous.API_UNIT},
        'lease': str(lease), 'authorization': authorization})
    lease.write_bytes(previous.checked(claim).read_bytes())
    monkeypatch.setattr(previous, 'require_allowed', lambda *_a, **_kw: {})
    monkeypatch.setattr(previous, 'AUTH_FILE', tmp_path/'auth.json')
    monkeypatch.setattr(previous, 'CLAIM_FILE', api/'capacity.json')
    monkeypatch.setattr(previous, 'LEASE_FILE', lease)
    monkeypatch.setattr(previous, 'API_ROOT', api)
    monkeypatch.setattr(module, 'OUTPUT', tmp_path/'proof.json')
    def physical():
        return {'passed': True, 'synthetic': True}
    def inactive():
        return {'ActiveState': 'inactive', 'SubState': 'dead', 'MainPID': '0'}
    with pytest.raises(ValueError, match='inactive'):
        module.reconcile(inspect_unit=lambda: {'ActiveState': 'active', 'MainPID': '12'},
                         validate_physical=physical)
    assert lease.read_bytes() == previous.checked(claim).read_bytes()
    blocker = claims/'active-grader-0.json'
    blocker.write_text('{}')
    with pytest.raises(ValueError, match='still reserved'):
        module.reconcile(inspect_unit=inactive, validate_physical=physical)
    blocker.unlink()
    lease.write_text('{}')
    with pytest.raises(ValueError, match='bytes changed'):
        module.reconcile(inspect_unit=inactive, validate_physical=physical)
    lease.write_bytes(previous.checked(claim).read_bytes())
    result = module.reconcile(inspect_unit=inactive, validate_physical=physical)
    assert result['released'] is True and result['claim'] == claim
    assert result['Docker_mutations'] == result['service_mutations'] == result['model_calls'] == 0
    assert not lease.exists()
    assert previous.load(reference(api/'coordinator-capacity-released.json')) == {'claim': claim, 'released': True}
    assert module.reconcile(inspect_unit=inactive, validate_physical=physical) == result
