"""Check ownership and resource admission without starting a service or GPU."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_ref_resident_v061 as resident


def test_gpu_capacity_uses_approved_lower_cache_threshold(monkeypatch):
    answer = ('2, GPU-31944e43-1557-aa29-82fb-5f541b2045a2, NVIDIA A800-SXM4-80GB, 81920, 50000\n'
              '3, GPU-7e01944c-768c-2f33-d58e-85d9b62ee185, NVIDIA A800-SXM4-80GB, 81920, 60440\n')
    monkeypatch.setattr(resident.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=answer))
    assert [c['gpu_index'] for c in resident.gpu_capacity()] == [3]


def test_memory_revision_changes_only_cache_reservation():
    old = resident.original_server_arguments(18161)
    new = resident.server_arguments(18161)
    changes = [(i, a, b) for i, (a, b) in enumerate(zip(old, new, strict=True)) if a != b]
    assert changes == [(old.index('--gpu-memory-utilization') + 1, '0.8', '0.6')]
    assert new[new.index('--max-model-len') + 1] == '131072'
    assert new[new.index('--max-num-seqs') + 1] == '1'
    assert new[new.index('--dtype') + 1] == 'bfloat16'


def test_shared_ram_and_disk_reserve_are_both_required(monkeypatch):
    real = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda self, *a, **k:
        'MemAvailable: 500000000 kB\n' if str(self) == '/proc/meminfo' else real(self, *a, **k))
    monkeypatch.setattr(resident.shutil, 'disk_usage', lambda _: SimpleNamespace(free=400 * resident.GIB))
    assert resident.shared_capacity_for(2)
    monkeypatch.setattr(resident.shutil, 'disk_usage', lambda _: SimpleNamespace(free=383 * resident.GIB))
    assert not resident.shared_capacity_for(1)


def test_stop_does_not_touch_unit_with_unproven_ownership(tmp_path, monkeypatch):
    monkeypatch.setattr(resident, 'RUNS', tmp_path)
    folder = tmp_path / 'model-0'
    folder.mkdir()
    (folder / 'spec.json').write_text('{}')
    monkeypatch.setattr(resident, 'validate_spec', lambda _: {'unit': 'proworksim-v061-model-0.service', 'ownership_token': 'ours'})
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='Description=another owner\nActiveState=active\nLoadState=loaded\n')
    monkeypatch.setattr(resident.subprocess, 'run', run)
    result = resident.stop_residents()
    assert result[0]['owned_unit_stopped'] is False
    assert len(calls) == 1 and 'stop' not in calls[0]


def test_failed_bus_query_cannot_be_reported_as_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(resident, 'RUNS', tmp_path)
    folder = tmp_path / 'model-0'
    folder.mkdir()
    (folder / 'spec.json').write_text('{}')
    monkeypatch.setattr(resident, 'validate_spec', lambda _: {'unit': 'proworksim-v061-model-0.service', 'ownership_token': 'ours'})
    monkeypatch.setattr(resident.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=1, stdout=''))
    assert resident.stop_residents()[0]['owned_unit_stopped'] is False


def test_ready_record_cannot_reuse_a_different_process(tmp_path, monkeypatch):
    monkeypatch.setattr(resident, 'RUNS', tmp_path)
    folder = tmp_path / 'model-0'
    folder.mkdir()
    (folder / 'spec.json').write_text('{}')
    (folder / 'ready.json').write_text('{"host_process":{"pid":22,"start_ticks":100}}')
    monkeypatch.setattr(resident, 'validate_spec', lambda _: {})
    monkeypatch.setattr(resident, 'process_identity', lambda _: {'pid': 22, 'start_ticks': 101})
    monkeypatch.setattr(resident, 'models_response', lambda *_: pytest.fail('Wrong process must not be queried'))
    assert resident.ready_residents() == []


def test_cpu_affinity_enforces_limit_without_user_cpu_controller():
    values = {'memory.max': str(96 * resident.GIB), 'memory.swap.max': '0', 'pids.max': '2048', 'cpu.max': None}
    result = resident.validate_cpu_memory_limits(values, range(24, 36), range(24, 36))
    assert result['cpu_cgroup_controller_available'] is False
    assert result['cpu_limit_enforced_by'] == 'inherited_process_affinity'
    with pytest.raises(ValueError, match='bounds differ'):
        resident.validate_cpu_memory_limits(values, range(24, 37), range(24, 36))
    with pytest.raises(ValueError, match='bounds differ'):
        resident.validate_cpu_memory_limits({**values, 'memory.max': 'max'}, range(24, 36), range(24, 36))


@pytest.mark.parametrize('index', [-1, 2, True, '0'])
def test_only_two_exact_owned_model_names(index):
    with pytest.raises(ValueError):
        resident.unit_name(index)
