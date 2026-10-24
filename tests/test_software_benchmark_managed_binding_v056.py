"""The public-test deadline policy must be reached through real v056 assembly."""
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_managed_v056 as managed
from proworksim.software_benchmark_public_tests_v056 import PublicTestRunner, VERSION
from proworksim.storage import json_bytes
from test_software_benchmark_world_v056 import prepare


class ReachedSDKFactory(Exception):
    pass


def test_old_callback_is_rejected_before_loading_an_sdk_worker(tmp_path, monkeypatch):
    prepared, _port, _calls = prepare(tmp_path)
    reached = []
    monkeypatch.setattr(managed, "worker_type", lambda: reached.append(True))
    with pytest.raises(ValueError, match="episode-bound public-test runner"):
        managed.build_runtime(None, prepared, tmp_path / "runtime",
                              deadline=SimpleNamespace(hard_at=5000.))
    assert reached == []


def test_explicit_public_test_binding_is_installed_before_sdk_creation(tmp_path, monkeypatch):
    prepared, _port, _calls = prepare(tmp_path)
    before = prepared.world.store.load()
    guard = tmp_path / "guard.json"
    guard.write_bytes(json_bytes({"claim_id": "synthetic", "stop_requested": False}))

    def factory():
        assert isinstance(prepared.source_provider.runner, PublicTestRunner)
        assert prepared.world.source_provider.runner is prepared.source_provider.runner
        raise ReachedSDKFactory

    monkeypatch.setattr(managed, "worker_type", factory)
    binding = {"socket_path": str(tmp_path / "synthetic-public.sock"),
               "identity": {"version": VERSION, "claim_id": "synthetic"},
               "hard_at": 5000., "guard_path": str(guard)}
    with pytest.raises(ValueError, match="cannot extend"):
        managed.build_runtime(None, prepared, tmp_path / "bad-runtime",
            deadline=SimpleNamespace(hard_at=4000.), public_test_config=binding)
    with pytest.raises(ReachedSDKFactory):
        managed.build_runtime(None, prepared, tmp_path / "runtime",
            deadline=SimpleNamespace(hard_at=5000.), public_test_config=binding)
    assert prepared.source_provider.runner.client.hard_at == 5000.
    assert (tmp_path / "runtime/public-tests-client/binding.json").exists()
    assert prepared.world.store.load() == before
