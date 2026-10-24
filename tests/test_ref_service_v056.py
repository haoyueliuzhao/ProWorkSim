from __future__ import annotations

import fcntl
import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_ref_service_v056 as service


def test_server_is_loopback_and_numerics_do_not_depend_on_port():
    left, right = service.server_arguments(18056), service.server_arguments(18059)
    position = left.index("--port") + 1
    assert left[position] == "18056" and right[position] == "18059"
    left[position] = right[position]
    assert left == right
    assert left[left.index("--host") + 1] == "127.0.0.1"
    assert left[left.index("--max-model-len") + 1] == "131072"
    assert left[left.index("--max-num-seqs") + 1] == "1"
    with pytest.raises(ValueError):
        service.server_arguments(80)


def test_capacity_accepts_shared_card_and_rejects_identity_change(monkeypatch):
    uuid = "GPU-12345678-1234-1234-1234-123456789abc"
    row = f"3, {uuid}, NVIDIA A800-SXM4-80GB, 81920, 70000\n"
    monkeypatch.setattr(service.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=row))
    spec = {"gpu_index": 3, "gpu_uuid": uuid}
    assert service.observe_card(spec)["capacity_available"] is True
    with pytest.raises(ValueError, match="identity"):
        service.observe_card({**spec, "gpu_index": 4})
    row = row.replace("70000", "66000")
    assert service.observe_card(spec)["capacity_available"] is False


def test_occupied_endpoint_releases_lease_without_attaching(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "ROOT", tmp_path)

    class OccupiedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def bind(self, *_):
            raise OSError("Address already in use")

    monkeypatch.setattr(service.socket, "socket", OccupiedSocket)
    with pytest.raises(OSError, match="already in use"):
        service.EndpointLease(18056)
    with (tmp_path / "runs/g56/locks/port-18056.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _resident_fixture(monkeypatch, tmp_path):
    folder = tmp_path / "resident"
    folder.mkdir()
    spec = {"root": str(folder)}
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    monkeypatch.setattr(service, "checked", lambda _: path)
    monkeypatch.setattr(service, "validate_spec", lambda body: body)
    return folder


def test_capacity_failure_allocates_nothing(monkeypatch, tmp_path):
    folder = _resident_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(service, "observe_card", lambda _: {"capacity_available": False})
    monkeypatch.setattr(service, "GpuLease", lambda *_: pytest.fail("No GPU lease expected"))
    assert service.run_service({}) == 75
    assert list(folder.iterdir()) == []


def test_old_resident_identity_cannot_restart(monkeypatch, tmp_path):
    folder = _resident_fixture(monkeypatch, tmp_path)
    (folder / "ready.json").write_text("{}")
    monkeypatch.setattr(service, "observe_card", lambda *_: pytest.fail("No hardware probe expected"))
    with pytest.raises(ValueError, match="Never restart"):
        service.run_service({})


def test_endpoint_failure_releases_gpu_lease(monkeypatch, tmp_path):
    folder = _resident_fixture(monkeypatch, tmp_path)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps({"root": str(folder), "gpu_uuid": "uuid", "port": 18056}))
    monkeypatch.setattr(service, "observe_card", lambda _: {"capacity_available": True})
    events = []

    class Lease:
        def __init__(self, _):
            events.append("leased")

        def close(self):
            events.append("released")

    monkeypatch.setattr(service, "GpuLease", Lease)
    monkeypatch.setattr(service, "EndpointLease", lambda _: (_ for _ in ()).throw(OSError("busy")))
    assert service.run_service({}) == 75
    assert events == ["leased", "released"]
    assert not (folder / "api-key.private").exists()
