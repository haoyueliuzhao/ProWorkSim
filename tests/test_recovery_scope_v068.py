import fcntl
from pathlib import Path
from types import FunctionType, SimpleNamespace

import pytest

from proworksim import software_benchmark_dispatch_v066 as primary
from proworksim import software_benchmark_recovery_scope_v068 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def fixture(tmp_path, monkeypatch):
    run, claims = tmp_path / 'recovery', tmp_path / 'claims'
    run.mkdir()
    claims.mkdir()
    for name, path in {'API_ROOT': run, 'CLAIM_FILE': run / 'capacity.json',
        'LEASE_FILE': claims / 'active-v068-coordinator.json', 'AUTH_FILE': run / 'auth.json',
        'PLAN_FILE': run / 'plan.json'}.items():
        monkeypatch.setattr(scope, name, path)
    write_new(scope.AUTH_FILE, {})
    write_new(scope.PLAN_FILE, {})
    namespace = {**vars(primary), 'physical_capacity': lambda: {'passed': True,
        'memory_available_bytes': 4096 * scope.GIB, 'disk_free_bytes': 4096 * scope.GIB}}
    budget = FunctionType(primary._budget.__code__, namespace, argdefs=primary._budget.__defaults__)
    def locked(active, cpu, ram):
        with (claims / 'allocation.lock').open('a+b') as stream:
            with pytest.raises(BlockingIOError):
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return budget(active, cpu, ram)
    monkeypatch.setattr(scope, 'primary', SimpleNamespace(host_cpu_pool=lambda: list(range(176)),
        _budget=locked, _write_claim=primary._write_claim, load=primary.load, reference=reference))
    monkeypatch.setattr(scope, 'require_allowed', lambda *args, **kwargs: None)
    return claims


def test_auxiliary_reserves_inside_original_pool_and_releases_only_exact_owned_lease(tmp_path, monkeypatch):
    claims = fixture(tmp_path, monkeypatch)
    other = claims / 'active-model-0.json'
    raw = b'{"reserved_cpu":140,"reserved_memory_bytes":858993459200}'
    other.write_bytes(raw)
    claim = scope.reserve_api_coordinator()
    value = scope.load(claim)
    assert value['admission']['reserved_memory_bytes_after'] == 832 * scope.GIB
    assert value['cpu_affinity'] == [164, 165, 166, 167]
    scope.release_api_coordinator(claim)
    assert other.read_bytes() == raw and not scope.LEASE_FILE.exists()
    assert scope.CLAIM_FILE.exists()
    with pytest.raises(ValueError, match='cannot be restarted'):
        scope.reserve_api_coordinator()


def test_full_pool_refuses_admission_without_consuming_identity(tmp_path, monkeypatch):
    claims = fixture(tmp_path, monkeypatch)
    write_new(claims / 'active-full.json', {'reserved_cpu': 148, 'reserved_memory_bytes': 0})
    with pytest.raises(primary.ResourceBusy):
        scope.reserve_api_coordinator()
    assert not scope.CLAIM_FILE.exists() and not scope.LEASE_FILE.exists()


def test_foreign_auxiliary_lease_never_adopted_or_deleted(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    scope.LEASE_FILE.write_bytes(b'foreign')
    with pytest.raises(ValueError, match='cannot be adopted'):
        scope.reserve_api_coordinator()
    assert scope.LEASE_FILE.read_bytes() == b'foreign'


def test_api_runtime_checks_exact_unit_and_limits(tmp_path, monkeypatch):
    group = tmp_path / scope.API_UNIT
    group.mkdir()
    proc = tmp_path / 'cgroup'
    proc.write_text('0::/' + scope.API_UNIT + '\n')
    for name, value in {'memory.max': str(16 * scope.GIB), 'memory.swap.max': '0', 'pids.max': '512'}.items():
        (group / name).write_text(value)
    monkeypatch.setattr(scope, 'Path', lambda path: proc if path == '/proc/self/cgroup'
        else tmp_path if path == '/sys/fs/cgroup' else Path(path))
    monkeypatch.setattr(scope, 'os', SimpleNamespace(getuid=lambda: 1000, geteuid=lambda: 1000,
        sched_getaffinity=lambda _: {164, 165, 166, 167}))
    monkeypatch.setattr(scope, 'cpu_affinity', lambda: [164, 165, 166, 167])
    assert scope.verify_api_host_limits()['cpu_affinity'] == [164, 165, 166, 167]
    (group / 'memory.max').write_text('max')
    with pytest.raises(ValueError, match='exact CPU/RAM/PID'):
        scope.verify_api_host_limits()
